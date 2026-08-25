"""Read-only AWS identity and safety preflight for bounded experiments."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from the_missing_20.config import ConfigurationError, Settings


class PreflightError(RuntimeError):
    """Raised when an AWS experiment must not proceed."""


@dataclass(frozen=True, slots=True)
class Identity:
    account_id: str
    arn: str


def validate_identity(identity: Identity, settings: Settings) -> None:
    if identity.arn.endswith(":root"):
        raise PreflightError("root AWS credentials are forbidden")
    if settings.expected_aws_account_id is None:
        raise PreflightError("MISSING20_EXPECTED_AWS_ACCOUNT_ID is required")
    if identity.account_id != settings.expected_aws_account_id:
        raise PreflightError("AWS account does not match the expected account")


def validate_mutation_gate(settings: Settings, repository_root: Path) -> None:
    if not settings.allow_aws_mutations:
        raise PreflightError("MISSING20_ALLOW_AWS_MUTATIONS must be explicitly enabled")
    manifest = repository_root / settings.cleanup_manifest
    if not manifest.is_file():
        raise PreflightError("cleanup manifest is missing")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("resources"), list):
        raise PreflightError("cleanup manifest has an invalid schema")
    if str(payload.get("budget_usd")) != str(settings.max_aws_spend_usd):
        raise PreflightError("cleanup manifest budget does not match configured budget")
    resources = payload["resources"]
    if not resources:
        raise PreflightError("cleanup manifest must list every planned mutable resource")
    for resource in resources:
        if not isinstance(resource, dict):
            raise PreflightError("cleanup manifest resource entries must be objects")
        if not all(resource.get(field) for field in ("logical_name", "service", "cleanup_command")):
            raise PreflightError("each resource needs a logical name, service, and cleanup command")
        if not isinstance(resource["cleanup_command"], list):
            raise PreflightError("cleanup command must be an argument list")


def validate_cli_version(version_output: str) -> None:
    if not version_output.startswith("aws-cli/2."):
        raise PreflightError("AWS CLI v2 is required")


def load_identity(settings: Settings) -> Identity:
    aws = shutil.which("aws")
    if aws is None:
        raise PreflightError("AWS CLI v2 is not installed")
    if settings.aws_profile is None:
        raise PreflightError("MISSING20_AWS_PROFILE is required")

    version = subprocess.run([aws, "--version"], check=True, capture_output=True, text=True)
    validate_cli_version(version.stdout or version.stderr)

    command = [
        aws,
        "sts",
        "get-caller-identity",
        "--profile",
        settings.aws_profile,
        "--region",
        settings.aws_region,
        "--output",
        "json",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload: dict[str, Any] = json.loads(completed.stdout)
    return Identity(account_id=str(payload["Account"]), arn=str(payload["Arn"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", choices=("0", "1"), default="0")
    parser.add_argument("--mutation-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.confirm != "1":
            raise PreflightError("set AWS_CONFIRM=1 for this individual preflight run")
        settings = Settings.from_env()
        identity = load_identity(settings)
        validate_identity(identity, settings)
        if args.mutation_check:
            validate_mutation_gate(settings, Path.cwd())
    except (ConfigurationError, PreflightError, subprocess.SubprocessError, KeyError) as exc:
        print(f"AWS preflight: BLOCKED ({exc})", file=sys.stderr)
        return 2

    print("AWS preflight: PASS (read-only identity and account boundary verified)")
    print("AWS mutations remain disabled unless the explicit mutation gate is checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
