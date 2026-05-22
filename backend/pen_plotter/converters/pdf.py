"""PDF converter.

Extracts a single page's vector content as SVG via PyMuPDF. Reports the
document's page count in the result metadata so the UI can offer page
selection.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pymupdf

from pen_plotter.converters.base import ConversionResult, Converter


def pdf_bytes_to_svg(data: bytes, page_index: int) -> tuple[str, int]:
    """Render one page of a PDF document to SVG.

    Args:
        data: Raw PDF file bytes.
        page_index: Zero-based index of the page to render.

    Returns:
        A ``(svg, page_count)`` pair.

    Raises:
        ValueError: If the PDF has no pages or the index is out of range.
    """
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        page_count = doc.page_count
        if page_count == 0:
            raise ValueError("PDF has no pages")
        if not 0 <= page_index < page_count:
            raise ValueError(f"page {page_index} out of range (0..{page_count - 1})")
        svg = doc[page_index].get_svg_image()
    return svg, page_count


class PdfConverter(Converter):
    """Converts a selected PDF page to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"application/pdf"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert one PDF page to SVG.

        Args:
            data: Raw PDF file bytes.
            options: Optional ``page`` (zero-based index, default 0).

        Returns:
            A :class:`ConversionResult` whose metadata reports ``page_count``
            and the selected ``page``.

        Raises:
            ValueError: If ``page`` is not a valid index for the document.
        """
        opts = options or {}
        page_index = int(opts.get("page", 0))
        svg, page_count = pdf_bytes_to_svg(data, page_index)
        return ConversionResult(
            svg=svg,
            source_mime="image/svg+xml",
            metadata={"page_count": page_count, "page": page_index},
        )
