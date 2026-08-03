import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.auth import (
    ALLOW_INSECURE_LAN_ENV,
    API_KEY_ENV,
    BIND_HOST_ENV,
    REQUIRE_AUTH_ENV,
    _is_local_bind,
    verify_auth_configuration,
)
from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.main import app

PROFILE = "Custom CoreXY A3"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def connected() -> MockTransport:
    transport = MockTransport()
    controller.attach(transport)
    yield transport
    controller.abort()
    controller._transport = None
    controller._streamer = None
    controller._task = None


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "secret-key"
    monkeypatch.setenv(API_KEY_ENV, key)
    return key


@pytest.mark.asyncio
async def test_machine_endpoint_open_without_configured_key(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/home", params={"profile_name": PROFILE})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_machine_endpoint_rejects_missing_key(api_key: str, connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/home", params={"profile_name": PROFILE})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_machine_endpoint_accepts_header_key(api_key: str, connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/home",
            params={"profile_name": PROFILE},
            headers={"X-API-Key": api_key},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_machine_endpoint_rejects_token_query(api_key: str, connected: MockTransport) -> None:
    """The API key must NOT be accepted in the query string on HTTP routes
    (P1.9) — a key in a URL leaks into logs / history. Header only."""
    async with _client() as client:
        response = await client.post(
            "/plotter/home",
            params={"profile_name": PROFILE, "token": api_key},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_preflight_guarded_when_key_set(api_key: str) -> None:
    """Default-deny: every router (including preflight) is locked when a
    key is configured. Operators must include the key on all calls."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" viewBox="0 0 100 100">'
        '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 90"/></g></svg>'
    )
    async with _client() as client:
        no_key = await client.post("/preflight", json={"svg": svg, "profile_name": PROFILE})
    assert no_key.status_code == 401
    async with _client() as client:
        with_key = await client.post(
            "/preflight",
            json={"svg": svg, "profile_name": PROFILE},
            headers={"X-API-Key": api_key},
        )
    assert with_key.status_code == 200


@pytest.mark.asyncio
async def test_file_download_guarded_when_key_set(api_key: str) -> None:
    """Originals must not leak: ``GET /files/{id}/original`` requires the
    key once one is configured, even if the file id leaks."""
    async with _client() as client:
        response = await client.get("/files/does-not-exist/original")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_open_when_key_set(api_key: str) -> None:
    """``/health`` stays open in locked mode so a load balancer / systemd
    healthcheck doesn't need to know the secret."""
    async with _client() as client:
        response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_queue_get_guarded_when_key_set(api_key: str) -> None:
    """PrintRun.pause_points contains operator-facing prompts that should
    not leak when an API key is configured."""
    async with _client() as client:
        no_key = await client.get("/queue")
    assert no_key.status_code == 401
    async with _client() as client:
        with_key = await client.get("/queue", headers={"X-API-Key": api_key})
    assert with_key.status_code == 200


@pytest.mark.asyncio
async def test_queue_get_open_without_configured_key() -> None:
    """Backwards-compatible: with no key configured, GET /queue stays open."""
    async with _client() as client:
        response = await client.get("/queue")
    assert response.status_code == 200


def test_websocket_rejects_missing_token(api_key: str) -> None:
    """The /ws/plotter WebSocket validates the ``token`` query param itself
    because FastAPI router-level dependencies don't apply to WS routes."""
    # Use the WebSocket handler directly without going through the full
    # ASGI lifespan, which would start the queue worker on this event loop
    # and conflict with other async fixtures.
    from starlette.routing import WebSocketRoute

    ws_route = next(
        r for r in app.router.routes if isinstance(r, WebSocketRoute) and r.path == "/ws/plotter"
    )
    closes: list[tuple[int, str]] = []
    accepts: list[bool] = []

    class FakeWebSocket:
        def __init__(self, query: str = "") -> None:
            self.query_params = {
                k: v for k, v in (kv.split("=", 1) for kv in query.split("&") if kv)
            }

        async def accept(self) -> None:
            accepts.append(True)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            closes.append((code, reason))

        async def send_json(self, data: dict) -> None:  # noqa: ARG002
            pass

    import asyncio

    # No token → close 1008.
    asyncio.run(ws_route.endpoint(FakeWebSocket("")))
    assert (1008, "Invalid or missing API key.") in closes
    assert not accepts

    # Wrong token → close 1008.
    closes.clear()
    accepts.clear()
    asyncio.run(ws_route.endpoint(FakeWebSocket("token=wrong")))
    assert (1008, "Invalid or missing API key.") in closes
    assert not accepts


def test_strict_mode_refuses_startup_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production deployments should fail loud rather than silently come up
    open when the operator asked for strict auth but forgot the key."""
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv(REQUIRE_AUTH_ENV, "1")
    with pytest.raises(RuntimeError, match=REQUIRE_AUTH_ENV):
        verify_auth_configuration()


def test_strict_mode_passes_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    monkeypatch.setenv(REQUIRE_AUTH_ENV, "1")
    verify_auth_configuration()  # no raise


def test_strict_mode_no_op_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_AUTH_ENV, raising=False)
    verify_auth_configuration()  # no raise — open mode is allowed


def _clear_bind_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in (API_KEY_ENV, REQUIRE_AUTH_ENV, BIND_HOST_ENV, ALLOW_INSECURE_LAN_ENV):
        monkeypatch.delenv(env, raising=False)


@pytest.mark.parametrize(
    "host,local",
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.10", False),
    ],
)
def test_is_local_bind_classifies_hosts(host: str, local: bool) -> None:
    assert _is_local_bind(host) is local


def test_remote_bind_without_key_refuses_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-local bind in open mode would expose machine control to the LAN
    (P0.3) — startup must fail loud."""
    _clear_bind_env(monkeypatch)
    monkeypatch.setenv(BIND_HOST_ENV, "0.0.0.0")
    with pytest.raises(RuntimeError, match="reachable off this machine"):
        verify_auth_configuration()


def test_remote_bind_with_key_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_bind_env(monkeypatch)
    monkeypatch.setenv(BIND_HOST_ENV, "0.0.0.0")
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    verify_auth_configuration()  # no raise


def test_remote_bind_allowed_with_explicit_insecure_optin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_bind_env(monkeypatch)
    monkeypatch.setenv(BIND_HOST_ENV, "192.168.1.10")
    monkeypatch.setenv(ALLOW_INSECURE_LAN_ENV, "1")
    verify_auth_configuration()  # no raise — operator knowingly opted in


def test_local_bind_without_key_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loopback in open mode stays the friction-free default for a fresh
    single-machine install."""
    _clear_bind_env(monkeypatch)
    monkeypatch.setenv(BIND_HOST_ENV, "127.0.0.1")
    verify_auth_configuration()  # no raise


def test_unknown_bind_host_does_not_enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """A direct uvicorn launch that doesn't export the bind host is the
    operator's responsibility — the guard stays silent rather than guessing."""
    _clear_bind_env(monkeypatch)  # BIND_HOST_ENV unset
    verify_auth_configuration()  # no raise


def test_cors_wildcard_with_credentials_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OMNIPLOT_CORS_ORIGINS=*`` is unsafe with credentialed requests
    and must be refused at startup."""
    from pen_plotter.main import _cors_origins

    monkeypatch.setenv("OMNIPLOT_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="wildcard"):
        _cors_origins()


def test_api_key_matches_tolerates_non_ascii_candidate() -> None:
    """A client-supplied non-ASCII key/token must yield a clean non-match, not
    a ``TypeError`` (which would surface as an unhandled 500)."""
    from pen_plotter.auth import api_key_matches

    # Non-ASCII bytes in the candidate (e.g. ``X-API-Key: \xff``) used to crash
    # ``secrets.compare_digest`` on ``str`` inputs.
    assert api_key_matches("s3kr1t", "\xff\xfe") is False
    assert api_key_matches("s3kr1t", None) is False
    assert api_key_matches("s3kr1t", "wrong") is False
    assert api_key_matches("s3kr1t", "s3kr1t") is True
