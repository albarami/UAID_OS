"""Strict Slice-44 security scan artifact contract and coverage derivation.

The artifact is connector-observed CI evidence for one exact commit. Validation proves
shape, binding, and declared scanner/category coverage; it does not prove scanner
infallibility or universal vulnerability absence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "slice44.security_scan.v1"
MAX_ARTIFACT_BYTES = 2_000_000
MAX_FINDINGS = 1_000
MAX_SUMMARY = 500
MAX_DETAIL = 4_000
MAX_EVIDENCE_REF = 500
MAX_KEY = 128

MANDATORY_CATEGORIES = (
    "authz",
    "injection",
    "secrets_exposure",
    "unsafe_tool",
    "supply_chain",
)
COVERAGE_STATUSES = (
    "completed_clean",
    "completed_with_findings",
    "failed",
    "unsupported",
)
SEVERITIES = ("low", "medium", "high", "critical")

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOP_FIELDS = {"schema_version", "commit_sha", "scanner_manifest", "categories"}
_MANIFEST_FIELDS = {
    "scanner_key",
    "scanner_version",
    "rule_pack_hash",
    "supported_categories",
}
_CATEGORY_FIELDS = {
    "category",
    "scanner_key",
    "scanner_version",
    "rule_pack_hash",
    "coverage_status",
    "findings",
}
_FINDING_FIELDS = {"fingerprint", "severity", "summary", "detail", "evidence_ref"}


def _rule_hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


# Code-owned logical scanner contracts. These names identify the bounded CI artifact
# producers; they are not claims about a third-party scanner's completeness.
SCANNER_ALLOWLIST: dict[str, dict[str, Any]] = {
    "uaid.authz_scan": {
        "scanner_version": "1",
        "rule_pack_hash": _rule_hash("uaid.authz_scan:1"),
        "supported_categories": frozenset({"authz"}),
    },
    "uaid.injection_scan": {
        "scanner_version": "1",
        "rule_pack_hash": _rule_hash("uaid.injection_scan:1"),
        "supported_categories": frozenset({"injection"}),
    },
    "uaid.secrets_scan": {
        "scanner_version": "1",
        "rule_pack_hash": _rule_hash("uaid.secrets_scan:1"),
        "supported_categories": frozenset({"secrets_exposure"}),
    },
    "uaid.unsafe_tool_scan": {
        "scanner_version": "1",
        "rule_pack_hash": _rule_hash("uaid.unsafe_tool_scan:1"),
        "supported_categories": frozenset({"unsafe_tool"}),
    },
    "uaid.supply_chain_scan": {
        "scanner_version": "1",
        "rule_pack_hash": _rule_hash("uaid.supply_chain_scan:1"),
        "supported_categories": frozenset({"supply_chain"}),
    },
}

_SEVERITY_MAPS: dict[tuple[str, str], dict[str, str]] = {
    (key, contract["scanner_version"]): {severity: severity for severity in SEVERITIES}
    for key, contract in SCANNER_ALLOWLIST.items()
}


class InvalidSecurityScanArtifact(ValueError):
    """Raised when security scan evidence is malformed or unsupported."""


@dataclass(frozen=True)
class ScannerManifestEntry:
    scanner_key: str
    scanner_version: str
    rule_pack_hash: str
    supported_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanner_key": self.scanner_key,
            "scanner_version": self.scanner_version,
            "rule_pack_hash": self.rule_pack_hash,
            "supported_categories": list(self.supported_categories),
        }


@dataclass(frozen=True)
class NormalizedSecurityFinding:
    fingerprint: str
    severity: str
    summary: str
    detail: str
    evidence_ref: str

    def to_dict(self) -> dict[str, str]:
        return {
            "fingerprint": self.fingerprint,
            "severity": self.severity,
            "summary": self.summary,
            "detail": self.detail,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True)
class CategoryCoverage:
    category: str
    scanner_key: str
    scanner_version: str
    rule_pack_hash: str
    coverage_status: str
    findings: tuple[NormalizedSecurityFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "scanner_key": self.scanner_key,
            "scanner_version": self.scanner_version,
            "rule_pack_hash": self.rule_pack_hash,
            "coverage_status": self.coverage_status,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class SecurityCoverageDecision:
    complete: bool
    mandatory_category_count: int
    completed_category_count: int
    failed_category_count: int
    finding_count: int

    def to_dict(self) -> dict[str, bool | int]:
        return {
            "complete": self.complete,
            "mandatory_category_count": self.mandatory_category_count,
            "completed_category_count": self.completed_category_count,
            "failed_category_count": self.failed_category_count,
            "finding_count": self.finding_count,
        }


@dataclass(frozen=True)
class SecurityScanArtifact:
    schema_version: str
    commit_sha: str
    scanner_manifest: tuple[ScannerManifestEntry, ...]
    categories: tuple[CategoryCoverage, ...]
    scanner_manifest_hash: str
    artifact_digest: str
    coverage: SecurityCoverageDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "commit_sha": self.commit_sha,
            "scanner_manifest": [entry.to_dict() for entry in self.scanner_manifest],
            "categories": [category.to_dict() for category in self.categories],
            "scanner_manifest_hash": self.scanner_manifest_hash,
            "artifact_digest": self.artifact_digest,
            "coverage": self.coverage.to_dict(),
        }


@dataclass(frozen=True)
class Gate5Evidence:
    scope_resolved: bool
    binding_resolved: bool
    run_present: bool
    artifact_trusted: bool
    execution_failed: bool
    coverage_complete: bool
    evidence_consistent: bool
    mandatory_category_count: int
    completed_category_count: int
    failed_category_count: int
    finding_count: int

    def gate_kwargs(self) -> dict[str, bool | int]:
        return {
            "security_scan_scope_resolved": self.scope_resolved,
            "security_scan_binding_resolved": self.binding_resolved,
            "security_scan_run_present": self.run_present,
            "security_scan_artifact_trusted": self.artifact_trusted,
            "security_scan_execution_failed": self.execution_failed,
            "security_scan_coverage_complete": self.coverage_complete,
            "security_scan_evidence_consistent": self.evidence_consistent,
            "security_scan_mandatory_category_count": self.mandatory_category_count,
            "security_scan_completed_category_count": self.completed_category_count,
            "security_scan_failed_category_count": self.failed_category_count,
            "security_scan_finding_count": self.finding_count,
        }

    def to_dict(self) -> dict[str, bool | int]:
        return self.gate_kwargs()


def canonical_digest(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvalidSecurityScanArtifact("artifact must contain canonical JSON data") from exc
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise InvalidSecurityScanArtifact("artifact exceeds the 2 MiB limit")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _text(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise InvalidSecurityScanArtifact(f"{name} must be a bounded non-blank string")
    return value.strip()


def _hash(name: str, value: Any) -> str:
    value = _text(name, value, MAX_KEY)
    if _HASH_RE.fullmatch(value) is None:
        raise InvalidSecurityScanArtifact(f"{name} must be a sha256 digest")
    return value


def _manifest(entries: Any) -> tuple[ScannerManifestEntry, ...]:
    if not isinstance(entries, list) or len(entries) != len(SCANNER_ALLOWLIST):
        raise InvalidSecurityScanArtifact("scanner manifest must contain the code-owned allowlist")
    normalized: list[ScannerManifestEntry] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != _MANIFEST_FIELDS:
            raise InvalidSecurityScanArtifact("scanner manifest has unknown or missing fields")
        key = _text("scanner_key", raw.get("scanner_key"), MAX_KEY)
        contract = SCANNER_ALLOWLIST.get(key)
        if contract is None or key in seen:
            raise InvalidSecurityScanArtifact("scanner manifest is not code-owned or is duplicated")
        seen.add(key)
        version = _text("scanner_version", raw.get("scanner_version"), MAX_KEY)
        rule_hash = _hash("rule_pack_hash", raw.get("rule_pack_hash"))
        categories = raw.get("supported_categories")
        if not isinstance(categories, list) or any(not isinstance(item, str) for item in categories):
            raise InvalidSecurityScanArtifact("scanner manifest supported_categories must be a list")
        supported = tuple(sorted(categories))
        if (
            version != contract["scanner_version"]
            or rule_hash != contract["rule_pack_hash"]
            or frozenset(supported) != contract["supported_categories"]
            or len(supported) != len(set(supported))
        ):
            raise InvalidSecurityScanArtifact("scanner manifest does not match the code-owned contract")
        normalized.append(ScannerManifestEntry(key, version, rule_hash, supported))
    if seen != set(SCANNER_ALLOWLIST):
        raise InvalidSecurityScanArtifact("scanner manifest is incomplete")
    return tuple(sorted(normalized, key=lambda item: item.scanner_key))


def _finding(raw: Any, scanner_key: str) -> NormalizedSecurityFinding:
    if not isinstance(raw, dict) or set(raw) != _FINDING_FIELDS:
        raise InvalidSecurityScanArtifact("finding fields are unknown or missing")
    fingerprint = _hash("fingerprint", raw.get("fingerprint"))
    provider_severity = _text("severity", raw.get("severity"), MAX_KEY)
    scanner_version = SCANNER_ALLOWLIST[scanner_key]["scanner_version"]
    severity = _SEVERITY_MAPS[(scanner_key, scanner_version)].get(provider_severity)
    if severity is None:
        raise InvalidSecurityScanArtifact("severity is unknown for this scanner")
    return NormalizedSecurityFinding(
        fingerprint=fingerprint,
        severity=severity,
        summary=_text("summary", raw.get("summary"), MAX_SUMMARY),
        detail=_text("detail", raw.get("detail"), MAX_DETAIL),
        evidence_ref=_text("evidence_ref", raw.get("evidence_ref"), MAX_EVIDENCE_REF),
    )


def _categories(
    entries: Any, manifest: Sequence[ScannerManifestEntry]
) -> tuple[CategoryCoverage, ...]:
    if not isinstance(entries, list) or len(entries) != len(MANDATORY_CATEGORIES):
        raise InvalidSecurityScanArtifact("mandatory category coverage is incomplete")
    contracts = {entry.scanner_key: entry for entry in manifest}
    normalized: list[CategoryCoverage] = []
    seen_categories: set[str] = set()
    seen_fingerprints: set[str] = set()
    total_findings = 0
    for raw in entries:
        if not isinstance(raw, dict) or set(raw) != _CATEGORY_FIELDS:
            raise InvalidSecurityScanArtifact("category result has unknown or missing fields")
        category = _text("category", raw.get("category"), MAX_KEY)
        if category not in MANDATORY_CATEGORIES or category in seen_categories:
            raise InvalidSecurityScanArtifact("mandatory category coverage is invalid or duplicated")
        seen_categories.add(category)
        scanner_key = _text("scanner_key", raw.get("scanner_key"), MAX_KEY)
        manifest_entry = contracts.get(scanner_key)
        version = _text("scanner_version", raw.get("scanner_version"), MAX_KEY)
        rule_hash = _hash("rule_pack_hash", raw.get("rule_pack_hash"))
        if (
            manifest_entry is None
            or category not in manifest_entry.supported_categories
            or version != manifest_entry.scanner_version
            or rule_hash != manifest_entry.rule_pack_hash
        ):
            raise InvalidSecurityScanArtifact("category scanner contract does not match manifest")
        status = raw.get("coverage_status")
        if status not in COVERAGE_STATUSES:
            raise InvalidSecurityScanArtifact("coverage_status is unsupported")
        raw_findings = raw.get("findings")
        if not isinstance(raw_findings, list):
            raise InvalidSecurityScanArtifact("findings must be a list")
        findings = tuple(_finding(item, scanner_key) for item in raw_findings)
        fingerprints = [item.fingerprint for item in findings]
        if len(fingerprints) != len(set(fingerprints)):
            raise InvalidSecurityScanArtifact("finding fingerprint is duplicated within a category")
        if seen_fingerprints.intersection(fingerprints):
            raise InvalidSecurityScanArtifact("finding fingerprint is duplicated within the run")
        seen_fingerprints.update(fingerprints)
        total_findings += len(findings)
        if total_findings > MAX_FINDINGS:
            raise InvalidSecurityScanArtifact("artifact exceeds the 1,000 finding limit")
        if status == "completed_clean" and findings:
            raise InvalidSecurityScanArtifact("completed_clean requires zero findings")
        if status == "completed_with_findings" and not findings:
            raise InvalidSecurityScanArtifact("completed_with_findings requires findings")
        if status in {"failed", "unsupported"} and findings:
            raise InvalidSecurityScanArtifact(f"{status} category cannot contain findings")
        normalized.append(
            CategoryCoverage(category, scanner_key, version, rule_hash, status, findings)
        )
    if seen_categories != set(MANDATORY_CATEGORIES):
        raise InvalidSecurityScanArtifact("mandatory category coverage is incomplete")
    return tuple(sorted(normalized, key=lambda item: item.category))


def evaluate_security_coverage(
    categories: Sequence[CategoryCoverage],
) -> SecurityCoverageDecision:
    completed = sum(
        item.coverage_status in {"completed_clean", "completed_with_findings"}
        for item in categories
    )
    failed = len(categories) - completed
    return SecurityCoverageDecision(
        complete=(
            {item.category for item in categories} == set(MANDATORY_CATEGORIES)
            and completed == len(MANDATORY_CATEGORIES)
        ),
        mandatory_category_count=len(MANDATORY_CATEGORIES),
        completed_category_count=completed,
        failed_category_count=failed,
        finding_count=sum(len(item.findings) for item in categories),
    )


def _manifest_payload(entries: Sequence[ScannerManifestEntry]) -> list[dict[str, Any]]:
    return [
        {
            "scanner_key": entry.scanner_key,
            "scanner_version": entry.scanner_version,
            "rule_pack_hash": entry.rule_pack_hash,
            "supported_categories": list(entry.supported_categories),
        }
        for entry in entries
    ]


def code_owned_manifest_hash() -> str:
    """Digest the exact code-owned scanner contract used for latest-binding selection."""
    return canonical_digest(
        [
            {
                "scanner_key": key,
                "scanner_version": contract["scanner_version"],
                "rule_pack_hash": contract["rule_pack_hash"],
                "supported_categories": sorted(contract["supported_categories"]),
            }
            for key, contract in sorted(SCANNER_ALLOWLIST.items())
        ]
    )


def scanner_manifest_hash(entries: Sequence[ScannerManifestEntry]) -> str:
    return canonical_digest(_manifest_payload(entries))


def artifact_digest(payload: Mapping[str, Any]) -> str:
    return canonical_digest(dict(payload))


def validate_security_scan_artifact(
    payload: Mapping[str, Any], *, expected_commit_sha: str
) -> SecurityScanArtifact:
    if not isinstance(payload, Mapping) or set(payload) != _TOP_FIELDS:
        raise InvalidSecurityScanArtifact("unknown or missing artifact fields")
    canonical_digest(dict(payload))  # validates canonical JSON + total byte cap
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise InvalidSecurityScanArtifact("unsupported security scan schema_version")
    if not isinstance(expected_commit_sha, str) or _SHA_RE.fullmatch(expected_commit_sha) is None:
        raise InvalidSecurityScanArtifact("expected commit_sha must be 40 lowercase hex characters")
    commit_sha = payload.get("commit_sha")
    if commit_sha != expected_commit_sha:
        raise InvalidSecurityScanArtifact("commit_sha does not match requested commit")
    manifest = _manifest(payload.get("scanner_manifest"))
    categories = _categories(payload.get("categories"), manifest)
    return SecurityScanArtifact(
        schema_version=SCHEMA_VERSION,
        commit_sha=commit_sha,
        scanner_manifest=manifest,
        categories=categories,
        scanner_manifest_hash=scanner_manifest_hash(manifest),
        artifact_digest=artifact_digest(payload),
        coverage=evaluate_security_coverage(categories),
    )
