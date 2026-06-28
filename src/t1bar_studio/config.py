"""Load + normalise the JSON config, and watch it for live edits (hot-reload).

The config is intentionally simple/forgiving: missing theme values fall back to
DEFAULT_THEME, so a button only needs what it overrides. See README for the schema.
"""
import copy
import json
import os

DEFAULT_THEME = {
    "background": [8, 10, 18],
    "button": {
        "fill": [38, 42, 58],       # background
        "text": [232, 234, 240],    # foreground (label + icon); per-item: "color"
        "radius": 12,
        "font_size": 26,
    },
    "pressed": {"fill": [70, 110, 210], "color": [255, 255, 255]},
    "accent": [80, 150, 240],          # scrubber fill, highlights
    "track": [60, 64, 82],             # scrubber background
    "gap": 10,                          # px between items
    "margin": 10,                       # px around the whole strip
}


def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def normalise(raw):
    cfg = copy.deepcopy(raw)
    cfg["theme"] = _deep_merge(DEFAULT_THEME, raw.get("theme", {}))
    cfg.setdefault("layouts", {})
    cfg.setdefault("rules", [{"show": next(iter(cfg["layouts"]), "default")}])
    for name, layout in cfg["layouts"].items():
        layout.setdefault("items", [])
        for it in layout["items"]:
            it.setdefault("type", "button")
            it.setdefault("weight", 1.0)
    return cfg


def load(path):
    with open(path) as f:
        return normalise(json.load(f))


class Hot:
    """Reload `path` when its mtime changes — the basis of live preview."""

    def __init__(self, path):
        self.path = path
        self._mtime = 0
        self.config = None
        self.error = None

    def poll(self):
        """Return the (re)loaded config if it changed since last poll, else None."""
        try:
            m = os.path.getmtime(self.path)
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
            print(f"[t1bar] config error (keeping previous): {e}", flush=True)
            return None
        return self.config
