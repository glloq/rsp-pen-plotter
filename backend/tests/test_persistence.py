import httpx
import pytest
from httpx import ASGITransport
from sqlmodel import create_engine

from pen_plotter.main import app
from pen_plotter.models import Job
from pen_plotter.persistence import get_job, init_db, list_jobs, save_job
from pen_plotter.presets import list_presets


def _engine():
    engine = create_engine("sqlite://")
    init_db(engine)
    return engine


def test_save_and_list_jobs() -> None:
    engine = _engine()
    job = Job(source_file="a.svg", source_mime="image/svg+xml", profile_name="P", status="ready")
    save_job(job, engine)
    records = list_jobs(engine)
    assert len(records) == 1
    assert records[0].source_file == "a.svg"
    assert get_job(job.job_id, engine) is not None


def test_save_is_idempotent_on_id() -> None:
    engine = _engine()
    job = Job(source_file="a.svg", source_mime="image/svg+xml", profile_name="P", status="ready")
    save_job(job, engine)
    job.status = "done"
    save_job(job, engine)
    records = list_jobs(engine)
    assert len(records) == 1
    assert records[0].status == "done"


def test_get_unknown_job_returns_none() -> None:
    assert get_job("nope", _engine()) is None


def test_presets_have_known_styles() -> None:
    names = {p.name for p in list_presets()}
    assert {"Fine line", "Halftone", "Stippling"} <= names


@pytest.mark.asyncio
async def test_jobs_and_presets_endpoints() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        presets = await client.get("/presets")
        jobs = await client.get("/jobs")
    assert presets.status_code == 200
    assert any(p["name"] == "Halftone" for p in presets.json())
    assert jobs.status_code == 200
    assert isinstance(jobs.json(), list)
