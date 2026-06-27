#!/usr/bin/env python3
"""Reactive touch demo on the t1touchbar public API: a glow follows your finger
and water ripples spread from each touch.

    sudo python3 examples/reactive_ripples.py
"""
import time

from PIL import Image, ImageDraw

from t1touchbar import Device, TouchReader

state = {"x": 0, "y": 0, "down": False, "last": 0.0}
ripples = []  # each: [x, y, t0]


def on_touch(ev):
    state["x"], state["y"], state["last"] = ev.x, ev.y, time.time()
    if ev.state == "up":
        state["down"] = False
        return
    state["down"] = True
    if ev.state == "down" or not ripples or time.time() - ripples[-1][2] > 0.05:
        ripples.append([ev.x, ev.y, time.time()])


def frame(w, h):
    im = Image.new("RGB", (w, h), (4, 6, 16))
    d = ImageDraw.Draw(im)
    now = time.time()
    alive = []
    for rp in list(ripples):
        x, y, t0 = rp
        age = now - t0
        if age > 0.8:
            continue
        alive.append(rp)
        rad = int(age * 700)
        b = max(0, int(220 * (1 - age / 0.8)))
        d.ellipse([x - rad, y - rad, x + rad, y + rad], outline=(0, b, b), width=3)
    ripples[:] = alive
    if state["down"] or now - state["last"] < 0.12:
        x, y = state["x"], state["y"]
        for rr, bb in ((30, 30), (20, 70), (12, 140), (6, 255)):
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(0, bb, min(255, bb + 40)))
    return im


def main():
    with Device() as bar:
        tr = TouchReader(bar.width, bar.height)
        tr.start(on_touch)
        print("touch and drag the bar — Ctrl-C to quit")
        try:
            while True:
                bar.blit(frame(bar.width, bar.height))
        except KeyboardInterrupt:
            pass
        finally:
            tr.stop()


if __name__ == "__main__":
    main()
