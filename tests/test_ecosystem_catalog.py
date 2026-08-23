"""Slice 61a Docker-free probes: checker, vocabulary, isolation, frozen hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from app.ecosystem.catalog import (
    ASSET_KINDS,
    CHECK_NAMES,
    REQUIRED_PROVENANCE,
    REQUIRED_VETTING_KIND,
    VETTING_KINDS,
    maps_are_exhaustive,
    refuse_checker_provenance_for_review,
    CatalogValidationError,
)
from app.ecosystem.catalog_db_checks import CHECK_NAME_SQL, RESULT_CHECK_CONSTRAINTS
from app.ecosystem.contract_test import run_connector_contract_test
from app.intake.readiness import RULESET_VERSION
from app.release.production_autonomy import A5_RULESET_VERSION
from tests.ecosystem_catalog_support import (
    CATALOG_TABLES,
    CORE_DECISION_GLOBS,
    FROZEN_HASHES,
    probe_spec,
    real_connector_specs,
)


def test_d1_well_formed_spec_passes_all_five():
    result = run_connector_contract_test(probe_spec())
    assert result.passed is True
    assert tuple(r.name for r in result.results) == CHECK_NAMES
    assert all(r.passed for r in result.results)


def test_d2_empty_scope_fails():
    result = run_connector_contract_test(probe_spec(tools=()))
    assert result.passed is False
    assert dict((r.name, r.passed) for r in result.results)["tool_scope_nonempty"] is False


def test_d3_duplicate_tool_name_fails():
    result = run_connector_contract_test(probe_spec(tools=("pm.read_issues", "pm.read_issues")))
    assert dict((r.name, r.passed) for r in result.results)["tool_scope_nonempty"] is False


def test_d4_unknown_tool_fails():
    result = run_connector_contract_test(probe_spec(tools=("not.a.registered.tool",)))
    assert dict((r.name, r.passed) for r in result.results)["tool_scope_resolves"] is False


def test_d5_non_protocol_target_fails():
    result = run_connector_contract_test(probe_spec(protocol_name="NotAProtocol"))
    assert dict((r.name, r.passed) for r in result.results)["protocol_resolves"] is False


def test_d6_fake_missing_method_fails():
    result = run_connector_contract_test(probe_spec(fake_name="ProbeFakeMissing"))
    assert dict((r.name, r.passed) for r in result.results)["fake_conforms"] is False


def test_d7_fake_mismatched_parameter_names_fails():
    result = run_connector_contract_test(probe_spec(fake_name="ProbeFakeMismatch"))
    assert dict((r.name, r.passed) for r in result.results)["fake_conforms"] is False


def test_d8_adapter_iff_refusals():
    missing = run_connector_contract_test(
        probe_spec(status="shipped_mock_tested_no_live_provider", adapter="DoesNotExist")
    )
    assert dict((r.name, r.passed) for r in missing.results)["live_adapter_symbol"] is False
    absent_with_name = run_connector_contract_test(probe_spec(status="absent", adapter="ProbeFake"))
    assert (
        dict((r.name, r.passed) for r in absent_with_name.results)["live_adapter_symbol"] is False
    )


def test_d9_six_real_services_pass_and_rename_breaks():
    specs = real_connector_specs()
    assert set(specs) == {"ci", "pr", "deploy", "monitoring", "secrets", "pm"}
    for spec in specs.values():
        result = run_connector_contract_test(spec)
        assert result.passed is True, spec
    broken = run_connector_contract_test(
        specs["ci"].__class__(**{**specs["ci"].__dict__, "fake_name": "SCMConnectorError"})
    )
    assert broken.passed is False
    assert dict((r.name, r.passed) for r in broken.results)["fake_conforms"] is False


def test_d10_maps_are_exhaustive_without_default_branch():
    assert maps_are_exhaustive() is True
    assert set(REQUIRED_VETTING_KIND) == set(ASSET_KINDS)
    assert set(REQUIRED_PROVENANCE) == set(VETTING_KINDS)


def test_d11_check_names_match_constraint_list():
    sql = dict(RESULT_CHECK_CONSTRAINTS)["ck_cvcr_check_name"]
    for name in CHECK_NAMES:
        assert f"'{name}'" in sql
    assert sql == f"check_name IN ({CHECK_NAME_SQL})"


def test_d15_record_review_refuses_checker_provenance_in_python():
    try:
        refuse_checker_provenance_for_review("checker_output_admin_recorded")
    except CatalogValidationError as exc:
        assert "refuses checker_output_admin_recorded" in str(exc)
    else:
        raise AssertionError("record_review must refuse checker provenance")


def test_d30_no_body_column_and_no_intake_content_callable():
    from app.models.ecosystem_catalog import (
        CatalogAsset,
        CatalogListing,
        CatalogVettingCheckResult,
        CatalogVettingRecord,
        ConnectorCatalogSpec,
        ConnectorCatalogToolScope,
        TenantCatalogAdoption,
    )

    for model in (
        CatalogAsset,
        ConnectorCatalogSpec,
        ConnectorCatalogToolScope,
        CatalogVettingRecord,
        CatalogVettingCheckResult,
        CatalogListing,
        TenantCatalogAdoption,
    ):
        columns = set(model.__table__.columns.keys())
        assert "body" not in columns
        assert "content" not in columns
    ecosystem = Path("app/ecosystem")
    for path in ecosystem.glob("*.py"):
        text = path.read_text()
        assert "def get_intake_content" not in text
        assert "return intake content" not in text


def test_d31_core_decision_modules_do_not_mention_catalog():
    roots = [Path(p) for p in CORE_DECISION_GLOBS]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.py"))
    forbidden_imports = ("app.ecosystem", "from app.ecosystem")
    for path in files:
        text = path.read_text()
        for token in forbidden_imports:
            assert token not in text, f"{path} imports catalog"
        for table in CATALOG_TABLES:
            assert table not in text, f"{path} mentions {table}"


def test_d32_frozen_sha256_unchanged():
    for path, expected in FROZEN_HASHES.items():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert actual == expected, path


def test_d34_rulesets_and_literal_false_go_live():
    from app.release.production_autonomy import ProductionAutonomyReport

    assert A5_RULESET_VERSION == "slice54.v1"
    assert RULESET_VERSION == "slice20.v1"
    report = ProductionAutonomyReport(project_id="probe")
    assert report.to_dict()["can_go_live_autonomously"] is False


@pytest.mark.db
async def test_d33_real_a5_and_readiness_bit_stable_across_lifecycle(db_session):
    from app.repositories.catalog_admin import delist_asset
    from app.repositories.catalog_adoptions import CatalogAdoptionRepository
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository
    from app.tenancy import TenantContext
    from tests.ecosystem_catalog_support import register_vet_list_pm, seed_project

    seeded = await seed_project(db_session)
    ctx = TenantContext(seeded["tenant"])
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(seeded["tenant"])}
    )
    before_a5 = (
        await ProductionAutonomyRepository(db_session, ctx).evaluate(seeded["project"])
    ).to_dict()
    before_ready = (
        await ReadinessRepository(db_session, ctx).evaluate(seeded["project"])
    ).to_dict()
    asset, vetting, listing = await register_vet_list_pm(db_session)
    await CatalogAdoptionRepository(db_session, ctx).adopt(
        seeded["project"], listing.id, adopted_by="adopter"
    )
    await delist_asset(db_session, listing_id=listing.id, reason="retired")
    after_a5 = (
        await ProductionAutonomyRepository(db_session, ctx).evaluate(seeded["project"])
    ).to_dict()
    after_ready = (await ReadinessRepository(db_session, ctx).evaluate(seeded["project"])).to_dict()
    assert before_a5 == after_a5
    assert before_ready == after_ready
    assert after_a5["ruleset_version"] == A5_RULESET_VERSION == "slice54.v1"
    assert after_ready["ruleset_version"] == RULESET_VERSION == "slice20.v1"
    assert after_a5["can_go_live_autonomously"] is False
    assert after_ready["can_go_live_autonomously"] is False
    assert asset.id is not None and vetting.id is not None
