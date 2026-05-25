"""File library service — disk layout, segmentation cache, integrity.

Before this module existed the same concerns were tangled across
``api/files.py`` and ``api/rerender.py``, with a circular import broken
only by a lazy ``from pen_plotter.api.files import …`` inside
``_try_rehydrate``. The shape of the cycle made every refactor risky:

- ``api/files.py`` called ``remember_job`` from ``api/rerender.py``
  at upload time.
- ``api/rerender.py`` called ``find_original`` / ``read_meta`` from
  ``api/files.py`` during cache rehydration.

This service owns both sides:

- the on-disk layout (``<files_dir>/<file_id>/{original.<ext>,
  normalized.svg, meta.json}``)
- the in-memory bitmap segmentation LRU cache (``remember_job`` /
  ``forget_job``)
- the rehydration-from-disk path (``try_rehydrate``)
- the library integrity scan

The HTTP endpoints (``api/files.py`` and ``api/rerender.py``) are now
thin adapters over this module — neither imports the other.
"""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions, SegmentationResult
from pen_plotter.models import LayerInfo
from pen_plotter.persistence import get_file_record

_log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Disk layout
# ----------------------------------------------------------------------

_DEFAULT_FILES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "files"


def files_dir() -> Path:
    """Return the writable directory the library stores files under.

    Resolved at call time (not import time) so tests that monkey-patch
    the ``OMNIPLOT_FILES_DIR`` env var — or the ``api.files.FILES_DIR``
    module attribute — pick up the override.
    """
    # Late import keeps the api module out of the import graph here;
    # the attribute lookup is the supported override hook for tests
    # that were written before this service existed.
    try:
        from pen_plotter.api import files as files_mod  # noqa: PLC0415

        override = getattr(files_mod, "FILES_DIR", None)
        if override is not None:
            return Path(override)
    except Exception:
        pass
    return Path(os.environ.get("OMNIPLOT_FILES_DIR", _DEFAULT_FILES_DIR))


def file_dir(file_id: str) -> Path:
    """Directory holding all artefacts for ``file_id``."""
    return files_dir() / file_id


def meta_path(file_id: str) -> Path:
    """Path to the per-file ``meta.json``."""
    return file_dir(file_id) / "meta.json"


def svg_path(file_id: str) -> Path:
    """Path to the per-file normalized SVG."""
    return file_dir(file_id) / "normalized.svg"


def find_original(file_id: str) -> Path | None:
    """Return the original uploaded bytes file (any extension), if present."""
    directory = file_dir(file_id)
    if not directory.is_dir():
        return None
    for child in directory.iterdir():
        if child.is_file() and child.stem == "original":
            return child
    return None


def read_original_bytes(file_id: str) -> bytes | None:
    """Return the raw bytes of the original upload for ``file_id``.

    Tiny wrapper over :func:`find_original` + ``Path.read_bytes`` so
    callers — primarily the application-layer text rerender path —
    don't have to remember the disk layout. Returns ``None`` when the
    file is absent (deleted between library reads + the
    /preflight or /generate call).
    """
    path = find_original(file_id)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        # Concurrent delete or transient I/O failure — surface as a
        # "missing" rather than crash the generation pipeline. The
        # caller decides whether to fall back to ``plan.svg``.
        _log.warning("read_original_bytes: %s vanished mid-read", path)
        return None


# ----------------------------------------------------------------------
# Persisted metadata
# ----------------------------------------------------------------------


class FileMeta(BaseModel):
    """Full metadata persisted alongside the SVG (warnings, layers, etc.).

    Kept in this module rather than ``api/files.py`` so both the upload
    endpoint and the rerender service can validate the same shape
    without one importing the other.
    """

    layers: list[LayerInfo]
    warnings: list[str] = []
    upload_metadata: dict[str, Any] = {}
    # True when the upload pipeline produced a bitmap segmentation cache,
    # so /rerender can re-run a different algorithm against the same
    # colour clusters. False for vector sources (SVG, PDF).
    rerenderable: bool = False
    # BitmapOptions (as a dict) used at the original segmentation. Kept
    # on disk so the /rerender cache can be rehydrated after a backend
    # restart without re-uploading.
    bitmap_options: dict[str, Any] | None = None
    # Raw converter options dict from the original /files upload. Drives
    # the dedup change-detection path for non-bitmap converters
    # (typography, markdown, …) whose option schemas the bitmap-shaped
    # ``bitmap_options`` cannot represent.
    source_options: dict[str, Any] | None = None


def read_meta(file_id: str) -> FileMeta | None:
    """Return the parsed meta.json for ``file_id``, or ``None`` if absent."""
    path = meta_path(file_id)
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return FileMeta.model_validate(raw)


def read_meta_or_empty(file_id: str) -> FileMeta:
    """Like :func:`read_meta` but returns an empty FileMeta on missing file."""
    return read_meta(file_id) or FileMeta(layers=[])


def read_svg(file_id: str) -> str | None:
    """Return the normalized SVG for ``file_id``, or ``None`` if missing."""
    path = svg_path(file_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Bitmap segmentation cache
# ----------------------------------------------------------------------


def _load_cache_size() -> int:
    """Read the LRU cap from env, clamped to a sane range."""
    raw = os.environ.get("RERENDER_CACHE_SIZE", "64")
    try:
        size = int(raw)
    except ValueError:
        size = 64
    return max(4, min(256, size))


_CACHE_SIZE = _load_cache_size()


class CacheEntry:
    """One cached bitmap job: its segmentation + the original options."""

    __slots__ = ("segmentation", "options")

    def __init__(self, segmentation: SegmentationResult, options: BitmapOptions) -> None:
        """Bind segmentation + options together for cache storage."""
        self.segmentation = segmentation
        self.options = options


_CACHE: OrderedDict[str, CacheEntry] = OrderedDict()


def remember_job(
    job_id: str, segmentation: SegmentationResult, options: BitmapOptions
) -> None:
    """Stash a bitmap job's segmentation result for later ``/rerender`` calls."""
    _CACHE[job_id] = CacheEntry(segmentation, options)
    _CACHE.move_to_end(job_id)
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)


