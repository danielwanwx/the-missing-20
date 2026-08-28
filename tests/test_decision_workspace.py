from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.decision_workspace_server import DecisionWorkspaceServer
from the_missing_20.authority_b import workspace_demo
from the_missing_20.authority_b.lifecycle import (
    LIFECYCLE_ARTIFACT_PATH,
    load_lifecycle_bundle,
)
from the_missing_20.authority_b.models import canonical_json
from the_missing_20.authority_b.workspace_demo import (
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceEvidenceClass,
    WorkspaceMode,
    WorkspaceUnavailable,
    _hypotheses_from_golden,
    build_decision_workspace,
)

ROOT = Path(__file__).resolve().parents[1]


def _resign_payload(payload: dict[str, object]) -> None:
    payload["bundle_digest"] = hashlib.sha256(
        canonical_json(
            {key: value for key, value in payload.items() if key != "bundle_digest"}
        ).encode()
    ).hexdigest()


@pytest.mark.parametrize("mode", ("complete", "degraded"))
def test_workspace_artifact_is_typed_stable_and_claim_classified(mode: str) -> None:
    artifact = build_decision_workspace(ROOT, mode=mode)
    assert not isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    assert payload["schema_version"] == WORKSPACE_SCHEMA_VERSION
    assert set(item["label"] for item in payload["evidence_taxonomy"]) == {
        "PROVEN",
        "SCRIPTED SYNTHETIC PROOF",
        "NOT PROVEN",
    }
    assert {item["evidence_class"] for item in payload["claims"]} <= {
        item.value for item in WorkspaceEvidenceClass
    }
    assert payload["human_control"]["controls_enabled"] is False
    assert payload["execution"]["replay_effect_delta"] == 0
    assert payload["m6_aws_proof"]["status"] == "PASS"
    assert payload["case"]["discrepancy_statement"] == "100 expected, 80 recorded, 20 missing."
    hypotheses = payload["advisory"]["hypotheses"]
    if mode == "complete":
        assert [
            (
                item["hypothesis_type"],
                len(item["supporting_evidence_ids"]),
                len(item["contradicting_evidence_ids"]),
            )
            for item in hypotheses
        ] == [
            ("RETRYABLE_MESSAGE", 5, 0),
            ("GENUINE_SHORT_SHIPMENT", 0, 5),
            ("ALREADY_POSTED", 0, 5),
        ]
    assert all(
        item["supporting_evidence_ids"] or item["contradicting_evidence_ids"] for item in hypotheses
    )
    assert all(
        evidence_id.startswith("m5-authority-b-case:")
        for item in hypotheses
        for evidence_id in (
            *item["supporting_evidence_ids"],
            *item["contradicting_evidence_ids"],
        )
    )
    assert payload["m6_aws_proof"]["real_provider_integration"]["outcome_status"] == "DEGRADED"
    assert (
        payload["m6_aws_proof"]["real_provider_integration"]["stable_real_usefulness"]
        == "NOT_PROVEN"
    )
    assert all(
        item["status"] == "NOT_PROVEN"
        for item in payload["m6_aws_proof"]["capabilities"]
        if item["capability_id"].startswith("agentcore_")
    )
    parsed = type(artifact).model_validate_json(json.dumps(payload))
    assert parsed.artifact_digest == artifact.artifact_digest
    if mode == "complete":
        assert parsed.advisory.status == "COMPLETE"
        assert len(parsed.advisory.hypotheses) == 3
        assert (
            parsed.advisory.usefulness_evidence_class
            is WorkspaceEvidenceClass.SCRIPTED_SYNTHETIC_PROOF
        )
    else:
        assert parsed.advisory.status == "DEGRADED"
        assert parsed.advisory.hypotheses == ()
        assert parsed.advisory.usefulness_evidence_class is WorkspaceEvidenceClass.NOT_PROVEN


def test_workspace_rejects_tampered_digest() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    payload = artifact.model_dump(mode="json")
    payload["artifact_digest"] = "tampered"
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        type(artifact).model_validate_json(json.dumps(payload))


def test_scripted_citation_with_unknown_evidence_fails_closed() -> None:
    golden = json.loads((ROOT / "artifacts/golden/golden-v2.json").read_text(encoding="utf-8"))
    claim = golden["scripted_strands_proof"]["profiles"][0]["agent_run"]["investigators"][0][
        "factual_claims"
    ][0]
    claim["evidence_ids"] = ["case-01-retryable-lock-main-path:unknown-record"]
    with pytest.raises(ValueError, match="citation is not admitted"):
        _hypotheses_from_golden(golden, "m5-authority-b-case", {"m5-authority-b-case:erp-receipt"})


def test_scripted_hypothesis_without_evidence_fails_closed() -> None:
    golden = json.loads((ROOT / "artifacts/golden/golden-v2.json").read_text(encoding="utf-8"))
    investigator = golden["scripted_strands_proof"]["profiles"][0]["agent_run"]["investigators"][0]
    investigator["factual_claims"] = []
    with pytest.raises(ValueError, match="no admitted evidence"):
        _hypotheses_from_golden(
            golden,
            "m5-authority-b-case",
            {
                "m5-authority-b-case:erp-receipt",
                "m5-authority-b-case:failed-message",
                "m5-authority-b-case:invoice",
                "m5-authority-b-case:material-documents",
                "m5-authority-b-case:warehouse",
            },
        )


