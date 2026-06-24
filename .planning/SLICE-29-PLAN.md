# Slice 29 — Pull-request evidence connector — PLAN v3

**Status:** ✅ **APPROVED (v3)** by coordinator review 2026-06-24 (v1 REJECTED → v2 REJECTED → v3 APPROVED). **Implementation is a SEPARATE step — gated on explicit authorization; no branch / no code / no migration / no tests started yet.**
**Persona:** senior release-governance / connector-security / evidence-model architect.
**Base:** `main` @ `9e23868` ("docs: mark Slice 28 merged (#46)"). This plan adds `.planning/SLICE-29-{PR-EVIDENCE-DISCUSSION,PLAN}.md`.
**Migration head:** `0027_connector_verified_evidence` (verified) → new head **`0028`**. *(Roadmap's `0027` at `:226` is stale.)*
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:221-231`. **Discussion (Q1–Q6 locked):** `.planning/SLICE-29-PR-EVIDENCE-DISCUSSION.md`.

> **Revision log — v2 → v3 (both accepted after verifying the cited anchors):**
> - **B-29-7 — Review/requested-reviewer endpoints were fail-open.** v2 lumped reviews with checks ("else `check_status_summary=None`"), so a failed reviews fetch would silently yield an empty approver set — dishonest, since review approvals are core to `connector_verified` (roadmap `:221-230`; §12.4 `:1209-1224`). v3 **splits endpoint mandatoriness** (§4): PR + **reviews** are MANDATORY (non-200/malformed ⇒ `SCMConnectorError` ⇒ **no verified snapshot**); requested-reviewers is **explicitly observed** (`requested_reviewers_observed` bool — failure ⇒ `false` + empty list, never a silent empty); checks/status stay optional observed-only (unavailable ⇒ `check_status_summary=None`).
> - **B-29-8 — DB backstop didn't enforce derived invariants.** v2 declared `approval_count = len(approver_principals)` + "DB guard is authoritative" but the guard/tests didn't enforce/test it at the DB layer (precedent `0025:127-129` enforces `required_status_check_count = jsonb_array_length(...)` in-trigger). v3 **adds DB-guard rules** (§2): `approval_count = jsonb_array_length(approver_principals)`; `check_status_summary IS NULL OR jsonb_typeof = 'object'`; when non-null — allowed state keys only, non-negative integer counts, `combined_state` absent/null or in-enum. Direct-SQL tests for each (§9).
>
> **Revision log — v1 → v2 (each line is a strict-review blocker; all accepted after verifying the cited anchors):**
> - **B-29-1 — Required-check evidence underspecified.** v1 listed only pulls/reviews/requested_reviewers endpoints but the schema carried `required_check_summary` (no source). v2: (a) **add a check-runs + combined-status fetch for the PR head SHA**, and (b) **rename the field `check_status_summary`** (observed counts by state) and **state plainly that required-check *satisfaction* is NOT determined in Slice 29**. Check evidence unavailable ⇒ `check_status_summary = NULL` (honest "not observed"), the PR snapshot still writes (PR/review facts are independently valid); a fabricated "checks passed" is never written. (§12.4 `:1224`; roadmap `:221-230`.)
> - **B-29-2 — `merged_via_protected_branch` overclaimed.** base-ref + merged-flag does not prove the branch was protected. v2: field renamed **`merged_to_declared_protected_branch_observed`** (bool, default false) with a defined source rule (§2) — true **only** when merged AND base == the project's declared protected branch AND a **connector_verified + protection_enabled + fresh** branch-protection snapshot exists for that same repo/branch (cross-ref the Slice-28 store via `latest_branch_protection_for_repo`). (Precedent `branch_protection_snapshot.py:1-12`.)
> - **B-29-3 — Traceability refs lacked same-project/kind integrity.** Q5 chose JSONB, so app validation is the only boundary, and pure validation only checks UUID shape. v2: **repository write-time validation** — `release_issue_ids` must resolve via `ReleaseIssueRepository.get` (same tenant/project); `acceptance_criterion_ids` must resolve via `IntakeRepository.get_artifact` with `kind=='acceptance_criterion'` and matching `project_id`; **wrong-project / missing / wrong-kind / duplicate ⇒ fail closed**. (Grounding `intake_artifact.py:81-82`, `repositories/intake.py:99-111`, `repositories/release_issues.py:81`.)
> - **B-29-4 — Connector service interface mismatch.** v1's `refresh_pull_request_evidence(...)` had no params for the caller-supplied `presence_flags`/`traceability_refs` it claimed to write. v2: **add explicit optional `presence_flags` / `traceability_refs` params**; each presence flag keeps its `source` label (`caller_declared` stays `caller_declared`). **Invariant:** a `connector_verified` snapshot **must not** promote `caller_declared` §12.4 flags into provider-verified adequacy; Q2 source labels remain visible per-flag in the row.
> - **B-29-5 — Duplicate approval-count fields.** v1 had both `review_approval_count` and `approval_count` (can diverge). v2: **one canonical `approval_count`**, derived from the normalized set of approving principals (B-29-6). `review_approval_count` removed.
> - **B-29-6 — Effective-approval semantics.** v1 said "review state == APPROVED" with no latest/dismissed handling. v2: `approver_principals` = the reviewers whose **latest non-dismissed** review state is `APPROVED` (dedup per principal, latest-wins); `approval_count = len(approver_principals)`. **Must not claim "required reviewers approved."**

> **Provenance (Sanad).** Precedents read this session: `scm_connector.py:1-124`, `ci_evidence_service.py:1-104`, `project_repo.py:1-72`, `repositories/ci_evidence.py:1-166` (incl. `latest_branch_protection_for_repo:104-129`), `release/ci_evidence.py:1-142`, `branch_protection_snapshot.py:1-97`, `production_autonomy.py:240-281`; `registry.py:54-60`, `matrix.py:40`, `config.py:27-28`; `intake_artifact.py:47-90`, `repositories/intake.py:99-111`, `repositories/release_issues.py:81`. Spec §2.2 (`:151-157`), §12.3 (`:1184-1207`), §12.4 (`:1209-1224`). Re-verify `0025_ci_evidence.py` DDL before authoring `0028`.

---

## 0. Goal & non-goal
- **Goal.** A **GitHub-first, broker-mediated** connector that fetches a pull request (+ its reviews, requested reviewers, **and head-SHA check/status**) for **the project's own declared repo**, verifies it, and writes an immutable **`connector_verified`** `pull_request_evidence_snapshots` row: provider PR facts; **observed** check-status summary (not required-satisfaction); §12.4 **presence** flags (per-flag `source` label preserved); normalized review/identity facts + **structural-only** separation-of-duties flags (Q3); an **observed** merged-to-declared-protected-branch flag (cross-referenced, not asserted); and **repository-validated** bounded `traceability_refs`. Latest-wins per `(tenant, project, provider, repo_ref, pr_number)`.
- **Non-goal.** **No A5 gate flip; no `production_autonomy.py` edit; no ruleset bump (stays `slice28.v1`)** (Q6). No acceptance verification / adequacy scoring; **no required-check-satisfaction determination; no "required reviewers approved" claim** (Slice 46). No enforcement of §2.2/§12.3. No PR body/diff/prose storage; no semantic parsing; no LLM. GitHub only. **No HTTP endpoint** (D-29-7). No raw `repo_ref`/token in broker params or audit. No real network in tests.

## 1. Files (create / modify)
| # | File | Action |
|---|---|---|
| 1 | `app/release/pr_evidence.py` | **create** — pure validators + `normalize_approvals(...)` + `derive_separation_flags(...)` |
| 2 | `app/release/scm_connector.py` | **modify (extend)** — `fetch_pull_request(...)` on protocol + Fake + GitHub; pure `map_github_pull_request(...)` (PR+reviews+requested+**checks**) |
| 3 | `app/release/pr_evidence_service.py` | **create** — `refresh_pull_request_evidence(...)` with optional `presence_flags`/`traceability_refs` params (B-29-4) |
| 4 | `app/release/project_repo.py` | **REUSE, no change** (D-29-3) |
| 5 | `app/models/pull_request_evidence_snapshot.py` | **create** — `PullRequestEvidenceSnapshot` / table `pull_request_evidence_snapshots` |
| 6 | `app/repositories/pr_evidence.py` | **create** — write paths + **traceability ref validation** (B-29-3) + **merged-protected cross-ref** (B-29-2) + `latest_pull_request_for_pr` + counts + safe audit |
| 7 | `app/tools/registry.py` | **modify** — add `source_control.read_pull_request` (read, no approval) |
| 8 | `app/policy/matrix.py` | **modify** — add `read_pull_requests: _r(L.A1)` |
| 9 | `migrations/versions/0028_pull_request_evidence.py` | **create** — new table + RLS + grants + append-only + guard; **additive** |
| 10 | `app/config.py` | **REUSE, no change** (`github_connector_token` + `ci_evidence_max_age_hours=24` exist) |
| 11 | `app/release/production_autonomy.py` + repo | **NOT TOUCHED** (Q6) |
| 12 | `tests/test_pr_evidence.py` | **create** — full matrix (§9) |
| 13 | `CLAUDE.md` + roadmap status banner | **modify** |

## 2. Schema — `pull_request_evidence_snapshots` (Q4; mirror `branch_protection_snapshot.py`)
Tenant-owned, RLS ENABLE+FORCE + `tenant_isolation`; **SELECT/INSERT only**, UPDATE/DELETE/TRUNCATE blocked; composite FK `(project_id, tenant_id) → projects`; `created_at DEFAULT clock_timestamp()`.

- **Identity/binding:** `id`, `tenant_id`, `project_id`, `provider` (CHECK `IN ('github')`), `repo_ref` (`ck_pres_repo_ref_slug` = `REPO_REF_RE` + `ck_pres_repo_ref_not_tokenish` = `TOKENISH_RE`), `pr_number` (Integer CHECK `> 0`).
- **Provider PR facts (Q2):** `pr_state` (CHECK `IN ('open','closed','merged')`), `merged` (bool), `merged_at` (tz null), `merge_commit_sha` (text null, CHECK `^[0-9a-f]{7,64}$` or NULL), `base_branch`, `base_sha`, `head_branch`, `head_sha` (hex bounded).
- **Observed check status (B-29-1):** `check_status_summary` (**JSONB, NULLABLE**) — counts by observed state `{success, failure, pending, neutral, error, unknown}` + optional `combined_state ∈ {success, failure, pending}`; **observed only — NOT required-check satisfaction.** NULL ⇒ check evidence not observed (never fabricated).
- **Observed merged-protected (B-29-2):** `merged_to_declared_protected_branch_observed` (bool, default false) — set by the repository per the §6 cross-ref rule; **observed, not asserted.**
- **§12.4 presence (Q2, B-29-4):** `presence_flags` (JSONB NOT NULL DEFAULT `'{}'`) — keys ⊆ the 10 §12.4 items; each `{present:bool, source:'caller_declared'|'connector_observed_template', observed_marker?:bounded-str}`. Per-flag `source` is authoritative and **never rewritten to imply provider adequacy**.
- **Normalized identity facts (Q3, B-29-5/6/7):** `author_principal` (text null), `approver_principals` (JSONB array — latest-non-dismissed-APPROVED, deduped), `reviewer_principals` (JSONB array of `{principal, latest_state}`, deduped latest-wins), `requested_reviewer_principals` (JSONB array), **`requested_reviewers_observed` (bool, default false — B-29-7: `true` only when that endpoint was fetched; on failure `false` + empty array, never a silent empty list)**, `merger_principal` (text null), `approval_count` (Integer CHECK ≥ 0 — **= `jsonb_array_length(approver_principals)`**, single canonical count, DB-enforced).
- **Derived structural flags (Q3, write-time, frozen — D-29-8):** `self_approval_observed`, `self_merge_observed`, `review_separation_observed` (bools).
- **Traceability (Q5, B-29-3):** `traceability_refs` (JSONB NOT NULL DEFAULT `'{}'`) — `{release_issue_ids:[uuid], acceptance_criterion_ids:[uuid], provider_refs:{...}}`, **repository-validated** (same-project/kind/no-dup); **refs only**, no FK.
- **Provenance/freshness:** `provenance` (CHECK two-tier, DEFAULT unverified), `observed_at` (tz null; connector sets), `created_at` (`clock_timestamp()`).
- **Index:** `ix_pres_tenant_project_pr_created` on `(tenant_id, project_id, provider, repo_ref, pr_number, created_at)`.

**DB guard trigger** (BEFORE INSERT, mirror `0025`): `repo_ref` slug + token denylist; `pr_number > 0`; enum CHECKs; `presence_flags`/`traceability_refs` are JSON objects, principal fields JSON arrays, bounded element strings; **provenance repo-controlled**. **Derived-invariant rules (B-29-8, mirroring `0025:127-129`):** (a) `approval_count = jsonb_array_length(approver_principals)` — RAISE on mismatch; (b) `check_status_summary IS NULL OR jsonb_typeof(check_status_summary) = 'object'`; (c) when non-null — keys ⊆ `{success,failure,pending,neutral,error,unknown,combined_state}`, each count is a non-negative integer, and `combined_state` is absent/NULL or ∈ `{success,failure,pending}`. UPDATE/DELETE/TRUNCATE block triggers (append-only). DB guard = authoritative backstop; app validators = defense-in-depth.

## 3. Pure validators — `app/release/pr_evidence.py`
- **Import** `REPO_REF_RE`, `TOKENISH_RE` from `app.release.ci_evidence` (single source).
- `PROVIDERS`, two-tier provenance sets; `PR_STATES`; `PRESENCE_ITEMS` (the 10 §12.4 keys); `PRESENCE_SOURCES`; `CHECK_STATES`.
- `validate_presence_flags`, `validate_check_status_summary` (nullable; counts ≥ 0; states ⊆ `CHECK_STATES`), `validate_principal_lists`, **`validate_traceability_refs_shape`** (UUID-shape + bounded arrays only — **existence/kind is the repository's job**, B-29-3; a free-form `urls[]` is accepted only as a bounded *untrusted* list, never gate-grade).
- `_validate_pr_shape`, `validate_new_pull_request` (caller path; rejects `connector_verified`), `validate_connector_pull_request` (connector path; requires `connector_verified` + `observed_at`).
- **`normalize_approvals(reviews) -> (approver_principals, reviewer_principals, approval_count)`** (B-29-5/6) — pure: group by principal, take the **latest non-dismissed** review state per principal; `approver_principals` = those whose latest non-dismissed state is `APPROVED`; `approval_count = len(approver_principals)`; dismissed/`CHANGES_REQUESTED`-after-`APPROVED`/`COMMENTED` handled. Docstring states it does NOT claim "required reviewers approved."
- **`derive_separation_flags(*, author_principal, approver_principals, merger_principal)`** (Q3) — pure equality over provider principals; docstring caveat: provider-principal equality, NOT a UAID-actor separation.

## 4. Connector — extend `app/release/scm_connector.py` (B-29-1 / B-29-7)
**Endpoint mandatoriness is explicit (B-29-7) — review facts cannot silently degrade:**
| Endpoint | Status | On non-200/malformed |
|---|---|---|
| `GET /repos/{o}/{r}/pulls/{n}` | **MANDATORY** | `SCMConnectorError` ⇒ **no verified snapshot** |
| `GET …/pulls/{n}/reviews` | **MANDATORY** (review facts are core to `connector_verified`) | `SCMConnectorError` ⇒ **no verified snapshot** |
| `GET …/pulls/{n}/requested_reviewers` | **OBSERVED** | `requested_reviewers_observed=false` + empty list (no silent empty); snapshot still writes |
| `GET …/commits/{head_sha}/check-runs` + `…/status` | **OPTIONAL observed-only** | `check_status_summary=None`; snapshot still writes |

- Protocol: `async def fetch_pull_request(self, *, repo_ref, pr_number) -> dict | None`.
- `map_github_pull_request(pull, reviews, *, requested_reviewers=None, requested_reviewers_observed=False, checks=None, combined_status=None) -> dict` (pure) — `pull` + `reviews` are **required args** (missing/malformed ⇒ `SCMConnectorError`); `reviews` → `normalize_approvals`; `requested_reviewers` honored only when `requested_reviewers_observed=True`; head-SHA checks → `check_status_summary` counts or `None`. **No token/URL/body/diff in the result.**
- `FakeSCMConnector.fetch_pull_request` (canned / None / raise — no network).
- `GitHubSCMConnector.fetch_pull_request` (**never tested**; lazy `httpx`; **PR and reviews calls must `200`** else `SCMConnectorError`; requested-reviewers failure ⇒ `observed=false`; checks failure ⇒ `check_status_summary=None`; token never logged). Min permission: PRs:read + Checks/Statuses:read.

## 5. Orchestration — `app/release/pr_evidence_service.py` (B-29-4)
```
refresh_pull_request_evidence(session, context, *, project_id, pr_number, agent_id, actor,
                              connector, presence_flags=None, traceability_refs=None) -> RefreshResult
```
1. **Resolve project's OWN repo** via shared `resolve_declared_repo` + `has_declared_credential` (D-29-3); undeclared/malformed ⇒ audited `repo_unbound`/`credential_unbound`, no write.
2. **Broker — SAFE params only:** `tool_name="source_control.read_pull_request"`, `params={"provider":"github","pr_number":pr_number,"repo_ref_present":True}` — **`repo_ref` never in params/audit** (D-29-3). Non-ALLOW ⇒ no write.
3. **Fetch** (Fake in tests). `SCMConnectorError`/`None` ⇒ audited failure, no write (fail-closed).
4. **Write** `connector_verified` snapshot via the repo, passing `repo_ref`/`pr_number` from the declaration (not params), `observed_at=now`, the optional caller-supplied `presence_flags`/`traceability_refs` (validated; **`caller_declared` source preserved**, B-29-4). Admin/internal — no HTTP endpoint (D-29-7).

## 6. Repository — `app/repositories/pr_evidence.py`
`PullRequestEvidenceRepository(TenantScopedRepository)`:
- `record_pull_request(...)` — caller path; `validate_new_pull_request`; stamps unverified.
- `record_connector_verified_pull_request(...)` — connector path; `validate_connector_pull_request`; stamps `connector_verified`; derives Q3 flags write-time.
- **`_validate_traceability_refs(project_id, refs)` (B-29-3)** — for each `release_issue_id`: `ReleaseIssueRepository(self.session, self.context).get(id)` is not None (tenant-scoped) AND `.project_id == project_id`; for each `acceptance_criterion_id`: `IntakeRepository(...).get_artifact(id)` is not None AND `.kind == 'acceptance_criterion'` AND `.project_id == project_id`; **reject duplicates / missing / wrong-kind / wrong-project (fail closed)** before the row is added.
- **`_compute_merged_protected(project_id, *, merged, base_branch, repo_ref)` (B-29-2)** — true iff `merged` AND `base_branch == declared protected branch` AND `CIEvidenceRepository(...).latest_branch_protection_for_repo(project_id, repo_ref, base_branch)` is `connector_verified` AND `protection_enabled` AND **fresh** (`observed_at` within `ci_evidence_max_age_hours`); else false. (Reuses the Slice-28 store + freshness convention.)
- `latest_pull_request_for_pr(project_id, provider, repo_ref, pr_number)` (latest-wins) / `latest_pull_request(project_id)` / counts.
- `_audit` — **safe metadata only**: ids / provider / `pr_number` / `pr_state` / `merged` / provenance / the three derived flags / `approval_count`. **NEVER** repo_ref / principals' tokens / body / diff / URLs / check-names / titles / traceability UUIDs.

## 7. Broker + policy wiring
- `registry.py`: `"source_control.read_pull_request": _c("source_control.read_pull_request", "source_control", "read_pull_requests")` — read, `requires_approval=False` (mirrors `read_branch_protection`, `registry.py:54-60`).
- `matrix.py`: `"read_pull_requests": _r(L.A1)` — dedicated A1 read (least-privilege). Broker stays decision-only; connector executes on `ALLOWED_UNVERIFIED_IDENTITY`.

## 8. Open decisions — all explicit
- **D-29-1 Connector source:** GitHub only — pulls + reviews + requested_reviewers **+ head-SHA check-runs/status** (B-29-1), with **explicit endpoint mandatoriness** (B-29-7): PR + reviews mandatory (fail-closed), requested-reviewers observed, checks optional. *(updated.)*
- **D-29-2 Broker path:** `source_control.read_pull_request` → new A1 `read_pull_requests`; decision-only. *(ruled.)*
- **D-29-3 Repo binding:** project-declared repo/branch only; no caller `repo_ref`; `pr_number` caller-supplied against the bound repo. *(ruled.)*
- **D-29-4 Freshness:** `ci_evidence_max_age_hours=24` is **used** for the merged-protected branch-protection cross-ref (B-29-2); still **no A5 gate consumer** (Q6). *(updated.)*
- **D-29-5 Traceability storage:** bounded `traceability_refs JSONB` + **repository existence/kind/project validation** (B-29-3). *(ruled Q5 + tightened.)*
- **D-29-6 Gate wiring:** store-only; no `production_autonomy.py` edit; ruleset `slice28.v1`. *(ruled Q6.)*
- **D-29-7 HTTP surface:** none. *(rec.)*
- **D-29-8 Flag derivation:** write-time, frozen. *(ruled.)*

## 9. Tests — `tests/test_pr_evidence.py`
- **Pure validators:** provider/provenance; `repo_ref` slug + token denylist; `pr_number > 0`; `pr_state` enum; `presence_flags` shape (bad key/source/prose rejected); `check_status_summary` shape + **nullable**; `traceability_refs` shape; caller path rejects `connector_verified`; connector path requires it + `observed_at`.
- **`normalize_approvals` (B-29-5/6):** multiple reviews by one principal (latest wins); `CHANGES_REQUESTED` after `APPROVED` (not approving); dismissed reviews excluded; `COMMENTED` not approving; requested-but-not-approved reviewer excluded; `approval_count == len(approver_principals)`.
- **`derive_separation_flags`:** self-approval / self-merge / separation truth table + negatives.
- **`map_github_pull_request` (B-29-1):** check states success/failure/pending/neutral/unknown mapped; **check evidence unavailable ⇒ `check_status_summary=None`** (PR facts still map); malformed PR body ⇒ `SCMConnectorError`; missing/malformed `reviews` arg ⇒ `SCMConnectorError`.
- **Endpoint mandatoriness (B-29-7, connector/service):** PR-endpoint failure ⇒ `SCMConnectorError` ⇒ **no write**; **reviews-endpoint failure ⇒ `SCMConnectorError` ⇒ no write**; requested-reviewers failure ⇒ snapshot writes with `requested_reviewers_observed=false` + empty list; check-endpoint failure ⇒ snapshot writes with `check_status_summary=None` only (review facts intact).
- **Repository — traceability (B-29-3, db):** same-project valid refs accepted; **wrong-project / unknown / wrong-kind (non-AC artifact) / duplicate ⇒ fail closed.**
- **Repository — merged-protected (B-29-2, db):** flag true only with merged + base==declared-protected + connector_verified+enabled+fresh branch-protection; **false when evidence absent / stale / unverified / repo-mismatch / branch-mismatch / not-merged.**
- **Repository — write paths (db):** connector write stamps `connector_verified` + derives flags + caller-declared presence `source` preserved (B-29-4); caller write stamps unverified; latest-wins ordering; counts.
- **Migration/RLS/grants/immutability (db):** table present; RLS ENABLE+FORCE; `uaid_app` SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked; composite FK cross-project/tenant rejected; cross-tenant SELECT empty.
- **DB guard (db, direct SQL):** bad provider/repo_ref/token/`pr_number<=0`/bad `pr_state`/non-object `presence_flags`/`traceability_refs` rejected; provenance repo-controlled.
- **DB derived-invariants (B-29-8, direct SQL):** `approval_count <> jsonb_array_length(approver_principals)` rejected; non-array `approver_principals` rejected; non-object (non-null) `check_status_summary` rejected; invalid check-state key rejected; negative / non-integer check count rejected; invalid `combined_state` rejected; **`check_status_summary = NULL` accepted.**
- **Broker / fail-closed (db):** deny ⇒ no write; `SCMConnectorError`/`None` ⇒ audited failure no write; `repo_unbound`/`credential_unbound` ⇒ no write; **no raw `repo_ref` in `tool_calls.params`.**
- **Safe audit (db):** token/repo_ref/body/diff/URL/check-names/principals/traceability-UUIDs never in audit or `tool_calls.params`.
- **No-A5-regression (db):** `evaluate_production_autonomy` report identical before/after PR evidence exists; `ruleset_version == "slice28.v1"`; `passed_gate_count`/`a5_satisfied`/go-live unchanged.
- `make test` + fresh `make test-db` (drop→bootstrap→migrate→`-m db`) green; `alembic upgrade head` + `downgrade -1` clean. *(Editing an applied migration needs `make test-db-drop` first.)*

## 10. Sequencing
1. Pure `pr_evidence.py` (validators + `normalize_approvals` + `derive_separation_flags`) + pure tests.
2. Model + migration `0028` (drop→migrate; DB-guard tests).
3. Repository (traceability + merged-protected cross-ref + write paths) + db tests.
4. Connector extension + `map_github_pull_request` (+ checks) + pure mapping tests.
5. Service + registry/matrix wiring + broker/fail-closed tests.
6. No-A5-regression; full `make test` + `make test-db`; alembic round-trip.
7. CLAUDE.md + roadmap banner.

## 11. Risks / honesty caveats
- **`connector_verified` is app-enforced, not DB-attested** (connector path is the sole writer; DB guard widens the value, can't attest authenticity) — same caveat as Slices 26/28.
- **Check status is observed, not required-satisfaction** (B-29-1) — `check_status_summary` records what the provider reports; Slice 29 does **not** determine whether *required* checks passed. NULL = not observed.
- **Review facts are fail-closed; requested-reviewers is disambiguated** (B-29-7) — a failed reviews fetch yields **no snapshot** (never a silent "0 approvers"); `requested_reviewers_observed=false` distinguishes "not fetched" from "fetched, none requested".
- **Merged-protected is a cross-referenced observation** (B-29-2) — true only when verified branch-protection evidence backs it; false ≠ "definitely unprotected", it means "not confirmed".
- **Separation flags are provider-principal equality, not §2.2 enforcement / not UAID-actor separation** (Q3).
- **Presence ≠ adequacy; `caller_declared` is never promoted** (B-29-4) — per-flag `source` stays visible.
- **`pr_number` is caller-supplied** — safe because repo-scoped to the project's OWN declared repo (`repo_ref` never caller-supplied).

## 12. Must NOT claim
- That any A5 gate flips / go-live / the A5 report changed (`production_autonomy` untouched; `slice28.v1`).
- That **required reviewers approved** or **required checks are satisfied** (B-29-1/6; that is Slice 46).
- That review approval == acceptance verification.
- That `connector_verified` attests §12.4 content adequacy, or that a `caller_declared` flag is provider-verified.
- That the self-approval flags enforce §2.2/§12.3 or prove UAID-actor separation.
- That the broker now executes or its authority widened — decision-only; the new tool is an A1 read.

## 13. Definition of done
A broker-gated, repo-bound PR-evidence connector writes immutable `connector_verified` `pull_request_evidence_snapshots` (provider facts + **observed** check-status + §12.4 presence with preserved source labels + normalized identity/structural flags + **observed** merged-protected + **repository-validated** `traceability_refs`) for the project's OWN declared repo, latest-wins; append-only + RLS + DB-guard + traceability/merged-protected validation proven by DB-backed tests; **zero `production_autonomy` change, ruleset `slice28.v1`, no A5 regression**; no secret/repo_ref leak; `make test` + `make test-db` + alembic round-trip green; go-live false.
