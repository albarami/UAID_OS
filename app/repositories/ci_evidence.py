"""Tenant-scoped source-control / CI evidence repository (Slice 26, Appendix B #3 / §26.3).

``record_branch_protection`` validates a snapshot (fail-closed), stamps ``provenance =
'caller_supplied_unverified'`` (the only value writable this slice), derives the check count, and
persists an immutable row + an audit entry with **safe metadata only** (ids/provider/branch/booleans/
count/provenance — never ``repo_ref``, the check-name list, or any URL/token). ``latest_branch_protection``
returns the newest snapshot. The DB guard (migration ``0025``) is the authoritative backstop for the
provenance, ``repo_ref`` shape/token, and JSON-array invariants. These snapshots never enable go-live
and never let gate #3 PASS. Run inside ``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.branch_protection_snapshot import BranchProtectionSnapshot
from app.release.ci_evidence import derived_check_count, validate_new_snapshot
from app.tenancy import TenantContext, TenantScopedRepository


class CIEvidenceRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, BranchProtectionSnapshot)

    async def record_branch_protection(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> BranchProtectionSnapshot:
        validate_new_snapshot(payload)
        checks = list(payload.get("required_status_checks", []))
        row = BranchProtectionSnapshot(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider=payload["provider"],
            repo_ref=payload["repo_ref"],
            branch=payload["branch"],
            protection_enabled=payload["protection_enabled"],
            required_pull_request_reviews=payload["required_pull_request_reviews"],
            required_status_checks=checks,
            required_status_check_count=derived_check_count(checks),
            enforce_admins=payload["enforce_admins"],
            # provenance is repo-controlled, never caller-controlled (DB guard enforces it too).
            provenance="caller_supplied_unverified",
            observed_at=payload.get("observed_at"),
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, "ci.branch_protection_observed", actor)
        return row

    async def latest_branch_protection(
        self, project_id: uuid.UUID
    ) -> BranchProtectionSnapshot | None:
        stmt = (
            select(BranchProtectionSnapshot)
            .where(
                BranchProtectionSnapshot.tenant_id == self.context.tenant_id,
                BranchProtectionSnapshot.project_id == project_id,
            )
            .order_by(
                BranchProtectionSnapshot.created_at.desc(),
                BranchProtectionSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_branch_protection_snapshots(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id)

    async def count_connector_verified_branch_protection(self, project_id: uuid.UUID) -> int:
        # Always 0 this slice (the verified tier is unwritable) — surfaced so the A5 report makes
        # "no verified evidence" explicit rather than implicit.
        return await self._count(project_id, provenance="connector_verified")

    async def _count(self, project_id: uuid.UUID, provenance: str | None = None) -> int:
        stmt = select(func.count()).where(
            BranchProtectionSnapshot.tenant_id == self.context.tenant_id,
            BranchProtectionSnapshot.project_id == project_id,
        )
        if provenance is not None:
            stmt = stmt.where(BranchProtectionSnapshot.provenance == provenance)
        return int((await self.session.execute(stmt)).scalar_one())

    async def _audit(self, row: BranchProtectionSnapshot, action: str, actor: str) -> None:
        # Safe metadata only — NEVER repo_ref, the required_status_checks list, or any URL/token.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"branch_protection_snapshot:{row.id}",
            payload={
                "branch_protection_snapshot_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "branch": row.branch,
                "protection_enabled": row.protection_enabled,
                "required_status_check_count": row.required_status_check_count,
                "provenance": row.provenance,
            },
        )
