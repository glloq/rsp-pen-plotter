"""G-code generation endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.profiles import get_profile

router = APIRouter()


class GenerateLayer(BaseModel):
    """Per-layer generation settings."""

    layer_id: str
    target_pen_slot: int | None = None
    drawing_speed_mm_s: float | None = None


class GenerateRequest(BaseModel):
    """Request body for G-code generation."""

    svg: str
    profile_name: str
    layers: list[GenerateLayer] = Field(default_factory=list)
    scale_mode: Literal["fit", "actual"] = "fit"
    margin_mm: float = 10.0


class GenerateResponse(BaseModel):
    """Generated G-code and basic statistics."""

    gcode: str
    line_count: int


@router.post("/generate")
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate G-code for an SVG against a named machine profile.

    Args:
        request: The SVG, profile name, and per-layer settings.

    Returns:
        A :class:`GenerateResponse` with the G-code and its line count.

    Raises:
        HTTPException: 404 if the profile is unknown; 400 if generation fails.
    """
    profile = get_profile(request.profile_name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")

    try:
        gcode = generate_gcode(
            request.svg,
            profile,
            layers=[
                LayerGeneration(
                    layer_id=layer.layer_id,
                    target_pen_slot=layer.target_pen_slot,
                    drawing_speed_mm_s=layer.drawing_speed_mm_s,
                )
                for layer in request.layers
            ],
            scale_mode=request.scale_mode,
            margin_mm=request.margin_mm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GenerateResponse(gcode=gcode, line_count=gcode.count("\n"))
