#!/usr/bin/env python3
"""Tappable-buttons demo: four buttons; the one you press lights up.

    sudo python3 examples/buttons.py
"""
import time

from PIL import Image, ImageDraw, ImageFont

from t1touchbar import Device, TouchReader

LABELS = ["< PREV", "|| PLAY", "NEXT >", "* LIKE"]
state = {"hi": -1, "dirty": True}


def _font(sz=40):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


FONT = _font()


def render(w, h):
    im = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(im)
    n = len(LABELS)
    bw = w // n
    for i, lbl in enumerate(LABELS):
        x0, x1 = i * bw + 5, (i + 1) * bw - 5
        on = i == state["hi"]
        d.rectangle([x0, 5, x1, h - 5], fill=(0, 130, 255) if on else (35, 35, 40),
                    outline=(110, 110, 120), width=2)
        bb = d.textbbox((0, 0), lbl, font=FONT)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((x0 + x1) // 2 - tw // 2 - bb[0], (h - th) // 2 - bb[1]), lbl,
               font=FONT, fill=(255, 255, 255) if on else (200, 200, 200))
    return im


def main():
    with Device() as bar:
        w, h, n = bar.width, bar.height, len(LABELS)

        def on_touch(ev):
            if ev.state in ("down", "move"):
                b = max(0, min(n - 1, ev.x * n // w))
                if b != state["hi"]:
                    state["hi"] = b
                    state["dirty"] = True
                    print(f"button {b}: {LABELS[b]}")

        tr = TouchReader(w, h)
        tr.start(on_touch)
        print("tap the buttons — Ctrl-C to quit")
        try:
            while True:
                if state["dirty"]:
                    state["dirty"] = False
                    bar.blit(render(w, h))
                time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            tr.stop()


if __name__ == "__main__":
    main()
