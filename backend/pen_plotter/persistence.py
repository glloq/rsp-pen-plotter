"""Job history persistence via SQLModel/SQLite.

Stores a lightweight record per processed upload so the UI can show a history.
The engine is module-level for the app, but every function accepts an explicit
engine so tests can use an isolated in-memory database.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, desc, select

from pen_plotter.models import Job

_log = logging.getLogger(__name__)

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


class FileRecord(SQLModel, table=True):
    """A persisted, dedup-by-hash entry in the file library.

    One row per unique uploaded source (keyed by ``sha256``). The actual
    bytes and the normalized SVG live on disk under ``data/files/<file_id>/``;
    this table only carries the metadata needed by the file-list UI.
    """

    file_id: str = Field(primary_key=True)
    sha256: str = Field(index=True, unique=True)
    source_file: str
    source_mime: str
    size_bytes: int
    layer_count: int
    folder: str = Field(default="", index=True)
    created_at: datetime


engine: Engine = create_engine(f"sqlite:///{_DB_PATH}")


def _add_missing_columns(target: Engine) -> None:
    """Add columns that exist on the models but not yet in the database.

    A lightweight, additive-only migration so new nullable columns (e.g. queue
    fields added in later versions) don't break an existing SQLite database.
    Renames, drops and type changes are out of scope and still require a manual
    migration.
    """
    inspector = inspect(target)
    for table_name, table in SQLModel.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable and column.default is None:
                _log.warning(
                    "Cannot auto-add non-nullable column %s.%s without a default; "
                    "a manual migration is required.",
                    table_name,
                    column.name,
                )
                continue
            col_type = column.type.compile(dialect=target.dialect)
            with target.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"))
            _log.info("Added missing column %s.%s", table_name, column.name)


def init_db(target: Engine = engine) -> None:
    """Create the database directory and tables, then apply additive migrations.

    Args:
        target: The engine to initialize.
    """
    if target.url.database and target.url.database != ":memory:":
        Path(target.url.database).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(target)
    _add_missing_columns(target)


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


def save_file_record(record: FileRecord, target: Engine = engine) -> FileRecord:
    """Insert or update a :class:`FileRecord` (upsert by ``file_id``)."""
    with Session(target) as session:
        session.merge(record)
        session.commit()
    return record


def get_file_record(file_id: str, target: Engine = engine) -> FileRecord | None:
    """Return a file record by id, or ``None``."""
    with Session(target) as session:
        return session.get(FileRecord, file_id)


def get_file_record_by_hash(sha256: str, target: Engine = engine) -> FileRecord | None:
    """Return the file record whose content hash matches, or ``None``."""
    with Session(target) as session:
        statement = select(FileRecord).where(FileRecord.sha256 == sha256)
        return session.exec(statement).first()


def list_file_records(
    target: Engine = engine,
    folder: str | None = None,
    search: str | None = None,
    sort: str = "date",
    order: str = "desc",
) -> list[FileRecord]:
    """List file records with optional folder filter, name search, and sort.

    Args:
        target: SQLAlchemy engine to read from.
        folder: If provided, restrict to entries in this folder (``""`` = root).
        search: Case-insensitive substring match on ``source_file``.
        sort: ``"name"``, ``"date"`` (``created_at``), or ``"type"`` (``source_mime``).
        order: ``"asc"`` or ``"desc"``.
    """
    with Session(target) as session:
        statement = select(FileRecord)
        if folder is not None:
            statement = statement.where(FileRecord.folder == folder)
        if search:
            statement = statement.where(FileRecord.source_file.ilike(f"%{search}%"))
        column = {
            "name": FileRecord.source_file,
            "date": FileRecord.created_at,
            "type": FileRecord.source_mime,
        }.get(sort, FileRecord.created_at)
        statement = statement.order_by(desc(column) if order == "desc" else column)
        return list(session.exec(statement).all())


def list_file_folders(target: Engine = engine) -> list[str]:
    """Return the distinct, non-empty folder names in use."""
    with Session(target) as session:
        statement = select(FileRecord.folder).distinct()
        return sorted({f for f in session.exec(statement).all() if f})


def delete_file_record(file_id: str, target: Engine = engine) -> bool:
    """Delete a file record. Returns True if a row was removed."""
    with Session(target) as session:
        record = session.get(FileRecord, file_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True


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
