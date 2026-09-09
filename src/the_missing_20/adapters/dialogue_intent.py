"""Retain human constraints independently of whether a model produces an answer.

These records never grant execution authority. Approval remains a separate,
evidence-bound action. A chat request cannot silently clear a previous refusal.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import uuid4


def record_request(state: Mapping, case_id: str, question: str, at: str) -> dict:
    current = dict(state) if state.get("case_id") == case_id else {"case_id": case_id}
    refusal = bool(
        re.search(
            r"\b(?:declin\w*|stop|read.only|without (?:writing|approval)|"
            r"do not (?:approve|execute)|only inspect)\b|拒绝|不要执行|只读|停止执行",
            question,
            re.IGNORECASE,
        )
    )
    if refusal:
        current["read_only_requested"] = True
        current["constraint_question"] = question
    request = {"request_id": uuid4().hex, "question": question, "created_at": at}
    current["requests"] = [*current.get("requests", []), request][-12:]
    return current


def public_state(state: Mapping, case_id: str) -> dict:
    if state.get("case_id") != case_id:
        return {"human_intent": {}, "human_requests": []}
    return {
        "human_intent": {
            key: state[key]
            for key in ("case_id", "read_only_requested", "constraint_question")
            if key in state
        },
        "human_requests": list(state.get("requests", [])),
    }
