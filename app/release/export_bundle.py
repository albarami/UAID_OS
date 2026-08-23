"""Pure Slice-60 offline auditor bundle contract.

No I/O. Validity is never stored: it is only the return value of verification
recomputed from persisted bytes. The signature is app-key-custody, not a human
signature, authority attestation, or PKI root.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.release.evidence_pack import (
    CANONICAL_SCHEMA_VERSION,
    canonical_json_bytes,
    digest_bytes,
)

BUNDLE_CONTRACT_VERSION = "slice60.export_bundle.v1"
MANIFEST_VERSION = "slice60.signed_manifest.v1"
REDACTION_POLICY_VERSION = "slice60.redaction_policy.v1"
VERIFICATION_CONTRACT_VERSION = "slice60.bundle_verification.v1"
SIGNATURE_ALGORITHM = "ed25519"
AUDITOR_ACCESS_MODE = "offline_bundle"
EXPORT_BUNDLE_VALIDITY_HOURS = 720
MAX_BUNDLE_FILE_BYTES = 16 * 1024 * 1024
MAX_IDEMPOTENCY = 200
MAX_SIGNING_KEY_ID = 200
FILE_COUNT = 4
MANIFESTED_FILE_COUNT = 2
DIGEST_RE = r"^sha256:[0-9a-f]{64}$"
APP_KEY_CUSTODY_SIGNED = "app_key_custody_signed"
AUDIT_ATTEMPT_NON_EVIDENCE = "audit_event_is_a_reported_attempt_not_validity_evidence"
SIGNING_KEY_NOT_CONFIGURED = "signing_key_not_configured"
SIGNING_KEY_NOT_SELF_CONSISTENT = "signing_key_not_self_consistent"


class IntegrityResult(str, Enum):
    """Cryptographic and content axis. Never persisted."""

    VERIFIED = "verified"
    UNTRUSTED_SIGNING_KEY = "untrusted_signing_key"
    SIGNATURE_INVALID = "signature_invalid"
    MANIFEST_INVALID = "manifest_invalid"
    MANIFEST_DIGEST_MISMATCH = "manifest_digest_mismatch"
    MANIFEST_BINDING_MISMATCH = "manifest_binding_mismatch"
    PAYLOAD_HASH_MISMATCH = "payload_hash_mismatch"
    STORED_BYTES_HASH_MISMATCH = "stored_bytes_hash_mismatch"
    REDACTION_POLICY_DIGEST_MISMATCH = "redaction_policy_digest_mismatch"
    FILE_SET_INCOMPLETE = "file_set_incomplete"


class HorizonStatus(str, Enum):
    """Declared-validity axis. Independent of integrity. Never persisted."""

    WITHIN = "within_declared_horizon"
    EXPIRED = "expired_declared_horizon"


@dataclass(frozen=True)
class BundleFileSpec:
    """One ordered bundle file. Ordinal is load-bearing."""

    ordinal: int
    file_name: str
    media_type: str


BUNDLE_FILES: tuple[BundleFileSpec, ...] = (
    BundleFileSpec(1, "evidence_pack.json", "application/json"),
    BundleFileSpec(2, "evidence_pack_core.preview.md", "text/markdown; charset=utf-8"),
    BundleFileSpec(3, "evidence_pack.manifest.json", "application/json"),
    BundleFileSpec(4, "evidence_pack.manifest.sig", "application/octet-stream"),
)
MANIFESTED_FILES: tuple[BundleFileSpec, ...] = BUNDLE_FILES[:MANIFESTED_FILE_COUNT]

LIMITATIONS: tuple[str, ...] = (
    "signature_is_app_key_custody_not_human_or_authority",
    "signing_key_is_not_externally_rooted_no_pki_or_transparency_log",
    "canonical_json_is_unsigned_signature_is_detached",
    "human_readable_file_is_a_core_preview_not_a_full_report",
    "no_pdf_export",
    "offline_bundle_expiry_is_declared_not_enforced",
    "no_oscal_control_mapping_optional_per_spec_2907",
    "no_scoped_link_or_temporary_audit_account",
    "redaction_policy_is_the_enforced_field_projection_not_a_human_approved_classification",
    "export_is_a_claim_about_evidence_not_a_replacement_for_it",
)

_MANIFEST_REQUIRED_KEYS = (
    "manifest_version",
    "schema_version",
    "project_id",
    "release_candidate_id",
    "evidence_pack_id",
    "release_verdict_id",
    "generated_at",
    "core_content_hash",
    "immutable_log_reference",
    "signing_key_id",
    "signature_algorithm",
    "redaction_policy",
    "auditor_access",
    "files",
    "limitations",
)
_FILE_REQUIRED_KEYS = ("ordinal", "file_name", "media_type", "byte_count", "sha256")


class ExportBundleError(ValueError):
    """Fail-closed export-bundle contract error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ExportBundleIdempotencyRace(ExportBundleError):
    """Winner stayed invisible after bounded REPEATABLE READ retries."""


