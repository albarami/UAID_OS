"""Read-only dashboard endpoints (Slice 10 + Slice 17 + Slice 19 + Slice 21, §18.6). API-only JSON.

Every endpoint requires a bearer API key (``require_tenant``), then opens
``tenant_scope`` so all reads pass through RLS. A ``project_id`` outside the caller's
tenant yields no rows (never another tenant's data). GET-only — no mutations.

Covers the implemented §18.6 subset: run state, open approvals, blockers, cost
consumed + stop decision, (Slice 17) the latest persisted build-readiness (§4.5)
and gap/contradiction findings snapshots, (Slice 19) their full snapshot **history**,
and (Slice 21) the fail-closed A5 **production-autonomy** report. Forecast / critical
path / evidence-pack / deployment / next action are deferred (subsystems not built).

Two distinct read shapes, both GET-only and never mutating:
- **readiness/findings (Slice 17/19)** — return **persisted snapshots**, no compute on GET.
  ``…/readiness`` & ``…/findings`` (``repo.latest``): latest snapshot or ``null``.
  ``…/{readiness,findings}/history`` (``repo.history``): the full list (newest-first) or ``[]``.
  No-snapshot / cross-tenant / nonexistent are indistinguishable (``200`` + ``null``/``[]``).
- **production_autonomy (Slice 21)** — **computed on read** (no persistence), always
  non-authorizing: ``a5_satisfied``/``can_go_live_autonomously`` are always false. Returns a
  report (never ``null``); cross-tenant/nonexistent yield a generic not-satisfied report (no leak).
"""

import uuid

from fastapi import APIRouter, Depends

from app.api.auth import require_tenant
from app.repositories.approvals import ApprovalRepository
from app.repositories.ci_evidence import CIEvidenceRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.cost import evaluate as cost_evaluate
from app.repositories.documents import DocumentRepository
from app.repositories.findings import FindingsRepository
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.repositories.readiness import ReadinessRepository
from app.repositories.runs import RunRepository
from app.tenancy import TenantContext, tenant_scope

router = APIRouter(prefix="/api", tags=["dashboard"])


