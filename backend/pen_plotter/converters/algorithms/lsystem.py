"""L-system algorithm.

Expands a classic Lindenmayer system, walks it with a turtle, scales
the figure to the region's bounding box and clips it to the mask. Four
curated grammars:

- ``dragon``: the Heighway dragon — one continuous folded stroke.
- ``plant``: a bracketed branching plant (stochastic-free Barnsley
  fern relative) — organic stems and leaves.
- ``koch``: the quadratic Koch island — crystalline coastline loops.
- ``sierpinski``: the Sierpiński arrowhead — one triangle-weave stroke.

``iterations`` trades detail for density; the expansion is hard-capped
so a deep setting can't blow up memory. (The hexagonal Gosper curve
lives in its own ``gosper`` algorithm — it is intentionally not
duplicated here.)
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# name → (axiom, rules, turn angle °, default iterations)
_GRAMMARS: dict[str, tuple[str, dict[str, str], float, int]] = {
    "dragon": ("FX", {"X": "X+YF+", "Y": "-FX-Y"}, 90.0, 11),
    "plant": ("X", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}, 25.0, 5),
    "koch": ("F+F+F+F", {"F": "F+F-F-FF+F+F-F"}, 90.0, 3),
    "sierpinski": ("A", {"A": "B-A-B", "B": "A+B+A"}, 60.0, 7),
}

# Hard cap on the expanded production string — keeps a deep ``iterations``
# from allocating hundreds of MB. ~400k symbols ≈ 200k segments tops.
_MAX_SYMBOLS = 400_000


def _expand(axiom: str, rules: dict[str, str], iterations: int) -> str:
    s = axiom
    for _ in range(iterations):
        expanded = "".join(rules.get(ch, ch) for ch in s)
        if len(expanded) > _MAX_SYMBOLS:
            break
        s = expanded
    return s


def _turtle_polylines(
    program: str, turn_deg: float
) -> list[list[tuple[float, float]]]:
    """Walk the L-system program; brackets push/pop = separate polylines."""
    angle = math.radians(turn_deg)
    heading = -math.pi / 2  # grow upward — matters for the plant
    x = y = 0.0
    stack: list[tuple[float, float, float]] = []
    polylines: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = [(x, y)]
    for ch in program:
        if ch in "FAB":
            x += math.cos(heading)
            y += math.sin(heading)
            current.append((x, y))
        elif ch == "+":
            heading += angle
        elif ch == "-":
            heading -= angle
        elif ch == "[":
            stack.append((x, y, heading))
        elif ch == "]":
            if len(current) >= 2:
                polylines.append(current)
            if stack:
                x, y, heading = stack.pop()
            current = [(x, y)]
    if len(current) >= 2:
        polylines.append(current)
    return polylines


class LSystemAlgorithm(RasterAlgorithm):
    """Classic L-system figures fitted to the region."""

    name: ClassVar[str] = "lsystem"
    description: ClassVar[str] = (
        "L-system — dragon curve, branching plant, Koch island or "
        "Sierpiński arrowhead fitted to the region."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="preset", label="convert.pattern", type="select",
                   default="dragon", choices=["dragon", "plant", "koch", "sierpinski"]),
        # 0 = the preset's tuned depth; 1..12 force a depth (clamped by
        # the symbol cap).
        OptionSpec(key="iterations", label="convert.iterations", type="integer",
                   default=0, min=0, max=12, step=1),
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
        preset = str(opts.get("preset", "dragon"))
        axiom, rules, turn, default_iters = _GRAMMARS.get(preset, _GRAMMARS["dragon"])
        iterations = int(opts.get("iterations", 0)) or default_iters
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        polylines = _turtle_polylines(_expand(axiom, rules, iterations), turn)
        if not polylines:
            return group_open + "</g>"

        # Fit the raw figure into the region's bounding box, preserving
        # aspect, with a small margin.
        all_pts = np.concatenate([np.asarray(p) for p in polylines])
        lo = all_pts.min(axis=0)
        hi = all_pts.max(axis=0)
        span = np.maximum(hi - lo, 1e-9)
        ys, xs = np.where(bool_mask)
        bw = float(xs.max() - xs.min() + 1)
        bh = float(ys.max() - ys.min() + 1)
        scale = 0.96 * min(bw / span[0], bh / span[1])
        ox = xs.min() + (bw - span[0] * scale) / 2.0 - lo[0] * scale
        oy = ys.min() + (bh - span[1] * scale) / 2.0 - lo[1] * scale

        parts: list[str] = []
        for poly in polylines:
            arr = np.asarray(poly)
            px = arr[:, 0] * scale + ox
            py = arr[:, 1] * scale + oy
            # Densify long segments to ~2 px so mask clipping cuts cleanly
            # mid-segment rather than dropping whole strokes.
            run: list[str] = []
            for i in range(len(arr) - 1):
                seg_len = float(np.hypot(px[i + 1] - px[i], py[i + 1] - py[i]))
                steps = max(1, int(seg_len / 2.0))
                ts = np.linspace(0.0, 1.0, steps + 1)[:-1] if i < len(arr) - 2 else \
                    np.linspace(0.0, 1.0, steps + 1)
                for t in ts:
                    gx = px[i] + (px[i + 1] - px[i]) * t
                    gy = py[i] + (py[i + 1] - py[i]) * t
                    igx, igy = int(round(gx)), int(round(gy))
                    if 0 <= igx < width and 0 <= igy < height and bool_mask[igy, igx]:
                        run.append(f"{gx:.2f},{gy:.2f}")
                    else:
                        if len(run) >= 2:
                            parts.append(f'<polyline points="{" ".join(run)}"/>')
                        run = []
            if len(run) >= 2:
                parts.append(f'<polyline points="{" ".join(run)}"/>')
        return group_open + "".join(parts) + "</g>"
