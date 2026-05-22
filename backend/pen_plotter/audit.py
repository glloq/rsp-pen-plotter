"""Audit trail for sensitive operations.

Records a persistent, append-only log of machine-control and queue actions so
operators can review what was sent to the hardware and when. Stored in the same
SQLite database as the job history and print queue.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, desc, select

from pen_plotter.persistence import engine as default_engine


class AuditEntry(SQLModel, table=True):
    """One recorded sensitive action."""

    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action: str
    detail: str = ""


def record(action: str, detail: str = "", target: Engine = default_engine) -> None:
    """Append an entry to the audit trail.

    Args:
        action: A short action identifier, e.g. ``"plotter.run"``.
        detail: Optional human-readable context.
        target: The engine to write to.
    """
    with Session(target) as session:
        session.add(AuditEntry(action=action, detail=detail))
        session.commit()


def list_entries(limit: int = 100, target: Engine = default_engine) -> list[AuditEntry]:
    """Return recent audit entries, newest first."""
    with Session(target) as session:
        statement = select(AuditEntry).order_by(desc(AuditEntry.id)).limit(limit)
        return list(session.exec(statement).all())
