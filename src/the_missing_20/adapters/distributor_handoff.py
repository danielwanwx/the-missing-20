"""Same-case distributor evidence handoffs through the existing durable journal.

The adapter deliberately owns only the distributor projection contract.  It does
not make a receiving photo case look like a distributor case and it never turns
an operational milestone into independent proof of physical delivery.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Protocol, cast
from urllib.parse import quote, urlencode, urlsplit

from the_missing_20.adapters.receiving_destinations import ReceivingAPI
from the_missing_20.adapters.receiving_handoff import HandoffJournal


class DistributorDestination(Protocol):
    route: str

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None: ...

    def send(self, event: dict[str, Any], key: str) -> None: ...


class JiraDistributorDestination(DistributorDestination, Protocol):
    def lookup(self, event: Mapping[str, object]) -> dict[str, Any] | None: ...


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"distributor {label} is missing")
    return value.strip()


def _copy(value: object) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"distributor {label} is malformed")
    return value


def _decision(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    status = value.get("status")
    if status not in {"SELECTED", "PENDING"}:
        return None
    result: dict[str, object] = {
        "status": status,
        "plan_id": _text(value.get("plan_id"), "decision plan ID"),
        "state_revision": _text(value.get("state_revision"), "decision revision"),
        "contract_refs": sorted(
            _text(ref, "contract reference") for ref in value.get("contract_refs", [])
        )
        if isinstance(value.get("contract_refs"), list)
        else [],
        "rationale": _text(value.get("rationale"), "decision rationale"),
    }
    plan = value.get("plan")
    if isinstance(plan, Mapping):
        result["policy_version"] = _text(plan.get("version"), "plan version")
    return result


def _parent_purchase_order(value: object) -> dict[str, object] | None:
    """Retain only the canonical parent-PO facts produced by the ERP projection."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("parent purchase order is malformed")
    return {
        "name": _text(value.get("name"), "parent purchase order name"),
        "ordered": _number(value.get("ordered"), "parent purchase order ordered"),
        "received": _number(value.get("received"), "parent purchase order received"),
        "outside_case_received": _number(
            value.get("outside_case_received"), "parent purchase order outside-case received"
        ),
        "uom": _text(value.get("uom"), "parent purchase order unit"),
    }


