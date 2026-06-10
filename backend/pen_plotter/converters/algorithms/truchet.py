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


def _arc_tile(x1: float, y1: float, x2: float, y2: float, flipped: bool) -> str:
    """Two quarter-circle arcs joining the midpoints of adjacent edges.

    The Smith-tile variant: each cell carries two arcs centred on
    opposite corners, so neighbouring tiles chain into smooth winding
    paths instead of straight diagonals.
    """
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    rx, ry = mx - x1, my - y1
    if flipped:
        # Arcs centred on the top-left and bottom-right corners.
        return (
            f'<path d="M {mx:.2f} {y1:.2f} A {rx:.2f} {ry:.2f} 0 0 0 {x1:.2f} {my:.2f}"/>'
            f'<path d="M {mx:.2f} {y2:.2f} A {rx:.2f} {ry:.2f} 0 0 0 {x2:.2f} {my:.2f}"/>'
        )
    # Arcs centred on the top-right and bottom-left corners.
    return (
        f'<path d="M {mx:.2f} {y1:.2f} A {rx:.2f} {ry:.2f} 0 0 1 {x2:.2f} {my:.2f}"/>'
        f'<path d="M {mx:.2f} {y2:.2f} A {rx:.2f} {ry:.2f} 0 0 1 {x1:.2f} {my:.2f}"/>'
    )


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
        # ``diagonal`` is the classic slash maze; ``arc`` swaps each tile
        # for two quarter-circles (the Smith variant — curved labyrinth);
        # ``mixed`` flips a coin per tile.
        OptionSpec(key="tile", label="convert.tile", type="select",
                   default="diagonal", choices=["diagonal", "arc", "mixed"]),
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
        tile = str(opts.get("tile", "diagonal"))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        parts: list[str] = []
        for y in range(0, height, cell):
            for x in range(0, width, cell):
                cy = min(height - 1, y + cell // 2)
                cx = min(width - 1, x + cell // 2)
                if not bool_mask[cy, cx]:
                    continue
                x1f, y1f = float(x), float(y)
                x2f = float(min(width, x + cell))
                y2f = float(min(height, y + cell))
                use_arc = tile == "arc" or (tile == "mixed" and rng.random() < 0.5)
                flipped = rng.random() < 0.5
                if use_arc:
                    parts.append(_arc_tile(x1f, y1f, x2f, y2f, flipped))
                elif flipped:
                    # forward slash: bottom-left → top-right
                    parts.append(
                        f'<line x1="{x1f:.2f}" y1="{y2f:.2f}" x2="{x2f:.2f}" y2="{y1f:.2f}"/>'
                    )
                else:
                    # back slash: top-left → bottom-right
                    parts.append(
                        f'<line x1="{x1f:.2f}" y1="{y1f:.2f}" x2="{x2f:.2f}" y2="{y2f:.2f}"/>'
                    )

        paths = "".join(parts)
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
