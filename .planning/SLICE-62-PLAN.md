# Slice 62 — Advanced cost optimizer + tenant-safe cross-project learning

**Seats (ruling 2026-08-23, standing).** PLANNER = Claude seat (this document). BUILDER =
Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on plan and code,
probe-backed verdicts only. Builder never edits this plan.

**Version.** v4 (v1 REJECTED — ten defects; v2 REJECTED — four; v3 REJECTED — one;
all accepted; owner authorized a fourth round 2026-08-23; see §10).

> **This slice does NOT satisfy the roadmap Slice 61 exit.** D-8, D-9, and D-10 stay OPEN
> (owner = Salim). Catalog population is already on `main` (`59af1c7`, PR #113) and is not
> reopened here.

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 62. **Spec grounding.**
§26.7 (l.2512–2522); §17.5 (l.1724–1750); §19.3–§19.4 (l.1852–1879); Appendix C l.3009
and l.3030. **A5 / readiness / go-live are untouched.**

**Alembic.** Head at plan time is `0060` (`migrations/versions/0060_ecosystem_catalog.py`,
`revision="0060"`, `down_revision="0059"`; verified `uv run alembic heads` → `0060 (head)`
on `main` @ `59af1c709dcb2ac302f255ed2eb2325ea3710c97`). This slice adds **migration
`0061`**, `revision="0061"`, `down_revision="0060"`. Additive. `make migrate` /
`test-db-migrate` stay schema-only: a freshly migrated database has **zero** aggregate
snapshots until `publish_cross_project_aggregates` / `make learning-publish` runs.

---

## 0. What this slice is

Two bounded, deterministic pieces that the roadmap scheduled together because the optimizer
is allowed to *consult* published aggregates and must not be able to *read tenant content*
to do so.

1. **Tenant-safe learning (admin-path publisher).** An append-only global snapshot of the
   seven §17.5 *allowed* aggregate classes, with a DB-generated publication flag that is
   true only when a bucket has ≥3 contributing projects **and** ≥2 contributing tenants.
   The publisher is the only runtime writer. Counts on each bucket are re-derived from the
   source table at INSERT by a deferred trigger (admin cannot forge `n_projects=3` without
   three real source rows). Forbidden tenant content has **no column** and **no publisher
   parameter**. `publisher` is the code-owned literal `slice62.learning_publish` (OD-8).
   Runtime `uaid_app` cannot SELECT unpublished buckets (OD-3).
2. **Advanced cost optimizer (tenant-path, decision-only).** A versioned recommendation of
   `{cost_efficient, mid_quality, high_quality, frontier, hold}` for one declared §19.4 `task_class` and
   `risk_level`, using the project's own budget/spend plus the project's own Slice-51
   routing booleans when a policy row exists, plus *published* buckets from the latest
   aggregate snapshot. It does not call a model, does not write `PRICE_CARD`, does not
   change the broker, and does not mutate Slice-7 STOP / Slice-51 forecasts / A5.

### 0.1 Grounding facts (re-verified 2026-08-23 against `main` @ `59af1c7`)

1. **The ledger has no model id and no task class.** `cost_events`
   (`app/models/cost_event.py:51-108`) stores `component` ∈ the eight §19.2 values,
   `amount_usd`, `quantity`, `source_system`, `external_ref`, `description`, `actor`.
   There is no `model_id`, `task_class`, or latency column. An optimizer that claimed to
   *learn which model is cheaper* from the ledger would be fabricating a column.
2. **Slice 51 already snapshots routing booleans and treats them as diagnostic.**
   `cost_forecast_policy_versions.cheap_first_for_low_risk` /
   `frontier_for_high_risk` / `use_cached_context_when_possible`
   (`app/models/cost_forecast.py:99-101`). OD-51-3: they are never claimed enforced.
   Slice 62 *applies* them as a recommendation. That is the "advanced" step. File-21
   zeros (`docs/UAID_OS_Intake_Template_Pack_v1_2/21_cost_and_resource_policy.yaml:2-5`)
   remain invalid as live caps; this slice does not read that YAML.
3. **`PRICE_CARD` is empty** (`app/llm/pricing.py:27-28`). This slice does not invent
   prices. Routing output is a *tier*, not a provider model id.
4. **`evaluate_stop` is decision-only and fail-closed on missing budget**
   (`app/cost.py:113-120`). The optimizer reuses that decision for the `hold` rung on
   the *calling project only*. It does not clear STOP, unpause a run, or write a budget.
5. **Cross-tenant reads of tenant-owned tables are already RLS-blocked** for `uaid_app`.
   The only honest cross-project path is a **global** table that stores no tenant id.
   `uaid_app` cannot INSERT that table (OD-3).
6. **Latency does exist on one tenant table, and it is not production RUM.**
   `reviewer_quality_case_results.latency_ms` (`app/models/reviewer_quality.py:365`) is
   Slice-48 challenge-harness latency. Publishing it is allowed by §17.5 "anonymized
   cost and latency benchmarks" only if labelled `qa_harness`, never as live-work or
   production latency. `cost_events` has no latency column; there is no second source.
7. **A5 is `slice54.v1`; readiness is `slice20.v1`; `can_go_live_autonomously` is the
   literal `False`** (`app/release/production_autonomy.py:71,119`;
   `app/intake/readiness.py:45`). Slice 55 did not flip go-live. This slice must not.

### 0.2 Load-bearing claim

A recommendation persisted by `CostOptimizerRepository.recommend` cited only
`published=true` buckets from the latest aggregate snapshot (or cited none), and those
published buckets' `(n_events, n_projects, n_tenants, metric_sum)` matched the source
tables at the snapshot INSERT. That does **not** prove: cheaper live spend, complete
remaining work, differential privacy, that admin SQL cannot insert matching source rows,
that a model was chosen, or that the broker will obey the tier.

### 0.3 Honesty crux (verbatim, for CLAUDE.md / README.md)

*UAID recorded a tenant-owned model-tier recommendation from a declared task class, the
calling project's own budget/spend, optional recorded routing flags, and — when a bucket
clears a 3-project / 2-tenant publication threshold — anonymized aggregate counts that
contain no tenant identifiers and no tenant content. This is not actuated model routing,
not a provider quote, not proof of future spend, not production latency, not a privacy
proof against reconstruction, not tenant-content sharing, and not go-live authority. A
freshly migrated database has no published aggregates until the admin publisher runs.
Appendix C l.3010 and l.3012, and the roadmap Slice 61 exit, remain open.*

### 0.4 Allowed claims, verbatim

- "The seven §17.5 allowed classes are the only `signal_class` values the schema admits."
- "A bucket is `published=true` only when `n_projects >= 3 AND n_tenants >= 2`, and those
  two columns are re-derived from the source table at INSERT."
- "The publisher SELECT list is the code-owned allowlist in `learning_sql.py`; it does
  not read `description`, `params`, `summary`, `detail`, `body`, `title`, `content`,
  `prompt`, `target_ref`, `reference_name`, `repo_ref`, `actor`, `external_ref`,
  `reason`, or `agent_id`."
- "The optimizer's output is one of five values (`cost_efficient`, `mid_quality`,
  `high_quality`, `frontier`, `hold`). Low-risk + `cheap_first_for_low_risk`
  recommends a cheaper-or-equal non-hold tier than high-risk +
  `frontier_for_high_risk` on the fixture corpus (P-opt-cheap)."