def _item_identifiers(
    projection: Mapping[str, object], parent_purchase_order: Mapping[str, object] | None
) -> dict[str, object]:
    """Derive the configured item and parent PO from current, retained ERP facts only."""

    result: dict[str, object] = {}
    item_codes = {
        value.strip()
        for value in [projection.get("item_code")]
        if isinstance(value, str) and value.strip()
    }
    events = projection.get("events")
    if isinstance(events, list):
        item_codes.update(
            value.strip()
            for row in events
            if isinstance(row, Mapping)
            and isinstance((value := row.get("item_code")), str)
            and value.strip()
        )
    if len(item_codes) > 1:
        raise ValueError("distributor item identifiers are ambiguous")
    if item_codes:
        result["item_code"] = item_codes.pop()
    direct_purchase_order = projection.get("purchase_order")
    if isinstance(direct_purchase_order, str) and direct_purchase_order.strip():
        result["purchase_order"] = direct_purchase_order.strip()
    elif parent_purchase_order is not None:
        result["purchase_order"] = parent_purchase_order["name"]
    for key in ("item_url", "purchase_order_url"):
        value = projection.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def distributor_event(projection: Mapping[str, object]) -> dict[str, object] | None:
    """Freeze current business facts; timestamps and conversation prose are excluded."""

    if projection.get("available") is not True:
        return None
    case_id = _text(projection.get("case_id"), "case ID")
    quantities = projection.get("quantities")
    allocations = projection.get("allocations")
    if not isinstance(quantities, Mapping) or not isinstance(allocations, list):
        raise ValueError("distributor current facts are malformed")
    facts = {
        key: _number(quantities.get(key), key)
        for key in ("ordered", "received", "held", "missing", "dispatched", "delivery_confirmed")
    }
    uom = _text(quantities.get("uom"), "unit")
    rows: list[dict[str, object]] = []
    for raw in allocations:
        if not isinstance(raw, Mapping):
            raise ValueError("distributor allocation is malformed")
        rows.append(
            {
                "customer_order": _text(raw.get("customer_order"), "customer order"),
                "requested_quantity": _number(raw.get("requested_quantity"), "requested quantity"),
                "allocated": _number(raw.get("allocated"), "allocated quantity"),
                "backordered": _number(raw.get("backordered"), "backordered quantity"),
                "dispatched": _number(raw.get("dispatched"), "dispatched quantity"),
            }
        )
    raw_decision = projection.get("allocation_decision")
    decision = _decision(raw_decision)
    if decision is not None and isinstance(raw_decision, Mapping):
        for field in ("provider", "usage"):
            if isinstance((value := raw_decision.get(field)), Mapping):
                decision[field] = _copy(value)
    alerts = projection.get("alerts")
    open_codes = (
        sorted(
            _text(row.get("code"), "alert code")
            for row in alerts
            if isinstance(row, Mapping) and row.get("status") == "OPEN"
        )
        if isinstance(alerts, list)
        else []
    )
    parent_purchase_order = _parent_purchase_order(projection.get("parent_purchase_order"))
    event: dict[str, object] = {
        "tenant": "distributor-case",
        "capture_id": case_id,
        "case_id": case_id,
        "case_label": _text(projection.get("case_label"), "case label"),
        "synthetic_input": projection.get("synthetic_input") is True,
        "uom": uom,
        "quantities": facts,
        "allocations": sorted(rows, key=lambda row: str(row["customer_order"])),
        "parent_purchase_order": parent_purchase_order,
        "item_identifiers": _item_identifiers(projection, parent_purchase_order),
        "open_alert_codes": open_codes,
        "allocation_decision": decision,
        "documents": _copy(projection.get("documents", [])),
    }
    semantic = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    event["semantic_digest"] = hashlib.sha256(semantic.encode()).hexdigest()
    return event


def exception_lifecycle(event: Mapping[str, object]) -> str | None:
    quantities = event.get("quantities")
    alerts = event.get("open_alert_codes")
    if not isinstance(quantities, Mapping) or not isinstance(alerts, list):
        raise ValueError("distributor event facts are malformed")
    if alerts:
        return "operational-exception"
    if quantities.get("missing", 0) != 0 or quantities.get("held", 0) != 0:
        return "operational-exception"
    return None


def milestone(event: Mapping[str, object]) -> str | None:
    if exception_lifecycle(event) is not None:
        return "EXCEPTION_REVIEW"
    quantities = event.get("quantities")
    if isinstance(quantities, Mapping) and quantities.get("dispatched") == quantities.get(
        "ordered"
    ):
        return "OPERATIONAL_DISPATCH_RECORDED"
    decision = event.get("allocation_decision")
    if isinstance(decision, Mapping) and decision.get("status") == "SELECTED":
        return "ALLOCATION_SELECTED"
    return None


def milestone_key(event: Mapping[str, object], mark: str) -> str:
    """Keep Slack identity on business progress, never provider metadata or timestamps."""

    quantities = event.get("quantities")
    if not isinstance(quantities, Mapping):
        raise ValueError("distributor milestone quantities are malformed")
    if mark == "ALLOCATION_SELECTED":
        decision = event.get("allocation_decision")
        if not isinstance(decision, Mapping):
            raise ValueError("distributor selected milestone lacks a decision")
        data: object = [decision.get("plan_id"), decision.get("state_revision")]
    elif mark == "EXCEPTION_REVIEW":
        data = [
            sorted(cast(list[str], event["open_alert_codes"])),
            quantities.get("held"),
            quantities.get("missing"),
        ]
    elif mark == "OPERATIONAL_DISPATCH_RECORDED":
        data = [quantities.get("dispatched"), quantities.get("delivery_confirmed")]
    else:
        raise ValueError("unknown distributor milestone")
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()[:20]


