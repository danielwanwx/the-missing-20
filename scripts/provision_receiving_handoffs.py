"""Provision two narrow demo destinations; does not send messages or receive goods."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from the_missing_20.adapters.receiving_destinations import ReceivingAPI
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_ID = "m20-verified-receiving-slack-v1"
TABLE = "Receiving Ledger"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--confirm", choices=["m20-receiving-destinations"], required=True)
    args = parser.parse_args()
    config = SaaSEvidenceSource.from_environment(repository_root=ROOT)._config
    api = ReceivingAPI(config)
    runtime = args.runtime_directory
    runtime.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(runtime / "handoff-provisioning.sqlite3")
    db.execute("CREATE TABLE IF NOT EXISTS attempts (scope TEXT PRIMARY KEY)")

    def create_once(scope, create):
        if db.execute("SELECT 1 FROM attempts WHERE scope=?", (scope,)).fetchone():
            raise ValueError("Provisioning outcome unknown; reconcile existing resources only")
        db.execute("INSERT INTO attempts VALUES (?)", (scope,))
        db.commit()
        create()

    flow = api.request("celigo", f"/flows/{config.celigo_flow_id}")
    source = api.request("celigo", "/imports/" + flow["pageProcessors"][0]["_importId"])
    if source.get("http", {}).get("relativeURI") != ["chat.postMessage"]:
        raise ValueError("Existing demo Slack destination did not match")
    connection_id = source["_connectionId"]
    imports = api.request("celigo", "/imports")
    matches = [row for row in imports if row.get("externalId") == EXTERNAL_ID]
    if not matches:
        create_once(
            "celigo:" + connection_id,
            lambda: api.request(
                "celigo",
                "/imports",
                payload={
                    "name": "M20 verified receiving → Slack",
                    "externalId": EXTERNAL_ID,
                    "description": "Receipt notice; no stock, payment or QA changes.",
                    "_connectionId": connection_id,
                    "_integrationId": flow["_integrationId"],
                    "adaptorType": "HTTPImport",
                    "maxAttempts": 1,
                    "http": {
                        "relativeURI": ["chat.postMessage"],
                        "method": ["POST"],
                        "requestType": ["CREATE"],
                        "type": "records",
                        "batchSize": 1,
                        "requestMediaType": "json",
                        "successMediaType": "json",
                        "errorMediaType": "json",
                        "sendPostMappedData": True,
                        "strictHandlebarEvaluation": True,
                        "response": {
                            "resourceIdPath": ["ts"],
                            "successPath": ["ok"],
                            "successValues": [["true"]],
                        },
                    },
                },
            ),
        )
        matches = [
            row for row in api.request("celigo", "/imports") if row.get("externalId") == EXTERNAL_ID
        ]
    if len(matches) != 1:
        raise ValueError("Expected one unique Celigo receiving import")
    table_path = f"/meta/bases/{config.airtable_base_id}/tables"
    tables = [row for row in api.request("airtable", table_path)["tables"] if row["name"] == TABLE]
    if not tables:
        names = [
            "Event ID",
            "Case ID",
            "Arrival",
            "Purchase Order",
            "Purchase Receipt",
            "Item",
            "Unit",
            "Stock Ledger IDs",
            "ERP Link",
            "Verified At",
            "Status",
            "Origin",
        ]
        fields = [{"name": name, "type": "singleLineText"} for name in names]
        fields.append({"name": "Quantity", "type": "number", "options": {"precision": 2}})
        create_once(
            "airtable:" + config.airtable_base_id,
            lambda: api.request(
                "airtable",
                table_path,
                payload={
                    "name": TABLE,
                    "fields": fields,
                    "description": "ERPNext event copies; not QA, invoice or stock authority.",
                },
            ),
        )
        tables = [
            row for row in api.request("airtable", table_path)["tables"] if row["name"] == TABLE
        ]
    if len(tables) != 1:
        raise ValueError("Expected one unique Airtable receiving table")
    output = {
        "celigo_import_id": matches[0]["_id"],
        "celigo_connection_id": connection_id,
        "airtable_base_id": config.airtable_base_id,
        "airtable_table_id": tables[0]["id"],
        "slack_channel_id": config.slack_channel_id,
    }
    (runtime / "handoff-config.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
