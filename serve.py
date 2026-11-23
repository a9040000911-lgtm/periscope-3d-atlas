"""Local HTTP development server for the Periskope 3D prototype."""

from __future__ import annotations

import functools
import http.server
import mimetypes
import socketserver
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8080

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("image/vnd.radiance", ".hdr")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/ktx2", ".ktx2")


class PeriskopeHandler(http.server.SimpleHTTPRequestHandler):
    """Serve project files with clean MIME types, UTF-8 defaults, and root redirect."""

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".json": "application/json; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".wasm": "application/wasm",
        ".hdr": "image/vnd.radiance",
        ".webp": "image/webp",
        ".ktx2": "image/ktx2",
    }

    def do_GET(self) -> None:
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    handler = functools.partial(PeriskopeHandler, directory=str(ROOT_DIR))
    with ReusableTCPServer((HOST, PORT), handler) as httpd:
        print(f"Periskope 3D server running at http://{HOST}:{PORT}/web/", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
