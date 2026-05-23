"""Tests for the fast preview endpoint."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pen_plotter.main import app


def _png_bytes(width: int = 32, height: int = 32) -> bytes:
    """Return a tiny synthetic image with two distinct colour regions."""
    image = Image.new("RGB", (width, height), (255, 255, 255))
    # Paint a black square in the centre so the converter has something to
    # vectorise (otherwise drop_background drops everything and we get no
    # layers — a real edge case but not what these tests are pinning).
    for x in range(width // 4, 3 * width // 4):
        for y in range(height // 4, 3 * height // 4):
            image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    # The /preview endpoint owns its own BitmapConverter and doesn't depend on
    # the lifespan (no DB, no print-queue interaction), so we skip the lifespan
    # by *not* using TestClient as a context manager. This sidesteps the known
    # cross-test event-loop leak around the print-queue's stop() coroutine.
    yield TestClient(app)


@pytest.fixture(autouse=True)
def _reset_preview_cache():
    """Clear the module-global preview LRU between tests."""
    from pen_plotter.api import preview as preview_module

    preview_module._cache.clear()
    yield
    preview_module._cache.clear()


def test_preview_returns_svg_for_png(client: TestClient) -> None:
    payload = _png_bytes()
    response = client.post(
        "/preview",
        data={"algorithm": "direct", "options": json.dumps({"num_colors": 2})},
        files={"file": ("dot.png", payload, "image/png")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["svg"].startswith("<svg") or body["svg"].startswith("<?xml")
    assert isinstance(body["elapsed_ms"], int)
    assert body["elapsed_ms"] < 5000  # generous CI bound
    assert body["cached"] is False
    assert any(entry["color"].startswith("#") for entry in body["palette"])


def test_preview_caches_identical_request(client: TestClient) -> None:
    payload = _png_bytes()
    files = {"file": ("dot.png", payload, "image/png")}
    data = {"algorithm": "direct", "options": json.dumps({"num_colors": 2})}

    first = client.post("/preview", data=data, files=files)
    assert first.status_code == 200 and first.json()["cached"] is False

    # Re-uploading the same bytes + same options must hit the cache.
    second = client.post(
        "/preview",
        data=data,
        files={"file": ("dot.png", payload, "image/png")},
    )
    assert second.status_code == 200
    assert second.json()["cached"] is True


def test_preview_rejects_non_image(client: TestClient) -> None:
    response = client.post(
        "/preview",
        data={"algorithm": "direct"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_preview_rejects_bad_options(client: TestClient) -> None:
    response = client.post(
        "/preview",
        data={"algorithm": "direct", "options": "not-json"},
        files={"file": ("dot.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 400
