"""Edge tracing algorithm.

Draws only the outer boundary of the region as a single thin outline.
Useful for line-art / technical-drawing styles where infill is not
desired. Conceptually similar to :class:`ContoursAlgorithm` with a
single ring, but optimised for that case and emitting open polylines
instead of closed polygons so connected pen-up segments remain shortest.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _boundary_chains(mask: NDArray[np.bool_]) -> list[list[tuple[int, int]]]:
    """Return the boundary pixels as ordered chains, one per connected ring."""
    try:
        from scipy.ndimage import label as nd_label
    except ImportError:
        return []
    if not mask.any():
        return []
    pad = np.pad(mask, 1, mode="constant", constant_values=False)
    border = mask & ~(
        pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    )
    if not border.any():
        return []
    components, count = nd_label(border)
    chains: list[list[tuple[int, int]]] = []
    for comp_idx in range(1, count + 1):
        ys, xs = np.where(components == comp_idx)
        if len(xs) < 2:
            continue
        cx, cy = float(xs.mean()), float(ys.mean())
        # Sort points by polar angle around the centroid — produces a
        # plausible closed walk for any blob; non-simply-connected shapes get
        # multiple chains because they land in different components.
        angles = np.arctan2(ys - cy, xs - cx)
        order = np.argsort(angles)
        chains.append([(int(xs[i]), int(ys[i])) for i in order])
    return chains


class EdgesAlgorithm(RasterAlgorithm):
    """Renders only the outline of the region (no fill)."""

    name: ClassVar[str] = "edges"
    description: ClassVar[str] = (
        "Trace only the region boundary — a line-art / technical-drawing style."
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
            '<polyline points="' + " ".join(f"{x},{y}" for x, y in chain) + '"/>'
            for chain in chains
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{thickness}" stroke-linejoin="round" '
            f'stroke-linecap="round">'
            + paths
            + "</g>"
        )
