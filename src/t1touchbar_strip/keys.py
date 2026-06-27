"""Watch the physical Fn key so the strip can switch to F-keys while it is held.

Apple's Fn key emits `KEY_FN` (down/hold/up) on the "Apple SPI Keyboard" evdev
device. We read it passively (no grab) so normal keyboard behaviour is untouched.
"""
import threading


class FnWatcher:
    """Call `on_change(pressed: bool)` whenever the physical Fn key goes down/up."""

    def __init__(self, on_change, device_name="Apple SPI Keyboard"):
        self.on_change = on_change
        self.device_name = device_name
        self._dev = None
        self._run = False
        self._thread = None

    def start(self):
        import evdev
        self._dev = next(
            (evdev.InputDevice(p) for p in evdev.list_devices()
             if self.device_name in (evdev.InputDevice(p).name or "")), None)
        if self._dev is None:
            print(f"[strip] Fn watcher: {self.device_name!r} not found "
                  "(physical Fn -> F-keys disabled)", flush=True)
            return False
        self._run = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._run = False

    def _loop(self):
        import select
        from evdev import ecodes as E
        fd = self._dev.fd
        while self._run:
            r, _, _ = select.select([fd], [], [], 0.3)
            if not r:
                continue
            try:
                events = list(self._dev.read())
            except Exception:
                continue
            for e in events:
                if e.type == E.EV_KEY and e.code == E.KEY_FN:
                    if e.value == 1:
                        self.on_change(True)
                    elif e.value == 0:
                        self.on_change(False)
