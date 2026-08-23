# Slice 59 Plan — Stabilization-window assessment (does not close §25.4 / §26.6) (§25.3 / §25.4)

**Status:** AWAITING PLAN APPROVAL (v6). v1/v2/v3 REJECT by GPT-5.6 Sol agent `8cd454f8-3cdf-43d5-84b8-1b8802e2fcab`; v4 and v5 REJECT by Sol agent `02b57793-3170-4b0d-bb8f-97038c543c59` (seq-4 removal accepted as honest in v4; v5 closed the clock, fixed-set and handover defects but its seq-3 pass path was shown forgeable). Owner (Salim) lifted the three-REJECT halt on 2026-08-23 and authorized a retry. OD-59-1…10 = Option A as restated.

**Seats (binding):** Builder Cursor Grok 4.6 (Grok family). Reviewer GPT-5.6 Sol (`gpt-5.6-sol-max`, GPT family), sole approval authority. Builder sub-agents may not approve.

**Author persona:** Senior SRE / incident-response architect applying fail-closed evidence-integrity discipline.

**Slice closure:** Non-closing. Window status vocabulary is `open` only. Backup/restore never validated. `all_criteria_passed` is **structurally unreachable**. Slice 58 residual §26.6 actuators stay open.

**Execution authorization:** Plan-only until APPROVE. No backup connector, git, broker, Jira, eval/prompt/oracle/forecast writes, go-live flip, A5/readiness bump, or §2.6 bypass.

---

## Coordinator standing rulings (binding)

1. Slice 59 Salim gate REMOVED; run 57→63 continuously (2026-08-22). Halt after three consecutive REJECTs; owner lifted that halt for this retry (2026-08-23).
2. Builder Grok 4.6; Reviewer GPT-5.6 Sol.
3. pyright mandatory every slice.
4. Hard stops unchanged: no weakening tests/CI, no force-push, no spec edits, no budget figures, no secrets, no go-live default-true, no §2.6 bypass.

---

## Sanad / citation key

- Spec §25.1 exit (2355–2361), §25.3 (2391–2402), §25.4 (2404–2424), §26.6 (2510), §27.13 (2812–2828).
- Schema asset `docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/stabilization_window_policy.yaml`.
- Slice 56 OD-56-4: `error_budget_threshold` is a string; never parsed as a number.
- Slice 58: frozen `app/ops/hotfix.py` `gate10_conjunction_passed`; `coverage_with_run(project_id, as_of=)` (`rollback_verifications.py:360`).
- Gate #11 ladder `production_autonomy.py:1005-1028`; gate #10 ladder `:1188-1285`. Neither is re-implemented; `ProductionAutonomyRepository.evaluate` is not called.
- Latest-wins orderings this plan must mirror exactly: `latest_monitoring_for_ref` — `(provider, target_ref)`, `created_at DESC, id DESC` (`monitoring_evidence.py:73-93`); `latest_deployment_target_for_ref` — `(provider, environment, target_ref)`, same order (`deployments.py:69-95`); `_latest_pack` — `assembly_status='complete'`, same order (`rollback_verifications.py:124-136`); `_latest_matching_run` — candidate+pack+`staging_target_binding_hash`+3 contract versions+`runner_manifest_hash`, same order (`:92-122`).
- Python-only digests the DB cannot recompute: `canonical_digest(repo_ref)`, `StagingTargetProjection.binding_hash`, `_snapshot_digest(...)`, `EvidencePackRepository.audit_pack` byte re-audit.
- Config: `settings.monitoring_evidence_max_age_hours` / `settings.deployment_evidence_max_age_hours` (`app/config.py:31,34`, both default 24).
- Identity: `TenantContext.actor: AuthenticatedActor | None` (`app/tenancy.py:38`).
- `resolve_declared_monitoring_target` returns the **raw declared `status_url` string** (`project_repo.py:197-204`), and the Slice-31 service records that same string as the snapshot `target_ref` (`monitoring_evidence_service.py:97`). Gate #11 looks up `latest_monitoring_for_ref(project, 'generic_monitoring_api', monitoring[0])` (`repositories/production_autonomy.py:166-172`). String equality against the declared value is therefore byte-exact with gate #11's own binding.
- `latest_handover` is project-scoped and ordered `created_at DESC, id DESC` (`ops_incident_reads.py:148-155`).
- Baseline: `main` `33ee561`; Alembic head **`0057_self_healing`**; migration **`0058_stabilization`** (`down_revision=0057`).

