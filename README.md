# t1-touchbar

**Make your 2017 MacBook Pro (T1) Touch Bar work on Linux.**

Install it and the Touch Bar lights up with a real control strip — **Esc, brightness,
keyboard backlight, media (⏮ ▶ ⏭), volume**, and **hold the physical Fn key for F1–F12** —
running from boot, with the native on-screen volume/brightness OSD. That's the default, and it
works on its own, with no other software.

Underneath, it's a clean **display + input driver** for the T1 (iBridge) Touch Bar: it speaks
the device's **DFR display protocol** and reads its **touch digitizer**, so the bar is also a
fully programmable 2170×60 surface — render anything at ~90 fps and get mapped touch events
back. So when the default strip isn't enough, you can **design your own** (see *Customize*).

> The 2016–2017 MacBook Pros (MacBookPro13,x / 14,x) have a **T1** Touch Bar. Mainline Linux
> only ever supported the **T2** models — on a T1 the bar was just a black strip. As far as the
> public record shows, this is the first time a T1 Touch Bar has been driven from Linux, with
> the normal keys *and* custom graphics. Full reverse-engineering story:
> [`docs/DEVGUIDE.md`](docs/DEVGUIDE.md).

## Two ways to use it

**1 · Just make it work (the default).** Install the driver + the control strip and your Touch
Bar behaves like a normal Mac control strip — esc / brightness / keyboard-backlight / media /
volume, and hold-Fn for F1–F12 — starting on every boot. **Standalone; nothing else required.**
This is the priority path: *just make my Touch Bar work.*

**2 · Customize (optional).** The strip is built on a small public Python/socket API, so you can
design your own layouts, widgets, and actions — by hand against the library, or with the
**t1bar-studio** UI tool (a separate project). The core driver stays a thin, pure surface; all
the opinion lives on top. You opt into this; it's never needed for path 1.

## Requirements

- A MacBook Pro with a **T1** chip (USB `05ac:8600` "iBridge"), running Linux. *(Not T2 — those
  are handled by the mainline `appletbdrm`.)*
- **Root** — USB control transfers + a brief kernel-module unload.
- **System packages:**
  - `libusb-1.0` — always (USB access).
  - `build-essential` + `python3-dev` — to build **`evdev`** for **touch** (tapping the strip's
    buttons). There's no PyPI wheel, so without these the strip *displays* but the buttons don't
    respond.
  - `playerctl` — the media ⏮ ▶ ⏭ buttons (volume uses `wpctl` / PipeWire).
  - *(optional)* `ffmpeg` + `v4l2loopback` — only for the webcam bridge.
- **Python packages:** `pyusb`, `Pillow` (both ship wheels, incl. Python 3.14). `evdev` is an
  optional extra (`[touch]`) and is lazy-imported, so the display path works without it.

## Install — "just make it work"

> **Not on PyPI yet** — install from a clone. The one git clone contains everything (the driver
> at the root, the studio app under `studio/`).

The installer bootstraps the prerequisites and offers the **Basic** vs **Full** choice:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar
cd t1-touchbar
sudo ./install.sh           # asks: Basic (just the strip) or Full (+ studio app)
#   sudo ./install.sh --basic   # non-interactive
#   sudo ./install.sh --full    # ...also installs the customization studio
#   --dry-run shows exactly what it would do, changing nothing
```

**Basic** installs the driver + control strip and enables it on boot — your Touch Bar just works.
**Full** adds the **t1bar studio** app for designing your own bar (see *Customize*). The installer
detects the T1, installs the apt prerequisites, sets up a venv, and wires the systemd service.

<details><summary>Prefer to do it by hand?</summary>

```bash
sudo apt install -y python3-pip python3-venv git libusb-1.0-0 build-essential python3-dev playerctl
python3 -m venv .venv && . .venv/bin/activate
pip install '.[touch]'            # omit [touch] for a display-only (non-tappable) install
sudo .venv/bin/t1touchbar-strip   # welcome, then the control strip
sudo bash packaging/install-service.sh   # ...and to start it on every boot
```
</details>

That's the whole basic experience. Everything below is for path 2 — building your own bar.

---

## Customize — build your own bar

The same driver that powers the strip is a public API. Consume it as a **Python library** or as
a language-agnostic **Unix-socket daemon**.

### Python

```python
from t1touchbar import Device, TouchReader
from PIL import Image, ImageDraw

