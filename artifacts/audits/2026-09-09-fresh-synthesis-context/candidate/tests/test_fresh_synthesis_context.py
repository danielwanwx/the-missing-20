"""Offline contracts for the diagnostic fresh-synthesis context boundary."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import pytest
import strands
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from strands.models import BedrockModel

from scripts.diagnostics import probe_fresh_synthesis_context as probe
from the_missing_20.adapters.investigation_case_sources import (
    Variant,
    correlate_investigation_sources,
    investigation_packet,
)
from the_missing_20.agents import live_advisory as advisory
from the_missing_20.agents.fresh_synthesis_context import (
    FreshSynthesisContextError,
    build_fresh_synthesis_context,
)
from the_missing_20.agents.live_advisory import (
    CORRELATION_TOOL_NAME,
    POLICY_TOOL_NAME,
    SOURCE_TOOL_NAMES,
    AdvisoryDisposition,
    LiveAdvisoryResult,
    model_source_payloads,
    run_fresh_synthesis_context_diagnostic,
    run_live_advisory,
)

REQUIRED_TOOLS = SOURCE_TOOL_NAMES + (CORRELATION_TOOL_NAME,)
PRIVATE_CAPTURE_ATTRIBUTE = "_fresh_synthesis_diagnostic_capture"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _payloads(variant: Variant = "uncommitted_receipt") -> dict[str, Any]:
    payloads = model_source_payloads(investigation_packet(variant))
    canonical = correlate_investigation_sources(
        {name: payloads[name] for name in SOURCE_TOOL_NAMES}
    )
    canonical["quantity_comparisons"] = {
        "invoice_minus_erp_accounted": canonical["observations"]["invoice_quantity"]
        - canonical["observations"]["erp_accounted_quantity"],
        "invoice_minus_physical_received": canonical["observations"]["invoice_quantity"]
        - canonical["observations"]["physical_received_quantity"],
        "quality_stock_recorded_in_erp": canonical["observations"][
            "erp_quality_inspection_quantity"
        ],
        "normalized_integration_attempt": canonical["observations"][
            "integration_normalized_quantity"
        ],
    }
    return {**payloads, CORRELATION_TOOL_NAME: canonical}


def _messages(
    payloads: Mapping[str, Any],
    *,
    include_prose: bool = False,
    blocked_correlation: bool = False,
    omit: str | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": "Original human investigation request."}]}
    ]
    if blocked_correlation:
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "name": CORRELATION_TOOL_NAME,
                                "toolUseId": "blocked-correlation",
                                "input": {"query": "too early"},
                            }
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": "blocked-correlation",
                                "content": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "status": "BLOCKED",
                                                "missing_source_reads": ["read_erp_evidence"],
                                            },
                                            sort_keys=True,
                                            separators=(",", ":"),
                                        )
                                    }
                                ],
                            }
                        }
                    ],
                },
            ]
        )
    for index, name in enumerate(REQUIRED_TOOLS):
        if name == omit:
            continue
        tool_use_id = f"read-{index}"
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": [
                        *([{"text": "ACQUISITION ASSISTANT SUMMARY"}] if include_prose else []),
                        {
                            "toolUse": {
                                "name": name,
                                "toolUseId": tool_use_id,
                                "input": {"query": f"fixture-{index}"},
                            }
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        *([{"text": "ACQUISITION USER PROSE"}] if include_prose else []),
                        {
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [
                                    {
                                        "text": _canonical(
                                            {**payloads[name], "query_received": f"fixture-{index}"}
                                        ).decode("utf-8")
                                    }
                                ],
                            }
                        },
                    ],
                },
            ]
        )
    return messages


def _result_texts(messages: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    ids: dict[str, str] = {}
    for message in messages:
        for block in message["content"]:
            if "toolUse" in block:
                tool_use = block["toolUse"]
                ids[tool_use["toolUseId"]] = tool_use["name"]
            if "toolResult" in block:
                result = block["toolResult"]
                names[ids[result["toolUseId"]]] = result["content"][0]["text"]
    return names


def test_fresh_context_removes_only_acquisition_prose_and_preserves_all_payload_bytes() -> None:
    payloads = _payloads()
    original_payloads = copy.deepcopy(payloads)
    acquisition_messages = _messages(payloads, include_prose=True)
    original_result_texts = _result_texts(acquisition_messages)
    context = build_fresh_synthesis_context(
        acquisition_messages,
        expected_payloads=payloads,
        required_tool_names=REQUIRED_TOOLS,
        prohibited_tool_names=(POLICY_TOOL_NAME,),
    )

    assert payloads == original_payloads
    assert "ACQUISITION" not in json.dumps(context.messages)
    assert context.messages[0] == {
        "role": "user",
        "content": [{"text": "Original human investigation request."}],
    }
    assert context.provenance_pairs_valid is True
    assert context.excluded_blocked_correlations == 0
    actual = _result_texts(context.messages)
    assert set(actual) == set(REQUIRED_TOOLS)
    for name in REQUIRED_TOOLS:
        assert actual[name].encode("utf-8") == original_result_texts[name].encode("utf-8")
        assert (
            context.tool_result_sha256[name]
            == hashlib.sha256(original_result_texts[name].encode("utf-8")).hexdigest()
        )
        recovered = json.loads(actual[name])
        recovered.pop("query_received")
        assert _canonical(recovered) == _canonical(payloads[name])
        assert (
            context.source_payload_sha256[name]
            == hashlib.sha256(_canonical(payloads[name])).hexdigest()
        )


@pytest.mark.parametrize(
    "variant,mutate",
    [
        ("uncommitted_receipt", None),  # authoritative destination absence
        ("lost_ack", None),  # authoritative destination presence
        ("lookup_unavailable", None),  # unavailable destination lookup
        (
            "uncommitted_receipt",
            lambda payloads: payloads["read_erp_evidence"]["ledger_read"].update(po="OTHER-PO"),
        ),  # wrong destination scope
        (
            "transfer_already_present",
            lambda payloads: payloads["read_airtable_evidence"]["quality_records"][0].update(
                quantity=7
            ),
        ),  # mismatched QA quantity
    ],
)
def test_fresh_context_retains_each_counterexample_payload_without_semantic_canned_answer(
    variant: Variant, mutate: Any
) -> None:
    payloads = _payloads(variant)
    if mutate is not None:
        mutate(payloads)
        payloads[CORRELATION_TOOL_NAME] = correlate_investigation_sources(
            {name: payloads[name] for name in SOURCE_TOOL_NAMES}
        )
    snapshot = copy.deepcopy(payloads)

    context = build_fresh_synthesis_context(
        _messages(payloads),
        expected_payloads=payloads,
        required_tool_names=REQUIRED_TOOLS,
        prohibited_tool_names=(POLICY_TOOL_NAME,),
    )

    assert payloads == snapshot
    assert set(context.source_payload_sha256) == set(REQUIRED_TOOLS)
    assert all(
        "expected_disposition" not in value for value in _result_texts(context.messages).values()
    )


def test_blocked_correlation_is_not_imported_and_an_incomplete_read_cannot_start_synthesis() -> (
    None
):
    payloads = _payloads()
    context = build_fresh_synthesis_context(
        _messages(payloads, blocked_correlation=True),
        expected_payloads=payloads,
        required_tool_names=REQUIRED_TOOLS,
        prohibited_tool_names=(POLICY_TOOL_NAME,),
    )
    assert context.excluded_blocked_correlations == 1
    assert "BLOCKED" not in json.dumps(context.messages)

    with pytest.raises(FreshSynthesisContextError, match="missing completed admitted tool result"):
        build_fresh_synthesis_context(
            _messages(payloads, omit="read_airtable_evidence"),
            expected_payloads=payloads,
            required_tool_names=REQUIRED_TOOLS,
            prohibited_tool_names=(POLICY_TOOL_NAME,),
        )


def test_fresh_context_keeps_parallel_tool_grouping_and_rejects_transport_error_results() -> None:
    payloads = _payloads()
    source_messages = _messages(payloads)
    first_use, first_result = source_messages[1:3]
    second_use, second_result = source_messages[3:5]
    grouped = [
        source_messages[0],
        {
            "role": "assistant",
            "content": [
                {"text": "ACQUISITION SUMMARY"},
                first_use["content"][0],
                second_use["content"][0],
            ],
        },
        {
            "role": "user",
            "content": [
                first_result["content"][0],
                {"text": "ACQUISITION USER FOLLOW-UP"},
                second_result["content"][0],
            ],
        },
        *source_messages[5:],
    ]
    context = build_fresh_synthesis_context(
        grouped,
        expected_payloads=payloads,
        required_tool_names=REQUIRED_TOOLS,
        prohibited_tool_names=(POLICY_TOOL_NAME,),
    )
    assert len(context.messages[1]["content"]) == 2
    assert len(context.messages[2]["content"]) == 2
    assert context.messages[1]["content"][0] == first_use["content"][0]
    assert context.messages[1]["content"][1] == second_use["content"][0]

    errored = _messages(payloads)
    errored[4]["content"][0]["toolResult"]["status"] = "error"
    with pytest.raises(FreshSynthesisContextError, match="did not complete successfully"):
        build_fresh_synthesis_context(
            errored,
            expected_payloads=payloads,
            required_tool_names=REQUIRED_TOOLS,
            prohibited_tool_names=(POLICY_TOOL_NAME,),
        )


def test_fresh_context_rejects_a_tool_use_id_reused_after_its_first_result() -> None:
    payloads = _payloads()
    messages = _messages(payloads)
    original_id = messages[1]["content"][0]["toolUse"]["toolUseId"]
    messages[3]["content"][0]["toolUse"]["toolUseId"] = original_id
    messages[4]["content"][0]["toolResult"]["toolUseId"] = original_id

    with pytest.raises(FreshSynthesisContextError, match="tool-use ID was repeated"):
        build_fresh_synthesis_context(
            messages,
            expected_payloads=payloads,
            required_tool_names=REQUIRED_TOOLS,
            prohibited_tool_names=(POLICY_TOOL_NAME,),
        )


def test_bedrock_request_format_starts_with_original_user_and_retains_valid_tool_pairs() -> None:
    payloads = _payloads()
    context = build_fresh_synthesis_context(
        _messages(payloads, include_prose=True),
        expected_payloads=payloads,
        required_tool_names=REQUIRED_TOOLS,
        prohibited_tool_names=(POLICY_TOOL_NAME,),
    )
    synthesis_prompt = {"role": "user", "content": [{"text": "Original synthesis request."}]}
    final_synthesis_input = [*context.messages, synthesis_prompt]
    assert context.messages[-1]["role"] == "user"
    assert all("toolResult" in block for block in context.messages[-1]["content"])

    model = BedrockModel(
        model_id="us.amazon.nova-pro-v1:0",
        region_name="us-west-2",
        streaming=False,
    )
    request = model.format_request(cast(Any, final_synthesis_input))
    formatted = request["messages"]
    assert formatted[0]["role"] == "user"
    assert formatted[0]["content"] == [{"text": "Original human investigation request."}]
    tool_use_ids = [
        block["toolUse"]["toolUseId"]
        for message in formatted
        for block in message["content"]
        if "toolUse" in block
    ]
    tool_result_ids = [
        block["toolResult"]["toolUseId"]
        for message in formatted
        for block in message["content"]
        if "toolResult" in block
    ]
    assert tool_use_ids == tool_result_ids
    assert len(tool_use_ids) == len(set(tool_use_ids)) == len(REQUIRED_TOOLS)
    assert "ACQUISITION" not in json.dumps(formatted)

    # The current SDK initially preserves adjacent user turns. On the specific
    # tool-result validation failure, its native retry inserts this request-local
    # separator and remembers the behavior for later requests; it never mutates
    # the copied application context.
    normalized = model._separate_tool_result_turns(formatted)
    assert normalized[-3:] == [
        formatted[-2],
        {"role": "assistant", "content": [{"text": "Tool result received."}]},
        formatted[-1],
    ]

    class RetryingClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []
            self.meta = SimpleNamespace(region_name="us-west-2")

        def converse(self, **request: Any) -> dict[str, Any]:
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ValidationException",
                            "Message": (
                                "Conversation blocks and tool result blocks cannot be provided "
                                "in the same turn."
                            ),
                        }
                    },
                    "Converse",
                )
            return {
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 0, "outputTokens": 0},
            }

    retrying_client = RetryingClient()
    model.client = cast(Any, retrying_client)
    model._stream(lambda _event=None: None, cast(Any, final_synthesis_input))
    assert [request["messages"] for request in retrying_client.requests] == [formatted, normalized]
    assert model._tool_result_turn_separation_model_id == model.config["model_id"]
    assert model.format_request(cast(Any, final_synthesis_input))["messages"] == normalized


def _candidate() -> LiveAdvisoryResult:
    return LiveAdvisoryResult(
        disposition=AdvisoryDisposition.RECOVERY_READY,
        evidence_ids=("ERP-READ-4817", "QA-901", "ATTEMPT-551", "SCAN-703"),
        reason="100 arrived; ERP accounts for 88 including 8 quality-held units. "
        "The 12-unit receipt key is confirmed absent. The exact held lot is approved "
        "and its transfer absent, so these are two separate effects.",
        safe_next_step="Request Manager approval for the bounded receipt and quality transfer.",
        write_performed=False,
    )


class _Factory:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.ledger = SimpleNamespace(
            snapshot=lambda: {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "incremental_cost_usd": 0.0,
            }
        )
        self.config = SimpleNamespace(
            model_id="offline-contract-test",
            region="us-west-2",
            max_tokens=2048,
            temperature=0,
            streaming=False,
            aws_profile=None,
            budget=SimpleNamespace(
                max_requests=8,
                max_input_tokens=32_000,
                max_output_tokens=16_000,
                max_output_tokens_per_request=2048,
                prior_cost_usd=0,
                incremental_cost_cap_usd=0.16,
                cumulative_cost_cap_usd=0.16,
                input_price_per_token=0,
                output_price_per_token=0,
                per_call_timeout_seconds=30,
                whole_run_timeout_seconds=90,
            ),
        )

    def create(self, **kwargs: Any) -> object:
        self.create_calls.append(kwargs)
        return SimpleNamespace(ledger=self.ledger)

    def provenance(self) -> dict[str, str]:
        return {"provider": "offline-contract-test"}


_UNSET_RAW_STRUCTURED_OUTPUT = object()


def _install_agent(
    monkeypatch: pytest.MonkeyPatch,
    *,
    complete: bool,
    candidate: LiveAdvisoryResult | None = None,
    raw_structured_output: Any = _UNSET_RAW_STRUCTURED_OUTPUT,
) -> list[Any]:
    agents: list[Any] = []

    class Agent:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.tools = kwargs["tools"]
            self.messages = kwargs.get("messages", [])
            self.invocation_count = 0
            self.structured_invocations: list[tuple[str, dict[str, Any]]] = []
            agents.append(self)

        async def invoke_async(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            self.invocation_count += 1
            if kwargs.get("structured_output_model") is None:
                if not self.messages:
                    self.messages.append({"role": "user", "content": [{"text": prompt}]})
                names = REQUIRED_TOOLS if complete else ("read_erp_evidence",)
                readers = dict(zip(REQUIRED_TOOLS, self.tools, strict=True))
                for index, name in enumerate(names):
                    payload = readers[name](f"diagnostic-{index}")
                    tool_use_id = f"actual-{index}"
                    self.messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": [
                                    {"text": "ACQUISITION MODEL PROSE MUST NOT CROSS"},
                                    {
                                        "toolUse": {
                                            "name": name,
                                            "toolUseId": tool_use_id,
                                            "input": {"query": f"diagnostic-{index}"},
                                        }
                                    },
                                ],
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"text": "ACQUISITION USER PROSE MUST NOT CROSS"},
                                    {
                                        "toolResult": {
                                            "toolUseId": tool_use_id,
                                            "content": [{"text": payload}],
                                        }
                                    },
                                ],
                            },
                        ]
                    )
                return SimpleNamespace(structured_output=None, stop_reason="end_turn")
            assert kwargs["structured_output_model"] is LiveAdvisoryResult
            self.structured_invocations.append((prompt, kwargs))
            return SimpleNamespace(
                structured_output=(
                    raw_structured_output
                    if raw_structured_output is not _UNSET_RAW_STRUCTURED_OUTPUT
                    else candidate or _candidate()
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(strands, "Agent", Agent)
    return agents


def test_diagnostic_recreates_only_the_synthesis_agent_and_stops_after_first_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents = _install_agent(monkeypatch, complete=True)
    factory = _Factory()
    packet = investigation_packet("uncommitted_receipt")

    run = run_fresh_synthesis_context_diagnostic(
        packet,
        factory=cast(Any, factory),
        question="Investigate this case.",
    )

    assert len(agents) == 2
    acquisition, synthesis = agents
    assert factory.create_calls[0] == factory.create_calls[1]
    assert acquisition.kwargs["model"].ledger is synthesis.kwargs["model"].ledger is factory.ledger
    assert acquisition.kwargs["system_prompt"] == synthesis.kwargs["system_prompt"]
    assert synthesis.tools == []
    assert "ACQUISITION MODEL PROSE" not in json.dumps(synthesis.messages)
    assert set(_result_texts(synthesis.messages)) == set(REQUIRED_TOOLS)
    assert run.usage["validation_retries"] == 0
    assert run.fresh_synthesis_context["same_factory_ledger"] is True
    assert run.fresh_synthesis_context["first_candidate_only"] is True
    assert 0 < run.fresh_synthesis_context["remaining_seconds_before_synthesis"] < 90

    normal_agents = _install_agent(monkeypatch, complete=True)
    run_live_advisory(
        packet,
        factory=cast(Any, _Factory()),
        question="Investigate this case.",
    )
    normal = normal_agents[0]
    fresh_prompt, fresh_kwargs = synthesis.structured_invocations[0]
    normal_prompt, normal_kwargs = normal.structured_invocations[0]
    assert synthesis.kwargs["system_prompt"] == normal.kwargs["system_prompt"]
    assert fresh_prompt == normal_prompt
    assert fresh_kwargs["structured_output_prompt"] == normal_kwargs["structured_output_prompt"]
    assert fresh_kwargs["structured_output_model"] is normal_kwargs["structured_output_model"]


def test_diagnostic_never_creates_a_synthesis_agent_before_all_reads_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents = _install_agent(monkeypatch, complete=False)
    factory = _Factory()

    with pytest.raises(Exception, match="acquisition did not complete"):
        run_fresh_synthesis_context_diagnostic(
            investigation_packet("uncommitted_receipt"),
            factory=cast(Any, factory),
            question="Investigate this case.",
        )
    assert len(agents) == 1
    assert len(factory.create_calls) == 1


def test_normal_advisory_keeps_its_original_single_agent_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents = _install_agent(monkeypatch, complete=True)
    factory = _Factory()

    run = run_live_advisory(
        investigation_packet("uncommitted_receipt"),
        factory=cast(Any, factory),
        question="Investigate this case.",
    )

    assert len(agents) == 1
    assert len(factory.create_calls) == 1
    assert run.usage["validation_retries"] == 0


def test_diagnostic_captures_the_first_rejected_candidate_without_a_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejected = _candidate().model_copy(
        update={
            "disposition": AdvisoryDisposition.NEEDS_EVIDENCE,
            "reason": "The timeout cause needs investigation.",
            "safe_next_step": "Inspect the source records without writing.",
        }
    )
    agents = _install_agent(monkeypatch, complete=True, candidate=rejected)
    factory = _Factory()

    with pytest.raises(advisory.AdvisoryValidationError) as failure:
        run_fresh_synthesis_context_diagnostic(
            investigation_packet("uncommitted_receipt"),
            factory=cast(Any, factory),
            question="Investigate this case.",
        )

    assert len(agents) == 2
    assert agents[1].invocation_count == 1
    assert len(failure.value.diagnostics) == 1
    assert failure.value.diagnostics[0]["candidate"] == rejected.model_dump(mode="json")
    assert failure.value.fresh_synthesis_context["message_sha256"]


def test_diagnostic_retains_an_unvalidated_first_structured_value_privately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = {
        "disposition": "NOT_A_REAL_DISPOSITION",
        "evidence_ids": ["ERP-READ-4817"],
        "reason": "raw provider mapping before schema validation",
        "safe_next_step": "Inspect the records.",
        "write_performed": False,
    }
    agents = _install_agent(
        monkeypatch,
        complete=True,
        raw_structured_output=malformed,
    )
    factory = _Factory()

    with pytest.raises(advisory.AdvisoryValidationError) as failure:
        run_fresh_synthesis_context_diagnostic(
            investigation_packet("uncommitted_receipt"),
            factory=cast(Any, factory),
            question="Investigate this case.",
        )

    assert len(agents) == 2
    assert agents[1].invocation_count == 1
    assert failure.value.diagnostics == []
    assert failure.value.usage == factory.ledger.snapshot()
    assert failure.value.fresh_synthesis_context["message_sha256"]
    capture = getattr(failure.value, PRIVATE_CAPTURE_ATTRIBUTE)
    assert capture == {
        "status": "UNVALIDATED",
        "first_structured_raw_value": malformed,
    }
    assert all("first_structured_raw_value" not in item for item in failure.value.diagnostics)


def test_standard_advisory_does_not_expose_a_raw_structured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_agent(
        monkeypatch,
        complete=True,
        raw_structured_output={"disposition": "NOT_A_REAL_DISPOSITION"},
    )

    with pytest.raises(advisory.AdvisoryValidationError) as failure:
        run_live_advisory(
            investigation_packet("uncommitted_receipt"),
            factory=cast(Any, _Factory()),
            question="Investigate this case.",
        )

    assert failure.value.diagnostics == []
    assert not hasattr(failure.value, PRIVATE_CAPTURE_ATTRIBUTE)


def test_probe_keeps_an_unvalidated_candidate_private_and_records_final_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = {"disposition": "NOT_A_REAL_DISPOSITION"}
    failure = advisory.AdvisoryValidationError("real advisory returned invalid structured data")
    failure.usage = {"request_count": 1}
    failure.fresh_synthesis_context = {"message_sha256": "fresh-context-hash"}
    private_capture = {
        "status": "UNVALIDATED",
        "first_structured_raw_value": malformed,
    }
    setattr(failure, PRIVATE_CAPTURE_ATTRIBUTE, private_capture)
    factory = _Factory()

    class Gateway:
        def __init__(self, _projection: Any) -> None:
            pass

        def _factory(self) -> _Factory:
            return factory

    def raise_failure(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(probe, "DashboardAdvisoryGateway", Gateway)
    monkeypatch.setattr(probe, "run_fresh_synthesis_context_diagnostic", raise_failure)
    report: dict[str, Any] = {"source_projection": {"case_id": "frozen"}}

    probe._run(report, {"case_id": "frozen"})

    assert report["status"] == "AdvisoryValidationError"
    assert report["candidate"] is None
    assert report["candidates"] == []
    assert report["diagnostics"] == []
    assert report["private_first_structured_capture"] == private_capture
    assert report["fresh_synthesis_context"] == failure.fresh_synthesis_context
    assert report["usage"] == failure.usage
    assert report["factory_usage"]["ledger"] == factory.ledger.snapshot()
    assert report["factory_usage"]["ledger_request_count_scope"] == (
        "logical BudgetedModel request reservations; not a provider HTTP-attempt count"
    )
    assert report["factory_usage"]["provider_http_attempts"]["status"] == (
        "NOT_EXPOSED_BY_FACTORY_LEDGER"
    )
