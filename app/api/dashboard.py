"""Read-only dashboard endpoints (Slice 10, §18.6). API-only JSON.

Every endpoint requires a bearer API key (``require_tenant``), then opens
``tenant_scope`` so all reads pass through RLS. A ``project_id`` outside the caller's
tenant yields no rows (never another tenant's data). GET-only — no mutations.

Covers the implemented §18.6 subset: run state, open approvals, blockers, cost
consumed + stop decision. Forecast / critical path / readiness / evidence-pack /
high-risk findings / deployment / next action are deferred (subsystems not built).
"""

import uuid

from fastapi import APIRouter, Depends

from app.api.auth import require_tenant
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.cost import evaluate as cost_evaluate
from app.repositories.documents import DocumentRepository
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
