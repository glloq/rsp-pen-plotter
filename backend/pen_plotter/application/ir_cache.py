"""SQLite-backed cache for IR artifacts (roadmap E.1 wire).

Stores serialized :class:`GeometryIR` (and, eventually,
:class:`SegmentationArtifact`) blobs keyed by
``(content_sha256, options_sha256)``. The cache lives next to the
existing app DB; ``init_db()`` creates the table on first import.

Today the cache is **write-only** — :func:`pipeline.convert_file` fills
it when ``OMNIPLOT_IR_ENABLED=1``, but no consumer reads from it yet.
That's by design: the IR rendering / optimization path will land next
and at that point the cache becomes the cold-start lookup. Until then
the table is a paper trail the operator (or a debug tool) can inspect
to confirm IR generation is happening end-to-end.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import Column, Engine, LargeBinary, String
from sqlmodel import Field, Session, SQLModel, select

from pen_plotter.domain.ir.geometry import GeometryIR
from pen_plotter.persistence import engine as default_engine

_log = logging.getLogger(__name__)


class IrArtifactRow(SQLModel, table=True):
    """One cached IR artifact (geometry/segmentation/...) per source+options."""

    __tablename__ = "ir_artifact_cache"

    cache_key: str = Field(primary_key=True)
    kind: str
    source_hash: str
    payload: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    options_json: str = Field(sa_column=Column(String, nullable=False))


def options_sha256(options: dict[str, Any] | None) -> str:
    """Hash the options dict deterministically (sorted keys, compact JSON)."""
    canonical = json.dumps(options or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_key(kind: str, source_hash: str, options: dict[str, Any] | None) -> str:
    return f"{kind}:{source_hash}:{options_sha256(options)}"


def store_geometry(
    source_hash: str,
    options: dict[str, Any] | None,
    geometry: GeometryIR,
    *,
    target: Engine = default_engine,
) -> None:
    """Persist ``geometry`` under the ``(source_hash, options)`` key.

    Best-effort: failures are logged but never raised — the cache is an
    accelerator, not a critical path. ``convert_file`` already has the
    geometry in memory; a missed write just costs a recompute next time.
    """
    try:
        payload = geometry.model_dump_json().encode("utf-8")
        key = _cache_key(geometry.kind, source_hash, options)
        with Session(target) as session:
            existing = session.exec(
                select(IrArtifactRow).where(IrArtifactRow.cache_key == key)
            ).first()
            if existing is not None:
                existing.payload = payload
                existing.options_json = json.dumps(options or {}, sort_keys=True)
                session.add(existing)
            else:
                session.add(
                    IrArtifactRow(
                        cache_key=key,
                        kind=geometry.kind,
                        source_hash=source_hash,
                        payload=payload,
                        options_json=json.dumps(options or {}, sort_keys=True),
                    )
                )
            session.commit()
    except Exception:  # noqa: BLE001 — cache is an accelerator, never fatal
        _log.warning("ir_cache_store_failed", exc_info=True)


def fetch_geometry(
    source_hash: str,
    options: dict[str, Any] | None,
    *,
    target: Engine = default_engine,
) -> GeometryIR | None:
    """Look up a cached :class:`GeometryIR` for ``(source_hash, options)``."""
    try:
        key = _cache_key("geometry", source_hash, options)
        with Session(target) as session:
            row = session.exec(select(IrArtifactRow).where(IrArtifactRow.cache_key == key)).first()
            if row is None:
                return None
            return GeometryIR.model_validate_json(row.payload.decode("utf-8"))
    except Exception:  # noqa: BLE001 — cache miss on error is the safe default
        _log.warning("ir_cache_fetch_failed", exc_info=True)
        return None
