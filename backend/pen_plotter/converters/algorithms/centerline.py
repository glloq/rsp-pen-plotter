"""Centerline / medial-axis tracing.

Traces each region's medial skeleton as single-stroke polylines.
Designed for schematics, technical diagrams and other line art where
``DirectVectorizationAlgorithm`` (potrace outline trace) would emit a
double-outline around what is conceptually a single stroke.

Skeletonisation uses ``scikit-image`` when available. If the optional
dep is missing at runtime, the algorithm falls back to
:class:`EdgesAlgorithm` rather than crashing, so deployments without
the dep installed still produce *some* line output for this layer.

Performance notes
-----------------
The chain tracer is the hot path on large schematics (4–8k px on the
long edge): a million-pixel skeleton means a million walk steps. To
keep the Python overhead per step small we:

* Build a per-pixel **direction bitmask** (one byte / pixel) in 8
  vectorised numpy passes — no per-pixel Python work. Bit ``di`` is
  set iff the neighbour at offset ``_NEIGHBOURS_8[di]`` is also a
  skeleton pixel. The walk then resolves "given I came from
  direction X, where do I go next?" with two array lookups and a
  bit op, with no dict involved.
* Use ``scipy.ndimage.label`` to find closed-loop components in O(N)
  C-time, *only* when there are unwalked edges left. The previous
  implementation re-scanned every count==2 pixel of the skeleton in
  Python, even though the overwhelming majority were already covered
  by chains walked from endpoints / junctions — that pass alone
  could take hundreds of seconds on a dense schematic.
* Vectorise Chaikin smoothing so long chains don't pay per-vertex
  Python overhead.
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
_KERNEL_8 = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.int8)
# For each of the 8 neighbour offsets, the index of the opposite offset:
# (-1,-1) ↔ (1,1), (-1,0) ↔ (1,0), …  — symmetric, so simply 7 - i.
_OPPOSITE_DIR = tuple(7 - i for i in range(8))
# uint8 byte → index of its lowest set bit (8 if the byte is zero).
# Used by the walker to pick the "other" neighbour at a count==2
# pixel without iterating 8 candidates in Python.
_LOWEST_SET_BIT = bytearray([8] * 256)
for _v in range(1, 256):
    _b = 0
    while not (_v >> _b) & 1:
        _b += 1
    _LOWEST_SET_BIT[_v] = _b


def _skeletonize(mask: NDArray[np.bool_]) -> NDArray[np.bool_] | None:
    """Return the 1-pixel-wide medial skeleton, or ``None`` if skimage missing."""
    try:
        from skimage.morphology import skeletonize as _sk
    except ImportError:
        return None
    return _sk(mask).astype(bool)


def _neighbour_count(skel: NDArray[np.bool_]) -> NDArray[np.int8]:
    """Count of skeleton-pixel neighbours (8-connectivity) for each pixel."""
    try:
        from scipy.ndimage import convolve
        total = convolve(
            skel.astype(np.int8), _KERNEL_8, mode="constant", cval=0
        )
    except ImportError:
        padded = np.pad(skel, 1, mode="constant", constant_values=False).astype(np.int8)
        total = np.zeros_like(skel, dtype=np.int8)
        for dy, dx in _NEIGHBOURS_8:
            total += padded[1 + dy:1 + dy + skel.shape[0], 1 + dx:1 + dx + skel.shape[1]]
    return (total * skel.astype(np.int8)).astype(np.int8)


def _direction_mask(skel: NDArray[np.bool_]) -> NDArray[np.uint8]:
    """uint8 bitmask per pixel; bit ``di`` is set iff neighbour ``di`` is too.

    Built in 8 vectorised passes (one per neighbour offset). The result
    is a flat ``(h*w,)`` array — the walker indexes it directly by
    flat pixel index, replacing what would otherwise be 8 bounds-checked
    Python lookups per step.
    """
    h, w = skel.shape
    padded = np.pad(skel, 1, mode="constant", constant_values=False)
    mask = np.zeros(h * w, dtype=np.uint8)
    for di, (dy, dx) in enumerate(_NEIGHBOURS_8):
        shifted = padded[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        pair = (skel & shifted).ravel().view(np.uint8)
        if pair.any():
            mask |= pair << di
    return mask


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

    h, w = skel.shape
    counts_flat = _neighbour_count(skel).ravel()
    dir_mask = _direction_mask(skel)
    dir_deltas = tuple(dy * w + dx for dy, dx in _NEIGHBOURS_8)
    lowest = _LOWEST_SET_BIT
    opposite = _OPPOSITE_DIR
    total_edges = int(counts_flat.sum()) // 2
    visited_edges: set[tuple[int, int]] = set()
    chains_flat: list[list[int]] = []

    seeds = np.flatnonzero((counts_flat == 1) | (counts_flat >= 3)).tolist()
    for s in seeds:
        s = int(s)
        m = int(dir_mask[s])
        di = 0
        while m:
            if m & 1:
                n = s + dir_deltas[di]
                edge = (s, n) if s < n else (n, s)
                if edge not in visited_edges:
                    chain: list[int] = [s]
                    prev = s
                    cur = n
                    cur_from = opposite[di]
                    while True:
                        e = (prev, cur) if prev < cur else (cur, prev)
                        visited_edges.add(e)
                        chain.append(cur)
                        if counts_flat[cur] != 2:
                            break
                        # Pick the "other" set neighbour by clearing the
                        # bit we came from; the byte then has exactly one
                        # bit set whose index we look up in O(1).
                        other = (int(dir_mask[cur]) & ~(1 << cur_from)) & 0xFF
                        ex = lowest[other]
                        nxt = cur + dir_deltas[ex]
                        cur_from = opposite[ex]
                        prev = cur
                        cur = nxt
                    if len(chain) - 1 >= min_branch_px:
                        chains_flat.append(chain)
            m >>= 1
            di += 1

    # Closed loops (cycles with no endpoints or junctions). Skip the
    # whole pass when every edge was already walked — schematics
    # without resistor loops, IC outlines etc. don't pay for it.
    if len(visited_edges) < total_edges:
        try:
            from scipy.ndimage import label as _ndi_label
        except ImportError:
            _ndi_label = None
        if _ndi_label is not None:
            remaining = skel & (counts_flat.reshape(h, w) == 2)
            if remaining.any():
                labeled, n_comp = _ndi_label(
                    remaining, structure=np.ones((3, 3), dtype=int)
                )
                if n_comp > 0:
                    flat_labeled = labeled.ravel()
                    # Find one representative pixel per labeled component
                    # via np.unique(return_index=True) — single C-time pass.
                    uniq, first_idx = np.unique(flat_labeled, return_index=True)
                    first_idx = first_idx[uniq != 0]
                    for s in first_idx.tolist():
                        s = int(s)
                        m = int(dir_mask[s])
                        if bin(m).count("1") < 2:
                            continue
                        # If any incident edge was already traced, this
                        # component is the interior of a chain we walked.
                        already_seen = False
                        mm = m
                        dd = 0
                        while mm:
                            if mm & 1:
                                nb = s + dir_deltas[dd]
                                ee = (s, nb) if s < nb else (nb, s)
                                if ee in visited_edges:
                                    already_seen = True
                                    break
                            mm >>= 1
                            dd += 1
                        if already_seen:
                            continue
                        # Walk the cycle.
                        first_di = lowest[m]
                        chain = [s]
                        prev = s
                        cur = s + dir_deltas[first_di]
                        cur_from = opposite[first_di]
                        e = (s, cur) if s < cur else (cur, s)
                        visited_edges.add(e)
                        chain.append(cur)
                        while cur != s:
                            if counts_flat[cur] != 2:
                                break  # defensive — pure cycles stay count==2
                            other = (int(dir_mask[cur]) & ~(1 << cur_from)) & 0xFF
                            ex = lowest[other]
                            nxt = cur + dir_deltas[ex]
                            cur_from = opposite[ex]
                            e = (cur, nxt) if cur < nxt else (nxt, cur)
                            visited_edges.add(e)
                            chain.append(nxt)
                            prev = cur
                            cur = nxt
                        if len(chain) - 1 >= min_branch_px:
                            chains_flat.append(chain)

    # Return as (N, 2) float numpy arrays so downstream Chaikin /
    # SVG formatting can stay vectorised — avoids two list↔ndarray
    # round-trips per chain that showed up in profiles on long polylines.
    out: list[NDArray[np.float64]] = []
    for c in chains_flat:
        idx = np.asarray(c, dtype=np.int64)
        arr = np.empty((len(c), 2), dtype=np.float64)
        arr[:, 0] = idx % w  # x
        arr[:, 1] = idx // w  # y
        out.append(arr)
    return out


def _chaikin(points: NDArray[np.float64], *, iters: int = 1) -> NDArray[np.float64]:
    """Chaikin corner-cutting smoothing — keeps endpoints, softens kinks.

    Operates on (N, 2) numpy arrays end-to-end so each call is just a
    handful of vectorised slices, with no Python-level iteration over
    vertices. The prior implementation converted list↔array once per
    chain and once per smoothing iteration — fine for small inputs but
    a measurable cost when a schematic produces 25k+ chains.
    """
    if len(points) < 3 or iters <= 0:
        return points
    arr = points
    for _ in range(iters):
        p0 = arr[:-1]
        p1 = arr[1:]
        q = 0.75 * p0 + 0.25 * p1
        r = 0.25 * p0 + 0.75 * p1
        out = np.empty((2 * len(p0) + 2, 2), dtype=np.float64)
        out[0] = arr[0]
        out[1:-1:2] = q
        out[2:-1:2] = r
        out[-1] = arr[-1]
        arr = out
    return arr


def _format_chains_points(
    chains: list[NDArray[np.float64]],
) -> list[str]:
    """Format every chain's ``"x0,y0 x1,y1 …"`` body.

    Concatenates all chains into one ``(M, 2)`` array so the ndarray→
    Python conversion happens in a single ``.tolist()`` call, then
    formats each ``(x, y)`` pair with the ``%`` operator inside a list
    comprehension. Benchmarked against ``np.char.mod`` and that
    formatter pays ~2× the cost at this scale — CPython's float→string
    is highly optimised and the per-call C-extension overhead of
    ``_vec_string`` dominates for ``.2f`` precision.
    """
    if not chains:
        return []
    sizes = [len(c) for c in chains]
    combined = np.concatenate(chains, axis=0).tolist()
    pairs = ["%.2f,%.2f" % (x, y) for x, y in combined]
    out: list[str] = []
    idx = 0
    for n in sizes:
        out.append(" ".join(pairs[idx:idx + n]))
        idx += n
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

        drawable = [c for c in chains if len(c) >= 2]
        bodies = _format_chains_points(drawable)
        paths = "".join(
            '<polyline points="' + body + '"/>' for body in bodies
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{thickness}" stroke-linejoin="round" '
            f'stroke-linecap="round">'
            + paths
            + "</g>"
        )
