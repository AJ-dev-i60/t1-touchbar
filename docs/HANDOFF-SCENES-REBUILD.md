# t1bar studio — "Scenes / Layer Loom" rebuild — transferable handoff

**This document is written for a fresh, dedicated coding session** that will build the new
t1bar-studio concept. It is self-contained: read this + the design package in
`docs/design-scenes/` and you have everything. The original session that produced this is
staying focused on the **driver / core hardware** work and is intentionally *not* doing this
rebuild.

---

## 0. The mandate (read first)

Rebuild **t1bar studio** to the approved concept in `docs/design-scenes/` (the "Scenes / Layer
Loom" direction). This is a **near-total rewrite of the app plus a real engine expansion** — not
a UI reskin. Two previous attempts produced conventional "live-preview + inspector + side-rails"
editors and were rejected as "a polished version of what we had." **Do not** rebuild that. Build
the Scenes concept.

**Hard rule:** do not break the working driver, the live Touch Bar, the camera/face-login, or the
boot services. Develop the new engine in NEW modules and test headless; only swap the live service
over once the new runtime is proven. The current app keeps working until then.

---

## 1. What the product is (one paragraph)

t1bar studio is a **native Linux desktop app** for designing what lives on a MacBook's **Touch
Bar** (a ~**2170×60 px, ~36:1** touch-sensitive OLED strip) while running Linux. A background
service renders the design onto the **real hardware and hot-reloads within ~1s of any edit** —
that live-on-hardware immediacy is the emotional core. The user composes a **personal, contextual
control surface**: its look, its controls/readouts, and how it changes with what they're doing.

---

## 2. The approved concept (the thing to build)

Full design package is in **`docs/design-scenes/`**:
- `CONCEPT-README.md` — the authoritative concept spec (read in full).
- `concept.dc.html` + `support.js` — the visual concept doc (open in a browser:
  `google-chrome --headless=new --screenshot=out.png --window-size=1400,7200 file://.../concept.dc.html`,
  it's a self-painting "design component"; `support.js` must sit beside it).
- `slices/01..04*.png` — pre-rendered screenshots of the concept (look at these first for the feel).

### The six locked decisions
1. **Spine = Scenes.** You don't design *a* strip; you define **situations** and what the strip
   becomes in each. Scenes resolve **top-down by priority** over an always-on **"Always" base**.
   Active scene = highest-priority scene whose **trigger** is currently true. **Live data updates
   *inside* a scene without swapping it.** (e.g. scenes: *Watching* `when media playing`, *Coding*
   `when editor focused`, *Gaming* `when game focused`, *Always* `base`.)
2. **One app, two altitudes: Compose ⇄ Craft.** No separate studio app; depth is *revealed* (open
   a part to go deeper), not relocated.
3. **Designer = Layer Loom.** A part's look is a **draggable stack of layers**
   (Background → Texture → Material → Icon → Effect → Motion, back→front). Reorder = restack.
   **Any layer can carry a timing envelope** (e.g. on-press flare that fades back over 600ms).
4. **Arranging = Auto-flow.** Parts **snap into slots** along the strip and are **reordered by
   drag** — no pixel positioning on the 36:1 ribbon. Each part is **fixed-width or stretchy**.
5. **Finite kit + import-by-spec.** Curated finite vocabulary; power users **import** custom
   icons/textures/effects conforming to a **spec**, each becoming another stackable/timeable layer.
   Whole scenes package into shareable **scene packs**.
6. **Chrome = neutral graphite, native dark.** App UI is grayscale; **color appears only on the
   strip being designed.** Live/active status = green `#46c479`.

### The finite kit (vocabulary)
- **Content parts (6):** Key, Transport, Slider, Readout(live), Label, Spacer.
- **Backgrounds (5):** Solid, Gradient, Motion, Texture, Image(import).
- **Materials (5):** Solid, Frosted (blur/translucent over bg), Outline, Ghost (icon/text only),
  Metal (beveled).
- **Effects (5, stackable):** Glow, Bevel/3D, Scanline, Shadow, Ripple.
- **Motion (4) + Timing envelope:** Drift, Breathe, Flicker, Sweep; envelope = `hold · decay ·
  curve` (linear/ease-out/spring) available on **any** layer.
- Principle: *5 materials × 5 backgrounds × stacked effects × per-layer timing → effectively
  unbounded, yet every piece is a known, supported block.*

### The six views (map to native GTK views/regions; reinvent the chrome, honor the IA)
1. **Scene Home (the spine)** — gallery of **scene cards** (each: name, priority, one-line
   trigger, a **mini live preview of that scene's strip**, "● active" emphasis on the live one);
   a persistent **"Live: <scene> — because <why>"** indicator. Create/prioritize(stack)/select;
   drag a trigger onto a card to bind it.
2. **Scene editor — Auto-flow** — full-width strip with parts in **slots** + a **part tray** to
   drop from; drag to reorder; per-part fixed/stretchy; tap a part → opens the Designer; parts can
   bind to a live source (`media.position`, `cpu.percent`, `build.status`, clock).
3. **Designer — Layer Loom (Craft)** — large **magnified part preview** with **idle/hover/pressed**
   state tabs + a **vertical layer stack** (drag handle, thumbnail, label, timing-envelope badge);
   "+ add layer"; imported assets show an "imported ↧" marker.
4. **Background & Materials** — the scene **background** (sibling surface, never a parent of parts)
   + per-part **material** (the single knob relating a part to the background behind it).
5. **The Kit** — vocabulary reference (the lists above).
6. **Extend** — import-by-spec (Icon: SVG/PNG square, safe-area, tint-able; Texture: tileable
   sRGB seamless; Effect: declares params the kit can drive) + **scene packs** (one shareable file).

### Art direction / tokens (chrome — honor; full list in CONCEPT-README §Design Tokens)
Graphite dark: page `#0b0b0d`, surfaces `#161618`/`#1d1d20`/`#101012`, hairlines white @6–8%,
text `#ededef`/`#9a9aa0`/`#6a6a72`, **green status accent `#46c479`** only. Card radius ~11–14,
pills 999. **Color only on the strip.** UI font = system/Cantarell; **mono labels = Space Mono**
(uppercase eyebrows ~11px, letter-spacing ~0.22em). Strip/material example tokens (Metal gradient,
Frosted rgba, etc.) are in the README.

---

## 3. Engine implications (the hard, non-obvious part)

The concept is **much** more than a new layout. It needs:

- **New config schema** (replaces today's `theme`/`layouts`/`items`/`rules`). Suggested model
  (from README §State Management):
  - `scenes[]`: `{ id, name, priority, trigger, background(layer stack), parts[] }`
  - `alwaysScene` (priority-0 base), `activeSceneId` (derived from live state + priority)
  - `part`: `{ id, type, widthMode: fixed|stretchy, binding?, layers[], material }`
  - `layer`: `{ id, kind, params, envelope? }`; `envelope = { trigger, holdMs, fadeMs, curve }`
  - `material`: one of Solid/Frosted/Outline/Ghost/Metal (part-level)
  - `library`: imported icons/textures/effects + saved parts + installed scene packs
  - `liveState`: focused app, media, cpu/gpu, clock (fed by the context service)
- **A layered/material compositor** to *replace* the current simple `render.py`. It must composite,
  per part: a **layer stack** (background/texture/material/icon/effect/motion) with **materials**
  (Frosted needs blur of what's behind; Metal needs bevel gradients; Ghost = icon/text only;
  Outline; Solid) and **stackable effects** (Glow/Shadow/Scanline/Bevel/Ripple), over a **scene
  background surface** (Solid/Gradient/Motion/Texture/Image). PIL is the current renderer; for
  blur/gradients/bevels you may want Cairo/`Pillow` filters, or move compositing to Cairo to match
  the GSK/Cairo direction. Output is a 2170×60 frame.
- **Scene resolution** by trigger + priority over the Always base — extend `context.py`. Triggers
  available now: **media playing** (works via playerctl). **Focused-app** needs a tiny **GNOME
  Shell extension** reporting the focused app over D-Bus on Wayland (NOT built yet — design the
  rules so it slots in). **cpu/gpu/fps/clock** readouts: cpu/clock easy; gpu/fps need sources.
- **Animation loop.** Motion (Drift/Breathe/Flicker/Sweep) and timing envelopes mean the runtime
  must render **at a frame rate** (e.g. 30–60fps while a motion/active envelope is live), not just
  on config change. **Performance matters**: pushing full 2170×60 frames over the USB bulk pipe
  continuously has a cost — measure it; consider dirty-region or rate-capping; idle scenes with no
  motion can stay event-driven. This is the riskiest engineering item — prototype it early.
  **→ MEASURED & answered in `docs/HARDWARE-FRAME-PUSH-REFERENCE.md`** (full-frame push is ~90 fps /
  ~11 ms, USB-bound; keep it synchronous; cap motion at 30 fps event-driven; dirty-rect is
  protocol-native but unverified; service-restart re-lights the panel — read it before building the
  motion runtime).
- **Live bindings** update *within* a scene (scrubber position, cpu%, fps, build status, clock)
  without swapping scenes.

**Recommendation:** build the new engine as NEW modules (e.g. `model.py`, `compose.py`,
`scenes.py`, `motion.py`) alongside the existing `render.py`/`runtime.py`, with a **converter**
from the current `config.json` → a starter scenes config. Prove it **headless** (render each scene
to PNG; render a short motion sequence to a few PNGs) before touching the live service.

---

## 4. Current state you're building on / replacing

The app today works end-to-end (the "unified model"): a boot service drives the bar from a config
the editor live-edits. You are reimagining the **editor and the engine**, keeping the live loop.

- **Repo:** `/home/armandt/touchbar-port/t1bar-studio/` — local git repo, package `t1bar_studio`,
  console `t1bar` (subcommands `run`/`render`/`edit`). **Editable install** (changes to `src/` are
  live; `/usr/local/bin/t1bar` is the wrapper). **NOT pushed to GitHub** (the driver repo is
  `github.com/AJ-dev-i60/t1-touchbar`, gh authed as `AJ-dev-i60`; t1bar-studio is local-only).
- **Current schema** (`configs/default.json`, and the live canonical config
  `~/.config/t1bar/config.json`): `{ version, theme{background,button{fill,text,radius,font_size},
  pressed,accent,track,gap,margin}, layouts{<name>{items[]}}, rules[] }`. Items: button/scrubber/
  label/spacer. This is what your **converter** reads.
- **Current modules:** `config.py` (load + DEFAULT_THEME deep-merge + `Hot` mtime watcher),
  `render.py` (simple L→R weighted compositor — see it for boxes()/hit() you'll reimplement),
  `context.py` (MPRIS `MediaWatcher` via playerctl + `pick_layout` rule eval), `runtime.py`
  (Device + TouchReader + MediaWatcher loop, render-signature change detection, **hot-reload**),
  `actions.py` (uinput key emit + media/seek), `icons.py` (vector glyphs), `editor_gtk.py` (the
  current GTK editor — the one being replaced).
- **Current editor (`editor_gtk.py`)** is the rejected "Combined main window" (hero preview + left
  rail layouts/rules + center inspector + right palette). Keep it runnable until the new app
  replaces it, or branch. It has a useful **`--shot PATH` screenshot mode** (+ env overrides
  `T1BAR_SHOT_MODE/LAYOUT/PLAYING`) you can copy for verifying your new UI headlessly.

---

## 5. Operational recipes (you will need these constantly)

- **Headless render of a config to PNG (current engine):**
  `t1bar render -c ~/.config/t1bar/config.json -l default [--playing] -o out.png` — build the
  equivalent for the new engine first; it's the fast dev loop (no hardware needed).
- **Launch the GTK GUI as the user** (gnome-shell's own environ lacks DISPLAY/WAYLAND — use these
  literals):
  ```
  sudo -u armandt env DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus t1bar edit -c ~/.config/t1bar/config.json
  ```
  Launched detached it keeps the stdout pipe open — redirect output or use `timeout` when scripting.
- **Self-screenshot the GUI** (only reliable Wayland method; gnome-screenshot hangs, `import`
  can't grab Wayland): the editor renders its own widget tree via `Gtk.WidgetPaintable` →
  `tex.save_to_png`. See `editor_gtk.py` `App._save_shot`. Use this to verify your new UI.
- **Render the concept HTML** for reference: see §2.
- **Toolkit:** GTK4 + libadwaita + PyGObject on **Python 3.14** (Qt/PySide6 has NO 3.14 wheels —
  don't suggest them). PIL/Pillow available. `cairo` foreign-struct needs `import cairo` +
  `apt python3-gi-cairo` (installed). Custom drawing via `Gtk.DrawingArea`+Cairo or GSK snapshots.
  `Gtk.ColorDialogButton`, `Adw.*` rows available. Fonts: **Inter** installed; **Space Mono** is
  NOT — `apt install fonts-spacemono` (or bundle) if you use it. `google-chrome` is available.

---

## 6. The live system — do NOT break it (owned by the other session)

The hardware/driver/service stack is working and managed by the core session. Coordinate; don't
disturb it:

- The Touch Bar is **single-owner** (USB **config 2**, interface IF3, needs root). Only one process
  drives it at a time. **`t1bar.service`** (`t1bar run -c ~/.config/t1bar/config.json`) currently
  owns it at boot; the camera service + Howdy face-login depend on config 2 being held.
- **Live hot-reload:** `runtime.py` polls the config file mtime and re-renders on change — this is
  the live-edit loop the editor relies on. Your new runtime must preserve an equivalent loop (and
  add the animation tick).
- To develop the new runtime without fighting the live one: test **headless** (render to PNG); when
  ready to drive hardware, `sudo systemctl stop t1bar.service` first (frees the device), run your
  new runtime, and restore with `sudo systemctl start t1bar.service t1touchbar-camera.service`
  after. The reversible installer/uninstaller live in `packaging/` (install-service.sh /
  uninstall-service.sh) — the swap to the new runtime should follow that pattern.
- Device facts: 2170×60, 24bpp BGR888 over a USB bulk pipe; the DFR protocol details + the whole
  driver story are in the memory file `t1-touchbar-driver-port-project` and
  `t1-touchbar-dfr-custom-pixels`.

---

## 7. Suggested phased roadmap (multi-session)

1. **Engine foundation (headless).** New schema + converter from the current config; the
   layered/material compositor (start: Solid/Outline/Ghost/Metal/Frosted + Glow/Shadow over
   Solid/Gradient backgrounds); render the example scenes to PNG. *No hardware risk.*
2. **Motion + live runtime.** Animation tick (Drift/Breathe/Flicker + envelopes); live bindings;
   scene resolution over Always base. Prove a short motion sequence headless, then drive hardware
   behind a service swap (keep the old runtime as fallback). Measure USB frame-push cost.
3. **Scene Home** (the spine) — graphite chrome, scene cards w/ live mini-renders, the live
   indicator, create/prioritize/select, trigger binding.
4. **Scene editor — Auto-flow** — slots + part tray + drag-reorder + fixed/stretchy + live binding.
5. **Layer Loom + Background & Materials** — magnified part preview w/ state tabs, draggable layer
   stack, envelopes; background editor + material picker.
6. **The Kit + Extend** — vocabulary surfaces; import-by-spec + scene packs.

Build each phase, verify headless/with `--shot`, commit, then move on. Don't try to land it all at
once.

---

## 8. Conventions

- Commit as `AJ-dev-i60 <armandt@cloudnexus.co.za>` (the repo's existing author). Clear,
  explanatory commit bodies (see git log for the house style).
- t1bar-studio is **local-only** (not on GitHub). Ask the user before pushing anywhere.
- This machine: Ubuntu-ish, Python 3.14, Wayland/GNOME, user `armandt`, passwordless sudo for
  Claude. The owner is design-conscious and wants **genuinely fresh, Apple-grade native** results —
  he rejected two conventional editors, so bias toward the bold concept, not safe patterns.

---

## 9. First moves for the new session

1. Read `docs/design-scenes/CONCEPT-README.md` fully + look at `docs/design-scenes/slices/*.png`.
2. Skim the current `src/t1bar_studio/{config,render,context,runtime}.py` to know what you convert
   from and the live loop you preserve.
3. Start **Phase 1**: draft the new schema + a converter from `~/.config/t1bar/config.json`, and a
   first-cut `compose.py` that renders one scene (Solid material over a Solid/Gradient background) to
   a 2170×60 PNG. Get *something* from the new model on screen headlessly, then iterate materials/
   effects, then motion, then the GUI.
4. Keep the live bar working the whole time (develop headless; swap the service only when proven).
