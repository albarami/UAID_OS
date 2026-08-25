"""Slice 83 commit-12: A3 barriers for ops leaves."""

from __future__ import annotations

import pytest

from app.tenancy import TenantContext
from tests.slice83_a1_support import seed_emergency_project
from tests.slice83_a2_c_support import (
    binding_idempotency_writer,
    emergency_hash,
    hotfix_writer,
    stab_writer,
    ticket_writer,
)
from tests.slice83_a3_copy import mutate_copied_child
from tests.slice83_a3_ops_support import (
    acceptance_writer,
    activate_writer,
    capability_writer,
    event_id,
    optimizer_writer,
    policy_version_id,
    realize_writer,
    seed_ac_world,
    seed_hotfix_a2,
    seed_incident_world,
    seed_optimizer_world,
    seed_realize_world,
    seed_stab,
    seed_two_armed,
    seed_two_blueprints,
    signals_writer,
)
from tests.slice83_a3_support import (
    assert_a3_green,
    minted_id,
    race_admin,
    race_runtime,
    row_id,
)
from tests.slice83_support import seed_org_tenant_project

pytestmark = pytest.mark.db


def _distinct(table: str, parent: str, extra: str) -> str:
    return f"SELECT count(DISTINCT {parent}) FROM {table} WHERE {extra}"


async def test_a3_avres_green(rls_engine, admin_engine):
    world = await seed_ac_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=acceptance_writer(world["ctx"], world["project"]),
        count_sql=_distinct(
            "acceptance_verification_results",
            "acceptance_verification_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-AVRES-GREEN", result.unique_row_count)


async def test_a3_avres_mutation(rls_engine, admin_engine):
    world = await seed_ac_world(admin_engine)
    await mutate_copied_child(
        table="acceptance_verification_results",
        constraint="uq_avres_run_criterion",
        parent_writer=acceptance_writer(world["ctx"], world["project"]),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "acceptance_verification_results",
            "acceptance_verification_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-AVRES-MUT")


async def test_a3_aps_green(admin_engine):
    world = await seed_two_blueprints(admin_engine)
    result = await race_admin(
        admin_engine=admin_engine,
        writer=capability_writer(world["bp1"]),
        writer_w2=capability_writer(world["bp2"]),
        count_sql=(
            "SELECT count(DISTINCT aps.capability_id) FROM agent_provided_skills aps "
            "JOIN agent_skill_capabilities c ON c.id=aps.capability_id "
            "WHERE c.blueprint_id IN (:b1, :b2)"
        ),
        count_params={"b1": world["bp1"], "b2": world["bp2"]},
    )
    assert_a3_green(result, parent_of=minted_id)
    print("A3-APS-GREEN", result.unique_row_count)


async def test_a3_aps_mutation(admin_engine):
    world = await seed_two_blueprints(admin_engine)
    await mutate_copied_child(
        table="agent_provided_skills",
        constraint="uq_aps_capability_skill",
        parent_writer=capability_writer(world["bp1"]),
        parent_id_of=minted_id,
        admin_engine=admin_engine,
        count_sql=(
            "SELECT count(DISTINCT aps.capability_id) FROM agent_provided_skills aps "
            "JOIN agent_skill_capabilities c ON c.id=aps.capability_id "
            "WHERE c.blueprint_id IN (:b1, :b2)"
        ),
        count_params={"b1": world["bp1"], "b2": world["bp2"]},
        admin=True,
    )
    print("A3-APS-MUT")


