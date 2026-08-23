"""Slice 61b review-round probes: fresh listing vetting, incomplete-identity mismatch."""

from __future__ import annotations

import pytest

from app.ecosystem.catalog import CHECK_NAMES
from app.ecosystem.catalog_declared import (
    ACTOR_BLUEPRINT_REVIEWER,
    ACTOR_CONTRACT_CHECKER,
    DECLARED_CONNECTORS,
    DECLARED_VERSION_LABEL,
)
from app.ecosystem.catalog_populate import CatalogPopulateError, populate_declared_catalog
from app.ecosystem.contract_test import run_connector_contract_test
from app.repositories.catalog_admin import register_blueprint_version, register_connector
from app.repositories.catalog_reads import get_by_key, latest_listing, latest_vetting
from tests.ecosystem_catalog_support import (
    add_probe_blueprint,
    add_probe_version,
    execute_sql,
    unique,
)


async def _sql_passing_connector_vetting(session, asset_id, reviewer: str):
    record_id = (
        await execute_sql(
            session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','checker_output_admin_recorded',"
            "'passed',:r) RETURNING id",
            a=asset_id,
            r=reviewer,
        )
    ).scalar_one()
    for name in CHECK_NAMES:
        await execute_sql(
            session,
            "INSERT INTO catalog_vetting_check_results "
            "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)",
            id=record_id,
            n=name,
        )
    return record_id


async def _register_declared_ci(session):
    declared = DECLARED_CONNECTORS["ci_evidence"]
    return await register_connector(
        session,
        asset_key="ci_evidence",
        version_label=DECLARED_VERSION_LABEL,
        registered_by="forger",
        protocol_module=declared.protocol_module,
        protocol_name=declared.protocol_name,
        fake_name=declared.fake_name,
        service_module=declared.service_module,
        live_adapter_status=declared.live_adapter_status,
        live_adapter_name=declared.live_adapter_name,
        tool_names=list(declared.tool_names),
    )


@pytest.mark.db
async def test_listing_cites_fresh_contract_test_not_sql_vetting(db_session, monkeypatch):
    asset = await _register_declared_ci(db_session)
    sql_id = await _sql_passing_connector_vetting(db_session, asset.id, "sql_forger")
    assert await latest_listing(db_session, asset.id) is None
    called: list[str] = []
    original = run_connector_contract_test

    def tracked(spec):
        called.append(spec.service_module)
        return original(spec)

    monkeypatch.setattr("app.repositories.catalog_admin.run_connector_contract_test", tracked)
    await populate_declared_catalog(db_session)
    listing = await latest_listing(db_session, asset.id)
    assert listing is not None and listing.listing_state == "listed"
    assert listing.vetting_record_id != sql_id
    cited = await latest_vetting(db_session, asset.id)
    assert cited is not None
    assert cited.id == listing.vetting_record_id
    assert cited.reviewer == ACTOR_CONTRACT_CHECKER
    assert "app.release.ci_evidence_service" in called


@pytest.mark.db
async def test_blueprint_listing_cites_fresh_review_not_sql_vetting(db_session):
    key = unique("bp")
    version = await add_probe_version(
        db_session, (await add_probe_blueprint(db_session, key)).id, "v1", "sql"
    )
    asset = await register_blueprint_version(
        db_session,
        asset_key=key,
        version_label="v1",
        registered_by="forger",
        agent_version_id=version.id,
    )
    sql_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'blueprint_security_review','reviewer_asserted_admin_recorded',"
            "'passed','sql_forger') RETURNING id",
            a=asset.id,
        )
    ).scalar_one()
    await populate_declared_catalog(db_session)
    listing = await latest_listing(db_session, asset.id)
    assert listing is not None
    assert listing.vetting_record_id != sql_id
    cited = await latest_vetting(db_session, asset.id)
    assert cited is not None and cited.id == listing.vetting_record_id
    assert cited.reviewer == ACTOR_BLUEPRINT_REVIEWER


@pytest.mark.db
async def test_missing_spec_is_bounded_mismatch(db_session):
    await execute_sql(
        db_session,
        "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
        "VALUES ('connector','ci_evidence','v1','forger')",
    )
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert "declared_identity_mismatch:ci_evidence" in str(caught.value)
    asset = await get_by_key(db_session, "connector", "ci_evidence", "v1")
    assert asset is not None
    assert await latest_listing(db_session, asset.id) is None


@pytest.mark.db
async def test_empty_scope_is_bounded_mismatch(db_session):
    declared = DECLARED_CONNECTORS["ci_evidence"]
    asset_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector','ci_evidence','v1','forger') RETURNING id",
        )
    ).scalar_one()
    await execute_sql(
        db_session,
        "INSERT INTO connector_catalog_specs "
        "(asset_id,asset_kind,protocol_module,protocol_name,fake_name,"
        "service_module,live_adapter_status,live_adapter_name) VALUES "
        "(:a,'connector',:pm,:pn,:fn,:sm,:st,:an)",
        a=asset_id,
        pm=declared.protocol_module,
        pn=declared.protocol_name,
        fn=declared.fake_name,
        sm=declared.service_module,
        st=declared.live_adapter_status,
        an=declared.live_adapter_name,
    )
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert "declared_identity_mismatch:ci_evidence" in str(caught.value)
    assert await latest_listing(db_session, asset_id) is None
