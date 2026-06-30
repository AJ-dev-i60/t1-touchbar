#!/usr/bin/env bash
#
# t1-touchbar installer.
#
#   Basic : just make my Touch Bar work. The T1's own FIRMWARE draws the strip (Esc /
#           brightness / keyboard-backlight / media / volume / hold-Fn→F1–F12) via the
#           apple-ib-drv kernel driver. Set-and-forget; the webcam keeps working natively.
#   Full  : Basic + the "t1bar studio" app. The studio takes over the bar with custom
#           pixels (Scenes). Hands the whole interface to the studio, needs a reboot, and
#           routes the webcam through a bridge. Uninstalling it returns you to Basic.
#
# Basic and Full are mutually exclusive boot states; switching between them is a reboot.
#
#   sudo ./install.sh            # interactive
#   sudo ./install.sh --basic    # firmware strip only
#   sudo ./install.sh --full     # + studio (custom bar)
#   flags: --yes  --no-service  --dry-run
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV=/opt/t1touchbar/venv
BINDIR=/usr/local/bin
SYSD=/etc/systemd/system
DKMS_NAME=apple-ib-drv
DKMS_VER=0.1

MODE=""; ASSUME_YES=0; DRY=0; ENABLE_SERVICE=1

usage() {
  grep '^#' "$0" | sed '1d;s/^# \{0,1\}//' | sed '/^!/d'
}
for a in "$@"; do case "$a" in
  --basic) MODE=basic;;
  --full)  MODE=full;;
  --yes|-y) ASSUME_YES=1;;
  --no-service) ENABLE_SERVICE=0;;
  --dry-run) DRY=1;;
  -h|--help) usage; exit 0;;
  *) echo "unknown option: $a" >&2; exit 2;;
