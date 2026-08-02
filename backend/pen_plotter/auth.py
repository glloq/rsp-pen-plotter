"""Optional API-key protection for the OmniPlot HTTP/WebSocket API.

Two modes:

* **Open mode** — ``OMNIPLOT_API_KEY`` unset. Endpoints respond as before;
  ``require_api_key`` is a no-op. Keeps a fresh single-machine install
  working without configuration.
* **Locked mode** — ``OMNIPLOT_API_KEY`` set to a non-empty value. Every
  router that mounts ``require_api_key`` (in practice all of them except
  ``/health`` and the static SPA) rejects requests that don't carry the
  matching key in the ``X-API-Key`` **header**. The key is NOT accepted in
  the query string for HTTP routes (P1.9): a key in a URL leaks into Uvicorn
  and reverse-proxy access logs, browser history, ``Referer`` headers and
  error captures. WebSockets — where the browser API can't set a custom
  header — carry the key in a ``token`` query parameter that each WebSocket
  endpoint validates itself (see ``plotter_ws`` / ``queue_ws``), so that
  narrow, unavoidable exception stays out of the shared HTTP dependency.

Set ``OMNIPLOT_REQUIRE_AUTH=1`` to refuse startup when no key is
configured. Production deployments on a LAN should set both env vars so
an accidental restart without the secret cannot silently expose the
machine controls.

Independently of that opt-in, :func:`verify_auth_configuration` refuses to
start when the process is bound to a **non-local** address (anything other
than loopback) without a key — a remote bind exposes jog / homing / macros /
GPIO / self-update to the whole LAN, and open mode makes ``require_api_key`` a
no-op. ``start.sh`` exports the bind host as ``OMNIPLOT_BIND_HOST`` so this
guard sees it. Set ``OMNIPLOT_ALLOW_INSECURE_LAN=1`` to knowingly bind the LAN
without authentication (not recommended).
"""

from __future__ import annotations

import ipaddress
import os
import secrets

from fastapi import Header, HTTPException

API_KEY_ENV = "OMNIPLOT_API_KEY"
REQUIRE_AUTH_ENV = "OMNIPLOT_REQUIRE_AUTH"
# Bind host the server was launched with (exported by ``start.sh``). Used only
# to decide whether open mode is safe — the actual bind is uvicorn's job.
BIND_HOST_ENV = "OMNIPLOT_BIND_HOST"
ALLOW_INSECURE_LAN_ENV = "OMNIPLOT_ALLOW_INSECURE_LAN"

# Hostnames that only ever reach this machine.
_LOCAL_HOSTNAMES = {"localhost", ""}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_local_bind(host: str | None) -> bool:
    """True when ``host`` only exposes the API to this machine (loopback).

    ``0.0.0.0`` / ``::`` (all interfaces) and any concrete LAN address count
    as remote; ``127.0.0.0/8``, ``::1`` and ``localhost`` are local.
    """
    candidate = (host or "").strip().lower().strip("[]")
    if candidate in _LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        # An unresolved hostname other than "localhost" — treat as remote so
        # an ambiguous bind never silently runs open.
        return False


def _matches(expected: str, candidate: str | None) -> bool:
    """Constant-time comparison that handles ``None`` candidates."""
    if candidate is None:
        return False
    return secrets.compare_digest(expected, candidate)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject the HTTP request when an API key is configured but not matched.

    Header-only by design (P1.9): the key must arrive in ``X-API-Key`` and is
    never read from the query string, so it can't leak into access logs or
    browser history. WebSocket endpoints validate their own ``token`` query
    param separately.

    Raises:
        HTTPException: 401 if a key is configured and the request omits it or
            sends the wrong one.
    """
    expected = os.environ.get(API_KEY_ENV)
    if not expected:
        return
    if not _matches(expected, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def verify_auth_configuration() -> None:
    """Refuse startup when strict mode is requested without a configured key.

    Called once during module import of ``pen_plotter.main`` so that a
    misconfigured production deployment fails fast (loud crash in the
    service log) instead of silently coming up with the controls open.

    Raises:
        RuntimeError: When ``OMNIPLOT_REQUIRE_AUTH`` is truthy and
            ``OMNIPLOT_API_KEY`` is empty / unset, or when the server is bound
            to a non-local address without a key and without the explicit
            ``OMNIPLOT_ALLOW_INSECURE_LAN`` opt-in.
    """
    api_key = os.environ.get(API_KEY_ENV)
    if _truthy(os.environ.get(REQUIRE_AUTH_ENV)) and not api_key:
        raise RuntimeError(
            f"{REQUIRE_AUTH_ENV} is set but {API_KEY_ENV} is not. "
            "Configure a strong secret in the environment before starting "
            "the service, or unset the require-auth flag for local use."
        )

    # Refuse an unauthenticated remote bind: open mode + a LAN-reachable
    # address would expose machine control (jog, homing, GPIO, self-update)
    # to anyone on the network. Only enforced when the bind host is known
    # (start.sh exports it); a direct ``uvicorn`` launch is the operator's
    # responsibility.
    bind_host = os.environ.get(BIND_HOST_ENV)
    if (
        bind_host is not None
        and not _is_local_bind(bind_host)
        and not api_key
        and not _truthy(os.environ.get(ALLOW_INSECURE_LAN_ENV))
    ):
        raise RuntimeError(
            f"Refusing to start: bound to {bind_host!r}, reachable off this "
            f"machine, with no {API_KEY_ENV}. Machine control would be open to "
            f"the whole network. Set {API_KEY_ENV} to a strong secret, or set "
            f"{ALLOW_INSECURE_LAN_ENV}=1 to bind the LAN without authentication "
            "(not recommended)."
        )
