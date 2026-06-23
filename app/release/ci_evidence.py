"""Source-control / CI branch-protection evidence validation (Slice 26, spec App. B #3 / §26.3) —
pure, no I/O.

A ``branch_protection_snapshots`` row is an immutable, observational record of a repo's
branch-protection *configuration* (the A5 gate-#3 evidence class). Fail-closed and
**non-authorizing**:

- ``provider ∈ {github}`` (GitHub-first; the schema is provider-shaped for the real connector, Slice 28).
- ``provenance`` is a two-tier axis: ``caller_supplied_unverified`` (the ONLY value Slice 26 may write —
  an unverified assertion) and ``connector_verified`` (schema-reserved, **unwritable** until a real
  connector exists). The repository stamps the unverified value; the DB guard enforces it.
- ``repo_ref`` must be a GitHub-first ``owner/repo`` slug (``REPO_REF_RE``) **and** must NOT contain a
  GitHub token prefix (``TOKENISH_RE``) — rejects URLs, credentialed URLs, SSH URLs, query strings,
  fragments, whitespace, multi-slash, and token-looking repo names (e.g. ``owner/ghp_…``).
- ``required_status_checks`` is a list of bounded non-empty strings; ``required_status_check_count`` is
  **derived** from it (never caller-trusted).

These snapshots never enable go-live and never let gate #3 PASS — Slice 26 implements no PASS path
(that lands with the real connector, Slice 28).
"""

from __future__ import annotations

import re

PROVIDERS = ("github",)
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)

# GitHub-first owner/repo slug SHAPE (anchored): rejects URLs / credentialed URLs / SSH URLs /
# query strings / fragments / whitespace / control chars / multi-slash paths.
REPO_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
# Token-prefix denylist on the repo segment: rejects GitHub token-looking repo names the slug shape
# alone would accept (``owner/ghp_…``). Case-insensitive.
TOKENISH_RE = re.compile(r"/(gh[opusr]_|github_pat_)", re.IGNORECASE)

MAX_CHECK_NAME_LEN = 200

REQUIRED_CREATE_FIELDS = (
    "provider",
    "repo_ref",
    "branch",
    "protection_enabled",
    "required_pull_request_reviews",
    "enforce_admins",
)
_STRING_FIELDS = ("provider", "repo_ref", "branch")
_BOOL_FIELDS = ("protection_enabled", "required_pull_request_reviews", "enforce_admins")


class InvalidBranchProtectionSnapshot(ValueError):
    """Raised when a branch-protection snapshot payload is invalid (fail-closed)."""


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_required_status_checks(checks) -> None:
    """Fail-closed: a list of non-empty strings each ≤ ``MAX_CHECK_NAME_LEN`` chars."""
    if not isinstance(checks, list):
        raise InvalidBranchProtectionSnapshot("required_status_checks must be a list")
    for c in checks:
        if not isinstance(c, str) or not (1 <= len(c) <= MAX_CHECK_NAME_LEN):
            raise InvalidBranchProtectionSnapshot(
                f"required_status_checks elements must be 1..{MAX_CHECK_NAME_LEN}-char strings"
            )


def derived_check_count(checks) -> int:
    """Server-derived count — never caller-trusted."""
    return len(checks or [])


def validate_new_snapshot(record: dict) -> None:
    """Fail-closed validation of a new branch-protection snapshot."""
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record:
            raise InvalidBranchProtectionSnapshot(f"missing required field: {field}")
    for field in _STRING_FIELDS:
        if _empty(record[field]) or not isinstance(record[field], str):
            raise InvalidBranchProtectionSnapshot(f"empty or non-string required field: {field}")
    if record["provider"] not in PROVIDERS:
        raise InvalidBranchProtectionSnapshot(f"invalid provider: {record['provider']!r}")
    repo_ref = record["repo_ref"]
    if REPO_REF_RE.fullmatch(repo_ref) is None:
        raise InvalidBranchProtectionSnapshot(f"repo_ref must be an owner/repo slug: {repo_ref!r}")
    if TOKENISH_RE.search(repo_ref) is not None:
        raise InvalidBranchProtectionSnapshot(
            "repo_ref must not contain a token prefix (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_)"
        )
    for field in _BOOL_FIELDS:
        # bool is an int subclass; isinstance(..., bool) rejects 0/1 and "true" alike.
        if not isinstance(record[field], bool):
            raise InvalidBranchProtectionSnapshot(f"{field} must be a bool")
    validate_required_status_checks(record.get("required_status_checks", []))
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidBranchProtectionSnapshot(
            f"provenance {prov!r} is not writable this slice (only caller_supplied_unverified)"
        )
