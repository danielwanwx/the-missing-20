"""Closed-loop controller for the disclosed-synthetic procurement demo.

It owns only the isolated M20 fixture.  The controller models the same
evidence/approval/execution boundaries as the provider-backed platform, while
keeping the demo's write effects local and explicit.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from the_missing_20.domain.ambiguous_receipt import (
    AmbiguousReceiptCase,
    CaseDisposition,
    IntegrationOutcome,
    primary_case,
)


class AmbiguousCasePlatform:
    """A small, idempotent end-to-end case controller for judge-mode replay."""

    def __init__(self, case: AmbiguousReceiptCase | None = None) -> None:
        self._case = case or primary_case()
        self._sequence = 0
        self._events: list[dict[str, object]] = []
        self._agent_state = "IDLE"
        self._diagnosis: dict[str, object] = {
            "status": "IDLE",
            "finding": "NOT_EVALUATED",
            "summary": "No diagnosis has run.",
            "tool_calls": [],
        }
        self._approval: dict[str, object] = {}
        self._execution: dict[str, object] = {}
        self._admit_initial_evidence()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _append(self, event_type: str, status: str, label: str, detail: str) -> None:
        self._sequence += 1
        self._events.append(
            {
                "sequence": self._sequence,
                "event_id": f"m20-ambiguous-{self._sequence:05d}",
                "event_type": event_type,
                "occurred_at": self._now(),
                "source_id": "m20-ambiguous-case",
                "provider": "Missing 20 synthetic demo tenant",
                "status": status,
                "label": label,
                "detail": detail,
                "provenance": "synthetic-demo-fixture",
                "read_only": event_type.startswith("source."),
            }
        )

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

    def _constellation(self) -> dict[str, object]:
        disposition = self._case.disposition()
        execution_status = str(self._execution.get("status", ""))
        if execution_status == "VERIFIED":
            conclusion = ("RECOVERY VERIFIED", "VERIFIED", 0.99)
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
                    "id": "jira_slack",
                    "position": "LEFT",
                    "role": "CONTEXT",
                    "label": "Manager",
                    "status": "APPROVED" if self._approval else "WAITING",
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
        return {
            "available": self._case.disposition() is CaseDisposition.RECOVERY_READY
            and self._agent_state == "PLAN_READY",
            "status": "AWAITING_MANAGER_APPROVAL",
            "detail": "Manager approval is required before a local synthetic recovery.",
        }

    def current(self) -> dict[str, object]:
        facts = self._case.evidence_projection()
        return {
            "schema_version": "missing20-agent-platform/v2",
            "received_at": self._now(),
            "mode": {
                "read_only": False,
                "provider_writes": "LOCAL_SYNTHETIC_ONLY",
                "execution_available": True,
                "provenance": "synthetic-demo-fixture",
            },
            "correlation": self._correlation(),
            "demo_case": {"provenance": "synthetic-demo-fixture", "read_only": True, "case": facts},
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
                    "id": "slack",
                    "name": "Slack",
                    "status": "CONNECTED",
                    "authority": "Synthetic manager audit",
                    "read_only": True,
                    "write_state": "DISABLED",
                },
            ],
            "agent_run": {
                "run_id": "m20-ambiguous-run-001" if self._agent_state != "IDLE" else "",
                "state": self._agent_state,
                "active_step": ""
                if self._agent_state not in {"OBSERVING", "GATHERING"}
                else "reread_erp_key",
                "confidence": 0.94 if self._agent_state == "PLAN_READY" else 0.0,
            },
            "plan": self._plan(),
            "evidence_constellation": self._constellation(),
            "diagnosis": dict(self._diagnosis),
            "execution": self._execution_projection(),
            "activity": list(self._events[-80:]),
            "latest_sequence": self._sequence,
        }

    def diagnose(self) -> dict[str, object]:
        self._agent_state = "OBSERVING"
        self._append(
            "agent.run.started",
            "OBSERVING",
            "Agent investigation opened",
            "Reading five source-scoped evidence packets.",
        )
        self._agent_state = "GATHERING"
        self._append(
            "agent.erp.key_reread",
            "ABSENT" if self._case.erp_receipt_key_found is False else "POSTED",
            "ERP business-key reread",
            f"{self._case.receipt_business_key} lookup completed.",
        )
        disposition = self._case.disposition()
        if disposition is CaseDisposition.RECOVERY_READY:
            status, finding, summary = (
                "PLAN_READY",
                "AMBIGUOUS_RECEIPT_RESOLVED",
                "ERP proves the 12-unit receipt is absent; the exact 8-unit approved quality lot "
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
        self._agent_state = status
        self._diagnosis = {
            "status": status,
            "finding": finding,
            "summary": summary,
            "tool_calls": [
                {"tool": "read_control_context", "status": "COMPLETE"},
                {"tool": "read_erp_evidence", "status": "COMPLETE"},
                {"tool": "read_airtable_evidence", "status": "COMPLETE"},
                {"tool": "read_celigo_evidence", "status": "COMPLETE"},
                {"tool": "read_collaboration_evidence", "status": "COMPLETE"},
            ],
        }
        self._append("agent.diagnosis.completed", status, "Agent diagnosis completed", summary)
        return self.current()

    def approve(self, manager_id: str) -> dict[str, object]:
        manager = " ".join(manager_id.split())
        if not manager or self._agent_state != "PLAN_READY":
            raise ValueError("Manager approval requires a current recovery-ready diagnosis")
        self._approval = {"approval_id": "m20-manager-approval-4817", "manager_id": manager}
        self._append(
            "manager.approval.granted",
            "APPROVED",
            "Manager approval recorded",
            "Approval is bound to the 12-unit receipt and 8-unit quality transfer.",
        )
        return self.current()

    def execute(self, approval_id: str, idempotency_key: str) -> dict[str, object]:
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
        self._execution = {
            "available": False,
            "status": "VERIFYING",
            "detail": (
                "Local synthetic receipt and quality transfer applied; verifying authoritative "
                "reread."
            ),
            "idempotency_key": idempotency_key,
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
        self._append(
            "executor.completed",
            "VERIFYING",
            "Bounded recovery completed",
            "One idempotent 12-unit receipt and one 8-unit quality transfer were applied locally.",
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
                "detail": (
                    "Authoritative synthetic reread proves 100 available, invoice open, and no "
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
            }
        )
        self._append(
            "executor.verified", "VERIFIED", "Recovery verified", str(self._execution["detail"])
        )
        return self.current()
