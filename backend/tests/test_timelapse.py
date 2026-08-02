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
    assert await recorder.delete(sid) is False  # cannot delete the active recording
    await recorder.stop()
    assert await recorder.delete(sid) is True
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


class TestCameraUrlSsrfGuard:
    """SSRF guard on operator-supplied camera URLs (P0.4).

    Uses literal IPs so ``socket.getaddrinfo`` resolves numerically with no
    live DNS, keeping the suite offline.
    """

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("file:///etc/passwd")

    def test_blocks_loopback(self) -> None:
        # An attacker could otherwise hit the appliance's own admin/update API.
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://127.0.0.1:8000/plotter/update")

    def test_blocks_cloud_metadata_endpoint(self) -> None:
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://169.254.169.254/latest/meta-data/")

    def test_allows_private_lan_camera_by_default(self) -> None:
        # Real cameras live on the LAN; private ranges stay reachable.
        tl.validate_camera_url("http://192.168.1.50/stream")

    def test_allowlist_permits_only_listed_hosts(self, monkeypatch) -> None:
        monkeypatch.setenv("OMNIPLOT_CAMERA_HOSTS", "192.168.1.30,10.0.0.0/8")
        tl.validate_camera_url("http://192.168.1.30/stream")  # exact host
        tl.validate_camera_url("http://10.4.5.6/stream")  # inside the CIDR
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://192.168.1.31/stream")  # off the list

    def test_allowlist_still_blocks_unlisted_loopback(self, monkeypatch) -> None:
        monkeypatch.setenv("OMNIPLOT_CAMERA_HOSTS", "192.168.1.30")
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://127.0.0.1/stream")

    def test_redirect_handler_revalidates_target(self) -> None:
        # An open redirect on an allowed host must not bounce to loopback.
        handler = tl._ValidatingRedirectHandler()
        assert handler.max_redirections <= 3
        with pytest.raises(tl.CameraUrlError):
            handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/x")

    def test_grab_jpeg_refuses_blocked_target_without_fetching(self) -> None:
        # The guard fires before any socket is opened.
        with pytest.raises(tl.CameraUrlError):
            tl.grab_jpeg("http://127.0.0.1:8000/stream")


class TestTimelapseStorageGuards:
    """Disk-saturation backstops on the capture loop (P0.5)."""

    def test_free_space_below_reserve_blocks_capture(
        self, recorder: tl.TimelapseRecorder, monkeypatch
    ) -> None:
        # Pretend the disk is almost full → capture must pause, not write.
        monkeypatch.setenv("OMNIPLOT_MIN_FREE_MB", "1024")
        monkeypatch.setattr(tl, "_free_bytes", lambda _p: 10 * 1024 * 1024)
        session = tl._Session(
            id="s", stream_url="http://cam/x", interval_seconds=0.5, fps=12, label=""
        )
        reason = recorder._capacity_block_reason(session)
        assert reason is not None
        assert "disk space" in reason.lower()

    def test_timelapse_quota_blocks_capture(
        self, recorder: tl.TimelapseRecorder, monkeypatch
    ) -> None:
        monkeypatch.setenv("OMNIPLOT_TIMELAPSE_MAX_MB", "1")
        monkeypatch.setattr(tl, "_free_bytes", lambda _p: 100 * 1024 * 1024 * 1024)
        session = tl._Session(
            id="s", stream_url="http://cam/x", interval_seconds=0.5, fps=12, label=""
        )
        session.bytes_written = 2 * 1024 * 1024  # over the 1 MB quota
        reason = recorder._capacity_block_reason(session)
        assert reason is not None
        assert "quota" in reason.lower()

    def test_capacity_allows_capture_with_headroom(
        self, recorder: tl.TimelapseRecorder, monkeypatch
    ) -> None:
        monkeypatch.setattr(tl, "_free_bytes", lambda _p: 100 * 1024 * 1024 * 1024)
        session = tl._Session(
            id="s", stream_url="http://cam/x", interval_seconds=0.5, fps=12, label=""
        )
        assert recorder._capacity_block_reason(session) is None

    def test_disabled_reserve_never_blocks(
        self, recorder: tl.TimelapseRecorder, monkeypatch
    ) -> None:
        # A zero budget disables the guard even on a nearly-full disk.
        monkeypatch.setenv("OMNIPLOT_MIN_FREE_MB", "0")
        monkeypatch.setenv("OMNIPLOT_TIMELAPSE_MAX_MB", "0")
        monkeypatch.setattr(tl, "_free_bytes", lambda _p: 1)
        session = tl._Session(
            id="s", stream_url="http://cam/x", interval_seconds=0.5, fps=12, label=""
        )
        session.bytes_written = 10**12
        assert recorder._capacity_block_reason(session) is None

    @pytest.mark.asyncio
    async def test_loop_stops_writing_when_disk_full(
        self, recorder: tl.TimelapseRecorder, monkeypatch
    ) -> None:
        monkeypatch.setattr(tl, "_free_bytes", lambda _p: 1)  # always "full"
        await recorder.start("http://cam/stream", interval_seconds=0.01, fps=12)
        await asyncio.sleep(0.1)
        status = recorder.status()
        assert status["frame_count"] == 0  # nothing written
        assert "disk space" in (status["error"] or "").lower()
        await recorder.stop()


