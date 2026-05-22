import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app

SVG_SAMPLE = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'


def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_upload_svg_dispatches_to_svg_converter() -> None:
    async with _client() as client:
        response = await client.post(
            "/upload",
            files={"file": ("drawing.svg", SVG_SAMPLE, "image/svg+xml")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["source_mime"] == "image/svg+xml"
    assert body["source_file"] == "drawing.svg"
    assert body["profile_name"] == "Custom CoreXY A3"
    assert body["status"] == "ready"
    assert body["layers"] == []


@pytest.mark.asyncio
async def test_upload_resolves_mime_from_extension() -> None:
    async with _client() as client:
        response = await client.post(
            "/upload",
            files={"file": ("drawing.svg", SVG_SAMPLE, "application/octet-stream")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 200
    assert response.json()["source_mime"] == "image/svg+xml"


@pytest.mark.asyncio
async def test_upload_unsupported_format_returns_415() -> None:
    async with _client() as client:
        response = await client.post(
            "/upload",
            files={"file": ("model.stl", b"solid foo", "model/stl")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 415
