"""Strands model adapters used by the offline harness and explicit Bedrock smoke."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from the_missing_20.ports.agent_model import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    AgentBudget,
    AgentBudgetExceeded,
    AgentBudgetLedger,
    AgentModelFactory,
    AgentProvider,
    AgentProviderUnavailable,
    AgentStage,
)

LOGGER = logging.getLogger(__name__)

try:  # Keep imports lazy-friendly for the pre-bootstrap repository commands.
    from strands.models import BedrockModel, Model
    from strands.types.content import Messages, SystemContentBlock
    from strands.types.event_loop import Usage
    from strands.types.streaming import StreamEvent
    from strands.types.tools import ToolChoice, ToolSpec

    STRANDS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only before dependency bootstrap
    BedrockModel = Any  # type: ignore[misc,assignment]
    Model = object  # type: ignore[assignment,misc]
    Messages = list[dict[str, Any]]  # type: ignore[misc,assignment]
    SystemContentBlock = dict[str, Any]  # type: ignore[misc,assignment]
    Usage = dict[str, int]  # type: ignore[misc,assignment]
    StreamEvent = dict[str, Any]  # type: ignore[misc,assignment]
    ToolChoice = dict[str, Any]  # type: ignore[misc,assignment]
    ToolSpec = dict[str, Any]  # type: ignore[misc,assignment]
    STRANDS_AVAILABLE = False


T = TypeVar("T", bound=BaseModel)
PROJECT_TOOL_NAMES = frozenset({"read_admitted_evidence", "search_synthetic_knowledge"})


def require_strands() -> None:
    if not STRANDS_AVAILABLE:
        raise RuntimeError("strands-agents is required; run make bootstrap")


def _usage(messages: Messages, tool_specs: list[ToolSpec] | None, output: object) -> Usage:
    input_tokens = max(1, len(json.dumps(messages, sort_keys=True, default=str)) // 4)
    input_tokens += len(json.dumps(tool_specs or [], sort_keys=True, default=str)) // 4
    output_tokens = max(1, len(json.dumps(output, sort_keys=True, default=str)) // 4)
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


class ScriptedStrandsModel(Model):
    """A deterministic custom Strands model that still drives the real event loop.

    The provider emits a tool-use turn for each frozen read plan, then emits a structured
    output tool-use turn when Strands switches into structured-output mode.  It never
    performs network I/O and is deliberately not presented as a generative-model proof.
    """

    def __init__(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
        output_payloads: tuple[dict[str, Any], ...] = (),
        model_id: str = "scripted-strands-v1",
    ) -> None:
        require_strands()
        self.config: dict[str, Any] = {
            "model_id": model_id,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS_PER_REQUEST,
        }
        self.stage = stage
        self.output_payload = output_payload
        self.output_payloads = output_payloads or (output_payload,)
        self.tool_plan = tool_plan
        self.tool_call_history: list[dict[str, Any]] = []
        self.request_count = 0
        self._tool_index = 0
        self._structured_index = 0
        self._last_provider_metadata: dict[str, Any] = {}

    def actual_provider_metadata(self) -> dict[str, Any]:
        """Return attribution for the last completed deterministic model response."""

        return dict(self._last_provider_metadata)

    def mark_provider_failure(self) -> None:
        """Mark a returned deterministic response as non-complete after validation."""

        if self._last_provider_metadata:
            self._last_provider_metadata["status"] = "DEGRADED"
            self._last_provider_metadata["invocation_status"] = "FAILED"

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    async def count_tokens(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
    ) -> int:
        return max(
            1,
            len(json.dumps(messages, sort_keys=True, default=str)) // 4
            + len(json.dumps(tool_specs or [], sort_keys=True, default=str)) // 4
            + len(system_prompt or "") // 4,
        )

    @staticmethod
    def _structured_tool(tool_specs: list[ToolSpec]) -> ToolSpec | None:
        candidates = [spec for spec in tool_specs if spec["name"] not in PROJECT_TOOL_NAMES]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _has_tool_result(messages: Messages) -> bool:
        return any(
            block.get("toolResult") is not None
            for message in messages
            for block in message.get("content", [])
        )

    def _payload(self) -> dict[str, Any]:
        index = min(self._structured_index, len(self.output_payloads) - 1)
        self._structured_index += 1
        return self.output_payloads[index]

    def _tool_events(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        messages: Messages,
        tool_specs: list[ToolSpec] | None,
    ) -> list[StreamEvent]:
        call_index = len(self.tool_call_history)
        tool_use_id = f"{self.stage.value}-tool-{call_index + 1}"
        self.tool_call_history.append(
            {"tool": name, "arguments": json.loads(json.dumps(arguments, sort_keys=True))}
        )
        return [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": tool_use_id}}}},
            {
                "contentBlockDelta": {
                    "delta": {"toolUse": {"input": json.dumps(arguments, sort_keys=True)}}
                }
            },
            {"contentBlockStop": {}},
            {"messageStop": {"stopReason": "tool_use"}},
            {
                "metadata": {
                    "usage": _usage(messages, tool_specs, arguments),
                    "metrics": {"latencyMs": 0},
                }
            },
        ]

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        del system_prompt, tool_choice, system_prompt_content, kwargs
        self.request_count += 1
        specs = tool_specs or []
        structured = self._structured_tool(specs)
        # A structured-output tool is registered on the first turn as well.  Frozen
        # investigator plans intentionally take precedence so offline proof exercises
        # the real read-tool loop before Strands enters forced structured-output mode.
        if self._tool_index < len(self.tool_plan):
            planned = self.tool_plan[self._tool_index]
            self._tool_index += 1
            events = self._tool_events(
                name=str(planned["tool"]),
                arguments=dict(planned.get("arguments", {})),
                messages=messages,
                tool_specs=tool_specs,
            )
        elif structured is not None:
            # This is the deterministic adapter's actual structured response
            # boundary.  It is not factory configuration and carries no fabricated
            # external invocation identity.
            self._last_provider_metadata = {
                "mode": AgentProvider.SCRIPTED.value,
                "provider": AgentProvider.SCRIPTED.value,
                "model": self.config["model_id"],
                "transport": "local_strands_model",
                "invocation_proof": "returned",
                "status": "COMPLETE",
                "invocation_status": "COMPLETED",
            }
            events = self._tool_events(
                name=structured["name"],
                arguments=self._payload(),
                messages=messages,
                tool_specs=tool_specs,
            )
        else:
            output = {"text": "Structured result is ready."}
            events = [
                {"messageStart": {"role": "assistant"}},
                {"contentBlockStart": {"start": {}}},
                {"contentBlockDelta": {"delta": {"text": "Structured result is ready."}}},
                {"contentBlockStop": {}},
                {"messageStop": {"stopReason": "end_turn"}},
                {
                    "metadata": {
                        "usage": _usage(messages, tool_specs, output),
                        "metrics": {"latencyMs": 0},
                    }
                },
            ]
        for event in events:
            yield event

    async def structured_output(
        self,
        output_model: type[T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        del prompt, system_prompt, kwargs
        self._last_provider_metadata = {
            "mode": AgentProvider.SCRIPTED.value,
            "provider": AgentProvider.SCRIPTED.value,
            "model": self.config["model_id"],
            "transport": "local_strands_model",
            "invocation_proof": "returned",
            "status": "COMPLETE",
            "invocation_status": "COMPLETED",
        }
        try:
            structured = output_model.model_validate(self._payload())
        except Exception:
            self.mark_provider_failure()
            raise
        yield {"output": structured}


class BudgetedModel(Model):
    """Delegate that reserves every provider call against one shared ledger."""

    def __init__(self, delegate: Any, ledger: AgentBudgetLedger) -> None:
        self._delegate = delegate
        self.ledger = ledger

    @property
    def stateful(self) -> bool:
        return bool(getattr(self._delegate, "stateful", False))

    def update_config(self, **model_config: Any) -> None:
        max_tokens = model_config.get("max_tokens")
        if (
            isinstance(max_tokens, int)
            and not isinstance(max_tokens, bool)
            and max_tokens > MAX_OUTPUT_TOKENS_PER_REQUEST
        ):
            raise AgentBudgetExceeded("model max_tokens exceeds the frozen per-request cap")
        self._delegate.update_config(**model_config)

    def get_config(self) -> Any:
        return self._delegate.get_config()

    async def count_tokens(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
    ) -> int:
        return int(
            await self._delegate.count_tokens(
                messages,
                tool_specs=tool_specs,
                system_prompt=system_prompt,
                system_prompt_content=system_prompt_content,
            )
        )

    @staticmethod
    def _metadata_usage(event: Any) -> tuple[int, int]:
        if not isinstance(event, dict):
            return 0, 0
        metadata = event.get("metadata")
        if metadata is None:
            return 0, 0
        if not isinstance(metadata, dict):
            raise AgentBudgetExceeded("provider metadata is malformed")
        usage = metadata.get("usage")
        if usage is None:
            return 0, 0
        if not isinstance(usage, dict):
            raise AgentBudgetExceeded("provider usage metadata is malformed")
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        if (
            isinstance(input_tokens, bool)
            or not isinstance(input_tokens, int)
            or input_tokens < 0
            or isinstance(output_tokens, bool)
            or not isinstance(output_tokens, int)
            or output_tokens < 0
        ):
            raise AgentBudgetExceeded("provider reported malformed token usage")
        return input_tokens, output_tokens

    @staticmethod
    def serialized_request_byte_length(
        *,
        messages: Messages,
        tool_specs: list[ToolSpec] | None,
        system_prompt: str | None,
        system_prompt_content: list[SystemContentBlock] | None,
        invocation_state: dict[str, Any] | None,
        model_state: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> int:
        """Return the UTF-8 size of the complete canonical provider request."""

        request = {
            "messages": messages,
            "tool_specs": tool_specs or [],
            "system_prompt": system_prompt,
            "system_prompt_content": system_prompt_content,
            "invocation_state": invocation_state,
            "model_state": model_state,
            "kwargs": kwargs,
        }
        return len(
            json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, Any] | None = None,
        model_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        serialized_length = self.serialized_request_byte_length(
            messages=messages,
            tool_specs=tool_specs,
            system_prompt=system_prompt,
            system_prompt_content=system_prompt_content,
            invocation_state=invocation_state,
            model_state=model_state,
            kwargs=kwargs,
        )
        reservation = self.ledger.reserve_request(
            input_token_upper_bound=serialized_length,
            output_token_upper_bound=self._output_token_ceiling(),
        )
        input_tokens = 0
        output_tokens = 0
        usage_failure = False
        try:
            async for event in self._delegate.stream(
                messages,
                tool_specs,
                system_prompt,
                tool_choice=tool_choice,
                system_prompt_content=system_prompt_content,
                invocation_state=invocation_state,
                model_state=model_state,
                **kwargs,
            ):
                event_input, event_output = self._metadata_usage(event)
                input_tokens += event_input
                output_tokens += event_output
                yield event
        except AgentBudgetExceeded:
            usage_failure = True
            raise
        finally:
            if usage_failure:
                self.ledger.abandon_reservation(reservation)
            else:
                self.ledger.reconcile(
                    reservation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

    async def structured_output(
        self,
        output_model: type[T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        serialized_length = self.serialized_request_byte_length(
            messages=prompt,
            tool_specs=None,
            system_prompt=system_prompt,
            system_prompt_content=None,
            invocation_state=None,
            model_state=None,
            kwargs={
                "output_model": output_model.model_json_schema(),
                **kwargs,
            },
        )
        reservation = self.ledger.reserve_request(
            input_token_upper_bound=serialized_length,
            output_token_upper_bound=self._output_token_ceiling(),
        )
        input_tokens = 0
        output_tokens = 0
        usage_failure = False
        try:
            async for event in self._delegate.structured_output(
                output_model,
                prompt,
                system_prompt=system_prompt,
                **kwargs,
            ):
                event_input, event_output = self._metadata_usage(event)
                input_tokens += event_input
                output_tokens += event_output
                yield event
        except AgentBudgetExceeded:
            usage_failure = True
            raise
        finally:
            if usage_failure:
                self.ledger.abandon_reservation(reservation)
            else:
                self.ledger.reconcile(
                    reservation,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

    def _output_token_ceiling(self) -> int:
        config = self.get_config()
        configured = config.get("max_tokens") if isinstance(config, dict) else None
        if not isinstance(configured, int) or isinstance(configured, bool):
            configured = self.ledger.budget.max_output_tokens_per_request
        if configured <= 0:
            raise AgentBudgetExceeded("model max_tokens must be positive")
        if configured > self.ledger.budget.max_output_tokens_per_request:
            raise AgentBudgetExceeded("model max_tokens exceeds the frozen per-request cap")
        return configured

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


@dataclass(frozen=True, slots=True)
class BedrockNovaProConfig:
    """Explicitly bounded Nova Pro configuration; no strict tool flag is sent."""

    model_id: str = "us.amazon.nova-pro-v1:0"
    region: str = "us-west-2"
    max_tokens: int = MAX_OUTPUT_TOKENS_PER_REQUEST
    temperature: float = 0.0
    streaming: bool = False
    budget: AgentBudget = AgentBudget()
    aws_profile: str | None = None

    def __post_init__(self) -> None:
        if self.model_id != "us.amazon.nova-pro-v1:0":
            raise ValueError("Milestone 4 only permits Amazon Nova Pro")
        if self.region != "us-west-2":
            raise ValueError("Bedrock experiments are restricted to us-west-2")
        if self.max_tokens <= 0 or self.max_tokens > self.budget.max_output_tokens:
            raise ValueError("max_tokens exceeds the frozen output-token budget")
        if self.max_tokens > self.budget.max_output_tokens_per_request:
            raise ValueError("max_tokens exceeds the frozen per-request output ceiling")
        if self.temperature != 0:
            raise ValueError("temperature is frozen at zero")


@dataclass(frozen=True, slots=True)
class AgentCoreRuntimeConfig:
    """Explicit boundary for an already-deployed AgentCore Runtime.

    The ARN is deliberately optional at construction time.  This lets the local
    application expose ``agentcore`` as a selected mode and fail visibly at the
    first invocation when deployment configuration is absent; it never silently
    downgrades to scripted or direct Bedrock execution.
    """

    runtime_arn: str | None = None
    region: str = "us-west-2"
    qualifier: str = "DEFAULT"
    max_tokens: int = MAX_OUTPUT_TOKENS_PER_REQUEST
    budget: AgentBudget = AgentBudget()
    aws_profile: str | None = None
    runtime_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.region != "us-west-2":
            raise ValueError("AgentCore experiments are restricted to us-west-2")
        if self.runtime_arn is not None and not self.runtime_arn.strip():
            raise ValueError("AgentCore runtime ARN must not be empty")
        if not self.qualifier.strip():
            raise ValueError("AgentCore qualifier must not be empty")
        if self.max_tokens <= 0 or self.max_tokens > self.budget.max_output_tokens:
            raise ValueError("max_tokens exceeds the frozen output-token budget")
        if self.max_tokens > self.budget.max_output_tokens_per_request:
            raise ValueError("max_tokens exceeds the frozen per-request output ceiling")


def _agentcore_response_bytes(response: Any) -> bytes:
    """Read one bounded AgentCore response without retaining SDK objects."""

    body = response.get("response") if isinstance(response, dict) else None
    if body is None:
        raise AgentProviderUnavailable("AgentCore response did not contain a response body")
    if hasattr(body, "read"):
        value = body.read()
    elif isinstance(body, (bytes, bytearray)):
        value = bytes(body)
    else:
        try:
            value = b"".join(
                item if isinstance(item, bytes) else str(item).encode("utf-8") for item in body
            )
        except TypeError as exc:
            raise AgentProviderUnavailable("AgentCore response body is malformed") from exc
    if not isinstance(value, bytes):
        raise AgentProviderUnavailable("AgentCore response body is not bytes")
    if len(value) > 256 * 1024:
        raise AgentProviderUnavailable("AgentCore response exceeded the bounded response size")
    return value


def _agentcore_json_payload(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentProviderUnavailable("AgentCore returned a non-JSON response") from exc


class AgentCoreRuntimeModel(Model):
    """A small Strands model adapter for an existing AgentCore Runtime.

    AgentCore hosts the Strands agent; this adapter only transports a bounded
    advisory request and exposes its response through the same model seam used by
    the local harness.  It has no tools that can mutate the enterprise state.
    """

    MAX_STRUCTURED_SCHEMA_BYTES = 16 * 1024

    def __init__(
        self,
        *,
        config: AgentCoreRuntimeConfig,
        stage: AgentStage,
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> None:
        require_strands()
        self.config = {
            "model_id": "agentcore-runtime",
            "runtime_arn_configured": bool(config.runtime_arn),
            "region": config.region,
            "qualifier": config.qualifier,
            "max_tokens": config.max_tokens,
            "stage": stage.value,
        }
        self._runtime_arn = config.runtime_arn
        self._region = config.region
        self._qualifier = config.qualifier
        self._max_tokens = config.max_tokens
        self._aws_profile = config.aws_profile
        self._runtime_session_id = config.runtime_session_id
        self._stage = stage
        self._tool_plan = self._freeze_tool_plan(tool_plan)
        self._tool_index = 0
        self._tool_call_history: list[dict[str, Any]] = []
        self._last_provider_metadata: dict[str, Any] = {}

    def actual_provider_metadata(self) -> dict[str, Any]:
        """Return only attribution captured from the last runtime response."""

        return dict(self._last_provider_metadata)

    def mark_provider_failure(self) -> None:
        """Mark a returned runtime response as degraded after local validation fails."""

        if self._last_provider_metadata:
            self._last_provider_metadata["status"] = "DEGRADED"
            self._last_provider_metadata["invocation_status"] = "FAILED"

    @staticmethod
    def _response_invocation_id(response: Any) -> str | None:
        """Extract an invocation identity only when the runtime returned one."""

        if not isinstance(response, dict):
            return None
        # AgentCore exposes the runtime invocation identity as a response header
        # named ``runtimeSessionId``.  Accept test/double transports that use the
        # equivalent JSON spellings, but never copy the client-side session value
        # when the provider did not return it.
        for key in ("invocationId", "invocation_id", "runtimeSessionId", "runtime_session_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _mark_response_returned(self, response: Any) -> None:
        """Record redacted attribution after transport returned a bounded response."""

        metadata: dict[str, Any] = {
            "mode": AgentProvider.AGENTCORE.value,
            "provider": AgentProvider.AGENTCORE.value,
            "model": "agentcore-runtime",
            "transport": "agentcore_invoke_agent_runtime",
            "region": self._region,
            "qualifier": self._qualifier,
            "runtime_configured": True,
            "invocation_proof": "returned",
            "status": "RETURNED",
            "invocation_status": "RETURNED",
        }
        invocation_id = self._response_invocation_id(response)
        if invocation_id is not None:
            metadata["invocation_id"] = invocation_id
        self._last_provider_metadata = metadata

    @staticmethod
    def _unpack_invocation_result(value: Any) -> tuple[Any, int, int, dict[str, Any]]:
        """Accept legacy test transports while preferring explicit result metadata."""

        if not isinstance(value, tuple) or len(value) not in {3, 4}:
            raise AgentProviderUnavailable("AgentCore invocation result is malformed")
        payload, input_tokens, output_tokens = value[:3]
        metadata = value[3] if len(value) == 4 else {}
        if not isinstance(metadata, dict):
            raise AgentProviderUnavailable("AgentCore invocation metadata is malformed")
        return payload, int(input_tokens), int(output_tokens), dict(metadata)

    @staticmethod
    def _freeze_tool_plan(tool_plan: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        """Copy the application-owned read plan before an invocation starts.

        The outer Strands event loop calls ``stream`` once per tool turn.  The plan
        is therefore model state, not request content: it must not be replaced by
        provider output or by a mutable caller-owned dictionary.  Only the two
        application-owned project read tools may enter this plan.
        """

        frozen: list[dict[str, Any]] = []
        for item in tool_plan:
            if not isinstance(item, dict):
                raise AgentProviderUnavailable("AgentCore read plan is malformed")
            name = item.get("tool")
            arguments = item.get("arguments", {})
            if name not in PROJECT_TOOL_NAMES:
                raise AgentProviderUnavailable("AgentCore read plan contains an unapproved tool")
            if not isinstance(arguments, dict):
                raise AgentProviderUnavailable("AgentCore read plan arguments are malformed")
            try:
                frozen_arguments = json.loads(
                    json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                )
            except (TypeError, ValueError) as exc:
                raise AgentProviderUnavailable(
                    "AgentCore read plan is not JSON serializable"
                ) from exc
            if not isinstance(frozen_arguments, dict):
                raise AgentProviderUnavailable("AgentCore read plan arguments are malformed")
            frozen.append({"tool": str(name), "arguments": frozen_arguments})
        return tuple(frozen)

    @property
    def stateful(self) -> bool:
        return True

    def update_config(self, **model_config: Any) -> None:
        max_tokens = model_config.get("max_tokens")
        if (
            isinstance(max_tokens, int)
            and not isinstance(max_tokens, bool)
            and max_tokens > self._max_tokens
        ):
            raise AgentBudgetExceeded("model max_tokens exceeds the frozen per-request cap")
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    @staticmethod
    def _prompt_text(messages: Messages, system_prompt: str | None) -> str:
        parts: list[str] = []
        if system_prompt:
            parts.append("SYSTEM:\n" + system_prompt)
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "user")).upper()
            content = message.get("content", "")
            if isinstance(content, list):
                rendered_blocks: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        rendered_blocks.append(str(item))
                    elif "text" in item:
                        rendered_blocks.append(str(item["text"]))
                    elif "toolUse" in item:
                        rendered_blocks.append(
                            "TOOL_USE:\n"
                            + json.dumps(
                                item["toolUse"],
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=str,
                            )
                        )
                    elif "toolResult" in item:
                        rendered_blocks.append(
                            "TOOL_RESULT:\n"
                            + json.dumps(
                                item["toolResult"],
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=str,
                            )
                        )
                    else:
                        # Preserve only the content block itself.  In particular,
                        # provider metadata is never rendered as model content.
                        rendered_blocks.append(
                            json.dumps(
                                item,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=str,
                            )
                        )
                rendered_content = "\n".join(rendered_blocks)
            else:
                rendered_content = str(content)
            parts.append(f"{role}:\n{rendered_content}")
        return "\n\n".join(parts)

    @classmethod
    def _structured_schema_instruction(cls, output_model: type[T]) -> str:
        """Append a deterministic, bounded output contract to a runtime prompt.

        The AgentCore entrypoint runs its own one-turn Strands agent, so the
        application-side ``structured_output_model`` is not visible inside that
        runtime.  Sending the canonical Pydantic schema as part of the prompt keeps
        the transport contract explicit while the adapter still performs the final
        ``model_validate`` below.  The schema is application-owned and bounded so a
        malformed/future model cannot turn this into an unbounded prompt expansion.
        """

        try:
            schema_text = json.dumps(
                output_model.model_json_schema(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise AgentProviderUnavailable("structured output schema is not serializable") from exc
        if len(schema_text.encode("utf-8")) > cls.MAX_STRUCTURED_SCHEMA_BYTES:
            raise AgentProviderUnavailable("structured output schema exceeds the bounded size")
        return (
            "\n\nAPPLICATION-OWNED STRUCTURED OUTPUT CONTRACT:\n"
            "Return exactly one JSON object that validates against this JSON Schema. "
            "Do not return Markdown, prose outside the object, or fields not in the schema. "
            "This contract controls formatting only; remain advisory and read-only.\n"
            + schema_text
        )

    @classmethod
    def _structured_input_schema_instruction(cls, tool_spec: ToolSpec) -> str:
        """Return the bounded canonical schema used by the outer structured tool."""

        input_schema = tool_spec.get("inputSchema")
        try:
            schema_text = json.dumps(
                input_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise AgentProviderUnavailable("structured tool schema is not serializable") from exc
        if len(schema_text.encode("utf-8")) > cls.MAX_STRUCTURED_SCHEMA_BYTES:
            raise AgentProviderUnavailable("structured tool schema exceeds the bounded size")
        return (
            "\n\nAPPLICATION-OWNED STRUCTURED TOOL CONTRACT:\n"
            f"Return exactly one JSON object for the {tool_spec.get('name', 'structured output')} "
            "tool. The object must validate against this canonical inputSchema. "
            "Do not return Markdown, prose outside the object, provider metadata, or "
            "wrapper fields.\n"
            + schema_text
        )

    @staticmethod
    def _structured_tool(tool_specs: list[ToolSpec] | None) -> ToolSpec | None:
        candidates = [
            spec
            for spec in (tool_specs or [])
            if isinstance(spec, dict) and spec.get("name") not in PROJECT_TOOL_NAMES
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _tool_events(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        messages: Messages,
        tool_specs: list[ToolSpec] | None,
    ) -> list[StreamEvent]:
        """Build one provider-shaped tool-use turn for the real Strands loop."""

        call_index = len(self._tool_call_history)
        tool_use_id = f"{self._stage.value}-tool-{call_index + 1}"
        self._tool_call_history.append(
            {"tool": name, "arguments": json.loads(json.dumps(arguments, sort_keys=True))}
        )
        return [
            {"messageStart": {"role": "assistant"}},
            {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": tool_use_id}}}},
            {
                "contentBlockDelta": {
                    "delta": {"toolUse": {"input": json.dumps(arguments, sort_keys=True)}}
                }
            },
            {"contentBlockStop": {}},
            {"messageStop": {"stopReason": "tool_use"}},
            {
                "metadata": {
                    "usage": _usage(messages, tool_specs, arguments),
                    "metrics": {"latencyMs": 0},
                }
            },
        ]

    @staticmethod
    def _extract_runtime_output(payload: Any) -> Any:
        """Unwrap only the known AgentCore response envelope, never metadata."""

        if isinstance(payload, dict) and "output" in payload:
            candidate = payload["output"]
        elif isinstance(payload, dict) and set(payload) == {"response"}:
            candidate = payload["response"]
        else:
            candidate = payload
        # Some local AgentCore clients add one singleton response wrapper.  Do not
        # unwrap a nested singleton ``output``: after the top-level envelope has
        # been removed, ``{"output": ...}`` can be a valid application result.
        if isinstance(candidate, dict) and set(candidate) == {"response"}:
            candidate = candidate["response"]
        return candidate

    @classmethod
    def _structured_candidate(cls, payload: Any) -> dict[str, Any]:
        candidate = cls._extract_runtime_output(payload)
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AgentProviderUnavailable(
                    "AgentCore returned invalid structured output"
                ) from exc
        if not isinstance(candidate, dict):
            raise AgentProviderUnavailable("AgentCore returned invalid structured output")
        return candidate

    @classmethod
    def _text_candidate(cls, payload: Any) -> str:
        candidate = cls._extract_runtime_output(payload)
        if isinstance(candidate, dict) and set(candidate) == {"response"}:
            candidate = candidate["response"]
        if isinstance(candidate, str):
            return candidate
        if isinstance(candidate, dict) and "text" in candidate:
            text = candidate["text"]
            if isinstance(text, str):
                return text
        if isinstance(candidate, dict) and "metadata" in candidate:
            raise AgentProviderUnavailable("AgentCore response did not contain model output")
        try:
            return json.dumps(candidate, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError) as exc:
            raise AgentProviderUnavailable("AgentCore response output is malformed") from exc

    def _invoke(self, prompt: str) -> tuple[Any, int, int, dict[str, Any]]:
        # A failed transport starts with no observed provider result.  In
        # particular, configuration alone must never become an invocation record.
        self._last_provider_metadata = {}
        if not self._runtime_arn:
            raise AgentProviderUnavailable("AgentCore runtime ARN is not configured")
        if not self._runtime_arn.startswith("arn:aws:bedrock-agentcore:"):
            raise AgentProviderUnavailable("AgentCore runtime ARN is not an allowed AWS runtime")
        try:
            import boto3  # type: ignore[import-untyped]

            session = boto3.Session(
                profile_name=self._aws_profile,
                region_name=self._region,
            )
            client = session.client("bedrock-agentcore", region_name=self._region)
            session_id = self._runtime_session_id or (
                "missing20-" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:40]
            )
            response = client.invoke_agent_runtime(
                agentRuntimeArn=self._runtime_arn,
                runtimeSessionId=session_id,
                payload=json.dumps(
                    {
                        "input": {
                            "prompt": prompt,
                            "stage": self._stage.value,
                            "advisory_only": True,
                        }
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
                qualifier=self._qualifier,
            )
        except AgentProviderUnavailable:
            raise
        except Exception as exc:  # pragma: no cover - exercised only with cloud credentials
            raise AgentProviderUnavailable("AgentCore invocation failed") from exc
        raw = _agentcore_response_bytes(response)
        self._mark_response_returned(response)
        try:
            payload = _agentcore_json_payload(raw)
        except Exception:
            self.mark_provider_failure()
            raise
        input_tokens = max(1, len(prompt.encode("utf-8")) // 4)
        output_tokens = max(1, len(raw) // 4)
        return payload, input_tokens, output_tokens, self.actual_provider_metadata()

    async def _invoke_async(self, prompt: str) -> tuple[Any, int, int, dict[str, Any]]:
        """Run the synchronous AgentCore SDK call outside Strands' event loop."""

        return await asyncio.to_thread(self._invoke, prompt)

    async def count_tokens(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
    ) -> int:
        del tool_specs, system_prompt_content
        return max(1, len(self._prompt_text(messages, system_prompt).encode("utf-8")) // 4)

    async def structured_output(
        self,
        output_model: type[T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        del kwargs
        request_prompt = self._prompt_text(prompt, system_prompt)
        request_prompt += self._structured_schema_instruction(output_model)
        invocation = await self._invoke_async(request_prompt)
        payload, input_tokens, output_tokens, invocation_metadata = self._unpack_invocation_result(
            invocation
        )
        if invocation_metadata:
            self._last_provider_metadata = invocation_metadata
        candidate = payload.get("output", payload) if isinstance(payload, dict) else payload
        if isinstance(candidate, dict) and isinstance(candidate.get("response"), dict):
            candidate = candidate["response"]
        try:
            structured = output_model.model_validate(candidate)
        except Exception as exc:
            self.mark_provider_failure()
            error_codes = tuple(
                str(item.get("type", "unknown"))
                for item in (exc.errors() if hasattr(exc, "errors") else ())
                if isinstance(item, dict)
            )
            candidate_keys = (
                tuple(sorted(str(key) for key in candidate))
                if isinstance(candidate, dict)
                else (type(candidate).__name__,)
            )
            LOGGER.warning(
                "AgentCore structured response rejected stage=%s model=%s "
                "candidate_keys=%s validation_codes=%s",
                self._stage.value,
                output_model.__name__,
                candidate_keys,
                error_codes,
            )
            raise AgentProviderUnavailable(
                "AgentCore returned an invalid structured response"
            ) from exc
        if self._last_provider_metadata:
            self._last_provider_metadata["status"] = "COMPLETE"
            self._last_provider_metadata["invocation_status"] = "COMPLETED"
        yield {
            "output": structured,
            "metadata": {
                "usage": {
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "totalTokens": input_tokens + output_tokens,
                },
                "metrics": {"latencyMs": 0},
                "provider_metadata": self.actual_provider_metadata(),
            },
        }

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        del tool_choice, system_prompt_content, kwargs
        specs = tool_specs or []
        available_names = {
            str(spec.get("name"))
            for spec in specs
            if isinstance(spec, dict) and spec.get("name") is not None
        }

        # Investigator read calls are frozen application-owned turns.  They happen
        # before any remote call and let the outer Strands loop execute the actual
        # audited tools against the case-scoped repository.
        if self._tool_index < len(self._tool_plan):
            planned = self._tool_plan[self._tool_index]
            name = str(planned["tool"])
            if name not in available_names:
                raise AgentProviderUnavailable("AgentCore read plan tool is unavailable")
            self._tool_index += 1
            for event in self._tool_events(
                name=name,
                arguments=dict(planned["arguments"]),
                messages=messages,
                tool_specs=tool_specs,
            ):
                yield event
            return

        structured = self._structured_tool(specs)
        request_prompt = self._prompt_text(messages, system_prompt)
        if structured is not None:
            request_prompt += self._structured_input_schema_instruction(structured)
            invocation = await self._invoke_async(request_prompt)
            payload, input_tokens, output_tokens, invocation_metadata = (
                self._unpack_invocation_result(invocation)
            )
            if invocation_metadata:
                self._last_provider_metadata = invocation_metadata
            try:
                candidate = self._structured_candidate(payload)
            except Exception:
                self.mark_provider_failure()
                raise
            for event in self._tool_events(
                name=str(structured["name"]),
                arguments=candidate,
                messages=messages,
                tool_specs=tool_specs,
            ):
                # The remote provider metadata is represented only by the bounded
                # Strands metadata event; it never becomes model content.
                if "metadata" in event:
                    cast(Any, event)["metadata"] = {
                        "usage": {
                            "inputTokens": input_tokens,
                            "outputTokens": output_tokens,
                            "totalTokens": input_tokens + output_tokens,
                        },
                        "metrics": {"latencyMs": 0},
                        "provider_metadata": self.actual_provider_metadata(),
                    }
                yield event
            return

        # Safe advisory-text fallback for callers that do not enable structured
        # output.  Even here, only the actual output/text field is rendered.
        invocation = await self._invoke_async(request_prompt)
        payload, input_tokens, output_tokens, invocation_metadata = self._unpack_invocation_result(
            invocation
        )
        if invocation_metadata:
            self._last_provider_metadata = invocation_metadata
        try:
            rendered = self._text_candidate(payload)
        except Exception:
            self.mark_provider_failure()
            raise
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": rendered}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield cast(Any, {
            "metadata": {
                "usage": {
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "totalTokens": input_tokens + output_tokens,
                },
                "metrics": {"latencyMs": 0},
                "provider_metadata": self.actual_provider_metadata(),
            }
        })


class BedrockNovaProFactory(AgentModelFactory):
    """Create Strands Bedrock clients only when an explicitly confirmed command invokes them."""

    provider = AgentProvider.BEDROCK

    def __init__(
        self,
        config: BedrockNovaProConfig | None = None,
        ledger: AgentBudgetLedger | None = None,
    ) -> None:
        self.config = config or BedrockNovaProConfig()
        self.ledger = ledger or AgentBudgetLedger(self.config.budget)

    def provenance(self) -> dict[str, Any]:
        """Return safe provider metadata; credentials and account IDs never escape."""

        return {
            "mode": AgentProvider.BEDROCK.value,
            "provider": AgentProvider.BEDROCK.value,
            "model": self.config.model_id,
            "region": self.config.region,
            "transport": "strands_bedrock_model",
        }

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> Any:
        del stage, output_payload, tool_plan
        require_strands()
        import boto3

        session = boto3.Session(
            profile_name=self.config.aws_profile,
            region_name=self.config.region,
        )
        # Nova rejects the optional Bedrock ``strict`` tool field.  Do not pass it;
        # deterministic Pydantic validation remains the harness boundary.
        model = BedrockModel(
            boto_session=session,
            model_id=self.config.model_id,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            streaming=self.config.streaming,
            use_native_token_count=False,
        )
        return BudgetedModel(model, self.ledger)


class ScriptedStrandsFactory(AgentModelFactory):
    """Factory for isolated, frozen model instances used by offline tests."""

    provider = AgentProvider.SCRIPTED

    def provenance(self) -> dict[str, Any]:
        return {
            "mode": AgentProvider.SCRIPTED.value,
            "provider": AgentProvider.SCRIPTED.value,
            "model": "scripted-strands-v1",
            "transport": "local_strands_model",
        }

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> ScriptedStrandsModel:
        return ScriptedStrandsModel(
            stage=stage,
            output_payload=output_payload,
            tool_plan=tool_plan,
        )


class AgentCoreRuntimeFactory(AgentModelFactory):
    """Create a bounded model adapter for an already deployed AgentCore Runtime."""

    provider = AgentProvider.AGENTCORE

    def __init__(
        self,
        config: AgentCoreRuntimeConfig | None = None,
        ledger: AgentBudgetLedger | None = None,
    ) -> None:
        self.config = config or AgentCoreRuntimeConfig()
        self.ledger = ledger or AgentBudgetLedger(self.config.budget)

    def provenance(self) -> dict[str, Any]:
        return {
            "mode": AgentProvider.AGENTCORE.value,
            "provider": AgentProvider.AGENTCORE.value,
            "model": "agentcore-runtime",
            "region": self.config.region,
            "qualifier": self.config.qualifier,
            "runtime_configured": bool(self.config.runtime_arn),
            "transport": "agentcore_invoke_agent_runtime",
        }

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> AgentCoreRuntimeModel:
        del output_payload
        return AgentCoreRuntimeModel(config=self.config, stage=stage, tool_plan=tool_plan)


def build_model_factory(
    provider: AgentProvider | str,
    *,
    budget: AgentBudget | None = None,
    aws_profile: str | None = None,
    region: str = "us-west-2",
    agentcore_runtime_arn: str | None = None,
    agentcore_qualifier: str = "DEFAULT",
) -> AgentModelFactory:
    """Resolve the explicit provider mode without making any network call."""

    mode = AgentProvider.parse(provider)
    selected_budget = budget or AgentBudget()
    if mode is AgentProvider.SCRIPTED:
        return ScriptedStrandsFactory()
    if mode is AgentProvider.BEDROCK:
        return BedrockNovaProFactory(
            BedrockNovaProConfig(
                region=region,
                aws_profile=aws_profile,
                budget=selected_budget,
            )
        )
    return AgentCoreRuntimeFactory(
        AgentCoreRuntimeConfig(
            runtime_arn=agentcore_runtime_arn,
            region=region,
            qualifier=agentcore_qualifier,
            aws_profile=aws_profile,
            budget=selected_budget,
        )
    )
