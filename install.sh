#!/usr/bin/env bash
# OmniPlot installer.
#
# Single-pass install: system packages, Node.js, uv (Python toolchain),
# backend dependencies, frontend build, optional systemd service.
#
# Usage:
#   ./install.sh                  # install everything, ready for ./start.sh
#   ./install.sh --service        # also install + enable the systemd unit
#                                 # (calls install-service.sh internally)
#   ./install.sh --no-system-deps # skip apt-get installs (custom setups)
#   ./install.sh --no-restart     # do not restart omniplot.service if installed
#   ./install.sh --help
#
# Environment:
#   OMNIPLOT_PYTHON     pin a Python interpreter for the venv fallback
#                       (only used when uv cannot be installed).
#   OMNIPLOT_SKIP_NODE  set non-empty to skip Node.js install attempts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WITH_SERVICE=0
SKIP_SYSTEM_DEPS=0
NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --service)        WITH_SERVICE=1 ;;
    --no-system-deps) SKIP_SYSTEM_DEPS=1 ;;
    --no-restart)     NO_RESTART=1 ;;
    --help|-h)
      # Print the header comment block (lines starting with '#' between the
      # shebang and the first code line), stripping the leading '# '.
      awk '
        NR == 1 { next }                       # skip shebang
        /^[^#]/ { exit }                       # stop at first non-comment
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

# ---------------------------------------------------------------- helpers ----

# Run a command as root, prepending sudo when we're not already root.
sudo_run() {
  if [ "$EUID" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

has() { command -v "$1" >/dev/null 2>&1; }

step() { echo; echo "==> $*"; }

# ---------------------------------------------------------- system packages --

install_system_deps() {
  if [ "$SKIP_SYSTEM_DEPS" -eq 1 ]; then
    step "Skipping system packages (--no-system-deps)"
    return
  fi
  if ! has apt-get; then
    step "Non-Debian system: install potrace, ghostscript, libreoffice manually if needed"
    return
  fi

  # Only the packages strictly needed by converters; anything else is a
  # user choice. We always install these because they're tiny and the
  # converter pipeline silently fails without them.
  local pkgs=(potrace ghostscript libreoffice-writer)
  local missing=()
  for pkg in "${pkgs[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ ${#missing[@]} -eq 0 ]; then
    step "System packages already present"
    return
  fi
  step "Installing system packages: ${missing[*]}"
  sudo_run apt-get update -qq
  sudo_run apt-get install -y --no-install-recommends "${missing[@]}"
}

install_nodejs() {
  if has node && has npm; then
    local version
    version="$(node -p 'process.versions.node.split(".")[0]')"
    if [ "$version" -ge 20 ]; then
      step "Node.js $(node --version) detected"
      return
    fi
    step "Node.js too old (need 20+), reinstalling via NodeSource"
  fi
  if [ -n "${OMNIPLOT_SKIP_NODE:-}" ]; then
    echo "Error: Node.js 20+ is required (set OMNIPLOT_SKIP_NODE='' to auto-install)." >&2
    exit 1
  fi
  if ! has apt-get || ! has curl; then
    echo "Error: install Node.js 20+ manually (https://nodejs.org)" >&2
    exit 1
  fi
  step "Installing Node.js 20 via NodeSource"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo_run -E bash -
  sudo_run apt-get install -y nodejs
}

install_uv() {
  if has uv; then
    step "uv $(uv --version 2>/dev/null | head -1) detected"
    return
  fi
  if ! has curl; then
    step "curl missing — falling back to pip-based install"
    return
  fi
  step "Installing uv (user-local, ~/.local/bin)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv installs into ~/.local/bin; make it visible to the rest of this script.
  export PATH="$HOME/.local/bin:$PATH"
}

# -------------------------------------------------------------- backend ----

install_backend() {
  step "Installing backend dependencies"
  cd "$ROOT/backend"
  if has uv; then
    uv sync
    return
  fi
  echo "    uv not available; using a Python venv + pip"
  local py="${OMNIPLOT_PYTHON:-python3}"
  if ! "$py" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; then
    echo "Error: Python 3.12+ is required. Install uv (https://docs.astral.sh/uv/) or set OMNIPLOT_PYTHON to a 3.12+ interpreter." >&2
    exit 1
  fi
  "$py" -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -e .
}

# -------------------------------------------------------------- frontend ---

install_frontend() {
  step "Building the frontend"
  cd "$ROOT/frontend"
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
  npm run build
}

# -------------------------------------------------------------- service ----

install_service() {
  step "Installing systemd service"
  local target_user
  target_user="${SUDO_USER:-$USER}"
  sudo_run "$ROOT/install-service.sh" "$target_user"

  # Serial access on the Pi: the systemd unit declares
  # SupplementaryGroups=dialout, but the user needs to be in it too for
  # interactive (non-service) runs. Idempotent — only adds if missing.
  if has usermod && [ -n "$target_user" ]; then
    if ! id -nG "$target_user" 2>/dev/null | tr ' ' '\n' | grep -qx dialout; then
      step "Adding $target_user to dialout (for /dev/ttyUSB* access)"
      sudo_run usermod -aG dialout "$target_user"
      echo "    Note: you must log out and back in (or 'newgrp dialout') for this to take effect outside the service."
    fi
  fi
}

# Restart the systemd unit if it's installed, so a rebuild picks up changes.
# Skipped when --service was passed (install-service.sh already enable --now's
# it) or when --no-restart is set. Silent no-op if the unit isn't installed.
restart_service_if_installed() {
  if [ "$NO_RESTART" -eq 1 ] || [ "$WITH_SERVICE" -eq 1 ]; then
    return
  fi
  has systemctl || return
  systemctl list-unit-files 2>/dev/null | grep -q '^omniplot\.service' || return
  step "Restarting omniplot.service"
  if [ "$EUID" -eq 0 ]; then
    systemctl restart omniplot.service
  else
    sudo -n systemctl restart omniplot.service 2>/dev/null || {
      echo "    Note: could not restart without password; run 'sudo systemctl restart omniplot' manually." >&2
      return
    }
  fi
}

# ----------------------------------------------------------------- main ----

install_system_deps
install_nodejs
install_uv
install_backend
install_frontend
if [ "$WITH_SERVICE" -eq 1 ]; then
  install_service
fi
restart_service_if_installed

# Suggest the URL the user will visit. Best-effort LAN-IP detection.
ip=""
if has hostname; then
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

echo
echo "================================================================"
echo "  OmniPlot installed."
if [ "$WITH_SERVICE" -eq 1 ]; then
  echo "  Service: running on boot (sudo systemctl status omniplot)"
else
  echo "  Launch:  ./start.sh"
fi
echo "  URL:     http://localhost:${PORT:-8000}"
[ -n "$ip" ] && echo "           http://$ip:${PORT:-8000}    (LAN)"
echo "================================================================"
