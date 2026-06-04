"""FastAPI application entry point for the OmniPlot backend."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pen_plotter import __version__
from pen_plotter.api.algorithms import router as algorithms_router
from pen_plotter.api.analyze import router as analyze_router
from pen_plotter.api.audit import router as audit_router
from pen_plotter.api.available_colors import router as available_colors_router
from pen_plotter.api.files import router as files_router
from pen_plotter.api.fonts import router as fonts_router
from pen_plotter.api.generate import router as generate_router
from pen_plotter.api.jobs import router as jobs_router
from pen_plotter.api.macros import router as macros_router
from pen_plotter.api.manifests import router as manifests_router
from pen_plotter.api.optimize import router as optimize_router
from pen_plotter.api.plans import router as plans_router
from pen_plotter.api.plotter import router as plotter_router
from pen_plotter.api.policy import router as policy_router
from pen_plotter.api.preflight import router as preflight_router
from pen_plotter.api.presets import router as presets_router
from pen_plotter.api.preview import router as preview_router
from pen_plotter.api.preview_stream import router as preview_stream_router
from pen_plotter.api.preview_text import router as preview_text_router
from pen_plotter.api.profiles import router as profiles_router
from pen_plotter.api.queue import print_queue
from pen_plotter.api.queue import router as queue_router
from pen_plotter.api.rerender import router as rerender_router
from pen_plotter.api.settings import router as settings_router
from pen_plotter.api.slo import router as slo_router
from pen_plotter.api.system import router as system_router
from pen_plotter.api.upload import router as upload_router
from pen_plotter.application.file_library import integrity_scan
from pen_plotter.auth import require_api_key, verify_auth_configuration
from pen_plotter.converters.defaults import register_default_converters
from pen_plotter.converters.registry import registry
from pen_plotter.deployment import capabilities_for, resolve_role
from pen_plotter.domain.slo import (
    evaluator_enabled as slo_evaluator_enabled,
)
from pen_plotter.domain.slo import (
    evaluator_loop as slo_evaluator_loop,
)
from pen_plotter.errors import install_error_handler
from pen_plotter.manifests_seed import register_default_manifests
from pen_plotter.observability import (
    RequestContextMiddleware,
    configure_logging,
    configure_tracing,
)
from pen_plotter.persistence import init_db
from pen_plotter.queue import recover_interrupted
from pen_plotter.rate_limit import install_rate_limit

configure_logging()
_log = logging.getLogger(__name__)

# Fail loud at startup if the operator asked for strict auth but didn't
# configure a key — better than coming up silently with the controls open.
verify_auth_configuration()


def _log_library_integrity() -> None:
    """Scan the file library at boot and warn about rerender-broken entries.

    Lets the operator see in the logs (and via /files/integrity) that
    some bitmap uploads cannot be re-rendered today, instead of finding
    out at the next Edit click.
    """
    try:
        report = integrity_scan()
    except Exception:
        _log.exception("Library integrity scan failed")
        return
    if not report.issues:
        _log.info(
            "Library integrity ok: %d rerenderable file(s) / %d total",
            report.rerenderable,
            report.checked,
        )
        return
    _log.warning(
        "Library integrity: %d issue(s) — files needing re-upload to restore rerender:",
        len(report.issues),
    )
    for issue in report.issues:
        _log.warning("  - %s (%s): %s", issue.source_file, issue.file_id, issue.reason)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize subsystems according to the resolved process role (D.6).

    The default ``monolith`` role keeps the v0.1 behaviour: converters
    + DB + queue worker + hardware transport in one process. Other
    roles skip the subsystems they don't own (an API process leaves
    queue/hardware to a dedicated worker; a render-only worker
    doesn't try to serve HTTP). The role is resolved from
    ``OMNIPLOT_ROLE`` — see :mod:`pen_plotter.deployment`.
    """
    role = resolve_role()
    caps = capabilities_for(role)
    _log.info("process_role", extra={"role": role.value})

    register_default_converters(registry)
    init_db()
    if caps.serves_http:
        _log_library_integrity()
    if caps.runs_queue_worker:
        recover_interrupted()
        print_queue.start()
    # Background SLO evaluator (E.4 wire). Opt-in via
    # ``OMNIPLOT_SLO_EVAL_ENABLED=1`` so dev sessions stay quiet.
    # Owned by the API role (or monolith) so a render-only worker
    # doesn't spin up redundant evaluators.
    slo_task: asyncio.Task[None] | None = None
    if caps.serves_http and slo_evaluator_enabled():
        slo_task = asyncio.create_task(slo_evaluator_loop())
    try:
        yield
    finally:
        if slo_task is not None:
            slo_task.cancel()
            try:
                await slo_task
            except (asyncio.CancelledError, Exception):
                pass
        if caps.runs_queue_worker:
            await print_queue.stop()


