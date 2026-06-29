"""`t1bar edit` — a native GTK4/libadwaita editor for the config.

No web server: it reads/writes the config file directly and renders the bar
preview in-process (via render.py). A running `t1bar run` hot-reloads the file, so
edits appear on the physical bar live. Designed to the t1bar-studio spec: an
"OLED-pit" bar canvas as the hero, a quiet instrument panel around it, Apple-like
restraint.
"""
import io
import json

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
ACTION_KINDS = ["(none)", "key", "media", "seek", "command", "layout"]

CSS = b"""
@define-color win_bg #0B0D14;
@define-color raised #14161F;
@define-color card #1C1F29;
@define-color accent_c #5AAAFA;
* { font-family: "Inter", "Adwaita Sans", sans-serif; }
window { background:@win_bg; }
/* flat, dark headerbar that melts into the window */
headerbar { background:@win_bg; box-shadow:none; border:none; min-height:50px; }
headerbar:backdrop { background:@win_bg; }
.app-title { font-weight:600; font-size:15px; letter-spacing:.2px; color:#F2F3F7; }
.app-sub { color:#5C616E; font-size:12px; }
.dim { color:#9AA0AD; }
.section-title { font-size:10px; font-weight:700; letter-spacing:.8px; color:#565C6B; }
/* the OLED pit - the bar looks embedded in dark aluminium */
.bar-pit { background:#05060B; border-radius:16px; padding:18px 20px;
  box-shadow: inset 0 2px 10px rgba(0,0,0,0.85), inset 0 0 0 1px rgba(255,255,255,0.05); }
.col-left { background:@raised; border-right:1px solid rgba(255,255,255,0.05); }
.col-right { background:@raised; border-left:1px solid rgba(255,255,255,0.05); }
.stage-hint { color:#3E4456; font-size:13px; }
.seg { background:#0C0E16; border-radius:9px; padding:3px; }
.seg button { border-radius:7px; padding:4px 14px; background:transparent; color:#8A90A0;
  box-shadow:none; border:none; min-height:0; font-weight:500; }
.seg button:checked { background:#262A36; color:#F2F3F7;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.07); }
.tabbar { padding:8px 12px; }
.layout-tab { color:#8A90A0; padding:5px 15px; background:transparent; border:none;
  border-radius:8px; box-shadow:none; font-weight:500; }
.layout-tab:hover { background:rgba(255,255,255,0.05); color:#E6E8EF; }
.layout-tab:checked { color:#FFFFFF; background:rgba(90,170,250,0.16); }
.palette-item { padding:11px 13px; border-radius:11px; background:@card;
  border:1px solid rgba(255,255,255,0.04); box-shadow: inset 0 1px 0 rgba(255,255,255,0.04); }
.palette-item:hover { background:#23262F; border-color:rgba(90,170,250,0.30); }
.live-pill { border-radius:999px; padding:4px 13px; background:#14161F; color:#8A90A0;
  border:1px solid rgba(255,255,255,0.06); font-weight:500; }
.live-pill:checked { color:#F2F3F7; border-color:rgba(52,199,89,0.5); }
.danger { color:#FF6B6B; }
.hint { color:#565C6B; font-size:12px; }
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
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Window(Adw.ApplicationWindow):
    def __init__(self, app, path):
        super().__init__(application=app, title="t1bar studio")
        self.set_default_size(1340, 800)
        self.path = path
        self.cfg = cfgmod.load(path)
        self.layout = next(iter(self.cfg["layouts"]), None)
        self.sel = None
        self.mode = "Item"
        self.ruler = None
        self._save_pending = False

        self.toasts = Adw.ToastOverlay()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toasts.set_child(root)
        self.set_content(self.toasts)

        root.append(self._header())
        # canvas (hero) + tabs
        canvas_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        canvas_area.set_margin_top(14); canvas_area.set_margin_bottom(4)
        canvas_area.set_margin_start(20); canvas_area.set_margin_end(20)
        canvas_area.append(self._canvas())
        canvas_area.append(self._ruler())
        canvas_area.append(self._tabbar())
        root.append(canvas_area)

        # three columns
        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        cols.append(self._palette())
        stage = Gtk.Box(hexpand=True)            # breathing space
        hint = Gtk.Label(label="Click a widget on the bar to edit it,\nor add one from the left.")
        hint.add_css_class("stage-hint")
        hint.set_justify(Gtk.Justification.CENTER)
        hint.set_halign(Gtk.Align.CENTER); hint.set_valign(Gtk.Align.CENTER)
        hint.set_hexpand(True); hint.set_vexpand(True)
        stage.append(hint)
        cols.append(stage)
        cols.append(self._inspector())
        root.append(cols)

        self.refresh()
        self.rebuild_inspector()

    # -- regions ---------------------------------------------------------------
    def _header(self):
        hb = Adw.HeaderBar()
        hb.add_css_class("flat")
        title = Gtk.Label(label="t1bar studio"); title.add_css_class("app-title")
        hb.set_title_widget(title)
        self.live = Gtk.ToggleButton(label="●  Live on bar")
        self.live.add_css_class("live-pill")
        self.live.set_tooltip_text("Run `sudo t1bar run -c <config>` to push edits to the hardware")
        hb.pack_end(self.live)
        return hb

    def _canvas(self):
        pit = Gtk.Box(); pit.add_css_class("bar-pit")
        self.pic = Gtk.Picture()
        self.pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.pic.set_can_shrink(True)
        self.pic.set_size_request(-1, 64)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_canvas_click)
        self.pic.add_controller(click)
        pit.append(self.pic)
        return pit

    def _ruler(self):
        box = Gtk.Box()
        box.set_margin_top(8); box.set_margin_start(2); box.set_margin_end(2)
        self.ruler = Gtk.DrawingArea()
        self.ruler.set_content_height(28); self.ruler.set_hexpand(True)
        self.ruler.set_draw_func(self._draw_ruler)
        box.append(self.ruler)
        return box

    def _draw_ruler(self, area, cr, w, h):
        items = self.items()
        if not items:
            return
        total = sum(max(0.01, it.get("weight", 1.0)) for it in items) or 1
        gap = 4
        avail = w - gap * (len(items) - 1)
        x = 0.0
        for i, it in enumerate(items):
            seg = avail * max(0.01, it.get("weight", 1.0)) / total
            t = it.get("type", "button")
            if t == "spacer":
                cr.set_source_rgba(1, 1, 1, 0.04)
            elif i == self.sel:
                cr.set_source_rgba(90/255, 170/255, 250/255, 0.32)
            else:
                cr.set_source_rgba(1, 1, 1, 0.07)
            _round_rect(cr, x, 2, seg, h - 4, 5)
            cr.fill()
            if t != "spacer" and seg > 28:
                label = it.get("id") or t
                cr.set_source_rgba(0.62, 0.66, 0.74, 1)
                cr.select_font_face("Inter")
                cr.set_font_size(10.5)
                ext = cr.text_extents(label)
                if ext.width < seg - 8:
                    cr.move_to(x + seg / 2 - ext.width / 2, h / 2 + ext.height / 2)
                    cr.show_text(label)
            x += seg + gap

    def _tabbar(self):
        self.tabbox = Gtk.Box(spacing=6); self.tabbox.add_css_class("tabbar")
        self._build_tabs()
        return self.tabbox

    def _build_tabs(self):
        while (c := self.tabbox.get_first_child()):
            self.tabbox.remove(c)
        first = None
        for name in self.cfg["layouts"]:
            t = Gtk.ToggleButton(label=name); t.add_css_class("layout-tab")
            t.set_active(name == self.layout)
            if first is None:
                first = t
            else:
                t.set_group(first)
            t.connect("toggled", self._on_tab, name)
            self.tabbox.append(t)
        add = Gtk.Button(label="+"); add.add_css_class("layout-tab")
        add.connect("clicked", self._on_add_layout)
        self.tabbox.append(add)

    def _palette(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.add_css_class("col-left")
        col.set_size_request(212, -1)
        col.set_margin_top(14); col.set_margin_start(14)
        col.set_margin_end(14); col.set_margin_bottom(14)
        lbl = Gtk.Label(label="WIDGETS", xalign=0); lbl.add_css_class("section-title")
        col.append(lbl)
        for kind, desc in (("button", "label or icon + action"),
                           ("scrubber", "draggable progress"),
                           ("label", "static or live text"),
                           ("spacer", "flexible gap")):
            b = Gtk.Button(); b.add_css_class("palette-item")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(label=kind.capitalize(), xalign=0)
            d = Gtk.Label(label=desc, xalign=0); d.add_css_class("hint")
            inner.append(t); inner.append(d); b.set_child(inner)
            b.connect("clicked", self._on_add_item, kind)
            col.append(b)
        return col

    def _inspector(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col.add_css_class("col-right")
        col.set_size_request(326, -1)
        col.set_margin_top(14); col.set_margin_start(14)
        col.set_margin_end(14); col.set_margin_bottom(14)
        seg = Gtk.Box(); seg.add_css_class("seg")
        seg.set_halign(Gtk.Align.CENTER)
        first = None
        for m in ("Item", "Theme", "Rules"):
            b = Gtk.ToggleButton(label=m)
            b.set_active(m == self.mode)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._on_mode, m)
            seg.append(b)
        col.append(seg)
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.inspector_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sc.set_child(self.inspector_body)
        col.append(sc)
        return col

    # -- model helpers ---------------------------------------------------------
    def items(self):
        return self.cfg["layouts"][self.layout]["items"]

    def selected(self):
        if self.sel is None or self.sel >= len(self.items()):
            return None
        return self.items()[self.sel]

    def refresh(self):
        """Re-render the bar (+ selection highlight) and schedule a save."""
        state = {"width": BAR_W, "height": BAR_H, "pressed": None,
                 "media": {"status": "Playing", "position": 73, "length": 210,
                           "title": "Demo Track", "artist": "Artist"}}
        try:
            im = render.render(self.cfg, self.layout, state).convert("RGB")
        except Exception as e:               # never let a bad edit kill the app
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
        if self.mode != "Item":
            self.mode = "Item"
        self.refresh(); self.rebuild_inspector()

    def _on_tab(self, btn, name):
        if btn.get_active():
            self.layout = name; self.sel = None
            self.refresh(); self.rebuild_inspector()

    def _on_mode(self, btn, m):
        if btn.get_active():
            self.mode = m; self.rebuild_inspector()

    def _on_add_layout(self, _btn):
        n = 1
        while f"layout{n}" in self.cfg["layouts"]:
            n += 1
        self.cfg["layouts"][f"layout{n}"] = {"items": []}
        self.layout = f"layout{n}"; self.sel = None
        self._build_tabs(); self.refresh(); self.rebuild_inspector()

    def _on_add_item(self, _btn, kind):
        defaults = {
            "button": {"type": "button", "id": "new", "label": "new",
                       "action": ["key", "KEY_ESC"]},
            "scrubber": {"type": "scrubber", "id": "seek", "weight": 4,
                         "source": "media_position", "action": ["seek"]},
            "label": {"type": "label", "id": "label", "label": "text", "weight": 2},
            "spacer": {"type": "spacer", "weight": 0.5},
        }
        self.items().append(dict(defaults[kind]))
        self.sel = len(self.items()) - 1
        self.mode = "Item"
        self.refresh(); self.rebuild_inspector()

    # -- inspector -------------------------------------------------------------
    def rebuild_inspector(self):
        body = self.inspector_body
        while (c := body.get_first_child()):
            body.remove(c)
        if self.mode == "Item":
            self._inspect_item(body)
        elif self.mode == "Theme":
            self._inspect_theme(body)
        else:
            self._inspect_rules(body)

    def _group(self, body, title):
        g = Adw.PreferencesGroup(title=title)
        body.append(g)
        return g

    def _color_row(self, group, title, obj, key, fallback, clearable=False):
        row = Adw.ActionRow(title=title)
        btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_rgba(rgb_to_rgba(obj.get(key, fallback)))
        btn.connect("notify::rgba", lambda b, _p: self._set(obj, key, rgba_to_rgb(b.get_rgba())))
        row.add_suffix(btn)
        # only per-item overrides can "inherit from theme"; theme base colours can't.
        if clearable and key in obj:
            clr = Gtk.Button(label="↺"); clr.add_css_class("flat"); clr.set_valign(Gtk.Align.CENTER)
            clr.set_tooltip_text("inherit from theme")
            clr.connect("clicked", lambda *_: (obj.pop(key, None), self.refresh(), self.rebuild_inspector()))
            row.add_suffix(clr)
        group.add(row)

    def _entry_row(self, group, title, obj, key, ph=""):
        row = Adw.EntryRow(title=title)
        row.set_text(str(obj.get(key, "")))
        row.connect("changed", lambda r: self._set_text(obj, key, r.get_text()))
        group.add(row)

    def _spin_row(self, group, title, obj, key, lo, hi, step, default):
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_title(title)
        row.set_value(float(obj.get(key, default)))
        row.connect("changed", lambda r: self._set(obj, key, round(r.get_value(), 2)))
        group.add(row)

    def _combo_row(self, group, title, options, current, cb):
        row = Adw.ComboRow(title=title)
        model = Gtk.StringList()
        for o in options:
            model.append(o if o != "" else "(none)")
        row.set_model(model)
        if current in options:
            row.set_selected(options.index(current))
        row.connect("notify::selected", lambda r, _p: cb(options[r.get_selected()]))
        group.add(row)

    def _set(self, obj, key, val):
        obj[key] = val; self.refresh()

    def _set_text(self, obj, key, val):
        if val == "":
            obj.pop(key, None)
        else:
            obj[key] = val
        self.refresh()

    def _inspect_item(self, body):
        it = self.selected()
        if not it:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_margin_top(40)
            l1 = Gtk.Label(label="Nothing selected"); l1.add_css_class("dim")
            l2 = Gtk.Label(label="Click a widget on the bar, or add one."); l2.add_css_class("hint")
            box.append(l1); box.append(l2); body.append(box)
            return
        t = it.get("type", "button")
        g = self._group(body, t.capitalize())
        self._entry_row(g, "id", it, "id")
        self._spin_row(g, "weight", it, "weight", 0.1, 8, 0.1, 1)

        if t == "button":
            cg = self._group(body, "Content")
            self._entry_row(cg, "label", it, "label")
            self._combo_row(cg, "icon", ICON_NAMES, it.get("icon", ""),
                            lambda v: self._set_opt(it, "icon", v))
            self._combo_row(cg, "follow playback", ["", "play_pause"], it.get("dynamic", ""),
                            lambda v: self._set_opt(it, "dynamic", v))
            colg = self._group(body, "Colors")
            self._color_row(colg, "fill", it, "fill", self.cfg["theme"]["button"]["fill"], clearable=True)
            self._color_row(colg, "text", it, "color", self.cfg["theme"]["button"]["text"], clearable=True)
            self._action_editor(body, it)
        elif t == "scrubber":
            sg = self._group(body, "Source")
            self._combo_row(sg, "bind", ["", "media_position"], it.get("source", ""),
                            lambda v: self._set_opt(it, "source", v))
        elif t == "label":
            cg = self._group(body, "Content")
            self._entry_row(cg, "text", it, "label")
            self._combo_row(cg, "bind", ["", "media_title", "media_artist"], it.get("source", ""),
                            lambda v: self._set_opt(it, "source", v))
            self._color_row(self._group(body, "Color"), "text", it, "color",
                            self.cfg["theme"]["button"]["text"], clearable=True)

        dg = self._group(body, "")
        rm = Adw.ButtonRow(title="Delete widget") if hasattr(Adw, "ButtonRow") else None
        if rm:
            rm.add_css_class("danger")
            rm.connect("activated", lambda *_: self._delete_item())
            dg.add(rm)
        else:
            btn = Gtk.Button(label="Delete widget"); btn.add_css_class("danger")
            btn.connect("clicked", lambda *_: self._delete_item())
            body.append(btn)

    def _set_opt(self, obj, key, val):
        if val == "":
            obj.pop(key, None)
        else:
            obj[key] = val
        self.refresh()

    def _delete_item(self):
        if self.sel is not None and self.sel < len(self.items()):
            self.items().pop(self.sel)
            self.sel = None
            self.refresh(); self.rebuild_inspector()

    def _action_editor(self, body, it):
        g = self._group(body, "Action")
        action = it.get("action") or []
        kind = action[0] if action else "(none)"

        def set_kind(v):
            if v == "(none)":
                it.pop("action", None)
            elif v == "key":
                it["action"] = ["key", "KEY_ESC"]
            elif v == "media":
                it["action"] = ["media", "play-pause"]
            elif v == "seek":
                it["action"] = ["seek"]
            elif v == "command":
                it["action"] = ["command", ""]
            elif v == "layout":
                it["action"] = ["layout", next(iter(self.cfg["layouts"]))]
            self.refresh(); self.rebuild_inspector()

        self._combo_row(g, "do", ACTION_KINDS, kind, set_kind)
        if kind == "key":
            self._combo_row(g, "key", KEYS, action[1] if len(action) > 1 else KEYS[0],
                            lambda v: self._set(it, "action", ["key", v]))
        elif kind == "media":
            verbs = ["play-pause", "play", "pause", "next", "previous", "stop"]
            self._combo_row(g, "verb", verbs, action[1] if len(action) > 1 else verbs[0],
                            lambda v: self._set(it, "action", ["media", v]))
        elif kind == "layout":
            lays = list(self.cfg["layouts"])
            self._combo_row(g, "to", lays, action[1] if len(action) > 1 else lays[0],
                            lambda v: self._set(it, "action", ["layout", v]))
        elif kind == "command":
            row = Adw.EntryRow(title="command")
            row.set_text(" ".join(action[1:]))
            row.connect("changed", lambda r: self._set(
                it, "action", ["command"] + r.get_text().split()))
            g.add(row)

    def _inspect_theme(self, body):
        th = self.cfg["theme"]
        sg = self._group(body, "Surface")
        self._color_row(sg, "background", th, "background", [8, 10, 18])
        self._color_row(sg, "accent", th, "accent", [90, 170, 250])
        bg = self._group(body, "Buttons")
        self._color_row(bg, "fill", th["button"], "fill", [38, 42, 58])
        self._color_row(bg, "text", th["button"], "text", [232, 234, 240])
        self._spin_row(bg, "radius", th["button"], "radius", 0, 24, 1, 12)
        self._spin_row(bg, "font size", th["button"], "font_size", 14, 34, 1, 26)
        pg = self._group(body, "Pressed")
        self._color_row(pg, "fill", th["pressed"], "fill", [70, 110, 210])
        spg = self._group(body, "Spacing")
        self._spin_row(spg, "gap", th, "gap", 0, 24, 1, 10)
        self._spin_row(spg, "margin", th, "margin", 0, 24, 1, 10)

    def _inspect_rules(self, body):
        g = self._group(body, "Rules — first match wins")
        for i, rule in enumerate(self.cfg.get("rules", [])):
            when = rule.get("when")
            if when:
                k, v = next(iter(when.items()))
                txt = f"When {k} is {v}  →  {rule.get('show')}"
            else:
                txt = f"Otherwise  →  {rule.get('show')}"
            g.add(Adw.ActionRow(title=txt, subtitle=f"priority {i + 1}"))
        hint = Gtk.Label(label="Rule editing UI is coming next; edit shown read-only.",
                         xalign=0)
        hint.add_css_class("hint"); hint.set_margin_top(8)
        body.append(hint)


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
            for i, it in enumerate(win.items()):     # select a widget for the shot
                if it.get("type", "button") == "button":
                    win.sel = i; win.mode = "Item"; win.refresh(); win.rebuild_inspector()
                    break
            GLib.timeout_add(1300, self._save_shot, win)

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
