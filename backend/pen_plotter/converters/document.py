"""Office document converter.

Converts DOCX/ODT/RTF to PDF via a headless LibreOffice subprocess, then
extracts vector SVG with PyMuPDF.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.converters.pdf import build_hershey_text_group, pdf_bytes_to_svg
from pen_plotter.core.pdf_postprocess import postprocess_pdf_svg

_EXTENSION_BY_MIME = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
}


def _office_to_pdf(data: bytes, extension: str) -> bytes:
    """Convert an office document to PDF via headless LibreOffice.

    Args:
        data: Raw document bytes.
        extension: Source file extension (without dot), e.g. ``"docx"``.

    Returns:
        The converted PDF as bytes.

    Raises:
        RuntimeError: If LibreOffice is unavailable or produces no output.
    """
    binary = shutil.which("libreoffice") or shutil.which("soffice")
    if binary is None:
        raise RuntimeError(
            "LibreOffice ('libreoffice'/'soffice') is required to convert documents "
            "but was not found."
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
            raise RuntimeError("LibreOffice did not produce a PDF (unsupported or corrupt input).")
        return pdf_path.read_bytes()


class DocumentConverter(Converter):
    """Converts office documents (DOCX/ODT/RTF) to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset(_EXTENSION_BY_MIME)

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert an office document to SVG.

        Args:
            data: Raw document bytes.
            options: Optional ``source_mime`` to pick the input extension; the
                first page is rendered.

        Returns:
            A :class:`ConversionResult` containing the first rendered page.
        """
        opts = options or {}
        mime = str(opts.get("source_mime", ""))
        extension = _EXTENSION_BY_MIME.get(mime, "docx")
        page_index = int(opts.get("page", 0))
        bitmap_options = {
            key: opts[key]
            for key in (
                "algorithm",
                "num_colors",
                "max_dimension_px",
                "drop_background",
                "background_luminance",
                "algorithm_options",
            )
            if key in opts
        } or None
        pdf_bytes = _office_to_pdf(data, extension)
        raw_svg, page_count, width_mm, height_mm = pdf_bytes_to_svg(pdf_bytes, page_index)
        hershey_group = build_hershey_text_group(pdf_bytes, page_index, opts)
        svg, warnings = postprocess_pdf_svg(
            raw_svg,
            bitmap_options=bitmap_options,
            hershey_text_group=hershey_group or None,
        )
        return ConversionResult(
            svg=svg,
            source_mime="image/svg+xml",
            warnings=warnings,
            metadata={
                "page_count": page_count,
                "page": page_index,
                "page_width_mm": width_mm,
                "page_height_mm": height_mm,
            },
        )
