"""Circle-packing algorithm.

Greedily packs non-overlapping circles into the region by dart-throwing:
each candidate centre is grown to the largest radius that still fits
inside the mask and clears every previously placed circle. Circles are
drawn as outlines (the pen traces each ring), giving the bubble / foam
fill popular in generative plotter art. A ``seed`` keeps the layout
reproducible.
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
        min_r = max(0.5, float(opts.get("min_radius_px", 1.5)))
        max_r = max(min_r, float(opts.get("max_radius_px", 8.0)))
        gap = max(0.0, float(opts.get("gap_px", 0.6)))
        attempts = max(1, int(opts.get("attempts", 3000)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        ys, xs = np.nonzero(bool_mask)
        circles: list[tuple[float, float, float]] = []
        if ys.size:
            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())
            placed: list[tuple[float, float, float]] = []

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

            for _ in range(attempts):
                cx = rng.uniform(x0, x1)
                cy = rng.uniform(y0, y1)
                if not (0 <= int(cy) < height and 0 <= int(cx) < width):
                    continue
                if not bool_mask[int(cy), int(cx)]:
                    continue
                # Largest radius clearing existing circles.
                allowed = max_r
                for px, py, pr in placed:
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
                    placed.append((cx, cy, r))
            circles = placed

        body = "".join(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>' for cx, cy, r in circles
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.8">' + body + "</g>"
        )
