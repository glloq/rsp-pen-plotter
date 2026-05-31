"""SVG passthrough converter.

SVG is already the pivot format, so this converter decodes the input and
applies the same post-processing chain as :mod:`pen_plotter.converters.pdf`:
``<use>`` references to local definitions are inlined (so Inkscape symbol
libraries and PDF-exported SVG plot correctly), embedded ``<image>`` rasters
are vectorized through the bitmap converter, and any remaining vector content
that is not already in a labeled group is wrapped into a ``text`` layer.

When the operator enables Hershey text re-render, every ``<text>`` /
``<tspan>`` element is replaced by single-stroke Hershey polylines at the
same baseline position — the only way to actually plot the text instead of
emitting a warning that asks the user to outline it first.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar
from xml.etree import ElementTree as ET

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.core.pdf_postprocess import extract_bitmap_options, postprocess_pdf_svg
from pen_plotter.core.svg_text_extract import (
    extract_svg_text_spans,
    strip_text_elements,
)
from pen_plotter.typography import render_placed_spans


def _text_elements_present(svg: str) -> int:
    """Count ``<text>`` elements (best-effort, ignores ``<textPath>``)."""
    return len(re.findall(r"<text[\s>]", svg))


def _hershey_text_group_from_svg(svg: str, opts: dict[str, Any]) -> tuple[str, str]:
    """Extract `<text>` from the input SVG and return a Hershey replacement group.

    Returns ``(stripped_svg, hershey_group)``. When ``hershey_text`` is not
    enabled or no usable text spans are found, the original SVG is returned
    unchanged and the group is the empty string.
    """
    if not bool(opts.get("hershey_text", False)):
        return svg, ""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg, ""
    spans = extract_svg_text_spans(root)
    # Strip every <text> unconditionally when the toggle is on: even
    # empty ones (no spans) shouldn't leave a stray element behind that
    # would re-trip the "<text> not plottable" warning downstream.
    strip_text_elements(root)
    stripped = ET.tostring(root, encoding="unicode")
    if not spans:
        return stripped, ""
    group = render_placed_spans(
        spans,
        font=str(opts.get("font", "futural")),
        stroke_width=float(opts.get("stroke_width_mm", 0.3)),
    )
    return stripped, group


class SvgConverter(Converter):
    """Normalizes SVG input to the pivot format.

    Inlines local ``<use>`` references and vectorizes embedded raster
    ``<image>`` elements into their own labeled layers. Optionally
    replaces ``<text>`` with single-stroke Hershey strokes.
    """

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"image/svg+xml"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Decode and normalize SVG bytes for the plotter pipeline.

        Args:
            data: The raw SVG file bytes.
            options: Optional bitmap-converter options applied to embedded
                raster ``<image>`` elements (``algorithm``, ``num_colors``,
                ``algorithm_options``, …) plus the Hershey text re-render
                toggle (``hershey_text``, ``font``, ``stroke_width_mm``).

        Returns:
            A :class:`ConversionResult` containing the post-processed SVG.
            Warnings note any non-plottable ``<text>`` elements still
            present (i.e. when ``hershey_text`` is disabled).
        """
        opts = options or {}
        bitmap_options = extract_bitmap_options(opts)
        raw_svg = data.decode("utf-8")
        warnings: list[str] = []
        raw_svg, hershey_group = _hershey_text_group_from_svg(raw_svg, opts)
        text_count = _text_elements_present(raw_svg)
        if text_count:
            warnings.append(
                f"SVG contains {text_count} <text> element(s); these will not be "
                "plotted. Enable the Hershey text option or convert text to outline "
                "paths in your editor before export."
            )
        svg, image_warnings = postprocess_pdf_svg(
            raw_svg,
            bitmap_options=bitmap_options,
            hershey_text_group=hershey_group or None,
        )
        warnings.extend(image_warnings)
        return ConversionResult(svg=svg, source_mime="image/svg+xml", warnings=warnings)
