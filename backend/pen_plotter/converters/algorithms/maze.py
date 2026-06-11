"""Maze-fill algorithm.

Carves a random depth-first spanning tree over the grid cells whose
centre lies inside the mask, then draws the *walls* that remain between
unconnected neighbours (plus the region's outer rim). The result is a
perfect maze — every corridor reachable, no loops — moulded to the
region's silhouette. A fixed ``seed`` keeps the maze reproducible.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class MazeAlgorithm(RasterAlgorithm):
    """Renders a region as a perfect maze clipped to its silhouette."""

    name: ClassVar[str] = "maze"
    description: ClassVar[str] = (
        "Perfect maze — a random spanning tree carved over the region, "
        "walls drawn between unconnected corridors."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_mm", label="convert.cellPx", type="number",
                   default=3, min=1.1, max=15, step=0.1),
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

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
        )

        n_rows = max(1, height // cell)
        n_cols = max(1, width // cell)
        # A grid cell participates when its centre pixel is on-mask.
        cy = np.minimum(np.arange(n_rows) * cell + cell // 2, height - 1)
        cx = np.minimum(np.arange(n_cols) * cell + cell // 2, width - 1)
        in_cells = bool_mask[np.ix_(cy, cx)]
        if not in_cells.any():
            return group_open + "</g>"

        # Iterative DFS spanning tree. ``opened`` marks carved passages:
        # bit 0 = passage to the east neighbour, bit 1 = to the south.
        visited = np.zeros((n_rows, n_cols), dtype=bool)
        open_east = np.zeros((n_rows, n_cols), dtype=bool)
        open_south = np.zeros((n_rows, n_cols), dtype=bool)
        cells = np.argwhere(in_cells)
        for r0, c0 in cells[rng.permutation(len(cells))]:
            if visited[r0, c0]:
                continue
            stack: list[tuple[int, int]] = [(int(r0), int(c0))]
            visited[r0, c0] = True
            while stack:
                r, c = stack[-1]
                neighbours = []
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nr, nc = r + dr, c + dc
                    if (
                        0 <= nr < n_rows and 0 <= nc < n_cols
                        and in_cells[nr, nc] and not visited[nr, nc]
                    ):
                        neighbours.append((nr, nc))
                if not neighbours:
                    stack.pop()
                    continue
                nr, nc = neighbours[int(rng.integers(len(neighbours)))]
                if nc > c:
                    open_east[r, c] = True
                elif nc < c:
                    open_east[nr, nc] = True
                elif nr > r:
                    open_south[r, c] = True
                else:
                    open_south[nr, nc] = True
                visited[nr, nc] = True
                stack.append((nr, nc))

        def edge(x0: int, y0: int, x1: int, y1: int) -> str:
            return f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}"/>'

        walls: list[str] = []
        for r in range(n_rows):
            for c in range(n_cols):
                if not in_cells[r, c]:
                    continue
                x0, y0 = c * cell, r * cell
                x1, y1 = x0 + cell, y0 + cell
                # North / west rim walls where no in-mask neighbour exists.
                if r == 0 or not in_cells[r - 1, c]:
                    walls.append(edge(x0, y0, x1, y0))
                if c == 0 or not in_cells[r, c - 1]:
                    walls.append(edge(x0, y0, x0, y1))
                # East wall unless a passage was carved or it's the rim.
                if c + 1 < n_cols and in_cells[r, c + 1]:
                    if not open_east[r, c]:
                        walls.append(edge(x1, y0, x1, y1))
                else:
                    walls.append(edge(x1, y0, x1, y1))
                # South wall, same rule.
                if r + 1 < n_rows and in_cells[r + 1, c]:
                    if not open_south[r, c]:
                        walls.append(edge(x0, y1, x1, y1))
                else:
                    walls.append(edge(x0, y1, x1, y1))

        return group_open + "".join(walls) + "</g>"
