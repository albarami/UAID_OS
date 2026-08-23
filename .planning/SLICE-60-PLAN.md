# Slice 60 — Signed offline auditor bundle (external-assurance export hardening)

**Seats (ruling 2026-08-23).** PLANNER = Claude seat (this document). BUILDER = Cursor Grok 4.6
Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority, probe-backed verdicts only.

**Version.** v4 (v1 REJECTED — eight defects; v2 REJECTED — three; v3 REJECTED — one; all twelve
accepted and fixed, none argued down; see §7 for the change log).

> **APPROVED.** The three-consecutive-REJECT halt (v1/v2/v3) was reported to Salim, who
> authorized a fourth review round on 2026-08-23 with halt rules otherwise unchanged, and
> confirmed the seat ruling — v1–v4 are planner-seat work; the builder seat never touched this
> plan. The reviewer **APPROVED v4**: "The verifier is now total and fail-closed … The builder
> may proceed." Build may start.
**Alembic head at plan time.** `0058` (`migrations/versions/0058_stabilization.py`,
`revision="0058"`, probe-confirmed). This slice's migration is **`0059`**, `down_revision="0058"`.

**Contract versions.** `slice60.export_bundle.v1`, `slice60.signed_manifest.v1`,
`slice60.redaction_policy.v1`, `slice60.bundle_verification.v1`.

---

## 0. What this slice is, and the two things it deliberately refuses

Slice 49 assembles an immutable evidence-pack core; Slice 50 unlocked re-audited canonical
`evidence_pack.json` export with `signatures: []` and
`signature_status='unsigned_signer_tier_not_implemented'`. Slice 60 makes that export
**externally verifiable and auditor-consumable offline**, per §28.1 (l.2855–2914) and §15.4
(l.1496–1502).

It adds: an Ed25519-signed **detached manifest**; **persisted exact bundle bytes** so
re-verification is real; an explicit, versioned, digest-pinned **redaction policy**; and a
recorded **offline auditor bundle** with a declared expiry.

### 0.1 The signing honesty crux

The private key is **operator env-only**. A signature therefore proves exactly one thing:

> These exact bytes were signed by a holder of the private key whose **operator-pinned trusted
> public key** is registered under `signing_key_id`, at the recorded time.

It is **not** a human signature, **not** an approval-matrix or domain authority attestation,
**not** rooted in any external PKI, certificate chain, or transparency log, and **not**
non-repudiation by any person. It is the key-custody tier the codebase already names honestly
for `request_authenticated` (`app/identity.py:7`), applied to bytes. Status value:
**`app_key_custody_signed`**, and it is **computed at verification time only** — never surfaced
merely because a row exists (§0.2).

What it buys an auditor is real: with the trusted public key alone, and no access to UAID, an
auditor can prove the bundle they hold is byte-identical to what UAID emitted.

### 0.2 The forgery lesson from Slice 59, applied in three places

Slice 59 was rejected twice for letting a `passed` rung rest on evidence `uaid_app` can write
directly. `uaid_app` will hold INSERT on all three new tables, so the same trap applies here in
three distinct forms. Each is closed **structurally**, not by convention.

**(a) No stored verdict.** There is no `verified`, `valid`, `signature_ok`, or `verified_at`
column anywhere in §3. Validity is only ever the return value of `verify_export_bundle`,
recomputed from persisted bytes on every call.

**(b) No caller-supplied trust anchor.** *This was v1's most serious defect.* v1 stored
`public_key_b64` on the signature row, so a direct-SQL forger could sign an attacker manifest
with an attacker key, store the attacker public key, and verification would pass against it.

**`public_key_b64` is removed from the schema entirely.** Verification resolves the trusted
public key **from operator configuration, by `signing_key_id`** (OD-60-2). A `signing_key_id`
absent from the operator's trusted map yields `untrusted_signing_key` and never verifies.
Probe D-9b inserts a *correctly signed* attacker manifest plus attacker key id and requires
`untrusted_signing_key`.

**(c) No forgeable audit claim.** v1's `evidence_pack.bundle_verified` action was itself a
persisted validity claim, appendable by `uaid_app` through `audit_append`
(`migrations/versions/0003_audit_log.py:123-151,200-204`). It is **removed**. The only
verification-related audit action is `evidence_pack.bundle_verification_attempted`, carrying a
runtime-reported `result_code` and the literal
`audit_event_is_a_reported_attempt_not_validity_evidence`. No code path may read an audit row as
proof of validity.

### 0.3 Refused: OSCAL

**Not built. Deliberately.** §28.1 l.2907 requires OSCAL "**optional** … **when policy requires
it**"; §15.4 l.1502 says "**optional** compliance mapping". No OSCAL catalog, profile, or
component definition ships here (zero matches under `app/`, `migrations/`, `tests/`,
`docs/UAID_OS_Intake_Template_Pack_v1_2/`). Emitting a control mapping with no catalog to map
against would be fabricated — the §2.1 fake-done this project refuses.

### 0.4 Refused: scoped links and temporary audit accounts

**Not built. Deliberately.** §28.1 l.2909 is a disjunction — "scoped links, temporary audit
accounts, **or** offline export bundles" — and `auditor_access.mode` (l.2899) is an enum
including `offline_bundle`. Either alternative is a **new bearer credential bypassing
`require_tenant`** (`app/api/auth.py:34-54`), and `tenant_api_keys` has no scope, audience,
expiry, or permission column (`app/models/tenant_api_key.py:44-49`). That is an authentication
redesign, not export hardening. **Slice 60 adds no HTTP route and no new credential type**, and
`app/api/auth.py` + `app/identity.py` are frozen (§1) to make this structural.

