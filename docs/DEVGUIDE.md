# T1 Touch Bar on Linux — Developer Guide

**Status: working end-to-end (2026-06-27).** Arbitrary graphics, text, images, and
animation render to the MacBook Pro (T1 / 2016–2017) Touch Bar from Linux, at ~90–100 fps,
with a verified geometry/color pipeline and a closed visual feedback loop. This document is
the spec + how-to for building tools and utilities on top of it.

> Companion docs in this folder: `FINDINGS.md` (chronological research journal),
> `t1_dfr_probe.py` (low-level one-shot probe), `t1_dfr_daemon.py` (the reference render
> daemon). Read this file first.

---

## 0. TL;DR for builders

- The Touch Bar is a **2170 × 60**, 24-bpp display reachable over USB once you switch the
  iBridge to **USB configuration 2** and speak the **DFR protocol** on its class-16
  (Audio/Video) interface (Bulk OUT `0x02` / IN `0x85`).
- Render path that works: build an upright RGB image → **flip vertically → transpose →
  send bytes**. The device renders it.
- Frames are **synchronous**: send a frame, then read its `UDCL` ack before the next.
  Honor this and you get ~90–100 fps; ignore it and the device stalls to ~3 fps and drops
  frames.
- A reference daemon (`t1_dfr_daemon.py`) already holds the device and renders on command
  via a `cmd` file. **Build your tools as producers that write to that daemon**, or import
  its primitives. You do not need to re-derive the protocol.
