"""Concentric offset (peeling) algorithm.

Iterative morphological erosion of the mask: at each level trace the
outer contour with ``skimage.measure.find_contours``, then erode by
``spacing_px`` and repeat until the mask is empty. With ``bridge=True``
(default) consecutive rings are joined by a short straight segment to
the nearest point of the next ring, yielding a near-continuous spiral
— one polyline per connected component instead of N nested rings.

The boundary tracer relies on marching squares (subpixel-accurate)
rather than the cheaper angular sort used by :mod:`contours`, so the
result is clean even for concave shapes.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _erode_disk(mask: NDArray[np.bool_], radius: int) -> NDArray[np.bool_]:
    """Disk-shaped binary erosion. Falls back to 4-connected when scipy is gone."""
    if radius <= 0:
        return mask
    try:
        from scipy.ndimage import binary_erosion  # type: ignore[import-untyped]
        from skimage.morphology import disk  # type: ignore[import-untyped]
    except ImportError:
        out = mask.copy()
        for _ in range(radius):
            pad = np.pad(out, 1, mode="constant", constant_values=False)
            out = out & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
        return out
    eroded = binary_erosion(mask, structure=disk(radius))
    return np.asarray(eroded, dtype=bool)


def _longest_contour(mask: NDArray[np.bool_]) -> list[tuple[float, float]]:
    """Trace the longest outer contour using marching squares."""
    try:
        from skimage.measure import find_contours  # type: ignore[import-untyped]
    except ImportError:
        return []
    contours = find_contours(mask.astype(np.float32), 0.5)
    if not contours:
        return []
    longest = max(contours, key=len)
    # find_contours returns (row, col) pairs; swap to (x=col, y=row).
    return [(float(c), float(r)) for r, c in longest]


def _nearest_index(target: tuple[float, float], poly: list[tuple[float, float]]) -> int:
    arr = np.asarray(poly, dtype=np.float64)
    diff = arr - np.asarray(target, dtype=np.float64)
    d = np.einsum("ij,ij->i", diff, diff)
    return int(d.argmin())


def _component_spiral(
    component_mask: NDArray[np.bool_],
    *,
    spacing_px: int,
    max_rings: int,
    bridge: bool,
) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    current = component_mask
    for _ in range(max_rings):
        if not current.any():
            break
        poly = _longest_contour(current)
        if len(poly) >= 3:
            rings.append(poly)
        current = _erode_disk(current, spacing_px)
    if not rings:
        return []
    if not bridge:
        return rings
    # Stitch rings into one polyline by re-rooting each ring at its
    # nearest point to the previous ring's endpoint.
    spiral: list[tuple[float, float]] = list(rings[0])
    for ring in rings[1:]:
        anchor = spiral[-1]
        idx = _nearest_index(anchor, ring)
        # Rotate ``ring`` so it starts at the nearest point.
        ring = ring[idx:] + ring[:idx]
        spiral.extend(ring)
    return [spiral]


class ConcentricOffsetAlgorithm(RasterAlgorithm):
    """Bridged concentric offset rings — one polyline per component."""

    name: ClassVar[str] = "concentric_offset"
    description: ClassVar[str] = (
        "Spiral inward via morphological erosion — near-continuous stroke, "
        "very few pen-lifts per region."
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
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 3))), opts))
        max_rings = max(1, int(opts.get("max_rings", 50)))
        bridge = bool(opts.get("bridge", True))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        try:
            from scipy.ndimage import label as nd_label
        except ImportError:
            return group_open + "</g>"

        components, count = nd_label(bool_mask)
        parts: list[str] = []
        for comp_idx in range(1, count + 1):
            comp_mask = components == comp_idx
            for poly in _component_spiral(
                comp_mask,
                spacing_px=spacing,
                max_rings=max_rings,
                bridge=bridge,
            ):
                pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
                parts.append(f'<polyline points="{pts}"/>')
        return group_open + "".join(parts) + "</g>"
