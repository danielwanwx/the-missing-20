"""Typed, redacted events exposed by the local experiment API."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, JsonValue

from the_missing_20.domain.models import ContractModel, NonEmptyStr, PositiveInt


class PublicEventType(StrEnum):
    """Public vocabulary shared by Dashboard and Agent Workspace projections."""

    # ``TELEMETRY_OBSERVED`` is an observation from the synthetic enterprise
    # source.  It intentionally lives in the same ordered ledger as incident
    # lifecycle events so the browser can prove that motion came from the
    # backend stream rather than from a client-side timer.
    TELEMETRY_OBSERVED = "telemetry.observed"
    # Scenario Lab changes the synthetic source first. The detector observes
    # that fact in a later event; a UI control must not claim an incident.
    SOURCE_CONDITION_INJECTED = "source.condition.injected"
    INCIDENT_DETECTED = "incident.detected"
    INVESTIGATION_STARTED = "investigation.started"
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
    RECOVERY_PREPARED = "recovery.prepared"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RECORDED = "approval.recorded"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    VERIFICATION_COMPLETED = "verification.completed"
    CHAT_MESSAGE = "copilot.message"
    PROVIDER_DEGRADED = "provider.degraded"
    WORKFLOW_BLOCKED = "workflow.blocked"


class PublicIncidentEvent(ContractModel):
    """One durable event safe to send to an untrusted browser.

    ``payload`` is display-oriented and intentionally contains no prompts, raw
    provider messages, or private credentials.  The server assigns ``sequence``
    and ``event_id`` under the ledger lock; clients must not invent either value.
    """

    schema_version: Literal["public-incident-event/v1"] = "public-incident-event/v1"
    event_id: NonEmptyStr
    incident_id: NonEmptyStr
    trace_id: NonEmptyStr
    sequence: PositiveInt
    case_version: int = Field(ge=0)
    event_type: PublicEventType
    actor: NonEmptyStr
    status: NonEmptyStr
    occurred_at: AwareDatetime
    correlation_id: NonEmptyStr
    idempotency_key: NonEmptyStr
    payload: Annotated[dict[NonEmptyStr, JsonValue], Field(default_factory=dict)]

    @property
    def event(self) -> PublicEventType:
        """Compatibility alias used by small clients and test fixtures."""

        return self.event_type
