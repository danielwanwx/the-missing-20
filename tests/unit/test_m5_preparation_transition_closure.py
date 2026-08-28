from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from the_missing_20.adapters.local_signer import LocalSigner
from the_missing_20.authority_b import workspace_demo
from the_missing_20.authority_b.lifecycle import (
    LIFECYCLE_ARTIFACT_PATH,
    load_lifecycle_bundle,
)
from the_missing_20.authority_b.models import canonical_json
from the_missing_20.authority_b.workspace_demo import (
    WorkspaceMode,
    WorkspaceUnavailable,
    build_decision_workspace,
)

ROOT = Path(__file__).resolve().parents[2]


def _rehash(payload: dict[str, Any]) -> None:
    payload["bundle_digest"] = hashlib.sha256(
        canonical_json(
            {key: value for key, value in payload.items() if key != "bundle_digest"}
        ).encode("utf-8")
    ).hexdigest()


def _candidate(tmp_path: Path, payload: dict[str, Any], name: str) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _assert_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    name: str,
) -> None:
    _rehash(payload)
    path = _candidate(tmp_path, payload, name)
    with pytest.raises(ValueError):
        load_lifecycle_bundle(ROOT, path=path)
    monkeypatch.setattr(workspace_demo, "LIFECYCLE_ARTIFACT_PATH", str(path))
    result = build_decision_workspace(ROOT, mode=WorkspaceMode.COMPLETE)
    assert isinstance(result, WorkspaceUnavailable)
    assert result.status == "UNAVAILABLE"
    assert result.operational_projection is None


def test_generated_bundle_persists_case_events_and_exact_preparation_chain() -> None:
    bundle = load_lifecycle_bundle(ROOT)
    assert len(bundle.case_events) == 10
    assert len(bundle.preparation_transitions) == 5
    assert tuple(item.new_version for item in bundle.case_events) == tuple(range(1, 11))
    assert bundle.actions[0].preparation_transition_ids == tuple(
        item.transition_id
        for item in bundle.preparation_transitions
        if item.action_id == "receipt-restart"
    )
    assert bundle.actions[1].preparation_transition_ids == tuple(
        item.transition_id
        for item in bundle.preparation_transitions
        if item.action_id == "invoice-release"
    )


@pytest.mark.parametrize(
    "name,mutate",
    (
        (
            "missing_preparation",
            lambda p: p["preparation_transitions"].pop(),
        ),
        (
            "extra_preparation",
            lambda p: p["preparation_transitions"].append(
                deepcopy(p["preparation_transitions"][0])
                | {"transition_id": "preparation:attacker-extra"}
            ),
        ),
        (
            "reordered_preparation",
            lambda p: p["actions"][0]["preparation_transition_ids"].reverse(),
        ),
        (
            "cross_intent_preparation",
            lambda p: p["actions"][0]["preparation_transition_ids"].__setitem__(
                0, p["actions"][1]["preparation_transition_ids"][0]
            ),
        ),
        (
            "event_type_substitution",
            lambda p: p["case_events"][1].update({"event": "INVOICE_APPROVAL_REQUESTED"}),
        ),
        (
            "event_version_offset",
            lambda p: p["case_events"][2].update({"prior_version": 99, "new_version": 100}),
        ),
        (
            "event_status_offset",
            lambda p: p["case_events"][2].update(
                {"prior_status": "INVESTIGATING", "new_status": "RECEIPT_RESTART_RECOMMENDED"}
            ),
        ),
        (
            "execution_start_discontinuity",
            lambda p: p["case_events"][4].update({"prior_version": 99, "new_version": 100}),
        ),
        (
            "coordinated_bridge_policy_rewrite",
            lambda p: (
                p["bridge_grants"][0].update({"case_version": 5}),
                p["policy_decisions"][0].update({"case_version": 5}),
                p["bridge_grants"][0].update(
                    {
                        "action_digest": "f" * 64,
                        "signature": "pending",
                    }
                ),
            ),
        ),
        (
            "event_digest_rewrite",
            lambda p: p["preparation_transitions"][0].update({"event_digest": "0" * 64}),
        ),
        (
            "whole_bundle_rehash_only",
            lambda p: p["case_events"][3].update({"idempotency_key": "attacker"}),
        ),
    ),
)
def test_preparation_and_combined_closure_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    payload = json.loads((ROOT / LIFECYCLE_ARTIFACT_PATH).read_text(encoding="utf-8"))
    mutate(payload)
    _assert_unavailable(tmp_path, monkeypatch, payload, name)


