"""Tenant-scoped LLM extraction repository (Slice 14a).

``extract`` orchestrates the safe pipeline: resolve an accepted source document →
fail-closed config checks (model + price) → injection hard-refuse → projected-cost
budget preflight (no provider call if it could exceed budget) → provider call (fake in
tests) → record cost keyed by the run → strict-JSON parse → verbatim-evidence
verification (hallucinations dropped) → persist an immutable run + inert pending
proposals → audit safe metadata only. ``review_proposal`` enforces the one-way
lifecycle and the distinct-reviewer (§2.2) invariant. Run inside ``tenant_scope``.

Nothing here promotes proposals into the canonical spine — that is Slice 14b.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import to_decimal
from app.intake.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    ExtractionParseError,
    actual_cost,
    build_user_block,
    estimate_input_tokens,
    parse_proposals,
    project_cost,
    verify_evidence,
)
from app.intake.sandbox import scan
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, get_price
from app.models.extraction_proposal import ExtractionProposal
from app.models.extraction_run import ExtractionRun
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.documents import DocumentRepository
from app.tenancy import TenantContext, TenantScopedRepository


def _positive_int(value) -> bool:
    """True iff ``value`` is a positive integer (rejects bool, None, zero, non-int)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ExtractionRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ExtractionRun)

    async def extract(
        self,
        *,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        model: str,
        llm_client: LLMClient,
        extracted_by: str,
        price_card: dict[str, ModelPrice] | None = None,
        max_output_tokens: int = 2048,
    ) -> tuple[ExtractionRun, list[ExtractionProposal]]:
        if not model:
            raise ValueError("llm_extraction_model is not configured (fail closed)")
        # Fail closed if the model is unpriced (cannot budget-gate ⇒ cannot call).
        price = get_price(model, price_card)
        # Validate price-card values with the ledger money guards BEFORE any provider
        # call (rejects float/bool/negative/non-finite/over-scale). An invalid price could
        # otherwise produce a bogus projection and only fail when recording the cost — too
        # late, after the model was already called.
        to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
        to_decimal(price.output_usd_per_1k, "output_usd_per_1k")

        doc = await DocumentRepository(self.session, self.context).get(document_id)
        if doc is None or doc.project_id != project_id:
            raise ValueError(f"unknown document {document_id} for this project/tenant")
        if doc.status != "accepted":
            raise ValueError(f"document {document_id} is not accepted")

        run_id = uuid.uuid4()

        # Injection hard-refuse: suspicious content never reaches the model.
        if scan(doc.content).suspicious:
            return (
                await self._record_run(
                    run_id, project_id, document_id, model, "refused_injection",
                    provider="none", actor=extracted_by,
                ),
                [],
            )

        # Projected-cost budget preflight (deny-by-default; no call if it could exceed).
        projected = project_cost(
            price,
            est_input_tokens=estimate_input_tokens(doc.content),
            max_output_tokens=max_output_tokens,
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return (
                await self._record_run(
                    run_id, project_id, document_id, model, "blocked_by_budget",
                    provider="none", actor=extracted_by,
                ),
                [],
            )

        # Provider call (fake in tests). On failure: a failed run, NO cost event.
        try:
            resp = await llm_client.complete(
                system=EXTRACTION_SYSTEM_PROMPT,
                user=build_user_block(doc.content),
                model=model,
                max_output_tokens=max_output_tokens,
                temperature=0.0,
            )
        except Exception:
            return (
                await self._record_run(
                    run_id, project_id, document_id, model, "failed",
                    provider="none", actor=extracted_by,
                ),
                [],
            )

        # Fail closed on invalid token accounting: a "successful" response without valid
        # positive token counts is not valid usage — record a failed run, NO cost event.
        if not _positive_int(resp.input_tokens) or not _positive_int(resp.output_tokens):
            return (
                await self._record_run(
                    run_id, project_id, document_id, model, "failed",
                    provider=resp.provider, actor=extracted_by,
                ),
                [],
            )

        # Cost recorded only on a successful response with token usage, keyed by the run.
        ext_ref = f"extraction_run:{run_id}:provider_request"
        await CostEventRepository(self.session, self.context).record(
            project_id=project_id,
            component="model_inference",
            amount_usd=actual_cost(
                price, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens
            ),
            quantity=resp.input_tokens + resp.output_tokens,
            source_system="llm",
            external_ref=ext_ref,
            actor=extracted_by,
        )

        try:
            _classification, drafts = parse_proposals(resp.text)
        except ExtractionParseError:
            return (
                await self._record_run(
                    run_id, project_id, document_id, model, "failed",
                    provider=resp.provider, actor=extracted_by,
                    input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                    cost_external_ref=ext_ref,
                ),
                [],
            )

        # Anti-hallucination: keep only drafts whose evidence quote is verbatim in source.
        verified = [d for d in drafts if verify_evidence(doc.content, d.evidence_quote)]

        run = await self._record_run(
            run_id, project_id, document_id, model, "succeeded",
            provider=resp.provider, actor=extracted_by,
            input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            cost_external_ref=ext_ref,
            proposal_count=len(verified), rejected_count=len(drafts) - len(verified),
        )
        proposals: list[ExtractionProposal] = []
        for d in verified:
            prop = ExtractionProposal(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                extraction_run_id=run_id,
                proposed_kind=d.kind,
                proposed_text=d.text,
                proposed_classification=d.classification,
                source_document_id=document_id,
                evidence_quote=d.evidence_quote,
                status="pending",
                extracted_by=extracted_by,
            )
            self.session.add(prop)
            proposals.append(prop)
        await self.session.flush()
        return run, proposals

    async def review_proposal(
        self, *, proposal_id: uuid.UUID, decision: str, reviewed_by: str
    ) -> ExtractionProposal:
        if decision not in ("approved", "rejected"):
            raise ValueError(f"invalid decision {decision!r}")
        if not reviewed_by:
            raise ValueError("reviewed_by is required")
        prop = await self._get_proposal(proposal_id)
        if prop is None:
            raise LookupError(str(proposal_id))
        if prop.status != "pending":
            raise ValueError(f"proposal {proposal_id} is not pending")
        if reviewed_by == prop.extracted_by:
            raise ValueError("reviewer must differ from the extracting actor (§2.2)")
        prop.status = decision
        prop.reviewed_by = reviewed_by
        prop.reviewed_at = datetime.now(timezone.utc)
        await self.session.flush()
        await audit_record(
            self.session,
            action="extraction.proposal_reviewed",
            actor=reviewed_by,
            target=f"extraction_proposal:{proposal_id}",
            payload={
                "extraction_proposal_id": str(proposal_id),
                "project_id": str(prop.project_id),
                "proposed_kind": prop.proposed_kind,
                "status": decision,
            },
        )
        return prop

    async def list_proposals(
        self, project_id: uuid.UUID, status: str | None = None
    ) -> Sequence[ExtractionProposal]:
        stmt = select(ExtractionProposal).where(
            ExtractionProposal.tenant_id == self.context.tenant_id,
            ExtractionProposal.project_id == project_id,
        )
        if status is not None:
            stmt = stmt.where(ExtractionProposal.status == status)
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

    async def _record_run(
        self,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        model: str,
        status: str,
        *,
        provider: str,
        actor: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_external_ref: str | None = None,
        proposal_count: int = 0,
        rejected_count: int = 0,
    ) -> ExtractionRun:
        run = ExtractionRun(
            id=run_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            document_id=document_id,
            model=model,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status=status,
            cost_external_ref=cost_external_ref,
        )
        self.session.add(run)
        await self.session.flush()
        # Audit safe metadata only — never document body / proposed text / evidence quote.
        await audit_record(
            self.session,
            action="extraction.run_recorded",
            actor=actor,
            target=f"extraction_run:{run_id}",
            payload={
                "extraction_run_id": str(run_id),
                "project_id": str(project_id),
                "document_id": str(document_id),
                "model": model,
                "provider": provider,
                "prompt_version": PROMPT_VERSION,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "status": status,
                "proposal_count": proposal_count,
                "rejected_count": rejected_count,
            },
        )
        return run

    async def _get_proposal(self, proposal_id: uuid.UUID) -> ExtractionProposal | None:
        stmt = select(ExtractionProposal).where(
            ExtractionProposal.id == proposal_id,
            ExtractionProposal.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
