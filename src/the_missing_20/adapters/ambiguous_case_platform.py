"""Closed-loop controller for the disclosed-synthetic procurement demo.

It owns only the isolated M20 fixture.  The controller models the same
evidence/approval/execution boundaries as the provider-backed platform, while
keeping the demo's write effects local and explicit.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from the_missing_20.adapters.case_console_store import CaseConsoleStore
from the_missing_20.adapters.connected_operations import build_connected_operations
from the_missing_20.adapters.investigation_case_sources import (
    investigation_case_catalog,
    investigation_packet,
)
from the_missing_20.domain.ambiguous_receipt import (
    AmbiguousReceiptCase,
    CaseDisposition,
    IntegrationOutcome,
    QualityDisposition,
    primary_case,
)


class AmbiguousCasePlatform:
    """A small, idempotent end-to-end case controller for judge-mode replay."""

    def __init__(
        self, case: AmbiguousReceiptCase | None = None, *, store_path: Path | None = None
    ) -> None:
        self._case = case or primary_case()
        self._run_lock = RLock()
        self._scenario_variant = "uncommitted_receipt"
        self._store = CaseConsoleStore(store_path) if store_path is not None else None
        self._sequence = 0
        self._events: list[dict[str, object]] = []
        self._run_id = ""
        self._case_version = 1
        self._diagnosis_authorization: dict[str, object] = {}
        self._conversation: list[dict[str, object]] = []
        self._runtime_events: list[dict[str, object]] = []
        self._evidence_observed_at = self._now()
        self._agent_state = "IDLE"
        self._diagnosis: dict[str, object] = {
            "status": "IDLE",
            "finding": "NOT_EVALUATED",
            "summary": "No diagnosis has run.",
            "tool_calls": [],
        }
        self._policy_decision: dict[str, object] = {}
        self._approval: dict[str, object] = {}
        self._rejection: dict[str, object] = {}
        self._execution: dict[str, object] = {}
        # The live case mutates only after Manager approval. Keep the exact,
        # pre-execution scope separately so a verified resolution packet can
        # never report a post-transfer zero as the approved transfer amount.
        self._recovery_scope: dict[str, int] = {}
        self._pre_execution_case: AmbiguousReceiptCase | None = None
        restored = self._store.load(self._case.case_id) if self._store is not None else None
        if restored is not None:
            self._restore(restored)
        else:
            self._admit_initial_evidence()
            self._persist()

    def _restore(self, snapshot: Mapping[str, Any]) -> None:
        self._case = AmbiguousReceiptCase.model_validate_json(json.dumps(snapshot["case"]))
        self._sequence = int(snapshot.get("sequence", 0))
        self._events = [
            dict(event) for event in snapshot.get("events", []) if isinstance(event, Mapping)
        ]
        self._agent_state = str(snapshot.get("agent_state", "IDLE"))
        self._diagnosis = dict(snapshot.get("diagnosis", {}))
        self._policy_decision = dict(snapshot.get("policy_decision", {}))
        self._approval = dict(snapshot.get("approval", {}))
        self._rejection = dict(snapshot.get("rejection", {}))
        self._execution = dict(snapshot.get("execution", {}))
        self._run_id = str(snapshot.get("run_id", ""))
        self._case_version = int(snapshot.get("case_version", 1))
        self._diagnosis_authorization = dict(snapshot.get("diagnosis_authorization", {}))
        self._scenario_variant = str(snapshot.get("scenario_variant", "uncommitted_receipt"))
        self._conversation = [
            dict(turn) for turn in snapshot.get("conversation", []) if isinstance(turn, Mapping)
        ]
        self._runtime_events = [
            dict(event)
            for event in snapshot.get("runtime_events", [])
            if isinstance(event, Mapping)
        ]
        self._evidence_observed_at = str(
            snapshot.get("evidence_observed_at", self._evidence_observed_at)
        )
        before = snapshot.get("pre_execution_case")
        self._pre_execution_case = (
            AmbiguousReceiptCase.model_validate_json(json.dumps(before))
            if before is not None
            else None
        )
        raw_scope = snapshot.get("recovery_scope", {})
        self._recovery_scope = {
            key: value
            for key, value in dict(raw_scope).items()
            if key in {"receipt_post_quantity", "quality_transfer_quantity"}
            and isinstance(value, int)
            and value >= 0
        }

    def _snapshot(self) -> dict[str, Any]:
        return {
            "case": self._case.model_dump(mode="json"),
            "sequence": self._sequence,
            "events": list(self._events),
            "agent_state": self._agent_state,
            "diagnosis": dict(self._diagnosis),
            "policy_decision": dict(self._policy_decision),
            "approval": dict(self._approval),
            "rejection": dict(self._rejection),
            "execution": dict(self._execution),
            "run_id": self._run_id,
            "case_version": self._case_version,
            "diagnosis_authorization": dict(self._diagnosis_authorization),
            "scenario_variant": self._scenario_variant,
            "conversation": list(self._conversation),
            "runtime_events": list(self._runtime_events),
            "evidence_observed_at": self._evidence_observed_at,
            "recovery_scope": dict(self._recovery_scope),
            "pre_execution_case": (
                self._pre_execution_case.model_dump(mode="json")
                if self._pre_execution_case is not None
                else None
            ),
        }

    def _persist(self, *, event: dict[str, Any] | None = None) -> None:
        if self._store is not None:
            self._store.save(self._case.case_id, self._snapshot(), event=event)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _business_impact(self) -> dict[str, object]:
        """Project owner-facing economics from the same admitted source records."""

        facts = self._case.evidence_projection()
        packet = investigation_packet(self._scenario_variant, case=facts)
        sources = packet["tool_payload"]["sources"]
        erp = sources["read_erp_evidence"]
        invoice = erp["invoice"]
        purchase_order = erp["purchase_order"]
        supplier = erp["supplier_master"]
        quantities = facts["quantities"]
        expected = Decimal(str(quantities["physically_arrived"]))
        available = Decimal(str(quantities["available"]))
        quality_hold = Decimal(str(quantities["quality_hold"]))
        receipt_unresolved = Decimal(str(quantities["receipt_unresolved"]))
        po_unit_cost = Decimal(str(purchase_order["unit_price"]))
        invoice_unit_price = Decimal(str(invoice["unit_price"]))
        invoice_quantity = Decimal(str(invoice["quantity"]))
        ordered_quantity = Decimal(str(purchase_order["ordered"]))
        erp_accounted = available + quality_hold
        at_risk_units = quality_hold + receipt_unresolved
        invoice_held = bool(self._case.invoice_held)
        verified = self._execution.get("status") == "VERIFIED"
        recovered_units = (
            Decimal(str(sum(self._recovery_scope.values()))) if verified else Decimal(0)
        )

        def amount(value: Decimal) -> float:
            return float(value.quantize(Decimal("0.01")))

        def percent(numerator: Decimal, denominator: Decimal) -> float:
            if denominator <= 0:
                return 0.0
            return float((numerator * Decimal(100) / denominator).quantize(Decimal("0.1")))

        return {
            "currency": str(invoice["currency"]),
            "po_unit_cost": amount(po_unit_cost),
            "invoice_unit_price": amount(invoice_unit_price),
            "po_line_value": amount(expected * po_unit_cost),
            "invoice_value": amount(invoice_quantity * invoice_unit_price),
            "available_inventory_value": amount(available * po_unit_cost),
            "invoice_hold_value": amount(invoice_quantity * invoice_unit_price)
            if invoice_held
            else 0.0,
            "working_capital_at_risk": amount(at_risk_units * po_unit_cost),
            "quality_hold_value": amount(quality_hold * po_unit_cost),
            "receipt_gap_value": amount(receipt_unresolved * po_unit_cost),
            "purchase_price_variance": amount(
                (invoice_unit_price - po_unit_cost) * invoice_quantity
            ),
            "invoice_price_delta_percent": percent(invoice_unit_price - po_unit_cost, po_unit_cost),
            "inventory_availability_percent": percent(available, expected),
            "erp_reconciliation_percent": percent(erp_accounted, expected),
            "quality_hold_percent": percent(quality_hold, expected),
            "receipt_gap_percent": percent(receipt_unresolved, expected),
            "supplier_delivery_completion_percent": percent(expected, ordered_quantity),
            "value_protected": amount(recovered_units * po_unit_cost),
            "supplier_status": str(supplier["status"]),
            "supplier_payment_hold": bool(supplier["payment_hold"]),
            "invoice_status": "HELD" if invoice_held else str(invoice["status"]),
            "basis": "current admitted PO, receipt, quality, supplier, and invoice records",
            "provenance": "synthetic-demo-fixture",
        }

    def _connected_operations(self) -> dict[str, object]:
        facts = self._case.evidence_projection()
        quantities = facts["quantities"]
        assert isinstance(quantities, Mapping)
        return build_connected_operations(
            expected_units=int(quantities["physically_arrived"]),
            available_units=int(quantities["available"]),
            quality_hold_units=int(quantities["quality_hold"]),
            receipt_unresolved_units=int(quantities["receipt_unresolved"]),
            business_impact=self._business_impact(),
            scenario_variant=self._scenario_variant,
            verified=self._execution.get("status") == "VERIFIED",
        )

    def _append(self, event_type: str, status: str, label: str, detail: str) -> None:
        quantities = self._case.evidence_projection()["quantities"]
        assert isinstance(quantities, Mapping)
        business = self._business_impact()
        operations = self._connected_operations()
        risk_signal = operations["risk_signal"]
        current_shift = operations["current_shift"]
        customer = operations["customer_commitments"]
        assert isinstance(risk_signal, Mapping)
        assert isinstance(current_shift, Mapping)
        assert isinstance(customer, Mapping)
        self._sequence += 1
        event: dict[str, Any] = {
            "sequence": self._sequence,
            "event_id": f"m20-ambiguous-{self._sequence:05d}",
            "event_type": event_type,
            "occurred_at": self._now(),
            "source_id": "m20-ambiguous-case",
            "case_id": self._case.case_id,
            "run_id": self._run_id,
            "case_version": self._case_version,
            "agent_state": self._agent_state,
            "provider": "Missing 20 synthetic demo tenant",
            "status": status,
            "label": label,
            "detail": detail,
            "provenance": "synthetic-demo-fixture",
            # Each immutable activity record carries the contemporaneous
            # operational counters. The dashboard can therefore draw a
            # real event-time series from the same run that the Agent
            # Workspace investigates instead of animating invented points.
            "metrics": {
                "expected": int(quantities["physically_arrived"]),
                "recorded": int(quantities["available"]),
                "gap": int(quantities["quality_hold"]) + int(quantities["receipt_unresolved"]),
                "quality_hold": int(quantities["quality_hold"]),
                "receipt_unresolved": int(quantities["receipt_unresolved"]),
                "invoice_count": (
                    int(quantities["available"])
                    if self._case.invoice_held
                    else int(quantities["physically_arrived"])
                ),
                "working_capital_at_risk": business["working_capital_at_risk"],
                "invoice_hold_value": business["invoice_hold_value"],
                "purchase_price_variance": business["purchase_price_variance"],
                "value_protected": business["value_protected"],
                "po_unit_cost": business["po_unit_cost"],
                "operational_risk_score": risk_signal["score"],
                "oee_percent": current_shift["oee_percent"],
                "schedule_attainment_percent": current_shift["schedule_attainment_percent"],
                "customer_units_at_risk": customer["units_at_risk"],
                "revenue_at_risk": customer["revenue_at_risk"],
            },
            # A Strands investigation and its resolution packet are
            # evidence-only records. Only the explicit Manager/executor
            # transitions can change the local synthetic tenant.
            "read_only": event_type.startswith(("source.", "agent.", "policy.")),
        }
        self._events.append(event)
        self._persist(event=event)

    def reset(
        self,
        case: AmbiguousReceiptCase | None = None,
        *,
        scenario_variant: str = "uncommitted_receipt",
    ) -> dict[str, object]:
        """Open a fresh isolated demo case without retaining a prior run's truth."""

        next_case = case or primary_case()
        if self._store is not None:
            self._store.reset(self._case.case_id)
            if next_case.case_id != self._case.case_id:
                self._store.reset(next_case.case_id)
        self._case = next_case
        self._scenario_variant = scenario_variant
        self._sequence = 0
        self._events = []
        self._run_id = ""
        self._case_version = 1
        self._diagnosis_authorization = {}
        self._conversation = []
        self._runtime_events = []
        self._evidence_observed_at = self._now()
        self._agent_state = "IDLE"
        self._diagnosis = {
            "status": "IDLE",
            "finding": "NOT_EVALUATED",
            "summary": (
                "Incident admitted; an operator may question the evidence Agent before "
                "authorizing diagnosis."
            ),
            "tool_calls": [],
        }
        self._policy_decision = {}
        self._approval = {}
        self._rejection = {}
        self._execution = {}
        self._recovery_scope = {}
        self._pre_execution_case = None
        self._admit_initial_evidence()
        self._persist()
        return self.current()

    def reset_variant(self, variant: str) -> dict[str, object]:
        """Open one counterfactual with the same surface 20-unit alert."""

        base = primary_case()
        aliases = {
            "primary": "uncommitted_receipt",
            "already-posted": "lost_ack",
            "quality-rejected": "wrong_quality_lot",
        }
        variant = aliases.get(variant, variant)
        if variant == "uncommitted_receipt":
            case = base
        elif variant == "lost_ack":
            case = base.model_copy(update={"erp_receipt_key_found": True})
        elif variant == "wrong_quality_lot":
            case = base.model_copy(update={"quality_disposition": QualityDisposition.PENDING})
        elif variant == "lookup_unavailable":
            case = base.model_copy(update={"erp_receipt_key_found": None})
        elif variant == "physical_shortage":
            case = base.model_copy(
                update={
                    "physically_arrived": 80,
                    "available_quantity": 72,
                    "quality_hold_quantity": 8,
                    "receipt_unresolved_quantity": 0,
                }
            )
        elif variant in {
            "evidence_conflict",
            "duplicate_invoice",
            "unit_price_variance",
            "uom_conversion_missing",
            "po_revision_race",
            "supplier_hold",
            "lot_trace_mismatch",
        }:
            case = base
        elif variant == "transfer_already_present":
            case = base.model_copy(update={"quality_transfer_key_found": True})
        elif variant == "normal_complete":
            case = base.model_copy(
                update={
                    "available_quantity": 100,
                    "quality_hold_quantity": 0,
                    "receipt_unresolved_quantity": 0,
                    "invoice_held": False,
                    "integration_outcome": IntegrationOutcome.ACKNOWLEDGED,
                    "erp_receipt_key_found": True,
                }
            )
        else:
            raise ValueError("unsupported counterfactual variant")
        return self.reset(case, scenario_variant=variant)

    def events_since(self, after: int = 0) -> list[dict[str, Any]]:
        """Return immutable server events for a reconnect cursor."""

        if after < 0:
            raise ValueError("event sequence cannot be negative")
        if self._store is not None:
            return self._store.events_since(self._case.case_id, after)
        selected: list[dict[str, Any]] = []
        for event in self._events:
            sequence = event.get("sequence")
            if isinstance(sequence, int) and sequence > after:
                selected.append(dict(event))
        return selected

    def _admit_initial_evidence(self) -> None:
        facts = self._case.evidence_projection()
        quantities = facts["quantities"]
        assert isinstance(quantities, Mapping)
        self._append(
            "source.warehouse.read",
            "ARRIVED",
            "Warehouse / ASN read",
            f"{quantities['physically_arrived']} units arrived against "
            f"{self._case.purchase_order_id}.",
        )
        self._append(
            "source.erp.read",
            "HELD",
            "ERP receipt + invoice read",
            f"{quantities['available']} available; invoice remains held.",
        )
        self._append(
            "source.quality.read",
            str(self._case.quality_disposition),
            "Supplier quality read",
            f"Lot {self._case.supplier_lot} covers {quantities['quality_hold']} held units.",
        )
        self._append(
            "source.integration.read",
            str(self._case.integration_outcome),
            "Integration attempt read",
            "The attempt outcome is unknown until the ERP business-key reread.",
        )

    def _correlation(self) -> dict[str, object]:
        return {
            "status": "FULLY_CORRELATED",
            "tuple": {
                "case_id": self._case.case_id,
                "purchase_order": self._case.purchase_order_id,
                "purchase_receipt": self._case.receipt_business_key,
                "purchase_invoice": self._case.invoice_id,
                "supplier_lot": self._case.supplier_lot,
                "quantity": self._case.quality_hold_quantity,
            },
            "missing_fields": [],
            "mismatched_fields": [],
            "release_eligibility": self._case.disposition(),
        }

    def _plan(self) -> list[dict[str, str]]:
        disposition = self._case.disposition()
        done = self._agent_state not in {"IDLE", "OBSERVING"}
        resolved = self._execution.get("status") == "VERIFIED"
        return [
            {
                "id": "read_match",
                "label": "Read match rule + invoice hold",
                "status": "DONE" if done else "QUEUED",
            },
            {
                "id": "read_quality",
                "label": "Read exact quality lot",
                "status": "DONE" if done else "QUEUED",
            },
            {
                "id": "reread_erp_key",
                "label": "Reread ERP business key",
                "status": "DONE" if done else "QUEUED",
            },
            {
                "id": "guarded_recovery",
                "label": "Build minimal recovery packet",
                "status": "DONE"
                if resolved
                else (
                    "READY"
                    if disposition is CaseDisposition.RECOVERY_READY and done
                    else "BLOCKED"
                    if done
                    else "QUEUED"
                ),
            },
        ]

    def _approval_binding(self) -> dict[str, object]:
        scope = {
            "receipt_post_quantity": self._case.receipt_unresolved_quantity,
            "quality_transfer_quantity": self._case.quality_hold_quantity,
            "invoice_id": self._case.invoice_id,
            "receipt_business_key": self._case.receipt_business_key,
        }
        digest_payload = {
            "case_id": self._case.case_id,
            "case_version": self._case_version,
            "demo_tenant": "missing-20-synthetic-tenant",
            "scope": scope,
            "actions": self._case.allowed_actions(),
        }
        digest = sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {**digest_payload, "plan_digest": digest}

    def _constellation(self) -> dict[str, object]:
        disposition = self._case.disposition()
        execution_status = str(self._execution.get("status", ""))
        if self._agent_state == "IDLE":
            conclusion = ("NO RELEASE", "IDLE", 0.0)
        elif execution_status == "VERIFIED":
            conclusion = ("RECOVERY VERIFIED", "VERIFIED", 0.99)
        elif execution_status == "VERIFYING":
            conclusion = ("VERIFYING RECOVERY", "GUARDED", 0.96)
        elif self._agent_state == "BLOCKED" and self._diagnosis.get("finding") in {
            "AGENT_UNAVAILABLE",
            "AGENT_VALIDATION_FAILED",
        }:
            conclusion = ("AGENT UNAVAILABLE", "BLOCKED", 0.0)
        elif disposition is CaseDisposition.RECOVERY_READY:
            conclusion = ("GUARDED PLAN", "GUARDED", 0.94)
        elif disposition is CaseDisposition.RECONCILE_ONLY:
            conclusion = ("RECONCILE ONLY", "PROTECT", 0.98)
        elif disposition is CaseDisposition.SAFE_STOP:
            conclusion = ("QUALITY HOLD", "BLOCKED", 0.98)
        else:
            conclusion = ("NEED ERP REREAD", "BLOCKED", 0.0)
        return {
            "nodes": [
                {
                    "id": "erpnext",
                    "position": "TOP",
                    "role": "ERP",
                    "label": "ERPNext",
                    "status": "HELD" if self._case.invoice_held else "VERIFIED",
                    "latest_sequence": 2,
                },
                {
                    "id": "airtable",
                    "position": "RIGHT",
                    "role": "QUALITY",
                    "label": "Quality Registry",
                    "status": str(self._case.quality_disposition),
                    "latest_sequence": 3,
                },
                {
                    "id": "celigo",
                    "position": "BOTTOM",
                    "role": "LINEAGE",
                    "label": "Integration",
                    "status": str(self._case.integration_outcome),
                    "latest_sequence": 4,
                },
                {
                    "id": "jira",
                    "position": "LEFT",
                    "role": "WORKFLOW",
                    "label": "Jira",
                    "status": "CONNECTED",
                    "latest_sequence": 5,
                },
                {
                    "id": "slack",
                    "position": "LEFT",
                    "role": "COLLABORATION",
                    "label": "Slack",
                    "status": "APPROVED" if self._approval else "CONNECTED",
                    "latest_sequence": self._sequence,
                },
            ],
            "conclusion": {
                "label": conclusion[0],
                "status": conclusion[1],
                "confidence": conclusion[2],
                "latest_sequence": self._sequence,
            },
        }

    def _evidence_catalog(self) -> dict[str, dict[str, object]]:
        # Freshness is tied to the admitted source snapshot, not to a browser
        # read. Re-rendering the page can never manufacture newer evidence.
        observed_at = self._evidence_observed_at
        rows = {
            "ALERT-4817": ("Control plane", "Invoice match failed; cause unknown."),
            self._case.invoice_id: ("ERPNext", "FOUR_WAY invoice record."),
            self._case.purchase_order_id: ("ERPNext", "Purchase order and ASN reference."),
            "ERP-READ-4817": ("ERPNext", "Authoritative complete stock-ledger read."),
            "MAT-401": ("ERPNext", f"{self._case.available_quantity} available units."),
            "MAT-402": ("ERPNext", f"{self._case.quality_hold_quantity} quality-held units."),
            self._case.receipt_business_key: ("Celigo", "Timed-out receipt business key."),
            "ATTEMPT-551": ("Celigo", "Integration attempt and timeout response."),
            self._case.supplier_lot: ("Airtable", "Exact supplier quality lot."),
            "QA-901": ("Airtable", f"Exact-lot disposition: {self._case.quality_disposition}."),
            "QA-XFER-READ": ("Airtable", "Quality-transfer effect reread."),
            "ASN-902": ("Warehouse", "Physical receiving ASN."),
            "SCAN-701": ("Warehouse", "Available-lot receiving scan."),
            "SCAN-702": ("Warehouse", "Quality-lot receiving scan."),
            "SCAN-703": ("Warehouse", "Unresolved-lot receiving scan."),
        }
        return {
            evidence_id: {
                "evidence_id": evidence_id,
                "provider": provider,
                "revision": "synthetic-current",
                "observed_at": observed_at,
                "summary": summary,
                "provenance": "synthetic-demo-fixture",
            }
            for evidence_id, (provider, summary) in rows.items()
        }

    def _execution_projection(self) -> dict[str, object]:
        if self._execution:
            return dict(self._execution)
        if self._approval:
            return {
                "available": True,
                "status": "AUTHORIZED",
                "detail": "Manager approved the exact recovery packet.",
                **self._approval,
            }
        if self._agent_state == "RECOVERY_COMPLETE":
            return {
                "available": False,
                "status": "NO_ACTION_REQUIRED",
                "detail": "Authoritative records already reconcile; no effect is eligible.",
            }
        if self._agent_state == "PLAN_READY":
            return {
                "available": self._case.disposition() is CaseDisposition.RECOVERY_READY,
                "status": "AWAITING_MANAGER_APPROVAL",
                "detail": "Manager approval is required for the validated recovery packet.",
            }
        if self._agent_state in {"OBSERVING", "GATHERING", "REASONING", "SYNTHESIZING"}:
            return {
                "available": False,
                "status": "INVESTIGATION_RUNNING",
                "detail": (
                    "No action is available while the Agent is gathering and reconciling evidence."
                ),
            }
        if self._agent_state == "BLOCKED":
            finding = str(self._diagnosis.get("finding", "SAFE_STOP"))
            details = {
                "AGENT_UNAVAILABLE": (
                    "No action released: the real Strands run did not complete. "
                    "Retry the investigation."
                ),
                "AGENT_VALIDATION_FAILED": (
                    "No action released: the Agent result failed validation."
                ),
                "EFFECT_ALREADY_PRESENT": (
                    "No write: reconcile the acknowledgement for the already-present ERP effect."
                ),
                "PHYSICAL_SHORTAGE_CONFIRMED": (
                    "No ERP receipt: preserve the hold and escalate the 20-unit supplier shortage."
                ),
                "CROSS_SOURCE_QUANTITY_CONFLICT": (
                    "No write: request a fresh scoped source read and reconcile "
                    "the conflicting quantities."
                ),
                "QUALITY_EVIDENCE_INELIGIBLE": (
                    "No transfer: preserve the quality and invoice holds."
                ),
                "NEEDS_ERP_KEY_REREAD": (
                    "No write: obtain the authoritative ERP business-key result first."
                ),
            }
            return {
                "available": False,
                "status": "SAFE_STOP",
                "detail": details.get(
                    finding, str(self._diagnosis.get("summary", "Recovery stopped safely."))
                ),
            }
        return {
            "available": False,
            "status": "WAITING_FOR_INVESTIGATION",
            "detail": "No recovery action has been released.",
        }

    def _human_review(self) -> dict[str, object]:
        if self._execution.get("status") == "VERIFIED":
            return {
                "status": "COMPLETE",
                "required": False,
                "action": "NONE",
                "reason": "Authoritative synthetic reread verified the guarded recovery.",
                "can_stop": False,
            }
        if self._agent_state == "IDLE":
            return {
                "status": "HUMAN_DIAGNOSIS_REQUIRED",
                "required": True,
                "action": "AUTHORIZE_DIAGNOSIS",
                "reason": (
                    "Question the evidence Agent first or authorize a bounded read-only diagnosis."
                ),
                "can_stop": False,
            }
        if self._agent_state == "STOPPED":
            return {
                "status": "PAUSED_BY_HUMAN",
                "required": True,
                "action": "RESUME_INVESTIGATION",
                "reason": (
                    "The operator paused this case; its evidence remains available to inspect."
                ),
                "can_stop": False,
            }
        if self._agent_state == "BLOCKED":
            finding = str(self._diagnosis.get("finding", ""))
            retry_agent = finding in {"AGENT_UNAVAILABLE", "AGENT_VALIDATION_FAILED"}
            return {
                "status": "AGENT_RETRY_REQUIRED" if retry_agent else "SAFE_STOP",
                "required": retry_agent,
                "action": "RETRY_INVESTIGATION" if retry_agent else "NONE",
                "reason": str(self._diagnosis.get("summary", "Recovery is stopped safely.")),
                "can_stop": False,
            }
        if self._agent_state == "RECOVERY_COMPLETE":
            return {
                "status": "COMPLETE",
                "required": False,
                "action": "NONE",
                "reason": "The Agent proved that no recovery action remains.",
                "can_stop": False,
            }
        if self._agent_state == "PLAN_READY" and not self._approval:
            return {
                "status": "MANAGER_REVIEW_REQUIRED",
                "required": True,
                "action": "APPROVE_GUARDED_PLAN",
                "reason": (
                    "The Agent completed its read-only investigation; a Manager owns "
                    "the recovery decision."
                ),
                "can_stop": True,
            }
        if self._approval and not self._execution:
            return {
                "status": "HUMAN_EXECUTION_REQUIRED",
                "required": True,
                "action": "EXECUTE_GUARDED_PLAN",
                "reason": (
                    "The Manager approved one bounded packet; an operator must "
                    "explicitly execute it."
                ),
                "can_stop": True,
            }
        if self._execution.get("status") == "VERIFYING":
            return {
                "status": "WAITING_FOR_REREAD",
                "required": False,
                "action": "VERIFY_REREAD",
                "reason": "The Agent is waiting for the independent authoritative reread.",
                "can_stop": True,
            }
        return {
            "status": "AGENT_READING",
            "required": False,
            "action": "NONE",
            "reason": "The Agent may perform only bounded, read-only evidence work.",
            "can_stop": True,
        }

    def _resolution_packet(self) -> dict[str, object] | None:
        if self._execution.get("status") != "VERIFIED":
            return None
        raw_tuple = self._correlation()["tuple"]
        assert isinstance(raw_tuple, Mapping)
        case_tuple = dict(raw_tuple)
        case_tuple["quality_transfer_quantity"] = self._recovery_scope.get(
            "quality_transfer_quantity", 0
        )
        case_tuple["receipt_post_quantity"] = self._recovery_scope.get("receipt_post_quantity", 0)
        raw_strands = self._diagnosis.get("strands_investigation", {})
        strands_trace = dict(raw_strands) if isinstance(raw_strands, Mapping) else {}
        return {
            "packet_id": "resolution-m20-4817",
            "status": "VERIFIED",
            "provenance": "synthetic-demo-fixture",
            "case_tuple": case_tuple,
            "finding": self._diagnosis["finding"],
            "policy": {
                "status": self._diagnosis.get("status"),
                "finding": self._diagnosis.get("finding"),
                "authority": "DETERMINISTIC_CONTROL_PLANE",
            },
            "agent_trace": strands_trace,
            "guard": "MANAGER_APPROVED_GUARDED_RECOVERY",
            "approval": dict(self._approval),
            "execution": {
                "status": self._execution.get("status"),
                "idempotency_key": self._execution.get("idempotency_key"),
                "approval_id": self._execution.get("approval_id"),
            },
            "effects": {
                "quality_release_transfer": self._execution.get("transfer_name"),
                "invoice": self._execution.get("invoice_name"),
                "receipt_business_key": self._case.receipt_business_key,
            },
            "pre_state": (
                {
                    "available": self._pre_execution_case.available_quantity,
                    "quality_hold": self._pre_execution_case.quality_hold_quantity,
                    "receipt_unresolved": self._pre_execution_case.receipt_unresolved_quantity,
                    "invoice_held": self._pre_execution_case.invoice_held,
                }
                if self._pre_execution_case is not None
                else None
            ),
            "post_state": {
                "available": self._case.available_quantity,
                "quality_hold": self._case.quality_hold_quantity,
                "receipt_unresolved": self._case.receipt_unresolved_quantity,
                "invoice_held": self._case.invoice_held,
            },
            "evidence": [
                {"source_id": "erpnext", "record_id": self._case.purchase_order_id},
                {"source_id": "airtable", "record_id": self._case.supplier_lot},
                {"source_id": "celigo", "record_id": self._case.receipt_business_key},
            ],
            "timestamps": {
                "approved_at": self._approval.get("approved_at"),
                "executed_at": self._execution.get("executed_at"),
                "verified_at": self._execution.get("verified_at"),
            },
        }

    def current(self) -> dict[str, object]:
        facts = self._case.evidence_projection()
        raw_strands = self._diagnosis.get("strands_investigation", {})
        strands = dict(raw_strands) if isinstance(raw_strands, Mapping) else {}
        if self._runtime_events:
            strands["runtime_events"] = list(self._runtime_events)
            if self._agent_state in {"REASONING", "GATHERING", "SYNTHESIZING"}:
                strands.setdefault("status", "RUNNING")
                strands.setdefault("mode", "real_strands")
        diagnosis = dict(self._diagnosis)
        if strands:
            diagnosis["strands_investigation"] = strands
        tool_calls = strands.get("tool_calls", self._diagnosis.get("tool_calls", []))
        source_checks = len(tool_calls) if isinstance(tool_calls, list) else 0
        return {
            "schema_version": "missing20-agent-platform/v2",
            "case_id": self._case.case_id,
            "run_id": self._run_id,
            "received_at": self._now(),
            "mode": {
                "read_only": False,
                "provider_writes": "LOCAL_SYNTHETIC_ONLY",
                "execution_available": self._agent_state == "PLAN_READY"
                or bool(self._approval)
                or bool(self._execution),
                "provenance": "synthetic-demo-fixture",
            },
            "correlation": self._correlation(),
            "business_impact": self._business_impact(),
            "connected_operations": self._connected_operations(),
            "demo_case": {"provenance": "synthetic-demo-fixture", "read_only": True, "case": facts},
            "scenario": {
                "variant": self._scenario_variant,
                "catalog": [dict(item) for item in investigation_case_catalog()],
            },
            "integration_receipt": {
                "status": self._case.integration_outcome,
                "record_id": self._case.receipt_business_key,
            },
            "systems": [
                {
                    "id": "erpnext",
                    "name": "ERPNext-shaped ERP",
                    "status": "CONNECTED",
                    "authority": "Synthetic operational system of record",
                    "read_only": False,
                    "write_state": "LOCAL_SYNTHETIC_ONLY",
                },
                {
                    "id": "airtable",
                    "name": "Supplier Quality Registry",
                    "status": "CONNECTED",
                    "authority": "Synthetic quality evidence",
                    "read_only": True,
                    "write_state": "DISABLED",
                },
                {
                    "id": "celigo",
                    "name": "Integration Control Plane",
                    "status": "CONNECTED",
                    "authority": "Synthetic delivery lineage",
                    "read_only": True,
                    "write_state": "DISABLED",
                },
                {
                    "id": "jira",
                    "name": "Jira",
                    "status": "CONNECTED",
                    "authority": "Synthetic exception workflow journal",
                    "read_only": True,
                    "write_state": "DISABLED",
                },
                {
                    "id": "slack",
                    "name": "Slack",
                    "status": "CONNECTED",
                    "authority": "Synthetic manager audit",
                    "read_only": True,
                    "write_state": "DISABLED",
                },
            ],
            "agent_run": {
                "run_id": self._run_id,
                "state": self._agent_state,
                "active_step": ""
                if self._agent_state not in {"OBSERVING", "GATHERING"}
                else "reread_erp_key",
                "confidence": 0.94 if self._agent_state == "PLAN_READY" else 0.0,
            },
            "plan": self._plan(),
            "evidence_constellation": self._constellation(),
            "evidence_catalog": self._evidence_catalog(),
            "diagnosis": diagnosis,
            "diagnosis_authorization": dict(self._diagnosis_authorization),
            "human_decision": (
                {"status": "APPROVED", **self._approval}
                if self._approval
                else {"status": "REJECTED", **self._rejection}
                if self._rejection
                else {"status": "PENDING"}
            ),
            "execution": self._execution_projection(),
            "human_review": self._human_review(),
            "resolution_packet": self._resolution_packet(),
            "judge_proof": {
                "evidence_records": len(self._evidence_catalog()),
                "source_checks": source_checks,
                "ledger_events": self._sequence,
                "evidence_observed_at": self._evidence_observed_at,
                "manager_touches": 1 if self._approval or self._rejection else 0,
                "diagnosis_authorized": bool(self._diagnosis_authorization),
                "autonomous_until_review": False,
                "runtime": strands.get("mode", "Strands SDK"),
                "provider": strands.get("provider", {}),
                "verified": self._execution.get("status") == "VERIFIED",
                "case_matrix_size": len(investigation_case_catalog()),
                "sdk_hook_events": len(strands.get("runtime_events", []))
                if isinstance(strands.get("runtime_events"), list)
                else 0,
            },
            "framework": {
                "name": "Hybrid Investigation Loop",
                "version": "v1",
                "current_case": self._scenario_variant,
                "online_loop": [
                    "MODEL_DRIVEN_TOOL_SELECTION",
                    "STRUCTURED_OUTPUT",
                    "SDK_LIFECYCLE_HOOKS",
                    "TRACE_CORRELATION",
                    "BOUNDED_VALIDATION_REPAIR",
                ],
                "control_plane": [
                    "DETERMINISTIC_JOIN",
                    "INDEPENDENT_POLICY_GATE",
                    "MANAGER_WHEN_NECESSARY",
                    "IDEMPOTENT_EXECUTION",
                    "AUTHORITATIVE_REREAD",
                ],
                "validation_harness": {
                    "topology": "3_PARALLEL_INVESTIGATORS_TO_SYNTHESIS_TO_EVALUATOR",
                    "case_families": len(investigation_case_catalog()),
                    "operational_authority": "NONE",
                },
            },
            "case_version": self._case_version,
            "conversation": list(self._conversation),
            "activity": list(self._events[-80:]),
            "latest_sequence": self._sequence,
        }

    def runtime_truth(self) -> dict[str, object]:
        """Return local-fixture runtime truth without starting an Agent run."""

        raw_strands = self._diagnosis.get("strands_investigation")
        strands = dict(raw_strands) if isinstance(raw_strands, Mapping) else {}
        return {
            "source_mode": "synthetic",
            "provider_mode": str(strands.get("mode") or "scripted"),
            "provider_configured": bool(strands),
            "calls_observed": bool(strands.get("runtime_events")),
            "write_scope": "local_synthetic_only",
            "external_provider_writes": "disabled",
            "latest_run_state": self._agent_state,
        }

    def stop(self) -> dict[str, object]:
        if self._agent_state in {"IDLE", "STOPPED", "VERIFIED"}:
            raise ValueError("only an active investigation can be paused")
        self._agent_state = "STOPPED"
        self._diagnosis.update(
            {
                "status": "STOPPED",
                "summary": "Investigation paused by the operator; no effect was issued.",
            }
        )
        self._append(
            "human.investigation.paused",
            "STOPPED",
            "Investigation paused by operator",
            "Evidence remains available; no synthetic effect was issued.",
        )
        return self.current()

    def authorize_diagnosis(self, operator_id: str) -> dict[str, object]:
        """Bind an explicit human decision to the next read-only diagnosis run."""

        operator = " ".join(operator_id.split())
        if not operator:
            raise ValueError("diagnosis authorization requires an operator identity")
        if self._agent_state not in {"IDLE", "STOPPED"} and not (
            self._agent_state == "BLOCKED"
            and self._diagnosis.get("finding") in {"AGENT_UNAVAILABLE", "AGENT_VALIDATION_FAILED"}
        ):
            return self.current()
        self._diagnosis_authorization = {
            "authorization_id": f"diagnosis-auth-{uuid4().hex[:16]}",
            "operator_id": operator,
            "authorized_at": self._now(),
            "scope": "READ_ONLY_CROSS_SYSTEM_DIAGNOSIS",
            "case_version": self._case_version,
        }
        self._append(
            "human.diagnosis.authorized",
            "AUTHORIZED",
            "Diagnosis authorized",
            "A human operator released one bounded, read-only cross-system investigation.",
        )
        return self.current()

    def claim_diagnosis(self) -> tuple[dict[str, object], bool]:
        """Atomically claim the one paid advisory run for the active case."""

        with self._run_lock:
            if not self._diagnosis_authorization:
                raise ValueError("human authorization is required before diagnosis")
            retryable_failure = self._agent_state == "BLOCKED" and self._diagnosis.get(
                "finding"
            ) in {"AGENT_UNAVAILABLE", "AGENT_VALIDATION_FAILED"}
            if self._agent_state not in {"IDLE", "STOPPED"} and not retryable_failure:
                return self.current(), False
            return self.diagnose(release=False), True

    def diagnose(self, *, release: bool = True) -> dict[str, object]:
        retryable_failure = self._agent_state == "BLOCKED" and self._diagnosis.get("finding") in {
            "AGENT_UNAVAILABLE",
            "AGENT_VALIDATION_FAILED",
        }
        if self._agent_state not in {"IDLE", "STOPPED"} and not retryable_failure:
            return self.current()
        self._run_id = f"m20-{uuid4().hex}"
        self._runtime_events = []
        self._approval = {}
        self._rejection = {}
        self._agent_state = "OBSERVING"
        self._append(
            "agent.run.started",
            "OBSERVING",
            "Autonomous investigation opened",
            "Incident admission started a bounded evidence packet for Strands.",
        )
        self._agent_state = "GATHERING"
        self._append(
            "agent.erp.key_reread",
            "ABSENT"
            if self._case.erp_receipt_key_found is False
            else "POSTED"
            if self._case.erp_receipt_key_found is True
            else "UNAVAILABLE",
            "ERP business-key reread",
            f"{self._case.receipt_business_key} lookup completed.",
        )
        disposition = self._case.disposition()
        if self._scenario_variant == "physical_shortage":
            status, finding, summary = (
                "BLOCKED",
                "PHYSICAL_SHORTAGE_CONFIRMED",
                "Warehouse scans do not reconcile to the ordered quantity; preserve the hold "
                "and escalate the supplier shortage instead of manufacturing an ERP receipt.",
            )
        elif self._scenario_variant == "evidence_conflict":
            status, finding, summary = (
                "BLOCKED",
                "CROSS_SOURCE_QUANTITY_CONFLICT",
                "The integration attempt quantity conflicts with the authoritative ERP gap; "
                "request a fresh scoped read before choosing an effect.",
            )
        elif self._scenario_variant == "duplicate_invoice":
            status, finding, summary = (
                "BLOCKED",
                "DUPLICATE_SUPPLIER_INVOICE",
                "The supplier invoice number already exists on a posted ERP document; preserve "
                "the hold and route the duplicate to AP review.",
            )
        elif self._scenario_variant == "unit_price_variance":
            status, finding, summary = (
                "BLOCKED",
                "COMMERCIAL_TERMS_MISMATCH",
                "Invoice pricing conflicts with the approved PO line; inventory recovery cannot "
                "resolve a commercial variance.",
            )
        elif self._scenario_variant == "uom_conversion_missing":
            status, finding, summary = (
                "BLOCKED",
                "UOM_CONVERSION_EVIDENCE_REQUIRED",
                "The integration quantity uses cases while ERP expects eaches, and no approved "
                "conversion is available.",
            )
        elif self._scenario_variant == "po_revision_race":
            status, finding, summary = (
                "BLOCKED",
                "PO_REVISION_EVIDENCE_REQUIRED",
                "The integration attempt used an older PO revision; refresh the scoped records "
                "before choosing any effect.",
            )
        elif self._scenario_variant == "supplier_hold":
            status, finding, summary = (
                "BLOCKED",
                "SUPPLIER_COMPLIANCE_HOLD",
                "The vendor master is compliance-blocked; preserve the invoice hold and route it "
                "to the authorized supplier owner.",
            )
        elif self._scenario_variant == "lot_trace_mismatch":
            status, finding, summary = (
                "BLOCKED",
                "LOT_TRACE_MISMATCH",
                "The ERP-held quality lot is absent from physical scans; preserve both holds and "
                "reconcile lot identity before release.",
            )
        elif self._scenario_variant == "normal_complete":
            status, finding, summary = (
                "RECOVERY_COMPLETE",
                "NO_EXCEPTION_REMAINS",
                "Authoritative records reconcile and the invoice is open; no action is needed.",
            )
        elif disposition is CaseDisposition.RECOVERY_READY:
            status, finding, summary = (
                "PLAN_READY",
                "AMBIGUOUS_RECEIPT_RESOLVED",
                f"ERP proves the {self._case.receipt_unresolved_quantity}-unit receipt is absent; "
                f"the exact {self._case.quality_hold_quantity}-unit approved quality lot "
                "is eligible for a bounded recovery.",
            )
        elif disposition is CaseDisposition.RECONCILE_ONLY:
            status, finding, summary = (
                "BLOCKED",
                "EFFECT_ALREADY_PRESENT",
                "ERP already contains an idempotent business key; reconcile the integration "
                "attempt and do not retry.",
            )
        elif disposition is CaseDisposition.SAFE_STOP:
            status, finding, summary = (
                "BLOCKED",
                "QUALITY_EVIDENCE_INELIGIBLE",
                "The exact quality evidence is not approved; preserve inventory and invoice holds.",
            )
        else:
            status, finding, summary = (
                "BLOCKED",
                "NEEDS_ERP_KEY_REREAD",
                "The integration result is ambiguous until the ERP business-key reread completes.",
            )
        self._policy_decision = {"status": status, "finding": finding, "summary": summary}
        self._agent_state = status if release else "SYNTHESIZING"
        self._diagnosis = {
            "status": status if release else "INVESTIGATING",
            "finding": finding if release else "PENDING_AGENT_VALIDATION",
            "summary": summary
            if release
            else "Source evidence is reconciled; the real Strands result is still pending.",
            "confidence": 0.94
            if release and status in {"PLAN_READY", "RECOVERY_COMPLETE"}
            else 0.0,
            "hypotheses": [
                {
                    "id": "missing_erp_receipt",
                    "label": "Receipt write never committed",
                    "status": (
                        "SUPPORTED"
                        if self._scenario_variant == "uncommitted_receipt"
                        else "ELIMINATED"
                        if self._case.erp_receipt_key_found is True
                        else "OPEN"
                    ),
                },
                {
                    "id": "duplicate_post",
                    "label": "Receipt already exists in ERP",
                    "status": (
                        "SUPPORTED" if self._case.erp_receipt_key_found is True else "ELIMINATED"
                    ),
                },
                {
                    "id": "physical_shortage",
                    "label": "Supplier delivered fewer than 100",
                    "status": (
                        "SUPPORTED"
                        if self._scenario_variant == "physical_shortage"
                        else "ELIMINATED"
                    ),
                },
                {
                    "id": "quality_not_approved",
                    "label": "Quality lot cannot be released",
                    "status": (
                        "ELIMINATED"
                        if self._case.quality_disposition is QualityDisposition.APPROVED
                        else "SUPPORTED"
                    ),
                },
            ],
            "tool_calls": [
                {"tool": "read_control_context", "status": "COMPLETE"},
                {"tool": "read_erp_evidence", "status": "COMPLETE"},
                {"tool": "read_airtable_evidence", "status": "COMPLETE"},
                {"tool": "read_celigo_evidence", "status": "COMPLETE"},
                {"tool": "read_collaboration_evidence", "status": "COMPLETE"},
            ],
        }
        if not release:
            self._policy_decision["hypotheses"] = [
                dict(item) for item in self._diagnosis["hypotheses"] if isinstance(item, Mapping)
            ]
            self._diagnosis["hypotheses"] = [
                {**dict(item), "status": "PENDING"}
                for item in self._diagnosis["hypotheses"]
                if isinstance(item, Mapping)
            ]
            # Deterministic source preparation is not a model tool call. Only
            # the SDK hook stream may populate the visible Agent tool ledger.
            self._diagnosis["tool_calls"] = []
        self._append(
            "policy.diagnosis.completed",
            status if release else "PENDING_AGENT",
            "Evidence reconciliation completed"
            if not release
            else "Deterministic policy evaluation completed",
            summary
            if release
            else "Policy result is held until the real Strands response passes validation.",
        )
        return self.current()

    def record_agent_tool_progress(
        self, tool_name: str, phase: str = "started", run_id: str | None = None
    ) -> None:
        """Publish each real model tool call while the HTTP request is still running."""

        if self._agent_state == "STOPPED" or (run_id is not None and run_id != self._run_id):
            return

        source_labels = {
            "read_control_context": "Control policy",
            "read_erp_evidence": "ERPNext ledger",
            "read_airtable_evidence": "Quality registry",
            "read_celigo_evidence": "Integration trace",
            "read_collaboration_evidence": "Warehouse scans",
            "reconcile_source_records": "Cross-source reconciliation",
            "apply_control_policy": "Deterministic policy gate",
        }
        synthesis = tool_name in {"reconcile_source_records", "apply_control_policy"}
        if phase == "started":
            self._agent_state = "SYNTHESIZING" if synthesis else "GATHERING"
        event_type = (
            "agent.strands.tool.succeeded"
            if phase == "succeeded"
            else "agent.strands.reconciling"
            if synthesis
            else "agent.strands.tool.started"
        )
        detail = (
            "Read-only evidence returned"
            if phase == "succeeded"
            else "Joining authoritative records"
            if synthesis
            else "Read-only evidence request started"
        )
        self._append(
            event_type,
            "COMPLETE" if phase == "succeeded" else self._agent_state,
            source_labels.get(tool_name, tool_name),
            detail,
        )

    def record_agent_runtime_progress(
        self, runtime_event: Mapping[str, object], run_id: str | None = None
    ) -> None:
        """Project genuine SDK model-call hooks into the live event ledger.

        Tool hook events already have richer source labels through
        ``record_agent_tool_progress``.  This projection deliberately keeps only
        model boundaries so the judge can see when the model is reasoning versus
        when deterministic evidence tools are executing.
        """

        if self._agent_state == "STOPPED" or (run_id is not None and run_id != self._run_id):
            return
        event_type = str(runtime_event.get("type", ""))
        if event_type not in {
            "model.started",
            "model.succeeded",
            "model.failed",
            "tool.started",
            "tool.succeeded",
            "tool.failed",
        }:
            return
        safe_event = {
            key: value
            for key, value in runtime_event.items()
            if key
            in {
                "sequence",
                "type",
                "tool",
                "tool_use_id",
                "duration_ms",
                "projected_input_tokens",
            }
            and isinstance(value, (str, int, float, bool, type(None)))
        }
        self._runtime_events.append(safe_event)
        if event_type.startswith("tool."):
            return
        if event_type == "model.started":
            self._agent_state = "REASONING"
            projected_tokens = runtime_event.get("projected_input_tokens")
            detail = (
                f"Strands model turn opened with {projected_tokens} projected input tokens"
                if isinstance(projected_tokens, int)
                else "Strands model turn opened"
            )
            status = "REASONING"
            label = "Model reasoning"
        elif event_type == "model.failed":
            detail = "SDK model hook reported a failed turn; no write authority was available"
            status = "FAILED"
            label = "Model turn failed"
        else:
            detail = "SDK model hook closed the reasoning turn"
            status = "COMPLETE"
            label = "Model turn complete"
        self._append(f"agent.strands.{event_type}", status, label, detail)

    def record_strands_investigation(self, advisory: Mapping[str, object]) -> dict[str, object]:
        """Persist a real Strands trace without granting it control-plane authority."""

        advisory_run_id = str(advisory.get("run_id", ""))
        if self._agent_state == "STOPPED" or (advisory_run_id and advisory_run_id != self._run_id):
            return self.current()

        status = str(advisory.get("status", "AGENT_UNAVAILABLE"))
        final_runtime = advisory.get("runtime_events")
        if isinstance(final_runtime, list):
            self._runtime_events = [
                dict(event) for event in final_runtime if isinstance(event, Mapping)
            ]
        self._diagnosis["strands_investigation"] = dict(advisory)
        if status != "COMPLETE":
            self._agent_state = "BLOCKED"
            self._approval = {}
            failure_finding = (
                "AGENT_VALIDATION_FAILED" if status == "VALIDATION_FAILED" else "AGENT_UNAVAILABLE"
            )
            self._diagnosis.update(
                {
                    "status": "BLOCKED",
                    "finding": failure_finding,
                    "summary": (
                        "The real Strands Agent did not complete, so no diagnosis or recovery "
                        "plan was released. Retry after the provider is available."
                    ),
                    "confidence": 0.0,
                }
            )
            self._append(
                "agent.strands.degraded",
                "BLOCKED",
                "Strands investigation unavailable",
                "No model conclusion or recovery plan was released; deterministic "
                "controls failed closed.",
            )
            return self.current()
        result = advisory.get("result")
        disposition = result.get("disposition", "") if isinstance(result, Mapping) else ""
        reason = result.get("reason") if isinstance(result, Mapping) else None
        if isinstance(reason, str) and reason.strip():
            self._diagnosis["summary"] = reason.strip()
        policy = self._policy_decision
        self._agent_state = str(policy.get("status", "BLOCKED"))
        self._diagnosis.update(
            {
                "status": self._agent_state,
                "finding": str(policy.get("finding", "AGENT_VALIDATED")),
                "hypotheses": list(policy.get("hypotheses", self._diagnosis.get("hypotheses", []))),
                "confidence": 0.94
                if self._agent_state in {"PLAN_READY", "RECOVERY_COMPLETE"}
                else 0.0,
            }
        )
        self._append(
            "agent.strands.completed",
            "COMPLETE",
            "Strands investigation completed",
            f"Read-only advisory returned {disposition}; deterministic policy retains authority.",
        )
        return self.current()

    def approve(self, manager_id: str) -> dict[str, object]:
        manager = " ".join(manager_id.split())
        if not manager or self._agent_state != "PLAN_READY":
            raise ValueError("Manager approval requires a current recovery-ready diagnosis")
        binding = self._approval_binding()
        plan_digest = str(binding["plan_digest"])
        self._approval = {
            "approval_id": f"m20-approval-{plan_digest[:16]}",
            "manager_id": manager,
            "approved_at": self._now(),
            **binding,
        }
        self._append(
            "manager.approval.granted",
            "APPROVED",
            "Manager approval recorded",
            f"Approval is bound to the {self._case.receipt_unresolved_quantity}-unit receipt "
            f"and {self._case.quality_hold_quantity}-unit quality transfer.",
        )
        return self.current()

    def reject_plan(self, manager_id: str, reason: str) -> dict[str, object]:
        """Record a human refusal without issuing or mutating any business effect."""

        manager = " ".join(manager_id.split())
        rationale = " ".join(reason.split())
        if not manager or not rationale:
            raise ValueError("Manager rejection requires manager_id and reason")
        if self._agent_state != "PLAN_READY" or self._approval or self._execution:
            raise ValueError("Manager rejection requires a current unexecuted recovery plan")
        self._rejection = {
            "decision_id": f"m20-rejection-{uuid4().hex[:16]}",
            "manager_id": manager,
            "reason": rationale,
            "rejected_at": self._now(),
            "case_version": self._case_version,
            "plan_digest": str(self._approval_binding()["plan_digest"]),
        }
        self._agent_state = "BLOCKED"
        self._diagnosis.update(
            {
                "status": "BLOCKED",
                "finding": "HUMAN_REJECTED_PLAN",
                "summary": f"Manager rejected the recovery plan: {rationale}",
                "confidence": 0.0,
            }
        )
        self._append(
            "manager.plan.rejected",
            "REJECTED",
            "Manager rejected recovery",
            "The proposed local recovery was refused; no business effect was issued.",
        )
        return self.current()

    def execute(self, approval_id: str, idempotency_key: str) -> dict[str, object]:
        if self._agent_state == "STOPPED":
            raise ValueError("a paused investigation cannot execute a recovery")
        if approval_id != self._approval.get("approval_id") or not idempotency_key.strip():
            raise ValueError(
                "execution requires the current Manager approval and an idempotency key"
            )
        if self._execution:
            if self._execution.get("idempotency_key") == idempotency_key:
                return self.current()
            raise ValueError("a different idempotency key cannot replace a completed recovery")
        if self._case.disposition() is not CaseDisposition.RECOVERY_READY:
            raise ValueError("current evidence does not permit recovery")
        current_binding = self._approval_binding()
        for field in ("plan_digest", "case_version", "demo_tenant", "scope"):
            if self._approval.get(field) != current_binding[field]:
                raise ValueError("approval is stale because evidence or recovery scope changed")
        self._pre_execution_case = self._case.model_copy(deep=True)
        self._recovery_scope = {
            "receipt_post_quantity": self._case.receipt_unresolved_quantity,
            "quality_transfer_quantity": self._case.quality_hold_quantity,
        }
        self._execution = {
            "available": False,
            "status": "VERIFYING",
            "detail": (
                "Local synthetic receipt and quality transfer applied; verifying authoritative "
                "reread."
            ),
            "idempotency_key": idempotency_key,
            "approval_id": approval_id,
            "executed_at": self._now(),
            "transfer_name": "M20-TRANSFER-4817",
            "invoice_name": self._case.invoice_id,
        }
        self._case = AmbiguousReceiptCase.model_validate(
            {
                **self._case.model_dump(),
                "available_quantity": self._case.physically_arrived,
                "quality_hold_quantity": 0,
                "receipt_unresolved_quantity": 0,
                "invoice_held": False,
                "integration_outcome": IntegrationOutcome.ACKNOWLEDGED,
                "erp_receipt_key_found": True,
                "quality_transfer_key_found": True,
            }
        )
        self._case_version += 1
        self._append(
            "executor.completed",
            "VERIFYING",
            "Bounded recovery completed",
            f"One idempotent {self._recovery_scope['receipt_post_quantity']}-unit receipt and "
            f"one {self._recovery_scope['quality_transfer_quantity']}-unit quality transfer "
            "were applied locally.",
        )
        return self.current()

    def approve_execute_verify(self, manager_id: str, idempotency_key: str) -> dict[str, object]:
        """Apply one human decision, then automatically execute and reread its exact scope."""

        approved = self.approve(manager_id)
        execution = approved["execution"]
        assert isinstance(execution, Mapping)
        approval_id = str(execution["approval_id"])
        self.execute(approval_id, idempotency_key)
        return self.verify()

    def record_conversation_turn(
        self, question: str, answer: str, advisory: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a case/run-scoped visible conversation without granting write authority."""

        raw_evidence_ids = advisory.get("evidence_ids", [])
        evidence_ids = (
            [str(item) for item in raw_evidence_ids]
            if isinstance(raw_evidence_ids, (list, tuple))
            else []
        )
        provider = advisory.get("provider", {})
        usage = advisory.get("usage", {})
        tool_calls = advisory.get("tool_calls", [])
        self._conversation.append(
            {
                "turn_id": f"turn-{len(self._conversation) + 1:03d}",
                "run_id": self._run_id,
                "question": question,
                "answer": answer,
                "evidence_ids": evidence_ids,
                "tool_calls": (
                    [str(item) for item in tool_calls]
                    if isinstance(tool_calls, (list, tuple))
                    else []
                ),
                "provider": dict(provider) if isinstance(provider, Mapping) else {},
                "usage": dict(usage) if isinstance(usage, Mapping) else {},
                "latency_ms": int(advisory.get("latency_ms", 0) or 0),
                "context_turns": int(advisory.get("context_turns", 0) or 0),
                "created_at": self._now(),
            }
        )
        self._append(
            "human.agent.conversation.completed",
            "ANSWERED",
            "Evidence Agent answered",
            f"Conversation turn {len(self._conversation)} cited "
            f"{len(evidence_ids)} evidence records.",
        )
        return self.current()

    def verify(self) -> dict[str, object]:
        if self._execution.get("status") != "VERIFYING":
            raise ValueError("verification requires a completed recovery")
        if (
            self._case.available_quantity != self._case.physically_arrived
            or self._case.invoice_held
        ):
            raise ValueError("authoritative reread failed")
        self._execution.update(
            {
                "status": "VERIFIED",
                "verified_at": self._now(),
                "detail": (
                    f"Authoritative synthetic reread proves {self._case.available_quantity} "
                    "available, invoice open, and no "
                    "duplicate business key."
                ),
            }
        )
        self._agent_state = "VERIFIED"
        self._diagnosis.update(
            {
                "status": "VERIFIED",
                "finding": "RECOVERY_VERIFIED",
                "summary": self._execution["detail"],
                "confidence": 0.99,
            }
        )
        self._append(
            "executor.verified", "VERIFIED", "Recovery verified", str(self._execution["detail"])
        )
        self._append(
            "agent.resolution_packet.issued",
            "VERIFIED",
            "Resolution packet issued",
            "Verified recovery is bound to its evidence, approval, and authoritative reread.",
        )
        return self.current()
