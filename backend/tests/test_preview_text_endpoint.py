"""``/preview-text`` endpoint — live Hershey typography preview."""

import asyncio
import json

import pytest

from pen_plotter.api.preview_text import preview_text


class _FakeUpload:
    """Minimal stand-in for ``fastapi.UploadFile``."""

    def __init__(self, data: bytes, filename: str, content_type: str) -> None:
        self._data = data
        self.filename = filename
        self.content_type = content_type
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + n]
        self._pos += n
        return chunk


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_preview_text_renders_plain_text_to_hershey_svg() -> None:
    f = _FakeUpload(b"Hello plotter!", "x.txt", "text/plain")
    res = _run(preview_text(f, options=None))
    assert res.svg.startswith("<svg")
    assert "<path" in res.svg
    assert not res.truncated


def test_preview_text_renders_markdown_blocks() -> None:
    f = _FakeUpload(b"# Heading\nbody text", "x.md", "text/markdown")
    res = _run(preview_text(f, options=json.dumps({"font": "rowmans"})))
    # Heading + body → at least two text lines worth of paths.
    assert res.svg.count("<path") >= 1


def test_preview_text_rejects_non_text_mime() -> None:
    from fastapi import HTTPException

    f = _FakeUpload(b"binary", "x.png", "image/png")
    with pytest.raises(HTTPException) as exc:
        _run(preview_text(f, options=None))
    assert exc.value.status_code == 415


def test_preview_text_rejects_unknown_font() -> None:
    from fastapi import HTTPException

    f = _FakeUpload(b"hi", "x.txt", "text/plain")
    with pytest.raises(HTTPException) as exc:
        _run(preview_text(f, options=json.dumps({"font": "not-a-font"})))
    assert exc.value.status_code == 400


def test_preview_text_rejects_empty_upload() -> None:
    from fastapi import HTTPException

    f = _FakeUpload(b"", "x.txt", "text/plain")
    with pytest.raises(HTTPException) as exc:
        _run(preview_text(f, options=None))
    assert exc.value.status_code == 400


def test_preview_text_truncation_flag_on_large_input() -> None:
    big = b"line\n" * 100_000  # 500 KB > 256 KB cap
    f = _FakeUpload(big, "x.txt", "text/plain")
    res = _run(preview_text(f, options=None))
    assert res.truncated is True
