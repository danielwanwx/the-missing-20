"""Run the private seven-step judge demo's clean-state acceptance check.

The check validates the persisted package and regenerates deterministic lifecycle/M6/
workspace inputs in a temporary clean repository.  It never starts a server and never
contacts AWS, Bedrock, Nova, or any remote resource.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root))
    sys.path.insert(0, str(_root / "src"))

from the_missing_20.competition.package import (  # noqa: E402
    M7PackageError,
    load_private_audit,
    regenerate_clean_state,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the default clean-state acceptance check (kept for explicit CI use)",
    )
    args = parser.parse_args()
    del args
    try:
        persisted = load_private_audit(ROOT)
        regenerated = regenerate_clean_state(ROOT)
        if persisted.audit_digest != regenerated.audit_digest:
            raise M7PackageError(
                "persisted private audit differs from a clean-state deterministic regeneration"
            )
        print(
            "The Missing 20 private judge demo: PASS "
            f"({persisted.package_status}, {persisted.total_duration_seconds // 60}:"
            f"{persisted.total_duration_seconds % 60:02d}, digest={persisted.audit_digest})"
        )
        for step in persisted.seven_step_story:
            print(
                f"{step.ordinal}. {step.start_seconds:03d}–{step.end_seconds:03d}s "
                f"{step.title} [{step.evidence_class.value}]"
            )
        print("provider_calls=0 new_cost_usd=0 ready_to_submit=false")
    except (M7PackageError, OSError, TypeError, ValueError) as exc:
        print(f"The Missing 20 private judge demo: BLOCKED ({exc})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
