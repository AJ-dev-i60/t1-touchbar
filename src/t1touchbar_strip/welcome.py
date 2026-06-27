"""Welcome showcase: 'T1 TOUCHBAR' growing in the centre over falling fiery
raindrops. Played once when the strip starts, to prove the driver works.

play(blit, width, height) renders frames and pushes them via the `blit` callback
(e.g. Device.blit). Returns when the animation finishes.
"""
import math
import random
import time

from PIL import Image, ImageDraw, ImageFont

TEXT = "T1 TOUCHBAR"


def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def play(blit, width, height, duration=4.0):
    n = max(40, width // 24)
    drops = [[random.uniform(0, width), random.uniform(-height, height),
              random.uniform(0.6, 1.8), random.uniform(0.4, 1.0)] for _ in range(n)]
    grow_for = duration * 0.65
    max_size = int(height * 0.78)
    t0 = time.time()
    last = t0
    while True:
        now = time.time()
        t = now - t0
        if t > duration:
            break
        dt = now - last
        last = now

        im = Image.new("RGB", (width, height), (0, 0, 0))
        d = ImageDraw.Draw(im)

        # fiery raindrops
        for dr in drops:
            dr[1] += dr[2] * height * dt * 1.6
            if dr[1] > height + 4:
                dr[0] = random.uniform(0, width)
                dr[1] = random.uniform(-30, -2)
            x, y, hot = int(dr[0]), int(dr[1]), dr[3]
            tail = int(6 + 10 * dr[2])
            g = int(90 + 130 * hot)
            d.line([(x, y - tail), (x, y)], fill=(255, g, 0), width=2)
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(255, 230, 140))

        # growing centre text with a warm glow
        prog = min(1.0, t / grow_for)
        size = max(10, int(max_size * (0.15 + 0.85 * prog)))
        f = _font(size)
        bb = d.textbbox((0, 0), TEXT, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        ox, oy = (width - tw) // 2 - bb[0], (height - th) // 2 - bb[1]
        glow = int(110 + 145 * prog)
        for off in (3, 2, 1):  # cheap glow
            d.text((ox, oy), TEXT, font=f, fill=(120, 40, 0))
        d.text((ox, oy), TEXT, font=f, fill=(255, glow, 70))

        blit(im)
