"""File upload endpoint with MIME-based converter dispatch."""

from __future__ import annotations

import json
import mimetypes
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pen_plotter.converters.base import UnsupportedFormatError
from pen_plotter.converters.registry import registry
from pen_plotter.core.layers import extract_layers
from pen_plotter.core.sanitize import sanitize_svg
from pen_plotter.models import Job
from pen_plotter.persistence import save_job

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class UploadResponse(BaseModel):
    """Result of an upload: the created job, the normalized SVG pivot, any
    non-fatal warnings, and converter-specific metadata (e.g. ``page_count``
    and the selected ``page`` for multi-page PDF / DOCX / HTML inputs)."""

    job: Job
    svg: str
    warnings: list[str] = []
    metadata: dict[str, Any] = {}


def _resolve_mime(upload: UploadFile) -> str | None:
    """Best-effort MIME detection from the client header or filename.

    Args:
        upload: The uploaded file.

    Returns:
        The resolved MIME type, or ``None`` if it cannot be determined.
    """
    content_type = upload.content_type
    if content_type and content_type != "application/octet-stream":
        return content_type
    if upload.filename:
        guessed, _ = mimetypes.guess_type(upload.filename)
        return guessed
    return None


def _parse_options(raw: str | None) -> dict[str, Any]:
    """Parse the optional JSON ``options`` form field into a dict.

    Args:
        raw: The raw JSON string, or ``None`` if omitted.

    Returns:
        The parsed options mapping, or an empty dict if omitted.

    Raises:
        HTTPException: 400 if the value is not a JSON object.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="options must be a JSON object")
    return parsed


@router.post("/upload")
async def upload(
    file: Annotated[UploadFile, File()],
    profile_name: Annotated[str, Form()],
    options: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    """Accept a file, normalize it to SVG, extract layers, and create a job.

    Args:
        file: The uploaded source file.
        profile_name: Name of the machine profile this job targets.
        options: Optional JSON object of converter-specific parameters.

    Returns:
        An :class:`UploadResponse` with the created job (layers populated) and
        the normalized SVG pivot.

    Raises:
        HTTPException: 400 for invalid options or input the converter rejects;
            415 if the file's MIME type has no registered converter.
    """
    mime = _resolve_mime(file)
    if mime is None:
        raise HTTPException(status_code=415, detail="Could not determine file type")

    try:
        converter = registry.for_mime(mime)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    parsed_options = _parse_options(options)
    parsed_options.setdefault("source_mime", mime)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
        )
    try:
        result = converter.convert(data, options=parsed_options)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # converter/subprocess/library failures
        raise HTTPException(status_code=422, detail=f"Could not convert file: {exc}") from exc

    svg = sanitize_svg(result.svg)
    source_file = PurePosixPath(file.filename).name if file.filename else "upload"
    job = Job(
        source_file=source_file,
        source_mime=mime,
        profile_name=profile_name,
        layers=extract_layers(svg),
        status="ready",
    )
    save_job(job)
    return UploadResponse(
        job=job,
        svg=svg,
        warnings=list(result.warnings),
        metadata=dict(result.metadata),
    )
