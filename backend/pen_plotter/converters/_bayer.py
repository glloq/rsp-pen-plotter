"""Shared 8×8 recursive Bayer ordered-dither matrix.

Single source for the classic Bayer-8 threshold pattern. The two
consumers normalise it differently:

- :mod:`pen_plotter.converters.segmentation` (``palette_dither``) wants
  a zero-centred perturbation in roughly ``[-0.5, 0.5)``.
- :mod:`pen_plotter.converters.algorithms.dither` wants thresholds in
  ``(0, 1)``.

Both derive from :data:`BAYER8_BASE` so the underlying pattern can't
drift between the two copies.
"""

from __future__ import annotations

import numpy as np

# Raw recursive Bayer index matrix, values 0..63.
BAYER8_BASE = np.array(
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

# Thresholds normalised to (0, 1) — ordered-dither comparison form.
BAYER8_UNIT = (BAYER8_BASE + 0.5) / 64.0

# Zero-centred perturbations in roughly [-0.5, 0.5).
BAYER8_CENTERED = BAYER8_UNIT - 0.5
