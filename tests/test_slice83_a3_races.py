"""Slice 83 commit-11: A3 barriers for evidence leaves."""

from __future__ import annotations

import pytest

from app.tenancy import TenantContext
from tests.export_bundle_support import committed_exportable, configure_signing
from tests.slice83_a3_copy import mutate_copied_child
from tests.slice83_a3_evidence_support import (
    connector_writer,
    export_fresh_writer,
    forecast_writer,
    learning_writer,
    pack_writer,
    seed_connector_asset,
    seed_connector_asset_shell,
    seed_forecast_world,
    seed_pack_world,
    spec_writer,
    vetting_writer,
)
from tests.slice83_a3_support import (
    FORECAST_CHILD_CONSTRAINTS,
    assert_a3_green,
    assert_a3_mutation,
    assert_a3_scoped_parents,
    race_admin,
    race_runtime,
    report_run_id,
    row_id,
)

pytestmark = pytest.mark.db


def _distinct(table: str, parent: str, extra: str = "") -> str:
    where = extra if extra.startswith("WHERE") else (f"WHERE {extra}" if extra else "")
    return f"SELECT count(DISTINCT {parent}) FROM {table} {where}".strip()


async def test_a3_ccs_asset_green(admin_engine):
    result = await race_admin(
        admin_engine=admin_engine,
        writer=connector_writer(),
        count_sql=_distinct("connector_catalog_specs", "asset_id"),
        count_params={},
    )
    first, second = assert_a3_green(result, parent_of=row_id, require_count=False)
    await assert_a3_scoped_parents(
        admin_engine,
        table="connector_catalog_specs",
        parent_column="asset_id",
        first=first,
        second=second,
    )
    print("A3-CCS-GREEN", first, second)


async def test_a3_ccs_asset_mutation(admin_engine):
    asset = await seed_connector_asset_shell(admin_engine)
    await assert_a3_mutation(
        lambda: race_admin(
            admin_engine=admin_engine,
            writer=spec_writer(asset.id),
            count_sql=_distinct("connector_catalog_specs", "asset_id"),
            count_params={},
        ),
        parent_of=row_id,
        constraint="uq_ccs_asset_id",
    )
    print("A3-CCS-MUT")


async def test_a3_cvcr_name_green(admin_engine):
    asset = await seed_connector_asset(admin_engine)
    sql = (
        "SELECT count(DISTINCT vetting_record_id) FROM catalog_vetting_check_results "
        "WHERE vetting_record_id IN (SELECT id FROM catalog_vetting_records WHERE asset_id=:a)"
    )
    result = await race_admin(
        admin_engine=admin_engine,
        writer=vetting_writer(asset.id),
        count_sql=sql,
        count_params={"a": asset.id},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-CVCR-GREEN", result.unique_row_count)


async def test_a3_cvcr_name_mutation(admin_engine):
    asset = await seed_connector_asset(admin_engine)
    sql = (
        "SELECT count(DISTINCT vetting_record_id) FROM catalog_vetting_check_results "
        "WHERE vetting_record_id IN (SELECT id FROM catalog_vetting_records WHERE asset_id=:a)"
    )
    await mutate_copied_child(
        table="catalog_vetting_check_results",
        constraint="uq_cvcr_record_name",
        parent_writer=vetting_writer(asset.id),
        parent_id_of=row_id,
        admin_engine=admin_engine,
        count_sql=sql,
        count_params={"a": asset.id},
        admin=True,
    )
    print("A3-CVCR-MUT")


async def test_a3_cpab_run_green(admin_engine):
    result = await race_admin(
        admin_engine=admin_engine,
        writer=learning_writer(),
        count_sql=_distinct("cross_project_aggregate_buckets", "run_id"),
        count_params={},
    )
    first, second = assert_a3_green(result, parent_of=report_run_id, require_count=False)
    await assert_a3_scoped_parents(
        admin_engine,
        table="cross_project_aggregate_buckets",
        parent_column="run_id",
        first=first,
        second=second,
    )
    print("A3-CPAB-GREEN", first, second)


async def test_a3_cpab_run_mutation(admin_engine):
    await mutate_copied_child(
        table="cross_project_aggregate_buckets",
        constraint="uq_cpab_run_class_key",
        parent_writer=learning_writer(),
        parent_id_of=report_run_id,
        admin_engine=admin_engine,
        count_sql=_distinct("cross_project_aggregate_buckets", "run_id"),
        count_params={},
        admin=True,
    )
    print("A3-CPAB-MUT")


async def _fc(rls_engine, admin_engine, world, table: str):
    return await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=forecast_writer(world),
        count_sql=_distinct(table, "run_id", "tenant_id=:t"),
        count_params={"t": world["tenant"]},
    )


