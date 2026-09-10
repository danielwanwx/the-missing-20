"""Capture a reconstructed frozen D4 Strands ``Model.stream`` input boundary.

This diagnostic is deliberately offline.  It uses the existing frozen receiving
packet and live-advisory tool assembly, but a local scripted model stops after
the five read tools return.  It does not construct Bedrock, boto3, a credential
session, or an HTTP request.  The retained Q4 candidate is separately injected
only into the existing validation seam; its admission is not a model-quality or
semantic-correctness result.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.diagnostics.serve_frozen_receiving_dialogue import (  # noqa: E402
    FileBackedReadOnlySource,
    FrozenFixtureAgentPlatform,
    frozen_receiving_packet,
)
from the_missing_20.adapters.live_advisory_gateway import (  # noqa: E402
    DashboardAdvisoryGateway,
)
from the_missing_20.adapters.strands_models import (  # noqa: E402
    BedrockNovaProFactory,
    ScriptedStrandsModel,
)
from the_missing_20.agents.live_advisory import (  # noqa: E402
    SOURCE_TOOL_NAMES,
    AdvisoryUnavailable,
    LiveAdvisoryResult,
    _invoke,
)
from the_missing_20.config import Settings  # noqa: E402
from the_missing_20.ports.agent_model import (  # noqa: E402
    AgentBudget,
    AgentBudgetLedger,
    AgentProvider,
    AgentStage,
)

DEFAULT_ARTIFACT = Path("/private/tmp/m20-s2-d4-live-q4.json")
DEFAULT_FIXTURE_ROOT = Path("/private/tmp/m20-s2-d4-screen-v2")
DEFAULT_ERP_SOURCE = DEFAULT_FIXTURE_ROOT / "erp-v1.json"
DEFAULT_SAAS_SOURCE = DEFAULT_FIXTURE_ROOT / "saas.json"
CAPTURE_SCHEMA = "missing20-frozen-receiving-sdk-boundary-capture/v1"
POST_TOOL_ACQUISITION_PHASE = "post_tool_acquisition_model_stream_before_typed_synthesis"


class CaptureError(RuntimeError):
    """The frozen diagnostic cannot make a bounded, truthful capture."""


class BoundaryCaptureStopped(RuntimeError):
    """Expected local stop once all synthetic read results reach ``Model.stream``."""


@dataclass(frozen=True, slots=True)
class Reconstruction:
    """Current-code reconstruction of the input without historical assistant messages."""

    packet: dict[str, Any]
    contextual_question: str
    candidate: dict[str, Any]
    metadata: dict[str, object]
    input_sha256: dict[str, str]


@dataclass(slots=True)
class OfflineFactory:
    """Minimal local factory shape consumed by the existing advisory invocation."""

    model: ScriptedStrandsModel
    ledger: AgentBudgetLedger = field(default_factory=lambda: AgentBudgetLedger(AgentBudget()))
    provider: AgentProvider = AgentProvider.SCRIPTED

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> ScriptedStrandsModel:
        del output_payload, tool_plan
        if stage is not AgentStage.SYNTHESIS:
            raise CaptureError(f"unexpected diagnostic stage: {stage.value}")
        return self.model

    def provenance(self) -> dict[str, Any]:
        return {
            "mode": "offline_frozen_sdk_boundary",
            "provider": AgentProvider.SCRIPTED.value,
            "transport": "strands_model_stream_boundary",
            "provider_request_count": 0,
        }


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CaptureError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(f"diagnostic input is unreadable: {path}") from exc
    return _mapping(decoded, label=str(path))


def _copy_json(value: object) -> Any:
    return json.loads(_canonical_json(value))


def _execution_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or len(revision) != 40:
        raise CaptureError("current git revision is unavailable")
    return revision


def _tool_plan() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "tool": tool_name,
            "arguments": {"query": "synthetic offline SDK-boundary diagnostic read"},
        }
        for tool_name in SOURCE_TOOL_NAMES
    )


def _direct_tool_result_names(messages: object) -> list[str]:
    if not isinstance(messages, list):
        return []
    names_by_id: dict[str, str] = {}
    names: list[str] = []
    for raw_message in messages:
        if not isinstance(raw_message, Mapping):
            continue
        content = raw_message.get("content")
        if not isinstance(content, list):
            continue
        for raw_block in content:
            if not isinstance(raw_block, Mapping):
                continue
            tool_use = raw_block.get("toolUse")
            if isinstance(tool_use, Mapping):
                tool_use_id = tool_use.get("toolUseId")
                name = tool_use.get("name")
                if isinstance(tool_use_id, str) and isinstance(name, str):
                    names_by_id[tool_use_id] = name
            tool_result = raw_block.get("toolResult")
            if isinstance(tool_result, Mapping):
                tool_use_id = tool_result.get("toolUseId")
                name = names_by_id.get(tool_use_id) if isinstance(tool_use_id, str) else None
                if name is not None:
                    names.append(name)
    return names


def _walk_json_values(value: object) -> Generator[Mapping[str, Any], None, None]:
    """Yield embedded mappings from SDK messages, including JSON tool-result text."""

    def visit(candidate: object) -> Generator[Mapping[str, Any], None, None]:
        if isinstance(candidate, Mapping):
            normalized = {str(key): item for key, item in candidate.items()}
            yield normalized
            for item in normalized.values():
                yield from visit(item)
            return
        if isinstance(candidate, list):
            for item in candidate:
                yield from visit(item)
            return
        if isinstance(candidate, str) and candidate[:1] in {"{", "["}:
            try:
                decoded = json.loads(candidate)
            except json.JSONDecodeError:
                return
            yield from visit(decoded)

    yield from visit(value)


def _model_facing_physical_basis(messages: object) -> dict[str, object]:
    for candidate in _walk_json_values(messages):
        quantities = candidate.get("quantities")
        if not isinstance(quantities, Mapping):
            continue
        if candidate.get("physical_observation_basis") != "RECEIPT_CONFIRMED":
            continue
        if "receipt_confirmed_lower_bound" not in quantities:
            continue
        lower_bound = quantities.get("receipt_confirmed_lower_bound")
        if isinstance(lower_bound, bool) or not isinstance(lower_bound, (int, float)):
            raise CaptureError("captured receipt lower bound is malformed")
        return {
            "physical_observation_basis": "RECEIPT_CONFIRMED",
            "independently_observed_quantity": quantities.get("independently_observed_quantity"),
            "receipt_confirmed_lower_bound": float(lower_bound),
            "raw_physically_arrived_present": "physically_arrived" in quantities,
        }
    raise CaptureError("captured SDK messages lack the model-facing receiving basis")


class BoundaryCaptureModel(ScriptedStrandsModel):
    """Drive real read tools locally, then retain only a redacted SDK input summary."""

    def __init__(self, plan: tuple[dict[str, Any], ...]) -> None:
        super().__init__(
            stage=AgentStage.SYNTHESIS,
            output_payload={},
            tool_plan=plan,
            model_id="offline-frozen-sdk-boundary-capture",
        )
        self.stream_summaries: list[dict[str, object]] = []
        self.boundary: dict[str, object] | None = None

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        *,
        tool_choice: Any = None,
        system_prompt_content: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        tool_result_names = _direct_tool_result_names(messages)
        specs = tool_specs if isinstance(tool_specs, list) else []
        self.stream_summaries.append(
            {
                "messages_sha256": _sha256(messages),
                "tool_specs_sha256": _sha256(specs),
                "system_prompt_sha256": _sha256(system_prompt or ""),
                "system_prompt_content_sha256": _sha256(system_prompt_content or []),
                "invocation_state_sha256": _sha256(kwargs.get("invocation_state", {})),
                "tool_result_count": len(tool_result_names),
            }
        )
        if self._tool_index < len(self.tool_plan):
            async for event in super().stream(
                messages,
                tool_specs,
                system_prompt,
                tool_choice=tool_choice,
                system_prompt_content=system_prompt_content,
                **kwargs,
            ):
                yield event
            return

        expected_names = [str(item["tool"]) for item in self.tool_plan]
        if tool_result_names != expected_names:
            raise CaptureError("SDK did not return the complete fixed diagnostic tool sequence")
        self.boundary = {
            "captured_phase": POST_TOOL_ACQUISITION_PHASE,
            "typed_synthesis_input_captured": False,
            "stream_call_count": len(self.stream_summaries),
            "messages_sha256": _sha256(messages),
            "tool_specs_sha256": _sha256(specs),
            "system_prompt_sha256": _sha256(system_prompt or ""),
            "system_prompt_content_sha256": _sha256(system_prompt_content or []),
            "invocation_state_sha256": _sha256(kwargs.get("invocation_state", {})),
            "tool_result_names": tool_result_names,
            "model_facing_physical_basis": _model_facing_physical_basis(messages),
            "stopped_after_tools": True,
            "answer_emitted": False,
        }
        raise BoundaryCaptureStopped("offline capture stopped after the fixed read tools")


def _historical_fields(artifact: Mapping[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    turns = artifact.get("turns")
    if not isinstance(turns, list) or len(turns) != 1:
        raise CaptureError("retained Q4 artifact must contain exactly one stopped D4 turn")
    turn = _mapping(turns[0], label="retained Q4 turn")
    response = _mapping(turn.get("response"), label="retained Q4 response")
    question = turn.get("question")
    if not isinstance(question, str) or not question:
        raise CaptureError("retained Q4 question is unavailable")
    advisory = _mapping(response.get("agent_advisory"), label="retained Q4 agent advisory")
    candidate = _mapping(advisory.get("result"), label="retained Q4 structured result")
    requests = response.get("human_requests")
    if not isinstance(requests, list) or not requests:
        raise CaptureError("retained Q4 artifact has no human request history")
    last_request = _mapping(requests[-1], label="retained Q4 current human request")
    if last_request.get("question") != question:
        raise CaptureError("retained Q4 current request does not match its question")
    return response, question, candidate


def _reconstruct(
    *,
    artifact_path: Path,
    erp_source: Path,
    saas_source: Path,
) -> Reconstruction:
    artifact = _json_object(artifact_path)
    response, current_question, candidate = _historical_fields(artifact)
    human_requests = response.get("human_requests")
    human_intent = response.get("human_intent")
    dialogue_context = response.get("dialogue_context")
    if not isinstance(human_requests, list):  # Guarded by _historical_fields for type checkers.
        raise CaptureError("retained Q4 human request history is unavailable")
    if not isinstance(human_intent, Mapping) or not isinstance(dialogue_context, Mapping):
        raise CaptureError("retained Q4 dialogue state is unavailable")

    input_sha256 = {
        "artifact": _file_sha256(artifact_path),
        "erp_source": _file_sha256(erp_source),
        "saas_source": _file_sha256(saas_source),
    }
    with tempfile.TemporaryDirectory(prefix="m20-frozen-sdk-boundary-") as runtime:
        state_path = Path(runtime) / "agent-platform-state.json"
        erp_reader = FileBackedReadOnlySource(erp_source, kind="erp")
        saas_reader = FileBackedReadOnlySource(saas_source, kind="saas")
        platform = FrozenFixtureAgentPlatform(erp_reader, saas_reader, state_path=state_path)
        projection = platform.current()
        projection.update(
            {
                "human_requests": _copy_json(human_requests),
                "human_intent": _copy_json(human_intent),
                "dialogue_context": _copy_json(dialogue_context),
            }
        )
        packet = dict(frozen_receiving_packet(projection))
        gateway = DashboardAdvisoryGateway(
            platform,
            settings=Settings(agent_provider=AgentProvider.SCRIPTED),
        )
        prior_requests = gateway._prior_human_requests(projection, current_question)
        packed = gateway._pack_contextual_question(
            packet,
            prior_requests=prior_requests,
            current_question=current_question,
            authority_context=gateway._authority_context(projection),
        )
        if packed.get("input_limit") is True:
            raise CaptureError("current bounded dialogue pack rejected the retained Q4 question")
        contextual_question = packed.get("prompt")
        if not isinstance(contextual_question, str) or not contextual_question:
            raise CaptureError("current dialogue pack lacks a contextual question")
        source_observability = {
            "erp_fixture_reads": erp_reader.read_count,
            "saas_fixture_reads": saas_reader.read_count,
            "erp_external_calls": erp_reader.external_calls,
            "saas_external_calls": saas_reader.external_calls,
        }

    metadata: dict[str, object] = {
        "execution_revision": _execution_revision(),
        "strands_agents_version": importlib.metadata.version("strands-agents"),
        "source_mode": "frozen_read_only_fixture",
        "historical_wire_capture": False,
        "historical_intermediate_assistant_reconstructed": False,
        "current_question_from_historical_artifact": True,
        "prior_human_request_count": len(prior_requests),
        "assistant_prose_in_reconstructed_context": False,
        "packed_context_sha256": _sha256(contextual_question),
        "source_observability": source_observability,
    }
    return Reconstruction(
        packet=packet,
        contextual_question=contextual_question,
        candidate=candidate,
        metadata=metadata,
        input_sha256=input_sha256,
    )


def _capture_stream_boundary(reconstruction: Reconstruction) -> dict[str, object]:
    model = BoundaryCaptureModel(_tool_plan())
    factory = OfflineFactory(model=model)
    try:
        asyncio.run(
            _invoke(
                reconstruction.packet,
                factory=cast(BedrockNovaProFactory, factory),
                question=reconstruction.contextual_question,
            )
        )
    except AdvisoryUnavailable:
        if model.boundary is None:
            raise CaptureError(
                "SDK capture stopped before the model saw all read tool results"
            ) from None
    else:
        raise CaptureError("SDK capture unexpectedly produced an advisory result")
    return dict(model.boundary)


def _retained_candidate_admission(reconstruction: Reconstruction) -> dict[str, object]:
    candidate = LiveAdvisoryResult.model_validate(reconstruction.candidate)
    model = ScriptedStrandsModel(
        stage=AgentStage.SYNTHESIS,
        output_payload=candidate.model_dump(mode="json"),
        tool_plan=_tool_plan(),
        model_id="offline-retained-q4-candidate-validation",
    )
    factory = OfflineFactory(model=model)
    try:
        run = asyncio.run(
            _invoke(
                reconstruction.packet,
                factory=cast(BedrockNovaProFactory, factory),
                question=reconstruction.contextual_question,
            )
        )
    except AdvisoryUnavailable as exc:
        raise CaptureError("retained Q4 candidate did not reach existing validation") from exc
    if run.result.model_dump(mode="json") != candidate.model_dump(mode="json"):
        raise CaptureError("existing validation did not retain the injected Q4 candidate exactly")
    return {
        "status": "ADMITTED_BY_EXISTING_VALIDATION",
        "existing_full_validation_seam": True,
        "separate_from_boundary_capture": True,
        "candidate_sha256": _sha256(candidate.model_dump(mode="json")),
        "candidate_disposition": candidate.disposition.value,
        "candidate_evidence_ids": list(candidate.evidence_ids),
        "tool_calls": list(run.tool_calls),
        "validation_retries": run.usage.get("validation_retries"),
        "synthetic_candidate_injection": True,
        "answer_displayed_or_persisted": False,
        "semantic_accuracy_assessed": False,
        "model_quality_pass": False,
        "provider_requests": 0,
    }


def _reserve_output(path: Path) -> int:
    if not path.parent.is_dir():
        raise CaptureError(f"capture output parent does not exist: {path.parent}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(descriptor, 0o600)
    return descriptor


def _write_reserved_output(descriptor: int, record: Mapping[str, object]) -> None:
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def capture_frozen_receiving_sdk_boundary(
    *,
    output_path: Path,
    artifact_path: Path = DEFAULT_ARTIFACT,
    erp_source: Path = DEFAULT_ERP_SOURCE,
    saas_source: Path = DEFAULT_SAAS_SOURCE,
) -> dict[str, object]:
    """Create one exclusive, redacted offline capture artifact.

    The output path is reserved before any fixture read or Strands invocation.  Existing
    output is an error so a caller cannot silently overwrite a prior diagnostic record.
    """

    descriptor = _reserve_output(output_path)
    try:
        reconstruction = _reconstruct(
            artifact_path=artifact_path,
            erp_source=erp_source,
            saas_source=saas_source,
        )
        boundary = _capture_stream_boundary(reconstruction)
        admission = _retained_candidate_admission(reconstruction)
        record: dict[str, object] = {
            "schema_version": CAPTURE_SCHEMA,
            "status": "CAPTURED_OFFLINE",
            "capture_kind": "strands_model_stream_input_boundary",
            "capture_scope": POST_TOOL_ACQUISITION_PHASE,
            "historical_wire_capture": False,
            "historical_intermediate_assistant_reconstructed": False,
            "synthetic_tool_orchestration": True,
            "provider_requests": 0,
            "provider_fallback": False,
            "input_sha256": reconstruction.input_sha256,
            "input_paths": {
                "artifact": str(artifact_path.resolve()),
                "erp_source": str(erp_source.resolve()),
                "saas_source": str(saas_source.resolve()),
            },
            "reconstruction": reconstruction.metadata,
            "stream_boundary": boundary,
            "retained_candidate_admission": admission,
            "limitations": [
                "This is a current-code reconstruction, not retained historical "
                "Bedrock HTTP bytes.",
                "The local fixed tool sequence is synthetic orchestration, not a model decision.",
                "Candidate admission by existing validation is not semantic correctness "
                "or a model pass.",
            ],
        }
        _write_reserved_output(descriptor, record)
    except BaseException:
        # ``_write_reserved_output`` owns and may already have closed this FD.
        with suppress(OSError):
            os.close(descriptor)
        raise
    return record


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--erp-source", type=Path, default=DEFAULT_ERP_SOURCE)
    parser.add_argument("--saas-source", type=Path, default=DEFAULT_SAAS_SOURCE)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        record = capture_frozen_receiving_sdk_boundary(
            output_path=args.output,
            artifact_path=args.artifact,
            erp_source=args.erp_source,
            saas_source=args.saas_source,
        )
    except (CaptureError, OSError, ValueError) as exc:
        print(f"Frozen SDK boundary capture: BLOCKED ({exc})", file=sys.stderr)
        return 2
    revision = _mapping(record["reconstruction"], label="capture reconstruction")[
        "execution_revision"
    ]
    print(f"Frozen SDK boundary capture: COMPLETE ({args.output}; revision {revision})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
