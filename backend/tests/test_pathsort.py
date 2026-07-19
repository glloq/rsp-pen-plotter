"""Unit tests for :mod:`pen_plotter.core.pathsort`."""

from __future__ import annotations

import numpy as np
import pytest

from pen_plotter.core.pathsort import improve_order, pen_up_length


def _circle(cx: float, cy: float, r: float, n: int = 24, phase: float = 0.0) -> np.ndarray:
    """Closed loop of ``n`` segments; the seam sits at angle ``phase``."""
    angles = phase + np.linspace(0.0, 2 * np.pi, n + 1)
    return (cx + r * np.cos(angles)) + 1j * (cy + r * np.sin(angles))


def _segment(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    return np.array([complex(x0, y0), complex(x1, y1)])


def _point_sets(lines: list[np.ndarray]) -> list[frozenset[complex]]:
    """Canonical geometry signature: the vertex set of each line, order-free.

    Rotation of a closed loop and reversal of an open path both preserve
    the vertex set, so equality of the sorted signatures proves no
    geometry was lost or invented.
    """
    return sorted(
        frozenset(complex(round(p.real, 6), round(p.imag, 6)) for p in line) for line in lines
    )


def test_geometry_survives_reordering() -> None:
    lines = [
        _circle(0, 0, 5),
        _segment(20, 0, 30, 0),
        _circle(50, 0, 5),
        _segment(70, 0, 80, 0),
    ]
    result = improve_order(lines)
    assert len(result) == len(lines)
    assert _point_sets(result) == _point_sets(lines)


def test_never_worse_than_input() -> None:
    rng = np.random.default_rng(42)
    lines = []
    for _ in range(60):
        x, y = rng.uniform(0, 100, size=2)
        if rng.random() < 0.5:
            lines.append(_circle(x, y, rng.uniform(1, 4)))
        else:
            dx, dy = rng.uniform(-5, 5, size=2)
            lines.append(_segment(x, y, x + dx, y + dy))
    before = pen_up_length(lines)
    after = pen_up_length(improve_order(lines))
    assert after <= before + 1e-9


def test_seam_rotation_beats_fixed_seams_on_closed_loops() -> None:
    """Circles in a triangle: entering each at its nearest rim must win.

    A closed loop is entered and left at the same point, so the seam
    choice decides both hops. With seams pinned at each circle's leftmost
    point the tour detours; seam rotation enters every loop at the rim
    facing the travel path. (A collinear row would be seam-invariant —
    the 2-D arrangement is what makes rotation strictly better.)
    """
    lines = [
        _circle(0, 0, 5, phase=np.pi),
        _circle(30, 0, 5, phase=np.pi),
        _circle(15, 30, 5, phase=np.pi),
    ]
    fixed = improve_order(lines, seam_rotation=False, two_opt_budget_s=0.0)
    rotated = improve_order(lines, seam_rotation=True, two_opt_budget_s=0.0)
    assert pen_up_length(rotated) < pen_up_length(fixed)


def test_closed_loops_stay_closed_after_rotation() -> None:
    lines = [_circle(x, 0, 5, phase=np.pi) for x in (0.0, 30.0, 60.0)]
    for line in improve_order(lines):
        assert line[0] == pytest.approx(line[-1])
        assert len(line) == len(lines[0])


def test_open_paths_may_flip_direction() -> None:
    """Reversing the middle segment turns a 20-unit hop into a 1-unit one."""
    lines = [
        _segment(0, 0, 10, 0),
        _segment(30, 0, 11, 0),
        _segment(31, 0, 40, 0),
    ]
    result = improve_order(lines)
    assert pen_up_length(result) == pytest.approx(2.0, abs=0.01)


def test_disabled_passes_return_input_order() -> None:
    lines = [_segment(0, 0, 1, 0), _segment(50, 0, 51, 0), _segment(10, 0, 11, 0)]
    result = improve_order(lines, seam_rotation=False, two_opt_budget_s=0.0)
    assert [id(line) for line in result] == [id(line) for line in lines]


def test_small_inputs_pass_through() -> None:
    assert improve_order([]) == []
    single = [_segment(0, 0, 1, 0)]
    assert len(improve_order(single)) == 1
