"""Grid algorithm.

Fills the region with a square mesh of horizontal *and* vertical pen
strokes clipped to the mask — the woven, graph-paper look. Spacing is
shared by both axes; the result reads as a uniform grid rather than the
single-direction sweep of ``scanlines`` or the diagonal of
``crosshatch``.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _runs(line: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Return ``(start, end)`` index pairs (end exclusive) of True runs."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, v in enumerate(line):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(line)))
    return runs


class GridAlgorithm(RasterAlgorithm):
    """Renders a region as a clipped square grid (horizontal + vertical)."""

    name: ClassVar[str] = "grid"
    description: ClassVar[str] = (
        "Square mesh of horizontal and vertical strokes clipped to the mask."
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
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 6))), opts))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        lines: list[tuple[float, float, float, float]] = []
        # Horizontal strokes: one clipped segment per on-mask run per row.
        for y in range(0, height, spacing):
            for start, end in _runs(bool_mask[y]):
                if end - start >= 2:
                    lines.append((float(start), float(y), float(end - 1), float(y)))
        # Vertical strokes: same sweep down each sampled column.
        for x in range(0, width, spacing):
            for start, end in _runs(bool_mask[:, x]):
                if end - start >= 2:
                    lines.append((float(x), float(start), float(x), float(end - 1)))

        paths = "".join(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            for x1, y1, x2, y2 in lines
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
