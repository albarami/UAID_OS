"""Pure Slice-49 evidence-pack assembly and audit contracts.

The module assembles bounded safe projections.  It never executes evidence,
decides release readiness, invents a verdict, or treats a content hash as a
signature.  Canonical export finalization is kept in ``evidence_export``.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

CANONICAL_SCHEMA_VERSION = "uaid.evidence_pack.v1.2"
EVIDENCE_PACK_CONTRACT_VERSION = "slice49.evidence_pack.v1"
PROJECTION_CONTRACT_VERSION = "slice49.evidence_projection.v1"
AUDIT_CONTRACT_VERSION = "slice49.evidence_audit.v1"
EXECUTION_PROVENANCE = "system_assembled_evidence_pack"
SEMANTIC_CONTRACT_HASH = "sha256:90e64eb7e786903f05712d45504b7ddd9078724d6aed97341477474d518908a7"
PROJECTION_CONTRACT_HASH = "sha256:f12faf251d243934a2b06ea4514d2e80720b9a58e49fe054eb6b96e76601a9ae"
AUDIT_CONTRACT_HASH = "sha256:3eb56da7d11157e89d0cd3daa047573930cd32d1c397263131d9c7de2bf0b012"

MAX_CORE_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024
MAX_ITEMS_PER_SECTION = 10_000
MAX_SOURCE_REFS = 50_000
MAX_TRACEABILITY_EDGES = 50_000
MAX_CODE_CHARS = 128
MAX_LABEL_CHARS = 255
MAX_EVIDENCE_REF_CHARS = 500

INVENTORY_SECTIONS = (
    "scope",
    "traceability",
    "candidate_issues",
    "risk_acceptances",
    "review_reports",
    "test_oracles",
    "security_scans",
    "shortcut_detectors",
    "acceptance_verification",
    "reviewer_quality",
    "sanad_provenance",
    "audit_checkpoint",
)

SOURCE_KINDS = (
    "intake_artifact",
    "intake_provenance",
    "release_candidate_issue_binding",
    "risk_acceptance_record",
    "release_finding",
    "release_issue",
    "review_report",
    "test_oracle_run",
    "security_scan_run",
    "shortcut_detector_run",
    "acceptance_verification_run",
    "reviewer_quality_record",
)

TRUSTED_COMMIT_TIERS = frozenset(
    {
        "connector_verified_ci",
        "connector_verified_ci_security",
        "connector_verified_ci_shortcut_corpus",
    }
)

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_AUDIT_ENTRY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PRESENCE_CODES = frozenset(
    {
        "present",
        "present_zero_rows",
        "missing_required_source",
        "inconsistent_source",
        "unsupported_this_slice",
        "deferred_to_slice_50",
        "deferred_to_slice_60",
    }
)
_PROHIBITED_PROJECTION_FIELDS = frozenset(
    {
        "title",
        "body",
        "data",
        "origin",
        "locator",
        "summary",
        "detail",
        "resolution",
        "rationale",
        "reason",
        "business_impact",
        "mitigation_plan",
        "controls",
        "accepted_by",
        "approver",
        "source",
        "failed_criteria",
        "suspected_shortcuts",
        "required_changes",
        "prompt",
        "response",
        "packet",
        "snippet",
        "secret",
        "raw_json",
        "url",
        "evidence_links",
    }
)
def _fields(*names: str) -> frozenset[str]:
    return frozenset({"id", *names})


PROJECTION_FIELDS = MappingProxyType(
    {
        "intake_artifact": _fields("kind", "ref_digest", "parent_id", "content_digest"),
        "intake_provenance": _fields(
            "artifact_id", "document_id", "origin_digest", "locator_digest"
        ),
        "release_candidate_issue_binding": _fields(
            "release_candidate_id", "release_issue_id"
        ),
        "risk_acceptance_record": _fields(
            "release_ref_digest",
            "subject_type",
            "subject_id",
            "severity",
            "status",
            "expires_at",
            "blocking_category",
            "approver_provenance",
        ),
        "release_finding": _fields(
            "finding_type",
            "category",
            "severity",
            "status",
            "source_provenance",
            "security_scan_category_result_id",
            "shortcut_detector_category_result_id",
        ),
        "release_issue": _fields(
            "issue_category",
            "severity",
            "blocking",
            "blocking_category",
            "status",
            "source_provenance",
            "source_finding_id",
        ),
        "review_report": _fields(
            "task_contract_id",
            "reviewer_instance_id",
            "layer",
            "verdict",
            "can_merge",
            "source_provenance",
        ),
        "test_oracle_run": _fields(
            "definition_schema_version",
            "definition_hash",
            "repo_binding_hash",
            "commit_sha",
            "execution_status",
            "observation_provenance",
            "execution_provenance",
            "failure_code",
            "reported_result_count",
            "reported_passed_count",
            "verdict",
        ),
        "security_scan_run": _fields(
            "artifact_schema_version",
            "repo_binding_hash",
            "commit_sha",
            "scanner_manifest_hash",
            "execution_status",
            "artifact_provenance",
            "execution_observation",
            "failure_code",
            "reported_category_count",
            "reported_finding_count",
            "coverage_complete",
            "coverage_verdict",
        ),
        "shortcut_detector_run": _fields(
            "schema_version",
            "repo_binding_hash",
            "commit_sha",
            "detector_contract_hash",
            "corpus_provenance",
            "execution_status",
            "failure_code",
            "reported_category_count",
            "reported_finding_count",
            "reported_reviewer_count",
            "coverage_complete",
            "coverage_verdict",
        ),
        "acceptance_verification_run": _fields(
            "schema_version",
            "scope_digest",
            "authorship_digest",
            "verifier_contract_hash",
            "execution_status",
            "execution_provenance",
            "failure_code",
            "reported_scope_count",
            "reported_eligible_count",
            "reported_unapproved_count",
            "reported_disputed_count",
            "reported_missing_or_untrusted_count",
            "evidence_consistent",
            "verdict",
        ),
        "reviewer_quality_record": _fields(
            "reviewer_instance_id",
            "reviewer_version_hash",
            "model_route_hash",
            "prompt_hash",
            "fixture_suite_hash",
            "schema_version",
            "qa_contract_hash",
            "policy_digest",
            "execution_status",
            "execution_provenance",
            "failure_code",
            "case_count",
            "critical_miss_rate",
            "false_approval_rate",
            "quality_status",
            "prescribed_decision",
            "coverage_complete",
            "next_calibration_due",
        ),
    }
)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "semantic_contract_version",
        "projection_contract_version",
        "project_id",
        "release_id",
        "generated_at",
        "scope",
        "traceability",
        "test_results",
        "review_reports",
        "reviewer_quality_records",
        "risk_acceptances",
        "provenance_chains",
        "audit_log_hash",
        "source_inventory",
        "source_refs",
        "release_issues",
        "release_findings",
        "security_scan_runs",
        "shortcut_detector_runs",
        "acceptance_verification_runs",
        "repo_commit_binding",
        "integrity",
        "assurance_limitations",
        "export_kind",
        "verdict",
        "verdict_attestation",
        "signatures",
        "signature_status",
    }
)
_CALLER_TRUTH_FIELDS = frozenset(
    {"complete", "verified", "passed", "trusted", "signed", "gate", "ready"}
)


class EvidencePackContractError(ValueError):
    """A bounded code-owned evidence-pack contract was violated."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise EvidencePackContractError("datetime_timezone_required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_code(value: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_CODE_CHARS:
        raise EvidencePackContractError(code)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return exact RFC-8259-compatible UTF-8 bytes for hashing and storage."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidencePackContractError("canonical_json_invalid") from exc
    return encoded


def digest_bytes(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RepoCommitBinding:
    state: str
    repo_binding_hash: str | None
    commit_sha: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "repo_binding_hash": self.repo_binding_hash,
            "commit_sha": self.commit_sha,
        }


def derive_repo_commit_binding(observations: Sequence[Mapping[str, Any]]) -> RepoCommitBinding:
    trusted: set[tuple[str, str]] = set()
    for row in observations:
        if row.get("truth_tier") not in TRUSTED_COMMIT_TIERS:
            continue
        repo_hash = row.get("repo_binding_hash")
        commit_sha = row.get("commit_sha")
        if not isinstance(repo_hash, str) or not _HASH_RE.fullmatch(repo_hash):
            raise EvidencePackContractError("trusted_repo_binding_invalid")
        if not isinstance(commit_sha, str) or not _COMMIT_RE.fullmatch(commit_sha):
            raise EvidencePackContractError("trusted_commit_sha_invalid")
        trusted.add((repo_hash, commit_sha))
    if not trusted:
        return RepoCommitBinding("missing_trusted_binding", None, None)
    if len(trusted) != 1:
        return RepoCommitBinding("trusted_binding_disagreement", None, None)
    repo_hash, commit_sha = trusted.pop()
    return RepoCommitBinding("agreed", repo_hash, commit_sha)


@dataclass(frozen=True)
class AuditCheckpointRef:
    id: uuid.UUID
    verification_ok: bool
    verified_through_seq: int | None
    verified_through_entry_hash: str | None
    verifier_contract_version: str
    verifier_contract_hash: str
    created_at: datetime
    first_bad_seq: int | None = None

    def __post_init__(self) -> None:
        _bounded_code(self.verifier_contract_version, "audit_contract_version_invalid")
        if not _HASH_RE.fullmatch(self.verifier_contract_hash):
            raise EvidencePackContractError("audit_contract_hash_invalid")
        if not self.verification_ok:
            raise EvidencePackContractError("audit_checkpoint_not_satisfying")
        if self.verified_through_seq is None or self.verified_through_seq < 1:
            raise EvidencePackContractError("audit_checkpoint_tip_missing")
        if not self.verified_through_entry_hash or not _AUDIT_ENTRY_HASH_RE.fullmatch(
            self.verified_through_entry_hash
        ):
            raise EvidencePackContractError("audit_checkpoint_hash_invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "verification_ok": self.verification_ok,
            "verified_through_seq": self.verified_through_seq,
            "verified_through_entry_hash": self.verified_through_entry_hash,
            "verifier_contract_version": self.verifier_contract_version,
            "verifier_contract_hash": self.verifier_contract_hash,
            "created_at": _utc(self.created_at),
            "first_bad_seq": self.first_bad_seq,
        }


@dataclass(frozen=True)
class EvidenceSourceRef:
    source_kind: str
    source_id: uuid.UUID
    truth_tier: str
    source_created_at: datetime
    projection: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise EvidencePackContractError("source_kind_not_allowed")
        _bounded_code(self.truth_tier, "truth_tier_invalid")
        keys = set(self.projection)
        if keys & _PROHIBITED_PROJECTION_FIELDS:
            raise EvidencePackContractError("projection_field_not_allowed")
        if keys - PROJECTION_FIELDS[self.source_kind]:
            raise EvidencePackContractError("projection_field_not_allowed")
        if str(self.projection.get("id")) != str(self.source_id):
            raise EvidencePackContractError("projection_source_id_mismatch")
        raw = canonical_json_bytes(dict(self.projection))
        if len(raw) > MAX_EVIDENCE_REF_CHARS * 16:
            raise EvidencePackContractError("projection_too_large")

    @property
    def projection_digest(self) -> str:
        return digest_bytes(canonical_json_bytes(dict(self.projection)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_id": str(self.source_id),
            "truth_tier": self.truth_tier,
            "source_created_at": _utc(self.source_created_at),
            "projection_digest": self.projection_digest,
            "projection": dict(self.projection),
        }


def _scalar(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def project_source_record(source_kind: str, row: Any) -> EvidenceSourceRef:
    """Build one code-owned safe projection; no caller field map is accepted."""
    if source_kind not in SOURCE_KINDS:
        raise EvidencePackContractError("source_kind_not_allowed")
    identifier = getattr(row, "id")
    created_at = getattr(row, "created_at")
    projection: dict[str, Any] = {"id": str(identifier)}
    truth_tier = "db_proven_structural"
    if source_kind == "intake_artifact":
        projection.update(
            {
                "kind": row.kind,
                "ref_digest": digest_bytes(row.ref),
                "parent_id": _scalar(row.parent_id),
                "content_digest": digest_bytes(
                    canonical_json_bytes(
                        {
                            "title": row.title,
                            "body": row.body,
                            "data": row.data,
                            "classification": row.classification,
                        }
                    )
                ),
            }
        )
    elif source_kind == "intake_provenance":
        truth_tier = "db_proven_sanad_record"
        projection.update(
            {
                "artifact_id": str(row.artifact_id),
                "document_id": _scalar(row.document_id),
                "origin_digest": digest_bytes(row.origin),
                "locator_digest": digest_bytes(row.locator) if row.locator else None,
            }
        )
    elif source_kind == "release_candidate_issue_binding":
        truth_tier = "db_proven_candidate_binding"
        projection.update(
            {
                "release_candidate_id": str(row.release_candidate_id),
                "release_issue_id": str(row.release_issue_id),
            }
        )
    elif source_kind == "risk_acceptance_record":
        truth_tier = row.approver_provenance
        projection.update(
            {
                "release_ref_digest": digest_bytes(row.release_id),
                "subject_type": row.subject_type,
                "subject_id": row.issue_id,
                "severity": row.severity,
                "status": row.status,
                "expires_at": _scalar(row.expiry_date),
                "blocking_category": row.blocking_category,
                "approver_provenance": row.approver_provenance,
            }
        )
    elif source_kind == "release_finding":
        truth_tier = row.source_provenance
        projection.update(
            {
                "finding_type": row.finding_type,
                "category": row.category,
                "severity": row.severity,
                "status": row.status,
                "source_provenance": row.source_provenance,
                "security_scan_category_result_id": _scalar(
                    row.security_scan_category_result_id
                ),
                "shortcut_detector_category_result_id": _scalar(
                    row.shortcut_detector_category_result_id
                ),
            }
        )
    elif source_kind == "release_issue":
        truth_tier = row.source_provenance
        projection.update(
            {
                "issue_category": row.issue_category,
                "severity": row.severity,
                "blocking": row.blocking,
                "blocking_category": row.blocking_category,
                "status": row.status,
                "source_provenance": row.source_provenance,
                "source_finding_id": _scalar(row.source_finding_id),
            }
        )
    elif source_kind == "review_report":
        truth_tier = row.source_provenance
        projection.update(
            {
                "task_contract_id": str(row.task_contract_id),
                "reviewer_instance_id": str(row.reviewer_instance_id),
                "layer": row.layer,
                "verdict": row.verdict,
                "can_merge": row.can_merge,
                "source_provenance": row.source_provenance,
            }
        )
    elif source_kind == "test_oracle_run":
        truth_tier = row.observation_provenance
        for name in (
            "definition_schema_version",
            "definition_hash",
            "repo_binding_hash",
            "commit_sha",
            "execution_status",
            "observation_provenance",
            "execution_provenance",
            "failure_code",
            "reported_result_count",
            "reported_passed_count",
            "verdict",
        ):
            projection[name] = _scalar(getattr(row, name))
    elif source_kind == "security_scan_run":
        truth_tier = row.artifact_provenance
        for name in (
            "artifact_schema_version",
            "repo_binding_hash",
            "commit_sha",
            "scanner_manifest_hash",
            "execution_status",
            "artifact_provenance",
            "execution_observation",
            "failure_code",
            "reported_category_count",
            "reported_finding_count",
            "coverage_complete",
            "coverage_verdict",
        ):
            projection[name] = _scalar(getattr(row, name))
    elif source_kind == "shortcut_detector_run":
        truth_tier = row.corpus_provenance
        for name in (
            "schema_version",
            "repo_binding_hash",
            "commit_sha",
            "detector_contract_hash",
            "corpus_provenance",
            "execution_status",
            "failure_code",
            "reported_category_count",
            "reported_finding_count",
            "reported_reviewer_count",
            "coverage_complete",
            "coverage_verdict",
        ):
            projection[name] = _scalar(getattr(row, name))
    elif source_kind == "acceptance_verification_run":
        truth_tier = row.execution_provenance
        for name in (
            "schema_version",
            "scope_digest",
            "authorship_digest",
            "verifier_contract_hash",
            "execution_status",
            "execution_provenance",
            "failure_code",
            "reported_scope_count",
            "reported_eligible_count",
            "reported_unapproved_count",
            "reported_disputed_count",
            "reported_missing_or_untrusted_count",
            "evidence_consistent",
            "verdict",
        ):
            projection[name] = _scalar(getattr(row, name))
    elif source_kind == "reviewer_quality_record":
        truth_tier = row.execution_provenance
        for name in (
            "reviewer_instance_id",
            "reviewer_version_hash",
            "model_route_hash",
            "prompt_hash",
            "fixture_suite_hash",
            "schema_version",
            "qa_contract_hash",
            "policy_digest",
            "execution_status",
            "execution_provenance",
            "failure_code",
            "case_count",
            "critical_miss_rate",
            "false_approval_rate",
            "quality_status",
            "prescribed_decision",
            "coverage_complete",
            "next_calibration_due",
        ):
            projection[name] = _scalar(getattr(row, name))
    return EvidenceSourceRef(
        source_kind=source_kind,
        source_id=identifier,
        truth_tier=truth_tier,
        source_created_at=created_at,
        projection=projection,
    )


@dataclass(frozen=True)
class SectionInventory:
    section_code: str
    presence_code: str
    item_count: int
    section_digest: str
    required: bool
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.section_code not in INVENTORY_SECTIONS:
            raise EvidencePackContractError("section_not_allowed")
        if self.presence_code not in _PRESENCE_CODES:
            raise EvidencePackContractError("presence_code_not_allowed")
        if not 0 <= self.item_count <= MAX_ITEMS_PER_SECTION:
            raise EvidencePackContractError("section_item_count_invalid")
        if not _HASH_RE.fullmatch(self.section_digest):
            raise EvidencePackContractError("section_digest_invalid")
        if self.failure_code is not None:
            _bounded_code(self.failure_code, "failure_code_invalid")
        if self.presence_code in {"missing_required_source", "inconsistent_source"}:
            if self.failure_code is None:
                raise EvidencePackContractError("section_failure_code_required")

    @property
    def blocks_completeness(self) -> bool:
        return self.required and self.presence_code in {
            "missing_required_source",
            "inconsistent_source",
            "unsupported_this_slice",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "section_code": self.section_code,
            "presence_code": self.presence_code,
            "item_count": self.item_count,
            "section_digest": self.section_digest,
            "required": self.required,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True)
class CoreAssembly:
    payload: Mapping[str, Any]
    canonical_text: str
    content_hash: str
    assembly_status: str
    source_set_digest: str
    traceability_digest: str


_SOURCE_OUTPUTS = {
    "test_oracle_run": "test_results",
    "review_report": "review_reports",
    "reviewer_quality_record": "reviewer_quality_records",
    "risk_acceptance_record": "risk_acceptances",
    "intake_provenance": "provenance_chains",
    "release_issue": "release_issues",
    "release_finding": "release_findings",
    "security_scan_run": "security_scan_runs",
    "shortcut_detector_run": "shortcut_detector_runs",
    "acceptance_verification_run": "acceptance_verification_runs",
}


def assemble_core(
    *,
    project_id: uuid.UUID,
    release_candidate_id: uuid.UUID,
    release_ref_digest: str,
    generated_at: datetime,
    frozen_at: datetime,
    artifact_scope_digest: str,
    issue_binding_digest: str,
    source_refs: Sequence[EvidenceSourceRef],
    inventories: Sequence[SectionInventory],
    traceability: Sequence[Mapping[str, Any]],
    audit_checkpoint: AuditCheckpointRef,
    repo_commit_binding: RepoCommitBinding,
) -> CoreAssembly:
    if len(source_refs) > MAX_SOURCE_REFS:
        raise EvidencePackContractError("source_ref_cap_exceeded")
    if len(traceability) > MAX_TRACEABILITY_EDGES:
        raise EvidencePackContractError("traceability_cap_exceeded")
    for digest, code in (
        (release_ref_digest, "release_ref_digest_invalid"),
        (artifact_scope_digest, "artifact_scope_digest_invalid"),
        (issue_binding_digest, "issue_binding_digest_invalid"),
    ):
        if not _HASH_RE.fullmatch(digest):
            raise EvidencePackContractError(code)
    inventory_by_code = {row.section_code: row for row in inventories}
    if set(inventory_by_code) != set(INVENTORY_SECTIONS) or len(inventories) != len(
        INVENTORY_SECTIONS
    ):
        raise EvidencePackContractError("source_inventory_incomplete")

    ordered_refs = sorted(
        source_refs,
        key=lambda row: (row.source_kind, str(row.source_id), row.source_created_at),
    )
    ref_payloads = [row.as_dict() for row in ordered_refs]
    source_set_digest = digest_bytes(canonical_json_bytes(ref_payloads))
    traceability_rows = sorted(
        (dict(row) for row in traceability),
        key=lambda row: canonical_json_bytes(row),
    )
    traceability_digest = digest_bytes(canonical_json_bytes(traceability_rows))
    section_outputs: dict[str, list[dict[str, Any]]] = {
        output: [] for output in _SOURCE_OUTPUTS.values()
    }
    for row in ref_payloads:
        output = _SOURCE_OUTPUTS.get(row["source_kind"])
        if output:
            section_outputs[output].append(row)

    assembly_status = (
        "incomplete"
        if any(row.blocks_completeness for row in inventories)
        else "complete"
    )
    payload: dict[str, Any] = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "semantic_contract_version": EVIDENCE_PACK_CONTRACT_VERSION,
        "projection_contract_version": PROJECTION_CONTRACT_VERSION,
        "project_id": str(project_id),
        "release_id": str(release_candidate_id),
        "generated_at": _utc(generated_at),
        "scope": {
            "release_candidate_id": str(release_candidate_id),
            "release_ref_digest": release_ref_digest,
            "frozen_at": _utc(frozen_at),
            "artifact_scope_digest": artifact_scope_digest,
            "issue_binding_digest": issue_binding_digest,
            "scope_claim": "frozen_candidate_plus_conservative_project_artifacts",
        },
        "traceability": traceability_rows,
        **section_outputs,
        "audit_log_hash": audit_checkpoint.verified_through_entry_hash,
        "source_inventory": [
            inventory_by_code[code].as_dict() for code in INVENTORY_SECTIONS
        ],
        "source_refs": ref_payloads,
        "repo_commit_binding": repo_commit_binding.as_dict(),
        "integrity": {
            "source_set_digest": source_set_digest,
            "traceability_digest": traceability_digest,
            "audit_checkpoint": audit_checkpoint.as_dict(),
        },
        "assurance_limitations": [
            "assembled_evidence_does_not_prove_release_readiness",
            "candidate_has_no_direct_commit_foreign_key",
            "issue_bindings_do_not_prove_issue_completeness",
            "verdict_deferred_to_slice_50",
            "signer_tier_deferred_to_slice_60",
        ],
    }
    validate_semantic_payload(payload, canonical_export=False)
    raw = canonical_json_bytes(payload)
    if len(raw) > MAX_CORE_BYTES:
        raise EvidencePackContractError("core_size_cap_exceeded")
    return CoreAssembly(
        payload=MappingProxyType(payload),
        canonical_text=raw.decode("utf-8"),
        content_hash=digest_bytes(raw),
        assembly_status=assembly_status,
        source_set_digest=source_set_digest,
        traceability_digest=traceability_digest,
    )


def validate_semantic_payload(payload: Mapping[str, Any], *, canonical_export: bool) -> None:
    unknown = set(payload) - _TOP_LEVEL_FIELDS
    if unknown or set(payload) & _CALLER_TRUTH_FIELDS:
        raise EvidencePackContractError("field_not_allowed")
    required = {
        "schema_version",
        "semantic_contract_version",
        "projection_contract_version",
        "project_id",
        "release_id",
        "generated_at",
        "scope",
        "traceability",
        "test_results",
        "review_reports",
        "reviewer_quality_records",
        "risk_acceptances",
        "provenance_chains",
        "audit_log_hash",
        "source_inventory",
        "source_refs",
        "release_issues",
        "release_findings",
        "security_scan_runs",
        "shortcut_detector_runs",
        "acceptance_verification_runs",
        "repo_commit_binding",
        "integrity",
        "assurance_limitations",
    }
    if not required.issubset(payload):
        raise EvidencePackContractError("semantic_required_field_missing")
    if payload.get("schema_version") != CANONICAL_SCHEMA_VERSION:
        raise EvidencePackContractError("schema_version_invalid")
    if payload.get("semantic_contract_version") != EVIDENCE_PACK_CONTRACT_VERSION:
        raise EvidencePackContractError("semantic_contract_version_invalid")
    if payload.get("projection_contract_version") != PROJECTION_CONTRACT_VERSION:
        raise EvidencePackContractError("projection_contract_version_invalid")
    inventory = payload.get("source_inventory")
    if not isinstance(inventory, list) or {
        row.get("section_code") for row in inventory if isinstance(row, Mapping)
    } != set(INVENTORY_SECTIONS):
        raise EvidencePackContractError("source_inventory_incomplete")
    if any(
        not isinstance(row, Mapping)
        or set(row)
        != {
            "section_code",
            "presence_code",
            "item_count",
            "section_digest",
            "required",
            "failure_code",
        }
        for row in inventory
    ):
        raise EvidencePackContractError("source_inventory_shape_invalid")
    source_refs = payload.get("source_refs")
    if not isinstance(source_refs, list) or len(source_refs) > MAX_SOURCE_REFS:
        raise EvidencePackContractError("source_refs_invalid")
    normalized_refs: list[dict[str, Any]] = []
    for raw in source_refs:
        if not isinstance(raw, Mapping) or set(raw) != {
            "source_kind",
            "source_id",
            "truth_tier",
            "source_created_at",
            "projection_digest",
            "projection",
        }:
            raise EvidencePackContractError("source_ref_shape_invalid")
        try:
            ref = EvidenceSourceRef(
                source_kind=raw["source_kind"],
                source_id=uuid.UUID(raw["source_id"]),
                truth_tier=raw["truth_tier"],
                source_created_at=datetime.fromisoformat(
                    raw["source_created_at"].replace("Z", "+00:00")
                ),
                projection=raw["projection"],
            )
        except EvidencePackContractError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidencePackContractError("source_ref_shape_invalid") from exc
        if ref.projection_digest != raw["projection_digest"]:
            raise EvidencePackContractError("source_projection_digest_mismatch")
        normalized_refs.append(ref.as_dict())
    ordered_refs = sorted(
        normalized_refs,
        key=lambda row: (row["source_kind"], row["source_id"], row["source_created_at"]),
    )
    if normalized_refs != source_refs or source_refs != ordered_refs or len(
        {(row["source_kind"], row["source_id"]) for row in source_refs}
    ) != len(source_refs):
        raise EvidencePackContractError("source_ref_canonical_order_or_shape_invalid")
    output_kind = {
        "test_results": "test_oracle_run",
        "review_reports": "review_report",
        "reviewer_quality_records": "reviewer_quality_record",
        "risk_acceptances": "risk_acceptance_record",
        "provenance_chains": "intake_provenance",
        "release_issues": "release_issue",
        "release_findings": "release_finding",
        "security_scan_runs": "security_scan_run",
        "shortcut_detector_runs": "shortcut_detector_run",
        "acceptance_verification_runs": "acceptance_verification_run",
    }
    ref_bytes = {canonical_json_bytes(row) for row in source_refs}
    for output, kind in output_kind.items():
        rows = payload.get(output)
        if not isinstance(rows, list) or len(rows) > MAX_ITEMS_PER_SECTION:
            raise EvidencePackContractError("section_shape_or_cap_invalid")
        if any(
            not isinstance(row, Mapping)
            or row.get("source_kind") != kind
            or canonical_json_bytes(row) not in ref_bytes
            for row in rows
        ):
            raise EvidencePackContractError("section_source_projection_mismatch")
    scope = payload.get("scope")
    if not isinstance(scope, Mapping) or set(scope) != {
        "release_candidate_id",
        "release_ref_digest",
        "frozen_at",
        "artifact_scope_digest",
        "issue_binding_digest",
        "scope_claim",
    }:
        raise EvidencePackContractError("scope_shape_invalid")
    for key in ("release_ref_digest", "artifact_scope_digest", "issue_binding_digest"):
        if not isinstance(scope[key], str) or not _HASH_RE.fullmatch(scope[key]):
            raise EvidencePackContractError("scope_digest_invalid")
    binding = payload.get("repo_commit_binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "state",
        "repo_binding_hash",
        "commit_sha",
    }:
        raise EvidencePackContractError("repo_commit_binding_shape_invalid")
    if binding["state"] == "agreed":
        if not isinstance(binding["repo_binding_hash"], str) or not _HASH_RE.fullmatch(
            binding["repo_binding_hash"]
        ):
            raise EvidencePackContractError("repo_commit_binding_invalid")
        if not isinstance(binding["commit_sha"], str) or not _COMMIT_RE.fullmatch(
            binding["commit_sha"]
        ):
            raise EvidencePackContractError("repo_commit_binding_invalid")
    elif binding["state"] not in {
        "missing_trusted_binding",
        "trusted_binding_disagreement",
    } or binding["repo_binding_hash"] is not None or binding["commit_sha"] is not None:
        raise EvidencePackContractError("repo_commit_binding_invalid")
    traceability = payload.get("traceability")
    if not isinstance(traceability, list) or len(traceability) > MAX_TRACEABILITY_EDGES:
        raise EvidencePackContractError("traceability_shape_or_cap_invalid")
    known_sources = {
        (row["source_kind"], row["source_id"])
        for row in source_refs
    }
    for edge in traceability:
        if not isinstance(edge, Mapping) or set(edge) != {
            "edge_kind",
            "from_kind",
            "from_id",
            "to_kind",
            "to_id",
        }:
            raise EvidencePackContractError("traceability_edge_shape_invalid")
        if (edge["from_kind"], edge["from_id"]) not in known_sources or (
            edge["to_kind"],
            edge["to_id"],
        ) not in known_sources:
            raise EvidencePackContractError("traceability_edge_unresolved")
        _bounded_code(edge["edge_kind"], "traceability_edge_kind_invalid")
    integrity = payload.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "source_set_digest",
        "traceability_digest",
        "audit_checkpoint",
    }:
        raise EvidencePackContractError("integrity_shape_invalid")
    if integrity["source_set_digest"] != digest_bytes(canonical_json_bytes(source_refs)):
        raise EvidencePackContractError("source_set_digest_mismatch")
    if integrity["traceability_digest"] != digest_bytes(canonical_json_bytes(traceability)):
        raise EvidencePackContractError("traceability_digest_mismatch")
    checkpoint = integrity["audit_checkpoint"]
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != {
        "id",
        "verification_ok",
        "verified_through_seq",
        "verified_through_entry_hash",
        "verifier_contract_version",
        "verifier_contract_hash",
        "created_at",
        "first_bad_seq",
    }:
        raise EvidencePackContractError("audit_checkpoint_shape_invalid")
    try:
        AuditCheckpointRef(
            id=uuid.UUID(checkpoint["id"]),
            verification_ok=checkpoint["verification_ok"],
            verified_through_seq=checkpoint["verified_through_seq"],
            verified_through_entry_hash=checkpoint["verified_through_entry_hash"],
            verifier_contract_version=checkpoint["verifier_contract_version"],
            verifier_contract_hash=checkpoint["verifier_contract_hash"],
            created_at=datetime.fromisoformat(checkpoint["created_at"].replace("Z", "+00:00")),
            first_bad_seq=checkpoint["first_bad_seq"],
        )
    except (TypeError, ValueError) as exc:
        raise EvidencePackContractError("audit_checkpoint_shape_invalid") from exc
    if payload.get("audit_log_hash") != checkpoint["verified_through_entry_hash"]:
        raise EvidencePackContractError("audit_log_hash_mismatch")
    if payload.get("assurance_limitations") != [
        "assembled_evidence_does_not_prove_release_readiness",
        "candidate_has_no_direct_commit_foreign_key",
        "issue_bindings_do_not_prove_issue_completeness",
        "verdict_deferred_to_slice_50",
        "signer_tier_deferred_to_slice_60",
    ]:
        raise EvidencePackContractError("assurance_limitations_invalid")
    if canonical_export:
        if payload.get("verdict") not in {"passed", "passed_with_accepted_risk", "failed", "blocked"}:
            raise EvidencePackContractError("real_verdict_attestation_required")
        if payload.get("signatures") != []:
            raise EvidencePackContractError("signature_attestation_not_supported")
        if payload.get("signature_status") != "unsigned_signer_tier_not_implemented":
            raise EvidencePackContractError("signature_status_invalid")
    elif "verdict" in payload or "signatures" in payload:
        raise EvidencePackContractError("core_must_not_contain_attestations")


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "UAID_OS_Intake_Template_Pack_v1_2"
    / "schemas"
    / "evidence_pack_schema.json"
)
try:
    _CANONICAL_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(_CANONICAL_SCHEMA)
except (OSError, json.JSONDecodeError, SchemaError) as exc:  # pragma: no cover - startup failure
    raise RuntimeError("canonical evidence-pack schema is unavailable or invalid") from exc
_CANONICAL_VALIDATOR = Draft202012Validator(
    _CANONICAL_SCHEMA,
    format_checker=FormatChecker(),
)


def validate_canonical_payload(payload: Mapping[str, Any]) -> None:
    validate_semantic_payload(payload, canonical_export=True)
    try:
        _CANONICAL_VALIDATOR.validate(dict(payload))
    except ValidationError as exc:
        raise EvidencePackContractError("canonical_schema_invalid") from exc