### 0.5 The expiry honesty crux

§28.1 l.2900 requires `auditor_access.expiry`. For an offline bundle this is a **declared
validity horizon, not enforced revocation** — bytes that have left the system cannot be
recalled. Manifest and record both carry `expires_at` and the literal limitation
`offline_bundle_expiry_is_declared_not_enforced`. Reads label an expired bundle expired; nothing
pretends the bytes stopped existing.

### 0.6 Allowed claims, verbatim

- "UAID emitted an offline auditor bundle for one exact re-audited evidence-pack core and its
  DB-bound release verdict, persisted the exact bytes, and signed a detached manifest of the
  payload files' hashes with an app-custody Ed25519 key."
- "An auditor holding the operator-pinned trusted public key can verify the bundle is
  byte-identical to what UAID emitted."

### 0.7 Refused claims, verbatim

- That the signature is a human signature, an authority attestation, or non-repudiation.
- That the signing key is externally rooted, certified, HSM-held, or in any PKI.
- That the bundle is OSCAL-mapped or compliance-certified.
- That the declared expiry is enforced, or that a bundle can be revoked.
- That the export replaces evidence (§28 l.2914) or authorizes go-live.
- That the redaction policy is a human-approved data-classification policy.
- That `evidence_pack.json` itself is signed — it is not; the signature is **detached**.
- That an audit row, or the existence of a signature row, is evidence of validity.

---

## 1. Frozen files — byte-identical, SHA-256 verified before and after

Builder re-verifies at start and finish; reviewer re-verifies independently. **Any change is an
automatic REJECT.**

| File | SHA-256 |
|---|---|
| `app/release/evidence_pack.py` | `4f4d79a3a7991b227a605f4e9ffc8d033804bbdfec89ba9af5f28a1d97689796` |
| `app/release/evidence_export.py` | `9877dc4057c1ac9a72d8fe0205b960ee81cfce0ff154dcc38ccbd4d0f4ff4116` |
| `app/repositories/evidence_packs.py` | `9b6c464a6831be3581737bd1a612699b9e8c51cf5374f79e754d001ebb194a2c` |
| `app/release/release_manager.py` | `4d9fe57557c39cbaff80d1a5730ae73554a009de5ca3360e8d866fa4be83b896` |
| `app/repositories/release_verdicts.py` | `2241e1a8df86647065c1c690780aa95884fc87429475869b6b2d3bf72e088555` |
| `app/release/production_autonomy.py` | `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029` |
| `app/intake/readiness.py` | `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26` |
| `app/runtime/control_loop.py` | `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180` |
| `app/api/auth.py` | `86930b47f16f0a487518b2e232412ce61e7536d45bf963e7da7f7518d0fc76ab` |
| `app/identity.py` | `a76f99b85593e6d7ade9f71b6adb1a1ca81b3066436bb12ec9a04e7876897a09` |

Freezing the first three is the central architectural choice (OD-60-3). `evidence_pack.py`
carries three **hardcoded** contract hashes (`:28-30`) that `get_latest_exact_binding` filters
on (`app/repositories/evidence_packs.py:195-197`), plus a five-element exact-match
`assurance_limitations` list duplicated across three sites (`evidence_pack.py:805-811`,
`:1041-1051`, `evidence_export.py:129-135`). Touching any would silently invalidate every
previously assembled pack.

Also unchanged and asserted: the `release_findings_guard()` MD5 `808036faf2660d6810aeca4342e6f1ac`.

---

## 2. Design

### OD-60-1 — Ed25519, and why not HMAC

**Ed25519** (RFC 8032) via `cryptography`, added with `uv add cryptography` (new direct
dependency; probe-confirmed absent, not even transitive).

HMAC-SHA256 was considered and **rejected**: symmetric, so any auditor able to verify is equally
able to forge. A signature the verifier can mint is not external assurance and would be
dishonest under §28 l.2849. Ed25519 is asymmetric, deterministic, and needs only a 32-byte
public key to verify.

### OD-60-2 — Key custody, the trusted-key map, fail-closed behaviour

Three `Settings` fields in `app/config.py` (Pydantic `BaseSettings`):

- `evidence_signing_private_key_b64: str = ""` — base64 of the 32-byte Ed25519 seed. **Signing
  input only. Never used for verification.**
- `evidence_signing_key_id: str = ""` — bounded operator label for the *active* signing key.
- `evidence_signing_trusted_keys: str = ""` — the **verification trust anchor**: a
  `key_id=base64_pubkey` comma-separated map, parsed into `Mapping[str, bytes]`. Historical key
  ids stay listed so old bundles remain verifiable after rotation.

**Signing fails closed** when the seed or active key id is empty, the seed is not exactly 32
bytes after strict decode, or `evidence_signing_key_id` is absent from
`evidence_signing_trusted_keys` **with a public key matching the seed's derived public key** —
that last check prevents an operator misconfiguration from producing bundles nobody can verify.
Refusal code `signing_key_not_configured` / `signing_key_not_self_consistent`; nothing is
written. There is no unsigned-bundle fallback.

