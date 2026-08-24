"""Promotion mixin for Slice-14b extraction → spine artifacts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.states import Status
from app.audit import record as audit_record
from app.concurrency import ConcurrentWriteUnresolved, unique_violation_constraint
from app.intake.compiler import SourceInput
from app.intake.extraction import PROMOTABLE_KINDS, promotion_ref, verify_evidence
from app.models.extraction_proposal import ExtractionProposal
from app.models.extraction_promotion import ExtractionPromotion
from app.models.intake_artifact import IntakeArtifact
from app.repositories.approvals import ApprovalRepository
from app.repositories.documents import DocumentRepository
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext

# Slice 14b — subject-scoped approval gate for promoting a needs_approval assumption.
_PROMOTE_ASSUMPTION_ACTION = "intake.promote_assumption"
_PROMOTION_CONFLICT_CONSTRAINTS = frozenset(
    {"uq_intake_artifacts_ref", "uq_extraction_promotions_proposal"}
)


class PromotionRefConflict(ValueError):
    """The artifact ref already belongs to a different proposal's promotion."""


def _subject_ref(proposal_id: uuid.UUID) -> str:
    return f"extraction_proposal:{proposal_id}"


class _ExtractionPromotionMixin:
    session: AsyncSession
    context: TenantContext

    async def _get_proposal(self, proposal_id: uuid.UUID) -> ExtractionProposal | None:
        """Implemented by ``ExtractionRepository``."""
        raise NotImplementedError

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
            return await self._require_promoted_artifact(existing.artifact_id)
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
                    prop.project_id,
                    _PROMOTE_ASSUMPTION_ACTION,
                    subject_ref=_subject_ref(proposal_id),
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

        artifact: IntakeArtifact
        try:
            async with self.session.begin_nested():
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
        except IntegrityError as exc:
            constraint = unique_violation_constraint(exc)
            if constraint not in _PROMOTION_CONFLICT_CONSTRAINTS:
                raise
            recovered = await self.promotion_for(proposal_id)
            if constraint == "uq_extraction_promotions_proposal":
                if recovered is not None:
                    return await self._require_promoted_artifact(recovered.artifact_id)
                raise ConcurrentWriteUnresolved("uq_extraction_promotions_proposal") from exc
            if recovered is not None:
                return await self._require_promoted_artifact(recovered.artifact_id)
            raise PromotionRefConflict(
                "artifact ref already used by a different promotion"
            ) from exc
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

    async def _require_promoted_artifact(self, artifact_id: uuid.UUID) -> IntakeArtifact:
        found = await IntakeRepository(self.session, self.context).get_artifact(artifact_id)
        if found is None:
            raise ConcurrentWriteUnresolved("promoted artifact not visible after conflict")
        return found

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
