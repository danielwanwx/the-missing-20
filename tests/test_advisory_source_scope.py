"""Connected service receipts must not become facts of an unrelated synthetic case."""

from the_missing_20.adapters.ambiguous_case_platform import AmbiguousCasePlatform
from the_missing_20.adapters.live_advisory_gateway import (
    competition_investigation_packet,
    connected_competition_investigation_packet,
)


def test_connected_records_do_not_change_the_synthetic_case_or_its_admitted_citations() -> None:
    projection = AmbiguousCasePlatform().current()
    isolated = competition_investigation_packet(projection)
    connected = connected_competition_investigation_packet(
        projection,
        erp_evidence={
            "status": "CONNECTED",
            "documents": [
                {
                    "name": "UNRELATED-ALREADY-RECOVERED-PO",
                    "quantity": 20,
                    "docstatus": 1,
                    "status": "Completed",
                }
            ],
        },
        saas_evidence={
            "status": "CONNECTED",
            "sources": [
                {
                    "source_id": "airtable-quality-registry",
                    "provider": "Airtable",
                    "record_id": "UNRELATED-APPROVAL",
                    "status": "VERIFIED",
                    "read_only": True,
                    "detail": "An unrelated lot was released.",
                }
            ],
        },
    )

    assert connected["source"] == "synthetic-demo-fixture"
    assert connected["tool_payload"] == isolated["tool_payload"]
    assert connected["evidence_ids"] == isolated["evidence_ids"]
    assert connected["connected_sources"] == 2
    assert len(connected["connection_receipts"]) == 2
    assert all(receipt["case_evidence"] is False for receipt in connected["connection_receipts"])