def _jira_create_event(event: Mapping[str, object], lifecycle: str) -> dict[str, object]:
    """Keep lifecycle creation immutable; later ERP facts belong to revision comments."""

    return {
        "tenant": event["tenant"],
        "capture_id": event["capture_id"],
        "case_id": event["case_id"],
        "operation": "create",
        "lifecycle": lifecycle,
    }


def _jira_resolve_event(event: Mapping[str, object], issue: str) -> dict[str, object]:
    return {
        "tenant": event["tenant"],
        "capture_id": event["capture_id"],
        "case_id": event["case_id"],
        "operation": "resolve",
        "issue": issue,
        "lifecycle": "operational-exception",
    }


def _slack_event(event: Mapping[str, object], mark: str) -> dict[str, object]:
    """Journal only the exact milestone payload, so unrelated revisions cannot replay it."""

    quantities = event.get("quantities")
    if not isinstance(quantities, Mapping):
        raise ValueError("distributor Slack quantities are malformed")
    result: dict[str, object] = {
        "tenant": event["tenant"],
        "capture_id": event["capture_id"],
        "case_id": event["case_id"],
        "uom": event["uom"],
        "synthetic_input": event["synthetic_input"],
        "milestone": mark,
        "item_identifiers": {
            key: value
            for key, value in cast(Mapping[str, object], event["item_identifiers"]).items()
            if key == "purchase_order"
        },
    }
    if mark == "ALLOCATION_SELECTED":
        decision = event.get("allocation_decision")
        if not isinstance(decision, Mapping):
            raise ValueError("distributor selected Slack milestone lacks a decision")
        result["allocation_decision"] = {
            key: decision[key]
            for key in ("status", "plan_id", "state_revision", "contract_refs", "rationale")
        }
    elif mark == "EXCEPTION_REVIEW":
        result["open_alert_codes"] = event["open_alert_codes"]
        result["quantities"] = {key: quantities[key] for key in ("held", "missing")}
    elif mark == "OPERATIONAL_DISPATCH_RECORDED":
        result["quantities"] = {
            key: quantities[key] for key in ("dispatched", "delivery_confirmed")
        }
    else:
        raise ValueError("unknown distributor Slack milestone")
    return result


class DistributorHandoff:
    """Synchronize one current distributor projection without a new workflow engine."""

    def __init__(
        self,
        journal: HandoffJournal,
        *,
        airtable: DistributorDestination,
        jira: JiraDistributorDestination,
        slack: DistributorDestination,
    ) -> None:
        self.journal = journal
        self.airtable, self.jira, self.slack = airtable, jira, slack

    def sync(self, projection: Mapping[str, object]) -> dict[str, object]:
        event = distributor_event(projection)
        if event is None:
            return {"status": "UNAVAILABLE", "destinations": []}
        case_id = _text(event["case_id"], "case ID")
        revision = _text(event["semantic_digest"], "semantic digest")
        records: list[dict[str, object]] = []
        records.append(
            self.journal.deliver(
                self.airtable.route,
                event,
                self.airtable,
                business_key=f"{case_id}:airtable:{revision}",
            )
        )
        lifecycle = exception_lifecycle(event)
        if lifecycle is not None:
            issue = self.journal.deliver(
                self.jira.route + ":create",
                _jira_create_event(event, lifecycle),
                self.jira,
                business_key=f"{case_id}:jira:{lifecycle}",
            )
            records.append(issue)
            if issue.get("status") == "VERIFIED":
                issue_id = issue.get("evidence", {}).get("record_id")
                if isinstance(issue_id, str):
                    records.append(
                        self.journal.deliver(
                            self.jira.route + ":comment",
                            {
                                **event,
                                "operation": "comment",
                                "issue": issue_id,
                                "lifecycle": lifecycle,
                            },
                            self.jira,
                            business_key=f"{case_id}:jira:{lifecycle}:{revision}",
                        )
                    )
        else:
            resolution_basis = {**event, "lifecycle": "operational-exception"}
            existing = self.jira.lookup(resolution_basis)
            if existing is not None and isinstance(existing.get("key"), str):
                issue_id = existing["key"]
                resolution = {
                    **resolution_basis,
                    "operation": "comment",
                    "issue": issue_id,
                    "resolution": (
                        "Recorded operational exception condition is reconciled in current ERP "
                        "facts; "
                        "this does not establish supplier responsibility or physical delivery."
                    ),
                }
                proof = self.journal.deliver(
                    self.jira.route + ":resolution-evidence",
                    resolution,
                    self.jira,
                    business_key=f"{case_id}:jira:operational-exception:resolution:{revision}",
                )
                records.append(proof)
                if proof.get("status") == "VERIFIED":
                    records.append(
                        self.journal.deliver(
                            self.jira.route + ":resolve",
                            _jira_resolve_event(event, issue_id),
                            self.jira,
                            business_key=f"{case_id}:jira:operational-exception:resolved",
                        )
                    )
        mark = milestone(event)
        if mark is not None:
            records.append(
                self.journal.deliver(
                    self.slack.route,
                    _slack_event(event, mark),
                    self.slack,
                    business_key=f"{case_id}:slack:{mark}:{milestone_key(event, mark)}",
                )
            )
        return {"status": "CURRENT", "semantic_digest": revision, "destinations": records}


