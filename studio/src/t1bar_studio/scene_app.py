"""Scene Home — the native GTK4/libadwaita front of the Scenes rebuild.

This is the **spine** view (concept §1): browse / create / prioritise / select scenes
and see which one is live *right now*. It is the app's home and the replacement for the
old single-window editor (now removed). Chrome is neutral
graphite, native dark; **the only colour is on the strip** — every scene card carries
a real **live mini-render** of that scene produced by the actual ``compose`` engine, so
the previews are honest, not mocked.

Design tokens honoured (CONCEPT-README §Design Tokens): page ``#0b0b0d``, surfaces
``#161618``/``#1d1d20``, hairlines white @6–8%, text ``#ededef``/``#9a9aa0``/``#6a6a72``,
status green ``#46c479`` (only for live/active). Eyebrows + technical labels in **Space
Mono** (uppercase, letter-spaced); names/headings in the system/Inter UI font.

Headless verification: ``run(path, shot=PATH)`` renders the window to a PNG via
``Gtk.WidgetPaintable`` (the only reliable Wayland capture) and quits — set
``T1BAR_SHOT_PLAYING=1`` to force the media-playing state so the active card shows.
"""
from __future__ import annotations

import io
import math
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import compose, context, model, scenes  # noqa: E402

CSS = b"""
window.scene-home { background: #0b0b0d; }
.eyebrow {
  font-family: "Space Mono", monospace;
  font-size: 11px; font-weight: 700; letter-spacing: 3px;
  color: #6a6a72; text-transform: uppercase;
}
.display-title { font-size: 30px; font-weight: 800; letter-spacing: -1px; color: #ededef; }
.display-title .dim { color: #6a6a72; }
.subhead { font-size: 14px; color: #9a9aa0; }

.live-bar { background: #141416; border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px; padding: 14px 18px; }
.live-dot { color: #46c479; font-size: 13px; }
.live-name { color: #ededef; font-weight: 700; }
.live-why  { color: #6a6a72; font-family: "Space Mono", monospace; font-size: 12px; }

.hero-panel { background: #141416; border: 1px solid rgba(255,255,255,0.06);
              border-radius: 16px; padding: 18px; }
.hero-strip { background: #000; border-radius: 9px; padding: 4px; }
.hero-cap { font-family: "Space Mono", monospace; font-size: 11px; color: #5e5e66;
            letter-spacing: 1px; }

.scene-card { background: #161618; border: 1px solid rgba(255,255,255,0.06);
              border-radius: 13px; padding: 14px; }
.scene-card.card-button { box-shadow: none; }
.scene-card.card-button:hover { background: #1b1b1e; border-color: rgba(255,255,255,0.12); }
.scene-card.active { border: 1px solid #46c479; background: #14181550; }
.editor-preview { background: #000; border-radius: 8px; padding: 4px; }
.editor-canvas { background: #000; border-radius: 8px; padding: 4px;
  border: 1px solid rgba(255,255,255,0.08); }
.editor-hint { font-family: "Space Mono", monospace; font-size: 11px; color: #6a6a72; }
.craft-name { font-size: 20px; font-weight: 800; color: #ededef; }
.part-row-type { font-family: "Space Mono", monospace; font-size: 11px; color: #9a9aa0;
                 letter-spacing: 1px; }
.scene-name { color: #ededef; font-weight: 700; font-size: 15px; }
.scene-prio { font-family: "Space Mono", monospace; font-size: 11px; color: #6a6a72;
              letter-spacing: 1px; }
.scene-active-tag { font-family: "Space Mono", monospace; font-size: 11px; color: #46c479;
                    letter-spacing: 1px; }
.mini-strip { background: #000; border-radius: 7px; padding: 3px; }
.scene-trigger { font-family: "Space Mono", monospace; font-size: 11px; color: #6a6a72;
                 letter-spacing: 0.5px; }
.add-card { background: transparent; border: 1px dashed rgba(255,255,255,0.12);
            border-radius: 13px; color: #6a6a72; }
.add-card:hover { border-color: rgba(255,255,255,0.22); color: #9a9aa0; }
"""


# ── PIL → GTK texture, and scene mini-renders ────────────────────────────────
def pil_to_texture(img):
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.getvalue()))


