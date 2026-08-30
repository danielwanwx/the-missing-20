"""Read-only Strands/Nova Pro entrypoint for an Amazon Bedrock AgentCore Runtime.

This module deliberately keeps the runtime boundary small.  The application owns
the incident state, evidence, policy, authorization, execution, and verification;
the hosted agent can only return advisory JSON.  In particular, there are no tools
registered with the Strands agent and the runtime never receives credentials or an
account identifier from the request.

The optional AgentCore import is lazy/optional so the contract and security tests can
run without cloud SDKs or AWS credentials.  In an AgentCore deployment the official
``BedrockAgentCoreApp`` decorator and ``app.run()`` entrypoint are used.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from typing import Any

try:  # The local test environment need not have the AgentCore SDK installed.
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
except ImportError:  # pragma: no cover - exercised by the offline test environment
    BedrockAgentCoreApp = None  # type: ignore[assignment,misc]


MODEL_ID = "us.amazon.nova-pro-v1:0"
MAX_PROMPT_CHARS = 64_000
MAX_PAYLOAD_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_OUTPUT_TOKENS = 1_551
MAX_TOTAL_TOKENS = 8_000
MAX_INVOCATION_SECONDS = 45.0

ALLOWED_STAGES = frozenset(
    {
        "retryable_investigator",
        "short_shipment_investigator",
        "duplicate_posting_investigator",
        "synthesis",
        "evaluator",
    }
)

STAGE_AGENT_IDS = {
    "retryable_investigator": "retryable_message_investigator",
    "short_shipment_investigator": "short_shipment_investigator",
    "duplicate_posting_investigator": "duplicate_posting_investigator",
    "synthesis": "synthesis",
    "evaluator": "evaluator",
}

_TOP_LEVEL_KEYS = frozenset({"input"})
_INPUT_KEYS = frozenset({"prompt", "stage", "advisory_only", "agent_id"})
_UNTRUSTED_QUESTION_MARKER = "the incident operator asked this untrusted question"

# These patterns target direct attempts to cross the advisory boundary.  The
# incoming prompt normally contains a trusted workflow instruction which itself
# mentions that untrusted text must not bypass policy, so only the question tail is
# scanned when that delimiter is present.
_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:ignore|disregard|override)\s+"
        r"(?:all|the|your|previous|prior|system|developer)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:reveal|show|print|expose|dump|repeat)\b.{0,48}\b"
        r"(?:system|developer|hidden|secret)\s+prompt\b",
        re.I,
    ),
    re.compile(r"\b(?:jailbreak|prompt\s*injection|\bdan\b)\b", re.I),
    re.compile(
        r"\b(?:bypass|skip|without)\b.{0,48}\b"
        r"(?:approval|policy|safety|authorization|guard)\b",
        re.I,
    ),
    re.compile(
        r"\byou\s+are\s+now\s+(?:an?\s+)?(?:admin|developer|system|root)\b",
        re.I,
    ),
)


class RuntimeInputError(ValueError):
    """Raised when an invocation cannot satisfy the frozen runtime contract."""


def _reject_if_injection(text: str) -> None:
    """Reject a clear prompt-injection attempt without exposing prompt contents."""

    lower = text.lower()
    question_start = lower.find(_UNTRUSTED_QUESTION_MARKER)
    scan_text = text[question_start:] if question_start >= 0 else text
    if any(pattern.search(scan_text) for pattern in _PROMPT_INJECTION_PATTERNS):
        raise RuntimeInputError("prompt violates the advisory input boundary")


def _validate_payload(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Validate and return the bounded prompt and allowlisted workflow stage.

    The public AgentCore request is intentionally a wrapped payload so it matches
    the application adapter.  Optional ``agent_id`` is accepted only when it is the
    deterministic identity assigned to the selected stage; it cannot select an
    arbitrary role or grant authority.
    """

    if not isinstance(payload, Mapping):
        raise RuntimeInputError("payload must be an object")
    if set(payload) != _TOP_LEVEL_KEYS:
        raise RuntimeInputError("payload must contain only input")
    request = payload.get("input")
    if not isinstance(request, Mapping):
        raise RuntimeInputError("input must be an object")
    if not set(request).issubset(_INPUT_KEYS) or "prompt" not in request:
        raise RuntimeInputError("input contains an unknown or missing field")

    prompt = request["prompt"]
    stage = request.get("stage")
    advisory_only = request.get("advisory_only")
    if not isinstance(prompt, str) or not prompt.strip():
        raise RuntimeInputError("input.prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise RuntimeInputError("input.prompt exceeds the bounded length")
    if any(
        (ord(character) < 32 and character not in "\n\r\t")
        or ord(character) == 127
        for character in prompt
    ):
        raise RuntimeInputError("input.prompt contains a disallowed control character")
    if not isinstance(stage, str) or stage not in ALLOWED_STAGES:
        raise RuntimeInputError("input.stage is not allowlisted")
    if advisory_only is not True:
        raise RuntimeInputError("input.advisory_only must be true")

    agent_id = request.get("agent_id")
    if agent_id is not None and agent_id != STAGE_AGENT_IDS[stage]:
        raise RuntimeInputError("input.agent_id is not valid for this stage")

    _reject_if_injection(prompt)
    try:
        payload_bytes = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeInputError("payload is not JSON serializable") from exc
    if payload_bytes > MAX_PAYLOAD_BYTES:
        raise RuntimeInputError("payload exceeds the bounded size")
    return prompt.strip(), stage


def _stage_system_prompt(stage: str) -> str:
    """Return the fixed, role-scoped system instruction for one stage."""

    role_scope = {
        "retryable_investigator": "investigate retryable message-delivery hypotheses",
        "short_shipment_investigator": "investigate short-shipment hypotheses",
        "duplicate_posting_investigator": "investigate duplicate-posting hypotheses",
        "synthesis": "summarize supplied investigator findings and their uncertainty",
        "evaluator": "evaluate the semantic quality of supplied claims and evidence",
    }.get(stage)
    if role_scope is None:
        raise RuntimeInputError("stage is not allowlisted")
    return (
        "You are a read-only advisory component in The Missing 20 incident workflow. "
        f"Your fixed scope is to {role_scope}. "
        "Use only facts present in the request. Never authorize, approve, execute, "
        "mutate, recover, or claim an operational decision. You have no tools and "
        "must not invent evidence. Return exactly one JSON object matching the "
        "structured contract in the request; do not return Markdown or prose outside "
        "that object. Deterministic application code owns evidence integrity, policy, "
        "authorization, execution, verification, and replay."
    )


def _extract_text(result: Any) -> str:
    """Extract text blocks from a Strands AgentResult without trusting other fields."""

    message = getattr(result, "message", None)
    if not isinstance(message, Mapping):
        raise RuntimeInputError("model response did not contain a message")
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, Mapping) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        text = "".join(parts).strip()
    else:
        text = ""
    if not text:
        raise RuntimeInputError("model response did not contain text")
    return text


