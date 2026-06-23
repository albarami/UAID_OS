# Slice 26 — Source-control / CI evidence-provenance foundation (A5 gate #3) — PLAN v3

**Status:** AWAITING PLAN APPROVAL — **no branch / no code / no migration / no tests until approved.**
Rulings D-26-1..7 are binding (see `.planning/SLICE-26-CI-EVIDENCE-DISCUSSION.md`, APPROVED).

> **Revision log (each fix enforced at the validator AND the DB level, with rejection tests):**
> - **Blocker 1a — `repo_ref` slug *shape* (v2).** `repo_ref` is constrained to a GitHub-first `owner/repo` **slug** by `REPO_REF_RE` in the **pure validator** (§2) **and** a column `CheckConstraint` + the INSERT guard (§3/§4.1), rejecting URLs, credentialed URLs, SSH URLs, query strings/fragments, whitespace/control chars, and multi-slash paths.
> - **Blocker 1b — token-looking `repo_ref` *content* (v3, per PLAN v2 review).** The slug shape alone did **not** reject token-looking repo names (e.g. `owner/ghp_…` matched, because the repo segment legitimately allows `[A-Za-z0-9._-]`). v3 adds a **separate denylist** `TOKENISH_RE = (?i)/(gh[opusr]_|github_pat_)` enforced in the pure validator (§2) **and** a column `CheckConstraint` (`repo_ref !~* …`) + the INSERT guard (§3/§4.1), rejecting GitHub token prefixes `ghp_/gho_/ghu_/ghs_/ghr_/github_pat_` in the repo segment. The pure-regex behavior is **empirically verified** against a battery (rejects all 6 token prefixes + all URL/SSH/query/fragment/ws/multislash cases; accepts legit names incl. `owner/github-actions`, `owner/ghost`, `owner/repo-ghp`). Pure + direct-SQL token rejection tests added (§8).
> - **Blocker 2 — `required_status_checks` JSON shape is DB-backed (v2).** Column is `JSONB NOT NULL DEFAULT '[]'::jsonb` with a `jsonb_typeof(...) = 'array'` CHECK; the INSERT guard iterates elements (every element a bounded non-empty string) and **strictly verifies** `required_status_check_count = jsonb_array_length(...)`; direct-SQL rejection tests for non-array, non-string element, empty string, oversized name, and mismatched count added (§8). The DB guard is the **authoritative backstop** because `uaid_app` holds INSERT (precedent: `migrations/versions/0015_readiness_reports.py:68-104`).
**Base:** `main` @ `3ec8116`; working tree is planning-only — intentional `.planning/HANDOFF.json` drift plus untracked Slice-26 discussion/PLAN docs + the approved `.planning/GO-LIVE-END-TO-END-ROADMAP.md`. No implementation files changed.
**Migration head:** `0024` → new head **`0025`** (verified current head is `0024_release_candidates`).
**Persona:** senior release-governance / delivery-platform + Postgres-security engineer.
**Approach:** TDD-first — pure validators + DB-guard refusal tests written and shown failing before the implementation/migration that satisfies them.
**Pattern sources (mirror exactly):**
- **Append-only immutable snapshot** (the model for this slice): `app/models/readiness_report.py`, `migrations/versions/0015_readiness_reports.py` (block-mutation triggers, RLS, SELECT/INSERT-only grants, `clock_timestamp()`).
- **INSERT guard + provenance + safe-metadata audit:** `app/release/findings.py`, `app/models/release_finding.py`, `app/repositories/release_findings.py`, `migrations/versions/0022_release_findings.py`.
- **A5 hook + read endpoint:** `app/release/production_autonomy.py`, `app/repositories/production_autonomy.py`, `app/api/dashboard.py` (Slice 17/19/21).
**Process note (memory `migration-edit-requires-db-drop`):** if `0025` is edited after a first `make test-db`, run `make test-db-drop` before re-running, else `alembic upgrade` is a no-op and stale DDL persists.

