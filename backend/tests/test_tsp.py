"""Unit tests for :mod:`pen_plotter.core.tsp`."""

from __future__ import annotations

import numpy as np
import pytest

from pen_plotter.core.tsp import (
    mst_dfs_tour,
    nearest_neighbour_tour,
    tour_length,
    two_opt_improve,
)


def test_empty_inputs() -> None:
    pts = np.empty((0, 2), dtype=np.float64)
    assert nearest_neighbour_tour(pts) == []
    assert mst_dfs_tour(pts) == []
    assert tour_length(pts, []) == 0.0


def test_single_point() -> None:
    pts = np.array([[1.0, 2.0]])
    assert nearest_neighbour_tour(pts) == [0]
    assert mst_dfs_tour(pts) == [0]
    assert tour_length(pts, [0]) == 0.0


def test_collinear_five_points_optimal_nn() -> None:
    pts = np.array([[x, 0.0] for x in (0.0, 1.0, 2.0, 3.0, 4.0)])
    tour = nearest_neighbour_tour(pts)
    assert sorted(tour) == [0, 1, 2, 3, 4]
    # NN starting from leftmost lands on the optimal left-to-right walk.
    assert tour_length(pts, tour) == pytest.approx(4.0)


def test_tour_visits_every_point() -> None:
    rng = np.random.default_rng(42)
    pts = rng.uniform(0.0, 100.0, size=(50, 2))
    for solver in (nearest_neighbour_tour, mst_dfs_tour):
        tour = solver(pts)
        assert len(tour) == len(pts)
        assert set(tour) == set(range(len(pts)))


def test_two_opt_no_worse_than_nn() -> None:
    """Across 5 random seeds, 2-opt never lengthens the NN tour."""
    for seed in range(5):
        rng = np.random.default_rng(seed)
        pts = rng.uniform(0.0, 100.0, size=(80, 2))
        nn_tour = nearest_neighbour_tour(pts)
        improved = two_opt_improve(pts, nn_tour, time_budget_s=0.5)
        # Strict ≤ because 2-opt only accepts strictly-improving swaps.
        assert tour_length(pts, improved) <= tour_length(pts, nn_tour) + 1e-9
        # Same set of points.
        assert set(improved) == set(nn_tour)


def test_two_opt_improves_clustered_input() -> None:
    """On clustered points the 2-opt result is strictly shorter than NN."""
    rng = np.random.default_rng(7)
    clusters = []
    for cx, cy in [(0, 0), (50, 0), (50, 50), (0, 50)]:
        clusters.append(rng.normal(loc=(cx, cy), scale=3.0, size=(20, 2)))
    pts = np.vstack(clusters)
    nn_tour = nearest_neighbour_tour(pts)
    improved = two_opt_improve(pts, nn_tour, time_budget_s=1.0)
    assert tour_length(pts, improved) < tour_length(pts, nn_tour)


def test_two_opt_respects_time_budget() -> None:
    """A 0s budget must return immediately without raising."""
    rng = np.random.default_rng(1)
    pts = rng.uniform(0.0, 100.0, size=(200, 2))
    nn_tour = nearest_neighbour_tour(pts)
    out = two_opt_improve(pts, nn_tour, time_budget_s=0.0)
    assert set(out) == set(nn_tour)
