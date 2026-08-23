"""Declared product-asset identities for Slice 61b catalog population.

These mappings are code-owned. Populate compares stored rows to them
field-for-field before skipping. They are not permission-scoping (D-8),
real-provider tests (D-9), or performed reviews (D-10).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.ecosystem.catalog import ConnectorSpecInput

DECLARED_VERSION_LABEL = "v1"

ACTOR_POPULATE = "slice61b.catalog_populate"
ACTOR_CONTRACT_CHECKER = "slice61b.contract_checker"
ACTOR_BLUEPRINT_REVIEWER = "slice61b.blueprint_review_asserted"
ACTOR_INTAKE_ATTESTOR = "slice61b.intake_attestor"

INTAKE_COMPANION_SENTENCE = "This companion is not a customer, industry, geography, or certifier."

DECLARED_CONNECTOR_SHORT_KEYS: dict[str, str] = {
    "ci": "ci_evidence",
    "pr": "pr_evidence",
    "deploy": "deploy_evidence",
    "monitoring": "monitoring_evidence",
    "secrets": "secrets_verification",
    "pm": "pm_issues",
}

_SCM_PROTOCOL_MODULE = "app.release.scm_connector"
_SCM_PROTOCOL_NAME = "SCMConnector"
_SCM_FAKE_NAME = "FakeSCMConnector"
_SCM_ADAPTER_STATUS = "shipped_mock_tested_no_live_provider"
_SCM_ADAPTER_NAME = "GitHubSCMConnector"

DECLARED_CONNECTORS: dict[str, ConnectorSpecInput] = {
    "ci_evidence": ConnectorSpecInput(
        protocol_module=_SCM_PROTOCOL_MODULE,
        protocol_name=_SCM_PROTOCOL_NAME,
        fake_name=_SCM_FAKE_NAME,
        service_module="app.release.ci_evidence_service",
        live_adapter_status=_SCM_ADAPTER_STATUS,
        live_adapter_name=_SCM_ADAPTER_NAME,
        tool_names=("source_control.read_branch_protection",),
    ),
    "pr_evidence": ConnectorSpecInput(
        protocol_module=_SCM_PROTOCOL_MODULE,
        protocol_name=_SCM_PROTOCOL_NAME,
        fake_name=_SCM_FAKE_NAME,
        service_module="app.release.pr_evidence_service",
        live_adapter_status=_SCM_ADAPTER_STATUS,
        live_adapter_name=_SCM_ADAPTER_NAME,
        tool_names=("source_control.read_pull_request",),
    ),
    "deploy_evidence": ConnectorSpecInput(
        protocol_module="app.release.deploy_connector",
        protocol_name="DeployTargetConnector",
        fake_name="FakeDeployTargetConnector",
        service_module="app.release.deploy_evidence_service",
        live_adapter_status="shipped_mock_tested_no_live_provider",
        live_adapter_name="GenericHttpsDeployTargetConnector",
        tool_names=("deployment.read_target_status",),
    ),
    "monitoring_evidence": ConnectorSpecInput(
        protocol_module="app.release.monitoring_connector",
        protocol_name="MonitoringConnector",
        fake_name="FakeMonitoringConnector",
        service_module="app.release.monitoring_evidence_service",
        live_adapter_status="shipped_mock_tested_no_live_provider",
        live_adapter_name="GenericMonitoringApiConnector",
        tool_names=("monitoring.read_status",),
    ),
    "secrets_verification": ConnectorSpecInput(
        protocol_module="app.release.secrets_connector",
        protocol_name="SecretsManagerConnector",
        fake_name="FakeSecretsManagerConnector",
        service_module="app.release.secrets_verification_service",
        live_adapter_status="shipped_local_no_network",
        live_adapter_name="EnvSecretsManagerConnector",
        tool_names=("secrets.verify_reference",),
    ),
    "pm_issues": ConnectorSpecInput(
        protocol_module="app.release.pm_connector",
        protocol_name="IssueTrackerConnector",
        fake_name="FakeIssueTrackerConnector",
        service_module="app.release.pm_sync_service",
        live_adapter_status="absent",
        live_adapter_name=None,
        tool_names=("pm.read_issues",),
    ),
}


@dataclass(frozen=True)
class DeclaredIntake:
    """Registrar identity for the one reference-intake companion."""

    asset_key: str
    version_label: str
    domain_label: str
    source_ref: str


DECLARED_INTAKE = DeclaredIntake(
    asset_key="generic_bounded_counter",
    version_label=DECLARED_VERSION_LABEL,
    domain_label="generic",
    source_ref=(
        "docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md"
    ),
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def service_module_path(service_module: str) -> Path:
    """Map ``app.release.ci_evidence_service`` to its source file path."""
    return _REPO_ROOT.joinpath(*service_module.split(".")).with_suffix(".py")


def intake_file_path() -> Path:
    """Absolute path of the declared reference-intake companion."""
    return _REPO_ROOT / DECLARED_INTAKE.source_ref


def reference_intake_digest(path: Path | str) -> str:
    """Return ``sha256:`` + hex of the file bytes. Drift metadata, not authentication."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def quoted_registry_keys(source_text: str) -> frozenset[str]:
    """Return TOOL_REGISTRY keys that appear as a quoted substring of ``source_text``.

    No AST. No import graph. A quoted audit-action string that is not a registry
    key is ignored. This is source↔DECLARED regression evidence, not D-8.
    """
    from app.tools.registry import TOOL_REGISTRY

    found: set[str] = set()
    for key in TOOL_REGISTRY:
        if f'"{key}"' in source_text or f"'{key}'" in source_text:
            found.add(key)
    return frozenset(found)
