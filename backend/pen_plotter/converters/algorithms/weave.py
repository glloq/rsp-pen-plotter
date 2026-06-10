"""Basket-weave algorithm.

Horizontal and vertical ribbons of width ``band_px`` interlaced in a
checkerboard over/under pattern: at every crossing the "under" ribbon's
edge lines break with a small clearance, so the eye reads continuous
strips passing over and under each other. The over/under illusion is
what separates this from a plain ``grid``-style mesh (whose lines all
cross flat).
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class WeaveAlgorithm(RasterAlgorithm):
    """Interlaced over/under ribbons — the basket-weave texture."""

    name: ClassVar[str] = "weave"
    description: ClassVar[str] = (
        "Basket weave — horizontal and vertical ribbons interlacing "
        "over/under at alternating crossings."
    )

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="band_px", label="convert.bandPx", type="integer",
                   default=12, min=4, max=60, step=1),
        OptionSpec(key="gap_px", label="convert.gapPx", type="number",
                   default=2, min=0.5, max=10, step=0.5),
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
        band = int(floored_spacing(max(4, int(opts.get("band_px", 12))), opts))
        gap = max(0.5, float(opts.get("gap_px", 2.0)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        inset = min(gap, band / 3.0)

        def on_mask(x: float, y: float) -> bool:
            ix = min(width - 1, max(0, int(x)))
            iy = min(height - 1, max(0, int(y)))
            return bool(bool_mask[iy, ix])

        n_rows = height // band + 1
        n_cols = width // band + 1

        parts: list[str] = []

        def emit_run(points: list[tuple[float, float]]) -> None:
            if len(points) >= 2:
                parts.append(
                    f'<line x1="{points[0][0]:.2f}" y1="{points[0][1]:.2f}" '
                    f'x2="{points[-1][0]:.2f}" y2="{points[-1][1]:.2f}"/>'
                )

        # Horizontal ribbon j: edge lines at y = j*band ± inset. The ribbon
        # is *under* at crossings with vertical ribbon i when (i + j) is
        # odd — there its edges break with ``inset`` clearance.
        for j in range(n_rows):
            for edge_y in (j * band + inset, (j + 1) * band - inset):
                if edge_y >= height:
                    continue
                run: list[tuple[float, float]] = []
                for i in range(n_cols + 1):
                    under = (i + j) % 2 == 1
                    x0 = max(0.0, i * band + (inset if under else 0.0))
                    x1 = min(float(width), (i + 1) * band - (inset if under else 0.0))
                    if x1 <= x0:
                        continue
                    mid_ok = on_mask((x0 + x1) / 2.0, edge_y)
                    if under:
                        # Broken segment inside this crossing cell.
                        if mid_ok:
                            emit_run([(x0, edge_y), (x1, edge_y)])
                        emit_run(run)
                        run = []
                    else:
                        if mid_ok:
                            if not run:
                                run = [(x0, edge_y)]
                            run.append((x1, edge_y))
                        else:
                            emit_run(run)
                            run = []
                emit_run(run)

        # Vertical ribbons — over where horizontals are under (parity
        # flipped).
        for i in range(n_cols):
            for edge_x in (i * band + inset, (i + 1) * band - inset):
                if edge_x >= width:
                    continue
                run = []
                for j in range(n_rows + 1):
                    under = (i + j) % 2 == 0
                    y0 = max(0.0, j * band + (inset if under else 0.0))
                    y1 = min(float(height), (j + 1) * band - (inset if under else 0.0))
                    if y1 <= y0:
                        continue
                    mid_ok = on_mask(edge_x, (y0 + y1) / 2.0)
                    if under:
                        if mid_ok:
                            emit_run([(edge_x, y0), (edge_x, y1)])
                        emit_run(run)
                        run = []
                    else:
                        if mid_ok:
                            if not run:
                                run = [(edge_x, y0)]
                            run.append((edge_x, y1))
                        else:
                            emit_run(run)
                            run = []
                emit_run(run)

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + "".join(parts)
            + "</g>"
        )
