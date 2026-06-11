"""Op-art warped grid algorithm.

A square grid of horizontal + vertical lines pushed around by the
image's tone field: every vertex is displaced along the gradient of the
smoothed darkness map, so the mesh crowds around dark masses and
relaxes in the highlights — the swelling-grid optical illusion
(Bridget Riley territory).

Unlike ``ridge_lines`` (rows displaced straight up by darkness), the
displacement here is the local *gradient vector*, applied to both line
families — the grid bulges radially around features instead of rising
over them.

Without a usable tone map the grid renders perfectly straight, so flat
masks and multicolour cluster regions still get a clean mesh.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import (
    floored_spacing,
    stroke_attr_px,
    tone_darkness,
)
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class WarpGridAlgorithm(RasterAlgorithm):
    """Renders a region as a tone-warped square mesh."""

    name: ClassVar[str] = "warp_grid"
    description: ClassVar[str] = (
        "Op-art mesh — grid lines pushed along the tone gradient, bulging "
        "around dark masses."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.9, min=0.74, max=11, step=0.1),
        OptionSpec(key="strength_mm", label="convert.warpStrength", type="number",
                   default=3.7, min=0.37, max=11, step=0.1),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as a warped mesh.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour for the mesh polylines.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``spacing_px`` (grid pitch, default 5) and
                ``strength_px`` (max displacement, default 10).

        Returns:
            A single SVG ``<g>...</g>`` group containing the mesh.
        """
        opts = options or {}
        spacing = int(floored_spacing(max(2, int(opts.get("spacing_px", 5))), opts))
        strength = max(0.0, float(opts.get("strength_px", 10.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        darkness = tone_darkness(bool_mask, opts)
        if darkness is not None and strength > 0:
            field = darkness * bool_mask
            try:
                from scipy.ndimage import gaussian_filter

                field = gaussian_filter(field, sigma=max(4.0, float(spacing)))
            except ImportError:
                pass  # raw field still warps, just less smoothly
            gy, gx = np.gradient(field)
            magnitude = float(np.hypot(gx, gy).max())
            if magnitude > 1e-9:
                dx = gx * (strength / magnitude)
                dy = gy * (strength / magnitude)
            else:
                darkness = None
        if darkness is None or strength <= 0:
            dx = np.zeros((height, width))
            dy = np.zeros((height, width))

        def warped_runs(base_xs: NDArray[Any], base_ys: NDArray[Any]) -> list[str]:
            """Displace one sampled line, split it on off-mask gaps."""
            ix = np.clip(np.round(base_xs).astype(np.intp), 0, width - 1)
            iy = np.clip(np.round(base_ys).astype(np.intp), 0, height - 1)
            on = bool_mask[iy, ix]
            wx = base_xs + dx[iy, ix]
            wy = base_ys + dy[iy, ix]
            out: list[str] = []
            run: list[str] = []
            for k in range(len(on)):
                if on[k]:
                    run.append(f"{wx[k]:.2f},{wy[k]:.2f}")
                elif len(run) >= 2:
                    out.append('<polyline points="' + " ".join(run) + '"/>')
                    run = []
                else:
                    run = []
            if len(run) >= 2:
                out.append('<polyline points="' + " ".join(run) + '"/>')
            return out

        parts: list[str] = []
        xs_full = np.arange(0, width, dtype=np.float64)
        ys_full = np.arange(0, height, dtype=np.float64)
        for y in range(0, height, spacing):
            parts.extend(warped_runs(xs_full, np.full_like(xs_full, float(y))))
        for x in range(0, width, spacing):
            parts.extend(warped_runs(np.full_like(ys_full, float(x)), ys_full))

        return group_open + "".join(parts) + "</g>"
