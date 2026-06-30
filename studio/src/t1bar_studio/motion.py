"""Motion + timing — the time dimension of the Scenes engine.

Two mechanisms, both functions of a clock the runtime advances:

  * **Continuous motion** (Drift / Breathe / Flicker / Sweep) — a motion *layer* on a
    part. Pure functions of absolute time ``t`` (seconds): they offset the part,
    modulate its alpha, or sweep a specular band across it. Always running while the
    scene is shown.
  * **Timing envelopes** — a per-layer lifecycle (``trigger → hold → fade`` along a
    ``curve``). Stateful: they fire on an event (a press, the scene activating) and
    decay back. The same mechanism powers press-flares, glow pulses, notification
    flashes and idle "breathing". The runtime owns a :class:`Dynamics` that remembers
    when each envelope last fired; the compositor asks it for a 0..1 intensity.

The compositor (``compose.py``) consumes both: it calls :func:`motion_offset` for the
per-part transform and, for each effect layer, scales the effect's intensity by
:meth:`Dynamics.layer_value`. With no motion layers and no fired envelopes the result
is a constant 1.0 / zero-offset, so a still scene renders identically frame to frame —
which is exactly what lets the runtime drop to event-driven when nothing is animating.
"""
from __future__ import annotations

import math

# ── easing curves ────────────────────────────────────────────────────────────
def ease(curve, x):
    """Map progress ``x`` (0..1) through a curve. Returns ~0..1 (spring overshoots)."""
    x = 0.0 if x < 0 else (1.0 if x > 1 else x)
    if curve == "linear":
        return x
    if curve == "spring":
        # decaying overshoot — reads as a springy settle
        return 1 - math.cos(x * math.pi * 1.5) * math.exp(-3 * x)
    # ease-out (default)
    return 1 - (1 - x) * (1 - x)


# ── continuous motion (of absolute time) ─────────────────────────────────────
def motion_offset(part, t):
    """Aggregate Drift/Breathe/Flicker on ``part`` at time ``t`` → (dx, dy, alpha).

    ``dx``/``dy`` are pixel offsets; ``alpha`` is a 0..1 opacity multiplier. Sweep is
    visual (a moving band) and handled separately by :func:`sweeps`."""
    dx = dy = 0.0
    alpha = 1.0
    for m in part.motions():
        p = m.params
        kind = p.get("motion")
        amp = float(p.get("amplitude", 1.0))
        period = max(0.05, float(p.get("period", 3.0)))
        ph = math.sin(2 * math.pi * t / period)
        if kind == "drift":
            dx += amp * 3.0 * ph
            dy += amp * 1.0 * math.sin(2 * math.pi * t / (period * 1.7))
        elif kind == "breathe":
            depth = float(p.get("depth", 0.22))
            alpha *= (1 - depth) + depth * (0.5 + 0.5 * ph)
        elif kind == "flicker":
            fp = max(0.02, float(p.get("period", 0.13)))
            depth = float(p.get("depth", 0.3))
            alpha *= (1 - depth) + depth * (0.5 + 0.5 * math.sin(2 * math.pi * t / fp))
    return dx, dy, max(0.0, min(1.0, alpha))


def sweeps(part, t):
    """Sweep bands on ``part`` at time ``t`` → list of (centre 0..1, width 0..1,
    intensity 0..1). A specular highlight travelling across the part."""
    out = []
    for m in part.motions():
        if m.params.get("motion") != "sweep":
            continue
        period = max(0.1, float(m.params.get("period", 2.5)))
        width = float(m.params.get("width", 0.22))
        intensity = float(m.params.get("intensity", 0.6))
        # travel a touch beyond both edges so it enters/exits cleanly
        centre = (t % period) / period * (1 + 2 * width) - width
        out.append((centre, width, intensity))
    return out


def any_motion(scene):
    """True if any part in the scene carries a (continuous) motion layer."""
    return any(p.motions() for p in scene.parts)


# ── timing envelopes (stateful) ──────────────────────────────────────────────
def envelope_value(env, now, fired_at):
    """A 0..1 intensity for an envelope. ``always`` breathes continuously; event
    triggers (``press``/``active``) rise to 1 on fire, hold, then fade along the curve
    and rest at 0. ``fired_at`` is the time the trigger last fired (or None)."""
    if env is None:
        return 1.0
    hold = env.hold_ms / 1000.0
    fade = max(1e-3, env.fade_ms / 1000.0)
    if env.trigger == "always":
        period = max(0.1, hold + fade)
        return 0.5 + 0.5 * math.sin(2 * math.pi * now / period)
    if fired_at is None:
        return 0.0
    el = now - fired_at
    if el < 0:
        return 0.0
    if el < hold:
        return 1.0
    if el < hold + fade:
        return max(0.0, 1.0 - ease(env.curve, (el - hold) / fade))
    return 0.0


def envelope_active(env, now, fired_at):
    """Is this envelope still changing the frame (so the runtime must keep ticking)?"""
    if env is None:
        return False
    if env.trigger == "always":
        return True
    if fired_at is None:
        return False
    return (now - fired_at) < (env.hold_ms + env.fade_ms) / 1000.0 + 0.05


class Dynamics:
    """Per-part/per-layer envelope state, owned by the runtime.

    The runtime calls :meth:`press` (or :meth:`fire`) on input/events; the compositor
    calls :meth:`layer_value` to scale an effect layer's intensity. Stateless scenes
    never touch it, so headless still-renders need no Dynamics at all (pass ``None``)."""

    def __init__(self):
        self.fired = {}        # (part_id, layer_id) -> fired_at (seconds)
        self.scene_activated_at = {}   # scene_id -> time (drives "active" envelopes)

    def fire(self, part_id, layer_id, now):
        self.fired[(part_id, layer_id)] = now

    def press(self, part, now):
        """Fire every press-triggered envelope on ``part`` (e.g. an on-press flare)."""
        for l in part.layers:
            if l.envelope and l.envelope.trigger == "press":
                self.fired[(part.id, l.id)] = now

    def activate_scene(self, scene, now):
        """Record a scene becoming active; fires its parts' ``active`` envelopes."""
        if self.scene_activated_at.get(scene.id) is not None:
            return
        self.scene_activated_at[scene.id] = now
        for p in scene.parts:
            for l in p.layers:
                if l.envelope and l.envelope.trigger == "active":
                    self.fired[(p.id, l.id)] = now

    def deactivate_scene(self, scene):
        self.scene_activated_at.pop(scene.id, None)

    def layer_value(self, part_id, layer, now):
        """0..1 intensity multiplier for ``layer`` right now (1.0 if no envelope)."""
        env = layer.envelope
        if env is None:
            return 1.0
        if env.trigger == "always":
            return envelope_value(env, now, None)
        return envelope_value(env, now, self.fired.get((part_id, layer.id)))

    def scene_animating(self, scene, now):
        """True if anything in ``scene`` is still moving — motion layer present, or an
        envelope mid-flight. The runtime renders frames while true, idles otherwise."""
        if any_motion(scene):
            return True
        for p in scene.parts:
            for l in p.layers:
                if l.envelope and envelope_active(
                        l.envelope, now, self.fired.get((p.id, l.id))):
                    return True
        return False
