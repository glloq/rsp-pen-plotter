"""Endpoint exposing the available Hershey fonts."""

from __future__ import annotations

from fastapi import APIRouter

from pen_plotter.typography import available_fonts

router = APIRouter()


@router.get("/fonts")
async def list_fonts() -> list[str]:
    """List the single-stroke Hershey fonts available for text rendering.

    Returns:
        Sorted font names for the typography panel to offer as choices.
    """
    return list(available_fonts())
