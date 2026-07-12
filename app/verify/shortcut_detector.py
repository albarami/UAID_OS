"""Slice-45 shortcut corpus validation, deterministic candidates, and gate evidence.

The deterministic checks are bounded candidate generators. Running every check proves
execution coverage for the versioned contract; it does not prove shortcut absence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from app.release.findings import SHORTCUT_CATEGORIES

CORPUS_SCHEMA_VERSION = "slice45.shortcut_review.v1"
DETECTOR_VERSION = "slice45.detector.v1"
FIXTURE_VERSION = "slice45.shortcut_fixtures.v1"
MAX_CORPUS_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_ENTRIES = 2_000
MAX_ENTRY_BYTES = 256 * 1024
MAX_EXTRACTED_TEXT_BYTES = 4 * 1024 * 1024
MAX_FINDINGS = 1_000
MAX_SUMMARY = 500
MAX_DETAIL = 4_000
MAX_EVIDENCE_REF = 500
MAX_KEY = 128

MANDATORY_CATEGORIES = tuple(item for item in SHORTCUT_CATEGORIES if item != "other")
IMPACT_FLAG_KEYS = frozenset(
    {
        "production_path",
        "requirement_bypassed",
        "evidence_fabricated",
        "failure_hidden",
        "test_integrity_weakened",
        "limited_scope",
    }
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TOP_FIELDS = {"schema_version", "commit_sha", "entries"}
_ENTRY_FIELDS = {"path", "content"}


class InvalidShortcutCorpus(ValueError):
    """The exact-commit review corpus is malformed, ambiguous, or over-cap."""


class InvalidImpactFlags(ValueError):
    """Impact flags cannot be mapped by the code-owned severity rubric."""


def canonical_digest(value: Any, *, max_bytes: int = MAX_CORPUS_BYTES) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvalidShortcutCorpus("corpus must contain canonical JSON data") from exc
    if len(encoded) > max_bytes:
        raise InvalidShortcutCorpus("corpus exceeds the byte limit")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _text(name: str, value: Any, *, max_bytes: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidShortcutCorpus(f"{name} must be non-blank")
    if len(value.encode("utf-8")) > max_bytes:
        raise InvalidShortcutCorpus(f"{name} exceeds the byte limit")
    return value


def _path(value: Any) -> str:
    path = _text("path", value, max_bytes=MAX_EVIDENCE_REF)
    if "\\" in path or "\x00" in path or path.startswith("/"):
        raise InvalidShortcutCorpus("path must be a safe relative POSIX path")
    parts = PurePosixPath(path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InvalidShortcutCorpus("path must be a safe relative POSIX path")
    return path


@dataclass(frozen=True)
class CorpusEntry:
    path: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "content": self.content}


@dataclass(frozen=True)
class ShortcutCorpus:
    schema_version: str
    commit_sha: str
    entries: tuple[CorpusEntry, ...]
    corpus_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "commit_sha": self.commit_sha,
            "entries": [entry.to_dict() for entry in self.entries],
            "corpus_digest": self.corpus_digest,
        }


@dataclass(frozen=True)
class NormalizedShortcutFinding:
    category: str
    fingerprint: str
    severity: str
    summary: str
    detail: str
    evidence_ref: str
    source: str
    impact_flags: dict[str, bool]
    reported_severity: str | None = None


@dataclass(frozen=True)
class DetectorCategoryResult:
    category: str
    completed: bool
    findings: tuple[NormalizedShortcutFinding, ...]
    evidence_digest: str


@dataclass(frozen=True)
class Gate6Evidence:
    scope_resolved: bool
    binding_resolved: bool
    run_present: bool
    corpus_trusted: bool
    execution_failed: bool
    independence_resolved: bool
    coverage_complete: bool
    evidence_consistent: bool
    mandatory_category_count: int
    completed_category_count: int
    failed_category_count: int
    reviewer_count: int
    finding_count: int

    def gate_kwargs(self) -> dict[str, bool | int]:
        return {
            "shortcut_review_scope_resolved": self.scope_resolved,
            "shortcut_review_binding_resolved": self.binding_resolved,
            "shortcut_review_run_present": self.run_present,
            "shortcut_review_corpus_trusted": self.corpus_trusted,
            "shortcut_review_execution_failed": self.execution_failed,
            "shortcut_review_independence_resolved": self.independence_resolved,
            "shortcut_review_coverage_complete": self.coverage_complete,
            "shortcut_review_evidence_consistent": self.evidence_consistent,
            "shortcut_review_mandatory_category_count": self.mandatory_category_count,
            "shortcut_review_completed_category_count": self.completed_category_count,
            "shortcut_review_failed_category_count": self.failed_category_count,
            "shortcut_review_reviewer_count": self.reviewer_count,
            "shortcut_review_finding_count": self.finding_count,
        }


def validate_shortcut_corpus(
    payload: Mapping[str, Any], *, expected_commit_sha: str
) -> ShortcutCorpus:
    if not isinstance(payload, Mapping) or set(payload) != _TOP_FIELDS:
        raise InvalidShortcutCorpus("corpus has unknown or missing fields")
    digest = canonical_digest(dict(payload))
    if payload.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise InvalidShortcutCorpus("unsupported corpus schema_version")
    if not isinstance(expected_commit_sha, str) or _SHA_RE.fullmatch(expected_commit_sha) is None:
        raise InvalidShortcutCorpus("expected commit_sha must be 40 lowercase hex characters")
    if payload.get("commit_sha") != expected_commit_sha:
        raise InvalidShortcutCorpus("commit_sha does not match requested commit")
    raw_entries = payload.get("entries")
    if (
        not isinstance(raw_entries, list)
        or not raw_entries
        or len(raw_entries) > MAX_MANIFEST_ENTRIES
    ):
        raise InvalidShortcutCorpus("entries must be a non-empty bounded list")
    entries: list[CorpusEntry] = []
    paths: set[str] = set()
    extracted_bytes = 0
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise InvalidShortcutCorpus("entry has unknown or missing fields")
        path = _path(raw.get("path"))
        if path in paths:
            raise InvalidShortcutCorpus("duplicate corpus path")
        paths.add(path)
        content = _text("content", raw.get("content"), max_bytes=MAX_ENTRY_BYTES)
        extracted_bytes += len(content.encode("utf-8"))
        if extracted_bytes > MAX_EXTRACTED_TEXT_BYTES:
            raise InvalidShortcutCorpus("extracted corpus text exceeds the byte limit")
        entries.append(CorpusEntry(path, content))
    return ShortcutCorpus(
        CORPUS_SCHEMA_VERSION,
        expected_commit_sha,
        tuple(sorted(entries, key=lambda item: item.path)),
        digest,
    )


def derive_severity(flags: Mapping[str, Any]) -> str:
    if not isinstance(flags, Mapping) or set(flags) != IMPACT_FLAG_KEYS:
        raise InvalidImpactFlags("impact flags must match the code-owned rubric")
    if any(not isinstance(value, bool) for value in flags.values()):
        raise InvalidImpactFlags("impact flags must be booleans")
    if flags["limited_scope"] and flags["production_path"]:
        raise InvalidImpactFlags("impact flags are contradictory")
    consequential = any(
        flags[key] for key in ("requirement_bypassed", "evidence_fabricated", "failure_hidden")
    )
    if flags["production_path"] and consequential:
        return "critical"
    if consequential:
        return "high"
    if flags["test_integrity_weakened"]:
        return "medium"
    if flags["limited_scope"]:
        return "low"
    raise InvalidImpactFlags("impact flags do not establish a supported severity")


def _flags(category: str, path: str) -> dict[str, bool]:
    test_only = path.startswith("tests/") or "/tests/" in path
    return {
        "production_path": not test_only,
        "requirement_bypassed": category
        in {
            "hardcoded_value",
            "static_response",
            "disabled_validation",
            "placeholder_ui",
            "todo_in_required_path",
            "local_only_substitute",
            "acceptance_silently_skipped",
        },
        "evidence_fabricated": category in {"fake_integration", "readiness_without_evidence"},
        "failure_hidden": category == "error_swallowing",
        "test_integrity_weakened": category in {"weakened_tests", "tests_check_implementation"},
        "limited_scope": False,
    }


_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "hardcoded_value": (re.compile(r"==\s*['\"](?:\d{3,}|fixed|admin)['\"]", re.I),),
    "static_response": (re.compile(r"return\s+\{[^\n]*(?:always|fixed|ok)[^\n]*\}", re.I),),
    "fake_integration": (re.compile(r"\b(?:class|def)\s+(?:Fake|Mock|Stub)\w+", re.I),),
    "disabled_validation": (re.compile(r"(?:validation|validate)[A-Z_a-z]*\s*=\s*False", re.I),),
    "weakened_tests": (re.compile(r"\bassert\s+True\b"),),
    "error_swallowing": (
        re.compile(r"except\s+(?:Exception|BaseException)(?:\s+as\s+\w+)?:\s*\n\s*pass\b"),
    ),
    "placeholder_ui": (re.compile(r"\b(?:coming soon|placeholder)\b", re.I),),
    "todo_in_required_path": (re.compile(r"\bTODO\b.*(?:implement|required)", re.I),),
    "local_only_substitute": (re.compile(r"(?:localhost|127\.0\.0\.1)(?::\d+)?", re.I),),
    "acceptance_silently_skipped": (
        re.compile(r"(?:pytest\.mark\.skip|unittest\.skip|@skip\b)", re.I),
    ),
    "tests_check_implementation": (re.compile(r"\bassert\s+\w+\._[A-Za-z_]"),),
    "readiness_without_evidence": (
        re.compile(r"return\s+True[^\n]*(?:ready|dependency)|(?:ready|readiness)\s*=\s*True", re.I),
    ),
}


def detector_contract_hash() -> str:
    contract = {
        "detector_version": DETECTOR_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "categories": {
            category: [pattern.pattern for pattern in patterns]
            for category, patterns in sorted(_RULES.items())
        },
        "impact_flags": sorted(IMPACT_FLAG_KEYS),
    }
    return canonical_digest(contract)


def _candidate(category: str, path: str, rule_index: int) -> NormalizedShortcutFinding:
    flags = _flags(category, path)
    severity = derive_severity(flags)
    fingerprint = canonical_digest(
        {"category": category, "path": path, "rule_index": rule_index}, max_bytes=MAX_KEY * 8
    )
    label = category.replace("_", " ")
    return NormalizedShortcutFinding(
        category=category,
        fingerprint=fingerprint,
        severity=severity,
        summary=f"Deterministic shortcut candidate: {label}",
        detail=(
            f"The code-owned {DETECTOR_VERSION} rule reported a {label} candidate. "
            "This is a candidate observation, not proof of intent or universal detector coverage."
        ),
        evidence_ref=f"path:{path}",
        source=DETECTOR_VERSION,
        impact_flags=flags,
    )


def run_deterministic_detectors(
    corpus: ShortcutCorpus,
) -> tuple[DetectorCategoryResult, ...]:
    results: list[DetectorCategoryResult] = []
    total = 0
    for category in MANDATORY_CATEGORIES:
        findings: list[NormalizedShortcutFinding] = []
        for entry in corpus.entries:
            for index, pattern in enumerate(_RULES[category]):
                if pattern.search(entry.content):
                    findings.append(_candidate(category, entry.path, index))
                    break
        total += len(findings)
        if total > MAX_FINDINGS:
            raise InvalidShortcutCorpus("detector output exceeds the finding limit")
        evidence = canonical_digest(
            {
                "category": category,
                "detector_contract_hash": detector_contract_hash(),
                "fingerprints": [item.fingerprint for item in findings],
            }
        )
        results.append(DetectorCategoryResult(category, True, tuple(findings), evidence))
    return tuple(results)
