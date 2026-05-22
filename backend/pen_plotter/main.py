"""FastAPI application entry point for the OmniPlot backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pen_plotter import __version__
from pen_plotter.api.algorithms import router as algorithms_router
from pen_plotter.api.fonts import router as fonts_router
from pen_plotter.api.generate import router as generate_router
from pen_plotter.api.jobs import router as jobs_router
from pen_plotter.api.macros import router as macros_router
from pen_plotter.api.optimize import router as optimize_router
from pen_plotter.api.plotter import router as plotter_router
from pen_plotter.api.preflight import router as preflight_router
from pen_plotter.api.presets import router as presets_router
from pen_plotter.api.profiles import router as profiles_router
from pen_plotter.api.upload import router as upload_router
from pen_plotter.auth import require_api_key
from pen_plotter.converters.defaults import register_default_converters
from pen_plotter.converters.registry import registry
from pen_plotter.persistence import init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize converters and the database on startup."""
    register_default_converters(registry)
    init_db()
    yield


app = FastAPI(title="OmniPlot", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(algorithms_router)
app.include_router(fonts_router)
app.include_router(profiles_router)
app.include_router(optimize_router)
app.include_router(generate_router)
app.include_router(preflight_router)
# Machine-control endpoints are guarded when OMNIPLOT_API_KEY is set.
app.include_router(plotter_router, dependencies=[Depends(require_api_key)])
app.include_router(jobs_router)
app.include_router(presets_router)
app.include_router(macros_router)


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
