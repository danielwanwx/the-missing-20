"""Compose the deterministic M5 Decision Workspace artifacts.

This command performs no network or provider work.  It reads only versioned
synthetic records and the frozen, redacted Authority-B degraded outcome.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    _root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_root / "src"))

from the_missing_20.authority_b.lifecycle import write_lifecycle_bundle  # noqa: E402
from the_missing_20.authority_b.workspace_demo import (  # noqa: E402
    WORKSPACE_MODES,
    WorkspaceMode,
    write_decision_workspace,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts/workspace/decision-workspace-{mode}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=WORKSPACE_MODES, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    modes = (
        (WorkspaceMode(args.mode),)
        if args.mode
        else tuple(WorkspaceMode(item) for item in WORKSPACE_MODES)
    )
    try:
        lifecycle = write_lifecycle_bundle(ROOT)
        print(f"Authority-B lifecycle: PASS ({lifecycle.bundle_digest})")
        for mode in modes:
            output = (
                args.output
                if args.output is not None and len(modes) == 1
                else Path(str(DEFAULT_OUTPUT).format(mode=mode.value))
            )
            write_decision_workspace(ROOT, mode=mode, output=output)
            print(f"Decision Workspace {mode.value}: PASS ({output.relative_to(ROOT)})")
    except (OSError, TypeError, ValueError) as exc:
        print(f"Decision Workspace: BLOCKED ({exc})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
