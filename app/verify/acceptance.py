"""Slice-46 structural acceptance-authorship verification (spec §7.1-7.3, App. B #8).

This module evaluates bounded structural evidence only.  It never reads acceptance-criterion
prose or claims semantic acceptance, human identity, or product behavior.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "slice46.acceptance_verification.v1"
AUTHORSHIP_CONTRACT_VERSION = "slice46.authorship.v1"
AUTHORSHIP_STATUSES = (
    "user_authored",
    "user_authored_system_normalized",
    "system_authored_unapproved",
    "system_authored_human_approved",
    "system_authored_independent_approved",
    "disputed",
)
APPROVAL_BASES = ("human_owner", "independent_agent_lineage")
SOURCE_KINDS = ("agent_generated", "extraction_promoted")
TRUSTED_PROVENANCE = "db_verified_independent_agent_lineage"
MAX_SCOPE = 10_000
_PAYLOAD_FIELDS = {
    "acceptance_criterion_id",
    "authorship_status",
    "source_kind",
    "source_reference",
    "evidence_reference",
}


class InvalidAcceptanceEvidence(ValueError):
    pass


def _bounded(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit:
        raise InvalidAcceptanceEvidence(f"{name} must be a non-blank bounded string")
    return value


def _uuid(name: str, value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidAcceptanceEvidence(f"{name} must be a UUID") from exc


def validate_authorship_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_FIELDS:
        raise InvalidAcceptanceEvidence("authorship payload has unknown or missing fields")
    status = _bounded("authorship_status", payload["authorship_status"], 128)
    source_kind = _bounded("source_kind", payload["source_kind"], 128)
    if status not in AUTHORSHIP_STATUSES or source_kind not in SOURCE_KINDS:
        raise InvalidAcceptanceEvidence("unsupported authorship status or source kind")
    evidence = _bounded("evidence_reference", payload["evidence_reference"], 500)
    if not evidence.startswith("sha256:") or len(evidence) != 71:
        raise InvalidAcceptanceEvidence("evidence_reference must be a sha256 digest")
    return {
        "acceptance_criterion_id": _uuid(
            "acceptance_criterion_id", payload["acceptance_criterion_id"]
        ),
        "authorship_status": status,
        "source_kind": source_kind,
        "source_reference": _uuid("source_reference", payload["source_reference"]),
        "evidence_reference": evidence,
    }


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def scope_digest(ids: Iterable[str]) -> str:
    canonical = sorted(_uuid("acceptance_criterion_id", item) for item in ids)
    if not canonical or len(canonical) > MAX_SCOPE or len(set(canonical)) != len(canonical):
        raise InvalidAcceptanceEvidence("scope must be non-empty, unique, and bounded")
    return canonical_digest(canonical)


def authorship_digest(chain: Iterable[tuple[str, int, str]]) -> str:
    rows = sorted((str(item[0]), int(item[1]), str(item[2])) for item in chain)
    return canonical_digest(rows)


def verifier_contract_hash() -> str:
    return canonical_digest(
        {
            "schema": SCHEMA_VERSION,
            "authorship_contract": AUTHORSHIP_CONTRACT_VERSION,
            "statuses": AUTHORSHIP_STATUSES,
            "approval_bases": APPROVAL_BASES,
            "trusted_provenance": TRUSTED_PROVENANCE,
        }
    )


@dataclass(frozen=True)
class AuthorshipEvidence:
    acceptance_criterion_id: str
    authorship_status: str
    authorship_provenance: str
    source_kind: str
    approval_basis: str | None
    source_db_proven: bool
    approval_db_bound: bool
    reviewer_active: bool
    reviewer_qualified: bool
    distinct_blueprint: bool
    distinct_version: bool
    distinct_model_route: bool
    current_record: bool


@dataclass(frozen=True)
class AcceptanceResult:
    acceptance_criterion_id: str
    eligibility_status: str
    reason_code: str


def evaluate_authorship(evidence: AuthorshipEvidence) -> AcceptanceResult:
    status = evidence.authorship_status
    if status not in AUTHORSHIP_STATUSES or not evidence.current_record:
        return AcceptanceResult(evidence.acceptance_criterion_id, "missing", "authorship_missing")
    if status == "disputed":
        return AcceptanceResult(evidence.acceptance_criterion_id, "disputed", "unresolved_dispute")
    if status == "system_authored_unapproved":
        return AcceptanceResult(evidence.acceptance_criterion_id, "unapproved", "generated_unapproved")
    controls = (
        status == "system_authored_independent_approved"
        and evidence.authorship_provenance == TRUSTED_PROVENANCE
        and evidence.source_kind in SOURCE_KINDS
        and evidence.approval_basis == "independent_agent_lineage"
        and evidence.source_db_proven
        and evidence.approval_db_bound
        and evidence.reviewer_active
        and evidence.reviewer_qualified
        and evidence.distinct_blueprint
        and evidence.distinct_version
        and evidence.distinct_model_route
    )
    if controls:
        return AcceptanceResult(
            evidence.acceptance_criterion_id,
            "eligible",
            "verified_independent_agent_approval",
        )
    return AcceptanceResult(evidence.acceptance_criterion_id, "untrusted", "approval_unverified")


@dataclass(frozen=True)
class Gate8Evidence:
    scope_resolved: bool = True
    binding_resolved: bool = False
    scope_count: int = 0
    run_present: bool = False
    verification_failed: bool = False
    missing_authorship_count: int = 0
    untrusted_count: int = 0
    disputed_count: int = 0
    unapproved_count: int = 0
    controls_failed_count: int = 0
    eligible_count: int = 0
    evidence_consistent: bool = False

    def gate_kwargs(self) -> dict[str, bool | int]:
        return {f"acceptance_{key}": value for key, value in {
            "scope_resolved": self.scope_resolved,
            "binding_resolved": self.binding_resolved,
            "scope_count": self.scope_count,
            "verification_run_present": self.run_present,
            "verification_failed": self.verification_failed,
            "missing_authorship_count": self.missing_authorship_count,
            "untrusted_count": self.untrusted_count,
            "disputed_count": self.disputed_count,
            "unapproved_count": self.unapproved_count,
            "controls_failed_count": self.controls_failed_count,
            "eligible_count": self.eligible_count,
            "evidence_consistent": self.evidence_consistent,
        }.items()}
