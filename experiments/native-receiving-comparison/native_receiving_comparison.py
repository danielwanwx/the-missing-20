"""Offline-first native Strands receiving comparison (N1 natural text; N2 answer/citations)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import AsyncGenerator, Mapping
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import Model
from strands.tools.structured_output import convert_pydantic_to_tool_spec
from strands.types.agent import Limits

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.diagnostics.capture_frozen_receiving_sdk_boundary import (  # noqa: E402
    DEFAULT_ARTIFACT,
    DEFAULT_ERP_SOURCE,
    DEFAULT_SAAS_SOURCE,
    Reconstruction,
    _reconstruct,
)
from the_missing_20.adapters.strands_models import (  # noqa: E402
    BedrockNovaProConfig,
    BedrockNovaProFactory,
    BudgetedModel,
)
from the_missing_20.agents.live_advisory import (  # noqa: E402
    ADVISORY_OUTPUT_TOKENS,
    ADVISORY_WALL_TIMEOUT_SECONDS,
    RECEIVING_LOOP_OUTPUT_TOKENS,
    RECEIVING_LOOP_TOTAL_TOKENS,
    SOURCE_TOOL_NAMES,
    model_source_payloads,
)
from the_missing_20.config import Settings  # noqa: E402
from the_missing_20.ports.agent_model import (  # noqa: E402
    AgentBudget,
    AgentBudgetLedger,
    AgentStage,
)

SCHEMA_VERSION = "missing20-native-receiving-comparison/v1"
PROCESS_BOUND_SECONDS = 120
Variant = Literal["n1", "n2"]
MODEL_ID = "us.amazon.nova-pro-v1:0"
AWS_REGION = "us-west-2"
AWS_PROFILE = "missing20-sandbox"
GENERIC_PROMPT = (
    "You are a read-only receiving evidence assistant. Answer the newest human question "
    "using only returned source evidence. Use prior human context included in the question "
    "only to resolve references. Distinguish observations from inferences, cite available "
    "record identifiers, and state when evidence is unavailable. Retrieve each available "
    "source before your final answer; treat unavailable evidence as unavailable. "
    "Do not write, approve, post, release, or execute anything."
)
TOOL_DESCRIPTION = (
    "Return the complete qualified, read-only source JSON for the current frozen case. "
    "The query is a retrieval hint and never changes the source."
)


class ComparisonError(RuntimeError):
    """The fixed first screen could not be assembled or executed."""


class ProcessDeadlineExceeded(ComparisonError):
    """The CLI's own 120-second process envelope elapsed."""


class NarrowAnswer(BaseModel):
    """N2 structure only; it deliberately contains no semantic validators."""

    answer: str = Field(min_length=1, max_length=1_600)
    citations: list[str] = Field(min_length=1, max_length=8)


def _json(value: object) -> str:
    def encode_unknown(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json")
        return str(item)

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=encode_unknown,
    )


def _copy(value: object) -> Any:
    return json.loads(_json(value))


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    revision = result.stdout.strip()
    if result.returncode or len(revision) != 40:
        raise ComparisonError("current git revision is unavailable")
    return revision


def _budget() -> AgentBudget:
    """Existing D4 per-candidate ledger caps; the pair therefore caps at USD0.32."""

    return AgentBudget(
        max_requests=16,
        max_input_tokens=250_000,
        max_output_tokens=12_000,
        max_output_tokens_per_request=ADVISORY_OUTPUT_TOKENS,
        prior_cost_usd=Decimal("0"),
        incremental_cost_cap_usd=Decimal("0.16"),
        cumulative_cost_cap_usd=Decimal("0.16"),
        per_call_timeout_seconds=ADVISORY_WALL_TIMEOUT_SECONDS,
        whole_run_timeout_seconds=PROCESS_BOUND_SECONDS,
    )


def _limits() -> Limits:
    return Limits(
        turns=16,
        output_tokens=RECEIVING_LOOP_OUTPUT_TOKENS,
        total_tokens=RECEIVING_LOOP_TOTAL_TOKENS,
    )


def _model_contract() -> dict[str, Any]:
    """Exact factory configuration, constructed without a session or provider call."""

    config = BedrockNovaProConfig(
        model_id=MODEL_ID,
        region=AWS_REGION,
        aws_profile=AWS_PROFILE,
        max_tokens=ADVISORY_OUTPUT_TOKENS,
        temperature=0,
        streaming=False,
        budget=_budget(),
    )
    return {
        "provider": "bedrock",
        "model_id": config.model_id,
        "region": config.region,
        "aws_profile": config.aws_profile,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "streaming": config.streaming,
    }


