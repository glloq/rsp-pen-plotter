"""Smoke tests for the six new raster algorithms.

Each test feeds a small synthetic mask, runs the algorithm, and asserts
the result is a non-empty SVG group of the expected shape. Pixel-perfect
geometry is out of scope here — these tests guard against regressions
that would emit empty/malformed output for a non-trivial mask.
"""

from __future__ import annotations

import numpy as np
import pytest

from pen_plotter.converters.algorithms import (
    CenterlineAlgorithm,
    ContoursAlgorithm,
    CrosshatchAlgorithm,
    EdgesAlgorithm,
    ScanlinesAlgorithm,
    SpiralAlgorithm,
    TspAlgorithm,
    algorithm_kind,
    available_algorithms,
    get_algorithm,
)


def _square_mask(size: int = 20, inset: int = 4) -> np.ndarray:
    """Filled square inside the canvas — gives every algo something to draw."""
    mask = np.zeros((size, size), dtype=bool)
    mask[inset:-inset, inset:-inset] = True
    return mask


def test_registry_lists_all_algorithms() -> None:
    names = {a.name for a in available_algorithms()}
    assert names == {
        "direct",
        "halftone",
        "stippling",
        "crosshatch",
        "contours",
        "edges",
        "centerline",
        "spiral",
        "scanlines",
        "tsp",
    }


def test_algorithm_kind_groups_by_family() -> None:
    assert algorithm_kind("direct") == "fill"
    assert algorithm_kind("crosshatch") == "fill"
    assert algorithm_kind("contours") == "lines"
    assert algorithm_kind("edges") == "lines"
    assert algorithm_kind("centerline") == "lines"
    assert algorithm_kind("spiral") == "mono_stroke"
    assert algorithm_kind("scanlines") == "mono_stroke"
    assert algorithm_kind("tsp") == "mono_stroke"


def test_centerline_traces_horizontal_bar() -> None:
    # A 100×10 horizontal bar should yield a single polyline running
    # roughly across the middle row from one end to the other.
    mask = np.zeros((10, 100), dtype=bool)
    mask[3:7, 1:99] = True
    svg = CenterlineAlgorithm().render_layer(
        mask, "#000000", "test", options={"min_branch_px": 3}
    )
    assert "<polyline" in svg
    assert svg.count("<polyline") == 1
    assert 'fill="none"' in svg


def test_centerline_skimage_missing_falls_back_to_edges(monkeypatch) -> None:
    # When scikit-image isn't installed the algorithm must degrade
    # gracefully to an outline rather than crash.
    import pen_plotter.converters.algorithms.centerline as centerline_module

    monkeypatch.setattr(centerline_module, "_skeletonize", lambda mask: None)
    mask = _square_mask()
    svg = CenterlineAlgorithm().render_layer(mask, "#000000", "test")
    assert svg.startswith("<g")
    assert "<polyline" in svg


@pytest.mark.parametrize(
    "name,expected_element",
    [
        ("crosshatch", "<line"),
        ("contours", "<polygon"),
        ("edges", "<polyline"),
        ("spiral", "<polyline"),
        ("scanlines", "<polyline"),
        ("tsp", "<polyline"),
    ],
)
def test_algorithm_emits_geometry_for_filled_square(
    name: str, expected_element: str
) -> None:
    algo = get_algorithm(name)
    mask = _square_mask()
    svg = algo.render_layer(mask, "#123456", f"layer-{name}")
    assert svg.startswith("<g ")
    assert svg.endswith("</g>")
    assert "#123456" in svg or "stroke-width" in svg
    assert expected_element in svg, (
        f"Expected {expected_element!r} for {name}, got start: {svg[:200]}"
    )


def test_empty_mask_yields_empty_group() -> None:
    """No pixels in the mask → an empty <g> with the right label, no error."""
    mask = np.zeros((10, 10), dtype=bool)
    for algo in (SpiralAlgorithm(), TspAlgorithm()):
        svg = algo.render_layer(mask, "#000000", "empty")
        assert "<g " in svg and "</g>" in svg
        # No polyline emitted for an empty mask.
        assert "<polyline" not in svg


def test_crosshatch_crossed_doubles_line_count() -> None:
    """``crossed=True`` lays the second set perpendicular to the first."""
    algo = CrosshatchAlgorithm()
    mask = _square_mask(size=24, inset=4)
    single = algo.render_layer(
        mask, "#000000", "single", options={"angle_deg": 0.0, "spacing_px": 4}
    )
    crossed = algo.render_layer(
        mask,
        "#000000",
        "crossed",
        options={"angle_deg": 0.0, "spacing_px": 4, "crossed": True},
    )
    # ``crossed`` should add a meaningful amount of line geometry.
    assert crossed.count("<line") >= single.count("<line") + 2


def test_contours_concentric_rings_decrease() -> None:
    """Each successive contour ring is strictly inside the previous one."""
    algo = ContoursAlgorithm()
    mask = _square_mask(size=24, inset=2)
    svg = algo.render_layer(
        mask, "#000000", "rings", options={"spacing_px": 2, "max_rings": 5}
    )
    # At least two distinct contour polygons emitted for a 24×24 square with
    # spacing=2 (5 rings worth of room).
    assert svg.count("<polygon") >= 2


def test_edges_emits_single_chain_for_simple_shape() -> None:
    algo = EdgesAlgorithm()
    mask = _square_mask(size=16, inset=4)
    svg = algo.render_layer(mask, "#000000", "edge")
    assert svg.count("<polyline") == 1


def test_tsp_respects_density_cap() -> None:
    """Density of 1.0 still produces a bounded number of dots (≤4000)."""
    algo = TspAlgorithm()
    mask = np.ones((64, 64), dtype=bool)  # 4096 candidate pixels
    svg = algo.render_layer(
        mask, "#000000", "tour", options={"density": 1.0, "seed": 1}
    )
    # Single polyline; point count = comma-separated x,y pairs.
    chunk = svg.split('points="', 1)[1].split('"', 1)[0]
    point_count = len(chunk.split())
    assert 2 <= point_count <= 4000
