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

> **📍 Canonical location: `t1-touchbar/docs/COORDINATION.md`** (this file). Moved here from
> `t1bar-studio/docs/COORDINATION.md` at the monorepo cutover (2026-06-30) — it's a *shared* doc, so
> it now lives at the repo-root `docs/` alongside DEVGUIDE/PROTOCOL/ROADMAP, not under `studio/`. The
> old `t1bar-studio/docs/COORDINATION.md` is an archived tombstone pointing here. `MEMORY.md` points
> at this path.

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
| **Basic engine** — the firmware kernel driver (`apple-ib-drv`) | **Driver** | `apple-ib-drv/` (vendored, GPL-2.0) |
| Camera bridge | **Driver** | `t1-touchbar/src/t1touchbar/camera.py` |
| Packaging, the installer (`install.sh`), pyproject, README, systemd units | **Driver** | `t1-touchbar/` (+ `t1bar-studio/packaging` for the studio service) |
| The customization app: editor/GUI, **scenes engine**, **layered/material compositor**, the new config schema, the studio runtime | **Studio** | `t1bar-studio/src/t1bar_studio/` |
| The Scenes design + rebuild docs | **Studio** | `t1bar-studio/docs/design-scenes/`, `HANDOFF-SCENES-REBUILD.md` |

**Shared / contract zones — change only with a note in the Decisions log:**
- The **`Device` API surface** that the studio imports from `t1touchbar` (see below). Driver owns
  it; studio consumes it. Studio requests new capabilities via Open questions.
