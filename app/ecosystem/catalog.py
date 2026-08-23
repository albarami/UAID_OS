"""Pure catalog vocabulary, maps, and validators (Slice 61a).

Identity is the row. There is no content hash, no canonical JSON, and no
rebinding trigger. Bounds here are mirrored by CHECK constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

ASSET_KINDS: tuple[str, ...] = ("connector", "agent_blueprint", "reference_intake")
VETTING_KINDS: tuple[str, ...] = (
    "connector_contract_test",
    "blueprint_security_review",
    "reference_intake_constraint_attestation",
)
PROVENANCES: tuple[str, ...] = (
    "checker_output_admin_recorded",
    "reviewer_asserted_admin_recorded",
)
OUTCOMES: tuple[str, ...] = ("passed", "failed")
CHECK_NAMES: tuple[str, ...] = (
    "tool_scope_nonempty",
    "tool_scope_resolves",
    "protocol_resolves",
    "fake_conforms",
    "live_adapter_symbol",
)
LISTING_STATES: tuple[str, ...] = ("listed", "delisted")
LIVE_ADAPTER_STATUSES: tuple[str, ...] = (
    "absent",
    "shipped_mock_tested_no_live_provider",
    "shipped_local_no_network",
)

REQUIRED_VETTING_KIND: dict[str, str] = {
    "connector": "connector_contract_test",
    "agent_blueprint": "blueprint_security_review",
    "reference_intake": "reference_intake_constraint_attestation",
}
REQUIRED_PROVENANCE: dict[str, str] = {
    "connector_contract_test": "checker_output_admin_recorded",
    "blueprint_security_review": "reviewer_asserted_admin_recorded",
    "reference_intake_constraint_attestation": "reviewer_asserted_admin_recorded",
}

ASSET_KEY_MAX = 120
VERSION_LABEL_MAX = 64
REGISTERED_BY_MAX = 200
DOMAIN_LABEL_MAX = 120
SOURCE_REF_MAX = 500
SYMBOL_MAX = 200
TOOL_NAME_MAX = 120
REVIEWER_MAX = 200
LISTED_BY_MAX = 200
DELISTED_REASON_MAX = 500
ADOPTED_BY_MAX = 200

CONTENT_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

LISTING_VETTING_ASSET_MISMATCH = "listing_vetting_asset_mismatch"
LISTING_VETTING_NOT_PASSED = "listing_vetting_not_passed"
LISTING_VETTING_KIND_MISMATCH = "listing_vetting_kind_mismatch"
LISTING_VETTING_PROVENANCE_MISMATCH = "listing_vetting_provenance_mismatch"
LISTING_BLUEPRINT_SELF_REVIEW = "listing_blueprint_self_review"
LISTING_MUST_INSERT_LISTED = "listing_must_insert_listed"
LISTING_CONNECTOR_CHILDREN_REQUIRED = "listing_connector_children_required"
CONNECTOR_CHILDREN_FROZEN = "connector_children_frozen"
CONNECTOR_CHILDREN_REQUIRED = "connector_children_required"
ADOPTION_LISTING_DELISTED = "adoption_listing_delisted"
DELIST_ONLY_LISTED_TO_DELISTED = "delist_only_listed_to_delisted"
DELIST_IDENTITY_IMMUTABLE = "delist_identity_immutable"
DELIST_SAME_STATE_REFUSED = "delist_same_state_refused"
DELIST_AT_REQUIRED = "delist_at_required_when_delisted"
CHECKER_REQUIRES_FIVE_RESULTS = "checker_record_requires_exactly_five_results"
CHECKER_OUTCOME_MUST_MATCH = "checker_outcome_must_match_results"
ASSERTION_FORBIDS_RESULTS = "assertion_record_forbids_result_rows"


class CatalogError(Exception):
    """Base catalog validation / guard error."""


class CatalogValidationError(CatalogError):
    """Caller input failed a fail-closed bound or vocabulary check."""


def required_vetting_kind(asset_kind: str) -> str:
    """Return the vetting kind required for ``asset_kind``. No default branch."""
    return REQUIRED_VETTING_KIND[asset_kind]


def required_provenance(vetting_kind: str) -> str:
    """Return the provenance required for ``vetting_kind``. No default branch."""
    return REQUIRED_PROVENANCE[vetting_kind]


def require_bounded_text(field: str, value: object, max_len: int) -> str:
    """Require a non-blank string whose stripped length is in ``1..max_len``."""
    if not isinstance(value, str):
        raise CatalogValidationError(f"{field} must be a non-blank string")
    stripped = value.strip()
    if not stripped or len(stripped) > max_len:
        raise CatalogValidationError(f"{field} must be non-blank and at most {max_len} chars")
    return stripped


def require_member(field: str, value: object, allowed: tuple[str, ...]) -> str:
    """Require ``value`` to be one of ``allowed``."""
    if not isinstance(value, str) or value not in allowed:
        raise CatalogValidationError(f"{field} must be one of {allowed}")
    return value


def require_content_sha256(value: object) -> str:
    """Require registrar-supplied ``sha256:<64 hex>`` drift metadata."""
    if not isinstance(value, str) or CONTENT_SHA256_RE.match(value) is None:
        raise CatalogValidationError("content_sha256 must match sha256:<64 lowercase hex>")
    return value


def validate_tool_names(tool_names: object) -> tuple[str, ...]:
    """Bound, strip, and de-duplicate declared tool names. Fail closed."""
    if not isinstance(tool_names, (list, tuple)):
        raise CatalogValidationError("tool_names must be a sequence")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tool_names:
        name = require_bounded_text("tool_name", raw, TOOL_NAME_MAX)
        if name in seen:
            raise CatalogValidationError("tool_names must be distinct")
        seen.add(name)
        cleaned.append(name)
    if not cleaned:
        raise CatalogValidationError("tool_names must be non-empty")
    return tuple(cleaned)


def validate_live_adapter(*, status: str, name: str | None) -> None:
    """Enforce the live-adapter iff: absent ⇔ name is NULL."""
    require_member("live_adapter_status", status, LIVE_ADAPTER_STATUSES)
    if status == "absent":
        if name is not None:
            raise CatalogValidationError("absent live adapter must not carry a name")
        return
    require_bounded_text("live_adapter_name", name, SYMBOL_MAX)


@dataclass(frozen=True)
class ConnectorSpecInput:
    """Declared connector identity consumed by the contract checker."""

    protocol_module: str
    protocol_name: str
    fake_name: str
    service_module: str
    live_adapter_status: str
    live_adapter_name: str | None
    tool_names: tuple[str, ...]


def maps_are_exhaustive() -> bool:
    """True when required-kind/provenance maps cover every enum value."""
    return set(REQUIRED_VETTING_KIND) == set(ASSET_KINDS) and set(REQUIRED_PROVENANCE) == set(
        VETTING_KINDS
    )


def refuse_checker_provenance_for_review(provenance: str) -> None:
    """``record_review`` must never stamp checker output."""
    if provenance == "checker_output_admin_recorded":
        raise CatalogValidationError("record_review refuses checker_output_admin_recorded")


def audit_safe_adoption_payload(
    *,
    listing_id: str,
    asset_kind: str,
    asset_key: str,
    version_label: str,
) -> Mapping[str, str]:
    """Safe-metadata adoption audit payload. Never source_ref or domain_label."""
    return {
        "listing_id": listing_id,
        "asset_kind": asset_kind,
        "asset_key": asset_key,
        "version_label": version_label,
    }
