"""The T1 (iBridge) FaceTime camera in config 2 — capture primitive + v4l2 bridge.

In its config-2 ("OS X") configuration the iBridge exposes the FaceTime HD camera
(IF1) *alongside* the DFR Touch Bar display (IF3), so the bar and the webcam can run
at the same time. Stock ``uvcvideo`` won't bind the config-2 camera because Apple
renumbered the UVC descriptor subtypes (19/20 instead of 6/7), but the payload is
ordinary **H.264** (1280x720 / 640x480). This module captures it in userspace.

Two layers:

* :class:`Camera` — thin capture primitive. Claims IF1, negotiates a stream, and
  yields the H.264 elementary stream (UVC payload headers stripped). The parallel of
  :class:`~t1touchbar.touch.TouchReader`, but for video input.
* :class:`LoopbackBridge` — batteries-included: pipes :class:`Camera` through
  ``ffmpeg`` onto a dedicated **v4l2loopback** node so any app (Howdy, Zoom, a
  browser) sees a normal ``/dev/video*`` camera.

Design guarantee: this never touches the system's real camera nodes or the default
camera. It creates its *own* loopback node, and when the bridge isn't running the
stock config-1 FaceTime camera behaves exactly as before. Composes with
:class:`~t1touchbar.device.Device`: in one process, open the ``Device`` first (it
performs the config switch) then a ``Camera(manage_config=False)``.
"""
import fcntl
import os
import struct
import subprocess
import time

VID, PID = 0x05AC, 0x8600
CONFIG_OSX = 2
# UVC class requests / selectors
_SET_CUR, _GET_CUR = 0x01, 0x81
_VS_PROBE, _VS_COMMIT = 0x0100, 0x0200
_RT_SET, _RT_GET = 0x21, 0xA1
# (bFormatIndex is always 1; frame index selects the resolution)
FRAME_INDEX = {"1280x720": 1, "640x480": 2}
DEFAULT_LABEL = "T1 iBridge Bridge"


def _find_syspath():
    base = "/sys/bus/usb/devices"
    for d in os.listdir(base):
        p = os.path.join(base, d)
        try:
            if (open(os.path.join(p, "idVendor")).read().strip() == "05ac" and
                    open(os.path.join(p, "idProduct")).read().strip() == "8600"):
                return p
        except OSError:
            continue
    return None


