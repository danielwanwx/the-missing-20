from copy import deepcopy

from the_missing_20.adapters.conversation_views import history_attachment
from the_missing_20.agents.live_advisory import LiveAdvisoryResult


def test_explicit_chart_survives_model_omission_but_requires_actual_read():
    history = {
        "case_id": "case",
        "points": [
            {"case_id": "case", "id": 1, "metrics": {"received": 0}},
            {"case_id": "case", "id": 2, "metrics": {"received": 1}},
        ],
    }
    packet = {"case_id": "case", "tool_payload": {"sources": {"read_operational_history": history}}}
    question = "Show the received quantity trend"
    calls = ("read_operational_history",)
    views = history_attachment(packet, None, calls, question=question)
    assert views[0]["metric"] == "received"
    assert views[0]["selection_basis"] == "explicit_human_request"
    assert views[0]["history"]["points"] == history["points"]
    assert history_attachment(packet, None, (), question=question) == []
    assert (
        history_attachment(packet, None, calls, question="Show trend of received and recorded")
        == []
    )
    assert history_attachment(packet, None, calls, question="Approve the receipt") == []


def test_retained_views_are_scoped_and_never_select_unsupported_profit():
    from the_missing_20.adapters.conversation_views import retained_history_view

    history = snapshot()["tool_payload"]["sources"]["read_operational_history"]
    projection = {"case_id": "case-1", "operational_history": history}
    view = retained_history_view(projection, "Show the receiving trend")
    assert view[0]["metric"] == "received"
    view[0]["history"]["points"][0]["metrics"]["received"] = 900
    assert history["points"][0]["metrics"]["received"] == 12
    assert retained_history_view(projection, "Show profit history") == []
    assert retained_history_view(projection, "Show receiving and quality hold trends") == []
    assert retained_history_view(projection, "Receive ten boxes") == []
    assert retained_history_view({**projection, "case_id": "case-2"}, "Show receiving trend") == []
    history["points"][0]["case_id"] = "case-2"
    assert retained_history_view(projection, "Show receiving trend") == []


def snapshot():
    return {
        "case_id": "case-1",
        "tool_payload": {
            "sources": {
                "read_operational_history": {
                    "case_id": "case-1",
                    "points": [{"case_id": "case-1", "id": 1, "metrics": {"received": 12}}],
                }
            }
        },
    }


def test_attachment_requires_actual_history_read_and_matching_scope():
    packet = snapshot()
    assert history_attachment(packet, "received", ()) == []
    assert history_attachment(packet, "profit", ("read_operational_history",)) == []
    original = deepcopy(packet)
    view = history_attachment(packet, "received", ("read_operational_history",))
    assert view[0]["history"]["points"][0]["metrics"]["received"] == 12
    view[0]["history"]["points"][0]["metrics"]["received"] = 99
    assert packet == original
    packet["case_id"] = "case-2"
    assert history_attachment(packet, "received", ("read_operational_history",)) == []


def test_result_accepts_typed_visual_request_not_arbitrary_chart_numbers():
    raw = {
        "disposition": "RECOVERY_COMPLETE",
        "evidence_ids": ["erp"],
        "reason": "Receiving is complete.",
        "safe_next_step": "Monitor only.",
        "write_performed": False,
        "chart_metric": "received",
        "follow_up_questions": ["Which receipts contributed?"],
    }
    result = LiveAdvisoryResult.model_validate(raw)
    assert result.chart_metric == "received"
    assert result.follow_up_questions == ("Which receipts contributed?",)
