"""Skill Matching Engine repository (Slice 38, §8) — admin-path catalog + tenant SquadRepository.

**Trust zones (B8):**
- `register_skill` / `register_capability` are **admin-path module functions** (mirroring Slice-6
  `register_blueprint`/`register_version`): they take an **admin session** and write the global
  vocab/capability tables. The runtime role `uaid_app` has **SELECT only** on those tables and can never
  run them.
- `capability_view` is a SELECT read usable by the runtime during a build.
- `SquadRepository` is tenant-scoped: it reads `capability_view`, runs the pure `build_squad`, and persists
  the §8.4 manifest + the §8.3 `skill_matches` breakdown (B2) inside `tenant_scope`, tenant-audited.

Deterministic — no LLM. `built_by` is an UNTRUSTED label.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.skills import (
    COST_LATENCY_CLASSES,
    DOMAIN_RE,
    RULESET_VERSION,
    SKILL_CATEGORIES,
    TOOL_KEY_RE,
    AgentCapability,
    build_squad,
    validate_skill_key,
)
from app.audit import record as audit_record
from app.models.squad_matching import SkillMatch, SquadManifestRecord
from app.tenancy import TenantContext, TenantScopedRepository


# --- admin-path catalog functions (admin session; NOT runnable as uaid_app — B8) -----


async def register_skill(
    admin_session: AsyncSession, *, key: str, category: str, description: str = ""
) -> None:
    validate_skill_key(key)
    if category not in SKILL_CATEGORIES:
        raise ValueError(f"invalid skill category: {category!r}")
    await admin_session.execute(
        text("INSERT INTO skills (key, category, description) VALUES (:k, :c, :d)"),
        {"k": key, "c": category, "d": description},
    )


async def register_capability(
    admin_session: AsyncSession,
    *,
    blueprint_id: uuid.UUID,
    provided_skills: Sequence[str],
    reviewer_skills: Sequence[str] = (),
    provided_tools: Sequence[str] = (),
    domains: Sequence[str] = (),
    cost_latency_class: str = "medium",
) -> uuid.UUID:
    if cost_latency_class not in COST_LATENCY_CLASSES:
        raise ValueError(f"invalid cost_latency_class: {cost_latency_class!r}")
    for s in (*provided_skills, *reviewer_skills):
        validate_skill_key(s)
    for t in provided_tools:
        if not TOOL_KEY_RE.match(t):
            raise ValueError(f"invalid tool key: {t!r}")
    for d in domains:
        if not DOMAIN_RE.match(d):
            raise ValueError(f"invalid domain: {d!r}")
    # Resolve skill keys → ids; an unknown key is an honest error (the FK is the DB backstop, B3).
    rows = (
        await admin_session.execute(
            text("SELECT key, id FROM skills WHERE key = ANY(:keys)"),
            {"keys": list(set(provided_skills) | set(reviewer_skills))},
        )
    ).all()
    skill_ids = {k: i for k, i in rows}
    missing = (set(provided_skills) | set(reviewer_skills)) - set(skill_ids)
    if missing:
        raise ValueError(f"unknown skill keys: {sorted(missing)}")

    import json

    cap_id = (
        await admin_session.execute(
            text(
                "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class, "
                "provided_tools, domains) VALUES (:b, :c, CAST(:t AS jsonb), CAST(:d AS jsonb)) RETURNING id"
            ),
            {
                "b": str(blueprint_id),
                "c": cost_latency_class,
                "t": json.dumps(list(provided_tools)),
                "d": json.dumps(list(domains)),
            },
        )
    ).scalar_one()
    reviewer_set = set(reviewer_skills)
    for s in provided_skills:
        await admin_session.execute(
            text(
                "INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) "
                "VALUES (:cap, :sid, :rev)"
            ),
            {"cap": cap_id, "sid": skill_ids[s], "rev": s in reviewer_set},
        )
    return cap_id


async def capability_view(
    session: AsyncSession,
) -> tuple[list[AgentCapability], dict[str, uuid.UUID]]:
    """Latest capability per blueprint (append-only latest-wins) + its FK-proven provided skills."""
    rows = (
        (
            await session.execute(
                text(
                    "SELECT DISTINCT ON (c.blueprint_id) c.id AS cap_id, c.blueprint_id, b.key AS ref, "
                    "b.role, c.cost_latency_class, c.provided_tools, c.domains "
                    "FROM agent_skill_capabilities c JOIN agent_blueprints b ON b.id = c.blueprint_id "
                    "ORDER BY c.blueprint_id, c.created_at DESC, c.id DESC"
                )
            )
        )
        .mappings()
        .all()
    )
    caps: list[AgentCapability] = []
    blueprint_ids: dict[str, uuid.UUID] = {}
    for r in rows:
        skill_rows = (
            await session.execute(
                text(
                    "SELECT s.key, aps.can_review FROM agent_provided_skills aps "
                    "JOIN skills s ON s.id = aps.skill_id WHERE aps.capability_id = :cap"
                ),
                {"cap": r["cap_id"]},
            )
        ).all()
        caps.append(
            AgentCapability(
                blueprint_ref=r["ref"],
                role=r["role"],
                provided_skills=frozenset(k for k, _ in skill_rows),
                provided_tools=frozenset(r["provided_tools"]),
                domains=frozenset(r["domains"]),
                cost_latency_class=r["cost_latency_class"],
                reviewer_skills=frozenset(k for k, can in skill_rows if can),
            )
        )
        blueprint_ids[r["ref"]] = r["blueprint_id"]
    return caps, blueprint_ids


def _dec(value: float) -> Decimal:
    return Decimal(str(value))


# --- tenant-scoped squad builder -----------------------------------------------------


class SquadRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, SquadManifestRecord)

    async def build_and_record(
        self, *, project_id: uuid.UUID, work_units, built_by: str
    ) -> SquadManifestRecord:
        caps, blueprint_ids = await capability_view(self.session)
        manifest, matches = build_squad(work_units, caps)
        manifest_json = {
            "project_id": str(project_id),
            "active_agents": [
                {
                    "id": a.blueprint_ref,
                    "role": a.role,
                    "assigned_tasks": list(a.assigned_work_units),
                    "reviewers": list(a.reviewers),
                }
                for a in manifest.active_agents
            ],
            "missing_skills": list(manifest.missing_skills),
            "agent_factory_requests": list(manifest.agent_factory_requests),
        }
        rec = SquadManifestRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            manifest=manifest_json,
            work_unit_count=len(work_units),
            missing_skill_count=len(manifest.missing_skills),
            ruleset_version=RULESET_VERSION,
            built_by=built_by,
        )
        self.session.add(rec)
        await self.session.flush()
        for m in matches:
            bd = m.breakdown
            self.session.add(
                SkillMatch(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    manifest_id=rec.id,
                    work_unit_ref=m.work_unit_ref,
                    blueprint_id=blueprint_ids[m.blueprint_ref],
                    capability_match=_dec(bd.capability_match),
                    domain_fit=_dec(bd.domain_fit),
                    tool_access_fit=_dec(bd.tool_access_fit),
                    eval_performance=_dec(bd.eval_performance),
                    reviewer_availability=_dec(bd.reviewer_availability),
                    cost_latency_fit=_dec(bd.cost_latency_fit),
                    risk_penalty=_dec(bd.risk_penalty),
                    total_score=_dec(bd.total_score),
                    eval_source=bd.eval_source,
                )
            )
        await self.session.flush()
        # Audit safe-metadata only — counts; never declared domain/risk prose.
        await audit_record(
            self.session,
            action="squad.built",
            actor=built_by,
            target=f"squad_manifest:{rec.id}",
            payload={
                "squad_manifest_id": str(rec.id),
                "project_id": str(project_id),
                "work_unit_count": len(work_units),
                "missing_skill_count": len(manifest.missing_skills),
                "match_count": len(matches),
                "ruleset_version": RULESET_VERSION,
            },
        )
        return rec

    async def latest(self, project_id: uuid.UUID) -> SquadManifestRecord | None:
        stmt = (
            select(SquadManifestRecord)
            .where(
                SquadManifestRecord.tenant_id == self.context.tenant_id,
                SquadManifestRecord.project_id == project_id,
            )
            .order_by(SquadManifestRecord.created_at.desc(), SquadManifestRecord.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def history(self, project_id: uuid.UUID) -> Sequence[SquadManifestRecord]:
        stmt = (
            select(SquadManifestRecord)
            .where(
                SquadManifestRecord.tenant_id == self.context.tenant_id,
                SquadManifestRecord.project_id == project_id,
            )
            .order_by(SquadManifestRecord.created_at.desc(), SquadManifestRecord.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def matches_for(self, manifest_id: uuid.UUID) -> Sequence[SkillMatch]:
        stmt = (
            select(SkillMatch)
            .where(
                SkillMatch.tenant_id == self.context.tenant_id,
                SkillMatch.manifest_id == manifest_id,
            )
            .order_by(SkillMatch.work_unit_ref, SkillMatch.id)
        )
        return (await self.session.execute(stmt)).scalars().all()
