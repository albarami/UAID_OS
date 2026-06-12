"""Canonical intake-category model (Slice 15, §4.2/§4.3/Appendix A) — pure, no DB, no LLM.

Anchors the readiness/go-live category universe to the **authoritative §4.2 26-file
intake package** (file stems) plus the Appendix-A "production authority is explicit"
condition, and partitions it into three disjoint sets:

- ``SPINE_CATEGORIES`` — already modeled as ``intake_artifacts`` kinds (Slice 11).
- ``GATED_ENGINE_CATEGORIES`` — evaluated later from policy/approval/budget/authority
  engine state (Slices 3/4/7 + the policy matrix); **not** self-declarable here and
  **not** treated as verified-complete.
- ``DECLARABLE_INTAKE_CATEGORIES`` — the categories this slice's ``intake_categories``
  table may declare from documents / human-provided evidence.

This module models INPUTS ONLY. It does not compute or claim R3/R4/R5, and it never
stores secret values — the ``secrets_and_credentials_manifest`` category accepts
reference metadata only.
"""

from __future__ import annotations

import uuid

# §4.2 file stems (00..25), authoritative. File 14 covers architecture AND stack.
SPINE_CATEGORIES = (
    "functional_requirements",  # 06 -> intake_artifacts kind=requirement
    "acceptance_criteria",  # 08 -> kind=acceptance_criterion
    "test_oracles",  # 09 -> kind=test_oracle
)

GATED_ENGINE_CATEGORIES = (
    "autonomy_policy",  # 19 -> Slice 3 autonomy_policies (not verified-complete)
    "human_approval_policy",  # 20 -> Slice 4 approvals (not verified-complete)
    "cost_and_resource_policy",  # 21 -> Slice 7 budgets (NOT verified human approvals)
    "production_authority",  # Appendix A condition -> policy matrix + approval (deferred)
)

DECLARABLE_INTAKE_CATEGORIES = (
    "project_manifest",  # 00
    "product_brief",  # 01
    "business_objectives",  # 02
    "scope_and_boundaries",  # 03
    "users_roles_permissions",  # 04
    "user_journeys_and_workflows",  # 05
    "non_functional_requirements",  # 07
    "domain_pack",  # 10
    "data_model_and_contracts",  # 11
    "integrations_and_external_systems",  # 12
    "existing_assets_and_repositories",  # 13
    "architecture_and_technology_constraints",  # 14 (architecture + stack)
    "security_privacy_compliance",  # 15
    "environments_and_deployment_targets",  # 16
    "secrets_and_credentials_manifest",  # 17 (reference-only)
    "tool_access_manifest",  # 18 (declared; access-approval gated later)
    "operations_observability_support",  # 22
    "go_live_checklist",  # 23 (declared; go-live gate gated later)
    "risk_register_and_assurance_requirements",  # 24
    "prior_decisions_and_architecture_log",  # 25
)

# Full universe = 26 §4.2 file categories + the Appendix-A production_authority condition.
CANONICAL_READINESS_CATEGORY_UNIVERSE = tuple(
    sorted(set(SPINE_CATEGORIES) | set(GATED_ENGINE_CATEGORIES) | set(DECLARABLE_INTAKE_CATEGORIES))
)

SECRET_CATEGORY = "secrets_and_credentials_manifest"
_DECLARABLE_SET = frozenset(DECLARABLE_INTAKE_CATEGORIES)
# Keys that strongly indicate an inline credential — rejected anywhere in category data.
_SECRET_DENYLIST_KEYS = frozenset(
    {"value", "secret", "password", "passwd", "token", "api_key", "apikey",
     "credential", "credentials", "private_key", "privatekey"}
)
# For the secrets category, only reference metadata is permitted.
_SECRET_ALLOWED_KEYS = frozenset({"manager", "reference_name", "references"})
_MAX_REF_LEN = 256


class InvalidCategory(ValueError):
    """Raised when a category is not a declarable §4.2 intake category."""


class InvalidCategoryData(ValueError):
    """Raised when category data is malformed or appears to contain a secret value."""


class InvalidProvenance(ValueError):
    """Raised when a declaration lacks exactly one valid source (document XOR origin)."""


def validate_declarable_category(category: str) -> None:
    if category not in _DECLARABLE_SET:
        raise InvalidCategory(f"{category!r} is not a declarable intake category")


def validate_source(
    *, source_document_id: uuid.UUID | None, locator: str | None, origin: str | None
) -> None:
    """Fail-closed XOR mirroring the DB CHECK exactly. Exactly one shape is valid:

    - document-backed: ``source_document_id`` set, non-empty ``locator``, ``origin`` None;
    - origin-backed: ``source_document_id`` None, ``locator`` None, non-empty ``origin``.

    Anything else (neither, both, origin+locator, doc+origin including ``""``, blank
    locator/origin) is rejected.
    """
    has_locator = isinstance(locator, str) and locator.strip() != ""
    has_origin = isinstance(origin, str) and origin.strip() != ""
    if source_document_id is not None:
        # document-backed
        if origin is not None:
            raise InvalidProvenance("a document-backed source must not set origin")
        if not has_locator:
            raise InvalidProvenance("a document-backed source requires a non-empty locator")
    else:
        # origin-backed
        if locator is not None:
            raise InvalidProvenance("an origin-backed source must not set locator")
        if not has_origin:
            raise InvalidProvenance("a declaration requires a source (document or origin)")


def _reject_secretish_keys(obj) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _SECRET_DENYLIST_KEYS:
                raise InvalidCategoryData(f"data must not contain a {k!r} value (no secrets)")
            _reject_secretish_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _reject_secretish_keys(item)


def validate_category_data(category: str, data: dict | None) -> None:
    """Reject secret-looking data anywhere; for the secrets category, allow reference
    metadata only (best-effort, convention-enforced — not a cryptographic guarantee)."""
    if data is None:
        return
    if not isinstance(data, dict):
        raise InvalidCategoryData("data must be a JSON object")
    # Defense-in-depth across all categories: no credential-looking keys.
    _reject_secretish_keys(data)
    if category != SECRET_CATEGORY:
        return
    # Secrets: reference metadata only.
    extra = set(data) - _SECRET_ALLOWED_KEYS
    if extra:
        raise InvalidCategoryData(f"secrets data allows only {_SECRET_ALLOWED_KEYS}; got {extra}")
    refs = data.get("references", [])
    if "references" in data and not isinstance(refs, list):
        raise InvalidCategoryData("secrets 'references' must be a list")
    entries = refs if "references" in data else [data]
    for entry in entries:
        if not isinstance(entry, dict):
            raise InvalidCategoryData("secrets reference must be an object")
        if set(entry) - {"manager", "reference_name"}:
            raise InvalidCategoryData("secrets reference allows only {manager, reference_name}")
        for val in entry.values():
            if not isinstance(val, str) or len(val) > _MAX_REF_LEN:
                raise InvalidCategoryData("secrets reference values must be short strings")
