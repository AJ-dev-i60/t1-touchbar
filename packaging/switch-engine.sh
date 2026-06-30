#!/usr/bin/env bash
# Switch which engine drives the Touch Bar, reversibly. Same t1bar.service name
# (so the camera's dependency on it is unaffected) — only the ExecStart + config
# change. Your legacy config.json and new scenes.json both stay on disk, so you can
# flip back and forth freely.
#
#   sudo packaging/switch-engine.sh scenes   # new Scenes/Layer-Loom engine (live)
#   sudo packaging/switch-engine.sh legacy   # original config-driven engine (fallback)
#
set -euo pipefail

ENGINE="${1:-}"
[ "$ENGINE" = scenes ] || [ "$ENGINE" = legacy ] || {
  echo "usage: $0 {scenes|legacy}" >&2; exit 2; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
SYSD=/etc/systemd/system
LEGACY_CFG="$USER_HOME/.config/t1bar/config.json"
SCENES_CFG="$USER_HOME/.config/t1bar/scenes.json"

cfgval(){ cat /sys/bus/usb/devices/1-3/bConfigurationValue 2>/dev/null || echo "?"; }

if [ "$ENGINE" = scenes ]; then
  TEMPLATE="$REPO/packaging/t1bar-scenes.service"
  CFG="$SCENES_CFG"
  if [ ! -f "$CFG" ]; then
    echo "==> scenes.json missing — converting from legacy config"
    sudo -u "$USER_NAME" env PYTHONPATH="$REPO/src" python3 -m t1bar_studio convert \
      -c "$LEGACY_CFG" -o "$CFG"
  fi
else
  TEMPLATE="$REPO/packaging/t1bar.service"
  CFG="$LEGACY_CFG"
fi

echo "==> writing t1bar.service ($ENGINE engine, config $CFG)"
sed "s#CONFIG_PATH#$CFG#g" "$TEMPLATE" > "$SYSD/t1bar.service"
systemctl daemon-reload

echo "==> restarting the bar"
systemctl stop t1touchbar-camera.service 2>/dev/null || true
systemctl restart t1bar.service
for i in $(seq 1 8); do
  [ "$(cfgval)" = 2 ] && [ "$(systemctl is-active t1bar.service)" = active ] && break
  sleep 1
done
systemctl restart t1touchbar-camera.service 2>/dev/null || true

echo "done.  engine=$ENGINE  t1bar=$(systemctl is-active t1bar.service)  camera=$(systemctl is-active t1touchbar-camera.service)  config=$(cfgval)"
if [ "$ENGINE" = scenes ]; then
  echo "Your bar now runs on the Scenes engine. Edit it live:  t1bar scene-edit -c $CFG"
  echo "Revert any time:  sudo packaging/switch-engine.sh legacy"
fi
