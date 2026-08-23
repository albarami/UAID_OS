"""Slice 61a DB probes: identity, freeze, vetting shape, listing, adoption, trust."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import (
    ASSERTION_FORBIDS_RESULTS,
    CHECK_NAMES,
    CHECKER_OUTCOME_MUST_MATCH,
    CHECKER_REQUIRES_FIVE_RESULTS,
    CONNECTOR_CHILDREN_FROZEN,
    CONNECTOR_CHILDREN_REQUIRED,
    LISTING_VETTING_ASSET_MISMATCH,
)
from app.repositories.catalog_admin import children_complete, record_review
from app.repositories.catalog_adoptions import CatalogAdoptionRepository
from app.tenancy import TenantContext
from tests.ecosystem_catalog_support import (
    execute_sql,
    register_listed_blueprint,
    register_probe_connector,
    register_vet_list_pm,
    seed_project,
    unique,
)


def _as_error(exc: BaseException) -> str:
    return str(exc)


def _is_guard(exc: BaseException, fragment: str) -> bool:
    return fragment in _as_error(exc)


@pytest.mark.db
async def test_d12_asset_update_blocked_as_admin(db_session):
    asset = await register_probe_connector(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await db_session.execute(
            text("UPDATE catalog_assets SET asset_key='mutated' WHERE id=:i"),
            {"i": asset.id},
        )
        await db_session.flush()
    assert "append-only" in _as_error(caught.value)


@pytest.mark.db
async def test_d13_append_only_tables_block_update_as_admin(db_session):
    asset, vetting, _listing = await register_vet_list_pm(db_session)
    updates = {
        "connector_catalog_specs": "protocol_name='X'",
        "connector_catalog_tool_scope": "tool_name='x'",
        "catalog_vetting_records": "outcome='failed'",
        "catalog_vetting_check_results": "passed=false",
    }
    ids = {
        "connector_catalog_specs": (
            await execute_sql(
                db_session, "SELECT id FROM connector_catalog_specs WHERE asset_id=:i", i=asset.id
            )
        ).scalar_one(),
        "connector_catalog_tool_scope": (
            await execute_sql(
                db_session,
                "SELECT id FROM connector_catalog_tool_scope WHERE asset_id=:i",
                i=asset.id,
            )
        ).scalar_one(),
        "catalog_vetting_records": vetting.id,
        "catalog_vetting_check_results": (
            await execute_sql(
                db_session,
                "SELECT id FROM catalog_vetting_check_results WHERE vetting_record_id=:i LIMIT 1",
                i=vetting.id,
            )
        ).scalar_one(),
    }
    for table, assignment in updates.items():
        with pytest.raises((IntegrityError, DBAPIError)) as caught:
            await db_session.execute(
                text(f"UPDATE {table} SET {assignment} WHERE id=:i"), {"i": ids[table]}
            )
            await db_session.flush()
        assert "append-only" in _as_error(caught.value)
        await db_session.rollback()
        asset, vetting, _listing = await register_vet_list_pm(db_session)
        ids = {
            "connector_catalog_specs": (
                await execute_sql(
                    db_session,
                    "SELECT id FROM connector_catalog_specs WHERE asset_id=:i",
                    i=asset.id,
                )
            ).scalar_one(),
            "connector_catalog_tool_scope": (
                await execute_sql(
                    db_session,
                    "SELECT id FROM connector_catalog_tool_scope WHERE asset_id=:i",
                    i=asset.id,
                )
            ).scalar_one(),
            "catalog_vetting_records": vetting.id,
            "catalog_vetting_check_results": (
                await execute_sql(
                    db_session,
                    "SELECT id FROM catalog_vetting_check_results "
                    "WHERE vetting_record_id=:i LIMIT 1",
                    i=vetting.id,
                )
            ).scalar_one(),
        }


@pytest.mark.db
async def test_d13_adoption_update_blocked(db_session):
    seeded = await seed_project(db_session)
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    adoption = await CatalogAdoptionRepository(db_session, TenantContext(seeded["tenant"])).adopt(
        seeded["project"], listing.id, adopted_by="adopter"
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await db_session.execute(
            text("UPDATE tenant_catalog_adoptions SET adopted_by='x' WHERE id=:i"),
            {"i": adoption.id},
        )
        await db_session.flush()
    assert "append-only" in _as_error(caught.value)


@pytest.mark.db
async def test_d14_unique_version_refused(db_session):
    asset = await register_probe_connector(db_session, asset_key="same-key", version_label="v1")
    with pytest.raises((IntegrityError, DBAPIError)):
        await register_probe_connector(db_session, asset_key=asset.asset_key, version_label="v1")
        await db_session.flush()


@pytest.mark.db
async def test_d15_record_review_refuses_checker_stamp_no_row(db_session):
    from app.ecosystem.catalog import CatalogValidationError

    asset, _vetting, _listing = await register_listed_blueprint(db_session)
    before = (
        await execute_sql(db_session, "SELECT count(*) FROM catalog_vetting_records")
    ).scalar_one()
    with pytest.raises(CatalogValidationError):
        await record_review(
            db_session,
            asset_id=asset.id,
            vetting_kind="blueprint_security_review",
            provenance="checker_output_admin_recorded",
            outcome="passed",
            reviewer="other",
        )
    after = (
        await execute_sql(db_session, "SELECT count(*) FROM catalog_vetting_records")
    ).scalar_one()
    assert after == before


@pytest.mark.db
async def test_d16_four_results_refused_by_parent_trigger(admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        asset_id = asset.id
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalog_vetting_records "
                    "(asset_id,vetting_kind,provenance,outcome,reviewer) "
                    "VALUES (:a,'connector_contract_test',"
                    "'checker_output_admin_recorded','passed','r')"
                ),
                {"a": asset_id},
            )
    assert _is_guard(caught.value, CHECKER_REQUIRES_FIVE_RESULTS)


@pytest.mark.db
async def test_d17_passed_outcome_with_false_result_refused(admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        asset_id = asset.id
    record_id = uuid.uuid4()
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalog_vetting_records "
                    "(id,asset_id,vetting_kind,provenance,outcome,reviewer) "
                    "VALUES (:id,:a,'connector_contract_test',"
                    "'checker_output_admin_recorded','passed','r')"
                ),
                {"id": record_id, "a": asset_id},
            )
            for i, name in enumerate(CHECK_NAMES):
                await conn.execute(
                    text(
                        "INSERT INTO catalog_vetting_check_results "
                        "(vetting_record_id,check_name,passed) VALUES (:id,:n,:p)"
                    ),
                    {"id": record_id, "n": name, "p": i != 0},
                )
    assert _is_guard(caught.value, CHECKER_OUTCOME_MUST_MATCH)


@pytest.mark.db
async def test_d18_late_sixth_result_refused_by_child_trigger(admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        _asset, vetting, _listing = await register_vet_list_pm(session)
        await session.commit()
        vetting_id = vetting.id
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE catalog_vetting_check_results DROP CONSTRAINT uq_cvcr_record_name"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO catalog_vetting_check_results "
                    "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)"
                ),
                {"id": vetting_id, "n": CHECK_NAMES[0]},
            )
    assert _is_guard(caught.value, CHECKER_REQUIRES_FIVE_RESULTS)


@pytest.mark.db
async def test_d19_duplicate_check_name_refused(db_session):
    asset, vetting, _listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)):
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_check_results "
            "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)",
            id=vetting.id,
            n=CHECK_NAMES[0],
        )
        await db_session.flush()


@pytest.mark.db
async def test_d20_assertion_result_row_and_kind_provenance_refused(admin_engine, db_session):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        _asset, vetting, _listing = await register_listed_blueprint(session)
        await session.commit()
        vetting_id = vetting.id
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO catalog_vetting_check_results "
                    "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)"
                ),
                {"id": vetting_id, "n": CHECK_NAMES[0]},
            )
    assert _is_guard(caught.value, ASSERTION_FORBIDS_RESULTS)
    asset2, _v, _l = await register_listed_blueprint(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'blueprint_security_review','checker_output_admin_recorded','passed','x')",
            a=asset2.id,
        )
        await db_session.flush()
    assert "ck_cvr_kind_provenance" in _as_error(caught.value)
    await db_session.rollback()
    connector = await register_probe_connector(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','reviewer_asserted_admin_recorded','passed','x')",
            a=connector.id,
        )
        await db_session.flush()
    assert "ck_cvr_kind_provenance" in _as_error(caught.value)


@pytest.mark.db
async def test_d21_old_vetting_cannot_list_new_version(db_session):
    asset, vetting, _listing = await register_vet_list_pm(db_session)
    new_asset = await register_probe_connector(
        db_session, asset_key=asset.asset_key, version_label="v2"
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_listings "
            "(asset_id,vetting_record_id,listing_state,listed_by) VALUES "
            "(:a,:v,'listed','lister')",
            a=new_asset.id,
            v=vetting.id,
        )
        await db_session.flush()
    assert LISTING_VETTING_ASSET_MISMATCH in _as_error(caught.value)


@pytest.mark.db
async def test_d21a_scope_insert_after_vetting_frozen(db_session):
    asset, _vetting, _listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
            "VALUES (:a,'connector','secrets.verify_reference')",
            a=asset.id,
        )
        await db_session.flush()
    assert _is_guard(caught.value, CONNECTOR_CHILDREN_FROZEN)


@pytest.mark.db
async def test_d21b_scope_insert_after_listing_frozen(db_session):
    await test_d21a_scope_insert_after_vetting_frozen(db_session)


@pytest.mark.db
async def test_d21c_spec_insert_after_vetting_frozen(db_session):
    asset, _vetting, _listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO connector_catalog_specs "
            "(asset_id,asset_kind,protocol_module,protocol_name,fake_name,"
            "service_module,live_adapter_status) VALUES "
            "(:a,'connector','m','P','F','s','absent')",
            a=asset.id,
        )
        await db_session.flush()
    assert _is_guard(caught.value, CONNECTOR_CHILDREN_FROZEN)


@pytest.mark.db
async def test_d21d_vetting_without_spec_refused(db_session):
    asset_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector',:k,'v1','r') RETURNING id",
            k=unique("nospec"),
        )
    ).scalar_one()
    await execute_sql(
        db_session,
        "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
        "VALUES (:a,'connector','pm.read_issues')",
        a=asset_id,
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','checker_output_admin_recorded','passed','r')",
            a=asset_id,
        )
        await db_session.flush()
    assert _is_guard(caught.value, CONNECTOR_CHILDREN_REQUIRED)


@pytest.mark.db
async def test_d21e_vetting_without_scope_refused(db_session):
    asset_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector',:k,'v1','r') RETURNING id",
            k=unique("noscope"),
        )
    ).scalar_one()
    await execute_sql(
        db_session,
        "INSERT INTO connector_catalog_specs "
        "(asset_id,asset_kind,protocol_module,protocol_name,fake_name,"
        "service_module,live_adapter_status) VALUES "
        "(:a,'connector','app.release.pm_connector','IssueTrackerConnector',"
        "'FakeIssueTrackerConnector','app.release.pm_sync_service','absent')",
        a=asset_id,
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','checker_output_admin_recorded','passed','r')",
            a=asset_id,
        )
        await db_session.flush()
    assert _is_guard(caught.value, CONNECTOR_CHILDREN_REQUIRED)


@pytest.mark.db
async def test_d21f_children_complete_helper(db_session):
    empty_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector',:k,'v1','r') RETURNING id",
            k=unique("helper"),
        )
    ).scalar_one()
    assert await children_complete(db_session, empty_id) is False
    await execute_sql(
        db_session,
        "INSERT INTO connector_catalog_specs "
        "(asset_id,asset_kind,protocol_module,protocol_name,fake_name,"
        "service_module,live_adapter_status) VALUES "
        "(:a,'connector','app.release.pm_connector','IssueTrackerConnector',"
        "'FakeIssueTrackerConnector','app.release.pm_sync_service','absent')",
        a=empty_id,
    )
    assert await children_complete(db_session, empty_id) is False
    await execute_sql(
        db_session,
        "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
        "VALUES (:a,'connector','pm.read_issues')",
        a=empty_id,
    )
    assert await children_complete(db_session, empty_id) is True


@pytest.mark.db
async def test_d21g_scope_kind_pin_refused(db_session):
    asset, _v, _l = await register_listed_blueprint(db_session)
    with pytest.raises((IntegrityError, DBAPIError)):
        await execute_sql(
            db_session,
            "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
            "VALUES (:a,'connector','pm.read_issues')",
            a=asset.id,
        )
        await db_session.flush()
    await db_session.rollback()
    with pytest.raises((IntegrityError, DBAPIError)):
        await execute_sql(
            db_session,
            "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
            "VALUES (:a,'agent_blueprint','pm.read_issues')",
            a=asset.id,
        )
        await db_session.flush()


# D-21h / D-21i live in test_ecosystem_catalog_races.py (500-line house cap).
