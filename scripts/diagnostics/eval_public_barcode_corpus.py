"""Run the shipped browser decoder on downloaded original public fixture bytes.

Keeps failed cases. No product mapping or warehouse effect is inferred from an
optical pass. QR payloads are decoded as data, never opened as URLs.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_decision_workspace_smoke import _CDPBrowser, _chrome, _wait_ui

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "artifacts/fixtures/realistic-receiving-v1"
OUT = ROOT / "artifacts/audits/2026-09-09-public-barcode-corpus-verified.json"


def classify(result: dict, case: dict) -> str:
    if result.get("error") and result["error"] != (
        "Conflicting barcode readings; reduce glare and scan again."
    ):
        return "error"
    if not result["codes"]:
        return "abstain"
    exact = len(result["codes"]) == 1 and all(
        result["codes"][0].get(key) == value
        for key, value in {"rawValue": case["expected_code"], "format": case["format"]}.items()
    )
    return "correct" if not result.get("error") and exact else "wrong"


def main() -> int:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    report = {
        "at": datetime.now(UTC).isoformat(),
        "scope": "Public originals -> shipped optical decoder; no stock writes or camera hardware",
        "manifest_sha256": hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest(),
        "results": [],
    }
    with (
        TemporaryDirectory(prefix="m20-corpus-") as profile,
        _CDPBrowser(_chrome(), Path(profile)) as browser,
    ):
        browser.command("Network.enable")
        browser.command("Network.setCacheDisabled", {"cacheDisabled": True})
        browser.navigate("http://127.0.0.1:8893/?view=dashboard&review=optical-corpus")
        _wait_ui(browser, "Boolean(window.M20Barcode)", "barcode module")
        report["browser"] = browser.command("Browser.getVersion")
        report["code_hashes"] = {}
        for route, local in [
            ("/barcode-capture.js", ROOT / "workspace/barcode-capture.js"),
            (
                "/vendor/zxing-browser.min.js",
                ROOT / "node_modules/@zxing/browser/umd/zxing-browser.min.js",
            ),
        ]:
            served = browser.evaluate(
                "(async()=>{const r=await fetch("
                + json.dumps(route)
                + ",{cache:'no-store'});if(!r.ok)throw Error(r.status);return await r.text();})()"
            )
            actual = hashlib.sha256(served.encode()).hexdigest()
            expected = hashlib.sha256(local.read_bytes()).hexdigest()
            assert actual == expected, f"Served decoder differs: {route}"
            report["code_hashes"][route] = {"served": actual, "local": expected}
        browser.evaluate("(async()=>{window.publicDecode=await M20Barcode.decoder();})()")
        for case in manifest["barcodes"]:
            raw = (FIXTURES / case["file"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == case["sha256"]
            encoded = base64.b64encode(raw).decode()
            result = browser.evaluate(
                """(async()=>{const bytes=Uint8Array.from(atob("""
                + json.dumps(encoded)
                + """), c=>c.charCodeAt(0));
                const img=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
                const c=document.createElement('canvas');
                c.width=img.width;c.height=img.height;c.getContext('2d').drawImage(img,0,0);
                img.close();try {return {codes:await publicDecode(c)};}
                catch(e){return {codes:[],error:e.message};}})()"""
            )
            entry = {
                "id": case["id"],
                "expected": case["expected_code"],
                "expected_format": case["format"],
                "decoded": result["codes"],
                "rejection": result.get("error"),
                "outcome": classify(result, case),
                "passed": classify(result, case) == "correct",
                "fixture_sha256": case["sha256"],
            }
            report["results"].append(entry)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(entry), flush=True)
        report["passed"] = sum(r["passed"] for r in report["results"])
        report["total"] = len(report["results"])
        report["outcomes"] = {
            outcome: sum(r["outcome"] == outcome for r in report["results"])
            for outcome in ["correct", "abstain", "wrong", "error"]
        }
        report["console_messages"] = browser.console_errors()
        OUT.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps({"passed": report["passed"], "total": report["total"], "artifact": str(OUT)})
        )
        return 1 if report["outcomes"]["wrong"] or report["outcomes"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
