#!/usr/bin/env python3
"""Fetch official NWS and NOAA context once and save a redacted smoke artifact.

This command is intentionally separate from deterministic tests.  It performs
one public read from each configured HTTP source, never calls AWS, and never
requires or emits a credential.  A failed public source is recorded as
``DEGRADED`` in the artifact rather than replaced with invented data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from the_missing_20.live_sources import (  # noqa: E402
    AISStreamAdapter,
    LiveSourceRegistry,
    LiveSourceStatus,
    NOAAWaterLevelAdapter,
    NWSAlertsAdapter,
)

ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "live-sources" / "smoke.json",
        help="public-only JSON artifact path",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    registry = LiveSourceRegistry(
        (NWSAlertsAdapter(), NOAAWaterLevelAdapter(), AISStreamAdapter())
    )
    try:
        registry.poll_once(force=True)
        payload = registry.current(poll=False)
    finally:
        registry.close()

    sources = cast(list[dict[str, object]], payload["sources"])
    http_sources = {
        str(source["source_id"]): source
        for source in sources
        if source["source_id"] != "aisstream-port-los-angeles"
    }
    http_ok = all(
        str(source.get("status"))
        in {LiveSourceStatus.CONNECTED.value, LiveSourceStatus.STALE.value}
        for source in http_sources.values()
    ) and len(http_sources) == 2
    artifact = {
        "schema_version": payload["schema_version"],
        "status": "PASS" if http_ok else "DEGRADED",
        "captured_at": datetime.now(UTC).isoformat(),
        "provider_calls": False,
        "new_cost_usd": 0,
        "private_only": True,
        "network": "official public NWS and NOAA one-shot read",
        "scope": payload["scope"],
        "sources": sources,
        "risk": payload["risk"],
        "event_cursor": payload["event_cursor"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"live source smoke: {artifact['status']} ({args.output})")
    return 0 if http_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
