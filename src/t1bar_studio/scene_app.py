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
.scene-card.active { border: 1px solid #46c479; background: #14181550; }
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
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        card.add_css_class("scene-card")
        if is_active:
            card.add_css_class("active")

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
        card.append(top)

        strip_box = Gtk.Box()
        strip_box.add_css_class("mini-strip")
        tex = scene_texture(self.cfg, scene, live, self.CARD_STRIP_W, self.CARD_STRIP_H)
        strip_box.append(_picture(tex, self.CARD_STRIP_W, self.CARD_STRIP_H))
        card.append(strip_box)

        trig = Gtk.Label(label=scene.trigger.describe(), xalign=0)
        trig.add_css_class("scene-trigger")
        card.append(trig)
        return card

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
