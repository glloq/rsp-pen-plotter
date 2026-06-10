"""String-art algorithm.

Pegs are placed on an ellipse around the region; a single thread then
hops greedily from peg to peg, always choosing the chord that crosses
the most remaining darkness. Each pass "spends" ink along its chord, so
successive chords spread out and the accumulated thread density
reproduces the tone — the classic nail-and-string portrait, emitted as
one continuous polyline (a single pen-down).

Darkness comes from the injected ``_tone`` map when available, else the
binary mask. Work happens at a capped resolution (like the tonal
spiral) so cost stays bounded on large canvases.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class StringArtAlgorithm(RasterAlgorithm):
    """Greedy thread over rim pegs reproducing tone by line density."""

    name: ClassVar[str] = "string_art"
    description: ClassVar[str] = (
        "String art — one continuous thread between rim pegs, chords "
        "stacked greedily where the region is darkest."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="pegs", label="convert.pegs", type="integer",
                   default=96, min=24, max=240, step=4),
        OptionSpec(key="lines", label="convert.lineCount", type="integer",
                   default=350, min=50, max=1500, step=10),
        # Ink subtracted along a chosen chord (0..1) — higher fades the
        # darkness faster, spreading chords out sooner.
        OptionSpec(key="fade", label="convert.fade", type="number",
                   default=0.25, min=0.05, max=1.0, step=0.05),
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
        n_pegs = max(8, int(opts.get("pegs", 96)))
        n_lines = max(1, int(opts.get("lines", 350)))
        fade = min(1.0, max(0.01, float(opts.get("fade", 0.25))))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            residual = (1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)).copy()
            residual *= bool_mask
        else:
            residual = bool_mask.astype(np.float64)

        # Work at a capped resolution; emitted coordinates scale back up.
        work_cap = max(120, int(opts.get("_work_cap", 600)))
        oh, ow = residual.shape
        inv = 1.0
        if max(oh, ow) > work_cap:
            ws = work_cap / float(max(oh, ow))
            inv = 1.0 / ws
            nh, nw = max(2, round(oh * ws)), max(2, round(ow * ws))
            yi = np.clip((np.arange(nh) / ws).astype(np.intp), 0, oh - 1)
            xi = np.clip((np.arange(nw) / ws).astype(np.intp), 0, ow - 1)
            residual = residual[yi][:, xi]
        height, width = residual.shape

        ys, xs = np.where(residual > 0)
        cx, cy = float(xs.mean()), float(ys.mean())
        rx = max(4.0, float(np.abs(xs - cx).max()) + 2.0)
        ry = max(4.0, float(np.abs(ys - cy).max()) + 2.0)
        angles = np.linspace(0.0, 2 * math.pi, n_pegs, endpoint=False)
        peg_x = cx + rx * np.cos(angles)
        peg_y = cy + ry * np.sin(angles)

        # Pre-sample every possible chord once: ``samples`` points per
        # chord, integer pixel indices clipped to the work canvas.
        samples = max(24, int(max(rx, ry)))
        ts = np.linspace(0.0, 1.0, samples)

        def chord_pixels(a: int, b: int) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
            px = peg_x[a] + (peg_x[b] - peg_x[a]) * ts
            py = peg_y[a] + (peg_y[b] - peg_y[a]) * ts
            ix = np.clip(np.round(px).astype(np.intp), 0, width - 1)
            iy = np.clip(np.round(py).astype(np.intp), 0, height - 1)
            return ix, iy

        current = 0
        sequence = [current]
        recent: list[int] = []
        for _ in range(n_lines):
            best_peg, best_score = -1, 0.0
            for cand in range(n_pegs):
                if cand == current or cand in recent:
                    continue
                ix, iy = chord_pixels(current, cand)
                score = float(residual[iy, ix].mean())
                if score > best_score:
                    best_peg, best_score = cand, score
            if best_peg < 0 or best_score <= 1e-4:
                break
            ix, iy = chord_pixels(current, best_peg)
            residual[iy, ix] = np.maximum(residual[iy, ix] - fade, 0.0)
            sequence.append(best_peg)
            # Short tabu list keeps the thread from ping-ponging between
            # the same pair of pegs while residual fades.
            recent.append(current)
            if len(recent) > 2:
                recent.pop(0)
            current = best_peg

        if len(sequence) < 2:
            return group_open + "</g>"
        pts = " ".join(
            f"{peg_x[p] * inv:.2f},{peg_y[p] * inv:.2f}" for p in sequence
        )
        return group_open + f'<polyline points="{pts}"/>' + "</g>"
