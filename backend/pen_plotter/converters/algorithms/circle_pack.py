"""Circle-packing algorithm.

Greedily packs non-overlapping circles into the region by dart-throwing:
each candidate centre is grown to the largest radius that still fits
inside the mask and clears every previously placed circle. Circles are
drawn as outlines (the pen traces each ring), giving the bubble / foam
fill popular in generative plotter art. A ``seed`` keeps the layout
reproducible.

Overlap tests use a spatial hash grid so each dart is O(1) regardless of
how many circles are already placed — that lets the attempt budget scale
with the region area (``attempts`` defaults to area-proportional) so the
packing actually fills the shape densely instead of plateauing at a few
hundred bubbles.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class CirclePackAlgorithm(RasterAlgorithm):
    """Renders a region as a packing of non-overlapping circle outlines."""

    name: ClassVar[str] = "circle_pack"
    description: ClassVar[str] = (
        "Packs non-overlapping circle outlines into the region — the bubble / foam generative fill."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = options or {}
        min_r = max(0.5, float(opts.get("min_radius_px", 1.2)))
        max_r = max(min_r, float(opts.get("max_radius_px", 8.0)))
        gap = max(0.0, float(opts.get("gap_px", 0.6)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        ys, xs = np.nonzero(bool_mask)
        circles: list[tuple[float, float, float]] = []
        if ys.size:
            # Attempt budget scales with the region area so big shapes get
            # proportionally more darts. The grid below keeps each dart
            # cheap, so a high budget stays fast. ``attempts`` overrides it.
            area = int(ys.size)
            default_attempts = min(150_000, max(6000, area // 2))
            attempts = max(1, int(opts.get("attempts", default_attempts)))

            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())

            # Spatial hash: cell holds the circles whose centre falls in it.
            # Cell size = the largest possible centre distance that can still
            # collide (2·max_r + gap), so a candidate only needs to test the
            # 3×3 block of cells around it.
            cell = max(1.0, 2.0 * max_r + gap)
            grid: dict[tuple[int, int], list[tuple[float, float, float]]] = {}

            def cell_of(px: float, py: float) -> tuple[int, int]:
                return (int(px // cell), int(py // cell))

            def fits_in_mask(cx: float, cy: float, r: float) -> bool:
                # Sample the centre and 8 rim points; cheap and good enough
                # to keep a circle off the region boundary for a texture.
                icx, icy = int(round(cx)), int(round(cy))
                if not (0 <= icx < width and 0 <= icy < height and bool_mask[icy, icx]):
                    return False
                for k in range(8):
                    ang = 2.0 * math.pi * k / 8
                    px = int(round(cx + r * math.cos(ang)))
                    py = int(round(cy + r * math.sin(ang)))
                    if not (0 <= px < width and 0 <= py < height and bool_mask[py, px]):
                        return False
                return True

            # Pre-draw candidate centres in bulk for speed.
            cand_x = rng.uniform(x0, x1, size=attempts)
            cand_y = rng.uniform(y0, y1, size=attempts)
            for i in range(attempts):
                cx = float(cand_x[i])
                cy = float(cand_y[i])
                icx, icy = int(cx), int(cy)
                if not (0 <= icy < height and 0 <= icx < width) or not bool_mask[icy, icx]:
                    continue
                gx, gy = cell_of(cx, cy)
                # Largest radius clearing existing circles in the 3×3 block.
                allowed = max_r
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for px, py, pr in grid.get((gx + dx, gy + dy), ()):
                            d = math.hypot(cx - px, cy - py) - pr - gap
                            if d < allowed:
                                allowed = d
                if allowed < min_r:
                    continue
                # Shrink to stay inside the mask.
                r = allowed
                while r >= min_r and not fits_in_mask(cx, cy, r):
                    r -= 0.5
                if r >= min_r:
                    circles.append((cx, cy, r))
                    grid.setdefault((gx, gy), []).append((cx, cy, r))

        body = "".join(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>' for cx, cy, r in circles
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.8">' + body + "</g>"
        )
