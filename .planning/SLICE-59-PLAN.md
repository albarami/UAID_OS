# Slice 59 Plan — Stabilization-window assessment (does not close §25.4 / §26.6) (§25.3 / §25.4)

**Status:** AWAITING PLAN APPROVAL (v3) — v1 and v2 REJECT by GPT-5.6 Sol agent `8cd454f8-3cdf-43d5-84b8-1b8802e2fcab`. Consecutive REJECT count = 2. OD-59-1…10 = Option A as restated.

**Seats (binding):** Builder Cursor Grok 4.6. Reviewer GPT-5.6 Sol (sole approval). Builder sub-agents may not approve.

**Author persona:** Senior SRE / incident-response architect applying fail-closed evidence-integrity discipline.

**Slice closure:** Non-closing. Status vocabulary is `open` only. Backup/restore never validated. Slice 58 residual actuators stay open. Seq 1 never `passed`/`failed` this slice (no production coverage clock).

**Execution authorization:** Plan-only until APPROVE. No backup connector, git, broker, Jira, eval/prompt/oracle/forecast writes, go-live flip, A5/readiness bump, or §2.6 bypass.

---

## Coordinator standing rulings (2026-08-22; verbatim; binding)

1. Slice 59 Salim gate REMOVED. Run 57→63 continuously.
2. Builder Grok 4.6; Reviewer GPT-5.6 Sol.
3. pyright mandatory.
4. Hard stops unchanged.

---

## Sanad / citation key

- Spec §25.1 (2355–2361), §25.3 (2391–2402), §25.4 (2404–2424), §26.6 (2510), §27.13 (2812–2828).
- Schema asset `stabilization_window_policy.yaml`.
- Slice 56 OD-56-4: do not parse `error_budget_threshold` as a number.
- Slice 58 frozen `gate10_conjunction_passed`; `coverage_with_run(..., as_of=)` already exists.
- Gate #11 `production_autonomy.py:1005-1028`. Do not call `evaluate`.
- `TenantContext.actor`. Alembic head `0057` → migration **`0058_stabilization`**.
- Baseline `main` `33ee561`. Frozen hashes unchanged from v2 §1.

---

## 0. Honesty crux

`projects.created_at` is project age, not incident-ledger coverage and not post-deployment uptime. There is no provenance-bound stabilization clock. Seq 1 therefore stays `not_evaluable`.

Claim allowed:

> UAID recorded a tenant-owned stabilization-window assessment against an immutable §27.13 policy snapshot. Seq 1 is not_evaluable: no production coverage clock exists. Backup/restore, p95, and post-launch security alerts stay not_observed. Monitoring and rollback may pass only when typed FKs point at rows a DB guard proves eligible at the transaction as_of. Closure attempts are persisted refusals. Follow-up is required_not_executed; a later run is an extension only when explicitly linked. This does not exit §25.4 or close §26.6.

---

## 1. Frozen files

Unchanged from v2 (byte-stable hashes in v2 §1). Do not modify them, `rollback_verifications.py`, or `emergency_controls.py`. Additive `resolve_declared_stabilization_window` on `project_repo.py` is allowed. Additive UNIQUE targets in `0058` are allowed.

---

## 2. Design

### 2.1 Contracts

`slice59.stabilization.v1` / `slice59.improvement_inventory.v1` / `ruleset_version='slice59.v1'`. A5 `slice54.v1`; readiness `slice20.v1`.

### 2.2 Policy snapshot

Exact §27.13 keys under `data.stabilization_window` (v2 §2.2 bounds). Missing/invalid ⇒ no writes.

Persist `category_id` NOT NULL (composite FK to `uq_intake_categories_id_proj_tenant`), `policy_snapshot` JSONB, `policy_digest`. SQL function `public.stabilization_policy_digest(jsonb) RETURNS text` (STABLE, `sha256:` + encode(sha256(canonical jsonb), 'hex')). App stores the function’s result. BEFORE INSERT/ guard: `policy_digest = stabilization_policy_digest(policy_snapshot)`.

Do not parse `error_budget_threshold` as a number.

### 2.3 Single `as_of`

`as_of = transaction_timestamp()` once. Pass into existing `coverage_with_run(project_id, as_of=as_of)` and `coverage_for_project(project_id, as_of=as_of)` and gate-#11 freshness. No new rollback methods.

### 2.4 Eight criteria

| seq | criterion | status | reason / pass path |
|---|---|---|---|
| 1 | `zero_open_critical_incidents_for_days` | **always `not_evaluable`** | `no_production_coverage_clock`. DB CHECK. Metric NULL. No incident-event reconstruction this slice. |
| 2 | `error_budget_under_threshold` | always `not_evaluable` | `error_budget_threshold_unparsed_string` |
| 3 | `monitoring_confirmed_active` | see below | typed FK `monitoring_snapshot_id` |
| 4 | `rollback_blockers_open` | see below | typed FK `rollback_verification_run_id` |
| 5 | `support_handover_complete` | handover latest | typed FK `handover_id` |
| 6 | `backup_restore_validated` | always `not_observed` | `no_backup_restore_source` |
| 7 | `p95_latency_within_slo` | always `not_observed` | `no_latency_slo_source` |
| 8 | `no_unresolved_security_alerts` | always `not_observed` | `no_post_launch_security_alert_source` |

