"""Source-basis and dialogue-reference boundaries, not a prose-quality oracle."""

from copy import deepcopy

import pytest
from test_receiving_advisory import partial_receipt

from the_missing_20.adapters import dialogue_intent
from the_missing_20.agents.live_advisory import live_recovery_packet, model_source_payloads
from the_missing_20.agents.receiving_facts import receipt_relations, reference_candidates


@pytest.mark.parametrize(
    "basis,independent,lower",
    [
        ("RECEIPT_CONFIRMED", None, 1),
        ("INDEPENDENT_OBSERVATION", 1, None),
        ("UNKNOWN", None, None),
        (None, None, None),
    ],
)
def test_model_quantity_names_cannot_imply_independent_physical_agreement(
    basis, independent, lower
):
    payload = partial_receipt()
    payload["case_projection"]["case"]["physical_observation_basis"] = basis
    packet = live_recovery_packet(payload)
    before = deepcopy(packet)
    source = model_source_payloads(packet)["read_erp_evidence"]
    quantities = source["quantities"]
    assert "physically_arrived" not in quantities
    assert quantities["independently_observed_quantity"] == independent
    assert quantities["receipt_confirmed_lower_bound"] == lower
    assert packet == before
    assert (
        packet["tool_payload"]["sources"]["read_erp_evidence"]["quantities"]["physically_arrived"]
        == 1
    )


def source():
    return {
        "evidence_ids": ["PO", "PR1", "PR2", "mixed:ledger"],
        "records": [
            {"evidence_id": "PR1", "provider": "ERPNext"},
            {"evidence_id": "PR2", "provider": "ERPNext"},
            {
                "evidence_id": "mixed:ledger",
                "provider": "ERPNext",
                "revision": "v2",
                "observed_at": "now",
                "stock_entries": [
                    {"voucher_no": "PR1", "name": "SLE1", "voucher_type": "Purchase Receipt"},
                    {"voucher_no": "PR2", "name": "SLE2", "voucher_type": "Purchase Receipt"},
                    {"voucher_no": "PR2", "name": "SLE3", "voucher_type": "Purchase Receipt"},
                    {"voucher_no": "ALIEN", "name": "SLE4", "voucher_type": "Purchase Receipt"},
                    {"voucher_no": "PR1", "name": "", "voucher_type": "Purchase Receipt"},
                    {"voucher_no": "PR1", "name": "SLE5", "voucher_type": "Delivery Note"},
                ],
            },
        ],
    }


def test_receipt_relation_joins_actual_voucher_not_enclosing_ledger_id():
    rows = receipt_relations(source())
    assert [(r["receipt_id"], r["stock_ledger_id"]) for r in rows] == [
        ("PR1", "SLE1"),
        ("PR2", "SLE2"),
        ("PR2", "SLE3"),
    ]
    assert all(r["evidence_id"] == "mixed:ledger" and r["revision"] == "v2" for r in rows)


def test_partial_reference_disappearance_does_not_select_surviving_receipt():
    previous = {
        "case_id": "C1",
        "status": "COMPLETE",
        "receipt_ids": ["PR1", "PR2"],
        "source_sequence": 1,
    }
    current = reference_candidates(
        previous,
        case_id="C1",
        relations=[{"receipt_id": "PR2", "stock_ledger_id": "SLE_NEW"}],
        source_sequence=2,
    )
    assert current["status"] == "CHANGED"
    assert current["previous_receipt_ids"] == ["PR1", "PR2"]
    assert current["current_receipt_ids"] == ["PR2"]
    assert current["missing_receipt_ids"] == ["PR1"]
    assert "selected_receipt_id" not in current


@pytest.mark.parametrize(
    "previous",
    [
        {},
        {"case_id": "C2", "status": "COMPLETE", "receipt_ids": ["PR1"]},
        {"case_id": "C1", "status": "FAILED", "receipt_ids": ["PR1"]},
    ],
)
def test_legacy_failed_or_other_case_references_are_not_carried(previous):
    assert (
        reference_candidates(
            previous, case_id="C1", relations=receipt_relations(source()), source_sequence=2
        )["status"]
        == "UNAVAILABLE"
    )


def test_plural_citations_are_candidates_and_current_ledger_ids_are_refreshed():
    previous = {
        "case_id": "C1",
        "status": "COMPLETE",
        "receipt_ids": ["PR1", "PR2"],
        "source_sequence": 1,
    }
    current = reference_candidates(
        previous, case_id="C1", relations=receipt_relations(source()), source_sequence=2
    )
    assert current["status"] == "MULTIPLE_CANDIDATES"
    assert current["current_receipt_ids"] == ["PR1", "PR2"]
    assert current["source_sequence"] == 2


