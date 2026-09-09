"""Run real Strands perception on an explicitly supplied image, without ERP writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from the_missing_20.adapters.erpnext_source import _read_env_file  # noqa: E402
from the_missing_20.agents.photo_receiving import (  # noqa: E402
    StrandsPhotoReader,
    normalize_photo,
)
from the_missing_20.config import Settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--image", type=Path)
    inputs.add_argument(
        "--synthetic-negative",
        action="store_true",
        help="Use a blank, generated image containing no user or business data.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-normalized-input", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env(
        {**_read_env_file(ROOT / ".env"), **os.environ, "MISSING20_AGENT_PROVIDER": "bedrock"}
    )
    if args.synthetic_negative:
        stream = BytesIO()
        Image.new("RGB", (320, 240), "white").save(stream, "PNG")
        photo = normalize_photo(stream.getvalue())
        input_name = "synthetic-empty-frame-not-a-warehouse-photo"
    else:
        photo = normalize_photo(args.image.read_bytes())
        input_name = args.image.name
    result = StrandsPhotoReader(settings)(photo)
    if args.save_normalized_input:
        args.save_normalized_input.write_bytes(photo)
    report = {
        "input_sha256": hashlib.sha256(photo).hexdigest(),
        "input_name": input_name,
        "stock_writes": 0,
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "assessment": result["assessment"],
                "latency_ms": result["latency_ms"],
                "usage": result["usage"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
