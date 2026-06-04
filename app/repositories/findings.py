"""Tenant-scoped gap & contradiction detector repository (Slice 13).

``evaluate`` reads the canonical intake spine for a project and runs the pure
``app.intake.findings`` detector — no write. ``evaluate_and_record`` additionally
persists an immutable snapshot and audits with **counts/metadata only** (no refs, no
titles, no body/data, no report JSON). Run inside ``tenant_scope`` (GUC set).
``actor`` is an untrusted caller label. This repository never reads artifact
``title``/``body``/``data`` — only structural fields flow into the detector.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.intake.findings import FindingsReport, StructuralArtifactView, detect_findings
from app.models.intake_findings_report import IntakeFindingsReport
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, TenantScopedRepository


class FindingsRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, IntakeFindingsReport)

    async def evaluate(self, project_id: uuid.UUID) -> FindingsReport:
        """Pure read: detect gaps + contradictions from the spine. Does not persist."""
        artifacts = await IntakeRepository(self.session, self.context).list_artifacts(project_id)
        # Structural fields only — title/body/data are never carried into the detector.
        views = [
            StructuralArtifactView(
                id=a.id,
                kind=a.kind,
                ref=a.ref,
                parent_id=a.parent_id,
                classification=a.classification,
            )
            for a in artifacts
        ]
        return detect_findings(project_id, views)

    async def evaluate_and_record(
        self, *, project_id: uuid.UUID, actor: str
    ) -> tuple[FindingsReport, IntakeFindingsReport]:
        report = await self.evaluate(project_id)
        d = report.to_dict()
        row = IntakeFindingsReport(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            gap_count=d["gap_count"],
            contradiction_count=d["contradiction_count"],
            report=d,
            evaluated_by=actor,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, d, actor)
        return report, row

    async def latest(self, project_id: uuid.UUID) -> IntakeFindingsReport | None:
        stmt = (
            select(IntakeFindingsReport)
            .where(
                IntakeFindingsReport.tenant_id == self.context.tenant_id,
                IntakeFindingsReport.project_id == project_id,
            )
            .order_by(desc(IntakeFindingsReport.created_at), desc(IntakeFindingsReport.id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def history(self, project_id: uuid.UUID) -> Sequence[IntakeFindingsReport]:
        stmt = (
            select(IntakeFindingsReport)
            .where(
                IntakeFindingsReport.tenant_id == self.context.tenant_id,
                IntakeFindingsReport.project_id == project_id,
            )
            .order_by(desc(IntakeFindingsReport.created_at), desc(IntakeFindingsReport.id))
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def _audit(self, row: IntakeFindingsReport, report_dict: dict, actor: str) -> None:
        # Counts/metadata only — NEVER refs, titles, body/data, or the report JSON.
        await audit_record(
            self.session,
            action="intake.findings_evaluated",
            actor=actor,
            target=f"intake_findings_report:{row.id}",
            payload={
                "intake_findings_report_id": str(row.id),
                "project_id": str(row.project_id),
                "gap_count": report_dict["gap_count"],
                "contradiction_count": report_dict["contradiction_count"],
                "ruleset_version": report_dict["ruleset_version"],
            },
        )
