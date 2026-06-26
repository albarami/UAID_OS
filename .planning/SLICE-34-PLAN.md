# Slice 34 — Project-management / issue-tracker connector — PLAN v2

**Status:** AWAITING PLAN REVIEW (v1 REJECTED; v2 binds D-34-1=Option A + fixes B1–B8) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**

> **Revision log — v1 → v2 (D-34-1 ruled Option A; all eight accepted):**
> - **B1 — Option A (mapping-only) BOUND; Option B removed from the executable body.** This slice **records mappings only** and **creates no `release_issues`** ⇒ truly store-only / `before==after`. (Option B / the PM→`release_issues` *creation* bridge is a deferred future slice — rationale only, not executed.)
> - **B2 — Jira-status → §12.3 board-column mapping BOUND** (§3.1): a fixed `JIRA_STATUS_MAP` (lowercased exact Jira status → one of the 16 §12.3 columns); **any unknown/unmapped Jira status → `board_column='unmapped'`** (honest fail-closed — never a guessed column). The raw `external_status` is also stored (bounded) so the item stays traceable when `unmapped`.
> - **B3 — observation-provenance split from issue-provenance-adequacy.** `provenance='connector_verified'` means **the connector verified it OBSERVED the external state** — NOT that the issue is provenance-complete/authoritative. **Issue-provenance adequacy (gate #7) stays unverified and is NOT consumed for any gate pass this slice** (`release_issues` provenance is already explicitly unverified/non-authorizing, `release_issue.py:1-10`).
> - **B4 — exact persisted declaration + credential shape BOUND** (§2.1): `tool_access_manifest.jira = {project_key:"<bounded>", instance_key:"<bounded operator alias>"}` + the credential reference `{manager:"env", reference_name:"JIRA_CONNECTOR_TOKEN"}` in `secrets_and_credentials_manifest` (mirrors the GitHub resolver, `project_repo.py:60-79`). `instance_key` is an **operator alias**, never a project-declared URL/host.
> - **B5 — live Jira adapter DEFERRED.** This slice ships the **protocol + `FakeIssueTrackerConnector` only** — **no live HTTP adapter** (no base-URL/redirect/timeout/pagination/body-cap/credential-audience surface to review). The security-bound live `JiraIssueTrackerConnector` is a dedicated follow-up.
> - **B6 — optional `release_issue_id` FK DROPPED.** Under Option A no `release_issues` are created and there is no same-ref matching mechanism, so the link is unused this slice — removed (no `release_issues` schema change at all). The `release_issues` link is added by the future bridge slice.
> - **B7 — canonical identity/latest-wins key BOUND:** `(tenant_id, project_id, external_system, instance_key, external_ref)` — so Jira keys from different projects/instances cannot collide. The index + latest-wins lookup use exactly this key.
> - **B8 — tool name BOUND `pm.read_issues`** (category `project_management`, consistent with the existing `pm.create_issue`) → action `read_project_management_issues`.

> **Provenance (Sanad — read this session):** §12.3 board workflow (`docs/…v1_2.md:1184-1207`) — the 16 columns `Backlog → Analysis → Requirements Review → Ready for Development → In Progress → Developer Self-Check → Specialist Review → Changes Requested → QA Testing → Security Review → Shortcut Detection → Acceptance Verification → Evidence Audit → Ready for Release → Released → Done`; **"Builder agents cannot move their own work to Done"** (`:1207`); file 18 `18_tool_access_manifest.yaml` `tool_access.jira` (empty placeholder — this slice binds its persisted shape); the existing GitHub credential resolver `{manager:'env', reference_name:'GITHUB_CONNECTOR_TOKEN'}` (`app/release/project_repo.py:54-79`); `release_issues` (Slice 24) provenance **UNVERIFIED / non-authorizing** (`app/models/release_issue.py:1-10`); A5 gate #7 reads release-issue counts as **`context` only** and never passes (`app/release/production_autonomy.py:208-234`); existing registry `pm.create_issue` / category `project_management` (`app/tools/registry.py:47-53`) + the read-tool naming `source_control.read_pull_request` / `deployment.read_target_status` / `monitoring.read_status` (`:57-75`). **No PM/Jira connector or mapping table exists** (grep). Reuse: the broker-gated fake-in-tests connector pattern; the immutable append-only + RLS + two-tier-provenance store pattern (Slices 26/30/31/32).

---

## 0. Goal & non-goal
- **Goal.** A broker-gated **Jira** issue-tracker connector that reflects external PM issues into an immutable, tenant-owned **`pm_issue_mappings`** store — **mapping-only** (Option A): observed external state `(external_ref, external_status, §12.3 board_column, title_present)` per item, idempotently re-syncable, so external PM state is **visible + traceable** (§12.3; §26.3). **Creates no `release_issues`.**
- **Non-goal — NOT a gate flip / NOT a `release_issues` change.** `production_autonomy.py`/`readiness.py` untouched; ruleset `slice31.v1`; **`before==after`** holds (no `release_issues` created ⇒ gate-#7 context counts unchanged). **A synced PM issue is NOT provenance-verified complete / authoritative** (roadmap `:290`; Slice 47) — `connector_verified` here means *observation*-verified only (B3). **No secret value** stored (credential operator-env, reference-only). **No live Jira HTTP adapter** this slice (B5). **Jira-only** (other PM tools deferred). The connector **never writes back** to Jira (read-only). No HTTP endpoint. **No `release_issues` schema change** (B6 — no link this slice).

## 1. Bound decisions
- **D-34-1 — Option A (mapping-only)** (B1).
- **D-34-2 Provider — `jira` only**; connector = protocol + `FakeIssueTrackerConnector` (CI). Live adapter **deferred** (B5).
- **D-34-7 Tool — `pm.read_issues`** (category `project_management`) → A1 action `read_project_management_issues` (`_r(L.A1)`, non-mandatory) (B8).
- Identity/latest-wins key — `(tenant_id, project_id, external_system, instance_key, external_ref)` (B7).

## 2. Declaration resolver + credential (B4)
### 2.1 `resolve_declared_pm_project` — `app/release/project_repo.py`
Returns `(instance_key, project_key)` or `None` (fail-closed) from the project's declared `tool_access_manifest` category: `data["jira"] = {project_key:<bounded ^[A-Z][A-Z0-9_]{0,63}$-ish>, instance_key:<bounded ^[a-z0-9_.:-]{1,64}$ operator alias>}`. Fail-closed: missing category / status≠`declared` / `data` not a dict / missing/non-dict `jira` / blank/invalid `project_key`/`instance_key`. **Never a URL/host** (the operator maps `instance_key`→base URL out-of-band; the live adapter — deferred — will use an operator allowlist). Credential presence reused via the `has_declared_credential` pattern for `{manager:'env', reference_name:'JIRA_CONNECTOR_TOKEN'}` in `secrets_and_credentials_manifest` (reference-only; the token value is operator-env, never stored/audited).

## 3. Pure module — `app/release/pm_issues.py`
- `EXTERNAL_SYSTEMS=("jira",)`; `BOARD_COLUMNS` = the 16 §12.3 columns (snake_case) **+ `"unmapped"`**; `PROVENANCES`/`WRITABLE`/`CONNECTOR_WRITABLE` (two-tier); `EXTERNAL_REF_RE`/`INSTANCE_KEY_RE` (bounded safe shapes + token denylist); `TOKENISH_RE` reuse.
### 3.1 `map_board_column(jira_status) -> str` (B2)
A fixed `JIRA_STATUS_MAP` (lowercased exact match → a §12.3 column, e.g. `"backlog"→backlog`, `"in progress"→in_progress`, `"in review"→specialist_review`, `"qa"/"testing"→qa_testing`, `"done"→done`, `"released"→released`, …). **Any status not in the map ⇒ `"unmapped"`** (honest fail-closed — never a guessed column). The raw `external_status` is preserved on the row for traceability.
- Validators (`validate_new_mapping`/`validate_connector_mapping`): `external_system`/`board_column`/`provenance` enums, `external_ref`/`instance_key` shapes + token denylist, caller-cannot-assert-`connector_verified`, connector-requires-`observed_at`.

## 4. Mapping store + migration `0033`
`pm_issue_mappings` (tenant-owned, RLS ENABLE+FORCE; SELECT/INSERT only, append-only block triggers; `created_at` `clock_timestamp()`): `id`, `tenant_id`, `project_id`, `external_system` (CHECK `IN ('jira')`), `instance_key` (CHECK shape), `external_ref` (CHECK shape + token denylist), `external_status` (bounded text), `board_column` (CHECK ∈ the 16 §12.3 columns ∪ `unmapped`), `title_present` (bool), `provenance` (two-tier CHECK), `observed_at` (tz null), `created_at`. **No title/description/credential/`release_issue_id` column** (B6 — no `release_issues` link; no secret/free-text). FK `(project_id, tenant_id) → projects`. Latest-wins index on `(tenant_id, project_id, external_system, instance_key, external_ref, created_at)` (B7). **Additive — no change to existing tables** (incl. `release_issues`).

## 5. Repository + service
- `app/repositories/pm_issues.py`: `PMIssueMappingRepository.record_connector_verified_mapping(...)` (validates, audits **safe metadata only** — external_system/instance_key/external_ref/external_status/board_column/title_present/provenance; **never** a title/credential) + `latest_for_ref(project_id, external_system, instance_key, external_ref)` + `list_latest_for_project`.
- `app/release/pm_sync_service.py`: `sync_pm_issues(...)` — resolve the declared Jira project (fail-closed; `None` ⇒ audited `pm_unbound`, no write) → `broker_call` `pm.read_issues` (**safe params** `{provider:'jira', project_present:true}` — never project_key/instance_key/credential) → non-ALLOW ⇒ audited `broker_denied`, no write → `connector.fetch_issues(...)` (Fake in tests) → record one latest-wins mapping row per external item. **Idempotent:** a re-sync of the same `(…, external_ref)` appends a new latest-wins row reflecting current state. Admin/internal — no HTTP endpoint.

## 6. A5 / evidence impact
- **NONE.** `production_autonomy.py` + `readiness.py` untouched; ruleset `slice31.v1`; a **`before==after`** regression proves recording PM mappings flips no gate/readiness (no `release_issues` created — gate #7 context unchanged).

## 7. Tenant / RLS / FK / audit / immutability
RLS ENABLE+FORCE + `tenant_isolation`; append-only (SELECT/INSERT only); FK pins project+tenant; audit safe-metadata only; **no secret/credential or free-text title stored/logged**.

## 8. Tests (DB-backed + Docker-free, per README `:19-32`)
- **Pure:** validators (system/ref/instance shapes + token denylist, board_column enum incl. `unmapped`, provenance, caller-cannot-assert-connector_verified); `map_board_column` truth table — known Jira statuses → §12.3 columns, **unknown ⇒ `unmapped`** (B2).
- **DB-guard:** bad system/ref/instance/board_column/provenance rejected; append-only no-UPDATE/DELETE/TRUNCATE; FK cross-project/tenant; RLS cross-tenant; **no title/credential/release_issue_id column** exists (structural assertion).
- **Connector:** `FakeIssueTrackerConnector` returns observed facts; **no title/description/credential in the observation**.
- **Resolver:** `resolve_declared_pm_project` returns `(instance_key, project_key)`; fail-closed (undeclared / bad shapes / missing jira block).
- **Service (db):** broker-allow writes a mapping per item; **idempotent latest-wins** re-sync (new row, latest reflects current state, keyed by the B7 identity); `pm_unbound`/`broker_denied` ⇒ no write; safe broker params (no project_key/instance_key/credential in `tool_calls.params`); audit no title/credential.
- **No-A5-impact (db):** `ProductionAutonomyRepository.evaluate` **`before==after`** recording mappings; `ruleset_version == "slice31.v1"`.
- `make test` + fresh `make test-db` + alembic `0033` round-trip; CI green.

## 9. Sequencing (TDD)
1. Pure validators + `map_board_column` (+ unmapped). 2. Model + migration `0033` (DB-guard enums/shape + append-only). 3. Repository + `resolve_declared_pm_project` (+ db tests). 4. Connector protocol + Fake (+ no-title-leak tests). 5. Service + registry/matrix `pm.read_issues` (+ broker/idempotent/safe-params tests). 6. No-A5-impact `before==after` guard. 7. Full gates; CLAUDE.md merge-stable entry + roadmap banner.

## 10. Must NOT claim
- That a synced PM issue is **provenance-verified complete / authoritative** (roadmap `:290`; Slice 47) — `connector_verified` is *observation*-verified only (B3); issue-provenance adequacy stays unverified and feeds no gate pass.
- That any A5 gate / readiness level changed (store/infra-only; `before==after`; ruleset `slice31.v1`; go-live false).
- That the connector writes back to / mutates Jira (read-only), or that a live Jira HTTP adapter ships this slice (deferred, B5).
- That `release_issues` changed (no schema change, no rows created — B6).
- That a secret/credential or issue title/description is stored (it is not).

## 11. Definition of done (for the eventual implementation — NOT this PLAN)
A broker-gated Jira connector (protocol + Fake; **live adapter deferred**) resolves the project's OWN declared Jira `(instance_key, project_key)` and writes immutable, append-only, **idempotent latest-wins** `pm_issue_mappings` (keyed by tenant/project/system/instance_key/external_ref, B7) reflecting external PM state — observed facts only (`external_status` + §12.3 `board_column` with `unmapped` fail-closed; **no title/description/credential/`release_issue_id`**); RLS + DB-guard; **no `release_issues`/`production_autonomy`/`readiness` change**, `ruleset_version=slice31.v1`, `before==after` regression green; `make test` + `make test-db` + alembic `0033` round-trip + CI green; go-live false; synced items observation-verified but issue-provenance-unverified.

---
**Review note:** PLAN v2 binds **D-34-1=Option A** and all of B1–B8: Option-B removed; Jira-status→§12.3 board-column map with an `unmapped` fail-closed sentinel (B2); observation-provenance split from issue-provenance-adequacy (B3); exact `tool_access_manifest.jira` `{project_key, instance_key}` + `JIRA_CONNECTOR_TOKEN` reference (B4); **live Jira adapter deferred — protocol + Fake only** (B5); the unused `release_issue_id` FK dropped (B6); canonical key `(tenant, project, system, instance_key, external_ref)` (B7); tool `pm.read_issues`→`read_project_management_issues` (B8). Store/infra-only, `before==after`, migration `0033`. No code/migration/tests/PR until an approved plan + your explicit go.
