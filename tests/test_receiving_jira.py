"""Offline provider contracts, not evidence of real Jira acceptance."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from the_missing_20.adapters.receiving_handoff import HandoffJournal, receipt_event
from the_missing_20.adapters.receiving_jira import JiraReceivingReview


class API:
    def __init__(self):
        self.config = SimpleNamespace(
            jira_project_key="QRC", jira_base_url="https://demo.atlassian.net"
        )
        self.issue = None
        self.comments = []
        self.writes = []
        self.lose_ack = False
        self.outage = False
        self.extra_issue = False
        self.transitions = [{"id": "31", "to": {"statusCategory": {"key": "done"}}}]

    def request(self, provider, path, *, payload=None):
        assert provider == "jira"
        if self.outage:
            raise OSError("provider unavailable")
        if payload is not None:
            self.writes.append(path)
            if path == "/rest/api/3/issue":
                fields = deepcopy(payload["fields"])
                fields["status"] = {"name": "Open", "statusCategory": {"key": "new"}}
                self.issue = {"key": "QRC-22", "fields": fields}
            elif path.endswith("/comment"):
                self.comments.append({"body": payload["body"]})
            elif path.endswith("/transitions"):
                self.comments.append({"body": payload["update"]["comment"][0]["add"]["body"]})
                self.issue["fields"]["status"] = {"name": "Done", "statusCategory": {"key": "done"}}
            else:
                raise AssertionError(path)
            if self.lose_ack:
                raise TimeoutError("lost response after provider commit")
            return None
        if path.startswith("/rest/api/3/search/jql?"):
            return {
                "issues": ([{"key": "QRC-22"}] * (2 if self.extra_issue else 1))
                if self.issue
                else [],
                "isLast": True,
            }
        if path.startswith("/rest/api/3/project/"):
            return {"issueTypes": [{"id": "10001", "name": "Task", "subtask": False}]}
        if "/comment?" in path:
            return {"comments": deepcopy(self.comments), "total": len(self.comments)}
        if path.endswith("/transitions"):
            return {"transitions": self.transitions}
        if path.startswith("/rest/api/3/issue/QRC-22?"):
            return deepcopy(self.issue)
        raise AssertionError(path)


def capture(status="NEEDS_REVIEW"):
    return {
        "tenant": "https://demo.erp.test",
        "id": "photo-1",
        "purchase_order": "PO-1",
        "work_item": {"case_id": "M20-case", "arrival_id": "arrival-1"},
        "version": 3,
        "digest": "a" * 64,
        "status": status,
        "events": [{"detail": "Visible package damage requires review"}],
    }


def setup(tmp_path):
    api = API()
    journal = HandoffJournal(tmp_path / "journal.db")
    return api, journal, JiraReceivingReview(api, journal, "QRC")


def posted(state):
    state.update(
        status="RECEIPT_SUBMITTED",
        version=4,
        stock_posted=True,
        receipt={
            "name": "PR-1",
            "docstatus": 1,
            "verified_receipt": True,
            "stock_posted": True,
            "stock_ledger": [{"name": "SLE-1"}],
            "stock_uom": "Box",
            "quantity": 1,
            "url": "https://demo.erp.test/PR-1",
            "verified_at": "2026-09-09T00:00:00Z",
        },
    )
    state["work_item"]["item_code"] = "M20-BOX"
    return receipt_event(state)


@pytest.mark.parametrize(
    "status",
    ["AWAITING_PHOTO", "NEEDS_PHOTO", "COUNT_CANDIDATE", "RECEIPT_PREPARED", "RECEIPT_SUBMITTED"],
)
def test_normal_work_never_creates_an_incident(tmp_path: Path, status: str):
    api, _, jira = setup(tmp_path)
    assert jira.sync(capture(status)) == []
    assert api.writes == []


def test_exception_create_update_resolve_and_restart_are_idempotent(tmp_path: Path):
    api, journal, jira = setup(tmp_path)
    state = capture()
    jira.sync(state)
    assert len(api.writes) == 2
    assert all(row["status"] == "VERIFIED" for row in journal.for_capture(state["id"]))
    jira = JiraReceivingReview(api, HandoffJournal(tmp_path / "journal.db"), "QRC")
    jira.sync(state)
    assert len(api.writes) == 2
    resolution = posted(state)
    jira.sync(state, verified_resolution=resolution)
    assert len(api.writes) == 4
    assert api.issue["fields"]["status"]["name"] == "Done"
    jira.sync(state, verified_resolution=resolution)
    assert len(api.writes) == 4


def test_lost_ack_reconciles_without_resending(tmp_path: Path):
    api, _, jira = setup(tmp_path)
    api.lose_ack = True
    jira.sync(capture())
    assert len(api.writes) == 1
    jira = JiraReceivingReview(api, HandoffJournal(tmp_path / "journal.db"), "QRC")
    jira.sync(capture())  # creation found; comment commits but ACK is lost too
    jira.sync(capture())
    assert len(api.writes) == 2


def test_duplicate_issue_or_changed_marker_blocks_further_writes(tmp_path: Path):
    api, journal, jira = setup(tmp_path)
    api.lose_ack = True
    jira.sync(capture())
    api.extra_issue = True
    jira.sync(capture())
    assert len(api.writes) == 1
    assert journal.for_capture("photo-1")[0]["status"] == "UNKNOWN"


def test_outage_before_claim_remains_retryable(tmp_path: Path):
    api, journal, jira = setup(tmp_path)
    api.outage = True
    jira.sync(capture())
    assert journal.for_capture("photo-1")[0]["status"] == "PENDING"
    api.outage = False
    jira.sync(capture())
    assert len(api.writes) == 2


def test_resolution_cannot_belong_to_another_capture(tmp_path: Path):
    api, _, jira = setup(tmp_path)
    jira.sync(capture())
    with pytest.raises(ValueError, match="does not match"):
        jira.sync(capture(), verified_resolution={"capture_id": "other"})
    assert not any(path.endswith("/transitions") for path in api.writes)


def test_ambiguous_legal_transition_requires_human_not_guess(tmp_path: Path):
    api, journal, jira = setup(tmp_path)
    state = capture()
    jira.sync(state)
    api.transitions *= 2
    jira.sync(state, verified_resolution=posted(state))
    assert api.issue["fields"]["status"]["name"] == "Open"
    assert journal.for_capture(state["id"])[-1]["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "field",
    ["receipt", "arrival_id", "purchase_order", "quantity", "uom", "item_code", "stock_ledger_ids"],
)
def test_changed_receipt_fact_cannot_close_or_comment(tmp_path, field):
    api, _, jira = setup(tmp_path)
    state = capture()
    jira.sync(state)
    resolution = posted(state)
    resolution[field] = "different"
    with pytest.raises(ValueError, match="does not match"):
        jira.sync(state, verified_resolution=resolution)
    assert len(api.writes) == 2


@pytest.mark.parametrize("broken", [None, [], {"issueTypes": None}, {"issueTypes": [None]}])
def test_malformed_project_cannot_kill_worker(tmp_path, broken):
    api, journal, jira = setup(tmp_path)
    original = api.request
    api.request = lambda provider, path, **kwargs: (
        broken if path.startswith("/rest/api/3/project/") else original(provider, path, **kwargs)
    )
    jira.sync(capture())
    assert api.writes == []
    assert journal.for_capture("photo-1")[0]["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "field,value",
    [("fields", None), ("fields", []), ("project", []), ("status", None), ("labels", None)],
)
def test_malformed_issue_cannot_kill_worker(tmp_path, field, value):
    api, _, jira = setup(tmp_path)
    api.lose_ack = True
    jira.sync(capture())
    if field == "fields":
        api.issue[field] = value
    else:
        api.issue["fields"][field] = value
    jira.sync(capture())
    assert len(api.writes) == 1
