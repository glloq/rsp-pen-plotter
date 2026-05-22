"""Endpoint exposing the available raster algorithms."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from pen_plotter.converters.algorithms import available_algorithms

router = APIRouter()


class AlgorithmInfo(BaseModel):
    """Metadata describing one raster algorithm choice."""

    name: str
    description: str


@router.get("/algorithms")
async def list_algorithms() -> list[AlgorithmInfo]:
    """List the raster algorithms the bitmap converter can apply.

    Returns:
        One entry per registered algorithm, for the UI to offer as choices.
    """
    return [
        AlgorithmInfo(name=algo.name, description=algo.description)
        for algo in available_algorithms()
    ]
