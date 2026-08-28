"""Audit or write the private, offline M7 competition package.

The default ``--check`` path is fail-closed.  ``--write`` only writes the local
redacted audit artifact after the same checks pass.  Neither mode calls AWS, a model,
or a network resource.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from the_missing_20.competition.package import (  # noqa: E402
    M7_AUDIT_ARTIFACT_PATH,
    M7PackageError,
    load_private_audit,
    write_private_audit,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="validate the persisted audit and every package source (the default)",
    )
    action.add_argument(
        "--write",
        action="store_true",
        help="rebuild and persist the local private audit after validation",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.write:
            audit = write_private_audit(root, output=args.output)
            destination = args.output or root / M7_AUDIT_ARTIFACT_PATH
            print(
                "M7 private competition audit: PASS "
                f"({destination.relative_to(root)}, digest={audit.audit_digest}, "
                "provider_calls=0, new_cost_usd=0, private_only=true)"
            )
        else:
            audit = load_private_audit(root, path=args.output)
            print(
                "M7 private competition audit: PASS "
                f"(digest={audit.audit_digest}, status={audit.package_status}, "
                "provider_calls=0, new_cost_usd=0)"
            )
    except (M7PackageError, OSError, TypeError, ValueError) as exc:
        print(f"M7 private competition audit: BLOCKED ({exc})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
