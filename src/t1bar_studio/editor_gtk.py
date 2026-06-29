"""`t1bar edit` — a native GTK4/libadwaita editor for the config.

No web server: it reads/writes the config file directly and renders the bar
preview in-process (via render.py). A running `t1bar run` hot-reloads the file, so
edits appear on the physical bar live.

Layout follows the "Combined main window" design: a full-width OLED-pit bar
preview as the hero (with a weight ruler beneath), a left rail that answers
"which layout & why" (layout cards + a first-match-wins rules ladder), a center
inspector for the current selection, and a widget palette on the right.
"""
import io
import json
import os
import subprocess

import cairo  # noqa: F401  (registers the cairo.Context foreign-struct converter)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib, Gio  # noqa: E402

from PIL import ImageDraw  # noqa: E402

from . import config as cfgmod, render  # noqa: E402

BAR_W, BAR_H = 2170, 60
ACCENT = (90, 170, 250)
ICON_NAMES = ["", "play", "pause", "prev", "next", "brightness_up",
              "brightness_down", "volume_up", "volume_down", "volume_mute",
              "fullscreen", "cc"]
KEYS = ["KEY_ESC", "KEY_PLAYPAUSE", "KEY_NEXTSONG", "KEY_PREVIOUSSONG",
        "KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_BRIGHTNESSUP",
        "KEY_BRIGHTNESSDOWN", "KEY_KBDILLUMUP", "KEY_KBDILLUMDOWN"] + \
       [f"KEY_F{i}" for i in range(1, 13)]
# action categories shown to the user (friendly), mapped to config tuples
ACTION_CATS = ["(none)", "Key", "Media", "Seek", "Switch layout"]

CSS = b"""
@define-color win_bg #0B0D12;
@define-color raised #11131B;
@define-color card #181B24;
@define-color accent_c #5AAAFA;
* { font-family: "Inter", "Adwaita Sans", sans-serif; }
window { background:@win_bg; }
headerbar { background:@win_bg; box-shadow:none; border:none; min-height:48px; }
headerbar:backdrop { background:@win_bg; }
.app-title { font-weight:600; font-size:14px; letter-spacing:.2px; color:#EEF0F6; }
.mono { font-family:"JetBrains Mono","Adwaita Mono",monospace; }
.dim { color:#9AA0AD; }
.caption { font-size:11px; color:#5A606E; letter-spacing:.3px; }
.caption-live { font-size:11px; color:#34C759; letter-spacing:.3px; }
.caption-off  { font-size:11px; color:#6A7080; letter-spacing:.3px; }
.section-title { font-size:9px; font-weight:700; letter-spacing:1px; color:#565C6B; }

/* the OLED pit - the bar looks embedded in dark aluminium */
.bar-pit { background:#050609; border-radius:14px; padding:16px 18px;
  box-shadow: inset 0 2px 14px rgba(0,0,0,0.9), inset 0 0 0 1px rgba(255,255,255,0.05); }

.rail-left  { background:@raised; border-right:1px solid rgba(255,255,255,0.05); }
.rail-right { background:@raised; border-left:1px solid rgba(255,255,255,0.05); }

/* layout cards */
.lcard { padding:9px 10px; border-radius:10px; background:@card;
  border:1px solid rgba(255,255,255,0.05); }
.lcard:hover { border-color:rgba(90,170,250,0.30); }
.lcard-active { background:rgba(90,170,250,0.10); border:1px solid rgba(90,170,250,0.55); }
.lcard-name { font-size:13px; font-weight:600; color:#E8EAF0; }
.badge-live { font-size:8px; color:#5AAAFA; letter-spacing:.4px; }
.mini-pit { background:#050609; border-radius:6px; padding:3px 4px;
  box-shadow: inset 0 1px 4px rgba(0,0,0,0.8); }
.dashed { border:1px dashed rgba(255,255,255,0.18); border-radius:10px;
  background:transparent; color:#7A808E; font-size:12px; padding:8px; }
.dashed:hover { border-color:rgba(90,170,250,0.5); color:#AEB4C2; }

/* rules ladder */
.rule-row { padding:5px 7px; border-radius:8px; background:@card;
  border:1px solid rgba(255,255,255,0.05); }
.rule-row:hover { border-color:rgba(90,170,250,0.30); }
.rule-now { background:rgba(90,170,250,0.10); border:1px solid rgba(90,170,250,0.55); }
.rule-grip { color:#4A4F5C; }
.now-tag { font-size:8px; color:#5AAAFA; letter-spacing:.4px; }

/* segmented control */
.seg { background:#0A0C12; border-radius:9px; padding:3px; }
.seg button { border-radius:7px; padding:4px 13px; background:transparent; color:#8A90A0;
  box-shadow:none; border:none; min-height:0; font-weight:500; }
.seg button:checked { background:#262A36; color:#F2F3F7;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.07); }

/* palette */
.palette-item { padding:10px 12px; border-radius:10px; background:@card;
  border:1px solid rgba(255,255,255,0.05); }
.palette-item:hover { background:#1F222C; border-color:rgba(90,170,250,0.30); }
.palette-dashed { border-style:dashed; color:#7A808E; }

/* live indicator pill */
.live-pill { border-radius:999px; padding:3px 11px; background:#14161F; color:#8A90A0;
  border:1px solid rgba(255,255,255,0.06); font-weight:500; font-size:12px; }
.live-on  { color:#E8F6EC; border-color:rgba(52,199,89,0.55); }
.live-off { color:#8A90A0; }

/* inspector */
.field-label { font-size:10px; color:#7A808E; letter-spacing:.2px; }
.field-note  { font-size:10px; color:#5AAAFA; }
.linklike { color:#8A90A0; text-decoration:underline; font-size:10px; padding:0; min-height:0;
  background:transparent; border:none; box-shadow:none; }
.linklike:hover { color:#5AAAFA; }
.insp-title { font-size:15px; font-weight:600; color:#EEF0F6; }
.insp-sub { font-size:11px; color:#7A808E; }
.swatch { min-width:26px; min-height:24px; border-radius:6px; padding:0;
  border:1px solid rgba(255,255,255,0.14); box-shadow:none; }
.swatch-sel { border:2px solid @accent_c; }
.value-chip { background:#0A0C12; border-radius:7px; padding:3px 9px; color:#C8CCD6;
  font-size:12px; border:1px solid rgba(255,255,255,0.06); }
.danger { color:#FF6B6B; }
.hint { color:#565C6B; font-size:11px; }
.empty-big { color:#3E4456; font-size:13px; }
"""