# -- capture primitive -----------------------------------------------------------
class Camera:
    """Capture the config-2 H.264 camera stream.

    ::

        with Camera(size="1280x720") as cam:
            for chunk in cam.stream():     # H.264 elementary stream bytes
                sink.write(chunk)

    `manage_config`/`manage_modules`: when True (standalone use) the camera unloads
    the apple kernel modules and switches the device to config 2 on open, and
    restores config 1 + modules on close. Set both False when a `Device` in the same
    process already owns the config-2 session.
    """

    def __init__(self, size="1280x720", manage_config=True, manage_modules=True):
        if size not in FRAME_INDEX:
            raise ValueError(f"size must be one of {list(FRAME_INDEX)}")
        self.size = size
        self.width, self.height = (int(x) for x in size.split("x"))
        self.manage_config = manage_config
        self.manage_modules = manage_modules
        self._dev = None
        self._usbutil = None
        self._ep = None
        self._ifnum = None
        self._syspath = None
        self._maxpayload = 92172
        self._stop = False

    def open(self):
        import usb.core
        import usb.util
        self._usbutil = usb.util

        self._syspath = _find_syspath()
        if not self._syspath:
            raise RuntimeError("iBridge 05ac:8600 not found on USB")
        if self.manage_modules and self.manage_config:
            os.system("rmmod apple_touchbar 2>/dev/null; rmmod apple_ibridge 2>/dev/null")
        if self.manage_config:
            self._set_config(CONFIG_OSX)
            time.sleep(1.0)

        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            raise RuntimeError("device not found after configuration switch")
        cfg = dev.get_active_configuration()
        if cfg.bConfigurationValue != CONFIG_OSX:
            raise RuntimeError("iBridge is not in config 2; open a Device first or "
                               "use manage_config=True")
        vs = next((i for i in cfg if i.bInterfaceClass == 14 and i.bInterfaceSubClass == 2),
                  None)
        if vs is None:
            raise RuntimeError("config 2 has no VideoStreaming interface")
        self._ifnum = vs.bInterfaceNumber
        self._ep = usb.util.find_descriptor(
            vs, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        for n in (0, self._ifnum):                 # VideoControl + VideoStreaming
            try:
                if dev.is_kernel_driver_active(n):
                    dev.detach_kernel_driver(n)
            except Exception:
                pass
        usb.util.claim_interface(dev, self._ifnum)
        self._dev = dev
        self._negotiate()
        return self

    def close(self):
        self._stop = True
        try:
            if self._dev is not None and self._ifnum is not None:
                self._usbutil.release_interface(self._dev, self._ifnum)
        except Exception:
            pass
        try:
            if self._dev is not None:
                self._usbutil.dispose_resources(self._dev)
        except Exception:
            pass
        if self.manage_config:
            try:
                self._set_config(1)
                time.sleep(0.8)
            except Exception:
                pass
            if self.manage_modules:
                os.system("modprobe apple_ibridge 2>/dev/null; "
                          "modprobe apple_touchbar 2>/dev/null")
        self._dev = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def stop(self):
        """Ask :meth:`stream` to finish after the current read."""
        self._stop = True

    def stream(self, read_timeout=2000):
        """Yield H.264 elementary-stream byte chunks (UVC payload headers stripped).

        Runs until :meth:`stop` is called or the device errors. Each yielded chunk
        is raw Annex-B H.264 ready to hand to a decoder.
        """
        import usb.core
        self._stop = False
        while not self._stop:
            try:
                p = self._dev.read(self._ep.bEndpointAddress,
                                   self._maxpayload + 4096, timeout=read_timeout)
            except usb.core.USBError:
                continue
            if len(p) < 2:
                continue
            hlen = p[0]
            if hlen < 2 or hlen > 12:    # sane UVC payload header lengths
                continue
            data = bytes(p[hlen:])
            if data:
                yield data

    # -- internals -------------------------------------------------------------
    def _set_config(self, value):
        with open(os.path.join(self._syspath, "bConfigurationValue"), "w") as f:
            f.write(str(value))

    def _probe_struct(self, frame_idx, interval=333333):
        b = bytearray(48)               # UVC 1.5 probe/commit control block
        struct.pack_into("<H", b, 0, 0x0001)    # bmHint: dwFrameInterval fixed
        b[2], b[3] = 1, frame_idx                # bFormatIndex, bFrameIndex
        struct.pack_into("<I", b, 4, interval)   # dwFrameInterval
        return bytes(b)

    def _negotiate(self):
        idx = FRAME_INDEX[self.size]
        self._dev.ctrl_transfer(_RT_SET, _SET_CUR, _VS_PROBE, self._ifnum,
                                self._probe_struct(idx))
        neg = bytes(self._dev.ctrl_transfer(_RT_GET, _GET_CUR, _VS_PROBE,
                                            self._ifnum, 48))
        self._maxpayload = struct.unpack_from("<I", neg, 22)[0] or self._maxpayload
        self._dev.ctrl_transfer(_RT_SET, _SET_CUR, _VS_COMMIT, self._ifnum, neg)


# -- v4l2loopback node management ------------------------------------------------
_CTL = "/dev/v4l2loopback"
# struct v4l2_loopback_config (v4l2loopback 0.15): s32 output_nr; s32 unused;
#   char card_label[32]; u32 min_w,max_w,min_h,max_h; s32 max_buffers,max_openers,
#   debug, announce_all_caps.  announce_all_caps == !exclusive_caps; we want
#   exclusive caps (=> 0) so capture apps (OpenCV/Howdy, Chrome) treat the node as a
#   pure capture device — otherwise they get a "select() timeout".
_CFG_FMT = "ii32sIIIIiiii"
_MAGIC = ord("~")              # V4L2LOOPBACK_CTL_IOCTLMAGIC


def _iow(nr, size):            # _IOW(magic, nr, size), Linux asm-generic encoding
    return (1 << 30) | (size << 16) | (_MAGIC << 8) | nr


_CTL_ADD = _iow(1, struct.calcsize(_CFG_FMT))
_CTL_REMOVE = _iow(2, 4)


def find_loopback_by_label(label=DEFAULT_LABEL):
    """Return the ``/dev/videoN`` path of a v4l2loopback node with this card name,
    or None. Lets callers find *our* node without depending on a fixed number."""
    base = "/sys/devices/virtual/video4linux"
    if not os.path.isdir(base):
        return None
    for d in sorted(os.listdir(base)):
        try:
            name = open(os.path.join(base, d, "name")).read().strip()
        except OSError:
            continue
        if name == label and d.startswith("video"):
            return "/dev/" + d
    return None


def ensure_loopback(label=DEFAULT_LABEL):
    """Return a dedicated loopback ``/dev/videoN``, creating one if needed.

    Uses the v4l2loopback control device with ``output_nr=-1`` (auto-assign) so it
    never collides with an existing node (e.g. another app's virtual camera). Needs
    the ``v4l2loopback`` module loaded and root.
    """
    existing = find_loopback_by_label(label)
    if existing:
        return existing
    if not os.path.exists(_CTL):
        raise RuntimeError("v4l2loopback control device missing; is the module "
                           "loaded? (modprobe v4l2loopback)")
    cfg = struct.pack(_CFG_FMT, -1, 0, label.encode()[:31],
                      2, 1920, 2, 1080, 4, 10, 0, 0)   # last 0 = exclusive caps
    fd = os.open(_CTL, os.O_RDWR)
    try:
        nr = fcntl.ioctl(fd, _CTL_ADD, bytearray(cfg))
    finally:
        os.close(fd)
    # settle so the /dev node + sysfs name appear
    for _ in range(50):
        path = find_loopback_by_label(label) or f"/dev/video{nr}"
        if os.path.exists(path):
            return path
        time.sleep(0.05)
    return f"/dev/video{nr}"


def remove_loopback(path):
    """Remove a loopback node previously created with :func:`ensure_loopback`."""
    try:
        nr = int(os.path.basename(path).replace("video", ""))
    except ValueError:
        return
    if not os.path.exists(_CTL):
        return
    fd = os.open(_CTL, os.O_RDWR)
    try:
        fcntl.ioctl(fd, _CTL_REMOVE, nr)
    except OSError:
        pass
    finally:
        os.close(fd)


# -- batteries-included bridge ---------------------------------------------------
class LoopbackBridge:
    """Pump :class:`Camera` H.264 through ffmpeg onto a v4l2loopback node.

    ::

        bridge = LoopbackBridge(size="1280x720")
        path = bridge.start()          # e.g. "/dev/video3" — point apps here
        ...                            # streams in a background thread
        bridge.stop()

    `device`: target loopback path; if None, a dedicated node is created/reused.
    `manage_config`/`manage_modules` are forwarded to :class:`Camera`.
    """

    def __init__(self, device=None, size="1280x720", label=DEFAULT_LABEL,
                 manage_config=True, manage_modules=True, fps=30):
        self.device = device
        self.size = size
        self.label = label
        self.fps = fps
        self.manage_config = manage_config
        self.manage_modules = manage_modules
        self._cam = None
        self._ff = None
        self._thread = None
        self._created_node = None

    def start(self):
        import threading
        if self.device is None:
            self.device = ensure_loopback(self.label)
            self._created_node = self.device
        self._cam = Camera(size=self.size, manage_config=self.manage_config,
                           manage_modules=self.manage_modules).open()
        self._ff = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-fflags", "nobuffer", "-flags", "low_delay",
             "-f", "h264", "-framerate", str(self.fps), "-i", "pipe:0",
             "-vf", "format=yuyv422", "-f", "v4l2", self.device],
            stdin=subprocess.PIPE)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        return self.device

    def _pump(self):
        try:
            for chunk in self._cam.stream():
                try:
                    self._ff.stdin.write(chunk)
                except (BrokenPipeError, ValueError):
                    break
        finally:
            try:
                self._ff.stdin.close()
            except Exception:
                pass

    def stop(self, remove_node=False):
        if self._cam:
            self._cam.stop()
        if self._thread:
            self._thread.join(timeout=3)
        if self._ff:
            try:
                self._ff.terminate()
                self._ff.wait(timeout=3)
            except Exception:
                pass
        if self._cam:
            self._cam.close()
        if remove_node and self._created_node:
            remove_loopback(self._created_node)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


