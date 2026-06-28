"""Agent qualification eval — pure scorer (Slice 40, §9.4 step 6-7 / §9.5.1).

A qualification run scores **recorded** dry-test case results against the realization's archetype
threshold. These pure helpers mirror, byte-for-byte, the DB GENERATED ``verdict`` expression and the
deferred children-verify trigger (migration 0039) so the two can never diverge — the DB is the
authority (a fake ``passed`` is rejected there), these helpers are for the repo + tests.

**Honesty:** the eval RESULTS are recorded inputs with ``caller_supplied_unverified`` provenance — no
agent executes here (a real eval harness + §9.4-step-5 project case generation are later). A
``critical failure`` is a critical case that FAILED (``is_critical AND NOT passed``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from app.agents.registry import ARCHETYPES

# §9.4-step-6/7 runtime values (B2: registry.ARCHETYPES, incl. 'ai_evaluation').
QUALIFICATION_ARCHETYPES = ARCHETYPES
# §9.5.1 — every archetype eval must include these case categories.
CASE_CATEGORIES = ("positive", "negative", "edge", "adversarial", "incomplete")
VERDICTS = ("passed", "failed")

MAX_CASE_REF_CHARS = 200


def derive_counts(cases: Iterable[Mapping]) -> tuple[int, int, int, set[str]]:
    """Return (total, passed, critical_failure_count, categories_present). Mirrors the DB trigger."""
    total = passed = critical_failures = 0
    categories: set[str] = set()
    for c in cases:
        total += 1
        is_passed = bool(c["passed"])
        is_critical = bool(c["is_critical"])
        if is_passed:
            passed += 1
        if is_critical and not is_passed:
            critical_failures += 1
        categories.add(c["case_category"])
    return total, passed, critical_failures, categories


def coverage_complete(
    categories_present: Iterable[str], required_categories: Iterable[str]
) -> bool:
    """True iff every required category appears among the present categories."""
    return set(required_categories) <= set(categories_present)


def expected_verdict(
    *,
    total: int,
    passed: int,
    critical_failure_count: int,
    coverage_complete: bool,
    min_cases: int,
    min_aggregate_score,
    require_zero_critical: bool,
) -> str:
    """Mirror the DB GENERATED verdict: passed IFF total≥min_cases AND passed/total≥threshold AND
    (no zero-critical violation) AND coverage complete."""
    if total < min_cases:
        return "failed"
    aggregate = Decimal(passed) / Decimal(total)
    if aggregate < Decimal(str(min_aggregate_score)):
        return "failed"
    if require_zero_critical and critical_failure_count > 0:
        return "failed"
    if not coverage_complete:
        return "failed"
    return "passed"


def validate_case_results(cases: Sequence[Mapping]) -> None:
    """Fail-closed shape check for recorded eval cases."""
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise ValueError("cases must be a sequence")
    for c in cases:
        ref = c.get("case_ref")
        if not isinstance(ref, str) or not (1 <= len(ref) <= MAX_CASE_REF_CHARS):
            raise ValueError(f"invalid case_ref: {ref!r}")
        if c.get("case_category") not in CASE_CATEGORIES:
            raise ValueError(f"invalid case_category: {c.get('case_category')!r}")
        for field in ("passed", "is_critical"):
            if not isinstance(c.get(field), bool):
                raise ValueError(f"{field} must be a bool in case {ref!r}")
