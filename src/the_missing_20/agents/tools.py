"""The only tools that can be placed on a Milestone 4 agent."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from the_missing_20.agents.events import (
    AgentEventSink,
    AgentOperationEvent,
    AgentOperationEventType,
)
from the_missing_20.agents.schemas import (
    REQUIRED_AUTHORITATIVE_SOURCES,
    KnowledgeCitation,
    KnowledgeUse,
)
from the_missing_20.domain.models import EvidenceItem
from the_missing_20.ports.knowledge import KnowledgeRepository


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class KnowledgeProvenanceError(ValueError):
    """A knowledge-tool audit cannot prove a safe public citation."""


class EvidenceReadAuditError(KnowledgeProvenanceError):
    """An evidence-read audit cannot prove that a referenced record was read."""


_KNOWLEDGE_PROVENANCE_FIELDS = frozenset(
    {"knowledge_id", "version", "allowed_use", "content_digest"}
)


def _normalize_knowledge_record(value: Mapping[str, Any]) -> dict[str, str]:
    """Keep only the exact provenance tuple required for public citations.

    Raw excerpts, titles, paths, and model text are intentionally rejected at this
    boundary.  They belong to the ephemeral tool response, not the normalized audit.
    """

    if set(value) != _KNOWLEDGE_PROVENANCE_FIELDS:
        raise KnowledgeProvenanceError(
            "knowledge audit record must contain only ID, version, allowed use, and digest"
        )
    normalized: dict[str, str] = {}
    for key in _KNOWLEDGE_PROVENANCE_FIELDS:
        item = value[key]
        if not isinstance(item, str) or not item.strip():
            raise KnowledgeProvenanceError(f"knowledge audit field {key} must be non-empty text")
        normalized[key] = item
    try:
        KnowledgeUse(normalized["allowed_use"])
    except ValueError as exc:
        raise KnowledgeProvenanceError(
            "knowledge audit contains an unsupported allowed use"
        ) from exc
    return normalized


@dataclass(slots=True)
class ToolAudit:
    """Normalized tool-call audit data; no raw prompts or model history are retained."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    event_sink: AgentEventSink | None = None
    case_id: str | None = None
    trace_id: str | None = None
    actor: str = "agent"
    stage: str = "investigator"
    _next_operation: int = field(default=1, init=False, repr=False)

    def start(self, *, name: str, arguments: dict[str, Any]) -> str:
        """Emit a start event before an audited tool body is entered.

        Tool implementations call this before validation and before any repository
        read.  Returning the operation id lets the later audit record bind its
        completion to the exact invocation, including concurrent calls.
        """

        operation_id = f"tool:{self.stage}:{self._next_operation:04d}"
        self._next_operation += 1
        if self.event_sink is not None:
            if self.case_id is None or self.trace_id is None:
                raise ValueError("an event sink requires immutable case and trace identity")
            self.event_sink.emit(
                AgentOperationEvent(
                    event_type=AgentOperationEventType.TOOL_STARTED,
                    case_id=self.case_id,
                    trace_id=self.trace_id,
                    actor=self.actor,
                    operation_id=operation_id,
                    status="RUNNING",
                    correlation_id=operation_id,
                    stage=self.stage,
                    payload={"tool": name, "arguments": _public_arguments(arguments)},
                )
            )
        return operation_id

    def record(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        result_evidence_ids: tuple[str, ...] = (),
        result_knowledge_records: tuple[Mapping[str, Any], ...] = (),
        result_digest: str | None = None,
        error_code: str | None = None,
        duration_ms: int = 0,
        operation_id: str | None = None,
    ) -> None:
        if error_code is not None and result_knowledge_records:
            raise KnowledgeProvenanceError("failed knowledge search cannot retain result records")
        normalized_knowledge_records = tuple(
            _normalize_knowledge_record(item) for item in result_knowledge_records
        )
        call = {
            "tool": name,
            "arguments": json.loads(_canonical(arguments)),
            "result_evidence_ids": list(result_evidence_ids),
            "result_knowledge_records": [
                json.loads(_canonical(item)) for item in normalized_knowledge_records
            ],
            "result_digest": result_digest,
            "error_code": error_code,
            "duration_ms": max(0, duration_ms),
        }
        self.calls.append(call)
        if self.event_sink is not None:
            if self.case_id is None or self.trace_id is None:
                raise ValueError("an event sink requires immutable case and trace identity")
            operation_id = operation_id or f"tool:{self.stage}:audit-{len(self.calls):04d}"
            evidence_ids = tuple(str(item) for item in result_evidence_ids)
            knowledge_ids = tuple(
                str(item["knowledge_id"])
                for item in normalized_knowledge_records
                if "knowledge_id" in item
            )
            self.event_sink.emit(
                AgentOperationEvent(
                    event_type=AgentOperationEventType.TOOL_COMPLETED,
                    case_id=self.case_id,
                    trace_id=self.trace_id,
                    actor=self.actor,
                    operation_id=operation_id,
                    status="FAILED" if error_code else "COMPLETED",
                    correlation_id=operation_id,
                    stage=self.stage,
                    payload={
                        "tool": name,
                        "result_evidence_ids": list(evidence_ids),
                        "result_knowledge_ids": list(knowledge_ids),
                        "error_code": error_code,
                    },
                )
            )
            if evidence_ids:
                self.event_sink.emit(
                    AgentOperationEvent(
                        event_type=AgentOperationEventType.EVIDENCE_RETURNED,
                        case_id=self.case_id,
                        trace_id=self.trace_id,
                        actor=self.actor,
                        operation_id=f"{operation_id}:evidence",
                        status="ADMITTED",
                        correlation_id=operation_id,
                        stage=self.stage,
                        payload={"evidence_ids": list(evidence_ids)},
                    )
                )


