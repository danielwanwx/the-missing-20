from __future__ import annotations

from threading import Event, Thread
from typing import Any

import pytest

from the_missing_20.adapters import dialogue_intent
from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import (
    DashboardAdvisoryGateway,
    competition_investigation_packet,
)
from the_missing_20.agents.live_advisory import (
    AdvisoryDisposition,
    AdvisoryRun,
    LiveAdvisoryResult,
)
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentProvider


def test_dialogue_intent_has_stable_scoped_identity_and_preserves_refusal() -> None:
    state = dialogue_intent.record_request(
        {},
        "case-1",
        "I decline execution; inspect only.",
        "2026-09-09T00:00:00Z",
        runtime_instance_id="runtime-1",
    )
    conversation_id = state["conversation_id"]

    same_scope = dialogue_intent.record_request(
        state,
        "case-1",
        "What evidence is missing?",
        "2026-09-09T00:01:00Z",
        runtime_instance_id="runtime-1",
    )
    assert same_scope["schema_version"] == dialogue_intent.SCHEMA_VERSION
    assert same_scope["conversation_id"] == conversation_id
    assert same_scope["read_only_requested"] is True

    changed_case = dialogue_intent.record_request(
        same_scope,
        "case-2",
        "Continue the inspection.",
        "2026-09-09T00:02:00Z",
        runtime_instance_id="runtime-1",
    )
    assert changed_case["conversation_id"] != conversation_id
    assert changed_case["case_id"] == "case-2"
    assert changed_case.get("read_only_requested") is not True

    restarted = dialogue_intent.restore_state(
        changed_case, case_id="case-2", runtime_instance_id="runtime-1"
    )
    assert restarted["conversation_id"] == changed_case["conversation_id"]


def test_explicit_new_conversation_changes_context_without_clearing_authority() -> None:
    state = dialogue_intent.record_request(
        {},
        "case-1",
        "Do not execute anything.",
        "2026-09-09T00:00:00Z",
        runtime_instance_id="runtime-1",
    )
    old_id = state["conversation_id"]
    restarted = dialogue_intent.record_request(
        state,
        "case-1",
        "Start a new conversation about this case.",
        "2026-09-09T00:01:00Z",
        runtime_instance_id="runtime-1",
        new_conversation=True,
    )
    assert restarted["conversation_id"] != old_id
    assert restarted["read_only_requested"] is True
    assert restarted["requests"][-1]["question"] == "Start a new conversation about this case."


def test_legacy_or_invalid_state_is_conservative_and_never_restores_answer_prose() -> None:
    legacy = {
        "case_id": "case-1",
        "read_only_requested": True,
        "constraint_question": "Only inspect evidence.",
        "requests": [{"request_id": "old-1", "question": "Old question", "created_at": "t1"}],
        "conversation": [
            {
                "question": "Old question",
                "answer": "STALE_AGENT_EXPLANATION",
                "receipt_ids": ["PR1"],
            }
        ],
    }
    restored = dialogue_intent.restore_state(
        legacy, case_id="case-1", runtime_instance_id="runtime-1"
    )
    assert restored["schema_version"] == dialogue_intent.SCHEMA_VERSION
    assert restored["read_only_requested"] is True
    assert restored["requests"][0]["question"] == "Old question"
    assert "conversation" not in restored
    assert "STALE_AGENT_EXPLANATION" not in str(restored)

    invalid = dialogue_intent.restore_state(
        {"schema_version": "future/v99", "case_id": "case-1", "conversation_id": "old"},
        case_id="case-1",
        runtime_instance_id="runtime-1",
        authority_state={"read_only_requested": True, "constraint_question": "Only inspect."},
    )
    assert invalid["conversation_id"] != "old"
    assert invalid["read_only_requested"] is True


