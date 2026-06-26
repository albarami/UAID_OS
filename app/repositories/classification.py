"""Tenant-scoped document-classification repository (Slice 35).

``classify`` orchestrates the safe LLM pipeline (mirroring Slice 14a ``extract``): resolve an
accepted source document → fail-closed config checks (model + price) → injection hard-refuse
→ projected-cost budget preflight (no provider call if it could exceed budget) → provider call
(fake in tests) → on a response with valid positive tokens, record the cost keyed by the run
**before** parse/evidence (incurred-cost semantics: a later parse/evidence failure still keeps
the cost) → strict-JSON parse → verbatim-evidence verification → persist one inert ``pending``
classification → audit safe metadata only (never the evidence quote / document body).
``review_classification`` enforces the one-way lifecycle + the distinct-reviewer (§2.2)
invariant. Run inside ``tenant_scope``.

No tool broker and no external I/O beyond the LLM call. A classification is inert and proposed
— never authoritative, never auto-promoted.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import to_decimal
from app.intake.classifier import (
    CLASSIFY_SYSTEM_PROMPT,
    PROMPT_VERSION,
    ClassificationParseError,
    parse_classification,
    validate_review_transition,
)
from app.intake.extraction import (
    actual_cost,
    build_user_block,
    estimate_input_tokens,
    project_cost,
    verify_evidence,
)
from app.intake.sandbox import scan
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, get_price
from app.models.document_classification import DocumentClassification
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.documents import DocumentRepository
from app.tenancy import TenantContext, TenantScopedRepository


def _positive_int(value) -> bool:
    """True iff ``value`` is a positive integer (rejects bool, None, zero, non-int)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ClassificationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, DocumentClassification)

    async def classify(
        self,
        *,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        model: str,
        llm_client: LLMClient,
        classified_by: str,
        price_card: dict[str, ModelPrice] | None = None,
        max_output_tokens: int = 2048,
    ) -> DocumentClassification:
        if not model:
            raise ValueError("llm_classification_model is not configured (fail closed)")
        price = get_price(model, price_card)
        # Validate the price values up front (fail closed) so a bad price cannot surface
        # only at cost-recording time, after the model was already called.
        to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
        to_decimal(price.output_usd_per_1k, "output_usd_per_1k")

        doc = await DocumentRepository(self.session, self.context).get(document_id)
        if doc is None or doc.status != "accepted":
            raise ValueError(f"document {document_id} is not accepted")

        cid = uuid.uuid4()  # app-minted id; also keys the cost event

        # Injection hard-refuse — no model call, no cost (§16.3).
        if scan(doc.content).suspicious:
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "refused_injection",
                provider="none",
                classified_by=classified_by,
            )

        # Projected-cost budget preflight (deny-by-default) — no call if it could exceed.
        projected = project_cost(
            price,
            est_input_tokens=estimate_input_tokens(doc.content),
            max_output_tokens=max_output_tokens,
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "blocked_by_budget",
                provider="none",
                classified_by=classified_by,
            )

        try:
            resp = await llm_client.complete(
                system=CLASSIFY_SYSTEM_PROMPT,
                user=build_user_block(doc.content),
                model=model,
                max_output_tokens=max_output_tokens,
                temperature=0.0,
            )
        except Exception:
            # Provider error — no cost event.
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "failed",
                provider="unknown",
                classified_by=classified_by,
            )

        # Fail closed on invalid token accounting — not valid usage, no cost event.
        if not _positive_int(resp.input_tokens) or not _positive_int(resp.output_tokens):
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "failed",
                provider=resp.provider,
                classified_by=classified_by,
            )

        # Incurred-cost (B2): a valid-token response is metered BEFORE parse/evidence, so a
        # later parse failure / non-verbatim evidence still records the cost it incurred.
        ext_ref = f"document_classification:{cid}:provider_request"
        await CostEventRepository(self.session, self.context).record(
            project_id=project_id,
            component="model_inference",
            amount_usd=actual_cost(
                price, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens
            ),
            quantity=resp.input_tokens + resp.output_tokens,
            source_system="llm",
            external_ref=ext_ref,
            actor=classified_by,
        )

        try:
            draft = parse_classification(resp.text)
        except ClassificationParseError:
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "failed",
                provider=resp.provider,
                classified_by=classified_by,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_external_ref=ext_ref,
            )

        if not verify_evidence(doc.content, draft.evidence_quote):
            return await self._record(
                cid,
                project_id,
                document_id,
                model,
                "failed",
                provider=resp.provider,
                classified_by=classified_by,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_external_ref=ext_ref,
            )

        return await self._record(
            cid,
            project_id,
            document_id,
            model,
            "succeeded",
            provider=resp.provider,
            classified_by=classified_by,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_external_ref=ext_ref,
            proposed_document_type=draft.document_type,
            proposed_authority_tier=draft.authority_tier,
            evidence_quote=draft.evidence_quote,
        )

    async def review_classification(
        self, *, classification_id: uuid.UUID, decision: str, reviewed_by: str
    ) -> DocumentClassification:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        if not reviewed_by:
            raise ValueError("reviewed_by is required")
        row = await self.session.get(DocumentClassification, classification_id)
        if row is None or row.tenant_id != self.context.tenant_id:
            raise ValueError(f"classification {classification_id} not found")
        if row.outcome != "succeeded":
            raise ValueError("only a succeeded classification can be reviewed")
        if row.review_status != "pending":
            raise ValueError("classification is not pending review")
        if reviewed_by == row.classified_by:
            raise ValueError("reviewer must differ from the classifying actor (§2.2)")
        validate_review_transition(row.review_status, decision)
        row.review_status = decision
        row.reviewed_by = reviewed_by
        row.reviewed_at = datetime.now(timezone.utc)
        await self.session.flush()
        await audit_record(
            self.session,
            action="classification.reviewed",
            actor=reviewed_by,
            target=f"document_classification:{classification_id}",
            payload={
                "document_classification_id": str(classification_id),
                "project_id": str(row.project_id),
                "outcome": row.outcome,
                "review_status": decision,
            },
        )
        return row

    async def latest_for_document(
        self, project_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentClassification | None:
        stmt = (
            select(DocumentClassification)
            .where(
                DocumentClassification.tenant_id == self.context.tenant_id,
                DocumentClassification.project_id == project_id,
                DocumentClassification.document_id == document_id,
            )
            .order_by(DocumentClassification.created_at.desc(), DocumentClassification.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_project(self, project_id: uuid.UUID) -> Sequence[DocumentClassification]:
        stmt = (
            select(DocumentClassification)
            .where(
                DocumentClassification.tenant_id == self.context.tenant_id,
                DocumentClassification.project_id == project_id,
            )
            .order_by(DocumentClassification.created_at.desc(), DocumentClassification.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    # --- internals ------------------------------------------------------------

    async def _projected_exceeds_budget(self, project_id: uuid.UUID, projected: Decimal) -> bool:
        budget = await BudgetRepository(self.session, self.context).get(project_id)
        if budget is None:
            return True  # deny-by-default: no budget ⇒ no LLM spend
        events = CostEventRepository(self.session, self.context)
        total = await events.total_spent(project_id)
        if total + projected >= budget.max_total_cost_usd:
            return True
        if budget.max_daily_cost_usd is not None:
            today = datetime.now(timezone.utc).date()
            daily = await events.daily_spent(project_id, today)
            if daily + projected >= budget.max_daily_cost_usd:
                return True
        return False

    async def _record(
        self,
        row_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        model: str,
        outcome: str,
        *,
        provider: str,
        classified_by: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_external_ref: str | None = None,
        proposed_document_type: str | None = None,
        proposed_authority_tier: str | None = None,
        evidence_quote: str | None = None,
    ) -> DocumentClassification:
        review_status = "pending" if outcome == "succeeded" else "not_applicable"
        row = DocumentClassification(
            id=row_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            document_id=document_id,
            model=model,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            outcome=outcome,
            cost_external_ref=cost_external_ref,
            proposed_document_type=proposed_document_type,
            proposed_authority_tier=proposed_authority_tier,
            evidence_quote=evidence_quote,
            review_status=review_status,
            classified_by=classified_by,
        )
        self.session.add(row)
        await self.session.flush()
        # Audit safe metadata only — never the document body / evidence quote (B5).
        await audit_record(
            self.session,
            action="classification.recorded",
            actor=classified_by,
            target=f"document_classification:{row_id}",
            payload={
                "document_classification_id": str(row_id),
                "project_id": str(project_id),
                "document_id": str(document_id),
                "model": model,
                "provider": provider,
                "outcome": outcome,
                "proposed_document_type": proposed_document_type,
                "proposed_authority_tier": proposed_authority_tier,
                "review_status": review_status,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        return row
