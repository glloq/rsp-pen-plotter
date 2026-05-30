"""Crosshatch algorithm.

Fills the region with parallel pen strokes, optionally with a second set
of strokes at +90° for the cross-hatch effect classic in pen-plotter art.
Each stroke is the on-mask portion of an infinite line; spacing between
lines and the rotation angle are configurable.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _line_segments(
    mask: NDArray[np.bool_],
    angle_deg: float,
    spacing_px: float,
) -> list[tuple[float, float, float, float]]:
    """Return ``(x1, y1, x2, y2)`` segments at ``angle_deg``, spaced ``spacing_px``."""
    height, width = mask.shape
    diag = math.hypot(width, height)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # Lines are parametrised as p0 + t * direction, where direction is along
    # the line and p0 walks along the perpendicular. We sweep the perpendicular
    # axis from -diag to +diag in steps of ``spacing`` and rasterise each.
    segments: list[tuple[float, float, float, float]] = []
    centre_x, centre_y = width / 2.0, height / 2.0
    samples = max(2, int(diag * 2))
    # ``along`` walks the line, ``across`` walks the spacing axis.
    along_t = np.linspace(-diag, diag, samples)
    spacing = max(1.0, spacing_px)
    across_t = np.arange(-diag, diag + spacing, spacing)
    for s in across_t:
        ox = centre_x + s * -sin_t
        oy = centre_y + s * cos_t
        xs = ox + along_t * cos_t
        ys = oy + along_t * sin_t
        # Convert to integer pixel indices, then collect the consecutive runs
        # where the rasterised pixel is inside the mask.
        ix = np.round(xs).astype(np.intp)
        iy = np.round(ys).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        valid = np.zeros_like(inside)
        valid[inside] = mask[iy[inside], ix[inside]]
        # Find maximal True runs in ``valid``.
        run_start: int | None = None
        for i, v in enumerate(valid):
            if v and run_start is None:
                run_start = i
            elif not v and run_start is not None:
                segments.append(
                    (float(xs[run_start]), float(ys[run_start]), float(xs[i - 1]), float(ys[i - 1]))
                )
                run_start = None
        if run_start is not None:
            segments.append(
                (float(xs[run_start]), float(ys[run_start]), float(xs[-1]), float(ys[-1]))
            )
    return segments


class CrosshatchAlgorithm(RasterAlgorithm):
    """Renders a region as parallel (or crossed) pen strokes."""

    name: ClassVar[str] = "crosshatch"
    description: ClassVar[str] = (
        "Fill regions with parallel pen strokes (and optional 90° cross-hatching)."
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
        spacing = floored_spacing(max(1.0, float(opts.get("spacing_px", 4.0))), opts)
        bool_mask = mask.astype(bool)

        # ``angles`` (new) lets monochrome mode stack 1..4 hatch passes
        # inside a single layer to darken a band without changing ink
        # colour. When absent, fall back to the legacy ``angle_deg`` +
        # ``crossed`` pair so existing layer presets and persisted
        # placements keep rendering identically.
        raw_angles = opts.get("angles")
        if raw_angles is None:
            angle = float(opts.get("angle_deg", 45.0))
            angles = [angle, angle + 90.0] if bool(opts.get("crossed", False)) else [angle]
        else:
            angles = [float(a) for a in raw_angles][:4]
            if not angles:
                angles = [float(opts.get("angle_deg", 45.0))]

        segments: list[tuple[float, float, float, float]] = []
        for a in angles:
            segments.extend(_line_segments(bool_mask, a, spacing))

        paths = "".join(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            for x1, y1, x2, y2 in segments
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
