"""Tenant-scoped document intake repository (Slice 9, §16.3).

``ingest`` validates + scans + stores a document (idempotent on content hash);
``quarantine`` is the reviewer's one-way ``accepted→quarantined`` path; ``list_usable``
returns only accepted documents. Run inside ``tenant_scope`` (GUC set). Audit carries
metadata + marker identifiers only — never the document body. ``filename``/``source``
are untrusted caller labels (validated/bounded).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.intake.sandbox import (
    content_hash as compute_hash,
)
from app.intake.sandbox import (
    content_size_bytes,
    scan,
    validate_content,
    validate_content_type,
    validate_filename,
    validate_source,
)
from app.models.document import Document
from app.tenancy import TenantContext, TenantScopedRepository


class DocumentRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, Document)

    async def ingest(
        self,
        *,
        project_id: uuid.UUID,
        filename: str,
        content_type: str,
        source: str,
        content: str,
        actor: str,
    ) -> Document:
        """Validate → scan → store (idempotent on content hash). Audited on insert only."""
        validate_filename(filename)
        validate_content_type(content_type)
        validate_source(source)
        validate_content(content)
        chash = compute_hash(content)
        size = content_size_bytes(content)
        result = scan(content)
        status = "quarantined" if result.suspicious else "accepted"
        reason = ",".join(result.markers) if result.suspicious else None

        stmt = (
            pg_insert(Document)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                filename=filename,
                content_type=content_type,
                source=source,
                content=content,
                content_hash=chash,
                size_bytes=size,
                status=status,
                scan_result=result.as_dict(),
                quarantine_reason=reason,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "project_id", "content_hash"])
            .returning(Document.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            # Idempotent re-ingest: identical content already stored — return it, no audit.
            return await self._by_hash(project_id, chash)
        doc = await self.get(new_id)
        await self._audit(doc, "document.ingested", actor)
        return doc

    async def quarantine(self, *, document_id: uuid.UUID, reason: str, actor: str) -> Document:
        """Reviewer one-way quarantine (`accepted→quarantined`). Idempotent if already quarantined."""
        doc = await self.get(document_id)
        if doc is None:
            raise LookupError(str(document_id))
        if doc.status == "quarantined":
            return doc  # already quarantined — no-op, no duplicate audit
        doc.status = "quarantined"
        doc.quarantine_reason = reason
        await self.session.flush()
        await self._audit(doc, "document.quarantined", actor)
        return doc

    async def list_usable(self, project_id: uuid.UUID):
        """Accepted (non-quarantined) documents for the project, scoped to the tenant."""
        stmt = select(Document).where(
            Document.tenant_id == self.context.tenant_id,
            Document.project_id == project_id,
            Document.status == "accepted",
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def _by_hash(self, project_id: uuid.UUID, chash: str) -> Document:
        stmt = select(Document).where(
            Document.tenant_id == self.context.tenant_id,
            Document.project_id == project_id,
            Document.content_hash == chash,
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def _audit(self, doc: Document, action: str, actor: str) -> None:
        # Safe metadata + marker identifiers only — NEVER the document body.
        # ``actor`` is the (untrusted) caller label; ``source`` stays as metadata.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"document:{doc.id}",
            payload={
                "document_id": str(doc.id),
                "project_id": str(doc.project_id),
                "filename": doc.filename,
                "content_type": doc.content_type,
                "source": doc.source,
                "status": doc.status,
                "content_hash": doc.content_hash,
                "markers": (doc.scan_result or {}).get("markers", []),
            },
        )
