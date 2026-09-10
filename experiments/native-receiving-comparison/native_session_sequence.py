"""Native six-turn receiving-session experiment; provider calls require explicit opt-in."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import stat
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, cast

import native_receiving_comparison as base
from strands import Agent
from strands.agent import AgentResult
from strands.agent.conversation_manager import NullConversationManager
from strands.models import Model
from strands.session import SnapshotSessionManager
from strands.storage import LocalFileStorage

ROOT = base.ROOT
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.diagnostics.serve_frozen_receiving_dialogue import (  # noqa: E402
    FileBackedReadOnlySource,
    FrozenFixtureAgentPlatform,
    frozen_receiving_packet,
)
from the_missing_20.adapters.strands_models import BudgetedModel  # noqa: E402
from the_missing_20.agents.live_advisory import (  # noqa: E402
    SOURCE_TOOL_NAMES,
    model_source_payloads,
)
from the_missing_20.ports.agent_model import AgentBudgetLedger  # noqa: E402

SCHEMA_VERSION = "missing20-native-receiving-session-sequence/v1"
FIXTURE_ROOT = Path("/private/tmp/m20-s2-d4-screen-v2")
Variant = Literal["n1", "n2"]
SEQUENCE_CAP_USD_PER_VARIANT = "0.96"
SEQUENCE_CAP_USD_PAIR = "1.92"
SEQUENCE_PROMPT = base.GENERIC_PROMPT.replace(
    "Use prior human context included in the question only to resolve references.",
    "Use native conversation history only to resolve references; current facts and authority "
    "must come from sources returned in this turn.",
)


class SequenceError(RuntimeError):
    """The fixed native sequence cannot safely advance."""


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SequenceError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, json.JSONDecodeError) as exc:
        raise SequenceError(f"{label} is unreadable: {path}") from exc


def _questions(manifest_path: Path) -> tuple[dict[str, Any], list[str]]:
    manifest = _load(manifest_path, "fixture manifest")
    root = manifest_path.parent
    questions_path = root / "questions.json"
    expected = _mapping(manifest.get("file_sha256"), "fixture file hashes").get("questions.json")
    if not isinstance(expected, str) or base._file_sha(questions_path) != expected:
        raise SequenceError("fixture questions.json does not match its declared manifest hash")
    try:
        questions = json.loads(questions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SequenceError("fixture questions are unreadable") from exc
    if (
        not isinstance(questions, list)
        or len(questions) != 6
        or not all(isinstance(question, str) and question for question in questions)
    ):
        raise SequenceError("fixture must declare exactly six non-empty literal questions")
    return manifest, list(questions)


def _source_paths(manifest_path: Path, turn: int) -> tuple[Path, Path]:
    manifest, _questions_value = _questions(manifest_path)
    erp_name = "erp-v1.json" if turn <= 4 else "erp-v2.json"
    source_hashes = _mapping(manifest.get("file_sha256"), "fixture file hashes")
    root = manifest_path.parent
    erp, saas = root / erp_name, root / "saas.json"
    for path, name in ((erp, erp_name), (saas, "saas.json")):
        expected = source_hashes.get(name)
        if not isinstance(expected, str) or base._file_sha(path) != expected:
            raise SequenceError(f"fixture {name} does not match its declared manifest hash")
    return erp, saas


def _ids(case_id: str, variant: Variant) -> tuple[str, str]:
    digest = base._sha({"case_id": case_id, "variant": variant})[:24]
    return f"m20-session-{digest}", f"m20-{variant}"


def _snapshot_path(root: Path, session_id: str, agent_id: str) -> Path:
    return (
        root
        / "session"
        / session_id
        / "scopes"
        / "agent"
        / agent_id
        / "snapshots"
        / "snapshot_latest.json"
    )


def _contract(*, variant: Variant, tools: list[Any]) -> dict[str, Any]:
    source_specs = [base._copy(item.tool_spec) for item in tools]
    n2_spec = base._copy(base.convert_pydantic_to_tool_spec(base.NarrowAnswer))
    return {
        "prompt": SEQUENCE_PROMPT,
        "prompt_sha256": base._sha(SEQUENCE_PROMPT),
        "model_contract": base._model_contract(),
        "source_tool_specs": source_specs,
        "source_tool_specs_sha256": base._sha(source_specs),
        "n2_schema": n2_spec if variant == "n2" else None,
        "n2_schema_sha256": base._sha(n2_spec) if variant == "n2" else None,
        "limits": dict(base._limits()),
        "session": {
            "manager": "SnapshotSessionManager",
            "storage": "LocalFileStorage",
            "save_latest_on": "message",
            "snapshot_trigger": None,
            "conversation_manager": "NullConversationManager",
            "proactive_compression": None,
            "checkpointing": False,
            "retry_strategy": None,
        },
    }


def _private_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise SequenceError(f"session root must be private 0700: {root}")


@contextmanager
def _private_umask() -> Any:
    original = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(original)


def _verify_private_tree(root: Path) -> None:
    for path in root.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir() and mode & 0o077:
            raise SequenceError(f"session directory is wider than 0700: {path}")
        if path.is_file() and mode & 0o077:
            raise SequenceError(f"session file is wider than 0600: {path}")


def _write_sidecar(path: Path, contract: Mapping[str, Any]) -> str:
    descriptor = base._reserve(path)
    base._write(
        descriptor, {"contract": base._copy(contract), "contract_sha256": base._sha(contract)}
    )
    return cast(str, base._file_sha(path))


def _sidecar(path: Path, contract: Mapping[str, Any], *, first_turn: bool) -> str:
    if first_turn:
        if path.exists():
            raise SequenceError("first turn refuses a reused session contract")
        return _write_sidecar(path, contract)
    saved = _load(path, "session contract")
    if saved.get("contract") != base._copy(contract):
        raise SequenceError("session contract drift detected before Agent initialization")
    return cast(str, base._file_sha(path))


def _agent_contract(
    agent: Agent,
    contract: Mapping[str, Any],
    runtime_model_config: object,
    tools: list[Any],
    variant: Variant,
    session_id: str,
    session_root: Path,
) -> None:
    manager = agent.conversation_manager
    if agent.system_prompt != SEQUENCE_PROMPT or not isinstance(manager, NullConversationManager):
        raise SequenceError("restored Agent prompt or conversation manager drifted")
    if manager._compression_threshold is not None:
        raise SequenceError("restored native history configuration drifted")
    session = getattr(agent, "_session_manager", None)
    storage = getattr(getattr(session, "_storage", None), "_storage", None)
    if (
        not isinstance(session, SnapshotSessionManager)
        or session.session_id != session_id
        or getattr(session, "_save_latest_on", None) != "message"
        or getattr(session, "_snapshot_trigger", object()) is not None
        or not isinstance(storage, LocalFileStorage)
        or Path(str(getattr(storage, "_base_dir", ""))).resolve() != session_root.resolve()
    ):
        raise SequenceError("restored native session configuration drifted")
    actual_specs = base._copy(agent.tool_registry.get_all_tool_specs())
    expected_specs = [base._copy(item.tool_spec) for item in tools]
    if actual_specs != expected_specs or agent.tool_names != list(SOURCE_TOOL_NAMES):
        raise SequenceError("restored source-tool configuration drifted")
    expected_model = base.NarrowAnswer if variant == "n2" else None
    if getattr(agent, "_default_structured_output_model", None) is not expected_model:
        raise SequenceError("restored structured-output schema drifted")
    if agent.model.stateful:
        raise SequenceError("stateful model cannot safely restore native local history")
    if base._copy(agent.model.get_config()) != base._copy(runtime_model_config):
        raise SequenceError("restored model configuration drifted")


def _runtime_contract(
    model: Model, *, execute_model: bool, contract: Mapping[str, Any]
) -> dict[str, Any]:
    config = base._copy(model.get_config())
    if execute_model:
        expected = _mapping(contract.get("model_contract"), "frozen model contract")
        if not isinstance(config, Mapping) or any(
            config.get(key) != value
            for key, value in expected.items()
            if key in {"model_id", "max_tokens", "temperature"}
        ):
            raise SequenceError("live model configuration does not match frozen Nova Pro contract")
    return {
        **base._copy(contract),
        "runtime_model_config": config,
        "runtime_model_mode": "live" if execute_model else "offline_injected",
    }


def _verify_prepared_fixture(prepared: Mapping[str, Any]) -> None:
    freeze = _mapping(prepared.get("freeze"), "prepared freeze metadata")
    if (
        freeze.get("native_script_sha256") != base._file_sha(Path(__file__))
        or freeze.get("base_script_sha256") != base._file_sha(Path(base.__file__))
        or freeze.get("execution_revision") != base._revision()
        or freeze.get("strands_agents_version") != importlib.metadata.version("strands-agents")
    ):
        raise SequenceError("prepared bundle code, revision, or SDK freeze no longer matches")
    manifest_path = Path(str(freeze.get("fixture_manifest_path", "")))
    if base._file_sha(manifest_path) != freeze.get("fixture_manifest_sha256"):
        raise SequenceError("prepared fixture manifest no longer matches its freeze")
    turn = prepared.get("turn")
    if not isinstance(turn, int):
        raise SequenceError("prepared turn is invalid")
    _manifest, questions = _questions(manifest_path)
    erp, saas = _source_paths(manifest_path, turn)
    sources = _mapping(prepared.get("source_file_sha256"), "prepared source hashes")
    if (
        prepared.get("question") != questions[turn - 1]
        or sources.get("erp") != base._file_sha(erp)
        or sources.get("saas") != base._file_sha(saas)
    ):
        raise SequenceError("prepared literal question or fixture source no longer matches")


def prepare_turn(
    *,
    turn: int,
    output_path: Path,
    platform_state_path: Path,
    manifest_path: Path = FIXTURE_ROOT / "manifest.json",
) -> dict[str, Any]:
    """Freeze one literal question and freshly derived production authority/source bundle."""

    descriptor = base._reserve(output_path)
    started = time.monotonic()
    try:
        manifest, questions = _questions(manifest_path)
        if not 1 <= turn <= len(questions):
            raise SequenceError("turn must be between 1 and 6")
        case_id = manifest.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise SequenceError("fixture manifest lacks case_id")
        erp_path, saas_path = _source_paths(manifest_path, turn)
        platform = FrozenFixtureAgentPlatform(
            FileBackedReadOnlySource(erp_path, kind="erp"),
            FileBackedReadOnlySource(saas_path, kind="saas"),
            state_path=platform_state_path,
        )
        current = platform.current()
        if current.get("case_id") != case_id:
            raise SequenceError("production platform case does not match fixture manifest")
        human = platform.record_human_request(questions[turn - 1], case_id)
        projection = platform.current()
        packet = frozen_receiving_packet(projection)
        payloads = model_source_payloads(packet)
        if not isinstance(payloads, Mapping) or set(SOURCE_TOOL_NAMES).difference(payloads):
            raise SequenceError(
                "production packet did not produce all five qualified source payloads"
            )
        tools = base._source_tools(cast(Mapping[str, Any], payloads), [])
        common = _contract(variant="n1", tools=tools)
        record: dict[str, Any] = {
            "status": "PREPARED",
            "schema_version": SCHEMA_VERSION,
            "turn": turn,
            "case_id": case_id,
            "question": questions[turn - 1],
            "source_version": "v1" if turn <= 4 else "v2",
            "fixture_manifest_sha256": base._file_sha(manifest_path),
            "source_file_sha256": {
                "erp": base._file_sha(erp_path),
                "saas": base._file_sha(saas_path),
            },
            "qualified_source_payloads": base._copy(dict(payloads)),
            "qualified_source_payloads_sha256": base._sha(payloads),
            "case_authority": {
                "case_id": projection.get("case_id"),
                "agent_run": projection.get("agent_run"),
                "mode": projection.get("mode"),
                "human_intent": human,
                "dialogue_context": projection.get("dialogue_context"),
            },
            "production_projection_sha256": base._sha(projection),
            "common_contract": common,
            "strands_agents_version": importlib.metadata.version("strands-agents"),
            "freeze": {
                "native_script_sha256": base._file_sha(Path(__file__)),
                "base_script_sha256": base._file_sha(Path(base.__file__)),
                "execution_revision": base._revision(),
                "strands_agents_version": importlib.metadata.version("strands-agents"),
                "fixture_manifest_path": str(manifest_path.resolve()),
                "fixture_manifest_sha256": base._file_sha(manifest_path),
            },
        }
    except Exception as exc:
        record = {
            "status": "PREPARATION_FAILED",
            "schema_version": SCHEMA_VERSION,
            "turn": turn,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    base._write(descriptor, record)
    return record


async def _stream(agent: Agent, question: str, events: list[dict[str, Any]]) -> AgentResult:
    result: AgentResult | None = None
    async for event in agent.stream_async(question, limits=base._limits()):
        value = event.get("result") if isinstance(event, Mapping) else None
        if isinstance(value, AgentResult):
            result = value
            events.append({"result": value.to_dict()})
        else:
            events.append(base._copy(event))
    if result is None:
        raise SequenceError("native Agent emitted no terminal AgentResult")
    return result


def _final(result: AgentResult) -> dict[str, Any]:
    structured = result.structured_output
    return {
        "message": base._copy(result.message),
        "structured_output": structured.model_dump(mode="json") if structured is not None else None,
        "stop_reason": str(result.stop_reason),
    }


def run_turn(
    *,
    variant: Variant,
    prepared_path: Path,
    output_path: Path,
    session_root: Path,
    predecessor_path: Path | None = None,
    model: Model | None = None,
    execute_model: bool = False,
) -> dict[str, Any]:
    """Run one candidate turn; the public CLI constructs a provider only with --execute-model."""

    if variant not in {"n1", "n2"}:
        raise SequenceError("variant must be n1 or n2")
    descriptor = base._reserve(output_path)
    started = time.monotonic()
    reads: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    ledger = AgentBudgetLedger(base._budget())
    sdk_invocation_count = 0
    session_id: str | None = None
    snapshot_path: Path | None = None
    snapshot_hash: str | None = None
    try:
        prepared = _load(prepared_path, "prepared turn")
        if prepared.get("status") != "PREPARED" or prepared.get("schema_version") != SCHEMA_VERSION:
            raise SequenceError("run requires a PREPARED native sequence turn")
        turn, case_id, question = (
            prepared.get("turn"),
            prepared.get("case_id"),
            prepared.get("question"),
        )
        payloads = prepared.get("qualified_source_payloads")
        if (
            not isinstance(turn, int)
            or not isinstance(case_id, str)
            or not isinstance(question, str)
        ):
            raise SequenceError("prepared turn lacks identity or literal question")
        if not isinstance(payloads, Mapping) or set(SOURCE_TOOL_NAMES).difference(payloads):
            raise SequenceError("prepared turn lacks all five source payloads")
        if base._sha(payloads) != prepared.get("qualified_source_payloads_sha256"):
            raise SequenceError("prepared qualified source payloads were altered")
        _verify_prepared_fixture(prepared)
        tools = base._source_tools(cast(Mapping[str, Any], payloads), reads)
        contract = _contract(variant=variant, tools=tools)
        common = _contract(variant="n1", tools=tools)
        if prepared.get("common_contract") != common:
            raise SequenceError("prepared common prompt/model/tool/session contract drifted")
        session_id, agent_id = _ids(case_id, variant)
        if model is not None and execute_model:
            raise SequenceError("injected offline model cannot combine with --execute-model")
        if model is None and not execute_model:
            record = {
                "status": "OFFLINE_INPUT_FROZEN",
                "turn": turn,
                "case_id": case_id,
                "question": question,
                "session_id": session_id,
                "sequence_cap_usd_per_variant": SEQUENCE_CAP_USD_PER_VARIANT,
                "pair_cap_usd": SEQUENCE_CAP_USD_PAIR,
            }
        else:
            delegate = model or base._live_model(ledger)
            runtime_contract = _runtime_contract(
                delegate, execute_model=execute_model, contract=contract
            )
            _private_root(session_root)
            sidecar = session_root / f"session-contract-{session_id}.json"
            snapshot = _snapshot_path(session_root, session_id, agent_id)
            snapshot_path = snapshot
            if turn == 1:
                if predecessor_path is not None or snapshot.exists():
                    raise SequenceError("turn one requires a fresh candidate session")
                sidecar_hash = _sidecar(sidecar, runtime_contract, first_turn=True)
            else:
                if predecessor_path is None or not snapshot.is_file():
                    raise SequenceError("later turn requires predecessor output and prior snapshot")
                predecessor = _load(predecessor_path, "predecessor output")
                if (
                    predecessor.get("status") != "STRUCTURAL_COMPLETE"
                    or predecessor.get("turn") != turn - 1
                ):
                    raise SequenceError(
                        "candidate cannot continue after a non-complete predecessor"
                    )
                if predecessor.get("session_id") != session_id or predecessor.get(
                    "session_contract_sha256"
                ) != base._file_sha(sidecar):
                    raise SequenceError(
                        "predecessor session identity or contract hash does not match"
                    )
                if predecessor.get("snapshot_sha256") != base._file_sha(snapshot):
                    raise SequenceError(
                        "predecessor snapshot hash does not match current native history"
                    )
                sidecar_hash = _sidecar(sidecar, runtime_contract, first_turn=False)
            bounded = (
                delegate if isinstance(delegate, BudgetedModel) else BudgetedModel(delegate, ledger)
            )
            capturing = base.CapturingModel(cast(Model, bounded))
            attempts = capturing.attempts
            manager = NullConversationManager(proactive_compression=None)
            with _private_umask():
                agent = Agent(
                    model=capturing,
                    tools=tools,
                    system_prompt=SEQUENCE_PROMPT,
                    structured_output_model=base.NarrowAnswer if variant == "n2" else None,
                    conversation_manager=manager,
                    session_manager=SnapshotSessionManager(
                        session_id,
                        storage=LocalFileStorage(str(session_root)),
                        save_latest_on="message",
                        snapshot_trigger=None,
                    ),
                    callback_handler=None,
                    retry_strategy=None,
                    checkpointing=False,
                    agent_id=agent_id,
                )
                _agent_contract(
                    agent,
                    contract,
                    runtime_contract["runtime_model_config"],
                    tools,
                    variant,
                    session_id,
                    session_root,
                )
                history_before = base._copy(agent.messages)
                sdk_invocation_count = 1
                result = asyncio.run(
                    asyncio.wait_for(
                        _stream(agent, question, events), timeout=base.ADVISORY_WALL_TIMEOUT_SECONDS
                    )
                )
                history_after = base._copy(agent.messages)
            _verify_private_tree(session_root)
            snapshot_hash = base._file_sha(snapshot) if snapshot.is_file() else None
            missing = [
                name for name in SOURCE_TOOL_NAMES if name not in {item["tool"] for item in reads}
            ]
            record = {
                "status": "STRUCTURAL_COMPLETE" if not missing else "STRUCTURAL_FAIL",
                "structural_reason": None if not missing else "required_source_tools_not_read",
                "missing_source_reads": missing,
                "turn": turn,
                "case_id": case_id,
                "question": question,
                "session_id": session_id,
                "session_contract_sha256": sidecar_hash,
                "snapshot_path": str(snapshot),
                "snapshot_sha256": snapshot_hash,
                "agent_events": events,
                "provider_attempts": attempts,
                "tool_reads": reads,
                "history_before": history_before,
                "history_after": history_after,
                "conversation_manager": {
                    **manager.get_state(),
                    "active_message_count": len(agent.messages),
                },
                "final": _final(result),
                "sequence_cap_usd_per_variant": SEQUENCE_CAP_USD_PER_VARIANT,
                "pair_cap_usd": SEQUENCE_CAP_USD_PAIR,
            }
    except Exception as exc:
        _verify_private_tree(session_root) if session_root.exists() else None
        if snapshot_path is not None and snapshot_path.is_file():
            snapshot_hash = base._file_sha(snapshot_path)
        record = {
            "status": "EXECUTION_FAILED",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "agent_events": events,
            "provider_attempts": attempts,
            "tool_reads": reads,
            "session_id": session_id,
            "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
            "snapshot_sha256": snapshot_hash,
        }
    ledger_snapshot = ledger.snapshot()
    record.update(
        {
            "schema_version": SCHEMA_VERSION,
            "variant": variant,
            "mode": "live"
            if execute_model
            else ("offline_injected_model" if model else "offline_manifest_only"),
            "sdk_invocation_count": sdk_invocation_count,
            "logical_model_request_count": ledger_snapshot["request_count"],
            "observed_provider_attempt_count": len(attempts),
            "ledger": ledger_snapshot,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    )
    base._write(descriptor, record)
    return record


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--turn", type=int, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--platform-state", type=Path, required=True)
    prepare.add_argument("--fixture-manifest", type=Path, default=FIXTURE_ROOT / "manifest.json")
    run = commands.add_parser("run")
    run.add_argument("--variant", choices=("n1", "n2"), required=True)
    run.add_argument("--prepared", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--session-root", type=Path, required=True)
    run.add_argument("--predecessor", type=Path)
    run.add_argument("--execute-model", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    with base._process_deadline():
        if args.command == "prepare":
            record = prepare_turn(
                turn=args.turn,
                output_path=args.output,
                platform_state_path=args.platform_state,
                manifest_path=args.fixture_manifest,
            )
        else:
            record = run_turn(
                variant=cast(Variant, args.variant),
                prepared_path=args.prepared,
                output_path=args.output,
                session_root=args.session_root,
                predecessor_path=args.predecessor,
                execute_model=args.execute_model,
            )
    print(f"Native receiving session sequence: {record['status']} ({args.output})")
    return (
        0 if record["status"] in {"PREPARED", "STRUCTURAL_COMPLETE", "OFFLINE_INPUT_FROZEN"} else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
