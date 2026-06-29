# t1bar studio — Functional Design Brief

A brief for a design agent. It describes **what the app must do and afford** — not how it
must look. Visual design, layout, motion, and styling are yours to invent. Everything here
is functionally true of the working app today; treat it as the contract the new design must
satisfy.

---

## 1. What you're designing

**t1bar studio** is a native Linux desktop app for designing the **Touch Bar** of a MacBook
(the thin OLED strip above the keyboard). The Touch Bar is now fully driven on Linux by a
background service; this app is the **settings + design surface** for it — the equivalent of
"System Settings → Keyboard → Touch Bar" on macOS, but far more capable.

The app edits a single JSON config. A background service renders that same config onto the
**real hardware and hot-reloads on save**, so **every change the user makes appears on the
physical Touch Bar within ~1 second.** Live, on real hardware, while they design. That live
loop is the soul of the product and should feel central — the user is *painting onto a real
device*, not filling in a form.

Think: **Apple Shortcuts meets Final Cut's inspector**, for a 2170×60 pixel strip.

---

## 2. Who uses it & what they want

A single technical-but-design-conscious owner of a MacBook running Linux. They are not a
developer of the app; they're a *user* customizing their machine. Their goals, roughly in
order of frequency:

1. **Recolor / restyle** buttons and the bar (themes) — the most common quick tweak.
2. **Rearrange** what's on the bar and how wide each thing is.
3. **Add / remove** controls (a media button, a volume slider, an app shortcut).
4. **Set up context rules** — "show media controls *only* when something is playing,"
   later "show *these* controls when Chrome is focused."
5. **Just look at it** — admire/sanity-check the bar, toggle between states.

They value: an Apple-caliber, calm, modern feel (it's on a MacBook); immediacy (live
preview); and *not* feeling like they're editing a config file or a generic GTK settings
dialog.

---

## 3. The canvas you're designing *for* (critical constraint)

The Touch Bar is **2170 × 60 physical pixels** — an extreme ~**36 : 1** letterbox. This
shapes everything:

- The **preview of the bar is the hero element** of the app. It must be shown faithfully
  (correct aspect ratio, real colors, real fonts/icons) and large enough to work on, but it
  is inherently a long thin ribbon. Designing the app *around* a 36:1 object is the central
  layout challenge — give it pride of place without letting it waste the rest of the window.
- Individual targets on the bar are small. Selection, hover, and editing affordances for
  things *inside* the ribbon need care (a click-to-select model exists today).
- Content is **horizontal only** — a single row of items. No vertical stacking on the device.

The app window itself is a normal desktop window (resizable, ~1340×800 today) on a HiDPI
laptop display.

---

## 4. Core concepts (the mental model to make legible)

The whole product is four nested ideas. A good design makes these obvious without jargon:

- **Theme** — global look of the bar: background color, default button fill/text/corner
  radius/font size, the "pressed" highlight, an accent color, the scrubber track color, and
  spacing (gap between items, margin at the ends).
- **Layout** — one arrangement of the bar: an ordered list of **widgets**. There are multiple
  named layouts (e.g. `default`, `media`). Exactly one layout is shown on the bar at any
  moment, chosen by rules.
- **Widget** — one item in a layout (button, spacer, label, scrubber). Each has a **weight**
  (its relative width — items share the bar proportionally) and type-specific properties.
- **Rules** — context → layout mapping, evaluated top-to-bottom, first match wins. Today:
  "when media is playing → show the `media` layout; otherwise → `default`." This is what makes
  the bar *contextual* (the headline feature direction).

Plus **actions** (what a widget does when tapped) and **context sources** (live data the bar
reacts to — currently media playback).

The design should help a user hold this model: *I'm theming the bar, arranging widgets into
layouts, and writing rules that pick a layout based on what I'm doing.*

---

## 5. Data model (the real schema — design to these fields)

The app reads/writes this JSON. Inspectors and controls should map to these exact fields.

```jsonc
{
  "version": 1,
  "theme": {
    "background": [R,G,B],            // whole-bar background
    "button": {
      "fill":  [R,G,B],               // default button background
      "text":  [R,G,B],               // default label/icon color
      "radius": 12,                   // button corner radius (px)
      "font_size": 26                 // default label size (px)
    },
    "pressed": { "fill": [R,G,B], "color": [R,G,B] },  // look while held down
    "accent":  [R,G,B],               // scrubber fill / highlights
    "track":   [R,G,B],               // scrubber empty-track color
    "gap": 10,                        // px between widgets
    "margin": 10                      // px inset at the bar ends
  },

  "layouts": {
    "default": { "items": [ <widget>, <widget>, ... ] },
    "media":   { "items": [ ... ] }
    // user can create more named layouts
  },

  "rules": [
    { "when": { "media": "playing" }, "show": "media" },
    { "show": "default" }             // a rule with no "when" = the fallback
  ]
}
```

