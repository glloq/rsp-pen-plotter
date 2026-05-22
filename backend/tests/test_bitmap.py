import shutil

import numpy as np
import pytest

from pen_plotter.converters.algorithms import available_algorithms, get_algorithm
from pen_plotter.converters.bitmap import BitmapConverter

needs_potrace = pytest.mark.skipif(
    shutil.which("potrace") is None, reason="potrace binary not installed"
)


def _square_mask() -> np.ndarray:
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:30, 10:30] = True
    return mask


def test_registered_algorithm_names() -> None:
    names = {algo.name for algo in available_algorithms()}
    assert names == {"direct", "halftone", "stippling"}


def test_get_unknown_algorithm_raises() -> None:
    with pytest.raises(KeyError):
        get_algorithm("nope")


def test_halftone_emits_dots_inside_region() -> None:
    group = get_algorithm("halftone").render_layer(_square_mask(), "#ff0000", "red")
    assert 'inkscape:label="red"' in group
    assert group.count("<circle") > 0


def test_stippling_is_deterministic() -> None:
    algo = get_algorithm("stippling")
    a = algo.render_layer(_square_mask(), "#ff0000", "red", options={"density": 0.1, "seed": 7})
    b = algo.render_layer(_square_mask(), "#ff0000", "red", options={"density": 0.1, "seed": 7})
    assert a == b
    assert a.count("<circle") > 0


def test_empty_mask_yields_empty_group() -> None:
    empty = np.zeros((20, 20), dtype=bool)
    group = get_algorithm("halftone").render_layer(empty, "#000000", "k")
    assert "<circle" not in group


@needs_potrace
def test_direct_traces_region_to_path() -> None:
    group = get_algorithm("direct").render_layer(_square_mask(), "#ff0000", "red")
    assert "<path" in group
    assert 'fill="#ff0000"' in group
    assert 'inkscape:label="red"' in group


@needs_potrace
def test_bitmap_converter_produces_layered_svg(two_color_png: bytes) -> None:
    result = BitmapConverter().convert(two_color_png, options={"algorithm": "direct"})
    assert result.source_mime == "image/svg+xml"
    assert result.svg.startswith("<svg")
    # White background dropped; the red square remains as one layer.
    assert result.svg.count("<g ") == 1
    assert "ff0000" in result.svg.lower() or "dc1414" in result.svg.lower()


def test_bitmap_converter_halftone_no_potrace_needed(two_color_png: bytes) -> None:
    result = BitmapConverter().convert(
        two_color_png, options={"algorithm": "halftone", "num_colors": 2}
    )
    assert "<circle" in result.svg


def test_bitmap_converter_rejects_unknown_algorithm(two_color_png: bytes) -> None:
    with pytest.raises(KeyError):
        BitmapConverter().convert(two_color_png, options={"algorithm": "bogus"})
