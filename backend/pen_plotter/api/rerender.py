"""Re-render selected bitmap layers with new per-layer algorithms.

The full ``/upload`` flow runs k-means + per-cluster rendering, which can
take a few seconds on a Pi. When the operator changes the algorithm for
a single layer in the UI, we don't want to re-segment — only re-render.
This module caches the segmentation result (labels + palette) of each
bitmap job by ``job_id`` so a second pass only pays for the rendering.

The in-memory cache is bounded (LRU) and lost on backend restart, but
when a cache miss happens we look the file up in the library, re-load
the original bytes from disk, and re-segment using the BitmapOptions
persisted in ``meta.json``. The result is then cached so subsequent
re-renders are fast. This makes ``/rerender`` effectively persistent
across restarts without paying the segmentation cost on every request.

The capacity defaults to 64 (room for several placements being edited
in a session) and is configurable via the ``RERENDER_CACHE_SIZE`` env
var.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions, SegmentationResult
from pen_plotter.core.sanitize import sanitize_svg

_log = logging.getLogger(__name__)

router = APIRouter()


def _load_cache_size() -> int:
    """Read the LRU cap from env, clamped to a sane range."""
    raw = os.environ.get("RERENDER_CACHE_SIZE", "64")
    try:
        size = int(raw)
    except ValueError:
        size = 64
    return max(4, min(256, size))


_CACHE_SIZE = _load_cache_size()


class _CacheEntry:
    """One cached bitmap job: its segmentation + the original options."""

    __slots__ = ("segmentation", "options")

    def __init__(self, segmentation: SegmentationResult, options: BitmapOptions) -> None:
        self.segmentation = segmentation
        self.options = options


_CACHE: OrderedDict[str, _CacheEntry] = OrderedDict()


def remember_job(job_id: str, segmentation: SegmentationResult, options: BitmapOptions) -> None:
    """Stash a bitmap job's segmentation result for later ``/rerender`` calls."""
    _CACHE[job_id] = _CacheEntry(segmentation, options)
    _CACHE.move_to_end(job_id)
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)


def forget_job(job_id: str) -> None:
    """Drop a cached job (e.g. when ``/upload`` replaces it)."""
    _CACHE.pop(job_id, None)


def _clear_cache_for_tests() -> None:
    """Test-only hook so the cache doesn't leak between cases."""
    _CACHE.clear()


# Rehydration outcomes. The endpoint exposes the failure reason as a
# machine-readable ``detail.reason`` so the UI can pick a precise prompt
# ("re-upload this file") instead of a generic 404 toast.
REHYDRATE_OK = "ok"
REHYDRATE_UNKNOWN = "unknown_job"
REHYDRATE_VECTOR = "not_rerenderable"
REHYDRATE_NO_OPTIONS = "missing_bitmap_options"
REHYDRATE_NO_ORIGINAL = "missing_original_bytes"
REHYDRATE_CORRUPT_OPTIONS = "corrupt_bitmap_options"
REHYDRATE_SEGMENT_FAILED = "segmentation_failed"


def _try_rehydrate(job_id: str) -> tuple[_CacheEntry | None, str]:
    """Re-segment from disk when the in-memory cache lost the job.

    Looks up ``job_id`` in the library; if a record exists, it's a bitmap
    upload (``meta.rerenderable``), and ``meta.bitmap_options`` is set,
    re-reads the stored original bytes and re-runs segmentation with the
    same options the operator picked at upload time. The resulting entry
    is stashed in ``_CACHE`` so further re-renders skip this rehydration.

    Returns a ``(entry, reason)`` pair: ``entry`` is ``None`` on every
    failure path and ``reason`` carries one of the ``REHYDRATE_*`` codes
    above so the caller can surface a precise 404 detail.
    """
    # Imported lazily to avoid a top-level circular import between
    # rerender.py and files.py (files.py imports remember_job).
    from pen_plotter.api.files import find_original, read_meta
    from pen_plotter.persistence import get_file_record

    record = get_file_record(job_id)
    if record is None:
        return None, REHYDRATE_UNKNOWN
    meta = read_meta(job_id)
    if meta is None or not meta.rerenderable:
        return None, REHYDRATE_VECTOR
    if not meta.bitmap_options:
        # Legacy file uploaded before bitmap_options was persisted, or
        # meta.json edited / corrupted. Operator must re-upload to
        # restore the rerender capability.
        _log.warning(
            "Rerender rehydration: %s has rerenderable=True but no bitmap_options", job_id
        )
        return None, REHYDRATE_NO_OPTIONS
    original = find_original(job_id)
    if original is None or not original.is_file():
        _log.warning("Rerender rehydration: %s has no original bytes on disk", job_id)
        return None, REHYDRATE_NO_ORIGINAL
    try:
        options = BitmapOptions.model_validate(meta.bitmap_options)
    except Exception as exc:
        _log.warning("Rerender rehydration: %s has invalid bitmap_options: %s", job_id, exc)
        return None, REHYDRATE_CORRUPT_OPTIONS
    try:
        data = original.read_bytes()
        _result, segmentation = BitmapConverter().segment_and_render(
            data, options=meta.bitmap_options
        )
    except Exception as exc:
        _log.warning("Rerender rehydration: %s segmentation failed: %s", job_id, exc)
        return None, REHYDRATE_SEGMENT_FAILED
    entry = _CacheEntry(segmentation, options)
    _CACHE[job_id] = entry
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return entry, REHYDRATE_OK


