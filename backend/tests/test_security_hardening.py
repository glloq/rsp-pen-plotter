"""Anti-regression tests for the Phase 4 security hardening.

Three independent guards introduced together:

- ``OMNIPLOT_CORS_ORIGINS`` env var drives the allow-list (Vite dev
  server default), so a Pi appliance behind a LAN domain no longer
  needs a source patch.
- ``BitmapConverter._load_rgb`` refuses images whose declared
  dimensions would exceed ``MAX_PIXELS`` before any RAM is committed.
- ``_sanitize_folder`` rejects path-separator / NUL / parent-directory
  shapes on the file-library folder label — defence in depth at the
  API edge even though the label is never joined onto a filesystem
  path today.
"""

from __future__ import annotations

import importlib
import io
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport
from PIL import Image

from pen_plotter.converters.bitmap import BitmapConverter

# ---------- CORS origins ----------------------------------------------------


def _reload_main():
    """Re-import ``pen_plotter.main`` so module-level state is fresh.

    The CORS list is resolved at import time, so a test that mutates
    ``OMNIPLOT_CORS_ORIGINS`` must reload the module to observe the
    new value.
    """
    import pen_plotter.main as main_module

    return importlib.reload(main_module)


def test_cors_defaults_to_vite_dev_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_CORS_ORIGINS", raising=False)
    main_module = _reload_main()
    assert main_module._cors_origins() == ["http://localhost:5173"]


def test_cors_reads_comma_separated_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OMNIPLOT_CORS_ORIGINS",
        "https://plotter.local, https://lan.example,http://localhost:5173",
    )
    main_module = _reload_main()
    assert main_module._cors_origins() == [
        "https://plotter.local",
        "https://lan.example",
        "http://localhost:5173",
    ]


def test_cors_falls_back_when_env_is_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank / whitespace-only env var must NOT produce an empty
    allow-list (which would lock every browser out)."""
    monkeypatch.setenv("OMNIPLOT_CORS_ORIGINS", "   ")
    main_module = _reload_main()
    assert main_module._cors_origins() == ["http://localhost:5173"]


# ---------- Bitmap resolution cap -------------------------------------------


def _png_with_size(width: int, height: int) -> bytes:
    """Build a minimal valid PNG advertising the given dimensions."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_bitmap_rejects_image_beyond_max_pixels() -> None:
    """An oversized upload is refused BEFORE the pixel buffer is
    materialised, so a malicious 20 000×20 000 PNG can't OOM the Pi.
    """
    too_big = max(BitmapConverter.MAX_PIXELS + 1, 16_777_217)
    # 4097×4097 ≈ 16.78 Mpx — just over the cap.
    width = height = 4097
    assert width * height > BitmapConverter.MAX_PIXELS
    with pytest.raises(ValueError, match="too large"):
        BitmapConverter._load_rgb(_png_with_size(width, height))
    # Suppress unused-variable warnings on the bound we computed above.
    assert too_big > 0


def test_bitmap_accepts_image_at_the_cap_boundary() -> None:
    """An image right at the cap (4000×4000 = 16 Mpx) must load — the
    guard's strict ``>`` keeps the boundary case usable.
    """
    width = height = 4000
    assert width * height == BitmapConverter.MAX_PIXELS
    img = BitmapConverter._load_rgb(_png_with_size(width, height))
    assert img.size == (width, height)


# ---------- Folder name sanitisation ----------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Test client that does NOT start the lifespan — we only hit the
    /files endpoint family which has no lifespan dependencies."""
    from pen_plotter.main import app

    return TestClient(app)


@pytest.fixture
def async_client() -> httpx.AsyncClient:
    from pen_plotter.main import app

    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _png_for_upload() -> bytes:
    return _png_with_size(8, 8)


@pytest.mark.asyncio
async def test_upload_rejects_folder_with_path_separator(
    async_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    """``folder=../etc`` (and variants with slash / backslash / NUL)
    must be refused with 400. The label never reaches the filesystem
    today, but the guard makes a future refactor that DOES build a
    path safe by default.
    """
    from pen_plotter.api import files as files_module

    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    async with async_client as ac:
        for bad in ["../etc", "..\\windows", "../../root", "a/b", "a\\b", "x\x00"]:
            r = await ac.post(
                "/files",
                data={"folder": bad},
                files={"file": ("a.png", _png_for_upload(), "image/png")},
            )
            assert r.status_code == 400, (bad, r.status_code, r.text)


@pytest.mark.asyncio
async def test_upload_accepts_normal_folder_names(
    async_client: httpx.AsyncClient, tmp_path, monkeypatch
) -> None:
    """Day-to-day folder labels keep working. Strips leading/trailing
    whitespace but otherwise passes the string through.
    """
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.persistence import FileRecord, engine

    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    async with async_client as ac:
        for ok in ["sketches", "logos 2024", "  Final  ", "fr-FR"]:
            r = await ac.post(
                "/files",
                data={"folder": ok},
                files={
                    "file": (
                        f"{abs(hash(ok))}.png",
                        _png_with_size(8 + (abs(hash(ok)) % 4), 8),
                        "image/png",
                    )
                },
            )
            assert r.status_code == 200, (ok, r.status_code, r.text)


@pytest.mark.asyncio
async def test_unknown_file_id_returns_404_does_not_walk_filesystem(
    async_client: httpx.AsyncClient,
) -> None:
    """Even with a path-traversal-looking ``file_id``, the DB lookup
    returns no row → clean 404. The handler never reaches the disk,
    so an attacker cannot use the endpoint to probe the host's FS.
    """
    async with async_client as ac:
        r = await ac.get("/files/..%2Fetc")
        assert r.status_code == 404
        r2 = await ac.get("/files/..%2F..%2Froot")
        assert r2.status_code == 404


# Restore the module to its on-disk state after the CORS env-var
# manipulations so subsequent test files don't inherit a reloaded copy.
def teardown_module(_mod: object) -> None:
    os.environ.pop("OMNIPLOT_CORS_ORIGINS", None)
    _reload_main()
