"""Capture the current live Case Console projection as immutable release evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:8888/api/v1/agent-platform"
DEFAULT_OUTPUT = ROOT / "artifacts" / "audits" / "2026-09-07-current-hero-live-snapshot.json"


def _read_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:  # noqa: S310 - explicit local release endpoint
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("release endpoint did not return a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        payload = _read_json(args.url)
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        print(f"Current hero capture: BLOCKED ({exc})")
        return 2

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Current hero capture: PASS ({output.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