---

## 0. Honesty crux

Three facts drive v6 and they are not negotiated away:

1. **No production coverage clock exists.** `projects.created_at` is project age, not incident-ledger or post-deployment coverage. Seq 1 is therefore **always `not_evaluable`**.
2. **Gate #10 currency is not DB-provable without duplicating Python digests.** `binding_current` depends on `canonical_digest(repo_ref)`, `StagingTargetProjection.binding_hash`, and `_snapshot_digest(...)`; `core_reaudited` depends on an evidence-pack byte re-audit. Re-implementing those in PL/pgSQL would fork frozen logic. A restricted-writer wrapper does not help either: `uaid_app` would still supply the verdict argument. **Therefore seq 4 has no `passed` status in this slice** (v3 defect 2 resolved by removing the unprovable claim, not by weakening the guard).
3. **Gate #11 activity is not DB-provable either, for the same class of reason.** `monitoring_status_snapshots` grants `uaid_app` INSERT and its provenance CHECK admits `connector_verified` (`0030_monitoring_evidence.py:86-89,176`), while the table's URL CHECKs are only `^https://`, `!~ '[[:space:]@?#]'`, a length bound, and a token denylist (`:93-100`) — far weaker than `parse_and_validate_status_url`. A direct-SQL forger can therefore insert a `connector_verified` snapshot for `https://localhost/x`, point the declaration at the same string, and satisfy every remaining column check. Mirroring the real validator (FQDN rules, IP-literal and private-range denial, port and path normalization) in PL/pgSQL would fork it, and any divergence reopens the hole. **Therefore seq 3 also has no `passed` status in this slice** (v5 defect 1 resolved the same way as seq 4).

Pass-capable criterion in Slice 59: **seq 5 (handover) only**, and its claim is deliberately scoped to exactly what the guard proves — that the *latest recorded* handover row says complete, never that a handover occurred or was signed by an authority (v4 defect 4). Every other criterion is structurally non-passing at the DB. `as_of` is DB-generated so no recorded row can carry a backdated clock (v4 defect 2).

Claim allowed:

> UAID recorded a tenant-owned stabilization-window assessment against an immutable §27.13 policy snapshot, stamped with a DB-generated transaction clock, bound to the currently declared monitoring target. Seq 1 is not_evaluable: no production coverage clock exists. Backup/restore, p95 latency, and post-launch security alerts stay not_observed. Monitoring activity and rollback currency are app-derived observations that mirror the gate #11 and gate #10 ladders, and neither is ever recorded as passed, because the runtime role can write the underlying evidence tiers directly and this store cannot prove them in the database. The only passable criterion is support handover, and it proves only that the latest recorded handover row says complete. Closure attempts are persisted refusals and never change window status. Follow-up is required_not_executed; a later run is an extension only when explicitly linked. This does not exit §25.4, close §26.6, or authorize go-live.

---

## 1. Frozen files (byte-stable)

- `app/release/production_autonomy.py` = `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029`
- `app/intake/readiness.py` = `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26`
- `app/runtime/control_loop.py` = `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180`
- `app/ops/db_checks.py` = `468837a3afe452239fa392a16cdf1ab90c10938fecb0854478f32606eabb49fc`
- `app/ops/incidents.py` = `0b5e996c410169b41d3aacd12659d680e3147354cfd23e2dad568a4221eb76c7`
- `app/ops/hotfix.py` = `ac6a26cee28ae37b872bcac0e8daef2709d9a69be35d4c31822328309aeb8599`
- `app/ops/incident_db_checks.py` = `c529a280f8758eefa6d5e82d616ff39580327caf2bdd307c7461b6c7295692b8`
- `app/ops/hotfix_db_checks.py` = `f7b282f5eef92234777ec0055c3e4efa5d9d3cc40e2d7852d29f3e0f7da8def4`
- Findings-guard MD5 = `808036faf2660d6810aeca4342e6f1ac`

Do not modify those, policy `MATRIX` keys, spec, templates, `.env`, `rollback_verifications.py` (496 lines), or `emergency_controls.py` (790 lines). Additive `resolve_declared_stabilization_window` on `project_repo.py` is allowed. Additive UNIQUE targets in `0058` are allowed.

