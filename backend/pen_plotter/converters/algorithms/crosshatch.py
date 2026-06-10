"""Crosshatch algorithm.

Fills the region with parallel pen strokes, optionally with a second set
of strokes at +90° for the cross-hatch effect classic in pen-plotter art.
Each stroke is the on-mask portion of an infinite line; spacing between
lines and the rotation angle are configurable.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._hatch import sweep_segments
from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


def _line_segments(
    mask: NDArray[np.bool_],
    angle_deg: float,
    spacing_px: float,
) -> list[tuple[float, float, float, float]]:
    """Return ``(x1, y1, x2, y2)`` segments at ``angle_deg``, spaced ``spacing_px``.

    Thin flattening wrapper around the shared vectorised sweep
    rasteriser (:func:`pen_plotter.converters.algorithms._hatch.sweep_segments`);
    also reused by ``dashes`` / ``moire`` / ``scribble`` / ``superpixel_hatch``.
    """
    return [seg for sweep in sweep_segments(mask, angle_deg, spacing_px) for seg in sweep]


class CrosshatchAlgorithm(RasterAlgorithm):
    """Renders a region as parallel (or crossed) pen strokes."""

    name: ClassVar[str] = "crosshatch"
    description: ClassVar[str] = (
        "Parallel pen strokes (optional crossed 90° pass) — disconnected runs, "
        "more pen-lifts than eulerian_hatch but simpler to tune per layer."
    )
    # ``angles`` (a list of 1–4 hatch angles for darkening passes inside a
    # single layer) is *also* accepted, but it's an internal hook used by
    # master styles — not surfaced as a standalone form field. The legacy
    # ``angle_deg`` + ``crossed`` pair covers everything operators do by hand.
    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(
            key="spacing_px", label="convert.spacing", type="number",
            default=4, min=1, max=30, step=0.5,
        ),
        OptionSpec(
            key="angle_deg", label="convert.angleDeg", type="number",
            default=45, min=0, max=180, step=1,
        ),
        OptionSpec(key="crossed", label="convert.crossed", type="boolean", default=False),
        # ``joined`` stitches consecutive sweep segments into boustrophedon
        # zig-zags (the eulerian_hatch geometry) — same look on paper,
        # drastically fewer pen-lifts. Kept as an option here so the picker
        # shows one hatch entry instead of two near-identical cards.
        OptionSpec(key="joined", label="convert.joined", type="boolean", default=False),
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
        if bool(opts.get("joined", False)):
            # Delegate to the boustrophedon variant — identical sweep
            # geometry, segments stitched into continuous zig-zags.
            from pen_plotter.converters.algorithms.eulerian_hatch import (
                EulerianHatchAlgorithm,
            )

            return EulerianHatchAlgorithm().render_layer(
                mask, color_hex, label, options=options
            )
        spacing = floored_spacing(max(1.0, float(opts.get("spacing_px", 4.0))), opts)
        bool_mask = mask.astype(bool)

        # ``angles`` (new) lets monochrome mode stack 1..4 hatch passes
        # inside a single layer to darken a band without changing ink
        # colour. When absent, fall back to the legacy ``angle_deg`` +
        # ``crossed`` pair so existing layer presets and persisted
        # placements keep rendering identically.
        raw_angles = opts.get("angles")
        if raw_angles is None:
            angle = float(opts.get("angle_deg", 45.0))
            angles = [angle, angle + 90.0] if bool(opts.get("crossed", False)) else [angle]
        else:
            angles = [float(a) for a in raw_angles][:4]
            if not angles:
                angles = [float(opts.get("angle_deg", 45.0))]

        segments: list[tuple[float, float, float, float]] = []
        for a in angles:
            segments.extend(_line_segments(bool_mask, a, spacing))

        paths = "".join(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            for x1, y1, x2, y2 in segments
        )
        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" stroke-linecap="round">'
            + paths
            + "</g>"
        )
