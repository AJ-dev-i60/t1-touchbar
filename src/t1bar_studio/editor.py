"""`t1bar edit` — a local web editor for the config.

It edits the config *file*; a running `t1bar run` hot-reloads that file, so changes
made in the browser appear on the physical bar live. The same `render.py` produces
the in-browser preview, so what you see in the editor matches the bar exactly.

Runs as your normal user (no root): it only reads/writes the config and renders
PNGs. Endpoints:
    GET  /                       the editor page
    GET  /api/state              {config, layouts}
    GET  /api/preview?layout&playing   PNG of a layout
    GET  /api/boxes?layout       item hit-boxes (for click-to-select)
    POST /api/save               body = full config JSON -> written to the file
"""
import io
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import config as cfgmod, render

_HTML = os.path.join(os.path.dirname(__file__), "editor_static", "index.html")
BAR_W, BAR_H = 2170, 60


def _demo_state(layout_playing):
    return {"width": BAR_W, "height": BAR_H, "pressed": None,
            "media": {"status": "Playing" if layout_playing else "Stopped",
                      "position": 73.0, "length": 210.0,
                      "title": "Demo Track", "artist": "Artist"}}


class Editor:
    def __init__(self, path):
        self.path = path

    def make_handler(self):
        editor = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path == "/":
                    with open(_HTML, "rb") as f:
                        return self._send(200, f.read(), "text/html")
                if u.path == "/api/state":
                    cfg = cfgmod.load(editor.path)
                    return self._send(200, json.dumps(
                        {"config": cfg, "layouts": list(cfg["layouts"]),
                         "path": editor.path}).encode())
                if u.path == "/api/preview":
                    cfg = cfgmod.load(editor.path)
                    layout = (q.get("layout") or [None])[0] or next(iter(cfg["layouts"]), None)
                    playing = (q.get("playing") or ["0"])[0] == "1"
                    if layout not in cfg["layouts"]:
                        return self._send(404, b"no layout")
                    im = render.render(cfg, layout, _demo_state(playing))
                    buf = io.BytesIO(); im.save(buf, "PNG")
                    return self._send(200, buf.getvalue(), "image/png")
                if u.path == "/api/boxes":
                    cfg = cfgmod.load(editor.path)
                    layout = (q.get("layout") or [None])[0] or next(iter(cfg["layouts"]), None)
                    out = []
                    for i, (item, box) in enumerate(render.boxes(cfg, layout, BAR_W, BAR_H)):
                        out.append({"index": i, "id": item.get("id"),
                                    "type": item.get("type", "button"),
                                    "x0": box[0], "x1": box[2]})
                    return self._send(200, json.dumps({"width": BAR_W, "items": out}).encode())
                return self._send(404, b"not found")

            def do_POST(self):
                u = urlparse(self.path)
                if u.path == "/api/save":
                    n = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(n)
                    try:
                        cfg = json.loads(raw)
                        cfgmod.normalise(cfg)            # validate
                        with open(editor.path, "w") as f:
                            json.dump(cfg, f, indent=2)
                        return self._send(200, b'{"ok":true}')
                    except Exception as e:
                        return self._send(400, json.dumps({"error": str(e)}).encode())
                return self._send(404, b"not found")

        return H

    def serve(self, host="127.0.0.1", port=8731, open_browser=True):
        httpd = ThreadingHTTPServer((host, port), self.make_handler())
        url = f"http://{host}:{port}/"
        print(f"[t1bar] editor on {url}  (editing {self.path})", flush=True)
        print("[t1bar] tip: run `sudo t1bar run -c <config>` in another terminal to "
              "see edits on the physical bar live.", flush=True)
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
