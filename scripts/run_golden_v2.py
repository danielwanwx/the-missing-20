"""Compose the offline Golden v2 evidence report without model or network access."""

from __future__ import annotations

from pathlib import Path

from the_missing_20.evaluation.agent_golden_runner import AgentGoldenRunner

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = AgentGoldenRunner(ROOT, ROOT / "artifacts/golden").run_all()
    safety = result["safety_regression"]
    scripted = result["scripted_strands_proof"]
    bedrock = result["bedrock_model_proof"]
    print(
        f"Golden v2 {result['status']}: "
        f"safety={safety.get('status')} scripted={scripted.get('status')} "
        f"bedrock={bedrock.get('status')} "
        f"stable_real_nova_usefulness={result['ai_usefulness_proof'].get('status')}"
    )
    print(
        f"Promotion: {result['promotion'].get('status', 'NOT_READY')}"
        if result["promotion"]["promotable"]
        else "Promotion: NOT_READY"
    )
    # A missing real-model artifact is expected in offline CI.  The command remains
    # successful when both reproducible offline layers pass, while promotion stays
    # false.  A validated, already-consumed degraded record promotes only with the
    # explicit disclosure status; it never becomes plain PASS.
    return 0 if safety.get("status") == "PASS" and scripted.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