**Seq 3:** no declared URL → `not_observed` / `no_monitoring_declaration`, FK NULL. Declared, no snapshot → `not_observed` / `monitoring_declared_but_no_evidence`. Snapshot unverified → `failed` / `monitoring_observed_unverified`. Stale vs `as_of` → `failed` / `monitoring_evidence_stale`. Unreadable (`response_valid=false`) → `not_evaluable` / `monitoring_evidence_unreadable`. Inactive → `failed` / `monitoring_or_alerts_inactive`. Else `passed` / `monitoring_and_alerts_active_verified` with FK set.

**Seq 4:** `coverage_with_run` returns no run → `not_observed` / `no_rollback_run`, FK NULL. Run present but `gate10_conjunction_passed(coverage)` is false → `failed` / `rollback_path_not_current`, FK still set to that latest run. Conjunction true → `passed` / `rollback_path_current`, FK set. Not a Slice-24 issue count.

**Seq 5:** none → `not_observed` / `no_handover_record`. `recorded_incomplete` → `failed` / `handover_recorded_incomplete`. `recorded_complete` → `passed` / `handover_recorded_complete`.

### 2.5 Typed FKs, not a polymorphic `source_ref` (v2 defect 2)

Criterion row columns (all nullable UUIDs except as CHECKed per seq):

- `monitoring_snapshot_id`
- `rollback_verification_run_id`
- `handover_id`

`0058` adds additive composite UNIQUE targets (do not rewrite 0030/0056):

- `monitoring_status_snapshots (id, project_id, tenant_id)`
- `ops_support_handovers (id, project_id, tenant_id)`
- `intake_findings_reports (id, project_id, tenant_id)` (improvement seq 6)

Rollback runs already have `uq_rbvr_id_project_tenant`. Cost forecast runs already have `uq_cfr_id_project_tenant`.

Per-seq nullness: seq 3 FK set iff status in `{passed, failed, not_evaluable}` with a snapshot; seq 4 FK set iff a latest run exists; seq 5 FK set iff a handover exists; seq 1/2/6/7/8 all three FKs NULL.

### 2.6 DB guard (v2 defect 3)

BEFORE INSERT `ops_stabilization_criterion_results_guard` + window guard. Direct-SQL forgery tests required.

Window guard:

- `policy_digest = stabilization_policy_digest(policy_snapshot)`
- `status = 'open'`
- `extends_window_id` NULL OR (same tenant/project AND prior.`extension_required` IS TRUE AND prior.id <> NEW.id)

Criterion guard (loads parent `as_of`):

- seq 1: status=`not_evaluable`, reason=`no_production_coverage_clock`, all typed FKs NULL
- seq 2: status=`not_evaluable`, reason=`error_budget_threshold_unparsed_string`, FKs NULL
- seq 6/7/8: status=`not_observed`, exact reasons, FKs NULL; never `passed`
- seq 3 `passed`: monitoring FK NOT NULL AND snapshot.provenance=`connector_verified` AND snapshot.response_valid AND snapshot.overall_active AND snapshot.observed_at <= parent.as_of AND (parent.as_of - snapshot.observed_at) <= `settings.monitoring_evidence_max_age_hours` (the trigger reads the setting GUC or a copied integer column `monitoring_max_age_hours` on the parent, default 24, CHECK 1..168). Unverified snapshot cannot be `passed`.
- seq 4 `passed`: rollback FK NOT NULL AND imported conjunction inputs on that run: `gate_eligible`, `drill_result='passed'`, `phase_count=5`, `evidence_consistent`, `execution_observation='connector_observed_ci'`, `attempt_status` not in `{failed,refused}`, and the run’s staging snapshot `observed_at` fresh vs parent.as_of using `settings.deployment_evidence_max_age_hours` (copied `deployment_max_age_hours` on the parent). A `passed` row whose run fails those predicates is rejected. App still requires full `gate10_conjunction_passed` including binding_current before writing `passed`; the guard is the DB backstop for stored pass-shaped columns + freshness, not a second Python evaluator.
- seq 5 `passed`: handover FK NOT NULL AND handover.status=`recorded_complete`

### 2.7 Improvement matrix (v2 defect 4 remainder)

Eight children. Typed nullable FKs: `findings_report_id`, `cost_forecast_run_id`.

| seq | class | status | reason | source |
|---|---|---|---|---|
| 1 | `lessons_learned` | `not_observed` | `no_lessons_store` | none |
| 2 | `recurring_failure_patterns` | `observed` | `incident_category_recurrence` | metric_int = count of categories with ≥2 incidents (0 allowed); no FK |
| 3 | `agent_evals` | `not_observed` | `no_live_eval_update` | none |
| 4 | `prompt_templates` | `not_observed` | `no_prompt_store` | none |
| 5 | `domain_pack_gaps` | `observed` if domain_pack declared else `not_observed` | `domain_pack_declared` / `no_domain_pack_declaration` | none (presence only) |
| 6 | `test_oracle_gaps` | `observed` iff latest findings report exists else `not_observed` | `acceptance_without_oracle_count` / `no_findings_report` | FK to findings report when observed; metric_int = count of `G_ACCEPTANCE_WITHOUT_ORACLE` |
| 7 | `cost_forecasts` | **`observed` only when `coverage.run_present`** else `not_observed` | `forecast_cited_not_refreshed` / `no_cost_forecast_run` | FK to that run when observed; `refresh_posture='recorded_not_refreshed'` |
| 8 | `connector_reliability_scores` | `not_observed` | `no_connector_score_store` | none |

