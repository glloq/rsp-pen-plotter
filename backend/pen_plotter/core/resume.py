"""Rebuild a G-code program so a job can resume after an interruption.

Streaming records how many executable lines were acknowledged. To resume from
that checkpoint safely we cannot simply continue mid-stream: G-code is modal, so
units, absolute/relative mode, the head position and the pen state must be
re-established first. This module replays the executed prefix to recover that
modal state, then emits a small preamble (restore units/positioning, lift the
pen, travel back to the last position, re-lower the pen if the checkpoint fell
mid-stroke) followed by the remaining lines.

Two limits worth stating plainly:

* **Checkpoint granularity.** The streamer persists a checkpoint at most every
  ~50 acknowledged lines / 2 s (plus on every pause / swap / error boundary),
  so an unclean stop can lose up to that many lines — resume replays from the
  last *checkpoint*, not the last physical stroke, and may retrace a short
  already-drawn section. Callers should describe resume as "from the last
  checkpoint", never "from the exact interruption point". A firmware ``ok`` is
  *accepted*, not *executed*, so after a power loss the head can sit several
  buffered moves behind the checkpoint. ``OMNIPLOT_RESUME_CONSERVATIVE=1``
  rewinds the resume point to the last pen-up boundary so those unexecuted
  moves are re-drawn rather than skipped (a little over-draw instead of a gap);
  it is opt-in because it changes the default no-over-draw behaviour, and the
  fully robust fix (checkpoint only on ``M400`` / ``Idle`` confirmation) needs
  per-firmware validation on real hardware.
* **EBB is partial.** This reconstruction reads absolute X/Y from the executed
  prefix. An EBB program is a stream of *relative* ``SM`` step moves with no
  absolute coordinates, so the head position cannot be recovered this way;
  resuming an interrupted EBB job may misregister and should be treated as
  best-effort until a native EBB resume path exists.
"""

from __future__ import annotations

import os
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
    # Pen-up command for the *currently loaded* pen — the calibrated up line of
    # whichever pen the last pen-down belonged to. The resume preamble lifts
    # the pen with this before travelling back, so a per-slot ``pen_up_command``
    # override isn't clobbered by the profile default. ``None`` ⇒ no pen seen
    # yet, fall back to the profile default.
    active_pen_up_line: str | None = None


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


def _pen_up_by_down(profile: MachineProfile) -> dict[str, str]:
    """Map each pen's effective pen-down line to its effective pen-up line.

    The executed prefix has no tool-change comments (they're stripped), so the
    only in-band signal of which pen is loaded is the pen-down command itself.
    A per-slot calibration that overrides ``pen_down_command`` yields a unique
    down line, letting the resume replay recover *that* pen's ``pen_up_command``
    rather than lifting with the profile default.
    """
    mapping: dict[str, str] = {}
    for pen in profile.effective_pens():
        down = (pen.pen_down_command or profile.pen_down_command).strip()
        up = (pen.pen_up_command or profile.pen_up_command).strip()
        if down and up:
            mapping.setdefault(down, up)
    return mapping


# Draw/travel moves whose X/Y words define the head's new position. Arcs
# (G2/G3) end at their X/Y just like a line, so their endpoint must advance the
# replayed position — omitting them left the checkpoint position stuck before
# the last arc and could send the head back to the wrong point on resume (P0.4).
_MOVE_CODES = ("G0", "G1", "G2", "G3", "G00", "G01", "G02", "G03")


def _replay(
    lines: list[str],
    pen_ups: set[str],
    pen_downs: set[str],
    pen_up_by_down: dict[str, str],
) -> _ModalState:
    """Recover modal state by scanning already-executed command lines."""
    state = _ModalState()
    for line in lines:
        if line in pen_downs:
            state.pen_down_line = line
            # Remember the loaded pen's up line so travel lifts correctly.
            state.active_pen_up_line = pen_up_by_down.get(line, state.active_pen_up_line)
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
        if code not in _MOVE_CODES:
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


def _resume_conservative() -> bool:
    """Whether to rewind the resume point to the last pen-up boundary (P0.3)."""
    return (os.environ.get("OMNIPLOT_RESUME_CONSERVATIVE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _rewind_to_pen_up(lines: list[str], checkpoint: int, pen_ups: set[str]) -> int:
    """Index of the last pen-up command at or before ``checkpoint`` (else 0).

    A firmware ``ok`` means *accepted*, not *executed*: on power loss the head
    may sit several buffered moves behind the checkpoint. Restarting from the
    last point where the pen was UP re-draws the interrupted stroke instead of
    skipping the moves that were acknowledged but never physically drawn —
    trading a little over-draw (harmless on a pen plot) for never leaving a gap.
    """
    for i in range(checkpoint - 1, -1, -1):
        if lines[i] in pen_ups:
            return i
    return 0


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

    With ``OMNIPLOT_RESUME_CONSERVATIVE=1`` the resume point is rewound to the
    last pen-up boundary at or before the checkpoint, so an acknowledged-but-
    unexecuted move at power-loss is re-drawn rather than skipped (P0.3).
    """
    lines = executable_lines(gcode)
    checkpoint = max(0, min(acked_lines, len(lines)))
    if checkpoint == 0 or checkpoint >= len(lines):
        # Past the end → nothing to resume; at the start → full program.
        return [] if checkpoint >= len(lines) and checkpoint else lines

    pen_ups, pen_downs = _pen_command_sets(profile)
    if _resume_conservative():
        checkpoint = _rewind_to_pen_up(lines, checkpoint, pen_ups)
        if checkpoint == 0:
            return lines  # rewound all the way back → replot from the start
    remainder = lines[checkpoint:]
    pen_up_by_down = _pen_up_by_down(profile)
    state = _replay(lines[:checkpoint], pen_ups, pen_downs, pen_up_by_down)
    preamble: list[str] = []
    if state.units:
        preamble.append(state.units)
    if state.x is not None and state.y is not None:
        # goto_command asserts G90, lifts the pen, and travels to the position.
        # Lift with the loaded pen's own up command so a per-slot override is
        # honoured — otherwise the pen may not actually clear the paper on the
        # travel back to the checkpoint (P0.4).
        preamble.extend(
            goto_command(
                state.x,
                state.y,
                profile,
                pen_up_command=state.active_pen_up_line,
            )
        )
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
