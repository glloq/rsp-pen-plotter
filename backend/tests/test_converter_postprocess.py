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

needs_gs = pytest.mark.skipif(
    shutil.which("gs") is None, reason="ghostscript not installed"
)


def test_dxf_postprocess_strips_background_rect() -> None:
    """The ezdxf background <rect> would otherwise plot as a giant frame."""
    raw = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">'
        '<defs><style>.C1 {stroke: #ff0000; fill: none;}</style></defs>'
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
        '<defs><style>'
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
        assert layer.layer_id.startswith("color-"), (
            f"layer {layer.layer_id} should be color-keyed"
        )
        assert layer.path_count > 0, f"layer {layer.layer_id} is empty"

    optimized = optimize_svg(clean)
    assert optimized.svg.count("<path") >= 1, "vpype should produce drawable paths"


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
    assert any(l.layer_id == "grid" for l in layers)
    grid = next(l for l in layers if l.layer_id == "grid")
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
    assert any(l.layer_id.startswith("image-") for l in layers)


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
    text_layer = next((l for l in layers if l.layer_id == "text"), None)
    assert text_layer is not None
    assert text_layer.path_count > 1  # glyphs + the diagonal stroke
    assert text_layer.total_length_mm > 0.0
