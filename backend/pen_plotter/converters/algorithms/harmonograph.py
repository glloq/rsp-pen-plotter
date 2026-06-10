"""Harmonograph algorithm.

Simulates the Victorian drawing machine: two damped pendulums per axis
trace a single decaying Lissajous-like curve, scaled to the region and
clipped to the mask. Frequency ratio and damping are the operator's
knobs; ``seed`` perturbs the phases so re-rolls give fresh figures. One
continuous stroke (minus mask clipping) — meditative, decorative, and
unmistakably analogue.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class HarmonographAlgorithm(RasterAlgorithm):
    """Damped twin-pendulum curve fitted to the region."""

    name: ClassVar[str] = "harmonograph"
    description: ClassVar[str] = (
        "Harmonograph — a damped twin-pendulum figure traced as one "
        "long decaying stroke."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        # Ratio between the two pendulum frequencies; near-rational values
        # (2.01, 3.0, 1.5) give the classic braided figures.
        OptionSpec(key="freq_ratio", label="convert.freqRatio", type="number",
                   default=2.01, min=1.0, max=5.0, step=0.01),
        OptionSpec(key="damping", label="convert.damping", type="number",
                   default=0.004, min=0.0005, max=0.02, step=0.0005),
        OptionSpec(key="turns", label="convert.turns", type="integer",
                   default=40, min=5, max=150, step=5),
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
        ratio = max(0.1, float(opts.get("freq_ratio", 2.01)))
        damping = max(0.0, float(opts.get("damping", 0.004)))
        turns = max(2, int(opts.get("turns", 40)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        rng = np.random.default_rng(seed)
        p1, p2, p3, p4 = rng.uniform(0, 2 * math.pi, size=4)

        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        ax = (float(xs.max()) - float(xs.min())) / 2.0
        ay = (float(ys.max()) - float(ys.min())) / 2.0

        t_max = turns * 2 * math.pi
        n = min(40000, max(2000, turns * 400))
        t = np.linspace(0.0, t_max, n)
        decay = np.exp(-damping * t)
        # Two pendulums per axis: a primary plus a half-amplitude partner
        # at the ratio'd frequency — the classic lateral harmonograph.
        px = cx + ax * decay * (
            0.7 * np.sin(t + p1) + 0.3 * np.sin(ratio * t + p2)
        )
        py = cy + ay * decay * (
            0.7 * np.sin(ratio * t + p3) + 0.3 * np.sin(t + p4)
        )

        ix = np.round(px).astype(np.intp)
        iy = np.round(py).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        on = np.zeros_like(inside)
        on[inside] = bool_mask[iy[inside], ix[inside]]

        parts: list[str] = []
        run: list[str] = []
        for i in range(n):
            if on[i]:
                run.append(f"{px[i]:.2f},{py[i]:.2f}")
            elif len(run) >= 2:
                parts.append(f'<polyline points="{" ".join(run)}"/>')
                run = []
            else:
                run = []
        if len(run) >= 2:
            parts.append(f'<polyline points="{" ".join(run)}"/>')
        return group_open + "".join(parts) + "</g>"
