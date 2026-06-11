"""Scallop / fish-scale algorithm.

Rows of overlapping semicircular arcs, staggered half a scale per row —
the roof-tile / mermaid-scale texture. Tone maps to *nesting*: each
scale draws 1..3 concentric arcs depending on the local darkness, so
shadows fill with tight nested ribs while highlights keep a single
clean arc.

Without a usable tone map every scale draws a single arc — the plain
decorative scale fill.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import (
    floored_spacing,
    stroke_attr_px,
    tone_darkness,
)
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Polyline samples per semicircle — plenty for the radii we draw.
_ARC_SAMPLES = 24


class ScallopAlgorithm(RasterAlgorithm):
    """Renders a region as overlapping fish-scale arcs."""

    name: ClassVar[str] = "scallop"
    description: ClassVar[str] = (
        "Fish-scale arcs in staggered rows — darker areas nest extra ribs "
        "inside each scale."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="scale_mm", label="convert.cellSize", type="number",
                   default=4.5, min=1.5, max=15, step=0.1),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as staggered scale arcs.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour for the arc polylines.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``scale_px`` (scale width, default 12).

        Returns:
            A single SVG ``<g>...</g>`` group containing the arcs.
        """
        opts = options or {}
        scale = floored_spacing(max(4.0, float(opts.get("scale_px", 12.0))), opts)
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        darkness = tone_darkness(bool_mask, opts)

        radius = scale / 2.0
        # Rows overlap so the arcs read as tiles; half-scale stagger on
        # odd rows is what makes the pattern weave.
        row_pitch = max(2.0, 0.62 * scale)

        polylines: list[list[tuple[float, float]]] = []

        def emit_arc(cx: float, cy: float, r: float) -> None:
            run: list[tuple[float, float]] = []
            for k in range(_ARC_SAMPLES + 1):
                theta = math.pi * k / _ARC_SAMPLES
                px = cx + r * math.cos(theta)
                py = cy + r * math.sin(theta)
                ix, iy = int(round(px)), int(round(py))
                if 0 <= ix < width and 0 <= iy < height and bool_mask[iy, ix]:
                    run.append((px, py))
                else:
                    if len(run) >= 2:
                        polylines.append(run)
                    run = []
            if len(run) >= 2:
                polylines.append(run)

        row = 0
        y = 0.0
        while y < height + radius:
            x_start = -radius if row % 2 == 0 else -radius + scale / 2.0
            x = x_start
            while x < width + radius:
                ix = min(max(int(x), 0), width - 1)
                iy = min(max(int(y), 0), height - 1)
                if darkness is not None:
                    d = float(darkness[iy, ix]) if bool_mask[iy, ix] else 0.0
                    ribs = 1 + int(d * 2.999)  # 1..3 nested arcs
                else:
                    ribs = 1
                for k in range(ribs):
                    emit_arc(x, y, radius * (1.0 - 0.28 * k))
                x += scale
            y += row_pitch
            row += 1

        paths = "".join(
            '<polyline points="' + " ".join(f"{px:.2f},{py:.2f}" for px, py in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
            + paths
            + "</g>"
        )
