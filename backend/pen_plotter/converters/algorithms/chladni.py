"""Chladni-pattern algorithm.

Traces the nodal lines of a vibrating square plate — the curves where
sand settles in the classic Chladni experiment. The standing-wave field
``cos(nπx)·cos(mπy) − cos(mπx)·cos(nπy)`` is evaluated over the
region's bounding box and its zero-contours are clipped to the mask.
Different ``m`` / ``n`` mode numbers give radically different symmetric
figures; ``modes`` > 1 superimposes extra node lines at intermediate
levels for a denser engraving.

Requires scikit-image (marching squares); degrades to an empty group
without it.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class ChladniAlgorithm(RasterAlgorithm):
    """Nodal lines of a vibrating plate clipped to the region."""

    name: ClassVar[str] = "chladni"
    description: ClassVar[str] = (
        "Chladni figures — nodal lines of a vibrating plate, the "
        "sand-pattern symmetry of resonance experiments."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="m", label="convert.modeM", type="integer",
                   default=3, min=1, max=12, step=1),
        OptionSpec(key="n", label="convert.modeN", type="integer",
                   default=5, min=1, max=12, step=1),
        # Extra contour levels around zero — 1 is the pure nodal set.
        OptionSpec(key="modes", label="convert.levels", type="integer",
                   default=1, min=1, max=7, step=1),
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
        m = max(1, int(opts.get("m", 3)))
        n = max(1, int(opts.get("n", 5)))
        modes = max(1, int(opts.get("modes", 1)))
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

        ys, xs = np.where(bool_mask)
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        bw = max(2, x_max - x_min + 1)
        bh = max(2, y_max - y_min + 1)
        # Evaluate on the bbox at ~1 px resolution (capped for huge
        # canvases — the field is smooth, upsampling artefacts are nil).
        gw = min(bw, 900)
        gh = min(bh, 900)
        u = np.linspace(0.0, 1.0, gw)
        v = np.linspace(0.0, 1.0, gh)
        uu, vv = np.meshgrid(u, v)
        field = (
            np.cos(n * math.pi * uu) * np.cos(m * math.pi * vv)
            - np.cos(m * math.pi * uu) * np.cos(n * math.pi * vv)
        )

        sx = bw / gw
        sy = bh / gh
        amp = float(np.abs(field).max())
        if amp < 1e-9:
            # Degenerate m == n plate: the field is identically zero.
            return group_open + "</g>"
        levels = (
            [0.0]
            if modes == 1
            else list(np.linspace(-0.5 * amp, 0.5 * amp, modes))
        )
        parts: list[str] = []
        for level in levels:
            for contour in find_contours(field, level):
                run: list[str] = []
                for gy, gx in contour:
                    px = x_min + gx * sx
                    py = y_min + gy * sy
                    ix = min(width - 1, max(0, int(round(px))))
                    iy = min(height - 1, max(0, int(round(py))))
                    if bool_mask[iy, ix]:
                        run.append(f"{px:.2f},{py:.2f}")
                    else:
                        if len(run) >= 3:
                            parts.append(f'<polyline points="{" ".join(run)}"/>')
                        run = []
                if len(run) >= 3:
                    parts.append(f'<polyline points="{" ".join(run)}"/>')
        return group_open + "".join(parts) + "</g>"