- "A published rework/inference overlay can change a recommendation relative to the
  policy-only baseline on fixtures (P-opt-learn). That is overlay evidence, not USD
  savings."
- "Harness latency buckets, when published, are Slice-48 challenge-case `latency_ms`
  grouped by fixture `challenge_family`."
- "Own-project `evaluate_stop` = STOP ⇒ `hold`. Cross-project spend is never an input
  to that rung."
- "Migration `0061` is additive. Head becomes `0061`. Populate/publish is not DDL."

### 0.5 Refused claims, verbatim

- That the Slice 61 exit, D-8, D-9, or D-10 is closed.
- That live LLM/tool routing changed (`broker.py`, `LLM_EXTRACTION_MODEL`, `PRICE_CARD`
  stay byte-identical / empty).
- That the ledger taught the system a cheaper *model id*. The ledger has no model id.
- That published latency is production RUM, live reviewer work, or connector RTT.
- That `k=3, t=2` is differential privacy, k-anonymity against reconstruction, or a
  substitute for the §17.5 consent path. The consent path is **not built**; forbidden
  content is refused, not consented.
- That admin SQL cannot create source rows whose counts then publish. It can. The
  trigger refuses *count forgery*, not *source insertion*.
- That `uaid_app` can publish. It cannot INSERT the global tables.
- That `uaid_app` can read unpublished buckets. It cannot SELECT the base
  bucket table; it can SELECT only `cross_project_published_buckets`
  (`published=true`).
- That `publisher` is a free-text actor. It is the literal
  `slice62.learning_publish`.
- That a recommendation is a Slice-51 forecast, a Slice-7 STOP mutation, or an A5
  input. Gate #9 is untouched (`ruleset_version` stays `slice54.v1`).
- That file-21's zero caps or §19.5 USD envelopes are encoded in this slice.
- That `use_cached_context_when_possible` caches anything. It is echoed, not executed.
- That every `cost_events` row that exists at wall-clock publish time is in that
  snapshot. The snapshot is the result of that call's source queries.
- That this slice advances any Appendix-B gate or `can_go_live_autonomously`.

---

## 1. Frozen files — byte-identical, SHA-256 verified on `main` @ `59af1c7`

| File | SHA-256 |
|---|---|
| `app/tools/broker.py` | `20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57` |
| `app/tools/registry.py` | `c10023cfcbd074bb8c99e4dc0fa5a2b7de89d685820394b0902cde1ccfcc94e3` |
| `app/policy/matrix.py` | `c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f` |
| `app/release/production_autonomy.py` | `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029` |
| `app/intake/readiness.py` | `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26` |
| `app/runtime/control_loop.py` | `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180` |
| `app/cost.py` | `2dc1e1d1a0dcfb433af536b69bba926b5c74f3c028bda841d243416546819b43` |
| `app/cost_forecast.py` | `0fb050597363bcb4af6393e48e8822d975094108f92f4c5770ea4656b3ce02b6` |
| `app/llm/pricing.py` | `0693ab457daefd45fedbf3bd6df08e531568c89e2ca9a91dbd710c40febe5d59` |
| `app/agents/registry.py` | `b942a9d6a210cbe9730c0b447d20158137e3c87e2c317515b35d91cb99195964` |

Do not `ruff format` the whole tree. `TOOL_REGISTRY` keys are *read* by the publisher
as the tool-bucket universe; `registry.py` is not modified. `ARCHETYPES` in
`app/agents/registry.py` is *read* as the eval-bucket universe; that file is not
modified.

---

## 2. Design decisions

### OD-1 — Seven `signal_class` values = the seven §17.5 allowed bullets

Rejected: inventing classes not in l.1728–1736. Rejected: a latency class sourced from
`cost_events` (no such column). Rejected: skipping latency entirely while claiming the
bullet is implemented — implement it from the only existing numeric latency column,
labelled harness-only.

| `signal_class` | Source table(s) | `bucket_key` universe | `metric_unit` | `metric_sum` meaning |
|---|---|---|---|---|
| `aggregate_eval_failure_rates` | `qualification_runs` | 11 `ARCHETYPES` | `count` | rows with `verdict='failed'` |
| `aggregate_reviewer_miss_patterns` | `reviewer_quality_records` | `challenge_qualified`, `threshold_breached`, `inconclusive` | `count` | NULL (the measure is `n_events`) |
| `anonymized_cost_and_latency_benchmarks` | `cost_events` **or** `reviewer_quality_case_results` ⋈ `reviewer_qa_fixture_cases` | `cost:<component>` (8) **or** `latency:qa_harness:<family>` (5 `CHALLENGE_FAMILIES`) | `usd` **or** `milliseconds` | `SUM(amount_usd)` **or** `SUM(latency_ms)` of `execution_status='succeeded'` |
| `generic_tool_reliability` | `tool_calls` | the **13** `TOOL_REGISTRY` keys at `59af1c7` (probed: `len(TOOL_REGISTRY)==13`) | `count` | rows whose `decision` is one of the six `denied_*` values |
| `generic_connector_failure_categories` | `secret_reference_checks` ∪ `monitoring_status_snapshots` ∪ `deployment_target_snapshots` | 12 keys in §2.1 | `count` | NULL |
| `failure_mode_frequency_counts` | `agent_failure_events` | 8 `FAILURE_PATTERNS` | `count` | NULL |
| `security_safe_statistics` | `release_findings` | `security`, `shortcut` | `count` | NULL |

`DENIED_DECISIONS` (frozen, from `app/models/tool_call.py:23-33`):
`denied_unknown_tool`, `denied_invalid_params`, `denied_not_allowlisted`,
`denied_policy`, `denied_unknown_agent`, `denied_unqualified_agent`.
Not `LIKE 'denied%'` — that would silently absorb a future decision.

### OD-2 — Every snapshot writes exactly `EXPECTED_BUCKET_COUNT=62` children

11 + 3 + 8 + 5 + **13** + 12 + 8 + 2 = **62**. Missing source groups become explicit
zero rows (`n_events=0`, `n_projects=0`, `n_tenants=0`, `metric_sum IS NULL` per §3,
`published=false`). Dual deferred count-match: parent `bucket_count` must equal 62
and must equal the child count. A later source insert is **not** in that snapshot;
the next publish creates a new run (P-pub-later). No `LOCK TABLE`. The 13 tool
keys are listed in §2.2. Do not change `registry.py`.

### OD-2a — Publication threshold is GENERATED, counts are re-derived

```
published BOOLEAN GENERATED ALWAYS AS (n_projects >= 3 AND n_tenants >= 2) STORED
```

`MIN_CONTRIBUTING_PROJECTS = 3`, `MIN_CONTRIBUTING_TENANTS = 2` in
`app/ecosystem/learning.py` and in the GENERATED expression. Tests must not lower
these. A row with `n_projects=3, n_tenants=1` is `published=false` (P-k-1).

