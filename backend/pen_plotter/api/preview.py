"""Fast bitmap preview endpoint.

Live-tunable parameters in the UI (algorithm, num_colors, drop_background, …)
benefit from sub-second feedback. The regular ``/upload`` path runs k-means
with 10 initialisations on a ~800px-wide image — that is overkill while the
operator is still picking parameters. ``/preview`` exposes three quality
tiers (Draft / Standard / Final) so the operator chooses where to sit on
the latency/fidelity curve: Draft caps the segmentation sample, Standard
honours the operator's resolution choice with a cheap k-means, Final pays
for the full 10-restart k-means.

Concurrency is limited so a slider drag does not pin every CPU; an in-memory
LRU caches successful results by file hash + canonicalised options +
quality tier so an identical request returns immediately. The DOS knob is
the request size limit, same as upload.
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
_cache: OrderedDict[str, PreviewResponse] = OrderedDict()
# A single shared converter — its state is purely the registered algorithms,
# stateless once instantiated.
_converter = BitmapConverter()
# Bound concurrency so multiple debounced requests don't saturate CPU on a
# small device (the AxiDraw target is a Pi).
_semaphore = asyncio.Semaphore(2)

# Bumped when the conversion pipeline output changes in a way that would
# stale all cached SVGs (algorithm tweaks, default values, segmentation
# tweaks). The frontend's options builder is intentionally NOT versioned
# here — Pydantic defaults handle that, and operator-visible knobs already
# live in the options dict that's part of the cache key.
_CONVERTER_VERSION = "v2"

# Quality presets. The /preview endpoint trades quality for latency; the
# operator picks one of three tiers via the preview pane toolbar.
#   - draft:    smallest sample, single k-means restart — slider-drag tier.
#   - standard: honour options.max_dimension_px, single restart (the
#               historical `fast=True` behaviour).
#   - final:    honour options.max_dimension_px, full 10-restart k-means —
#               near-/upload fidelity, for the "I've stopped tweaking,
#               show me the truth" tier.
_QUALITY_TIERS: dict[str, dict[str, Any]] = {
    "draft": {"n_init": 1, "max_dim_cap": 256},
    "standard": {"n_init": 1, "max_dim_cap": None},
    "final": {"n_init": 10, "max_dim_cap": None},
}
_DEFAULT_QUALITY = "standard"


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


def _canonicalise(value: Any) -> Any:
    """Quantise floats so semantically-equivalent options share a cache slot.

    A slider that emits ``1.2000000000001`` and one that emits ``1.2`` would
    otherwise miss the LRU even though the pipeline produces an identical
    SVG. We round to 4 decimals (well below any perceptual threshold for
    gamma / levels / brightness / contrast / saturation), normalise booleans
    away from numpy types, and recurse into nested dicts / lists.
    """
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return value
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(v) for v in value]
    return value


def _cache_key(data: bytes, options: dict[str, Any], quality: str) -> str:
    """Stable key for ``(file bytes, options, quality)``.

    Includes the converter version so cached SVGs from older pipeline
    revisions are silently invalidated after a backend upgrade.
    """
    digest = hashlib.sha256(data).hexdigest()
    canonical = _canonicalise(options)
    serialised = json.dumps(canonical, sort_keys=True, default=str)
    return f"{_CONVERTER_VERSION}:{quality}:{digest}:{serialised}"


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
    quality: Annotated[str, Form()] = _DEFAULT_QUALITY,
) -> PreviewResponse:
    """Run a quick bitmap vectorisation and return the SVG.

    Args:
        file: Uploaded image (PNG / JPEG / TIFF / WebP / HEIC).
        algorithm: ``direct`` / ``halftone`` / ``stippling``.
        options: Optional JSON object mirroring ``BitmapOptions`` (the same
            keys ``/upload`` accepts).
        quality: ``draft`` / ``standard`` / ``final``. Trades latency for
            fidelity — see ``_QUALITY_TIERS`` for the concrete knobs.

    Returns:
        A :class:`PreviewResponse` with a fast-rendered SVG and the palette.

    Raises:
        HTTPException: 415 if the MIME is not a supported raster image;
            413 if the upload exceeds ``MAX_PREVIEW_BYTES``;
            400 if options can't be parsed or the quality tier is unknown.
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

    if quality not in _QUALITY_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown quality tier {quality!r}; expected one of {sorted(_QUALITY_TIERS)}",
        )
    tier = _QUALITY_TIERS[quality]
    # The Draft tier caps max_dimension_px so a slider drag stays sub-second
    # regardless of the operator's chosen segmentation resolution. We never
    # *raise* the cap, only lower it — Standard and Final honour the
    # operator's choice exactly.
    cap = tier["max_dim_cap"]
    if cap is not None:
        current_max = raw_opts.get("max_dimension_px")
        if not isinstance(current_max, (int, float)) or current_max > cap:
            raw_opts["max_dimension_px"] = cap

    data = await file.read()
    if len(data) > MAX_PREVIEW_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_PREVIEW_BYTES // (1024 * 1024)} MB preview limit",
        )

    key = _cache_key(data, raw_opts, quality)
    cached = _cache.get(key)
    if cached is not None:
        # Touch for LRU eviction order, mark cached so the UI can skip its
        # "still computing" spinner instantly.
        _cache.move_to_end(key)
        return cached.model_copy(update={"cached": True})

    # The converter's ``fast`` flag controls k-means n_init (1 vs 10). The
    # Draft and Standard tiers both want the single-restart path; only
    # Final pays for the full 10-restart k-means.
    fast_mode = tier["n_init"] == 1

    async with _semaphore:
        start = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                _converter.convert, data, options=raw_opts, fast=fast_mode
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
