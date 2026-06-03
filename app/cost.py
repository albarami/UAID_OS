"""Pure cost-ledger primitives (Slice 7, §19) — no DB, no I/O.

Money guards (`_to_decimal`), the §19.2 cost-component set, and the deterministic
stop-condition decision (`evaluate_stop`). DB persistence lives in
`app.repositories.cost`. Enforcement/halting is out of scope — `evaluate_stop`
only returns a signal for a future workflow runtime to consume.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

# §19.2 cost components. A cost event must name one of these.
COST_COMPONENTS: frozenset[str] = frozenset(
    {
        "model_inference",
        "tool_execution",
        "cloud_runtime",
        "ci_cd",
        "storage_retrieval",
        "monitoring",
        "human_review",
        "rework",
    }
)

# Money scale: NUMERIC(18, 6) — six fractional digits.
_MAX_SCALE = 6


class CostError(Exception):
    """Base class for cost-ledger validation/integrity errors."""


class InvalidAmount(CostError):
    """A money/quantity value is not a safe, finite, non-negative Decimal at scale ≤6."""


class InvalidComponent(CostError):
    """A cost component is not in the §19.2 set."""


class IdempotencyConflict(CostError):
    """An (tenant, source_system, external_ref) key was reused with different material data."""


class StopReason(str, Enum):
    NO_BUDGET = "no_budget"
    BUDGET_EXCEEDED = "budget_exceeded"
    DAILY_BUDGET_EXCEEDED = "daily_budget_exceeded"


@dataclass(frozen=True)
class CostStopDecision:
    """OK ⇒ may proceed; STOP ⇒ halt future work (reason set). Returned, never halting."""

    stop: bool
    reason: StopReason | None = None

    @classmethod
    def ok(cls) -> "CostStopDecision":
        return cls(stop=False, reason=None)

    @classmethod
    def stopped(cls, reason: StopReason) -> "CostStopDecision":
        return cls(stop=True, reason=reason)


@dataclass(frozen=True)
class BudgetCeilings:
    """Budget ceilings used by `evaluate_stop` (decoupled from the ORM row)."""

    max_total_cost_usd: Decimal
    max_daily_cost_usd: Decimal | None = None


def validate_component(component: str) -> str:
    if component not in COST_COMPONENTS:
        raise InvalidComponent(f"unknown cost component: {component!r}")
    return component


def to_decimal(value, field: str = "amount") -> Decimal:
    """Coerce a money/quantity input to a safe Decimal (or raise InvalidAmount).

    Accepts Decimal, int, or numeric str. Rejects float and bool (money must not
    enter as a float). Requires finite, non-negative, scale ≤ 6 — no silent
    rounding of money.
    """
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise InvalidAmount(f"{field}: bool is not a valid money value")
    if isinstance(value, float):
        raise InvalidAmount(f"{field}: float is not allowed; pass Decimal or str")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, (int, str)):
        try:
            dec = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise InvalidAmount(f"{field}: not a valid decimal: {value!r}") from exc
    else:
        raise InvalidAmount(f"{field}: unsupported type {type(value).__name__}")
    if not dec.is_finite():
        raise InvalidAmount(f"{field}: must be finite (got {value!r})")
    if dec < 0:
        raise InvalidAmount(f"{field}: must be non-negative (got {dec})")
    # exponent < -6 means more than 6 fractional digits.
    if dec.as_tuple().exponent < -_MAX_SCALE:
        raise InvalidAmount(f"{field}: more than {_MAX_SCALE} decimal places: {dec}")
    return dec


def evaluate_stop(
    *,
    total_spent: Decimal,
    daily_spent: Decimal,
    budget: BudgetCeilings | None,
) -> CostStopDecision:
    """Deterministic stop decision (§19.7). Fail-closed; threshold is ``>=``."""
    if budget is None:
        return CostStopDecision.stopped(StopReason.NO_BUDGET)  # D-A: fail-closed
    if total_spent >= budget.max_total_cost_usd:  # D-B: >=
        return CostStopDecision.stopped(StopReason.BUDGET_EXCEEDED)
    if budget.max_daily_cost_usd is not None and daily_spent >= budget.max_daily_cost_usd:
        return CostStopDecision.stopped(StopReason.DAILY_BUDGET_EXCEEDED)
    return CostStopDecision.ok()
