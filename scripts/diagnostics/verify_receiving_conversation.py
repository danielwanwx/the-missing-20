"""Run a bounded, read-only receiving conversation against the real HTTP gateway.

The resulting artifact records runtime facts for independent semantic review. ``COMPLETE``
means that the real gateway returned runtime-valid turns; it is not a claim that the model's
business answers are correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from typing import TextIO, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_QUESTION_CHARS = 500
MAX_QUESTIONS = 10
MAX_PERSISTED_REQUESTS = 12
PERSISTED_CONTEXT_SCHEMA = "missing20-dialogue-intent/v2"
REQUEST_TIMEOUT_SECONDS = 150
DEFAULT_QUESTIONS = (
    "Compare ordered, physically received and posted quantities. Is the outstanding "
    "balance evidence of missing stock? Check the source records and explain.",
    "I decline any inventory change. Do not approve or execute anything. "
    "Which records independently verify that receipt, and should we retry it?",
    "Keep that read-only constraint. Show the receiving trend and historical baseline. "
    "Explain net change versus the prior-observation average; is this proof of revenue gain?",
)

RequestCallback = Callable[[str, Mapping[str, object] | None], object]

_SECRET_KEY = re.compile(
    r"(?:secret|password|credential|authorization|api[_-]?key|access[_-]?key|"
    r"session[_-]?token|security[_-]?token|cookie|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE = (
    (re.compile(r"(?i)(bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
)


class GatewayRequestError(RuntimeError):
    """A bounded HTTP/transport/decoding error suitable for the private report."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        status_code: int | None = None,
        body: object = None,
        usage: object = None,
    ) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.status_code = status_code
        self.body = body
        self.usage = usage


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redact_error(value: object, *, depth: int = 0) -> object:
    """Bound and redact only provider/transport error bodies.

    Successful gateway responses are already public projections and are stored exactly. Error
    bodies are copied separately so a malformed provider error cannot place credentials in the
    private artifact.
    """

    if depth > 8:
        return "[REDACTED_NESTED_ERROR]"
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _SECRET_KEY.search(str(key))
            else _redact_error(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_error(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        result = value[:16_384]
        for pattern, replacement in _SECRET_VALUE:
            result = pattern.sub(replacement, result)
        return result
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:16_384]


def _decode_body(raw: bytes) -> object:
    text = raw[:16_384].decode("utf-8", errors="replace")
    try:
        return _redact_error(json.loads(text))
    except json.JSONDecodeError:
        return _redact_error(text)


def _usage(value: object) -> object:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get("usage")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    selected = {
        str(key): item
        for key, item in value.items()
        if "cost" in str(key).lower()
        or str(key).lower() in {"request_count", "input_tokens", "output_tokens", "total_tokens"}
    }
    return selected or None


def request_json(
    base_url: str,
    path: str,
    payload: Mapping[str, object] | None = None,
    *,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> object:
    """Call the production loopback route and retain public HTTP failure data safely."""

    request = Request(
        base_url.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": base_url.rstrip("/")},
        method="GET" if payload is None else "POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as error:
        try:
            body = _decode_body(error.read(64 * 1024))
        except (OSError, HTTPException):
            body = None
        raise GatewayRequestError(
            "http",
            f"HTTP {error.code} from {path}",
            status_code=error.code,
            body=body,
            usage=_usage(body),
        ) from error
    except (HTTPException, OSError, TimeoutError, URLError) as error:
        raise GatewayRequestError("transport", "loopback gateway transport failed") from error
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GatewayRequestError(
            "decode", "loopback gateway returned invalid JSON", body=_decode_body(raw)
        ) from error
    if not isinstance(value, Mapping):
        raise GatewayRequestError("response", "loopback gateway returned a non-object JSON value")
    return dict(value)


def _as_gateway_error(error: Exception) -> Exception:
    """Normalize a directly injected HTTPError for the same safe report path."""

    if not isinstance(error, HTTPError):
        return error
    try:
        body = _decode_body(error.read(64 * 1024))
    except (OSError, HTTPException):
        body = None
    return GatewayRequestError(
        "http",
        f"HTTP {error.code} from ask",
        status_code=error.code,
        body=body,
        usage=_usage(body),
    )


def _load_questions(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return DEFAULT_QUESTIONS
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_QUESTIONS:
        raise ValueError(f"questions file must contain 1-{MAX_QUESTIONS} questions")
    questions: list[str] = []
    for index, question in enumerate(value, start=1):
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"question {index} must be a non-empty string")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(
                f"question {index} exceeds the {MAX_QUESTION_CHARS}-character raw limit"
            )
        questions.append(question)
    return tuple(questions)


def _validate_questions(questions: Sequence[str]) -> tuple[str, ...]:
    if not 1 <= len(questions) <= MAX_QUESTIONS:
        raise ValueError(f"questions must contain 1-{MAX_QUESTIONS} questions")
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"question {index} must be a non-empty string")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(
                f"question {index} exceeds the {MAX_QUESTION_CHARS}-character raw limit"
            )
    return tuple(questions)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _conversation_id(value: object) -> str | None:
    context = _mapping(value).get("dialogue_context")
    identifier = _mapping(context).get("conversation_id")
    return identifier if isinstance(identifier, str) and identifier else None


def _context_summary(value: object) -> dict[str, object]:
    context = _mapping(value).get("dialogue_context")
    context_map = _mapping(context)
    result: dict[str, object] = {}
    for key in (
        "schema_version",
        "runtime_instance_id",
        "case_id",
        "conversation_id",
        "requests_omitted",
    ):
        if key in context_map:
            result[key] = context_map[key]
    return result


def _quantities(value: object) -> Mapping[str, object] | None:
    projection = _mapping(value)
    candidates = (
        _mapping(_mapping(projection.get("case_projection")).get("case")).get("quantities"),
        _mapping(_mapping(projection.get("demo_case")).get("case")).get("quantities"),
        projection.get("quantities"),
    )
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return None


def _source_identity(value: object) -> object:
    projection = _mapping(value)
    if "source_identity" in projection:
        return projection["source_identity"]
    freshness = _mapping(projection.get("source_freshness"))
    case_projection = _mapping(projection.get("case_projection"))
    business = _mapping(projection.get("business_impact"))
    return {
        "case_id": projection.get("case_id"),
        "source_freshness": {
            key: freshness[key]
            for key in ("status", "scope", "erp_status", "observed_at", "error_code")
            if key in freshness
        },
        "source_sequence": case_projection.get("source_sequence", business.get("source_sequence")),
        "correlation_status": _mapping(projection.get("correlation")).get("status"),
    }


def _reported_digests(value: object) -> dict[str, object]:
    projection = _mapping(value)
    result: dict[str, object] = {}
    for key in (
        "source_digest",
        "source_digests",
        "evidence_digest",
        "erp_state_digest",
        "saas_state_digest",
    ):
        if key in projection:
            result[key] = projection[key]
    for container_name in ("model_gate", "approval", "execution", "diagnosis"):
        container = _mapping(projection.get(container_name))
        for key, item in container.items():
            if "digest" in str(key).lower():
                result[f"{container_name}.{key}"] = item
    return result


def _projection_snapshot(value: object) -> dict[str, object]:
    projection = _mapping(value)
    identity = _source_identity(projection)
    quantities = _quantities(projection)
    reported = _reported_digests(projection)
    digest_material = {
        "case_id": projection.get("case_id"),
        "source_identity": identity,
        "source_digests": reported,
        "quantities": quantities,
    }
    computed = hashlib.sha256(
        json.dumps(digest_material, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return {
        "case_id": projection.get("case_id"),
        "source_identity": identity,
        "source_digests": {"reported": reported, "computed": computed},
        "quantities": quantities,
        "dialogue_context": _context_summary(projection),
    }


def _check(
    status: str,
    *,
    expected: object = None,
    observed: object = None,
    detail: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {"status": status}
    if expected is not None:
        value["expected"] = expected
    if observed is not None:
        value["observed"] = observed
    if detail:
        value["detail"] = detail
    return value


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def _nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _valid_persisted_request(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    question = value.get("question")
    return (
        _valid_identifier(value.get("request_id"))
        and isinstance(question, str)
        and bool(question.strip())
        and len(question) <= MAX_QUESTION_CHARS
        and _valid_identifier(value.get("created_at"))
    )


def _persisted_context(
    projection: object,
    *,
    case_id: str,
    expected_question: str | None = None,
    allow_fresh_baseline: bool = False,
) -> dict[str, object]:
    """Validate the production persisted context before trusting turn counts."""

    value = _mapping(projection)
    context = value.get("dialogue_context")
    requests = value.get("human_requests")
    if allow_fresh_baseline and context == {} and requests == [] and expected_question is None:
        return {
            "checks": {"fresh_baseline_context": _check("PASS")},
            "valid": True,
            "conversation_id": None,
            "requests_omitted": None,
            "request_count": 0,
        }
    checks: dict[str, object] = {}
    if not isinstance(context, Mapping):
        checks["dialogue_context_object"] = _check(
            "FAIL", detail="persisted dialogue_context is unavailable"
        )
        context_map: Mapping[str, object] = {}
    else:
        context_map = context
        checks["dialogue_context_schema"] = _check(
            "PASS" if context.get("schema_version") == PERSISTED_CONTEXT_SCHEMA else "FAIL",
            expected=PERSISTED_CONTEXT_SCHEMA,
            observed=context.get("schema_version"),
        )
        checks["dialogue_context_runtime_instance"] = _check(
            "PASS" if _valid_identifier(context.get("runtime_instance_id")) else "FAIL",
            detail="persisted runtime instance identity is required",
        )
        checks["dialogue_context_case_id_exact"] = _check(
            "PASS" if context.get("case_id") == case_id else "FAIL",
            expected=case_id,
            observed=context.get("case_id"),
        )
        checks["dialogue_context_conversation_id"] = _check(
            "PASS" if _valid_identifier(context.get("conversation_id")) else "FAIL",
            detail="persisted conversation_id is required",
        )
        omitted = context.get("requests_omitted")
        checks["dialogue_context_requests_omitted"] = _check(
            "PASS" if _nonnegative_int(omitted) is not None else "FAIL",
            observed=omitted,
            detail="requests_omitted must be a non-negative integer",
        )

    if not isinstance(requests, list):
        checks["human_requests_list"] = _check(
            "FAIL", detail="persisted human_requests list is unavailable"
        )
        request_items: list[object] = []
    else:
        request_items = requests
        checks["human_requests_window"] = _check(
            "PASS" if len(requests) <= MAX_PERSISTED_REQUESTS else "FAIL",
            expected=f"at most {MAX_PERSISTED_REQUESTS} stored requests",
            observed=len(requests),
        )
        checks["human_requests_entries"] = _check(
            "PASS" if all(_valid_persisted_request(item) for item in requests) else "FAIL",
            detail="every stored request must retain its complete bounded fields",
        )

    if expected_question is not None:
        saved_question = None
        if request_items and _valid_persisted_request(request_items[-1]):
            saved_question = _mapping(request_items[-1]).get("question")
        checks["saved_current_question_exact"] = _check(
            "PASS" if saved_question == expected_question else "FAIL",
            expected=expected_question,
            observed=saved_question,
        )

    statuses = [_mapping(item).get("status") for item in checks.values()]
    omitted = context_map.get("requests_omitted")
    valid_omitted = _nonnegative_int(omitted)
    conversation_id = context_map.get("conversation_id")
    valid_conversation_id = conversation_id if _valid_identifier(conversation_id) else None
    return {
        "checks": checks,
        "valid": bool(statuses) and all(status == "PASS" for status in statuses),
        "conversation_id": valid_conversation_id,
        "requests_omitted": valid_omitted,
        "request_count": len(request_items) if isinstance(requests, list) else None,
    }


def _error_record(error: BaseException) -> dict[str, object]:
    if isinstance(error, GatewayRequestError):
        record: dict[str, object] = {
            "type": type(error).__name__,
            "kind": error.kind,
            "detail": _redact_error(error.detail),
        }
        if error.status_code is not None:
            record["status_code"] = error.status_code
        if error.body is not None:
            record["body"] = _redact_error(error.body)
        if error.usage is not None:
            record["usage"] = error.usage
        return record
    record = {"type": type(error).__name__, "detail": "request callback failed"}
    usage = getattr(error, "usage", None)
    if isinstance(usage, Mapping):
        record["usage"] = dict(usage)
    diagnostics = getattr(error, "diagnostics", None)
    if diagnostics is not None:
        record["diagnostics"] = _redact_error(diagnostics)
    return record


def _response_usage(response: object, error: BaseException | None = None) -> object:
    projection = _mapping(response)
    advisory = _mapping(projection.get("agent_advisory"))
    for candidate in (advisory, projection):
        usage = _usage(candidate)
        if usage is not None:
            return usage
    if error is not None:
        usage = getattr(error, "usage", None)
        if isinstance(usage, Mapping):
            return dict(usage)
        usage = _usage(getattr(error, "body", None))
        if usage is not None:
            return usage
    return None


def _response_diagnostics(response: object, error: BaseException | None = None) -> object:
    projection = _mapping(response)
    advisory = _mapping(projection.get("agent_advisory"))
    for candidate in (projection, advisory):
        for key in ("validation_diagnostics", "diagnostics"):
            if key in candidate:
                return candidate[key]
    if error is not None:
        diagnostics = getattr(error, "diagnostics", None)
        if diagnostics is not None:
            return _redact_error(diagnostics)
        body = _mapping(getattr(error, "body", None))
        for key in ("validation_diagnostics", "diagnostics"):
            if key in body:
                return _redact_error(body[key])
    return []


def _not_reached(index: int, question: str) -> dict[str, object]:
    return {
        "turn": index,
        "status": "NOT_REACHED",
        "question": question,
        "response": None,
        "answer": None,
        "diagnostics": [],
        "usage": None,
        "runtime_checks": {},
        "semantic_review": {"status": "PENDING"},
        "not_reached_reason": "prior_runtime_failure",
    }


def _new_report(case_id: str, questions: Sequence[str]) -> dict[str, object]:
    return {
        "schema_version": "receiving-conversation-diagnostic/v2",
        "status": "RUNNING",
        "runtime_status": "RUNNING",
        "scope": "real_model_runtime_only",
        "semantic_review": {
            "status": "PENDING",
            "scope": "Independent answer quality and business semantics review.",
        },
        "limitations": [
            (
                "The HTTP ask endpoint currently accepts question only; segmented restarts are "
                "orchestrated outside this harness."
            ),
            "A runtime COMPLETE does not certify semantic answer accuracy.",
        ],
        "case_id": case_id,
        "planned_questions": list(questions),
        "planned_turns": len(questions),
        "started_at": _now(),
        "turns": [],
        "runtime_failures": [],
    }


class _ReportWriter:
    """Create an exclusive private report and fsync every checkpoint."""

    def __init__(self, handle: TextIO) -> None:
        self.handle = handle

    @classmethod
    def create(cls, path: Path) -> _ReportWriter:
        path = path.expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            return cls(os.fdopen(descriptor, "w", encoding="utf-8"))
        except BaseException:
            os.close(descriptor)
            raise

    def write(self, report: Mapping[str, object]) -> None:
        payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(payload + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def __enter__(self) -> _ReportWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.handle.close()


def run_diagnostic(
    *,
    case_id: str,
    output: Path,
    questions: Sequence[str] = DEFAULT_QUESTIONS,
    request_callback: RequestCallback | None = None,
    port: int | None = None,
    require_history_attachment: bool = False,
    expected_conversation_id: str | None = None,
) -> dict[str, object]:
    """Run one segment through the real routes with a small injectable request callback."""

    checked_questions = _validate_questions(questions)
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id must be a non-empty string")
    if request_callback is None:
        if port is None:
            raise ValueError("port is required when request_callback is not supplied")
        base_url = f"http://127.0.0.1:{port}"

        def http_callback(path: str, payload: Mapping[str, object] | None = None) -> object:
            return request_json(base_url, path, payload)

        callback: RequestCallback = http_callback
    else:
        callback = request_callback

    report = _new_report(case_id, checked_questions)
    with _ReportWriter.create(Path(output)) as writer:
        writer.write(report)

        def fail(detail: str, turn_number: int | None = None) -> None:
            report["status"] = "RUNTIME_FAILED"
            report["runtime_status"] = "FAILED"
            failures = cast(list[object], report["runtime_failures"])
            failures.append({"detail": detail, **({"turn": turn_number} if turn_number else {})})

        def stop_after_failure(start: int) -> None:
            turns = cast(list[object], report["turns"])
            for index in range(start, len(checked_questions)):
                turns.append(_not_reached(index + 1, checked_questions[index]))
                writer.write(report)

        try:
            baseline_value = callback("/api/v1/agent-platform", None)
        except Exception as error:
            error = _as_gateway_error(error)
            report["baseline"] = {
                "status": "ERROR",
                "source_identity": None,
                "source_digests": {},
                "quantities": None,
                "error": _error_record(error),
            }
            fail("baseline projection request failed")
            writer.write(report)
            stop_after_failure(0)
            report["final"] = {"status": "NOT_AVAILABLE", "reason": "baseline_failed"}
            report["completed_at"] = _now()
            writer.write(report)
            return report

        if not isinstance(baseline_value, Mapping):
            report["baseline"] = {
                "status": "ERROR",
                "source_identity": None,
                "source_digests": {},
                "quantities": None,
                "error": {"type": "InvalidResponse", "detail": "baseline is not an object"},
            }
            fail("baseline projection is not an object")
            writer.write(report)
            stop_after_failure(0)
            report["final"] = {"status": "NOT_AVAILABLE", "reason": "baseline_failed"}
            report["completed_at"] = _now()
            writer.write(report)
            return report

        baseline = dict(baseline_value)
        baseline_snapshot = _projection_snapshot(baseline)
        baseline_record: dict[str, object] = {"status": "AVAILABLE", **baseline_snapshot}
        report["baseline"] = baseline_record
        baseline_case = baseline.get("case_id")
        baseline_quantities = baseline_snapshot["quantities"]
        baseline_context = _persisted_context(baseline, case_id=case_id, allow_fresh_baseline=True)
        baseline_id = cast(str | None, baseline_context["conversation_id"])
        baseline_checks: dict[str, object] = {
            "case_id_exact": _check(
                "PASS" if baseline_case == case_id else "FAIL",
                expected=case_id,
                observed=baseline_case,
            ),
            "quantities_available": _check(
                "PASS" if isinstance(baseline_quantities, Mapping) else "FAIL",
                detail="baseline case quantities are required for runtime comparison",
            ),
        }
        baseline_checks.update(cast(dict[str, object], baseline_context["checks"]))
        if expected_conversation_id is not None:
            baseline_checks["expected_conversation_id"] = _check(
                "PASS" if baseline_id == expected_conversation_id else "FAIL",
                expected=expected_conversation_id,
                observed=baseline_id,
            )
        baseline_record["runtime_checks"] = baseline_checks
        writer.write(report)
        if any(_mapping(value).get("status") == "FAIL" for value in baseline_checks.values()):
            fail("baseline projection failed a runtime check")
            writer.write(report)
            stop_after_failure(0)
            report["final"] = {"status": "NOT_AVAILABLE", "reason": "baseline_runtime_failure"}
            report["completed_at"] = _now()
            writer.write(report)
            return report

        segment_id = baseline_id
        runtime_failed = False
        for index, question in enumerate(checked_questions):
            try:
                response_value = callback("/api/v1/agent-platform/ask", {"question": question})
            except Exception as error:
                error = _as_gateway_error(error)
                failed_turn = {
                    "turn": index + 1,
                    "status": "RUNTIME_FAILED",
                    "question": question,
                    "response": _redact_error(getattr(error, "body", None)),
                    "answer": None,
                    "diagnostics": _response_diagnostics(None, error),
                    "usage": _response_usage(None, error),
                    "error": _error_record(error),
                    "runtime_checks": {"http_request": _check("FAIL", detail="ask request failed")},
                    "semantic_review": {"status": "PENDING"},
                }
                cast(list[object], report["turns"]).append(failed_turn)
                writer.write(report)
                fail("ask request failed", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break

            response = dict(response_value) if isinstance(response_value, Mapping) else None
            advisory = _mapping(response.get("agent_advisory")) if response else {}
            status = advisory.get("status")
            turn: dict[str, object] = {
                "turn": index + 1,
                "status": "PENDING_RUNTIME_CHECKS",
                "question": question,
                "response": response_value,
                "answer": response.get("answer") if response else None,
                "diagnostics": _response_diagnostics(response),
                "usage": _response_usage(response),
                "runtime_checks": {},
                "semantic_review": {"status": "PENDING"},
            }
            cast(list[object], report["turns"]).append(turn)
            writer.write(report)

            checks: dict[str, object] = {
                "advisory_status": _check(
                    "PASS" if status == "COMPLETE" else "FAIL",
                    expected="COMPLETE",
                    observed=status,
                ),
                "mode_real_strands": _check(
                    "PASS" if advisory.get("mode") == "real_strands" else "FAIL",
                    expected="real_strands",
                    observed=advisory.get("mode"),
                ),
                "case_id_exact": _check(
                    "PASS" if response and response.get("case_id") == case_id else "FAIL",
                    expected=case_id,
                    observed=response.get("case_id") if response else None,
                ),
            }
            nested_case = (
                _mapping(_mapping(response.get("case_projection")).get("case")) if response else {}
            )
            if "case_id" in nested_case:
                checks["case_projection_case_id_exact"] = _check(
                    "PASS" if nested_case.get("case_id") == case_id else "FAIL",
                    expected=case_id,
                    observed=nested_case.get("case_id"),
                )
            references = _mapping(advisory.get("receiving_references"))
            if "case_id" in references:
                checks["receiving_reference_case_id_exact"] = _check(
                    "PASS" if references.get("case_id") == case_id else "FAIL",
                    expected=case_id,
                    observed=references.get("case_id"),
                )
            result = _mapping(advisory.get("result"))
            checks["write_performed_false"] = _check(
                "PASS" if result.get("write_performed") is False else "FAIL",
                expected=False,
                observed=result.get("write_performed"),
            )
            persisted_context = _persisted_context(
                response, case_id=case_id, expected_question=question
            )
            checks.update(cast(dict[str, object], persisted_context["checks"]))
            persisted_id = cast(str | None, persisted_context["conversation_id"])
            advisory_id = advisory.get("conversation_id")
            observed_id = persisted_id
            if "conversation_id" in advisory:
                checks["advisory_conversation_id_matches_projection"] = _check(
                    "PASS" if advisory_id == persisted_id else "FAIL",
                    expected=persisted_id,
                    observed=advisory_id,
                )
            if segment_id is None and isinstance(observed_id, str):
                segment_id = observed_id
            checks["conversation_id_stable"] = _check(
                "PASS" if isinstance(observed_id, str) and observed_id == segment_id else "FAIL",
                expected=segment_id,
                observed=observed_id,
            )
            if expected_conversation_id is not None:
                checks["expected_conversation_id"] = _check(
                    "PASS" if observed_id == expected_conversation_id else "FAIL",
                    expected=expected_conversation_id,
                    observed=observed_id,
                )
            context_turns = advisory.get("context_turns")
            omitted_turns = advisory.get("omitted_turns")
            context_count = _nonnegative_int(context_turns)
            omitted_count = _nonnegative_int(omitted_turns)
            context_valid = context_count is not None
            omitted_valid = omitted_count is not None
            checks["context_turns_metadata"] = _check(
                "PASS" if context_valid else "FAIL", observed=context_turns
            )
            checks["omitted_turns_metadata"] = _check(
                "PASS" if omitted_valid else "FAIL", observed=omitted_turns
            )
            expected_prior: int | None = None
            stored_prior: int | None = None
            if (
                persisted_context["valid"] is True
                and isinstance(persisted_context["requests_omitted"], int)
                and isinstance(persisted_context["request_count"], int)
            ):
                stored_prior = max(0, persisted_context["request_count"] - 1)
                expected_prior = persisted_context["requests_omitted"] + max(0, stored_prior)
            checks["context_matches_persisted_state"] = _check(
                "PASS"
                if expected_prior is not None
                and context_valid
                and omitted_valid
                and stored_prior is not None
                and context_count is not None
                and context_count <= stored_prior
                and omitted_count is not None
                and context_count + omitted_count == expected_prior
                else "FAIL",
                expected=expected_prior,
                observed=(
                    context_count + omitted_count
                    if context_count is not None and omitted_count is not None
                    else None
                ),
                detail=(
                    None
                    if expected_prior is not None
                    else "persisted context evidence is unavailable or malformed"
                ),
            )
            if require_history_attachment:
                attachments = advisory.get("attachments")
                checks["history_attachment_present"] = _check(
                    "PASS" if isinstance(attachments, list) and bool(attachments) else "FAIL",
                    detail="history attachment was explicitly required",
                )

            if status != "COMPLETE":
                # A failure may still contain a public projection dialogue_context and usage;
                # retain the complete response and stop without attempting later questions.
                turn["runtime_checks"] = checks
                turn["status"] = "RUNTIME_FAILED"
                if response:
                    report["final"] = {
                        "status": "OBSERVED_ON_FAILURE",
                        **_projection_snapshot(response),
                    }
                writer.write(report)
                fail("gateway returned a non-complete advisory", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break

            if any(_mapping(value).get("status") == "FAIL" for value in checks.values()):
                turn["runtime_checks"] = checks
                turn["status"] = "RUNTIME_FAILED"
                if response:
                    report["final"] = {
                        "status": "OBSERVED_ON_FAILURE",
                        **_projection_snapshot(response),
                    }
                writer.write(report)
                fail("turn failed runtime checks", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break

            try:
                current_value = callback("/api/v1/agent-platform", None)
            except Exception as error:
                error = _as_gateway_error(error)
                turn["runtime_checks"] = checks
                turn["status"] = "RUNTIME_FAILED"
                turn["post_projection_error"] = _error_record(error)
                report["final"] = {
                    "status": "OBSERVED_ON_FAILURE",
                    **_projection_snapshot(response),
                }
                writer.write(report)
                fail("post-turn projection request failed", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break
            if not isinstance(current_value, Mapping):
                checks["post_projection_object"] = _check("FAIL")
                turn["runtime_checks"] = checks
                turn["status"] = "RUNTIME_FAILED"
                writer.write(report)
                fail("post-turn projection was not an object", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break

            current = dict(current_value)
            current_snapshot = _projection_snapshot(current)
            turn["post_projection"] = current_snapshot
            checks["post_case_id_exact"] = _check(
                "PASS" if current.get("case_id") == case_id else "FAIL",
                expected=case_id,
                observed=current.get("case_id"),
            )
            checks["quantities_unchanged"] = _check(
                "PASS"
                if isinstance(baseline_quantities, Mapping)
                and current_snapshot["quantities"] == baseline_quantities
                else "FAIL",
                expected=baseline_quantities,
                observed=current_snapshot["quantities"],
            )
            current_id = _conversation_id(current)
            checks["post_conversation_id_stable"] = _check(
                "PASS" if current_id == observed_id else "FAIL",
                expected=observed_id,
                observed=current_id,
            )
            post_context = _persisted_context(current, case_id=case_id, expected_question=question)
            checks.update(
                {
                    f"post_{name}": check
                    for name, check in cast(dict[str, object], post_context["checks"]).items()
                }
            )
            turn["runtime_checks"] = checks
            report["final"] = {"status": "AVAILABLE", **current_snapshot}
            if any(_mapping(value).get("status") == "FAIL" for value in checks.values()):
                turn["status"] = "RUNTIME_FAILED"
                writer.write(report)
                fail("turn failed runtime checks", index + 1)
                stop_after_failure(index + 1)
                runtime_failed = True
                break
            turn["status"] = "COMPLETE"
            writer.write(report)

        turns = cast(list[object], report["turns"])
        report["completed_turns"] = sum(
            1 for turn in turns if isinstance(turn, Mapping) and turn.get("status") == "COMPLETE"
        )
        report["not_reached_turns"] = sum(
            1 for turn in turns if isinstance(turn, Mapping) and turn.get("status") == "NOT_REACHED"
        )
        if not runtime_failed:
            report["status"] = "COMPLETE"
            report["runtime_status"] = "COMPLETE"
        elif "final" not in report:
            report["final"] = {"status": "NOT_AVAILABLE", "reason": "runtime_failed"}
        report["completed_at"] = _now()
        writer.write(report)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--questions-file", type=Path)
    parser.add_argument(
        "--require-history-attachment",
        action="store_true",
        help="Require a non-empty history attachment on every successful turn.",
    )
    parser.add_argument(
        "--expected-conversation-id",
        help="Require the persisted conversation ID for the restart segment.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        questions = _load_questions(args.questions_file)
        report = run_diagnostic(
            case_id=args.case_id,
            output=args.output,
            questions=questions,
            port=args.port,
            require_history_attachment=args.require_history_attachment,
            expected_conversation_id=args.expected_conversation_id,
        )
    except FileExistsError:
        print(
            json.dumps(
                {"status": "OUTPUT_EXISTS", "detail": "refusing to overwrite existing output"}
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INPUT_FAILED", "detail": str(error)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "runtime_status": report["runtime_status"],
                "semantic_review": report["semantic_review"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["runtime_status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
