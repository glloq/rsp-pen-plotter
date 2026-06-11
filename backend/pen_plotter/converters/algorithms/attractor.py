"""Strange-attractor algorithm.

Iterates a chaotic 2D map (Peter de Jong or Clifford) and scatters its
orbit into the region as pen taps. The orbit's fractal density gives a
smoky, filamentary texture impossible to lay out deterministically.
When a ``_tone`` map is present each point is kept with probability
equal to local darkness, so the attractor doubles as a tonal screen.
``seed`` perturbs the map coefficients — every seed is a different
attractor.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Base coefficient sets known to produce dense, well-spread orbits.
_PRESETS = {
    "dejong": (-2.0, -2.3, -1.2, 2.1),
    "clifford": (-1.4, 1.6, 1.0, 0.7),
}


class AttractorAlgorithm(RasterAlgorithm):
    """Chaotic-map orbit scattered as tone-gated pen taps."""

    name: ClassVar[str] = "attractor"
    description: ClassVar[str] = (
        "Strange attractor — a chaotic orbit (de Jong / Clifford) "
        "scattered into the region as smoky dot filaments."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="preset", label="convert.pattern", type="select",
                   default="dejong", choices=["dejong", "clifford"]),
        OptionSpec(key="points", label="convert.maxPoints", type="integer",
                   default=6000, min=500, max=20000, step=500),
        OptionSpec(key="dot_radius_mm", label="convert.dotRadius", type="number",
                   default=0.19, min=0.07, max=1.1, step=0.1),
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
        preset = str(opts.get("preset", "dejong"))
        max_points = max(100, int(opts.get("points", 6000)))
        radius = max(0.2, float(opts.get("dot_radius_px", 0.5)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
        if not bool_mask.any():
            return group_open + "</g>"

        rng = np.random.default_rng(seed)
        a, b, c, d = _PRESETS.get(preset, _PRESETS["dejong"])
        # Small seeded perturbation: stays within the chaotic regime but
        # reshapes the orbit completely.
        a += float(rng.uniform(-0.15, 0.15))
        b += float(rng.uniform(-0.15, 0.15))
        c += float(rng.uniform(-0.15, 0.15))
        d += float(rng.uniform(-0.15, 0.15))
        clifford = preset == "clifford"

        # Iterate the map. The orbit lives in roughly [-2-|c|, 2+|c|]²;
        # we collect raw points first, then scale into the region bbox.
        budget = max_points * 4  # oversample — mask/tone gating discards
        sin, cos = math.sin, math.cos
        x = y = 0.1
        pts = np.empty((budget, 2), dtype=np.float64)
        for i in range(budget):
            if clifford:
                x, y = (
                    sin(a * y) + c * cos(a * x),
                    sin(b * x) + d * cos(b * y),
                )
            else:
                x, y = sin(a * y) - cos(b * x), sin(c * x) - cos(d * y)
            pts[i, 0] = x
            pts[i, 1] = y

        ys, xs = np.where(bool_mask)
        bx0, bx1 = float(xs.min()), float(xs.max())
        by0, by1 = float(ys.min()), float(ys.max())
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        span = np.maximum(hi - lo, 1e-9)
        px = bx0 + (pts[:, 0] - lo[0]) / span[0] * (bx1 - bx0)
        py = by0 + (pts[:, 1] - lo[1]) / span[1] * (by1 - by0)

        ix = np.clip(np.round(px).astype(np.intp), 0, width - 1)
        iy = np.clip(np.round(py).astype(np.intp), 0, height - 1)
        keep = bool_mask[iy, ix]
        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            keep &= rng.random(budget) < darkness[iy, ix]

        idx = np.flatnonzero(keep)[:max_points]
        dots = "".join(
            f'<circle cx="{px[i]:.2f}" cy="{py[i]:.2f}" r="{radius:.2f}"/>' for i in idx
        )
        return group_open + dots + "</g>"
