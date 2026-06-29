# T1 Touch Bar — frame-push / motion-runtime technical reference

Answers the motion-runtime / frame-push questions for the t1bar-studio rebuild, with
**measured-on-hardware** numbers (2026-06-29, this MacBookPro14,3, kernel 7.0.0-27) and the
device-API facts the new engine must build on. Ground truth: `t1-touchbar/src/t1touchbar/`
(`device.py`, `protocol.py`, `geometry.py`, `touch.py`) and `~/touchbar-port/dfr-experiment/FINDINGS.md`.

**Panel:** 2170 × 60, 24 bpp, **BGR888**, `pixel_format = 0x52474241`. One full frame =
2170×60×3 = **390,600 bytes**. The display pipe is USB **config 2**, interface 3 (Audio/Video,
class 16), **Bulk OUT 0x02 / IN 0x85**. Single-owner, root-only.

---

## Q1 — Max sustained full-frame rate? Synchronous or can it pipeline?

**Measured: ~90 fps sustained, full-panel.** Not the ~15 fps the old notes guessed (that was an
unoptimized cmd-file relay).

| run | result |
|-----|--------|
| 240-frame burst | **90.1 fps**, per-frame **median 11.0 ms** / mean 11.1 / p95 13.6 / max 15.7 / min 9.5, jitter ±1.2 ms, **0 stalls**, no drift |
| 30 s sustained (2735 frames) | **91.2 fps** overall; per-second 76–100 (typically 88–95) |
| throughput | **~35 MB/s** (≈ USB 2.0 bulk saturation) |

**It is synchronous and should stay that way.** `Device.blit()` writes the 390 KB frame then
waits for the device's `UDCL` (UPDATE_COMPLETE) ack before returning (`device.py:_wait_udcl`).
That ack is **not** the bottleneck — the ~11 ms/frame is the USB bulk transfer of 390 KB at
~35 MB/s. So the synchronous path already runs at line rate.

**Do NOT pipeline / fire-and-forget.** `FINDINGS.md` (frame-pacing section) is explicit: sending
frames without draining each `UDCL` both **drops frames** and **stalls the device** (its ack queue
backs up → ~3 fps). The current synchronous `blit()` is optimal; async wouldn't beat USB
bandwidth and would re-introduce the stall. **Treat 90 fps as the ceiling and ~11 ms as the
per-full-frame cost.**

## Q2 — Is continuous high-fps blitting safe? Recommended cap?

Safe, with margin. The 30 s continuous run showed **no stalls, no collapse**, only a mild ~10 %
softening (95 → 85 fps) and no thermal cliff. Across 240-burst + 2735-frame runs: **zero** frames
exceeded 3× median. The device is well-behaved *as long as you read `UDCL` per frame*.

OLED wear is a function of cumulative **lit-time and static bright content** (burn-in), **not**
frame rate — 90 fps vs 30 fps for the same lit duration doesn't wear the panel more. Standard OLED
care (avoid long static max-brightness regions) is the only wear consideration; irrelevant for motion.

**Recommendations for the motion runtime:**
- **Cap motion at 30 fps** (60 max). 30 fps is smooth for a control strip and uses only ~⅓ of
  capacity, leaving headroom for the host to *render* each frame.
- **Be event-driven, not free-running.** Idle scenes (no active motion layer, no live-binding
  tick due) should push **0 fps** — blit only on actual change. Run the animation clock only while
  a motion layer / timing envelope / live binding is actually animating, then stop.
- **The real budget is host CPU, not device health.** At 30 fps you have ~33 ms/frame to composite
  a full 2170×60 scene (layers + materials + effects) in Python/PIL/Cairo *and* the ~11 ms USB
  push. Full-frame compositing must fit there — which is the main argument for Q3 (dirty-rects).

## Q3 — Partial / dirty-rectangle updates (sub-region fb_request)?

**Protocol-native: YES — but untested from our stack.** The fb_request frame header is
`struct <HHHH I>` = **`begin_x, begin_y, width, height, buf_size`** followed by the BGR888 buffer
(`protocol.py:fb_request`). Today we hardcode `(0, 0, 2170, 60)` + a full 390,600-byte buffer, but
those rectangle fields exist precisely for sub-region updates. The mainline `appletbdrm` driver's
`appletbdrm_flush_damage` builds fb_requests from **damage rectangles** — partial updates are how
the real driver works; full-panel is just our current simplification.

**This is a big lever.** A 200 px-wide widget pulse = 200×60×3 ≈ **36 KB vs 390 KB** (~11× less
data → ~11× cheaper push), enabling many small concurrent animations within budget.

**Caveat — coordinate space.** The framebuffer is **column-major / transposed** (index =
`(x_long*H + y_short)*3`); `geometry.to_device_bytes` produces it via **flip-V then transpose**
(byte order R,G,B, no swap). `appletbdrm` maps the damage rect through the 90° rotation
(`begin_x = damage.y1`, etc.). So a dirty-rect must transform the upright damage rectangle through
that same flip-V+transpose and send only that sub-region's bytes.