**Widget types** (the `type` field), each also has `id` (optional) and `weight` (number,
relative width):

| type       | purpose                              | key fields |
|------------|--------------------------------------|------------|
| `button`   | tappable key/control                 | `label` *or* `icon`; optional `fill`/`color` overrides; optional `dynamic`; `action` |
| `spacer`   | invisible gap to push things apart   | `weight` only |
| `label`    | text, static or bound to live data   | `source` (e.g. `media_title`), `font_size` |
| `scrubber` | draggable progress bar, tap-to-seek  | `source: "media_position"`, `action: ["seek"]` |

**Button specifics:**
- A button shows **either** a text `label` **or** an `icon` (named vector glyph).
- `fill` / `color` are **optional per-button overrides** of the theme's button colors.
- `dynamic: "play_pause"` makes the icon swap between play/pause based on live media state.
- Available **icons** today: `play`, `pause`, `prev`, `next`, `brightness_up`,
  `brightness_down`, `volume_up`, `volume_down`, `volume_mute`, `fullscreen`, plus simple
  text-glyph icons. (The icon set is extensible.)

**Actions** (the `action` field — what a tap does):
- `["key", "KEY_X"]` — emit a keystroke (e.g. `KEY_ESC`, `KEY_F1`…`KEY_F12`, `KEY_VOLUMEUP`,
  `KEY_MUTE`, `KEY_BRIGHTNESSUP`, `KEY_KBDILLUMUP`, `KEY_PLAYPAUSE`, `KEY_NEXTSONG`, …).
- `["seek"]` — scrubber seeks playback to the tapped position.
- `["media", …]` — media transport via the session.
- `["layout", "name"]` — switch the bar to another layout for ~10s (manual override).

**Context sources / rule conditions:**
- Today: `media` with status `playing` (and live title/artist/position/length for labels and
  the scrubber).
