"""Typed operation events emitted by the real agent/tool execution path.

The agent package deliberately knows nothing about the public SQLite ledger.  It
emits this small, redacted operation contract instead; the experiment session
adapts it to its durable ``PublicIncidentEvent`` stream.  Keeping the boundary
here makes it possible to test event timing with a blocking observer without
starting a web server or a model provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class AgentOperationEventType(StrEnum):
    """Operation vocabulary produced by the harness and its audited tools."""

    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    EVIDENCE_RETURNED = "evidence.returned"
    AGENT_HANDOFF = "agent.handoff"
    SYNTHESIS_STARTED = "synthesis.started"
    SYNTHESIS_COMPLETED = "synthesis.completed"
    EVALUATION_STARTED = "evaluation.started"
    EVALUATION_COMPLETED = "evaluation.completed"


@dataclass(frozen=True, slots=True)
class AgentOperationEvent:
    """One redacted event at the point an operation actually occurs.

    ``operation_id`` is stable within one harness run and is used by the session
    adapter as the durable event idempotency key.  Payloads are display-oriented;
    raw prompts, model messages, and credentials are never part of this contract.
    """

    event_type: AgentOperationEventType
    case_id: str
    trace_id: str
    actor: str
    operation_id: str
    status: str
    correlation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    stage: str | None = None


class AgentEventSink(Protocol):
    """Durable or test observer for actual harness operations."""

    def emit(self, event: AgentOperationEvent) -> None:
        """Persist/observe an event before execution is allowed to continue."""
