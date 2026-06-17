"""Tests for the camera timelapse recorder + /timelapse endpoints.

Frame grabbing and ffmpeg assembly are faked so the suite needs neither a
camera nor ffmpeg; one ``skipif`` test exercises the real ffmpeg path when
it's installed (it is in production via install.sh).
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from PIL import Image

from pen_plotter import timelapse as tl
from pen_plotter.main import app


def _fake_jpeg(_url: str) -> bytes:
    return b"\xff\xd8\xff\xd9"  # minimal SOI + EOI


def _fake_assemble(_frames_dir: Path, out_path: Path, _fps: int) -> None:
    out_path.write_bytes(b"FAKE-MP4-DATA")


async def _await_first_frame(rec: tl.TimelapseRecorder) -> None:
    for _ in range(100):
        if rec.status()["frame_count"] >= 1:
            return
        await asyncio.sleep(0.02)


@pytest.fixture
def recorder(tmp_path: Path) -> tl.TimelapseRecorder:
    return tl.TimelapseRecorder(base_dir=tmp_path, grabber=_fake_jpeg, assembler=_fake_assemble)


@pytest.mark.asyncio
async def test_record_capture_and_assemble(recorder: tl.TimelapseRecorder) -> None:
    await recorder.start("http://cam/stream", interval_seconds=0.5, fps=12, label="run")
    assert recorder.recording
    await _await_first_frame(recorder)
    summary = await recorder.stop()

    assert not recorder.recording
    assert summary["frame_count"] >= 1
    assert summary["has_video"] is True
    assert summary["fps"] == 12
    assert summary["label"] == "run"
    assert [m["id"] for m in recorder.list()] == [summary["id"]]
    assert recorder.video_path(summary["id"]) is not None


@pytest.mark.asyncio
async def test_start_while_recording_raises(recorder: tl.TimelapseRecorder) -> None:
    await recorder.start("http://cam/stream", 0.5, 12)
    with pytest.raises(RuntimeError):
        await recorder.start("http://cam/stream", 0.5, 12)
    await recorder.stop()


@pytest.mark.asyncio
async def test_stop_without_recording_raises(recorder: tl.TimelapseRecorder) -> None:
    with pytest.raises(RuntimeError):
        await recorder.stop()


@pytest.mark.asyncio
async def test_delete_guards_active_then_removes(recorder: tl.TimelapseRecorder) -> None:
    await recorder.start("http://cam/stream", 0.5, 12)
    sid = recorder.status()["session_id"]
    assert recorder.delete(sid) is False  # cannot delete the active recording
    await recorder.stop()
    assert recorder.delete(sid) is True
    assert recorder.get(sid) is None


def test_grab_jpeg_rejects_non_http() -> None:
    with pytest.raises(RuntimeError):
        tl.grab_jpeg("file:///etc/passwd")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_assemble_video_real_ffmpeg(tmp_path: Path) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(3):
        Image.new("RGB", (32, 24), (i * 40, 0, 0)).save(frames / f"frame_{i:06d}.jpg")
    out = tmp_path / "video.mp4"
    tl.assemble_video(frames, out, fps=12)
    assert out.is_file() and out.stat().st_size > 0


# --- API ---------------------------------------------------------------


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def api_recorder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the shared recorder at a tmp dir with fakes; reset afterwards."""
    monkeypatch.setattr(tl.recorder, "_base_dir", tmp_path)
    monkeypatch.setattr(tl.recorder, "_grabber", _fake_jpeg)
    monkeypatch.setattr(tl.recorder, "_assembler", _fake_assemble)
    yield
    if tl.recorder.recording and tl.recorder._task is not None:
        tl.recorder._task.cancel()
    tl.recorder._task = None
    tl.recorder._session = None
    tl.recorder._error = None


@pytest.mark.asyncio
async def test_timelapse_api_lifecycle(api_recorder: None) -> None:
    async with _client() as client:
        assert (await client.get("/timelapse/status")).json()["recording"] is False

        started = await client.post(
            "/timelapse/start",
            json={"stream_url": "http://cam/stream", "interval_seconds": 0.5, "fps": 10},
        )
        assert started.status_code == 200, started.text
        assert started.json()["recording"] is True

        await _await_first_frame(tl.recorder)

        stopped = await client.post("/timelapse/stop")
        assert stopped.status_code == 200, stopped.text
        body = stopped.json()
        tid = body["id"]
        assert body["has_video"] is True

        listing = await client.get("/timelapse")
        assert tid in [m["id"] for m in listing.json()]

        video = await client.get(f"/timelapse/{tid}/video")
        assert video.status_code == 200
        assert video.headers["content-type"] == "video/mp4"

        assert (await client.delete(f"/timelapse/{tid}")).status_code == 200
        assert (await client.delete(f"/timelapse/{tid}")).status_code == 404


@pytest.mark.asyncio
async def test_timelapse_api_validation(api_recorder: None) -> None:
    async with _client() as client:
        bad = await client.post("/timelapse/start", json={"stream_url": "ftp://nope"})
        assert bad.status_code == 422
        assert (await client.post("/timelapse/stop")).status_code == 409