> **Required wording correction (per review).** The discussion §1 "Provenance convention" bullet is **superseded** by the precise statement: `release_findings` and `release_issues` use **`source_provenance='caller_supplied_unverified'`** (`app/models/release_finding.py:68-71`, `app/models/release_issue.py:70-73`); `risk_acceptance_records` use **`approver_provenance='caller_supplied_unverified'`** (`app/models/risk_acceptance_record.py:85-89`). Slice 26 introduces a **`provenance`** column (its own name) carrying the same `caller_supplied_unverified` token for cross-store consistency.

---

## 0. Goal & non-goal
- **Goal:** a deterministic, tenant-owned, **immutable append-only** branch-protection evidence store (`branch_protection_snapshots`, migration `0025`) + a minimal latest-only read endpoint, supplying the **first evidence class** for A5 gate #3 and moving gate #3 `no_evidence_source → insufficient_evidence` (context only).
- **Non-goal:** gate #3 must **never pass**; **no connector / no broker call**; **no `connector_verified` row may be written** (schema-reserved only); no `ci_check_results` table (deferred — D-26-1); no secrets/credentialed URLs; no PR/test-oracle evidence; no go-live; no LLM; no change to existing tables.

## 1. Files (create / modify)

| # | File | Action | Mirrors |
|---|---|---|---|
| 1 | `app/release/ci_evidence.py` | **create** (pure validators + constants) | `app/release/findings.py` |
| 2 | `app/models/branch_protection_snapshot.py` | **create** | `app/models/readiness_report.py` |
| 3 | `app/models/__init__.py` | **modify** (register 1 model) | existing |
| 4 | `app/repositories/ci_evidence.py` | **create** | `app/repositories/release_findings.py` (+ `readiness.latest`) |
| 5 | `migrations/versions/0025_ci_evidence.py` | **create** (`down_revision="0024"`) | `0015` + `0022` |
| 6 | `app/release/production_autonomy.py` | **modify** (gate #3 + `slice26.v1`) | current gate #3 |
| 7 | `app/repositories/production_autonomy.py` | **modify** (wire CI-evidence counts) | current |
| 8 | `app/api/dashboard.py` | **modify** (add `GET …/ci_evidence`) | `…/readiness` |
| 9 | `tests/test_ci_evidence.py` | **create** (pure + `db`) | `tests/test_release_findings.py` |
| 10 | `tests/test_production_autonomy.py` | **modify** (gate #3 reason/context + `slice26.v1`) | existing |
| 11 | `tests/test_api.py` | **modify** (`ci_evidence` endpoint + `production_autonomy` ruleset/reason) | existing |
| 12 | `CLAUDE.md` + `README.md` | **modify** | Slice-25 entries |

## 2. Pure module — `app/release/ci_evidence.py` (D-26-1/3/4)

```text
PROVIDERS            = ("github",)                 # GitHub-first allowlist (D-26-4)
PROVENANCES          = ("caller_supplied_unverified", "connector_verified")   # schema enum (D-26-3)
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)   # Slice 26 may write ONLY this
REPO_REF_RE          = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"  # owner/repo slug SHAPE
TOKENISH_RE          = r"(?i)/(gh[opusr]_|github_pat_)"   # GitHub token prefixes in the repo segment (denylist)
MAX_CHECK_NAME_LEN   = 200
REQUIRED_CREATE_FIELDS = ("provider", "repo_ref", "branch",
                          "protection_enabled", "required_pull_request_reviews", "enforce_admins")
```
- `InvalidBranchProtectionSnapshot(ValueError)`.
- `validate_new_snapshot(record)` — fail-closed:
  - required fields present + non-empty; `provider ∈ PROVIDERS`; `branch` non-empty `str`;
  - **`repo_ref` (Blocker-1a, shape):** a `str` that **fully matches `REPO_REF_RE`** (GitHub-first `owner/repo` slug, `re.fullmatch`). The anchored slug pattern **rejects** URLs (`https://github.com/org/repo`), credentialed URLs (`https://token@github.com/org/repo`), SSH URLs (`git@github.com:org/repo.git`), query strings/fragments (`…?token=x`, `…#frag`), embedded whitespace/control chars, and multi-slash paths (`org/repo/extra`) — none can match the slug shape;
  - **`repo_ref` (Blocker-1b, token content):** **must NOT** match `TOKENISH_RE` (`re.search`) — rejects GitHub token prefixes (`ghp_/gho_/ghu_/ghs_/ghr_/github_pat_`) in the repo segment, e.g. `owner/ghp_…`. This is the **separate denylist** the slug shape cannot express (the repo segment legitimately allows `[A-Za-z0-9._-]`). Verified to **accept** legit names like `owner/github-actions`, `owner/ghost`, `owner/repo-ghp`;
  - `protection_enabled`/`required_pull_request_reviews`/`enforce_admins` are **real bools** (reject `0`/`1`/`"true"`);
  - **`required_status_checks` (Blocker-2):** must be a `list`; **every** element a **non-empty `str`** with `1 ≤ len ≤ MAX_CHECK_NAME_LEN` (reject non-list, non-string element, empty string, oversized name);
  - if `provenance` is supplied it **must** be in `WRITABLE_PROVENANCES` (a caller may not assert `connector_verified`);
  - `required_status_check_count` is **derived** server-side from `len(required_status_checks)` (never caller-trusted).
- No I/O; mirrors `app/release/findings.py` validator style (module-level tuples + a single fail-closed validator).

## 3. Model — `app/models/branch_protection_snapshot.py` (D-26-5; mirror `readiness_report.py`)

`BranchProtectionSnapshot`, table `branch_protection_snapshots` — **immutable append-only snapshot**:
`id, tenant_id, project_id, provider, repo_ref, branch, protection_enabled (bool),
required_pull_request_reviews (bool), required_status_checks (JSONB NOT NULL, server_default `'[]'::jsonb`),
required_status_check_count (int), enforce_admins (bool), provenance (text),
observed_at (timestamptz, nullable — caller-asserted), created_at (timestamptz, clock_timestamp())`.
`__table_args__` (mirror `readiness_report.py:37-53`):
- composite FK `(project_id, tenant_id) → projects(id, tenant_id)` RESTRICT, name `project_tenant`;
- direct FK `tenant_id → tenants.id` RESTRICT;
- `CheckConstraint("provenance IN ('caller_supplied_unverified','connector_verified')")` (**both** enum values — reserves the verified tier; the **write restriction is the INSERT guard**, §4.1);
- `CheckConstraint("provider IN ('github')")`;
- `CheckConstraint("required_status_check_count >= 0")`;
- **`CheckConstraint("repo_ref ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$'", name="ck_bps_repo_ref_slug")`** (Blocker-1a DB backstop — same slug **shape** as `REPO_REF_RE`; a scalar regex, valid in a CHECK);
- **`CheckConstraint("repo_ref !~* '/(gh[opusr]_|github_pat_)'", name="ck_bps_repo_ref_not_tokenish")`** (Blocker-1b DB backstop — **token-prefix denylist**, the POSIX equivalent of `TOKENISH_RE`; `!~*` = case-insensitive not-match);
- **`CheckConstraint("jsonb_typeof(required_status_checks) = 'array'", name="ck_bps_checks_array")`** (Blocker-2 DB backstop — array shape; per-element + count strict-verify live in the §4.1 guard, which iteration requires);
- `Index("ix_branch_protection_snapshots_tenant_project_created", "tenant_id","project_id","created_at")`.
`app/models/__init__.py` — import + export `BranchProtectionSnapshot`.

> **No events table, no status column, no UPDATE path** — a snapshot is immutable; "newest wins" by `created_at DESC, id DESC` (the `readiness_reports` precedent, **not** the `release_findings` lifecycle precedent — D-26-5).

## 4. Migration — `migrations/versions/0025_ci_evidence.py` (D-26-5; mirror `0015` + `0022` guard)

`revision="0025"`, `down_revision="0024"`. One table exactly as §3 + `_PREDICATE` identical to `0015:25`.
Grants: **`GRANT SELECT, INSERT`** to `uaid_app`; **`REVOKE UPDATE, DELETE, TRUNCATE`** (snapshots are immutable — **no UPDATE grant**, unlike the lifecycle stores). ENABLE+FORCE RLS + `tenant_isolation`.

### 4.1 `branch_protection_snapshots_guard()` BEFORE INSERT (authoritative DB backstop — `uaid_app` holds INSERT)
- **Provenance:** `NEW.provenance = 'caller_supplied_unverified'` else raise — reject `connector_verified` (the verified tier is schema-reserved but **unwritable** this slice; Slice 28 relaxes this guard). Crux of D-26-2/D-26-3.
- **`repo_ref` safe shape (Blocker-1a):** `NEW.repo_ref ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$'` else raise (defense-in-depth with the column CHECK — rejects URLs / credentialed URLs / SSH URLs / query strings / fragments / whitespace / control chars / multi-slash).
- **`repo_ref` token denylist (Blocker-1b):** `NEW.repo_ref !~* '/(gh[opusr]_|github_pat_)'` else raise (rejects GitHub token prefixes in the repo segment — defense-in-depth with the `ck_bps_repo_ref_not_tokenish` CHECK).
- **`required_status_checks` shape (Blocker-2):**
  - `jsonb_typeof(NEW.required_status_checks) = 'array'` else raise (also a column CHECK);
  - for **every** `elem` in `jsonb_array_elements(NEW.required_status_checks)`: `jsonb_typeof(elem) = 'string'` **and** `char_length(elem #>> '{}') BETWEEN 1 AND 200` else raise (reject non-string, empty, oversized element);
  - **count strict-verify:** `NEW.required_status_check_count = jsonb_array_length(NEW.required_status_checks)` else raise (a raw-SQL count mismatch is **rejected**; the repo always supplies a derived, consistent count).
- (provider, `required_status_check_count >= 0`, the provenance enum, the array-shape, and the `repo_ref` slug are **also** column CHECKs; the trigger adds the per-element + count-equality invariants that a scalar CHECK cannot express.)

### 4.2 Append-only block triggers (mirror `0015:68-92`)
`branch_protection_snapshots_block_mutation()` → `BEFORE UPDATE OR DELETE` (row) + `BEFORE TRUNCATE` (statement) raise "append-only (no UPDATE/DELETE/TRUNCATE)".

`downgrade()` drops triggers/functions/index/table + RLS in reverse (mirror `0015:107-118`).

## 5. Repository — `app/repositories/ci_evidence.py` (D-26-5/6; mirror `release_findings` + `readiness.latest`)

`CIEvidenceRepository(TenantScopedRepository)`:
- `record_branch_protection(*, project_id, payload, actor)` → `validate_new_snapshot`; **stamp `provenance='caller_supplied_unverified'`** (repo-controlled, never caller-controlled); derive `required_status_check_count`; INSERT; `_audit("ci.branch_protection_observed", …)`. **No `_event`** (snapshots are the log).
- `latest_branch_protection(project_id)` → first row ordered **`created_at DESC, id DESC`** (mirror `ReadinessRepository.latest`) or `None`.
- **A5 count helpers:** `count_branch_protection_snapshots(project_id)`; `count_connector_verified_branch_protection(project_id)` (`provenance='connector_verified'` ⇒ **0** this slice — proves the verified tier is unwritten).
- **Audit safe-metadata only:** `snapshot_id, project_id, provider, branch, protection_enabled, required_status_check_count, provenance` — **never** `repo_ref`, the `required_status_checks` name list, or any URL/token (conservative, mirrors Slice 23/24 audit discipline).

## 6. A5 hook (D-26-6)

### 6.1 `app/release/production_autonomy.py`
- `A5_RULESET_VERSION`: `slice25.v1` → **`slice26.v1`** (+ docstring update: gate #3 now `insufficient_evidence`, partial-context).
- `evaluate_production_autonomy(...)` gains kwargs (defaults **fail-closed**): `branch_protection_snapshot_count=0`, `connector_verified_branch_protection_count=0`, `latest_branch_protection_provenance=None`, `latest_branch_protection_enabled=None`, `latest_required_status_check_count=0`.
- Gate #3 changes from `_no_source(3, …, "ci_branch_protection")` to:
  ```python
  gate3_reason = ("no_branch_protection_evidence" if branch_protection_snapshot_count == 0
                  else "branch_protection_observed_unverified")
  gate3 = _insufficient(3, "branch_protection_and_required_checks_active", gate3_reason, {
      "branch_protection_snapshot_count": branch_protection_snapshot_count,
      "connector_verified_branch_protection_count": connector_verified_branch_protection_count,
      "latest_branch_protection_provenance": latest_branch_protection_provenance,
      "latest_branch_protection_enabled": latest_branch_protection_enabled,  # observed, UNVERIFIED
      "latest_required_status_check_count": latest_required_status_check_count,
  })
  ```
  Status stays **`insufficient_evidence`** — **gate #3 never passes** (no PASS path exists; the PASS logic is Slice 28). `latest_branch_protection_enabled` is **context only** — never flips the gate.
- Gate-set move: gate #3 leaves `SOURCELESS {3,4,10,11,13}` → `{4,10,11,13}`; joins `PARTIAL {2,5,6,7,8,9,12}` → `{2,3,5,6,7,8,9,12}`. `passed_gate_count` stays **1** at R5; `unmet_gates` stays **12**. `can_go_live_autonomously`/`a5_satisfied` unchanged (false).

### 6.2 `app/repositories/production_autonomy.py`
- Instantiate `CIEvidenceRepository`; compute `count_branch_protection_snapshots`, `count_connector_verified_branch_protection`, and (if a `latest_branch_protection` exists) its `provenance`/`protection_enabled`/`required_status_check_count`; pass all into `evaluate_production_autonomy`. Reads only `branch_protection_snapshots`. (Compute-on-read, no persistence — unchanged Slice-21 contract.)

## 7. Read endpoint (D-26-5) — `app/api/dashboard.py`

Add `GET /api/projects/{project_id}/ci_evidence` (mirror `…/readiness`): `require_tenant → tenant_scope`/RLS; returns `{"ci_evidence": _ci_evidence_dict(rec) | None}` from `CIEvidenceRepository.latest_branch_protection`. **Latest-or-null only** (no list/history endpoint — D-26-5). `_ci_evidence_dict`: `snapshot_id, observed_at, provider, repo_ref, branch, protection_enabled, required_pull_request_reviews, required_status_checks, required_status_check_count, enforce_admins, provenance`. Cross-tenant/nonexistent ⇒ `null` (no existence oracle, no leak). GET-only.

## 8. Tests — TDD-first

### 8.1 `tests/test_ci_evidence.py`
**Pure (Docker-free):** `validate_new_snapshot` — missing/empty required field ⇒ raise; bad `provider` ⇒ raise; non-bool flag ⇒ raise; caller-supplied `provenance='connector_verified'` ⇒ raise; happy path (`repo_ref="owner/repo"`, `required_status_checks=["ci/build","ci/test"]`) passes; constants (`PROVIDERS`, `PROVENANCES`, `WRITABLE_PROVENANCES`, `REPO_REF_RE`, `MAX_CHECK_NAME_LEN`).
- **`repo_ref` shape rejections (Blocker-1a):** `https://github.com/org/repo`, `https://token@github.com/org/repo`, `git@github.com:org/repo.git`, `https://github.com/org/repo?token=x`, `org/repo#frag`, `org/repo/extra` (multi-slash), `" org/repo"` / `"org/repo "` (whitespace), `"org/repo\n"` (control char), `""` (empty) ⇒ each raise.
- **`repo_ref` token-content rejections (Blocker-1b):** `owner/ghp_abcdefghijklmnopqrstuvwxyz123456`, `owner/github_pat_11ABCDEFG0…`, `owner/gho_…`, `owner/ghu_…`, `owner/ghs_…`, `owner/ghr_…` ⇒ each raise.
- **`repo_ref` accepts (no false positives):** `"owner/repo"`, `"Org-1/repo.name_2"`, `"owner/my_repo"`, `"owner/github-actions"`, `"owner/ghost"`, `"owner/repo-ghp"` ⇒ pass.
- **`required_status_checks` rejections (Blocker-2):** not a `list` (`{}`/`"x"`/`None`); list with a non-string element (`["ci",1]`); list with an empty string (`[""]`); list with an oversized name (`["x"*201]`) ⇒ each raise; `[]` and `["ci/build"]` ⇒ pass.

**DB-backed (`@pytest.mark.db`):**
1. `record_branch_protection` happy path → row stored with `provenance='caller_supplied_unverified'`, `required_status_check_count == len(checks)`, `created_at` set; `latest_branch_protection` returns it; audit row present.
2. **audit safe-metadata** — payload has ids/provider/branch/booleans/count/provenance; **no `repo_ref`, no check-name list, no URL/token**.
3. **RLS / cross-tenant** — tenant B cannot read tenant-A snapshots; cross-tenant `project_id` ⇒ `latest` `None`.
4. **DB-guard refusals (direct SQL — authoritative backstop, `uaid_app` holds INSERT):**
   - INSERT `provenance='connector_verified'` ⇒ raise (verified tier unwritable);
   - `provider` not in CHECK set ⇒ raise; `required_status_check_count < 0` ⇒ raise;
   - **Blocker-1a `repo_ref` shape:** INSERT with `repo_ref` = a URL (`https://github.com/org/repo`), credentialed URL (`https://token@github.com/org/repo`), SSH URL (`git@github.com:org/repo.git`), query-string (`org/repo?token=x`), or multi-slash (`org/repo/extra`) ⇒ each raise (`ck_bps_repo_ref_slug` + guard);
   - **Blocker-1b `repo_ref` token content:** INSERT with `repo_ref` = `owner/ghp_…` / `owner/github_pat_…` / `owner/gho_…` ⇒ each raise (`ck_bps_repo_ref_not_tokenish` + guard); `owner/github-actions` ⇒ **accepted** (no false positive);
   - **Blocker-2 `required_status_checks`:** INSERT with a **non-array** JSON (`'"x"'::jsonb`, `'{"a":1}'::jsonb`) ⇒ raise (array CHECK); array with a **non-string** element (`'[1]'::jsonb`) ⇒ raise (guard); array with an **empty string** (`'[""]'::jsonb`) ⇒ raise (guard); array with an **oversized** name (`> 200` chars) ⇒ raise (guard); `required_status_check_count` **≠ `jsonb_array_length`** ⇒ raise (guard strict-verify).
5. **Append-only:** UPDATE / DELETE / TRUNCATE `branch_protection_snapshots` ⇒ raise.
6. **FK:** insert with cross-project / cross-tenant `(project_id, tenant_id)` ⇒ raise.
7. **catalog/grants/RLS:** grants = `{SELECT, INSERT}` (no UPDATE/DELETE); `relrowsecurity`+`relforcerowsecurity` true; CHECKs present via `pg_constraint`.

### 8.2 `tests/test_production_autonomy.py` (modify)
- Pure: `branch_protection_snapshot_count=0` ⇒ gate #3 reason `no_branch_protection_evidence`; `>0` ⇒ `branch_protection_observed_unverified`; **both `insufficient_evidence`, gate #3 in unmet set, never `passed`** (even with `latest_branch_protection_enabled=True` + a hypothetical `connector_verified_branch_protection_count>0` — still insufficient, since no PASS path). Context carries the 5 new keys.
- Gate-set: `3 ∈ PARTIAL`, `3 ∉ SOURCELESS`; `passed_gate_count==1` at R5; `unmet_gates` count 12. `ruleset_version == "slice26.v1"`.
- DB: `test_db_gate3_reads_branch_protection_counts` — seed a snapshot; assert reason `branch_protection_observed_unverified`, context counts match, still never passes, go-live false.
- Unchanged: only gate #1 can pass; go-live always false; compute-on-read.

### 8.3 `tests/test_api.py` (modify)
- New `GET …/ci_evidence`: returns latest snapshot dict after a seeded insert; `null` when none / cross-tenant; `401` without bearer; `405` on POST.
- `…/production_autonomy`: `ruleset_version == "slice26.v1"`; gate #3 reason matches fixture state (no snapshot seeded ⇒ `no_branch_protection_evidence`) + the 5 context keys present. (Existing auth/cross-tenant/read-only assertions unchanged.)

## 9. Docs (D-26-7)
- `CLAUDE.md`: add the `branch_protection_snapshots` What-exists entry + `0025` migrations entry; update the production-autonomy bullet (gate #3 now `insufficient_evidence`, `PARTIAL={2,3,5,6,7,8,9,12}`/`SOURCELESS={4,10,11,13}`, `slice26.v1`); status line "Slice 26 … In progress."; test-files list (+`test_ci_evidence.py`); test counts from **actual** `make test`/`make test-db` output (no invented numbers — §2.1).
- `README.md`: add a "Source-control / CI evidence (branch protection)" section; update the production-autonomy gate #3 wording + `slice26.v1`.

## 10. Acceptance criteria (evidence-decided)
- `make fmt` / `ruff check .` clean (format only my files).
- `make test` (Docker-free) green incl. new pure tests; `make test-db` green incl. all §8.1 guard refusals + §8.2/§8.3 changes (run on a **fresh** DB — `make test-db-drop` first since `0025` is new/edited).
- `alembic upgrade head → downgrade -1 → upgrade head` round-trips cleanly (`0025` reversible).
- Gate #3 demonstrably **never passes**; reason narrows `no_branch_protection_evidence → branch_protection_observed_unverified` only when ≥1 snapshot exists; `connector_verified_branch_protection_count` is 0; `can_go_live_autonomously` false everywhere.
- **No `connector_verified` row can be written** (guard refusal test green); no change to existing tables.
- **`repo_ref` (slug shape + token denylist) and `required_status_checks` shape are DB-enforced:** the §8 Blocker-1a/1b/2 direct-SQL rejection tests are green — validator, column CHECKs (`ck_bps_repo_ref_slug`, `ck_bps_repo_ref_not_tokenish`, `ck_bps_checks_array`), and INSERT guard agree, so an unsafe or token-looking value cannot enter even via raw SQL on the `uaid_app` INSERT privilege.
- Record actual passing test counts in `CLAUDE.md` from real output.

## 11. Risk / reversibility
- **Additive only** — one migration, one new table, two new Python modules (+ one model), three modified modules (`production_autonomy` ×2 + `dashboard`) + tests + docs. `downgrade()` fully drops the slice; no existing table altered.
- **Blast radius:** the only change to an existing surface is gate #3's `status`/`reason`/`context` + `ruleset_version` on the read-only `…/production_autonomy` endpoint (now `insufficient_evidence` instead of `no_evidence_source` — still not-satisfied, still no go-live; consumers keying on the gate `status` see `insufficient_evidence`). Plus one **new** read endpoint.
- **Honesty preserved:** observed ≠ verified; gate #3 stays fail-closed and never passes; the verified tier is schema-reserved but DB-unwritable.

## 12. Notes for the coordinator (non-blocking)
- `connector_verified_branch_protection_count` is surfaced (always 0 this slice) **on purpose** — it makes the "verified tier is empty" fact explicit in the A5 report rather than implicit.
- `latest_branch_protection_enabled` is included as **observed, unverified** context; a future reviewer reading the report must not treat it as an assertion that protection is on (the reason string `branch_protection_observed_unverified` makes this explicit).
- `repo_ref` is returned on the tenant's **own** dashboard read (their data) but **excluded from the audit log** (conservative) — same split the existing stores use (API returns tenant rows; audit stays safe-metadata only).

---
**Awaiting PLAN approval. On approval:** branch `feat/slice26-ci-evidence` off `main`, execute TDD-first in §1 order (tests → pure → model → migration → repo → A5 hook → read endpoint → docs), atomic commits per `github-flow`. **No implementation — no branch, code, migration, or tests — begins until this PLAN is separately approved.**
