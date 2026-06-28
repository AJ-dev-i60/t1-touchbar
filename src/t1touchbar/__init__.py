"""t1touchbar — a display + input driver for the Apple T1 (iBridge) MacBook Pro
Touch Bar on Linux.

The driver is intentionally thin: it does **display output**, **touch input**,
**camera capture**, and **device lifecycle**, and nothing else — graphics,
animation, layouts, and action-mapping belong to tools built on top of it.

In the iBridge's config-2 session the FaceTime camera and the Touch Bar display
coexist; :class:`Camera` / :class:`LoopbackBridge` expose the camera as a normal
v4l2 device so the bar and webcam run together (``sudo t1touchbar-camera``).

Quick start (Python)::

    from t1touchbar import Device, TouchReader
    from PIL import Image
    with Device() as bar:
        bar.blit(Image.new("RGB", (bar.width, bar.height), (0, 200, 0)))
        tr = TouchReader(bar.width, bar.height)
        tr.start(lambda ev: print(ev))
        input("press enter to quit")

Or run the socket daemon and drive it from any language::

    sudo t1touchbar serve
"""
from .device import Device
from .touch import TouchReader, TouchEvent
from .geometry import to_device_bytes
from . import protocol

__all__ = ["Device", "TouchReader", "TouchEvent", "to_device_bytes", "protocol",
           "Camera", "LoopbackBridge"]
__version__ = "0.1.0"


def __getattr__(name):
    # Lazy: importing camera pulls in subprocess/fcntl only when actually used.
    if name in ("Camera", "LoopbackBridge"):
        from . import camera
        return getattr(camera, name)
    raise AttributeError(name)
