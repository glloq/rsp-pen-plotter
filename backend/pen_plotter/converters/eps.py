"""EPS / PostScript converter.

Rasterization-free path: convert EPS (or AI saved as EPS) to PDF via the
ghostscript binary, then extract vector SVG with PyMuPDF.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.converters.pdf import pdf_bytes_to_svg


def _eps_to_pdf(data: bytes) -> bytes:
    """Convert EPS/PostScript bytes to PDF bytes using ghostscript.

    Args:
        data: Raw EPS or PostScript file bytes.

    Returns:
        The converted PDF as bytes.

    Raises:
        RuntimeError: If the ``gs`` binary is not available.
    """
    if shutil.which("gs") is None:
        raise RuntimeError(
            "The 'gs' (ghostscript) binary is required to convert EPS but was not found."
        )
    with tempfile.TemporaryDirectory() as tmp:
        eps_path = Path(tmp) / "in.eps"
        pdf_path = Path(tmp) / "out.pdf"
        eps_path.write_bytes(data)
        subprocess.run(
            [
                "gs",
                "-q",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-dEPSCrop",
                "-sDEVICE=pdfwrite",
                f"-sOutputFile={pdf_path}",
                str(eps_path),
            ],
            check=True,
            capture_output=True,
        )
        return pdf_path.read_bytes()


class EpsConverter(Converter):
    """Converts EPS/PostScript to SVG via ghostscript and PyMuPDF."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset(
        {"application/postscript", "application/eps", "image/eps", "image/x-eps"}
    )

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert EPS bytes to SVG.

        Args:
            data: Raw EPS or PostScript file bytes.
            options: Unused; accepted for interface compatibility.

        Returns:
            A :class:`ConversionResult` containing the vector SVG.
        """
        pdf_bytes = _eps_to_pdf(data)
        svg, _ = pdf_bytes_to_svg(pdf_bytes, 0)
        return ConversionResult(svg=svg, source_mime="image/svg+xml")
