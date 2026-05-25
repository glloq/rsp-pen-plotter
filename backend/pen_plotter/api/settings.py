"""Small global settings the UI persists across reloads.

Today this hosts the ``palette_source`` toggle that decides whether the
per-layer colour picker reads from installed pens, the available-colours
inventory, or the union of both. The shape is intentionally narrow —
typed GET/PUT endpoints per setting — so each option's contract is
explicit and the OpenAPI schema documents the valid values. Future
settings ride alongside as their own typed pair.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from pen_plotter.persistence import get_setting, set_setting

router = APIRouter()


PaletteSource = Literal["pens", "available", "union"]
_PALETTE_SOURCE_KEY = "palette_source"
_PALETTE_SOURCE_DEFAULT: PaletteSource = "pens"


class PaletteSourceResponse(BaseModel):
    """Wire shape returned by ``GET /settings/palette-source``."""

    source: PaletteSource


class PaletteSourceUpdate(BaseModel):
    """Request body for ``PUT /settings/palette-source``."""

    source: PaletteSource


def load_palette_source() -> PaletteSource:
    """Read the stored setting, falling back to the default.

    A stored value that doesn't match the current enum (older schema,
    manual DB tinkering) silently degrades to the default rather than
    blowing up — the UI surfaces the source it actually applies.
    Public — used by the application layer (auto-attribution) to keep
    backend + frontend in lock-step on which pool to snap against.
    """
    raw = get_setting(_PALETTE_SOURCE_KEY)
    if raw in ("pens", "available", "union"):
        return raw  # type: ignore[return-value]
    return _PALETTE_SOURCE_DEFAULT


@router.get("/settings/palette-source", response_model=PaletteSourceResponse)
async def read_palette_source() -> PaletteSourceResponse:
    """Return the active palette source the per-layer picker reads from."""
    return PaletteSourceResponse(source=load_palette_source())


@router.put("/settings/palette-source", response_model=PaletteSourceResponse)
async def write_palette_source(body: PaletteSourceUpdate) -> PaletteSourceResponse:
    """Persist the operator's palette-source choice."""
    set_setting(_PALETTE_SOURCE_KEY, body.source)
    return PaletteSourceResponse(source=body.source)


__all__ = [
    "PaletteSource",
    "PaletteSourceResponse",
    "PaletteSourceUpdate",
    "load_palette_source",
    "router",
]
