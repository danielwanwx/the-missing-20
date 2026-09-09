"""Three real read-only Strands turns over the current receiving workspace."""
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

QUESTIONS = (
    "Read the newly identified M20-CARTON-001 evidence. What product, category, unit and "
    "purchase-order price does ERP show? Cite the source. Did identifying it post new stock?",
    "Do the 39 Box still to receive indicate a loss? Does our short history prove revenue "
    "growth or labor savings? Explain what is measured versus not yet proven.",
    "I decline any inventory changes. Keep everything read-only. What evidence should we "
    "collect for the next delivery, and what can we safely inspect now?",
)


def main():
    output = Path("artifacts/agent/2026-09-08-barcode-real-dialogue.json")
    report = {"started_at": datetime.now(UTC).isoformat(), "scope": "real Strands, live ERP",
              "business_write_requested": False, "turns": []}
    for question in QUESTIONS:
        request = Request("http://127.0.0.1:8893/api/v1/agent-platform/ask",
                          data=json.dumps({"question": question}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
        record = {"question": question, "answer": result.get("answer"),
                  "agent_advisory": result.get("agent_advisory")}
        report["turns"].append(record)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
