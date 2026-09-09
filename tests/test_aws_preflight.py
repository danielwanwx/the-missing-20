import os
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path

import pytest

from scripts.aws_preflight import (
    Identity,
    PreflightError,
    _identity_failure,
    load_identity,
    login_recovery_message,
    resolve_login_profile,
    validate_cli_version,
    validate_identity,
    validate_mutation_gate,
)
from the_missing_20.config import Settings


def test_identity_rejects_root_credentials() -> None:
    settings = Settings(expected_aws_account_id="123456789012")
    identity = Identity(account_id="123456789012", arn="arn:aws:iam::123456789012:root")

    with pytest.raises(PreflightError, match="root"):
        validate_identity(identity, settings)


def test_identity_rejects_unexpected_account() -> None:
    settings = Settings(expected_aws_account_id="123456789012")
    identity = Identity(
        account_id="999999999999",
        arn="arn:aws:sts::999999999999:assumed-role/Demo/session",
    )

    with pytest.raises(PreflightError, match="expected account"):
        validate_identity(identity, settings)


def test_mutation_gate_requires_explicit_flag(tmp_path: Path) -> None:
    settings = Settings(cleanup_manifest=Path("cleanup.json"))
    (tmp_path / "cleanup.json").write_text('{"version": 1, "resources": []}')

    with pytest.raises(PreflightError, match="explicitly enabled"):
        validate_mutation_gate(settings, tmp_path)


def test_mutation_gate_accepts_valid_manifest(tmp_path: Path) -> None:
    settings = Settings(
        expected_aws_account_id="123456789012",
        cleanup_manifest=Path("cleanup.json"),
        allow_aws_mutations=True,
    )
    (tmp_path / "cleanup.json").write_text(
        """{
          "version": 1,
          "budget_usd": "5.00",
          "resources": [{
            "logical_name": "probe",
            "service": "dynamodb",
            "cleanup_command": ["aws", "dynamodb", "delete-table"]
          }]
        }"""
    )

    validate_mutation_gate(settings, tmp_path)


def test_mutation_gate_rejects_empty_cleanup_plan(tmp_path: Path) -> None:
    settings = Settings(cleanup_manifest=Path("cleanup.json"), allow_aws_mutations=True)
    (tmp_path / "cleanup.json").write_text('{"version": 1, "budget_usd": "5.00", "resources": []}')

    with pytest.raises(PreflightError, match="planned mutable resource"):
        validate_mutation_gate(settings, tmp_path)


def test_aws_cli_must_support_temporary_login() -> None:
    validate_cli_version("aws-cli/2.36.30 Python/3.14.7 Darwin/24.6.0")
    validate_cli_version("aws-cli/2.32.0 Python/3.13.7 Darwin/24.6.0")

    with pytest.raises(PreflightError, match="2.32.0"):
        validate_cli_version("aws-cli/1.38.0 Python/3.12.0")

    with pytest.raises(PreflightError, match="2.32.0"):
        validate_cli_version("aws-cli/2.31.9 Python/3.13.7 Darwin/24.6.0")


def test_cli_refuses_a_run_without_one_time_confirmation() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "src"
    completed = subprocess.run(
        [sys.executable, "scripts/aws_preflight.py", "--confirm", "0"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 2
    assert "AWS_CONFIRM=1" in completed.stderr


def test_recovery_targets_source_login_not_assumed_role() -> None:
    config = ConfigParser(interpolation=None)
    config.read_string("""
[profile missing20-sandbox]
role_arn = arn:aws:iam::523356960326:role/Missing20DeveloperRole
source_profile = missing20-login
[profile missing20-login]
login_session = arn:aws:iam::523356960326:user/missing20/missing20-dev
""")
    profile = resolve_login_profile("missing20-sandbox", config)
    assert profile == "missing20-login"
    message = login_recovery_message(profile, "us-west-2")
    assert "aws login --profile missing20-login --region us-west-2" in message
    assert "aws login --profile missing20-sandbox" not in message
    assert "--remote" not in message
    assert "fresh" in message and "running" in message


def test_recovery_rejects_cycle_or_ambiguous_role_profile() -> None:
    config = ConfigParser(interpolation=None)
    config.read_string("""
[profile a]
role_arn = role-a
source_profile = b
[profile b]
role_arn = role-b
source_profile = a
""")
    with pytest.raises(PreflightError, match="cycle"):
        resolve_login_profile("a", config)
    config.remove_option("profile a", "source_profile")
    with pytest.raises(PreflightError, match="source_profile"):
        resolve_login_profile("a", config)


def test_missing_login_configuration_does_not_invent_authentication_method() -> None:
    with pytest.raises(PreflightError, match="login_session"):
        resolve_login_profile("unknown", ConfigParser())


def test_expired_identity_check_has_fresh_source_login_advice_without_leaking_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    config.write_text("""
[profile missing20-sandbox]
role_arn = arn:aws:iam::523356960326:role/Missing20DeveloperRole
source_profile = missing20-login
[profile missing20-login]
login_session = project-user
""")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setattr("scripts.aws_preflight.shutil.which", lambda _: "/usr/bin/aws")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] <= 45
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "aws-cli/2.36.30", "")
        raise subprocess.CalledProcessError(
            255, command, stderr="login expired: https://secret-auth-url.example?token=secret"
        )

    monkeypatch.setattr("scripts.aws_preflight.subprocess.run", run)
    with pytest.raises(PreflightError) as error:
        load_identity(Settings(aws_profile="missing20-sandbox", aws_region="us-west-2"))
    assert "aws login --profile missing20-login" in str(error.value)
    assert "secret" not in str(error.value)
    assert len(calls) == 2  # Read-only preflight never logs out or starts a login.


@pytest.mark.parametrize(
    "detail", ["ThrottlingException: token bucket exhausted", "HTTP 429", "Rate exceeded"]
)
def test_provider_throttling_does_not_request_a_new_login(detail: str) -> None:
    error = _identity_failure(
        Settings(), subprocess.CalledProcessError(255, ["aws"], stderr=detail)
    )
    assert "rate-limited" in str(error)
    assert "aws login" not in str(error)


def test_generic_token_word_does_not_prove_credentials_expired() -> None:
    error = _identity_failure(
        Settings(),
        subprocess.CalledProcessError(
            255, ["aws"], stderr="token service endpoint connection failed"
        ),
    )
    assert "network" in str(error)
