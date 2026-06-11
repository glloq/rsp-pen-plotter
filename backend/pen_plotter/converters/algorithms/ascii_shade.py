"""ASCII shading algorithm.

Typewriter-art shading: the region is cut into a square grid and each
cell draws one glyph from a density ramp (`` . - : = + x # @``) picked
by the cell's mean darkness — the denser the glyph, the more ink the
pen lays down. Glyphs are tiny hand-defined single-stroke vectors (not
font outlines), so every mark is a clean plottable polyline.

Differs from ``text_fill`` (repeated operator-supplied text as a
texture, Hershey outlines): here the *glyph choice itself* encodes the
tone, character by character — the classic terminal-art portrait.

Without a usable tone map each covered cell falls back to a mid-ramp
glyph scaled by its mask coverage, so flat fills still render sensibly.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px, tone_darkness
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Density ramp, lightest → darkest. Each glyph is a list of polylines in
# unit-cell coordinates (0..1, y down); strokes are scaled into the cell
# with a small margin so neighbouring glyphs never touch.
_RAMP: tuple[tuple[tuple[tuple[float, float], ...], ...], ...] = (
    # "."
    (((0.42, 0.62), (0.58, 0.62)),),
    # "-"
    (((0.25, 0.5), (0.75, 0.5)),),
    # ":"
    (((0.42, 0.3), (0.58, 0.3)), ((0.42, 0.7), (0.58, 0.7))),
    # "="
    (((0.2, 0.4), (0.8, 0.4)), ((0.2, 0.6), (0.8, 0.6))),
    # "+"
    (((0.2, 0.5), (0.8, 0.5)), ((0.5, 0.2), (0.5, 0.8))),
    # "x"
    (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8))),
    # "#"
    (
        ((0.35, 0.15), (0.35, 0.85)),
        ((0.65, 0.15), (0.65, 0.85)),
        ((0.15, 0.35), (0.85, 0.35)),
        ((0.15, 0.65), (0.85, 0.65)),
    ),
    # "@" — square outline + both diagonals (heaviest ink).
    (
        ((0.15, 0.15), (0.85, 0.15), (0.85, 0.85), (0.15, 0.85), (0.15, 0.15)),
        ((0.15, 0.15), (0.85, 0.85)),
        ((0.85, 0.15), (0.15, 0.85)),
    ),
)


class AsciiShadeAlgorithm(RasterAlgorithm):
    """Renders a region as a grid of darkness-ramp glyphs."""

    name: ClassVar[str] = "ascii_shade"
    description: ClassVar[str] = (
        "Typewriter-art shading — each grid cell draws one glyph from a "
        "density ramp picked by its darkness."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_mm", label="convert.cellSize", type="number",
                   default=3.7, min=1.5, max=15, step=0.1),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as a glyph grid.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour applied to every glyph stroke.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``cell_px`` (grid pitch, default 10).

        Returns:
            A single SVG ``<g>...</g>`` group of glyph polylines.
        """
        opts = options or {}
        cell = max(4, int(opts.get("cell_px", 10)))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape
        darkness = tone_darkness(bool_mask, opts)

        parts: list[str] = []
        for y0 in range(0, height, cell):
            for x0 in range(0, width, cell):
                block = bool_mask[y0 : y0 + cell, x0 : x0 + cell]
                coverage = float(block.mean())
                if coverage < 0.25:
                    continue
                if darkness is not None:
                    d = float((darkness[y0 : y0 + cell, x0 : x0 + cell] * block).sum()) / max(
                        1, int(block.sum())
                    )
                else:
                    # Coverage-only fallback: solid cells land mid-ramp.
                    d = coverage * 0.55
                level = int(d * (len(_RAMP) + 1)) - 1
                if level < 0:
                    continue
                level = min(level, len(_RAMP) - 1)
                bw = block.shape[1]
                bh = block.shape[0]
                for stroke in _RAMP[level]:
                    pts = " ".join(f"{x0 + u * bw:.2f},{y0 + v * bh:.2f}" for u, v in stroke)
                    parts.append(f'<polyline points="{pts}"/>')

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
            + "".join(parts)
            + "</g>"
        )
