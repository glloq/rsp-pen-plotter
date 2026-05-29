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

        ys, xs = np.where(bool_mask)
        cx, cy = float(xs.mean()), float(ys.mean())
        max_r = float(np.hypot(xs - cx, ys - cy).max()) + spacing + max_amp
        turns = max(1, int(max_r / spacing))
        # Base sampling: ``samples_per_turn`` per revolution. When
        # modulating, lift it so the outermost (longest) turn still gets
        # ~8 samples per wavelength — otherwise the wave aliases into
        # spikes. Total spiral arc length ≈ π·spacing·turns² (sum of the
        # per-turn circumferences); cap the sample count so a tight spiral
        # on a big canvas can't blow up the SVG.
        total_samples = turns * samples_per_turn
        if modulating:
            arc_len = math.pi * spacing * turns * turns
            needed = int(8.0 * arc_len / wavelength)
            total_samples = max(total_samples, min(needed, 40000))
        t = np.linspace(0, turns * 2 * math.pi, total_samples)
        # Archimedean spiral: r = (spacing / 2π) * θ.
        r = (spacing / (2 * math.pi)) * t
        if modulating:
            # Cumulative arc length of the un-modulated path → constant
            # spatial-frequency wobble.
            x0 = r * np.cos(t)
            y0 = r * np.sin(t)
            cum = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(x0), np.diff(y0)))))
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
            r = r + amp * np.sin(2 * math.pi * cum / wavelength)
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
