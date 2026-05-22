"""Parameter preset endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from pen_plotter.presets import Preset, list_presets

router = APIRouter()


@router.get("/presets")
async def presets() -> list[Preset]:
    """List the available raster conversion presets."""
    return list_presets()
