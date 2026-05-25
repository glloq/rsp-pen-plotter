from sqlmodel import create_engine

from pen_plotter.audit import list_entries, record
from pen_plotter.persistence import init_db


def _engine():
    engine = create_engine("sqlite://")
    init_db(engine)
    return engine


def test_record_and_list_newest_first() -> None:
    engine = _engine()
    record("plotter.run", "5 lines", target=engine)
    record("queue.cancel", "run-1", target=engine)
    entries = list_entries(target=engine)
    assert [e.action for e in entries] == ["queue.cancel", "plotter.run"]
    assert entries[0].detail == "run-1"


def test_list_respects_limit() -> None:
    engine = _engine()
    for i in range(5):
        record("plotter.home", str(i), target=engine)
    assert len(list_entries(limit=3, target=engine)) == 3


def test_audit_table_rejects_updates_at_the_db_level() -> None:
    """Triggers must abort any UPDATE so a rogue admin tool / debug
    session cannot rewrite history. The application code never UPDATEs
    audit rows; this lock at the SQLite level turns that convention
    into a hard guarantee.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, select

    from pen_plotter.audit import AuditEntry

    engine = _engine()
    record("plotter.run", "original", target=engine)
    with Session(engine) as session:
        entry = session.exec(select(AuditEntry)).first()
        assert entry is not None
        entry.detail = "tampered"
        session.add(entry)
        try:
            session.commit()
        except IntegrityError as exc:
            assert "audit log is append-only" in str(exc)
        else:
            raise AssertionError("UPDATE should have been rejected by the trigger")


def test_audit_table_rejects_deletes_at_the_db_level() -> None:
    """Same as above for DELETE — the trail can only grow."""
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, select

    from pen_plotter.audit import AuditEntry

    engine = _engine()
    record("plotter.run", "keepme", target=engine)
    with Session(engine) as session:
        entry = session.exec(select(AuditEntry)).first()
        assert entry is not None
        session.delete(entry)
        try:
            session.commit()
        except IntegrityError as exc:
            assert "audit log is append-only" in str(exc)
        else:
            raise AssertionError("DELETE should have been rejected by the trigger")
    # Confirm the row is still there.
    assert len(list_entries(target=engine)) == 1


def test_init_db_is_idempotent_with_existing_triggers() -> None:
    """Repeated init_db (e.g. lifespan restart on the same SQLite file)
    must not raise from "trigger already exists" — the CREATE IF NOT
    EXISTS guard plus the trigger names handle that.
    """
    engine = _engine()
    # Already called init_db inside _engine; do it twice more for good
    # measure. No exception should escape.
    init_db(engine)
    init_db(engine)
    record("plotter.run", "after-restart", target=engine)
    assert len(list_entries(target=engine)) == 1
