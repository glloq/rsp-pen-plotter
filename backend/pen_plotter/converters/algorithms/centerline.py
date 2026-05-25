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
  skeleton pixel.
* Convert the direction mask and neighbour counts to ``bytearray`` /
  ``bytes`` for the walk: indexing a ``bytearray`` returns a Python
  ``int`` directly, sidestepping the numpy-scalar boxing that every
  ``arr[i]`` would otherwise pay per step.
* Track unwalked edges by **mutating the direction bitmask** instead
  of maintaining a Python ``set`` of visited (a, b) tuples. Each
  walked edge clears one bit on each endpoint. "Edge already visited"
  becomes a single bit test, and the set's ~80 MB / 1.6 M tuple
  overhead disappears.
* Use ``scipy.ndimage.label`` to find closed-loop components in O(N)
  C-time, *only* when bits remain set after the seed pass — schematics
  without resistor loops, IC outlines etc. don't pay for it at all.
* Vectorise Chaikin smoothing and batch coordinate formatting so the
  per-vertex Python overhead is amortised across all chains.
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
# uint8 byte → popcount. Used to derive skeleton-neighbour counts from
# the direction bitmask without a second numpy convolution pass.
_POPCOUNT_LUT = np.array([bin(v).count("1") for v in range(256)], dtype=np.uint8)


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
    return total * skel.astype(np.int8)


def _direction_mask(skel: NDArray[np.bool_]) -> NDArray[np.uint8]:
    """uint8 bitmask per pixel; bit ``di`` is set iff neighbour ``di`` is too.

    Built in 8 vectorised passes (one per neighbour offset). The result
    is a flat ``(h*w,)`` array — the walker indexes it directly by
    flat pixel index, replacing what would otherwise be 8 bounds-checked
    Python lookups per step.
    """
    skel = np.ascontiguousarray(skel)
    h, w = skel.shape
    padded = np.pad(skel, 1, mode="constant", constant_values=False)
    mask = np.zeros(h * w, dtype=np.uint8)
    for di, (dy, dx) in enumerate(_NEIGHBOURS_8):
        shifted = padded[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
        pair = np.ascontiguousarray(skel & shifted).ravel().view(np.uint8)
        if pair.any():
            mask |= pair << di
    return mask


def _trace_chains(
    skel: NDArray[np.bool_], *, min_branch_px: int
) -> list[NDArray[np.float64]]:
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
    dir_mask_np = _direction_mask(skel)
    # Derive per-pixel neighbour counts from the direction bitmask via
    # a 256-entry popcount LUT — saves a second scipy convolution pass
    # over the full canvas (0.5 s on 8 k × 6 k in benchmarks).
    counts_np = _POPCOUNT_LUT[dir_mask_np]
    # ``bytes`` / ``bytearray`` views give O(1) Python-int indexing in
    # the hot loop without paying numpy-scalar boxing per access.
    counts = bytes(counts_np)
    # ``live`` starts as the per-pixel direction bitmask of unwalked
    # edges; the walker clears bits as it traverses them. When every
    # edge is walked, ``live`` is all-zero, and the cycle pass
    # short-circuits.
    live = bytearray(dir_mask_np)
    dir_deltas = tuple(dy * w + dx for dy, dx in _NEIGHBOURS_8)
    lowest = _LOWEST_SET_BIT
    opposite = _OPPOSITE_DIR
    chains_flat: list[list[int]] = []

    seeds = np.flatnonzero(
        (counts_np == 1) | (counts_np >= 3)
    ).tolist()
    for s in seeds:
        s = int(s)
        # Walk every still-live edge out of s. Re-checking ``live[s]``
        # each iteration handles the case where another chain (e.g. one
        # walked from a different junction sharing this pixel) has
        # already cleared some bits.
        while live[s]:
            di = lowest[live[s]]
            n = s + dir_deltas[di]
            opp = opposite[di]
            live[s] &= 0xFF ^ (1 << di)
            live[n] &= 0xFF ^ (1 << opp)
            chain: list[int] = [s, n]
            cur = n
            # Walk through count==2 interior pixels until we hit a
            # junction / endpoint. The entry edge has already been
            # cleared in ``live[cur]``, so the remaining set bit
            # (there's exactly one for count==2) is the exit direction.
            while counts[cur] == 2:
                other = live[cur]
                if not other:
                    break  # defensive — pure-cycle entries handled below
                ex = lowest[other]
                nxt = cur + dir_deltas[ex]
                live[cur] = 0  # both bits cleared (entry + exit)
                live[nxt] &= 0xFF ^ (1 << opposite[ex])
                chain.append(nxt)
                cur = nxt
            if len(chain) - 1 >= min_branch_px:
                chains_flat.append(chain)

    # Closed loops (cycles with no endpoints or junctions). After the
    # seed pass, any pixel with ``live[p] != 0`` is part of an unwalked
    # cycle. Build a 2D mask of those and label its connected components
    # so we walk each cycle exactly once.
    live_np = np.frombuffer(live, dtype=np.uint8)
    if live_np.any():
        try:
            from scipy.ndimage import label as _ndi_label
        except ImportError:
            _ndi_label = None
        if _ndi_label is not None:
            cycle_mask = (live_np != 0).reshape(h, w)
            labeled, n_comp = _ndi_label(
                cycle_mask, structure=np.ones((3, 3), dtype=int)
            )
            if n_comp > 0:
                # One representative pixel per component, iterating only
                # the sparse "alive" pixels rather than the full canvas
                # — np.unique over h*w would be ~30× slower on a typical
                # schematic with <5% skeleton coverage.
                nz_indices = np.flatnonzero(cycle_mask.ravel())
                nz_labels = labeled.ravel()[nz_indices]
                order = np.argsort(nz_labels, kind="stable")
                sorted_labels = nz_labels[order]
                sorted_indices = nz_indices[order]
                first_positions = np.concatenate(
                    ([0], np.flatnonzero(np.diff(sorted_labels)) + 1)
                )
                for s in sorted_indices[first_positions].tolist():
                    s = int(s)
                    if not live[s]:
                        continue  # cleared by an earlier cycle walk
                    di = lowest[live[s]]
                    cur = s + dir_deltas[di]
                    live[s] &= 0xFF ^ (1 << di)
                    live[cur] &= 0xFF ^ (1 << opposite[di])
                    chain = [s, cur]
                    while cur != s and live[cur]:
                        ex = lowest[live[cur]]
                        nxt = cur + dir_deltas[ex]
                        live[cur] = 0
                        live[nxt] &= 0xFF ^ (1 << opposite[ex])
                        chain.append(nxt)
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
    pairs = [f"{x:.2f},{y:.2f}" for x, y in combined]
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