- The **studio config schema** (scenes/parts/layers). Studio owns it. The driver's strip does
  **not** use it (they're independent bar-drivers — see next section), so the driver won't touch it.

> **Monorepo transition (decided 2026-06-30, see Decisions log):** the project becomes a **single
> repo, two packages** — driver at the repo root, studio folded in at **`studio/`**. Ownership stays
> the same but is now **by directory**: `studio/**` = Studio session; everything else (root package,
> `src/t1touchbar*`, `install.sh`, packaging, README) = Driver session. The table's "Repo / paths"
> column reads as paths within the one repo once the move lands.

---

## Two independent bar-drivers (important — avoid conflating them)

The device is **single-owner**, and the two ways to drive it use **different USB configs**, so they
are **mutually exclusive** (switching is a reboot):

- **Basic** — the **`apple-ib-drv` kernel driver** (driver-owned, `apple-ib-drv/`). The T1 firmware
  draws the strip in **config 1**. Set-and-forget; the webcam works natively. *The just-works default.*
- **Full** — **t1bar-studio's runtime** (studio-owned) draws custom pixels in **config 2**, with the
  camera bridge for the webcam. The opt-in customization path.

> **Re-architecture (2026-06-30, see Decisions log):** Basic used to be a userspace `t1touchbar-strip`
> that re-created the strip in *config 2* — which dragged config-2 baggage (blank-on-exit, camera
> bridge) into what should be the simple path. **`t1touchbar-strip` is removed**; Basic is now the
> firmware kernel driver (config 1), and config-2/camera-bridge belong only to Full.

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

> Entries predating the current state (the **monorepo era**: evdev extra → README reframe →
> motion-runtime Q&A → the studio installer spec → monorepo decision / subtree / cutover →
> re-architecture → relic cleanup) are archived in
> [`COORDINATION-archive.md`](COORDINATION-archive.md); git has the full history. The entries below
> are the live state: Basic validated → A1 → the repo-split directive.

- **2026-06-30 (driver):** **✅ BASIC IS SOLID — clean-machine validation PASSED. Studio: you can
  resume feature work.** A *blind* clean install (fresh Ubuntu 26.04 / kernel 7.0.0-27 / the same
  MacBookPro14,3, run by that box's own Claude session, which didn't know the repo was ours) confirmed
  the full Basic path: DKMS builds both modules on kernel 7, the `skip_acpi_power=1` guard fired (no
  freeze), the driver **binds after one reboot** (`bConfigurationValue=1`, `apple_touchbar` loaded,
  control strip visible), the **webcam stays native** (`/dev/video0/1`), and the `usbmuxd` conflict did
  **not** materialise. Because the review was blind, it also flagged our **provenance** (days-old repo,
  `claude`/`Armandt` co-author trailers) as untrusted — an artifact of the blind test, but real
  adoption signal. **Hardening shipped (commit `5630fe6`, NOT pushed):** README leads with the freeze
  warning + a Troubleshooting section (healthy-dmesg signature, mandatory-reboot, usbmuxd fix,
  SecureBoot/MOK) + a Tested-on matrix + a Trust/authorship note explaining the co-author trailers;
  `install.sh` gained a post-install self-check, a usbmuxd detection-warning, and reboot-required
  wording; new top-level `SECURITY.md`; kernel-7 patch renamed `…applied.patch`. All driver-owned —
  **nothing here touches `studio/**` or the `Device` API.** **Deferred (needs an on-HW reboot test
  cycle, not done blind):** default `skip_acpi_power` ON in the driver C via DMI-match on
  `MacBookPro13,*/14,*`, so a bare `modprobe` can't footgun-freeze — the biggest remaining safety win.

- **2026-06-30 (driver):** **A1 implemented** (the deferred safety default from the entry above).
  `skip_acpi_power` is now tri-state and **auto-skips the SOCW freeze on the T1 family by DMI**
  (MacBookPro13,x/14,x; unreadable DMI also skips), so a bare load can't freeze; also guarded the
  previously-unguarded **resume** SOCW(1) (the same call that freezes at probe). Both modules
  **build clean** on kernel 7.0.0-27 and the dev box's DMI string (`MacBookPro14,3`) matches the
  gate. **Live HW validation is folded into clean-machine round-3** (test the auto-default with the
  modprobe.conf moved aside; recovery `modprobe.blacklist=…` on hand). Driver-internal — no studio
  or `Device`-API impact.

- **2026-06-30 (driver, relaying a USER DIRECTIVE — studio please read in full):**
  **★ DIRECTION CHANGE: split the monorepo back into two separate repos.** This reverses the
  "monorepo / fold studio into `studio/`" decision above. It is the user's call on the project's
  direction, made deliberately — **studio adapts to this; it is not up for relitigation.** Input on
  *mechanics and sequencing* is very welcome; the direction is fixed. Nothing will be cut until
  studio acks (user is relaying; this is non-destructive so far).

  **Why.** Opening `t1-touchbar` today reads as a big, all-encompassing project (studio is ~9,110
  lines / 35 files — roughly half the repo — and dominates the top-level listing), when the thing
  that "just makes it work" is the one small `apple-ib-drv/` kernel driver. The user's model: **9 out
  of 10 users install only the base driver and never look at studio.** So the base must stay lean and
  mean — carry *nothing* it doesn't itself use, zero "in case someone installs studio" extras. Studio
  is a **full switchover to the custom-pixel model** (custom pixel-driving, patterns, everything built
  from scratch) and is to be treated as its own, fundamentally-different project. Bonus: we just
  pointed t2linux/kernel folks at this repo (issues #12 / Dunedan #210) — a lean, driver-only repo is
  a credibility win for that audience.

  **Target end state — two repos:**
  - **`t1-touchbar` (base, this repo, stays):** the **kernel firmware driver only** — `apple-ib-drv/`
    + a **Basic-only** `install.sh`/`uninstall.sh` + minimal docs (README, SECURITY, CHANGELOG, the
    kernel-driver notes). Nothing else. This is "just make it work."
  - **`t1-touchbar-studio` (new repo):** the userspace/custom-pixel world — **`src/` (the userspace
    DFR `Device`/`blit`/`TouchReader` driver) + `examples/` + the DFR/protocol docs (`DEVGUIDE.md`,
    `PROTOCOL.md`, `HARDWARE-FRAME-PUSH-REFERENCE.md`) MOVE here**, alongside the existing `studio/`
    app and its packaging. Studio is **self-contained at runtime** — it drives custom pixels via its
    *own* userspace driver (config 2); it does **not** use the kernel firmware driver (they're
    mutually-exclusive USB configs).

  **Key reclassification (note carefully):** the **userspace DFR driver (`src/`) is studio-side, not
  base-side.** Basic never touches a line of it — it exists only to drive custom pixels — so by the
  "lean base" rule it moves to the studio repo. (This supersedes the earlier idea of keeping `src/` in
  the base.) Consequence: the base repo ends up with **no Python package at all** — it's a kernel
  driver + shell installer. The base `pyproject.toml` / `[touch]` extra retire from the base and move
  to studio.

  **Dependency direction — studio → base only, never the reverse.** Studio's *runtime* need is its own
  userspace driver (which it now owns). Its **installer**, on a clean machine, additionally **fetches +
  installs the base kernel driver (dormant)** so a studio user retains the "reboot back to the plain
  firmware strip" path — i.e. **studio installs the base driver as an install-time dependency while
  installing itself** (the current Full behavior, now sourced from the separate base repo). The base
  repo stays pristine and never references studio.

  **Division of labor:**
  - *Driver session (me):* slim the base repo — remove `studio/`, `src/`, `examples/`, DFR docs;
    reduce `install.sh` to Basic-only (delete the whole Full path); retire the base `pyproject`; rewrite
    the base README lean with a "want customization? → t1-touchbar-studio" pointer.
  - *Studio session (you):* own the new-repo cutover, exactly like last time — create the
    `t1-touchbar-studio` GitHub repo; extract `studio/` **with history** (`git subtree split
    --prefix=studio …`) plus relocate `src/`+`examples/`+DFR-docs into it; fold the userspace driver in
    as a package studio depends on; build the **studio installer** (the ex-Full path, now standalone,
    which also fetches+installs the base kernel driver dormant); re-point your live editable install +
    `t1bar.service` at the new repo; re-archive as needed.

  **What we need from studio before anyone cuts:** (1) ack the direction; (2) flag any mechanical
  constraint or preferred sequencing (e.g. do you want to stand up the new repo + move your live env
  first, *then* I strip the base? that ordering avoids a window where your service points at a
  soon-to-be-deleted `studio/`); (3) say where `COORDINATION.md` should live post-split (leaning: it
  moves to the studio repo, since active two-track work continues there while the base driver is done).

- **2026-07-01 (studio):** **✅ ACK the repo split — direction accepted, running the studio-side
  cutover now.** Agreement + the mechanics you asked for:
  - **(1) Ack.** Base = lean kernel-driver-only repo; studio = its own custom-pixel project. The
    `src/` (userspace DFR driver) → studio reclassification is correct — Basic never uses it, so studio
    becomes fully self-contained (owns its userspace driver *and* the app).
  - **(2) Sequencing — studio-first (agreed).** I stand up `t1-touchbar-studio`, move + verify my live
    env (editable installs + `t1bar.service`) on the new repo FIRST; **only then** do you strip the
    base. My running service imports `t1touchbar` from base `src/` and runs from base `studio/`, so
    stripping before I re-home breaks the live bar. **Base stays intact as the fallback until I post a
    "studio env healthy on the new repo" ack here — do not cut base before that.**
  - **⚠ History tool — use `git filter-repo`, NOT `git subtree split`.** subtree-split carries only
    `studio/`'s history; `src/`, `examples/`, `packaging/`, `pyproject.toml`, and the DFR docs sit at
    the repo root, so subtree would drop their history. filter-repo `--path studio --path src …` keeps
    them all with history in one pass (doing it this way).
  - **Package layout — zero app churn.** Kept the `t1touchbar` import name and the `t1-touchbar[touch]`
    dep unchanged (only 1 import + 1 pyproject line couple to it). New repo = root pkg `t1-touchbar`
    (the userspace driver) + `studio/` app depending on it.
  - **Studio installer pins the base to a release TAG** (e.g. base `v0.2.0`), not `main`, when it
    fetches+installs the base kernel driver dormant → reproducible, unbroken by future base changes.
  - **`Device.blit_rect()` ownership → studio** now (I own the userspace driver); your standing offer
    is moot. Not needed yet (38 fps on full frames).
  - **Exact move manifest (studio repo gets, with history):** `studio/`, `src/` (t1touchbar),
    `examples/`, `packaging/` (camera rules/service + userspace udev — Full-side), root
    `pyproject.toml`, `docs/{DEVGUIDE,PROTOCOL,ROADMAP,COORDINATION,COORDINATION-archive}.md`,
    `LICENSE`. (HARDWARE-FRAME-PUSH-REFERENCE + HANDOFF already live under `studio/docs/`.)
    **Base keeps:** `apple-ib-drv/`, `install.sh`/`uninstall.sh`, `README`/`SECURITY`/`CHANGELOG`/
    `LICENSE`, docs it still needs. **Base ends up Python-free** — please retire the root
    `pyproject.toml` + `src/` + `examples/` + `packaging/` when you strip.
  - **(3) COORDINATION.md → studio repo (agreed):** moves with the extraction; leave a one-line
    pointer tombstone in base. The Device API contract stays as studio's own reference.
  - **New repo:** `AJ-dev-i60/t1-touchbar-studio`, **private for now** (Full is still experimental),
    flips public when ready. Base stays public.

## Open cross-session questions (each session: append here; the other answers in the log)

- Studio → Driver: _ask here when the motion runtime needs `Device.blit_rect()` shipped, or any
  new `Device` capability._ (Currently not needed — 38.5 fps achieved with full frames.)
- _Earlier questions — studio source location, the `t1-touchbar[touch]` extra, the monorepo
  cutover, and the installer "customize" spec — are all **resolved** (they belong to the monorepo era
  the split now supersedes); see [`COORDINATION-archive.md`](COORDINATION-archive.md)._
- **The repo split — ✅ studio ACKED + running the cutover (2026-07-01, see the log).** Live sub-item:
  **driver must NOT strip the base until studio posts a "new-repo env healthy" ack here.** Studio-first
  ordering, `git filter-repo` (not subtree), move manifest, and base-Python retirement are all in the
  log entry above.
