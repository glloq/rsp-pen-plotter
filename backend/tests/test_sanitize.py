import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.core.sanitize import sanitize_svg
from pen_plotter.main import app

MALICIOUS = (
    '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
    '<script>alert(2)</script>'
    '<rect width="10" height="10" onclick="evil()"/>'
    '<a href="javascript:alert(3)">x</a>'
    '<foreignObject><body>hi</body></foreignObject>'
    "</svg>"
)


def test_sanitize_strips_active_content() -> None:
    cleaned = sanitize_svg(MALICIOUS)
    assert "<script" not in cleaned
    assert "onload" not in cleaned
    assert "onclick" not in cleaned
    assert "javascript:" not in cleaned
    assert "foreignObject" not in cleaned.lower()
    assert "<rect" in cleaned  # benign geometry preserved


def test_sanitize_keeps_inkscape_labels() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
        '<g inkscape:label="red"><path d="M0 0 L1 1"/></g></svg>'
    )
    assert 'inkscape:label="red"' in sanitize_svg(svg)


@pytest.mark.asyncio
async def test_upload_strips_script_from_svg() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("evil.svg", MALICIOUS.encode(), "image/svg+xml")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 200
    assert "<script" not in response.json()["svg"]
    assert "onload" not in response.json()["svg"]


@pytest.mark.asyncio
async def test_upload_oversized_returns_413() -> None:
    big = b"x" * (50 * 1024 * 1024 + 1)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("big.png", big, "image/png")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_corrupt_image_returns_422() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("broken.png", b"not a real png", "image/png")},
            data={"profile_name": "Custom CoreXY A3"},
        )
    assert response.status_code == 422
