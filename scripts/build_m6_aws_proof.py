"""Build the offline M6 AWS/AgentCore existing-evidence proof.

The command reads approved local artifacts only.  It never imports an AWS SDK or
creates a provider client, and it records zero new calls and zero new cost.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from the_missing_20.authority_b.aws_proof import (  # noqa: E402
    M6_PROOF_ARTIFACT_PATH,
    M6ProofError,
    write_m6_aws_proof,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        bundle = write_m6_aws_proof(ROOT)
    except (M6ProofError, OSError, TypeError, ValueError) as exc:
        print(f"M6 AWS evidence proof: BLOCKED ({exc})", file=sys.stderr)
        return 2
    print(
        f"M6 AWS evidence proof: PASS ({M6_PROOF_ARTIFACT_PATH}, "
        f"digest={bundle.proof_digest}, provider_calls=0, new_cost_usd=0)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
