"""Reaction-diffusion (Gray–Scott) algorithm.

Runs a Gray–Scott reaction-diffusion simulation seeded inside the
region and traces the resulting Turing pattern as contour lines. The
feed rate is modulated by local darkness, so the organic
spots-and-stripes texture thickens where the image is dark — coral,
fingerprint and animal-coat patterns that no geometric fill can
imitate. Deterministic for a given ``seed``.

Simulation runs on a capped grid (≤ ``_work_cap`` on the long edge) so
runtime stays bounded; contours are scaled back to canvas coordinates.
Requires scikit-image (marching squares); degrades to an empty group
without it.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# (feed, kill) pairs for the two canonical Gray–Scott regimes.
_PATTERNS = {
    "spots": (0.035, 0.065),
    "stripes": (0.025, 0.056),
}


def _laplacian(arr: NDArray[np.float64]) -> NDArray[np.float64]:
    """5-point Laplacian with edge-replication (no wraparound seams)."""
    padded = np.pad(arr, 1, mode="edge")
    return (
        padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:]
        - 4.0 * arr
    )


class ReactionDiffusionAlgorithm(RasterAlgorithm):
    """Gray–Scott Turing patterns traced as contour lines."""

    name: ClassVar[str] = "reaction_diffusion"
    description: ClassVar[str] = (
        "Reaction-diffusion (Gray–Scott) — organic Turing spots/stripes "
        "grown inside the region, denser where darker."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="pattern", label="convert.pattern", type="select",
                   default="spots", choices=["spots", "stripes"]),
        OptionSpec(key="steps", label="convert.maxSteps", type="integer",
                   default=2500, min=500, max=8000, step=100),
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
        pattern = str(opts.get("pattern", "spots"))
        steps = max(100, int(opts.get("steps", 2500)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"
        try:
            from skimage.measure import find_contours
        except ImportError:
            return group_open + "</g>"

        # Downscale to the simulation grid.
        work_cap = max(64, int(opts.get("_work_cap", 180)))
        oh, ow = bool_mask.shape
        inv = 1.0
        work_mask = bool_mask
        tone = opts.get("_tone")
        tone_arr = None if tone is None else np.asarray(tone, dtype=np.float64)
        if max(oh, ow) > work_cap:
            ws = work_cap / float(max(oh, ow))
            inv = 1.0 / ws
            nh, nw = max(4, round(oh * ws)), max(4, round(ow * ws))
            yi = np.clip((np.arange(nh) / ws).astype(np.intp), 0, oh - 1)
            xi = np.clip((np.arange(nw) / ws).astype(np.intp), 0, ow - 1)
            work_mask = bool_mask[yi][:, xi]
            if tone_arr is not None:
                tone_arr = tone_arr[yi][:, xi]
        height, width = work_mask.shape

        if tone_arr is not None:
            darkness = 1.0 - np.clip(tone_arr, 0.0, 1.0)
        else:
            darkness = work_mask.astype(np.float64)

        feed_base, kill = _PATTERNS.get(pattern, _PATTERNS["spots"])
        # Darker → slightly higher feed → thicker, denser growth.
        feed = feed_base + 0.012 * (darkness - 0.5)

        rng = np.random.default_rng(seed)
        u = np.ones((height, width), dtype=np.float64)
        v = np.zeros((height, width), dtype=np.float64)
        # Seed V with sparse random blobs inside the mask.
        ys, xs = np.where(work_mask)
        n_seeds = max(3, len(xs) // 400)
        for idx in rng.choice(len(xs), size=min(n_seeds, len(xs)), replace=False):
            y0, x0 = ys[idx], xs[idx]
            v[max(0, y0 - 2) : y0 + 3, max(0, x0 - 2) : x0 + 3] = 1.0
        du, dv, dt = 0.16, 0.08, 1.0
        for _ in range(steps):
            uvv = u * v * v
            u += dt * (du * _laplacian(u) - uvv + feed * (1.0 - u))
            v += dt * (dv * _laplacian(v) + uvv - (kill + feed) * v)
            # Keep the chemistry inside the region: V cannot grow off-mask.
            v *= work_mask

        if float(v.max()) < 1e-4:
            return group_open + "</g>"
        level = 0.5 * float(v.max())
        parts: list[str] = []
        for contour in find_contours(v, level):
            pts: list[str] = []
            for cy, cx in contour:
                iy = min(height - 1, max(0, int(round(cy))))
                ix = min(width - 1, max(0, int(round(cx))))
                if work_mask[iy, ix]:
                    pts.append(f"{cx * inv:.2f},{cy * inv:.2f}")
            if len(pts) >= 3:
                parts.append(f'<polyline points="{" ".join(pts)}"/>')
        return group_open + "".join(parts) + "</g>"
