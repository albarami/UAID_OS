"""Slice 41 — §9.6 agent replacement / failure policy tests.

Docker-free: the pure §9.6 prescription table + the retry-cap/effective-response ladder +
fail-closed validation of REPORTED failure events (B2/B3) + constants. DB-backed (`db`):
the `agent_failure_events` store + migration 0040 (enum + char_length CHECKs, the B1
provenance lock, composite instance FK, RLS, append-only), the repository
(`record_failure` audit-safety + `evaluate_replacement` decisions), and the
non-executing / bit-stable guards (OD-1/D-41-8). No diagnosis/classifier, no response
execution, no auto-suspend, no LLM.
"""

import dataclasses
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.agents.failure_policy import (
    FAILURE_PATTERNS,
    MAX_DETAIL,
    MAX_EVIDENCE_REF,
    MAX_FAILURE_ATTEMPTS,
    MAX_REPORTED_BY,
    MAX_SOURCE,
    MAX_SUMMARY,
    NO_FAILURES_RESPONSE,
    PRESCRIPTION,
    RESPONSES,
    RULESET_VERSION,
    SEVERITIES,
    SOURCE_PROVENANCES,
    ReplacementDecision,
    effective_response,
    prescribe,
    validate_failure_event,
)
from app.repositories.agent_failures import AgentFailureRepository
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.tenancy import TenantContext, tenant_scope

# --- Pure: constants + the §9.6 table --------------------------------------------


def test_constants():
    assert len(FAILURE_PATTERNS) == 8 and len(set(FAILURE_PATTERNS)) == 8
    assert len(RESPONSES) == 8 and len(set(RESPONSES)) == 8
    assert SEVERITIES == ("low", "medium", "high", "critical")
    # B1 — the only writable provenance tier this slice (the verified tier is future work).
    assert SOURCE_PROVENANCES == ("caller_supplied_unverified",)
    assert MAX_FAILURE_ATTEMPTS == 3  # OD-4 fixed cap
    assert RULESET_VERSION == "slice41.v1"
    # "none" is the no-failure effective value — NOT one of the 8 §9.6 responses.
    assert NO_FAILURES_RESPONSE == "none" and NO_FAILURES_RESPONSE not in RESPONSES
    assert (MAX_SOURCE, MAX_EVIDENCE_REF, MAX_SUMMARY, MAX_DETAIL, MAX_REPORTED_BY) == (
        100,
        200,
        2000,
        8000,
        200,
    )


def test_prescription_is_the_spec_table_verbatim():
    # §9.6 (spec:936-945) — the 8 failure-pattern → response rows, machine values.
    assert PRESCRIPTION == {
        "missing_skill": "create_or_recruit_specialist",
        "weak_instructions": "regenerate_prompt_and_eval",
        "wrong_tools": "update_tool_allowlist_after_security_review",
        "poor_model_performance": "route_to_stronger_model",
        "context_overload": "improve_context_retrieval",
        "repeated_reviewer_rejection": "create_focused_remediation_task",
        "safety_authority_violation": "suspend_and_audit",
        "persistent_inability": "escalate_or_blocker",
    }
    assert set(PRESCRIPTION) == set(FAILURE_PATTERNS)
    assert set(PRESCRIPTION.values()) == set(RESPONSES)
    for pattern in FAILURE_PATTERNS:
        assert prescribe(pattern) == PRESCRIPTION[pattern]


def test_prescribe_unknown_pattern_fails_closed():
    for bad in ("not_a_pattern", "", None, 7):
        with pytest.raises(ValueError):
            prescribe(bad)


# --- Pure: effective_response ladder ----------------------------------------------


def test_effective_response_none_when_no_failures():
    assert effective_response(attempt_count=0, latest_pattern=None) == NO_FAILURES_RESPONSE


