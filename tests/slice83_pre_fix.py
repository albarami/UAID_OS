"""Pre-fix writer bodies for Slice 83 P-MUT-1…6 (commit-3 behaviour)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import (
    ARCHETYPES,
    COMPONENT_HASH_FIELDS,
    InvalidArchetype,
    _require_sha256,
    compute_content_hash,
)
from app.audit import record as audit_record
from app.cost import to_decimal
from app.ecosystem.catalog import (
    ADOPTED_BY_MAX,
    audit_safe_adoption_payload,
    require_bounded_text,
)
from app.intake.compiler import SourceInput
from app.intake.extraction import PROMOTABLE_KINDS, promotion_ref, verify_evidence
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_version import AgentVersion
from app.models.budget import Budget
from app.models.cost_forecast import CostForecastPolicyVersion
from app.models.ecosystem_catalog import CatalogAsset, CatalogListing, TenantCatalogAdoption
from app.models.extraction_promotion import ExtractionPromotion
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost_forecast_types import _storage_hash, _money, _percent
from app.cost_forecast import (
    COST_POLICY_CONTRACT_HASH,
    COST_POLICY_CONTRACT_VERSION,
    POLICY_PROVENANCE,
    parse_structured_policy,
)
from app.repositories.documents import DocumentRepository
from app.repositories.extraction_promotion import _PROMOTE_ASSUMPTION_ACTION, _subject_ref
from app.repositories.intake import IntakeRepository


async def pre_fix_budget_upsert(
    self,
    *,
    project_id: uuid.UUID,
    max_total_cost_usd,
    max_daily_cost_usd=None,
    actor: str,
):
    total = to_decimal(max_total_cost_usd, "max_total_cost_usd")
    daily = (
        to_decimal(max_daily_cost_usd, "max_daily_cost_usd")
        if max_daily_cost_usd is not None
        else None
    )
    existing = await self.get(project_id)
    old_total = existing.max_total_cost_usd if existing else None
    old_daily = existing.max_daily_cost_usd if existing else None
    if existing is not None:
        existing.max_total_cost_usd = total
        existing.max_daily_cost_usd = daily
        budget = existing
    else:
        budget = Budget(project_id=project_id, max_total_cost_usd=total, max_daily_cost_usd=daily)
        await self.add(budget)
    await self.session.flush()
    from app.repositories.cost import _money_str

    await audit_record(
        self.session,
        action="budget.set",
        actor=actor,
        target=f"budget:project:{project_id}",
        payload={
            "project_id": str(project_id),
            "old_total": _money_str(old_total),
            "new_total": _money_str(total),
            "old_daily": _money_str(old_daily),
            "new_daily": _money_str(daily),
        },
    )
    return budget


async def pre_fix_register_blueprint(
    session: AsyncSession,
    *,
    key: str,
    role: str,
    mission: str,
    archetype: str,
    actor: str,
) -> AgentBlueprint:
    if archetype not in ARCHETYPES:
        raise InvalidArchetype(f"unknown archetype: {archetype!r}")
    existing = (
        await session.execute(select(AgentBlueprint).where(AgentBlueprint.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    blueprint = AgentBlueprint(key=key, role=role, mission=mission, archetype=archetype)
    session.add(blueprint)
    await session.flush()
    return blueprint


async def pre_fix_register_version(
    session: AsyncSession,
    *,
    blueprint_id: uuid.UUID,
    version_label: str,
    model_route: str,
    prompt_hash: str,
    tool_policy_hash: str,
    context_policy_hash: str,
    eval_suite_hash: str,
    critical_dependencies_hash: str,
    output_schema_hash: str,
    actor: str,
) -> AgentVersion:
    component_hashes = {
        "prompt_hash": prompt_hash,
        "tool_policy_hash": tool_policy_hash,
        "context_policy_hash": context_policy_hash,
        "eval_suite_hash": eval_suite_hash,
        "critical_dependencies_hash": critical_dependencies_hash,
        "output_schema_hash": output_schema_hash,
    }
    for field in COMPONENT_HASH_FIELDS:
        _require_sha256(field, component_hashes[field])
    content_hash = compute_content_hash(
        blueprint_id=blueprint_id,
        version_label=version_label,
        model_route=model_route,
        component_hashes=component_hashes,
    )
    existing = (
        await session.execute(select(AgentVersion).where(AgentVersion.content_hash == content_hash))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    version = AgentVersion(
        blueprint_id=blueprint_id,
        version_label=version_label,
        model_route=model_route,
        content_hash=content_hash,
        **component_hashes,
    )
    session.add(version)
    await session.flush()
    return version


async def pre_fix_adopt(self, project_id, listing_id, *, adopted_by):
    listing = await self.session.get(CatalogListing, listing_id)
    if listing is None:
        from app.repositories.catalog_adoptions import CatalogAdoptionError

        raise CatalogAdoptionError("unknown listing")
    existing = (
        await self.session.execute(
            select(TenantCatalogAdoption).where(
                TenantCatalogAdoption.tenant_id == self.context.tenant_id,
                TenantCatalogAdoption.project_id == project_id,
                TenantCatalogAdoption.listing_id == listing_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    actor = require_bounded_text("adopted_by", adopted_by, ADOPTED_BY_MAX)
    row = TenantCatalogAdoption(
        tenant_id=self.context.tenant_id,
        project_id=project_id,
        listing_id=listing.id,
        asset_id=listing.asset_id,
        adopted_by=actor,
    )
    self.session.add(row)
    await self.session.flush()
    asset = await self.session.get(CatalogAsset, listing.asset_id)
    if asset is None:
        from app.repositories.catalog_adoptions import CatalogAdoptionError

        raise CatalogAdoptionError("listing asset missing")
    await audit_record(
        self.session,
        action="catalog.adopted",
        actor=actor,
        target=str(row.id),
        payload=dict(
            audit_safe_adoption_payload(
                listing_id=str(listing.id),
                asset_kind=asset.asset_kind,
                asset_key=asset.asset_key,
                version_label=asset.version_label,
            )
        ),
    )
    return row


async def pre_fix_record_policy_version(
    self, *, project_id, payload, source_label, evidence_ref, actor
):
    from app.repositories.cost_forecasts import CostForecastRepositoryError

    parsed = parse_structured_policy(payload)
    if source_label is not None and (not source_label.strip() or len(source_label) > 255):
        raise CostForecastRepositoryError("source_label_invalid")
    if evidence_ref is not None and (not evidence_ref.strip() or len(evidence_ref) > 500):
        raise CostForecastRepositoryError("evidence_ref_invalid")
    digest = _storage_hash(
        COST_POLICY_CONTRACT_VERSION,
        _money(parsed.max_total_model_cost_usd),
        _money(parsed.max_daily_model_cost_usd),
        _money(parsed.max_cloud_spend_usd),
        _money(parsed.max_ci_minutes_per_day),
        _percent(parsed.require_approval_above_forecast_percentage),
        str(parsed.cheap_first_for_low_risk).lower(),
        str(parsed.frontier_for_high_risk).lower(),
        str(parsed.use_cached_context_when_possible).lower(),
        ",".join(parsed.stop_conditions),
        POLICY_PROVENANCE,
    )
    existing = (
        await self.session.execute(
            select(CostForecastPolicyVersion).where(
                CostForecastPolicyVersion.tenant_id == self.context.tenant_id,
                CostForecastPolicyVersion.project_id == project_id,
                CostForecastPolicyVersion.policy_digest == digest,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = CostForecastPolicyVersion(
        tenant_id=self.context.tenant_id,
        project_id=project_id,
        policy_contract_version=COST_POLICY_CONTRACT_VERSION,
        policy_contract_hash=COST_POLICY_CONTRACT_HASH,
        policy_digest=digest,
        max_total_model_cost_usd=parsed.max_total_model_cost_usd,
        max_daily_model_cost_usd=parsed.max_daily_model_cost_usd,
        max_cloud_spend_usd=parsed.max_cloud_spend_usd,
        max_ci_minutes_per_day=parsed.max_ci_minutes_per_day,
        require_approval_above_forecast_percentage=parsed.require_approval_above_forecast_percentage,
        cheap_first_for_low_risk=parsed.cheap_first_for_low_risk,
        frontier_for_high_risk=parsed.frontier_for_high_risk,
        use_cached_context_when_possible=parsed.use_cached_context_when_possible,
        stop_conditions=list(parsed.stop_conditions),
        stop_condition_count=4,
        source_provenance=POLICY_PROVENANCE,
        source_label=source_label,
        evidence_ref=evidence_ref,
    )
    self.session.add(row)
    await self.session.flush()
    await audit_record(
        self.session,
        action="cost_forecast.policy_recorded",
        actor=actor,
        target=str(row.id),
        payload={
            "project_id": str(project_id),
            "policy_version_id": str(row.id),
            "policy_digest": digest,
            "contract_version": COST_POLICY_CONTRACT_VERSION,
            "source_provenance": POLICY_PROVENANCE,
        },
    )
    return row


async def pre_fix_promote_proposal(self, *, proposal_id, actor, parent_id=None, ref=None):
    prop = await self._get_proposal(proposal_id)
    if prop is None:
        raise LookupError(str(proposal_id))
    existing = await self.promotion_for(proposal_id)
    if existing is not None:
        return await IntakeRepository(self.session, self.context).get_artifact(existing.artifact_id)
    if prop.status != "approved":
        raise ValueError(f"proposal {proposal_id} is not approved (status={prop.status})")
    if prop.proposed_kind not in PROMOTABLE_KINDS:
        raise ValueError(f"proposed_kind {prop.proposed_kind!r} is not promotable in 14b")
    if parent_id is not None and prop.proposed_kind != "acceptance_criterion":
        raise ValueError("parent_id is only valid for acceptance_criterion promotions")
    doc = await DocumentRepository(self.session, self.context).get(prop.source_document_id)
    if doc is None or doc.project_id != prop.project_id:
        raise ValueError("source document not found for this project/tenant")
    if doc.status != "accepted":
        raise ValueError("source document is not accepted")
    if not verify_evidence(doc.content, prop.evidence_quote):
        raise ValueError("evidence quote is not a verbatim substring of the source document")
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
