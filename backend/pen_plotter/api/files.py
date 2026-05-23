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
from pen_plotter.converters.pipeline import convert_file, parse_options, resolve_mime
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


class FileDetail(FileRecordOut):
    """Library entry plus its converted SVG and per-file metadata."""

    svg: str
    layers: list[LayerInfo]
    warnings: list[str] = []
    upload_metadata: dict[str, Any] = {}


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
    )


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
    """
    mime = resolve_mime(file)
    if mime is None:
        raise HTTPException(status_code=415, detail="Could not determine file type")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
        )

    digest = hashlib.sha256(data).hexdigest()
    existing = get_file_record_by_hash(digest)
    if existing is not None:
        return FileUploadResponse(file=_record_to_detail(existing), existing=True)

    parsed_options = parse_options(options)
    converted = convert_file(data, file.filename, mime, parsed_options)

    file_id = str(uuid.uuid4())
    directory = _file_dir(file_id)
    directory.mkdir(parents=True, exist_ok=True)
    _svg_path(file_id).write_text(converted.svg, encoding="utf-8")
    original = directory / f"original{_ext_for(file.filename, converted.source_mime)}"
    original.write_bytes(data)
    meta = FileMeta(
        layers=converted.layers,
        warnings=converted.warnings,
        upload_metadata=converted.metadata,
    )
    _meta_path(file_id).write_text(meta.model_dump_json(), encoding="utf-8")

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
