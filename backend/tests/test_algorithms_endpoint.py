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


@pytest.mark.asyncio
async def test_algorithms_carry_complexity() -> None:
    """Every algorithm must declare a complexity bucket the UI can render."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/algorithms")
    items = response.json()
    by_name = {item["name"]: item for item in items}
    # TSP is the classic high-cost outlier; direct is a low-cost baseline.
    # Both are pinned so a future tweak to the cost table can't silently
    # invert the operator's expectations.
    assert by_name["tsp"]["complexity"] == "high"
    assert by_name["direct"]["complexity"] == "low"
    for item in items:
        assert item["complexity"] in {"low", "medium", "high"}
