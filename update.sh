#!/usr/bin/env bash
# Self-update for OmniPlot. Pulls the latest commit on the current branch,
# purges any stale Python bytecode left by the previous install, reinstalls
# backend + frontend dependencies, rebuilds the SPA, and restarts the
# systemd service end-to-end so the operator never needs to drop to SSH.
#
# Usage:
#   ./update.sh              # pull → purge cache → install → build → restart → health-check
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
  # When the previous invocation re-execed us (because update.sh itself
  # was modified by the pull), the upstream we already merged equals the
  # current HEAD — but the purge / install / restart steps below still
  # need to run. Skip the "already up to date" short-circuit on the
  # re-exec leg; only exit early when we genuinely have nothing to do.
  if [ -z "${OMNIPLOT_UPDATE_REEXEC:-}" ]; then
    echo "Already up to date ($PREV_COMMIT)."
    exit 0
  fi
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "Update available: $PREV_COMMIT → $NEW_COMMIT"
  exit 0
fi

if [ -n "${OMNIPLOT_UPDATE_REEXEC:-}" ]; then
  step "Resuming after re-exec (HEAD is already at $NEW_COMMIT)"
else
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
fi

# If the pull changed update.sh itself, re-exec with the freshly-pulled
# version. Bash loads the script into memory at start, so any improvement
# to the post-pull logic (e.g. the bytecode purge below, or a future
# safety fix) would otherwise sit out the very upgrade that delivered it.
# The ``OMNIPLOT_UPDATE_REEXEC`` guard prevents an infinite loop if a
# bug ever made update.sh always claim it was modified.
if [ -z "${OMNIPLOT_UPDATE_REEXEC:-}" ] && \
   ! git diff --quiet "$PREV_COMMIT" "$NEW_COMMIT" -- update.sh; then
  step "update.sh itself changed — re-executing with the new version"
  export OMNIPLOT_UPDATE_REEXEC=1
  # ``$@`` preserves the operator's original flags (--force / --no-restart
  # etc.) across the re-exec, so the rerun continues with the same intent.
  exec "$ROOT/update.sh" "$@"
fi

# Purge any stale Python bytecode before the reinstall + restart. Without
# this step, a ``.pyc`` left behind in ``__pycache__`` whose source file
# was renamed / moved / deleted in the new commit still satisfies the
# import path, and the running backend silently mixes old + new modules.
# Symptoms previously seen on the field: ``GET /files/integrity`` 404'd
# because the new route was on disk but the old ``files.py`` bytecode
# still owned the import; ``Generation failed: 'feed' is undefined``
# because the new templates were on disk but ``gcode.py``'s old bytecode
# didn't pass ``feed=`` to the Jinja render. Cleaning this on every
# update keeps the bytecode in lockstep with the source tree.
step "Purging stale Python bytecode"
find "$ROOT/backend" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT/backend" -type f -name "*.pyc" -delete 2>/dev/null || true

# Run install with --no-system-deps: a self-update should never silently apt-get.
# Pass --no-restart so install.sh's restart hook stays out of the way; we handle
# the restart explicitly here (one well-known place) instead of having both
# scripts try.
step "Reinstalling backend + frontend"
"$ROOT/install.sh" --no-system-deps --no-restart

