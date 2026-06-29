"""Convert a legacy t1bar config (theme/layouts/items/rules) into a starter
Scenes config (the new ``model.SceneConfig``).

The mapping is faithful, not magic:

  * **each rule → a scene.** Rules are evaluated top→down (first match wins), so
    the top rule becomes the highest-priority scene and the catch-all rule (the one
    with no ``when``) becomes the **Always** base (priority 0).
  * **a rule's ``when`` → a Trigger.** ``{"media": "playing"}`` → media-playing.
  * **a layout's items → parts.** button → key/transport, scrubber → slider,
    label → label, spacer → spacer. Each part gets a Layer Loom: a background layer
    (its fill) plus an icon layer (its glyph/label), so the new compositor has a
    real stack to composite even straight out of the converter.
  * **theme → scene background + part defaults.** ``theme.background`` becomes a
    solid scene background; ``theme.accent``/``track``/``pressed`` are preserved in
    ``library.legacyTheme`` so nothing from the old config is lost.

This is the "get something from the new model" seam: feed it the live
``~/.config/t1bar/config.json`` and you get a scenes config you can render headless.
"""
from __future__ import annotations

from . import config as legacy_config
from .model import Layer, Part, Scene, SceneConfig, Trigger

# friendlier scene names for the layout names we ship today
_NAME_MAP = {"default": "Always", "media": "Watching", "coding": "Coding",
             "gaming": "Gaming", "watching": "Watching"}

# icons that mean "this button is a media transport control"
_TRANSPORT_ICONS = {"play", "pause", "prev", "next"}


def _scene_name(layout_name):
    return _NAME_MAP.get(layout_name, layout_name.replace("_", " ").title())


def _trigger_from_when(when):
    if not when:
        return Trigger("always", {})
    if "media" in when:
        return Trigger("media", {"state": when["media"]})
    if "app" in when:
        return Trigger("app", {"matches": when["app"]})
    if "window" in when:
        return Trigger("app", {"matches": when["window"]})
    return Trigger("always", {})


def _convert_item(item, theme):
    """One legacy item → one Part (with a starter Layer Loom)."""
    t = item.get("type", "button")
    weight = float(item.get("weight", 1.0))
    bt = theme["button"]
    radius = int(bt.get("radius", 12))
    font_size = int(item.get("font_size", bt.get("font_size", 26)))

    if t == "spacer":
        return Part(type="spacer", width_mode="stretchy", weight=weight,
                    material="ghost", layers=[])

    if t == "scrubber":
        accent = list(theme.get("accent", [90, 170, 250]))
        track = list(theme.get("track", [55, 60, 78]))
        return Part(
            type="slider", id=item.get("id", ""), width_mode="stretchy",
            weight=weight, material="solid", radius=radius,
            fill=accent, color=track,
            binding={"source": "media.position"} if item.get("source") == "media_position" else None,
            action=item.get("action"),
            layers=[Layer.background(track, type="solid")],
        )

    if t == "label":
        color = list(item.get("color", bt.get("text", [232, 234, 240])))
        src = item.get("source")
        binding = {"source": {"media_title": "media.title",
                              "media_artist": "media.artist"}.get(src, src)} if src else None
        return Part(
            type="label", id=item.get("id", ""), width_mode="stretchy",
            weight=weight, material="ghost", radius=radius, color=color,
            binding=binding,
            layers=[Layer.icon(label=item.get("label", ""), color=color, size=font_size)],
        )

    # default: a button → key or transport
    icon = item.get("icon")
    dynamic = item.get("dynamic")
    is_transport = dynamic == "play_pause" or icon in _TRANSPORT_ICONS
    fill = list(item.get("fill", bt.get("fill", [38, 42, 58])))
    color = list(item.get("color", bt.get("text", [232, 234, 240])))
    return Part(
        type="transport" if is_transport else "key",
        id=item.get("id", ""), width_mode="fixed", weight=weight,
        material="solid", radius=radius, fill=fill, color=color,
        action=item.get("action"),
        layers=[
            Layer.background(fill, type="solid"),
            Layer.icon(name=icon, label=item.get("label", ""), color=color,
                       dynamic=dynamic, size=font_size),
        ],
    )


def _convert_layout(cfg, layout_name, theme):
    layout = cfg["layouts"].get(layout_name, {"items": []})
    return [_convert_item(it, theme) for it in layout.get("items", [])]


def convert(legacy_cfg):
    """Legacy normalised config (dict) → ``SceneConfig``."""
    theme = legacy_cfg["theme"]
    bg_color = list(theme.get("background", [8, 10, 18]))
    rules = legacy_cfg.get("rules", []) or [{"show": next(iter(legacy_cfg["layouts"]), None)}]

    scenes = []
    always = None
    prio = len(rules)            # top rule → highest priority

    for rule in rules:
        when = rule.get("when")
        layout_name = rule.get("show")
        if layout_name not in legacy_cfg["layouts"]:
            continue
        parts = _convert_layout(legacy_cfg, layout_name, theme)
        background = [Layer.background(bg_color, type="solid")]
        if when is None:         # the catch-all → the Always base
            always = Scene(id=layout_name, name=_scene_name(layout_name),
                           priority=0, trigger=Trigger("always", {}),
                           background=background, parts=parts)
        else:
            scenes.append(Scene(id=layout_name, name=_scene_name(layout_name),
                                priority=prio, trigger=_trigger_from_when(when),
                                background=background, parts=parts))
            prio -= 1

    # no explicit catch-all? demote the lowest-priority scene to the base.
    if always is None and scenes:
        always = min(scenes, key=lambda s: s.priority)
        scenes.remove(always)
        always.priority = 0
        always.trigger = Trigger("always", {})

    cfg = SceneConfig(
        scenes=scenes,
        always=always,
        library={"legacyTheme": {
            "accent": list(theme.get("accent", [90, 170, 250])),
            "track": list(theme.get("track", [55, 60, 78])),
            "pressed": dict(theme.get("pressed", {})),
        }},
        geometry={"width": 2170, "height": 60,
                  "margin": int(theme.get("margin", 10)),
                  "gap": int(theme.get("gap", 10))},
    )
    return cfg.ensure_ids()


def convert_file(legacy_path):
    """Load a legacy config from disk and convert it. Returns a ``SceneConfig``."""
    return convert(legacy_config.load(legacy_path))
