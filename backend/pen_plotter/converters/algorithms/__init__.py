"""Raster algorithm registry.

Algorithms are looked up by name so the converter and API can offer a stable
set of choices. Only fully implemented algorithms are registered here.

Each algorithm also declares a ``kind`` ("fill" / "lines" / "mono_stroke")
that the UI uses to group cards into families.
"""

from __future__ import annotations

from typing import Literal

from pen_plotter.converters.algorithms.attractor import AttractorAlgorithm
from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.brick import BrickAlgorithm
from pen_plotter.converters.algorithms.centerline import CenterlineAlgorithm
from pen_plotter.converters.algorithms.chladni import ChladniAlgorithm
from pen_plotter.converters.algorithms.circle_pack import CirclePackAlgorithm
from pen_plotter.converters.algorithms.concentric_offset import ConcentricOffsetAlgorithm
from pen_plotter.converters.algorithms.contours import ContoursAlgorithm
from pen_plotter.converters.algorithms.crosshatch import CrosshatchAlgorithm
from pen_plotter.converters.algorithms.cubic_disarray import CubicDisarrayAlgorithm
from pen_plotter.converters.algorithms.curve_stitching import CurveStitchingAlgorithm
from pen_plotter.converters.algorithms.dashes import DashesAlgorithm
from pen_plotter.converters.algorithms.direct import DirectVectorizationAlgorithm
from pen_plotter.converters.algorithms.dither import DitherAlgorithm
from pen_plotter.converters.algorithms.edges import EdgesAlgorithm
from pen_plotter.converters.algorithms.etch import EtchAlgorithm
from pen_plotter.converters.algorithms.eulerian_hatch import EulerianHatchAlgorithm
from pen_plotter.converters.algorithms.flowfield import FlowFieldAlgorithm
from pen_plotter.converters.algorithms.gosper import GosperFillAlgorithm
from pen_plotter.converters.algorithms.grid import GridAlgorithm
from pen_plotter.converters.algorithms.halftone import HalftoneAlgorithm
from pen_plotter.converters.algorithms.harmonograph import HarmonographAlgorithm
from pen_plotter.converters.algorithms.hilbert import HilbertFillAlgorithm
from pen_plotter.converters.algorithms.hitomezashi import HitomezashiAlgorithm
from pen_plotter.converters.algorithms.honeycomb import HoneycombAlgorithm
from pen_plotter.converters.algorithms.lowpoly import LowPolyAlgorithm
from pen_plotter.converters.algorithms.lsystem import LSystemAlgorithm
from pen_plotter.converters.algorithms.maze import MazeAlgorithm
from pen_plotter.converters.algorithms.moire import MoireAlgorithm
from pen_plotter.converters.algorithms.noise_contours import NoiseContoursAlgorithm
from pen_plotter.converters.algorithms.penrose import PenroseAlgorithm
from pen_plotter.converters.algorithms.phyllotaxis import PhyllotaxisAlgorithm
from pen_plotter.converters.algorithms.quadtree import QuadtreeAlgorithm
from pen_plotter.converters.algorithms.reaction_diffusion import ReactionDiffusionAlgorithm
from pen_plotter.converters.algorithms.ridge_lines import RidgeLinesAlgorithm
from pen_plotter.converters.algorithms.rings import RingsAlgorithm
from pen_plotter.converters.algorithms.scanlines import ScanlinesAlgorithm
from pen_plotter.converters.algorithms.scribble import ScribbleAlgorithm
from pen_plotter.converters.algorithms.sine_halftone import SineHalftoneAlgorithm
from pen_plotter.converters.algorithms.space_colonization import SpaceColonizationAlgorithm
from pen_plotter.converters.algorithms.spiral import SpiralAlgorithm
from pen_plotter.converters.algorithms.squiggle import SquiggleAlgorithm
from pen_plotter.converters.algorithms.stippling import StipplingAlgorithm
from pen_plotter.converters.algorithms.string_art import StringArtAlgorithm
from pen_plotter.converters.algorithms.sunburst import SunburstAlgorithm
from pen_plotter.converters.algorithms.superpixel_hatch import SuperpixelHatchAlgorithm
from pen_plotter.converters.algorithms.text_fill import TextFillAlgorithm
from pen_plotter.converters.algorithms.truchet import TruchetAlgorithm
from pen_plotter.converters.algorithms.tsp import TspAlgorithm
from pen_plotter.converters.algorithms.tsp_opt import TspOptimizedAlgorithm
from pen_plotter.converters.algorithms.voronoi_mosaic import VoronoiMosaicAlgorithm
from pen_plotter.converters.algorithms.voronoi_stipple import VoronoiStippleAlgorithm
from pen_plotter.converters.algorithms.weave import WeaveAlgorithm

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
        RidgeLinesAlgorithm(),
        HitomezashiAlgorithm(),
        CubicDisarrayAlgorithm(),
        QuadtreeAlgorithm(),
        MazeAlgorithm(),
        PhyllotaxisAlgorithm(),
        VoronoiMosaicAlgorithm(),
        CurveStitchingAlgorithm(),
        StringArtAlgorithm(),
        SpaceColonizationAlgorithm(),
        PenroseAlgorithm(),
        DitherAlgorithm(),
        EtchAlgorithm(),
        NoiseContoursAlgorithm(),
        ReactionDiffusionAlgorithm(),
        SuperpixelHatchAlgorithm(),
        MoireAlgorithm(),
        WeaveAlgorithm(),
        HoneycombAlgorithm(),
        HarmonographAlgorithm(),
        AttractorAlgorithm(),
        TextFillAlgorithm(),
        LSystemAlgorithm(),
        ChladniAlgorithm(),
        SineHalftoneAlgorithm(),
    )
}

