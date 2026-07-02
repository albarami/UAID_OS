"""Slice 42 — task contracts + maker-checker-verifier workflow + reviewer reports tests.

Docker-free: the pure §27.2 contract validators (bounds/known-tools/disjointness, B3-style
non-blank), the §12.3-subset lifecycle matrix (internal/board/terminal vocabularies + the
V2-B1 invariant), the §13.3 verdict validators (no ``can_merge`` input — V2-B2), and the
per-REGISTRATION done-gate decision. DB-backed (`db`): the 5-table migration 0041 store
(FK-proven spine links + §2.2 blueprint-distinct reviewer registry + registration-bound
immutable reports with a GENERATED ``can_merge`` + the guarded lifecycle incl. the done-gate
+ the fully-specified event trail), the repositories, and the non-executing / bit-stable
guards. No review execution, no LLM, no oracle/shortcut/acceptance subsystems.
"""

import dataclasses
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.pm_issues import _SPEC_COLUMNS
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.repositories.review_reports import ReviewReportRepository
from app.repositories.task_contracts import TaskContractRepository
from app.tenancy import TenantContext, tenant_scope
from app.review.task_contracts import (
    ARTIFACT_LINK_KINDS,
    MAX_DESCRIPTION,
    MAX_ITEM_CHARS,
    MAX_LIST_ITEMS,
    MAX_REVIEWERS,
    MAX_TASK_REF,
    MAX_TITLE,
    MAX_TOOLS,
    REVIEW_LAYERS,
    RISK_LEVELS,
    validate_artifact_link,
    validate_new_contract,
)
from app.review.workflow import (
    BOARD_STATUSES,
    CONTRACT_STATUSES,
    INTERNAL_STATUSES,
    MAX_REPORT_SOURCE,
    MAX_SUMMARY,
    REPORTABLE_STATUSES,
    RULESET_VERSION,
    SOURCE_PROVENANCES,
    TERMINAL_STATUSES,
    VERDICTS,
    RegistrationView,
    evaluate_done_gate,
    validate_review_report,
    validate_transition,
)

# --- Pure: constants + the V2-B1 vocabulary invariant -------------------------------


def test_status_vocabularies_and_invariant():
    assert INTERNAL_STATUSES == ("draft",)  # internal pre-board assembly status (NOT §12.3)
    assert BOARD_STATUSES == (
        "ready_for_development",
        "in_progress",
        "specialist_review",
        "changes_requested",
        "done",
    )
    assert TERMINAL_STATUSES == ("canceled", "superseded")  # lifecycle terminals (NOT §12.3)
    assert CONTRACT_STATUSES == INTERNAL_STATUSES + BOARD_STATUSES + TERMINAL_STATUSES
    # V2-B1 — only the five board statuses are §12.3 columns; the invariant is over the union.
    assert set(BOARD_STATUSES) <= set(_SPEC_COLUMNS)
    assert set(CONTRACT_STATUSES) <= (
        set(_SPEC_COLUMNS) | set(TERMINAL_STATUSES) | set(INTERNAL_STATUSES)
    )
    assert not (set(INTERNAL_STATUSES) | set(TERMINAL_STATUSES)) & set(_SPEC_COLUMNS)


def test_constants():
    assert RISK_LEVELS == ("low", "medium", "high", "critical")
    assert REVIEW_LAYERS == ("role_specific", "cross_functional", "acceptance")
    assert ARTIFACT_LINK_KINDS == {
        "source_requirement": "requirement",
        "acceptance_criterion": "acceptance_criterion",
        "test_oracle": "test_oracle",
    }
    assert VERDICTS == ("approved", "rejected_with_required_changes")
    assert REPORTABLE_STATUSES == ("in_progress", "specialist_review", "changes_requested")
    assert SOURCE_PROVENANCES == ("caller_supplied_unverified",)
    assert RULESET_VERSION == "slice42.v1"
    assert (MAX_TASK_REF, MAX_TITLE, MAX_DESCRIPTION) == (64, 200, 4000)
    assert (MAX_LIST_ITEMS, MAX_ITEM_CHARS) == (32, 500)
    assert (MAX_TOOLS, MAX_REVIEWERS) == (64, 16)  # factory parity
    assert (MAX_SUMMARY, MAX_REPORT_SOURCE) == (2000, 100)


def test_validate_artifact_link():
    for kind in ARTIFACT_LINK_KINDS:
        validate_artifact_link(kind)  # no raise
    for bad in ("requirement", "", None, 7):  # spine kinds are NOT link kinds
        with pytest.raises(ValueError):
            validate_artifact_link(bad)


# --- Pure: validate_new_contract ------------------------------------------------------


def _contract(**over):
    kwargs = dict(
        task_ref="AUTH-013",
        title="Implement user login",
        description="Login per the §13.2 example.",
        must_have=["User can log in with email and password"],
        must_not_do=["Do not use fake authentication"],
        required_evidence=["unit tests"],
        definition_of_done=["all ACs demonstrated"],
        allowed_tools=["ci.run_tests"],
        forbidden_tools=["ci.deploy_production"],
        risk_level="medium",
    )
    kwargs.update(over)
    return kwargs


