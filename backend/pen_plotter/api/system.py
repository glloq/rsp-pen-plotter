"""System-level endpoints: version info and self-update."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pen_plotter import __version__
from pen_plotter.audit import record
from pen_plotter.auth import require_api_key


router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_api_key)])


def _repo_root() -> Path:
    """Locate the git checkout root (parent of the ``backend`` directory)."""
    # ``__file__`` is at backend/pen_plotter/api/system.py, so .parents[3] is
    # the repo root where ``update.sh`` and the ``.git`` directory live.
    return Path(__file__).resolve().parents[3]


def _git(*args: str, cwd: Path | None = None) -> str | None:
    """Run a git command and return stdout, or ``None`` on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or _repo_root(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


class VersionResponse(BaseModel):
    """Currently-installed OmniPlot version and git state."""

    version: str
    commit: str | None
    branch: str | None
    dirty: bool


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Report the package version and (if available) the git checkout state."""
    root = _repo_root()
    is_git = (root / ".git").exists()
    commit = _git("rev-parse", "HEAD") if is_git else None
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") if is_git else None
    dirty = False
    if is_git:
        status = _git("status", "--porcelain")
        dirty = bool(status)
    return VersionResponse(
        version=__version__,
        commit=commit,
        branch=branch,
        dirty=dirty,
    )


class UpdateResponse(BaseModel):
    """Result of a ``./update.sh`` invocation, suitable for the UI to render."""

    ok: bool
    previous_commit: str | None
    new_commit: str | None
    updated: bool
    log: str
    needs_restart: bool


@router.post("/update", response_model=UpdateResponse)
async def trigger_update() -> UpdateResponse:
    """Run the bundled ``update.sh`` script and return its log.

    The script pulls the latest commit on the current branch and rebuilds
    the frontend. If a new commit is applied, the backend needs a restart
    to load the new Python code — we report that in the response so the UI
    can prompt the operator.
    """
    root = _repo_root()
    script = root / "update.sh"
    if not script.is_file():
        raise HTTPException(status_code=500, detail="update.sh is missing from the checkout")
    if not (root / ".git").exists():
        raise HTTPException(status_code=400, detail="not running from a git checkout")
    # Operators can opt out of self-updates entirely (managed deployments) by
    # setting ``OMNIPLOT_DISABLE_UPDATE=1`` in the systemd unit's environment.
    if os.environ.get("OMNIPLOT_DISABLE_UPDATE"):
        raise HTTPException(status_code=403, detail="self-update is disabled on this host")

    previous = _git("rev-parse", "HEAD")

    process = await asyncio.create_subprocess_exec(
        str(script),
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        # 10-minute ceiling: npm install + vite build on a Raspberry Pi can be
        # slow but shouldn't legitimately exceed this. Past that, something is
        # wrong and we'd rather surface the timeout than hang the request.
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=600)
    except asyncio.TimeoutError:
        process.kill()
        record("system.update_timeout")
        raise HTTPException(status_code=504, detail="update timed out after 10 minutes")

    log = stdout.decode("utf-8", errors="replace") if stdout else ""
    ok = process.returncode == 0
    new = _git("rev-parse", "HEAD") if ok else previous
    updated = ok and previous is not None and new is not None and previous != new
    record(
        "system.update",
        f"updated={updated} previous={previous} new={new} rc={process.returncode}",
    )

    if not ok:
        # Surface the failure body so the UI can show actionable error text
        # instead of a generic 500.
        raise HTTPException(
            status_code=500,
            detail={"message": "update.sh failed", "log": log, "returncode": process.returncode},
        )

    return UpdateResponse(
        ok=True,
        previous_commit=previous,
        new_commit=new,
        updated=updated,
        log=log,
        # The Python process is still running the old code path; only a
        # restart picks up Python-side changes. (Frontend changes are picked
        # up on the next page reload.)
        needs_restart=updated,
    )