---

## 2. Design

### 2.1 Contracts

`slice59.stabilization.v1` / `slice59.improvement_inventory.v1` / `ruleset_version='slice59.v1'`. A5 stays `slice54.v1`; readiness stays `slice20.v1`.

### 2.2 Immutable policy snapshot

`resolve_declared_stabilization_window` reads `operations_observability_support` with `status='declared'` and requires `data.stabilization_window` with **exactly** these keys: `duration_days`, `owner`, `support_owner`, `monitored_journeys`, `error_budget_threshold`, `exit_criteria`, `closure_approver`. `exit_criteria` exact keys: `zero_open_critical_incidents_for_days` (int 1..30), `error_budget_under_threshold` (bool), `monitoring_confirmed_active` (bool), `rollback_blockers_open` (must be `0`), `support_handover_complete` (bool). `duration_days ∈ {7,14,30}`. Strings bounded ≤200 non-blank; `monitored_journeys` ≤16 bounded strings. Unknown keys fail closed. Template YAML is never parsed. Missing/invalid ⇒ `StabilizationError('no_window_declaration')`, **no writes**.

Persist on the run: `category_id` **NOT NULL** with composite FK to `uq_intake_categories_id_proj_tenant`; `policy_snapshot` JSONB (the validated dict, copied — not a pointer at mutable `intake_categories.data`); `policy_digest`.

SQL function `public.stabilization_policy_digest(jsonb) RETURNS text` — IMMUTABLE, `'sha256:' || encode(sha256(convert_to(jsonb_canonical_text, 'UTF8')),'hex')` over the jsonb rendered with sorted keys. The window guard enforces `policy_digest = stabilization_policy_digest(policy_snapshot)`. `error_budget_threshold` is copied verbatim and never parsed numerically.

### 2.3 DB-generated clock; freshness recorded, never load-bearing (v3 defect 3, v4 defect 2)

**Clock.** `as_of` is obtained as `SELECT transaction_timestamp()` inside the REPEATABLE READ write transaction, and the window guard enforces `NEW.as_of = transaction_timestamp()`. Because `transaction_timestamp()` is stable within a transaction, the honest app path always matches; a direct-SQL forger inserting in its own transaction **cannot backdate** `as_of`.

**Freshness limits.** No pass path depends on freshness any more (seq 3 and seq 4 have no `passed`), so there is no DB-authoritative age constant and no guard arithmetic over these values. The run records, as NOT NULL INTEGER columns with `CHECK BETWEEN 1 AND 168`, the values the app actually used in that call (same `settings` object):

- `monitoring_max_age_hours` ← `settings.monitoring_evidence_max_age_hours`
- `deployment_max_age_hours` ← `settings.deployment_evidence_max_age_hours`

They are transparency + `input_digest` inputs only. Recording them makes the app-derived `monitoring_evidence_stale` / `rollback_path_not_current` verdicts interpretable after the fact; they gate nothing and confer no authority.

The same `as_of` is passed into the existing `coverage_with_run(project_id, as_of=as_of)` and `CostForecastRepository.coverage_for_project(project_id, as_of=as_of)`. No new methods are added to those files. `coverage_with_run` uses `settings.deployment_evidence_max_age_hours` internally, so the snapshotted value and the coverage computation agree by construction.

### 2.4 Eight criteria

Statuses: `passed` | `failed` | `not_observed` | `not_evaluable`.

| seq | criterion | allowed statuses | reasons |
|---|---|---|---|
| 1 | `zero_open_critical_incidents_for_days` | `not_evaluable` only | `no_production_coverage_clock` |
| 2 | `error_budget_under_threshold` | `not_evaluable` only | `error_budget_threshold_unparsed_string` |
| 3 | `monitoring_confirmed_active` | `not_observed`, `failed`, `not_evaluable` — **never `passed`** | see §2.4.1 |
| 4 | `rollback_blockers_open` | `not_observed`, `failed`, `not_evaluable` — **never `passed`** | see §2.4.2 |
| 5 | `support_handover_complete` | `passed`, `failed`, `not_observed` | `handover_recorded_complete` / `handover_recorded_incomplete` / `no_handover_record` |
| 6 | `backup_restore_validated` | `not_observed` only | `no_backup_restore_source` |
| 7 | `p95_latency_within_slo` | `not_observed` only | `no_latency_slo_source` |
| 8 | `no_unresolved_security_alerts` | `not_observed` only | `no_post_launch_security_alert_source` |

