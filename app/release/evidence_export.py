"""Internal-only Slice-49 evidence-pack rendering surfaces."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.release.evidence_pack import (
    MAX_JSON_BYTES,
    MAX_MARKDOWN_BYTES,
    CoreAssembly,
    EvidencePackContractError,
    canonical_json_bytes,
    digest_bytes,
    validate_canonical_payload,
    validate_semantic_payload,
)


class CanonicalExportUnavailable(EvidencePackContractError):
    """A real future attestation required for canonical export is absent."""


@dataclass(frozen=True)
class ReleaseVerdictAttestation:
    """Reserved Slice-50 input interface; Slice 49 does not persist or create it."""

    id: uuid.UUID
    evidence_pack_id: uuid.UUID
    verdict: str
    attestation_provenance: str
    created_at: datetime


@dataclass(frozen=True)
class _DBBoundReleaseVerdictAttestation:
    """Repository-only projection of an exact FK-loaded immutable Slice-50 row."""

    id: uuid.UUID
    evidence_pack_id: uuid.UUID
    spec_verdict: str
    canonical_verdict: str
    reason_code: str
    decision_scope: str
    attestation_provenance: str
    verdict_contract_version: str
    projection_contract_version: str
    verdict_contract_hash: str
    input_digest: str
    core_content_hash: str
    created_at: datetime


@dataclass(frozen=True)
class SignatureAttestation:
    """Reserved Slice-60 input interface; deliberately unsupported in Slice 49."""

    id: uuid.UUID
    evidence_pack_id: uuid.UUID
    signer_id: str
    signature_bytes: bytes
    created_at: datetime


@dataclass(frozen=True)
class ExportArtifact:
    file_name: str
    media_type: str
    content: bytes


def build_core_preview(core: CoreAssembly) -> ExportArtifact:
    validate_semantic_payload(core.payload, canonical_export=False)
    payload = dict(core.payload)
    payload["export_kind"] = "not_canonical_export"
    raw = canonical_json_bytes(payload)
    if len(raw) > MAX_JSON_BYTES:
        raise EvidencePackContractError("json_export_size_cap_exceeded")
    return ExportArtifact("evidence_pack_core.preview.json", "application/json", raw)


def build_canonical_export(
    core: CoreAssembly,
    *,
    verdict_attestation: ReleaseVerdictAttestation | None,
) -> ExportArtifact:
    if verdict_attestation is None:
        raise CanonicalExportUnavailable("real_verdict_attestation_required")
    # The type above reserves Slice 50's input shape; Slice 49 has no DB table
    # from which to reload and prove such an attestation.  Therefore even an
    # object carrying the right-looking strings is caller-shaped and refused.
    # Slice 50 must replace this refusal with a repository-loaded FK-bound row.
    raise CanonicalExportUnavailable("db_bound_slice50_verdict_store_not_implemented")


def _build_db_bound_canonical_export(
    core: CoreAssembly,
    *,
    verdict_attestation: _DBBoundReleaseVerdictAttestation,
) -> ExportArtifact:
    """Finalize exact core bytes with a repository-loaded verdict attestation."""

    validate_semantic_payload(core.payload, canonical_export=False)
    if verdict_attestation.core_content_hash != core.content_hash:
        raise CanonicalExportUnavailable("verdict_core_binding_mismatch")
    payload = json.loads(core.canonical_text)
    payload["verdict"] = verdict_attestation.canonical_verdict
    payload["verdict_attestation"] = {
        "id": str(verdict_attestation.id),
        "evidence_pack_id": str(verdict_attestation.evidence_pack_id),
        "spec_verdict": verdict_attestation.spec_verdict,
        "canonical_verdict": verdict_attestation.canonical_verdict,
        "reason_code": verdict_attestation.reason_code,
        "decision_scope": verdict_attestation.decision_scope,
        "attestation_provenance": verdict_attestation.attestation_provenance,
        "verdict_contract_version": verdict_attestation.verdict_contract_version,
        "projection_contract_version": verdict_attestation.projection_contract_version,
        "verdict_contract_hash": verdict_attestation.verdict_contract_hash,
        "input_digest": verdict_attestation.input_digest,
        "core_content_hash": verdict_attestation.core_content_hash,
        "created_at": verdict_attestation.created_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    payload["signatures"] = []
    payload["signature_status"] = "unsigned_signer_tier_not_implemented"
    payload["assurance_limitations"] = [
        "assembled_evidence_does_not_prove_release_readiness",
        "candidate_has_no_direct_commit_foreign_key",
        "issue_bindings_do_not_prove_issue_completeness",
        "release_verdict_bounded_known_issue_disposition_not_go_live_authorization",
        "signer_tier_deferred_to_slice_60",
    ]
    validate_canonical_payload(payload)
    raw = canonical_json_bytes(payload)
    if len(raw) > MAX_JSON_BYTES:
        raise EvidencePackContractError("json_export_size_cap_exceeded")
    return ExportArtifact("evidence_pack.json", "application/json", raw)


def build_markdown_export(core: CoreAssembly) -> ExportArtifact:
    validate_semantic_payload(core.payload, canonical_export=False)
    binding = core.payload["repo_commit_binding"]
    lines = [
        "# Evidence Pack Core Preview",
        "",
        "- Export kind: `not_canonical_export`",
        f"- Project ID: `{core.payload['project_id']}`",
        f"- Release candidate ID: `{core.payload['release_id']}`",
        f"- Assembly status: `{core.assembly_status}`",
        f"- Repo/commit binding state: `{binding['state']}`",
        f"- Source-set digest: `{core.source_set_digest}`",
        f"- Core content hash: `{core.content_hash}`",
        "- Verdict: deferred to Slice 50 (not present)",
        "- Signature: signer tier deferred to Slice 60 (not present)",
        "",
        "## Source inventory",
        "",
    ]
    for row in core.payload["source_inventory"]:
        lines.append(
            f"- `{row['section_code']}`: `{row['presence_code']}` ({row['item_count']} items)"
        )
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    if len(raw) > MAX_MARKDOWN_BYTES:
        raise EvidencePackContractError("markdown_export_size_cap_exceeded")
    return ExportArtifact("evidence_pack_core.preview.md", "text/markdown; charset=utf-8", raw)


def build_unsigned_manifest(artifact: ExportArtifact) -> ExportArtifact:
    payload = {
        "manifest_version": "slice49.unsigned_manifest.v1",
        "signature_status": "unsigned_signer_tier_not_implemented",
        "files": [
            {
                "file_name": artifact.file_name,
                "media_type": artifact.media_type,
                "byte_count": len(artifact.content),
                "sha256": digest_bytes(artifact.content),
            }
        ],
    }
    return ExportArtifact(
        "evidence_pack.integrity.json",
        "application/json",
        canonical_json_bytes(payload),
    )
