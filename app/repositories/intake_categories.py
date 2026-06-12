"""Tenant-scoped intake-category repository (Slice 15, §4.2).

``declare`` records a declared intake category (one per project per category); ``revise``
updates an existing declaration's mutable fields. Both validate the category (must be a
declarable §4.2 category — not a spine kind or a gated-engine policy), the data (non-secret;
reference-only for secrets), and the source (document XOR origin, fail-closed). A
document-backed source is pre-checked against the tenant-scoped document store (exists,
accepted, same project). Audit carries **safe metadata only** — never the summary, data,
locator, secret references, or document body. Run inside ``tenant_scope``.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.intake.categories import (
    validate_category_data,
    validate_declarable_category,
    validate_source,
)
from app.models.intake_category import IntakeCategory
from app.repositories.documents import DocumentRepository
from app.tenancy import TenantContext, TenantScopedRepository

_VALID_STATUS = ("declared", "not_applicable")


class IntakeCategoryRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, IntakeCategory)

    async def declare(
        self,
        *,
        project_id: uuid.UUID,
        category: str,
        actor: str,
        status: str = "declared",
        summary: str | None = None,
        data: dict | None = None,
        source_document_id: uuid.UUID | None = None,
        locator: str | None = None,
        origin: str | None = None,
    ) -> IntakeCategory:
        """Insert a new declaration (fails on a duplicate category for the project)."""
        self._validate(category, status, data, source_document_id, locator, origin)
        await self._check_document(project_id, source_document_id)
        rec = IntakeCategory(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            category=category,
            status=status,
            summary=summary,
            data=data or {},
            source_document_id=source_document_id,
            locator=locator,
            origin=origin,
        )
        self.session.add(rec)
        await self.session.flush()  # assign id + surface UNIQUE(tenant,project,category)
        await self._audit(rec, "intake.category_declared", actor)
        return rec

    async def revise(
        self,
        *,
        project_id: uuid.UUID,
        category: str,
        actor: str,
        status: str | None = None,
        summary: str | None = None,
        data: dict | None = None,
        source_document_id: uuid.UUID | None = None,
        locator: str | None = None,
        origin: str | None = None,
    ) -> IntakeCategory:
        """Revise an existing declaration's mutable fields (category/keys stay immutable)."""
        rec = await self._get(project_id, category)
        if rec is None:
            raise LookupError(f"no {category!r} declaration for this project")
        new_status = status if status is not None else rec.status
        # Determine the resulting source (allow switching doc<->origin, still XOR-valid).
        if source_document_id is not None or origin is not None:
            new_doc, new_loc, new_origin = source_document_id, locator, origin
        else:
            new_doc, new_loc, new_origin = rec.source_document_id, rec.locator, rec.origin
        self._validate(category, new_status, data, new_doc, new_loc, new_origin)
        await self._check_document(project_id, source_document_id)
        rec.status = new_status
        if summary is not None:
            rec.summary = summary
        if data is not None:
            rec.data = data
        rec.source_document_id, rec.locator, rec.origin = new_doc, new_loc, new_origin
        await self.session.flush()
        await self._audit(rec, "intake.category_revised", actor)
        return rec

    async def get_category(self, project_id: uuid.UUID, category: str) -> IntakeCategory | None:
        return await self._get(project_id, category)

    async def list_categories(self, project_id: uuid.UUID) -> Sequence[IntakeCategory]:
        stmt = select(IntakeCategory).where(
            IntakeCategory.tenant_id == self.context.tenant_id,
            IntakeCategory.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalars().all()

    # --- internals ------------------------------------------------------------

    def _validate(self, category, status, data, source_document_id, locator, origin) -> None:
        validate_declarable_category(category)
        if status not in _VALID_STATUS:
            raise ValueError(f"invalid status {status!r}")
        validate_category_data(category, data)
        validate_source(source_document_id=source_document_id, locator=locator, origin=origin)

    async def _check_document(self, project_id, source_document_id) -> None:
        if source_document_id is None:
            return
        doc = await DocumentRepository(self.session, self.context).get(source_document_id)
        if doc is None or doc.project_id != project_id:
            raise ValueError(f"unknown document {source_document_id} for this project/tenant")
        if doc.status != "accepted":
            raise ValueError(f"document {source_document_id} is not accepted")

    async def _get(self, project_id, category) -> IntakeCategory | None:
        stmt = select(IntakeCategory).where(
            IntakeCategory.tenant_id == self.context.tenant_id,
            IntakeCategory.project_id == project_id,
            IntakeCategory.category == category,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _audit(self, rec: IntakeCategory, action: str, actor: str) -> None:
        # Safe metadata only — NEVER summary / data / locator / secret refs / document body.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"intake_category:{rec.id}",
            payload={
                "intake_category_id": str(rec.id),
                "project_id": str(rec.project_id),
                "category": rec.category,
                "status": rec.status,
                # Presence-only source metadata — never the concrete document UUID/locator.
                "has_source_document": rec.source_document_id is not None,
                "has_origin": rec.origin is not None,
            },
        )
