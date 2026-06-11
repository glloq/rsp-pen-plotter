"""Tonal upgrade of the classic fill algorithms (audit-fix batch 2026-06).

Every shaded monochrome master used to go flat at the default single
luminance band when its algorithm ignored the injected ``_tone`` map.
These tests pin the new contract for the upgraded algorithms:

- a left-dark -> right-light gradient must produce more ink (or denser
  geometry) in the dark half than in the light half;
- a *uniform* tone map must leave the output byte-identical to a render
  without any tone map (the ``tone_darkness`` helper returns ``None``
  below its contrast floor), so flat fills and multicolour cluster
  regions keep rendering exactly as before the upgrade.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.algorithms._style import tone_darkness

SIZE = 64

# All algorithms upgraded in this batch, with fast render options.
TONAL_BATCH: dict[str, dict[str, object]] = {
    "crosshatch": {"spacing_px": 4},
    "eulerian_hatch": {"spacing_px": 4},
    "scribble": {"spacing_px": 4, "amp_px": 1.0, "overshoot_px": 1.0},
    "halftone": {"cell_size_px": 4},
    "stippling": {"density": 0.05},
    "lowpoly": {"density": 0.02},
    "scanlines": {"spacing_px": 4, "wave_amp_px": 1.5, "wave_period_px": 8},
    "squiggle": {"spacing_px": 4, "amp_px": 1.5, "period_px": 8},
    "gosper": {"order": 4, "spacing_px": 3},
    "concentric_offset": {"spacing_px": 3, "max_rings": 20},
    "contours": {"spacing_px": 3, "max_rings": 10},
    "tsp_opt": {"density": 0.05, "method": "nn"},
}


def _full_mask(size: int = SIZE) -> np.ndarray:
    return np.ones((size, size), dtype=bool)


def _gradient_tone(size: int = SIZE) -> np.ndarray:
    """Left = black (0.0), right = white (1.0)."""
    return np.tile(np.linspace(0.0, 1.0, size), (size, 1))


def _coords(svg: str) -> list[tuple[float, float]]:
    """Every (x, y) coordinate appearing in the group's geometry."""
    pts: list[tuple[float, float]] = []
    for x, y in re.findall(r'x1="([\d.e+-]+)" y1="([\d.e+-]+)"', svg):
        pts.append((float(x), float(y)))
    for x, y in re.findall(r'x2="([\d.e+-]+)" y2="([\d.e+-]+)"', svg):
        pts.append((float(x), float(y)))
    for x, y in re.findall(r'cx="([\d.e+-]+)" cy="([\d.e+-]+)"', svg):
        pts.append((float(x), float(y)))
    for points in re.findall(r'points="([^"]+)"', svg):
        for pair in points.split():
            x, y = pair.split(",")
            pts.append((float(x), float(y)))
    return pts


def _half_counts(svg: str, mid: float = SIZE / 2) -> tuple[int, int]:
    pts = _coords(svg)
    dark = sum(1 for x, _ in pts if x < mid)
    light = sum(1 for x, _ in pts if x >= mid)
    return dark, light


# ---------------------------------------------------------------------------
# Helper contract
# ---------------------------------------------------------------------------


def test_tone_darkness_none_without_map() -> None:
    assert tone_darkness(_full_mask(), {}) is None
    assert tone_darkness(_full_mask(), None) is None


def test_tone_darkness_none_for_uniform_region() -> None:
    assert tone_darkness(_full_mask(), {"_tone": np.full((SIZE, SIZE), 0.5)}) is None


def test_tone_darkness_none_for_wrong_shape() -> None:
    assert tone_darkness(_full_mask(), {"_tone": np.zeros((3, 3))}) is None


def test_tone_darkness_normalises_gradient() -> None:
    dn = tone_darkness(_full_mask(), {"_tone": _gradient_tone()})
    assert dn is not None
    # Darkest (left) column ~1, lightest (right) ~0.
    assert float(dn[:, 1].mean()) > 0.95
    assert float(dn[:, -2].mean()) < 0.05


# ---------------------------------------------------------------------------
# Uniform tone == no tone (legacy invariance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(TONAL_BATCH))
def test_uniform_tone_is_byte_identical_to_no_tone(name: str) -> None:
    algo = get_algorithm(name)
    opts = dict(TONAL_BATCH[name])
    plain = algo.render_layer(_full_mask(), "#000000", "layer", options=dict(opts))
    uniform = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**opts, "_tone": np.full((SIZE, SIZE), 0.5)},
    )
    assert plain == uniform


@pytest.mark.parametrize("name", sorted(TONAL_BATCH))
def test_tonal_batch_opted_into_tone(name: str) -> None:
    assert get_algorithm(name).tone_aware is True


# ---------------------------------------------------------------------------
# Gradient: dark half must carry more geometry than the light half
# ---------------------------------------------------------------------------

