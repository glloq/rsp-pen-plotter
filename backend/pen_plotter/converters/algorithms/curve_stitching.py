"""Curve-stitching (string-art envelope) algorithm.

Each grid cell whose centre lies on-mask gets a fan of straight chords
between two adjacent edges — the classic nail-and-thread construction
whose envelope reads as a smooth parabola without a single curved
stroke. Cell orientation rotates per cell (seeded), so neighbouring
envelopes interlock into a woven, op-art texture.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class CurveStitchingAlgorithm(RasterAlgorithm):
    """Parabolic chord envelopes stitched per grid cell."""

    name: ClassVar[str] = "curve_stitching"
    description: ClassVar[str] = (
        "Curve stitching — per-cell chord fans whose envelopes read as "
        "parabolas, the nail-and-thread op-art texture."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_mm", label="convert.cellPx", type="number",
                   default=6.7, min=3, max=30, step=0.1),
        OptionSpec(key="chords", label="convert.chords", type="integer",
                   default=7, min=3, max=20, step=1),
        OptionSpec(key="seed", label="convert.seed", type="integer",
                   default=0, min=0, step=1),
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
        cell = int(floored_spacing(max(8, int(opts.get("cell_px", 18))), opts))
        chords = max(3, int(opts.get("chords", 7)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        # Fractions along the two legs; chord i runs from t[i] on one leg
        # to t[chords-1-i] on the other — the parabola envelope.
        t = np.linspace(0.0, 1.0, chords + 2)[1:-1]

        lines: list[str] = []
        for y in range(0, height, cell):
            for x in range(0, width, cell):
                my = min(height - 1, y + cell // 2)
                mx = min(width - 1, x + cell // 2)
                if not bool_mask[my, mx]:
                    continue
                x1 = float(min(width, x + cell))
                y1 = float(min(height, y + cell))
                x0, y0 = float(x), float(y)
                # Pick the corner the fan opens from (4 orientations).
                corner = int(rng.integers(4))
                if corner == 0:    # top-left: legs along top + left edges
                    ax, ay = x0 + t * (x1 - x0), np.full_like(t, y0)
                    bx, by = np.full_like(t, x0), y0 + t[::-1] * (y1 - y0)
                elif corner == 1:  # top-right
                    ax, ay = x1 - t * (x1 - x0), np.full_like(t, y0)
                    bx, by = np.full_like(t, x1), y0 + t[::-1] * (y1 - y0)
                elif corner == 2:  # bottom-right
                    ax, ay = x1 - t * (x1 - x0), np.full_like(t, y1)
                    bx, by = np.full_like(t, x1), y1 - t[::-1] * (y1 - y0)
                else:              # bottom-left
                    ax, ay = x0 + t * (x1 - x0), np.full_like(t, y1)
                    bx, by = np.full_like(t, x0), y1 - t[::-1] * (y1 - y0)
                for i in range(chords):
                    lines.append(
                        f'<line x1="{ax[i]:.2f}" y1="{ay[i]:.2f}" '
                        f'x2="{bx[i]:.2f}" y2="{by[i]:.2f}"/>'
                    )

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + "".join(lines)
            + "</g>"
        )
