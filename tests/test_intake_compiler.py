"""Slice 11 — Sanad provenance store + canonical intake spine (§3.4/§2.4/§4.2/§4.4) tests.

Docker-free: kind/classification validation + the ``Fact``-gate fail-closed (no source).
DB-backed (`db`): provenance-backed add + audit-without-content, the DB-level
deferrable source-count constraint, document composite-FK tenant/project pinning,
accepted-document-only trigger, parent triple-FK, append-only (no UPDATE/DELETE),
RLS + cross-tenant, the tightened classification CHECK, duplicate-ref reject, catalog/grants.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.provenance import NoFreeFactsError
from app.intake.compiler import (
    ARTIFACT_KINDS,
    ASSUMPTION_CLASSIFICATIONS,
    InvalidArtifact,
    SourceInput,
    assert_sources,
    validate_classification,
    validate_kind,
)
from app.intake.sandbox import content_hash, content_size_bytes
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, tenant_scope

# --- Docker-free --------------------------------------------------------------


def test_kinds_and_classifications_are_the_minimal_canonical_set():
    assert set(ARTIFACT_KINDS) == {
        "requirement",
        "acceptance_criterion",
        "test_oracle",
        "assumption",
    }
    assert set(ASSUMPTION_CLASSIFICATIONS) == {
        "safe_assumption",
        "needs_approval",
        "unsafe_assumption_blocked",
        "unknown_cannot_proceed",
    }


def test_validate_kind():
    for k in ARTIFACT_KINDS:
        validate_kind(k)  # no raise
    with pytest.raises(InvalidArtifact):
        validate_kind("bogus")


def test_validate_classification_assumptions_require_a_valid_value():
    for c in ASSUMPTION_CLASSIFICATIONS:
        validate_classification("assumption", c)  # no raise
    # assumption with NULL/invalid is rejected
    with pytest.raises(InvalidArtifact):
        validate_classification("assumption", None)
    with pytest.raises(InvalidArtifact):
        validate_classification("assumption", "maybe")


def test_validate_classification_non_assumptions_must_be_null():
    for k in ("requirement", "acceptance_criterion", "test_oracle"):
        validate_classification(k, None)  # no raise
        with pytest.raises(InvalidArtifact):
            validate_classification(k, "safe_assumption")


def test_assert_sources_fail_closed_no_source():
    # Reuses the Sanad primitive: a fact with no source raises.
    with pytest.raises(NoFreeFactsError):
        assert_sources("a requirement", [])


def test_assert_sources_ok_with_one_source():
    assert_sources("a requirement", [SourceInput(origin="document:abc", locator="p1")])


def test_source_input_shape():
    s = SourceInput(origin="human_decision", locator="meeting", document_id=None)
    assert s.origin == "human_decision"
    assert s.locator == "meeting"
    assert s.document_id is None


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


async def _doc(c, *, tenant, project, content, status):
    return await _scalar(
        c,
        "INSERT INTO documents (tenant_id, project_id, filename, content_type, source, "
        "content, content_hash, size_bytes, status) "
        "VALUES (:t,:p,'f.txt','text/plain','manual',:c,:h,:sz,:status) RETURNING id",
        t=tenant,
        p=project,
        c=content,
        h=content_hash(content),
        sz=content_size_bytes(content),
        status=status,
    )


@pytest_asyncio.fixture
async def intake_ctx(admin_engine):
    """Two tenants; t1 has p1+p2, t2 has px. Seed accepted/quarantined docs."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('IntakeOrg',:s) RETURNING id",
            s=f"intk-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"intk-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"intk-{proj}-{sfx}",
            )
        out["d1_accepted"] = await _doc(
            c, tenant=out["t1"], project=out["p1"], content=f"acc-p1-{sfx}", status="accepted"
        )
        out["d1_quar"] = await _doc(
            c, tenant=out["t1"], project=out["p1"], content=f"quar-p1-{sfx}", status="quarantined"
        )
        out["d2_accepted"] = await _doc(
            c, tenant=out["t1"], project=out["p2"], content=f"acc-p2-{sfx}", status="accepted"
        )
        out["dx_accepted"] = await _doc(
            c, tenant=out["t2"], project=out["px"], content=f"acc-px-{sfx}", status="accepted"
        )
    return out


