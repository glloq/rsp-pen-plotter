"""Structured JSON logging configuration.

The formatter emits one JSON object per log record with a stable schema:

- ``ts``     — ISO-8601 UTC timestamp
- ``level``  — log level name (``INFO``, ``WARNING``, ...)
- ``logger`` — qualified logger name
- ``msg``   — formatted message
- correlation fields from :mod:`pen_plotter.observability.context`
  (only those that are currently bound)
- ``exc``    — formatted traceback, when an exception is attached
- any extra fields passed via ``logger.info("...", extra={"foo": "bar"})``

The configuration is idempotent: calling :func:`configure_logging` more
than once replaces the previous handler instead of stacking duplicates.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, Final

from pen_plotter.observability.context import get_context

# Standard ``LogRecord`` attributes are filtered out of the ``extra``
# payload so they don't double up with the named fields above.
_RESERVED_LOG_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

# Field names whose values get masked before being serialized. The match
# is on the *key*, case-insensitive — values are never inspected. Keep
# the set conservative; we'll grow it as real call sites are audited.
_REDACT_KEYS: Final[frozenset[str]] = frozenset(
    {"api_key", "authorization", "password", "secret", "token", "x-api-key"}
)

_REDACTED_PLACEHOLDER: Final[str] = "***"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (_REDACTED_PLACEHOLDER if k.lower() in _REDACT_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Format log records as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize ``record`` to a single-line JSON string."""
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(get_context())

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_KEYS or key.startswith("_"):
                continue
            if key in payload:
                continue
            payload[key] = _redact(value)

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def _resolve_level() -> int:
    raw = os.environ.get("OMNIPLOT_LOG_LEVEL", "INFO").strip().upper()
    return logging.getLevelNamesMapping().get(raw, logging.INFO)


def configure_logging(*, force: bool = False) -> None:
    """Install the JSON formatter on the root logger.

    Reads ``OMNIPLOT_LOG_LEVEL`` (default ``INFO``) and
    ``OMNIPLOT_LOG_FORMAT`` (``json`` — default — or ``text`` to keep
    the legacy human-friendly format, used by tests that grep stderr).

    Args:
        force: Reinstall the handler even if logging was already
            configured. Useful in tests that toggle env vars.
    """
    root = logging.getLogger()
    fmt = os.environ.get("OMNIPLOT_LOG_FORMAT", "json").strip().lower()

    if not force and getattr(root, "_omniplot_configured", False):
        return

    for handler in list(root.handlers):
        if getattr(handler, "_omniplot_handler", False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler._omniplot_handler = True  # type: ignore[attr-defined]
    if fmt == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(_resolve_level())
    root._omniplot_configured = True  # type: ignore[attr-defined]