Each seq owns a fixed code-owned `criterion_key` (the middle column above), enforced by a `(seq, criterion_key)` pairing CHECK, `CHECK (seq BETWEEN 1 AND 8)`, and `UNIQUE (tenant_id, window_id, seq)` — so eight rows necessarily means the exact set 1..8, each with its own key, with no duplicates (v4 defect 3).

Counters on the run (disjoint, CHECK sum = 8): `passed_count`, `failed_count`, `not_observed_count`, `not_evaluable_count`. They are **derived, not asserted**: the deferred count-match trigger recomputes all four tallies from the children and rejects the transaction on any mismatch, and likewise requires `extension_required = (passed_count < 8)`, which is always `true`.

#### 2.4.1 Seq 3 — monitoring (never passes)

App resolution uses `resolve_declared_monitoring_target` then `latest_monitoring_for_ref(project_id, 'generic_monitoring_api', status_url)`. The ladder mirrors gate #11 up to, but never reaching, a pass:

| condition | status | reason |
|---|---|---|
| no declared target | `not_observed` | `no_monitoring_declaration` |
| declared, no snapshot | `not_observed` | `monitoring_declared_but_no_evidence` |
| `provenance <> 'connector_verified'` | `failed` | `monitoring_observed_unverified` |
| stale vs `as_of` / `monitoring_max_age_hours` | `failed` | `monitoring_evidence_stale` |
| `response_valid = false` | `not_evaluable` | `monitoring_evidence_unreadable` |
| `overall_active = false` | `failed` | `monitoring_or_alerts_inactive` |
| else | `not_evaluable` | `monitoring_active_app_derived_not_db_provable` |

Unreadable is never reported as inactive, and an active verified reading is never reported as passed: the negative rungs are safe to store because they fail closed, while the positive rung would assert a provenance tier the runtime role can write directly (§0.3). This is symmetric with seq 4.

#### 2.4.2 Seq 4 — rollback (never passes)

App calls `coverage_with_run(..., as_of=as_of)` and the frozen `gate10_conjunction_passed(coverage)`.

| condition | status | reason |
|---|---|---|
| no latest matching run | `not_observed` | `no_rollback_run` |
| run present, conjunction false | `failed` | `rollback_path_not_current` |
| run present, conjunction true | `not_evaluable` | `rollback_currency_app_derived_not_db_provable` |

`failed` is safe to store because it is the fail-closed direction. `passed` is excluded by DB CHECK, so no obsolete or forged run can be recorded as current. This is not a Slice-24 open-issue count.

### 2.5 Typed FKs and additive UNIQUE targets (v2 defect 2, retained)

Criterion columns: `monitoring_snapshot_id`, `rollback_verification_run_id`, `handover_id` — all nullable typed UUIDs with composite FKs `(x, project_id, tenant_id)`. No polymorphic `source_ref`.

`0058` adds additive `UNIQUE (id, project_id, tenant_id)` (never rewriting `0030`/`0056`/`0016`) to:

- `monitoring_status_snapshots` → `uq_mss_id_project_tenant`
- `ops_support_handovers` → `uq_osh_id_project_tenant`
- `intake_findings_reports` → `uq_ifr_id_project_tenant` (improvement seq 6)

`rollback_verification_runs` already has `uq_rbvr_id_project_tenant`; `cost_forecast_runs` already has `uq_cfr_id_project_tenant`.

Nullness: seq 3 sets `monitoring_snapshot_id` iff a snapshot for the declared target exists; seq 4 sets `rollback_verification_run_id` iff a latest matching run exists; seq 5 sets `handover_id` iff a handover exists; seq 1/2/6/7/8 leave all three NULL. Every other seq leaves the FKs it does not own NULL.

### 2.6 DB guards

Every comparison below is written NULL-safely: each check is expressed as an explicit `IF <positive condition is not TRUE> THEN RAISE` branch (or `IS DISTINCT FROM`), never as a bare `NOT (a = b)` that a NULL would silence (v4 defect 1).

**Window guard (BEFORE INSERT on `ops_stabilization_windows`):**

