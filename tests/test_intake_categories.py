"""Slice 15 — intake category modeling (R3–R5 readiness foundation) tests.

Docker-free: the three constants partition the §4.2 universe (3/22/2 after Slice 20);
declarable/secret/source validators; provenance XOR fail-closed; and a readiness INTERACTION
check — Slices 16/18/20 now consume these declared categories, so spine coverage WITHOUT any
declared category still stays R2, the cap is now R5, and at R5 every category is consumed so
NOT_ASSESSED_CATEGORIES is empty.
DB-backed (`db`): declare (doc/origin-backed, incl. the two Slice-20 presence-only categories) +
audit safety (no summary/data/locator), accepted-doc pinning, uniqueness, revise + immutability
guard, no-DELETE, RLS, catalog; the DB CHECK accepts the 22-set and still rejects non-declarable.
This slice models INPUTS ONLY — it stores no secret values; Slices 16/18/20 read them.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.intake.categories import (
    CANONICAL_READINESS_CATEGORY_UNIVERSE,
    DECLARABLE_INTAKE_CATEGORIES,
    GATED_ENGINE_CATEGORIES,
    SPINE_CATEGORIES,
    InvalidCategory,
    InvalidCategoryData,
    InvalidProvenance,
    validate_category_data,
    validate_declarable_category,
    validate_source,
)
from app.intake.readiness import NOT_ASSESSED_CATEGORIES, ArtifactView, evaluate_readiness
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext, tenant_scope

# --- Docker-free: constants partition -----------------------------------------


def test_constants_partition_the_universe():
    universe = set(CANONICAL_READINESS_CATEGORY_UNIVERSE)
    decl = set(DECLARABLE_INTAKE_CATEGORIES)
    gated = set(GATED_ENGINE_CATEGORIES)
    spine = set(SPINE_CATEGORIES)
    assert len(universe) == 27
    # Slice 20: human_approval_policy + production_authority became presence-only declarable.
    assert len(decl) == 22 and len(gated) == 2 and len(spine) == 3
    # pairwise disjoint
    assert decl.isdisjoint(gated) and decl.isdisjoint(spine) and gated.isdisjoint(spine)
    # exact cover
    assert decl | gated | spine == universe
    # key anchors
    assert "architecture_and_technology_constraints" in decl  # architecture + stack
    assert "secrets_and_credentials_manifest" in decl
    assert {"human_approval_policy", "production_authority"} <= decl  # now declarable (Slice 20)
    assert gated == {"autonomy_policy", "cost_and_resource_policy"}  # engine-read only
    assert spine == {"functional_requirements", "acceptance_criteria", "test_oracles"}


# --- Docker-free: validators --------------------------------------------------


def test_validate_declarable_category():
    for c in DECLARABLE_INTAKE_CATEGORIES:
        validate_declarable_category(c)  # no raise
    # autonomy_policy + cost_and_resource_policy remain engine-read (not declarable); spine + bogus rejected.
    for bad in ("autonomy_policy", "cost_and_resource_policy", "functional_requirements", "bogus"):
        with pytest.raises(InvalidCategory):
            validate_declarable_category(bad)


def test_validate_source_xor():
    did = uuid.uuid4()
    # the two valid shapes
    validate_source(source_document_id=did, locator="§3.1", origin=None)  # doc-backed ok
    validate_source(source_document_id=None, locator=None, origin="human_decision")  # origin ok
    # every invalid shape is rejected (mirrors the DB CHECK)
    for kwargs in (
        dict(source_document_id=None, locator=None, origin=None),  # neither
        dict(source_document_id=did, locator="x", origin="human"),  # both
        dict(source_document_id=did, locator="x", origin=""),  # doc + empty origin
        dict(source_document_id=did, locator=None, origin=None),  # doc without locator
        dict(source_document_id=did, locator="   ", origin=None),  # doc + blank locator
        dict(source_document_id=None, locator="§3.1", origin="human"),  # origin + locator
        dict(source_document_id=None, locator=None, origin="   "),  # blank origin
        dict(source_document_id=None, locator=None, origin=""),  # empty origin
    ):
        with pytest.raises(InvalidProvenance):
            validate_source(**kwargs)


def test_secret_data_reference_only():
    # reference-only metadata accepted
    validate_category_data(
        "secrets_and_credentials_manifest",
        {"manager": "vault", "reference_name": "prod/db_password"},
    )
    validate_category_data(
        "secrets_and_credentials_manifest",
        {"references": [{"manager": "aws_sm", "reference_name": "app/api_key"}]},
    )
    validate_category_data("secrets_and_credentials_manifest", {})  # empty ok
    # inline secret values rejected
    for bad in (
        {"value": "hunter2"},
        {"password": "p@ss"},
        {"manager": "vault", "secret": "abc"},
        {"references": [{"manager": "vault", "value": "leak"}]},
    ):
        with pytest.raises(InvalidCategoryData):
            validate_category_data("secrets_and_credentials_manifest", bad)


def test_non_secret_data_rejects_obvious_secret_keys():
    # defense-in-depth: any category rejects credential-looking keys
    with pytest.raises(InvalidCategoryData):
        validate_category_data("environments_and_deployment_targets", {"password": "x"})
    # ordinary non-secret data is fine
    validate_category_data(
        "environments_and_deployment_targets", {"envs": ["staging", "production"]}
    )


# --- Docker-free: readiness interaction (Slices 16 + 18 + 20 supersede the Slice-15 R2 guards) ---
# Slice 15 pinned the auditor at R2 / a 22-tuple to prove it didn't touch readiness. Slice 16 lifts
# to R3 (technical trio + environments), Slice 18 to R4 (the two "tools" categories), and Slice 20
# to R5 (all remaining declarable categories + the two engine gates). The current contract: spine
# coverage WITHOUT any declared categories still stays R2; the cap is now R5; and at R5 the entire
# §4.2 universe is consumed, so NOT_ASSESSED_CATEGORIES is empty.


def test_readiness_without_declared_categories_stays_r2_cap_now_r5():
    req = ArtifactView(id=uuid.uuid4(), kind="requirement", ref="REQ-1", title="r")
    ac = ArtifactView(
        id=uuid.uuid4(), kind="acceptance_criterion", ref="AC-1", title="a", parent_id=req.id
    )
    oracle = ArtifactView(
        id=uuid.uuid4(), kind="test_oracle", ref="OR-1", title="o", parent_id=ac.id
    )
    rep = evaluate_readiness("p", [req, ac, oracle], production_authority_decision="needs_approval")
    assert rep.readiness_level == "R2"  # no declared categories -> R2 base only
    assert rep.readiness_cap == "R5"  # Slice 20: cap is now R5
    assert rep.can_build_to_staging is False
    assert rep.can_go_live_autonomously is False


def test_r5_consumes_entire_universe_so_not_assessed_is_empty():
    # At R5 every §4.2 category is consumed by a rule (spine ladder + R3 + R4 + R5 + engine gates),
    # so the not-assessed list is empty.
    assert NOT_ASSESSED_CATEGORIES == ()
    for consumed in (
        "architecture_and_technology_constraints",
        "environments_and_deployment_targets",
        "integrations_and_external_systems",
        "tool_access_manifest",
        "human_approval_policy",
        "production_authority",
        "go_live_checklist",
    ):
        assert consumed not in NOT_ASSESSED_CATEGORIES


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def cat_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('CatOrg',:s) RETURNING id",
            s=f"cat-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c, "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"cat-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c, "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"cat-{proj}-{sfx}",
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

        out["doc_p1"] = await _doc(out["t1"], out["p1"], f"arch-doc-{sfx}")
        out["doc_p1_quar"] = await _doc(out["t1"], out["p1"], f"quar-{sfx}", "quarantined")
        out["doc_p2"] = await _doc(out["t1"], out["p2"], f"p2-doc-{sfx}")
        out["doc_px"] = await _doc(out["t2"], out["px"], f"px-doc-{sfx}")
    return out


_SECRET_SUMMARY = "SENSITIVE-SUMMARY-should-not-leak"


# --- DB-backed: declare + audit safety ----------------------------------------


@pytest.mark.db
async def test_declare_doc_backed_persists_and_audits_safely(cat_ctx, admin_engine):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rec = await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1,
            category="architecture_and_technology_constraints",
            summary=_SECRET_SUMMARY,
            source_document_id=d1,
            locator="§ stack",
            actor="planner",
        )
        rid = rec.id
        assert rec.status == "declared"
        assert rec.source_document_id == d1
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE action='intake.category_declared' "
                    "AND target=:tg ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"intake_category:{rid}"},
            )
        ).one()
    assert actor == "planner"
    blob = str(payload)
    assert _SECRET_SUMMARY not in blob
    # presence-only source metadata; never the concrete document UUID / locator / summary / data
    assert "summary" not in payload and "data" not in payload and "locator" not in payload
    assert "source_document_id" not in payload
    assert str(d1) not in blob
    assert payload["has_source_document"] is True
    assert payload["has_origin"] is False
    assert payload["category"] == "architecture_and_technology_constraints"


@pytest.mark.db
async def test_declare_origin_backed(cat_ctx):
    t1, p1 = cat_ctx["t1"], cat_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rec = await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1, category="risk_register_and_assurance_requirements",
            status="not_applicable", origin="human_decision", actor="planner",
        )
        assert rec.origin == "human_decision"
        assert rec.source_document_id is None


@pytest.mark.parametrize("category", ["human_approval_policy", "production_authority"])
@pytest.mark.db
async def test_slice20_new_declarable_categories_persist(cat_ctx, category):
    # Slice 20: human_approval_policy + production_authority are now declarable (app + DB CHECK).
    t1, p1 = cat_ctx["t1"], cat_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rec = await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1, category=category, origin="human_decision", actor="planner",
        )
        assert rec.category == category and rec.status == "declared"


@pytest.mark.db
async def test_slice20_non_declarable_category_still_rejected_at_db(cat_ctx, admin_engine):
    # autonomy_policy / cost_and_resource_policy stay engine-read: the DB CHECK must still reject them.
    t1, p1 = cat_ctx["t1"], cat_ctx["p1"]
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO intake_categories (tenant_id, project_id, category, status, origin) "
                    "VALUES (:t,:p,'autonomy_policy','declared','x')"
                ),
                {"t": str(t1), "p": str(p1)},
            )
    assert "ck_intake_categories_category_valid" in str(ei.value) or "check constraint" in str(
        ei.value
    ).lower()


@pytest.mark.db
async def test_secret_category_reference_only_persists(cat_ctx, admin_engine):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rec = await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1, category="secrets_and_credentials_manifest",
            data={"manager": "vault", "reference_name": "prod/db"},
            source_document_id=d1, locator="§ secrets", actor="planner",
        )
        rid = rec.id
    # the audit must not carry the data (even though it's reference-only)
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE target=:tg "
                    "AND action='intake.category_declared' ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"intake_category:{rid}"},
            )
        ).scalar_one()
    assert "data" not in payload and "vault" not in str(payload)


# --- DB-backed: provenance / pinning / uniqueness -----------------------------


@pytest.mark.db
async def test_quarantined_or_foreign_doc_rejected(cat_ctx):
    t1, p1 = cat_ctx["t1"], cat_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        # quarantined source doc
        with pytest.raises(ValueError):
            await repo.declare(
                project_id=p1, category="environments_and_deployment_targets",
                source_document_id=cat_ctx["doc_p1_quar"], locator="x", actor="a",
            )
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        # cross-project doc (p2 doc for a p1 declaration)
        with pytest.raises(ValueError):
            await repo.declare(
                project_id=p1, category="environments_and_deployment_targets",
                source_document_id=cat_ctx["doc_p2"], locator="x", actor="a",
            )
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        # cross-tenant doc (t2/px doc for a t1/p1 declaration) — not visible under RLS
        with pytest.raises(ValueError):
            await repo.declare(
                project_id=p1, category="environments_and_deployment_targets",
                source_document_id=cat_ctx["doc_px"], locator="x", actor="a",
            )


@pytest.mark.db
async def test_one_declaration_per_category(cat_ctx):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        await repo.declare(
            project_id=p1, category="domain_pack", source_document_id=d1, locator="x", actor="a"
        )
        with pytest.raises(Exception):  # UNIQUE(tenant,project,category)
            await repo.declare(
                project_id=p1, category="domain_pack", source_document_id=d1, locator="y", actor="a"
            )


# --- DB-backed: revise + immutability guard + no-delete -----------------------


@pytest.mark.db
async def test_revise_allowed_but_keys_immutable(cat_ctx, admin_engine):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        rec = await repo.declare(
            project_id=p1, category="go_live_checklist", summary="draft",
            source_document_id=d1, locator="x", actor="a",
        )
        rid = rec.id
        # legitimate revise of summary/status
        revised = await repo.revise(project_id=p1, category="go_live_checklist",
                                    summary="updated", actor="a")
        assert revised.summary == "updated"
    # raw immutability: id / tenant_id / project_id / category / created_at all frozen
    for col, val in (
        ("id", "gen_random_uuid()"),
        ("tenant_id", f"'{cat_ctx['t2']}'"),
        ("project_id", f"'{cat_ctx['p2']}'"),
        ("category", "'domain_pack'"),
        ("created_at", "now() - interval '1 day'"),
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(
                    text(f"UPDATE intake_categories SET {col}={val} WHERE id=:i"), {"i": str(rid)}
                )
        assert "immutable" in str(ei.value).lower(), f"{col}: {ei.value}"


@pytest.mark.db
async def test_no_delete(cat_ctx, rls_engine):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1, category="product_brief", source_document_id=d1, locator="x", actor="a"
        )
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text("DELETE FROM intake_categories WHERE tenant_id=:t"), {"t": str(t1)}
                )
    msg = str(ei.value).lower()
    assert "append-only" in msg or "permission denied" in msg or "denied" in msg or "delete" in msg


@pytest.mark.db
async def test_no_truncate(admin_engine):
    # TRUNCATE is blocked by the statement-level trigger (owner/admin path).
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            await c.execute(text("TRUNCATE intake_categories"))
    assert "truncate" in str(ei.value).lower() or "delete" in str(ei.value).lower()


@pytest.mark.db
async def test_db_source_xor_raw_inserts_rejected(cat_ctx, admin_engine):
    # Raw inserts bypassing the repository must still be rejected by the DB source-XOR CHECK.
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    base = (
        "INSERT INTO intake_categories (tenant_id, project_id, category, status, "
        "source_document_id, locator, origin) VALUES (:t,:p,'domain_pack','declared',{src})"
    )
    for src in (
        "NULL, NULL, NULL",  # no source
        f"'{d1}', 'x', 'human'",  # both document and origin
        "NULL, 'x', 'human'",  # origin + locator
        f"'{d1}', NULL, NULL",  # document without locator
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(base.format(src=src)), {"t": str(t1), "p": str(p1)})
        msg = str(ei.value).lower()
        assert "check" in msg or "violates" in msg or "source_xor" in msg


# --- DB-backed: RLS / catalog -------------------------------------------------


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(cat_ctx, rls_engine):
    t1, p1, d1 = cat_ctx["t1"], cat_ctx["p1"], cat_ctx["doc_p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1, category="business_objectives", source_document_id=d1, locator="x",
            actor="a",
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (await conn.execute(text("SELECT count(*) FROM intake_categories"))).scalar_one()
            assert n == 0
    async with tenant_scope(TenantContext(cat_ctx["t2"])) as session:
        assert await IntakeCategoryRepository(session, TenantContext(cat_ctx["t2"])).list_categories(
            p1
        ) == []


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='intake_categories' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT", "UPDATE"}  # no DELETE
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='intake_categories'"
                )
            )
        ).one()
        assert rls == (True, True)
