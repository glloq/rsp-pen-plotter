"""Unit tests for the shared pause-decision predicate.

Lives at the bottom of the dependency tree (pure function over
primitives) so the decision matrix can be pinned without spinning up
SVG geometry or template engines.

The contract this module enforces: every code path that asks "should
we emit a pause before this layer?" must reach the same conclusion.
core/gcode.py renders the pause command; core/preflight.py counts it
for the operator's pre-flight report. They MUST agree.
"""

from __future__ import annotations

import pytest

from pen_plotter.core.pause_logic import should_pause


def _decide(**overrides: object):
    """Helper: defaults to the common "no pause" baseline."""
    base: dict[str, object] = {
        "slot": None,
        "source_color": None,
        "pause_before": "auto",
        "previous_slot": None,
        "previous_color": None,
        "mono_pen": False,
        "tool_change_method": "manual_pause",
    }
    base.update(overrides)
    return should_pause(**base)  # type: ignore[arg-type]


def test_no_pause_when_nothing_changed() -> None:
    """Auto policy + unchanged slot + multi-pen ⇒ no pause."""
    decision = _decide(slot=1, previous_slot=1)
    assert decision.pause is False
    assert decision.slot_changed is False


def test_pause_when_slot_changed_under_auto() -> None:
    decision = _decide(slot=2, previous_slot=1)
    assert decision.pause is True
    assert decision.slot_changed is True


def test_no_pause_when_slot_changes_but_policy_is_never() -> None:
    """``never`` overrides every other signal — the operator wants no stops."""
    decision = _decide(slot=2, previous_slot=1, pause_before="never")
    assert decision.pause is False


def test_pause_when_policy_is_always_even_without_slot_change() -> None:
    """``always`` forces a pause every layer, even when slot is unchanged."""
    decision = _decide(slot=1, previous_slot=1, pause_before="always")
    assert decision.pause is True


def test_no_pause_when_tool_change_method_is_none() -> None:
    """Profiles that declare ``none`` cannot pause, regardless of the policy."""
    for policy in ("auto", "always", "never"):
        decision = _decide(
            slot=2, previous_slot=1, pause_before=policy, tool_change_method="none"
        )
        assert decision.pause is False, policy


def test_mono_pen_first_pose_triggers_pause() -> None:
    """First layer on a mono-pen machine prompts the operator to install the pen."""
    decision = _decide(source_color="#ff0000", mono_pen=True)
    assert decision.pause is True
    assert decision.first_pose is True
    assert decision.color_changed is True  # baseline previous_color=None


def test_mono_pen_color_change_triggers_pause() -> None:
    decision = _decide(
        source_color="#0000ff", previous_color="#ff0000", mono_pen=True
    )
    assert decision.pause is True
    assert decision.color_changed is True


def test_mono_pen_same_color_does_not_pause() -> None:
    decision = _decide(
        source_color="#ff0000", previous_color="#ff0000", mono_pen=True
    )
    assert decision.pause is False
    assert decision.color_changed is False


def test_multi_pen_ignores_color_change() -> None:
    """Multi-pen machines pause on slot, not on colour."""
    decision = _decide(
        slot=1,
        previous_slot=1,
        source_color="#0000ff",
        previous_color="#ff0000",
        mono_pen=False,
    )
    assert decision.pause is False
    assert decision.color_changed is False


def test_first_layer_on_multi_pen_with_slot_pauses() -> None:
    """Slot 0 + previous=None counts as slot_changed for the very first layer."""
    decision = _decide(slot=0, previous_slot=None)
    assert decision.pause is True
    assert decision.slot_changed is True


def test_decision_carries_individual_flags_for_caller_branching() -> None:
    """gcode.py picks the prompt template based on ``slot_changed`` —
    expose it so the caller doesn't recompute it.
    """
    decision = _decide(slot=2, previous_slot=1, source_color="#abc", mono_pen=True)
    assert decision.slot_changed is True
    # Mono-pen colour-change is also tracked; the caller decides which
    # prompt to surface (tool change wins because the slot changed).
    assert decision.color_changed is True


@pytest.mark.parametrize(
    "policy,expected", [("auto", False), ("never", False), ("always", True)]
)
def test_always_policy_pauses_even_when_nothing_changed(policy: str, expected: bool) -> None:
    decision = _decide(slot=1, previous_slot=1, pause_before=policy)
    assert decision.pause is expected
