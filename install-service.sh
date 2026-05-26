#!/usr/bin/env bash
# Install OmniPlot as a systemd service that starts at boot.
# Usage: sudo ./install-service.sh [user]
#
# - Substitutes the user and install path into deploy/omniplot.service.in.
# - Creates an editable .env.service for runtime overrides if missing.
# - Enables and starts the omniplot.service unit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -ne 0 ]; then
  echo "Error: this script must run as root (sudo $0)." >&2
  exit 1
fi
command -v systemctl >/dev/null 2>&1 || {
  echo "Error: systemd is required but systemctl was not found." >&2
  exit 1
}

USER_NAME="${1:-${SUDO_USER:-}}"
if [ -z "$USER_NAME" ]; then
  echo "Error: pass the target user (sudo $0 <user>) or run via sudo as that user." >&2
  exit 1
fi
if ! id "$USER_NAME" >/dev/null 2>&1; then
  echo "Error: user '$USER_NAME' does not exist." >&2
  exit 1
fi

ENV_FILE="$ROOT/.env.service"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# OmniPlot service environment.
# Uncomment and edit as needed, then: sudo systemctl restart omniplot
#HOST=0.0.0.0
#PORT=8000
#OMNIPLOT_API_KEY=change-me
EOF
  chown "$USER_NAME":"$USER_NAME" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

UNIT=/etc/systemd/system/omniplot.service
sed -e "s|__USER__|$USER_NAME|g" -e "s|__ROOT__|$ROOT|g" \
  "$ROOT/deploy/omniplot.service.in" > "$UNIT"
chmod 644 "$UNIT"

# Allow the service user to restart omniplot without a password. Required so
# the in-app "Update" button (which runs update.sh inside the service) can
# trigger a restart to load new Python code. Scope is intentionally narrow:
# only `systemctl restart omniplot.service`, nothing else.
SUDOERS=/etc/sudoers.d/omniplot
cat > "$SUDOERS.tmp" <<EOF
$USER_NAME ALL=(root) NOPASSWD: /bin/systemctl restart omniplot.service, /usr/bin/systemctl restart omniplot.service, /bin/systemctl restart omniplot, /usr/bin/systemctl restart omniplot
EOF
chmod 440 "$SUDOERS.tmp"
if visudo -cf "$SUDOERS.tmp" >/dev/null; then
  mv "$SUDOERS.tmp" "$SUDOERS"
else
  rm -f "$SUDOERS.tmp"
  echo "Error: generated sudoers file failed validation; not installed." >&2
  exit 1
fi

systemctl daemon-reload
systemctl enable omniplot.service
# ``enable --now`` would only *start* the unit, which is a no-op when the
# service is already running. To make a re-run actually pick up changes
# to ``omniplot.service.in``, we issue a restart — it doubles as a fresh
# start when the unit wasn't running yet.
systemctl restart omniplot.service

echo
echo "==> OmniPlot service installed and started."
echo "    Status:   sudo systemctl status omniplot"
echo "    Logs:     sudo journalctl -u omniplot -f"
echo "    Edit env: sudo -u $USER_NAME \$EDITOR $ENV_FILE && sudo systemctl restart omniplot"
echo "    Remove:   sudo systemctl disable --now omniplot && sudo rm $UNIT $SUDOERS && sudo systemctl daemon-reload"
