"""Low-poly (Delaunay triangulation) algorithm.

Scatters sample points over the region, builds a Delaunay triangulation
of them, keeps the triangles whose centroid falls inside the mask, and
emits each triangle *edge* as a pen stroke. Shared edges are de-duplicated
so the plotter draws every facet boundary exactly once.

The result is the faceted "low-poly" wireframe look. Tone is driven by
point ``density``: more points → smaller facets → denser lines → darker,
so monochrome bands can lerp the density from dark to light.

Uses ``scipy.spatial.Delaunay``; when scipy is unavailable the algorithm
degrades gracefully to an empty group rather than crashing (the same
contract the other scipy-backed algorithms follow).
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


class LowPolyAlgorithm(RasterAlgorithm):
    """Renders a region as a Delaunay triangulation wireframe."""

    name: ClassVar[str] = "lowpoly"
    description: ClassVar[str] = (
        "Low-poly facets — a Delaunay triangulation of scattered points, "
        "drawn as edges. Denser points read darker."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render the region as triangle-edge strokes.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex stroke colour applied to every edge.
            label: Layer label written to ``inkscape:label``.
            options: Optional ``density`` (sample points per region pixel,
                default 0.01 — higher packs smaller facets), ``seed`` (RNG
                seed, default 0), and ``stroke_width`` (default 0.8).

        Returns:
            A single SVG ``<g>...</g>`` group of ``<line>`` triangle edges.
        """
        opts = options or {}
        density = max(0.0, float(opts.get("density", 0.01)))
        seed = int(opts.get("seed", 0))
        stroke_width = float(opts.get("stroke_width", 0.8))

        bool_mask = mask.astype(bool)
        ys, xs = np.nonzero(bool_mask)
        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_width:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
        )
        # Need at least a triangle's worth of points to tessellate.
        if ys.size < 3 or density <= 0.0:
            return group_open + "</g>"

        try:
            from scipy.spatial import Delaunay  # type: ignore[import-untyped]
        except ImportError:
            return group_open + "</g>"

        count = max(3, int(ys.size * density))
        rng = np.random.default_rng(seed)
        idx = rng.choice(ys.size, size=min(count, ys.size), replace=False)
        pts = np.column_stack([xs[idx], ys[idx]]).astype(np.float64)
        # Collinear or duplicate-heavy samples make Delaunay throw; bail to
        # an empty group rather than propagate a QhullError.
        if np.unique(pts, axis=0).shape[0] < 3:
            return group_open + "</g>"
        try:
            tri = Delaunay(pts)
        except Exception:  # pragma: no cover — QhullError on degenerate input
            return group_open + "</g>"

        height, width = bool_mask.shape
        # De-duplicate shared edges (each interior edge is shared by two
        # triangles) so the pen traces every facet boundary just once.
        edges: set[tuple[int, int]] = set()
        for simplex in tri.simplices:
            a, b, c = pts[simplex]
            cx = (a[0] + b[0] + c[0]) / 3.0
            cy = (a[1] + b[1] + c[1]) / 3.0
            ix, iy = int(round(cx)), int(round(cy))
            if 0 <= ix < width and 0 <= iy < height and bool_mask[iy, ix]:
                i0, i1, i2 = int(simplex[0]), int(simplex[1]), int(simplex[2])
                edges.add((min(i0, i1), max(i0, i1)))
                edges.add((min(i1, i2), max(i1, i2)))
                edges.add((min(i2, i0), max(i2, i0)))

        lines = []
        for u, v in edges:
            x1, y1 = pts[u]
            x2, y2 = pts[v]
            lines.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
        return group_open + "".join(lines) + "</g>"
