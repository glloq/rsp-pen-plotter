"""Optional API-key protection for the OmniPlot HTTP/WebSocket API.

Two modes:

* **Open mode** — ``OMNIPLOT_API_KEY`` unset. Endpoints respond as before;
  ``require_api_key`` is a no-op. Keeps a fresh single-machine install
  working without configuration.
* **Locked mode** — ``OMNIPLOT_API_KEY`` set to a non-empty value. Every
  router that mounts ``require_api_key`` (in practice all of them except
  ``/health`` and the static SPA) rejects requests that don't carry the
  matching key in the ``X-API-Key`` header or the ``token`` query
  parameter (the latter exists so browsers can authenticate the
  WebSocket, where custom headers are not available).

Set ``OMNIPLOT_REQUIRE_AUTH=1`` to refuse startup when no key is
configured. Production deployments on a LAN should set both env vars so
an accidental restart without the secret cannot silently expose the
machine controls.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, Query

API_KEY_ENV = "OMNIPLOT_API_KEY"
REQUIRE_AUTH_ENV = "OMNIPLOT_REQUIRE_AUTH"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _matches(expected: str, candidate: str | None) -> bool:
    """Constant-time comparison that handles ``None`` candidates."""
    if candidate is None:
        return False
    return secrets.compare_digest(expected, candidate)


def require_api_key(
    x_api_key: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    """Reject the request when an API key is configured but not matched.

    Raises:
        HTTPException: 401 if a key is configured and the request omits it or
            sends the wrong one.
    """
    expected = os.environ.get(API_KEY_ENV)
    if not expected:
        return
    if not (_matches(expected, x_api_key) or _matches(expected, token)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def verify_auth_configuration() -> None:
    """Refuse startup when strict mode is requested without a configured key.

    Called once during module import of ``pen_plotter.main`` so that a
    misconfigured production deployment fails fast (loud crash in the
    service log) instead of silently coming up with the controls open.

    Raises:
        RuntimeError: When ``OMNIPLOT_REQUIRE_AUTH`` is truthy and
            ``OMNIPLOT_API_KEY`` is empty / unset.
    """
    if _truthy(os.environ.get(REQUIRE_AUTH_ENV)) and not os.environ.get(API_KEY_ENV):
        raise RuntimeError(
            f"{REQUIRE_AUTH_ENV} is set but {API_KEY_ENV} is not. "
            "Configure a strong secret in the environment before starting "
            "the service, or unset the require-auth flag for local use."
        )
