# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

Hardening from the first clean-machine validation (MacBookPro14,3 / Ubuntu 26.04 / kernel
7.0.0-27 — Basic mode verified: DKMS builds, driver binds after reboot, webcam intact).

### Added
- Installer self-check (Basic): greps the healthy dmesg/lsmod signature and prints a clear
  pass/fail instead of "it should work".
- Installer `usbmuxd` detection: warns (with the exact fix) if `usbmuxd` is active and its udev
  rule matches the iBridge, the most likely cause of a still-dark bar after a reboot.
- `SECURITY.md`: what the installer touches, the freeze hazard, authorship/co-author trailers,
  and how to report issues.
- README: a leading freeze-safety note, a **Troubleshooting** section (healthy signature, reboot
  requirement, `usbmuxd`, Secure Boot/MOK), and a **Tested on** matrix.

### Security
- **`skip_acpi_power` is now safe-by-default in the driver itself.** The freeze-guard was a module
  parameter defaulting to the *dangerous* upstream behavior — protection lived only in
  `/etc/modprobe.d`, which a bare `insmod`, a from-source build, or a removed conf would miss.
  It's now tri-state (`-1` auto / `0` force-run / `1` force-skip) and **auto-skips on the T1 family
  (MacBookPro13,x/14,x) by DMI match** (unreadable DMI also skips, fail-safe), so the module can't
  hard-freeze the machine even when loaded by hand. `0` is the only way to run the power-on now.
- **Guarded the suspend/resume SOCW calls.** Upstream ran `ASOC.SOCW(1)` on *resume* with no guard —
  the same call that freezes at probe. All three sites (probe, suspend, resume) now honour the skip.

### Changed
- Installer now explains the alarming-but-harmless `tainting kernel … signature missing` line where
  it appears (or, if Secure Boot is on, points at the one-time `mokutil` MOK enrolment instead).
- Installer exports `DEBIAN_FRONTEND=noninteractive` so apt doesn't warn (`dpkg-preconfigure:
  unable to re-open stdin`) or block when stdin is the curl/`--yes` pipe.
- README documents why the installer doesn't force a live unbind/rebind (it would poke the bind/power
  paths that can wedge the T1, for no benefit over a reboot).
- Installer + README now state the **reboot is required to finish** Basic (the live load can't
  claim interfaces the generic HID drivers already hold), rather than implying it's optional.
- `apple-ib-drv/t1-kernel7-fixes.patch` → `…applied.patch`, clarified as a reference diff for the
  original kernel-7 build fixes (the safe-by-default change above is a follow-on, documented here).

## [0.1.0] — 2026-06-27

First release. The Apple T1 (iBridge) Touch Bar is, as far as the public record
shows, driven from Linux for the first time.

### Added
- `Device` — display output: configuration switch to config 2, GINF/REDY
  handshake, synchronous (UDCL-acked) framebuffer blit at ~90 fps, restore on
  close. Accepts PIL images or raw RGB; geometry/byte-order handled internally.
- `TouchReader` — input: reads the iBridge digitizer and emits `TouchEvent`s
  (`down`/`move`/`up`) with coordinates mapped to panel pixels.
- `Server` / `t1touchbar serve` — Unix-socket daemon (frames in, touch events
  out) so tools in any language can drive the bar over a stable IPC.
- `Client` — Python client for the socket daemon.
- `protocol` / `geometry` — reusable DFR wire framing and the image transform.
- Examples: reactive ripples, tappable buttons, scrolling marquee.
- Docs: `PROTOCOL.md` (socket + DFR wire format), `DEVGUIDE.md` (the full
  reverse-engineering reference).
