"""Stream MPRIS playback state via `playerctl --follow status`.

One long-lived subprocess (vs. polling), so there's no per-tick process spawning /
auth-log spam, and play/pause updates are effectively instant.
"""
import subprocess
import threading
import time


class MediaWatcher:
    """Call `on_change(playing: bool)` whenever playback state changes."""

    def __init__(self, on_change, command):
        self.on_change = on_change
        self.command = command          # argv, already session-bridged
        self._run = False
        self._proc = None

    def start(self):
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _loop(self):
        while self._run:
            try:
                self._proc = subprocess.Popen(
                    self.command, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, bufsize=1)
            except Exception:
                time.sleep(2)
                continue
            for line in self._proc.stdout:
                if not self._run:
                    break
                self.on_change(line.strip() == "Playing")
            # playerctl exited (e.g. no players yet) — retry after a short wait
            if self._run:
                time.sleep(1.0)
