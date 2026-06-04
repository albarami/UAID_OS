"""Tenant-scoped canonical intake repository (Slice 11, §3.4/§4.2).

``add_artifact`` persists a provenance-backed artifact: it validates kind +
classification, fails closed if no source is supplied (Sanad / No-Free-Facts),
pre-checks every document-backed source against the tenant-scoped document store
(must exist, be ``accepted``, and belong to the same project), then writes the
artifact + its sources in one transaction. The DB is the backstop — a deferrable
constraint trigger rejects a committed artifact with zero provenance, a composite FK
pins document sources to the same tenant/project, and a BEFORE INSERT trigger rejects
non-accepted documents. Run inside ``tenant_scope`` (GUC set). Audit carries safe
metadata only — never the artifact title/body/data. ``actor`` is an untrusted label.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.intake.compiler import (
    SourceInput,
    assert_sources,
    validate_classification,
    validate_kind,
)
from app.models.intake_artifact import IntakeArtifact
from app.models.intake_provenance import IntakeProvenance
from app.repositories.documents import DocumentRepository
from app.tenancy import TenantContext, TenantScopedRepository


class IntakeRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, IntakeArtifact)

    async def add_artifact(
        self,
        *,
        project_id: uuid.UUID,
        kind: str,
        ref: str,
        title: str,
        sources: list[SourceInput],
        body: str | None = None,
        data: dict | None = None,
        classification: str | None = None,
        parent_id: uuid.UUID | None = None,
        actor: str,
    ) -> IntakeArtifact:
        """Validate → fail-closed on no source → store artifact + provenance → audit."""
        validate_kind(kind)
        validate_classification(kind, classification)
        # Fail closed before any DB write (the DB constraint trigger is the backstop).
        assert_sources(title, sources)

        # Pre-check document-backed sources against the tenant-scoped document store.
        docs = DocumentRepository(self.session, self.context)
        for src in sources:
            if src.document_id is not None:
                doc = await docs.get(src.document_id)
                if doc is None:
                    raise ValueError(f"unknown document {src.document_id} for this tenant")
                if doc.project_id != project_id:
                    raise ValueError(f"document {src.document_id} belongs to another project")
                if doc.status != "accepted":
                    raise ValueError(f"document {src.document_id} is not accepted")

        artifact = IntakeArtifact(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            kind=kind,
            ref=ref,
            title=title,
            body=body,
            data=data or {},
            classification=classification,
            parent_id=parent_id,
        )
        self.session.add(artifact)
        await self.session.flush()  # assign artifact.id (and surface duplicate-ref/parent FK)

        for src in sources:
            self.session.add(
                IntakeProvenance(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    artifact_id=artifact.id,
                    document_id=src.document_id,
                    origin=src.origin,
                    locator=src.locator,
                )
            )
        await self.session.flush()

        await self._audit(artifact, sources, actor)
        return artifact

    async def get_artifact(self, artifact_id: uuid.UUID) -> IntakeArtifact | None:
        return await self.get(artifact_id)

    async def list_artifacts(
        self, project_id: uuid.UUID, kind: str | None = None
    ) -> Sequence[IntakeArtifact]:
        stmt = select(IntakeArtifact).where(
            IntakeArtifact.tenant_id == self.context.tenant_id,
            IntakeArtifact.project_id == project_id,
        )
        if kind is not None:
            stmt = stmt.where(IntakeArtifact.kind == kind)
        return (await self.session.execute(stmt)).scalars().all()

    async def sources_for(self, artifact_id: uuid.UUID) -> Sequence[IntakeProvenance]:
        stmt = select(IntakeProvenance).where(
            IntakeProvenance.tenant_id == self.context.tenant_id,
            IntakeProvenance.artifact_id == artifact_id,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def _audit(
        self, artifact: IntakeArtifact, sources: list[SourceInput], actor: str
    ) -> None:
        # Safe metadata only — NEVER the artifact title/body/data (tenant content).
        document_ids = [str(s.document_id) for s in sources if s.document_id is not None]
        await audit_record(
            self.session,
            action="intake.artifact_added",
            actor=actor,
            target=f"intake_artifact:{artifact.id}",
            payload={
                "artifact_id": str(artifact.id),
                "project_id": str(artifact.project_id),
                "kind": artifact.kind,
                "ref": artifact.ref,
                "classification": artifact.classification,
                "source_count": len(sources),
                "document_ids": document_ids,
            },
        )
