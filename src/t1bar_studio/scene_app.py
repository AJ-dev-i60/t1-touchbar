"""Scene Home — the native GTK4/libadwaita front of the Scenes rebuild.

This is the **spine** view (concept §1): browse / create / prioritise / select scenes
and see which one is live *right now*. It is a fresh app, NOT the rejected
``editor_gtk.py`` (which stays runnable until fully replaced). Chrome is neutral
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
.editor-hint { font-family: "Space Mono", monospace; font-size: 11px; color: #6a6a72; }
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


def _rgba_to_list(rgba):
    return [round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)]


def _list_to_rgba(c):
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1.0
    return r


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
    PREVIEW_W, PREVIEW_H = 720, 30

    def __init__(self, parent, cfg, path, scene, on_change=None):
        super().__init__(transient_for=parent, modal=False)
        self.set_default_size(780, 620)
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

        self.preview_box = Gtk.Box()
        self.preview_box.add_css_class("editor-preview")
        box.append(self.preview_box)

        hint = Gtk.Label(
            label="edits apply to the live bar within ~1s", xalign=0)
        hint.add_css_class("editor-hint")
        box.append(hint)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self.listbox)
        box.append(scroller)

        addbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for label, ptype in (("+ Key", "key"), ("+ Label", "label"),
                             ("+ Spacer", "spacer")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, t=ptype: self._add_part(t))
            addbar.append(b)
        box.append(addbar)

        toolbar.set_content(box)
        self.set_content(toolbar)
        self._rebuild_rows()
        self._refresh_preview()

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
        self._refresh_preview()
        if self.on_change:
            self.on_change()
        return False

    def _refresh_preview(self):
        child = self.preview_box.get_first_child()
        if child:
            self.preview_box.remove(child)
        live = {"media": {"status": "Playing", "position": 96, "length": 210,
                          "title": "Preview", "artist": ""}, "frac": 0.5}
        tex = scene_texture(self.cfg, self.scene, live, self.PREVIEW_W, self.PREVIEW_H)
        self.preview_box.append(_picture(tex, self.PREVIEW_W, self.PREVIEW_H))

    # -- part rows ------------------------------------------------------------
    def _rebuild_rows(self):
        while (row := self.listbox.get_first_child()) is not None:
            self.listbox.remove(row)
        for idx, part in enumerate(self.scene.parts):
            self.listbox.append(self._part_row(part, idx))

    def _part_row(self, part, idx):
        row = Adw.ActionRow()
        ptype = Gtk.Label(label=part.type.upper())
        ptype.add_css_class("part-row-type")
        ptype.set_size_request(64, -1)
        ptype.set_xalign(0)
        row.add_prefix(ptype)

        # editable label (keys/labels)
        if part.type in ("key", "label", "readout"):
            entry = Gtk.Entry(text=(part.icon_layer().params.get("label", "")
                                    if part.icon_layer() else ""))
            entry.set_placeholder_text("label")
            entry.set_max_width_chars(8)
            entry.set_valign(Gtk.Align.CENTER)
            entry.connect("changed", lambda e, p=part: self._set_label(p, e.get_text()))
            row.add_suffix(entry)

        if part.type != "spacer":
            color_btn = Gtk.ColorDialogButton.new(Gtk.ColorDialog())
            color_btn.set_rgba(_list_to_rgba(part.fill))
            color_btn.set_valign(Gtk.Align.CENTER)
            color_btn.connect("notify::rgba",
                              lambda b, _p, part=part: self._set_color(part, b.get_rgba()))
            row.add_suffix(color_btn)

            mat = Gtk.DropDown.new_from_strings(list(MATERIALS))
            mat.set_selected(MATERIALS.index(part.material)
                             if part.material in MATERIALS else 0)
            mat.set_valign(Gtk.Align.CENTER)
            mat.connect("notify::selected",
                        lambda d, _p, part=part: self._set_material(part, d.get_selected()))
            row.add_suffix(mat)

        stretch = Gtk.ToggleButton(label="↔")
        stretch.set_tooltip_text("stretchy (fills remaining space)")
        stretch.set_active(part.width_mode == "stretchy")
        stretch.set_valign(Gtk.Align.CENTER)
        stretch.connect("toggled", lambda t, p=part: self._set_width(p, t.get_active()))
        row.add_suffix(stretch)

        up = Gtk.Button(icon_name="go-up-symbolic")
        up.set_valign(Gtk.Align.CENTER)
        up.connect("clicked", lambda _b, i=idx: self._move(i, -1))
        row.add_suffix(up)
        down = Gtk.Button(icon_name="go-down-symbolic")
        down.set_valign(Gtk.Align.CENTER)
        down.connect("clicked", lambda _b, i=idx: self._move(i, 1))
        row.add_suffix(down)
        rm = Gtk.Button(icon_name="user-trash-symbolic")
        rm.add_css_class("flat")
        rm.set_valign(Gtk.Align.CENTER)
        rm.connect("clicked", lambda _b, p=part: self._remove(p))
        row.add_suffix(rm)
        return row

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
            il.params["icon"] = None if text else il.params.get("icon")
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

    def _move(self, idx, delta):
        j = idx + delta
        parts = self.scene.parts
        if 0 <= j < len(parts):
            parts[idx], parts[j] = parts[j], parts[idx]
            self._rebuild_rows()
            self._schedule_apply()

    def _remove(self, part):
        if part in self.scene.parts:
            self.scene.parts.remove(part)
            self._rebuild_rows()
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
        self._rebuild_rows()
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
