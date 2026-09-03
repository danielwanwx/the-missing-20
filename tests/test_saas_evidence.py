from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

from the_missing_20.adapters.saas_evidence import SaaSEvidenceConfig, SaaSEvidenceSource


def test_environment_prefers_the_restricted_demo_operator_token(
    monkeypatch, tmp_path: Path
) -> None:
    for name in ("AIRTABLE_DEMO_OPERATOR_TOKEN", "AIRTABLE_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "AIRTABLE_DEMO_OPERATOR_TOKEN=demo-operator-token\n"
        "AIRTABLE_API_TOKEN=observer-token\n"
        "AIRTABLE_BASE_ID=app-demo\n",
        encoding="utf-8",
    )

    source = SaaSEvidenceSource.from_environment(repository_root=tmp_path)

    assert source._config.airtable_token == "demo-operator-token"


def _transport(request: Request, _timeout: float) -> bytes:
    assert "secret" not in request.full_url
    authorization = request.get_header("Authorization")
    url = request.full_url
    if "api.airtable.com" in url:
        assert authorization == "Bearer airtable-secret"
        payload = {
            "records": [
                {
                    "id": "rec-release",
                    "fields": {
                        "Release Correlation ID": "M20-TEST",
                        "Supplier Lot": "LOT-A",
                        "Disposition": "APPROVED",
                        "Approved Quantity": 8,
                    },
                }
            ]
        }
    elif "celigo.example" in url:
        assert authorization == "Bearer celigo-secret"
        payload = {"runId": "run-8", "status": "FAILED", "erpAcknowledged": False}
    elif "jira.example" in url:
        assert authorization and authorization.startswith("Basic ")
        payload = {
            "issues": [
                {
                    "key": "CAPA-8",
                    "fields": {
                        "summary": "Release sync investigation M20-TEST",
                        "status": {"name": "Investigating"},
                    },
                }
            ]
        }
    elif "slack.com" in url:
        assert authorization == "Bearer slack-secret"
        payload = {"ok": True, "messages": [{"ts": "1.2", "text": "M20-TEST incident opened"}]}
    else:  # pragma: no cover - proves the adapter stays in its declared scope
        raise AssertionError(url)
    return json.dumps(payload).encode()


def test_saas_projection_is_correlation_scoped_and_redacts_credentials() -> None:
    source = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-TEST",
            airtable_token="airtable-secret",
            airtable_base_id="app-demo",
            celigo_evidence_url="https://celigo.example/run",
            celigo_api_token="celigo-secret",
            jira_base_url="https://jira.example",
            jira_email="demo@example.com",
            jira_api_token="jira-secret",
            jira_project_key="CAPA",
            slack_bot_token="slack-secret",
            slack_channel_id="C123",
        ),
        transport=_transport,
    )

    projection = source.current()

    assert projection["status"] == "CONNECTED"
    assert projection["read_only"] is True
    assert [item["status"] for item in projection["activity"]] == [
        "VERIFIED",
        "FAILED",
        "VERIFIED",
        "VERIFIED",
    ]
    encoded = json.dumps(projection)
    assert "secret" not in encoded
    assert "M20-TEST" in encoded


def test_saas_projection_is_explicit_when_nothing_is_configured() -> None:
    projection = SaaSEvidenceSource(SaaSEvidenceConfig(correlation_id="M20-TEST")).current()

    assert projection["status"] == "NOT_CONFIGURED"
    assert {item["status"] for item in projection["activity"]} == {"NOT_CONFIGURED"}


