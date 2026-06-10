"""Phyllotaxis (Vogel spiral) algorithm.

Places dots along the golden-angle sunflower spiral radiating from the
region centroid: point *n* sits at radius ``c·√n``, angle ``n·137.5°``.
Dot size follows local darkness (from the injected ``_tone`` map when
available, else mask coverage), so the seed-head lattice doubles as a
halftone screen with an organic, botanical look that a square grid
can't produce.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# The golden angle in radians — the irrational rotation that gives
# sunflower heads their uniform, never-aligning packing.
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


class PhyllotaxisAlgorithm(RasterAlgorithm):
    """Golden-angle dot spiral sized by local darkness."""

    name: ClassVar[str] = "phyllotaxis"
    description: ClassVar[str] = (
        "Phyllotaxis — sunflower-spiral dots from the centroid, "
        "sized by local darkness."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        # Average distance between consecutive ring points.
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=7, min=2, max=30, step=0.5),
        OptionSpec(key="dot_radius_px", label="convert.dotRadius", type="number",
                   default=2.5, min=0.3, max=10, step=0.1),
        # Draw rings (outlines) instead of filled dots.
        OptionSpec(key="outline", label="convert.outline", type="boolean",
                   default=False),
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
        spacing = floored_spacing(max(2.0, float(opts.get("spacing_px", 7.0))), opts)
        max_dot = max(0.3, float(opts.get("dot_radius_px", 2.5)))
        outline = bool(opts.get("outline", False))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        if outline:
            attrs = (
                f'fill="none" stroke={quoteattr(color_hex)} '
                f'stroke-width="{stroke_attr_px(opts):.3f}"'
            )
        else:
            attrs = f"fill={quoteattr(color_hex)}"
        group_open = f"<g inkscape:label={quoteattr(label)} {attrs}>"
        if not bool_mask.any():
            return group_open + "</g>"

        tone = opts.get("_tone")
        darkness: NDArray[np.float64] | None = None
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)

        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        max_r = float(np.hypot(xs - cx, ys - cy).max()) + spacing
        # Vogel: r = c·√n with c ≈ spacing/√π keeps neighbouring dots
        # roughly ``spacing`` apart over the whole disk.
        c = spacing / math.sqrt(math.pi)
        n_points = int((max_r / c) ** 2) + 1

        n = np.arange(1, n_points + 1, dtype=np.float64)
        r = c * np.sqrt(n)
        theta = n * _GOLDEN_ANGLE
        px = cx + r * np.cos(theta)
        py = cy + r * np.sin(theta)
        ix = np.round(px).astype(np.intp)
        iy = np.round(py).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        on = np.zeros_like(inside)
        on[inside] = bool_mask[iy[inside], ix[inside]]

        dots: list[str] = []
        for i in np.flatnonzero(on):
            if darkness is not None:
                radius = max_dot * float(darkness[iy[i], ix[i]])
                if radius < 0.15:
                    continue
            else:
                radius = max_dot
            dots.append(
                f'<circle cx="{px[i]:.2f}" cy="{py[i]:.2f}" r="{radius:.2f}"/>'
            )
        return group_open + "".join(dots) + "</g>"