A DEFERRABLE constraint trigger `cross_project_aggregate_buckets_counts_match` runs
at INSERT and asserts `(n_events, n_projects, n_tenants, metric_sum)` equal
`learning_expected_counts(signal_class, bucket_key)` — a function installed by
the migration, owned by the table owner, invoked **only** from that trigger.
`REVOKE ALL ON FUNCTION learning_expected_counts(...) FROM PUBLIC, uaid_app`.
`uaid_app` must not be able to call it as a cross-tenant read oracle (P-fn-revoke).
The function body is generated from `app/ecosystem/learning_sql.py`
(`expected_counts_function_body()`), the same `SOURCE_QUERIES` the publisher
executes. Admin INSERT with `n_projects=3` and zero matching source rows is
refused (P-forge-counts). Admin INSERT of three real `cost_events` across three
projects / two tenants, then a matching bucket, is accepted — that is source
insertion, not count forgery (0.5).

### OD-3 — Two writers, two trust zones (Slice-6 pattern)

- **Admin path:** `publish_cross_project_aggregates(admin_session)` in
  `app/ecosystem/learning_publish.py`. Uses `ADMIN_DATABASE_URL`. No
  `tenant_scope`. Writes only the two global tables. `scripts/publish_learning.py`
  + `make learning-publish`. Prints `run_id` and `published_bucket_count` only.
- **Tenant path:** `CostOptimizerRepository.recommend` inside `tenant_scope`.
  Reads own `budgets` / `cost_events` / latest `cost_forecast_policy_versions`
  (RLS) and **SELECT of `cross_project_published_buckets` only** (OD-3a).
  Writes the two tenant tables.
- `uaid_app` GRANT:
  - `cross_project_aggregate_runs`: `SELECT` only
  - `cross_project_aggregate_buckets`: **none** (no SELECT, no INSERT)
  - `cross_project_published_buckets` (view `WITH (security_barrier=true)`
    defined as `SELECT * FROM cross_project_aggregate_buckets WHERE published`):
    `SELECT` only
  - tenant tables: `SELECT, INSERT` only
  - no UPDATE/DELETE/TRUNCATE (block triggers + REVOKE). PUBLIC revoked.
  RLS ENABLE+FORCE + `tenant_isolation` on the tenant tables. Global tables are
  **not** RLS. Admin role retains full DML on the base tables so publish and
  P-k-1 / P-forge-counts can see zeros.

### OD-3a — Unpublished aggregates are not a runtime-readable side channel

A singleton unpublished bucket (`n_projects=1`) is that one project's statistic.
Granting `uaid_app` SELECT on the base table would defeat the publication
threshold. P-unpub-hidden: after P-k-1, `uaid_app` `SELECT` from the view
returns 0 rows for that `cost:model_inference` key; `SELECT` from the base
table is denied. After P-9, the same view returns the published row.

### OD-4 — Optimizer is a tier recommender, not a model router

`TASK_CLASSES` (verbatim §19.4 left column, machine values):

`document_classification`, `requirements_extraction`, `architecture_decisions`,
`routine_code_generation`, `complex_ai_security_domain`, `code_review`,
`shortcut_detection`, `acceptance_verification`, `judgment_oracle_review`.

Nine rows. Spec l.1869–1879 lists those nine. No invented tenth. Unknown → refuse.

`RISK_LEVELS = ("low", "medium", "high")`. `production` is not a level here (Slice-4
risk tiers are for approvals). Unknown → refuse.

`TIER_ORDER` (non-hold): `cost_efficient` < `mid_quality` < `high_quality` <
`frontier`. `hold` is overlay-only and is **not** in `POLICY_TIER` or
`clamped_policy_tier`.

**Policy table** (`base_policy_tier`, before flags and overlays), code-owned
`POLICY_TIER`:

| task_class | base_policy_tier |
|---|---|
| `document_classification` | `cost_efficient` |
| `requirements_extraction` | `mid_quality` |
| `architecture_decisions` | `frontier` |
| `routine_code_generation` | `cost_efficient` |
| `complex_ai_security_domain` | `frontier` |
| `code_review` | `mid_quality` |
| `shortcut_detection` | `high_quality` |
| `acceptance_verification` | `high_quality` |
| `judgment_oracle_review` | `mid_quality` |

Spec l.1877–1878 says shortcut detection and acceptance verification use a
high-quality model. Spec l.1879 (judgment oracle) requires multiple reviewers
and model diversity when possible — recorded as non-actuated metadata
(`requires_multiple_reviewers=true`, `requires_model_diversity=true` iff
`task_class==judgment_oracle_review`); the tier stays `mid_quality` unless
flags/overlays change it. No second reviewer is invoked.

Spec "unless ambiguity is high" for classification: `ambiguity_high: bool` on the
request. If true, classification **base** is `mid_quality`. That flag is
caller-supplied, not inferred from a document.

**Flag clamp** (after the table, before overlays) produces `clamped_policy_tier`
∈ `TIER_ORDER` (never `hold`):

- `cheap_first_for_low_risk and risk_level=="low"`: demote one step
  (`frontier→high_quality`, `high_quality→mid_quality`,
  `mid_quality→cost_efficient`) **except** floors:
  - `{architecture_decisions, complex_ai_security_domain}` cannot go below
    `frontier`
  - `{shortcut_detection, acceptance_verification}` cannot go below
    `high_quality`
  - `document_classification and ambiguity_high` cannot go below `mid_quality`
- `frontier_for_high_risk and risk_level=="high"`: promote one step
  (`cost_efficient→mid_quality`, `mid_quality→high_quality`,
  `high_quality→frontier`) **except** `task_class==code_review`, which
  spec l.1876 routes to frontier for high-risk PRs: set
  `clamped_policy_tier='frontier'` directly (not a one-step promote from
  `mid_quality`). P-opt-review-high: `code_review` + `risk=high` +
  `frontier_for_high_risk=True` → `clamped_policy_tier==recommended_tier=='frontier'`.
  If `frontier_for_high_risk=False`, high-risk `code_review` stays at
  `base_policy_tier` (`mid_quality`) — the flag is the recorded preference.
- `use_cached_context_when_possible`: copied onto the recommendation row as
  `cache_hint=true|false`. Changes no tier. No cache exists.

