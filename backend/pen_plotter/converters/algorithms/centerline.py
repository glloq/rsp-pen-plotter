"""Centerline / medial-axis tracing.

Traces each region's medial skeleton as single-stroke polylines.
Designed for schematics, technical diagrams and other line art where
``DirectVectorizationAlgorithm`` (potrace outline trace) would emit a
double-outline around what is conceptually a single stroke.

Skeletonisation uses ``scikit-image`` when available. If the optional
dep is missing at runtime, the algorithm falls back to
:class:`EdgesAlgorithm` rather than crashing, so deployments without
the dep installed still produce *some* line output for this layer.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm

_NEIGHBOURS_8 = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)


def _skeletonize(mask: NDArray[np.bool_]) -> NDArray[np.bool_] | None:
    """Return the 1-pixel-wide medial skeleton, or ``None`` if skimage missing."""
    try:
        from skimage.morphology import skeletonize as _sk
    except ImportError:
        return None
    return _sk(mask).astype(bool)


def _neighbour_count(skel: NDArray[np.bool_]) -> NDArray[np.int8]:
    """Count of skeleton-pixel neighbours (8-connectivity) for each pixel."""
    padded = np.pad(skel, 1, mode="constant", constant_values=False).astype(np.int8)
    total = np.zeros_like(skel, dtype=np.int8)
    for dy, dx in _NEIGHBOURS_8:
        total += padded[1 + dy:1 + dy + skel.shape[0], 1 + dx:1 + dx + skel.shape[1]]
    return total * skel.astype(np.int8)


def _trace_chains(
    skel: NDArray[np.bool_], *, min_branch_px: int
) -> list[list[tuple[float, float]]]:
    """Walk the skeleton into polylines between endpoints/junctions.

    A skeleton pixel is an *endpoint* if it has exactly one skeleton
    neighbour, a *junction* if it has three or more, and otherwise a
    *path* pixel. We start a chain at every endpoint or junction, walk
    8-connected path pixels until we hit another endpoint or junction,
    and emit the visited pixel sequence as one polyline. Spurs shorter
    than ``min_branch_px`` are discarded to suppress skeletonisation
    noise around stroke ends.
    """
    if not skel.any():
        return []
    counts = _neighbour_count(skel)
    visited_edges: set[tuple[int, int, int, int]] = set()
    chains: list[list[tuple[float, float]]] = []

    def neighbours(y: int, x: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for dy, dx in _NEIGHBOURS_8:
            ny, nx = y + dy, x + dx
            if 0 <= ny < skel.shape[0] and 0 <= nx < skel.shape[1] and skel[ny, nx]:
                out.append((ny, nx))
        return out

    seeds_y, seeds_x = np.where((counts == 1) | (counts >= 3))
    for sy, sx in zip(seeds_y.tolist(), seeds_x.tolist()):
        for ny, nx in neighbours(sy, sx):
            edge = (sy, sx, ny, nx) if (sy, sx) < (ny, nx) else (ny, nx, sy, sx)
            if edge in visited_edges:
                continue
            chain: list[tuple[int, int]] = [(sy, sx)]
            prev_y, prev_x = sy, sx
            cur_y, cur_x = ny, nx
            while True:
                edge = (
                    (prev_y, prev_x, cur_y, cur_x)
                    if (prev_y, prev_x) < (cur_y, cur_x)
                    else (cur_y, cur_x, prev_y, prev_x)
                )
                visited_edges.add(edge)
                chain.append((cur_y, cur_x))
                if counts[cur_y, cur_x] != 2:
                    break
                nxts = [p for p in neighbours(cur_y, cur_x) if p != (prev_y, prev_x)]
                if not nxts:
                    break
                prev_y, prev_x = cur_y, cur_x
                cur_y, cur_x = nxts[0]
            if len(chain) - 1 >= min_branch_px:
                chains.append([(float(x), float(y)) for (y, x) in chain])

    # Closed loops (no endpoints, no junctions) are still possible — pick
    # an arbitrary pixel and walk the cycle.
    remaining = skel & (counts == 2)
    for ey, ex in zip(*np.where(remaining)):
        if remaining[ey, ex] == False:  # noqa: E712 — re-checked because we mutate below
            continue
        if any(
            ((min(ey, ny), min(ex, nx), max(ey, ny), max(ex, nx)) in visited_edges)
            for (ny, nx) in neighbours(int(ey), int(ex))
        ):
            continue
        chain_yx: list[tuple[int, int]] = [(int(ey), int(ex))]
        prev_y, prev_x = int(ey), int(ex)
        nbrs = neighbours(prev_y, prev_x)
        if not nbrs:
            continue
        cur_y, cur_x = nbrs[0]
        while (cur_y, cur_x) != (int(ey), int(ex)):
            chain_yx.append((cur_y, cur_x))
            edge = (
                (prev_y, prev_x, cur_y, cur_x)
                if (prev_y, prev_x) < (cur_y, cur_x)
                else (cur_y, cur_x, prev_y, prev_x)
            )
            visited_edges.add(edge)
            nxts = [p for p in neighbours(cur_y, cur_x) if p != (prev_y, prev_x)]
            if not nxts:
                break
            prev_y, prev_x = cur_y, cur_x
            cur_y, cur_x = nxts[0]
        chain_yx.append((int(ey), int(ex)))
        if len(chain_yx) - 1 >= min_branch_px:
            chains.append([(float(x), float(y)) for (y, x) in chain_yx])

    return chains


def _chaikin(points: list[tuple[float, float]], *, iters: int = 1) -> list[tuple[float, float]]:
    """Chaikin corner-cutting smoothing — keeps endpoints, softens kinks."""
    if len(points) < 3 or iters <= 0:
        return points
    out = points
    for _ in range(iters):
        smoothed: list[tuple[float, float]] = [out[0]]
        for (x0, y0), (x1, y1) in zip(out, out[1:]):
            smoothed.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            smoothed.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        smoothed.append(out[-1])
        out = smoothed
    return out


class CenterlineAlgorithm(RasterAlgorithm):
    """Trace the medial skeleton of each region as single-stroke polylines."""

    name: ClassVar[str] = "centerline"
    description: ClassVar[str] = (
        "Trace the medial skeleton as single-stroke polylines — ideal for "
        "schematics and line art. Thick filled regions collapse to a single "
        "line at the centre, which is intentional but may surprise on photos."
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
        thickness = float(opts.get("stroke_width", 0.8))
        smooth = bool(opts.get("smooth", True))
        min_branch_px = int(opts.get("min_branch_px", 3))

        bool_mask = mask.astype(bool)
        skel = _skeletonize(bool_mask)
        if skel is None:
            # scikit-image not installed — emit an outline instead of nothing.
            from pen_plotter.converters.algorithms.edges import EdgesAlgorithm
            return EdgesAlgorithm().render_layer(
                mask, color_hex, label, options=options
            )

        chains = _trace_chains(skel, min_branch_px=min_branch_px)
        if smooth:
            chains = [_chaikin(c, iters=1) for c in chains]

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in chain) + '"/>'
            for chain in chains
            if len(chain) >= 2
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{thickness}" stroke-linejoin="round" '
            f'stroke-linecap="round">'
            + paths
            + "</g>"
        )
