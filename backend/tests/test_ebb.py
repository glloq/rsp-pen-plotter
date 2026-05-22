import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.core.ebb import generate_ebb
from pen_plotter.main import app
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
SVG = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="black" stroke="#000000"><path d="M0 0 L100 0 L100 100"/></g></svg>'
)


def _axidraw():
    profile = get_profile("AxiDraw V3")
    assert profile is not None
    assert profile.gcode_dialect == "ebb"
    return profile


def test_ebb_emits_setup_pen_moves_and_teardown() -> None:
    program = generate_ebb(SVG, _axidraw())
    lines = program.splitlines()
    assert "EM,1,1" in lines  # motors enabled
    assert any(line.startswith("SC,5,") for line in lines)  # servo up position
    assert "SP,1" in lines  # pen up command from profile
    assert "SP,0" in lines  # pen down command
    assert any(line.startswith("SM,") for line in lines)  # at least one stepper move
    assert lines[-1] == "EM,0,0"  # motors disabled at the end


def test_ebb_move_uses_hbot_mixing_and_steps_per_mm() -> None:
    # The first SM is the travel-in; the first *drawing* move is the horizontal
    # segment (0,0)->(100,0): a = (dx+dy)*spm, b = (dx-dy)*spm, both 100*80.
    profile = _axidraw()
    assert profile.ebb.steps_per_mm == 80.0
    program = generate_ebb(SVG, profile, scale_mode="actual")
    moves = [line for line in program.splitlines() if line.startswith("SM,")]
    assert len(moves) >= 2
    _, a, b = moves[1].split(",")[1:]
    assert int(a) == 8000
    assert int(b) == 8000


def test_ebb_no_step_drift_round_trip() -> None:
    # A closed loop's drawing moves (excluding the initial travel) net to zero,
    # confirming the step accumulator does not drift through rounding.
    profile = _axidraw()
    square = (
        f'<svg {NS} viewBox="0 0 10 10"><g inkscape:label="k" stroke="#000000">'
        '<path d="M0 0 L10 0 L10 10 L0 10 L0 0"/></g></svg>'
    )
    program = generate_ebb(square, profile, scale_mode="actual")
    moves = [line for line in program.splitlines() if line.startswith("SM,")]
    draw_moves = moves[1:]  # skip the travel-in move
    a_total = sum(int(line.split(",")[2]) for line in draw_moves)
    b_total = sum(int(line.split(",")[3]) for line in draw_moves)
    assert a_total == 0
    assert b_total == 0


@pytest.mark.asyncio
async def test_generate_endpoint_dispatches_ebb() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/generate", json={"svg": SVG, "profile_name": "AxiDraw V3"})
    assert response.status_code == 200
    gcode = response.json()["gcode"]
    assert "SM," in gcode
    assert "G1 " not in gcode  # not G-code