def test_validate_new_contract_ok():
    validate_new_contract(**_contract())
    validate_new_contract(  # at the caps; empty lists allowed; padded-but-non-blank ok
        **_contract(
            task_ref="A" * MAX_TASK_REF,
            title=" t" + "x" * (MAX_TITLE - 2),
            description="d" * MAX_DESCRIPTION,
            must_have=["m" * MAX_ITEM_CHARS] * MAX_LIST_ITEMS,
            must_not_do=[],
            required_evidence=[],
            definition_of_done=[],
            allowed_tools=[],
            forbidden_tools=[],
        )
    )


def test_validate_new_contract_rejects_bad_inputs():
    bad = [
        _contract(task_ref=""),
        _contract(task_ref="-starts-bad"),
        _contract(task_ref="A" * (MAX_TASK_REF + 1)),
        _contract(task_ref=None),
        _contract(title=""),
        _contract(title=" "),  # whitespace-only (non-blank rule)
        _contract(title="t" * (MAX_TITLE + 1)),
        _contract(description=""),
        _contract(description="\t\n"),
        _contract(description="d" * (MAX_DESCRIPTION + 1)),
        _contract(risk_level="urgent"),
        _contract(risk_level=None),
        _contract(must_have="not-a-list"),
        _contract(must_have=[7]),
        _contract(must_have=[""]),
        _contract(must_have=[" "]),  # whitespace-only item
        _contract(must_have=["m" * (MAX_ITEM_CHARS + 1)]),
        _contract(must_have=["x"] * (MAX_LIST_ITEMS + 1)),
        _contract(must_not_do=[" \r\n "]),
        _contract(required_evidence=["\x0b"]),
        _contract(definition_of_done=[None]),
        _contract(allowed_tools=["nope.not_a_real_tool"]),  # UNKNOWN tool (broker registry)
        _contract(forbidden_tools=["nope.not_a_real_tool"]),
        _contract(allowed_tools=["ci.run_tests"], forbidden_tools=["ci.run_tests"]),  # overlap
        _contract(allowed_tools=["ci.run_tests"] * (MAX_TOOLS + 1)),
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            validate_new_contract(**kwargs)


# --- Pure: transition matrix (D-42-5 / V2-B1 terminals) -------------------------------

_LEGAL = [
    ("draft", "ready_for_development"),
    ("ready_for_development", "in_progress"),
    ("in_progress", "specialist_review"),
    ("specialist_review", "changes_requested"),
    ("changes_requested", "in_progress"),
    ("specialist_review", "done"),
    ("draft", "canceled"),
    ("ready_for_development", "canceled"),
    ("in_progress", "canceled"),
    ("specialist_review", "canceled"),
    ("changes_requested", "canceled"),
    ("done", "superseded"),  # done is NOT terminal — exactly one outgoing
]


def test_validate_transition_matrix():
    for current, new in _LEGAL:
        validate_transition(current, new)  # no raise
    illegal = [
        ("done", "canceled"),  # refused (B2 ruling)
        ("done", "in_progress"),  # no reopen
        ("canceled", "superseded"),  # terminals: no outgoing
        ("superseded", "done"),
        ("canceled", "canceled"),  # same-status no-op refused
        ("draft", "draft"),
        ("draft", "in_progress"),  # cannot skip ready
        ("draft", "done"),
        ("ready_for_development", "done"),
        ("in_progress", "done"),  # done only from specialist_review
        ("changes_requested", "done"),
        ("draft", "superseded"),  # superseded only from done
        ("in_progress", "ready_for_development"),  # no backward
        ("nope", "done"),
        ("draft", "nope"),
    ]
    for current, new in illegal:
        with pytest.raises(ValueError):
            validate_transition(current, new)


# --- Pure: validate_review_report (§13.3; V2-B2 no can_merge input) --------------------


def _report(**over):
    kwargs = dict(
        verdict="rejected_with_required_changes",
        summary="Implementation accepts any password for existing emails.",
        failed_criteria=["Invalid credentials are rejected"],
        suspected_shortcuts=["success without hash comparison"],
        required_changes=["Implement password hash verification"],
        source="reviewer_run",
        source_provenance="caller_supplied_unverified",
    )
    kwargs.update(over)
    return kwargs


def test_validate_review_report_ok():
    validate_review_report(**_report())  # rejected: failed + changes non-empty
    validate_review_report(  # approved: ALL lists empty (a suspected shortcut ≠ approval)
        **_report(
            verdict="approved",
            failed_criteria=[],
            suspected_shortcuts=[],
            required_changes=[],
        )
    )


def test_validate_review_report_has_no_can_merge_input():
    # V2-B2 — can_merge is DB-GENERATED, never an input.
    with pytest.raises(TypeError):
        validate_review_report(**_report(), can_merge=True)


def test_validate_review_report_rejects_bad_inputs():
    bad = [
        _report(verdict="REJECTED"),  # not a machine value
        _report(verdict=None),
        _report(verdict="approved"),  # approved with non-empty lists (defaults) — refused
        _report(verdict="approved", failed_criteria=[], suspected_shortcuts=[]),  # changes left
        _report(failed_criteria=[]),  # rejected without failed_criteria
        _report(required_changes=[]),  # rejected without required_changes
        _report(summary=""),
        _report(summary="   "),
        _report(summary="s" * (MAX_SUMMARY + 1)),
        _report(source=""),
        _report(source="\t"),
        _report(source="s" * (MAX_REPORT_SOURCE + 1)),
        _report(source_provenance="connector_verified"),  # locked this slice
        _report(failed_criteria="not-a-list"),
        _report(failed_criteria=[7]),
        _report(failed_criteria=[" "]),
        _report(failed_criteria=["f" * (MAX_ITEM_CHARS + 1)]),
        _report(suspected_shortcuts=["x"] * (MAX_LIST_ITEMS + 1)),
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            validate_review_report(**kwargs)


# --- Pure: the per-REGISTRATION done-gate (B1 option (b)) ------------------------------


def _regs(*triples):
    return [RegistrationView(layer=la, reviewer_ref=r, latest_verdict=v) for la, r, v in triples]


def test_done_gate_eligible_when_every_registration_approved():
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "r1", "approved"),
            ("cross_functional", "r2", "approved"),
            ("acceptance", "r3", "approved"),
        )
    )
    assert decision.eligible is True
    assert decision.missing_layers == ()
    assert decision.pending_registrations == ()
    assert decision.rejected_registrations == ()
    assert decision.ruleset_version == RULESET_VERSION


