"""Rebuild a G-code program so a job can resume after an interruption.

Streaming records how many executable lines were acknowledged. To resume from
that checkpoint safely we cannot simply continue mid-stream: G-code is modal, so
units, absolute/relative mode and the head position must be re-established
first. This module replays the executed prefix to recover that modal state, then
emits a small preamble (restore units/positioning, lift the pen, travel back to
the last position) followed by the remaining lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from pen_plotter.hardware.commands import goto_command
from pen_plotter.hardware.streamer import executable_lines
from pen_plotter.models import MachineProfile


@dataclass
class _ModalState:
    """Modal G-code state recovered from an executed prefix."""

    x: float | None = None
    y: float | None = None
    units: str | None = None  # "G20" or "G21"
    absolute: bool = True


def _coord(token: str) -> float | None:
    try:
        return float(token[1:])
    except ValueError:
        return None


def _replay(lines: list[str]) -> _ModalState:
    """Recover modal state by scanning already-executed command lines."""
    state = _ModalState()
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        code = tokens[0]
        if code in ("G20", "G21"):
            state.units = code
            continue
        if code == "G90":
            state.absolute = True
            continue
        if code == "G91":
            state.absolute = False
            continue
        if code not in ("G0", "G1", "G00", "G01"):
            continue
        for token in tokens[1:]:
            if token[:1] == "X":
                value = _coord(token)
                if value is not None:
                    state.x = value if state.absolute else (state.x or 0.0) + value
            elif token[:1] == "Y":
                value = _coord(token)
                if value is not None:
                    state.y = value if state.absolute else (state.y or 0.0) + value
    return state


def build_resume_program(gcode: str, acked_lines: int, profile: MachineProfile) -> list[str]:
    """Build the executable line list needed to resume a job from a checkpoint.

    Args:
        gcode: The full original G-code program.
        acked_lines: Number of executable lines already acknowledged.
        profile: Target machine profile (for pen-up and travel speed).

    Returns:
        Executable command lines: a re-initialization preamble followed by the
        not-yet-sent lines. Resuming from the start returns the full program
        unchanged; resuming past the end returns an empty list.
    """
    lines = executable_lines(gcode)
    checkpoint = max(0, min(acked_lines, len(lines)))
    remainder = lines[checkpoint:]
    if checkpoint == 0 or not remainder:
        return remainder if checkpoint else lines

    state = _replay(lines[:checkpoint])
    preamble: list[str] = []
    if state.units:
        preamble.append(state.units)
    if state.x is not None and state.y is not None:
        # goto_command asserts G90, lifts the pen, and travels to the position.
        preamble.extend(goto_command(state.x, state.y, profile))
    else:
        preamble.append("G90")
    if not state.absolute:
        preamble.append("G91")
    return preamble + remainder
