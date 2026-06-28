#!/usr/bin/env bash
# Install the t1-touchbar boot services so the machine comes up with the custom
# Touch Bar live AND the FaceTime webcam available (on-demand) — both off the
# config-2 session, at once.
#
#   t1touchbar-strip.service   drives the bar, owns config 2 (welcome on first run)
#   t1touchbar-camera.service  watches a v4l2loopback node; streams the webcam only
#                              while an app has it open. Stable path: /dev/t1-camera
#
# Requires the package installed (so t1touchbar-strip / t1touchbar-camera are on
# PATH) and the v4l2loopback kernel module available.
#
# Usage:
#   sudo bash packaging/install-service.sh            # install + enable both
#   sudo bash packaging/install-service.sh --howdy    # also point Howdy at the cam
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WANT_HOWDY=0
[ "${1:-}" = "--howdy" ] && WANT_HOWDY=1

for bin in t1touchbar-strip t1touchbar-camera; do
    command -v "$bin" >/dev/null 2>&1 || { echo "error: $bin not on PATH — install the package first" >&2; exit 1; }
done
if ! modinfo v4l2loopback >/dev/null 2>&1; then
    echo "error: v4l2loopback kernel module not found. Install it first, e.g.:" >&2
    echo "       sudo apt install v4l2loopback-dkms" >&2
    exit 1
fi

echo "[*] installing systemd units + udev rule"
install -m 0644 "$HERE/t1touchbar-strip.service"  /etc/systemd/system/t1touchbar-strip.service
install -m 0644 "$HERE/t1touchbar-camera.service" /etc/systemd/system/t1touchbar-camera.service
install -m 0644 "$HERE/70-t1touchbar-camera.rules" /etc/udev/rules.d/70-t1touchbar-camera.rules
# load v4l2loopback on boot
echo v4l2loopback | install -m 0644 /dev/stdin /etc/modules-load.d/t1touchbar-v4l2loopback.conf

udevadm control --reload
systemctl daemon-reload
systemctl enable --now t1touchbar-strip.service
systemctl enable --now t1touchbar-camera.service

# give the camera service a moment to create the loopback node + symlink
for _ in $(seq 1 20); do [ -e /dev/t1-camera ] && break; sleep 0.5; done

if [ "$WANT_HOWDY" = 1 ]; then
    CFG=/usr/lib/security/howdy/config.ini
    if [ -f "$CFG" ]; then
        cp "$CFG" "$CFG.t1backup.$(date +%s 2>/dev/null || echo bak)"
        sed -i "s|^device_path = .*|device_path = /dev/t1-camera|" "$CFG"
        echo "[*] Howdy device_path -> /dev/t1-camera (backup saved next to config.ini)"
        echo "    NOTE: enroll while the bridge is active so the model matches:"
        echo "          sudo howdy add"
    else
        echo "[!] --howdy requested but Howdy config not found; skipping."
    fi
fi

echo
echo "Done. Custom Touch Bar + on-demand webcam now start on every boot."
echo "  camera path : /dev/t1-camera   (point Zoom/Howdy/etc. here)"
echo "  status      : systemctl status t1touchbar-strip t1touchbar-camera"
echo "  uninstall   : sudo bash $HERE/uninstall-service.sh"