app = FastAPI(title="OmniPlot", version=__version__, lifespan=lifespan)
configure_tracing(app)
install_error_handler(app)
register_default_manifests()


def _cors_origins() -> list[str]:
    """Resolve the CORS allow-list from ``OMNIPLOT_CORS_ORIGINS``.

    A comma-separated list of origins (e.g.
    ``http://localhost:5173,https://plotter.local``). Defaults to the
    Vite dev server so the development workflow keeps working out of
    the box; a Pi appliance behind a LAN domain should set this env
    var so browsers from other devices can reach the UI.

    Empty / unset env var ⇒ default (Vite dev server only).

    Raises:
        RuntimeError: If a wildcard origin is combined with credentialed
            requests — browsers reject the combination, and accepting
            it server-side hides the misconfiguration.
    """
    raw = os.environ.get("OMNIPLOT_CORS_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5173"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError(
            "OMNIPLOT_CORS_ORIGINS=* is not allowed: the API is mounted with "
            "allow_credentials=True, which browsers refuse to combine with a "
            "wildcard origin. List the exact origins instead "
            "(e.g. 'http://plotter.local,http://192.168.1.42:5173')."
        )
    return origins


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def _add_security_headers(request, call_next):  # type: ignore[no-untyped-def]
    """Attach defensive headers to every HTTP response.

    Deliberately omits ``Content-Security-Policy``: the SPA renders
    sanitized SVG via ``v-html`` and an over-restrictive CSP would
    break previews. Operators who need CSP should terminate it at a
    reverse proxy together with TLS — see docs/deployment.md.
    """
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
install_rate_limit(app)

# Default-deny: every router carries the API-key dependency so a
# locked-mode deployment (OMNIPLOT_API_KEY set) actually locks the
# whole API surface — uploads, file downloads, profiles, macros, etc.
# When the env var is unset, ``require_api_key`` is a no-op and the
# single-machine workflow keeps working without configuration.
# /health and the static SPA stay open so a browser can bootstrap and
# the operator can land on a login screen.
_GUARDED = [Depends(require_api_key)]

app.include_router(upload_router, dependencies=_GUARDED)
app.include_router(files_router, dependencies=_GUARDED)
app.include_router(algorithms_router, dependencies=_GUARDED)
app.include_router(fonts_router, dependencies=_GUARDED)
app.include_router(profiles_router, dependencies=_GUARDED)
app.include_router(optimize_router, dependencies=_GUARDED)
app.include_router(generate_router, dependencies=_GUARDED)
app.include_router(preflight_router, dependencies=_GUARDED)
app.include_router(plans_router, dependencies=_GUARDED)
app.include_router(policy_router, dependencies=_GUARDED)
app.include_router(plotter_router, dependencies=_GUARDED)
app.include_router(queue_router, dependencies=_GUARDED)
app.include_router(audit_router, dependencies=_GUARDED)
app.include_router(jobs_router, dependencies=_GUARDED)
app.include_router(presets_router, dependencies=_GUARDED)
app.include_router(macros_router, dependencies=_GUARDED)
app.include_router(preview_router, dependencies=_GUARDED)
app.include_router(preview_stream_router, dependencies=_GUARDED)
app.include_router(preview_text_router, dependencies=_GUARDED)
app.include_router(rerender_router, dependencies=_GUARDED)
app.include_router(system_router, dependencies=_GUARDED)
app.include_router(analyze_router, dependencies=_GUARDED)
app.include_router(available_colors_router, dependencies=_GUARDED)
app.include_router(settings_router, dependencies=_GUARDED)
app.include_router(manifests_router, dependencies=_GUARDED)
app.include_router(slo_router, dependencies=_GUARDED)


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str
    version: str


@app.get("/health")
async def health() -> HealthResponse:
    """Report that the API is reachable and which version is running.

    Returns:
        A payload with a fixed ``ok`` status and the package version.
    """
    return HealthResponse(status="ok", version=__version__)


def _static_dir() -> Path | None:
    """Locate the built frontend, if present (production appliance mode)."""
    override = os.environ.get("OMNIPLOT_STATIC_DIR")
    if override:
        candidate = Path(override)
    else:
        candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return candidate if (candidate / "index.html").is_file() else None


# Serve the built single-page app from the same origin when it exists, so one
# process serves both the UI and the API. Mounted last so API routes win.
_STATIC = _static_dir()
if _STATIC is not None:
    app.mount("/", StaticFiles(directory=_STATIC, html=True), name="frontend")
