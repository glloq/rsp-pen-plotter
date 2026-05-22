#!/usr/bin/env bash
# Install OmniPlot: backend Python deps and the built frontend.
# Usage: ./install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking prerequisites"
command -v node >/dev/null 2>&1 || { echo "Error: Node.js 20+ is required (https://nodejs.org)."; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "Error: npm is required."; exit 1; }

echo "==> Installing backend dependencies"
cd "$ROOT/backend"
if command -v uv >/dev/null 2>&1; then
  uv sync
else
  echo "    uv not found; falling back to a Python venv + pip."
  PY="${PYTHON:-python3}"
  if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)'; then
    echo "Error: Python 3.12+ is required. Install uv (https://docs.astral.sh/uv/) or Python 3.12+."
    exit 1
  fi
  "$PY" -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -e .
fi

echo "==> Installing and building the frontend"
cd "$ROOT/frontend"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
npm run build

echo
echo "==> Done. Launch the system with:  ./start.sh"
