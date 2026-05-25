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

from pen_plotter.api.files import FILES_DIR  # noqa: E402
from pen_plotter.main import app  # noqa: E402
from pen_plotter.persistence import FileRecord, engine  # noqa: E402
from sqlmodel import Session, delete  # noqa: E402

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
    assert "empty" in response.json()["detail"].lower()


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
