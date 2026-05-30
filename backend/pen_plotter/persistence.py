"""Job history persistence via SQLModel/SQLite.

Stores a lightweight record per processed upload so the UI can show a history.
The engine is module-level for the app, but every function accepts an explicit
engine so tests can use an isolated in-memory database.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, desc, select

from pen_plotter.domain.print_plan import ResolvedPlan
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


class PlanSnapshotRecord(SQLModel, table=True):
    """A resolved :class:`PrintPlan` archived for diagnostics.

    Keyed by the deterministic ``plan_hash`` produced by
    :func:`pen_plotter.application.plan_resolver.resolve_plan`, so the
    same logical plan only ever occupies one row regardless of how many
    times it's submitted. ``plan_json`` carries the full resolved plan
    so an operator can replay or compare it later.
    """

    plan_hash: str = Field(primary_key=True)
    profile_name: str = Field(index=True)
    layer_count: int
    created_at: datetime
    plan_json: str


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


class AppSettingRecord(SQLModel, table=True):
    """Generic key/value store for small global app settings.

    Used today for the ``palette_source`` toggle that picks where the
    per-layer colour picker reads from (installed pens / available
    colours / union). The shape stays generic so future single-value
    settings can land without another migration: each setting is one
    row, ``key`` is the namespaced identifier, ``value`` carries the
    string-encoded payload (JSON for non-string types).
    """

    key: str = Field(primary_key=True)
    value: str


class AvailableColorRecord(SQLModel, table=True):
    """An ink the operator has on hand but doesn't necessarily mount.

    The library is a global app-wide inventory of pen colours — independent
    of any specific machine profile. It feeds the editor's per-layer
    colour picker so the operator can pre-declare every Sharpie / fineliner
    they own once, then assign them to layers without typing ``#`` codes
    each time. ``hex`` is the only mandatory field; ``name`` is optional
    (UI falls back to the hex code) and ``position`` drives the display
    order so the operator can rearrange the swatch strip.
    """

    color_id: str = Field(primary_key=True)
    # Lowercased ``#rrggbb``. Indexed unique so duplicates can't sneak in
    # through the API even if the client doesn't dedupe; the endpoint
    # surfaces the existing entry instead of returning a 409.
    hex: str = Field(index=True, unique=True)
    # Free-form operator label ("Cyan Sharpie 04", "Rouge cerise"); empty
    # string when unset. The picker shows the hex when this is blank.
    name: str = Field(default="")
    # Display ordering. Auto-assigned to ``max(position) + 1`` at create
    # time so new entries land at the end of the strip; can be rewritten
    # by the PATCH endpoint to reorder.
    position: int = Field(default=0, index=True)
    # Pen tip / line width in millimetres. Each marker lays down a
    # different stroke, which drives line spacing for fills and the
    # preview's rendered thickness. Defaults to a typical fineliner so
    # rows migrated from an older DB (where the column is back-filled by
    # ``_add_missing_columns``) get a sensible value rather than 0.
    stroke_width_mm: float = Field(default=0.5)
    # Accumulated distance actually drawn with this pen, in millimetres.
    # Incremented by the frontend each time a job is sent/queued; reset
    # manually when the operator swaps the pen. Lets the operator track
    # wear and know when to replace a marker.
    odometer_mm: float = Field(default=0.0)
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


def _install_audit_immutability_triggers(target: Engine) -> None:
    """Install SQLite triggers that make the ``auditentry`` table append-only.

    The application code never updates or deletes audit rows, but a
    rogue debug session, a misconfigured admin tool or a future ORM
    misuse could. Triggers at the DB level make the immutability a
    hard guarantee instead of a code-review convention.

    SQLite-only by design: the production deployment ships a SQLite
    file (``omniplot.db``). If the engine is ever pointed at another
    backend the triggers are skipped — those dialects need their own
    equivalent (e.g. PostgreSQL ``RAISE EXCEPTION`` in a BEFORE trigger
    function).
    """
    if target.dialect.name != "sqlite":
        return
    inspector = inspect(target)
    if not inspector.has_table("auditentry"):
        return
    with target.begin() as conn:
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS auditentry_no_update "
                "BEFORE UPDATE ON auditentry BEGIN "
                "SELECT RAISE(ABORT, 'audit log is append-only'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS auditentry_no_delete "
                "BEFORE DELETE ON auditentry BEGIN "
                "SELECT RAISE(ABORT, 'audit log is append-only'); END"
            )
        )


def init_db(target: Engine = engine) -> None:
    """Create the database directory and tables, then apply additive migrations.

    Args:
        target: The engine to initialize.
    """
    if target.url.database and target.url.database != ":memory:":
        Path(target.url.database).parent.mkdir(parents=True, exist_ok=True)
    # Ensure the IR cache table is registered on SQLModel.metadata
    # before create_all runs. Importing here (rather than at module
    # top) avoids a circular import with ``application.ir_cache``,
    # which itself imports the engine from this module.
    import pen_plotter.application.ir_cache  # noqa: F401

    SQLModel.metadata.create_all(target)
    _add_missing_columns(target)
    _install_audit_immutability_triggers(target)


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


def save_plan_snapshot(
    resolved: ResolvedPlan, target: Engine = engine
) -> PlanSnapshotRecord:
    """Persist a resolved plan; idempotent on ``plan_hash``.

    Best-effort by design: a DB failure should not prevent the
    generated G-code from being returned, so callers are expected to
    log + swallow exceptions rather than propagating them.
    """
    record = PlanSnapshotRecord(
        plan_hash=resolved.plan_hash,
        profile_name=resolved.profile_name,
        layer_count=len(resolved.layers),
        created_at=datetime.now(UTC),
        plan_json=resolved.model_dump_json(),
    )
    try:
        with Session(target) as session:
            session.merge(record)
            session.commit()
    except Exception:  # pragma: no cover — diagnostics, never fatal
        _log.exception("Failed to persist plan snapshot %s", resolved.plan_hash)
    return record


def get_plan_snapshot(
    plan_hash: str, target: Engine = engine
) -> PlanSnapshotRecord | None:
    """Return a stored snapshot by its hash, or ``None``."""
    with Session(target) as session:
        return session.get(PlanSnapshotRecord, plan_hash)


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


# ---------------------------------------------------------------- available colours


def list_available_colors(target: Engine = engine) -> list[AvailableColorRecord]:
    """Return every available-colour entry in display order.

    Args:
        target: The engine to read from.

    Returns:
        Records ordered by ``position`` ascending, ties broken by
        ``created_at`` so a freshly-inserted row stays at the end of
        the strip rather than jumping above a sibling with the same
        position.
    """
    with Session(target) as session:
        statement = select(AvailableColorRecord).order_by(
            AvailableColorRecord.position,
            AvailableColorRecord.created_at,
        )
        return list(session.exec(statement).all())


def get_available_color(
    color_id: str, target: Engine = engine
) -> AvailableColorRecord | None:
    """Return one entry by id, or ``None`` if it doesn't exist."""
    with Session(target) as session:
        return session.get(AvailableColorRecord, color_id)


