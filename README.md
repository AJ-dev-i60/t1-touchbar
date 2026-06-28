# t1-touchbar

A **display + input driver for the Apple T1 (iBridge) MacBook Pro Touch Bar on Linux.**

The T1 Touch Bar (MacBookPro13,x / 14,x — the 2016–2017 models) is a 2170×60 display
driven by a coprocessor over USB. On Linux only its three fixed firmware layouts
(Esc / function keys / media keys) were ever reachable — until now. `t1-touchbar`
speaks the device's **DFR display protocol** and reads its **touch digitizer**, giving
you a fully programmable, finger-trackable surface: render anything at ~90 fps and get
mapped touch events back.

> As far as the public record shows, this is the first time the T1 Touch Bar has been
> driven with custom graphics from Linux. See [`docs/DEVGUIDE.md`](docs/DEVGUIDE.md) for
> the full reverse-engineering story and protocol reference.

This driver is intentionally **thin**: it does *display output*, *touch input*, and
*device lifecycle* — and nothing else. Graphics, animation, layouts, widgets, and
action-mapping belong to tools built **on top** of it.

## Features

- **Display** — blit any image (PIL or raw RGB) to the bar; ~90 fps full-panel updates,
  correct geometry and color handled for you.
- **Touch** — `down` / `move` / `up` events with coordinates mapped to panel pixels.
- **Camera** — the FaceTime webcam lives in the same config as the display, so the bar and
  the camera can run **at the same time**. `t1touchbar-camera` exposes it as an ordinary
  `/dev/video*` (via v4l2loopback) for Howdy / Zoom / browsers.
- **Two ways to consume it** — a Python library (`import t1touchbar`) *or* a Unix-socket
  daemon (`t1touchbar serve`) so a tool in any language can drive it over a stable IPC.

## Requirements

- A MacBook Pro with a **T1** chip (USB `05ac:8600` "iBridge"), running Linux.
- **Root** — the driver issues USB control transfers and briefly unloads the kernel
  `apple_touchbar` / `apple_ibridge` modules.
- System: `libusb-1.0`. Python deps (auto-installed): `pyusb`, `Pillow`, `evdev`.

## Install

```bash
pip install t1-touchbar          # from PyPI (once published)
# or, from a clone:
pip install .
```

## Quick start — Python

```python
from t1touchbar import Device, TouchReader
from PIL import Image, ImageDraw

with Device() as bar:                       # switches config, handshakes, restores on exit
    w, h = bar.width, bar.height            # 2170 x 60
    img = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(img).text((20, 10), "Hello from Linux", fill=(0, 255, 120))
    bar.blit(img)

    def on_touch(ev):                       # ev.state, ev.x, ev.y
        print(ev)
    tr = TouchReader(w, h); tr.start(on_touch)
    input("touch the bar; enter to quit\n")
    tr.stop()
```

## Quick start — socket daemon (any language)

```bash
sudo t1touchbar serve            # owns the device; prints the socket path
```

Then connect to the Unix socket (default `/tmp/t1touchbar.sock`) and exchange
length-prefixed messages — `FRAME` / `IMG` / `CLEAR` in, `TOUCH` events out. Full spec in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md). A Python client is included:

```python
from t1touchbar.client import Client
c = Client()
c.on_touch(lambda ev: print(ev))     # {'x':418, 'y':30, 'state':'down'}
c.image("logo.png")
```

## Examples

See [`examples/`](examples/): reactive finger-tracking ripples, tappable buttons, and a
scrolling marquee — all built on the public API.

## Control strip (companion app)

The repo also ships **`t1touchbar-strip`** — a reference *control strip* app built on the
driver, so a fresh install lands on something that visibly works without any design tool.
It plays a welcome showcase, then shows a functional strip — **Esc, brightness, keyboard
backlight, media, volume** (with the native on-screen OSD), live **play/pause** state, and
**hold the physical Fn key for F1–F12**. It's the *opinionated* layer; the core driver
stays pure.

```bash
sudo t1touchbar-strip               # welcome, then the control strip
```

**Auto-start on boot** (optional — it takes over the bar; disable anytime):

```bash
sudo bash packaging/install-service.sh        # installs + enables the systemd service
sudo systemctl disable --now t1touchbar-strip # ...and to hand the bar back
```

## Camera — webcam *and* Touch Bar together

The iBridge's config-2 session exposes the FaceTime camera (as **H.264**) right next to the
display interface, so they coexist. `t1touchbar-camera` captures that stream in userspace and
pipes it onto a **dedicated v4l2loopback node** — any app then opens it like a normal camera:

```bash
sudo modprobe v4l2loopback                 # once (a real install does this at boot)
sudo t1touchbar-camera --print-device      # prints e.g. DEVICE=/dev/video3, then streams
#   -> point Howdy / Zoom / your browser at that /dev/video* node
```

By design this is **invisible to your real camera**: it creates its *own* loopback node
(never touches `/dev/video0` or the default device), and when it isn't running the stock
config-1 webcam behaves exactly as before. In Python:

```python
from t1touchbar import LoopbackBridge
with LoopbackBridge(size="1280x720") as cam:
    print("camera at", cam.device)         # stream until the block exits
```

> Requires the `v4l2loopback` kernel module and `ffmpeg`. The raw H.264 frames are available
> without either via `t1touchbar.Camera(...).stream()` if you want to handle decoding yourself.

## Important caveats

- **One owner at a time.** Only one process may hold the device (config 2).
- **Blank until reboot.** Exiting hands display control back, and on T1 the firmware does
  not reclaim the panel — it stays blank until a reboot. Keep the driver running while you
  want the bar lit (the daemon is built for exactly this).
- **Coexistence.** The built-in **webcam** *can* run alongside the bar — see the Camera
  section above. The ambient-light sensor and the stock Fn/media key row remain unavailable
  while the driver owns config 2.
- **Nothing is persistent** — a reboot fully restores the stock Touch Bar.

## How it works

The driver switches the iBridge to its config-2 ("OS X") configuration, claims the
Audio/Video interface, and speaks the **DFR** protocol (the same one the mainline
`appletbdrm` driver uses on T2 Macs). Images are transposed + flipped into the device's
buffer layout and streamed with synchronous pacing. Touch comes from the digitizer the
kernel exposes as an evdev "iBridge Touchpad", with `ABS_X`/`ABS_Y` mapped to pixels.
Details and the reverse-engineering journal are in [`docs/`](docs/).

## License

MIT — see [LICENSE](LICENSE). Build whatever you want on top.

## Acknowledgements

Protocol shape informed by the mainline Linux `appletbdrm` (T2) driver and imbushuo's
Windows DFR work. T1 support, geometry, touch, and this driver are an independent
implementation.
