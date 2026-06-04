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

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
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


def _status_slug(status_code: int) -> str:
    """Return a snake_case slug for an HTTP status, used as a fallback ``code``.

    Maps e.g. 404 → ``"not_found"``, 409 → ``"conflict"``. When the
    status code is non-standard, falls back to ``"http_<code>"`` so the
    envelope still carries a stable, machine-readable discriminator.
    """
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return f"http_{status_code}"
    return phrase.lower().replace(" ", "_").replace("-", "_")


def _coerce_detail(detail: Any) -> tuple[str, dict[str, Any]]:
    """Split a FastAPI ``HTTPException.detail`` into ``(message, details)``.

    Plain strings become the message with empty details. Lists (typical
    of Pydantic validation errors) and dicts move into ``details`` so
    the wire envelope keeps the single-string ``message`` invariant the
    frontend relies on.
    """
    if isinstance(detail, str):
        return detail, {}
    if isinstance(detail, list):
        return "validation_error", {"errors": detail}
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "error")
        return message, {k: v for k, v in detail.items() if k not in {"message", "detail"}}
    return str(detail), {}


def install_error_handler(app: FastAPI) -> None:
    """Register handlers that render every error as the :class:`ApiError` shape.

    Three handlers cooperate:

    * :class:`ApiError` — explicit raises from v0.2+ endpoints.
    * :class:`HTTPException` — legacy v0.1 endpoints; the body is
      coerced into the same envelope so the SPA only handles one error
      shape. The ``code`` field is derived from the status phrase
      (``not_found``, ``conflict``, …) when the caller didn't pass an
      explicit one.
    * :class:`RequestValidationError` — Pydantic input rejections, mapped
      to ``code="validation_error"`` with the field errors in ``details``.
    """

    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        body = exc.as_body(path=request.url.path)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        message, details = _coerce_detail(exc.detail)
        body = ApiErrorBody(
            code=_status_slug(exc.status_code),
            message=message,
            details=details,
            path=request.url.path,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # ``exc.errors()`` may carry Pydantic ``ctx`` values that are
        # raw Python exceptions (not JSON-serializable). ``jsonable_encoder``
        # is FastAPI's own coercion helper — same path the default 422
        # handler uses — so the envelope renders without 500ing.
        errors = jsonable_encoder(exc.errors())
        body = ApiErrorBody(
            code="validation_error",
            message="request validation failed",
            details={"errors": errors},
            path=request.url.path,
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    app.add_exception_handler(ApiError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
