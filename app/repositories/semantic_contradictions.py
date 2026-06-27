"""Tenant-scoped semantic-contradiction-detector repository (Slice 37).

``detect`` orchestrates the safe LLM pipeline (mirroring Slice 35/36): app-mint the report id up front
(T1, keys the cost event) → read the project's spine ``requirement``+``acceptance_criterion`` artifacts,
sort ``(kind, ref, id)`` and cap ``MAX_ANALYZED_ARTIFACTS`` (T2) → ``<2`` ⇒ ``skipped_insufficient_input``
(no call/no cost, B1) → assign opaque per-prompt item keys (B8) → injection hard-refuse → projected-cost
budget preflight → provider call (fake in tests) → on a valid-token response record the cost keyed by the
report **before** parse (incurred-cost, B2) → strict-JSON parse → ``keep_valid`` (resolve item keys →
FK-backed artifacts, drop OOV/unknown/ambiguous, B3/B4/B8) → persist one report + one
``semantic_contradictions`` row per kept pair in one txn (the deferred count triggers validate
report.count == child rows at commit, B6/B9) → audit safe metadata only (counts/per-conflict_type counts —
never description/artifact content). DESCRIPTIVE-ONLY: no resolution is ever chosen (§6.4). Run inside
``tenant_scope``. ``detected_by`` is a caller-supplied UNVERIFIED label.
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
from app.intake.sandbox import scan
from app.intake.semantic_contradictions import (
    DETECT_SYSTEM_PROMPT,
    MAX_ANALYZED_ARTIFACTS,
    MAX_ARTIFACT_BODY_CHARS_IN_PROMPT,
    PROMPT_VERSION,
    RULESET_VERSION,
    KeptContradiction,
    SemanticContradictionParseError,
    format_artifacts,
    keep_valid,
    parse_contradictions,
)
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, get_price
from app.models.semantic_contradiction import SemanticContradiction
from app.models.semantic_contradiction_report import SemanticContradictionReport
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, TenantScopedRepository


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class SemanticContradictionRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, SemanticContradictionReport)

    async def detect(
        self,
        *,
        project_id: uuid.UUID,
        model: str,
        llm_client: LLMClient,
        detected_by: str,
        price_card: dict[str, ModelPrice] | None = None,
        max_output_tokens: int = 2048,
    ) -> SemanticContradictionReport:
        if not model:
            raise ValueError("llm model is not configured (fail closed)")
        price = get_price(model, price_card)
        to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
        to_decimal(price.output_usd_per_1k, "output_usd_per_1k")

        rid = uuid.uuid4()  # T1: app-minted; also keys the cost event

        intake = IntakeRepository(self.session, self.context)
        artifacts = list(await intake.list_artifacts(project_id, kind="requirement"))
        artifacts += list(await intake.list_artifacts(project_id, kind="acceptance_criterion"))
        artifacts.sort(key=lambda a: (a.kind, a.ref, str(a.id)))  # T2: deterministic order
        over_cap = len(artifacts) > MAX_ANALYZED_ARTIFACTS
        artifacts = artifacts[:MAX_ANALYZED_ARTIFACTS]
        analyzed = len(artifacts)
        input_truncated = over_cap or any(
            len(a.body or "") > MAX_ARTIFACT_BODY_CHARS_IN_PROMPT for a in artifacts
        )

        async def record(
            outcome: str,
            *,
            provider: str,
            input_tokens: int | None = None,
            output_tokens: int | None = None,
            cost_external_ref: str | None = None,
            kept: Sequence[KeptContradiction] = (),
        ) -> SemanticContradictionReport:
            return await self._record(
                row_id=rid,
                project_id=project_id,
                model=model,
                provider=provider,
                detected_by=detected_by,
                outcome=outcome,
                analyzed_artifact_count=analyzed,
                input_truncated=input_truncated,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_external_ref=cost_external_ref,
                kept=kept,
            )

        # B1 — fewer than two analyzable artifacts ⇒ no provider call, no cost.
        if analyzed < 2:
            return await record("skipped_insufficient_input", provider="none")

        block, key_to_artifact = format_artifacts(artifacts)

        # Injection hard-refuse — no model call, no cost (§16.3).
        if scan(block).suspicious:
            return await record("refused_injection", provider="none")

        # Projected-cost budget preflight (deny-by-default).
        projected = project_cost(
            price,
            est_input_tokens=estimate_input_tokens(block),
            max_output_tokens=max_output_tokens,
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await record("blocked_by_budget", provider="none")

        try:
            resp = await llm_client.complete(
                system=DETECT_SYSTEM_PROMPT,
                user=build_user_block(block),
                model=model,
                max_output_tokens=max_output_tokens,
                temperature=0.0,
            )
        except Exception:
            return await record("failed", provider="unknown")

        if not _positive_int(resp.input_tokens) or not _positive_int(resp.output_tokens):
            return await record("failed", provider=resp.provider)

        # Incurred-cost (B2): meter a valid-token response BEFORE parse.
        ext_ref = f"semantic_contradiction_report:{rid}:provider_request"
        await CostEventRepository(self.session, self.context).record(
            project_id=project_id,
            component="model_inference",
            amount_usd=actual_cost(
                price, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens
            ),
            quantity=resp.input_tokens + resp.output_tokens,
            source_system="llm",
            external_ref=ext_ref,
            actor=detected_by,
        )

        try:
            drafts = parse_contradictions(resp.text)
        except SemanticContradictionParseError:
            return await record(
                "failed",
                provider=resp.provider,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_external_ref=ext_ref,
            )

        kept = keep_valid(drafts, key_to_artifact)
        return await record(
            "succeeded",
            provider=resp.provider,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_external_ref=ext_ref,
            kept=kept,
        )

    async def latest(self, project_id: uuid.UUID) -> SemanticContradictionReport | None:
        stmt = (
            select(SemanticContradictionReport)
            .where(
                SemanticContradictionReport.tenant_id == self.context.tenant_id,
                SemanticContradictionReport.project_id == project_id,
            )
            .order_by(
                SemanticContradictionReport.created_at.desc(),
                SemanticContradictionReport.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def history(self, project_id: uuid.UUID) -> Sequence[SemanticContradictionReport]:
        stmt = (
            select(SemanticContradictionReport)
            .where(
                SemanticContradictionReport.tenant_id == self.context.tenant_id,
                SemanticContradictionReport.project_id == project_id,
            )
            .order_by(
                SemanticContradictionReport.created_at.desc(),
                SemanticContradictionReport.id.desc(),
            )
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def contradictions_for(self, report_id: uuid.UUID) -> Sequence[SemanticContradiction]:
        stmt = (
            select(SemanticContradiction)
            .where(
                SemanticContradiction.tenant_id == self.context.tenant_id,
                SemanticContradiction.report_id == report_id,
            )
            .order_by(SemanticContradiction.created_at, SemanticContradiction.id)
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
        *,
        row_id: uuid.UUID,
        project_id: uuid.UUID,
        model: str,
        provider: str,
        detected_by: str,
        outcome: str,
        analyzed_artifact_count: int,
        input_truncated: bool,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_external_ref: str | None,
        kept: Sequence[KeptContradiction],
    ) -> SemanticContradictionReport:
        report = SemanticContradictionReport(
            id=row_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            model=model,
            provider=provider,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            outcome=outcome,
            cost_external_ref=cost_external_ref,
            contradiction_count=len(kept),
            analyzed_artifact_count=analyzed_artifact_count,
            input_truncated=input_truncated,
            ruleset_version=RULESET_VERSION,
            detected_by=detected_by,
        )
        self.session.add(report)
        await self.session.flush()
        by_type: dict[str, int] = {}
        for k in kept:
            self.session.add(
                SemanticContradiction(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    report_id=row_id,
                    conflict_type=k.conflict_type,
                    description=k.description,
                    artifact_a_id=k.artifact_a.id,
                    artifact_b_id=k.artifact_b.id,
                )
            )
            by_type[k.conflict_type] = by_type.get(k.conflict_type, 0) + 1
        await self.session.flush()
        # Audit safe metadata only — counts + per-conflict_type counts; never description/refs (B5).
        await audit_record(
            self.session,
            action="semantic_contradiction.recorded",
            actor=detected_by,
            target=f"semantic_contradiction_report:{row_id}",
            payload={
                "report_id": str(row_id),
                "project_id": str(project_id),
                "model": model,
                "provider": provider,
                "outcome": outcome,
                "contradiction_count": len(kept),
                "analyzed_artifact_count": analyzed_artifact_count,
                "input_truncated": input_truncated,
                "conflict_type_counts": by_type,
            },
        )
        return report
