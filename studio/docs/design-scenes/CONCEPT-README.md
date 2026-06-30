# Handoff: t1bar studio — core experience concept

## Overview
**t1bar studio** is a native Linux desktop app for designing what lives on a MacBook's
Touch Bar (a ~2170×60px, ~36:1 OLED strip) while running Linux. The user composes a
personal, contextual control surface — its look, its controls/readouts, and how it changes
with what they're doing — and every edit appears on the *real* hardware within ~1 second.

This package documents the **agreed core-experience concept** decided during a design
session. It is the direction to build toward, not a finished screen-by-screen spec.

## About the Design Files
The file in this bundle (`t1bar studio — Concept.dc.html`) is a **design reference created
in HTML** — a single concept document that communicates the intended interaction model,
information architecture, and visual feel. **It is not production code and must not be
shipped or embedded.**

The hard platform constraint: this product is a **native Linux desktop application built in
GTK4 / libadwaita with custom drawing (Cairo / GSK snapshots)**. There is **no web, no
browser, no embedded web view**. The task is to **recreate the intent of these designs as a
native GTK4 app**, using libadwaita patterns for chrome (windows, headerbars, sidebars,
dialogs) and custom-drawn widgets for the strip canvas and the layer/effect surfaces. Treat
the HTML purely as a visual + behavioral reference.

## Fidelity
**Low-to-mid fidelity / concept.** This is a concept document, not a pixel-perfect mockup.
- Use it as the source of truth for **structure, interaction model, IA, and overall feel**.
- The dark "graphite, native, the-strip-is-the-only-color" art direction is intentional and
  should be honored, but exact paddings/radii are illustrative — apply native libadwaita
  spacing and the platform's HIG rather than copying pixel values.
- The **strip mockups** (colors, materials, glow) represent how the *designed object* should
  look on hardware; the **app chrome** should be neutral graphite and unmistakably native.

## Core Concept (read this first)
Six locked decisions define the product:

1. **Spine = Scenes.** The user doesn't design *a* strip; they define **situations** and what
   the strip becomes in each. Scenes resolve **top-down by priority** over an always-on
   **"Always" base** scene. The active scene is whichever highest-priority trigger is currently
   true. **Live data updates *inside* a scene without swapping it.**
2. **One app, two altitudes: Compose ⇄ Craft.** No separate "studio" app. Depth is *revealed*
   (open a part to go deeper), not relocated to another program.
3. **Designer = Layer Loom.** A part's look is a **draggable stack of layers** (background →
   texture → material → icon → effects → motion). Reorder = restack. **Any layer can carry a
   timing envelope** (e.g. on-press flare that fades back over 600ms).
4. **Arranging = Auto-flow.** Parts **snap into slots** along the strip and are **reordered by
   drag** — no pixel positioning on the 36:1 ribbon. Each part declares fixed-width or stretchy.
5. **Finite kit + import-by-spec.** A curated, finite vocabulary of blocks anyone can layer.
   Power users **import** custom icons/textures/effects that conform to a **spec**; each becomes
   just another stackable, timeable layer. Whole scenes package into **shareable scene packs**.
6. **Chrome = neutral graphite, native dark.** The app UI is grayscale; **color appears only on
   the strip being designed.**

## Screens / Views
The concept is presented as one scrolling document with six sections. In the native app these
map to the following views/regions.

### 1. Scene Home (the spine)
- **Purpose:** Browse, create, prioritize, and select scenes; see which one is live right now.
- **Layout:** A gallery/grid of **scene cards** (concept shows a 2-col grid; native can be a
  flow grid). A persistent **"Live: <scene>" indicator** at the top states the active scene and
  *why* (e.g. "because mpv is focused & media is playing").
- **Each scene card contains:**
  - Scene name (e.g. Watching, Coding, Gaming) + a **priority** label and (for the base)
    an "Always · base" tag.
  - A **mini live preview of that scene's strip** (dark strip with that scene's parts).
  - A one-line **trigger** description ("when ▶ media playing", "when ⌨ editor focused",
    "when 🎮 game focused", "always on").
  - The **currently-active** card is emphasized (green accent ring/border + "● active").
