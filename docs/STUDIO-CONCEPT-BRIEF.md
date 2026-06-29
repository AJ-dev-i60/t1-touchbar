# t1bar studio — Concept Brief (start from a blank canvas)

This is an **open creative brief**, not a spec. It tells you *what the app is for* and *who uses
it* — and deliberately nothing about how it should be laid out. We want a **genuinely fresh
interaction concept**, not a refinement of any existing editor. Invent the paradigm.

> We are intentionally **not** showing you the current app. Two prior passes both landed on a
> conventional "live preview + properties inspector + side rails" layout — competent, but it
> feels like a settings panel. Please don't reverse-engineer that. Start from the human and the
> hardware and design forward.

---

## What the hardware is

Some MacBooks have a **Touch Bar**: a slim, touch-sensitive **OLED strip** that sits above the
keyboard where the function-key row would be. It's a real, tiny, *very* wide display —
**about 2170 × 60 pixels, a ~36:1 letterbox ribbon** — and it responds to taps and drags. It can
show anything you draw on it: buttons, sliders, text, icons, indicators, art.

On a Mac it adapts to what you're doing (media controls while playing, formatting tools while
typing, etc.). This product brings that strip to life on **Linux**, and goes further: the user
decides entirely what it shows and how it behaves.

## What this app is

**t1bar studio lets a person design what lives on their Touch Bar — and feel it come alive on the
real hardware as they work.** It is the place where someone shapes their strip: its look, what
controls and information it carries, and how it changes depending on what they're doing.

The defining magic: **it's live on real hardware.** A change the user makes appears on the
physical strip under their fingertips within about a second. They're not configuring an abstract
file — they're shaping a small, glowing instrument attached to their laptop, in real time.

## Who uses it, and why (use-cases)

One person: a technically capable, design-conscious owner of a MacBook running Linux, customizing
their own machine. They reach for this app to make the strip *theirs*. Real scenarios:

- **"Make it useful for my work."** A developer wants the strip to carry the function keys, media
  keys, and a couple of personal shortcuts — and maybe a small build/status light. Practical,
  always-there controls.
- **"Adapt to what I'm doing."** While watching a video, they want scrubbing, volume, captions,
  and fullscreen right there; while coding, something else; while idle, just the essentials. The
  strip should *follow the moment* — change with the focused app, with media playback, with
  system state — without them micromanaging it.
- **"Show me something at a glance."** A gamer wants live CPU/GPU/FPS readouts during play; someone
  else wants the now-playing track, the time, or a battery/network glance.
- **"Make it beautiful."** Some of it is pure delight: colors, style, a vibe that matches their
  desktop and their hardware. Tinkering with how it looks is a joy in itself, not a chore.

Across all of these, the through-line is: **the strip is a personal, contextual control surface,
and this app is where you compose it** — quickly for the practical bits, lovingly for the
expressive bits.

## What a person can express here (capabilities, not UI)

Think of these as the raw materials the design must let someone shape — *how* is up to you:

- **Look** — the overall appearance of the strip and the things on it (color, style, density,
  feel). This is the most frequent, most tactile activity; it should be a pleasure.
- **Content** — the things that live on the strip: tappable controls (keys, transport, app
  shortcuts), sliders (scrub, volume), text and live readouts (track title, a stat, the time),
  and spacing/arrangement. Each thing occupies a slice of that long ribbon.
- **Behavior / context** — the strip can show *different things in different situations*. The
  person defines those situations ("when media is playing," "when this app is focused," "when the
  GPU is busy," later maybe time-of-day) and what the strip becomes in each. This contextual
  intelligence is the product's ambition — the strip should feel smart and alive, not static.

## The context the app lives in (hard constraints)

- It is a **native Linux desktop application** (built in GTK4 / libadwaita with custom drawing).
  **No web, no browser, no embedded web view** — this is a firm requirement. Whatever you design
  must be realizable as a native desktop app with custom-drawn surfaces.
- It runs on a **laptop screen**, **dark**, on Wayland/HiDPI. It should feel **Apple-grade and
  unmistakably native** — calm, precise, modern — because it lives on a MacBook, while being a
  first-class Linux citizen.
- The object being designed is an **extreme ultrawide ribbon (≈36:1)**. Representing, editing, and
  living alongside that strange shape is the central spatial puzzle of this app — and a big part
  of why a conventional layout feels wrong. Treat the strip's shape as a design opportunity, not
  an awkward constraint to hide.
- Single local app, one machine, one user. No accounts, no cloud.

## What we want from you

A **fresh concept for how a person designs a small, living, contextual hardware strip.** We're
open to — and hoping for — an interaction model that doesn't resemble a typical settings editor.
Be bold about the core metaphor and the primary gesture of the app. A few provocations (not
requirements, just to break the frame):

- What if the strip itself — at or near its real size — *is* the workspace, and you compose
  directly on it?
- What if "what shows when" (context) is the spine of the whole experience, not a buried list?
- What if styling feels more like playing an instrument or mixing than filling in fields?
- What if the app celebrates that this is *live on real hardware* as a central, emotional element?

You choose the metaphor, the spatial model, and the primary interactions. Surprise us.

## What success feels like

- The person feels like they're **crafting a living instrument**, not configuring software.
- The **live-on-real-hardware** magic is front and center and delightful.
- Quick practical edits are effortless; expressive/aesthetic play is genuinely fun.
- The contextual "it changes with what I'm doing" idea is **obvious and central**, not hidden.
- It looks and feels **Apple-grade and native** — something you'd be proud to have on a MacBook.

## Deliverable

Fresh concept directions for the app's core experience — the metaphor, the spatial/interaction
model, and how the three activities (look, content, behavior/context) come together. Wireframe or
concept fidelity is fine. We'll choose a direction and then detail it.

## Out of scope / freedoms

- You are **not** bound by any existing layout, region structure, or terminology. Reinvent freely.
- Don't worry about exact data formats, the icon set, or implementation plumbing — assume the
  controls, colors, live readouts, and context triggers described above are all available.
- Not a general drawing/animation tool, not multi-user, not cloud. One person, one strip, one
  beautiful native app.
