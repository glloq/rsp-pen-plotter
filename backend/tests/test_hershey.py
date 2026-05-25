import xml.etree.ElementTree as ET

import pytest

from pen_plotter.typography.hershey import (
    HersheyRenderer,
    TypographyOptions,
    available_fonts,
)

_INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"


def test_available_fonts_is_non_empty() -> None:
    fonts = available_fonts()
    assert fonts
    assert "futural" in fonts


def test_unknown_font_raises() -> None:
    with pytest.raises(ValueError):
        HersheyRenderer(TypographyOptions(font="not-a-real-font"))


def test_render_text_produces_labeled_svg() -> None:
    renderer = HersheyRenderer(TypographyOptions())
    svg = renderer.render_text("Hello plotter")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    groups = [child for child in root if child.tag.endswith("}g")]
    assert groups
    assert groups[0].get(_INKSCAPE_LABEL) == "text"
    # Single-stroke output: paths only, no fills.
    assert groups[0].get("fill") == "none"
    assert any(child.tag.endswith("}path") for child in groups[0])


def test_long_text_word_wraps_to_multiple_lines() -> None:
    opts = TypographyOptions(page_width_mm=60.0, margin_mm=5.0, font_size_mm=6.0)
    renderer = HersheyRenderer(opts)
    narrow = renderer.render_text("word " * 40)
    one_word = renderer.render_text("word")
    assert narrow.count("<path") > one_word.count("<path")


def test_alignment_shifts_geometry_right() -> None:
    text = "short line"
    left = HersheyRenderer(TypographyOptions(alignment="left")).render_text(text)
    right = HersheyRenderer(TypographyOptions(alignment="right")).render_text(text)
    # Right alignment pushes the first move command to a larger x than left.
    left_x = float(left.split("M", 2)[1].split(" ")[0])
    right_x = float(right.split("M", 2)[1].split(" ")[0])
    assert right_x > left_x


def test_strokes_render_as_continuous_subpaths() -> None:
    """Each glyph stroke should be one ``M ... L L L`` polyline.

    Regression: an earlier implementation emitted every stroke segment
    as its own ``M ... L`` pair, forcing the G-code generator to lift
    the pen between each segment of a curve. The pen plotter could
    still draw the text but the simulator preview and the physical
    plot looked broken.
    """
    svg = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("e")
    path_d = svg.split('d="', 1)[1].split('"', 1)[0]
    # Letter "e" is one continuous stroke — so a single ``M`` followed
    # by several ``L`` commands, no extra moves.
    assert path_d.count("M") == 1
    assert path_d.count("L") >= 5


def test_bold_doubles_stroke_count() -> None:
    """Bold renders each stroke twice with a small offset."""
    text = "abc"
    plain = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text(text)
    bold = HersheyRenderer(TypographyOptions(font_size_mm=10.0, bold=True)).render_text(text)
    plain_d = plain.split('d="', 1)[1].split('"', 1)[0]
    bold_d = bold.split('d="', 1)[1].split('"', 1)[0]
    assert bold_d.count("M") == 2 * plain_d.count("M")


def test_italic_slants_glyph_top_to_the_right() -> None:
    """Italic should shear glyph tops forward (larger x at the top)."""
    plain = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("I")
    italic = HersheyRenderer(TypographyOptions(font_size_mm=10.0, italic=True)).render_text("I")
    # First M coordinate is the top of the first stroke (font y is high
    # there, mapped via baseline_y - y to a small SVG y). Italic adds
    # ``y * tan(slant)`` so the italic top sits to the right of plain.
    plain_x = float(plain.split("M", 2)[1].split(" ")[0])
    italic_x = float(italic.split("M", 2)[1].split(" ")[0])
    assert italic_x > plain_x


def test_letter_spacing_widens_line() -> None:
    """Positive letter spacing pushes later glyphs further right."""
    base = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("AB")
    spaced = HersheyRenderer(
        TypographyOptions(font_size_mm=10.0, letter_spacing_mm=5.0)
    ).render_text("AB")
    # Compare the x of the LAST move command — it sits on the second glyph
    # and so picks up the inserted space between A and B.
    base_last = float(base.rsplit("M", 1)[1].split(" ")[0])
    spaced_last = float(spaced.rsplit("M", 1)[1].split(" ")[0])
    assert spaced_last > base_last + 3.0