- **Behavior:** Tap a card to open/edit it. Dragging a trigger onto a card binds its situation.
  Stacking/ordering sets priority. The active card updates automatically as real machine state
  changes (focused app, media state, GPU load, etc.).

### 2. Scene editor — Auto-flow arrangement
- **Purpose:** Decide *what* sits on the strip for a given scene and in what order.
- **Layout:** A full-width representation of the strip with parts in **slots**. A **part tray**
  below offers part types to drop in.
- **Part types (Content kit, 6):** `Key`, `Transport`, `Slider`, `Readout (live)`, `Label`,
  `Spacer`. Readouts that are bound to live data show a small green "live" dot.
- **Behavior:** Drop a part → it snaps into a slot. Drag to reorder. Each part is fixed-width or
  **stretchy** (e.g. the scrubber stretches). A part can be **bound to a live data source**
  (e.g. `media.position`, `cpu.percent`, `build.status`). Tapping a part opens the Designer.

### 3. Designer — Layer Loom (Craft altitude)
- **Purpose:** Craft the *look* of a single part by stacking layers.
- **Layout:** Two regions — a large **magnified preview** of the part on the left (with
  state tabs: idle / hover / pressed), and a **vertical layer stack** on the right.
- **Layer types, top (front) → bottom (back):** `Motion`, `Effect`, `Icon`, `Material`,
  `Texture`, `Background`. "+ add layer" appends.
- **Each layer row:** a drag handle (⠿), a swatch/thumbnail, a label, and — when present — a
  **timing envelope** badge (e.g. "⧖ on press → flare, fade 600ms").
- **Behavior:** Drag to reorder (changes stacking). Imported assets (e.g. an icon set) appear as
  normal layers with an "imported ↧" marker. Editing a layer reveals its parameters.

### 4. Background & Materials
- **Purpose:** Design the scene **background** (a sibling surface, never a parent of the parts)
  and choose how parts sit on it via **material**.
- **Materials (5):** `Solid`, `Frosted` (blur/translucent over background), `Outline`, `Ghost`
  (text/icon only), `Metal` (beveled). The material is the single knob that relates a part to
  whatever background is behind it — e.g. *moving gradient + Frosted parts* vs *black background
  + Solid colored parts*.
- **Background layers (5):** `Solid`, `Gradient`, `Motion`, `Texture`, `Image (imported ↧)`.

### 5. The Kit (vocabulary reference)
The complete finite vocabulary the app ships with:
- **Backgrounds (5):** Solid, Gradient, Motion, Texture, Image(import).
- **Effects (5, stackable):** Glow, Bevel/3D, Scanline, Shadow, Ripple.
- **Motion + Timing:** Drift, Breathe, Flicker, Sweep, and an envelope (`hold · decay · curve`)
  available on any layer.
- **Materials (5):** see above.
- **Content (6):** Key, Transport, Slider, Readout(live), Label, Spacer.
- Principle: *5 materials × 5 backgrounds × stacked effects × per-layer timing → effectively
  unbounded results, every piece a known/supported block.*

### 6. Extend — Import-by-spec & Scene Packs
- **Scene Pack:** one downloadable file bundling background+texture layers, parts (material +
  effects baked in), imported icon sets/textures, and triggers/bindings. **Import** drops it into
  the user's library to use or remix. This enables community sharing.
- **Import spec (so the system can understand custom assets):**
  - **Icon:** SVG/PNG, square, with safe-area inset, tint-able (mono variant).
  - **Texture:** tileable, sRGB, seamless edges, within a max px budget.
  - **Effect:** declares its parameters/slots the kit can drive — color, intensity, time.
- The import seam sits **at the edge** of the experience, never between the user and the live
  hardware.

## Interactions & Behavior
- **Live-on-hardware loop:** any edit pushes to the physical strip within ~1s. This immediacy is
  the product's emotional core — make the feedback loop tight and visible.
- **Context resolution:** a background service watches machine state (focused app, media
  playback, CPU/GPU load, time-of-day). The active scene = highest-priority scene whose trigger
  currently matches, falling back to **Always**. The Scene Home reflects this live.
