"""Hitomezashi stitch-pattern algorithm.

The Japanese sashiko stitching pattern: horizontal and vertical dashes
of one cell length, alternating on/off, where each row and each column
carries a random phase bit. The emergent texture of interlocking
rectangles reads completely differently from hatching or grids while
costing almost nothing to compute. A fixed ``seed`` keeps the pattern
reproducible across re-renders.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class HitomezashiAlgorithm(RasterAlgorithm):
    """Renders a region as a hitomezashi stitch pattern."""

    name: ClassVar[str] = "hitomezashi"
    description: ClassVar[str] = (
        "Hitomezashi sashiko stitches — phase-shifted dash rows and columns "
        "weaving an interlocking textile pattern."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_px", label="convert.cellPx", type="integer",
                   default=8, min=3, max=40, step=1),
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
        cell = int(floored_spacing(max(3, int(opts.get("cell_px", 8))), opts))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        n_rows = height // cell + 2
        n_cols = width // cell + 2
        row_phase = rng.integers(0, 2, size=n_rows)
        col_phase = rng.integers(0, 2, size=n_cols)

        def _on_mask(x0: float, y0: float, x1: float, y1: float) -> bool:
            mx = min(width - 1, max(0, int((x0 + x1) / 2)))
            my = min(height - 1, max(0, int((y0 + y1) / 2)))
            return bool(bool_mask[my, mx])

        lines: list[str] = []
        # Horizontal stitches: row r dashes the cells whose column index
        # matches the row's phase bit.
        for r in range(n_rows):
            y = r * cell
            if y >= height:
                break
            for c in range(n_cols):
                if (c + row_phase[r]) % 2:
                    continue
                x0, x1 = c * cell, min((c + 1) * cell, width)
                if x0 >= width or not _on_mask(x0, y, x1, y):
                    continue
                lines.append(
                    f'<line x1="{x0:.2f}" y1="{y:.2f}" x2="{x1:.2f}" y2="{y:.2f}"/>'
                )
        # Vertical stitches, phase per column.
        for c in range(n_cols):
            x = c * cell
            if x >= width:
                break
            for r in range(n_rows):
                if (r + col_phase[c]) % 2:
                    continue
                y0, y1 = r * cell, min((r + 1) * cell, height)
                if y0 >= height or not _on_mask(x, y0, x, y1):
                    continue
                lines.append(
                    f'<line x1="{x:.2f}" y1="{y0:.2f}" x2="{x:.2f}" y2="{y1:.2f}"/>'
                )

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + "".join(lines)
            + "</g>"
        )