def get_available_color_by_hex(
    hex_value: str, target: Engine = engine
) -> AvailableColorRecord | None:
    """Return the (at most one) entry matching this hex, lookup helper for dedup."""
    with Session(target) as session:
        statement = select(AvailableColorRecord).where(
            AvailableColorRecord.hex == hex_value
        )
        return session.exec(statement).first()


def save_available_color(
    record: AvailableColorRecord, target: Engine = engine
) -> AvailableColorRecord:
    """Insert or update an available-colour entry.

    Uses ``session.merge`` so the same call works for both create and
    update — the API adapter picks which path applies based on whether
    the ``color_id`` already exists.
    """
    with Session(target) as session:
        session.merge(record)
        session.commit()
    return record


def delete_available_color(color_id: str, target: Engine = engine) -> bool:
    """Remove one entry by id. Returns ``True`` if a row was deleted.

    Args:
        color_id: The identifier of the entry to drop.
        target: The engine to write to.

    Returns:
        ``True`` if the row existed and was removed, ``False`` if the
        id was already absent (so the endpoint can map to 404).
    """
    with Session(target) as session:
        record = session.get(AvailableColorRecord, color_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True


def next_available_color_position(target: Engine = engine) -> int:
    """Return ``max(position) + 1`` so new entries land at the end of the strip.

    Returns ``0`` when the table is empty so the first inserted row
    starts at position 0.
    """
    with Session(target) as session:
        statement = select(AvailableColorRecord).order_by(
            desc(AvailableColorRecord.position)
        )
        last = session.exec(statement).first()
        return 0 if last is None else last.position + 1


# ---------------------------------------------------------------- app settings


def get_setting(key: str, target: Engine = engine) -> str | None:
    """Return the raw string value of a setting, or ``None`` when unset."""
    with Session(target) as session:
        record = session.get(AppSettingRecord, key)
        return None if record is None else record.value


def set_setting(key: str, value: str, target: Engine = engine) -> None:
    """Upsert a setting. ``value`` is stored as-is; callers JSON-encode if needed."""
    with Session(target) as session:
        session.merge(AppSettingRecord(key=key, value=value))
        session.commit()
