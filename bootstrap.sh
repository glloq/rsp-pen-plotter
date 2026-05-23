#!/usr/bin/env bash
# OmniPlot one-shot bootstrap.
#
# Usage (from a fresh Pi / Linux host):
#   bash <(curl -fsSL https://raw.githubusercontent.com/glloq/rsp-pen-plotter/main/bootstrap.sh) [install-args]
#
# What it does:
#   1. installs git if missing (apt)
#   2. clones the repo into $OMNIPLOT_DEST (default $HOME/rsp-pen-plotter)
#   3. runs ./install.sh with any arguments you passed
#
# Environment:
#   OMNIPLOT_REPO    Repo URL (default https://github.com/glloq/rsp-pen-plotter.git)
#   OMNIPLOT_BRANCH  Branch to check out (default main)
#   OMNIPLOT_DEST    Local clone target (default $HOME/rsp-pen-plotter)
#
# Examples:
#   # Install everything for ad-hoc use; you start it later with ./start.sh
#   bash <(curl -fsSL .../bootstrap.sh)
#
#   # Install + enable systemd auto-start at boot (the recommended Pi mode)
#   bash <(curl -fsSL .../bootstrap.sh) --service
set -euo pipefail

REPO_URL="${OMNIPLOT_REPO:-https://github.com/glloq/rsp-pen-plotter.git}"
BRANCH="${OMNIPLOT_BRANCH:-main}"
DEST="${OMNIPLOT_DEST:-$HOME/rsp-pen-plotter}"

has() { command -v "$1" >/dev/null 2>&1; }

sudo_run() {
  if [ "$EUID" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# ---------------------------------------------------------------- git -----

if ! has git; then
  echo "==> Installing git"
  if has apt-get; then
    sudo_run apt-get update -qq
    sudo_run apt-get install -y git
  else
    echo "Error: git is required and apt-get is unavailable; install git first." >&2
    exit 1
  fi
fi

# ------------------------------------------------------------- clone -----

if [ -d "$DEST/.git" ]; then
  echo "==> Updating existing clone at $DEST"
  git -C "$DEST" fetch origin "$BRANCH"
  git -C "$DEST" checkout "$BRANCH"
  git -C "$DEST" pull --ff-only origin "$BRANCH"
else
  echo "==> Cloning $REPO_URL ($BRANCH) into $DEST"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$DEST"
fi

# ----------------------------------------------------------- install -----

cd "$DEST"
exec ./install.sh "$@"
