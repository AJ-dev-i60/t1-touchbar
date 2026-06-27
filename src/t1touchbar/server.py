"""Unix-socket daemon: owns the Device + TouchReader and exposes them over a
simple length-prefixed binary protocol, so a tool in any language can drive the
Touch Bar and receive touch events. See docs/PROTOCOL.md.

Wire framing (both directions): 4-byte big-endian length, 1-byte type, payload.
  client -> server:  FRAME(1)=raw WxHx3 RGB | IMG(2)=PNG/JPG bytes | CLEAR(3)
                     INFO(4) | PING(5)
  server -> client:  TOUCH(0x81)=json{x,y,state} | INFO(0x82)=json | PONG(0x83)
"""
import io
import json
import os
import socket
import struct
import threading

from .device import Device
from .touch import TouchReader

DEFAULT_SOCK = "/tmp/t1touchbar.sock"

C_FRAME, C_IMG, C_CLEAR, C_INFO, C_PING = 1, 2, 3, 4, 5
S_TOUCH, S_INFO, S_PONG = 0x81, 0x82, 0x83


def send_msg(conn, mtype, payload=b""):
    conn.sendall(struct.pack(">IB", len(payload), mtype) + payload)


def _recv_n(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def recv_msg(conn):
    hdr = _recv_n(conn, 5)
    if not hdr:
        return None
    length, mtype = struct.unpack(">IB", hdr)
    payload = _recv_n(conn, length) if length else b""
    if payload is None:
        return None
    return mtype, payload


class Server:
    """Run with `Server().serve()` (blocks) or via `t1touchbar serve`."""

    def __init__(self, sock_path=DEFAULT_SOCK, grab_touch=True):
        self.sock_path = sock_path
        self.grab_touch = grab_touch
        self.device = None
        self.touch = None
        self._clients = []
        self._clients_lock = threading.Lock()
        self._dev_lock = threading.Lock()

    def serve(self):
        self.device = Device().open()
        self._info = self.device.info()
        self.touch = TouchReader(self._info["width"], self._info["height"],
                                 grab=self.grab_touch)
        try:
            self.touch.start(self._on_touch)
        except Exception as e:
            print(f"[t1touchbar] touch input unavailable: {e}", flush=True)

        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.sock_path)
        os.chmod(self.sock_path, 0o666)
        srv.listen(8)
        print(f"[t1touchbar] ready: {self._info['width']}x{self._info['height']} "
              f"on {self.sock_path}", flush=True)
        try:
            while True:
                conn, _ = srv.accept()
                threading.Thread(target=self._client, args=(conn,), daemon=True).start()
        finally:
            self.shutdown()

    def shutdown(self):
        if self.touch:
            self.touch.stop()
        if self.device:
            self.device.close()
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

    # -- internals -------------------------------------------------------------
    def _on_touch(self, ev):
        payload = json.dumps({"x": ev.x, "y": ev.y, "state": ev.state}).encode()
        with self._clients_lock:
            for c in list(self._clients):
                try:
                    send_msg(c, S_TOUCH, payload)
                except Exception:
                    self._clients.remove(c)

    def _client(self, conn):
        with self._clients_lock:
            self._clients.append(conn)
        try:
            while True:
                msg = recv_msg(conn)
                if msg is None:
                    break
                mtype, payload = msg
                if mtype == C_FRAME:
                    with self._dev_lock:
                        self.device.blit(payload)
                elif mtype == C_IMG:
                    from PIL import Image
                    img = Image.open(io.BytesIO(payload))
                    with self._dev_lock:
                        self.device.blit(img)
                elif mtype == C_CLEAR:
                    with self._dev_lock:
                        self.device.clear()
                elif mtype == C_INFO:
                    send_msg(conn, S_INFO, json.dumps(self._info).encode())
                elif mtype == C_PING:
                    send_msg(conn, S_PONG)
        except Exception:
            pass
        finally:
            with self._clients_lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            conn.close()
