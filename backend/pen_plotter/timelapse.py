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
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

_log = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "timelapses"
TIMELAPSE_DIR = Path(os.environ.get("OMNIPLOT_TIMELAPSE_DIR", _DEFAULT_DIR))

# Every timelapse id is ``uuid4().hex`` — 32 lowercase hex chars. Anything
# else in a request path is a traversal attempt and is refused (see P0.1).
_TIMELAPSE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

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

# Storage backstops against SD-card saturation (P0.5). A full disk corrupts
# SQLite, drops queue checkpoints and can wedge the OS, so recording halts
# well before that: capture stops when free space would fall below the reserve
# or the timelapse store grows past its byte quota. Both are env-tunable.
_MIN_FREE_MB_ENV = "OMNIPLOT_MIN_FREE_MB"
_TIMELAPSE_MAX_MB_ENV = "OMNIPLOT_TIMELAPSE_MAX_MB"
_DEFAULT_MIN_FREE_MB = 1024
_DEFAULT_TIMELAPSE_MAX_MB = 4096

JpegGrabber = Callable[[str], bytes]
VideoAssembler = Callable[[Path, Path, int], None]


def _env_mb_bytes(name: str, default_mb: int) -> int:
    """Read a megabyte budget from ``name`` (0/negative disables the cap)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default_mb * 1024 * 1024
    try:
        mb = int(float(raw))
    except ValueError:
        return default_mb * 1024 * 1024
    return max(0, mb) * 1024 * 1024


def _free_bytes(path: Path) -> int:
    """Free bytes on the filesystem holding ``path`` (0 if it can't be read)."""
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def _dir_size_bytes(path: Path) -> int:
    """Total size of the files under ``path`` (missing dir ⇒ 0)."""
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


# SSRF guard: the camera URL is operator-supplied and the backend fetches it
# server-side (no CORS), so an attacker who can set it could otherwise make the
# appliance hit its own admin/update API on loopback or a cloud metadata
# service on 169.254.169.254. ``validate_camera_url`` rejects those before any
# request and re-checks every redirect hop.
#
# Cameras normally live on the LAN (private IPs), so private ranges stay
# reachable by default — set ``OMNIPLOT_CAMERA_HOSTS`` (comma-separated hosts
# and/or CIDRs) to lock grabbing down to known cameras, the recommended mode.
_CAMERA_HOSTS_ENV = "OMNIPLOT_CAMERA_HOSTS"
_MAX_CAMERA_REDIRECTS = 3


class CameraUrlError(RuntimeError):
    """A camera URL was rejected by the SSRF guard before any request."""


def _camera_host_allowlist() -> list[str]:
    """Parse ``OMNIPLOT_CAMERA_HOSTS`` into a list of host / CIDR entries."""
    raw = os.environ.get(_CAMERA_HOSTS_ENV, "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def _resolve_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve ``host`` to every IP it maps to (all A/AAAA records)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise CameraUrlError(f"Camera host {host!r} did not resolve.") from exc
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        addr = str(info[4][0]).split("%", 1)[0]  # strip any zone id
        with contextlib.suppress(ValueError):
            ips.append(ipaddress.ip_address(addr))
    if not ips:
        raise CameraUrlError(f"Camera host {host!r} did not resolve to an IP.")
    return ips


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for addresses a camera should never legitimately live on.

    Loopback (the appliance's own services), link-local (incl. the cloud
    metadata endpoint 169.254.169.254), multicast, reserved and the
    unspecified address are all refused. Private LAN ranges are deliberately
    *not* blocked here — that's where real cameras sit — so operators who
    want a tighter boundary use the allowlist instead.
    """
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_camera_url(url: str) -> None:
    """Reject a camera URL that could be used for SSRF.

    Enforces an http(s) scheme, resolves the host, and either matches it
    against ``OMNIPLOT_CAMERA_HOSTS`` (when set) or refuses loopback /
    link-local / reserved targets. Called once per URL and again for every
    redirect hop.

    Raises:
        CameraUrlError: When the URL or its resolved address is not allowed.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise CameraUrlError("Camera URL must be an http(s) stream.")
    host = parts.hostname
    if not host:
        raise CameraUrlError("Camera URL has no host.")

    ips = _resolve_ips(host)
    allowlist = _camera_host_allowlist()
    if allowlist:
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        names: set[str] = set()
        for entry in allowlist:
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                names.add(entry.lower())
        allowed = host.lower() in names or any(ip in net for ip in ips for net in networks)
        if not allowed:
            raise CameraUrlError(
                f"Camera host {host!r} is not permitted by {_CAMERA_HOSTS_ENV}."
            )
        return

    for ip in ips:
        if _ip_is_blocked(ip):
            raise CameraUrlError(
                f"Camera host {host!r} resolves to a blocked address ({ip})."
            )


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-run the SSRF guard on each redirect target and cap the hop count.

    An open redirect on an allowed host could otherwise bounce the fetch to
    loopback or the metadata service; validating every ``Location`` closes
    that. ``max_redirections`` keeps a redirect loop from hanging the grab.
    """

    max_redirections = _MAX_CAMERA_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        """Validate ``newurl`` before letting urllib follow the redirect."""
        validate_camera_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_camera_opener = urllib.request.build_opener(_ValidatingRedirectHandler())


def grab_jpeg(url: str, timeout: float = _FRAME_GRAB_TIMEOUT_S) -> bytes:
    """Fetch one JPEG frame from a snapshot or MJPEG stream URL.

    Handles both a single-image snapshot endpoint (``Content-Type:
    image/jpeg``) and an ``multipart/x-mixed-replace`` MJPEG stream, from
    which the first complete JPEG frame (SOI…EOI) is extracted.

    The URL is checked by :func:`validate_camera_url` first (and again for
    every redirect) so it can't be used to reach the appliance's own services
    or a cloud metadata endpoint.

    Raises:
        CameraUrlError: When the URL fails the SSRF guard.
        RuntimeError: When no JPEG frame is found.
    """
    validate_camera_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "omniplot-timelapse"})
    with _camera_opener.open(req, timeout=timeout) as resp:  # noqa: S310 (guarded above)
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
    # Bytes this session has written, plus the store's size when it began, so
    # the quota guard can bound total timelapse storage without re-walking the
    # whole tree on every frame.
    bytes_written: int = 0
    store_baseline_bytes: int = 0


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
            store_baseline_bytes=_dir_size_bytes(self._base_dir),
        )
        self._error = None
        self._task = asyncio.create_task(self._loop(self._session))
        return self.status()

    def _capacity_block_reason(self, session: _Session) -> str | None:
        """Why capture must pause right now, or ``None`` when it may continue.

        Guards, in order: the frame-count backstop, the free-space reserve
        (protects the whole SD card / OS), and the timelapse byte quota. The
        first two protect against saturation that would corrupt SQLite and the
        print queue; all three keep the captured frames intact so the operator
        can still stop-to-save.
        """
        if session.frame_count >= _MAX_FRAMES:
            return f"Frame limit ({_MAX_FRAMES}) reached — stop to save."
        min_free = _env_mb_bytes(_MIN_FREE_MB_ENV, _DEFAULT_MIN_FREE_MB)
        if min_free and _free_bytes(self._base_dir) < min_free:
            return (
                f"Low disk space (< {min_free // (1024 * 1024)} MB free) — "
                "recording stopped to protect the system. Stop to save."
            )
        max_store = _env_mb_bytes(_TIMELAPSE_MAX_MB_ENV, _DEFAULT_TIMELAPSE_MAX_MB)
        if max_store and session.store_baseline_bytes + session.bytes_written >= max_store:
            return f"Timelapse quota ({max_store // (1024 * 1024)} MB) reached — stop to save."
        return None

    async def _loop(self, session: _Session) -> None:
        """Capture a frame every ``interval`` until cancelled."""
        frames_dir = self._base_dir / session.id / "frames"
        while True:
            blocked = self._capacity_block_reason(session)
            if blocked is not None:
                # Keep the session alive (frames captured so far stay saveable)
                # but stop writing so a runaway recording can't fill the disk.
                self._error = blocked
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
                session.bytes_written += len(frame)
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

    def _session_dir(self, timelapse_id: str) -> Path | None:
        """Resolve a timelapse id to its confined directory, or ``None``.

        The id comes straight from the request URL and drives an ``rmtree`` /
        file read, so it must never be able to escape ``TIMELAPSE_DIR``. Every
        real id is ``uuid4().hex`` — exactly 32 lowercase hex chars — so
        anything else (``..``, encoded separators, an absolute path) is
        rejected before any filesystem access, and the resolved path is
        re-checked to sit directly under the base dir as defence in depth.
        """
        if not _TIMELAPSE_ID_RE.fullmatch(timelapse_id):
            return None
        base = self._base_dir.resolve()
        directory = (base / timelapse_id).resolve()
        if directory.parent != base:
            return None
        return directory

    def get(self, timelapse_id: str) -> dict[str, Any] | None:
        """One saved timelapse's metadata, or ``None``."""
        directory = self._session_dir(timelapse_id)
        return None if directory is None else _read_meta(directory)

    def video_path(self, timelapse_id: str) -> Path | None:
        """Path to a timelapse's MP4 if it exists, else ``None``."""
        directory = self._session_dir(timelapse_id)
        if directory is None:
            return None
        video = directory / "video.mp4"
        return video if video.is_file() else None

    def delete(self, timelapse_id: str) -> bool:
        """Delete a saved timelapse (cannot delete the active recording)."""
        if self._session is not None and self._session.id == timelapse_id:
            return False
        directory = self._session_dir(timelapse_id)
        if directory is None or not directory.is_dir():
            return False
        shutil.rmtree(directory, ignore_errors=True)
        return True


recorder = TimelapseRecorder()
