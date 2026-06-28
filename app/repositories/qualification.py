"""Tenant-scoped qualification repository (Slice 40, §9.4 step 6-7 / §9.5.1).

``record_qualification_run`` scores recorded dry-test cases into an immutable run (the DB verifies the
counts/coverage against the FK children and GENERATES the verdict). ``request_qualification_approvals``
opens the two **run-scoped** sign-offs (QA + Platform Security — B7: the ``run_id`` is in the subject
ref, so an approval can never satisfy a different run). ``qualify`` performs the one-way
``unqualified→qualified`` transition only when a **passing** run **and both** approvals (for that exact
run) are present. Audit is safe-metadata only. Run inside ``tenant_scope``. Labels are UNTRUSTED.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.qualification import coverage_complete, derive_counts, validate_case_results
from app.audit import record as audit_record
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_instance import AgentInstance
from app.models.agent_realization import AgentRealization
from app.models.agent_version import AgentVersion
from app.models.archetype_eval import ArchetypeEval
from app.models.qualification_run import QualificationCaseResult, QualificationRun
from app.repositories.approvals import ApprovalRepository
from app.tenancy import TenantContext, TenantScopedRepository

_QA_ROLES = ("qa", "security")  # §9.4 step 7 — Agent QA Reviewer + Platform Security Reviewer
_QUALIFY_RISK_TIER = "high"


class QualificationError(ValueError):
    """Raised when a qualification precondition (passing run / both run-scoped approvals) is unmet."""


def _approval_action(role: str) -> str:
    return f"qualify_agent_{role}"


def _approval_subject(realization_id: uuid.UUID, run_id: uuid.UUID, role: str) -> str:
    return f"agent_realization:{realization_id}:qualification_run:{run_id}:{role}"


class QualificationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, QualificationRun)

    async def _realization(self, realization_id: uuid.UUID) -> AgentRealization:
        real = (
            await self.session.execute(
                select(AgentRealization).where(
                    AgentRealization.id == realization_id,
                    AgentRealization.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if real is None:
            raise QualificationError("realization not found")
        return real

    async def _archetype_of(self, real: AgentRealization) -> str:
        stmt = (
            select(AgentBlueprint.archetype)
            .join(AgentVersion, AgentVersion.blueprint_id == AgentBlueprint.id)
            .join(AgentInstance, AgentInstance.version_id == AgentVersion.id)
            .where(
                AgentInstance.id == real.instance_id,
                AgentInstance.tenant_id == self.context.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def record_qualification_run(
        self, *, realization_id: uuid.UUID, cases: Sequence[dict], evaluated_by: str
    ) -> QualificationRun:
        validate_case_results(cases)
        real = await self._realization(realization_id)
        archetype = await self._archetype_of(real)
        ae = (
            (
                await self.session.execute(
                    select(ArchetypeEval)
                    .where(ArchetypeEval.archetype == archetype)
                    .order_by(ArchetypeEval.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if ae is None:
            raise QualificationError(f"no archetype_eval for archetype {archetype!r}")

        total, passed, critical, categories = derive_counts(cases)
        cov = coverage_complete(categories, ae.required_categories)
        run = QualificationRun(
            tenant_id=self.context.tenant_id,
            project_id=real.project_id,
            realization_id=real.id,
            archetype_eval_id=ae.id,
            archetype=archetype,
            eval_version=ae.eval_version,
            min_aggregate_score=ae.min_aggregate_score,
            require_zero_critical=ae.require_zero_critical,
            min_cases=ae.min_cases,
            required_categories=ae.required_categories,
            total_cases=total,
            passed_cases=passed,
            critical_failure_count=critical,
            coverage_complete=cov,
            evaluated_by=evaluated_by,
        )
        self.session.add(run)
        await self.session.flush()
        for c in cases:
            self.session.add(
                QualificationCaseResult(
                    tenant_id=self.context.tenant_id,
                    project_id=real.project_id,
                    run_id=run.id,
                    case_ref=c["case_ref"],
                    case_category=c["case_category"],
                    passed=bool(c["passed"]),
                    is_critical=bool(c["is_critical"]),
                )
            )
        await self.session.flush()
        await self.session.refresh(run)  # load the GENERATED verdict/aggregate_score
        await audit_record(
            self.session,
            action="qualification.run_recorded",
            actor=evaluated_by,
            target=f"qualification_run:{run.id}",
            payload={
                "realization_id": str(realization_id),
                "archetype": archetype,
                "verdict": run.verdict,
                "aggregate_score": str(run.aggregate_score),
                "total_cases": total,
                "passed_cases": passed,
                "critical_failure_count": critical,
                "coverage_complete": cov,
            },
        )
        return run

    async def request_qualification_approvals(
        self, *, realization_id: uuid.UUID, run_id: uuid.UUID, requested_by: str
    ) -> dict:
        real = await self._realization(realization_id)
        approvals = ApprovalRepository(self.session, self.context)
        out: dict = {}
        for role in _QA_ROLES:
            action = _approval_action(role)
            subject = _approval_subject(realization_id, run_id, role)
            existing = await approvals.latest_for(real.project_id, action, subject_ref=subject)
            if existing is not None:  # idempotent — one approval per (run, role)
                out[role] = existing
                continue
            out[role] = await approvals.request(
                project_id=real.project_id,
                action=action,
                risk_tier=_QUALIFY_RISK_TIER,
                requires_explicit_approval=True,
                requested_by=requested_by,
                subject_ref=subject,
                payload={"realization_id": str(realization_id), "run_id": str(run_id)},
            )
        return out

    async def qualify(
        self, *, realization_id: uuid.UUID, run_id: uuid.UUID, qualified_by: str
    ) -> AgentRealization:
        real = await self._realization(realization_id)
        run = (
            await self.session.execute(
                select(QualificationRun).where(
                    QualificationRun.id == run_id,
                    QualificationRun.tenant_id == self.context.tenant_id,
                    QualificationRun.realization_id == realization_id,
                )
            )
        ).scalar_one_or_none()
        if run is None or run.verdict != "passed":
            raise QualificationError("a passing qualification run for this realization is required")

        approvals = ApprovalRepository(self.session, self.context)
        for role in _QA_ROLES:
            appr = await approvals.latest_for(
                real.project_id,
                _approval_action(role),
                subject_ref=_approval_subject(realization_id, run_id, role),
            )
            if appr is None or appr.status != "approved":
                raise QualificationError(f"an APPROVED {role} sign-off for THIS run is required")

        real.qualification_status = "qualified"
        real.qualified_via_run_id = run_id
        real.updated_at = datetime.now(timezone.utc)
        await (
            self.session.flush()
        )  # the DB guard backstops the transition + passing-run requirement
        await audit_record(
            self.session,
            action="agent.qualified",
            actor=qualified_by,
            target=f"agent_realization:{realization_id}",
            payload={"run_id": str(run_id), "archetype": run.archetype, "verdict": run.verdict},
        )
        return real

    async def runs_for(self, realization_id: uuid.UUID) -> Sequence[QualificationRun]:
        stmt = (
            select(QualificationRun)
            .where(
                QualificationRun.tenant_id == self.context.tenant_id,
                QualificationRun.realization_id == realization_id,
            )
            .order_by(QualificationRun.created_at.desc(), QualificationRun.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def is_qualified(self, realization_id: uuid.UUID) -> bool:
        real = await self._realization(realization_id)
        return real.qualification_status == "qualified"
