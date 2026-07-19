from pen_plotter.core.layers import extract_layers
from pen_plotter.core.toolpath import LayerOptimization, optimize_geometry_ir, optimize_svg
from pen_plotter.domain.ir.adapter import content_sha256, geometry_ir_from_svg

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)

# Two short segments with a large gap between them: sorting can reduce travel.
TWO_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000">'
    '<path d="M0 0 L10 0"/><path d="M90 0 L100 0"/><path d="M10 0 L90 0"/></g>'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M0 50 L100 50"/></g>'
    "</svg>"
)


def test_optimize_preserves_labels_and_colors() -> None:
    result = optimize_svg(TWO_LAYERS)
    assert 'inkscape:label="red"' in result.svg
    assert 'inkscape:label="blue"' in result.svg
    assert "#ff0000" in result.svg
    layers = extract_layers(result.svg)
    assert [layer.layer_id for layer in layers] == ["red", "blue"]


def test_optimize_reduces_or_keeps_travel() -> None:
    result = optimize_svg(TWO_LAYERS)
    assert result.metrics.pen_up_after_mm <= result.metrics.pen_up_before_mm
    assert 0.0 <= result.metrics.reduction_pct <= 100.0


def test_optimize_respects_disabled_layer() -> None:
    settings = [
        LayerOptimization(layer_id="red", optimize=False),
        LayerOptimization(layer_id="blue", optimize=True),
    ]
    result = optimize_svg(TWO_LAYERS, layers=settings)
    # Still produces both layers.
    assert 'inkscape:label="red"' in result.svg
    assert 'inkscape:label="blue"' in result.svg


def test_optimize_invalid_svg_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        optimize_svg("<svg><g></svg>")


def test_optimize_geometry_ir_round_trip_preserves_layers() -> None:
    """The first v0.2 IR consumer: feed a ``GeometryIR`` to the
    optimizer and verify the layered output matches the SVG path."""
    geometry = geometry_ir_from_svg(TWO_LAYERS, source_hash=content_sha256(b"x"))
    result = optimize_geometry_ir(geometry)
    assert 'inkscape:label="red"' in result.svg
    assert 'inkscape:label="blue"' in result.svg
    assert result.metrics.pen_up_after_mm <= result.metrics.pen_up_before_mm


# Three circles in a triangle whose seams (svgelements starts a circle at
# its rightmost point) all sit away from the shortest tour. A collinear
# row would be seam-invariant; the 2-D arrangement makes seam rotation
# strictly better than any reordering of fixed-seam loops.
CLOSED_LOOPS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="ink" stroke="#000000">'
    '<circle cx="20" cy="20" r="5"/>'
    '<circle cx="60" cy="20" r="5"/>'
    '<circle cx="40" cy="60" r="5"/>'
    "</g></svg>"
)


def test_optimize_rotates_closed_loop_seams() -> None:
    """Seam rotation (default on) beats fixed seams on closed loops."""
    rotated = optimize_svg(CLOSED_LOOPS)
    fixed = optimize_svg(
        CLOSED_LOOPS, layers=[LayerOptimization(layer_id="ink", seam_rotation=False)]
    )
    assert rotated.metrics.pen_up_after_mm < fixed.metrics.pen_up_after_mm
    assert rotated.metrics.pen_up_after_mm <= rotated.metrics.pen_up_before_mm


def test_optimize_seam_rotation_keeps_loops_closed() -> None:
    """Rotated loops still start and end on the same point in the output."""
    from pen_plotter.core.toolpath import _doc_from_svg

    result = optimize_svg(CLOSED_LOOPS)
    doc = _doc_from_svg(result.svg)
    lines = [line for layer in doc.layers.values() for line in layer]
    assert len(lines) == 3
    for line in lines:
        assert abs(line[0] - line[-1]) < 1e-6


def test_optimize_does_not_early_exit_on_circle_only_layer() -> None:
    """Regression: a mono-layer drawing made of ``<circle>`` dots must optimize.

    The single-path early-exit counted only path/polyline/polygon/line, so
    a single-layer stippling / halftone / circle_pack render (dots are
    ``<circle>`` elements) was returned untouched — in raw generation
    order, with zeroed metrics. Three circles across the canvas must
    yield non-zero pen-up metrics, proof the vpype pipeline actually ran.
    """
    result = optimize_svg(CLOSED_LOOPS)
    assert result.metrics.pen_up_before_mm > 0.0
