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

from pen_plotter.hardware.transport import Transport


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
                enters ``WAITING`` until resumed (a software-guided tool change).
        """
        self._transport = transport
        self._on_progress = on_progress
        self._ack_timeout_s = ack_timeout_s
        self._pause_points = pause_points or {}
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

            if index in self._pause_points:
                # Guided tool change: replace the firmware pause with a software
                # one. Skip the line and wait for the operator to resume.
                self.progress.state = StreamState.WAITING
                self.progress.message = self._pause_points[index]
                self._resume.clear()
                await self._emit()
                await self._resume.wait()
                if self._aborted:
                    self.progress.state = StreamState.ABORTED
                    await self._emit()
                    return self.progress
                self.progress.state = StreamState.RUNNING
                self.progress.message = None
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
