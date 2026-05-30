"""Squiggle / wavy lines algorithm.

Horizontal scan lines with a *modulated* sinusoidal wiggle: amplitude
and frequency drift as the pen sweeps across the row, producing the
hand-drawn squiggle look that classic scanlines (uniform sine) can't
match. Two flavours via ``mode``:

- ``constant``  : every line uses the same wiggle parameters — same
  texture as a noisy oscilloscope.
- ``modulated`` : amplitude grows with the local horizontal run length
  so dense areas of the mask get bolder squiggles, mimicking the way a
  hand-drawn shading wiggle gets fatter where it has more room. This is
  the default — it's the variant that reads as ``squiggle`` rather than
  ``noisy lines``.

Unlike ``scanlines``, each on-mask row run becomes a *single* polyline
densified at sub-pixel steps so the wave is smooth even with large
amplitude. Spacing between rows controls darkness the same way it does
for scanlines.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


class SquiggleAlgorithm(RasterAlgorithm):
    """Renders the region as wiggly horizontal scan lines."""

    name: ClassVar[str] = "squiggle"
    description: ClassVar[str] = (
        "Wiggly horizontal lines with amplitude / frequency drift — " "hand-drawn squiggle look."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as wiggly scan lines.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour for the resulting polylines.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``spacing_px`` (row stride, default 4),
                ``amp_px`` (wiggle amplitude, default 1.4),
                ``period_px`` (wiggle wavelength, default 8),
                ``jitter`` (per-row phase / frequency perturbation,
                default 0.4), ``mode`` (``modulated`` / ``constant``,
                default ``modulated``), ``seed`` (RNG seed, default 0).

        Returns:
            A single SVG ``<g>...</g>`` group containing the polylines.
        """
        opts = options or {}
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 4))), opts))
        amp = max(0.1, float(opts.get("amp_px", 1.4)))
        period = max(2.0, float(opts.get("period_px", 8.0)))
        jitter = max(0.0, min(1.0, float(opts.get("jitter", 0.4))))
        mode = str(opts.get("mode", "modulated"))
        seed = int(opts.get("seed", 0))

        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        rng = np.random.default_rng(seed)

        # Sub-pixel sampling step along x: 0.5 px is enough for the
        # amplitudes we expose without producing crazy SVG sizes.
        sample_step = 0.5
        # Per-row phase / period perturbation so neighbouring rows don't
        # ride exactly in sync, which is what makes scan-mode look
        # robotic. Range ±jitter on both phase and frequency.
        row_phases = rng.uniform(0.0, 2.0 * math.pi, size=height)
        row_period_mul = 1.0 + jitter * rng.uniform(-0.5, 0.5, size=height)

        polylines: list[list[tuple[float, float]]] = []
        for y in range(0, height, spacing):
            row = bool_mask[y]
            if not row.any():
                continue
            phase = row_phases[y]
            local_period = max(1.0, period * row_period_mul[y])
            # Walk on-mask runs; each contiguous run becomes one polyline.
            x = 0
            while x < width:
                if not row[x]:
                    x += 1
                    continue
                start = x
                while x < width and row[x]:
                    x += 1
                end = x  # exclusive
                run_len = end - start
                if run_len < 2:
                    continue
                # Modulated amplitude: grows toward the middle of the
                # run and tapers at the edges so squiggles look like
                # they fit the available room.
                if mode == "modulated":
                    eff_amp = amp * min(1.0, run_len / (3.0 * local_period))
                else:
                    eff_amp = amp
                points: list[tuple[float, float]] = []
                xx = float(start)
                while xx <= end - 1:
                    # Sin + small secondary harmonic for non-mechanical
                    # feel. The harmonic adds the dwn-up flick a hand
                    # makes between waves.
                    t = (xx - start) / local_period
                    wiggle = math.sin(2 * math.pi * t + phase) + 0.3 * math.sin(
                        4 * math.pi * t + phase * 1.7
                    )
                    points.append((xx, float(y) + eff_amp * wiggle * 0.7))
                    xx += sample_step
                if len(points) >= 2:
                    polylines.append(points)

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{yy:.2f}" for x, yy in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
