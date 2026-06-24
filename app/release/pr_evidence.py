"""Pull-request evidence validation (Slice 29, App. B #7 feed / §12.3-12.4) — pure, no I/O.

A ``pull_request_evidence_snapshots`` row is an immutable, observational record of a pull request's
provider facts + §12.4 **presence** (declared/observed, **never adequacy**) + normalized review/identity
facts + **structural-only** separation-of-duties flags. Fail-closed and **non-authorizing**:

- ``provider ∈ {github}``; two-tier ``provenance`` (caller path writes ``caller_supplied_unverified``;
  the connector path writes ``connector_verified``). ``validate_new_pull_request`` rejects the verified
  tier; ``validate_connector_pull_request`` requires it (+ ``observed_at``).
- ``repo_ref`` reuses the Slice-26/28 ``REPO_REF_RE`` slug + ``TOKENISH_RE`` token denylist (single
  source). ``pr_number`` is a positive int.
- ``presence_flags`` record §12.4 **presence**, each labeled ``caller_declared`` | ``connector_observed_template``
  — never prose, never adequacy. ``check_status_summary`` is **observed-only** (nullable) — NOT
  required-check satisfaction. ``traceability_refs`` shape only here; **existence/kind/project is the
  repository's job** (Slice-29 B-29-3).
- ``normalize_approvals`` takes latest-review-per-principal; an approver is one whose **latest** review
  state is ``APPROVED`` (a later CHANGES_REQUESTED / DISMISSED / COMMENTED supersedes it). It does **not**
  claim "required reviewers approved." ``derive_separation_flags`` is **provider-principal equality** —
  NOT a verified UAID-actor-vs-reviewer separation.
"""

from __future__ import annotations

import uuid

from app.release.ci_evidence import REPO_REF_RE, TOKENISH_RE  # single source of truth

PROVIDERS = ("github",)
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)
CONNECTOR_WRITABLE = ("connector_verified",)  # the connector path may write ONLY this

PR_STATES = ("open", "closed", "merged")

# The 10 §12.4 required PR contents (spec :1211-1222).
PRESENCE_ITEMS = (
    "linked_task_or_issue",
    "task_contract",
    "implementation_summary",
    "acceptance_criteria_coverage",
    "tests_added",
    "evidence_links",
    "known_limitations",
    "workarounds_fallbacks",
    "security_notes",
    "rollback_notes",
)
PRESENCE_SOURCES = ("caller_declared", "connector_observed_template")
MAX_MARKER_LEN = 200

CHECK_STATES = ("success", "failure", "pending", "neutral", "error", "unknown")
COMBINED_STATES = ("success", "failure", "pending")

APPROVED_STATE = "APPROVED"

REQUIRED_CREATE_FIELDS = ("provider", "repo_ref", "pr_number", "pr_state", "merged")
_STRING_FIELDS = ("provider", "repo_ref", "pr_state")


class InvalidPullRequestSnapshot(ValueError):
    """Raised when a pull-request snapshot payload is invalid (fail-closed)."""


def _is_int(v) -> bool:
    # bool is an int subclass; exclude it so True/False is never a count / pr_number.
    return isinstance(v, int) and not isinstance(v, bool)


def _is_uuid_str(v) -> bool:
    if not isinstance(v, str):
        return False
    try:
        uuid.UUID(v)
        return True
    except ValueError:
        return False


def validate_presence_flags(obj) -> None:
    """§12.4 presence object: keys ⊆ PRESENCE_ITEMS; each value {present:bool, source∈PRESENCE_SOURCES,
    observed_marker?:bounded-str}. No prose, no adequacy."""
    if not isinstance(obj, dict):
        raise InvalidPullRequestSnapshot("presence_flags must be an object")
    for key, val in obj.items():
        if key not in PRESENCE_ITEMS:
            raise InvalidPullRequestSnapshot(f"unknown §12.4 presence item: {key!r}")
        if not isinstance(val, dict):
            raise InvalidPullRequestSnapshot(f"presence flag {key!r} must be an object (no prose)")
        if not isinstance(val.get("present"), bool):
            raise InvalidPullRequestSnapshot(f"presence flag {key!r} requires a bool 'present'")
        if val.get("source") not in PRESENCE_SOURCES:
            raise InvalidPullRequestSnapshot(
                f"presence flag {key!r} requires source in {PRESENCE_SOURCES}"
            )
        marker = val.get("observed_marker")
        if marker is not None and (
            not isinstance(marker, str) or not (1 <= len(marker) <= MAX_MARKER_LEN)
        ):
            raise InvalidPullRequestSnapshot(
                f"presence flag {key!r} observed_marker must be a bounded string"
            )


def validate_check_status_summary(obj) -> None:
    """Observed-only check summary (B-29-1). NULL = not observed; otherwise an object of non-negative
    integer counts keyed by CHECK_STATES, plus optional combined_state ∈ COMBINED_STATES."""
    if obj is None:
        return
    if not isinstance(obj, dict):
        raise InvalidPullRequestSnapshot("check_status_summary must be null or an object")
    for key, val in obj.items():
        if key == "combined_state":
            if val is not None and val not in COMBINED_STATES:
                raise InvalidPullRequestSnapshot(f"invalid combined_state: {val!r}")
            continue
        if key not in CHECK_STATES:
            raise InvalidPullRequestSnapshot(f"invalid check-state key: {key!r}")
        if not _is_int(val) or val < 0:
            raise InvalidPullRequestSnapshot(
                f"check count for {key!r} must be a non-negative integer"
            )


