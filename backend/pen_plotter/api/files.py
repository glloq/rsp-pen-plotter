"""File library endpoints — durable, dedup-by-hash storage of uploaded sources.

The library is the canonical place uploaded files live: one row per unique
SHA-256, normalized SVG on disk, foldering / search / sort handled by the
backend so the UI stays thin. Re-uploading the same content returns the
existing record instead of creating a duplicate entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pen_plotter.api.rerender import remember_job
from pen_plotter.converters.pipeline import (
    convert_file,
    parse_options,
    read_upload_safely,
    resolve_mime,
)
from pen_plotter.models import LayerInfo
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

_DEFAULT_FILES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "files"
FILES_DIR = Path(os.environ.get("OMNIPLOT_FILES_DIR", _DEFAULT_FILES_DIR))


def _file_dir(file_id: str) -> Path:
    return FILES_DIR / file_id


def _meta_path(file_id: str) -> Path:
    return _file_dir(file_id) / "meta.json"


def _svg_path(file_id: str) -> Path:
    return _file_dir(file_id) / "normalized.svg"


def _find_original(file_id: str) -> Path | None:
    """Return the stored original file for ``file_id`` if present."""
    directory = _file_dir(file_id)
    if not directory.is_dir():
        return None
    for child in directory.iterdir():
        if child.is_file() and child.stem == "original":
            return child
    return None


def find_original(file_id: str) -> Path | None:
    """Public accessor for the stored original file path, if present."""
    return _find_original(file_id)


def read_meta(file_id: str) -> "FileMeta | None":
    """Return the parsed meta.json for ``file_id``, or ``None`` if absent."""
    path = _meta_path(file_id)
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return FileMeta.model_validate(raw)


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


class FileMeta(BaseModel):
    """Full metadata persisted alongside the SVG (warnings, layers, etc.)."""

    layers: list[LayerInfo]
    warnings: list[str] = []
    upload_metadata: dict[str, Any] = {}
    # True when the upload pipeline produced a bitmap segmentation cache,
    # so /rerender can re-run a different algorithm against the same colour
    # clusters. False for vector sources (SVG, PDF) where the geometry is
    # used as-is and the algorithm picker has no effect.
    rerenderable: bool = False
    # BitmapOptions (as a dict) used at the original segmentation. Kept on
    # disk so the /rerender cache can be rehydrated after a backend restart
    # without re-uploading — re-segmenting the stored ``original.<ext>``
    # bytes with these exact options reproduces the same labels + palette.
    bitmap_options: dict[str, Any] | None = None


class FileDetail(FileRecordOut):
    """Library entry plus its converted SVG and per-file metadata."""

    svg: str
    layers: list[LayerInfo]
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


def _read_meta(file_id: str) -> FileMeta:
    path = _meta_path(file_id)
    if not path.is_file():
        return FileMeta(layers=[])
    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    return FileMeta.model_validate(raw)


def _read_svg(file_id: str) -> str:
    path = _svg_path(file_id)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Stored SVG is missing on disk")
    return path.read_text(encoding="utf-8")


def _record_to_detail(record: FileRecord) -> FileDetail:
    meta = _read_meta(record.file_id)
    return FileDetail(
        **_record_to_out(record).model_dump(),
        svg=_read_svg(record.file_id),
        layers=meta.layers,
        warnings=meta.warnings,
        upload_metadata=meta.upload_metadata,
        rerenderable=meta.rerenderable,
    )


def _options_changed(file_id: str, new_options: dict[str, Any]) -> bool:
    """True when the operator's new conversion options differ from those
    that produced the stored file. Empty / missing ``new_options`` is
    treated as "no change" — a plain library-pick re-upload that just
    wants the existing entry, not a settings edit.
    """
    if not new_options:
        return False
    meta = _read_meta(file_id)
    stored = meta.bitmap_options or {}
    # Use BitmapOptions to normalize both sides (drops keys the model
    # doesn't know about, fills defaults). This way a request that only
    # sets ``algorithm`` is compared against the same fully-populated
    # object as the stored one — no false positives on missing-key vs
    # default-value.
    try:
        from pen_plotter.converters.bitmap import BitmapOptions

        a = BitmapOptions.model_validate(stored).model_dump()
        b = BitmapOptions.model_validate({**stored, **new_options}).model_dump()
        return a != b
    except Exception:
        # Non-bitmap source (no BitmapOptions): fall back to raw dict
        # compare. Any new key or changed value re-processes.
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
    from pen_plotter.api.rerender import forget_job, remember_job

    converted = convert_file(data, record.source_file, mime, new_options)
    directory = _file_dir(record.file_id)
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
    # upload can never leave the library half-populated — a crash mid-write
    # surfaces as a leftover ``.tmp-*`` dir that startup or the next upload
    # can sweep, not as an orphan record pointing at missing SVG / meta.
    final_dir = _file_dir(file_id)
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
        )
        (staging / "meta.json").write_text(meta.model_dump_json(), encoding="utf-8")
        # Atomic on POSIX: rename within the same directory is one syscall,
        # so either the final path exists with every file or it doesn't
        # exist at all.
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
    original = _find_original(file_id)
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
        record.folder = patch.folder.strip()
    save_file_record(record)
    return _record_to_out(record)


@router.delete("/files/{file_id}")
async def delete_file(file_id: str) -> dict[str, bool]:
    """Remove a library entry and its on-disk artifacts."""
    if not delete_file_record(file_id):
        raise HTTPException(status_code=404, detail=f"Unknown file: {file_id!r}")
    directory = _file_dir(file_id)
    if directory.is_dir():
        shutil.rmtree(directory, ignore_errors=True)
    return {"ok": True}
