"""Offline proof for the frozen D4 receiving dialogue HTTP harness."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.diagnostics.serve_frozen_receiving_dialogue import (
    FileBackedReadOnlySource,
    FrozenFixtureError,
    FrozenReceivingDialogueServer,
    ReadOnlyReceivingScope,
    build_frozen_receiving_dialogue_server,
)
from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.agents.live_advisory import (
    AdvisoryDisposition,
    AdvisoryRun,
    LiveAdvisoryResult,
)

FIXTURE_ROOT = Path("/private/tmp/m20-s2-d4-screen-v2")
ERP_V1 = FIXTURE_ROOT / "erp-v1.json"
ERP_V2 = FIXTURE_ROOT / "erp-v2.json"
SAAS = FIXTURE_ROOT / "saas.json"
QUESTIONS_BEFORE_RESTART = FIXTURE_ROOT / "questions-before-restart.json"
QUESTIONS_AFTER_RESTART = FIXTURE_ROOT / "questions-after-restart.json"


class OfflineFixtureRunner:
    """Test-only runner that labels its fake answer and retains supplied packets."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        packet: Mapping[str, Any],
        *,
        factory: object,
        question: str,
    ) -> AdvisoryRun:
        del factory
        copied = json.loads(json.dumps(packet, default=str))
        self.calls.append({"packet": copied, "question": question})
        evidence_ids = tuple(str(item) for item in packet["evidence_ids"])
        turn = len(self.calls)
        cited_id = "MAT-PRE-2026-00006" if turn == 1 else "PUR-ORD-2026-00015"
        assert cited_id in evidence_ids
        required_tools = tuple(str(name) for name in packet.get("required_tools", ()))
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=(cited_id,),
                reason=(
                    "OFFLINE_FIXTURE_ASSISTANT_PROSE: current frozen evidence was inspected; "
                    "no record change was performed."
                ),
                safe_next_step="Inspect the current read-only source records.",
                write_performed=False,
            ),
            tool_calls=required_tools,
            provider={"mode": "offline_fixture_test", "real_model": False},
            latency_ms=1,
            usage={"request_count": 0, "cost_usd": "0"},
        )


def _copy(path: Path, destination: Path) -> Path:
    destination.write_bytes(path.read_bytes())
    return destination


def _questions(path: Path) -> tuple[str, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, list)
    assert all(isinstance(question, str) for question in value)
    return tuple(value)


@contextmanager
def _running(server: FrozenReceivingDialogueServer) -> Iterator[str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def _post(base_url: str, path: str, payload: Mapping[str, object]) -> dict[str, object]:
    request = Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": base_url},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 - loopback fixture server
        result = json.loads(response.read().decode("utf-8"))
    assert isinstance(result, dict)
    return result


def _get(base_url: str, path: str) -> dict[str, object]:
    with urlopen(base_url + path, timeout=10) as response:  # noqa: S310 - loopback fixture server
        result = json.loads(response.read().decode("utf-8"))
    assert isinstance(result, dict)
    return result


def _source_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return (
        _copy(ERP_V1, tmp_path / "erp-v1.json"),
        _copy(ERP_V2, tmp_path / "erp-v2.json"),
        _copy(SAAS, tmp_path / "saas.json"),
    )


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, Mapping)
    return dict(value)


