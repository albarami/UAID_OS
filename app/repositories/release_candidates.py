"""Tenant-scoped release-candidate / release-binding repository (Slice 25, §24.1/§24.2/Appendix B #7).

``create`` validates + persists a ``draft`` candidate; ``freeze``/``supersede``/``cancel`` drive the
one-way lifecycle (the DB guard is the authoritative backstop); ``bind_issue`` adds a freeze-locked
issue binding (DB guard enforces draft + project match). Count helpers feed the conservative A5
gate #7. Every transition writes an append-only event + an audit entry with **safe metadata only**
(ids / release_ref / status — never ``title``/prose). Bindings declare KNOWN issues for a release —
**not** a completeness claim; gate #7 never passes. Run inside ``tenant_scope``; ``actor`` is an
untrusted caller label.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.release_candidate import ReleaseCandidate
from app.models.release_candidate_event import ReleaseCandidateEvent
from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
from app.models.release_issue import ReleaseIssue
from app.release.release_candidates import validate_new_candidate, validate_transition
from app.tenancy import TenantContext, TenantScopedRepository


class ReleaseCandidateRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReleaseCandidate)

    async def create(self, *, project_id: uuid.UUID, payload: dict, actor: str) -> ReleaseCandidate:
        validate_new_candidate(payload)
        row = ReleaseCandidate(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_ref=payload["release_ref"],
            title=payload.get("title"),
            status="draft",
        )
        self.session.add(row)
        await self.session.flush()
        await self._event(row, "created", actor)
        await self._audit(row, "release.candidate_created", actor)
        return row

    async def freeze(self, *, candidate_id: uuid.UUID, actor: str) -> ReleaseCandidate:
        row = await self._get_or_raise(candidate_id)
        validate_transition(row.status, "frozen")
        row.status = "frozen"
        row.frozen_at = func.clock_timestamp()
        row.updated_at = func.clock_timestamp()
        await self.session.flush()
        await self._event(row, "frozen", actor)
        await self._audit(row, "release.candidate_frozen", actor)
        return row

    async def supersede(self, *, candidate_id: uuid.UUID, actor: str) -> ReleaseCandidate:
        return await self._transition(candidate_id, "superseded", actor)

    async def cancel(self, *, candidate_id: uuid.UUID, actor: str) -> ReleaseCandidate:
        return await self._transition(candidate_id, "canceled", actor)

    async def bind_issue(
        self, *, candidate_id: uuid.UUID, release_issue_id: uuid.UUID, actor: str
    ) -> ReleaseCandidateIssueBinding:
        candidate = await self._get_or_raise(candidate_id)
        binding = ReleaseCandidateIssueBinding(
            tenant_id=self.context.tenant_id,
            project_id=candidate.project_id,
            release_candidate_id=candidate.id,
            release_issue_id=release_issue_id,
        )
        self.session.add(binding)
        # The DB guard enforces candidate=draft + issue project match on flush.
        await self.session.flush()
        await self._event(candidate, "issue_bound", actor)
        await self._audit_binding(candidate, release_issue_id, actor)
        return binding

    async def get(self, candidate_id: uuid.UUID) -> ReleaseCandidate | None:
        stmt = select(ReleaseCandidate).where(
            ReleaseCandidate.id == candidate_id,
            ReleaseCandidate.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[ReleaseCandidate]:
        stmt = (
            select(ReleaseCandidate)
            .where(
                ReleaseCandidate.tenant_id == self.context.tenant_id,
                ReleaseCandidate.project_id == project_id,
            )
            .order_by(ReleaseCandidate.created_at.desc(), ReleaseCandidate.id.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # --- A5 gate #7 count helpers --------------------------------------------

    async def count_frozen(self, project_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            ReleaseCandidate.tenant_id == self.context.tenant_id,
            ReleaseCandidate.project_id == project_id,
            ReleaseCandidate.status == "frozen",
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def latest_frozen(self, project_id: uuid.UUID) -> ReleaseCandidate | None:
        stmt = (
            select(ReleaseCandidate)
            .where(
                ReleaseCandidate.tenant_id == self.context.tenant_id,
                ReleaseCandidate.project_id == project_id,
                ReleaseCandidate.status == "frozen",
            )
            .order_by(
                ReleaseCandidate.frozen_at.desc(),
                ReleaseCandidate.created_at.desc(),
                ReleaseCandidate.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def bound_open_issue_count(self, candidate_id: uuid.UUID) -> int:
        return await self._bound_count(candidate_id)

    async def bound_open_blocking_issue_count(self, candidate_id: uuid.UUID) -> int:
        return await self._bound_count(candidate_id, blocking=True)

    async def bound_open_unaccepted_blocking_issue_count(self, candidate_id: uuid.UUID) -> int:
        """An ``open`` issue is by definition not yet ``accepted``, so this equals
        ``bound_open_blocking_issue_count`` under the lifecycle (documented, no fabricated
        distinction; kept distinct per the A5 gate-#7 context contract)."""
        return await self._bound_count(candidate_id, blocking=True)

    async def _bound_count(self, candidate_id: uuid.UUID, *, blocking: bool | None = None) -> int:
        conds = [
            ReleaseCandidateIssueBinding.tenant_id == self.context.tenant_id,
            ReleaseCandidateIssueBinding.release_candidate_id == candidate_id,
            ReleaseIssue.status == "open",
        ]
        if blocking is not None:
            conds.append(ReleaseIssue.blocking == blocking)
        stmt = (
            select(func.count())
            .select_from(ReleaseCandidateIssueBinding)
            .join(
                ReleaseIssue,
                (ReleaseIssue.id == ReleaseCandidateIssueBinding.release_issue_id)
                & (ReleaseIssue.tenant_id == ReleaseCandidateIssueBinding.tenant_id),
            )
            .where(*conds)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    # --- internals ------------------------------------------------------------

    async def _transition(
        self, candidate_id: uuid.UUID, to_status: str, actor: str
    ) -> ReleaseCandidate:
        row = await self._get_or_raise(candidate_id)
        validate_transition(row.status, to_status)
        row.status = to_status
        row.updated_at = func.clock_timestamp()
        await self.session.flush()
        await self._event(row, to_status, actor)
        await self._audit(row, f"release.candidate_{to_status}", actor)
        return row

    async def _get_or_raise(self, candidate_id: uuid.UUID) -> ReleaseCandidate:
        row = await self.get(candidate_id)
        if row is None:
            raise LookupError(f"release_candidate {candidate_id} not found in tenant scope")
        return row

    async def _event(self, row: ReleaseCandidate, event_type: str, actor: str) -> None:
        self.session.add(
            ReleaseCandidateEvent(
                tenant_id=self.context.tenant_id,
                release_candidate_id=row.id,
                event_type=event_type,
                actor=actor,
            )
        )
        await self.session.flush()

    async def _audit(self, row: ReleaseCandidate, action: str, actor: str) -> None:
        # Safe metadata only — NEVER title/prose.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"release_candidate:{row.id}",
            payload={
                "release_candidate_id": str(row.id),
                "project_id": str(row.project_id),
                "release_ref": row.release_ref,
                "status": row.status,
            },
        )

    async def _audit_binding(
        self, candidate: ReleaseCandidate, release_issue_id: uuid.UUID, actor: str
    ) -> None:
        await audit_record(
            self.session,
            action="release.issue_bound",
            actor=actor,
            target=f"release_candidate:{candidate.id}",
            payload={
                "release_candidate_id": str(candidate.id),
                "project_id": str(candidate.project_id),
                "release_ref": candidate.release_ref,
                "release_issue_id": str(release_issue_id),
            },
        )
