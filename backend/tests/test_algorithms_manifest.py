"""Tests for the algorithms manifest provider (roadmap A.6)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.converters.algorithms import available_algorithms
from pen_plotter.main import app
from pen_plotter.manifests import get_manifest
from pen_plotter.manifests.algorithms import (
    ALGORITHMS_MANIFEST_VERSION,
    algorithms_manifest,
)


def test_algorithms_manifest_contains_every_registered_algo() -> None:
    manifest = algorithms_manifest()
    expected = {algo.name for algo in available_algorithms()}
    assert {entry.name for entry in manifest.entries} == expected


def test_algorithms_manifest_meta_has_version_and_domain() -> None:
    manifest = algorithms_manifest()
    assert manifest.meta.domain == "algorithms"
    assert manifest.meta.manifest_version == ALGORITHMS_MANIFEST_VERSION
    assert manifest.meta.schema_semver


def test_algorithms_manifest_entry_carries_metadata() -> None:
    manifest = algorithms_manifest()
    by_id = {entry.id: entry for entry in manifest.entries}
    assert "stippling" in by_id
    entry = by_id["stippling"]
    assert entry.kind in {"fill", "lines", "mono_stroke"}
    assert entry.complexity in {"low", "medium", "high"}
    assert entry.description


def test_algorithms_manifest_params_is_jsonschema_object() -> None:
    manifest = algorithms_manifest()
    for entry in manifest.entries:
        assert entry.params["type"] == "object"


def test_algorithms_manifest_registered_at_startup() -> None:
    manifest = get_manifest("algorithms")
    assert manifest.meta.domain == "algorithms"


@pytest.mark.asyncio
async def test_algorithms_manifest_via_http() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/manifests/algorithms")
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["domain"] == "algorithms"
    assert payload["meta"]["manifest_version"] == ALGORITHMS_MANIFEST_VERSION
    names = {entry["name"] for entry in payload["entries"]}
    assert "stippling" in names
    assert "halftone" in names


@pytest.mark.asyncio
async def test_algorithms_legacy_endpoint_still_works() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/algorithms")
    assert response.status_code == 200
    payload = response.json()
    legacy_names = {item["name"] for item in payload}
    manifest_names = {entry.name for entry in algorithms_manifest().entries}
    assert legacy_names == manifest_names
