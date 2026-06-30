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

### Changed
- Installer + README now state the **reboot is required to finish** Basic (the live load can't
  claim interfaces the generic HID drivers already hold), rather than implying it's optional.
- `apple-ib-drv/t1-kernel7-fixes.patch` → `…applied.patch`, clarified as a reference diff already
  baked into the sources (stops the confusing `patch --dry-run` "previously applied").

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
