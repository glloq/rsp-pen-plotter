"""Tests for the /files library endpoints (dedup, list, sort, search, CRUD)."""

import os
import tempfile

# Isolate the library storage dir before importing the app.
os.environ.setdefault(
    "OMNIPLOT_FILES_DIR", os.path.join(tempfile.gettempdir(), "omniplot_test_files")
)

import shutil  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

from pen_plotter.api.files import FILES_DIR  # noqa: E402
from pen_plotter.main import app  # noqa: E402
from pen_plotter.persistence import FileRecord, engine  # noqa: E402

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
SVG_A = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M0 0 L50 0 L50 50"/></g></svg>'
).encode()
SVG_B = (
    f'<svg {NS} viewBox="0 0 50 50">'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M0 0 L25 25"/></g></svg>'
).encode()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _clean_library():
    """Wipe the library DB rows + on-disk storage between tests."""
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()
    if FILES_DIR.exists():
        shutil.rmtree(FILES_DIR, ignore_errors=True)
    yield
    with Session(engine) as session:
        session.exec(delete(FileRecord))
        session.commit()
    if FILES_DIR.exists():
        shutil.rmtree(FILES_DIR, ignore_errors=True)


def _upload_form(content: bytes, name: str, folder: str = "") -> dict:
    return {
        "files": {"file": (name, content, "image/svg+xml")},
        "data": {"folder": folder},
    }


@pytest.mark.asyncio
async def test_upload_creates_library_entry() -> None:
    async with _client() as client:
        response = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
    assert response.status_code == 200
    body = response.json()
    assert body["existing"] is False
    file = body["file"]
    assert file["source_file"] == "a.svg"
    assert file["size_bytes"] == len(SVG_A)
    assert file["layer_count"] >= 1
    assert file["svg"]
    assert file["sha256"]


@pytest.mark.asyncio
async def test_upload_same_content_dedups() -> None:
    async with _client() as client:
        first = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
        second = await client.post("/files", **_upload_form(SVG_A, "renamed.svg"))
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["existing"] is True
    assert first.json()["file"]["file_id"] == second.json()["file"]["file_id"]
    # Listing still shows a single entry.
    async with _client() as client:
        listed = await client.get("/files")
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_lookup_by_hash_hit_returns_detail() -> None:
    """The dedup pre-check route returns the full detail for a known hash."""
    async with _client() as client:
        uploaded = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
        sha = uploaded.json()["file"]["sha256"]
        found = await client.get(f"/files/by-hash/{sha}")
    assert found.status_code == 200
    body = found.json()
    assert body["file_id"] == uploaded.json()["file"]["file_id"]
    # Same shape as the upload response's ``file`` — the frontend merges it
    # as a dedup hit without a second round-trip.
    assert body["svg"]
    assert body["layer_count"] >= 1


@pytest.mark.asyncio
async def test_lookup_by_hash_miss_is_404() -> None:
    async with _client() as client:
        missing = await client.get("/files/by-hash/" + "0" * 64)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_lookup_by_hash_does_not_shadow_file_id_route() -> None:
    """``by-hash`` is a literal segment, not a file id — the id route still wins."""
    async with _client() as client:
        uploaded = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
        file_id = uploaded.json()["file"]["file_id"]
        by_id = await client.get(f"/files/{file_id}")
    assert by_id.status_code == 200
    assert by_id.json()["file_id"] == file_id


@pytest.mark.asyncio
async def test_list_filters_and_sorts() -> None:
    async with _client() as client:
        await client.post("/files", **_upload_form(SVG_A, "alpha.svg", folder="tests"))
        await client.post("/files", **_upload_form(SVG_B, "bravo.svg"))
        # Folder filter.
        in_folder = await client.get("/files", params={"folder": "tests"})
        assert [f["source_file"] for f in in_folder.json()] == ["alpha.svg"]
        # Substring search.
        searched = await client.get("/files", params={"search": "brav"})
        assert [f["source_file"] for f in searched.json()] == ["bravo.svg"]
        # Sort by name asc.
        sorted_asc = await client.get("/files", params={"sort": "name", "order": "asc"})
        assert [f["source_file"] for f in sorted_asc.json()] == ["alpha.svg", "bravo.svg"]


