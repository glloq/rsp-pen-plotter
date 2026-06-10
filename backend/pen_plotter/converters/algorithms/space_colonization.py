"""Space-colonization algorithm — organic branching growth.

Scatters attraction points over the region (denser where darker, when a
tone map is available) and grows a branching skeleton toward them from
seed nodes: each iteration, every attractor pulls its nearest node, and
nodes spawn children along the mean pull direction; attractors are
consumed once a node grows close enough. The classic Runions et al.
"Modeling Trees with a Space Colonization Algorithm" — produces veins /
roots / lightning textures moulded to the silhouette.

Uses ``scipy.spatial.cKDTree`` for the nearest-node queries; without
scipy the algorithm degrades to an empty group.
"""

from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class SpaceColonizationAlgorithm(RasterAlgorithm):
    """Organic branching skeleton grown toward darkness."""

    name: ClassVar[str] = "space_colonization"
    description: ClassVar[str] = (
        "Space colonization — organic veins growing toward the darkest "
        "parts of the region, root / lightning texture."
    )
    tone_aware: ClassVar[bool] = True

    options_schema: ClassVar[list[OptionSpec]] = [
        OptionSpec(key="attractors", label="convert.attractors", type="integer",
                   default=700, min=100, max=4000, step=50),
        OptionSpec(key="step_mm", label="convert.stepPx", type="number",
                   default=1.5, min=0.37, max=5.6, step=0.1),
        OptionSpec(key="influence_mm", label="convert.influencePx", type="number",
                   default=15, min=1.9, max=74, step=0.1),
        OptionSpec(key="kill_mm", label="convert.killPx", type="number",
                   default=2.2, min=0.74, max=15, step=0.1),
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
        n_attr = max(50, int(opts.get("attractors", 700)))
        step = max(1.0, float(opts.get("step_px", 4.0)))
        influence = max(step * 2, float(opts.get("influence_px", 40.0)))
        kill = max(step, float(opts.get("kill_px", 6.0)))
        seed = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}" '
            f'stroke-linecap="round">'
        )
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            return group_open + "</g>"

        ys, xs = np.where(bool_mask)
        if len(xs) < 8:
            return group_open + "</g>"
        rng = np.random.default_rng(seed)

        tone = opts.get("_tone")
        if tone is not None:
            darkness = 1.0 - np.clip(np.asarray(tone, dtype=np.float64), 0.0, 1.0)
            weights = darkness[ys, xs] + 0.02
            weights = weights / weights.sum()
            picks = rng.choice(len(xs), size=min(n_attr, len(xs)), replace=False, p=weights)
        else:
            picks = rng.choice(len(xs), size=min(n_attr, len(xs)), replace=False)
        attractors = np.column_stack((xs[picks], ys[picks])).astype(np.float64)

        # Seed nodes: a handful of points spread over the region so
        # disconnected blobs each get their own root.
        n_seeds = max(1, min(5, len(xs) // 5000 + 1))
        seed_picks = rng.choice(len(xs), size=n_seeds, replace=False)
        nodes = np.column_stack((xs[seed_picks], ys[seed_picks])).astype(np.float64)
        parents = [-1] * n_seeds

        max_nodes = 4000
        max_iters = 200
        for _ in range(max_iters):
            if len(attractors) == 0 or len(nodes) >= max_nodes:
                break
            tree = cKDTree(nodes)
            dist, nearest = tree.query(attractors, k=1)
            in_range = dist < influence
            if not in_range.any():
                break
            # Mean normalised pull per node.
            pull = np.zeros_like(nodes)
            counts = np.zeros(len(nodes))
            vec = attractors[in_range] - nodes[nearest[in_range]]
            norm = np.linalg.norm(vec, axis=1, keepdims=True)
            norm[norm == 0] = 1.0
            np.add.at(pull, nearest[in_range], vec / norm)
            np.add.at(counts, nearest[in_range], 1.0)
            growers = np.flatnonzero(counts)
            if len(growers) == 0:
                break
            new_nodes = []
            for i in growers:
                direction = pull[i] / counts[i]
                d_norm = float(np.linalg.norm(direction))
                if d_norm < 1e-6:
                    continue
                new_nodes.append(nodes[i] + step * direction / d_norm)
                parents.append(int(i))
            if not new_nodes:
                break
            nodes = np.vstack((nodes, np.array(new_nodes)))
            # Kill attractors reached by the new growth.
            tree = cKDTree(nodes)
            dist, _ = tree.query(attractors, k=1)
            attractors = attractors[dist > kill]

        lines: list[str] = []
        for child, parent in enumerate(parents):
            if parent < 0:
                continue
            x1, y1 = nodes[parent]
            x2, y2 = nodes[child]
            lines.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>'
            )
        return group_open + "".join(lines) + "</g>"