class TestTimelapseIdConfinement:
    """Timelapse ids from the URL must never escape TIMELAPSE_DIR (P0.1)."""

    @pytest.mark.parametrize(
        "bad_id",
        [
            "..",
            "../files",
            "%2e%2e",
            "%2e%2e%2f",
            "/absolute/path",
            "a" * 31,  # too short
            "a" * 33,  # too long
            "A" * 32,  # uppercase — uuid4().hex is lowercase
            "g" * 32,  # non-hex
            "../../etc/passwd",
        ],
    )
    @pytest.mark.asyncio
    async def test_bad_id_is_rejected(self, recorder: tl.TimelapseRecorder, bad_id: str) -> None:
        assert recorder._session_dir(bad_id) is None
        assert recorder.get(bad_id) is None
        assert recorder.video_path(bad_id) is None
        assert await recorder.delete(bad_id) is False

    def test_valid_hex_id_is_accepted(self, recorder: tl.TimelapseRecorder) -> None:
        good = "0123456789abcdef0123456789abcdef"
        resolved = recorder._session_dir(good)
        assert resolved is not None
        assert resolved.parent == recorder._base_dir.resolve()

    @pytest.mark.asyncio
    async def test_traversal_delete_does_not_escape_base(
        self, recorder: tl.TimelapseRecorder, tmp_path
    ) -> None:
        # A sensitive file living beside the timelapse dir must survive a
        # delete() that tries to climb out with "..".
        victim = recorder._base_dir.parent / "victim.txt"
        victim.write_text("keep me", encoding="utf-8")
        assert await recorder.delete("..") is False
        assert await recorder.delete("%2e%2e") is False
        assert victim.exists()


class TestCameraAllowlistPorts:
    """Port-pinned camera allowlist entries (P1.7)."""

    def test_port_pin_matches_only_that_port(self, monkeypatch) -> None:
        monkeypatch.setenv("OMNIPLOT_CAMERA_HOSTS", "192.168.1.30:8080")
        tl.validate_camera_url("http://192.168.1.30:8080/stream")  # exact port
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://192.168.1.30:9000/stream")  # wrong port
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://192.168.1.30/stream")  # default 80 ≠ 8080

    def test_cidr_with_port(self, monkeypatch) -> None:
        monkeypatch.setenv("OMNIPLOT_CAMERA_HOSTS", "192.168.1.0/24:80")
        tl.validate_camera_url("http://192.168.1.5/stream")  # port 80 in the CIDR
        with pytest.raises(tl.CameraUrlError):
            tl.validate_camera_url("http://192.168.1.5:8080/stream")  # wrong port

    def test_entry_without_port_matches_any_port(self, monkeypatch) -> None:
        # Backward compatible: a host with no :port still allows every port.
        monkeypatch.setenv("OMNIPLOT_CAMERA_HOSTS", "192.168.1.30")
        tl.validate_camera_url("http://192.168.1.30:8080/stream")
        tl.validate_camera_url("http://192.168.1.30/stream")


@pytest.mark.asyncio
async def test_assembly_skipped_when_no_space_for_video(
    recorder: tl.TimelapseRecorder, monkeypatch
) -> None:
    """stop() must not run ffmpeg when the video wouldn't fit under the
    reserve — the frames are kept and an error is surfaced (P1.3)."""
    await recorder.start("http://cam/stream", interval_seconds=0.01, fps=12)
    await _await_first_frame(recorder)
    # Simulate a nearly-full disk only for the assembly space check.
    monkeypatch.setattr(tl, "_free_bytes", lambda _p: 1)
    summary = await recorder.stop()
    assert summary["has_video"] is False
    assert summary["frame_count"] >= 1  # frames were kept, not lost
    assert "disk space" in (recorder.status()["error"] or "").lower()


def test_cleanup_orphan_sessions_removes_metaless_dirs(recorder: tl.TimelapseRecorder) -> None:
    """A crashed recording (frames but no meta.json) is reclaimed at startup;
    a finished session (with meta.json) is kept (P1.4)."""
    base = recorder._base_dir
    # Orphan: frames, no meta.json.
    orphan = base / ("0" * 32)
    (orphan / "frames").mkdir(parents=True)
    (orphan / "frames" / "frame_000000.jpg").write_bytes(b"x")
    # Finished: has meta.json.
    good = base / ("1" * 32)
    good.mkdir()
    (good / "meta.json").write_text("{}", encoding="utf-8")

    removed = recorder.cleanup_orphan_sessions()
    assert removed == 1
    assert not orphan.exists()
    assert good.exists()


@pytest.mark.asyncio
async def test_concurrent_start_creates_a_single_session(recorder: tl.TimelapseRecorder) -> None:
    """Two start() calls racing must yield exactly one recording, not two
    capture loops with an orphaned task (P0.1)."""
    results = await asyncio.gather(
        recorder.start("http://cam/a", 0.5, 12),
        recorder.start("http://cam/b", 0.5, 12),
        return_exceptions=True,
    )
    started = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, RuntimeError)]
    assert len(started) == 1
    assert len(refused) == 1
    assert recorder.recording
    session_dirs = [d for d in recorder._base_dir.iterdir() if d.is_dir()]
    assert len(session_dirs) == 1
    await recorder.stop()
