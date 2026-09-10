"""Persist bounded human dialogue context without restoring model prose.

The local demo has one operator and one persisted runtime.  This module keeps
only original human requests, an authority constraint, and runtime-validated
receipt-reference candidates.  It deliberately does not use the display
conversation as a source of model context.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from uuid import uuid4

SCHEMA_VERSION = "missing20-dialogue-intent/v2"
MAX_REQUESTS = 12
MAX_REFERENCE_GROUPS = 12
DEFAULT_RUNTIME_INSTANCE_ID = "local-runtime"


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if value and len(value) <= 256 else ""


def _whole_text(value: object, *, limit: int = 500) -> str:
    """Accept a complete bounded message; never keep a truncated fragment."""

    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return ""
    return value


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _authority_from(value: Mapping[str, object]) -> dict[str, object]:
    """Extract only the durable human constraint, never an answer or a plan."""

    if value.get("read_only_requested") is not True:
        return {}
    authority: dict[str, object] = {"read_only_requested": True}
    question = _whole_text(value.get("constraint_question"))
    if question:
        authority["constraint_question"] = question
    return authority


def _merge_authority(*authorities: Mapping[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for authority in authorities:
        candidate = _authority_from(authority)
        if candidate:
            merged["read_only_requested"] = True
            if "constraint_question" in candidate:
                merged["constraint_question"] = candidate["constraint_question"]
    return merged


def _requests_from(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    requests: list[dict[str, str]] = []
    for request in value:
        if not isinstance(request, Mapping):
            continue
        request_id = _identifier(request.get("request_id"))
        question = _whole_text(request.get("question"))
        created_at = _identifier(request.get("created_at"))
        if request_id and question and created_at:
            requests.append(
                {"request_id": request_id, "question": question, "created_at": created_at}
            )
    return requests[-MAX_REQUESTS:]


def _receipt_ids_from(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    receipt_ids: list[str] = []
    for item in value:
        receipt_id = _identifier(item)
        if receipt_id and receipt_id not in receipt_ids:
            receipt_ids.append(receipt_id)
    return receipt_ids


def _reference_groups_from(
    value: object,
    *,
    case_id: str,
    runtime_instance_id: str,
    conversation_id: str,
) -> list[dict[str, object]]:
    """Accept only versioned, runtime-validated candidate groups."""

    if not isinstance(value, list):
        return []
    groups: list[dict[str, object]] = []
    for group in value:
        if not isinstance(group, Mapping):
            continue
        if (
            group.get("case_id") != case_id
            or group.get("runtime_instance_id") != runtime_instance_id
            or group.get("conversation_id") != conversation_id
            or group.get("provenance") != "runtime_validated"
        ):
            continue
        question = _whole_text(group.get("question"))
        created_at = _identifier(group.get("created_at"))
        receipt_ids = _receipt_ids_from(group.get("receipt_ids"))
        if not question or not created_at or not receipt_ids:
            continue
        groups.append(
            {
                "case_id": case_id,
                "runtime_instance_id": runtime_instance_id,
                "conversation_id": conversation_id,
                "question": question,
                "receipt_ids": receipt_ids,
                "created_at": created_at,
                "provenance": "runtime_validated",
            }
        )
    return groups[-MAX_REFERENCE_GROUPS:]


def _fresh_state(
    *, case_id: str, runtime_instance_id: str, authority: Mapping[str, object]
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_instance_id": runtime_instance_id,
        "case_id": case_id,
        "conversation_id": uuid4().hex,
        "requests": [],
        "requests_omitted": 0,
        "reference_groups": [],
        **_authority_from(authority),
    }


def restore_state(
    state: Mapping[str, object],
    *,
    case_id: str,
    runtime_instance_id: str = DEFAULT_RUNTIME_INSTANCE_ID,
    authority_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Restore only safe context after validating its local runtime and case scope.

    Only rows with no schema marker are legacy. They may contribute original
    human requests and constraint when their case and any supplied runtime
    identifier match. Unsupported schemas never contribute requests or
    reference candidates; a same-runtime application refusal may survive.
    """

    scoped_case_id = _identifier(case_id)
    scoped_runtime_id = _identifier(runtime_instance_id) or DEFAULT_RUNTIME_INSTANCE_ID
    raw = dict(state)
    external_authority = authority_state if isinstance(authority_state, Mapping) else {}
    same_case = raw.get("case_id") == scoped_case_id
    schema_present = "schema_version" in raw
    versioned = raw.get("schema_version") == SCHEMA_VERSION
    runtime_present = "runtime_instance_id" in raw
    same_runtime = runtime_present and raw.get("runtime_instance_id") == scoped_runtime_id
    legacy_runtime_compatible = not runtime_present or same_runtime
    raw_authority: Mapping[str, object] = {}
    if same_case and (
        (versioned and same_runtime)
        or (schema_present and not versioned and same_runtime)
        or (not schema_present and legacy_runtime_compatible)
    ):
        raw_authority = raw
    authority = _merge_authority(raw_authority, external_authority)

    if not scoped_case_id:
        return _fresh_state(
            case_id="", runtime_instance_id=scoped_runtime_id, authority=external_authority
        )

    if versioned and same_case and same_runtime:
        conversation_id = _identifier(raw.get("conversation_id"))
        restored = _fresh_state(
            case_id=scoped_case_id, runtime_instance_id=scoped_runtime_id, authority=authority
        )
        if conversation_id:
            restored["conversation_id"] = conversation_id
        restored["requests"] = _requests_from(raw.get("requests"))
        restored["requests_omitted"] = _nonnegative_int(raw.get("requests_omitted"))
        restored["reference_groups"] = _reference_groups_from(
            raw.get("reference_groups"),
            case_id=scoped_case_id,
            runtime_instance_id=scoped_runtime_id,
            conversation_id=str(restored["conversation_id"]),
        )
        return restored

    # Only an explicitly unversioned, same-runtime (or pre-runtime) legacy row
    # can restore user wording. A foreign runtime/case or unsupported schema
    # starts a fresh conversation instead.
    restored = _fresh_state(
        case_id=scoped_case_id, runtime_instance_id=scoped_runtime_id, authority=authority
    )
    if same_case and not schema_present and legacy_runtime_compatible:
        legacy_requests = _requests_from(raw.get("requests"))
        restored["requests"] = legacy_requests
        raw_requests = raw.get("requests")
        raw_count = len(raw_requests) if isinstance(raw_requests, list) else 0
        restored["requests_omitted"] = max(
            _nonnegative_int(raw.get("requests_omitted")), raw_count - len(legacy_requests)
        )
    return restored


