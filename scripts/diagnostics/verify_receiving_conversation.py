"""Exercise real receiving dialogue without authorizing inventory or recovery writes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    def request(path, payload=None):
        req = Request(
            base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Origin": base},
        )
        with urlopen(req, timeout=150) as response:
            return json.load(response)

    baseline = request("/api/v1/agent-platform")
    assert baseline["case_id"] == args.case_id
    quantities = baseline["case_projection"]["case"]["quantities"]
    questions = (
        "Compare ordered, physically received and posted quantities. Is the outstanding "
        "balance evidence of missing stock? Check the source records and explain.",
        "I decline any inventory change. Do not approve or execute anything. "
        "Which records independently verify that receipt, and should we retry it?",
        "Keep that read-only constraint. Show the receiving trend and historical baseline. "
        "Explain net change versus the prior-observation average; is this proof of revenue gain?",
    )
    report = {"case_id": args.case_id, "started_at": datetime.now(UTC).isoformat(),
              "source": "real local HTTP gateway to Strands/Bedrock",
              "acceptance_scope": "runtime_contract_only",
              "independent_answer_quality_review_required": True, "turns": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for question in questions:
        response = request("/api/v1/agent-platform/ask", {"question": question})
        advisory = response.get("agent_advisory", {})
        turn = {"question": question, "answer": response.get("answer"),
                "advisory": advisory,
                "validation_diagnostics": response.get("validation_diagnostics", [])}
        report["turns"].append(turn)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"turn": len(report["turns"]), "status": advisory.get("status"),
                          "answer": turn["answer"], "usage": advisory.get("usage"),
                          "diagnostics": turn["validation_diagnostics"]}), flush=True)
        assert advisory.get("status") == "COMPLETE", "Real model turn did not pass"
        assert advisory["mode"] == "real_strands"
        assert advisory["result"]["write_performed"] is False
        assert response["case_id"] == args.case_id
        current = request("/api/v1/agent-platform")
        assert current["case_projection"]["case"]["quantities"] == quantities
    assert report["turns"][-1]["advisory"].get("attachments"), "Missing real history view"
    contexts = [turn["advisory"]["context_turns"] for turn in report["turns"]]
    # The gateway intentionally retains at most three prior turns, including
    # failed human requests. A saturated window must not be mistaken for lost context.
    assert contexts == [min(3, contexts[0] + index) for index in range(3)]
    report.update(passed=True, quantities_unchanged=True,
                  completed_at=datetime.now(UTC).isoformat())
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