def _spec_names(specs: object) -> set[str]:
    return (
        {
            str(spec["name"])
            for spec in specs
            if isinstance(spec, Mapping) and isinstance(spec.get("name"), str)
        }
        if isinstance(specs, list)
        else set()
    )


class CapturingModel(Model):
    """Retain every SDK provider turn before returning it to Strands."""

    def __init__(self, delegate: Model) -> None:
        self.delegate = delegate
        self.attempts: list[dict[str, Any]] = []

    @property
    def stateful(self) -> bool:
        return bool(getattr(self.delegate, "stateful", False))

    def get_config(self) -> Any:
        return self.delegate.get_config()

    def update_config(self, **model_config: Any) -> None:
        self.delegate.update_config(**model_config)

    async def count_tokens(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        system_prompt_content: Any = None,
    ) -> int:
        return int(
            await self.delegate.count_tokens(
                messages,
                tool_specs=tool_specs,
                system_prompt=system_prompt,
                system_prompt_content=system_prompt_content,
            )
        )

    async def structured_output(
        self,
        output_model: type[BaseModel],
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for event in self.delegate.structured_output(
            output_model, prompt, system_prompt=system_prompt, **kwargs
        ):
            yield event

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        *,
        tool_choice: Any = None,
        system_prompt_content: Any = None,
        invocation_state: dict[str, Any] | None = None,
        model_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        attempt: dict[str, Any] = {
            "request": {
                "messages": _copy(messages),
                "tool_specs": _copy(tool_specs or []),
                "system_prompt": system_prompt or "",
                "system_prompt_content": _copy(system_prompt_content or []),
                "tool_choice": _copy(tool_choice or {}),
                "invocation_state": _copy(invocation_state or {}),
                "model_state": _copy(model_state or {}),
                "kwargs": _copy(kwargs),
            },
            "raw_model_events": [],
            "usage": [],
        }
        self.attempts.append(attempt)
        try:
            async for event in self.delegate.stream(
                messages,
                tool_specs,
                system_prompt,
                tool_choice=tool_choice,
                system_prompt_content=system_prompt_content,
                invocation_state=invocation_state,
                model_state=model_state,
                **kwargs,
            ):
                captured = _copy(event)
                attempt["raw_model_events"].append(captured)
                metadata = captured.get("metadata") if isinstance(captured, Mapping) else None
                if isinstance(metadata, Mapping) and isinstance(metadata.get("usage"), Mapping):
                    attempt["usage"].append(_copy(metadata["usage"]))
                yield event
        except Exception as exc:
            attempt["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise


def _source_tools(payloads: Mapping[str, Any], reads: list[dict[str, Any]]) -> list[Any]:
    missing = [name for name in SOURCE_TOOL_NAMES if name not in payloads]
    if missing:
        raise ComparisonError(f"qualified source payloads are incomplete: {', '.join(missing)}")

    def make_tool(name: str, payload: Any) -> Any:
        def read_source(query: str = "") -> Any:
            reads.append({"tool": name, "query": query, "qualified_source": _copy(payload)})
            return _copy(payload)

        read_source.__name__ = name
        return tool(read_source, name=name, description=TOOL_DESCRIPTION)

    return [make_tool(name, _copy(payloads[name])) for name in SOURCE_TOOL_NAMES]


def _frozen_input(reconstruction: Reconstruction, payloads: Mapping[str, Any]) -> dict[str, Any]:
    """Private, model-facing bytes rebuilt from current sources without old assistant prose."""

    return {
        "contextual_question": reconstruction.contextual_question,
        "qualified_source_payloads": _copy(dict(payloads)),
        "reconstruction_input_sha256": _copy(reconstruction.input_sha256),
        "reconstruction_metadata": _copy(reconstruction.metadata),
        "retained_candidate_fixture_excluded": True,
    }


def _manifest(frozen_input: Mapping[str, Any], tools: list[Any]) -> dict[str, Any]:
    budget = _budget()
    question = frozen_input.get("contextual_question")
    payloads = frozen_input.get("qualified_source_payloads")
    input_hashes = frozen_input.get("reconstruction_input_sha256")
    if not isinstance(question, str) or not isinstance(payloads, Mapping):
        raise ComparisonError("frozen input lacks its question or qualified source payloads")
    if not isinstance(input_hashes, Mapping):
        raise ComparisonError("frozen input lacks reconstruction source hashes")
    tool_specs = [_copy(item.tool_spec) for item in tools]
    n2_tool_spec = _copy(convert_pydantic_to_tool_spec(NarrowAnswer))
    return {
        "experiment_schema": SCHEMA_VERSION,
        "execution_revision": _revision(),
        "experiment_script_sha256": _file_sha(Path(__file__)),
        "strands_agents_version": importlib.metadata.version("strands-agents"),
        "model_contract": _model_contract(),
        "shared_prompt_sha256": _sha(GENERIC_PROMPT),
        "source_tool_specs": tool_specs,
        "source_tool_specs_sha256": _sha(tool_specs),
        "qualified_source_payloads_sha256": _sha(payloads),
        "contextual_question_sha256": _sha(question),
        "frozen_input_sha256": _sha(frozen_input),
        "reconstruction_input_sha256": _copy(input_hashes),
        "retained_candidate_fixture_excluded": True,
        "candidate_contracts": {
            "n1": {"output_mode": "native_natural_language", "structured_output_tool": None},
            "n2": {
                "output_mode": "native_structured_output_tool",
                "structured_output_tool": n2_tool_spec,
                "structured_output_tool_sha256": _sha(n2_tool_spec),
            },
        },
        "native_retry_strategy": None,
        "native_forced_format_fallback_max": 1,
        "limits": dict(_limits()),
        "budget": {
            "max_requests": budget.max_requests,
            "max_input_tokens": budget.max_input_tokens,
            "max_output_tokens": budget.max_output_tokens,
            "max_output_tokens_per_request": budget.max_output_tokens_per_request,
            "incremental_cost_cap_usd": str(budget.incremental_cost_cap_usd),
            "cumulative_cost_cap_usd": str(budget.cumulative_cost_cap_usd),
            "per_call_timeout_seconds": budget.per_call_timeout_seconds,
            "whole_run_timeout_seconds": budget.whole_run_timeout_seconds,
        },
    }


def _load_frozen_input(path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        raise ComparisonError("--execute-model requires an exact prior --manifest")
    try:
        supplied = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"fixed manifest is unreadable: {path}") from exc
    if not isinstance(supplied, Mapping) or supplied.get("status") != "OFFLINE_INPUT_FROZEN":
        raise ComparisonError("--manifest must be a prior OFFLINE_INPUT_FROZEN record")
    frozen_input = supplied.get("frozen_input")
    manifest = supplied.get("freeze_manifest")
    if not isinstance(frozen_input, Mapping) or not isinstance(manifest, Mapping):
        raise ComparisonError("prior frozen record lacks input or manifest")
    return _copy(frozen_input), _copy(manifest)


def _verify_fixture_correspondence(
    frozen_input: Mapping[str, Any], *, artifact_path: Path, erp_source: Path, saas_source: Path
) -> None:
    """Refuse a reviewed bundle when its original frozen fixture files no longer match."""

    expected = frozen_input.get("reconstruction_input_sha256")
    if not isinstance(expected, Mapping):
        raise ComparisonError("frozen input lacks source correspondence hashes")
    actual = {
        "artifact": _file_sha(artifact_path),
        "erp_source": _file_sha(erp_source),
        "saas_source": _file_sha(saas_source),
    }
    if _json(expected) != _json(actual):
        raise ComparisonError("frozen fixture hashes do not match the reviewed input bundle")


def _reserve(path: Path) -> int:
    if not path.parent.is_dir():
        raise ComparisonError(f"comparison output parent does not exist: {path.parent}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(descriptor, 0o600)
    return descriptor


def _write(descriptor: int, record: Mapping[str, Any]) -> None:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _schema_only_turns(attempts: list[dict[str, Any]]) -> int:
    return sum(
        1
        for attempt in attempts
        if len(_spec_names(attempt["request"]["tool_specs"])) == 1
        and _spec_names(attempt["request"]["tool_specs"]).isdisjoint(SOURCE_TOOL_NAMES)
    )


def _forced_fallbacks(attempts: list[dict[str, Any]]) -> int:
    """The forced fallback has the native prompt; later schema-only turns may be retries."""

    count = 0
    for attempt in attempts:
        messages = attempt["request"]["messages"]
        last = messages[-1] if isinstance(messages, list) and messages else None
        content = last.get("content") if isinstance(last, Mapping) else None
        text = (
            content[0].get("text")
            if isinstance(content, list) and content and isinstance(content[0], Mapping)
            else None
        )
        count += text == "You must format the previous response as structured output."
    return count


def _output(events: list[dict[str, Any]]) -> dict[str, Any]:
    text = "".join(event["data"] for event in events if isinstance(event.get("data"), str))
    structured = next(
        (event["structured_output"] for event in reversed(events) if "structured_output" in event),
        None,
    )
    return {
        "natural_text": text or None,
        "structured_output": _copy(structured) if structured is not None else None,
    }


async def _collect(
    variant: Variant,
    model: CapturingModel,
    tools: list[Any],
    question: str,
    events: list[dict[str, Any]],
) -> None:
    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=GENERIC_PROMPT,
        callback_handler=None,
        retry_strategy=None,
    )
    kwargs: dict[str, Any] = {"limits": _limits()}
    if variant == "n2":
        kwargs["structured_output_model"] = NarrowAnswer
    async for event in agent.stream_async(question, **kwargs):
        events.append(_copy(event))


def _run_stream(
    variant: Variant,
    model: CapturingModel,
    tools: list[Any],
    question: str,
    events: list[dict[str, Any]],
) -> None:
    async def bounded() -> None:
        await asyncio.wait_for(
            _collect(variant, model, tools, question, events), timeout=ADVISORY_WALL_TIMEOUT_SECONDS
        )

    asyncio.run(bounded())


def _live_model(ledger: AgentBudgetLedger) -> Model:
    settings = Settings.from_env()
    if settings.aws_region != AWS_REGION or settings.aws_profile != AWS_PROFILE:
        raise ComparisonError(
            "--execute-model requires MISSING20_AWS_REGION=us-west-2 and "
            "MISSING20_AWS_PROFILE=missing20-sandbox"
        )
    factory = BedrockNovaProFactory(
        BedrockNovaProConfig(
            model_id=MODEL_ID,
            region=AWS_REGION,
            aws_profile=AWS_PROFILE,
            max_tokens=ADVISORY_OUTPUT_TOKENS,
            temperature=0,
            budget=ledger.budget,
        ),
        ledger=ledger,
    )
    return cast(Model, factory.create(stage=AgentStage.SYNTHESIS, output_payload={}))


def run_candidate(
    *,
    variant: Variant,
    output_path: Path,
    artifact_path: Path = DEFAULT_ARTIFACT,
    erp_source: Path = DEFAULT_ERP_SOURCE,
    saas_source: Path = DEFAULT_SAAS_SOURCE,
    execute_model: bool = False,
    manifest_path: Path | None = None,
    model: Model | None = None,
) -> dict[str, Any]:
    """Write one O_EXCL 0600 structural record; never return semantic acceptance.

    The public CLI leaves ``model`` unset, so its default mode freezes exactly one
    shared source/question bundle without constructing a provider. Tests inject a local
    ``Model`` to exercise the native loop; ``--execute-model`` consumes that bundle.
    """

    if variant not in {"n1", "n2"}:
        raise ComparisonError("variant must be n1 or n2")
    descriptor = _reserve(output_path)  # Must precede every fixture input read.
    started = time.monotonic()
    ledger = AgentBudgetLedger(_budget())
    reads: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    frozen_input: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    sdk_invocation_count = 0
    try:
        if execute_model or manifest_path is not None:
            frozen_input, prior_manifest = _load_frozen_input(manifest_path)
            payloads = frozen_input["qualified_source_payloads"]
        else:
            reconstruction = _reconstruct(
                artifact_path=artifact_path, erp_source=erp_source, saas_source=saas_source
            )
            payloads = model_source_payloads(reconstruction.packet)
            frozen_input = _frozen_input(reconstruction, payloads)
            prior_manifest = None
        if not isinstance(payloads, Mapping):
            raise ComparisonError("qualified source payloads must be an object")
        missing_payloads = [name for name in SOURCE_TOOL_NAMES if name not in payloads]
        if missing_payloads:
            record: dict[str, Any] = {
                "status": "STRUCTURAL_FAIL",
                "structural_reason": "qualified_source_payloads_incomplete",
                "missing_source_payloads": missing_payloads,
                "provider_attempts": [],
                "tool_reads": [],
                "frozen_input": frozen_input,
            }
        else:
            tools = _source_tools(payloads, reads)
            manifest = _manifest(frozen_input, tools)
            if prior_manifest is not None and _json(prior_manifest) != _json(manifest):
                raise ComparisonError(
                    "fixed manifest does not match current comparison code/configuration"
                )
            if execute_model:
                _verify_fixture_correspondence(
                    frozen_input,
                    artifact_path=artifact_path,
                    erp_source=erp_source,
                    saas_source=saas_source,
                )
            if model is not None and execute_model:
                raise ComparisonError("injected model cannot be combined with --execute-model")
            if not execute_model and model is None:
                record = {
                    "status": "OFFLINE_INPUT_FROZEN",
                    "structural_reason": None,
                    "provider_attempts": [],
                    "tool_reads": [],
                    "frozen_input": frozen_input,
                    "freeze_manifest": manifest,
                }
            else:
                delegate = model or _live_model(ledger)
                bounded = (
                    delegate
                    if isinstance(delegate, BudgetedModel)
                    else BudgetedModel(delegate, ledger)
                )
                capturing = CapturingModel(cast(Model, bounded))
                attempts = capturing.attempts
                sdk_invocation_count = 1
                _run_stream(
                    variant,
                    capturing,
                    tools,
                    cast(str, frozen_input["contextual_question"]),
                    events,
                )
                missing_reads = [
                    name
                    for name in SOURCE_TOOL_NAMES
                    if name not in {item["tool"] for item in reads}
                ]
                record = {
                    "status": "STRUCTURAL_COMPLETE" if not missing_reads else "STRUCTURAL_FAIL",
                    "structural_reason": None
                    if not missing_reads
                    else "required_source_tools_not_read",
                    "missing_source_reads": missing_reads,
                    "provider_attempts": attempts,
                    "agent_events": events,
                    "tool_reads": reads,
                    "native_forced_format_fallback_count": _forced_fallbacks(attempts),
                    "native_schema_only_turn_count": _schema_only_turns(attempts),
                    "request_turns_containing_schema_error_history": sum(
                        "Validation failed for NarrowAnswer" in _json(attempt)
                        for attempt in attempts
                    ),
                    "output": _output(events),
                    "frozen_input": frozen_input,
                    "freeze_manifest": manifest,
                }
    except Exception as exc:
        record = {
            "status": "EXECUTION_FAILED",
            "provider_attempts": attempts,
            "agent_events": events,
            "tool_reads": reads,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        if frozen_input is not None:
            record["frozen_input"] = frozen_input
        if manifest is not None:
            record["freeze_manifest"] = manifest
    ledger_snapshot = ledger.snapshot()
    record.update(
        {
            "schema_version": SCHEMA_VERSION,
            "variant": variant,
            "mode": "live"
            if execute_model
            else ("offline_injected_model" if model is not None else "offline_manifest_only"),
            "retained_candidate_fixture_excluded": True,
            "sdk_invocation_count": sdk_invocation_count,
            "logical_model_request_count": ledger_snapshot["request_count"],
            "observed_provider_attempt_count": len(attempts),
            "ledger": ledger_snapshot,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    )
    _write(descriptor, record)
    return record


@contextmanager
def _process_deadline() -> Any:
    if not hasattr(signal, "setitimer"):
        yield
        return
    old_handler, old_timer = (
        signal.getsignal(signal.SIGALRM),
        signal.setitimer(signal.ITIMER_REAL, PROCESS_BOUND_SECONDS),
    )
    signal.signal(
        signal.SIGALRM,
        lambda _signal, _frame: (_ for _ in ()).throw(
            ProcessDeadlineExceeded("comparison exceeded 120-second process bound")
        ),
    )
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, old_timer[0], old_timer[1])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("n1", "n2"), default="n1")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--erp-source", type=Path, default=DEFAULT_ERP_SOURCE)
    parser.add_argument("--saas-source", type=Path, default=DEFAULT_SAAS_SOURCE)
    parser.add_argument("--execute-model", action="store_true")
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    with _process_deadline():
        record = run_candidate(
            variant=cast(Variant, args.variant),
            output_path=args.output,
            artifact_path=args.artifact,
            erp_source=args.erp_source,
            saas_source=args.saas_source,
            execute_model=args.execute_model,
            manifest_path=args.manifest,
        )
    print(f"Native receiving comparison: {record['status']} ({args.output})")
    return 0 if record["status"] in {"STRUCTURAL_COMPLETE", "OFFLINE_INPUT_FROZEN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
