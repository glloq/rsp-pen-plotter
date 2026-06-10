"""Text-fill algorithm.

Fills the region with rows of repeated single-stroke (Hershey) text:
the words themselves become the shading texture — the classic
"typewriter art" / concrete-poetry portrait. With a ``_tone`` map the
glyph strokes only survive where local darkness clears ``threshold``,
so the text emerges from shadow areas; without one the text simply
fills the mask.

Glyph geometry comes from the same ``HersheyFonts`` engine the
typography pipeline uses, so the strokes are genuine single-pass pen
paths (no outline doubling).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


@lru_cache(maxsize=4)
def _font(size_px: float) -> Any:
    """A HersheyFonts instance normalised to ``size_px`` cap height."""
    from HersheyFonts import HersheyFonts

    font = HersheyFonts()
    font.load_default_font()
    font.normalize_rendering(size_px)
    return font


class TextFillAlgorithm(RasterAlgorithm):
    """Rows of repeated Hershey text clipped (and tone-gated) to the region."""

    name: ClassVar[str] = "text_fill"
    description: ClassVar[str] = (
        "Text fill — rows of repeated single-stroke text become the "
        "shading texture (typewriter-art portraits)."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="text", label="convert.text", type="text",
                   default="OmniPlot "),
        OptionSpec(key="font_size_px", label="convert.fontSize", type="number",
                   default=12, min=4, max=60, step=1),
        OptionSpec(key="line_spacing", label="convert.lineSpacing", type="number",
                   default=1.25, min=0.8, max=3, step=0.05),
        # Minimum local darkness for a glyph point to survive when a tone
        # map is present (0 = keep everything inside the mask).
        OptionSpec(key="threshold", label="convert.threshold", type="number",
                   default=0.35, min=0, max=0.95, step=0.05),
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
        text = str(opts.get("text") or "OmniPlot ")
        size = max(4.0, float(opts.get("font_size_px", 12.0)))
        line_spacing = max(0.5, float(opts.get("line_spacing", 1.25)))
        threshold = min(0.95, max(0.0, float(opts.get("threshold", 0.35))))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"
        try:
            font = _font(size)
        except Exception:  # pragma: no cover — HersheyFonts is a hard dep
            return group_open + "</g>"

        tone = opts.get("_tone")
        darkness: NDArray[np.float64] | None = None
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)

        # Lay out one reference line of repeated text, then stamp it on
        # every row with a half-period stagger so the column seams don't
        # align vertically.
        sample = text if text.strip() else "OmniPlot "
        strokes_one = [list(s) for s in font.strokes_for_text(sample)]
        if not strokes_one:
            return group_open + "</g>"
        unit_w = max(max(x for x, _ in s) for s in strokes_one) + size * 0.4
        repeats = int(width / unit_w) + 2

        parts: list[str] = []
        row_step = size * line_spacing
        row_idx = 0
        y = row_step / 2.0
        while y < height + size:
            x_shift = -(row_idx % 2) * unit_w / 2.0
            for rep in range(repeats):
                ox = x_shift + rep * unit_w
                if ox > width:
                    break
                for stroke in strokes_one:
                    run: list[str] = []
                    for sx, sy in stroke:
                        gx = ox + sx
                        # Hershey y grows downward after normalize_rendering;
                        # baseline sits at the row line.
                        gy = y + sy
                        igx = int(round(gx))
                        igy = int(round(gy))
                        ok = (
                            0 <= igx < width
                            and 0 <= igy < height
                            and bool_mask[igy, igx]
                        )
                        if ok and darkness is not None:
                            ok = darkness[igy, igx] >= threshold
                        if ok:
                            run.append(f"{gx:.2f},{gy:.2f}")
                        else:
                            if len(run) >= 2:
                                parts.append(
                                    f'<polyline points="{" ".join(run)}"/>'
                                )
                            run = []
                    if len(run) >= 2:
                        parts.append(f'<polyline points="{" ".join(run)}"/>')
            row_idx += 1
            y += row_step
        return group_open + "".join(parts) + "</g>"
