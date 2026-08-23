"""Shared Slice-60 export-bundle test helpers. Not a collected test module."""

from __future__ import annotations

import os
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.release.evidence_pack import (
    INVENTORY_SECTIONS,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
)
from app.release.export_bundle import (
    BUNDLE_CONTRACT_VERSION,
    BUNDLE_FILES,
    REDACTION_POLICY_VERSION,
)
from app.release.export_signing import (
    derived_public_key,
    encode_public_key_b64,
    encode_seed_b64,
    encode_signature_b64,
    generate_seed,
)
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.release_verdicts import ReleaseVerdictRepository
from app.tenancy import TenantContext

FINDINGS_GUARD_MD5 = "808036faf2660d6810aeca4342e6f1ac"
SHA_A = "sha256:" + "a" * 64
EXPORT_TABLES = (
    "evidence_pack_export_records",
    "evidence_pack_export_files",
    "evidence_pack_manifest_signatures",
)
STABLE_HASHES = {
    "app/release/evidence_pack.py": (
        "4f4d79a3a7991b227a605f4e9ffc8d033804bbdfec89ba9af5f28a1d97689796"
    ),
    "app/release/evidence_export.py": (
        "9877dc4057c1ac9a72d8fe0205b960ee81cfce0ff154dcc38ccbd4d0f4ff4116"
    ),
    "app/repositories/evidence_packs.py": (
        "9b6c464a6831be3581737bd1a612699b9e8c51cf5374f79e754d001ebb194a2c"
    ),
    "app/release/release_manager.py": (
        "4d9fe57557c39cbaff80d1a5730ae73554a009de5ca3360e8d866fa4be83b896"
    ),
    "app/repositories/release_verdicts.py": (
        "2241e1a8df86647065c1c690780aa95884fc87429475869b6b2d3bf72e088555"
    ),
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26",
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
    "app/api/auth.py": "86930b47f16f0a487518b2e232412ce61e7536d45bf963e7da7f7518d0fc76ab",
    "app/identity.py": "a76f99b85593e6d7ade9f71b6adb1a1ca81b3066436bb12ec9a04e7876897a09",
}


def unique_key(prefix: str) -> str:
    """Return a unique idempotency key."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def configure_signing(
    monkeypatch,
    *,
    seed: bytes | None = None,
    key_id: str = "uaid-test-key",
    trusted: dict[str, bytes] | None = None,
    private_b64: str | None = None,
) -> tuple[bytes, str, bytes]:
    """Pin operator signing settings. Returns ``(seed, key_id, public)``."""
    if seed is None:
        seed, public = generate_seed()
    else:
        public = derived_public_key(seed)
    mapping = trusted if trusted is not None else {key_id: public}
    raw = ",".join(f"{kid}={encode_public_key_b64(pub)}" for kid, pub in mapping.items())
    monkeypatch.setattr(
        settings, "evidence_signing_private_key_b64", private_b64 or encode_seed_b64(seed)
    )
    monkeypatch.setattr(settings, "evidence_signing_key_id", key_id)
    monkeypatch.setattr(settings, "evidence_signing_trusted_keys", raw)
    return seed, key_id, public


def zero_inventories() -> tuple[SectionInventory, ...]:
    """Return a complete zero-row inventory matching Slice 50's passing path."""
    empty = digest_bytes(canonical_json_bytes([]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present_zero_rows",
            item_count=0,
            section_digest=empty,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


async def scalar(conn, sql: str, **params):
    """Return a single SQL scalar."""
    return (await conn.execute(text(sql), params)).scalar_one()


async def seed_project(session) -> dict:
    """Insert org/tenants/project/two frozen candidates and a seed audit row."""
    suffix = uuid.uuid4().hex[:10]
    org = await scalar(
        session,
        "INSERT INTO organizations (name,slug) VALUES ('BundleOrg',:s) RETURNING id",
        s=f"bundle-org-{suffix}",
    )
    tenant = await scalar(
        session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t1',:s) RETURNING id",
        o=org,
        s=f"bundle-t1-{suffix}",
    )
    tenant2 = await scalar(
        session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t2',:s) RETURNING id",
        o=org,
        s=f"bundle-t2-{suffix}",
    )
    project = await scalar(
        session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id",
        t=tenant,
        s=f"bundle-p1-{suffix}",
    )
    project2 = await scalar(
        session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P2',:s) RETURNING id",
        t=tenant2,
        s=f"bundle-p2-{suffix}",
    )
    candidate = await _frozen_candidate(session, tenant, project, f"rel-{suffix}")
    candidate_b = await _frozen_candidate(session, tenant, project, f"rel-b-{suffix}")
    await session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(tenant)}
    )
    await session.execute(
        text("SELECT * FROM audit_append('slice60-test','seed',NULL,'{}'::jsonb)")
    )
    frozen_at = await scalar(
        session, "SELECT frozen_at FROM release_candidates WHERE id=:c", c=candidate
    )
    frozen_at_b = await scalar(
        session, "SELECT frozen_at FROM release_candidates WHERE id=:c", c=candidate_b
    )
    return {
        "tenant": tenant,
        "tenant2": tenant2,
        "project": project,
        "project2": project2,
        "candidate": candidate,
        "candidate_b": candidate_b,
        "frozen_at": frozen_at,
        "frozen_at_b": frozen_at_b,
        "suffix": suffix,
    }