def test_coordinated_bridge_policy_rewrite_cannot_pass_with_valid_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads((ROOT / LIFECYCLE_ARTIFACT_PATH).read_text(encoding="utf-8"))
    bridge = payload["bridge_grants"][0]
    bridge["case_version"] = 5
    bridge["action_digest"] = hashlib.sha256(
        canonical_json(
            {
                "case_id": bridge["case_id"],
                "case_version": 5,
                "principal_id": bridge["principal_id"],
                "role": bridge["role"],
                "tool": bridge["tool"],
                "parameters": bridge["complete_parameters"],
                "evidence_digest": bridge["evidence_digest"],
            }
        ).encode()
    ).hexdigest()
    unsigned = dict(bridge)
    unsigned.pop("signature")
    bridge["signature"] = LocalSigner(b"missing20-authority-b-m5-lifecycle").sign(
        canonical_json(unsigned)
    )
    payload["policy_decisions"][0]["case_version"] = 5
    _assert_unavailable(tmp_path, monkeypatch, payload, "valid-resigned-offset")


def test_reissued_expired_quorum_and_bridge_grants_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.loads((ROOT / LIFECYCLE_ARTIFACT_PATH).read_text(encoding="utf-8"))
    secret = LocalSigner(b"missing20-authority-b-m5-lifecycle")
    intent = payload["intents"][0]
    grant = payload["grants"][0]
    bridge = payload["bridge_grants"][0]
    expiry = "2026-08-27T00:00:30Z"
    execution_time = "2026-08-27T00:01:00Z"

    intent["expires_at"] = expiry
    intent_immutable = {
        key: value for key, value in intent.items() if key not in {"intent_digest", "status"}
    }
    intent["intent_digest"] = hashlib.sha256(
        canonical_json(intent_immutable).encode("utf-8")
    ).hexdigest()
    for attestation in payload["attestations"][:2]:
        attestation["intent_digest"] = intent["intent_digest"]
        attestation["attestation_digest"] = hashlib.sha256(
            canonical_json(
                {key: value for key, value in attestation.items() if key != "attestation_digest"}
            ).encode("utf-8")
        ).hexdigest()
    grant["intent_digest"] = intent["intent_digest"]
    grant["expires_at"] = expiry
    grant_immutable = {
        key: value for key, value in grant.items() if key not in {"grant_digest", "signature"}
    }
    grant["grant_digest"] = hashlib.sha256(
        canonical_json(grant_immutable).encode("utf-8")
    ).hexdigest()
    grant_unsigned = {key: value for key, value in grant.items() if key != "signature"}
    grant["signature"] = secret.sign(canonical_json(grant_unsigned))
    bridge["expires_at"] = expiry
    bridge_unsigned = {key: value for key, value in bridge.items() if key != "signature"}
    bridge["signature"] = secret.sign(canonical_json(bridge_unsigned))

    payload["attempts"][0]["reserved_at"] = execution_time
    payload["attempts"][0]["completed_at"] = execution_time
    payload["policy_decisions"][0]["decided_at"] = execution_time
    payload["verifications"][0]["executed_at"] = execution_time
    payload["effects"][0]["committed_at"] = execution_time
    payload["rereads"][0]["observed_at"] = execution_time
    payload["rereads"][1]["observed_at"] = execution_time
    payload["replays"][0]["receipt"] = deepcopy(payload["verifications"][0])
    payload["replays"][0]["receipt_digest"] = hashlib.sha256(
        canonical_json(payload["replays"][0]["receipt"]).encode("utf-8")
    ).hexdigest()
    _assert_unavailable(tmp_path, monkeypatch, payload, "expired-reissued-grant")
