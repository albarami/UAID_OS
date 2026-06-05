"""Slice 14b — promotion of approved proposals into the spine (§2.2/§2.4/§16.5) tests.

Docker-free: deterministic promotion-ref derivation. DB-backed (`db`): the full promotion
pipeline via IntakeRepository.add_artifact — promotion-time evidence re-verification,
exact field mapping, eligibility, idempotency, unsupported-kind refusal, parent
validation, assumption gating (incl. approval-engine), approval-request idempotency +
payload safety, RLS/cross-tenant, append-only, grants. All extraction uses FakeLLMClient.
"""

import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.intake.extraction import promotion_ref
from app.llm.client import FakeLLMClient
from app.llm.pricing import ModelPrice
from app.repositories.approvals import ApprovalRepository
from app.repositories.extraction import ExtractionRepository
from app.tenancy import TenantContext, tenant_scope

_PRICE = ModelPrice(input_usd_per_1k=Decimal("0.003"), output_usd_per_1k=Decimal("0.015"))
_CARD = {"test-model": _PRICE}
_DOC = (
    "The system shall export an evidence pack. Users must authenticate before access. "
    "Assume UTC timestamps for all logs."
)
_PROMOTE_ACTION = "intake.promote_assumption"


def _resp(items, classification="requirements_doc"):
    return json.dumps({"document_classification": classification, "items": items})


# --- Docker-free: ref derivation ----------------------------------------------


def test_promotion_ref_deterministic_and_prefixed():
    pid = uuid.UUID("0123456789abcdef0123456789abcdef")
    assert promotion_ref("requirement", pid) == "REQ-EXT-01234567"
    assert promotion_ref("acceptance_criterion", pid) == "AC-EXT-01234567"
    assert promotion_ref("assumption", pid) == "ASM-EXT-01234567"
    # deterministic
    assert promotion_ref("requirement", pid) == promotion_ref("requirement", pid)


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def promo_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('PrOrg',:s) RETURNING id",
            s=f"pr-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c, "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"pr-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c, "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"pr-{proj}-{sfx}",
            )

        async def _doc(tenant, project, content, status="accepted"):
            return await _scalar(
                c,
                "INSERT INTO documents (tenant_id, project_id, filename, content_type, source, "
                "content, content_hash, size_bytes, status) "
                "VALUES (:t,:p,'f.txt','text/plain','manual',:c,:h,:sz,:st) RETURNING id",
                t=tenant, p=project, c=content,
                h="sha256:" + __import__("hashlib").sha256(content.encode()).hexdigest(),
                sz=len(content.encode()), st=status,
            )

        out["doc_p1"] = await _doc(out["t1"], out["p1"], _DOC)
        out["doc_p2"] = await _doc(out["t1"], out["p2"], _DOC)
        out["doc_px"] = await _doc(out["t2"], out["px"], _DOC)
        for proj in ("p1", "p2", "px"):
            tn = "t2" if proj == "px" else "t1"
            await c.execute(
                text(
                    "INSERT INTO budgets (tenant_id, project_id, max_total_cost_usd) "
                    "VALUES (:t,:p,:m)"
                ),
                {"t": str(out[tn]), "p": str(out[proj]), "m": Decimal("100")},
            )
    return out


async def _extract_and_approve(ctx, project_id, document_id, items, *, reviewer="human-rev"):
    """Run extraction (fake) then approve every produced proposal. Returns proposal ids."""
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        _run, proposals = await repo.extract(
            project_id=project_id, document_id=document_id, model="test-model",
            llm_client=FakeLLMClient(response_text=_resp(items), input_tokens=100, output_tokens=50),
            price_card=_CARD, extracted_by="agent-x",
        )
        ids = [p.id for p in proposals]
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        for pid in ids:
            await repo.review_proposal(proposal_id=pid, decision="approved", reviewed_by=reviewer)
    return ids


async def _raw_run(admin_engine, tenant, project, doc):
    async with admin_engine.begin() as c:
        return await _scalar(
            c,
            "INSERT INTO extraction_runs (id, tenant_id, project_id, document_id, model, provider, "
            "prompt_version, status) VALUES (gen_random_uuid(),:t,:p,:d,'m','fake','v','succeeded') "
            "RETURNING id",
            t=str(tenant), p=str(project), d=str(doc),
        )


