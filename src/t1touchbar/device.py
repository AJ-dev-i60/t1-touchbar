"""The T1 Touch Bar as a display device: lifecycle + framebuffer output.

Owns the USB side: switches the iBridge to its config-2 ("OS X") configuration,
claims the Audio/Video interface, performs the GINF/REDY handshake, and pushes
frames with synchronous (UDCL-acked) pacing. Only one process at a time may own it.
"""
import os
import time

from . import protocol
from .geometry import to_device_bytes

VID, PID = 0x05AC, 0x8600
CONFIG_OSX = 2
AV_INTERFACE_CLASS = 0x10  # Audio/Video


class Device:
    """Open the Touch Bar, blit images to it, and restore it on close.

    Typical use::

        from t1touchbar import Device
        with Device() as bar:
            print(bar.info())          # {'width': 2170, 'height': 60, ...}
            bar.blit(pil_image)        # upright image; transform handled for you

    `manage_modules=True` unloads the kernel `apple_touchbar`/`apple_ibridge`
    modules on open and reloads them on close. Requires root.

    NOTE: exiting hands display control back; on T1 the firmware does not reclaim
    the panel, so the bar stays blank until a reboot. Keep the device open while
    you want the bar lit.
    """

    def __init__(self, manage_modules=True):
        self.manage_modules = manage_modules
        self.width = None
        self.height = None
        self._info = {}
        self._dev = None
        self._usbutil = None
        self._syspath = None
        self._ep_out = None
        self._ep_in = None
        self._intf = None
        self._ts = 0x1000

    # -- lifecycle -------------------------------------------------------------
    def open(self):
        import usb.core
        import usb.util
        self._usbutil = usb.util

        self._syspath = self._find_syspath()
        if not self._syspath:
            raise RuntimeError("iBridge 05ac:8600 not found on USB")
        if self.manage_modules:
            os.system("rmmod apple_touchbar 2>/dev/null; rmmod apple_ibridge 2>/dev/null")

        self._set_config(CONFIG_OSX)
        time.sleep(0.8)

        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            raise RuntimeError("device disappeared after configuration switch")
        cfg = dev.get_active_configuration()
        intf = next((i for i in cfg if i.bInterfaceClass == AV_INTERFACE_CLASS), None)
        if intf is None:
            raise RuntimeError("config 2 has no Audio/Video (class 16) interface")
        self._ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self._ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        try:
            dev.detach_kernel_driver(intf.bInterfaceNumber)
        except Exception:
            pass
        usb.util.claim_interface(dev, intf.bInterfaceNumber)
        self._dev = dev
        self._intf = intf.bInterfaceNumber
        self._handshake()
        return self

    def close(self):
        try:
            if self._dev is not None:
                self._usbutil.dispose_resources(self._dev)
        except Exception:
            pass
        try:
            self._set_config(1)
        except Exception:
            pass
        if self.manage_modules:
            os.system("modprobe apple_ibridge 2>/dev/null; modprobe apple_touchbar 2>/dev/null")
        self._dev = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # -- output ----------------------------------------------------------------
    def info(self) -> dict:
        """Panel geometry/format: {'width', 'height', 'bpp', 'pixel_format'}."""
        return dict(width=self.width, height=self.height,
                    bpp=self._info.get("bpp"),
                    pixel_format=self._info.get("pixel_format"))

    def blit(self, image):
        """Display an upright image: a PIL Image, or raw width*height*3 RGB bytes."""
        buf = to_device_bytes(image, self.width, self.height)
        self._ts += 1
        self._ep_out.write(
            protocol.fb_request(self.width, self.height, buf, self._ts), timeout=4000)
        self._wait_udcl()

    def clear(self):
        """Blank the panel (CLEAR_DISPLAY)."""
        self._ep_out.write(protocol.simple_request(protocol.CLRD), timeout=1000)

    # -- internals -------------------------------------------------------------
    @staticmethod
    def _find_syspath():
        base = "/sys/bus/usb/devices"
        for d in os.listdir(base):
            p = os.path.join(base, d)
            try:
                vid = open(os.path.join(p, "idVendor")).read().strip()
                pid = open(os.path.join(p, "idProduct")).read().strip()
            except OSError:
                continue
            if vid == "05ac" and pid == "8600":
                return p
        return None

    def _set_config(self, value):
        with open(os.path.join(self._syspath, "bConfigurationValue"), "w") as f:
            f.write(str(value))

    def _handshake(self):
        # Probe order matters: GET_INFORMATION first (skip a stray startup REDY),
        # then SIGNAL_READINESS.
        self._ep_out.write(protocol.simple_request(protocol.GINF), timeout=1000)
        info = None
        for _ in range(5):
            try:
                r = bytes(self._ep_in.read(512, timeout=1000))
            except Exception:
                break
            if protocol.tag(r) == "GINF" and len(r) >= 60:
                info = protocol.parse_information(r)
                break
        self._ep_out.write(protocol.simple_request(protocol.REDY), timeout=1000)
        if not info:
            raise RuntimeError("no GINF response; device did not report geometry")
        self.width = info["width"]
        self.height = info["height"]
        self._info = info

    def _wait_udcl(self, timeout=1000):
        # DFR is synchronous: wait for the device's UDCL ack before the next frame
        # (skipping any stray REDY/STAT/short acks). Ignoring this drops frames AND
        # stalls the device.
        for _ in range(8):
            try:
                r = bytes(self._ep_in.read(512, timeout=timeout))
            except Exception:
                return False
            if protocol.tag(r) == "UDCL":
                return True
        return False
