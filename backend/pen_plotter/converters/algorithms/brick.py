"""Brick / masonry algorithm.

Fills the region with a running-bond brick pattern: continuous
horizontal mortar lines every ``brick_h`` pixels, plus vertical mortar
ticks every ``brick_w`` pixels within each course. Alternating courses
are offset by half a brick so the verticals stagger like real masonry.
All geometry is clipped to the mask.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.grid import _runs


class BrickAlgorithm(RasterAlgorithm):
    """Renders a region as a running-bond brick wall."""

    name: ClassVar[str] = "brick"
    description: ClassVar[str] = (
        "Running-bond brick pattern: horizontal courses with staggered "
        "vertical mortar joints, clipped to the mask."
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
        brick_h = max(2, int(opts.get("brick_h_px", 8)))
        brick_w = max(2, int(opts.get("brick_w_px", 16)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        lines: list[tuple[float, float, float, float]] = []

        # Horizontal courses: one clipped segment per on-mask run per row.
        for y in range(0, height, brick_h):
            for start, end in _runs(bool_mask[y]):
                if end - start >= 2:
                    lines.append((float(start), float(y), float(end - 1), float(y)))

        # Vertical mortar joints: walk each course band and drop a tick
        # every ``brick_w``, offset half a brick on odd courses. Each tick
        # spans the band height, clipped to the mask column run that holds
        # its midpoint so joints never spill outside the shape.
        for course, y0 in enumerate(range(0, height, brick_h)):
            y1 = min(height, y0 + brick_h)
            offset = (brick_w // 2) if (course % 2) else 0
            mid_y = min(height - 1, (y0 + y1) // 2)
            for x in range(offset, width, brick_w):
                if not bool_mask[mid_y, x]:
                    continue
                # Clip the tick to the contiguous column run at this x that
                # contains the midpoint row.
                col = bool_mask[y0:y1, x]
                # Walk up from the midpoint, then down, to find the run.
                local_mid = mid_y - y0
                up = local_mid
                while up - 1 >= 0 and col[up - 1]:
                    up -= 1
                down = local_mid
                while down + 1 < col.size and col[down + 1]:
                    down += 1
                top, bot = y0 + up, y0 + down
                if bot - top >= 1:
                    lines.append((float(x), float(top), float(x), float(bot)))

        paths = "".join(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            for x1, y1, x2, y2 in lines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.8" stroke-linecap="round">' + paths + "</g>"
        )
