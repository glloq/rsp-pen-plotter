"""Scanlines algorithm.

Sweeps horizontal lines across the region, optionally modulated into a
sine wave whose amplitude grows in dense areas. The result reads like a
CRT scan or an oscilloscope trace — a graphic style hard to get with the
other algorithms.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class ScanlinesAlgorithm(RasterAlgorithm):
    """Renders a region as horizontal scan lines (optionally sinusoidal)."""

    name: ClassVar[str] = "scanlines"
    description: ClassVar[str] = "Horizontal scan lines clipped to the mask — flat or sinusoidal."

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=4, min=1, max=30, step=0.5),
        OptionSpec(key="wave_amp_px", label="convert.waveAmp", type="number",
                   default=0, min=0, max=20, step=0.5),
        OptionSpec(key="wave_period_px", label="convert.wavePeriod", type="number",
                   default=12, min=2, max=50, step=0.5),
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
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 4))), opts))
        wave_amp = max(0.0, float(opts.get("wave_amp_px", 0.0)))
        wave_period = max(1.0, float(opts.get("wave_period_px", 12.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        polylines: list[list[tuple[float, float]]] = []
        # Walk every ``spacing``-th row and emit one polyline per on-mask run.
        for y in range(0, height, spacing):
            row = bool_mask[y]
            if not row.any():
                continue
            if wave_amp <= 0:
                # Flat lines: a run is fully described by its two
                # endpoints — emitting one vertex per pixel would bloat
                # the SVG (and the G-code) by ~width× for no visual gain.
                delta = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
                starts = np.flatnonzero(delta == 1)
                ends = np.flatnonzero(delta == -1)  # exclusive
                for a, b in zip(starts, ends, strict=True):
                    if b - a >= 2:
                        polylines.append([(float(a), float(y)), (float(b - 1), float(y))])
                continue
            current: list[tuple[float, float]] = []
            for x in range(width):
                if row[x]:
                    offset = (
                        wave_amp * math.sin(2 * math.pi * x / wave_period) if wave_amp > 0 else 0.0
                    )
                    current.append((float(x), float(y) + offset))
                elif current:
                    if len(current) >= 2:
                        polylines.append(current)
                    current = []
            if len(current) >= 2:
                polylines.append(current)

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