**Verification** resolves the public key **solely** from `evidence_signing_trusted_keys` by the
`signing_key_id` stored on the row. An unknown id yields `untrusted_signing_key`. The signature
row's own bytes are never a trust input, and there is no stored public key to consult (§0.2b).

The private key is **never** stored, logged, audited, exported, placed in a manifest, or put in
an error message. Test D-11 asserts the seed string appears in no audit payload, no persisted
column, and no bundle byte.

The raw crypto entry points are private/explicitly named unchecked
(`_sign_bytes_unchecked`, `_verify_signature_unchecked`); the only public surface is
`sign_manifest_bytes` and `verify_manifest_signature`, both of which enforce the trusted-key
resolution.

### OD-60-3 — Detached signature; core and canonical export stay byte-identical

The signature is over the **manifest**, not `evidence_pack.json`. §28.1 l.2908 permits exactly
this: "cryptographically sign the evidence pack contents **or** store a signed manifest of
hashes for all included artifacts" (probe-confirmed wording).

Consequences, all deliberate: `evidence_pack.json` keeps `signatures: []` and
`signature_status='unsigned_signer_tier_not_implemented'`, **stated as limitation 3** and never
hidden; the `evidence_packs` row is untouched, so `0059` does **not** alter
`ck_evidence_packs_attestations_deferred`; the Slice-49 invariant "the stored core must never
contain attestations" (`evidence_pack.py:1121-1122`) is preserved. Slice 60 is **purely
additive** — no existing table, column, CHECK, grant, trigger, or contract hash changes.

### OD-60-4 — Bundle composition: four persisted files, two manifested

*v1 defect 1 (the manifest cannot contain its own hash — an impossible fixed point) is fixed by
separating the two tuples.*

`BUNDLE_FILES` — the four files persisted and delivered:

| ord | file_name | media_type | producer |
|---|---|---|---|
| 1 | `evidence_pack.json` | `application/json` | frozen `export_canonical_json` |
| 2 | `evidence_pack_core.preview.md` | `text/markdown; charset=utf-8` | frozen `export_markdown` |
| 3 | `evidence_pack.manifest.json` | `application/json` | new (§2.1) |
| 4 | `evidence_pack.manifest.sig` | `application/octet-stream` | new; raw 64-byte Ed25519 signature over file 3's exact bytes |

`MANIFESTED_FILES` — ordinals **1 and 2 only**, the payload files whose hashes the manifest
enumerates.

**The authentication chain is complete without self-reference:** the signature (file 4)
authenticates file 3's exact bytes; file 3 enumerates the SHA-256 of files 1 and 2. Tampering
with any of the four is detected — payload tampering by hash mismatch against the manifest,
manifest tampering by signature failure, signature tampering by verification failure. Tests
D-20/21/22 prove each independently.

Both tuples are ordered and the order is load-bearing, mirroring `INVENTORY_SECTIONS`
(`evidence_pack.py:42-55`).

Because file 1 requires `export_canonical_json`, a bundle **inherits Slice 50's gate**: it can
exist only for a pack with a re-audited, DB-bound `ReleaseVerdict` whose `core_content_hash`
matches. No gate is invented or weakened. The exact `release_verdict_id` is persisted (§3.1) so
the bundle's verdict lineage is pinned rather than re-derived by a latest-wins select.

**No PDF** (§15.4 l.1499 offers md **or** pdf; markdown is provided). File 2 keeps its
`_core.preview` name because that is what the frozen builder produces
(`evidence_export.py:143-169`) — renaming it `evidence_pack.md` would overstate completeness.

### OD-60-5 — Manifest shape (`slice60.signed_manifest.v1`)

Canonical bytes via the frozen `canonical_json_bytes` (`evidence_pack.py:312-324`), so the
signed bytes are reproducible.

```
{
  "manifest_version": "slice60.signed_manifest.v1",
  "schema_version": "uaid.evidence_pack.v1.2",
  "project_id": "...", "release_candidate_id": "...",
  "evidence_pack_id": "...", "release_verdict_id": "...",
  "generated_at": "...Z",
  "core_content_hash": "sha256:...",
  "immutable_log_reference": "<audit_chain_verifications.verified_through_entry_hash>",
  "signing_key_id": "...",
  "signature_algorithm": "ed25519",
  "redaction_policy": {"version": "slice60.redaction_policy.v1", "digest": "sha256:..."},
  "auditor_access": {"mode": "offline_bundle", "expiry": "...Z",
                     "redaction_policy": "slice60.redaction_policy.v1"},
  "files": [ {"ordinal": 1, ...}, {"ordinal": 2, ...} ],   // MANIFESTED_FILES only
  "limitations": [ ... §2.2, exact ordered list ... ]
}
```

`auditor_access` mirrors §28.1 l.2898-2901 field-for-field.

**`immutable_log_reference` lineage (v1 defect 4 fix).** `evidence_packs` has **no**
`immutable_log_reference` column — it has `audit_checkpoint_id`
(`app/models/evidence_pack.py:222`). The value is therefore read by joining the pack's
`audit_checkpoint_id` to `audit_chain_verifications.verified_through_entry_hash`
(`app/models/audit_chain_verification.py:39-44`), never from a caller, and the §3.1 guard
enforces that join.

### 2.1 Signed-bytes definition

The signature covers **exactly** `canonical_json_bytes(manifest_payload)` — the identical bytes
persisted as file 3. `manifest_digest = digest_bytes(those bytes)`.

