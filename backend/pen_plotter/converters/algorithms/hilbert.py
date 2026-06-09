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


class HilbertFillAlgorithm(RasterAlgorithm):
    """Fills each connected component with a single Hilbert-curve stroke."""

    name: ClassVar[str] = "hilbert"
    description: ClassVar[str] = (
        "Fill regions with a Hilbert space-filling curve — one continuous stroke per region."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="spacing_px", label="convert.spacing", type="number",
                   default=4, min=1, max=30, step=0.5),
        OptionSpec(key="min_run_px", label="convert.minRunPx", type="integer",
                   default=3, min=1, max=20, step=1),
        # ``order`` overrides the auto-derived L-system depth; 0 = "auto",
        # 1..8 force that depth. Useful for tuning ink density on small
        # regions where the auto rule under-fills.
        OptionSpec(key="order", label="convert.hilbertOrder", type="integer",
                   default=0, min=0, max=8, step=1),
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
