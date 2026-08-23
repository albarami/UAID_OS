"""Slice 60 direct-SQL guard, cardinality, base64, and totality proofs."""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.export_bundle import HorizonStatus, IntegrityResult
from app.release.export_bundle_service import generate_export_bundle, verify_export_bundle
from app.release.export_signing import encode_signature_b64
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.export_bundle_reads import ExportBundleReadRepository
from app.tenancy import TenantContext, tenant_scope
from tests.export_bundle_support import (
    EXPORT_TABLES,
    FINDINGS_GUARD_MD5,
    SHA_A,
    committed_exportable,
    configure_signing,
    insert_raw_bundle,
    insert_raw_bundle_as_runtime,
    persist_exportable_pack,
    seed_project,
    unique_key,
)


async def _seeded(db_session) -> dict:
    ctx = await seed_project(db_session)
    packed = await persist_exportable_pack(db_session, ctx)
    return {
        **ctx,
        "pack_id": packed["pack"].id,
        "verdict_id": packed["verdict"].id,
        "checkpoint_id": packed["checkpoint"].id,
        "core_hash": packed["pack"].core_content_hash,
        "log_ref": packed["checkpoint"].verified_through_entry_hash,
        "candidate_id": packed["pack"].release_candidate_id,
    }


@pytest.mark.db
async def test_d5_backdated_as_of_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine, seeded, as_of_sql="transaction_timestamp() - INTERVAL '1 day'"
        )


@pytest.mark.db
async def test_d6_chosen_expires_at_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine,
            seeded,
            expires_at_sql="transaction_timestamp() + INTERVAL '1 hour'",
        )


@pytest.mark.db
async def test_d7_scoped_link_mode_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, auditor_access_mode="scoped_link")


@pytest.mark.db
async def test_d8_wrong_core_hash_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, core_content_hash=SHA_A)


@pytest.mark.db
async def test_d8b_wrong_candidate_or_checkpoint_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine, seeded, release_candidate_id=seeded["candidate_b"]
        )
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant',:t,true)"),
                {"t": str(seeded["tenant"])},
            )
            other = await EvidencePackRepository(
                session, TenantContext(seeded["tenant"])
            ).record_audit_checkpoint()
            other_id = other.id
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, audit_checkpoint_id=other_id)


@pytest.mark.db
async def test_d8c_wrong_log_reference_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, immutable_log_reference="ab" * 32)


@pytest.mark.db
async def test_d8d_verdict_of_another_pack_refused(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant',:t,true)"),
                {"t": str(seeded["tenant"])},
            )
            other = await persist_exportable_pack(
                session,
                seeded,
                candidate_id=seeded["candidate_b"],
                frozen_at=seeded["frozen_at_b"],
            )
            other_verdict = other["verdict"].id
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, release_verdict_id=other_verdict)


@pytest.mark.db
async def test_d10_signed_digest_must_match_parent(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, signed_bytes_digest=SHA_A)


@pytest.mark.db
async def test_d12_file_count_tampering_rejected(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, files={1: b"a", 2: b"b", 3: b"c"})
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine,
            seeded,
            files={1: b"a", 2: b"b", 3: b"c", 4: os.urandom(64), 5: b"nope"},
        )


@pytest.mark.db
async def test_d12b_total_byte_count_must_match_sum(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, total_byte_count=1)


@pytest.mark.db
async def test_d13_wrong_ordinal_file_name_rejected(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine,
            seeded,
            file_overrides={1: {"file_name": "evidence_pack.manifest.json"}},
        )


