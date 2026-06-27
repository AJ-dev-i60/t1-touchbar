"""Apply control-strip actions to the system. Every handler is best-effort and
guarded — a missing tool or permission logs a warning instead of crashing.

The strip runs as root (for USB), but media/volume control lives in the user's
login session (PipeWire / MPRIS under /run/user/<uid>), so those commands are run
as the desktop user with their session environment bridged in. Keys, brightness,
and keyboard backlight work directly as root.
"""
import glob
import os
import subprocess

SINK = "@DEFAULT_AUDIO_SINK@"
_uinput = None


# -- keys (virtual keyboard via uinput) ------------------------------------------
# Everything the strip can emit. Media/brightness/volume keys are handled by the
# desktop, which also shows its native OSD overlay (volume/brightness popup).
_EMIT_KEYS = (
    ["KEY_ESC"] + [f"KEY_F{i}" for i in range(1, 13)]
    + ["KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_MUTE",
       "KEY_BRIGHTNESSUP", "KEY_BRIGHTNESSDOWN",
       "KEY_KBDILLUMUP", "KEY_KBDILLUMDOWN",
       "KEY_PLAYPAUSE", "KEY_NEXTSONG", "KEY_PREVIOUSSONG"]
)


def _ensure_uinput():
    global _uinput
    if _uinput is None:
        from evdev import UInput, ecodes as E
        keys = [getattr(E, k) for k in _EMIT_KEYS if hasattr(E, k)]
        _uinput = UInput({E.EV_KEY: keys}, name="t1touchbar-strip")
    return _uinput


def _emit_key(keyname):
    from evdev import ecodes as E
    code = getattr(E, keyname, None)
    if code is None:
        return
    u = _ensure_uinput()
    u.write(E.EV_KEY, code, 1)
    u.syn()
    u.write(E.EV_KEY, code, 0)
    u.syn()


# -- user-session bridge (media / volume) ----------------------------------------
def _desktop_session():
    """(uid, env) for the active graphical user, or (None, None)."""
    base = "/run/user"
    try:
        for d in sorted(os.listdir(base)):
            if d.isdigit() and int(d) >= 1000 and os.path.exists(f"{base}/{d}/bus"):
                uid, rt = int(d), f"{base}/{d}"
                return uid, {
                    "XDG_RUNTIME_DIR": rt,
                    "DBUS_SESSION_BUS_ADDRESS": f"unix:path={rt}/bus",
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                }
    except OSError:
        pass
    return None, None


def _run_user(cmd):
    uid, env = _desktop_session()
    if uid is None or os.geteuid() != 0:
        subprocess.run(cmd, check=False)
        return
    full = ["sudo", "-u", f"#{uid}", "env"] + [f"{k}={v}" for k, v in env.items()] + cmd
    subprocess.run(full, check=False)


def _media(arg):
    _run_user(["playerctl", arg])


def _user_cmd(cmd):
    """Wrap a command to run in the desktop user's session (when we're root)."""
    uid, env = _desktop_session()
    if uid is not None and os.geteuid() == 0:
        return ["sudo", "-u", f"#{uid}", "env"] + [f"{k}={v}" for k, v in env.items()] + cmd
    return cmd


def media_follow_command():
    """argv that streams MPRIS status changes (one line per change), session-bridged."""
    return _user_cmd(["playerctl", "--follow", "status"])


def media_status():
    """Current MPRIS playback state: 'Playing', 'Paused', 'Stopped', or None."""
    try:
        out = subprocess.run(_user_cmd(["playerctl", "status"]),
                             capture_output=True, text=True, timeout=2)
        s = out.stdout.strip()
        return s if s in ("Playing", "Paused", "Stopped") else None
    except Exception:
        return None


def _volume(arg):
    if arg == "mute":
        _run_user(["wpctl", "set-mute", SINK, "toggle"])
    else:
        _run_user(["wpctl", "set-volume", "-l", "1.5", SINK,
                   "5%" + ("-" if arg == "-" else "+")])


# -- sysfs brightness / keyboard backlight (root) --------------------------------
def _sysfs_step(paths, arg, frac=0.08):
    for path in paths:
        try:
            bdir = os.path.dirname(path)
            cur = int(open(path).read().strip())
            mx = int(open(os.path.join(bdir, "max_brightness")).read().strip())
            step = max(1, int(mx * frac))
            new = max(0, min(mx, cur + (step if arg == "+" else -step)))
            with open(path, "w") as f:
                f.write(str(new))
            return True
        except (OSError, ValueError):
            continue
    return False


def _brightness(arg):
    _sysfs_step(sorted(glob.glob("/sys/class/backlight/*/brightness")), arg)


def _kbd_backlight(arg):
    paths = set(glob.glob("/sys/class/leds/*kbd_backlight*/brightness"))
    _sysfs_step(sorted(paths), arg, frac=0.15)


# -- dispatch --------------------------------------------------------------------
def dispatch(action):
    if not action:
        return
    typ = action[0]
    arg = action[1] if len(action) > 1 else None
    try:
        if typ == "key":
            _emit_key(arg)
        elif typ == "media":
            _media(arg)
        elif typ == "volume":
            _volume(arg)
        elif typ == "brightness":
            _brightness(arg)
        elif typ == "kbd_backlight":
            _kbd_backlight(arg)
    except Exception as e:
        print(f"[strip] action {action} failed: {e}", flush=True)
