"""Audit trail for sensitive operations.

Records a persistent, append-only log of machine-control and queue actions so
operators can review what was sent to the hardware and when. Stored in the same
SQLite database as the job history and print queue.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, desc, select

from pen_plotter.persistence import engine as default_engine

_log = logging.getLogger(__name__)


class AuditEntry(SQLModel, table=True):
    """One recorded sensitive action."""

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action: str
    detail: str = ""


def record(action: str, detail: str = "", target: Engine = default_engine) -> None:
    """Append an entry to the audit trail (best-effort).

    Audit call sites run *after* the sensitive action has already happened
    (the macro executed, the job started). A failed write here — SQLite
    locked past ``busy_timeout``, or a full disk mid-rebuild — must therefore
    never propagate: raising would turn a completed hardware action into a 500,
    and an operator retry would re-send the commands to the machine. On failure
    we log and move on rather than mask or duplicate the action.

    Args:
        action: A short action identifier, e.g. ``"plotter.run"``.
        detail: Optional human-readable context.
        target: The engine to write to.
    """
    try:
        with Session(target) as session:
            session.add(AuditEntry(action=action, detail=detail))
            session.commit()
    except Exception:  # noqa: BLE001 — audit is best-effort; never break the caller
        _log.warning("Audit write failed for action=%r; continuing", action, exc_info=True)


def list_entries(limit: int = 100, target: Engine = default_engine) -> list[AuditEntry]:
    """Return recent audit entries, newest first."""
    with Session(target) as session:
        statement = select(AuditEntry).order_by(desc(AuditEntry.id)).limit(limit)
        return list(session.exec(statement).all())
