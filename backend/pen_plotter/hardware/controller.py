"""Plotter connection controller.

Owns the active transport and streaming task, exposes jog/home/run/pause/
resume/abort, and broadcasts progress to subscribers (e.g. WebSocket clients).
Transport is injected, so the controller is fully testable with a mock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from pen_plotter.hardware.commands import goto_command, home_command, jog_command
from pen_plotter.hardware.streamer import (
    GcodeStreamer,
    ProgressCallback,
    StreamProgress,
    StreamState,
    SwapAction,
)
from pen_plotter.hardware.transport import SerialTransport, Transport
from pen_plotter.models import MachineProfile


class PlotterController:
    """Manages a single plotter connection and streaming job."""

    def __init__(self) -> None:
        """Create a disconnected controller."""
        self._transport: Transport | None = None
        self._streamer: GcodeStreamer | None = None
        self._task: asyncio.Task[StreamProgress] | None = None
        self._subscribers: set[asyncio.Queue[StreamProgress]] = set()

    @property
    def connected(self) -> bool:
        """Whether a transport is currently attached."""
        return self._transport is not None

    @property
    def progress(self) -> StreamProgress:
        """The current streaming progress snapshot."""
        if self._streamer is not None:
            return self._streamer.progress
        return StreamProgress(total=0, sent=0, acked=0, state=StreamState.IDLE)

    def attach(self, transport: Transport) -> None:
        """Attach an already-open transport (used in tests and after connect)."""
        self._transport = transport

    async def open_serial(self, port: str, baudrate: int = 115200, terminator: str = "\n") -> None:
        """Open and attach a real serial transport.

        Args:
            port: Serial device path.
            baudrate: Connection baud rate.
            terminator: Line terminator (line feed for GRBL/Marlin, carriage
                return for EBB).
        """
        self.attach(await SerialTransport.open(port, baudrate, terminator))

    async def disconnect(self) -> None:
        """Abort any running job and close the transport."""
        self.abort()
        if self._task is not None:
            with contextlib.suppress(Exception):
                await self._task
        if self._transport is not None:
            await self._transport.close()
        self._transport = None
        self._streamer = None
        self._task = None

    def _require_transport(self) -> Transport:
        """Return the active transport or raise if disconnected."""
        if self._transport is None:
            raise RuntimeError("Not connected to a plotter.")
        return self._transport

    @property
    def _job_active(self) -> bool:
        """Whether a streaming job is currently running or paused."""
        return self._task is not None and not self._task.done()

    def _require_idle(self) -> None:
        """Reject manual commands while a job owns the transport."""
        if self._job_active:
            raise RuntimeError("A job is running; pause or abort it before sending commands.")

    async def _send_immediate(self, lines: list[str], timeout_s: float = 30.0) -> None:
        """Send control lines, waiting for an ``ok`` after each."""
        transport = self._require_transport()
        for line in lines:
            await transport.write_line(line)
            while True:
                try:
                    response = (await asyncio.wait_for(transport.read_line(), timeout_s)).lower()
                except TimeoutError as exc:
                    raise RuntimeError("Controller did not acknowledge in time.") from exc
                if response.startswith("ok"):
                    break
                if response.startswith(("error", "alarm", "!!")):
                    raise RuntimeError(f"Controller error: {response}")

    async def jog(self, dx_mm: float, dy_mm: float, profile: MachineProfile) -> None:
        """Jog the head by a relative offset."""
        self._require_idle()
        await self._send_immediate(jog_command(dx_mm, dy_mm, profile))

    async def goto(self, x_mm: float, y_mm: float, profile: MachineProfile) -> None:
        """Move the head to an absolute workspace position."""
        self._require_idle()
        await self._send_immediate(goto_command(x_mm, y_mm, profile))

    async def home(self, profile: MachineProfile) -> None:
        """Home the machine."""
        self._require_idle()
        await self._send_immediate(home_command(profile))

    async def send_commands(self, lines: list[str]) -> None:
        """Send raw control lines immediately, e.g. for a user macro.

        Raises:
            RuntimeError: If disconnected or a job currently owns the transport.
        """
        self._require_idle()
        await self._send_immediate(lines)

    async def run(self, gcode: str) -> None:
        """Start streaming a G-code program in the background.

        Args:
            gcode: The G-code program to stream.

        Raises:
            RuntimeError: If disconnected or a job is already running.
        """
        transport = self._require_transport()
        if self._job_active:
            raise RuntimeError("A job is already running.")
        self._streamer = GcodeStreamer(transport, on_progress=self._broadcast)
        self._task = asyncio.create_task(self._streamer.run(gcode))
        self._task.add_done_callback(self._on_task_done)

    async def stream(
        self,
        gcode: str,
        on_progress: ProgressCallback | None = None,
        pause_points: dict[int, str] | None = None,
        swap_actions: dict[int, SwapAction] | None = None,
    ) -> StreamProgress:
        """Stream a G-code program and await its completion.

        Unlike :meth:`run` (fire-and-forget for the manual send path), this
        awaits the streaming task and returns its final progress, so a queue
        worker can drive jobs sequentially. Pause/resume/abort act on the
        running stream as usual.

        Args:
            gcode: The G-code program to stream.
            on_progress: Optional extra progress callback (in addition to the
                broadcast to WebSocket subscribers).
            pause_points: Optional ``{line_index: prompt}`` for guided
                tool-change pauses (see :class:`GcodeStreamer`). Legacy
                — superseded by ``swap_actions`` for new code paths.
            swap_actions: Optional ``{line_index: SwapAction}`` for the
                richer v0.2 tool-change boundary plans (firmware /
                host_macro / operator confirm in one channel).

        Returns:
            The final :class:`StreamProgress`.

        Raises:
            RuntimeError: If disconnected or a job is already running.
            StreamError: If the controller reports an error during streaming.
        """
        transport = self._require_transport()
        if self._job_active:
            raise RuntimeError("A job is already running.")

        async def _combined(progress: StreamProgress) -> None:
            await self._broadcast(progress)
            if on_progress is not None:
                await on_progress(progress)

        self._streamer = GcodeStreamer(
            transport,
            on_progress=_combined,
            pause_points=pause_points,
            swap_actions=swap_actions,
        )
        self._task = asyncio.create_task(self._streamer.run(gcode))
        self._task.add_done_callback(self._on_task_done)
        return await self._task

    def _on_task_done(self, task: asyncio.Task[StreamProgress]) -> None:
        """Retrieve the streaming task's result so exceptions aren't lost."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logging.getLogger(__name__).error("Streaming job failed: %s", exc)

    def pause(self) -> None:
        """Pause the running job."""
        if self._streamer is not None:
            self._streamer.pause()

    def resume(self) -> None:
        """Resume a paused job."""
        if self._streamer is not None:
            self._streamer.resume()

    def abort(self) -> None:
        """Abort the running job."""
        if self._streamer is not None:
            self._streamer.abort()

    def subscribe(self) -> asyncio.Queue[StreamProgress]:
        """Register a progress subscriber queue."""
        queue: asyncio.Queue[StreamProgress] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[StreamProgress]) -> None:
        """Remove a progress subscriber queue."""
        self._subscribers.discard(queue)

    async def _broadcast(self, progress: StreamProgress) -> None:
        """Push a progress snapshot to all subscribers.

        Iterate over a snapshot of the subscriber set: ``put`` awaits, and a
        concurrent ``subscribe``/``unsubscribe`` during that await would
        otherwise mutate the set mid-iteration (``RuntimeError``).
        """
        for queue in list(self._subscribers):
            await queue.put(progress)


controller = PlotterController()
