from pathlib import Path

import pytest
from test_live_advisory_gateway import _settings

from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import DashboardAdvisoryGateway
from the_missing_20.agents.live_advisory import AdvisoryValidationError
from the_missing_20.ports.agent_model import AgentProvider


def test_failed_decline_survives_followups_truncation_and_restart(tmp_path: Path):
    seen = []

    def runner(packet, **kwargs):
        seen.append((packet, kwargs["question"]))
        error = AdvisoryValidationError("rejected")
        error.diagnostics = [{"candidate": {"reason": "UNSAFE PRIVATE CANDIDATE"}}]
        raise error

    path = tmp_path / "case.db"
    platform = AmbiguousCasePlatform(store_path=path)
    gateway = DashboardAdvisoryGateway(
        platform, settings=_settings(AgentProvider.BEDROCK), runner=runner
    )
    rejected = gateway.ask("I decline execution. Continue with read-only investigation.")
    assert "UNSAFE PRIVATE CANDIDATE" not in str(rejected)
    assert platform.current()["human_intent"]["read_only_requested"] is True
    for index in range(13):
        gateway.ask(f"Explain source evidence {index}")
    restarted = AmbiguousCasePlatform(store_path=path)
    gateway = DashboardAdvisoryGateway(
        restarted, settings=_settings(AgentProvider.BEDROCK), runner=runner
    )
    gateway.ask("What evidence should I look at next?")
    assert seen[-1][0]["read_only_requested"] is True
    assert "decline" in seen[-1][1].lower()
    assert restarted.current()["execution"]["status"] not in {"VERIFYING", "VERIFIED"}
    assert len(restarted.current()["human_requests"]) <= 12


@pytest.mark.parametrize("provider", [AgentProvider.BEDROCK, AgentProvider.SCRIPTED])
def test_source_or_provider_outage_cannot_discard_human_request(provider):
    platform = AmbiguousCasePlatform()
    gateway = DashboardAdvisoryGateway(
        platform,
        settings=_settings(provider),
        runner=lambda *a, **k: (_ for _ in ()).throw(OSError()),
    )
    gateway.ask("Do not execute. Only inspect evidence.")
    assert platform.current()["human_intent"]["read_only_requested"] is True
