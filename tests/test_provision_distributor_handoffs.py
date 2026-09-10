"""Offline schema checks for the narrowly scoped Distributor Cases table."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.provision_distributor_handoffs import (
    FIELD_DEFINITIONS,
    FIELD_TYPES,
    TABLE_NAME,
    existing_table,
)


class API:
    def __init__(self, table: dict[str, object]) -> None:
        self.config = SimpleNamespace(airtable_base_id="base-1")
        self.table = table

    def request(self, provider: str, path: str) -> object:
        assert provider == "airtable"
        assert path == "/meta/bases/base-1/tables"
        return {"tables": [self.table]}


def table(fields: object = FIELD_DEFINITIONS) -> dict[str, object]:
    return {"id": "tbl-distributor", "name": TABLE_NAME, "fields": list(fields)}


def test_field_definitions_match_the_adapter_write_types() -> None:
    assert {field["name"] for field in FIELD_DEFINITIONS} == set(FIELD_TYPES)
    for name in (
        "Received",
        "Held",
        "Missing",
        "Dispatched",
        "Recorded Delivery Confirmation",
    ):
        field = next(field for field in FIELD_DEFINITIONS if field["name"] == name)
        assert field == {"name": name, "type": "number", "options": {"precision": 2}}
    assert FIELD_TYPES["Customer Impact"] == "multilineText"
    assert FIELD_TYPES["Semantic Revision"] == "singleLineText"


def test_existing_table_requires_each_expected_name_and_type() -> None:
    assert existing_table(API(table())) == table()
    wrong = list(FIELD_DEFINITIONS)
    wrong[1] = {"name": "Case Label", "type": "number", "options": {"precision": 2}}
    with pytest.raises(ValueError, match="schema mismatch"):
        existing_table(API(table(wrong)))
    missing = [field for field in FIELD_DEFINITIONS if field["name"] != "ERP Documents"]
    with pytest.raises(ValueError, match="ERP Documents"):
        existing_table(API(table(missing)))
