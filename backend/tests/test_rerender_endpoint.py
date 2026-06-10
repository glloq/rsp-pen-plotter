"""Tests for the /rerender bitmap re-rendering endpoint."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pen_plotter.api import rerender as rerender_module
from pen_plotter.converters.bitmap import BitmapOptions, SegmentationResult
from pen_plotter.main import app


@pytest.fixture()
def client():
    # Re-rendering doesn't depend on the lifespan, so we skip it (avoids the
    # cross-test event-loop leak around the print queue).
    yield TestClient(app)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the in-memory segmentation cache between tests."""
    rerender_module._clear_cache_for_tests()
    yield
    rerender_module._clear_cache_for_tests()


def _seed_cache(job_id: str = "test-job") -> str:
    """Insert a fake bitmap segmentation into the cache and return its job_id."""
    # 8x8 image split in two halves: left = black (cluster 0), right = white (cluster 1).
    labels = np.zeros((8, 8), dtype=np.intp)
    labels[:, 4:] = 1
    palette = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
    seg = SegmentationResult(labels=labels, palette=palette, width=8, height=8)
    opts = BitmapOptions.model_validate(
        {"algorithm": "halftone", "drop_background": False, "num_colors": 2}
    )
    rerender_module.remember_job(job_id, seg, opts)
    return job_id


def test_rerender_404_when_job_not_cached(client: TestClient) -> None:
    response = client.post("/rerender", json={"job_id": "unknown", "layers": []})
    assert response.status_code == 404


def test_rerender_returns_svg_with_default_algorithm(client: TestClient) -> None:
    job_id = _seed_cache()
    response = client.post("/rerender", json={"job_id": job_id, "layers": []})
    assert response.status_code == 200
    body = response.json()
    assert "<svg" in body["svg"]
    # Default algorithm was halftone → expect circle elements.
    assert "<circle" in body["svg"]


def test_rerender_overrides_one_layer_algorithm(client: TestClient) -> None:
    job_id = _seed_cache()
    # Black layer label is "color-000000"; rerender it with crosshatch
    # while the white layer stays on the default (halftone) — but white
    # is dropped by the default ``drop_background=False`` we pin in the
    # cache options, so output should only contain crosshatch lines.
    response = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [
                {
                    "layer_id": "color-000000",
                    "algorithm": "crosshatch",
                    "algorithm_options": {"angle_deg": 0, "spacing_px": 2},
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Crosshatch emits <line> elements.
    assert "<line" in body["svg"]


def test_rerender_layer_ink_colors_overrides_stroke(client: TestClient) -> None:
    """``layer_ink_colors`` swaps the rendered stroke for the assigned ink.

    The cached black cluster (``#000000``) should render in the operator's
    pick (``#ff00aa``) rather than its segmentation centroid, so the
    preview reflects the magazine / inventory colour that will really be
    drawn. Layers not in the map keep their centroid stroke.
    """
    job_id = _seed_cache()
    response = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [
                {
                    "layer_id": "color-000000",
                    "algorithm": "crosshatch",
                    "algorithm_options": {"angle_deg": 0, "spacing_px": 2},
                }
            ],
            "layer_ink_colors": {"color-000000": "#ff00aa"},
        },
    )
    assert response.status_code == 200, response.text
    svg = response.json()["svg"]
    # The assigned ink wins over the centroid: the black layer paints in pink.
    assert "#ff00aa" in svg.lower()
    assert "#000000" not in svg.lower()