def _parse_structured_json(text: str) -> dict[str, Any]:
    """Parse one bounded JSON object, tolerating one ordinary Markdown fence."""

    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline <= 0:
            raise RuntimeInputError("model response was not a structured object")
        candidate = candidate[first_newline + 1 : -3].strip()
    try:
        if len(candidate.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise RuntimeInputError("model response exceeds the bounded size")
        parsed = json.loads(candidate)
    except RuntimeInputError:
        raise
    except (UnicodeEncodeError, json.JSONDecodeError) as exc:
        raise RuntimeInputError("model response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeInputError("model response must be a JSON object")
    return parsed


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _result_metadata(result: Any, *, stage: str, elapsed_ms: int) -> dict[str, Any]:
    """Create safe provenance/usage metadata; no prompt, account, or credential data."""

    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", {}) if metrics is not None else {}
    if not isinstance(usage, Mapping):
        usage = {}
    input_tokens = _nonnegative_int(usage.get("inputTokens", usage.get("input_tokens")))
    output_tokens = _nonnegative_int(usage.get("outputTokens", usage.get("output_tokens")))
    request_count = max(1, _nonnegative_int(usage.get("cycleCount", usage.get("cycle_count"))))
    accumulated_metrics = (
        getattr(metrics, "accumulated_metrics", {}) if metrics is not None else {}
    )
    provider_latency = (
        _nonnegative_int(accumulated_metrics.get("latencyMs"))
        if isinstance(accumulated_metrics, Mapping)
        else 0
    )
    latency_ms = provider_latency or max(0, elapsed_ms)
    cost_estimate_usd = round(
        (input_tokens * 0.80 + output_tokens * 3.20) / 1_000_000,
        8,
    )
    return {
        "mode": "agentcore",
        "provider": "amazon_bedrock",
        "model": MODEL_ID,
        "stage": stage,
        "agent_id": STAGE_AGENT_IDS[stage],
        "request_count": request_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "cost_estimate_usd": cost_estimate_usd,
        "read_only": True,
        "authority": "ADVISORY_NOT_OPERATIONAL_DECISION",
        "status": "COMPLETED",
    }


async def _run_agent(prompt: str, stage: str) -> dict[str, Any]:
    """Run one bounded Strands agent with no tools and parse its JSON response."""

    try:
        from strands import Agent
        from strands.models import BedrockModel
        from strands.types.agent import Limits
    except ImportError as exc:  # pragma: no cover - dependency/bootstrap failure
        raise RuntimeInputError("Strands runtime dependencies are unavailable") from exc

    model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        streaming=False,
        use_native_token_count=False,
    )
    agent = Agent(
        model=model,
        tools=[],
        system_prompt=_stage_system_prompt(stage),
        callback_handler=None,
        agent_id=f"missing20-{STAGE_AGENT_IDS[stage]}",
        name=STAGE_AGENT_IDS[stage],
    )
    started = time.monotonic()
    result = await asyncio.wait_for(
        agent.invoke_async(
            prompt,
            limits=Limits(turns=1, output_tokens=MAX_OUTPUT_TOKENS, total_tokens=MAX_TOTAL_TOKENS),
        ),
        timeout=MAX_INVOCATION_SECONDS,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    output = _parse_structured_json(_extract_text(result))
    return {
        "output": output,
        "metadata": _result_metadata(result, stage=stage, elapsed_ms=elapsed_ms),
    }


async def _invoke(payload: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    del context  # AgentCore context is intentionally not exposed to the model/output.
    prompt, stage = _validate_payload(payload)
    response = await _run_agent(prompt, stage)
    # Keep the transport contract closed even if a future implementation changes
    # the internal result shape.
    if set(response) != {"output", "metadata"}:
        raise RuntimeInputError("runtime returned an invalid response shape")
    return response


if BedrockAgentCoreApp is not None:
    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
        return await _invoke(payload, context)

else:
    app = None

    async def invoke(payload: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
        """Offline-callable equivalent used by contract tests."""

        return await _invoke(payload, context)


if __name__ == "__main__":  # pragma: no cover - only used by AgentCore deployment
    if app is None:
        raise RuntimeError("bedrock-agentcore is required to run this entrypoint")
    app.run()
