"""Single source of truth for the layer-pause decision.

Before this module existed, ``core/gcode.py`` and ``core/preflight.py``
each carried an identical 15-line predicate (``slot_changed`` /
``color_changed`` / ``first_pose`` / ``should_pause``). The
``pen_changes`` count surfaced in the preflight report HAD to match
the number of M0 prompts the streamer would later see — but the
two implementations drifted any time someone touched one and
forgot the other. Folding both call sites onto :func:`should_pause`
makes the contract enforceable.

The EBB generator (``core/ebb.py``) has its own pause semantics —
single-pen hardware, no ``slot_changed``, stricter requirements on
``tool_change_method`` and ``tool_change_command``. It now consumes
:func:`should_pause_ebb` in this module so the colour-change /
first-pose predicates are shared with the G-code path even though
the surrounding decision rule stays specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pen_plotter.domain.print_plan import PausePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pen_plotter.models import PenSlot


def installed_pen_hex_slots(pens: Mapping[int, PenSlot]) -> dict[str, int]:
    """Map lower-cased installed-pen hex → magazine slot index.

    Lower-cased lookup so case differences across the inventory ↔
    profile YAML don't miss matches. The first slot wins when two
    installed pens carry the same hex.
    """
    mapping: dict[str, int] = {}
    for pen_index, slot_pen in pens.items():
        if slot_pen.installed and slot_pen.color:
            mapping.setdefault(slot_pen.color.lower(), pen_index)
    return mapping


def effective_layer_pen(
    *,
    slot: int | None,
    source_color: str | None,
    assigned_color_hex: str | None,
    pen_hex_to_slot: Mapping[str, int],
) -> tuple[int | None, str | None]:
    """Promote a layer's raw plan values to the effective slot / colour.

    L7: when the operator picked an assigned colour AND it matches an
    installed pen by hex, the prompt is promoted to a proper
    tool-change with the magazine slot. Without a matching pen the
    assigned hex still replaces the raw source colour so the mono-pen
    swap prompt names the ink the operator actually picked.

    Both :func:`pen_plotter.core.gcode.generate_gcode` and
    :func:`pen_plotter.core.preflight.preflight_report` MUST feed
    :func:`should_pause` these promoted values — otherwise the
    preflight ``pen_changes`` count drifts from the number of M0
    prompts the generated program actually contains.

    Returns:
        ``(effective_slot, effective_color)``.
    """
    promoted_slot: int | None = None
    if assigned_color_hex and slot is None:
        promoted_slot = pen_hex_to_slot.get(assigned_color_hex.lower())
    effective_slot = slot if slot is not None else promoted_slot
    effective_color = assigned_color_hex or source_color
    return effective_slot, effective_color


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
    color_changed = mono_pen and source_color is not None and source_color != previous_color
    # First pose on a mono-pen machine: prompt the operator to install
    # the initial pen before drawing anything. Multi-pen profiles still
    # rely on slot_changed for the first layer (slot != None != None).
    first_pose = (
        mono_pen and previous_color is None and previous_slot is None and source_color is not None
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


def should_pause_ebb(
    *,
    source_color: str | None,
    pause_before: PausePolicy,
    previous_color: str | None,
    tool_change_method: str,
    tool_change_command: str,
) -> PauseDecision:
    """EBB-specific variant of :func:`should_pause`.

    EBB plotters (AxiDraw-class) have a single physical pen, so the
    pause decision tracks **colour changes** (the operator swaps the
    ink mid-print) instead of slot changes. The hardware requirements
    are stricter too:

    - ``tool_change_method`` must be exactly ``"manual_pause"`` (the
      board has no carousel / rack notion to enable an automated swap)
    - ``tool_change_command`` must be a non-empty string (the streamer
      uses it as the line to intercept and gate)

    Returns the same :class:`PauseDecision` shape as :func:`should_pause`
    so callers can share downstream code; ``slot_changed`` is always
    ``False`` on this path since EBB has no slot concept.
    """
    color_changed = source_color is not None and source_color != previous_color
    first_pose = previous_color is None and source_color is not None
    pause = (
        tool_change_method == "manual_pause"
        and bool(tool_change_command.strip())
        and pause_before != "never"
        and (pause_before == "always" or color_changed or first_pose)
    )
    return PauseDecision(
        pause=pause,
        slot_changed=False,
        color_changed=color_changed,
        first_pose=first_pose,
    )