_INS_ARTIFACT = (
    "INSERT INTO intake_artifacts (tenant_id, project_id, kind, ref, title, classification) "
    "VALUES (:t,:p,:kind,:ref,:title,:classification) RETURNING id"
)
_INS_PROV = (
    "INSERT INTO intake_provenance (tenant_id, project_id, artifact_id, document_id, origin) "
    "VALUES (:t,:p,:a,:doc,:origin)"
)


# --- DB-backed: add + audit-safety --------------------------------------------


@pytest.mark.db
async def test_add_artifact_persists_with_provenance_and_audits_safely(intake_ctx, admin_engine):
    t1, p1, d1 = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d1_accepted"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        art = await repo.add_artifact(
            project_id=p1,
            kind="requirement",
            ref="REQ-001",
            title="The system shall export an evidence pack.",
            body="full statement text",
            sources=[SourceInput(origin=f"document:{d1}", locator="p3", document_id=d1)],
            actor="compiler",
        )
        aid = art.id
        assert art.kind == "requirement"
        srcs = await repo.sources_for(aid)
        assert len(srcs) == 1
        assert srcs[0].document_id == d1
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "AND action='intake.artifact_added' ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"intake_artifact:{aid}", "t": t1},
            )
        ).one()
    assert actor == "compiler"
    assert payload["kind"] == "requirement"
    assert payload["ref"] == "REQ-001"
    assert payload["source_count"] == 1
    assert str(d1) in payload["document_ids"]
    # body / title / data are tenant content and must never be audited
    assert "title" not in payload
    assert "body" not in payload
    assert "data" not in payload


@pytest.mark.db
async def test_add_assumption_with_classification(intake_ctx):
    t1, p1 = intake_ctx["t1"], intake_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        art = await repo.add_artifact(
            project_id=p1,
            kind="assumption",
            ref="ASM-001",
            title="Assume UTC timestamps.",
            classification="needs_approval",
            sources=[SourceInput(origin="human_decision", document_id=None)],
            actor="compiler",
        )
        assert art.classification == "needs_approval"
        assert art.kind == "assumption"


# --- DB-backed: fail-closed source-count (deferrable constraint) --------------


@pytest.mark.db
async def test_repo_rejects_empty_sources(intake_ctx):
    t1, p1 = intake_ctx["t1"], intake_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        with pytest.raises(NoFreeFactsError):
            await IntakeRepository(session, ctx).add_artifact(
                project_id=p1,
                kind="requirement",
                ref="REQ-EMPTY",
                title="no sources here",
                sources=[],
                actor="compiler",
            )


@pytest.mark.db
async def test_db_artifact_without_provenance_fails_on_constraint(intake_ctx, rls_engine):
    """Raw uaid_app insert of an artifact with zero provenance fails the deferrable check."""
    t1, p1 = intake_ctx["t1"], intake_ctx["p1"]
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(_INS_ARTIFACT),
                    {
                        "t": str(t1),
                        "p": str(p1),
                        "kind": "requirement",
                        "ref": "REQ-NOPROV",
                        "title": "orphan",
                        "classification": None,
                    },
                )
                # Force the deferred constraint to evaluate inside the transaction.
                await conn.execute(text("SET CONSTRAINTS intake_artifacts_requires_source IMMEDIATE"))
    msg = str(ei.value).lower()
    assert "provenance" in msg or "source" in msg


# --- DB-backed: document composite-FK pinning ---------------------------------


@pytest.mark.db
async def test_document_provenance_cross_project_rejected_at_db(intake_ctx, admin_engine):
    """A provenance row in (p1,t1) referencing an accepted doc that lives in (p2,t1)
    is rejected by the composite FK — same tenant, different project."""
    t1, p1, d2 = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d2_accepted"]
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            aid = await _scalar(
                c,
                _INS_ARTIFACT,
                t=str(t1),
                p=str(p1),
                kind="requirement",
                ref="REQ-XP",
                title="x",
                classification=None,
            )
            await c.execute(
                text(_INS_PROV),
                {"t": str(t1), "p": str(p1), "a": str(aid), "doc": str(d2), "origin": "o"},
            )
    assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


@pytest.mark.db
async def test_document_provenance_cross_tenant_rejected_at_db(intake_ctx, admin_engine):
    """A provenance row in (p1,t1) referencing a t2 accepted doc is rejected by the FK."""
    t1, p1, dx = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["dx_accepted"]
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            aid = await _scalar(
                c,
                _INS_ARTIFACT,
                t=str(t1),
                p=str(p1),
                kind="requirement",
                ref="REQ-XT",
                title="x",
                classification=None,
            )
            await c.execute(
                text(_INS_PROV),
                {"t": str(t1), "p": str(p1), "a": str(aid), "doc": str(dx), "origin": "o"},
            )
    assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


