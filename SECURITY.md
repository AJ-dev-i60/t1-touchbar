# Security & trust

This project builds and loads a **kernel module** as **root**, and that module can **hard-freeze**
a 2016/2017 MacBook Pro if loaded incorrectly (see below). Treat it with the same care as any
out-of-tree driver. This page explains what it does, how it's authored, and how to report a problem.

## What the installer touches

The **Basic** path (the firmware Touch Bar driver) only:

- writes `/etc/modprobe.d/apple-touchbar.conf`, `/etc/modules-load.d/apple-touchbar.conf`,
  `/etc/udev/rules.d/99-ibridge.rules`,
- installs DKMS sources under `/usr/src/apple-ib-drv-0.1/` and builds the module,
- reaches the network **only** via `apt` (to pull `build-essential`, `dkms`, `linux-headers`).

No data leaves the machine, nothing is piped from the network into a shell, and nothing is written
outside `/etc`, `/usr/src`, and DKMS. You can verify all of this by reading
[`install.sh`](install.sh) — it supports `--dry-run` to print every action without doing it.

The **Full** path additionally installs a Python venv, GTK, `ffmpeg`/`v4l2loopback`, and systemd
services for the studio + webcam bridge. Read [`install.sh`](install.sh)'s Full block if that
matters to you.

## The freeze hazard (read this)

On the T1 (MacBookPro13,x/14,x), the ACPI method `ASOC.SOCW(1)` **hard-freezes the machine** — only
a forced power-off recovers, with a small risk of filesystem damage. The driver **skips this call by
default on T1 hardware** (DMI-gated), the installer also pins `skip_acpi_power=1` in modprobe.d, and
all three call sites (probe, suspend, resume) honour the skip — so the supported path is safe. The
only way to trigger the freeze is to **force the power-on with `skip_acpi_power=0`**; don't.

## Authorship

Commits are authored by **AJ-dev-i60** and co-authored by **Claude** — this project is developed
with Claude Code as an AI pair-programmer, which is the source of the `Claude` / `Co-Authored-By`
trailers in the git history. They are not a sign of compromised or misattributed commits.

## Reporting a vulnerability

Open a GitHub issue at <https://github.com/AJ-dev-i60/t1-touchbar/issues>. For anything you'd
rather not disclose publicly, say so in a minimal issue ("found a security problem, please provide a
private contact") and a maintainer will follow up. There is no formal SLA — this is a small,
community project — but security reports are triaged first.

## Don't trust blindly

If piping `curl … | bash` as root is not for you, **clone and read first**:

```bash
git clone https://github.com/AJ-dev-i60/t1-touchbar && cd t1-touchbar
less install.sh          # read it
sudo ./install.sh --basic --dry-run   # preview every action
sudo ./install.sh --basic             # then, if you're satisfied
```
