import pytest

from pen_plotter.core.layers import extract_layers

LABELED = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
    '<g inkscape:label="color-ff0000" fill="#ff0000"><path d="M0 0 L1 1"/></g>'
    '<g inkscape:label="color-0000ff" stroke="#0000ff">'
    '<circle cx="1" cy="1" r="1"/><circle cx="2" cy="2" r="1"/></g>'
    "</svg>"
)

UNLABELED = '<svg xmlns="http://www.w3.org/2000/svg"><g><path d="M0 0 L1 1"/></g></svg>'


def test_extracts_labeled_groups_in_order() -> None:
    layers = extract_layers(LABELED)
    assert [layer.layer_id for layer in layers] == ["color-ff0000", "color-0000ff"]
    assert [layer.draw_order for layer in layers] == [0, 1]
    assert layers[0].source_color == "#ff0000"
    assert layers[1].source_color == "#0000ff"
    assert layers[1].path_count == 2


def test_unlabeled_svg_yields_single_layer() -> None:
    layers = extract_layers(UNLABELED)
    assert len(layers) == 1
    assert layers[0].layer_id == "layer-1"
    assert layers[0].path_count == 1


def test_invalid_svg_raises() -> None:
    with pytest.raises(ValueError):
        extract_layers("<svg><g></svg>")
