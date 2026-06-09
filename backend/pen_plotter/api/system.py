"""System-level endpoints: version info and self-update."""

from __future__ import annotations

import asyncio
import contextlib
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
    # Short list of modified / staged / untracked tracked-file changes so the
    # UI can show the operator exactly *what* is dirty before they decide
    # whether to force the update.
    dirty_files: list[str] = []


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Report the package version and (if available) the git checkout state."""
    root = _repo_root()
    is_git = (root / ".git").exists()
    commit = _git("rev-parse", "HEAD") if is_git else None
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") if is_git else None
    dirty = False
    dirty_files: list[str] = []
    if is_git:
        # ``status --porcelain`` lists tracked-file changes and untracked
        # files in a compact ``XY path`` format (X = staged, Y = workspace).
        # We only flag *tracked* edits as dirty (untracked files don't block
        # the update), and surface a capped list to the UI. The status is
        # read via ``check_output`` directly here (not ``_git``) because
        # ``_git`` strips trailing whitespace from the whole blob, which
        # would chew the leading space off the first ``" M path"`` line and
        # break the fixed-index parsing below.
        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
                timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            status = ""
        for line in status.splitlines():
            if len(line) < 3:
                continue
            code = line[:2]
            path = line[3:]
            # "??" = untracked, ignored by the update gate. Anything else is
            # an edit or stage we want the operator to see.
            if code == "??":
                continue
            dirty = True
            if len(dirty_files) < 40:
                dirty_files.append(f"{code.strip() or '·'} {path}")
    return VersionResponse(
        version=__version__,
        commit=commit,
        branch=branch,
        dirty=dirty,
        dirty_files=dirty_files,
    )


class CheckUpdateResponse(BaseModel):
    """Result of ``GET /system/check-update``: is a newer commit available?"""

    # ``True`` only when the remote branch tip is strictly ahead of the local
    # HEAD. ``False`` covers "up to date", "no git", "fetch failed", "dirty
    # tree" — anything where the UI shouldn't nudge the operator to update.
    update_available: bool
    current_commit: str | None
    remote_commit: str | None
    # How many commits the remote is ahead by (0 when up to date or when we
    # can't tell). Surfaced so the toast can say "3 commits behind" if we
    # want it later.
    behind: int
    branch: str | None
    # Set when we couldn't perform the check — e.g. no network, no git, no
    # tracking branch. The UI uses this to silently skip the notification
    # rather than display a noisy error on every page load.
    error: str | None = None


@router.get("/check-update", response_model=CheckUpdateResponse)
async def check_update() -> CheckUpdateResponse:
    """Fetch from the remote and report whether a newer commit exists.

    This is the polling endpoint behind the optional "update available"
    startup toast; it never mutates the working tree (only ``git fetch``)
    and tolerates offline machines by returning ``update_available=False``
    with an ``error`` string instead of raising.
    """
    root = _repo_root()
    if not (root / ".git").exists():
        return CheckUpdateResponse(
            update_available=False,
            current_commit=None,
            remote_commit=None,
            behind=0,
            branch=None,
            error="not a git checkout",
        )

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    current = _git("rev-parse", "HEAD")
    if not branch or branch == "HEAD" or not current:
        return CheckUpdateResponse(
            update_available=False,
            current_commit=current,
            remote_commit=None,
            behind=0,
            branch=branch,
            error="detached HEAD or unknown branch",
        )

    # ``git fetch`` is the only network operation; cap it tightly so a flaky
    # link doesn't hang the page-load toast.
    try:
        fetch = await asyncio.create_subprocess_exec(
            "git",
            "fetch",
            "--quiet",
            "origin",
            branch,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(fetch.communicate(), timeout=15)
        except TimeoutError:
            fetch.kill()
            return CheckUpdateResponse(
                update_available=False,
                current_commit=current,
                remote_commit=None,
                behind=0,
                branch=branch,
                error="git fetch timed out",
            )
        if fetch.returncode != 0:
            return CheckUpdateResponse(
                update_available=False,
                current_commit=current,
                remote_commit=None,
                behind=0,
                branch=branch,
                error="git fetch failed",
            )
    except FileNotFoundError:
        return CheckUpdateResponse(
            update_available=False,
            current_commit=current,
            remote_commit=None,
            behind=0,
            branch=branch,
            error="git not available",
        )

    remote_ref = f"origin/{branch}"
    remote = _git("rev-parse", remote_ref)
    if not remote:
        return CheckUpdateResponse(
            update_available=False,
            current_commit=current,
            remote_commit=None,
            behind=0,
            branch=branch,
            error="no tracking branch",
        )

    # ``rev-list --count HEAD..origin/branch`` reports the number of commits
    # the remote has that we don't — i.e. how far behind we are.
    behind_str = _git("rev-list", "--count", f"HEAD..{remote_ref}")
    try:
        behind = int(behind_str) if behind_str is not None else 0
    except ValueError:
        behind = 0

    return CheckUpdateResponse(
        update_available=behind > 0 and current != remote,
        current_commit=current,
        remote_commit=remote,
        behind=behind,
        branch=branch,
    )


class UpdateRequest(BaseModel):
    """Optional knobs for ``POST /system/update``."""

    # ``force=True`` discards uncommitted local changes (``git reset --hard``)
    # before pulling. Only the UI's explicit "force update" button should set
    # this — never the default Update button.
    force: bool = False


class UpdateResponse(BaseModel):
    """Result of a ``./update.sh`` invocation, suitable for the UI to render."""

    ok: bool
    previous_commit: str | None
    new_commit: str | None
    updated: bool
    log: str
    needs_restart: bool
    # ``forced=True`` indicates ``update.sh --force`` ran, so the operator's
    # local edits were discarded. Useful for the UI to surface a clearer
    # post-update banner ("Local changes were discarded").
    forced: bool = False


@router.post("/update", response_model=UpdateResponse)
async def trigger_update(request: UpdateRequest | None = None) -> UpdateResponse:
    """Run the bundled ``update.sh`` script and return its log.

    The script pulls the latest commit on the current branch and rebuilds
    the frontend. If a new commit is applied, the backend needs a restart
    to load the new Python code — we report that in the response so the UI
    can prompt the operator.

    Pass ``{"force": true}`` to discard uncommitted local changes before
    pulling. Use sparingly — this is irreversible.
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

    force = bool(request.force) if request else False
    previous = _git("rev-parse", "HEAD")

    cmd: list[str] = [str(script)]
    if force:
        cmd.append("--force")
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        # Spawning can fail before the script even runs — most commonly a
        # lost executable bit on update.sh (PermissionError). Without this
        # guard the exception escapes as a bare 500 with no JSON detail and
        # the UI can only show a generic axios message.
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"could not launch update.sh: {exc}",
                "log": "Check that update.sh is executable (chmod +x update.sh).",
                "returncode": -1,
            },
        ) from exc
    try:
        # 10-minute ceiling: npm install + vite build on a Raspberry Pi can be
        # slow but shouldn't legitimately exceed this. Past that, something is
        # wrong and we'd rather surface the timeout than hang the request.
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=600)
    except TimeoutError as exc:
        process.kill()
        with contextlib.suppress(Exception):
            record("system.update_timeout")
        raise HTTPException(status_code=504, detail="update timed out after 10 minutes") from exc

    log = stdout.decode("utf-8", errors="replace") if stdout else ""
    ok = process.returncode == 0
    new = _git("rev-parse", "HEAD") if ok else previous
    updated = ok and previous is not None and new is not None and previous != new
    # Audit is best-effort here: a failed SQLite write (locked/full disk
    # mid-rebuild) must not mask the update result behind a bare 500.
    with contextlib.suppress(Exception):
        record(
            "system.update",
            f"updated={updated} forced={force} previous={previous} "
            f"new={new} rc={process.returncode}",
        )

    if not ok:
        # Surface the failure body so the UI can show actionable error text
        # instead of a generic 500. Dirty-tree refusals (exit 3) are common
        # enough to deserve a specific status code so the UI can route them
        # into the "force update" affordance.
        status = 409 if process.returncode == 3 else 500
        raise HTTPException(
            status_code=status,
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
        forced=force,
    )
