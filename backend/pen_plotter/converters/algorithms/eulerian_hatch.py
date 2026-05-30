"""Eulerian (boustrophedon) hatching algorithm.

Same parallel-stroke geometry as :mod:`crosshatch` but consecutive
sweep-line segments are joined into a continuous zig-zag. Where a
classic crosshatch emits N ``<line>`` elements (= N pen-lifts), this
emits one ``<polyline>`` per hatch *island* — typically a 40–60%
reduction in pen-lift count on a simply-connected region. Reference
for the connection-of-endpoints trick: hatchfill2 Inkscape extension
(GPL — studied only, not vendored).
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _sweep_segments(
    mask: NDArray[np.bool_],
    angle_deg: float,
    spacing_px: float,
) -> list[list[tuple[float, float, float, float]]]:
    """Sweep parallel lines at ``angle_deg`` and return per-sweep segments.

    Unlike :func:`crosshatch._line_segments` this returns segments
    *grouped by sweep line* so the caller can chain consecutive sweeps
    into a boustrophedon polyline.
    """
    height, width = mask.shape
    diag = math.hypot(width, height)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    centre_x, centre_y = width / 2.0, height / 2.0
    samples = max(2, int(diag * 2))
    along_t = np.linspace(-diag, diag, samples)
    spacing = max(1.0, spacing_px)
    across_t = np.arange(-diag, diag + spacing, spacing)
    per_sweep: list[list[tuple[float, float, float, float]]] = []
    for s in across_t:
        ox = centre_x + s * -sin_t
        oy = centre_y + s * cos_t
        xs = ox + along_t * cos_t
        ys = oy + along_t * sin_t
        ix = np.round(xs).astype(np.intp)
        iy = np.round(ys).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        valid = np.zeros_like(inside)
        valid[inside] = mask[iy[inside], ix[inside]]
        segs: list[tuple[float, float, float, float]] = []
        run_start: int | None = None
        for i, v in enumerate(valid):
            if v and run_start is None:
                run_start = i
            elif not v and run_start is not None:
                segs.append(
                    (
                        float(xs[run_start]),
                        float(ys[run_start]),
                        float(xs[i - 1]),
                        float(ys[i - 1]),
                    )
                )
                run_start = None
        if run_start is not None:
            segs.append(
                (
                    float(xs[run_start]),
                    float(ys[run_start]),
                    float(xs[-1]),
                    float(ys[-1]),
                )
            )
        per_sweep.append(segs)
    return per_sweep


def _connect_boustrophedon(
    per_sweep: list[list[tuple[float, float, float, float]]],
    *,
    connect_threshold: float,
) -> list[list[tuple[float, float]]]:
    """Stitch consecutive sweep-line segments into zig-zag polylines.

    Each polyline is one "hatch island" — a maximal run of sweep lines
    that share a single segment whose endpoint sits within
    ``connect_threshold`` pixels of the next sweep's segment endpoint.
    When the mask is concave (multiple segments on one sweep) or the
    sweep produces no segment, the current polyline closes and a new
    one starts.
    """
    polylines: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    last_end: tuple[float, float] | None = None
    flip = False
    for segs in per_sweep:
        if len(segs) != 1:
            # Concave row or empty: close current run.
            if current:
                polylines.append(current)
                current = []
                last_end = None
                flip = False
            # If there are multiple segments on this sweep, emit each as
            # a tiny standalone polyline (better than dropping ink).
            for x1, y1, x2, y2 in segs:
                polylines.append([(x1, y1), (x2, y2)])
            continue
        x1, y1, x2, y2 = segs[0]
        start = (x1, y1)
        end = (x2, y2)
        if flip:
            start, end = end, start
        gap = (
            math.hypot(start[0] - last_end[0], start[1] - last_end[1])
            if last_end is not None
            else float("inf")
        )
        if gap > connect_threshold:
            # Gap too large → start a new polyline.
            if current:
                polylines.append(current)
            current = [start, end]
            flip = True  # next sweep should reverse direction
        else:
            current.append(start)
            current.append(end)
            flip = not flip
        last_end = end
    if current:
        polylines.append(current)
    return polylines


class EulerianHatchAlgorithm(RasterAlgorithm):
    """Boustrophedon-connected parallel hatching."""

    name: ClassVar[str] = "eulerian_hatch"
    description: ClassVar[str] = (
        "Parallel hatches stitched into one continuous zig-zag per island — "
        "drastically fewer pen-lifts than crosshatch."
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
        connect_threshold = float(opts.get("connect_threshold_px", 2.0 * spacing))
        raw_angles = opts.get("angles")
        if raw_angles is None:
            angle = float(opts.get("angle_deg", 45.0))
            angles = [angle, angle + 90.0] if bool(opts.get("crossed", False)) else [angle]
        else:
            angles = [float(a) for a in raw_angles][:4] or [45.0]
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        parts: list[str] = []
        for a in angles:
            sweeps = _sweep_segments(bool_mask, a, spacing)
            polys = _connect_boustrophedon(sweeps, connect_threshold=connect_threshold)
            for poly in polys:
                pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
                parts.append(f'<polyline points="{pts}"/>')
        return group_open + "".join(parts) + "</g>"
