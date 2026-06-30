#!/usr/bin/env bash
# Wire t1bar-studio in as the Touch Bar *system*: a t1bar.service that drives the
# bar from YOUR config (hot-reloading as you edit), retiring the driver's hardcoded
# strip. Fully reversible with uninstall-service.sh. Run with sudo.
#
#   sudo packaging/install-service.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CFG="$USER_HOME/.config/t1bar/config.json"
SYSD=/etc/systemd/system

cfgval(){ cat /sys/bus/usb/devices/1-3/bConfigurationValue 2>/dev/null || echo "?"; }

echo "==> seed canonical config ($CFG)"
install -d -o "$USER_NAME" -g "$USER_NAME" "$(dirname "$CFG")"
if [ -f "$CFG" ]; then
  echo "    already exists — keeping your layout"
else
  install -o "$USER_NAME" -g "$USER_NAME" -m644 "$REPO/configs/default.json" "$CFG"
  echo "    seeded from configs/default.json"
fi

echo "==> install t1bar.service"
sed "s#CONFIG_PATH#$CFG#g" "$REPO/packaging/t1bar.service" > "$SYSD/t1bar.service"

# The driver's camera unit hard-codes Wants/After the strip. systemd drop-ins can
# add deps but cannot RESET an inherited Wants= (so the strip would get pulled back
# in), so re-point the camera at t1bar in the installed unit directly — a deploy
# transform, like the CONFIG_PATH sub. The repo's driver units stay untouched.
CAM="$SYSD/t1touchbar-camera.service"
if [ -f "$CAM" ]; then
  echo "==> re-point camera dependency: strip -> t1bar"
  sed -i \
    -e 's#^After=t1touchbar-strip.service#After=t1bar.service#' \
    -e 's#^Wants=t1touchbar-strip.service#Wants=t1bar.service#' \
    -e 's#order it after the strip#order it after t1bar (unified model)#' \
    "$CAM"
fi

echo "==> retire the strip (disable), enable t1bar at boot"
systemctl daemon-reload
systemctl disable --now t1touchbar-strip.service 2>/dev/null || true
systemctl enable t1bar.service

echo "==> switch the running bar over to t1bar"
systemctl stop t1touchbar-camera.service 2>/dev/null || true
systemctl start t1bar.service
for i in $(seq 1 8); do [ "$(cfgval)" = 2 ] && [ "$(systemctl is-active t1bar.service)" = active ] && break; sleep 1; done
systemctl restart t1touchbar-camera.service 2>/dev/null || true

echo "==> point the app launcher at your config"
LAUNCHER="$USER_HOME/.local/share/applications/t1bar-studio.desktop"
[ -f "$LAUNCHER" ] && sed -i "s#-c [^ ]*#-c $CFG#" "$LAUNCHER" || true

echo "done.  t1bar=$(systemctl is-active t1bar.service)  camera=$(systemctl is-active t1touchbar-camera.service)  config=$(cfgval)"
echo "Edit your bar:  t1bar scene-edit -c $CFG   (or launch 't1bar studio' from the app grid)"
