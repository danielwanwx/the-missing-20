from decimal import Decimal
from pathlib import Path

import pytest

from the_missing_20.config import ConfigurationError, Settings


def test_settings_default_to_local_and_no_cloud_mutations() -> None:
    settings = Settings.from_env({})

    assert settings.environment == "local"
    assert settings.aws_region == "us-west-2"
    assert settings.cleanup_manifest == Path("artifacts/aws/cleanup-manifest.json")
    assert settings.max_aws_spend_usd == Decimal("5.00")
    assert settings.allow_aws_mutations is False


def test_settings_accept_explicit_safe_aws_context() -> None:
    settings = Settings.from_env(
        {
            "MISSING20_AWS_PROFILE": "missing20-sandbox",
            "MISSING20_EXPECTED_AWS_ACCOUNT_ID": "123456789012",
            "MISSING20_ALLOW_AWS_MUTATIONS": "true",
        }
    )

    assert settings.aws_profile == "missing20-sandbox"
    assert settings.expected_aws_account_id == "123456789012"
    assert settings.allow_aws_mutations is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MISSING20_AWS_REGION", "us-east-1"),
        ("MISSING20_RESOURCE_PREFIX", "demo"),
        ("MISSING20_EXPECTED_AWS_ACCOUNT_ID", "123"),
        ("MISSING20_CLEANUP_MANIFEST", "/tmp/cleanup.json"),
        ("MISSING20_CLEANUP_MANIFEST", "../cleanup.json"),
        ("MISSING20_MAX_AWS_SPEND_USD", "0"),
        ("MISSING20_MAX_AWS_SPEND_USD", "21"),
        ("MISSING20_MAX_AWS_SPEND_USD", "many"),
        ("MISSING20_ALLOW_AWS_MUTATIONS", "sometimes"),
    ],
)
def test_settings_reject_unsafe_or_ambiguous_values(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env({name: value})