Verification, in order, all against **persisted bytes**: (1) recompute each file's SHA-256 from
its stored bytes and compare to the stored `content_sha256`; (2) recompute `manifest_digest`
from file 3's stored bytes and compare to the record; (3) **parse file 3 totally and fail
closed** per §2.1.3, then confirm its `files[]` hashes match files 1 and 2; (4) **rebind the
manifest to its record** per §2.1.2; (5) resolve the
trusted public key by `signing_key_id` from operator config, failing `untrusted_signing_key` if
absent; (6) verify file 4's bytes as an Ed25519 signature over file 3's bytes; (7) recompute the
redaction-policy digest and compare. Every step must pass.

### 2.1.2 Manifest rebinding — the replay defence

*v2 defect 1 fix.* Steps 1–3 and 5–6 prove the four files are mutually consistent and signed,
but **not that they belong to the record that carries them**. A direct-SQL attacker could copy a
valid four-file bundle verbatim into a *new* export record for the same pack with a fresh
`as_of`, fresh `expires_at`, and a new `idempotency_key`. Every guard in §3.1 and every
signature check would pass, and the replayed record would appear to have a refreshed horizon —
without the attacker ever holding the private key.

Step 4 therefore **reconstructs the complete expected manifest payload** from the DB-bound row
set — the export record, its pack, its verdict, its audit checkpoint, and its file rows — using
the same `build_manifest_payload` the generator used, and requires **byte-exact canonical
equality** with file 3's stored bytes. Every signed identity, time, and policy field is thereby
compared: `project_id`, `release_candidate_id`, `evidence_pack_id`, `release_verdict_id`,
`generated_at`, `core_content_hash`, `immutable_log_reference`, `signing_key_id`,
`redaction_policy`, `auditor_access` (including `expiry`), `files[]`, and `limitations`.

A mismatch yields **`manifest_binding_mismatch`**. Because the manifest commits to
`generated_at` and `expiry`, a replayed record with a fresh horizon fails here: its
reconstructed manifest cannot equal the signed original. Probe D-27 performs exactly this copy
attack and requires `manifest_binding_mismatch`.

### 2.1.3 Total parsing — the verifier must never raise on attacker bytes

*v3 defect fix.* `content` is arbitrary `BYTEA`; the DB derives only its hash, count, and the
base64/signature bindings. Nothing constrains file 3 to be valid UTF-8, valid JSON, or a
well-shaped manifest, so `uaid_app` can commit a file 3 that satisfies **every** hash, count,
signature-byte, and base64 invariant yet cannot be parsed. v3's step 3 would then raise before
returning any closed result — an unhandled exception where a verdict was promised.

Step 3 is therefore **total**. It fails closed over, in order: UTF-8 decoding, JSON parsing,
top-level object shape, required-key presence, per-field types, and the `files[]` array
structure. Any failure returns **`manifest_invalid`** — never an exception, never a partial
result, and never a fall-through to a later step that might mask it.

`verify_export_bundle` is required to be total over **all** persisted byte sequences: for any
row set it must return a `(integrity_result, horizon_status)` pair. Probes D-28a/b/c commit,
by direct SQL, a file 3 that is invalid UTF-8, valid UTF-8 but malformed JSON, and valid JSON
with a wrong shape; each must return `manifest_invalid` and each must **not** raise.

### 2.1.1 The verification result (`slice60.bundle_verification.v1`)

*v2 defect 3 fix.* A single closed enum cannot simultaneously say "cryptographically intact" and
"past its declared horizon", yet both must be reportable — v2 asked one field to hold two
values. The result is therefore a frozen dataclass, never persisted, with **two independent
axes**:

**`integrity_result`** — the cryptographic and content axis:
`verified` · `untrusted_signing_key` · `signature_invalid` · `manifest_invalid` ·
`manifest_digest_mismatch` · `manifest_binding_mismatch` · `payload_hash_mismatch` ·
`stored_bytes_hash_mismatch` · `redaction_policy_digest_mismatch` · `file_set_incomplete`

**`horizon_status`** — the declared-validity axis, computed independently and never able to mask
or be masked by integrity: `within_declared_horizon` · `expired_declared_horizon`

`app_key_custody_signed` is emitted whenever `integrity_result == verified`, **regardless of
`horizon_status`** — an expired bundle whose signature verifies is honestly reported as
cryptographically intact and past its declared horizon, which is the truthful description of an
offline artifact that cannot be recalled (§0.5). Both axes are audited. Test D-4 asserts the
pairing `(verified, expired_declared_horizon)` is reachable and reported in full.

### 2.2 `limitations` — exact ordered list, matched exactly

Following the `assurance_limitations` precedent (`evidence_pack.py:1041-1053`):

1. `signature_is_app_key_custody_not_human_or_authority`
2. `signing_key_is_not_externally_rooted_no_pki_or_transparency_log`
3. `canonical_json_is_unsigned_signature_is_detached`
4. `human_readable_file_is_a_core_preview_not_a_full_report`
5. `no_pdf_export`
6. `offline_bundle_expiry_is_declared_not_enforced`
7. `no_oscal_control_mapping_optional_per_spec_2907`
8. `no_scoped_link_or_temporary_audit_account`
9. `redaction_policy_is_the_enforced_field_projection_not_a_human_approved_classification`
10. `export_is_a_claim_about_evidence_not_a_replacement_for_it`