class AirtableDistributorCase:
    """One case-keyed Airtable summary, verified after each meaningful revision."""

    def __init__(self, api: ReceivingAPI, table_id: str) -> None:
        self.api, self.table_id = api, _text(table_id, "Airtable table")
        self.route = f"airtable-distributor:{api.config.airtable_base_id}:{self.table_id}"

    def _path(self) -> str:
        return (
            "/"
            + quote(self.api.config.airtable_base_id, safe="")
            + "/"
            + quote(self.table_id, safe="")
        )

    @staticmethod
    def fields(event: Mapping[str, object]) -> dict[str, object]:
        quantities = event["quantities"]
        assert isinstance(quantities, Mapping)
        decision = event.get("allocation_decision")
        decision_text = "No allocation decision retained."
        if isinstance(decision, Mapping):
            decision_text = (
                f"{decision['status']} {decision['plan_id']} "
                f"({decision.get('policy_version', 'unknown policy')}); "
                f"refs: {', '.join(cast(str, ref) for ref in decision['contract_refs'])}; "
                f"rationale: {decision['rationale']}"
            )
        synthetic = event.get("synthetic_input") is True
        return {
            "Case ID": event["case_id"],
            "Case Label": event["case_label"],
            "Unit": event["uom"],
            "Received": quantities["received"],
            "Held": quantities["held"],
            "Missing": quantities["missing"],
            "Dispatched": quantities["dispatched"],
            "Recorded Delivery Confirmation": quantities["delivery_confirmed"],
            "Customer Impact": json.dumps(event["allocations"], sort_keys=True),
            "Parent Purchase Order": json.dumps(event["parent_purchase_order"], sort_keys=True),
            "Item Identifiers": json.dumps(event["item_identifiers"], sort_keys=True),
            "ERP Documents": json.dumps(event["documents"], sort_keys=True),
            "Allocation Decision": decision_text,
            "Open Operational Alerts": ", ".join(cast(list[str], event["open_alert_codes"])),
            "Evidence Basis": (
                "Synthetic recorded operational evidence; independent physical delivery is not "
                "verified."
                if synthetic
                else "Recorded operational evidence; independent physical delivery is not verified."
            ),
            "Semantic Revision": event["semantic_digest"],
        }

    def _records(self, event: Mapping[str, object]) -> list[dict[str, object]]:
        query = urlencode({"filterByFormula": f"{{Case ID}}='{event['case_id']}'", "maxRecords": 2})
        payload = self.api.request("airtable", self._path() + "?" + query)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
            raise ValueError("Airtable distributor readback is malformed")
        rows = payload["records"]
        if len(rows) > 1 or payload.get("offset"):
            raise ValueError("Airtable distributor case identity is ambiguous")
        if any(not isinstance(row, Mapping) for row in rows):
            raise ValueError("Airtable distributor record is malformed")
        return [dict(row) for row in rows]

    def find(self, event: dict[str, Any], _key: str) -> dict[str, Any] | None:
        rows = self._records(event)
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row.get("id"), str) or not isinstance(row.get("fields"), Mapping):
            raise ValueError("Airtable distributor record lacks readback identity")
        fields = row["fields"]
        assert isinstance(fields, Mapping)
        actual = dict(fields)
        expected = self.fields(event)
        if expected["Open Operational Alerts"] == "" and "Open Operational Alerts" not in actual:
            # Airtable omits an empty single-line field from otherwise valid readback.
            actual["Open Operational Alerts"] = ""
        if actual != expected:
            return None
        record_id = row["id"]
        return {
            "provider": "Airtable",
            "record_id": record_id,
            "url": f"https://airtable.com/{self.api.config.airtable_base_id}/{self.table_id}/{record_id}",
        }

    def send(self, event: dict[str, Any], _key: str) -> None:
        rows = self._records(event)
        if rows:
            record_id = rows[0].get("id")
            if not isinstance(record_id, str):
                raise ValueError("Airtable distributor update identity is malformed")
            self.api.request(
                "airtable",
                self._path() + "/" + quote(record_id, safe=""),
                payload={"fields": self.fields(event)},
                method="PATCH",
            )
        else:
            self.api.request("airtable", self._path(), payload={"fields": self.fields(event)})


