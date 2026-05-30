"""Pen-width plumbing: algorithms honour the injected ``stroke_width``.

The frontend converts each colour's physical ``stroke_width_mm`` into the
layer's viewBox units and injects it as ``stroke_width`` in the algorithm
options. Algorithms must then (a) emit that width as the group's
``stroke-width`` and (b) floor their fill spacing at one pen width so the
strokes never overlap unintentionally.
"""

from __future__ import annotations

import numpy as np

from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.algorithms._style import (
    floored_spacing,
    pen_width_px,
    stroke_attr_px,
)


def test_style_helpers() -> None:
    assert pen_width_px(None) is None
    assert pen_width_px({}) is None
    assert pen_width_px({"stroke_width": 0}) is None
    assert pen_width_px({"stroke_width": "bad"}) is None
    assert pen_width_px({"stroke_width": 2.5}) == 2.5

    # Stroke falls back to the historical default when no pen is injected.
    assert stroke_attr_px(None) == 0.8
    assert stroke_attr_px({"stroke_width": 3.0}) == 3.0

    # Spacing floor: pen width is a minimum, wider spacing is preserved.
    assert floored_spacing(4.0, {"stroke_width": 2.0}) == 4.0
    assert floored_spacing(2.0, {"stroke_width": 6.0}) == 6.0
    assert floored_spacing(2.0, None) == 2.0


def _solid_mask(size: int = 60) -> np.ndarray:
    return np.ones((size, size), dtype=bool)


def test_crosshatch_emits_injected_stroke_width() -> None:
    algo = get_algorithm("crosshatch")
    mask = _solid_mask()
    default_svg = algo.render_layer(mask, "#123456", "color-123456", options={})
    assert 'stroke-width="0.800"' in default_svg

    wide = algo.render_layer(
        mask, "#123456", "color-123456", options={"stroke_width": 3.0}
    )
    assert 'stroke-width="3.000"' in wide


def test_scanlines_spacing_floored_by_pen_width() -> None:
    # Tight spacing + a fat pen → the floor kicks in and the layer ends up
    # with strictly fewer scan lines than the un-floored render.
    algo = get_algorithm("scanlines")
    mask = _solid_mask()
    dense = algo.render_layer(mask, "#000000", "l", options={"spacing_px": 2})
    floored = algo.render_layer(
        mask, "#000000", "l", options={"spacing_px": 2, "stroke_width": 20.0}
    )
    assert floored.count("<polyline") < dense.count("<polyline")
    assert 'stroke-width="20.000"' in floored