Never UPDATE source systems. Improvement CHECKs lock seq 1/3/4/8 to `not_observed`. Seq 7 `observed` ⇒ `cost_forecast_run_id` NOT NULL.

### 2.8 Window / extension / closure / identity

As v2: status `open` only; `assessor_subject` / `assessor_actor_type` / `assessor_provenance` from `TenantContext.actor`; `follow_up_posture='required_not_executed'` + `extension_required` when any criterion not `passed`; explicit `extends_window_id` only.

Closure always persists; no raising `assert_project_not_stopped`; ladder latch → unauthenticated → same-actor → incomplete. No `approved`.

### 2.9 Idempotency + retry (v2 defects 5–6)

**Request digest** canonical JSON:

`{ruleset_version, project_id, extends_window_id, assessor_subject, assessor_actor_type, assessor_provenance}`

Excludes `as_of` and live observations. Different principals reusing a key ⇒ digest mismatch ⇒ `StabilizationIdempotencyConflict`. Unique `(tenant_id, project_id, idempotency_key)`.

**Input digest** hashes `as_of`, `policy_digest`, criterion tuples, improvement tuples.

Assess: REPEATABLE READ. Retry the **entire** transaction up to 5 times on `40001`, `40P01`, **and** the invisible-winner condition (select-after-insert miss). Only after those bounded fresh-transaction retries fail raise `StabilizationIdempotencyRace`. Two-session race test required.

Closure: READ COMMITTED + `SELECT projects … FOR UPDATE`.

### 2.10 API + schema

Public API as v2. Four tables as v2 plus additive UNIQUEs in §2.5. `criterion_count=8`, `improvement_count=8`, dual deferred count-match. Populated downgrade refused. Empty `0058→0057→0058`.

---

## 3. Open decisions (Option A v3)

| ID | Option A |
|---|---|
| OD-59-1 | Non-closing. `open` only. Seq 1 always `not_evaluable` (`no_production_coverage_clock`). Slice 58 residual stays open. |
| OD-59-2 | `0058_stabilization` from `0057`. |
| OD-59-3 | Immutable policy snapshot + SQL digest function. No numeric error-budget parse. |
| OD-59-4 | Typed FKs + additive UNIQUEs + criterion/improvement guards in §2.5–2.7. Shared `as_of`. |
| OD-59-5 | No fake coverage-start. Seq 1 never passes this slice. |
| OD-59-6 | `extension_required` / explicit `extends_window_id`. No auto-incident. |
| OD-59-7 | Closure persist-always ladder. No approved code. |
| OD-59-8 | No HTTP/broker/git/new MATRIX keys. |
| OD-59-9 | Request digest includes assessor identity. Retry 40001/40P01/invisible-winner; race only after bound. |
| OD-59-10 | Frozen files in §1. Import `gate10_conjunction_passed`. |

No §12 halt.

---

## 4. Tests

Docker-free: seq 1 always not_evaluable (zero incidents does not pass); seq 2/6/7/8 locked; seq 4 no-run vs failed vs passed mapping; seq 7 observed iff `run_present`; digest includes assessor; no session/broker/git; A5/readiness/go-live before==after.

DB: RLS/append-only; 8+8 count-match; forged seq-1/2/6 passed fail; forged seq-3 passed on unverified snapshot fail; forged seq-4 passed on failed/refused run fail; digest mismatch fail; bad extends_window_id fail; category revise leaves snapshot; closure four refusals persist; two-session retry; migrate empty/populated; frozen hashes; audit safe-metadata only.

CI pyright: add Slice 59 paths; keep 55–58; do not lower the bar.

---

## 5. Must NOT claim

§25.4 exited; backup validated; production live; seq 1 streak proved; self-healing closed; human signature; evals/prompts/oracles/forecasts updated; auto tickets executed; go-live true; stored `gate_eligible` alone without the app conjunction.

---

## 6–7. Sequence / exit

After APPROVE: `feat/slice-59-stabilization` from `main`. Docs non-closing. Slice 60 next. Roadmap Slice 59 exit remains open.

---

## Appendix S — Muhasabah

v1 REJECT: seven control-flow/honesty defects. v2 REJECT: fake coverage-start; polymorphic FK; CHECKs that cannot prove source eligibility; incomplete matrices / seq-1 digest; assessor missing from request digest; retry/race wording. v3: seq 1 locked not_evaluable; typed FKs + UNIQUEs; INSERT guard; cost forecast observed iff `run_present`; assessor in request digest; invisible-winner inside the bounded retry loop.
