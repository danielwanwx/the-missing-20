"""Offline evidence for the reconstructed frozen D4 Strands input boundary."""

from __future__ import annotations

import hashlib
import json
import socket
import stat
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.diagnostics import capture_frozen_receiving_sdk_boundary as capture_module
from scripts.diagnostics.capture_frozen_receiving_sdk_boundary import (
    CaptureError,
    capture_frozen_receiving_sdk_boundary,
)
from the_missing_20.adapters.strands_models import BedrockNovaProFactory

CASE_ID = "SYNTHETIC-RECEIVING-CASE"
PURCHASE_ORDER = "SYN-PO-01"
PURCHASE_RECEIPT = "SYN-PR-01"
STOCK_LEDGER = "SYN-SLE-01"
FIRST_QUESTION = "Which receipt was posted?"
REFUSAL_QUESTION = "Do not execute or approve anything. Keep this conversation read-only."
THIRD_QUESTION = "What remains outstanding?"
CURRENT_QUESTION = "Does this receiving basis independently prove carton contents?"
ASSISTANT_SENTINEL = "SYNTHETIC_ASSISTANT_PROSE_MUST_NOT_REACH_CAPTURE"


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _synthetic_erp_source() -> dict[str, Any]:
    return {
        "schema_version": "missing20-erpnext-evidence/v1",
        "source_id": "synthetic-erp",
        "case_id": CASE_ID,
        "configured_document_names": {
            "purchase_order": PURCHASE_ORDER,
            "purchase_receipt": PURCHASE_RECEIPT,
            "purchase_invoice": "",
        },
        "primary_document_names": {
            "purchase_order": PURCHASE_ORDER,
            "purchase_receipt": PURCHASE_RECEIPT,
        },
        "provider": "ERPNext Synthetic Fixture",
        "read_only": True,
        "status": "CONNECTED",
        "documents": [
            {
                "kind": "purchase_order",
                "name": PURCHASE_ORDER,
                "status": "SUBMITTED",
                "docstatus": 1,
                "quantity": 2.0,
                "supplier": "Synthetic Supplier",
                "unit_rate": 50.0,
                "currency": "USD",
                "items": [
                    {
                        "name": "SYN-PO-LINE",
                        "item_code": "SYN-CARTON",
                        "qty": 2.0,
                        "uom": "Box",
                        "stock_uom": "Box",
                        "received_qty": 2.0,
                        "net_rate": 50.0,
                    }
                ],
            },
            {
                "kind": "purchase_receipt",
                "name": PURCHASE_RECEIPT,
                "status": "RECEIVED",
                "docstatus": 1,
                "received": 2.0,
                "accepted": 2.0,
                "rejected": 0.0,
                "quality_hold_remaining": 0.0,
                "case_scope_complete": True,
                "uom": "Box",
                "items": [
                    {
                        "name": "SYN-PR-LINE",
                        "item_code": "SYN-CARTON",
                        "qty": 2.0,
                        "uom": "Box",
                        "stock_uom": "Box",
                        "received_qty": 2.0,
                        "rejected_qty": 0.0,
                        "purchase_order": PURCHASE_ORDER,
                        "purchase_order_item": "SYN-PO-LINE",
                    }
                ],
            },
        ],
        "ledger_evidence": {
            "status": "CONNECTED",
            "source": "ERPNext Synthetic Fixture",
            "read_only": True,
            "voucher_names": [PURCHASE_RECEIPT],
            "stock_entries": [
                {
                    "name": STOCK_LEDGER,
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": PURCHASE_RECEIPT,
                    "item_code": "SYN-CARTON",
                    "warehouse": "Synthetic Stores",
                    "actual_qty": 2.0,
                }
            ],
            "general_ledger_entries": [],
            "totals": {},
            "assertions": {"stock_ledger_present": True},
        },
        "document_lifecycle": {
            "purchase_order": "PRESENT",
            "purchase_receipt": "PRESENT",
            "purchase_invoice": "AWAITING_INVOICE",
        },
        "purchase_scope": "ALL_LINKED_DOCUMENTS",
        "activity": [],
        "sequence": 1,
        "received_at": "2026-09-09T00:00:00+00:00",
        "changed_at": "2026-09-09T00:00:00+00:00",
    }


