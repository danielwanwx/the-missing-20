"""Strands model adapters used by the offline harness and explicit Bedrock smoke."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from the_missing_20.ports.agent_model import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    AgentBudget,
    AgentBudgetExceeded,
    AgentBudgetLedger,
    AgentModelFactory,
    AgentProvider,
    AgentStage,
)

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
        yield {"output": output_model.model_validate(self._payload())}


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

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> Any:
        del stage, output_payload, tool_plan
        require_strands()
        import boto3  # type: ignore[import-untyped]

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