@pytest.mark.db
async def test_d13b_stored_hash_must_match_content(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(
            rls_engine, seeded, file_overrides={1: {"content_sha256": SHA_A}}
        )


@pytest.mark.db
async def test_d14_append_only_rls_grants_and_no_forbidden_columns(db_session, admin_engine):
    seeded = await _seeded(db_session)
    await insert_raw_bundle(db_session, seeded)
    await db_session.flush()
    for table in EXPORT_TABLES:
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"UPDATE {table} SET created_at = created_at WHERE true")
                )
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(f"DELETE FROM {table} WHERE true"))
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(f"TRUNCATE {table} CASCADE"))
    async with admin_engine.connect() as conn:
        for table in EXPORT_TABLES:
            row = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == (True, True)
            grants = {
                item[0]
                for item in (
                    await conn.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            assert grants == {"SELECT", "INSERT"}
            cols = {
                item[0]
                for item in (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_name=:t"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            assert not {"public_key_b64", "verified", "valid", "signature_ok", "verified_at"} & cols
        guard = (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one()
        assert guard == FINDINGS_GUARD_MD5


@pytest.mark.db
async def test_d17_zero_signatures_rejected(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, include_signature=False)


@pytest.mark.db
async def test_d18_and_d18b_noncanonical_signatures_rejected(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, signature_b64="!" * 88)
    valid = encode_signature_b64(os.urandom(64))
    injected = valid[:40] + "\n" + valid[41:]
    assert len(injected) == 88
    with pytest.raises(DBAPIError):
        await insert_raw_bundle_as_runtime(rls_engine, seeded, signature_b64=injected)


@pytest.mark.db
async def test_manifest_digest_must_match_ordinal_3_hash(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    with pytest.raises(DBAPIError, match="manifest_digest must equal ordinal 3 content_sha256"):
        await insert_raw_bundle_as_runtime(
            rls_engine, seeded, manifest_digest=SHA_A, signed_bytes_digest=SHA_A
        )


@pytest.mark.db
async def test_signature_b64_must_equal_ordinal_4_bytes(admin_engine, rls_engine):
    seeded = await committed_exportable(admin_engine)
    file_sig = os.urandom(64)
    other_sig = os.urandom(64)
    while other_sig == file_sig:
        other_sig = os.urandom(64)
    with pytest.raises(DBAPIError, match="signature_b64 must equal ordinal 4 content"):
        await insert_raw_bundle_as_runtime(
            rls_engine,
            seeded,
            files={1: b'{"pack":true}', 2: b"# preview\n", 3: b'{"not":"manifest"}', 4: file_sig},
            signature_b64=encode_signature_b64(other_sig),
        )


@pytest.mark.db
async def test_d27_replayed_horizon_is_binding_mismatch(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    snap = await generate_export_bundle(
        ctx, seeded["pack_id"], actor="slice60-test", idempotency_key=unique_key("d27")
    )
    async with tenant_scope(ctx) as session:
        repo = ExportBundleReadRepository(session, ctx)
        files = await repo.bundle_files(snap.id)
        signature = await repo.bundle_signature(snap.id)
        payload = {row.ordinal: bytes(row.content) for row in files}
        assert signature is not None
        signature_b64 = signature.signature_b64
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant',:t,true)"),
                {"t": str(seeded["tenant"])},
            )
            replayed = await insert_raw_bundle(
                session,
                seeded,
                files=payload,
                signature=payload[4],
                signature_b64=signature_b64,
                signing_key_id=snap.signing_key_id,
                redaction_policy_digest=snap.redaction_policy_digest,
                idempotency_key=unique_key("d27-copy"),
            )
    result = await verify_export_bundle(ctx, replayed)
    assert result.integrity_result is IntegrityResult.MANIFEST_BINDING_MISMATCH


@pytest.mark.db
async def test_d28_invalid_file3_is_manifest_invalid_without_raise(admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    nested = b"[" * (sys.getrecursionlimit() + 50) + b"]" * (sys.getrecursionlimit() + 50)
    huge_int = ("1" * 5000).encode("ascii")
    cases = (b"\xff\xfe", b"{not json", b'{"wrong":"shape"}', nested, huge_int)
    for index, content in enumerate(cases):
        files = {1: b'{"pack":true}', 2: b"# p\n", 3: content, 4: os.urandom(64)}
        async with AsyncSession(admin_engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.current_tenant',:t,true)"),
                    {"t": str(seeded["tenant"])},
                )
                record_id = await insert_raw_bundle(
                    session, seeded, files=files, idempotency_key=unique_key(f"d28-{index}")
                )
        result = await verify_export_bundle(ctx, record_id)
        assert result.integrity_result is IntegrityResult.MANIFEST_INVALID
        assert result.horizon_status in {HorizonStatus.WITHIN, HorizonStatus.EXPIRED}
