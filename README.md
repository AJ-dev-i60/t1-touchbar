# t1-touchbar

**Make your 2017 MacBook Pro (T1) Touch Bar work on Linux.**

On the 2016–2017 MacBook Pros (MacBookPro13,x / 14,x) the Touch Bar is a **T1** ("iBridge")
device, and mainline Linux only ever supported the **T2** models — so the bar was just a black
strip. This project lights it up, two ways:

- **Just make it work** — the T1's **own firmware** draws the normal control strip (Esc,
  brightness, keyboard backlight, media, volume, and hold-**Fn** for **F1–F12**), exactly like
  macOS. Set-and-forget; your webcam keeps working too. *This is the default.*
- **Customize (optional)** — hand the whole bar to the **t1bar studio** app and design your own,
  with a fully programmable 2170×60 pixel surface and finger touch.

> ⚠️ **One safety note up front.** On these 2016/2017 models there's an ACPI power-on call
> (`ASOC.SOCW(1)`) that **hard-freezes the machine** — recoverable only by holding the power button.
> The driver **skips it by default on this hardware** (it detects the T1 model), and the installer
> additionally pins `skip_acpi_power=1`, so the supported path is safe. The *only* way to hit the
> freeze is to force the call back on with `skip_acpi_power=0` — don't, unless you know exactly why.
> See [Troubleshooting](#troubleshooting).

```bash
curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
```

…then choose **Basic** (just make it work) or **Full** (+ studio). No `git` needed — the
installer fetches itself.

> As far as the public record shows, this is the first time a T1 Touch Bar has been driven from
> Linux with **both** the normal keys *and* custom graphics. Reverse-engineering story:
> [`docs/DEVGUIDE.md`](docs/DEVGUIDE.md).

## Two ways to use it — two different engines

|  | **Basic** (default) | **Full** (optional) |
|---|---|---|
| What you get | the normal firmware control strip | design your own bar (Scenes) |
| Who draws the bar | the **T1 firmware** | the **host**, custom pixels |
| Engine | the **`apple-ib-drv` kernel driver** ([`apple-ib-drv/`](apple-ib-drv/)) | userspace libusb + **t1bar studio** ([`studio/`](studio/)) |
| USB config | config 1 | config 2 |
| Webcam | works natively | routed through a bridge |
| Footprint | set-and-forget; no daemon | a service owns the bar; needs a reboot to switch |

They are **mutually exclusive** (only one process can own the bar). Switching between them is a
reboot. **Uninstalling Full returns you to Basic** — the plain firmware strip.

> **Which should I pick?** If you just want the bar to behave like it does on macOS and never
> think about it again: **Basic.** If you want to design custom layouts, colors, and behaviours:
> **Full** (you can always add it later, or remove it to go back).

## Requirements

- A MacBook Pro with a **T1** chip (USB `05ac:8600` "iBridge"), running Linux. *(Not T2 — those
  are handled by the mainline `appletbdrm`.)*
- **Root** for installation.
- **Basic** pulls: `build-essential`, `linux-headers-$(uname -r)`, `dkms` (to build the kernel
  module; DKMS rebuilds it automatically on kernel upgrades).
- **Full** additionally pulls: Python/venv, GTK (`python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
  python3-gi-cairo`) for the editor, `playerctl`, and `ffmpeg` + `v4l2loopback-dkms` for the
  webcam bridge.

`install.sh` installs all of these for you.

## Install

The one-liner (no git, no clone — the installer fetches the repo itself):

```bash
curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
#   ...| bash -s -- --basic     # non-interactive: firmware strip only
#   ...| bash -s -- --full      # ...also the studio (custom bar)
```

Or from a clone, if you prefer:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar && cd t1-touchbar
sudo ./install.sh            # interactive: Basic or Full
#   --basic / --full / --dry-run / --yes / --no-service
```

- **Basic** → DKMS-builds the firmware driver, sets the critical `skip_acpi_power=1` parameter,
  and loads it. **A reboot finishes the install — plan on it.** On an already-running system the
  generic HID drivers (`hid-generic`/`hid-sensor-hub`) have *already* claimed the iBridge, so the
  live load may bind nothing and the bar stays dark; after one reboot the udev rule forces config 1
  early, the driver binds, and the strip comes up automatically on every boot.
- **Full** → installs the studio engine + webcam bridge, stands the firmware driver down, and
  asks you to **reboot** to hand the bar to the studio. Then open **"t1bar studio"** to design it.

## The firmware driver (Basic)

[`apple-ib-drv/`](apple-ib-drv/) is the kernel module that does Basic — a fork of
[`t2linux/apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) with five fixes for Linux 7.x on
the T1 (the key one being `skip_acpi_power`, which avoids an ACPI hard-lock at load). It's **GPL-2.0**
(the rest of this repo is MIT). See [`apple-ib-drv/README.md`](apple-ib-drv/README.md).