async def test_a3_realizations_green(rls_engine, admin_engine):
    world = await seed_realize_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=realize_writer(world, "a3a"),
        writer_w2=realize_writer(world, "a3b"),
        count_sql=_distinct("agent_realizations", "instance_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=lambda value: value.instance_id)
    print("A3-REAL-GREEN", result.unique_row_count)


async def test_a3_realizations_mutation(rls_engine, admin_engine):
    world = await seed_realize_world(admin_engine)
    await mutate_copied_child(
        table="agent_realizations",
        constraint="uq_agent_realizations_instance",
        parent_writer=realize_writer(world, "a3same"),
        parent_id_of=lambda value: value.instance_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct("agent_realizations", "instance_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-REAL-MUT")


async def test_a3_coc_green(rls_engine, admin_engine):
    world = await seed_optimizer_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=optimizer_writer(world["ctx"], world["project"]),
        count_sql=_distinct("cost_optimizer_citations", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-COC-GREEN", result.unique_row_count)


async def test_a3_coc_mutation(rls_engine, admin_engine):
    world = await seed_optimizer_world(admin_engine)
    await mutate_copied_child(
        table="cost_optimizer_citations",
        constraint="uq_coc_run_bucket",
        parent_writer=optimizer_writer(world["ctx"], world["project"]),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct("cost_optimizer_citations", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-COC-MUT")


async def test_a3_ecam_papa_green(rls_engine, admin_engine):
    world = await seed_emergency_project(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=binding_idempotency_writer(world, emergency_hash("s83-a3-bind-a")),
        writer_w2=binding_idempotency_writer(world, emergency_hash("s83-a3-bind-b")),
        count_sql=_distinct(
            "emergency_control_authority_members",
            "binding_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    assert_a3_green(result, parent_of=policy_version_id)
    print("A3-ECAM-PAPA-GREEN", result.unique_row_count)


async def test_a3_ecam_papa_mutation(rls_engine, admin_engine):
    world = await seed_emergency_project(admin_engine)
    await mutate_copied_child(
        table="emergency_control_authority_members",
        constraint=("uq_ecam_binding_ordinal", "uq_ecam_binding_subject"),
        parent_writer=binding_idempotency_writer(world, emergency_hash("s83-a3-ecam-ma")),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "emergency_control_authority_members",
            "binding_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    await mutate_copied_child(
        table="production_approval_policy_approvers",
        constraint=("uq_papa_policy_ordinal", "uq_papa_policy_subject"),
        parent_writer=binding_idempotency_writer(world, emergency_hash("s83-a3-papa-ma")),
        parent_id_of=policy_version_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "production_approval_policy_approvers",
            "policy_version_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-ECAM-PAPA-MUT")


async def test_a3_esre_green(rls_engine, admin_engine):
    world = await seed_two_armed(rls_engine, admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=activate_writer(world, world["project"], "s83-a3-act-a"),
        writer_w2=activate_writer(world, world["project2"], "s83-a3-act-b"),
        count_sql=_distinct("emergency_stop_run_effects", "activation_event_id", "tenant_id=:t"),
        count_params={"t": world["tenant"]},
    )
    assert_a3_green(result, parent_of=event_id)
    print("A3-ESRE-GREEN", result.unique_row_count)


async def test_a3_esre_mutation(rls_engine, admin_engine):
    world = await seed_two_armed(rls_engine, admin_engine)
    await mutate_copied_child(
        table="emergency_stop_run_effects",
        constraint="uq_esre_event_run",
        parent_writer=activate_writer(world, world["project"], "s83-a3-act-ma"),
        parent_id_of=event_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct("emergency_stop_run_effects", "activation_event_id", "tenant_id=:t"),
        count_params={"t": world["tenant"]},
    )
    print("A3-ESRE-MUT")


async def test_a3_hotfix_children_green(rls_engine, admin_engine):
    world = await seed_hotfix_a2(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=hotfix_writer(world["ctx"], world["project"], world["incident_id"], "hf-a"),
        writer_w2=hotfix_writer(world["ctx"], world["project"], world["incident_id"], "hf-b"),
        count_sql=_distinct("ops_hotfix_plans", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-HF-GREEN", result.unique_row_count)


async def test_a3_hotfix_children_mutation(rls_engine, admin_engine):
    world = await seed_hotfix_a2(admin_engine)
    await mutate_copied_child(
        table="ops_self_healing_results",
        constraint=(
            "uq_ops_hotfix_plans_run_kind",
            "uq_ops_self_healing_results_run_action",
            "uq_ops_self_healing_results_run_seq",
        ),
        parent_writer=hotfix_writer(
            world["ctx"], world["project"], world["incident_id"], "hf-same"
        ),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct("ops_self_healing_results", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-HF-MUT")


async def test_a3_incident_actions_green(rls_engine, admin_engine):
    world = await seed_incident_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=ticket_writer(world["ctx"], world["project"], world["incident_id"]),
        count_sql=_distinct(
            "ops_incident_action_results",
            "evaluation_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=lambda value: value.evaluation_id)
    print("A3-INC-GREEN", result.unique_row_count)


async def test_a3_incident_actions_mutation(rls_engine, admin_engine):
    world = await seed_incident_world(admin_engine)
    await mutate_copied_child(
        table="ops_incident_action_results",
        constraint=(
            "uq_ops_incident_action_results_eval_action",
            "uq_ops_incident_action_results_eval_seq",
        ),
        parent_writer=ticket_writer(world["ctx"], world["project"], world["incident_id"]),
        parent_id_of=lambda value: value.evaluation_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "ops_incident_action_results",
            "evaluation_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-INC-MUT")


async def test_a3_signals_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=signals_writer(ctx, world["project"], "sig-a"),
        writer_w2=signals_writer(ctx, world["project"], "sig-b"),
        count_sql=_distinct("ops_signal_results", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-SIG-GREEN", result.unique_row_count)


async def test_a3_signals_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    await mutate_copied_child(
        table="ops_signal_results",
        constraint=("uq_ops_signal_results_run_class", "uq_ops_signal_results_run_seq"),
        parent_writer=signals_writer(ctx, world["project"], "sig-same"),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct("ops_signal_results", "run_id", "tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-SIG-MUT")


async def test_a3_stab_children_green(rls_engine, admin_engine):
    world = await seed_stab(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=stab_writer(world["ctx"], world["project"], "stab-a"),
        writer_w2=stab_writer(world["ctx"], world["project"], "stab-b"),
        count_sql=_distinct(
            "ops_stabilization_criterion_results",
            "window_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-STAB-GREEN", result.unique_row_count)


async def test_a3_stab_children_mutation(rls_engine, admin_engine):
    world = await seed_stab(admin_engine)
    await mutate_copied_child(
        table="ops_stabilization_criterion_results",
        constraint=("uq_ops_stab_criteria_window_seq", "uq_ops_improvement_results_window_seq"),
        parent_writer=stab_writer(world["ctx"], world["project"], "stab-same"),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "ops_stabilization_criterion_results",
            "window_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-STAB-MUT")