@pytest.mark.asyncio
async def test_patch_and_delete() -> None:
    async with _client() as client:
        created = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
        file_id = created.json()["file"]["file_id"]
        patched = await client.patch(
            f"/files/{file_id}",
            json={"source_file": "new-name.svg", "folder": "moved"},
        )
        assert patched.status_code == 200
        assert patched.json()["source_file"] == "new-name.svg"
        assert patched.json()["folder"] == "moved"
        folders = await client.get("/files/folders")
        assert folders.json() == ["moved"]
        deleted = await client.delete(f"/files/{file_id}")
        assert deleted.status_code == 200
        missing = await client.get(f"/files/{file_id}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_upload_honors_palette_source_available() -> None:
    """With ``palette_source='available'`` the upload snaps centroids to the
    inventory pool, not the raw source colour."""
    from datetime import UTC, datetime

    from pen_plotter.api.available_colors import _normalise_hex
    from pen_plotter.persistence import (
        AvailableColorRecord,
        delete_available_color,
        list_available_colors,
        save_available_color,
        set_setting,
    )

    for record in list_available_colors():
        delete_available_color(record.color_id)
    set_setting("palette_source", "available")
    # A near-red ink the red layer should snap to.
    save_available_color(
        AvailableColorRecord(
            color_id="inv-red",
            hex=_normalise_hex("#ee1111"),
            name="",
            position=0,
            created_at=datetime.now(UTC),
        )
    )
    try:
        async with _client() as client:
            response = await client.post("/files", **_upload_form(SVG_A, "pal-a.svg"))
        layers = response.json()["file"]["layers"]
        assert layers
        assert layers[0]["assigned_color_hex"] == "#ee1111"
    finally:
        for record in list_available_colors():
            delete_available_color(record.color_id)
        set_setting("palette_source", "pens")


@pytest.mark.asyncio
async def test_upload_honors_palette_source_pens_clears_assignment() -> None:
    """With ``palette_source='pens'`` the profile-agnostic upload has an empty
    pool, so the auto assignment is cleared (the editor re-snaps against the
    selected profile's installed pens)."""
    from pen_plotter.persistence import (
        delete_available_color,
        list_available_colors,
        set_setting,
    )

    for record in list_available_colors():
        delete_available_color(record.color_id)
    set_setting("palette_source", "pens")
    try:
        async with _client() as client:
            response = await client.post("/files", **_upload_form(SVG_B, "pal-b.svg"))
        layers = response.json()["file"]["layers"]
        assert layers
        assert layers[0]["assigned_color_hex"] is None
    finally:
        set_setting("palette_source", "pens")


@pytest.mark.asyncio
async def test_list_rejects_bad_sort() -> None:
    async with _client() as client:
        response = await client.get("/files", params={"sort": "bogus"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_empty_file() -> None:
    async with _client() as client:
        response = await client.post(
            "/files",
            files={"file": ("empty.svg", b"", "image/svg+xml")},
        )
    assert response.status_code == 400
    assert "empty" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_upload_rejects_oversize_payload() -> None:
    """Stream guard fires before the body is fully buffered."""
    from pen_plotter.api.files import MAX_UPLOAD_BYTES

    huge = b"x" * (MAX_UPLOAD_BYTES + 1024)
    async with _client() as client:
        response = await client.post(
            "/files",
            files={"file": ("big.svg", huge, "image/svg+xml")},
        )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_overlong_filename() -> None:
    long_name = ("a" * 300) + ".svg"
    async with _client() as client:
        response = await client.post(
            "/files",
            files={"file": (long_name, SVG_A, "image/svg+xml")},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_failure_leaves_no_partial_directory() -> None:
    """A converter crash must not leave a half-populated library dir."""
    # An "svg" payload that's actually garbage will trip the layer
    # extractor and surface as a server-side error. Whatever the failure
    # mode, the atomic-rename strategy must have swept the staging dir.
    bad = b"\x00\x01not actually svg" * 50
    async with _client() as client:
        try:
            await client.post(
                "/files",
                files={"file": ("bad.svg", bad, "image/svg+xml")},
            )
        except Exception:
            # ASGI may surface uncaught server exceptions as transport
            # errors here — that's fine, we only care about disk state.
            pass
    if FILES_DIR.exists():
        leftover = list(FILES_DIR.glob(".tmp-*"))
        assert not leftover, f"leftover staging dirs: {leftover}"


# Regression — pre-fix bug: ``_options_changed`` validated against
# ``BitmapOptions`` only, so it silently dropped typography keys
# (font, font_size_mm, bold, italic, …). Re-uploading the same .txt
# file with a different font returned the stale cached SVG and the
# operator's setting never reached the generated G-code.
@pytest.mark.asyncio
async def test_typography_reupload_with_changed_font_size_reprocesses() -> None:
    import json

    txt = b"Hello plotter"
    upload_small = {
        "files": {"file": ("hello.txt", txt, "text/plain")},
        "data": {"folder": "", "options": json.dumps({"font_size_mm": 4.0})},
    }
    upload_large = {
        "files": {"file": ("hello.txt", txt, "text/plain")},
        "data": {"folder": "", "options": json.dumps({"font_size_mm": 20.0})},
    }
    async with _client() as client:
        small = await client.post("/files", **upload_small)
        large = await client.post("/files", **upload_large)
    assert small.status_code == 200 and large.status_code == 200
    # Same content → same file_id (dedup), but the SVG MUST differ because
    # the typography options changed.
    assert small.json()["file"]["file_id"] == large.json()["file"]["file_id"]
    assert small.json()["file"]["svg"] != large.json()["file"]["svg"]


@pytest.mark.asyncio
async def test_typography_reupload_with_bold_reprocesses() -> None:
    import json

    txt = b"Hello plotter"
    plain = {
        "files": {"file": ("hello.txt", txt, "text/plain")},
        "data": {"folder": "", "options": json.dumps({"font_size_mm": 10.0, "bold": False})},
    }
    bold = {
        "files": {"file": ("hello.txt", txt, "text/plain")},
        "data": {"folder": "", "options": json.dumps({"font_size_mm": 10.0, "bold": True})},
    }
    async with _client() as client:
        a = await client.post("/files", **plain)
        b = await client.post("/files", **bold)
    # Bold double-passes every stroke, so the bold SVG has ~2x as many
    # ``M`` sub-paths as the plain one.
    plain_subpaths = a.json()["file"]["svg"].count("M")
    bold_subpaths = b.json()["file"]["svg"].count("M")
    assert bold_subpaths >= plain_subpaths * 1.8


@pytest.mark.asyncio
async def test_typography_reupload_with_identical_options_dedupes() -> None:
    import json

    txt = b"Hello plotter"
    opts = {"font_size_mm": 10.0, "font": "futural", "bold": False}
    form = {
        "files": {"file": ("hello.txt", txt, "text/plain")},
        "data": {"folder": "", "options": json.dumps(opts)},
    }
    async with _client() as client:
        first = await client.post("/files", **form)
        second = await client.post("/files", **form)
    assert first.json()["file"]["file_id"] == second.json()["file"]["file_id"]
    # Same content + same options → cache hit, identical SVG.
    assert first.json()["file"]["svg"] == second.json()["file"]["svg"]


# /preview-image — the rasterised "Original" the editor's compare slider
# loads on the left half. Used to be bitmap-only (the toggle was hidden
# for every other format); these tests pin the new behaviour: an image
# source passes through untouched, a vector source comes back as PNG,
# unknown formats / ids surface clean error codes the UI can branch on.
@pytest.mark.asyncio
async def test_preview_image_for_svg_returns_png() -> None:
    async with _client() as client:
        uploaded = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
        file_id = uploaded.json()["file"]["file_id"]
        response = await client.get(f"/files/{file_id}/preview-image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    # PNG magic byte signature.
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_preview_image_passes_through_raster_uploads() -> None:
    # 1×1 transparent PNG: smallest valid raster we can ship in source.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63000100000005000172e2c0e80000000049454e44"
        "ae426082"
    )
    upload = {
        "files": {"file": ("dot.png", png_bytes, "image/png")},
        "data": {"folder": ""},
    }
    async with _client() as client:
        uploaded = await client.post("/files", **upload)
        file_id = uploaded.json()["file"]["file_id"]
        response = await client.get(f"/files/{file_id}/preview-image")
    assert response.status_code == 200
    # Bytes match — no re-encode, so JPEG sources also keep their quality
    # when the same endpoint serves them.
    assert response.content == png_bytes


@pytest.mark.asyncio
async def test_preview_image_rejects_unsupported_format() -> None:
    """``.txt`` has no useful raster preview — endpoint surfaces 415 so the
    UI can fall back to its text-source pane instead of a broken ``<img>``."""
    import json

    upload = {
        "files": {"file": ("hello.txt", b"Hello plotter", "text/plain")},
        "data": {"folder": "", "options": json.dumps({"font_size_mm": 10.0})},
    }
    async with _client() as client:
        uploaded = await client.post("/files", **upload)
        file_id = uploaded.json()["file"]["file_id"]
        response = await client.get(f"/files/{file_id}/preview-image")
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_preview_image_unknown_id_is_404() -> None:
    async with _client() as client:
        response = await client.get("/files/does-not-exist/preview-image")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_identical_upload_race_is_idempotent(monkeypatch) -> None:
    """Dedup TOCTOU regression: two concurrent identical uploads can both
    pass the hash pre-check; the loser's INSERT then hits the unique
    ``sha256`` index. The endpoint must catch the integrity error, clean
    up its orphaned artefact directory, and return the winner's record —
    not a 500."""
    from pen_plotter.api import files as files_module

    async with _client() as client:
        first = await client.post("/files", **_upload_form(SVG_A, "a.svg"))
    assert first.status_code == 200
    winner_id = first.json()["file"]["file_id"]
    dirs_before = {p.name for p in FILES_DIR.iterdir()}

    # Simulate the race window: the pre-check misses (as if the winner's
    # row hadn't landed yet), but the post-IntegrityError recovery lookup
    # sees the real record.
    real_lookup = files_module.get_file_record_by_hash
    calls = {"n": 0}

    def racy_lookup(digest):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # pre-check: pretend the row isn't there yet
        return real_lookup(digest)

    monkeypatch.setattr(files_module, "get_file_record_by_hash", racy_lookup)

    async with _client() as client:
        second = await client.post("/files", **_upload_form(SVG_A, "renamed.svg"))

    assert second.status_code == 200, second.text
    assert second.json()["existing"] is True
    assert second.json()["file"]["file_id"] == winner_id
    # The loser's artefact directory was cleaned up — no orphans.
    dirs_after = {p.name for p in FILES_DIR.iterdir()}
    assert dirs_after == dirs_before
