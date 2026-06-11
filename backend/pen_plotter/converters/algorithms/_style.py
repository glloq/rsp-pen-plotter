"""Shared stroke / spacing helpers for raster algorithms.

Each available colour carries a physical pen tip width
(``stroke_width_mm``). The frontend, which owns the placement's mm↔pixel
scale, converts that width into the layer's viewBox units and injects it
into the per-layer ``algorithm_options`` as ``stroke_width`` (in SVG user
units) before ``/rerender``. These helpers let every algorithm honour it
uniformly:

* :func:`stroke_attr_px` — the value to emit as the group's
  ``stroke-width`` so the drawn line matches the real pen. Falls back to
  the historical ``0.8`` when no pen width was resolved, so layers
  rendered without inventory context look exactly as before.
* :func:`floored_spacing` — clamps a fill/hatch line spacing so it is
  never *tighter* than the pen tip. The operator's wider spacing (used
  for tonal hatching) is preserved; only spacings that would make the
  pen strokes overlap unintentionally get bumped up to one pen width.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

DEFAULT_STROKE_WIDTH_PX = 0.8

# Fallback physical reference when the caller provides no placement
# scale: pretend the raster's long side prints on an A4 long side. Keeps
# millimetre options meaningful for renders that happen before a
# physical footprint exists (the initial /upload conversion, presets
# applied outside the editor) — the next /rerender with a real placement
# size then corrects the geometry.
A4_LONG_SIDE_MM = 297.0


def convert_mm_options(options: dict[str, Any] | None, px_per_mm: float) -> dict[str, Any]:
    """Translate ``*_mm`` length options into the ``*_px`` twins algorithms read.

    Every numeric option whose key ends in ``_mm`` is replaced by the
    same key with a ``_px`` suffix, scaled by ``px_per_mm`` (the
    raster-pixels-per-millimetre of the placement's physical footprint).
    This is what makes a millimetre knob *physical*: the same
    ``spacing_mm`` yields more raster pixels of spacing — hence the same
    on-paper pitch — whatever page format the operator picked. A
    millimetre key wins over an explicitly provided ``_px`` twin (mm is
    the canonical unit; the px spelling is the legacy escape hatch).
    Non-numeric values and unknown keys pass through untouched, so the
    conversion is safe to apply to every algorithm's options blindly.
    """
    if not options:
        return options or {}
    out = dict(options)
    for key, value in options.items():
        if not key.endswith("_mm"):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out.pop(key)
        out[key[: -len("_mm")] + "_px"] = float(value) * px_per_mm
    return out


def pen_width_px(options: dict[str, Any] | None) -> float | None:
    """Return the injected pen width (SVG user units), or ``None``.

    ``None`` means no physical pen width was resolved for this layer —
    callers then keep their historical defaults.
    """
    raw = (options or {}).get("stroke_width")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def stroke_attr_px(
    options: dict[str, Any] | None, default: float = DEFAULT_STROKE_WIDTH_PX
) -> float:
    """Stroke width to emit for a group, honouring the injected pen width."""
    value = pen_width_px(options)
    return value if value is not None else default


def floored_spacing(spacing: float, options: dict[str, Any] | None) -> float:
    """Clamp ``spacing`` so adjacent strokes never overlap the pen width.

    Pen width acts as a *minimum* spacing (a floor): a wider operator
    spacing is left untouched so tonal hatching keeps its lighter fill.
    A no-op when no pen width was injected.
    """
    pen = pen_width_px(options)
    return max(spacing, pen) if pen is not None else spacing


def tone_darkness(
    mask: NDArray[np.bool_],
    options: dict[str, Any] | None,
    *,
    min_range: float = 0.08,
) -> NDArray[np.float64] | None:
    """Normalised in-mask darkness from the injected ``_tone`` map, or ``None``.

    Returns a float array (same shape as ``mask``, 0 = lightest .. 1 =
    darkest *within this region*) when the pipeline injected a usable
    luminance map AND the region actually has tonal contrast. The map is
    contrast-stretched between the region's 2nd and 98th luminance
    percentiles so a low-contrast source still spans the full tonal
    range of the texture.

    Returns ``None`` when the map is absent, malformed, or the region is
    (near-)uniform — below ``min_range`` of luminance spread there is no
    tone worth encoding. Callers then keep their legacy non-tonal
    rendering, so flat fills and multicolour cluster regions (whose
    pixels share one colour, hence one luminance) render exactly as
    before the tonal upgrade.
    """
    tone = (options or {}).get("_tone")
    if not isinstance(tone, np.ndarray) or tone.shape != mask.shape:
        return None
    if not mask.any():
        return None
    values = np.clip(tone[mask].astype(np.float64), 0.0, 1.0)
    low, high = np.percentile(values, [2.0, 98.0])
    if high - low < min_range:
        return None
    stretched = (high - np.clip(tone.astype(np.float64), 0.0, 1.0)) / (high - low)
    out: NDArray[np.float64] = np.clip(stretched, 0.0, 1.0)
    return out
