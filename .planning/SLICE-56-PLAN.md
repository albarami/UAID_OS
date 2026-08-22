# Slice 56 Plan — Post-launch monitoring (§25.1 signal set)

**Status:** IMPLEMENTED — independent plan APPROVE (agent `8ca43267-57a2-4ff1-aac5-802f30310b52`) and independent code APPROVE (agent `160c2a06-f414-4222-876f-0bcc59029525`). OD-56-1…10 = Option A. Merge SHA is stamped in HANDOFF after squash.

**Bound open decisions:**

- OD-56-1 = Option A
- OD-56-2 = Option A
- OD-56-3 = Option A
- OD-56-4 = Option A
- OD-56-5 = Option A
- OD-56-6 = Option A
- OD-56-7 = Option A
- OD-56-8 = Option A
- OD-56-9 = Option A
- OD-56-10 = Option A

**Seats (binding, recorded in `.planning/HANDOFF.json` before planning):**
- **Builder:** Cursor Grok 4.6 (Grok family) — resumes.
- **Reviewer:** GPT-5.6 Sol (`gpt-5.6-sol-max`, GPT family).

**Author persona:** Senior SRE / observability-platform architect applying fail-closed evidence-integrity discipline.

**Execution authorization:** Plan-only until independent plan APPROVE. Production deploy, `can_go_live_autonomously` flip, A5 ruleset bump, incident workflow (Slice 57), and stabilization closure (Slice 59) remain out of scope.

---

## Coordinator standing rulings (2026-08-22; verbatim; binding)

Salim reviewed merged PR #100 (`15d0e75`) and released the Slice 55→56 transition:

1. Slice 56 migration number = `0055` (`0054` is occupied by Slice 55). Sequential numbering continues from whatever head exists at plan time — never assume.
2. Builder/reviewer seats must be different model families and must be stated in `HANDOFF.json` before planning. Done: Grok builds; Sol reviews.
3. Standing cadence for Slices 56–59: full loop per slice (plan → plan review → build → validate → code review → docs → PR → merge), no Salim gate required per slice — but log each merge in `HANDOFF.json` and HALT for the Salim gate again after Slice 59, before ecosystem slices 60–63.
4. pyright is now part of validation every slice; a slice that cannot run it logs a blocker, never skips silently.

Open decisions in §4 become **binding on independent plan APPROVE**. Hard stops still HALT: spec edits, go-live default-true, budget figures, secrets, §2.6 bypass, weakening tests/CI, force-push.

---

## Sanad / citation key

