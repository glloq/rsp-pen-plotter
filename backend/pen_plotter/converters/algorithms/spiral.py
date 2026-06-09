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

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class SpiralAlgorithm(RasterAlgorithm):
    """Renders a region as the on-mask portion of an Archimedean spiral."""

    name: ClassVar[str] = "spiral"
    description: ClassVar[str] = (
        "Fill regions with a single Archimedean spiral clipped to the mask."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=4, min=1, max=30, step=0.5),
        OptionSpec(key="samples_per_turn", label="convert.samplesPerTurn",
                   type="integer", default=64, min=16, max=256, step=1),
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
        spacing = floored_spacing(max(1.0, float(opts.get("spacing_px", 4.0))), opts)
        # Samples per turn — denser = smoother curve, slower to compute.
        samples_per_turn = max(16, int(opts.get("samples_per_turn", 64)))
        # Tonal (amplitude-modulated) spiral. The radius wobbles by a sine
        # whose *spatial* wavelength (``wavelength_px``) is constant along
        # the arc; its amplitude tracks local darkness so the single line
        # reads as continuous grey — tight thin line in highlights, a wide
        # space-filling wobble in shadows. Two invariants keep it readable
        # as a spiral rather than noise:
        #   * amplitude is capped to just under half the turn spacing, so
        #     neighbouring turns never collide however dark the tone;
        #   * the phase advances with arc length (not angle), so the waves
        #     keep a constant size from the centre outward instead of
        #     collapsing into a scribble near the middle.
        #
        # Darkness comes from one of two sources:
        #   * ``_tone`` — a per-pixel luminance map (0=black..1=white) the
        #     render pipeline injects for the tonal spiral. Amplitude is
        #     sampled *per point* → one continuous, smoothly-modulated
        #     spiral over the whole image (the iconic "spiral portrait").
        #   * ``wave_amp_px`` — a scalar fallback (per-band recipes / API
        #     callers without a tone map). ``0`` (the default) yields the
        #     plain Archimedean spiral, preserving the line-art use.
        wavelength = max(2.0, float(opts.get("wavelength_px", 8.0)))
        tone = opts.get("_tone")
        max_amp = 0.49 * spacing
        strength = max(0.0, min(1.0, float(opts.get("tone_strength", 1.0))))
        scalar_amp = min(max(0.0, float(opts.get("wave_amp_px", 0.0))), max_amp)
        modulating = tone is not None or scalar_amp > 0.0
        bool_mask = mask.astype(bool)

        if not bool_mask.any():
            return f"<g inkscape:label={quoteattr(label)}></g>"

        # Cap the working resolution so the spiral's turn count, tone and
        # cost stay consistent regardless of the source size / detail tier
        # (``spacing_px`` then always means the same thing). We compute in
        # the downscaled space and scale the emitted coordinates back to
        # the original canvas with ``inv``.
        work_cap = max(200, int(opts.get("_work_cap", 1400)))
        oh, ow = bool_mask.shape
        inv = 1.0
        if max(oh, ow) > work_cap:
            ws = work_cap / float(max(oh, ow))
            inv = 1.0 / ws
            nh, nw = max(1, round(oh * ws)), max(1, round(ow * ws))
            yi = np.clip((np.arange(nh) / ws).astype(np.intp), 0, oh - 1)
            xi = np.clip((np.arange(nw) / ws).astype(np.intp), 0, ow - 1)
            bool_mask = bool_mask[yi][:, xi]
            if tone is not None:
                tone = np.asarray(tone)[yi][:, xi]

        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        max_r = float(np.hypot(xs - cx, ys - cy).max()) + spacing + max_amp
        turns = max(1, int(max_r / spacing))
        # --- Bounded sampling ---------------------------------------------
        # A spiral covering a big canvas with tight spacing has an enormous
        # arc length (≈ π·spacing·turns²); emitting a point per pixel would
        # produce a multi-megabyte path that locks up the live preview. So:
        #   * cap the turn count (widening the spacing to still fill the
        #     region) — keeps a deep zoom / high-detail tier from exploding;
        #   * cap the total sample budget;
        #   * sample with a √-spaced angle so the points are roughly EQUAL
        #     arc length apart (uniform-angle would crowd the centre and
        #     starve the outer turns, aliasing the wobble there);
        #   * coarsen the wobble wavelength to the actual sample step so the
        #     sine never aliases into spikes.
        point_budget = max(2000, int(opts.get("_point_budget", 48000)))
        min_samples_per_turn = 24
        max_turns = max(1, point_budget // min_samples_per_turn)
        if turns > max_turns:
            turns = max_turns
            spacing = max_r / turns
        arc_len = math.pi * spacing * turns * turns
        total_samples = turns * samples_per_turn
        if modulating:
            total_samples = max(total_samples, int(8.0 * arc_len / wavelength))
        total_samples = max(min(total_samples, point_budget), turns * min_samples_per_turn, 2)
        theta_max = turns * 2 * math.pi
        # √-spaced angle → near-constant arc step (arc ∝ θ²).
        t = theta_max * np.sqrt(np.linspace(0.0, 1.0, total_samples))
        # Archimedean spiral: r = (spacing / 2π) * θ.
        r = (spacing / (2 * math.pi)) * t
        if modulating:
            # Cumulative arc length of the un-modulated path → constant
            # spatial-frequency wobble.
            x0 = r * np.cos(t)
            y0 = r * np.sin(t)
            cum = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x0), np.diff(y0)))))
            # Keep ≥4 samples per wobble given the real (max) step.
            step = float(np.max(np.diff(cum))) if cum.size > 1 else wavelength
            eff_wavelength = max(wavelength, 4.0 * step)
            amp: NDArray[np.float64] | float
            if tone is not None:
                # Per-point amplitude from local darkness. Sample the tone
                # map at each base point; off-canvas points read as white
                # (no wobble).
                tone_arr = np.asarray(tone, dtype=np.float64)
                th, tw = tone_arr.shape
                bx = np.clip(np.round(cx + x0).astype(np.intp), 0, tw - 1)
                by = np.clip(np.round(cy + y0).astype(np.intp), 0, th - 1)
                darkness = 1.0 - tone_arr[by, bx]
                amp = strength * max_amp * np.clip(darkness, 0.0, 1.0)
            else:
                amp = scalar_amp
            r = r + amp * np.sin(2 * math.pi * cum / eff_wavelength)
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
                # Scale back to the original canvas (no-op when not capped).
                current.append((float(sx[i]) * inv, float(sy[i]) * inv))
            elif current:
                if len(current) >= 2:
                    polylines.append(current)
                current = []
        if len(current) >= 2:
            polylines.append(current)

        paths = "".join(
            '<polyline points="' + " ".join(f"{x:.2f},{y:.2f}" for x, y in poly) + '"/>'
            for poly in polylines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
