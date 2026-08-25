"""Slice 83 inventory mutations plus commit-6 subtier tests 8–9."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_slice83_inventory import (
    B2_SQL,
    _assert_b2_catalog,
    _assert_b2_edge_evidence,
    _assert_index_coverage,
    _assert_pending_empty,
    _assert_tier_a_registration,
    _assert_tier_derivation,
    _node_exists,
    _od8_maps,
)
from tests.writer_inventory import (
    A1_LEAF_IDS,
    B2_EDGE_EVIDENCE,
    CANDIDATE_ENDPOINTS,
    PENDING_TIER_A_BATCHES,
    SUBTIER,
    TIER_A_NODES,
    WRITE_LEAVES,
    B2EdgeEvidence,
    Candidate,
    WriteLeaf,
)

pytestmark = pytest.mark.db

_CONTENT = "agent_versions.uq_agent_versions_content_hash"
_LABEL = "agent_versions.uq_agent_versions_blueprint_id_version_label"


@pytest.mark.asyncio
async def test_p_mut_8_b1_and_b2_4(admin_engine) -> None:
    """P-MUT-8: a B1 leaf on a collidable table fails test 3; a B2 FK gap fails B2-4."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    b1 = next(leaf for leaf in WRITE_LEAVES if leaf.tier == "B1")
    moved = tuple(
        replace(leaf, table="budgets") if leaf.leaf_id == b1.leaf_id else leaf
        for leaf in WRITE_LEAVES
    )
    with pytest.raises(AssertionError, match=re.escape(b1.leaf_id)):
        _assert_tier_derivation(moved, collidable)
    b2 = next(leaf for leaf in WRITE_LEAVES if leaf.tier == "B2")
    broken = tuple(
        replace(leaf, parent_fk_column="id") if leaf.leaf_id == b2.leaf_id else leaf
        for leaf in WRITE_LEAVES
    )
    async with admin_engine.connect() as conn:
        from sqlalchemy import text

        rows = (await conn.execute(text(B2_SQL))).mappings().all()
    with pytest.raises(AssertionError, match="B2-1/B2-4"):
        _assert_b2_catalog(broken, rows, collidable)


def test_p_mut_9_unbarriered_registered_leaf() -> None:
    """P-MUT-9: removing one TIER_A_NODES entry names the unbarriered leaf."""
    target = "budgets.uq_budgets_tenant_id_project_id"
    reduced = {key: value for key, value in TIER_A_NODES.items() if key != target}
    with pytest.raises(AssertionError, match=re.escape(target)):
        _assert_tier_a_registration(WRITE_LEAVES, reduced, PENDING_TIER_A_BATCHES)


@pytest.mark.asyncio
async def test_p_mut_10_register_version_axes(admin_engine) -> None:
    """P-MUT-10: omitting either agent_versions axis fails per-candidate coverage."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    version = next(c for c in CANDIDATE_ENDPOINTS if c.name == "register_version")
    for dropped in (_CONTENT, _LABEL):
        mutated = tuple(
            replace(c, leaf_ids=tuple(lid for lid in c.leaf_ids if lid != dropped))
            if c.name == "register_version"
            else c
            for c in CANDIDATE_ENDPOINTS
        )
        with pytest.raises(AssertionError, match=re.escape(dropped.split(".", 1)[1])):
            _assert_index_coverage(mutated, WRITE_LEAVES, collidable)
    stripped = tuple(
        replace(c, leaf_ids=version.leaf_ids[1:]) if c.name == "register_version" else c
        for c in CANDIDATE_ENDPOINTS
    )
    with pytest.raises(AssertionError, match="register_version"):
        _assert_index_coverage(stripped, WRITE_LEAVES, collidable)


@pytest.mark.asyncio
async def test_p_mut_14_per_candidate_not_per_table(admin_engine) -> None:
    """P-MUT-14: a second candidate declaring both axes does not hide register_version's omission."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    version = next(c for c in CANDIDATE_ENDPOINTS if c.name == "register_version")
    cover = Candidate(
        "app/agents/registry.py",
        1,
        "cover_both_axes",
        "pg_insert",
        version.leaf_ids,
    )
    for dropped in (_CONTENT, _LABEL):
        mutated = tuple(
            replace(c, leaf_ids=tuple(lid for lid in c.leaf_ids if lid != dropped))
            if c.name == "register_version"
            else c
            for c in CANDIDATE_ENDPOINTS
        ) + (cover,)
        with pytest.raises(AssertionError, match="register_version"):
            _assert_index_coverage(mutated, WRITE_LEAVES, collidable)
        union: dict[str, set[str]] = {}
        for candidate in mutated:
            for leaf_id in candidate.leaf_ids:
                table, _, idx = leaf_id.partition(".")
                if idx != "-":
                    union.setdefault(table, set()).add(idx)
        assert union["agent_versions"] == collidable["agent_versions"]


