"""Camera timelapse recorder + MP4 export.

Grabs JPEG frames from a camera's MJPEG/HTTP stream at a fixed interval
while recording, stores them on disk, and assembles them into a
downloadable H.264 MP4 with ffmpeg on stop.

The camera URL lives client-side (the SPA keeps it in localStorage), so
the frontend hands it to ``start`` — the backend, free of CORS, does the
grabbing. Frame grabbing and video assembly are injected so the recorder
is testable without a real camera or ffmpeg.

Storage layout (one directory per timelapse)::

    <TIMELAPSE_DIR>/<id>/frames/frame_000000.jpg ...
    <TIMELAPSE_DIR>/<id>/video.mp4
    <TIMELAPSE_DIR>/<id>/meta.json
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_log = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "timelapses"
TIMELAPSE_DIR = Path(os.environ.get("OMNIPLOT_TIMELAPSE_DIR", _DEFAULT_DIR))

# Guards: cap a single grabbed frame, the grab timeout, and the bounds the
# API also validates so the recorder is safe even if called directly.
_MAX_FRAME_BYTES = 8 * 1024 * 1024
_FRAME_GRAB_TIMEOUT_S = 5.0
MIN_INTERVAL_S = 0.5
MAX_INTERVAL_S = 3600.0
MIN_FPS = 1
MAX_FPS = 60
_ASSEMBLE_TIMEOUT_S = 600.0
# Backstop against a forgotten recording filling the SD card: stop
# capturing past this many frames (the operator still stops to save).
_MAX_FRAMES = 100_000

JpegGrabber = Callable[[str], bytes]
VideoAssembler = Callable[[Path, Path, int], None]


def grab_jpeg(url: str, timeout: float = _FRAME_GRAB_TIMEOUT_S) -> bytes:
    """Fetch one JPEG frame from a snapshot or MJPEG stream URL.

    Handles both a single-image snapshot endpoint (``Content-Type:
    image/jpeg``) and an ``multipart/x-mixed-replace`` MJPEG stream, from
    which the first complete JPEG frame (SOI…EOI) is extracted.

    Raises:
        RuntimeError: On a non-http(s) URL or when no JPEG frame is found.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise RuntimeError("Camera URL must be an http(s) stream.")
    req = urllib.request.Request(url, headers={"User-Agent": "omniplot-timelapse"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
        if resp.headers.get_content_type() == "image/jpeg":
            return bytes(resp.read(_MAX_FRAME_BYTES))
        # MJPEG (or unknown): read until one full JPEG frame is buffered.
        buf = b""
        while len(buf) < _MAX_FRAME_BYTES:
            chunk: bytes = resp.read(16384)
            if not chunk:
                break
            buf += chunk
            start = buf.find(b"\xff\xd8")
            if start != -1:
                end = buf.find(b"\xff\xd9", start + 2)
                if end != -1:
                    return buf[start : end + 2]
    raise RuntimeError(f"No JPEG frame received from {url!r}")


def assemble_video(frames_dir: Path, out_path: Path, fps: int) -> None:
    """Assemble contiguous ``frame_%06d.jpg`` files into an H.264 MP4.

    Raises:
        RuntimeError: If ffmpeg is unavailable or the encode fails.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed; cannot assemble the timelapse video.")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%06d.jpg"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=_ASSEMBLE_TIMEOUT_S)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", "replace")[-500:] if exc.stderr else ""
        raise RuntimeError(f"ffmpeg failed: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg timed out assembling the timelapse.") from exc


@dataclass
class _Session:
    """The currently-recording timelapse."""

    id: str
    stream_url: str
    interval_seconds: float
    fps: int
    label: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    frame_count: int = 0


def _read_meta(directory: Path) -> dict[str, Any] | None:
    meta_path = directory / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class TimelapseRecorder:
    """Manages a single timelapse recording and the saved-timelapse store."""

    def __init__(
        self,
        base_dir: Path | None = None,
        grabber: JpegGrabber = grab_jpeg,
        assembler: VideoAssembler = assemble_video,
    ) -> None:
        """Create a recorder. ``base_dir`` defaults to ``TIMELAPSE_DIR``."""
        self._base_dir = base_dir or TIMELAPSE_DIR
        self._grabber = grabber
        self._assembler = assembler
        self._task: asyncio.Task[None] | None = None
        self._session: _Session | None = None
        self._error: str | None = None

    @property
    def recording(self) -> bool:
        """Whether a capture loop is currently running."""
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        """A snapshot of the active recording (or the idle state)."""
        s = self._session
        return {
            "recording": self.recording,
            "session_id": s.id if s else None,
            "label": s.label if s else "",
            "frame_count": s.frame_count if s else 0,
            "interval_seconds": s.interval_seconds if s else 0.0,
            "fps": s.fps if s else 0,
            "started_at": s.started_at.isoformat() if s else None,
            "error": self._error,
        }

    async def start(
        self, stream_url: str, interval_seconds: float, fps: int, label: str = ""
    ) -> dict[str, Any]:
        """Begin capturing frames from ``stream_url`` every ``interval_seconds``.

        Raises:
            RuntimeError: If a recording is already in progress.
        """
        if self.recording:
            raise RuntimeError("A timelapse is already recording.")
        interval_seconds = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, interval_seconds))
        fps = max(MIN_FPS, min(MAX_FPS, fps))
        session_id = uuid4().hex
        (self._base_dir / session_id / "frames").mkdir(parents=True, exist_ok=True)
        self._session = _Session(
            id=session_id,
            stream_url=stream_url,
            interval_seconds=interval_seconds,
            fps=fps,
            label=label.strip(),
        )
        self._error = None
        self._task = asyncio.create_task(self._loop(self._session))
        return self.status()

    async def _loop(self, session: _Session) -> None:
        """Capture a frame every ``interval`` until cancelled."""
        frames_dir = self._base_dir / session.id / "frames"
        while True:
            if session.frame_count >= _MAX_FRAMES:
                self._error = f"Frame limit ({_MAX_FRAMES}) reached — stop to save."
                await asyncio.sleep(session.interval_seconds)
                continue
            try:
                frame = await asyncio.to_thread(self._grabber, session.stream_url)
            except Exception as exc:  # a transient grab failure must not kill the loop
                self._error = str(exc)
                _log.warning("Timelapse frame grab failed: %s", exc)
            else:
                # Contiguous numbering (only on success) keeps ffmpeg's
                # ``%06d`` input pattern gap-free.
                (frames_dir / f"frame_{session.frame_count:06d}.jpg").write_bytes(frame)
                session.frame_count += 1
                self._error = None
            await asyncio.sleep(session.interval_seconds)

    async def stop(self) -> dict[str, Any]:
        """Stop recording, assemble the MP4, and return the saved summary.

        Raises:
            RuntimeError: If no recording is in progress.
        """
        session = self._session
        if session is None or self._task is None:
            raise RuntimeError("No timelapse is recording.")
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._session = None

        directory = self._base_dir / session.id
        duration = round(session.frame_count / session.fps, 2) if session.fps else 0.0
        has_video = False
        if session.frame_count > 0:
            try:
                await asyncio.to_thread(
                    self._assembler, directory / "frames", directory / "video.mp4", session.fps
                )
                has_video = True
            except Exception as exc:
                self._error = str(exc)
                _log.error("Timelapse assembly failed: %s", exc)
        else:
            self._error = "No frames were captured."

        video = directory / "video.mp4"
        meta: dict[str, Any] = {
            "id": session.id,
            "label": session.label,
            "created_at": session.started_at.isoformat(),
            "interval_seconds": session.interval_seconds,
            "fps": session.fps,
            "frame_count": session.frame_count,
            "duration_seconds": duration,
            "has_video": has_video,
            "size_bytes": video.stat().st_size if has_video and video.is_file() else 0,
        }
        (directory / "meta.json").write_text(json.dumps(meta), "utf-8")
        return meta

    def list(self) -> list[dict[str, Any]]:
        """All saved timelapses, newest first."""
        if not self._base_dir.is_dir():
            return []
        items = [m for d in self._base_dir.iterdir() if d.is_dir() and (m := _read_meta(d))]
        items.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
        return items

    def get(self, timelapse_id: str) -> dict[str, Any] | None:
        """One saved timelapse's metadata, or ``None``."""
        return _read_meta(self._base_dir / timelapse_id)

    def video_path(self, timelapse_id: str) -> Path | None:
        """Path to a timelapse's MP4 if it exists, else ``None``."""
        video = self._base_dir / timelapse_id / "video.mp4"
        return video if video.is_file() else None

    def delete(self, timelapse_id: str) -> bool:
        """Delete a saved timelapse (cannot delete the active recording)."""
        if self._session is not None and self._session.id == timelapse_id:
            return False
        directory = self._base_dir / timelapse_id
        if not directory.is_dir():
            return False
        shutil.rmtree(directory, ignore_errors=True)
        return True


recorder = TimelapseRecorder()
