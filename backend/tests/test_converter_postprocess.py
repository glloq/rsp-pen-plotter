"""Tests for the cross-converter post-processing pipeline.

Mirrors test_pdf_postprocess.py for the converters that were missing the
same fix: EPS skipped postprocess entirely, DXF emitted a background rect
and unlabeled drawables, SVG passthrough did no normalization at all.
"""

from __future__ import annotations

import io
import re
import shutil

import ezdxf
import pytest

from pen_plotter.converters.dxf import DxfConverter
from pen_plotter.converters.eps import EpsConverter
from pen_plotter.converters.svg import SvgConverter
from pen_plotter.core.dxf_postprocess import postprocess_dxf_svg
from pen_plotter.core.layers import extract_layers
from pen_plotter.core.sanitize import sanitize_svg
from pen_plotter.core.toolpath import optimize_svg

needs_gs = pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript not installed")


def test_dxf_postprocess_strips_background_rect() -> None:
    """The ezdxf background <rect> would otherwise plot as a giant frame."""
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
        "<defs><style>.C1 {stroke: #ff0000; fill: none;}</style></defs>"
        '<rect fill="#212830" x="0" y="0" width="1000" height="1000"/>'
        '<g><path class="C1" d="M0 0L100 0"/></g>'
        "</svg>"
    )
    out = postprocess_dxf_svg(raw)
    assert "<rect" not in out, "background rect not stripped"
    assert 'inkscape:label="color-ff0000"' in out


def test_dxf_postprocess_groups_by_color_class() -> None:
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        "<defs><style>"
        ".C1 {stroke: #ff0000; fill: none;}"
        ".C2 {stroke: #00ff00; fill: none;}"
        "</style></defs>"
        '<g><path class="C1" d="M0 0L1 0"/>'
        '<path class="C2" d="M0 1L1 1"/>'
        '<path class="C1" d="M0 2L1 2"/></g>'
        "</svg>"
    )
    out = postprocess_dxf_svg(raw)
    labels = re.findall(r'inkscape:label="([^"]+)"', out)
    assert set(labels) == {"color-ff0000", "color-00ff00"}


def test_dxf_converter_produces_labeled_layer() -> None:
    """The full DXF flow: ezdxf renders → postprocess strips/groups → layers
    extract → vpype optimizes."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 50))
    msp.add_circle((50, 25), 10)
    buf = io.StringIO()
    doc.write(buf)
    data = buf.getvalue().encode("utf-8")

    result = DxfConverter().convert(data)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    assert layers, "DXF must produce at least one labeled layer"
    for layer in layers:
        assert layer.layer_id.startswith("color-"), f"layer {layer.layer_id} should be color-keyed"
        assert layer.path_count > 0, f"layer {layer.layer_id} is empty"

    optimized = optimize_svg(clean)
    assert optimized.svg.count("<path") >= 1, "vpype should produce drawable paths"


def test_dxf_postprocess_rebases_viewbox_to_mm() -> None:
    """ezdxf renders into a million-unit canvas; without rebasing, vpype's
    mm-tolerance simplification (0.05) operates on user units and produces
    no simplification at all — exploding a single circle into thousands of
    near-collinear segments."""
    doc = ezdxf.new(setup=True)
    doc.modelspace().add_line((0, 0), (50, 50))
    doc.modelspace().add_circle((25, 25), 10)
    buf = io.StringIO()
    doc.write(buf)

    result = DxfConverter().convert(buf.getvalue().encode("utf-8"))
    viewbox = re.search(r'viewBox="([^"]+)"', result.svg)
    assert viewbox is not None
    parts = [float(v) for v in viewbox.group(1).split()]
    # Drawing is 50×50 mm; viewBox should match, not the 1 000 000-unit canvas.
    assert parts[2] < 1000 and parts[3] < 1000, f"viewBox not rebased to mm: {viewbox.group(1)}"

    # Optimized polyline count must be modest, not thousands of points.
    from pen_plotter.core.sanitize import sanitize_svg

    optimized = optimize_svg(sanitize_svg(result.svg))
    total_l = sum(p.count("L") for p in re.findall(r'd="([^"]+)"', optimized.svg))
    assert total_l < 500, f"too many segments: {total_l} (simplify probably broken)"


def test_dxf_converter_does_not_plot_background() -> None:
    """The background rect must be gone before vpype sees it."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((0, 0), (0, 10))
    buf = io.StringIO()
    doc.write(buf)

    result = DxfConverter().convert(buf.getvalue().encode("utf-8"))
    clean = sanitize_svg(result.svg)
    # No <rect> at all — DXF should never emit one for us.
    assert "<rect" not in clean


