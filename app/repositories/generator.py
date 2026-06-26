"""Tenant-scoped canonical-artifact-generator repository (Slice 36).

``generate`` orchestrates the safe LLM pipeline (mirroring Slice 35 ``classify``): validate the
**requested** artifact_type up front (B3 — unsupported ⇒ ValueError, no model work) → resolve an
accepted same-project source document → injection hard-refuse → projected-cost budget preflight →
provider call (fake in tests) → on a valid-token response record the cost keyed by the run **before**
parse (incurred-cost; a parse failure still records cost) → strict-JSON ``{title, body}`` parse →
persist one inert ``system_authored_unapproved`` draft → audit safe metadata only (never title/body).

``review_artifact`` applies the §7.3 independence rules (``validate_independence``) and the one-way
authorship transition; ``request_artifact_approval`` opens a subject-scoped approval; ``authorship_marking``
recovers the §7.4 marking. **Store/infra-only:** no spine write, no promotion (deferred). Run inside
``tenant_scope``. Actor/lineage labels are caller-supplied-UNVERIFIED.
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
    actual_cost,
    build_user_block,
    estimate_input_tokens,
    project_cost,
)
from app.intake.generator import (
    GENERATE_SYSTEM_PROMPT,
    GENERATED_INSERT_STATUS,
    PROMPT_VERSION,
    GeneratorParseError,
    parse_generated_artifact,
    validate_authorship_transition,
    validate_independence,
    validate_requested_artifact_type,
)
from app.intake.sandbox import scan
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, get_price
from app.models.approval import Approval
from app.models.generated_artifact import GeneratedArtifact
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.documents import DocumentRepository
from app.tenancy import TenantContext, TenantScopedRepository

_APPROVE_ACTION = "intake.approve_generated_artifact"


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _subject_ref(generated_artifact_id: uuid.UUID) -> str:
    return f"generated_artifact:{generated_artifact_id}"


class GeneratedArtifactRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, GeneratedArtifact)

    async def generate(
        self,
        *,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        artifact_type: str,
        model: str,
        llm_client: LLMClient,
        generated_by: str,
        generator_prompt_family: str,
        generator_model_route: str | None = None,
        price_card: dict[str, ModelPrice] | None = None,
        max_output_tokens: int = 2048,
    ) -> GeneratedArtifact:
        # B3 — the requested target is validated BEFORE any document / model / cost work.
        validate_requested_artifact_type(artifact_type)
        if not model:
            raise ValueError("llm_generation_model is not configured (fail closed)")
        price = get_price(model, price_card)
        to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
        to_decimal(price.output_usd_per_1k, "output_usd_per_1k")

        doc = await DocumentRepository(self.session, self.context).get(document_id)
        # Pin to the same project before any model work (Slice-35 wrong-project baseline).
        if doc is None or doc.project_id != project_id:
            raise ValueError(f"unknown document {document_id} for this project/tenant")
        if doc.status != "accepted":
            raise ValueError(f"document {document_id} is not accepted")

        gid = uuid.uuid4()  # app-minted id; also keys the cost event

        async def record(
            outcome: str,
            *,
            provider: str,
            input_tokens: int | None = None,
            output_tokens: int | None = None,
            cost_external_ref: str | None = None,
            title: str | None = None,
            body: str | None = None,
        ) -> GeneratedArtifact:
            return await self._record(
                row_id=gid,
                project_id=project_id,
                document_id=document_id,
                artifact_type=artifact_type,
                model=model,
                generated_by=generated_by,
                generator_prompt_family=generator_prompt_family,
                generator_model_route=generator_model_route,
                outcome=outcome,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_external_ref=cost_external_ref,
                title=title,
                body=body,
            )

        # Injection hard-refuse — no model call, no cost (§16.3).
        if scan(doc.content).suspicious:
            return await record("refused_injection", provider="none")

        # Projected-cost budget preflight (deny-by-default).
        projected = project_cost(
            price,
            est_input_tokens=estimate_input_tokens(doc.content),
            max_output_tokens=max_output_tokens,
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await record("blocked_by_budget", provider="none")

        try:
            resp = await llm_client.complete(
                system=GENERATE_SYSTEM_PROMPT,
                user=build_user_block(doc.content),
                model=model,
                max_output_tokens=max_output_tokens,
                temperature=0.0,
            )
        except Exception:
            return await record("failed", provider="unknown")

        if not _positive_int(resp.input_tokens) or not _positive_int(resp.output_tokens):
            return await record("failed", provider=resp.provider)

        # Incurred-cost (B2): meter a valid-token response BEFORE parse.
        ext_ref = f"generated_artifact:{gid}:provider_request"
        await CostEventRepository(self.session, self.context).record(
            project_id=project_id,
            component="model_inference",
            amount_usd=actual_cost(
                price, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens
            ),
            quantity=resp.input_tokens + resp.output_tokens,
            source_system="llm",
            external_ref=ext_ref,
            actor=generated_by,
        )

        try:
            draft = parse_generated_artifact(resp.text)
        except GeneratorParseError:
            return await record(
                "failed",
                provider=resp.provider,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_external_ref=ext_ref,
            )

        return await record(
            "succeeded",
            provider=resp.provider,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_external_ref=ext_ref,
            title=draft.title,
            body=draft.body,
        )

    async def request_artifact_approval(
        self, *, generated_artifact_id: uuid.UUID, requested_by: str
    ) -> Approval:
        row = await self._get(generated_artifact_id)
        return await ApprovalRepository(self.session, self.context).request(
            project_id=row.project_id,
            action=_APPROVE_ACTION,
            risk_tier="high",
            requested_by=requested_by,
            requires_explicit_approval=True,
            subject_ref=_subject_ref(generated_artifact_id),
            payload={
                "generated_artifact_id": str(generated_artifact_id),
                "project_id": str(row.project_id),
                "artifact_type": row.artifact_type,
            },
        )

    async def review_artifact(
        self,
        *,
        generated_artifact_id: uuid.UUID,
        decision: str,
        approved_by: str,
        approval_basis: str | None = None,
        reviewer_role: str | None = None,
        reviewer_prompt_family: str | None = None,
        reviewer_authority: str | None = None,
        reviewer_model_route: str | None = None,
    ) -> GeneratedArtifact:
        row = await self._get(generated_artifact_id)
        if row.outcome != "succeeded":
            raise ValueError("only a succeeded generated artifact can be reviewed")
        if row.authorship_status != GENERATED_INSERT_STATUS:
            raise ValueError("generated artifact is not pending review")
        target = validate_independence(
            decision=decision,
            approval_basis=approval_basis,
            generated_by=row.generated_by,
            approved_by=approved_by,
            generator_prompt_family=row.generator_prompt_family,
            reviewer_prompt_family=reviewer_prompt_family,
            reviewer_role=reviewer_role,
            reviewer_authority=reviewer_authority,
        )
        validate_authorship_transition(row.authorship_status, target)
        row.authorship_status = target
        if target == "disputed":
            # disputed is status-only — NO approval/reviewer evidence on the row (PLAN §3.3);
            # the disputing actor is recorded in the audit event only.
            row.approved_by = None
            row.approved_at = None
            row.approval_basis = None
            row.reviewer_role = None
            row.reviewer_prompt_family = None
            row.reviewer_authority = None
            row.reviewer_model_route = None
        else:
            row.approved_by = approved_by
            row.approved_at = datetime.now(timezone.utc)
            row.approval_basis = approval_basis
            row.reviewer_role = reviewer_role
            row.reviewer_prompt_family = reviewer_prompt_family
            row.reviewer_authority = reviewer_authority
            row.reviewer_model_route = reviewer_model_route
        await self.session.flush()
        await audit_record(
            self.session,
            action="generated_artifact.reviewed",
            actor=approved_by,
            target=f"generated_artifact:{generated_artifact_id}",
            payload={
                "generated_artifact_id": str(generated_artifact_id),
                "project_id": str(row.project_id),
                "artifact_type": row.artifact_type,
                "authorship_status": target,
                "approval_basis": row.approval_basis,
            },
        )
        return row

    async def authorship_marking(self, generated_artifact_id: uuid.UUID) -> dict:
        """§7.4 marking — recoverable authorship provenance for a generated artifact."""
        row = await self._get(generated_artifact_id)
        return {
            "authorship_status": row.authorship_status,
            "generated_by": row.generated_by,
            "generator_prompt_family": row.generator_prompt_family,
            "approval_basis": row.approval_basis,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at,
            "reviewer_prompt_family": row.reviewer_prompt_family,
            "reviewer_authority": row.reviewer_authority,
        }

    async def latest_for(
        self, project_id: uuid.UUID, document_id: uuid.UUID, artifact_type: str
    ) -> GeneratedArtifact | None:
        stmt = (
            select(GeneratedArtifact)
            .where(
                GeneratedArtifact.tenant_id == self.context.tenant_id,
                GeneratedArtifact.project_id == project_id,
                GeneratedArtifact.source_document_id == document_id,
                GeneratedArtifact.artifact_type == artifact_type,
            )
            .order_by(GeneratedArtifact.created_at.desc(), GeneratedArtifact.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_project(self, project_id: uuid.UUID) -> Sequence[GeneratedArtifact]:
        stmt = (
            select(GeneratedArtifact)
            .where(
                GeneratedArtifact.tenant_id == self.context.tenant_id,
                GeneratedArtifact.project_id == project_id,
            )
            .order_by(GeneratedArtifact.created_at.desc(), GeneratedArtifact.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    # --- internals ------------------------------------------------------------

    async def _get(self, generated_artifact_id: uuid.UUID) -> GeneratedArtifact:
        row = await self.session.get(GeneratedArtifact, generated_artifact_id)
        if row is None or row.tenant_id != self.context.tenant_id:
            raise ValueError(f"generated artifact {generated_artifact_id} not found")
        return row

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
        *,
        row_id: uuid.UUID,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        artifact_type: str,
        model: str,
        outcome: str,
        provider: str,
        generated_by: str,
        generator_prompt_family: str,
        generator_model_route: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_external_ref: str | None = None,
        title: str | None = None,
        body: str | None = None,
    ) -> GeneratedArtifact:
        row = GeneratedArtifact(
            id=row_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            source_document_id=document_id,
            artifact_type=artifact_type,
            model=model,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            outcome=outcome,
            cost_external_ref=cost_external_ref,
            title=title,
            body=body,
            authorship_status=GENERATED_INSERT_STATUS,
            generated_by=generated_by,
            generator_prompt_family=generator_prompt_family,
            generator_model_route=generator_model_route,
        )
        self.session.add(row)
        await self.session.flush()
        # Audit safe metadata only — never title/body (source-derived content, B5).
        await audit_record(
            self.session,
            action="generated_artifact.recorded",
            actor=generated_by,
            target=f"generated_artifact:{row_id}",
            payload={
                "generated_artifact_id": str(row_id),
                "project_id": str(project_id),
                "document_id": str(document_id),
                "artifact_type": artifact_type,
                "model": model,
                "provider": provider,
                "outcome": outcome,
                "authorship_status": GENERATED_INSERT_STATUS,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        return row
