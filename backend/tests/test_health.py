import httpx
import pytest
from httpx import ASGITransport

from pen_plotter import __version__
from pen_plotter.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    # Assert against the package version so a release bump doesn't break this.
    assert response.json() == {"status": "ok", "version": __version__}