if [ "$NO_RESTART" -eq 0 ]; then
  if has systemctl && systemctl list-unit-files 2>/dev/null | grep -q '^omniplot\.service'; then
    # Two restart paths:
    #
    # 1. Invoked from a shell (SSH / cron / the bundled installer): restart
    #    synchronously and poll ``/health`` until the new process answers,
    #    so a botched restart surfaces here instead of leaving the operator
    #    staring at a dead UI. The boot-time template-contract guard added
    #    in fix(gcode) is the typical reason a restart fails — catching it
    #    here means the update returns non-zero and the operator sees the
    #    journalctl pointer immediately.
    #
    # 2. Invoked from the web UI's Update button (the running process IS
    #    omniplot itself, see ``api/system.trigger_update``): restarting
    #    synchronously would kill the process before the HTTP response
    #    flushes. Defer via a detached background ``sleep 3 && restart``
    #    so the caller gets its response, and skip the health-check
    #    locally — the UI does its own poll once the response lands.
    #
    # The detector below picks between the two: if our parent process tree
    # includes uvicorn, we're being called from the backend and use the
    # deferred path.
    invoked_from_backend=0
    parent_pid="${PPID:-0}"
    while [ "$parent_pid" -gt 1 ]; do
      cmdline_file="/proc/$parent_pid/cmdline"
      [ -r "$cmdline_file" ] || break
      if tr '\0' ' ' < "$cmdline_file" 2>/dev/null | grep -qE "uvicorn|pen_plotter\.main"; then
        invoked_from_backend=1
        break
      fi
      next_pid="$(awk '/^PPid:/ {print $2; exit}' "/proc/$parent_pid/status" 2>/dev/null || echo 0)"
      [ "$next_pid" = "$parent_pid" ] && break
      parent_pid="$next_pid"
    done

    if [ "$EUID" -eq 0 ]; then
      restart_cmd='systemctl restart omniplot.service'
    else
      # Don't gate on ``sudo -n true`` — the install-service.sh sudoers
      # rule grants NOPASSWD *only* for ``systemctl restart
      # omniplot.service`` (narrow by design), so ``sudo -n true`` always
      # fails for the service user even though the actual restart we
      # care about is permitted. Gating on it left restart_cmd empty,
      # silently skipped the restart, and made the operator see
      # "Updated to NEW_COMMIT" while the old Python code kept running
      # — until they happened to run install.sh from SSH (which restarts
      # directly without the bogus probe). Try the real command instead;
      # failures surface through the eval / deferred subprocess.
      restart_cmd='sudo -n systemctl restart omniplot.service'
    fi

    if [ "$invoked_from_backend" -eq 1 ]; then
      step "Scheduling omniplot.service restart (deferred ~3s — UI poll path)"
      # Pipe through ``logger`` so a failed deferred restart leaves a
      # trace in journalctl instead of vanishing into /dev/null. Without
      # this, a broken sudoers rule (or a typo in $restart_cmd) silently
      # fails and the operator only finds out by noticing stale behaviour.
      setsid sh -c "sleep 3 && { $restart_cmd 2>&1 | logger -t omniplot-restart; }" \
        </dev/null >/dev/null 2>&1 &
      disown 2>/dev/null || true
    else
      step "Restarting omniplot.service"
      if ! eval "$restart_cmd"; then
        echo "Error: failed to restart omniplot.service ($restart_cmd)." >&2
        echo "       Reinstall the sudoers rule with: sudo ./install-service.sh \$USER" >&2
        exit 5
      fi

      # Poll ``/health`` until the new process answers or we run out of
      # tries. ``OMNIPLOT_HEALTH_URL`` lets a non-default port / host
      # override the probe; otherwise we try the unit's configured PORT
      # then fall back to 8000.
      probe_url="${OMNIPLOT_HEALTH_URL:-}"
      if [ -z "$probe_url" ]; then
        probe_port="${PORT:-}"
        if [ -z "$probe_port" ] && [ -f "$ROOT/.env.service" ]; then
          # shellcheck disable=SC1091
          probe_port="$(grep -E '^PORT=' "$ROOT/.env.service" 2>/dev/null | tail -1 | cut -d= -f2 || true)"
        fi
        probe_port="${probe_port:-8000}"
        probe_url="http://127.0.0.1:${probe_port}/health"
      fi
      step "Waiting for $probe_url"
      tries=0
      max_tries=30
      until curl -fsS --max-time 2 "$probe_url" >/dev/null 2>&1; do
        tries=$((tries + 1))
        if [ "$tries" -ge "$max_tries" ]; then
          echo "Error: omniplot.service did not come back healthy after restart." >&2
          echo "       Inspect: sudo journalctl -u omniplot -n 100 --no-pager" >&2
          exit 4
        fi
        sleep 1
      done
      version_line="$(curl -fsS --max-time 2 "$probe_url" 2>/dev/null || true)"
      echo "Service healthy: $version_line"
    fi
  fi
fi

echo
echo "Updated to $NEW_COMMIT."