async def _raw_approved_proposal(
    admin_engine, *, tenant, project, run_id, doc, kind, text_val, evidence, classification=None
):
    async with admin_engine.begin() as c:
        pid = await _scalar(
            c,
            "INSERT INTO extraction_proposals (tenant_id, project_id, extraction_run_id, "
            "proposed_kind, proposed_text, proposed_classification, source_document_id, "
            "evidence_quote, status, extracted_by) "
            "VALUES (:t,:p,:r,:k,:tx,:cl,:d,:ev,'pending','agent-x') RETURNING id",
            t=str(tenant), p=str(project), r=str(run_id), k=kind, tx=text_val,
            cl=classification, d=str(doc), ev=evidence,
        )
        await c.execute(
            text(
                "UPDATE extraction_proposals SET status='approved', reviewed_by='human-rev', "
                "reviewed_at=now() WHERE id=:i"
            ),
            {"i": str(pid)},
        )
    return pid


# --- DB-backed: happy path + field mapping + provenance + audit safety --------


@pytest.mark.db
async def test_promote_requirement_maps_fields_and_provenance(promo_ctx, admin_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "requirement", "text": "export evidence", "evidence_quote": "evidence pack"}],
    )
    async with tenant_scope(ctx) as session:
        art = await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=pid, actor="promoter"
        )
        assert art.kind == "requirement"
        assert art.title == "export evidence"
        assert art.body is None
        assert art.data == {"extraction_proposal_id": str(pid)}
        assert art.classification is None
        assert art.parent_id is None
        assert art.ref == promotion_ref("requirement", pid)
        aid = art.id
        # provenance row points at the source doc with the evidence quote as locator
        prov = (
            await session.execute(
                text(
                    "SELECT document_id, locator FROM intake_provenance "
                    "WHERE artifact_id=:a AND tenant_id=:t"
                ),
                {"a": str(aid), "t": t1},
            )
        ).one()
        assert prov[0] == d1
        assert prov[1] == "evidence pack"
    # audit safety: proposal_promoted carries no proposed_text / evidence_quote
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE action='intake.proposal_promoted' "
                    "AND target=:tg ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"extraction_proposal:{pid}"},
            )
        ).scalar_one()
    blob = str(payload)
    assert "export evidence" not in blob and "evidence pack" not in blob
    assert payload["artifact_id"] == str(aid)


@pytest.mark.db
async def test_promotion_reverifies_evidence(promo_ctx, admin_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    run_id = await _raw_run(admin_engine, t1, p1, d1)
    pid = await _raw_approved_proposal(
        admin_engine, tenant=t1, project=p1, run_id=run_id, doc=d1,
        kind="requirement", text_val="fabricated", evidence="NOT IN THE DOCUMENT",
    )
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")
        # no artifact and no promotion link created
        n = (
            await session.execute(
                text("SELECT count(*) FROM extraction_promotions WHERE tenant_id=:t"),
                {"t": t1},
            )
        ).scalar_one()
        assert n == 0


# --- DB-backed: eligibility / idempotency / unsupported kind ------------------


@pytest.mark.db
async def test_pending_and_rejected_not_promotable(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    # create a pending proposal (extract, do NOT approve)
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        _run, proposals = await repo.extract(
            project_id=p1, document_id=d1, model="test-model",
            llm_client=FakeLLMClient(
                response_text=_resp(
                    [{"kind": "requirement", "text": "x", "evidence_quote": "evidence pack"}]
                ),
                input_tokens=10, output_tokens=10,
            ),
            price_card=_CARD, extracted_by="agent-x",
        )
        pid = proposals[0].id
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=pid, actor="p")
        # unknown id
        with pytest.raises(LookupError):
            await repo.promote_proposal(proposal_id=uuid.uuid4(), actor="p")
    # reject the proposal, then promotion must still refuse
    async with tenant_scope(ctx) as session:
        await ExtractionRepository(session, ctx).review_proposal(
            proposal_id=pid, decision="rejected", reviewed_by="human-rev"
        )
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")


@pytest.mark.db
async def test_promote_is_idempotent(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "requirement", "text": "x", "evidence_quote": "evidence pack"}],
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        a1 = await repo.promote_proposal(proposal_id=pid, actor="p")
        a2 = await repo.promote_proposal(proposal_id=pid, actor="p")
        assert a1.id == a2.id
        n = (
            await session.execute(
                text("SELECT count(*) FROM extraction_promotions WHERE tenant_id=:t"),
                {"t": t1},
            )
        ).scalar_one()
        assert n == 1