def test_celigo_flow_list_reports_control_plane_state() -> None:
    def flow_transport(request: Request, _timeout: float) -> bytes:
        assert request.get_header("Authorization") == "Bearer celigo-secret"
        assert request.full_url == "https://api.integrator.io/v1/flows"
        return json.dumps(
            [
                {"_id": "other", "name": "Other flow", "disabled": False},
                {
                    "_id": "flow-quality-release",
                    "name": "Notify Slack channel when quality release is held",
                    "disabled": True,
                },
            ]
        ).encode()

    source = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-TEST",
            celigo_evidence_url="https://api.integrator.io/v1/flows",
            celigo_api_token="celigo-secret",
            celigo_flow_id="flow-quality-release",
        ),
        transport=flow_transport,
    )

    celigo = next(
        item
        for item in source.current()["sources"]
        if item["source_id"] == "celigo-quality-release"
    )

    assert celigo["status"] == "HELD"
    assert celigo["record_id"] == "flow-quality-release"
    assert celigo["label"] == "Flow control-plane read · DISABLED"
    assert "2 account flows visible" in celigo["detail"]


def test_celigo_direct_run_exposes_only_the_tuple_needed_for_receipt_validation() -> None:
    def receipt_transport(_request: Request, _timeout: float) -> bytes:
        return json.dumps(
            {
                "runId": "run-20",
                "status": "COMPLETED",
                "erpAcknowledged": True,
                "correlationId": "M20-TEST",
                "purchaseOrder": "PO-20",
                "purchaseReceipt": "PR-20",
                "purchaseInvoice": "PI-20",
                "supplierLot": "LOT-20",
                "certificateId": "CERT-20",
                "quantity": 8,
                "evidenceRevision": "rev-3",
                "unrelated_secret": "must-not-escape",
            }
        ).encode()

    source = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-TEST",
            celigo_evidence_url="https://celigo.example/run",
            celigo_api_token="celigo-secret",
        ),
        transport=receipt_transport,
    )

    celigo = next(
        item
        for item in source.current()["sources"]
        if item["source_id"] == "celigo-quality-release"
    )

    assert celigo["status"] == "VERIFIED"
    assert celigo["evidence_kind"] == "RUN_RECEIPT"
    assert celigo["erp_acknowledged"] is True
    assert celigo["correlation"] == {
        "case_id": "M20-TEST",
        "purchase_order": "PO-20",
        "purchase_receipt": "PR-20",
        "purchase_invoice": "PI-20",
        "supplier_lot": "LOT-20",
        "certificate_id": "CERT-20",
        "quantity": 8,
        "evidence_revision": "rev-3",
    }
    assert "must-not-escape" not in json.dumps(celigo)


def test_jira_scoped_token_uses_gateway_bearer_authentication() -> None:
    requests: list[Request] = []

    def gateway_transport(request: Request, _timeout: float) -> bytes:
        requests.append(request)
        return json.dumps(
            {
                "issues": [
                    {
                        "key": "QRC-1",
                        "fields": {
                            "summary": "CAPA M20-TEST",
                            "status": {"name": "To Do"},
                        },
                    }
                ]
            }
        ).encode()

    source = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-TEST",
            jira_api_token="scoped-secret",
            jira_project_key="QRC",
            jira_cloud_id="18d3438e-e912-48dd-b2f8-0fc043c78ba7",
        ),
        transport=gateway_transport,
    )

    jira = next(item for item in source.current()["sources"] if item["source_id"] == "jira-capa")

    assert jira["status"] == "VERIFIED"
    assert len(requests) == 1
    assert requests[0].full_url.startswith(
        "https://api.atlassian.com/ex/jira/18d3438e-e912-48dd-b2f8-0fc043c78ba7/"
    )
    assert requests[0].get_header("Authorization") == "Bearer scoped-secret"


def test_jira_scoped_token_rejects_invalid_cloud_id() -> None:
    source = SaaSEvidenceSource(
        SaaSEvidenceConfig(
            correlation_id="M20-TEST",
            jira_api_token="scoped-secret",
            jira_project_key="QRC",
            jira_cloud_id="not-a-cloud-id",
        ),
    )

    jira = next(item for item in source.current()["sources"] if item["source_id"] == "jira-capa")

    assert jira["status"] == "DEGRADED"
    assert jira["detail"] == "Jira cloud ID is invalid."
