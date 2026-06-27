"""Simple vector glyphs for the control strip, drawn with PIL primitives.

draw(d, name, box, color) renders the named glyph centered in `box`=(x0,y0,x1,y1).
For the "<icon> <+/->" buttons the icon sits left-of-centre and the sign right-of-
centre, as a balanced, well-spaced group.
"""
import math

MUTE_RED = (255, 45, 45)


def _plus(d, cx, cy, r, color, w=3):
    d.line([(cx - r, cy), (cx + r, cy)], fill=color, width=w)
    d.line([(cx, cy - r), (cx, cy + r)], fill=color, width=w)


def _minus(d, cx, cy, r, color, w=3):
    d.line([(cx - r, cy), (cx + r, cy)], fill=color, width=w)


def _sun(d, cx, cy, r, color):
    d.ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5],
              outline=color, width=2)
    for a in range(0, 360, 45):
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        d.line([(cx + dx * r * 0.72, cy + dy * r * 0.72),
                (cx + dx * r * 0.98, cy + dy * r * 0.98)], fill=color, width=2)


def _keyboard(d, cx, cy, r, color):
    d.rounded_rectangle([cx - r * 0.9, cy - r * 0.55, cx + r * 0.9, cy + r * 0.55],
                        radius=3, outline=color, width=2)
    for ix in (-r * 0.45, 0, r * 0.45):
        d.ellipse([cx + ix - 1.5, cy - 1.5, cx + ix + 1.5, cy + 1.5], fill=color)


def _speaker(d, cx, cy, r, color):
    d.polygon([(cx - r * 0.7, cy - r * 0.35), (cx - r * 0.1, cy - r * 0.35),
               (cx + r * 0.5, cy - r * 0.8), (cx + r * 0.5, cy + r * 0.8),
               (cx - r * 0.1, cy + r * 0.35), (cx - r * 0.7, cy + r * 0.35)], fill=color)


def draw(d, name, box, color=(255, 255, 255)):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) * 0.34

    # Balanced "<icon>   <sign>" group: icon left, sign right, generous gap.
    ICON_X = cx - r * 1.0
    SIGN_X = cx + r * 1.25
    SIGN_R = r * 0.5

    def rtri(px):
        d.polygon([(px - r, cy - r), (px - r, cy + r), (px + r, cy)], fill=color)

    def ltri(px):
        d.polygon([(px + r, cy - r), (px + r, cy + r), (px - r, cy)], fill=color)

    if name == "play":
        rtri(cx)
    elif name == "pause":
        bw = r * 0.36
        d.rectangle([cx - r * 0.55, cy - r, cx - r * 0.55 + bw, cy + r], fill=color)
        d.rectangle([cx + r * 0.55 - bw, cy - r, cx + r * 0.55, cy + r], fill=color)
    elif name == "prev":
        ltri(cx - r * 0.5)
        ltri(cx + r * 0.9)
        d.rectangle([cx - r * 1.5, cy - r, cx - r * 1.2, cy + r], fill=color)
    elif name == "next":
        rtri(cx - r * 0.9)
        rtri(cx + r * 0.5)
        d.rectangle([cx + r * 1.2, cy - r, cx + r * 1.5, cy + r], fill=color)
    elif name == "bright_dn":
        _sun(d, ICON_X, cy, r, color); _minus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "bright_up":
        _sun(d, ICON_X, cy, r, color); _plus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "kbd_dn":
        _keyboard(d, ICON_X, cy, r, color); _minus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "kbd_up":
        _keyboard(d, ICON_X, cy, r, color); _plus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "vol_dn":
        _speaker(d, ICON_X, cy, r, color); _minus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "vol_up":
        _speaker(d, ICON_X, cy, r, color); _plus(d, SIGN_X, cy, SIGN_R, color)
    elif name == "mute":
        _speaker(d, ICON_X, cy, r, color)
        mr = r * 0.78
        mx, my = cx + r * 1.15, cy
        d.ellipse([mx - mr, my - mr, mx + mr, my + mr], outline=MUTE_RED, width=3)
        off = mr * 0.7071
        d.line([(mx - off, my - off), (mx + off, my + off)], fill=MUTE_RED, width=3)
