"""The Scenes runtime: drive the Touch Bar from a Scenes config.

This is the new engine's live loop — it *extends* the proven `runtime.py` pattern
(hold the Device open continuously, hot-reload the config, route touch → actions)
and adds the three things the Scenes model needs:

  * **scene resolution** — pick the active scene from live machine state + priority,
    over the Always base (`scenes.resolve_active`), re-light on change;
  * **the layered/material compositor** — `compose.compose` replaces `render.py`;
  * **an animation tick** — capped at **30 fps and event-driven** per the measured
    hardware budget (`docs/HARDWARE-FRAME-PUSH-REFERENCE.md`): an idle scene blits
    **0 frames**; a scene with an active motion layer / timing envelope / changing
    live binding ticks at ≤30 fps, then settles back to event-driven.

Live bindings (media position/title, cpu%, clock) update **inside** a scene without
swapping it. Press events fire per-layer envelopes (the on-press flare) via the
shared `motion.Dynamics`.

Hardware facts honoured (from the reference doc): synchronous UDCL-paced `blit()` is
optimal and must stay synchronous; never free-run; hold the Device open the whole
time (closing hands back to firmware and blanks the panel until something re-opens
it). Swap in via `systemctl stop t1bar.service` → run this → `systemctl start …`.
"""
from __future__ import annotations

import signal
import time

from t1touchbar import Device, TouchReader

from . import actions, compose, context, motion, scenes
from .model import Hot

FPS_CAP = 30
FRAME_DT = 1.0 / FPS_CAP
IDLE_POLL = 0.04          # ~25 Hz event poll when nothing is animating


class _CpuSampler:
    """Cheap whole-host CPU% from /proc/stat deltas, sampled ~1 Hz."""

    def __init__(self):
        self._prev = None
        self.value = 0.0
        self._last = 0.0

    def sample(self, now):
        if now - self._last < 0.9:
            return self.value
        self._last = now
        try:
            with open("/proc/stat") as f:
                parts = [int(x) for x in f.readline().split()[1:]]
        except (OSError, ValueError):
            return self.value
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        if self._prev:
            dt = total - self._prev[0]
            di = idle - self._prev[1]
            if dt > 0:
                self.value = max(0.0, min(100.0, 100.0 * (1 - di / dt)))
        self._prev = (total, idle)
        return self.value


class SceneRuntime:
    def __init__(self, config_path, on_action=None):
        self.hot = Hot(config_path)
        self.cfg = None
        self.cfg_gen = 0
        self.dynamics = motion.Dynamics()
        self.media = None
        self.cpu = _CpuSampler()
        self.pressed = None             # part id currently held
        self.manual = None              # part-selected scene override (id)
        self.manual_until = 0.0
        self.scene = None               # the active Scene object
        self.geometry = None
        self.on_action = on_action or actions.dispatch
        self._stop = False

    # -- live state ------------------------------------------------------------
    def _live(self, now):
        return {
            "media": self.media.state if self.media else {},
            "cpu": self.cpu.sample(now),
            "gpu": 0,
            "clock": time.strftime("%H:%M"),
            "app": "",                   # focused-app source not wired yet
            "pressed": self.pressed,
        }

    def _resolve(self, live, now):
        """Active scene, honouring a short-lived manual override."""
        if self.manual and now < self.manual_until:
            s = self.cfg.scene_by_id(self.manual)
            if s:
                return s
        return scenes.resolve_active(self.cfg, live)

    def _signature(self, scene, live):
        """What, when idle, should trigger a re-blit (live bindings ticking, etc.)."""
        m = live["media"]
        return (self.cfg_gen, scene.id if scene else None, self.pressed,
                m.get("status"), int(m.get("position", 0)), m.get("title"),
                round(live["cpu"] / 5) * 5, live["clock"])

    # -- main loop -------------------------------------------------------------
    def run(self):
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_stop", True))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))

        self.cfg = self.hot.poll() or self.hot.config
        if self.cfg is None:
            raise SystemExit(f"could not load scene config: {self.hot.error}")
        self.geometry = self.cfg.geometry

        self.media = context.MediaWatcher().start()
        with Device() as bar:
            w, h = bar.width, bar.height
            self.geometry = dict(self.geometry, width=w, height=h)
            tr = TouchReader(w, h)
            tr.start(lambda ev: self._on_touch(ev))
            print(f"[t1bar] scenes running ({w}x{h}). Active scene resolves live; "
                  f"motion ticks at <= {FPS_CAP}fps, idle is event-driven. Ctrl-C to quit.",
                  flush=True)
            last_sig = None
            last_blit = 0.0
            try:
                while not self._stop:
                    now = time.monotonic()
                    new_cfg = self.hot.poll()
                    if new_cfg is not None:                 # live config edit
                        self.cfg = new_cfg
                        self.cfg_gen += 1
                        self.geometry = dict(new_cfg.geometry, width=w, height=h)
                        print("[t1bar] scene config reloaded (live)", flush=True)

                    live = self._live(now)
                    scene = self._resolve(live, now)
                    if scene is not self.scene:
                        self.dynamics.activate_scene(scene, now)
                        self.scene = scene
                        last_sig = None                     # force a repaint
                    self.scene = scene

                    animating = scene is not None and self.dynamics.scene_animating(scene, now)
                    if animating:
                        # tick at the fps cap while something moves (epsilon so clock
                        # jitter can't alias the rate down to ~20fps)
                        if now - last_blit >= FRAME_DT - 1e-3:
                            self._blit(bar, scene, live, now)
                            last_blit = now
                            last_sig = self._signature(scene, live)
                        time.sleep(min(FRAME_DT, max(0.0, FRAME_DT - (time.monotonic() - now))))
                    else:
                        # event-driven: blit only when the signature changes
                        sig = self._signature(scene, live)
                        if sig != last_sig:
                            last_sig = sig
                            self._blit(bar, scene, live, now)
                            last_blit = now
                        time.sleep(IDLE_POLL)
            finally:
                tr.stop()
                self.media.stop()

    def _blit(self, bar, scene, live, now):
        if scene is None:
            return
        img = compose.compose(self.cfg, live, scene=scene, t=now, dynamics=self.dynamics)
        bar.blit(img)

    # -- touch -----------------------------------------------------------------
    def _on_touch(self, ev):
        if self.cfg is None or self.scene is None:
            return
        if ev.state == "down":
            part, frac = compose.hit_test(self.scene, self.geometry, ev.x)
            if not part:
                return
            action = part.action
            if action and action[0] == "scene":             # manual scene override
                self.manual = action[1]
                self.manual_until = time.monotonic() + 10
                self.pressed = None
                return
            self.pressed = part.id
            self.dynamics.press(part, time.monotonic())      # fire on-press envelopes
            ctx = self.media.state if self.media else {}
            if part.type == "slider":
                self.on_action(["seek", frac], ctx=ctx)
            elif action:
                self.on_action(action, ctx=ctx)
        elif ev.state == "up":
            self.pressed = None
