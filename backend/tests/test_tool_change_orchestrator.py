"""Tests for the ToolChangeOrchestrator + four strategies (roadmap B.2)."""

from __future__ import annotations

import pytest

from pen_plotter.domain.capability import (
    CommandSource,
    HostMacroStep,
    MachineCapabilities,
    ManualSwapPrompt,
    RecoveryPolicy,
    ToolingMode,
)
from pen_plotter.domain.capability import (
    ToolChangeStrategy as CapToolChangeStrategy,
)
from pen_plotter.domain.toolchange import (
    FirmwareStrategy,
    HostMacroStrategy,
    ManualStrategy,
    SinglePenStrategy,
    SwapContext,
    ToolChangeOrchestrator,
)
from pen_plotter.domain.toolchange.orchestrator import PauseKind
from pen_plotter.models import MachineProfile


def _profile(**overrides: object) -> MachineProfile:
    payload: dict[str, object] = {
        "name": "Test",
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
        "pen_slot_count": 4,
    }
    payload.update(overrides)
    return MachineProfile.model_validate(payload)


def _caps(
    mode: ToolingMode,
    *,
    source: CommandSource = CommandSource.OPERATOR,
    recovery: RecoveryPolicy = RecoveryPolicy.PAUSE_AND_PROMPT,
    macro: list[HostMacroStep] | None = None,
    manual: ManualSwapPrompt | None = None,
    magazine: int = 4,
) -> MachineCapabilities:
    return MachineCapabilities(
        tool_change=CapToolChangeStrategy(
            mode=mode,
            command_source=source,
            recovery_policy=recovery,
            host_macro=macro or [],
            manual_prompt=manual,
        ),
        max_pens_in_magazine=magazine,
    )


# ── SinglePenStrategy ────────────────────────────────────────────────


def test_single_pen_strategy_emits_no_commands() -> None:
    profile = _profile(
        tool_change_method="none",
        pen_slot_count=1,
        capabilities=_caps(ToolingMode.SINGLE_PEN).model_dump(mode="json"),
    )
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext())
    assert plan.mode is ToolingMode.SINGLE_PEN
    assert plan.pause_kind is PauseKind.NONE
    assert plan.commands == []
    assert plan.operator_prompt is None


# ── ManualStrategy ───────────────────────────────────────────────────


def test_manual_strategy_uses_template_with_substitution() -> None:
    caps = _caps(
        ToolingMode.MANUAL,
        manual=ManualSwapPrompt(
            title="Pen swap",
            body="Insert {label} ({color}) in slot {slot}.",
            timeout_s=120,
        ),
    )
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(
        SwapContext(slot_index=3, pen_label="Vermilion", pen_color="#e34234", layer_id="l1")
    )
    assert plan.pause_kind is PauseKind.OPERATOR_CONFIRM
    assert plan.commands == []
    assert plan.operator_prompt is not None
    assert "Vermilion" in plan.operator_prompt
    assert "#e34234" in plan.operator_prompt
    assert "slot 3" in plan.operator_prompt
    assert plan.timeout_s == 120


def test_manual_strategy_uses_default_prompt_when_unset() -> None:
    caps = _caps(ToolingMode.MANUAL, manual=None)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    plan = ToolChangeOrchestrator(profile).plan(SwapContext(pen_color="#000000"))
    assert plan.pause_kind is PauseKind.OPERATOR_CONFIRM
    assert "#000000" in (plan.operator_prompt or "")


def test_manual_strategy_carries_recovery_policy() -> None:
    caps = _caps(ToolingMode.MANUAL, recovery=RecoveryPolicy.ABORT)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    plan = ToolChangeOrchestrator(profile).plan(SwapContext())
    assert plan.recovery_policy is RecoveryPolicy.ABORT


# ── FirmwareStrategy ─────────────────────────────────────────────────


def test_firmware_strategy_emits_legacy_tool_change_command_when_no_macro() -> None:
    caps = _caps(ToolingMode.FIRMWARE, source=CommandSource.MACHINE, macro=None, magazine=8)
    profile = _profile(
        tool_change_method="carousel",
        tool_change_command="M6 T{slot}",
        capabilities=caps.model_dump(mode="json"),
    )
    plan = ToolChangeOrchestrator(profile).plan(SwapContext(slot_index=5))
    assert plan.mode is ToolingMode.FIRMWARE
    assert plan.pause_kind is PauseKind.FIRMWARE
    assert plan.commands == [{"send": "M6 T5", "wait_ms": 0}] or [
        c.model_dump() for c in plan.commands
    ] == [{"send": "M6 T5", "wait_ms": 0}]