def test_unsupported_schema_drops_foreign_runtime_requests_references_and_authority() -> None:
    foreign = dialogue_intent.record_request(
        {},
        "case-1",
        "FOREIGN ORIGINAL REQUEST: decline execution.",
        "t1",
        runtime_instance_id="foreign-runtime",
    )
    foreign = dialogue_intent.record_reference_group(
        foreign,
        case_id="case-1",
        question="FOREIGN ORIGINAL REQUEST: decline execution.",
        receipt_ids=["PR-FOREIGN"],
        validated=True,
        at="t1",
        runtime_instance_id="foreign-runtime",
    )
    foreign["schema_version"] = "future/v99"

    restored = dialogue_intent.restore_state(
        foreign, case_id="case-1", runtime_instance_id="current-runtime"
    )
    trusted = dialogue_intent.restore_state(
        foreign,
        case_id="case-1",
        runtime_instance_id="current-runtime",
        authority_state={
            "read_only_requested": True,
            "constraint_question": "Current operator keeps this read-only.",
        },
    )

    assert restored["requests"] == []
    assert restored["reference_groups"] == []
    assert restored.get("read_only_requested") is not True
    assert trusted["read_only_requested"] is True
    assert trusted["constraint_question"] == "Current operator keeps this read-only."


def test_same_runtime_unsupported_schema_keeps_only_application_refusal() -> None:
    state = dialogue_intent.record_request(
        {},
        "case-1",
        "I decline execution; inspect PR-20 only.",
        "t1",
        runtime_instance_id="runtime-1",
    )
    old_conversation_id = state["conversation_id"]
    state = dialogue_intent.record_reference_group(
        state,
        case_id="case-1",
        question="I decline execution; inspect PR-20 only.",
        receipt_ids=["PR-20"],
        validated=True,
        at="t1",
        runtime_instance_id="runtime-1",
    )
    state["schema_version"] = "corrupt/context"

    restored = dialogue_intent.restore_state(
        state, case_id="case-1", runtime_instance_id="runtime-1"
    )

    assert restored["conversation_id"] != old_conversation_id
    assert restored["requests"] == []
    assert restored["reference_groups"] == []
    assert restored["read_only_requested"] is True
    assert restored["constraint_question"] == "I decline execution; inspect PR-20 only."


def test_unversioned_legacy_migrates_only_when_runtime_is_absent_or_matches() -> None:
    legacy = {
        "case_id": "case-1",
        "read_only_requested": True,
        "constraint_question": "Inspect only.",
        "requests": [
            {"request_id": "legacy-1", "question": "Original legacy question", "created_at": "t1"}
        ],
    }
    same_runtime_legacy = {**legacy, "runtime_instance_id": "runtime-1"}
    foreign_runtime_legacy = {**legacy, "runtime_instance_id": "foreign-runtime"}

    restored = dialogue_intent.restore_state(
        legacy, case_id="case-1", runtime_instance_id="runtime-1"
    )
    same_runtime = dialogue_intent.restore_state(
        same_runtime_legacy, case_id="case-1", runtime_instance_id="runtime-1"
    )
    rejected = dialogue_intent.restore_state(
        foreign_runtime_legacy, case_id="case-1", runtime_instance_id="runtime-1"
    )

    assert restored["requests"][0]["question"] == "Original legacy question"
    assert restored["read_only_requested"] is True
    assert same_runtime["requests"][0]["question"] == "Original legacy question"
    assert same_runtime["read_only_requested"] is True
    assert rejected["requests"] == []
    assert rejected.get("read_only_requested") is not True


def test_requests_are_original_whole_messages_and_bounded_at_twelve() -> None:
    state: dict[str, Any] = {}
    questions = [
        f"request-{index}-" + ("x" * (500 - len(f"request-{index}-"))) for index in range(14)
    ]
    for index, question in enumerate(questions):
        state = dialogue_intent.record_request(
            state,
            "case-1",
            question,
            f"2026-09-09T00:{index:02d}:00Z",
            runtime_instance_id="runtime-1",
        )
    assert len(state["requests"]) == 12
    assert [row["question"] for row in state["requests"]] == questions[-12:]
    assert state["requests_omitted"] == 2
    assert all(len(row["question"]) == 500 for row in state["requests"])


def test_context_budget_omits_whole_old_requests_and_keeps_current_question_whole() -> None:
    requests = [
        {"request_id": f"r-{index}", "question": f"q{index}-" + ("x" * 495), "created_at": "t"}
        for index in range(12)
    ]
    current = "current question: " + ("y" * 470)
    packed = dialogue_intent.build_model_context(
        requests,
        current_question=current,
        authority_context="Retained read-only constraint remains active.",
        max_chars=4000,
    )
    assert len(packed["prompt"]) <= 4000
    assert packed["prompt"].endswith(current)
    assert packed["omitted_requests"] > 0
    for row in requests:
        assert (
            row["question"] not in packed["prompt"]
            or row["question"] in packed["included_questions"]
        )
    assert "x" * 100 not in packed["prompt"] or packed["included_questions"]


