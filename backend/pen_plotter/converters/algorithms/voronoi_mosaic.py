"""Voronoi-mosaic algorithm.

Where ``voronoi_stipple`` draws the *sites* as dots, this draws the
*cell walls*: sites are scattered over the region (denser where darker,
when a tone map is available), one round of Lloyd relaxation evens them
out, and the finite Voronoi ridges whose midpoint stays on-mask are
emitted as strokes. The result is the cracked-glaze / crazy-paving
mosaic with cell size tracking tone.

Uses ``scipy.spatial.Voronoi``; when scipy is unavailable the algorithm
degrades to an empty group (same contract as ``lowpoly``).
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class VoronoiMosaicAlgorithm(RasterAlgorithm):
    """Renders a region as the edges of a tone-weighted Voronoi mosaic."""

    name: ClassVar[str] = "voronoi_mosaic"
    description: ClassVar[str] = (
        "Voronoi mosaic — cracked-glaze cell walls, cells smaller where "
        "the region is darker."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="density", label="convert.density", type="number",
                   default=0.004, min=0.0005, max=0.05, step=0.0005),
        OptionSpec(key="seed", label="convert.seed", type="integer",
                   default=0, min=0, step=1),
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
        density = float(opts.get("density", 0.004))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)
        height, width = bool_mask.shape

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linejoin="round">'
        )
        try:
            from scipy.spatial import Voronoi, cKDTree
        except ImportError:
            return group_open + "</g>"

        ys, xs = np.where(bool_mask)
        if len(xs) < 8:
            return group_open + "</g>"

        n_sites = max(4, min(int(len(xs) * density), 4000))
        rng = np.random.default_rng(seed)

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            weights = darkness[ys, xs] + 0.05  # keep light areas sparsely tiled
            weights = weights / weights.sum()
            picks = rng.choice(len(xs), size=n_sites, replace=False, p=weights)
        else:
            picks = rng.choice(len(xs), size=min(n_sites, len(xs)), replace=False)
        sites = np.column_stack((xs[picks], ys[picks])).astype(np.float64)
        # Sub-pixel jitter avoids the degenerate collinear lattices that
        # Voronoi/QHull dislikes on pixel-aligned input.
        sites += rng.uniform(-0.25, 0.25, size=sites.shape)

        # One Lloyd step: move each site to the centroid of its on-mask
        # pixels — evens out the random clumps without the full
        # relaxation cost of voronoi_stipple.
        tree = cKDTree(sites)
        pixels = np.column_stack((xs, ys)).astype(np.float64)
        _, owner = tree.query(pixels, k=1)
        sums = np.zeros_like(sites)
        counts = np.zeros(len(sites))
        np.add.at(sums, owner, pixels)
        np.add.at(counts, owner, 1.0)
        occupied = counts > 0
        sites[occupied] = sums[occupied] / counts[occupied, None]

        vor = Voronoi(sites)
        lines: list[str] = []
        for (i1, i2) in vor.ridge_vertices:
            if i1 < 0 or i2 < 0:
                continue  # infinite ridge — clipped at the hull, skip
            x1, y1 = vor.vertices[i1]
            x2, y2 = vor.vertices[i2]
            mx = int(round((x1 + x2) / 2.0))
            my = int(round((y1 + y2) / 2.0))
            if not (0 <= mx < width and 0 <= my < height) or not bool_mask[my, mx]:
                continue
            lines.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            )
        return group_open + "".join(lines) + "</g>"
