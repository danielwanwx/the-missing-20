"""Rehydrate admitted read results for the private fresh-synthesis diagnostic.

The diagnostic deliberately starts a second Agent after source acquisition.  It
keeps the real initial user request plus actual read tool-use/result pairs, but
never acquisition assistant prose, blocked correlation attempts, policy output,
or a fabricated tool result.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class FreshSynthesisContextError(ValueError):
    """The admitted read boundary cannot be represented safely in a new context."""


@dataclass(frozen=True, slots=True)
class FreshSynthesisContext:
    """Only the authenticated source-result history a new synthesis Agent receives."""

    messages: list[dict[str, Any]]
    source_payload_sha256: dict[str, str]
    tool_result_sha256: dict[str, str]
    message_sha256: str
    provenance_pairs_valid: bool
    excluded_blocked_correlations: int
    preserved_acquisition_user_text_blocks: int
    omitted_assistant_text_blocks: int
    omitted_user_text_blocks: int

    def audit_metadata(self) -> dict[str, Any]:
        """Return digest-only information suitable for the private diagnostic report."""

        return {
            "source_payload_sha256": dict(self.source_payload_sha256),
            "tool_result_sha256": dict(self.tool_result_sha256),
            "message_sha256": self.message_sha256,
            "message_sha256_scope": (
                "canonical application context before Bedrock SDK request formatting or "
                "retry normalization"
            ),
            "provenance_pairs_valid": self.provenance_pairs_valid,
            "excluded_blocked_correlations": self.excluded_blocked_correlations,
            "preserved_acquisition_user_text_blocks": self.preserved_acquisition_user_text_blocks,
            "omitted_assistant_text_blocks": self.omitted_assistant_text_blocks,
            "omitted_user_text_blocks": self.omitted_user_text_blocks,
            "message_count": len(self.messages),
        }


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FreshSynthesisContextError("admitted source payload is not canonical JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FreshSynthesisContextError(f"{label} must be an object")
    return value


def _tool_result_text(result: Mapping[str, Any]) -> str:
    status = result.get("status")
    if status is not None and status != "success":
        raise FreshSynthesisContextError("admitted tool result did not complete successfully")
    content = result.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)) or len(content) != 1:
        raise FreshSynthesisContextError("admitted tool result must contain one exact text payload")
    block = _mapping(content[0], label="admitted tool-result content")
    text = block.get("text")
    if not isinstance(text, str) or set(block) != {"text"}:
        raise FreshSynthesisContextError(
            "admitted tool result must contain only its exact text payload"
        )
    return text


def _tool_use_details(block: Mapping[str, Any]) -> tuple[str, str] | None:
    raw = block.get("toolUse")
    if raw is None:
        return None
    tool_use = _mapping(raw, label="tool use")
    name = tool_use.get("name")
    tool_use_id = tool_use.get("toolUseId")
    if not isinstance(name, str) or not name:
        raise FreshSynthesisContextError("tool use lacks a tool name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise FreshSynthesisContextError("tool use lacks a tool-use ID")
    return name, tool_use_id


def _tool_result_details(block: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    raw = block.get("toolResult")
    if raw is None:
        return None
    result = _mapping(raw, label="tool result")
    tool_use_id = result.get("toolUseId")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise FreshSynthesisContextError("tool result lacks a tool-use ID")
    return tool_use_id, result


def _contains_forbidden_key(value: Any, forbidden: frozenset[str]) -> bool:
    if isinstance(value, Mapping):
        return any(
            isinstance(key, str)
            and (key in forbidden or _contains_forbidden_key(nested, forbidden))
            for key, nested in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def _is_blocked_correlation(
    tool_name: str, result: Mapping[str, Any], correlation_tool_name: str
) -> bool:
    if tool_name != correlation_tool_name:
        return False
    try:
        parsed = json.loads(_tool_result_text(result))
    except json.JSONDecodeError as exc:
        raise FreshSynthesisContextError("correlation result is not JSON") from exc
    return isinstance(parsed, Mapping) and parsed.get("status") == "BLOCKED"


def _validate_payload(
    *,
    tool_name: str,
    result: Mapping[str, Any],
    expected_payload: Mapping[str, Any],
) -> tuple[str, str]:
    """Prove the actual returned payload retains the entire admitted source payload.

    The live reader appends only ``query_received`` to its scoped source object.
    That query is retained in the copied result, while equality and source hashes
    compare the unchanged admitted payload underneath it.
    """

    try:
        actual = json.loads(_tool_result_text(result))
    except json.JSONDecodeError as exc:
        raise FreshSynthesisContextError(
            f"admitted {tool_name} result is not a JSON source payload"
        ) from exc
    if not isinstance(actual, Mapping):
        raise FreshSynthesisContextError(f"admitted {tool_name} result is not an object")
    actual_without_query = dict(actual)
    query = actual_without_query.pop("query_received", None)
    if not isinstance(query, str):
        raise FreshSynthesisContextError(f"admitted {tool_name} result lacks its received query")
    if _canonical_json(actual_without_query) != _canonical_json(expected_payload):
        raise FreshSynthesisContextError(
            f"admitted {tool_name} result differs from the frozen source payload"
        )
    return _sha256(_canonical_json(expected_payload)), _sha256(
        _tool_result_text(result).encode("utf-8")
    )


def build_fresh_synthesis_context(
    messages: Sequence[Mapping[str, Any]],
    *,
    expected_payloads: Mapping[str, Mapping[str, Any]],
    required_tool_names: Sequence[str],
    prohibited_tool_names: Sequence[str],
) -> FreshSynthesisContext:
    """Copy the original acquisition request and completed admitted pairs into a fresh context.

    This function is deliberately strict: it accepts exact, completed source
    reads only.  It does not produce a fallback source message when a real tool
    result is absent, and it does not promote a ``BLOCKED`` correlation attempt
    into the new Agent's history.
    """

    required = tuple(required_tool_names)
    prohibited = frozenset(prohibited_tool_names)
    if not required or len(required) != len(set(required)):
        raise FreshSynthesisContextError("required tool names must be unique and non-empty")
    if set(required).intersection(prohibited):
        raise FreshSynthesisContextError("required tools include a prohibited authority tool")
    if set(expected_payloads) != set(required):
        raise FreshSynthesisContextError(
            "expected payloads must contain exactly the admitted tools"
        )
    if any(not isinstance(expected_payloads[name], Mapping) for name in required):
        raise FreshSynthesisContextError("expected tool payloads must be objects")
    oracle_keys = frozenset({"expected_disposition", "expected_safe_next_step"})
    if _contains_forbidden_key(expected_payloads, oracle_keys):
        raise FreshSynthesisContextError(
            "admitted source payloads contain an expected-answer oracle"
        )

    pending: dict[str, tuple[dict[str, Any], str]] = {}
    groups: list[dict[str, Any]] = []
    completed: set[str] = set()
    observed_tool_use_ids: set[str] = set()
    observed_tool_result_ids: set[str] = set()
    blocked_correlations = 0
    preserved_acquisition_user_text_blocks = 0
    omitted_assistant_text_blocks = 0
    omitted_user_text_blocks = 0
    correlation_name = next((name for name in required if "reconcile" in name), None)
    copied_messages: list[dict[str, Any]] = []
    seen_admitted_tool_use = False

    for message in messages:
        source_message = _mapping(message, label="agent message")
        role = source_message.get("role")
        content = source_message.get("content")
        if role not in {"assistant", "user"}:
            raise FreshSynthesisContextError("agent message has an invalid role")
        if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
            raise FreshSynthesisContextError("agent message has invalid content")
        if role == "user" and not seen_admitted_tool_use:
            original_request_blocks = [
                copy.deepcopy(_mapping(block, label="message content"))
                for block in content
                if isinstance(block, Mapping) and "text" in block
            ]
            if original_request_blocks:
                if copied_messages:
                    raise FreshSynthesisContextError(
                        "fresh synthesis context requires one original acquisition user message"
                    )
                copied_messages.append({"role": "user", "content": original_request_blocks})
                preserved_acquisition_user_text_blocks += len(original_request_blocks)
        for raw_block in content:
            block = _mapping(raw_block, label="message content")
            if "text" in block:
                if role == "assistant":
                    omitted_assistant_text_blocks += 1
                elif seen_admitted_tool_use:
                    omitted_user_text_blocks += 1
            tool_use = _tool_use_details(block)
            if tool_use is not None:
                name, tool_use_id = tool_use
                if tool_use_id in observed_tool_use_ids:
                    raise FreshSynthesisContextError("tool-use ID was repeated")
                if tool_use_id in observed_tool_result_ids:
                    raise FreshSynthesisContextError("tool result appeared before its tool use")
                observed_tool_use_ids.add(tool_use_id)
                if name in prohibited:
                    raise FreshSynthesisContextError(
                        "acquisition history included a prohibited authority tool"
                    )
                if name in required:
                    if role != "assistant":
                        raise FreshSynthesisContextError(
                            "admitted tool use must have assistant role"
                        )
                    if tool_use_id in pending:
                        raise FreshSynthesisContextError("admitted tool-use ID was repeated")
                    if not seen_admitted_tool_use:
                        if not copied_messages:
                            raise FreshSynthesisContextError(
                                "fresh synthesis context requires the original acquisition "
                                "user message"
                            )
                        seen_admitted_tool_use = True
                    group = next(
                        (item for item in groups if item["message"] is source_message),
                        None,
                    )
                    if group is None:
                        group = {
                            "message": source_message,
                            "uses": [],
                            "results": {},
                            "result_order": [],
                        }
                        groups.append(group)
                    copied_use = copy.deepcopy(block)
                    group["uses"].append((tool_use_id, name, copied_use))
                    pending[tool_use_id] = (group, name)
                continue
            tool_result = _tool_result_details(block)
            if tool_result is None:
                continue
            tool_use_id, result = tool_result
            if tool_use_id in observed_tool_result_ids:
                raise FreshSynthesisContextError("tool-result ID was repeated")
            observed_tool_result_ids.add(tool_use_id)
            pending_pair = pending.get(tool_use_id)
            if pending_pair is None:
                # A non-admitted result must not be imported; any result that
                # claims a required ID without its real preceding use is unsafe.
                continue
            group, name = pending_pair
            if role != "user":
                raise FreshSynthesisContextError("admitted tool result must have user role")
            # A transport-level error is never an admitted source payload, even
            # if its textual body happens to parse as JSON.
            _tool_result_text(result)
            if _is_blocked_correlation(name, result, correlation_name or ""):
                blocked_correlations += 1
                pending.pop(tool_use_id)
                continue
            if name in completed:
                raise FreshSynthesisContextError("admitted source tool completed more than once")
            expected = _mapping(expected_payloads[name], label=f"expected {name} payload")
            source_hash, result_hash = _validate_payload(
                tool_name=name,
                result=result,
                expected_payload=expected,
            )
            group["results"][tool_use_id] = copy.deepcopy(block)
            group["result_order"].append(tool_use_id)
            group.setdefault("source_hashes", {})[name] = source_hash
            group.setdefault("result_hashes", {})[name] = result_hash
            completed.add(name)
            pending.pop(tool_use_id)

    missing = sorted(set(required).difference(completed))
    if missing:
        raise FreshSynthesisContextError(
            "missing completed admitted tool result: " + ", ".join(missing)
        )
    if pending:
        unresolved = sorted(name for _group, name in pending.values() if name in required)
        if unresolved:
            raise FreshSynthesisContextError(
                "admitted tool use has no matching result: " + ", ".join(unresolved)
            )

    if not copied_messages:
        raise FreshSynthesisContextError(
            "fresh synthesis context requires the original acquisition user message"
        )
    source_hashes: dict[str, str] = {}
    result_hashes: dict[str, str] = {}
    for group in groups:
        included_uses = [
            (tool_use_id, name, use_block)
            for tool_use_id, name, use_block in group["uses"]
            if tool_use_id in group["results"]
        ]
        if not included_uses:
            continue
        copied_messages.append(
            {
                "role": "assistant",
                "content": [use_block for _tool_use_id, _name, use_block in included_uses],
            }
        )
        copied_messages.append(
            {
                "role": "user",
                "content": [group["results"][tool_use_id] for tool_use_id in group["result_order"]],
            }
        )
        source_hashes.update(group.get("source_hashes", {}))
        result_hashes.update(group.get("result_hashes", {}))

    if set(source_hashes) != set(required):  # defensive: copied-pair ordering cannot widen scope
        raise FreshSynthesisContextError("fresh synthesis context lost an admitted source payload")
    if _contains_forbidden_key(copied_messages, oracle_keys):
        raise FreshSynthesisContextError(
            "fresh synthesis context contains an expected-answer oracle"
        )
    if any(name in json.dumps(copied_messages, ensure_ascii=False) for name in prohibited):
        raise FreshSynthesisContextError(
            "fresh synthesis context contains a prohibited authority tool"
        )

    canonical_messages = _canonical_json(copied_messages)
    return FreshSynthesisContext(
        messages=copied_messages,
        source_payload_sha256=source_hashes,
        tool_result_sha256=result_hashes,
        message_sha256=_sha256(canonical_messages),
        provenance_pairs_valid=True,
        excluded_blocked_correlations=blocked_correlations,
        preserved_acquisition_user_text_blocks=preserved_acquisition_user_text_blocks,
        omitted_assistant_text_blocks=omitted_assistant_text_blocks,
        omitted_user_text_blocks=omitted_user_text_blocks,
    )
