"""Tenant-scoped A5 production-autonomy repository (Slice 21 + 22 + 23) — compute-on-read, no persist.

``evaluate`` reads current RLS-scoped state and runs the pure ``app.release.production_autonomy``
engine. It is **read-only**: no rows are written (no ``production_autonomy_reports`` table, no
migration — D-21-A). The verdict is deterministic from current state and, this slice, always "A5 not
satisfied" with ``can_go_live_autonomously`` hard-false. Run inside ``tenant_scope`` (GUC set).

Inputs read for the gates (all partial-context signals are recorded, never gate-passing):
- gate #1: the **current** readiness level via ``ReadinessRepository.evaluate`` (no persisted
  snapshot required);
- gates #2/#12 context: an ``autonomy_policies`` row exists, a ``budgets`` row exists, the
  ``environments_and_deployment_targets`` category is declared;
- gates #5/#6 (Slice 23): ``ReleaseFindingRepository.count_open`` /
  ``count_open_unaccepted_critical`` for ``security`` and ``shortcut`` — surfaced as the four
  ``context`` counts; both stay ``insufficient_evidence:no_finding_provenance_or_scan_source``;
- gate #7 (Slice 22): ``RiskAcceptanceRepository.count_active_nonblocking`` — surfaced as
  ``context.active_risk_acceptance_count``; stays ``insufficient_evidence:no_open_issue_store``.
Nothing here authorizes go-live.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.release.production_autonomy import (
    ProductionAutonomyReport,
    evaluate_production_autonomy,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.cost import BudgetRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.readiness import ReadinessRepository
from app.repositories.release_findings import ReleaseFindingRepository
from app.repositories.risk_acceptance import RiskAcceptanceRepository
from app.tenancy import TenantContext

_ENV_CATEGORY = "environments_and_deployment_targets"


class ProductionAutonomyRepository:
    """Composes other tenant-scoped repositories; owns no table, so it is not a
    ``TenantScopedRepository`` (nothing to write/stamp). All reads it issues go through
    tenant-scoped repositories inside the caller's ``tenant_scope``/RLS."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        self.session = session
        self.context = context

    async def evaluate(self, project_id: uuid.UUID) -> ProductionAutonomyReport:
        """Compute the §Appendix-B A5 report from current state. Read-only — writes nothing."""
        readiness = await ReadinessRepository(self.session, self.context).evaluate(project_id)
        autonomy = await AutonomyPolicyRepository(self.session, self.context).get_for_project(
            project_id
        )
        budget = await BudgetRepository(self.session, self.context).get(project_id)
        categories = await IntakeCategoryRepository(self.session, self.context).list_categories(
            project_id
        )
        environments_declared = any(
            c.category == _ENV_CATEGORY and c.status == "declared" for c in categories
        )
        active_risk_acceptance_count = await RiskAcceptanceRepository(
            self.session, self.context
        ).count_active_nonblocking(project_id)
        findings = ReleaseFindingRepository(self.session, self.context)
        return evaluate_production_autonomy(
            project_id,
            readiness_level=readiness.readiness_level,
            autonomy_policy_present=autonomy is not None,
            cost_policy_present=budget is not None,
            environments_declared=environments_declared,
            active_risk_acceptance_count=active_risk_acceptance_count,
            open_security_finding_count=await findings.count_open(project_id, "security"),
            open_unaccepted_critical_security_finding_count=(
                await findings.count_open_unaccepted_critical(project_id, "security")
            ),
            open_shortcut_finding_count=await findings.count_open(project_id, "shortcut"),
            open_unaccepted_critical_shortcut_finding_count=(
                await findings.count_open_unaccepted_critical(project_id, "shortcut")
            ),
        )
