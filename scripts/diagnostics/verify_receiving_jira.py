"""GET-only proof of the scoped receiving Jira lifecycle, including replay identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from the_missing_20.adapters.receiving_destinations import ReceivingAPI
from the_missing_20.adapters.receiving_handoff import HandoffJournal, receipt_event
from the_missing_20.adapters.receiving_jira import JiraReceivingReview, _JiraOperation
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument(
        "--phase", choices=("resolved", "after_restart", "after_replay"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime_directory.resolve()
    with sqlite3.connect(f"file:{runtime / 'photo-receiving.sqlite3'}?mode=ro", uri=True) as db:
        state = json.loads(db.execute(
            "SELECT state FROM captures WHERE id=?", (args.capture_id,)).fetchone()[0])
    journal_path = runtime / "receiving-handoffs.sqlite3"
    assert journal_path.is_file()
    with sqlite3.connect(f"file:{journal_path}?mode=ro", uri=True) as db:
        rows = [(key, json.loads(payload), json.loads(raw)) for key, payload, raw in db.execute(
            "SELECT key,payload,state FROM handoffs WHERE json_extract(payload,'$.capture_id')=?",
            (args.capture_id,))]
    config = json.loads((runtime / "handoff-config.json").read_text())
    api = ReceivingAPI(SaaSEvidenceSource.from_environment(repository_root=ROOT)._config)
    # Open the existing journal, but never call sync/deliver (the write paths).
    journal = HandoffJournal(journal_path)
    jira = JiraReceivingReview(api, journal, config["jira_project_key"])
    marker = jira.marker(state)
    issue = jira.lookup(marker)
    assert issue and issue["fields"]["status"]["statusCategory"]["key"] == "done"
    proofs = []
    for key, event, retained in rows:
        if not retained["route"].startswith(jira.route + ":"):
            continue
        assert retained["status"] == "VERIFIED"
        assert event["marker"] == marker and event["case_id"] == state["work_item"]["case_id"]
        proof = _JiraOperation(jira).find(event, key)
        assert proof and proof["record_id"] == issue["key"]
        if event["operation"] == "resolve":
            assert event["receipt_evidence"] == receipt_event(state)
        proofs.append({"key": key, "operation": event["operation"],
                       "version": event.get("version"), **proof})
    assert [p["operation"] for p in proofs].count("create") == 1
    assert [p["operation"] for p in proofs].count("resolve") == 1
    assert any(p["operation"] == "comment" for p in proofs)
    comments = api.request("jira", f"/rest/api/3/issue/{issue['key']}/comment?maxResults=100")
    assert comments["total"] == len(comments["comments"])
    comment_identity = sorted(
        ({"id": row["id"], "body_sha256": hashlib.sha256(
            json.dumps(row["body"], sort_keys=True).encode()).hexdigest()}
         for row in comments["comments"]), key=lambda row: row["id"])
    assert len({row["id"] for row in comment_identity}) == len(comment_identity)
    snapshot = {"case_id": state["work_item"]["case_id"], "capture_id": args.capture_id,
                "issue": issue["key"], "status": issue["fields"]["status"]["name"],
                "url": jira.origin + "/browse/" + issue["key"], "proofs": proofs,
                "comment_identity": comment_identity}
    report = json.loads(args.output.read_text()) if args.output.exists() else {
        "scope": "Jira GET readback only; pair with independent ERP and SaaS receipt readback",
        "external_writes": 0}
    if args.phase != "resolved":
        assert snapshot == report["resolved"]["snapshot"], "Jira effects changed across replay"
    report[args.phase] = {"snapshot": snapshot, "passed": True,
                          "checked_at": datetime.now(UTC).isoformat()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report[args.phase], indent=2))
    journal.db.close()


if __name__ == "__main__":
    main()
