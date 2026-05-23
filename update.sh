#!/usr/bin/env bash
# Self-update for OmniPlot. Pulls the latest commit on the current branch,
# reinstalls backend + frontend dependencies, and rebuilds the SPA. Designed
# to be safe to run with the systemd service active — the running backend is
# not killed, but it needs to be restarted to pick up new code.
#
# Usage:
#   ./update.sh             # pull, install, build
#   ./update.sh --restart   # also restart the omniplot systemd service
#   ./update.sh --check     # print whether updates are available, do nothing
#
# Exits non-zero on any failure. All output is captured for the UI to display.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RESTART=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --restart)    RESTART=1 ;;
    --check)      CHECK_ONLY=1 ;;
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

# Refuse to update on top of uncommitted changes — otherwise the merge can
# leave the tree in a half-broken state with no easy recovery.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree has uncommitted changes. Commit, stash or revert them first." >&2
  git status --short
  exit 3
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
git merge --ff-only "origin/$BRANCH"

# Run install with --no-system-deps: a self-update should never silently apt-get.
# If new system deps are required, the operator can rerun install.sh manually.
step "Reinstalling backend + frontend"
"$ROOT/install.sh" --no-system-deps

if [ "$RESTART" -eq 1 ]; then
  if has systemctl && systemctl list-unit-files 2>/dev/null | grep -q '^omniplot\.service'; then
    step "Restarting omniplot service"
    if [ "$EUID" -eq 0 ]; then
      systemctl restart omniplot
    else
      sudo -n systemctl restart omniplot || {
        echo "Warning: could not restart service without password; run 'sudo systemctl restart omniplot' manually." >&2
      }
    fi
  else
    echo "Note: systemd service not installed; restart the backend manually."
  fi
fi

echo
echo "Updated to $NEW_COMMIT."
