#!/usr/bin/env bash
# Launch OmniPlot.
#
#   ./start.sh            # production appliance (default): one process serves
#                         # the built UI and the API on $HOST:$PORT.
#   ./start.sh --dev      # development: backend with --reload + Vite hot reload.
#
# Environment:
#   HOST  (default 0.0.0.0)         interface to bind, set to 127.0.0.1 to
#                                   restrict access to this machine.
#   PORT  (default 8000)            API/UI port in production mode.
#   OMNIPLOT_API_KEY                if set, machine-control endpoints require
#                                   the same key (recommended on a LAN).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODE="prod"
case "${1:-}" in
  --dev)  MODE="dev" ;;
  --prod) MODE="prod" ;;
  "")     ;;
  *) echo "Usage: $0 [--dev|--prod]"; exit 2 ;;
esac

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

backend_run() {
  cd "$ROOT/backend"
  if command -v uv >/dev/null 2>&1; then
    uv run uvicorn pen_plotter.main:app "$@"
  elif [ -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
    "$ROOT/backend/.venv/bin/uvicorn" pen_plotter.main:app "$@"
  else
    echo "Error: backend is not installed. Run ./install.sh first." >&2
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
    echo "Error: frontend is not built. Run ./install.sh first." >&2
    exit 1
  fi
  ip="$(lan_ip)"
  echo "==> OmniPlot (production)"
  echo "    Local:    http://localhost:$PORT"
  [ -n "$ip" ] && echo "    Network:  http://$ip:$PORT"
  if [ -z "${OMNIPLOT_API_KEY:-}" ] && [ "$HOST" = "0.0.0.0" ]; then
    echo "    Tip: set OMNIPLOT_API_KEY=... to require an API key for machine control."
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
