"""Error-diffusion dither algorithm.

Quantises the region's tone to pen taps on a cell grid using classic
dithering: Floyd–Steinberg / Atkinson error diffusion (serpentine scan)
or the ordered Bayer 8×8 matrix. Unlike ``halftone`` (variable dot size
on a fixed lattice) and ``stippling`` (random placement), dithering
keeps every dot the same size and lets the *pattern* carry the tone —
the highest-fidelity tonal mapping of the dot fills, with the
recognisable newspaper / retro-computer texture.

Darkness comes from the injected ``_tone`` map when the pipeline
provides one, else from mask coverage per cell.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

# Standard 8×8 Bayer matrix, thresholds normalised to (0, 1).
_BAYER_8 = (
    np.array(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ],
        dtype=np.float64,
    )
    + 0.5
) / 64.0


def _error_diffuse(darkness: NDArray[np.float64], method: str) -> NDArray[np.bool_]:
    """Serpentine error diffusion; True = draw a dot in this cell."""
    work = darkness.copy()
    rows, cols = work.shape
    out = np.zeros((rows, cols), dtype=bool)
    if method == "atkinson":
        # Atkinson spreads 6/8 of the error — blown highlights stay
        # clean, the classic early-Mac look.
        kernel = [(0, 1, 1 / 8), (0, 2, 1 / 8), (1, -1, 1 / 8),
                  (1, 0, 1 / 8), (1, 1, 1 / 8), (2, 0, 1 / 8)]
    else:  # floyd
        kernel = [(0, 1, 7 / 16), (1, -1, 3 / 16), (1, 0, 5 / 16), (1, 1, 1 / 16)]
    for r in range(rows):
        reverse = r % 2 == 1
        rng_cols = range(cols - 1, -1, -1) if reverse else range(cols)
        sign = -1 if reverse else 1
        for c in rng_cols:
            old = work[r, c]
            new = old >= 0.5
            out[r, c] = new
            err = old - (1.0 if new else 0.0)
            for dr, dc, w in kernel:
                cc = c + sign * dc
                rr = r + dr
                if 0 <= rr < rows and 0 <= cc < cols:
                    work[rr, cc] += err * w
    return out


class DitherAlgorithm(RasterAlgorithm):
    """Fixed-size pen taps placed by error-diffusion / ordered dithering."""

    name: ClassVar[str] = "dither"
    description: ClassVar[str] = (
        "Error-diffusion dither (Floyd–Steinberg / Atkinson / Bayer) — "
        "fixed-size dots whose pattern carries the tone."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="cell_px", label="convert.cellPx", type="integer",
                   default=4, min=2, max=20, step=1),
        OptionSpec(key="dot_radius_px", label="convert.dotRadius", type="number",
                   default=1.0, min=0.2, max=5, step=0.1),
        OptionSpec(key="method", label="convert.ditherMethod", type="select",
                   default="floyd", choices=["floyd", "atkinson", "bayer"]),
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
        cell = int(floored_spacing(max(2, int(opts.get("cell_px", 4))), opts))
        radius = max(0.2, float(opts.get("dot_radius_px", 1.0)))
        method = str(opts.get("method", "floyd"))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
        if not bool_mask.any():
            return group_open + "</g>"

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            darkness = darkness * bool_mask
        else:
            darkness = bool_mask.astype(np.float64)

        # Block-mean downsample to the cell grid.
        rows = (height + cell - 1) // cell
        cols = (width + cell - 1) // cell
        padded = np.zeros((rows * cell, cols * cell), dtype=np.float64)
        padded[:height, :width] = darkness
        cells = padded.reshape(rows, cell, cols, cell).mean(axis=(1, 3))
        cover = np.zeros((rows * cell, cols * cell), dtype=np.float64)
        cover[:height, :width] = bool_mask
        on_cells = cover.reshape(rows, cell, cols, cell).mean(axis=(1, 3)) > 0.4

        if method == "bayer":
            thresholds = np.tile(_BAYER_8, (rows // 8 + 1, cols // 8 + 1))[:rows, :cols]
            dots = cells >= thresholds
        else:
            dots = _error_diffuse(cells, method)
        dots &= on_cells

        parts: list[str] = []
        half = cell / 2.0
        for r, c in np.argwhere(dots):
            cx = c * cell + half
            cy = r * cell + half
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}"/>')
        return group_open + "".join(parts) + "</g>"
