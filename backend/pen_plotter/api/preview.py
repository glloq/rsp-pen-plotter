"""Fast bitmap preview endpoint.

Live-tunable parameters in the UI (algorithm, num_colors, drop_background, …)
benefit from sub-second feedback. The regular ``/upload`` path runs k-means
with 10 initialisations on a ~800px-wide image — that is overkill for a
preview while the user is still picking parameters. ``/preview`` runs the
same :class:`BitmapConverter` in ``fast=True`` mode (128px max, ``n_init=1``)
and skips DB persistence entirely.

Concurrency is limited so a slider drag does not pin every CPU; an in-memory
LRU caches successful results by file hash + options so an identical request
returns immediately. The DOS knob is the request size limit, same as upload.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import time
from collections import OrderedDict
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from pen_plotter.converters.bitmap import BitmapConverter

router = APIRouter()

MAX_PREVIEW_BYTES = 20 * 1024 * 1024
_ACCEPTED_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/webp",
        "image/heic",
        "image/heif",
    }
)
_CACHE_SIZE = 16
_cache: OrderedDict[str, "PreviewResponse"] = OrderedDict()
# A single shared converter — its state is purely the registered algorithms,
# stateless once instantiated.
_converter = BitmapConverter()
# Bound concurrency so multiple debounced requests don't saturate CPU on a
# small device (the AxiDraw target is a Pi).
_semaphore = asyncio.Semaphore(2)


class PaletteEntry(BaseModel):
    """One cluster colour and its share of the image (0..1)."""

    color: str
    coverage: float


class PreviewResponse(BaseModel):
    """Fast-preview output for the UI."""

    svg: str
    elapsed_ms: int
    palette: list[PaletteEntry]
    warnings: list[str] = []
    cached: bool = False


def _resolve_mime(upload: UploadFile) -> str | None:
    content_type = upload.content_type
    if content_type and content_type != "application/octet-stream":
        return content_type
    if upload.filename:
        guessed, _ = mimetypes.guess_type(upload.filename)
        return guessed
    return None


def _cache_key(data: bytes, options: dict[str, Any]) -> str:
    """Stable key for ``(file bytes, options)`` — sha256 keeps it short."""
    digest = hashlib.sha256(data).hexdigest()
    serialised = json.dumps(options, sort_keys=True, default=str)
    return f"{digest}:{serialised}"


def _palette_from_svg(svg: str) -> list[PaletteEntry]:
    """Extract the colour set from a generated SVG by scanning fill/stroke attrs.

    The SVG produced by ``BitmapConverter`` carries one ``<g>`` per colour,
    tagged with either ``fill="#…"`` (direct/potrace) or ``stroke="#…"``
    (halftone/stippling). We return distinct colours in document order so the
    UI can render an ordered swatch strip.
    """
    palette: list[PaletteEntry] = []
    seen: set[str] = set()
    for attr in ('fill="', 'stroke="'):
        for chunk in svg.split(attr)[1:]:
            end = chunk.find('"')
            if end <= 0:
                continue
            colour = chunk[:end]
            if not colour.startswith("#") or colour in seen:
                continue
            seen.add(colour)
            palette.append(PaletteEntry(color=colour, coverage=0.0))
    return palette


@router.post("/preview", response_model=PreviewResponse)
async def preview(
    file: Annotated[UploadFile, File()],
    algorithm: Annotated[str, Form()] = "direct",
    options: Annotated[str | None, Form()] = None,
) -> PreviewResponse:
    """Run a quick bitmap vectorisation and return the SVG.

    Args:
        file: Uploaded image (PNG / JPEG / TIFF / WebP / HEIC).
        algorithm: ``direct`` / ``halftone`` / ``stippling``.
        options: Optional JSON object mirroring ``BitmapOptions`` (the same
            keys ``/upload`` accepts).

    Returns:
        A :class:`PreviewResponse` with a fast-rendered SVG and the palette.

    Raises:
        HTTPException: 415 if the MIME is not a supported raster image;
            413 if the upload exceeds ``MAX_PREVIEW_BYTES``;
            400 if options can't be parsed.
    """
    mime = _resolve_mime(file)
    if mime is None or mime not in _ACCEPTED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Preview only supports raster images; got {mime!r}.",
        )

    raw_opts: dict[str, Any] = {}
    if options:
        try:
            parsed = json.loads(options)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="options must be a JSON object")
        raw_opts = parsed
    raw_opts.setdefault("algorithm", algorithm)

    data = await file.read()
    if len(data) > MAX_PREVIEW_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_PREVIEW_BYTES // (1024 * 1024)} MB preview limit",
        )

    key = _cache_key(data, raw_opts)
    cached = _cache.get(key)
    if cached is not None:
        # Touch for LRU eviction order, mark cached so the UI can skip its
        # "still computing" spinner instantly.
        _cache.move_to_end(key)
        return cached.model_copy(update={"cached": True})

    async with _semaphore:
        start = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                _converter.convert, data, options=raw_opts, fast=True
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # converter / library failure
            raise HTTPException(status_code=422, detail=f"Preview failed: {exc}") from exc
        elapsed_ms = int((time.perf_counter() - start) * 1000)

    response = PreviewResponse(
        svg=result.svg,
        elapsed_ms=elapsed_ms,
        palette=_palette_from_svg(result.svg),
        warnings=list(result.warnings),
        cached=False,
    )
    _cache[key] = response
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return response
