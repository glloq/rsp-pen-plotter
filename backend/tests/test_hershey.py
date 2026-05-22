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
