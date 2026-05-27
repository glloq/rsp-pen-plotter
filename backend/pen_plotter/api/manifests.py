"""``/manifests/...`` endpoints — generic domain dispatch."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from pen_plotter.errors import ApiError
from pen_plotter.manifests import (
    Manifest,
    UnknownManifestError,
    available_domains,
    get_manifest,
)

router = APIRouter()


class ManifestIndex(BaseModel):
    """Index of registered manifest domains."""

    domains: list[str]


@router.get("/manifests")
async def list_manifests() -> ManifestIndex:
    """List the manifest domains the backend serves.

    Returns:
        One entry per registered domain; the frontend uses this as a
        capability probe before requesting a specific manifest.
    """
    return ManifestIndex(domains=available_domains())


@router.get("/manifests/{domain}")
async def read_manifest(domain: str) -> Manifest[Any]:
    """Return the manifest for ``domain``.

    Raises:
        ApiError: ``manifest.unknown_domain`` (404) when the domain is
            not registered.
    """
    try:
        return get_manifest(domain)
    except UnknownManifestError as exc:
        raise ApiError(
            code="manifest.unknown_domain",
            message=f"no manifest registered for domain {domain!r}",
            status_code=404,
            details={"requested": domain, "available": available_domains()},
        ) from exc