# -- CLI -------------------------------------------------------------------------
def main(argv=None):
    """``t1touchbar-camera`` — bridge the config-2 camera to a v4l2loopback node."""
    import argparse
    import signal

    ap = argparse.ArgumentParser(
        prog="t1touchbar-camera",
        description="Expose the T1 config-2 FaceTime camera as a v4l2loopback "
                    "device so it can run alongside the custom Touch Bar.")
    ap.add_argument("--device", help="target loopback /dev/videoN (default: "
                                     "create/reuse a dedicated node)")
    ap.add_argument("--size", default="1280x720", choices=list(FRAME_INDEX))
    ap.add_argument("--label", default=DEFAULT_LABEL)
    ap.add_argument("--keep-config", action="store_true",
                    help="don't restore config 1 on exit (when a Device/strip also "
                         "holds config 2)")
    ap.add_argument("--remove-node", action="store_true",
                    help="delete the created loopback node on exit")
    ap.add_argument("--print-device", action="store_true",
                    help="print the loopback path on a line prefixed 'DEVICE='")
    args = ap.parse_args(argv)

    if os.geteuid() != 0:
        ap.error("must run as root (USB + v4l2loopback control)")

    bridge = LoopbackBridge(device=args.device, size=args.size, label=args.label,
                            manage_config=not args.keep_config,
                            manage_modules=not args.keep_config)
    path = bridge.start()
    if args.print_device:
        print(f"DEVICE={path}", flush=True)
    print(f"[camera] streaming {args.size} -> {path}  (Ctrl-C to stop)", flush=True)

    stop = {"v": False}
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stop.update(v=True))
    try:
        while not stop["v"]:
            time.sleep(0.2)
            if bridge._ff and bridge._ff.poll() is not None:
                print("[camera] ffmpeg exited", flush=True)
                break
    finally:
        bridge.stop(remove_node=args.remove_node)
        print("[camera] stopped"
              + ("" if args.keep_config else "; config 1 restored (Touch Bar blank "
                 "until reboot)"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
