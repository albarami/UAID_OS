"""Deterministic Slice-50 release verdicts (spec §24.3 / Appendix B gate #7).

The evaluator decides only the bounded disposition of the known issue set for one frozen release
candidate and one re-audited evidence-pack core.  It does not authorize deployment, prove issue-set
completeness, or represent a human decision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

SPEC_VERDICTS = (
    "passed",
    "passed_with_limitations",
    "failed_blocking_issue",
    "failed_missing_evidence",
    "requires_human_decision",
    "not_applicable",
)
CANONICAL_VERDICTS = (
    "passed",
    "passed_with_accepted_risk",
    "failed",
    "blocked",
)

VERDICT_CONTRACT_VERSION = "slice50.release_verdict.v1"
PROJECTION_CONTRACT_VERSION = "slice50.verdict_projection.v1"
INPUT_CONTRACT_VERSION = "slice50.release_verdict_input.v1"
DECISION_SCOPE = "known_bound_issue_disposition"
EXECUTION_PROVENANCE = "system_derived_release_verdict"
MAX_ISSUE_RESULTS = 10_000


def _version_hash(*values: str) -> str:
    raw = "\n".join(values).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


VERDICT_CONTRACT_HASH = _version_hash(
    VERDICT_CONTRACT_VERSION,
    PROJECTION_CONTRACT_VERSION,
    INPUT_CONTRACT_VERSION,
    DECISION_SCOPE,
)

_PROJECTION = {
    "passed": "passed",
    "passed_with_limitations": "passed_with_accepted_risk",
    "failed_blocking_issue": "failed",
    "failed_missing_evidence": "failed",
    "requires_human_decision": "blocked",
    "not_applicable": "blocked",
}
_ISSUE_STATUSES = {"open", "resolved", "accepted", "superseded"}


class ReleaseVerdictContractError(ValueError):
    """Raised when structural verdict input violates the code-owned contract."""


@dataclass(frozen=True)
class IssueDisposition:
    """Bounded structural projection of one frozen candidate issue binding."""

    binding_id: str
    issue_id: str
    status: str
    trusted_provenance: bool
    blocking: bool
    hard_blocker: bool
    exact_risk_acceptance: bool
    risk_authority_verified: bool

    def __post_init__(self) -> None:
        for name in ("binding_id", "issue_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ReleaseVerdictContractError(f"{name}_invalid")
        if self.status not in _ISSUE_STATUSES:
            raise ReleaseVerdictContractError("issue_status_invalid")
        for name in (
            "trusted_provenance",
            "blocking",
            "hard_blocker",
            "exact_risk_acceptance",
            "risk_authority_verified",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ReleaseVerdictContractError(f"{name}_invalid")
        if self.risk_authority_verified and not self.exact_risk_acceptance:
            raise ReleaseVerdictContractError("risk_authority_without_exact_acceptance")


@dataclass(frozen=True)
class ReleaseVerdictInput:
    """Code-owned input shape; no caller verdict/trust/gate fields are accepted."""

    assembly_complete: bool
    inventory_complete: bool
    issue_binding_exact: bool
    input_current: bool
    issues: tuple[IssueDisposition, ...]

    def __post_init__(self) -> None:
        for name in (
            "assembly_complete",
            "inventory_complete",
            "issue_binding_exact",
            "input_current",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ReleaseVerdictContractError(f"{name}_invalid")
        if not isinstance(self.issues, tuple) or len(self.issues) > MAX_ISSUE_RESULTS:
            raise ReleaseVerdictContractError("issue_result_count_invalid")
        if any(not isinstance(issue, IssueDisposition) for issue in self.issues):
            raise ReleaseVerdictContractError("issue_result_invalid")
        binding_ids = [issue.binding_id for issue in self.issues]
        issue_ids = [issue.issue_id for issue in self.issues]
        if len(set(binding_ids)) != len(binding_ids) or len(set(issue_ids)) != len(issue_ids):
            raise ReleaseVerdictContractError("issue_result_duplicate")


@dataclass(frozen=True)
class ReleaseVerdictDecision:
    spec_verdict: str
    canonical_verdict: str
    reason_code: str
    gate_eligible: bool
    decision_scope: str = DECISION_SCOPE
    execution_provenance: str = EXECUTION_PROVENANCE


def project_canonical_verdict(spec_verdict: str) -> str:
    """Apply the ruled, intentionally lossy six-to-four vocabulary projection."""

    try:
        return _PROJECTION[spec_verdict]
    except (KeyError, TypeError) as exc:
        raise ReleaseVerdictContractError("spec_verdict_invalid") from exc


def canonical_input_digest(value: ReleaseVerdictInput) -> str:
    """SHA-256 over the exact, canonically ordered structural decision input."""

    payload = {
        "contract_version": INPUT_CONTRACT_VERSION,
        "assembly_complete": value.assembly_complete,
        "inventory_complete": value.inventory_complete,
        "issue_binding_exact": value.issue_binding_exact,
        "input_current": value.input_current,
        "issues": [
            asdict(issue)
            for issue in sorted(value.issues, key=lambda row: (row.binding_id, row.issue_id))
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _decision(spec_verdict: str, reason_code: str, *, gate_eligible: bool = False) -> ReleaseVerdictDecision:
    return ReleaseVerdictDecision(
        spec_verdict=spec_verdict,
        canonical_verdict=project_canonical_verdict(spec_verdict),
        reason_code=reason_code,
        gate_eligible=gate_eligible,
    )


def evaluate_release_verdict(value: ReleaseVerdictInput) -> ReleaseVerdictDecision:
    """Evaluate the ruled strict issue-disposition ladder without side effects."""

    if not (
        value.assembly_complete
        and value.inventory_complete
        and value.issue_binding_exact
        and value.input_current
    ):
        return _decision(
            "failed_missing_evidence", "release_verdict_evidence_incomplete_or_stale"
        )
    if any(not issue.trusted_provenance for issue in value.issues):
        return _decision("failed_missing_evidence", "bound_issue_provenance_incomplete")

    active = tuple(issue for issue in value.issues if issue.status not in {"resolved", "superseded"})
    if any(issue.blocking or issue.hard_blocker for issue in active):
        return _decision("failed_blocking_issue", "open_blocking_or_hard_refusal_issue")

    limitations = tuple(issue for issue in active if issue.status in {"open", "accepted"})
    if limitations:
        if any(not issue.exact_risk_acceptance for issue in limitations):
            return _decision(
                "requires_human_decision", "open_issue_requires_risk_acceptance_authority"
            )
        if any(not issue.risk_authority_verified for issue in limitations):
            return _decision(
                "requires_human_decision", "risk_acceptance_authority_unverified"
            )
        return _decision(
            "passed_with_limitations",
            "bound_release_limitations_authoritatively_accepted",
            gate_eligible=True,
        )

    return _decision(
        "passed", "bound_release_issue_disposition_clean", gate_eligible=True
    )
