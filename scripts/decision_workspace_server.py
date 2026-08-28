"""Local HTTP adapter for the Missing 20 decision workspace.

The legacy ``/api/workspace`` route remains a read-only artifact endpoint for the
existing acceptance tests.  The ``/api/v1`` routes expose the real synthetic
experiment session used by the Dashboard and Agent Workspace.  They are local,
loopback-oriented routes only: no provider, cloud resource, or private system is
contacted by this process.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

if __package__ in {None, ""}:
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root / "src"))

from the_missing_20.authority_b.models import canonical_json  # noqa: E402
from the_missing_20.authority_b.quorum import QuorumDenied  # noqa: E402
from the_missing_20.authority_b.workspace_demo import (  # noqa: E402
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceMode,
    build_decision_workspace,
)
from the_missing_20.domain.errors import VersionConflict  # noqa: E402
from the_missing_20.experiment.ledger import EventLedgerError  # noqa: E402
from the_missing_20.experiment.session import ExperimentRegistry, ExperimentSession  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "workspace"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
API_SCHEMA_VERSION = "missing20-experiment-api/v1"
MAX_REQUEST_BYTES = 64 * 1024
SSE_HEARTBEAT_SECONDS = 10.0
# Delivering one real ledger frame at a time keeps the local judge experience
# legible without inventing an event: every frame is still read directly from
# the authoritative public ledger.
SSE_EVENT_PACING_SECONDS = 0.12


class APIRequestError(Exception):
    """A safe, typed error returned by an experiment API handler."""

    def __init__(self, status: HTTPStatus, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


def _json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _headers(content_type: str, content_length: int | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": content_type,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        ),
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return headers


def _identity(snapshot: dict[str, object]) -> dict[str, object]:
    """Return the identity fields required on every JSON experiment response."""

    return {
        "schema_version": API_SCHEMA_VERSION,
        "incident_id": snapshot["incident_id"],
        "trace_id": snapshot["trace_id"],
        "case_version": snapshot["case_version"],
        "projection_sequence": snapshot["projection_sequence"],
    }


def _error_status(exc: Exception) -> tuple[HTTPStatus, str]:
    if isinstance(exc, VersionConflict):
        return HTTPStatus.CONFLICT, "stale_case_version"
    if isinstance(exc, QuorumDenied):
        return HTTPStatus.CONFLICT, "decision_not_allowed"
    if isinstance(exc, EventLedgerError):
        return HTTPStatus.UNPROCESSABLE_ENTITY, "event_ledger_invalid"
    if isinstance(exc, ValueError):
        return HTTPStatus.BAD_REQUEST, "invalid_request"
    return HTTPStatus.INTERNAL_SERVER_ERROR, "experiment_unavailable"


class DecisionWorkspaceHandler(BaseHTTPRequestHandler):
    """Read-only legacy adapter plus the local experiment API."""

    server_version = "Missing20Workspace/2"

    @property
    def repository_root(self) -> Path:
        return self.server.repository_root  # type: ignore[attr-defined,no-any-return]

    @property
    def registry(self) -> ExperimentRegistry:
        return self.server.registry  # type: ignore[attr-defined,no-any-return]

    def _send(
        self,
        status: HTTPStatus,
        payload: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        headers = _headers(content_type, len(payload))
        if extra_headers:
            headers.update(extra_headers)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: HTTPStatus, value: object) -> None:
        self._send(status, _json_bytes(value), "application/json; charset=utf-8")

    def _send_api_error(
        self,
        status: HTTPStatus,
        code: str,
        detail: str,
        *,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "schema_version": API_SCHEMA_VERSION,
            "error": {"code": code, "detail": detail},
        }
        if snapshot is not None:
            payload.update(_identity(snapshot))
        self._send_json(status, payload)

    def _method_not_allowed(self, allow: str = "GET") -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        for key, value in _headers("application/json; charset=utf-8", 0).items():
            self.send_header(key, value)
        self.send_header("Allow", allow)
        self.end_headers()

    def _session(self, incident_id: str) -> ExperimentSession:
        try:
            return self.registry.get(incident_id)
        except (OSError, TypeError, ValueError) as exc:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "incident_not_found", str(exc)) from exc

    def _read_json(self, *, allow_empty: bool = False) -> dict[str, object]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be an integer",
            ) from exc
        if length == 0 and allow_empty:
            return {}
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request_size",
                f"request body must be between 1 and {MAX_REQUEST_BYTES} bytes",
            )
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST, "invalid_json", "request body must be valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST, "invalid_json_shape", "request body must be a JSON object"
            )
        return payload

    @staticmethod
    def _after_sequence(query: dict[str, list[str]], header: str | None) -> int:
        values = query.get("after") or query.get("after_sequence")
        raw = values[0] if values else (header or "0")
        try:
            sequence = int(raw)
        except ValueError as exc:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_sequence",
                "event sequence must be a non-negative integer",
            ) from exc
        if sequence < 0:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "invalid_sequence",
                "event sequence cannot be negative",
            )
        return sequence

    def _v1_get(self, route: str, query: dict[str, list[str]]) -> None:
        prefix = "/api/v1/incidents"
        if route == prefix:
            sessions = self.registry.list()
            summaries = []
            for session in sessions:
                snapshot = session.snapshot()
                incident = snapshot["incident"]
                summaries.append(
                    {
                        **_identity(snapshot),
                        "status": incident["status"],
                        "scenario_id": incident["scenario_id"],
                        "unit_counts": snapshot["unit_counts"],
                        "advisory": snapshot["advisory"],
                    }
                )
            first = self.registry.get()
            first_snapshot = first.snapshot()
            self._send_json(
                HTTPStatus.OK,
                {
                    **_identity(first_snapshot),
                    "incidents": summaries,
                },
            )
            return

        parts = route[len(prefix) :].strip("/").split("/")
        if not parts or not parts[0]:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "not_found", "incident route not found")
        incident_id = unquote(parts[0])
        session = self._session(incident_id)
        snapshot = session.snapshot()
        if len(parts) == 1:
            if query.get("compact") == ["1"]:
                # Browser-smoke captures validate the authoritative projection,
                # not the complete historical ledger. Keep the same lifecycle
                # state while omitting large collections that the client does
                # not need when ``smoke=1`` disables SSE and live operations.
                lifecycle_tail = [
                    event
                    for event in snapshot.get("events", [])
                    if event.get("event_type") in {"execution.completed", "verification.completed"}
                ]
                snapshot = {
                    key: value
                    for key, value in snapshot.items()
                    if key not in {"activity", "events", "evidence", "units"}
                }
                snapshot["activity"] = lifecycle_tail
                snapshot["events"] = lifecycle_tail
                snapshot["evidence"] = []
            self._send_json(HTTPStatus.OK, snapshot)
            return
        if len(parts) != 2:
            raise APIRequestError(HTTPStatus.NOT_FOUND, "not_found", "incident route not found")
        resource = parts[1]
        if resource == "units":
            self._send_json(
                HTTPStatus.OK,
                {
                    **_identity(snapshot),
                    "unit_counts": snapshot["unit_counts"],
                    "units": snapshot["units"],
                },
            )
            return
        if resource == "events":
            self._send_sse(session, query)
            return
        raise APIRequestError(HTTPStatus.NOT_FOUND, "not_found", "incident resource not found")

    def _send_sse(self, session: ExperimentSession, query: dict[str, list[str]]) -> None:
        after = self._after_sequence(query, self.headers.get("Last-Event-ID"))
        replay = query.get("replay") == ["1"]
        latest = session.ledger.latest_sequence(session.incident_id)
        if after > latest:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "future_cursor",
                "event sequence is beyond the current incident ledger",
            )
        self.send_response(HTTPStatus.OK)
        for key, value in _headers("text/event-stream; charset=utf-8").items():
            self.send_header(key, value)
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            # Keep the stream open for the lifetime of the browser subscription.
            # A fixed-duration stream can leave the UI showing LIVE after the
            # server has silently closed it; heartbeats keep idle connections
            # observable while ``wait_for_events`` wakes immediately for later
            # ledger appends.
            while True:
                current_latest = session.ledger.latest_sequence(session.incident_id)
                if after > current_latest:
                    # The durable ledger may have been rotated while a browser
                    # connection was idle. Signal a typed reset instead of
                    # leaving the old cursor subscribed forever.
                    reset = {
                        "incident_id": session.incident_id,
                        "safe_cursor": current_latest,
                        "reason": "ledger_cursor_reset",
                    }
                    self.wfile.write(
                        b"event: stream.reset\n" + f"data: {canonical_json(reset)}\n\n".encode()
                    )
                    self.wfile.flush()
                    return
                events = session.events_since(after)
                if events:
                    for event in events:
                        wire_event = event.model_dump(mode="json")
                        frame = (
                            f"id: {event.sequence}\n"
                            f"event: {event.event_type.value}\n"
                            f"data: {canonical_json(wire_event)}\n\n"
                        ).encode()
                        self.wfile.write(frame)
                        self.wfile.flush()
                        after = event.sequence
                        time.sleep(SSE_EVENT_PACING_SECONDS)
                    continue
                if replay:
                    # A replay is a finite re-emission of the immutable ledger;
                    # it must not remain subscribed as though it were a new run.
                    return
                if not session.wait_for_events(after, timeout=SSE_HEARTBEAT_SECONDS):
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        route = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if route == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "local_synthetic_commands": True,
                    "provider_calls": False,
                    "write_scope": "local_synthetic_only",
                    "advisory_tools_read_only": True,
                    "schema_version": WORKSPACE_SCHEMA_VERSION,
                    "experiment_api": API_SCHEMA_VERSION,
                },
            )
            return
        if route == "/api/workspace":
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
        if route == "/api/v1/incidents" or route.startswith("/api/v1/incidents/"):
            try:
                self._v1_get(route, query)
            except APIRequestError as exc:
                self._send_api_error(exc.status, exc.code, exc.detail)
            except Exception as exc:  # pragma: no cover - defensive transport boundary
                status, code = _error_status(exc)
                self._send_api_error(status, code, str(exc))
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

    def _v1_post(self, route: str, payload: dict[str, object]) -> None:
        prefix = "/api/v1/incidents/"
        parts = route[len(prefix) :].strip("/").split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise APIRequestError(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "experiment command route not found",
            )
        session = self._session(unquote(parts[0]))
        resource = parts[1]
        if resource == "start":
            started = session.start_investigation()
            snapshot = session.snapshot()
            self._send_json(
                HTTPStatus.OK,
                {
                    **snapshot,
                    "command": (
                        "investigation_started" if started else "investigation_already_complete"
                    ),
                },
            )
            return
        if resource == "chat":
            question = payload.get("question")
            key = str(payload.get("idempotency_key") or "").strip()
            if not isinstance(question, str) or not key:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_chat_request",
                    "chat requires question and idempotency_key",
                )
            response = session.chat_command(question, idempotency_key=key)
            snapshot = session.snapshot()
            self._send_json(HTTPStatus.OK, {**_identity(snapshot), **response})
            return
        if resource == "decisions":
            try:
                response = session.decision_command(payload)
            except (QuorumDenied, VersionConflict, ValueError) as exc:
                status, code = _error_status(exc)
                raise APIRequestError(status, code, str(exc)) from exc
            self._send_json(HTTPStatus.OK, response)
            return
        raise APIRequestError(HTTPStatus.NOT_FOUND, "not_found", "experiment command not found")

    def do_POST(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        if route == "/api/workspace":
            self._method_not_allowed("GET")
            return
        if not route.startswith("/api/v1/incidents/"):
            self._method_not_allowed("GET")
            return
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_api_error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "json_required",
                "POST requests require Content-Type: application/json",
            )
            return
        origin = self.headers.get("Origin")
        if origin:
            host = self.headers.get("Host", "")
            allowed_origins = {f"http://{host}", f"https://{host}"}
            if origin not in allowed_origins:
                self._send_api_error(
                    HTTPStatus.FORBIDDEN,
                    "origin_not_allowed",
                    "local API accepts only same-origin requests",
                )
                return
        try:
            payload = self._read_json(allow_empty=route.endswith("/start"))
            self._v1_post(route, payload)
        except APIRequestError as exc:
            self._send_api_error(exc.status, exc.code, exc.detail)
        except (QuorumDenied, VersionConflict, EventLedgerError, ValueError) as exc:
            status, code = _error_status(exc)
            self._send_api_error(status, code, str(exc))
        except Exception as exc:  # pragma: no cover - defensive transport boundary
            status, code = _error_status(exc)
            self._send_api_error(status, code, str(exc))

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
    """Threaded loopback server carrying the repository and session registry."""

    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Suppress only expected client-close noise from long-lived SSE streams."""

        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

    def __init__(
        self,
        address: tuple[str, int],
        repository_root: Path = ROOT,
        *,
        runtime_directory: Path | None = None,
        registry: ExperimentRegistry | None = None,
    ) -> None:
        if address[0] not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("decision workspace server must bind to loopback")
        self.repository_root = repository_root.resolve()
        self.registry = registry or ExperimentRegistry(
            self.repository_root,
            data_directory=runtime_directory,
        )
        super().__init__(address, DecisionWorkspaceHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--runtime-directory",
        type=Path,
        default=None,
        help="directory for the local synthetic session ledger (defaults to a temporary directory)",
    )
    args = parser.parse_args()
    try:
        server = DecisionWorkspaceServer(
            (args.host, args.port),
            ROOT,
            runtime_directory=args.runtime_directory,
        )
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
