"""Serve the frozen D4 receiving dialogue through the production HTTP ask path.

This harness reads supplied JSON snapshots on every projection.  It never creates
an ERP/SaaS adapter from environment credentials, never exposes a fixture-mutation
route, and blocks every POST except the normal advisory ``/ask`` endpoint.  By
default that endpoint remains provider-unconfigured; ``--execute-model`` is the
explicit opt-in for the existing Nova Pro gateway settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.decision_workspace_server import (  # noqa: E402
    DecisionWorkspaceHandler,
    DecisionWorkspaceServer,
)
from the_missing_20.adapters.agent_platform import AgentPlatform  # noqa: E402
from the_missing_20.adapters.erpnext_source import ERPNextEvidenceSource  # noqa: E402
from the_missing_20.adapters.live_advisory_gateway import (  # noqa: E402
    AdvisoryRunner,
    DashboardAdvisoryGateway,
)
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource  # noqa: E402
from the_missing_20.agents.live_advisory import live_recovery_packet  # noqa: E402
from the_missing_20.config import Settings  # noqa: E402
from the_missing_20.ports.agent_model import AgentProvider  # noqa: E402

DEFAULT_ERP_SOURCE = Path("/private/tmp/m20-s2-r3-erp-readonly-source.json")
DEFAULT_SAAS_SOURCE = Path("/private/tmp/m20-s2-r3-saas-readonly-source.json")
RUNTIME_MARKER = "frozen-receiving-dialogue-runtime.json"
RUNTIME_SCHEMA = "missing20-frozen-receiving-dialogue-runtime/v1"

_WRITER_ENVIRONMENT = (
    "ERPNEXT_BASE_URL",
    "ERPNEXT_API_KEY",
    "ERPNEXT_API_SECRET",
)
_RECEIVING_ENVIRONMENT = (
    "MISSING20_PHOTO_PURCHASE_ORDER",
    "MISSING20_RECEIVING_MANIFEST",
    "MISSING20_PHOTO_AUTO_PREPARE",
    "MISSING20_PHOTO_DRAFTS_ENABLED",
    "MISSING20_RECEIVING_HANDOFF_ENABLED",
)


class FrozenFixtureError(ValueError):
    """A supplied source is not the declared read-only fixture contract."""


@dataclass(frozen=True, slots=True)
class FixtureSnapshot:
    """Non-secret metadata for one reread of a frozen fixture file."""

    path: str
    sha256: str
    schema_version: str
    source_status: str
    source_sequence: int | None


class FileBackedReadOnlySource:
    """Reread one declared JSON snapshot without any external adapter or cache."""

    def __init__(
        self,
        path: Path,
        *,
        kind: Literal["erp", "saas"],
    ) -> None:
        try:
            self.path = path.expanduser().resolve(strict=True)
        except OSError as exc:
            raise FrozenFixtureError(f"{kind} fixture is not readable: {path}") from exc
        if not self.path.is_file():
            raise FrozenFixtureError(f"{kind} fixture must be a regular file: {self.path}")
        self.kind = kind
        self._lock = threading.Lock()
        self._read_count = 0
        self._last_snapshot: FixtureSnapshot | None = None
        # Validate the declared source before the server constructor can select
        # any fallback adapter. This is a local file read, never an ERP/SaaS call.
        self._read_and_validate()

    @property
    def read_count(self) -> int:
        with self._lock:
            return self._read_count

    @property
    def last_snapshot(self) -> FixtureSnapshot:
        with self._lock:
            if self._last_snapshot is None:
                raise FrozenFixtureError("fixture has not been read")
            return self._last_snapshot

    @property
    def external_calls(self) -> int:
        """Make the no-ERP/SaaS-network boundary observable to harness tests."""

        return 0

    def current(self) -> dict[str, object]:
        payload, snapshot = self._read_and_validate()
        with self._lock:
            self._read_count += 1
            self._last_snapshot = snapshot
        return payload

    def _read_and_validate(self) -> tuple[dict[str, object], FixtureSnapshot]:
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise FrozenFixtureError(f"{self.kind} fixture could not be reread") from exc
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FrozenFixtureError(f"{self.kind} fixture is not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise FrozenFixtureError(f"{self.kind} fixture must contain an object")
        payload = dict(decoded)
        self._validate(payload)
        sequence = payload.get("sequence")
        return payload, FixtureSnapshot(
            path=str(self.path),
            sha256=hashlib.sha256(raw).hexdigest(),
            schema_version=str(payload["schema_version"]),
            source_status=str(payload["status"]),
            source_sequence=sequence
            if isinstance(sequence, int) and not isinstance(sequence, bool)
            else None,
        )

    def _validate(self, payload: Mapping[str, object]) -> None:
        expected_schema = (
            "missing20-erpnext-evidence/v1" if self.kind == "erp" else "missing20-saas-evidence/v1"
        )
        if payload.get("schema_version") != expected_schema:
            raise FrozenFixtureError(
                f"{self.kind} fixture schema must be {expected_schema}, not "
                f"{payload.get('schema_version')!r}"
            )
        if payload.get("read_only") is not True:
            raise FrozenFixtureError(f"{self.kind} fixture must explicitly declare read_only=true")
        status = payload.get("status")
        if not isinstance(status, str) or status not in {"CONNECTED", "UNAVAILABLE", "DEGRADED"}:
            raise FrozenFixtureError(f"{self.kind} fixture has an invalid declared source status")
        if self.kind == "erp":
            self._validate_erp(payload)
        else:
            self._validate_saas(payload)

    @staticmethod
    def _validate_erp(payload: Mapping[str, object]) -> None:
        for name in ("source_id", "case_id", "provider"):
            if not isinstance(payload.get(name), str) or not str(payload[name]).strip():
                raise FrozenFixtureError(f"erp fixture requires a non-empty {name}")
        documents = payload.get("documents")
        if not isinstance(documents, list) or not documents:
            raise FrozenFixtureError("erp fixture requires its scoped documents")
        if not all(
            isinstance(row, Mapping)
            and isinstance(row.get("kind"), str)
            and isinstance(row.get("name"), str)
            and str(row["name"]).strip()
            for row in documents
        ):
            raise FrozenFixtureError("erp fixture has an invalid scoped document")
        if not any(
            row.get("kind") == "purchase_order" for row in documents if isinstance(row, Mapping)
        ):
            raise FrozenFixtureError("erp fixture requires a purchase-order document")
        if not isinstance(payload.get("ledger_evidence"), Mapping):
            raise FrozenFixtureError("erp fixture requires declared ledger evidence")
        lifecycle = payload.get("document_lifecycle")
        if not isinstance(lifecycle, Mapping):
            raise FrozenFixtureError("erp fixture requires document lifecycle metadata")
        if lifecycle.get("purchase_invoice") != "AWAITING_INVOICE":
            raise FrozenFixtureError("frozen receiving fixture must remain before supplier invoice")
        if payload.get("purchase_scope") != "ALL_LINKED_DOCUMENTS":
            raise FrozenFixtureError("erp fixture must retain ALL_LINKED_DOCUMENTS scope")
        if not isinstance(payload.get("activity"), list):
            raise FrozenFixtureError("erp fixture requires activity metadata")

    @staticmethod
    def _validate_saas(payload: Mapping[str, object]) -> None:
        if (
            not isinstance(payload.get("correlation_id"), str)
            or not str(payload["correlation_id"]).strip()
        ):
            raise FrozenFixtureError("saas fixture requires a non-empty correlation_id")
        if not isinstance(payload.get("sources"), list) or not isinstance(
            payload.get("activity"), list
        ):
            raise FrozenFixtureError("saas fixture requires source and activity lists")


class ReadOnlyReceivingScope:
    """Supply only empty receiving configuration; it has no draft or write surface."""

    def receiving_work(self, case_id: str, purchase_order: str) -> dict[str, object]:
        return {
            "case_id": case_id,
            "purchase_order": purchase_order,
            "status": "CONFIGURED",
            "arrivals": [],
            "provenance": "frozen-read-only-harness",
        }


class FrozenFixtureAgentPlatform(AgentPlatform):
    """The production platform with fixture provenance exposed in its runtime truth."""

    def __init__(
        self,
        erpnext: FileBackedReadOnlySource,
        saas: FileBackedReadOnlySource,
        *,
        state_path: Path,
    ) -> None:
        super().__init__(
            erpnext,
            saas,
            executor=None,
            state_path=state_path,
            receiving=ReadOnlyReceivingScope(),
        )
        self._frozen_erp_reader = erpnext
        self._frozen_saas_reader = saas

    def runtime_truth(self) -> dict[str, object]:
        return {
            **super().runtime_truth(),
            "source_mode": "frozen_read_only_fixture",
            "source_provenance": "file_backed_declared_fixture",
            "external_provider_reads": "disabled",
            "external_provider_writes": "disabled",
            "fixture_schemas": {
                "erp": self._frozen_erp_reader.last_snapshot.schema_version,
                "saas": self._frozen_saas_reader.last_snapshot.schema_version,
            },
        }


def frozen_receiving_packet(projection: Mapping[str, object]) -> Mapping[str, Any]:
    """Disclose frozen/simulated provenance to the normal receiving packet boundary."""

    packet = dict(live_recovery_packet(projection))
    tool_payload = packet.get("tool_payload")
    sources = tool_payload.get("sources") if isinstance(tool_payload, Mapping) else None
    if not isinstance(sources, Mapping):
        raise FrozenFixtureError("production receiving packet lacks source controls")
    control_context = sources.get("read_control_context")
    if not isinstance(control_context, Mapping):
        raise FrozenFixtureError("production receiving packet lacks control context")
    packet["tool_payload"] = {
        "sources": {
            **sources,
            "read_control_context": {
                **control_context,
                "fixture_provenance": (
                    "Frozen file-backed read-only fixture. This is simulated source evidence, "
                    "not a fresh ERP/SaaS provider call and never write authority."
                ),
            },
        }
    }
    packet["source"] = "frozen_read_only_fixture"
    return packet


class FrozenReceivingDialogueHandler(DecisionWorkspaceHandler):
    """Keep the real ask route while excluding all diagnostic and write endpoints."""

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/v1/agent-platform/ask":
            self._send_api_error(
                HTTPStatus.FORBIDDEN,
                "frozen_harness_read_only",
                "This frozen harness accepts only the read-only advisory ask endpoint.",
            )
            return
        super().do_POST()


class FrozenReceivingDialogueServer(DecisionWorkspaceServer):
    """A DecisionWorkspaceServer with the frozen harness handler and observability."""

    def __init__(
        self,
        address: tuple[str, int],
        *,
        configuration_root: Path,
        runtime_directory: Path,
        erp_reader: FileBackedReadOnlySource,
        saas_reader: FileBackedReadOnlySource,
        platform: AgentPlatform,
        advisory: DashboardAdvisoryGateway,
    ) -> None:
        super().__init__(
            address,
            configuration_root,
            runtime_directory=runtime_directory,
            erpnext_evidence=cast(ERPNextEvidenceSource, erp_reader),
            saas_evidence=cast(SaaSEvidenceSource, saas_reader),
            agent_platform=platform,
            agent_advisory=advisory,
            live_sources_autostart=False,
        )
        self.RequestHandlerClass = FrozenReceivingDialogueHandler
        self.frozen_erp_reader = erp_reader
        self.frozen_saas_reader = saas_reader
        self.frozen_runtime_directory = runtime_directory

    def fixture_metadata(self) -> dict[str, object]:
        return {
            "mode": "frozen_read_only_fixture",
            "erp": asdict(self.frozen_erp_reader.last_snapshot),
            "saas": asdict(self.frozen_saas_reader.last_snapshot),
            "external_calls": {
                "erp": self.frozen_erp_reader.external_calls,
                "saas": self.frozen_saas_reader.external_calls,
            },
        }


def _configured_environment_is_safe() -> None:
    configured_writer = [key for key in _WRITER_ENVIRONMENT if os.environ.get(key)]
    if configured_writer:
        raise FrozenFixtureError(
            "frozen harness refuses ambient ERP writer credentials: " + ", ".join(configured_writer)
        )
    configured_receiving = [
        key
        for key in _RECEIVING_ENVIRONMENT
        if os.environ.get(key, "").strip().lower() not in {"", "0", "false", "no", "off"}
    ]
    if configured_receiving:
        raise FrozenFixtureError(
            "frozen harness refuses ambient photo/draft/handoff configuration: "
            + ", ".join(configured_receiving)
        )


def _prepare_runtime(runtime_directory: Path, *, resume: bool) -> tuple[Path, Path]:
    runtime = runtime_directory.expanduser().resolve()
    marker = runtime / RUNTIME_MARKER
    if resume:
        if not marker.is_file():
            raise FrozenFixtureError(
                "--resume requires a runtime created by this frozen harness; "
                "no prior runtime was copied"
            )
        try:
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FrozenFixtureError("frozen harness runtime marker is unreadable") from exc
        if (
            not isinstance(marker_payload, Mapping)
            or marker_payload.get("schema_version") != RUNTIME_SCHEMA
        ):
            raise FrozenFixtureError("runtime marker is not a frozen receiving dialogue runtime")
        configuration_root = runtime / "isolated-config"
        if not configuration_root.is_dir() or any(configuration_root.iterdir()):
            raise FrozenFixtureError(
                "isolated configuration root must remain empty; dotenv configuration is not allowed"
            )
        return runtime, configuration_root

    if runtime.exists() and any(runtime.iterdir()):
        raise FrozenFixtureError(
            "runtime directory must be new and empty; use --resume only for this harness runtime"
        )
    runtime.mkdir(parents=True, exist_ok=True)
    configuration_root = runtime / "isolated-config"
    configuration_root.mkdir()
    marker.write_text(
        json.dumps({"schema_version": RUNTIME_SCHEMA, "source": "frozen-read-only"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return runtime, configuration_root


def _settings(*, execute_model: bool) -> Settings:
    """Keep the normal Nova Pro settings, changing only the explicit provider opt-in."""

    configured = Settings.from_env()
    return replace(
        configured,
        agent_provider=AgentProvider.BEDROCK if execute_model else AgentProvider.SCRIPTED,
    )


def build_frozen_receiving_dialogue_server(
    *,
    host: str,
    port: int,
    runtime_directory: Path,
    erp_source: Path = DEFAULT_ERP_SOURCE,
    saas_source: Path = DEFAULT_SAAS_SOURCE,
    resume: bool = False,
    execute_model: bool = False,
    runner: AdvisoryRunner | None = None,
) -> FrozenReceivingDialogueServer:
    """Construct the production HTTP/gateway/platform stack around frozen local files.

    ``runner`` exists only for offline tests.  The command-line path never installs a
    fake runner, so an operator cannot mistake a fixture response for a provider call.
    """

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise FrozenFixtureError("frozen receiving dialogue must bind to loopback")
    _configured_environment_is_safe()
    runtime, configuration_root = _prepare_runtime(runtime_directory, resume=resume)
    erp_reader = FileBackedReadOnlySource(erp_source, kind="erp")
    saas_reader = FileBackedReadOnlySource(saas_source, kind="saas")
    erp_case = erp_reader.current().get("case_id")
    saas_case = saas_reader.current().get("correlation_id")
    if erp_case != saas_case:
        raise FrozenFixtureError(
            "ERP case_id and SaaS correlation_id must describe the same fixture"
        )

    platform = FrozenFixtureAgentPlatform(
        erp_reader,
        saas_reader,
        state_path=runtime / "agent-platform-state.json",
    )
    # A supplied runner is the non-CLI test seam. It needs the same gateway
    # provider gate as a real invocation, while the command-line path can only
    # reach that gate through explicit --execute-model.
    kwargs: dict[str, Any] = {
        "settings": _settings(execute_model=execute_model or runner is not None)
    }
    if runner is not None:
        kwargs["runner"] = runner
    advisory = DashboardAdvisoryGateway(platform, packet_factory=frozen_receiving_packet, **kwargs)
    return FrozenReceivingDialogueServer(
        (host, port),
        configuration_root=configuration_root,
        runtime_directory=runtime,
        erp_reader=erp_reader,
        saas_reader=saas_reader,
        platform=platform,
        advisory=advisory,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--erp-source", type=Path, default=DEFAULT_ERP_SOURCE)
    parser.add_argument("--saas-source", type=Path, default=DEFAULT_SAAS_SOURCE)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse only the persisted runtime created by an earlier harness process",
    )
    parser.add_argument(
        "--execute-model",
        action="store_true",
        help="explicitly enable the existing Nova Pro gateway provider for ask requests",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        server = build_frozen_receiving_dialogue_server(
            host=args.host,
            port=args.port,
            runtime_directory=args.runtime_directory,
            erp_source=args.erp_source,
            saas_source=args.saas_source,
            resume=args.resume,
            execute_model=args.execute_model,
        )
    except (FrozenFixtureError, OSError, ValueError) as exc:
        print(f"Frozen receiving dialogue server: BLOCKED ({exc})", file=sys.stderr)
        return 2
    model_mode = (
        "Nova Pro enabled by explicit --execute-model" if args.execute_model else "disabled"
    )
    print(
        "Frozen receiving dialogue server: "
        f"http://{args.host}:{server.server_port}/ (model {model_mode}; fixture source only)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
