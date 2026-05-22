"""Machine profile endpoints: list, fetch, export, and import."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from pen_plotter.models import MachineProfile
from pen_plotter.profiles import (
    export_profile_yaml,
    get_profile,
    load_profiles,
    save_profile,
)

router = APIRouter()


class ImportRequest(BaseModel):
    """A profile to import, as a YAML document."""

    yaml: str


@router.get("/profiles")
async def list_profiles() -> list[MachineProfile]:
    """List the configured machine profiles, sorted by name."""
    return load_profiles()


@router.get("/profiles/{name}")
async def get_one(name: str) -> MachineProfile:
    """Return a single profile by name.

    Raises:
        HTTPException: 404 if no profile with the name exists.
    """
    profile = get_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {name!r}")
    return profile


@router.get("/profiles/{name}/export", response_class=PlainTextResponse)
async def export_one(name: str) -> str:
    """Export a profile as YAML.

    Raises:
        HTTPException: 404 if no profile with the name exists.
    """
    profile = get_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {name!r}")
    return export_profile_yaml(profile)


@router.post("/profiles/import")
async def import_one(request: ImportRequest) -> MachineProfile:
    """Validate and persist an imported YAML profile.

    Raises:
        HTTPException: 422 if the YAML is malformed or fails validation.
    """
    try:
        data = yaml.safe_load(request.yaml)
        profile = MachineProfile.model_validate(data)
    except (yaml.YAMLError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid profile: {exc}") from exc
    save_profile(profile)
    return profile