Item 10 is §28 l.2914 and must never be removed.

### OD-60-6 — Redaction policy (`slice60.redaction_policy.v1`)

Redaction today is real but **implicit**: `EvidenceSourceRef.__post_init__`
(`evidence_pack.py:411-424`) enforces a two-sided allowlist against
`_PROHIBITED_PROJECTION_FIELDS` (`:94-124`) and `PROJECTION_FIELDS` (`:129-252`).

Slice 60 makes it explicit and pinned **without changing behaviour**: a pure function reads
those two frozen structures **by import** and computes
`digest_bytes(canonical_json_bytes({...}))`. Derived rather than restated, so it cannot drift
from what is enforced. Recomputed at verification and compared; a mismatch reports
`redaction_policy_digest_mismatch`. Limitation 9 states the honest scope.

### OD-60-7 — Expiry

`expires_at = as_of + EXPORT_BUNDLE_VALIDITY_HOURS` (`720`, a named constant). `as_of` is
**DB-generated** `transaction_timestamp()` (Slice 59 lesson); `expires_at` is the DB-computed
`as_of + INTERVAL`, set by the guard. Caller-supplied values for either are refused.

### OD-60-8 — Idempotency, latest-wins, and the race retry

*v1 defect 8 fix.* Generation takes a required `idempotency_key` (bounded 1–200, non-blank).
`UNIQUE (tenant_id, evidence_pack_id, idempotency_key)` makes a retry return the existing
record.

Under REPEATABLE READ an `IntegrityError` leaves the transaction failed, and the fixed snapshot
may never see the concurrent winner. The owned wrapper therefore **retries the entire
transaction from a fresh snapshot**, bounded, following the existing precedent verbatim
(`app/ops/stabilization_service.py:65-82`): at most `MAX_IDEMPOTENCY_RACE_RETRIES` complete
fresh transactions, retrying **only** the named idempotency race and PostgreSQL `40001`/`40P01`,
raising `ExportBundleIdempotencyRace` if the winner stays invisible. Test D-23 drives a real
concurrent generation.

Reads are **latest-wins** by `(created_at DESC, id DESC)`, matching every comparable store
(`monitoring_evidence.py`, `deployments.py`, `ops_incident_reads.py`). No "current" flag exists
to disagree with the ordering.

### OD-60-9 — Transaction and isolation

`generate_export_bundle(...)` owns its `tenant_scope` at **REPEATABLE READ** and takes no caller
`session`, `as_of`, or `expires_at`. `verify_export_bundle(...)` is a separate **READ
COMMITTED**, strictly read-only wrapper that writes nothing except, optionally, the
attempt-audit row of §0.2c.

### OD-60-10 — Audit safety

`evidence_pack.bundle_generated` and `evidence_pack.bundle_verification_attempted` carry **only**
ids, file count, byte counts, digests, `signing_key_id`, mode, expiry, and (for the attempt) the
reported `result_code` plus the non-evidence label. Never the private key, never file bytes,
never manifest contents, never a source ref. Mirrors `evidence_packs.py:811-825`.

---

## 3. Schema — migration `0059_export_bundles`, purely additive

Three tenant-owned tables, all **RLS ENABLE + FORCE**, all **append-only** (SELECT/INSERT only;
block-DML and block-TRUNCATE triggers), following `0048_evidence_packs.py:56-84` and
`app/ops/stabilization_ddl.py:255-280`.

**No new constraint on `evidence_packs`.** *v1 defect 6 fix:* `uq_ep_id_project_tenant
UNIQUE (id, project_id, tenant_id)` **already exists** (`0048:329`,
`app/models/evidence_pack.py:210`). `0059` references it and neither creates nor drops it.

### 3.1 `evidence_pack_export_records`

`id`, `tenant_id`, `project_id`, `evidence_pack_id`, `release_candidate_id`,
`release_verdict_id`, `audit_checkpoint_id`, `idempotency_key`, `bundle_contract_version`,
`manifest_digest`, `redaction_policy_version`, `redaction_policy_digest`, `core_content_hash`,
`immutable_log_reference`, `signing_key_id`, `auditor_access_mode`, `as_of`, `expires_at`,
`file_count`, `total_byte_count`, `created_at`.

Composite FK `(evidence_pack_id, project_id, tenant_id) → evidence_packs(id, project_id,
tenant_id)` `ON DELETE RESTRICT`; composite FK on `release_verdict_id` to `release_verdicts`.
`UNIQUE (tenant_id, evidence_pack_id, idempotency_key)`; `UNIQUE (id, project_id, tenant_id)` as
the child FK target.

CHECKs: `bundle_contract_version='slice60.export_bundle.v1'`;
`redaction_policy_version='slice60.redaction_policy.v1'`;
`auditor_access_mode='offline_bundle'` (single value — a scoped link is structurally
unrecordable, making §0.4 enforceable); `file_count=4`; `total_byte_count > 0`;
`expires_at > as_of`; `sha256:` regex on the three digest columns; bounded non-blank
`char_length`/`btrim` on `idempotency_key`, `signing_key_id`, `immutable_log_reference`.