- **Planned (design should leave room for):** `app` / focused-window conditions ("when Chrome
  is focused"), and system-stat conditions ("CPU/GPU/RAM" for a gaming layout).

---

## 6. Primary user journeys (must all be smooth)

1. **First run** — open the app; the bar's current design is shown immediately; it's obvious
   how to change something and that changes are live.
2. **Recolor a button** — select a button on the preview → change its fill/text color →
   see it on the preview *and* the hardware instantly.
3. **Restyle the whole bar** — open theme controls → change background/accent/radius/spacing →
   whole bar updates.
4. **Rearrange** — change the order of widgets and their relative widths (weights).
5. **Add a widget** — pick a widget type from a palette → it appears on the bar → configure it
   (icon/label, action, color).
6. **Remove / duplicate** a widget.
7. **Build a context rule** — create/edit a layout (e.g. `media`), then a rule that shows it in
   a context (e.g. media playing). Understand which layout is currently active and why.
8. **Preview a state** — toggle a "media playing" preview so they can design the `media`
   layout even when nothing is actually playing (the bar shows the active layout regardless;
   the *in-app* preview can simulate states).
9. **Revert / undo** — confidently back out of a change.

---

## 7. Screen regions (functional inventory — reorganize freely)

These capabilities must exist; their arrangement, grouping, and styling are open.

- **Bar preview / canvas (hero).** Faithful render of the bar (2170×60 aspect, real colors,
  icons, fonts). Click a widget to select it. Should communicate "this is your real Touch
  Bar." Ideally supports direct manipulation (drag to reorder, drag a handle to resize a
  widget's weight) rather than only numeric fields.
- **Layout switcher.** Choose which layout you're editing (`default`, `media`, …); create,
  rename, delete layouts. Indicate which layout is *currently live on the bar*.
- **Widget palette.** The set of addable widgets (button, spacer, label, scrubber). Add to the
  current layout.
- **Inspector.** Context-sensitive editor for the current selection, in three modes today:
  - **Item** — edit the selected widget (label/icon, color overrides, weight, action, dynamic).
  - **Theme** — edit the global theme fields (§5).
  - **Rules** — edit the context→layout rules.
- **Header / status.** App identity; a **live status indicator** ("edits are applying to the
  bar"); the **"preview as playing"** toggle.
- **Weight ruler** (today): a strip under the preview visualizing how widths are distributed.
  Keep some affordance for understanding/adjusting relative widths.

---

## 8. Detailed functional requirements

**Preview**
- Always reflects the current config exactly (it uses the same renderer as the hardware).
- Shows the layout currently selected for editing, under a simulated state (idle by default;
  "playing" when the preview toggle is on).
- Selection is visible (which widget is being edited).

**Editing**
- Every theme field and widget field in §5 must be editable through appropriate controls
  (color pickers for RGB fields, numeric/slider for radius/font_size/gap/margin/weight,
  text entry for labels, a picker for icons, a picker for actions/keys, a chooser for
  bound `source`).
- **Color editing is the most-used action** — make it excellent (swatches, recent colors,
  a real picker, maybe palette presets). RGB triples in the schema; the UI should hide that.
- **Per-button override vs theme default** must be legible: a button can inherit the theme or
  override fill/text; the UI should show which, and allow "reset to theme."
- **Actions**: choosing what a button does should be approachable — a categorized picker
  (media keys, function keys, volume/brightness, layout-switch) rather than typing `KEY_*`.
- **Weights**: relative widths are unintuitive as raw numbers; prefer direct manipulation
  (drag handles on the preview) with the number as secondary.

**Auto-save & live**
- Changes save automatically (debounced) and apply to the hardware live; the design should
  reassure the user this is happening (subtle save/applied feedback) without nagging.
- No explicit "save" step is required, but the design may still offer undo/redo and revert.

**Rules**
- Present the top-to-bottom, first-match-wins logic understandably. Each rule = a condition
  ("when …") + a target layout ("show …"); the last rule is the catch-all default.
- Make it clear *which rule is currently matching* (i.e., why the bar shows what it shows).

---

## 9. States, feedback & edge cases

Design needs to cover:

- **Live / connected** vs **not connected** (the service may be stopped, or the Touch Bar
  hardware absent on a non-MacBook). When not live, the app should still be fully usable as a
  design tool (preview only) and say so calmly.
- **Saving / applied** micro-feedback.
- **Selection** state (item selected vs nothing selected → inspector shows theme/rules or an
  empty hint).
- **Empty states** — a layout with no widgets; no rules yet; first run.
- **Active layout indicator** — which layout the bar is showing right now (may differ from the
  one being edited).
- **Preview-state toggle** — idle vs "media playing" (affects play/pause icon, scrubber fill,
  bound labels). Be clear this is a *preview simulation*, not the real state.
- **Errors** — an invalid value shouldn't break the bar; surface gently (the renderer is
  defensive).

---

## 10. Interactions worth adding (current UI lacks most of these)

The current build is functional but utilitarian. Strongly consider:

- **Direct manipulation** on the preview: drag to reorder widgets; drag handles to resize
  weights; click-empty to add.
- **Rich color picking**: swatches, recent/used colors, theme palette, eyedropper feel.
- **Undo / redo** and **revert to last-saved / reset-to-default**.
- **Duplicate widget**, **copy a style** between widgets.
- **Theme presets** (a few tasteful starting themes) and **layout templates**.
- **Keyboard support** (select, nudge, delete, undo).
- A clear path for the **contextual future** (per-app layouts, system-stat widgets) so the
  rules UI won't need a redesign when those land.

---

## 11. Platform & technical constraints (hard requirements)

- **Native Linux desktop app. No web / no browser / no local server** — this was an explicit
  requirement. It is implemented in **GTK4 + libadwaita + PyGObject** (Python). Designs must
  be realizable with GTK4/libadwaita widgets and custom CSS/drawing (custom canvas drawing is
  available via Cairo, as used for the preview and ruler). Avoid designs that assume web/CSS
  capabilities GTK can't do.
- **Wayland**, HiDPI laptop display, **dark theme** (the app forces dark today).
- Use **system-available fonts** (Inter is installed and used; a mono face is available).
- **Single-window** desktop app (resizable). It should degrade gracefully across window sizes.

---

## 12. Aesthetic direction (guidance, not prescription)

- **Apple-like**: calm, precise, generous spacing, restrained color, content-first. It runs on
  a MacBook; it should feel at home there while being a great Linux citizen.
- A prior internal spec described the target as **"Shortcuts × Final Cut inspector"**: the
  bar preview sitting in a deep **OLED 'pit'** as the hero, a quiet widget palette, and a
  precise inspector. You may honor or rethink this.
- Let the **live, on-hardware** nature shine — the emotional hook is "I changed this and it's
  *already on my laptop's Touch Bar*." Motion/feedback can reinforce that.
- Avoid the "generic settings form" feel — that's the main thing the owner dislikes today.

---

## 13. What's weak today (problems to solve)

- Reads like a **stacked settings form**, not a design tool — the inspector is a dense column
  of rows; editing feels indirect (numbers, not manipulation).
- The **hero preview doesn't feel hero** enough; the relationship between the preview, the
  layout you're editing, and the live bar isn't vivid.
- **Color editing** (the most common task) is just standard color buttons — not delightful.
- **Weights** are raw numbers; **actions** require knowing `KEY_*` names; **rules** are a bare
  list — all functional but not approachable.
- Overall it doesn't yet evoke "Apple-grade tool for a beautiful piece of hardware."

---

## 14. Non-goals / out of scope

- Not a general image/animation editor for the bar (no per-pixel art, no video).
- Not a multi-user / cloud / account product. Local, single-machine.
- Doesn't manage the driver/service lifecycle — assume the bar "just works"; this app only
  designs its content.
- The bar is a **single horizontal row**; don't design multi-row/grid bar content.

---

## 15. Success criteria

A redesign succeeds if:

1. A new user immediately understands "this controls my Touch Bar, live."
2. Recoloring and rearranging feel **direct and delightful**, not form-like.
3. The bar preview is an unmistakable hero and always trustworthy (matches the hardware).
4. The theme / layouts / widgets / rules model is legible without documentation.
5. It feels **Apple-grade** — calm, modern, precise — and unmistakably native (not web).
6. It's buildable in GTK4 + libadwaita + PyGObject + Cairo.

---

## Appendix A — current region map (for reference, reorganize freely)

```
┌───────────────────────────────────────────────────────────────┐
│ header:  t1bar studio            [▶ playing]   [● Live on bar]  │
├───────────────────────────────────────────────────────────────┤
│         ┌───────── bar preview (2170×60 ribbon in an OLED pit) ─────────┐         │
│         │  esc   ☼  ☀   ◀  ▶  ▶▶        🔊 🔇 🔊                         │         │
│         └────────────────────────────────────────────────────┘         │
│         weight ruler  ▏──▏─▏──▏──▏──▏────▏──▏─▏──▏                         │
│         [ default ] [ media ] (+ layout tabs)                            │
├───────────┬───────────────────────────────────┬───────────────┤
│ palette   │            (breathing stage)        │  inspector    │
│ • button  │   "click a widget to edit it,       │ Item|Theme|Rules │
│ • spacer  │    or add one from the left"        │  …field rows…  │
│ • label   │                                     │                │
│ • scrubber│                                     │                │
└───────────┴───────────────────────────────────┴───────────────┘
```

## Appendix B — a real example config

```json
{
  "version": 1,
  "theme": {
    "background": [8, 10, 18],
    "button": { "fill": [38,42,58], "text": [232,234,240], "radius": 12, "font_size": 26 },
    "pressed": { "fill": [70,110,210], "color": [255,255,255] },
    "accent": [90,170,250], "track": [55,60,78], "gap": 10, "margin": 10
  },
  "layouts": {
    "default": { "items": [
      { "type":"button", "id":"esc", "label":"esc", "weight":1.3, "fill":[60,40,48], "action":["key","KEY_ESC"] },
      { "type":"spacer", "weight":0.3 },
      { "type":"button", "id":"bdn", "icon":"brightness_down", "action":["key","KEY_BRIGHTNESSDOWN"], "weight":1 },
      { "type":"button", "id":"bup", "icon":"brightness_up",   "action":["key","KEY_BRIGHTNESSUP"],   "weight":1 },
      { "type":"spacer", "weight":0.4 },
      { "type":"button", "id":"prev", "icon":"prev", "action":["key","KEY_PREVIOUSSONG"], "weight":1 },
      { "type":"button", "id":"play", "icon":"play", "dynamic":"play_pause", "fill":[34,54,44], "action":["key","KEY_PLAYPAUSE"], "weight":1 },
      { "type":"button", "id":"next", "icon":"next", "action":["key","KEY_NEXTSONG"], "weight":1 },
      { "type":"spacer", "weight":0.4 },
      { "type":"button", "id":"voldn", "icon":"volume_down", "action":["key","KEY_VOLUMEDOWN"], "weight":1 },
      { "type":"button", "id":"mute",  "icon":"volume_mute", "action":["key","KEY_MUTE"], "weight":1 },
      { "type":"button", "id":"volup", "icon":"volume_up", "action":["key","KEY_VOLUMEUP"], "weight":1 }
    ] },
    "media": { "items": [
      { "type":"button", "icon":"prev", "action":["key","KEY_PREVIOUSSONG"], "weight":1 },
      { "type":"button", "icon":"play", "dynamic":"play_pause", "fill":[34,54,44], "action":["key","KEY_PLAYPAUSE"], "weight":1 },
      { "type":"button", "icon":"next", "action":["key","KEY_NEXTSONG"], "weight":1 },
      { "type":"label", "source":"media_title", "weight":2.6, "font_size":22 },
      { "type":"scrubber", "source":"media_position", "action":["seek"], "weight":5 },
      { "type":"button", "icon":"volume_up", "action":["key","KEY_VOLUMEUP"], "weight":1 }
    ] }
  },
  "rules": [
    { "when": { "media": "playing" }, "show": "media" },
    { "show": "default" }
  ]
}
```
