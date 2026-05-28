"""Toolpath optimization endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.core.layers import extract_layers
from pen_plotter.core.toolpath import (
    LayerOptimization,
    ToolpathMetrics,
    ToolpathResult,
    optimize_geometry_ir,
    optimize_svg,
)
from pen_plotter.domain.ir.adapter import content_sha256, is_ir_enabled
from pen_plotter.models import LayerInfo

_log = logging.getLogger(__name__)

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

    When ``OMNIPLOT_IR_ENABLED=1`` and a matching :class:`GeometryIR`
    artifact has been previously cached for this SVG, we route through
    :func:`optimize_geometry_ir` so the IR path gets real traffic in
    production. The SVG path stays the fallback when no cached IR is
    available (typical fresh upload, no prior cache hit).

    Args:
        request: The SVG to optimize plus optional per-layer settings.

    Returns:
        An :class:`OptimizeResponse` with the optimized SVG, refreshed layer
        descriptors, and before/after travel metrics.

    Raises:
        HTTPException: 400 if the SVG cannot be processed.
    """
    try:
        result = _optimize_with_ir_when_available(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # vpype/geometry failures
        raise HTTPException(status_code=422, detail=f"Optimization failed: {exc}") from exc

    return OptimizeResponse(
        svg=result.svg,
        layers=extract_layers(result.svg),
        metrics=result.metrics,
    )


def _optimize_with_ir_when_available(request: OptimizeRequest) -> ToolpathResult:
    """Pick the IR-driven path when the flag is on, else SVG.

    When ``OMNIPLOT_IR_ENABLED=1`` we (1) try the SVG-hash-keyed
    cache populated by previous runs and (2) build the IR fresh from
    the request SVG when there's no cache hit. Either way we end up
    calling :func:`optimize_geometry_ir` — that's the whole point of
    the flag: give the IR path real production traffic so any
    behavioural drift surfaces during the v2.0 migration window.
    """
    if not is_ir_enabled():
        return optimize_svg(
            request.svg,
            layers=request.layers,
            merge_tolerance_mm=request.merge_tolerance_mm,
        )
    from pen_plotter.application.ir_cache import fetch_geometry, store_geometry
    from pen_plotter.domain.ir.adapter import geometry_ir_from_svg

    svg_hash = content_sha256(request.svg.encode("utf-8"))
    geometry = fetch_geometry(svg_hash, {})
    if geometry is None:
        geometry = geometry_ir_from_svg(request.svg, source_hash=svg_hash)
        store_geometry(svg_hash, {}, geometry)
        _log.info("optimize_ir_built", extra={"svg_hash": svg_hash[:12]})
    else:
        _log.info("optimize_ir_cache_hit", extra={"svg_hash": svg_hash[:12]})
    return optimize_geometry_ir(
        geometry,
        layers=request.layers,
        merge_tolerance_mm=request.merge_tolerance_mm,
    )
