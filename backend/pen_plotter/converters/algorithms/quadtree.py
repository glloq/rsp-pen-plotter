"""Quadtree-subdivision algorithm.

Recursively splits the canvas into quadrants, descending deeper where
the region is darker, and draws every leaf cell as a square outline.
Dark areas dissolve into a fine mesh of small cells while light areas
stay as a few large frames — tone becomes structure.

Cell darkness is the mean of the injected ``_tone`` luminance map when
available (tonal portraits), else the mask coverage. Mean lookups use a
summed-area table so each node costs O(1) regardless of size.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class QuadtreeAlgorithm(RasterAlgorithm):
    """Recursive quadrant subdivision driven by local darkness."""

    name: ClassVar[str] = "quadtree"
    description: ClassVar[str] = (
        "Quadtree subdivision — squares split recursively where the region "
        "is darkest, turning tone into cell density."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="min_cell_px", label="convert.minCell", type="integer",
                   default=6, min=2, max=64, step=1),
        # Darkness (0..1) above which a cell keeps splitting. Lower =
        # deeper subdivision = darker, busier texture.
        OptionSpec(key="split_threshold", label="convert.threshold", type="number",
                   default=0.12, min=0.01, max=0.9, step=0.01),
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
        min_cell = int(floored_spacing(max(2, int(opts.get("min_cell_px", 6))), opts))
        threshold = float(opts.get("split_threshold", 0.12))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            # Only shade where the mask owns pixels, so neighbouring
            # layers don't both subdivide over the same dark area.
            darkness = darkness * bool_mask
        else:
            darkness = bool_mask.astype(np.float64)

        sat = np.zeros((height + 1, width + 1), dtype=np.float64)
        sat[1:, 1:] = darkness.cumsum(axis=0).cumsum(axis=1)
        cover = np.zeros((height + 1, width + 1), dtype=np.float64)
        cover[1:, 1:] = bool_mask.astype(np.float64).cumsum(axis=0).cumsum(axis=1)

        def window_mean(table: NDArray[np.float64], x0: int, y0: int, x1: int, y1: int) -> float:
            area = (y1 - y0) * (x1 - x0)
            if area <= 0:
                return 0.0
            total = table[y1, x1] - table[y0, x1] - table[y1, x0] + table[y0, x0]
            return float(total / area)

        rects: list[str] = []
        # Iterative stack — recursion depth is log2(canvas) but a stack
        # keeps the hot loop flat and avoids per-call overhead.
        stack: list[tuple[int, int, int, int]] = [(0, 0, width, height)]
        while stack:
            x0, y0, x1, y1 = stack.pop()
            if window_mean(cover, x0, y0, x1, y1) <= 0.0:
                continue
            size = max(x1 - x0, y1 - y0)
            dark = window_mean(sat, x0, y0, x1, y1)
            if size > 2 * min_cell and dark > threshold:
                mx, my = (x0 + x1) // 2, (y0 + y1) // 2
                stack.extend(
                    ((x0, y0, mx, my), (mx, y0, x1, my),
                     (x0, my, mx, y1), (mx, my, x1, y1))
                )
                continue
            rects.append(
                f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}"/>'
            )
        return group_open + "".join(rects) + "</g>"