def test_done_gate_pending_registration_blocks():
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "r1", "approved"),
            ("cross_functional", "r2", None),  # registered, no report yet
            ("acceptance", "r3", "approved"),
        )
    )
    assert decision.eligible is False
    assert decision.pending_registrations == (("cross_functional", "r2"),)


def test_done_gate_same_layer_approval_cannot_bury_a_rejection():
    # The v2-B1 bypass case: A rejected, B approved in the SAME layer ⇒ NOT eligible.
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "reviewer_a", "rejected_with_required_changes"),
            ("role_specific", "reviewer_b", "approved"),
            ("cross_functional", "r2", "approved"),
            ("acceptance", "r3", "approved"),
        )
    )
    assert decision.eligible is False
    assert decision.rejected_registrations == (("role_specific", "reviewer_a"),)


def test_done_gate_same_reviewer_reapproval_clears_their_rejection():
    # A's OWN latest became approved ⇒ eligible (latest is per registration).
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "reviewer_a", "approved"),
            ("role_specific", "reviewer_b", "approved"),
            ("cross_functional", "r2", "approved"),
            ("acceptance", "r3", "approved"),
        )
    )
    assert decision.eligible is True


def test_done_gate_missing_layer_blocks():
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "r1", "approved"),
            ("acceptance", "r3", "approved"),
        )
    )
    assert decision.eligible is False
    assert decision.missing_layers == ("cross_functional",)


