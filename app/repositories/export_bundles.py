"""Slice-60 export-bundle persistence. Generate path only."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.audit_chain_verification import AuditChainVerification
from app.models.evidence_pack import EvidencePack
from app.models.evidence_pack_export import (
    EvidencePackExportFile,
    EvidencePackExportRecord,
    EvidencePackManifestSignature,
)
from app.release.evidence_export import CanonicalExportUnavailable, ExportArtifact
from app.release.evidence_pack import canonical_json_bytes, digest_bytes
from app.release.export_bundle import (
    AUDITOR_ACCESS_MODE,
    BUNDLE_CONTRACT_VERSION,
    BUNDLE_FILES,
    FILE_COUNT,
    MAX_BUNDLE_FILE_BYTES,
    REDACTION_POLICY_VERSION,
    SIGNATURE_ALGORITHM,
    ExportBundleError,
    ExportBundleSnapshot,
    ManifestedFile,
    build_manifest_payload,
    compute_redaction_policy_digest,
    validate_actor_label,
    validate_idempotency_key,
)
from app.release.export_signing import encode_signature_b64, load_signing_seed, sign_manifest_bytes
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.tenancy import TenantContext, TenantScopedRepository


class ExportBundleRepository(TenantScopedRepository):
    """Persist one signed offline auditor bundle for an exact pack and verdict."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, EvidencePackExportRecord)

    async def get_by_idempotency(
        self, evidence_pack_id: uuid.UUID, idempotency_key: str
    ) -> EvidencePackExportRecord | None:
        """Return the existing row for ``(pack, idempotency_key)``, if any."""
        stmt = select(EvidencePackExportRecord).where(
            EvidencePackExportRecord.tenant_id == self.context.tenant_id,
            EvidencePackExportRecord.evidence_pack_id == evidence_pack_id,
            EvidencePackExportRecord.idempotency_key == idempotency_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def generate(
        self,
        pack_id: uuid.UUID,
        *,
        actor: str,
        idempotency_key: str,
    ) -> ExportBundleSnapshot | None:
        """Insert one bundle. Returns ``None`` on idempotent conflict-do-nothing."""
        actor_label = validate_actor_label(actor)
        key = validate_idempotency_key(idempotency_key)
        existing = await self.get_by_idempotency(pack_id, key)
        if existing is not None:
            return snapshot_of(existing)
        load_signing_seed()
        packs = EvidencePackRepository(self.session, self.context)
        pack = await packs.get(pack_id)
        if pack is None:
            raise ExportBundleError("evidence_pack_not_found")
        try:
            canonical = await packs.export_canonical_json(pack_id, actor=actor_label)
            markdown = await packs.export_markdown(pack_id, actor=actor_label)
        except CanonicalExportUnavailable as exc:
            raise ExportBundleError(exc.code) from exc
        except EvidencePackRepositoryError as exc:
            raise ExportBundleError(str(exc)) from exc
        payload = json.loads(canonical.content)
        try:
            verdict_id = uuid.UUID(payload["verdict_attestation"]["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportBundleError("release_verdict_id_unreadable") from exc
        checkpoint = await self.session.get(AuditChainVerification, pack.audit_checkpoint_id)
        if (
            checkpoint is None
            or not checkpoint.verification_ok
            or not checkpoint.verified_through_entry_hash
        ):
            raise ExportBundleError("audit_checkpoint_unusable")
        clock = (
            await self.session.execute(
                text(
                    "SELECT transaction_timestamp() AS ts, "
                    "transaction_timestamp() + INTERVAL '720 hours' AS exp"
                )
            )
        ).one()
        as_of = clock.ts
        expires_at = clock.exp
        if (
            as_of is None
            or expires_at is None
            or getattr(as_of, "tzinfo", None) is None
            or getattr(expires_at, "tzinfo", None) is None
        ):
            raise ExportBundleError("transaction_timestamp required")
        as_of = as_of.astimezone(timezone.utc)
        expires_at = expires_at.astimezone(timezone.utc)
        redaction_digest = compute_redaction_policy_digest()
        _seed, signing_key_id, _public = load_signing_seed()
        manifested = (
            _as_manifested(BUNDLE_FILES[0], canonical),
            _as_manifested(BUNDLE_FILES[1], markdown),
        )
        manifest_object = build_manifest_payload(
            project_id=pack.project_id,
            release_candidate_id=pack.release_candidate_id,
            evidence_pack_id=pack.id,
            release_verdict_id=verdict_id,
            generated_at=as_of,
            core_content_hash=pack.core_content_hash,
            immutable_log_reference=checkpoint.verified_through_entry_hash,
            signing_key_id=signing_key_id,
            redaction_policy_digest=redaction_digest,
            expires_at=expires_at,
            files=manifested,
        )
        manifest_bytes = canonical_json_bytes(manifest_object)
        signature, signing_key_id = sign_manifest_bytes(manifest_bytes)
        artifacts = (
            canonical,
            markdown,
            ExportArtifact(BUNDLE_FILES[2].file_name, BUNDLE_FILES[2].media_type, manifest_bytes),
            ExportArtifact(BUNDLE_FILES[3].file_name, BUNDLE_FILES[3].media_type, signature),
        )
        for artifact in artifacts:
            if not artifact.content or len(artifact.content) > MAX_BUNDLE_FILE_BYTES:
                raise ExportBundleError("bundle_file_size_invalid")
        total_bytes = sum(len(item.content) for item in artifacts)
        manifest_digest = digest_bytes(manifest_bytes)
        await self.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        inserted = await self._try_insert_record(
            pack=pack,
            verdict_id=verdict_id,
            idempotency_key=key,
            manifest_digest=manifest_digest,
            redaction_digest=redaction_digest,
            log_ref=checkpoint.verified_through_entry_hash,
            signing_key_id=signing_key_id,
            as_of=as_of,
            expires_at=expires_at,
            total_bytes=total_bytes,
        )
        if inserted is None:
            return None
        record = await self.get(inserted)
        if record is None:
            return None
        for spec, artifact in zip(BUNDLE_FILES, artifacts, strict=True):
            await self.add(
                EvidencePackExportFile(
                    project_id=pack.project_id,
                    export_record_id=record.id,
                    ordinal=spec.ordinal,
                    file_name=spec.file_name,
                    media_type=spec.media_type,
                    content=artifact.content,
                    byte_count=len(artifact.content),
                    content_sha256=digest_bytes(artifact.content),
                )
            )
        await self.add(
            EvidencePackManifestSignature(
                project_id=pack.project_id,
                export_record_id=record.id,
                signature_algorithm=SIGNATURE_ALGORITHM,
                signing_key_id=signing_key_id,
                signature_b64=encode_signature_b64(signature),
                signed_bytes_digest=manifest_digest,
            )
        )
        await self.session.flush()
        await audit_record(
            self.session,
            action="evidence_pack.bundle_generated",
            actor=actor_label,
            target=str(record.id),
            payload={
                "project_id": str(pack.project_id),
                "evidence_pack_id": str(pack.id),
                "release_verdict_id": str(verdict_id),
                "file_count": FILE_COUNT,
                "total_byte_count": total_bytes,
                "manifest_digest": manifest_digest,
                "signing_key_id": signing_key_id,
                "auditor_access_mode": AUDITOR_ACCESS_MODE,
                "expires_at": expires_at.isoformat(),
            },
        )
        return snapshot_of(record)

    async def _try_insert_record(
        self,
        *,
        pack: EvidencePack,
        verdict_id: uuid.UUID,
        idempotency_key: str,
        manifest_digest: str,
        redaction_digest: str,
        log_ref: str,
        signing_key_id: str,
        as_of: datetime,
        expires_at: datetime,
        total_bytes: int,
    ) -> uuid.UUID | None:
        stmt = (
            pg_insert(EvidencePackExportRecord)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=pack.project_id,
                evidence_pack_id=pack.id,
                release_candidate_id=pack.release_candidate_id,
                release_verdict_id=verdict_id,
                audit_checkpoint_id=pack.audit_checkpoint_id,
                idempotency_key=idempotency_key,
                bundle_contract_version=BUNDLE_CONTRACT_VERSION,
                manifest_digest=manifest_digest,
                redaction_policy_version=REDACTION_POLICY_VERSION,
                redaction_policy_digest=redaction_digest,
                core_content_hash=pack.core_content_hash,
                immutable_log_reference=log_ref,
                signing_key_id=signing_key_id,
                auditor_access_mode=AUDITOR_ACCESS_MODE,
                as_of=as_of,
                expires_at=expires_at,
                file_count=FILE_COUNT,
                total_byte_count=total_bytes,
            )
            .on_conflict_do_nothing(constraint="uq_epr_idempotency")
            .returning(EvidencePackExportRecord.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


def _as_manifested(spec, artifact: ExportArtifact) -> ManifestedFile:
    return ManifestedFile(
        ordinal=spec.ordinal,
        file_name=spec.file_name,
        media_type=spec.media_type,
        byte_count=len(artifact.content),
        sha256=digest_bytes(artifact.content),
    )


def snapshot_of(row: EvidencePackExportRecord) -> ExportBundleSnapshot:
    return ExportBundleSnapshot(
        id=row.id,
        project_id=row.project_id,
        evidence_pack_id=row.evidence_pack_id,
        release_candidate_id=row.release_candidate_id,
        release_verdict_id=row.release_verdict_id,
        audit_checkpoint_id=row.audit_checkpoint_id,
        idempotency_key=row.idempotency_key,
        bundle_contract_version=row.bundle_contract_version,
        manifest_digest=row.manifest_digest,
        redaction_policy_digest=row.redaction_policy_digest,
        core_content_hash=row.core_content_hash,
        immutable_log_reference=row.immutable_log_reference,
        signing_key_id=row.signing_key_id,
        auditor_access_mode=row.auditor_access_mode,
        as_of=row.as_of,
        expires_at=row.expires_at,
        file_count=row.file_count,
        total_byte_count=int(row.total_byte_count),
    )
