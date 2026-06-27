"""Render a control-strip layout to a panel-sized PIL image."""
from PIL import Image, ImageDraw, ImageFont

from . import icons

_FONT_CACHE = {}


def _font(size):
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except Exception:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def button_bounds(layout, width):
    """Yield (button, x0, x1) pixel spans for hit-testing and rendering."""
    total = sum(b.weight for b in layout) or 1
    x = 0.0
    for b in layout:
        bw = width * b.weight / total
        yield b, int(x), int(x + bw)
        x += bw


def hit(layout, px, width):
    """Return the Button under pixel x, or None."""
    for b, x0, x1 in button_bounds(layout, width):
        if x0 <= px < x1:
            return b
    return layout[-1] if layout else None


def render(layout, width, height, pressed=None, playing=None):
    im = Image.new("RGB", (width, height), (0, 0, 0))
    d = ImageDraw.Draw(im)
    font = _font(26)
    for b, x0, x1 in button_bounds(layout, width):
        on = (b.id == pressed)
        d.rounded_rectangle([x0 + 4, 5, x1 - 4, height - 5], radius=8,
                            fill=(0, 120, 255) if on else (28, 28, 34),
                            outline=(70, 70, 82), width=1)
        col = (255, 255, 255)
        icon = b.icon
        if b.id == "play" and playing is not None:
            # Reflect live media state. Standard convention: the icon shows what a
            # tap will DO -> pause while playing, play while paused. (Flip these two
            # if you'd rather mirror the current state instead.)
            icon = "pause" if playing else "play"
        if icon:
            icons.draw(d, icon, (x0 + 10, 6, x1 - 10, height - 6), col)
        elif b.label:
            bb = d.textbbox((0, 0), b.label, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            d.text(((x0 + x1) // 2 - tw // 2 - bb[0], (height - th) // 2 - bb[1]),
                   b.label, font=font, fill=col)
    return im
