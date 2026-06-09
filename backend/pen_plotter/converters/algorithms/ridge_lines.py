"""Ridge-lines algorithm — the "Joy Division" displaced-line look.

Sweeps horizontal lines across the region and displaces each sample
*upward* by the local darkness, so bright areas stay flat and dark areas
rise into peaks. Unlike ``scanlines`` / ``squiggle`` (which oscillate a
sine along the row), the displacement here is a plain vertical offset —
the classic pulsar-plot ridge texture.

Darkness comes from the injected ``_tone`` luminance map when the
pipeline provides one (tonal portraits), falling back to the binary
mask (inside = full displacement) so the algorithm still reads on
plain colour regions. Optional ``occlude`` hides line portions that
fall behind an earlier (lower) ridge — the classic hidden-line
mountain-range effect, rows are then drawn bottom-up.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


def _smooth(values: NDArray[np.float64], radius: int) -> NDArray[np.float64]:
    """Box-blur ``values`` with the given half-window (edge-padded)."""
    if radius <= 0 or values.size == 0:
        return values
    kernel = np.ones(2 * radius + 1) / (2 * radius + 1)
    padded = np.pad(values, radius, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


class RidgeLinesAlgorithm(RasterAlgorithm):
    """Horizontal lines displaced upward by local darkness."""

    name: ClassVar[str] = "ridge_lines"
    description: ClassVar[str] = (
        "Horizontal lines displaced upward by darkness — the pulsar-plot "
        "ridge / mountain-range texture."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=6, min=2, max=40, step=0.5),
        OptionSpec(key="amp_px", label="convert.waveAmp", type="number",
                   default=10, min=0, max=60, step=1),
        OptionSpec(key="smooth_px", label="convert.smooth", type="integer",
                   default=3, min=0, max=20, step=1),
        OptionSpec(key="occlude", label="convert.hiddenLines", type="boolean",
                   default=True),
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
        spacing = floored_spacing(max(2.0, float(opts.get("spacing_px", 6.0))), opts)
        amp = max(0.0, float(opts.get("amp_px", 10.0)))
        smooth_px = max(0, int(opts.get("smooth_px", 3)))
        occlude = bool(opts.get("occlude", True))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
        else:
            darkness = bool_mask.astype(np.float64)

        xs = np.arange(width, dtype=np.float64)
        rows = np.arange(spacing / 2.0, height, spacing)
        # Bottom-up so each ridge can occlude the ones behind (above) it.
        horizon = np.full(width, np.inf)
        parts: list[str] = []
        for y in rows[::-1]:
            iy = min(height - 1, int(round(y)))
            disp = _smooth(darkness[iy] * amp, smooth_px)
            ys = y - disp
            on = bool_mask[iy].copy()
            if occlude:
                visible = ys < horizon
                np.minimum(horizon, np.where(on, ys, np.inf), out=horizon)
                on &= visible
            # Emit one polyline per contiguous on-mask (and visible) run.
            run_start: int | None = None
            for i in range(width + 1):
                inside = i < width and on[i]
                if inside and run_start is None:
                    run_start = i
                elif not inside and run_start is not None:
                    if i - run_start >= 2:
                        pts = " ".join(
                            f"{xs[j]:.2f},{ys[j]:.2f}" for j in range(run_start, i)
                        )
                        parts.append(f'<polyline points="{pts}"/>')
                    run_start = None
        # Rows were generated back-to-front; order in the SVG is irrelevant
        # for the plotter, so no re-sort needed.
        return group_open + "".join(parts) + "</g>"
