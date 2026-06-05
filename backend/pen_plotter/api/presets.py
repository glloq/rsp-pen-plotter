"""Parameter preset endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pen_plotter.presets import (
    Preset,
    PresetExistsError,
    PresetLimitError,
    PresetNotFoundError,
    delete_user_preset,
    list_presets,
    save_user_preset,
)

router = APIRouter()


class PresetCreate(BaseModel):
    """Payload for creating / overwriting an operator preset."""

    name: str
    description: str = ""
    options: dict[str, Any]


@router.get("/presets")
async def presets() -> list[Preset]:
    """List the available raster conversion presets (builtin + user)."""
    return list_presets()


@router.post("/presets", status_code=201)
async def create_preset(body: PresetCreate) -> Preset:
    """Persist an operator-defined preset, replacing any same-name entry."""
    try:
        return save_user_preset(body.name, body.description, body.options)
    except PresetExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PresetLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/presets/{name}", status_code=204)
async def remove_preset(name: str) -> None:
    """Delete an operator-defined preset. Built-ins are read-only."""
    try:
        delete_user_preset(name)
    except PresetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown preset {name!r}") from exc
