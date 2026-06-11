"""Lichtenberg figure algorithm.

Jagged electric-discharge trees: branches start on the darkest spots and
random-walk through the region, steering toward darker pixels at every
step and forking more often where the image is dark. The result reads
as captured lightning / wood-burning fractals.

Differs from ``space_colonization`` (smooth organic veins relaxing
toward attractor points): this is a forward random walk with hard
angular jitter — branches stay jagged and spiky, the electric look.

Deterministic per ``seed``. Without a usable tone map the walk steers
uniformly and forks at the base rate, so flat masks still grow a
sensible discharge tree.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px, tone_darkness
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Hard global step budget so a huge region with many branches can't run
# away — at the budget the tree just stops growing.
_MAX_TOTAL_STEPS = 24000
# Candidate steering offsets (radians) scored against darkness each step.
_STEER = (-0.6, -0.3, 0.0, 0.3, 0.6)


class LichtenbergAlgorithm(RasterAlgorithm):
    """Renders a region as jagged darkness-seeking discharge trees."""

    name: ClassVar[str] = "lichtenberg"
    description: ClassVar[str] = (
        "Lichtenberg figures — jagged discharge branches seeking the dark, "
        "forking where the image is darkest."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="branches", label="convert.branches", type="integer",
                   default=24, min=2, max=120, step=1),
        OptionSpec(key="step_mm", label="convert.stepPx", type="number",
                   default=1.1, min=0.37, max=3.7, step=0.1),
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
        """Render the region as discharge trees.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour for the branch polylines.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``branches`` (root count, default 24),
                ``step_px`` (segment length, default 3) and ``seed``.

        Returns:
            A single SVG ``<g>...</g>`` group containing the branches.
        """
        opts = options or {}
        roots = max(2, min(120, int(opts.get("branches", 24))))
        step = max(1.0, float(opts.get("step_px", 3.0)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        ys, xs = np.nonzero(bool_mask)
        if ys.size == 0:
            return group_open + "</g>"

        darkness = tone_darkness(bool_mask, opts)
        rng = np.random.default_rng(seed)

        def dark_at(px: float, py: float) -> float:
            ix = min(max(int(px), 0), width - 1)
            iy = min(max(int(py), 0), height - 1)
            if not bool_mask[iy, ix]:
                return -1.0  # off-mask: the walk must stop
            return 0.5 if darkness is None else float(darkness[iy, ix])

        # Roots sampled toward the darkest pixels (squared weighting digs
        # the seeds into the true shadows instead of the mid-tones).
        if darkness is not None:
            weights = np.clip(darkness[ys, xs], 1e-3, None) ** 2
            idx = rng.choice(ys.size, size=min(roots, ys.size), replace=False,
                             p=weights / weights.sum())
        else:
            idx = rng.choice(ys.size, size=min(roots, ys.size), replace=False)

        max_branch_len = max(8, int(math.hypot(width, height) / step / 2))
        budget = _MAX_TOTAL_STEPS
        polylines: list[list[tuple[float, float]]] = []
        # Each stack entry is (x, y, direction, remaining_depth).
        stack: list[tuple[float, float, float, int]] = [
            (float(xs[i]), float(ys[i]), float(rng.uniform(0, 2 * math.pi)), 3) for i in idx
        ]
        while stack and budget > 0:
            x, y, direction, depth = stack.pop()
            points = [(x, y)]
            for _ in range(max_branch_len):
                if budget <= 0:
                    break
                budget -= 1
                # Score a fan of candidate headings by the darkness at
                # their endpoints; jitter keeps the path jagged even
                # across flat tone.
                best_score = -2.0
                best_angle = direction
                for offset in _STEER:
                    a = direction + offset
                    score = dark_at(x + step * math.cos(a), y + step * math.sin(a)) + float(
                        rng.uniform(0, 0.35)
                    )
                    if score > best_score:
                        best_score = score
                        best_angle = a
                if best_score < 0:
                    break  # every candidate leaves the mask
                direction = best_angle + float(rng.uniform(-0.35, 0.35))
                x += step * math.cos(direction)
                y += step * math.sin(direction)
                points.append((x, y))
                d = dark_at(x, y)
                if d < 0:
                    break
                # Fork: more likely in the shadows, never beyond depth.
                if depth > 0 and rng.uniform(0, 1) < 0.06 + 0.22 * max(0.0, d):
                    fork = direction + float(rng.choice((-1.0, 1.0))) * float(
                        rng.uniform(0.5, 1.1)
                    )
                    stack.append((x, y, fork, depth - 1))
            if len(points) >= 2:
                polylines.append(points)

        paths = "".join(
            '<polyline points="' + " ".join(f"{px:.2f},{py:.2f}" for px, py in poly) + '"/>'
            for poly in polylines
        )
        return group_open + paths + "</g>"
