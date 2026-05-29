"""Spiral fill algorithm.

Draws an Archimedean spiral across the bounding box of the region and
keeps only the on-mask portion. Produces a single connected stroke (when
the region is simply connected) — minimal travel between pen-downs.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class SpiralAlgorithm(RasterAlgorithm):
    """Renders a region as the on-mask portion of an Archimedean spiral."""

    name: ClassVar[str] = "spiral"
    description: ClassVar[str] = (
        "Fill regions with a single Archimedean spiral clipped to the mask."
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
        spacing = max(1.0, float(opts.get("spacing_px", 4.0)))
        # Samples per turn — denser = smoother curve, slower to compute.
        samples_per_turn = max(16, int(opts.get("samples_per_turn", 64)))
        # Tonal (amplitude-modulated) spiral: the radius wobbles by a sine
        # of ``wave_amp_px`` running ``waves_per_turn`` times per turn. The
        # band recipe feeds a *large* amplitude to dark bands and a near-
        # zero one to light bands, so the single spiral reads as continuous
        # grey: tight thin line in highlights, fat wobble in shadows. A
        # zero amplitude (the default) reproduces the plain Archimedean
        # spiral, keeping the binary/line-art use of this algorithm intact.
        wave_amp = max(0.0, float(opts.get("wave_amp_px", 0.0)))
        waves_per_turn = max(1, int(opts.get("waves_per_turn", 12)))
        bool_mask = mask.astype(bool)

        if not bool_mask.any():
            return f"<g inkscape:label={quoteattr(label)}></g>"

        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        max_r = float(np.hypot(xs - cx, ys - cy).max()) + spacing + wave_amp
        turns = max(1, int(max_r / spacing))
        # When modulating, the wave needs enough samples per oscillation or
        # it aliases into jagged spikes — lift the sampling so each wave
        # gets ~8 points, but never below the operator's smoothness knob.
        effective_spt = samples_per_turn
        if wave_amp > 0.0:
            effective_spt = max(samples_per_turn, waves_per_turn * 8)
        total_samples = turns * effective_spt
        t = np.linspace(0, turns * 2 * math.pi, total_samples)
        # Archimedean spiral: r = (spacing / 2π) * θ, plus the tonal wobble.
        r = (spacing / (2 * math.pi)) * t
        if wave_amp > 0.0:
            r = r + wave_amp * np.sin(waves_per_turn * t)
            # Keep the wobble from crossing the centre into negative radius.
            np.clip(r, 0.0, None, out=r)
        sx = cx + r * np.cos(t)
        sy = cy + r * np.sin(t)
        height, width = bool_mask.shape
        ix = np.round(sx).astype(np.intp)
        iy = np.round(sy).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        valid = np.zeros_like(inside)
        valid[inside] = bool_mask[iy[inside], ix[inside]]

        polylines: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for i, v in enumerate(valid):
            if v:
                current.append((float(sx[i]), float(sy[i])))
            elif current:
                if len(current) >= 2:
                    polylines.append(current)
                current = []
        if len(current) >= 2:
            polylines.append(current)

        paths = "".join(
            '<polyline points="'
            + " ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
            + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.8" stroke-linecap="round">'
            + paths
            + "</g>"
        )