def test_effective_response_safety_is_immediate():
    # D-41-6 — safety wins regardless of count (a RECOMMENDATION; nothing is executed).
    assert (
        effective_response(attempt_count=1, latest_pattern="safety_authority_violation")
        == "suspend_and_audit"
    )
    assert (
        effective_response(attempt_count=5, latest_pattern="safety_authority_violation")
        == "suspend_and_audit"
    )


def test_effective_response_budget_exhausted_escalates():
    # D-41-5 — attempt_count >= MAX_FAILURE_ATTEMPTS ⇒ escalate_or_blocker (a DECISION).
    assert (
        effective_response(attempt_count=3, latest_pattern="weak_instructions")
        == "escalate_or_blocker"
    )
    assert (
        effective_response(attempt_count=4, latest_pattern="missing_skill") == "escalate_or_blocker"
    )


def test_effective_response_persistent_inability_escalates():
    assert (
        effective_response(attempt_count=1, latest_pattern="persistent_inability")
        == "escalate_or_blocker"
    )


def test_effective_response_otherwise_prescribes():
    assert (
        effective_response(attempt_count=1, latest_pattern="weak_instructions")
        == "regenerate_prompt_and_eval"
    )
    assert (
        effective_response(attempt_count=2, latest_pattern="context_overload")
        == "improve_context_retrieval"
    )


def test_effective_response_fails_closed_on_inconsistent_input():
    for kwargs in (
        dict(attempt_count=0, latest_pattern="weak_instructions"),  # 0 failures with a pattern
        dict(attempt_count=1, latest_pattern=None),  # failures without a pattern
        dict(attempt_count=-1, latest_pattern=None),
        dict(attempt_count=True, latest_pattern="weak_instructions"),  # bool is not a count
        dict(attempt_count="3", latest_pattern="weak_instructions"),
        dict(attempt_count=1, latest_pattern="nope"),
    ):
        with pytest.raises(ValueError):
            effective_response(**kwargs)


# --- Pure: validate_failure_event (B2/B3 fail-closed) ------------------------------


def _event(**over):
    kwargs = dict(
        failure_pattern="weak_instructions",
        severity="medium",
        source="ci",
        reported_by="operator",
        evidence_ref=None,
        summary=None,
        detail=None,
        source_provenance="caller_supplied_unverified",
    )
    kwargs.update(over)
    return kwargs


def test_validate_failure_event_ok():
    validate_failure_event(**_event())  # minimal
    validate_failure_event(  # every text field exactly at its cap (B3 boundaries)
        **_event(
            source="s" * MAX_SOURCE,
            reported_by="r" * MAX_REPORTED_BY,
            evidence_ref="e" * MAX_EVIDENCE_REF,
            summary="m" * MAX_SUMMARY,
            detail="d" * MAX_DETAIL,
        )
    )
    # padded-but-non-blank values are legitimate — only BLANK-after-strip is refused
    validate_failure_event(**_event(source=" ci ", summary=" padded "))


