"""Concentric contours algorithm.

Renders a region as a series of nested outlines, each one ``spacing_px``
inside the previous. The result has a topographic look — useful when the
operator wants depth cues that crosshatch can't produce.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _boundary_polylines(mask: NDArray[np.bool_]) -> list[list[tuple[int, int]]]:
    """Return the outer boundary of ``mask`` as one or more closed polylines.

    We walk between pixel centres: an "edge pixel" is a True pixel with at
    least one False 4-neighbour. The resulting set of edge pixels is grouped
    into connected components (per :func:`scipy.ndimage.label`) and emitted
    as polylines via a simple bounding-box hull. This is deliberately
    approximate — it captures the *shape* of each contour ring without the
    cost of marching-squares — which is exactly what the plotter UX needs.
    """
    try:
        from scipy.ndimage import label as nd_label
    except ImportError:
        return []
    if not mask.any():
        return []
    # 4-neighbour erosion via padding + shifts (cheaper than scipy.morphology
    # since we're already importing scipy.ndimage).
    pad = np.pad(mask, 1, mode="constant", constant_values=False)
    up = pad[:-2, 1:-1]
    down = pad[2:, 1:-1]
    left = pad[1:-1, :-2]
    right = pad[1:-1, 2:]
    border = mask & ~(up & down & left & right)
    if not border.any():
        return []
    components, count = nd_label(border)
    polys: list[list[tuple[int, int]]] = []
    for comp_idx in range(1, count + 1):
        ys, xs = np.where(components == comp_idx)
        if len(xs) < 3:
            continue
        # Order points by angle around the centroid — cheap convex-hull-like
        # sort that gives a plottable closed loop even for non-convex regions.
        cx, cy = float(xs.mean()), float(ys.mean())
        angles = np.arctan2(ys - cy, xs - cx)
        order = np.argsort(angles)
        polys.append([(int(xs[i]), int(ys[i])) for i in order])
    return polys


def _erode(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Binary 4-connected erosion via shifted-AND."""
    pad = np.pad(mask, 1, mode="constant", constant_values=False)
    return mask & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]


class ContoursAlgorithm(RasterAlgorithm):
    """Renders a region as nested offset contours (topographic style)."""

    name: ClassVar[str] = "contours"
    description: ClassVar[str] = (
        "Fill regions with concentric inner outlines — a topographic-map feel."
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
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 4))), opts))
        max_rings = max(1, int(opts.get("max_rings", 20)))
        bool_mask = mask.astype(bool)

        paths: list[str] = []
        current = bool_mask
        for _ in range(max_rings):
            if not current.any():
                break
            for poly in _boundary_polylines(current):
                pts = " ".join(f"{x},{y}" for x, y in poly)
                paths.append(f'<polygon points="{pts}"/>')
            # Erode ``spacing`` times to inset the next ring.
            for _step in range(spacing):
                current = _erode(current)

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linejoin="round">'
            + "".join(paths)
            + "</g>"
        )
