"""Internal-only Slice-49 evidence-pack rendering surfaces."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.release.evidence_pack import (
    MAX_JSON_BYTES,
    MAX_MARKDOWN_BYTES,
    CoreAssembly,
    EvidencePackContractError,
    canonical_json_bytes,
    digest_bytes,
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