- **Spec** — `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md` (§2.1, §2.6, §19, §23.3, §25.1–§25.4, §26.6, §27.13, App. B #11).
- **Roadmap** — `.planning/GO-LIVE-END-TO-END-ROADMAP.md` Rev 16 (Slice 56 at 559–569; §11 at 805–826).
- **Stabilization schema** — `docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/stabilization_window_policy.yaml` (`error_budget_threshold: string` only; Spec:2812–2828).
- **Slice 31** — `app/release/monitoring_evidence.py` (alerts-active, not SLO uptime).
- **Cost stop** — `app/cost.py` `evaluate_stop` (fail-closed; missing budget ⇒ STOP `no_budget`; threshold `>=`).
- **Runs** — `app/models/project_run.py` statuses `created|running|paused|blocked|completed|failed` (no `superseded`).
- **Count-match prior art** — `migrations/versions/0036_semantic_contradictions.py` (parent-side AND child-side DEFERRABLE triggers).
- **CI** — `.github/workflows/ci.yml` (no pyright step today).
- **Baseline** — `HEAD`/`origin/main` at branch creation `be93143`; Alembic head `0054`/`down_revision=0053`; no `app/ops/`.

---

## 0. Honesty crux

### 0.1 Spec says “after production deployment.” Production was not deployed.

§25.1 opens after production deployment (Spec:2349). §23.3 places `monitor_and_stabilize()` after `deploy_production()` (Spec:2209–2211). Slice 55 recorded only `decided_not_executed` (PR #100). Slice 56 must not claim the launched system is observable.

Claim allowed:

> UAID assessed all eleven §25.1 signal classes, persisted one complete run with per-class source binding and threshold provenance, and evaluated a threshold only when a source-bound threshold existed. Missing live sources are `not_observed`. This does not prove production is live, that monitoring is adequate, or that incidents were opened.

### 0.2 Gate #11 ≠ §25.1

Slice 31 / App. B #11 prove **≥1 active monitor AND ≥1 active alert rule** on a declared `status_url`. That is not uptime, error rate, latency, or the rest of §25.1. Adjacent stores (deployment snapshots, release findings, PM mappings) are **context only** — they must not be written as those operational classes.

### 0.3 Tickets/incidents vs Slice 57

§25.1 requires monitoring those classes. Slice 57 owns create/triage/handover. This slice records `incident_reports` as `not_observed` / `no_incident_store` and `support_tickets` as `not_observed` / `no_support_ticket_source`. No sample may overwrite that structural absence for `incident_reports`.

### 0.4 Truth tiers

| Tier | Example | Proves | Must not be called |
|---|---|---|---|
| **CALLER_SUPPLIED_UNVERIFIED** | Fixture sample with metric **and** threshold | What the caller asserted | Live telemetry or a real SLO |
| **SYSTEM_DERIVED_LEDGER** | Slice-7 stop vs recorded budget; distinct `run_id` from immutable `run_steps` with `event_type='run_failed'` | Named arithmetic over named tables | Customer SLO, Datadog, pager, post-launch security |
| **DB_PROVEN_RUN_GRAPH** | One run + exactly 11 children; dual deferred count-match | The set was assessed | Adequate monitoring or production readiness |
| **THRESHOLD_EVALUATED** | `ok`/`breached` only from a persisted source-bound threshold | That comparison | Alert delivery, incident, or coverage |

---

## 1. Verified baseline

Same as v1: feature branch from `be93143`; Alembic `0054`; no `app/ops/`; A5 `slice54.v1`; readiness `slice20.v1`; `can_go_live_autonomously` literal `False`; recorded Slice-55 counts 1150 / 855; full-repo pyright 3051 pre-existing. Plan task did not re-run suites.

---

## 2. Existing stores — context vs signal

| Store | May feed a §25.1 class this slice? | Why |
|---|---|---|
| Slice 7 cost ledger + budget + `evaluate_stop` | **Yes — `cost_anomalies` only** | The class *is* cost; the threshold *is* the recorded budget cap(s) compared via pure `evaluate_stop`. |
| Immutable `run_steps` with `event_type='run_failed'` | **Yes — `job_failures` only, as UAID-runtime count of distinct `run_id`** | Honest local-runtime jobs. Not a customer job SLO. No default breach. |
| Slice 31 monitoring snapshots | **No** | Alerts-active ≠ uptime / error / latency. |
| Slice 30 deployment-target snapshots | **No** | Point-in-time `target_available` is not uptime. |
| Slice 23/44 release findings | **No** | Pre-release/security-scan findings are not post-launch security alerts. |
| Slice 34 PM mappings | **No** | Mappings are not support tickets (and have no title). |
| Slice 48 reviewer QA | **No** | Challenge-corpus rates are not live model drift. |
| Slice 51 cost forecast | **No** | Forward estimate, not an anomaly observation. |
| Incident store | **Does not exist** | `incident_reports` = `not_observed`. |

No optional category read. Do not parse `error_budget_threshold`. OD-56-4 is the closed allowlist.

---

## 3. Design

### 3.1 Contracts

- `slice56.ops_signals.v1`
- `slice56.threshold_eval.v1` — evaluate only when a threshold row is source-bound.
- Run `ruleset_version='slice56.v1'`.
- A5 stays `slice54.v1`. Readiness stays `slice20.v1`.

### 3.2 Eleven classes (spec order, seq 1–11; no `other`/`unknown`)

`uptime`, `error_rates`, `latency`, `job_failures`, `security_alerts`, `user_journey_failures`, `data_quality_issues`, `cost_anomalies`, `model_output_drift`, `support_tickets`, `incident_reports`.

### 3.3 Observation status (exactly three; sum to 11)

- `observed` — ledger-derived (`cost_anomalies` or `job_failures` as specified).
- `caller_supplied_unverified` — accepted sample (metric **and** threshold both present).
- `not_observed` — successful empty/absent source.

`observed_uaid_runtime` is **not** a status. Job failures use `observed` + `source_kind='uaid_runtime'`.

Parent counters (disjoint, CHECK sum = 11):

- `observed_count`
- `caller_supplied_count`
- `not_observed_count`

`breached_count` is **independent**: number of children with `threshold_state='breached'` (0..11), validated by the deferred child match, not by adding to the status sum.

### 3.4 Source-binding matrix (every child row)

Persisted on **every** child:

| Field | Type / bound |
|---|---|
| `truth_tier` | `none` \| `system_derived_ledger` \| `caller_supplied_unverified` |
| `source_kind` | `none` \| `cost_ledger` \| `uaid_runtime` \| `caller_supplied` |
| `source_table` | `none` \| `cost_events_and_budgets` \| `run_steps` \| `caller_sample` |
| `source_ref` | NULL, or a UUID (never a URL). Cost/job use NULL (aggregates). |
| `source_digest` | NULL or `sha256:` + 64 hex |
| `window_kind` | `none` \| `cumulative_project` \| `caller_declared` |
| `window_start` | NULL or timestamptz |
| `window_end` | NULL or timestamptz (`as_of` bound) |
| `reason_code` | see §3.5 (≤128, non-blank, known set) |
| `threshold_provenance` | `none` \| `recorded_budget` \| `caller_supplied_unverified` |
| `threshold_kind` | `none` \| `cost_stop` \| `caller_count` \| `caller_ratio` \| `caller_ms` |
| `threshold_int` / `threshold_ratio` / `threshold_money` / `threshold_money_daily` | nullable; CHECKs by `threshold_kind` / class |
| `metric_kind` | `none` \| `count` \| `ratio` \| `milliseconds` \| `money` |
| `metric_int` | INT 0..2147483647 NULL |
| `metric_ratio` | NUMERIC(8,6) NULL, **only** when `metric_kind='ratio'` then `BETWEEN 0 AND 1` |
| `metric_money` | NUMERIC(18,6) NULL, ≥0 (cost **total** spent; **not** capped at 1) |
| `metric_money_daily` | NUMERIC(18,6) NULL, ≥0 (cost **daily** spent; NULL on non-cost rows) |
| `threshold_state` | `not_evaluable` \| `ok` \| `breached` |

Input digest (on the parent, **snapshot identity**) hashes the canonical JSON of: `ruleset_version`, `project_id`, `as_of` (UTC), then the eleven children in seq order each as `(signal_class, observation_status, truth_tier, source_kind, source_table, source_ref, source_digest, window_kind, window_start, window_end, reason_code, metric_*, threshold_*)`. Keys sorted; UUIDs canonical; decimals as strings; datetimes `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Algorithm `sha256:` hex.

**Request digest (idempotency identity)** hashes only: `ruleset_version`, `project_id`, and the canonical caller `samples` (sorted by class; empty samples = `[]`). It **excludes** `as_of` and all live ledger observations. Same retry ⇒ same `request_digest`. A changed sample set with the same idempotency key is a conflict.

Window CHECKs on the child row: `window_kind='none'` ⇒ both timestamps NULL; `cumulative_project` ⇒ `window_start` NULL AND `window_end` NOT NULL; `caller_declared` ⇒ both NOT NULL AND `window_start < window_end`.

**Parent `as_of` binding (cannot be a child-table CHECK):** a BEFORE INSERT trigger on `ops_signal_results` loads the parent `ops_observation_runs.as_of` and refuses the row unless `window_kind='none'` or `window_end <= parent.as_of`. Direct-SQL tests must reject a child with `window_end > parent.as_of` and a `caller_declared` child with `window_end > parent.as_of`.

### 3.5 Reason codes (closed set)

```
no_uptime_source
no_error_rate_source
no_latency_source
no_post_launch_security_alert_source
no_journey_failure_source
no_data_quality_source
no_model_drift_source
no_support_ticket_source
no_incident_store
no_job_slo_threshold
cost_ledger_recorded
cost_no_budget
cost_budget_exceeded
cost_daily_budget_exceeded
cost_within_budget
uaid_runtime_failed_run_count
caller_sample_accepted
caller_threshold_ok
caller_threshold_breached
```

Python `REASON_CODES` tuple must match the DB CHECK exactly.

### 3.6 Allowed class × status × source × metric × threshold

Default collect (no samples):

| seq | class | status | source_kind | metric | threshold_state | reason_code |
|---|---|---|---|---|---|---|
| 1 | uptime | not_observed | none | none | not_evaluable | no_uptime_source |
| 2 | error_rates | not_observed | none | none | not_evaluable | no_error_rate_source |
| 3 | latency | not_observed | none | none | not_evaluable | no_latency_source |
| 4 | job_failures | observed | uaid_runtime | count = distinct `run_id` from immutable `run_steps` with `event_type='run_failed'` and `created_at < as_of` | **not_evaluable** | `uaid_runtime_failed_run_count`; threshold_kind=`none`, threshold_provenance=`none` |
| 5 | security_alerts | not_observed | none | none | not_evaluable | no_post_launch_security_alert_source |
| 6 | user_journey_failures | not_observed | none | none | not_evaluable | no_journey_failure_source |
| 7 | data_quality_issues | not_observed | none | none | not_evaluable | no_data_quality_source |
| 8 | cost_anomalies | observed | cost_ledger | see cost rules below | see cost rules below | see cost rules below |
| 9 | model_output_drift | not_observed | none | none | not_evaluable | no_model_drift_source |
| 10 | support_tickets | not_observed | none | none | not_evaluable | no_support_ticket_source |
| 11 | incident_reports | not_observed | none | none | not_evaluable | no_incident_store |

`not_observed` CHECK: `truth_tier='none'` AND `source_kind='none'` AND `source_table='none'` AND all metric/threshold value columns NULL AND `threshold_kind='none'` AND `threshold_provenance='none'` AND `threshold_state='not_evaluable'` AND `window_kind='none'` AND `window_start` IS NULL AND `window_end` IS NULL.

`observed` CHECK: `truth_tier='system_derived_ledger'` AND `source_digest` matches the computed aggregate AND `source_ref` IS NULL.

**Job-failure count and digest.** Query immutable append-only `run_steps` (migration `0009`; `event_type='run_failed'`):

```sql
SELECT DISTINCT run_id
FROM run_steps
WHERE tenant_id = :t AND project_id = :p
  AND event_type = 'run_failed'
  AND created_at < :as_of
ORDER BY run_id ASC
```

Count = length of that distinct list. A later `project_runs.status='failed'` row whose `run_failed` step is **after** `as_of` (or missing) is **not** counted. **Zero matching steps is still `observed` with count 0.** Threshold stays `not_evaluable`. `window_kind='cumulative_project'`, `window_start` NULL, `window_end=as_of`.

`source_digest` = `sha256:` of canonical JSON with sorted keys:

```json
{"as_of": "<UTC>", "count": <int>, "failed_run_ids": ["<uuid>", "...ordered by run_id ASC"], "project_id": "<uuid>"}
```

Empty list is valid (`count: 0`, `failed_run_ids: []`).

**Cost rules (always `observed` after a successful bounded ledger read).** Inside the same REPEATABLE READ transaction (OD-56-4), the ops repository runs **one** aggregate:

```sql
-- total: occurred_at < as_of
-- daily: utc_midnight(as_of.date()) <= occurred_at < as_of
SELECT
  COALESCE(SUM(amount_usd) FILTER (WHERE occurred_at < :as_of), 0) AS total_spent,
  COALESCE(SUM(amount_usd) FILTER (
    WHERE occurred_at >= :utc_midnight AND occurred_at < :as_of
  ), 0) AS daily_spent
FROM cost_events
WHERE tenant_id = :t AND project_id = :p;
```

Then `BudgetRepository.get` in that same transaction. Then **pure** `app.cost.evaluate_stop(total_spent=..., daily_spent=..., budget=...)`. Do **not** call `CostEventRepository.total_spent`, `daily_spent`, or `app.repositories.cost.evaluate`.

Every cost row persists **all four** amounts (daily cap nullable):

- `metric_money` = total_spent
- `metric_money_daily` = daily_spent
- `threshold_money` = `max_total_cost_usd` or NULL if no budget
- `threshold_money_daily` = `max_daily_cost_usd` or NULL if no budget or no daily cap

`metric_kind='money'`. Window always `cumulative_project`, `window_start` NULL, `window_end=as_of`. The daily half-open bound is recorded in `source_digest` (`utc_midnight`, `as_of`) rather than a second window_kind on the same row.

| budget / evaluate_stop | threshold_kind | threshold_provenance | threshold_state | reason_code |
|---|---|---|---|---|
| budget is None | `none` | `none` | `not_evaluable` | `cost_no_budget` |
| STOP `budget_exceeded` | `cost_stop` | `recorded_budget` | `breached` | `cost_budget_exceeded` |
| STOP `daily_budget_exceeded` | `cost_stop` | `recorded_budget` | `breached` | `cost_daily_budget_exceeded` |
| OK | `cost_stop` | `recorded_budget` | `ok` | `cost_within_budget` |

An OK result is reproducible from the four persisted amounts: `total_spent < total_cap` AND (`daily_cap` IS NULL OR `daily_spent < daily_cap`). The `>=` stop rule in `evaluate_stop` is the same comparison (`app/cost.py:122-125`).

Missing budget is **not** a recorded-budget breach.

`source_digest` = `sha256:` of canonical JSON:

```json
{"as_of": "<UTC>", "daily_cap": "<str|null>", "daily_spent": "<str>", "project_id": "<uuid>", "reason": "<StopReason.value|null>", "stop": <bool>, "total_cap": "<str|null>", "total_spent": "<str>", "utc_midnight": "<UTC>"}
```

Decimals as canonical strings from `str(Decimal)` (no float).

Default counters (empty project, no samples): `observed_count=2`, `caller_supplied_count=0`, `not_observed_count=9`, `breached_count=0` (cost with no budget is observed + not_evaluable, not breached).

### 3.7 Caller samples (fixtures)

**Allowed sample classes (closed):** `error_rates`, `latency`, `user_journey_failures`, `data_quality_issues`, `model_output_drift`.

**Forbidden sample classes:** `uptime`, `security_alerts`, `support_tickets`, `incident_reports` (must remain `not_observed`); `job_failures`, `cost_anomalies` (cannot overwrite ledger `observed`).

Class → metric/threshold shape (no other combination is valid):

| class | metric_kind | metric field | bounds | threshold_kind | threshold field | bounds | breached iff |
|---|---|---|---|---|---|---|---|
| error_rates | `ratio` | `metric_ratio` | NUMERIC(8,6) `0..1` inclusive | `caller_ratio` | `threshold_ratio` | same | `metric_ratio > threshold_ratio` |
| model_output_drift | `ratio` | `metric_ratio` | `0..1` | `caller_ratio` | `threshold_ratio` | `0..1` | `metric_ratio > threshold_ratio` |
| latency | `milliseconds` | `metric_int` | INT `0..2147483647` | `caller_ms` | `threshold_int` | INT `0..2147483647` | `metric_int > threshold_int` |
| user_journey_failures | `count` | `metric_int` | INT `0..2147483647` | `caller_count` | `threshold_int` | INT `0..2147483647` | `metric_int > threshold_int` |
| data_quality_issues | `count` | `metric_int` | INT `0..2147483647` | `caller_count` | `threshold_int` | INT `0..2147483647` | `metric_int > threshold_int` |

Unused metric/threshold columns for that row must be NULL (`metric_money`, `metric_money_daily`, `threshold_money`, `threshold_money_daily` included).

A sample is accepted only if **all** hold:

- `signal_class` in the allowed sample set above.
- class currently `not_observed`.
- exact shape in the table (both metric **and** matching threshold required; extra fields refused).
- `window_kind='caller_declared'`.
- `window_start` and `window_end` required, timezone-aware UTC, `window_start < window_end <= as_of`.
- `threshold_provenance='caller_supplied_unverified'`.
- `observation_status='caller_supplied_unverified'`.
- `truth_tier='caller_supplied_unverified'`.
- `source_kind='caller_supplied'`, `source_table='caller_sample'`.
- `source_digest` = sha256 of the canonical sample payload **including** `window_start` and `window_end`.
- `reason_code` = `caller_threshold_ok` if not breached else `caller_threshold_breached`.

No default 0.05 / 2000 / 0.10. No `data.slo`. Do not parse `error_budget_threshold` string into a number (schema type is `string`; Spec:2820).

### 3.8 Collection

Public wrapper (owns the transaction):

```python
async def collect_ops_signals(context, project_id, *, actor, samples=None, idempotency_key)
```

It **must** open `async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:` itself. Callers cannot pass a session. Inside that transaction:

1. `as_of = session.scalar(select(func.transaction_timestamp()))`, then normalize the returned timezone-aware datetime to UTC in Python (`astimezone(datetime.UTC)`). Persist that aware UTC value. Do **not** wrap in SQL `timezone('UTC', ...)` (that yields `timestamp without time zone`). Mutable budget state is bound to the transaction’s current time, not a caller-injected `as_of`.
2. Validate idempotency_key (non-blank, ≤200). Compute `request_digest`. SELECT existing row by `(tenant_id, project_id, idempotency_key)`; matching `request_digest` ⇒ return it (no further writes); mismatch ⇒ conflict.
3. Allowlisted reads (§4) against that `as_of` in the **same** transaction. Repository/DB errors abort — they do not become `not_observed`.
4. Pure `app.cost.evaluate_stop` on that snapshot.
5. Apply samples (§3.7) using the **DB** `as_of` for the `window_end <= as_of` rule.
6. Compute counters and `input_digest`.
7. `INSERT INTO ops_observation_runs ... ON CONFLICT (tenant_id, project_id, idempotency_key) DO NOTHING`. If `rowcount == 0`: reselect that key and compare `request_digest` — match ⇒ return existing (do **not** insert children or audit); mismatch ⇒ conflict. A unique-violation RAISE is forbidden (it aborts the PostgreSQL transaction). If `rowcount == 0` **and** the reselect finds **no row** (REPEATABLE READ snapshot cannot yet see the concurrently committed winner): **abort this transaction** and retry the **complete** public operation in a **fresh** REPEATABLE READ transaction. Cap: `MAX_IDEMPOTENCY_RACE_RETRIES = 5` with Slice 55 jitter (`RETRY_BACKOFF_BASE_SECONDS=0.005`, jitter `0.003`). After a successful retry, compare `request_digest` as above. Exhausted retries ⇒ raise `OpsSignalIdempotencyRace` after rollback (no partial parent/children).
8. Only if the INSERT inserted a row: insert the 11 children and audit.

Idempotency uses `request_digest`, not `input_digest`. Unique `(tenant_id, project_id, idempotency_key)`; same `request_digest` ⇒ return existing; different `request_digest` ⇒ conflict. `input_digest` remains the immutable observation snapshot (includes `as_of` and live facts) and is expected to differ across retries in time.

Private `_collect_ops_signals_in_txn(session, context, project_id, *, actor, as_of, samples, idempotency_key)` holds the in-transaction logic. Tests of persistence go through the public wrapper.

**Pure unit helpers** in `app/ops/signals.py` (`merge_samples`, `evaluate_caller_threshold`, `canonical_digest`, matrix builders) **may** take an injected `as_of` so Docker-free tests do not need a database clock. Those helpers do not read Budget or cost_events.

History: `latest(project_id)` one row or None; `history(project_id, *, limit=50)` newest-first (`created_at DESC, id DESC`), `limit` default 50, max 100, min 1.

### 3.9 Tables — migration `0055` revises `0054`

Two tenant-owned tables; RLS ENABLE+FORCE; `tenant_isolation`; SELECT/INSERT only; UPDATE/DELETE/TRUNCATE block triggers; no UPDATE/DELETE grant to `uaid_app`.

**`ops_observation_runs`:** id, tenant_id, project_id (composite FK), ruleset_version CHECK `= 'slice56.v1'`, idempotency_key, `request_digest` CHECK `~ '^sha256:[0-9a-f]{64}$'`, `input_digest` CHECK `~ '^sha256:[0-9a-f]{64}$'`, as_of timestamptz NOT NULL, signal_count CHECK `= 11`, observed_count/caller_supplied_count/not_observed_count CHECK `>= 0` AND sum = 11, breached_count CHECK `BETWEEN 0 AND 11`, created_at `clock_timestamp()`, `UNIQUE (id, project_id, tenant_id)`, `UNIQUE (tenant_id, project_id, idempotency_key)`.

**`ops_signal_results`:** composite FK to the run unique, seq 1–11, UNIQUE (run_id, seq), UNIQUE (run_id, signal_class), enum CHECKs, metric/threshold consistency CHECKs as above, `signal_class` CHECK in the eleven literals. BEFORE INSERT guard: load parent `as_of`; refuse unless `window_kind='none'` or `window_end <= parent.as_of`; also enforce the window_kind nullability rules from §3.4.

**Dual deferred count-match (0036 pattern):**

- **Parent-side** DEFERRABLE INITIALLY DEFERRED constraint trigger: at commit, `signal_count=11` AND child count=11 AND seq set = {1..11} AND class set = the eleven AND `observed_count`/`caller_supplied_count`/`not_observed_count`/`breached_count` each equal the corresponding child tallies.
- **Child-side** DEFERRABLE INITIALLY DEFERRED constraint trigger: at commit, the parent’s stored counts still match (rejects a late 12th child and a zero-child parent).

Tests must include: parent insert with zero children ⇒ commit fails; 10 children ⇒ fail; 12th insert ⇒ fail.

Downgrade: refuse if either table has rows. Empty `0055→0054→0055` succeeds. `release_findings_guard()` MD5 stays `808036faf2660d6810aeca4342e6f1ac`.

### 3.10 Files (each ≤500 lines)

| File | Role |
|---|---|
| `app/ops/__init__.py` | Package |
| `app/ops/signals.py` | Pure enums, matrix, sample merge, threshold compare, digest |
| `app/ops/collect.py` | Allowlisted reads + persist |
| `app/models/ops_signal.py` | ORM |
| `app/repositories/ops_signals.py` | `record_run` / `latest` / `history` |
| `migrations/versions/0055_ops_signals.py` | Additive |
| `tests/test_ops_signals.py` | Units + `@pytest.mark.db` |
| `.github/workflows/ci.yml` | Add scoped pyright step |

**Do not modify:** `production_autonomy.py`, `readiness.py`, `control_loop.py`, policy matrix/engine, findings guard, templates, spec.

### 3.11 Exact pyright CI (ruling 4)

After `uv sync --locked`, before or after `ruff check .`, add:

```yaml
      - name: Typecheck owned Slice 55/56 paths
        run: uv run pyright app/ops app/models/ops_signal.py app/repositories/ops_signals.py tests/test_ops_signals.py app/runtime/control_loop.py app/runtime/checkpointer.py app/repositories/go_live_decisions.py app/release/go_live_decision.py tests/test_control_loop_owner_retry.py tests/test_control_loop_owner_review.py
```

Local validation uses that **same** command. If pyright cannot run, log a HANDOFF blocker and HALT. Do not skip. Do not run full-repo pyright as a CI gate (3051 pre-existing errors). Do not weaken pyright config.

---

## 4. Open decisions (bind on plan APPROVE)

### OD-56-1 — Collect before production exists?

**Option A — recommended:** yes. Assessment is honest without claiming post-launch.

### OD-56-2 — A5 gate #11

**Option A — recommended:** do not touch `production_autonomy.py`. `before==after`.

### OD-56-3 — New network collectors?

**Option A — recommended:** none.

### OD-56-4 — Exact read allowlist

**Option A — recommended; this list only:**

1. `BudgetRepository.get`
2. Ops-owned bounded cost aggregate: `SUM(amount_usd)` with `occurred_at < as_of` (total) and `[utc_midnight(as_of.date()), as_of)` (daily) — a single query
3. Pure `app.cost.evaluate_stop` with that exact snapshot (no `CostEventRepository.total_spent` / `daily_spent`, no `app.repositories.cost.evaluate`)
4. Ops-owned failed-run query on immutable `run_steps`: `event_type='run_failed' AND created_at < as_of`, distinct `run_id` ordered ASC, scoped `(tenant_id, project_id)`

**Removed from v1:** `latest_monitoring`, `latest_deployment_target`, generic latest-* (declaration-unbound), findings counts, PM list, `resolve_declared_*` as signal sources, cost forecast.

**Forbidden:** broker_call, probes, control_loop, writes to findings/issues/incidents, LLM, HTTP, parsing `error_budget_threshold` as a number.

### OD-56-5 — Uptime

**Option A — recommended:** always `not_observed` / `no_uptime_source` this slice. Point-in-time target availability is not uptime. Slice-31 `overall_active` is not uptime.

### OD-56-6 — Job failures

**Option A — recommended:** distinct `run_id` from immutable `run_steps` where `event_type='run_failed' AND created_at < as_of`. No `project_runs.status` cutoff. No default “≥1 means breached.” Threshold stays `not_evaluable`.

### OD-56-7 — HTTP

**Option A — recommended:** none.

### OD-56-8 — Control-loop wiring

**Option A — recommended:** do not modify `control_loop.py`.

### OD-56-9 — pyright CI

**Option A — recommended:** the exact command in §3.11, in `.github/workflows/ci.yml`.

### OD-56-10 — Preservation

Migration `0055` / `down_revision=0054`; populated downgrade refused; findings-guard MD5 pinned; A5/readiness/control_loop/policy byte-stable; `can_go_live_autonomously is False`; `NO_GO_LIVE_REASONS` unchanged; no spec/template edits; no invented budget figures; `.env` unstaged.

---

## 5. Tests

Docker-free:

1. Default collect matrix: job_failures `observed` (count 0) + cost `observed` + nine `not_observed`; counters exactly `observed_count=2`, `caller_supplied_count=0`, `not_observed_count=9`, `breached_count=0`. Cost with no budget is `not_evaluable` (not breached).
2. Sample fills `model_output_drift` (ratio) and `data_quality_issues` (count) with matching metric+threshold and `window_start < window_end <= as_of` ⇒ `caller_supplied_unverified` and `breached`/`ok` per §3.7.
3. Sample missing threshold refused; sample on `uptime` / `security_alerts` / `support_tickets` / `incident_reports` refused; sample overwriting cost/job_failures refused; latency-as-ratio refused.
4. OOV class refused.
5. Cost with no budget ⇒ `not_evaluable` + `cost_no_budget` with both spend columns set and both cap columns NULL. Total cap exceeded ⇒ `breached` with all four amounts persisted (`threshold_money` = total cap). Daily cap exceeded ⇒ `breached` with all four amounts persisted (`threshold_money_daily` = daily cap). Within both caps ⇒ `ok` with all four amounts (daily cap NULL if the budget has no daily ceiling). Spend after `as_of` is excluded from both totals.
6. Uptime remains `not_observed` even if tests plant monitoring/deploy snapshots (those tables are not read).
7. A5 `before==after` + readiness level + `can_go_live_autonomously is False`.
8. Digest: `request_digest` is stable for identical samples even when `as_of`/`input_digest` differ; sample changes `request_digest` and conflicts on key reuse.
9. Audit has no URL/host/finding text.

DB:

1. Persist 11 children; latest/history (limit default 50 / max 100); idempotent retry returns the same row when `request_digest` matches even if `input_digest` would differ; `request_digest` mismatch on the same key raises conflict.
2. RLS cross-tenant empty.
3. Zero-child commit fails; 10-child fails; 12th child fails (dual deferred triggers).
4. Append-only refused; grants SELECT/INSERT only.
5. Populated downgrade refused; empty 0055→0054→0055; findings-guard MD5 unchanged.
6. CHECK: `not_observed` with metric; ratio > 1; cost row missing `metric_money_daily`; non-cost row with `metric_money_daily`; status counter mismatch.
7. Direct-SQL INSERT of a child with `window_end > parent.as_of` is refused by the BEFORE INSERT guard; a valid `window_end = parent.as_of` is accepted for `cumulative_project`.
8. `inspect.signature(collect_ops_signals)` has no `session` or `as_of` parameter.
9. Two concurrent `collect_ops_signals` calls with the same idempotency key: both succeed or one returns the winner’s row; neither aborts on unique-violation; a REPEATABLE READ winner-not-visible path retries in a fresh transaction (test with two sessions).

---

## 6. Must NOT claim

- Production or staging was deployed, or that a project is in a live stabilization window.
- Request-authenticated key custody is a human signature.
- Gate #11 equals the §25.1 set.
- Slice 48 rates are live model-output drift.
- PM mappings are support tickets; release findings are post-launch security alerts; a deployment-target snapshot is uptime.
- UAID failed runs are a customer job SLO.
- Threshold `breached` opened an incident, sent a channel notification, or paged a human.
- `can_go_live_autonomously=true` or A5 satisfied.
- **An eleven-row assessment, any threshold result, or existing adjacent evidence establishes adequate monitoring, operational coverage, stabilization success, or production readiness.**

---

## 7. Sequence after plan APPROVE

1. Stamp `OD-56-* = Option A` in this header.
2. Failing tests, then pure module, models, `0055`, repository, collect.
3. DB/RLS/trigger/downgrade/guard tests.
4. Same pyright command as CI; `ruff`; `make test`; `make test-db`.
5. Independent code review (Sol). Docs, PR, CI, squash-merge, HANDOFF merge SHA. Next: Slice 57 under standing cadence. HALT only after Slice 59.

---

## 8. Exit

Plan APPROVE + code APPROVE + CI green + merge. Eleven classes assessable. Thresholds fire only from source-bound values (recorded budget or caller sample). A5/readiness/go-live unchanged. pyright ran on the §3.11 path list with 0 errors.

---

## Appendix S — Muhasabah (v8)

- Invented 0.05/2000/0.10 and `data.slo` **removed** (reviewer defect 1; spec schema is a string threshold with no numeric type).
- Adjacent stores **not** promoted to operational classes (defect 2).
- Cost money not capped at 1; three status counters + independent `breached_count`; no `threshold_bool` / `metric_kind=boolean`.
- Source-binding matrix + digest material enumerated (defect 4).
- Dual deferred triggers + tests (defect 5).
- No `superseded`; job failures from `run_steps.event_type='run_failed'` with `created_at < as_of`; no default breach.
- v8: empty reselect after `ON CONFLICT DO NOTHING` aborts and retries the full collect in a fresh REPEATABLE READ TX (max 5); two-session concurrency test required.
- Closed reason codes, combination matrix, digest, history bounds, error≠not_observed (defect 7).
- Exact CI command and `ci.yml` in the file plan (defect 8).
- Adequacy refusal added (defect 9).
- Residual: `error_budget_threshold` remains an unparsed string until Slice 59 defines a numeric contract — labelled, not guessed.
- v3: no-budget cost is `not_evaluable`; samples cannot overwrite the four structurally unobserved classes; `window_start` required for caller windows; job-failure digest enumerates ordered IDs; default counters are exactly 2/0/9.
- v4: cost spend is `occurred_at < as_of` (daily `[utc_midnight, as_of)`); REPEATABLE READ snapshot; allowlist is Budget.get + ops aggregate + evaluate_stop + failed runs; all four cost amounts persist; `threshold_bool` removed.
- v5: job failures from `run_steps.run_failed` + `created_at < as_of`; public wrapper owns REPEATABLE READ and `transaction_timestamp()` as_of; child INSERT guard enforces `window_end <= parent.as_of`.