@pytest.mark.db
async def test_test_oracle_kind_refused(promo_ctx, admin_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    run_id = await _raw_run(admin_engine, t1, p1, d1)
    pid = await _raw_approved_proposal(
        admin_engine, tenant=t1, project=p1, run_id=run_id, doc=d1,
        kind="test_oracle", text_val="oracle", evidence="evidence pack",
    )
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")


# --- DB-backed: parent validation (acceptance_criterion) ----------------------


@pytest.mark.db
async def test_acceptance_criterion_parent_validation(promo_ctx, admin_engine):
    t1, p1, p2 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["p2"]
    d1, d2 = promo_ctx["doc_p1"], promo_ctx["doc_p2"]
    ctx = TenantContext(t1)
    # promote a requirement to act as a valid parent
    [req_pid] = await _extract_and_approve(
        ctx, p1, d1, [{"kind": "requirement", "text": "r", "evidence_quote": "evidence pack"}]
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        req_art = await repo.promote_proposal(proposal_id=req_pid, actor="p")
        req_id = req_art.id
    # a requirement in a DIFFERENT project (same tenant) for the cross-project case
    [req2_pid] = await _extract_and_approve(
        ctx, p2, d2, [{"kind": "requirement", "text": "r2", "evidence_quote": "evidence pack"}]
    )
    async with tenant_scope(ctx) as session:
        cross_req = await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=req2_pid, actor="p"
        )
        cross_req_id = cross_req.id
    # an acceptance_criterion proposal in p1
    [ac_pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "acceptance_criterion", "text": "ac", "evidence_quote": "authenticate"}],
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        # nonexistent parent
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=ac_pid, actor="p", parent_id=uuid.uuid4())
        # cross-project parent (a requirement in p2) is rejected
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=ac_pid, actor="p", parent_id=cross_req_id)
    # wrong-kind parent: promote an assumption, then use it as parent
    [asm_pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "a", "classification": "safe_assumption",
          "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        asm_art = await repo.promote_proposal(proposal_id=asm_pid, actor="p")
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=ac_pid, actor="p", parent_id=asm_art.id)
    # valid parent (a requirement in the same project) links
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        ac_art = await repo.promote_proposal(proposal_id=ac_pid, actor="p", parent_id=req_id)
        assert ac_art.parent_id == req_id


@pytest.mark.db
async def test_parent_id_rejected_for_non_acceptance_criterion(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [req_pid] = await _extract_and_approve(
        ctx, p1, d1, [{"kind": "requirement", "text": "r", "evidence_quote": "evidence pack"}]
    )
    [asm_pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "a", "classification": "safe_assumption",
          "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=req_pid, actor="p", parent_id=uuid.uuid4())
        with pytest.raises(ValueError):
            await repo.promote_proposal(proposal_id=asm_pid, actor="p", parent_id=uuid.uuid4())


@pytest.mark.db
async def test_request_promotion_approval_requires_approved(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    # pending needs_approval assumption (extract, do NOT approve)
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        _run, proposals = await repo.extract(
            project_id=p1, document_id=d1, model="test-model",
            llm_client=FakeLLMClient(
                response_text=_resp(
                    [{"kind": "assumption", "text": "x", "classification": "needs_approval",
                      "evidence_quote": "UTC timestamps"}]
                ),
                input_tokens=10, output_tokens=10,
            ),
            price_card=_CARD, extracted_by="agent-x",
        )
        pid = proposals[0].id
        with pytest.raises(ValueError):  # pending ⇒ cannot request promotion approval
            await repo.request_promotion_approval(proposal_id=pid, requested_by="agent-x")
    # reject it, then still cannot request
    async with tenant_scope(ctx) as session:
        await ExtractionRepository(session, ctx).review_proposal(
            proposal_id=pid, decision="rejected", reviewed_by="human-rev"
        )
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).request_promotion_approval(
                proposal_id=pid, requested_by="agent-x"
            )


@pytest.mark.db
async def test_promotion_approval_payload_and_audit_safe(promo_ctx, admin_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "secret assumption text",
          "classification": "needs_approval", "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        ap = await ExtractionRepository(session, ctx).request_promotion_approval(
            proposal_id=pid, requested_by="agent-x"
        )
        ap_id = ap.id
        assert set(ap.payload.keys()) == {
            "proposal_id", "project_id", "kind", "classification", "subject_ref"
        }
        assert "secret assumption text" not in str(ap.payload)
        assert "UTC timestamps" not in str(ap.payload)
    # the approval.requested audit carries engine-safe metadata only
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE action='approval.requested' "
                    "AND target=:tg ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"approval:{ap_id}"},
            )
        ).scalar_one()
    blob = str(payload)
    assert "secret assumption text" not in blob and "UTC timestamps" not in blob


