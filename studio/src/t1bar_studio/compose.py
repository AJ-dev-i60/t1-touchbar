"""The layered / material compositor — renders a Scene to a 2170×60 frame.

This replaces the legacy left-to-right ``render.py``. Where the old renderer drew a
flat coloured box per item, this one composites, per part:

    scene background (Solid / Gradient …)            ← a sibling surface
      └─ for each part, in an auto-flow slot:
           under-effects (Shadow, Glow)              ← haloes beneath the part
           the part shape per its MATERIAL           ← Solid/Outline/Ghost/Metal/Frosted
           over-effects (Bevel, Scanline)            ← inset light, scanlines
           the icon / label / live readout           ← the Loom's icon layer
           (sliders draw their own track/fill/knob)

It is deliberately PIL-based for Phase 1 (matches the existing renderer; blur via
``ImageFilter``, gradients/bevels hand-rolled). Cairo/GSK can replace internals later
without changing this module's surface.

The ``t`` (seconds) parameter is threaded through for Phase 2 motion: motion layers
and timing envelopes modulate per-part offset/alpha. With no motion layers present
(the converter adds none), rendering is fully static, so ``t`` is a no-op today.

Public entry points:
    render_scene(scene, geometry, live, theme=None, t=0.0) -> PIL.Image (RGB)
    compose(cfg, live, scene=None, t=0.0)                  -> PIL.Image (RGB)
    layout_parts(parts, w, h, margin, gap)                -> [(part, (x0,y0,x1,y1))]
    hit_test(scene, geometry, px)                          -> (part, fraction) | (None, None)
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import icons, motion

# ── material / strip example tokens (from the concept design tokens) ─────────
METAL_TOP = (227, 179, 79)        # #e3b34f
METAL_MID = (200, 144, 47)        # #c8902f
METAL_BOT = (156, 108, 31)        # #9c6c1f
METAL_BORDER = (94, 67, 16)       # #5e4310
METAL_INK = (40, 28, 8)           # dark icon/text on metal
FROST_FILL = (255, 255, 255, 41)  # rgba(255,255,255,0.16)
FROST_BORDER = (255, 255, 255, 87)  # rgba(255,255,255,0.34)
FROST_BLUR = 7
STATUS_GREEN = (70, 196, 121)     # #46c479

_FONTS = {}


def _font(size, mono=False):
    size = max(8, int(size))
    key = (size, mono)
    if key not in _FONTS:
        candidates = (["SpaceMono-Bold.ttf", "DejaVuSansMono-Bold.ttf"] if mono
                      else ["DejaVuSans-Bold.ttf"])
        for name in candidates:
            try:
                _FONTS[key] = ImageFont.truetype(name, size)
                break
            except Exception:
                continue
        else:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _rgba(c, alpha=255):
    c = list(c)
    if len(c) >= 4:
        return tuple(int(v) for v in c[:4])
    return (int(c[0]), int(c[1]), int(c[2]), int(alpha))


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# ── auto-flow slot layout ────────────────────────────────────────────────────
def _intrinsic(part, slot_h):
    """The natural width of a fixed-width part (square-ish, scaled by weight).
    Spacers contribute nothing intrinsic — they only exist to stretch."""
    if part.type == "spacer":
        return 0.0
    return slot_h * 1.15 * max(0.1, part.weight)


def _weighted(parts, inner_w, x0, gap, y0, y1):
    """Fallback: split the ribbon across every part by weight (legacy behaviour).
    Used when there are no stretchy parts, or fixed parts overflow the strip."""
    wsum = sum(max(0.01, p.weight) for p in parts) or 1
    boxes, x = [], x0
    for p in parts:
        w = inner_w * max(0.01, p.weight) / wsum
        boxes.append((p, (x, y0, x + w, y1)))
        x += w + gap
    return boxes


def layout_parts(parts, width, height, margin, gap):
    """Lay parts into slots along the strip. Fixed parts take an intrinsic width;
    stretchy parts share the remaining ribbon by weight. Returns
    ``[(part, (x0, y0, x1, y1)), …]`` with vertical margins already applied."""
    n = len(parts)
    if not n:
        return []
    inner_w = width - 2 * margin - gap * (n - 1)
    y0, y1 = margin, height - margin
    slot_h = y1 - y0

    stretch = [p for p in parts if p.width_mode == "stretchy"]
    if not stretch:
        return _weighted(parts, inner_w, margin, gap, y0, y1)

    fixed_w = {id(p): _intrinsic(p, slot_h) for p in parts if p.width_mode != "stretchy"}
    fixed_total = sum(fixed_w.values())
    rem = inner_w - fixed_total
    if rem < 0:                                  # fixed parts overflow → weighted
        return _weighted(parts, inner_w, margin, gap, y0, y1)

    wsum = sum(max(0.01, p.weight) for p in stretch) or 1
    boxes, x = [], margin
    for p in parts:
        if p.width_mode == "stretchy":
            w = rem * max(0.01, p.weight) / wsum
        else:
            w = fixed_w[id(p)]
        boxes.append((p, (x, y0, x + w, y1)))
        x += w + gap
    return boxes


# ── shape + effect primitives ────────────────────────────────────────────────
def _rrect_mask(w, h, radius):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1],
                                        radius=min(radius, h // 2, w // 2), fill=255)
    return m


def _grad_from_t(t, stops):
    """Build an RGB image from a per-pixel parameter array ``t`` (h×w, 0..1) and a
    list of (pos, rgb) stops. Fully vectorised — no Python pixel loop."""
    import numpy as np
    stops = sorted(stops)
    pos = np.array([p for p, _ in stops], dtype="float32")
    cols = np.array([c for _, c in stops], dtype="float32")     # (k, 3)
    out = np.empty(t.shape + (3,), dtype="float32")
    for ch in range(3):
        out[..., ch] = np.interp(t, pos, cols[:, ch])
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"), "RGB")


def _vgrad(w, h, stops):
    """Vertical gradient from a list of (pos0-1, rgb) stops (numpy-vectorised)."""
    import numpy as np
    t = np.linspace(0.0, 1.0, h, dtype="float32")[:, None].repeat(w, axis=1)
    return _grad_from_t(t, stops)


def _scene_gradient(w, h, c0, c1, angle):
    """A 2-stop scene background gradient (numpy-vectorised — was a ~170ms pixel
    loop). Angle 0=→ (horizontal), 90=↓ (vertical)."""
    import numpy as np
    a = math.radians(angle)
    dx, dy = math.cos(a), math.sin(a)
    extent = abs(dx) * (w - 1) + abs(dy) * (h - 1) or 1
    ox = 0 if dx >= 0 else (w - 1)
    oy = 0 if dy >= 0 else (h - 1)
    tx = np.abs(np.arange(w, dtype="float32") - ox) * abs(dx)
    ty = np.abs(np.arange(h, dtype="float32") - oy) * abs(dy)
    t = np.clip((tx[None, :] + ty[:, None]) / extent, 0.0, 1.0)
    return _grad_from_t(t, [(0.0, c0), (1.0, c1)])


def _silhouette(canvas, box, mask, color, blur, alpha, dx=0, dy=0):
    """Composite a blurred coloured silhouette of ``mask`` onto ``canvas`` — the
    basis of both Shadow (dark, offset) and Glow (bright, large blur)."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    if mask.size != (w, h):
        mask = mask.resize((w, h))
    pad = int(blur * 3) + 2
    tile = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    col = Image.new("RGBA", (w, h), (*color[:3], alpha))
    tile.paste(col, (pad, pad), mask)
    if blur > 0:
        tile = tile.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(tile, (x0 - pad + int(dx), y0 - pad + int(dy)))


