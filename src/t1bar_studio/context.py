"""Context sources + rule evaluation: decide which layout is active right now.

Stage 1 source: MPRIS media (status / position / length / title) via playerctl,
which covers Spotify *and* browser video (YouTube etc.). Position/length drive the
scrubber; status drives play/pause and the "when media is playing" rule.

Rules are evaluated top→down, first match wins; a rule with no "when" is the
catch-all default::

    "rules": [
        {"when": {"media": "playing"}, "show": "media"},
        {"show": "default"}
    ]
"""
import subprocess
import threading
import time

from .actions import user_cmd

_FMT = "{{status}}\x1f{{position}}\x1f{{mpris:length}}\x1f{{title}}\x1f{{artist}}"


class MediaWatcher:
    """Poll a single combined playerctl call; expose the latest media state."""

    def __init__(self, interval=0.5):
        self.interval = interval
        self.state = {"status": "Stopped", "position": 0.0, "length": 0.0,
                      "title": "", "artist": ""}
        self._run = False

    def start(self):
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()
        return self

    def stop(self):
        self._run = False

    @staticmethod
    def _to_seconds(v):
        try:
            n = float(v)
        except (TypeError, ValueError):
            return 0.0
        return n / 1e6 if n > 1e5 else n      # playerctl templates emit microseconds

    def _loop(self):
        cmd = user_cmd(["playerctl", "metadata", "--format", _FMT])
        while self._run:
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                line = out.stdout.strip()
                if line:
                    parts = (line.split("\x1f") + ["", "", "", "", ""])[:5]
                    st, pos, length, title, artist = parts
                    self.state = {
                        "status": st or "Stopped",
                        "position": self._to_seconds(pos),
                        "length": self._to_seconds(length),
                        "title": title, "artist": artist,
                    }
                else:
                    self.state["status"] = "Stopped"
            except Exception:
                self.state["status"] = "Stopped"
            time.sleep(self.interval)


def pick_layout(cfg, state):
    """Evaluate rules against current state; return a layout name."""
    layouts = cfg["layouts"]
    for rule in cfg.get("rules", []):
        when = rule.get("when")
        if when is None or _matches(when, state):
            name = rule.get("show")
            if name in layouts:
                return name
    return next(iter(layouts), None)


def _matches(when, state):
    media = state.get("media", {})
    for key, want in when.items():
        if key == "media":
            st = media.get("status")
            if want == "playing" and st != "Playing":
                return False
            if want == "active" and st not in ("Playing", "Paused"):
                return False
            if want == "stopped" and st in ("Playing", "Paused"):
                return False
        # (future: "app", "window", "stat" conditions)
    return True