def test_validate_failure_event_rejects_bad_inputs():
    bad = [
        _event(failure_pattern="not_a_pattern"),
        _event(failure_pattern=""),
        _event(failure_pattern=None),
        _event(severity="urgent"),
        _event(severity=None),
        _event(source_provenance="connector_verified"),  # B1 — locked this slice
        _event(source_provenance=""),
        _event(source=""),
        _event(source="s" * (MAX_SOURCE + 1)),
        _event(source=None),
        _event(source=7),
        _event(reported_by=""),
        _event(reported_by="r" * (MAX_REPORTED_BY + 1)),
        _event(reported_by=None),
        _event(evidence_ref=""),  # optional fields: None or a bounded non-blank str
        _event(evidence_ref="e" * (MAX_EVIDENCE_REF + 1)),
        _event(evidence_ref=9),
        _event(summary=""),
        _event(summary="m" * (MAX_SUMMARY + 1)),
        _event(detail=""),
        _event(detail="d" * (MAX_DETAIL + 1)),
        # B1/B3 review round 1 — whitespace-only is BLANK provenance/text, refused per field
        _event(source=" "),
        _event(source="   "),
        _event(source="\t"),
        _event(source="\n"),
        _event(reported_by=" "),
        _event(reported_by="\t\n"),
        _event(evidence_ref=" "),
        _event(evidence_ref="\t"),
        _event(summary=" "),
        _event(summary=" \r\n "),
        _event(detail=" "),
        _event(detail="\x0b\x0c"),
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            validate_failure_event(**kwargs)


# --- Pure: ReplacementDecision -----------------------------------------------------


def test_replacement_decision_to_dict_and_frozen():
    decision = ReplacementDecision(
        instance_id="i-1",
        attempt_count=3,
        latest_pattern="weak_instructions",
        prescribed_response="regenerate_prompt_and_eval",
        budget_exhausted=True,
        effective_response="escalate_or_blocker",
    )
    assert decision.to_dict() == {
        "instance_id": "i-1",
        "attempt_count": 3,
        "latest_pattern": "weak_instructions",
        "prescribed_response": "regenerate_prompt_and_eval",
        "budget_exhausted": True,
        "effective_response": "escalate_or_blocker",
        "ruleset_version": "slice41.v1",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.attempt_count = 9


# --- DB-backed: fixture (mirrors test_factory.ar_ctx) -------------------------------

_H = "sha256:" + "a" * 64


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def afe_ctx(admin_engine):
    """A global blueprint+version; t1/p1 with TWO instances (per-instance isolation);
    t2/px with one instance (cross-project/cross-tenant composite-FK + RLS probes)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('FpOrg',:s) RETURNING id",
            s=f"fp-org-{sfx}",
        )
        t1 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"fp-t1-{sfx}",
        )
        t2 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"fp-t2-{sfx}",
        )
        p1 = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
            t=t1,
            s=f"fp-p1-{sfx}",
        )
        px = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"fp-px-{sfx}",
        )
        bp = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) "
            "VALUES (:k,'Builder','build','builder') RETURNING id",
            k=f"fp-builder-{sfx}",
        )
        ver = await _scalar(
            c,
            "INSERT INTO agent_versions (blueprint_id, version_label, model_route, prompt_hash, "
            "tool_policy_hash, context_policy_hash, eval_suite_hash, critical_dependencies_hash, "
            "output_schema_hash, content_hash) "
            "VALUES (:b,'v1','m',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=bp,
            h=_H,
            ch="sha256:" + sfx + "0" * (64 - len(sfx)),
        )
        inst1 = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) "
            "VALUES (:t,:p,:v,:k) RETURNING id",
            t=t1,
            p=p1,
            v=ver,
            k=f"fk1{sfx}",
        )
        inst2 = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) "
            "VALUES (:t,:p,:v,:k) RETURNING id",
            t=t1,
            p=p1,
            v=ver,
            k=f"fk2{sfx}",
        )
        inst_px = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) "
            "VALUES (:t,:p,:v,:k) RETURNING id",
            t=t2,
            p=px,
            v=ver,
            k=f"fkx{sfx}",
        )
    return {
        "t1": t1,
        "t2": t2,
        "p1": p1,
        "px": px,
        "inst1": inst1,
        "inst2": inst2,
        "inst_px": inst_px,
        "sfx": sfx,
    }


_INSERT_EVENT = (
    "INSERT INTO agent_failure_events (tenant_id, project_id, instance_id, failure_pattern, "
    "severity, source, source_provenance, evidence_ref, summary, detail, reported_by) "
    "VALUES (:t,:p,:i,:fp,:sev,:src,:prov,:ev,:su,:de,:rb) RETURNING id"
)


async def _insert_event(conn, ctx, **over):
    params = {
        "t": str(ctx["t1"]),
        "p": str(ctx["p1"]),
        "i": str(ctx["inst1"]),
        "fp": "weak_instructions",
        "sev": "medium",
        "src": "ci",
        "prov": "caller_supplied_unverified",
        "ev": None,
        "su": None,
        "de": None,
        "rb": "operator",
    }
    params.update(over)
    return await _scalar(conn, _INSERT_EVENT, **params)


# --- DB-backed: store (migration 0040 CHECKs / FK / RLS / append-only) ---------------


@pytest.mark.db
async def test_db_insert_ok_and_bad_enums_rejected(admin_engine, afe_ctx):
    async with admin_engine.begin() as c:
        eid = await _insert_event(c, afe_ctx)
    assert eid is not None
    for over in (
        {"fp": "not_a_pattern"},
        {"sev": "urgent"},
    ):
        with pytest.raises(Exception, match="ck_agent_failure_events|violates check"):
            async with admin_engine.begin() as c:
                await _insert_event(c, afe_ctx, **over)


@pytest.mark.db
async def test_db_source_provenance_locked(admin_engine, afe_ctx):
    # B1 — the DB CHECK locks the provenance tier to caller_supplied_unverified this slice.
    with pytest.raises(Exception, match="ck_agent_failure_events|violates check"):
        async with admin_engine.begin() as c:
            await _insert_event(c, afe_ctx, prov="connector_verified")


@pytest.mark.db
async def test_db_char_length_bounds_rejected(admin_engine, afe_ctx):
    # B3 — every user text field is bounded by a DB CHECK: empty, oversized, AND
    # whitespace-only (blank-after-btrim — B1/B3 review round 1) are all refused.
    for over in (
        {"src": ""},
        {"src": "s" * (MAX_SOURCE + 1)},
        {"rb": ""},
        {"rb": "r" * (MAX_REPORTED_BY + 1)},
        {"ev": ""},
        {"ev": "e" * (MAX_EVIDENCE_REF + 1)},
        {"su": ""},
        {"su": "m" * (MAX_SUMMARY + 1)},
        {"de": ""},
        {"de": "d" * (MAX_DETAIL + 1)},
        {"src": " "},
        {"src": "\t"},
        {"src": "\n"},
        {"rb": "  "},
        {"rb": "\t\n"},
        {"ev": " "},
        {"su": " \r\n "},
        {"de": "\x0b\x0c"},
    ):
        with pytest.raises(Exception, match="ck_agent_failure_events|violates check"):
            async with admin_engine.begin() as c:
                await _insert_event(c, afe_ctx, **over)


@pytest.mark.db
async def test_db_cross_project_instance_fk_rejected(admin_engine, afe_ctx):
    # the composite FK (instance_id, project_id, tenant_id) → agent_instances rejects an
    # instance that belongs to another project/tenant.
    with pytest.raises(Exception, match="foreign key|instance_project_tenant"):
        async with admin_engine.begin() as c:
            await _insert_event(c, afe_ctx, i=str(afe_ctx["inst_px"]))


@pytest.mark.db
async def test_db_rls_cross_tenant(rls_engine, afe_ctx):
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(afe_ctx["t1"])}
        )
        eid = await _insert_event(conn, afe_ctx)
        await conn.commit()
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(afe_ctx["t2"])}
        )
        n = (
            await conn.execute(
                text("SELECT count(*) FROM agent_failure_events WHERE id=:i"), {"i": str(eid)}
            )
        ).scalar_one()
        assert n == 0


@pytest.mark.db
async def test_db_append_only_blocks_update_delete(admin_engine, afe_ctx):
    # the block triggers stop even the admin role (append-only; the events ARE the audit trail).
    async with admin_engine.begin() as c:
        eid = await _insert_event(c, afe_ctx)
    for sql in (
        "UPDATE agent_failure_events SET severity='low' WHERE id=:i",
        "DELETE FROM agent_failure_events WHERE id=:i",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), {"i": str(eid)})


@pytest.mark.db
async def test_db_uaid_app_lacks_update_delete_grant(rls_engine, afe_ctx):
    # the RUNTIME role has SELECT/INSERT only — UPDATE/DELETE denied at the privilege layer,
    # distinct from the append-only trigger above.
    for sql in (
        "UPDATE agent_failure_events SET severity='low'",
        "DELETE FROM agent_failure_events",
    ):
        with pytest.raises(Exception, match="permission denied"):
            async with rls_engine.connect() as conn:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, false)"),
                    {"t": str(afe_ctx["t1"])},
                )
                await conn.execute(text(sql))
                await conn.commit()


# --- DB-backed: repository (record_failure) -----------------------------------------


@pytest.mark.db
async def test_record_failure_inserts_and_audits_safe_metadata(afe_ctx, admin_engine):
    ctx = TenantContext(afe_ctx["t1"])
    secret = "SENSITIVE-detail-must-not-leak"
    async with tenant_scope(ctx) as session:
        event = await AgentFailureRepository(session, ctx).record_failure(
            instance_id=afe_ctx["inst1"],
            failure_pattern="weak_instructions",
            severity="medium",
            source="ci",
            reported_by="operator",
            evidence_ref="run:123",
            summary="agent kept looping",
            detail=secret,
        )
        eid = event.id
        assert event.project_id == afe_ctx["p1"]  # derived from the instance, not caller input
        assert event.source_provenance == "caller_supplied_unverified"
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"agent_failure_event:{eid}", "t": afe_ctx["t1"]},
            )
        ).one()
    assert actor == "operator"
    blob = str(payload)
    assert secret not in blob and "agent kept looping" not in blob and "run:123" not in blob
    assert "summary" not in payload and "detail" not in payload and "evidence_ref" not in payload
    assert payload["failure_pattern"] == "weak_instructions"
    assert payload["severity"] == "medium"
    assert payload["source"] == "ci"
    assert payload["source_provenance"] == "caller_supplied_unverified"


@pytest.mark.db
async def test_record_failure_refuses_invalid_event_and_unknown_instance(afe_ctx):
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = AgentFailureRepository(session, ctx)
        with pytest.raises(ValueError, match="failure_pattern"):
            await repo.record_failure(
                instance_id=afe_ctx["inst1"],
                failure_pattern="not_a_pattern",
                severity="medium",
                source="ci",
                reported_by="operator",
            )
        for bad_instance in (uuid.uuid4(), afe_ctx["inst_px"]):  # unknown + cross-tenant
            with pytest.raises(ValueError, match="unknown instance"):
                await repo.record_failure(
                    instance_id=bad_instance,
                    failure_pattern="weak_instructions",
                    severity="medium",
                    source="ci",
                    reported_by="operator",
                )


# --- DB-backed: evaluate_replacement (compute-on-read decision) ----------------------


async def _record_n(session, ctx, afe_ctx, n, pattern, instance=None):
    repo = AgentFailureRepository(session, ctx)
    for _ in range(n):
        await repo.record_failure(
            instance_id=instance or afe_ctx["inst1"],
            failure_pattern=pattern,
            severity="medium",
            source="ci",
            reported_by="operator",
        )
    return repo


@pytest.mark.db
async def test_evaluate_replacement_none_when_no_failures(afe_ctx):
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = AgentFailureRepository(session, ctx)
        for iid in (afe_ctx["inst1"], uuid.uuid4()):  # real-no-failures + unknown (no leak)
            d = await repo.evaluate_replacement(iid)
            assert d.attempt_count == 0 and d.latest_pattern is None
            assert d.prescribed_response is None and d.budget_exhausted is False
            assert d.effective_response == NO_FAILURES_RESPONSE
            assert d.ruleset_version == RULESET_VERSION


@pytest.mark.db
async def test_evaluate_replacement_prescribes_after_one(afe_ctx):
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 1, "weak_instructions")
        d = await repo.evaluate_replacement(afe_ctx["inst1"])
    assert d.attempt_count == 1 and d.latest_pattern == "weak_instructions"
    assert d.prescribed_response == "regenerate_prompt_and_eval"
    assert d.budget_exhausted is False
    assert d.effective_response == "regenerate_prompt_and_eval"


@pytest.mark.db
async def test_evaluate_replacement_latest_pattern_wins(afe_ctx):
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 1, "weak_instructions")
        await _record_n(session, ctx, afe_ctx, 1, "wrong_tools")
        d = await repo.evaluate_replacement(afe_ctx["inst1"])
    assert d.attempt_count == 2 and d.latest_pattern == "wrong_tools"
    assert d.effective_response == "update_tool_allowlist_after_security_review"


@pytest.mark.db
async def test_evaluate_replacement_budget_exhausted_escalates(afe_ctx):
    # D-41-5 — the retry cap is enforced AS A DECISION (escalate_or_blocker), never an action.
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 3, "weak_instructions")
        d = await repo.evaluate_replacement(afe_ctx["inst1"])
    assert d.attempt_count == 3 and d.budget_exhausted is True
    assert d.prescribed_response == "regenerate_prompt_and_eval"  # the §9.6 row, kept visible
    assert d.effective_response == "escalate_or_blocker"


@pytest.mark.db
async def test_evaluate_replacement_safety_immediate(afe_ctx):
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 1, "safety_authority_violation")
        d = await repo.evaluate_replacement(afe_ctx["inst1"])
    assert d.attempt_count == 1 and d.budget_exhausted is False
    assert d.effective_response == "suspend_and_audit"  # a RECOMMENDATION — nothing executed


@pytest.mark.db
async def test_evaluate_replacement_per_instance_isolation(afe_ctx):
    # OD-2 — the failure budget is per-INSTANCE: inst1's failures never touch inst2.
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 3, "weak_instructions")
        d1 = await repo.evaluate_replacement(afe_ctx["inst1"])
        d2 = await repo.evaluate_replacement(afe_ctx["inst2"])
        assert await repo.attempt_count(afe_ctx["inst1"]) == 3
        assert await repo.attempt_count(afe_ctx["inst2"]) == 0
        assert len(await repo.failures_for(afe_ctx["inst1"])) == 3
    assert d1.effective_response == "escalate_or_blocker"
    assert d2.effective_response == NO_FAILURES_RESPONSE


# --- DB-backed: non-executing / bit-stable (OD-1 / D-41-8) ---------------------------


@pytest.mark.db
async def test_non_executing_and_bit_stable_for_a5(afe_ctx, admin_engine):
    # Recording failures + evaluating the decision executes NOTHING: the instance status is
    # untouched (no auto-suspend, OD-1) and the A5 report is byte-identical (D-41-8).
    ctx = TenantContext(afe_ctx["t1"])
    async with tenant_scope(ctx) as session:
        before = (
            await ProductionAutonomyRepository(session, ctx).evaluate(afe_ctx["p1"])
        ).to_dict()
    async with tenant_scope(ctx) as session:
        repo = await _record_n(session, ctx, afe_ctx, 3, "weak_instructions")
        await _record_n(session, ctx, afe_ctx, 1, "safety_authority_violation")
        d = await repo.evaluate_replacement(afe_ctx["inst1"])
        assert d.effective_response == "suspend_and_audit"  # recommended, NOT executed
    async with admin_engine.connect() as c:
        status = (
            await c.execute(
                text("SELECT status FROM agent_instances WHERE id=:i"),
                {"i": str(afe_ctx["inst1"])},
            )
        ).scalar_one()
    assert status == "registered"  # untouched — no auto-suspend (OD-1)
    async with tenant_scope(ctx) as session:
        after = (await ProductionAutonomyRepository(session, ctx).evaluate(afe_ctx["p1"])).to_dict()
    assert before == after  # bit-stable — no A5 gate flip
    assert before["a5_satisfied"] is False and before["can_go_live_autonomously"] is False