class LayerPass(BaseModel):
    """One rendering pass within a multi-pass layer override.

    A single colour can be drawn with several stacked algorithms — e.g.
    ``contours`` for the outline followed by ``crosshatch`` for the fill
    — so the operator gets the visual effect of multiple inks while
    keeping the layer on one physical pen.
    """

    algorithm: str
    algorithm_options: dict[str, Any] = Field(default_factory=dict)


class LayerAlgorithm(BaseModel):
    """A per-layer algorithm override applied on top of the cached defaults.

    Backwards compatible: callers can still pass a single ``algorithm`` /
    ``algorithm_options`` pair (the legacy shape). When ``passes`` is set
    and non-empty, it overrides the single-algorithm fields and the layer
    is rendered as the stack of passes in order.
    """

    layer_id: str
    algorithm: str = ""
    algorithm_options: dict[str, Any] = Field(default_factory=dict)
    passes: list[LayerPass] = Field(default_factory=list)


class RerenderRequest(BaseModel):
    """Request body for ``POST /rerender``."""

    job_id: str
    layers: list[LayerAlgorithm] = Field(default_factory=list)


class RerenderResponse(BaseModel):
    """The freshly rendered SVG plus any non-fatal warnings."""

    svg: str
    warnings: list[str] = Field(default_factory=list)


@router.post("/rerender", response_model=RerenderResponse)
async def rerender(request: RerenderRequest) -> RerenderResponse:
    """Re-render the cached bitmap job with optional per-layer algorithm overrides.

    Args:
        request: The job id and per-layer algorithm choices.

    Returns:
        The freshly rendered SVG (sanitized) plus rendering warnings.

    Raises:
        HTTPException: 404 if no segmentation cache exists for the job
            (e.g. after a backend restart or LRU eviction); the UI then
            re-uploads instead.
    """
    entry = _CACHE.get(request.job_id)
    if entry is None:
        entry, reason = _try_rehydrate(request.job_id)
        if entry is None:
            # Structured detail mirrors the L8 missing-pen-slots shape so
            # the UI can branch on ``reason`` to pick a precise prompt
            # (re-upload vs unsupported file type vs ...).
            raise HTTPException(
                status_code=404,
                detail={
                    "reason": reason,
                    "job_id": request.job_id,
                    "message": (
                        f"No cached segmentation for job {request.job_id!r}; "
                        "re-upload to refresh."
                    ),
                },
            )
    # Refresh LRU position so frequently-tweaked jobs stay hot.
    _CACHE.move_to_end(request.job_id)

    overrides: dict[str, dict[str, Any]] = {}
    for item in request.layers:
        spec: dict[str, Any] = {}
        if item.passes:
            spec["passes"] = [
                {"algorithm": p.algorithm, "algorithm_options": p.algorithm_options}
                for p in item.passes
            ]
        if item.algorithm:
            spec["algorithm"] = item.algorithm
            spec["algorithm_options"] = item.algorithm_options
        if spec:
            overrides[item.layer_id] = spec
    try:
        svg, warnings = BitmapConverter.render_from_segmentation(
            entry.segmentation, entry.options, per_layer_overrides=overrides
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — algorithm/runtime failures
        raise HTTPException(status_code=422, detail=f"Re-render failed: {exc}") from exc

    return RerenderResponse(svg=sanitize_svg(svg), warnings=warnings)
