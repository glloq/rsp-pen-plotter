"""Halftone screen algorithm.

Fills a binary color region with a regular grid of dots whose radius scales
with how fully each grid cell is covered by the region.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class HalftoneAlgorithm(RasterAlgorithm):
    """Renders a region as a grid of variable-radius dots."""

    name: ClassVar[str] = "halftone"
    description: ClassVar[str] = "Fill regions with a regular grid of variable-size dots."

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as a halftone dot grid.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex color applied as the dot fill.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``cell_size_px`` (grid spacing, default 6).

        Returns:
            A single SVG ``<g>...</g>`` group containing the dots.
        """
        opts = options or {}
        cell = max(2, int(opts.get("cell_size_px", 6)))
        height, width = mask.shape
        coverage = mask.astype(np.float64)

        dots: list[str] = []
        for y in range(0, height, cell):
            for x in range(0, width, cell):
                block = coverage[y : y + cell, x : x + cell]
                frac = float(block.mean())
                if frac <= 0.0:
                    continue
                radius = (cell / 2.0) * np.sqrt(frac)
                cx = x + block.shape[1] / 2.0
                cy = y + block.shape[0] / 2.0
                dots.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}"/>')

        return (
            f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
            + "".join(dots)
            + "</g>"
        )
