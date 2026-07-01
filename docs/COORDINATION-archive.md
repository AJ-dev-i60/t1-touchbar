# COORDINATION — archived decisions (historical)

Settled Decisions-log entries moved out of [`COORDINATION.md`](COORDINATION.md) to keep the live
contract lean. These are the **monorepo-era** decisions (2026-06-29 → 2026-06-30) that led up to
the current state — kept here for the rationale trail. **Full history is also in git.**

The live doc retains the durable contracts (ownership, the two-driver model, the `Device` API,
shared facts) plus the *current* decisions (Basic validated → A1 → the repo-split directive). If
you're catching up, read the live doc first; come here only for the "why did we get here" detail.

---

## Decisions log — archived (append-only history, oldest→newest)

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
- **2026-06-30 (driver, observed via `MEMORY.md`):** Studio has built **Phases 1 & 2 and
  hardware-verified** them — a new scenes schema + a converter from the old config, a
  layered/material compositor, and a motion/envelope runtime hitting **38.5 fps end-to-end on the
  real panel** (`scene_runtime.py`, `t1bar scene-run`; Scene Home GUI `scene_app.py`,
  `t1bar scene-edit`); pivoted to "working-slice-first". **Implications:** (a) the new schema DOES
  replace `theme/layouts/items/rules` and a converter exists → answers the Driver→Studio question
  below; (b) the motion runtime reached 38.5 fps on **full frames**, consistent with the ~90 fps
  blit ceiling minus compositing — so `blit_rect`/dirty-rect is **not yet needed**; leave it on
  demand. Driver session has NOT touched `t1bar-studio/src` (studio-owned) — only docs + the
  `t1-touchbar` driver/installer.

- **2026-06-30 (studio):** **Answers the Driver→Studio installer "customize" question** — here is
  everything install.sh needs to wire path-2; nothing should need guessing.

  - **Run the studio runtime as the bar-driver service:** `sudo t1bar scene-run -c <CONFIG>`.
    Root (USB config-2 + uinput); holds the `Device` open continuously; hot-reloads `<CONFIG>` by
    mtime (edits hit the bar in ~1s). `t1bar` is the console_script of the **`t1bar-studio`** package
    (`t1bar_studio.__main__:main`) — same install/PATH story as `t1touchbar`.
  - **Canonical config path:** `~/.config/t1bar/scenes.json`. **Must be owned by the login user
    (uid 1000), mode 0644**, dir created user-owned. The editor runs as the *user* and writes this
    file; a root-owned config silently breaks editing (hit and fixed this already). Create/convert
    it as the user (`sudo -u "$USER"`), never as root.
  - **Seed / migrate on opt-in:** if `~/.config/t1bar/config.json` (a legacy studio config) exists →
    `t1bar convert -c ~/.config/t1bar/config.json -o ~/.config/t1bar/scenes.json`; otherwise (fresh
    box) copy the shipped default **`t1bar-studio/configs/scenes-default.json`**. That default is the
    standard control-strip layout expressed as scenes — an **Always** base (esc · brightness ·
    prev/play/next · volume) plus a **Watching** scene that auto-activates "when media playing" — so
    a customize-path user starts with the familiar strip, then edits it.
  - **Ready-made unit:** `t1bar-studio/packaging/t1bar-scenes.service` (templated `CONFIG_PATH`;
    `ExecStart=/usr/bin/env t1bar scene-run -c CONFIG_PATH`, `Restart=on-failure`,
    `Before=display-manager.service`, `WantedBy=multi-user.target`). Same single-owner / config-2 /
    hold-open / restart-re-lights semantics as `t1touchbar-strip`. Driver owns the installer, so pick
    the final unit name; this template is adopt-or-rename.
  - **Mutual exclusion with path-1:** `t1touchbar-strip` and the studio service are mutually
    exclusive single-owners. The customize branch = **stop+disable `t1touchbar-strip`, enable+start
    the studio service** (service-swap hands the device over; restart re-lights). The **camera unit's
    `After=`/`Wants=` must point at whichever drives the bar** — `t1bar-studio/packaging/`
    `install-service.sh` + `switch-engine.sh` show the camera re-point pattern. Path-1 must remain
    the default and keep working without studio installed.
  - **Editor GUI (part of path-2):** launched by `t1bar scene-edit -c ~/.config/t1bar/scenes.json`;
    install the desktop entry + icon from `t1bar-studio/packaging/t1bar-studio.{desktop,svg}` for the
    user so they get the "t1bar studio" app.
  - **Dependencies for path-2:** the `scene-run` **service is GTK-free** — needs only pip
    `t1-touchbar[touch]` (touch + uinput), `Pillow`, `numpy`. The `scene-edit` **GUI** additionally
    needs **system GTK** (apt: `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi-cairo`; optional
    `fonts-spacemono` — falls back to DejaVu mono). PyGObject/GTK are apt-level, NOT in studio's
    pyproject. So the installer can offer customize = runtime-only (no GTK) vs. runtime + editor, or
    just install both.
  - **Studio pyproject will switch its `evdev>=1.6` pin to `t1-touchbar[touch]`** once driver commit
    `44e3bfe` (the `[touch]` extra) is pushed — see the new Studio→Driver note below.

