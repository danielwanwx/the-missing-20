"""Local HTTP adapter for the Missing 20 decision workspace.

The legacy ``/api/workspace`` route remains a read-only artifact endpoint for the
existing acceptance tests. The ``/api/v1`` routes expose the deterministic experiment
and a multi-SaaS evidence projection used by the Dashboard. They are local,
loopback-oriented routes only. Agent tools remain read-only; an explicitly configured
demo-tenant executor may apply one Manager-gated, idempotent ERPNext recovery.
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

from the_missing_20.adapters.agent_platform import AgentPlatform  # noqa: E402
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform  # noqa: E402
from the_missing_20.adapters.ambiguous_receipt_source import (  # noqa: E402
    AmbiguousReceiptEvidenceSource,
)
from the_missing_20.adapters.demo_executor import ERPNextDemoExecutor  # noqa: E402
from the_missing_20.adapters.erpnext_source import (  # noqa: E402
    ERPNextEvidenceSource,
    _read_env_file,
)
from the_missing_20.adapters.external_source_change import (  # noqa: E402
    ExternalSourceChangeDetector,
)
from the_missing_20.adapters.live_advisory_gateway import (  # noqa: E402
    DashboardAdvisoryGateway,
    connected_competition_investigation_packet,
)
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource  # noqa: E402
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
from the_missing_20.ports.agent_model import AgentProvider  # noqa: E402
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
    "/assets/geist-latin.woff2": ("geist-latin.woff2", "font/woff2"),
    "/assets/geist-mono-latin.woff2": ("geist-mono-latin.woff2", "font/woff2"),
}
STATIC_ASSET_ROOT = (STATIC_ROOT / "assets").resolve()
API_SCHEMA_VERSION = "missing20-experiment-api/v1"
MAX_REQUEST_BYTES = 64 * 1024
SSE_HEARTBEAT_SECONDS = 10.0
# Delivering one real ledger frame at a time keeps the local judge experience
# legible without inventing an event: every frame is still read directly from
# the authoritative public ledger.
SSE_EVENT_PACING_SECONDS = 0.12
BROWSER_EVENT_TAIL_LIMIT = 96
BROWSER_EVENT_ANCHORS = frozenset(
    {
        "source.condition.injected",
        "incident.detected",
        "investigation.started",
        "agent.started",
        "agent.completed",
        "evaluation.completed",
        "recovery.prepared",
        "approval.requested",
        "approval.recorded",
        "execution.started",
        "execution.completed",
        "verification.started",
        "verification.completed",
    }
)


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
            # The command canvas uses bounded client-side positioning for
            # draggable modules, graph anchors, and live metric bars. Permit
            # style attributes while keeping scripts, connections, images,
            # frames, and form submissions locked to this local origin.
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        ),
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return headers


def _browser_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Bound initial browser history while preserving current authoritative state.

    The immutable ledger remains available through cursor-based SSE.  Shipping
    thousands of historical payloads before the browser can render its first
    frame turns an old demo run into a multi-megabyte bootstrap response.  The
    browser only needs the recent tail plus lifecycle anchors to reconstruct a
    truthful starting view and subscribe from the latest sequence.
    """

    raw_events = snapshot.get("events")
    events = (
        [item for item in raw_events if isinstance(item, dict)]
        if isinstance(raw_events, list)
        else []
    )
    selected = events[-BROWSER_EVENT_TAIL_LIMIT:]
    latest_anchors: dict[str, dict[str, Any]] = {}
    first_detection: dict[str, Any] | None = None
    for event in events:
        event_type = str(event.get("event_type") or event.get("event") or "")
        if (
            event_type in {"source.condition.injected", "incident.detected"}
            and first_detection is None
        ):
            first_detection = event
        if event_type in BROWSER_EVENT_ANCHORS:
            latest_anchors[event_type] = event
    by_sequence: dict[int, dict[str, Any]] = {}
    for event in (
        ([first_detection] if first_detection is not None else [])
        + list(latest_anchors.values())
        + selected
    ):
        sequence = event.get("sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            by_sequence[sequence] = event
    bounded = [by_sequence[key] for key in sorted(by_sequence)]
    projected = dict(snapshot)
    projected["events"] = bounded
    projected["activity"] = bounded
    projected["event_window"] = {
        "total": len(events),
        "returned": len(bounded),
        "truncated": len(bounded) < len(events),
    }
    return projected


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

    @property
    def erpnext_evidence(self) -> ERPNextEvidenceSource:
        return self.server.erpnext_evidence  # type: ignore[attr-defined,no-any-return]

    @property
    def saas_evidence(self) -> SaaSEvidenceSource:
        return self.server.saas_evidence  # type: ignore[attr-defined,no-any-return]

    @property
    def agent_platform(self) -> AgentPlatform | AmbiguousCasePlatform:
        return self.server.agent_platform  # type: ignore[attr-defined,no-any-return]

    @property
    def ambiguous_receipt(self) -> AmbiguousReceiptEvidenceSource:
        return self.server.ambiguous_receipt  # type: ignore[attr-defined,no-any-return]

    @property
    def agent_advisory(self) -> DashboardAdvisoryGateway:
        return self.server.agent_advisory  # type: ignore[attr-defined,no-any-return]

    @property
    def case_console_source_mode(self) -> str:
        return self.server.case_console_source_mode  # type: ignore[attr-defined,no-any-return]

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
        if route == "/api/v1/agent-platform":
            self._send_json(HTTPStatus.OK, self.agent_platform.current())
            return
        if route == "/api/v1/agent-platform/events":
            self._send_agent_platform_sse(query)
            return
        if route == "/api/v1/ambiguous-receipt-case":
            self._send_json(HTTPStatus.OK, self.ambiguous_receipt.current())
            return
        if route == "/api/v1/erpnext-evidence":
            projection = self.erpnext_evidence.current()
            self.server.observe_external_change("erpnext", projection)  # type: ignore[attr-defined]
            self._send_json(HTTPStatus.OK, projection)
            return
        if route == "/api/v1/saas-evidence":
            projection = self.saas_evidence.current()
            self.server.observe_external_change("saas", projection)  # type: ignore[attr-defined]
            self._send_json(HTTPStatus.OK, projection)
            return
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
            incident = incident_candidate.snapshot() if incident_candidate is not None else None
            recovery_session = self.registry.latest_verified()
            recovery = recovery_session.snapshot() if recovery_session is not None else None
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
                            **(_identity(incident) if incident is not None else {}),
                            "status": (
                                "ACTIVE" if active_scenario in {"incident", "golden"} else "READY"
                            ),
                            "launch_method": "POST" if incident is None else "OPEN",
                            "deep_link_available": incident is not None,
                        },
                        {
                            "id": "recovery",
                            "label": "Recovery",
                            **(_identity(recovery) if recovery is not None else {}),
                            "status": ("READY" if recovery_session is not None else "LOCKED"),
                            "deep_link_available": recovery is not None,
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
            if query.get("projection") == ["browser"]:
                snapshot = _browser_snapshot(snapshot)
            elif query.get("compact") == ["1"]:
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
        replay_target = latest if replay else None
        if after > latest:
            raise APIRequestError(
                HTTPStatus.BAD_REQUEST,
                "future_cursor",
                "event sequence is beyond the current incident ledger",
            )
        self.send_response(HTTPStatus.OK)
        for key, value in _headers("text/event-stream; charset=utf-8").items():
            self.send_header(key, value)
        self.send_header("Connection", "close" if replay else "keep-alive")
        if replay:
            self.close_connection = True
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
                if replay_target is not None:
                    events = tuple(event for event in events if event.sequence <= replay_target)
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
                        # Replay restores persisted truth; it is not a synthetic
                        # animation. Catch it up immediately, then let the live
                        # subscription provide the reviewer-visible cadence.
                        if not replay:
                            time.sleep(SSE_EVENT_PACING_SECONDS)
                    if replay_target is not None and after >= replay_target:
                        return
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

    def _send_agent_platform_sse(self, query: dict[str, list[str]]) -> None:
        """Stream only activity appended by the Case Console server ledger."""

        after = self._after_sequence(query, self.headers.get("Last-Event-ID"))
        self.send_response(HTTPStatus.OK)
        for key, value in _headers("text/event-stream; charset=utf-8").items():
            self.send_header(key, value)
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            idle_since = time.monotonic()
            while True:
                events = self.agent_platform.events_since(after)
                if events:
                    for event in events:
                        raw_sequence = event.get("sequence")
                        if not isinstance(raw_sequence, int):
                            continue
                        sequence = raw_sequence
                        frame = (
                            f"id: {sequence}\n"
                            "event: case.activity\n"
                            f"data: {canonical_json(event)}\n\n"
                        ).encode()
                        self.wfile.write(frame)
                        self.wfile.flush()
                        after = sequence
                    idle_since = time.monotonic()
                    continue
                if time.monotonic() - idle_since >= SSE_HEARTBEAT_SECONDS:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    idle_since = time.monotonic()
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        route = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if route == "/healthz":
            compatibility_truth = self.registry.provider_truth()
            platform_truth_reader = getattr(self.agent_platform, "runtime_truth", None)
            platform_truth = platform_truth_reader() if callable(platform_truth_reader) else {}
            advisory_truth_reader = getattr(self.agent_advisory, "runtime_truth", None)
            advisory_truth = advisory_truth_reader() if callable(advisory_truth_reader) else {}
            provider_calls = bool(
                compatibility_truth["calls_observed"] or platform_truth.get("calls_observed", False)
            )
            provider_mode = str(
                (
                    platform_truth.get("provider_mode")
                    if platform_truth.get("calls_observed")
                    else None
                )
                or advisory_truth.get("provider_mode")
                or compatibility_truth["mode"]
            )
            provider_configured = bool(
                advisory_truth.get("provider_configured", False)
                or compatibility_truth["configured"]
            )
            external_writes = str(platform_truth.get("external_provider_writes", "disabled"))
            write_scope = str(
                platform_truth.get(
                    "write_scope",
                    "local_synthetic_only"
                    if self.case_console_source_mode == "synthetic"
                    else "read_only",
                )
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "local_synthetic_commands": True,
                    "provider_calls": provider_calls,
                    "provider_mode": provider_mode,
                    "provider_configured": provider_configured,
                    "write_scope": write_scope,
                    "external_provider_writes": external_writes,
                    "advisory_tools_read_only": True,
                    "live_sources": True,
                    "external_context_only": True,
                    "paths": {
                        "hero_case_console": {**platform_truth, **advisory_truth},
                        "legacy_compatibility_harness": compatibility_truth,
                    },
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
            route == "/api/v1/agent-platform"
            or route == "/api/v1/agent-platform/events"
            or route == "/api/v1/ambiguous-receipt-case"
            or route == "/api/v1/scenarios"
            or route == "/api/v1/incidents"
            or route.startswith("/api/v1/incidents/")
            or route == "/api/v1/live-sources"
            or route == "/api/v1/live-sources/events"
            or route == "/api/v1/erpnext-evidence"
            or route == "/api/v1/saas-evidence"
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
        if route == "/api/v1/agent-platform/diagnose":
            if set(payload) - {"operator_id"}:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "unexpected_payload",
                    "diagnosis accepts only the human operator identity",
                )
            operator_id = payload.get("operator_id")
            if not isinstance(operator_id, str) or not operator_id.strip():
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "diagnosis_authorization_required",
                    "diagnosis requires an explicit human operator identity",
                )
            authorize = getattr(self.agent_platform, "authorize_diagnosis", None)
            if callable(authorize):
                authorize(operator_id)
            claim = getattr(self.agent_platform, "claim_diagnosis", None)
            if callable(claim):
                projection, started = claim()
                if not started:
                    self._send_json(HTTPStatus.OK, projection)
                    return
            else:
                projection = self.agent_platform.diagnose()
            advisory = self.agent_advisory.investigate(projection)
            self._send_json(
                HTTPStatus.OK, self.agent_platform.record_strands_investigation(advisory)
            )
            return
        if route == "/api/v1/agent-platform/counterfactual":
            variant = payload.get("variant")
            if not isinstance(variant, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_counterfactual",
                    "counterfactual requires a named variant",
                )
            if not isinstance(self.agent_platform, AmbiguousCasePlatform):
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "unsupported_counterfactual_mode",
                    "counterfactuals are isolated synthetic-tenant cases",
                )
            self._send_json(HTTPStatus.OK, self.agent_platform.reset_variant(variant))
            return
        if route == "/api/v1/agent-platform/stop":
            if payload:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "unexpected_payload",
                    "pause preserves evidence and accepts no provider commands",
                )
            self._send_json(HTTPStatus.OK, self.agent_platform.stop())
            return
        if route == "/api/v1/agent-platform/ask":
            question = payload.get("question")
            if not isinstance(question, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_question",
                    "evidence questions require a text question",
                )
            self._send_json(HTTPStatus.OK, self.agent_advisory.ask(question))
            return
        if route == "/api/v1/agent-platform/approve":
            manager_id = payload.get("manager_id")
            if not isinstance(manager_id, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST, "invalid_manager", "approval requires manager_id"
                )
            self._send_json(HTTPStatus.OK, self.agent_platform.approve(manager_id))
            return
        if route == "/api/v1/agent-platform/reject":
            manager_id = payload.get("manager_id")
            reason = payload.get("reason")
            if not isinstance(manager_id, str) or not isinstance(reason, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_rejection",
                    "rejection requires manager_id and reason",
                )
            reject = getattr(self.agent_platform, "reject_plan", None)
            if not callable(reject):
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "unsupported_rejection_mode",
                    "plan rejection is unavailable for this platform mode",
                )
            self._send_json(HTTPStatus.OK, reject(manager_id, reason))
            return
        if route == "/api/v1/agent-platform/approve-and-execute":
            manager_id = payload.get("manager_id")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(manager_id, str) or not isinstance(idempotency_key, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_approval",
                    "approval requires manager_id and idempotency_key",
                )
            approve_execute_verify = getattr(self.agent_platform, "approve_execute_verify", None)
            if not callable(approve_execute_verify):
                raise APIRequestError(
                    HTTPStatus.CONFLICT,
                    "unsupported_execution_mode",
                    "one-click guarded execution is unavailable for this platform mode",
                )
            self._send_json(
                HTTPStatus.OK,
                approve_execute_verify(manager_id, idempotency_key),
            )
            return
        if route == "/api/v1/agent-platform/execute":
            approval_id = payload.get("approval_id")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(approval_id, str) or not isinstance(idempotency_key, str):
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_execution",
                    "execution requires approval_id and idempotency_key",
                )
            self._send_json(
                HTTPStatus.OK, self.agent_platform.execute(approval_id, idempotency_key)
            )
            return
        if route == "/api/v1/agent-platform/verify":
            if payload:
                raise APIRequestError(
                    HTTPStatus.BAD_REQUEST,
                    "unexpected_payload",
                    "verification is a fresh provider read and accepts no commands",
                )
            self._send_json(HTTPStatus.OK, self.agent_platform.verify())
            return
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
            if scenario in {"incident", "golden"} and isinstance(
                self.agent_platform, AmbiguousCasePlatform
            ):
                # The current Case Console is the authoritative judge path.
                # A newly admitted legacy compatibility session must begin
                # with the same fresh case/run truth, never a persisted result
                # from a previous demo take.
                self.agent_platform.reset()
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
                if str(payload.get("command") or "") in {"execute", "recover"}:
                    intent_id = str(payload.get("intent_id") or "").strip()
                    idempotency_key = str(payload.get("idempotency_key") or "").strip()
                    if not intent_id or not idempotency_key:
                        raise ValueError("execution requires an intent_id and idempotency_key")
                    response = session.accept_execution(
                        intent_id=intent_id,
                        idempotency_key=idempotency_key,
                    )
                else:
                    response = session.decision_command(payload)
            except (QuorumDenied, VersionConflict, ValueError) as exc:
                status, code = _error_status(exc)
                raise APIRequestError(status, code, str(exc)) from exc
            status = (
                HTTPStatus.ACCEPTED
                if response.get("command") == "execution_accepted"
                else HTTPStatus.OK
            )
            self._send_json(status, response)
            return
        raise APIRequestError(HTTPStatus.NOT_FOUND, "not_found", "experiment command not found")

    def do_POST(self) -> None:  # noqa: N802
        route = urlsplit(self.path).path
        if route == "/api/workspace":
            self._method_not_allowed("GET")
            return
        allowed_routes = {
            "/api/v1/scenarios",
            "/api/v1/agent-platform/ask",
            "/api/v1/agent-platform/diagnose",
            "/api/v1/agent-platform/counterfactual",
            "/api/v1/agent-platform/stop",
            "/api/v1/agent-platform/approve",
            "/api/v1/agent-platform/reject",
            "/api/v1/agent-platform/approve-and-execute",
            "/api/v1/agent-platform/execute",
            "/api/v1/agent-platform/verify",
        }
        if route not in allowed_routes and not route.startswith("/api/v1/incidents/"):
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
            payload = self._read_json(
                allow_empty=route.endswith("/start") or route.endswith("/diagnose")
            )
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
            incident_id = str(metrics["incident_id"]).replace("\\", "_").replace('"', "_")
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
        erpnext_evidence: ERPNextEvidenceSource | None = None,
        saas_evidence: SaaSEvidenceSource | None = None,
        ambiguous_receipt: AmbiguousReceiptEvidenceSource | None = None,
        agent_platform: AgentPlatform | AmbiguousCasePlatform | None = None,
        agent_advisory: DashboardAdvisoryGateway | None = None,
        live_sources_autostart: bool | None = None,
    ) -> None:
        if address[0] not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("decision workspace server must bind to loopback")
        self.repository_root = repository_root.resolve()
        self.registry = registry or ExperimentRegistry(
            self.repository_root,
            data_directory=runtime_directory,
            # The legacy graph is a local compatibility projection. Keep its
            # harness deterministic and cost-free; the Case Console is the
            # only surface that may invoke the separately configured real,
            # read-only Strands advisory agent.
            provider_mode=AgentProvider.SCRIPTED,
            # Dashboard motion is source-driven: the initial authoritative
            # snapshot is visible, then the ledger stays still until an
            # operator/source transition or workflow event actually occurs.
            periodic_telemetry_enabled=False,
        )
        self.live_sources = live_sources or LiveSourceRegistry()
        self.erpnext_evidence = erpnext_evidence or ERPNextEvidenceSource.from_environment(
            repository_root=repository_root
        )
        self.saas_evidence = saas_evidence or SaaSEvidenceSource.from_environment(
            repository_root=repository_root
        )
        self.external_source_changes = ExternalSourceChangeDetector()
        self.ambiguous_receipt = ambiguous_receipt or AmbiguousReceiptEvidenceSource()
        # The default remains the deterministic synthetic tenant used by the
        # recorded judge path.  A real authorised read path is opt-in so a
        # missing token can never silently turn a production-looking demo into
        # a degraded mock.  External writes stay disabled unless the dedicated
        # M20 demo tenant is explicitly selected.
        source_mode = os.environ.get("MISSING20_CASE_CONSOLE_SOURCE", "synthetic").strip().lower()
        self.case_console_source_mode = source_mode
        if agent_platform is not None:
            self.agent_platform = agent_platform
        elif source_mode == "live":
            executor = (
                ERPNextDemoExecutor.from_environment(repository_root)
                if os.environ.get("MISSING20_ENVIRONMENT", "").strip().lower() == "demo"
                else None
            )
            self.agent_platform = AgentPlatform(
                self.erpnext_evidence,
                self.saas_evidence,
                executor=executor,
                state_path=(runtime_directory / "agent-platform-state.json")
                if runtime_directory is not None
                else None,
            )
        elif source_mode == "synthetic":
            case_console_store = (
                runtime_directory / "case-console.sqlite3"
                if runtime_directory is not None
                else None
            )
            self.agent_platform = AmbiguousCasePlatform(store_path=case_console_store)
        else:
            raise ValueError("MISSING20_CASE_CONSOLE_SOURCE must be synthetic or live")
        if agent_advisory is not None:
            self.agent_advisory = agent_advisory
        elif isinstance(self.agent_platform, AmbiguousCasePlatform):
            self.agent_advisory = DashboardAdvisoryGateway(
                self.agent_platform,
                packet_factory=lambda projection: connected_competition_investigation_packet(
                    projection,
                    erp_evidence=self.erpnext_evidence.current(),
                    saas_evidence=self.saas_evidence.current(),
                ),
            )
        else:
            self.agent_advisory = DashboardAdvisoryGateway(self.agent_platform)
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

    def observe_external_change(self, source_id: str, projection: dict[str, object]) -> None:
        """Bridge a semantic provider version into the active incident ledger."""

        change = self.external_source_changes.observe(source_id, projection)
        if change is None:
            return
        _scenario, incident_id = self.registry.active_scenario()
        session = self.registry.get(incident_id)
        session.record_external_source_change(
            source_id=source_id,
            source_sequence=int(change["source_sequence"]),
            change=change,
        )

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
    for key, value in _read_env_file(ROOT / ".env").items():
        os.environ.setdefault(key, value)
    # A clean clone must remain runnable without private provider credentials.
    # Connected-source and Bedrock modes are explicit Makefile targets.
    os.environ.setdefault("MISSING20_CASE_CONSOLE_SOURCE", "synthetic")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--runtime-directory",
        type=Path,
        default=ROOT / ".missing20-runtime",
        help="directory for durable local synthetic ledgers and Case Console state",
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
