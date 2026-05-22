from pen_plotter.core.layers import extract_layers
from pen_plotter.core.toolpath import LayerOptimization, optimize_svg

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