def test_gateway_rejects_raw_over_limit_whitespace_before_persistence() -> None:
    class Platform:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def current(self) -> dict[str, object]:
            return {"case_id": "case-1"}

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            del case_id, new_conversation
            self.requests.append(question)
            return {}

    platform = Platform()
    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=lambda *args, **kwargs: pytest.fail("over-limit input must not invoke the model"),
    ).ask("Inspect PR-20" + (" " * 490))

    assert response["agent_advisory"]["status"] == "VALIDATION_FAILED"
    assert platform.requests == []


def test_gateway_keeps_original_bounded_user_wording() -> None:
    prompts: list[str] = []

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args
        prompts.append(kwargs["question"])
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=("control-context",),
                reason="Inspect current evidence.",
                safe_next_step="Inspect only.",
                write_performed=False,
            ),
            tool_calls=(),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    question = "Inspect  PR-20\twithout execution."
    platform = AmbiguousCasePlatform()
    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    ).ask(question)

    assert response["agent_advisory"]["status"] == "COMPLETE"
    assert platform.current()["human_requests"][-1]["question"] == question
    assert prompts == [question]


def test_gateway_reports_persisted_and_prompt_budget_omissions() -> None:
    class Platform:
        def __init__(self) -> None:
            self.state: dict[str, object] = {}
            for index in range(14):
                question = f"old-{index}:" + ("x" * (500 - len(f"old-{index}:")))
                self.state = dialogue_intent.record_request(
                    self.state,
                    "case-1",
                    question,
                    f"2026-09-09T00:{index:02d}:00Z",
                    runtime_instance_id="test-runtime",
                )

        def current(self) -> dict[str, object]:
            return {
                "case_id": "case-1",
                **dialogue_intent.public_state(
                    self.state, "case-1", runtime_instance_id="test-runtime"
                ),
            }

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            self.state = dialogue_intent.record_request(
                self.state,
                case_id,
                question,
                "2026-09-09T01:00:00Z",
                runtime_instance_id="test-runtime",
                new_conversation=new_conversation,
            )
            return dialogue_intent.public_state(
                self.state, case_id, runtime_instance_id="test-runtime"
            )

        def record_conversation_turn(
            self,
            question: str,
            answer: str,
            advisory: dict[str, object],
            *,
            expected_case_id: str = "",
            expected_conversation_id: str = "",
        ) -> dict[str, object]:
            del question, answer, advisory, expected_case_id, expected_conversation_id
            return self.current()

    prompts: list[str] = []

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args
        prompts.append(kwargs["question"])
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=("control-context",),
                reason="Inspect current evidence.",
                safe_next_step="Inspect only.",
                write_performed=False,
            ),
            tool_calls=(),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    current_question = "Newest request: " + ("y" * 480)
    response = DashboardAdvisoryGateway(
        Platform(),
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=lambda projection: {"case_id": projection["case_id"]},
    ).ask(current_question)

    assert len(prompts[0]) <= 4000
    assert prompts[0].endswith(current_question)
    assert response["agent_advisory"]["context_turns"] < 12
    assert response["agent_advisory"]["omitted_turns"] > 3


def test_reference_group_is_latest_validated_group_and_survives_no_reference_turns() -> None:
    state = dialogue_intent.record_request(
        {}, "case-1", "Inspect PR1", "t1", runtime_instance_id="runtime-1"
    )
    state = dialogue_intent.record_reference_group(
        state,
        case_id="case-1",
        question="Inspect PR1",
        receipt_ids=["PR1", "PR2"],
        validated=True,
        at="t1",
    )
    state = dialogue_intent.record_request(
        state, "case-1", "What about the invoice?", "t2", runtime_instance_id="runtime-1"
    )
    assert dialogue_intent.latest_reference_group(state)["receipt_ids"] == ["PR1", "PR2"]

    state = dialogue_intent.record_reference_group(
        state,
        case_id="case-1",
        question="Inspect PR3",
        receipt_ids=["PR3"],
        validated=True,
        at="t3",
    )
    assert dialogue_intent.latest_reference_group(state)["receipt_ids"] == ["PR3"]
    failed = dialogue_intent.record_reference_group(
        state,
        case_id="case-1",
        question="Maybe PR4",
        receipt_ids=["PR4"],
        validated=False,
        at="t4",
    )
    assert dialogue_intent.latest_reference_group(failed)["receipt_ids"] == ["PR3"]