1. `status='open'`; `criterion_count=8`; `improvement_count=8`; `extension_required IS TRUE`.
2. `policy_digest = stabilization_policy_digest(policy_snapshot)` (both operands NOT NULL).
3. `as_of = transaction_timestamp()` — a DB-generated clock, so `as_of` cannot be backdated (§2.3).
4. `monitoring_max_age_hours` and `deployment_max_age_hours` NOT NULL and within 1..168 (recorded, not load-bearing).
5. **Declared-target binding.** Let

   ```sql
   SELECT c.data->'monitoring'->>'status_url' INTO declared
   FROM intake_categories c
   WHERE c.id = NEW.category_id
     AND c.tenant_id = NEW.tenant_id
     AND c.project_id = NEW.project_id
     AND c.category = 'operations_observability_support'
     AND c.status = 'declared'
     AND c.data->'monitoring'->>'provider' = 'generic_monitoring_api';
   ```

   Then: `IF NEW.monitoring_target_ref IS NOT NULL AND (declared IS NULL OR NEW.monitoring_target_ref <> declared) THEN RAISE`. Under-claiming (NULL) is allowed; a missing, wrong-category, wrong-provider, undeclared, or mismatched declaration is rejected. This is a **labelling** guarantee — it proves which target the seq-3 rows refer to — and it is not load-bearing for any pass, since seq 3 cannot pass. The URL validator is deliberately **not** forked into PL/pgSQL (§0.3).
6. `extends_window_id IS NULL OR` (prior row exists, same tenant+project, `prior.extension_required IS TRUE`, `prior.id <> NEW.id`).

**Criterion guard (BEFORE INSERT on `ops_stabilization_criterion_results`, loading the parent run):**

- seq 1: `status='not_evaluable'`, reason `no_production_coverage_clock`, all FKs NULL.
- seq 2: `status='not_evaluable'`, reason `error_budget_threshold_unparsed_string`, all FKs NULL.
- seq 3: `status <> 'passed'`; `monitoring_snapshot_id` NULL iff the reason is `no_monitoring_declaration` or `monitoring_declared_but_no_evidence`, NOT NULL otherwise; when NOT NULL, `parent.monitoring_target_ref` NOT NULL, `snapshot.target_ref = parent.monitoring_target_ref`, and `snapshot.provider='generic_monitoring_api'`, so a cited row always belongs to the declared target (v3 defect 1, now a labelling guarantee).
- seq 4: `status <> 'passed'`; FK NULL iff reason `no_rollback_run`; FK NOT NULL for the other two reasons.
- seq 6/7/8: `status='not_observed'`, exact reason per §2.4, all FKs NULL.
- **seq 5 — the only pass path — `passed` requires ALL of:** `handover_id` NOT NULL; the handover's `status='recorded_complete'`; and **latest-wins** — `NOT EXISTS` a same-`(tenant_id, project_id)` `ops_support_handovers` row ordering strictly after it by `(created_at, id)`, mirroring `latest_handover` exactly, so an older complete handover cannot override a newer incomplete one (v4 defect 4). The guard proves exactly the scoped claim of §0 — that the latest recorded row says complete — and nothing about whether a handover happened.

Because `monitoring_status_snapshots` and `ops_support_handovers` are immutable append-only, id-identity implies content-identity — the guard needs no content digest.

**Deferred count/tally trigger (both child tables, per §2.4 and §2.7):** exactly 8 criteria and 8 improvements; seqs form the exact set 1..8 on each side; the four status counters equal the recomputed child tallies; `extension_required = (passed_count < 8)`.

Forgery tests (direct SQL) must fail for: `passed` on **every seq except 5**, including the `https://localhost` scenario of §0.3 (a directly inserted `connector_verified` snapshot plus a matching revised declaration must still not yield a seq-3 pass, because seq-3 `passed` does not exist); seq-3 rows citing a snapshot for a non-declared target; seq-5 `passed` with `recorded_incomplete` or with a superseded handover; duplicate `seq`; tampered status counters; window with a mismatched `policy_digest`, a backdated `as_of`, a non-declared / missing / wrong-category `monitoring_target_ref`, `extension_required=false`, or a bad `extends_window_id`.

### 2.7 Improvement inventory (descriptive; no source-system writes)

Eight children, `improvement_count=8`. Typed nullable FKs `findings_report_id`, `cost_forecast_run_id`.

