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
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column, Engine
from sqlmodel import Field, Session, SQLModel, asc, desc, select

from pen_plotter.core.resume import build_resume_program
from pen_plotter.core.toolchange import guided_pause_points
from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.streamer import StreamError, StreamState, executable_lines
from pen_plotter.persistence import engine as default_engine
from pen_plotter.profiles import get_profile

_log = logging.getLogger(__name__)


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
    pause_points: dict = Field(default_factory=dict, sa_column=Column(JSON))
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
    run = PrintRun(
        id=str(uuid4()),
        name=name,
        profile_name=profile_name,
        gcode=gcode,
        total_lines=len(executable_lines(gcode)),
        priority=priority,
        pause_points={str(k): v for k, v in pause_points.items()},
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

        # Remap absolute guided-pause indices onto the (possibly resumed) program.
        pause_points = {
            preamble_len + (int(idx) - start_checkpoint): prompt
            for idx, prompt in (run.pause_points or {}).items()
            if int(idx) >= start_checkpoint
        }

        self._current_id = run.id
        self._cancel_requested = False
        _update(run.id, self._engine, state=RunState.RUNNING, error=None)

        async def checkpoint(progress: object) -> None:
            acked = getattr(progress, "acked", 0)
            absolute = min(start_checkpoint + max(0, acked - preamble_len), run.total_lines)
            _update(run.id, self._engine, acked_lines=absolute)

        try:
            final = await self._controller.stream(
                "\n".join(program), on_progress=checkpoint, pause_points=pause_points
            )
        except StreamError as exc:
            _update(run.id, self._engine, state=RunState.FAILED, error=str(exc))
            return True
        finally:
            self._current_id = None

        if final.state == StreamState.DONE:
            _update(run.id, self._engine, state=RunState.COMPLETED, acked_lines=run.total_lines)
        elif final.state == StreamState.ABORTED:
            state = RunState.CANCELED if self._cancel_requested else RunState.PAUSED
            _update(run.id, self._engine, state=state)
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
