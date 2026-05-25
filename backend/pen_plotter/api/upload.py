"""File upload endpoint with MIME-based converter dispatch."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pen_plotter.api.rerender import remember_job
from pen_plotter.converters.pipeline import (
    convert_file,
    parse_options,
    read_upload_safely,
    resolve_mime,
)
from pen_plotter.models import Job
from pen_plotter.persistence import save_job

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class UploadResponse(BaseModel):
    """Result of an upload.

    Carries the created job, the normalized SVG pivot, any non-fatal
    warnings, and converter-specific metadata (e.g. ``page_count`` and the
    selected ``page`` for multi-page PDF / DOCX / HTML inputs).
    """

    job: Job
    svg: str
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    # True when /rerender can re-run a different algorithm against a cached
    # bitmap segmentation. False for vector sources (SVG, PDF).
    rerenderable: bool = False


@router.post("/upload")
async def upload(
    file: Annotated[UploadFile, File()],
    profile_name: Annotated[str, Form()],
    options: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    """Accept a file, normalize it to SVG, extract layers, and create a job.

    Raises:
        HTTPException: 400 for invalid options or input the converter rejects;
            415 if the file's MIME type has no registered converter.
    """
    mime = resolve_mime(file)
    if mime is None:
        raise HTTPException(status_code=415, detail="Could not determine file type")

    # Stream-read with a cumulative size cap so a malicious / accidental
    # giant body never gets fully buffered into RAM before the size check.
    data = await read_upload_safely(file, MAX_UPLOAD_BYTES)

    parsed_options = parse_options(options)
    converted = convert_file(data, file.filename, mime, parsed_options)

    job = Job(
        source_file=converted.source_file,
        source_mime=converted.source_mime,
        profile_name=profile_name,
        layers=converted.layers,
        status="ready",
    )
    save_job(job)
    if converted.bitmap_segmentation is not None and converted.bitmap_options is not None:
        remember_job(job.job_id, converted.bitmap_segmentation, converted.bitmap_options)
    return UploadResponse(
        job=job,
        svg=converted.svg,
        warnings=converted.warnings,
        metadata=converted.metadata,
        rerenderable=converted.bitmap_segmentation is not None,
    )