@pytest.mark.asyncio
async def test_p_mut_15_b2_catalog_conditions(admin_engine) -> None:
    """P-MUT-15: B2-2, B2-1, B2-3, and wrong parent-leaf each fail by name."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    from sqlalchemy import text

    async with admin_engine.connect() as conn:
        rows = (await conn.execute(text(B2_SQL))).mappings().all()
    scope = next(leaf for leaf in WRITE_LEAVES if leaf.table == "connector_catalog_tool_scope")
    reviewers = next(leaf for leaf in WRITE_LEAVES if leaf.table == "agent_realization_reviewers")

    as_tenant = tuple(
        replace(leaf, parent_fk_column="tenant_id") if leaf.leaf_id == reviewers.leaf_id else leaf
        for leaf in WRITE_LEAVES
    )
    with pytest.raises(AssertionError, match="B2-2"):
        _assert_b2_catalog(as_tenant, rows, collidable)

    wrong_parent = tuple(
        replace(leaf, parent_table="budgets") if leaf.leaf_id == reviewers.leaf_id else leaf
        for leaf in WRITE_LEAVES
    )
    with pytest.raises(AssertionError, match="B2-1/B2-4"):
        _assert_b2_catalog(wrong_parent, rows, collidable)

    seeded = tuple(
        replace(leaf, parent_table="skills", parent_fk_column="skill_id")
        if leaf.leaf_id == scope.leaf_id
        else leaf
        for leaf in WRITE_LEAVES
    )
    with pytest.raises(AssertionError, match="B2-3|B2-1/B2-4"):
        _assert_b2_catalog(seeded, rows, collidable)

    bad_parent_leaf = tuple(
        replace(edge, parent_leaf_id="budgets.uq_budgets_tenant_id_project_id")
        if edge.leaf_id == reviewers.leaf_id
        else edge
        for edge in B2_EDGE_EVIDENCE
    )
    with pytest.raises(AssertionError, match="parent_table"):
        _assert_b2_edge_evidence(CANDIDATE_ENDPOINTS, WRITE_LEAVES, bad_parent_leaf)


def test_p_mut_16_shared_b2_uncited_edge() -> None:
    """P-MUT-16: one cited B2 edge cannot mask a second uncited candidate on the same leaf."""
    leaf = WriteLeaf(
        leaf_id="child.uq_child",
        table="child",
        unique_index="uq_child",
        tier="B2",
        parent_table="parent",
        parent_fk_column="parent_id",
        rationale="synthetic",
        isolation_level="READ COMMITTED",
        retryable_loser_sqlstates=(),
        isolation_citation=None,
    )
    parent = WriteLeaf(
        leaf_id="parent.uq_parent",
        table="parent",
        unique_index="uq_parent",
        tier="A",
        parent_table=None,
        parent_fk_column=None,
        rationale="synthetic parent",
        isolation_level="READ COMMITTED",
        retryable_loser_sqlstates=(),
        isolation_citation=None,
    )
    cand_a = Candidate(
        "app/repositories/agent_realizations.py", 30, "realize", "orm_add", (leaf.leaf_id,)
    )
    cand_b = Candidate(
        "app/repositories/catalog_admin.py", 71, "register_connector", "orm_add", (leaf.leaf_id,)
    )
    only_a = (
        B2EdgeEvidence(
            candidate_path=cand_a.path,
            candidate_lineno=cand_a.lineno,
            candidate_name=cand_a.name,
            candidate_mechanism=cand_a.mechanism,
            leaf_id=leaf.leaf_id,
            parent_leaf_id=parent.leaf_id,
            parent_creation_citation="app/repositories/agent_realizations.py:63",
        ),
    )
    with pytest.raises(AssertionError, match="register_connector"):
        _assert_b2_edge_evidence((cand_a, cand_b), (leaf, parent), only_a)


_PLAN_A1_LEAF_IDS = frozenset(
    {
        "audit_logs.uq_audit_logs_seq",
        "audit_logs.uq_audit_logs_entry_hash",
        "go_live_decisions.uq_gld_previous",
        "go_live_decisions.uq_gld_entry_hash",
        "go_live_decisions.uq_gld_project_root",
        "go_live_decisions.uq_gld_evaluation",
        "control_loop_events.uq_cle_run_ordinal",
        "control_loop_events.uq_cle_previous",
        "control_loop_events.uq_cle_loop_root",
        "acceptance_criterion_authorship_records.uq_acar_criterion_sequence",
        "acceptance_criterion_authorship_records.uq_acar_supersedes_once",
        "emergency_stop_events.uq_ese_previous",
        "emergency_stop_events.uq_ese_project_root",
        "emergency_stop_events.uq_ese_idempotency",
        "production_preapproval_lifecycle_events.uq_pple_previous",
        "production_preapproval_lifecycle_events.uq_pple_attestation_event",
        "production_preapproval_lifecycle_events.uq_pple_idempotency",
        "budgets.uq_budgets_tenant_id_project_id",
        "autonomy_policies.uq_autonomy_policies_tenant_id_project_id",
        "admin_policy_changes.uq_admin_policy_changes_action",
        "run_checkpoint_writes.uq_run_checkpoint_writes_id",
    }
)


def test_p_inventory_8_every_tier_a_leaf_has_one_subtier() -> None:
    """Inventory test 8: every Tier-A leaf has a collectible node and one A1/A2/A3 subtier."""
    allowed = {"A1", "A2", "A3"}
    tier_a = {leaf.leaf_id for leaf in WRITE_LEAVES if leaf.tier == "A"}
    other = {leaf.leaf_id for leaf in WRITE_LEAVES if leaf.tier != "A"}
    assert set(SUBTIER) == tier_a
    assert set(SUBTIER.values()) <= allowed
    for leaf_id, subtier in SUBTIER.items():
        assert subtier in allowed, leaf_id
    leaked = other & set(SUBTIER)
    assert not leaked, sorted(leaked)
    _assert_pending_empty()
    for leaf_id in tier_a:
        nodes = TIER_A_NODES[leaf_id]
        assert nodes, leaf_id
        for node in nodes:
            assert _node_exists(node), node


def test_p_inventory_9_a1_set_matches_plan() -> None:
    """Inventory test 9: A1 equals plan §0A.3; A2/A3 cardinalities are 38/53."""
    a1 = {leaf_id for leaf_id, subtier in SUBTIER.items() if subtier == "A1"}
    a2 = {leaf_id for leaf_id, subtier in SUBTIER.items() if subtier == "A2"}
    a3 = {leaf_id for leaf_id, subtier in SUBTIER.items() if subtier == "A3"}
    assert a1 == A1_LEAF_IDS == _PLAN_A1_LEAF_IDS
    assert "run_checkpoint_writes.uq_run_checkpoint_writes_id" in a1
    assert len(a2) == 38, len(a2)
    assert len(a3) == 53, len(a3)
    assert len(a1) == 21, len(a1)


_EVIDENCE = Path(".planning/SLICE-83-LEAF-EVIDENCE.md")
_RETRYABLE = ("40001", "40P01")
_S55_LEAF = "go_live_decisions.uq_gld_project_root"


def test_p_inventory_a1_evidence_citations() -> None:
    """Commit 14: every A1 evidence row cites the read and the derived write."""
    body = _EVIDENCE.read_text()
    section = body.split("## 1. Tier A1", 1)[1].split("## 2. Tier A2", 1)[0]
    found = list(re.finditer(r"^### `([^`]+)`", section, flags=re.M))
    ids = [match.group(1) for match in found]
    assert set(ids) == A1_LEAF_IDS == _PLAN_A1_LEAF_IDS
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(section)
        block = section[match.end() : end]
        assert "**Read of committed state**" in block, match.group(1)
        assert "**Derived value written**" in block, match.group(1)


def test_p_mut_17_pending_cannot_hide() -> None:
    """P-MUT-17: a pending real leaf fails final-empty; registered/B1 pending fail union."""
    target = "budgets.uq_budgets_tenant_id_project_id"
    reduced = {key: value for key, value in TIER_A_NODES.items() if key != target}
    hidden = frozenset({target})
    _assert_tier_a_registration(WRITE_LEAVES, reduced, hidden)
    with pytest.raises(AssertionError, match=re.escape(target)):
        _assert_pending_empty(hidden)
    with pytest.raises(AssertionError, match=re.escape(target)):
        _assert_tier_a_registration(WRITE_LEAVES, TIER_A_NODES, frozenset({target}))
    b1 = next(leaf for leaf in WRITE_LEAVES if leaf.tier == "B1")
    with pytest.raises(AssertionError, match=re.escape(b1.leaf_id)):
        _assert_tier_a_registration(WRITE_LEAVES, TIER_A_NODES, frozenset({b1.leaf_id}))


def _assert_s55_node(result: object, retryable: tuple[str, ...]) -> None:
    from tests.slice83_support import TwoWriterResult, assert_no_integrity_error
    from tests.admin_support import pg_state

    assert isinstance(result, TwoWriterResult)
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    if result.w2_error is not None:
        state = pg_state(result.w2_error) if isinstance(result.w2_error, Exception) else None
        assert result.w2_settled == "rolled_back", result.w2_settled
        assert state in retryable, state


async def _gld_first_race(rls_engine, admin_engine, retryable: tuple[str, ...] = _RETRYABLE):
    from app.repositories.go_live_decisions import GoLiveDecisionRepository
    from tests.slice83_a1_ledger_support import seed_gld_evaluations
    from tests.slice83_support import SERIALIZABLE, run_two_writers

    world = await seed_gld_evaluations(admin_engine, count=2)
    eval_a, eval_b = world["evaluations"]

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=SERIALIZABLE,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        retryable_loser_sqlstates=retryable,
        count_sql=(
            "SELECT count(*) FROM go_live_decisions "
            "WHERE tenant_id=:t AND project_id=:p AND previous_decision_id IS NULL"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )


@pytest.mark.asyncio
async def test_p_mut_18_serializable_loser_sqlstate(rls_engine, admin_engine) -> None:
    """P-MUT-18: slice55 loser SQLSTATE is exact; aborted W2 is rolled back, never committed."""
    from tests.admin_support import pg_state

    observed = None
    result = None
    for _ in range(8):
        result = await _gld_first_race(rls_engine, admin_engine)
        _assert_s55_node(result, _RETRYABLE)
        if result.w2_error is not None:
            observed = pg_state(result.w2_error)
            if observed in _RETRYABLE:
                break
    assert result is not None
    assert observed in _RETRYABLE, observed
    assert observed != "23505"
    reduced = tuple(state for state in _RETRYABLE if state != observed)
    with pytest.raises(AssertionError, match=re.escape(str(observed))):
        _assert_s55_node(result, reduced)

    async def commit_aborted(trans, session, w2_error, retryable_loser_sqlstates):
        await trans.commit()
        return "committed"

    with patch("tests.slice83_support.settle_w2_transaction", commit_aborted):
        mutated = None
        for _ in range(8):
            mutated = await _gld_first_race(rls_engine, admin_engine)
            if mutated.w2_error is not None:
                break
        assert mutated is not None
        from tests.slice83_support import assert_no_integrity_error

        assert_no_integrity_error(mutated)
        assert pg_state(mutated.w2_error) in _RETRYABLE if mutated.w2_error else True
        with pytest.raises(AssertionError, match="committed"):
            _assert_s55_node(mutated, _RETRYABLE)
    assert _S55_LEAF in TIER_A_NODES