async def _fc_mut(rls_engine, admin_engine, table: str):
    world = await seed_forecast_world(admin_engine)
    await mutate_copied_child(
        table=table,
        constraint=FORECAST_CHILD_CONSTRAINTS[table],
        parent_writer=forecast_writer(world),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(table, "run_id", "tenant_id=:t"),
        count_params={"t": world["tenant"]},
    )


async def test_a3_cfdr_dimension_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_dimension_results")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFDR-DIM-GREEN", result.unique_row_count)


async def test_a3_cfdr_dimension_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_dimension_results")
    print("A3-CFDR-DIM-MUT")


async def test_a3_cfdr_ordinal_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_dimension_results")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFDR-ORD-GREEN", result.unique_row_count)


async def test_a3_cfdr_ordinal_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_dimension_results")
    print("A3-CFDR-ORD-MUT")


async def test_a3_cfil_kind_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_input_lines")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFIL-KIND-GREEN", result.unique_row_count)


async def test_a3_cfil_kind_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_input_lines")
    print("A3-CFIL-KIND-MUT")


async def test_a3_cfil_route_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=forecast_writer(world),
        count_sql=(
            "SELECT count(DISTINCT run_id) FROM cost_forecast_input_lines "
            "WHERE tenant_id=:t AND model_route_hash IS NOT NULL"
        ),
        count_params={"t": world["tenant"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFIL-ROUTE-GREEN", result.unique_row_count)


async def test_a3_cfil_route_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_input_lines")
    print("A3-CFIL-ROUTE-MUT")


async def test_a3_cfil_ordinal_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_input_lines")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFIL-ORD-GREEN", result.unique_row_count)


async def test_a3_cfil_ordinal_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_input_lines")
    print("A3-CFIL-ORD-MUT")


async def test_a3_cfler_event_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_ledger_event_refs")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFLER-EVT-GREEN", result.unique_row_count)


async def test_a3_cfler_event_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_ledger_event_refs")
    print("A3-CFLER-EVT-MUT")


async def test_a3_cfler_ordinal_green(rls_engine, admin_engine):
    world = await seed_forecast_world(admin_engine)
    result = await _fc(rls_engine, admin_engine, world, "cost_forecast_ledger_event_refs")
    assert_a3_green(result, parent_of=row_id)
    print("A3-CFLER-ORD-GREEN", result.unique_row_count)


async def test_a3_cfler_ordinal_mutation(rls_engine, admin_engine):
    await _fc_mut(rls_engine, admin_engine, "cost_forecast_ledger_event_refs")
    print("A3-CFLER-ORD-MUT")


async def _ex(rls_engine, admin_engine, seeded, writer, table: str):
    return await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=seeded["tenant"],
        writer=writer,
        count_sql=_distinct(table, "export_record_id", "tenant_id=:t"),
        count_params={"t": seeded["tenant"]},
    )