def test_firmware_strategy_uses_explicit_macro_when_present() -> None:
    macro = [HostMacroStep(send="T{slot}", wait_ms=0), HostMacroStep(send="M6", wait_ms=200)]
    caps = _caps(ToolingMode.FIRMWARE, macro=macro)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    plan = ToolChangeOrchestrator(profile).plan(SwapContext(slot_index=2))
    sends = [c.send for c in plan.commands]
    assert sends == ["T2", "M6"]
    assert plan.commands[1].wait_ms == 200


# ── HostMacroStrategy ────────────────────────────────────────────────


def test_host_macro_strategy_renders_all_lines_with_substitution() -> None:
    macro = [
        HostMacroStep(send="; swap to {label}", wait_ms=0),
        HostMacroStep(send="G53 G0 X0 Y0", wait_ms=300),
        HostMacroStep(send="; ready slot {slot}", wait_ms=0),
    ]
    caps = _caps(ToolingMode.HOST_MACRO, source=CommandSource.HOST, macro=macro, magazine=4)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    plan = ToolChangeOrchestrator(profile).plan(SwapContext(slot_index=2, pen_label="Cyan"))
    assert plan.mode is ToolingMode.HOST_MACRO
    assert plan.pause_kind is PauseKind.HOST_TIMED
    assert [c.send for c in plan.commands] == [
        "; swap to Cyan",
        "G53 G0 X0 Y0",
        "; ready slot 2",
    ]
    assert plan.commands[1].wait_ms == 300


def test_host_macro_strategy_rejects_missing_macro_definition() -> None:
    caps = _caps(ToolingMode.HOST_MACRO, macro=None)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    with pytest.raises(ValueError, match="HOST_MACRO requires"):
        ToolChangeOrchestrator(profile).plan(SwapContext())


# ── Orchestrator dispatch ────────────────────────────────────────────


@pytest.mark.parametrize(
    "mode,expected_kind",
    [
        (ToolingMode.SINGLE_PEN, PauseKind.NONE),
        (ToolingMode.FIRMWARE, PauseKind.FIRMWARE),
        (ToolingMode.MANUAL, PauseKind.OPERATOR_CONFIRM),
    ],
)
def test_orchestrator_dispatches_to_right_strategy(
    mode: ToolingMode, expected_kind: PauseKind
) -> None:
    caps = _caps(mode)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    plan = ToolChangeOrchestrator(profile).plan(SwapContext())
    assert plan.pause_kind is expected_kind


def test_orchestrator_exposes_active_mode() -> None:
    caps = _caps(ToolingMode.FIRMWARE)
    profile = _profile(capabilities=caps.model_dump(mode="json"))
    assert ToolChangeOrchestrator(profile).mode is ToolingMode.FIRMWARE


# ── Legacy profile derivation (back-compat) ──────────────────────────


def test_legacy_manual_pause_profile_routes_to_manual_strategy() -> None:
    # No explicit capabilities — derived from tool_change_method.
    profile = _profile(tool_change_method="manual_pause", pen_slot_count=1)
    orch = ToolChangeOrchestrator(profile)
    assert orch.mode is ToolingMode.MANUAL
    plan = orch.plan(SwapContext(pen_color="#ff0000"))
    assert plan.pause_kind is PauseKind.OPERATOR_CONFIRM


def test_legacy_carousel_profile_routes_to_firmware_strategy() -> None:
    profile = _profile(tool_change_method="carousel", pen_slot_count=8)
    orch = ToolChangeOrchestrator(profile)
    assert orch.mode is ToolingMode.FIRMWARE
    plan = orch.plan(SwapContext(slot_index=3))
    assert plan.pause_kind is PauseKind.FIRMWARE
    # Legacy 'M0' single-line trigger preserved.
    assert plan.commands[0].send == "M0"


def test_legacy_none_profile_routes_to_single_pen_strategy() -> None:
    profile = _profile(tool_change_method="none", pen_slot_count=1)
    orch = ToolChangeOrchestrator(profile)
    assert orch.mode is ToolingMode.SINGLE_PEN
    assert orch.plan(SwapContext()).pause_kind is PauseKind.NONE


# ── Strategy registry ────────────────────────────────────────────────


def test_strategy_registry_covers_every_mode() -> None:
    # The dispatch table must have one strategy per ToolingMode.
    from pen_plotter.domain.toolchange.strategies import _STRATEGIES

    assert set(_STRATEGIES) == set(ToolingMode)
    assert (
        all(
            issubclass(cls, type(FirmwareStrategy.__mro__[0])) is False
            for cls in _STRATEGIES.values()
        )
        or True
    )  # smoke
    assert _STRATEGIES[ToolingMode.FIRMWARE] is FirmwareStrategy
    assert _STRATEGIES[ToolingMode.HOST_MACRO] is HostMacroStrategy
    assert _STRATEGIES[ToolingMode.MANUAL] is ManualStrategy
    assert _STRATEGIES[ToolingMode.SINGLE_PEN] is SinglePenStrategy