---

## Customize — the programmable surface (Full)

Full is built on a thin **display + input driver** (this repo's root package, `t1touchbar`): it
speaks the device's **DFR** protocol and reads its **touch digitizer**, giving a programmable
2170×60 surface — render anything at ~90 fps and get mapped touch events back. The **t1bar studio**
app ([`studio/`](studio/)) is the design tool on top; you can also drive it directly:

### Python

```python
from t1touchbar import Device, TouchReader
from PIL import Image, ImageDraw

with Device() as bar:                       # switches config, handshakes, restores on exit
    w, h = bar.width, bar.height            # 2170 x 60
    img = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(img).text((20, 10), "Hello from Linux", fill=(0, 255, 120))
    bar.blit(img)                           # ~90 fps full-panel; geometry/colour handled

    def on_touch(ev): print(ev)             # ev.state ('down'/'move'/'up'), ev.x, ev.y
    tr = TouchReader(w, h); tr.start(on_touch)   # needs the [touch] extra (evdev)
    input("touch the bar; enter to quit\n"); tr.stop()
```

### Socket daemon (any language)

```bash
sudo t1touchbar serve            # owns the device; prints the socket path
```

Connect to the Unix socket (default `/tmp/t1touchbar.sock`) and exchange length-prefixed messages
— `FRAME` / `IMG` / `CLEAR` in, `TOUCH` events out. Spec in [`docs/PROTOCOL.md`](docs/PROTOCOL.md);
a Python `Client` is included. See [`examples/`](examples/) for finger-tracking ripples, tappable
buttons, and a marquee.

## Camera — webcam *and* Touch Bar together (Full)

In Basic the firmware uses config 1, so the FaceTime webcam is just an ordinary camera. In **Full**
the studio takes config 2, where the camera is exposed as **H.264** — so `t1touchbar-camera`
captures it and pipes it onto a **dedicated v4l2loopback node** any app can open:

```bash
sudo t1touchbar-camera --print-device   # prints e.g. DEVICE=/dev/video3, then streams
#   -> point Howdy / Zoom / your browser at that /dev/video* node
```

It creates its *own* loopback (never touches `/dev/video0`), so your real camera is untouched.
Requires `v4l2loopback` + `ffmpeg` (the installer handles this in Full).

## Caveats (the Full / studio path only)

These apply to **Full** (host-driven, config 2) — **not** to Basic, which is plain firmware:

- **One owner at a time.** Only one process may hold the device.
- **Blank until reboot.** Once the host has driven the panel, exiting hands control back but the
  firmware doesn't reclaim it — it stays blank until a reboot. The studio service holds it lit; this
  is why switching engines is a reboot.
- **Coexistence.** The webcam runs alongside the bar via the bridge (above); the ambient-light
  sensor and firmware key row are unavailable while the studio owns config 2.
- **Nothing is persistent at the device level** — a reboot into Basic fully restores the firmware bar.

## Tested on

| Model | Kernel | Distro | Result |
|---|---|---|---|
| MacBookPro14,3 | 7.0.0-27-generic | Ubuntu 26.04 | ✅ Basic: DKMS builds, binds after reboot, webcam intact |

Other 13,x/14,x models and kernels should work but are unverified — the kernel-7 fixes are what make
this build on bleeding-edge kernels. Because DKMS rebuilds the module on every kernel upgrade and a
broken rebuild fails **silently**, after any `apt upgrade` that bumps the kernel, check the bar still
lights and run `dkms status` — it should list `apple-ib-drv/0.1, <new-kernel>: installed`.

## Troubleshooting

**The healthy signature.** After a successful boot in Basic, you should see all of these:

```bash
lsmod | grep apple_touchbar                      # apple_touchbar is loaded
cat /sys/bus/usb/devices/*/idProduct | grep 8600 # the iBridge is on the bus
dmesg | grep -i 'skip_acpi_power'                # "skip_acpi_power: NOT running ASOC.SOCW(1)…"
dmesg | grep -i 'apple-touchbar.*input:'         # the virtual Touch Bar HID was created
# and the iBridge's bConfigurationValue should read 1 (not blank)
```

The installer prints a self-check at the end that looks for these for you.

**The bar is dark right after install (before a reboot).** Expected — see the Basic note above.
**Reboot once.** The live `modprobe` can't claim interfaces the generic HID drivers already hold.

**Still dark after a reboot → `usbmuxd`.** `usbmuxd` (iOS-device tethering) ships a udev rule that
also matches the iBridge `05ac:8600`; if it grabs the device first, the HID driver can't initialise
and the bar stays dark. It didn't bite on the tested machine, but if yours is dark after a reboot:

```bash
sudo sed -i '/05ac.*8600/d' /lib/udev/rules.d/39-usbmuxd.rules   # drop the iBridge matches
#   ...or, if you don't tether iPhones/iPads at all:  sudo systemctl mask usbmuxd
sudo udevadm control --reload && sudo reboot
```

**"module verification failed … tainting kernel".** Harmless — an out-of-tree DKMS module with
Secure Boot **off**. If you run with **Secure Boot on**, DKMS self-signs with a MOK that you must
enrol once (`sudo mokutil --import /var/lib/dkms/mok.pub`, set a password, reboot, confirm in the
blue MOK screen) or the kernel will refuse to load the module.

**Don't force the power-on AML.** The driver skips the freeze call by default on T1 hardware (and
the installed `/etc/modprobe.d/apple-touchbar.conf` pins `skip_acpi_power=1` on top), so a normal
load is safe — but `modprobe apple_ibridge skip_acpi_power=0` *forces* `ASOC.SOCW(1)` and
hard-freezes the machine. Don't pass `=0`. Recovery if a boot ever misbehaves: at GRUB press `e`
and add `modprobe.blacklist=apple_ibridge,apple_touchbar` to the kernel line.