def validate_traceability_refs_shape(obj) -> None:
    """SHAPE only — UUID-shaped id arrays + a bounded provider_refs object. Existence/kind/project
    validation is the repository's job (B-29-3); a free-form URL is never a trusted ref here."""
    if not isinstance(obj, dict):
        raise InvalidPullRequestSnapshot("traceability_refs must be an object")
    for field in ("release_issue_ids", "acceptance_criterion_ids"):
        if field in obj:
            vals = obj[field]
            if not isinstance(vals, list):
                raise InvalidPullRequestSnapshot(f"{field} must be a list")
            for v in vals:
                if not _is_uuid_str(v):
                    raise InvalidPullRequestSnapshot(f"{field} elements must be UUID strings")
    provider_refs = obj.get("provider_refs")
    if provider_refs is not None and not isinstance(provider_refs, dict):
        raise InvalidPullRequestSnapshot("provider_refs must be an object")


def _validate_pr_shape(record: dict) -> None:
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record:
            raise InvalidPullRequestSnapshot(f"missing required field: {field}")
    for field in _STRING_FIELDS:
        v = record[field]
        if not isinstance(v, str) or not v.strip():
            raise InvalidPullRequestSnapshot(f"empty or non-string field: {field}")
    if record["provider"] not in PROVIDERS:
        raise InvalidPullRequestSnapshot(f"invalid provider: {record['provider']!r}")
    repo_ref = record["repo_ref"]
    if REPO_REF_RE.fullmatch(repo_ref) is None:
        raise InvalidPullRequestSnapshot(f"repo_ref must be an owner/repo slug: {repo_ref!r}")
    if TOKENISH_RE.search(repo_ref) is not None:
        raise InvalidPullRequestSnapshot("repo_ref must not contain a token prefix")
    if not _is_int(record["pr_number"]) or record["pr_number"] <= 0:
        raise InvalidPullRequestSnapshot("pr_number must be a positive integer")
    if record["pr_state"] not in PR_STATES:
        raise InvalidPullRequestSnapshot(f"invalid pr_state: {record['pr_state']!r}")
    if not isinstance(record["merged"], bool):
        raise InvalidPullRequestSnapshot("merged must be a bool")
    if "presence_flags" in record:
        validate_presence_flags(record["presence_flags"])
    if "check_status_summary" in record:
        validate_check_status_summary(record["check_status_summary"])
    if "traceability_refs" in record:
        validate_traceability_refs_shape(record["traceability_refs"])


def validate_new_pull_request(record: dict) -> None:
    """Fail-closed validation of a CALLER (unverified) snapshot."""
    _validate_pr_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidPullRequestSnapshot(
            f"provenance {prov!r} is not writable on the caller path (only caller_supplied_unverified)"
        )


def validate_connector_pull_request(record: dict) -> None:
    """Fail-closed validation of a CONNECTOR (verified) snapshot — provenance must be
    ``connector_verified`` (if present) and ``observed_at`` is required."""
    _validate_pr_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in CONNECTOR_WRITABLE:
        raise InvalidPullRequestSnapshot(
            f"connector provenance must be connector_verified, got {prov!r}"
        )
    if record.get("observed_at") is None:
        raise InvalidPullRequestSnapshot("connector snapshot requires observed_at")


def _ge_submitted(a, b) -> bool:
    """True if review ``a`` is at least as late as ``b``. Missing timestamps ⇒ last input wins."""
    if a is None or b is None:
        return True
    return str(a) >= str(b)


def normalize_approvals(reviews):
    """Return ``(approver_principals, reviewer_principals, approval_count)`` (B-29-5/6).

    Latest review per principal wins (by ``submitted_at``; ties/missing ⇒ input order, last wins). A
    principal is an approver iff their LATEST review state is ``APPROVED`` — a later
    CHANGES_REQUESTED / DISMISSED / COMMENTED supersedes an earlier APPROVED. ``approval_count`` is
    exactly ``len(approver_principals)``. This does NOT claim "required reviewers approved."
    """
    latest: dict = {}
    order: list = []
    for rev in reviews or []:
        principal = rev.get("principal") if isinstance(rev, dict) else None
        if not isinstance(principal, str) or not principal:
            continue
        if principal not in latest:
            order.append(principal)
            latest[principal] = rev
        elif _ge_submitted(rev.get("submitted_at"), latest[principal].get("submitted_at")):
            latest[principal] = rev
    reviewer_principals = [{"principal": p, "latest_state": latest[p].get("state")} for p in order]
    approver_principals = sorted(p for p in order if latest[p].get("state") == APPROVED_STATE)
    return approver_principals, reviewer_principals, len(approver_principals)


def derive_separation_flags(*, author_principal, approver_principals, merger_principal) -> dict:
    """Structural-only separation-of-duties flags (Q3) — **provider-principal equality**, NOT a
    verified UAID-actor-vs-reviewer separation, and NOT §2.2 enforcement. Conservative when the author
    is unknown (all False — a relationship cannot be asserted)."""
    approvers = approver_principals or []
    return {
        "self_approval_observed": bool(author_principal) and author_principal in approvers,
        "self_merge_observed": bool(author_principal)
        and bool(merger_principal)
        and author_principal == merger_principal,
        "review_separation_observed": bool(author_principal)
        and any(a != author_principal for a in approvers),
    }
