"""Slice 61b DB probes: populate, identity reconcile, fail-closed, isolation."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.ecosystem.catalog import CHECK_NAMES, CONNECTOR_CHILDREN_FROZEN, ConnectorSpecInput
from app.ecosystem.catalog_declared import (
    ACTOR_BLUEPRINT_REVIEWER,
    ACTOR_POPULATE,
    DECLARED_CONNECTORS,
    DECLARED_INTAKE,
    DECLARED_VERSION_LABEL,
    intake_file_path,
    reference_intake_digest,
)
from app.ecosystem.catalog_populate import CatalogPopulateError, populate_declared_catalog
from app.ecosystem.contract_test import CheckResult, ContractTestResult, run_connector_contract_test
from app.models.agent_instance import AgentInstance
from app.models.agent_tool_allowlist import AgentToolAllowlist
from app.models.agent_version import AgentVersion
from app.models.ecosystem_catalog import (
    CatalogAsset,
    CatalogListing,
    CatalogVettingCheckResult,
    CatalogVettingRecord,
    ConnectorCatalogSpec,
    ConnectorCatalogToolScope,
    TenantCatalogAdoption,
)
from app.repositories.catalog_admin import (
    list_asset,
    record_contract_test,
    record_review,
    register_blueprint_version,
    register_connector,
    register_reference_intake,
)
from app.repositories.catalog_reads import get_by_key, latest_listing, latest_vetting, listed_keys
from tests.ecosystem_catalog_support import (
    add_probe_blueprint,
    add_probe_version,
    execute_sql,
    seed_project,
    sha,
    stored_connector_spec,
    unique,
)

_SIX = tuple(sorted(DECLARED_CONNECTORS))
_NO_BODY = (
    CatalogAsset,
    ConnectorCatalogSpec,
    ConnectorCatalogToolScope,
    CatalogVettingRecord,
    CatalogVettingCheckResult,
    CatalogListing,
    TenantCatalogAdoption,
)


async def _count(session, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _declared_asset_n(session) -> int:
    q = (
        select(func.count())
        .select_from(CatalogAsset)
        .where(
            CatalogAsset.asset_kind == "connector",
            CatalogAsset.asset_key.in_(_SIX),
            CatalogAsset.version_label == DECLARED_VERSION_LABEL,
        )
    )
    return int((await session.execute(q)).scalar_one())


@pytest.mark.db
async def test_p8_declared_catalog_empty_before_populate(db_session):
    assert await get_by_key(db_session, "connector", "ci_evidence", "v1") is None
    assert set(DECLARED_CONNECTORS).isdisjoint(await listed_keys(db_session, "connector"))


@pytest.mark.db
async def test_p9_populate_lists_six_declared_connectors(db_session):
    report = await populate_declared_catalog(db_session)
    assert report.connector_listed == _SIX
    assert report.connector_skipped == ()
    for key in _SIX:
        asset = await get_by_key(db_session, "connector", key, "v1")
        assert asset is not None
        listing = await latest_listing(db_session, asset.id)
        assert listing is not None and listing.listing_state == "listed"
        vetting = await latest_vetting(db_session, asset.id)
        assert vetting is not None
        assert vetting.vetting_kind == "connector_contract_test"
        assert vetting.provenance == "checker_output_admin_recorded"
        assert vetting.outcome == "passed"
        passed = (
            (
                await db_session.execute(
                    select(CatalogVettingCheckResult.passed).where(
                        CatalogVettingCheckResult.vetting_record_id == vetting.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(passed) == len(CHECK_NAMES) == 5 and all(passed)
    pm = await stored_connector_spec(db_session, "pm_issues")
    assert pm.live_adapter_name is None and pm.live_adapter_status == "absent"


@pytest.mark.db
async def test_p10_second_populate_skips_unchanged(db_session):
    first = await populate_declared_catalog(db_session)
    assets = await _declared_asset_n(db_session)
    listings = await _count(db_session, CatalogListing)
    second = await populate_declared_catalog(db_session)
    assert second.connector_listed == () and second.connector_skipped == _SIX
    assert first.connector_listed == _SIX
    assert await _declared_asset_n(db_session) == assets
    assert await _count(db_session, CatalogListing) == listings


@pytest.mark.db
async def test_p11_live_adapter_vocabulary(db_session):
    await populate_declared_catalog(db_session)
    for key, declared in DECLARED_CONNECTORS.items():
        stored = await stored_connector_spec(db_session, key)
        assert stored.live_adapter_status == declared.live_adapter_status
        assert stored.live_adapter_name == declared.live_adapter_name


@pytest.mark.db
async def test_p12_ci_and_pr_share_scm_disjoint_tools(db_session):
    await populate_declared_catalog(db_session)
    ci = await get_by_key(db_session, "connector", "ci_evidence", "v1")
    pr = await get_by_key(db_session, "connector", "pr_evidence", "v1")
    assert ci is not None and pr is not None and ci.id != pr.id
    ci_s, pr_s = (
        await stored_connector_spec(db_session, "ci_evidence"),
        await stored_connector_spec(db_session, "pr_evidence"),
    )
    assert ci_s.protocol_module == pr_s.protocol_module
    assert ci_s.protocol_name == pr_s.protocol_name
    assert ci_s.fake_name == pr_s.fake_name
    assert ci_s.live_adapter_name == pr_s.live_adapter_name
    assert frozenset(ci_s.tool_names).isdisjoint(pr_s.tool_names)


@pytest.mark.db
async def test_p13_runtime_role_cannot_insert_after_populate(db_session, rls_engine):
    await populate_declared_catalog(db_session)
    await db_session.flush()
    await db_session.execute(text("SET LOCAL ROLE uaid_app"))
    assert set(DECLARED_CONNECTORS).issubset(await listed_keys(db_session, "connector"))
    with pytest.raises((IntegrityError, DBAPIError, Exception)) as caught:
        await db_session.execute(
            text(
                "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
                "VALUES ('connector','k','v1','r')"
            )
        )
        await db_session.flush()
    assert "permission denied" in str(caught.value).lower()
    await db_session.rollback()
    inserts = (
        "INSERT INTO catalog_assets (asset_kind,asset_key,version_label,registered_by) "
        "VALUES ('connector','k','v1','r')",
        "INSERT INTO catalog_listings (asset_id,vetting_record_id,listing_state,listed_by) "
        "VALUES (gen_random_uuid(),gen_random_uuid(),'listed','x')",
        "INSERT INTO catalog_vetting_records "
        "(asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
        "(gen_random_uuid(),'connector_contract_test',"
        "'checker_output_admin_recorded','passed','r')",
    )
    async with rls_engine.connect() as conn:
        for sql in inserts:
            with pytest.raises((IntegrityError, DBAPIError, Exception)) as denied:
                await conn.execute(text(sql))
                await conn.commit()
            assert "permission denied" in str(denied.value).lower()
            await conn.rollback()


@pytest.mark.db
async def test_p14_allowlist_and_instances_unchanged(db_session):
    before = (await _count(db_session, AgentToolAllowlist), await _count(db_session, AgentInstance))
    await populate_declared_catalog(db_session)
    assert (
        await _count(db_session, AgentToolAllowlist),
        await _count(db_session, AgentInstance),
    ) == before


@pytest.mark.db
async def test_p15_real_a5_and_readiness_bit_stable(db_session):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository
    from app.tenancy import TenantContext

    seeded = await seed_project(db_session)
    ctx = TenantContext(seeded["tenant"])
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    before_a5 = (
        await ProductionAutonomyRepository(db_session, ctx).evaluate(seeded["project"])
    ).to_dict()
    before_r = (await ReadinessRepository(db_session, ctx).evaluate(seeded["project"])).to_dict()
    await populate_declared_catalog(db_session)
    after_a5 = (
        await ProductionAutonomyRepository(db_session, ctx).evaluate(seeded["project"])
    ).to_dict()
    after_r = (await ReadinessRepository(db_session, ctx).evaluate(seeded["project"])).to_dict()
    assert before_a5 == after_a5
    assert before_r == after_r
    assert after_a5["a5_satisfied"] == before_a5["a5_satisfied"]
    assert after_a5["can_go_live_autonomously"] is False
    assert after_a5["ruleset_version"] == "slice54.v1"
    assert [g["status"] for g in after_a5["gates"]] == [g["status"] for g in before_a5["gates"]]
    assert after_r["readiness_level"] == before_r["readiness_level"]
    assert after_r["ruleset_version"] == "slice20.v1"


@pytest.mark.db
async def test_p16_failed_checker_rolls_back(db_session, monkeypatch):
    original = run_connector_contract_test

    def fake(spec: ConnectorSpecInput) -> ContractTestResult:
        if spec.service_module == "app.release.pm_sync_service":
            return ContractTestResult(
                results=tuple(CheckResult(name, False) for name in CHECK_NAMES), passed=False
            )
        return original(spec)

    monkeypatch.setattr("app.repositories.catalog_admin.run_connector_contract_test", fake)
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert "connector_contract_test_failed:pm_issues" in str(caught.value)
    await db_session.rollback()
    assert await _declared_asset_n(db_session) == 0
    assert set(DECLARED_CONNECTORS).isdisjoint(await listed_keys(db_session, "connector"))


@pytest.mark.db
async def test_p17_zero_versions_lists_no_blueprints(db_session):
    n_versions = await _count(db_session, AgentVersion)
    report = await populate_declared_catalog(db_session)
    assert report.blueprint_listed + report.blueprint_skipped == n_versions
    if n_versions == 0:
        assert report.blueprint_listed == 0
        assert await listed_keys(db_session, "agent_blueprint") == []


@pytest.mark.db
async def test_p18_two_versions_distinct_reviewer_then_skip(db_session):
    k1, k2 = unique("bp"), unique("bp")
    await add_probe_version(db_session, (await add_probe_blueprint(db_session, k1)).id, "v1", "a")
    await add_probe_version(db_session, (await add_probe_blueprint(db_session, k2)).id, "v1", "b")
    n_versions = await _count(db_session, AgentVersion)
    first = await populate_declared_catalog(db_session)
    assert first.blueprint_listed + first.blueprint_skipped == n_versions
    assert first.blueprint_listed >= 2
    for key in (k1, k2):
        asset = await get_by_key(db_session, "agent_blueprint", key, "v1")
        assert asset is not None and asset.registered_by == ACTOR_POPULATE
        vetting = await latest_vetting(db_session, asset.id)
        assert vetting is not None
        assert vetting.vetting_kind == "blueprint_security_review"
        assert vetting.provenance == "reviewer_asserted_admin_recorded"
        assert vetting.outcome == "passed"
        assert vetting.reviewer == ACTOR_BLUEPRINT_REVIEWER != asset.registered_by
    second = await populate_declared_catalog(db_session)
    assert second.blueprint_listed == 0
    assert second.blueprint_skipped == n_versions


@pytest.mark.db
async def test_p18b_later_version_listed_on_second_call(db_session):
    key = unique("bp")
    blueprint = await add_probe_blueprint(db_session, key)
    await add_probe_version(db_session, blueprint.id, "v1", "first")
    first = await populate_declared_catalog(db_session)
    assert await get_by_key(db_session, "agent_blueprint", key, "v1") is not None
    accounted = first.blueprint_listed + first.blueprint_skipped
    await add_probe_version(db_session, blueprint.id, "v2", "second")
    second = await populate_declared_catalog(db_session)
    assert second.blueprint_listed == 1
    assert second.blueprint_skipped == accounted
    assert await get_by_key(db_session, "agent_blueprint", key, "v2") is not None


@pytest.mark.db
async def test_p19_intake_listed_with_attestation(db_session):
    report = await populate_declared_catalog(db_session)
    assert report.intake_listed is True
    asset = await get_by_key(
        db_session, "reference_intake", DECLARED_INTAKE.asset_key, DECLARED_INTAKE.version_label
    )
    assert asset is not None
    assert asset.source_ref == DECLARED_INTAKE.source_ref
    assert asset.domain_label == "generic"
    assert asset.content_sha256 == reference_intake_digest(intake_file_path())
    vetting = await latest_vetting(db_session, asset.id)
    assert vetting is not None
    assert vetting.vetting_kind == "reference_intake_constraint_attestation"
    for model in _NO_BODY:
        columns = set(model.__table__.columns.keys())
        assert "body" not in columns and "content" not in columns


@pytest.mark.db
async def test_p20_tmp_copy_digest_differs_db_unchanged(db_session):
    await populate_declared_catalog(db_session)
    asset = await get_by_key(
        db_session, "reference_intake", DECLARED_INTAKE.asset_key, DECLARED_INTAKE.version_label
    )
    assert asset is not None
    listed_digest = asset.content_sha256
    original = intake_file_path().read_bytes()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(original + b"\n# drifted\n")
        tmp_path = Path(tmp.name)
    try:
        assert reference_intake_digest(tmp_path) != listed_digest
        reloaded = await get_by_key(
            db_session, "reference_intake", DECLARED_INTAKE.asset_key, DECLARED_INTAKE.version_label
        )
        assert reloaded is not None and reloaded.content_sha256 == listed_digest
        assert listed_digest == "sha256:" + hashlib.sha256(original).hexdigest()
    finally:
        tmp_path.unlink(missing_ok=True)


@pytest.mark.db
async def test_p22_clean_populate_matches_declared(db_session):
    await populate_declared_catalog(db_session)
    for key, declared in DECLARED_CONNECTORS.items():
        stored = await stored_connector_spec(db_session, key)
        assert stored == declared


@pytest.mark.db
async def test_p22a_wrong_service_module_raises_and_does_not_skip(db_session):
    declared = DECLARED_CONNECTORS["ci_evidence"]
    asset = await register_connector(
        db_session,
        asset_key="ci_evidence",
        version_label="v1",
        registered_by="forger",
        protocol_module=declared.protocol_module,
        protocol_name=declared.protocol_name,
        fake_name=declared.fake_name,
        service_module="app.release.pm_sync_service",
        live_adapter_status=declared.live_adapter_status,
        live_adapter_name=declared.live_adapter_name,
        tool_names=list(declared.tool_names),
    )
    vetting = await record_contract_test(db_session, asset_id=asset.id, reviewer="checker")
    await list_asset(
        db_session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
    )
    forged = await stored_connector_spec(db_session, "ci_evidence")
    assert forged.service_module == "app.release.pm_sync_service"
    assert forged != declared
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert "declared_identity_mismatch:ci_evidence" in str(caught.value)
    assert (await stored_connector_spec(db_session, "ci_evidence")).service_module == (
        "app.release.pm_sync_service"
    )
    listing = await latest_listing(db_session, asset.id)
    assert listing is not None and listing.listing_state == "listed"


@pytest.mark.db
async def test_p22b_intake_digest_mismatch_raises(db_session):
    asset = await register_reference_intake(
        db_session,
        asset_key=DECLARED_INTAKE.asset_key,
        version_label=DECLARED_INTAKE.version_label,
        registered_by="forger",
        domain_label=DECLARED_INTAKE.domain_label,
        content_sha256=sha("not-the-file"),
        source_ref=DECLARED_INTAKE.source_ref,
    )
    vetting = await record_review(
        db_session,
        asset_id=asset.id,
        vetting_kind="reference_intake_constraint_attestation",
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer="attestor",
    )
    await list_asset(
        db_session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
    )
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert "declared_identity_mismatch:generic_bounded_counter" in str(caught.value)
    reloaded = await get_by_key(
        db_session, "reference_intake", DECLARED_INTAKE.asset_key, DECLARED_INTAKE.version_label
    )
    assert reloaded is not None and reloaded.content_sha256 == sha("not-the-file")


@pytest.mark.db
async def test_p22c_catalog_v1_bound_to_other_version_raises(db_session):
    key = unique("bp")
    blueprint = await add_probe_blueprint(db_session, key)
    version_a = await add_probe_version(db_session, blueprint.id, "v1", "A")
    version_c = await add_probe_version(db_session, blueprint.id, "v2", "C")
    asset = await register_blueprint_version(
        db_session,
        asset_key=key,
        version_label="v1",
        registered_by="forger",
        agent_version_id=version_c.id,
    )
    vetting = await record_review(
        db_session,
        asset_id=asset.id,
        vetting_kind="blueprint_security_review",
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer="reviewer-b",
    )
    await list_asset(
        db_session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
    )
    with pytest.raises(CatalogPopulateError) as caught:
        await populate_declared_catalog(db_session)
    assert f"declared_identity_mismatch:{key}" in str(caught.value)
    reloaded = await get_by_key(db_session, "agent_blueprint", key, "v1")
    assert reloaded is not None
    assert reloaded.agent_version_id == version_c.id != version_a.id


@pytest.mark.db
async def test_p23_listed_product_scope_frozen(db_session):
    await populate_declared_catalog(db_session)
    asset = await get_by_key(db_session, "connector", "ci_evidence", "v1")
    assert asset is not None
    with pytest.raises((IntegrityError, DBAPIError)) as caught:
        await execute_sql(
            db_session,
            "INSERT INTO connector_catalog_tool_scope (asset_id,asset_kind,tool_name) "
            "VALUES (:a,'connector','pm.read_issues')",
            a=asset.id,
        )
        await db_session.flush()
    assert CONNECTOR_CHILDREN_FROZEN in str(caught.value)


@pytest.mark.db
async def test_p24_populate_does_not_adopt(db_session):
    before = await _count(db_session, TenantCatalogAdoption)
    await populate_declared_catalog(db_session)
    assert await _count(db_session, TenantCatalogAdoption) == before


@pytest.mark.db
async def test_p26_go_live_false_on_real_a5_after_populate(db_session):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext

    seeded = await seed_project(db_session)
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    await populate_declared_catalog(db_session)
    report = (
        await ProductionAutonomyRepository(db_session, TenantContext(seeded["tenant"])).evaluate(
            seeded["project"]
        )
    ).to_dict()
    assert report["can_go_live_autonomously"] is False
    assert report["ruleset_version"] == "slice54.v1"
