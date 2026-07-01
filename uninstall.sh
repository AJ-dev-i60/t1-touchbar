#!/usr/bin/env bash
#
# t1-touchbar uninstaller — remove the firmware Touch Bar driver, back to stock.
#
# Reboot afterward: the bar returns to its stock (firmware-default) state.
#
#   sudo ./uninstall.sh
#   flags: --yes  --dry-run
#
# Or with no git/clone:
#   curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/uninstall.sh | bash
#
set -euo pipefail

# self-bootstrap: support `curl -fsSL <raw>/uninstall.sh | bash` with no git/checkout.
_src="${BASH_SOURCE[0]:-$0}"; _self_dir=""
[ -f "$_src" ] && _self_dir="$(cd "$(dirname "$_src")" && pwd)"
if [ -z "$_self_dir" ] || [ ! -f "${_self_dir}/apple-ib-drv/dkms.conf" ]; then
  command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 \
    || { echo "t1-touchbar: need curl + tar to bootstrap." >&2; exit 1; }
  _tmp="$(mktemp -d)"; echo "==> fetching t1-touchbar (no git needed)…"
  curl -fsSL "https://github.com/AJ-dev-i60/t1-touchbar/tarball/main" | tar -xz -C "$_tmp" --strip-components=1
  if { true </dev/tty; } 2>/dev/null; then exec sudo bash "$_tmp/uninstall.sh" "$@" </dev/tty
  else exec sudo bash "$_tmp/uninstall.sh" "$@"; fi
fi

DKMS_NAME=apple-ib-drv; DKMS_VER=0.1
ASSUME_YES=0; DRY=0
for a in "$@"; do case "$a" in
  --yes|-y) ASSUME_YES=1;;
  --dry-run) DRY=1;;
  -h|--help) grep '^#' "$0" | sed '1d;s/^# \{0,1\}//'; exit 0;;
  *) echo "unknown option: $a" >&2; exit 2;;
esac; done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
run() { printf '   + %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }

if [ "$(id -u)" -ne 0 ]; then exec sudo bash "$0" "$@"; fi

say "Removing the firmware Touch Bar driver (apple-ib-drv) + its config…"
run dkms remove -m "$DKMS_NAME" -v "$DKMS_VER" --all 2>/dev/null || true
run rm -rf "/usr/src/${DKMS_NAME}-${DKMS_VER}"
run rm -f /etc/modprobe.d/apple-touchbar.conf /etc/modules-load.d/apple-touchbar.conf
run rm -f /etc/udev/rules.d/99-ibridge.rules
run modprobe -r apple_touchbar apple_ibridge 2>/dev/null || true
run udevadm control --reload || true
echo
say "✅ Removed. Reboot for the bar to return to its stock (firmware-default) state."
