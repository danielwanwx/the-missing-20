"""Plan the explicitly scoped Distributor Cases Airtable table.

The default command is read-only.  Creating a table requires ``--execute`` and
is intentionally left for the separately authorized provider run.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from the_missing_20.adapters.receiving_destinations import ReceivingAPI
from the_missing_20.adapters.saas_evidence import SaaSEvidenceSource

TABLE_NAME = "Distributor Cases"
_QUANTITY_FIELDS = (
    "Received",
    "Held",
    "Missing",
    "Dispatched",
    "Recorded Delivery Confirmation",
)
_LONG_TEXT_FIELDS = (
    "Customer Impact",
    "Parent Purchase Order",
    "Item Identifiers",
    "ERP Documents",
    "Allocation Decision",
    "Open Operational Alerts",
    "Evidence Basis",
)
FIELD_DEFINITIONS: tuple[Mapping[str, object], ...] = (
    *({"name": name, "type": "singleLineText"} for name in ("Case ID", "Case Label", "Unit")),
    *({"name": name, "type": "number", "options": {"precision": 2}} for name in _QUANTITY_FIELDS),
    *({"name": name, "type": "multilineText"} for name in _LONG_TEXT_FIELDS),
    {"name": "Semantic Revision", "type": "singleLineText"},
)
FIELD_TYPES = {str(field["name"]): str(field["type"]) for field in FIELD_DEFINITIONS}


def existing_table(api: ReceivingAPI) -> dict[str, Any] | None:
    payload = api.request("airtable", f"/meta/bases/{api.config.airtable_base_id}/tables")
    tables = payload.get("tables") if isinstance(payload, dict) else None
    matches = (
        [row for row in tables if isinstance(row, dict) and row.get("name") == TABLE_NAME]
        if isinstance(tables, list)
        else []
    )
    if len(matches) > 1:
        raise ValueError("Distributor Cases table identity is ambiguous")
    if not matches:
        return None
    table = matches[0]
    fields = table.get("fields")
    if not isinstance(fields, list):
        raise ValueError("Distributor Cases table schema is unavailable")
    actual = {
        field.get("name"): field.get("type")
        for field in fields
        if isinstance(field, dict) and isinstance(field.get("name"), str)
    }
    wrong = {
        name: {"expected": field_type, "actual": actual.get(name)}
        for name, field_type in FIELD_TYPES.items()
        if actual.get(name) != field_type
    }
    if wrong:
        raise ValueError(f"Distributor Cases table schema mismatch: {wrong}")
    return table


def output_config(table: dict[str, Any]) -> dict[str, str]:
    table_id = table.get("id")
    if not isinstance(table_id, str) or not table_id:
        raise ValueError("Distributor Cases table has no ID")
    return {"airtable_table_id": table_id, "airtable_table_name": TABLE_NAME}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = SaaSEvidenceSource.from_environment(repository_root=Path.cwd())._config
    api = ReceivingAPI(config)
    table = existing_table(api)
    if table is None:
        if not args.execute:
            raise SystemExit(
                "Distributor Cases table is absent; rerun only with explicit --execute"
            )
        payload = {
            "name": TABLE_NAME,
            "fields": list(FIELD_DEFINITIONS),
        }
        created = api.request(
            "airtable", f"/meta/bases/{config.airtable_base_id}/tables", payload=payload
        )
        if not isinstance(created, dict) or created.get("name") != TABLE_NAME:
            raise SystemExit("Airtable table creation did not return the scoped table")
        table = created
    result = output_config(table)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    args.output.chmod(0o600)


if __name__ == "__main__":
    main()
