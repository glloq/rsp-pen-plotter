"""Smoke tests for the bundled v0.2 plotter presets (roadmap B.6)."""

from __future__ import annotations

import pytest

from pen_plotter.domain.capability import ToolingMode
from pen_plotter.domain.toolchange import SwapContext, ToolChangeOrchestrator
from pen_plotter.models import MachineProfile
from pen_plotter.profiles import load_profiles

_EXPECTED_NAMES = {
    "AxiDraw V3",
    "NextDraw A2",
    "iDraw A3 (GRBL)",
    "Custom CoreXY A3",
    "Custom CoreXY A3 (rack)",
}


@pytest.fixture
def bundled() -> dict[str, MachineProfile]:
    return {p.name: p for p in load_profiles()}


def test_every_bundled_preset_is_loaded(bundled: dict[str, MachineProfile]) -> None:
    missing = _EXPECTED_NAMES - bundled.keys()
    assert not missing, f"missing presets: {missing}"


@pytest.mark.parametrize("name", sorted(_EXPECTED_NAMES))
def test_preset_validates_against_machine_profile(
    bundled: dict[str, MachineProfile], name: str
) -> None:
    profile = bundled[name]
    # All fields the rest of the codebase relies on are populated.
    assert profile.workspace.x_max > profile.workspace.x_min
    assert profile.workspace.y_max > profile.workspace.y_min
    assert profile.drawing_speed_mm_s > 0
    assert profile.travel_speed_mm_s > 0
    assert profile.acceleration_mm_s2 > 0
    assert profile.pen_slot_count >= 1
    # Capability Model populated (either explicit or derived).
    caps = profile.effective_capabilities()
    assert caps.tool_change.mode in set(ToolingMode)


def test_axidraw_routes_to_manual_strategy(bundled: dict[str, MachineProfile]) -> None:
    orch = ToolChangeOrchestrator(bundled["AxiDraw V3"])
    assert orch.mode is ToolingMode.MANUAL
    plan = orch.plan(SwapContext(pen_color="#ff0000"))
    assert plan.operator_prompt is not None


def test_nextdraw_uses_explicit_capability_block(
    bundled: dict[str, MachineProfile],
) -> None:
    profile = bundled["NextDraw A2"]
    caps = profile.effective_capabilities()
    assert caps.tool_change.mode is ToolingMode.MANUAL
    assert caps.tool_change.manual_prompt is not None
    assert "NextDraw" in caps.tool_change.manual_prompt.body


def test_idraw_grbl_uses_arc_support(bundled: dict[str, MachineProfile]) -> None:
    profile = bundled["iDraw A3 (GRBL)"]
    assert profile.gcode_dialect == "grbl"
    assert profile.supports_arcs is True


def test_corexy_rack_routes_to_host_macro_strategy(
    bundled: dict[str, MachineProfile],
) -> None:
    profile = bundled["Custom CoreXY A3 (rack)"]
    orch = ToolChangeOrchestrator(profile)
    assert orch.mode is ToolingMode.HOST_MACRO

    plan = orch.plan(
        SwapContext(slot_index=3, pen_label="Cyan", pen_color="#00ffff")
    )
    sends = [c.send for c in plan.commands]
    # Macro starts with the swap comment and ends with the "ready" comment.
    assert sends[0].startswith("; rack swap")
    assert "Cyan" in sends[0]
    assert "#00ffff" in sends[0]
    assert sends[-1].startswith("; ready")
    # And the slot index is substituted into the rack position line.
    assert any("X30 Y150" in s for s in sends)
    # Waits preserved.
    assert any(c.wait_ms == 500 for c in plan.commands)


def test_corexy_rack_advertises_magazine_size(
    bundled: dict[str, MachineProfile],
) -> None:
    profile = bundled["Custom CoreXY A3 (rack)"]
    assert profile.effective_capabilities().max_pens_in_magazine == 6


def test_all_bundled_profiles_route_through_orchestrator(
    bundled: dict[str, MachineProfile],
) -> None:
    # Every preset can produce *some* SwapPlan without raising. host_macro
    # presets exercise the placeholder substitution path through the
    # SwapContext; everything else exercises the default flow.
    for name, profile in bundled.items():
        orch = ToolChangeOrchestrator(profile)
        ctx = SwapContext(
            slot_index=1, pen_label="Black", pen_color="#000000", layer_id="l1"
        )
        plan = orch.plan(ctx)
        assert plan.mode in set(ToolingMode), name
