"""Raster algorithm registry.

Algorithms are looked up by name so the converter and API can offer a stable
set of choices. Only fully implemented algorithms are registered here.

Each algorithm also declares a ``kind`` ("fill" / "lines" / "mono_stroke")
that the UI uses to group cards into families.
"""

from __future__ import annotations

from typing import Literal

from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.contours import ContoursAlgorithm
from pen_plotter.converters.algorithms.crosshatch import CrosshatchAlgorithm
from pen_plotter.converters.algorithms.direct import DirectVectorizationAlgorithm
from pen_plotter.converters.algorithms.edges import EdgesAlgorithm
from pen_plotter.converters.algorithms.halftone import HalftoneAlgorithm
from pen_plotter.converters.algorithms.scanlines import ScanlinesAlgorithm
from pen_plotter.converters.algorithms.spiral import SpiralAlgorithm
from pen_plotter.converters.algorithms.stippling import StipplingAlgorithm
from pen_plotter.converters.algorithms.tsp import TspAlgorithm

AlgorithmKind = Literal["fill", "lines", "mono_stroke"]

_ALGORITHMS: dict[str, RasterAlgorithm] = {
    algo.name: algo
    for algo in (
        DirectVectorizationAlgorithm(),
        HalftoneAlgorithm(),
        StipplingAlgorithm(),
        CrosshatchAlgorithm(),
        ContoursAlgorithm(),
        EdgesAlgorithm(),
        SpiralAlgorithm(),
        ScanlinesAlgorithm(),
        TspAlgorithm(),
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
    "spiral": "mono_stroke",
    "scanlines": "mono_stroke",
    "tsp": "mono_stroke",
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


def available_algorithms() -> list[RasterAlgorithm]:
    """Return all registered raster algorithms."""
    return list(_ALGORITHMS.values())


__all__ = [
    "AlgorithmKind",
    "ContoursAlgorithm",
    "CrosshatchAlgorithm",
    "DirectVectorizationAlgorithm",
    "EdgesAlgorithm",
    "HalftoneAlgorithm",
    "RasterAlgorithm",
    "ScanlinesAlgorithm",
    "SpiralAlgorithm",
    "StipplingAlgorithm",
    "TspAlgorithm",
    "algorithm_kind",
    "available_algorithms",
    "get_algorithm",
]
