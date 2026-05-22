"""Endpoint exposing the available machine profiles."""

from __future__ import annotations

from fastapi import APIRouter

from pen_plotter.models import MachineProfile
from pen_plotter.profiles import load_profiles

router = APIRouter()


@router.get("/profiles")
async def list_profiles() -> list[MachineProfile]:
    """List the configured machine profiles.

    Returns:
        Every valid profile found in the profiles directory, sorted by name.
    """
    return load_profiles()
