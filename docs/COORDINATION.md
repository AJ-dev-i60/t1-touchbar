# Cross-session coordination contract

Two Claude Code sessions are building this product in parallel. This doc is the **shared
contract** so they don't collide or duplicate work. **Both sessions read this at start** (it's
pointed to from `MEMORY.md`) and append to the Decisions log / Open questions instead of editing
across ownership lines.

- **Driver / core session** — owns the hardware driver and the standalone "just-make-it-work"
  experience.
- **Studio / UI session** — owns the optional customization app (the "Scenes / Layer Loom"
  rebuild; see `HANDOFF-SCENES-REBUILD.md`).

There is **no live channel between the sessions** (separate chats are isolated; the Agent tool
only spawns sub-agents within a session). Coordination happens through: this doc, the shared git
repos, the shared memory dir, and the user relaying specific Q&A.

---

## Product vision (the split both sessions serve)

`t1-touchbar` is the standalone thing that **makes a 2017 MacBook Pro (T1) Touch Bar work on
Linux**. The installer offers two paths:

1. **Just make it work (default, highest priority).** Driver + control strip (esc / brightness /
   keyboard-backlight / media / volume / hold-Fn→F1–F12) on boot. **Standalone, no studio app.**
2. **Customize (optional, opt-in).** Adds **t1bar-studio** so the user can design their own bar.
   Layered on top; never required for path 1.

Path 1 must always work without path 2.

---

## Ownership boundaries (don't edit across the line without a note here)

| Area | Owner | Repo / paths |
|------|-------|--------------|
| Hardware driver: `Device`, `blit`/`blit_rect`, `protocol`, `geometry`, `touch`/`TouchReader`, `server`/`client` | **Driver** | `t1-touchbar/src/t1touchbar/` |
| The standalone control strip | **Driver** | `t1-touchbar/src/t1touchbar_strip/` |
| Camera bridge | **Driver** | `t1-touchbar/src/t1touchbar/camera.py` |
| Packaging, the installer (`install.sh`), pyproject, README, systemd units | **Driver** | `t1-touchbar/` (+ `t1bar-studio/packaging` for the studio service) |
| The customization app: editor/GUI, **scenes engine**, **layered/material compositor**, the new config schema, the studio runtime | **Studio** | `t1bar-studio/src/t1bar_studio/` |
| The Scenes design + rebuild docs | **Studio** | `t1bar-studio/docs/design-scenes/`, `HANDOFF-SCENES-REBUILD.md` |

**Shared / contract zones — change only with a note in the Decisions log:**
- The **`Device` API surface** that the studio imports from `t1touchbar` (see below). Driver owns
  it; studio consumes it. Studio requests new capabilities via Open questions.
