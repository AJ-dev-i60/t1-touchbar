# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

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
