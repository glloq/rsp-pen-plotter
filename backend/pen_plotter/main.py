"""FastAPI application entry point for the OmniPlot backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pen_plotter import __version__

app = FastAPI(title="OmniPlot", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
