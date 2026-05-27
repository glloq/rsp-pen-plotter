"""Tests for the recovery decision layer + pause/swap/resume end-to-end (B.3)."""

from __future__ import annotations

import pytest

from pen_plotter.core.resume import build_resume_program
from pen_plotter.domain.capability import RecoveryPolicy
from pen_plotter.domain.recovery import (
    Directive,
    FailureKind,
    JobRecoveryOverride,
    effective_policy,
    resolve_recovery,
)
from pen_plotter.domain.toolchange import (
    SwapContext,
    ToolChangeOrchestrator,
)
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


# ── effective_policy precedence ──────────────────────────────────────


def test_effective_policy_falls_back_to_profile_when_no_override() -> None:
    eff = effective_policy(
        RecoveryPolicy.PAUSE_AND_PROMPT, None, FailureKind.SWAP_TIMEOUT
    )
    assert eff is RecoveryPolicy.PAUSE_AND_PROMPT


def test_effective_policy_uses_job_wide_override() -> None:
    eff = effective_policy(
        RecoveryPolicy.PAUSE_AND_PROMPT,
        JobRecoveryOverride(policy=RecoveryPolicy.ABORT),
        FailureKind.SWAP_TIMEOUT,
    )
    assert eff is RecoveryPolicy.ABORT


def test_per_failure_override_beats_job_wide_override() -> None:
    eff = effective_policy(
        RecoveryPolicy.PAUSE_AND_PROMPT,
        JobRecoveryOverride(
            policy=RecoveryPolicy.ABORT,
            per_failure={FailureKind.COMMAND_REJECTED: RecoveryPolicy.SKIP_LAYER},
        ),
        FailureKind.COMMAND_REJECTED,
    )
    assert eff is RecoveryPolicy.SKIP_LAYER


def test_per_failure_override_only_applies_to_its_failure_kind() -> None:
    override = JobRecoveryOverride(
        per_failure={FailureKind.COMMAND_REJECTED: RecoveryPolicy.SKIP_LAYER}
    )
    # Same override, different failure → still profile.
    assert (
        effective_policy(RecoveryPolicy.PAUSE_AND_PROMPT, override, FailureKind.SWAP_TIMEOUT)
        is RecoveryPolicy.PAUSE_AND_PROMPT
    )


# ── resolve_recovery directive table ─────────────────────────────────


@pytest.mark.parametrize(
    "policy,failure,expected",
    [
        (RecoveryPolicy.ABORT, FailureKind.SWAP_TIMEOUT, Directive.ABORT_RUN),
        (RecoveryPolicy.ABORT, FailureKind.DEVICE_DISCONNECT, Directive.ABORT_RUN),
        (RecoveryPolicy.ABORT, FailureKind.COMMAND_REJECTED, Directive.ABORT_RUN),
        (RecoveryPolicy.ABORT, FailureKind.OPERATOR_ABORT, Directive.ABORT_RUN),
        (
            RecoveryPolicy.PAUSE_AND_PROMPT,
            FailureKind.SWAP_TIMEOUT,
            Directive.WAIT_FOR_OPERATOR,
        ),
        (
            RecoveryPolicy.PAUSE_AND_PROMPT,
            FailureKind.COMMAND_REJECTED,
            Directive.WAIT_FOR_OPERATOR,
        ),
        (
            RecoveryPolicy.PAUSE_AND_PROMPT,
            FailureKind.DEVICE_DISCONNECT,
            Directive.ABORT_RUN,
        ),
        (
            RecoveryPolicy.PAUSE_AND_PROMPT,
            FailureKind.OPERATOR_ABORT,
            Directive.ABORT_RUN,
        ),
        (
            RecoveryPolicy.SKIP_LAYER,
            FailureKind.SWAP_TIMEOUT,
            Directive.SKIP_AND_CONTINUE,
        ),
        (
            RecoveryPolicy.SKIP_LAYER,
            FailureKind.COMMAND_REJECTED,
            Directive.SKIP_AND_CONTINUE,
        ),
        (
            RecoveryPolicy.SKIP_LAYER,
            FailureKind.DEVICE_DISCONNECT,
            Directive.ABORT_RUN,
        ),
        (
            RecoveryPolicy.SKIP_LAYER,
            FailureKind.OPERATOR_ABORT,
            Directive.ABORT_RUN,
        ),
    ],
)
def test_resolve_recovery_table(
    policy: RecoveryPolicy, failure: FailureKind, expected: Directive
) -> None:
    decision = resolve_recovery(policy, None, failure)
    assert decision.directive is expected
    assert decision.effective_policy is policy
    assert decision.failure_kind is failure
    assert decision.reason


def test_resolve_recovery_honours_job_override() -> None:
    decision = resolve_recovery(
        RecoveryPolicy.ABORT,
        JobRecoveryOverride(policy=RecoveryPolicy.PAUSE_AND_PROMPT),
        FailureKind.SWAP_TIMEOUT,
    )
    assert decision.directive is Directive.WAIT_FOR_OPERATOR
    assert decision.effective_policy is RecoveryPolicy.PAUSE_AND_PROMPT


def test_unknown_failure_always_aborts() -> None:
    for policy in RecoveryPolicy:
        assert (
            resolve_recovery(policy, None, FailureKind.UNKNOWN).directive
            is Directive.ABORT_RUN
        )


# ── End-to-end: pause -> swap -> resume preserves state ──────────────


_GCODE_FOR_RESUME = """\
G21
G90
G0 X10 Y10
G1 X20 Y10
G1 X20 Y20
; Change to pen slot 2 (Cyan)
M0
G1 X30 Y20
G1 X30 Y30
"""


def test_pause_swap_resume_preserves_position_and_units() -> None:
    profile = _profile()
    # Pretend we acked 3 executable lines (G21, G90, G0 X10 Y10).
    program = build_resume_program(_GCODE_FOR_RESUME, acked_lines=3, profile=profile)
    # The resume preamble must reassert G21 (units) and travel back to
    # the last known head position before the user-supplied commands.
    assert program[0] == "G21"
    assert any("X10" in line and "Y10" in line for line in program[1:5])
    # And the remainder still contains the swap marker + drawing.
    assert "M0" in program
    assert any("X30" in line for line in program)


def test_pause_swap_resume_uses_orchestrator_for_prompt() -> None:
    # The operator-facing prompt that the queue would show on this swap
    # must come from the orchestrator (not the legacy M0 substitution).
    profile = _profile()
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(
        SwapContext(slot_index=2, pen_label="Cyan", pen_color="#00ffff", layer_id="l1")
    )
    assert plan.operator_prompt is not None
    assert "Cyan" in plan.operator_prompt or "#00ffff" in plan.operator_prompt


def test_resume_from_zero_returns_full_program() -> None:
    profile = _profile()
    program = build_resume_program(_GCODE_FOR_RESUME, acked_lines=0, profile=profile)
    # No re-init prefix because checkpoint=0.
    assert program[0] == "G21"


def test_resume_past_end_returns_empty() -> None:
    profile = _profile()
    program = build_resume_program(_GCODE_FOR_RESUME, acked_lines=999, profile=profile)
    assert program == []


# ── Defensive: every (policy, failure) combination has a directive ───


def test_table_is_total() -> None:
    for policy in RecoveryPolicy:
        for failure in FailureKind:
            decision = resolve_recovery(policy, None, failure)
            assert decision.directive in {
                Directive.ABORT_RUN,
                Directive.WAIT_FOR_OPERATOR,
                Directive.SKIP_AND_CONTINUE,
            }
