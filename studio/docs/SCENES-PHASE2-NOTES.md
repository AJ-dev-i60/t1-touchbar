# Scenes / Layer Loom rebuild — Phase 2 (motion + live runtime)

Status: **done & verified — headless AND on real hardware.** Builds on Phase 1
(`docs/SCENES-PHASE1-NOTES.md`) and the driver session's measured
`docs/HARDWARE-FRAME-PUSH-REFERENCE.md`. The legacy `run`/`render`/`editor_gtk` paths
and the live `t1bar.service` remain untouched; the new runtime swaps in via the safe
stop→run→restart pattern and was tested that way (services restored cleanly).

## What landed

- **`motion.py`** — the time dimension. Continuous motion (Drift/Breathe/Flicker/Sweep)
  as pure functions of absolute `t`; timing **envelopes** (`trigger → hold → fade →
  curve`, with linear/ease-out/spring) as a stateful `Dynamics` object the runtime owns.
  `scene_animating()` tells the runtime whether anything is still moving (so it can drop
  to event-driven). Stateless scenes never touch it → still-renders are identical
  frame-to-frame.
- **`compose.py`** — now consumes both: `motion_offset()` transforms each part and
  modulates alpha; effect intensities are scaled by their envelope (press-flare,
  breathe) via `Dynamics.layer_value()`; sweeps draw a clipped travelling highlight.
  `render_scene`/`compose` gained `t` + `dynamics`, both defaulting to a static frame.
  **Gradients vectorised with numpy** (were a ~171 ms pixel loop → sub-ms).
- **`scene_runtime.py`** — the new live loop. Extends the proven `runtime.py` pattern
  (hold Device open, hot-reload, touch→actions) and adds: scene resolution over the
  Always base, the layered compositor, and a **30 fps-capped, event-driven** animation
  tick. Idle scenes blit 0 frames; motion/envelope/live-binding activity ticks ≤30 fps
  then settles. Live bindings: media position/title, cpu% (`/proc/stat`), clock. Press
  fires per-layer envelopes. `model.Hot` added for new-schema hot-reload.
- **CLI:** `t1bar scene-run -c <scenes>` (root). Legacy `run` untouched.

## Verified

**Headless** (real runtime decision methods + fake bar + simulated clock, 3 s):
- idle, media stopped → 1 blit then 0 fps (event-driven)
- media playing (slider live-binding) → re-blits each 1 s position tick, no scene swap
- breathe motion → clean 30.3 fps (cap holds at any sim step)
- idle + press flare → ~1 + ~28-frame burst, then settles to idle
- motion sequence renders correctly; flare envelope traces 0→1.0→0.78→0.42→0.17→0
  over a 120 ms hold + 700 ms ease-out fade

**On hardware** (swapped onto the real panel, services restored each time):
- new compositor drove the panel: 120 composed frames pushed, 0 errors
- **38.5 fps end-to-end** on the *heaviest* scene (gradient+frosted+5 materials+glows;
  ~25.6 ms compose+push) — above the 30 fps cap; **pure-push ceiling 103 fps**
- real `t1bar scene-run` (breathing-glow `always` envelope) held the Device open and
  ticked ≤30 fps for 14 s, clean exit, services restored, device back in config 2

## Performance model (measured, this machine)

At 30 fps you have ~33 ms/frame: ~10–11 ms is the synchronous UDCL-paced USB push of the
390 KB frame (USB-2 bound, keep it synchronous), leaving ~22 ms to composite. Typical
scenes composite in ~2 ms (≈100 fps possible, capped to 30); the heaviest gradient+
frosted+multi-glow scene is ~16 ms (≈38 fps end-to-end). Full-frame push is sufficient
for 30 fps motion **today**.

## Deferred / next

- **Dirty-rect `blit_rect`** (driver session offered to build+probe it): protocol-native
  (`fb_request` already carries begin_x/y/w/h), ~11× cheaper for a small animating widget.
  Not a prerequisite now — adopt when a heavy scene animates only a small region. Coords
  must go through the column-major flip-V+transpose.
- **Focused-app trigger** (`app` scene trigger): needs a focused-app D-Bus source on
  Wayland/GNOME. Asked the driver/contextual session whether their "contextual touchbar
  customization for apps" work exposes one to subscribe to instead of building a second
  GNOME extension. `scenes.trigger_matches` already evaluates `app` (false until a source
  feeds `live['app']`).
- **gpu/fps readouts**, **Ripple** effect (motion-driven), **Texture/Motion/Image**
  backgrounds (currently fall back to solid).

## Next roadmap step (handoff §7 step 3+): the GUI

Scene Home (graphite chrome, scene cards with live mini-renders + the live indicator),
then Auto-flow editor, Layer Loom, Background & Materials, Kit, Extend. The engine now
renders + animates scenes, so the GUI's live previews can light up immediately.
