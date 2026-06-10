"""Cross-origin write guard for open mode (no API key configured).

With ``OMNIPLOT_API_KEY`` unset, several mutating endpoints accept
requests without a JSON body (``POST /plotter/pause``, ``POST
/macros/{name}/run``, …) — exactly the shape a cross-origin HTML form
or a DNS-rebinding page can produce. The ``_reject_cross_site_writes``
middleware must reject state-changing requests whose ``Origin`` header
is present and neither matches the request ``Host`` nor sits in the
CORS allow-list, while leaving header-less clients (curl, the SDK)
untouched.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_foreign_origin_write_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_API_KEY", raising=False)
    async with _client() as client:
        response = await client.post(
            "/plotter/pause", headers={"Origin": "http://evil.example"}
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_same_origin_write_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_API_KEY", raising=False)
    async with _client() as client:
        # base_url http://test ⇒ Host: test; a same-origin browser POST
        # carries Origin: http://test.
        response = await client.post("/plotter/pause", headers={"Origin": "http://test"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_allowlisted_dev_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Vite dev server origin (default CORS allow-list) keeps working."""
    monkeypatch.delenv("OMNIPLOT_API_KEY", raising=False)
    monkeypatch.delenv("OMNIPLOT_CORS_ORIGINS", raising=False)
    async with _client() as client:
        response = await client.post(
            "/plotter/pause", headers={"Origin": "http://localhost:5173"}
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_request_without_origin_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl / SDK requests carry no Origin header and must stay usable."""
    monkeypatch.delenv("OMNIPLOT_API_KEY", raising=False)
    async with _client() as client:
        response = await client.post("/plotter/pause")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_safe_methods_are_never_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_API_KEY", raising=False)
    async with _client() as client:
        response = await client.get(
            "/plotter/status", headers={"Origin": "http://evil.example"}
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_locked_mode_relies_on_api_key_not_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With an API key configured the guard steps aside: the key itself is
    the CSRF defence (an attacker's page cannot read or forge it)."""
    monkeypatch.setenv("OMNIPLOT_API_KEY", "sekrit")
    async with _client() as client:
        rejected = await client.post(
            "/plotter/pause", headers={"Origin": "http://evil.example"}
        )
        accepted = await client.post(
            "/plotter/pause",
            headers={"Origin": "http://evil.example", "X-API-Key": "sekrit"},
        )
    assert rejected.status_code == 401
    assert accepted.status_code == 200
