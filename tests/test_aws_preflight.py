import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.aws_preflight import (
    Identity,
    PreflightError,
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


def test_aws_cli_must_be_v2() -> None:
    validate_cli_version("aws-cli/2.36.30 Python/3.14.7 Darwin/24.6.0")

    with pytest.raises(PreflightError, match="CLI v2"):
        validate_cli_version("aws-cli/1.38.0 Python/3.12.0")


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