def preview_geometry(w, h):
    """Geometry for a card/hero preview at a chosen display size — margins/gaps
    scaled to the preview height so parts aren't dwarfed by hardware-sized padding."""
    return {"width": w, "height": h,
            "margin": max(2, round(h * 0.12)), "gap": max(2, round(h * 0.16))}


def scene_texture(cfg, scene, live, w, h, scale=2):
    """Render ``scene`` to a Gdk.Texture at display size (w×h), supersampled ×scale
    for crispness on HiDPI. Uses the real compositor — an honest preview."""
    geom = preview_geometry(w * scale, h * scale)
    img = compose.render_scene(scene, geom, live,
                               theme=(cfg.library or {}).get("legacyTheme", {}))
    return pil_to_texture(img)


def _picture(texture, w, h):
    pic = Gtk.Picture.new_for_paintable(texture)
    pic.set_content_fit(Gtk.ContentFit.FILL)
    pic.set_size_request(w, h)
    return pic


# ── the window ───────────────────────────────────────────────────────────────
class SceneHome(Adw.ApplicationWindow):
    HERO_W, HERO_H = 1140, 32
    CARD_STRIP_W, CARD_STRIP_H = 430, 26

    def __init__(self, app, path):
        super().__init__(application=app)
        self.add_css_class("scene-home")
        self.set_default_size(1180, 860)
        self.set_title("t1bar studio")
        self.path = path
        self.cfg = model.load(path)
        self.media = None
        self.fake_playing = bool(os.environ.get("T1BAR_SHOT_PLAYING"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        new_btn = Gtk.Button(label="New scene")
        new_btn.connect("clicked", self._on_new_scene)
        header.pack_end(new_btn)
        toolbar.add_top_bar(header)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.body.set_margin_top(8)
        self.body.set_margin_bottom(28)
        self.body.set_margin_start(28)
        self.body.set_margin_end(28)
        clamp = Adw.Clamp(maximum_size=1200, child=self.body)
        scroller.set_child(clamp)
        toolbar.set_content(scroller)
        self.set_content(toolbar)

        self._build()
        if not self.fake_playing:
            self.media = context.MediaWatcher().start()
            GLib.timeout_add_seconds(2, self._refresh_live)

    # -- live state -----------------------------------------------------------
    def _live(self):
        if self.fake_playing:
            return {"media": {"status": "Playing", "position": 96, "length": 210,
                              "title": "Tame Impala — Borderline", "artist": "Tame Impala"},
                    "clock": "12:40", "cpu": 38}
        m = self.media.state if self.media else {}
        return {"media": m, "clock": GLib.DateTime.new_now_local().format("%H:%M"),
                "cpu": 0}

    # -- build the page -------------------------------------------------------
    def _build(self):
        for c in list(self.body):
            self.body.remove(c)
        live = self._live()
        active, why = scenes.resolve_with_reason(self.cfg, live)

        # masthead
        eyebrow = Gtk.Label(label="CONCEPT · SCENE HOME", xalign=0)
        eyebrow.add_css_class("eyebrow")
        title = Gtk.Label(xalign=0)
        title.add_css_class("display-title")
        title.set_markup('t1bar<span foreground="#6a6a72"> studio</span>')
        sub = Gtk.Label(
            label="Define situations — the strip becomes what the moment needs.",
            xalign=0, wrap=True)
        sub.add_css_class("subhead")
        for w in (eyebrow, title, sub):
            self.body.append(w)

        # live indicator + hero strip of the active scene
        self.body.append(self._live_bar(active, why))
        self.body.append(self._hero(active, live))

        # the spine: scene cards
        spine_eyebrow = Gtk.Label(label="01 · THE SPINE", xalign=0)
        spine_eyebrow.add_css_class("eyebrow")
        spine_eyebrow.set_margin_top(6)
        self.body.append(spine_eyebrow)

        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           min_children_per_line=2, max_children_per_line=2,
                           column_spacing=14, row_spacing=14, homogeneous=True)
        for scene in self.cfg.all_scenes():
            flow.append(self._scene_card(scene, scene is active, live))
        flow.append(self._add_card())
        self.body.append(flow)

    def _live_bar(self, active, why):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.add_css_class("live-bar")
        dot = Gtk.Label(label="●")
        dot.add_css_class("live-dot")
        name = Gtk.Label(xalign=0)
        name.add_css_class("live-name")
        name.set_text(f'Live: "{active.name}"' if active else "No scene")
        whyl = Gtk.Label(label=f"— because {why}", xalign=0)
        whyl.add_css_class("live-why")
        bar.append(dot)
        bar.append(name)
        bar.append(whyl)
        return bar

    def _hero(self, active, live):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("hero-panel")
        if active:
            strip_box = Gtk.Box()
            strip_box.add_css_class("hero-strip")
            tex = scene_texture(self.cfg, active, live, self.HERO_W, self.HERO_H)
            strip_box.append(_picture(tex, self.HERO_W, self.HERO_H))
            panel.append(strip_box)
        cap = Gtk.Label(
            label="rendered at true 36:1  ·  this lights up on the physical strip within ~1s",
            xalign=0.5)
        cap.add_css_class("hero-cap")
        panel.append(cap)
        return panel

    def _scene_card(self, scene, is_active, live):
        card = Gtk.Button()
        card.add_css_class("scene-card")
        card.add_css_class("card-button")
        if is_active:
            card.add_css_class("active")
        card.connect("clicked", lambda _b, s=scene: self._open_editor(s))
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        card.set_child(inner)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        name = Gtk.Label(label=scene.name, xalign=0, hexpand=True)
        name.add_css_class("scene-name")
        top.append(name)
        if is_active:
            tag = Gtk.Label(label=f"● active · prio {scene.priority}")
            tag.add_css_class("scene-active-tag")
        elif scene.priority == 0:
            tag = Gtk.Label(label="base · prio 0")
            tag.add_css_class("scene-prio")
        else:
            tag = Gtk.Label(label=f"prio {scene.priority}")
            tag.add_css_class("scene-prio")
        top.append(tag)
        inner.append(top)

        strip_box = Gtk.Box()
        strip_box.add_css_class("mini-strip")
        tex = scene_texture(self.cfg, scene, live, self.CARD_STRIP_W, self.CARD_STRIP_H)
        strip_box.append(_picture(tex, self.CARD_STRIP_W, self.CARD_STRIP_H))
        inner.append(strip_box)

        trig = Gtk.Label(label=scene.trigger.describe(), xalign=0)
        trig.add_css_class("scene-trigger")
        inner.append(trig)
        return card

    def _open_editor(self, scene):
        ed = SceneEditor(self, self.cfg, self.path, scene, on_change=self._build)
        ed.present()

    def _add_card(self):
        btn = Gtk.Button()
        btn.add_css_class("add-card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_valign(Gtk.Align.CENTER)
        plus = Gtk.Label(label="+")
        plus.add_css_class("display-title")
        lbl = Gtk.Label(label="New scene")
        lbl.add_css_class("scene-trigger")
        inner.append(plus)
        inner.append(lbl)
        btn.set_child(inner)
        btn.connect("clicked", self._on_new_scene)
        return btn

    # -- actions (stubs for now; wired in later phases) -----------------------
    def _on_new_scene(self, _btn):
        print("[t1bar] new-scene (not yet wired — Auto-flow editor lands next phase)",
              flush=True)

    def _refresh_live(self):
        self._build()
        return True


MATERIALS = ("solid", "frosted", "outline", "ghost", "metal")

# What a button can fire when pressed — the curated `action` set the runtime
# (actions.dispatch) already supports. Each entry is (short label, action list|None);
# every key here is in actions._EMIT_KEYS, emitted via uinput (and pops the desktop OSD).
KEY_ACTIONS = [
    ("—", None),
    ("Esc", ["key", "KEY_ESC"]),
    *[(f"F{i}", ["key", f"KEY_F{i}"]) for i in range(1, 13)],
    ("Bright +", ["key", "KEY_BRIGHTNESSUP"]),
    ("Bright −", ["key", "KEY_BRIGHTNESSDOWN"]),
    ("KbdLt +", ["key", "KEY_KBDILLUMUP"]),
    ("KbdLt −", ["key", "KEY_KBDILLUMDOWN"]),
    ("Vol +", ["key", "KEY_VOLUMEUP"]),
    ("Vol −", ["key", "KEY_VOLUMEDOWN"]),
    ("Mute", ["key", "KEY_MUTE"]),
    ("Play/Pause", ["key", "KEY_PLAYPAUSE"]),
    ("Next", ["key", "KEY_NEXTSONG"]),
    ("Prev", ["key", "KEY_PREVIOUSSONG"]),
]

# What a part can show — the finite icon kit (icons.ICONS) + the live play/pause
# dynamic. Each entry is (short label, icon name|None, dynamic name|None).
ICON_CHOICES = [
    ("— none —", None, None),
    ("Play", "play", None),
    ("Pause", "pause", None),
    ("Prev", "prev", None),
    ("Next", "next", None),
    ("Play/Pause ↻", "play", "play_pause"),
    ("Bright +", "brightness_up", None),
    ("Bright −", "brightness_down", None),
    ("Vol +", "volume_up", None),
    ("Vol −", "volume_down", None),
    ("Mute", "volume_mute", None),
    ("Full", "fullscreen", None),
    ("CC", "cc", None),
]


# Live data a slider/readout can bind to (Part.binding["source"]).
BINDING_SOURCES = [
    ("(none)", None),
    ("media.position", "media.position"),
    ("media.title", "media.title"),
    ("media.artist", "media.artist"),
    ("cpu", "cpu"),
    ("gpu", "gpu"),
    ("clock", "clock"),
]


def _describe_action(action):
    if not action:
        return "—"
    if action[0] == "key":
        return action[1].replace("KEY_", "").title()
    if action[0] == "media":
        return f"media: {action[1]}"
    return action[0]


def _action_index(action):
    for i, (_lbl, a) in enumerate(KEY_ACTIONS):
        if a == action:
            return i
    return -1


def _icon_index(part):
    il = part.icon_layer()
    if il is None:
        return 0
    icon, dyn = il.params.get("icon"), il.params.get("dynamic")
    for i, (_lbl, ic, dy) in enumerate(ICON_CHOICES):
        if ic == icon and dy == dyn:
            return i
    return 0


def _rgba_to_list(rgba):
    return [round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)]


def _list_to_rgba(c):
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1.0
    return r


def _rounded(cr, x0, y0, x1, y1, r):
    """Trace a rounded-rectangle path on a cairo context."""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    cr.new_sub_path()
    cr.arc(x1 - r, y0 + r, r, -math.pi / 2, 0)
    cr.arc(x1 - r, y1 - r, r, 0, math.pi / 2)
    cr.arc(x0 + r, y1 - r, r, math.pi / 2, math.pi)
    cr.arc(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _swatch(rgb, size=28):
    """A small rounded colour chip."""
    da = Gtk.DrawingArea()
    da.set_content_width(size)
    da.set_content_height(size)
    da.set_valign(Gtk.Align.CENTER)
    rgb = list(rgb) if rgb else [60, 60, 66]

    def draw(_a, cr, w, h):
        _rounded(cr, 1, 1, w - 1, h - 1, 7)
        cr.set_source_rgb(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.set_line_width(1)
        cr.stroke()
    da.set_draw_func(draw)
    return da


def _set_part_color(part, rgb):
    """Apply one colour to a part across the fields the materials actually read."""
    part.fill = list(rgb)
    if part.material in ("ghost", "outline") or part.type in ("label", "readout"):
        part.color = list(rgb)
    for l in part.layers:
        if l.kind == "background":
            l.params["color"] = list(rgb)


class SceneEditor(Adw.Window):
    """Bare-basic but real scene editor — the first usable Compose-altitude loop.

    Edits are **auto-applied** (debounced) to the live config on disk, which the
    running ``scene-run`` service hot-reloads → the change appears on the physical
    strip within ~1s. Edit a part's colour / material / width, reorder, add or remove
    parts. Richer editing (icons, actions, triggers, drag-slots, the Layer Loom)
    layers on top of this working loop in later iterations.
    """
    CANVAS_W, CANVAS_H = 864, 46

    def __init__(self, parent, cfg, path, scene, on_change=None):
        super().__init__(transient_for=parent, modal=False)
        self.set_default_size(900, 640)
        self.set_title(f"Edit scene · {scene.name}")
        self.cfg = cfg
        self.path = path
        self.scene = scene
        self.on_change = on_change
        self._apply_src = 0

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        eyebrow = Gtk.Label(label=f"{scene.trigger.describe().upper()}", xalign=0)
        eyebrow.add_css_class("eyebrow")
        box.append(eyebrow)

        # the bar itself — WYSIWYG. Click an element to edit it; drag to reorder.
        self._sel_id = None
        self._drag_part = None
        self._drag_start = 0.0
        self._drag_target = None
        self.canvas_pic = Gtk.Picture()
        self.canvas_pic.set_content_fit(Gtk.ContentFit.FILL)
        self.canvas_pic.set_size_request(self.CANVAS_W, self.CANVAS_H)
        self.canvas_overlay = Gtk.DrawingArea()
        self.canvas_overlay.set_content_width(self.CANVAS_W)
        self.canvas_overlay.set_content_height(self.CANVAS_H)
        self.canvas_overlay.set_draw_func(self._draw_selection)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_canvas_click)
        self.canvas_overlay.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.canvas_overlay.add_controller(drag)
        canvas = Gtk.Overlay()
        canvas.set_child(self.canvas_pic)
        canvas.add_overlay(self.canvas_overlay)
        canvas.set_halign(Gtk.Align.CENTER)
        canvas.add_css_class("editor-canvas")
        box.append(canvas)

        hint = Gtk.Label(
            label="click an item to edit it · drag to reorder · changes hit the bar within ~1s",
            xalign=0)
        hint.add_css_class("editor-hint")
        box.append(hint)

        # per-item inspector — populated when an element is selected
        self.inspector = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        insp_scroll = Gtk.ScrolledWindow(vexpand=True)
        insp_scroll.set_child(self.inspector)
        box.append(insp_scroll)

        addbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, ptype in (("+ Key", "key"), ("+ Label", "label"),
                             ("+ Spacer", "spacer")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, t=ptype: self._add_part(t))
            addbar.append(b)
        box.append(addbar)

        toolbar.set_content(box)
        self.set_content(toolbar)
        self._refresh_canvas()
        self._refresh_inspector()

    # -- live apply -----------------------------------------------------------
    def _schedule_apply(self):
        if self._apply_src:
            GLib.source_remove(self._apply_src)
        self._apply_src = GLib.timeout_add(250, self._apply)

    def _apply(self):
        self._apply_src = 0
        try:
            model.save(self.cfg, self.path)       # → service hot-reloads → bar updates
        except Exception as e:
            print(f"[t1bar] save failed: {e}", flush=True)
        self._refresh_canvas()
        if self.on_change:
            self.on_change()
        return False

    def _live(self):
        return {"media": {"status": "Playing", "position": 96, "length": 210,
                          "title": "Preview", "artist": ""}, "frac": 0.5}

    def _refresh_canvas(self):
        tex = scene_texture(self.cfg, self.scene, self._live(),
                            self.CANVAS_W, self.CANVAS_H)
        self.canvas_pic.set_paintable(tex)
        self.canvas_overlay.queue_draw()

    # -- the interactive strip ------------------------------------------------
    def _layout_boxes(self, width, height):
        """Per-part display-space rects, matching what the canvas renders."""
        geom = preview_geometry(width, height)
        return compose.layout_parts(self.scene.parts, width, height,
                                    geom["margin"], geom["gap"])

    def _part_at(self, x, width, height):
        for p, (x0, _y0, x1, _y1) in self._layout_boxes(width, height):
            if x0 <= x <= x1:
                return p
        return None

    def _draw_selection(self, _area, cr, width, height):
        if self._drag_part is not None and self._drag_target is not None:
            self._draw_drop_line(cr, width, height)
        part = self._selected()
        if part is None:
            return
        for p, (x0, _y0, x1, _y1) in self._layout_boxes(width, height):
            if p is part:
                cr.set_source_rgba(0.275, 0.769, 0.475, 0.16)     # #46c479 wash
                _rounded(cr, x0, 1, x1, height - 1, 5)
                cr.fill()
                cr.set_source_rgba(0.275, 0.769, 0.475, 0.95)
                cr.set_line_width(2)
                _rounded(cr, x0 + 1, 2, x1 - 1, height - 2, 5)
                cr.stroke()
                break

    def _on_canvas_click(self, _gesture, _n, x, _y):
        w = self.canvas_overlay.get_width() or self.CANVAS_W
        h = self.canvas_overlay.get_height() or self.CANVAS_H
        hit = self._part_at(x, w, h)
        self._select(hit.id if hit else None)

    def _select(self, pid):
        self._sel_id = pid
        self.canvas_overlay.queue_draw()
        self._refresh_inspector()

    def _selected(self):
        return next((p for p in self.scene.parts if p.id == self._sel_id), None)

    # -- drag to reorder (snaps into the auto-flow) ---------------------------
    def _on_drag_begin(self, _g, sx, _sy):
        w = self.canvas_overlay.get_width() or self.CANVAS_W
        h = self.canvas_overlay.get_height() or self.CANVAS_H
        self._drag_part = self._part_at(sx, w, h)
        self._drag_start = sx
        self._drag_target = None
        if self._drag_part is not None:
            self._select(self._drag_part.id)

    def _on_drag_update(self, _g, ox, _oy):
        if self._drag_part is None:
            return
        w = self.canvas_overlay.get_width() or self.CANVAS_W
        h = self.canvas_overlay.get_height() or self.CANVAS_H
        self._drag_target = self._drop_index(self._drag_start + ox, w, h)
        self.canvas_overlay.queue_draw()

    def _on_drag_end(self, _g, _ox, _oy):
        part, target = self._drag_part, self._drag_target
        self._drag_part = None
        self._drag_target = None
        if part is None or target is None:
            self.canvas_overlay.queue_draw()
            return
        parts = self.scene.parts
        before = parts.index(part)
        parts.remove(part)
        parts.insert(target, part)
        if parts.index(part) != before:
            self._refresh_canvas()
            self._schedule_apply()
        else:
            self.canvas_overlay.queue_draw()

    def _drop_index(self, x, width, height):
        """Index at which the dragged part should land — one past every other
        part whose centre is left of the cursor."""
        target = 0
        for p, (x0, _y0, x1, _y1) in self._layout_boxes(width, height):
            if p is self._drag_part:
                continue
            if (x0 + x1) / 2 < x:
                target += 1
        return target

    def _draw_drop_line(self, cr, width, height):
        boxes = [b for p, b in self._layout_boxes(width, height) if p is not self._drag_part]
        gap = preview_geometry(width, height)["gap"]
        t = self._drag_target
        if not boxes:
            lx = width / 2
        elif t <= 0:
            lx = boxes[0][0] - gap / 2
        elif t >= len(boxes):
            lx = boxes[-1][2] + gap / 2
        else:
            lx = (boxes[t - 1][2] + boxes[t][0]) / 2
        cr.set_source_rgba(0.275, 0.769, 0.475, 0.95)
        cr.set_line_width(3)
        cr.move_to(lx, 2)
        cr.line_to(lx, height - 2)
        cr.stroke()

    # -- the per-item inspector ----------------------------------------------
    def _refresh_inspector(self):
        while (c := self.inspector.get_first_child()) is not None:
            self.inspector.remove(c)
        part = self._selected()
        if part is None:
            empty = Gtk.Label(label="select an item on the bar to edit it", xalign=0)
            empty.add_css_class("editor-hint")
            empty.set_margin_top(8)
            self.inspector.append(empty)
            return

        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        cols.append(self._craft_left(part))
        cols.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        right = self._craft_right(part)
        right.set_hexpand(True)
        cols.append(right)
        self.inspector.append(cols)

    # left column: identity + a live preview of just this element + binding
    def _craft_left(self, part):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        col.set_size_request(360, -1)

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hdr.append(_swatch(part.fill, 40))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.set_valign(Gtk.Align.CENTER)
        nm = Gtk.Label(label=part.id, xalign=0)
        nm.add_css_class("craft-name")
        sub = Gtk.Label(label=f"{part.width_mode} {part.type}", xalign=0)
        sub.add_css_class("editor-hint")
        names.append(nm)
        names.append(sub)
        hdr.append(names)
        col.append(hdr)

        preview = Gtk.Box()
        preview.add_css_class("editor-canvas")
        preview.set_halign(Gtk.Align.FILL)
        preview.append(self._element_preview(part))
        col.append(preview)

        if part.type in ("slider", "readout"):
            eb = Gtk.Label(label="LIVE BINDING", xalign=0)
            eb.add_css_class("eyebrow")
            eb.set_margin_top(4)
            col.append(eb)
            src = (part.binding or {}).get("source")
            cur = next((i for i, (_l, s) in enumerate(BINDING_SOURCES) if s == src), 0)
            bd = Gtk.DropDown.new_from_strings([l for l, _s in BINDING_SOURCES])
            bd.set_selected(cur)
            bd.connect("notify::selected",
                       lambda d, _p, p=part: self._set_binding(p, d.get_selected()))
            col.append(bd)
        return col

    def _element_preview(self, part, pw=360, ph=110):
        """A crisp crop of just this element from a real scene render, at the
        true 36:1 strip aspect (supersampled) so proportions aren't distorted."""
        SS = 4
        RW, RH = 2170 * SS, 60 * SS
        geom = preview_geometry(RW, RH)
        theme = (self.cfg.library or {}).get("legacyTheme", {})
        img = compose.render_scene(self.scene, geom, self._live(), theme=theme)
        box = next((b for p, b in
                    compose.layout_parts(self.scene.parts, RW, RH, geom["margin"], geom["gap"])
                    if p is part), None)
        if box is not None:
            x0, _y0, x1, _y1 = (int(v) for v in box)
            pad = 12 * SS
            img = img.crop((max(0, x0 - pad), 0, min(RW, x1 + pad), RH))
        pic = Gtk.Picture.new_for_paintable(pil_to_texture(img))
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_size_request(pw, ph)
        return pic

    def _set_binding(self, part, sel):
        src = BINDING_SOURCES[sel][1]
        part.binding = {"source": src} if src else None
        self._schedule_apply()

    # right column (temporary until the Layer Loom lands): the part's properties
    def _craft_right(self, part):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        eb = Gtk.Label(label="LOOK", xalign=0)
        eb.add_css_class("eyebrow")
        col.append(eb)
        grp = Adw.PreferencesGroup()

        if part.type in ("key", "label", "readout"):
            il = part.icon_layer()
            er = Adw.EntryRow(title="Label")
            er.set_text(il.params.get("label", "") if il else "")
            er.connect("changed", lambda e, p=part: self._set_label(p, e.get_text()))
            grp.add(er)

        if part.type != "spacer":
            crow = Adw.ActionRow(title="Colour")
            cbtn = Gtk.ColorDialogButton.new(Gtk.ColorDialog())
            cbtn.set_rgba(_list_to_rgba(part.fill))
            cbtn.set_valign(Gtk.Align.CENTER)
            cbtn.connect("notify::rgba",
                         lambda b, _p, p=part: self._set_color(p, b.get_rgba()))
            crow.add_suffix(cbtn)
            grp.add(crow)

            mrow = Adw.ComboRow(title="Material",
                                model=Gtk.StringList.new(list(MATERIALS)))
            mrow.set_selected(MATERIALS.index(part.material)
                              if part.material in MATERIALS else 0)
            mrow.connect("notify::selected",
                         lambda d, _p, p=part: self._set_material(p, d.get_selected()))
            grp.add(mrow)

        if part.type in ("key", "transport"):
            irow = Adw.ComboRow(title="Icon",
                                model=Gtk.StringList.new([l for l, _i, _d in ICON_CHOICES]))
            irow.set_selected(_icon_index(part))
            irow.connect("notify::selected",
                         lambda d, _p, p=part: self._set_icon(p, d.get_selected()))
            grp.add(irow)

            arow = Adw.ComboRow(title="Action",
                                model=Gtk.StringList.new([l for l, _a in KEY_ACTIONS]))
            cur = _action_index(part.action)
            arow.set_selected(cur if cur >= 0 else 0)
            if cur < 0 and part.action is not None:
                arow.set_subtitle(f"currently {_describe_action(part.action)}")
            arow.connect("notify::selected",
                         lambda d, _p, p=part: self._set_action(p, d.get_selected(), False))
            grp.add(arow)

        srow = Adw.SwitchRow(title="Stretchy", subtitle="fills remaining space")
        srow.set_active(part.width_mode == "stretchy")
        srow.connect("notify::active",
                     lambda s, _p, p=part: self._set_width(p, s.get_active()))
        grp.add(srow)
        col.append(grp)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_top(4)
        left = Gtk.Button(label="◀ move left")
        left.connect("clicked", lambda _b: self._move_sel(-1))
        right = Gtk.Button(label="move right ▶")
        right.connect("clicked", lambda _b: self._move_sel(1))
        rm = Gtk.Button(label="Remove")
        rm.add_css_class("destructive-action")
        rm.connect("clicked", lambda _b: self._remove_sel())
        bar.append(left)
        bar.append(right)
        bar.append(Gtk.Box(hexpand=True))
        bar.append(rm)
        col.append(bar)
        return col

    # -- edits ----------------------------------------------------------------
    def _set_label(self, part, text):
        il = part.icon_layer()
        if il is None:
            from .model import Layer
            il = Layer.icon(label=text, color=part.color)
            il.id = f"{part.id}_icon"
            part.layers.append(il)
        else:
            il.params["label"] = text
            if text:                       # text replaces an icon to avoid overlap
                il.params["icon"] = None
                il.params["dynamic"] = None
        self._schedule_apply()

    def _set_action(self, part, sel, has_extra):
        if has_extra:
            if sel == 0:                   # kept the existing (unlisted) action
                return
            sel -= 1
        action = KEY_ACTIONS[sel][1]
        part.action = list(action) if action else None
        self._schedule_apply()

    def _set_icon(self, part, sel):
        _lbl, icon, dyn = ICON_CHOICES[sel]
        il = part.icon_layer()
        if il is None:
            from .model import Layer
            il = Layer.icon(name=icon, color=part.color, dynamic=dyn)
            il.id = f"{part.id}_icon"
            part.layers.append(il)
        else:
            il.params["icon"] = icon
            il.params["dynamic"] = dyn
            if icon or dyn:                # an icon replaces a label to avoid overlap
                il.params["label"] = ""
        self._schedule_apply()

    def _set_color(self, part, rgba):
        _set_part_color(part, _rgba_to_list(rgba))
        self._schedule_apply()

    def _set_material(self, part, sel):
        part.material = MATERIALS[sel]
        self._schedule_apply()

    def _set_width(self, part, stretchy):
        part.width_mode = "stretchy" if stretchy else "fixed"
        self._schedule_apply()

    def _move_sel(self, delta):
        part = self._selected()
        if part is None:
            return
        parts = self.scene.parts
        i = parts.index(part)
        j = i + delta
        if 0 <= j < len(parts):
            parts[i], parts[j] = parts[j], parts[i]
            self._refresh_canvas()
            self._schedule_apply()

    def _remove_sel(self):
        part = self._selected()
        if part and part in self.scene.parts:
            self.scene.parts.remove(part)
            self._sel_id = None
            self._refresh_canvas()
            self._refresh_inspector()
            self._schedule_apply()

    def _add_part(self, ptype):
        from .model import Layer, Part
        taken = {p.id for p in self.scene.parts}
        i = 1
        while f"{ptype}{i}" in taken:
            i += 1
        pid = f"{ptype}{i}"
        if ptype == "spacer":
            part = Part(type="spacer", id=pid, width_mode="stretchy", weight=0.5)
        elif ptype == "label":
            part = Part(type="label", id=pid, width_mode="stretchy", material="ghost",
                        color=[232, 234, 240],
                        layers=[Layer.icon(label="text", color=[232, 234, 240])])
        else:
            part = Part(type="key", id=pid, width_mode="fixed", material="solid",
                        fill=[58, 110, 165], color=[240, 245, 255],
                        layers=[Layer.background([58, 110, 165]),
                                Layer.icon(label="key", color=[240, 245, 255])])
        for l in part.layers:
            if not l.id:
                l.id = f"{pid}_{l.kind}"
        self.scene.parts.append(part)
        self._sel_id = pid
        self._refresh_canvas()
        self._refresh_inspector()
        self._schedule_apply()


class App(Adw.Application):
    def __init__(self, path, shot=None):
        super().__init__(application_id="za.co.cloudnexus.t1bar.scenes",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path
        self.shot = shot
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def do_activate(self):
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = SceneHome(self, self.path)
        win.present()
        if self.shot:
            if os.environ.get("T1BAR_SHOT_EDIT"):
                scene = win.cfg.all_scenes()[0]
                self._edit = SceneEditor(win, win.cfg, self.path, scene)
                self._edit.present()
                GLib.timeout_add(1400, self._save_shot, self._edit)
            else:
                GLib.timeout_add(1400, self._save_shot, win)

    def _save_shot(self, win):
        try:
            w, h = win.get_width(), win.get_height()
            paintable = Gtk.WidgetPaintable.new(win)
            snap = Gtk.Snapshot()
            paintable.snapshot(snap, w, h)
            node = snap.to_node()
            if node is not None:
                tex = win.get_renderer().render_texture(node, None)
                tex.save_to_png(self.shot)
                print(f"[t1bar] saved shot {self.shot} ({w}x{h})", flush=True)
        except Exception as e:
            print(f"[t1bar] shot failed: {e}", flush=True)
        self.quit()
        return False


def run(path, shot=None):
    App(path, shot).run([])
