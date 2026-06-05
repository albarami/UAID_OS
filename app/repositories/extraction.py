"""Tenant-scoped LLM extraction repository (Slice 14a).

``extract`` orchestrates the safe pipeline: resolve an accepted source document →
fail-closed config checks (model + price) → injection hard-refuse → projected-cost
budget preflight (no provider call if it could exceed budget) → provider call (fake in
tests) → record cost keyed by the run → strict-JSON parse → verbatim-evidence
verification (hallucinations dropped) → persist an immutable run + inert pending
proposals → audit safe metadata only. ``review_proposal`` enforces the one-way
lifecycle and the distinct-reviewer (§2.2) invariant. Run inside ``tenant_scope``.

Slice 14b adds promotion of *approved* proposals into the canonical spine
(``promote_proposal`` via ``IntakeRepository.add_artifact``) with promotion-time evidence
re-verification, §16.5 assumption gating, and an idempotent append-only promotion link.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.states import Status
from app.audit import record as audit_record
from app.cost import to_decimal
from app.intake.compiler import SourceInput
from app.intake.extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMOTABLE_KINDS,
    PROMPT_VERSION,
    ExtractionParseError,
    actual_cost,
    build_user_block,
    estimate_input_tokens,
    parse_proposals,
    project_cost,
    promotion_ref,
    verify_evidence,
)
from app.intake.sandbox import scan
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, get_price
from app.models.extraction_promotion import ExtractionPromotion
from app.models.extraction_proposal import ExtractionProposal
from app.models.extraction_run import ExtractionRun
from app.models.intake_artifact import IntakeArtifact
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.documents import DocumentRepository
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, TenantScopedRepository

# Slice 14b — subject-scoped approval gate for promoting a needs_approval assumption.
_PROMOTE_ASSUMPTION_ACTION = "intake.promote_assumption"


def _positive_int(value) -> bool:
    """True iff ``value`` is a positive integer (rejects bool, None, zero, non-int)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _subject_ref(proposal_id: uuid.UUID) -> str:
    return f"extraction_proposal:{proposal_id}"


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

    # --- Slice 14b: promotion into the canonical spine ------------------------

    async def request_promotion_approval(self, *, proposal_id: uuid.UUID, requested_by: str):
        """Idempotently open the §16.5 promotion approval for a needs_approval assumption.

        Already-promoted ⇒ refuse. A pending/approved subject-scoped approval is returned
        as-is (no duplicate that could re-block after approval); a terminal-negative one
        allows a fresh request. Payload is safe metadata only (no proposed text/evidence).
        """
        prop = await self._get_proposal(proposal_id)
        if prop is None:
            raise LookupError(str(proposal_id))
        if prop.proposed_kind != "assumption" or prop.proposed_classification != "needs_approval":
            raise ValueError("promotion approval only applies to needs_approval assumptions")
        # Two-gate model: the 14a human review must come first.
        if prop.status != "approved":
            raise ValueError(f"proposal {proposal_id} is not approved (status={prop.status})")
        if await self.promotion_for(proposal_id) is not None:
            raise ValueError("proposal already promoted")
        approvals = ApprovalRepository(self.session, self.context)
        subject = _subject_ref(proposal_id)
        latest = await approvals.latest_for(
            prop.project_id, _PROMOTE_ASSUMPTION_ACTION, subject_ref=subject
        )
        if latest is not None and latest.status in (Status.PENDING.value, Status.APPROVED.value):
            return latest
        return await approvals.request(
            project_id=prop.project_id,
            action=_PROMOTE_ASSUMPTION_ACTION,
            risk_tier="high",
            requested_by=requested_by,
            requires_explicit_approval=True,
            subject_ref=subject,
            payload={
                "proposal_id": str(proposal_id),
                "project_id": str(prop.project_id),
                "kind": prop.proposed_kind,
                "classification": prop.proposed_classification,
                "subject_ref": subject,
            },
        )

    async def promote_proposal(
        self,
        *,
        proposal_id: uuid.UUID,
        actor: str,
        parent_id: uuid.UUID | None = None,
        ref: str | None = None,
    ) -> IntakeArtifact:
        """Promote an approved proposal into a spine artifact (deterministic, idempotent).

        Re-verifies evidence at promotion (the trust boundary), gates assumptions per
        §16.5, validates an optional acceptance-criterion parent, then delegates to
        ``IntakeRepository.add_artifact`` (which re-checks accepted/same-project sources).
        """
        prop = await self._get_proposal(proposal_id)
        if prop is None:
            raise LookupError(str(proposal_id))
        # Idempotent: already promoted ⇒ return the existing artifact, no duplicate.
        existing = await self.promotion_for(proposal_id)
        if existing is not None:
            return await IntakeRepository(self.session, self.context).get_artifact(
                existing.artifact_id
            )
        if prop.status != "approved":
            raise ValueError(f"proposal {proposal_id} is not approved (status={prop.status})")
        if prop.proposed_kind not in PROMOTABLE_KINDS:
            raise ValueError(f"proposed_kind {prop.proposed_kind!r} is not promotable in 14b")
        # parent_id only applies to acceptance_criterion promotions.
        if parent_id is not None and prop.proposed_kind != "acceptance_criterion":
            raise ValueError("parent_id is only valid for acceptance_criterion promotions")

        # Promotion-time re-verification (do NOT trust 14a alone): the document must still
        # be an accepted same-project doc AND the evidence quote must be verbatim present.
        doc = await DocumentRepository(self.session, self.context).get(prop.source_document_id)
        if doc is None or doc.project_id != prop.project_id:
            raise ValueError("source document not found for this project/tenant")
        if doc.status != "accepted":
            raise ValueError("source document is not accepted")
        if not verify_evidence(doc.content, prop.evidence_quote):
            raise ValueError("evidence quote is not a verbatim substring of the source document")

        # §16.5 assumption gating.
        if prop.proposed_kind == "assumption":
            cls = prop.proposed_classification
            if cls in ("unsafe_assumption_blocked", "unknown_cannot_proceed"):
                raise ValueError(f"assumption classification {cls!r} cannot be promoted")
            if cls == "needs_approval":
                blocked = await ApprovalRepository(self.session, self.context).is_blocked(
                    prop.project_id, _PROMOTE_ASSUMPTION_ACTION, subject_ref=_subject_ref(proposal_id)
                )
                if blocked:
                    raise ValueError(
                        "promotion requires an approved promotion approval for this assumption"
                    )

        # Optional acceptance-criterion parent must be a same-project requirement.
        intake = IntakeRepository(self.session, self.context)
        if parent_id is not None:
            parent = await intake.get_artifact(parent_id)
            if parent is None or parent.project_id != prop.project_id:
                raise ValueError("parent artifact not found for this project/tenant")
            if parent.kind != "requirement":
                raise ValueError("parent must be a requirement")

        artifact = await intake.add_artifact(
            project_id=prop.project_id,
            kind=prop.proposed_kind,
            ref=ref or promotion_ref(prop.proposed_kind, proposal_id),
            title=prop.proposed_text,
            body=None,
            data={"extraction_proposal_id": str(proposal_id)},
            classification=prop.proposed_classification,
            parent_id=parent_id,
            sources=[
                SourceInput(
                    origin=f"document:{prop.source_document_id}",
                    locator=prop.evidence_quote,
                    document_id=prop.source_document_id,
                )
            ],
            actor=actor,
        )
        link = ExtractionPromotion(
            tenant_id=self.context.tenant_id,
            project_id=prop.project_id,
            extraction_proposal_id=proposal_id,
            artifact_id=artifact.id,
            promoted_by=actor,
        )
        self.session.add(link)
        await self.session.flush()
        await audit_record(
            self.session,
            action="intake.proposal_promoted",
            actor=actor,
            target=_subject_ref(proposal_id),
            payload={
                "extraction_proposal_id": str(proposal_id),
                "project_id": str(prop.project_id),
                "artifact_id": str(artifact.id),
                "proposed_kind": prop.proposed_kind,
                "classification": prop.proposed_classification,
            },
        )
        return artifact

    async def promotion_for(self, proposal_id: uuid.UUID) -> ExtractionPromotion | None:
        stmt = select(ExtractionPromotion).where(
            ExtractionPromotion.tenant_id == self.context.tenant_id,
            ExtractionPromotion.extraction_proposal_id == proposal_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_promotions(self, project_id: uuid.UUID) -> Sequence[ExtractionPromotion]:
        stmt = select(ExtractionPromotion).where(
            ExtractionPromotion.tenant_id == self.context.tenant_id,
            ExtractionPromotion.project_id == project_id,
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
