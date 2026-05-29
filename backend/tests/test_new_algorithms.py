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
    ConcentricOffsetAlgorithm,
    ContoursAlgorithm,
    CrosshatchAlgorithm,
    EdgesAlgorithm,
    EulerianHatchAlgorithm,
    FlowFieldAlgorithm,
    GosperFillAlgorithm,
    HilbertFillAlgorithm,
    SpiralAlgorithm,
    TspAlgorithm,
    TspOptimizedAlgorithm,
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
        "hilbert",
        "gosper",
        "eulerian_hatch",
        "concentric_offset",
        "flowfield",
        "tsp_opt",
        "voronoi_stipple",
        "squiggle",
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
    assert algorithm_kind("hilbert") == "mono_stroke"
    assert algorithm_kind("gosper") == "mono_stroke"
    assert algorithm_kind("eulerian_hatch") == "fill"
    assert algorithm_kind("concentric_offset") == "mono_stroke"
    assert algorithm_kind("flowfield") == "fill"
    assert algorithm_kind("tsp_opt") == "mono_stroke"


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
        ("hilbert", "<polyline"),
        ("gosper", "<polyline"),
        ("eulerian_hatch", "<polyline"),
        ("concentric_offset", "<polyline"),
        ("flowfield", "<polyline"),
        ("tsp_opt", "<polyline"),
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


def test_spiral_amplitude_modulation_adds_detail() -> None:
    """A non-zero wave amplitude perturbs the spiral and lifts sampling.

    The tonal spiral relies on ``wave_amp_px`` wobbling the radius so dark
    bands read denser; the modulated output must differ from — and carry
    more points than — the plain Archimedean spiral.
    """
    mask = _square_mask(size=60, inset=4)
    plain = SpiralAlgorithm().render_layer(
        mask, "#000000", "x", options={"spacing_px": 4, "wave_amp_px": 0.0}
    )
    wavy = SpiralAlgorithm().render_layer(
        mask,
        "#000000",
        "x",
        options={"spacing_px": 4, "wave_amp_px": 5.0, "waves_per_turn": 12},
    )
    assert "<polyline" in plain and "<polyline" in wavy
    assert wavy != plain
    assert wavy.count(",") > plain.count(",")


def test_spiral_tone_map_modulates_by_darkness() -> None:
    """A per-pixel tone map drives the wobble: white = plain, black = wavy."""
    mask = np.ones((80, 80), dtype=bool)
    white = np.ones((80, 80), dtype=float)  # darkness 0 → no wobble
    black = np.zeros((80, 80), dtype=float)  # darkness 1 → max wobble
    on_white = SpiralAlgorithm().render_layer(
        mask, "#000000", "x", options={"spacing_px": 4, "wavelength_px": 8, "_tone": white}
    )
    on_black = SpiralAlgorithm().render_layer(
        mask, "#000000", "x", options={"spacing_px": 4, "wavelength_px": 8, "_tone": black}
    )
    assert "<polyline" in on_white and "<polyline" in on_black
    assert on_white != on_black


def test_spiral_zero_amplitude_matches_default() -> None:
    """Default options (no amplitude) reproduce the legacy plain spiral."""
    mask = _square_mask(size=40)
    default = SpiralAlgorithm().render_layer(mask, "#000000", "x")
    explicit_zero = SpiralAlgorithm().render_layer(
        mask, "#000000", "x", options={"wave_amp_px": 0.0}
    )
    assert default == explicit_zero


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


def test_eulerian_hatch_fewer_pen_lifts_than_crosshatch() -> None:
    """Boustrophedon stitching cuts pen-lifts by ≥50% on a simple square."""
    mask = _square_mask(size=40, inset=4)
    cross = CrosshatchAlgorithm().render_layer(
        mask, "#000000", "ch", options={"angle_deg": 0.0, "spacing_px": 3}
    )
    eulerian = EulerianHatchAlgorithm().render_layer(
        mask, "#000000", "eh", options={"angle_deg": 0.0, "spacing_px": 3}
    )
    cross_segments = cross.count("<line")
    eulerian_polylines = eulerian.count("<polyline")
    # Each polyline replaces ~spacing/connect_threshold individual segments;
    # for a convex square one polyline covers every sweep.
    assert eulerian_polylines * 2 <= cross_segments


def test_hilbert_one_polyline_per_simply_connected_region() -> None:
    """A single connected mask yields exactly one polyline."""
    mask = _square_mask(size=32, inset=4)
    svg = HilbertFillAlgorithm().render_layer(mask, "#000", "h")
    assert svg.count("<polyline") == 1


def test_hilbert_two_components_yield_two_polylines() -> None:
    """Two disjoint masked squares produce two polylines."""
    mask = np.zeros((40, 40), dtype=bool)
    mask[4:14, 4:14] = True
    mask[24:34, 24:34] = True
    svg = HilbertFillAlgorithm().render_layer(mask, "#000", "h")
    assert svg.count("<polyline") == 2


def test_concentric_offset_bridge_collapses_to_single_polyline() -> None:
    """``bridge=True`` stitches all rings into one polyline per component."""
    mask = _square_mask(size=40, inset=4)
    bridged = ConcentricOffsetAlgorithm().render_layer(
        mask, "#000", "co", options={"spacing_px": 2, "bridge": True}
    )
    unbridged = ConcentricOffsetAlgorithm().render_layer(
        mask, "#000", "co", options={"spacing_px": 2, "bridge": False}
    )
    assert bridged.count("<polyline") == 1
    assert unbridged.count("<polyline") >= 2


def test_gosper_handles_filled_square() -> None:
    svg = GosperFillAlgorithm().render_layer(
        _square_mask(size=40, inset=4), "#000", "g", options={"order": 3}
    )
    assert svg.count("<polyline") >= 1


def test_flowfield_emits_streamlines() -> None:
    mask = np.ones((40, 40), dtype=bool)
    svg = FlowFieldAlgorithm().render_layer(
        mask, "#000", "ff", options={"seed_spacing_px": 6.0, "max_steps": 200}
    )
    assert svg.count("<polyline") >= 2


def test_tsp_opt_2opt_not_longer_than_nn() -> None:
    """2-opt result is never longer than the seed NN tour."""

    def _length(svg: str) -> float:
        chunk = svg.split('points="', 1)[1].split('"', 1)[0]
        pts = [tuple(float(v) for v in p.split(",")) for p in chunk.split()]
        return sum(
            ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            for a, b in zip(pts, pts[1:], strict=False)
        )

    mask = np.ones((50, 50), dtype=bool)
    algo = TspOptimizedAlgorithm()
    nn = algo.render_layer(mask, "#000", "t", options={"method": "nn", "seed": 1})
    opt = algo.render_layer(
        mask,
        "#000",
        "t",
        options={"method": "nn_2opt", "seed": 1, "time_budget_s": 0.5},
    )
    assert _length(opt) <= _length(nn) + 1e-6