# Algorithms kept registered (persisted placements and presets keep
# rendering) but hidden from the editor's pickers — each is a strict or
# near duplicate of a better-tuned entry:
#   * tsp            → tsp_opt(method="nn") is byte-equivalent, the other
#                      methods strictly better
#   * grid           → crosshatch(angle=0, crossed=True)
#   * eulerian_hatch → crosshatch(joined=True)
#   * contours       → concentric_offset (marching-squares quality vs the
#                      deliberately approximate hull walk)
_HIDDEN: frozenset[str] = frozenset({"tsp", "grid", "eulerian_hatch", "contours"})

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
    "sine_halftone": "mono_stroke",
    "lowpoly": "lines",
    "scribble": "fill",
    "grid": "lines",
    "brick": "lines",
    "dashes": "fill",
    "truchet": "lines",
    "rings": "mono_stroke",
    "sunburst": "mono_stroke",
    "circle_pack": "fill",
    "ridge_lines": "fill",
    "hitomezashi": "lines",
    "cubic_disarray": "lines",
    "quadtree": "lines",
    "maze": "lines",
    "phyllotaxis": "fill",
    "voronoi_mosaic": "lines",
    "curve_stitching": "lines",
    "string_art": "mono_stroke",
    "space_colonization": "lines",
    "penrose": "lines",
    "dither": "fill",
    "etch": "fill",
    "noise_contours": "lines",
    "reaction_diffusion": "fill",
    "superpixel_hatch": "fill",
    "moire": "lines",
    "weave": "lines",
    "honeycomb": "lines",
    "harmonograph": "mono_stroke",
    "attractor": "fill",
    "text_fill": "fill",
    "lsystem": "lines",
    "chladni": "lines",
}

