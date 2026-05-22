"""Audit trail endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from pen_plotter.audit import AuditEntry, list_entries

router = APIRouter()


@router.get("/audit")
async def audit() -> list[AuditEntry]:
    """List recent sensitive actions, newest first."""
    return list_entries()
