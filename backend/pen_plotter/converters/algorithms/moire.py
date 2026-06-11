"""Moiré-interference algorithm.

Superimposes two slightly mismatched copies of a simple pattern so
their interference produces the large-scale moiré fringes op-art is
built on. Two modes:

- ``rings``: two families of concentric circles whose centres are
  offset by ``offset_px`` — the classic two-point interference fringe
  pattern (think ripple tanks).
- ``lines``: two straight-line gratings rotated ±``delta_deg``/2 around
  the hatch angle, beating into wide diagonal fringes.

Both are clipped to the mask. The fringes themselves are an emergent
optical effect — the pen only ever draws plain circles or lines.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm
from pen_plotter.converters.algorithms.crosshatch import _line_segments


class MoireAlgorithm(RasterAlgorithm):
    """Two offset pattern families beating into moiré fringes."""

    name: ClassVar[str] = "moire"
    description: ClassVar[str] = (
        "Moiré interference — two offset ring or line gratings whose "
        "beat pattern forms op-art fringes."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.9, min=0.74, max=7.4, step=0.1),
        OptionSpec(key="mode", label="convert.mode", type="select",
                   default="rings", choices=["rings", "lines"]),
        OptionSpec(key="offset_mm", label="convert.offsetPx", type="number",
                   default=5.2, min=0, max=30, step=0.1),
        OptionSpec(key="delta_deg", label="convert.angleDeg", type="number",
                   default=4, min=0.5, max=20, step=0.5),
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
        spacing = floored_spacing(max(2.0, float(opts.get("spacing_px", 5.0))), opts)
        mode = str(opts.get("mode", "rings"))
        offset = max(0.0, float(opts.get("offset_px", 14.0)))
        delta = max(0.1, float(opts.get("delta_deg", 4.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        parts: list[str] = []
        if mode == "lines":
            for angle in (45.0 - delta / 2.0, 45.0 + delta / 2.0):
                for x1, y1, x2, y2 in _line_segments(bool_mask, angle, spacing):
                    parts.append(
                        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
                    )
            return group_open + "".join(parts) + "</g>"

        # rings: two circle families centred ±offset/2 around the centroid.
        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        max_r = float(np.hypot(xs - cx, ys - cy).max()) + offset + spacing
        for centre_x in (cx - offset / 2.0, cx + offset / 2.0):
            r = spacing
            while r <= max_r:
                # ~1.5 px arc steps keep circles smooth without flooding
                # the SVG with points on big radii.
                n = max(16, int(2 * math.pi * r / 1.5))
                theta = np.linspace(0.0, 2 * math.pi, n, endpoint=True)
                px = centre_x + r * np.cos(theta)
                py = cy + r * np.sin(theta)
                ix = np.round(px).astype(np.intp)
                iy = np.round(py).astype(np.intp)
                inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
                on = np.zeros_like(inside)
                on[inside] = bool_mask[iy[inside], ix[inside]]
                run: list[str] = []
                for i in range(n):
                    if on[i]:
                        run.append(f"{px[i]:.2f},{py[i]:.2f}")
                    elif len(run) >= 2:
                        parts.append(f'<polyline points="{" ".join(run)}"/>')
                        run = []
                    else:
                        run = []
                if len(run) >= 2:
                    parts.append(f'<polyline points="{" ".join(run)}"/>')
                r += spacing
        return group_open + "".join(parts) + "</g>"
