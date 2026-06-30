# apple-ib-drv — the firmware-path T1 Touch Bar kernel driver (Option 1's engine)

This is the **kernel driver** that makes the T1's *own firmware* draw the Touch Bar — the
familiar Esc / brightness / keyboard-backlight / media / volume strip, with **hold-Fn → F1–F12**,
exactly like macOS. It's what the installer's **Basic ("just make it work")** path sets up.

It is a different thing from the userspace driver at the repo root:

| | engine | how the bar is drawn | USB config |
|---|---|---|---|
| **Basic** (this dir) | `apple-ib-drv` kernel modules | the **T1 firmware** draws it | config 1 |
| **Full** (repo root + `studio/`) | userspace libusb + Scenes | the **host** draws custom pixels | config 2 |

Because Basic uses the firmware, it's *set-and-forget*: no daemon holding the device, no
"blank-until-reboot", and the **FaceTime webcam keeps working normally** (the udev rule that
forces config 1 exposes both the Touch Bar HID and the camera's UVC interfaces).

## License & provenance

**GPL-2.0** (see `LICENSE`) — *not* MIT like the rest of this repo. It is a fork of
[**t2linux/apple-ib-drv**](https://github.com/t2linux/apple-ib-drv) (upstream `~4afd309`), which is
GPL, with **five fixes** to make it build and bind on **Linux 7.x** for the **T1** (`05ac:8600`,
MacBookPro13,x/14,x). The exact delta vs upstream is recorded in `t1-kernel7-fixes.applied.patch`
— a **reference diff, already baked into the `.c` sources here** (so the DKMS build needs no
patching; don't re-apply it — a `patch --dry-run` will correctly report "previously applied").

The five fixes (full write-up in the project's kernel-7 guide):
1. **`skip_acpi_power` — safe-by-default freeze guard ⭐** — the `ASOC.SOCW(1)` ACPI power-on
   **hard-freezes** the T1 (confirmed on MacBookPro14,3) at module load *and on resume*. *This is
   the key finding.* The param is tri-state and **defaults to skipping on the T1 family
   (MacBookPro13,x/14,x), detected by DMI** (`-1` = auto; unreadable DMI also skips, fail-safe) — so
   even a bare `insmod` can't freeze the machine. `1` forces skip (the installer pins this in
   modprobe.d, belt-and-suspenders); `0` forces the upstream power-on (**can freeze — opt-in only**).
   All three SOCW call sites — probe, suspend, resume — honour it (upstream left suspend/resume
   unguarded).
2. UBSAN out-of-bounds in `appleib_add_device` (index by slot, not collection idx).
3. `appleib_ll_parse` was a no-op → restored `hid_parse_report` (fixes `-ENODEV` on the sub-device).
4. T1 activation with the mode interface alone (T1 has no separate display iface) → the firmware
   renders the row itself.
5. NULL-guard the sparse `sub_hdevs[]` (crash on USB autosuspend).

## How it's installed

The repo-root **`install.sh` (Basic)** does it for you, via **DKMS** so it auto-rebuilds on kernel
upgrades:

```
dkms add/build/install (this source as apple-ib-drv/0.1)
/etc/modprobe.d/apple-touchbar.conf      -> options apple_ibridge skip_acpi_power=1   ⭐ required
/etc/modules-load.d/apple-touchbar.conf  -> apple-ibridge (auto-load at boot)
/etc/udev/rules.d/99-ibridge.rules       -> force USB config 1 + disable autosuspend
```

`packaging/` holds those three files. The driver defaults to skipping the freeze on T1 hardware, so
the modprobe.conf `skip_acpi_power=1` is belt-and-suspenders; **never pass `skip_acpi_power=0`** —
that forces `SOCW(1)` and freezes the machine.

## Recovery

If a boot ever misbehaves, add to the kernel cmdline (GRUB → `e`):
`modprobe.blacklist=apple_ibridge,apple_touchbar`, boot, and investigate.