# ── material rendering ───────────────────────────────────────────────────────
def _material_tile(material, w, h, radius, fill, color):
    """Return an RGBA tile (the part's shape per its material) + the ink colour to
    draw icons/text in. Ghost returns a transparent tile (ink only)."""
    mask = _rrect_mask(w, h, radius)
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ink = color

    if material == "ghost":
        return tile, mask, color

    if material == "outline":
        d = ImageDraw.Draw(tile)
        d.rounded_rectangle([1, 1, w - 2, h - 2], radius=min(radius, h // 2),
                            outline=_rgba(fill), width=max(2, h // 22))
        return tile, mask, fill

    if material == "metal":
        grad = _vgrad(w, h, [(0.0, METAL_TOP), (0.18, METAL_TOP),
                             (0.5, METAL_MID), (1.0, METAL_BOT)]).convert("RGBA")
        tile.paste(grad, (0, 0), mask)
        d = ImageDraw.Draw(tile)
        r = min(radius, h // 2)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                            outline=_rgba(METAL_BORDER), width=max(1, h // 30))
        # inset bevel: bright top edge, dark bottom edge
        d.line([(r, 2), (w - r, 2)], fill=(255, 245, 210, 150), width=max(1, h // 40))
        d.line([(r, h - 3), (w - r, h - 3)], fill=(60, 40, 8, 120), width=max(1, h // 40))
        return tile, mask, METAL_INK

    # solid (default)
    shape = Image.new("RGBA", (w, h), _rgba(fill))
    tile.paste(shape, (0, 0), mask)
    return tile, mask, ink


def _apply_frosted(canvas, box, radius):
    """Frosted: blur the slice of the canvas behind the part, then overlay a
    translucent white fill + brighter border. Operates in place on the canvas."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    mask = _rrect_mask(w, h, radius)
    behind = canvas.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(FROST_BLUR))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r = min(radius, h // 2)
    od.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=FROST_FILL)
    od.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, outline=FROST_BORDER,
                         width=max(1, h // 28))
    behind = behind.convert("RGBA")
    behind.alpha_composite(overlay)
    canvas.paste(behind, (x0, y0), mask)


def _over_effect(tile, mask, eff, w, h):
    """Bevel / Scanline: drawn over the part shape, clipped to its mask."""
    name = eff.params.get("effect")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if name == "bevel":
        d.line([(2, 1), (w - 2, 1)], fill=(255, 255, 255, 90), width=max(1, h // 24))
        d.line([(2, h - 2), (w - 2, h - 2)], fill=(0, 0, 0, 110), width=max(1, h // 24))
    elif name == "scanline":
        a = int(eff.params.get("intensity", 0.18) * 255)
        for y in range(0, h, 3):
            d.line([(0, y), (w, y)], fill=(0, 0, 0, a), width=1)
    else:
        return
    layer.putalpha(Image.composite(layer.getchannel("A"),
                                   Image.new("L", (w, h), 0), mask))
    tile.alpha_composite(layer)


# ── icon / text / live readout ───────────────────────────────────────────────
def _resolve_icon(layer, live):
    if layer.params.get("dynamic") == "play_pause":
        return "pause" if live.get("media", {}).get("status") == "Playing" else "play"
    return layer.params.get("icon")


def _binding_text(part, live):
    src = (part.binding or {}).get("source")
    if not src:
        return None
    media = live.get("media", {})
    if src == "media.title":
        t, a = media.get("title", ""), media.get("artist", "")
        return f"{t} — {a}" if (t and a) else (t or a)
    if src == "media.artist":
        return media.get("artist", "")
    if src.startswith("cpu"):
        return f"CPU {int(live.get('cpu', 0))}%"
    if src.startswith("gpu"):
        return f"GPU {int(live.get('gpu', 0))}%"
    if src.startswith("clock"):
        return live.get("clock", "")
    return None


def _ellipsize(d, s, font, max_w):
    if not s or d.textlength(s, font=font) <= max_w:
        return s
    while s and d.textlength(s + "…", font=font) > max_w:
        s = s[:-1]
    return s + "…"


def _draw_centered_text(canvas, box, s, font, color):
    if not s:
        return
    d = ImageDraw.Draw(canvas)
    s = _ellipsize(d, s, font, box[2] - box[0] - 8)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    tb = d.textbbox((0, 0), s, font=font)
    d.text((cx - (tb[2] - tb[0]) / 2, cy - (tb[3] - tb[1]) / 2 - tb[1]),
           s, font=font, fill=_rgba(color))


def _draw_icon_layer(canvas, box, part, ink, live):
    layer = part.icon_layer()
    text = _binding_text(part, live)
    mono = part.type in ("label", "readout")
    if text is not None:                          # live-bound text wins
        size = (layer.params.get("size") if layer else 22)
        _draw_centered_text(canvas, box, text, _font(size, mono=mono), ink)
        return
    if not layer:
        return
    icon = _resolve_icon(layer, live)
    if icon:
        x0, y0, x1, y1 = box
        # square the icon box around the centre so glyphs aren't stretched
        side = min(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ibox = (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
        if icons.draw_icon(ImageDraw.Draw(canvas), icon, ibox, _rgba(ink)):
            return
    label = layer.params.get("label", "")
    if label:
        _draw_centered_text(canvas, box, label, _font(layer.params.get("size", 26), mono),
                            ink)


# ── slider (its own track / fill / knob) ─────────────────────────────────────
def _slider_frac(part, live):
    src = (part.binding or {}).get("source")
    if src == "media.position":
        m = live.get("media", {})
        if m.get("length"):
            return _clamp01((m.get("position") or 0) / m["length"])
    return _clamp01(live.get("frac", 0.4))


def _draw_slider(canvas, box, part, live):
    x0, y0, x1, y1 = box
    h = y1 - y0
    midy = (y0 + y1) / 2
    th = max(6, h * 0.34)
    track = part.color           # converter stores the track colour here
    accent = part.fill           # …and the accent/fill colour here
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([x0, midy - th / 2, x1, midy + th / 2], radius=th / 2,
                        fill=_rgba(track))
    frac = _slider_frac(part, live)
    if frac > 0:
        d.rounded_rectangle([x0, midy - th / 2, x0 + (x1 - x0) * frac, midy + th / 2],
                            radius=th / 2, fill=_rgba(accent))
    kx = x0 + (x1 - x0) * frac
    kr = h * 0.36
    d.ellipse([kx - kr, midy - kr, kx + kr, midy + kr], fill=_rgba(accent),
              outline=(255, 255, 255, 255), width=2)


# ── motion: sweep band (Drift/Breathe/Flicker handled via motion.motion_offset) ─
def _draw_sweeps(tile, mask, part, t, w, h):
    """Draw any Sweep bands (a travelling specular highlight) clipped to the shape."""
    bands = motion.sweeps(part, t)
    if not bands:
        return
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for centre, width, intensity in bands:
        cx = centre * w
        bw = max(2, width * w)
        a = int(intensity * 150)
        d.rectangle([cx - bw / 2, 0, cx + bw / 2, h], fill=(255, 255, 255, a))
    layer = layer.filter(ImageFilter.GaussianBlur(max(1, w // 200)))
    layer.putalpha(Image.composite(layer.getchannel("A"),
                                   Image.new("L", (w, h), 0), mask))
    tile.alpha_composite(layer)


def _scale_alpha(tile, mul):
    """Scale an RGBA tile's alpha channel by ``mul`` (0..1) — used for breathe/flicker."""
    if mul >= 0.999:
        return tile
    a = tile.getchannel("A").point(lambda v: int(v * mul))
    tile.putalpha(a)
    return tile


# ── the main render ──────────────────────────────────────────────────────────
def _paint_background(layers, w, h):
    """Paint the scene background surface (Solid / Gradient; others → solid base)."""
    base = (0, 0, 0)
    img = Image.new("RGB", (w, h), base)
    for layer in layers:
        if layer.kind != "background":
            continue
        p = layer.params
        btype = p.get("type", "solid")
        c0 = tuple(p.get("color", [0, 0, 0])[:3])
        if btype == "gradient":
            c1 = tuple(p.get("color2", p.get("color", [0, 0, 0]))[:3])
            img = _scene_gradient(w, h, c0, c1, float(p.get("angle", 0)))
        else:                                  # solid / motion / texture / image → solid
            img = Image.new("RGB", (w, h), c0)
    return img.convert("RGBA")


def _eff_intensity(eff, part, dynamics, now, motion_alpha, base):
    """An effect's live intensity: its base, scaled by the layer's timing envelope
    (press-flare, breathe, …) and by continuous-motion alpha. ``dynamics`` may be
    None (still render) → envelope multiplier is 1.0."""
    inten = float(eff.params.get("intensity", base))
    if dynamics is not None:
        inten *= dynamics.layer_value(part.id, eff, now)
    return inten * motion_alpha


def render_scene(scene, geometry, live=None, theme=None, t=0.0, dynamics=None):
    """Render one ``Scene`` to a PIL RGB image at the strip's true resolution.

    ``t`` (seconds) drives continuous motion; ``dynamics`` (a ``motion.Dynamics``)
    drives per-layer timing envelopes. Both default to a static frame."""
    live = live or {}
    theme = theme or {}
    w = int(geometry.get("width", 2170))
    h = int(geometry.get("height", 60))
    margin = int(geometry.get("margin", 10))
    gap = int(geometry.get("gap", 10))

    canvas = _paint_background(scene.background, w, h)
    pressed_id = live.get("pressed")

    for part, box in layout_parts(scene.parts, w, h, margin, gap):
        if part.type == "spacer":
            continue
        dx, dy, malpha = motion.motion_offset(part, t)
        x0, y0, x1, y1 = box
        box = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)

        if part.type == "slider":
            for eff in part.effects():               # glow under the slider
                inten = _eff_intensity(eff, part, dynamics, t, malpha, 0.6)
                _slider_effects(canvas, box, eff, part, inten)
            _draw_slider(canvas, box, part, live)
            continue

        ix0, iy0, ix1, iy1 = (int(round(v)) for v in box)
        pw, ph = ix1 - ix0, iy1 - iy0
        if pw <= 0 or ph <= 0:
            continue
        radius = part.radius
        fill = part.fill
        color = part.color
        if pressed_id and part.id == pressed_id and theme.get("pressed"):
            fill = theme["pressed"].get("fill", fill)
            color = theme["pressed"].get("color", color)

        mask = _rrect_mask(pw, ph, radius)

        # under-effects: shadow first (lowest), then glow
        for eff in sorted(part.effects(),
                          key=lambda e: 0 if e.params.get("effect") == "shadow" else 1):
            name = eff.params.get("effect")
            if name == "shadow":
                inten = _eff_intensity(eff, part, dynamics, t, malpha, 0.55)
                _silhouette(canvas, (ix0, iy0, ix1, iy1), mask, (0, 0, 0),
                            blur=eff.params.get("blur", 6), alpha=int(inten * 255),
                            dx=eff.params.get("dx", 0), dy=eff.params.get("dy", 3))
            elif name == "glow":
                inten = _eff_intensity(eff, part, dynamics, t, malpha, 0.7)
                if inten > 0.01:
                    _silhouette(canvas, (ix0, iy0, ix1, iy1), mask,
                                eff.params.get("color", fill),
                                blur=eff.params.get("blur", 12), alpha=int(inten * 255))

        # the material shape
        if part.material == "frosted":
            _apply_frosted(canvas, (ix0, iy0, ix1, iy1), radius)
            ink = color
        else:
            tile, mask, ink = _material_tile(part.material, pw, ph, radius, fill, color)
            for eff in part.effects():               # over-effects clipped to shape
                if eff.params.get("effect") in ("bevel", "scanline"):
                    _over_effect(tile, mask, eff, pw, ph)
            _draw_sweeps(tile, mask, part, t, pw, ph)
            _scale_alpha(tile, malpha)
            canvas.alpha_composite(tile, (ix0, iy0))

        _draw_icon_layer(canvas, (ix0, iy0, ix1, iy1), part, ink, live)

    return canvas.convert("RGB")


def _slider_effects(canvas, box, eff, part, intensity=None):
    """A glow under the slider's filled portion (sliders have no rect shape)."""
    name = eff.params.get("effect")
    if name != "glow":
        return
    inten = eff.params.get("intensity", 0.6) if intensity is None else intensity
    if inten <= 0.01:
        return
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    midy = (y0 + y1) // 2
    th = max(6, (y1 - y0) // 3)
    gy0 = midy - th // 2
    mask = _rrect_mask(x1 - x0, th, th // 2)
    _silhouette(canvas, (x0, gy0, x1, gy0 + th), mask,
                eff.params.get("color", part.fill), blur=eff.params.get("blur", 10),
                alpha=int(inten * 255))


# ── config-level convenience + hit-testing ───────────────────────────────────
def compose(cfg, live=None, scene=None, t=0.0, dynamics=None):
    """Render the active scene of a ``SceneConfig`` (or a named/given scene)."""
    from . import scenes as scene_mod
    if scene is None:
        scene = scene_mod.resolve_active(cfg, live or {})
    theme = (cfg.library or {}).get("legacyTheme", {})
    return render_scene(scene, cfg.geometry, live or {}, theme=theme, t=t,
                        dynamics=dynamics)


def hit_test(scene, geometry, px):
    """Return ``(part, fraction)`` for the part under x=``px`` (for touch routing)."""
    w = int(geometry.get("width", 2170))
    h = int(geometry.get("height", 60))
    margin = int(geometry.get("margin", 10))
    gap = int(geometry.get("gap", 10))
    for part, box in layout_parts(scene.parts, w, h, margin, gap):
        if part.type == "spacer":
            continue
        if box[0] <= px <= box[2]:
            frac = (px - box[0]) / max(1, box[2] - box[0])
            return part, frac
    return None, None
