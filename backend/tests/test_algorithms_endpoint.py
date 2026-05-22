import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app


@pytest.mark.asyncio
async def test_list_algorithms() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/algorithms")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"direct", "halftone", "stippling"} <= names
