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
