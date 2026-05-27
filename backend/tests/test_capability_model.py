"""Tests for the machine-profile Capability Model (roadmap A.5)."""

from __future__ import annotations

from pathlib import Path

import yaml

from pen_plotter.domain.capability import (
    CommandSource,
    HostMacroStep,
    MachineCapabilities,
    ManualSwapPrompt,
    RecoveryPolicy,
    ToolChangeStrategy,
    ToolingMode,
    derive_capabilities,
)
from pen_plotter.models import MachineProfile
from pen_plotter.profiles import export_profile_yaml, load_profiles


def _bare_profile_yaml(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Test Plotter",
        "units": "mm",
        "workspace": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
        "origin": "top_left",
        "gcode_dialect": "grbl",
        "pen_up_command": "G0 Z5",
        "pen_down_command": "G0 Z0",
        "tool_change_method": "manual_pause",
        "tool_change_command": "M0",
        "drawing_speed_mm_s": 50.0,
        "travel_speed_mm_s": 100.0,
        "acceleration_mm_s2": 1000.0,
        "pen_slot_count": 1,
    }
    base.update(overrides)
    return base


def test_derive_capabilities_for_manual_pause() -> None:
    caps = derive_capabilities("manual_pause", pen_slot_count=1)
    assert caps.tool_change.mode is ToolingMode.MANUAL
    assert caps.tool_change.command_source is CommandSource.OPERATOR
    assert caps.tool_change.recovery_policy is RecoveryPolicy.PAUSE_AND_PROMPT
    assert caps.tool_change.manual_prompt is not None


def test_derive_capabilities_for_carousel_is_firmware() -> None:
    caps = derive_capabilities("carousel", pen_slot_count=8)
    assert caps.tool_change.mode is ToolingMode.FIRMWARE
    assert caps.tool_change.command_source is CommandSource.MACHINE
    assert caps.max_pens_in_magazine == 8


def test_derive_capabilities_for_rack_is_host_macro() -> None:
    caps = derive_capabilities("rack", pen_slot_count=4)
    assert caps.tool_change.mode is ToolingMode.HOST_MACRO
    assert caps.tool_change.command_source is CommandSource.HOST


def test_derive_capabilities_for_none_is_single_pen() -> None:
    caps = derive_capabilities("none", pen_slot_count=1)
    assert caps.tool_change.mode is ToolingMode.SINGLE_PEN


def test_legacy_profile_loads_with_derived_capabilities() -> None:
    profile = MachineProfile.model_validate(_bare_profile_yaml())
    caps = profile.effective_capabilities()
    assert caps.tool_change.mode is ToolingMode.MANUAL


def test_explicit_capabilities_block_wins_over_legacy_field() -> None:
    payload = _bare_profile_yaml(
        tool_change_method="manual_pause",
        capabilities={
            "tool_change": {
                "mode": "host_macro",
                "command_source": "host",
                "recovery_policy": "abort",
                "host_macro": [
                    {"send": "M6 T{slot}", "wait_ms": 500},
                    {"send": "G4 P0", "wait_ms": 0},
                ],
            },
            "max_pens_in_magazine": 6,
        },
    )
    profile = MachineProfile.model_validate(payload)
    caps = profile.effective_capabilities()
    assert caps.tool_change.mode is ToolingMode.HOST_MACRO
    assert caps.tool_change.command_source is CommandSource.HOST
    assert caps.tool_change.recovery_policy is RecoveryPolicy.ABORT
    assert caps.tool_change.host_macro[0].send == "M6 T{slot}"
    assert caps.tool_change.host_macro[0].wait_ms == 500
    assert caps.max_pens_in_magazine == 6


def test_export_profile_yaml_roundtrips_capabilities() -> None:
    payload = _bare_profile_yaml(
        capabilities={
            "tool_change": {
                "mode": "firmware",
                "command_source": "machine",
                "recovery_policy": "pause_and_prompt",
            },
            "max_pens_in_magazine": 4,
        },
    )
    original = MachineProfile.model_validate(payload)
    yaml_text = export_profile_yaml(original)
    reread = MachineProfile.model_validate(yaml.safe_load(yaml_text))
    assert reread.effective_capabilities().tool_change.mode is ToolingMode.FIRMWARE


def test_bundled_axidraw_profile_still_loads(tmp_path: Path) -> None:
    profiles = load_profiles()
    by_name = {p.name: p for p in profiles}
    axidraw = by_name["AxiDraw V3"]
    caps = axidraw.effective_capabilities()
    assert caps.tool_change.mode is ToolingMode.MANUAL
    assert caps.max_pens_in_magazine == 1


def test_manual_prompt_template_defaults() -> None:
    prompt = ManualSwapPrompt()
    assert "{color}" in prompt.body
    assert prompt.timeout_s is None


def test_host_macro_step_validates() -> None:
    step = HostMacroStep(send="M6 T1", wait_ms=250)
    assert step.send == "M6 T1"
    assert step.wait_ms == 250


def test_machine_capabilities_default_construction() -> None:
    caps = MachineCapabilities()
    assert isinstance(caps.tool_change, ToolChangeStrategy)
    assert caps.tool_change.mode is ToolingMode.MANUAL