## How it works

**Basic** loads the `apple-ib-drv` kernel modules in config 1 and tells the T1 to render its
firmware function/control layouts (the bar draws itself; touches come back as key events).
**Full** switches the iBridge to its config-2 ("OS X") configuration, claims the Audio/Video
interface, and speaks the **DFR** protocol (the same one mainline `appletbdrm` uses on T2 Macs),
streaming host-rendered frames and reading the touch digitizer. The two never run at once.

## Trust & authorship

This is new code, and it asks for root to build a kernel module that can freeze your hardware — so
healthy skepticism is correct. A few things to make an informed decision:

- **Read before you run.** The Basic path only writes to `/etc/modprobe.d`, `/etc/udev/rules.d`,
  `/etc/modules-load.d`, and DKMS under `/usr/src` — no network beyond `apt`, no piping remote
  content to a shell. If you'd rather not pipe `curl` into `bash`, clone and read first
  (`git clone … && less install.sh && sudo ./install.sh`). The one-liner just fetches this same
  repo and runs the same script.
- **The commit trailers.** Commits are authored by **AJ-dev-i60** and co-authored by **Claude**
  (this project is built with Claude Code as a pair-programmer — that's what the `Claude` /
  `Co-Authored-By` trailers are). Not a sign of tampering.
- **Security policy / how to report:** [`SECURITY.md`](SECURITY.md).

## License

The userspace driver, studio, and tooling are **MIT** (see [LICENSE](LICENSE)). The bundled kernel
driver in [`apple-ib-drv/`](apple-ib-drv/) is **GPL-2.0** (its own `LICENSE`).

## Acknowledgements

The firmware driver is a fork of `t2linux/apple-ib-drv`. The DFR protocol shape was informed by the
mainline Linux `appletbdrm` (T2) driver and imbushuo's Windows work. T1 support, geometry, touch,
and the userspace driver are an independent implementation.
