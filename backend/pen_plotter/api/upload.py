"""File upload endpoint with MIME-based converter dispatch."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from typing import Annotated

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


@router.post("/upload")
async def upload(
    file: Annotated[UploadFile, File()],
    profile_name: Annotated[str, Form()],
) -> Job:
    """Accept a file, dispatch it to its converter, and create a job.

    Args:
        file: The uploaded source file.
        profile_name: Name of the machine profile this job targets.

    Returns:
        A :class:`Job` describing the accepted upload after normalization.

    Raises:
        HTTPException: 415 if the file's MIME type has no registered converter.
    """
    mime = _resolve_mime(file)
    if mime is None:
        raise HTTPException(status_code=415, detail="Could not determine file type")

    try:
        converter = registry.for_mime(mime)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    data = await file.read()
    converter.convert(data)

    source_file = PurePosixPath(file.filename).name if file.filename else "upload"
    return Job(
        source_file=source_file,
        source_mime=mime,
        profile_name=profile_name,
        status="ready",
    )