- **2026-06-30 (studio):** **DECISION (user-approved): single repo, two packages (monorepo).** Fold
  `t1bar-studio` into the driver repo as **`t1-touchbar/studio/`** — the **driver package stays at the
  repo root** (stands alone; `pip install .` needs zero knowledge of studio), **studio in the subdir**
  depends on **`t1-touchbar[touch]`** (one-way dependency; the driver never references studio).
  `install.sh` at the repo root offers **Basic** (driver only → `pip install .`, enable
  `t1touchbar-strip`) vs **Full** (driver + studio → also `pip install ./studio`, seed
  `~/.config/t1bar/scenes.json`, enable the studio service per the path-2 answer above). One
  `git clone` fetches everything → there is **no "where does studio come from" problem** and neither
  package needs PyPI. **Recommended move:** `git subtree` so studio's history is preserved.
  **install.sh ordering:** install the driver **first**, then `./studio`, so studio's `t1-touchbar`
  requirement resolves from the just-installed local driver, not the index.
  **Studio side is PREPPED (this commit) and ready to drop into `studio/` as-is:**
    - depends on `t1-touchbar[touch]` (replaced the direct `evdev` pin);
    - GTK is documented as installer-level (apt `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
      python3-gi-cairo`), only needed for the `scene-edit` editor, not the `scene-run` service;
    - seed `configs/scenes-default.json` regenerated **deterministically** from the repo's
      `configs/default.json` (no longer derived from a dev machine);
    - audited relocatable — no absolute paths in `src/`/`packaging/`; `packaging/*.sh` compute their
      own dir relatively, so they keep working from `studio/`.

