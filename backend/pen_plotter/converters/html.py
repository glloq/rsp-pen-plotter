"""HTML converter.

Renders HTML to PDF via WeasyPrint, then extracts vector SVG with PyMuPDF.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from weasyprint import HTML

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.converters.pdf import build_hershey_text_group, pdf_bytes_to_svg
from pen_plotter.core.pdf_postprocess import extract_bitmap_options, postprocess_pdf_svg

# Matches a CSS ``background[-color]`` declaration whose value is one of
# the pure-black aliases. We intentionally do NOT match ``color:`` (so
# text ink stays black) or ``border[-…]:`` (so registration borders /
# 2 px page frames stay precise outlines rather than getting hatched).
_BG_BLACK_RE = re.compile(
    r"""
    (background(?:-color)?\s*:\s*)         # property + colon, captured for re-emit
    (?:
        \#000(?:000)?\b                    # #000 or #000000
        | black\b                          # named colour
        | rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)   # rgb(0,0,0) — the explicit form
                                           # the operator's HTML test page uses
                                           # for the dark end of its ramp
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _nudge_explicit_black_backgrounds(html: str) -> str:
    """Replace explicit pure-black backgrounds with ``#010101``.

    PyMuPDF emits the SVG default fill (which IS black) by simply
    omitting the ``fill`` attribute on the resulting ``<path>``. That
    makes operator-intended black swatches indistinguishable from the
    dozens of auxiliary no-fill paths WeasyPrint also emits — border
    rings, clip rectangles, every coloured bar's duplicate outline —
    so the post-processor can't safely hatch ALL no-fill paths and the
    operator's rgb(0,0,0) print-test cell ends up as a bare outline
    instead of a solid swatch. Rewriting the source's pure-black
    background to ``#010101`` (still grayscale, R == G == B == 1,
    luminance ≈ 0.4 %) makes WeasyPrint write an explicit
    ``fill="#010101"`` on the path, which the grayscale density
    hatcher then folds into its black layer at min spacing. Visually
    identical, distinguishable to the post-processor.
    """
    return _BG_BLACK_RE.sub(lambda m: f"{m.group(1)}#010101", html)


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
        html = _nudge_explicit_black_backgrounds(html)
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
