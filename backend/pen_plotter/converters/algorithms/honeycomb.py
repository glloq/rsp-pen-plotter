"""Honeycomb algorithm.

Tiles the region with flat-top hexagons. Two modes:

- ``grid``: a continuous honeycomb lattice clipped to the mask — the
  hexagonal counterpart of the square mesh, with no doubled edges
  (each cell only draws its three "leading" sides).
- ``scaled``: each cell shrinks toward its centre by the local darkness
  (from ``_tone`` when available, else mask coverage) — a hex-cell
  halftone where the lattice dissolves in highlights.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Flat-top hexagon corner angles (0° = east, counter-clockwise).
_CORNERS = [math.radians(60 * i) for i in range(6)]


class HoneycombAlgorithm(RasterAlgorithm):
    """Hexagonal lattice fill, optionally tone-scaled per cell."""

    name: ClassVar[str] = "honeycomb"
    description: ClassVar[str] = (
        "Honeycomb — hexagonal lattice clipped to the region, or "
        "tone-scaled hex cells in 'scaled' mode."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_mm", label="convert.cellPx", type="number",
                   default=4.5, min=1.5, max=22, step=0.1),
        OptionSpec(key="mode", label="convert.mode", type="select",
                   default="grid", choices=["grid", "scaled"]),
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
        radius = float(floored_spacing(max(4, int(opts.get("cell_px", 12))), opts))
        mode = str(opts.get("mode", "grid"))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        tone = opts.get("_tone")
        darkness: NDArray[np.float64] | None = None
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)

        parts: list[str] = []
        # Flat-top axial layout: column step 1.5·R, row step √3·R, odd
        # columns offset by half a row.
        col_step = 1.5 * radius
        row_step = math.sqrt(3.0) * radius
        n_cols = int(width / col_step) + 2
        n_rows = int(height / row_step) + 2
        for col in range(n_cols):
            cx = col * col_step
            y_off = (col % 2) * row_step / 2.0
            for row in range(n_rows):
                cy = row * row_step + y_off
                ix = min(width - 1, max(0, int(cx)))
                iy = min(height - 1, max(0, int(cy)))
                if not bool_mask[iy, ix]:
                    continue
                if mode == "scaled":
                    d = float(darkness[iy, ix]) if darkness is not None else 1.0
                    r = radius * math.sqrt(d)
                    if r < radius * 0.18:
                        continue
                    pts = " ".join(
                        f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}"
                        for a in _CORNERS
                    )
                    parts.append(f'<polygon points="{pts}"/>')
                else:
                    # Continuous lattice: each cell draws only its three
                    # eastern sides so shared walls aren't double-plotted.
                    corners = [
                        (cx + radius * math.cos(a), cy + radius * math.sin(a))
                        for a in _CORNERS
                    ]
                    for i in (5, 0, 1):  # NE, E…SE corner-to-corner walls
                        x1, y1 = corners[i]
                        x2, y2 = corners[(i + 1) % 6]
                        mx = min(width - 1, max(0, int((x1 + x2) / 2)))
                        my = min(height - 1, max(0, int((y1 + y2) / 2)))
                        if bool_mask[my, mx]:
                            parts.append(
                                f'<line x1="{x1:.2f}" y1="{y1:.2f}" '
                                f'x2="{x2:.2f}" y2="{y2:.2f}"/>'
                            )
                    # Western walls only on the lattice rim (no neighbour).
                    for i in (2, 3, 4):
                        x1, y1 = corners[i]
                        x2, y2 = corners[(i + 1) % 6]
                        nx = min(width - 1, max(0, int(cx - col_step)))
                        ny = min(height - 1, max(0, int(cy)))
                        if not bool_mask[ny, nx]:
                            mx = min(width - 1, max(0, int((x1 + x2) / 2)))
                            my = min(height - 1, max(0, int((y1 + y2) / 2)))
                            if bool_mask[my, mx]:
                                parts.append(
                                    f'<line x1="{x1:.2f}" y1="{y1:.2f}" '
                                    f'x2="{x2:.2f}" y2="{y2:.2f}"/>'
                                )

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
            + "".join(parts)
            + "</g>"
        )