- **Live bindings:** parts bound to data sources update continuously *within* a scene (scrubber
  position, CPU%, FPS, build status, clock) — no scene swap.
- **Timing envelopes:** per-layer lifecycle — `trigger` (e.g. on press) → `hold` (e.g. 120ms) →
  `fade/decay` (e.g. 600ms) with a `curve` (linear / ease-out / spring). Same mechanism powers
  press flares, glow pulses, notification flashes, idle "breathing".
- **Drag & drop:** parts into slots (auto-flow, reorder), triggers onto scene cards, layers
  reorder within the Loom.
- **States:** parts have idle / hover / pressed states designed in the Loom's state tabs.

## State Management
Suggested model (adapt to native idioms — GObject properties, a store, etc.):
- `scenes[]` — each: `{ id, name, priority, trigger, background(layer stack), parts[] }`.
- `alwaysScene` — the priority-0 base.
- `activeSceneId` — derived from live machine state + priority.
- `part` — `{ id, type, widthMode: fixed|stretchy, binding?, layers[] }`.
- `layer` — `{ id, kind, params, envelope? }`; `envelope = { trigger, holdMs, fadeMs, curve }`.
- `material` — one of Solid/Frosted/Outline/Ghost/Metal (a part-level property).
- `library` — imported icons/textures/effects + saved parts + installed scene packs.
- `liveState` — focused app, media state, cpu/gpu, clock — fed by the context service; drives
  `activeSceneId` and live bindings.
- **Device push:** a writer that renders the active scene to the hardware strip on any change.

## Design Tokens
These are the values used in the concept doc. **Chrome tokens** are the app's neutral graphite
system; **strip/material tokens** are examples of what the designed object can look like.

### App chrome (neutral, dark — honor these)
- Page background: `#0b0b0d`
- Panel/surface: `#161618`, secondary `#1d1d20`, deep `#101012`
- Borders/hairlines: `rgba(255,255,255,0.06–0.08)`
- Text: primary `#ededef`, secondary `#9a9aa0`, tertiary/muted `#6a6a72`, faint `#5e5e66`
- Live/active accent (status only): green `#46c479` (with soft glow)
- Card radius: ~11–14px; pill radius: 999px; inner strip radius: ~6–9px

### Typography
- UI: system font stack — `-apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui,
  sans-serif` (in-app use the platform default / Cantarell or the user's system font).
- Technical labels / eyebrows / segment text: **Space Mono** (monospace). Eyebrows are
  ~11px, weight 700, letter-spacing ~0.22em, uppercase, color `#6a6a72`.
- Display headings: ~38–74px, weight 700, letter-spacing ~ -0.03em.

### Strip / material example tokens (illustrative)
- Strip base: `#000`
- "Solid" sample parts: blue `#3a6ea5` / `#2f6b8f`, green `#2f8f5b`, terracotta `#c2603a`,
  violet `#7a4fa5`
- "Metal" material: gradient `#e3b34f → #c8902f → #9c6c1f`, border `#5e4310`, inset
  highlight/shadow for bevel
- "Frosted" material: `rgba(255,255,255,0.16)` fill, `rgba(255,255,255,0.34)` border, ~7px blur
- Themed "weathered industrial" example background: deep teal `#14302f`/`#0d2c2b` + grunge +
  scanline overlay
- Example envelope: hold 120ms, fade 600ms, ease-out

## Assets
- **No production art assets** are included — strip visuals are CSS/drawn placeholders
  illustrating materials/effects.
- Icons in the concept are emoji/text stand-ins; the real app ships its own curated icon set and
  supports imported icon sets per the import spec above.
- Fonts: system UI font + **Space Mono** (Google Fonts) for monospace labels. In-app, substitute
  the platform monospace if preferred.

## Files
- `t1bar studio — Concept.dc.html` — the concept document (open in a browser to view). It is a
  self-painting "Design Component"; `support.js` (included) is its tiny runtime. **Reference
  only.**
- `support.js` — runtime needed to open the concept HTML locally. Not part of the product.
