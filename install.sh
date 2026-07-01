#!/usr/bin/env bash
#
# t1-touchbar installer — just make my Touch Bar work.
#
# The T1's own FIRMWARE draws the control strip (Esc / brightness / keyboard-backlight /
# media / volume / hold-Fn→F1–F12) via the apple-ib-drv kernel driver. Set-and-forget;
# the webcam keeps working natively.
#
# Quick install — no git, no clone:
#   curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
# Or from a clone:
#   sudo ./install.sh
#   flags: --yes  --no-service  --dry-run
#
# Want to design your own custom bar instead (custom pixels / Scenes)? That's a separate,
# still-in-development project — t1-touchbar-studio. This installer is just the driver.
#
set -euo pipefail

# ── self-bootstrap ──────────────────────────────────────────────────────────
# Supports `curl -fsSL <raw>/install.sh | bash` with NO git and NO checkout: if we're
# not already inside a repo checkout, fetch the repo tarball and re-exec from it.
# We're in a checkout only if THIS script is a real file sitting next to the repo.
# Under `curl | bash` it isn't a file at all → bootstrap (regardless of cwd).
_src="${BASH_SOURCE[0]:-$0}"; _self_dir=""
[ -f "$_src" ] && _self_dir="$(cd "$(dirname "$_src")" && pwd)"
if [ -z "$_self_dir" ] || [ ! -f "${_self_dir}/apple-ib-drv/dkms.conf" ]; then
  command -v curl >/dev/null 2>&1 || { echo "t1-touchbar: need 'curl' to bootstrap." >&2; exit 1; }
  command -v tar  >/dev/null 2>&1 || { echo "t1-touchbar: need 'tar' to bootstrap." >&2; exit 1; }
  _tmp="$(mktemp -d)"
  echo "==> fetching t1-touchbar (no git needed)…"
  curl -fsSL "https://github.com/AJ-dev-i60/t1-touchbar/tarball/main" \
    | tar -xz -C "$_tmp" --strip-components=1
  # re-exec the real installer from the extracted repo, as root, with the terminal
  # reattached so the prompts work even though stdin came from the curl pipe.
  if { true </dev/tty; } 2>/dev/null; then
    exec sudo bash "$_tmp/install.sh" "$@" </dev/tty   # reattach the terminal so prompts work
  else
    exec sudo bash "$_tmp/install.sh" "$@"             # no tty (CI/pipe) — pass --yes
  fi
fi

REPO="$(cd "$(dirname "$0")" && pwd)"
DKMS_NAME=apple-ib-drv
DKMS_VER=0.1

ASSUME_YES=0; DRY=0; ENABLE_SERVICE=1

usage() { grep '^#' "$0" | sed '1d;s/^# \{0,1\}//' | sed '/^!/d'; }
for a in "$@"; do case "$a" in
  --yes|-y) ASSUME_YES=1;;
  --no-service) ENABLE_SERVICE=0;;
  --dry-run) DRY=1;;
  --basic) ;;   # accepted for back-compat; the firmware driver is the only mode this repo installs
  --full)
    echo "The custom-bar 'Full' path is now a separate project, t1-touchbar-studio (still in" >&2
    echo "development). This installer only sets up the firmware driver (Basic)." >&2
    exit 2;;
  -h|--help) usage; exit 0;;
  *) echo "unknown option: $a" >&2; exit 2;;