**Guard trigger (BEFORE INSERT) — the DB backstop.** *v1 defect 4 fix adds rules 3–6.*
1. `as_of` **must equal** `transaction_timestamp()`.
2. `expires_at` **must equal** `as_of + INTERVAL '720 hours'`.
3. `core_content_hash` must equal the referenced `evidence_packs` row's value.
4. `release_candidate_id` and `audit_checkpoint_id` must equal the referenced pack's values.
5. `immutable_log_reference` must equal
   `audit_chain_verifications.verified_through_entry_hash` for that `audit_checkpoint_id`.
6. The referenced `release_verdicts` row must belong to the same tenant/project and have
   `evidence_pack_id` equal to this record's, with `core_content_hash` matching.
7. `file_count` must equal 4.

### 3.2 `evidence_pack_export_files`

`id`, `tenant_id`, `project_id`, `export_record_id`, `ordinal`, `file_name`, `media_type`,
`content` (**`BYTEA NOT NULL`**), `byte_count`, `content_sha256`, `created_at`.

*v1 defect 3 fix — the exact bytes are persisted.* Without them the promised re-verification
could not run and a record could claim hashes for files never emitted. `byte_count` and
`content_sha256` are **DB-derived from `content`**, not caller-asserted: the guard enforces
`byte_count = octet_length(content)` and
`content_sha256 = 'sha256:' || encode(sha256(content),'hex')` (core `sha256`, the same function
`0003_audit_log.py` uses — no extension). A caller-supplied mismatch is refused.

Bounded by `MAX_BUNDLE_FILE_BYTES` (16 MiB, matching `MAX_JSON_BYTES`,
`evidence_pack.py:33`) as both a Python bound and a CHECK.

Composite FK `(export_record_id, project_id, tenant_id) →
evidence_pack_export_records(id, project_id, tenant_id)`. `UNIQUE (export_record_id, ordinal)`,
`UNIQUE (export_record_id, file_name)`.

CHECKs: `ordinal BETWEEN 1 AND 4`; the exact ordinal↔file_name↔media_type triple pinned by a
four-way disjunction, mirroring `app/ops/stabilization_db_checks.py:9-16`; `byte_count > 0`;
`sha256:` regex.

**Deferred both-sided triggers** (Slice 37/59 pattern), so a late child insert is rejected:
- child count must equal the parent's `file_count` (4);
- `SUM(byte_count)` must equal the parent's `total_byte_count`;
- the parent's `manifest_digest` must equal ordinal 3's `content_sha256`;
- the signature row's `signature_b64`, base64-decoded, must equal ordinal 4's `content`.

The last two bind the record's digests and the signature to the **actual persisted bytes**,
which is what closes v1 defect 3.

### 3.3 `evidence_pack_manifest_signatures`

`id`, `tenant_id`, `project_id`, `export_record_id`, `signature_algorithm`, `signing_key_id`,
`signature_b64`, `signed_bytes_digest`, `created_at`.

*v1 defect 2 fix: `public_key_b64` is **deleted from the design**.* Storing it created a
caller-controlled trust anchor. The trust anchor is operator configuration only (OD-60-2).

Composite FK to the export record; `UNIQUE (export_record_id)` gives **at most** one signature.
*v1 defect 4 fix:* **exactly** one is enforced by a **deferred parent-side constraint trigger**
requiring exactly one child signature row at commit.

CHECKs: `signature_algorithm='ed25519'`; `sha256:` regex on `signed_bytes_digest`; bounded
non-blank `signing_key_id`.

**Strict base64 (v1 defect 7 + v2 defect 2 fix).** v1 used `char_length(signature_b64)=88`,
which proves nothing — `'!'*88` satisfies it, and 64 bytes encode to 88 chars ending `==`, not
one `=`.

v2's round-trip was still wrong: it stripped newlines from **both** sides, which the reviewer
disproved on real PostgreSQL 16 — a newline-injected 88-character signature decodes to 64 bytes
and was **accepted**. Normalizing the stored input is what creates the hole.

The CHECK therefore normalizes **only** `encode(...)`'s output — Postgres wraps at 76 chars —
and never touches the stored value, plus a strict character-class shape:

```
signature_b64 ~ '^[A-Za-z0-9+/]{86}==$'
AND octet_length(decode(signature_b64,'base64')) = 64
AND replace(encode(decode(signature_b64,'base64'),'base64'), E'\n', '') = signature_b64
```

Python-side validation uses `base64.b64decode(s, validate=True)`, a decoded-length check, and a
re-encode equality check. Both layers are required. Probe D-18b inserts a newline-injected
signature by direct SQL and requires rejection.

`sha256(bytea)` is available from `pg_catalog` with no extension — confirmed by the reviewer on
PostgreSQL 16 and already relied on by `migrations/versions/0003_audit_log.py`.

**Guard trigger:** `signed_bytes_digest` must equal the parent's `manifest_digest`, and
`signing_key_id` must equal the parent's.

### 3.4 Downgrade

Refuses if any row exists (`0048:660-670` / `0058:340` pattern), then drops the three tables and
their triggers and functions. Nothing on `evidence_packs` to restore.

---

## 4. Code layout (500-line house cap; split where needed)

