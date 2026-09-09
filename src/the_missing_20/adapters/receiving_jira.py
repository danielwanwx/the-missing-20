"""Case-scoped receiving review tasks; Jira never authorizes stock movements.

One durable operation per creation/evidence revision/resolution. An uncertain
write is lookup-only through HandoffJournal, including after process restart.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from .receiving_destinations import ReceivingAPI
from .receiving_handoff import HandoffJournal, receipt_event


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Malformed Jira object")
    return value


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Malformed Jira list")
    return value


def _adf(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


class JiraReceivingReview:
    def __init__(self, api: ReceivingAPI, journal: HandoffJournal, project: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,20}", project):
            raise ValueError("Invalid receiving Jira project")
        if project != api.config.jira_project_key:
            raise ValueError("Receiving Jira project scope changed")
        url = urlsplit(api.config.jira_base_url)
        if url.scheme != "https" or not url.hostname or not url.hostname.endswith(".atlassian.net"):
            raise ValueError("Receiving Jira browser origin must be an Atlassian tenant")
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("Invalid receiving Jira browser origin")
        self.api, self.journal, self.project = api, journal, project
        self.origin = api.config.jira_base_url.rstrip("/")
        self.route = "jira-receiving:" + project

    @staticmethod
    def marker(state: dict[str, Any]) -> str:
        return (
            "m20-review-"
            + hashlib.sha256(
                json.dumps(
                    [state["tenant"], state["work_item"]["case_id"], state["id"]],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:32]
        )

    def _issue(self, key: str, marker: str) -> dict[str, Any]:
        if not isinstance(key, str) or not re.fullmatch(
            re.escape(self.project) + r"-[1-9][0-9]*", key
        ):
            raise ValueError("Jira returned an out-of-project issue")
        row = self.api.request(
            "jira",
            "/rest/api/3/issue/"
            + quote(key, safe="")
            + "?fields=project,labels,status,description,updated",
        )
        fields = _object(_object(row).get("fields"))
        if (
            row.get("key") != key
            or _object(fields.get("project")).get("key") != self.project
            or not isinstance(fields.get("labels"), list)
            or marker not in fields["labels"]
        ):
            raise ValueError("Jira issue scope cannot be verified")
        _object(_object(fields.get("status")).get("statusCategory"))
        return row

    def lookup(self, marker: str) -> dict[str, Any] | None:
        query = urlencode(
            {
                "jql": f'project = "{self.project}" AND labels = "{marker}"',
                "maxResults": 2,
                "fields": "key",
            }
        )
        page = self.api.request("jira", "/rest/api/3/search/jql?" + query)
        if not isinstance(page, dict) or not isinstance(page.get("issues"), list):
            raise ValueError("Jira issue lookup unavailable")
        rows = _rows(page["issues"])
        if len(rows) > 1 or page.get("nextPageToken") or page.get("isLast") is False:
            raise ValueError("Jira receiving task identity is not unique")
        return self._issue(rows[0].get("key"), marker) if rows else None

    def sync(
        self, state: dict[str, Any], *, verified_resolution: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Caller supplies a freshly verified ERP resolution, not an LLM assertion."""
        if verified_resolution is not None:
            expected = receipt_event(state)
            if expected is None or expected != verified_resolution:
                raise ValueError("Jira resolution does not match the verified receipt")
        marker = self.marker(state)
        existing = [
            row
            for row in self.journal.for_capture(state["id"])
            if row["route"].startswith(self.route + ":")
        ]
        # Count candidates, partial POs and ordinary photo retakes are not incidents.
        if not existing and state.get("status") != "NEEDS_REVIEW":
            return []
        work = state["work_item"]
        base = {
            "tenant": state["tenant"],
            "case_id": work["case_id"],
            "arrival_id": work["arrival_id"],
            "capture_id": state["id"],
            "purchase_order": state["purchase_order"],
            "marker": marker,
        }
        # Freeze the creation payload; subsequent photo revisions become comments.
        create_event = {**base, "operation": "create"}
        created = self.journal.deliver(
            self.route + ":create", create_event, _JiraOperation(self), business_key=marker
        )
        if created["status"] != "VERIFIED":
            return self.journal.for_capture(state["id"])
        issue = created["evidence"]["record_id"]
        evidence = {
            **base,
            "operation": "comment",
            "issue": issue,
            "version": state["version"],
            "status": state["status"],
            "photo_digest": state.get("digest"),
            "detail": (state.get("events") or [{}])[-1].get("detail", "Review receiving evidence"),
        }
        revision = self.journal.deliver(
            self.route + ":comment",
            evidence,
            _JiraOperation(self),
            business_key=f"{marker}:revision:{state['version']}",
        )
        if verified_resolution is not None and revision["status"] == "VERIFIED":
            resolution = {
                **base,
                "operation": "resolve",
                "issue": issue,
                "receipt": verified_resolution["receipt"],
                "receipt_evidence": verified_resolution,
            }
            self.journal.deliver(
                self.route + ":resolve",
                resolution,
                _JiraOperation(self),
                business_key=marker + ":resolved",
            )
        return self.journal.for_capture(state["id"])


