"""Weighted Voronoi stippling (Lloyd relaxation).

Improvement over the plain ``stippling`` algorithm: dots converge toward
a *centroidal Voronoi tessellation* of the mask, so spacing becomes
even and visually pleasant — no clumps, no holes. When ``intensity`` is
supplied (a float array same shape as the mask, lower values = darker
= more dots), the centroid is weighted by darkness, so darker regions
attract more dots without changing the global count.

Inspired by Adrian Secord's 2002 paper "Weighted Voronoi Stippling"
(https://www.cs.ubc.ca/labs/imager/tr/2002/secord-stippling/).
The implementation uses ``scipy.spatial.cKDTree`` for the nearest-site
lookup, which is the bottleneck of the relaxation step. When scipy is
unavailable, falls back to a single random sample (no relaxation) so
the algorithm still emits *something* sensible.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class VoronoiStippleAlgorithm(RasterAlgorithm):
    """Even-spaced dot stippling via centroidal Voronoi relaxation."""

    name: ClassVar[str] = "voronoi_stipple"
    description: ClassVar[str] = (
        "Centroidal Voronoi stippling — evenly-spaced dots, optionally "
        "weighted by darkness."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as evenly-spaced Voronoi-relaxed dots.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex fill colour applied to every circle.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``density`` (dots per region pixel, default
                0.02), ``dot_radius_px`` (default 0.6), ``iterations``
                (Lloyd relaxation passes, default 6 — 0 = uniform random
                sample, no relaxation), ``seed`` (RNG seed, default 0),
                and ``intensity`` (optional float ndarray same shape as
                ``mask``; lower values pull dots toward darker pixels
                for weighted stippling).

        Returns:
            A single SVG ``<g>...</g>`` group containing the dots.
        """
        opts = options or {}
        density = max(0.0, float(opts.get("density", 0.02)))
        radius = float(opts.get("dot_radius_px", 0.6))
        iterations = max(0, int(opts.get("iterations", 6)))
        seed = int(opts.get("seed", 0))

        bool_mask = mask.astype(bool)
        ys, xs = np.nonzero(bool_mask)
        group_open = (
            f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}>"
        )
        if ys.size == 0 or density <= 0.0:
            return group_open + "</g>"

        count = max(1, int(ys.size * density))
        rng = np.random.default_rng(seed)
        # Seed: random sample of mask pixels.
        idx = rng.choice(ys.size, size=min(count, ys.size), replace=False)
        sites = np.column_stack([xs[idx], ys[idx]]).astype(np.float64)

        # Lloyd relaxation: each iteration assigns every mask pixel to
        # its nearest site, then moves the site to the centroid of its
        # assigned cluster. Intensity (if supplied as a 2D float array)
        # weights the centroid so darker pixels pull dots toward them.
        intensity = opts.get("intensity")
        weights: NDArray[np.float64] | None = None
        if isinstance(intensity, np.ndarray) and intensity.shape == bool_mask.shape:
            # Invert so darker -> larger weight; clip to avoid all-zero
            # rows when the layer is uniform.
            w = 1.0 - intensity.astype(np.float64)
            weights = np.clip(w[ys, xs], 1e-3, None)

        try:
            from scipy.spatial import cKDTree  # type: ignore[import-untyped]
        except ImportError:
            iterations = 0  # No KDTree -> skip relaxation, emit seed dots.

        if iterations > 0:
            points = np.column_stack([xs, ys]).astype(np.float64)
            for _ in range(iterations):
                tree = cKDTree(sites)  # type: ignore[possibly-undefined]
                _, assign = tree.query(points, k=1)
                # Weighted centroid per site. ``np.bincount`` handles
                # the summation in C; one pass per coordinate axis.
                if weights is not None:
                    wsum = np.bincount(assign, weights=weights, minlength=len(sites))
                    cx = np.bincount(assign, weights=weights * points[:, 0], minlength=len(sites))
                    cy = np.bincount(assign, weights=weights * points[:, 1], minlength=len(sites))
                else:
                    wsum = np.bincount(assign, minlength=len(sites)).astype(np.float64)
                    cx = np.bincount(assign, weights=points[:, 0], minlength=len(sites))
                    cy = np.bincount(assign, weights=points[:, 1], minlength=len(sites))
                # Sites with no assigned pixels keep their previous position.
                nonzero = wsum > 0
                sites[nonzero, 0] = cx[nonzero] / wsum[nonzero]
                sites[nonzero, 1] = cy[nonzero] / wsum[nonzero]

        dots = [
            f'<circle cx="{x + 0.5:.2f}" cy="{y + 0.5:.2f}" r="{radius:.2f}"/>'
            for x, y in sites
        ]
        return group_open + "".join(dots) + "</g>"
