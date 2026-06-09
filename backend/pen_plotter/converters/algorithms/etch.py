"""Etch / engraving-stroke algorithm.

Short pen strokes laid on a grid, each oriented *along* the local
isophote (perpendicular to the tone gradient) with length and presence
driven by darkness — the burin texture of classical engraving and
banknote portraits. Where ``flowfield`` integrates long streamlines,
this stays deliberately short and broken, reading as hand-cut marks.

The orientation field comes from the Sobel gradient of the smoothed
``_tone`` map when available; without a tone map it falls back to the
mask's distance transform, so strokes follow the silhouette.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class EtchAlgorithm(RasterAlgorithm):
    """Short gradient-oriented strokes — the engraving / burin texture."""

    name: ClassVar[str] = "etch"
    description: ClassVar[str] = (
        "Engraving strokes — short marks following the image's isophotes, "
        "denser and longer where darker."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=5, min=2, max=20, step=0.5),
        OptionSpec(key="length_px", label="convert.strokeLen", type="number",
                   default=9, min=2, max=40, step=1),
        OptionSpec(key="jitter", label="convert.jitter", type="number",
                   default=0.3, min=0, max=1, step=0.05),
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
        opts = options or {}
        spacing = floored_spacing(max(2.0, float(opts.get("spacing_px", 5.0))), opts)
        length = max(2.0, float(opts.get("length_px", 9.0)))
        jitter = min(1.0, max(0.0, float(opts.get("jitter", 0.3))))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        try:
            from scipy.ndimage import distance_transform_edt, gaussian_filter, sobel
        except ImportError:
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            field = gaussian_filter(darkness, sigma=2.0)
        else:
            darkness = bool_mask.astype(np.float64)
            # Distance transform: strokes then follow the silhouette rings.
            field = gaussian_filter(distance_transform_edt(bool_mask), sigma=2.0)

        gx = sobel(field, axis=1)
        gy = sobel(field, axis=0)
        # Isophote direction = gradient rotated 90°.
        angle = np.arctan2(gx, -gy)
        magnitude = np.hypot(gx, gy)
        flat = magnitude < (magnitude.max() * 0.02 + 1e-12)

        rng = np.random.default_rng(seed)
        lines: list[str] = []
        for y in np.arange(spacing / 2.0, height, spacing):
            for x in np.arange(spacing / 2.0, width, spacing):
                iy, ix = int(y), int(x)
                if not bool_mask[iy, ix]:
                    continue
                d = float(darkness[iy, ix])
                if d <= 0.06:
                    continue
                # Length tracks darkness; flat areas get a seeded angle so
                # large even fills still read as hand-cut, not combed.
                theta = float(angle[iy, ix])
                if flat[iy, ix]:
                    theta = float(rng.uniform(0, math.pi))
                theta += float(rng.uniform(-1, 1)) * jitter * 0.6
                half = 0.5 * length * (0.35 + 0.65 * d)
                jx = float(rng.uniform(-1, 1)) * jitter * spacing * 0.4
                jy = float(rng.uniform(-1, 1)) * jitter * spacing * 0.4
                cx, cy = x + jx, y + jy
                dx, dy = half * math.cos(theta), half * math.sin(theta)
                lines.append(
                    f'<line x1="{cx - dx:.2f}" y1="{cy - dy:.2f}" '
                    f'x2="{cx + dx:.2f}" y2="{cy + dy:.2f}"/>'
                )
        return group_open + "".join(lines) + "</g>"