- The **studio config schema** (scenes/parts/layers). Studio owns it. The driver's strip does
  **not** use it (they're independent bar-drivers — see next section), so the driver won't touch it.

---

## Two independent bar-drivers (important — avoid conflating them)

The device is **single-owner** (USB config 2, IF3, root). At any moment exactly one process
drives the bar. There are two such processes, owned by different sessions, and they are
**mutually exclusive**:

- **`t1touchbar-strip`** (driver-owned) — the standalone control strip. Hardcoded reference
  layout; does NOT read the studio config. This is path 1.
- **t1bar-studio's runtime** (studio-owned) — renders the user's scenes config. This is path 2.

The installer wires up whichever the user chose (the service-swap pattern handles handing the
device between them). Neither session should assume the other's process is running.

---

## The `Device` API contract (driver-owned; studio builds on this — do not re-derive)

Authoritative measured details: **`HARDWARE-FRAME-PUSH-REFERENCE.md`**. Summary:

- `from t1touchbar import Device, TouchReader` (root). `Device()` context manager: config-2
  switch → GINF/REDY handshake → claims A/V iface. `.info()` → `{width:2170, height:60, bpp:24,
  pixel_format:…}`. `.blit(img)` takes an **upright** PIL image / raw W*H*3 RGB and pushes it
  **synchronously** (UDCL-paced). `.clear()`. Single-owner; hold it open continuously while lit.
- `geometry.to_device_bytes(img, w, h)` — upright→device transform (flip-V → transpose → bytes).
- `TouchReader` — `/dev/input/event4`, `ABS_X 0–32767 → pixel_x = ABS_X/32767*2170` (linear, not
  flipped), `ABS_Y 0–127`. Needs the `[touch]` extra (evdev).
- **Frame-push envelope (measured):** full-panel blit ≈ **90 fps / ~11 ms**, USB-2.0-bound; keep
  it synchronous (do NOT pipeline — that stalls the device to ~3 fps). Cap motion at **30 fps,
  event-driven** (0 fps when idle); the real budget is host compositing time.
- **Service swap / re-light:** restarting the owning service re-lights the panel
  (`Device.open` re-runs the full init). The "blanks till reboot" caveat only applies to handing
  back to *firmware* simple-mode.

### `Device.blit_rect()` — dirty-rect partial updates (STATUS: validated, not yet shipped)
The protocol supports sub-region frames (`fb_request` carries `begin_x/begin_y/width/height`).
**Probed live on hardware (2026-06-29):** a `begin_x=723`, 724-px-wide partial frame (130 KB vs
390 KB) was **accepted and UDCL-ack'd** by the device — so partial updates work on T1. Visual
positioning confirmation was interrupted before completion. **Coordinate space:** device buffer is
column-major/transposed (`index = x_long*60 + y_short`); a rect's `begin_x/width` map to the long
(2170) axis, `begin_y/height` to the short (60) axis, full-height = `begin_y=0,height=60`. **The
driver session will add a clean `Device.blit_rect(image, x, y, w, h)` + finish the visual
verification when the studio motion runtime needs it** — studio: raise it in Open questions when
you're ready, don't implement your own protocol-write.

---

## Shared facts both sessions should rely on (don't re-derive)
- Panel 2170×60, 24bpp, frame = 390,600 bytes. Config 2 / IF3 / Bulk OUT 0x02, IN 0x85.
- The **userspace driver does not need the out-of-tree kernel driver** and never loads
  `apple-ibridge`, so it sidesteps the SOCW ACPI hard-lock (validated on a clean Ubuntu 26.04).
- Reference docs: `HARDWARE-FRAME-PUSH-REFERENCE.md` (frame-push), `HANDOFF-SCENES-REBUILD.md`
  (the studio rebuild), `docs/design-scenes/` (the concept), `~/touchbar-port/dfr-experiment/`
  (raw RE journal). Memory index: `MEMORY.md`.

---

## Decisions log (append-only; date + which session)

- **2026-06-30 (driver):** Made `evdev` an optional `[touch]` extra in `t1-touchbar/pyproject.toml`
  (commit `44e3bfe`, not yet pushed) — bare `pip install` no longer hard-fails; touch is opt-in.
  Studio: when depending on touch, install `t1-touchbar[touch]`.
- **2026-06-30 (driver):** README reframed to "make your Touch Bar work" + the two paths. Vision
  above is the locked split (basic standalone strip = priority; studio = optional add-on).
- **2026-06-29 (driver):** Answered the studio session's 4 motion-runtime questions with on-HW
  measurements → `HARDWARE-FRAME-PUSH-REFERENCE.md`. Headline: full-frame ≈90 fps synchronous,
  don't pipeline, cap motion at 30 fps event-driven, dirty-rect is protocol-native, service
  restart re-lights.
- **2026-06-29 (driver):** Live-probed dirty-rect — device accepts/acks sub-region frames (see
  `blit_rect` status above). `Device.blit_rect()` to be shipped on demand.

## Open cross-session questions (each session: append here; the other answers in the log)

*(none open right now — studio's frame-push questions are answered in the reference doc.)*

- Studio → Driver: _ask here when the motion runtime needs `Device.blit_rect()` shipped, or any
  new `Device` capability._
- Driver → Studio: _will the new scenes config schema fully replace the current
  `theme/layouts/items/rules`, and does the installer's "customize" path need to migrate an
  existing config? (affects what the installer offers / the strip↔studio handoff.)_