# --- DB-backed: accepted-document-only trigger --------------------------------


@pytest.mark.db
async def test_quarantined_document_provenance_rejected(intake_ctx, rls_engine):
    t1, p1, dq = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d1_quar"]
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                aid = await _scalar(
                    conn,
                    _INS_ARTIFACT,
                    t=str(t1),
                    p=str(p1),
                    kind="requirement",
                    ref="REQ-Q",
                    title="x",
                    classification=None,
                )
                await conn.execute(
                    text(_INS_PROV),
                    {"t": str(t1), "p": str(p1), "a": str(aid), "doc": str(dq), "origin": "o"},
                )
    assert "accepted" in str(ei.value).lower()


@pytest.mark.db
async def test_repo_rejects_quarantined_doc_source(intake_ctx):
    t1, p1, dq = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d1_quar"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        with pytest.raises(ValueError):
            await IntakeRepository(session, ctx).add_artifact(
                project_id=p1,
                kind="requirement",
                ref="REQ-Q2",
                title="x",
                sources=[SourceInput(origin=f"document:{dq}", document_id=dq)],
                actor="compiler",
            )


# --- DB-backed: parent triple-FK ----------------------------------------------


@pytest.mark.db
async def test_parent_link_same_project_ok_cross_project_rejected(intake_ctx, admin_engine):
    t1, p1, p2 = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["p2"]
    d1, d2 = intake_ctx["d1_accepted"], intake_ctx["d2_accepted"]
    ctx = TenantContext(t1)
    # same-project parent: acceptance_criterion -> requirement (both p1)
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        req = await repo.add_artifact(
            project_id=p1,
            kind="requirement",
            ref="REQ-P",
            title="parent req",
            sources=[SourceInput(origin=f"document:{d1}", document_id=d1)],
            actor="c",
        )
        ac = await repo.add_artifact(
            project_id=p1,
            kind="acceptance_criterion",
            ref="AC-P",
            title="child ac",
            parent_id=req.id,
            sources=[SourceInput(origin=f"document:{d1}", document_id=d1)],
            actor="c",
        )
        assert ac.parent_id == req.id
        parent_in_p1 = req.id
    # cross-project parent: child in p2 pointing at a p1 parent -> triple FK rejects
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            aid = await _scalar(
                c,
                "INSERT INTO intake_artifacts "
                "(tenant_id, project_id, kind, ref, title, classification, parent_id) "
                "VALUES (:t,:p,'acceptance_criterion','AC-XP','x',NULL,:par) RETURNING id",
                t=str(t1),
                p=str(p2),
                par=str(parent_in_p1),
            )
            await c.execute(
                text(_INS_PROV),
                {"t": str(t1), "p": str(p2), "a": str(aid), "doc": str(d2), "origin": "o"},
            )
    assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


# --- DB-backed: append-only ---------------------------------------------------


@pytest.mark.db
async def test_artifacts_and_provenance_append_only(intake_ctx, admin_engine, rls_engine):
    t1, p1, d1 = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d1_accepted"]
    # seed a complete valid fact (artifact + provenance) committed via admin
    async with admin_engine.begin() as c:
        aid = await _scalar(
            c,
            _INS_ARTIFACT,
            t=str(t1),
            p=str(p1),
            kind="requirement",
            ref="REQ-AO",
            title="frozen",
            classification=None,
        )
        await c.execute(
            text(_INS_PROV),
            {"t": str(t1), "p": str(p1), "a": str(aid), "doc": str(d1), "origin": "o"},
        )
    for tbl in ("intake_artifacts", "intake_provenance"):
        for verb in ("UPDATE", "DELETE"):
            sql = (
                f"UPDATE {tbl} SET origin='x' WHERE tenant_id=:t"
                if (verb == "UPDATE" and tbl == "intake_provenance")
                else f"UPDATE {tbl} SET title='x' WHERE tenant_id=:t"
                if verb == "UPDATE"
                else f"DELETE FROM {tbl} WHERE tenant_id=:t"
            )
            with pytest.raises(Exception) as ei:
                async with rls_engine.connect() as conn:
                    async with conn.begin():
                        await conn.execute(
                            text("SELECT set_config('app.current_tenant', :t, true)"),
                            {"t": str(t1)},
                        )
                        await conn.execute(text(sql), {"t": str(t1)})
            msg = str(ei.value).lower()
            assert "append-only" in msg or "permission denied" in msg or "denied" in msg