| File | Contents |
|---|---|
| `app/release/export_bundle.py` | Pure: contract constants, `BUNDLE_FILES`, `MANIFESTED_FILES`, `LIMITATIONS`, `EXPORT_BUNDLE_VALIDITY_HOURS`, `MAX_BUNDLE_FILE_BYTES`, `build_manifest_payload` (used by both the generator **and** the §2.1.2 rebinding check), `compute_redaction_policy_digest`, the two result enums, frozen dataclasses. No I/O. |
| `app/release/export_signing.py` | Crypto boundary: `load_trusted_keys`, `sign_manifest_bytes`, `verify_manifest_signature`, private `_sign_bytes_unchecked` / `_verify_signature_unchecked`. The **only** module importing `cryptography`; mockable per house rule. |
| `app/release/export_bundle_db_checks.py` | Shared CHECK SQL consumed by both ORM and migration `0059`. |
| `app/release/export_bundle_ddl.py` | Shared DDL/trigger/RLS helpers for `0059`. |
| `app/release/export_bundle_service.py` | Public wrappers owning `tenant_scope` + the bounded race retry: `generate_export_bundle`, `verify_export_bundle`. |
| `app/models/evidence_pack_export.py` | The three ORM models. |
| `app/repositories/export_bundles.py` | `ExportBundleRepository`: generate/persist. |
| `app/repositories/export_bundle_reads.py` | `latest_bundle_for_pack`, `bundle_files`, `bundle_signature`, history. |
| `migrations/versions/0059_export_bundles.py` | `revision="0059"`, `down_revision="0058"`. |

Allowed existing-file edits, additive only: `app/config.py` (three settings),
`app/models/__init__.py` (registration — required for `Base.metadata`/Alembic, explicitly
permitted so the builder need not deviate), `.github/workflows/ci.yml` (add Slice 60 owned paths
to the scoped pyright list, keeping 55/56/57/58/59), `pyproject.toml` + `uv.lock` (via
`uv add cryptography`), `.env.example` (the three new key names, **no values**).

---

## 5. Tests

`tests/test_export_bundle.py`, `test_export_bundle_db.py`, `test_export_bundle_checks.py`,
`test_export_bundle_migrate.py`, plus `tests/export_bundle_support.py`. Split further if any
file nears 500 lines.

**Happy path.** U-1 manifest payload is exactly the specified shape with the exact 10-element
limitations list and `files[]` of length 2. U-2 sign→verify round-trips. U-3 canonical manifest
bytes are byte-stable across two builds of identical input. D-1 a full bundle persists one
record, four file rows with real bytes, one signature, and verifies end-to-end returning
`verified` + `app_key_custody_signed`.

**Edge.** U-4 unconfigured key ⇒ `signing_key_not_configured`, nothing written. U-5 malformed
seed (wrong length, non-base64) refused. U-6 active key id absent from the trusted map ⇒
`signing_key_not_self_consistent`, nothing written. D-2 retry with the same `idempotency_key`
returns the same record, no second bundle. D-3 a pack with no DB-bound verdict cannot produce a
bundle (inherited Slice 50 gate). D-4 an expired bundle reports `expired_declared_horizon`
**and** cryptographic success, not one masking the other. U-7 the redaction digest changes if
the projection changes (digest a mutated copy), proving it is derived.

**Failure and forgery — the direct-SQL probe set under `uaid_app` the reviewer will re-run.**
D-5 backdated `as_of` refused. D-6 caller-chosen `expires_at` refused. D-7
`auditor_access_mode='scoped_link'` refused. D-8 record whose `core_content_hash` differs from
the pack refused. D-8b wrong `release_candidate_id` / `audit_checkpoint_id` refused. D-8c
`immutable_log_reference` not matching the checkpoint refused. D-8d a `release_verdict_id`
belonging to another pack refused. **D-9 a garbage signature fails verification.** **D-9b the
key-substitution attack: a correctly signed attacker manifest under an attacker `signing_key_id`
must return `untrusted_signing_key`** — the §0.2b proof, and the single most important test in
this slice. D-10 signature whose `signed_bytes_digest` ≠ parent `manifest_digest` refused.
**D-11 the private seed appears in no audit payload, no column, no bundle byte.** D-12 file-count
tampering (3 or 5 children) rejected by the deferred trigger. D-12b `total_byte_count` not equal
to the child sum rejected. D-13 wrong ordinal↔file_name pairing rejected. D-13b a file row whose
`content_sha256` disagrees with `sha256(content)` rejected. D-14 UPDATE/DELETE/TRUNCATE blocked
on all three tables; RLS forced; grants exactly `SELECT, INSERT`. D-15 cross-tenant read returns
nothing. D-16 mutated projection ⇒ `redaction_policy_digest_mismatch`. D-17 zero signature rows
rejected by the deferred exactly-one trigger. **D-28a/b/c a file 3 committed by direct SQL as
invalid UTF-8, as malformed JSON, and as valid JSON of the wrong shape each return
`manifest_invalid` without raising** — the §2.1.3 totality proof. D-18 non-canonical base64
(`'!'*88`) rejected at
both DB and Python. **D-18b a newline-injected 88-char signature that decodes to 64 bytes is
rejected** — the v2 defect-2 proof. **D-27 the replay attack: a valid four-file bundle copied
verbatim into a fresh export record with a new `as_of`, `expires_at`, and `idempotency_key`
must return `manifest_binding_mismatch`** — the §2.1.2 proof, and jointly with D-9b the most
important test in this slice.

**Tamper chain (OD-60-4).** D-20 mutate file 1's bytes ⇒ `payload_hash_mismatch`. D-21 mutate
file 3's bytes ⇒ `signature_invalid`. D-22 mutate file 4's bytes ⇒ `signature_invalid`.

