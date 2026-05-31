"""Source-file rasterisation for the editor "Original / Compare" preview.

The edit modal's mode toggle (Original raster | Result SVG | Compare
slider) used to be hidden for every non-bitmap source because the
"original" half had nothing to display: the browser cannot drop a PDF
or DOCX straight into ``<img src=…>``. This module produces a PNG
rasterisation of any supported source so the same toggle works for
PDF, SVG, DOCX/ODT/RTF, HTML and EPS/PS/AI placements — the operator
can finally A/B-compare the conversion against the original page.

Backends used:
    * **Image sources** (PNG/JPG/TIFF/WebP/HEIC) — passed through as the
      bytes already are; the caller streams the original file unchanged.
      Reported here only for completeness; the API endpoint short-circuits
      these without touching this module.
    * **PDF / SVG** — PyMuPDF ``page.get_pixmap`` at the requested DPI.
    * **DOCX / ODT / RTF** — headless LibreOffice → PDF, then PyMuPDF.
    * **HTML** — WeasyPrint → PDF, then PyMuPDF.
    * **EPS / PS / AI** — Ghostscript ``-sDEVICE=png16m`` direct.
    * **TXT / MD / DXF** — not rasterisable here (typography has its own
      text-source preview; DXF has no good preview backend in stock
      Ghostscript). Raises :class:`UnsupportedFormatError` so the API can
      surface a clean 415 and the UI can fall back gracefully.

The default 144 DPI matches the operator's editor viewport at typical
zoom levels — high enough that text on an A4 page stays legible when
they pan / zoom in, low enough that the round-trip stays well under a
second on a Pi-class device.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_DPI = 144

# Extensions PyMuPDF can open directly. ``pdf`` is the obvious target,
# but PyMuPDF also reads SVG (and a couple of bitmap formats we don't
# route through this path) — using it for SVG saves us a second
# dependency (resvg / Inkscape) just to rasterise a vector source.
_PYMUPDF_DIRECT = {".pdf": "pdf", ".svg": "svg"}

# Office formats: route through LibreOffice → PDF → PyMuPDF.
_OFFICE_EXTS = {".docx", ".odt", ".rtf"}

# PostScript family: Ghostscript handles all three with the same device.
_POSTSCRIPT_EXTS = {".eps", ".ps", ".ai"}

# Browser-renderable rasters: the API serves the original bytes directly
# instead of re-encoding them through PyMuPDF — avoids quality loss on
# JPEG sources and keeps the response a fast file-stream.
_PASSTHROUGH_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic"}


class UnsupportedFormatError(RuntimeError):
    """The source extension has no rasterisation backend wired up."""


def is_passthrough(ext: str) -> bool:
    """Return True if the original bytes can be served straight back."""
    return ext.lower() in _PASSTHROUGH_EXTS


def rasterize_source(path: Path, page_index: int = 0, dpi: int = DEFAULT_DPI) -> bytes:
    """Rasterise ``path`` to a PNG of the requested page.

    Args:
        path: On-disk path to the original uploaded file.
        page_index: Zero-based page for multi-page documents (PDF / DOCX).
            Single-page formats ignore this.
        dpi: Render resolution. Defaults to a screen-friendly 144 DPI.

    Returns:
        PNG bytes, ready to stream to the browser.

    Raises:
        UnsupportedFormatError: The extension isn't covered by any backend.
        RuntimeError: A required external tool is missing or failed.
        ValueError: ``page_index`` is out of range for the document.
    """
    ext = path.suffix.lower()
    if ext in _PYMUPDF_DIRECT:
        return _pymupdf_to_png(path.read_bytes(), _PYMUPDF_DIRECT[ext], page_index, dpi)
    if ext in _OFFICE_EXTS:
        pdf_bytes = _office_to_pdf(path.read_bytes(), ext.lstrip("."))
        return _pymupdf_to_png(pdf_bytes, "pdf", page_index, dpi)
    if ext in {".html", ".htm"}:
        pdf_bytes = _html_to_pdf(path.read_bytes())
        return _pymupdf_to_png(pdf_bytes, "pdf", page_index, dpi)
    if ext in _POSTSCRIPT_EXTS:
        return _ghostscript_to_png(path.read_bytes(), page_index, dpi)
    raise UnsupportedFormatError(f"No preview rasteriser for {ext!r}")


def _pymupdf_to_png(data: bytes, filetype: str, page_index: int, dpi: int) -> bytes:
    """Render one page of a PyMuPDF-readable document to PNG bytes."""
    import pymupdf  # local import: heavy native lib, not needed for passthrough.

    with pymupdf.open(stream=data, filetype=filetype) as doc:
        page_count = doc.page_count
        if page_count == 0:
            raise ValueError(f"{filetype.upper()} has no pages")
        if not 0 <= page_index < page_count:
            # Multi-page documents page out of range — clamp rather than
            # raise so a stale ``?page=`` query string from a switched
            # placement doesn't 500 the preview pane. Operator can still
            # navigate forward with the existing pager.
            page_index = max(0, min(page_index, page_count - 1))
        pix = doc[page_index].get_pixmap(dpi=dpi, alpha=False)
        png_bytes: bytes = pix.tobytes("png")
        return png_bytes


def _office_to_pdf(data: bytes, extension: str) -> bytes:
    """Run a one-shot headless LibreOffice conversion to PDF.

    Mirrors ``converters.document._office_to_pdf`` but stays self-contained
    so the preview path doesn't pull the full converter package (and its
    PyMuPDF / hershey imports) just to ask LibreOffice for a PDF.
    """
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if binary is None:
        raise RuntimeError(
            "LibreOffice ('libreoffice'/'soffice') is required for document previews."
        )
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in.{extension}"
        src.write_bytes(data)
        profile = Path(tmp) / "profile"
        env = {**os.environ, "HOME": tmp}
        subprocess.run(
            [
                binary,
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp,
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=180,
            env=env,
        )
        pdf_path = src.with_suffix(".pdf")
        if not pdf_path.exists():
            raise RuntimeError(
                "LibreOffice produced no PDF (unsupported or corrupt input)."
            )
        return pdf_path.read_bytes()


def _html_to_pdf(data: bytes) -> bytes:
    """Render HTML to PDF via WeasyPrint (the converter's existing dep)."""
    from weasyprint import HTML  # local: weasyprint pulls in cairo / pango.

    html = data.decode("utf-8", errors="replace")
    pdf_bytes: bytes = HTML(string=html).write_pdf()
    return pdf_bytes


def _ghostscript_to_png(data: bytes, page_index: int, dpi: int) -> bytes:
    """Render a PostScript/EPS/AI page to a PNG via Ghostscript."""
    binary = shutil.which("gs")
    if binary is None:
        raise RuntimeError("Ghostscript ('gs') is required for EPS/PS/AI previews.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.ps"
        src.write_bytes(data)
        out = Path(tmp) / "out.png"
        # ``-dFirstPage`` / ``-dLastPage`` are 1-indexed in Ghostscript.
        page_arg = max(1, page_index + 1)
        subprocess.run(
            [
                binary,
                "-q",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-sDEVICE=png16m",
                f"-r{dpi}",
                f"-dFirstPage={page_arg}",
                f"-dLastPage={page_arg}",
                f"-sOutputFile={out}",
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
        if not out.exists():
            raise RuntimeError("Ghostscript produced no PNG output.")
        return out.read_bytes()


__all__ = [
    "DEFAULT_DPI",
    "UnsupportedFormatError",
    "is_passthrough",
    "rasterize_source",
]
