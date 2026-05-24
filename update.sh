#!/usr/bin/env bash
# Self-update for OmniPlot. Pulls the latest commit on the current branch,
# reinstalls backend + frontend dependencies, and rebuilds the SPA. Designed
# to be safe to run with the systemd service active — the running backend is
# not killed, but it needs to be restarted to pick up new code.
#
# Usage:
#   ./update.sh              # pull, install, build, restart service if installed
#   ./update.sh --no-restart # skip the service restart at the end
#   ./update.sh --check      # print whether updates are available, do nothing
#   ./update.sh --force      # discard local changes (git reset --hard) then pull
#   ./update.sh --restart    # accepted for backwards compatibility (no-op:
#                            # restart is now the default behaviour)
#
# Exits non-zero on any failure. All output is captured for the UI to display.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

NO_RESTART=0
CHECK_ONLY=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --restart)    ;;  # accepted for compat — restart is now the default
    --no-restart) NO_RESTART=1 ;;
    --check)      CHECK_ONLY=1 ;;
    --force)      FORCE=1 ;;
    --help|-h)
      awk '
        NR == 1 { next }
        /^[^#]/ { exit }
        { sub(/^# ?/, ""); print }
      ' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

has() { command -v "$1" >/dev/null 2>&1; }
step() { echo; echo "==> $*"; }

if [ ! -d .git ]; then
  echo "Error: $ROOT is not a git checkout — cannot self-update." >&2
  exit 1
fi

# Refuse to update on top of uncommitted changes — unless --force is set,
# in which case we discard them before pulling.
if ! git diff --quiet || ! git diff --cached --quiet; then
  if [ "$FORCE" -eq 0 ]; then
    echo "Error: working tree has uncommitted changes. Re-run with --force to discard them, or commit/stash first." >&2
    git status --short
    exit 3
  fi
  step "Discarding local changes (--force)"
  git status --short
  git reset --hard HEAD
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
PREV_COMMIT="$(git rev-parse HEAD)"

step "Fetching origin/$BRANCH"
git fetch --quiet origin "$BRANCH"

NEW_COMMIT="$(git rev-parse "origin/$BRANCH")"

if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
  echo "Already up to date ($PREV_COMMIT)."
  exit 0
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "Update available: $PREV_COMMIT → $NEW_COMMIT"
  exit 0
fi

step "Updating $PREV_COMMIT → $NEW_COMMIT"
# --force already did a hard reset to local HEAD, which can lag behind the
# remote. Use --ff-only as the default safe path; on --force we additionally
# allow a hard reset to the remote so divergent local commits (rare in
# practice) don't block the update.
if [ "$FORCE" -eq 1 ]; then
  git reset --hard "origin/$BRANCH"
else
  git merge --ff-only "origin/$BRANCH"
fi

# Run install with --no-system-deps: a self-update should never silently apt-get.
# Pass --no-restart so install.sh's restart hook stays out of the way; we handle
# the restart explicitly here (one well-known place) instead of having both
# scripts try.
step "Reinstalling backend + frontend"
"$ROOT/install.sh" --no-system-deps --no-restart

if [ "$NO_RESTART" -eq 0 ]; then
  if has systemctl && systemctl list-unit-files 2>/dev/null | grep -q '^omniplot\.service'; then
    # Defer the restart: when this script is invoked via the web UI's Update
    # button, the calling process IS the omniplot backend, and restarting
    # synchronously would kill it before the HTTP response goes out. A short
    # sleep in a detached background process lets the response flush first.
    # When invoked from a shell, the delay is harmless.
    step "Scheduling omniplot.service restart (in ~3s)"
    if [ "$EUID" -eq 0 ]; then
      restart_cmd='systemctl restart omniplot.service'
    elif sudo -n true 2>/dev/null; then
      restart_cmd='sudo -n systemctl restart omniplot.service'
    else
      restart_cmd=''
      echo "Warning: cannot restart omniplot without a password." >&2
      echo "         Run 'sudo systemctl restart omniplot' manually, or reinstall" >&2
      echo "         the service (./install-service.sh) to add the sudoers rule." >&2
    fi
    if [ -n "$restart_cmd" ]; then
      setsid sh -c "sleep 3 && $restart_cmd" </dev/null >/dev/null 2>&1 &
      disown 2>/dev/null || true
    fi
  fi
fi

echo
echo "Updated to $NEW_COMMIT."