| seq | class | status | reason | binding |
|---|---|---|---|---|
| 1 | `lessons_learned` | `not_observed` | `no_lessons_store` | none |
| 2 | `recurring_failure_patterns` | `observed` | `incident_category_recurrence` | `metric_int` = count of incident categories with ≥2 rows (0 valid); no FK |
| 3 | `agent_evals` | `not_observed` | `no_live_eval_update` | none |
| 4 | `prompt_templates` | `not_observed` | `no_prompt_store` | none |
| 5 | `domain_pack_gaps` | `observed` iff `domain_pack` declared, else `not_observed` | `domain_pack_declared` / `no_domain_pack_declaration` | presence only |
| 6 | `test_oracle_gaps` | `observed` iff a latest findings report exists, else `not_observed` | `acceptance_without_oracle_count` / `no_findings_report` | `findings_report_id` when observed; `metric_int` = `G_ACCEPTANCE_WITHOUT_ORACLE` count |
| 7 | `cost_forecasts` | `observed` **only when `coverage.run_present`**, else `not_observed` | `forecast_cited_not_refreshed` / `no_cost_forecast_run` | `cost_forecast_run_id` when observed; `refresh_posture='recorded_not_refreshed'` |
| 8 | `connector_reliability_scores` | `not_observed` | `no_connector_score_store` | none |

Improvement guard: `CHECK (seq BETWEEN 1 AND 8)`, `UNIQUE (tenant_id, window_id, seq)`, and a `(seq, improvement_class)` pairing CHECK, so eight rows means the exact set 1..8 with fixed classes; seq 1/3/4/8 locked to `not_observed`; seq 6 `observed` ⇒ `findings_report_id` NOT NULL; seq 7 `observed` ⇒ `cost_forecast_run_id` NOT NULL. Never UPDATE evals, prompts, domain packs, oracles, or forecasts.

### 2.8 Window row, extension, closure, identity

Status `open` only (no `closed` value exists). Also persisted: `as_of`; `clock_basis='transaction_timestamp_not_production_uptime'`; `assessor_subject` (bounded non-blank), `assessor_actor_type` (nullable), `assessor_provenance ∈ {caller_supplied_unverified, request_authenticated}` derived from `TenantContext.actor` (subject/type when present, else the caller label at the unverified tier); `follow_up_posture ∈ {none, required_not_executed}`; `extension_required` boolean; `extends_window_id` nullable composite FK.

`extension_required` is derived by the deferred trigger as `passed_count < 8` (always true, since seq 1/2/4/6/7/8 can never pass) and is not caller-assertable. It means the spec-2424 obligation is **required and not executed** — it is not an extension. An extension exists only when a later run is created with an explicit `extends_window_id` naming a prior run whose `extension_required` is true.

`attempt_closure(context, project_id, *, actor)` **always persists a row** when a latest window exists (missing window ⇒ error, no write). It does **not** call the raising `assert_project_not_stopped`; instead, under READ COMMITTED it takes `SELECT projects … FOR UPDATE`, reads the latest `emergency_stop_events.state_after`, then inserts. First match wins:

1. latest stop `state_after='active'` → `refused_latch_active`
2. `context.actor IS NULL` → `refused_unauthenticated`
3. `context.actor.subject = window.assessor_subject` and both provenances are `request_authenticated` → `refused_same_actor`
4. else → `refused_incomplete_criteria`

All four are reachable and each persists a row. There is no `approved`/`closed` result code; window status never changes. Spec's "pre-approved closure rule" is deliberately not implemented.

### 2.9 Idempotency and retry

**Request digest** (idempotency identity), canonical JSON: `{ruleset_version, project_id, extends_window_id, assessor_subject, assessor_actor_type, assessor_provenance}`. Excludes `as_of` and every live observation, so a retry is stable; a different principal reusing a key mismatches and raises `StabilizationIdempotencyConflict`. `UNIQUE (tenant_id, project_id, idempotency_key)`.

**Input digest** (snapshot identity): `as_of`, `policy_digest`, `monitoring_max_age_hours`, `deployment_max_age_hours`, the eight criterion tuples, the eight improvement tuples.

Assess runs at **REPEATABLE READ**. The wrapper retries the **entire** transaction up to 5 times with bounded jitter on `40001`, `40P01`, **and** the invisible-winner condition (a committed winner not yet visible to this snapshot). `StabilizationIdempotencyRace` is raised only after the bound is exhausted. A two-session DB race test is required. Closure runs at READ COMMITTED with the project row lock.