def test_svg_converter_expands_local_use_references() -> None:
    """Inkscape symbol libraries used to be wiped by sanitize because <use>
    was on the blocklist. The passthrough now inlines them so vpype sees
    real geometry."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        b'viewBox="0 0 100 100">'
        b'<defs><path id="dot" d="M0 0L1 0"/></defs>'
        b'<g inkscape:label="grid">'
        b'<use xlink:href="#dot" transform="translate(10 10)"/>'
        b'<use xlink:href="#dot" transform="translate(20 20)"/>'
        b"</g>"
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    assert any(layer.layer_id == "grid" for layer in layers)
    grid = next(layer for layer in layers if layer.layer_id == "grid")
    assert grid.path_count >= 2  # two expanded copies
    optimized = optimize_svg(clean)
    assert optimized.svg.count("<path") >= 1


def test_svg_converter_warns_about_text_elements() -> None:
    """``<text>`` is not plottable; the passthrough must surface a warning so
    the user knows their text will be ignored."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        b'<text x="10" y="50">Hello</text>'
        b'<path d="M0 0L10 10" stroke="black"/>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    assert any("text" in w.lower() for w in result.warnings)


def test_svg_converter_vectorizes_embedded_image() -> None:
    """Same regression as PDF: embedded <image> must become a vectorized
    labeled layer instead of being silently dropped by vpype."""
    import base64

    from PIL import Image

    img = Image.new("RGB", (8, 8), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 100 100">'
        f'<image x="10" y="10" width="50" height="50" '
        f'xlink:href="data:image/png;base64,{b64}"/>'
        "</svg>"
    ).encode()
    result = SvgConverter().convert(svg)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    assert any(layer.layer_id.startswith("image-") for layer in layers)


def test_svg_line_drawing_routes_style_strokes_per_colour() -> None:
    """Schematic / line-art SVGs from every modern editor (Inkscape,
    browsers, KiCad) write colours in the CSS ``style`` attribute, not
    as presentation attributes. The post-processor used to read only
    ``element.get("fill")``, so every coloured stroke collapsed into a
    single black ``text`` layer and per-pen routing was impossible. The
    bucketer must now honour ``style="fill:none;stroke:#xxx"`` and emit
    one ``color-#xxxxxx`` layer per distinct stroke colour."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        b'<path d="M10 10 L100 10" style="fill:none;stroke:#ff0000"/>'
        b'<path d="M10 20 L100 20" style="fill:none;stroke:#0000ff"/>'
        b'<path d="M10 30 L100 30" style="fill:none;stroke:#00aa00"/>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    layers = {layer.layer_id: layer for layer in extract_layers(sanitize_svg(result.svg))}
    assert "color-#ff0000" in layers
    assert "color-#0000ff" in layers
    assert "color-#00aa00" in layers
    assert layers["color-#ff0000"].source_color.lower() in {"#ff0000", "ff0000"}


def test_svg_line_drawing_routes_bare_stroke_only_lines() -> None:
    """An element with an explicit ``stroke`` and no ``fill`` attribute
    (the form a hand-written or KiCad-style ``<line stroke="red"/>``
    takes) used to be bucketed as black because "no fill" defaulted to
    ``#000000``. Stroke-only line art now picks up its stroke colour as
    the routing key."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        b'<line x1="10" y1="10" x2="100" y2="10" stroke="red"/>'
        b'<line x1="10" y1="30" x2="100" y2="30" stroke="blue"/>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    layers = {layer.layer_id: layer for layer in extract_layers(sanitize_svg(result.svg))}
    # CSS named colours are canonicalised to ``#rrggbb`` so the bucket
    # key matches sibling elements that wrote the hex form directly and
    # the frontend swatch parser can resolve them.
    assert "color-#ff0000" in layers
    assert "color-#0000ff" in layers


