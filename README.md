# t1-touchbar

**Make your 2017 MacBook Pro (T1) Touch Bar work on Linux.**

On the 2016–2017 MacBook Pros (MacBookPro13,x / 14,x) the Touch Bar is a **T1** ("iBridge")
device, and mainline Linux only ever supported the **T2** models — so the bar was just a black
strip. This makes it work: the T1's **own firmware** draws the normal control strip (Esc,
brightness, keyboard backlight, media, volume, and hold-**Fn** for **F1–F12**), exactly like
macOS. Set-and-forget; your webcam keeps working too.

It's a small out-of-tree kernel driver (a DKMS-packaged fork of `apple-ib-drv`) with the fixes
needed to build and bind on **Linux 7.x** for the T1 — validated end-to-end on real hardware.

> ⚠️ **One safety note up front.** On these 2016/2017 models there's an ACPI power-on call
> (`ASOC.SOCW(1)`) that **hard-freezes the machine** — recoverable only by holding the power button.
> The driver **skips it by default on this hardware** (it detects the T1 model), and the installer
> additionally pins `skip_acpi_power=1`, so the supported path is safe. The *only* way to hit the
> freeze is to force the call back on with `skip_acpi_power=0` — don't, unless you know exactly why.
> See [Troubleshooting](#troubleshooting).

```bash
curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
```

…or, if you'd rather clone it first:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar && cd t1-touchbar && sudo ./install.sh
```

The `curl` line needs no `git` (the installer fetches itself); either way, **reboot** to finish.

> **What this is — and what it builds on.** The T1 Touch Bar has worked on Linux for *years*, thanks
> to the [`apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) / roadrunner2 community — but only
> up to **kernel 6.x**. A 2023 HID change broke it on newer kernels, and Linux **7.0** only released
> in **April 2026**, so on current systems the bar went dark again. This is the driver that makes the
> T1 Touch Bar work on **Linux 7**: the community's kernel-6 work **ported forward** to build and bind
> on the 7.x series, and made freeze-safe by default. It stands entirely on the shoulders of the
> people who got it working on kernel 6.

## Requirements

- A MacBook Pro with a **T1** chip (USB `05ac:8600` "iBridge"), running Linux. *(Not T2 — those
  are handled by the mainline `appletbdrm`.)*
- **Root** for installation.
- The installer pulls `build-essential`, `linux-headers-$(uname -r)`, and `dkms` (to build the
  kernel module; DKMS rebuilds it automatically on kernel upgrades). It targets apt-based distros
  (Ubuntu/Debian).

## Install

The one-liner (no git, no clone — the installer fetches the repo itself):

```bash
curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
#   ...| bash -s -- --yes        # non-interactive
```

Or from a clone, if you'd rather read it first:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar && cd t1-touchbar
sudo ./install.sh
#   --yes / --dry-run / --no-service
```

It DKMS-builds the firmware driver, sets the critical `skip_acpi_power=1` parameter, installs the
udev rule that forces the iBridge into config 1 (which exposes both the Touch Bar HID *and* the
webcam), and loads it. **A reboot finishes the install — plan on it.** On an already-running system
the generic HID drivers (`hid-generic`/`hid-sensor-hub`) have *already* claimed the iBridge, so the
live load may bind nothing and the bar stays dark; after one reboot the udev rule wins the race, the
driver binds, and the strip comes up automatically on every boot.

## The firmware driver

[`apple-ib-drv/`](apple-ib-drv/) is the kernel module — a fork of
[`t2linux/apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) with fixes for Linux 7.x on the T1
(the key one being `skip_acpi_power`, which avoids the ACPI hard-lock at load, plus the HID/ACPI API
updates that make it build and bind on kernel 7). It's **GPL-2.0** (its own `LICENSE`); the installer
and docs are MIT. See [`apple-ib-drv/README.md`](apple-ib-drv/README.md) for the full fix list.

## Tested on

