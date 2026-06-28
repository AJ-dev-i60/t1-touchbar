"""The control-strip app: plays the welcome showcase, then runs the default
control strip on the Touch Bar, hit-testing touches to buttons.

Increment 1: actions are *logged* (not applied) except layout switches, so the
display + touch behaviour can be validated safely. Real system actions
(uinput keys, media, volume, brightness, kbd backlight) arrive in increment 2 via
actions.py.
"""
import time

from t1touchbar import Device, TouchReader

from . import actions
from . import layout as L
from . import render
from . import welcome
from .keys import FnWatcher
from .media import MediaWatcher


class StripApp:
    def __init__(self, show_welcome=True, on_action=None):
        self.show_welcome = show_welcome
        self.current = "control"
        self.pressed = None
        self.playing = False
        self.dirty = True
        # `on_action(action_tuple)` performs a system action; default logs only.
        self.on_action = on_action or self._log_action

    @staticmethod
    def _log_action(action):
        print(f"[strip] action: {action}", flush=True)

    def run(self):
        import signal
        # Stop cleanly on SIGTERM (systemd stop) and SIGINT (Ctrl-C) alike — both
        # set a flag the loop checks, so the `with Device()` block always exits and
        # restores config 1. Without a SIGTERM handler the default action kills the
        # process outright and the bar is left stranded in config 2.
        self._stop = False

        def _on_signal(*_):
            self._stop = True
        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        with Device() as bar:
            w, h = bar.width, bar.height
            if self.show_welcome:
                print("[strip] welcome showcase...", flush=True)
                welcome.play(bar.blit, w, h)
            self.dirty = True

            tr = TouchReader(w, h)
            tr.start(lambda ev: self._on_touch(ev, w))
            fn = FnWatcher(self._on_fn)
            fn.start()
            media = MediaWatcher(self._on_media, actions.media_follow_command())
            media.start()
            print(f"[strip] control strip ready ({w}x{h}). Hold Fn for F-keys. Ctrl-C to quit.",
                  flush=True)
            try:
                while not self._stop:
                    if self.dirty:
                        self.dirty = False
                        bar.blit(render.render(L.LAYOUTS[self.current], w, h,
                                               self.pressed, self.playing))
                    time.sleep(0.02)
            finally:
                tr.stop()
                fn.stop()
                media.stop()

    def _on_media(self, playing):
        if playing != self.playing:
            self.playing = playing
            self.dirty = True

    def _on_fn(self, pressed):
        # Physical Fn held -> F-keys; released -> control strip.
        self.current = "fkeys" if pressed else "control"
        self.pressed = None
        self.dirty = True

    def _on_touch(self, ev, width):
        lay = L.LAYOUTS[self.current]
        if ev.state == "down":
            b = render.hit(lay, ev.x, width)
            if not b:
                return
            self.pressed = b.id
            self.dirty = True
            if b.action and b.action[0] == "layout":
                self.current = b.action[1]
                self.pressed = None
            else:
                self.on_action(b.action)
                if b.id == "play":
                    self.playing = not self.playing   # instant feedback; poll reconciles
        elif ev.state == "up":
            if self.pressed is not None:
                self.pressed = None
                self.dirty = True
