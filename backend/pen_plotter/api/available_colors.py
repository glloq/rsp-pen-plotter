"""Available-colours endpoint — global inventory of inks the operator owns.

The library is decoupled from any specific machine profile: it lists every
Sharpie / fineliner / brush pen the operator can reach for, named or not,
ordered to mirror the operator's physical drawer. The editor's per-layer
colour picker reads this list when ``palette_source`` is set to
``available`` or ``union``, so the operator declares each ink once and
maps clusters to chips without re-typing hex codes for every job.

The CRUD surface is intentionally narrow:

- ``GET /available-colors`` lists every entry in display order.
- ``POST /available-colors`` adds one (auto-deduped by hex — re-adding an
  existing colour returns the existing entry instead of failing).
- ``PATCH /available-colors/{id}`` rewrites ``name`` / ``hex`` / ``position``
  on one entry, used by the rename + drag-reorder UI gestures.
- ``DELETE /available-colors/{id}`` removes one entry.

Hex codes are normalised to lowercased ``#rrggbb`` at the entrypoint so
duplicates can't sneak in via case or shorthand mismatch.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from pen_plotter.persistence import (
    AvailableColorRecord,
    delete_available_color,
    get_available_color,
    get_available_color_by_hex,
    list_available_colors,
    next_available_color_position,
    save_available_color,
)

router = APIRouter()

# Accept ``#rgb`` / ``#rrggbb`` / ``rgb`` / ``rrggbb``; canonicalise to
# ``#rrggbb`` lowercase before persistence so the unique index treats
# ``#ABC`` and ``#aabbcc`` as the same entry.
_HEX_PATTERN = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _normalise_hex(raw: str) -> str:
    """Lowercase, expand shorthand, prefix with ``#``. Raises on invalid input."""
    candidate = raw.strip()
    if not _HEX_PATTERN.match(candidate):
        raise ValueError(f"Invalid hex colour: {raw!r}")
    body = candidate.lstrip("#").lower()
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return f"#{body}"


class AvailableColorOut(BaseModel):
    """Wire shape returned by every available-colour endpoint."""

    color_id: str
    hex: str
    name: str
    position: int
    created_at: datetime


def _record_to_out(record: AvailableColorRecord) -> AvailableColorOut:
    return AvailableColorOut(
        color_id=record.color_id,
        hex=record.hex,
        name=record.name,
        position=record.position,
        created_at=record.created_at,
    )


class AvailableColorCreate(BaseModel):
    """Request body for ``POST /available-colors``."""

    hex: str
    name: str = ""

    @field_validator("hex")
    @classmethod
    def _check_hex(cls, value: str) -> str:
        # Validate at the API boundary so a malformed hex never reaches
        # the DB layer (the unique index is on the canonical form).
        return _normalise_hex(value)


class AvailableColorPatch(BaseModel):
    """Partial update body for ``PATCH /available-colors/{id}``."""

    hex: str | None = None
    name: str | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("hex")
    @classmethod
    def _check_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalise_hex(value)


@router.get("/available-colors")
async def list_colors() -> list[AvailableColorOut]:
    """Return every available-colour entry, ordered by position."""
    return [_record_to_out(r) for r in list_available_colors()]


@router.post("/available-colors")
async def create_color(body: AvailableColorCreate) -> AvailableColorOut:
    """Add an entry to the inventory.

    Idempotent on the hex value: re-adding an existing colour returns
    the existing record (its name may be updated if a non-empty name
    is supplied in the request) instead of erroring with 409. This
    matches the library / file dedup semantics — declaring the same
    ink twice should be a no-op, not a failure.
    """
    existing = get_available_color_by_hex(body.hex)
    if existing is not None:
        # Allow callers to update the human label when re-adding — handy
        # when the operator typo'd the first name and re-submits with
        # the corrected one. An explicit empty string also clears.
        if body.name != existing.name:
            existing.name = body.name
            save_available_color(existing)
        return _record_to_out(existing)

    record = AvailableColorRecord(
        color_id=str(uuid.uuid4()),
        hex=body.hex,
        name=body.name,
        position=next_available_color_position(),
        created_at=datetime.now(UTC),
    )
    save_available_color(record)
    return _record_to_out(record)


@router.patch("/available-colors/{color_id}")
async def patch_color(color_id: str, body: AvailableColorPatch) -> AvailableColorOut:
    """Rewrite ``name`` / ``hex`` / ``position`` on one entry."""
    record = get_available_color(color_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown colour: {color_id!r}")
    if body.hex is not None and body.hex != record.hex:
        # Refuse a hex change that would collide with another row — the
        # unique index would 500 otherwise.
        clash = get_available_color_by_hex(body.hex)
        if clash is not None and clash.color_id != record.color_id:
            raise HTTPException(
                status_code=409,
                detail=f"Hex {body.hex!r} is already used by {clash.color_id!r}",
            )
        record.hex = body.hex
    if body.name is not None:
        record.name = body.name
    if body.position is not None:
        record.position = body.position
    save_available_color(record)
    return _record_to_out(record)


@router.delete("/available-colors/{color_id}")
async def delete_color(color_id: str) -> dict[str, bool]:
    """Remove one entry. Returns ``{"deleted": true}`` on success."""
    if not delete_available_color(color_id):
        raise HTTPException(status_code=404, detail=f"Unknown colour: {color_id!r}")
    return {"deleted": True}


__all__ = [
    "AvailableColorCreate",
    "AvailableColorOut",
    "AvailableColorPatch",
    "router",
]
