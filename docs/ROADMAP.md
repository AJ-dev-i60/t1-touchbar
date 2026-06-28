# Roadmap / deferred work

Things intentionally left for later, with enough context to pick up cold.

## Webcam ⇄ Touch Bar coexistence  *(SOLVABLE natively — proven 2026-06-28)*

The custom Touch Bar needs the iBridge in **USB configuration 2**; stock `uvcvideo` only
binds the webcam in **configuration 1**. Earlier this looked mutually exclusive. It isn't —
config 2 carries the camera too, and the camera stream is a **standard codec**.

**What the live capture proved (2026-06-28):**
- Config 2 (`bNumInterfaces=8`) contains **both** the webcam (IF0 VideoControl + IF1
  VideoStreaming) **and** the DFR display (IF3, class 16). One USB config, both interfaces —
  so a single process owning config 2 can drive the bar *and* read the camera at once.
- The config-2 VideoStreaming descriptors use Apple subtypes `19`/`20` (0x13/0x14) instead of
  the standard `6`/`7`, which is why `uvcvideo` bails ("No streaming interface found for
  terminal 32770"). But decoding the bytes: subtype 20 = a normal FRAME descriptor —
  **1280×720 / 640×480** with frame intervals **identical** to config 1. Not a new codec,
  just renumbered subtypes (Apple marks config 2 "macOS-only").
- **The payload is H.264** (not MJPEG): captured EP `0x81` in config 2 and the first NAL after
  the 12-byte UVC payload header is `00 00 00 01 27 64 …` — Annex-B start code, NAL type 7
  (SPS), High profile. `ffmpeg -f h264` decoded it to a real, recognisable camera frame.

**So native coexistence needs NO kernel patch.** The driver already owns config 2 in
userspace for the display; it can *also* claim IF1, run the UVC PROBE/COMMIT handshake,
bulk-read EP `0x81`, strip the UVC payload headers, and feed the H.264 elementary stream to a
**`v4l2loopback`** node (decode in-process or pass H.264 through). Howdy / Zoom / browsers
then open the loopback device — camera **and** custom Touch Bar, simultaneously.
(`v4l2loopback` DKMS + `pyusb` + `ffmpeg` are already installed.)

**Proof-of-concept scripts:** `dfr-experiment/cam_probe.py` (config switch + PROBE/COMMIT +
codec sniff) and `cam_capture.py` (header-stripped H.264 → `ffmpeg` → JPEG, visually
confirmed). See `dfr-experiment/CAMERA-FINDINGS.md`.

**Build path (next):**
1. Userspace UVC capture class: claim IF1, negotiate, stream EP `0x81`, reassemble frames via
   the UVC header FID/EOF bits → H.264 frames. (Belongs ONE level above the thin driver, or as
   an optional `t1touchbar.camera` module — keep `Device` pure.)
2. Pipe into `v4l2loopback` (re-encode to MJPEG/YUYV for max app compatibility, or expose
   H.264 directly). Repoint Howdy's `device_path` at the loopback node.
3. Integrate with the strip: camera is just always-available in config 2 — no handoff needed.

**Fallback still valid** if perf/quality of the H.264 path disappoints: cooperative handoff
(drop to config 1 on screen-lock for Howdy, resume config 2 on unlock) + a manual "camera
mode" toggle. But the native path makes the bar and camera coexist with no compromise.

**Already done:** Howdy's `device_path` was repointed from the fragile `/dev/video0` to the
stable per-camera path `/dev/v4l/by-id/usb-Apple_Inc._iBridge-video-index0`.

## Other deferred items

- **`uvcvideo` quirk (optional, upstreamable):** instead of userspace capture, a small kernel
  patch mapping config-2 subtypes 19→FORMAT / 20→FRAME would let the in-kernel driver bind the
  config-2 camera directly. Nice contribution, but the userspace path above needs no kernel.
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