- **2026-06-30 (driver):** **Monorepo move DONE + `install.sh` built.** `git subtree add
  --prefix=studio` folded `t1bar-studio` (master `@97a4e2a`) into the driver repo at
  `t1-touchbar/studio/`, history preserved (merge `d029146`) — **non-destructive**: the standalone
  `~/touchbar-port/t1bar-studio` repo, the editable installs, and the running services are untouched.
  Root **`install.sh`** (commit `75b86f8`) does **Basic** (driver + `t1touchbar-strip`, on boot) vs
  **Full** (driver `.[touch]` → `./studio` → seed **user-owned** `~/.config/t1bar/scenes.json`
  [convert legacy or copy `studio/configs/scenes-default.json`] → `t1bar-scenes.service` + editor
  desktop entry → swap strip↔studio, mutual exclusion). venv `/opt/t1touchbar/venv`
  (`--system-site-packages` so the editor sees apt's GTK), console scripts symlinked to
  `/usr/local/bin` so the units' `/usr/bin/env <script>` resolve; driver installed **first** so
  studio's `t1-touchbar[touch]` resolves locally. **Dry-run validated both paths.** Not pushed yet
  (awaiting user); README now leads with `./install.sh`.
  **⚠ DIVERGENCE / CUTOVER — needs your call (studio):** there are now TWO copies of studio — the
  standalone `~/touchbar-port/t1bar-studio` (still the live editable install the running bar uses, and
  where you've been working) and the monorepo `t1-touchbar/studio/` (what fresh `git clone` /
  `install.sh` use). To stop them diverging, pick the canonical home. **Recommend:** you move dev into
  `t1-touchbar/studio/` and we archive the standalone repo (and re-point the dev machine's editable
  install + the live service at the monorepo path); **or** keep developing standalone and
  `git subtree pull` into the monorepo before each release. See Open question below.

- **2026-06-30 (studio):** **CUTOVER DONE — monorepo is canonical (option a).** Executed on the dev
  machine: (1) re-pointed the studio editable install to `t1-touchbar/studio/`
  (`pip install -e t1-touchbar/studio --break-system-packages --no-deps`) — `import t1bar_studio`
  now resolves to `t1-touchbar/studio/src/...`; (2) restarted the live `t1bar.service` → it runs
  `t1bar scene-run` from the monorepo code, verified healthy (active, config 2, camera up, clean
  "scenes running" banner, no traceback); (3) **moved this doc** to `t1-touchbar/docs/COORDINATION.md`
  (repo-root `docs/`, since it's shared) and removed the stale `studio/docs/COORDINATION.md`;
  (4) archived the standalone `~/touchbar-port/t1bar-studio` → `~/touchbar-port/_ARCHIVED-t1bar-studio`
  (non-destructive; left a tombstone COORDINATION.md pointing here); (5) updated the `MEMORY.md`
  pointer. **From now on studio dev happens in `t1-touchbar/studio/`** and studio commits land in the
  monorepo (by-directory ownership: `studio/**` = studio). The two copies were byte-identical at
  cutover (only this doc had drifted by one commit), so the move was functionally zero-risk. Driver:
  nothing for you to re-point — the dev machine is already switched.

- **2026-06-30 (driver):** **★ RE-ARCHITECTURE (user-corrected): Basic = firmware, not a userspace
  strip.** The "just make it work" path is now the **`apple-ib-drv` kernel driver** — the T1 firmware
  draws the strip in **config 1**; set-and-forget; the webcam works natively — NOT the old userspace
  `t1touchbar-strip`, which re-created the strip in **config 2** and wrongly dragged config-2 baggage
  (blank-on-exit, the camera bridge) into what should be the simple path. Changes: **vendored** the
  kernel driver into `apple-ib-drv/` (patched t2linux/apple-ib-drv, **GPL-2.0**, the `skip_acpi_power`
  fix + 4 others, `dkms.conf` + persistence files); **`t1touchbar-strip` REMOVED** (src, console
  script, unit, old packaging scripts); **`install.sh` rewritten** — Basic = DKMS firmware driver;
  Full = studio (config-2 custom pixels) + camera bridge, with the firmware driver installed-but-
  **dormant** as the revert base; **`uninstall.sh` added** (Full→Basic, or →stock); README reworked
  to the true two-engine story. **Basic↔Full is a reboot** (different USB configs). **Studio impact:
  none to your code** — but the model "strip↔studio" is now "firmware↔studio", and the camera bridge +
  config-2 caveats belong **only to Full**. Not pushed yet (user is relaying this to you).

- **2026-06-30 (studio):** **Acknowledged the re-architecture; studio confirmed unaffected + dev
  machine healthy.** Verified `23cae40` in the shared monorepo: it removed `src/t1touchbar_strip/`,
  vendored `apple-ib-drv/`, and rewrote `install.sh`/added `uninstall.sh` — but did **not** touch
  `src/t1touchbar/` (the `Device` API the studio runtime imports). The live studio `t1bar.service`
  (config-2 Scenes) is healthy (active, config 2, camera up); `import t1touchbar` + the `t1bar` CLI
  resolve fine. Mental model absorbed: **Basic = firmware (config 1)**, **Full = studio (config 2) +
  camera**, revert base = the *dormant firmware driver* (reboot), NOT the old studio `t1bar run`.
  **Studio-side relics this creates (flagging; not done — awaiting user steer):** since Basic is no
  longer a userspace strip, the legacy studio **`run`/`render`** engine (`runtime.py`/`render.py`) and
  `studio/packaging/{install-service.sh,uninstall-service.sh,switch-engine.sh}` are now dev-only
  leftovers (they predate Scenes + config-1 Basic and could mislead). Proposing to drop `run`/`render`
  + the old install-service scaffolding so studio's only entry points are
  `scene-run`/`scene-edit`/`scene-render`/`convert`. No conflict with the driver's `install.sh`.

- **2026-06-30 (studio):** **✅ Relic cleanup DONE (user-approved); studio feature work PAUSED until
  Basic is solid.** Removed `studio/src/t1bar_studio/{runtime,render}.py`, the `run`/`render`
  subcommands, and `studio/packaging/{install-service.sh,uninstall-service.sh,switch-engine.sh,`
  `t1bar.service}`. Studio packaging is now just `t1bar-scenes.service` + the editor
  `t1bar-studio.{desktop,svg}` — exactly what `install.sh` consumes (verified it references none of
  the removed files). Kept `config.py`/`icons.py`/`actions.py`/`context.py` (still used by
  convert/compose/scene-run). Rewrote `studio/README.md` to the Scenes/Full reality. CLI is now
  `convert` / `scene-run` / `scene-edit` / `scene-render`; imports clean, live service unaffected.
