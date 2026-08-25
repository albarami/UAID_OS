"""Slice 83 commit-12: A3 barriers for ops leaves."""

from __future__ import annotations

import uuid

import pytest

from app.models.acceptance_verification import AcceptanceVerificationRun
from app.models.cost_optimizer import CostOptimizerRun
from app.models.emergency_control import EmergencyControlBinding, EmergencyStopEvent
from app.models.go_live_decision import GoLiveEvaluation
from app.models.ops_incident import OpsIncidentActionEvaluation
from app.models.production_preapproval import ProductionApprovalPolicyVersion
from app.tenancy import TenantContext
from tests.slice83_a1_support import seed_emergency_project
from tests.slice83_a2_c_support import (
    binding_idempotency_writer,
    commit_serializable,
    emergency_hash,
    hotfix_writer,
    stab_writer,
    ticket_writer,
)
from tests.slice83_a3_ops_support import (
    acceptance_writer,
    activate_writer,
    capability_writer,
    evaluation_for,
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
    seed_two_cycles,
    signals_writer,
)
from tests.slice83_a3_support import (
    assert_a3_green,
    assert_a3_mutation,
    force_row_id,
    force_sql_pk_default,
    minted_id,
    race_admin,
    race_runtime,
    row_id,
)
from tests.slice83_support import SERIALIZABLE, seed_org_tenant_project, unique_row_count

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
    with force_row_id(AcceptanceVerificationRun, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
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
            ),
            parent_of=row_id,
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
    async with force_sql_pk_default(admin_engine, "agent_skill_capabilities", uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_admin(
                admin_engine=admin_engine,
                writer=capability_writer(world["bp1"]),
                writer_w2=capability_writer(world["bp2"]),
                count_sql=(
                    "SELECT count(DISTINCT aps.capability_id) FROM agent_provided_skills aps "
                    "JOIN agent_skill_capabilities c ON c.id=aps.capability_id "
                    "WHERE c.blueprint_id IN (:b1, :b2)"
                ),
                count_params={"b1": world["bp1"], "b2": world["bp2"]},
            ),
            parent_of=minted_id,
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
    await assert_a3_mutation(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=realize_writer(world, "a3same"),
            count_sql=_distinct(
                "agent_realizations", "instance_id", "tenant_id=:t AND project_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        parent_of=lambda value: None if value is None else value.instance_id,
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
    with force_row_id(CostOptimizerRun, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=optimizer_writer(world["ctx"], world["project"]),
                count_sql=_distinct(
                    "cost_optimizer_citations", "run_id", "tenant_id=:t AND project_id=:p"
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            ),
            parent_of=row_id,
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
    with force_row_id(EmergencyControlBinding, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=binding_idempotency_writer(world, emergency_hash("s83-a3-ecam-ma")),
                writer_w2=binding_idempotency_writer(world, emergency_hash("s83-a3-ecam-mb")),
                count_sql=_distinct(
                    "emergency_control_authority_members",
                    "binding_id",
                    "tenant_id=:t AND project_id=:p",
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            ),
            parent_of=row_id,
        )
    with force_row_id(ProductionApprovalPolicyVersion, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=binding_idempotency_writer(world, emergency_hash("s83-a3-papa-ma")),
                writer_w2=binding_idempotency_writer(world, emergency_hash("s83-a3-papa-mb")),
                count_sql=_distinct(
                    "production_approval_policy_approvers",
                    "policy_version_id",
                    "tenant_id=:t AND project_id=:p",
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            ),
            parent_of=policy_version_id,
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
    with force_row_id(EmergencyStopEvent, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=activate_writer(world, world["project"], "s83-a3-act-ma"),
                writer_w2=activate_writer(world, world["project2"], "s83-a3-act-mb"),
                count_sql=_distinct(
                    "emergency_stop_run_effects", "activation_event_id", "tenant_id=:t"
                ),
                count_params={"t": world["tenant"]},
            ),
            parent_of=event_id,
        )
    print("A3-ESRE-MUT")


async def test_a3_glegr_green(rls_engine, admin_engine):
    world = await seed_two_cycles(rls_engine, admin_engine)
    first = await commit_serializable(
        rls_engine, world["tenant"], evaluation_for(world, world["cycle"])
    )
    second = await commit_serializable(
        rls_engine, world["tenant"], evaluation_for(world, world["cycle2"])
    )
    count = await unique_row_count(
        admin_engine,
        _distinct(
            "go_live_evaluation_gate_results",
            "evaluation_id",
            "tenant_id=:t AND project_id=:p",
        ),
        {"t": world["tenant"], "p": world["project"]},
    )
    assert first.id != second.id
    assert count >= 2
    print("A3-GLEGR-GREEN", count)


async def test_a3_glegr_mutation(rls_engine, admin_engine):
    world = await seed_two_cycles(rls_engine, admin_engine)
    with force_row_id(GoLiveEvaluation, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=evaluation_for(world, world["cycle"]),
                writer_w2=evaluation_for(world, world["cycle2"]),
                isolation_level=SERIALIZABLE,
                count_sql=_distinct(
                    "go_live_evaluation_gate_results",
                    "evaluation_id",
                    "tenant_id=:t AND project_id=:p",
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            ),
            parent_of=row_id,
        )
    print("A3-GLEGR-MUT")


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
    await assert_a3_mutation(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=hotfix_writer(world["ctx"], world["project"], world["incident_id"], "hf-same"),
            count_sql=_distinct(
                "ops_self_healing_results", "run_id", "tenant_id=:t AND project_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        parent_of=row_id,
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
    with force_row_id(OpsIncidentActionEvaluation, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
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
            ),
            parent_of=lambda value: None if value is None else value.evaluation_id,
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
    await assert_a3_mutation(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=signals_writer(ctx, world["project"], "sig-same"),
            count_sql=_distinct("ops_signal_results", "run_id", "tenant_id=:t AND project_id=:p"),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        parent_of=row_id,
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
    await assert_a3_mutation(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=stab_writer(world["ctx"], world["project"], "stab-same"),
            count_sql=_distinct(
                "ops_improvement_results", "window_id", "tenant_id=:t AND project_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        parent_of=row_id,
    )
    print("A3-STAB-MUT")
