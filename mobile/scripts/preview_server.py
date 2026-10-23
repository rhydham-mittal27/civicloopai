"""Serve a web export of a mobile app and forward /api and /health to the CivicLoop backend.

The apps talk to the API from the browser, and the backend has no cross-origin rules because the web app and the phone
apps are not served from a browser origin. This tiny server puts the page and the API on one origin so the web preview works.

    python mobile/scripts/preview_server.py <export-dir> <port> [backend-url]
"""

import http.server
import mimetypes
import socketserver
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2])
BACKEND = (sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000").rstrip("/")
HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "host", "accept-encoding"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        request = urllib.request.Request(BACKEND + self.path, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() not in HOP:
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, headers, payload = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, headers, payload = error.code, error.headers, error.read()
        except OSError:
            status, headers, payload = 502, {}, b'{"detail":"backend unreachable"}'
        self.send_response(status)
        for key, value in dict(headers).items():
            if key.lower() not in HOP:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def static(self):
        path = self.path.split("?", 1)[0].lstrip("/")
        file = (ROOT / path).resolve()
        if not str(file).startswith(str(ROOT)) or not file.is_file():
            file = ROOT / "index.html"  # single-page app: unknown paths open the app
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(file))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self):
        if self.path.startswith("/api/") or self.path == "/health":
            self.proxy()
        elif self.command == "GET":
            self.static()
        else:
            self.send_error(405)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = handle_any


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print(f"serving {ROOT} on http://localhost:{PORT}, API to {BACKEND}")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
