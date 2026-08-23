"""Slice 61a listing/delist/adoption/trust-zone refusal probes."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import (
    ADOPTION_LISTING_DELISTED,
    CHECK_NAMES,
    DELIST_IDENTITY_IMMUTABLE,
    DELIST_ONLY_LISTED_TO_DELISTED,
    DELIST_SAME_STATE_REFUSED,
    LISTING_BLUEPRINT_SELF_REVIEW,
    LISTING_CONNECTOR_CHILDREN_REQUIRED,
    LISTING_MUST_INSERT_LISTED,
    LISTING_VETTING_KIND_MISMATCH,
    LISTING_VETTING_NOT_PASSED,
    LISTING_VETTING_PROVENANCE_MISMATCH,
)
from app.ecosystem.catalog_ddl import GLOBAL_TABLES
from app.repositories.catalog_admin import (
    delist_asset,
    list_asset,
    record_contract_test,
    record_review,
)
from app.repositories.catalog_adoptions import CatalogAdoptionRepository
from app.tenancy import TenantContext
from tests.ecosystem_catalog_support import (
    CATALOG_TABLES,
    execute_sql,
    register_listed_blueprint,
    register_probe_connector,
    register_vet_list_pm,
    seed_project,
    unique,
)


def _err(exc: BaseException) -> str:
    return str(exc)


@pytest.mark.db
async def test_d22_clause2_failed_outcome_refused(db_session):
    asset = await register_probe_connector(db_session, fake_name="DoesNotExist")
    vetting = await record_contract_test(db_session, asset_id=asset.id, reviewer="checker")
    assert vetting.outcome == "failed"
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await list_asset(
            db_session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
        )
        await db_session.flush()
    assert LISTING_VETTING_NOT_PASSED in _err(caught.value)


@pytest.mark.db
async def test_d22_clause3_wrong_vetting_kind_refused(db_session):
    asset = await register_probe_connector(db_session)
    await execute_sql(
        db_session,
        "INSERT INTO catalog_vetting_records "
        "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
        "(:a,'blueprint_security_review','reviewer_asserted_admin_recorded','passed','r')",
        a=asset.id,
    )
    vetting_id = (
        await execute_sql(
            db_session,
            "SELECT id FROM catalog_vetting_records WHERE asset_id=:a "
            "AND vetting_kind='blueprint_security_review'",
            a=asset.id,
        )
    ).scalar_one()
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await list_asset(
            db_session, asset_id=asset.id, vetting_record_id=vetting_id, listed_by="lister"
        )
        await db_session.flush()
    assert LISTING_VETTING_KIND_MISMATCH in _err(caught.value)


@pytest.mark.db
async def test_d22_clause4_wrong_provenance_refused(db_session):
    asset = await register_probe_connector(db_session)
    await db_session.execute(
        text(
            "ALTER TABLE catalog_vetting_records "
            "DROP CONSTRAINT ck_catalog_vetting_records_ck_cvr_kind_provenance"
        )
    )
    record_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','reviewer_asserted_admin_recorded',"
            "'passed','r') RETURNING id",
            a=asset.id,
        )
    ).scalar_one()
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await list_asset(
            db_session, asset_id=asset.id, vetting_record_id=record_id, listed_by="lister"
        )
        await db_session.flush()
    assert LISTING_VETTING_PROVENANCE_MISMATCH in _err(caught.value)


@pytest.mark.db
async def test_d22_clause5_blueprint_self_review_refused(db_session):
    asset, _vetting, _listing = await register_listed_blueprint(db_session)
    self_review = await record_review(
        db_session,
        asset_id=asset.id,
        vetting_kind="blueprint_security_review",
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer=asset.registered_by,
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await list_asset(
            db_session, asset_id=asset.id, vetting_record_id=self_review.id, listed_by="lister"
        )
        await db_session.flush()
    assert LISTING_BLUEPRINT_SELF_REVIEW in _err(caught.value)


@pytest.mark.db
async def test_d22_clause6_non_listed_insert_refused(db_session):
    _asset, vetting, _listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_listings "
            "(asset_id,vetting_record_id,listing_state,listed_by) VALUES "
            "(:a,:v,'delisted','lister')",
            a=_asset.id,
            v=vetting.id,
        )
        await db_session.flush()
    assert LISTING_MUST_INSERT_LISTED in _err(caught.value)


@pytest.mark.db
async def test_d22_clause7_listing_calls_children_complete(db_session):
    await db_session.execute(
        text("ALTER TABLE connector_catalog_specs DISABLE TRIGGER connector_spec_freeze_guard")
    )
    await db_session.execute(
        text(
            "ALTER TABLE connector_catalog_tool_scope DISABLE TRIGGER connector_scope_freeze_guard"
        )
    )
    await db_session.execute(
        text("ALTER TABLE catalog_vetting_records DISABLE TRIGGER catalog_vetting_records_guard")
    )
    enabled = (
        await execute_sql(
            db_session,
            "SELECT tgenabled FROM pg_trigger WHERE tgname='catalog_listings_guard'",
        )
    ).scalar_one()
    assert enabled in {"O", b"O"}
    asset_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector',:k,'v1','r') RETURNING id",
            k=unique("incomplete"),
        )
    ).scalar_one()
    record_id = (
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_records "
            "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:a,'connector_contract_test','checker_output_admin_recorded',"
            "'passed','r') RETURNING id",
            a=asset_id,
        )
    ).scalar_one()
    for name in CHECK_NAMES:
        await execute_sql(
            db_session,
            "INSERT INTO catalog_vetting_check_results "
            "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)",
            id=record_id,
            n=name,
        )
    await db_session.execute(
        text(
            "SET CONSTRAINTS catalog_vetting_records_shape_match, "
            "catalog_vetting_check_results_shape_match IMMEDIATE"
        )
    )
    await db_session.execute(
        text("ALTER TABLE connector_catalog_specs ENABLE TRIGGER connector_spec_freeze_guard")
    )
    await db_session.execute(
        text("ALTER TABLE connector_catalog_tool_scope ENABLE TRIGGER connector_scope_freeze_guard")
    )
    await db_session.execute(
        text("ALTER TABLE catalog_vetting_records ENABLE TRIGGER catalog_vetting_records_guard")
    )
    still = (
        await execute_sql(
            db_session,
            "SELECT tgenabled FROM pg_trigger WHERE tgname='catalog_listings_guard'",
        )
    ).scalar_one()
    assert still in {"O", b"O"}
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await list_asset(
            db_session, asset_id=asset_id, vetting_record_id=record_id, listed_by="lister"
        )
        await db_session.flush()
    assert LISTING_CONNECTOR_CHILDREN_REQUIRED in _err(caught.value)


@pytest.mark.db
async def test_d23_two_live_listings_refused(db_session):
    asset, vetting, _listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)):
        await list_asset(
            db_session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister2"
        )
        await db_session.flush()


@pytest.mark.db
async def test_d24_delist_lifecycle_refusals(db_session):
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    updated = await delist_asset(db_session, listing_id=listing.id, reason="retired")
    assert updated.listing_state == "delisted"
    assert updated.delisted_at is not None
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await db_session.execute(
            text("UPDATE catalog_listings SET listing_state='listed' WHERE id=:i"),
            {"i": listing.id},
        )
        await db_session.flush()
    assert DELIST_ONLY_LISTED_TO_DELISTED in _err(caught.value)
    await db_session.rollback()
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await db_session.execute(
            text(
                "UPDATE catalog_listings SET listing_state='delisted', "
                "delisted_at=now(), delisted_reason='x', listed_by='mutated' WHERE id=:i"
            ),
            {"i": listing.id},
        )
        await db_session.flush()
    assert DELIST_IDENTITY_IMMUTABLE in _err(caught.value)
    await db_session.rollback()
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await db_session.execute(
            text("UPDATE catalog_listings SET listed_by='same-state' WHERE id=:i"),
            {"i": listing.id},
        )
        await db_session.flush()
    assert DELIST_SAME_STATE_REFUSED in _err(caught.value)


@pytest.mark.db
async def test_d25_adoption_is_not_a_grant_and_audit_is_safe(db_session):
    seeded = await seed_project(db_session)
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    allow_before = (
        await execute_sql(db_session, "SELECT count(*) FROM agent_tool_allowlist")
    ).scalar_one()
    inst_before = (
        await execute_sql(db_session, "SELECT count(*) FROM agent_instances")
    ).scalar_one()
    await CatalogAdoptionRepository(db_session, TenantContext(seeded["tenant"])).adopt(
        seeded["project"], listing.id, adopted_by="adopter"
    )
    payload = (
        await execute_sql(
            db_session,
            "SELECT payload::text FROM audit_logs WHERE action='catalog.adopted' "
            "ORDER BY created_at DESC LIMIT 1",
        )
    ).scalar_one()
    assert "source_ref" not in payload
    assert "domain_label" not in payload
    allow_after = (
        await execute_sql(db_session, "SELECT count(*) FROM agent_tool_allowlist")
    ).scalar_one()
    inst_after = (
        await execute_sql(db_session, "SELECT count(*) FROM agent_instances")
    ).scalar_one()
    assert allow_before == allow_after
    assert inst_before == inst_after


@pytest.mark.db
async def test_d26_delisted_idempotent_and_cross_tenant(db_session, admin_engine, rls_engine):
    # Committed RLS probe first: db_session's later audit_append holds the
    # advisory xact lock until the test fixture rolls back, so a second
    # connection must not audit while that transaction is still open.
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        seeded2 = await seed_project(session)
        _a, _v, listed = await register_vet_list_pm(session)
        await session.execute(
            text("SELECT set_config('app.current_tenant',:t,true)"),
            {"t": str(seeded2["tenant"])},
        )
        adopted = await CatalogAdoptionRepository(session, TenantContext(seeded2["tenant"])).adopt(
            seeded2["project"], listed.id, adopted_by="adopter"
        )
        await session.commit()
        other_tenant = seeded2["tenant2"]
        adoption_id = adopted.id
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(other_tenant)}
        )
        visible = (
            await conn.execute(
                text("SELECT count(*) FROM tenant_catalog_adoptions WHERE id=:i"),
                {"i": adoption_id},
            )
        ).scalar_one()
        assert visible == 0

    seeded = await seed_project(db_session)
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    await delist_asset(db_session, listing_id=listing.id, reason="retired")
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await CatalogAdoptionRepository(db_session, TenantContext(seeded["tenant"])).adopt(
            seeded["project"], listing.id, adopted_by="adopter"
        )
        await db_session.flush()
    assert ADOPTION_LISTING_DELISTED in _err(caught.value)
    await db_session.rollback()
    seeded = await seed_project(db_session)
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    repo = CatalogAdoptionRepository(db_session, TenantContext(seeded["tenant"]))
    first = await repo.adopt(seeded["project"], listing.id, adopted_by="adopter")
    second = await repo.adopt(seeded["project"], listing.id, adopted_by="adopter")
    assert first.id == second.id


@pytest.mark.db
async def test_d27_runtime_cannot_write_globals(rls_engine, admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        _asset, _vetting, listing = await register_vet_list_pm(session)
        await session.commit()
        listing_id = listing.id
    async with rls_engine.connect() as conn:
        for table, sql in (
            (
                "catalog_assets",
                "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
                "VALUES ('connector','k','v1','r')",
            ),
            (
                "connector_catalog_specs",
                "INSERT INTO connector_catalog_specs "
                "(asset_id,asset_kind,protocol_module,protocol_name,fake_name,"
                "service_module,live_adapter_status) VALUES "
                "(gen_random_uuid(),'connector','m','P','F','s','absent')",
            ),
            (
                "connector_catalog_tool_scope",
                "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
                "VALUES (gen_random_uuid(),'connector','pm.read_issues')",
            ),
            (
                "catalog_vetting_records",
                "INSERT INTO catalog_vetting_records "
                "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
                "(gen_random_uuid(),'connector_contract_test',"
                "'checker_output_admin_recorded','passed','r')",
            ),
            (
                "catalog_vetting_check_results",
                "INSERT INTO catalog_vetting_check_results "
                "(vetting_record_id,check_name,passed) VALUES "
                "(gen_random_uuid(),'tool_scope_nonempty',true)",
            ),
            (
                "catalog_listings",
                "INSERT INTO catalog_listings "
                "(asset_id,vetting_record_id,listing_state,listed_by) VALUES "
                "(gen_random_uuid(),gen_random_uuid(),'listed','x')",
            ),
        ):
            with pytest.raises((IntegrityError, DBAPIError, Exception)) as caught:
                await conn.execute(text(sql))
                await conn.commit()
            assert "permission denied" in _err(caught.value).lower() or table in _err(caught.value)
            await conn.rollback()
        with pytest.raises((IntegrityError, DBAPIError, Exception)) as caught:
            await conn.execute(
                text("UPDATE catalog_listings SET listed_by='x' WHERE id=:i"),
                {"i": listing_id},
            )
            await conn.commit()
        assert "permission denied" in _err(caught.value).lower()
        await conn.rollback()


@pytest.mark.db
async def test_d28_runtime_privileges_and_rls_forced(rls_engine):
    names = ", ".join(f"'{name}'" for name in CATALOG_TABLES)
    async with rls_engine.connect() as conn:
        grants = (
            await conn.execute(
                text(
                    "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee='uaid_app' AND table_schema='public' "
                    f"AND table_name IN ({names})"
                )
            )
        ).all()
    by_table: dict[str, set[str]] = {}
    for table, privilege in grants:
        by_table.setdefault(table, set()).add(privilege)
    for table in GLOBAL_TABLES:
        assert by_table.get(table, set()) == {"SELECT"}
    assert by_table.get("tenant_catalog_adoptions", set()) == {"SELECT", "INSERT"}
    async with rls_engine.connect() as conn:
        rls = (
            await conn.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='tenant_catalog_adoptions'"
                )
            )
        ).one()
    assert rls == (True, True)


@pytest.mark.db
async def test_d29_delete_truncate_blocked_listing_update_works(db_session):
    _asset, _vetting, listing = await register_vet_list_pm(db_session)
    for table in CATALOG_TABLES:
        with pytest.raises((IntegrityError, DBAPIError)) as caught:
            await db_session.execute(text(f"DELETE FROM {table}"))
            await db_session.flush()
        assert "append-only" in _err(caught.value)
        await db_session.rollback()
        _asset, _vetting, listing = await register_vet_list_pm(db_session)
        await db_session.execute(
            text(
                "SET CONSTRAINTS catalog_vetting_records_shape_match, "
                "catalog_vetting_check_results_shape_match IMMEDIATE"
            )
        )
        with pytest.raises((IntegrityError, DBAPIError)) as caught:
            await db_session.execute(text(f"TRUNCATE {table} CASCADE"))
        assert "append-only" in _err(caught.value)
        await db_session.rollback()
        _asset, _vetting, listing = await register_vet_list_pm(db_session)
    updated = await delist_asset(db_session, listing_id=listing.id, reason="retired")
    assert updated.listing_state == "delisted"