def _synthetic_saas_source() -> dict[str, Any]:
    return {
        "schema_version": "missing20-saas-evidence/v1",
        "correlation_id": CASE_ID,
        "read_only": True,
        "status": "CONNECTED",
        "sources": [],
        "activity": [],
        "sequence": 1,
        "received_at": "2026-09-09T00:00:00+00:00",
        "changed_at": "2026-09-09T00:00:00+00:00",
    }


def _synthetic_q4_artifact() -> dict[str, Any]:
    requests = [
        {"request_id": "human-1", "question": FIRST_QUESTION},
        {"request_id": "human-2", "question": REFUSAL_QUESTION},
        {"request_id": "human-3", "question": THIRD_QUESTION},
        {"request_id": "human-4", "question": CURRENT_QUESTION},
    ]
    candidate = {
        "disposition": "SAFE_NOOP",
        "evidence_ids": [PURCHASE_ORDER, PURCHASE_RECEIPT],
        "reason": (
            f"{ASSISTANT_SENTINEL}: The receiving basis independently proves carton contents."
        ),
        "safe_next_step": "Inspect the current read-only records.",
        "write_performed": False,
        "chart_metric": None,
        "follow_up_questions": [],
    }
    return {
        "turns": [
            {
                "question": CURRENT_QUESTION,
                "response": {
                    "human_requests": requests,
                    "human_intent": {"case_id": CASE_ID, "read_only_requested": True},
                    "dialogue_context": {
                        "case_id": CASE_ID,
                        "conversation_id": "synthetic-conversation",
                        "requests_omitted": 0,
                    },
                    "agent_advisory": {"result": candidate},
                },
            }
        ]
    }


def _inputs(tmp_path: Path) -> dict[str, Path]:
    fixture_root = tmp_path / "frozen-fixture"
    fixture_root.mkdir()
    return {
        "artifact": _write_json(fixture_root / "retained-q4.json", _synthetic_q4_artifact()),
        "erp_source": _write_json(fixture_root / "erp-v1.json", _synthetic_erp_source()),
        "saas_source": _write_json(fixture_root / "saas.json", _synthetic_saas_source()),
    }


def _capture(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, Path]]:
    inputs = _inputs(tmp_path)
    output = tmp_path / "sdk-boundary-capture.json"
    captured = capture_frozen_receiving_sdk_boundary(
        output_path=output,
        artifact_path=inputs["artifact"],
        erp_source=inputs["erp_source"],
        saas_source=inputs["saas_source"],
    )
    return output, captured, inputs


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, Mapping)
    return dict(value)


