#!/usr/bin/env bash
# Revert install-service.sh: stop t1bar and hand the bar back to the driver's strip
# (or, if the driver is gone, to the stock firmware on next reboot). Your layout at
# ~/.config/t1bar/config.json is LEFT IN PLACE — harmless on its own, and a reinstall
# picks up right where you left off. Run with sudo.
#
#   sudo packaging/uninstall-service.sh
#
set -euo pipefail

USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CFG="$USER_HOME/.config/t1bar/config.json"
SYSD=/etc/systemd/system

cfgval(){ cat /sys/bus/usb/devices/1-3/bConfigurationValue 2>/dev/null || echo "?"; }

echo "==> stop + disable t1bar.service"
systemctl disable --now t1bar.service 2>/dev/null || true
rm -f "$SYSD/t1bar.service"

CAM="$SYSD/t1touchbar-camera.service"
if [ -f "$CAM" ]; then
  echo "==> restore camera dependency: t1bar -> strip"
  sed -i \
    -e 's#^After=t1bar.service#After=t1touchbar-strip.service#' \
    -e 's#^Wants=t1bar.service#Wants=t1touchbar-strip.service#' \
    -e 's#order it after t1bar (unified model)#order it after the strip#' \
    "$CAM"
fi
systemctl daemon-reload

if systemctl list-unit-files t1touchbar-strip.service >/dev/null 2>&1 \
   && [ -f "$SYSD/t1touchbar-strip.service" ]; then
  echo "==> hand the bar back to the driver's strip"
  systemctl stop t1touchbar-camera.service 2>/dev/null || true
  systemctl enable --now t1touchbar-strip.service
  for i in $(seq 1 8); do [ "$(cfgval)" = 2 ] && break; sleep 1; done
  systemctl restart t1touchbar-camera.service 2>/dev/null || true
  echo "    strip restored: $(systemctl is-active t1touchbar-strip.service)  config=$(cfgval)"
else
  echo "    driver strip not installed — the bar reverts to stock firmware on next reboot"
fi

# point the launcher back at the repo's example config (harmless if the repo moved)
LAUNCHER="$USER_HOME/.local/share/applications/t1bar-studio.desktop"
[ -f "$LAUNCHER" ] && sed -i "s#-c [^ ]*\.json#-c CONFIG_PATH#" "$LAUNCHER" || true

echo "done.  Your layout is kept at $CFG (delete it to forget your customizations)."
