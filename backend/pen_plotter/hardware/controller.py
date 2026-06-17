"""Plotter connection controller.

Owns the active transport and streaming task, exposes jog/home/run/pause/
resume/abort, and broadcasts progress to subscribers (e.g. WebSocket clients).
Transport is injected, so the controller is fully testable with a mock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections import deque

from pen_plotter.hardware.commands import goto_command, home_command, jog_command
from pen_plotter.hardware.streamer import (
    GcodeStreamer,
    ProgressCallback,
    StreamProgress,
    StreamState,
    SwapAction,
)
from pen_plotter.hardware.transport import MockTransport, SerialTransport, Transport
from pen_plotter.models import MachineProfile

# Per-dialect emergency-stop payload. GRBL processes ``0x18`` (Ctrl-X) as
# a soft reset at interrupt level — it bypasses the planner queue, so it
# stops a long G1 move that an ``ok``-ack flow cannot interrupt. Marlin
# and Klipper accept ``M112`` as an immediate halt. EBB exposes ``ES``
# (emergency stop) over its CR-terminated protocol.
_EMERGENCY_BYTES: dict[str, bytes] = {
    "grbl": b"\x18",
    "marlin": b"M112\n",
    "klipper": b"M112\n",
    "ebb": b"ES\r",
}

# Capacity of each per-subscriber progress queue. The streamer emits one
# event per acked line, so a slow consumer (sluggish browser tab) can
# fall behind quickly. A bounded queue with drop-oldest semantics keeps
# memory finite while still surfacing the latest snapshot — progress is
# idempotent (sent/acked/state) so dropping intermediates is safe.
_SUBSCRIBER_QUEUE_MAXSIZE = 256

# How many of the most-recent G-code lines written to the device are kept
# for the "commands sent" history surfaced in the Plotter tab. A rolling
# window: during a long job it simply tails the latest lines.
_COMMAND_LOG_MAXLEN = 200


def _fake_hardware_enabled() -> bool:
    """Return True when OMNIPLOT_FAKE_HARDWARE asks for in-process mocking.

    Lets E2E tests drive the full operator workflow without a serial
    device — every ``open_serial`` call attaches a :class:`MockTransport`
    that echoes ``ok`` instead of opening ``/dev/ttyUSB*``.
    """
    raw = os.environ.get("OMNIPLOT_FAKE_HARDWARE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class PlotterController:
    """Manages a single plotter connection and streaming job."""

    def __init__(self) -> None:
        """Create a disconnected controller."""
        self._transport: Transport | None = None
        self._streamer: GcodeStreamer | None = None
        self._task: asyncio.Task[StreamProgress] | None = None
        self._subscribers: set[asyncio.Queue[StreamProgress]] = set()
        # Serialises manual commands (jog / goto / home / send_commands)
        # so two concurrent HTTP requests cannot interleave their bytes
        # on the serial line or steal each other's ``ok`` response.
        self._send_lock = asyncio.Lock()
        # Rolling history of G-code lines actually written to the device —
        # manual commands (``_send_immediate``) and streamed job / pen /
        # swap lines (via the streamer's ``on_send``) — surfaced read-only
        # in the Plotter tab. Capped so it can't grow without bound.
        self._command_log: deque[str] = deque(maxlen=_COMMAND_LOG_MAXLEN)

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

    @property
    def command_log(self) -> list[str]:
        """The recent G-code lines sent to the device, oldest first."""
        return list(self._command_log)

    def _record_sent(self, line: str) -> None:
        """Append one written line to the rolling command history."""
        self._command_log.append(line)

    def attach(self, transport: Transport) -> None:
        """Attach an already-open transport (used in tests and after connect)."""
        # A fresh connection starts a fresh command history.
        self._command_log.clear()
        self._transport = transport

    async def open_serial(self, port: str, baudrate: int = 115200, terminator: str = "\n") -> None:
        """Open and attach a real serial transport.

        When ``OMNIPLOT_FAKE_HARDWARE=1`` is set, attaches a
        :class:`MockTransport` instead — the call signature stays
        identical so the API endpoint and the SPA don't notice. Used by
        Playwright E2E tests to drive the full operator parcours
        (connect → queue → plot → resume) without a serial device.

        Args:
            port: Serial device path.
            baudrate: Connection baud rate.
            terminator: Line terminator (line feed for GRBL/Marlin, carriage
                return for EBB).
        """
        if _fake_hardware_enabled():
            self.attach(MockTransport())
            return
        transport = await SerialTransport.open(port, baudrate, terminator)
        # Consume the startup banner GRBL/Marlin emit on reset so the
        # first ``_wait_ok`` doesn't swallow it and shift the ack count.
        with contextlib.suppress(Exception):
            await transport.drain_input(idle_timeout_s=0.2)
        self.attach(transport)

    async def disconnect(self) -> None:
        """Abort any running job and close the transport.

        Cancels the streaming task instead of merely awaiting it: if the
        firmware is mute, the streamer is blocked in ``_wait_ok`` for up
        to ``ack_timeout_s`` (30 s) and ``abort()`` alone won't unblock
        it. Disconnect is operator intent — drop the link now, the
        machine's state on the other end of a cut cable is irrelevant.
        """
        self.abort()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(self._task, timeout=2.0)
        if self._transport is not None:
            with contextlib.suppress(Exception):
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
        """Send control lines, waiting for an ``ok`` after each.

        Holds ``_send_lock`` for the duration so two concurrent manual
        commands cannot interleave bytes on the serial line.

        Raises:
            RuntimeError: If disconnected, or if a streaming job took
                ownership of the transport while this command was queued
                on the lock (the callers' ``_require_idle`` pre-check is
                a TOCTOU: ``stream()``/``run()`` may install a streamer
                between that check and our lock acquisition).
        """
        transport = self._require_transport()
        async with self._send_lock:
            # Re-check under the lock — a manual command that passed
            # ``_require_idle`` may have been waiting here while a job
            # started; letting it proceed would interleave its G-code
            # into the live stream.
            self._require_idle()
            for line in lines:
                self._record_sent(line)
                await transport.write_line(line)
                while True:
                    try:
                        response = (
                            await asyncio.wait_for(transport.read_line(), timeout_s)
                        ).lower()
                    except TimeoutError as exc:
                        raise RuntimeError("Controller did not acknowledge in time.") from exc
                    if response.startswith("ok"):
                        break
                    if response.startswith(("error", "alarm", "!!")):
                        raise RuntimeError(f"Controller error: {response}")

    async def jog(
        self, dx_mm: float, dy_mm: float, profile: MachineProfile, dz_mm: float = 0.0
    ) -> None:
        """Jog the head by a relative offset (X/Y, plus optional Z)."""
        self._require_idle()
        await self._send_immediate(jog_command(dx_mm, dy_mm, profile, dz_mm=dz_mm))

    async def goto(
        self, x_mm: float, y_mm: float, profile: MachineProfile, z_mm: float | None = None
    ) -> None:
        """Move the head to an absolute workspace position (optional Z)."""
        self._require_idle()
        await self._send_immediate(goto_command(x_mm, y_mm, profile, z_mm=z_mm))

    async def home(self, profile: MachineProfile, axis: str | None = None) -> None:
        """Home the machine — all axes, or a single ``axis`` (X / Y / Z)."""
        self._require_idle()
        await self._send_immediate(home_command(profile, axis))

    async def send_commands(self, lines: list[str]) -> None:
        """Send raw control lines immediately, e.g. for a user macro.

        Raises:
            RuntimeError: If disconnected or a job currently owns the transport.
        """
        self._require_idle()
        await self._send_immediate(lines)

    async def run(
        self,
        gcode: str,
        profile: MachineProfile | None = None,
    ) -> None:
        """Start streaming a G-code program in the background.

        When ``profile`` is supplied, guided tool-change swap actions are
        computed from the program (same logic the print queue uses) so a
        direct ``POST /plotter/run`` honours operator-confirm pauses on a
        multi-pen profile instead of blindly sending firmware-pause
        commands. Without a profile the behaviour is unchanged — every
        line is streamed as-is.

        Args:
            gcode: The G-code program to stream.
            profile: Optional machine profile used to derive ``swap_actions``.

        Raises:
            RuntimeError: If disconnected or a job is already running.
        """
        transport = self._require_transport()
        swap_actions: dict[int, SwapAction] | None = None
        if profile is not None:
            # Local import keeps ``hardware`` decoupled from ``core``.
            from pen_plotter.core.toolchange import guided_swap_actions  # noqa: PLC0415

            swap_actions = guided_swap_actions(gcode, profile) or None
        # Acquire ``_send_lock`` so a manual command in flight finishes
        # before we install the streamer task — otherwise its bytes can
        # interleave with the streamer's first write (TOCTOU between
        # ``_require_idle`` and the eventual write).
        async with self._send_lock:
            if self._job_active:
                raise RuntimeError("A job is already running.")
            self._streamer = GcodeStreamer(
                transport,
                on_progress=self._broadcast,
                swap_actions=swap_actions,
                on_send=self._record_sent,
            )
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

        async def _combined(progress: StreamProgress) -> None:
            await self._broadcast(progress)
            if on_progress is not None:
                await on_progress(progress)

        # Same lock as :meth:`run` — block out any racing manual command
        # so the streamer owns the transport from its very first write.
        async with self._send_lock:
            if self._job_active:
                raise RuntimeError("A job is already running.")
            streamer = GcodeStreamer(
                transport,
                on_progress=_combined,
                pause_points=pause_points,
                swap_actions=swap_actions,
                on_send=self._record_sent,
            )
            task = asyncio.create_task(streamer.run(gcode))
            task.add_done_callback(self._on_task_done)
            self._streamer = streamer
            self._task = task
        try:
            return await task
        except asyncio.CancelledError:
            # The streaming task was cancelled — typically by
            # ``emergency_stop`` or ``disconnect``. Distinguish that from
            # an *outer* cancellation (queue worker being shut down): if
            # the task itself is cancelled, surface a clean ABORTED final
            # progress so callers like the print queue's ``run_next``
            # don't have a ``CancelledError`` (BaseException) escape past
            # their ``except Exception`` clause and kill the worker loop.
            # If the task is NOT cancelled, the cancel came from our own
            # caller — propagate it.
            if not task.cancelled():
                raise
            streamer.progress.state = StreamState.ABORTED
            return streamer.progress

    def _on_task_done(self, task: asyncio.Task[StreamProgress]) -> None:
        """Retrieve the streaming task's result so exceptions aren't lost."""
        if task.cancelled():
            # Reflect the cancellation in the streamer's progress so
            # ``/plotter/status`` doesn't return a stale RUNNING for a
            # job that was emergency-stopped or disconnected mid-flight.
            if self._streamer is not None:
                self._streamer.progress.state = StreamState.ABORTED
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

    async def emergency_stop(self, profile: MachineProfile | None = None) -> None:
        """Send an immediate real-time stop to the controller.

        The ``ok``-ack handshake cannot interrupt a long G1 move that
        the firmware is already executing — ``abort()`` only takes effect
        on the *next* iteration of the streamer's send loop. This sends
        the dialect-appropriate real-time payload (GRBL ``0x18`` soft
        reset, Marlin/Klipper ``M112``, EBB ``ES``) straight to the
        transport, bypassing the line queue, and cancels the streaming
        task so any in-flight ``_wait_ok`` unblocks promptly.

        Args:
            profile: Optional profile — its ``gcode_dialect`` selects
                the payload. Falls back to GRBL's soft reset when None.
        """
        # Mark abort first so a racing send loop sees the flag the next
        # time it gets the GIL, even if the cancel below arrives later.
        if self._streamer is not None:
            self._streamer.abort()
        transport = self._transport
        if transport is not None:
            dialect = profile.gcode_dialect if profile is not None else "grbl"
            payload = _EMERGENCY_BYTES.get(dialect, _EMERGENCY_BYTES["grbl"])
            with contextlib.suppress(Exception):
                await transport.write_raw(payload)
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self._task

    def subscribe(self) -> asyncio.Queue[StreamProgress]:
        """Register a bounded progress subscriber queue.

        The queue is sized to absorb a normal burst of progress events;
        a slow consumer that fills it past capacity loses the oldest
        snapshot first (see :meth:`_broadcast`) rather than blocking the
        streamer or growing memory without bound.
        """
        queue: asyncio.Queue[StreamProgress] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_MAXSIZE
        )
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[StreamProgress]) -> None:
        """Remove a progress subscriber queue."""
        self._subscribers.discard(queue)

    async def _broadcast(self, progress: StreamProgress) -> None:
        """Push a progress snapshot to all subscribers without blocking.

        Iterate over a snapshot of the subscriber set so a concurrent
        ``subscribe``/``unsubscribe`` can't mutate the set mid-iteration.
        Uses non-blocking ``put_nowait`` with drop-oldest on overflow so
        the streamer is never stalled by a lagging WebSocket client —
        progress is idempotent (sent/acked/state), dropping intermediate
        snapshots is safe.
        """
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(progress)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(progress)


controller = PlotterController()