# Rough cost class per algorithm — see ``AlgorithmComplexity`` above for
# the meaning of low/medium/high. Reviewed against typical /preview
# latencies on a Pi-class device with the default detail tier; tweak
# alongside any algorithm-internal changes that change runtime scaling.
_COMPLEXITY: dict[str, AlgorithmComplexity] = {
    "direct": "low",  # potrace on a small label mask
    "halftone": "low",  # uniform dot grid
    "stippling": "medium",  # Poisson-disk sampling
    "crosshatch": "medium",
    "contours": "low",
    "edges": "low",
    "centerline": "medium",  # thinning + path extraction
    "spiral": "medium",
    "scanlines": "low",
    "tsp": "high",  # tour optimisation dominates
    "hilbert": "medium",
    "gosper": "medium",
    "eulerian_hatch": "medium",
    "concentric_offset": "medium",
    "flowfield": "high",  # streamline integration over the field
    "tsp_opt": "high",  # 2-opt sweep with kd-tree neighbours
    "voronoi_stipple": "high",  # Lloyd relaxation iterations
    "squiggle": "medium",  # sub-pixel sampling per scan row
    "sine_halftone": "medium",  # sub-pixel sampling per scan row
    "lowpoly": "high",  # Delaunay triangulation over sampled points
    "scribble": "medium",  # wobble polyline per scan run
    "grid": "low",  # two clipped line sweeps
    "brick": "low",  # course lines + staggered joints
    "dashes": "medium",  # hatch sweep chopped into dashes
    "truchet": "low",  # one diagonal per grid cell
    "rings": "medium",  # circle sampling per radius
    "sunburst": "medium",  # ray sampling per angle
    "circle_pack": "high",  # dart-throwing with overlap checks
    "ridge_lines": "low",  # one displaced polyline per row
    "hitomezashi": "low",  # two phase-bit dash sweeps
    "cubic_disarray": "low",  # one square per grid cell
    "quadtree": "medium",  # SAT means, log-depth subdivision
    "maze": "medium",  # DFS spanning tree over grid cells
    "phyllotaxis": "medium",  # one tone lookup per spiral point
    "voronoi_mosaic": "high",  # site sampling + Lloyd step + qhull
    "curve_stitching": "low",  # fixed chord fan per cell
    "string_art": "high",  # greedy chord search per thread hop
    "space_colonization": "high",  # kd-tree per growth iteration
    "penrose": "medium",  # exponential triangle count in divisions
    "dither": "medium",  # python-loop error diffusion over the cell grid
    "etch": "medium",  # one short stroke per grid site
    "noise_contours": "medium",  # fBm synthesis + marching squares per level
    "reaction_diffusion": "high",  # thousands of Gray–Scott steps
    "superpixel_hatch": "high",  # SLIC + per-region hatch sweeps
    "moire": "low",  # two clipped pattern families
    "weave": "low",  # two ribbon sweeps
    "honeycomb": "low",  # one hex outline per cell
    "harmonograph": "medium",  # tens of thousands of curve samples
    "attractor": "medium",  # sequential chaotic-map iteration
    "text_fill": "medium",  # glyph stroke clipping per row
    "lsystem": "medium",  # capped string expansion + turtle walk
    "chladni": "low",  # one smooth field + marching squares
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


def algorithm_hidden(name: str) -> bool:
    """True when ``name`` should be hidden from the editor's pickers.

    Hidden algorithms stay fully registered — persisted placements and
    presets that reference them keep rendering — they just stop being
    offered for *new* layers because a visible entry covers the same
    output (see ``_HIDDEN`` above).
    """
    return name in _HIDDEN


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
    "AttractorAlgorithm",
    "BrickAlgorithm",
    "CenterlineAlgorithm",
    "ChladniAlgorithm",
    "CirclePackAlgorithm",
    "ConcentricOffsetAlgorithm",
    "ContoursAlgorithm",
    "CrosshatchAlgorithm",
    "CubicDisarrayAlgorithm",
    "CurveStitchingAlgorithm",
    "DashesAlgorithm",
    "DirectVectorizationAlgorithm",
    "DitherAlgorithm",
    "EdgesAlgorithm",
    "EtchAlgorithm",
    "EulerianHatchAlgorithm",
    "FlowFieldAlgorithm",
    "GosperFillAlgorithm",
    "GridAlgorithm",
    "HalftoneAlgorithm",
    "HarmonographAlgorithm",
    "HilbertFillAlgorithm",
    "HitomezashiAlgorithm",
    "HoneycombAlgorithm",
    "LSystemAlgorithm",
    "LowPolyAlgorithm",
    "MazeAlgorithm",
    "MoireAlgorithm",
    "NoiseContoursAlgorithm",
    "PenroseAlgorithm",
    "PhyllotaxisAlgorithm",
    "QuadtreeAlgorithm",
    "RasterAlgorithm",
    "ReactionDiffusionAlgorithm",
    "RidgeLinesAlgorithm",
    "RingsAlgorithm",
    "ScanlinesAlgorithm",
    "ScribbleAlgorithm",
    "SpaceColonizationAlgorithm",
    "SpiralAlgorithm",
    "SquiggleAlgorithm",
    "StipplingAlgorithm",
    "StringArtAlgorithm",
    "SunburstAlgorithm",
    "SuperpixelHatchAlgorithm",
    "TextFillAlgorithm",
    "TruchetAlgorithm",
    "TspAlgorithm",
    "TspOptimizedAlgorithm",
    "VoronoiMosaicAlgorithm",
    "VoronoiStippleAlgorithm",
    "WeaveAlgorithm",
    "algorithm_complexity",
    "algorithm_hidden",
    "algorithm_kind",
    "available_algorithms",
    "get_algorithm",
]
