"""Durable G-code file library.

Saved G-code programs the operator can re-print on demand. Persisted in
SQLite alongside the print queue and job history so they survive
restarts. Each row carries the full program text; callers that only need
the file list project metadata (name / size / line count) and never load
the payload, keeping the list cheap.

The library is intentionally decoupled from the print *queue*: saving a
program here does not start it. Printing is an explicit, on-demand action
(:func:`pen_plotter.api.gcode_files.print_file`) that enqueues the saved
program as a run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, Engine
from sqlmodel import Field, Session, SQLModel, desc, select

from pen_plotter.persistence import engine as default_engine


class GcodeFile(SQLModel, table=True):
    """A saved G-code program in the operator's print library."""

    id: str = Field(primary_key=True)
    name: str
    # Profile the program was generated for. Validated again at print time
    # (the profile may have been deleted since the file was saved).
    profile_name: str
    gcode: str
    line_count: int = 0
    size_bytes: int = 0
    # Per-colour drawn length (mm), keyed by canonical hex. Captured at save
    # time from the job that produced the program so a later re-print from
    # the library can still advance the ink odometer — the G-code text alone
    # no longer carries this. Nullable JSON column (auto-added on existing
    # databases by ``_add_missing_columns``); pre-migration rows read back as
    # ``None`` and callers coerce to an empty mapping.
    length_mm_by_color: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def save_gcode_file(
    name: str,
    profile_name: str,
    gcode: str,
    length_mm_by_color: dict[str, float] | None = None,
    target: Engine = default_engine,
) -> GcodeFile:
    """Persist a new G-code program. Returns the stored row."""
    record = GcodeFile(
        id=str(uuid4()),
        name=name,
        profile_name=profile_name,
        gcode=gcode,
        line_count=len(gcode.splitlines()),
        size_bytes=len(gcode.encode("utf-8")),
        length_mm_by_color=length_mm_by_color or {},
    )
    with Session(target) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_gcode_files(target: Engine = default_engine) -> list[GcodeFile]:
    """Return saved programs, newest first."""
    with Session(target) as session:
        statement = select(GcodeFile).order_by(desc(GcodeFile.created_at))
        return list(session.exec(statement).all())


def get_gcode_file(file_id: str, target: Engine = default_engine) -> GcodeFile | None:
    """Return one program by id (with its full ``gcode``), or ``None``."""
    with Session(target) as session:
        return session.get(GcodeFile, file_id)


def rename_gcode_file(file_id: str, name: str, target: Engine = default_engine) -> GcodeFile | None:
    """Rename a program. Returns the updated row, or ``None`` if unknown."""
    with Session(target) as session:
        record = session.get(GcodeFile, file_id)
        if record is None:
            return None
        record.name = name
        record.updated_at = datetime.now(UTC)
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def delete_gcode_file(file_id: str, target: Engine = default_engine) -> bool:
    """Delete a program. Returns ``True`` if a row was removed."""
    with Session(target) as session:
        record = session.get(GcodeFile, file_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True