def test_rerender_unknown_algorithm_falls_back_with_warning(client: TestClient) -> None:
    job_id = _seed_cache()
    response = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [{"layer_id": "color-000000", "algorithm": "nope"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert any("nope" in w for w in body["warnings"])
    # Falls back to the cached default algorithm (halftone → circles).
    assert "<circle" in body["svg"]


def test_rerender_with_multipass_stacks_algorithms(client: TestClient) -> None:
    """Multi-pass: one colour drawn with several stacked algorithms.

    The black layer is rendered first with crosshatch (lines) then
    contours (path strokes), both wrapped in a single ``color-000000``
    group so downstream consumers still see one layer per colour.
    """
    job_id = _seed_cache()
    response = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [
                {
                    "layer_id": "color-000000",
                    "passes": [
                        {
                            "algorithm": "crosshatch",
                            "algorithm_options": {"angle_deg": 0, "spacing_px": 2},
                        },
                        {
                            "algorithm": "contours",
                            "algorithm_options": {"spacing_px": 1, "max_rings": 3},
                        },
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    svg = response.json()["svg"]
    # Crosshatch emits <line>, contours emit <polygon> (closed rings) or
    # <path>. Both pass-marker groups must be present and wrapped under a
    # single labeled outer group.
    assert "<line" in svg
    assert "<polygon" in svg or "<path" in svg
    assert svg.count('inkscape:label="color-000000"') == 1
    assert 'inkscape:label="color-000000-pass-0"' in svg
    assert 'inkscape:label="color-000000-pass-1"' in svg


def test_rerender_multipass_unknown_algorithm_falls_back(client: TestClient) -> None:
    job_id = _seed_cache()
    response = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [
                {
                    "layer_id": "color-000000",
                    "passes": [
                        {"algorithm": "nope"},
                        {"algorithm": "crosshatch"},
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert any("nope" in w for w in body["warnings"])


def test_upload_populates_cache_then_rerender_works(client: TestClient) -> None:
    """End-to-end: upload a PNG, then immediately /rerender by job_id.

    The lifespan-aware ``TestClient(app)`` context manager would normally
    register the converters, but the print-queue's event leaks between
    event loops when several test files share the same module ``app``.
    We register the converters by hand instead so this test can use the
    plain ``client`` fixture (no lifespan).
    """
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry

    register_default_converters(_registry)

    image = Image.new("RGB", (32, 32), (255, 255, 255))
    for y in range(32):
        for x in range(32):
            if x < 16:
                image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    upload = client.post(
        "/upload",
        data={
            "profile_name": "Custom CoreXY A3",
            "options": json.dumps(
                {
                    "algorithm": "direct",
                    "num_colors": 2,
                    "drop_background": False,
                }
            ),
        },
        files={"file": ("dot.png", buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    job_id = upload.json()["job"]["job_id"]
    assert job_id in rerender_module._CACHE

    rerender = client.post(
        "/rerender",
        json={
            "job_id": job_id,
            "layers": [{"layer_id": "color-000000", "algorithm": "halftone"}],
        },
    )
    assert rerender.status_code == 200, rerender.text
    assert "<circle" in rerender.json()["svg"]


def test_rerender_rehydrates_from_disk_after_cache_eviction(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """Cache miss → re-segment from the on-disk original + persisted options.

    Simulates a backend restart (the in-memory ``_CACHE`` is empty) and
    proves that /rerender still works for a bitmap upload because the
    rehydration path reads ``original.png`` + ``meta.bitmap_options`` from
    the library on demand.
    """
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry
    from pen_plotter.persistence import FileRecord, engine

    register_default_converters(_registry)
    # Isolate library storage to the test's tmp_path so the seeded upload
    # doesn't leak between runs and the DB row clean-up below is sufficient.
    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    image = Image.new("RGB", (16, 16), (255, 255, 255))
    for y in range(16):
        for x in range(8):
            image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    upload = client.post(
        "/files",
        data={
            "options": json.dumps(
                {"algorithm": "direct", "num_colors": 2, "drop_background": False}
            ),
        },
        files={"file": ("split.png", buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    detail = upload.json()["file"]
    file_id = detail["file_id"]
    assert detail["rerenderable"] is True
    assert file_id in rerender_module._CACHE

    # Simulate a backend restart: drop the in-memory cache.
    rerender_module._clear_cache_for_tests()
    assert file_id not in rerender_module._CACHE

    rerender = client.post(
        "/rerender",
        json={
            "job_id": file_id,
            "layers": [{"layer_id": "color-000000", "algorithm": "halftone"}],
        },
    )
    assert rerender.status_code == 200, rerender.text
    assert "<circle" in rerender.json()["svg"]
    # And the rehydrated entry should now be in the cache for subsequent
    # re-renders (no rehydration cost a second time).
    assert file_id in rerender_module._CACHE

    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()


def test_rerender_404_for_vector_source(client: TestClient, tmp_path, monkeypatch) -> None:
    """Vector files (SVG/PDF) have no segmentation cache → 404 with no rehydration.

    The /rerender endpoint should return 404 for files whose upload didn't
    produce a bitmap segmentation, so the frontend knows to hide the
    algorithm picker rather than silently doing nothing.
    """
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry
    from pen_plotter.persistence import FileRecord, engine

    register_default_converters(_registry)
    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        b'viewBox="0 0 100 100">'
        b'<path d="M0 0 L50 50"/></svg>'
    )
    upload = client.post(
        "/files",
        files={"file": ("vec.svg", svg, "image/svg+xml")},
    )
    assert upload.status_code == 200, upload.text
    detail = upload.json()["file"]
    assert detail["rerenderable"] is False

    rerender = client.post(
        "/rerender",
        json={"job_id": detail["file_id"], "layers": []},
    )
    assert rerender.status_code == 404

    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()


def test_reupload_with_changed_options_reprocesses_in_place(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """SourceSection edit → Apply → /files dedup hit should still apply.

    Reproduces the operator's report that changing the global algorithm
    in SourceSection and clicking Apply silently did nothing: the
    /files endpoint used to dedup-by-hash unconditionally, returning
    the prior conversion and dropping the new options on the floor.
    """
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry
    from pen_plotter.persistence import FileRecord, engine

    register_default_converters(_registry)
    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    # 16x16 PNG, left-black / right-white — two-cluster segmentation,
    # easy to tell algorithms apart by output element type.
    image = Image.new("RGB", (16, 16), (255, 255, 255))
    for y in range(16):
        for x in range(8):
            image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # First upload: scanlines → SVG should contain polylines.
    first = client.post(
        "/files",
        data={
            "options": json.dumps(
                {"algorithm": "scanlines", "num_colors": 2, "drop_background": False}
            )
        },
        files={"file": ("dot.png", png_bytes, "image/png")},
    )
    assert first.status_code == 200, first.text
    detail1 = first.json()["file"]
    file_id = detail1["file_id"]
    assert "<polyline" in detail1["svg"]
    assert "<circle" not in detail1["svg"]

    # Second upload, same bytes, DIFFERENT options (halftone → circles).
    # Pre-fix: dedup returned the scanline SVG unchanged. Post-fix: the
    # endpoint re-processes in place, file_id stays stable, SVG flips
    # to halftone.
    second = client.post(
        "/files",
        data={
            "options": json.dumps(
                {"algorithm": "halftone", "num_colors": 2, "drop_background": False}
            )
        },
        files={"file": ("dot.png", png_bytes, "image/png")},
    )
    assert second.status_code == 200, second.text
    detail2 = second.json()["file"]
    assert detail2["file_id"] == file_id, "file_id must stay stable on reprocess"
    assert second.json()["existing"] is True
    assert "<circle" in detail2["svg"], "halftone should emit circles"
    assert detail2["svg"] != detail1["svg"], "SVG must reflect the new algorithm"

    # And the /rerender cache is refreshed so subsequent re-renders use
    # the new segmentation (not the stale scanline one).
    assert file_id in rerender_module._CACHE

    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()


def test_reupload_without_options_keeps_dedup_silent(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """No options on the request → preserve the existing conversion.

    A library-pick re-upload (e.g. drag-and-drop the same PNG to add a
    second placement) MUST NOT re-process — that would burn CPU on a
    no-op and risk shifting palette indices on the operator's other
    placements of the same file.
    """
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry
    from pen_plotter.persistence import FileRecord, engine

    register_default_converters(_registry)
    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    image = Image.new("RGB", (16, 16), (255, 255, 255))
    for y in range(16):
        for x in range(8):
            image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    first = client.post(
        "/files",
        data={
            "options": json.dumps(
                {"algorithm": "scanlines", "num_colors": 2, "drop_background": False}
            )
        },
        files={"file": ("dot.png", png_bytes, "image/png")},
    )
    detail1 = first.json()["file"]
    second = client.post(
        "/files",
        files={"file": ("dot.png", png_bytes, "image/png")},
    )
    detail2 = second.json()["file"]
    assert detail1["svg"] == detail2["svg"]

    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()


# ---------- L4: rehydration failure modes + integrity endpoint ----------


def _seed_library_png(
    client: TestClient,
    tmp_path,
    monkeypatch,
    *,
    filename: str = "img.png",
) -> str:
    """Helper: upload a bitmap and return its file_id, isolated to tmp_path."""
    from sqlmodel import Session, delete

    from pen_plotter.api import files as files_module
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry as _registry
    from pen_plotter.persistence import FileRecord, engine

    register_default_converters(_registry)
    monkeypatch.setattr(files_module, "FILES_DIR", tmp_path / "files")
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()

    image = Image.new("RGB", (16, 16), (255, 255, 255))
    for y in range(16):
        for x in range(8):
            image.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    upload = client.post(
        "/files",
        data={
            "options": json.dumps(
                {"algorithm": "direct", "num_colors": 2, "drop_background": False}
            ),
        },
        files={"file": (filename, buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    detail = upload.json()["file"]
    assert detail["rerenderable"] is True
    return detail["file_id"]


def test_rerender_404_detail_is_structured(client: TestClient, tmp_path, monkeypatch) -> None:
    """The L4 contract: every 404 carries a machine-readable ``reason``.

    The frontend used to receive a free-text detail and could only show
    a generic toast. With the structured shape it can branch (re-upload,
    different file type, etc.) and present a specific prompt.
    """
    response = client.post("/rerender", json={"job_id": "no-such-job", "layers": []})
    assert response.status_code == 404
    body = response.json()
    # P1: HTTPException(detail={"reason": ..., "job_id": ..., "message": ...})
    # flattens into the unified envelope: ``message`` is hoisted out and the
    # remaining keys live under ``details``.
    assert body["details"]["reason"] == "unknown_job"
    assert body["details"]["job_id"] == "no-such-job"
    assert body["message"]


def test_rerender_404_when_original_bytes_disappeared(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """Cache cleared + original.png deleted ⇒ structured 404, no crash."""
    from pen_plotter.api import files as files_module

    file_id = _seed_library_png(client, tmp_path, monkeypatch)
    rerender_module._clear_cache_for_tests()
    # Wipe the stored original to simulate disk loss / manual cleanup.
    original = files_module._find_original(file_id)
    assert original is not None
    original.unlink()

    response = client.post(
        "/rerender",
        json={
            "job_id": file_id,
            "layers": [{"layer_id": "color-000000", "algorithm": "halftone"}],
        },
    )
    assert response.status_code == 404
    assert response.json()["details"]["reason"] == "missing_original_bytes"


def test_rerender_404_when_bitmap_options_corrupted(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """meta.json without bitmap_options (legacy / edited) ⇒ structured 404."""
    from pen_plotter.application import file_library

    file_id = _seed_library_png(client, tmp_path, monkeypatch)
    rerender_module._clear_cache_for_tests()
    # Strip bitmap_options from meta.json to simulate a legacy file or
    # an externally-tampered library entry.
    meta_path = file_library.meta_path(file_id)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["bitmap_options"] = None
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    response = client.post(
        "/rerender",
        json={
            "job_id": file_id,
            "layers": [{"layer_id": "color-000000", "algorithm": "halftone"}],
        },
    )
    assert response.status_code == 404
    assert response.json()["details"]["reason"] == "missing_bitmap_options"


def test_files_integrity_endpoint_lists_broken_entries(
    client: TestClient, tmp_path, monkeypatch
) -> None:
    """The /files/integrity endpoint surfaces the same diagnoses the UI
    needs to disable Edit / show a re-upload banner.
    """
    from pen_plotter.application import file_library

    file_id = _seed_library_png(client, tmp_path, monkeypatch)
    # Healthy snapshot first.
    healthy = client.get("/files/integrity").json()
    assert healthy["rerenderable"] >= 1
    assert healthy["issues"] == []

    # Now break the entry on disk and re-run the scan.
    meta_path = file_library.meta_path(file_id)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["bitmap_options"] = None
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    broken = client.get("/files/integrity").json()
    assert any(
        issue["file_id"] == file_id and issue["reason"] == "missing_bitmap_options"
        for issue in broken["issues"]
    )
