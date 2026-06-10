"""Durable print queue with checkpointing and safe resume.

Print runs are persisted in SQLite (alongside the job history) so the queue
survives restarts. A single worker streams runs one at a time to the shared
plotter controller, persisting an acknowledged-line checkpoint as it goes. On
startup, runs left ``running`` by a crash are marked ``paused`` and can be
resumed from their checkpoint — never auto-resumed, since the head's physical
position is unknown after an unclean stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Engine
from sqlmodel import Field, Session, SQLModel, asc, desc, select

from pen_plotter.core.resume import build_resume_program
from pen_plotter.core.toolchange import guided_pause_points, guided_swap_actions
from pen_plotter.domain.recovery import (
    Directive,
    FailureKind,
    resolve_recovery,
)
from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.streamer import (
    StreamError,
    StreamState,
    SwapAction,
    executable_lines,
)
from pen_plotter.persistence import engine as default_engine
from pen_plotter.profiles import get_profile

_log = logging.getLogger(__name__)

# Checkpoint throttling. The streamer emits one progress event per acked
# G-code line; committing a SQLite row for each would put a synchronous
# fsync on the event loop for every ``ok``. Persist at most every
# ``_CHECKPOINT_EVERY_LINES`` lines or ``_CHECKPOINT_INTERVAL_S`` seconds,
# plus on every stream-state flip (pause/swap/error/done) so recovery
# resolution stays acceptable: a crash loses at most ~50 lines of
# checkpoint, and every pause/error boundary is always durable.
_CHECKPOINT_EVERY_LINES = 50
_CHECKPOINT_INTERVAL_S = 2.0


class RunState(StrEnum):
    """Lifecycle states of a queued print run."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


_ACTIVE = (RunState.QUEUED, RunState.RUNNING, RunState.PAUSED)


