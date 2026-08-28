"""Read-only local HTTP server for the M5 Decision Workspace.

The server intentionally has no mutation route and binds to loopback by default.
It computes each mode from the repository's persisted, synthetic records; no
provider, cloud, or remote resource is contacted.
"""

from __future__ import annotations

import argparse
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

if __package__ in {None, ""}:
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root / "src"))

from the_missing_20.authority_b.models import canonical_json  # noqa: E402
from the_missing_20.authority_b.workspace_demo import (  # noqa: E402
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceMode,
    build_decision_workspace,
)

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "workspace"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def _json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _headers(content_type: str, content_length: int) -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "Content-Length": str(content_length),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        ),
    }


class DecisionWorkspaceHandler(BaseHTTPRequestHandler):
    """One-way HTTP adapter: GET only, fixed local resource allowlist."""

    server_version = "Missing20Workspace/1"

    @property
    def repository_root(self) -> Path:
        return self.server.repository_root  # type: ignore[attr-defined,no-any-return]

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        for key, value in _headers(content_type, len(payload)).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: HTTPStatus, value: object) -> None:
        self._send(status, _json_bytes(value), "application/json; charset=utf-8")

    def _method_not_allowed(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        for key, value in _headers("application/json; charset=utf-8", 0).items():
            self.send_header(key, value)
        self.send_header("Allow", "GET")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        route = parsed.path
        if route == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "read_only": True,
                    "schema_version": WORKSPACE_SCHEMA_VERSION,
                },
            )
            return
        if route == "/api/workspace":
            query = parse_qs(parsed.query, keep_blank_values=True)
            requested = query.get("mode", [WorkspaceMode.COMPLETE.value])[0]
            try:
                mode = WorkspaceMode(requested)
                artifact = build_decision_workspace(self.repository_root, mode=mode)
            except (OSError, TypeError, ValueError) as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "workspace_unavailable", "detail": str(exc)},
                )
                return
            self._send_json(HTTPStatus.OK, artifact.model_dump(mode="json"))
            return
        if route in STATIC_FILES:
            relative, content_type = STATIC_FILES[route]
            path = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT.resolve() not in path.parents:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                payload = path.read_bytes()
            except OSError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._send(HTTPStatus.OK, payload, content_type)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_HEAD(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def log_message(self, format: str, *args: object) -> None:
        # Keep local smoke output concise and avoid reflecting arbitrary request text.
        del format, args


class DecisionWorkspaceServer(ThreadingHTTPServer):
    """Threaded loopback server carrying the repository root explicitly."""

    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], repository_root: Path = ROOT) -> None:
        self.repository_root = repository_root.resolve()
        super().__init__(address, DecisionWorkspaceHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        server = DecisionWorkspaceServer((args.host, args.port), ROOT)
    except OSError as exc:
        print(f"Decision Workspace server: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(f"Decision Workspace server: http://{args.host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
