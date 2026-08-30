"""Small ports and immutable budgets for the Milestone 4 model boundary.

The application depends on a model factory rather than on a provider SDK.  This keeps
the safety-sensitive orchestration easy to exercise with the offline scripted provider
and makes the Bedrock provider an explicit, separately confirmed choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol

MAX_REQUESTS = 40
MAX_INPUT_TOKENS = 400_000
MAX_OUTPUT_TOKENS = 62_040
MAX_OUTPUT_TOKENS_PER_REQUEST = 1_551
PRIOR_ESTIMATED_COST_USD = Decimal("0.0814368")
INCREMENTAL_COST_CAP_USD = Decimal("0.5185632")
CUMULATIVE_COST_CAP_USD = Decimal("0.60")
INPUT_PRICE_PER_TOKEN = Decimal("0.80") / Decimal("1000000")
OUTPUT_PRICE_PER_TOKEN = Decimal("3.20") / Decimal("1000000")


class AgentProvider(StrEnum):
    """Providers accepted by this milestone."""

    SCRIPTED = "scripted"
    BEDROCK = "bedrock"
    AGENTCORE = "agentcore"

    @classmethod
    def parse(cls, value: str | AgentProvider) -> AgentProvider:
        """Parse the explicit provider mode without silently falling back.

        Provider selection is a deployment boundary.  A typo must therefore fail
        closed instead of accidentally routing a request to the local scripted
        implementation (or to a cloud provider).
        """

        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError("agent provider mode must be scripted, bedrock, or agentcore")
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                "agent provider mode must be one of: scripted, bedrock, agentcore"
            ) from exc


# More descriptive spelling for configuration and API callers.  Keep the enum
# name above for compatibility with the existing provider evidence scripts.
AgentProviderMode = AgentProvider


class AgentStage(StrEnum):
    """The fixed stages in the application-owned workflow."""

    RETRYABLE_INVESTIGATOR = "retryable_investigator"
    SHORT_SHIPMENT_INVESTIGATOR = "short_shipment_investigator"
    DUPLICATE_POSTING_INVESTIGATOR = "duplicate_posting_investigator"
    SYNTHESIS = "synthesis"
    EVALUATOR = "evaluator"


@dataclass(frozen=True, slots=True)
class AgentBudget:
    """Hard per-run limits; the model layer may never exceed these values."""

    max_requests: int = MAX_REQUESTS
    max_input_tokens: int = MAX_INPUT_TOKENS
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    max_output_tokens_per_request: int = MAX_OUTPUT_TOKENS_PER_REQUEST
    prior_cost_usd: Decimal = PRIOR_ESTIMATED_COST_USD
    incremental_cost_cap_usd: Decimal = INCREMENTAL_COST_CAP_USD
    cumulative_cost_cap_usd: Decimal = CUMULATIVE_COST_CAP_USD
    input_price_per_token: Decimal = INPUT_PRICE_PER_TOKEN
    output_price_per_token: Decimal = OUTPUT_PRICE_PER_TOKEN
    per_call_timeout_seconds: float = 45.0
    whole_run_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if self.max_requests > MAX_REQUESTS:
            raise ValueError("max_requests exceeds the frozen request cap")
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0:
            raise ValueError("token budgets must be positive")
        if self.max_input_tokens > MAX_INPUT_TOKENS:
            raise ValueError("max_input_tokens exceeds the frozen input-token cap")
        if self.max_output_tokens > MAX_OUTPUT_TOKENS:
            raise ValueError("max_output_tokens exceeds the frozen output-token cap")
        if self.max_output_tokens_per_request <= 0:
            raise ValueError("max_output_tokens_per_request must be positive")
        if self.max_output_tokens_per_request > MAX_OUTPUT_TOKENS_PER_REQUEST:
            raise ValueError("per-request output ceiling exceeds the frozen cap")
        object.__setattr__(self, "prior_cost_usd", Decimal(str(self.prior_cost_usd)))
        object.__setattr__(
            self,
            "incremental_cost_cap_usd",
            Decimal(str(self.incremental_cost_cap_usd)),
        )
        object.__setattr__(
            self,
            "cumulative_cost_cap_usd",
            Decimal(str(self.cumulative_cost_cap_usd)),
        )
        object.__setattr__(self, "input_price_per_token", Decimal(str(self.input_price_per_token)))
        object.__setattr__(
            self,
            "output_price_per_token",
            Decimal(str(self.output_price_per_token)),
        )
        if self.prior_cost_usd < 0:
            raise ValueError("prior_cost_usd cannot be negative")
        if self.incremental_cost_cap_usd <= 0:
            raise ValueError("incremental_cost_cap_usd must be positive")
        if self.cumulative_cost_cap_usd <= 0:
            raise ValueError("cumulative_cost_cap_usd must be positive")
        if self.prior_cost_usd + self.incremental_cost_cap_usd > self.cumulative_cost_cap_usd:
            raise ValueError("prior plus incremental cost cap exceeds cumulative cap")
        if self.input_price_per_token <= 0 or self.output_price_per_token <= 0:
            raise ValueError("token prices must be positive")
        if self.per_call_timeout_seconds <= 0 or self.whole_run_timeout_seconds <= 0:
            raise ValueError("timeouts must be positive")
        if self.per_call_timeout_seconds > self.whole_run_timeout_seconds:
            raise ValueError("per-call timeout cannot exceed whole-run timeout")

    @property
    def prior_estimated_cost_usd(self) -> Decimal:
        """Compatibility name used by the provider evidence manifest."""

        return self.prior_cost_usd


class AgentBudgetExceeded(RuntimeError):
    """A model request or its reported usage would cross a frozen budget."""


class AgentProviderUnavailable(RuntimeError):
    """A selected real provider cannot be reached or is not configured.

    This error is intentionally distinct from a validation error.  The application
    records it as a visible advisory degradation and never treats it as an
    operational decision or an invitation to use an unapproved fallback provider.
    """


@dataclass(frozen=True, slots=True)
class AgentRequestReservation:
    """One atomically reserved provider request, held until response reconciliation."""

    reservation_id: int
    input_token_upper_bound: int
    output_token_upper_bound: int
    reserved_cost_usd: Decimal


class AgentBudgetLedger:
    """Thread-safe request and token ledger shared by every model stage.

    Reservation happens before a provider stream is started.  Providers report token
    usage in stream metadata; those values are accumulated under the same lock, so the
    next request is refused once a cap has been reached.
    """

    def __init__(self, budget: AgentBudget) -> None:
        self.budget = budget
        self._lock = Lock()
        self._request_count = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._reserved_input_tokens = 0
        self._reserved_output_tokens = 0
        self._actual_cost_usd = Decimal("0")
        self._reserved_cost_usd = Decimal("0")
        self._next_reservation_id = 1
        self._active_reservations: dict[int, AgentRequestReservation] = {}
        self._budget_errors = 0

    @staticmethod
    def _valid_count(value: object, *, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AgentBudgetExceeded(f"malformed {label}")
        return value

    def reserve_request(
        self,
        *,
        input_token_upper_bound: int | None = None,
        output_token_upper_bound: int | None = None,
        serialized_request: bytes | str | None = None,
    ) -> AgentRequestReservation:
        """Reserve a request and its worst-case cost before opening provider I/O.

        ``serialized_request`` is the complete UTF-8 request representation used at the
        model boundary.  Its byte length is a deliberately conservative token upper
        bound; callers may provide a larger bound but never a smaller one.
        """

        if serialized_request is not None:
            serialized_bytes = (
                serialized_request
                if isinstance(serialized_request, bytes)
                else serialized_request.encode("utf-8")
            )
            serialized_length = len(serialized_bytes)
            if input_token_upper_bound is None:
                input_token_upper_bound = serialized_length
            elif input_token_upper_bound < serialized_length:
                raise AgentBudgetExceeded(
                    "input-token reservation is smaller than serialized request bytes"
                )
        if input_token_upper_bound is None:
            input_token_upper_bound = 1
        input_bound = self._valid_count(input_token_upper_bound, label="input-token bound")
        if output_token_upper_bound is None:
            output_token_upper_bound = self.budget.max_output_tokens_per_request
        output_bound = self._valid_count(output_token_upper_bound, label="output-token bound")
        if output_bound <= 0:
            raise AgentBudgetExceeded("output-token reservation must be positive")
        output_bound = min(output_bound, self.budget.max_output_tokens_per_request)

        with self._lock:
            if self._request_count >= self.budget.max_requests:
                self._budget_errors += 1
                raise AgentBudgetExceeded("model request budget exhausted")
            if self._input_tokens + self._reserved_input_tokens + input_bound > (
                self.budget.max_input_tokens
            ):
                self._budget_errors += 1
                raise AgentBudgetExceeded("model input-token budget exhausted")
            available_output = self.budget.max_output_tokens - (
                self._output_tokens + self._reserved_output_tokens
            )
            if available_output <= 0:
                self._budget_errors += 1
                raise AgentBudgetExceeded("model output-token budget exhausted")
            output_bound = min(output_bound, available_output)
            reserved_cost = self._cost(input_bound, output_bound)
            if self._actual_cost_usd + self._reserved_cost_usd + reserved_cost > (
                self.budget.incremental_cost_cap_usd
            ):
                self._budget_errors += 1
                raise AgentBudgetExceeded("incremental provider cost cap exhausted")
            if (
                self.budget.prior_cost_usd
                + self._actual_cost_usd
                + self._reserved_cost_usd
                + reserved_cost
                > self.budget.cumulative_cost_cap_usd
            ):
                self._budget_errors += 1
                raise AgentBudgetExceeded("cumulative provider cost cap exhausted")
            self._request_count += 1
            reservation = AgentRequestReservation(
                reservation_id=self._next_reservation_id,
                input_token_upper_bound=input_bound,
                output_token_upper_bound=output_bound,
                reserved_cost_usd=reserved_cost,
            )
            self._next_reservation_id += 1
            self._active_reservations[reservation.reservation_id] = reservation
            self._reserved_input_tokens += input_bound
            self._reserved_output_tokens += output_bound
            self._reserved_cost_usd += reserved_cost
            return reservation

    def _cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.budget.input_price_per_token
            + Decimal(output_tokens) * self.budget.output_price_per_token
        )

    def reconcile(
        self,
        reservation: AgentRequestReservation,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Reconcile actual provider usage and release the unused reservation."""

        input_value = self._valid_count(input_tokens, label="input-token usage")
        output_value = self._valid_count(output_tokens, label="output-token usage")
        with self._lock:
            current = self._active_reservations.pop(reservation.reservation_id, None)
            if current != reservation:
                self._budget_errors += 1
                raise AgentBudgetExceeded("unknown or already reconciled request reservation")
            self._reserved_input_tokens -= reservation.input_token_upper_bound
            self._reserved_output_tokens -= reservation.output_token_upper_bound
            self._reserved_cost_usd -= reservation.reserved_cost_usd
            actual_cost = self._cost(input_value, output_value)
            self._input_tokens += input_value
            self._output_tokens += output_value
            self._actual_cost_usd += actual_cost
            malformed = (
                input_value > reservation.input_token_upper_bound
                or output_value > reservation.output_token_upper_bound
                or self._input_tokens > self.budget.max_input_tokens
                or self._output_tokens > self.budget.max_output_tokens
                or self._actual_cost_usd > self.budget.incremental_cost_cap_usd
                or self.budget.prior_cost_usd + self._actual_cost_usd
                > self.budget.cumulative_cost_cap_usd
            )
            if malformed:
                self._budget_errors += 1
                raise AgentBudgetExceeded("provider usage exceeded its reserved budget")

    def abandon_reservation(self, reservation: AgentRequestReservation) -> None:
        """Release a reservation after malformed provider metadata and record the fault."""

        with self._lock:
            current = self._active_reservations.pop(reservation.reservation_id, None)
            if current != reservation:
                self._budget_errors += 1
                raise AgentBudgetExceeded("unknown or already reconciled request reservation")
            self._reserved_input_tokens -= reservation.input_token_upper_bound
            self._reserved_output_tokens -= reservation.output_token_upper_bound
            self._reserved_cost_usd -= reservation.reserved_cost_usd
            self._budget_errors += 1

    def record_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        reservation: AgentRequestReservation | None = None,
    ) -> None:
        """Record usage, retaining compatibility for direct ledger callers.

        The model adapter always supplies its reservation.  A lone active reservation
        is reconciled for older callers that used ``reserve_request(); record_usage()``.
        """

        if reservation is not None:
            self.reconcile(
                reservation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return
        with self._lock:
            active = tuple(self._active_reservations.values())
        if len(active) == 1:
            self.reconcile(
                active[0],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return
        input_value = self._valid_count(input_tokens, label="input-token usage")
        output_value = self._valid_count(output_tokens, label="output-token usage")
        with self._lock:
            actual_cost = self._cost(input_value, output_value)
            self._input_tokens += input_value
            self._output_tokens += output_value
            self._actual_cost_usd += actual_cost

    @property
    def incremental_cost_usd(self) -> Decimal:
        with self._lock:
            return self._actual_cost_usd

    @property
    def cumulative_cost_usd(self) -> Decimal:
        with self._lock:
            return self.budget.prior_cost_usd + self._actual_cost_usd

    @property
    def reserved_cost_usd(self) -> Decimal:
        with self._lock:
            return self._reserved_cost_usd

    def snapshot(self) -> dict[str, int | float]:
        """Return a stable, public view used by smoke artifacts and tests."""

        with self._lock:
            return {
                "request_count": self._request_count,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "request_cap": self.budget.max_requests,
                "input_token_cap": self.budget.max_input_tokens,
                "output_token_cap": self.budget.max_output_tokens,
                "reserved_input_tokens": self._reserved_input_tokens,
                "reserved_output_tokens": self._reserved_output_tokens,
                "reserved_cost_usd": float(self._reserved_cost_usd),
                "reserved_incremental_cost_usd": float(
                    self._actual_cost_usd + self._reserved_cost_usd
                ),
                "reserved_cumulative_cost_usd": float(
                    self.budget.prior_cost_usd + self._actual_cost_usd + self._reserved_cost_usd
                ),
                "incremental_cost_usd": float(self._actual_cost_usd),
                "cumulative_cost_usd": float(self.budget.prior_cost_usd + self._actual_cost_usd),
                "prior_cost_usd": float(self.budget.prior_cost_usd),
                "incremental_cost_cap_usd": float(self.budget.incremental_cost_cap_usd),
                "cumulative_cost_cap_usd": float(self.budget.cumulative_cost_cap_usd),
                "remaining_incremental_cost_usd": float(
                    self.budget.incremental_cost_cap_usd
                    - self._actual_cost_usd
                    - self._reserved_cost_usd
                ),
                "remaining_cumulative_cost_usd": float(
                    self.budget.cumulative_cost_cap_usd
                    - self.budget.prior_cost_usd
                    - self._actual_cost_usd
                    - self._reserved_cost_usd
                ),
                "budget_error_count": self._budget_errors,
            }


class AgentModelFactory(Protocol):
    """Create one isolated model instance for a fixed workflow stage."""

    provider: AgentProvider

    def create(
        self,
        *,
        stage: AgentStage,
        output_payload: dict[str, Any],
        tool_plan: tuple[dict[str, Any], ...] = (),
    ) -> Any:
        """Return a Strands ``Model`` configured for exactly one stage."""
