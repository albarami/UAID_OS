"""Shared Postgres CHECK fragments for Slice-61a catalog tables.

NAME, SQL tuples consumed by the ORM and migration ``0060`` so vocabulary
cannot drift. A passing CHECK is not a performed review or a checker run.
"""

from __future__ import annotations

from app.ecosystem.catalog import CHECK_NAMES

_WS = r"E' \t\n\r\x0b\x0c'"


def _nonblank(column: str, max_len: int) -> str:
    return (
        f"char_length(btrim({column}, {_WS})) BETWEEN 1 AND {max_len} "
        f"AND char_length({column}) BETWEEN 1 AND {max_len}"
    )


ASSET_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "ck_ca_kind_valid",
        "asset_kind IN ('connector','agent_blueprint','reference_intake')",
    ),
    ("ck_ca_asset_key", _nonblank("asset_key", 120)),
    ("ck_ca_version_label", _nonblank("version_label", 64)),
    ("ck_ca_registered_by", _nonblank("registered_by", 200)),
    (
        "ck_ca_kind_shape",
        "("
        "asset_kind='connector' AND agent_version_id IS NULL AND domain_label IS NULL "
        "AND content_sha256 IS NULL AND source_ref IS NULL"
        ") OR ("
        "asset_kind='agent_blueprint' AND agent_version_id IS NOT NULL "
        "AND domain_label IS NULL AND content_sha256 IS NULL AND source_ref IS NULL"
        ") OR ("
        "asset_kind='reference_intake' AND agent_version_id IS NULL "
        "AND domain_label IS NOT NULL AND content_sha256 IS NOT NULL "
        "AND source_ref IS NOT NULL"
        ")",
    ),
    (
        "ck_ca_content_sha256",
        "content_sha256 IS NULL OR content_sha256 ~ '^sha256:[0-9a-f]{64}$'",
    ),
    (
        "ck_ca_domain_label",
        f"domain_label IS NULL OR ({_nonblank('domain_label', 120)})",
    ),
    (
        "ck_ca_source_ref",
        f"source_ref IS NULL OR ({_nonblank('source_ref', 500)})",
    ),
)

SPEC_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_ccs_asset_kind_connector", "asset_kind = 'connector'"),
    ("ck_ccs_protocol_module", _nonblank("protocol_module", 200)),
    ("ck_ccs_protocol_name", _nonblank("protocol_name", 200)),
    ("ck_ccs_fake_name", _nonblank("fake_name", 200)),
    ("ck_ccs_service_module", _nonblank("service_module", 200)),
    (
        "ck_ccs_adapter_status",
        "live_adapter_status IN ('absent',"
        "'shipped_mock_tested_no_live_provider',"
        "'shipped_local_no_network')",
    ),
    (
        "ck_ccs_adapter_name_iff_shipped",
        "(live_adapter_status='absent' AND live_adapter_name IS NULL) OR "
        "(live_adapter_status<>'absent' AND live_adapter_name IS NOT NULL)",
    ),
    (
        "ck_ccs_adapter_name",
        f"live_adapter_name IS NULL OR ({_nonblank('live_adapter_name', 200)})",
    ),
)

SCOPE_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_ccts_asset_kind_connector", "asset_kind = 'connector'"),
    ("ck_ccts_tool_name", _nonblank("tool_name", 120)),
)

VETTING_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "ck_cvr_kind_valid",
        "vetting_kind IN ('connector_contract_test',"
        "'blueprint_security_review',"
        "'reference_intake_constraint_attestation')",
    ),
    (
        "ck_cvr_provenance_valid",
        "provenance IN ('checker_output_admin_recorded','reviewer_asserted_admin_recorded')",
    ),
    ("ck_cvr_outcome_valid", "outcome IN ('passed','failed')"),
    ("ck_cvr_reviewer", _nonblank("reviewer", 200)),
    (
        "ck_cvr_kind_provenance",
        "(provenance='checker_output_admin_recorded' AND "
        "vetting_kind='connector_contract_test') OR "
        "(provenance='reviewer_asserted_admin_recorded' AND "
        "vetting_kind<>'connector_contract_test')",
    ),
)

CHECK_NAME_SQL = ",".join(f"'{name}'" for name in CHECK_NAMES)

RESULT_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_cvcr_check_name", f"check_name IN ({CHECK_NAME_SQL})"),
)

LISTING_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_cl_state_valid", "listing_state IN ('listed','delisted')"),
    ("ck_cl_listed_by", _nonblank("listed_by", 200)),
    (
        "ck_cl_delisted_reason",
        f"delisted_reason IS NULL OR ({_nonblank('delisted_reason', 500)})",
    ),
)

ADOPTION_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_tca_adopted_by", _nonblank("adopted_by", 200)),
)
