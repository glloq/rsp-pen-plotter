"""PDF converter.

Extracts a single page's vector content as SVG via PyMuPDF, then runs the
post-processing chain that inlines ``<use>`` glyph references (so the text
survives sanitization and reaches vpype) and vectorizes embedded raster
``<image>`` elements into their own labeled layers (so they actually plot
instead of being silently dropped). Reports the document's page count in
the result metadata so the UI can offer page selection.

When the operator enables Hershey text re-render, the original glyph
outlines emitted by PyMuPDF are stripped and the text is redrawn as
single-stroke Hershey polylines at the same baseline positions. The
PDF's font metrics (size, bold / italic flags) are honoured, but the
glyph shapes come from the operator's chosen Hershey face — which is
the only way to plot legibly with a pen, since outline tracing of
real TrueType glyphs produces a double-traced silhouette no pen can
fill convincingly.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pymupdf

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.core.pdf_postprocess import postprocess_pdf_svg
from pen_plotter.typography import PlacedSpan, render_placed_spans

# PDF user-space units are points (1 pt = 1/72 inch).
PT_TO_MM = 25.4 / 72.0

# PyMuPDF span ``flags`` bit assignments. Only the two we render
# specially are pulled out; the rest (superscript, serif, mono) don't
# change how Hershey draws the glyph.
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4


def pdf_bytes_to_svg(data: bytes, page_index: int) -> tuple[str, int, float, float]:
    """Render one page of a PDF document to raw SVG (pre-postprocessing).

    Args:
        data: Raw PDF file bytes.
        page_index: Zero-based index of the page to render.

    Returns:
        A ``(svg, page_count, page_width_mm, page_height_mm)`` tuple. The
        page dimensions come from the PDF's MediaBox so a downstream
        consumer can size an A4 page at 210 × 297 mm without having to
        re-parse the PDF.

    Raises:
        ValueError: If the PDF has no pages or the index is out of range.
    """
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        page_count = doc.page_count
        if page_count == 0:
            raise ValueError("PDF has no pages")
        if not 0 <= page_index < page_count:
            raise ValueError(f"page {page_index} out of range (0..{page_count - 1})")
        page = doc[page_index]
        svg = page.get_svg_image()
        width_mm = float(page.rect.width) * PT_TO_MM
        height_mm = float(page.rect.height) * PT_TO_MM
    return svg, page_count, width_mm, height_mm


def extract_pdf_text_spans(data: bytes, page_index: int) -> list[PlacedSpan]:
    """Extract Hershey-renderable text spans from one PDF page.

    Coordinates are returned in PyMuPDF SVG user units (points) so the
    output matches the surrounding SVG produced by
    :func:`pdf_bytes_to_svg` without any further conversion. ``size``
    is the PDF font size in points; bold / italic come from the PyMuPDF
    span ``flags`` bitmask.
    """
    spans: list[PlacedSpan] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 0 <= page_index < doc.page_count:
            return spans
        page = doc[page_index]
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text") or ""
                    if not text.strip():
                        continue
                    origin = span.get("origin") or (0.0, 0.0)
                    flags = int(span.get("flags", 0))
                    spans.append(
                        PlacedSpan(
                            text=text,
                            x=float(origin[0]),
                            baseline_y=float(origin[1]),
                            size=float(span.get("size", 10.0)),
                            bold=bool(flags & _FLAG_BOLD),
                            italic=bool(flags & _FLAG_ITALIC),
                        )
                    )
    return spans


def build_hershey_text_group(data: bytes, page_index: int, opts: dict[str, Any]) -> str:
    """Build the Hershey text replacement group for a PDF page.

    Returns the empty string when ``hershey_text`` is not enabled or
    the page contains no extractable text. ``opts`` may carry
    ``font`` (Hershey face name) and ``stroke_width_mm`` overrides;
    other ``TypographyOptions`` fields (size, alignment, margins) are
    ignored because the document's own layout dictates per-span size
    and position.
    """
    if not bool(opts.get("hershey_text", False)):
        return ""
    spans = extract_pdf_text_spans(data, page_index)
    if not spans:
        return ""
    return render_placed_spans(
        spans,
        font=str(opts.get("font", "futural")),
        stroke_width=float(opts.get("stroke_width_mm", 0.3)),
    )


class PdfConverter(Converter):
    """Converts a selected PDF page to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"application/pdf"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert one PDF page to SVG with text inlined and rasters vectorized.

        Args:
            data: Raw PDF file bytes.
            options: Optional ``page`` (zero-based index, default 0) plus any
                bitmap-converter options applied to embedded raster images
                (``algorithm``, ``num_colors``, ``algorithm_options``, …).

        Returns:
            A :class:`ConversionResult` whose metadata reports ``page_count``
            and the selected ``page``, and whose ``warnings`` include any
            per-image vectorization failures.

        Raises:
            ValueError: If ``page`` is not a valid index for the document.
        """
        opts = options or {}
        page_index = int(opts.get("page", 0))
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

        raw_svg, page_count, width_mm, height_mm = pdf_bytes_to_svg(data, page_index)
        hershey_group = build_hershey_text_group(data, page_index, opts)
        svg, warnings = postprocess_pdf_svg(
            raw_svg,
            bitmap_options=bitmap_options,
            hershey_text_group=hershey_group or None,
        )
        return ConversionResult(
            svg=svg,
            source_mime="image/svg+xml",
            metadata={
                "page_count": page_count,
                "page": page_index,
                "page_width_mm": width_mm,
                "page_height_mm": height_mm,
            },
            warnings=warnings,
        )
