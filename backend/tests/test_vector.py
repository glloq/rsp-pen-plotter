import io
import shutil

import ezdxf
import pymupdf
import pytest

from pen_plotter.converters.dxf import DxfConverter
from pen_plotter.converters.eps import EpsConverter
from pen_plotter.converters.pdf import PdfConverter

needs_gs = pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript not installed")

EPS_SAMPLE = b"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 100 100
newpath 10 10 moveto 90 90 lineto 10 90 lineto closepath stroke
showpage
"""


def _two_page_pdf() -> bytes:
    doc = pymupdf.open()
    p0 = doc.new_page(width=200, height=100)
    p0.draw_line((10, 10), (180, 80))
    p1 = doc.new_page(width=200, height=100)
    p1.draw_circle((100, 50), 30)
    data = doc.tobytes()
    doc.close()
    return data


def _dxf_bytes() -> bytes:
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 50))
    msp.add_circle((50, 25), 10)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_pdf_selects_page_and_reports_count() -> None:
    result = PdfConverter().convert(_two_page_pdf(), options={"page": 1})
    assert result.source_mime == "image/svg+xml"
    assert result.svg.startswith("<svg")
    assert result.metadata["page_count"] == 2
    assert result.metadata["page"] == 1


def test_pdf_page_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        PdfConverter().convert(_two_page_pdf(), options={"page": 9})


def test_dxf_renders_svg() -> None:
    result = DxfConverter().convert(_dxf_bytes())
    assert result.source_mime == "image/svg+xml"
    assert "<svg" in result.svg
    assert "<path" in result.svg


def test_dxf_invalid_raises() -> None:
    with pytest.raises(ValueError):
        DxfConverter().convert(b"not a dxf file at all")


@needs_gs
def test_eps_converts_to_svg() -> None:
    result = EpsConverter().convert(EPS_SAMPLE)
    assert result.source_mime == "image/svg+xml"
    assert result.svg.startswith("<svg")
