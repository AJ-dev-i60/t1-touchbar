#!/usr/bin/env python3
"""Scrolling marquee.

    sudo python3 examples/scroll.py "your message here"
"""
import sys

from PIL import Image, ImageDraw, ImageFont

from t1touchbar import Device


def _font(sz=44):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def main():
    text = " ".join(sys.argv[1:]) or "t1-touchbar  —  hello from Linux   "
    font = _font()
    with Device() as bar:
        w, h = bar.width, bar.height
        bb = ImageDraw.Draw(Image.new("RGB", (4, 4))).textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        strip = Image.new("RGB", (tw + 2 * w, h), (0, 0, 0))
        ImageDraw.Draw(strip).text((w - bb[0], (h - th) // 2 - bb[1]), text, font=font,
                                   fill=(255, 255, 255))
        print("scrolling — Ctrl-C to quit")
        try:
            while True:
                for off in range(0, strip.width - w, 3):   # 3 px/frame ≈ smooth ticker
                    bar.blit(strip.crop((off, 0, off + w, h)))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
