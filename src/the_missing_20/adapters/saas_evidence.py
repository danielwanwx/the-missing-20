"""Read-only, correlation-scoped evidence from the demo's SaaS systems.

This module is deliberately a *reader*.  It gives the local dashboard a small,
truthful projection of real Airtable, Celigo, Jira, and Slack records without
putting provider credentials or raw third-party payloads in browser responses.
Writes and account provisioning remain separate, explicit operations.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from the_missing_20.adapters.erpnext_source import _read_env_file

SAAS_EVIDENCE_SCHEMA_VERSION = "missing20-saas-evidence/v1"
DEFAULT_CORRELATION_ID = "M20-ECU-2026-00011-LOT-A"
DEFAULT_AIRTABLE_TABLE = "Supplier Quality Registry"


@dataclass(frozen=True, slots=True)
class SaaSEvidenceConfig:
    """Private settings for optional, narrow source reads."""

    correlation_id: str
    airtable_token: str = ""
    airtable_base_id: str = ""
    airtable_table: str = DEFAULT_AIRTABLE_TABLE
    airtable_receipt_table: str = ""
    celigo_evidence_url: str = ""
    celigo_api_token: str = ""
    celigo_flow_id: str = ""
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_cloud_id: str = ""
    slack_bot_token: str = ""
    slack_channel_id: str = ""


class SaaSEvidenceSource:
    """Return a bounded, display-safe multi-SaaS investigation projection."""

    def __init__(
        self,
        config: SaaSEvidenceConfig,
        *,
        transport: Callable[[Request, float], bytes] | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._config = config
        self._transport = transport or self._default_transport
        self._timeout_seconds = timeout_seconds
        self._sequence = 0

    @classmethod
    def from_environment(cls, *, repository_root: Path) -> SaaSEvidenceSource:
        dotenv = _read_env_file(repository_root / ".env")
        values = {**dotenv, **os.environ}
        return cls(
            SaaSEvidenceConfig(
                correlation_id=(
                    values.get(
                        "MISSING20_QUALITY_RELEASE_CORRELATION_ID", DEFAULT_CORRELATION_ID
                    ).strip()
                    or DEFAULT_CORRELATION_ID
                ),
                airtable_token=(
                    values.get("AIRTABLE_DEMO_OPERATOR_TOKEN", "").strip()
                    or values.get("AIRTABLE_API_TOKEN", "").strip()
                ),
                airtable_base_id=values.get("AIRTABLE_BASE_ID", "").strip(),
                airtable_table=(
                    values.get("AIRTABLE_QUALITY_RELEASE_TABLE", DEFAULT_AIRTABLE_TABLE).strip()
                    or DEFAULT_AIRTABLE_TABLE
                ),
                airtable_receipt_table=values.get("AIRTABLE_INTEGRATION_RECEIPT_TABLE", "").strip(),
                celigo_evidence_url=values.get("CELIGO_EVIDENCE_URL", "").strip(),
                celigo_api_token=values.get("CELIGO_API_TOKEN", "").strip(),
                celigo_flow_id=values.get("CELIGO_FLOW_ID", "").strip(),
                jira_base_url=values.get("JIRA_BASE_URL", "").rstrip("/"),
                jira_email=values.get("JIRA_API_EMAIL", "").strip(),
                jira_api_token=values.get("JIRA_API_TOKEN", "").strip(),
                jira_project_key=values.get("JIRA_CAPA_PROJECT_KEY", "").strip(),
                jira_cloud_id=values.get("JIRA_CLOUD_ID", "").strip(),
                slack_bot_token=values.get("SLACK_BOT_TOKEN", "").strip(),
                slack_channel_id=values.get("SLACK_INCIDENT_CHANNEL_ID", "").strip(),
            )
        )

    @staticmethod
    def _default_transport(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured HTTPS API
            return bytes(response.read())

    def _get_payload(self, url: str, headers: Mapping[str, str]) -> Any:
        request = Request(
            url,
            headers={
                **headers,
                "Accept": "application/json",
                "User-Agent": "TheMissing20/0.1 read-only SaaS evidence adapter",
            },
        )
        return json.loads(self._transport(request, self._timeout_seconds).decode("utf-8"))

    def _get_json(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        payload = self._get_payload(url, headers)
        if not isinstance(payload, Mapping):
            raise ValueError("SaaS provider returned an invalid JSON envelope")
        return payload

    @staticmethod
    def _record(
        source_id: str,
        provider: str,
        status: str,
        label: str,
        detail: str,
        now: datetime,
        *,
        record_id: str = "",
        evidence_kind: str = "",
        correlation: Mapping[str, object] | None = None,
        erp_acknowledged: bool | None = None,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "source_id": source_id,
            "provider": provider,
            "status": status,
            "record_id": record_id,
            "occurred_at": now.isoformat(),
            "label": label,
            "detail": detail,
            "read_only": True,
        }
        if evidence_kind:
            record["evidence_kind"] = evidence_kind
        if correlation is not None:
            record["correlation"] = dict(correlation)
        if erp_acknowledged is not None:
            record["erp_acknowledged"] = erp_acknowledged
        return record

    @staticmethod
    def _correlation_fields(fields: Mapping[str, object]) -> dict[str, object]:
        """Return the fixed, display-safe release tuple and nothing else."""

        field_names = {
            "case_id": "Release Correlation ID",
            "purchase_order": "Purchase Order",
            "purchase_receipt": "Purchase Receipt",
            "purchase_invoice": "Purchase Invoice",
            "supplier_lot": "Supplier Lot",
            "certificate_id": "Certificate ID",
            "quantity": "Approved Quantity",
            "evidence_revision": "Evidence Revision",
        }
        return {
            key: fields.get(field_name, "")
            for key, field_name in field_names.items()
        }

    @staticmethod
    def _run_correlation_fields(payload: Mapping[str, object]) -> dict[str, object]:
        """Normalize only known direct-run tuple aliases from Celigo's receipt."""

        aliases = {
            "case_id": ("correlationId", "correlation_id", "Release Correlation ID"),
            "purchase_order": ("purchaseOrder", "purchase_order", "Purchase Order"),
            "purchase_receipt": ("purchaseReceipt", "purchase_receipt", "Purchase Receipt"),
            "purchase_invoice": ("purchaseInvoice", "purchase_invoice", "Purchase Invoice"),
            "supplier_lot": ("supplierLot", "supplier_lot", "Supplier Lot"),
            "certificate_id": ("certificateId", "certificate_id", "Certificate ID"),
            "quantity": ("quantity", "approvedQuantity", "Approved Quantity"),
            "evidence_revision": ("evidenceRevision", "evidence_revision", "Evidence Revision"),
        }
        return {
            key: next(
                (
                    payload.get(alias, "")
                    for alias in names
                    if payload.get(alias) is not None and str(payload.get(alias)).strip()
                ),
                "",
            )
            for key, names in aliases.items()
        }

    def _airtable(self, now: datetime) -> dict[str, object]:
        config = self._config
        if not (config.airtable_token and config.airtable_base_id):
            return self._record(
                "airtable-quality-registry",
                "Airtable · Supplier Quality Registry",
                "NOT_CONFIGURED",
                "Registry read unavailable",
                "Airtable observer credential has not been configured.",
                now,
            )
        query = urlencode({"maxRecords": "25"})
        url = (
            f"https://api.airtable.com/v0/{quote(config.airtable_base_id, safe='')}/"
            f"{quote(config.airtable_table, safe='')}?{query}"
        )
        try:
            payload = self._get_json(url, {"Authorization": f"Bearer {config.airtable_token}"})
            records = payload.get("records")
            if not isinstance(records, list):
                raise ValueError("Airtable returned no records")
            matching = next(
                (
                    row
                    for row in records
                    if isinstance(row, Mapping)
                    and isinstance(row.get("fields"), Mapping)
                    and str(row["fields"].get("Release Correlation ID", ""))
                    == config.correlation_id
                ),
                None,
            )
            if not isinstance(matching, Mapping) or not isinstance(matching.get("fields"), Mapping):
                return self._record(
                    "airtable-quality-registry",
                    "Airtable · Supplier Quality Registry",
                    "NOT_FOUND",
                    "Registry correlation not found",
                    f"No release record matched {config.correlation_id}.",
                    now,
                )
            fields = matching["fields"]
            disposition = str(fields.get("Disposition", "UNKNOWN"))
            quantity = fields.get("Approved Quantity", "unknown")
            supplier_lot = str(fields.get("Supplier Lot", "unrecorded"))
            return self._record(
                "airtable-quality-registry",
                "Airtable · Supplier Quality Registry",
                "VERIFIED" if disposition.upper() == "APPROVED" else "HELD",
                f"Registry read · {disposition}",
                f"Lot {supplier_lot} · {quantity} approved · correlation matched",
                now,
                record_id=str(matching.get("id", "")),
                evidence_kind="REGISTRY",
                correlation=self._correlation_fields(fields),
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._record(
                "airtable-quality-registry",
                "Airtable · Supplier Quality Registry",
                "DEGRADED",
                "Registry read degraded",
                "Airtable did not return a usable release record.",
                now,
            )

    def _celigo(self, now: datetime) -> dict[str, object]:
        config = self._config
        receipt = self._celigo_receipt_registry(now)
        if receipt is not None:
            return receipt
        if not (config.celigo_evidence_url and config.celigo_api_token):
            return self._record(
                "celigo-quality-release",
                "Celigo · quality.release",
                "NOT_CONFIGURED",
                "Integration-run read unavailable",
                "Celigo evidence endpoint has not been configured.",
                now,
            )
        return self._celigo_direct(now)

    def _celigo_direct(self, now: datetime) -> dict[str, object]:
        config = self._config
        try:
            payload = self._get_payload(
                config.celigo_evidence_url,
                {"Authorization": f"Bearer {config.celigo_api_token}"},
            )
            if isinstance(payload, Mapping) and (
                "runId" in payload or "erpAcknowledged" in payload
            ):
                run_id = str(payload.get("id") or payload.get("runId") or "")
                status = str(payload.get("status") or "UNKNOWN").upper()
                acknowledged = bool(payload.get("erpAcknowledged"))
                return self._record(
                    "celigo-quality-release",
                    "Celigo · quality.release",
                    "VERIFIED" if status in {"SUCCESS", "COMPLETED"} and acknowledged else "FAILED",
                    f"Integration run · {status}",
                    (
                        "ERP acknowledgement confirmed"
                        if acknowledged
                        else "No ERP acknowledgement recorded"
                    ),
                    now,
                    record_id=run_id,
                    evidence_kind="RUN_RECEIPT",
                    correlation=self._run_correlation_fields(payload),
                    erp_acknowledged=acknowledged,
                )
            if isinstance(payload, Sequence) and not isinstance(payload, str):
                flows_raw = payload
            elif isinstance(payload, Mapping):
                flows_raw = payload.get("items", [])
            else:
                flows_raw = []
            flows = [flow for flow in flows_raw if isinstance(flow, Mapping)]
            if not flows:
                raise ValueError("Celigo did not return a flow list")
            selected = next(
                (
                    flow
                    for flow in flows
                    if config.celigo_flow_id and str(flow.get("_id", "")) == config.celigo_flow_id
                ),
                flows[0],
            )
            flow_id = str(selected.get("_id", ""))
            name = " ".join(str(selected.get("name", "Unnamed flow")).split())[:120]
            disabled = bool(selected.get("disabled"))
            return self._record(
                "celigo-quality-release",
                "Celigo · integration control plane",
                "HELD" if disabled else "VERIFIED",
                f"Flow control-plane read · {'DISABLED' if disabled else 'ENABLED'}",
                f"{len(flows)} account flows visible · {name}",
                now,
                record_id=flow_id,
                evidence_kind="CONTROL_PLANE",
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._record(
                "celigo-quality-release",
                "Celigo · quality.release",
                "DEGRADED",
                "Integration-run read degraded",
                "Celigo did not return a usable run record.",
                now,
            )

    def _celigo_receipt_registry(self, now: datetime) -> dict[str, object] | None:
        """Read a Celigo-written receipt from the dedicated demo registry.

        The table is deliberately separate from the human-maintained quality
        registry.  A row is useful only after the flow has written its Celigo flow
        flow identifier, the flow reports success, and the payload attests to the
        fresh ERP read.  Until then it remains a pending *post-execution*
        verification artifact and can never authorize a release.
        """

        config = self._config
        if not (
            config.airtable_token
            and config.airtable_base_id
            and config.airtable_receipt_table
        ):
            return None
        query = urlencode({"maxRecords": "25"})
        url = (
            f"https://api.airtable.com/v0/{quote(config.airtable_base_id, safe='')}/"
            f"{quote(config.airtable_receipt_table, safe='')}?{query}"
        )
        try:
            payload = self._get_json(url, {"Authorization": f"Bearer {config.airtable_token}"})
            records = payload.get("records")
            if not isinstance(records, list):
                raise ValueError("Airtable returned no receipt records")
            matching = next(
                (
                    row
                    for row in records
                    if isinstance(row, Mapping)
                    and isinstance(row.get("fields"), Mapping)
                    and str(row["fields"].get("Case ID", "")) == config.correlation_id
                ),
                None,
            )
            if not isinstance(matching, Mapping) or not isinstance(matching.get("fields"), Mapping):
                return self._record(
                    "celigo-quality-release",
                    "Celigo · quality.release",
                    "PENDING",
                    "Celigo run receipt pending",
                    "No post-execution integration receipt has been written for this M20 case.",
                    now,
                    evidence_kind="RUN_RECEIPT_PENDING",
                )
            fields = matching["fields"]
            raw_status = str(fields.get("Status", "PENDING")).upper()
            flow_id = str(fields.get("Celigo Flow ID", "")).strip()
            acknowledged = bool(fields.get("ERP Acknowledged"))
            correlation = {
                "case_id": fields.get("Case ID", ""),
                "purchase_order": fields.get("Purchase Order", ""),
                "purchase_receipt": fields.get("Purchase Receipt", ""),
                "purchase_invoice": fields.get("Purchase Invoice", ""),
                "supplier_lot": fields.get("Supplier Lot", ""),
                "certificate_id": fields.get("Certificate ID", ""),
                "quantity": fields.get("Quantity", ""),
                "evidence_revision": fields.get("Evidence Revision", ""),
            }
            verified = raw_status == "VERIFIED" and bool(flow_id) and acknowledged
            return self._record(
                "celigo-quality-release",
                "Celigo · quality.release",
                "VERIFIED" if verified else ("FAILED" if raw_status == "FAILED" else "PENDING"),
                f"Celigo run receipt · {raw_status}",
                (
                    "ERP acknowledgement and the Celigo flow ID are recorded."
                    if verified
                    else "Waiting for the Celigo flow to record a successful ERP acknowledgement."
                ),
                now,
                record_id=flow_id or str(matching.get("id", "")),
                evidence_kind="RUN_RECEIPT" if verified else "RUN_RECEIPT_PENDING",
                correlation=correlation,
                erp_acknowledged=acknowledged,
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._record(
                "celigo-quality-release",
                "Celigo · quality.release",
                "DEGRADED",
                "Celigo receipt read degraded",
                "The dedicated Celigo run-receipt registry could not be read.",
                now,
            )

    def _jira(self, now: datetime) -> dict[str, object]:
        config = self._config
        has_gateway_config = bool(config.jira_cloud_id and config.jira_api_token)
        has_legacy_config = bool(
            config.jira_base_url and config.jira_email and config.jira_api_token
        )
        if not (config.jira_project_key and (has_gateway_config or has_legacy_config)):
            return self._record(
                "jira-capa",
                "Jira · CAPA",
                "NOT_CONFIGURED",
                "CAPA read unavailable",
                "Jira observer credential or CAPA project has not been configured.",
                now,
            )
        if config.jira_cloud_id:
            try:
                cloud_id = str(UUID(config.jira_cloud_id))
            except ValueError:
                return self._record(
                    "jira-capa",
                    "Jira · CAPA",
                    "DEGRADED",
                    "CAPA read degraded",
                    "Jira cloud ID is invalid.",
                    now,
                )
            jira_url_prefix = f"https://api.atlassian.com/ex/jira/{cloud_id}"
            auth_header = f"Bearer {config.jira_api_token}"
        else:
            auth = base64.b64encode(
                f"{config.jira_email}:{config.jira_api_token}".encode()
            ).decode()
            jira_url_prefix = config.jira_base_url
            auth_header = f"Basic {auth}"
        jql = (
            f'project = "{config.jira_project_key}" '
            f'AND text ~ "{config.correlation_id}" ORDER BY updated DESC'
        )
        query = urlencode({"jql": jql, "maxResults": "1", "fields": "summary,status,updated"})
        url = f"{jira_url_prefix}/rest/api/3/search/jql?{query}"
        try:
            payload = self._get_json(url, {"Authorization": auth_header})
            issues = payload.get("issues")
            if not isinstance(issues, list) or not issues or not isinstance(issues[0], Mapping):
                return self._record(
                    "jira-capa",
                    "Jira · CAPA",
                    "NOT_FOUND",
                    "CAPA not found",
                    f"No CAPA matched {config.correlation_id}.",
                    now,
                )
            issue = issues[0]
            raw_fields = issue.get("fields")
            fields: Mapping[str, Any] = raw_fields if isinstance(raw_fields, Mapping) else {}
            status_value = fields.get("status")
            status_name = (
                str(status_value.get("name", "UNKNOWN"))
                if isinstance(status_value, Mapping)
                else "UNKNOWN"
            )
            return self._record(
                "jira-capa",
                "Jira · CAPA",
                "VERIFIED",
                f"CAPA read · {status_name}",
                str(fields.get("summary", "CAPA record")),
                now,
                record_id=str(issue.get("key", "")),
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._record(
                "jira-capa",
                "Jira · CAPA",
                "DEGRADED",
                "CAPA read degraded",
                "Jira did not return a usable CAPA record.",
                now,
            )

    def _slack(self, now: datetime) -> dict[str, object]:
        config = self._config
        if not (config.slack_bot_token and config.slack_channel_id):
            return self._record(
                "slack-quality-alerts",
                "Slack · #quality-release-incidents",
                "NOT_CONFIGURED",
                "Incident channel read unavailable",
                "Slack bot token or incident channel has not been configured.",
                now,
            )
        url = "https://slack.com/api/conversations.history?" + urlencode(
            {"channel": config.slack_channel_id, "limit": "20"}
        )
        try:
            payload = self._get_json(url, {"Authorization": f"Bearer {config.slack_bot_token}"})
            if payload.get("ok") is not True:
                raise ValueError("Slack returned a failed API envelope")
            messages = payload.get("messages")
            if not isinstance(messages, list):
                raise ValueError("Slack returned no messages")
            match = next(
                (
                    message
                    for message in messages
                    if isinstance(message, Mapping)
                    and config.correlation_id in str(message.get("text", ""))
                ),
                None,
            )
            if not isinstance(match, Mapping):
                return self._record(
                    "slack-quality-alerts",
                    "Slack · #quality-release-incidents",
                    "NOT_FOUND",
                    "Incident notification not found",
                    f"No incident alert matched {config.correlation_id}.",
                    now,
                )
            text = " ".join(str(match.get("text", "")).split())[:180]
            return self._record(
                "slack-quality-alerts",
                "Slack · #quality-release-incidents",
                "VERIFIED",
                "Incident notification read",
                text,
                now,
                record_id=str(match.get("ts", "")),
            )
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self._record(
                "slack-quality-alerts",
                "Slack · #quality-release-incidents",
                "DEGRADED",
                "Incident channel read degraded",
                "Slack did not return a usable incident notification.",
                now,
            )

    def current(self) -> dict[str, object]:
        """Return only display-safe, source-attributed evidence rows."""

        self._sequence += 1
        now = datetime.now(UTC)
        sources = [self._airtable(now), self._celigo(now), self._jira(now), self._slack(now)]
        configured = [source for source in sources if source["status"] != "NOT_CONFIGURED"]
        connected = [source for source in configured if source["status"] not in {"DEGRADED"}]
        return {
            "schema_version": SAAS_EVIDENCE_SCHEMA_VERSION,
            "correlation_id": self._config.correlation_id,
            "sequence": self._sequence,
            "received_at": now.isoformat(),
            "read_only": True,
            "status": "CONNECTED"
            if configured and len(connected) == len(configured)
            else ("DEGRADED" if configured else "NOT_CONFIGURED"),
            "sources": sources,
            "activity": sources,
        }
