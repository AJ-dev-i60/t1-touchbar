# Roadmap / deferred work

Things intentionally left for later, with enough context to pick up cold.

## Webcam ⇄ Touch Bar coexistence  *(deferred — plan: cooperative handoff)*

The custom Touch Bar needs the iBridge in **USB configuration 2**; the built-in webcam
(including **Howdy** face-login) needs **configuration 1**. A USB device has only one active
configuration, so today they're mutually exclusive.

**Why native coexistence is hard (investigated 2026-06-27):** config 2 *does* expose the
webcam interfaces, but its VideoStreaming interface describes the stream with **Apple's
proprietary UVC descriptor subtypes** (`19` = format, `20` = frame) instead of the standard
`FORMAT_MJPEG`/`FRAME_MJPEG` (6/7) used in config 1. Linux `uvcvideo` doesn't recognise
19/20, registers zero formats, and logs *"No streaming interface found for terminal 32770"* —
so no `/dev/video` capture node appears. Making it work natively would require
reverse-engineering that format (the subtype-19 GUID doesn't map to an obvious known codec)
**and** patching `uvcvideo` to translate the Apple descriptors — a real sub-project, with a
risk the codec is undecodable outside macOS.

**Chosen plan (A) — cooperative handoff:**
- The control-strip app yields the device on demand. Subscribe to the screen-lock D-Bus
  signal (`org.freedesktop.login1` / the screensaver); on **lock**, drop to config 1 so the
  FaceTime cam appears for Howdy; on **unlock**, resume config 2 and the strip.
- Add a manual **"camera mode" toggle** (command/hotkey) for arbitrary webcam apps (Zoom,
  browsers): in config 2 the camera node is absent, so an app sees "no camera" with nothing
  to trigger an auto-switch — a manual toggle covers that case.
- Trade-off: the Touch Bar reverts to firmware/blank during active camera use.

**Already done:** Howdy's `device_path` was repointed from the fragile `/dev/video0` to the
stable per-camera path `/dev/v4l/by-id/usb-Apple_Inc._iBridge-video-index0`.

## Other deferred items

- **Native webcam coexistence** (the hard option above): RE the config-2 webcam format +
  `uvcvideo` support. Would be a nice upstream contribution if the format decodes.
- **UI design tool** (separate project): rich customization on top of the driver — themes,
  colors, fonts, swappable icons, tap glow-fade animation, action mapping, scripts.
- **Multi-client "bar compositor" + SDK** so third-party apps can share the bar (e.g. a
  Chrome extension via a native-messaging host, Spotify, games). Prerequisite: add a
  **version handshake** to the socket protocol so it can evolve without breaking clients.
- **PyPI publish** of the driver.
- **Touch refinements:** Y-axis calibration; the IF6 / `hidraw1` interface (EP `0x87`) for
  multitouch / gestures; reading touch inside the daemon's render loop for smooth sliders.
- **Kernel end-state:** add the T1 USB id to mainline `appletbdrm` so the bar is a real DRM
  device owned full-time.
