"""Pure-Python TSP helpers for one-line drawings.

Reusable across raster algorithms (``tsp_opt``) and any future CLI tool
that needs to turn a point cloud into a single plottable polyline. All
solvers operate on a ``(n, 2)`` float64 array of XY coordinates and
return a list of indices describing the visit order.

Three strategies are exposed:

- :func:`nearest_neighbour_tour` — fast greedy seed.
- :func:`two_opt_improve` — local-search refinement using a kd-tree
  candidate list, so the per-iteration cost is O(n·k) instead of
  O(n²). Stops on a time budget so the Pi-class device never stalls.
- :func:`mst_dfs_tour` — minimum spanning tree on a k-NN sparse graph
  followed by a DFS pre-order traversal with shortcuts. Christofides-
  like upper bound 2× optimal, much cheaper than 2-opt on large
  instances.
"""

from __future__ import annotations

import time

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "mst_dfs_tour",
    "nearest_neighbour_tour",
    "tour_length",
    "two_opt_improve",
]


def tour_length(points: NDArray[np.float64], tour: list[int]) -> float:
    """Return the cumulative pen-down length of ``tour`` over ``points``.

    Open tour: no closing edge back to the first point — matches what a
    plotter actually draws when ``tour`` is rendered as a single polyline.
    """
    if len(tour) < 2:
        return 0.0
    ordered = points[tour]
    diffs = np.diff(ordered, axis=0)
    return float(np.sqrt((diffs * diffs).sum(axis=1)).sum())


def nearest_neighbour_tour(
    points: NDArray[np.float64], *, start: int | None = None
) -> list[int]:
    """Greedy nearest-neighbour tour starting at ``start`` (or top-left)."""
    n = len(points)
    if n == 0:
        return []
    if n == 1:
        return [0]
    visited = np.zeros(n, dtype=bool)
    if start is None:
        start = int(np.argmin(points[:, 0] + points[:, 1]))
    visited[start] = True
    order = [start]
    current = points[start]
    for _ in range(n - 1):
        diff = points - current
        dist = np.einsum("ij,ij->i", diff, diff)
        dist[visited] = np.inf
        nxt = int(dist.argmin())
        visited[nxt] = True
        order.append(nxt)
        current = points[nxt]
    return order


def two_opt_improve(
    points: NDArray[np.float64],
    tour: list[int],
    *,
    time_budget_s: float = 1.5,
    neighbour_k: int = 20,
) -> list[int]:
    """Refine ``tour`` with 2-opt swaps, bounded by ``time_budget_s``.

    Candidate edges to test are the ``neighbour_k`` spatial neighbours of
    each tour node (via ``scipy.spatial.cKDTree``) rather than every
    other node. That keeps each sweep O(n·k) — essential for the Pi
    when n grows past ~2000.
    """
    n = len(tour)
    if n < 4:
        return list(tour)
    try:
        from scipy.spatial import cKDTree  # type: ignore[import-untyped]
    except ImportError:
        return _two_opt_full(points, tour, time_budget_s)

    tree = cKDTree(points)
    k = max(2, min(neighbour_k, n - 1))
    # Query k+1 because the first hit is always the point itself.
    _, neighbours = tree.query(points, k=k + 1)

    # ``pos[i]`` = position of point i in the current tour. Maintained
    # alongside ``order`` so we can look up where a neighbour sits.
    order = list(tour)
    pos = [0] * n
    for idx, p in enumerate(order):
        pos[p] = idx

    deadline = time.perf_counter() + max(0.0, time_budget_s)
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        for i in range(n - 1):
            if time.perf_counter() >= deadline:
                break
            a = order[i]
            b = order[i + 1]
            d_ab = _dist(points, a, b)
            # Test swaps with each near-spatial neighbour of ``a``.
            for c in neighbours[a][1:]:
                j = pos[c]
                # We rewrite the slice ``order[i+1 : j+1]`` reversed,
                # turning edges (a,b) + (c,d) into (a,c) + (b,d). Skip
                # degenerate / adjacent cases.
                if j <= i + 1 or j >= n - 1:
                    continue
                d = order[j + 1]
                gain = d_ab + _dist(points, c, d) - _dist(points, a, c) - _dist(points, b, d)
                if gain > 1e-9:
                    order[i + 1 : j + 1] = order[i + 1 : j + 1][::-1]
                    # Refresh pos for the reversed slice.
                    for idx in range(i + 1, j + 1):
                        pos[order[idx]] = idx
                    improved = True
                    break  # restart neighbour scan with the new b
    return order


