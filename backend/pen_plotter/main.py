"""FastAPI application entry point for the OmniPlot backend."""

from __future__ import annotations

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
from pen_plotter.api.optimize import router as optimize_router
from pen_plotter.api.plans import router as plans_router
from pen_plotter.api.plotter import router as plotter_router
from pen_plotter.api.preflight import router as preflight_router
from pen_plotter.api.presets import router as presets_router
from pen_plotter.api.preview import router as preview_router
from pen_plotter.api.preview_text import router as preview_text_router
from pen_plotter.api.profiles import router as profiles_router
from pen_plotter.api.queue import print_queue
from pen_plotter.api.queue import router as queue_router
from pen_plotter.api.rerender import router as rerender_router
from pen_plotter.api.settings import router as settings_router
from pen_plotter.api.system import router as system_router
from pen_plotter.api.upload import router as upload_router
from pen_plotter.application.file_library import integrity_scan
from pen_plotter.auth import require_api_key
from pen_plotter.converters.defaults import register_default_converters
from pen_plotter.converters.registry import registry
from pen_plotter.persistence import init_db
from pen_plotter.queue import recover_interrupted

_log = logging.getLogger(__name__)


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
    """Initialize converters and the database, then run the print-queue worker."""
    register_default_converters(registry)
    init_db()
    _log_library_integrity()
    recover_interrupted()
    print_queue.start()
    try:
        yield
    finally:
        await print_queue.stop()


app = FastAPI(title="OmniPlot", version=__version__, lifespan=lifespan)


def _cors_origins() -> list[str]:
    """Resolve the CORS allow-list from ``OMNIPLOT_CORS_ORIGINS``.

    A comma-separated list of origins (e.g.
    ``http://localhost:5173,https://plotter.local``). Defaults to the
    Vite dev server so the development workflow keeps working out of
    the box; a Pi appliance behind a LAN domain should set this env
    var so browsers from other devices can reach the UI.

    Empty / unset env var ⇒ default (Vite dev server only).
    """
    raw = os.environ.get("OMNIPLOT_CORS_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(files_router)
app.include_router(algorithms_router)
app.include_router(fonts_router)
app.include_router(profiles_router)
app.include_router(optimize_router)
app.include_router(generate_router)
app.include_router(preflight_router)
app.include_router(plans_router)
# Machine-control endpoints are guarded when OMNIPLOT_API_KEY is set.
app.include_router(plotter_router, dependencies=[Depends(require_api_key)])
app.include_router(queue_router)
app.include_router(audit_router)
app.include_router(jobs_router)
app.include_router(presets_router)
app.include_router(macros_router)
app.include_router(preview_router)
app.include_router(preview_text_router)
app.include_router(rerender_router)
app.include_router(system_router)
app.include_router(analyze_router)
app.include_router(available_colors_router)
app.include_router(settings_router)


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
