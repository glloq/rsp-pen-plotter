"""Endpoint exposing the available raster algorithms."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from pen_plotter.converters.algorithms import (
    AlgorithmComplexity,
    AlgorithmKind,
    algorithm_complexity,
    algorithm_kind,
    available_algorithms,
)

router = APIRouter()


class AlgorithmInfo(BaseModel):
    """Metadata describing one raster algorithm choice."""

    name: str
    description: str
    # Family the UI uses to group cards: "fill" packs ink across the region,
    # "lines" emits discrete outlines, "mono_stroke" produces a single
    # continuous polyline (spiral / scanlines / TSP).
    kind: AlgorithmKind = "fill"
    # Static cost class. The UI seeds its preview-time estimator from this
    # before any /preview round-trip has been observed, then refines the
    # estimate with the real ``elapsed_ms`` history per (algorithm,
    # quality) pair.
    complexity: AlgorithmComplexity = "medium"


@router.get("/algorithms")
async def list_algorithms() -> list[AlgorithmInfo]:
    """List the raster algorithms the bitmap converter can apply.

    Returns:
        One entry per registered algorithm, for the UI to offer as choices.
    """
    return [
        AlgorithmInfo(
            name=algo.name,
            description=algo.description,
            kind=algorithm_kind(algo.name),
            complexity=algorithm_complexity(algo.name),
        )
        for algo in available_algorithms()
    ]
