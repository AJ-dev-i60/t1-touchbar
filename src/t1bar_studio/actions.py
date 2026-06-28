"""Apply widget actions to the system. Runs as root (USB), but media/seek live in
the user's login session, so those are bridged to the desktop user.

Action forms (the config's "action" array):
  ["key", "KEY_VOLUMEUP"]      emit a key via uinput (desktop also shows its OSD)
  ["media", "play-pause"]      playerctl verb
  ["seek", <fraction 0..1>]    seek the active player to a fraction of its length
  ["command", "cmd", "arg"...] run a command (in the user's session)
  ["layout", "name"]           switch layout (handled by the runtime, not here)
"""
import os
import subprocess

_uinput = None
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
        _uinput = UInput({E.EV_KEY: keys}, name="t1bar-studio")
    return _uinput


def _emit_key(keyname):
    from evdev import ecodes as E
    code = getattr(E, keyname, None)
    if code is None:
        return
    u = _ensure_uinput()
    u.write(E.EV_KEY, code, 1); u.syn()
    u.write(E.EV_KEY, code, 0); u.syn()


def desktop_session():
    """(uid, env) for the active graphical user, or (None, None)."""
    base = "/run/user"
    try:
        for d in sorted(os.listdir(base)):
            if d.isdigit() and int(d) >= 1000 and os.path.exists(f"{base}/{d}/bus"):
                rt = f"{base}/{d}"
                return int(d), {
                    "XDG_RUNTIME_DIR": rt,
                    "DBUS_SESSION_BUS_ADDRESS": f"unix:path={rt}/bus",
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                }
    except OSError:
        pass
    return None, None


def user_cmd(cmd):
    """Wrap a command to run in the desktop user's session (when we're root)."""
    uid, env = desktop_session()
    if uid is not None and os.geteuid() == 0:
        return ["sudo", "-u", f"#{uid}", "env"] + [f"{k}={v}" for k, v in env.items()] + cmd
    return cmd


def _run_user(cmd):
    subprocess.run(user_cmd(cmd), check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dispatch(action, ctx=None):
    """Perform an action. `ctx` carries live state (e.g. media length for seek)."""
    if not action:
        return
    typ = action[0]
    arg = action[1] if len(action) > 1 else None
    try:
        if typ == "key":
            _emit_key(arg)
        elif typ == "media":
            _run_user(["playerctl", arg or "play-pause"])
        elif typ == "seek":
            length = (ctx or {}).get("length") or 0
            frac = float(arg if arg is not None else 0)
            if length > 0:
                _run_user(["playerctl", "position", str(max(0, frac) * length)])
        elif typ == "command":
            _run_user(list(action[1:]))
    except Exception as e:
        print(f"[t1bar] action {action} failed: {e}", flush=True)
