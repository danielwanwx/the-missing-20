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
import math
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from the_missing_20.adapters import dialogue_intent, operational_metrics
from the_missing_20.adapters.demo_executor import DemoReleasePlan
from the_missing_20.adapters.operational_history import OperationalHistory

AGENT_PLATFORM_SCHEMA_VERSION = "missing20-agent-platform/v1"


class EvidenceReader(Protocol):
    """Minimal read-only contract shared by the evidence adapters."""

    def current(self) -> dict[str, object]: ...


class DemoExecutor(Protocol):
    def execute(self, plan: DemoReleasePlan) -> object: ...


class ReceivingReader(Protocol):
    def receiving_work(self, case_id: str, purchase_order: str) -> dict[str, object]: ...


class AgentPlatform:
    """Build a truthful, case-scoped platform projection from provider reads."""

    def __init__(
        self,
        erpnext: EvidenceReader,
        saas: EvidenceReader,
        *,
        executor: DemoExecutor | None = None,
        state_path: Path | None = None,
        receiving: ReceivingReader | None = None,
    ) -> None:
        self._erpnext = erpnext
        self._saas = saas
        self._executor = executor
        self._receiving = receiving
        self._receiving_refresh_after = 0.0
        self._state_path = state_path
        self._history = (
            OperationalHistory(state_path.with_suffix(".history.sqlite3"))
            if state_path is not None
            else None
        )
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
        self._model_gate: dict[str, object] = {}
        self._conversation: list[dict[str, object]] = []
        self._runtime_instance_id = uuid4().hex
        self._dialogue_intent: dict[str, object] = {}
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
        stored_runtime_id = payload.get("runtime_instance_id")
        if isinstance(stored_runtime_id, str) and stored_runtime_id:
            self._runtime_instance_id = stored_runtime_id
        events = payload.get("events")
        if isinstance(events, list):
            self._events = [dict(item) for item in events if isinstance(item, Mapping)][-80:]
        for attribute, key in (
            ("_agent_run", "agent_run"),
            ("_diagnosis", "diagnosis"),
            ("_approval", "approval"),
            ("_execution", "execution"),
            ("_resolution_packet", "resolution_packet"),
            ("_model_gate", "model_gate"),
            ("_dialogue_intent", "dialogue_intent"),
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
        if self._text(self._model_gate.get("status")) == "PENDING":
            self._block_model_plan(
                "INTERRUPTED",
                "Investigation was interrupted by a restart. Retry the investigation.",
            )
            self._persist_state()
        elif (
            self._text(self._agent_run.get("state")) == "PLAN_READY"
            and self._text(self._model_gate.get("status")) != "VALIDATED"
        ):
            # An older persisted deterministic plan is not proof that a live
            # model completed. Re-read it instead of restoring its authority.
            self._block_model_plan(
                "REVALIDATION_REQUIRED", "Restarted plans require a fresh investigation."
            )
            self._persist_state()

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
                "This earlier answer was withheld because it claimed an unproven revenue uplift. "
                "Inspect current order, invoice and ledger evidence; no replacement business "
                "conclusion has been inferred."
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
            "model_gate": self._model_gate,
            "conversation": self._conversation[-12:],
            "runtime_instance_id": self._runtime_instance_id,
            "dialogue_intent": self._dialogue_intent,
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

    @staticmethod
    def _float_or_zero(value: object) -> float:
        """Keep existing optional-number defaults, but reject malformed scalars."""

        if value is None:
            return 0.0
        if not isinstance(value, (str, int, float)):
            raise TypeError("numeric evidence must be a scalar")
        number = float(value or 0)
        if not math.isfinite(number):
            raise ValueError("numeric evidence must be finite")
        return number

    @staticmethod
    def _int_or_zero(value: object) -> int:
        """Narrow optional counters without a lossy intermediate float conversion."""

        if value is None:
            return 0
        if not isinstance(value, (str, int, float)):
            raise TypeError("counter evidence must be a scalar")
        return int(value or 0)

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
        quality_hold = self._float_or_zero(self._live_flow_metrics(erp)["quality_hold"])
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

    def _model_evidence_digest(self, erp: Mapping[str, object], saas: Mapping[str, object]) -> str:
        """Bind model completion to facts, not polling timestamps or animation frames."""

        facts = {
            "case_id": erp.get("case_id"),
            "documents": erp.get("documents", []),
            "sources": [
                {key: value for key, value in row.items() if key != "occurred_at"}
                for row in self._source_rows(saas)
            ],
            "correlation": self._correlation(erp, saas),
            "ledger_evidence": erp.get("ledger_evidence"),
            "receiving_work": erp.get("receiving_work"),
        }
        return hashlib.sha256(
            json.dumps(facts, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

    def _block_model_plan(self, status: str, summary: str) -> None:
        self._approval = {}
        self._model_gate["status"] = status
        if self._text(self._agent_run.get("state")) == "STOPPED":
            return
        self._agent_run.update({"state": "BLOCKED", "active_step": "", "confidence": 0.0})
        self._diagnosis.update({"status": "BLOCKED", "summary": summary})

    def claim_diagnosis(self) -> tuple[dict[str, object], bool]:
        """Atomically claim one live model run; repeated requests do not start another."""

        with self._lock:
            if self._text(self._model_gate.get("status")) == "PENDING":
                erp, saas = self._read_all()
                return self._projection(erp, saas), False
            return self.diagnose(release=False), True

    def agent_run_is_active(self, run_id: str) -> bool:
        """Local cancellation check: do not poll ERP from each specialist hook."""
        with self._lock:
            return (
                bool(run_id)
                and run_id == self._text(self._agent_run.get("run_id"))
                and self._text(self._model_gate.get("status")) == "PENDING"
                and self._text(self._agent_run.get("state")) != "STOPPED"
            )

    def record_agent_runtime_progress(
        self, runtime_event: Mapping[str, object], run_id: str | None = None
    ) -> None:
        from the_missing_20.agents.role_delegation import task_activity

        with self._lock:
            if run_id is None or not self.agent_run_is_active(run_id):
                return
            activity = task_activity(runtime_event)
            if activity is None:
                return
            status, label, detail = activity
            self._append(
                f"agent.{runtime_event['type']}",
                source_id="agent-platform",
                provider="Strands",
                status=status,
                label=label,
                detail=detail,
                record_id=str(runtime_event.get("task_id", "")),
            )

    def record_live_strands_investigation(
        self, advisory: Mapping[str, object], *, run_id: str
    ) -> dict[str, object]:
        """Complete the exact claimed HTTP run, never whichever run happens to be active."""

        return self.record_strands_investigation(advisory, run_id=run_id)

    def record_strands_investigation(
        self, advisory: Mapping[str, object], *, run_id: str | None = None
    ) -> dict[str, object]:
        """Release a current policy-backed plan only after validated model completion.

        Tokenless calls are retained for direct offline diagnosis callers. A live
        claim always requires its run token, including failures and retries.
        """

        with self._lock:
            active_run = self._text(self._agent_run.get("run_id"))
            pending = self._text(self._model_gate.get("status")) == "PENDING"
            if (
                self._text(self._agent_run.get("state"))
                in {"IDLE", "STOPPED", "VERIFYING", "VERIFIED"}
                or (pending and run_id != active_run)
                or (
                    self._model_gate.get("requires_run_id") is True
                    and (not pending or run_id != active_run)
                )
                or (run_id is not None and (not pending or run_id != active_run))
            ):
                erp, saas = self._read_all()
                return self._projection(erp, saas)
            self._diagnosis["strands_investigation"] = dict(advisory)
            status = self._text(advisory.get("status"), "AGENT_UNAVAILABLE")
            run_id = active_run
            # Revoke a previous offline plan as well: an unavailable/invalid
            # actual model result must never leave a manager action enabled.
            self._block_model_plan(
                status, "The agent could not validate a recovery plan. Retry the investigation."
            )
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
            policy = self._mapping(self._mapping(advisory.get("evidence_findings")).get("policy"))
            result = self._mapping(advisory.get("result"))
            disposition = self._text(result.get("disposition"))
            unchanged = self._text(self._model_gate.get("evidence_digest")) == (
                self._model_evidence_digest(erp, saas)
            )
            valid = (
                status == "COMPLETE"
                and disposition == self._text(policy.get("disposition"))
                and result.get("write_performed") is False
                and self._source_freshness(erp)["status"] == "CURRENT"
                and self._correlation(erp, saas)["status"] == "FULLY_CORRELATED"
                and unchanged
            )
            candidate = self._text(self._model_gate.get("candidate_state"))
            if valid and disposition == "RECOVERY_READY" and candidate == "PLAN_READY":
                self._apply_completed_strands_diagnosis(advisory, erp, saas)
                self._model_gate["status"] = "VALIDATED"
            elif valid and disposition == "RECOVERY_COMPLETE" and candidate == "VERIFIED":
                self._agent_run.update({"state": "VERIFIED", "active_step": "", "confidence": 0.96})
                self._diagnosis.update(
                    {"status": "VERIFIED", "summary": self._text(result.get("reason"))}
                )
                self._model_gate["status"] = "VALIDATED"
            elif status == "COMPLETE":
                reason = (
                    "Source evidence changed during investigation. Start a fresh investigation."
                    if not unchanged
                    else "The evidence and agent result do not support a recovery plan."
                )
                self._block_model_plan("VALIDATION_FAILED", reason)
            self._append(
                "agent.plan.ready"
                if self._model_gate["status"] == "VALIDATED"
                else "agent.plan.blocked",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status=self._text(self._agent_run.get("state")),
                label="Investigation validated"
                if self._model_gate["status"] == "VALIDATED"
                else "Investigation needs review",
                detail=self._text(self._diagnosis.get("summary")),
                record_id=run_id,
            )
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
                event["change_count"] = (
                    0 if self._int_or_zero(metrics.get("source_sequence")) <= 1 else 1
                )
            source_id = self._text(record.get("source_id"))
            self._source_sequences[source_id] = self._sequence
            if source_id.startswith("erp-"):
                self._source_sequences["erpnext-missing20"] = self._sequence

    @staticmethod
    def _documents_by_kind(erp: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        raw_documents = erp.get("documents")
        if not isinstance(raw_documents, list):
            return {}
        configured = erp.get("configured_document_names")
        primary = erp.get("primary_document_names")
        names = dict(primary) if isinstance(primary, Mapping) else {}
        if isinstance(configured, Mapping):
            names.update({kind: name for kind, name in configured.items() if name})
        kinds = {
            str(row["kind"])
            for row in raw_documents
            if isinstance(row, Mapping) and row.get("kind")
        }
        selected: dict[str, Mapping[str, object]] = {}
        for kind in kinds:
            rows = operational_metrics.documents(erp, kind, posted=False)
            preferred = names.get(kind)
            if preferred:
                match = next((row for row in rows if row.get("name") == preferred), None)
                if match is not None:
                    selected[kind] = match
            elif len(rows) == 1:
                selected[kind] = rows[0]
            # Multiple unbound documents are evidence, not an implicit authorization target.
        return selected

    @classmethod
    def _source_freshness(cls, erp: Mapping[str, object]) -> dict[str, object]:
        return operational_metrics.source_freshness(erp)

    @classmethod
    def _live_flow_metrics(cls, erp: Mapping[str, object]) -> dict[str, object]:
        return operational_metrics.live_flow_metrics(erp)

    @classmethod
    def _case_projection(cls, erp: Mapping[str, object]) -> dict[str, object]:
        metrics = cls._live_flow_metrics(erp)
        documents = cls._documents_by_kind(erp)
        status = cls._source_freshness(erp)["status"]
        current = status == "CURRENT"
        quantities = {
            name: metrics.get(key) if current else None
            for name, key in (
                ("ordered", "expected"),
                ("physically_arrived", "physically_arrived"),
                ("available", "recorded"),
                ("quality_hold", "quality_hold"),
                ("receipt_unresolved", "receipt_unresolved"),
                ("received", "received"),
                ("outstanding_order_quantity", "outstanding_order_quantity"),
                ("available_to_promise", "available_to_promise"),
                ("received_cumulative", "received_cumulative"),
                ("accepted_cumulative", "accepted_cumulative"),
                ("released_quantity", "released_quantity"),
                ("delivered_quantity", "delivered_quantity"),
                ("case_balance", "case_balance"),
                ("receipt_posted_quantity", "receipt_posted_quantity"),
                ("invoice_count", "invoice_count"),
            )
        }
        return {
            "provenance": "live-read",
            "status": status,
            "read_only": True,
            "source_sequence": metrics["source_sequence"],
            "case": {
                "case_id": cls._text(erp.get("case_id"), "M20-ERP-LIVE"),
                "quantities": quantities,
                "balance_basis": metrics.get("recorded_basis"),
                "uom": metrics.get("uom"),
                "item_code": metrics.get("item_code"),
                "physical_observation_basis": metrics.get("physically_arrived_basis"),
                "price_comparison_status": cls._business_impact(erp).get("price_comparison_status"),
                "invoice_held": metrics["invoice_held"] if current else None,
                **{
                    kind: cls._text(documents.get(kind, {}).get("name"))
                    for kind in (
                        "purchase_order",
                        "purchase_receipt",
                        "purchase_invoice",
                        "quality_release_transfer",
                        "sales_order",
                        "delivery_note",
                        "sales_invoice",
                    )
                },
            },
        }

    @classmethod
    def _business_impact(cls, erp: Mapping[str, object]) -> dict[str, object]:
        return operational_metrics.business_impact(erp)

    @classmethod
    def _value_proof(cls, erp: Mapping[str, object]) -> dict[str, object]:
        """Separate observed financial facts from estimates and counterfactuals."""

        documents = cls._documents_by_kind(erp)
        purchase_order = documents.get("purchase_order", {})
        sales_order = documents.get("sales_order", {})
        delivery_note = documents.get("delivery_note", {})
        sales_invoice = documents.get("sales_invoice", {})

        def number(value: object) -> float | None:
            if value is None or isinstance(value, bool):
                return None
            try:
                parsed = float(str(value))
                return parsed if math.isfinite(parsed) else None
            except (TypeError, ValueError, OverflowError):
                return None

        metrics = cls._live_flow_metrics(erp)
        booked = number(sales_order.get("booked_value")) if sales_order else None
        billed = (
            number(sales_invoice.get("billed_revenue"))
            if sales_invoice
            else 0.0
            if sales_order
            else None
        )
        invoice_gross = number(sales_invoice.get("billed_amount"))
        order_quantity = number(sales_order.get("quantity"))
        issue_quantity = (
            number(delivery_note.get("quantity")) if delivery_note else 0.0 if sales_order else None
        )
        billing_percent = number(sales_order.get("billed_percent"))
        invoice_quantity = number(sales_invoice.get("quantity"))
        currency = sales_invoice.get("currency") or sales_order.get("currency") or None
        same_currency = bool(
            currency
            and sales_order.get("currency") == currency
            and sales_invoice.get("currency") == currency
        )
        order_status = cls._text(sales_order.get("status"), "NOT_CONFIGURED")
        delivered = cls._text(delivery_note.get("status")) == "SUBMITTED"
        invoice_posted = cls._text(sales_invoice.get("status")) == "SUBMITTED"
        issue_complete = bool(
            delivered
            and order_quantity is not None
            and order_quantity > 0
            and issue_quantity is not None
            and issue_quantity >= order_quantity
        )
        billed_complete = bool(
            invoice_posted
            and (
                (billing_percent is not None and billing_percent >= 100)
                or (
                    invoice_quantity is not None
                    and order_quantity is not None
                    and order_quantity > 0
                    and invoice_quantity >= order_quantity
                )
            )
        )
        closed_loop_verified = issue_complete and billed_complete
        unit_cost = number(metrics.get("po_unit_cost"))

        def item_basis(document: Mapping[str, object]) -> set[tuple[str, str]]:
            rows = document.get("items", [])
            if not isinstance(rows, list) or not rows:
                return set()
            return {
                (str(row.get("item_code") or ""), str(row.get("uom") or ""))
                for row in rows
                if isinstance(row, Mapping)
            }

        po_items, billed_items = item_basis(purchase_order), item_basis(sales_invoice)
        matched_item = (
            len(po_items) == 1
            and po_items == billed_items
            and all(all(part for part in basis) for basis in po_items)
        )
        cost_quantity = (
            invoice_quantity
            if invoice_quantity is not None
            else (order_quantity if billed_complete else None)
        )
        purchase_basis = (
            unit_cost * cost_quantity
            if unit_cost is not None
            and cost_quantity is not None
            and same_currency
            and matched_item
            and purchase_order.get("currency") == currency
            else None
        )
        spread = (
            billed - purchase_basis
            if invoice_posted and billed is not None and purchase_basis is not None
            else None
        )
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
        proof: dict[str, object] = {
            "provenance": "ERPNext / Frappe Cloud live reread",
            "status": stage,
            "status_meaning": "Recorded ERP goods issue and billing; not carrier delivery or cash",
            "currency": currency,
            "observed": {
                "booked_revenue": booked,
                "billed_revenue": billed,
                "billed_amount": invoice_gross,
                "billing_percent": billing_percent,
                "billing_complete": billed_complete,
                "issue_complete": issue_complete,
                "delivered_quantity": issue_quantity,
                "recorded_issue_quantity": issue_quantity,
                "order_quantity": order_quantity,
                "purchase_cost_basis": purchase_basis,
                "gross_spread": None,
                "received_cumulative": metrics.get("received_cumulative"),
                "accepted_cumulative": metrics.get("accepted_cumulative"),
                "released_quantity": metrics.get("released_quantity"),
                "case_balance": metrics.get("case_balance"),
                "cash_collected": None,
            },
            "estimated": {
                "gross_spread": spread,
                "cost_basis_quantity": cost_quantity,
                "gross_spread_note": (
                    "Net invoiced sales less matched billed quantity at PO unit cost; "
                    "not realized margin, excludes landed-cost adjustments and overhead."
                    if spread is not None
                    else "Incomparable or missing net sales, currency, item/UOM or billed quantity."
                ),
            },
            "money_basis": {
                "booked_revenue": "SALES_ORDER_GROSS_AMOUNT",
                "billed_revenue": "SALES_INVOICE_NET_SALES",
                "billed_amount": "SALES_INVOICE_GROSS_AMOUNT",
                "comparable_currency": same_currency,
                "matched_purchase_item_uom": matched_item,
                "completion_basis": "ERP_BILLED_PERCENT_OR_LINKED_INVOICE_QUANTITY",
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
                "billed_revenue_is_observed": invoice_posted and billed is not None,
                "order_to_billing_closed_loop_verified": closed_loop_verified,
                "order_to_cash_closed_loop_verified": False,
                "carrier_delivery_verified": False,
                "cash_collection_verified": False,
                "causal_revenue_increase_proven": False,
            },
        }
        if cls._source_freshness(erp)["status"] != "CURRENT":
            proof.update(
                {
                    "status": "UNAVAILABLE",
                    "currency": None,
                    "observed": {key: None for key in cls._mapping(proof["observed"])},
                    "assertions": {key: False for key in cls._mapping(proof["assertions"])},
                    "counterfactual": {
                        "revenue_at_risk_if_hold_persists": None,
                        "classification": "UNAVAILABLE",
                    },
                    "estimated": {"gross_spread_note": "Current ERP evidence is unavailable."},
                }
            )
        return proof

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
                "url": self._text(row.get("url")),
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
        receiving = self._mapping(erp.get("receiving_work"))
        if receiving.get("status") == "CONFIGURED" and not self._live_flow_metrics(erp).get(
            "quality_hold"
        ):
            for index, source_id in (
                (1, "airtable-receiving"),
                (2, "jira-receiving"),
                (3, "celigo-receiving"),
            ):
                notification = by_source.get(source_id)
                if (
                    notification
                    and notification.get("case_id") == erp.get("case_id")
                    and notification.get("purchase_order") == receiving.get("purchase_order")
                ):
                    systems[index] = system(
                        {1: "airtable", 2: "jira", 3: "celigo"}[index],
                        {1: "Airtable Receiving", 2: "Jira Receiving", 3: "Celigo"}[index],
                        notification,
                        "Receiving review record; not QA, billing or stock authority"
                        if index == 2
                        else "Receipt notification copy; not QA, billing or stock authority",
                    )
                    systems[index]["write_state"] = (
                        "RECEIVING_REVIEW" if index == 2 else "EVENT_DRIVEN_NOTIFICATION"
                    )
                    if index == 2:
                        systems[index].update(
                            {
                                key: notification.get(key)
                                for key in ("arrival_id", "capture_id", "operation", "last_failure")
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

        if (
            self._source_freshness(erp)["status"] != "CURRENT"
            or self._text(saas.get("status")) != "CONNECTED"
        ):
            return False
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

        if self._source_freshness(erp)["status"] != "CURRENT":
            return None
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
            str(self._execution.get("receipt_post_quantity") or 0)
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
        pre_state.setdefault("available", None)
        pre_state.setdefault(
            "observation_basis",
            "EXECUTION_SNAPSHOT" if raw_pre_state else "PRE_EXECUTION_STATE_NOT_RETAINED",
        )
        current_metrics = self._live_flow_metrics(erp)
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
                "available": current_metrics["recorded"],
                "available_basis": current_metrics["recorded_basis"],
                **{
                    key: current_metrics.get(key)
                    for key in (
                        "received_cumulative",
                        "accepted_cumulative",
                        "released_quantity",
                        "delivered_quantity",
                        "case_balance",
                        "available_to_promise",
                    )
                },
                "customer_order_status": self._text(sales_order.get("status")),
                "customer_billed_revenue": sales_invoice.get("billed_revenue"),
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
        raw_documents = erp.get("documents", [])
        all_documents = (
            [document for document in raw_documents if isinstance(document, Mapping)]
            if isinstance(raw_documents, list)
            else []
        )
        for document in all_documents:
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
            totals = cls._mapping(ledger.get("totals"))
            assertions = cls._mapping(ledger.get("assertions"))
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
                    f"Debit {float(str(totals.get('debit') or 0)):,.2f}; credit "
                    f"{float(str(totals.get('credit') or 0)):,.2f}; "
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
        if self._text(value_proof.get("status")) not in {"NOT_CONFIGURED", "UNAVAILABLE"}:
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
            if node_id == "erpnext" and self._float_or_zero(live_metrics["quality_hold"]) > 0:
                status = "HOLD"
            elif node_id == "erpnext" and bool(live_metrics["invoice_held"]):
                status = "INVOICE_HOLD"
            receiving_notification = system.get("write_state") == "EVENT_DRIVEN_NOTIFICATION"
            if receiving_notification:
                role = "RECEIVING"
                sequence = self._source_sequences.get(f"{node_id}-receiving", 0)
            if (
                node_id == "airtable"
                and not receiving_notification
                and correlation["status"] != "FULLY_CORRELATED"
            ):
                status = "PARTIAL"
            if node_id == "celigo" and not receiving_notification:
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
        hold_detected = self._float_or_zero(live_metrics["quality_hold"]) > 0
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

    def _read_all(self, *, fresh: bool = False) -> tuple[dict[str, object], dict[str, object]]:
        if fresh:
            for source in (self._erpnext, self._saas):
                invalidate = getattr(source, "invalidate_cache", None)
                if callable(invalidate):
                    invalidate()
        erp = dict(self._erpnext.current())
        saas = self._saas.current()
        if self._receiving is not None:
            order = self._documents_by_kind(erp).get("purchase_order", {})
            work = self._receiving.receiving_work(
                self._text(erp.get("case_id")), self._text(order.get("name"))
            )
            erp["receiving_work"] = work
            if (
                operational_metrics.receiving_receipt_conflicts(erp)
                and not fresh
                and time.monotonic() >= self._receiving_refresh_after
            ):
                invalidate = getattr(self._erpnext, "invalidate_cache", None)
                if callable(invalidate):
                    self._receiving_refresh_after = time.monotonic() + 30
                    invalidate()
                    erp = {**self._erpnext.current(), "receiving_work": work}
            rows = work.get("arrivals", [])
            if not isinstance(rows, list):
                raise ValueError("Receiving arrival projection must be a list")
            activity = []
            for arrival in rows:
                for match in arrival.get("barcode_matches", []):
                    activity.append(
                        {
                            "source_id": "receiving-scan",
                            "provider": "ERPNext barcode lookup",
                            "record_id": match["evidence_id"],
                            "status": "MATCHED",
                            "label": "Goods identified",
                            "detail": f"{match['item_code']} · {match['unit_price']} "
                            f"{match['currency']}/{match['uom']} · {match['purchase_order']}. "
                            "Identity lookup only; stock unchanged.",
                            "occurred_at": match["observed_at"],
                        }
                    )
                for index, event in enumerate(arrival["events"]):
                    activity.append(
                        {
                            "source_id": "receiving-photo",
                            "provider": "Photo receiving",
                            "record_id": f"{arrival['capture_id']}:{index}",
                            "label": event["status"].replace("_", " ").capitalize(),
                            "status": event["status"],
                            "detail": event["detail"],
                            "occurred_at": event["at"],
                        }
                    )
                for event in arrival["scans"]["events"]:
                    activity.append(
                        {
                            "source_id": "receiving-scan",
                            "provider": event["origin"],
                            "record_id": event["source_event_id"],
                            "status": "OBSERVED",
                            "label": "Handling unit scanned",
                            "detail": event["handling_unit_id"]
                            + (
                                f" · {event['observation_method']} · {event['barcode_format']}"
                                if event.get("observation_method")
                                else ""
                            ),
                            "occurred_at": event["occurred_at"],
                        }
                    )
                for conflict in arrival["scans"].get("conflicts", []):
                    activity.append(
                        {
                            "source_id": "receiving-scan",
                            "provider": "Receiving input validation",
                            "record_id": conflict["conflict_id"],
                            "status": "CONFLICT",
                            "label": "Scan conflict needs review",
                            "detail": f"Conflicting content for scan "
                            f"{conflict['source_event_id']}; affected quantity is unknown.",
                            "occurred_at": conflict["detected_at"],
                        }
                    )
            self._admit_source_activity(activity)
        metrics = (
            self._live_flow_metrics(erp)
            if self._source_freshness(erp)["status"] == "CURRENT"
            else None
        )
        self._admit_source_activity(erp.get("activity"), metrics=metrics)
        self._admit_source_activity(saas.get("activity"))
        if self._history is not None and not operational_metrics.receiving_receipt_conflicts(erp):
            self._history.record(
                {"case_id": "M20-ERP-LIVE", "source_id": "erpnext-missing20", **erp},
                metrics or {},
            )
        return erp, saas

    def operational_history(
        self, *, limit: int = 96, since: str | None = None
    ) -> dict[str, object]:
        """Read the current case's retained observations, never another tenant's history."""
        with self._lock:
            erp, _ = self._read_all()
            case_id = self._text(erp.get("case_id"), "M20-ERP-LIVE")
            if self._history is None:
                return {"case_id": case_id, "points": [], "status": "NOT_CONFIGURED"}
            return self._history.query(case_id, limit=limit, since=since)

    def _projection(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        source_freshness = self._source_freshness(erp)
        source_current = source_freshness["status"] == "CURRENT"
        correlation = self._correlation(erp, saas)
        if (
            self._model_gate.get("requires_run_id") is True
            and self._text(self._model_gate.get("status")) == "VALIDATED"
            and self._text(self._agent_run.get("state")) == "PLAN_READY"
            and (
                not source_current
                or correlation["status"] != "FULLY_CORRELATED"
                or self._text(self._model_gate.get("evidence_digest"))
                != self._model_evidence_digest(erp, saas)
            )
        ):
            self._block_model_plan(
                "STALE_EVIDENCE",
                "Source evidence changed or is unavailable. Investigate again before approval.",
            )
            self._append(
                "agent.plan.invalidated",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status="BLOCKED",
                label="Recovery plan needs fresh evidence",
                detail=self._text(self._diagnosis.get("summary")),
                record_id=self._text(self._agent_run.get("run_id")),
            )
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
        systems = self._systems(erp, saas)
        plan = self._plan(erp, saas)
        projection: dict[str, object] = {
            "schema_version": AGENT_PLATFORM_SCHEMA_VERSION,
            "received_at": self._now(),
            "source_freshness": source_freshness,
            "document_lifecycle": erp.get("document_lifecycle", {}),
            "purchase_scope": erp.get("purchase_scope"),
            "mode": {
                "read_only": self._executor is None,
                "provider_writes": "DEMO_GUARDED" if self._executor else "DISABLED",
                "execution_available": self._executor is not None,
                "provenance": "live-read",
            },
            "case_id": self._text(erp.get("case_id"), "M20-ERP-LIVE"),
            "receiving_work": erp.get("receiving_work"),
            "case_projection": live_case,
            # Compatibility alias for the current browser; provenance remains
            # explicitly live and never claims a synthetic fixture is authoritative.
            "demo_case": live_case,
            "business_impact": self._business_impact(erp),
            "value_proof": self._value_proof(erp),
            "correlation": correlation,
            "integration_receipt": integration_receipt,
            "systems": systems,
            "agent_run": agent_run,
            "plan": plan,
            "evidence_constellation": self._constellation(erp, saas),
            "evidence_catalog": self._evidence_catalog(erp, saas),
            "diagnosis": diagnosis,
            "judge_proof": {
                "evidence_records": len(evidence_ids),
                "source_checks": source_checks,
                "ledger_events": self._sequence,
                "runtime": self._text(strands.get("mode"), "Strands SDK"),
                "provider": dict(self._mapping(strands.get("provider"))),
                "verified": external_recovery and not value_pending,
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
            "operational_history": (
                self._history.query(self._text(erp.get("case_id"), "M20-ERP-LIVE"), limit=32)
                if self._history is not None
                else None
            ),
            "conversation": [
                self._validate_stored_conversation_turn(dict(turn)) for turn in self._conversation
            ],
            **dialogue_intent.public_state(
                self._dialogue_intent,
                self._text(erp.get("case_id"), "M20-ERP-LIVE"),
                runtime_instance_id=self._runtime_instance_id,
            ),
            "latest_sequence": self._sequence,
        }
        if not source_current:
            erp_status = self._text(source_freshness["erp_status"])
            if erp_status == "CONNECTED":
                erp_status = "UNAVAILABLE"
            for system in systems:
                if system["id"] == "erpnext":
                    system.update({"status": erp_status, "label": "ERP evidence unavailable"})
            for step in plan:
                if step["id"] in {"read_erp", "guarded_plan"}:
                    step["status"] = "BLOCKED"
            agent_run["freshness"] = "HISTORICAL"
            diagnosis["freshness"] = "HISTORICAL"
            execution = dict(self._mapping(projection["execution"]))
            execution.update(
                {
                    "available": False,
                    "fresh_read_verified": False,
                    "freshness": "UNAVAILABLE",
                    "detail": "Current ERP evidence is unavailable; prior execution is historical.",
                }
            )
            projection["execution"] = execution
            projection["human_review"] = {
                "status": "SOURCE_UNAVAILABLE",
                "required": False,
                "action": "NONE",
                "reason": "Current ERP evidence is unavailable. Retry the source read.",
                "can_stop": False,
            }
            constellation = dict(self._mapping(projection["evidence_constellation"]))
            nodes = constellation.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict) and node.get("id") == "erpnext":
                        node["status"] = erp_status
            constellation["conclusion"] = {
                "label": "ERP EVIDENCE UNAVAILABLE",
                "status": "UNAVAILABLE",
                "confidence": 0.0,
                "latest_sequence": self._sequence,
            }
            projection["evidence_constellation"] = constellation
            projection["resolution_packet"] = (
                {**self._resolution_packet, "freshness": "HISTORICAL", "fresh_read_verified": False}
                if self._resolution_packet
                else None
            )
        return projection

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
            erp, saas = self._read_all(fresh=True)
            correlation = self._correlation(erp, saas)
            if (
                self._executor is None
                or self._source_freshness(erp)["status"] != "CURRENT"
                or not clean_manager
                or self._text(self._agent_run.get("state")) != "PLAN_READY"
                or correlation["status"] != "FULLY_CORRELATED"
                or (
                    self._text(self._model_gate.get("status")) == "VALIDATED"
                    and self._text(self._model_gate.get("evidence_digest"))
                    != self._model_evidence_digest(erp, saas)
                )
            ):
                raise ValueError("manager approval requires an executor and a fresh verified plan")
            approval_id = f"m20-approval-{self._run_number:04d}"
            tuple_values = correlation.get("tuple")
            binding = {
                "case_tuple": dict(tuple_values) if isinstance(tuple_values, Mapping) else {},
                "erp_sequence": self._int_or_zero(erp.get("sequence")),
                "saas_sequence": self._int_or_zero(saas.get("sequence")),
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
            erp, saas = self._read_all(fresh=True)
            correlation = self._correlation(erp, saas)
            tuple_values = correlation.get("tuple")
            current_binding = {
                "case_tuple": dict(tuple_values) if isinstance(tuple_values, Mapping) else {},
                "erp_sequence": self._int_or_zero(erp.get("sequence")),
                "saas_sequence": self._int_or_zero(saas.get("sequence")),
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
                or self._source_freshness(erp)["status"] != "CURRENT"
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
                    sales_order_quantity=self._float_or_zero(sales_order.get("quantity")),
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
            erp, saas = self._read_all(fresh=True)
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

    def record_conversation_tool_progress(
        self, tool: str, phase: str, conversation_id: str
    ) -> None:
        """Record actual chat hooks without starting a diagnosis or granting write authority."""
        if phase not in {"started", "succeeded", "failed"}:
            return
        with self._lock:
            self._append(
                f"conversation.tool.{phase}",
                source_id="agent-platform",
                provider="Strands Agent",
                status=phase.upper(),
                label=f"Agent {'reading' if phase == 'started' else phase} · {tool}",
                detail="Read-only conversation tool activity.",
                record_id=conversation_id,
            )

    def record_human_request(
        self, question: str, case_id: str, *, new_conversation: bool = False
    ) -> dict[str, object]:
        with self._lock:
            self._dialogue_intent = dialogue_intent.record_request(
                self._dialogue_intent,
                case_id,
                question,
                self._now(),
                runtime_instance_id=self._runtime_instance_id,
                new_conversation=new_conversation,
            )
            self._persist_state()
            return dialogue_intent.public_state(
                self._dialogue_intent,
                case_id,
                runtime_instance_id=self._runtime_instance_id,
            )

    def record_conversation_turn(
        self,
        question: str,
        answer: str,
        advisory: Mapping[str, object],
        *,
        expected_case_id: str = "",
        expected_conversation_id: str = "",
    ) -> dict[str, object]:
        """Persist bounded, case-scoped dialogue without granting write authority."""

        with self._lock:
            if expected_case_id or expected_conversation_id:
                erp, saas = self._read_all()
                current_case_id = self._text(erp.get("case_id"), "M20-ERP-LIVE")
                if (
                    current_case_id != expected_case_id
                    or self._dialogue_intent.get("case_id") != expected_case_id
                    or self._dialogue_intent.get("conversation_id") != expected_conversation_id
                ):
                    return self._projection(erp, saas)
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
            reference_group = advisory.get("dialogue_reference_group")
            if (
                isinstance(reference_group, Mapping)
                and reference_group.get("case_id") == self._dialogue_intent.get("case_id")
                and reference_group.get("provenance") == "runtime_validated"
            ):
                raw_receipt_ids = reference_group.get("receipt_ids", [])
                receipt_ids = (
                    [str(receipt_id) for receipt_id in raw_receipt_ids]
                    if isinstance(raw_receipt_ids, (list, tuple))
                    else []
                )
                self._dialogue_intent = dialogue_intent.record_reference_group(
                    self._dialogue_intent,
                    case_id=str(reference_group["case_id"]),
                    question=question,
                    receipt_ids=receipt_ids,
                    validated=True,
                    at=self._now(),
                    runtime_instance_id=self._runtime_instance_id,
                )
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
                    "latency_ms": self._int_or_zero(advisory.get("latency_ms")),
                    "context_turns": self._int_or_zero(advisory.get("context_turns")),
                    "created_at": self._now(),
                    "attachments": advisory.get("attachments", []),
                    "receiving_references": advisory.get("receiving_references", {}),
                    "follow_up_questions": advisory.get("follow_up_questions", []),
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
            erp, saas = self._read_all(fresh=True)
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

    def automatic_investigation_observation(self, *, fresh: bool = True) -> dict[str, object]:
        """Trigger on proved exceptions, never on an order merely arriving in batches."""
        with self._lock:
            erp, saas = self._read_all(fresh=fresh)
            metrics = self._live_flow_metrics(erp)
            digest = self._model_evidence_digest(erp, saas)
            status = "WATCHING"
            if self._source_freshness(erp)["status"] != "CURRENT":
                status = "WAITING_SOURCE"
            elif self._agent_run.get("state") == "STOPPED":
                status = "STOPPED"
            elif (
                self._model_gate.get("status") == "PENDING"
                or self._agent_run.get("state") == "VERIFYING"
            ):
                status = "BUSY"
            elif (
                self._model_gate.get("evidence_digest") == digest
                and self._model_gate.get("status") == "VALIDATED"
            ):
                status = (
                    "WATCHING" if self._agent_run.get("state") == "VERIFIED" else "AWAITING_REVIEW"
                )
            elif (
                self._float_or_zero(metrics.get("quality_hold")) > 0
                or self._float_or_zero(metrics.get("receipt_unresolved")) > 0
                or metrics.get("invoice_held") is True
            ):
                status = "READY"
            return {"case_id": self._text(erp.get("case_id")), "digest": digest, "status": status}

    def claim_changed_diagnosis(self, case_id: str, digest: str) -> tuple[dict[str, object], bool]:
        with self._lock:
            observed = self.automatic_investigation_observation(fresh=False)
            if observed != {"case_id": case_id, "digest": digest, "status": "READY"}:
                return {}, False
            projection, started = self.claim_diagnosis()
            if started:
                self._automatic_run_id = self._text(self._agent_run.get("run_id"))
            return projection, started

    def cancel_automatic_investigation(self) -> None:
        """Cancel the owned model run locally, even while a provider is unavailable."""
        with self._lock:
            if self.agent_run_is_active(getattr(self, "_automatic_run_id", "")):
                self._agent_run.update({"state": "STOPPED", "active_step": ""})
                self._model_gate["status"] = "STOPPED"
                self._approval = {}
                self._diagnosis.update(
                    {"status": "STOPPED", "summary": "Automatic investigation paused."}
                )
                self._append(
                    "human.automation.paused",
                    source_id="agent-platform",
                    provider="Operator",
                    status="STOPPED",
                    label="Automatic investigation paused",
                    detail="No new provider effect was authorized.",
                    record_id=getattr(self, "_automatic_run_id", ""),
                )

    def finish_automatic_investigation(self, advisory: Mapping[str, object], *, run_id: str) -> str:
        """Record the accepted control outcome, not the model's self-reported success."""
        with self._lock:
            if not self.agent_run_is_active(run_id):
                return "CANCELLED"
            self.record_live_strands_investigation(advisory, run_id=run_id)
            return self._text(self._agent_run.get("state"), "BLOCKED")

    def resume_automatic_investigation(self) -> None:
        with self._lock:
            if self._agent_run.get("state") == "STOPPED":
                self._agent_run.update({"state": "IDLE", "active_step": ""})
                self._model_gate = {}
                self._diagnosis.update(
                    {"status": "IDLE", "summary": "Watching for source exceptions."}
                )
                self._persist_state()

    def stop(self) -> dict[str, object]:
        """Let the operator pause an unclosed investigation without losing evidence."""

        with self._lock:
            if self._text(self._agent_run.get("state")) in {"IDLE", "VERIFIED", "STOPPED"}:
                raise ValueError("only an active investigation can be paused")
            erp, saas = self._read_all()
            run_id = self._text(self._agent_run.get("run_id"))
            self._agent_run.update({"state": "STOPPED", "active_step": ""})
            self._model_gate["status"] = "STOPPED"
            self._approval = {}
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

    def diagnose(self, *, release: bool = True) -> dict[str, object]:
        """Read a deterministic candidate; HTTP uses ``claim_diagnosis`` to gate release.

        ``release=True`` preserves the explicitly offline coordinator contract.
        Live requests must wait for the matching model result before approval.
        """

        with self._lock:
            self._approval = {}
            self._execution = {}
            self._resolution_packet = {}
            self._conversation = []
            self._run_number += 1
            run_id = f"agent-run-{self._run_number:04d}"
            self._model_gate = {
                "run_id": run_id,
                "status": "OFFLINE" if release else "PENDING",
                "requires_run_id": not release,
            }
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
            rejected = self._float_or_zero(live_metrics["quality_hold"])
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
                    f"still has {self._float_or_zero(observed.get('booked_revenue')):,.0f} "
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
            self._model_gate.update(
                {
                    "candidate_state": run_state,
                    "evidence_digest": self._model_evidence_digest(erp, saas),
                }
            )
            if not release:
                run_state = "REASONING"
                summary = "The agent is investigating source evidence. No recovery plan is ready."
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
                    "active_step": "" if release else "model_investigation",
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
                "agent.diagnosis.completed" if release else "agent.strands.pending",
                source_id="agent-platform",
                provider="Missing 20 Agent",
                status=run_state,
                label="Diagnosis completed" if release else "Agent investigation in progress",
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
