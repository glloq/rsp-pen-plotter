"""Cubic-disarray algorithm (after Georg Nees' *Schotter*, 1968).

A grid of square outlines whose rotation and offset jitter grow with the
local darkness: light cells stay neatly aligned, dark cells tumble into
disorder. The canonical generative-art piece ramps the chaos top-to-bottom;
here the ramp follows the region's tone instead, so the disarray *is* the
shading. A fixed ``seed`` keeps the layout reproducible.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class CubicDisarrayAlgorithm(RasterAlgorithm):
    """Square grid whose rotation/offset chaos tracks local darkness."""

    name: ClassVar[str] = "cubic_disarray"
    description: ClassVar[str] = (
        "Cubic disarray (Schotter) — a grid of squares tumbling into "
        "disorder where the region is darkest."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_px", label="convert.cellPx", type="integer",
                   default=12, min=4, max=60, step=1),
        OptionSpec(key="max_rotate_deg", label="convert.rotateMax", type="number",
                   default=35, min=0, max=90, step=1),
        OptionSpec(key="max_offset_px", label="convert.offsetMax", type="number",
                   default=5, min=0, max=30, step=0.5),
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
        cell = int(floored_spacing(max(4, int(opts.get("cell_px", 12))), opts))
        max_rot = math.radians(max(0.0, float(opts.get("max_rotate_deg", 35.0))))
        max_off = max(0.0, float(opts.get("max_offset_px", 5.0)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        tone = opts.get("_tone")
        darkness: NDArray[np.float64] | None = None
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)

        half = cell / 2.0
        parts: list[str] = []
        for y in range(0, height, cell):
            for x in range(0, width, cell):
                block = bool_mask[y : y + cell, x : x + cell]
                if not block.any():
                    continue
                if darkness is not None:
                    chaos = float(darkness[y : y + cell, x : x + cell].mean())
                else:
                    # No tone map: chaos from mask coverage so partial
                    # (edge) cells wobble less than solid ones.
                    chaos = float(block.mean())
                angle = float(rng.uniform(-1, 1)) * max_rot * chaos
                ox = float(rng.uniform(-1, 1)) * max_off * chaos
                oy = float(rng.uniform(-1, 1)) * max_off * chaos
                cx = x + half + ox
                cy = y + half + oy
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                corners = (
                    (-half, -half), (half, -half), (half, half), (-half, half),
                )
                pts = " ".join(
                    f"{cx + u * cos_a - v * sin_a:.2f},{cy + u * sin_a + v * cos_a:.2f}"
                    for u, v in corners
                )
                parts.append(f'<polygon points="{pts}"/>')

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
            + "".join(parts)
            + "</g>"
        )
