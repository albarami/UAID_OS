"""Slice 60 export-bundle pure contract proofs. Docker-free."""

from __future__ import annotations

import hashlib
import inspect
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.release.evidence_pack import canonical_json_bytes, digest_bytes
from app.release.export_bundle import (
    LIMITATIONS,
    MANIFESTED_FILES,
    MAX_BUNDLE_FILE_BYTES,
    SIGNING_KEY_NOT_CONFIGURED,
    SIGNING_KEY_NOT_SELF_CONSISTENT,
    ExportBundleError,
    ManifestedFile,
    build_manifest_payload,
    compute_redaction_policy_digest,
    parse_manifest_bytes,
    redaction_policy_payload,
)
from app.release.export_bundle_service import generate_export_bundle, verify_export_bundle
from app.release.export_signing import (
    generate_seed,
    sign_manifest_bytes,
    validate_signature_b64,
    verify_manifest_signature,
)
from app.tenancy import TenantContext
from tests.export_bundle_support import STABLE_HASHES, configure_signing


def _files() -> tuple[ManifestedFile, ManifestedFile]:
    return (
        ManifestedFile(
            1,
            "evidence_pack.json",
            "application/json",
            12,
            digest_bytes(b'{"a":1}'),
        ),
        ManifestedFile(
            2,
            "evidence_pack_core.preview.md",
            "text/markdown; charset=utf-8",
            9,
            digest_bytes(b"# preview"),
        ),
    )


def _payload(**overrides):
    values = {
        "project_id": uuid.UUID("60000000-0000-4000-8000-000000000001"),
        "release_candidate_id": uuid.UUID("60000000-0000-4000-8000-000000000002"),
        "evidence_pack_id": uuid.UUID("60000000-0000-4000-8000-000000000003"),
        "release_verdict_id": uuid.UUID("60000000-0000-4000-8000-000000000004"),
        "generated_at": datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        "core_content_hash": "sha256:" + "a" * 64,
        "immutable_log_reference": "b" * 64,
        "signing_key_id": "uaid-test-key",
        "redaction_policy_digest": "sha256:" + "c" * 64,
        "expires_at": datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        "files": _files(),
    }
    values.update(overrides)
    return build_manifest_payload(**values)


def test_u1_manifest_shape_limitations_and_two_files():
    payload = _payload()
    assert payload["manifest_version"] == "slice60.signed_manifest.v1"
    assert payload["schema_version"] == "uaid.evidence_pack.v1.2"
    assert payload["signature_algorithm"] == "ed25519"
    assert payload["auditor_access"]["mode"] == "offline_bundle"
    assert payload["limitations"] == list(LIMITATIONS)
    assert len(payload["limitations"]) == 10
    assert payload["limitations"][-1] == "export_is_a_claim_about_evidence_not_a_replacement_for_it"
    assert len(payload["files"]) == 2 == len(MANIFESTED_FILES)
    assert [row["ordinal"] for row in payload["files"]] == [1, 2]
    assert "evidence_pack.manifest.json" not in {row["file_name"] for row in payload["files"]}


def test_u2_sign_verify_round_trip(monkeypatch):
    seed, key_id, _public = configure_signing(monkeypatch)
    data = canonical_json_bytes(_payload())
    signature, signed_id = sign_manifest_bytes(data)
    assert signed_id == key_id
    assert len(signature) == 64
    assert verify_manifest_signature(data, signature, key_id) is True
    assert verify_manifest_signature(data + b"x", signature, key_id) is False
    del seed


def test_u3_canonical_manifest_bytes_are_stable():
    first = canonical_json_bytes(_payload())
    second = canonical_json_bytes(_payload())
    assert first == second
    assert first.startswith(b"{")


def test_u4_unconfigured_key_refuses(monkeypatch):
    monkeypatch.setattr("app.config.settings.evidence_signing_private_key_b64", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_key_id", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_trusted_keys", "")
    from app.release.export_signing import load_signing_seed

    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_CONFIGURED):
        load_signing_seed()


async def test_u4_generate_wrapper_refuses_unconfigured(monkeypatch):
    monkeypatch.setattr("app.config.settings.evidence_signing_private_key_b64", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_key_id", "")
    monkeypatch.setattr("app.config.settings.evidence_signing_trusted_keys", "")
    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_CONFIGURED):
        await generate_export_bundle(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="slice60-test",
            idempotency_key="k1",
        )


def test_u5_malformed_seed_refused(monkeypatch):
    configure_signing(monkeypatch)
    monkeypatch.setattr("app.config.settings.evidence_signing_private_key_b64", "not-base64!!")
    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_CONFIGURED):
        from app.release.export_signing import load_signing_seed

        load_signing_seed()
    monkeypatch.setattr(
        "app.config.settings.evidence_signing_private_key_b64",
        "YWJjZA==",
    )
    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_CONFIGURED):
        from app.release.export_signing import load_signing_seed

        load_signing_seed()


def test_u6_key_id_absent_or_public_mismatch(monkeypatch):
    seed, _key_id, public = configure_signing(monkeypatch, key_id="active")
    monkeypatch.setattr("app.config.settings.evidence_signing_trusted_keys", "")
    from app.release.export_signing import load_signing_seed

    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_SELF_CONSISTENT):
        load_signing_seed()
    other_seed, other_public = generate_seed()
    configure_signing(
        monkeypatch,
        seed=seed,
        key_id="active",
        trusted={"active": other_public},
    )
    with pytest.raises(ExportBundleError, match=SIGNING_KEY_NOT_SELF_CONSISTENT):
        load_signing_seed()
    del other_seed
    del public


def test_u7_redaction_digest_changes_on_mutated_projection():
    original = compute_redaction_policy_digest()
    payload = redaction_policy_payload()
    mutated_fields = {
        kind: list(names) + ["slice60_probe_field"]
        for kind, names in payload["projection_fields"].items()
    }
    mutated = compute_redaction_policy_digest(projection=mutated_fields)
    assert mutated != original
    assert compute_redaction_policy_digest() == original


def test_d25_frozen_file_sha256():
    for path, digest in STABLE_HASHES.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_wrappers_have_no_session_as_of_or_expires_at():
    for fn in (generate_export_bundle, verify_export_bundle):
        params = inspect.signature(fn).parameters
        assert "session" not in params
        assert "as_of" not in params
        assert "expires_at" not in params


def test_parse_manifest_is_total_over_attacker_bytes():
    nested = b"[" * (sys.getrecursionlimit() + 50) + b"]" * (sys.getrecursionlimit() + 50)
    huge_int = ("1" * 5000).encode("ascii")
    oversized = b"x" * (MAX_BUNDLE_FILE_BYTES + 1)
    assert parse_manifest_bytes(b"\xff\xfe") is None
    assert parse_manifest_bytes(b"{not json") is None
    assert parse_manifest_bytes(b"[]") is None
    assert parse_manifest_bytes(b"{}") is None
    assert parse_manifest_bytes(nested) is None
    assert parse_manifest_bytes(huge_int) is None
    assert parse_manifest_bytes(oversized) is None


def test_python_strict_base64_rejects_bang_and_newline(monkeypatch):
    configure_signing(monkeypatch)
    with pytest.raises(ExportBundleError, match="signature_b64_invalid"):
        validate_signature_b64("!" * 88)
    valid = "A" * 86 + "=="
    injected = valid[:40] + "\n" + valid[41:]
    with pytest.raises(ExportBundleError, match="signature_b64_invalid"):
        validate_signature_b64(injected)