def forget_job(job_id: str) -> None:
    """Drop a cached job (e.g. when ``/upload`` replaces it)."""
    _CACHE.pop(job_id, None)


def get_cached(job_id: str) -> CacheEntry | None:
    """Return the cached entry for ``job_id`` and bump it to LRU MRU."""
    entry = _CACHE.get(job_id)
    if entry is not None:
        _CACHE.move_to_end(job_id)
    return entry


def clear_cache_for_tests() -> None:
    """Test-only hook so the cache doesn't leak between cases."""
    _CACHE.clear()


def _cache_contains(job_id: str) -> bool:
    """Test introspection."""
    return job_id in _CACHE


# ----------------------------------------------------------------------
# Rehydration
# ----------------------------------------------------------------------

# Outcomes — exported as constants so callers (the endpoint adapters)
# can return a machine-readable ``reason`` in the structured 404 detail
# without redefining the strings.
REHYDRATE_OK = "ok"
REHYDRATE_UNKNOWN = "unknown_job"
REHYDRATE_VECTOR = "not_rerenderable"
REHYDRATE_NO_OPTIONS = "missing_bitmap_options"
REHYDRATE_NO_ORIGINAL = "missing_original_bytes"
REHYDRATE_CORRUPT_OPTIONS = "corrupt_bitmap_options"
REHYDRATE_SEGMENT_FAILED = "segmentation_failed"


def try_rehydrate(job_id: str) -> tuple[CacheEntry | None, str]:
    """Re-segment from disk when the in-memory cache lost the job.

    Looks up ``job_id`` in the library; if a record exists, it's a
    bitmap upload (``meta.rerenderable``), and ``meta.bitmap_options``
    is set, re-reads the stored original bytes and re-runs segmentation
    with the same options the operator picked at upload time. The
    resulting entry is stashed in the cache so further re-renders skip
    this rehydration.

    Returns a ``(entry, reason)`` pair: ``entry`` is ``None`` on every
    failure path and ``reason`` carries one of the ``REHYDRATE_*``
    codes above so the caller can surface a precise 404 detail.
    """
    record = get_file_record(job_id)
    if record is None:
        return None, REHYDRATE_UNKNOWN
    meta = read_meta(job_id)
    if meta is None or not meta.rerenderable:
        return None, REHYDRATE_VECTOR
    if not meta.bitmap_options:
        _log.warning(
            "Rerender rehydration: %s has rerenderable=True but no bitmap_options",
            job_id,
        )
        return None, REHYDRATE_NO_OPTIONS
    original = find_original(job_id)
    if original is None or not original.is_file():
        _log.warning("Rerender rehydration: %s has no original bytes on disk", job_id)
        return None, REHYDRATE_NO_ORIGINAL
    try:
        options = BitmapOptions.model_validate(meta.bitmap_options)
    except Exception as exc:
        _log.warning(
            "Rerender rehydration: %s has invalid bitmap_options: %s", job_id, exc
        )
        return None, REHYDRATE_CORRUPT_OPTIONS
    try:
        data = original.read_bytes()
        _result, segmentation = BitmapConverter().segment_and_render(
            data, options=meta.bitmap_options
        )
    except Exception as exc:
        _log.warning(
            "Rerender rehydration: %s segmentation failed: %s", job_id, exc
        )
        return None, REHYDRATE_SEGMENT_FAILED
    entry = CacheEntry(segmentation, options)
    remember_job(job_id, segmentation, options)
    return entry, REHYDRATE_OK


# ----------------------------------------------------------------------
# Integrity scan
# ----------------------------------------------------------------------


class IntegrityIssue(BaseModel):
    """One library entry that cannot be re-rendered today."""

    file_id: str
    source_file: str
    reason: str


class IntegrityReport(BaseModel):
    """Summary returned by ``GET /files/integrity``."""

    checked: int
    rerenderable: int
    issues: list[IntegrityIssue]


def integrity_scan() -> IntegrityReport:
    """Walk the library and flag rerenderable entries that have lost state.

    Returns the same diagnoses the rehydration path uses, so operators
    get a single place to find and resolve broken entries (banner +
    /files/integrity endpoint + boot log).
    """
    # Late import to keep persistence.py off this module's top-level
    # import graph (persistence imports the domain types we depend on).
    from pen_plotter.persistence import list_file_records  # noqa: PLC0415

    issues: list[IntegrityIssue] = []
    records = list_file_records()
    rerenderable_count = 0
    for record in records:
        meta = read_meta(record.file_id)
        if meta is None or not meta.rerenderable:
            continue
        rerenderable_count += 1
        if not meta.bitmap_options:
            issues.append(
                IntegrityIssue(
                    file_id=record.file_id,
                    source_file=record.source_file,
                    reason="missing_bitmap_options",
                )
            )
            continue
        original = find_original(record.file_id)
        if original is None or not original.is_file():
            issues.append(
                IntegrityIssue(
                    file_id=record.file_id,
                    source_file=record.source_file,
                    reason="missing_original_bytes",
                )
            )
            continue
        try:
            BitmapOptions.model_validate(meta.bitmap_options)
        except Exception:
            issues.append(
                IntegrityIssue(
                    file_id=record.file_id,
                    source_file=record.source_file,
                    reason="corrupt_bitmap_options",
                )
            )
    return IntegrityReport(
        checked=len(records), rerenderable=rerenderable_count, issues=issues
    )
