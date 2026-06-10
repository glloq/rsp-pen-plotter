"""Noise-contours (marbling) algorithm.

Draws iso-lines of a scalar field built from the region's darkness plus
a band of smooth procedural noise. The result is a topographic, marbled
texture: contour lines pool tightly around dark features and wander
organically through flat areas — quite unlike ``concentric_offset``,
which erodes the *silhouette* inward and ignores tone entirely.

Iso-line extraction uses ``skimage.measure.find_contours`` (marching
squares); without scikit-image the algorithm degrades to an empty group
(same contract as ``centerline``'s skeleton path).
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


def _smooth_noise(
    shape: tuple[int, int], scale_px: float, octaves: int, rng: np.random.Generator
) -> NDArray[np.float64]:
    """Fractal value noise: stacked, blurred random grids (needs scipy)."""
    from scipy.ndimage import gaussian_filter, zoom

    height, width = shape
    out = np.zeros(shape, dtype=np.float64)
    amp = 1.0
    total = 0.0
    for octave in range(octaves):
        step = max(2.0, scale_px / (2**octave))
        gh = max(2, int(height / step) + 2)
        gw = max(2, int(width / step) + 2)
        grid = rng.standard_normal((gh, gw))
        layer = zoom(grid, (height / gh, width / gw), order=1)[:height, :width]
        # Pad in case the zoom rounded short on either axis.
        if layer.shape != shape:
            padded = np.zeros(shape)
            padded[: layer.shape[0], : layer.shape[1]] = layer
            layer = padded
        out += amp * gaussian_filter(layer, sigma=1.0)
        total += amp
        amp *= 0.5
    return out / total


class NoiseContoursAlgorithm(RasterAlgorithm):
    """Marbled iso-lines of darkness + fractal noise."""

    name: ClassVar[str] = "noise_contours"
    description: ClassVar[str] = (
        "Marbled topography — iso-lines of the image tone warped by "
        "fractal noise, pooling around dark features."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="levels", label="convert.levels", type="integer",
                   default=12, min=3, max=40, step=1),
        OptionSpec(key="noise_scale", label="convert.noiseScale", type="number",
                   default=60, min=10, max=300, step=5),
        OptionSpec(key="noise_amp", label="convert.noiseAmp", type="number",
                   default=0.35, min=0, max=2, step=0.05),
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
        levels = max(2, int(opts.get("levels", 12)))
        noise_scale = max(4.0, float(opts.get("noise_scale", 60.0)))
        noise_amp = max(0.0, float(opts.get("noise_amp", 0.35)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"
        try:
            from skimage.measure import find_contours
        except ImportError:
            return group_open + "</g>"
        try:
            from scipy.ndimage import gaussian_filter  # noqa: F401  (probe for scipy)
        except ImportError:
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
        else:
            # Mask-only fallback: distance transform gives the field some
            # relief so the contours aren't a single binary step.
            from scipy.ndimage import distance_transform_edt

            dist = distance_transform_edt(bool_mask)
            darkness = dist / (dist.max() + 1e-12)

        rng = np.random.default_rng(seed)
        field = darkness + noise_amp * _smooth_noise(
            (height, width), noise_scale, octaves=3, rng=rng
        )

        lo, hi = float(field.min()), float(field.max())
        if hi - lo < 1e-9:
            return group_open + "</g>"
        parts: list[str] = []
        for level in np.linspace(lo, hi, levels + 2)[1:-1]:
            for contour in find_contours(field, level):
                # contour rows are (y, x); clip to the mask and split into
                # on-mask runs so lines stop cleanly at the region edge.
                run: list[tuple[float, float]] = []
                for cy, cx in contour:
                    iy = min(height - 1, max(0, int(round(cy))))
                    ix = min(width - 1, max(0, int(round(cx))))
                    if bool_mask[iy, ix]:
                        run.append((float(cx), float(cy)))
                    elif run:
                        if len(run) >= 3:
                            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in run)
                            parts.append(f'<polyline points="{pts}"/>')
                        run = []
                if len(run) >= 3:
                    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in run)
                    parts.append(f'<polyline points="{pts}"/>')
        return group_open + "".join(parts) + "</g>"
