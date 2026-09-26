"""Local server for the slim WhiteBoard UI. Standard library only."""

from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from present import build_state

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
ASSETS = ROOT.parent / "assets"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._json(build_state())
            return
        if parsed.path == "/logo.png":
            self._file(ASSETS / "logo.png")
            return
        rel = parsed.path.lstrip("/") or "index.html"
        self._file(STATIC / rel)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        if parsed.path == "/api/open":
            url = str(body.get("url") or "")
            if url.startswith("http") and EDGE.is_file():
                subprocess.Popen(
                    [str(EDGE), f"--app={url}", "--new-window"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            self._json({"ok": True})
            return
        self._json({"ok": False}, status=404)

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path) -> None:
        resolved = path.resolve()
        allowed_roots = (STATIC.resolve(), ASSETS.resolve())
        if not path.is_file() or not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            self.send_error(404)
            return
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Slim WhiteBoard at http://127.0.0.1:{port}")
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
