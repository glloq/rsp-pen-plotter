"""Sine-wave halftone — tone-driven frequency-modulated rows."""

from __future__ import annotations

import re

import numpy as np

from pen_plotter.converters.algorithms.sine_halftone import SineHalftoneAlgorithm

SIZE = 64
OPTS = {"spacing_px": 4, "amp_px": 1.5, "period_px": 4}


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


def test_full_mask_emits_wave_rows() -> None:
    svg = SineHalftoneAlgorithm().render_layer(_full_mask(), "#000000", "layer", options=dict(OPTS))
    assert svg.startswith("<g")
    assert svg.count("<polyline") >= SIZE // 4 - 1


def test_empty_mask_yields_empty_group() -> None:
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    svg = SineHalftoneAlgorithm().render_layer(mask, "#000000", "layer", options=dict(OPTS))
    assert "<polyline" not in svg


def test_uniform_tone_is_byte_identical_to_no_tone() -> None:
    algo = SineHalftoneAlgorithm()
    plain = algo.render_layer(_full_mask(), "#000000", "layer", options=dict(OPTS))
    uniform = algo.render_layer(
        _full_mask(), "#000000", "layer", options={**OPTS, "_tone": np.full((SIZE, SIZE), 0.5)}
    )
    assert plain == uniform


def test_gradient_swings_and_buzzes_in_the_dark_half() -> None:
    svg = SineHalftoneAlgorithm().render_layer(
        _full_mask(), "#000000", "layer", options={**OPTS, "_tone": _gradient_tone()}
    )
    dark_dev: list[float] = []
    light_dev: list[float] = []
    for x, y in _points(svg):
        dev = abs(y - round(y / 4) * 4)
        (dark_dev if x < SIZE / 2 else light_dev).append(dev)
    # Amplitude follows darkness: the dark half swings much harder.
    assert sum(dark_dev) / len(dark_dev) > 2.0 * (sum(light_dev) / len(light_dev))


def test_gradient_modulates_frequency_not_just_amplitude() -> None:
    svg = SineHalftoneAlgorithm().render_layer(
        _full_mask(), "#000000", "layer", options={**OPTS, "_tone": _gradient_tone()}
    )
    # Count local extrema (direction changes of dy) per half: higher
    # frequency in the dark half means more oscillations over the same
    # horizontal distance.
    dark = light = 0
    for poly in re.findall(r'points="([^"]+)"', svg):
        ys = []
        xs = []
        for pair in poly.split():
            x, y = pair.split(",")
            xs.append(float(x))
            ys.append(float(y))
        for k in range(1, len(ys) - 1):
            if (ys[k] - ys[k - 1]) * (ys[k + 1] - ys[k]) < 0:
                if xs[k] < SIZE / 2:
                    dark += 1
                else:
                    light += 1
    assert dark > 1.5 * light


def test_amplitude_capped_below_row_pitch() -> None:
    # An absurd amplitude must not make rows collide: every emitted y
    # stays within half a row pitch of its baseline.
    svg = SineHalftoneAlgorithm().render_layer(
        _full_mask(),
        "#000000",
        "layer",
        options={"spacing_px": 4, "amp_px": 50, "period_px": 4, "_tone": _gradient_tone()},
    )
    for _x, y in _points(svg):
        assert abs(y - round(y / 4) * 4) < 2.0