esac; done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
run() { printf '   + %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }
gen() { printf '   + write %s\n' "$1"; if [ "$DRY" = 1 ]; then cat >/dev/null; else cat >"$1"; fi; }
ask() {
  [ "$ASSUME_YES" = 1 ] && return 0
  local d="$2" p; [ "$d" = Y ] && p="[Y/n]" || p="[y/N]"
  read -rp "$1 $p " r; r="${r:-$d}"; [[ "$r" =~ ^[Yy] ]]
}

# ── root ────────────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  say "This installer needs root (apt + DKMS + systemd). Re-running with sudo…"
  exec sudo -E bash "$0" "$@"
fi
USER_NAME="${SUDO_USER:-root}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"

# ── preflight ───────────────────────────────────────────────────────────────
command -v apt-get >/dev/null || { echo "This installer targets apt-based distros (Ubuntu/Debian)." >&2; exit 1; }
if lsusb 2>/dev/null | grep -qi '05ac:8600'; then
  say "T1 iBridge (05ac:8600) detected."
else
  say "⚠  No T1 iBridge (05ac:8600) found on USB — this is a MacBookPro13,x/14,x feature."
  ask "Continue anyway?" N || exit 1
fi

# ── choose mode ─────────────────────────────────────────────────────────────
if [ -z "$MODE" ]; then
  echo
  echo "  1) Basic — just make my Touch Bar work. The firmware draws the strip (esc · brightness ·"
  echo "             keyboard backlight · media · volume · hold-Fn→F1–F12). Set-and-forget; webcam"
  echo "             keeps working. Nothing to think about again."
  echo "  2) Full  — Basic + the 't1bar studio' app to design your own bar (Scenes). Hands the whole"
  echo "             bar to the studio (custom pixels), needs a reboot, routes the webcam via a"
  echo "             bridge. Uninstall it any time to return to Basic."
  echo
  if [ "$ASSUME_YES" = 1 ]; then MODE=basic; else
    read -rp "Choose [1/2] (default 1): " c; [ "$c" = 2 ] && MODE=full || MODE=basic
  fi
fi
say "Installing: ${MODE^^}"
[ "$DRY" = 1 ] && say "(dry run — nothing will actually change)"

# ── shared: build + DKMS-install the firmware kernel driver (apple-ib-drv) ───
# Installs the module + the critical skip_acpi_power param + the config-1/autosuspend
# udev. Does NOT enable auto-load — Basic enables it, Full leaves it dormant.
install_kernel_driver() {
  say "Building the firmware Touch Bar driver (apple-ib-drv) via DKMS…"
  run apt-get update
  run apt-get install -y build-essential dkms "linux-headers-$(uname -r)" \
    || run apt-get install -y build-essential dkms linux-headers-generic
  local SRC="/usr/src/${DKMS_NAME}-${DKMS_VER}"
  run install -d "$SRC"
  run cp "$REPO"/apple-ib-drv/{Makefile,apple-ibridge.c,apple-ibridge.h,apple-touchbar.c,hid-ids.h,dkms.conf} "$SRC"/
  if dkms status "${DKMS_NAME}/${DKMS_VER}" 2>/dev/null | grep -q installed; then
    say "  ${DKMS_NAME}/${DKMS_VER} already installed."
  else
    run dkms add -m "$DKMS_NAME" -v "$DKMS_VER" || true
    run dkms build -m "$DKMS_NAME" -v "$DKMS_VER"
    run dkms install -m "$DKMS_NAME" -v "$DKMS_VER"
  fi
  # the critical param (NEVER load without it) + force config 1 + no autosuspend
  run install -m644 "$REPO/apple-ib-drv/packaging/apple-touchbar.modprobe.conf" /etc/modprobe.d/apple-touchbar.conf
  run install -m644 "$REPO/apple-ib-drv/packaging/99-ibridge.rules" /etc/udev/rules.d/99-ibridge.rules
  run udevadm control --reload
  run udevadm trigger
}

# ════════════════════════════════ BASIC (State A) ═══════════════════════════
if [ "$MODE" = basic ]; then
  install_kernel_driver
  say "Enabling the firmware driver on boot…"
  run install -m644 "$REPO/apple-ib-drv/packaging/apple-touchbar.modules-load.conf" /etc/modules-load.d/apple-touchbar.conf
  # mutual exclusion: make sure no studio engine is driving the bar
  run systemctl disable --now t1bar-scenes.service 2>/dev/null || true
  run systemctl disable --now t1touchbar-camera.service 2>/dev/null || true
  if [ "$ENABLE_SERVICE" = 1 ]; then
    say "Loading the driver now…"
    run modprobe apple_ibridge skip_acpi_power=1 || say "  (couldn't load live — a reboot will load it)"
  fi
  echo
  say "✅ Done — installed BASIC (firmware strip)."
  echo "   Your Touch Bar should now show the control strip; the webcam works as normal."
  echo "   If the bar isn't lit yet, reboot — it auto-loads on every boot from here."
  echo "   To add customization later:  sudo ./install.sh --full"

# ════════════════════════════════ FULL (State B) ════════════════════════════
else
  install_kernel_driver            # installed but DORMANT — the revert target for Basic
  say "Standing the firmware driver down (the studio will own the bar)…"
  run rm -f /etc/modules-load.d/apple-touchbar.conf
  run modprobe -r apple_touchbar apple_ibridge 2>/dev/null || true

  say "Installing the studio (Scenes) engine + webcam bridge…"
  run apt-get install -y libusb-1.0-0 python3-dev python3-venv python3-pip git playerctl
  run apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi-cairo
  run apt-get install -y fonts-spacemono || true
  run apt-get install -y ffmpeg v4l2loopback-dkms

  run python3 -m venv --system-site-packages "$VENV"
  run "$VENV/bin/pip" install --quiet --upgrade pip
  ( set -e; cd "$REPO";        run "$VENV/bin/pip" install --quiet ".[touch]" )   # driver first
  ( set -e; cd "$REPO/studio"; run "$VENV/bin/pip" install --quiet . )            # resolves t1-touchbar locally
  for s in t1touchbar t1touchbar-camera t1bar; do
    [ -x "$VENV/bin/$s" ] && run ln -sf "$VENV/bin/$s" "$BINDIR/$s"
  done

  # user-owned Scenes config
  CFGDIR="$USER_HOME/.config/t1bar"; CFG="$CFGDIR/scenes.json"
  run install -d -o "$USER_NAME" -g "$USER_NAME" "$CFGDIR"
  if [ -f "$CFG" ]; then
    say "Keeping your existing $CFG"
  elif [ -f "$CFGDIR/config.json" ]; then
    say "Migrating legacy config → scenes.json"
    run sudo -u "$USER_NAME" "$VENV/bin/t1bar" convert -c "$CFGDIR/config.json" -o "$CFG"
  else
    run install -m644 -o "$USER_NAME" -g "$USER_NAME" "$REPO/studio/configs/scenes-default.json" "$CFG"
  fi

  # studio bar-driver service
  sed "s#CONFIG_PATH#$CFG#g" "$REPO/studio/packaging/t1bar-scenes.service" | gen "$SYSD/t1bar-scenes.service"

  # webcam bridge (config-2 H.264 → v4l2loopback), ordered after the studio service
  echo v4l2loopback | gen /etc/modules-load.d/t1touchbar-v4l2loopback.conf
  sed -e 's#^After=t1touchbar-strip.service#After=t1bar-scenes.service#' \
      -e 's#^Wants=t1touchbar-strip.service#Wants=t1bar-scenes.service#' \
      "$REPO/packaging/t1touchbar-camera.service" | gen "$SYSD/t1touchbar-camera.service"
  run install -m644 "$REPO/packaging/70-t1touchbar-camera.rules" /etc/udev/rules.d/70-t1touchbar-camera.rules
  run udevadm control --reload || true

  # editor app entry + icon (force Exec to scene-edit regardless of the shipped file)
  APPDIR="$USER_HOME/.local/share/applications"
  ICONDIR="$USER_HOME/.local/share/icons/hicolor/scalable/apps"
  run install -d -o "$USER_NAME" -g "$USER_NAME" "$APPDIR" "$ICONDIR"
  run install -m644 -o "$USER_NAME" -g "$USER_NAME" "$REPO/studio/packaging/t1bar-studio.svg" "$ICONDIR/t1bar-studio.svg"
  sed -e "s#CONFIG_PATH#$CFG#g" -e "s#^Exec=.*#Exec=t1bar scene-edit -c $CFG#" \
      "$REPO/studio/packaging/t1bar-studio.desktop" | gen "$APPDIR/t1bar-studio.desktop"
  [ "$DRY" = 1 ] || chown "$USER_NAME":"$USER_NAME" "$APPDIR/t1bar-studio.desktop"

  if [ "$ENABLE_SERVICE" = 1 ]; then
    run systemctl daemon-reload
    run systemctl enable t1bar-scenes.service        # enable for boot; a reboot does the config-1→2 switch
    run systemctl enable t1touchbar-camera.service
  fi
  echo
  say "✅ Done — installed FULL (studio)."
  echo "   ⟳  REBOOT to hand the bar over to the studio (firmware config-1 → studio config-2)."
  echo "   After reboot, design it:  launch \"t1bar studio\" from the app grid, or"
  echo "                             t1bar scene-edit -c $CFG"
  echo "   The webcam runs through the bridge while the studio owns the bar."
  echo "   To go back to the plain firmware strip:  sudo ./install.sh --basic   (then reboot)"
fi
