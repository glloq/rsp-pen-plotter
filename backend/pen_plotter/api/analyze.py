"""Document analysis endpoint.

Returns the structure of a PDF (text vs image blocks with bounding
boxes) so the UI can offer per-block render presets in the editor's
BlockMapCard. The endpoint is read-only and does not persist anything;
clients call it once per upload and cache the result alongside the
placement.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from pen_plotter.converters.pdf_blocks import DocumentAnalysis, extract_blocks

router = APIRouter()

MAX_ANALYZE_BYTES = 50 * 1024 * 1024


def _is_pdf(file: UploadFile) -> bool:
    if file.content_type == "application/pdf":
        return True
    filename = (file.filename or "").lower()
    return filename.endswith(".pdf")


@router.post("/document/analyze", response_model=DocumentAnalysis)
async def analyze_document(
    file: Annotated[UploadFile, File()],
) -> DocumentAnalysis:
    """Extract text and image blocks for every page of a PDF.

    Args:
        file: A PDF upload; other MIME types are rejected with 415.

    Returns:
        A :class:`DocumentAnalysis` listing the blocks of each page.

    Raises:
        HTTPException: 415 when the upload is not a PDF; 413 if the
            file exceeds the analysis size limit; 422 if PyMuPDF cannot
            parse the document.
    """
    if not _is_pdf(file):
        raise HTTPException(status_code=415, detail="Only PDF analysis is supported.")
    data = await file.read()
    if len(data) > MAX_ANALYZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_ANALYZE_BYTES // (1024 * 1024)} MB analysis limit.",
        )
    try:
        # PyMuPDF parsing is synchronous CPU-bound work; keep it off the
        # event loop so a large PDF doesn't stall every other request.
        return await run_in_threadpool(extract_blocks, data)
    except Exception as exc:  # PyMuPDF raises a variety of exceptions
        raise HTTPException(status_code=422, detail=f"PDF analysis failed: {exc}") from exc
