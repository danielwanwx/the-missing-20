from __future__ import annotations

from typing import Any

from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
from the_missing_20.agents.live_advisory import AdvisoryDisposition, AdvisoryRun, LiveAdvisoryResult
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentProvider


class _Platform:
    def current(self) -> dict[str, object]:
        return {
            "execution": {
                "status": "VERIFIED",
                "transfer_name": "MAT-STE-2026-00001",
                "invoice_name": "ACC-PINV-2026-00007",
            },
            "diagnosis": {"status": "VERIFIED"},
            "activity": [],
            "correlation": {},
            "integration_receipt": {},
        }


def _settings(provider: AgentProvider) -> Settings:
    return Settings(agent_provider=provider)


def test_gateway_returns_explicit_unavailable_without_bedrock() -> None:
    gateway = DashboardAdvisoryGateway(_Platform(), settings=_settings(AgentProvider.SCRIPTED))  # type: ignore[arg-type]

    response = gateway.ask("What happened to the receipt?")

    assert response["answer"].startswith("Real Strands Agent is not configured")
    assert response["agent_advisory"] == {
        "status": "AGENT_UNAVAILABLE",
        "mode": "real_strands",
        "tool_calls": [],
        "result": None,
    }


def test_gateway_returns_provenanced_real_result() -> None:
    observed: dict[str, Any] = {}

    def runner(*args: Any, **kwargs: Any) -> AdvisoryRun:
        observed.update(kwargs)
        return AdvisoryRun(
            result=LiveAdvisoryResult(
                disposition=AdvisoryDisposition.RECOVERY_COMPLETE,
                evidence_ids=("MAT-STE-2026-00001",),
                reason="The ERP transfer is verified.",
                safe_next_step="Keep the deterministic control plane read-only.",
                write_performed=False,
            ),
            tool_calls=(
                "read_control_context",
                "read_erp_evidence",
                "read_airtable_evidence",
                "read_celigo_evidence",
                "read_collaboration_evidence",
            ),
            provider={"provider": "bedrock"},
            latency_ms=12,
            usage={"request_count": 2},
        )

    gateway = DashboardAdvisoryGateway(
        _Platform(),  # type: ignore[arg-type]
        settings=_settings(AgentProvider.BEDROCK),
        runner=runner,
    )
    response = gateway.ask("Is recovery complete?")

    assert observed["question"] == "Is recovery complete?"
    assert response["answer"] == "The ERP transfer is verified."
    advisory = response["agent_advisory"]
    assert advisory["status"] == "COMPLETE"
    assert advisory["result"]["write_performed"] is False