def test_svg_style_property_preserves_url_data_url_semicolons() -> None:
    """``_style_property`` must not truncate ``url(data:image/png;base64,...)``
    values at the inner ``;`` — that semicolon is part of the value,
    not a declaration separator.
    """
    from pen_plotter.core.pdf_postprocess import _style_property

    style = "fill:url(data:image/png;base64,AAAA);stroke:#0000ff"
    assert _style_property(style, "fill") == "url(data:image/png;base64,AAAA)"
    assert _style_property(style, "stroke") == "#0000ff"


def test_svg_style_property_strips_css_important_token() -> None:
    """``fill:#ff0000 !important`` and ``fill:#ff0000`` must hit the
    same bucket — otherwise the operator sees duplicate colour layers
    for the same hex and per-pen routing fragments. The token sometimes
    appears unspaced (``#ff0000!important``) too.
    """
    from pen_plotter.core.pdf_postprocess import _style_property

    assert _style_property("fill:#ff0000 !important;stroke:none", "fill") == "#ff0000"
    assert _style_property("fill:#ff0000!important", "fill") == "#ff0000"
    assert _style_property("fill:red !important", "fill") == "red"


def test_svg_named_colours_canonicalised_to_hex() -> None:
    """``<line stroke='red'/>`` must produce ``color-#ff0000`` layer
    ids, not ``color-red`` — the frontend swatch / pen-routing pickers
    parse the suffix as a hex.
    """
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        b'<line x1="10" y1="10" x2="100" y2="10" stroke="red"/>'
        b'<line x1="10" y1="30" x2="100" y2="30" stroke="blue"/>'
        b'<line x1="10" y1="50" x2="100" y2="50" stroke="forestgreen"/>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    layers = {layer.layer_id: layer for layer in extract_layers(sanitize_svg(result.svg))}
    assert "color-#ff0000" in layers
    assert "color-#0000ff" in layers
    assert "color-#228b22" in layers


def test_svg_line_drawing_optimized_geometry_round_trips() -> None:
    """The geometry of a multi-colour line drawing must survive the
    full upload → sanitize → extract → optimize round-trip. Regression
    against the colour-routing fix: optimization shouldn't drop or
    duplicate strokes when per-colour layers are present."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        b'<path d="M10 10 L100 10 L100 100" style="fill:none;stroke:#ff0000"/>'
        b'<circle cx="150" cy="50" r="20" style="fill:none;stroke:#0000ff"/>'
        b"</svg>"
    )
    result = SvgConverter().convert(svg)
    clean = sanitize_svg(result.svg)
    layers = {layer.layer_id: layer for layer in extract_layers(clean)}
    assert "color-#ff0000" in layers
    assert "color-#0000ff" in layers
    # Round-trip through the optimizer.
    optimized = optimize_svg(clean)
    assert 'stroke="#ff0000"' in optimized.svg or 'stroke="#FF0000"' in optimized.svg
    assert 'stroke="#0000ff"' in optimized.svg or 'stroke="#0000FF"' in optimized.svg


@needs_gs
def test_eps_converter_preserves_text_after_postprocess() -> None:
    """EPS used to share the PDF bug — text wiped by sanitize, image dropped
    by vpype. The converter now runs the same post-processing chain."""
    eps = b"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 100 100
/Helvetica findfont 12 scalefont setfont
10 50 moveto (Hello) show
newpath 10 10 moveto 90 90 lineto stroke
showpage
"""
    result = EpsConverter().convert(eps)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    text_layer = next((layer for layer in layers if layer.layer_id == "text"), None)
    assert text_layer is not None
    assert text_layer.path_count > 1  # glyphs + the diagonal stroke
    assert text_layer.total_length_mm > 0.0
