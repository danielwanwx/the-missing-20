from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError

import pytest

from scripts.diagnostics import verify_receiving_conversation as probe

CASE_ID = "M20-RECEIVING-TEST"
QUANTITIES = {"ordered": 40, "received": 2, "outstanding_order_quantity": 38}


def _projection(
    *,
    conversation_id: str = "conversation-1",
    questions: tuple[str, ...] = (),
    requests_omitted: int = 0,
    case_id: str = CASE_ID,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_identity": {"provider": "ERPNext", "record_id": "safe-record"},
        "source_digests": {"erp": "digest-erp", "saas": "digest-saas"},
        "source_freshness": {"status": "CURRENT", "scope": "erp_case_documents"},
        "case_projection": {
            "source_sequence": 12,
            "case": {"quantities": dict(QUANTITIES)},
        },
        "dialogue_context": {
            "schema_version": probe.PERSISTED_CONTEXT_SCHEMA,
            "runtime_instance_id": "runtime-1",
            "case_id": case_id,
            "conversation_id": conversation_id,
            "requests_omitted": requests_omitted,
        },
        "human_requests": [
            {
                "request_id": f"request-{index}",
                "question": question,
                "created_at": f"2026-09-09T00:00:{index:02d}Z",
            }
            for index, question in enumerate(questions)
        ],
    }


class FixtureGateway:
    def __init__(
        self,
        questions: tuple[str, ...],
        *,
        context_turns: tuple[int, ...] | None = None,
        omitted_turns: tuple[int, ...] | None = None,
        conversation_ids: tuple[str, ...] | None = None,
        case_ids: tuple[str, ...] | None = None,
        attachments: object = None,
        fresh_baseline: bool = False,
    ) -> None:
        self.questions = questions
        self.context_turns = context_turns or tuple(range(len(questions)))
        self.omitted_turns = omitted_turns or (0,) * len(questions)
        self.conversation_ids = conversation_ids or ("conversation-1",) * len(questions)
        self.case_ids = case_ids or (CASE_ID,) * len(questions)
        self.attachments = attachments
        self.fresh_baseline = fresh_baseline
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []
        self.index = 0
        self.latest = _projection()

    def __call__(self, path: str, payload: Mapping[str, object] | None) -> object:
        self.calls.append((path, payload))
        if path == "/api/v1/agent-platform":
            if self.index:
                return self.latest
            if self.fresh_baseline:
                return {**_projection(), "dialogue_context": {}, "human_requests": []}
            return _projection()
        if path != "/api/v1/agent-platform/ask":
            raise AssertionError(f"unexpected path: {path}")
        assert payload is not None
        assert payload["question"] == self.questions[self.index]
        conversation_id = self.conversation_ids[self.index]
        response_projection = _projection(
            conversation_id=conversation_id,
            questions=self.questions[: self.index + 1],
            case_id=self.case_ids[self.index],
        )
        self.latest = response_projection
        response = {
            **response_projection,
            "answer": f"answer-{self.index + 1}",
            "agent_advisory": {
                "status": "COMPLETE",
                "mode": "real_strands",
                "conversation_id": conversation_id,
                "context_turns": self.context_turns[self.index],
                "omitted_turns": self.omitted_turns[self.index],
                "usage": {"request_count": 1, "cost_usd": 0.01},
                "result": {"write_performed": False, "disposition": "SAFE_NOOP"},
                **({"attachments": self.attachments} if self.attachments is not None else {}),
            },
        }
        self.index += 1
        return response


def _run(
    tmp_path: Path, gateway: probe.RequestCallback, questions: tuple[str, ...]
) -> dict[str, object]:
    return probe.run_diagnostic(
        case_id=CASE_ID,
        output=tmp_path / "diagnostic.json",
        questions=questions,
        request_callback=gateway,
    )


def test_http_failure_retains_safe_body_costs_and_marks_remaining_not_reached(
    tmp_path: Path,
) -> None:
    questions = ("first question", "second question", "third question")
    calls: list[str] = []

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        calls.append(path)
        if path == "/api/v1/agent-platform":
            return _projection()
        raise probe.GatewayRequestError(
            "http",
            "HTTP 502 from ask",
            status_code=502,
            body={
                "error": {"code": "provider_timeout", "secret": "provider-secret"},
                "usage": {"request_count": 1, "cost_usd": 0.37},
            },
            usage={"request_count": 1, "cost_usd": 0.37},
        )

    report = probe.run_diagnostic(
        case_id=CASE_ID,
        output=tmp_path / "failure.json",
        questions=questions,
        request_callback=callback,
    )

    assert report["status"] == "RUNTIME_FAILED"
    assert calls == ["/api/v1/agent-platform", "/api/v1/agent-platform/ask"]
    turns = report["turns"]
    assert isinstance(turns, list)
    assert [turn["status"] for turn in turns] == [
        "RUNTIME_FAILED",
        "NOT_REACHED",
        "NOT_REACHED",
    ]
    first_turn = cast(Any, turns[0])
    assert first_turn["usage"] == {"request_count": 1, "cost_usd": 0.37}
    assert first_turn["error"]["body"]["error"]["secret"] == "[REDACTED]"
    assert "provider-secret" not in json.dumps(report)


