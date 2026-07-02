"""Tenant-scoped review-report repository (Slice 42, §13.3).

``record_report`` stores a **REPORTED** reviewer verdict — content
``caller_supplied_unverified`` (reviewer QA = S48) — after pure validation and a
registration lookup: the reporter must be a REGISTERED (contract, reviewer-instance,
layer) reviewer (the ``0041`` registration FK is the backstop; the exact-subject
Slice-40 lesson). ``can_merge`` is never written here — it is DB-GENERATED from the
verdict (V2-B2). Audit carries safe metadata only: ids + layer + verdict + list COUNTS —
never summary/criteria/changes prose. Reports are append-only immutable; nothing here
performs a review. Run inside ``tenant_scope``. ``reported_by``/``source`` are UNTRUSTED
labels.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.review_report import ReviewReport
from app.models.task_contract import TaskContract, TaskContractReviewer
from app.review.task_contracts import require_text
from app.review.workflow import validate_review_report
from app.tenancy import TenantContext, TenantScopedRepository


class ReviewReportRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReviewReport)

    async def record_report(
        self,
        *,
        contract_id: uuid.UUID,
        reviewer_instance_id: uuid.UUID,
        layer: str,
        verdict: str,
        summary: str,
        failed_criteria: Sequence[str],
        suspected_shortcuts: Sequence[str],
        required_changes: Sequence[str],
        source: str,
        reported_by: str,
        source_provenance: str = "caller_supplied_unverified",
    ) -> ReviewReport:
        validate_review_report(
            verdict=verdict,
            summary=summary,
            failed_criteria=failed_criteria,
            suspected_shortcuts=suspected_shortcuts,
            required_changes=required_changes,
            source=source,
            source_provenance=source_provenance,
        )
        require_text("reported_by", reported_by, 200)
        contract_stmt = select(TaskContract).where(
            TaskContract.tenant_id == self.context.tenant_id,
            TaskContract.id == contract_id,
        )
        contract = (await self.session.execute(contract_stmt)).scalars().first()
        if contract is None:
            raise ValueError(f"unknown task contract for this tenant: {contract_id}")
        reg_stmt = select(TaskContractReviewer).where(
            TaskContractReviewer.tenant_id == self.context.tenant_id,
            TaskContractReviewer.task_contract_id == contract.id,
            TaskContractReviewer.reviewer_instance_id == reviewer_instance_id,
            TaskContractReviewer.layer == layer,
        )
        registration = (await self.session.execute(reg_stmt)).scalars().first()
        if registration is None:
            raise ValueError(
                "reviewer is not registered for this contract/layer "
                f"({reviewer_instance_id}, {layer})"
            )
        report = ReviewReport(
            tenant_id=self.context.tenant_id,
            project_id=contract.project_id,
            task_contract_id=contract.id,
            reviewer_instance_id=reviewer_instance_id,
            layer=layer,
            verdict=verdict,
            summary=summary,
            failed_criteria=list(failed_criteria),
            suspected_shortcuts=list(suspected_shortcuts),
            required_changes=list(required_changes),
            source=source,
            source_provenance=source_provenance,
        )
        self.session.add(report)
        await self.session.flush()  # the 0041 window guard + registration FK fire here
        await audit_record(
            self.session,
            action="review_report.recorded",
            actor=reported_by,
            target=f"review_report:{report.id}",
            payload={
                "review_report_id": str(report.id),
                "task_contract_id": str(contract.id),
                "reviewer_instance_id": str(reviewer_instance_id),
                "layer": layer,
                "verdict": verdict,
                "failed_criteria_count": len(list(failed_criteria)),
                "suspected_shortcut_count": len(list(suspected_shortcuts)),
                "required_change_count": len(list(required_changes)),
            },
        )
        return report

    async def latest_by_registration(
        self, contract_id: uuid.UUID
    ) -> dict[tuple[uuid.UUID, str], ReviewReport]:
        """The latest report per (reviewer_instance_id, layer) registration key."""
        stmt = (
            select(ReviewReport)
            .where(
                ReviewReport.tenant_id == self.context.tenant_id,
                ReviewReport.task_contract_id == contract_id,
            )
            .order_by(ReviewReport.created_at.desc(), ReviewReport.id.desc())
        )
        latest: dict[tuple[uuid.UUID, str], ReviewReport] = {}
        for report in (await self.session.execute(stmt)).scalars().all():
            key = (report.reviewer_instance_id, report.layer)
            if key not in latest:
                latest[key] = report
        return latest

    async def reports_for(self, contract_id: uuid.UUID) -> Sequence[ReviewReport]:
        stmt = (
            select(ReviewReport)
            .where(
                ReviewReport.tenant_id == self.context.tenant_id,
                ReviewReport.task_contract_id == contract_id,
            )
            .order_by(ReviewReport.created_at.desc(), ReviewReport.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()
