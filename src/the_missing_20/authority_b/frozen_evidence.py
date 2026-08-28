"""Source-controlled anchor for the one consumed Authority-B evidence bundle.

The JSON records carry their own schemas and (where applicable) self-digests, but
self-digests alone do not prevent a coordinated rewrite followed by a fresh rehash.
These four bytes-level SHA-256 values are intentionally reviewed with the source and
are checked before the Golden composer can promote the disclosed-degradation result.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Final

AUTHORITY_B_FROZEN_EVIDENCE_VERSION: Final = "authority-b-frozen-evidence/v1"

# Paths are repository-relative and remain independent of the current working
# directory.  Values cover the exact redacted bytes, including the final newline.
AUTHORITY_B_FROZEN_EVIDENCE_DIGESTS: Final[Mapping[str, str]] = {
    "artifacts/agent/authority-b-attempt-claim-v1.json": (
        "fa90b8b83089516f5ba2aa48293ebe1833a0490bc92d98f4b2488cd407be29dc"
    ),
    "artifacts/agent/authority-b-failure-v1.json": (
        "6e1d6830f15e34c8183e4be25e6406a755f0e89ddfd7247d7ae57f7d94f32ed0"
    ),
    "artifacts/agent/authority-b-advisory-v1.json": (
        "1d6c6c6cb6e3998d4412407558dbc934d4eb04cf2d54d7ad2655caa7dc77ad53"
    ),
    "artifacts/agent/authority-b-usefulness-proof-v1.json": (
        "f1a961dcafa34fb6936f6b466556720891bebbc4023081a0d00b4d1a12599469"
    ),
}


def frozen_evidence_digest(path: Path) -> str:
    """Return the bytes-level digest used by the frozen evidence gate."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_evidence_matches(repository_root: Path) -> bool:
    """Check every required file against the source-controlled byte anchors."""

    try:
        return all(
            frozen_evidence_digest(repository_root / relative_path) == expected
            for relative_path, expected in AUTHORITY_B_FROZEN_EVIDENCE_DIGESTS.items()
        )
    except OSError:
        return False


__all__ = [
    "AUTHORITY_B_FROZEN_EVIDENCE_DIGESTS",
    "AUTHORITY_B_FROZEN_EVIDENCE_VERSION",
    "frozen_evidence_digest",
    "frozen_evidence_matches",
]
