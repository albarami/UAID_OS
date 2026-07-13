"""Tenant-scoped A5 production-autonomy repository (Slice 21..26 + 28 + 30 + 31) — compute-on-read, no persist.

``evaluate`` reads current RLS-scoped state and runs the pure ``app.release.production_autonomy``
engine. It is **read-only**: no rows are written (no ``production_autonomy_reports`` table, no
migration — D-21-A). The verdict is deterministic from current state and always "A5 not satisfied" with
``can_go_live_autonomously`` hard-false — even though gates #2/#3/#4/#5/#6/#7/#8/#11 are PASS-capable,
remaining gates stay unmet. Run inside ``tenant_scope`` (GUC set).

Inputs read for the gates (all partial-context signals are recorded, never gate-passing):
- gate #1: the **current** readiness level via ``ReadinessRepository.evaluate`` (no persisted
  snapshot required);
- gates #2/#12 context: an ``autonomy_policies`` row exists, a ``budgets`` row exists, the
  ``environments_and_deployment_targets`` category is declared;
- gate #5 (Slice 44): connector-observed exact-binding security scan coverage plus the existing
  all-source open-critical count; gate #6 (Slice 45): exact-binding hybrid shortcut coverage;
- gate #8 (Slice 46): non-vacuous canonical-AC scope plus current DB-bound authorship evidence;
- gate #7 (Slices 47 + 50): latest-frozen candidate membership and a latest-wins, DB-bound generated
  release verdict over the re-audited Slice-49 core; legacy issue/risk counts remain context only;
- gate #3 (Slice 26 + 28): the latest ``branch_protection_snapshots`` row **for the project's currently
  declared repo/branch** (``resolve_declared_repo`` + ``latest_branch_protection_for_repo``) plus
  freshness (``CI_EVIDENCE_MAX_AGE_HOURS``). Gate #3 **PASSes** on repo-bound + ``connector_verified`` +
  protection-active + fresh evidence; undeclared/malformed ⇒ ``branch_protection_repo_unbound``;
- gate #2 (Slice 30): the latest ``deployment_target_snapshots`` row for the **currently declared
  production target** (``resolve_declared_production_target`` + ``latest_deployment_target_for_ref``)
  plus ``DEPLOYMENT_EVIDENCE_MAX_AGE_HOURS`` freshness — PASSes on verified + available + fresh;
- gate #11 (Slice 31): the latest ``monitoring_status_snapshots`` row for the **currently declared
  monitoring status_url** (``resolve_declared_monitoring_target`` + ``latest_monitoring_for_ref``) plus
  ``MONITORING_EVIDENCE_MAX_AGE_HOURS`` freshness — PASSes on ``connector_verified`` + valid-read +
  ``overall_active`` + fresh; an unreadable verified+fresh read is ``monitoring_evidence_unreadable``
  (never "inactive", B4).
- gate #4 (Slice 43): compute-on-read conservative coverage over every structurally valid canonical
  project test oracle, selecting one declared-repo + commit binding and exact-definition latest runs.
- gate #5 (Slice 44): compute-on-read latest security coverage for the declared repository and
  code-owned scanner manifest, with a later failed attempt superseding an older pass.
- gate #8 (Slice 46): compute-on-read latest exact scope/authorship binding; only DB-verified
  independent-agent lineage is gate-eligible, while unknown/unapproved/disputed evidence blocks.
Nothing here authorizes go-live.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.release.project_repo import (
    resolve_declared_monitoring_target,
    resolve_declared_production_target,
    resolve_declared_repo,
)
from app.release.production_autonomy import (
    ProductionAutonomyReport,
    evaluate_production_autonomy,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.acceptance_verification import AcceptanceVerificationRepository
from app.repositories.ci_evidence import CIEvidenceRepository
from app.repositories.deployments import DeploymentTargetRepository
from app.repositories.monitoring_evidence import MonitoringEvidenceRepository
from app.repositories.cost import BudgetRepository
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.readiness import ReadinessRepository
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.repositories.release_findings import ReleaseFindingRepository
from app.repositories.release_issues import ReleaseIssueRepository
from app.repositories.release_verdicts import ReleaseVerdictRepository
from app.repositories.risk_acceptance import RiskAcceptanceRepository
from app.repositories.security_scans import SecurityScanRepository
from app.repositories.shortcut_detectors import ShortcutDetectorRepository
from app.repositories.test_oracles import TestOracleRepository
from app.tenancy import TenantContext

_ENV_CATEGORY = "environments_and_deployment_targets"


def _is_fresh(row) -> bool:
    """Slice 28: branch-protection evidence is fresh iff observed within CI_EVIDENCE_MAX_AGE_HOURS."""
    if row is None or row.observed_at is None:
        return False
    max_age = timedelta(hours=settings.ci_evidence_max_age_hours)
    return (datetime.now(timezone.utc) - row.observed_at) <= max_age


def _is_fresh_deploy(row) -> bool:
    """Slice 30: deployment-target evidence is fresh iff observed within
    DEPLOYMENT_EVIDENCE_MAX_AGE_HOURS (its own domain — not CI_EVIDENCE_MAX_AGE_HOURS)."""
    if row is None or row.observed_at is None:
        return False
    max_age = timedelta(hours=settings.deployment_evidence_max_age_hours)
    return (datetime.now(timezone.utc) - row.observed_at) <= max_age


def _is_fresh_monitoring(row) -> bool:
    """Slice 31: monitoring evidence is fresh iff observed within MONITORING_EVIDENCE_MAX_AGE_HOURS
    (its own domain)."""
    if row is None or row.observed_at is None:
        return False
    max_age = timedelta(hours=settings.monitoring_evidence_max_age_hours)
    return (datetime.now(timezone.utc) - row.observed_at) <= max_age


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
        risk_acceptances = RiskAcceptanceRepository(self.session, self.context)
        active_risk_acceptance_count = await risk_acceptances.count_active_nonblocking(project_id)
        issues = ReleaseIssueRepository(self.session, self.context)
        findings = ReleaseFindingRepository(self.session, self.context)
        candidates = ReleaseCandidateRepository(self.session, self.context)
        ci = CIEvidenceRepository(self.session, self.context)
        # Slice 28: gate #3 binds to the project's CURRENTLY declared repo (B1-cont) — the snapshot
        # for that repo/branch, NOT the project-only latest.
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        repo_bound = declared is not None
        if declared is not None:
            latest_bp = await ci.latest_branch_protection_for_repo(
                project_id, declared[0], declared[1]
            )
        else:
            latest_bp = None
        bp_fresh = _is_fresh(latest_bp)
        # Slice 30: gate #2 binds to the project's CURRENTLY declared production target (B-30-3) — the
        # latest snapshot for that exact target, NOT the project-only latest.
        deploy_host = await resolve_declared_production_target(
            self.session, self.context, project_id
        )
        if deploy_host is not None:
            latest_dt = await DeploymentTargetRepository(
                self.session, self.context
            ).latest_deployment_target_for_ref(project_id, "generic_https", deploy_host)
        else:
            latest_dt = None
        # Slice 31: gate #11 binds to the project's CURRENTLY declared monitoring status_url (B2) — the
        # latest snapshot for that exact status_url, NOT the project-only latest.
        monitoring = await resolve_declared_monitoring_target(
            self.session, self.context, project_id
        )
        if monitoring is not None:
            latest_mon = await MonitoringEvidenceRepository(
                self.session, self.context
            ).latest_monitoring_for_ref(project_id, "generic_monitoring_api", monitoring[0])
        else:
            latest_mon = None
        latest_frozen = await candidates.latest_frozen(project_id)
        if latest_frozen is not None:
            bound_open = await candidates.bound_open_issue_count(latest_frozen.id)
            bound_open_blocking = await candidates.bound_open_blocking_issue_count(latest_frozen.id)
            bound_open_unaccepted_blocking = (
                await candidates.bound_open_unaccepted_blocking_issue_count(latest_frozen.id)
            )
            bound_issue_count = await candidates.bound_issue_count(latest_frozen.id)
            bound_trusted_issue_count = await candidates.bound_trusted_issue_count(latest_frozen.id)
            bound_untrusted_issue_count = await candidates.bound_untrusted_issue_count(
                latest_frozen.id
            )
            bound_finding_bridge_issue_count = (
                await candidates.bound_finding_bridge_issue_count(latest_frozen.id)
            )
            bound_security_bridge_issue_count = await candidates.bound_bridge_type_count(
                latest_frozen.id, "security"
            )
            bound_shortcut_bridge_issue_count = await candidates.bound_bridge_type_count(
                latest_frozen.id, "shortcut"
            )
            bound_accepted_issue_count = await candidates.bound_accepted_issue_count(
                latest_frozen.id
            )
            bound_release_consistent_accepted_issue_count = (
                await candidates.bound_release_consistent_accepted_issue_count(latest_frozen.id)
            )
        else:
            bound_open = bound_open_blocking = bound_open_unaccepted_blocking = 0
            bound_issue_count = bound_trusted_issue_count = bound_untrusted_issue_count = 0
            bound_finding_bridge_issue_count = 0
            bound_security_bridge_issue_count = bound_shortcut_bridge_issue_count = 0
            bound_accepted_issue_count = bound_release_consistent_accepted_issue_count = 0
        oracle_coverage = await TestOracleRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        security_coverage = await SecurityScanRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        shortcut_coverage = await ShortcutDetectorRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        acceptance_coverage = await AcceptanceVerificationRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        verdict_coverage = await ReleaseVerdictRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        cost_forecast_coverage = await CostForecastRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        return evaluate_production_autonomy(
            project_id,
            readiness_level=readiness.readiness_level,
            autonomy_policy_present=autonomy is not None,
            cost_policy_present=budget is not None,
            **cost_forecast_coverage.gate_kwargs(),
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
            bound_issue_count=bound_issue_count,
            bound_trusted_issue_count=bound_trusted_issue_count,
            bound_untrusted_issue_count=bound_untrusted_issue_count,
            bound_finding_bridge_issue_count=bound_finding_bridge_issue_count,
            bound_security_bridge_issue_count=bound_security_bridge_issue_count,
            bound_shortcut_bridge_issue_count=bound_shortcut_bridge_issue_count,
            bound_accepted_issue_count=bound_accepted_issue_count,
            bound_release_consistent_accepted_issue_count=(
                bound_release_consistent_accepted_issue_count
            ),
            release_bound_active_risk_acceptance_count=(
                await risk_acceptances.count_release_bound_active(project_id)
            ),
            legacy_unbound_risk_acceptance_count=(
                await risk_acceptances.count_legacy_unbound(project_id)
            ),
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
            branch_protection_repo_bound=repo_bound,
            latest_branch_protection_required_pull_request_reviews=(
                latest_bp.required_pull_request_reviews if latest_bp is not None else None
            ),
            latest_branch_protection_fresh=bp_fresh,
            deployment_target_bound=deploy_host is not None,
            latest_deployment_target_provenance=(
                latest_dt.provenance if latest_dt is not None else None
            ),
            latest_deployment_target_available=(
                latest_dt.target_available if latest_dt is not None else None
            ),
            latest_deployment_target_fresh=_is_fresh_deploy(latest_dt),
            monitoring_bound=monitoring is not None,
            latest_monitoring_provenance=(
                latest_mon.provenance if latest_mon is not None else None
            ),
            latest_monitoring_response_valid=(
                latest_mon.response_valid if latest_mon is not None else None
            ),
            latest_monitoring_overall_active=(
                latest_mon.overall_active if latest_mon is not None else None
            ),
            latest_monitoring_fresh=_is_fresh_monitoring(latest_mon),
            latest_monitoring_failure_kind=(
                latest_mon.failure_kind if latest_mon is not None else None
            ),
            **oracle_coverage.gate_kwargs(),
            **security_coverage.gate_kwargs(),
            **shortcut_coverage.gate_kwargs(),
            **acceptance_coverage.gate_kwargs(),
            **verdict_coverage.gate_kwargs(),
        )
