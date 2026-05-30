"""Shared conversion pipeline used by ``/upload`` and ``/files``.

Centralizes the steps every entry point needs: pick a converter by MIME,
run it (with the cache-aware bitmap variant), sanitize the SVG, extract
layers, and surface warnings + metadata. Keeps the API endpoints thin and
guarantees both routes behave identically.
"""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from fastapi import HTTPException, UploadFile

from pen_plotter.converters.base import UnsupportedFormatError
from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions, SegmentationResult
from pen_plotter.converters.registry import registry
from pen_plotter.core.layers import extract_layers
from pen_plotter.core.sanitize import sanitize_svg
from pen_plotter.models import LayerInfo


@dataclass(frozen=True)
class ConvertedFile:
    """Result of converting an uploaded file to SVG + layer metadata."""

    source_file: str
    source_mime: str
    svg: str
    layers: list[LayerInfo]
    warnings: list[str]
    metadata: dict[str, Any]
    # Optional bitmap segmentation cache hook — when set, the caller should
    # call ``remember_job`` so ``/rerender`` can skip re-segmentation.
    bitmap_segmentation: SegmentationResult | None
    bitmap_options: BitmapOptions | None


# Hard cap on filename length we agree to store / log. Browsers and most
# filesystems allow up to 255 bytes, but anything beyond that on our side
# is almost certainly an attacker probing for path / log overflow bugs.
MAX_FILENAME_BYTES = 255


async def read_upload_safely(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an ``UploadFile`` in chunks, capped at ``max_bytes``.

    Raises HTTP 413 as soon as the cumulative size crosses the limit so a
    malicious 1 GB body never sits fully in memory. Empty uploads raise
    HTTP 400 — every accepted converter needs at least a few bytes of input
    and the downstream code reads ``data[0]`` in several places.
    """
    if upload.filename and len(upload.filename.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise HTTPException(status_code=400, detail="Filename is too long")
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024  # 1 MiB
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            # Stop draining the stream — starlette will release it when
            # the response is returned.
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return b"".join(chunks)


def resolve_mime(upload: UploadFile) -> str | None:
    """Best-effort MIME detection from the client header or filename."""
    content_type = upload.content_type
    if content_type and content_type != "application/octet-stream":
        return content_type
    if upload.filename:
        guessed, _ = mimetypes.guess_type(upload.filename)
        return guessed
    return None


def resolve_mime_from_name(filename: str | None, fallback: str | None = None) -> str | None:
    """Like :func:`resolve_mime` but takes a filename + optional content type."""
    if fallback and fallback != "application/octet-stream":
        return fallback
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        return guessed
    return None


def parse_options(raw: str | None) -> dict[str, Any]:
    """Parse the optional JSON ``options`` form field into a dict."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="options must be a JSON object")
    return parsed


def convert_file(
    data: bytes,
    filename: str | None,
    mime: str,
    options: dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> ConvertedFile:
    """Run the appropriate converter and produce a sanitized SVG + layer list.

    Raises:
        HTTPException: 415 if no converter for the MIME; 400 for invalid options;
            422 for converter failures.
    """
    from pen_plotter.observability import traced_span

    with traced_span(
        "pipeline.convert_file",
        mime=mime,
        size_bytes=len(data),
        filename=filename or "",
    ):
        try:
            converter = registry.for_mime(mime)
        except UnsupportedFormatError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

        parsed_options = dict(options or {})
        parsed_options.setdefault("source_mime", mime)

        bitmap_segmentation: SegmentationResult | None = None
        bitmap_options: BitmapOptions | None = None
        try:
            if isinstance(converter, BitmapConverter):
                with traced_span("pipeline.segment_and_render"):
                    result, bitmap_segmentation = converter.segment_and_render(
                        data,
                        options=parsed_options,
                        progress_callback=progress_callback,
                    )
                bitmap_options = BitmapOptions.model_validate(parsed_options)
            else:
                with traced_span("pipeline.convert", converter=type(converter).__name__):
                    result = converter.convert(data, options=parsed_options)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not convert file: {exc}") from exc

        with traced_span("pipeline.sanitize_svg"):
            svg = sanitize_svg(result.svg)
        with traced_span("pipeline.extract_layers"):
            layers = extract_layers(svg)
        # IR pass-through (E.1 wire). When ``OMNIPLOT_IR_ENABLED=1`` we
        # also build the typed :class:`GeometryIR` from the sanitized
        # SVG and stash it in the artifact cache keyed on
        # ``(content_sha256, options)``. The IR isn't consumed by any
        # downstream code yet — the cache is the infrastructure for the
        # future IR-native render/optimize path. Cheap by construction:
        # the adapter walks the SVG once and the cache write is a
        # single SQLite UPSERT.
        from pen_plotter.domain.ir.adapter import is_ir_enabled

        if is_ir_enabled():
            with traced_span("pipeline.ir.build"):
                from pen_plotter.application.ir_cache import store_geometry
                from pen_plotter.domain.ir.adapter import (
                    content_sha256,
                    geometry_ir_from_svg,
                )

                source_hash = content_sha256(data)
                geometry = geometry_ir_from_svg(svg, source_hash=source_hash)
                store_geometry(source_hash, parsed_options, geometry)
        source_file = PurePosixPath(filename).name if filename else "upload"
        return ConvertedFile(
            source_file=source_file,
            source_mime=mime,
            svg=svg,
            layers=layers,
            warnings=list(result.warnings),
            metadata=dict(result.metadata),
            bitmap_segmentation=bitmap_segmentation,
            bitmap_options=bitmap_options,
        )