def _mappings(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    return [_mapping(item) for item in value]


def test_file_backed_reader_requires_declared_read_only_schema_and_rereads(tmp_path: Path) -> None:
    erp_v1, _, _ = _source_paths(tmp_path)
    reader = FileBackedReadOnlySource(erp_v1, kind="erp")
    first = reader.current()
    assert reader.external_calls == 0
    assert reader.read_count == 1
    assert first["case_id"] == "M20-GOODS-20260909-40-R3"

    altered = dict(first)
    altered["read_only"] = False
    erp_v1.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(FrozenFixtureError, match="read_only"):
        reader.current()

    altered["read_only"] = True
    altered["schema_version"] = "missing20-erpnext-evidence/v99"
    erp_v1.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(FrozenFixtureError, match="schema"):
        reader.current()


def test_frozen_server_uses_real_http_gateway_and_persists_d4_restart(
    tmp_path: Path,
) -> None:
    erp_v1, erp_v2, saas = _source_paths(tmp_path)
    before_questions = _questions(QUESTIONS_BEFORE_RESTART)
    after_questions = _questions(QUESTIONS_AFTER_RESTART)
    assert len(before_questions) == 4 and len(after_questions) == 2
    runner = OfflineFixtureRunner()
    runtime = tmp_path / "fresh-runtime"
    root_v1_hash = hashlib.sha256(ERP_V1.read_bytes()).hexdigest()
    root_v2_hash = hashlib.sha256(ERP_V2.read_bytes()).hexdigest()

    try:
        server = build_frozen_receiving_dialogue_server(
            host="127.0.0.1",
            port=0,
            runtime_directory=runtime,
            erp_source=erp_v1,
            saas_source=saas,
            runner=runner,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")

    assert server.repository_root == runtime / "isolated-config"
    assert not (server.repository_root / ".env").exists()
    platform = cast(AgentPlatform, server.agent_platform)
    assert platform._executor is None
    assert isinstance(platform._receiving, ReadOnlyReceivingScope)
    assert server.photo_receiving.erp is None
    assert server.photo_receiving.drafts_enabled is False
    assert server.receiving_draft_worker.thread is None
    assert server.receiving_handoff_worker is None
    assert server.automatic_investigation is not None
    assert server.automatic_investigation.current()["enabled"] is False
    truth = server.agent_platform.runtime_truth()
    assert truth["source_mode"] == "frozen_read_only_fixture"
    assert truth["external_provider_reads"] == "disabled"
    assert truth["external_provider_writes"] == "disabled"
    assert runner.calls == []
    assert server.frozen_erp_reader.external_calls == server.frozen_saas_reader.external_calls == 0
    startup_reads = server.frozen_erp_reader.read_count

    with _running(server) as base_url:
        with pytest.raises(HTTPError) as forbidden:
            _post(
                base_url,
                "/api/v1/agent-platform/execute",
                {"approval_id": "not-permitted", "idempotency_key": "m20-not-permitted"},
            )
        assert forbidden.value.code == 403
        health = _get(base_url, "/healthz")
        hero_truth = _mapping(_mapping(health["paths"])["hero_case_console"])
        assert hero_truth["source_mode"] == "frozen_read_only_fixture"

        responses = [
            _post(base_url, "/api/v1/agent-platform/ask", {"question": question})
            for question in before_questions
        ]

    assert len(runner.calls) == 4
    assert server.frozen_erp_reader.read_count > startup_reads
    assert all(
        _mapping(_mapping(response["agent_advisory"])["provider"])["mode"] == "offline_fixture_test"
        for response in responses
    )
    fourth = responses[-1]
    assert _mapping(fourth["human_intent"])["read_only_requested"] is True
    assert [request["question"] for request in _mappings(fourth["human_requests"])] == list(
        before_questions
    )
    dialogue = _mapping(fourth["dialogue_context"])
    conversation_id = dialogue["conversation_id"]
    assert _mappings(dialogue["reference_groups"])[0]["receipt_ids"] == ["MAT-PRE-2026-00006"]
    persisted = json.loads((runtime / "agent-platform-state.json").read_text(encoding="utf-8"))
    assert "OFFLINE_FIXTURE_ASSISTANT_PROSE" not in json.dumps(persisted["dialogue_intent"])
    assert hashlib.sha256(ERP_V1.read_bytes()).hexdigest() == root_v1_hash

    try:
        restarted = build_frozen_receiving_dialogue_server(
            host="127.0.0.1",
            port=0,
            runtime_directory=runtime,
            erp_source=erp_v2,
            saas_source=saas,
            resume=True,
            runner=runner,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")

    restart_reads = restarted.frozen_erp_reader.read_count
    with _running(restarted) as base_url:
        restarted_responses = [
            _post(base_url, "/api/v1/agent-platform/ask", {"question": question})
            for question in after_questions
        ]

    assert len(runner.calls) == 6
    assert restarted.frozen_erp_reader.read_count > restart_reads
    assert restarted.frozen_erp_reader.last_snapshot.sha256 == root_v2_hash
    fifth_packet = runner.calls[4]["packet"]
    assert isinstance(fifth_packet, Mapping)
    assert fifth_packet["source"] == "frozen_read_only_fixture"
    sources = _mapping(_mapping(fifth_packet["tool_payload"])["sources"])
    assert (
        "Frozen file-backed read-only fixture"
        in _mapping(sources["read_control_context"])["fixture_provenance"]
    )
    candidates = _mapping(_mapping(sources["read_control_context"])["prior_reference_candidates"])
    assert candidates["status"] == "ONE_CANDIDATE"
    assert candidates["previous_receipt_ids"] == ["MAT-PRE-2026-00006"]
    stock_rows = [
        row
        for record in _mappings(_mapping(sources["read_erp_evidence"])["records"])
        for row in record.get("stock_entries", [])
        if row.get("voucher_no") == "MAT-PRE-2026-00006"
    ]
    assert [row["name"] for row in stock_rows] == ["FIXTURE-SLE-R3-PR6-RENAMED"]
    assert [row["actual_qty"] for row in stock_rows] == [1.0]
    assert "MAT-SLE-2026-00026" not in json.dumps(sources)
    fifth_prompt = runner.calls[4]["question"]
    assert isinstance(fifth_prompt, str)
    assert "OFFLINE_FIXTURE_ASSISTANT_PROSE" not in fifth_prompt
    final = restarted_responses[-1]
    assert _mapping(final["dialogue_context"])["conversation_id"] == conversation_id
    assert _mapping(final["human_intent"])["read_only_requested"] is True
    assert [request["question"] for request in _mappings(final["human_requests"])] == list(
        before_questions + after_questions
    )
    assert hashlib.sha256(ERP_V2.read_bytes()).hexdigest() == root_v2_hash


def test_unavailable_frozen_source_saves_human_request_without_runner_call(tmp_path: Path) -> None:
    erp_v1, _, saas = _source_paths(tmp_path)
    unavailable = json.loads(erp_v1.read_text(encoding="utf-8"))
    unavailable["status"] = "UNAVAILABLE"
    erp_v1.write_text(json.dumps(unavailable), encoding="utf-8")
    runner = OfflineFixtureRunner()
    try:
        server = build_frozen_receiving_dialogue_server(
            host="127.0.0.1",
            port=0,
            runtime_directory=tmp_path / "unavailable-runtime",
            erp_source=erp_v1,
            saas_source=saas,
            runner=runner,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")

    with _running(server) as base_url:
        response = _post(
            base_url,
            "/api/v1/agent-platform/ask",
            {"question": "Keep this read-only and show the current source status."},
        )

    advisory = _mapping(response["agent_advisory"])
    assert advisory["status"] == "SOURCE_UNAVAILABLE"
    assert advisory["mode"] == "not_invoked"
    assert runner.calls == []
    assert _mapping(response["human_intent"])["read_only_requested"] is True
    assert _mappings(response["human_requests"])[0]["question"] == (
        "Keep this read-only and show the current source status."
    )
    assert server.frozen_erp_reader.external_calls == server.frozen_saas_reader.external_calls == 0


def test_default_server_is_provider_unconfigured_without_a_fake_answer(tmp_path: Path) -> None:
    erp_v1, _, saas = _source_paths(tmp_path)
    try:
        server = build_frozen_receiving_dialogue_server(
            host="127.0.0.1",
            port=0,
            runtime_directory=tmp_path / "default-runtime",
            erp_source=erp_v1,
            saas_source=saas,
        )
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")

    assert server.agent_advisory.runtime_truth()["provider_configured"] is False
    assert server.automatic_investigation is not None
    assert server.automatic_investigation.current()["enabled"] is False
    with _running(server) as base_url:
        response = _post(
            base_url,
            "/api/v1/agent-platform/ask",
            {"question": "What does the frozen receipt source currently show?"},
        )

    advisory = _mapping(response["agent_advisory"])
    assert advisory["status"] == "AGENT_UNAVAILABLE"
    assert advisory["result"] is None
    assert "no fallback answer" in str(response["answer"])
    assert server.frozen_erp_reader.external_calls == server.frozen_saas_reader.external_calls == 0
