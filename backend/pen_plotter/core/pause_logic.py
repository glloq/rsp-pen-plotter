"""Single source of truth for the layer-pause decision.

Before this module existed, ``core/gcode.py`` and ``core/preflight.py``
each carried an identical 15-line predicate (``slot_changed`` /
``color_changed`` / ``first_pose`` / ``should_pause``). The
``pen_changes`` count surfaced in the preflight report HAD to match
the number of M0 prompts the streamer would later see — but the
two implementations drifted any time someone touched one and
forgot the other. Folding both call sites onto :func:`should_pause`
makes the contract enforceable.

This is intentionally limited to the standard G-code path. The EBB
generator (``core/ebb.py``) has its own pause semantics — single-pen
hardware, no slot_changed, stricter ``tool_change_method`` /
``tool_change_command`` checks — and is left alone for now.
"""

from __future__ import annotations

from dataclasses import dataclass

from pen_plotter.domain.print_plan import PausePolicy


@dataclass(frozen=True)
class PauseDecision:
    """Result of :func:`should_pause` plus the predicate flags that drove it.

    Callers can read ``pause`` alone; the per-flag fields are exposed
    so :mod:`core.gcode` can pick the right prompt template (tool
    change vs colour change) based on ``slot_changed`` without
    recomputing it.
    """

    pause: bool
    slot_changed: bool
    color_changed: bool
    first_pose: bool


def should_pause(
    *,
    slot: int | None,
    source_color: str | None,
    pause_before: PausePolicy,
    previous_slot: int | None,
    previous_color: str | None,
    mono_pen: bool,
    tool_change_method: str,
) -> PauseDecision:
    """Decide whether the engine should pause before this layer.

    Args:
        slot: The pen slot the layer targets, or ``None`` if unset.
        source_color: The source colour the layer carries (mono-pen
            colour-change tracking), or ``None``.
        pause_before: The operator's policy for this layer
            (``"auto"`` / ``"always"`` / ``"never"``).
        previous_slot: The slot used by the previous layer (``None``
            on the first layer).
        previous_color: The colour used by the previous layer
            (mono-pen only; ``None`` on the first layer).
        mono_pen: Whether the active profile has a single pen
            magazine slot.
        tool_change_method: ``profile.tool_change_method``. The pause
            is unconditionally suppressed when this is ``"none"``,
            matching the behaviour of profiles that declare they do
            not support tool changes at all.

    Returns:
        A :class:`PauseDecision` carrying both the boolean and the
        flags that justified it.
    """
    slot_changed = slot is not None and slot != previous_slot
    color_changed = (
        mono_pen and source_color is not None and source_color != previous_color
    )
    # First pose on a mono-pen machine: prompt the operator to install
    # the initial pen before drawing anything. Multi-pen profiles still
    # rely on slot_changed for the first layer (slot != None != None).
    first_pose = (
        mono_pen
        and previous_color is None
        and previous_slot is None
        and source_color is not None
    )
    pause = (
        tool_change_method != "none"
        and pause_before != "never"
        and (pause_before == "always" or slot_changed or color_changed or first_pose)
    )
    return PauseDecision(
        pause=pause,
        slot_changed=slot_changed,
        color_changed=color_changed,
        first_pose=first_pose,
    )