### 2.10 Public API and schema

Owns `tenant_scope`; no caller `session`, no caller `as_of`, no broker:

- `assess_stabilization(context, project_id, *, actor, idempotency_key, extends_window_id=None)`
- `attempt_closure(context, project_id, *, actor)`
- `latest_stabilization(context, project_id)` / `history_stabilization(context, project_id, *, limit)`

Migration `0058_stabilization` (`down_revision=0057`) adds four tenant-owned tables — `ops_stabilization_windows`, `ops_stabilization_criterion_results`, `ops_improvement_results`, `ops_stabilization_closure_attempts` — all RLS ENABLE+FORCE + `tenant_isolation`, SELECT/INSERT only, append-only block triggers, `UNIQUE (tenant_id, window_id, seq)` on both child tables, the deferred count/tally trigger of §2.6, plus the three additive UNIQUE targets in §2.5 and the IMMUTABLE function `stabilization_policy_digest(jsonb)` (§2.2). Populated downgrade refused (`cannot downgrade Slice 59`); empty `0058→0057→0058` round-trip.

Files: `app/ops/stabilization.py` (pure), `app/ops/stabilization_db_checks.py`, `app/ops/stabilization_ddl.py`, `app/ops/stabilization_service.py`, `app/models/ops_stabilization.py`, `app/repositories/ops_stabilization.py`. House 500-line cap respected.

---

## 3. Open decisions (Option A, v6)

| ID | Option A |
|---|---|
| OD-59-1 | Non-closing. `open` only. `all_criteria_passed` structurally unreachable. Slice 58 residual stays open. |
| OD-59-2 | `0058_stabilization` from verified head `0057`. |
| OD-59-3 | Immutable `policy_snapshot` + SQL digest function + NOT NULL `category_id`. No numeric error-budget parse. |
| OD-59-4 | **Seq 5 is the only pass path**, guarded by status + handover latest-wins and claim-scoped to the latest record. Seq 3 and seq 4 have no `passed` (their positive rungs rest on runtime-writable evidence tiers); seq 1/2/6/7/8 locked non-passing. Fixed seq sets, per-seq keys/classes, and derived status counters are DB-enforced; `as_of` is DB-generated. |
| OD-59-5 | No fabricated coverage-start. Seq 1 always `not_evaluable`. |
| OD-59-6 | `extension_required` / `required_not_executed`; extension only via explicit `extends_window_id`. No auto-incident, no Jira. |
| OD-59-7 | Closure persists always; ladder latch → unauthenticated → same-actor → incomplete; no approved code. |
| OD-59-8 | No HTTP, broker, git, or new MATRIX keys. |
| OD-59-9 | Assessor identity in the request digest; retry covers `40001`/`40P01`/invisible-winner; race only after the bound. |
| OD-59-10 | Frozen files in §1. Import `gate10_conjunction_passed`; pass the DB-generated `as_of` into the existing coverage methods; freshness limits are recorded and digested for transparency only and are read by no guard, since no pass path depends on them. |

No §12 halt. Residual capabilities are open, not blockers for landing this assessment store.

---

## 4. Tests

**Docker-free:** missing/invalid declaration raises with no writes; unknown keys and `duration_days: custom` refused; seq 1/2 always `not_evaluable`; seq 6/7/8 always `not_observed`; seq 3 ladder over all seven outcomes, incl. verified+valid+active+fresh ⇒ `not_evaluable` / `monitoring_active_app_derived_not_db_provable`; seq 4 three-way mapping incl. conjunction-true ⇒ `not_evaluable`; seq 5 three-way, plus a newer incomplete handover downgrading an older complete one; improvement seq 7 `observed` iff `run_present`; request digest changes with assessor identity and not with `as_of`; wrappers expose no `session`; no `broker_call`/git/subprocess; A5, readiness, and go-live `before == after`; Slice 58 residual still open.

