"""Live typography preview endpoint.

Mirrors ``/preview`` for ``.txt`` / ``.md`` sources: takes the operator's
current TypographyDraft and returns a Hershey-rendered SVG so the editor
can show the actual final font / size / layout without a full ``/upload``
round-trip.

Kept thin (no caching, no concurrency limit) because Hershey rendering is
pure-Python and cheap — a full page of text renders in low single-digit
milliseconds, well below the network round-trip cost.
"""

from __future__ import annotations

import json
import mimetypes
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from pen_plotter.converters.markdown import _blocks_from_markdown
from pen_plotter.typography import HersheyRenderer, TypographyOptions

router = APIRouter()

MAX_PREVIEW_TEXT_BYTES = 256 * 1024
_ACCEPTED_MIMES = frozenset({"text/plain", "text/markdown"})


class TypographyPreviewResponse(BaseModel):
    """Hershey-rendered SVG plus the truncation flag the UI surfaces."""

    svg: str
    truncated: bool = False


def _resolve_mime(upload: UploadFile) -> str | None:
    """Mirror the ``/preview`` MIME detection: header → filename guess."""
    content_type = upload.content_type
    if content_type and content_type != "application/octet-stream":
        return content_type
    if upload.filename:
        guessed, _ = mimetypes.guess_type(upload.filename)
        return guessed
    return None


@router.post("/preview-text", response_model=TypographyPreviewResponse)
async def preview_text(
    file: Annotated[UploadFile, File()],
    options: Annotated[str | None, Form()] = None,
) -> TypographyPreviewResponse:
    """Render a typography draft to single-stroke Hershey SVG.

    Args:
        file: Uploaded ``.txt`` or ``.md`` source. Truncated to
            ``MAX_PREVIEW_TEXT_BYTES`` so a runaway paste never pins the
            event loop; the response flags whether truncation happened so
            the UI can warn.
        options: Optional JSON object mirroring
            :class:`~pen_plotter.typography.TypographyOptions`.

    Returns:
        A :class:`TypographyPreviewResponse` carrying the SVG ready for
        the EditPreviewPane.

    Raises:
        HTTPException: 415 if the MIME isn't text/markdown; 400 if the
            options can't be parsed or the font name is unknown; 413 if
            the upload is empty.
    """
    mime = _resolve_mime(file)
    if mime is None or mime not in _ACCEPTED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Typography preview only supports text/markdown; got {mime!r}.",
        )

    raw = await file.read(MAX_PREVIEW_TEXT_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded text is empty")
    truncated = len(raw) > MAX_PREVIEW_TEXT_BYTES
    if truncated:
        raw = raw[:MAX_PREVIEW_TEXT_BYTES]

    parsed_opts: dict[str, Any] = {}
    if options:
        try:
            parsed = json.loads(options)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="options must be a JSON object")
        parsed_opts = parsed

    try:
        opts = TypographyOptions.model_validate(parsed_opts)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc

    try:
        renderer = HersheyRenderer(opts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    text = raw.decode("utf-8", errors="replace")
    if mime == "text/markdown":
        blocks = _blocks_from_markdown(text, opts.font_size_mm)
        svg = renderer.render_blocks(blocks)
    else:
        svg = renderer.render_text(text)
    return TypographyPreviewResponse(svg=svg, truncated=truncated)
