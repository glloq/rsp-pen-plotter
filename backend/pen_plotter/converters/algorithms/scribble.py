"""Scribble algorithm — sketchy hand-drawn hatching.

Like crosshatch, this sweeps parallel lines across the region and keeps
their on-mask runs; unlike crosshatch, each run is drawn as a *wobbly*
polyline (a smoothed random perpendicular offset along its length) with
a small random *overshoot* past each end. Together these give the loose,
"sketched by hand" feel of a scribble rather than a clean ruled hatch.

Darkness comes from line ``spacing_px`` (tighter = darker) and, like
crosshatch, from stacking multiple ``angles`` in one layer — monochrome
bands lerp the spacing and add a crossing angle on the darkest band.

Reuses crosshatch's ``_line_segments`` run scanner so the on-mask
clipping behaves identically; only the per-segment rendering differs.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.crosshatch import _line_segments


def _scribble_polyline(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    amp: float,
    overshoot: float,
    rng: np.random.Generator,
) -> str | None:
    """Turn a straight segment into a wobbly, overshooting polyline.

    Returns ``None`` for sub-pixel segments (nothing worth drawing).
    """
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1.0:
        return None
    ux, uy = dx / length, dy / length  # along the segment
    px, py = -uy, ux  # perpendicular

    # Random overshoot past each end (sketch lines rarely stop dead on the
    # boundary). Shrink the start, grow the end, both by a random fraction.
    start = -overshoot * float(rng.uniform(0.2, 1.0))
    end = length + overshoot * float(rng.uniform(0.2, 1.0))

    # Sample roughly every 3 px; smooth a random walk so the wobble reads
    # as a loose hand tremor rather than high-frequency noise.
    n = max(2, int(length / 3.0))
    raw = rng.standard_normal(n + 1)
    kernel = np.ones(3) / 3.0
    smooth = np.convolve(raw, kernel, mode="same")
    # Taper the offset to ~0 at the ends so consecutive strokes still meet
    # near the silhouette instead of flaring outward.
    taper = np.sin(np.linspace(0.0, math.pi, n + 1))
    offsets = smooth * taper * amp

    coords = []
    for k in range(n + 1):
        t = k / n
        along = start + (end - start) * t
        bx = x1 + ux * along + px * offsets[k]
        by = y1 + uy * along + py * offsets[k]
        coords.append(f"{bx:.2f},{by:.2f}")
    return '<polyline points="' + " ".join(coords) + '"/>'


class ScribbleAlgorithm(RasterAlgorithm):
    """Renders a region as loose, hand-drawn scribbled hatching."""

    name: ClassVar[str] = "scribble"
    description: ClassVar[str] = (
        "Sketchy hand-drawn hatching — wobbly, overshooting strokes for a loose pencil feel."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as scribbled pen strokes.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour applied to every stroke.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``spacing_px`` (line spacing, default 4),
                ``amp_px`` (perpendicular wobble amplitude, default 1.6),
                ``overshoot_px`` (random end overshoot, default 3),
                ``angles`` (list of 1..4 hatch angles; falls back to
                ``angle_deg`` + ``crossed`` when absent) and ``seed``.

        Returns:
            A single SVG ``<g>...</g>`` group of ``<polyline>`` strokes.
        """
        opts = options or {}
        spacing = floored_spacing(max(1.0, float(opts.get("spacing_px", 4.0))), opts)
        amp = max(0.0, float(opts.get("amp_px", 1.6)))
        overshoot = max(0.0, float(opts.get("overshoot_px", 3.0)))
        stroke_width = stroke_attr_px(opts)
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        # Same angle contract as crosshatch: explicit ``angles`` list wins,
        # otherwise the legacy ``angle_deg`` + ``crossed`` pair.
        raw_angles = opts.get("angles")
        if raw_angles is None:
            angle = float(opts.get("angle_deg", 45.0))
            angles = [angle, angle + 90.0] if bool(opts.get("crossed", False)) else [angle]
        else:
            angles = [float(a) for a in raw_angles][:4]
            if not angles:
                angles = [float(opts.get("angle_deg", 45.0))]

        rng = np.random.default_rng(seed)
        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_width:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
        )

        strokes = []
        for a in angles:
            for x1, y1, x2, y2 in _line_segments(bool_mask, a, spacing):
                poly = _scribble_polyline(x1, y1, x2, y2, amp, overshoot, rng)
                if poly is not None:
                    strokes.append(poly)
        return group_open + "".join(strokes) + "</g>"
