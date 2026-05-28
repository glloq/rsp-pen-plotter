"""Edge tracing algorithm.

Draws the boundary of the region as thin outlines. Useful for line-art /
technical-drawing styles where infill is not desired. Conceptually
similar to :class:`ContoursAlgorithm` with a single ring, but optimised
for that case and emitting open polylines instead of closed polygons so
connected pen-up segments remain shortest.

Boundary extraction follows the *actual* outline using marching-squares
contour tracing (``skimage.measure.find_contours``), which walks each
connected edge — outer rings **and** interior holes — in order. This
preserves the fine detail of line art and complex silhouettes. The
legacy centroid polar-angle sort (kept as a fallback for deployments
without scikit-image) only produced a plausible walk for convex blobs:
on anything with concavities or holes it scrambled the boundary into a
single star-shaped loop, which is what made line drawings look heavily
"simplified".
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _boundary_chains(mask: NDArray[np.bool_]) -> list[list[tuple[float, float]]]:
    """Return ordered boundary chains, one per traced contour.

    Each chain is a list of ``(x, y)`` points following the region
    outline. Uses marching-squares contour tracing when scikit-image is
    available (the common case — it's a hard dependency used by the
    centerline algorithm too); falls back to the centroid polar-angle
    sort otherwise so a deployment without the optional wheel still
    produces *some* outline rather than nothing.
    """
    if not mask.any():
        return []
    try:
        from skimage import measure
    except ImportError:
        return _boundary_chains_polar(mask)

    # Pad by one pixel so contours that touch the array edge still close
    # cleanly; ``find_contours`` traces the iso-0.5 level between the
    # False (0) background and True (1) region. Coordinates come back as
    # (row, col) float pairs in the padded frame.
    padded = np.pad(mask.astype(np.float32), 1, mode="constant", constant_values=0.0)
    chains: list[list[tuple[float, float]]] = []
    for contour in measure.find_contours(padded, 0.5):
        if len(contour) < 2:
            continue
        # Undo the 1-px pad and swap (row, col) → (x, y).
        chains.append([(float(col - 1), float(row - 1)) for row, col in contour])
    return chains


def _boundary_chains_polar(mask: NDArray[np.bool_]) -> list[list[tuple[float, float]]]:
    """Fallback boundary extraction: border pixels sorted by polar angle.

    Only used when scikit-image is unavailable. Produces a rough closed
    walk per connected border component — acceptable for simple convex
    shapes, lossy on anything with concavities.
    """
    try:
        from scipy.ndimage import label as nd_label
    except ImportError:
        return []
    pad = np.pad(mask, 1, mode="constant", constant_values=False)
    border = mask & ~(
        pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    )
    if not border.any():
        return []
    components, count = nd_label(border)
    chains: list[list[tuple[float, float]]] = []
    for comp_idx in range(1, count + 1):
        ys, xs = np.where(components == comp_idx)
        if len(xs) < 2:
            continue
        cx, cy = float(xs.mean()), float(ys.mean())
        angles = np.arctan2(ys - cy, xs - cx)
        order = np.argsort(angles)
        chains.append([(float(xs[i]), float(ys[i])) for i in order])
    return chains


class EdgesAlgorithm(RasterAlgorithm):
    """Renders only the outline of the region (no fill)."""

    name: ClassVar[str] = "edges"
    description: ClassVar[str] = (
        "Trace the region boundary — a line-art / technical-drawing style."
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
        bool_mask = mask.astype(bool)
        chains = _boundary_chains(bool_mask)
        paths = "".join(
            '<polyline points="'
            + " ".join(f"{x:.2f},{y:.2f}" for x, y in chain)
            + '"/>'
            for chain in chains
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{thickness}" stroke-linejoin="round" '
            f'stroke-linecap="round">'
            + paths
            + "</g>"
        )