**Concurrency.** D-23 two concurrent generations with the same idempotency key yield one record,
via the bounded fresh-transaction retry.

**Non-regression, real-store (Slice 59 lesson — no tautologies).** D-24 real
`ProductionAutonomyRepository` and `ReadinessRepository` evaluated before → generate → after;
reports equal; A5 `slice54.v1`; readiness `slice20.v1`; `can_go_live_autonomously` literal
`False`. D-25 the ten frozen files' SHA-256 asserted in-test. D-26 migration `0059` empty
round-trip up/down/up; populated downgrade refused.

---

## 6. Non-goals, restated

No OSCAL. No scoped link. No temporary audit account. No HTTP route. No new credential type. No
PDF. No change to `evidence_pack.json` bytes, to any Slice-49/50 contract hash, to the
`evidence_packs` row or its constraints, or to `ck_evidence_packs_attestations_deferred`. No A5
gate flip: A5 stays `slice54.v1`, readiness `slice20.v1`, `can_go_live_autonomously` the literal
`False`. No HSM, no PKI, no key rotation mechanism (the trusted-key map merely keeps old ids
verifiable), no certificate chain, no transparency log.

**Roadmap exit: NOT SATISFIED.** Slice 60 delivers the signed manifest, the redaction policy, and
offline-bundle auditor access. OSCAL mapping, scoped links, temporary accounts, PDF, versioned
schema *migrations* (as opposed to a single version string), and key rotation stay open.

---

## 7. v1 → v2 change log (all eight reviewer defects accepted)

1. **Manifest self-hash fixed point.** `MANIFESTED_FILES` (ordinals 1–2) split from
   `BUNDLE_FILES` (1–4); the authentication chain and its three tamper tests are spelled out
   (OD-60-4, D-20/21/22).
2. **Attacker-controlled trust anchor.** `public_key_b64` deleted from the schema; verification
   resolves the key only from `evidence_signing_trusted_keys`; `untrusted_signing_key` added;
   probe D-9b added; raw crypto entry points made private/unchecked; the computed result enum
   defined (§2.1.1); `app_key_custody_signed` emitted only on `verified`.
3. **No persisted bytes.** `content BYTEA NOT NULL` added with DB-derived `byte_count` and
   `content_sha256`, a 16 MiB bound, deferred triggers binding `manifest_digest` to ordinal 3
   and the signature to ordinal 4, and `release_verdict_id` persisted.
4. **Unenforced cardinality and lineage.** Deferred parent-side exactly-one-signature trigger;
   candidate, checkpoint, and verdict bound to the referenced pack;
   `immutable_log_reference` derived through `audit_checkpoint_id` →
   `audit_chain_verifications` (the pack has **no** such column — corrected factual error);
   probes D-8b/c/d, D-12b, D-17 added.
5. **Forgeable audit claim.** `bundle_verified` removed; replaced by
   `bundle_verification_attempted` with a reported `result_code` and an explicit non-evidence
   label; §0.2c added.
6. **Duplicate constraint.** `uq_ep_id_project_tenant` already exists (`0048:329`) — creation and
   downgrade removed; corrected factual error.
7. **Meaningless base64 CHECK.** Length check replaced by strict decode + decoded-length +
   canonical re-encode round-trip at both DB and Python; probe D-18 added. (v1 also wrongly said
   64 bytes pad with one `=`; it is `==`.)
8. **Unworkable race handling.** Replaced with bounded whole-transaction retry from a fresh
   snapshot following `app/ops/stabilization_service.py:65-82`; test D-23 added.

### v2 → v3 (three further defects, all accepted)

9. **Replay: signed manifest not rebound to its record.** A valid bundle could be copied
   verbatim into a fresh export record with a new `as_of`/`expires_at` and pass every check,
   apparently refreshing its horizon without the private key. §2.1.2 adds a rebinding step that
   reconstructs the expected manifest from the DB-bound record, pack, verdict, checkpoint, and
   file rows via the same `build_manifest_payload`, and requires byte-exact canonical equality
   with file 3. New result `manifest_binding_mismatch`; probe D-27.
10. **Base64 normalization created the hole it was meant to close.** v2 stripped newlines from
    both sides, which the reviewer disproved on real PostgreSQL 16 by inserting a
    newline-injected 88-char signature that decoded to 64 bytes and was accepted. v3 normalizes
    **only** `encode(...)`'s output and adds `^[A-Za-z0-9+/]{86}==$`; probe D-18b.
11. **One enum cannot hold two values.** `verified` and `expired_declared_horizon` were both in
    a single closed enum while §2.1.1 required reporting them together. Split into independent
    `integrity_result` and `horizon_status` axes; `app_key_custody_signed` follows
    `integrity_result == verified` regardless of horizon; D-4 updated to assert the
    `(verified, expired_declared_horizon)` pairing is reachable.

### v3 → v4 (one further defect, accepted)

12. **The verifier was not total over attacker-writable bytes.** `content` is arbitrary `BYTEA`
    and nothing constrains file 3 to be parseable, so a row satisfying every hash, count,
    signature-byte, and base64 invariant could still make step 3 raise instead of returning a
    verdict. §2.1.3 makes parsing total and fail-closed over UTF-8, JSON, shape, field types,
    and `files[]` structure; new result `manifest_invalid`; probes D-28a/b/c. `verify_export_bundle`
    is now required to return a `(integrity_result, horizon_status)` pair for **any** row set.
