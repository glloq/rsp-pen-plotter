"""Hilbert curve fill algorithm.

A Hilbert space-filling curve is generated over the bounding box of each
connected component, sampled at ``spacing_px`` intervals, then clipped
to the mask. Each contiguous on-mask run becomes one polyline — for a
simply-connected region this is *one* pen-down per region. That's the
strongest pen-lift reduction of any fill algorithm we offer for solid
regions.

Generation uses the canonical iterative ``d2xy`` rotation algorithm
(Wikipedia "Hilbert curve") implemented natively in ~30 lines of numpy.
Bounding boxes are rounded up to the next power of two so the recursion
depth covers the region completely.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


def _d2xy(order: int, d: int) -> tuple[int, int]:
    """Convert distance ``d`` along the Hilbert curve to ``(x, y)``."""
    n = 1 << order
    x = y = 0
    t = d
    s = 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y


def _hilbert_points(order: int) -> NDArray[np.int64]:
    """All ``2**(2*order)`` points along a Hilbert curve of given order."""
    total = 1 << (2 * order)
    out = np.empty((total, 2), dtype=np.int64)
    for d in range(total):
        out[d, 0], out[d, 1] = _d2xy(order, d)
    return out


def _component_polylines(
    mask: NDArray[np.bool_],
    *,
    spacing_px: float,
    min_run_px: int,
    order_override: int | None,
) -> list[list[tuple[float, float]]]:
    try:
        from scipy.ndimage import label as nd_label
    except ImportError:
        return []
    components, count = nd_label(mask)
    polylines: list[list[tuple[float, float]]] = []
    for comp_idx in range(1, count + 1):
        ys, xs = np.where(components == comp_idx)
        if xs.size == 0:
            continue
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        w = x_max - x_min + 1
        h = y_max - y_min + 1
        side = max(w, h)
        if order_override is not None:
            order = max(1, min(10, int(order_override)))
        else:
            order = max(1, math.ceil(math.log2(max(2, side / max(1.0, spacing_px)))))
            order = min(order, 9)
        pts = _hilbert_points(order)
        n = 1 << order
        # Scale curve so consecutive samples are ~spacing_px apart in pixel space.
        cell_w = max(1.0, side / n)
        sx = pts[:, 0].astype(np.float64) * cell_w + x_min + cell_w / 2.0
        sy = pts[:, 1].astype(np.float64) * cell_w + y_min + cell_w / 2.0
        ix = np.round(sx).astype(np.intp)
        iy = np.round(sy).astype(np.intp)
        inside = (ix >= 0) & (ix < mask.shape[1]) & (iy >= 0) & (iy < mask.shape[0])
        on_mask = np.zeros_like(inside)
        on_mask[inside] = mask[iy[inside], ix[inside]]
        run: list[tuple[float, float]] = []
        for k in range(len(on_mask)):
            if on_mask[k]:
                run.append((float(sx[k]), float(sy[k])))
            elif run:
                if len(run) >= max(2, int(min_run_px)):
                    polylines.append(run)
                run = []
        if run and len(run) >= max(2, int(min_run_px)):
            polylines.append(run)
    return polylines


def _adaptive_hilbert(
    x0: float,
    y0: float,
    xi: tuple[float, float],
    yj: tuple[float, float],
    depth: int,
    min_cell: float,
    darkness_mean: Callable[[float, float, float], float],
    out: list[tuple[float, float]],
) -> None:
    """Hilbert traversal that recurses deeper where the cell is darker.

    ``xi`` / ``yj`` are the cell's edge vectors in the curve's local
    frame (the canonical recursive construction). A cell stops splitting
    when it reaches ``min_cell`` or its mean darkness no longer warrants
    the next level — the same darkness > min_cell/size rule the
    ``quadtree`` algorithm uses, so tone maps to local curve density
    while the traversal order keeps the whole path connected.
    """
    size = max(abs(xi[0]) + abs(yj[0]), abs(xi[1]) + abs(yj[1]))
    # 1.4 (not 2.0): lets the darkest cells subdivide all the way down to
    # ~min_cell, matching the non-adaptive curve's density at full black.
    if depth > 0 and size > 1.4 * min_cell:
        cx0 = x0 + min(xi[0], 0.0) + min(yj[0], 0.0)
        cy0 = y0 + min(xi[1], 0.0) + min(yj[1], 0.0)
        if darkness_mean(cx0, cy0, size) > min_cell / size:
            hx, hy = xi[0] / 2.0, xi[1] / 2.0
            jx, jy = yj[0] / 2.0, yj[1] / 2.0
            _adaptive_hilbert(x0, y0, (jx, jy), (hx, hy), depth - 1,
                              min_cell, darkness_mean, out)
            _adaptive_hilbert(x0 + hx, y0 + hy, (hx, hy), (jx, jy), depth - 1,
                              min_cell, darkness_mean, out)
            _adaptive_hilbert(x0 + hx + jx, y0 + hy + jy, (hx, hy), (jx, jy),
                              depth - 1, min_cell, darkness_mean, out)
            _adaptive_hilbert(x0 + hx + 2 * jx, y0 + hy + 2 * jy, (-jx, -jy),
                              (-hx, -hy), depth - 1, min_cell, darkness_mean, out)
            return
    out.append((x0 + (xi[0] + yj[0]) / 2.0, y0 + (xi[1] + yj[1]) / 2.0))


class HilbertFillAlgorithm(RasterAlgorithm):
    """Fills each connected component with a single Hilbert-curve stroke."""

    name: ClassVar[str] = "hilbert"
    description: ClassVar[str] = (
        "Fill regions with a Hilbert space-filling curve — one continuous "
        "stroke per region, optionally tone-adaptive."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.5, min=0.37, max=11, step=0.1),
        OptionSpec(key="min_run_mm", label="convert.minRunPx", type="number",
                   default=1.1, min=0.37, max=7.4, step=0.1),
        # ``order`` overrides the auto-derived L-system depth; 0 = "auto",
        # 1..8 force that depth. Useful for tuning ink density on small
        # regions where the auto rule under-fills.
        OptionSpec(key="order", label="convert.hilbertOrder", type="integer",
                   default=0, min=0, max=8, step=1),
        # Adaptive mode: the curve recurses deeper (tighter) where the
        # region is darker — tone becomes local curve density while the
        # path stays a single connected stroke.
        OptionSpec(key="adaptive", label="convert.adaptive", type="boolean",
                   default=False),
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
        min_run = max(2, int(opts.get("min_run_px", 3)))
        order_override = opts.get("order")
        order_int = int(order_override) if order_override is not None else None
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        if bool(opts.get("adaptive", False)):
            polylines = self._adaptive_polylines(
                bool_mask, opts, spacing_px=spacing, min_run_px=min_run
            )
        else:
            polylines = _component_polylines(
                bool_mask,
                spacing_px=spacing,
                min_run_px=min_run,
                order_override=order_int,
            )
        parts = []
        for poly in polylines:
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
            parts.append(f'<polyline points="{pts}"/>')
        return group_open + "".join(parts) + "</g>"

    @staticmethod
    def _adaptive_polylines(
        mask: NDArray[np.bool_],
        opts: dict[str, Any],
        *,
        spacing_px: float,
        min_run_px: int,
    ) -> list[list[tuple[float, float]]]:
        """Tone-adaptive traversal over the mask's bounding square."""
        height, width = mask.shape
        ys, xs = np.where(mask)
        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())
        side = float(max(x_max - x_min + 1, y_max - y_min + 1))

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            darkness = darkness * mask
        else:
            darkness = mask.astype(np.float64)
        sat = np.zeros((height + 1, width + 1), dtype=np.float64)
        sat[1:, 1:] = darkness.cumsum(axis=0).cumsum(axis=1)

        def darkness_mean(cx0: float, cy0: float, size: float) -> float:
            ax0 = max(0, min(width, int(cx0)))
            ay0 = max(0, min(height, int(cy0)))
            ax1 = max(0, min(width, int(cx0 + size) + 1))
            ay1 = max(0, min(height, int(cy0 + size) + 1))
            area = (ay1 - ay0) * (ax1 - ax0)
            if area <= 0:
                return 0.0
            total = sat[ay1, ax1] - sat[ay0, ax1] - sat[ay1, ax0] + sat[ay0, ax0]
            return float(total / area)

        max_depth = min(9, max(1, math.ceil(math.log2(max(2.0, side / spacing_px)))))
        points: list[tuple[float, float]] = []
        _adaptive_hilbert(
            float(x_min), float(y_min), (side, 0.0), (0.0, side),
            max_depth, max(1.0, spacing_px), darkness_mean, points,
        )

        polylines: list[list[tuple[float, float]]] = []
        run: list[tuple[float, float]] = []
        for px, py in points:
            ix = int(round(px))
            iy = int(round(py))
            if 0 <= ix < width and 0 <= iy < height and mask[iy, ix]:
                run.append((px, py))
            elif run:
                if len(run) >= max(2, min_run_px):
                    polylines.append(run)
                run = []
        if len(run) >= max(2, min_run_px):
            polylines.append(run)
        return polylines
