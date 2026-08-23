"""Postgres CHECK fragments for Slice-60 export bundles.

Consumed by the ORM and migration ``0059`` only.
"""

from __future__ import annotations

from app.release.export_bundle import (
    AUDITOR_ACCESS_MODE,
    BUNDLE_CONTRACT_VERSION,
    DIGEST_RE,
    FILE_COUNT,
    MAX_BUNDLE_FILE_BYTES,
    MAX_IDEMPOTENCY,
    MAX_SIGNING_KEY_ID,
    REDACTION_POLICY_VERSION,
    SIGNATURE_ALGORITHM,
)

HASH_SQL = f"~ '{DIGEST_RE}'"
IDEMPOTENCY_SQL = (
    f"char_length(idempotency_key) BETWEEN 1 AND {MAX_IDEMPOTENCY} "
    "AND idempotency_key = btrim(idempotency_key)"
)
SIGNING_KEY_SQL = (
    f"char_length(signing_key_id) BETWEEN 1 AND {MAX_SIGNING_KEY_ID} "
    "AND signing_key_id = btrim(signing_key_id)"
)
LOG_REF_SQL = (
    "char_length(immutable_log_reference) BETWEEN 1 AND 64 "
    "AND immutable_log_reference = btrim(immutable_log_reference) "
    "AND immutable_log_reference ~ '^[0-9a-f]{64}$'"
)
SIGNATURE_B64_SQL = (
    "signature_b64 ~ '^[A-Za-z0-9+/]{86}==$' "
    "AND octet_length(decode(signature_b64,'base64')) = 64 "
    "AND replace(encode(decode(signature_b64,'base64'),'base64'), E'\\n', '') = signature_b64"
)
ORDINAL_FILE_SQL = (
    "(ordinal=1 AND file_name='evidence_pack.json' "
    "AND media_type='application/json') OR "
    "(ordinal=2 AND file_name='evidence_pack_core.preview.md' "
    "AND media_type='text/markdown; charset=utf-8') OR "
    "(ordinal=3 AND file_name='evidence_pack.manifest.json' "
    "AND media_type='application/json') OR "
    "(ordinal=4 AND file_name='evidence_pack.manifest.sig' "
    "AND media_type='application/octet-stream')"
)
BYTE_BOUND_SQL = f"byte_count > 0 AND byte_count <= {MAX_BUNDLE_FILE_BYTES}"

RECORD_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("bundle_version", f"bundle_contract_version='{BUNDLE_CONTRACT_VERSION}'"),
    ("redaction_version", f"redaction_policy_version='{REDACTION_POLICY_VERSION}'"),
    ("access_mode", f"auditor_access_mode='{AUDITOR_ACCESS_MODE}'"),
    ("file_count", f"file_count={FILE_COUNT}"),
    ("total_bytes", "total_byte_count > 0"),
    ("expiry_after_as_of", "expires_at > as_of"),
    ("manifest_digest", f"manifest_digest {HASH_SQL}"),
    ("redaction_digest", f"redaction_policy_digest {HASH_SQL}"),
    ("core_hash", f"core_content_hash {HASH_SQL}"),
    ("idempotency_key", IDEMPOTENCY_SQL),
    ("signing_key_id", SIGNING_KEY_SQL),
    ("immutable_log_reference", LOG_REF_SQL),
)
FILE_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ordinal_range", "ordinal BETWEEN 1 AND 4"),
    ("ordinal_file_media", ORDINAL_FILE_SQL),
    ("byte_bound", BYTE_BOUND_SQL),
    ("content_sha256", f"content_sha256 {HASH_SQL}"),
)
SIGNATURE_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("algorithm", f"signature_algorithm='{SIGNATURE_ALGORITHM}'"),
    ("signed_digest", f"signed_bytes_digest {HASH_SQL}"),
    ("signing_key_id", SIGNING_KEY_SQL),
    ("signature_b64", SIGNATURE_B64_SQL),
)
