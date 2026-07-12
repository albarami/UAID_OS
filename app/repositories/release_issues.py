"""Tenant-scoped release issues repository (Slice 24, §24.1/§24.2/Appendix B #7).

``create`` validates the issue (fail-closed; taxonomy + critical⇒blocking + ``other`` rule) and
persists an ``open`` issue + a ``created`` event. ``resolve``/``supersede`` set the resolution
metadata; ``accept`` links a usable risk-acceptance record (refused for hard blockers). Every
transition writes an append-only event + an audit entry with **safe metadata only**
(ids/issue_category/severity/blocking/status — never summary/detail/resolution/blocking_category prose).
The DB guard (migration ``0023``, extended by ``0046``) is the authoritative backstop. Slice 47 adds
one code-derived issue per trusted Slice-44/45 finding plus bounded historical reconciliation; it
never claims semantic cross-run dedupe or completeness. Issues never enable go-live. Run inside
``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid
from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.release_finding import ReleaseFinding
from app.models.release_issue import ReleaseIssue
from app.models.release_issue_event import ReleaseIssueEvent
from app.release.issues import (
    InvalidIssue,
    MAX_RECONCILIATION_FINDINGS,
    TRUSTED_FINDING_PROVENANCE,
    TrustedFindingIssueDerivation,
    derive_issue_from_finding,
    is_hard_blocker,
    validate_new_issue,
    validate_transition,
)
from app.tenancy import TenantContext, TenantScopedRepository


class ReleaseIssueRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReleaseIssue)

    async def create(self, *, project_id: uuid.UUID, payload: dict, actor: str) -> ReleaseIssue:
        validate_new_issue(payload)
        row = ReleaseIssue(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            issue_category=payload["issue_category"],
            severity=payload["severity"],
            blocking=payload["blocking"],
            blocking_category=payload.get("blocking_category"),
            summary=payload["summary"],
            detail=payload.get("detail"),
            source=payload["source"],
            status="open",
        )
        self.session.add(row)
        await self.session.flush()
        await self._event(row, "created", actor)
        await self._audit(row, "release.issue_created", actor)
        return row

    async def create_from_trusted_finding(
        self, *, project_id: uuid.UUID, finding_id: uuid.UUID, actor: str
    ) -> ReleaseIssue:
        """Create the single code-derived issue for one stored trusted Slice-44/45 finding."""

        finding = (
            await self.session.execute(
                select(ReleaseFinding).where(
                    ReleaseFinding.id == finding_id,
                    ReleaseFinding.tenant_id == self.context.tenant_id,
                    ReleaseFinding.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if finding is None:
            raise InvalidIssue("trusted finding is missing or outside project scope")
        derived = derive_issue_from_finding(self._finding_shape(finding))
        existing = await self.get_by_source_finding(finding_id)
        if existing is not None:
            self._require_material_match(existing, derived)
            return existing

        row = ReleaseIssue(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            source_finding_id=derived.source_finding_id,
            issue_category=derived.issue_category,
            severity=derived.severity,
            blocking=derived.blocking,
            blocking_category=derived.blocking_category,
            summary=derived.summary,
            detail=None,
            source=derived.source,
            source_provenance=derived.source_provenance,
            status="open",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_by_source_finding(finding_id)
            if existing is None:
                raise
            self._require_material_match(existing, derived)
            return existing
        await self._event(row, "created", actor)
        await self._audit(row, "release.issue_created", actor)
        return row

    async def get_by_source_finding(self, finding_id: uuid.UUID) -> ReleaseIssue | None:
        stmt = select(ReleaseIssue).where(
            ReleaseIssue.tenant_id == self.context.tenant_id,
            ReleaseIssue.source_finding_id == finding_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_trusted_for_project(
        self, project_id: uuid.UUID, *, limit: int
    ) -> list[ReleaseIssue]:
        if limit < 1 or limit > MAX_RECONCILIATION_FINDINGS:
            raise ValueError(f"limit must be between 1 and {MAX_RECONCILIATION_FINDINGS}")
        stmt = (
            select(ReleaseIssue)
            .where(
                ReleaseIssue.tenant_id == self.context.tenant_id,
                ReleaseIssue.project_id == project_id,
                ReleaseIssue.source_provenance == TRUSTED_FINDING_PROVENANCE,
                ReleaseIssue.source_finding_id.is_not(None),
            )
            .order_by(ReleaseIssue.created_at, ReleaseIssue.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def reconcile_trusted_findings(
        self, *, project_id: uuid.UUID, actor: str, limit: int
    ) -> int:
        """Idempotently bridge at most ``limit`` historical trusted findings."""

        if limit < 1 or limit > MAX_RECONCILIATION_FINDINGS:
            raise ValueError(f"limit must be between 1 and {MAX_RECONCILIATION_FINDINGS}")
        stmt = (
            select(ReleaseFinding)
            .outerjoin(
                ReleaseIssue,
                (ReleaseIssue.tenant_id == ReleaseFinding.tenant_id)
                & (ReleaseIssue.source_finding_id == ReleaseFinding.id),
            )
            .where(
                ReleaseFinding.tenant_id == self.context.tenant_id,
                ReleaseFinding.project_id == project_id,
                ReleaseFinding.status == "open",
                ReleaseFinding.source_provenance.in_(
                    (
                        "connector_verified_security_scan",
                        "system_executed_shortcut_review",
                    )
                ),
                ReleaseIssue.id.is_(None),
            )
            .order_by(ReleaseFinding.created_at, ReleaseFinding.id)
            .limit(limit)
        )
        findings = list((await self.session.execute(stmt)).scalars().all())
        for finding in findings:
            await self.create_from_trusted_finding(
                project_id=project_id, finding_id=finding.id, actor=actor
            )
        return len(findings)

    async def resolve(
        self, *, issue_id: uuid.UUID, resolution_note: str, resolved_by: str, actor: str
    ) -> ReleaseIssue:
        return await self._resolve_like(issue_id, "resolved", resolution_note, resolved_by, actor)

    async def supersede(
        self, *, issue_id: uuid.UUID, resolution_note: str, resolved_by: str, actor: str
    ) -> ReleaseIssue:
        return await self._resolve_like(issue_id, "superseded", resolution_note, resolved_by, actor)

    async def accept(
        self, *, issue_id: uuid.UUID, risk_acceptance_record_id: uuid.UUID, actor: str
    ) -> ReleaseIssue:
        row = await self._get_or_raise(issue_id)
        validate_transition(row.status, "accepted")
        # Repository-layer hard-block (defense in depth; the DB guard re-validates).
        if is_hard_blocker(row.severity, row.blocking_category):
            raise InvalidIssue("critical/hard-blocker issues cannot be accepted")
        row.status = "accepted"
        row.risk_acceptance_record_id = risk_acceptance_record_id
        row.updated_at = func.clock_timestamp()
        # The DB guard validates the referenced record is usable (active/non-expired/non-blocking/
        # same tenant+project/issue_id==issue.id) on flush.
        await self.session.flush()
        await self._event(row, "accepted", actor)
        await self._audit(row, "release.issue_accepted", actor)
        return row

    async def get(self, issue_id: uuid.UUID) -> ReleaseIssue | None:
        stmt = select(ReleaseIssue).where(
            ReleaseIssue.id == issue_id,
            ReleaseIssue.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_open(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id)

    async def count_open_blocking(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id, blocking=True)

    async def count_open_unaccepted_blocking(self, project_id: uuid.UUID) -> int:
        """An ``open`` issue is by definition not yet ``accepted``, so this equals
        ``count_open_blocking`` under the Slice-24 lifecycle. Kept as a distinct method per the
        approved A5 gate-#7 context contract (no fabricated distinction is claimed)."""
        return await self._count(project_id, blocking=True)

    async def _count(self, project_id: uuid.UUID, *, blocking: bool | None = None) -> int:
        conds = [
            ReleaseIssue.tenant_id == self.context.tenant_id,
            ReleaseIssue.project_id == project_id,
            ReleaseIssue.status == "open",
        ]
        if blocking is not None:
            conds.append(ReleaseIssue.blocking == blocking)
        return int((await self.session.execute(select(func.count()).where(*conds))).scalar_one())

    async def _resolve_like(
        self,
        issue_id: uuid.UUID,
        to_status: str,
        resolution_note: str,
        resolved_by: str,
        actor: str,
    ) -> ReleaseIssue:
        row = await self._get_or_raise(issue_id)
        validate_transition(row.status, to_status)
        row.status = to_status
        row.resolution_note = resolution_note
        row.resolved_by = resolved_by
        row.resolved_at = func.clock_timestamp()
        row.updated_at = func.clock_timestamp()
        await self.session.flush()
        await self._event(row, to_status, actor)
        await self._audit(row, f"release.issue_{to_status}", actor)
        return row

    async def _get_or_raise(self, issue_id: uuid.UUID) -> ReleaseIssue:
        row = await self.get(issue_id)
        if row is None:
            raise LookupError(f"release_issue {issue_id} not found in tenant scope")
        return row

    async def _event(self, row: ReleaseIssue, event_type: str, actor: str) -> None:
        self.session.add(
            ReleaseIssueEvent(
                tenant_id=self.context.tenant_id,
                issue_id=row.id,
                event_type=event_type,
                actor=actor,
            )
        )
        await self.session.flush()

    async def _audit(self, row: ReleaseIssue, action: str, actor: str) -> None:
        # Safe metadata only — NEVER summary/detail/resolution/blocking_category prose.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"release_issue:{row.id}",
            payload={
                "release_issue_id": str(row.id),
                "project_id": str(row.project_id),
                "issue_category": row.issue_category,
                "severity": row.severity,
                "blocking": row.blocking,
                "status": row.status,
                "source_provenance": row.source_provenance,
                "source_finding_id": (
                    str(row.source_finding_id) if row.source_finding_id is not None else None
                ),
            },
        )

    @staticmethod
    def _finding_shape(row: ReleaseFinding) -> Mapping:
        return {
            "id": row.id,
            "finding_type": row.finding_type,
            "category": row.category,
            "severity": row.severity,
            "status": row.status,
            "source_provenance": row.source_provenance,
            "security_scan_category_result_id": row.security_scan_category_result_id,
            "scan_finding_fingerprint": row.scan_finding_fingerprint,
            "shortcut_detector_category_result_id": row.shortcut_detector_category_result_id,
            "shortcut_finding_fingerprint": row.shortcut_finding_fingerprint,
        }

    @staticmethod
    def _require_material_match(
        row: ReleaseIssue, derived: TrustedFindingIssueDerivation
    ) -> None:
        material = (
            row.source_finding_id,
            row.issue_category,
            row.severity,
            row.blocking,
            row.blocking_category,
            row.summary,
            row.detail,
            row.source,
            row.source_provenance,
        )
        expected = (
            derived.source_finding_id,
            derived.issue_category,
            derived.severity,
            derived.blocking,
            derived.blocking_category,
            derived.summary,
            derived.detail,
            derived.source,
            derived.source_provenance,
        )
        if material != expected:
            raise InvalidIssue("existing finding bridge conflicts with code-owned derivation")
