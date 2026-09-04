"""Read-only synthetic source for the recorded procurement investigation.

The source is intentionally explicit about being synthetic.  It supplies the
same kind of independently-owned facts a production adapter would project,
without disguising a scenario fixture as a live vendor response.
"""

from __future__ import annotations

from datetime import UTC, datetime

from the_missing_20.domain.ambiguous_receipt import AmbiguousReceiptCase, primary_case

AMBIGUOUS_RECEIPT_SCHEMA_VERSION = "missing20-ambiguous-receipt/v1"


class AmbiguousReceiptEvidenceSource:
    """Expose a display-safe, source-separated case projection."""

    def __init__(self, case: AmbiguousReceiptCase | None = None) -> None:
        self._case = case or primary_case()
        self._sequence = 0

    def current(self) -> dict[str, object]:
        self._sequence += 1
        observed_at = datetime.now(UTC).isoformat()
        case = self._case
        facts = case.evidence_projection()
        quantities = facts["quantities"]
        assert isinstance(quantities, dict)
        activity = [
            {
                "source_id": "warehouse-asn",
                "provider": "Warehouse / ASN · synthetic demo source",
                "record_id": f"ASN-{case.purchase_order_id}",
                "correlation_id": case.case_id,
                "observed_at": observed_at,
                "status": "ARRIVED",
                "detail": f"{quantities['physically_arrived']} units physically arrived.",
            },
            {
                "source_id": "erp-business-key",
                "provider": "ERP · synthetic demo source",
                "record_id": case.receipt_business_key,
                "correlation_id": case.case_id,
                "observed_at": observed_at,
                "status": (
                    "POSTED"
                    if case.erp_receipt_key_found is True
                    else ("ABSENT" if case.erp_receipt_key_found is False else "UNREAD")
                ),
                "detail": "Business-key reread determines whether retry is safe.",
            },
            {
                "source_id": "supplier-quality",
                "provider": "Supplier Quality Registry · synthetic demo source",
                "record_id": case.quality_release_key,
                "correlation_id": case.case_id,
                "observed_at": observed_at,
                "status": case.quality_disposition,
                "detail": (
                    f"Lot {case.supplier_lot} covers {quantities['quality_hold']} held units."
                ),
            },
            {
                "source_id": "integration-attempt",
                "provider": "Integration Control Plane · synthetic demo source",
                "record_id": case.receipt_business_key,
                "correlation_id": case.case_id,
                "observed_at": observed_at,
                "status": case.integration_outcome,
                "detail": "A retryable attempt is not proof of an ERP write failure.",
            },
        ]
        return {
            "schema_version": AMBIGUOUS_RECEIPT_SCHEMA_VERSION,
            "status": "CONNECTED",
            "provenance": "synthetic-demo-fixture",
            "read_only": True,
            "sequence": self._sequence,
            "received_at": observed_at,
            "case": facts,
            "activity": activity,
        }
