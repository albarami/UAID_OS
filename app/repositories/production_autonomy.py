"""Tenant-scoped A5 production-autonomy repository (Slice 21 + 22 + 23 + 24 + 25) — compute-on-read, no persist.

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
- gate #7 (Slice 22 + 24 + 25): ``RiskAcceptanceRepository.count_active_nonblocking`` +
  ``ReleaseIssueRepository`` open counts + ``ReleaseCandidateRepository.count_frozen`` /
  ``latest_frozen`` + bound-issue counts — surfaced as ``context``. The reason narrows to
  ``no_issue_provenance`` when a frozen release candidate exists; it stays
  ``insufficient_evidence`` and never passes.
Nothing here authorizes go-live.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.release.production_autonomy import (
    ProductionAutonomyReport,
    evaluate_production_autonomy,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.ci_evidence import CIEvidenceRepository
from app.repositories.cost import BudgetRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.readiness import ReadinessRepository
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.repositories.release_findings import ReleaseFindingRepository
from app.repositories.release_issues import ReleaseIssueRepository
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
        issues = ReleaseIssueRepository(self.session, self.context)
        findings = ReleaseFindingRepository(self.session, self.context)
        candidates = ReleaseCandidateRepository(self.session, self.context)
        ci = CIEvidenceRepository(self.session, self.context)
        latest_bp = await ci.latest_branch_protection(project_id)
        latest_frozen = await candidates.latest_frozen(project_id)
        if latest_frozen is not None:
            bound_open = await candidates.bound_open_issue_count(latest_frozen.id)
            bound_open_blocking = await candidates.bound_open_blocking_issue_count(latest_frozen.id)
            bound_open_unaccepted_blocking = (
                await candidates.bound_open_unaccepted_blocking_issue_count(latest_frozen.id)
            )
        else:
            bound_open = bound_open_blocking = bound_open_unaccepted_blocking = 0
        return evaluate_production_autonomy(
            project_id,
            readiness_level=readiness.readiness_level,
            autonomy_policy_present=autonomy is not None,
            cost_policy_present=budget is not None,
            environments_declared=environments_declared,
            active_risk_acceptance_count=active_risk_acceptance_count,
            open_issue_count=await issues.count_open(project_id),
            open_blocking_issue_count=await issues.count_open_blocking(project_id),
            open_unaccepted_blocking_issue_count=(
                await issues.count_open_unaccepted_blocking(project_id)
            ),
            frozen_release_candidate_count=await candidates.count_frozen(project_id),
            latest_frozen_release_candidate_id=(
                str(latest_frozen.id) if latest_frozen is not None else None
            ),
            latest_frozen_release_ref=(
                latest_frozen.release_ref if latest_frozen is not None else None
            ),
            bound_open_issue_count=bound_open,
            bound_open_blocking_issue_count=bound_open_blocking,
            bound_open_unaccepted_blocking_issue_count=bound_open_unaccepted_blocking,
            open_security_finding_count=await findings.count_open(project_id, "security"),
            open_unaccepted_critical_security_finding_count=(
                await findings.count_open_unaccepted_critical(project_id, "security")
            ),
            open_shortcut_finding_count=await findings.count_open(project_id, "shortcut"),
            open_unaccepted_critical_shortcut_finding_count=(
                await findings.count_open_unaccepted_critical(project_id, "shortcut")
            ),
            branch_protection_snapshot_count=(
                await ci.count_branch_protection_snapshots(project_id)
            ),
            connector_verified_branch_protection_count=(
                await ci.count_connector_verified_branch_protection(project_id)
            ),
            latest_branch_protection_provenance=(
                latest_bp.provenance if latest_bp is not None else None
            ),
            latest_branch_protection_enabled=(
                latest_bp.protection_enabled if latest_bp is not None else None
            ),
            latest_required_status_check_count=(
                latest_bp.required_status_check_count if latest_bp is not None else 0
            ),
        )
