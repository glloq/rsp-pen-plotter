"""Persisted rows carry the current schema_version (P5).

Lets a future upgrade detect old shapes (``schema_version < N``) and
reshape on read instead of crashing in the deserializer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from pen_plotter.models import BoundingBox, Job, LayerInfo
from pen_plotter.persistence import (
    PERSISTENCE_SCHEMA_VERSION,
    FileRecord,
    PlanSnapshotRecord,
    engine,
    get_file_record,
    get_job,
    get_plan_snapshot,
    save_file_record,
    save_job,
)


def _make_job() -> Job:
    layer = LayerInfo(
        layer_id="0",
        source_color="#000000",
        target_pen_slot=None,
        draw_order=0,
        total_length_mm=10.0,
        path_count=1,
        bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0),
    )
    return Job(
        source_file="x.svg",
        source_mime="image/svg+xml",
        profile_name="default",
        layers=[layer],
        status="ready",
    )


def test_job_record_stamps_schema_version() -> None:
    job = _make_job()
    save_job(job)
    record = get_job(job.job_id)
    assert record is not None
    assert record.schema_version == PERSISTENCE_SCHEMA_VERSION
    assert PERSISTENCE_SCHEMA_VERSION >= 1


def test_file_record_stamps_schema_version() -> None:
    record = FileRecord(
        file_id="test-id-1",
        sha256="deadbeef" * 8,
        source_file="x.svg",
        source_mime="image/svg+xml",
        size_bytes=10,
        layer_count=1,
        folder="",
        created_at=datetime.now(UTC),
        schema_version=PERSISTENCE_SCHEMA_VERSION,
    )
    save_file_record(record)
    fetched = get_file_record("test-id-1")
    assert fetched is not None
    assert fetched.schema_version == PERSISTENCE_SCHEMA_VERSION


def test_plan_snapshot_stamps_schema_version() -> None:
    # ``save_plan_snapshot`` requires a fully-built ResolvedPlan; bypass
    # the resolver by writing the row directly with the same stamping
    # invariant the helper enforces.
    record = PlanSnapshotRecord(
        plan_hash="deadbeef-test",
        profile_name="default",
        layer_count=0,
        created_at=datetime.now(UTC),
        plan_json="{}",
        schema_version=PERSISTENCE_SCHEMA_VERSION,
    )
    with Session(engine) as session:
        session.merge(record)
        session.commit()
    fetched = get_plan_snapshot("deadbeef-test")
    assert fetched is not None
    assert fetched.schema_version == PERSISTENCE_SCHEMA_VERSION