def test_workspace_case_rejects_inconsistent_headline_numbers() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    assert not isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    payload["case"]["missing_quantity"] = 19
    with pytest.raises(ValueError, match="quantities are inconsistent"):
        type(artifact).model_validate_json(json.dumps(payload))


def test_workspace_exposes_final_case_and_initial_decision_as_different_times() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    assert not isinstance(artifact, WorkspaceUnavailable)
    assert artifact.case.status == "CLOSED"
    assert artifact.deterministic_decision.eligibility == "PENDING_APPROVAL"


def test_workspace_is_backed_by_distinct_authoritative_lifecycle_actions() -> None:
    bundle = load_lifecycle_bundle(ROOT)
    assert bundle.schema_version == "AuthorityBLifecycleDemo/v1"
    assert len(bundle.actions) == 2
    assert {item.tool.value for item in bundle.actions} == {
        "restart_receipt_message",
        "release_invoice",
    }
    assert len({item.intent_id for item in bundle.actions}) == 2
    assert len({item.grant_id for item in bundle.actions}) == 2
    assert len({item.effect_id for item in bundle.actions}) == 2
    assert bundle.final_state.case.status.value == "CLOSED"
    assert len(bundle.final_state.enterprise.business_effects) == 2
    complete = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    degraded = build_decision_workspace(ROOT, mode=WorkspaceMode.DEGRADED)
    assert not isinstance(complete, WorkspaceUnavailable)
    assert not isinstance(degraded, WorkspaceUnavailable)
    assert complete.operational_projection_digest == degraded.operational_projection_digest
    assert len(complete.human_control.approvals) == 4
    assert {item.action_id for item in complete.human_control.approvals} == {
        "receipt-restart",
        "invoice-release",
    }


def test_lifecycle_mutation_or_deletion_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / LIFECYCLE_ARTIFACT_PATH
    baseline = json.loads(source.read_text(encoding="utf-8"))
    mutations: tuple[tuple[str, Callable[[dict[str, Any]], object]], ...] = (
        ("intent", lambda value: value["intents"].pop()),
        ("attestation", lambda value: value["attestations"].pop()),
        ("grant", lambda value: value["grants"].pop()),
        ("signature", lambda value: value["grants"][0].update({"signature": "0" * 64})),
        ("version", lambda value: value["decisions"][0].update({"case_version": 99})),
        (
            "parameters",
            lambda value: value["intents"][0]["complete_parameters"].update({"quantity": 99}),
        ),
        ("attempt", lambda value: value["attempts"].pop()),
        ("effect", lambda value: value["effects"].pop()),
        ("verification", lambda value: value["verifications"].pop()),
        ("replay", lambda value: value["replays"].pop()),
        ("final_state", lambda value: value["final_state"].pop("state_digest")),
    )
    for category, mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        _resign_payload(payload)
        candidate = tmp_path / f"invalid-{category}.json"
        candidate.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            load_lifecycle_bundle(ROOT, path=candidate)
        monkeypatch.setattr(workspace_demo, "LIFECYCLE_ARTIFACT_PATH", str(candidate))
        unavailable = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
        assert isinstance(unavailable, WorkspaceUnavailable), category
        assert unavailable.status == "UNAVAILABLE"
        assert unavailable.operational_projection is None

    with pytest.raises(ValueError, match="lifecycle bundle is unreadable"):
        load_lifecycle_bundle(ROOT, path=tmp_path / "absent.json")


def test_invalid_workspace_mode_is_explicitly_unavailable() -> None:
    artifact = build_decision_workspace(ROOT, mode=WorkspaceMode.INVALID)
    assert isinstance(artifact, WorkspaceUnavailable)
    payload = artifact.model_dump(mode="json")
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason_code"] == "LIFECYCLE_BUNDLE_INCOMPLETE"
    assert payload["operational_projection"] is None
    assert payload["human_controls"] is None


def _request(url: str, method: str = "GET") -> tuple[int, bytes, dict[str, str]]:
    try:
        with urlopen(Request(url, method=method), timeout=5) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def test_workspace_server_is_read_only_and_local() -> None:
    try:
        server = DecisionWorkspaceServer(("127.0.0.1", 0), ROOT)
    except PermissionError:
        pytest.skip("the managed test sandbox disallows loopback sockets")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body, headers = _request(f"{base}/api/workspace?mode=complete")
        assert status == 200
        assert json.loads(body)["mode"] == "complete"
        assert headers["Content-Security-Policy"].startswith("default-src 'self'")
        status, body, _headers = _request(f"{base}/api/workspace?mode=degraded")
        assert status == 200
        assert json.loads(body)["advisory"]["status"] == "DEGRADED"
        status, body, _headers = _request(f"{base}/api/workspace?mode=invalid")
        assert status == 200
        unavailable = json.loads(body)
        assert unavailable["status"] == "UNAVAILABLE"
        assert unavailable["operational_projection"] is None
        assert "human_control" not in unavailable
        status, _body, headers = _request(f"{base}/api/workspace?mode=complete", method="POST")
        assert status == 405
        assert headers["Allow"] == "GET"
        status, _body, _headers = _request(f"{base}/api/workspace?mode=unexpected")
        assert status == 400
        status, body, _headers = _request(f"{base}/healthz")
        assert status == 200
        assert json.loads(body)["read_only"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