class PrintRun(SQLModel, table=True):
    """A persisted print job in the production queue."""

    id: str = Field(primary_key=True)
    name: str
    profile_name: str
    gcode: str
    total_lines: int
    acked_lines: int = 0
    state: str = RunState.QUEUED
    priority: int = 0
    error: str | None = None
    # {executable_line_index: operator prompt} for guided tool-change pauses.
    # **Legacy** — kept for backward compatibility with queued runs
    # that predate ``swap_actions``. New runs populate both fields so
    # an older worker version still produces the right operator-confirm
    # behaviour even if it can't act on the richer plan.
    pause_points: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    # {executable_line_index: {kind, prompt, commands}} — richer than
    # ``pause_points``, supports firmware / host_timed / none plans
    # produced by the ``ToolChangeOrchestrator`` (roadmap 2.3 wire).
    # Streamer consumes this when available and falls back to
    # ``pause_points`` for runs queued before the column existed.
    swap_actions: dict[str, dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    # Operator-facing prompt for the swap the run is currently halted on
    # (e.g. "Change pen to Red (#ff0000)" or "Load Red into magazine slot
    # 2"). Set while the streamer sits in its ``WAITING`` state for an
    # operator-confirm tool change and the run is surfaced as ``paused``;
    # cleared the moment streaming resumes. Lets the cockpit show *what*
    # to do and bridge the gap between the controller's transient WAITING
    # state and the durable run state the UI drives off of.
    swap_prompt: str | None = None
    # Layers that were skipped at runtime under a ``skip_layer`` recovery
    # policy. Populated when the streamer raises ``StreamError`` and the
    # active policy says "skip and continue" — see ``_skip_to_next_layer``.
    skipped_layers: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Optional client-supplied key to make enqueue idempotent across retries.
    idempotency_key: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def enqueue(
    name: str,
    profile_name: str,
    gcode: str,
    priority: int = 0,
    idempotency_key: str | None = None,
    target: Engine = default_engine,
) -> PrintRun:
    """Add a run to the queue.

    When ``idempotency_key`` is supplied and a run already exists with it, the
    existing run is returned unchanged so retries don't enqueue duplicates.
    """
    if idempotency_key:
        with Session(target) as session:
            existing = session.exec(
                select(PrintRun).where(PrintRun.idempotency_key == idempotency_key)
            ).first()
            if existing is not None:
                return existing

    profile = get_profile(profile_name)
    pause_points = guided_pause_points(gcode, profile) if profile else {}
    swap_actions_raw = guided_swap_actions(gcode, profile) if profile else {}
    # SQLite JSON column expects string keys; pydantic-dump each
    # SwapAction so the storage round-trip is JSON-safe.
    swap_actions: dict[str, dict[str, Any]] = {
        str(idx): action.model_dump(mode="json") for idx, action in swap_actions_raw.items()
    }
    run = PrintRun(
        id=str(uuid4()),
        name=name,
        profile_name=profile_name,
        gcode=gcode,
        total_lines=len(executable_lines(gcode)),
        priority=priority,
        pause_points={str(k): v for k, v in pause_points.items()},
        swap_actions=swap_actions,
        idempotency_key=idempotency_key,
    )
    with Session(target) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
    return run


def list_runs(target: Engine = default_engine, limit: int = 100) -> list[PrintRun]:
    """Return runs, active ones first (by priority) then recent history."""
    with Session(target) as session:
        statement = (
            select(PrintRun)
            .order_by(desc(PrintRun.priority), asc(PrintRun.created_at))
            .limit(limit)
        )
        return list(session.exec(statement).all())


def get_run(run_id: str, target: Engine = default_engine) -> PrintRun | None:
    """Return a single run by id, or ``None``."""
    with Session(target) as session:
        return session.get(PrintRun, run_id)


def _update(run_id: str, target: Engine, **fields: object) -> PrintRun | None:
    """Patch a run's fields and bump ``updated_at``."""
    with Session(target) as session:
        run = session.get(PrintRun, run_id)
        if run is None:
            return None
        for key, value in fields.items():
            setattr(run, key, value)
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


_LAYER_BOUNDARY_RE = re.compile(
    r"^\s*;\s*(?:Change\s+to\s+pen\s+slot\s+(\d+)\s*\((.*?)\)|Load\s+pen\s+slot\s+(\d+)\s*\((.*?)\)"
    r"|Change\s+pen[:\s]+(.+)|layer[-_\s](\S+))",
    re.IGNORECASE,
)


def _next_layer_boundary(gcode: str, start_exec_index: int) -> tuple[int, str] | None:
    """Locate the next layer/tool-change boundary after ``start_exec_index``.

    Walks the executable lines of ``gcode`` (i.e. the same indexing the
    streamer's checkpoint uses), looking for the next ``; Change to pen
    slot N (label)`` comment or equivalent. Returns
    ``(executable_index, label)`` of the line **after** the comment so
    the run can be re-queued at that checkpoint and the offending
    layer is skipped entirely.

    Used by the ``skip_layer`` recovery policy in :class:`PrintQueue` —
    keeping the regex co-located with the queue keeps the recovery
    decision auditable.
    """
    exec_index = 0
    pending_label: str | None = None
    for raw in gcode.splitlines():
        code = raw.split(";", 1)[0].strip()
        comment = raw.split(";", 1)[1].strip() if ";" in raw else ""
        if comment:
            match = _LAYER_BOUNDARY_RE.match(f"; {comment}")
            if match:
                pending_label = next((g for g in match.groups() if g), "layer")
        if not code:
            continue
        if pending_label is not None and exec_index > start_exec_index:
            return exec_index, pending_label
        if pending_label is not None and exec_index <= start_exec_index:
            # Boundary was for the current/past layer — keep looking for
            # the NEXT one.
            pending_label = None
        exec_index += 1
    return None


def delete_run(run_id: str, target: Engine = default_engine) -> bool:
    """Delete a run by id. Returns ``True`` if a row was removed."""
    with Session(target) as session:
        run = session.get(PrintRun, run_id)
        if run is None:
            return False
        session.delete(run)
        session.commit()
        return True


def next_queued(target: Engine = default_engine) -> PrintRun | None:
    """Return the highest-priority queued run, or ``None``."""
    with Session(target) as session:
        statement = (
            select(PrintRun)
            .where(PrintRun.state == RunState.QUEUED)
            .order_by(desc(PrintRun.priority), asc(PrintRun.created_at))
            .limit(1)
        )
        return session.exec(statement).first()


def recover_interrupted(target: Engine = default_engine) -> int:
    """Mark runs left ``running`` by a crash as ``paused`` for manual resume.

    Returns:
        The number of runs recovered.
    """
    with Session(target) as session:
        statement = select(PrintRun).where(PrintRun.state == RunState.RUNNING)
        interrupted = list(session.exec(statement).all())
        for run in interrupted:
            run.state = RunState.PAUSED
            run.updated_at = datetime.now(UTC)
            session.add(run)
        session.commit()
        return len(interrupted)


class PrintQueue:
    """Sequential worker that streams queued runs to a plotter controller."""

    def __init__(self, controller: PlotterController, engine: Engine = default_engine) -> None:
        """Bind the queue to a controller and persistence engine."""
        self._controller = controller
        self._engine = engine
        self._wake = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._running = False
        self._current_id: str | None = None
        self._cancel_requested = False

    @property
    def current_id(self) -> str | None:
        """The id of the run currently streaming, if any."""
        return self._current_id

    def wake(self) -> None:
        """Signal the worker to re-check the queue (e.g. after enqueue)."""
        self._wake.set()

    def start(self) -> None:
        """Start the background worker loop."""
        if self._loop_task is None:
            self._running = True
            self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        self._wake.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    async def _loop(self) -> None:
        """Drain the queue, waking on new work or a 2s fallback poll."""
        while self._running:
            try:
                ran = await self.run_next()
            except Exception:  # never let the worker die on a single failure
                _log.exception("Print queue worker error")
                ran = False
            if ran:
                continue
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=2.0)

    async def run_next(self) -> bool:
        """Stream the next queued run if the plotter is idle.

        Returns:
            ``True`` if a run was started (and has now finished), ``False`` if
            there was nothing to do or the plotter is busy/disconnected.
        """
        if not self._controller.connected or self._controller.progress.state in (
            StreamState.RUNNING,
            StreamState.PAUSED,
            StreamState.WAITING,
        ):
            return False
        run = next_queued(self._engine)
        if run is None:
            return False

        profile = get_profile(run.profile_name)
        if profile is None:
            _update(run.id, self._engine, state=RunState.FAILED, error="Unknown profile.")
            return True

        program = build_resume_program(run.gcode, run.acked_lines, profile)
        if not program:
            _update(run.id, self._engine, state=RunState.COMPLETED, acked_lines=run.total_lines)
            return True
        preamble_len = len(program) - (run.total_lines - run.acked_lines)
        start_checkpoint = run.acked_lines

        # Remap absolute boundary indices onto the (possibly resumed) program.
        def _remap(idx_str: str) -> int:
            return preamble_len + (int(idx_str) - start_checkpoint)

        pause_points = {
            _remap(idx): prompt
            for idx, prompt in (run.pause_points or {}).items()
            if int(idx) >= start_checkpoint
        }
        swap_actions: dict[int, SwapAction] = {}
        for idx, raw in (run.swap_actions or {}).items():
            if int(idx) < start_checkpoint:
                continue
            try:
                swap_actions[_remap(idx)] = SwapAction.model_validate(raw)
            except Exception:  # noqa: BLE001 — corrupt entry, fall back to legacy
                _log.warning("Discarding malformed swap_action at idx=%s", idx)

        self._current_id = run.id
        self._cancel_requested = False
        _update(run.id, self._engine, state=RunState.RUNNING, error=None)

        # Tracks the swap state we last mirrored into the DB so we only
        # write a row when it actually flips (the streamer emits progress
        # on every acked line; we don't want a redundant UPDATE each time).
        swap_waiting = False
        # In-memory progress tracker. ``latest_acked`` is the live absolute
        # checkpoint — error recovery below MUST use it instead of the
        # ``run`` row snapshot loaded at ``next_queued`` time, which is
        # stale the moment streaming starts. ``flushed_acked``/``flushed_at``
        # drive the write throttle.
        latest_acked = start_checkpoint
        flushed_acked = start_checkpoint
        flushed_at = time.monotonic()
        last_stream_state: object = None

        async def checkpoint(progress: object) -> None:
            nonlocal swap_waiting, latest_acked, flushed_acked, flushed_at, last_stream_state
            acked = getattr(progress, "acked", 0)
            absolute = min(start_checkpoint + max(0, acked - preamble_len), run.total_lines)
            latest_acked = absolute
            fields: dict[str, object] = {}
            state = getattr(progress, "state", None)
            if state == StreamState.WAITING:
                # The streamer parked for an operator-confirm swap. Surface
                # it as a durable ``paused`` run carrying the prompt so the
                # cockpit/header/atelier can show what to do + offer Resume
                # (which routes back through ``controller.resume()``).
                if not swap_waiting:
                    swap_waiting = True
                    fields["state"] = RunState.PAUSED
                    fields["swap_prompt"] = getattr(progress, "message", None)
            elif state == StreamState.RUNNING and swap_waiting:
                # Streaming resumed past the swap — clear the prompt and
                # restore the running state.
                swap_waiting = False
                fields["state"] = RunState.RUNNING
                fields["swap_prompt"] = None
            state_flipped = state != last_stream_state
            last_stream_state = state
            now = time.monotonic()
            # Throttle: a synchronous SQLite commit per acked line would
            # stall the event loop on every ``ok``. Flush on state flips
            # (pause points, swaps, error/done/aborted) so recovery
            # boundaries are always durable, otherwise every N lines / T s.
            if not (
                fields
                or state_flipped
                or absolute - flushed_acked >= _CHECKPOINT_EVERY_LINES
                or now - flushed_at >= _CHECKPOINT_INTERVAL_S
            ):
                return
            fields["acked_lines"] = absolute
            flushed_acked = absolute
            flushed_at = now
            _update(run.id, self._engine, **fields)

        try:
            final = await self._controller.stream(
                "\n".join(program),
                on_progress=checkpoint,
                pause_points=pause_points,
                swap_actions=swap_actions,
            )
        except StreamError as exc:
            # Recovery layer (B.3 → E.2 → 2.4 wire): turn the firmware
            # rejection into a directive that respects the profile's
            # ``recovery_policy``.
            #   - abort            → FAILED.
            #   - pause_and_prompt → PAUSED (operator drives resume).
            #   - skip_layer       → advance acked_lines past the next
            #     layer boundary, append the label to ``skipped_layers``
            #     and re-queue. The worker loop picks the run up again
            #     and resumes from the new checkpoint, so the offending
            #     layer is effectively skipped.
            caps = profile.effective_capabilities()
            decision = resolve_recovery(
                caps.tool_change.recovery_policy,
                None,
                FailureKind.COMMAND_REJECTED,
            )
            if decision.directive is Directive.WAIT_FOR_OPERATOR:
                _update(
                    run.id,
                    self._engine,
                    state=RunState.PAUSED,
                    acked_lines=latest_acked,
                    error=f"{exc} — paused per recovery policy.",
                )
            elif decision.directive is Directive.SKIP_AND_CONTINUE:
                # Use the LIVE checkpoint, not ``run.acked_lines`` — that
                # snapshot was loaded before streaming started, and re-queuing
                # at the stale boundary would physically re-plot already-inked
                # layers (and record the wrong skipped label).
                boundary = _next_layer_boundary(run.gcode, latest_acked)
                if boundary is None:
                    # No more layers to skip into — treat as a normal
                    # failure so the operator is informed.
                    _update(
                        run.id,
                        self._engine,
                        state=RunState.FAILED,
                        acked_lines=latest_acked,
                        error=f"{exc} — skip-layer policy: no further layer boundary.",
                    )
                else:
                    next_index, label = boundary
                    skipped = list(run.skipped_layers or [])
                    skipped.append(label)
                    _update(
                        run.id,
                        self._engine,
                        state=RunState.QUEUED,
                        acked_lines=next_index,
                        skipped_layers=skipped,
                        error=f"{exc} — skipped layer {label!r} per skip_layer policy.",
                    )
                    self.wake()
            else:
                _update(
                    run.id,
                    self._engine,
                    state=RunState.FAILED,
                    acked_lines=latest_acked,
                    error=str(exc),
                )
            return True
        except Exception as exc:  # noqa: BLE001 — never leave a run stranded RUNNING
            # ``controller.stream`` can raise more than ``StreamError``:
            # a ``RuntimeError`` ("A job is already running" / "Not
            # connected") when a manual command or disconnect raced the
            # queue worker. The run was already flipped RUNNING above —
            # without this handler it would stay stranded forever
            # (``next_queued`` only selects QUEUED rows).
            if isinstance(exc, RuntimeError):
                # Connection / busy race — give the run back to the queue
                # so the worker retries once the controller frees up.
                _log.warning("Run %s could not stream (%s); re-queueing.", run.id, exc)
                _update(
                    run.id, self._engine, state=RunState.QUEUED, acked_lines=latest_acked
                )
            else:
                _log.exception("Run %s failed unexpectedly", run.id)
                _update(
                    run.id,
                    self._engine,
                    state=RunState.FAILED,
                    acked_lines=latest_acked,
                    error=str(exc),
                )
            return True
        finally:
            self._current_id = None

        if final.state == StreamState.DONE:
            _update(
                run.id,
                self._engine,
                state=RunState.COMPLETED,
                acked_lines=run.total_lines,
                swap_prompt=None,
            )
        elif final.state == StreamState.ABORTED:
            state = RunState.CANCELED if self._cancel_requested else RunState.PAUSED
            # Keep the swap prompt when the abort left the run paused
            # mid-swap (so the cockpit still shows what to do on resume);
            # clear it on an outright cancel. Always persist the final
            # checkpoint — with throttled writes the last flushed value
            # can lag the true acked count (e.g. an emergency-stop cancel
            # never reaches the streamer's ABORTED emit).
            clear = {"swap_prompt": None} if state == RunState.CANCELED else {}
            _update(run.id, self._engine, state=state, acked_lines=latest_acked, **clear)
        return True

    def pause(self, run_id: str) -> PrintRun | None:
        """Pause the run if it is the one currently streaming."""
        if run_id == self._current_id:
            self._controller.pause()
            return _update(run_id, self._engine, state=RunState.PAUSED)
        return get_run(run_id, self._engine)

    def resume(self, run_id: str) -> PrintRun | None:
        """Resume a run: continue if streaming, else re-queue from checkpoint."""
        run = get_run(run_id, self._engine)
        if run is None:
            return None
        if run_id == self._current_id:
            self._controller.resume()
            return _update(run_id, self._engine, state=RunState.RUNNING)
        if run.state == RunState.PAUSED:
            updated = _update(run_id, self._engine, state=RunState.QUEUED)
            self.wake()
            return updated
        return run

    def cancel(self, run_id: str) -> PrintRun | None:
        """Cancel a run, aborting it if it is currently streaming."""
        run = get_run(run_id, self._engine)
        if run is None:
            return None
        if run_id == self._current_id:
            self._cancel_requested = True
            self._controller.abort()
            return get_run(run_id, self._engine)
        if run.state in _ACTIVE:
            return _update(run_id, self._engine, state=RunState.CANCELED)
        return run