def test_done_gate_fails_closed_and_to_dict():
    with pytest.raises(ValueError):
        evaluate_done_gate(_regs(("nope_layer", "r1", "approved")))
    with pytest.raises(ValueError):
        evaluate_done_gate(_regs(("acceptance", "r1", "MAYBE")))
    decision = evaluate_done_gate(
        _regs(
            ("role_specific", "r1", None),
            ("cross_functional", "r2", "rejected_with_required_changes"),
        )
    )
    assert decision.to_dict() == {
        "eligible": False,
        "missing_layers": ["acceptance"],
        "pending_registrations": [["role_specific", "r1"]],
        "rejected_registrations": [["cross_functional", "r2"]],
        "ruleset_version": "slice42.v1",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.eligible = True


# --- DB-backed: fixture ---------------------------------------------------------------

_H = "sha256:" + "a" * 64


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def tc_ctx(admin_engine):
    """t1/p1: a builder instance + four reviewer instances (distinct blueprint) + one
    builder-blueprint 'reviewer' (the §2.2 probe) + spine artifacts (req/AC/oracle);
    t2/px: a cross-tenant instance + artifact for FK/RLS probes."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('TcOrg',:s) RETURNING id",
            s=f"tc-org-{sfx}",
        )
        t1 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"tc-t1-{sfx}",
        )
        t2 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"tc-t2-{sfx}",
        )
        p1 = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
            t=t1,
            s=f"tc-p1-{sfx}",
        )
        px = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"tc-px-{sfx}",
        )
        bp_builder = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) "
            "VALUES (:k,'Builder','build','builder') RETURNING id",
            k=f"tc-builder-{sfx}",
        )
        bp_rev = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) "
            "VALUES (:k,'Reviewer','review','reviewer') RETURNING id",
            k=f"tc-reviewer-{sfx}",
        )
        ver_b = await _scalar(
            c,
            "INSERT INTO agent_versions (blueprint_id, version_label, model_route, prompt_hash, "
            "tool_policy_hash, context_policy_hash, eval_suite_hash, critical_dependencies_hash, "
            "output_schema_hash, content_hash) "
            "VALUES (:b,'v1','m',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=bp_builder,
            h=_H,
            ch="sha256:b" + sfx + "0" * (63 - len(sfx)),
        )
        ver_r = await _scalar(
            c,
            "INSERT INTO agent_versions (blueprint_id, version_label, model_route, prompt_hash, "
            "tool_policy_hash, context_policy_hash, eval_suite_hash, critical_dependencies_hash, "
            "output_schema_hash, content_hash) "
            "VALUES (:b,'v1','m',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=bp_rev,
            h=_H,
            ch="sha256:c" + sfx + "0" * (63 - len(sfx)),
        )

        async def _inst(tenant, project, version, key):
            return await _scalar(
                c,
                "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) "
                "VALUES (:t,:p,:v,:k) RETURNING id",
                t=tenant,
                p=project,
                v=version,
                k=key,
            )

        builder_i = await _inst(t1, p1, ver_b, f"b{sfx}")
        rev_role = await _inst(t1, p1, ver_r, f"rr{sfx}")
        rev_role2 = await _inst(t1, p1, ver_r, f"rr2{sfx}")
        rev_cross = await _inst(t1, p1, ver_r, f"rc{sfx}")
        rev_acc = await _inst(t1, p1, ver_r, f"ra{sfx}")
        builder_like = await _inst(t1, p1, ver_b, f"bl{sfx}")  # §2.2 probe (builder blueprint)
        inst_px = await _inst(t2, px, ver_r, f"px{sfx}")

        async def _art(tenant, project, kind, ref):
            aid = await _scalar(
                c,
                "INSERT INTO intake_artifacts (tenant_id, project_id, kind, ref, title) "
                "VALUES (:t,:p,:k,:r,'a') RETURNING id",
                t=tenant,
                p=project,
                k=kind,
                r=ref,
            )
            await c.execute(
                text(
                    "INSERT INTO intake_provenance (tenant_id, project_id, artifact_id, origin) "
                    "VALUES (:t,:p,:a,'test')"
                ),
                {"t": tenant, "p": project, "a": aid},
            )
            return aid

        req = await _art(t1, p1, "requirement", "REQ-1")
        ac = await _art(t1, p1, "acceptance_criterion", "AC-1")
        oracle = await _art(t1, p1, "test_oracle", "ORA-1")
        req_px = await _art(t2, px, "requirement", "REQ-X")
    return {
        "t1": t1,
        "t2": t2,
        "p1": p1,
        "px": px,
        "builder_i": builder_i,
        "rev_role": rev_role,
        "rev_role2": rev_role2,
        "rev_cross": rev_cross,
        "rev_acc": rev_acc,
        "builder_like": builder_like,
        "inst_px": inst_px,
        "req": req,
        "ac": ac,
        "oracle": oracle,
        "req_px": req_px,
        "sfx": sfx,
    }


async def _create(repo, ctx_d, **over):
    kwargs = dict(
        builder_instance_id=ctx_d["builder_i"],
        task_ref=f"AUTH-{uuid.uuid4().hex[:6]}",
        title="Implement user login",
        description="Login per the §13.2 example.",
        must_have=["User can log in"],
        must_not_do=["No fake auth"],
        required_evidence=["unit tests"],
        definition_of_done=["ACs demonstrated"],
        allowed_tools=["ci.run_tests"],
        forbidden_tools=[],
        risk_level="medium",
        created_by="planner",
    )
    kwargs.update(over)
    return await repo.create(**kwargs)


async def _staffed_contract(session, ctx, ctx_d, *, extra_role_reviewer=False):
    """A draft contract with a requirement link + full 3-layer coverage (optionally a 2nd
    role_specific reviewer)."""
    repo = TaskContractRepository(session, ctx)
    contract = await _create(repo, ctx_d)
    await repo.add_artifact_link(
        contract_id=contract.id,
        link_kind="source_requirement",
        artifact_id=ctx_d["req"],
        actor="planner",
    )
    for inst, layer in (
        (ctx_d["rev_role"], "role_specific"),
        (ctx_d["rev_cross"], "cross_functional"),
        (ctx_d["rev_acc"], "acceptance"),
    ):
        await repo.add_reviewer(
            contract_id=contract.id, reviewer_instance_id=inst, layer=layer, actor="planner"
        )
    if extra_role_reviewer:
        await repo.add_reviewer(
            contract_id=contract.id,
            reviewer_instance_id=ctx_d["rev_role2"],
            layer="role_specific",
            actor="planner",
        )
    return repo, contract


async def _to_review(repo, contract_id, actor="lead"):
    await repo.submit_for_development(contract_id, actor=actor)
    await repo.start(contract_id, actor=actor)
    await repo.submit_for_review(contract_id, actor=actor)


async def _approve(session, ctx, contract_id, reviewer_instance_id, layer):
    return await ReviewReportRepository(session, ctx).record_report(
        contract_id=contract_id,
        reviewer_instance_id=reviewer_instance_id,
        layer=layer,
        verdict="approved",
        summary="meets the contract",
        failed_criteria=[],
        suspected_shortcuts=[],
        required_changes=[],
        source="reviewer_run",
        reported_by="rev",
    )


async def _reject(session, ctx, contract_id, reviewer_instance_id, layer):
    return await ReviewReportRepository(session, ctx).record_report(
        contract_id=contract_id,
        reviewer_instance_id=reviewer_instance_id,
        layer=layer,
        verdict="rejected_with_required_changes",
        summary="accepts any password",
        failed_criteria=["invalid credentials rejected"],
        suspected_shortcuts=[],
        required_changes=["implement hash verification"],
        source="reviewer_run",
        reported_by="rev",
    )


# --- DB-backed: contracts (create / JSONB guards / freeze / FK / uniqueness) -----------


@pytest.mark.db
async def test_db_create_draft_creation_event_and_audit_safe(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    secret = "SENSITIVE-description-must-not-leak"
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx, description=secret, must_have=["SECRET-item"])
        cid = contract.id
        assert contract.status == "draft"
        assert contract.project_id == tc_ctx["p1"]  # derived from the builder instance
    async with admin_engine.connect() as c:
        ev = (
            await c.execute(
                text(
                    "SELECT from_status, to_status FROM task_contract_events "
                    "WHERE task_contract_id=:c ORDER BY created_at, id"
                ),
                {"c": str(cid)},
            )
        ).all()
        assert [tuple(r) for r in ev] == [(None, "draft")]  # the creation event
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"task_contract:{cid}", "t": tc_ctx["t1"]},
            )
        ).one()
    assert actor == "planner"
    blob = str(payload)
    assert secret not in blob and "SECRET-item" not in blob
    assert "description" not in payload and "must_have" not in payload and "title" not in payload
    assert payload["status"] == "draft" and payload["risk_level"] == "medium"


_INSERT_CONTRACT = (
    "INSERT INTO task_contracts (tenant_id, project_id, task_ref, title, description, "
    "must_have, must_not_do, required_evidence, definition_of_done, allowed_tools, "
    "forbidden_tools, risk_level, builder_instance_id) "
    "VALUES (:t,:p,:ref,'T','D',CAST(:mh AS jsonb),'[]','[]','[]',CAST(:at AS jsonb),"
    "CAST(:ft AS jsonb),'low',:b) RETURNING id"
)


@pytest.mark.db
async def test_db_jsonb_guard_refusals(tc_ctx, admin_engine):
    base = {
        "t": str(tc_ctx["t1"]),
        "p": str(tc_ctx["p1"]),
        "b": str(tc_ctx["builder_i"]),
        "mh": "[]",
        "at": "[]",
        "ft": "[]",
    }
    bad = [
        {"mh": '"not-an-array"'},
        {"mh": "[1]"},  # non-string item
        {"mh": '[" "]'},  # blank item (btrim)
        {"mh": "[" + ",".join(['"x"'] * 33) + "]"},  # > 32 items
        {"at": '["ci.run_tests"]', "ft": '["ci.run_tests"]'},  # overlap
    ]
    for over in bad:
        params = {**base, **over, "ref": f"J-{uuid.uuid4().hex[:6]}"}
        with pytest.raises(Exception, match="task_contracts"):
            async with admin_engine.begin() as c:
                await c.execute(text(_INSERT_CONTRACT), params)


@pytest.mark.db
async def test_db_freeze_prereqs_and_content_freeze(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        # no source_requirement link yet ⇒ freeze refused
        with pytest.raises(Exception, match="source_requirement|requirement link"):
            await repo.submit_for_development(contract.id, actor="lead")
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        await repo.add_artifact_link(
            contract_id=contract.id,
            link_kind="source_requirement",
            artifact_id=tc_ctx["req"],
            actor="planner",
        )
        await repo.add_reviewer(  # only ONE layer covered ⇒ freeze refused
            contract_id=contract.id,
            reviewer_instance_id=tc_ctx["rev_role"],
            layer="role_specific",
            actor="planner",
        )
        with pytest.raises(Exception, match="layer"):
            await repo.submit_for_development(contract.id, actor="lead")
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await repo.submit_for_development(contract.id, actor="lead")
        cid = contract.id
    # frozen: content UPDATE, link INSERT, reviewer INSERT all refused post-draft
    with pytest.raises(Exception, match="draft|immutable"):
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE task_contracts SET title='new' WHERE id=:i"), {"i": str(cid)}
            )
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        with pytest.raises(Exception, match="draft"):
            await repo.add_artifact_link(
                contract_id=cid,
                link_kind="acceptance_criterion",
                artifact_id=tc_ctx["ac"],
                actor="planner",
            )
        with pytest.raises(Exception, match="draft"):
            await repo.add_reviewer(
                contract_id=cid,
                reviewer_instance_id=tc_ctx["rev_role2"],
                layer="role_specific",
                actor="planner",
            )


@pytest.mark.db
async def test_db_cross_project_builder_fk_and_unknown_instance(tc_ctx, admin_engine):
    # repo path: a cross-tenant instance is unknown under t1 (tenant-scoped resolution)
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        with pytest.raises(ValueError, match="unknown builder instance"):
            await _create(repo, tc_ctx, builder_instance_id=tc_ctx["inst_px"])
    # DB path: builder FK is composite (instance, project, tenant)
    with pytest.raises(Exception, match="foreign key|builder"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(_INSERT_CONTRACT),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "ref": "FK-1",
                    "b": str(tc_ctx["inst_px"]),
                    "mh": "[]",
                    "at": "[]",
                    "ft": "[]",
                },
            )


@pytest.mark.db
async def test_db_task_ref_unique_per_project(tc_ctx):
    ctx = TenantContext(tc_ctx["t1"])
    ref = f"UNIQ-{tc_ctx['sfx']}"
    async with tenant_scope(ctx) as session:
        await _create(TaskContractRepository(session, ctx), tc_ctx, task_ref=ref)
    with pytest.raises(Exception, match="unique|duplicate"):
        async with tenant_scope(ctx) as session:
            await _create(TaskContractRepository(session, ctx), tc_ctx, task_ref=ref)


# --- DB-backed: links + reviewers (kind guard / FK / §2.2 / uniqueness) -----------------


@pytest.mark.db
async def test_db_wrong_kind_link_refused(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        cid = contract.id
        # repo pre-check: an acceptance_criterion link must point at an AC artifact
        with pytest.raises(ValueError, match="kind"):
            await repo.add_artifact_link(
                contract_id=cid,
                link_kind="acceptance_criterion",
                artifact_id=tc_ctx["req"],
                actor="planner",
            )
    # DB guard backstop (direct SQL)
    with pytest.raises(Exception, match="kind"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO task_contract_artifact_links (tenant_id, project_id, "
                    "task_contract_id, artifact_id, link_kind) VALUES (:t,:p,:c,:a,'test_oracle')"
                ),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "c": str(cid),
                    "a": str(tc_ctx["req"]),
                },
            )


@pytest.mark.db
async def test_db_cross_project_artifact_link_refused(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        cid = contract.id
        with pytest.raises(ValueError, match="unknown artifact"):
            await repo.add_artifact_link(
                contract_id=cid,
                link_kind="source_requirement",
                artifact_id=tc_ctx["req_px"],
                actor="planner",
            )
    with pytest.raises(Exception, match="foreign key|artifact"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO task_contract_artifact_links (tenant_id, project_id, "
                    "task_contract_id, artifact_id, link_kind) "
                    "VALUES (:t,:p,:c,:a,'source_requirement')"
                ),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "c": str(cid),
                    "a": str(tc_ctx["req_px"]),
                },
            )


@pytest.mark.db
async def test_db_self_review_blueprint_refused(tc_ctx, admin_engine):
    # §2.2 — a reviewer whose ACTUAL blueprint equals the builder's is refused (repo AND DB).
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        cid = contract.id
        with pytest.raises(Exception, match="self-review|blueprint"):
            await repo.add_reviewer(
                contract_id=cid,
                reviewer_instance_id=tc_ctx["builder_like"],
                layer="role_specific",
                actor="planner",
            )
    with pytest.raises(Exception, match="self-review|blueprint"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO task_contract_reviewers (tenant_id, project_id, "
                    "task_contract_id, reviewer_instance_id, layer) "
                    "VALUES (:t,:p,:c,:r,'role_specific')"
                ),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "c": str(cid),
                    "r": str(tc_ctx["builder_like"]),
                },
            )


@pytest.mark.db
async def test_db_duplicate_link_and_reviewer_unique(tc_ctx):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        await repo.add_artifact_link(
            contract_id=contract.id,
            link_kind="source_requirement",
            artifact_id=tc_ctx["req"],
            actor="planner",
        )
        with pytest.raises(Exception, match="unique|duplicate"):
            await repo.add_artifact_link(
                contract_id=contract.id,
                link_kind="source_requirement",
                artifact_id=tc_ctx["req"],
                actor="planner",
            )
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        contract = await _create(repo, tc_ctx)
        await repo.add_reviewer(
            contract_id=contract.id,
            reviewer_instance_id=tc_ctx["rev_role"],
            layer="role_specific",
            actor="planner",
        )
        with pytest.raises(Exception, match="unique|duplicate"):
            await repo.add_reviewer(
                contract_id=contract.id,
                reviewer_instance_id=tc_ctx["rev_role"],
                layer="role_specific",
                actor="planner",
            )


# --- DB-backed: review reports (registration FK / window / GENERATED can_merge / CHECKs) --


@pytest.mark.db
async def test_db_report_requires_registration(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        cid = contract.id
        # unregistered reviewer instance ⇒ repo refusal
        with pytest.raises(ValueError, match="registered"):
            await _approve(session, ctx, cid, tc_ctx["rev_role2"], "role_specific")
        # registered reviewer, WRONG layer ⇒ repo refusal (registration is (reviewer, layer))
        with pytest.raises(ValueError, match="registered"):
            await _approve(session, ctx, cid, tc_ctx["rev_role"], "acceptance")
    # DB backstop: the composite registration FK
    with pytest.raises(Exception, match="foreign key|registration"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO review_reports (tenant_id, project_id, task_contract_id, "
                    "reviewer_instance_id, layer, verdict, summary, failed_criteria, "
                    "suspected_shortcuts, required_changes, source) "
                    "VALUES (:t,:p,:c,:r,'acceptance','approved','ok','[]','[]','[]','x')"
                ),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "c": str(cid),
                    "r": str(tc_ctx["rev_role"]),
                },
            )


@pytest.mark.db
async def test_db_report_window_guard(tc_ctx):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        _, contract = await _staffed_contract(session, ctx, tc_ctx)
        cid = contract.id
    # draft ⇒ refused (its own scope: the aborted txn must not eat the setup)
    with pytest.raises(Exception, match="status|reportable"):
        async with tenant_scope(ctx) as session:
            await _approve(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
    async with tenant_scope(ctx) as session:
        await TaskContractRepository(session, ctx).submit_for_development(cid, actor="lead")
    # ready_for_development ⇒ refused
    with pytest.raises(Exception, match="status|reportable"):
        async with tenant_scope(ctx) as session:
            await _approve(session, ctx, cid, tc_ctx["rev_role"], "role_specific")


@pytest.mark.db
async def test_db_can_merge_is_generated_never_writable(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        cid = contract.id
        approved = await _approve(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
        rejected = await _reject(session, ctx, cid, tc_ctx["rev_cross"], "cross_functional")
        approved_id, rejected_id = approved.id, rejected.id
    async with admin_engine.connect() as c:
        rows = dict(
            (
                await c.execute(
                    text("SELECT id, can_merge FROM review_reports WHERE id IN (:a,:r)"),
                    {"a": str(approved_id), "r": str(rejected_id)},
                )
            ).all()
        )
    assert rows[approved_id] is True and rows[rejected_id] is False  # GENERATED from verdict
    # V2-B2 — supplying can_merge directly is refused by Postgres (generated column)
    with pytest.raises(Exception, match="generated|can_merge"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO review_reports (tenant_id, project_id, task_contract_id, "
                    "reviewer_instance_id, layer, verdict, can_merge, summary, failed_criteria, "
                    "suspected_shortcuts, required_changes, source) "
                    "VALUES (:t,:p,:c,:r,'role_specific','rejected_with_required_changes',true,"
                    "'s','[\"f\"]','[]','[\"c\"]','x')"
                ),
                {
                    "t": str(tc_ctx["t1"]),
                    "p": str(tc_ctx["p1"]),
                    "c": str(cid),
                    "r": str(tc_ctx["rev_role"]),
                },
            )


@pytest.mark.db
async def test_db_report_check_refusals(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        cid = contract.id
    base = {
        "t": str(tc_ctx["t1"]),
        "p": str(tc_ctx["p1"]),
        "c": str(cid),
        "r": str(tc_ctx["rev_role"]),
    }
    stmt = (
        "INSERT INTO review_reports (tenant_id, project_id, task_contract_id, "
        "reviewer_instance_id, layer, verdict, summary, failed_criteria, suspected_shortcuts, "
        "required_changes, source, source_provenance) "
        "VALUES (:t,:p,:c,:r,'role_specific',:v,:s,CAST(:fc AS jsonb),CAST(:ss AS jsonb),"
        "CAST(:rc AS jsonb),:src,:prov)"
    )
    ok = {
        "v": "approved",
        "s": "ok",
        "fc": "[]",
        "ss": "[]",
        "rc": "[]",
        "src": "x",
        "prov": "caller_supplied_unverified",
    }
    bad = [
        {"v": "MAYBE"},  # verdict enum
        {"fc": '["f"]'},  # approved with a non-empty list
        {"v": "rejected_with_required_changes"},  # rejected with EMPTY failed/changes
        {"s": "   "},  # whitespace summary
        {"src": "\t"},  # whitespace source
        {"prov": "connector_verified"},  # provenance locked
        {"fc": '[" "]'},  # blank list item (guard)
    ]
    for over in bad:
        with pytest.raises(Exception, match="review_reports|violates check"):
            async with admin_engine.begin() as c:
                await c.execute(text(stmt), {**base, **ok, **over})


@pytest.mark.db
async def test_db_reports_append_only_and_grants(tc_ctx, admin_engine, rls_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        report = await _approve(session, ctx, contract.id, tc_ctx["rev_role"], "role_specific")
        rid = report.id
    for sql in (
        "UPDATE review_reports SET summary='x' WHERE id=:i",
        "DELETE FROM review_reports WHERE id=:i",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), {"i": str(rid)})
    for table in (
        "task_contract_artifact_links",
        "task_contract_reviewers",
        "review_reports",
        "task_contract_events",
    ):
        for sql in (f"UPDATE {table} SET tenant_id = tenant_id", f"DELETE FROM {table}"):
            with pytest.raises(Exception, match="permission denied"):
                async with rls_engine.connect() as conn:
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, false)"),
                        {"t": str(tc_ctx["t1"])},
                    )
                    await conn.execute(text(sql))
                    await conn.commit()


@pytest.mark.db
async def test_db_rls_cross_tenant(tc_ctx, rls_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        await _approve(session, ctx, contract.id, tc_ctx["rev_role"], "role_specific")
        cid = contract.id
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(tc_ctx["t2"])}
        )
        for table, col in (
            ("task_contracts", "id"),
            ("review_reports", "task_contract_id"),
            ("task_contract_events", "task_contract_id"),
        ):
            n = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {col}=:i"), {"i": str(cid)}
                )
            ).scalar_one()
            assert n == 0, table


# --- DB-backed: the done-gate (§12.3/§2.2, per-registration) ----------------------------


@pytest.mark.db
async def test_db_done_gate_per_registration(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx, extra_role_reviewer=True)
        await _to_review(repo, contract.id)
        cid = contract.id
    # zero reports ⇒ every registration pending ⇒ done refused (own scope per DB error)
    with pytest.raises(Exception, match="done|approved|pending"):
        async with tenant_scope(ctx) as session:
            await TaskContractRepository(session, ctx).complete(cid, actor="lead")
    async with tenant_scope(ctx) as session:
        status = await TaskContractRepository(session, ctx).review_status(cid)
        assert status.eligible is False and len(status.pending_registrations) == 4
        # three approvals; rev_role REJECTS; rev_role2 (same layer) APPROVES
        await _reject(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
        await _approve(session, ctx, cid, tc_ctx["rev_role2"], "role_specific")
        await _approve(session, ctx, cid, tc_ctx["rev_cross"], "cross_functional")
        await _approve(session, ctx, cid, tc_ctx["rev_acc"], "acceptance")
    # the standing rejection blocks done even though a same-layer approval is NEWER
    with pytest.raises(Exception, match="done|approved|rejected"):
        async with tenant_scope(ctx) as session:
            await TaskContractRepository(session, ctx).complete(cid, actor="lead")
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        status = await repo.review_status(cid)
        assert status.eligible is False
        assert status.rejected_registrations == (("role_specific", str(tc_ctx["rev_role"])),)
        # the rejecting reviewer's OWN latest becomes approved ⇒ done OK
        await _approve(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
        assert (await repo.review_status(cid)).eligible is True
        await repo.complete(cid, actor="lead")
        assert (await repo.get(cid)).status == "done"
    async with admin_engine.connect() as c:
        transitions = (
            await c.execute(
                text(
                    "SELECT from_status, to_status FROM task_contract_events "
                    "WHERE task_contract_id=:c ORDER BY created_at, id"
                ),
                {"c": str(cid)},
            )
        ).all()
    assert [tuple(r) for r in transitions] == [
        (None, "draft"),
        ("draft", "ready_for_development"),
        ("ready_for_development", "in_progress"),
        ("in_progress", "specialist_review"),
        ("specialist_review", "done"),
    ]


@pytest.mark.db
async def test_db_done_is_not_terminal_and_post_done_locks(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        cid = contract.id
        await _approve(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
        await _approve(session, ctx, cid, tc_ctx["rev_cross"], "cross_functional")
        await _approve(session, ctx, cid, tc_ctx["rev_acc"], "acceptance")
        await repo.complete(cid, actor="lead")
    # post-done: reports refused (window guard; own scope)
    with pytest.raises(Exception, match="status|reportable"):
        async with tenant_scope(ctx) as session:
            await _reject(session, ctx, cid, tc_ctx["rev_role"], "role_specific")
    # done→canceled refused at the DB guard (B2 ruling)
    with pytest.raises(Exception, match="transition|illegal"):
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE task_contracts SET status='canceled' WHERE id=:i"), {"i": str(cid)}
            )
    # done→superseded is the single outgoing transition
    async with tenant_scope(ctx) as session:
        repo = TaskContractRepository(session, ctx)
        await repo.supersede(cid, actor="lead")
        assert (await repo.get(cid)).status == "superseded"
        # terminal: no outgoing (pure-matrix refusal — no DB write attempted)
        with pytest.raises(Exception, match="transition|illegal|same-status"):
            await repo.cancel(cid, actor="lead")


# --- DB-backed: events (B3 spec) --------------------------------------------------------


@pytest.mark.db
async def test_db_event_checks_and_fk(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        contract = await _create(TaskContractRepository(session, ctx), tc_ctx)
        cid = contract.id
    stmt = (
        "INSERT INTO task_contract_events (tenant_id, project_id, task_contract_id, "
        "from_status, to_status, actor) VALUES (:t,:p,:c,:f,:to,:a)"
    )
    base = {"t": str(tc_ctx["t1"]), "p": str(tc_ctx["p1"]), "c": str(cid)}
    for over, match in (
        ({"f": None, "to": "in_progress", "a": "x"}, "violates check|duality"),  # NULL ⇔ draft
        ({"f": "draft", "to": "draft", "a": "x"}, "violates check|duality"),
        ({"f": "draft", "to": "ready_for_development", "a": " "}, "violates check|actor"),
        ({"f": "nope", "to": "in_progress", "a": "x"}, "violates check"),
    ):
        with pytest.raises(Exception, match=match):
            async with admin_engine.begin() as c:
                await c.execute(text(stmt), {**base, **over})
    # cross-project FK
    with pytest.raises(Exception, match="foreign key"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(stmt),
                {
                    "t": str(tc_ctx["t2"]),
                    "p": str(tc_ctx["px"]),
                    "c": str(cid),
                    "f": "draft",
                    "to": "ready_for_development",
                    "a": "x",
                },
            )


# --- DB-backed: non-executing / bit-stable ----------------------------------------------


@pytest.mark.db
async def test_db_bit_stable_for_a5_and_readiness(tc_ctx, admin_engine):
    ctx = TenantContext(tc_ctx["t1"])
    async with tenant_scope(ctx) as session:
        before = (await ProductionAutonomyRepository(session, ctx).evaluate(tc_ctx["p1"])).to_dict()
    async with tenant_scope(ctx) as session:
        repo, contract = await _staffed_contract(session, ctx, tc_ctx)
        await _to_review(repo, contract.id)
        await _approve(session, ctx, contract.id, tc_ctx["rev_role"], "role_specific")
        await _approve(session, ctx, contract.id, tc_ctx["rev_cross"], "cross_functional")
        await _approve(session, ctx, contract.id, tc_ctx["rev_acc"], "acceptance")
        await repo.complete(contract.id, actor="lead")
    async with tenant_scope(ctx) as session:
        after = (await ProductionAutonomyRepository(session, ctx).evaluate(tc_ctx["p1"])).to_dict()
    assert before == after  # bit-stable — no A5 gate flip
    assert before["a5_satisfied"] is False and before["can_go_live_autonomously"] is False
    async with admin_engine.connect() as c:
        n = (
            await c.execute(
                text("SELECT count(*) FROM readiness_reports WHERE project_id=:p"),
                {"p": str(tc_ctx["p1"])},
            )
        ).scalar_one()
    assert n == 0  # readiness untouched (no snapshot written by any of this)
