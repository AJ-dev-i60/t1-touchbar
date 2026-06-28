"""The runtime: own the bar, render the active layout, route touch to actions, and
hot-reload the config so edits appear live on the Touch Bar.
"""
import signal
import time

from t1touchbar import Device, TouchReader

from . import actions, context, render
from .config import Hot


class Runtime:
    def __init__(self, config_path, on_action=None):
        self.hot = Hot(config_path)
        self.cfg = None
        self.cfg_gen = 0
        self.manual = None              # button-selected layout override
        self.manual_until = 0.0
        self.pressed = None
        self.media = None
        self.current_layout = None      # what the render loop last showed
        self.on_action = on_action or actions.dispatch
        self._stop = False

    def _active_layout(self, state):
        if self.manual and time.monotonic() < self.manual_until:
            if self.manual in self.cfg["layouts"]:
                return self.manual
        return context.pick_layout(self.cfg, state)

    def _state(self, w, h):
        return {"width": w, "height": h, "pressed": self.pressed,
                "media": self.media.state if self.media else {}}

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_stop", True))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))

        self.cfg = self.hot.poll() or self.hot.config
        if self.cfg is None:
            raise SystemExit(f"could not load config: {self.hot.error}")

        self.media = context.MediaWatcher().start()
        with Device() as bar:
            w, h = bar.width, bar.height
            tr = TouchReader(w, h)
            tr.start(lambda ev: self._on_touch(ev, w, h))
            print(f"[t1bar] running ({w}x{h}). Edit the config and watch it update "
                  f"live. Ctrl-C to quit.", flush=True)
            last_sig = None
            try:
                while not self._stop:
                    if self.hot.poll() is not None:        # config edited → live reload
                        self.cfg_gen += 1
                        print("[t1bar] config reloaded (live)", flush=True)
                    state = self._state(w, h)
                    layout = self._active_layout(state)
                    self.current_layout = layout
                    sig = self._signature(layout, state)
                    if sig != last_sig:
                        last_sig = sig
                        if layout:
                            bar.blit(render.render(self.cfg, layout, state))
                    time.sleep(0.05)
            finally:
                tr.stop()
                self.media.stop()

    def _signature(self, layout, state):
        m = state["media"]
        # re-render when any of these change (position rounded so the scrubber ticks)
        return (self.cfg_gen, layout, self.pressed, m.get("status"),
                int(m.get("position", 0)), m.get("title"))

    def _on_touch(self, ev, w, h):
        if self.cfg is None or self.current_layout is None:
            return
        layout = self.current_layout
        if ev.state == "down":
            item, frac = render.hit(self.cfg, layout, ev.x, w, h)
            if not item:
                return
            action = item.get("action")
            if action and action[0] == "layout":
                self.manual = action[1]
                self.manual_until = time.monotonic() + 10
                self.pressed = None
                return
            self.pressed = item.get("id")
            ctx = self.media.state if self.media else {}
            if item.get("type") == "scrubber":
                self.on_action(["seek", frac], ctx=ctx)
            elif action:
                self.on_action(action, ctx=ctx)
        elif ev.state == "up":
            self.pressed = None
