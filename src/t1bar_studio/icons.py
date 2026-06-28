"""Vector glyphs drawn into a bounding box, so they scale crisply at any size and
recolour with the theme. Each function: draw(d, box, color) where box=(x0,y0,x1,y1).

Register new icons in ICONS; reference them from a button's "icon" in the config.
"""
from PIL import ImageDraw


def _fit(box, frac=0.46):
    """Centre point + radius for a glyph that fills `frac` of the (square-ish) box."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) * frac
    return cx, cy, r


def _triangle(d, cx, cy, r, color, pointing="right"):
    if pointing == "right":
        pts = [(cx - r * 0.7, cy - r), (cx - r * 0.7, cy + r), (cx + r * 0.85, cy)]
    else:  # left
        pts = [(cx + r * 0.7, cy - r), (cx + r * 0.7, cy + r), (cx - r * 0.85, cy)]
    d.polygon(pts, fill=color)


def play(d, box, color):
    cx, cy, r = _fit(box)
    _triangle(d, cx, cy, r, color, "right")


def pause(d, box, color):
    cx, cy, r = _fit(box)
    w = r * 0.5
    d.rectangle([cx - r * 0.65, cy - r, cx - r * 0.65 + w, cy + r], fill=color)
    d.rectangle([cx + r * 0.15, cy - r, cx + r * 0.15 + w, cy + r], fill=color)


def prev(d, box, color):
    cx, cy, r = _fit(box)
    d.rectangle([cx - r, cy - r, cx - r + r * 0.32, cy + r], fill=color)
    _triangle(d, cx + r * 0.15, cy, r * 0.9, color, "left")


def nxt(d, box, color):
    cx, cy, r = _fit(box)
    _triangle(d, cx - r * 0.3, cy, r * 0.9, color, "right")
    d.rectangle([cx + r * 0.7, cy - r, cx + r, cy + r], fill=color)


def _sun(d, box, color, rays=8, ray_len=0.55):
    import math
    cx, cy, r = _fit(box, 0.30)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    for i in range(rays):
        a = (math.pi * 2 / rays) * i
        x0 = cx + math.cos(a) * r * 1.5
        y0 = cy + math.sin(a) * r * 1.5
        x1 = cx + math.cos(a) * r * (1.5 + ray_len)
        y1 = cy + math.sin(a) * r * (1.5 + ray_len)
        d.line([x0, y0, x1, y1], fill=color, width=3)


def brightness_up(d, box, color):
    _sun(d, box, color, ray_len=0.7)


def brightness_down(d, box, color):
    _sun(d, box, color, ray_len=0.25)


def _speaker(d, box, color):
    cx, cy, r = _fit(box, 0.42)
    bx0 = cx - r * 0.9
    d.rectangle([bx0, cy - r * 0.35, bx0 + r * 0.45, cy + r * 0.35], fill=color)
    d.polygon([(bx0 + r * 0.45, cy - r * 0.35), (bx0 + r * 0.45, cy + r * 0.35),
               (cx + r * 0.1, cy + r * 0.8), (cx + r * 0.1, cy - r * 0.8)], fill=color)
    return cx, cy, r


def volume_up(d, box, color):
    cx, cy, r = _speaker(d, box, color)
    for k in (0.45, 0.8):
        d.arc([cx - r * 0.1, cy - r * k, cx + r * (0.3 + k), cy + r * k],
              start=-45, end=45, fill=color, width=3)


def volume_down(d, box, color):
    cx, cy, r = _speaker(d, box, color)
    d.arc([cx - r * 0.1, cy - r * 0.45, cx + r * 0.75, cy + r * 0.45],
          start=-45, end=45, fill=color, width=3)


def volume_mute(d, box, color, red=(235, 60, 60)):
    cx, cy, r = _speaker(d, box, color)
    rr = r * 0.7
    ox, oy = cx + r * 0.7, cy
    d.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], outline=red, width=3)
    import math
    a = math.radians(45)
    d.line([ox - rr * math.cos(a), oy - rr * math.sin(a),
            ox + rr * math.cos(a), oy + rr * math.sin(a)], fill=red, width=3)


def fullscreen(d, box, color):
    cx, cy, r = _fit(box, 0.5)
    L = r * 0.55
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y = cx + sx * r, cy + sy * r
        d.line([x, y, x - sx * L, y], fill=color, width=3)
        d.line([x, y, x, y - sy * L], fill=color, width=3)


def _glyph_text(s):
    def draw(d, box, color):
        # fallback: a couple of letters centred (used for CC etc.)
        from PIL import ImageFont
        try:
            fs = int(min(box[2] - box[0], box[3] - box[1]) * 0.5)
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", fs)
        except Exception:
            font = ImageFont.load_default()
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        tb = d.textbbox((0, 0), s, font=font)
        d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
               s, font=font, fill=color)
    return draw


ICONS = {
    "play": play, "pause": pause, "prev": prev, "next": nxt,
    "brightness_up": brightness_up, "brightness_down": brightness_down,
    "volume_up": volume_up, "volume_down": volume_down, "volume_mute": volume_mute,
    "fullscreen": fullscreen, "cc": _glyph_text("CC"),
}


def draw_icon(d, name, box, color):
    fn = ICONS.get(name)
    if fn:
        fn(d, box, color)
        return True
    return False