def test_capture_exercises_strands_model_stream_and_stops_before_any_answer(tmp_path: Path) -> None:
    output, captured, inputs = _capture(tmp_path)

    boundary = _mapping(captured["stream_boundary"])
    physical = _mapping(boundary["model_facing_physical_basis"])

    assert captured["capture_kind"] == "strands_model_stream_input_boundary"
    assert captured["capture_scope"] == "post_tool_acquisition_model_stream_before_typed_synthesis"
    assert captured["historical_wire_capture"] is False
    assert captured["historical_intermediate_assistant_reconstructed"] is False
    assert captured["synthetic_tool_orchestration"] is True
    assert captured["provider_requests"] == 0
    assert captured["provider_fallback"] is False
    assert boundary["captured_phase"] == captured["capture_scope"]
    assert boundary["typed_synthesis_input_captured"] is False
    assert boundary["stopped_after_tools"] is True
    assert boundary["answer_emitted"] is False
    assert boundary["tool_result_names"] == [
        "read_control_context",
        "read_erp_evidence",
        "read_airtable_evidence",
        "read_celigo_evidence",
        "read_collaboration_evidence",
    ]
    assert physical == {
        "physical_observation_basis": "RECEIPT_CONFIRMED",
        "independently_observed_quantity": None,
        "receipt_confirmed_lower_bound": 2.0,
        "raw_physically_arrived_present": False,
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert (
        _mapping(captured["input_sha256"])["artifact"]
        == hashlib.sha256(inputs["artifact"].read_bytes()).hexdigest()
    )
    assert _mapping(captured["input_paths"]) == {
        key: str(path.resolve()) for key, path in inputs.items()
    }


def test_capture_intercepts_human_only_messages_and_blocks_provider_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "sdk-boundary-capture.json"
    captured_messages: list[object] = []
    original_stream = capture_module.BoundaryCaptureModel.stream

    async def recording_stream(
        self: capture_module.BoundaryCaptureModel,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        *,
        tool_choice: Any = None,
        system_prompt_content: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        captured_messages.append(json.loads(json.dumps(messages, default=str)))
        async for event in original_stream(
            self,
            messages,
            tool_specs,
            system_prompt,
            tool_choice=tool_choice,
            system_prompt_content=system_prompt_content,
            **kwargs,
        ):
            yield event

    def forbidden_provider_construction(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("Bedrock provider construction is forbidden in this diagnostic")

    def forbidden_network(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("network access is forbidden in this diagnostic")

    monkeypatch.setattr(capture_module.BoundaryCaptureModel, "stream", recording_stream)
    monkeypatch.setattr(
        BedrockNovaProFactory,
        "create",
        forbidden_provider_construction,
    )
    monkeypatch.setattr(socket, "create_connection", forbidden_network)

    captured = capture_frozen_receiving_sdk_boundary(
        output_path=output,
        artifact_path=inputs["artifact"],
        erp_source=inputs["erp_source"],
        saas_source=inputs["saas_source"],
    )
    stream_text = json.dumps(captured_messages)

    assert FIRST_QUESTION in stream_text
    assert REFUSAL_QUESTION in stream_text
    assert THIRD_QUESTION in stream_text
    assert CURRENT_QUESTION in stream_text
    assert ASSISTANT_SENTINEL not in stream_text
    assert _mapping(captured["reconstruction"])["assistant_prose_in_reconstructed_context"] is False
    assert _mapping(captured["stream_boundary"])["typed_synthesis_input_captured"] is False


def test_candidate_admission_is_not_a_model_or_semantic_pass(tmp_path: Path) -> None:
    output, captured, _ = _capture(tmp_path)

    admission = _mapping(captured["retained_candidate_admission"])
    persisted = json.loads(output.read_text(encoding="utf-8"))

    assert admission["status"] == "ADMITTED_BY_EXISTING_VALIDATION"
    assert admission["existing_full_validation_seam"] is True
    assert admission["separate_from_boundary_capture"] is True
    assert admission["synthetic_candidate_injection"] is True
    assert admission["answer_displayed_or_persisted"] is False
    assert admission["semantic_accuracy_assessed"] is False
    assert admission["model_quality_pass"] is False
    assert ASSISTANT_SENTINEL not in json.dumps(persisted)


def test_missing_inputs_and_existing_output_stop_before_capture_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "not-present.json"
    newly_reserved = tmp_path / "newly-reserved.json"

    with pytest.raises(CaptureError, match="diagnostic input is unreadable"):
        capture_frozen_receiving_sdk_boundary(
            output_path=newly_reserved,
            artifact_path=missing,
            erp_source=missing,
            saas_source=missing,
        )
    assert newly_reserved.exists()
    assert newly_reserved.read_bytes() == b""
    assert stat.S_IMODE(newly_reserved.stat().st_mode) == 0o600

    existing = tmp_path / "existing-output.json"
    existing.write_text("keep this existing diagnostic", encoding="utf-8")

    def inputs_must_not_be_read(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("existing output must stop before reading inputs")

    monkeypatch.setattr(capture_module, "_reconstruct", inputs_must_not_be_read)
    with pytest.raises(FileExistsError):
        capture_frozen_receiving_sdk_boundary(
            output_path=existing,
            artifact_path=missing,
            erp_source=missing,
            saas_source=missing,
        )
    assert existing.read_text(encoding="utf-8") == "keep this existing diagnostic"
