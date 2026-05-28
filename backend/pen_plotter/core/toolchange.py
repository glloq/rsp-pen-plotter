"""Locate guided tool-change pauses in generated G-code.

For ``manual_pause`` profiles the generator emits a ``; Change to pen slot N``
comment immediately followed by the firmware pause command (e.g. ``M0``). When
a job runs through the print queue we replace that firmware pause with a
software-guided pause: the streamer stops, the UI prompts the operator to swap
the pen, and streaming resumes on confirmation. The downloaded G-code is left
untouched (it keeps ``M0``) so it stays portable to other senders.

Source-of-truth migration (v0.2 → v0.2 finish): the operator prompt is
now produced by the :class:`ToolChangeOrchestrator` rather than the
legacy regex-driven string template. The regex below still detects
*boundaries* (a property of the G-code text, not of the strategy) and
extracts a :class:`SwapContext`; the orchestrator's ``ManualStrategy``
formats the operator-visible string using the profile's
``manual_prompt`` block. Default templates in
:func:`pen_plotter.domain.capability.default_manual_prompt` reproduce
the legacy strings byte-for-byte for backwards compatibility.
"""

from __future__ import annotations

import re

from pen_plotter.domain.toolchange import (
    PauseKind,
    SwapContext,
    ToolChangeOrchestrator,
)
from pen_plotter.models import MachineProfile

_CHANGE_RE = re.compile(r"Change to pen slot (\d+) \((.*)\)\s*$")
# Mono-pen colour-change format emitted by ``pen_color_change.j2``.
_COLOR_RE = re.compile(r"Change pen:\s*(.+?)\s*\((#[0-9a-fA-F]{3,8})\)\s*$")


def _context_from_comment(comment: str) -> SwapContext | None:
    """Parse a G-code change comment into a :class:`SwapContext`.

    For mono-pen colour changes the ``pen_label`` field is pre-built
    to either ``"{label} ({color})"`` (when a human label exists) or
    just ``"{color}"`` (when the comment carries no label and the
    parser sees ``"#ff0000 (#ff0000)"``). That collapses the legacy
    dual prompt format into a single ``"Change pen to {label}"``
    template the orchestrator can render directly.
    """
    match = _CHANGE_RE.search(comment)
    if match:
        return SwapContext(slot_index=int(match.group(1)), pen_label=match.group(2))
    match = _COLOR_RE.search(comment)
    if match:
        label, color = match.group(1), match.group(2)
        if label.strip().lower() == color.strip().lower():
            display_label = color
        else:
            display_label = f"{label} ({color})"
        return SwapContext(pen_label=display_label, pen_color=color)
    return None


def guided_pause_points(gcode: str, profile: MachineProfile) -> dict[int, str]:
    """Map executable-line indices of firmware pause commands to operator prompts.

    Only ``manual_pause`` profiles with a non-empty tool-change command produce
    guided pauses; for everything else this returns an empty mapping.

    Args:
        gcode: The generated G-code (with comments).
        profile: The target machine profile.

    Returns:
        ``{executable_line_index: prompt}`` for each tool change. The indexed
        line is the firmware pause command, which the streamer skips in favour
        of the guided pause.
    """
    if profile.tool_change_method != "manual_pause" or not profile.tool_change_command.strip():
        return {}

    orchestrator = ToolChangeOrchestrator(profile)
    points: dict[int, str] = {}
    exec_index = 0
    pending: str | None = None
    for raw in gcode.splitlines():
        comment = raw.split(";", 1)[1].strip() if ";" in raw else ""
        code = raw.split(";", 1)[0].strip()
        if comment and pending is None:
            context = _context_from_comment(comment)
            if context is not None:
                plan = orchestrator.plan(context)
                # Only ``operator_confirm`` plans produce a prompt we
                # store on the run; the streamer doesn't yet act on
                # the other ``SwapCommand[]`` plans (see TODO 2.3 in
                # docs/TODO.md for the streamer inline-command refactor).
                if plan.pause_kind is PauseKind.OPERATOR_CONFIRM and plan.operator_prompt:
                    pending = plan.operator_prompt
        if not code:
            continue
        if pending is not None:
            points[exec_index] = pending
            pending = None
        exec_index += 1
    return points
