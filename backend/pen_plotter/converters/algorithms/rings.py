"""Concentric-rings algorithm.

Draws concentric circles centred on the region's centroid, spaced
``spacing_px`` apart, each clipped to the mask. Where a circle leaves the
region it breaks into separate arcs, so a non-circular shape reads as a
set of nested contour arcs — the "tree-ring" / topographic-target look.

Unlike ``concentric_offset`` (which erodes the *outline* inward), the
rings here are true circles about a single centre, so the texture stays
radial even for irregular shapes.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class RingsAlgorithm(RasterAlgorithm):
    """Renders a region as concentric circles clipped to the mask."""

    name: ClassVar[str] = "rings"
    description: ClassVar[str] = (
        "Concentric circles about the region centroid, clipped to the mask."
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
        spacing = max(1.0, float(opts.get("spacing_px", 6.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        ys, xs = np.nonzero(bool_mask)
        polylines: list[list[tuple[float, float]]] = []
        if ys.size:
            cx = float(xs.mean())
            cy = float(ys.mean())
            max_r = float(np.sqrt(((xs - cx) ** 2 + (ys - cy) ** 2).max()))
            r = spacing
            while r <= max_r:
                # Angular sampling density scales with circumference so the
                # arc stays smooth on large rings without exploding small ones.
                samples = max(24, int(2 * math.pi * r / 2.0))
                theta = np.linspace(0.0, 2.0 * math.pi, samples, endpoint=True)
                px = cx + r * np.cos(theta)
                py = cy + r * np.sin(theta)
                ix = np.round(px).astype(np.intp)
                iy = np.round(py).astype(np.intp)
                inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
                valid = np.zeros(samples, dtype=bool)
                valid[inside] = bool_mask[iy[inside], ix[inside]]
                # Collect contiguous on-mask arcs.
                current: list[tuple[float, float]] = []
                for k in range(samples):
                    if valid[k]:
                        current.append((float(px[k]), float(py[k])))
                    elif len(current) >= 2:
                        polylines.append(current)
                        current = []
                    else:
                        current = []
                if len(current) >= 2:
                    polylines.append(current)
                r += spacing

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.8" stroke-linecap="round">' + paths + "</g>"
        )