**Recommended (driver-session task, not yet done):** add `Device.blit_rect(image, x, y, w, h)`
that sets begin_x/begin_y/width/height to the transposed damage rect and ships only that buffer;
verify with a probe (repaint only the left third, confirm the rest is untouched). Low risk —
recoverable via service restart, reboot as ultimate fallback. **I held off doing the live probe
this round** (untested protocol-write path; didn't want to risk a wedge unattended) — ping the
driver session to validate it when the motion runtime needs it.

## Q4 — After a service swap, does restarting re-light the panel, or is a re-init needed?

**Restarting the service is enough — confirmed empirically (twice just now, plus many times
earlier).** Sequence proven: `Device.close()` sets config 1 → panel blanks (the "blanks until
reboot" caveat) → `systemctl start t1bar.service` → `t1bar run` calls `Device.open()` which re-runs
the **full init** (switch to config 2 → GINF/REDY handshake → first blit) → **panel re-lights and
repaints**. No separate re-init step.

The "blanks until reboot" caveat applies **only** to handing back to *firmware simple-mode* (config
1 can't reclaim the T1 display coprocessor). It does **not** apply to a new host session re-acquiring
the panel — re-open + REDY + blit always re-lights it.

**So the service-swap pattern is safe:**
`sudo systemctl stop t1bar.service` (panel blanks briefly) → run your new runtime (open Device →
handshake → blit; panel lights with your content) → on exit `sudo systemctl start t1bar.service`
(re-opens; panel relights with the old runtime). The only gap is the momentary blank between owners.

**Corollary — your runtime must hold the Device open continuously** for as long as you want the bar
lit (the current runtime does: `with Device() as bar:` wraps the whole loop). Never close the Device
expecting firmware to take over; if you close it and nothing re-opens, the bar stays dark until
something re-opens it (or reboot).

---

## The device/engine API you build on (reuse — do not re-derive)

- **`from t1touchbar import Device, TouchReader`** — already installed (editable), used by the
  current `runtime.py`. Build the new runtime on these; the hard USB/protocol/geometry work is done.
- **`Device()`** context manager (root): switches to config 2, unloads `apple_touchbar`/
  `apple_ibridge`, GINF/REDY handshake, claims the A/V interface. `.info()` → `{'width':2170,
  'height':60,'bpp':24,'pixel_format':...}`. `.blit(img)` takes a **PIL Image or raw W*H*3 RGB
  bytes, upright** — it calls `geometry.to_device_bytes` for the flip-V/transpose/BGR, then the
  synchronous UDCL-paced push. `.clear()` = CLEAR_DISPLAY. Single-owner.
- **`geometry.to_device_bytes(image, w, h)`** — the upright-image → device-buffer transform
  (flip-V → transpose W×H→H×W → bytes, R,G,B order). Reuse for any new compositor output; reuse its
  logic if you implement `blit_rect`.
- **`TouchReader`** (input) — config 2 exposes the digitizer at `/dev/input/event4`
  ("Apple Inc. iBridge Touchpad"): `ABS_X 0–32767` → `pixel_x = ABS_X/32767*2170` (linear, **not**
  flipped, same orientation as the display), `ABS_Y 0–127`, `BTN_TOUCH`. Reads via python3-evdev,
  `dev.grab()` to keep touches off the desktop. Use it for the strip's tap/drag input.
- **`runtime.py`** is the loop to *extend, not replace*: holds the Device open, renders on change,
  **hot-reloads** the config (mtime poll), routes touch → `actions.py`. The new engine adds: a
  **scene resolver**, a **layered/material compositor** (replacing `render.py`), and an **animation
  tick** (capped fps while motion/envelopes/live-bindings are active; event-driven when idle).
- **`actions.py`** — uinput key emit + session-bridged media/seek. Reuse for Key/Transport parts.

## Implications for the motion-runtime design (task #7)

- Render at a **30 fps cap, event-driven**: an idle scene blits 0 frames; a scene with an active
  motion layer or a live binding ticks at ≤30 fps; press/notification envelopes animate for their
  `hold+decay` then stop. Never free-run at 90.
- Full-frame compositing must fit ~**25 ms** (leaving USB push ~11 ms inside a 33 ms budget). If a
  scene's per-frame compositing is too heavy in Python/PIL, that's the cue to (a) move compositing
  to Cairo/numpy, and/or (b) implement **dirty-rect `blit_rect`** (Q3) so only the animating region
  is recomposited *and* pushed (~11× less USB for small widgets).
- Swap onto hardware via the stop→run→restart pattern (Q4); develop the compositor **headless**
  (render scenes/sequences to PNG) until it's ready to drive the panel.
