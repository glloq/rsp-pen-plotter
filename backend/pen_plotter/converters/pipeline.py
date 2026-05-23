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
) -> ConvertedFile:
    """Run the appropriate converter and produce a sanitized SVG + layer list.

    Raises:
        HTTPException: 415 if no converter for the MIME; 400 for invalid options;
            422 for converter failures.
    """
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
            result, bitmap_segmentation = converter.segment_and_render(
                data, options=parsed_options
            )
            bitmap_options = BitmapOptions.model_validate(parsed_options)
        else:
            result = converter.convert(data, options=parsed_options)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not convert file: {exc}") from exc

    svg = sanitize_svg(result.svg)
    source_file = PurePosixPath(filename).name if filename else "upload"
    return ConvertedFile(
        source_file=source_file,
        source_mime=mime,
        svg=svg,
        layers=extract_layers(svg),
        warnings=list(result.warnings),
        metadata=dict(result.metadata),
        bitmap_segmentation=bitmap_segmentation,
        bitmap_options=bitmap_options,
    )