class _JiraOperation:
    def __init__(self, owner: JiraReceivingReview) -> None:
        self.owner = owner

    @staticmethod
    def body(event: dict[str, Any], key: str) -> dict[str, Any]:
        return _adf(
            "M20 demo receiving evidence\n"
            + json.dumps(event, sort_keys=True)
            + "\nOperation: "
            + key
        )

    def find(self, event: dict[str, Any], key: str) -> dict[str, Any] | None:
        owner, operation = self.owner, event["operation"]
        issue = (
            owner.lookup(event["marker"])
            if operation == "create"
            else owner._issue(event["issue"], event["marker"])
        )
        if issue is None:
            return None
        issue_key = issue["key"]
        if operation == "create":
            if issue["fields"].get("description") != self.body(event, key):
                raise ValueError("Jira creation evidence changed")
        else:
            page = owner.api.request(
                "jira", f"/rest/api/3/issue/{issue_key}/comment?maxResults=100"
            )
            if (
                not isinstance(page, dict)
                or not isinstance(page.get("comments"), list)
                or type(page.get("total")) is not int
                or page["total"] != len(page["comments"])
            ):
                raise ValueError("Jira comment reconciliation is incomplete")
            matches = [
                row for row in _rows(page["comments"]) if row.get("body") == self.body(event, key)
            ]
            if len(matches) > 1:
                raise ValueError("Duplicate Jira operation evidence")
            if not matches:
                return None
            if (
                operation == "resolve"
                and issue["fields"].get("status", {}).get("statusCategory", {}).get("key") != "done"
            ):
                return None
        return {
            "provider": "Jira",
            "record_id": issue_key,
            "url": owner.origin + "/browse/" + issue_key,
            "status": issue["fields"].get("status", {}).get("name", "UNKNOWN"),
            "operation": operation,
        }

    def send(self, event: dict[str, Any], key: str) -> None:
        owner, operation = self.owner, event["operation"]
        if operation == "create":
            project = owner.api.request("jira", "/rest/api/3/project/" + owner.project)
            types = [
                kind
                for kind in _rows(_object(project).get("issueTypes"))
                if kind.get("name") == "Task" and kind.get("subtask") is False
            ]
            if len(types) != 1:
                raise ValueError("Jira receiving Task type unavailable")
            owner.api.request(
                "jira",
                "/rest/api/3/issue",
                payload={
                    "fields": {
                        "project": {"key": owner.project},
                        "issuetype": {"id": types[0]["id"]},
                        "summary": f"[M20 demo] Receiving review — {event['case_id']}"
                        f" / {event['arrival_id']}",
                        "labels": [event["marker"], "m20-demo-receiving"],
                        "description": self.body(event, key),
                    }
                },
            )
            return
        issue = owner._issue(event["issue"], event["marker"])
        path = f"/rest/api/3/issue/{issue['key']}"
        if operation == "comment":
            owner.api.request("jira", path + "/comment", payload={"body": self.body(event, key)})
            return
        transitions = owner.api.request("jira", path + "/transitions")
        done = [
            row
            for row in _rows(_object(transitions).get("transitions"))
            if _object(_object(row.get("to")).get("statusCategory")).get("key") == "done"
        ]
        if len(done) != 1:
            raise ValueError("Jira resolution needs a human-selected legal transition")
        # One provider operation atomically records the proof comment and transition.
        owner.api.request(
            "jira",
            path + "/transitions",
            payload={
                "transition": {"id": done[0]["id"]},
                "update": {"comment": [{"add": {"body": self.body(event, key)}}]},
            },
        )