esac; done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
run() { printf '   + %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }
ask() {
  [ "$ASSUME_YES" = 1 ] && return 0
  local d="$2" p; [ "$d" = Y ] && p="[Y/n]" || p="[y/N]"
  read -rp "$1 $p " r; r="${r:-$d}"; [[ "$r" =~ ^[Yy] ]]
}

# usbmuxd ships a udev rule matching the iBridge (05ac:8600); if it claims the device
# first, the HID driver can't bind and the bar stays dark. We don't auto-edit a system
# file — just flag it so the user knows the fix if a reboot doesn't light the bar.
warn_usbmuxd() {
  local rule=/lib/udev/rules.d/39-usbmuxd.rules
  if systemctl is-active --quiet usbmuxd 2>/dev/null && grep -qsi '05ac.*8600' "$rule"; then
    say "⚠  usbmuxd is active and its udev rule matches the iBridge (05ac:8600)."
    echo "   It didn't block binding on the tested machine, but if the bar stays dark AFTER a reboot,"
    echo "   drop the iBridge matches and reboot:"
    echo "       sudo sed -i '/05ac.*8600/d' $rule && sudo udevadm control --reload && sudo reboot"
    echo "   (or, if you never tether iPhones/iPads:  sudo systemctl mask usbmuxd)"
  fi
}

# Grep the healthy-boot signature so the user gets a clear pass/fail, not "it should work".
# Most checks only pass after the reboot that binds the driver early enough — that's expected.
selfcheck() {
  [ "$DRY" = 1 ] && return 0
  say "Self-check…"
  local bound=1
  if lsmod | grep -q '^apple_touchbar'; then echo "   ✓ apple_touchbar loaded"
  else echo "   • apple_touchbar not loaded yet (expected until you reboot)"; bound=0; fi
  if dmesg 2>/dev/null | grep -qi 'skip_acpi_power.*NOT running'; then echo "   ✓ freeze-guard active (SOCW skipped)"
  else echo "   • freeze-guard message not in dmesg yet (will appear on the reboot load)"; fi
  if dmesg 2>/dev/null | grep -qiE 'apple-touchbar.*input:'; then echo "   ✓ Touch Bar HID created"
  else echo "   • Touch Bar HID not created yet — reboot to bind"; bound=0; fi
  [ "$bound" = 1 ] && say "✅ Looks healthy — the bar should be lit." \
                   || say "↻ Not bound yet — this is normal on first install. REBOOT to finish."
}

# ── root ────────────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  say "This installer needs root (apt + DKMS + udev). Re-running with sudo…"
  exec sudo bash "$0" "$@"
fi
# stdin often comes from the curl|bash pipe or --yes wrapper; keep apt non-interactive so it
# doesn't warn ("dpkg-preconfigure: unable to re-open stdin") or block on a prompt.
export DEBIAN_FRONTEND=noninteractive

# ── preflight ───────────────────────────────────────────────────────────────
command -v apt-get >/dev/null || { echo "This installer targets apt-based distros (Ubuntu/Debian)." >&2; exit 1; }
if lsusb 2>/dev/null | grep -qi '05ac:8600'; then
  say "T1 iBridge (05ac:8600) detected."
else
  say "⚠  No T1 iBridge (05ac:8600) found on USB — this is a MacBookPro13,x/14,x feature."
  ask "Continue anyway?" N || exit 1
fi

say "Installing the T1 firmware Touch Bar driver."
[ "$DRY" = 1 ] && say "(dry run — nothing will actually change)"

# ── build + DKMS-install the firmware kernel driver (apple-ib-drv) ───────────
# Installs the module + the critical skip_acpi_power param + the config-1/autosuspend udev,
# and enables auto-load on boot.
say "Building the firmware Touch Bar driver (apple-ib-drv) via DKMS…"
# SAFETY FIRST: write skip_acpi_power=1 BEFORE the module can ever exist or auto-load.
# A load without it runs ASOC.SOCW(1) and HARD-FREEZES the machine. (The driver also
# defaults to skipping on T1 by DMI, so this is belt-and-suspenders.)
run install -m644 "$REPO/apple-ib-drv/packaging/apple-touchbar.modprobe.conf" /etc/modprobe.d/apple-touchbar.conf
run apt-get update
run apt-get install -y build-essential dkms "linux-headers-$(uname -r)" \
  || run apt-get install -y build-essential dkms linux-headers-generic
SRC="/usr/src/${DKMS_NAME}-${DKMS_VER}"
run install -d "$SRC"
run cp "$REPO"/apple-ib-drv/{Makefile,apple-ibridge.c,apple-ibridge.h,apple-touchbar.c,hid-ids.h,dkms.conf} "$SRC"/
if dkms status "${DKMS_NAME}/${DKMS_VER}" 2>/dev/null | grep -q installed; then
  say "  ${DKMS_NAME}/${DKMS_VER} already installed."
else
  run dkms add -m "$DKMS_NAME" -v "$DKMS_VER" || true
  run dkms build -m "$DKMS_NAME" -v "$DKMS_VER"
  run dkms install -m "$DKMS_NAME" -v "$DKMS_VER"
fi
# Reassure about the scary-but-harmless taint line the build/load emits. If Secure Boot is
# ON the self-signed module won't load until its MOK is enrolled — point at that instead.
if mokutil --sb-state 2>/dev/null | grep -qi enabled; then
  say "Secure Boot is ON — enrol the module-signing key once, or the kernel will refuse the module:"
  echo "      sudo mokutil --import /var/lib/dkms/mok.pub   # set a password, reboot, confirm in the blue MOK screen"
else
  say "FYI: a \"module verification failed … tainting kernel\" line is EXPECTED and harmless here"
  echo "      (Secure Boot is off, so the self-signed module loads but isn't key-verified). Not an error."
fi
# force config 1 + no autosuspend (the skip_acpi_power param was written first, above)
run install -m644 "$REPO/apple-ib-drv/packaging/99-ibridge.rules" /etc/udev/rules.d/99-ibridge.rules
run udevadm control --reload
run udevadm trigger

say "Enabling the firmware driver on boot…"
run install -m644 "$REPO/apple-ib-drv/packaging/apple-touchbar.modules-load.conf" /etc/modules-load.d/apple-touchbar.conf
# If the separate studio project is installed and holding the device (config 2), stop it so
# the firmware can own the bar. Harmless if absent.
run systemctl disable --now t1bar-scenes.service 2>/dev/null || true

if [ "$ENABLE_SERVICE" = 1 ]; then
  say "Loading the driver now…"
  run modprobe apple_ibridge skip_acpi_power=1 || say "  (couldn't load live — a reboot will load it)"
fi
echo
selfcheck
warn_usbmuxd
echo
say "✅ Done — the T1 firmware control strip is installed."
echo "   ⟳  REBOOT to finish. On an already-running system the generic HID drivers have already"
echo "      claimed the iBridge, so the live load may bind nothing — a reboot lets the driver grab"
echo "      it early. After that the strip comes up automatically on every boot; the webcam works"
echo "      as normal."
echo "   To remove it later:  sudo ./uninstall.sh"
