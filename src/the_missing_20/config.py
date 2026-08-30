"""Validated runtime configuration with safe local defaults."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from the_missing_20.ports.agent_model import AgentProvider


class ConfigurationError(ValueError):
    """Raised when configuration would make an unsafe or ambiguous run possible."""


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "local"
    aws_region: str = "us-west-2"
    aws_profile: str | None = None
    expected_aws_account_id: str | None = None
    resource_prefix: str = "missing20-dev"
    cleanup_manifest: Path = Path("artifacts/aws/cleanup-manifest.json")
    max_aws_spend_usd: Decimal = Decimal("5.00")
    allow_aws_mutations: bool = False
    agent_provider: AgentProvider = AgentProvider.SCRIPTED
    agentcore_runtime_arn: str | None = None
    agentcore_qualifier: str = "DEFAULT"

    @property
    def provider_mode(self) -> AgentProvider:
        """Compatibility/readability alias for the explicit agent provider mode."""

        return self.agent_provider

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        settings = cls(
            environment=values.get("MISSING20_ENVIRONMENT", "local").strip(),
            aws_region=values.get("MISSING20_AWS_REGION", "us-west-2").strip(),
            aws_profile=_optional(values.get("MISSING20_AWS_PROFILE")),
            expected_aws_account_id=_optional(values.get("MISSING20_EXPECTED_AWS_ACCOUNT_ID")),
            resource_prefix=values.get("MISSING20_RESOURCE_PREFIX", "missing20-dev").strip(),
            cleanup_manifest=Path(
                values.get(
                    "MISSING20_CLEANUP_MANIFEST",
                    "artifacts/aws/cleanup-manifest.json",
                ).strip()
            ),
            max_aws_spend_usd=_parse_decimal(values.get("MISSING20_MAX_AWS_SPEND_USD", "5.00")),
            allow_aws_mutations=_parse_bool(values.get("MISSING20_ALLOW_AWS_MUTATIONS", "0")),
            agent_provider=AgentProvider.parse(
                values.get("MISSING20_AGENT_PROVIDER", AgentProvider.SCRIPTED.value)
            ),
            agentcore_runtime_arn=_optional(values.get("MISSING20_AGENTCORE_RUNTIME_ARN")),
            agentcore_qualifier=values.get("MISSING20_AGENTCORE_QUALIFIER", "DEFAULT").strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.environment:
            raise ConfigurationError("MISSING20_ENVIRONMENT must not be empty")
        if self.aws_region != "us-west-2":
            raise ConfigurationError("AWS experiments are restricted to us-west-2")
        if not self.resource_prefix.startswith("missing20-"):
            raise ConfigurationError("resource prefix must start with 'missing20-'")
        if self.expected_aws_account_id is not None and (
            len(self.expected_aws_account_id) != 12 or not self.expected_aws_account_id.isdigit()
        ):
            raise ConfigurationError("expected AWS account ID must be exactly 12 digits")
        if self.cleanup_manifest.is_absolute():
            raise ConfigurationError("cleanup manifest must be a repository-relative path")
        if ".." in self.cleanup_manifest.parts:
            raise ConfigurationError("cleanup manifest must not escape the repository")
        if self.max_aws_spend_usd <= 0 or self.max_aws_spend_usd > Decimal("20.00"):
            raise ConfigurationError("AWS experiment budget must be greater than 0 and at most $20")
        try:
            AgentProvider.parse(self.agent_provider)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        if not self.agentcore_qualifier:
            raise ConfigurationError("MISSING20_AGENTCORE_QUALIFIER must not be empty")


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    raise ConfigurationError(f"invalid boolean value: {value!r}")


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise ConfigurationError(f"invalid decimal value: {value!r}") from exc
