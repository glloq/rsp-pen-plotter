"""Rebuild a G-code program so a job can resume after an interruption.

Streaming records how many executable lines were acknowledged. To resume from
that checkpoint safely we cannot simply continue mid-stream: G-code is modal, so
units, absolute/relative mode, the head position and the pen state must be
re-established first. This module replays the executed prefix to recover that
modal state, then emits a small preamble (restore units/positioning, lift the
pen, travel back to the last position, re-lower the pen if the checkpoint fell
mid-stroke) followed by the remaining lines.
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
    # The pen-down command last seen, verbatim, when the pen was left DOWN
    # at the checkpoint — ``None`` when the pen is up (or no pen command
    # appeared in the prefix). Kept as the exact line so a per-slot
    # calibration override (``PenSlot.pen_down_command``) is replayed
    # unchanged instead of being replaced by the profile default.
    pen_down_line: str | None = None


def _coord(token: str) -> float | None:
    try:
        return float(token[1:])
    except ValueError:
        return None


def _pen_command_sets(profile: MachineProfile) -> tuple[set[str], set[str]]:
    """Return ``(pen_up_lines, pen_down_lines)`` the profile can emit.

    Generated programs write the profile's ``pen_up_command`` /
    ``pen_down_command`` verbatim, or a per-slot override when the pen's
    calibration sets one — collect them all so the replay recognises
    every variant.
    """
    ups = {profile.pen_up_command.strip()}
    downs = {profile.pen_down_command.strip()}
    for pen in profile.effective_pens():
        if pen.pen_up_command:
            ups.add(pen.pen_up_command.strip())
        if pen.pen_down_command:
            downs.add(pen.pen_down_command.strip())
    ups.discard("")
    downs.discard("")
    return ups, downs


def _replay(lines: list[str], pen_ups: set[str], pen_downs: set[str]) -> _ModalState:
    """Recover modal state by scanning already-executed command lines."""
    state = _ModalState()
    for line in lines:
        if line in pen_downs:
            state.pen_down_line = line
            continue
        if line in pen_ups:
            state.pen_down_line = None
            continue
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


def _starts_with_draw_move(remainder: list[str]) -> bool:
    """Whether the first remaining line is a drawing move (G1/G2/G3).

    Generated programs travel with G0 and draw with G1/G2/G3, so a
    remainder opening on a draw move means the checkpoint fell
    mid-stroke. When it opens on anything else (a pen-up, a travel, a
    tool change) the program re-establishes its own pen state and
    re-lowering the pen first would only stamp a stray dot at the
    resume point.
    """
    if not remainder:
        return False
    code = remainder[0].split()[0] if remainder[0].split() else ""
    return code in ("G1", "G01", "G2", "G02", "G3", "G03")


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

    pen_ups, pen_downs = _pen_command_sets(profile)
    state = _replay(lines[:checkpoint], pen_ups, pen_downs)
    preamble: list[str] = []
    if state.units:
        preamble.append(state.units)
    if state.x is not None and state.y is not None:
        # goto_command asserts G90, lifts the pen, and travels to the position.
        preamble.extend(goto_command(state.x, state.y, profile))
        # The checkpoint fell mid-stroke (pen was down, the next line keeps
        # drawing): re-lower the pen so the rest of the interrupted path is
        # actually inked instead of being air-drawn until the next pen-down.
        if state.pen_down_line is not None and _starts_with_draw_move(remainder):
            preamble.append(state.pen_down_line)
    else:
        preamble.append("G90")
    if not state.absolute:
        preamble.append("G91")
    return preamble + remainder
