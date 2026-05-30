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

DEFAULT_STROKE_WIDTH_PX = 0.8


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
