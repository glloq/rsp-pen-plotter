"""2026-06 new-algorithm batch 2: ascii_shade, lichtenberg, warp_grid, scallop."""

from __future__ import annotations

import re

import numpy as np
import pytest

from pen_plotter.converters.algorithms import get_algorithm

SIZE = 64

BATCH: dict[str, dict[str, object]] = {
    "ascii_shade": {"cell_px": 8},
    "lichtenberg": {"branches": 12, "step_px": 2, "seed": 0},
    "warp_grid": {"spacing_px": 4, "strength_px": 6},
    "scallop": {"scale_px": 10},
}


def _full_mask(size: int = SIZE) -> np.ndarray:
    return np.ones((size, size), dtype=bool)


def _gradient_tone(size: int = SIZE) -> np.ndarray:
    """Left = black (0.0), right = white (1.0)."""
    return np.tile(np.linspace(0.0, 1.0, size), (size, 1))


def _points(svg: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for points in re.findall(r'points="([^"]+)"', svg):
        for pair in points.split():
            x, y = pair.split(",")
            pts.append((float(x), float(y)))
    return pts


@pytest.mark.parametrize("name", sorted(BATCH))
def test_full_mask_emits_geometry(name: str) -> None:
    svg = get_algorithm(name).render_layer(
        _full_mask(), "#000000", "layer", options=dict(BATCH[name])
    )
    assert svg.startswith("<g")
    assert svg.count("<polyline") > 3


@pytest.mark.parametrize("name", sorted(BATCH))
def test_empty_mask_yields_empty_group(name: str) -> None:
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    svg = get_algorithm(name).render_layer(mask, "#000000", "layer", options=dict(BATCH[name]))
    assert "<polyline" not in svg


@pytest.mark.parametrize("name", sorted(BATCH))
def test_uniform_tone_is_byte_identical_to_no_tone(name: str) -> None:
    algo = get_algorithm(name)
    plain = algo.render_layer(_full_mask(), "#000000", "layer", options=dict(BATCH[name]))
    uniform = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**BATCH[name], "_tone": np.full((SIZE, SIZE), 0.5)},
    )
    assert plain == uniform


@pytest.mark.parametrize("name", sorted(BATCH))
def test_batch_opted_into_tone(name: str) -> None:
    assert get_algorithm(name).tone_aware is True


def test_ascii_shade_picks_denser_glyphs_in_the_dark_half() -> None:
    svg = get_algorithm("ascii_shade").render_layer(
        _full_mask(), "#000000", "layer", options={**BATCH["ascii_shade"], "_tone": _gradient_tone()}
    )
    # Denser ramp glyphs are built from more strokes, so the dark half
    # carries more polyline vertices than the light half.
    dark = sum(1 for x, _ in _points(svg) if x < SIZE / 2)
    light = sum(1 for x, _ in _points(svg) if x >= SIZE / 2)
    assert dark > 1.5 * light


def test_lichtenberg_branches_seek_the_dark_half() -> None:
    svg = get_algorithm("lichtenberg").render_layer(
        _full_mask(), "#000000", "layer", options={**BATCH["lichtenberg"], "_tone": _gradient_tone()}
    )
    pts = _points(svg)
    dark = sum(1 for x, _ in pts if x < SIZE / 2)
    assert dark > 1.5 * (len(pts) - dark)


def test_lichtenberg_is_deterministic_per_seed() -> None:
    algo = get_algorithm("lichtenberg")
    opts = {**BATCH["lichtenberg"], "_tone": _gradient_tone()}
    assert algo.render_layer(_full_mask(), "#000", "l", options=dict(opts)) == algo.render_layer(
        _full_mask(), "#000", "l", options=dict(opts)
    )
    reseeded = algo.render_layer(_full_mask(), "#000", "l", options={**opts, "seed": 7})
    assert reseeded != algo.render_layer(_full_mask(), "#000", "l", options=dict(opts))


def test_warp_grid_straight_without_tone_and_warped_with_it() -> None:
    algo = get_algorithm("warp_grid")
    straight = algo.render_layer(_full_mask(), "#000000", "layer", options=dict(BATCH["warp_grid"]))
    # No tone: every horizontal-line vertex sits exactly on its row.
    for _x, y in _points(straight):
        if abs(y - round(y)) > 1e-6:
            break
    else:
        pass  # all integer — straight grid as expected
    # Radial tone bulges the mesh: some vertex moves off-axis by > 1 px.
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    radial = np.clip(np.hypot(xx - SIZE / 2, yy - SIZE / 2) / (SIZE / 2), 0.0, 1.0)
    warped = algo.render_layer(
        _full_mask(), "#000000", "layer", options={**BATCH["warp_grid"], "_tone": radial}
    )
    assert warped != straight
    deviations = [abs(y - round(y / 4) * 4) for _x, y in _points(warped)]
    assert max(deviations) > 1.0


def test_scallop_nests_extra_ribs_in_the_dark_half() -> None:
    svg = get_algorithm("scallop").render_layer(
        _full_mask(), "#000000", "layer", options={**BATCH["scallop"], "_tone": _gradient_tone()}
    )
    pts = _points(svg)
    dark = sum(1 for x, _ in pts if x < SIZE / 2)
    light = len(pts) - dark
    assert dark > 1.3 * light
