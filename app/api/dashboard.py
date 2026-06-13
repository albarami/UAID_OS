"""Read-only dashboard endpoints (Slice 10 + Slice 17, §18.6). API-only JSON.

Every endpoint requires a bearer API key (``require_tenant``), then opens
``tenant_scope`` so all reads pass through RLS. A ``project_id`` outside the caller's
tenant yields no rows (never another tenant's data). GET-only — no mutations.

Covers the implemented §18.6 subset: run state, open approvals, blockers, cost
consumed + stop decision, and (Slice 17) the latest persisted build-readiness (§4.5)
and gap/contradiction findings snapshots. Forecast / critical path / evidence-pack /
deployment / next action are deferred (subsystems not built).

The readiness/findings endpoints return the **latest persisted snapshot** via
``repo.latest`` (a read-only, tenant+project-scoped SELECT) — they never compute or
persist on a GET. No snapshot, a cross-tenant ``project_id``, and a nonexistent
project are all indistinguishable: ``200`` with a ``null`` body (no existence oracle).
"""

import uuid

from fastapi import APIRouter, Depends

from app.api.auth import require_tenant
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.cost import evaluate as cost_evaluate
from app.repositories.documents import DocumentRepository
from app.repositories.findings import FindingsRepository
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
