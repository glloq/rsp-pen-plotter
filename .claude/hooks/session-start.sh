#!/bin/bash
# SessionStart hook: install system + project dependencies for OmniPlot.
# Runs only in Claude Code on the web; idempotent and non-interactive.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# System binaries the converters shell out to.
#   potrace            - direct raster vectorization (Phase 2)
#   ghostscript        - EPS/AI rasterization (Phase 3)
#   libreoffice-writer - DOCX/ODT/RTF conversion (Phase 4)
# Non-fatal: unrelated third-party apt repos may fail to refresh, and a missing
# binary only degrades the corresponding converter rather than the whole app.
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y || true
  apt-get install -y --no-install-recommends potrace ghostscript libreoffice-writer \
    || echo "warning: could not install potrace/ghostscript/libreoffice-writer; related converters will be unavailable" >&2
fi

# Backend (uv).
if command -v uv >/dev/null 2>&1; then
  (cd "$PROJECT_DIR/backend" && uv sync --extra dev)
fi

# Frontend (npm).
if command -v npm >/dev/null 2>&1; then
  (cd "$PROJECT_DIR/frontend" && npm install)
fi