# Algorithms whose tonal response is density / presence — countable by
# comparing coordinate counts per half. The remaining algorithms
# (scanlines, squiggle, concentric_offset) modulate amplitude instead
# and get dedicated assertions below.
_DENSITY_ALGOS = [
    "crosshatch",
    "eulerian_hatch",
    "scribble",
    "stippling",
    "lowpoly",
    "gosper",
    "tsp_opt",
    "contours",
]


@pytest.mark.parametrize("name", _DENSITY_ALGOS)
def test_gradient_packs_geometry_into_dark_half(name: str) -> None:
    algo = get_algorithm(name)
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH[name], "_tone": _gradient_tone()},
    )
    dark, light = _half_counts(svg)
    assert dark > light, f"{name}: dark={dark} light={light}"


def test_crosshatch_gradient_leaves_highlights_blank() -> None:
    algo = get_algorithm("crosshatch")
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH["crosshatch"], "angle_deg": 0, "_tone": _gradient_tone()},
    )
    # With angle 0 every stroke is horizontal: x2 marks where the hatch
    # stops. The lightest ~8% (right edge) must stay unhatched.
    ends = [float(x) for x in re.findall(r'x2="([\d.e+-]+)"', svg)]
    assert ends and max(ends) < SIZE - 1


def test_halftone_gradient_grows_dots_in_dark_half() -> None:
    algo = get_algorithm("halftone")
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH["halftone"], "_tone": _gradient_tone()},
    )
    dots = [
        (float(cx), float(r))
        for cx, r in re.findall(r'cx="([\d.e+-]+)" cy="[\d.e+-]+" r="([\d.e+-]+)"', svg)
    ]
    assert dots
    dark = [r for cx, r in dots if cx < SIZE / 2]
    light = [r for cx, r in dots if cx >= SIZE / 2]
    assert dark and sum(dark) / len(dark) > (sum(light) / len(light) if light else 0.0)


def _row_deviation_by_half(svg: str, spacing: int) -> tuple[float, float]:
    """Mean |y - nearest row| per half — the wave amplitude signature."""
    dark: list[float] = []
    light: list[float] = []
    for x, y in _coords(svg):
        dev = abs(y - round(y / spacing) * spacing)
        (dark if x < SIZE / 2 else light).append(dev)
    return (
        sum(dark) / max(1, len(dark)),
        sum(light) / max(1, len(light)),
    )


def test_scanlines_gradient_swings_harder_in_dark_half() -> None:
    algo = get_algorithm("scanlines")
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH["scanlines"], "_tone": _gradient_tone()},
    )
    dark_dev, light_dev = _row_deviation_by_half(svg, 4)
    assert dark_dev > 2.0 * light_dev


def test_squiggle_gradient_swings_harder_in_dark_half() -> None:
    algo = get_algorithm("squiggle")
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH["squiggle"], "_tone": _gradient_tone()},
    )
    dark_dev, light_dev = _row_deviation_by_half(svg, 4)
    assert dark_dev > 1.5 * light_dev


def test_concentric_offset_gradient_wobbles_dark_side() -> None:
    algo = get_algorithm("concentric_offset")
    opts = TONAL_BATCH["concentric_offset"]
    plain = algo.render_layer(_full_mask(), "#000000", "layer", options=dict(opts))
    tonal = algo.render_layer(
        _full_mask(), "#000000", "layer", options={**opts, "_tone": _gradient_tone()}
    )
    assert tonal != plain
    assert "<polyline" in tonal
    # The wobble displaces ring points; rings on the dark side must move
    # while the light side stays close to the clean rings.
    plain_pts = np.asarray(_coords(plain))
    tonal_pts = np.asarray(_coords(tonal))
    assert plain_pts.shape == tonal_pts.shape
    delta = np.hypot(*(tonal_pts - plain_pts).T)
    dark = delta[plain_pts[:, 0] < SIZE / 2]
    light = delta[plain_pts[:, 0] >= SIZE / 2]
    assert float(dark.mean()) > 2.0 * float(light.mean())


def test_contours_gradient_traces_luminance_isolines() -> None:
    algo = get_algorithm("contours")
    opts = TONAL_BATCH["contours"]
    tonal = algo.render_layer(
        _full_mask(), "#000000", "layer", options={**opts, "_tone": _gradient_tone()}
    )
    # 10 levels over a full-range gradient -> several distinct isolines,
    # all bounded away from the light edge.
    assert tonal.count("<polygon") >= 3


def test_gosper_gradient_blanks_the_lightest_strip() -> None:
    algo = get_algorithm("gosper")
    svg = algo.render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={**TONAL_BATCH["gosper"], "_tone": _gradient_tone()},
    )
    xs = [x for x, _ in _coords(svg)]
    assert xs and max(xs) < SIZE - 2