async def persist_exportable_pack(
    session,
    ctx: dict,
    *,
    candidate_id=None,
    frozen_at=None,
    with_verdict: bool = True,
) -> dict:
    """Persist one complete core, optionally with a DB-bound Slice-50 verdict."""
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    candidate = candidate_id if candidate_id is not None else ctx["candidate"]
    frozen = frozen_at if frozen_at is not None else ctx["frozen_at"]
    tenant_context = TenantContext(ctx["tenant"])
    packs = EvidencePackRepository(session, tenant_context)
    checkpoint = await packs.record_audit_checkpoint()
    inventories = zero_inventories()
    core = assemble_core(
        project_id=ctx["project"],
        release_candidate_id=candidate,
        release_ref_digest=SHA_A,
        generated_at=checkpoint.created_at,
        frozen_at=frozen,
        artifact_scope_digest=SHA_A,
        issue_binding_digest=digest_bytes(canonical_json_bytes([])),
        source_refs=(),
        inventories=inventories,
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )
    pack = await packs._persist_core(
        project_id=ctx["project"],
        release_candidate_id=candidate,
        core=core,
        source_refs=(),
        inventories=inventories,
        traceability_edge_count=0,
        actor="slice60-test",
    )
    verdict = None
    if with_verdict:
        verdict = await ReleaseVerdictRepository(session, tenant_context).evaluate_and_record(
            project_id=ctx["project"],
            release_candidate_id=candidate,
            evidence_pack_id=pack.id,
            actor="slice60-test",
        )
    return {"pack": pack, "verdict": verdict, "checkpoint": checkpoint}


async def committed_exportable(admin_engine, *, with_verdict: bool = True) -> dict:
    """Commit a tenant, frozen candidate, pack, and optional verdict."""
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        async with session.begin():
            ctx = await seed_project(session)
            packed = await persist_exportable_pack(session, ctx, with_verdict=with_verdict)
            return {
                **ctx,
                "pack_id": packed["pack"].id,
                "verdict_id": None if packed["verdict"] is None else packed["verdict"].id,
                "checkpoint_id": packed["checkpoint"].id,
                "core_hash": packed["pack"].core_content_hash,
                "log_ref": packed["checkpoint"].verified_through_entry_hash,
                "candidate_id": packed["pack"].release_candidate_id,
            }


