import pytest
from sqlalchemy import inspect, text
from sqlmodel import create_engine

from pen_plotter import queue  # noqa: F401  (registers the PrintRun table)
from pen_plotter.persistence import init_db
from pen_plotter.queue import enqueue, get_run

_OLD_PRINTRUN = (
    "CREATE TABLE printrun ("
    "id VARCHAR PRIMARY KEY, name VARCHAR, profile_name VARCHAR, gcode VARCHAR, "
    "total_lines INTEGER, acked_lines INTEGER, state VARCHAR, priority INTEGER, "
    "error VARCHAR, created_at DATETIME, updated_at DATETIME)"
)


def test_init_db_adds_missing_columns_to_existing_table() -> None:
    engine = create_engine("sqlite://")
    # Simulate a database created before pause_points / idempotency_key existed.
    with engine.begin() as conn:
        conn.execute(text(_OLD_PRINTRUN))

    init_db(engine)

    columns = {col["name"] for col in inspect(engine).get_columns("printrun")}
    assert "pause_points" in columns
    assert "idempotency_key" in columns


def test_migrated_table_is_usable() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_PRINTRUN))
    init_db(engine)

    run = enqueue("job", "Custom CoreXY A3", "G0 X1\n", idempotency_key="k1", target=engine)
    assert get_run(run.id, engine) is not None


# An AvailableColorRecord table from before stroke_width_mm / odometer_mm
# existed. The audit's core P0.2 case: additive migration must back-fill the
# declared defaults, not leave old rows NULL.
_OLD_AVAILABLE_COLOR = (
    "CREATE TABLE availablecolorrecord ("
    "color_id VARCHAR PRIMARY KEY, hex VARCHAR, name VARCHAR, "
    "position INTEGER, created_at DATETIME)"
)


def test_added_columns_are_backfilled_to_declared_defaults() -> None:
    from pen_plotter.persistence import get_available_color

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_AVAILABLE_COLOR))
        conn.execute(
            text(
                "INSERT INTO availablecolorrecord (color_id, hex, name, position, created_at) "
                "VALUES ('c1', '#ff0000', 'Red', 0, '2026-01-01 00:00:00')"
            )
        )

    init_db(engine)

    row = get_available_color("c1", engine)
    assert row is not None
    # Pre-existing data is preserved…
    assert row.hex == "#ff0000"
    assert row.name == "Red"
    # …and the newly-added columns are the model defaults, NOT NULL.
    assert row.stroke_width_mm == 0.5
    assert row.odometer_mm == 0.0


def test_no_unexpected_nulls_after_migration() -> None:
    """No back-filled scalar column should read back NULL for an old row."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_AVAILABLE_COLOR))
        conn.execute(
            text(
                "INSERT INTO availablecolorrecord (color_id, hex, name, position, created_at) "
                "VALUES ('c1', '#00ff00', 'Green', 0, '2026-01-01 00:00:00')"
            )
        )
    init_db(engine)

    with engine.begin() as conn:
        nulls = conn.execute(
            text(
                "SELECT COUNT(*) FROM availablecolorrecord "
                "WHERE stroke_width_mm IS NULL OR odometer_mm IS NULL"
            )
        ).scalar_one()
    assert nulls == 0


def test_idempotency_unique_index_created_on_old_printrun() -> None:
    """The unique index behind atomic enqueue dedup (P1.2) is added to a
    PrintRun table that predates it, so the constraint becomes retroactive."""
    import uuid

    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session

    from pen_plotter.queue import PrintRun

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_PRINTRUN))
    init_db(engine)

    enqueue("a", "Custom CoreXY A3", "G0 X1\n", idempotency_key="dup", target=engine)
    # A second row with the same key must now be rejected by the migrated index.
    with Session(engine) as session:
        session.add(
            PrintRun(
                id=str(uuid.uuid4()),
                name="b",
                profile_name="Custom CoreXY A3",
                gcode="G0 X1\n",
                total_lines=1,
                idempotency_key="dup",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_duplicate_idempotency_keys_are_repaired_then_index_created() -> None:
    """An old table with duplicate idempotency keys must be repaired (earliest
    row keeps the key, the rest NULLed) so the unique index — and atomic
    enqueue — can be established rather than silently skipped (P1.5)."""
    from sqlalchemy.exc import IntegrityError

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_PRINTRUN))
        conn.execute(text("ALTER TABLE printrun ADD COLUMN idempotency_key VARCHAR"))
        for rid, created in (("r1", "2026-01-01"), ("r2", "2026-02-01")):
            conn.execute(
                text(
                    "INSERT INTO printrun (id, name, profile_name, gcode, total_lines, "
                    "acked_lines, state, priority, created_at, updated_at, idempotency_key) "
                    f"VALUES ('{rid}', 'j', 'p', 'g', 1, 0, 'queued', 0, "
                    f"'{created}', '{created}', 'same')"
                )
            )

    init_db(engine)  # repairs the duplicate, then builds the unique index

    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM printrun")).scalar_one()
        keyed = conn.execute(
            text("SELECT COUNT(*) FROM printrun WHERE idempotency_key = 'same'")
        ).scalar_one()
    assert count == 2  # both rows preserved
    assert keyed == 1  # exactly one keeps the key; the duplicate was NULLed

    # The unique index is now real: a fresh duplicate insert is rejected.
    from sqlmodel import Session

    from pen_plotter.queue import PrintRun

    with Session(engine) as session:
        session.add(
            PrintRun(
                id="r3",
                name="j",
                profile_name="p",
                gcode="g",
                total_lines=1,
                idempotency_key="same",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_non_unique_index_is_upgraded_to_unique() -> None:
    """A same-named but non-unique idempotency_key index from an intermediate
    version must be replaced with the unique one (P1.5)."""
    from sqlalchemy import inspect

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_OLD_PRINTRUN))
        conn.execute(text("ALTER TABLE printrun ADD COLUMN idempotency_key VARCHAR"))
        # A NON-unique index with the exact name SQLModel would generate.
        conn.execute(
            text("CREATE INDEX ix_printrun_idempotency_key ON printrun (idempotency_key)")
        )

    init_db(engine)

    indexes = {
        ix["name"]: ix for ix in inspect(engine).get_indexes("printrun")
    }
    assert bool(indexes["ix_printrun_idempotency_key"]["unique"]) is True
