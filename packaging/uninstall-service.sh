#!/usr/bin/env bash
# Remove the t1-touchbar boot services and hand the stock Touch Bar / camera back.
# The bar returns to firmware on the next reboot. If you pointed Howdy at
# /dev/t1-camera, restore its device_path from the backup next to config.ini.
set -uo pipefail

echo "[*] stopping + disabling services"
systemctl disable --now t1touchbar-camera.service 2>/dev/null || true
systemctl disable --now t1touchbar-strip.service  2>/dev/null || true

echo "[*] removing units, udev rule, module-load drop-in"
rm -f /etc/systemd/system/t1touchbar-strip.service
rm -f /etc/systemd/system/t1touchbar-camera.service
rm -f /etc/udev/rules.d/70-t1touchbar-camera.rules
rm -f /etc/modules-load.d/t1touchbar-v4l2loopback.conf

systemctl daemon-reload
udevadm control --reload 2>/dev/null || true

echo "Done. Reboot to fully restore the stock Touch Bar."
echo "If you set Howdy's device_path to /dev/t1-camera, restore it from the"
echo "  /usr/lib/security/howdy/config.ini.t1backup.* file."
