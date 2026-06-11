"""Superpixel-hatch algorithm.

Segments the region into SLIC superpixels (tone-following patches) and
hatches each patch independently: hatch *angle* follows the patch's
dominant gradient orientation (structure tensor) and hatch *spacing*
follows its mean darkness. The patchwork of differently-angled hatches
reads as a painterly, faceted shading — like brush-block underpainting
— quite different from the single global sweep of ``crosshatch``.

Requires scikit-image (SLIC); degrades to an empty group without it.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm
from pen_plotter.converters.algorithms.crosshatch import _line_segments


class SuperpixelHatchAlgorithm(RasterAlgorithm):
    """Per-superpixel hatching, angle from the local structure tensor."""

    name: ClassVar[str] = "superpixel_hatch"
    description: ClassVar[str] = (
        "Painterly patches — SLIC superpixels each hatched along their "
        "own dominant orientation, spacing from local darkness."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="regions", label="convert.regions", type="integer",
                   default=180, min=20, max=800, step=10),
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.5, min=0.56, max=7.4, step=0.1),
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
        regions = max(8, int(opts.get("regions", 180)))
        spacing = floored_spacing(max(1.5, float(opts.get("spacing_px", 4.0))), opts)
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"
        try:
            from scipy.ndimage import gaussian_filter, sobel
            from skimage.segmentation import slic
        except ImportError:
            return group_open + "</g>"

        # Work at a capped resolution; emitted coordinates scale back.
        work_cap = max(150, int(opts.get("_work_cap", 500)))
        oh, ow = bool_mask.shape
        inv = 1.0
        work_mask = bool_mask
        tone = opts.get("_tone")
        tone_arr = None if tone is None else np.asarray(tone, dtype=np.float64)
        if max(oh, ow) > work_cap:
            ws = work_cap / float(max(oh, ow))
            inv = 1.0 / ws
            nh, nw = max(4, round(oh * ws)), max(4, round(ow * ws))
            yi = np.clip((np.arange(nh) / ws).astype(np.intp), 0, oh - 1)
            xi = np.clip((np.arange(nw) / ws).astype(np.intp), 0, ow - 1)
            work_mask = bool_mask[yi][:, xi]
            if tone_arr is not None:
                tone_arr = tone_arr[yi][:, xi]
        spacing_w = max(1.0, spacing * (1.0 if inv == 1.0 else 1.0 / inv))

        if tone_arr is not None:
            darkness = 1.0 - np.clip(tone_arr, 0.0, 1.0)
        else:
            darkness = work_mask.astype(np.float64)

        labels = slic(
            darkness,
            n_segments=regions,
            compactness=0.08,
            channel_axis=None,
            start_label=1,
            mask=work_mask,
        )

        smoothed = gaussian_filter(darkness, sigma=1.5)
        gx = sobel(smoothed, axis=1)
        gy = sobel(smoothed, axis=0)
        rng = np.random.default_rng(seed)

        parts: list[str] = []
        for region_id in np.unique(labels):
            if region_id == 0:
                continue  # 0 = outside the SLIC mask
            patch = labels == region_id
            d = float(darkness[patch].mean())
            if d <= 0.05:
                continue
            # Structure tensor → dominant gradient orientation; hatch runs
            # along the isophote (perpendicular to the gradient).
            jxx = float((gx[patch] ** 2).mean())
            jyy = float((gy[patch] ** 2).mean())
            jxy = float((gx[patch] * gy[patch]).mean())
            if jxx + jyy < 1e-12:
                theta = float(rng.uniform(0, math.pi))
            else:
                theta = 0.5 * math.atan2(2.0 * jxy, jxx - jyy) + math.pi / 2.0
            # Darker patch → tighter spacing (lerp 2.2× … 0.8× of base).
            patch_spacing = spacing_w * (2.2 - 1.4 * d)
            ys, xs = np.nonzero(patch)
            y0, y1 = ys.min(), ys.max() + 1
            x0, x1 = xs.min(), xs.max() + 1
            sub = patch[y0:y1, x0:x1]
            for sx1, sy1, sx2, sy2 in _line_segments(
                sub, math.degrees(theta), patch_spacing
            ):
                parts.append(
                    f'<line x1="{(sx1 + x0) * inv:.2f}" y1="{(sy1 + y0) * inv:.2f}" '
                    f'x2="{(sx2 + x0) * inv:.2f}" y2="{(sy2 + y0) * inv:.2f}"/>'
                )
        return group_open + "".join(parts) + "</g>"
