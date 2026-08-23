"""Slice 60 export-bundle DB proofs: generate, verify, tamper, concurrency."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.release.evidence_pack import digest_bytes
from app.release.export_bundle import (
    APP_KEY_CUSTODY_SIGNED,
    AUDIT_ATTEMPT_NON_EVIDENCE,
    ExportBundleError,
    HorizonStatus,
    IntegrityResult,
    SIGNING_KEY_NOT_CONFIGURED,
)
from app.release.export_bundle_service import generate_export_bundle, verify_export_bundle
from app.release.export_signing import encode_seed_b64, generate_seed
from app.repositories.export_bundle_reads import ExportBundleReadRepository
from app.tenancy import TenantContext, tenant_scope
from tests.export_bundle_support import (
    FINDINGS_GUARD_MD5,
    committed_exportable,
    configure_signing,
    unique_key,
)


@pytest.mark.db
async def test_d1_full_bundle_persists_and_verifies(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d1")
    )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.VERIFIED
    assert result.horizon_status is HorizonStatus.WITHIN
    assert result.signature_status == APP_KEY_CUSTODY_SIGNED
    async with tenant_scope(ctx) as session:
        repo = ExportBundleReadRepository(session, ctx)
        files = await repo.bundle_files(snap.id)
        signature = await repo.bundle_signature(snap.id)
    assert [row.ordinal for row in files] == [1, 2, 3, 4]
    body = json.loads(files[0].content)
    assert body["signatures"] == []
    assert body["signature_status"] == "unsigned_signer_tier_not_implemented"
    parsed = json.loads(files[2].content)
    assert len(parsed["files"]) == 2
    assert len(parsed["limitations"]) == 10
    assert len(files[3].content) == 64
    assert signature is not None
    assert snap.file_count == 4
    assert snap.auditor_access_mode == "offline_bundle"


@pytest.mark.db
async def test_d2_idempotency_returns_same_record(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    key = unique_key("d2")
    first = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=key
    )
    second = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=key
    )
    assert first.id == second.id
    async with tenant_scope(ctx) as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM evidence_pack_export_records WHERE evidence_pack_id=:p"),
                {"p": seeded["pack_id"]},
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.db
async def test_d3_pack_without_verdict_cannot_bundle(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine, with_verdict=False)
    with pytest.raises(ExportBundleError, match="real_verdict_attestation_required"):
        await generate_export_bundle(
            TenantContext(seeded["tenant"]),
            seeded["pack_id"],
            actor="slice60-test",
            idempotency_key=unique_key("d3"),
        )


@pytest.mark.db
async def test_d4_expired_horizon_still_verified(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d4")
    )
    monkeypatch.setattr(
        "app.release.export_bundle.utc_now",
        lambda: snap.expires_at + timedelta(seconds=1),
    )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.VERIFIED
    assert result.horizon_status is HorizonStatus.EXPIRED
    assert result.signature_status == APP_KEY_CUSTODY_SIGNED


@pytest.mark.db
async def test_u4_unconfigured_writes_nothing(admin_engine, monkeypatch):
    monkeypatch.setattr("app.config.settings.evidence_signing_private_key_b64", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_key_id", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_trusted_keys", "")
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_CONFIGURED):
        await generate_export_bundle(
            TenantContext(seeded["tenant"]),
            seeded["pack_id"],
            actor="slice60-test",
            idempotency_key=unique_key("u4"),
        )
    async with admin_engine.connect() as conn:
        remaining = (
            await conn.execute(
                text("SELECT count(*) FROM evidence_pack_export_records WHERE evidence_pack_id=:p"),
                {"p": seeded["pack_id"]},
            )
        ).scalar_one()
    assert remaining == 0


@pytest.mark.db
async def test_d9_garbage_signature_fails_verification(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d9")
    )
    garbage = os.urandom(64)
    async with admin_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE evidence_pack_export_files SET content=:c, byte_count=64, "
                "content_sha256=:h WHERE export_record_id=:e AND ordinal=4"
            ),
            {"c": garbage, "h": digest_bytes(garbage), "e": snap.id},
        )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.SIGNATURE_INVALID


@pytest.mark.db
async def test_d9b_attacker_key_is_untrusted(admin_engine, monkeypatch):
    attacker_seed, _pub = generate_seed()
    configure_signing(monkeypatch, seed=attacker_seed, key_id="attacker-key")
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d9b")
    )
    operator_seed, operator_pub = generate_seed()
    configure_signing(
        monkeypatch,
        seed=operator_seed,
        key_id="operator-key",
        trusted={"operator-key": operator_pub},
    )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.UNTRUSTED_SIGNING_KEY
    assert result.signature_status is None


@pytest.mark.db
async def test_d11_private_seed_never_persisted(admin_engine, monkeypatch):
    seed, _key_id, _public = configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d11")
    )
    await verify_export_bundle(ctx, snap.id)
    marker = encode_seed_b64(seed)
    async with admin_engine.connect() as conn:
        payloads = (
            (
                await conn.execute(
                    text(
                        "SELECT payload::text FROM audit_logs "
                        "WHERE action LIKE 'evidence_pack.bundle%' AND tenant_id=:t"
                    ),
                    {"t": seeded["tenant"]},
                )
            )
            .scalars()
            .all()
        )
        assert all(marker not in (row or "") for row in payloads)
        files = (
            (
                await conn.execute(
                    text(
                        "SELECT content FROM evidence_pack_export_files WHERE export_record_id=:e"
                    ),
                    {"e": snap.id},
                )
            )
            .scalars()
            .all()
        )
        needle = marker.encode("ascii")
        assert all(needle not in bytes(content) for content in files)
        assert all(seed not in bytes(content) for content in files)


@pytest.mark.db
async def test_d15_cross_tenant_reads_nothing(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d15")
    )
    other = TenantContext(seeded["tenant2"])
    result = await verify_export_bundle(other, snap.id)
    assert result.integrity_result is IntegrityResult.FILE_SET_INCOMPLETE
    async with tenant_scope(other) as session:
        repo = ExportBundleReadRepository(session, other)
        latest = await repo.latest_bundle_for_pack(seeded["pack_id"])
        history = await repo.history_for_pack(seeded["pack_id"])
    assert latest is None
    assert history == []


@pytest.mark.db
async def test_d16_mutated_projection_mismatches_redaction_digest(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d16")
    )
    import app.release.evidence_pack as ep

    mutated = {
        kind: set(names) | {"slice60_probe_field"} for kind, names in ep.PROJECTION_FIELDS.items()
    }
    monkeypatch.setattr(ep, "PROJECTION_FIELDS", mutated)
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.REDACTION_POLICY_DIGEST_MISMATCH


@pytest.mark.db
async def test_d20_payload_hash_mismatch(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d20")
    )
    tampered = b'{"tampered":true}'
    async with admin_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE evidence_pack_export_files SET content=:c, byte_count=:n, "
                "content_sha256=:h WHERE export_record_id=:e AND ordinal=1"
            ),
            {"c": tampered, "n": len(tampered), "h": digest_bytes(tampered), "e": snap.id},
        )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.PAYLOAD_HASH_MISMATCH


@pytest.mark.db
async def test_d21_mutated_manifest_is_signature_invalid(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d21")
    )
    async with tenant_scope(ctx) as session:
        files = await ExportBundleReadRepository(session, ctx).bundle_files(snap.id)
        original = bytes(files[2].content)
    payload = json.loads(original)
    payload["limitations"] = list(payload["limitations"])
    payload["limitations"][0] = "mutated_limitation"
    mutated = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    digest = digest_bytes(mutated)
    async with admin_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE evidence_pack_export_files SET content=:c, byte_count=:n, "
                "content_sha256=:h WHERE export_record_id=:e AND ordinal=3"
            ),
            {"c": mutated, "n": len(mutated), "h": digest, "e": snap.id},
        )
        await conn.execute(
            text("UPDATE evidence_pack_export_records SET manifest_digest=:h WHERE id=:e"),
            {"h": digest, "e": snap.id},
        )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.SIGNATURE_INVALID


@pytest.mark.db
async def test_d22_mutated_signature_file_is_invalid(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d22")
    )
    mutated = os.urandom(64)
    async with admin_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(
            text(
                "UPDATE evidence_pack_export_files SET content=:c, byte_count=64, "
                "content_sha256=:h WHERE export_record_id=:e AND ordinal=4"
            ),
            {"c": mutated, "h": digest_bytes(mutated), "e": snap.id},
        )
    result = await verify_export_bundle(ctx, snap.id)
    assert result.integrity_result is IntegrityResult.SIGNATURE_INVALID


@pytest.mark.db
async def test_d23_concurrent_same_idempotency_one_record(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    key = unique_key("d23")
    first, second = await asyncio.gather(
        generate_export_bundle(ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=key),
        generate_export_bundle(ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=key),
    )
    assert first.id == second.id
    async with tenant_scope(ctx) as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM evidence_pack_export_records WHERE evidence_pack_id=:p"),
                {"p": seeded["pack_id"]},
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.db
async def test_d24_real_a5_and_readiness_are_bit_stable(admin_engine, monkeypatch):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository

    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    project = seeded["project"]
    async with tenant_scope(ctx) as session:
        before_a5 = (await ProductionAutonomyRepository(session, ctx).evaluate(project)).to_dict()
        before_ready = (await ReadinessRepository(session, ctx).evaluate(project)).to_dict()
    await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d24")
    )
    async with tenant_scope(ctx) as session:
        after_a5 = (await ProductionAutonomyRepository(session, ctx).evaluate(project)).to_dict()
        after_ready = (await ReadinessRepository(session, ctx).evaluate(project)).to_dict()
    assert before_a5 == after_a5
    assert before_ready == after_ready
    assert after_a5["ruleset_version"] == "slice54.v1"
    assert after_a5["can_go_live_autonomously"] is False
    assert after_ready["ruleset_version"] == "slice20.v1"
    assert after_ready["can_go_live_autonomously"] is False
    async with admin_engine.connect() as conn:
        guard = (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one()
    assert guard == FINDINGS_GUARD_MD5


@pytest.mark.db
async def test_attempt_audit_is_not_validity_evidence(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("audit")
    )
    await verify_export_bundle(ctx, snap.id)
    async with admin_engine.connect() as conn:
        payload = (
            await conn.execute(
                text(
                    "SELECT payload FROM audit_logs "
                    "WHERE action='evidence_pack.bundle_verification_attempted' "
                    "AND target=:t ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": str(snap.id)},
            )
        ).scalar_one()
    assert payload[AUDIT_ATTEMPT_NON_EVIDENCE] is True
    assert payload["result_code"] == "verified"
    assert "bundle_verified" not in json.dumps(payload)
