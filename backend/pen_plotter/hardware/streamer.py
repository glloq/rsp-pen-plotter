"""G-code streaming with acknowledgment-based flow control.

Sends one line at a time and waits for the controller's ``ok`` before sending
the next, the standard handshake for GRBL/Marlin-class firmware. Supports
pause, resume, and abort, and reports progress through an optional async
callback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from pen_plotter.hardware.transport import Transport


class SwapCommandLine(BaseModel):
    """One inline command emitted at a tool-change boundary.

    Mirrors :class:`pen_plotter.domain.toolchange.SwapCommand` but with
    the streamer's wire shape — plain strings + a millisecond dwell.
    The streamer writes the line to the transport, awaits the ``ok``
    from the controller, then sleeps ``wait_ms`` before the next.
    """

    send: str
    wait_ms: int = Field(default=0, ge=0)


class SwapAction(BaseModel):
    """What the streamer should do at one tool-change boundary.

    Stored on :class:`PrintRun` as JSON so a queued run survives a
    restart with its swap plan intact. The streamer reads
    ``swap_actions`` at runtime and dispatches per ``kind``:

    - ``operator_confirm``: halt, show ``prompt``, wait for resume
      (legacy behaviour from ``pause_points``).
    - ``firmware``: emit each ``commands`` line and await its ack
      just like a normal G-code line — the firmware handles the
      physical swap.
    - ``host_timed``: emit each line, await ack, then sleep
      ``wait_ms`` before the next (host-driven rack macros).
    - ``none``: emit the lines inline without halting; useful for
      single-pen profiles that still want some inline marker.
    """

    kind: Literal["operator_confirm", "firmware", "host_timed", "none"]
    prompt: str | None = None
    commands: list[SwapCommandLine] = Field(default_factory=list)


class StreamState(StrEnum):
    """Lifecycle states of a streaming run."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    DONE = "done"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class StreamProgress:
    """A snapshot of streaming progress."""

    total: int
    sent: int
    acked: int
    state: StreamState
    message: str | None = None


class StreamError(Exception):
    """Raised when the controller reports an error during streaming."""


ProgressCallback = Callable[[StreamProgress], Awaitable[None]]