def _two_opt_full(
    points: NDArray[np.float64], tour: list[int], time_budget_s: float
) -> list[int]:
    """O(n²) per-sweep fallback when scipy isn't importable."""
    n = len(tour)
    if n < 4:
        return list(tour)
    order = list(tour)
    deadline = time.perf_counter() + max(0.0, time_budget_s)
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        for i in range(n - 2):
            if time.perf_counter() >= deadline:
                break
            a = order[i]
            b = order[i + 1]
            d_ab = _dist(points, a, b)
            for j in range(i + 2, n - 1):
                c = order[j]
                d = order[j + 1]
                gain = d_ab + _dist(points, c, d) - _dist(points, a, c) - _dist(points, b, d)
                if gain > 1e-9:
                    order[i + 1 : j + 1] = order[i + 1 : j + 1][::-1]
                    improved = True
                    break
    return order


def _dist(points: NDArray[np.float64], i: int, j: int) -> float:
    dx = points[i, 0] - points[j, 0]
    dy = points[i, 1] - points[j, 1]
    return float(np.hypot(dx, dy))


def mst_dfs_tour(points: NDArray[np.float64], *, neighbour_k: int = 8) -> list[int]:
    """Build a Hamiltonian tour via MST + DFS preorder shortcuts.

    For pen-plotter workloads this is the practical alternative to 2-opt
    when ``len(points)`` runs into the thousands: scipy's sparse MST on
    a k-NN graph keeps the build cost linear in the graph size, and the
    Christofides bound (≤ 2× optimal) is more than acceptable for the
    visual result.
    """
    n = len(points)
    if n == 0:
        return []
    if n == 1:
        return [0]
    try:
        from scipy.sparse import lil_matrix  # type: ignore[import-untyped]
        from scipy.sparse.csgraph import (  # type: ignore[import-untyped]
            depth_first_order,
            minimum_spanning_tree,
        )
        from scipy.spatial import cKDTree  # type: ignore[import-untyped]
    except ImportError:
        return nearest_neighbour_tour(points)

    tree = cKDTree(points)
    k = max(2, min(neighbour_k, n - 1))
    dists, neighbours = tree.query(points, k=k + 1)

    graph = lil_matrix((n, n))
    # Symmetric k-NN: edge (i, j) exists iff j is in i's k-NN list. Using
    # only one direction would leave isolated nodes in irregular clusters
    # — MST would silently drop them.
    for i in range(n):
        for idx in range(1, k + 1):
            j = int(neighbours[i, idx])
            w = float(dists[i, idx])
            if graph[i, j] == 0 or w < graph[i, j]:
                graph[i, j] = w
                graph[j, i] = w
    mst = minimum_spanning_tree(graph.tocsr())
    start = int(np.argmin(points[:, 0] + points[:, 1]))
    visited_order, _ = depth_first_order(mst, i_start=start, directed=False)
    visited_set: set[int] = set()
    tour: list[int] = []
    for node in visited_order:
        node_i = int(node)
        if node_i in visited_set:
            continue
        visited_set.add(node_i)
        tour.append(node_i)
    # depth_first_order on a disconnected graph leaves some nodes out.
    # Append leftovers via nearest-to-last greedy so every point is hit.
    if len(tour) < n:
        remaining = [i for i in range(n) if i not in visited_set]
        while remaining:
            last = points[tour[-1]]
            diff = points[remaining] - last
            d = np.einsum("ij,ij->i", diff, diff)
            idx = int(d.argmin())
            tour.append(remaining.pop(idx))
    return tour
