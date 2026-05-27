"""Tests for the versioned manifest system (roadmap A.4)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.errors import ApiError
from pen_plotter.main import app
from pen_plotter.manifests import (
    Deprecation,
    Manifest,
    ManifestEntry,
    ManifestMeta,
    UnknownManifestError,
    available_domains,
    get_manifest,
    register_manifest,
)


class _DemoEntry(ManifestEntry):
    label: str = ""


def _demo_manifest() -> Manifest[Any]:
    return Manifest[_DemoEntry](
        meta=ManifestMeta(
            domain="demo",
            manifest_version=2,
            schema_semver="0.2.0",
            deprecations=[Deprecation(name="old_thing", deprecated_since=1, remove_after=4)],
            feature_flags={"beta_x": True},
        ),
        entries=[
            _DemoEntry(id="alpha", label="Alpha"),
            _DemoEntry(id="beta", label="Beta", deprecated=True),
        ],
    )


@pytest.fixture(autouse=True)
def _register_demo() -> None:
    register_manifest("demo", _demo_manifest)


def test_register_and_get_manifest_round_trip() -> None:
    m = get_manifest("demo")
    assert m.meta.domain == "demo"
    assert m.meta.manifest_version == 2
    assert m.meta.deprecations[0].name == "old_thing"
    assert {e.id for e in m.entries} == {"alpha", "beta"}


def test_get_manifest_unknown_raises() -> None:
    with pytest.raises(UnknownManifestError):
        get_manifest("does-not-exist")


def test_available_domains_includes_seeded() -> None:
    assert "system" in available_domains()
    assert "demo" in available_domains()


def test_apierror_envelope_has_normalized_shape() -> None:
    err = ApiError("demo.bad", "broken", status_code=418, details={"k": "v"})
    body = err.as_body(path="/x").model_dump()
    assert body == {
        "code": "demo.bad",
        "message": "broken",
        "details": {"k": "v"},
        "path": "/x",
    }


@pytest.mark.asyncio
async def test_endpoint_lists_domains_including_system() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/manifests")
    assert response.status_code == 200
    payload = response.json()
    assert "system" in payload["domains"]
    assert "demo" in payload["domains"]


@pytest.mark.asyncio
async def test_endpoint_returns_system_manifest_with_meta() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/manifests/system")
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["domain"] == "system"
    assert payload["meta"]["manifest_version"] >= 1
    assert "generated_at" in payload["meta"]
    assert isinstance(payload["entries"], list)


@pytest.mark.asyncio
async def test_endpoint_unknown_domain_returns_normalized_error() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/manifests/nope")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "manifest.unknown_domain"
    assert payload["path"] == "/manifests/nope"
    assert "requested" in payload["details"]
    assert "available" in payload["details"]
