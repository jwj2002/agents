"""Warm embedding service for coding-memory (jns, localhost-only). stdlib only.

Keeps the FastEmbed model loaded so query/ingest skip the ~5s cold start. Binds
127.0.0.1 ONLY (never externally reachable). Start via systemd
(claude-config/systemd/coding-memory-embed.service). The CLI opts in by setting
CODING_MEMORY_EMBED_URL and falls back to in-process embedding if this is down.

  POST /embed  {"texts": [...], "kind": "doc"|"query"} -> {"vectors": [[...], ...]}
  GET  /health -> {"ok": true, "model": "..."}
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import EMBED_MODEL, embedder

HOST = "127.0.0.1"  # localhost only — residency + no external exposure
PORT = int(os.environ.get("CODING_MEMORY_EMBED_PORT", "8788"))


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (stdlib handler name)
        if self.path == "/health":
            self._send(200, {"ok": True, "model": EMBED_MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/embed":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            texts = data.get("texts") or []
            if data.get("kind") == "query":
                vecs = [embedder._embed_local_query(t) for t in texts]
            else:
                vecs = embedder._embed_local_docs(texts)
            self._send(200, {"vectors": vecs})
        except Exception as exc:  # daemon: one bad request must not kill the service
            self._send(500, {"error": str(exc)})

    def log_message(self, *args):  # silence per-request stderr noise
        pass


def main() -> None:
    embedder._get()  # warm the model at startup so the first request is fast
    ThreadingHTTPServer((HOST, PORT), _Handler).serve_forever()


if __name__ == "__main__":
    main()
