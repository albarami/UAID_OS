"""Slice 61a CHECK-fragment agreement and Python-guard refusal probes."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.ecosystem.catalog import (
    CHECK_NAMES,
    LIVE_ADAPTER_STATUSES,
    CatalogValidationError,
    refuse_checker_provenance_for_review,
    require_bounded_text,
    require_content_sha256,
    validate_live_adapter,
    validate_tool_names,
)
from app.ecosystem.catalog_db_checks import (
    ASSET_CHECK_CONSTRAINTS,
    RESULT_CHECK_CONSTRAINTS,
    SPEC_CHECK_CONSTRAINTS,
    VETTING_CHECK_CONSTRAINTS,
)


def test_check_names_match_sql_and_catalog():
    sql = dict(RESULT_CHECK_CONSTRAINTS)["ck_cvcr_check_name"]
    for name in CHECK_NAMES:
        assert f"'{name}'" in sql
    migration = Path("migrations/versions/0060_ecosystem_catalog.py").read_text()
    assert 'revision: str = "0060"' in migration
    assert 'down_revision: str | None = "0059"' in migration
    assert "content_hash" not in migration
    catalog = Path("app/ecosystem/catalog.py").read_text()
    assert "content_hash" not in catalog
    assert "rebinding trigger" in catalog


def test_kind_shape_and_adapter_iff_sql_present():
    named = dict(ASSET_CHECK_CONSTRAINTS)
    assert "asset_kind='connector'" in named["ck_ca_kind_shape"]
    assert "agent_version_id IS NOT NULL" in named["ck_ca_kind_shape"]
    adapter = dict(SPEC_CHECK_CONSTRAINTS)["ck_ccs_adapter_name_iff_shipped"]
    assert "live_adapter_status='absent' AND live_adapter_name IS NULL" in adapter
    assert "live_adapter_status<>'absent' AND live_adapter_name IS NOT NULL" in adapter
    provenance = dict(VETTING_CHECK_CONSTRAINTS)["ck_cvr_kind_provenance"]
    assert "checker_output_admin_recorded" in provenance
    assert "connector_contract_test" in provenance


def test_python_validators_refuse_blank_and_bad_sha():
    try:
        require_bounded_text("asset_key", "   ", 120)
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("blank text must be refused")
    try:
        require_content_sha256("not-a-digest")
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("bad digest must be refused")
    try:
        validate_tool_names([])
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("empty tool scope must be refused")
    try:
        validate_tool_names(["pm.read_issues", "pm.read_issues"])
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("duplicate tools must be refused")
    try:
        validate_live_adapter(status="absent", name="X")
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("absent+name must be refused")
    validate_live_adapter(status="absent", name=None)
    assert "shipped_local_no_network" in LIVE_ADAPTER_STATUSES


def test_record_review_python_guard_refuses_checker_label():
    try:
        refuse_checker_provenance_for_review("checker_output_admin_recorded")
    except CatalogValidationError as exc:
        assert "refuses" in str(exc)
    else:
        raise AssertionError("python review guard must refuse")
    refuse_checker_provenance_for_review("reviewer_asserted_admin_recorded")


@pytest.mark.db
async def test_kind_and_provenance_checks_refuse_forbidden_writes(db_session):
    from tests.ecosystem_catalog_support import execute_sql, register_probe_connector, unique

    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('not_a_kind',:k,'v1','r')",
            k=unique("badkind"),
        )
        await db_session.flush()
    assert "ck_ca_kind_valid" in str(caught.value) or "ck_ca_kind_shape" in str(caught.value)
    await db_session.rollback()
    connector = await register_probe_connector(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'not_a_kind','reviewer_asserted_admin_recorded','passed','x')",
            a=connector.id,
        )
        await db_session.flush()
    assert "ck_cvr_kind_valid" in str(caught.value)
    await db_session.rollback()
    connector = await register_probe_connector(db_session)
    await db_session.execute(
        text(
            "ALTER TABLE catalog_vetting_records "
            "DROP CONSTRAINT ck_catalog_vetting_records_ck_cvr_kind_provenance"
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','not_a_provenance','passed','x')",
            a=connector.id,
        )
        await db_session.flush()
    assert "ck_cvr_provenance_valid" in str(caught.value)
