"""SVG passthrough converter.

SVG is already the pivot format, so this converter decodes the input and
applies the same post-processing chain as :mod:`pen_plotter.converters.pdf`:
``<use>`` references to local definitions are inlined (so Inkscape symbol
libraries and PDF-exported SVG plot correctly), embedded ``<image>`` rasters
are vectorized through the bitmap converter, and any remaining vector content
that is not already in a labeled group is wrapped into a ``text`` layer.
``<text>`` and ``<tspan>`` are surfaced as warnings because they are not
plottable strokes; users should outline text in their editor before export.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.core.pdf_postprocess import postprocess_pdf_svg


def _text_elements_present(svg: str) -> int:
    """Count ``<text>`` elements (best-effort, ignores ``<textPath>``)."""
    return len(re.findall(r"<text[\s>]", svg))


class SvgConverter(Converter):
    """Normalizes SVG input to the pivot format.

    Inlines local ``<use>`` references and vectorizes embedded raster
    ``<image>`` elements into their own labeled layers.
    """

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"image/svg+xml"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Decode and normalize SVG bytes for the plotter pipeline.

        Args:
            data: The raw SVG file bytes.
            options: Optional bitmap-converter options applied to embedded
                raster ``<image>`` elements (``algorithm``, ``num_colors``,
                ``algorithm_options``, …).

        Returns:
            A :class:`ConversionResult` containing the post-processed SVG.
            Warnings note any non-plottable ``<text>`` elements left in the
            input (the user must outline text before plotting them).
        """
        opts = options or {}
        bitmap_options = {
            key: opts[key]
            for key in (
                "algorithm",
                "num_colors",
                "max_dimension_px",
                "drop_background",
                "background_luminance",
                "algorithm_options",
            )
            if key in opts
        } or None
        raw_svg = data.decode("utf-8")
        warnings: list[str] = []
        text_count = _text_elements_present(raw_svg)
        if text_count:
            warnings.append(
                f"SVG contains {text_count} <text> element(s); these will not be "
                "plotted. Convert text to outline paths in your editor before export."
            )
        svg, image_warnings = postprocess_pdf_svg(raw_svg, bitmap_options=bitmap_options)
        warnings.extend(image_warnings)
        return ConversionResult(svg=svg, source_mime="image/svg+xml", warnings=warnings)
