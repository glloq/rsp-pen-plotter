"""Toolpath optimization endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.core.layers import extract_layers
from pen_plotter.core.toolpath import LayerOptimization, ToolpathMetrics, optimize_svg
from pen_plotter.models import LayerInfo

router = APIRouter()


class OptimizeRequest(BaseModel):
    """Request body for toolpath optimization."""

    svg: str
    layers: list[LayerOptimization] = Field(default_factory=list)
    merge_tolerance_mm: float = 0.1


class OptimizeResponse(BaseModel):
    """Optimized SVG, re-extracted layers, and travel metrics."""

    svg: str
    layers: list[LayerInfo]
    metrics: ToolpathMetrics


@router.post("/optimize")
async def optimize(request: OptimizeRequest) -> OptimizeResponse:
    """Optimize toolpaths to reduce pen-up travel.

    Args:
        request: The SVG to optimize plus optional per-layer settings.

    Returns:
        An :class:`OptimizeResponse` with the optimized SVG, refreshed layer
        descriptors, and before/after travel metrics.

    Raises:
        HTTPException: 400 if the SVG cannot be processed.
    """
    try:
        result = optimize_svg(
            request.svg,
            layers=request.layers,
            merge_tolerance_mm=request.merge_tolerance_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # vpype/geometry failures
        raise HTTPException(status_code=422, detail=f"Optimization failed: {exc}") from exc

    return OptimizeResponse(
        svg=result.svg,
        layers=extract_layers(result.svg),
        metrics=result.metrics,
    )
