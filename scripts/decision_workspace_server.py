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
import os
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
from the_missing_20.experiment.session import (  # noqa: E402
    ExperimentRegistry,
    ExperimentSession,
    ScenarioTransitionDenied,
)
from the_missing_20.live_sources import (  # noqa: E402
    LiveSourcePoller,
    LiveSourceRegistry,
)
from the_missing_20.ports.enterprise_systems import EnterprisePreconditionFailed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "workspace"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
STATIC_ASSETS = {
    "/assets/phosphor-regular.css": ("phosphor-regular.css", "text/css; charset=utf-8"),
    "/assets/phosphor-bold.css": ("phosphor-bold.css", "text/css; charset=utf-8"),
    "/assets/Phosphor.woff2": ("Phosphor.woff2", "font/woff2"),
    "/assets/Phosphor-Bold.woff2": ("Phosphor-Bold.woff2", "font/woff2"),
}
STATIC_ASSET_ROOT = (STATIC_ROOT / "assets").resolve()
API_SCHEMA_VERSION = "missing20-experiment-api/v1"
MAX_REQUEST_BYTES = 64 * 1024
SSE_HEARTBEAT_SECONDS = 10.0
# Delivering one real ledger frame at a time keeps the local judge experience
# legible without inventing an event: every frame is still read directly from
# the authoritative public ledger.
SSE_EVENT_PACING_SECONDS = 0.12