@dataclass(frozen=True)
class ManifestedFile:
    """One payload file enumerated by the signed manifest."""

    ordinal: int
    file_name: str
    media_type: str
    byte_count: int
    sha256: str

    def as_payload(self) -> dict[str, Any]:
        """Return the canonical JSON object for this file row."""
        return {
            "byte_count": self.byte_count,
            "file_name": self.file_name,
            "media_type": self.media_type,
            "ordinal": self.ordinal,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class BundleVerification:
    """Compute-on-read result. Never persisted. Two independent axes."""

    integrity_result: IntegrityResult
    horizon_status: HorizonStatus

    @property
    def signature_status(self) -> str | None:
        """Return ``app_key_custody_signed`` iff integrity verified, else ``None``."""
        if self.integrity_result is IntegrityResult.VERIFIED:
            return APP_KEY_CUSTODY_SIGNED
        return None


@dataclass(frozen=True)
class ExportBundleSnapshot:
    """Safe export-record surface. Omits file bytes and signature material."""

    id: uuid.UUID
    project_id: uuid.UUID
    evidence_pack_id: uuid.UUID
    release_candidate_id: uuid.UUID
    release_verdict_id: uuid.UUID
    audit_checkpoint_id: uuid.UUID
    idempotency_key: str
    bundle_contract_version: str
    manifest_digest: str
    redaction_policy_digest: str
    core_content_hash: str
    immutable_log_reference: str
    signing_key_id: str
    auditor_access_mode: str
    as_of: datetime
    expires_at: datetime
    file_count: int
    total_byte_count: int


def utc_now() -> datetime:
    """Return the current UTC instant used for declared-horizon comparison."""
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    """Return an RFC-3339 UTC timestamp ending in ``Z``."""
    if value.tzinfo is None:
        raise ExportBundleError("datetime_timezone_required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def horizon_status_for(expires_at: datetime, *, now: datetime | None = None) -> HorizonStatus:
    """Return the declared-horizon axis for ``expires_at`` relative to ``now``."""
    instant = utc_now() if now is None else now
    if instant.tzinfo is None or expires_at.tzinfo is None:
        raise ExportBundleError("datetime_timezone_required")
    if instant.astimezone(timezone.utc) >= expires_at.astimezone(timezone.utc):
        return HorizonStatus.EXPIRED
    return HorizonStatus.WITHIN


def validate_idempotency_key(value: str) -> str:
    """Return a stripped idempotency key or raise."""
    if not isinstance(value, str):
        raise ExportBundleError("idempotency_key must be a string")
    key = value.strip()
    if not key or len(key) > MAX_IDEMPOTENCY:
        raise ExportBundleError("idempotency_key must be non-blank and <=200 characters")
    return key


def validate_actor_label(value: str) -> str:
    """Return a stripped actor label or raise."""
    if not isinstance(value, str):
        raise ExportBundleError("actor must be a string")
    actor = value.strip()
    if not actor or len(actor) > MAX_IDEMPOTENCY:
        raise ExportBundleError("actor must be non-blank and <=200 characters")
    return actor


def redaction_policy_payload(
    *,
    prohibited: Sequence[str] | None = None,
    projection: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Return the digest input derived from the frozen projection allow/deny lists."""
    from app.release import evidence_pack as ep

    denied = (
        sorted(prohibited) if prohibited is not None else sorted(ep._PROHIBITED_PROJECTION_FIELDS)
    )
    fields = (
        {kind: sorted(names) for kind, names in sorted(projection.items())}
        if projection is not None
        else {kind: sorted(names) for kind, names in sorted(ep.PROJECTION_FIELDS.items())}
    )
    return {
        "prohibited_fields": denied,
        "projection_fields": fields,
        "version": REDACTION_POLICY_VERSION,
    }


def compute_redaction_policy_digest(
    *,
    prohibited: Sequence[str] | None = None,
    projection: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Return the SHA-256 digest of the enforced redaction policy projection."""
    return digest_bytes(
        canonical_json_bytes(
            redaction_policy_payload(
                prohibited=prohibited,
                projection=projection,
            )
        )
    )


def build_manifest_payload(
    *,
    project_id: uuid.UUID,
    release_candidate_id: uuid.UUID,
    evidence_pack_id: uuid.UUID,
    release_verdict_id: uuid.UUID,
    generated_at: datetime,
    core_content_hash: str,
    immutable_log_reference: str,
    signing_key_id: str,
    redaction_policy_digest: str,
    expires_at: datetime,
    files: Sequence[ManifestedFile],
) -> dict[str, Any]:
    """Return the canonical signed-manifest object for generation and rebinding."""
    if len(files) != MANIFESTED_FILE_COUNT:
        raise ExportBundleError("manifested_file_count_invalid")
    expected = {spec.ordinal: spec for spec in MANIFESTED_FILES}
    ordered: list[dict[str, Any]] = []
    for item in files:
        spec = expected.get(item.ordinal)
        if spec is None or item.file_name != spec.file_name or item.media_type != spec.media_type:
            raise ExportBundleError("manifested_file_spec_invalid")
        if item.byte_count <= 0 or item.byte_count > MAX_BUNDLE_FILE_BYTES:
            raise ExportBundleError("manifested_file_size_invalid")
        ordered.append(item.as_payload())
    ordered.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in ordered] != [1, 2]:
        raise ExportBundleError("manifested_file_ordinals_invalid")
    expiry = format_utc(expires_at)
    return {
        "auditor_access": {
            "expiry": expiry,
            "mode": AUDITOR_ACCESS_MODE,
            "redaction_policy": REDACTION_POLICY_VERSION,
        },
        "core_content_hash": core_content_hash,
        "evidence_pack_id": str(evidence_pack_id),
        "files": ordered,
        "generated_at": format_utc(generated_at),
        "immutable_log_reference": immutable_log_reference,
        "limitations": list(LIMITATIONS),
        "manifest_version": MANIFEST_VERSION,
        "project_id": str(project_id),
        "redaction_policy": {
            "digest": redaction_policy_digest,
            "version": REDACTION_POLICY_VERSION,
        },
        "release_candidate_id": str(release_candidate_id),
        "release_verdict_id": str(release_verdict_id),
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "signing_key_id": signing_key_id,
    }


def parse_manifest_bytes(content: bytes) -> dict[str, Any] | None:
    """Totally parse file-3 bytes. Return the object or ``None``; never raise."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if any(key not in payload for key in _MANIFEST_REQUIRED_KEYS):
        return None
    if payload.get("manifest_version") != MANIFEST_VERSION:
        return None
    if payload.get("schema_version") != CANONICAL_SCHEMA_VERSION:
        return None
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        return None
    for key in (
        "project_id",
        "release_candidate_id",
        "evidence_pack_id",
        "release_verdict_id",
        "generated_at",
        "core_content_hash",
        "immutable_log_reference",
        "signing_key_id",
    ):
        if not isinstance(payload.get(key), str) or not payload[key]:
            return None
    policy = payload.get("redaction_policy")
    if not isinstance(policy, dict):
        return None
    if policy.get("version") != REDACTION_POLICY_VERSION:
        return None
    if not isinstance(policy.get("digest"), str) or not policy["digest"]:
        return None
    access = payload.get("auditor_access")
    if not isinstance(access, dict):
        return None
    if access.get("mode") != AUDITOR_ACCESS_MODE:
        return None
    if access.get("redaction_policy") != REDACTION_POLICY_VERSION:
        return None
    if not isinstance(access.get("expiry"), str) or not access["expiry"]:
        return None
    limitations = payload.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        return None
    files = payload.get("files")
    if not isinstance(files, list) or len(files) != MANIFESTED_FILE_COUNT:
        return None
    seen: set[int] = set()
    for row in files:
        if not isinstance(row, dict):
            return None
        if any(key not in row for key in _FILE_REQUIRED_KEYS):
            return None
        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal not in (1, 2):
            return None
        if ordinal in seen:
            return None
        seen.add(ordinal)
        if not isinstance(row.get("file_name"), str) or not row["file_name"]:
            return None
        if not isinstance(row.get("media_type"), str) or not row["media_type"]:
            return None
        byte_count = row.get("byte_count")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count <= 0:
            return None
        if not isinstance(row.get("sha256"), str) or not row["sha256"]:
            return None
    if seen != {1, 2}:
        return None
    return payload


def manifested_hashes(payload: Mapping[str, Any]) -> dict[int, str]:
    """Return ordinal → sha256 for a parsed manifest's ``files[]``."""
    return {int(row["ordinal"]): str(row["sha256"]) for row in payload["files"]}
