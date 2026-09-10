"""Resume an existing goods manifest and its durable workflow, never reseed it."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8893)
    parser.add_argument("--enable-handoffs", action="store_true")
    parser.add_argument(
        "--enable-normal-billing",
        action="store_true",
        help="enable the separately guarded R4 synthetic supplier-bill console action",
    )
    parser.add_argument(
        "--pause-auto-prepare",
        action="store_true",
        help="Require an explicit draft action; does not disable evidence or handoff processing",
    )
    args = parser.parse_args()
    runtime = args.runtime_directory.resolve()
    manifest_path = runtime / "receiving-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    os.environ.update(
        {
            "MISSING20_CASE_CONSOLE_SOURCE": "live",
            "MISSING20_AGENT_PROVIDER": "bedrock",
            "MISSING20_AWS_PROFILE": "missing20-sandbox",
            "MISSING20_ENVIRONMENT": "demo",
            "MISSING20_AGENT_WORKFLOW": "single",
            "MISSING20_LIVE_SOURCES_AUTOSTART": "0",
            "MISSING20_CASE_ID": manifest["case_id"],
            "MISSING20_QUALITY_RELEASE_CORRELATION_ID": manifest["case_id"],
            "MISSING20_ERPNEXT_PURCHASE_ORDER": manifest["purchase_order"],
            "MISSING20_ERPNEXT_PURCHASE_RECEIPT": "",
            "MISSING20_ERPNEXT_PURCHASE_INVOICE": "",
            "MISSING20_ERPNEXT_CUSTOMER_PO": "",
            "MISSING20_PHOTO_PURCHASE_ORDER": manifest["purchase_order"],
            "MISSING20_PHOTO_DRAFTS_ENABLED": "1",
            "MISSING20_PHOTO_AUTO_PREPARE": "0" if args.pause_auto_prepare else "1",
            "MISSING20_RECEIVING_HANDOFF_ENABLED": "1" if args.enable_handoffs else "0",
            "MISSING20_RECEIVING_MANIFEST": str(manifest_path),
        }
    )
    if args.enable_normal_billing:
        os.environ.setdefault(
            "MISSING20_NORMAL_BILLING_SOURCE_READ",
            "/private/tmp/m20-r4-billing-source-current-read-02.json",
        )
    sys.path[:0] = [str(ROOT), str(ROOT / "src")]
    from scripts.decision_workspace_server import main as serve

    sys.argv = [
        "decision_workspace_server",
        "--runtime-directory",
        str(runtime),
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
    ]
    if args.enable_normal_billing:
        sys.argv.append("--enable-normal-billing")
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
