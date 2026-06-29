# Scenes / Layer Loom rebuild — Phase 1 (engine foundation, headless)

Status: **done & verified headless.** Builds on `docs/HANDOFF-SCENES-REBUILD.md`
(roadmap §7 step 1). No hardware touched; the live `t1bar.service` and legacy
`render.py`/`runtime.py`/`editor_gtk.py` are entirely untouched and still work.

## What landed (new modules, alongside the legacy engine)

- **`model.py`** — the new Scenes schema as forgiving dataclasses with lossless
  `to_dict`/`from_dict` round-trip and `load`/`save`:
  `SceneConfig → scenes[] / always → Scene → parts[] → Part → layers[] → Layer
  (+ Envelope, Trigger, Material)`. Vocabulary constants for the finite kit
  (PART_TYPES, MATERIALS, LAYER_KINDS, BACKGROUND_TYPES, EFFECTS, MOTIONS, CURVES).
  `is_scene_config()` distinguishes a new config from a legacy one; `ensure_ids()`
  stamps stable ids for the GUI.
- **`convert.py`** — legacy `theme/layouts/items/rules` → a starter Scenes config.
  Each rule becomes a scene (top rule = highest priority); the catch-all rule becomes
  the **Always** base (priority 0); items become parts with a real starter Layer Loom
  (a background layer + an icon layer). `theme.accent/track/pressed` are preserved in
  `library.legacyTheme` so nothing is lost.
- **`compose.py`** — the layered / material compositor that *replaces* `render.py`.
  Scene background surface (Solid / Gradient; Motion/Texture/Image fall back to solid
  for now). Auto-flow slot layout (`layout_parts`): fixed parts take an intrinsic
  width, stretchy parts share the remaining ribbon by weight (falls back to legacy
  weighted split when there are no stretchy parts). Per-part **materials**
  (Solid / Outline / Ghost / Metal / Frosted) + stackable **effects** (Glow / Shadow
  under, Bevel / Scanline over) + the icon/label/live-readout layer. Sliders draw
  their own track/fill/knob. `hit_test()` mirrors the layout for touch routing.
  `t` (seconds) is threaded through for Phase 2 motion (a couple of motion kinds are
  already wired so `t` genuinely changes the frame).
- **`scenes.py`** — `resolve_active(cfg, live)` / `resolve_with_reason(cfg, live)`:
  highest-priority scene whose trigger matches over the Always base. `media` and
  `always` triggers evaluate today (via the existing MPRIS watcher's status);
  `app`/`stat`/`clock` are wired to evaluate false until their sources land.

## New CLI (headless dev loop — no hardware)

```
t1bar convert -c ~/.config/t1bar/config.json -o configs/scenes-default.json
t1bar scene-render -c configs/scenes-default.json -s default  -o always.png
t1bar scene-render -c configs/scenes-default.json --playing   -o active.png   # resolves to Watching
t1bar scene-render -c configs/scenes-showcase.json            -o showcase.png  # gradient + all 5 materials + glow
```

`scene-render` flags: `-s/--scene` (default: the active scene for the faked state),
`--playing`, `--frac`, `-t/--time`.

## Example configs committed

- `configs/scenes-default.json` — the converted live config (Watching p2 over Always p0).
- `configs/scenes-showcase.json` — a hand-built scene exercising the full engine:
  angled gradient background + Solid/Frosted/Outline/Ghost/Metal materials + Glow/Shadow
  + a stretchy glowing slider.

## Verified

- Model round-trips losslessly (`to_dict → from_dict → to_dict` identical).
- Converter turns the live config into 2 scenes; resolution picks Watching when media
  is "playing", else Always.
- Both render at true **2170×60**; the media scene matches the concept hero (transport
  keys · mono title · big stretchy scrubber · volume keys).
- The showcase renders all five materials as visually distinct surfaces over a gradient.
- Legacy `t1bar render` still works; all new modules import cleanly; motion `t` changes frames.

## Known Phase-1 simplifications (for later phases)

- Compositing is **canonical** (material shape → effects → icon), not literal
  back→front layer-array order. Honors stacking among effects; full free-form layer
  ordering is a Phase 5 (Layer Loom) concern.
- Backgrounds: only Solid/Gradient are real; Motion/Texture/Image fall back to solid.
- Effects: Glow/Shadow/Bevel/Scanline implemented; **Ripple** is a no-op (motion-driven,
  Phase 2). Timing **envelopes** are parsed/stored but not yet driven.
- Fonts: DejaVu (mono fallback). Space Mono is not installed — `apt install fonts-spacemono`
  when the GUI/labels want it.
- Renderer is PIL. Cairo/GSK can replace `compose.py` internals later without changing
  its public surface.

## Next (roadmap §7 step 2): Motion + live runtime

Animation tick driving Drift/Breathe/Flicker/Sweep + timing envelopes; live bindings
within a scene; a new runtime that resolves scenes over the Always base and pushes
frames — proven headless first, then a service swap with the old runtime as fallback.
Measure USB frame-push cost before going continuous.