class APIRequestError(Exception):
    """A safe, typed error returned by an experiment API handler."""

    def __init__(
        self,
        status: HTTPStatus,
        code: str,
        detail: str,
        *,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.snapshot = snapshot


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
    if isinstance(exc, ScenarioTransitionDenied):
        return HTTPStatus.CONFLICT, "scenario_transition_required"
    if isinstance(exc, QuorumDenied):
        return HTTPStatus.CONFLICT, "decision_not_allowed"
    if isinstance(exc, EnterprisePreconditionFailed):
        return HTTPStatus.CONFLICT, "source_precondition_failed"
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

    @property
    def live_sources(self) -> LiveSourceRegistry:
        return self.server.live_sources  # type: ignore[attr-defined,no-any-return]

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
        except (LookupError, OSError, TypeError, ValueError) as exc:
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
        if route == "/api/v1/live-sources":
            self._send_json(HTTPStatus.OK, self.live_sources.current())
            return
        if route == "/api/v1/live-sources/events":
            raw_after = (query.get("after") or ["0"])[0]
            try:
                after = int(raw_after)
            except ValueError as exc:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_live_source_cursor",
                    "live-source cursor must be a non-negative integer",
                ) from exc
            if after < 0:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_live_source_cursor",
                    "live-source cursor cannot be negative",
                )
            self._send_json(HTTPStatus.OK, self.live_sources.events_since(after))
            return
        prefix = "/api/v1/incidents"
        if route == "/api/v1/scenarios":
            normal = self.registry.get("missing-20-normal").snapshot()
            active_scenario, active_incident_id = self.registry.active_scenario()
            incident_candidate = (
                self.registry.get(active_incident_id)
                if active_scenario in {"incident", "golden"}
                else None
            )
            incident = (
                incident_candidate.snapshot()
                if incident_candidate is not None
                else self.registry.scenario_incident_identity()
            )
            recovery_session = self.registry.latest_verified()
            recovery = recovery_session.snapshot() if recovery_session is not None else normal
            self._send_json(
                HTTPStatus.OK,
                {
                    "schema_version": API_SCHEMA_VERSION,
                    "current": active_incident_id,
                    "scenarios": [
                        {
                            "id": "normal",
                            "label": "Normal",
                            **_identity(normal),
                            "status": "READY",
                        },
                        {
                            "id": "incident",
                            "label": "Incident",
                            **_identity(incident),
                            "status": (
                                "ACTIVE"
                                if active_scenario in {"incident", "golden"}
                                else "READY"
                            ),
                        },
                        {
                            "id": "recovery",
                            "label": "Recovery",
                            **_identity(recovery),
                            "status": (
                                "READY"
                                if recovery_session is not None
                                else "LOCKED"
                            ),
                        },
                    ],
                },
            )
            return
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
            first = self.registry.get("missing-20-normal")
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
        if resource == "metrics":
            self._send_json(HTTPStatus.OK, session.metrics())
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
            provider_truth = self.registry.provider_truth()
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "local_synthetic_commands": True,
                    "provider_calls": provider_truth["calls_observed"],
                    "provider_mode": provider_truth["mode"],
                    "provider_configured": provider_truth["configured"],
                    "write_scope": "local_synthetic_only",
                    "advisory_tools_read_only": True,
                    "live_sources": True,
                    "external_context_only": True,
                    "schema_version": WORKSPACE_SCHEMA_VERSION,
                    "experiment_api": API_SCHEMA_VERSION,
                },
            )
            return
        if route == "/metrics":
            self._send_prometheus()
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
        if (
            route == "/api/v1/scenarios"
            or route == "/api/v1/incidents"
            or route.startswith("/api/v1/incidents/")
            or route == "/api/v1/live-sources"
            or route == "/api/v1/live-sources/events"
        ):
            try:
                self._v1_get(route, query)
            except APIRequestError as exc:
                self._send_api_error(exc.status, exc.code, exc.detail)
            except Exception as exc:  # pragma: no cover - defensive transport boundary
                status, code = _error_status(exc)
                self._send_api_error(status, code, str(exc))
            return
        if route in STATIC_ASSETS:
            relative, content_type = STATIC_ASSETS[route]
            path = (STATIC_ROOT / "assets" / relative).resolve()
            try:
                path.relative_to(STATIC_ASSET_ROOT)
            except ValueError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                payload = path.read_bytes()
            except OSError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._send(HTTPStatus.OK, payload, content_type)
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
        if route == "/api/v1/scenarios":
            scenario = str(payload.get("scenario") or "").strip().lower()
            if scenario not in {"normal", "incident", "recovery", "golden"}:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_scenario",
                    "scenario must be normal, incident, recovery, or golden",
                )
            session: ExperimentSession
            if scenario == "normal":
                # Normal is the explicit reset boundary. It does not delete any
                # completed run; it only permits a later Incident to allocate a
                # new source session.
                session = self.registry.select_normal()
            elif scenario == "recovery":
                recovery_candidate = self.registry.select_recovery()
                if recovery_candidate is None:
                    raise APIRequestError(
                        HTTPStatus.CONFLICT,
                        "scenario_not_ready",
                        "recovery is available after the approved recovery is verified",
                    )
                session = recovery_candidate
            elif scenario == "golden":
                session = self.registry.select_golden()
            else:
                # Incident is an explicit Scenario Lab command. The source
                # condition is persisted first, then the detector performs its
                # fresh read and emits ``incident.detected``.
                session = self.registry.select_incident(
                    requested_incident_id=(
                        str(payload["incident_id"])
                        if payload.get("incident_id") is not None
                        else None
                    )
                )
            snapshot = session.snapshot()
            if scenario == "recovery" and snapshot.get("execution", {}).get("verified") is not True:
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "scenario_not_ready",
                    "recovery is available after the approved recovery is verified",
                    snapshot=snapshot,
                )
            command = "scenario_selected"
            if scenario == "golden":
                session.start_investigation()
                snapshot = session.snapshot()
                command = "golden_incident_started"
            self._send_json(
                HTTPStatus.OK,
                {**snapshot, "scenario": scenario, "command": command},
            )
            return
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
            agent_id = payload.get("agent_id", "orchestrator")
            if not isinstance(question, str) or not key or not isinstance(agent_id, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_chat_request",
                    "chat requires question, agent_id, and idempotency_key",
                )
            try:
                response = session.chat_command(
                    question,
                    idempotency_key=key,
                    agent_id=agent_id,
                )
            except (QuorumDenied, ValueError) as exc:
                status, code = _error_status(exc)
                raise APIRequestError(status, code, str(exc)) from exc
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
        if route not in {"/api/v1/scenarios"} and not route.startswith("/api/v1/incidents/"):
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
            self._send_api_error(exc.status, exc.code, exc.detail, snapshot=exc.snapshot)
        except (QuorumDenied, VersionConflict, EventLedgerError, ValueError) as exc:
            status, code = _error_status(exc)
            self._send_api_error(status, code, str(exc))
        except Exception as exc:  # pragma: no cover - defensive transport boundary
            status, code = _error_status(exc)
            self._send_api_error(status, code, str(exc))

    def _send_prometheus(self) -> None:
        """Expose the same local authoritative metrics used by the native UI."""

        lines = [
            "# HELP missing20_expected_units Expected units in the active order.",
            "# TYPE missing20_expected_units gauge",
            "# HELP missing20_recorded_units Units recorded by the ERP projection.",
            "# TYPE missing20_recorded_units gauge",
            "# HELP missing20_queue_units Units currently held at the message queue.",
            "# TYPE missing20_queue_units gauge",
            "# HELP missing20_active_agents Investigators currently working.",
            "# TYPE missing20_active_agents gauge",
            "# HELP missing20_event_sequence Latest public ledger sequence.",
            "# TYPE missing20_event_sequence gauge",
            "# HELP missing20_tool_calls Tool results admitted to the public ledger.",
            "# TYPE missing20_tool_calls counter",
        ]
        for session in self.registry.list():
            metrics = session.metrics()
            incident_id = str(metrics["incident_id"]).replace('\\', '_').replace('"', '_')
            labels = f'incident_id="{incident_id}"'
            lines.extend(
                [
                    f"missing20_expected_units{{{labels}}} {metrics['expected_units']}",
                    f"missing20_recorded_units{{{labels}}} {metrics['recorded_units']}",
                    f"missing20_queue_units{{{labels}}} {metrics['queue_units']}",
                    f"missing20_active_agents{{{labels}}} {metrics['active_agents']}",
                    f"missing20_event_sequence{{{labels}}} {metrics['projection_sequence']}",
                    f"missing20_tool_calls{{{labels}}} {metrics['tool_calls']}",
                ]
            )
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        self._send(HTTPStatus.OK, payload, "text/plain; version=0.0.4; charset=utf-8")

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
        live_sources: LiveSourceRegistry | None = None,
        live_sources_autostart: bool | None = None,
    ) -> None:
        if address[0] not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("decision workspace server must bind to loopback")
        self.repository_root = repository_root.resolve()
        self.registry = registry or ExperimentRegistry(
            self.repository_root,
            data_directory=runtime_directory,
        )
        self.live_sources = live_sources or LiveSourceRegistry()
        self.live_source_poller = LiveSourcePoller(self.live_sources)
        configured_autostart = os.environ.get("MISSING20_LIVE_SOURCES_AUTOSTART", "0")
        should_autostart = (
            live_sources_autostart
            if live_sources_autostart is not None
            else configured_autostart.strip().lower() in {"1", "true", "yes", "on"}
        )
        super().__init__(address, DecisionWorkspaceHandler)
        if should_autostart:
            self.live_source_poller.start()

    def shutdown(self) -> None:
        """Stop session producers as the serving loop is asked to terminate."""

        self.live_source_poller.stop()
        self.registry.close()
        super().shutdown()

    def server_close(self) -> None:
        """Stop session producers before closing the listening socket."""

        self.live_source_poller.stop()
        self.registry.close()
        super().server_close()


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
