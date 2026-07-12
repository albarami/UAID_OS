"""Connector-controlled Slice-44 security scan persistence and gate coverage."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.release_finding import ReleaseFinding
from app.models.release_finding_event import ReleaseFindingEvent
from app.models.security_scan_category_result import SecurityScanCategoryResult
from app.models.security_scan_run import SecurityScanRun
from app.release.project_repo import resolve_declared_repo
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.release_issues import ReleaseIssueRepository
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.security_scan import (
    MANDATORY_CATEGORIES,
    SCHEMA_VERSION,
    CategoryCoverage,
    Gate5Evidence,
    SecurityScanArtifact,
    canonical_digest,
    code_owned_manifest_hash,
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class SecurityScanRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, SecurityScanRun)

    async def execute_ci(
        self,
        *,
        project_id: uuid.UUID,
        commit_sha: str,
        connector: SCMConnector,
        actor: str,
    ) -> SecurityScanRun:
        if _COMMIT_RE.fullmatch(commit_sha) is None:
            raise ValueError("commit_sha must be 40 lowercase hexadecimal characters")
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            raise ValueError("project has no valid declared repository")
        repo_ref, _branch = declared
        repo_hash = canonical_digest(repo_ref)
        try:
            artifact = await connector.fetch_security_scan_artifact(
                repo_ref=repo_ref, commit_sha=commit_sha
            )
        except (SCMConnectorError, ValueError):
            return await self._record_failure(
                project_id, repo_hash, commit_sha, "connector_failure", actor
            )
        if artifact is None:
            return await self._record_failure(
                project_id, repo_hash, commit_sha, "artifact_missing", actor
            )
        return await self._record_observation(project_id, repo_hash, artifact, actor)

    async def coverage_for_project(self, project_id: uuid.UUID) -> Gate5Evidence:
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            return self._empty(binding=False)
        repo_hash = canonical_digest(declared[0])
        latest = (
            await self.session.execute(
                select(SecurityScanRun)
                .where(
                    SecurityScanRun.tenant_id == self.context.tenant_id,
                    SecurityScanRun.project_id == project_id,
                    SecurityScanRun.repo_binding_hash == repo_hash,
                    SecurityScanRun.scanner_manifest_hash == code_owned_manifest_hash(),
                )
                .order_by(SecurityScanRun.created_at.desc(), SecurityScanRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return self._empty(binding=True)
        categories = list(
            (
                await self.session.execute(
                    select(SecurityScanCategoryResult).where(
                        SecurityScanCategoryResult.tenant_id == self.context.tenant_id,
                        SecurityScanCategoryResult.project_id == project_id,
                        SecurityScanCategoryResult.security_scan_run_id == latest.id,
                    )
                )
            ).scalars()
        )
        completed = sum(
            row.coverage_status in {"completed_clean", "completed_with_findings"}
            for row in categories
        )
        return Gate5Evidence(
            scope_resolved=True,
            binding_resolved=True,
            run_present=True,
            artifact_trusted=(
                latest.artifact_provenance == "connector_verified_ci_security"
            ),
            execution_failed=latest.execution_status in {"failed", "refused"},
            coverage_complete=latest.coverage_complete,
            evidence_consistent=True,
            mandatory_category_count=len(MANDATORY_CATEGORIES),
            completed_category_count=completed,
            failed_category_count=len(categories) - completed,
            finding_count=latest.reported_finding_count,
        )

    async def _record_failure(
        self,
        project_id: uuid.UUID,
        repo_hash: str,
        commit_sha: str,
        failure_code: str,
        actor: str,
    ) -> SecurityScanRun:
        row = SecurityScanRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider="github",
            repo_binding_hash=repo_hash,
            commit_sha=commit_sha,
            artifact_schema_version=SCHEMA_VERSION,
            scanner_manifest_hash=code_owned_manifest_hash(),
            artifact_digest=None,
            execution_status="failed",
            artifact_provenance="caller_supplied_unverified",
            execution_observation="connector_attempted",
            failure_code=failure_code,
            reported_category_count=0,
            reported_finding_count=0,
            coverage_complete=False,
            coverage_verdict="failed",
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def _record_observation(
        self,
        project_id: uuid.UUID,
        repo_hash: str,
        artifact: SecurityScanArtifact,
        actor: str,
    ) -> SecurityScanRun:
        row = SecurityScanRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider="github",
            repo_binding_hash=repo_hash,
            commit_sha=artifact.commit_sha,
            artifact_schema_version=artifact.schema_version,
            scanner_manifest_hash=artifact.scanner_manifest_hash,
            artifact_digest=artifact.artifact_digest,
            execution_status="succeeded",
            artifact_provenance="connector_verified_ci_security",
            execution_observation="connector_observed_ci",
            failure_code=None,
            reported_category_count=len(artifact.categories),
            reported_finding_count=artifact.coverage.finding_count,
            coverage_complete=artifact.coverage.complete,
            coverage_verdict="covered" if artifact.coverage.complete else "failed",
        )
        self.session.add(row)
        await self.session.flush()
        for category in artifact.categories:
            await self._record_category(row, category, actor)
        await self._audit(row, actor)
        return row

    async def _record_category(
        self, run: SecurityScanRun, category: CategoryCoverage, actor: str
    ) -> None:
        safe_evidence = {
            "category": category.category,
            "scanner_key": category.scanner_key,
            "scanner_version": category.scanner_version,
            "rule_pack_hash": category.rule_pack_hash,
            "coverage_status": category.coverage_status,
            "finding_fingerprints": sorted(item.fingerprint for item in category.findings),
        }
        result = SecurityScanCategoryResult(
            tenant_id=self.context.tenant_id,
            project_id=run.project_id,
            security_scan_run_id=run.id,
            category=category.category,
            scanner_key=category.scanner_key,
            scanner_version=category.scanner_version,
            rule_pack_hash=category.rule_pack_hash,
            coverage_status=category.coverage_status,
            reported_finding_count=len(category.findings),
            evidence_digest=canonical_digest(safe_evidence),
        )
        self.session.add(result)
        await self.session.flush()
        for finding in category.findings:
            row = ReleaseFinding(
                tenant_id=self.context.tenant_id,
                project_id=run.project_id,
                finding_type="security",
                category=category.category,
                severity=finding.severity,
                summary=finding.summary,
                detail=finding.detail,
                source=category.scanner_key,
                source_provenance="connector_verified_security_scan",
                status="open",
                security_scan_category_result_id=result.id,
                scan_finding_fingerprint=finding.fingerprint,
            )
            self.session.add(row)
            await self.session.flush()
            self.session.add(
                ReleaseFindingEvent(
                    tenant_id=self.context.tenant_id,
                    finding_id=row.id,
                    event_type="created",
                    actor=actor,
                )
            )
            await ReleaseIssueRepository(
                self.session, self.context
            ).create_from_trusted_finding(
                project_id=run.project_id,
                finding_id=row.id,
                actor=actor,
            )
        await self.session.flush()

    async def _audit(self, row: SecurityScanRun, actor: str) -> None:
        # No repo, commit, URL, finding text, evidence ref, fingerprint, or raw artifact.
        await audit_record(
            self.session,
            action="release.security_scan_observed",
            actor=actor,
            target=f"security_scan_run:{row.id}",
            payload={
                "security_scan_run_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "execution_status": row.execution_status,
                "artifact_provenance": row.artifact_provenance,
                "execution_observation": row.execution_observation,
                "failure_code": row.failure_code,
                "reported_category_count": row.reported_category_count,
                "reported_finding_count": row.reported_finding_count,
                "coverage_complete": row.coverage_complete,
                "artifact_schema_version": row.artifact_schema_version,
                "scanner_manifest_hash": row.scanner_manifest_hash,
            },
        )

    @staticmethod
    def _empty(*, binding: bool) -> Gate5Evidence:
        return Gate5Evidence(
            scope_resolved=True,
            binding_resolved=binding,
            run_present=False,
            artifact_trusted=False,
            execution_failed=False,
            coverage_complete=False,
            evidence_consistent=True,
            mandatory_category_count=len(MANDATORY_CATEGORIES),
            completed_category_count=0,
            failed_category_count=0,
            finding_count=0,
        )
