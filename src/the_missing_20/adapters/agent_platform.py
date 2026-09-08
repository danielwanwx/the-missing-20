"""Evidence-bound coordination for the Agent Platform console.

The coordinator joins narrow ERPNext and SaaS reads.  An optional executor may
perform one Manager-gated, idempotent ERPNext effect; diagnosis remains
read-only and closure always requires fresh provider reads.  Its event ledger
is owned by the server, not by browser polling, so repeated reads cannot be
presented as newly-created provider activity.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from the_missing_20.adapters.demo_executor import DemoReleasePlan

AGENT_PLATFORM_SCHEMA_VERSION = "missing20-agent-platform/v1"


class EvidenceReader(Protocol):
    """Minimal read-only contract shared by the evidence adapters."""

    def current(self) -> dict[str, object]: ...


class DemoExecutor(Protocol):
    def execute(self, plan: DemoReleasePlan) -> object: ...


class AgentPlatform:
    """Build a truthful, case-scoped platform projection from provider reads."""

    def __init__(
        self,
        erpnext: EvidenceReader,
        saas: EvidenceReader,
        *,
        executor: DemoExecutor | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._erpnext = erpnext
        self._saas = saas
        self._executor = executor
        self._state_path = state_path
        self._lock = threading.RLock()
        self._sequence = 0
        self._events: list[dict[str, object]] = []
        self._seen_source_records: set[str] = set()
        self._source_sequences: dict[str, int] = {}
        self._run_number = 0
        self._agent_run: dict[str, object] = {
            "run_id": "",
            "state": "IDLE",
            "active_step": "",
            "confidence": 0.0,
        }
        self._diagnosis: dict[str, object] = {
            "status": "IDLE",
            "summary": "No diagnosis has run. Guarded provider effects are inactive.",
            "finding": "NOT_EVALUATED",
            "tool_calls": [],
        }
        self._approval: dict[str, object] = {}
        self._execution: dict[str, object] = {}
        self._resolution_packet: dict[str, object] = {}
        self._conversation: list[dict[str, object]] = []
        self._load_state()

    def _load_state(self) -> None:
        """Restore non-secret control evidence for restart-safe verification."""

        if self._state_path is None or not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(payload, Mapping):
            return
        self._sequence = int(payload.get("sequence") or 0)
        self._run_number = int(payload.get("run_number") or 0)
        events = payload.get("events")
        if isinstance(events, list):
            self._events = [dict(item) for item in events if isinstance(item, Mapping)][-80:]
        for attribute, key in (
            ("_agent_run", "agent_run"),
            ("_diagnosis", "diagnosis"),
            ("_approval", "approval"),
            ("_execution", "execution"),
            ("_resolution_packet", "resolution_packet"),
        ):
            value = payload.get(key)
            if isinstance(value, Mapping):
                setattr(self, attribute, dict(value))
        conversation = payload.get("conversation")
        if isinstance(conversation, list):
            self._conversation = [
                self._validate_stored_conversation_turn(dict(item))
                for item in conversation
                if isinstance(item, Mapping)
            ][-12:]
        source_sequences = payload.get("source_sequences")
        if isinstance(source_sequences, Mapping):
            self._source_sequences = {
                str(key): int(value)
                for key, value in source_sequences.items()
                if isinstance(value, int)
            }
        seen = payload.get("seen_source_records")
        if isinstance(seen, list):
            self._seen_source_records = {str(item) for item in seen}

    @staticmethod
    def _validate_stored_conversation_turn(turn: dict[str, object]) -> dict[str, object]:
        """Quarantine a historically persisted claim rejected by the causal validator."""

        answer = str(turn.get("answer") or "")
        lowered = answer.lower()
        unsupported = (
            "causal revenue uplift proven" in lowered
            and "does not prove causal revenue uplift" not in lowered
        )
        if unsupported:
            turn["answer"] = (
                "Rejected by the deterministic causal-claim validator. The live ERP reread "
                "proves delivery, billing, and the observed $42,000 accounting outcome; this "
                "demo does not prove that the platform caused incremental revenue."
            )
            turn["validation_status"] = "REJECTED_CAUSAL_CLAIM"
        return turn

    def runtime_truth(self) -> dict[str, object]:
        """Return non-secret, non-network runtime truth for the health endpoint."""

        strands = self._diagnosis.get("strands_investigation")
        trace = dict(strands) if isinstance(strands, Mapping) else {}
        provider = trace.get("provider")
        provider_map = dict(provider) if isinstance(provider, Mapping) else {}
        mode = str(trace.get("mode") or "")
        calls_observed = mode == "real_strands" and bool(trace.get("runtime_events"))
        return {
            "source_mode": "live",
            "provider_mode": str(provider_map.get("mode") or "bedrock"),
            "provider_configured": True,
            "calls_observed": calls_observed,
            "model": str(provider_map.get("model") or ""),
            "write_scope": "demo_tenant_manager_gated" if self._executor else "read_only",
            "external_provider_writes": "manager_gated" if self._executor else "disabled",
            "latest_run_state": str(self._agent_run.get("state") or "IDLE"),
        }

    def _persist_state(self) -> None:
        """Atomically persist the control trail without provider credentials."""

        if self._state_path is None:
            return
        payload = {
            "schema_version": "missing20-agent-platform-state/v1",
            "sequence": self._sequence,
            "run_number": self._run_number,
            "events": self._events[-80:],
            "agent_run": self._agent_run,
            "diagnosis": self._diagnosis,
            "approval": self._approval,
            "execution": self._execution,
            "resolution_packet": self._resolution_packet,
            "conversation": self._conversation[-12:],
            "source_sequences": self._source_sequences,
            "seen_source_records": sorted(self._seen_source_records),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_suffix(f"{self._state_path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        temporary.replace(self._state_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _text(value: object, default: str = "") -> str:
        return value if isinstance(value, str) else default

    @classmethod
    def _signature(cls, item: Mapping[str, object]) -> str:
        stable = {
            "provider": cls._text(item.get("provider")),
            "source_id": cls._text(item.get("source_id")),
            "record_id": cls._text(item.get("record_id")),
            "status": cls._text(item.get("status")),
            "label": cls._text(item.get("label")),
            "detail": cls._text(item.get("detail")),
            "evidence_kind": cls._text(item.get("evidence_kind")),
            "erp_acknowledged": item.get("erp_acknowledged"),
            "correlation": item.get("correlation", {}),
        }
        return hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

    def _append(
        self,
        event_type: str,
        *,
        source_id: str,
        provider: str,
        status: str,
        label: str,
        detail: str,
        provenance: str = "live",
        record_id: str = "",
        read_only: bool = True,
    ) -> dict[str, object]:
        self._sequence += 1
        event = {
            "sequence": self._sequence,
            "event_id": f"agent-platform-{self._sequence:06d}",
            "event_type": event_type,
            "occurred_at": self._now(),
            "source_id": source_id,
            "provider": provider,
            "status": status,
            "label": label,
            "detail": detail,
            "record_id": record_id,
            "provenance": provenance,
            "read_only": read_only,
        }
        self._events.append(event)
        self._persist_state()
        return event

    def _current_tool_calls(self) -> list[Mapping[str, object]]:
        raw_calls = self._diagnosis.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            return []
        return [call for call in raw_calls if isinstance(call, Mapping)]

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @classmethod
    def _evidence_ids(cls, advisory: Mapping[str, object]) -> list[str]:
        findings = cls._mapping(advisory.get("evidence_findings"))
        result = cls._mapping(advisory.get("result"))
        raw_ids = findings.get("evidence_ids") or result.get("evidence_ids") or []
        if not isinstance(raw_ids, (list, tuple)):
            return []
        return list(dict.fromkeys(item for item in raw_ids if isinstance(item, str) and item))

    def _apply_completed_strands_diagnosis(
        self,
        advisory: Mapping[str, object],
        erp: Mapping[str, object],
        saas: Mapping[str, object],
    ) -> None:
        """Project a validated SDK result onto the current authoritative source state.

        The deterministic policy embedded in ``evidence_findings`` remains the
        decision authority. The model's prose is shown only after that policy
        has returned the same recovery-ready disposition.
        """

        if self._text(advisory.get("status")) != "COMPLETE":
            return
        findings = self._mapping(advisory.get("evidence_findings"))
        policy = self._mapping(findings.get("policy"))
        policy_checks = self._mapping(policy.get("checks"))
        result = self._mapping(advisory.get("result"))
        if (
            self._text(policy.get("disposition")) != "RECOVERY_READY"
            or self._text(result.get("disposition")) != "RECOVERY_READY"
        ):
            return

        documents = self._documents_by_kind(erp)
        invoice = documents.get("purchase_invoice", {})
        quality_hold = float(self._live_flow_metrics(erp)["quality_hold"] or 0)
        invoice_held = bool(invoice.get("on_hold")) or self._text(invoice.get("status")) in {
            "PAYMENT_HOLD",
            "HELD",
        }
        correlation = self._correlation(erp, saas)
        inventory_reconciled = quality_hold <= 0
        customer_order_gap = policy_checks.get("customer_order_requires_fulfillment") is True

        if customer_order_gap:
            finding = "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT"
        elif inventory_reconciled and invoice_held:
            finding = "INVOICE_PAYMENT_HOLD"
        elif quality_hold > 0:
            finding = "QUALITY_HOLD_DETECTED"
        else:
            finding = "RECOVERY_READY"
        summary = self._text(result.get("reason")) or self._text(policy.get("reason"))
        self._diagnosis.update(
            {
                "status": "PLAN_READY",
                "finding": finding,
                "summary": summary,
                "confidence": 0.91,
                "hypotheses": [
                    {
                        "id": "quality_hold",
                        "label": "Inventory remains in Quality Hold",
                        "status": "SUPPORTED" if quality_hold > 0 else "ELIMINATED",
                    },
                    {
                        "id": "invoice_payment_hold",
                        "label": "Invoice remains held after inventory reconciliation",
                        "status": (
                            "SUPPORTED" if inventory_reconciled and invoice_held else "ELIMINATED"
                        ),
                    },
                    {
                        "id": "correlation_gap",
                        "label": "Source records refer to different receipts",
                        "status": (
                            "ELIMINATED"
                            if correlation["status"] == "FULLY_CORRELATED"
                            else "SUPPORTED"
                        ),
                    },
                    {
                        "id": "customer_order_value_gap",
                        "label": "Customer order is not yet delivered and billed",
                        "status": "SUPPORTED" if customer_order_gap else "ELIMINATED",
                    },
                    {
                        "id": "journal_is_causal",
                        "label": "Slack or Jira alone proves the root cause",
                        "status": "ELIMINATED",
                    },
                ],
            }
        )
        self._agent_run.update({"state": "PLAN_READY", "active_step": "", "confidence": 0.91})

    def events_since(self, after: int = 0) -> list[dict[str, object]]:
        """Expose server-owned activity frames for a Case Console SSE cursor."""

        if after < 0:
            raise ValueError("event sequence cannot be negative")
        with self._lock:
            selected: list[dict[str, object]] = []
            for event in self._events:
                sequence = event.get("sequence")
                if isinstance(sequence, int) and sequence > after:
                    selected.append(dict(event))
            return selected

    def record_strands_investigation(self, advisory: Mapping[str, object]) -> dict[str, object]:
        """Attach a real advisory trace while keeping policy/execution deterministic."""

        with self._lock:
            self._diagnosis["strands_investigation"] = dict(advisory)
            status = self._text(advisory.get("status"), "AGENT_UNAVAILABLE")
            run_id = self._text(self._agent_run.get("run_id"))
            if status != "COMPLETE":
                self._append(
                    "agent.strands.degraded",
                    source_id="agent-platform",
                    provider="Strands",
                    status="DEGRADED",
                    label="Strands investigation unavailable",
                    detail=(
                        "No model conclusion was used; deterministic safety controls "
                        "remain in force."
                    ),
                    record_id=run_id,
                )
            else:
                raw_tool_calls = advisory.get("tool_calls", [])
                tool_calls = raw_tool_calls if isinstance(raw_tool_calls, (list, tuple)) else []
                for tool_name in tool_calls:
                    if not isinstance(tool_name, str):
                        continue
                    self._append(
                        "agent.strands.tool.completed",
                        source_id="agent-platform",
                        provider="Strands",
                        status="COMPLETE",
                        label=f"Strands read {tool_name}",
                        detail="Read-only source tool returned a scoped evidence packet.",
                        record_id=run_id,
                    )
                result = advisory.get("result")
                disposition = (
                    self._text(result.get("disposition")) if isinstance(result, Mapping) else ""
                )
                self._append(
                    "agent.strands.completed",
                    source_id="agent-platform",
                    provider="Strands",
                    status="COMPLETE",
                    label="Strands investigation completed",
                    detail=(
                        f"Read-only advisory returned {disposition}; "
                        "deterministic policy retains authority."
                    ),
                    record_id=run_id,
                )
            erp, saas = self._read_all()
            self._apply_completed_strands_diagnosis(advisory, erp, saas)
            return self._projection(erp, saas)

    def _admit_source_activity(
        self, rows: object, *, metrics: Mapping[str, object] | None = None
    ) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            record = dict(row)
            signature = self._signature(record)
            if signature in self._seen_source_records:
                continue
            self._seen_source_records.add(signature)
            event = self._append(
                "provider.read.observed",
                source_id=self._text(record.get("source_id"), "unknown-source"),
                provider=self._text(record.get("provider"), "Unknown provider"),
                status=self._text(record.get("status"), "UNKNOWN"),
                label=self._text(record.get("label"), "Provider record read"),
                detail=self._text(record.get("detail")),
                record_id=self._text(record.get("record_id")),
            )
            if metrics is not None:
                event["metrics"] = dict(metrics)
                event["source_sequence"] = metrics.get("source_sequence", 0)
                event["change_count"] = 0 if int(metrics.get("source_sequence") or 0) <= 1 else 1
            source_id = self._text(record.get("source_id"))
            self._source_sequences[source_id] = self._sequence
            if source_id.startswith("erp-"):
                self._source_sequences["erpnext-missing20"] = self._sequence

    @staticmethod
    def _documents_by_kind(erp: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        documents = erp.get("documents")
        if not isinstance(documents, list):
            return {}
        return {
            str(document.get("kind")): document
            for document in documents
            if isinstance(document, Mapping) and document.get("kind")
        }

    @classmethod
    def _live_flow_metrics(cls, erp: Mapping[str, object]) -> dict[str, object]:
        """Derive the dashboard state from one ERPNext evidence projection."""

        documents = cls._documents_by_kind(erp)
        po = documents.get("purchase_order", {})
        receipt = documents.get("purchase_receipt", {})
        invoice = documents.get("purchase_invoice", {})
        transfer = documents.get("quality_release_transfer", {})
        sales_order = documents.get("sales_order", {})
        delivery_note = documents.get("delivery_note", {})
        sales_invoice = documents.get("sales_invoice", {})
        accepted = float(receipt.get("accepted") or 0)
        rejected = float(receipt.get("rejected") or 0)
        received = float(receipt.get("received") or accepted + rejected)
        ordered = float(po.get("quantity") or received)
        released = (
            float(transfer.get("quantity") or 0)
            if cls._text(transfer.get("status")).upper() == "SUBMITTED"
            else 0.0
        )
        available = min(received, accepted + released)
        quality_hold = max(0.0, rejected - released)
        unresolved = max(0.0, ordered - received)
        gap = quality_hold + unresolved
        invoice_held = (
            bool(invoice.get("on_hold"))
            or cls._text(invoice.get("status")).upper() == "PAYMENT_HOLD"
        )
        unit_rate = float(po.get("unit_rate") or 0)
        invoice_value = float(invoice.get("grand_total") or po.get("line_value") or 0)
        booked_revenue = float(sales_order.get("booked_value") or 0)
        billed_revenue = (
            float(sales_invoice.get("billed_revenue") or 0)
            if cls._text(sales_invoice.get("status")) == "SUBMITTED"
            else 0.0
        )
        order_open = bool(sales_order) and billed_revenue < booked_revenue
        return {
            "source_sequence": int(erp.get("sequence") or 0),
            "expected": ordered,
            "physically_arrived": received,
            "recorded": available,
            "gap": gap,
            "quality_hold": quality_hold,
            "receipt_unresolved": unresolved,
            "invoice_held": invoice_held,
            "invoice_count": 0.0 if invoice_held else available,
            "working_capital_at_risk": gap * unit_rate,
            "invoice_hold_value": invoice_value if invoice_held else 0.0,
            "purchase_price_variance": 0.0,
            # Kept as a compatibility alias for older chart consumers.  It is
            # now an observed customer billing fact, never a supplier AP value.
            "value_protected": billed_revenue,
            "booked_revenue": booked_revenue,
            "billed_revenue": billed_revenue,
            "revenue_at_risk": booked_revenue if order_open else 0.0,
            "delivered_quantity": float(delivery_note.get("quantity") or 0),
            "customer_order_quantity": float(sales_order.get("quantity") or 0),
            "po_unit_cost": unit_rate,
        }

    @classmethod
    def _case_projection(cls, erp: Mapping[str, object]) -> dict[str, object]:
        metrics = cls._live_flow_metrics(erp)
        documents = cls._documents_by_kind(erp)
        return {
            "provenance": "live-read",
            "read_only": True,
            "source_sequence": metrics["source_sequence"],
            "case": {
                "case_id": cls._text(erp.get("case_id"), "M20-ERP-LIVE"),
                "quantities": {
                    "ordered": metrics["expected"],
                    "physically_arrived": metrics["physically_arrived"],
                    "available": metrics["recorded"],
                    "quality_hold": metrics["quality_hold"],
                    "receipt_unresolved": metrics["receipt_unresolved"],
                },
                "invoice_held": metrics["invoice_held"],
                "purchase_order": cls._text(documents.get("purchase_order", {}).get("name")),
                "purchase_receipt": cls._text(documents.get("purchase_receipt", {}).get("name")),
                "purchase_invoice": cls._text(documents.get("purchase_invoice", {}).get("name")),
                "quality_release_transfer": cls._text(
                    documents.get("quality_release_transfer", {}).get("name")
                ),
                "sales_order": cls._text(documents.get("sales_order", {}).get("name")),
                "delivery_note": cls._text(documents.get("delivery_note", {}).get("name")),
                "sales_invoice": cls._text(documents.get("sales_invoice", {}).get("name")),
            },
        }

    @classmethod
    def _business_impact(cls, erp: Mapping[str, object]) -> dict[str, object]:
        metrics = cls._live_flow_metrics(erp)
        documents = cls._documents_by_kind(erp)
        po = documents.get("purchase_order", {})
        invoice = documents.get("purchase_invoice", {})
        sales_order = documents.get("sales_order", {})
        sales_invoice = documents.get("sales_invoice", {})
        expected = float(metrics["expected"] or 0)
        arrived = float(metrics["physically_arrived"] or 0)
        recorded = float(metrics["recorded"] or 0)
        unit_rate = float(metrics["po_unit_cost"] or 0)
        po_value = float(po.get("line_value") or expected * unit_rate)
        invoice_value = float(invoice.get("grand_total") or po_value)
        invoice_unit = invoice_value / expected if expected else 0.0
        booked_revenue = float(sales_order.get("booked_value") or 0)
        billed_revenue = (
            float(sales_invoice.get("billed_revenue") or 0)
            if cls._text(sales_invoice.get("status")) == "SUBMITTED"
            else 0.0
        )
        order_open = bool(sales_order) and float(sales_order.get("billed_percent") or 0) < 100
        return {
            "provenance": "ERPNext / Frappe Cloud live read",
            "source_sequence": metrics["source_sequence"],
            "currency": cls._text(po.get("currency") or invoice.get("currency"), "USD"),
            "inventory_availability_percent": (recorded / expected * 100) if expected else 0.0,
            "erp_reconciliation_percent": (recorded / arrived * 100) if arrived else 0.0,
            "working_capital_at_risk": metrics["working_capital_at_risk"],
            "invoice_hold_value": metrics["invoice_hold_value"],
            "quality_hold_value": float(metrics["quality_hold"]) * unit_rate,
            "receipt_gap_value": float(metrics["receipt_unresolved"]) * unit_rate,
            "receipt_gap_percent": (float(metrics["gap"]) / expected * 100) if expected else 0.0,
            "quality_hold_percent": (
                float(metrics["quality_hold"]) / expected * 100 if expected else 0.0
            ),
            "available_inventory_value": recorded * unit_rate,
            "value_protected": billed_revenue,
            "value_protected_classification": (
                "OBSERVED_BILLED_REVENUE" if billed_revenue else "NOT_REALIZED"
            ),
            "booked_revenue": booked_revenue,
            "billed_revenue": billed_revenue,
            "revenue_at_risk": booked_revenue if order_open else 0.0,
            "po_line_value": po_value,
            "po_unit_cost": unit_rate,
            "invoice_value": invoice_value,
            "invoice_unit_price": invoice_unit,
            "purchase_price_variance": invoice_value - po_value,
            "invoice_price_delta_percent": (
                (invoice_value - po_value) / po_value * 100 if po_value else 0.0
            ),
            "supplier_delivery_completion_percent": (arrived / expected * 100 if expected else 0.0),
            "supplier_status": "ACTIVE",
            "supplier_payment_hold": bool(metrics["invoice_held"]),
            "invoice_status": "PAYMENT HOLD" if metrics["invoice_held"] else "OPEN",
        }

    @classmethod
    def _value_proof(cls, erp: Mapping[str, object]) -> dict[str, object]:
        """Separate observed financial facts from estimates and counterfactuals."""

        documents = cls._documents_by_kind(erp)
        purchase_order = documents.get("purchase_order", {})
        sales_order = documents.get("sales_order", {})
        delivery_note = documents.get("delivery_note", {})
        sales_invoice = documents.get("sales_invoice", {})
        booked = float(sales_order.get("booked_value") or 0)
        billed = (
            float(sales_invoice.get("billed_revenue") or 0)
            if cls._text(sales_invoice.get("status")) == "SUBMITTED"
            else 0.0
        )
        purchase_basis = float(purchase_order.get("line_value") or 0)
        order_status = cls._text(sales_order.get("status"), "NOT_CONFIGURED")
        delivered = cls._text(delivery_note.get("status")) == "SUBMITTED"
        invoice_posted = bool(billed and cls._text(sales_invoice.get("status")) == "SUBMITTED")
        closed_loop_verified = delivered and invoice_posted
        stage = (
            "BILLED_VERIFIED"
            if closed_loop_verified
            else "INVOICE_POSTED_AWAITING_DELIVERY_EVIDENCE"
            if invoice_posted
            else "DELIVERED"
            if delivered
            else "ORDER_HELD"
            if order_status == "On Hold"
            else "ORDER_OPEN"
            if sales_order
            else "NOT_CONFIGURED"
        )
        return {
            "provenance": "ERPNext / Frappe Cloud live reread",
            "status": stage,
            "currency": cls._text(
                sales_invoice.get("currency") or sales_order.get("currency"), "USD"
            ),
            "observed": {
                "booked_revenue": booked,
                "billed_revenue": billed,
                "delivered_quantity": float(delivery_note.get("quantity") or 0),
                "order_quantity": float(sales_order.get("quantity") or 0),
                "purchase_cost_basis": purchase_basis,
                "gross_spread": max(0.0, billed - purchase_basis) if invoice_posted else 0.0,
            },
            "estimated": {
                "gross_spread_note": (
                    "Sales invoice less scoped purchase-order value; excludes labor, "
                    "freight, tax, and overhead."
                    if invoice_posted
                    else "Not calculated until customer billing is verified."
                )
            },
            "counterfactual": {
                "revenue_at_risk_if_hold_persists": booked if not closed_loop_verified else 0.0,
                "classification": "COUNTERFACTUAL_NOT_OBSERVED",
            },
            "documents": {
                "sales_order": cls._text(sales_order.get("name")),
                "delivery_note": cls._text(delivery_note.get("name")),
                "sales_invoice": cls._text(sales_invoice.get("name")),
            },
            "assertions": {
                "customer_order_observed": bool(sales_order),
                "delivery_posted": delivered,
                "customer_invoice_posted": invoice_posted,
                "billed_revenue_is_observed": invoice_posted,
                "order_to_cash_closed_loop_verified": closed_loop_verified,
                "causal_revenue_increase_proven": False,
            },
        }

    @classmethod
    def _value_pending(cls, erp: Mapping[str, object]) -> bool:
        proof = cls._value_proof(erp)
        return cls._text(proof.get("status")) in {
            "ORDER_HELD",
            "ORDER_OPEN",
            "DELIVERED",
            "INVOICE_POSTED_AWAITING_DELIVERY_EVIDENCE",
        }

    @staticmethod
    def _source_rows(saas: Mapping[str, object]) -> list[Mapping[str, object]]:
        raw_rows = saas.get("sources")
        if not isinstance(raw_rows, list):
            return []
        return [cast(Mapping[str, object], row) for row in raw_rows if isinstance(row, Mapping)]

    @staticmethod
    def _source_by_id(saas: Mapping[str, object], source_id: str) -> Mapping[str, object] | None:
        return next(
            (row for row in AgentPlatform._source_rows(saas) if row.get("source_id") == source_id),
            None,
        )

    @staticmethod
    def _correlation_values(row: Mapping[str, object] | None) -> dict[str, object]:
        raw = row.get("correlation") if row else None
        return dict(raw) if isinstance(raw, Mapping) else {}

    @staticmethod
    def _matches(left: object, right: object) -> bool:
        """Compare display-safe scalar correlation values without coercing blanks."""

        if left is None or right is None:
            return False
        if isinstance(left, bool) or isinstance(right, bool):
            return left is right
        try:
            return float(str(left)) == float(str(right))
        except (TypeError, ValueError):
            return " ".join(str(left).split()) == " ".join(str(right).split())

    @staticmethod
    def _missing(value: object) -> bool:
        return value is None or not str(value).strip() or str(value).startswith("UNAVAILABLE")

    def _systems(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> list[dict[str, object]]:
        erp_status = self._text(erp.get("status"), "NOT_CONFIGURED")
        saas_rows = self._source_rows(saas)
        by_source = {self._text(row.get("source_id")): row for row in saas_rows}

        def system(
            system_id: str,
            name: str,
            source: Mapping[str, object] | None,
            authority: str,
        ) -> dict[str, object]:
            row = source or {}
            return {
                "id": system_id,
                "name": name,
                "status": self._text(row.get("status"), "NOT_CONFIGURED"),
                "authority": authority,
                "label": self._text(row.get("label"), "Read unavailable"),
                "detail": self._text(row.get("detail"), "Observer read has not been configured."),
                "record_id": self._text(row.get("record_id")),
                "read_only": True,
                "write_state": "DISABLED",
            }

        erp_row: Mapping[str, object] = {
            "status": erp_status,
            "label": "ERP evidence read",
            "detail": (
                "Purchase order, receipt, and invoice read together."
                if erp_status == "CONNECTED"
                else "ERPNext observer read is unavailable."
            ),
            "record_id": "erpnext-missing20",
        }
        systems = [
            system("erpnext", "ERPNext", erp_row, "Authoritative operational evidence"),
            system(
                "airtable",
                "Airtable",
                by_source.get("airtable-quality-registry"),
                "Release registry evidence; partial until tuple matches",
            ),
            system(
                "jira",
                "Jira",
                by_source.get("jira-capa"),
                "Journal only; cannot prove a release",
            ),
            system(
                "celigo",
                "Celigo",
                by_source.get("celigo-quality-release"),
                "Post-execution run receipt; cannot authorize an ERP release",
            ),
            system(
                "slack",
                "Slack",
                by_source.get("slack-quality-alerts"),
                "Journal only; cannot prove a release",
            ),
        ]
        if self._executor is not None:
            systems[0].update(
                {
                    "read_only": False,
                    "write_state": "MANAGER_GATED",
                    "authority": (
                        "Authoritative operational evidence and guarded business effects"
                    ),
                }
            )
        return systems

    def _correlation(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        docs = self._documents_by_kind(erp)
        po = docs.get("purchase_order", {})
        receipt = docs.get("purchase_receipt", {})
        invoice = docs.get("purchase_invoice", {})
        correlation_id = self._text(saas.get("correlation_id"), "UNCONFIGURED")
        registry = self._source_by_id(saas, "airtable-quality-registry")
        registry_values = (
            self._correlation_values(registry)
            if registry and self._text(registry.get("status")) == "VERIFIED"
            else {}
        )
        expected = {
            "case_id": correlation_id,
            "purchase_order": self._text(po.get("name")),
            "purchase_receipt": self._text(receipt.get("name")),
            "purchase_invoice": self._text(invoice.get("name")),
            "quantity": receipt.get("rejected", "UNAVAILABLE_FROM_READS"),
        }
        tuple_values = {
            "case_id": correlation_id,
            "purchase_order": expected["purchase_order"],
            "purchase_receipt": expected["purchase_receipt"],
            "purchase_invoice": expected["purchase_invoice"],
            "supplier_lot": registry_values.get("supplier_lot", "UNAVAILABLE_FROM_READS"),
            "certificate_id": registry_values.get("certificate_id", "UNAVAILABLE_FROM_READS"),
            "quantity": expected["quantity"],
            "evidence_revision": registry_values.get("evidence_revision", "UNAVAILABLE_FROM_READS"),
        }
        compared = ("case_id", "purchase_order", "purchase_receipt", "purchase_invoice", "quantity")
        missing = [key for key, value in tuple_values.items() if self._missing(value)]
        missing.extend(
            key
            for key in compared
            if self._missing(registry_values.get(key)) and key not in missing
        )
        mismatched = [
            key
            for key in compared
            if registry_values.get(key) is not None
            and expected.get(key) is not None
            and not self._matches(registry_values.get(key), expected.get(key))
        ]
        status = (
            "MISMATCHED_CORRELATION"
            if mismatched
            else ("PARTIAL_CORRELATION" if missing else "FULLY_CORRELATED")
        )
        return {
            "status": status,
            "tuple": tuple_values,
            "missing_fields": missing,
            "mismatched_fields": mismatched,
            "registry_tuple": registry_values,
            "release_eligibility": (
                "DEMO_GUARDED" if self._executor is not None else "WRITE_DISABLED"
            )
            if status == "FULLY_CORRELATED"
            else "NOT_EVALUABLE_READ_ONLY",
        }

    def _integration_receipt(
        self, saas: Mapping[str, object], correlation: Mapping[str, object]
    ) -> dict[str, object]:
        """Accept only an acknowledged, tuple-matched Celigo run receipt."""

        receipt = self._source_by_id(saas, "celigo-quality-release")
        if receipt is None:
            return {"status": "MISSING", "record_id": "", "mismatched_fields": []}
        evidence_kind = self._text(receipt.get("evidence_kind"))
        if evidence_kind == "RUN_RECEIPT_PENDING":
            return {
                "status": "PENDING",
                "record_id": self._text(receipt.get("record_id")),
                "mismatched_fields": [],
            }
        if evidence_kind != "RUN_RECEIPT":
            return {
                "status": "CONTROL_PLANE_ONLY",
                "record_id": self._text(receipt.get("record_id")),
                "mismatched_fields": [],
            }
        if (
            self._text(receipt.get("status")) != "VERIFIED"
            or receipt.get("erp_acknowledged") is not True
        ):
            return {
                "status": "FAILED",
                "record_id": self._text(receipt.get("record_id")),
                "mismatched_fields": [],
            }
        if self._text(correlation.get("status")) != "FULLY_CORRELATED":
            return {
                "status": "BLOCKED",
                "record_id": self._text(receipt.get("record_id")),
                "mismatched_fields": [],
            }
        expected = correlation.get("registry_tuple")
        expected_values = dict(expected) if isinstance(expected, Mapping) else {}
        received_values = self._correlation_values(receipt)
        required = (
            "case_id",
            "purchase_order",
            "purchase_receipt",
            "purchase_invoice",
            "supplier_lot",
            "certificate_id",
            "quantity",
            "evidence_revision",
        )
        missing = [key for key in required if self._missing(received_values.get(key))]
        mismatched = [
            key
            for key in required
            if key not in missing
            and not self._matches(received_values.get(key), expected_values.get(key))
        ]
        status = "VERIFIED" if not missing and not mismatched else "MISMATCHED_RECEIPT"
        return {
            "status": status,
            "record_id": self._text(receipt.get("record_id")),
            "missing_fields": missing,
            "mismatched_fields": mismatched,
        }

    def _external_recovery_verified(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> bool:
        """Prove a previous recovery from fresh provider reads after a server restart."""

        documents = self._documents_by_kind(erp)
        receipt = documents.get("purchase_receipt", {})
        invoice = documents.get("purchase_invoice", {})
        transfer = documents.get("quality_release_transfer", {})
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        return (
            self._text(receipt.get("status"))
            in {"PARTIAL_QUALITY_HOLD", "RELEASED_AFTER_QUALITY_HOLD"}
            and self._text(invoice.get("status")) == "OPEN"
            and self._text(transfer.get("status")) == "SUBMITTED"
            and self._matches(transfer.get("quantity"), receipt.get("rejected"))
            and self._text(correlation.get("status")) == "FULLY_CORRELATED"
            and self._text(integration_receipt.get("status")) == "VERIFIED"
        )

    def _human_review(
        self,
        correlation: Mapping[str, object],
        integration_receipt: Mapping[str, object],
        external_recovery: bool,
    ) -> dict[str, object]:
        """Describe the next human decision without granting the advisory authority."""

        run_state = self._text(self._agent_run.get("state"), "IDLE")
        execution_state = self._text(self._execution.get("status"))
        if external_recovery or execution_state == "VERIFIED":
            return {
                "status": "COMPLETE",
                "required": False,
                "action": "NONE",
                "reason": "Recovery is independently verified by fresh source reads.",
                "can_stop": False,
            }
        if run_state == "IDLE":
            return {
                "status": "HUMAN_START_REQUIRED",
                "required": True,
                "action": "START_INVESTIGATION",
                "reason": "A person must start this case; no background diagnosis has been run.",
                "can_stop": True,
            }
        if run_state == "STOPPED":
            return {
                "status": "PAUSED_BY_HUMAN",
                "required": True,
                "action": "RESUME_INVESTIGATION",
                "reason": (
                    "The operator paused this case. Existing evidence remains available for review."
                ),
                "can_stop": False,
            }
        if run_state == "BLOCKED":
            return {
                "status": "NEEDS_EVIDENCE",
                "required": True,
                "action": "RESUME_AFTER_EVIDENCE",
                "reason": self._text(
                    self._diagnosis.get("summary"),
                    "Evidence is incomplete or inconsistent; recovery is stopped safely.",
                ),
                "can_stop": True,
            }
        if run_state == "PLAN_READY" and not self._approval:
            return {
                "status": "MANAGER_REVIEW_REQUIRED",
                "required": True,
                "action": "APPROVE_GUARDED_PLAN",
                "reason": (
                    "The evidence tuple is complete; only a Manager can authorize "
                    "the bounded recovery."
                ),
                "can_stop": True,
            }
        if self._approval and not self._execution:
            return {
                "status": "HUMAN_EXECUTION_REQUIRED",
                "required": True,
                "action": "EXECUTE_GUARDED_PLAN",
                "reason": (
                    "Manager approval is recorded; a person must explicitly start "
                    "the guarded effect."
                ),
                "can_stop": True,
            }
        if execution_state == "VERIFYING":
            return {
                "status": "WAITING_FOR_INDEPENDENT_RECEIPT",
                "required": False,
                "action": "VERIFY_REREAD",
                "reason": (
                    "The effect completed; the Agent is waiting for the independent "
                    "integration reread."
                ),
                "can_stop": True,
            }
        return {
            "status": "AGENT_READING",
            "required": False,
            "action": "NONE",
            "reason": "The Agent may perform its bounded, read-only investigation.",
            "can_stop": True,
        }

    def _resolution_packet_projection(
        self,
        erp: Mapping[str, object],
        saas: Mapping[str, object],
        correlation: Mapping[str, object],
        integration_receipt: Mapping[str, object],
        external_recovery: bool,
    ) -> dict[str, object] | None:
        """Create an inspectable business outcome only after verified recovery."""

        verified = external_recovery or self._text(self._execution.get("status")) == "VERIFIED"
        if not verified:
            return None
        documents = self._documents_by_kind(erp)
        receipt = documents.get("purchase_receipt", {})
        invoice = documents.get("purchase_invoice", {})
        transfer = documents.get("quality_release_transfer", {})
        sales_order = documents.get("sales_order", {})
        delivery_note = documents.get("delivery_note", {})
        sales_invoice = documents.get("sales_invoice", {})
        tuple_values = correlation.get("tuple")
        safe_tuple = dict(tuple_values) if isinstance(tuple_values, Mapping) else {}
        # A missing receipt-post quantity is materially different from an
        # unknown quantity.  This live recovery only releases the existing
        # quality transfer/invoice hold; it must not imply another receipt.
        safe_tuple["receipt_post_quantity"] = float(
            self._execution.get("receipt_post_quantity") or 0
        )
        safe_tuple["quality_transfer_quantity"] = self._execution.get(
            "approved_quantity", transfer.get("quantity", 0)
        )
        evidence = [
            {
                "source_id": "erpnext-missing20",
                "provider": "ERPNext",
                "record_id": self._text(receipt.get("name")),
            },
            *[
                {
                    "source_id": self._text(row.get("source_id")),
                    "provider": self._text(row.get("provider")),
                    "record_id": self._text(row.get("record_id")),
                }
                for row in self._source_rows(saas)
            ],
        ]
        packet_basis = {
            "tuple": safe_tuple,
            "approval_id": self._text(self._approval.get("approval_id")),
            "transfer": self._text(transfer.get("name")),
            "receipt": self._text(receipt.get("name")),
            "invoice": self._text(invoice.get("name")),
            "celigo_receipt": self._text(integration_receipt.get("record_id")),
            "sales_order": self._text(sales_order.get("name")),
            "delivery_note": self._text(delivery_note.get("name")),
            "sales_invoice": self._text(sales_invoice.get("name")),
        }
        packet_id = (
            "resolution-"
            + hashlib.sha256(
                json.dumps(packet_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:12]
        )
        live_provider = self._text(erp.get("provider")).startswith("ERPNext / Frappe Cloud")
        packet_provenance = (
            "live-provider-write"
            if live_provider and self._execution
            else ("live-provider-reread" if live_provider else "synthetic-demo")
        )
        raw_pre_state = self._execution.get("pre_state")
        pre_state = dict(raw_pre_state) if isinstance(raw_pre_state, Mapping) else {}
        pre_state.setdefault("available", self._live_flow_metrics(erp)["recorded"])
        return {
            "packet_id": packet_id,
            "status": "VERIFIED",
            "provenance": packet_provenance,
            "case_tuple": safe_tuple,
            "finding": self._text(
                self._diagnosis.get("finding"),
                "RECOVERY_VERIFIED_FROM_LIVE_READS" if external_recovery else "NOT_EVALUATED",
            ),
            "policy": {
                "status": self._text(
                    self._diagnosis.get("status"), "VERIFIED" if external_recovery else ""
                ),
                "finding": self._text(
                    self._diagnosis.get("finding"),
                    "RECOVERY_VERIFIED_FROM_LIVE_READS" if external_recovery else "NOT_EVALUATED",
                ),
                "authority": "DETERMINISTIC_CONTROL_PLANE",
            },
            "agent_trace": (
                dict(trace)
                if isinstance((trace := self._diagnosis.get("strands_investigation")), Mapping)
                else {}
            ),
            "guard": (
                "MANAGER_APPROVED_GUARDED_RECOVERY"
                if self._approval
                else "PRIOR_GUARDED_RECOVERY_VERIFIED_BY_REREAD"
            ),
            "approval": dict(self._approval),
            "execution": {
                "status": self._execution.get("status")
                or ("VERIFIED" if external_recovery else None),
                "idempotency_key": self._execution.get("idempotency_key"),
                "approval_id": self._execution.get("approval_id")
                or self._approval.get("approval_id"),
            },
            "effects": {
                "quality_release_transfer": self._text(transfer.get("name")),
                "invoice": self._text(invoice.get("name")),
                "celigo_receipt": self._text(integration_receipt.get("record_id")),
                "sales_order": self._text(
                    sales_order.get("name") or self._execution.get("sales_order")
                ),
                "delivery_note": self._text(
                    delivery_note.get("name") or self._execution.get("delivery_note")
                ),
                "sales_invoice": self._text(
                    sales_invoice.get("name") or self._execution.get("sales_invoice")
                ),
            },
            "pre_state": pre_state,
            "post_state": {
                "receipt_status": self._text(receipt.get("status")),
                "invoice_status": self._text(invoice.get("status")),
                "integration_receipt_status": self._text(integration_receipt.get("status")),
                "available": self._live_flow_metrics(erp)["recorded"],
                "customer_order_status": self._text(sales_order.get("status")),
                "customer_billed_revenue": float(sales_invoice.get("billed_revenue") or 0),
            },
            "evidence": evidence,
            "timestamps": {
                "approved_at": self._approval.get("approved_at"),
                "executed_at": self._execution.get("executed_at"),
                "verified_at": self._execution.get("verified_at"),
            },
        }

    @classmethod
    def _evidence_catalog(
        cls, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, dict[str, object]]:
        """Project provider evidence into citation drawers without weakening provenance."""

        documents = cls._documents_by_kind(erp)
        observed_at = cls._text(erp.get("received_at") or erp.get("changed_at"))
        catalog: dict[str, dict[str, object]] = {}
        for document in documents.values():
            record_id = cls._text(document.get("name"))
            if not record_id:
                continue
            stable = json.dumps(dict(document), sort_keys=True, separators=(",", ":"))
            catalog[record_id] = {
                "evidence_id": record_id,
                "provider": "ERPNext / Frappe Cloud",
                "summary": (
                    f"Authoritative ERPNext {cls._text(document.get('kind')).replace('_', ' ')} "
                    f"is {cls._text(document.get('status'), 'observed')}."
                ),
                "revision": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16],
                "observed_at": observed_at,
                "provenance": "live-provider-read",
                "fields": [
                    {"label": key.replace("_", " "), "value": value}
                    for key, value in document.items()
                    if key not in {"kind", "name"}
                ],
            }

        raw_ledger = erp.get("ledger_evidence")
        ledger = dict(raw_ledger) if isinstance(raw_ledger, Mapping) else {}
        receipt_id = cls._text(documents.get("purchase_receipt", {}).get("name"))
        if receipt_id and cls._text(ledger.get("status")) == "CONNECTED":
            stock = [
                dict(row) for row in ledger.get("stock_entries", []) if isinstance(row, Mapping)
            ]
            gl = [
                dict(row)
                for row in ledger.get("general_ledger_entries", [])
                if isinstance(row, Mapping)
            ]
            totals = dict(ledger.get("totals")) if isinstance(ledger.get("totals"), Mapping) else {}
            assertions = (
                dict(ledger.get("assertions"))
                if isinstance(ledger.get("assertions"), Mapping)
                else {}
            )
            stable_ledger = json.dumps(
                {"stock": stock, "general_ledger": gl, "totals": totals},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            balanced = assertions.get("debits_equal_credits") is True
            catalog[f"{receipt_id}:ledger"] = {
                "evidence_id": f"{receipt_id}:ledger",
                "provider": "ERPNext / Frappe Cloud",
                "summary": (
                    f"{len(stock)} Stock Ledger rows and {len(gl)} GL rows were freshly read. "
                    f"Debit {float(totals.get('debit') or 0):,.2f} equals credit "
                    f"{float(totals.get('credit') or 0):,.2f}; "
                    f"balance assertion {'VERIFIED' if balanced else 'FAILED'}."
                ),
                "revision": hashlib.sha256(stable_ledger.encode("utf-8")).hexdigest()[:16],
                "observed_at": observed_at,
                "provenance": "live-provider-read",
                "assertions": assertions,
                "totals": totals,
                "stock_entries": stock,
                "general_ledger_entries": gl,
            }

        for row in cls._source_rows(saas):
            record_id = cls._text(row.get("record_id"))
            if not record_id:
                continue
            stable = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str)
            catalog[record_id] = {
                "evidence_id": record_id,
                "provider": cls._text(row.get("provider"), "Connected SaaS"),
                "summary": cls._text(row.get("detail"), cls._text(row.get("label"))),
                "revision": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16],
                "observed_at": cls._text(row.get("occurred_at") or saas.get("received_at")),
                "provenance": "live-provider-read",
                "fields": [
                    {"label": "status", "value": row.get("status")},
                    {"label": "source", "value": row.get("source_id")},
                ],
            }
        return catalog

    def _issue_resolution_packet(
        self,
        erp: Mapping[str, object],
        saas: Mapping[str, object],
        correlation: Mapping[str, object],
        integration_receipt: Mapping[str, object],
    ) -> None:
        packet = self._resolution_packet_projection(
            erp, saas, correlation, integration_receipt, external_recovery=False
        )
        if packet is None or self._resolution_packet:
            return
        self._resolution_packet = packet
        self._append(
            "agent.resolution_packet.issued",
            source_id="agent-platform",
            provider="Missing 20 Agent",
            status="VERIFIED",
            label="Resolution packet issued",
            detail=(
                "Verified live provider recovery is bound to its evidence, approval, and reread."
                if self._text(packet.get("provenance")).startswith("live-provider")
                else "Verified synthetic recovery is bound to its evidence, approval, and reread."
            ),
            provenance=self._text(packet.get("provenance"), "synthetic-demo"),
            record_id=self._text(packet.get("packet_id")),
            read_only=False,
        )

    def _plan(self, erp: Mapping[str, object], saas: Mapping[str, object]) -> list[dict[str, str]]:
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        external_recovery = self._external_recovery_verified(erp, saas)
        value_proof = self._value_proof(erp)
        value_pending = self._value_pending(erp)
        erp_ready = self._text(erp.get("status")) == "CONNECTED"
        saas_ready = self._text(saas.get("status")) == "CONNECTED"
        complete = self._text(self._agent_run.get("state")) in {
            "PLAN_READY",
            "BLOCKED",
            "VERIFYING",
            "VERIFIED",
        } or (external_recovery and not value_pending)
        plan = [
            {
                "id": "read_erp",
                "label": "Read ERP receipt + invoice",
                "status": "DONE" if erp_ready else "BLOCKED",
            },
            {
                "id": "correlate_registry",
                "label": "Correlate release registry",
                "status": "DONE" if saas_ready else "BLOCKED",
            },
            {
                "id": "validate_run",
                "label": "Validate integration receipt",
                "status": (
                    "DONE"
                    if integration_receipt["status"] == "VERIFIED"
                    else (
                        "WAITING"
                        if self._execution
                        and self._text(self._execution.get("status")) == "VERIFYING"
                        else ("QUEUED" if not complete else "NOT_REQUIRED_YET")
                    )
                ),
            },
            {
                "id": "guarded_plan",
                "label": "Produce guarded recovery plan",
                "status": (
                    "DONE"
                    if external_recovery
                    and not value_pending
                    or self._text(self._agent_run.get("state"))
                    in {"PLAN_READY", "VERIFYING", "VERIFIED"}
                    else ("BLOCKED" if complete else "QUEUED")
                ),
            },
        ]
        if self._text(value_proof.get("status")) != "NOT_CONFIGURED":
            plan.extend(
                [
                    {
                        "id": "read_customer_order",
                        "label": "Read customer order",
                        "status": "DONE",
                    },
                    {
                        "id": "verify_customer_value",
                        "label": "Verify delivery + billing",
                        "status": (
                            "DONE"
                            if self._text(value_proof.get("status")) == "BILLED_VERIFIED"
                            else "QUEUED"
                            if value_pending
                            else "BLOCKED"
                        ),
                    },
                ]
            )
        return plan

    def _constellation(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        systems = {system["id"]: system for system in self._systems(erp, saas)}
        live_metrics = self._live_flow_metrics(erp)
        node_specs = (
            ("erpnext", "TOP", "OPERATIONAL"),
            ("airtable", "RIGHT", "REGISTRY"),
            ("celigo", "BOTTOM", "RUN RECEIPT"),
            ("jira", "LEFT", "WORKFLOW"),
            ("slack", "LEFT", "COLLABORATION"),
        )
        nodes: list[dict[str, object]] = []
        for node_id, position, role in node_specs:
            system = systems.get(node_id, {})
            status = self._text(system.get("status"), "NOT_CONFIGURED")
            label = self._text(system.get("name"), node_id)
            sequence = self._source_sequences.get(
                {
                    "erpnext": "erpnext-missing20",
                    "airtable": "airtable-quality-registry",
                    "celigo": "celigo-quality-release",
                    "jira": "jira-capa",
                    "slack": "slack-quality-alerts",
                }[node_id],
                0,
            )
            if node_id == "erpnext" and float(live_metrics["quality_hold"] or 0) > 0:
                status = "HOLD"
            elif node_id == "erpnext" and bool(live_metrics["invoice_held"]):
                status = "INVOICE_HOLD"
            if node_id == "airtable" and correlation["status"] != "FULLY_CORRELATED":
                status = "PARTIAL"
            if node_id == "celigo":
                status = self._text(integration_receipt.get("status"), "BLOCKED")
            nodes.append(
                {
                    "id": node_id,
                    "position": position,
                    "role": role,
                    "label": label,
                    "status": status,
                    "latest_sequence": sequence,
                }
            )
        hold_detected = float(live_metrics["quality_hold"] or 0) > 0
        attention_detected = hold_detected or bool(live_metrics["invoice_held"])
        eligible = correlation["status"] == "FULLY_CORRELATED"
        verified = eligible and integration_receipt["status"] == "VERIFIED"
        confidence = (
            0.91
            if attention_detected and verified
            else (0.82 if attention_detected and eligible else 0.0)
        )
        external_recovery = self._external_recovery_verified(erp, saas)
        if external_recovery:
            for node in nodes:
                if node["id"] == "erpnext":
                    node["status"] = "VERIFIED"
        recovery_verified = (
            self._text(self._execution.get("status")) == "VERIFIED" or external_recovery
        )
        conclusion_status = (
            "VERIFIED"
            if recovery_verified
            else ("BLOCKED" if not eligible else ("GUARDED" if hold_detected else "CLEAR"))
        )
        return {
            "nodes": nodes,
            "conclusion": {
                "label": (
                    "RECOVERY VERIFIED"
                    if conclusion_status == "VERIFIED"
                    else ("NO RELEASE" if conclusion_status == "BLOCKED" else "GUARDED PLAN")
                ),
                "status": conclusion_status,
                "confidence": confidence,
                "latest_sequence": self._sequence,
            },
            "integration_receipt": integration_receipt,
        }

    def _read_all(self) -> tuple[dict[str, object], dict[str, object]]:
        erp = self._erpnext.current()
        saas = self._saas.current()
        self._admit_source_activity(erp.get("activity"), metrics=self._live_flow_metrics(erp))
        self._admit_source_activity(saas.get("activity"))
        return erp, saas

    def _projection(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        external_recovery = self._external_recovery_verified(erp, saas)
        value_pending = self._value_pending(erp)
        agent_run = dict(self._agent_run)
        diagnosis = dict(self._diagnosis)
        if external_recovery and not value_pending and self._text(agent_run.get("state")) == "IDLE":
            documents = self._documents_by_kind(erp)
            transfer = documents.get("quality_release_transfer", {})
            agent_run.update({"state": "VERIFIED", "confidence": 0.96})
            diagnosis.update(
                {
                    "status": "VERIFIED",
                    "finding": "RECOVERY_VERIFIED_FROM_LIVE_READS",
                    "summary": (
                        "Fresh ERPNext reads prove the prior quality release "
                        f"{self._text(transfer.get('name'), 'transfer')} is submitted; "
                        "the invoice is "
                        "open and the tuple-matched Celigo receipt is verified."
                    ),
                    "tool_calls": [
                        {"tool": "erpnext.read_quality_release_transfer", "status": "VERIFIED"},
                        {"tool": "celigo.read_exact_run_receipt", "status": "VERIFIED"},
                    ],
                }
            )
        live_case = self._case_projection(erp)
        strands = self._mapping(diagnosis.get("strands_investigation"))
        runtime_events = strands.get("runtime_events")
        tool_calls = strands.get("tool_calls")
        evidence_ids = self._evidence_ids(strands)
        source_checks = len(
            set(tool_calls)
            if isinstance(tool_calls, (list, tuple))
            else {self._text(call.get("tool")) for call in self._current_tool_calls()}
        )
        current_resolution_packet = self._resolution_packet_projection(
            erp, saas, correlation, integration_receipt, external_recovery and not value_pending
        )
        return {
            "schema_version": AGENT_PLATFORM_SCHEMA_VERSION,
            "received_at": self._now(),
            "mode": {
                "read_only": self._executor is None,
                "provider_writes": "DEMO_GUARDED" if self._executor else "DISABLED",
                "execution_available": self._executor is not None,
                "provenance": "live-read",
            },
            "case_id": self._text(erp.get("case_id"), "M20-ERP-LIVE"),
            "case_projection": live_case,
            # Compatibility alias for the current browser; provenance remains
            # explicitly live and never claims a synthetic fixture is authoritative.
            "demo_case": live_case,
            "business_impact": self._business_impact(erp),
            "value_proof": self._value_proof(erp),
            "correlation": correlation,
            "integration_receipt": integration_receipt,
            "systems": self._systems(erp, saas),
            "agent_run": agent_run,
            "plan": self._plan(erp, saas),
            "evidence_constellation": self._constellation(erp, saas),
            "evidence_catalog": self._evidence_catalog(erp, saas),
            "diagnosis": diagnosis,
            "judge_proof": {
                "evidence_records": len(evidence_ids),
                "source_checks": source_checks,
                "ledger_events": self._sequence,
                "runtime": self._text(strands.get("mode"), "Strands SDK"),
                "provider": dict(self._mapping(strands.get("provider"))),
                "verified": self._text(self._execution.get("status")) == "VERIFIED",
                "sdk_hook_events": (len(runtime_events) if isinstance(runtime_events, list) else 0),
            },
            "execution": self._execution_projection(erp, saas),
            "human_review": self._human_review(
                correlation, integration_receipt, external_recovery and not value_pending
            ),
            "resolution_packet": (
                current_resolution_packet
                if current_resolution_packet is not None
                else (dict(self._resolution_packet) if self._resolution_packet else None)
            ),
            "activity": list(self._events[-80:]),
            "conversation": [
                self._validate_stored_conversation_turn(dict(turn)) for turn in self._conversation
            ],
            "latest_sequence": self._sequence,
        }

    def _execution_projection(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        if (
            not self._execution
            and self._external_recovery_verified(erp, saas)
            and not self._value_pending(erp)
        ):
            documents = self._documents_by_kind(erp)
            transfer = documents.get("quality_release_transfer", {})
            invoice = documents.get("purchase_invoice", {})
            return {
                "available": False,
                "status": "VERIFIED",
                "detail": "Fresh ERPNext and Celigo reads verify the prior guarded recovery.",
                "transfer_name": self._text(transfer.get("name")),
                "invoice_name": self._text(invoice.get("name")),
                "external_proof": True,
            }
        if self._executor is None:
            return {
                "available": False,
                "status": "WRITE_DISABLED",
                "detail": (
                    "External provider mutations are intentionally disabled in this demo build."
                ),
            }
        if self._execution:
            return dict(self._execution)
        if self._approval:
            return {
                "available": True,
                "status": "AUTHORIZED",
                "detail": "Manager approval is bound to the current guarded plan.",
                **self._approval,
            }
        return {
            "available": self._text(self._agent_run.get("state")) == "PLAN_READY",
            "status": "AWAITING_MANAGER_APPROVAL",
            "detail": "Demo-only execution requires Manager approval after a verified plan.",
        }

    def approve(self, manager_id: str) -> dict[str, object]:
        clean_manager = " ".join(manager_id.split())
        with self._lock:
            erp, saas = self._read_all()
            correlation = self._correlation(erp, saas)
            if (
                self._executor is None
                or not clean_manager
                or self._text(self._agent_run.get("state")) != "PLAN_READY"
                or correlation["status"] != "FULLY_CORRELATED"
            ):
                raise ValueError("manager approval requires an executor and a fresh verified plan")
            approval_id = f"m20-approval-{self._run_number:04d}"
            tuple_values = correlation.get("tuple")
            binding = {
                "case_tuple": dict(tuple_values) if isinstance(tuple_values, Mapping) else {},
                "erp_sequence": int(erp.get("sequence") or 0),
                "saas_sequence": int(saas.get("sequence") or 0),
                "erp_state_digest": hashlib.sha256(
                    json.dumps(
                        erp.get("documents", []),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
                "saas_state_digest": hashlib.sha256(
                    json.dumps(
                        saas.get("sources", []),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
                "run_id": self._text(self._agent_run.get("run_id")),
                "scope": "M20_DEMO_RECOVERY_AND_CUSTOMER_FULFILLMENT",
            }
            plan_digest = hashlib.sha256(
                json.dumps(binding, sort_keys=True, separators=(",", ":"), default=str).encode(
                    "utf-8"
                )
            ).hexdigest()
            self._approval = {
                "approval_id": approval_id,
                "manager_id": clean_manager,
                "approved_at": self._now(),
                "plan_digest": plan_digest,
                **binding,
            }
            self._append(
                "manager.approval.granted",
                source_id="agent-platform",
                provider="Manager",
                status="APPROVED",
                label="Guarded recovery approved",
                detail="Approval is bound to the current M20 case evidence.",
                record_id=approval_id,
            )
            return self._projection(erp, saas)

    def execute(self, approval_id: str, idempotency_key: str) -> dict[str, object]:
        with self._lock:
            erp, saas = self._read_all()
            correlation = self._correlation(erp, saas)
            tuple_values = correlation.get("tuple")
            current_binding = {
                "case_tuple": dict(tuple_values) if isinstance(tuple_values, Mapping) else {},
                "erp_sequence": int(erp.get("sequence") or 0),
                "saas_sequence": int(saas.get("sequence") or 0),
                "erp_state_digest": hashlib.sha256(
                    json.dumps(
                        erp.get("documents", []),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
                "saas_state_digest": hashlib.sha256(
                    json.dumps(
                        saas.get("sources", []),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                ).hexdigest(),
                "run_id": self._text(self._agent_run.get("run_id")),
                "scope": "M20_DEMO_RECOVERY_AND_CUSTOMER_FULFILLMENT",
            }
            current_digest = hashlib.sha256(
                json.dumps(
                    current_binding, sort_keys=True, separators=(",", ":"), default=str
                ).encode("utf-8")
            ).hexdigest()
            if (
                self._executor is None
                or approval_id != self._text(self._approval.get("approval_id"))
                or correlation["status"] != "FULLY_CORRELATED"
                or self._text(self._agent_run.get("state")) != "PLAN_READY"
                or not idempotency_key.startswith("m20-")
                or current_digest != self._text(self._approval.get("plan_digest"))
            ):
                raise ValueError(
                    "execution requires the current Manager approval, unchanged plan, "
                    "M20 idempotency key, and fully verified evidence"
                )
            raw_values = correlation.get("tuple")
            values = dict(raw_values) if isinstance(raw_values, Mapping) else {}
            documents = self._documents_by_kind(erp)
            receipt = documents.get("purchase_receipt", {})
            invoice = documents.get("purchase_invoice", {})
            sales_order = documents.get("sales_order", {})
            result = self._executor.execute(
                DemoReleasePlan(
                    case_id=self._text(values.get("case_id")),
                    purchase_receipt=self._text(values.get("purchase_receipt")),
                    purchase_invoice=self._text(values.get("purchase_invoice")),
                    quantity=float(values.get("quantity") or 0),
                    idempotency_key=idempotency_key,
                    sales_order=self._text(sales_order.get("name")),
                    sales_order_quantity=float(sales_order.get("quantity") or 0),
                )
            )
            value_required = bool(sales_order)
            erp_verified = bool(getattr(result, "verified", False)) and (
                not value_required or bool(getattr(result, "order_to_cash_verified", False))
            )
            self._execution = {
                "available": False,
                "status": "VERIFYING" if erp_verified else "FAILED",
                "detail": (
                    "ERPNext write completed. Waiting for the independent Celigo run receipt."
                    if erp_verified
                    else "ERPNext write did not pass its fresh verification read."
                ),
                "transfer_name": getattr(result, "transfer_name", ""),
                "invoice_name": getattr(result, "invoice_name", ""),
                "sales_order": getattr(result, "sales_order", ""),
                "delivery_note": getattr(result, "delivery_note", ""),
                "sales_invoice": getattr(result, "sales_invoice", ""),
                "order_to_cash_verified": bool(getattr(result, "order_to_cash_verified", False)),
                "idempotency_key": idempotency_key,
                "approved_quantity": float(values.get("quantity") or 0),
                "executed_at": self._now(),
                "erp_verified": erp_verified,
                "approval_id": approval_id,
                "pre_state": {
                    "receipt_status": self._text(receipt.get("status")),
                    "invoice_status": self._text(invoice.get("status")),
                    "integration_receipt_status": self._text(
                        self._integration_receipt(saas, correlation).get("status")
                    ),
                },
            }
            self._append(
                "agent.execution.completed",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status=self._text(self._execution["status"]),
                label="Guarded ERP recovery completed",
                detail=self._text(self._execution["detail"]),
                record_id=self._text(self._execution.get("transfer_name")),
                provenance=(
                    "live-provider-write"
                    if self._text(erp.get("provider")).startswith("ERPNext / Frappe Cloud")
                    else "synthetic-demo"
                ),
                read_only=False,
            )
            erp, saas = self._read_all()
            return self._projection(erp, saas)

    def approve_execute_verify(self, manager_id: str, idempotency_key: str) -> dict[str, object]:
        """Apply one Manager decision, execute, then freshly verify the scoped providers."""

        approved = self.approve(manager_id)
        execution = approved.get("execution")
        if not isinstance(execution, Mapping):
            raise ValueError("manager approval did not produce an execution scope")
        approval_id = self._text(execution.get("approval_id"))
        if not approval_id:
            raise ValueError("manager approval did not produce an approval id")
        self.execute(approval_id, idempotency_key)
        return self.verify()

    def record_conversation_turn(
        self, question: str, answer: str, advisory: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist bounded, case-scoped dialogue without granting write authority."""

        with self._lock:
            raw_evidence_ids = advisory.get("evidence_ids", [])
            evidence_ids = (
                [str(item) for item in raw_evidence_ids]
                if isinstance(raw_evidence_ids, (list, tuple))
                else []
            )
            raw_tools = advisory.get("tool_calls", [])
            tool_calls = (
                [str(item) for item in raw_tools] if isinstance(raw_tools, (list, tuple)) else []
            )
            provider = advisory.get("provider")
            usage = advisory.get("usage")
            self._conversation.append(
                {
                    "turn_id": f"turn-{len(self._conversation) + 1:03d}",
                    "run_id": self._text(self._agent_run.get("run_id")),
                    "question": " ".join(question.split())[:500],
                    "answer": " ".join(answer.split())[:1200],
                    "evidence_ids": evidence_ids,
                    "tool_calls": tool_calls,
                    "provider": dict(provider) if isinstance(provider, Mapping) else {},
                    "usage": dict(usage) if isinstance(usage, Mapping) else {},
                    "latency_ms": int(advisory.get("latency_ms") or 0),
                    "context_turns": int(advisory.get("context_turns") or 0),
                    "created_at": self._now(),
                }
            )
            self._conversation = self._conversation[-12:]
            self._append(
                "human.agent.conversation.completed",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="ANSWERED",
                label="Evidence Agent answered",
                detail=(
                    f"Conversation turn {len(self._conversation)} cited "
                    f"{len(evidence_ids)} evidence records."
                ),
            )
            erp, saas = self._read_all()
            return self._projection(erp, saas)

    def verify(self) -> dict[str, object]:
        """Complete recovery only after a fresh, independent Celigo receipt read."""

        with self._lock:
            erp, saas = self._read_all()
            correlation = self._correlation(erp, saas)
            receipt = self._integration_receipt(saas, correlation)
            if not self._execution or not bool(self._execution.get("erp_verified")):
                raise ValueError("verification requires a completed guarded ERP execution")
            documents = self._documents_by_kind(erp)
            value_required = bool(documents.get("sales_order"))
            value_proof = self._value_proof(erp)
            if value_required and self._text(value_proof.get("status")) != "BILLED_VERIFIED":
                self._execution.update(
                    {
                        "available": False,
                        "status": "VERIFYING",
                        "detail": (
                            "ERPNext write returned, but the fresh authoritative reread has not "
                            "yet proven both the submitted Delivery Note and Sales Invoice."
                        ),
                    }
                )
                return self._projection(erp, saas)
            if receipt["status"] != "VERIFIED":
                self._execution.update(
                    {
                        "available": False,
                        "status": "VERIFYING",
                        "detail": (
                            "ERPNext is verified; waiting for a tuple-matched Celigo run receipt."
                        ),
                    }
                )
                return self._projection(erp, saas)
            self._execution.update(
                {
                    "available": False,
                    "status": "VERIFIED",
                    "detail": (
                        "ERPNext recovery and the independent Celigo run receipt are verified."
                    ),
                    "celigo_receipt_id": self._text(receipt.get("record_id")),
                    "verified_at": self._now(),
                }
            )
            self._diagnosis.update(
                {
                    "status": "VERIFIED",
                    "integration_receipt_status": "VERIFIED",
                    "summary": (
                        "The agent diagnosed the ERPNext Quality Hold, completed the "
                        "manager-gated recovery, and verified the tuple-matched Celigo run receipt."
                    ),
                    "tool_calls": [
                        *[
                            call
                            for call in self._current_tool_calls()
                            if self._text(call.get("tool")) != "celigo.read_exact_run_receipt"
                        ],
                        {"tool": "celigo.read_exact_run_receipt", "status": "VERIFIED"},
                    ],
                }
            )
            self._agent_run.update({"state": "VERIFIED", "active_step": "", "confidence": 0.96})
            self._issue_resolution_packet(erp, saas, correlation, receipt)
            self._append(
                "agent.execution.verified",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="VERIFIED",
                label="Closed-loop recovery verified",
                detail=self._text(self._execution["detail"]),
                record_id=self._text(receipt.get("record_id")),
            )
            return self._projection(erp, saas)

    def current(self) -> dict[str, object]:
        """Fetch evidence and return a read-only, server-ledger projection."""

        with self._lock:
            erp, saas = self._read_all()
            return self._projection(erp, saas)

    def stop(self) -> dict[str, object]:
        """Let the operator pause an unclosed investigation without losing evidence."""

        with self._lock:
            if self._text(self._agent_run.get("state")) in {"IDLE", "VERIFIED", "STOPPED"}:
                raise ValueError("only an active investigation can be paused")
            erp, saas = self._read_all()
            run_id = self._text(self._agent_run.get("run_id"))
            self._agent_run.update({"state": "STOPPED", "active_step": ""})
            self._diagnosis.update(
                {
                    "status": "STOPPED",
                    "summary": (
                        "Investigation paused by the operator; no provider effect was issued."
                    ),
                }
            )
            self._append(
                "human.investigation.paused",
                source_id="agent-platform",
                provider="Operator",
                status="STOPPED",
                label="Investigation paused by operator",
                detail="Evidence remains read-only and available; no provider effect was issued.",
                record_id=run_id,
            )
            return self._projection(erp, saas)

    def diagnose(self) -> dict[str, object]:
        """Run bounded diagnosis from the same provider reads, never a write."""

        with self._lock:
            self._approval = {}
            self._execution = {}
            self._resolution_packet = {}
            self._conversation = []
            self._run_number += 1
            run_id = f"agent-run-{self._run_number:04d}"
            self._agent_run = {
                "run_id": run_id,
                "state": "OBSERVING",
                "active_step": "read_erp",
                "confidence": 0.0,
            }
            self._append(
                "agent.run.observing",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="OBSERVING",
                label="Agent run opened",
                detail="Observing the scoped quality-release case.",
                record_id=run_id,
            )
            self._agent_run.update({"state": "PLANNING", "active_step": "correlate_registry"})
            self._append(
                "agent.run.planning",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="PLANNING",
                label="Investigation plan created",
                detail="ERP, registry, and integration-receipt reads were planned.",
                record_id=run_id,
            )
            self._agent_run.update({"state": "GATHERING", "active_step": "validate_run"})
            self._append(
                "agent.diagnosis.started",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="DIAGNOSING",
                label="Automatic diagnosis started",
                detail="Reading correlated provider evidence; provider writes remain disabled.",
            )
            erp, saas = self._read_all()
            self._agent_run.update({"state": "REASONING", "active_step": "guarded_plan"})
            self._append(
                "agent.run.reasoning",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="REASONING",
                label="Agent evaluated evidence",
                detail=(
                    "Evidence authority, correlation completeness, and guard conditions "
                    "were evaluated."
                ),
                record_id=run_id,
            )
            docs = self._documents_by_kind(erp)
            live_metrics = self._live_flow_metrics(erp)
            rejected = float(live_metrics["quality_hold"] or 0)
            quality_hold = rejected > 0
            invoice = docs.get("purchase_invoice", {})
            invoice_held = bool(live_metrics["invoice_held"])
            source_statuses = [
                self._text(erp.get("status")),
                *[self._text(row.get("status")) for row in self._source_rows(saas)],
            ]
            degraded = any(status in {"DEGRADED", "NOT_CONFIGURED"} for status in source_statuses)
            correlation = self._correlation(erp, saas)
            integration_receipt = self._integration_receipt(saas, correlation)
            external_recovery = self._external_recovery_verified(erp, saas)
            value_proof = self._value_proof(erp)
            value_pending = self._value_pending(erp)
            tool_calls = [
                {"tool": "erpnext.read_case_documents", "status": self._text(erp.get("status"))},
                {"tool": "saas.read_correlated_records", "status": self._text(saas.get("status"))},
                {
                    "tool": "celigo.read_exact_run_receipt",
                    "status": self._text(integration_receipt.get("status")),
                },
            ]
            if self._text(value_proof.get("status")) != "NOT_CONFIGURED":
                tool_calls.append(
                    {
                        "tool": "erpnext.read_customer_order_to_cash",
                        "status": self._text(value_proof.get("status")),
                    }
                )
            if self._text(erp.get("status")) != "CONNECTED":
                finding = "INCONCLUSIVE"
                summary = "ERPNext evidence is unavailable, so the agent cannot diagnose the case."
            elif external_recovery and not value_pending:
                finding = "RECOVERY_VERIFIED_FROM_LIVE_READS"
                summary = (
                    "Fresh ERPNext, Airtable, and Celigo reads prove the prior guarded "
                    "recovery is complete; no new release is proposed."
                )
            elif value_pending and external_recovery:
                finding = "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT"
                observed = self._mapping(value_proof.get("observed"))
                value_documents = self._mapping(value_proof.get("documents"))
                sales_order_name = self._text(
                    value_documents.get("sales_order"), "the scoped order"
                )
                summary = (
                    "Procurement recovery is verified, but ERPNext customer order "
                    f"{sales_order_name} "
                    f"still has {float(observed.get('booked_revenue') or 0):,.0f} "
                    "of booked revenue awaiting a manager-gated delivery and billing reread."
                )
            elif quality_hold:
                finding = "QUALITY_HOLD_DETECTED"
                summary = (
                    f"ERPNext reports {rejected:g} units in Quality Hold; no release is executed."
                )
            elif invoice_held:
                finding = "INVOICE_PAYMENT_HOLD"
                summary = (
                    f"Inventory is reconciled, but ERPNext invoice "
                    f"{self._text(invoice.get('name'), 'the scoped invoice')} remains in "
                    "PAYMENT_HOLD; no release is executed."
                )
            else:
                finding = "NO_QUALITY_HOLD_DETECTED"
                summary = "ERPNext did not return a Quality Hold for the scoped receipt."
            if degraded:
                summary += (
                    " Some supporting systems are unavailable; journal records are not "
                    "causal proof."
                )
            if correlation["status"] != "FULLY_CORRELATED":
                summary += " Correlation is partial; release eligibility cannot be proven."
            elif integration_receipt["status"] != "VERIFIED":
                summary += (
                    " A Celigo run receipt will be required only after guarded ERP execution."
                )
            run_state = (
                "VERIFIED"
                if external_recovery and not value_pending
                else (
                    "BLOCKED"
                    if (
                        finding == "INCONCLUSIVE"
                        or correlation["status"] != "FULLY_CORRELATED"
                        or (not quality_hold and not invoice_held and not value_pending)
                    )
                    else "PLAN_READY"
                )
            )
            self._diagnosis = {
                "status": run_state,
                "finding": finding,
                "summary": summary,
                "hypotheses": [
                    {
                        "id": "quality_hold",
                        "label": "Inventory remains in Quality Hold",
                        "status": "SUPPORTED" if quality_hold else "ELIMINATED",
                    },
                    {
                        "id": "invoice_payment_hold",
                        "label": "Invoice remains held after inventory reconciliation",
                        "status": (
                            "SUPPORTED" if invoice_held and not quality_hold else "ELIMINATED"
                        ),
                    },
                    {
                        "id": "correlation_gap",
                        "label": "Source records refer to different receipts",
                        "status": (
                            "ELIMINATED"
                            if correlation["status"] == "FULLY_CORRELATED"
                            else "SUPPORTED"
                        ),
                    },
                    {
                        "id": "prior_effect",
                        "label": "Guarded recovery already completed",
                        "status": "SUPPORTED" if external_recovery else "ELIMINATED",
                    },
                    {
                        "id": "customer_order_value_gap",
                        "label": "Customer order is not yet delivered and billed",
                        "status": "SUPPORTED" if value_pending else "ELIMINATED",
                    },
                    {
                        "id": "journal_is_causal",
                        "label": "Slack or Jira alone proves the root cause",
                        "status": "ELIMINATED",
                    },
                ],
                "tool_calls": tool_calls,
                "correlation_status": correlation["status"],
                "integration_receipt_status": integration_receipt["status"],
            }
            self._agent_run.update(
                {
                    "state": run_state,
                    "active_step": "",
                    "confidence": (
                        0.96
                        if external_recovery and not value_pending
                        else (
                            0.91
                            if finding
                            in {
                                "QUALITY_HOLD_DETECTED",
                                "INVOICE_PAYMENT_HOLD",
                                "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT",
                            }
                            and correlation["status"] == "FULLY_CORRELATED"
                            else (
                                0.82
                                if finding
                                in {
                                    "QUALITY_HOLD_DETECTED",
                                    "INVOICE_PAYMENT_HOLD",
                                    "CUSTOMER_ORDER_AWAITING_VERIFIED_FULFILLMENT",
                                }
                                else 0.0
                            )
                        )
                    ),
                }
            )
            self._append(
                "agent.diagnosis.completed",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status=run_state,
                label="Diagnosis completed",
                detail=summary,
            )
            return self._projection(erp, saas)

    def answer(self, question: str) -> dict[str, object]:
        """Answer a case question only from a fresh, bounded evidence read."""

        clean_question = " ".join(question.split())
        if not clean_question or len(clean_question) > 500:
            raise ValueError("question must contain between 1 and 500 visible characters")
        with self._lock:
            erp, saas = self._read_all()
            docs = self._documents_by_kind(erp)
            receipt = docs.get("purchase_receipt", {})
            invoice = docs.get("purchase_invoice", {})
            correlation = self._correlation(erp, saas)
            integration_receipt = self._integration_receipt(saas, correlation)
            execution = self._execution_projection(erp, saas)
            normalized = clean_question.lower()
            value_proof = self._value_proof(erp)
            observed_value = value_proof.get("observed")
            observed = observed_value if isinstance(observed_value, Mapping) else {}
            counterfactual_value = value_proof.get("counterfactual")
            counterfactual = (
                counterfactual_value if isinstance(counterfactual_value, Mapping) else {}
            )
            asks_recovery = any(
                term in normalized
                for term in (
                    "release",
                    "approve",
                    "execute",
                    "fix",
                    "recover",
                    "complete",
                    "verify",
                )
            )
            asks_provenance = any(
                term in normalized
                for term in (
                    "evidence",
                    "source",
                    "provenance",
                    "correlation",
                    "trace",
                    "prove",
                    "why",
                )
            )
            asks_customer_value = any(
                term in normalized
                for term in (
                    "revenue",
                    "sales order",
                    "customer order",
                    "delivery",
                    "billed",
                    "billing",
                    "margin",
                    "gross spread",
                    "收入",
                    "订单",
                    "交付",
                    "毛利",
                )
            )
            if asks_recovery and self._text(execution.get("status")) == "VERIFIED":
                answer = (
                    "Recovery is complete: ERPNext transfer "
                    f"{self._text(execution.get('transfer_name'), 'unavailable')} "
                    "is freshly verified; "
                    f"invoice {self._text(execution.get('invoice_name'), 'unavailable')} "
                    "is no longer held; the tuple-matched Celigo receipt is verified; "
                    f"and customer billing status is {self._text(value_proof.get('status'))}."
                )
            elif asks_recovery and self._executor is None:
                answer = (
                    "This observer build can diagnose the case, but provider writes are disabled."
                )
            elif asks_recovery:
                answer = (
                    "The dedicated demo executor is guarded by a verified evidence tuple and one "
                    "Manager approval. Its current recovery state is "
                    f"{self._text(execution.get('status'), 'AWAITING_MANAGER_APPROVAL')}."
                )
            elif asks_provenance:
                tuple_values = correlation.get("tuple")
                case_id = (
                    self._text(tuple_values.get("case_id"))
                    if isinstance(tuple_values, Mapping)
                    else "the scoped case"
                )
                answer = (
                    "The agent correlated ERPNext receipt "
                    f"{self._text(receipt.get('name'), 'unavailable')}, invoice "
                    f"{self._text(invoice.get('name'), 'unavailable')}, and the Airtable "
                    f"release tuple for {case_id}. Celigo receipt status is "
                    f"{self._text(integration_receipt.get('status'), 'UNAVAILABLE')}."
                )
            elif asks_customer_value:
                currency = self._text(value_proof.get("currency"), "USD")
                answer = (
                    f"ERPNext currently proves customer-order stage "
                    f"{self._text(value_proof.get('status'), 'NOT_CONFIGURED')}: "
                    f"booked revenue {currency} {float(observed.get('booked_revenue') or 0):,.2f}, "
                    f"billed revenue {currency} {float(observed.get('billed_revenue') or 0):,.2f}, "
                    f"and delivered quantity {float(observed.get('delivered_quantity') or 0):g} of "
                    f"{float(observed.get('order_quantity') or 0):g}. "
                    f"Revenue at risk is {currency} "
                    f"{float(counterfactual.get('revenue_at_risk_if_hold_persists') or 0):,.2f} "
                    "and is explicitly counterfactual; this case does not claim a "
                    "causal revenue lift."
                )
            elif "invoice" in normalized:
                answer = (
                    f"The scoped invoice is {self._text(invoice.get('name'), 'unavailable')}. "
                    f"Its current ERP status is {self._text(invoice.get('status'), 'unavailable')}."
                )
            elif any(term in normalized for term in ("hold", "missing", "quantity", "receipt")):
                answer = (
                    f"The scoped receipt is {self._text(receipt.get('name'), 'unavailable')}: "
                    f"{receipt.get('rejected', 'unavailable')} units are in the reported hold "
                    "state."
                )
            else:
                answer = (
                    "I can answer from the current ERPNext, Airtable, Jira, Celigo, and Slack "
                    "read projection. Ask about the receipt hold, invoice, correlation, or "
                    "release guard."
                )
            if correlation["status"] != "FULLY_CORRELATED":
                answer += " Correlation remains partial."
            self._append(
                "agent.evidence.question_answered",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="READ_ONLY",
                label="Evidence question answered",
                detail="Fresh read-only evidence was used; no provider command was issued.",
            )
            projection = self._projection(erp, saas)
            projection["answer"] = answer
            return projection
