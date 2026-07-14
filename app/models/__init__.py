"""SQLAlchemy ORM models for the UAID OS control-plane spine.

Importing this package imports every model so that ``Base.metadata`` is fully
populated (Alembic autogenerate and the test schema build both depend on this).
"""

from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_failure_event import AgentFailureEvent
from app.models.agent_instance import AgentInstance
from app.models.agent_tool_allowlist import AgentToolAllowlist
from app.models.agent_version import AgentVersion
from app.models.approval import Approval
from app.models.approval_event import ApprovalEvent
from app.models.acceptance_verification import (
    AcceptanceCriterionAuthorshipRecord,
    AcceptanceVerificationResult,
    AcceptanceVerificationRun,
)
from app.models.audit_log import AuditLog
from app.models.audit_chain_verification import AuditChainVerification
from app.models.autonomy_policy import AutonomyPolicy
from app.models.base import Base
from app.models.branch_protection_snapshot import BranchProtectionSnapshot
from app.models.budget import Budget
from app.models.cost_event import CostEvent
from app.models.cost_forecast import (
    CostForecastDimensionResult,
    CostForecastInputLine,
    CostForecastLedgerEventRef,
    CostForecastPolicyVersion,
    CostForecastRun,
)
from app.models.deployment_target_snapshot import DeploymentTargetSnapshot
from app.models.document import Document
from app.models.document_classification import DocumentClassification
from app.models.generated_artifact import GeneratedArtifact
from app.models.semantic_contradiction_report import SemanticContradictionReport
from app.models.semantic_contradiction import SemanticContradiction
from app.models.squad_matching import SquadManifestRecord, SkillMatch
from app.models.agent_realization import AgentRealization, AgentRealizationReviewer
from app.models.archetype_eval import ArchetypeEval
from app.models.qualification_run import QualificationRun, QualificationCaseResult
from app.models.extraction_promotion import ExtractionPromotion
from app.models.extraction_proposal import ExtractionProposal
from app.models.extraction_run import ExtractionRun
from app.models.intake_artifact import IntakeArtifact
from app.models.intake_category import IntakeCategory
from app.models.intake_findings_report import IntakeFindingsReport
from app.models.intake_provenance import IntakeProvenance
from app.models.run_checkpoint import RunCheckpoint
from app.models.run_checkpoint_write import RunCheckpointWrite
from app.models.run_step import RunStep
from app.models.tenant_api_key import TenantApiKey
from app.models.organization import Organization
from app.models.monitoring_status_snapshot import MonitoringStatusSnapshot
from app.models.approval_notification import ApprovalNotification
from app.models.pm_issue_mapping import PMIssueMapping
from app.models.project import Project
from app.models.project_run import ProjectRun
from app.models.secret_reference_check import SecretReferenceCheck
from app.models.security_scan_category_result import SecurityScanCategoryResult
from app.models.security_scan_run import SecurityScanRun
from app.models.shortcut_detector_category_result import ShortcutDetectorCategoryResult
from app.models.shortcut_detector_reviewer_result import ShortcutDetectorReviewerResult
from app.models.shortcut_detector_run import ShortcutDetectorRun
from app.models.pull_request_evidence_snapshot import PullRequestEvidenceSnapshot
from app.models.readiness_report import ReadinessReportRecord
from app.models.review_report import ReviewReport
from app.models.reviewer_quality import (
    ReviewerQAFixtureCase,
    ReviewerQAFixtureDefect,
    ReviewerQAFixtureSuite,
    ReviewerQualityCaseResult,
    ReviewerQualityDefectResult,
    ReviewerQualityRecord,
)
from app.models.task_contract import (
    TaskContract,
    TaskContractArtifactLink,
    TaskContractEvent,
    TaskContractReviewer,
)
from app.models.test_oracle_run import TestOracleRun
from app.models.test_result import TestResult
from app.models.evidence_pack import (
    EvidencePack,
    EvidencePackGenerationRun,
    EvidencePackSectionResult,
    EvidencePackSourceRef,
)
from app.models.release_finding import ReleaseFinding
from app.models.release_finding_event import ReleaseFindingEvent
from app.models.release_candidate import ReleaseCandidate
from app.models.release_candidate_event import ReleaseCandidateEvent
from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
from app.models.release_issue import ReleaseIssue
from app.models.release_issue_event import ReleaseIssueEvent
from app.models.release_verdict import (
    ReleaseVerdict,
    ReleaseVerdictIssueResult,
    ReleaseVerdictRun,
)
from app.models.rollback_verification import (
    RollbackVerificationPhaseResult,
    RollbackVerificationRun,
)
from app.models.risk_acceptance_event import RiskAcceptanceEvent
from app.models.risk_acceptance_record import RiskAcceptanceRecord
from app.models.tenant import Tenant
from app.models.tool_call import ToolCall

