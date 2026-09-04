"""Fail-closed gateway from the dashboard to the real read-only advisory agent."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from the_missing_20.adapters.agent_platform import AgentPlatform
from the_missing_20.adapters.strands_models import BedrockNovaProConfig, BedrockNovaProFactory
from the_missing_20.agents.live_advisory import (
    AdvisoryRun,
    AdvisoryUnavailable,
    AdvisoryValidationError,
    live_recovery_packet,
    run_live_advisory,
)
from the_missing_20.config import Settings
from the_missing_20.ports.agent_model import AgentBudget, AgentBudgetLedger, AgentProvider

AdvisoryRunner = Callable[..., AdvisoryRun]


class DashboardAdvisoryGateway:
    """Expose real agent results while making every provider failure explicit."""

    def __init__(
        self,
        platform: AgentPlatform,
        *,
        settings: Settings | None = None,
        runner: AdvisoryRunner = run_live_advisory,
    ) -> None:
        self._platform = platform
        self._settings = settings or Settings.from_env()
        self._runner = runner

    def ask(self, question: str) -> dict[str, object]:
        """Run real advisory chat or return an unmistakably unavailable result."""

        projection = self._platform.current()
        if self._settings.agent_provider is not AgentProvider.BEDROCK:
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="Real Strands Agent is not configured; no fallback answer was generated.",
            )
        try:
            packet = live_recovery_packet(projection)
            run = self._runner(packet, factory=self._factory(), question=question)
        except AdvisoryValidationError:
            return self._unavailable(
                projection,
                code="VALIDATION_FAILED",
                detail="The real Agent response failed safety validation; no conclusion was shown.",
            )
        except (AdvisoryUnavailable, OSError, ValueError):
            return self._unavailable(
                projection,
                code="AGENT_UNAVAILABLE",
                detail="The real Strands Agent is unavailable; no fallback answer was generated.",
            )
        result = run.result.model_dump(mode="json")
        return {
            **projection,
            "answer": f"{result['reason']} Next: {result['safe_next_step']}",
            "agent_advisory": {
                "status": "COMPLETE",
                "mode": "real_strands",
                "provider": run.provider,
                "tool_calls": list(run.tool_calls),
                "latency_ms": run.latency_ms,
                "usage": run.usage,
                "result": result,
            },
        }

    def _factory(self) -> BedrockNovaProFactory:
        budget = AgentBudget(
            max_requests=8,
            max_input_tokens=100_000,
            max_output_tokens=4_000,
            max_output_tokens_per_request=800,
            prior_cost_usd="0",
            incremental_cost_cap_usd="0.08",
            cumulative_cost_cap_usd="0.08",
            per_call_timeout_seconds=45,
            whole_run_timeout_seconds=60,
        )
        return BedrockNovaProFactory(
            BedrockNovaProConfig(
                region=self._settings.aws_region,
                aws_profile=self._settings.aws_profile,
                max_tokens=800,
                temperature=0,
                budget=budget,
            ),
            ledger=AgentBudgetLedger(budget),
        )

    @staticmethod
    def _unavailable(
        projection: Mapping[str, object], *, code: str, detail: str
    ) -> dict[str, object]:
        return {
            **projection,
            "answer": detail,
            "agent_advisory": {
                "status": code,
                "mode": "real_strands",
                "tool_calls": [],
                "result": None,
            },
        }
