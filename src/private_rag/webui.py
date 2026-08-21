"""Minimal web UI: identity picker, visible documents, chat over the store.

Standard-library HTTP server on localhost, deliberately: the deployment
claim is that nothing leaves the host, and the UI should not be the
component that adds a framework dependency or a build step. One HTML
page, three JSON endpoints, everything served from loopback.

The employee picker is the demo stand-in for real sign-on, the same
known gap as the CLI's --user flag (recorded in docs/ACCESS_CONTROL.md):
the enforcement point trusts the identity it is handed, and the identity
source is where a firm's SSO plugs in. Every list and every answer in
this UI still flows through the same store enforcement as the CLI —
there is no separate retrieval path to get wrong.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .access import AccessPolicy
from .answer import DEFAULT_MODEL, OllamaAnswerer, answer_from_hits
from .audit import AuditLog
from .store import Store

_PAGE = Path(__file__).with_name("ui.html")


class _App:
    """Shared state: one store, one policy, one answerer per server."""

    def __init__(self, store: Store, policy: AccessPolicy,
                 answerer: OllamaAnswerer):
        self.store = store
        self.policy = policy
        self.answerer = answerer
        # One sqlite connection, many handler threads: serialize.
        self._lock = threading.Lock()

    def users(self) -> list[str]:
        return sorted(self.policy._grants)

    def documents(self, user: str) -> list[dict]:
        with self._lock:
            return self.store.documents_for(self.policy.resolve(user))

    def ask(self, user: str, question: str, k: int = 8) -> dict:
        identity = self.policy.resolve(user)
        with self._lock:
            hits = self.store.search(identity, question, k=k)
        result = answer_from_hits(question, hits, self.answerer)
        return {
            "user": identity.user,
            "granted_matters": sorted(identity.matters),
            "supported": result.supported,
            "answer": result.answer,
            "model": result.model,
            "citations": [
                {"doc_id": c.doc_id, "quote": c.quote, "verified": c.verified}
                for c in result.citations
            ],
        }


class _Handler(BaseHTTPRequestHandler):
    app: _App  # set on the server class before serving

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        if url.path == "/":
            body = _PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/users":
            self._json({"users": self.app.users()})
        elif url.path == "/api/documents":
            user = parse_qs(url.query).get("user", [""])[0]
            self._json({"user": user, "documents": self.app.documents(user)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/ask":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(self.app.ask(str(body["user"]),
                                    str(body["question"])))
        except (KeyError, json.JSONDecodeError):
            self._json({"error": "expected {user, question}"}, 400)
        except RuntimeError as exc:  # Ollama unreachable — say so plainly
            self._json({"error": str(exc)}, 502)

    def log_message(self, fmt, *args):  # quiet; the audit log is the record
        pass


def serve(db: Path, access: Path, audit: Path, port: int,
          embedder, model: str = DEFAULT_MODEL) -> None:
    app = _App(Store(db, embedder, audit=AuditLog(audit)),
               AccessPolicy.load(access), OllamaAnswerer(model=model))
    handler = type("Handler", (_Handler,), {"app": app})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"serving on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
