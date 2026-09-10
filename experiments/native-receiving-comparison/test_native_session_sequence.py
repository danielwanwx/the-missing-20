"""Offline, process-bound mechanics checks for the native six-turn session experiment."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any, cast

from strands.models import Model

EXPERIMENT = Path(__file__).parent
ROOT = EXPERIMENT.parents[1]
for path in (EXPERIMENT, ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import native_session_sequence as sequence  # noqa: E402
from native_receiving_comparison import _file_sha, _sha, _spec_names  # noqa: E402
from test_frozen_receiving_sdk_boundary_capture import (  # noqa: E402
    CASE_ID,
    _synthetic_erp_source,
    _synthetic_saas_source,
)

from the_missing_20.agents.live_advisory import SOURCE_TOOL_NAMES  # noqa: E402

QUESTIONS = [
    "For SYN-PR-01, what quantity was posted, and which stock-ledger record supports it?",
    "Do not execute or approve anything. Keep this conversation read-only.",
    "How many Box are ordered and how many remain outstanding on this purchase order?",
    "Does the receiving basis independently prove what was physically inside the cartons?",
    (
        "For the receipt I asked about first, what stock-ledger record supports it now, "
        "and did its posted quantity change?"
    ),
    (
        "What permission have I given you to change records, and what evidence supports "
        "your last answer?"
    ),
]
CHILD_TIMEOUT_SECONDS = 45
SIX_TURN_STAGE_COUNT = 18  # six production prepares, then six turns for each native candidate
READ_ONLY_ACK = (
    "Understood. I will keep this conversation read-only and will not execute or approve anything."
)


def _tool_events(
    name: str, payload: Mapping[str, Any], number: int, tool_id_prefix: str
) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "start": {
                    "toolUse": {
                        "name": name,
                        "toolUseId": f"{tool_id_prefix}-{number}",
                    }
                }
            }
        },
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(payload)}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}}},
    ]


def _text_events(text: str) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
        {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}}},
    ]


class LocalSequenceModel(Model):  # type: ignore[misc]
    """A local protocol model; it drives real Strands tool/history mechanics only."""

    def __init__(
        self,
        *,
        variant: str,
        answer: str,
        tool_id_prefix: str,
        source_reads: list[str] | None = None,
        citations: list[str] | None = None,
        fail_after: int | None = None,
    ) -> None:
        self.variant = variant
        self.answer = answer
        self.tool_id_prefix = tool_id_prefix
        self.source_reads = list(SOURCE_TOOL_NAMES) if source_reads is None else list(source_reads)
        self.citations = ["local-citation"] if citations is None else list(citations)
        self.fail_after = fail_after
        self.index = 0
        self.config = {"model_id": "local-session-test", "max_tokens": 1551, "temperature": 0}

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def update_config(self, **kwargs: Any) -> None:
        self.config.update(kwargs)

    async def structured_output(
        self, output_model: type[Any], prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        del output_model, prompt, system_prompt, kwargs
        if False:  # pragma: no cover
            yield {}
        raise AssertionError("native sequence must use Agent.stream_async")

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        del messages, system_prompt, kwargs
        if self.fail_after is not None and self.index >= self.fail_after:
            raise RuntimeError("local partial stream failure")
        if self.index < len(self.source_reads):
            name = self.source_reads[self.index]
            events = _tool_events(
                name, {"query": "local current source"}, self.index, self.tool_id_prefix
            )
        elif self.variant == "n2":
            names = _spec_names(tool_specs)
            choices = names.difference(SOURCE_TOOL_NAMES)
            assert len(choices) == 1
            events = _tool_events(
                choices.pop(),
                {"answer": self.answer, "citations": self.citations},
                self.index,
                self.tool_id_prefix,
            )
        else:
            events = _text_events(self.answer)
        self.index += 1
        for event in events:
            yield event


def _prepare_worker(kwargs: dict[str, Any]) -> None:
    sequence.prepare_turn(**kwargs)


def _run_worker(kwargs: dict[str, Any], model_args: dict[str, Any]) -> None:
    sequence.run_turn(model=LocalSequenceModel(**model_args), **kwargs)


def _encode(value: Any) -> Any:
    if isinstance(value, Path):
        return {"__path__": str(value)}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__path__"}:
            return Path(value["__path__"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _child(kind: str, *args: Any) -> int:
    """Start a fresh interpreter; fake models remain confined to this test module."""

    payload = json.dumps({"kind": kind, "args": _encode(list(args))})
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--native-session-test-child", payload],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=CHILD_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        raise AssertionError(
            f"child PID {process.pid} exceeded {CHILD_TIMEOUT_SECONDS}s; stdout={stdout!r}; "
            f"stderr={stderr!r}"
        ) from exc
    if process.returncode:
        raise AssertionError(
            f"child PID {process.pid} exited {process.returncode}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )
    return process.pid


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _fixture(tmp_path: Path, *, case_id: str = CASE_ID) -> Path:
    root = tmp_path / case_id
    root.mkdir(parents=True)
    erp_v1 = _synthetic_erp_source()
    erp_v1["case_id"] = case_id
    erp_v2 = copy.deepcopy(erp_v1)
    erp_v2["sequence"] = 2
    erp_v2["changed_at"] = "2026-09-09T00:01:00+00:00"
    erp_v2["ledger_evidence"]["stock_entries"][0]["name"] = "SYN-SLE-V2"
    erp_v1["ledger_evidence"]["stock_entries"][0]["name"] = "SYN-SLE-V1"
    saas = _synthetic_saas_source()
    saas["correlation_id"] = case_id
    paths = {
        "erp-v1.json": _write(root / "erp-v1.json", erp_v1),
        "erp-v2.json": _write(root / "erp-v2.json", erp_v2),
        "saas.json": _write(root / "saas.json", saas),
        "questions.json": _write(root / "questions.json", QUESTIONS),
    }
    manifest = {
        "case_id": case_id,
        "file_sha256": {name: _file_sha(path) for name, path in paths.items()},
    }
    return _write(root / "manifest.json", manifest)


def _prepared(tmp_path: Path, manifest: Path, turn: int) -> Path:
    output = tmp_path / f"prepared-{turn}.json"
    assert not output.exists(), "PREPARED bundles are exclusive and must not be overwritten"
    _child(
        "prepare",
        {
            "turn": turn,
            "output_path": output,
            "platform_state_path": tmp_path / "platform-state.json",
            "manifest_path": manifest,
        },
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["status"] == "PREPARED"
    return output


def _prepared_turns(tmp_path: Path, manifest: Path) -> dict[int, Path]:
    """Create one immutable production bundle per turn for both candidate histories."""

    return {turn: _prepared(tmp_path, manifest, turn) for turn in range(1, 7)}


def _run(
    tmp_path: Path,
    prepared: Path,
    *,
    variant: str,
    turn: int,
    session_root: Path,
    answer: str,
    source_reads: list[str] | None = None,
    citations: list[str] | None = None,
    fail_after: int | None = None,
) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    output = tmp_path / f"{variant}-turn-{turn}.json"
    _child(
        "run",
        {
            "variant": variant,
            "prepared_path": prepared,
            "output_path": output,
            "session_root": session_root,
            "predecessor_path": (tmp_path / f"{variant}-turn-{turn - 1}.json")
            if turn > 1
            else None,
        },
        {
            "variant": variant,
            "answer": answer,
            "tool_id_prefix": f"{variant}-turn-{turn}",
            "source_reads": source_reads,
            "citations": citations,
            "fail_after": fail_after,
        },
    )
    return cast(dict[str, Any], json.loads(output.read_text(encoding="utf-8")))


def _run_six(
    output_root: Path,
    prepared_turns: Mapping[int, Path],
    *,
    variant: str,
    session_root: Path,
) -> list[dict[str, Any]]:
    """Use fresh interpreters for every native turn of one independent candidate session."""

    output_root.mkdir()
    source_reads_by_turn = {2: [], 3: ["read_erp_evidence"]}
    return [
        _run(
            output_root,
            prepared_turns[turn],
            variant=variant,
            turn=turn,
            session_root=session_root,
            answer=READ_ONLY_ACK if turn == 2 else f"actual {variant.upper()} answer turn {turn}",
            source_reads=source_reads_by_turn.get(turn),
            citations=[] if turn == 2 else None,
        )
        for turn in range(1, 7)
    ]


def _messages_have_unique_consumed_pairs(messages: list[dict[str, Any]]) -> bool:
    pending: set[str] = set()
    seen_uses: set[str] = set()
    seen_results: set[str] = set()
    for message in messages:
        for block in message.get("content", []):
            if "toolUse" in block:
                tool_use_id = block["toolUse"]["toolUseId"]
                if tool_use_id in seen_uses:
                    return False
                seen_uses.add(tool_use_id)
                pending.add(tool_use_id)
            if "toolResult" in block:
                tool_use_id = block["toolResult"]["toolUseId"]
                if tool_use_id in seen_results or tool_use_id not in pending:
                    return False
                seen_results.add(tool_use_id)
                pending.remove(tool_use_id)
    return not pending and seen_uses == seen_results


def test_six_fresh_processes_retain_native_history_for_both_variants(tmp_path: Path) -> None:
    """One production-prepared bundle per turn feeds two divergent native histories."""

    manifest = _fixture(tmp_path)
    started = time.monotonic()
    prepared_turns = _prepared_turns(tmp_path, manifest)
    n1 = _run_six(
        tmp_path / "n1-output",
        prepared_turns,
        variant="n1",
        session_root=tmp_path / "n1-session",
    )
    n2 = _run_six(
        tmp_path / "n2-output",
        prepared_turns,
        variant="n2",
        session_root=tmp_path / "n2-session",
    )
    # Each stage is its own Popen child with a 45-second hard deadline. This
    # assertion gives the complete 18-stage proof a bounded, observable ceiling.
    assert time.monotonic() - started < SIX_TURN_STAGE_COUNT * CHILD_TIMEOUT_SECONDS
    assert all(record["status"] == "STRUCTURAL_COMPLETE" for record in n1 + n2)
    assert all(record["semantic_status"] == "NOT_EVALUATED" for record in n1 + n2)
    assert all(record["qualified_source_payloads_complete"] for record in n1 + n2)
    assert all(record["source_tools_available"] == list(SOURCE_TOOL_NAMES) for record in n1 + n2)

    for variant, records in (("n1", n1), ("n2", n2)):
        q6_request = json.dumps(records[-1]["provider_attempts"][0]["request"]["messages"])
        q3_request = json.dumps(records[2]["provider_attempts"][0]["request"]["messages"])
        assert f"actual {variant.upper()} answer turn 5" in q6_request
        assert QUESTIONS[1] in q6_request
        assert READ_ONLY_ACK in q3_request
        assert records[-1]["conversation_manager"]["removed_message_count"] == 0
        assert all(
            current["history_before"] == previous["history_after"]
            for previous, current in zip(records[:-1], records[1:], strict=True)
        )
        assert _messages_have_unique_consumed_pairs(records[-1]["history_after"])
        assert "SYN-SLE-V2" in json.dumps(records[4]["tool_reads"])
        assert "SYN-SLE-V1" in json.dumps(records[4]["history_before"])
        assert records[1]["tool_reads"] == []
        assert records[1]["source_tools_read"] == []
        assert records[1]["source_tools_unread"] == list(SOURCE_TOOL_NAMES)
        assert records[2]["source_tools_read"] == ["read_erp_evidence"]
        assert records[2]["source_tools_unread"] == [
            name for name in SOURCE_TOOL_NAMES if name != "read_erp_evidence"
        ]

    n2_history = json.dumps(n2[-1]["history_before"])
    assert n2[0]["final"]["structured_output"] == {
        "answer": "actual N2 answer turn 1",
        "citations": ["local-citation"],
    }
    assert n2[1]["final"]["structured_output"] == {
        "answer": READ_ONLY_ACK,
        "citations": [],
    }
    assert "SequenceAnswer" in n2_history and "local-citation" in n2_history


def test_zero_read_factual_output_is_retained_without_semantic_acceptance(tmp_path: Path) -> None:
    """SDK completion does not turn an unsupported external claim into a semantic pass."""

    manifest = _fixture(tmp_path)
    prepared = _prepared(tmp_path, manifest, 1)
    factual_claim = "The current posted quantity is 1 Box."
    for variant in ("n1", "n2"):
        record = _run(
            tmp_path / variant,
            prepared,
            variant=variant,
            turn=1,
            session_root=tmp_path / f"{variant}-session",
            answer=factual_claim,
            source_reads=[],
            citations=[],
        )
        assert record["status"] == "STRUCTURAL_COMPLETE"
        assert record["semantic_status"] == "NOT_EVALUATED"
        assert record["tool_reads"] == []
        assert record["source_tools_read"] == []
        assert record["source_tools_unread"] == list(SOURCE_TOOL_NAMES)
        assert factual_claim in json.dumps(record["final"])


def test_case_and_variant_sessions_are_isolated(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    prepared = _prepared(tmp_path, manifest, 1)
    n1 = _run(
        tmp_path / "n1",
        prepared,
        variant="n1",
        turn=1,
        session_root=tmp_path / "sessions",
        answer="N1 isolated",
    )
    n2 = _run(
        tmp_path / "n2",
        prepared,
        variant="n2",
        turn=1,
        session_root=tmp_path / "sessions",
        answer="N2 isolated",
    )
    foreign_root = tmp_path / "foreign"
    foreign_manifest = _fixture(foreign_root, case_id="SYNTHETIC-OTHER-CASE")
    foreign = _run(
        foreign_root,
        _prepared(foreign_root, foreign_manifest, 1),
        variant="n1",
        turn=1,
        session_root=tmp_path / "sessions",
        answer="foreign",
    )
    assert n1["history_before"] == n2["history_before"] == foreign["history_before"] == []
    assert n1["session_id"] != n2["session_id"] != foreign["session_id"]
    v1_n1_session = f"m20-session-{_sha({'case_id': CASE_ID, 'variant': 'n1'})[:24]}"
    assert n1["session_id"] != v1_n1_session
    assert n1["session_identity_schema_version"] == sequence.SCHEMA_VERSION


def test_v1_prepared_or_predecessor_cannot_reach_the_model(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    prepared_one = _prepared(tmp_path, manifest, 1)
    legacy_prepared = json.loads(prepared_one.read_text(encoding="utf-8"))
    legacy_prepared["schema_version"] = "missing20-native-receiving-session-sequence/v1"
    legacy_prepared["session_identity_schema_version"] = (
        "missing20-native-receiving-session-sequence/v1"
    )
    legacy_prepared_path = _write(tmp_path / "legacy-prepared-v1.json", legacy_prepared)
    invalid_prepared = _run(
        tmp_path / "invalid-prepared",
        legacy_prepared_path,
        variant="n1",
        turn=1,
        session_root=tmp_path / "invalid-prepared-session",
        answer="must not reach the model",
    )

    output_root = tmp_path / "valid"
    first = _run(
        output_root,
        prepared_one,
        variant="n1",
        turn=1,
        session_root=tmp_path / "valid-session",
        answer="valid v2 first turn",
    )
    assert first["status"] == "STRUCTURAL_COMPLETE"
    predecessor_path = output_root / "n1-turn-1.json"
    legacy_predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    legacy_predecessor["schema_version"] = "missing20-native-receiving-session-sequence/v1"
    legacy_predecessor["session_identity_schema_version"] = (
        "missing20-native-receiving-session-sequence/v1"
    )
    _write(predecessor_path, legacy_predecessor)
    invalid_predecessor = _run(
        output_root,
        _prepared(tmp_path, manifest, 2),
        variant="n1",
        turn=2,
        session_root=tmp_path / "valid-session",
        answer="must not reach the model",
    )

    for record in (invalid_prepared, invalid_predecessor):
        assert record["status"] == "EXECUTION_FAILED"
        assert record["semantic_status"] == "NOT_EVALUATED"
        assert record["sdk_invocation_count"] == 0
        assert record["logical_model_request_count"] == 0
        assert record["observed_provider_attempt_count"] == 0


def test_pre_and_post_restore_contract_drift_stop_before_model(tmp_path: Path) -> None:
    manifest, root = _fixture(tmp_path), tmp_path / "session"
    first = _run(
        tmp_path,
        _prepared(tmp_path, manifest, 1),
        variant="n1",
        turn=1,
        session_root=root,
        answer="first",
    )
    session_id = first["session_id"]
    sidecar = root / f"session-contract-{session_id}.json"
    changed = json.loads(sidecar.read_text(encoding="utf-8"))
    changed["contract"]["runtime_model_config"]["model_id"] = "drift"
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    predecessor = tmp_path / "n1-turn-1.json"
    predecessor_record = json.loads(predecessor.read_text(encoding="utf-8"))
    predecessor_record["session_contract_sha256"] = _file_sha(sidecar)
    predecessor.write_text(json.dumps(predecessor_record), encoding="utf-8")
    pre = _run(
        tmp_path,
        _prepared(tmp_path, manifest, 2),
        variant="n1",
        turn=2,
        session_root=root,
        answer="second",
    )
    assert pre["status"] == "EXECUTION_FAILED" and pre["logical_model_request_count"] == 0
    assert pre["sdk_invocation_count"] == 0
    fresh = tmp_path / "post"
    second_first = _run(
        fresh,
        _prepared(fresh, _fixture(fresh), 1),
        variant="n1",
        turn=1,
        session_root=fresh / "session",
        answer="first",
    )
    _session_id, agent_id = sequence._ids(CASE_ID, "n1")
    snapshot = sequence._snapshot_path(fresh / "session", second_first["session_id"], agent_id)
    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    raw["data"]["system_prompt"] = [{"text": "drift"}]
    snapshot.write_text(json.dumps(raw), encoding="utf-8")
    predecessor = fresh / "n1-turn-1.json"
    predecessor_record = json.loads(predecessor.read_text(encoding="utf-8"))
    predecessor_record["snapshot_sha256"] = _file_sha(snapshot)
    predecessor.write_text(json.dumps(predecessor_record), encoding="utf-8")
    post = _run(
        fresh,
        _prepared(fresh, fresh / "SYNTHETIC-RECEIVING-CASE" / "manifest.json", 2),
        variant="n1",
        turn=2,
        session_root=fresh / "session",
        answer="second",
    )
    assert post["status"] == "EXECUTION_FAILED" and post["logical_model_request_count"] == 0
    assert post["sdk_invocation_count"] == 0
    assert "restored Agent prompt" in post["error"]["message"]


def test_partial_snapshot_cannot_be_continued(tmp_path: Path) -> None:
    manifest, root = _fixture(tmp_path), tmp_path / "session"
    failed = _run(
        tmp_path,
        _prepared(tmp_path, manifest, 1),
        variant="n1",
        turn=1,
        session_root=root,
        answer="never",
        fail_after=1,
    )
    next_turn = _run(
        tmp_path,
        _prepared(tmp_path, manifest, 2),
        variant="n1",
        turn=2,
        session_root=root,
        answer="never",
    )
    assert failed["status"] == "EXECUTION_FAILED"
    assert failed["snapshot_path"] is not None
    snapshot = Path(failed["snapshot_path"])
    assert snapshot.is_file() and failed["snapshot_sha256"] == _file_sha(snapshot)
    assert next_turn["status"] == "EXECUTION_FAILED"
    assert next_turn["logical_model_request_count"] == 0


if __name__ == "__main__":  # pragma: no cover - exercised by explicit fresh-interpreter tests.
    if len(sys.argv) != 3 or sys.argv[1] != "--native-session-test-child":
        raise SystemExit("test helper requires --native-session-test-child JSON")
    request = _decode(json.loads(sys.argv[2]))
    if request["kind"] == "prepare":
        _prepare_worker(*request["args"])
    elif request["kind"] == "run":
        _run_worker(*request["args"])
    else:
        raise SystemExit("unknown native session test child")
