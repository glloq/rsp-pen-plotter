#!/usr/bin/env bash
# Launch OmniPlot.
#
#   ./start.sh            # production appliance (default): one process serves
#                         # the built UI and the API on $HOST:$PORT.
#   ./start.sh --dev      # development: backend with --reload + Vite hot reload.
#
# Environment:
#   HOST  (default 127.0.0.1)       interface to bind. Loopback by default so a
#                                   fresh install is not exposed; set to
#                                   0.0.0.0 to serve the LAN (requires a key,
#                                   see below).
#   PORT  (default 8000)            API/UI port in production mode.
#   OMNIPLOT_API_KEY                if set, machine-control endpoints require
#                                   the same key. Required for any non-local
#                                   bind unless OMNIPLOT_ALLOW_INSECURE_LAN=1.
#   OMNIPLOT_ALLOW_INSECURE_LAN     set to 1 to knowingly bind the LAN without
#                                   a key (not recommended — exposes machine
#                                   control to the whole network).
set -euo pipefail

# systemd gives services a minimal PATH; make sure user-installed tools
# (notably uv in ~/.local/bin) are reachable.
export PATH="${HOME:-/root}/.local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODE="prod"
case "${1:-}" in
  --dev)  MODE="dev" ;;
  --prod) MODE="prod" ;;
  "")     ;;
  *) echo "Usage: $0 [--dev|--prod]"; exit 2 ;;
esac

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# Let the backend's startup guard (pen_plotter.auth.verify_auth_configuration)
# see which interface we bound, so it can refuse an unauthenticated remote bind.
export OMNIPLOT_BIND_HOST="$HOST"

_truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

is_local_host() {
  case "$1" in
    localhost|"" | 127.* | ::1 | "[::1]") return 0 ;;
    *) return 1 ;;
  esac
}

# Fail fast (before uvicorn binds) on an open LAN bind: a non-local host with
# no API key exposes jog / homing / GPIO / self-update to the whole network.
if ! is_local_host "$HOST"; then
  if [ -z "${OMNIPLOT_API_KEY:-}" ] && ! _truthy "${OMNIPLOT_ALLOW_INSECURE_LAN:-}"; then
    echo "Error: refusing to bind '$HOST' (reachable off this machine) with no OMNIPLOT_API_KEY." >&2
    echo "       Machine control would be open to the whole network." >&2
    echo "       Fix: export OMNIPLOT_API_KEY=<strong secret>   (recommended)" >&2
    echo "        or: export OMNIPLOT_ALLOW_INSECURE_LAN=1       (open LAN, not recommended)" >&2
    exit 1
  fi
fi

backend_run() {
  cd "$ROOT/backend"
  if command -v uv >/dev/null 2>&1; then
    uv run uvicorn pen_plotter.main:app "$@"
  elif [ -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
    "$ROOT/backend/.venv/bin/uvicorn" pen_plotter.main:app "$@"
  else
    # Surface the diagnosis to journalctl so an operator hitting "server
    # inaccessible" after a boot can see why directly in ``journalctl -u
    # omniplot`` instead of having to bisect the install state.
    echo "Error: backend not installed (uv missing and no .venv at $ROOT/backend/.venv)." >&2
    echo "       HOME=${HOME:-<unset>}  PATH=$PATH" >&2
    echo "       Fix: run './install.sh' on this host." >&2
    exit 1
  fi
}

lan_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
  fi
}

if [ "$MODE" = "prod" ]; then
  if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
    echo "Error: frontend not built (missing $ROOT/frontend/dist/index.html)." >&2
    echo "       Fix: run './install.sh' on this host to rebuild the SPA." >&2
    exit 1
  fi
  ip="$(lan_ip)"
  echo "==> OmniPlot (production)"
  echo "    Local:    http://localhost:$PORT"
  [ -n "$ip" ] && echo "    Network:  http://$ip:$PORT"
  if ! is_local_host "$HOST" && [ -z "${OMNIPLOT_API_KEY:-}" ]; then
    # We only reach here on a non-local bind with OMNIPLOT_ALLOW_INSECURE_LAN=1
    # (otherwise the guard above already exited). Make the exposure loud.
    echo "    WARNING: bound to $HOST with no API key — machine control is open to the LAN."
    echo "             Set OMNIPLOT_API_KEY=... to require a key."
  fi
  backend_run --host "$HOST" --port "$PORT"
else
  echo "==> OmniPlot (development)"
  echo "    API:  http://localhost:$PORT"
  echo "    UI:   http://localhost:5173"
  trap 'kill 0' INT TERM EXIT
  backend_run --host "$HOST" --port "$PORT" --reload &
  (cd "$ROOT/frontend" && npm run dev -- --host "$HOST") &
  wait
fi
