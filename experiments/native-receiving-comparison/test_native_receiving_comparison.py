from __future__ import annotations

import json
import socket
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from strands.models import Model

EXPERIMENT = Path(__file__).parent
if str(EXPERIMENT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT))
import native_receiving_comparison as comparison  # noqa: E402

SENTINEL = "RETAINED-ASSISTANT-CANDIDATE-MUST-NEVER-REACH-MODEL"


def _tool_events(name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"tool-{name}"}}}},
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


class FakeNativeModel(Model):
    """Test-local offline provider; its action list is not a quality claim."""

    def __init__(self, actions: list[tuple[str, Any]]) -> None:
        self.actions = actions
        self.calls: list[dict[str, Any]] = []
        self.config = {"model_id": "test-local-native", "max_tokens": 1551, "temperature": 0}

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    async def structured_output(
        self, output_model: type[Any], prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        del output_model, prompt, system_prompt, kwargs
        if False:  # pragma: no cover - fulfills Model's async-generator protocol.
            yield {}
        raise AssertionError(
            "comparison must use Agent.stream_async, never Model.structured_output"
        )

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
        del system_prompt, tool_choice, system_prompt_content, invocation_state, model_state, kwargs
        self.calls.append(
            {
                "messages": comparison._copy(messages),
                "tool_specs": comparison._copy(tool_specs or []),
            }
        )
        if not self.actions:
            raise AssertionError("native loop made an unexpected provider turn")
        kind, value = self.actions.pop(0)
        if kind == "raise":
            raise RuntimeError(str(value))
        if kind == "text":
            events = _text_events(str(value))
        else:
            names = comparison._spec_names(tool_specs)
            if kind == "typed":
                choices = names.difference(comparison.SOURCE_TOOL_NAMES)
                assert len(choices) == 1
                name = choices.pop()
            else:
                name = str(value)
                assert name in names
            payload = value if kind == "typed" else {"query": "fixture read"}
            events = _tool_events(name, payload)
        for event in events:
            yield event


def _read_actions() -> list[tuple[str, Any]]:
    return [("tool", name) for name in comparison.SOURCE_TOOL_NAMES]


@pytest.fixture
def frozen_input(monkeypatch: pytest.MonkeyPatch) -> None:
    reconstruction = comparison.Reconstruction(
        packet={"case_class": "receiving_operations", "case_id": "fixture-case"},
        contextual_question="Human history only: what does the current evidence establish?",
        candidate={"answer": SENTINEL},
        metadata={"fixture": True},
        input_sha256={"fixture": "sha"},
    )
    payloads = {
        name: {"source": name, "record_id": f"fixture-{index}"}
        for index, name in enumerate(comparison.SOURCE_TOOL_NAMES, start=1)
    }
    monkeypatch.setattr(comparison, "_reconstruct", lambda **_kwargs: reconstruction)
    monkeypatch.setattr(comparison, "model_source_payloads", lambda _packet: payloads)


def _run(tmp_path: Path, variant: comparison.Variant, model: Model) -> dict[str, Any]:
    return comparison.run_candidate(
        variant=variant, output_path=tmp_path / f"{variant}.json", model=model
    )


def test_n1_and_n2_share_frozen_inputs_and_n2_excludes_retained_candidate(
    tmp_path: Path, frozen_input: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    n1_model = FakeNativeModel(_read_actions() + [("text", "Fixture natural-language answer")])
    n2_model = FakeNativeModel(
        _read_actions() + [("typed", {"answer": "Fixture answer", "citations": ["fixture-1"]})]
    )
    monkeypatch.setattr(
        comparison,
        "_live_model",
        lambda _ledger: (_ for _ in ()).throw(AssertionError("network factory used")),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )

    input_path = tmp_path / "shared-input.json"
    frozen = comparison.run_candidate(variant="n1", output_path=input_path)
    n1 = comparison.run_candidate(
        variant="n1", output_path=tmp_path / "n1.json", manifest_path=input_path, model=n1_model
    )
    record = comparison.run_candidate(
        variant="n2", output_path=tmp_path / "n2.json", manifest_path=input_path, model=n2_model
    )

    assert frozen["status"] == "OFFLINE_INPUT_FROZEN"
    assert frozen["sdk_invocation_count"] == 0
    assert frozen["observed_provider_attempt_count"] == 0
    assert n1["status"] == "STRUCTURAL_COMPLETE"
    assert n1["sdk_invocation_count"] == 1
    assert n1["logical_model_request_count"] == 6
    assert n1["observed_provider_attempt_count"] == 6
    assert record["status"] == "STRUCTURAL_COMPLETE"
    assert record["sdk_invocation_count"] == 1
    assert record["logical_model_request_count"] == 6
    assert record["observed_provider_attempt_count"] == 6
    assert [entry["tool"] for entry in record["tool_reads"]] == list(comparison.SOURCE_TOOL_NAMES)
    assert record["native_forced_format_fallback_count"] == 0
    assert record["output"]["structured_output"] == {
        "answer": "Fixture answer",
        "citations": ["fixture-1"],
    }
    assert SENTINEL not in json.dumps(record)
    assert SENTINEL not in json.dumps(n1_model.calls)
    assert SENTINEL not in json.dumps(n2_model.calls)
    assert record["freeze_manifest"]["retained_candidate_fixture_excluded"] is True
    for field in (
        "shared_prompt_sha256",
        "source_tool_specs_sha256",
        "qualified_source_payloads_sha256",
        "contextual_question_sha256",
    ):
        assert n1["freeze_manifest"][field] == record["freeze_manifest"][field]
    assert (
        n1["freeze_manifest"]["candidate_contracts"]
        == record["freeze_manifest"]["candidate_contracts"]
    )
    assert frozen["freeze_manifest"]["model_contract"] == {
        "provider": "bedrock",
        "model_id": "us.amazon.nova-pro-v1:0",
        "region": "us-west-2",
        "aws_profile": "missing20-sandbox",
        "max_tokens": 1551,
        "temperature": 0,
        "streaming": False,
    }
    assert "Retrieve each available source" in comparison.GENERIC_PROMPT


def test_early_final_is_structural_failure_without_repair(
    tmp_path: Path, frozen_input: None
) -> None:
    record = _run(tmp_path, "n1", FakeNativeModel([("text", "Early final.")]))

    assert record["status"] == "STRUCTURAL_FAIL"
    assert record["structural_reason"] == "required_source_tools_not_read"
    assert record["missing_source_reads"] == list(comparison.SOURCE_TOOL_NAMES)
    assert record["sdk_invocation_count"] == 1
    assert record["logical_model_request_count"] == 1


def test_native_forced_format_and_invalid_schema_are_retained_raw(
    tmp_path: Path, frozen_input: None
) -> None:
    invalid = {"answer": "invalid-candidate", "citations": []}
    valid = {"answer": "valid fixture answer", "citations": ["fixture-1"]}
    model = FakeNativeModel(
        _read_actions() + [("text", "untyped"), ("typed", invalid), ("typed", valid)]
    )

    record = _run(tmp_path, "n2", model)

    serialized = json.dumps(record)
    assert record["status"] == "STRUCTURAL_COMPLETE"
    assert record["native_forced_format_fallback_count"] == 1
    assert record["native_schema_only_turn_count"] == 2
    assert record["request_turns_containing_schema_error_history"] == 1
    assert "invalid-candidate" in serialized
    assert "valid fixture answer" in serialized
    assert len(record["provider_attempts"]) >= 8


def test_schema_error_history_counter_counts_turns_not_invalid_candidates(
    tmp_path: Path, frozen_input: None
) -> None:
    invalid = {"answer": "one-invalid-candidate", "citations": []}
    valid = {"answer": "valid fixture answer", "citations": ["fixture-1"]}
    model = FakeNativeModel(
        _read_actions()
        + [
            ("typed", invalid),
            ("tool", comparison.SOURCE_TOOL_NAMES[0]),
            ("typed", valid),
        ]
    )

    record = _run(tmp_path, "n2", model)

    assert record["status"] == "STRUCTURAL_COMPLETE"
    assert (
        sum(
            "one-invalid-candidate" in json.dumps(event)
            for attempt in record["provider_attempts"]
            for event in attempt["raw_model_events"]
        )
        == 1
    )
    assert record["request_turns_containing_schema_error_history"] == 2


def test_missing_source_payloads_stops_before_model(
    tmp_path: Path, frozen_input: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeNativeModel([])
    monkeypatch.setattr(
        comparison,
        "model_source_payloads",
        lambda _packet: {comparison.SOURCE_TOOL_NAMES[0]: {"only": "one"}},
    )

    record = _run(tmp_path, "n1", model)

    assert record["status"] == "STRUCTURAL_FAIL"
    assert record["sdk_invocation_count"] == 0
    assert record["logical_model_request_count"] == 0
    assert model.calls == []


def test_tampered_bundle_and_changed_fixture_are_rejected_before_live_factory(
    tmp_path: Path, frozen_input: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle.json"
    comparison.run_candidate(variant="n1", output_path=bundle)
    tampered = json.loads(bundle.read_text(encoding="utf-8"))
    tampered["frozen_input"]["contextual_question"] = "tampered question"
    bundle.write_text(json.dumps(tampered), encoding="utf-8")
    model = FakeNativeModel([])

    rejected = comparison.run_candidate(
        variant="n1",
        output_path=tmp_path / "tampered-result.json",
        manifest_path=bundle,
        model=model,
    )

    assert rejected["status"] == "EXECUTION_FAILED"
    assert "fixed manifest" in rejected["error"]["message"]
    assert model.calls == []

    checked_bundle = tmp_path / "checked-bundle.json"
    comparison.run_candidate(variant="n1", output_path=checked_bundle)
    real_file_sha = comparison._file_sha

    def changed_fixture_hash(path: Path) -> str:
        return real_file_sha(path) if path == Path(comparison.__file__) else "changed"

    monkeypatch.setattr(comparison, "_file_sha", changed_fixture_hash)
    monkeypatch.setattr(
        comparison,
        "_live_model",
        lambda _ledger: (_ for _ in ()).throw(AssertionError("live factory used")),
    )
    mismatch = comparison.run_candidate(
        variant="n1",
        output_path=tmp_path / "changed-fixture-result.json",
        manifest_path=checked_bundle,
        execute_model=True,
    )

    assert mismatch["status"] == "EXECUTION_FAILED"
    assert "fixture hashes" in mismatch["error"]["message"]


def test_exception_usage_is_written_and_existing_output_blocks_all_input_reads(
    tmp_path: Path, frozen_input: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "failed.json"
    record = comparison.run_candidate(
        variant="n1",
        output_path=output,
        model=FakeNativeModel(
            [("tool", comparison.SOURCE_TOOL_NAMES[0]), ("raise", "test stream failure")]
        ),
    )

    assert record["status"] == "EXECUTION_FAILED"
    assert record["sdk_invocation_count"] == 1
    assert record["observed_provider_attempt_count"] == 2
    assert record["provider_attempts"][1]["error"]["message"] == "test stream failure"
    assert record["logical_model_request_count"] == 2
    assert record["agent_events"]
    assert record["freeze_manifest"]
    assert output.stat().st_mode & 0o777 == 0o600

    existing = tmp_path / "existing.json"
    existing.write_text("do-not-overwrite", encoding="utf-8")
    monkeypatch.setattr(
        comparison,
        "_reconstruct",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("input was read")),
    )
    with pytest.raises(FileExistsError):
        comparison.run_candidate(variant="n1", output_path=existing)
    assert existing.read_text(encoding="utf-8") == "do-not-overwrite"
