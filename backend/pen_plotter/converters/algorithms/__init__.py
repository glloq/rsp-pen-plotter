"""Raster algorithm registry.

Algorithms are looked up by name so the converter and API can offer a stable
set of choices. Only fully implemented algorithms are registered here.
"""

from __future__ import annotations

from pen_plotter.converters.algorithms.base import RasterAlgorithm
from pen_plotter.converters.algorithms.direct import DirectVectorizationAlgorithm
from pen_plotter.converters.algorithms.halftone import HalftoneAlgorithm
from pen_plotter.converters.algorithms.stippling import StipplingAlgorithm

_ALGORITHMS: dict[str, RasterAlgorithm] = {
    algo.name: algo
    for algo in (
        DirectVectorizationAlgorithm(),
        HalftoneAlgorithm(),
        StipplingAlgorithm(),
    )
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


def available_algorithms() -> list[RasterAlgorithm]:
    """Return all registered raster algorithms."""
    return list(_ALGORITHMS.values())


__all__ = [
    "DirectVectorizationAlgorithm",
    "HalftoneAlgorithm",
    "RasterAlgorithm",
    "StipplingAlgorithm",
    "available_algorithms",
    "get_algorithm",
]