with Device() as bar:                       # switches config, handshakes, restores on exit
    w, h = bar.width, bar.height            # 2170 x 60
    img = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(img).text((20, 10), "Hello from Linux", fill=(0, 255, 120))
    bar.blit(img)                           # ~90 fps full-panel; geometry/colour handled

    def on_touch(ev):                       # ev.state ('down'/'move'/'up'), ev.x, ev.y
        print(ev)
    tr = TouchReader(w, h); tr.start(on_touch)   # needs the [touch] extra
    input("touch the bar; enter to quit\n")
    tr.stop()
```

### Socket daemon (any language)

```bash
sudo t1touchbar serve            # owns the device; prints the socket path
```

Connect to the Unix socket (default `/tmp/t1touchbar.sock`) and exchange length-prefixed
messages — `FRAME` / `IMG` / `CLEAR` in, `TOUCH` events out. Full spec in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md). A Python client is included:

```python
from t1touchbar.client import Client
c = Client()
c.on_touch(lambda ev: print(ev))     # {'x':418, 'y':30, 'state':'down'}
c.image("logo.png")
```

See [`examples/`](examples/): reactive finger-tracking ripples, tappable buttons, and a
scrolling marquee — all built on the public API.

## Camera — webcam *and* Touch Bar together

The iBridge's config-2 session exposes the FaceTime camera (as **H.264**) right next to the
display interface, so they coexist. `t1touchbar-camera` captures that stream in userspace and
pipes it onto a **dedicated v4l2loopback node** — any app then opens it like a normal camera:

```bash
sudo modprobe v4l2loopback                 # once (a real install does this at boot)
sudo t1touchbar-camera --print-device      # prints e.g. DEVICE=/dev/video3, then streams
#   -> point Howdy / Zoom / your browser at that /dev/video* node
```

By design this is **invisible to your real camera**: it creates its *own* loopback node (never
touches `/dev/video0` or the default device), and when it isn't running the stock config-1
webcam behaves exactly as before. In Python:

```python
from t1touchbar import LoopbackBridge
with LoopbackBridge(size="1280x720") as cam:
    print("camera at", cam.device)         # stream until the block exits
```

> Requires the `v4l2loopback` kernel module and `ffmpeg`. Raw H.264 frames are available without
> either via `t1touchbar.Camera(...).stream()` if you want to handle decoding yourself.

## Important caveats

- **One owner at a time.** Only one process may hold the device (config 2). The strip, the
  daemon, and a custom script are mutually exclusive — stop one to run another.
- **Blank until reboot.** Exiting hands display control back, and on T1 the firmware does not
  reclaim the panel — it stays blank until a reboot. Keep the driver/strip running while you want
  the bar lit (the service does exactly this).
- **Coexistence.** The built-in **webcam** *can* run alongside the bar (see Camera). The
  ambient-light sensor and the stock firmware Fn/media row are unavailable while the driver owns
  config 2 — the strip provides those keys instead.
- **Nothing is persistent** — a reboot fully restores the stock Touch Bar.

## How it works

The driver switches the iBridge to its config-2 ("OS X") configuration, claims the Audio/Video
interface, and speaks the **DFR** protocol (the same one the mainline `appletbdrm` driver uses on
T2 Macs). Images are transposed + flipped into the device's buffer layout and streamed with
synchronous pacing. Touch comes from the digitizer the kernel exposes as an evdev "iBridge
Touchpad", with `ABS_X` / `ABS_Y` mapped to pixels. It runs **entirely in userspace over libusb**
— it does **not** require the out-of-tree T1 kernel driver, and because it never loads
`apple-ibridge` it sidesteps that driver's ACPI-power hard-lock. Details and the
reverse-engineering journal are in [`docs/`](docs/).

## License

MIT — see [LICENSE](LICENSE). Build whatever you want on top.

## Acknowledgements

Protocol shape informed by the mainline Linux `appletbdrm` (T2) driver and imbushuo's Windows
DFR work. T1 support, geometry, touch, and this driver are an independent implementation.
