"""Slice 52 rollback-drill evidence contract — pure validation, no I/O.

The contract validates a connector-observed CI artifact for one exact A→B→A staging drill.  It
does not claim UAID executed the remote actions or that a future production rollback will succeed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.release.deploy_evidence import DeploySSRFRejected, validate_target_host

SCHEMA_VERSION = "slice52.rollback_drill.v1"
VERIFICATION_CONTRACT_VERSION = "slice52.rollback_verification.v1"
STAGING_TARGET_CONTRACT_VERSION = "slice52.staging_target.v1"
ARTIFACT_PROVENANCE = "connector_verified_ci_rollback"
EXECUTION_OBSERVATION = "connector_observed_ci"
SCOPE_LIMITATION = "from_version_connector_observed_not_deployment_fk"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
RUNNER_MANIFEST_HASH = "73064081141351425c245a6f8bcbe5c6427f130c9a0bf5f8c0aee991ad0a3e53"

PHASE_CODES = (
    "baseline_a_probe",
    "forward_deploy_b",
    "forward_b_probe",
    "rollback_to_a",
    "post_rollback_a_probe",
)
PROBE_PHASES = frozenset(("baseline_a_probe", "forward_b_probe", "post_rollback_a_probe"))
WORKFLOW_CONCLUSIONS = frozenset(
    ("success", "failure", "cancelled", "timed_out", "action_required")
)
PHASE_STATUSES = frozenset(("passed", "failed", "not_run"))

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")

_TOP_FIELDS = frozenset(
    (
        "schema_version",
        "commit_sha",
        "target_binding_hash",
        "from_artifact_digest",
        "to_artifact_digest",
        "runner_manifest_hash",
        "workflow_conclusion",
        "completed_at",
        "phases",
    )
)
_PHASE_FIELDS = frozenset(
    (
        "ordinal",
        "phase_code",
        "phase_status",
        "result_code",
        "target_binding_hash",
        "expected_version_digest",
        "observed_version_digest",
        "health_ok",
        "operation_ok",
        "started_at",
        "completed_at",
    )
)


class InvalidRollbackArtifact(ValueError):
    """The rollback artifact is malformed, inconsistent, or outside the ruled contract."""


class InvalidStagingTarget(ValueError):
    """The canonical staging projection is missing, unsafe, or outside the ruled contract."""


@dataclass(frozen=True)
class StagingTargetProjection:
    provider: str
    domain: str
    binding_hash: str
    contract_version: str = STAGING_TARGET_CONTRACT_VERSION


@dataclass(frozen=True)
class RollbackPhaseObservation:
    ordinal: int
    phase_code: str
    phase_status: str
    result_code: str
    target_binding_hash: str
    expected_version_digest: str
    observed_version_digest: str | None
    health_ok: bool | None
    operation_ok: bool | None
    started_at: datetime
    completed_at: datetime

    def canonical_values(self) -> tuple[str, ...]:
        return (
            str(self.ordinal),
            self.phase_code,
            self.phase_status,
            self.result_code,
            self.target_binding_hash,
            self.expected_version_digest,
            self.observed_version_digest or "",
            "" if self.health_ok is None else str(self.health_ok).lower(),
            "" if self.operation_ok is None else str(self.operation_ok).lower(),
            _utc_text(self.started_at),
            _utc_text(self.completed_at),
        )


@dataclass(frozen=True)
class RollbackDrillArtifact:
    schema_version: str
    commit_sha: str
    target_binding_hash: str
    from_artifact_digest: str
    to_artifact_digest: str
    runner_manifest_hash: str
    workflow_conclusion: str
    completed_at: datetime
    phases: tuple[RollbackPhaseObservation, ...]
    phase_digest: str
    artifact_content_hash: str
    passed: bool
    failed_phase_count: int
    not_run_phase_count: int
    provider_run_ref_hash: str | None = None
    artifact_provenance: str = ARTIFACT_PROVENANCE
    execution_observation: str = EXECUTION_OBSERVATION
    scope_limitation_code: str = SCOPE_LIMITATION


def _canonical_hash(*values: str) -> str:
    raw = "\x1f".join(values).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _require_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise InvalidRollbackArtifact(f"{field} must be a canonical SHA-256 digest")
    return value


def _require_code(value: object, field: str) -> str:
    if not isinstance(value, str) or _CODE_RE.fullmatch(value) is None:
        raise InvalidRollbackArtifact(f"{field} must be a bounded non-blank code")
    return value


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidRollbackArtifact(f"{field} must be an explicit UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidRollbackArtifact(f"{field} must be an explicit UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InvalidRollbackArtifact(f"{field} must be UTC")
    return parsed


def validate_staging_target_projection(payload: object) -> StagingTargetProjection:
    """Read the strict Slice-52 projection without changing canonical template 16."""
    if not isinstance(payload, dict) or set(payload) != {"environments"}:
        raise InvalidStagingTarget("canonical staging projection must contain environments only")
    environments = payload.get("environments")
    if not isinstance(environments, dict) or set(environments) != {"staging"}:
        raise InvalidStagingTarget("canonical staging projection must contain staging only")
    staging = environments.get("staging")
    if not isinstance(staging, dict) or set(staging) != {"provider", "domain"}:
        raise InvalidStagingTarget("staging requires exactly provider and domain")
    if staging.get("provider") != "generic_https":
        raise InvalidStagingTarget("staging provider must be generic_https")
    domain = staging.get("domain")
    if not isinstance(domain, str):
        raise InvalidStagingTarget("staging domain must be a string")
    domain = domain.strip().lower()
    try:
        validate_target_host(domain)
    except DeploySSRFRejected as exc:
        raise InvalidStagingTarget("staging domain is unsafe or malformed") from exc
    return StagingTargetProjection(
        provider="generic_https",
        domain=domain,
        binding_hash=_canonical_hash(STAGING_TARGET_CONTRACT_VERSION, "generic_https", domain),
    )


def _validate_phase(
    raw: object,
    *,
    ordinal: int,
    phase_code: str,
    target_hash: str,
    expected_digest: str,
) -> RollbackPhaseObservation:
    if not isinstance(raw, dict) or set(raw) != _PHASE_FIELDS:
        raise InvalidRollbackArtifact("phase has unknown or missing fields")
    if raw.get("ordinal") != ordinal or raw.get("phase_code") != phase_code:
        raise InvalidRollbackArtifact("phase order or phase code is invalid")
    status = raw.get("phase_status")
    if status not in PHASE_STATUSES:
        raise InvalidRollbackArtifact("phase status is invalid")
    result_code = _require_code(raw.get("result_code"), "result_code")
    if _require_hash(raw.get("target_binding_hash"), "phase target") != target_hash:
        raise InvalidRollbackArtifact("phase target binding does not match")
    if _require_hash(raw.get("expected_version_digest"), "expected version") != expected_digest:
        raise InvalidRollbackArtifact("phase expected version does not match A/B contract")

    observed = raw.get("observed_version_digest")
    health = raw.get("health_ok")
    operation = raw.get("operation_ok")
    is_probe = phase_code in PROBE_PHASES
    if status == "passed":
        required_code = "healthy" if is_probe else "operation_complete"
        if result_code != required_code:
            raise InvalidRollbackArtifact("passed phase result code is inconsistent")
        if is_probe:
            if _require_hash(observed, "observed version") != expected_digest or health is not True:
                raise InvalidRollbackArtifact("probe version or health result is inconsistent")
            if operation is not None:
                raise InvalidRollbackArtifact("probe operation flag must be null")
        else:
            if observed is not None or health is not None or operation is not True:
                raise InvalidRollbackArtifact("action phase result shape is inconsistent")
    elif status == "failed":
        if result_code not in {"unhealthy", "operation_failed"}:
            raise InvalidRollbackArtifact("failed phase result code is inconsistent")
        if is_probe:
            if observed is not None:
                _require_hash(observed, "observed version")
            if health is not False or operation is not None:
                raise InvalidRollbackArtifact("failed probe result shape is inconsistent")
        elif observed is not None or health is not None or operation is not False:
            raise InvalidRollbackArtifact("failed action result shape is inconsistent")
    else:
        if result_code != "not_run_after_failure":
            raise InvalidRollbackArtifact("not-run result code is inconsistent")
        if observed is not None or health is not None or operation is not None:
            raise InvalidRollbackArtifact("not-run phase cannot contain observations")

    started = _timestamp(raw.get("started_at"), "phase started_at")
    completed = _timestamp(raw.get("completed_at"), "phase completed_at")
    if completed <= started:
        raise InvalidRollbackArtifact("phase timestamps are not ordered")
    return RollbackPhaseObservation(
        ordinal=ordinal,
        phase_code=phase_code,
        phase_status=status,
        result_code=result_code,
        target_binding_hash=target_hash,
        expected_version_digest=expected_digest,
        observed_version_digest=observed,
        health_ok=health,
        operation_ok=operation,
        started_at=started,
        completed_at=completed,
    )


def validate_rollback_drill_artifact(
    payload: object, *, expected_commit_sha: str
) -> RollbackDrillArtifact:
    """Validate and derive one exact connector-observed rollback-drill result."""
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        raise InvalidRollbackArtifact("artifact has unknown or missing fields")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise InvalidRollbackArtifact("schema_version is unsupported")
    commit = payload.get("commit_sha")
    if (
        not isinstance(expected_commit_sha, str)
        or _COMMIT_RE.fullmatch(expected_commit_sha) is None
        or commit != expected_commit_sha
    ):
        raise InvalidRollbackArtifact("commit_sha does not match the requested commit")
    target_hash = _require_hash(payload.get("target_binding_hash"), "target_binding_hash")
    from_digest = _require_hash(payload.get("from_artifact_digest"), "from_artifact_digest")
    to_digest = _require_hash(payload.get("to_artifact_digest"), "to_artifact_digest")
    if from_digest == to_digest:
        raise InvalidRollbackArtifact("from and to artifact digests must differ")
    manifest_hash = _require_hash(payload.get("runner_manifest_hash"), "runner_manifest_hash")
    if manifest_hash != RUNNER_MANIFEST_HASH:
        raise InvalidRollbackArtifact("runner manifest is not the code-owned current manifest")
    conclusion = payload.get("workflow_conclusion")
    if conclusion not in WORKFLOW_CONCLUSIONS:
        raise InvalidRollbackArtifact("workflow_conclusion is unsupported")
    artifact_completed = _timestamp(payload.get("completed_at"), "completed_at")
    phase_payloads = payload.get("phases")
    if not isinstance(phase_payloads, list) or len(phase_payloads) != len(PHASE_CODES):
        raise InvalidRollbackArtifact("artifact must contain exactly five phase rows")

    expected_by_phase = (
        from_digest,
        to_digest,
        to_digest,
        from_digest,
        from_digest,
    )
    phases = tuple(
        _validate_phase(
            phase_payloads[index],
            ordinal=index + 1,
            phase_code=PHASE_CODES[index],
            target_hash=target_hash,
            expected_digest=expected_by_phase[index],
        )
        for index in range(len(PHASE_CODES))
    )
    previous_completed: datetime | None = None
    failure_seen = False
    for phase in phases:
        if previous_completed is not None and phase.started_at <= previous_completed:
            raise InvalidRollbackArtifact("phase timestamps are not strictly ordered")
        previous_completed = phase.completed_at
        if phase.phase_status == "failed":
            if failure_seen:
                raise InvalidRollbackArtifact("only the first failed phase may be failed")
            failure_seen = True
        elif phase.phase_status == "not_run" and not failure_seen:
            raise InvalidRollbackArtifact("not-run phase requires an earlier failed phase")
        elif phase.phase_status == "passed" and failure_seen:
            raise InvalidRollbackArtifact("phases after a failure must be not_run")
    if phases[-1].completed_at > artifact_completed:
        raise InvalidRollbackArtifact("artifact completed_at precedes a phase")

    failed_count = sum(phase.phase_status == "failed" for phase in phases)
    not_run_count = sum(phase.phase_status == "not_run" for phase in phases)
    passed = conclusion == "success" and failed_count == 0 and not_run_count == 0
    phase_digest = _canonical_hash(
        VERIFICATION_CONTRACT_VERSION,
        *(value for phase in phases for value in phase.canonical_values()),
    )
    artifact_content_hash = _canonical_hash(
        SCHEMA_VERSION,
        commit,
        target_hash,
        from_digest,
        to_digest,
        manifest_hash,
        conclusion,
        _utc_text(artifact_completed),
        phase_digest,
    )
    return RollbackDrillArtifact(
        schema_version=SCHEMA_VERSION,
        commit_sha=commit,
        target_binding_hash=target_hash,
        from_artifact_digest=from_digest,
        to_artifact_digest=to_digest,
        runner_manifest_hash=manifest_hash,
        workflow_conclusion=conclusion,
        completed_at=artifact_completed,
        phases=phases,
        phase_digest=phase_digest,
        artifact_content_hash=artifact_content_hash,
        passed=passed,
        failed_phase_count=failed_count,
        not_run_phase_count=not_run_count,
    )
