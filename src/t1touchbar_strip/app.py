"""The control-strip app: plays the welcome showcase, then runs the default
control strip on the Touch Bar, hit-testing touches to buttons.

Increment 1: actions are *logged* (not applied) except layout switches, so the
display + touch behaviour can be validated safely. Real system actions
(uinput keys, media, volume, brightness, kbd backlight) arrive in increment 2 via
actions.py.
"""
import time

from t1touchbar import Device, TouchReader

from . import layout as L
from . import render
from . import welcome


class StripApp:
    def __init__(self, show_welcome=True, on_action=None):
        self.show_welcome = show_welcome
        self.current = "control"
        self.pressed = None
        self.dirty = True
        # `on_action(action_tuple)` performs a system action; default logs only.
        self.on_action = on_action or self._log_action

    @staticmethod
    def _log_action(action):
        print(f"[strip] action: {action}", flush=True)

    def run(self):
        with Device() as bar:
            w, h = bar.width, bar.height
            if self.show_welcome:
                print("[strip] welcome showcase...", flush=True)
                welcome.play(bar.blit, w, h)
            self.dirty = True

            tr = TouchReader(w, h)
            tr.start(lambda ev: self._on_touch(ev, w))
            print(f"[strip] control strip ready ({w}x{h}). Ctrl-C to quit.", flush=True)
            try:
                while True:
                    if self.dirty:
                        self.dirty = False
                        bar.blit(render.render(L.LAYOUTS[self.current], w, h, self.pressed))
                    time.sleep(0.02)
            except KeyboardInterrupt:
                pass
            finally:
                tr.stop()

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
        elif ev.state == "up":
            if self.pressed is not None:
                self.pressed = None
                self.dirty = True
