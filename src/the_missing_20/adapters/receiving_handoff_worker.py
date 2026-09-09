"""Resume authorized demo receipt notifications after posted-stock verification."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from threading import Event, Thread
from typing import Any

from the_missing_20.adapters.photo_receiving import PhotoReceiving
from the_missing_20.adapters.receiving_destinations import (
    AirtableReceipt,
    CeligoSlackReceipt,
    ReceivingAPI,
)
from the_missing_20.adapters.receiving_handoff import (
    HandoffJournal,
    receipt_event,
    same_stock_effects,
)
from the_missing_20.adapters.receiving_jira import JiraReceivingReview
from the_missing_20.adapters.saas_evidence import SaaSEvidenceConfig


class ReceivingHandoffWorker:
    def __init__(
        self, receiving: PhotoReceiving, runtime: Path, config: SaaSEvidenceConfig
    ) -> None:
        if receiving.erp is None or receiving.arrivals is None:
            raise ValueError("Receipt handoffs require a configured receiving manifest")
        if receiving.erp.client._environment != "demo":
            raise ValueError("Receipt handoffs are restricted to the authorized demo environment")
        settings = json.loads((runtime / "handoff-config.json").read_text())
        if (
            settings["airtable_base_id"] != config.airtable_base_id
            or settings["slack_channel_id"] != config.slack_channel_id
        ):
            raise ValueError("Receiving handoff destination scope changed")
        self.receiving = receiving
        self.journal = HandoffJournal(runtime / "receiving-handoffs.sqlite3")
        api = ReceivingAPI(config)
        self.destinations: list[CeligoSlackReceipt | AirtableReceipt] = [
            CeligoSlackReceipt(api, settings["celigo_import_id"], settings["celigo_connection_id"]),
            AirtableReceipt(api, settings["airtable_table_id"]),
        ]
        self.jira = (
            JiraReceivingReview(api, self.journal, settings["jira_project_key"])
            if settings.get("jira_receiving_enabled") is True
            else None
        )
        self.closed = Event()
        self.thread: Thread | None = None

    def projection(self, state: dict[str, Any]) -> dict[str, Any]:
        routes = {target.route for target in self.destinations}
        return {
            **state,
            "handoffs": [
                row
                for row in self.journal.for_capture(state["id"])
                if row["route"] in routes
                or (self.jira and row["route"].startswith(self.jira.route + ":"))
            ],
        }

    def sources(self) -> list[dict[str, Any]]:
        """Retained destination readbacks, never release-policy evidence."""
        with self.journal.lock:
            rows = self.journal.db.execute(
                "SELECT payload, state FROM handoffs ORDER BY rowid"
            ).fetchall()
        sources = []
        routes = {target.route for target in self.destinations}
        for payload, raw in rows:
            event, state = json.loads(payload), json.loads(raw)
            jira = bool(self.jira and state["route"].startswith(self.jira.route + ":"))
            if (state["route"] not in routes and not jira) or event[
                "case_id"
            ] != self.receiving.arrivals.case_id:  # type: ignore[union-attr]
                continue
            celigo = state["route"].startswith("celigo-slack:")
            proof = state.get("evidence") or {}
            verified = state["status"] == "VERIFIED"
            if jira:
                sources.append(
                    {
                        "source_id": "jira-receiving",
                        "provider": "Jira",
                        "status": state["status"],
                        "record_id": proof.get("record_id", ""),
                        "url": proof.get("url", ""),
                        "case_id": event["case_id"],
                        "purchase_order": event["purchase_order"],
                        "arrival_id": event["arrival_id"],
                        "capture_id": event["capture_id"],
                        "operation": event["operation"],
                        "label": "Receiving review " + event["operation"],
                        "detail": proof.get("status", "Awaiting Jira verification"),
                        "last_failure": state.get("last_failure"),
                        "occurred_at": state["updated_at"],
                        "read_only": True,
                        "evidence_kind": "RECEIVING_REVIEW",
                        "readback_at": state["updated_at"] if verified else None,
                    }
                )
                continue
            sources.append(
                {
                    "source_id": "celigo-receiving" if celigo else "airtable-receiving",
                    "provider": "Slack via Celigo" if celigo else "Airtable",
                    "status": "VERIFIED" if verified else state["status"],
                    "record_id": proof.get("record_id", ""),
                    "url": proof.get("url", ""),
                    "label": "Receiving notification delivered"
                    if celigo and verified
                    else (
                        "Receiving ledger synced" if verified else "Receipt synchronization pending"
                    ),
                    "detail": f"{event['receipt']} · {event['quantity']:g} {event['uom']} · "
                    + (
                        "Destination record reread verified."
                        if verified
                        else "Awaiting destination verification."
                    ),
                    "occurred_at": state["updated_at"],
                    "read_only": True,
                    "evidence_kind": "RECEIPT_NOTIFICATION",
                    "case_id": event["case_id"],
                    "purchase_order": event["purchase_order"],
                    "readback_at": state["updated_at"] if verified else None,
                }
            )
        return sources

    def tick(self) -> None:
        for offset in range(0, 200, 50):
            states = self.receiving.list_captures(limit=50, offset=offset)["captures"]
            for state in states:
                event = receipt_event(state)
                if event is None:
                    if self.jira is not None:
                        with suppress(OSError, ValueError, KeyError, TypeError):
                            self.receiving._require_scope(state)
                            self.jira.sync(state)
                    continue
                completed_routes = {
                    row["route"]
                    for row in self.journal.for_capture(state["id"])
                    if row["status"] == "VERIFIED"
                }
                jira_open = (
                    self.jira is not None
                    and any(
                        row["route"] == self.jira.route + ":create"
                        for row in self.journal.for_capture(state["id"])
                    )
                    and not any(
                        row["route"] == self.jira.route + ":resolve" and row["status"] == "VERIFIED"
                        for row in self.journal.for_capture(state["id"])
                    )
                )
                if {
                    target.route for target in self.destinations
                } <= completed_routes and not jira_open:
                    continue
                try:
                    self.receiving._require_scope(state)
                    # The original submitted document and ledger must STILL match before
                    # a new notification, including when resuming after interruption.
                    fresh = self.receiving.erp.submit(  # type: ignore[union-attr]
                        state["candidate"], state["id"], state["draft"], lookup_only=True
                    )
                    fresh_event = receipt_event({**state, "receipt": fresh})
                    # Preserve the original verification time as the event timestamp;
                    # every business field must agree with the fresh authoritative read.
                    if fresh_event is None:
                        continue
                    fresh_ledger = fresh.get("stock_ledger")
                    if not isinstance(fresh_ledger, list) or not same_stock_effects(
                        state["receipt"]["stock_ledger"], fresh_ledger
                    ):
                        continue
                    if (
                        any(
                            row["voucher_type"] != "Purchase Receipt"
                            or row["voucher_no"] != event["receipt"]
                            or row["item_code"] != event["item_code"]
                            for row in fresh_ledger
                        )
                        or sum(row["actual_qty"] for row in fresh_ledger) != event["quantity"]
                    ):
                        continue
                    comparable = {**fresh_event, "verified_at": event["verified_at"]}
                    comparable["stock_ledger_ids"] = event["stock_ledger_ids"]
                    if comparable != event:
                        continue
                except (OSError, ValueError, KeyError, TypeError):
                    continue  # Never notify based solely on a stale local success flag.
                for target in self.destinations:
                    if self.closed.is_set():
                        return
                    with suppress(OSError, ValueError):
                        self.journal.deliver(target.route, event, target)
                if jira_open and self.jira is not None:
                    verified_routes = {
                        row["route"]
                        for row in self.journal.for_capture(state["id"])
                        if row["status"] == "VERIFIED"
                    }
                    if {target.route for target in self.destinations} <= verified_routes:
                        with suppress(OSError, ValueError, KeyError, TypeError):
                            self.jira.sync(state, verified_resolution=event)
            if len(states) < 50:
                return

    def start(self) -> None:
        if self.thread is None:
            self.thread = Thread(target=self._run, name="receiving-handoffs", daemon=True)
            self.thread.start()

    def _run(self) -> None:
        while not self.closed.is_set():
            with suppress(OSError, ValueError):
                self.tick()
            if self.closed.wait(30):
                return

    def close(self) -> None:
        self.closed.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
