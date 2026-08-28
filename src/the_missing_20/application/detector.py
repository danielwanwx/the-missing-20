"""Fresh-read discrepancy detection and immutable case genesis."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from the_missing_20.domain.enterprise import EvidenceReadStatus, ScenarioFixture
from the_missing_20.domain.events import TransitionCommand
from the_missing_20.domain.execution import DetectionGenesis
from the_missing_20.domain.models import (
    Case,
    Discrepancy,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSourceType,
)
from the_missing_20.domain.states import CaseStatus, TransitionEvent
from the_missing_20.ports.case_store import CaseStore
from the_missing_20.ports.clock import Clock
from the_missing_20.ports.enterprise_systems import EnterpriseSystems


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _portable_fixture_reference(fixture_path: Path) -> str:
    parts = fixture_path.parts
    if "fixtures" in parts:
        return Path(*parts[parts.index("fixtures") :]).as_posix()
    return fixture_path.name


class DiscrepancyDetector:
    def __init__(self, enterprise: EnterpriseSystems, store: CaseStore, clock: Clock) -> None:
        self.enterprise = enterprise
        self.store = store
        self.clock = clock

    def detect(
        self,
        *,
        case_id: str,
        trace_id: str,
        fixture_path: Path,
        failed_unit_ids: tuple[str, ...] = (),
    ) -> tuple[Case, tuple[EvidenceItem, ...]]:
        occurred_at = self.clock.now()
        fixture = ScenarioFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        snapshot = self.enterprise.read_snapshot()
        expected = snapshot.purchase_order.ordered_quantity
        observed = snapshot.erp_receipt.quantity
        missing = expected - observed
        if failed_unit_ids and (
            len(failed_unit_ids) != snapshot.failed_message.quantity
            or len(set(failed_unit_ids)) != len(failed_unit_ids)
        ):
            raise ValueError("failed-message evidence must bind the exact failed unit set")
        if (
            missing < 0
            or snapshot.invoice.quantity != expected
            or (missing == 0 and snapshot.invoice.state.value != "HELD")
        ):
            raise ValueError("fixture does not contain the approved receipt discrepancy")

        provenance = EvidenceProvenance(
            source_system="synthetic-enterprise-sqlite",
            collection_method="fresh-read",
            collected_by="deterministic-detector",
        )
        failed_message_fields = snapshot.failed_message.model_dump(mode="json")
        if failed_unit_ids:
            # The per-unit expansion is an experiment read model.  Keep it opt-in so
            # legacy signed Authority-B detector evidence remains byte-identical.
            failed_message_fields = {
                **failed_message_fields,
                "failed_unit_ids": list(failed_unit_ids),
            }
        evidence_specs = [
            (
                f"{case_id}:warehouse",
                EvidenceSourceType.WAREHOUSE,
                snapshot.warehouse_receipt.receipt_id,
                snapshot.warehouse_receipt.model_dump(mode="json"),
            ),
            (
                f"{case_id}:erp-receipt",
                EvidenceSourceType.ERP_RECEIPT,
                f"{snapshot.erp_receipt.purchase_order_id}:{snapshot.erp_receipt.line_id}",
                snapshot.erp_receipt.model_dump(mode="json"),
            ),
            (
                f"{case_id}:failed-message",
                EvidenceSourceType.FAILED_MESSAGE_QUEUE,
                snapshot.failed_message.message_id,
                failed_message_fields,
            ),
            (
                f"{case_id}:invoice",
                EvidenceSourceType.INVOICE,
                snapshot.invoice.invoice_id,
                snapshot.invoice.model_dump(mode="json"),
            ),
        ]
        document_read = self.enterprise.read_material_documents()
        if document_read.status is EvidenceReadStatus.AVAILABLE:
            evidence_specs.append(
                (
                    f"{case_id}:material-documents",
                    EvidenceSourceType.MATERIAL_DOCUMENT,
                    snapshot.failed_message.message_id,
                    {
                        "material_documents": [
                            d.model_dump(mode="json") for d in document_read.documents
                        ],
                        "business_effects": [
                            effect.model_dump(mode="json")
                            for effect in document_read.business_effects
                        ],
                    },
                )
            )
        evidence = tuple(
            EvidenceItem(
                evidence_id=evidence_id,
                case_id=case_id,
                trace_id=trace_id,
                subject=source_type.value.lower(),
                source_type=source_type,
                source_record_id=record_id,
                observed_at=occurred_at,
                content_digest=_digest(fields),
                admitted_fields=cast(dict[str, JsonValue], fields),
                provenance=provenance,
            )
            for evidence_id, source_type, record_id, fields in evidence_specs
        )
        case = Case(
            case_id=case_id,
            case_version=0,
            scenario_id=fixture.scenario_id,
            status=CaseStatus.OPEN,
            discrepancy=Discrepancy(
                expected_quantity=expected,
                observed_quantity=observed,
                missing_quantity=missing,
                unit=snapshot.purchase_order.unit,
            ),
            current_evidence_revision=0,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        fixture_digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        genesis = DetectionGenesis(
            case_id=case_id,
            trace_id=trace_id,
            fixture_path=_portable_fixture_reference(fixture_path),
            fixture_digest=fixture_digest,
            initial_case_json=case.model_dump_json(),
            detection_facts={
                "ordered_quantity": expected,
                "warehouse_quantity": snapshot.warehouse_receipt.quantity,
                "physical_receipt_quantity": snapshot.warehouse_receipt.quantity,
                "erp_receipt_quantity": observed,
                "invoice_quantity": snapshot.invoice.quantity,
                "missing_quantity": missing,
                "material_document_source_status": document_read.status.value,
                "material_document_source_reason": document_read.reason_code,
            },
            detector_evidence_ids=tuple(item.evidence_id for item in evidence),
            created_at=occurred_at,
        )
        self.store.create_case(case, genesis)
        for item in evidence:
            self.store.add_evidence(item)
        started, _ = self.store.apply_transition(
            TransitionCommand(
                case_id=case_id,
                expected_version=0,
                event=TransitionEvent.INVESTIGATION_STARTED,
                idempotency_key="case-investigation-started",
                trace_id=trace_id,
                occurred_at=occurred_at,
            )
        )
        return started, evidence