def _public_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only safe identifiers in public operation events."""

    return {
        key: value for key, value in arguments.items() if key in {"evidence_id", "version", "query"}
    }


@dataclass(frozen=True, slots=True)
class ToolScope:
    """Immutable invocation allowlist used by both read tools."""

    case_id: str
    trace_id: str
    admitted_evidence: tuple[EvidenceItem, ...]
    allowed_evidence_ids: frozenset[str]
    knowledge: KnowledgeRepository
    knowledge_version: str
    max_evidence_reads: int = len(REQUIRED_AUTHORITATIVE_SOURCES)
    max_knowledge_searches: int = 2

    def __post_init__(self) -> None:
        known = {item.evidence_id for item in self.admitted_evidence}
        if not self.allowed_evidence_ids.issubset(known):
            raise ValueError("tool allowlist contains an unknown evidence ID")
        if any(
            item.case_id != self.case_id or item.trace_id != self.trace_id
            for item in self.admitted_evidence
        ):
            raise ValueError("tool evidence must match immutable case and trace")
        if self.max_evidence_reads != len(REQUIRED_AUTHORITATIVE_SOURCES):
            raise ValueError(
                "evidence read budget must equal the required authoritative source count"
            )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def make_read_admitted_evidence_tool(scope: ToolScope, audit: ToolAudit) -> Any:
    """Build a closure-backed Strands tool scoped to admitted evidence only."""

    try:
        from strands import tool
    except ImportError as exc:  # pragma: no cover - exercised only without M4 dependency
        raise RuntimeError("strands-agents is required for the agent harness") from exc

    by_id = {item.evidence_id: item for item in scope.admitted_evidence}
    reads = 0

    @tool
    def read_admitted_evidence(evidence_id: str) -> dict[str, Any]:
        """Read one evidence record already admitted to the current case.

        Args:
            evidence_id: Exact ID from the invocation allowlist.
        """

        nonlocal reads
        started = time.monotonic()
        arguments = {"evidence_id": evidence_id}
        operation_id = audit.start(name="read_admitted_evidence", arguments=arguments)
        if reads >= scope.max_evidence_reads:
            audit.record(
                name="read_admitted_evidence",
                arguments=arguments,
                error_code="TOOL_BUDGET_EXHAUSTED",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise ValueError("evidence read budget exhausted")
        if evidence_id not in scope.allowed_evidence_ids:
            audit.record(
                name="read_admitted_evidence",
                arguments=arguments,
                error_code="EVIDENCE_NOT_ALLOWLISTED",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise ValueError("evidence ID is not allowlisted for this invocation")
        item = by_id.get(evidence_id)
        if item is None:
            audit.record(
                name="read_admitted_evidence",
                arguments=arguments,
                error_code="EVIDENCE_NOT_FOUND",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise ValueError("evidence ID is not admitted to this case")
        reads += 1
        result = {
            "evidence_id": item.evidence_id,
            "source_type": item.source_type.value,
            "source_record_id": item.source_record_id,
            "observed_at": item.observed_at.isoformat(),
            "content_digest": item.content_digest,
            "admitted_fields": item.admitted_fields,
        }
        audit.record(
            name="read_admitted_evidence",
            arguments=arguments,
            result_evidence_ids=(item.evidence_id,),
            result_digest=_digest(result),
            duration_ms=round((time.monotonic() - started) * 1000),
            operation_id=operation_id,
        )
        return result

    return read_admitted_evidence


def make_search_synthetic_knowledge_tool(scope: ToolScope, audit: ToolAudit) -> Any:
    """Build a closure-backed, exact-version synthetic knowledge search tool."""

    try:
        from strands import tool
    except ImportError as exc:  # pragma: no cover - exercised only without M4 dependency
        raise RuntimeError("strands-agents is required for the agent harness") from exc

    searches = 0

    @tool
    def search_synthetic_knowledge(query: str, version: str) -> dict[str, Any]:
        """Search public synthetic procedures at one exact corpus version.

        Args:
            query: Short error or procedure phrase.
            version: Exact knowledge-corpus version required by the case.
        """

        nonlocal searches
        started = time.monotonic()
        arguments = {"query": query, "version": version}
        operation_id = audit.start(name="search_synthetic_knowledge", arguments=arguments)
        if searches >= scope.max_knowledge_searches:
            audit.record(
                name="search_synthetic_knowledge",
                arguments=arguments,
                error_code="TOOL_BUDGET_EXHAUSTED",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise ValueError("knowledge search budget exhausted")
        if version != scope.knowledge_version:
            audit.record(
                name="search_synthetic_knowledge",
                arguments=arguments,
                error_code="KNOWLEDGE_VERSION_MISMATCH",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise ValueError("knowledge version does not match the immutable invocation")
        searches += 1
        try:
            records = scope.knowledge.search(query, version)
        except Exception:
            audit.record(
                name="search_synthetic_knowledge",
                arguments=arguments,
                error_code="KNOWLEDGE_SEARCH_FAILED",
                duration_ms=round((time.monotonic() - started) * 1000),
                operation_id=operation_id,
            )
            raise
        result = {
            "knowledge_version": version,
            "procedural_only": True,
            "results": [
                {
                    "knowledge_id": record.knowledge_id,
                    "version": record.version,
                    "title": record.title,
                    "allowed_use": record.allowed_use,
                    "excerpt": record.excerpt,
                    "content_digest": record.content_digest,
                }
                for record in records
            ],
        }
        audit.record(
            name="search_synthetic_knowledge",
            arguments=arguments,
            result_knowledge_records=tuple(
                {
                    "knowledge_id": record.knowledge_id,
                    "version": record.version,
                    "allowed_use": record.allowed_use,
                    "content_digest": record.content_digest,
                }
                for record in records
            ),
            result_digest=_digest(result),
            duration_ms=round((time.monotonic() - started) * 1000),
            operation_id=operation_id,
        )
        return result

    return search_synthetic_knowledge


def derive_read_evidence_ids(
    audits: ToolAudit | Iterable[ToolAudit],
) -> tuple[str, ...]:
    """Project unique, sorted evidence IDs from successful read-tool audits.

    The model can cite only evidence that its investigator actually read.  This
    projection is intentionally independent of the model response: a read call must
    have one normalized result ID, a matching requested ID, and no error.  Any
    malformed or error-bearing read call fails closed before validation.
    """

    audit_iterable = (audits,) if isinstance(audits, ToolAudit) else audits
    read_ids: set[str] = set()
    for audit in audit_iterable:
        if not isinstance(audit, ToolAudit) or not isinstance(audit.calls, list):
            raise EvidenceReadAuditError("evidence-read audit is malformed")
        for call in audit.calls:
            if not isinstance(call, Mapping):
                raise EvidenceReadAuditError("evidence-read audit call is malformed")
            if call.get("tool") != "read_admitted_evidence":
                continue
            if call.get("error_code") is not None:
                raise EvidenceReadAuditError("evidence-read audit contains an error-bearing result")
            if "result_evidence_ids" not in call:
                raise EvidenceReadAuditError(
                    "successful evidence read is missing normalized result IDs"
                )
            raw_ids = call["result_evidence_ids"]
            if not isinstance(raw_ids, (list, tuple)) or len(raw_ids) != 1:
                raise EvidenceReadAuditError(
                    "successful evidence read must contain exactly one result ID"
                )
            evidence_id = raw_ids[0]
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise EvidenceReadAuditError("evidence read result ID must be non-empty text")
            arguments = call.get("arguments")
            if not isinstance(arguments, Mapping):
                raise EvidenceReadAuditError("evidence-read audit arguments are malformed")
            requested_id = arguments.get("evidence_id")
            if not isinstance(requested_id, str) or not requested_id.strip():
                raise EvidenceReadAuditError(
                    "evidence-read audit is missing its requested evidence ID"
                )
            if requested_id != evidence_id:
                raise EvidenceReadAuditError(
                    "evidence-read audit result does not match its requested ID"
                )
            read_ids.add(evidence_id)
    return tuple(sorted(read_ids))


def derive_knowledge_citations(
    audits: ToolAudit | Iterable[ToolAudit],
    knowledge: KnowledgeRepository,
) -> tuple[KnowledgeCitation, ...]:
    """Project verified, unique citations from successful knowledge searches only.

    Every candidate is checked against the immutable repository again.  Exact repeats
    across separate successful searches collapse to one citation; duplicates in one
    result or conflicting records for one ID fail closed.  A failed search invalidates
    the stage rather than allowing a partial citation set to escape.
    """

    audit_iterable = (audits,) if isinstance(audits, ToolAudit) else audits
    candidates: dict[str, dict[str, str]] = {}
    for audit in audit_iterable:
        for call in audit.calls:
            if call.get("tool") != "search_synthetic_knowledge":
                continue
            if call.get("error_code") is not None:
                raise KnowledgeProvenanceError(
                    "knowledge search audit contains an error-bearing result"
                )
            if "result_knowledge_records" not in call:
                raise KnowledgeProvenanceError(
                    "successful knowledge search is missing normalized provenance"
                )
            arguments = call.get("arguments")
            if arguments is not None and not isinstance(arguments, Mapping):
                raise KnowledgeProvenanceError("knowledge search audit arguments are malformed")
            invocation_version = (
                arguments.get("version") if isinstance(arguments, Mapping) else None
            )
            if invocation_version is not None and invocation_version != knowledge.version:
                raise KnowledgeProvenanceError(
                    "knowledge search audit uses a stale or mismatched corpus version"
                )
            raw_records = call["result_knowledge_records"]
            if not isinstance(raw_records, (list, tuple)):
                raise KnowledgeProvenanceError("knowledge audit results must be a list")
            seen_in_call: set[str] = set()
            for raw_record in raw_records:
                if not isinstance(raw_record, Mapping):
                    raise KnowledgeProvenanceError("knowledge audit result is not an object")
                record = _normalize_knowledge_record(raw_record)
                if invocation_version is not None and record["version"] != invocation_version:
                    raise KnowledgeProvenanceError(
                        "knowledge audit record is unknown or stale for its search invocation"
                    )
                knowledge_id = record["knowledge_id"]
                if knowledge_id in seen_in_call:
                    raise KnowledgeProvenanceError(
                        "knowledge search returned a duplicate provenance record"
                    )
                seen_in_call.add(knowledge_id)
                previous = candidates.get(knowledge_id)
                if previous is not None and previous != record:
                    raise KnowledgeProvenanceError(
                        "knowledge searches returned conflicting provenance records"
                    )
                candidates[knowledge_id] = record

    citations: list[KnowledgeCitation] = []
    for knowledge_id in sorted(candidates):
        candidate = candidates[knowledge_id]
        try:
            allowed_use = KnowledgeUse(candidate["allowed_use"])
        except ValueError as exc:  # guarded by _normalize_knowledge_record
            raise KnowledgeProvenanceError(
                "knowledge audit contains an unsupported allowed use"
            ) from exc
        try:
            resolved = knowledge.get(knowledge_id, candidate["version"])
        except Exception as exc:
            raise KnowledgeProvenanceError(
                "knowledge repository failed to resolve an audit record"
            ) from exc
        if resolved is None:
            raise KnowledgeProvenanceError("knowledge audit references an unknown or stale record")
        if (
            resolved.knowledge_id != candidate["knowledge_id"]
            or resolved.version != candidate["version"]
            or resolved.allowed_use != allowed_use.value
            or resolved.content_digest != candidate["content_digest"]
        ):
            raise KnowledgeProvenanceError(
                "knowledge audit record does not match the frozen corpus"
            )
        citations.append(
            KnowledgeCitation(
                knowledge_id=resolved.knowledge_id,
                version=resolved.version,
                allowed_use=allowed_use,
                content_digest=resolved.content_digest,
            )
        )
    return tuple(citations)
