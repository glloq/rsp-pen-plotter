"""Pre-run check endpoint: bounds, estimates, and pen-magazine validation."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.api.generate import GenerateLayer
from pen_plotter.core.gcode import LayerGeneration
from pen_plotter.core.preflight import preflight_report
from pen_plotter.models import PreflightReport
from pen_plotter.profiles import get_profile

router = APIRouter()


class PreflightRequest(BaseModel):
    """Request body for a pre-run check; mirrors the generate request."""

    svg: str
    profile_name: str
    layers: list[GenerateLayer] = Field(default_factory=list)
    scale_mode: Literal["fit", "actual"] = "fit"
    margin_mm: float = 10.0


@router.post("/preflight")
async def preflight(request: PreflightRequest) -> PreflightReport:
    """Validate and estimate a placed drawing before generating/sending it.

    Raises:
        HTTPException: 404 if the profile is unknown; 400 if the SVG cannot be
            parsed.
    """
    profile = get_profile(request.profile_name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")

    layer_settings = [
        LayerGeneration(
            layer_id=layer.layer_id,
            target_pen_slot=layer.target_pen_slot,
            drawing_speed_mm_s=layer.drawing_speed_mm_s,
        )
        for layer in request.layers
    ]
    try:
        return preflight_report(
            request.svg,
            profile,
            layers=layer_settings,
            scale_mode=request.scale_mode,
            margin_mm=request.margin_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
