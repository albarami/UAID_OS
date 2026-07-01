"""§9.6 agent replacement / failure policy (Slice 41) — pure.

The honesty model (B2): a failure event is a **REPORTED** §9.6 failure-pattern classification —
caller-supplied, **unverified** (Sanad-backed by a required ``source`` + ``source_provenance``
locked to ``caller_supplied_unverified`` this slice, B1). **No automatic diagnosis/classifier
exists**: ``validate_failure_event`` fail-closed-validates a *reported* pattern, it never infers
one. ``prescribe`` maps a pattern to the §9.6 response **verbatim** (spec:936-945) and
``effective_response`` enforces the §9.6 "must not retry forever" retry cap **as a DECISION**
(``escalate_or_blocker``) — nothing here executes, suspends, or authorizes anything (OD-1/D-41-1);
the prescribed responses (including ``suspend_and_audit``) are recorded recommendations only.

Storage lives in ``app.models.agent_failure_event``; the DB orchestrator is
``app.repositories.agent_failures``.
"""

from __future__ import annotations

from dataclasses import dataclass

RULESET_VERSION = "slice41.v1"

# §9.6 (spec:936-945) — the 8 failure patterns, machine values (row order preserved).
FAILURE_PATTERNS = (
    "missing_skill",
    "weak_instructions",
    "wrong_tools",
    "poor_model_performance",
    "context_overload",
    "repeated_reviewer_rejection",
    "safety_authority_violation",
    "persistent_inability",
)

# §9.6 — the 8 prescribed responses, machine values (row order preserved).
RESPONSES = (
    "create_or_recruit_specialist",
    "regenerate_prompt_and_eval",
    "update_tool_allowlist_after_security_review",
    "route_to_stronger_model",
    "improve_context_retrieval",
    "create_focused_remediation_task",
    "suspend_and_audit",
    "escalate_or_blocker",
)

# The §9.6 table verbatim: failure pattern → prescribed response.
PRESCRIPTION = dict(zip(FAILURE_PATTERNS, RESPONSES, strict=True))

SEVERITIES = ("low", "medium", "high", "critical")

# B1 — the only writable provenance tier this slice (the verified tier mirrors the A5 stores
# and is future work; the DB CHECK in migration 0040 is the backstop).
SOURCE_PROVENANCES = ("caller_supplied_unverified",)

# OD-4 — fixed retry cap; D-41-5: attempt_count >= cap ⇒ escalate_or_blocker (a decision).
MAX_FAILURE_ATTEMPTS = 3

# The no-failure effective value — deliberately NOT one of the 8 §9.6 responses.
NO_FAILURES_RESPONSE = "none"

# B3 — every user-supplied text field is bounded here AND by DB char_length CHECKs.
MAX_SOURCE = 100
MAX_EVIDENCE_REF = 200
MAX_SUMMARY = 2000
MAX_DETAIL = 8000
MAX_REPORTED_BY = 200


def prescribe(failure_pattern) -> str:
    """The §9.6 response for a (reported) failure pattern — fail-closed on unknown values."""
    if failure_pattern not in PRESCRIPTION:
        raise ValueError(f"unknown failure_pattern: {failure_pattern!r}")
    return PRESCRIPTION[failure_pattern]


def _require_bounded(name: str, value, max_chars: int) -> None:
    if not isinstance(value, str) or not (1 <= len(value) <= max_chars):
        raise ValueError(f"{name} must be a non-empty string of at most {max_chars} chars")


def validate_failure_event(
    *,
    failure_pattern,
    severity,
    source,
    reported_by,
    evidence_ref=None,
    summary=None,
    detail=None,
    source_provenance="caller_supplied_unverified",
) -> None:
    """Fail-closed validation of a REPORTED failure event (B2 — validation, never inference).

    Required: ``failure_pattern``/``severity`` enum members; ``source`` (the Sanad origin
    label, B1) and ``reported_by`` bounded non-empty; ``source_provenance`` in the writable
    tier set. Optional ``evidence_ref``/``summary``/``detail``: ``None`` or bounded non-empty
    strings (B3).
    """
    if failure_pattern not in FAILURE_PATTERNS:
        raise ValueError(f"unknown failure_pattern: {failure_pattern!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity!r}")
    if source_provenance not in SOURCE_PROVENANCES:
        raise ValueError(f"unsupported source_provenance: {source_provenance!r}")
    _require_bounded("source", source, MAX_SOURCE)
    _require_bounded("reported_by", reported_by, MAX_REPORTED_BY)
    for name, value, cap in (
        ("evidence_ref", evidence_ref, MAX_EVIDENCE_REF),
        ("summary", summary, MAX_SUMMARY),
        ("detail", detail, MAX_DETAIL),
    ):
        if value is not None:
            _require_bounded(name, value, cap)


def effective_response(*, attempt_count, latest_pattern) -> str:
    """The §9.6 decision ladder over REPORTED failures — a recommendation, never an action.

    ``none`` (no failures) → ``suspend_and_audit`` (safety, immediate regardless of count,
    D-41-6) → ``escalate_or_blocker`` (retry cap reached OR ``persistent_inability``, D-41-5)
    → otherwise the §9.6 prescription for the latest reported pattern.
    """
    if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or attempt_count < 0:
        raise ValueError(f"attempt_count must be a non-negative int, got {attempt_count!r}")
    if attempt_count == 0:
        if latest_pattern is not None:
            raise ValueError("attempt_count 0 is inconsistent with a latest_pattern")
        return NO_FAILURES_RESPONSE
    if latest_pattern not in FAILURE_PATTERNS:
        raise ValueError(f"unknown latest_pattern: {latest_pattern!r}")
    if latest_pattern == "safety_authority_violation":
        return "suspend_and_audit"
    if attempt_count >= MAX_FAILURE_ATTEMPTS or latest_pattern == "persistent_inability":
        return "escalate_or_blocker"
    return prescribe(latest_pattern)


@dataclass(frozen=True)
class ReplacementDecision:
    """The compute-on-read §9.6 replacement decision (OD-3/D-41-4) — non-authorizing,
    non-executing; the append-only failure events are the audit trail."""

    instance_id: str
    attempt_count: int
    latest_pattern: str | None
    prescribed_response: str | None
    budget_exhausted: bool
    effective_response: str
    ruleset_version: str = RULESET_VERSION

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "attempt_count": self.attempt_count,
            "latest_pattern": self.latest_pattern,
            "prescribed_response": self.prescribed_response,
            "budget_exhausted": self.budget_exhausted,
            "effective_response": self.effective_response,
            "ruleset_version": self.ruleset_version,
        }
