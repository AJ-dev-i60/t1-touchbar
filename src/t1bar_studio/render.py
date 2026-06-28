"""Render a layout to a PIL image, and hit-test touches back to items.

Items lay out left→right, widths split by "weight". Supported types:
  button   — label or icon; per-button "fill"/"text"/"icon" colour overrides; a
             "dynamic":"play_pause" swaps its icon from live media state
  scrubber — a draggable progress bar ("source":"media_position" tracks playback)
  label    — static text
  spacer   — empty flexible gap
"""
from PIL import Image, ImageDraw, ImageFont

from . import icons

_FONTS = {}


def _font(size):
    if size not in _FONTS:
        try:
            _FONTS[size] = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except Exception:
            _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


def _rounded(d, box, radius, fill):
    d.rounded_rectangle(box, radius=radius, fill=tuple(fill))


def boxes(cfg, layout_name, width, height):
    """[(item, (x0,y0,x1,y1)), ...] for every item (incl. spacers)."""
    theme = cfg["theme"]
    margin, gap = theme["margin"], theme["gap"]
    items = cfg["layouts"][layout_name]["items"]
    if not items:
        return []
    total_w = width - 2 * margin - gap * (len(items) - 1)
    wsum = sum(max(0.01, it.get("weight", 1.0)) for it in items) or 1
    out, x = [], margin
    for it in items:
        w = total_w * max(0.01, it.get("weight", 1.0)) / wsum
        out.append((it, (x, margin, x + w, height - margin)))
        x += w + gap
    return out


def _label_text(item, state):
    """Static label, or bound to live state via "source"."""
    src = item.get("source")
    m = state.get("media", {})
    if src == "media_title":
        t, a = m.get("title", ""), m.get("artist", "")
        return f"{t} — {a}" if (t and a) else (t or a)
    if src == "media_artist":
        return m.get("artist", "")
    return item.get("label", "")


def _ellipsize(d, s, font, max_w):
    if not s:
        return s
    if d.textlength(s, font=font) <= max_w:
        return s
    while s and d.textlength(s + "…", font=font) > max_w:
        s = s[:-1]
    return s + "…"


def _resolve_icon(item, state):
    if item.get("dynamic") == "play_pause":
        return "pause" if (state.get("media", {}).get("status") == "Playing") else "play"
    return item.get("icon")


def _draw_button(d, item, box, theme, pressed, state):
    bt, pr = theme["button"], theme["pressed"]
    fill = pr.get("fill", bt["fill"]) if pressed else item.get("fill", bt["fill"])
    _rounded(d, box, bt["radius"], fill)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    fg = pr.get("color", bt["text"]) if pressed else item.get("color", bt["text"])
    icon = _resolve_icon(item, state)            # icon NAME (or None)
    if icon and icons.draw_icon(d, icon, box, tuple(fg)):
        return
    label = item.get("label", "")
    font = _font(item.get("font_size", bt["font_size"]))
    tb = d.textbbox((0, 0), label, font=font)
    d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
           label, font=font, fill=tuple(fg))


def _draw_scrubber(d, item, box, theme, state):
    x0, y0, x1, y1 = box
    h = (y1 - y0)
    midy = (y0 + y1) / 2
    th = max(6, h * 0.32)
    track = (x0, midy - th / 2, x1, midy + th / 2)
    _rounded(d, track, th / 2, theme["track"])
    frac = 0.0
    if item.get("source") == "media_position":
        m = state.get("media", {})
        if m.get("length"):
            frac = min(1.0, max(0.0, (m.get("position") or 0) / m["length"]))
    if frac > 0:
        _rounded(d, (x0, midy - th / 2, x0 + (x1 - x0) * frac, midy + th / 2),
                 th / 2, theme["accent"])
    # knob
    kx = x0 + (x1 - x0) * frac
    kr = h * 0.34
    d.ellipse([kx - kr, midy - kr, kx + kr, midy + kr], fill=tuple(theme["accent"]),
              outline=(255, 255, 255), width=2)


def render(cfg, layout_name, state):
    theme = cfg["theme"]
    w, h = state["width"], state["height"]
    im = Image.new("RGB", (w, h), tuple(theme["background"]))
    d = ImageDraw.Draw(im)
    pressed = state.get("pressed")
    for item, box in boxes(cfg, layout_name, w, h):
        t = item.get("type", "button")
        if t == "spacer":
            continue
        if t == "scrubber":
            _draw_scrubber(d, item, box, theme, state)
        elif t == "label":
            font = _font(item.get("font_size", theme["button"]["font_size"]))
            color = item.get("color", theme["button"]["text"])
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            s = _label_text(item, state)
            s = _ellipsize(d, s, font, box[2] - box[0])
            tb = d.textbbox((0, 0), s, font=font)
            d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
                   s, font=font, fill=tuple(color))
        else:
            _draw_button(d, item, box, theme, item.get("id") == pressed, state)
    return im


def hit(cfg, layout_name, px, width, height):
    """Return (item, fraction) for the item under x=px, or (None, None).
    `fraction` is the 0..1 position along the item (used by scrubbers)."""
    for item, box in boxes(cfg, layout_name, width, height):
        if item.get("type") == "spacer":
            continue
        if box[0] <= px <= box[2]:
            frac = (px - box[0]) / max(1, box[2] - box[0])
            return item, frac
    return None, None