__all__ = [
    "Base",
    "Organization",
    "Tenant",
    "Project",
    "ProjectRun",
    "AuditLog",
    "AuditChainVerification",
    "AutonomyPolicy",
    "Approval",
    "ApprovalEvent",
    "AcceptanceCriterionAuthorshipRecord",
    "AcceptanceVerificationRun",
    "AcceptanceVerificationResult",
    "ToolCall",
    "AgentToolAllowlist",
    "AgentBlueprint",
    "AgentVersion",
    "AgentInstance",
    "AgentFailureEvent",
    "CostEvent",
    "Budget",
    "CostForecastPolicyVersion",
    "CostForecastRun",
    "CostForecastLedgerEventRef",
    "CostForecastInputLine",
    "CostForecastDimensionResult",
    "BranchProtectionSnapshot",
    "PullRequestEvidenceSnapshot",
    "DeploymentTargetSnapshot",
    "MonitoringStatusSnapshot",
    "SecretReferenceCheck",
    "SecurityScanRun",
    "SecurityScanCategoryResult",
    "ShortcutDetectorRun",
    "ShortcutDetectorCategoryResult",
    "ShortcutDetectorReviewerResult",
    "ApprovalNotification",
    "PMIssueMapping",
    "RunCheckpoint",
    "RunCheckpointWrite",
    "RunStep",
    "Document",
    "DocumentClassification",
    "GeneratedArtifact",
    "SemanticContradictionReport",
    "SemanticContradiction",
    "SquadManifestRecord",
    "SkillMatch",
    "AgentRealization",
    "AgentRealizationReviewer",
    "ArchetypeEval",
    "QualificationRun",
    "QualificationCaseResult",
    "ExtractionRun",
    "ExtractionProposal",
    "ExtractionPromotion",
    "IntakeArtifact",
    "IntakeCategory",
    "IntakeFindingsReport",
    "IntakeProvenance",
    "ReadinessReportRecord",
    "TaskContract",
    "TaskContractArtifactLink",
    "TaskContractReviewer",
    "TaskContractEvent",
    "ReviewReport",
    "ReviewerQAFixtureSuite",
    "ReviewerQAFixtureCase",
    "ReviewerQAFixtureDefect",
    "ReviewerQualityRecord",
    "ReviewerQualityCaseResult",
    "ReviewerQualityDefectResult",
    "TestOracleRun",
    "TestResult",
    "EvidencePackGenerationRun",
    "EvidencePack",
    "EvidencePackSourceRef",
    "EvidencePackSectionResult",
    "RiskAcceptanceRecord",
    "RiskAcceptanceEvent",
    "ReleaseFinding",
    "ReleaseFindingEvent",
    "ReleaseIssue",
    "ReleaseIssueEvent",
    "ReleaseCandidate",
    "ReleaseCandidateEvent",
    "ReleaseCandidateIssueBinding",
    "ReleaseVerdictRun",
    "ReleaseVerdict",
    "ReleaseVerdictIssueResult",
    "RollbackVerificationRun",
    "RollbackVerificationPhaseResult",
    "TenantApiKey",
]