async def insert_raw_bundle(
    session,
    seeded: dict,
    *,
    files: dict[int, bytes] | None = None,
    signature: bytes | None = None,
    include_files: bool = True,
    include_signature: bool = True,
    as_of_sql: str = "transaction_timestamp()",
    expires_at_sql: str = "transaction_timestamp() + INTERVAL '720 hours'",
    auditor_access_mode: str = "offline_bundle",
    core_content_hash: str | None = None,
    release_candidate_id=None,
    audit_checkpoint_id=None,
    immutable_log_reference: str | None = None,
    release_verdict_id=None,
    signing_key_id: str = "uaid-test-key",
    total_byte_count: int | None = None,
    idempotency_key: str | None = None,
    file_overrides: dict[int, dict] | None = None,
    signature_b64: str | None = None,
    redaction_policy_digest: str | None = None,
    signed_bytes_digest: str | None = None,
) -> uuid.UUID:
    """Insert one bundle row set, optionally malformed, under deferred constraints."""
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    payload = files if files is not None else _dummy_files()
    sig = signature if signature is not None else payload.get(4, os.urandom(64))
    total = total_byte_count
    if total is None:
        total = sum(len(payload[ord_]) for ord_ in sorted(payload))
    record_id = uuid.uuid4()
    key = idempotency_key or unique_key("raw")
    await session.execute(
        text(
            "INSERT INTO evidence_pack_export_records ("
            "id, tenant_id, project_id, evidence_pack_id, release_candidate_id, "
            "release_verdict_id, audit_checkpoint_id, idempotency_key, "
            "bundle_contract_version, manifest_digest, redaction_policy_version, "
            "redaction_policy_digest, core_content_hash, immutable_log_reference, "
            "signing_key_id, auditor_access_mode, as_of, expires_at, file_count, "
            "total_byte_count) VALUES ("
            ":id, :t, :p, :pack, :rc, :v, :cp, :key, :bver, :md, :rver, :rd, :ch, "
            ":log, :sk, :mode, " + as_of_sql + ", " + expires_at_sql + ", 4, :bytes)"
        ),
        {
            "id": record_id,
            "t": seeded["tenant"],
            "p": seeded["project"],
            "pack": seeded["pack_id"],
            "rc": seeded["candidate_id"] if release_candidate_id is None else release_candidate_id,
            "v": seeded["verdict_id"] if release_verdict_id is None else release_verdict_id,
            "cp": seeded["checkpoint_id"] if audit_checkpoint_id is None else audit_checkpoint_id,
            "key": key,
            "bver": BUNDLE_CONTRACT_VERSION,
            "md": digest_bytes(payload[3]),
            "rver": REDACTION_POLICY_VERSION,
            "rd": (
                redaction_policy_digest
                if redaction_policy_digest is not None
                else digest_bytes(canonical_json_bytes({"probe": True}))
            ),
            "ch": seeded["core_hash"] if core_content_hash is None else core_content_hash,
            "log": seeded["log_ref"]
            if immutable_log_reference is None
            else immutable_log_reference,
            "sk": signing_key_id,
            "mode": auditor_access_mode,
            "bytes": total,
        },
    )
    overrides = file_overrides or {}
    if include_files:
        for ordinal, content in sorted(payload.items()):
            spec = next((item for item in BUNDLE_FILES if item.ordinal == ordinal), None)
            extra = overrides.get(ordinal, {})
            await session.execute(
                text(
                    "INSERT INTO evidence_pack_export_files ("
                    "tenant_id, project_id, export_record_id, ordinal, file_name, "
                    "media_type, content, byte_count, content_sha256) VALUES ("
                    ":t, :p, :e, :o, :n, :m, :c, :b, :h)"
                ),
                {
                    "t": seeded["tenant"],
                    "p": seeded["project"],
                    "e": record_id,
                    "o": extra.get("ordinal", ordinal),
                    "n": extra.get("file_name", spec.file_name if spec else "extra.bin"),
                    "m": extra.get(
                        "media_type", spec.media_type if spec else "application/octet-stream"
                    ),
                    "c": extra.get("content", content),
                    "b": extra.get("byte_count", len(content)),
                    "h": extra.get("content_sha256", digest_bytes(content)),
                },
            )
    if include_signature:
        encoded = signature_b64 if signature_b64 is not None else encode_signature_b64(sig)
        await session.execute(
            text(
                "INSERT INTO evidence_pack_manifest_signatures ("
                "tenant_id, project_id, export_record_id, signature_algorithm, "
                "signing_key_id, signature_b64, signed_bytes_digest) VALUES ("
                ":t, :p, :e, 'ed25519', :sk, :b64, :d)"
            ),
            {
                "t": seeded["tenant"],
                "p": seeded["project"],
                "e": record_id,
                "sk": signing_key_id,
                "b64": encoded,
                "d": signed_bytes_digest
                if signed_bytes_digest is not None
                else digest_bytes(payload[3]),
            },
        )
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    return record_id


def _dummy_files() -> dict[int, bytes]:
    signature = os.urandom(64)
    return {
        1: b'{"pack":true}',
        2: b"# preview\n",
        3: b'{"not":"manifest"}',
        4: signature,
    }


async def _frozen_candidate(session, tenant_id, project_id, release_ref):
    candidate = await scalar(
        session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:t,:p,:r,'draft') RETURNING id",
        t=tenant_id,
        p=project_id,
        r=release_ref,
    )
    await session.execute(
        text(
            "UPDATE release_candidates SET status='frozen', frozen_at=clock_timestamp() WHERE id=:c"
        ),
        {"c": candidate},
    )
    return candidate