| Model | Kernel | Distro | Result |
|---|---|---|---|
| MacBookPro14,3 | 7.0.0-27-generic | Ubuntu 26.04 | ✅ DKMS builds, binds after reboot, keys + OSD work, webcam intact |

Other 13,x/14,x models and kernels should work but are unverified — the kernel-7 fixes are what make
this build on bleeding-edge kernels. Because DKMS rebuilds the module on every kernel upgrade and a
broken rebuild fails **silently**, after any `apt upgrade` that bumps the kernel, check the bar still
lights and run `dkms status` — it should list `apple-ib-drv/0.1, <new-kernel>: installed`.

## Troubleshooting

**The healthy signature.** After a successful boot, you should see all of these:

```bash
lsmod | grep apple_touchbar                      # apple_touchbar is loaded
cat /sys/bus/usb/devices/*/idProduct | grep 8600 # the iBridge is on the bus
dmesg | grep -i 'skip_acpi_power'                # "skip_acpi_power: NOT running ASOC.SOCW(1)…"
dmesg | grep -i 'apple-touchbar.*input:'         # the virtual Touch Bar HID was created
# and the iBridge's bConfigurationValue should read 1 (not blank)
```

The installer prints a self-check at the end that looks for these for you.

**The bar is dark right after install (before a reboot).** Expected. **Reboot once.** The live
`modprobe` can't claim interfaces the generic HID drivers already hold. The installer *deliberately*
doesn't force-unbind them and rebind live: doing so would exercise the device's bind/power paths
(the same family as the resume `SOCW` call) outside a clean boot, for no real benefit — a reboot is
simpler and avoids poking the one area that can wedge the hardware.

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

The installer loads the `apple-ib-drv` kernel modules in USB **config 1** and lets the T1 render its
firmware function/control layouts — the bar draws itself, and touches come back as ordinary key
events (so brightness/volume OSD and hold-Fn→F-keys all work through the normal input stack). Config
1 also exposes the FaceTime webcam's UVC interfaces, which is why the camera keeps working.

## Want to design your own bar?

Custom pixels — your own buttons, colours, and app-aware behaviours drawn by the host instead of the
firmware — are a **separate, still-in-development project, `t1-touchbar-studio`.** It's a
fundamentally different approach (it takes the device's config-2 "DFR" display path) and is treated
as its own project. This repo stays lean: just the driver that makes the bar work. The studio will
be announced when it's ready.

## Trust & authorship

This is new code, and it asks for root to build a kernel module that can freeze your hardware — so
healthy skepticism is correct. A few things to make an informed decision:

- **Read before you run.** The installer only writes to `/etc/modprobe.d`, `/etc/udev/rules.d`,
  `/etc/modules-load.d`, and DKMS under `/usr/src` — no network beyond `apt`, no piping remote
  content to a shell. If you'd rather not pipe `curl` into `bash`, clone and read first
  (`git clone … && less install.sh && sudo ./install.sh`). The one-liner just fetches this same
  repo and runs the same script. `--dry-run` prints every action without doing it.
- **The commit trailers.** Commits are authored by **AJ-dev-i60** and co-authored by **Claude**
  (this project is built with Claude Code as a pair-programmer — that's what the `Claude` /
  `Co-Authored-By` trailers are). Not a sign of tampering.
- **Security policy / how to report:** [`SECURITY.md`](SECURITY.md).

## License

The installer, packaging, and docs are **MIT** (see [LICENSE](LICENSE)). The kernel driver in
[`apple-ib-drv/`](apple-ib-drv/) is **GPL-2.0** (its own `LICENSE`).

## Acknowledgements

This is a fork of [`t2linux/apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) (itself descended
from the roadrunner2 / `macbook12-spi-driver` lineage) — all the hard reverse-engineering and the
working kernel-6 driver are their work. What this fork adds on top is the port forward to **kernel 7**
(the HID/ACPI build-and-bind fixes) and the DMI-gated freeze-skip. Credit to everyone in that
lineage; without them there'd be nothing to port.