async def test_a3_epef_name_green(rls_engine, admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    result = await _ex(
        rls_engine,
        admin_engine,
        seeded,
        export_fresh_writer(ctx, seeded["pack_id"]),
        "evidence_pack_export_files",
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPEF-NAME-GREEN", result.unique_row_count)


async def _ex_mut(rls_engine, admin_engine, monkeypatch, table: str, constraint):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    await mutate_copied_child(
        table=table,
        constraint=constraint,
        parent_writer=export_fresh_writer(ctx, seeded["pack_id"]),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=seeded["tenant"],
        count_sql=_distinct(table, "export_record_id", "tenant_id=:t"),
        count_params={"t": seeded["tenant"]},
    )


async def test_a3_epef_name_mutation(rls_engine, admin_engine, monkeypatch):
    await _ex_mut(
        rls_engine,
        admin_engine,
        monkeypatch,
        "evidence_pack_export_files",
        ("uq_epef_file_name", "uq_epef_ordinal"),
    )
    print("A3-EPEF-NAME-MUT")


async def test_a3_epef_ordinal_green(rls_engine, admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    result = await _ex(
        rls_engine,
        admin_engine,
        seeded,
        export_fresh_writer(ctx, seeded["pack_id"]),
        "evidence_pack_export_files",
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPEF-ORD-GREEN", result.unique_row_count)


async def test_a3_epef_ordinal_mutation(rls_engine, admin_engine, monkeypatch):
    await _ex_mut(
        rls_engine,
        admin_engine,
        monkeypatch,
        "evidence_pack_export_files",
        ("uq_epef_file_name", "uq_epef_ordinal"),
    )
    print("A3-EPEF-ORD-MUT")


async def test_a3_epms_record_green(rls_engine, admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    result = await _ex(
        rls_engine,
        admin_engine,
        seeded,
        export_fresh_writer(ctx, seeded["pack_id"]),
        "evidence_pack_manifest_signatures",
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPMS-GREEN", result.unique_row_count)


async def test_a3_epms_record_mutation(rls_engine, admin_engine, monkeypatch):
    await _ex_mut(
        rls_engine,
        admin_engine,
        monkeypatch,
        "evidence_pack_manifest_signatures",
        "uq_epms_export_record",
    )
    print("A3-EPMS-MUT")


async def _pk(rls_engine, admin_engine, world, sql: str):
    return await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=pack_writer(world),
        count_sql=sql,
        count_params={"t": world["tenant"]},
    )


async def _pk_mut(rls_engine, admin_engine, table: str, sql: str, constraint, parent_id_of=row_id):
    world = await seed_pack_world(admin_engine)
    await mutate_copied_child(
        table=table,
        constraint=constraint,
        parent_writer=pack_writer(world),
        parent_id_of=parent_id_of,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=sql,
        count_params={"t": world["tenant"]},
    )


_SEC = (
    "SELECT count(DISTINCT evidence_pack_id) FROM evidence_pack_section_results WHERE tenant_id=:t"
)
_REF = "SELECT count(DISTINCT evidence_pack_id) FROM evidence_pack_source_refs WHERE tenant_id=:t"
_RUN = "SELECT count(DISTINCT generation_run_id) FROM evidence_packs WHERE tenant_id=:t"


async def test_a3_eps_ordinal_green(rls_engine, admin_engine):
    world = await seed_pack_world(admin_engine)
    result = await _pk(rls_engine, admin_engine, world, _SEC)
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPS-ORD-GREEN", result.unique_row_count)


async def test_a3_eps_ordinal_mutation(rls_engine, admin_engine):
    await _pk_mut(
        rls_engine,
        admin_engine,
        "evidence_pack_section_results",
        _SEC,
        ("uq_eps_pack_ordinal", "uq_eps_pack_section"),
    )
    print("A3-EPS-ORD-MUT")


async def test_a3_eps_section_green(rls_engine, admin_engine):
    world = await seed_pack_world(admin_engine)
    result = await _pk(rls_engine, admin_engine, world, _SEC)
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPS-SEC-GREEN", result.unique_row_count)


async def test_a3_eps_section_mutation(rls_engine, admin_engine):
    await _pk_mut(
        rls_engine,
        admin_engine,
        "evidence_pack_section_results",
        _SEC,
        ("uq_eps_pack_ordinal", "uq_eps_pack_section"),
    )
    print("A3-EPS-SEC-MUT")


async def test_a3_epsr_ordinal_green(rls_engine, admin_engine):
    world = await seed_pack_world(admin_engine)
    result = await _pk(rls_engine, admin_engine, world, _REF)
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPSR-ORD-GREEN", result.unique_row_count)


async def test_a3_epsr_ordinal_mutation(rls_engine, admin_engine):
    await _pk_mut(
        rls_engine,
        admin_engine,
        "evidence_pack_source_refs",
        _REF,
        ("uq_epsr_pack_ordinal", "uq_epsr_pack_source"),
    )
    print("A3-EPSR-ORD-MUT")


async def test_a3_epsr_source_green(rls_engine, admin_engine):
    world = await seed_pack_world(admin_engine)
    result = await _pk(rls_engine, admin_engine, world, _REF)
    assert_a3_green(result, parent_of=row_id)
    print("A3-EPSR-SRC-GREEN", result.unique_row_count)


async def test_a3_epsr_source_mutation(rls_engine, admin_engine):
    await _pk_mut(
        rls_engine,
        admin_engine,
        "evidence_pack_source_refs",
        _REF,
        ("uq_epsr_pack_ordinal", "uq_epsr_pack_source"),
    )
    print("A3-EPSR-SRC-MUT")


async def test_a3_ep_run_green(rls_engine, admin_engine):
    world = await seed_pack_world(admin_engine)
    result = await _pk(rls_engine, admin_engine, world, _RUN)
    assert_a3_green(result, parent_of=row_id)
    print("A3-EP-RUN-GREEN", result.unique_row_count)


async def test_a3_ep_run_mutation(rls_engine, admin_engine):
    await _pk_mut(
        rls_engine,
        admin_engine,
        "evidence_packs",
        _RUN,
        "uq_evidence_packs_generation_run",
        parent_id_of=lambda pack: pack.generation_run_id,
    )
    print("A3-EP-RUN-MUT")