def test_gateway_rereads_scoped_references_without_prior_assistant_claims():
    from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
    from the_missing_20.agents.live_advisory import AdvisoryRun, LiveAdvisoryResult
    from the_missing_20.config import Settings
    from the_missing_20.ports.agent_model import AgentProvider

    payload = partial_receipt()
    payload["case_id"] = "LIVE-CASE"
    payload["evidence_catalog"] = {r["evidence_id"]: r for r in source()["records"]}
    payload["evidence_catalog"]["PO"] = {"evidence_id": "PO", "provider": "ERPNext"}
    payload["case_projection"]["case"]["purchase_receipt"] = "PR1"
    payload["conversation"] = []

    class Platform:
        def __init__(self):
            self._dialogue: dict[str, object] = {}
            self._runtime_instance_id = "receiving-test-runtime"

        def current(self):
            return {
                **deepcopy(payload),
                **dialogue_intent.public_state(
                    self._dialogue,
                    str(payload["case_id"]),
                    runtime_instance_id=self._runtime_instance_id,
                ),
            }

        def record_human_request(self, question, case_id, *, new_conversation=False):
            self._dialogue = dialogue_intent.record_request(
                self._dialogue,
                case_id,
                question,
                "now",
                runtime_instance_id=self._runtime_instance_id,
                new_conversation=new_conversation,
            )
            return dialogue_intent.public_state(
                self._dialogue,
                case_id,
                runtime_instance_id=self._runtime_instance_id,
            )

        def record_conversation_turn(
            self,
            question,
            answer,
            advisory,
            *,
            expected_case_id="",
            expected_conversation_id="",
        ):
            del expected_case_id, expected_conversation_id
            group = advisory.get("dialogue_reference_group")
            if isinstance(group, dict):
                self._dialogue = dialogue_intent.record_reference_group(
                    self._dialogue,
                    case_id=str(group["case_id"]),
                    question=question,
                    receipt_ids=list(group["receipt_ids"]),
                    validated=group.get("provenance") == "runtime_validated",
                    at="now",
                    runtime_instance_id=self._runtime_instance_id,
                )
            payload["conversation"].append(
                {
                    "question": question,
                    "answer": "UNTRUSTED_OLD_PROSE",
                    "receiving_references": advisory["receiving_references"],
                }
            )
            return self.current()

    seen = []

    def runner(packet, **kwargs):
        seen.append((deepcopy(packet), kwargs["question"]))
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition="SAFE_NOOP",
                evidence_ids=("PR2",),
                reason="PR2 is posted.",
                safe_next_step="Inspect its ledger.",
                write_performed=False,
            ),
            tool_calls=("read_control_context", "read_erp_evidence"),
            provider={"provider": "bedrock"},
            latency_ms=1,
            usage={},
        )

    gateway = DashboardAdvisoryGateway(
        Platform(), settings=Settings(agent_provider=AgentProvider.BEDROCK), runner=runner
    )
    gateway.ask("Inspect PR2")
    gateway.ask("Which records support that receipt?")
    refs = seen[-1][0]["tool_payload"]["sources"]["read_control_context"][
        "prior_reference_candidates"
    ]
    assert refs["current_receipt_ids"] == ["PR2"]
    assert refs["status"] == "ONE_CANDIDATE"
    assert "UNTRUSTED_OLD_PROSE" not in seen[-1][1]
    payload["case_projection"]["case"]["case_id"] = payload["case_id"] = "OTHER"
    payload["receiving_work"]["case_id"] = "OTHER"
    gateway.ask("And that receipt?")
    assert (
        seen[-1][0]["tool_payload"]["sources"]["read_control_context"][
            "prior_reference_candidates"
        ]["status"]
        == "UNAVAILABLE"
    )


def test_real_platform_persists_reference_metadata_without_business_effect(tmp_path):
    from test_agent_platform import _erp, _Reader, _saas

    from the_missing_20.adapters.agent_platform import AgentPlatform

    state = tmp_path / "state.json"
    refs = {"case_id": "C", "status": "COMPLETE", "receipt_ids": ["PR1"], "source_sequence": 1}
    platform = AgentPlatform(_Reader(_erp()), _Reader(_saas()), state_path=state)
    before = platform.current()
    platform.record_conversation_turn("Read PR1", "Retained answer", {"receiving_references": refs})
    current = AgentPlatform(_Reader(_erp()), _Reader(_saas()), state_path=state).current()
    assert current["conversation"][-1]["receiving_references"] == refs
    for key in ("execution", "approval", "diagnosis"):
        assert current.get(key) == before.get(key)
