"""Plotter connection controller.

Owns the active transport and streaming task, exposes jog/home/run/pause/
resume/abort, and broadcasts progress to subscribers (e.g. WebSocket clients).
Transport is injected, so the controller is fully testable with a mock.
"""

from __future__ import annotations

import asyncio
import contextlib

from pen_plotter.hardware.commands import home_command, jog_command
from pen_plotter.hardware.streamer import GcodeStreamer, StreamProgress, StreamState
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

    async def open_serial(self, port: str, baudrate: int = 115200) -> None:
        """Open and attach a real serial transport.

        Args:
            port: Serial device path.
            baudrate: Connection baud rate.
        """
        self.attach(await SerialTransport.open(port, baudrate))

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

    async def _send_immediate(self, lines: list[str]) -> None:
        """Send control lines, waiting for an ``ok`` after each."""
        transport = self._require_transport()
        for line in lines:
            await transport.write_line(line)
            while True:
                response = (await transport.read_line()).lower()
                if response.startswith("ok"):
                    break
                if response.startswith(("error", "alarm", "!!")):
                    raise RuntimeError(f"Controller error: {response}")

    async def jog(self, dx_mm: float, dy_mm: float, profile: MachineProfile) -> None:
        """Jog the head by a relative offset."""
        await self._send_immediate(jog_command(dx_mm, dy_mm, profile))

    async def home(self, profile: MachineProfile) -> None:
        """Home the machine."""
        await self._send_immediate(home_command(profile))

    async def run(self, gcode: str) -> None:
        """Start streaming a G-code program in the background.

        Args:
            gcode: The G-code program to stream.

        Raises:
            RuntimeError: If disconnected or a job is already running.
        """
        transport = self._require_transport()
        if self._task is not None and not self._task.done():
            raise RuntimeError("A job is already running.")
        self._streamer = GcodeStreamer(transport, on_progress=self._broadcast)
        self._task = asyncio.create_task(self._streamer.run(gcode))

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
        """Push a progress snapshot to all subscribers."""
        for queue in self._subscribers:
            await queue.put(progress)


controller = PlotterController()
