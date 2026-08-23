"""Slice 61b Docker-free probes: declared identities, scanner, isolation, frozen hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.ecosystem.catalog import ConnectorSpecInput
from app.ecosystem.catalog_declared import (
    DECLARED_CONNECTORS,
    DECLARED_CONNECTOR_SHORT_KEYS,
    DECLARED_INTAKE,
    INTAKE_COMPANION_SENTENCE,
    intake_file_path,
    quoted_registry_keys,
    reference_intake_digest,
    service_module_path,
)
from app.ecosystem.contract_test import run_connector_contract_test
from app.intake.readiness import RULESET_VERSION
from app.release.production_autonomy import A5_RULESET_VERSION, ProductionAutonomyReport
from tests.ecosystem_catalog_support import (
    CATALOG_TABLES,
    CORE_DECISION_GLOBS,
    FROZEN_HASHES,
    real_connector_specs,
)

_OD1: dict[str, ConnectorSpecInput] = {
    "ci_evidence": ConnectorSpecInput(
        protocol_module="app.release.scm_connector",
        protocol_name="SCMConnector",
        fake_name="FakeSCMConnector",
        service_module="app.release.ci_evidence_service",
        live_adapter_status="shipped_mock_tested_no_live_provider",
        live_adapter_name="GitHubSCMConnector",
        tool_names=("source_control.read_branch_protection",),
    ),
    "pr_evidence": ConnectorSpecInput(
        protocol_module="app.release.scm_connector",
        protocol_name="SCMConnector",
        fake_name="FakeSCMConnector",
        service_module="app.release.pr_evidence_service",
        live_adapter_status="shipped_mock_tested_no_live_provider",
        live_adapter_name="GitHubSCMConnector",
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


def test_p1_declared_connectors_match_od1_and_wrapper():
    assert set(DECLARED_CONNECTORS) == set(_OD1)
    for key, expected in _OD1.items():
        assert DECLARED_CONNECTORS[key] == expected
    specs = real_connector_specs()
    assert set(specs) == {"ci", "pr", "deploy", "monitoring", "secrets", "pm"}
    assert set(DECLARED_CONNECTOR_SHORT_KEYS) == set(specs)
    for short, asset_key in DECLARED_CONNECTOR_SHORT_KEYS.items():
        assert specs[short] == DECLARED_CONNECTORS[asset_key]


def test_p2_every_declared_spec_passes_contract_test():
    for spec in DECLARED_CONNECTORS.values():
        assert run_connector_contract_test(spec).passed is True


def test_p3_quoted_registry_keys_match_declared_tool_names():
    for spec in DECLARED_CONNECTORS.values():
        text = service_module_path(spec.service_module).read_text(encoding="utf-8")
        assert quoted_registry_keys(text) == frozenset(spec.tool_names)


def test_p4_scanner_is_registry_key_exact():
    both = 'call("pm.read_issues") then "ci.deploy_production"'
    assert quoted_registry_keys(both) == frozenset({"pm.read_issues", "ci.deploy_production"})
    audit_only = 'action="ci.branch_protection_fetch_failed"'
    assert quoted_registry_keys(audit_only) == frozenset()


def test_p5_intake_file_sentence_and_digest():
    path = Path(DECLARED_INTAKE.source_ref)
    assert path == Path(
        "docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md"
    )
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert INTAKE_COMPANION_SENTENCE in body
    digest = reference_intake_digest(path)
    expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == expected
    assert reference_intake_digest(intake_file_path()) == expected


def test_p6_frozen_sha256_unchanged():
    for path, expected in FROZEN_HASHES.items():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert actual == expected, path


def test_p7_rulesets_and_literal_false_go_live():
    assert A5_RULESET_VERSION == "slice54.v1"
    assert RULESET_VERSION == "slice20.v1"
    report = ProductionAutonomyReport(project_id="probe")
    assert report.to_dict()["can_go_live_autonomously"] is False


def test_p21_populate_module_does_not_name_frozen_engines():
    source = Path("app/ecosystem/catalog_populate.py").read_text(encoding="utf-8")
    for token in ("production_autonomy", "readiness", "control_loop", "broker", "matrix"):
        assert token not in source, token


def test_p25_intake_key_absent_from_core_and_frozen():
    for path in Path("app/intake").rglob("*.py"):
        assert "generic_bounded_counter" not in path.read_text(encoding="utf-8"), path
    for rel in FROZEN_HASHES:
        assert "generic_bounded_counter" not in Path(rel).read_text(encoding="utf-8"), rel
    files: list[Path] = []
    for root in (Path(p) for p in CORE_DECISION_GLOBS):
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.py"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        for table in CATALOG_TABLES:
            assert table not in text, f"{path} mentions {table}"
