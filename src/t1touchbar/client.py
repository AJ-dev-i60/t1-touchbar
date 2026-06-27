"""Python client for the t1touchbar socket daemon.

For tools that prefer talking to a running `t1touchbar serve` daemon rather than
owning the USB device themselves (e.g. so several tools can share the bar, or to
drive it from code that shouldn't run as root).

    from t1touchbar.client import Client
    c = Client()
    c.on_touch(lambda ev: print(ev))     # ev = {'x':.., 'y':.., 'state':..}
    print(c.info())                      # {'width':2170, 'height':60, ...}
    c.image("logo.png")                  # send a file / PIL image / raw RGB bytes
"""
import io
import json
import socket
import threading

from .server import (DEFAULT_SOCK, C_FRAME, C_IMG, C_CLEAR, C_INFO, C_PING,
                     S_TOUCH, S_INFO, S_PONG, send_msg, recv_msg)


class Client:
    def __init__(self, sock_path=DEFAULT_SOCK):
        self.conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.conn.connect(sock_path)
        self._touch_cb = None
        self._info = None
        self._info_evt = threading.Event()
        self._run = True
        threading.Thread(target=self._reader, daemon=True).start()

    # -- output ----------------------------------------------------------------
    def frame(self, rgb_bytes):
        """Send a raw upright width*height*3 RGB framebuffer."""
        send_msg(self.conn, C_FRAME, bytes(rgb_bytes))

    def image(self, img):
        """Send an image: a path, a PIL Image, or encoded image bytes."""
        if isinstance(img, str):
            with open(img, "rb") as f:
                data = f.read()
        elif hasattr(img, "save"):                 # PIL Image
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
        else:
            data = bytes(img)
        send_msg(self.conn, C_IMG, data)

    def clear(self):
        send_msg(self.conn, C_CLEAR)

    # -- input / info ----------------------------------------------------------
    def on_touch(self, callback):
        """Register a callback receiving dicts: {'x', 'y', 'state'}."""
        self._touch_cb = callback

    def info(self, timeout=2.0):
        self._info_evt.clear()
        send_msg(self.conn, C_INFO)
        self._info_evt.wait(timeout)
        return self._info

    def close(self):
        self._run = False
        try:
            self.conn.close()
        except Exception:
            pass

    # -- internals -------------------------------------------------------------
    def _reader(self):
        while self._run:
            try:
                msg = recv_msg(self.conn)
            except Exception:
                break
            if msg is None:
                break
            mtype, payload = msg
            if mtype == S_TOUCH and self._touch_cb:
                self._touch_cb(json.loads(payload))
            elif mtype == S_INFO:
                self._info = json.loads(payload)
                self._info_evt.set()
            elif mtype == S_PONG:
                pass
