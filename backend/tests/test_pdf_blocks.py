"""Tests for the PDF block analyser.

Builds tiny PDFs with PyMuPDF so the test doesn't depend on any
external fixture. Checks block counts, bbox sanity, kind labelling,
and the text-sample extraction.
"""

from __future__ import annotations

import base64
import io

import pymupdf
import pytest
from fastapi.testclient import TestClient

from pen_plotter.converters.pdf_blocks import PT_TO_MM, extract_blocks
from pen_plotter.main import app

# 1x1 transparent PNG, used to seed an image block in the synthetic PDFs.
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _make_pdf(*, with_text: bool = True, with_image: bool = True) -> bytes:
    """Return a one-page A4 PDF with optional text and image blocks."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 in PDF points
    if with_text:
        page.insert_text((50, 100), "Hello World", fontsize=12)
    if with_image:
        page.insert_image((400, 100, 450, 150), stream=_TINY_PNG)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_extract_blocks_finds_text_and_image() -> None:
    """Synthetic A4 page with one text and one image block returns both."""
    result = extract_blocks(_make_pdf())
    assert len(result.pages) == 1
    page = result.pages[0]
    assert page.page_index == 0
    # A4 is 210x297 mm; allow ~0.5 mm slack for PyMuPDF's MediaBox math.
    assert 209 < page.width_mm < 211
    assert 296 < page.height_mm < 298

    kinds = sorted(b.kind for b in page.blocks)
    assert kinds == ["image", "text"]

    text_block = next(b for b in page.blocks if b.kind == "text")
    assert text_block.id == "p0-t0"
    assert text_block.text_sample == "Hello World"
    assert text_block.char_count == len("Hello World")

    image_block = next(b for b in page.blocks if b.kind == "image")
    assert image_block.id == "p0-i0"
    # Image was placed at (400,100)–(450,150) pt → mm conversion.
    assert image_block.bbox[0] == pytest.approx(400 * PT_TO_MM, rel=0.01)
    assert image_block.bbox[3] == pytest.approx(150 * PT_TO_MM, rel=0.01)


def test_extract_blocks_text_only_has_no_image_block() -> None:
    """A text-only page returns a single text block."""
    result = extract_blocks(_make_pdf(with_image=False))
    blocks = result.pages[0].blocks
    assert [b.kind for b in blocks] == ["text"]


def test_extract_blocks_caps_max_pages() -> None:
    """``max_pages`` caps how many pages are walked."""
    doc = pymupdf.open()
    for _ in range(5):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), "x", fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()

    result = extract_blocks(buf.getvalue(), max_pages=2)
    assert len(result.pages) == 2


def test_analyze_endpoint_returns_blocks() -> None:
    """The /document/analyze HTTP endpoint mirrors the helper output."""
    client = TestClient(app)
    files = {"file": ("test.pdf", _make_pdf(), "application/pdf")}
    response = client.post("/document/analyze", files=files)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["pages"]) == 1
    assert {b["kind"] for b in payload["pages"][0]["blocks"]} == {"text", "image"}


def test_analyze_endpoint_rejects_non_pdf() -> None:
    """Non-PDF uploads return 415."""
    client = TestClient(app)
    files = {"file": ("hello.txt", b"hello", "text/plain")}
    response = client.post("/document/analyze", files=files)
    assert response.status_code == 415
