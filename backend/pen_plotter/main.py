"""FastAPI application entry point for the OmniPlot backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pen_plotter import __version__
from pen_plotter.api.algorithms import router as algorithms_router
from pen_plotter.api.fonts import router as fonts_router
from pen_plotter.api.optimize import router as optimize_router
from pen_plotter.api.profiles import router as profiles_router
from pen_plotter.api.upload import router as upload_router
from pen_plotter.converters.defaults import register_default_converters
from pen_plotter.converters.registry import registry

register_default_converters(registry)

app = FastAPI(title="OmniPlot", version=__version__)

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
