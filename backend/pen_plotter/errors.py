"""Normalized error envelope (RFC 7807-ish) for v0.2 endpoints.

Roadmap step **A.4**. Existing endpoints keep using ``HTTPException``;
new endpoints (manifests + everything from phase B onward) raise
:class:`ApiError`, which the registered handler renders as::

    {
      "code": "manifest.unknown_domain",
      "message": "no manifest registered for domain 'bogus'",
      "details": {...},
      "path": "/manifests/bogus"
    }

The shape is forward-compatible with RFC 7807 (one renamable field
away from ``type``/``title``/``detail``/``instance``) but uses our
``code`` discriminator because the frontend dispatches user-facing
messages on it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    """Wire shape of a normalized API error."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    path: str = ""


class ApiError(Exception):
    """Raise to emit a normalized error response."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the error with the wire-shape fields."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def as_body(self, path: str = "") -> ApiErrorBody:
        """Materialize the response body for ``path``."""
        return ApiErrorBody(
            code=self.code,
            message=self.message,
            details=self.details,
            path=path,
        )


def install_error_handler(app: FastAPI) -> None:
    """Register the global handler that renders :class:`ApiError` instances."""

    async def _handler(request: Request, exc: ApiError) -> JSONResponse:
        body = exc.as_body(path=request.url.path)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    app.add_exception_handler(ApiError, _handler)  # type: ignore[arg-type]
