"""Sunburst / radial-rays algorithm.

Emits straight rays fanning out from the region's centroid at evenly
spaced angles, each clipped to the mask. A ray that crosses a concave
part of the shape breaks into separate spokes. The result is the radial
"sunburst" / starburst texture — strong directional lines that converge
on a centre, complementary to the concentric ``rings`` style.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class SunburstAlgorithm(RasterAlgorithm):
    """Renders a region as radial rays from the centroid, clipped to mask."""

    name: ClassVar[str] = "sunburst"
    description: ClassVar[str] = (
        "Radial rays fanning out from the region centroid, clipped to the mask."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="rays", label="convert.rays", type="integer",
                   default=120, min=8, max=720, step=4),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = options or {}
        rays = max(3, int(opts.get("rays", 120)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        ys, xs = np.nonzero(bool_mask)
        polylines: list[list[tuple[float, float]]] = []
        if ys.size:
            cx = float(xs.mean())
            cy = float(ys.mean())
            max_r = float(np.sqrt(((xs - cx) ** 2 + (ys - cy) ** 2).max())) + 1.0
            steps = max(8, int(max_r))
            radii = np.linspace(0.0, max_r, steps)
            for a in range(rays):
                theta = 2.0 * math.pi * a / rays
                px = cx + radii * math.cos(theta)
                py = cy + radii * math.sin(theta)
                ix = np.round(px).astype(np.intp)
                iy = np.round(py).astype(np.intp)
                inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
                valid = np.zeros(steps, dtype=bool)
                valid[inside] = bool_mask[iy[inside], ix[inside]]
                current: list[tuple[float, float]] = []
                for k in range(steps):
                    if valid[k]:
                        current.append((float(px[k]), float(py[k])))
                    elif len(current) >= 2:
                        polylines.append(current)
                        current = []
                    else:
                        current = []
                if len(current) >= 2:
                    polylines.append(current)

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