def rgb_to_rgba(rgb):
    r, g, b = (rgb or [0, 0, 0])[:3]
    c = Gdk.RGBA(); c.red = r / 255; c.green = g / 255; c.blue = b / 255; c.alpha = 1
    return c


def rgba_to_rgb(c):
    return [round(c.red * 255), round(c.green * 255), round(c.blue * 255)]


def _round_rect(cr, x, y, w, h, r):
    import math
    r = min(r, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h); return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Window(Adw.ApplicationWindow):
    def __init__(self, app, path):
        super().__init__(application=app, title="t1bar studio")
        self.set_default_size(1360, 820)
        self.path = path
        self.cfg = cfgmod.load(path)
        self.layout = next(iter(self.cfg["layouts"]), None)
        self.sel = None
        self.sel_rule = None
        self.mode = "Item"
        self.ruler = None
        self._save_pending = False
        self.preview_playing = False
        self.live_ok = False

        self.toasts = Adw.ToastOverlay()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toasts.set_child(root)
        self.set_content(self.toasts)

        root.append(self._header())
        root.append(self._hero())

        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        cols.append(self._rail_left())
        cols.append(self._inspector())
        cols.append(self._palette())
        root.append(cols)

        self.refresh()
        self.rebuild_left()
        self.rebuild_inspector()
        self._update_live()
        GLib.timeout_add_seconds(3, self._update_live)

    # -- header ----------------------------------------------------------------
    def _header(self):
        hb = Adw.HeaderBar()
        hb.add_css_class("flat")
        title = Gtk.Label(label="t1bar studio"); title.add_css_class("app-title")
        hb.set_title_widget(title)
        self.live = Gtk.Label(label="○  live on bar")
        self.live.add_css_class("live-pill")
        self.live.set_tooltip_text("Whether the t1bar service is driving the hardware right now")
        hb.pack_end(self.live)
        self.play_toggle = Gtk.ToggleButton(label="▶  preview playing")
        self.play_toggle.add_css_class("live-pill")
        self.play_toggle.set_tooltip_text("Simulate the media-playing state in the preview only")
        self.play_toggle.connect("toggled", self._on_preview_playing)
        hb.pack_end(self.play_toggle)
        return hb

    def _on_preview_playing(self, btn):
        self.preview_playing = btn.get_active()
        self.refresh(); self.rebuild_left()

    # -- hero (full-width preview + ruler) -------------------------------------
    def _hero(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(10); box.set_margin_bottom(8)
        box.set_margin_start(20); box.set_margin_end(20)

        cap = Gtk.Box()
        self.cap_left = Gtk.Label(xalign=0); self.cap_left.add_css_class("caption")
        self.cap_left.add_css_class("mono"); self.cap_left.set_hexpand(True)
        self.cap_left.set_halign(Gtk.Align.START)
        self.cap_right = Gtk.Label(xalign=1); self.cap_right.add_css_class("caption-off")
        self.cap_right.add_css_class("mono")
        cap.append(self.cap_left); cap.append(self.cap_right)
        cap.set_margin_bottom(6)
        box.append(cap)

        pit = Gtk.Box(); pit.add_css_class("bar-pit")
        self.pic = Gtk.Picture()
        self.pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.pic.set_can_shrink(True)
        self.pic.set_size_request(-1, 66)
        click = Gtk.GestureClick(); click.connect("pressed", self._on_canvas_click)
        self.pic.add_controller(click)
        pit.append(self.pic)
        box.append(pit)

        rb = Gtk.Box(); rb.set_margin_top(7); rb.set_margin_start(2); rb.set_margin_end(2)
        self.ruler = Gtk.DrawingArea()
        self.ruler.set_content_height(24); self.ruler.set_hexpand(True)
        self.ruler.set_draw_func(self._draw_ruler)
        rb.append(self.ruler)
        box.append(rb)
        return box

    def _draw_ruler(self, area, cr, w, h):
        items = self.items()
        if not items:
            return
        total = sum(max(0.01, it.get("weight", 1.0)) for it in items) or 1
        gap = 5
        avail = w - gap * (len(items) - 1)
        x = 0.0
        for i, it in enumerate(items):
            seg = avail * max(0.01, it.get("weight", 1.0)) / total
            sel = (i == self.sel)
            cr.set_source_rgba(90/255, 170/255, 250/255, 0.85 if sel else 0.28)
            cr.rectangle(x, 0, seg, 2); cr.fill()
            label = f"{it.get('weight', 1.0):g}"
            cr.set_source_rgba(0.61, 0.74, 0.88, 1) if sel else cr.set_source_rgba(0.46, 0.5, 0.58, 1)
            cr.select_font_face("Inter"); cr.set_font_size(9.5)
            ext = cr.text_extents(label)
            if ext.width < seg - 4:
                cr.move_to(x + seg / 2 - ext.width / 2, 14)
                cr.show_text(label)
            x += seg + gap

    # -- left rail: layouts + rules --------------------------------------------
    def _rail_left(self):
        col = Gtk.ScrolledWindow()
        col.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        col.add_css_class("rail-left"); col.set_size_request(252, -1)
        self.rail_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.rail_body.set_margin_top(14); self.rail_body.set_margin_start(13)
        self.rail_body.set_margin_end(13); self.rail_body.set_margin_bottom(14)
        col.set_child(self.rail_body)
        return col

    def rebuild_left(self):
        body = self.rail_body
        while (c := body.get_first_child()):
            body.remove(c)

        body.append(self._label("LAYOUTS"))
        for name in self.cfg["layouts"]:
            body.append(self._layout_card(name))
        add = Gtk.Button(label="+  new layout"); add.add_css_class("dashed")
        add.connect("clicked", self._on_add_layout)
        body.append(add)

        sp = Gtk.Box(); sp.set_size_request(-1, 8); body.append(sp)
        body.append(self._label("RULES · first match wins"))
        now = self._matching_rule()
        rules = self.cfg.get("rules", [])
        for i, rule in enumerate(rules):
            body.append(self._rule_row(i, rule, i == now))
        addr = Gtk.Button(label="+  add rule"); addr.add_css_class("dashed")
        addr.connect("clicked", self._on_add_rule)
        body.append(addr)

    def _label(self, text):
        l = Gtk.Label(label=text, xalign=0)
        l.add_css_class("section-title"); l.add_css_class("mono")
        return l

    def _layout_card(self, name):
        active = (name == self.layout)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("lcard-active" if active else "lcard")
        head = Gtk.Box()
        nm = Gtk.Label(label=name, xalign=0); nm.add_css_class("lcard-name")
        nm.set_hexpand(True); nm.set_halign(Gtk.Align.START)
        head.append(nm)
        live_layout = self._matching_layout()
        tags = []
        if name == live_layout:
            tags.append("● live")
        if active:
            tags.append("editing")
        if tags:
            b = Gtk.Label(label=" · ".join(tags)); b.add_css_class("badge-live")
            b.add_css_class("mono"); head.append(b)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic")
        menu.add_css_class("flat"); menu.set_valign(Gtk.Align.CENTER)
        menu.set_popover(self._layout_menu(name))
        head.append(menu)
        card.append(head)

        mini = Gtk.Box(); mini.add_css_class("mini-pit")
        pic = Gtk.Picture(); pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_can_shrink(True); pic.set_size_request(-1, 22)
        pic.set_paintable(self._mini_texture(name))
        mini.append(pic); card.append(mini)

        clk = Gtk.GestureClick()
        clk.connect("pressed", lambda *_: self._select_layout(name))
        card.add_controller(clk)
        return card

    def _layout_menu(self, name):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4); box.set_margin_bottom(4)
        box.set_margin_start(4); box.set_margin_end(4)
        for lbl, fn in (("Rename", self._rename_layout),
                        ("Duplicate", self._dup_layout),
                        ("Delete", self._del_layout)):
            b = Gtk.Button(label=lbl); b.add_css_class("flat")
            b.set_halign(Gtk.Align.FILL); b.get_child().set_xalign(0)
            if lbl == "Delete":
                b.add_css_class("danger")
            b.connect("clicked", lambda _b, f=fn, n=name: (pop.popdown(), f(n)))
            box.append(b)
        pop.set_child(box)
        return pop

    def _mini_texture(self, name):
        state = {"width": 620, "height": 50, "pressed": None,
                 "media": self._media_state()}
        try:
            im = render.render(self.cfg, name, state).convert("RGB")
        except Exception:
            im = None
        if im is None:
            return None
        buf = io.BytesIO(); im.save(buf, "PNG")
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.getvalue()))

    def _rule_row(self, i, rule, is_now):
        row = Gtk.Box(spacing=4)
        row.add_css_class("rule-now" if is_now else "rule-row")
        grip = Gtk.Label(label="⋮"); grip.add_css_class("rule-grip"); row.append(grip)
        when = rule.get("when")
        if when:
            k, v = next(iter(when.items()))
            txt = f"when {k} {v} → "
        else:
            txt = "otherwise → "
        lab = Gtk.Label(xalign=0)
        lab.set_markup(f'<span size="small">{GLib.markup_escape_text(txt)}</span>'
                       f'<b><span size="small">{GLib.markup_escape_text(str(rule.get("show","")))}</span></b>')
        lab.set_hexpand(True); lab.set_halign(Gtk.Align.START)
        lab.set_ellipsize(3)  # Pango.EllipsizeMode.END — keep the "now" tag visible
        row.append(lab)
        if is_now:
            tag = Gtk.Label(label="now"); tag.add_css_class("now-tag"); tag.add_css_class("mono")
            tag.set_margin_end(2)
            row.append(tag)
        clk = Gtk.GestureClick()
        clk.connect("pressed", lambda *_a, idx=i: self._edit_rule(idx))
        row.add_controller(clk)
        return row

    # -- center inspector ------------------------------------------------------
    def _inspector(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col.set_hexpand(True)
        col.set_margin_top(14); col.set_margin_start(18)
        col.set_margin_end(18); col.set_margin_bottom(14)

        head = Gtk.Box()
        tbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.insp_title = Gtk.Label(xalign=0); self.insp_title.add_css_class("insp-title")
        self.insp_title.set_halign(Gtk.Align.START)
        tbox.append(self.insp_title)
        head.append(tbox)
        spacer = Gtk.Box(hexpand=True); head.append(spacer)
        seg = Gtk.Box(); seg.add_css_class("seg"); seg.set_valign(Gtk.Align.CENTER)
        first = None
        self.mode_btns = {}
        for m in ("Item", "Theme", "Rules"):
            b = Gtk.ToggleButton(label=m); b.set_active(m == self.mode)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._on_mode, m)
            self.mode_btns[m] = b
            seg.append(b)
        head.append(seg)
        col.append(head)

        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.inspector_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        sc.set_child(self.inspector_body)
        col.append(sc)
        return col

    # -- right palette ---------------------------------------------------------
    def _palette(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.add_css_class("rail-right"); col.set_size_request(178, -1)
        col.set_margin_top(14); col.set_margin_start(12)
        col.set_margin_end(12); col.set_margin_bottom(14)
        col.append(self._label("WIDGETS"))
        for kind, glyph, dashed in (("button", "▭  Button", False),
                                    ("scrubber", "═  Scrubber", False),
                                    ("label", "T  Label", False),
                                    ("spacer", "⇿  Spacer", True)):
            b = Gtk.Button(label=glyph); b.add_css_class("palette-item")
            b.get_child().set_xalign(0)
            if dashed:
                b.add_css_class("palette-dashed")
            b.connect("clicked", self._on_add_item, kind)
            col.append(b)
        hint = Gtk.Label(label="click to add to the\ncurrent layout", xalign=0, wrap=True)
        hint.add_css_class("hint"); hint.set_margin_top(8)
        col.append(hint)
        return col

    # -- model helpers ---------------------------------------------------------
    def items(self):
        return self.cfg["layouts"][self.layout]["items"]

    def selected(self):
        if self.sel is None or self.sel >= len(self.items()):
            return None
        return self.items()[self.sel]

    def _media_state(self):
        playing = self.preview_playing
        return {"status": "Playing" if playing else "Stopped",
                "position": 73, "length": 210, "title": "Demo Track", "artist": "Artist"}

    def _matching_rule(self):
        for i, r in enumerate(self.cfg.get("rules", [])):
            w = r.get("when")
            if not w:
                return i
            if w.get("media") == "playing" and self.preview_playing:
                return i
        return None

    def _matching_layout(self):
        i = self._matching_rule()
        rules = self.cfg.get("rules", [])
        if i is not None and i < len(rules):
            return rules[i].get("show")
        return self.layout

    def refresh(self):
        """Re-render the bar (+ selection highlight) and schedule a save."""
        state = {"width": BAR_W, "height": BAR_H, "pressed": None, "media": self._media_state()}
        try:
            im = render.render(self.cfg, self.layout, state).convert("RGB")
        except Exception as e:
            self.toasts.add_toast(Adw.Toast(title=f"render error: {e}"))
            return
        if self.sel is not None:
            bxs = render.boxes(self.cfg, self.layout, BAR_W, BAR_H)
            if self.sel < len(bxs):
                box = bxs[self.sel][1]
                d = ImageDraw.Draw(im)
                d.rounded_rectangle([box[0] + 1, 1, box[2] - 1, BAR_H - 2],
                                    radius=10, outline=ACCENT, width=3)
        buf = io.BytesIO(); im.save(buf, "PNG")
        self.pic.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.getvalue())))
        if self.ruler:
            self.ruler.queue_draw()
        if hasattr(self, "cap_left"):
            self.cap_left.set_text(f"YOUR TOUCH BAR · 2170×60 · editing “{self.layout}”")
        self._schedule_save()

    def _schedule_save(self):
        if self._save_pending:
            return
        self._save_pending = True
        GLib.timeout_add(80, self._do_save)

    def _do_save(self):
        self._save_pending = False
        try:
            with open(self.path, "w") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception as e:
            self.toasts.add_toast(Adw.Toast(title=f"save failed: {e}"))
        return False

    def _update_live(self):
        try:
            r = subprocess.run(["systemctl", "is-active", "t1bar.service"],
                               capture_output=True, text=True, timeout=2)
            ok = r.stdout.strip() == "active"
        except Exception:
            ok = False
        self.live_ok = ok
        if hasattr(self, "live"):
            self.live.set_text(("●  live on bar") if ok else ("○  preview only"))
            self.live.remove_css_class("live-on"); self.live.remove_css_class("live-off")
            self.live.add_css_class("live-on" if ok else "live-off")
        if hasattr(self, "cap_right"):
            self.cap_right.set_text("● applied to hardware" if ok else "○ preview only — service stopped")
            self.cap_right.remove_css_class("caption-live"); self.cap_right.remove_css_class("caption-off")
            self.cap_right.add_css_class("caption-live" if ok else "caption-off")
        return True

    # -- events ----------------------------------------------------------------
    def _on_canvas_click(self, gesture, n, x, y):
        w = self.pic.get_width()
        if w <= 0:
            return
        nx = x / w * BAR_W
        self.sel = None
        for i, (item, box) in enumerate(render.boxes(self.cfg, self.layout, BAR_W, BAR_H)):
            if item.get("type") == "spacer":
                continue
            if box[0] <= nx <= box[2]:
                self.sel = i
                break
        self._set_mode("Item")
        self.refresh(); self.rebuild_inspector()

    def _on_mode(self, btn, m):
        if btn.get_active():
            self.mode = m; self.rebuild_inspector()

    def _set_mode(self, m):
        self.mode = m
        if hasattr(self, "mode_btns"):
            self.mode_btns[m].set_active(True)

    def _select_layout(self, name):
        self.layout = name; self.sel = None
        self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _on_add_layout(self, _btn):
        n = 1
        while f"layout{n}" in self.cfg["layouts"]:
            n += 1
        self.cfg["layouts"][f"layout{n}"] = {"items": []}
        self._select_layout(f"layout{n}")

    def _rename_layout(self, name):
        dlg = Adw.MessageDialog(transient_for=self, heading="Rename layout",
                                body=f"New name for “{name}”")
        entry = Gtk.Entry(text=name); dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel"); dlg.add_response("ok", "Rename")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def done(_d, resp):
            new = entry.get_text().strip()
            if resp == "ok" and new and new not in self.cfg["layouts"]:
                lays = {(new if k == name else k): v for k, v in self.cfg["layouts"].items()}
                self.cfg["layouts"] = lays
                for r in self.cfg.get("rules", []):
                    if r.get("show") == name:
                        r["show"] = new
                if self.layout == name:
                    self.layout = new
                self.refresh(); self.rebuild_left(); self.rebuild_inspector()
        dlg.connect("response", done); dlg.present()

    def _dup_layout(self, name):
        base = name + "_copy"; n = base; i = 2
        while n in self.cfg["layouts"]:
            n = f"{base}{i}"; i += 1
        self.cfg["layouts"][n] = json.loads(json.dumps(self.cfg["layouts"][name]))
        self._select_layout(n)

    def _del_layout(self, name):
        if len(self.cfg["layouts"]) <= 1:
            self.toasts.add_toast(Adw.Toast(title="Keep at least one layout"))
            return
        self.cfg["layouts"].pop(name, None)
        if self.layout == name:
            self.layout = next(iter(self.cfg["layouts"]))
        self.sel = None
        self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _on_add_item(self, _btn, kind):
        defaults = {
            "button": {"type": "button", "id": "new", "label": "new", "action": ["key", "KEY_ESC"]},
            "scrubber": {"type": "scrubber", "id": "seek", "weight": 4,
                         "source": "media_position", "action": ["seek"]},
            "label": {"type": "label", "id": "label", "label": "text", "weight": 2},
            "spacer": {"type": "spacer", "weight": 0.5},
        }
        self.items().append(dict(defaults[kind]))
        self.sel = len(self.items()) - 1
        self._set_mode("Item")
        self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _delete_item(self):
        if self.sel is not None and self.sel < len(self.items()):
            self.items().pop(self.sel)
            self.sel = None
            self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    # rule events
    def _on_add_rule(self, _btn):
        rules = self.cfg.setdefault("rules", [])
        target = next(iter(self.cfg["layouts"]))
        new = {"when": {"media": "playing"}, "show": target}
        # insert before a trailing catch-all (rule with no "when"), else append
        if rules and "when" not in rules[-1]:
            rules.insert(len(rules) - 1, new)
            self.sel_rule = len(rules) - 2
        else:
            rules.append(new)
            self.sel_rule = len(rules) - 1
        self._set_mode("Rules"); self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _edit_rule(self, i):
        self.sel_rule = i
        self._set_mode("Rules"); self.rebuild_inspector()

    # -- inspector bodies ------------------------------------------------------
    def rebuild_inspector(self):
        body = self.inspector_body
        while (c := body.get_first_child()):
            body.remove(c)
        if self.mode == "Item":
            it = self.selected()
            self.insp_title.set_markup(
                f'{GLib.markup_escape_text(it.get("id") or it.get("type","item"))}'
                f'  <span size="small" foreground="#7A808E">· {it.get("type","")}</span>'
                if it else 'Inspector')
            self._inspect_item(body)
        elif self.mode == "Theme":
            self.insp_title.set_text("Theme")
            self._inspect_theme(body)
        else:
            self.insp_title.set_text("Rules")
            self._inspect_rules(body)

    # field helpers
    def _field(self, parent, label_text, control, note=None, note_action=None):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lab_row = Gtk.Box(spacing=6)
        l = Gtk.Label(label=label_text, xalign=0); l.add_css_class("field-label"); l.add_css_class("mono")
        lab_row.append(l)
        if note:
            n = Gtk.Label(label=note); n.add_css_class("field-note"); n.add_css_class("mono")
            lab_row.append(n)
        if note_action:
            btn = Gtk.Button(label="reset"); btn.add_css_class("linklike")
            btn.connect("clicked", lambda *_: note_action())
            lab_row.append(btn)
        b.append(lab_row)
        b.append(control)
        parent.append(b)
        return b

    def _set(self, obj, key, val):
        obj[key] = val; self.refresh(); self.rebuild_left()

    def _set_text(self, obj, key, val):
        if val == "":
            obj.pop(key, None)
        else:
            obj[key] = val
        self.refresh(); self.rebuild_left()

    def _set_opt(self, obj, key, val):
        if val in ("", None):
            obj.pop(key, None)
        else:
            obj[key] = val
        self.refresh(); self.rebuild_left()

    def _entry(self, obj, key, ph=""):
        e = Gtk.Entry(); e.set_text(str(obj.get(key, ""))); e.set_placeholder_text(ph)
        e.connect("changed", lambda w: self._set_text(obj, key, w.get_text()))
        return e

    def _dropdown(self, options, current, cb, labels=None):
        model = Gtk.StringList()
        for o in (labels or options):
            model.append(o if o != "" else "(none)")
        dd = Gtk.DropDown(model=model)
        if current in options:
            dd.set_selected(options.index(current))
        dd.connect("notify::selected", lambda d, _p: cb(options[d.get_selected()]))
        return dd

    def _weight_slider(self, it):
        box = Gtk.Box(spacing=10)
        adj = Gtk.Adjustment(value=float(it.get("weight", 1.0)), lower=0.1, upper=8, step_increment=0.1)
        sc = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        sc.set_draw_value(False); sc.set_hexpand(True)
        chip = Gtk.Label(label=f"{it.get('weight',1.0):g}"); chip.add_css_class("value-chip")
        chip.add_css_class("mono")

        def changed(s):
            v = round(s.get_value(), 2)
            it["weight"] = v; chip.set_text(f"{v:g}")
            self.refresh(); self.rebuild_left()
        sc.connect("value-changed", changed)
        box.append(sc); box.append(chip)
        return box

    def _swatches(self, it, key, theme_default):
        row = Gtk.Box(spacing=7)
        cur = it.get(key)
        th = self.cfg["theme"]
        palette = [th["button"]["fill"], th["accent"], th["pressed"]["fill"], th["background"],
                   [60, 40, 48], [34, 54, 44], [42, 46, 62]]
        seen = []
        for c in palette:
            if c and c not in seen:
                seen.append(c)
        for c in seen[:6]:
            b = Gtk.Button(); b.add_css_class("swatch")
            if cur == c:
                b.add_css_class("swatch-sel")
            self._tint(b, c)
            b.connect("clicked", lambda _b, col=c: self._set(it, key, list(col)))
            row.append(b)
        pick = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        pick.set_valign(Gtk.Align.CENTER)
        pick.set_rgba(rgb_to_rgba(cur if cur else theme_default))
        pick.connect("notify::rgba", lambda b, _p: self._set(it, key, rgba_to_rgb(b.get_rgba())))
        row.append(pick)
        return row

    def _tint(self, widget, rgb):
        prov = Gtk.CssProvider()
        prov.load_from_data(f"button {{ background:rgb({rgb[0]},{rgb[1]},{rgb[2]}); }}".encode())
        widget.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _inspect_item(self, body):
        it = self.selected()
        if not it:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_margin_top(60); box.set_valign(Gtk.Align.CENTER)
            l1 = Gtk.Label(label="Nothing selected"); l1.add_css_class("empty-big")
            l2 = Gtk.Label(label="Click a widget on the bar above, or add one from the right.")
            l2.add_css_class("hint")
            box.append(l1); box.append(l2); body.append(box)
            return
        t = it.get("type", "button")

        if t in ("button", "label"):
            grid = Gtk.Box(spacing=18)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); left.set_hexpand(True)
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); right.set_hexpand(True)
            self._field(left, "label", self._entry(it, "label"))
            if t == "button":
                self._field(right, "icon",
                            self._dropdown(ICON_NAMES, it.get("icon", ""),
                                           lambda v: self._set_opt(it, "icon", v)))
            else:
                self._field(right, "bind text",
                            self._dropdown(["", "media_title", "media_artist"], it.get("source", ""),
                                           lambda v: self._set_opt(it, "source", v)))
            grid.append(left); grid.append(right)
            body.append(grid)

        self._field(body, "weight — drag on bar coming soon, or here", self._weight_slider(it))

        if t == "button":
            overriding = "fill" in it
            self._field(body, "fill", self._swatches(it, "fill", self.cfg["theme"]["button"]["fill"]),
                        note=("· overriding theme" if overriding else None),
                        note_action=(lambda: (it.pop("fill", None), self.refresh(),
                                              self.rebuild_left(), self.rebuild_inspector()))
                        if overriding else None)
            tover = "color" in it
            self._field(body, "text color", self._swatches(it, "color", self.cfg["theme"]["button"]["text"]),
                        note=("· overriding theme" if tover else None),
                        note_action=(lambda: (it.pop("color", None), self.refresh(),
                                              self.rebuild_left(), self.rebuild_inspector()))
                        if tover else None)
            self._field(body, "follow playback",
                        self._dropdown(["", "play_pause"], it.get("dynamic", ""),
                                       lambda v: self._set_opt(it, "dynamic", v)))
            self._action_field(body, it)
        elif t == "scrubber":
            self._field(body, "bind", self._dropdown(["", "media_position"], it.get("source", ""),
                        lambda v: self._set_opt(it, "source", v)))

        dl = Gtk.Button(label="Delete widget"); dl.add_css_class("danger"); dl.add_css_class("flat")
        dl.set_halign(Gtk.Align.START); dl.set_margin_top(8)
        dl.connect("clicked", lambda *_: self._delete_item())
        body.append(dl)

    def _action_field(self, body, it):
        action = it.get("action") or []
        kind = action[0] if action else None
        cat = {None: "(none)", "key": "Key", "media": "Media",
               "seek": "Seek", "layout": "Switch layout"}.get(kind, "(none)")
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        def set_cat(v):
            if v == "(none)":
                it.pop("action", None)
            elif v == "Key":
                it["action"] = ["key", "KEY_ESC"]
            elif v == "Media":
                it["action"] = ["media", "play-pause"]
            elif v == "Seek":
                it["action"] = ["seek"]
            elif v == "Switch layout":
                it["action"] = ["layout", next(iter(self.cfg["layouts"]))]
            self.refresh(); self.rebuild_inspector()

        wrap.append(self._dropdown(ACTION_CATS, cat, set_cat))
        if kind == "key":
            wrap.append(self._dropdown(KEYS, action[1] if len(action) > 1 else KEYS[0],
                        lambda v: self._set(it, "action", ["key", v])))
        elif kind == "media":
            verbs = ["play-pause", "play", "pause", "next", "previous", "stop"]
            wrap.append(self._dropdown(verbs, action[1] if len(action) > 1 else verbs[0],
                        lambda v: self._set(it, "action", ["media", v])))
        elif kind == "layout":
            lays = list(self.cfg["layouts"])
            wrap.append(self._dropdown(lays, action[1] if len(action) > 1 else lays[0],
                        lambda v: self._set(it, "action", ["layout", v])))
        self._field(body, "action", wrap)

    def _inspect_theme(self, body):
        th = self.cfg["theme"]
        g = Adw.PreferencesGroup(title="Surface"); body.append(g)
        self._color_row(g, "background", th, "background", [8, 10, 18])
        self._color_row(g, "accent", th, "accent", [90, 170, 250])
        bg = Adw.PreferencesGroup(title="Buttons"); body.append(bg)
        self._color_row(bg, "fill", th["button"], "fill", [38, 42, 58])
        self._color_row(bg, "text", th["button"], "text", [232, 234, 240])
        self._spin_row(bg, "radius", th["button"], "radius", 0, 24, 1, 12)
        self._spin_row(bg, "font size", th["button"], "font_size", 14, 34, 1, 26)
        pg = Adw.PreferencesGroup(title="Pressed"); body.append(pg)
        self._color_row(pg, "fill", th["pressed"], "fill", [70, 110, 210])
        sg = Adw.PreferencesGroup(title="Scrubber and spacing"); body.append(sg)
        self._color_row(sg, "track", th, "track", [55, 60, 78])
        self._spin_row(sg, "gap", th, "gap", 0, 24, 1, 10)
        self._spin_row(sg, "margin", th, "margin", 0, 24, 1, 10)

    def _color_row(self, group, title, obj, key, fallback):
        row = Adw.ActionRow(title=title)
        btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog()); btn.set_valign(Gtk.Align.CENTER)
        btn.set_rgba(rgb_to_rgba(obj.get(key, fallback)))
        btn.connect("notify::rgba", lambda b, _p: self._set(obj, key, rgba_to_rgb(b.get_rgba())))
        row.add_suffix(btn); group.add(row)

    def _spin_row(self, group, title, obj, key, lo, hi, step, default):
        row = Adw.SpinRow.new_with_range(lo, hi, step); row.set_title(title)
        row.set_value(float(obj.get(key, default)))
        row.connect("changed", lambda r: self._set(obj, key, round(r.get_value(), 2)))
        group.add(row)

    def _inspect_rules(self, body):
        intro = Gtk.Label(label="Evaluated top to bottom — the first matching rule wins.",
                          xalign=0, wrap=True)
        intro.add_css_class("hint"); body.append(intro)
        rules = self.cfg.setdefault("rules", [])
        now = self._matching_rule()
        lays = list(self.cfg["layouts"])
        conds = ["(always)", "media playing"]
        for i, rule in enumerate(rules):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.add_css_class("lcard")
            if i == now:
                card.add_css_class("lcard-active")
            top = Gtk.Box(spacing=8)
            num = Gtk.Label(label=f"{i+1}"); num.add_css_class("hint"); num.add_css_class("mono")
            top.append(num)
            if i == now:
                tg = Gtk.Label(label="◀ now"); tg.add_css_class("now-tag"); tg.add_css_class("mono")
                top.append(tg)
            top.append(Gtk.Box(hexpand=True))
            up = Gtk.Button(icon_name="go-up-symbolic"); up.add_css_class("flat")
            dn = Gtk.Button(icon_name="go-down-symbolic"); dn.add_css_class("flat")
            rm = Gtk.Button(icon_name="user-trash-symbolic"); rm.add_css_class("flat"); rm.add_css_class("danger")
            up.set_sensitive(i > 0); dn.set_sensitive(i < len(rules) - 1)
            up.connect("clicked", lambda _b, idx=i: self._move_rule(idx, -1))
            dn.connect("clicked", lambda _b, idx=i: self._move_rule(idx, 1))
            rm.connect("clicked", lambda _b, idx=i: self._del_rule(idx))
            for b in (up, dn, rm):
                top.append(b)
            card.append(top)

            r2 = Gtk.Box(spacing=8)
            cur_cond = "media playing" if rule.get("when") else "(always)"
            cond_dd = self._dropdown(conds, cur_cond,
                                     lambda v, idx=i: self._set_rule_cond(idx, v))
            cond_dd.set_hexpand(True)
            arrow = Gtk.Label(label="→")
            show_dd = self._dropdown(lays, rule.get("show", lays[0]),
                                     lambda v, idx=i: self._set_rule_show(idx, v))
            show_dd.set_hexpand(True)
            r2.append(cond_dd); r2.append(arrow); r2.append(show_dd)
            card.append(r2)
            body.append(card)
        add = Gtk.Button(label="+  add rule"); add.add_css_class("dashed")
        add.connect("clicked", self._on_add_rule)
        body.append(add)

    def _set_rule_cond(self, i, v):
        rules = self.cfg["rules"]
        if v == "(always)":
            rules[i].pop("when", None)
        else:
            rules[i]["when"] = {"media": "playing"}
        self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _set_rule_show(self, i, v):
        self.cfg["rules"][i]["show"] = v
        self.refresh(); self.rebuild_left()

    def _move_rule(self, i, d):
        rules = self.cfg["rules"]; j = i + d
        if 0 <= j < len(rules):
            rules[i], rules[j] = rules[j], rules[i]
            self.refresh(); self.rebuild_left(); self.rebuild_inspector()

    def _del_rule(self, i):
        rules = self.cfg["rules"]
        if 0 <= i < len(rules):
            rules.pop(i)
            self.refresh(); self.rebuild_left(); self.rebuild_inspector()


class App(Adw.Application):
    def __init__(self, path, shot=None):
        super().__init__(application_id="za.co.cloudnexus.t1bar",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path
        self.shot = shot
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def do_activate(self):
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        win = Window(self, self.path)
        win.present()
        if self.shot:
            mode = os.environ.get("T1BAR_SHOT_MODE", "Item")
            want_layout = os.environ.get("T1BAR_SHOT_LAYOUT")
            if want_layout and want_layout in win.cfg["layouts"]:
                win.layout = want_layout
            if os.environ.get("T1BAR_SHOT_PLAYING") and hasattr(win, "play_toggle"):
                win.preview_playing = True; win.play_toggle.set_active(True)
            for i, it in enumerate(win.items()):
                if it.get("type", "button") == "button":
                    win.sel = i; break
            win._set_mode(mode)
            if mode != "Item":
                win.sel = None
            win.refresh(); win.rebuild_left(); win.rebuild_inspector()
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
                print(f"[t1bar] saved shot {self.shot}", flush=True)
        except Exception as e:
            print(f"[t1bar] shot failed: {e}", flush=True)
        self.quit()
        return False


def run(path, shot=None):
    App(path, shot).run([])
