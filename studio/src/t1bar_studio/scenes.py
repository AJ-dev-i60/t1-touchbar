"""Scene resolution: pick the active scene from live machine state + priority.

The active scene is the **highest-priority scene whose trigger is currently true**,
falling back to the **Always** base. Live data then updates *inside* that scene
without swapping it (the compositor reads ``live`` per frame).

Phase 1 evaluates the triggers we have sources for today:
  * ``always`` — always true (the base / fallback).
  * ``media``  — matches the MPRIS status from the existing ``context.MediaWatcher``
                 ("playing" / "active" (playing|paused) / "stopped").
Triggers we've designed but not yet wired (``app`` focused-window, ``stat`` cpu/gpu,
``clock``) evaluate false for now, so scenes using them simply never win until their
source lands — the resolution order is already correct for when they do.
"""
from __future__ import annotations


def trigger_matches(trigger, live):
    """Is this trigger currently satisfied by ``live`` state?"""
    kind = trigger.kind
    if kind == "always":
        return True
    if kind == "media":
        status = live.get("media", {}).get("status", "Stopped")
        want = trigger.params.get("state", "playing")
        if want == "playing":
            return status == "Playing"
        if want == "active":
            return status in ("Playing", "Paused")
        if want == "stopped":
            return status not in ("Playing", "Paused")
        return False
    if kind == "app":
        focused = (live.get("app") or "").lower()
        return bool(focused) and trigger.params.get("matches", "").lower() in focused
    if kind == "stat":
        metric = trigger.params.get("metric", "cpu")
        val = live.get(metric)
        if val is None:
            return False
        op = trigger.params.get("op", ">")
        thr = float(trigger.params.get("value", 0))
        return (val > thr) if op == ">" else (val < thr if op == "<" else val == thr)
    if kind == "clock":
        return False        # source not wired yet
    return False


def resolve_active(cfg, live):
    """Return the active ``Scene`` for the current ``live`` state.

    ``cfg.all_scenes()`` is already sorted highest-priority-first and includes the
    Always base, so the first trigger that matches wins; the base (``always``) is
    last and always matches, guaranteeing a result."""
    for scene in cfg.all_scenes():
        if trigger_matches(scene.trigger, live):
            return scene
    return cfg.always or (cfg.scenes[0] if cfg.scenes else None)


def resolve_with_reason(cfg, live):
    """Like ``resolve_active`` but also returns a human 'because …' string for the
    persistent Live indicator in Scene Home."""
    scene = resolve_active(cfg, live)
    if scene is None:
        return None, "no scenes"
    if scene.trigger.kind == "always":
        reason = "no other scene's trigger is active"
    else:
        reason = scene.trigger.describe().removeprefix("when ").strip()
    return scene, reason
