"""Locate guided tool-change pauses in generated G-code.

For ``manual_pause`` profiles the generator emits a ``; Change to pen slot N``
comment immediately followed by the firmware pause command (e.g. ``M0``). When
a job runs through the print queue we replace that firmware pause with a
software-guided pause: the streamer stops, the UI prompts the operator to swap
the pen, and streaming resumes on confirmation. The downloaded G-code is left
untouched (it keeps ``M0``) so it stays portable to other senders.

Migration note (E.3 wire): the v0.2 ``ToolChangeOrchestrator`` is the
forward-looking source of truth for swap prompts (it composes mode +
manual_prompt template + placeholder substitution). The legacy regex
format used by these prompts predates the orchestrator's template, so
swapping it in here would break golden-text contracts. The orchestrator
remains the path the streamer takes for **non-operator-confirm** swaps
(firmware / host_macro / single_pen via the future inline-command
streamer integration); the manual-pause prompt rendering migrates once
the legacy profiles' ``manual_prompt`` templates are aligned with the
``Insert pen slot N: Label`` format these regexes still match.
"""

from __future__ import annotations

import re

from pen_plotter.models import MachineProfile

_CHANGE_RE = re.compile(r"Change to pen slot (\d+) \((.*)\)\s*$")
# Mono-pen colour-change format emitted by ``pen_color_change.j2``. Kept as a
# separate regex from ``_CHANGE_RE`` so older G-code in the persisted queue
# (slot-based prompts) keeps deserialising correctly after the upgrade.
_COLOR_RE = re.compile(r"Change pen:\s*(.+?)\s*\((#[0-9a-fA-F]{3,8})\)\s*$")


def _prompt(comment: str) -> str | None:
    """Return the operator prompt for a recognised tool-change comment, or None."""
    match = _CHANGE_RE.search(comment)
    if match:
        slot, name = match.group(1), match.group(2)
        return f"Insert pen slot {slot}: {name}"
    match = _COLOR_RE.search(comment)
    if match:
        label, color = match.group(1), match.group(2)
        # If the label is identical to the hex (no human label was provided),
        # show the hex only — avoids "Change pen to #ff0000 (#ff0000)".
        if label.strip().lower() == color.strip().lower():
            return f"Change pen to {color}"
        return f"Change pen to {label} ({color})"
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

    points: dict[int, str] = {}
    exec_index = 0
    pending: str | None = None
    for raw in gcode.splitlines():
        comment = raw.split(";", 1)[1].strip() if ";" in raw else ""
        code = raw.split(";", 1)[0].strip()
        if comment and pending is None:
            prompt = _prompt(comment)
            if prompt is not None:
                pending = prompt
        if not code:
            continue
        if pending is not None:
            points[exec_index] = pending
            pending = None
        exec_index += 1
    return points