Tier arithmetic (table + clamp + overlay 3's one-step promote) is
**app-derived**. SQL stores `base_policy_tier` and `clamped_policy_tier` and
checks overlay duality; it does not re-implement the clamp.

**Overlays** (after flags), first match wins, later do not stack:

1. Own-project `evaluate_stop(...).stop is True` → `hold`,
   `overlay_applied='budget_hold'`. Inputs are that project's
   `BudgetRepository.get` + `CostEventRepository.total_spent` /
   `daily_spent`. Missing budget is STOP (`no_budget`) so it holds. Other
   tenants' ledgers are not read.
2. Else if a *published* `generic_tool_reliability` bucket for a
   caller-declared `tool_name` (optional; omit → skip) has
   `metric_sum / n_events >= TOOL_DENY_HOLD_RATIO` (`Decimal("0.50")`) → `hold`,
   `overlay_applied='tool_deny_hold'`. Ratio, not a USD figure.
3. Else if `task_class` ∈ `{code_review, shortcut_detection,
   acceptance_verification, judgment_oracle_review}` **and** published buckets
   `cost:rework` and `cost:model_inference` both exist with `n_events>0` **and**
   `(metric_sum_rework/n_events_rework) >= REWORK_TO_INFERENCE_BUMP_RATIO *
   (metric_sum_inference/n_events_inference)` with
   `REWORK_TO_INFERENCE_BUMP_RATIO = Decimal("1")` → promote `clamped_policy_tier`
   one step (not past `frontier`; `hold` is not reachable here),
   `overlay_applied='rework_intensity_bump'`.
4. Else `overlay_applied='none'`.

If the latest snapshot exists but every bucket is unpublished, overlays 2–3 do
not fire. That is `no_published_aggregate`, recorded as overlay `none` plus
`published_bucket_count=0` on the run — not a fake overlay name.

Citations: one child row per *used* published bucket. FK `(bucket_id) →
cross_project_aggregate_buckets(id)` — PostgreSQL cannot target a view; the
FK is identity-only and does not grant `uaid_app` SELECT on the base table.
All citation *metadata* checks (published, `bucket_key`, `signal_class`,
`run_id`, count, overlay shape) join `cross_project_published_buckets` inside
**one** PL/pgSQL function `cost_optimizer_citations_guard()`, invoked by
**two** deferred trigger instances (see §3.4). Overlay
required sets:

| `overlay_applied` | required citations |
|---|---|
| `none` | `citation_count=0` |
| `budget_hold` | `citation_count=0` |
| `tool_deny_hold` | `citation_count=1`; the one bucket is `signal_class='generic_tool_reliability'` and `bucket_key = parent.tool_name`; `tool_name IS NOT NULL` |
| `rework_intensity_bump` | `citation_count=2`; the two `bucket_key`s are exactly `{cost:rework, cost:model_inference}` |

### OD-5 — Routing flags source

`recommend` requires `task_class`, `risk_level`, `ambiguity_high: bool`, optional
`tool_name`. Routing flags come from the latest same-project
`cost_forecast_policy_versions` row (`created_at DESC, id DESC`) if one exists;
otherwise the caller must pass an explicit `RoutingFlags`. Neither source →
`CostOptimizerError("no_routing_flags")`. File-21 YAML is never opened.
A policy row's USD caps are **not** read by this slice (Slice-51 owns them).
Only the three booleans are used. When `flags_source='recorded_cost_policy'`,
`policy_version_id` is the composite FK
`(policy_version_id, project_id, tenant_id) → cost_forecast_policy_versions
(id, project_id, tenant_id)` (`uq_cfpv_id_project_tenant` already exists)
**and** an INSERT trigger `cost_optimizer_runs_policy_flags_match` asserts
the three stored booleans equal that policy row's
`cheap_first_for_low_risk`, `frontier_for_high_risk`,
`use_cached_context_when_possible`. Existence of the FK alone is not
the claim. P-policy-flags: insert with FK to a real policy but
`cheap_first_for_low_risk` flipped; refused. Mutation: disable only that
trigger; the flipped row commits; restore. When
`flags_source='caller_supplied'`, `policy_version_id IS NULL` and that
trigger is a no-op.

### OD-8 — Publisher identity is a code-owned literal

`PUBLISHER = "slice62.learning_publish"`. Column CHECK `publisher = that literal`.
Direct SQL with any other string is refused (P-publisher-literal). This is not
an actor/principal and not tenant content.

### OD-6 — No HTTP, no LLM, no broker, no A5, no consent artifact

No route. No new tool. No new A1 action. `production_autonomy.py` /
`readiness.py` / `control_loop.py` / `cost.py` / `cost_forecast.py` /
`pricing.py` / `broker.py` frozen. Consent artifacts (l.1750) are deferred: this
slice never accepts tenant content, so it has nothing to consent to.

### OD-7 — Audit is safe metadata only

Tenant optimizer run: `action=cost_optimizer.recorded` with
`task_class`, `recommended_tier`, `overlay_applied`, `citation_count`, `run_id`.
Never metric_sum, never bucket_key lists that could be joined to a rare key in
an unpublished row, never other tenants.

Global publish: same as Slice 6 / 61b global writes — **no** `audit_append`
(GUC-derived tenant; platform-event audit remains deferred). The snapshot row
*is* the trail.

---

## 2.1 Connector bucket keys (exact 12)

From existing enums, never from URLs or names:

- `secrets:resolved`, `secrets:not_found`, `secrets:unsupported_manager`,
  `secrets:probe_error` (`app/release/secrets_verification.py` `OUTCOMES`)
- `monitoring:unreachable`, `monitoring:http_error`, `monitoring:content_type`,
  `monitoring:oversize`, `monitoring:malformed`, `monitoring:valid_read`
  (`FAILURE_KINDS` plus `failure_kind IS NULL` as `valid_read`)
- `deploy:available`, `deploy:unavailable`
  (`deployment_target_snapshots.target_available`)

Publisher SQL for monitoring **must not** list `target_ref`. Deploy **must not**
list `target_ref`. Secrets **must not** list `reference_name` or `manager`.

### 2.2 Tool-bucket keys (exact 13, live `TOOL_REGISTRY` at `59af1c7`)

`pm.create_issue`, `source_control.create_branch`,
`source_control.read_branch_protection`, `source_control.read_pull_request`,
`deployment.read_target_status`, `monitoring.read_status`,
`secrets.verify_reference`, `pm.read_issues`,
`source_control.open_pull_request`, `ci.run_tests`, `ci.deploy_staging`,
`ci.deploy_production`, `source_control.merge_to_protected`.

P-1 asserts `frozenset(TOOL_REGISTRY) == frozenset(these 13)`.

---

## 3. Schema (migration `0061`)

### 3.1 `cross_project_aggregate_runs` (GLOBAL, append-only)

Columns: `id UUID PK`, `ruleset_version TEXT NOT NULL CHECK (= 'slice62.v1')`,
`contract_version TEXT NOT NULL CHECK (= 'slice62.aggregates.v1')`,
`bucket_count SMALLINT NOT NULL CHECK (= 62)`,
`published_bucket_count SMALLINT NOT NULL CHECK (BETWEEN 0 AND 62)`,
`publisher TEXT NOT NULL CHECK (= 'slice62.learning_publish')`,
`created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()`.

`published_bucket_count` is written by the publisher (it knows the 62 rows in
memory). A deferred trigger **verifies** it equals
`COUNT(*) FILTER (WHERE published)` on the children. The trigger must not UPDATE
the parent (append-only). Do **not** `SET CONSTRAINTS ALL DEFERRED` in Python.
P-pubcount-mutation: disable only this trigger, insert parent `published_bucket_count=0`
with 62 unpublished children... wait, zeros are unpublished so 0 is correct on empty
DB. On P-9, disable the trigger and insert parent with `published_bucket_count=0`
while one child is published: COMMIT succeeds only with the trigger disabled;
with the trigger enabled, refused. Restore `tgenabled='O'`.

UNIQUE `(id)` already from PK. No `tenant_id`. No JSONB. No free-text payload.

### 3.2 `cross_project_aggregate_buckets` (GLOBAL, append-only)

Columns: `id UUID PK`, `run_id UUID NOT NULL REFERENCES
cross_project_aggregate_runs(id)`,
`signal_class TEXT NOT NULL` CHECK IN the seven OD-1 values,
`bucket_key TEXT NOT NULL` CHECK against the frozen per-class universe
(a single CHECK that is a conjunction of `signal_class = X ⇒ bucket_key IN (...)`),
`n_events INT NOT NULL CHECK (>= 0)`,
`n_projects INT NOT NULL CHECK (>= 0)`,
`n_tenants INT NOT NULL CHECK (>= 0)`,
`metric_sum NUMERIC(18,6) NULL`,
`metric_unit TEXT NOT NULL` CHECK IN `('usd','milliseconds','count')`,
`published BOOLEAN NOT NULL GENERATED ALWAYS AS (n_projects >= 3 AND n_tenants >= 2) STORED`,
`UNIQUE (run_id, signal_class, bucket_key)`.

Shape-by-class (CHECK):

- `anonymized_cost_and_latency_benchmarks` + `bucket_key LIKE 'cost:%'` ⇒
  `metric_unit='usd'` AND (`n_events=0` ⇒ `metric_sum IS NULL`;
  `n_events>0` ⇒ `metric_sum IS NOT NULL AND metric_sum >= 0`).
- same class + `bucket_key LIKE 'latency:%'` ⇒ `metric_unit='milliseconds'`
  AND the same null rule.
- `aggregate_eval_failure_rates` and `generic_tool_reliability` ⇒
  `metric_unit='count'` AND (`n_events=0` ⇒ `metric_sum IS NULL`;
  `n_events>0` ⇒ `metric_sum IS NOT NULL AND metric_sum BETWEEN 0 AND n_events`).
- the other four classes ⇒ `metric_unit='count' AND metric_sum IS NULL`.

Also: `n_tenants <= n_projects` (a project has one tenant). `n_projects <=
n_events` when `n_events>0` is true for these grains (one row is one event);
enforce `n_projects <= n_events` always (0=0).

No `tenant_id`, `project_id`, `description`, JSONB, or URL column. P-schema
asserts `information_schema.columns` for both global tables contains none of
those names except we *do not* even have them to check — the probe lists
forbidden names and expects zero matches.

Triggers: UPDATE/DELETE/TRUNCATE blocked. Counts-match deferred trigger
(OD-2a). Parent/child count-match deferred (OD-2).

### 3.3 `cost_optimizer_runs` (TENANT, RLS ENABLE+FORCE, append-only)

Composite FK `(project_id, tenant_id) → projects`. UNIQUE `(id, project_id,
tenant_id)` for children. Columns:

- `task_class`, `risk_level`, `ambiguity_high BOOLEAN NOT NULL`,
  `tool_name TEXT NULL` (NULL or a `TOOL_REGISTRY` key),
- `cheap_first_for_low_risk`, `frontier_for_high_risk`,
  `use_cached_context_when_possible` (the flags actually used),
- `flags_source TEXT NOT NULL CHECK IN ('recorded_cost_policy','caller_supplied')`,
- `policy_version_id UUID NULL`,
  composite FK `(policy_version_id, project_id, tenant_id) →
  cost_forecast_policy_versions(id, project_id, tenant_id)` (nullable),
  CHECK: `flags_source='recorded_cost_policy' ⇔ policy_version_id IS NOT NULL`,
- `base_policy_tier TEXT NOT NULL CHECK IN
  ('cost_efficient','mid_quality','high_quality','frontier')`  — never `hold`,
- `clamped_policy_tier TEXT NOT NULL CHECK IN
  ('cost_efficient','mid_quality','high_quality','frontier')`  — never `hold`,
- `recommended_tier TEXT NOT NULL CHECK IN
  ('cost_efficient','mid_quality','high_quality','frontier','hold')`,
- `overlay_applied CHECK IN
  ('none','budget_hold','tool_deny_hold','rework_intensity_bump')`,
- `cache_hint BOOLEAN NOT NULL`,
- `requires_multiple_reviewers BOOLEAN NOT NULL`,
- `requires_model_diversity BOOLEAN NOT NULL`,
  CHECK: both true iff `task_class='judgment_oracle_review'`; both false otherwise,
- `published_bucket_count SMALLINT NOT NULL CHECK (>= 0)`,
- `citation_count SMALLINT NOT NULL CHECK (>= 0)`,
- `aggregate_run_id UUID NULL REFERENCES cross_project_aggregate_runs(id)`,
- `ruleset_version='slice62.v1'`,
- `execution_provenance='system_derived_cost_recommendation'`,
- `created_at` default `clock_timestamp()`.

Bindings that **are** SQL-enforced:

- `recommended_tier='hold' ⇔ overlay_applied IN ('budget_hold','tool_deny_hold')`
- `overlay_applied='none' ⇒ recommended_tier = clamped_policy_tier`
- `overlay_applied='rework_intensity_bump' ⇒ recommended_tier <> 'hold'`
  (the one-step promote itself stays app-derived)
- `(aggregate_run_id IS NULL AND published_bucket_count=0 AND citation_count=0)
  OR (aggregate_run_id IS NOT NULL)`
- if `aggregate_run_id IS NOT NULL`, a deferred trigger asserts
  `published_bucket_count` equals that run's `published_bucket_count`
- deferred `citation_count = COUNT(children)` **and** overlay citation shape
  live in **one** function `cost_optimizer_citations_guard()`, invoked by
  two deferred trigger instances (see §3.4).

Tier clamp arithmetic remains app-derived (OD-4). Direct SQL can write a
nonsensical `base_policy_tier='frontier'` for `document_classification`; that is
the 61a §0.7 class of limitation and is **not** claimed closed. The overlay
duality and citation shape **are** claimed.

No remaining-USD column. No document/prompt column.

### 3.4 `cost_optimizer_citations` (TENANT, RLS, append-only)

`(run_id, project_id, tenant_id) → cost_optimizer_runs`.
`bucket_id UUID NOT NULL REFERENCES cross_project_aggregate_buckets(id)`.
UNIQUE `(run_id, bucket_id)`. One PL/pgSQL function
`cost_optimizer_citations_guard()` is the **single** overlay-shape and
citation-count authority (OD-4 table AND `COUNT(children)=parent.citation_count`).
It runs as the invoker (`uaid_app` on the runtime path) and therefore
**must not** read `cross_project_aggregate_buckets` (REVOKE SELECT). It joins
`cross_project_published_buckets` only. Unpublished bucket ids are
invisible to that join, so a citation of an unpublished id is refused
the same as a missing id. Stale-run: `view.run_id = parent.aggregate_run_id`.

Two DEFERRABLE INITIALLY DEFERRED constraint-trigger instances call that
same function:

| Trigger name | Event |
|---|---|
| `cost_optimizer_runs_citations_guard` | AFTER INSERT ON `cost_optimizer_runs` |
| `cost_optimizer_citations_row_guard` | AFTER INSERT ON `cost_optimizer_citations` |

A parent INSERT with `overlay_applied` requiring citations and **zero**
children never fires the citation-table trigger; the parent-table instance
is what refuses that case. A citation INSERT after a committed valid parent
never re-fires the parent-table instance; the citation-table instance is
what refuses a late child.

P-cite-uaid-app: as `uaid_app`, a valid `tool_deny_hold` or
`rework_intensity_bump` citation against a published view row commits.
P-cite-unpublished / P-cite-stale / P-overlay-shape fire with both instances
enabled. Do **not** split count and shape into two functions — they mask
each other. The two instances are event coverage, not a second authority.

### 3.5 Grants / RLS / immutability

Per OD-3 / OD-3a. Downgrade `0061→0060` fails closed while any of the four
**tables** has a row (the view is dropped with the tables). Empty 0061
downgrade succeeds. `GRANT SELECT ON cross_project_published_buckets TO uaid_app`.
`REVOKE ALL ON cross_project_aggregate_buckets FROM uaid_app`.

---

## 4. Python modules (new; all ≤500 lines)

| Path | Responsibility |
|---|---|
| `app/ecosystem/learning.py` | Enums, thresholds, `EXPECTED_BUCKET_COUNT`, `validate_bucket`, `PublicationThreshold` |
| `app/ecosystem/learning_sql.py` | The seven source queries + `learning_expected_counts` PL/pgSQL body as the **single** string source. Forbidden-column tuple used by P-sql-allowlist. |
| `app/ecosystem/learning_db_checks.py` | CHECK constraint SQL consumed by ORM + migration |
| `app/ecosystem/learning_ddl.py` | Guard install/drop (counts-match, append-only, `cost_optimizer_citations_guard()` + the two deferred instances, `cost_optimizer_runs_policy_flags_match`, published-count verify) |
| `app/ecosystem/learning_publish.py` | `publish_cross_project_aggregates(session) -> PublishReport` |
| `app/ecosystem/cost_optimizer.py` | Pure `evaluate_recommendation(...) -> Recommendation` |
| `app/models/cross_project_aggregate.py` | Two global ORM classes + the published-only view mapping if needed |
| `app/models/cost_optimizer.py` | Two tenant ORM classes |
| `app/repositories/learning.py` | Admin persist of a 62-row snapshot; `latest_snapshot()` (admin); no uaid_app read of base buckets |
| `app/repositories/cost_optimizer.py` | `recommend` + `latest_for`; reads published view only |
| `scripts/publish_learning.py` | Admin CLI, counts only |
| `migrations/versions/0061_cost_learning.py` | Additive |
| `tests/test_learning.py` | Pure P-1, P-4 (sql allowlist), universe sizes |
| `tests/test_cost_optimizer.py` | Pure P-2, P-3, P-opt-* |
| `tests/test_learning_db.py` | P-7…P-9, P-k-1, P-unpub-hidden, P-fn-revoke, P-10 view path, P-pub-later |
| `tests/test_learning_guards.py` | P-forge-counts, P-pubcount-mutation, P-publisher-literal, append-only |
| `tests/test_learning_checks.py` | CHECK / GENERATED / view catalog |
| `tests/test_learning_migrate.py` | P-20 head + downgrade |
| `tests/test_cost_optimizer_db.py` | P-opt-learn-db, P-12…P-18, P-15/P-16, overlay-shape |
| `tests/test_cost_optimizer_checks.py` | Optimizer CHECKs / citation guards |
| `tests/learning_support.py` | Shared seed helpers (two-tenant three-project, budgets) |

`evaluate_recommendation` is pure: it receives `RoutingFlags`, optional
`CostStopDecision`, optional `PublishedBucket` views (already filtered to
`published=true` by the caller). It never opens a session.

`CostOptimizerRepository.recommend` loads flags (OD-5), own STOP, latest
snapshot's **published-view** buckets, calls the pure function, persists run +
citations in one transaction. Parent optimizer row first, then citation
children, then COMMIT.

Publisher: INSERT **parent run first** (FK is not deferrable), then the 62
bucket rows, then COMMIT so deferred count-match and published_bucket_count
verification fire. Idempotent in the Slice-56 sense: **always a new run**,
never UPDATE. Do not insert children before the parent.

---

## 5. Probes

**Pure.**

- **P-1** `SIGNAL_CLASSES` is exactly the seven OD-1 names in that order.
  `EXPECTED_BUCKET_COUNT == 62`. Sum of per-class key-universe sizes is 62.
  `frozenset(TOOL_REGISTRY) ==` the 13 keys in §2.2.
- **P-2** `POLICY_TIER` matches the OD-4 table field-for-field (`shortcut_detection`
  and `acceptance_verification` are `high_quality`).
- **P-3** `evaluate_recommendation` unknown `task_class` / `risk_level` raises.
- **P-opt-cheap** fixture: `document_classification`, `risk=low`,
  `cheap_first=True`, `ambiguity_high=False`, no STOP, no buckets →
  `recommended_tier=='cost_efficient'` and
  `clamped_policy_tier=='cost_efficient'`. Same class `risk=high`,
  `frontier_for_high_risk=True` → `mid_quality` (promote from
  `cost_efficient`). `architecture_decisions` + low + cheap_first → still
  `frontier`. `document_classification` + `ambiguity_high=True` + low +
  cheap_first → `mid_quality` (ambiguity floor). `shortcut_detection` + low
  +   cheap_first → `high_quality` (spec floor; not demoted to `mid_quality`).
  **P-opt-review-high:** `code_review` + `risk=high` +
  `frontier_for_high_risk=True` → `clamped_policy_tier==recommended_tier=='frontier'`
  (direct, not `mid_quality→high_quality`). Same class + high +
  `frontier_for_high_risk=False` → `mid_quality`.
  The low/cheap unambiguous classification is cheaper-or-equal than the
  high/frontier classification (`cost_efficient` < `mid_quality` <
  `high_quality` < `frontier` is the tier order used by P-opt-cheap, not a
  spend claim).
- **P-opt-learn** same as cheap-low classification baseline (`cost_efficient`,
  overlay `none`); add two published cost buckets whose rework mean ≥
  inference mean → still `cost_efficient` because classification is **not**
  in the review-class overlay set. Repeat with `task_class='code_review'`,
  `risk=low`, `cheap_first=True`: `base_policy_tier='mid_quality'` clamps to
  `cost_efficient`; with the same rework overlay, result is `mid_quality`
  and `overlay_applied='rework_intensity_bump'`. Disabling the overlay
  comparison (monkeypatch ratio to never fire) makes the test fail — load-bearing.
  **P-opt-learn-db** (not a tautology): seed two tenants / three projects with
  **a per-project budget strictly above that project's total and daily spend**
  (missing budget would `hold` via `no_budget` and hide the overlay); seed
  `cost_events` for both `rework` and `model_inference` such that rework mean
  ≥ inference mean; publish; `recommend(code_review, low, caller flags with
  cheap_first)` on one of those projects yields `mid_quality` /
  `rework_intensity_bump` and two citations whose `bucket_key`s are
  `cost:rework` and `cost:model_inference`. A same-shape publish with rework
  mean *below* inference must not apply that overlay (still non-hold because
  of the seeded budget).
- **P-opt-hold-budget** `CostStopDecision.stopped(BUDGET_EXCEEDED)` → `hold`
  / `budget_hold` even if a rework overlay would otherwise bump.
- **P-opt-hold-tool** published tool bucket deny ratio 0.50 on declared
  `tool_name` → `hold` / `tool_deny_hold`. Ratio `0.49` with `n_events=100`
  does not hold.
- **P-opt-unpub** buckets with `published=False` are ignored even if passed
  in by mistake: the pure function accepts only a `PublishedBucket` type
  that the repository constructs from `published.is_(True)`. A unit that
  feeds a hand-built unpublished view is refused (`unpublished_bucket`).
- **P-4** `learning_sql.py` text contains none of the forbidden column names
  in OD-0.4 (word-boundary scan). `cost_optimizer.py` / `learning.py` text
  contains none of `25000`, `1000`, `5000`, `10000`, `50000`, `250000`,
  `1k`, `USD`.
- **P-5** the ten frozen hashes match §1.
- **P-6** `A5_RULESET_VERSION == "slice54.v1"`, readiness
  `RULESET_VERSION == "slice20.v1"`, `can_go_live_autonomously is False`
  by identity.

- **P-opt-judgment** `task_class='judgment_oracle_review'` →
  `requires_multiple_reviewers is True` and `requires_model_diversity is True`;
  no second reviewer is called. `code_review` → both False. Direct SQL flipping
  those bits on a `code_review` row is refused by CHECK.

**DB.**

- **P-7** after migrate, before publish: `latest_snapshot()` is `None`;
  `cross_project_aggregate_runs` count is 0.
- **P-8** publish on an empty DB: one run, **62** children, `published_bucket_count=0`,
  every `published is False`.
- **P-9** seed two tenants, three projects, one `cost_events.model_inference`
  row in each project (admin inserts). Publish. The `cost:model_inference`
  bucket has `n_projects=3`, `n_tenants=2`, `published is True`. Other cost
  keys remain unpublished zeros. `published_bucket_count >= 1`.
- **P-unpub-hidden** after P-k-1 (or an equivalent singleton unpublished
  `cost:model_inference`): as `uaid_app`, `SELECT` from
  `cross_project_published_buckets` returns no row for that key; `SELECT`
  from `cross_project_aggregate_buckets` is denied. After P-9, the view
  returns the published row. Mutation: `GRANT SELECT` on the base table to
  `uaid_app` would make this fail — do not grant it; the probe is the
  privilege, not a WHERE in Python.
- **P-publisher-literal** admin INSERT a run with `publisher='other'` is
  refused by CHECK. `publisher='slice62.learning_publish'` is accepted.
- **P-k-1** same as P-9 but all three projects on **one** tenant:
  `n_tenants=1`, `published is False`.
- **P-forge-counts** admin INSERT a bucket for `cost:model_inference` with
  `n_projects=3`, `n_tenants=2`, `n_events=3` and **no** `cost_events` rows:
  refused by counts-match. Triggers remain `tgenabled='O'`. Mutation: disable
  only that trigger → the insert succeeds; the probe is load-bearing. Restore.
- **P-sql-allowlist** migration `0061` imports `expected_counts_function_body`
  (and the CHECK strings) from `app.ecosystem.learning_sql` /
  `learning_db_checks` the way `0060` imports `catalog_db_checks`. Publisher
  executes `SOURCE_QUERIES` values. Each `SOURCE_QUERIES` SQL string is a
  substring of `expected_counts_function_body()`.
- **P-fn-revoke** as `uaid_app`, `SELECT learning_expected_counts('aggregate_eval_failure_rates','builder')`
  is refused (no EXECUTE). The trigger still fires on admin INSERT.
- **P-10** `uaid_app` INSERT into `cross_project_aggregate_runs` /
  `_buckets` is denied. `uaid_app` SELECT of P-9's published row **from the
  view** succeeds. `uaid_app` SELECT of another tenant's `cost_events` is
  empty (existing RLS; re-assert so learning did not widen it).
- **P-11** `information_schema.columns` for the two global tables: zero
  columns named `tenant_id`, `project_id`, `description`, `params`,
  `summary`, `detail`, `body`, `title`, `content`, `prompt`, `target_ref`,
  `reference_name`, `repo_ref`, `actor`, `external_ref`.
- **P-12** optimizer `recommend` for tenant A after P-9: may cite
  `cost:model_inference` if that overlay applies; `aggregate_run_id` is the
  latest run. Tenant B same. Neither run stores the other's `tenant_id`.
- **P-cite-unpublished** as `uaid_app`, INSERT a citation whose `bucket_id` is
  a real unpublished base-table id (admin-known): refused (view join misses it).
  Mutation: disable `cost_optimizer_citations_row_guard` only; the insert commits;
  restore.
- **P-cite-stale** publish twice; cite a published bucket from run 1 on a run
  that points at run 2: refused by the same guard.
- **P-cite-uaid-app** after P-9, as `uaid_app` inside `tenant_scope`, a
  `recommend` that produces `rework_intensity_bump` (P-opt-learn-db setup)
  persists two citations. A hand-built valid `tool_deny_hold` citation of a
  published view row also commits as `uaid_app`.
- **P-policy-flags** recorded-policy insert with matching FK but one boolean
  flipped: refused by `cost_optimizer_runs_policy_flags_match`. Mutation:
  disable only that trigger; flipped row commits; restore.
- **P-13** `recommend` with no policy row and no caller flags raises
  `no_routing_flags`. With caller flags, `flags_source='caller_supplied'`.
  With a recorded policy, `flags_source='recorded_cost_policy'` and the
  booleans equal that row (do not read USD caps — P-13b asserts the
  repository source does not mention `max_total_model_cost_usd`).
- **P-14** own-project STOP: insert a budget of 1.00 and a `cost_events` of
  1.00 for this project only; `recommend` → `hold` / `budget_hold`. **P-14b**
  a second tenant/project is seeded with its **own** budget strictly above
  zero spend (missing budget would also hold) and gets a non-hold on the
  same task — proving STOP is not global.
- **P-15** real `ProductionAutonomyRepository.evaluate` and
  `ReadinessRepository.evaluate` before and after publish+recommend are
  bit-equal on `a5_satisfied`, `can_go_live_autonomously`, `ruleset_version`,
  gate statuses, and readiness `readiness_level` / `ruleset_version`. Not a
  pure-function tautology.
- **P-16** `can_go_live_autonomously is False` after recommend on a real A5
  report.
- **P-17** append-only: UPDATE/DELETE/TRUNCATE on all four tables refused
  (admin role).
- **P-18** RLS: tenant A cannot SELECT tenant B's `cost_optimizer_runs`.
- **P-19-universe** inserting a 63rd child with a `bucket_key` outside the
  frozen CHECK universe is refused by the key CHECK / UNIQUE even if the
  count trigger is disabled. This is a universe test, not a cardinality
  mutation.
- **P-19-count** parent `bucket_count<>62` refused; 61 children refused (run
  with `bucket_count=62` and 61 in-universe keys). Mutation: disable only
  the parent/child count-match trigger; 61 in-universe children then
  commit; restore `tgenabled='O'`.
- **P-overlay-shape** direct SQL: `overlay_applied='rework_intensity_bump'`
  with 0 or 1 citation, or with two citations that are not
  `{cost:rework, cost:model_inference}`; `tool_deny_hold` with a
  mismatched `bucket_key`; `none` with a citation. All refused with both
  trigger instances enabled.
- **P-cite-parent-zero** INSERT a parent with
  `overlay_applied='rework_intensity_bump'` and `citation_count=2` and
  **zero** children; COMMIT is refused by
  `cost_optimizer_runs_citations_guard` (the citation-table instance does
  not fire — there is no child INSERT). Mutation: disable **only**
  `cost_optimizer_runs_citations_guard`; the same parent commits; restore
  `tgenabled='O'`.
- **P-cite-late-child** COMMIT a valid `none` / `citation_count=0` parent
  (zero children). Then INSERT one published citation against that run:
  refused by `cost_optimizer_citations_row_guard` (the parent-table
  instance does not re-fire). Mutation: disable **only**
  `cost_optimizer_citations_row_guard`; the late INSERT commits; restore
  `tgenabled='O'`.
- **P-pub-later** publish; insert a fourth project's `cost_events`; publish
  again; latest `cost:model_inference.n_projects` is 4 (if that fourth
  project is a third tenant, still published). First snapshot unchanged
  (append-only).
- **P-20** Alembic head is `0061`. Downgrade with rows present fails closed;
  empty downgrade 0061→0060 succeeds.
- **P-21** `learning_publish.py` source does not mention `production_autonomy`,
  `readiness`, `control_loop`, `broker`, or `matrix`.
- **P-22** no public function in `app.ecosystem.learning_publish`,
  `learning`, `cost_optimizer` has a parameter named `content`, `document`,
  `prompt`, `body`, `evidence_pack`, or `schema` (`inspect.signature`).
- **P-23** connector publisher SQL: `target_ref` / `reference_name` /
  `manager` / `repo_ref` absent (covered by P-4/P-sql-allowlist). A monitoring
  snapshot with a distinctive `target_ref` does not appear in any bucket_key
  or metric (P-23b: bucket_keys are exactly the 12 OD-2.1 strings).

---

## 6. Documentation language, required

`CLAUDE.md` and `README.md` must:

- Carry the §0.3 honesty crux verbatim.
- State Slice 62 **implements** the §17.5 / App. C l.3009 allowed/forbidden
  split for the seven named classes, with the k-threshold labelled a
  **publication threshold, not a privacy proof**, and the consent path
  **unbuilt**.
- State it does **not** meet the Slice 61 exit; D-8 / D-9 / D-10 stay OPEN.
- State A5 `slice54.v1`, readiness `slice20.v1`,
  `can_go_live_autonomously` literal `False`.
- State a freshly migrated database has no aggregates until
  `make learning-publish`.
- Record no test counts in `README.md`.

Roadmap Slice 62 **Exit** may be marked as the bounded optimizer + tenant-safe
publisher delivered, with the honesty limitations above. Do not mark Slice 61
done. Do not claim go-live.

---

## 7. Deferred / not claimed

| Capability | Disposition |
|---|---|
| Slice 61 exit / D-8 / D-9 / D-10 | Stay OPEN, owner = Salim |
| Consent artifact + retention + removal (l.1750) | Deferred; content is refused |
| Actuated model routing / broker wiring | Forbidden this slice |
| Production latency / RUM | No source; harness latency only |
| Differential privacy / reconstruction proof | Refused as a claim |
| HTTP API | Deferred |
| Platform-event audit of global publish | Deferred (Slice 6 same) |
| Using §19.5 USD envelopes | Forbidden (owner: no budget figures) |
| A5 / readiness / go-live movement | Forbidden |

---

## 8. Non-goals, restated

No change to the ten frozen files. No new tool, A1 action, connector, LLM call,
or PRICE_CARD entry. No forecast arithmetic change. No STOP mutation. No catalog
change. No HTTP. No go-live flip.

---

## 9. Builder constraints

- TDD: P-1…P-6 and failing P-7/P-8 first.
- Do not `ruff format` the whole tree.
- pyright on CI owned paths **plus** every new Slice-62 module and test listed
  in §4; 0 errors on that set.
- Every new refusal test must fail when its named trigger/behaviour is removed
  (mutation probe) and restore `tgenabled='O'`.
- Conventional commits. Do not commit `.env`. Do not edit this plan.
- Line cap 500 per file. Split rather than grow.
- `make learning-publish` uses `ADMIN_DATABASE_URL`. Do not fold publish into
  `make migrate` / `test-db-migrate`.

---

## 10. Change log

**v1.** First version. Grounded on `main` @ `59af1c7` (Slice 61b merged, Alembic
head `0060`).

**v1 → v2 (ten reviewer defects, all accepted).**

1. **Tool universe off-by-one.** Live `TOOL_REGISTRY` has 13 keys, not 12.
   `EXPECTED_BUCKET_COUNT=62`. §2.2 lists the 13 keys. Frozen `registry.py`
   unchanged.
2. **Unpublished buckets were runtime-readable.** `uaid_app` has no SELECT on
   `cross_project_aggregate_buckets`; SELECT only on security-barrier view
   `cross_project_published_buckets` (`WHERE published`). P-unpub-hidden.
3. **P-opt-learn-db / P-14b missing budgets.** Missing budget is STOP/`hold`.
   Both probes now seed a per-project budget strictly above spend.
4. **`overlay='none'` vs unclamped `policy_tier`.** Split `base_policy_tier` /
   `clamped_policy_tier`; `hold` excluded from both; `none` compares to clamped.
5. **Child-before-parent.** Publisher inserts the run row first, then 62
   buckets; optimizer inserts the run then citations.
6. **`publisher` was free text.** CHECK-locked to `slice62.learning_publish`.
   P-publisher-literal.
7. **Optimizer bindings were unenforced.** Recorded-policy composite FK;
   aggregate_run_id NULL-shape; published_bucket_count rebound to the cited
   run; overlay-specific citation guards; P-overlay-shape; P-cite-count-mutation.
   Clamp arithmetic remains app-derived.
8. **P-19 was not a count-guard mutation.** Split P-19-universe vs P-19-count.
   Added P-pubcount-mutation and dual citation-count mutation.
9. **Shortcut/acceptance mapped to `mid_quality` against spec "high-quality".**
   New `high_quality` tier; those two floor there; judgment-oracle multi-reviewer
   / model-diversity recorded as non-actuated booleans (P-opt-judgment).
10. **§4 listed no tests.** Exact test files and pyright scope are in §4.

**v2 → v3 (four reviewer defects, all accepted).**

1. **Citation trigger would run as `uaid_app` and could not read the revoked
   base table.** Guard joins `cross_project_published_buckets` only. FK to
   the base PK remains (views cannot be FK targets) and does not grant SELECT.
   P-cite-uaid-app.
2. **`policy_version_id` proved existence, not flag equality.** Trigger
   `cost_optimizer_runs_policy_flags_match` compares all three booleans.
   P-policy-flags + mutation.
3. **High-risk `code_review` was a one-step promote to `high_quality`.** Spec
   l.1876 is frontier for high-risk PRs. Direct clamp to `frontier` when
   `frontier_for_high_risk=True`. P-opt-review-high.
4. **Count-trigger mutation was masked by overlay-shape.** One trigger
   `cost_optimizer_citations_guard`. P-cite-guard-mutation.

**v3 → v4 (one reviewer defect, accepted; owner authorized this round).**

1. **A citation-table INSERT trigger cannot refuse a parent that needs
   citations when zero children are inserted — no event fires.** One
   function `cost_optimizer_citations_guard()`; two deferred instances:
   `cost_optimizer_runs_citations_guard` (parent INSERT) and
   `cost_optimizer_citations_row_guard` (citation INSERT).
   P-cite-parent-zero and P-cite-late-child are separate mutation probes.
