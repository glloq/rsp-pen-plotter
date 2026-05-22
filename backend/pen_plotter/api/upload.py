"""File upload endpoint with MIME-based converter dispatch."""

from __future__ import annotations

import json
import mimetypes
from pathlib import PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from pen_plotter.converters.base import UnsupportedFormatError
from pen_plotter.converters.registry import registry
from pen_plotter.models import Job

router = APIRouter()


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
) -> Job:
    """Accept a file, dispatch it to its converter, and create a job.

    Args:
        file: The uploaded source file.
        profile_name: Name of the machine profile this job targets.
        options: Optional JSON object of converter-specific parameters.

    Returns:
        A :class:`Job` describing the accepted upload after normalization.

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
    data = await file.read()
    try:
        converter.convert(data, options=parsed_options)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_file = PurePosixPath(file.filename).name if file.filename else "upload"
    return Job(
        source_file=source_file,
        source_mime=mime,
        profile_name=profile_name,
        status="ready",
    )
