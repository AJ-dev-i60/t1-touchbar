#!/usr/bin/env bash
# Install + enable the t1-touchbar control strip as a system service, so the bar
# comes up working on every boot (with a one-time welcome showcase on first run).
#
# Requires the package to be installed first (e.g. `sudo pip install t1-touchbar`
# so `t1touchbar-strip` is on PATH). Run:  sudo bash packaging/install-service.sh
set -euo pipefail

UNIT="t1touchbar-strip.service"
SRC="$(cd "$(dirname "$0")" && pwd)/$UNIT"

if ! command -v t1touchbar-strip >/dev/null 2>&1; then
    echo "error: t1touchbar-strip not on PATH — install the package first" >&2
    exit 1
fi

install -m 0644 "$SRC" /etc/systemd/system/"$UNIT"
systemctl daemon-reload
systemctl enable --now "$UNIT"

echo "Enabled. The control strip now starts on boot."
echo "  status:  systemctl status $UNIT"
echo "  stop:    sudo systemctl disable --now $UNIT   (restores the stock bar after reboot)"
