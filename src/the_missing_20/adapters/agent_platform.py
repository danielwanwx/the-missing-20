"""Read-only, evidence-bound coordination for the Agent Platform console.

This projection joins narrow ERPNext and SaaS reads without granting the web
application (or this coordinator) any provider mutation capability.  Its event
ledger is owned by the server, not by browser polling, so repeated reads cannot
be presented as newly-created provider activity.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
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
        self, erpnext: EvidenceReader, saas: EvidenceReader, *, executor: DemoExecutor | None = None
    ) -> None:
        self._erpnext = erpnext
        self._saas = saas
        self._executor = executor
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
            "summary": "No diagnosis has run. Provider writes are disabled.",
            "finding": "NOT_EVALUATED",
            "tool_calls": [],
        }
        self._approval: dict[str, object] = {}
        self._execution: dict[str, object] = {}

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
            "read_only": True,
        }
        self._events.append(event)
        return event

    def _admit_source_activity(self, rows: object) -> None:
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
            self._append(
                "provider.read.observed",
                source_id=self._text(record.get("source_id"), "unknown-source"),
                provider=self._text(record.get("provider"), "Unknown provider"),
                status=self._text(record.get("status"), "UNKNOWN"),
                label=self._text(record.get("label"), "Provider record read"),
                detail=self._text(record.get("detail")),
                record_id=self._text(record.get("record_id")),
            )
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

    @staticmethod
    def _source_rows(saas: Mapping[str, object]) -> list[Mapping[str, object]]:
        raw_rows = saas.get("sources")
        if not isinstance(raw_rows, list):
            return []
        return [cast(Mapping[str, object], row) for row in raw_rows if isinstance(row, Mapping)]

    @staticmethod
    def _source_by_id(
        saas: Mapping[str, object], source_id: str
    ) -> Mapping[str, object] | None:
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
        return [
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
            "evidence_revision": registry_values.get(
                "evidence_revision", "UNAVAILABLE_FROM_READS"
            ),
        }
        compared = ("case_id", "purchase_order", "purchase_receipt", "purchase_invoice", "quantity")
        missing = [
            key
            for key, value in tuple_values.items()
            if self._missing(value)
        ]
        missing.extend(
            key
            for key in compared
            if self._missing(registry_values.get(key))
            and key not in missing
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
            if key not in missing and not self._matches(received_values.get(key), expected_values.get(key))
        ]
        status = "VERIFIED" if not missing and not mismatched else "MISMATCHED_RECEIPT"
        return {
            "status": status,
            "record_id": self._text(receipt.get("record_id")),
            "missing_fields": missing,
            "mismatched_fields": mismatched,
        }

    def _plan(self, erp: Mapping[str, object], saas: Mapping[str, object]) -> list[dict[str, str]]:
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        erp_ready = self._text(erp.get("status")) == "CONNECTED"
        saas_ready = self._text(saas.get("status")) == "CONNECTED"
        complete = self._text(self._agent_run.get("state")) in {
            "PLAN_READY",
            "BLOCKED",
            "VERIFYING",
            "VERIFIED",
        }
        return [
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
                        if self._execution and self._text(self._execution.get("status")) == "VERIFYING"
                        else ("QUEUED" if not complete else "NOT_REQUIRED_YET")
                    )
                ),
            },
            {
                "id": "guarded_plan",
                "label": "Produce guarded recovery plan",
                "status": (
                    "DONE"
                    if self._text(self._agent_run.get("state")) in {"PLAN_READY", "VERIFYING", "VERIFIED"}
                    else ("BLOCKED" if complete else "QUEUED")
                ),
            },
        ]

    def _constellation(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        documents = self._documents_by_kind(erp)
        receipt = documents.get("purchase_receipt", {})
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        systems = {system["id"]: system for system in self._systems(erp, saas)}
        node_specs = (
            ("erpnext", "TOP", "OPERATIONAL"),
            ("airtable", "RIGHT", "REGISTRY"),
            ("celigo", "BOTTOM", "RUN RECEIPT"),
            ("jira_slack", "LEFT", "CONTEXT"),
        )
        nodes: list[dict[str, object]] = []
        for node_id, position, role in node_specs:
            if node_id == "jira_slack":
                status = "CONTEXT"
                label = "Jira + Slack"
                sequence = max(
                    self._source_sequences.get("jira-capa", 0),
                    self._source_sequences.get("slack-quality-alerts", 0),
                )
            else:
                system = systems.get(node_id, {})
                status = self._text(system.get("status"), "NOT_CONFIGURED")
                label = self._text(system.get("name"), node_id)
                sequence = self._source_sequences.get(
                    {
                        "erpnext": "erpnext-missing20",
                        "airtable": "airtable-quality-registry",
                        "celigo": "celigo-quality-release",
                    }[node_id],
                    0,
                )
                if (
                    node_id == "erpnext"
                    and self._text(receipt.get("status")) == "PARTIAL_QUALITY_HOLD"
                ):
                    status = "HOLD"
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
        hold_detected = self._text(receipt.get("status")) == "PARTIAL_QUALITY_HOLD"
        eligible = correlation["status"] == "FULLY_CORRELATED"
        verified = eligible and integration_receipt["status"] == "VERIFIED"
        confidence = 0.91 if hold_detected and verified else (0.82 if hold_detected and eligible else 0.0)
        conclusion_status = "BLOCKED" if not eligible else ("GUARDED" if hold_detected else "CLEAR")
        return {
            "nodes": nodes,
            "conclusion": {
                "label": "NO RELEASE" if conclusion_status == "BLOCKED" else "GUARDED PLAN",
                "status": conclusion_status,
                "confidence": confidence,
                "latest_sequence": self._sequence,
            },
            "integration_receipt": integration_receipt,
        }

    def _read_all(self) -> tuple[dict[str, object], dict[str, object]]:
        erp = self._erpnext.current()
        saas = self._saas.current()
        self._admit_source_activity(erp.get("activity"))
        self._admit_source_activity(saas.get("activity"))
        return erp, saas

    def _projection(
        self, erp: Mapping[str, object], saas: Mapping[str, object]
    ) -> dict[str, object]:
        correlation = self._correlation(erp, saas)
        integration_receipt = self._integration_receipt(saas, correlation)
        return {
            "schema_version": AGENT_PLATFORM_SCHEMA_VERSION,
            "received_at": self._now(),
            "mode": {
                "read_only": self._executor is None,
                "provider_writes": "DEMO_GUARDED" if self._executor else "DISABLED",
                "execution_available": self._executor is not None,
                "provenance": "live-read",
            },
            "correlation": correlation,
            "integration_receipt": integration_receipt,
            "systems": self._systems(erp, saas),
            "agent_run": dict(self._agent_run),
            "plan": self._plan(erp, saas),
            "evidence_constellation": self._constellation(erp, saas),
            "diagnosis": dict(self._diagnosis),
            "execution": self._execution_projection(),
            "activity": list(self._events[-80:]),
            "latest_sequence": self._sequence,
        }

    def _execution_projection(self) -> dict[str, object]:
        if self._executor is None:
            return {"available": False, "status": "WRITE_DISABLED", "detail": "External provider mutations are intentionally disabled in this demo build."}
        if self._execution:
            return dict(self._execution)
        if self._approval:
            return {"available": True, "status": "AUTHORIZED", "detail": "Manager approval is bound to the current guarded plan.", **self._approval}
        return {"available": self._text(self._agent_run.get("state")) == "PLAN_READY", "status": "AWAITING_MANAGER_APPROVAL", "detail": "Demo-only execution requires Manager approval after a verified plan."}

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
            self._approval = {"approval_id": approval_id, "manager_id": clean_manager}
            self._append("manager.approval.granted", source_id="agent-platform", provider="Manager", status="APPROVED", label="Guarded recovery approved", detail="Approval is bound to the current M20 case evidence.", record_id=approval_id)
            return self._projection(erp, saas)

    def execute(self, approval_id: str, idempotency_key: str) -> dict[str, object]:
        with self._lock:
            erp, saas = self._read_all()
            correlation = self._correlation(erp, saas)
            if (
                self._executor is None
                or approval_id != self._text(self._approval.get("approval_id"))
                or correlation["status"] != "FULLY_CORRELATED"
            ):
                raise ValueError("execution requires the current Manager approval and fully verified evidence")
            raw_values = correlation.get("tuple")
            values = dict(raw_values) if isinstance(raw_values, Mapping) else {}
            result = self._executor.execute(DemoReleasePlan(case_id=self._text(values.get("case_id")), purchase_receipt=self._text(values.get("purchase_receipt")), purchase_invoice=self._text(values.get("purchase_invoice")), quantity=float(values.get("quantity") or 0), idempotency_key=idempotency_key))
            erp_verified = bool(getattr(result, "verified", False))
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
                "erp_verified": erp_verified,
            }
            self._append("agent.execution.completed", source_id="agent-platform", provider="Missing 20 Agent", status=self._text(self._execution["status"]), label="Guarded ERP recovery completed", detail=self._text(self._execution["detail"]), record_id=self._text(self._execution.get("transfer_name")))
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
            if receipt["status"] != "VERIFIED":
                self._execution.update(
                    {
                        "available": False,
                        "status": "VERIFYING",
                        "detail": "ERPNext is verified; waiting for a tuple-matched Celigo run receipt.",
                    }
                )
                return self._projection(erp, saas)
            self._execution.update(
                {
                    "available": False,
                    "status": "VERIFIED",
                    "detail": "ERPNext recovery and the independent Celigo run receipt are verified.",
                    "celigo_receipt_id": self._text(receipt.get("record_id")),
                }
            )
            self._agent_run.update({"state": "VERIFIED", "active_step": "", "confidence": 0.96})
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

    def diagnose(self) -> dict[str, object]:
        """Run bounded diagnosis from the same provider reads, never a write."""

        with self._lock:
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
            receipt = docs.get("purchase_receipt", {})
            rejected = receipt.get("rejected", 0)
            quality_hold = self._text(receipt.get("status")) == "PARTIAL_QUALITY_HOLD"
            source_statuses = [
                self._text(erp.get("status")),
                *[self._text(row.get("status")) for row in self._source_rows(saas)],
            ]
            degraded = any(status in {"DEGRADED", "NOT_CONFIGURED"} for status in source_statuses)
            correlation = self._correlation(erp, saas)
            integration_receipt = self._integration_receipt(saas, correlation)
            tool_calls = [
                {"tool": "erpnext.read_case_documents", "status": self._text(erp.get("status"))},
                {"tool": "saas.read_correlated_records", "status": self._text(saas.get("status"))},
                {
                    "tool": "celigo.read_exact_run_receipt",
                    "status": self._text(integration_receipt.get("status")),
                },
            ]
            if self._text(erp.get("status")) != "CONNECTED":
                finding = "INCONCLUSIVE"
                summary = "ERPNext evidence is unavailable, so the agent cannot diagnose the case."
            elif quality_hold:
                finding = "QUALITY_HOLD_DETECTED"
                summary = (
                    f"ERPNext reports {rejected:g} units in Quality Hold; no release is executed."
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
                summary += " A Celigo run receipt will be required only after guarded ERP execution."
            run_state = (
                "BLOCKED"
                if (
                    finding == "INCONCLUSIVE"
                    or correlation["status"] != "FULLY_CORRELATED"
                    or not quality_hold
                )
                else "PLAN_READY"
            )
            self._diagnosis = {
                "status": run_state,
                "finding": finding,
                "summary": summary,
                "tool_calls": tool_calls,
                "correlation_status": correlation["status"],
                "integration_receipt_status": integration_receipt["status"],
            }
            self._agent_run.update(
                {
                    "state": run_state,
                    "active_step": "",
                    "confidence": (
                        0.91
                        if finding == "QUALITY_HOLD_DETECTED"
                        and correlation["status"] == "FULLY_CORRELATED"
                        else (0.82 if finding == "QUALITY_HOLD_DETECTED" else 0.0)
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
            normalized = clean_question.lower()
            if any(term in normalized for term in ("release", "approve", "execute", "fix")):
                answer = (
                    "Release eligibility cannot be proven from the current partial correlation, "
                    "and external provider writes are disabled."
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
