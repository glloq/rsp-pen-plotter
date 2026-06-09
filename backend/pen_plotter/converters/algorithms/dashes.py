"""Dashed-hatch algorithm.

Like ``crosshatch`` but every stroke is broken into short dashes — the
stitched / engraving-dash texture. Hatch spacing and angle work as in
crosshatch; ``dash_px`` / ``gap_px`` control the on/off rhythm along
each line.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm
from pen_plotter.converters.algorithms.crosshatch import _line_segments


class DashesAlgorithm(RasterAlgorithm):
    """Renders a region as dashed parallel pen strokes."""

    name: ClassVar[str] = "dashes"
    description: ClassVar[str] = (
        "Dashed hatching — parallel strokes chopped into short dashes "
        "for a stitched / engraving texture."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=5, min=1, max=30, step=0.5),
        OptionSpec(key="angle_deg", label="convert.angleDeg", type="number",
                   default=45, min=0, max=180, step=1),
        OptionSpec(key="dash_px", label="convert.dashPx", type="number",
                   default=3, min=0.5, max=20, step=0.5),
        OptionSpec(key="gap_px", label="convert.gapPx", type="number",
                   default=3, min=0.5, max=20, step=0.5),
        OptionSpec(key="crossed", label="convert.crossed", type="boolean", default=False),
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
        spacing = floored_spacing(max(1.0, float(opts.get("spacing_px", 5.0))), opts)
        angle = float(opts.get("angle_deg", 45.0))
        dash = max(0.5, float(opts.get("dash_px", 3.0)))
        gap = max(0.5, float(opts.get("gap_px", 3.0)))
        crossed = bool(opts.get("crossed", False))
        bool_mask = mask.astype(bool)

        angles = [angle, angle + 90.0] if crossed else [angle]
        segments: list[tuple[float, float, float, float]] = []
        for a in angles:
            segments.extend(_line_segments(bool_mask, a, spacing))

        period = dash + gap
        dashes: list[tuple[float, float, float, float]] = []
        for x1, y1, x2, y2 in segments:
            length = math.hypot(x2 - x1, y2 - y1)
            if length < 0.5:
                continue
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            pos = 0.0
            while pos < length:
                end = min(length, pos + dash)
                dashes.append((x1 + ux * pos, y1 + uy * pos, x1 + ux * end, y1 + uy * end))
                pos += period

        paths = "".join(
            f'<line x1="{dx1:.2f}" y1="{dy1:.2f}" x2="{dx2:.2f}" y2="{dy2:.2f}"/>'
            for dx1, dy1, dx2, dy2 in dashes
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
