"""Optional API-key protection for machine-control endpoints.

Disabled by default so local single-machine use needs no configuration. Set the
``OMNIPLOT_API_KEY`` environment variable to require a matching key on guarded
endpoints, supplied either as an ``X-API-Key`` header or a ``token`` query
parameter (the latter lets browsers authenticate WebSocket connections, which
cannot carry custom headers).
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, Query

API_KEY_ENV = "OMNIPLOT_API_KEY"


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
    if expected not in (x_api_key, token):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
