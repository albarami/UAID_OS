"""Slice-60 export-bundle reads and compute-on-read verification."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_pack_export import (
    EvidencePackExportFile,
    EvidencePackExportRecord,
    EvidencePackManifestSignature,
)
from app.release.evidence_pack import canonical_json_bytes, digest_bytes
from app.release.export_bundle import (
    FILE_COUNT,
    MANIFESTED_FILES,
    BundleVerification,
    ExportBundleError,
    ExportBundleSnapshot,
    HorizonStatus,
    IntegrityResult,
    ManifestedFile,
    build_manifest_payload,
    compute_redaction_policy_digest,
    horizon_status_for,
    manifested_hashes,
    parse_manifest_bytes,
)
from app.release.export_signing import trusted_public_key, verify_manifest_signature
from app.repositories.export_bundles import snapshot_of
from app.tenancy import TenantContext, TenantScopedRepository


class ExportBundleReadRepository(TenantScopedRepository):
    """Latest-wins reads and total fail-closed verification over persisted bytes."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, EvidencePackExportRecord)

    async def latest_bundle_for_pack(self, pack_id: uuid.UUID) -> ExportBundleSnapshot | None:
        """Return the newest bundle for the pack, or ``None``."""
        row = await self._latest_row(pack_id)
        return snapshot_of(row) if row is not None else None

    async def history_for_pack(self, pack_id: uuid.UUID) -> list[ExportBundleSnapshot]:
        """Return newest-first bundle history for the pack."""
        rows = (
            (
                await self.session.execute(
                    select(EvidencePackExportRecord)
                    .where(
                        EvidencePackExportRecord.tenant_id == self.context.tenant_id,
                        EvidencePackExportRecord.evidence_pack_id == pack_id,
                    )
                    .order_by(
                        EvidencePackExportRecord.created_at.desc(),
                        EvidencePackExportRecord.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [snapshot_of(row) for row in rows]

    async def bundle_files(self, export_record_id: uuid.UUID) -> list[EvidencePackExportFile]:
        """Return file rows for the record, ordinal-ascending."""
        return list(
            (
                await self.session.execute(
                    select(EvidencePackExportFile)
                    .where(
                        EvidencePackExportFile.tenant_id == self.context.tenant_id,
                        EvidencePackExportFile.export_record_id == export_record_id,
                    )
                    .order_by(EvidencePackExportFile.ordinal)
                )
            )
            .scalars()
            .all()
        )

    async def bundle_signature(
        self, export_record_id: uuid.UUID
    ) -> EvidencePackManifestSignature | None:
        """Return the unique signature row, or ``None``."""
        return (
            await self.session.execute(
                select(EvidencePackManifestSignature).where(
                    EvidencePackManifestSignature.tenant_id == self.context.tenant_id,
                    EvidencePackManifestSignature.export_record_id == export_record_id,
                )
            )
        ).scalar_one_or_none()

    async def verify(self, export_record_id: uuid.UUID) -> BundleVerification:
        """Return a closed ``(integrity, horizon)`` pair for any persisted row set."""
        record = await self.get(export_record_id)
        if record is None:
            return BundleVerification(IntegrityResult.FILE_SET_INCOMPLETE, HorizonStatus.WITHIN)
        horizon = horizon_status_for(record.expires_at)
        files = await self.bundle_files(record.id)
        signature = await self.bundle_signature(record.id)
        by_ord = {row.ordinal: row for row in files}
        if len(files) != FILE_COUNT or signature is None or set(by_ord) != {1, 2, 3, 4}:
            return BundleVerification(IntegrityResult.FILE_SET_INCOMPLETE, horizon)
        for row in files:
            if digest_bytes(bytes(row.content)) != row.content_sha256:
                return BundleVerification(IntegrityResult.STORED_BYTES_HASH_MISMATCH, horizon)
        manifest_bytes = bytes(by_ord[3].content)
        if digest_bytes(manifest_bytes) != record.manifest_digest:
            return BundleVerification(IntegrityResult.MANIFEST_DIGEST_MISMATCH, horizon)
        parsed = parse_manifest_bytes(manifest_bytes)
        if parsed is None:
            return BundleVerification(IntegrityResult.MANIFEST_INVALID, horizon)
        expected_hashes = manifested_hashes(parsed)
        for spec in MANIFESTED_FILES:
            row = by_ord[spec.ordinal]
            if expected_hashes.get(spec.ordinal) != digest_bytes(bytes(row.content)):
                return BundleVerification(IntegrityResult.PAYLOAD_HASH_MISMATCH, horizon)
        if trusted_public_key(record.signing_key_id) is None:
            return BundleVerification(IntegrityResult.UNTRUSTED_SIGNING_KEY, horizon)
        if not verify_manifest_signature(
            manifest_bytes, bytes(by_ord[4].content), record.signing_key_id
        ):
            return BundleVerification(IntegrityResult.SIGNATURE_INVALID, horizon)
        if not self._rebinding_matches(record, by_ord, manifest_bytes):
            return BundleVerification(IntegrityResult.MANIFEST_BINDING_MISMATCH, horizon)
        live_digest = compute_redaction_policy_digest()
        parsed_digest = parsed["redaction_policy"]["digest"]
        if live_digest != record.redaction_policy_digest or parsed_digest != live_digest:
            return BundleVerification(IntegrityResult.REDACTION_POLICY_DIGEST_MISMATCH, horizon)
        return BundleVerification(IntegrityResult.VERIFIED, horizon)

    def _rebinding_matches(
        self,
        record: EvidencePackExportRecord,
        by_ord: dict[int, EvidencePackExportFile],
        manifest_bytes: bytes,
    ) -> bool:
        files = tuple(
            ManifestedFile(
                ordinal=by_ord[spec.ordinal].ordinal,
                file_name=by_ord[spec.ordinal].file_name,
                media_type=by_ord[spec.ordinal].media_type,
                byte_count=by_ord[spec.ordinal].byte_count,
                sha256=by_ord[spec.ordinal].content_sha256,
            )
            for spec in MANIFESTED_FILES
        )
        try:
            expected = build_manifest_payload(
                project_id=record.project_id,
                release_candidate_id=record.release_candidate_id,
                evidence_pack_id=record.evidence_pack_id,
                release_verdict_id=record.release_verdict_id,
                generated_at=record.as_of,
                core_content_hash=record.core_content_hash,
                immutable_log_reference=record.immutable_log_reference,
                signing_key_id=record.signing_key_id,
                redaction_policy_digest=record.redaction_policy_digest,
                expires_at=record.expires_at,
                files=files,
            )
        except ExportBundleError:
            return False
        return canonical_json_bytes(expected) == manifest_bytes

    async def _latest_row(self, pack_id: uuid.UUID) -> EvidencePackExportRecord | None:
        return (
            await self.session.execute(
                select(EvidencePackExportRecord)
                .where(
                    EvidencePackExportRecord.tenant_id == self.context.tenant_id,
                    EvidencePackExportRecord.evidence_pack_id == pack_id,
                )
                .order_by(
                    EvidencePackExportRecord.created_at.desc(),
                    EvidencePackExportRecord.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