def test_reference_rejoin_retains_missing_and_ambiguous_status() -> None:
    group = {
        "case_id": "case-1",
        "receipt_ids": ["PR1", "PR2"],
        "question": "Inspect both receipts",
        "provenance": "runtime_validated",
    }
    changed = dialogue_intent.rejoin_reference_group(
        group, case_id="case-1", current_receipt_ids=["PR1"]
    )
    assert changed["status"] == "CHANGED"
    assert changed["current_receipt_ids"] == ["PR1"]
    assert changed["missing_receipt_ids"] == ["PR2"]

    ambiguous = dialogue_intent.rejoin_reference_group(
        {**group, "receipt_ids": ["PR1"]},
        case_id="case-1",
        current_receipt_ids=["PR1", "PR1"],
    )
    assert ambiguous["status"] == "AMBIGUOUS"


def test_gateway_uses_stable_id_and_user_only_history_after_restart() -> None:
    prompts: list[str] = []

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args
        prompts.append(kwargs["question"])
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.RECOVERY_READY,
                evidence_ids=("PR1",),
                reason="UNTRUSTED_AGENT_EXPLANATION",
                safe_next_step="Inspect current evidence.",
                write_performed=False,
            ),
            tool_calls=("read_control_context", "read_erp_evidence"),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    gateway = DashboardAdvisoryGateway(
        AmbiguousCasePlatform(),
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    )
    first = gateway.ask("Which ERP key is missing?")
    second = gateway.ask("Does that explain all twenty units?")
    assert first["agent_advisory"]["conversation_id"] == second["agent_advisory"]["conversation_id"]
    assert "UNTRUSTED_AGENT_EXPLANATION" not in prompts[1]
    assert "Evidence Agent:" not in prompts[1]
    assert "Which ERP key is missing?" in prompts[1]
    assert second["agent_advisory"]["context_turns"] == 1


def test_persisted_ambiguous_platform_restores_six_turn_user_only_context(tmp_path) -> None:
    prompts: list[str] = []

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args
        prompts.append(kwargs["question"])
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=("control-context",),
                reason="ASSISTANT_STALE_PROSE must not become recoverable context.",
                safe_next_step="Inspect only.",
                write_performed=False,
            ),
            tool_calls=("read_control_context", "read_erp_evidence"),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    path = tmp_path / "case.db"
    first_platform = AmbiguousCasePlatform(store_path=path)
    first_gateway = DashboardAdvisoryGateway(
        first_platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    )
    questions = [
        "I decline execution; inspect evidence only.",
        "Which current records should I inspect?",
        "Does PR-20 appear in the current ledger?",
        "Which source is missing a receipt?",
        "What remains unresolved in the current evidence?",
        "What should I inspect next without execution?",
    ]
    responses = [first_gateway.ask(question) for question in questions]
    case_id = str(first_platform.current()["case_id"])
    first_platform.record_conversation_turn(
        questions[2],
        "ASSISTANT_STALE_PROSE must not be restored.",
        {
            "dialogue_reference_group": {
                "case_id": case_id,
                "question": questions[2],
                "receipt_ids": ["PR-20"],
                "provenance": "runtime_validated",
            }
        },
    )
    before_restart = first_platform.current()

    restarted_platform = AmbiguousCasePlatform(store_path=path)
    restarted_gateway = DashboardAdvisoryGateway(
        restarted_platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    )
    restarted = restarted_gateway.ask("What remains unresolved after the restart?")
    restarted_context = restarted_platform.current()["dialogue_context"]

    assert (
        restarted["agent_advisory"]["conversation_id"]
        == responses[0]["agent_advisory"]["conversation_id"]
    )
    assert before_restart["human_requests"] == restarted_platform.current()["human_requests"][:6]
    assert [row["question"] for row in before_restart["human_requests"]] == questions
    assert restarted_platform.current()["human_intent"]["read_only_requested"] is True
    assert dialogue_intent.latest_reference_group(restarted_context, case_id=case_id)[
        "receipt_ids"
    ] == ["PR-20"]
    assert "ASSISTANT_STALE_PROSE" not in str(restarted_context)
    assert "ASSISTANT_STALE_PROSE" not in prompts[-1]
    assert "Evidence Agent:" not in prompts[-1]
    assert questions[0] in prompts[-1]
    assert questions[-1] in prompts[-1]


