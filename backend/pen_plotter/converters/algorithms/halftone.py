"""Halftone screen algorithm.

Fills a binary color region with a regular grid of dots whose radius scales
with how fully each grid cell is covered by the region.

The screen can be **rotated** (``angle_deg``): in multi-ink work each pen
gets its own screen angle (the classic offset-print convention — cyan 15°,
magenta 75°, yellow 0°, black 45°) so overlapping or adjacent colour
screens interleave into a rosette instead of clashing on a shared grid
(moiré). ``angle_deg == 0`` keeps the original axis-aligned grid exactly.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class HalftoneAlgorithm(RasterAlgorithm):
    """Renders a region as a grid of variable-radius dots."""

    name: ClassVar[str] = "halftone"
    description: ClassVar[str] = (
        "Fill regions with a regular grid of variable-size dots, "
        "optionally rotated to a per-ink screen angle."
    )

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
            options: Optional ``cell_size_px`` (grid spacing, default 6) and
                ``angle_deg`` (screen rotation, default 0).

        Returns:
            A single SVG ``<g>...</g>`` group containing the dots.
        """
        opts = options or {}
        cell = max(2, int(opts.get("cell_size_px", 6)))
        angle = float(opts.get("angle_deg", 0.0))
        coverage = mask.astype(np.float64)

        if abs(angle % 180.0) < 1e-9:
            dots = self._axis_aligned_dots(coverage, cell)
        else:
            dots = self._rotated_dots(coverage, cell, angle)

        return (
            f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
            + "".join(dots)
            + "</g>"
        )

    @staticmethod
    def _axis_aligned_dots(coverage: NDArray[np.float64], cell: int) -> list[str]:
        """Original (unrotated) dot grid — preserved byte-for-byte."""
        height, width = coverage.shape
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
        return dots

    @staticmethod
    def _rotated_dots(coverage: NDArray[np.float64], cell: int, angle_deg: float) -> list[str]:
        """Dot grid sampled on a lattice rotated by ``angle_deg``.

        Dot centres walk a square lattice in the rotated frame; coverage at
        each centre is the mean mask value over a ``cell``×``cell`` window
        (computed in O(1) from a summed-area table), so a partially-covered
        cell still yields a proportionally smaller dot — same tonal mapping
        as the axis-aligned path, just on a turned grid.
        """
        height, width = coverage.shape
        # Summed-area table for O(1) window sums (padded by one row/col).
        sat = np.zeros((height + 1, width + 1), dtype=np.float64)
        sat[1:, 1:] = coverage.cumsum(axis=0).cumsum(axis=1)

        theta = math.radians(angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        cx0, cy0 = width / 2.0, height / 2.0
        half = cell / 2.0
        # The rotated lattice must cover the whole image; the corners reach
        # at most half the diagonal from the centre along either axis.
        limit = math.hypot(width, height) / 2.0 + cell
        coords = np.arange(-limit, limit + cell, cell)

        dots: list[str] = []
        for v in coords:
            for u in coords:
                x = cx0 + u * cos_t - v * sin_t
                y = cy0 + u * sin_t + v * cos_t
                x0 = int(round(x - half))
                y0 = int(round(y - half))
                x1, y1 = x0 + cell, y0 + cell
                # Clip the sampling window to the image.
                cx0i, cy0i = max(0, x0), max(0, y0)
                cx1i, cy1i = min(width, x1), min(height, y1)
                if cx1i <= cx0i or cy1i <= cy0i:
                    continue
                total = sat[cy1i, cx1i] - sat[cy0i, cx1i] - sat[cy1i, cx0i] + sat[cy0i, cx0i]
                area = (cy1i - cy0i) * (cx1i - cx0i)
                frac = total / area
                if frac <= 0.0:
                    continue
                radius = half * math.sqrt(frac)
                dots.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}"/>')
        return dots
