"""Optimised TSP-art algorithm.

Stipples the region into a point cloud then connects every point in a
single polyline using one of three strategies (all from
:mod:`pen_plotter.core.tsp`):

- ``nn``: bare greedy nearest-neighbour (equivalent to the legacy
  :mod:`tsp` algorithm, kept for parity / benchmarking).
- ``nn_2opt`` (default): NN seed followed by k-NN-limited 2-opt within
  a configurable time budget. Typically 5–15% shorter than NN alone.
- ``mst``: minimum spanning tree on a k-NN sparse graph + DFS preorder
  with shortcut — Christofides-like upper bound 2× optimal, much
  cheaper than 2-opt at 5k+ points.

This sits alongside the legacy :mod:`tsp` algorithm (back-compat for
existing presets / persisted placements) — operators picking the new
algorithm get the better tour while existing layouts keep rendering
identically.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.core.tsp import (
    mst_dfs_tour,
    nearest_neighbour_tour,
    two_opt_improve,
)


def _poisson_sample(
    ys: NDArray[np.intp],
    xs: NDArray[np.intp],
    *,
    target: int,
    seed: int,
) -> NDArray[np.float64]:
    """Approximate Poisson-disk sampling via grid binning.

    Cheaper than Bridson but visually equivalent for the densities the
    TSP-art renderer uses. Falls back to plain random selection when
    the grid resolution would push fewer than ``target`` cells.
    """
    rng = np.random.default_rng(seed)
    n = ys.size
    if n <= target:
        return np.column_stack([xs, ys]).astype(np.float64)
    # Side of a square grid that fits ~target cells across the bbox.
    span_x = max(1.0, float(xs.max() - xs.min() + 1))
    span_y = max(1.0, float(ys.max() - ys.min() + 1))
    cell = max(1.0, np.sqrt(span_x * span_y / max(1, target)))
    gx = ((xs - xs.min()) // cell).astype(np.int64)
    gy = ((ys - ys.min()) // cell).astype(np.int64)
    key = gx + gy * (int(gx.max()) + 2)
    # Pick one random pixel per occupied cell.
    order = rng.permutation(n)
    seen: dict[int, int] = {}
    for idx in order:
        k = int(key[idx])
        if k not in seen:
            seen[k] = int(idx)
    chosen = list(seen.values())
    if len(chosen) > target:
        chosen = list(rng.choice(chosen, size=target, replace=False))
    return np.column_stack([xs[chosen], ys[chosen]]).astype(np.float64)


class TspOptimizedAlgorithm(RasterAlgorithm):
    """Stipples + connects via NN+2-opt or MST-DFS — minimal total travel."""

    name: ClassVar[str] = "tsp_opt"
    description: ClassVar[str] = (
        "TSP-art with 2-opt or MST optimisation — shorter total travel than the "
        "legacy greedy tour."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = options or {}
        density = max(0.0, min(1.0, float(opts.get("density", 0.02))))
        max_points = max(2, int(opts.get("max_points", 4000)))
        method = str(opts.get("method", "nn_2opt"))
        time_budget = max(0.0, float(opts.get("time_budget_s", 1.5)))
        seed = int(opts.get("seed", 0))
        poisson = bool(opts.get("poisson_disk", True))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.6" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        ys, xs = np.where(bool_mask)
        n = ys.size
        if n == 0:
            return group_open + "</g>"
        target = max(2, min(max_points, int(n * density)))
        if poisson:
            points = _poisson_sample(ys, xs, target=target, seed=seed)
        else:
            rng = np.random.default_rng(seed)
            choice = rng.choice(n, size=min(target, n), replace=False)
            points = np.column_stack([xs[choice], ys[choice]]).astype(np.float64)

        if len(points) < 2:
            return group_open + "</g>"

        if method == "mst":
            order = mst_dfs_tour(points)
        elif method == "nn":
            order = nearest_neighbour_tour(points)
        else:  # nn_2opt (default)
            seed_tour = nearest_neighbour_tour(points)
            order = two_opt_improve(points, seed_tour, time_budget_s=time_budget)

        ordered = points[order]
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in ordered)
        return group_open + f'<polyline points="{path}"/></g>'
