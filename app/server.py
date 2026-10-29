"""Local HTTP server (127.0.0.1 only).

Always serves the built UI. In ``--dev`` mode it also exposes the same API as the
pywebview bridge over HTTP (POST /api/call, GET /api/events, POST /api/upload) so the
UI can be driven from a normal browser or Playwright during development and tests.
Every API request must carry the per-session token.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import dispatch
from .backend import Backend

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")


class EventQueue:
    def __init__(self):
        self.events: list[dict] = []
        self.base = 0  # index of events[0] in the overall stream
        self.cv = threading.Condition()

    def push(self, ev: dict) -> None:
        with self.cv:
            self.events.append(ev)
            if len(self.events) > 2000:
                drop = len(self.events) - 1000
                self.events = self.events[drop:]
                self.base += drop
            self.cv.notify_all()

    def after(self, n: int, timeout: float = 15.0) -> tuple[int, list[dict]]:
        end = time.time() + timeout
        with self.cv:
            while self.base + len(self.events) <= n and time.time() < end:
                self.cv.wait(max(0.0, end - time.time()))
            total = self.base + len(self.events)
            return total, self.events[max(0, n - self.base):]


def make_server(ui_root: Path, backend: Backend | None, dev: bool, port: int = 0,
                events: EventQueue | None = None) -> tuple[ThreadingHTTPServer, str]:
    token = secrets.token_urlsafe(16)
    upload_dir = Path(tempfile.mkdtemp(prefix="elv-dev-upload-"))

    class Handler(BaseHTTPRequestHandler):
        server_version = "ELVEstimator"

        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def _authorised(self) -> bool:
            return dev and backend is not None and self.headers.get("X-ELV-Token") == token

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path == "/api/events":
                if not self._authorised():
                    return self._json({"error": "forbidden"}, 403)
                n = int(urllib.parse.parse_qs(url.query).get("after", ["0"])[0])
                total, evs = events.after(n)
                return self._json({"next": total, "events": evs})
            rel = urllib.parse.unquote(url.path.lstrip("/")) or "index.html"
            f = (ui_root / rel).resolve()
            if not str(f).startswith(str(ui_root.resolve())) or not f.is_file():
                f = ui_root / "index.html"
            if not f.exists():
                return self._send(404, b"UI not built. Run: cd ui && npm ci && npm run build", "text/plain")
            body = f.read_bytes()
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if f.name == "index.html":
                inject = f'<script>window.__ELV_DEV={json.dumps(dev)};window.__ELV_TOKEN={json.dumps(token if dev else "")};</script>'
                body = body.replace(b"</head>", inject.encode() + b"</head>", 1)
                ctype = "text/html; charset=utf-8"
            self._send(200, body, ctype)

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            if not self._authorised():
                return self._json({"error": "forbidden"}, 403)
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b""
            if url.path == "/api/call":
                req = json.loads(raw or b"{}")
                return self._json(dispatch(backend, req.get("method", ""), req.get("args")))
            if url.path == "/api/upload":
                name = Path(urllib.parse.parse_qs(url.query).get("name", ["upload.bin"])[0]).name
                d = upload_dir / secrets.token_hex(4)
                d.mkdir(parents=True, exist_ok=True)
                (d / name).write_bytes(raw)
                return self._json({"ok": True, "data": str(d / name)})
            return self._json({"error": "not found"}, 404)

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    threading.Thread(target=httpd.serve_forever, daemon=True, name="ui-server").start()
    return httpd, url
