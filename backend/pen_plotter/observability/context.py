"""Correlation context propagated through contextvars.

The roadmap (`docs/ROADMAP_V0.2.md`, step A.1) requires every backend log
line and span to carry the same set of correlation IDs so a single
request can be traced from upload through render, optimization, gcode
emission, queue execution and machine streaming.

The fields are stored in :data:`contextvars.ContextVar` so they
naturally follow `asyncio` task boundaries — no thread-locals, no
manual passing.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Final

# Canonical correlation field names. Kept in one place so the middleware,
# the JSON formatter, and future OTel attribute mapping stay in sync.
CORRELATION_FIELDS: Final[tuple[str, ...]] = (
    "request_id",
    "job_id",
    "run_id",
    "placement_id",
    "algorithm_id",
    "quality_tier",
    "profile_name",
    "source_kind",
)


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_placement_id: ContextVar[str | None] = ContextVar("placement_id", default=None)
_algorithm_id: ContextVar[str | None] = ContextVar("algorithm_id", default=None)
_quality_tier: ContextVar[str | None] = ContextVar("quality_tier", default=None)
_profile_name: ContextVar[str | None] = ContextVar("profile_name", default=None)
_source_kind: ContextVar[str | None] = ContextVar("source_kind", default=None)


_VARS: Final[dict[str, ContextVar[str | None]]] = {
    "request_id": _request_id,
    "job_id": _job_id,
    "run_id": _run_id,
    "placement_id": _placement_id,
    "algorithm_id": _algorithm_id,
    "quality_tier": _quality_tier,
    "profile_name": _profile_name,
    "source_kind": _source_kind,
}


def bind_context(**fields: str | None) -> dict[str, Token[str | None]]:
    """Bind one or more correlation fields for the current async context.

    Returns the reset tokens so the caller can restore the previous
    values (typically in a ``finally`` clause). Unknown field names are
    rejected to keep the schema tight — adding a new field requires an
    explicit update to :data:`CORRELATION_FIELDS`.
    """
    tokens: dict[str, Token[str | None]] = {}
    for name, value in fields.items():
        var = _VARS.get(name)
        if var is None:
            raise KeyError(f"unknown correlation field: {name!r}")
        tokens[name] = var.set(value)
    return tokens


def clear_context(tokens: dict[str, Token[str | None]]) -> None:
    """Restore the correlation values captured by :func:`bind_context`."""
    for name, token in tokens.items():
        _VARS[name].reset(token)


def get_context() -> dict[str, str]:
    """Return the currently bound correlation fields (non-null only)."""
    return {name: value for name, var in _VARS.items() if (value := var.get()) is not None}
