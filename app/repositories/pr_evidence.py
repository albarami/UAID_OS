"""Tenant-scoped pull-request evidence repository (Slice 29, §12.3-12.4; App. B #7/#8 feed).

``record_pull_request`` (caller path) stamps ``provenance='caller_supplied_unverified'``;
``record_connector_verified_pull_request`` (connector path, after a verified fetch) stamps
``provenance='connector_verified'``. Both: validate fail-closed; **derive** the Q3 separation flags +
the canonical ``approval_count = len(approver_principals)`` (so the DB invariant holds); compute the
**observed** ``merged_to_declared_protected_branch_observed`` by cross-referencing the Slice-26/28
``branch_protection_snapshots`` store (true only when the base branch has a ``connector_verified`` +
protection-enabled + **fresh** snapshot for the same repo — B-29-2); **validate** ``traceability_refs``
existence/kind/project against ``release_issues`` + ``intake_artifacts`` (B-29-3); persist an immutable
row + an audit entry with **safe metadata only** (ids/provider/pr_number/state/booleans/provenance —
never ``repo_ref``, principals, the check-name list, traceability UUIDs, or any URL/token). Store-only:
**no A5 gate flip, no ``production_autonomy`` change, ruleset stays ``slice28.v1``.** Run inside
``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.config import settings
from app.models.pull_request_evidence_snapshot import PullRequestEvidenceSnapshot
from app.release.pr_evidence import (
    InvalidPullRequestSnapshot,
    derive_separation_flags,
    parse_iso_timestamp,
    validate_connector_pull_request,
    validate_new_pull_request,
    validate_traceability_refs_shape,
)
from app.release.project_repo import resolve_declared_repo
from app.tenancy import TenantContext, TenantScopedRepository


def _is_fresh(row) -> bool:
    """Branch-protection evidence is fresh iff observed within CI_EVIDENCE_MAX_AGE_HOURS (Slice 28)."""
    if row is None or row.observed_at is None:
        return False
    max_age = timedelta(hours=settings.ci_evidence_max_age_hours)
    return (datetime.now(timezone.utc) - row.observed_at) <= max_age


class PullRequestEvidenceRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, PullRequestEvidenceSnapshot)

    async def record_pull_request(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> PullRequestEvidenceSnapshot:
        validate_new_pull_request(payload)
        return await self._record(
            project_id, payload, "caller_supplied_unverified", actor, "pr.evidence_observed"
        )

    async def record_connector_verified_pull_request(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> PullRequestEvidenceSnapshot:
        """Connector path — reached ONLY after a verified PR+reviews fetch; provenance is
        repo-controlled, ``observed_at`` required by ``validate_connector_pull_request``."""
        validate_connector_pull_request(payload)
        return await self._record(
            project_id, payload, "connector_verified", actor, "pr.evidence_verified"
        )

    async def _record(
        self, project_id: uuid.UUID, payload: dict, provenance: str, actor: str, action: str
    ) -> PullRequestEvidenceSnapshot:
        refs = payload.get("traceability_refs") or {}
        await self._validate_traceability_refs(project_id, refs)
        approvers = list(payload.get("approver_principals") or [])
        flags = derive_separation_flags(
            author_principal=payload.get("author_principal"),
            approver_principals=approvers,
            merger_principal=payload.get("merger_principal"),
            merged=bool(payload.get("merged")),
        )
        merged_protected = await self._compute_merged_protected(
            project_id,
            merged=bool(payload.get("merged")),
            base_branch=payload.get("base_branch"),
            repo_ref=payload["repo_ref"],
        )
        row = PullRequestEvidenceSnapshot(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider=payload["provider"],
            repo_ref=payload["repo_ref"],
            pr_number=payload["pr_number"],
            pr_state=payload["pr_state"],
            merged=payload["merged"],
            merged_at=parse_iso_timestamp(payload.get("merged_at")),
            merge_commit_sha=payload.get("merge_commit_sha"),
            base_branch=payload.get("base_branch"),
            base_sha=payload.get("base_sha"),
            head_branch=payload.get("head_branch"),
            head_sha=payload.get("head_sha"),
            merged_to_declared_protected_branch_observed=merged_protected,
            check_status_summary=payload.get("check_status_summary"),
            presence_flags=payload.get("presence_flags") or {},
            author_principal=payload.get("author_principal"),
            approver_principals=approvers,
            reviewer_principals=list(payload.get("reviewer_principals") or []),
            requested_reviewer_principals=list(payload.get("requested_reviewer_principals") or []),
            requested_reviewers_observed=bool(payload.get("requested_reviewers_observed", False)),
            merger_principal=payload.get("merger_principal"),
            approval_count=len(approvers),  # canonical; matches the DB derived-count invariant
            self_approval_observed=flags["self_approval_observed"],
            self_merge_observed=flags["self_merge_observed"],
            review_separation_observed=flags["review_separation_observed"],
            traceability_refs=refs,
            provenance=provenance,
            observed_at=payload.get("observed_at"),
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, action, actor)
        return row

    async def _validate_traceability_refs(self, project_id: uuid.UUID, refs: dict) -> None:
        """B-29-3: same-project ``release_issues`` + ``kind='acceptance_criterion'`` intake artifacts;
        wrong-project / missing / wrong-kind / duplicate ⇒ fail closed."""
        if not refs:
            return
        validate_traceability_refs_shape(refs)
        from app.repositories.intake import IntakeRepository
        from app.repositories.release_issues import ReleaseIssueRepository

        issue_ids = list(refs.get("release_issue_ids") or [])
        if len(set(issue_ids)) != len(issue_ids):
            raise InvalidPullRequestSnapshot("duplicate release_issue_ids")
        ac_ids = list(refs.get("acceptance_criterion_ids") or [])
        if len(set(ac_ids)) != len(ac_ids):
            raise InvalidPullRequestSnapshot("duplicate acceptance_criterion_ids")

        issues = ReleaseIssueRepository(self.session, self.context)
        for iid in issue_ids:
            row = await issues.get(uuid.UUID(iid))
            if row is None or row.project_id != project_id:
                raise InvalidPullRequestSnapshot(f"unknown or cross-project release_issue: {iid}")
        intake = IntakeRepository(self.session, self.context)
        for aid in ac_ids:
            art = await intake.get_artifact(uuid.UUID(aid))
            if art is None or art.project_id != project_id or art.kind != "acceptance_criterion":
                raise InvalidPullRequestSnapshot(
                    f"unknown, cross-project, or wrong-kind acceptance_criterion: {aid}"
                )

    async def _compute_merged_protected(
        self, project_id: uuid.UUID, *, merged: bool, base_branch, repo_ref: str
    ) -> bool:
        """B-29-2: an *observed* (not asserted) merged-to-protected fact. True only when the PR merged
        INTO the project's currently **declared** protected branch (``resolve_declared_repo``) AND that
        declared repo/branch has a ``connector_verified`` + protection-enabled + fresh branch-protection
        snapshot (cross-ref the Slice-26/28 store). A PR merged into a protected-but-not-declared branch
        does NOT count — the field name promises 'declared'. False ≠ 'definitely unprotected'."""
        if not merged or not base_branch:
            return False
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            return False
        declared_repo, declared_branch = declared
        if repo_ref != declared_repo or base_branch != declared_branch:
            return False
        from app.repositories.ci_evidence import CIEvidenceRepository

        bp = await CIEvidenceRepository(
            self.session, self.context
        ).latest_branch_protection_for_repo(project_id, declared_repo, declared_branch)
        if bp is None or bp.provenance != "connector_verified" or not bp.protection_enabled:
            return False
        return _is_fresh(bp)

    async def latest_pull_request_for_pr(
        self, project_id: uuid.UUID, provider: str, repo_ref: str, pr_number: int
    ) -> PullRequestEvidenceSnapshot | None:
        stmt = (
            select(PullRequestEvidenceSnapshot)
            .where(
                PullRequestEvidenceSnapshot.tenant_id == self.context.tenant_id,
                PullRequestEvidenceSnapshot.project_id == project_id,
                PullRequestEvidenceSnapshot.provider == provider,
                PullRequestEvidenceSnapshot.repo_ref == repo_ref,
                PullRequestEvidenceSnapshot.pr_number == pr_number,
            )
            .order_by(
                PullRequestEvidenceSnapshot.created_at.desc(),
                PullRequestEvidenceSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_pull_request(
        self, project_id: uuid.UUID
    ) -> PullRequestEvidenceSnapshot | None:
        stmt = (
            select(PullRequestEvidenceSnapshot)
            .where(
                PullRequestEvidenceSnapshot.tenant_id == self.context.tenant_id,
                PullRequestEvidenceSnapshot.project_id == project_id,
            )
            .order_by(
                PullRequestEvidenceSnapshot.created_at.desc(),
                PullRequestEvidenceSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_pull_request_snapshots(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id)

    async def count_connector_verified_pull_requests(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id, provenance="connector_verified")

    async def _count(self, project_id: uuid.UUID, provenance: str | None = None) -> int:
        stmt = select(func.count()).where(
            PullRequestEvidenceSnapshot.tenant_id == self.context.tenant_id,
            PullRequestEvidenceSnapshot.project_id == project_id,
        )
        if provenance is not None:
            stmt = stmt.where(PullRequestEvidenceSnapshot.provenance == provenance)
        return int((await self.session.execute(stmt)).scalar_one())

    async def _audit(self, row: PullRequestEvidenceSnapshot, action: str, actor: str) -> None:
        # Safe metadata only — NEVER repo_ref, principals, traceability UUIDs, check-names, URL/token.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"pull_request_evidence_snapshot:{row.id}",
            payload={
                "pull_request_evidence_snapshot_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "pr_number": row.pr_number,
                "pr_state": row.pr_state,
                "merged": row.merged,
                "provenance": row.provenance,
                "approval_count": row.approval_count,
                "self_approval_observed": row.self_approval_observed,
                "self_merge_observed": row.self_merge_observed,
                "merged_to_declared_protected_branch_observed": (
                    row.merged_to_declared_protected_branch_observed
                ),
            },
        )
