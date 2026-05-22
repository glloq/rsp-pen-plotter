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