# --- DB-backed: RLS / cross-tenant --------------------------------------------


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant_check(intake_ctx, admin_engine, rls_engine):
    t1, t2, p1, d1 = intake_ctx["t1"], intake_ctx["t2"], intake_ctx["p1"], intake_ctx["d1_accepted"]
    # seed one fact
    async with admin_engine.begin() as c:
        aid = await _scalar(
            c,
            _INS_ARTIFACT,
            t=str(t1),
            p=str(p1),
            kind="requirement",
            ref="REQ-RLS",
            title="x",
            classification=None,
        )
        await c.execute(
            text(_INS_PROV),
            {"t": str(t1), "p": str(p1), "a": str(aid), "doc": str(d1), "origin": "o"},
        )
    # deny-by-default (no GUC) on both tables
    async with rls_engine.connect() as conn:
        async with conn.begin():
            for tbl in ("intake_artifacts", "intake_provenance"):
                n = (await conn.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar_one()
                assert n == 0
    # cross-tenant WITH CHECK insert blocked (GUC=t1, row for t2)
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(_INS_ARTIFACT),
                    {
                        "t": str(t2),
                        "p": str(p1),
                        "kind": "requirement",
                        "ref": "REQ-X",
                        "title": "x",
                        "classification": None,
                    },
                )
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


# --- DB-backed: classification CHECK ------------------------------------------


@pytest.mark.db
async def test_classification_check_enforced_at_db(intake_ctx, admin_engine):
    t1, p1 = intake_ctx["t1"], intake_ctx["p1"]
    # assumption with NULL classification -> CHECK violation (immediate at insert)
    with pytest.raises(Exception) as ei1:
        async with admin_engine.begin() as c:
            await c.execute(
                text(_INS_ARTIFACT),
                {
                    "t": str(t1),
                    "p": str(p1),
                    "kind": "assumption",
                    "ref": "ASM-NULL",
                    "title": "x",
                    "classification": None,
                },
            )
    assert "check" in str(ei1.value).lower() or "violates" in str(ei1.value).lower()
    # non-assumption with a classification -> CHECK violation
    with pytest.raises(Exception) as ei2:
        async with admin_engine.begin() as c:
            await c.execute(
                text(_INS_ARTIFACT),
                {
                    "t": str(t1),
                    "p": str(p1),
                    "kind": "requirement",
                    "ref": "REQ-CLS",
                    "title": "x",
                    "classification": "safe_assumption",
                },
            )
    assert "check" in str(ei2.value).lower() or "violates" in str(ei2.value).lower()


# --- DB-backed: duplicate ref -------------------------------------------------


@pytest.mark.db
async def test_duplicate_ref_rejected(intake_ctx):
    t1, p1, d1 = intake_ctx["t1"], intake_ctx["p1"], intake_ctx["d1_accepted"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        await repo.add_artifact(
            project_id=p1,
            kind="requirement",
            ref="REQ-DUP",
            title="first",
            sources=[SourceInput(origin=f"document:{d1}", document_id=d1)],
            actor="c",
        )
        with pytest.raises(Exception):
            await repo.add_artifact(
                project_id=p1,
                kind="requirement",
                ref="REQ-DUP",
                title="second",
                sources=[SourceInput(origin=f"document:{d1}", document_id=d1)],
                actor="c",
            )


# --- DB-backed: catalog / grants ----------------------------------------------


@pytest.mark.db
async def test_catalog_grants_rls_and_documents_unique(admin_engine):
    async with admin_engine.connect() as c:
        for tbl in ("intake_artifacts", "intake_provenance"):
            grants = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:tbl AND grantee='uaid_app'"
                        ),
                        {"tbl": tbl},
                    )
                ).all()
            }
            assert grants == {"SELECT", "INSERT"}, f"{tbl}: {grants}"
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname=:tbl"
                    ),
                    {"tbl": tbl},
                )
            ).one()
            assert rls == (True, True), f"{tbl}: {rls}"
        # the documents composite unique (FK target) exists
        present = (
            await c.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname='uq_documents_id_project_tenant'"
                )
            )
        ).scalar_one_or_none()
        assert present == 1
