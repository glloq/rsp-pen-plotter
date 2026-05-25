"""Hershey re-render for SVG ``<text>`` sources.

Mirrors the PDF/DOCX/HTML test surface: when the operator enables
``hershey_text``, every ``<text>`` element in the input SVG must be
replaced by single-stroke polylines and the original glyph elements
removed so the pen plotter doesn't paint a double-traced silhouette on
top of the Hershey output.
"""

import xml.etree.ElementTree as ET

from pen_plotter.converters.svg import SvgConverter

_INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"


_SVG_WITH_TEXT = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">'
    b'<text x="10" y="40" font-size="20">Hello</text>'
    b"</svg>"
)


def test_svg_without_hershey_keeps_warning_and_drops_text() -> None:
    """Default behaviour stays: warning emitted, no stroke generated."""
    result = SvgConverter().convert(_SVG_WITH_TEXT, options={})
    assert any("text" in w for w in result.warnings)
    assert "<path" not in result.svg


def test_svg_with_hershey_replaces_text_with_strokes() -> None:
    """``hershey_text=True`` Hershey-renders every <text> element."""
    result = SvgConverter().convert(
        _SVG_WITH_TEXT, options={"hershey_text": True, "font": "futural"}
    )
    # No more <text> in the output (stripped before postprocessing).
    assert "<text" not in result.svg
    # No outline-removal warning.
    assert not any("not be plotted" in w for w in result.warnings)
    # At least one Hershey path emitted.
    assert "<path" in result.svg
    # Hershey output sits in a labeled group so extract_layers picks it up.
    root = ET.fromstring(result.svg)
    labels = {child.get(_INKSCAPE_LABEL) for child in root.iter()}
    assert "text" in labels


def test_svg_hershey_honours_font_choice() -> None:
    """Switching the font produces different stroke geometry."""
    futural = SvgConverter().convert(
        _SVG_WITH_TEXT, options={"hershey_text": True, "font": "futural"}
    )
    timesr = SvgConverter().convert(
        _SVG_WITH_TEXT, options={"hershey_text": True, "font": "timesr"}
    )
    # Both produced output but the path data differs — the two faces
    # have different glyph shapes.
    assert futural.svg != timesr.svg


def test_svg_hershey_honours_tspan_inheritance() -> None:
    """Nested <tspan> inherits the parent <text>'s font-size."""
    svg_in = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
        b'<text x="5" y="30" font-size="14"><tspan>nested</tspan></text>'
        b"</svg>"
    ).strip()
    result = SvgConverter().convert(svg_in, options={"hershey_text": True})
    assert "<path" in result.svg
    assert "<text" not in result.svg


def test_svg_hershey_handles_empty_text_gracefully() -> None:
    """A <text> with no content shouldn't crash; just be stripped."""
    svg_in = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 20">'
        b'<text x="0" y="10"></text>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg_in, options={"hershey_text": True})
    # No path because nothing to render, but conversion succeeded.
    assert "<text" not in result.svg
