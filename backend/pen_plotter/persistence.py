"""Job history persistence via SQLModel/SQLite.

Stores a lightweight record per processed upload so the UI can show a history.
The engine is module-level for the app, but every function accepts an explicit
engine so tests can use an isolated in-memory database.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, desc, select

from pen_plotter.models import Job

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "omniplot.db"
_DB_PATH = Path(os.environ.get("OMNIPLOT_DB", _DEFAULT_DB))


class JobRecord(SQLModel, table=True):
    """A persisted summary of one processed job."""

    job_id: str = Field(primary_key=True)
    source_file: str
    source_mime: str
    profile_name: str
    status: str
    layer_count: int
    created_at: datetime


def _default_engine() -> Engine:
    """Create the application's SQLite engine, ensuring its directory exists."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{_DB_PATH}")


engine: Engine = _default_engine()


def init_db(target: Engine = engine) -> None:
    """Create tables if they do not yet exist.

    Args:
        target: The engine to initialize.
    """
    SQLModel.metadata.create_all(target)


def save_job(job: Job, target: Engine = engine) -> JobRecord:
    """Persist a job summary.

    Args:
        job: The job to record.
        target: The engine to write to.

    Returns:
        The stored :class:`JobRecord`.
    """
    record = JobRecord(
        job_id=job.job_id,
        source_file=job.source_file,
        source_mime=job.source_mime,
        profile_name=job.profile_name,
        status=job.status,
        layer_count=len(job.layers),
        created_at=job.created_at,
    )
    with Session(target) as session:
        session.merge(record)
        session.commit()
    return record


def list_jobs(target: Engine = engine, limit: int = 50) -> list[JobRecord]:
    """Return recent job records, newest first.

    Args:
        target: The engine to read from.
        limit: Maximum number of records to return.

    Returns:
        Job records ordered by creation time, descending.
    """
    with Session(target) as session:
        statement = select(JobRecord).order_by(desc(JobRecord.created_at)).limit(limit)
        return list(session.exec(statement).all())


def get_job(job_id: str, target: Engine = engine) -> JobRecord | None:
    """Return a single job record by id, or ``None``.

    Args:
        job_id: The job identifier.
        target: The engine to read from.

    Returns:
        The matching record, or ``None``.
    """
    with Session(target) as session:
        return session.get(JobRecord, job_id)