def test_agent_platform_restores_six_turn_user_only_reference_context(tmp_path) -> None:
    from test_agent_platform import _erp, _Reader, _saas

    from the_missing_20.adapters.agent_platform import AgentPlatform

    path = tmp_path / "agent-platform.json"
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()), state_path=path)
    case_id = str(platform.current()["case_id"])
    questions = [
        "I decline execution; inspect evidence only.",
        "Which current records should I inspect?",
        "Inspect PR-20 in the current ERP evidence.",
        "Does the current receipt explain the hold?",
        "Which source remains unresolved?",
        "What should I inspect next without execution?",
    ]
    for question in questions:
        platform.record_human_request(question, case_id)
    before = platform.current()["dialogue_context"]
    platform.record_conversation_turn(
        questions[2],
        "UNTRUSTED_AGENT_EXPLANATION",
        {
            "dialogue_reference_group": {
                "case_id": case_id,
                "question": questions[2],
                "receipt_ids": ["PR-20"],
                "provenance": "runtime_validated",
            }
        },
    )
    restarted = AgentPlatform(_Reader(_erp()), _Reader(_saas()), state_path=path).current()
    context = restarted["dialogue_context"]

    assert context["runtime_instance_id"] == before["runtime_instance_id"]
    assert context["conversation_id"] == before["conversation_id"]
    assert [row["question"] for row in restarted["human_requests"]] == questions
    assert restarted["human_intent"]["read_only_requested"] is True
    assert dialogue_intent.latest_reference_group(context, case_id=case_id)["receipt_ids"] == [
        "PR-20"
    ]
    assert "UNTRUSTED_AGENT_EXPLANATION" not in str(context)


def test_gateway_stops_when_the_case_changes_between_fresh_reads() -> None:
    class Platform:
        def __init__(self) -> None:
            self.case_id = "case-a"
            self.recorded: list[tuple[str, str]] = []

        def current(self) -> dict[str, object]:
            return {"case_id": self.case_id}

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            del new_conversation
            self.recorded.append((case_id, question))
            self.case_id = "case-b"
            return {}

    platform = Platform()
    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=lambda *args, **kwargs: pytest.fail("scope change must not invoke the model"),
    ).ask("Inspect the current receipt.")

    assert response["agent_advisory"]["status"] == "CONTEXT_SCOPE_CHANGED"
    assert platform.recorded == [("case-a", "Inspect the current receipt.")]


def test_gateway_discards_completion_after_case_changes_during_model_run() -> None:
    class Platform:
        def __init__(self) -> None:
            self.case_id = "case-a"
            self.state: dict[str, object] = {}
            self.recorded_turns: list[str] = []

        def current(self) -> dict[str, object]:
            return {
                "case_id": self.case_id,
                **dialogue_intent.public_state(
                    self.state, self.case_id, runtime_instance_id="test-runtime"
                ),
            }

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            self.state = dialogue_intent.record_request(
                self.state,
                case_id,
                question,
                "now",
                runtime_instance_id="test-runtime",
                new_conversation=new_conversation,
            )
            return dialogue_intent.public_state(
                self.state, case_id, runtime_instance_id="test-runtime"
            )

        def record_conversation_turn(
            self,
            question: str,
            answer: str,
            advisory: dict[str, object],
            *,
            expected_case_id: str = "",
            expected_conversation_id: str = "",
        ) -> dict[str, object]:
            del answer, advisory, expected_case_id, expected_conversation_id
            self.recorded_turns.append(question)
            return self.current()

    platform = Platform()

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args, kwargs
        platform.case_id = "case-b"
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=("control-context",),
                reason="This completion belongs to case A.",
                safe_next_step="Inspect only.",
                write_performed=False,
            ),
            tool_calls=(),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=lambda projection: {"case_id": projection["case_id"]},
    ).ask("Inspect the current receipt.")

    assert response["agent_advisory"]["status"] == "CONTEXT_SCOPE_CHANGED"
    assert response["case_id"] == "case-b"
    assert platform.recorded_turns == []
    assert "This completion belongs to case A." not in response["answer"]


