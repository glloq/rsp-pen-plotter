"""Sine-wave halftone algorithm.

The classic "sound-wave portrait": horizontal waves whose **frequency**
and **amplitude** both follow the local image darkness. Highlights read
as a calm, slow wave; shadows buzz at high frequency with a full swing,
which packs more ink per millimetre and visually thickens the line —
tone becomes waveform, not dot size.

Differs from its two cousins:

- ``scanlines``: fixed-frequency sine, amplitude-only tone response.
- ``squiggle``: randomised hand-tremor wiggle; this one is a clean,
  deterministic oscillator (no jitter, no seed) — the engraved /
  lenticular look.

Phase accumulates continuously along each on-mask run so the frequency
chirps smoothly between tonal regions instead of tearing the waveform.
Without a usable tone map every row falls back to a uniform mid-tone
wave, so the algorithm still renders sensibly on flat masks and
multicolour cluster regions.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import (
    floored_spacing,
    stroke_attr_px,
    tone_darkness,
)
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class SineHalftoneAlgorithm(RasterAlgorithm):
    """Renders the region as tone-driven frequency-modulated waves."""

    name: ClassVar[str] = "sine_halftone"
    description: ClassVar[str] = (
        "Horizontal waves whose frequency and amplitude follow the tone — "
        "the sound-wave portrait."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.9, min=0.74, max=11, step=0.1),
        OptionSpec(key="amp_mm", label="convert.waveAmp", type="number",
                   default=0.74, min=0.07, max=3.7, step=0.1),
        OptionSpec(key="period_mm", label="convert.wavePeriod", type="number",
                   default=1.5, min=0.37, max=7.4, step=0.1),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as frequency-modulated sine rows.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour for the resulting polylines.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``spacing_px`` (row stride, default 5),
                ``amp_px`` (full-darkness amplitude, default 2),
                ``period_px`` (mid-tone wavelength, default 4).

        Returns:
            A single SVG ``<g>...</g>`` group containing the polylines.
        """
        opts = options or {}
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 5))), opts))
        amp = max(0.1, float(opts.get("amp_px", 2.0)))
        period = max(1.0, float(opts.get("period_px", 4.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        # Cap the swing just under half the row pitch so neighbouring
        # rows never collide whatever the operator dials in.
        amp = min(amp, 0.48 * spacing)
        darkness = tone_darkness(bool_mask, opts)

        # Sub-pixel sampling keeps the wave smooth at the highest
        # frequency the modulation can reach (~2.5× the base).
        sample_step = 0.5

        polylines: list[list[tuple[float, float]]] = []
        for y in range(0, height, spacing):
            row = bool_mask[y]
            if not row.any():
                continue
            x = 0
            while x < width:
                if not row[x]:
                    x += 1
                    continue
                start = x
                while x < width and row[x]:
                    x += 1
                end = x  # exclusive
                if end - start < 2:
                    continue
                points: list[tuple[float, float]] = []
                phase = 0.0
                xx = float(start)
                while xx <= end - 1:
                    if darkness is not None:
                        d = float(darkness[y, min(int(xx), width - 1)])
                    else:
                        d = 0.5
                    # Frequency 0.25×..2.5× of the base, amplitude 10..100%
                    # of the cap — both ride the same darkness sample so
                    # shadows buzz and highlights flatten out together.
                    phase += 2 * math.pi * (0.25 + 2.25 * d) * sample_step / period
                    points.append((xx, float(y) + amp * (0.1 + 0.9 * d) * math.sin(phase)))
                    xx += sample_step
                if len(points) >= 2:
                    polylines.append(points)

        paths = "".join(
            '<polyline points="' + " ".join(f"{px:.2f},{py:.2f}" for px, py in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
            + paths
            + "</g>"
        )