def _run_dict(run) -> dict:
    return {
        "id": str(run.id),
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _approval_dict(appr) -> dict:
    return {
        "id": str(appr.id),
        "action": appr.action,
        "subject_ref": appr.subject_ref,
        "risk_tier": appr.risk_tier,
        "requested_at": appr.requested_at.isoformat(),
    }


def _readiness_dict(rec) -> dict:
    # ``evaluated_by`` (untrusted internal label) is intentionally omitted (D-17-1).
    return {
        "report_id": str(rec.id),
        "evaluated_at": rec.created_at.isoformat(),
        "readiness_level": rec.readiness_level,
        "can_build_to_staging": rec.can_build_to_staging,
        "can_go_live_autonomously": rec.can_go_live_autonomously,
        "report": rec.report,  # full §4.5 doc + extensions, already JSON-safe from JSONB
    }


def _findings_dict(rec) -> dict:
    # ``evaluated_by`` (untrusted internal label) is intentionally omitted (D-17-1).
    return {
        "report_id": str(rec.id),
        "evaluated_at": rec.created_at.isoformat(),
        "gap_count": rec.gap_count,
        "contradiction_count": rec.contradiction_count,
        "report": rec.report,  # gaps/contradictions (refs only) + counts, JSON-safe
    }


def _ci_evidence_dict(rec) -> dict:
    # Slice 26 — latest branch-protection snapshot. ``provenance`` distinguishes observed-unverified
    # (the only value writable this slice) from connector_verified (Slice 28). Returned only on the
    # tenant's own dashboard (their data); the audit log excludes repo_ref/check-names.
    return {
        "snapshot_id": str(rec.id),
        "observed_at": rec.observed_at.isoformat() if rec.observed_at is not None else None,
        "recorded_at": rec.created_at.isoformat(),
        "provider": rec.provider,
        "repo_ref": rec.repo_ref,
        "branch": rec.branch,
        "protection_enabled": rec.protection_enabled,
        "required_pull_request_reviews": rec.required_pull_request_reviews,
        "required_status_checks": rec.required_status_checks,
        "required_status_check_count": rec.required_status_check_count,
        "enforce_admins": rec.enforce_admins,
        "provenance": rec.provenance,
    }


@router.get("/projects/{project_id}/runs")
async def project_runs(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        runs = await RunRepository(session, context).list_for_project(project_id)
        return {"runs": [_run_dict(r) for r in runs]}


@router.get("/projects/{project_id}/approvals")
async def project_open_approvals(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        pending = await ApprovalRepository(session, context).list_pending(project_id)
        return {"open_approvals": [_approval_dict(a) for a in pending]}


@router.get("/projects/{project_id}/blockers")
async def project_blockers(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        runs = await RunRepository(session, context).list_for_project(project_id)
        pending = await ApprovalRepository(session, context).list_pending(project_id)
        quarantined = await DocumentRepository(session, context).count_quarantined(project_id)
        return {
            "blocked_runs": [_run_dict(r) for r in runs if r.status == "blocked"],
            "open_approvals": [_approval_dict(a) for a in pending],
            "quarantined_documents": quarantined,
        }


@router.get("/projects/{project_id}/cost")
async def project_cost(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        total = await CostEventRepository(session, context).total_spent(project_id)
        budget = await BudgetRepository(session, context).get(project_id)
        decision = await cost_evaluate(session, context, project_id=project_id)
        return {
            "total_spent": str(total),
            "budget": (
                None
                if budget is None
                else {
                    "max_total_cost_usd": str(budget.max_total_cost_usd),
                    "max_daily_cost_usd": (
                        None
                        if budget.max_daily_cost_usd is None
                        else str(budget.max_daily_cost_usd)
                    ),
                }
            ),
            "decision": {
                "stop": decision.stop,
                "reason": decision.reason.value if decision.reason else None,
            },
        }


@router.get("/projects/{project_id}/readiness")
async def project_readiness(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        rec = await ReadinessRepository(session, context).latest(project_id)
        return {"readiness": _readiness_dict(rec) if rec is not None else None}


@router.get("/projects/{project_id}/findings")
async def project_findings(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        rec = await FindingsRepository(session, context).latest(project_id)
        return {"findings": _findings_dict(rec) if rec is not None else None}


@router.get("/projects/{project_id}/readiness/history")
async def project_readiness_history(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    # Full persisted history, newest-first (repo.history orders created_at DESC, id DESC).
    async with tenant_scope(context) as session:
        rows = await ReadinessRepository(session, context).history(project_id)
        return {"readiness_history": [_readiness_dict(r) for r in rows]}


@router.get("/projects/{project_id}/findings/history")
async def project_findings_history(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    async with tenant_scope(context) as session:
        rows = await FindingsRepository(session, context).history(project_id)
        return {"findings_history": [_findings_dict(r) for r in rows]}


@router.get("/projects/{project_id}/production_autonomy")
async def project_production_autonomy(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    # Slice 21 — fail-closed, non-authorizing A5 evaluator. Computed on read (no persistence);
    # always not-A5-satisfied, can_go_live_autonomously false. Cross-tenant/nonexistent yields a
    # generic not-satisfied report (no leak), never null.
    async with tenant_scope(context) as session:
        report = await ProductionAutonomyRepository(session, context).evaluate(project_id)
        return {"production_autonomy": report.to_dict()}


@router.get("/projects/{project_id}/ci_evidence")
async def project_ci_evidence(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    # Slice 26 — latest source-control/CI branch-protection snapshot (the A5 gate-#3 evidence class),
    # or null. Latest-only (no list/history this slice). Never-recorded / cross-tenant / nonexistent
    # are indistinguishable (200 + null, no existence oracle).
    async with tenant_scope(context) as session:
        rec = await CIEvidenceRepository(session, context).latest_branch_protection(project_id)
        return {"ci_evidence": _ci_evidence_dict(rec) if rec is not None else None}