def executable_lines(gcode: str) -> list[str]:
    """Strip comments and blanks, returning only sendable command lines.

    Args:
        gcode: Raw G-code text.

    Returns:
        One cleaned command per list entry, in order.
    """
    lines: list[str] = []
    for raw in gcode.splitlines():
        line = raw.split(";", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


class GcodeStreamer:
    """Streams G-code to a transport with ``ok``-acknowledged flow control."""

    def __init__(
        self,
        transport: Transport,
        on_progress: ProgressCallback | None = None,
        ack_timeout_s: float = 30.0,
        pause_points: dict[int, str] | None = None,
        swap_actions: dict[int, SwapAction] | None = None,
    ) -> None:
        """Create a streamer.

        Args:
            transport: The link to the controller.
            on_progress: Optional async callback invoked after each acknowledgment
                and on state changes.
            ack_timeout_s: Maximum time to wait for an ``ok`` before failing,
                guarding against a stalled or disconnected controller.
            pause_points: Optional ``{executable_line_index: prompt}`` mapping.
                When streaming reaches such a line it is skipped and the stream
                enters ``WAITING`` until resumed. **Legacy** — kept for
                backward compatibility with queued runs that predate the
                ``swap_actions`` plumbing. When both are supplied,
                ``swap_actions`` wins for matching indices.
            swap_actions: Optional ``{executable_line_index: SwapAction}``
                mapping. Richer than ``pause_points`` — supports
                operator-confirm prompts AND inline firmware / host_macro
                command sequences. Produced by
                :func:`pen_plotter.core.toolchange.guided_swap_actions`.
        """
        self._transport = transport
        self._on_progress = on_progress
        self._ack_timeout_s = ack_timeout_s
        self._pause_points = pause_points or {}
        self._swap_actions = swap_actions or {}
        self._resume = asyncio.Event()
        self._resume.set()
        self._aborted = False
        self.progress = StreamProgress(total=0, sent=0, acked=0, state=StreamState.IDLE)

    def pause(self) -> None:
        """Pause after the current line is acknowledged."""
        self._resume.clear()
        if self.progress.state == StreamState.RUNNING:
            self.progress.state = StreamState.PAUSED

    def resume(self) -> None:
        """Resume a paused stream."""
        if self.progress.state == StreamState.PAUSED:
            self.progress.state = StreamState.RUNNING
        self._resume.set()

    def abort(self) -> None:
        """Abort the stream as soon as possible."""
        self._aborted = True
        self._resume.set()

    async def _emit(self) -> None:
        """Invoke the progress callback if one is registered."""
        if self._on_progress is not None:
            await self._on_progress(self.progress)

    async def _wait_ok(self) -> None:
        """Read responses until an ``ok`` is seen, raising on error or timeout.

        Raises:
            StreamError: If the controller reports an ``error``/``alarm`` or
                fails to acknowledge within ``ack_timeout_s``.
        """
        while True:
            try:
                response = (
                    await asyncio.wait_for(self._transport.read_line(), self._ack_timeout_s)
                ).lower()
            except TimeoutError as exc:
                raise StreamError(f"No acknowledgment within {self._ack_timeout_s}s") from exc
            if response.startswith("ok"):
                return
            if response.startswith(("error", "alarm", "!!")):
                raise StreamError(response)

    async def run(self, gcode: str) -> StreamProgress:
        """Stream a G-code program to completion.

        Args:
            gcode: Raw G-code text.

        Returns:
            The final :class:`StreamProgress`.

        Raises:
            StreamError: If the controller reports an error (state set to ERROR).
        """
        commands = executable_lines(gcode)
        self.progress = StreamProgress(
            total=len(commands), sent=0, acked=0, state=StreamState.RUNNING
        )
        await self._emit()

        for index, command in enumerate(commands):
            await self._resume.wait()
            if self._aborted:
                self.progress.state = StreamState.ABORTED
                await self._emit()
                return self.progress

            # New-style swap action takes precedence over the legacy
            # ``pause_points`` map for the same line index. Legacy
            # ``pause_points`` are translated on the fly to an
            # operator-confirm action.
            action = self._swap_actions.get(index)
            if action is None and index in self._pause_points:
                action = SwapAction(
                    kind="operator_confirm", prompt=self._pause_points[index]
                )
            if action is not None:
                aborted = await self._handle_swap(action)
                if aborted:
                    self.progress.state = StreamState.ABORTED
                    await self._emit()
                    return self.progress
                # The firmware-pause command on this line is replaced
                # by the swap action itself: skip it, count it as
                # delivered so the line counter stays consistent.
                self.progress.sent += 1
                self.progress.acked += 1
                await self._emit()
                continue

            await self._transport.write_line(command)
            self.progress.sent += 1
            try:
                await self._wait_ok()
            except StreamError:
                self.progress.state = StreamState.ERROR
                await self._emit()
                raise
            self.progress.acked += 1
            await self._emit()

        self.progress.state = StreamState.DONE
        await self._emit()
        return self.progress

    async def _handle_swap(self, action: SwapAction) -> bool:
        """Execute a :class:`SwapAction` at a tool-change boundary.

        Returns ``True`` when the action was aborted mid-execution, so
        the caller can short-circuit to the ABORTED state and emit a
        final progress snapshot.
        """
        if action.kind == "operator_confirm":
            self.progress.state = StreamState.WAITING
            self.progress.message = action.prompt
            self._resume.clear()
            await self._emit()
            await self._resume.wait()
            if self._aborted:
                return True
            self.progress.state = StreamState.RUNNING
            self.progress.message = None
            return False

        # Inline command sequences (firmware / host_timed / none).
        # ``firmware`` and ``host_timed`` differ only in whether we
        # sleep ``wait_ms`` between sends; ``none`` is identical to
        # ``firmware`` in practice (we still wait for acks). The
        # streamer treats them uniformly by emitting commands one at
        # a time with the per-line dwell.
        if action.commands:
            self.progress.state = StreamState.WAITING
            self.progress.message = f"swap ({action.kind})"
            await self._emit()
            for cmd in action.commands:
                if self._aborted:
                    return True
                await self._transport.write_line(cmd.send)
                try:
                    await self._wait_ok()
                except StreamError:
                    self.progress.state = StreamState.ERROR
                    await self._emit()
                    raise
                if cmd.wait_ms > 0:
                    await asyncio.sleep(cmd.wait_ms / 1000.0)
            self.progress.state = StreamState.RUNNING
            self.progress.message = None
            await self._emit()
        return False
