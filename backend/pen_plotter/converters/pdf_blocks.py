"""Block-level analysis of PDF documents.

Detects text and image regions per page and reports their bounding
boxes in millimetres so the UI can map per-block render presets onto
PDFs that mix typography and imagery. Block IDs are stable for a given
``(page_index, kind, position-in-list)`` so the frontend can persist
per-block assignments alongside a placement.

A future converter extension will honour those assignments by routing
each block to a different rendering strategy; for now the analyser only
reports what it sees, which is enough to drive the BlockMapCard.
"""

from __future__ import annotations

from typing import Literal

import pymupdf
from pydantic import BaseModel

# PDF user-space units are points (1 pt = 1/72 inch).
PT_TO_MM = 25.4 / 72.0

BlockKind = Literal["text", "image"]


class Block(BaseModel):
    """One detected region on a PDF page.

    Attributes:
        id: Stable identifier ``p<page>-<t|i><index>`` — see module docstring.
        kind: ``"text"`` or ``"image"``.
        bbox: ``[x_min, y_min, x_max, y_max]`` in millimetres, top-left origin.
        text_sample: First ~60 characters of the block's text (text blocks only).
        char_count: Number of non-whitespace characters (text blocks only).
    """

    id: str
    kind: BlockKind
    bbox: list[float]
    text_sample: str | None = None
    char_count: int | None = None


class PageBlocks(BaseModel):
    """All detected blocks on one PDF page."""

    page_index: int
    width_mm: float
    height_mm: float
    blocks: list[Block]


class DocumentAnalysis(BaseModel):
    """Container returned by :func:`extract_blocks`."""

    pages: list[PageBlocks]


def _rect_to_bbox_mm(rect: pymupdf.Rect) -> list[float]:
    return [rect.x0 * PT_TO_MM, rect.y0 * PT_TO_MM, rect.x1 * PT_TO_MM, rect.y1 * PT_TO_MM]


def extract_blocks(data: bytes, *, max_pages: int = 20) -> DocumentAnalysis:
    """Return per-page text + image blocks for a PDF.

    Args:
        data: Raw PDF bytes.
        max_pages: Cap on the number of pages analysed; long documents
            are otherwise expensive to walk.

    Returns:
        A :class:`DocumentAnalysis` with one :class:`PageBlocks` per
        analysed page.
    """
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pages: list[PageBlocks] = []
        for page_index in range(min(doc.page_count, max_pages)):
            page = doc[page_index]
            blocks: list[Block] = []

            # Text blocks. PyMuPDF returns one tuple per block:
            # (x0, y0, x1, y1, text, block_no, block_type) where
            # block_type == 0 is text and block_type == 1 is image — we
            # handle image blocks separately via get_images() to also
            # get the underlying xref for future per-block rendering.
            text_index = 0
            for entry in page.get_text("blocks"):
                if len(entry) < 7:
                    continue
                x0, y0, x1, y1, text, _block_no, block_type = entry[:7]
                if block_type != 0:
                    continue
                stripped = (text or "").strip()
                if not stripped:
                    continue
                rect = pymupdf.Rect(x0, y0, x1, y1)
                if rect.is_empty or rect.is_infinite:
                    continue
                blocks.append(
                    Block(
                        id=f"p{page_index}-t{text_index}",
                        kind="text",
                        bbox=_rect_to_bbox_mm(rect),
                        text_sample=stripped[:60],
                        char_count=len(stripped),
                    )
                )
                text_index += 1

            # Image blocks. ``get_images(full=True)`` enumerates every
            # raster object referenced from the page; ``get_image_bbox``
            # turns each into a page-space rectangle.
            for image_index, image_info in enumerate(page.get_images(full=True)):
                try:
                    rect = page.get_image_bbox(image_info)
                except (ValueError, RuntimeError):
                    # Image referenced but not actually placed on the page
                    # (e.g., used only via a soft mask). Skip.
                    continue
                if rect.is_empty or rect.is_infinite:
                    continue
                blocks.append(
                    Block(
                        id=f"p{page_index}-i{image_index}",
                        kind="image",
                        bbox=_rect_to_bbox_mm(rect),
                    )
                )

            pages.append(
                PageBlocks(
                    page_index=page_index,
                    width_mm=page.rect.width * PT_TO_MM,
                    height_mm=page.rect.height * PT_TO_MM,
                    blocks=blocks,
                )
            )
        return DocumentAnalysis(pages=pages)