def _is_refusal(question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:declin\w*|stop|read.only|without (?:writing|approval)|"
            r"do not (?:approve|execute)|only inspect)\b|拒绝|不要执行|只读|停止执行",
            question,
            re.IGNORECASE,
        )
    )


def record_request(
    state: Mapping[str, object],
    case_id: str,
    question: str,
    at: str,
    *,
    runtime_instance_id: str = DEFAULT_RUNTIME_INSTANCE_ID,
    new_conversation: bool = False,
    authority_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Save a complete user request before model inference starts."""

    current = restore_state(
        state,
        case_id=case_id,
        runtime_instance_id=runtime_instance_id,
        authority_state=authority_state,
    )
    if new_conversation:
        current = _fresh_state(
            case_id=str(current["case_id"]),
            runtime_instance_id=str(current["runtime_instance_id"]),
            authority=current,
        )

    whole_question = _whole_text(question)
    created_at = _identifier(at)
    if not whole_question or not created_at:
        return current
    if _is_refusal(whole_question):
        current["read_only_requested"] = True
        current["constraint_question"] = whole_question

    requests = _requests_from(current.get("requests"))
    requests.append(
        {"request_id": uuid4().hex, "question": whole_question, "created_at": created_at}
    )
    omitted = max(0, len(requests) - MAX_REQUESTS)
    current["requests"] = requests[-MAX_REQUESTS:]
    current["requests_omitted"] = _nonnegative_int(current.get("requests_omitted")) + omitted
    return current


def record_reference_group(
    state: Mapping[str, object],
    *,
    case_id: str,
    question: str,
    receipt_ids: Sequence[str],
    validated: bool,
    at: str,
    runtime_instance_id: str | None = None,
) -> dict[str, object]:
    """Retain one admitted receipt group after a successful validated turn."""

    inherited_runtime_id = state.get("runtime_instance_id")
    scoped_runtime_id = (
        runtime_instance_id
        if runtime_instance_id is not None
        else (
            inherited_runtime_id
            if isinstance(inherited_runtime_id, str)
            else DEFAULT_RUNTIME_INSTANCE_ID
        )
    )
    current = restore_state(state, case_id=case_id, runtime_instance_id=scoped_runtime_id)
    whole_question = _whole_text(question)
    created_at = _identifier(at)
    admitted_ids = _receipt_ids_from(receipt_ids)
    if not validated or not whole_question or not created_at or not admitted_ids:
        return current

    conversation_id = str(current["conversation_id"])
    groups = _reference_groups_from(
        current.get("reference_groups"),
        case_id=str(current["case_id"]),
        runtime_instance_id=str(current["runtime_instance_id"]),
        conversation_id=conversation_id,
    )
    groups.append(
        {
            "case_id": current["case_id"],
            "runtime_instance_id": current["runtime_instance_id"],
            "conversation_id": conversation_id,
            "question": whole_question,
            "receipt_ids": admitted_ids,
            "created_at": created_at,
            "provenance": "runtime_validated",
        }
    )
    current["reference_groups"] = groups[-MAX_REFERENCE_GROUPS:]
    return current


def latest_reference_group(
    state: Mapping[str, object],
    *,
    case_id: str | None = None,
    runtime_instance_id: str | None = None,
) -> dict[str, object] | None:
    """Return the newest valid group, skipping intervening turns with no refs."""

    if state.get("schema_version") != SCHEMA_VERSION:
        return None
    scoped_case_id = (
        _identifier(case_id) if case_id is not None else _identifier(state.get("case_id"))
    )
    scoped_runtime_id = (
        _identifier(runtime_instance_id)
        if runtime_instance_id is not None
        else _identifier(state.get("runtime_instance_id"))
    )
    conversation_id = _identifier(state.get("conversation_id"))
    if (
        not scoped_case_id
        or not scoped_runtime_id
        or not conversation_id
        or state.get("case_id") != scoped_case_id
        or state.get("runtime_instance_id") != scoped_runtime_id
    ):
        return None
    groups = _reference_groups_from(
        state.get("reference_groups"),
        case_id=scoped_case_id,
        runtime_instance_id=scoped_runtime_id,
        conversation_id=conversation_id,
    )
    return dict(groups[-1]) if groups else None


def rejoin_reference_group(
    group: Mapping[str, object],
    *,
    case_id: str,
    current_receipt_ids: Sequence[str],
    source_sequence: object = None,
) -> dict[str, object]:
    """Rejoin a prior candidate group against current receipt identities.

    The result stays a candidate set. Missing members and duplicate current
    identities remain visible rather than silently selecting a survivor.
    """

    scoped_case_id = _identifier(case_id)
    prior = _receipt_ids_from(group.get("receipt_ids"))
    question = _whole_text(group.get("question"))
    if (
        group.get("case_id") != scoped_case_id
        or group.get("provenance") != "runtime_validated"
        or not prior
        or not question
    ):
        return {"status": "UNAVAILABLE", "case_id": scoped_case_id}

    counts: dict[str, int] = {}
    for receipt_id in current_receipt_ids:
        safe_receipt_id = _identifier(receipt_id)
        if safe_receipt_id:
            counts[safe_receipt_id] = counts.get(safe_receipt_id, 0) + 1
    current = [receipt_id for receipt_id in prior if receipt_id in counts]
    missing = [receipt_id for receipt_id in prior if receipt_id not in counts]
    ambiguous = [receipt_id for receipt_id in prior if counts.get(receipt_id, 0) > 1]
    status = (
        "CHANGED"
        if missing
        else (
            "AMBIGUOUS"
            if ambiguous
            else ("ONE_CANDIDATE" if len(current) == 1 else "MULTIPLE_CANDIDATES")
        )
    )
    return {
        "status": status,
        "case_id": scoped_case_id,
        "question": question,
        "previous_receipt_ids": prior,
        "current_receipt_ids": current,
        "missing_receipt_ids": missing,
        "ambiguous_receipt_ids": ambiguous,
        "source_sequence": source_sequence,
        "provenance": "runtime_validated",
        "authority": (
            "Runtime-validated prior references are candidate identifiers only, not current "
            "facts, selected receipts, approvals, or proof that an earlier answer was correct."
        ),
    }


def build_model_context(
    requests: Sequence[Mapping[str, object]],
    *,
    current_question: str,
    authority_context: str = "",
    max_chars: int = 4000,
    prefix: str = (
        "Continue the evidence conversation below. Treat prior user requests only as context, "
        "not as current evidence or a list of questions to answer again. Resolve references in "
        "the new question, but answer ONLY the newest question. Do not answer from the transcript "
        "alone."
    ),
    history_header: str = "\n\nPrior conversation:\n",
    current_prefix: str = "\n\nNewest human question: ",
) -> dict[str, object]:
    """Pack complete user requests within a strict model-input character budget."""

    if max_chars <= 0:
        return {
            "prompt": "",
            "included_questions": [],
            "included_request_ids": [],
            "omitted_requests": 0,
            "input_limit": True,
        }
    whole_current = _whole_text(current_question)
    if not whole_current:
        return {
            "prompt": "",
            "included_questions": [],
            "included_request_ids": [],
            "omitted_requests": 0,
            "input_limit": True,
        }
    # Authority text is produced by the gateway from a bounded human request.
    # If an integration provides a larger string, fail closed instead of cutting it.
    authority = authority_context if isinstance(authority_context, str) else ""
    base = f"{prefix}{authority}{current_prefix}{whole_current}"
    if len(base) > max_chars:
        return {
            "prompt": "",
            "included_questions": [],
            "included_request_ids": [],
            "omitted_requests": 0,
            "input_limit": True,
        }

    prior: list[dict[str, str]] = []
    for request in requests:
        if not isinstance(request, Mapping):
            continue
        request_id = _identifier(request.get("request_id"))
        question = _whole_text(request.get("question"))
        if request_id and question:
            prior.append({"request_id": request_id, "question": question})

    selected_reversed: list[dict[str, str]] = []
    for request in reversed(prior):
        selected = [request, *selected_reversed]
        transcript = "\n".join(f"Human: {item['question']}" for item in selected)
        candidate = (
            f"{prefix}{authority}{history_header}{transcript}{current_prefix}{whole_current}"
        )
        if len(candidate) <= max_chars:
            selected_reversed = selected
        else:
            break

    selected = selected_reversed
    if selected:
        transcript = "\n".join(f"Human: {item['question']}" for item in selected)
        prompt = f"{prefix}{authority}{history_header}{transcript}{current_prefix}{whole_current}"
    else:
        prompt = base
    return {
        "prompt": prompt,
        "included_questions": [item["question"] for item in selected],
        "included_request_ids": [item["request_id"] for item in selected],
        "omitted_requests": len(prior) - len(selected),
        "input_limit": False,
    }


def public_state(
    state: Mapping[str, object],
    case_id: str,
    *,
    runtime_instance_id: str | None = None,
) -> dict[str, object]:
    """Return display-safe user context without any retained assistant response."""

    if state.get("case_id") != case_id:
        return {"human_intent": {}, "human_requests": [], "dialogue_context": {}}

    versioned = state.get("schema_version") == SCHEMA_VERSION
    if runtime_instance_id is not None and state.get("runtime_instance_id") != runtime_instance_id:
        return {"human_intent": {}, "human_requests": [], "dialogue_context": {}}

    intent = _authority_from(state)
    requests = _requests_from(state.get("requests"))
    context: dict[str, object] = {}
    if versioned:
        conversation_id = _identifier(state.get("conversation_id"))
        stored_runtime_id = _identifier(state.get("runtime_instance_id"))
        if conversation_id and stored_runtime_id:
            context = {
                "schema_version": SCHEMA_VERSION,
                "runtime_instance_id": stored_runtime_id,
                "case_id": case_id,
                "conversation_id": conversation_id,
                "requests_omitted": _nonnegative_int(state.get("requests_omitted")),
                "reference_groups": _reference_groups_from(
                    state.get("reference_groups"),
                    case_id=case_id,
                    runtime_instance_id=stored_runtime_id,
                    conversation_id=conversation_id,
                ),
            }
    return {
        "human_intent": {"case_id": case_id, **intent} if intent else {},
        "human_requests": requests,
        "dialogue_context": context,
    }
