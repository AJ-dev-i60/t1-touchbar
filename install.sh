#!/usr/bin/env bash
#
# t1-touchbar installer.
#
#   Basic : just make my Touch Bar work — the control strip (esc / brightness /
#           keyboard-backlight / media / volume / hold-Fn→F1–F12), on boot. Standalone.
#   Full  : Basic + the "t1bar studio" customization app (design your own bar with Scenes).
#
# One git clone has everything (driver at the repo root, studio under studio/). The driver
# is installed first so studio's `t1-touchbar[touch]` requirement resolves from it locally.
#
#   sudo ./install.sh                 # interactive: choose Basic or Full
#   sudo ./install.sh --basic         # non-interactive Basic
#   sudo ./install.sh --full          # non-interactive Full
#   flags: --yes (assume yes) · --no-service (install but don't enable on boot) · --dry-run
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV=/opt/t1touchbar/venv
BINDIR=/usr/local/bin
SYSD=/etc/systemd/system

MODE=""; ASSUME_YES=0; DRY=0; ENABLE_SERVICE=1

usage() { sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; }

for a in "$@"; do case "$a" in
  --basic) MODE=basic;;
  --full)  MODE=full;;
  --yes|-y) ASSUME_YES=1;;
  --no-service) ENABLE_SERVICE=0;;
  --dry-run) DRY=1;;
  -h|--help) usage; exit 0;;
  *) echo "unknown option: $a" >&2; exit 2;;
esac; done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
run()  { printf '   + %s\n' "$*"; [ "$DRY" = 1 ] || "$@"; }
gen()  { # gen <dest> : write stdin to <dest> (honours --dry-run)
  printf '   + write %s\n' "$1"
  if [ "$DRY" = 1 ]; then cat >/dev/null; else cat >"$1"; fi
}
ask()  { # ask <prompt> <default Y|N> -> 0 if yes
  [ "$ASSUME_YES" = 1 ] && return 0
  local d="$2" p; [ "$d" = Y ] && p="[Y/n]" || p="[y/N]"
  read -rp "$1 $p " r; r="${r:-$d}"; [[ "$r" =~ ^[Yy] ]]
}

# ── root ────────────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  say "This installer needs root (apt + systemd). Re-running with sudo…"
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
  echo "  1) Basic — just make my Touch Bar work: control strip (esc · brightness · keyboard"
  echo "             backlight · media · volume · hold-Fn→F1–F12), on boot. Standalone."
  echo "  2) Full  — Basic + the 't1bar studio' app to design your own bar (Scenes)."
  echo
  if [ "$ASSUME_YES" = 1 ]; then MODE=basic; else
    read -rp "Choose [1/2] (default 1): " c; [ "$c" = 2 ] && MODE=full || MODE=basic
  fi
fi
say "Installing: ${MODE^^}"
[ "$DRY" = 1 ] && say "(dry run — nothing will actually change)"

# ── 1 · system prerequisites ────────────────────────────────────────────────
say "Installing system prerequisites…"
run apt-get update
# libusb (USB), build-essential+python3-dev (build evdev for touch), venv/pip/git, playerctl (media)
run apt-get install -y libusb-1.0-0 build-essential python3-dev python3-venv python3-pip git playerctl
if [ "$MODE" = full ]; then
  # GTK stack is needed only for the Scene Home editor (the scene-run service is GTK-free)
  run apt-get install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi-cairo
  run apt-get install -y fonts-spacemono || true   # nice-to-have; falls back to DejaVu mono
fi

# ── 2 · python packages (driver first, then studio) ─────────────────────────
say "Creating venv at $VENV and installing packages…"
# --system-site-packages so the editor can see apt's PyGObject/GTK
run python3 -m venv --system-site-packages "$VENV"
run "$VENV/bin/pip" install --quiet --upgrade pip
( set -e; cd "$REPO";        run "$VENV/bin/pip" install --quiet ".[touch]" )   # driver + touch
SCRIPTS=(t1touchbar t1touchbar-strip t1touchbar-camera)
if [ "$MODE" = full ]; then
  ( set -e; cd "$REPO/studio"; run "$VENV/bin/pip" install --quiet . )          # resolves t1-touchbar locally
  SCRIPTS+=(t1bar)
fi

# ── 3 · put console scripts on PATH (the units call /usr/bin/env <script>) ───
say "Linking console scripts into $BINDIR…"
for s in "${SCRIPTS[@]}"; do
  [ -x "$VENV/bin/$s" ] && run ln -sf "$VENV/bin/$s" "$BINDIR/$s"
done

# ── 4 · the bar-driver service ──────────────────────────────────────────────
if [ "$MODE" = basic ]; then
  say "Installing the control-strip service…"
  run install -m644 "$REPO/packaging/t1touchbar-strip.service" "$SYSD/t1touchbar-strip.service"
  if [ "$ENABLE_SERVICE" = 1 ]; then
    run systemctl daemon-reload
    run systemctl enable --now t1touchbar-strip.service
  fi
else
  say "Seeding your Scenes config (owned by $USER_NAME) and installing the studio service…"
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
  # studio bar-driver service (templated CONFIG_PATH)
  sed "s#CONFIG_PATH#$CFG#g" "$REPO/studio/packaging/t1bar-scenes.service" | gen "$SYSD/t1bar-scenes.service"
  # editor desktop entry + icon (force the Exec to scene-edit regardless of the shipped file)
  APPDIR="$USER_HOME/.local/share/applications"
  ICONDIR="$USER_HOME/.local/share/icons/hicolor/scalable/apps"
  run install -d -o "$USER_NAME" -g "$USER_NAME" "$APPDIR" "$ICONDIR"
  run install -m644 -o "$USER_NAME" -g "$USER_NAME" "$REPO/studio/packaging/t1bar-studio.svg" "$ICONDIR/t1bar-studio.svg"
  sed -e "s#CONFIG_PATH#$CFG#g" -e "s#^Exec=.*#Exec=t1bar scene-edit -c $CFG#" \
      "$REPO/studio/packaging/t1bar-studio.desktop" | gen "$APPDIR/t1bar-studio.desktop"
  [ "$DRY" = 1 ] || { chown "$USER_NAME":"$USER_NAME" "$APPDIR/t1bar-studio.desktop"; }
  if [ "$ENABLE_SERVICE" = 1 ]; then
    run systemctl daemon-reload
    # mutual exclusion: the strip and the studio service are both single-owners of the bar
    run systemctl disable --now t1touchbar-strip.service 2>/dev/null || true
    run systemctl enable --now t1bar-scenes.service
  fi
fi

# ── done ────────────────────────────────────────────────────────────────────
echo
say "✅ Done — installed ${MODE^^}."
if [ "$MODE" = basic ]; then
  echo "   Your Touch Bar now shows the control strip (and starts on every boot)."
  echo "   Run by hand:  sudo t1touchbar-strip"
else
  echo "   Your Touch Bar is driven by the Scenes engine, starting on every boot."
  echo "   Design it:    launch \"t1bar studio\" from the app grid, or:"
  echo "                 t1bar scene-edit -c $USER_HOME/.config/t1bar/scenes.json"
fi
echo "   Note: while the driver owns the bar, exiting it leaves the panel blank until a"
echo "         reboot (T1 firmware behaviour); the service keeps it lit. The webcam bridge"
echo "         (t1touchbar-camera) is a separate optional feature — see the README."
