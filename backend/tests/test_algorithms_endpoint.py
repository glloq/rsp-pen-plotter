import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.converters.algorithms import available_algorithms
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


@pytest.mark.asyncio
async def test_algorithms_carry_options_schema() -> None:
    """Every algorithm's per-knob schema is shipped via the endpoint."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/algorithms")
    by_name = {item["name"]: item for item in response.json()}

    # Spot-check a few well-known schemas to lock the wire contract.
    halftone = by_name["halftone"]
    halftone_keys = {opt["key"]: opt for opt in halftone["options"]}
    assert halftone_keys["cell_size_px"]["min"] == 2  # backend clamps to 2
    assert halftone_keys["cell_size_px"]["default"] == 6

    tsp_opt = by_name["tsp_opt"]
    method = next(o for o in tsp_opt["options"] if o["key"] == "method")
    assert method["type"] == "select"
    assert "nn_2opt" in method["choices"]

    # Parameterless algorithms expose an explicit empty list (not null).
    assert by_name["direct"]["options"] == []


def test_every_option_spec_is_well_formed() -> None:
    """No malformed bounds, no duplicated keys per algorithm."""
    for algo in available_algorithms():
        seen: set[str] = set()
        for opt in algo.options_schema:
            assert opt.key not in seen, f"{algo.name}: duplicate option key {opt.key}"
            seen.add(opt.key)
            if opt.type in {"number", "integer"}:
                if opt.min is not None and opt.max is not None:
                    assert opt.min <= opt.max, (
                        f"{algo.name}.{opt.key}: min ({opt.min}) > max ({opt.max})"
                    )
                if opt.default is not None and opt.min is not None:
                    assert float(opt.default) >= opt.min, (
                        f"{algo.name}.{opt.key}: default {opt.default} below min {opt.min}"
                    )
                if opt.default is not None and opt.max is not None:
                    assert float(opt.default) <= opt.max, (
                        f"{algo.name}.{opt.key}: default {opt.default} above max {opt.max}"
                    )
            if opt.type == "select":
                assert opt.choices, f"{algo.name}.{opt.key}: select without choices"
                assert opt.default in opt.choices, (
                    f"{algo.name}.{opt.key}: default {opt.default!r} not in choices"
                )
