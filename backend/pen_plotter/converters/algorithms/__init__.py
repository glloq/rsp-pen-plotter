"""Raster algorithm registry.

Algorithms are looked up by name so the converter and API can offer a stable
set of choices. Only fully implemented algorithms are registered here.

Each algorithm also declares a ``kind`` ("fill" / "lines" / "mono_stroke")
that the UI uses to group cards into families.
"""

from __future__ import annotations

from typing import Literal

from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.brick import BrickAlgorithm
from pen_plotter.converters.algorithms.centerline import CenterlineAlgorithm
from pen_plotter.converters.algorithms.circle_pack import CirclePackAlgorithm
from pen_plotter.converters.algorithms.concentric_offset import ConcentricOffsetAlgorithm
from pen_plotter.converters.algorithms.contours import ContoursAlgorithm
from pen_plotter.converters.algorithms.crosshatch import CrosshatchAlgorithm
from pen_plotter.converters.algorithms.dashes import DashesAlgorithm
from pen_plotter.converters.algorithms.direct import DirectVectorizationAlgorithm
from pen_plotter.converters.algorithms.edges import EdgesAlgorithm
from pen_plotter.converters.algorithms.eulerian_hatch import EulerianHatchAlgorithm
from pen_plotter.converters.algorithms.flowfield import FlowFieldAlgorithm
from pen_plotter.converters.algorithms.gosper import GosperFillAlgorithm
from pen_plotter.converters.algorithms.grid import GridAlgorithm
from pen_plotter.converters.algorithms.halftone import HalftoneAlgorithm
from pen_plotter.converters.algorithms.hilbert import HilbertFillAlgorithm
from pen_plotter.converters.algorithms.lowpoly import LowPolyAlgorithm
from pen_plotter.converters.algorithms.rings import RingsAlgorithm
from pen_plotter.converters.algorithms.scanlines import ScanlinesAlgorithm
from pen_plotter.converters.algorithms.scribble import ScribbleAlgorithm
from pen_plotter.converters.algorithms.spiral import SpiralAlgorithm
from pen_plotter.converters.algorithms.squiggle import SquiggleAlgorithm
from pen_plotter.converters.algorithms.stippling import StipplingAlgorithm
from pen_plotter.converters.algorithms.sunburst import SunburstAlgorithm
from pen_plotter.converters.algorithms.truchet import TruchetAlgorithm
from pen_plotter.converters.algorithms.tsp import TspAlgorithm
from pen_plotter.converters.algorithms.tsp_opt import TspOptimizedAlgorithm
from pen_plotter.converters.algorithms.voronoi_stipple import VoronoiStippleAlgorithm

AlgorithmKind = Literal["fill", "lines", "mono_stroke"]

# Static complexity score: a rough order-of-magnitude estimate of how
# expensive each algorithm is at /preview-time, relative to the cheapest
# pipeline. Used by the UI's cost estimator to pre-warn the operator
# *before* the first /preview round-trip — the actual EMA correction
# kicks in after the first observation. "low" ≈ sub-200ms-ish on a Pi
# with a small image; "medium" ≈ a few hundred ms; "high" can hit
# multiple seconds (TSP is the obvious offender — its tour length grows
# super-linearly with point count).
AlgorithmComplexity = Literal["low", "medium", "high"]

_ALGORITHMS: dict[str, RasterAlgorithm] = {
    algo.name: algo
    for algo in (
        DirectVectorizationAlgorithm(),
        HalftoneAlgorithm(),
        StipplingAlgorithm(),
        CrosshatchAlgorithm(),
        ContoursAlgorithm(),
        EdgesAlgorithm(),
        CenterlineAlgorithm(),
        SpiralAlgorithm(),
        ScanlinesAlgorithm(),
        TspAlgorithm(),
        HilbertFillAlgorithm(),
        GosperFillAlgorithm(),
        EulerianHatchAlgorithm(),
        ConcentricOffsetAlgorithm(),
        FlowFieldAlgorithm(),
        TspOptimizedAlgorithm(),
        VoronoiStippleAlgorithm(),
        SquiggleAlgorithm(),
        LowPolyAlgorithm(),
        ScribbleAlgorithm(),
        GridAlgorithm(),
        BrickAlgorithm(),
        DashesAlgorithm(),
        TruchetAlgorithm(),
        RingsAlgorithm(),
        SunburstAlgorithm(),
        CirclePackAlgorithm(),
    )
}

