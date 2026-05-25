"""HTTP adapter for the file library — upload, list, fetch, dedup, integrity.

All disk layout, persistence, segmentation cache and integrity logic
live in :mod:`pen_plotter.application.file_library`. This module owns
only the HTTP wire shape and the upload orchestration.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pen_plotter.application.file_library import (
    FileMeta,
    IntegrityReport,
    file_dir,
    find_original,
    forget_job,
    integrity_scan,
    read_meta,
    read_meta_or_empty,
    read_svg,
    remember_job,
)
from pen_plotter.converters.pipeline import (
    convert_file,
    parse_options,
    read_upload_safely,
    resolve_mime,
)
from pen_plotter.persistence import (
    FileRecord,
    delete_file_record,
    get_file_record,
    get_file_record_by_hash,
    list_file_folders,
    list_file_records,
    save_file_record,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Folder is a free-form label stored in the FileRecord row, never
# joined onto a filesystem path on disk (the file_id — a UUID — is the
# only path component). The guard below still rejects shapes that
# could be misread by an admin tool, a CLI export, or a future
# refactor that does build a path from this string — defence in depth
# at the API edge.
_FORBIDDEN_FOLDER_CHARS = ("/", "\\", "\x00")
_MAX_FOLDER_LEN = 128


def _sanitize_folder(folder: str) -> str:
    """Validate the operator-supplied folder label.

    Strips surrounding whitespace, rejects path separators / NULs /
    parent-directory traversal hints, and caps the length so a single
    pathological folder name can't blow up the search index.

    Raises:
        HTTPException: 400 if the label is unsafe. The error message
            tells the operator what was wrong so they can correct it.
    """
    folder = folder.strip()
    if not folder:
        return ""
    if len(folder) > _MAX_FOLDER_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Folder name must be at most {_MAX_FOLDER_LEN} characters.",
        )
    if any(c in folder for c in _FORBIDDEN_FOLDER_CHARS):
        raise HTTPException(
            status_code=400,
            detail="Folder name cannot contain slashes, backslashes or NUL.",
        )
    if folder in {".", ".."} or folder.startswith(".."):
        raise HTTPException(
            status_code=400,
            detail="Folder name cannot be '.' or '..' or start with '..'.",
        )
    return folder

# Test compatibility: ``FILES_DIR`` is the conventional monkey-patch
# point used by tests to redirect the library to a temp dir. The
# application service reads this attribute at call time (see
# ``file_library.files_dir``) so the override flows through.
_DEFAULT_FILES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "files"
FILES_DIR = Path(os.environ.get("OMNIPLOT_FILES_DIR", _DEFAULT_FILES_DIR))

# Backwards-compatible aliases. The tests and any external callers that
# imported these private helpers from this module keep working; new
# code should import them from ``application.file_library`` directly.
_file_dir = file_dir
_meta_path = lambda file_id: file_dir(file_id) / "meta.json"  # noqa: E731
_svg_path = lambda file_id: file_dir(file_id) / "normalized.svg"  # noqa: E731
_find_original = find_original


class FileRecordOut(BaseModel):
    """Public projection of a :class:`FileRecord`, ready for JSON."""

    file_id: str
    sha256: str
    source_file: str
    source_mime: str
    size_bytes: int
    layer_count: int
    folder: str
    created_at: datetime


class FileDetail(FileRecordOut):
    """Library entry plus its converted SVG and per-file metadata."""

    svg: str
    layers: list[Any]  # LayerInfo; widened to Any to avoid a cycle through models
    warnings: list[str] = []
    upload_metadata: dict[str, Any] = {}
    rerenderable: bool = False


class FileUploadResponse(BaseModel):
    """Result of uploading to the library; ``existing`` flags dedup hits."""

    file: FileDetail
    existing: bool


class FilePatch(BaseModel):
    """In-place edit of a library entry — rename and/or move between folders."""

    source_file: str | None = None
    folder: str | None = None


def _record_to_out(record: FileRecord) -> FileRecordOut:
    return FileRecordOut(
        file_id=record.file_id,
        sha256=record.sha256,
        source_file=record.source_file,
        source_mime=record.source_mime,
        size_bytes=record.size_bytes,
        layer_count=record.layer_count,
        folder=record.folder,
        created_at=record.created_at,
    )


def _record_to_detail(record: FileRecord) -> FileDetail:
    meta = read_meta_or_empty(record.file_id)
    svg = read_svg(record.file_id)
    if svg is None:
        raise HTTPException(status_code=410, detail="Stored SVG is missing on disk")
    return FileDetail(
        **_record_to_out(record).model_dump(),
        svg=svg,
        layers=meta.layers,
        warnings=meta.warnings,
        upload_metadata=meta.upload_metadata,
        rerenderable=meta.rerenderable,
    )


def _options_changed(file_id: str, new_options: dict[str, Any]) -> bool:
    """Detect a real settings edit between two upload requests.

    Returns ``True`` when ``new_options`` differs from what was used
    to produce the stored file. Empty / missing ``new_options`` is
    treated as "no change" — a plain library-pick re-upload that
    just wants the existing entry, not a settings edit.
    """
    if not new_options:
        return False
    meta = read_meta_or_empty(file_id)
    # Bitmap path: stored as BitmapOptions, normalize both sides so a
    # request that omits an implicit default doesn't trigger a false
    # re-conversion.
    stored_bitmap = meta.bitmap_options
    if stored_bitmap is not None:
        try:
            from pen_plotter.converters.bitmap import BitmapOptions

            a = BitmapOptions.model_validate(stored_bitmap).model_dump()
            b = BitmapOptions.model_validate({**stored_bitmap, **new_options}).model_dump()
            return a != b
        except Exception:
            # Fall through to the raw-dict compare so non-bitmap
            # converters still detect their settings edits.
            pass
    # Non-bitmap converters (typography / markdown / svg / …): compare
    # against the raw options dict that produced the file.
    stored = meta.source_options or {}
    return {**stored, **new_options} != stored


def _reprocess_existing(
    record: FileRecord,
    data: bytes,
    mime: str,
    new_options: dict[str, Any],
) -> FileRecord:
    """Re-convert and overwrite the stored artefacts for an existing entry.

    Keeps ``file_id`` and the SHA-256 stable so library references / the
    /rerender cache key don't break; the operator's settings edit is
    visible on the next /files/<id> read. Also refreshes the rerender
    cache so the next /rerender skips the rehydration step.
    """
    converted = convert_file(data, record.source_file, mime, new_options)
    directory = file_dir(record.file_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "normalized.svg").write_text(converted.svg, encoding="utf-8")
    # Refresh the on-disk original too — extension may differ if the
    # operator re-uploaded the same content under a different filename.
    original_target = directory / f"original{_ext_for(record.source_file, converted.source_mime)}"
    for stale in directory.iterdir():
        if stale.is_file() and stale.stem == "original" and stale != original_target:
            stale.unlink(missing_ok=True)
    original_target.write_bytes(data)
    meta = FileMeta(
        layers=converted.layers,
        warnings=converted.warnings,
        upload_metadata=converted.metadata,
        rerenderable=converted.bitmap_segmentation is not None,
        bitmap_options=(
            converted.bitmap_options.model_dump()
            if converted.bitmap_options is not None
            else None
        ),
        source_options=dict(new_options) if new_options else None,
    )
    (directory / "meta.json").write_text(meta.model_dump_json(), encoding="utf-8")

    # Update DB row: layer_count and source_mime may have shifted; keep
    # file_id, sha256, folder, created_at.
    updated = FileRecord(
        file_id=record.file_id,
        sha256=record.sha256,
        source_file=record.source_file,
        source_mime=converted.source_mime,
        size_bytes=len(data),
        layer_count=len(converted.layers),
        folder=record.folder,
        created_at=record.created_at,
    )
    save_file_record(updated)

    # Refresh the /rerender cache so the segmentation matches the new
    # SVG. Dropping the old entry first avoids a stale palette + new
    # algorithm mismatch on the next request.
    forget_job(record.file_id)
    if converted.bitmap_segmentation is not None and converted.bitmap_options is not None:
        remember_job(record.file_id, converted.bitmap_segmentation, converted.bitmap_options)
    return updated


def _ext_for(filename: str | None, mime: str) -> str:
    """Pick a sensible extension for the stored original."""
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    # Best-effort fallback by MIME.
    return {
        "image/svg+xml": ".svg",
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/html": ".html",
        "text/markdown": ".md",
        "text/plain": ".txt",
        "application/postscript": ".ps",
        "image/x-eps": ".eps",
        "image/vnd.dxf": ".dxf",
    }.get(mime, ".bin")


@router.post("/files")
async def upload_to_library(
    file: Annotated[UploadFile, File()],
    folder: Annotated[str, Form()] = "",
    options: Annotated[str | None, Form()] = None,
) -> FileUploadResponse:
    """Add a file to the library, deduplicating by content hash.

    If a file with the same SHA-256 already exists, the existing record is
    returned and ``existing`` is ``true`` — no second copy is stored.
    Exception: when the request carries conversion ``options`` (e.g. the
    operator changed the bitmap algorithm or palette in SourceSection and
    clicked Apply), and those options differ from what was used last time,
    we re-process the file in place — overwriting ``normalized.svg`` and
    ``meta.json`` — instead of silently returning the stale conversion.
    Without this branch the operator's option edits would never reach the
    plotter, because the editor re-uploads the same bytes to apply changes.
    """
    mime = resolve_mime(file)
    if mime is None:
        raise HTTPException(status_code=415, detail="Could not determine file type")

    folder = _sanitize_folder(folder)
    data = await read_upload_safely(file, MAX_UPLOAD_BYTES)
    parsed_options = parse_options(options)

    digest = hashlib.sha256(data).hexdigest()
    existing = get_file_record_by_hash(digest)
    if existing is not None:
        if _options_changed(existing.file_id, parsed_options):
            updated = _reprocess_existing(existing, data, mime, parsed_options)
            return FileUploadResponse(file=_record_to_detail(updated), existing=True)
        return FileUploadResponse(file=_record_to_detail(existing), existing=True)

    converted = convert_file(data, file.filename, mime, parsed_options)

    file_id = str(uuid.uuid4())
    # Write all artefacts into a staging directory and only rename it to
    # its final name once every file is on disk. Guarantees an interrupted
    # upload can never leave the library half-populated.
    final_dir = file_dir(file_id)
    staging = final_dir.with_name(f".tmp-{file_id}")
    try:
        staging.mkdir(parents=True, exist_ok=False)
        (staging / "normalized.svg").write_text(converted.svg, encoding="utf-8")
        original = staging / f"original{_ext_for(file.filename, converted.source_mime)}"
        original.write_bytes(data)
        meta = FileMeta(
            layers=converted.layers,
            warnings=converted.warnings,
            upload_metadata=converted.metadata,
            rerenderable=converted.bitmap_segmentation is not None,
            bitmap_options=(
                converted.bitmap_options.model_dump()
                if converted.bitmap_options is not None
                else None
            ),
            source_options=dict(parsed_options) if parsed_options else None,
        )
        (staging / "meta.json").write_text(meta.model_dump_json(), encoding="utf-8")
        staging.rename(final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    record = FileRecord(
        file_id=file_id,
        sha256=digest,
        source_file=converted.source_file,
        source_mime=converted.source_mime,
        size_bytes=len(data),
        layer_count=len(converted.layers),
        folder=folder,
        created_at=datetime.now(UTC),
    )
    save_file_record(record)

    if converted.bitmap_segmentation is not None and converted.bitmap_options is not None:
        # Cache under the file_id so /rerender can find the segmentation
        # when the UI later derives a job_id from this library file.
        remember_job(file_id, converted.bitmap_segmentation, converted.bitmap_options)

    return FileUploadResponse(file=_record_to_detail(record), existing=False)


@router.get("/files/integrity")
async def files_integrity() -> IntegrityReport:
    """Return the integrity report for the file library.

    Lets the UI surface a banner ("3 file(s) need re-upload to support
    style editing") instead of failing on the next /rerender click.
    """
    return integrity_scan()


@router.get("/files")
async def list_files(
    folder: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str = Query(default="date"),
    order: str = Query(default="desc"),
) -> list[FileRecordOut]:
    """List library entries. Filters/sort applied server-side."""
    if sort not in {"name", "date", "type"}:
        raise HTTPException(status_code=400, detail="sort must be one of name|date|type")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="order must be asc|desc")
    records = list_file_records(folder=folder, search=search, sort=sort, order=order)
    return [_record_to_out(r) for r in records]


@router.get("/files/folders")
async def list_folders() -> list[str]:
    """Return the distinct folder names currently used by library entries."""
    return list_file_folders()


@router.get("/files/{file_id}")
async def get_file(file_id: str) -> FileDetail:
    """Return one library entry, including its SVG and layer metadata."""
    record = get_file_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown file: {file_id!r}")
    return _record_to_detail(record)


@router.get("/files/{file_id}/original")
async def download_original(file_id: str) -> FileResponse:
    """Stream the original uploaded bytes back to the client."""
    record = get_file_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown file: {file_id!r}")
    original = find_original(file_id)
    if original is None:
        raise HTTPException(status_code=410, detail="Original file is missing on disk")
    return FileResponse(
        path=original,
        media_type=record.source_mime,
        filename=record.source_file,
    )


@router.patch("/files/{file_id}")
async def patch_file(file_id: str, patch: FilePatch) -> FileRecordOut:
    """Rename a library entry and/or move it to another folder."""
    record = get_file_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown file: {file_id!r}")
    if patch.source_file is not None:
        name = patch.source_file.strip()
        if not name:
            raise HTTPException(status_code=400, detail="source_file cannot be empty")
        record.source_file = name
    if patch.folder is not None:
        record.folder = _sanitize_folder(patch.folder)
    save_file_record(record)
    return _record_to_out(record)


@router.delete("/files/{file_id}")
async def delete_file(file_id: str) -> dict[str, bool]:
    """Remove a library entry and its on-disk artifacts."""
    if not delete_file_record(file_id):
        raise HTTPException(status_code=404, detail=f"Unknown file: {file_id!r}")
    directory = file_dir(file_id)
    if directory.is_dir():
        shutil.rmtree(directory, ignore_errors=True)
    return {"ok": True}


__all__ = [
    "FILES_DIR",
    "FileDetail",
    "FileMeta",
    "FilePatch",
    "FileRecordOut",
    "FileUploadResponse",
    "IntegrityReport",
    "MAX_UPLOAD_BYTES",
    "find_original",
    "read_meta",
    "router",
]
