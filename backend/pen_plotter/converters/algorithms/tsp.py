"""TSP-art algorithm.

Stipples the region into a cloud of points and connects them with a
single greedy nearest-neighbour tour. The result is one long polyline
that visits every dot — a hallmark of "TSP art". We deliberately stop
short of a Lin-Kernighan optimisation: the runtime cost outpaces the
visual gain at the pen-plotter scale (~1k–5k dots).
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _greedy_nn_tour(points: NDArray[np.float64]) -> list[int]:
    """Greedy nearest-neighbour tour, starting from the top-left-most point."""
    n = len(points)
    if n == 0:
        return []
    visited = np.zeros(n, dtype=bool)
    # Start at the point closest to the (0, 0) corner — gives a deterministic
    # entry that lands near the pen's idle position on a top-left origin.
    start = int(np.argmin(points[:, 0] + points[:, 1]))
    visited[start] = True
    order = [start]
    current = points[start]
    for _ in range(n - 1):
        # Squared distance to all unvisited; mask visited with +inf.
        diff = points - current
        dist = np.einsum("ij,ij->i", diff, diff)
        dist[visited] = np.inf
        nxt = int(dist.argmin())
        visited[nxt] = True
        order.append(nxt)
        current = points[nxt]
    return order


class TspAlgorithm(RasterAlgorithm):
    """Stipples the region and connects the dots into one long polyline."""

    name: ClassVar[str] = "tsp"
    description: ClassVar[str] = (
        "Dots connected in one greedy nearest-neighbour tour — single-stroke TSP art."
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
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        ys, xs = np.where(bool_mask)
        n = len(xs)
        if n == 0:
            return f"<g inkscape:label={quoteattr(label)}></g>"
        target = max(2, int(n * density))
        # Cap aggressively to keep the O(n²) tour tractable on a Pi.
        target = min(target, 4000)
        rng = np.random.default_rng(seed)
        choice = rng.choice(n, size=target, replace=False)
        points = np.column_stack([xs[choice], ys[choice]]).astype(np.float64)

        order = _greedy_nn_tour(points)
        ordered = points[order]
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in ordered)
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.6" stroke-linecap="round" '
            f'stroke-linejoin="round">'
            f'<polyline points="{path}"/></g>'
        )
