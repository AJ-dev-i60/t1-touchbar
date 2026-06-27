"""The T1 Touch Bar as an input device: the digitizer -> mapped touch events.

In config 2 the kernel exposes the digitizer as an evdev device ("Apple Inc.
iBridge Touchpad"). This reads it on a background thread and reports touch events
with coordinates already mapped to panel pixels.
"""
import threading
import time


class TouchEvent:
    """A single touch sample. `state` is 'down', 'move', or 'up'.

    `x` is 0..width (left->right), `y` is 0..height (top->bottom).
    """
    __slots__ = ("x", "y", "state", "t")

    def __init__(self, x, y, state, t):
        self.x, self.y, self.state, self.t = x, y, state, t

    def __repr__(self):
        return f"TouchEvent(state={self.state!r}, x={self.x}, y={self.y})"


class TouchReader:
    """Read the Touch Bar digitizer and deliver mapped TouchEvents to a callback.

        def on_touch(ev):
            print(ev.state, ev.x, ev.y)

        tr = TouchReader(width=2170, height=60)
        tr.start(on_touch)
        ...
        tr.stop()

    `grab=True` takes exclusive access (EVIOCGRAB) so touches don't reach the
    desktop (no cursor movement / media keys). Requires root. The callback runs on
    the reader thread; keep it quick.
    """

    def __init__(self, width, height, grab=True, device_name="iBridge Touchpad"):
        self.width = width
        self.height = height
        self.grab = grab
        self.device_name = device_name
        self._dev = None
        self._thread = None
        self._run = False
        self._xmax = 32767
        self._ymax = 127

    def start(self, callback):
        import evdev
        self._dev = self._find()
        if self._dev is None:
            raise RuntimeError(f"no input device matching {self.device_name!r}")
        try:
            self._xmax = self._dev.absinfo(evdev.ecodes.ABS_X).max or self._xmax
            self._ymax = self._dev.absinfo(evdev.ecodes.ABS_Y).max or self._ymax
        except Exception:
            pass
        if self.grab:
            try:
                self._dev.grab()
            except Exception:
                pass
        self._run = True
        self._thread = threading.Thread(target=self._loop, args=(callback,), daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        if self._dev is not None and self.grab:
            try:
                self._dev.ungrab()
            except Exception:
                pass

    # -- internals -------------------------------------------------------------
    def _find(self):
        import evdev
        for path in evdev.list_devices():
            d = evdev.InputDevice(path)
            if self.device_name in (d.name or ""):
                return d
        return None

    def _mx(self, ax):
        return max(0, min(self.width, int(ax / self._xmax * self.width)))

    def _my(self, ay):
        return max(0, min(self.height, int(ay / self._ymax * self.height)))

    def _loop(self, callback):
        import select
        from evdev import ecodes as E
        ax, ay, down, pending = 0, self._ymax // 2, False, False
        fd = self._dev.fd
        while self._run:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            try:
                events = list(self._dev.read())
            except Exception:
                continue
            for e in events:
                if e.type == E.EV_ABS:
                    if e.code == E.ABS_X:
                        ax = e.value
                    elif e.code == E.ABS_Y:
                        ay = e.value
                elif e.type == E.EV_KEY and e.code == E.BTN_TOUCH:
                    if e.value == 1:
                        down = True
                        pending = True   # emit 'down' on next SYN, when coords are fresh
                    else:
                        down = False
                        callback(TouchEvent(self._mx(ax), self._my(ay), "up", time.time()))
                elif e.type == E.EV_SYN:
                    x, y = self._mx(ax), self._my(ay)
                    if pending:
                        pending = False
                        callback(TouchEvent(x, y, "down", time.time()))
                    elif down:
                        callback(TouchEvent(x, y, "move", time.time()))