# Family per algorithm: "fill" packs ink across the region, "lines" emits
# discrete outlines, "mono_stroke" produces a single continuous polyline.
_KINDS: dict[str, AlgorithmKind] = {
    "direct": "fill",
    "halftone": "fill",
    "stippling": "fill",
    "crosshatch": "fill",
    "contours": "lines",
    "edges": "lines",
    "centerline": "lines",
    "spiral": "mono_stroke",
    "scanlines": "mono_stroke",
    "tsp": "mono_stroke",
    "hilbert": "mono_stroke",
    "gosper": "mono_stroke",
    "eulerian_hatch": "fill",
    "concentric_offset": "mono_stroke",
    "flowfield": "fill",
    "tsp_opt": "mono_stroke",
    "voronoi_stipple": "fill",
    "squiggle": "mono_stroke",
    "lowpoly": "lines",
    "scribble": "fill",
    "grid": "lines",
    "brick": "lines",
    "dashes": "fill",
    "truchet": "lines",
    "rings": "mono_stroke",
    "sunburst": "mono_stroke",
    "circle_pack": "fill",
}

# Rough cost class per algorithm — see ``AlgorithmComplexity`` above for
# the meaning of low/medium/high. Reviewed against typical /preview
# latencies on a Pi-class device with the default detail tier; tweak
# alongside any algorithm-internal changes that change runtime scaling.
_COMPLEXITY: dict[str, AlgorithmComplexity] = {
    "direct": "low",       # potrace on a small label mask
    "halftone": "low",     # uniform dot grid
    "stippling": "medium", # Poisson-disk sampling
    "crosshatch": "medium",
    "contours": "low",
    "edges": "low",
    "centerline": "medium",  # thinning + path extraction
    "spiral": "medium",
    "scanlines": "low",
    "tsp": "high",          # tour optimisation dominates
    "hilbert": "medium",
    "gosper": "medium",
    "eulerian_hatch": "medium",
    "concentric_offset": "medium",
    "flowfield": "high",      # streamline integration over the field
    "tsp_opt": "high",        # 2-opt sweep with kd-tree neighbours
    "voronoi_stipple": "high",  # Lloyd relaxation iterations
    "squiggle": "medium",       # sub-pixel sampling per scan row
    "lowpoly": "high",          # Delaunay triangulation over sampled points
    "scribble": "medium",       # wobble polyline per scan run
    "grid": "low",              # two clipped line sweeps
    "brick": "low",             # course lines + staggered joints
    "dashes": "medium",         # hatch sweep chopped into dashes
    "truchet": "low",           # one diagonal per grid cell
    "rings": "medium",          # circle sampling per radius
    "sunburst": "medium",       # ray sampling per angle
    "circle_pack": "high",      # dart-throwing with overlap checks
}


def get_algorithm(name: str) -> RasterAlgorithm:
    """Return the raster algorithm registered under ``name``.

    Args:
        name: The algorithm identifier, e.g. ``"direct"``.

    Returns:
        The matching algorithm instance.

    Raises:
        KeyError: If no algorithm is registered under the name.
    """
    try:
        return _ALGORITHMS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown raster algorithm: {name!r}") from exc


def algorithm_kind(name: str) -> AlgorithmKind:
    """Return the family classification for a registered algorithm."""
    return _KINDS.get(name, "fill")


def algorithm_complexity(name: str) -> AlgorithmComplexity:
    """Return the static cost class for a registered algorithm.

    Unknown names default to ``"medium"`` so a never-classified algorithm
    surfaces in the UI without an aggressive "this will be fast" badge.
    """
    return _COMPLEXITY.get(name, "medium")


def available_algorithms() -> list[RasterAlgorithm]:
    """Return all registered raster algorithms."""
    return list(_ALGORITHMS.values())


__all__ = [
    "AlgorithmComplexity",
    "AlgorithmKind",
    "BrickAlgorithm",
    "CenterlineAlgorithm",
    "CirclePackAlgorithm",
    "ConcentricOffsetAlgorithm",
    "ContoursAlgorithm",
    "CrosshatchAlgorithm",
    "DashesAlgorithm",
    "DirectVectorizationAlgorithm",
    "EdgesAlgorithm",
    "EulerianHatchAlgorithm",
    "FlowFieldAlgorithm",
    "GosperFillAlgorithm",
    "GridAlgorithm",
    "HalftoneAlgorithm",
    "HilbertFillAlgorithm",
    "LowPolyAlgorithm",
    "RasterAlgorithm",
    "RingsAlgorithm",
    "ScanlinesAlgorithm",
    "ScribbleAlgorithm",
    "SpiralAlgorithm",
    "SquiggleAlgorithm",
    "StipplingAlgorithm",
    "SunburstAlgorithm",
    "TruchetAlgorithm",
    "TspAlgorithm",
    "TspOptimizedAlgorithm",
    "VoronoiStippleAlgorithm",
    "algorithm_complexity",
    "algorithm_kind",
    "available_algorithms",
    "get_algorithm",
]