- Two caveats to design around: (1) while you own the bar (config 2), the webcam, ambient
  light sensor, and the normal Fn/media row are **gone**; (2) exiting leaves the bar
  **blank until reboot** (the T1 firmware doesn't reclaim it). See §7.

---

## 1. Architecture

```
   your tool / widget  ──writes──▶  cmd file  ──polled by──▶  t1_dfr_daemon.py
   (spotify, sysmon, …)                                          │
                                                                 │ owns USB config 2,
                                                                 │ holds the AV interface
                                                                 ▼
   PIL image (RGB, 2170×60)  ──to_buf(): flipV+transpose+tobytes──▶  DFR frame
                                                                 │ Bulk OUT 0x02
                                                                 ▼
                                                       T1 (iBridge) panel  ◀── Bulk IN 0x85 (UDCL ack)
```

Three layers:
1. **Transport/protocol** (`t1_dfr_probe.py`): config switch, handshake, frame framing.
2. **Render daemon** (`t1_dfr_daemon.py`): keeps config 2 open, exposes a command file,
   render primitives (solids, text, images, scroll, animations), geometry transform,
   synchronous frame pacing.
3. **Producers** (to build): app-aware logic that decides what to draw and writes commands.

---

## 2. Hardware & USB topology

- Device: `05ac:8600` "iBridge" (the T1 chip), USB 2.0 high-speed, **3 configurations**:
  1 = "Default iBridge Interfaces" (Linux default; simple Fn/media only — no pixel pipe),
  2 = "…(OS X)" (**what we use** — exposes the display pipe), 3 = "…(Recovery)".
- The display lives **only in config 2**, **Interface 3**, `bInterfaceClass 16`
  (Audio/Video), endpoints **Bulk OUT `0x02`**, **Bulk IN `0x85`**. (This is why stock
  Linux, sitting on config 1, could only ever show the 3 firmware layouts.)
- Other config-2 interfaces (for future work): IF0/IF1 webcam (UVC), **IF2 HID
  (Interrupt IN `0x83`, 64-byte reports)** and **IF6 HID (Interrupt IN `0x87`, 1024-byte
  reports)** — these are the **touch/button input** channels (see §8), IF4/IF5 CDC-NCM
  (bridgeOS networking), IF7 vendor "Apple USB SEP" (Touch ID/secure enclave).
- Switching to config 2 is **safe** on this T1 (tested many times; macOS uses it every
  boot). Do it via sysfs: `echo 2 > /sys/bus/usb/devices/1-3/bConfigurationValue` after
  unloading `apple_touchbar`/`apple_ibridge` so they don't fight it back to config 1.

---

## 3. The DFR display protocol (complete reference)

All multi-byte fields are **little-endian**. This is the same protocol the mainline
**`appletbdrm`** (T2) kernel driver uses; we confirmed the T1 speaks it.

### 3.1 Control messages (a 32-byte "simple request")
```
struct simple_request {           // 32 bytes
  le16 unk_00 = 2
  le16 unk_02 = 0x1512
  le32 unk_04 = 0
  le32 unk_08 = 0
  le32 size   = 16               // = sizeof(struct) - sizeof(header[16])  (NOT 20!)
  le32 msg                       // one of the magics below
  u8   pad[8] = 0
  le32 size2  = 16
}
```
Message magics (ASCII, little-endian on the wire):
- `GINF` `0x47494e46` — GET_INFORMATION (returns panel geometry)
- `REDY` `0x52454459` — SIGNAL_READINESS
- `CLRD` `0x434c5244` — CLEAR_DISPLAY
- `UDCL` `0x5544434c` — UPDATE_COMPLETE (device→host, after a frame renders)

Responses carry their `msg` magic at **byte offset 16**. (A common gotcha: `size=20`
instead of `16` makes the device reject the command and return a short error header.)

### 3.2 Startup handshake (must be in this order)
1. Send `GINF`. Read responses until you get one tagged `GINF` (skip a stray startup
   `REDY` and any `STAT`/16-byte ack). The `GINF` info struct (65 bytes):
   - offset 32: `le32 width`  (= **2170**)
   - offset 36: `le32 height` (= **60**)
   - offset 40: `u8  bits_per_pixel` (= **24**)
   - offset 41: `le32 bytes_per_row` (= 6510 = 2170×3)
   - offset 53: `le32 pixel_format` (= `0x52474241`)
2. Send `REDY` (write-only).
Now you can send frames.

### 3.3 Frame message
```
struct fb_request_header {        // 48 bytes total before pixel data
  le16 unk_00 = 2
  le16 unk_02 = 0x12
  le32 unk_04 = 9
  le32 unk_08 = 0
  le32 size   = request_size - 16
  le16 unk_10 = 1
  u8   msg_id = timestamp & 0xff
  u8   pad[29] = 0
}
struct frame {                    // one rectangle (use one full-panel rect)
  le16 begin_x = 0
  le16 begin_y = 0
  le16 width   = 2170
  le16 height  = 60
  le32 buf_size = 2170*60*3 = 390600
  u8   buf[buf_size]              // pixel bytes (see §4 for layout/order)
}
struct footer {                   // 80 bytes, fixed
  pad[12]; le32 = 0xfffe;  pad[12]; le32 = 0x80001;
  le64 timestamp;          pad[12]; le32 = 0x80002;
  pad[20]; le32 = 0xffff;
}
// request = fb_request_header + frame + footer
```
- `timestamp` is any nonzero 64-bit value; put the same value in the footer and in
  `msg_id` (low byte). The device echoes it in the `UDCL` response (offset 32) — you can
  match it to confirm, but matching is optional.
- Partial updates: the protocol supports sub-rectangles (`begin_x/y`, smaller `width/
  height`, matching `buf_size`). We always send the full panel; damage-rects are an
  optimization opportunity (smaller frames = even higher fps for small changes).

### 3.4 Synchronous pacing (critical)
After sending a frame, **read from Bulk IN until you get a `UDCL`** (skip stray
`REDY`/`STAT`/16-byte acks), then send the next frame. The device renders one frame at a
time and will **stall and drop frames** if you fire-and-forget. With proper acking we
measured **~90–100 fps** of full-panel updates (≈35 MB/s). See `wait_udcl()` in the daemon.

---

## 4. Pixel format & geometry (the transform that makes it upright)

The device frame buffer is **column-major / transposed** relative to a normal raster, and
the panel is mounted such that a **vertical flip** is also needed. The verified pipeline,
starting from a normal upright `PIL` image of size **(W=2170, H=60)**:

```python
img = img.transpose(Image.FLIP_TOP_BOTTOM)   # 1) flip vertically
img = img.transpose(Image.TRANSPOSE)         # 2) WxH -> HxW (column-major)
buf = img.tobytes()                          # 3) row-major bytes of the transposed image
# buf is exactly 2170*60*3 bytes; send as the frame's buf[]
```
- **Color order: send R,G,B per pixel (PIL default). No swap needed** — verified with the
  4-quadrant diagnostic (red renders red, blue renders blue). (The T2 `appletbdrm` driver
  documents BGR888; on this T1 path RGB-order is correct. If you hand-build buffers and
  colors look swapped, flip R/B and re-test with the diag.)
- Equivalent index math if you build buffers without PIL: a physical pixel at
  `(X in 0..2170, Y in 0..60)` maps to device byte offset
  `((X)*60 + (59 - Y)) * 3` (= transpose + vertical flip), 3 bytes `R,G,B`.
- **Always design content for a 2170×60 canvas** (≈36:1). A square logo must be placed in
  a ~60×60 region, not stretched across the bar.

---

## 5. Performance (measured on this machine)

| Metric | Value |
|---|---|
| Full-panel frame | 390,600 px-bytes (~390 KB total request) |
| Sustained frame rate | **~90–100 fps** (synchronous, full panel) |
| Throughput | ~35 MB/s (~280 Mbps; USB 2.0 HS bulk) |
| Scroll @ 12 px/frame | ~1,078 px/s (crosses the bar in ~2 s) |
| Scroll @ 3 px/frame | ~270 px/s — comfortable readable "news ticker" |
| Latency per frame | ~10 ms (render + USB + UDCL) |

Practical implications:
- You are **not** frame-rate limited for any realistic widget. 90 fps is plenty for smooth
  scrolling, progress bars, VU meters, spinners, live graphs.
- For smooth *readable* scrolling, use a **small px/frame step (2–4)**, not a big one.
- Per-frame work in Python (PIL transpose + tobytes) is a few ms; fine. For very high
  refresh, precompute/transpose once and reuse, or use numpy.

---

## 6. Reference implementation (the daemon)

`t1_dfr_daemon.py` — run as root; it unloads the touchbar modules, switches to config 2,
claims the AV interface, does the handshake, then polls a `cmd` file and renders.

**Run:** `sudo python3 t1_dfr_daemon.py` (backgrounds fine). **Stop:** `echo quit > cmd`
(or SIGTERM/SIGINT — both restore config 1).

**Drive it** by writing one command per line into `./cmd` (the daemon re-reads the whole
file on change):
| command | effect |
|---|---|
| `green red blue white black yellow cyan magenta` | solid color |
| `diag` | 4-quadrant geometry test (TL=R TR=G BL=B BR=W) |
| `text <string>` | centered text, native 2170×60 |
| `image <path>` | blit an image (resized to panel) |
| `scroll <string>` | rainbow marquee, default 10 px/frame |
| `scroll <pixstep> <string>` | marquee at a given speed (e.g. `scroll 3 hello`) |
| `scrolltest` | speed sweep (12/30/70/150 px/frame) with fps logging |
| `rainbow` / `celebrate` | demo animations |
| `clear` | CLEAR_DISPLAY |
| `fliph`/`flipv`/`swaprb`/`reset`/`flags` | live transform toggles (for re-calibration) |
| `quit` | restore config 1 and exit |

**Render primitives to reuse** (import from the daemon / probe):
- `t1_dfr_probe.build_fb_request(W,H,buf,ts)` — frame bytes from a buffer.
- daemon `to_buf(img,W,H)` — the geometry transform (PIL image → device bytes).
- daemon `send_img(img)` — transform + send + wait for `UDCL`.
- `img_solid / img_text / img_diag`, `anim_wash / anim_marquee / anim_flash`.

For new tools, prefer **producing images and handing them to `send_img`** (or writing
`image <path>` to the daemon) over touching USB directly.

### 6.1 Closed-loop visual verification (dev superpower)
The bar is captured by a phone running **Iriun Webcam** = `/dev/video0`. To see your own
output programmatically:
```bash
ffmpeg -y -f v4l2 -i /dev/video0 -frames:v 8 -update 1 out.jpg -loglevel error
```
then view `out.jpg`. This is how the geometry was solved with no human in the loop — keep
it for regression-checking widgets.

---

## 7. Operational caveats & safety

- **Blank-until-reboot:** entering config 2 + sending `REDY` makes the T1 hand display
  control to the host; on exit the firmware does **not** reclaim it (the T1 simple-mode
  display path is a no-op). Module reload, fnmode cycling, and USB re-enumeration do **not**
  restore it — only a reboot does. So a render session ends with a blank bar until reboot.
  **Design tools to keep the daemon running** (own the bar persistently) rather than
  starting/stopping per action.
- **Coexistence:** while in config 2 the **webcam, ambient light sensor, and the stock
  Fn/media/brightness row are unavailable** (those interfaces belong to config 1 / the
  simple-mode driver). If a user needs the webcam or hardware Fn keys, you must hand the
  bar back (→ reboot) or solve coexistence (see §9).
- **Nothing is persistent:** the config switch and the dev watchdog are runtime-only; a
  reboot returns the machine fully to stock.
- **Safety:** poking the iBridge historically hard-froze this box via an ACPI power call
  (`SOCW`), which is disabled via the `skip_acpi_power=1` module param — **do not re-enable
  it**. The config-2 switch itself is safe. Keep a hardlockup watchdog armed during
  development (`sysctl kernel.hardlockup_panic=1 kernel.panic=10`, runtime-only) and ideally
  an external keyboard attached.

---

## 8. Touch input — SOLVED (2026-06-27)

**Touch works.** In config 2 the kernel binds `usbhid` to IF2 and exposes the digitizer as
an evdev device: **`/dev/input/event4` = "Apple Inc. iBridge Touchpad"**, reporting
`ABS_X` (0–32767), `ABS_Y` (0–127), and `BTN_TOUCH`. Read it with `python3-evdev`.

- **X mapping (verified, linear, NOT flipped):** `pixel_x = ABS_X / 32767 * 2170`.
  Demonstrated with a 4-button bar — all taps hit-tested to the correct button across
  dozens of presses (button i = `int(pixel_x / (2170/N))`).
- **Y mapping:** `ABS_Y` 0–127 over the 60px height (`pixel_y = ABS_Y/127*60`); direction
  not yet separately calibrated (less critical on a 60px-tall bar). TODO: top/bottom test.
- **Suppress desktop interpretation:** call `dev.grab()` (EVIOCGRAB) so touches don't move
  the cursor or trigger anything. (The volume/brightness "leak" seen mid-session was a
  config-1 transient from daemon restarts, not present in stable config 2 — but grab is the
  clean guard regardless.)
- **Reference code:** `touchfollow.py` (finger→dot), `button_demo.py` (tappable buttons,
  daemon `buttons <i>` command + `img_buttons`). Tap latency is fine; *smooth dragging*
  via the cmd-file relay is laggy (~6fps) + contact is reported intermittently — for
  sliders, **read event4 inside the daemon** (a touch thread) instead of the cmd-file IPC.
- **Multitouch:** this is single-touch (`BTN_TOOL_FINGER`); IF6 / `hidraw1` (EP 0x87,
  1024-byte reports) is likely a richer multitouch digitizer if you need gestures.

Older notes on the raw approach (still valid if you bypass the kernel):
- The touch/button data comes over the **HID interrupt endpoints in config 2**: **IF2
  (Interrupt IN `0x83`, 64-byte reports)** and/or **IF6 (Interrupt IN `0x87`, 1024-byte
  reports)**. IF6's large reports are likely the **multitouch digitizer** (x/y/contacts);
  IF2 is likely simple key/region events.
- Approach: in the daemon's config-2 setup, also claim the HID interface and spawn a
  reader thread doing `ep.read()` on the interrupt endpoint; log raw reports while touching
  known on-screen regions (use the webcam loop to correlate). Reverse-engineer the report
  layout (touch down/up, X along the 2170 axis, Y along 60). Then map touch X→widget hit
  testing.
- Note the digitizer's coordinate system may need the same flip/transpose reasoning as the
  display; calibrate by touching the rendered `diag` quadrants and logging coordinates.
- Once taps are decoded, you have a full **input+output** surface: real buttons, sliders
  (track X while held), swipes.

---

## 9. Coexistence & the kernel-driver endgame

The userspace/libusb approach is perfect for prototyping but has the config-2 trade-offs
above. The clean long-term path:
- **Add the T1 USB id + interface match to the mainline `appletbdrm` DRM driver** so the
  bar becomes a real `/dev/dri` framebuffer the host owns full-time. Then it never returns
  to simple mode (blank-till-reboot caveat becomes moot) and standard tools (KMS, even a
  tiny compositor) can draw to it. Our protocol findings (geometry transform, RGB order,
  synchronous pacing, config-2 binding) are exactly what such a patch needs.
- Coexistence with webcam/ALS would still require deciding who owns the composite device;
  worth checking whether config 2's UVC interface can drive the camera concurrently.

---

## 10. Roadmap: tools & utilities to build

Tiered by effort. All can be built as **producers feeding the daemon**.

**A. Quick wins (output-only, build today)**
- `tb-clock` — live clock / date, updates once a second.
- `tb-notify` — show a transient message/toast (scroll long ones).
- `tb-sysmon` — CPU/GPU/RAM/temperature gauges + sparkline graphs (read `/proc`,
  `sensors`, `nvidia-smi`/`amdgpu` sysfs). This was your gaming use-case.
- `tb-nowplaying` — current track via MPRIS (`playerctl`/DBus): title scrolling + a
  progress bar. (Display only; controls need §8.)
- `tb-battery`, `tb-net` (up/down rate), `tb-pomodoro`, audio **VU meter** (PipeWire).

**B. Context engine (the original goal)**
- `tb-context` — a focus-watcher (GNOME Wayland: a small shell extension or
  `gdbus`/`wlr-foreign-toplevel` where available) that maps the **active app** to a
  **layout**: Spotify → now-playing widget; Chrome/Edge → tab/URL widget; a Steam game →
  the sysmon gauges; default → clock. It just emits `image`/`text` commands to the daemon.

**C. Interactive (needs §8 touch decoding first)**
- A **widget/button framework**: define regions with labels/icons + callbacks; render them;
  hit-test incoming touches. Then real buttons (play/pause, new-tab, "open Steam overlay"),
  **sliders** (volume by dragging), and tab strips.

**D. Platform**
- Promote the render core to a small library (`libt1dfr`) with a clean API
  (`open()/info()/blit(rgb_image)/close()`), and a stable IPC (socket instead of the `cmd`
  file) so multiple producers can share the bar via a simple z-ordered "layout manager".
- The kernel `appletbdrm` T1 patch (§9) as the upstreamable endgame.

**Suggested architecture for B/D:** a long-lived **bar server** (owns the device) +
a **layout manager** (decides which widget is active) + **widget plugins** (each renders a
2170×60 or a sub-rect). Producers talk to the server over a unix socket; the server
serializes frames and handles pacing. This avoids every tool fighting over config 2.

---

## 11. Developer quickstart

```bash
cd ~/touchbar-port/dfr-experiment
sudo sysctl -w kernel.hardlockup_panic=1 kernel.panic=10   # dev safety net (runtime only)
sudo python3 t1_dfr_daemon.py &                            # owns the bar
echo "text Hello from my tool" > cmd                       # render something
echo "scroll 3 a smooth readable ticker message here   " > cmd
# verify what's on the bar:
ffmpeg -y -f v4l2 -i /dev/video0 -frames:v 8 -update 1 /tmp/tb.jpg -loglevel error && xdg-open /tmp/tb.jpg
echo quit > cmd                                            # stop (bar blanks until reboot)
```
Requirements: `python3-usb` (pyusb), `python3-pil` (Pillow), `ffmpeg`, root (for USB +
module unload). Panel constants: `W=2170, H=60`, RGB, transform = flipV + transpose.

---

## Appendix: file map
- `DEVGUIDE.md` — this guide.
- `FINDINGS.md` — chronological research journal (how each fact was discovered).
- `t1_dfr_probe.py` — low-level: config switch, handshake, single frame; `--probe`/`--draw`.
- `t1_dfr_daemon.py` — reference render daemon (protocol + geometry + primitives + cmd loop).
- `cmd` — the daemon's command file.

*First known T1-Touch-Bar-on-Linux custom rendering. Built 2026-06-26/27.*