**DB:** RLS + append-only on all four tables; 8+8 deferred count-match. Direct-SQL forgery must be rejected for: `passed` on seq 1/2/3/4/6/7/8; the §0.3 scenario end to end (insert a `connector_verified` snapshot for `https://localhost/x`, revise the declaration to that URL, then attempt a seq-3 pass — rejected because the status does not exist); a seq-3 row citing a snapshot for a non-declared target; seq-5 `passed` with `recorded_incomplete` and with a superseded handover; duplicate `(window_id, seq)` on both child tables; tampered status counters and `extension_required=false`; a window whose declaration is missing, wrong-category, or wrong-provider; a window with a backdated `as_of`, a mismatched `policy_digest`, out-of-range age columns, or a bad `extends_window_id`. Positive control: seq-5 `passed` accepted for the latest `recorded_complete` handover, and a full eight-criterion run accepted with `passed_count` ∈ {0,1}. Also: category revise leaves the historical snapshot and digest unchanged; all four closure refusals persist a row and leave status `open`; idempotency conflict on a different principal; two-session REPEATABLE READ race; empty and populated `0058` migrate/downgrade; frozen hashes unchanged; audit carries no owner/journey/summary/URL.

**CI pyright:** add Slice 59 paths; keep 55/56/57/58; do not lower the bar.

---

## 5. Must NOT claim

§25.4 exited or Slice 59 roadmap exit satisfied; backup/restore validated; production live; an incident-free streak proved; monitoring confirmed active, or rollback currency proved, by this store; **that a support handover actually occurred or was signed by an authority** (seq 5 proves only that the latest recorded row says complete); self-healing/§26.6 closed; a human signature or release-authority sign-off; evals/prompts/domain packs/oracles/forecasts updated; auto tickets executed; `can_go_live_autonomously=true`; A5/readiness bump; a stored `gate_eligible` flag alone as proof.

---

## 6. Sequence after APPROVE

Stamp OD-59-* = Option A (v6). Branch `feat/slice-59-stabilization` from `main` `33ee561`. Tests land with the slice. Validate `uv sync` / ruff / pyright / `make test` / `make test-db`. Sol code review. Docs must say **non-closing**. PR quoting the APPROVE verbatim with real counts, green CI, squash-merge, HANDOFF close-out. Slice 60 next.

---

## 7. Exit

Plan APPROVE + code APPROVE + CI green + merge of a **stabilization-window assessment store**. §25.4, §26.6, and the roadmap Slice 59 exit remain open. A5, readiness, and go-live unchanged.

---

## Appendix S — Muhasabah

- v1 REJECT: streak proof, mutable policy pointer, incomplete matrices, split clocks, unreachable closure refusals, dishonest `extension_recorded`, unspecified idempotency/race.
- v2 REJECT: `projects.created_at` is not coverage; polymorphic `source_ref`; CHECKs cannot prove source eligibility; incomplete matrices; assessor missing from the request digest; retry wording.
- v3 REJECT: seq-3 guard not bound to the declared target; seq-4 guard cannot prove full gate-10 currency; ambiguous freshness source.
- v4 REJECT: seq-3 binding NULL-unsafe, missing the category filter, and not resolver-equivalent; `as_of` and the age limit were caller-writable, so freshness was not DB-proven; 8+8 row counts did not pin unique seqs, fixed keys, or derived counters; seq 5 ignored handover latest-wins. (Sol accepted the seq-4 removal as honest and non-authorizing.)
- v5 fixed defects 2–4 (accepted): `as_of = transaction_timestamp()`; unique seqs, `(seq, key)` / `(seq, class)` pairing CHECKs, trigger-derived counters and `extension_required`; handover latest-wins with the presence-only limit written into both the allowed claim and the must-not-claim list.
- v5 REJECT on defect 1: the resolver-equivalence argument was wrong. `0030_monitoring_evidence.py` grants `uaid_app` INSERT and permits `connector_verified` under URL CHECKs far weaker than `parse_and_validate_status_url`, so a forged `https://localhost` snapshot plus a matching declaration would have satisfied every seq-3 clause. A second stale-text defect flagged OD-59-10.
- v6: **seq-3 `passed` removed**, for the same reason seq 4's was — the positive rung rested on an evidence tier the runtime role can write directly, and mirroring the validator in PL/pgSQL would fork it. Seq 5 is the only pass path and its claim is scoped to exactly what the guard proves. Freshness columns are demoted to recorded-only and OD-59-10 rewritten to match.
- Standing limitations, stated not hidden: monitoring activity and rollback currency are app-derived observations, never recorded as passed; seq 5 proves a record, not an event.
