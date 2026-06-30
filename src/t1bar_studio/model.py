"""The Scenes data model — the new config schema for t1bar studio.

This replaces the legacy ``theme``/``layouts``/``items``/``rules`` shape (see
``config.py``/``render.py``) with the approved "Scenes / Layer Loom" concept:

  SceneConfig
    ├─ scenes[]          situations, resolved top-down by priority
    │    └─ Scene
    │         ├─ trigger        when this scene is live (media/app/always/…)
    │         ├─ background      a scene-wide surface (layer stack, sibling of parts)
    │         └─ parts[]         the controls/readouts laid out along the strip
    │              └─ Part
    │                   ├─ material   one knob relating the part to the bg behind it
    │                   └─ layers[]   the Layer Loom: back→front stack
    │                        └─ Layer  {kind, params, envelope?}
    ├─ always            the priority-0 base scene (the fallback)
    └─ library           imported icons/textures/effects + saved parts + packs

Design goals mirror the legacy config: **forgiving**. Anything missing falls back
to a sane default, so a hand-written or half-built scene still loads and renders.
Everything round-trips losslessly through ``to_dict``/``from_dict`` so the GUI (and
the hot-reload loop) can read, mutate and re-save without data loss.

This module is pure data + (de)serialisation — no rendering, no I/O beyond load/save.
The compositor lives in ``compose.py``; scene resolution in ``scenes.py``.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, replace
from typing import Any, Optional

SCHEMA_VERSION = 2
MODEL_TAG = "scenes"          # distinguishes a new config from a legacy one

# ── the finite kit (the vocabulary the app ships with) ───────────────────────
PART_TYPES = ("key", "transport", "slider", "readout", "label", "spacer")
MATERIALS = ("solid", "frosted", "outline", "ghost", "metal")
LAYER_KINDS = ("background", "texture", "material", "icon", "effect", "motion")
BACKGROUND_TYPES = ("solid", "gradient", "motion", "texture", "image")
EFFECTS = ("glow", "bevel", "scanline", "shadow", "ripple")
MOTIONS = ("drift", "breathe", "flicker", "sweep")
CURVES = ("linear", "ease-out", "spring")
ENVELOPE_TRIGGERS = ("press", "active", "always")
TRIGGER_KINDS = ("always", "media", "app", "stat", "clock")

Color = list          # [r, g, b] or [r, g, b, a], 0-255


# ── small helpers ────────────────────────────────────────────────────────────
def _color(v, default):
    """Coerce a colour to a list of ints; fall back to ``default`` if unusable."""
    if not isinstance(v, (list, tuple)) or len(v) < 3:
        return list(default)
    try:
        return [int(round(float(c))) for c in v][:4]
    except (TypeError, ValueError):
        return list(default)


def _gen_id(prefix, taken):
    """Deterministic, collision-free id (no Math.random/clock available here)."""
    i = 1
    while f"{prefix}{i}" in taken:
        i += 1
    taken.add(f"{prefix}{i}")
    return f"{prefix}{i}"


# ── timing envelope (per-layer lifecycle) ────────────────────────────────────
@dataclass
class Envelope:
    """A per-layer lifecycle: trigger → hold → fade/decay along a curve.

    The same mechanism drives press-flares, glow pulses, notification flashes and
    idle "breathing". Phase 1 stores it; ``motion.py`` (Phase 2) will drive it.
    """
    trigger: str = "press"        # one of ENVELOPE_TRIGGERS
    hold_ms: int = 120
    fade_ms: int = 600
    curve: str = "ease-out"       # one of CURVES

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return None
        return cls(
            trigger=d.get("trigger", "press"),
            hold_ms=int(d.get("holdMs", d.get("hold_ms", 120))),
            fade_ms=int(d.get("fadeMs", d.get("fade_ms", 600))),
            curve=d.get("curve", "ease-out"),
        )

    def to_dict(self):
        return {"trigger": self.trigger, "holdMs": self.hold_ms,
                "fadeMs": self.fade_ms, "curve": self.curve}


# ── a single layer in the Loom ───────────────────────────────────────────────
@dataclass
class Layer:
    """One stackable, timeable layer. ``kind`` is one of LAYER_KINDS; ``params``
    is a free-form bag whose meaning depends on the kind (the compositor knows how
    to read each). ``envelope`` is an optional timing envelope."""
    kind: str
    params: dict = field(default_factory=dict)
    id: str = ""
    envelope: Optional[Envelope] = None
    imported: bool = False        # asset came in via import-by-spec (shows ↧ marker)

    @classmethod
    def from_dict(cls, d, taken=None):
        taken = taken if taken is not None else set()
        kind = d.get("kind", "background")
        lid = d.get("id") or _gen_id("l", taken)
        taken.add(lid)
        return cls(
            kind=kind,
            params=dict(d.get("params", {})),
            id=lid,
            envelope=Envelope.from_dict(d.get("envelope")),
            imported=bool(d.get("imported", False)),
        )

    def to_dict(self):
        out = {"id": self.id, "kind": self.kind, "params": self.params}
        if self.envelope:
            out["envelope"] = self.envelope.to_dict()
        if self.imported:
            out["imported"] = True
        return out

    # convenience constructors for the common layers ------------------------
    @staticmethod
    def background(color, type="solid", **params):
        return Layer("background", {"type": type, "color": list(color), **params})

    @staticmethod
    def icon(name=None, label="", color=(232, 234, 240), dynamic=None, size=26):
        return Layer("icon", {"icon": name, "label": label, "color": list(color),
                              "dynamic": dynamic, "size": size})

    @staticmethod
    def effect(effect, **params):
        return Layer("effect", {"effect": effect, **params})

    @staticmethod
    def motion(motion, **params):
        return Layer("motion", {"motion": motion, **params})


# ── a part: a control/readout placed in an auto-flow slot ────────────────────
@dataclass
class Part:
    """A control or readout that snaps into a slot along the strip.

    ``layers`` is the Layer Loom (back→front). ``material`` is the part-level knob
    relating it to the background behind it. ``width_mode`` + ``weight`` drive the
    auto-flow slot sizing (fixed parts get an intrinsic width; stretchy parts share
    the remaining ribbon by weight). ``binding`` ties a part to a live data source.
    """
    type: str = "key"
    id: str = ""
    width_mode: str = "fixed"       # "fixed" | "stretchy"
    weight: float = 1.0
    material: str = "solid"
    radius: int = 12
    fill: Color = field(default_factory=lambda: [38, 42, 58])
    color: Color = field(default_factory=lambda: [232, 234, 240])
    binding: Optional[dict] = None  # {"source": "media.position", ...}
    action: Optional[list] = None   # ["key", "KEY_PLAYPAUSE"] | ["seek"] | …
    layers: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d, taken=None):
        taken = taken if taken is not None else set()
        pid = d.get("id") or _gen_id("p", taken)
        taken.add(pid)
        ltaken = set()
        layers = [Layer.from_dict(l, ltaken) for l in d.get("layers", [])]
        ptype = d.get("type", "key")
        return cls(
            type=ptype,
            id=pid,
            width_mode=d.get("widthMode", d.get("width_mode",
                       "stretchy" if ptype in ("slider", "spacer") else "fixed")),
            weight=float(d.get("weight", 1.0)),
            material=d.get("material", "ghost" if ptype == "label" else "solid"),
            radius=int(d.get("radius", 12)),
            fill=_color(d.get("fill"), [38, 42, 58]),
            color=_color(d.get("color"), [232, 234, 240]),
            binding=d.get("binding"),
            action=d.get("action"),
            layers=layers,
        )

    def to_dict(self):
        out = {
            "id": self.id, "type": self.type, "widthMode": self.width_mode,
            "weight": self.weight, "material": self.material, "radius": self.radius,
            "fill": self.fill, "color": self.color,
            "layers": [l.to_dict() for l in self.layers],
        }
        if self.binding is not None:
            out["binding"] = self.binding
        if self.action is not None:
            out["action"] = self.action
        return out

    # the icon layer (if any) — convenience for the compositor / converter ----
    def icon_layer(self):
        for l in self.layers:
            if l.kind == "icon":
                return l
        return None

    def background_layer(self):
        for l in self.layers:
            if l.kind == "background":
                return l
        return None

    def effects(self):
        return [l for l in self.layers if l.kind == "effect"]

    def motions(self):
        return [l for l in self.layers if l.kind == "motion"]


# ── a trigger: the situation that makes a scene live ─────────────────────────
@dataclass
class Trigger:
    """When a scene becomes the active one. Phase 1 supports ``always`` (base) and
    ``media`` (via the existing MPRIS watcher). ``app``/``stat``/``clock`` are
    declared now so scenes can be authored ahead of the sources landing."""
    kind: str = "always"            # one of TRIGGER_KINDS
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return cls("always", {})
        kind = d.get("kind", "always")
        params = {k: v for k, v in d.items() if k != "kind"}
        return cls(kind=kind, params=params)

    def to_dict(self):
        return {"kind": self.kind, **self.params}

    def describe(self):
        """One-line human description, e.g. 'when ▶ media playing'."""
        if self.kind == "always":
            return "always on · the fallback"
        if self.kind == "media":
            st = self.params.get("state", "playing")
            return f"when ▶ media {st}"
        if self.kind == "app":
            return f"when ⌨ {self.params.get('matches', 'app')} focused"
        if self.kind == "stat":
            m = self.params.get("metric", "cpu")
            return f"when {m} {self.params.get('op', '>')} {self.params.get('value', '')}"
        if self.kind == "clock":
            return f"when clock {self.params.get('from', '')}–{self.params.get('to', '')}"
        return self.kind


# ── a scene: a situation + what the strip becomes ────────────────────────────
@dataclass
class Scene:
    id: str = ""
    name: str = "Scene"
    priority: int = 1
    trigger: Trigger = field(default_factory=Trigger)
    background: list = field(default_factory=list)   # scene-wide background layer stack
    parts: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d, taken=None):
        taken = taken if taken is not None else set()
        sid = d.get("id") or _gen_id("scene", taken)
        taken.add(sid)
        ptaken = set()
        parts = [Part.from_dict(p, ptaken) for p in d.get("parts", [])]
        bg = d.get("background", [])
        if isinstance(bg, dict):          # tolerate {"layers": [...]}
            bg = bg.get("layers", [])
        btaken = set()
        background = [Layer.from_dict(l, btaken) for l in bg]
        return cls(
            id=sid,
            name=d.get("name", sid),
            priority=int(d.get("priority", 1)),
            trigger=Trigger.from_dict(d.get("trigger")),
            background=background,
            parts=parts,
        )

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "priority": self.priority,
            "trigger": self.trigger.to_dict(),
            "background": [l.to_dict() for l in self.background],
            "parts": [p.to_dict() for p in self.parts],
        }


# ── the whole config ─────────────────────────────────────────────────────────
@dataclass
class SceneConfig:
    version: int = SCHEMA_VERSION
    model: str = MODEL_TAG
    scenes: list = field(default_factory=list)       # non-base scenes
    always: Optional[Scene] = None                   # the priority-0 base
    library: dict = field(default_factory=dict)      # imported assets + packs
    geometry: dict = field(default_factory=lambda: {"width": 2170, "height": 60,
                                                    "margin": 10, "gap": 10})

    @classmethod
    def from_dict(cls, d):
        taken = set()
        scenes = [Scene.from_dict(s, taken) for s in d.get("scenes", [])]
        always = d.get("always")
        always_scene = Scene.from_dict(always, taken) if always else None
        if always_scene:
            always_scene.priority = 0
            if always_scene.trigger.kind != "always":
                always_scene.trigger = Trigger("always", {})
        geom = {"width": 2170, "height": 60, "margin": 10, "gap": 10}
        geom.update(d.get("geometry", {}))
        return cls(
            version=int(d.get("version", SCHEMA_VERSION)),
            model=d.get("model", MODEL_TAG),
            scenes=scenes,
            always=always_scene,
            library=dict(d.get("library", {})),
            geometry=geom,
        )

    def to_dict(self):
        out = {
            "version": self.version, "model": self.model,
            "geometry": self.geometry,
            "scenes": [s.to_dict() for s in self.scenes],
        }
        if self.always:
            out["always"] = self.always.to_dict()
        if self.library:
            out["library"] = self.library
        return out

    def ensure_ids(self):
        """Fill in any blank scene/part/layer ids deterministically. Convenience
        constructors leave ids empty; call this once after building a config so it
        round-trips stably and the GUI has stable handles."""
        staken = set()
        for s in self.all_scenes():
            if not s.id:
                s.id = _gen_id("scene", staken)
            staken.add(s.id)
            btaken = set()
            for l in s.background:
                if not l.id:
                    l.id = _gen_id("l", btaken)
                btaken.add(l.id)
            ptaken = set()
            for p in s.parts:
                if not p.id:
                    p.id = _gen_id("p", ptaken)
                ptaken.add(p.id)
                ltaken = set()
                for l in p.layers:
                    if not l.id:
                        l.id = _gen_id("l", ltaken)
                    ltaken.add(l.id)
        return self

    def all_scenes(self):
        """Every scene including the base, highest priority first."""
        scenes = list(self.scenes)
        if self.always:
            scenes.append(self.always)
        return sorted(scenes, key=lambda s: s.priority, reverse=True)

    def scene_by_id(self, sid):
        for s in self.all_scenes():
            if s.id == sid:
                return s
        return None

    def copy(self):
        return SceneConfig.from_dict(copy.deepcopy(self.to_dict()))


# ── detection + load/save ────────────────────────────────────────────────────
def is_scene_config(raw):
    """True if ``raw`` (a parsed dict) is a new Scenes config, not a legacy one."""
    return isinstance(raw, dict) and (
        raw.get("model") == MODEL_TAG or "scenes" in raw or "always" in raw
    )


def from_dict(raw):
    return SceneConfig.from_dict(raw)


def load(path):
    with open(path) as f:
        return SceneConfig.from_dict(json.load(f))


def save(cfg, path):
    with open(path, "w") as f:
        json.dump(cfg.to_dict(), f, indent=2)
        f.write("\n")


class Hot:
    """Reload a Scenes config when its file mtime changes — the live-edit loop.

    Mirrors ``config.Hot`` (the legacy watcher) but for the new schema. Keeps the
    last good config on a bad edit so a half-saved file never blanks the bar."""

    def __init__(self, path):
        import os
        self._os = os
        self.path = path
        self._mtime = 0
        self.config = None
        self.error = None

    def poll(self):
        """Return the (re)loaded ``SceneConfig`` if the file changed, else None."""
        try:
            m = self._os.path.getmtime(self.path)
        except OSError:
            return None
        if m == self._mtime:
            return None
        self._mtime = m
        try:
            self.config = load(self.path)
            self.error = None
        except Exception as e:           # keep the last good config on a bad edit
            self.error = str(e)
            print(f"[t1bar] scene config error (keeping previous): {e}", flush=True)
            return None
        return self.config
