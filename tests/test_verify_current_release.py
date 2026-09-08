from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_current_release.py"
PROOF = ROOT / "artifacts" / "audits" / "2026-09-07-current-hero-proof.json"
CAPTURE = ROOT / "artifacts" / "audits" / "2026-09-07-current-hero-live-snapshot.json"


def _run(proof: Path, capture: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MISSING20_RELEASE_PROOF"] = str(proof)
    env["MISSING20_RELEASE_CAPTURE"] = str(capture)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_current_release_verifier_accepts_committed_live_capture() -> None:
    result = _run(PROOF, CAPTURE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Current hero release: PASS" in result.stdout


def test_current_release_verifier_rejects_tampered_capture(tmp_path: Path) -> None:
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    capture["value_proof"]["observed"]["billed_revenue"] = 999999.0

    proof_path = tmp_path / "proof.json"
    capture_path = tmp_path / "capture.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    capture_path.write_text(json.dumps(capture), encoding="utf-8")

    digest_result = _run(proof_path, capture_path)
    assert digest_result.returncode == 2
    assert "digest does not match" in digest_result.stdout

    proof["source_capture"]["sha256"] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    invariant_result = _run(proof_path, capture_path)
    assert invariant_result.returncode == 2
    assert "billed revenue is not 42000" in invariant_result.stdout