def test_existing_output_is_exclusive_and_causes_no_request(tmp_path: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("keep this", encoding="utf-8")
    calls: list[str] = []

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        calls.append(path)
        raise AssertionError("request callback must not run")

    with pytest.raises(FileExistsError):
        probe.run_diagnostic(
            case_id=CASE_ID,
            output=output,
            questions=("question",),
            request_callback=callback,
        )
    assert calls == []
    assert output.read_text(encoding="utf-8") == "keep this"


def test_raw_question_over_500_is_rejected_before_request(tmp_path: Path) -> None:
    calls: list[str] = []

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        calls.append(path)
        raise AssertionError("request callback must not run")

    with pytest.raises(ValueError, match="500-character raw limit"):
        probe.run_diagnostic(
            case_id=CASE_ID,
            output=tmp_path / "too-long.json",
            questions=("x" * 501,),
            request_callback=callback,
        )
    assert calls == []


def test_more_than_three_context_turns_are_recorded_without_a_cap(tmp_path: Path) -> None:
    questions = tuple(f"question-{index}" for index in range(4))
    gateway = FixtureGateway(questions)
    report = _run(tmp_path, gateway, questions)

    assert report["status"] == "COMPLETE"
    turns = report["turns"]
    assert isinstance(turns, list)
    assert [turn["status"] for turn in turns] == ["COMPLETE"] * 4
    assert [cast(Any, turn)["response"]["agent_advisory"]["context_turns"] for turn in turns] == [
        0,
        1,
        2,
        3,
    ]
    report_view = cast(Any, report)
    assert report_view["baseline"]["source_identity"]["provider"] == "ERPNext"
    assert report_view["final"]["quantities"] == QUANTITIES
    assert stat.S_IMODE((tmp_path / "diagnostic.json").stat().st_mode) == 0o600
    assert "passed" not in report
    assert report_view["semantic_review"]["status"] == "PENDING"


def test_fresh_baseline_without_persisted_context_is_allowed(tmp_path: Path) -> None:
    questions = ("first question",)
    report = _run(tmp_path, FixtureGateway(questions, fresh_baseline=True), questions)

    assert report["status"] == "COMPLETE"
    assert (
        cast(Any, report)["baseline"]["runtime_checks"]["fresh_baseline_context"]["status"]
        == "PASS"
    )


def test_omitted_context_is_recorded_and_checked_against_persisted_state(tmp_path: Path) -> None:
    questions = ("q1", "q2", "q3")
    gateway = FixtureGateway(
        questions,
        context_turns=(0, 1, 0),
        omitted_turns=(0, 0, 2),
    )
    report = _run(tmp_path, gateway, questions)

    assert report["status"] == "COMPLETE"
    turns = report["turns"]
    assert isinstance(turns, list)
    assert (
        cast(Any, turns[2])["runtime_checks"]["context_matches_persisted_state"]["status"] == "PASS"
    )


def test_missing_persisted_requests_cannot_make_impossible_context_complete(tmp_path: Path) -> None:
    questions = tuple(f"question-{index}" for index in range(4))
    gateway = FixtureGateway(questions, context_turns=(99, 99, 99, 99))

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        value = gateway(path, payload)
        if isinstance(value, Mapping):
            value = dict(value)
            value.pop("human_requests", None)
        return value

    report = _run(tmp_path, callback, questions)

    assert report["status"] == "RUNTIME_FAILED"
    assert [path for path, _payload in gateway.calls] == ["/api/v1/agent-platform"]
    turns = cast(Any, report)["turns"]
    assert [turn["status"] for turn in turns] == ["NOT_REACHED"] * len(questions)


def test_malformed_requests_omitted_cannot_finish_green(tmp_path: Path) -> None:
    questions = ("question",)
    gateway = FixtureGateway(questions)

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        value = gateway(path, payload)
        if path == "/api/v1/agent-platform/ask":
            value = dict(cast(Mapping[str, object], value))
            context = dict(cast(Mapping[str, object], value["dialogue_context"]))
            context["requests_omitted"] = "unknown"
            value["dialogue_context"] = context
        return value

    report = _run(tmp_path, callback, questions)

    assert report["status"] == "RUNTIME_FAILED"
    assert (
        cast(Any, report)["turns"][0]["runtime_checks"]["dialogue_context_requests_omitted"][
            "status"
        ]
        == "FAIL"
    )


def test_dishonest_context_count_cannot_finish_green(tmp_path: Path) -> None:
    questions = ("question",)
    gateway = FixtureGateway(questions, context_turns=(99,))
    report = _run(tmp_path, gateway, questions)

    assert report["status"] == "RUNTIME_FAILED"
    assert (
        cast(Any, report)["turns"][0]["runtime_checks"]["context_matches_persisted_state"]["status"]
        == "FAIL"
    )


def test_saved_current_question_must_match_original_request(tmp_path: Path) -> None:
    questions = ("question",)
    gateway = FixtureGateway(questions)

    def callback(path: str, payload: Mapping[str, object] | None) -> object:
        value = gateway(path, payload)
        if path == "/api/v1/agent-platform/ask":
            value = dict(cast(Mapping[str, object], value))
            requests = list(cast(list[object], value["human_requests"]))
            requests[-1] = {**cast(Mapping[str, object], requests[-1]), "question": "other"}
            value["human_requests"] = requests
        return value

    report = _run(tmp_path, callback, questions)

    assert report["status"] == "RUNTIME_FAILED"
    assert (
        cast(Any, report)["turns"][0]["runtime_checks"]["saved_current_question_exact"]["status"]
        == "FAIL"
    )


@pytest.mark.parametrize(
    ("case_ids", "conversation_ids", "expected_check"),
    [
        (("wrong-case",), ("conversation-1",), "case_id_exact"),
        ((CASE_ID, CASE_ID), ("conversation-1", "conversation-2"), "conversation_id_stable"),
    ],
)
def test_case_or_conversation_mismatch_cannot_finish_green(
    tmp_path: Path,
    case_ids: tuple[str, ...],
    conversation_ids: tuple[str, ...],
    expected_check: str,
) -> None:
    questions = ("q1",) if len(case_ids) == 1 else ("q1", "q2", "q3")
    gateway = FixtureGateway(
        questions,
        case_ids=case_ids,
        conversation_ids=conversation_ids,
    )
    report = _run(tmp_path, gateway, questions)

    assert report["status"] == "RUNTIME_FAILED"
    turns = report["turns"]
    assert isinstance(turns, list)
    failed_turn = next(
        cast(Any, turn) for turn in turns if cast(Any, turn)["status"] == "RUNTIME_FAILED"
    )
    assert failed_turn["runtime_checks"][expected_check]["status"] == "FAIL"
    assert "passed" not in report


def test_history_attachment_is_optional_by_default(tmp_path: Path) -> None:
    questions = ("question",)
    report = _run(tmp_path, FixtureGateway(questions), questions)
    assert report["status"] == "COMPLETE"


def test_history_attachment_can_be_required_explicitly(tmp_path: Path) -> None:
    questions = ("question",)
    gateway = FixtureGateway(questions)
    report = probe.run_diagnostic(
        case_id=CASE_ID,
        output=tmp_path / "required.json",
        questions=questions,
        request_callback=gateway,
        require_history_attachment=True,
    )
    assert report["status"] == "RUNTIME_FAILED"
    assert (
        cast(Any, report["turns"])[0]["runtime_checks"]["history_attachment_present"]["status"]
        == "FAIL"
    )


def test_expected_conversation_id_mismatch_stops_segment(tmp_path: Path) -> None:
    questions = ("question", "unreached")
    gateway = FixtureGateway(questions)
    report = probe.run_diagnostic(
        case_id=CASE_ID,
        output=tmp_path / "expected-id.json",
        questions=questions,
        request_callback=gateway,
        expected_conversation_id="conversation-expected",
    )
    assert report["status"] == "RUNTIME_FAILED"
    assert [path for path, _payload in gateway.calls] == ["/api/v1/agent-platform"]


def test_request_json_catches_http_body_and_preserves_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorResponse:
        def read(self, _limit: int) -> bytes:
            return json.dumps({"usage": {"cost_usd": 0.42}, "secret": "do-not-write"}).encode()

        def close(self) -> None:
            return None

    error = HTTPError(
        "http://127.0.0.1:1",
        503,
        "unavailable",
        cast(Any, {}),
        cast(Any, ErrorResponse()),
    )
    monkeypatch.setattr(probe, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(probe.GatewayRequestError) as caught:
        probe.request_json("http://127.0.0.1:1", "/api/v1/agent-platform/ask", {"question": "q"})
    assert caught.value.status_code == 503
    assert caught.value.usage == {"cost_usd": 0.42}
    assert cast(Any, caught.value.body)["secret"] == "[REDACTED]"
