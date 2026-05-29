"""Segmentation dispatch for the bitmap converter.

Routes the operator's chosen ``segmentation_method`` (kmeans /
luminance_bands / thresholds / fixed_palette) to the matching
implementation in :mod:`pen_plotter.converters.segmentation` and
returns the ``(labels, palette)`` pair downstream rendering consumes.

The actual clustering primitives live in the ``segmentation`` sibling
module so each algorithm stays independently testable; this module is
purely the strategy selector + a small ``palette_has_near_white`` helper
the ``fixed_palette`` branch uses to auto-inject ``#ffffff`` when the
operator's pen palette omits white.

``_REC709`` lives here because the only consumers of the luminance
weighting are this module (palette-near-white check) and the
``render`` module's drop-background filter / layer ordering — keeping
it next to the segmentation strategies makes the "what counts as
dark vs light" knob a one-stop import for both.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from pen_plotter.converters import segmentation

SegmentationMethod = Literal[
    "kmeans",
    "kmeans_lab",
    "luminance_bands",
    "thresholds",
    "fixed_palette",
    "palette_dither",
]

# Rec.709 luminance weighting used by every "is this layer / palette
# entry bright enough to count as background" decision in the pipeline.
# Kept as a module-level array so the multiplication stays vectorised
# without re-allocating the weights on every call.
_REC709 = np.array([0.2126, 0.7152, 0.0722])


def _palette_has_near_white(palette_hex: list[str], threshold: float) -> bool:
    """True if any entry's Rec.709 luminance reaches the drop threshold."""
    for entry in palette_hex:
        try:
            rgb = segmentation._hex_to_rgb(entry)
        except ValueError:
            continue
        if float(np.dot(np.array(rgb) / 255.0, _REC709)) >= threshold:
            return True
    return False


def segment_image(
    image: Image.Image,
    *,
    method: SegmentationMethod,
    options: dict[str, Any],
    num_colors: int,
    drop_background: bool,
    background_luminance: float,
    n_init: int = 10,
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Dispatch to the segmentation method selected by ``method``.

    Args:
        image: The pre-loaded RGB Pillow image to segment.
        method: Strategy selector (``kmeans`` / ``luminance_bands`` /
            ``thresholds`` / ``fixed_palette``).
        options: Method-specific arguments — ``num_bands``, ``levels``,
            ``palette`` — passed through verbatim from
            ``BitmapOptions.segmentation_options``.
        num_colors: K-means fallback cluster count. Also used as
            ``num_bands`` for luminance_bands when ``options`` doesn't
            override it.
        drop_background: When ``fixed_palette`` and this is true,
            auto-injects ``#ffffff`` ahead of the operator's palette if
            none of their entries already reach
            ``background_luminance``. Preserves the white-background
            drop behaviour even when the pen rack has no white pen.
        background_luminance: Threshold used by the white-injection
            heuristic above. Same value the drop-background filter uses
            at render time, so the segmentation and the filter agree on
            what counts as "white enough".
        n_init: K-means restarts. Only consumed when ``method`` is
            ``kmeans``; the preview path drops it to 1 for speed.

    Returns:
        ``(labels, palette)``: ``labels`` is a (height, width) array of
        cluster indices, ``palette`` is a (k, 3) array of RGB centroids.
    """
    if method == "luminance_bands":
        num_bands = int(options.get("num_bands", num_colors))
        return segmentation.luminance_bands(image, num_bands=num_bands)
    if method == "thresholds":
        levels = options.get("levels", [])
        if not isinstance(levels, list):
            raise ValueError("segmentation_options.levels must be a list of floats")
        return segmentation.thresholds(image, levels=levels)
    if method in ("fixed_palette", "palette_dither"):
        palette_hex = options.get("palette", [])
        if not isinstance(palette_hex, list) or not palette_hex:
            raise ValueError(
                "segmentation_options.palette must be a non-empty list of hex colours"
            )
        # Preserve white background: when the operator's palette
        # follows their pen rack (typically no white pen), white
        # pixels would otherwise snap to the nearest pen colour
        # (light grey, pale yellow, …) and the resulting layer's
        # luminance is no longer above ``background_luminance`` —
        # so the drop_background filter downstream lets the wrong-
        # colour "background" through. Auto-inject ``#ffffff`` here
        # so white pixels snap to white instead, and the existing
        # filter at the render step drops that layer cleanly.
        if drop_background and not _palette_has_near_white(palette_hex, background_luminance):
            palette_hex = ["#ffffff", *palette_hex]
        if method == "palette_dither":
            amount = float(options.get("dither_amount", 0.6))
            return segmentation.palette_dither(image, palette_hex=palette_hex, amount=amount)
        return segmentation.fixed_palette(image, palette_hex=palette_hex)
    if method == "kmeans_lab":
        return segmentation.kmeans_lab(image, num_colors=num_colors, n_init=n_init)
    return segmentation.kmeans(image, num_colors=num_colors, n_init=n_init)
