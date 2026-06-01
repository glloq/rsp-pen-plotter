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


def _path_x_extents(svg: str) -> tuple[float, float]:
    xs = [float(m) for m in re.findall(r"[ML]\s*(-?\d+(?:\.\d+)?)\s", svg)]
    assert xs, "expected at least one path coordinate"
    return min(xs), max(xs)


def test_long_word_is_broken_to_fit_page_width() -> None:
    # A single 40-character word at 10 mm font size measures well past
    # 60 mm of usable width (80 mm page – 2×10 mm margins). It must be
    # hard-broken so every glyph stays inside the viewBox.
    opts = TypographyOptions(font_size_mm=10, page_width_mm=80, margin_mm=10)
    svg = HersheyRenderer(opts).render_text("A" * 40)
    _, x_max = _path_x_extents(svg)
    # Allow a tiny epsilon for the final stroke's right side-bearing.
    assert x_max <= 80.0 + 0.5, f"glyph at x={x_max} overflows the 80 mm page"


def test_long_word_renders_every_character() -> None:
    # All 40 letters must end up drawn somewhere — the previous
    # implementation kept the word intact and let trailing glyphs run
    # past the right edge, where the SVG viewBox (and the G-code
    # generator) silently dropped them.
    opts = TypographyOptions(font_size_mm=10, page_width_mm=80, margin_mm=10)
    svg = HersheyRenderer(opts).render_text("A" * 40)
    # "A" is two strokes per glyph in the default Hershey font; 40 glyphs
    # therefore yield clearly more sub-paths than a single "A".
    one = HersheyRenderer(opts).render_text("A")
    assert svg.count("M") >= 40 * one.count("M")
