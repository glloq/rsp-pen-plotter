"""HTML converter.

Renders HTML to PDF via WeasyPrint, then extracts vector SVG with PyMuPDF.
"""

from __future__ import annotations

from typing import Any, ClassVar

from weasyprint import HTML

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.converters.pdf import build_hershey_text_group, pdf_bytes_to_svg
from pen_plotter.core.pdf_postprocess import extract_bitmap_options, postprocess_pdf_svg


class HtmlConverter(Converter):
    """Converts HTML to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"text/html"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Render HTML bytes to SVG.

        Args:
            data: Raw HTML bytes.
            options: Optional bitmap-converter options applied to embedded
                raster images (``algorithm``, ``num_colors``, …).

        Returns:
            A :class:`ConversionResult` containing the first rendered page,
            with text expanded inline and any embedded raster vectorized as
            a sibling labeled layer.
        """
        opts = options or {}
        page_index = int(opts.get("page", 0))
        bitmap_options = extract_bitmap_options(opts)
        html = data.decode("utf-8", errors="replace")
        pdf_bytes = HTML(string=html).write_pdf()
        raw_svg, page_count, width_mm, height_mm = pdf_bytes_to_svg(pdf_bytes, page_index)
        hershey_group = build_hershey_text_group(pdf_bytes, page_index, opts)
        svg, warnings = postprocess_pdf_svg(
            raw_svg,
            bitmap_options=bitmap_options,
            hershey_text_group=hershey_group or None,
            pdf_bytes=pdf_bytes,
            page_index=page_index,
        )
        return ConversionResult(
            svg=svg,
            source_mime="image/svg+xml",
            warnings=warnings,
            metadata={
                "page_count": page_count,
                "page": page_index,
                "page_width_mm": width_mm,
                "page_height_mm": height_mm,
            },
        )
