"""HTML converter.

Renders HTML to PDF via WeasyPrint, then extracts vector SVG with PyMuPDF.
"""

from __future__ import annotations

from typing import Any, ClassVar

from weasyprint import HTML

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.converters.pdf import pdf_bytes_to_svg


class HtmlConverter(Converter):
    """Converts HTML to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"text/html"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Render HTML bytes to SVG.

        Args:
            data: Raw HTML bytes.
            options: Unused; accepted for interface compatibility.

        Returns:
            A :class:`ConversionResult` containing the first rendered page.
        """
        html = data.decode("utf-8", errors="replace")
        pdf_bytes = HTML(string=html).write_pdf()
        svg, _ = pdf_bytes_to_svg(pdf_bytes, 0)
        return ConversionResult(svg=svg, source_mime="image/svg+xml")
