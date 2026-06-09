r"""Truchet-tile algorithm.

Tiles the region with a square grid; each cell whose centre falls inside
the mask gets one randomly chosen diagonal (``/`` or ``\\``). The result
is the classic Truchet maze-like texture — a graphic fill that reads very
differently from hatching or dots. A fixed ``seed`` keeps the pattern
reproducible across re-renders.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class TruchetAlgorithm(RasterAlgorithm):
    """Renders a region as randomly-oriented Truchet diagonal tiles."""

    name: ClassVar[str] = "truchet"
    description: ClassVar[str] = (
        "Truchet tiles — a grid of randomly oriented diagonals making a maze-like graphic fill."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_px", label="convert.cellPx", type="integer",
                   default=10, min=2, max=40, step=1),
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
        cell = int(floored_spacing(max(2, int(opts.get("cell_px", 10))), opts))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        lines: list[tuple[float, float, float, float]] = []
        for y in range(0, height, cell):
            for x in range(0, width, cell):
                cy = min(height - 1, y + cell // 2)
                cx = min(width - 1, x + cell // 2)
                if not bool_mask[cy, cx]:
                    continue
                x1f, y1f = float(x), float(y)
                x2f = float(min(width, x + cell))
                y2f = float(min(height, y + cell))
                if rng.random() < 0.5:
                    # forward slash: bottom-left → top-right
                    lines.append((x1f, y2f, x2f, y1f))
                else:
                    # back slash: top-left → bottom-right
                    lines.append((x1f, y1f, x2f, y2f))

        paths = "".join(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            for x1, y1, x2, y2 in lines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
