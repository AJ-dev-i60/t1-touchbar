#!/usr/bin/env bash
#
# t1-touchbar uninstaller.
#
#   --to-basic : remove the studio (Full) and return to the plain firmware strip (Basic).
#   --all      : remove everything — driver, studio, kernel module — back to a stock bar.
#
# Either way, reboot afterward to apply (the bar engine changes across a reboot).
# Your Scenes config (~/.config/t1bar/) is left in place; delete it manually if you want.
#
#   sudo ./uninstall.sh             # interactive
#   sudo ./uninstall.sh --to-basic
#   sudo ./uninstall.sh --all
#   flags: --yes  --dry-run
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV=/opt/t1touchbar/venv
BINDIR=/usr/local/bin
SYSD=/etc/systemd/system
DKMS_NAME=apple-ib-drv; DKMS_VER=0.1

WHAT=""; ASSUME_YES=0; DRY=0
for a in "$@"; do case "$a" in
  --to-basic) WHAT=basic;;
  --all) WHAT=all;;
  --yes|-y) ASSUME_YES=1;;
  --dry-run) DRY=1;;
  -h|--help) grep '^#' "$0" | sed '1d;s/^# \{0,1\}//'; exit 0;;
  *) echo "unknown option: $a" >&2; exit 2;;
esac; done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
run() { printf '   + %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }

if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
USER_NAME="${SUDO_USER:-root}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

if [ -z "$WHAT" ]; then
  echo "  1) Back to Basic — remove the studio, keep the firmware strip."
  echo "  2) Remove everything — driver, studio, kernel module → stock bar."
  if [ "$ASSUME_YES" = 1 ]; then WHAT=basic; else
    read -rp "Choose [1/2] (default 1): " c; [ "$c" = 2 ] && WHAT=all || WHAT=basic
  fi
fi

# ── tear down the studio (Full) bits — common to both ───────────────────────
remove_studio() {
  say "Removing the studio engine + webcam bridge…"
  run systemctl disable --now t1bar-scenes.service 2>/dev/null || true
  run systemctl disable --now t1touchbar-camera.service 2>/dev/null || true
  run rm -f "$SYSD/t1bar-scenes.service" "$SYSD/t1touchbar-camera.service"
  run rm -f /etc/modules-load.d/t1touchbar-v4l2loopback.conf
  run rm -f /etc/udev/rules.d/70-t1touchbar-camera.rules
  run rm -f "$USER_HOME/.local/share/applications/t1bar-studio.desktop"
  run rm -f "$USER_HOME/.local/share/icons/hicolor/scalable/apps/t1bar-studio.svg"
  run systemctl daemon-reload
}

if [ "$WHAT" = basic ]; then
  remove_studio
  say "Re-enabling the firmware driver on boot…"
  run install -m644 "$REPO/apple-ib-drv/packaging/apple-touchbar.modules-load.conf" /etc/modules-load.d/apple-touchbar.conf
  echo
  say "✅ Reverted to Basic. Reboot to return to the firmware strip."
  echo "   (The studio venv at $VENV is left in place; re-add it any time with: sudo ./install.sh --full)"
else
  remove_studio
  say "Removing the firmware kernel module + all persistence…"
  run dkms remove -m "$DKMS_NAME" -v "$DKMS_VER" --all 2>/dev/null || true
  run rm -rf "/usr/src/${DKMS_NAME}-${DKMS_VER}"
  run rm -f /etc/modprobe.d/apple-touchbar.conf /etc/modules-load.d/apple-touchbar.conf
  run rm -f /etc/udev/rules.d/99-ibridge.rules
  run rm -rf "$VENV"
  for s in t1touchbar t1touchbar-camera t1bar; do run rm -f "$BINDIR/$s"; done
  run udevadm control --reload || true
  echo
  say "✅ Removed everything. Reboot for the bar to return to its stock (firmware-default) state."
  echo "   Your layout is kept at $USER_HOME/.config/t1bar/ — delete it if you want it gone."
fi
