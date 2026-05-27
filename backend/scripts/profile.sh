#!/usr/bin/env bash
# Wrapper around py-spy for the OmniPlot backend (roadmap D.1).
#
# Two modes:
#   - record  attach to a running backend and dump a flamegraph
#   - top     live "top"-style breakdown
#
# Usage:
#   scripts/profile.sh record --duration 30 --output flame.svg
#   scripts/profile.sh top
#
# Targets the uvicorn worker by default (pgrep "uvicorn"); set
# OMNIPLOT_PID=<pid> to attach to a specific process instead.

set -euo pipefail

cmd="${1:-record}"
shift || true

if [[ -z "${OMNIPLOT_PID:-}" ]]; then
  if ! pgrep -f "uvicorn" > /dev/null; then
    echo "no uvicorn process found; start the backend first or set OMNIPLOT_PID=<pid>" >&2
    exit 1
  fi
  OMNIPLOT_PID="$(pgrep -f "uvicorn" | head -n1)"
fi

if ! command -v py-spy > /dev/null; then
  echo "py-spy not installed; pip install py-spy or use the dev container" >&2
  exit 1
fi

case "$cmd" in
  record)
    duration=30
    output="flame.svg"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --duration) duration="$2"; shift 2 ;;
        --output)   output="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    echo "recording $duration s into $output (PID $OMNIPLOT_PID)..."
    exec py-spy record --pid "$OMNIPLOT_PID" --duration "$duration" --output "$output" --format flamegraph
    ;;
  top)
    exec py-spy top --pid "$OMNIPLOT_PID"
    ;;
  *)
    echo "unknown command: $cmd (expected: record | top)" >&2
    exit 1
    ;;
esac
