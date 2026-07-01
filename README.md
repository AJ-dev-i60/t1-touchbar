# t1-touchbar

**Make your 2016–2017 Intel MacBook Pro (T1) Touch Bar work on Linux.**

On the 2016–2017 MacBook Pros (MacBookPro13,x / 14,x) the Touch Bar is a **T1** ("iBridge") device.
Mainline Linux only ever supported the **T2** models, so on these machines the bar was just a black
strip. This is a small DKMS kernel driver that lets the T1's **own firmware** draw the normal control
strip — Esc, brightness, keyboard backlight, media, volume, and hold-**Fn** for **F1–F12**, exactly
like macOS. Set-and-forget; your webcam keeps working too.

The T1 bar has worked on Linux for years via the
[`apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) / roadrunner2 community — but only up to
**kernel 6.x**. A 2023 HID change broke it on newer kernels, and Linux **7.0** only released in
**April 2026**, so the bar went dark on current systems. This is that driver ported forward to build
and bind on **kernel 7**, made freeze-safe by default. It stands entirely on the shoulders of the
kernel-6 work.

> ⚠️ **Freeze safety.** On these models an ACPI power-on call (`ASOC.SOCW(1)`) **hard-freezes the
> machine** (power-button recovery). The driver skips it by default on T1 hardware and the installer
> pins `skip_acpi_power=1`, so the supported path is safe — the *only* way to hit the freeze is to
> force it back on with `skip_acpi_power=0`. Don't. See [Troubleshooting](#troubleshooting).

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/AJ-dev-i60/t1-touchbar/main/install.sh | bash
```

…or clone it first:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar && cd t1-touchbar && sudo ./install.sh
```

No `git`? The `curl` line fetches the repo itself. Flags: `--yes` (non-interactive), `--dry-run`
(preview every action), `--no-service` (don't load it now). Needs **root** and an apt-based distro
(Ubuntu/Debian); it pulls `build-essential`, `dkms`, and `linux-headers`.

The installer DKMS-builds the driver, sets `skip_acpi_power=1`, and installs the udev rule that puts
the iBridge into USB config 1 — which exposes both the Touch Bar HID *and* the webcam. **Then reboot
to finish:** on a running system the generic HID drivers have already claimed the device, so the live
load may bind nothing; after one reboot the driver wins the race and the strip comes up on every boot.

To remove it: `sudo ./uninstall.sh` (then reboot).

## Tested on

| Model | Kernel | Distro | Result |
|---|---|---|---|
| MacBookPro14,3 | 7.0.0-27-generic | Ubuntu 26.04 | ✅ builds, binds after reboot, keys + OSD work, webcam intact |

Other 13,x/14,x models and kernels should work but are unverified. DKMS rebuilds the module on kernel
upgrades — but a broken rebuild fails **silently**, so after an upgrade check the bar still lights and
that `dkms status` shows `apple-ib-drv/0.1, <new-kernel>: installed`.

## Troubleshooting

**Healthy signature** (after a good boot):

```bash
lsmod | grep apple_touchbar                # loaded
dmesg | grep -i skip_acpi_power            # "skip_acpi_power: NOT running ASOC.SOCW(1)…"
dmesg | grep -iE 'apple-touchbar.*input:'  # Touch Bar HID created
# and the iBridge's bConfigurationValue reads 1
```

The installer prints this self-check for you.

**Bar dark right after install?** Expected — **reboot once.** The live `modprobe` can't claim
interfaces the generic HID drivers already hold, and the installer deliberately doesn't force a live
unbind/rebind (that would poke the same bind/power paths that can wedge the T1 — a reboot is safer).

**Still dark after a reboot?** Most likely `usbmuxd` (iOS tethering) grabbed the iBridge first — its
udev rule also matches `05ac:8600`. Drop the matches and reboot:

```bash
sudo sed -i '/05ac.*8600/d' /lib/udev/rules.d/39-usbmuxd.rules   # or: sudo systemctl mask usbmuxd
sudo udevadm control --reload && sudo reboot
```

**"tainting kernel / signature missing"?** Harmless with Secure Boot off. With Secure Boot **on**,
enrol the DKMS key once: `sudo mokutil --import /var/lib/dkms/mok.pub` (set a password, reboot,
confirm at the MOK screen), or the module won't load.

**Recovery.** If a boot ever hangs, at GRUB press `e` and add
`modprobe.blacklist=apple_ibridge,apple_touchbar` to the kernel line.

## Want to design your own bar?

Custom pixels — your own buttons, colours, and app-aware behaviours drawn by the host — are a
separate, still-in-development project (`t1-touchbar-studio`) that takes a fundamentally different
approach (the device's config-2 "DFR" display path). This repo stays lean: just the driver that
makes the bar work.

## Details, trust & license

- **The driver** is a fork of [`t2linux/apple-ib-drv`](https://github.com/t2linux/apple-ib-drv)
  (roadrunner2 lineage) with the kernel-7 build fixes and the DMI-gated freeze-skip on top — full fix
  list in [`apple-ib-drv/README.md`](apple-ib-drv/README.md). It's **GPL-2.0**; the installer and docs
  are **MIT** ([LICENSE](LICENSE)).
- **Trust.** It's root plus a kernel module that can freeze hardware, so skepticism is fair. The
  installer only writes to `/etc/modprobe.d`, `/etc/udev/rules.d`, `/etc/modules-load.d`, and DKMS
  under `/usr/src`, with no network beyond `apt`. Read it first if you like — `--dry-run` previews
  every action; see [`SECURITY.md`](SECURITY.md).
- **Authorship.** Built with Claude Code as a pair-programmer — that's what the `Claude` /
  `Co-Authored-By` trailers in the history are, not tampering.

## Acknowledgements

All the hard reverse-engineering and the working kernel-6 driver are the
[`t2linux/apple-ib-drv`](https://github.com/t2linux/apple-ib-drv) / roadrunner2 community's work; this
fork just ports it forward to kernel 7. Without them there'd be nothing to port.