def _adf(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


class JiraDistributorCase:
    """Stable case/lifecycle task with revision comments and readback-only reconciliation."""

    def __init__(self, api: ReceivingAPI, project: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,20}", project):
            raise ValueError("invalid distributor Jira project")
        url = urlsplit(api.config.jira_base_url)
        if url.scheme != "https" or not url.hostname or not url.hostname.endswith(".atlassian.net"):
            raise ValueError("Jira distributor browser origin must be an Atlassian tenant")
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("Invalid Jira distributor browser origin")
        self.api, self.project = api, project
        self.origin = api.config.jira_base_url.rstrip("/")
        self.route = "jira-distributor:" + project

    @staticmethod
    def marker(event: Mapping[str, object]) -> str:
        return (
            "m20-dist-"
            + hashlib.sha256(
                json.dumps([event["case_id"], event["lifecycle"]], separators=(",", ":")).encode()
            ).hexdigest()[:24]
        )

    @staticmethod
    def body(event: Mapping[str, object], key: str) -> dict[str, object]:
        return _adf(
            "M20 distributor operational evidence\n"
            + json.dumps(event, sort_keys=True, ensure_ascii=False)
            + "\nOperation: "
            + key
            + "\nNo supplier responsibility or independent physical delivery is asserted."
        )

    def _issue(self, key: str, marker: str) -> dict[str, Any]:
        if not re.fullmatch(re.escape(self.project) + r"-[1-9][0-9]*", key):
            raise ValueError("Jira distributor issue is out of project")
        payload = self.api.request(
            "jira",
            "/rest/api/3/issue/"
            + quote(key, safe="")
            + "?fields=project,labels,status,description",
        )
        if not isinstance(payload, Mapping) or payload.get("key") != key:
            raise ValueError("Jira distributor issue readback is malformed")
        fields = payload.get("fields")
        if not isinstance(fields, Mapping) or not isinstance(fields.get("project"), Mapping):
            raise ValueError("Jira distributor issue fields are malformed")
        if fields["project"].get("key") != self.project or marker not in fields.get("labels", []):
            raise ValueError("Jira distributor issue scope differs")
        return dict(payload)

    def lookup(self, event: Mapping[str, object]) -> dict[str, Any] | None:
        marker = self.marker(event)
        query = urlencode(
            {
                "jql": f'project = "{self.project}" AND labels = "{marker}"',
                "maxResults": 2,
                "fields": "key",
            }
        )
        page = self.api.request("jira", "/rest/api/3/search/jql?" + query)
        if not isinstance(page, Mapping) or not isinstance(page.get("issues"), list):
            raise ValueError("Jira distributor lookup is unavailable")
        if len(page["issues"]) > 1 or page.get("nextPageToken") or page.get("isLast") is False:
            raise ValueError("Jira distributor issue identity is ambiguous")
        if not page["issues"] or not isinstance(page["issues"][0], Mapping):
            return None
        key = page["issues"][0].get("key")
        return self._issue(_text(key, "Jira issue key"), marker)

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        operation = _text(event.get("operation"), "Jira operation")
        issue = (
            self.lookup(event)
            if operation == "create"
            else self._issue(_text(event.get("issue"), "Jira issue"), self.marker(event))
        )
        if issue is None:
            return None
        fields = issue["fields"]
        if operation == "create":
            if fields.get("description") != self.body(event, key):
                return None
        elif operation == "comment":
            comments = self.api.request(
                "jira", f"/rest/api/3/issue/{issue['key']}/comment?maxResults=100"
            )
            if not isinstance(comments, Mapping) or not isinstance(comments.get("comments"), list):
                raise ValueError("Jira distributor comments are unavailable")
            if (
                sum(
                    row.get("body") == self.body(event, key)
                    for row in comments["comments"]
                    if isinstance(row, Mapping)
                )
                != 1
            ):
                return None
        elif operation == "resolve":
            status = fields.get("status")
            if not isinstance(status, Mapping) or not isinstance(
                status.get("statusCategory"), Mapping
            ):
                raise ValueError("Jira distributor status is malformed")
            if status["statusCategory"].get("key") != "done":
                return None
        return {
            "provider": "Jira",
            "record_id": issue["key"],
            "url": self.origin + "/browse/" + issue["key"],
            "status": fields.get("status", {}).get("name", "UNKNOWN"),
        }

    def send(self, event: dict[str, Any], key: str) -> None:
        operation = _text(event.get("operation"), "Jira operation")
        if operation == "create":
            project = self.api.request("jira", "/rest/api/3/project/" + self.project)
            types = project.get("issueTypes") if isinstance(project, Mapping) else None
            tasks = (
                [
                    row
                    for row in types
                    if isinstance(row, Mapping)
                    and row.get("name") == "Task"
                    and row.get("subtask") is False
                ]
                if isinstance(types, list)
                else []
            )
            if len(tasks) != 1 or not isinstance(tasks[0].get("id"), str):
                raise ValueError("Jira distributor Task type is unavailable")
            self.api.request(
                "jira",
                "/rest/api/3/issue",
                payload={
                    "fields": {
                        "project": {"key": self.project},
                        "issuetype": {"id": tasks[0]["id"]},
                        "summary": f"[M20 demo] Distributor exception — {event['case_id']}",
                        "labels": [self.marker(event), "m20-demo-distributor"],
                        "description": self.body(event, key),
                    }
                },
            )
            return
        issue = self._issue(_text(event.get("issue"), "Jira issue"), self.marker(event))
        path = "/rest/api/3/issue/" + quote(issue["key"], safe="")
        if operation == "comment":
            self.api.request("jira", path + "/comment", payload={"body": self.body(event, key)})
            return
        transitions = self.api.request("jira", path + "/transitions")
        rows = transitions.get("transitions") if isinstance(transitions, Mapping) else None
        done = (
            [
                row
                for row in rows
                if isinstance(row, Mapping)
                and isinstance(row.get("to"), Mapping)
                and isinstance(row["to"].get("statusCategory"), Mapping)
                and row["to"]["statusCategory"].get("key") == "done"
            ]
            if isinstance(rows, list)
            else []
        )
        if len(done) != 1 or not isinstance(done[0].get("id"), str):
            raise ValueError("Jira distributor transition is ambiguous")
        self.api.request(
            "jira", path + "/transitions", payload={"transition": {"id": done[0]["id"]}}
        )


class CeligoDistributorSlack:
    """A scoped milestone message sent through the existing single-attempt Celigo import."""

    def __init__(self, api: ReceivingAPI, import_id: str, connection_id: str) -> None:
        self.api, self.import_id, self.connection_id = (
            api,
            _text(import_id, "Celigo import"),
            _text(connection_id, "Celigo connection"),
        )
        self.route = f"celigo-distributor:{self.import_id}:{api.config.slack_channel_id}"

    @staticmethod
    def text(event: Mapping[str, object], key: str) -> str:
        decision = event.get("allocation_decision")
        decision_line = "No allocation decision retained."
        if isinstance(decision, Mapping):
            decision_line = (
                f"Allocation {decision['status']}: {decision['plan_id']} / "
                f"{', '.join(cast(list[str], decision['contract_refs']))}. {decision['rationale']}"
            )
        basis = (
            "Synthetic recorded operational evidence; independent physical delivery is not "
            "verified."
            if event.get("synthetic_input") is True
            else "Recorded operational evidence; independent physical delivery is not verified."
        )
        identifiers = event.get("item_identifiers")
        purchase_order = (
            identifiers.get("purchase_order", "not exposed by current facts")
            if isinstance(identifiers, Mapping)
            else "not exposed by current facts"
        )
        return (
            f"[M20 DEMO · {event['milestone']}] {event['case_id']}\n"
            f"unit {event['uom']}\n"
            f"PO {purchase_order}\n"
            f"{decision_line}\n{basis}\nEvent: {key}"
        )

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        auth = self.api.request("slack", "/auth.test")
        if (
            not isinstance(auth, Mapping)
            or auth.get("ok") is not True
            or not isinstance(auth.get("user_id"), str)
        ):
            raise ValueError("Slack distributor identity is unavailable")
        query = urlencode({"channel": self.api.config.slack_channel_id, "limit": 100})
        page = self.api.request("slack", "/conversations.history?" + query)
        messages = page.get("messages") if isinstance(page, Mapping) else None
        if (
            not isinstance(messages, list)
            or page.get("has_more")
            or (page.get("response_metadata") or {}).get("next_cursor")
        ):
            raise ValueError("Slack distributor readback is incomplete")
        matches = [
            row
            for row in messages
            if isinstance(row, Mapping)
            and row.get("text") == self.text(event, key)
            and row.get("user") == auth["user_id"]
            and isinstance(row.get("ts"), str)
        ]
        if len(matches) > 1:
            raise ValueError("Slack distributor message identity is ambiguous")
        if not matches:
            return None
        ts = matches[0]["ts"]
        link = self.api.request(
            "slack",
            "/chat.getPermalink?"
            + urlencode({"channel": self.api.config.slack_channel_id, "message_ts": ts}),
        )
        if (
            not isinstance(link, Mapping)
            or link.get("ok") is not True
            or not isinstance(link.get("permalink"), str)
        ):
            raise ValueError("Slack distributor permalink is unavailable")
        return {
            "provider": "Slack via Celigo",
            "record_id": ts,
            "url": link["permalink"],
            "celigo_import_id": self.import_id,
        }

    def send(self, event: dict[str, Any], key: str) -> None:
        definition = self.api.request("celigo", f"/imports/{self.import_id}")
        http = definition.get("http") if isinstance(definition, Mapping) else None
        if (
            not isinstance(http, Mapping)
            or definition.get("_connectionId") != self.connection_id
            or definition.get("externalId") != "m20-verified-receiving-slack-v1"
            or http.get("relativeURI") != ["chat.postMessage"]
            or http.get("method") != ["POST"]
            or definition.get("maxAttempts") != 1
        ):
            raise ValueError("Celigo distributor import definition changed")
        result = self.api.request(
            "celigo",
            f"/imports/{self.import_id}/invoke",
            payload={
                "data": [
                    {
                        "channel": self.api.config.slack_channel_id,
                        "text": self.text(event, key),
                        "unfurl_links": False,
                        "unfurl_media": False,
                    }
                ]
            },
        )
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not isinstance(result[0], Mapping)
            or result[0].get("statusCode") != 200
            or result[0].get("errors")
            or result[0].get("ignored")
        ):
            raise ValueError("Celigo distributor notification was not confirmed")
