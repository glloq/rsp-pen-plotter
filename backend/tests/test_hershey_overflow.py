"""Page overflow handling for the Hershey renderer.

When the laid-out text exceeds ``page_height_mm``, the renderer grows
the output viewBox vertically so every glyph stays inside the SVG. Short
text leaves the page dimensions untouched.
"""

import re

from pen_plotter.typography import HersheyRenderer, TypographyOptions


def _page_height(svg: str) -> float:
    match = re.search(r'height="([0-9.]+)mm"', svg)
    assert match
    return float(match.group(1))


def test_short_text_preserves_page_height() -> None:
    opts = TypographyOptions(font_size_mm=10, page_height_mm=100)
    svg = HersheyRenderer(opts).render_text("just one line")
    assert _page_height(svg) == 100


def test_overflowing_text_grows_page_height() -> None:
    opts = TypographyOptions(font_size_mm=10, page_width_mm=80, page_height_mm=30, margin_mm=5)
    svg = HersheyRenderer(opts).render_text("\n".join(f"l{i}" for i in range(10)))
    # 10 lines at 10mm × 1.5 line-spacing = 150mm of content. The output
    # must be at least tall enough to fit them (plus margins).
    assert _page_height(svg) > 100


def test_viewbox_matches_page_height_after_overflow() -> None:
    opts = TypographyOptions(font_size_mm=10, page_width_mm=80, page_height_mm=30, margin_mm=5)
    svg = HersheyRenderer(opts).render_text("\n".join(f"l{i}" for i in range(8)))
    height = _page_height(svg)
    vb = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
    assert vb
    assert float(vb.group(2)) == height
