import xml.etree.ElementTree as ET

import pytest

from pen_plotter.typography import PlacedSpan, render_placed_spans
from pen_plotter.typography.hershey import (
    HersheyRenderer,
    TypographyOptions,
    _sanitize_for_font,
    _supported_chars,
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


# ---- Unicode sanitization --------------------------------------------------
#
# Regression coverage for the "letters going missing" class of bug. The
# bundled Hershey fonts only carry printable ASCII; without preprocessing,
# the upstream ``HersheyFonts`` library silently drops every other code
# point AND lets the dropped character contribute zero advance — so
# ``café`` plots as ``caf`` with no width for the missing ``é``, and the
# operator reads it as a typo. The renderer pre-sanitizes every text
# entry point so accented Latin chars decompose to ASCII, smart quotes
# and dashes collapse to their typewriter equivalents, NBSPs become
# spaces, and anything still unsupported renders as a visible ``?``
# placeholder rather than a hole in the word.


def test_sanitize_strips_combining_accents() -> None:
    """Latin accents decompose to base ASCII letters."""
    supported = _supported_chars("futural")
    assert _sanitize_for_font("café", supported) == "cafe"
    assert _sanitize_for_font("naïveté", supported) == "naivete"
    assert _sanitize_for_font("Ångström", supported) == "Angstrom"


def test_sanitize_maps_smart_quotes_and_dashes() -> None:
    """Typographic punctuation collapses to ASCII equivalents."""
    supported = _supported_chars("futural")
    assert _sanitize_for_font("“Hello”", supported) == '"Hello"'
    assert _sanitize_for_font("l’\xe9t\xe9", supported) == "l'ete"
    assert _sanitize_for_font("a—b", supported) == "a-b"
    assert _sanitize_for_font("a…b", supported) == "a...b"
    assert _sanitize_for_font("a b", supported) == "a b"


def test_sanitize_replaces_unsupported_with_fallback() -> None:
    """Anything still unsupported after decomposition renders as ``?``.

    A visible placeholder lets the operator see that an input character
    could not be drawn, instead of the upstream library's silent drop
    that just shrinks the surrounding word.
    """
    supported = _supported_chars("futural")
    # CJK / emoji aren't in the bundled fonts and don't decompose to Latin.
    assert "?" in _sanitize_for_font("漢字", supported)
    assert "?" in _sanitize_for_font("a🙂b", supported)


def test_render_text_keeps_accented_letters() -> None:
    """``café`` renders the same number of strokes as ``cafe``.

    Pre-fix the ``é`` was silently dropped and the SVG was identical to
    ``caf`` — operators saw the last letter of a French word disappear
    when moving from file → preparation → print.
    """
    accented = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("café")
    ascii_ref = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("cafe")
    truncated = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text("caf")
    assert accented.count("M") == ascii_ref.count("M")
    assert accented.count("M") > truncated.count("M")


def test_render_text_keeps_smart_punctuation() -> None:
    """Smart quotes / em dash / ellipsis all draw, not silently dropped."""
    smart = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text(
        "“Hello—world…”"
    )
    plain = HersheyRenderer(TypographyOptions(font_size_mm=10.0)).render_text(
        '"Hello-world..."'
    )
    # Same Hershey output: the smart-punctuation form has been mapped
    # onto the plain ASCII glyph sequence one character at a time.
    assert smart.count("M") == plain.count("M")


def _max_x(svg: str) -> float:
    import re

    xs = [float(m) for m in re.findall(r"[ML]\s*(-?\d+(?:\.\d+)?)\s", svg)]
    return max(xs) if xs else 0.0


def test_placed_span_compresses_to_source_width() -> None:
    """PDF/DOCX text spans must fit their source layout width.

    PyMuPDF reports each span's ``bbox`` so we know what horizontal
    extent the source document expected. Hershey glyphs are wider than
    a typical TrueType face, so plotting at native width would push the
    span past the right edge of the source line — the operator sees
    "lines too long" / "running off the page". The renderer compresses
    each span horizontally to fit the source width.
    """
    natural = render_placed_spans(
        [PlacedSpan(text="Hello world", x=0.0, baseline_y=20.0, size=10.0)]
    )
    natural_x_max = _max_x(natural)
    # Squeeze to 75 % — well above the 60 % legibility floor so the
    # exact target is reachable.
    target = natural_x_max * 0.75
    squeezed = render_placed_spans(
        [
            PlacedSpan(
                text="Hello world",
                x=0.0,
                baseline_y=20.0,
                size=10.0,
                source_width=target,
            )
        ]
    )
    squeezed_x_max = _max_x(squeezed)
    # Compression brings the span back within the source extent (allow
    # a tiny epsilon for float rounding in the SVG coords).
    assert squeezed_x_max <= target + 0.5
    # And every glyph is still drawn — same number of strokes as the
    # uncompressed reference.
    assert squeezed.count("M") == natural.count("M")


def test_placed_span_floors_compression_for_legibility() -> None:
    """If the source width is absurdly small, compression clamps so
    single-stroke glyphs don't collide into an unreadable blob.

    The placed-span floor (40 %) is more aggressive than the
    plain-text wrap floor (60 %) because PDF / DOCX spans have no
    word-wrap fallback — they must fit the source layout at any cost,
    so we trade some letter-crowding for layout fidelity.
    """
    natural = render_placed_spans(
        [PlacedSpan(text="text", x=0.0, baseline_y=20.0, size=10.0)]
    )
    natural_x_max = _max_x(natural)
    # Ask for 10 % of natural — far below the placed-span floor.
    crushed = render_placed_spans(
        [
            PlacedSpan(
                text="text",
                x=0.0,
                baseline_y=20.0,
                size=10.0,
                source_width=natural_x_max * 0.1,
            )
        ]
    )
    crushed_x_max = _max_x(crushed)
    # Final extent stays around the 40 % floor, not the requested 10 %.
    assert crushed_x_max >= natural_x_max * 0.35
    assert crushed_x_max <= natural_x_max * 0.45


def test_placed_span_no_compression_when_fits_natively() -> None:
    """A source_width larger than the natural Hershey extent leaves
    the span unchanged — we never stretch."""
    baseline = render_placed_spans(
        [PlacedSpan(text="ok", x=0.0, baseline_y=20.0, size=10.0)]
    )
    roomy = render_placed_spans(
        [
            PlacedSpan(
                text="ok",
                x=0.0,
                baseline_y=20.0,
                size=10.0,
                source_width=10_000.0,
            )
        ]
    )
    assert baseline == roomy


def test_render_placed_spans_keeps_accented_letters() -> None:
    """The PDF/DXF placed-span path also sanitizes Unicode.

    Same pre-fix bug: a PDF page containing ``Économie`` was extracted
    as the literal Unicode string but Hershey dropped the ``É``, so the
    word came out missing its capital. Verify the placed flow now
    matches the equivalent ASCII baseline.
    """
    accented = render_placed_spans(
        [PlacedSpan(text="café", x=0.0, baseline_y=20.0, size=10.0)]
    )
    ascii_ref = render_placed_spans(
        [PlacedSpan(text="cafe", x=0.0, baseline_y=20.0, size=10.0)]
    )
    assert accented.count("M") == ascii_ref.count("M")
    assert accented.count("M") > 0
