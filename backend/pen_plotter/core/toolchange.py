"""Locate guided tool-change pauses in generated G-code.

For ``manual_pause`` profiles the generator emits a ``; Change to pen slot N``
comment immediately followed by the firmware pause command (e.g. ``M0``). When
a job runs through the print queue we replace that firmware pause with a
software-guided pause: the streamer stops, the UI prompts the operator to swap
the pen, and streaming resumes on confirmation. The downloaded G-code is left
untouched (it keeps ``M0``) so it stays portable to other senders.
"""

from __future__ import annotations

import re

from pen_plotter.models import MachineProfile

_CHANGE_RE = re.compile(r"Change to pen slot (\d+) \((.*)\)\s*$")


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
            match = _CHANGE_RE.search(comment)
            if match:
                slot, name = match.group(1), match.group(2)
                pending = f"Insert pen slot {slot}: {name}"
        if not code:
            continue
        if pending is not None:
            points[exec_index] = pending
            pending = None
        exec_index += 1
    return points
