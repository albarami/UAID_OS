"""Tenant-scoped readiness auditor repository (Slice 12, §4.5).

``evaluate`` reads the canonical intake spine for a project, consults the autonomy
policy for the (transparency-only) ``deploy_production`` decision, and runs the pure
``app.intake.readiness`` engine — no write. ``evaluate_and_record`` additionally
persists an immutable snapshot and audits with **safe metadata only** (no assumption
titles, no tenant content, no report body). Run inside ``tenant_scope`` (GUC set).
``actor`` is an untrusted caller label.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.intake.readiness import ArtifactView, ReadinessReport, evaluate_readiness
from app.models.readiness_report import ReadinessReportRecord
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, TenantScopedRepository


class ReadinessRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReadinessReportRecord)

    async def evaluate(self, project_id: uuid.UUID) -> ReadinessReport:
        """Pure read: compute the §4.5 report from the spine. Does not persist."""
        artifacts = await IntakeRepository(self.session, self.context).list_artifacts(project_id)
        views = [
            ArtifactView(
                id=a.id,
                kind=a.kind,
                ref=a.ref,
                title=a.title,
                parent_id=a.parent_id,
                classification=a.classification,
            )
            for a in artifacts
        ]
        # Transparency only — deploy_production is mandatory-approval, never ALLOW,
        # and can never make can_go_live_autonomously true (handled in the engine).
        decision = await AutonomyPolicyRepository(self.session, self.context).decision_for(
            project_id, "deploy_production"
        )
        return evaluate_readiness(
            project_id, views, production_authority_decision=decision.value
        )

    async def evaluate_and_record(
        self, *, project_id: uuid.UUID, actor: str
    ) -> tuple[ReadinessReport, ReadinessReportRecord]:
        report = await self.evaluate(project_id)
        row = ReadinessReportRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            readiness_level=report.readiness_level,
            can_build_to_staging=report.can_build_to_staging,
            can_go_live_autonomously=report.can_go_live_autonomously,
            report=report.to_dict(),
            evaluated_by=actor,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, report, actor)
        return report, row

    async def latest(self, project_id: uuid.UUID) -> ReadinessReportRecord | None:
        stmt = (
            select(ReadinessReportRecord)
            .where(
                ReadinessReportRecord.tenant_id == self.context.tenant_id,
                ReadinessReportRecord.project_id == project_id,
            )
            .order_by(desc(ReadinessReportRecord.created_at), desc(ReadinessReportRecord.id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def history(self, project_id: uuid.UUID) -> Sequence[ReadinessReportRecord]:
        stmt = (
            select(ReadinessReportRecord)
            .where(
                ReadinessReportRecord.tenant_id == self.context.tenant_id,
                ReadinessReportRecord.project_id == project_id,
            )
            .order_by(desc(ReadinessReportRecord.created_at), desc(ReadinessReportRecord.id))
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def _audit(
        self, row: ReadinessReportRecord, report: ReadinessReport, actor: str
    ) -> None:
        # Safe metadata only — NEVER assumption titles, tenant content, or the report body.
        await audit_record(
            self.session,
            action="intake.readiness_evaluated",
            actor=actor,
            target=f"readiness_report:{row.id}",
            payload={
                "readiness_report_id": str(row.id),
                "project_id": str(row.project_id),
                "readiness_level": report.readiness_level,
                "can_build_to_staging": report.can_build_to_staging,
                "can_go_live_autonomously": report.can_go_live_autonomously,
                "spine_gap_count": len(report.spine_gaps),
                "safe_assumption_count": len(report.safe_assumptions),
                "blocked_assumption_count": len(report.blocked_assumptions),
                "ruleset_version": report.to_dict()["ruleset_version"],
            },
        )