def test_gateway_serializes_same_instance_and_second_turn_uses_fresh_context() -> None:
    runner_started = Event()
    allow_first_runner_to_finish = Event()
    second_current_during_runner = Event()
    prompts: list[str] = []
    results: list[dict[str, object]] = []

    class Platform:
        def __init__(self) -> None:
            self.state: dict[str, object] = {}

        def current(self) -> dict[str, object]:
            if runner_started.is_set():
                second_current_during_runner.set()
            return {
                "case_id": "case-1",
                **dialogue_intent.public_state(
                    self.state, "case-1", runtime_instance_id="test-runtime"
                ),
            }

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            self.state = dialogue_intent.record_request(
                self.state,
                case_id,
                question,
                "now",
                runtime_instance_id="test-runtime",
                new_conversation=new_conversation,
            )
            return dialogue_intent.public_state(
                self.state, case_id, runtime_instance_id="test-runtime"
            )

        def record_conversation_turn(
            self,
            question: str,
            answer: str,
            advisory: dict[str, object],
            *,
            expected_case_id: str = "",
            expected_conversation_id: str = "",
        ) -> dict[str, object]:
            del question, answer, advisory, expected_case_id, expected_conversation_id
            return self.current()

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args
        prompts.append(kwargs["question"])
        if len(prompts) == 1:
            runner_started.set()
            assert allow_first_runner_to_finish.wait(timeout=1)
            runner_started.clear()
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.SAFE_NOOP,
                evidence_ids=("control-context",),
                reason="Inspect current evidence.",
                safe_next_step="Inspect only.",
                write_performed=False,
            ),
            tool_calls=(),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    gateway = DashboardAdvisoryGateway(
        Platform(),
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=lambda projection: {"case_id": projection["case_id"]},
    )
    first = Thread(target=lambda: results.append(gateway.ask("First request.")))
    first.start()
    assert runner_started.wait(timeout=1)
    second = Thread(target=lambda: results.append(gateway.ask("Second request.")))
    second.start()
    assert not second_current_during_runner.wait(timeout=0.1)
    allow_first_runner_to_finish.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive() and not second.is_alive()
    assert len(results) == 2
    assert "Prior conversation:" in prompts[1]
    assert "First request." in prompts[1]
    assert "Second request." in prompts[1]


def test_gateway_persists_failed_request_without_candidate_or_model_answer() -> None:
    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        del args, kwargs
        raise RuntimeError("provider unavailable")

    platform = AmbiguousCasePlatform()
    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=AgentProvider.BEDROCK),
        runner=runner,
        packet_factory=competition_investigation_packet,
    ).ask("Do not execute; inspect PR1 only.")
    assert response["agent_advisory"]["status"] == "AGENT_UNAVAILABLE"
    current = platform.current()
    assert current["human_requests"][-1]["question"] == "Do not execute; inspect PR1 only."
    assert not current["conversation"]
    assert "STALE" not in str(current)


@pytest.mark.parametrize("provider", [AgentProvider.SCRIPTED, AgentProvider.BEDROCK])
def test_source_unavailable_does_not_drop_user_request(provider: AgentProvider) -> None:
    class Platform:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def current(self) -> dict[str, object]:
            return {
                "case_id": "case-1",
                "source_freshness": {"status": "UNAVAILABLE"},
                "human_requests": [{"question": value} for value in self.requests],
            }

        def record_human_request(
            self, question: str, case_id: str, *, new_conversation: bool = False
        ) -> dict[str, object]:
            del case_id, new_conversation
            self.requests.append(question)
            return {"human_requests": [{"question": value} for value in self.requests]}

    platform = Platform()
    response = DashboardAdvisoryGateway(
        platform,
        settings=Settings(agent_provider=provider),
        runner=lambda *args, **kwargs: pytest.fail("source outage must not invoke model"),
    ).ask("What evidence is current?")
    assert response["agent_advisory"]["status"] == "SOURCE_UNAVAILABLE"
    assert platform.requests == ["What evidence is current?"]
