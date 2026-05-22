"""Stippling algorithm.

Fills a binary color region with randomly scattered dots whose count scales
with the region area.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class StipplingAlgorithm(RasterAlgorithm):
    """Renders a region as scattered point dots."""

    name: ClassVar[str] = "stippling"
    description: ClassVar[str] = "Fill regions with randomly scattered dots."

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as scattered dots.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex color applied as the dot fill.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``density`` (dots per region pixel, default 0.02),
                ``dot_radius_px`` (default 0.6), and ``seed`` (default 0).

        Returns:
            A single SVG ``<g>...</g>`` group containing the dots.
        """
        opts = options or {}
        density = float(opts.get("density", 0.02))
        radius = float(opts.get("dot_radius_px", 0.6))
        seed = int(opts.get("seed", 0))

        ys, xs = np.nonzero(mask)
        group_open = f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
        if ys.size == 0 or density <= 0.0:
            return group_open + "</g>"

        count = max(1, int(ys.size * density))
        rng = np.random.default_rng(seed)
        idx = rng.choice(ys.size, size=min(count, ys.size), replace=False)
        dots = [
            f'<circle cx="{float(xs[i]) + 0.5:.2f}" '
            f'cy="{float(ys[i]) + 0.5:.2f}" r="{radius:.2f}"/>'
            for i in idx
        ]
        return group_open + "".join(dots) + "</g>"