@pytest.mark.db
async def test_terminal_negative_approval_allows_fresh_request(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "x", "classification": "needs_approval",
          "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        ap1 = await repo.request_promotion_approval(proposal_id=pid, requested_by="agent-x")
        # reject the approval (terminal-negative)
        await ApprovalRepository(session, ctx).reject(approval_id=ap1.id, actor="human-approver")
    async with tenant_scope(ctx) as session:
        ap2 = await ExtractionRepository(session, ctx).request_promotion_approval(
            proposal_id=pid, requested_by="agent-x"
        )
        assert ap2.id != ap1.id  # a fresh request after a terminal-negative


# --- DB-backed: assumption gating ---------------------------------------------


@pytest.mark.db
async def test_safe_assumption_promotes(promo_ctx):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "utc", "classification": "safe_assumption",
          "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        art = await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")
        assert art.kind == "assumption" and art.classification == "safe_assumption"


@pytest.mark.db
@pytest.mark.parametrize("cls", ["unsafe_assumption_blocked", "unknown_cannot_proceed"])
async def test_blocked_assumptions_hard_refuse(promo_ctx, cls):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "x", "classification": cls,
          "evidence_quote": "UTC timestamps"}],
    )
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")


@pytest.mark.db
async def test_needs_approval_requires_approval_then_promotes(promo_ctx, admin_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1,
        [{"kind": "assumption", "text": "x", "classification": "needs_approval",
          "evidence_quote": "UTC timestamps"}],
    )
    # without an approval, promotion is blocked
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")
    # request approval (idempotent) + approve it
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        ap1 = await repo.request_promotion_approval(proposal_id=pid, requested_by="agent-x")
        ap2 = await repo.request_promotion_approval(proposal_id=pid, requested_by="agent-x")
        assert ap1.id == ap2.id  # idempotent before approval (no duplicate pending)
        # approval payload safety
        assert "UTC timestamps" not in str(ap1.payload)
        await ApprovalRepository(session, ctx).approve(approval_id=ap1.id, actor="human-approver")
    # duplicate request AFTER approval returns the approved one (no new pending)
    async with tenant_scope(ctx) as session:
        repo = ExtractionRepository(session, ctx)
        ap3 = await repo.request_promotion_approval(proposal_id=pid, requested_by="agent-x")
        assert ap3.id == ap1.id
        art = await repo.promote_proposal(proposal_id=pid, actor="p")
        assert art.classification == "needs_approval"


# --- DB-backed: RLS / cross-tenant / append-only / catalog --------------------


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(promo_ctx, rls_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1, [{"kind": "requirement", "text": "x", "evidence_quote": "evidence pack"}]
    )
    async with tenant_scope(ctx) as session:
        await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM extraction_promotions"))
            ).scalar_one()
            assert n == 0
    # tenant t2 sees no promotions for p1
    async with tenant_scope(TenantContext(promo_ctx["t2"])) as session:
        assert await ExtractionRepository(session, TenantContext(promo_ctx["t2"])).list_promotions(
            p1
        ) == []


@pytest.mark.db
async def test_promotions_append_only(promo_ctx, rls_engine):
    t1, p1, d1 = promo_ctx["t1"], promo_ctx["p1"], promo_ctx["doc_p1"]
    ctx = TenantContext(t1)
    [pid] = await _extract_and_approve(
        ctx, p1, d1, [{"kind": "requirement", "text": "x", "evidence_quote": "evidence pack"}]
    )
    async with tenant_scope(ctx) as session:
        await ExtractionRepository(session, ctx).promote_proposal(proposal_id=pid, actor="p")
    for sql in (
        "UPDATE extraction_promotions SET promoted_by='y' WHERE tenant_id=:t",
        "DELETE FROM extraction_promotions WHERE tenant_id=:t",
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(sql), {"t": str(t1)})
        msg = str(ei.value).lower()
        assert "append-only" in msg or "permission denied" in msg or "denied" in msg


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='extraction_promotions' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='extraction_promotions'"
                )
            )
        ).one()
        assert rls == (True, True)
