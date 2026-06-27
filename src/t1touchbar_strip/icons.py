"""Simple vector glyphs for the control strip, drawn with PIL primitives.

draw(d, name, box, color) renders the named glyph centered in `box` = (x0,y0,x1,y1).
Kept deliberately minimal/recognisable; refine freely later.
"""
import math


def _plus(d, cx, cy, r, color):
    d.line([(cx - r, cy), (cx + r, cy)], fill=color, width=3)
    d.line([(cx, cy - r), (cx, cy + r)], fill=color, width=3)


def _minus(d, cx, cy, r, color):
    d.line([(cx - r, cy), (cx + r, cy)], fill=color, width=3)


def draw(d, name, box, color=(255, 255, 255)):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) * 0.32

    def rtri(px):  # right-pointing play triangle at x=px
        d.polygon([(px - r, cy - r), (px - r, cy + r), (px + r, cy)], fill=color)

    def ltri(px):  # left-pointing
        d.polygon([(px + r, cy - r), (px + r, cy + r), (px - r, cy)], fill=color)

    if name == "play":
        rtri(cx)
    elif name == "prev":
        ltri(cx - r * 0.5)
        ltri(cx + r * 0.9)
        d.rectangle([cx - r * 1.5, cy - r, cx - r * 1.2, cy + r], fill=color)
    elif name == "next":
        rtri(cx - r * 0.9)
        rtri(cx + r * 0.5)
        d.rectangle([cx + r * 1.2, cy - r, cx + r * 1.5, cy + r], fill=color)
    elif name in ("vol_up", "vol_dn", "mute"):
        d.polygon([(cx - r, cy - r * 0.4), (cx - r * 0.3, cy - r * 0.4),
                   (cx + r * 0.2, cy - r), (cx + r * 0.2, cy + r),
                   (cx - r * 0.3, cy + r * 0.4), (cx - r, cy + r * 0.4)], fill=color)
        if name == "vol_up":
            _plus(d, cx + r * 0.9, cy, r * 0.45, color)
        elif name == "vol_dn":
            _minus(d, cx + r * 0.9, cy, r * 0.45, color)
        else:
            d.line([(cx + r * 0.45, cy - r * 0.6), (cx + r * 1.15, cy + r * 0.6)],
                   fill=color, width=2)
    elif name in ("bright_up", "bright_dn"):
        d.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5],
                  outline=color, width=2)
        for a in range(0, 360, 45):
            dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
            d.line([(cx + dx * r * 0.75, cy + dy * r * 0.75),
                    (cx + dx * r * 1.0, cy + dy * r * 1.0)], fill=color, width=2)
        (_plus if name == "bright_up" else _minus)(d, cx + r * 1.8, cy, r * 0.5, color)
    elif name in ("kbd_up", "kbd_dn"):
        d.rounded_rectangle([cx - r, cy - r * 0.6, cx + r, cy + r * 0.6], radius=3,
                            outline=color, width=2)
        for ix in (-r * 0.5, 0, r * 0.5):
            d.ellipse([cx + ix - 1, cy - 1, cx + ix + 1, cy + 1], fill=color)
        (_plus if name == "kbd_up" else _minus)(d, cx + r * 1.9, cy, r * 0.5, color)
