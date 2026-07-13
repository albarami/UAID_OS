# Slice 51 — Cost forecast model (A5 gate #9) — PLAN v1

**Status:** MERGED — historical record. Implemented via PR #92 (squash commit `0dbacb3`); this v1 plan is retained as the approved design rationale for Slice 51.

> **Citation key / Sanad discipline.** `spec:N-M` means numbered lines in
> `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`; `template21:N-M` means
> `docs/UAID_OS_Intake_Template_Pack_v1_2/21_cost_and_resource_policy.yaml`; bare source paths use
> repository line numbers as observed at plan time. Prospective choices are labelled **proposed**,
> **recommended**, **inference**, or **assumption**; none is reported as existing behavior.

## Coordinator rulings (final)

OD-51-1 = Option A: append-only cost_forecast_policy_versions validated against the exact canonical file-21 field set, stamped caller_supplied_unverified_structured_cost_policy; budgets unchanged as the all-cost STOP ceiling; both required for gate #9; the template's zero-valued caps are invalid for a live gate-bearing policy. Confirmed: gate #9 means "within the recorded structured policy" — never verified human/finance/procurement authority.

OD-51-2 = Option A: explicit remaining-work envelope over all eight COST_COMPONENTS (explicit zeros required; omission is not zero); model-inference remaining USD derived only from reported token quantities × exact snapshotted ModelPrice rates (missing/invalid price for nonzero planned tokens refuses); non-model remaining USD and CI minutes are labeled REPORTED assumptions; no burn-rate extrapolation, no task-contract unit-cost bridge; PRICE_CARD untouched.

OD-51-3 = Option A: all six gate-bearing dimensions mandatory (two budgets all-cost caps + four file-21 caps, all positive); full non-vacuous coverage per plan §3.5; routing booleans and non-budget stop conditions validated/snapshotted but diagnostic — never claimed enforced.

OD-51-4 = Option A: utilization_percent = forecast/limit × 100 per dimension; approval trigger = max_utilization > percentage (strict; equality does not trigger); hard-cap reach/exceed fails regardless; an approval-required result below hard caps is recorded honestly but is not gate-eligible this slice — no approval is created or consumed. The §19.7 boolean is never silently equated with the file-21 percentage.

OD-51-5 = Option A: binding = latest frozen candidate + latest complete re-auditable Slice-49 core (plus policy/budget/ledger/assumption/price/contract digests and UTC date per plan §3.6); no frozen candidate or no re-auditable core ⇒ gate #9 cannot pass; no candidate→cost-completeness claim.

OD-51-6 = Option A: content/binding latest-wins (created_at DESC, id DESC); later failed/refused attempts supersede older passes; any input-digest change de-currents; daily dimensions expire at the end of their named UTC day (semantic horizon validity); no additional wall-clock TTL; as_of/UTC date injectable in tests, never session-timezone-dependent.

OD-51-7 = Option A: an active Slice-7 STOP (no_budget, total >=, or daily >=) always blocks gate #9; the forecast never clears STOP, unpauses a run, or mutates a budget; hard-limit semantics are strictly-below because STOP fires at >=.

OD-51-8 = Option A: the five normalized append-only tables with generated row-local columns and deferred DB re-verification of child sets, digests, arithmetic, outcome/result duality, approval flag, STOP snapshot, and gate eligibility; only the additive UNIQUE(id, project_id, tenant_id) targets on cost_events and budgets — no row or meaning changes; succeeded runs require all four identities and one exact complete child set; failed/refused runs have no result children.

OD-51-9 = recommended ruling: the three contract versions, the stated caps and NUMERIC scales, the 13-rung gate ladder exactly as written (ending passed:system_derived_cost_forecast_within_recorded_policy), safe gate context and audit surface per the plan's lists (no raw model IDs, assumption values, or policy YAML anywhere in audit/context), and downgrade 0050→0049 failing closed while any Slice-51 row exists.

Two consequences are explicitly accepted: a gate-#9 pass rests partly on honestly-labeled declared assumptions (inherent to any forecast), and gate #9 requires a forecast generated on the current UTC day (recurring operational cadence).

## 0. The defining honesty constraint (the crux)

A Slice-51 forecast can be a **deterministic projection from an exact, bounded input snapshot**. It cannot be
DB-proven future spend, a provider quote, a procurement commitment, a guarantee that all remaining work was
declared, or proof that real-world costs will stay inside a ceiling. The specification itself labels its worked
economic values a policy-envelope example rather than vendor quotes and says actual cost depends on provider
rates, context size, tool use, cloud runtime, and human review (`spec:1881-1889`). Appendix B asks only whether
the “cost forecast is within policy”; it does not upgrade a forecast into fact (`spec:2981-2997`).

This plan therefore keeps five truth layers separate:

1. **REPORTED / DECLARED.** A project policy payload, remaining-work quantities, non-model future-dollar
   assumptions, a forecast horizon, and actor/source labels are declarations. The current budget writer also
   accepts an untrusted actor label and proves no human approval (`app/repositories/cost.py:1-7,184-225`;
   `app/models/budget.py:1-8`). Slice 51 must preserve that limitation.
2. **OPERATOR-CONFIGURED.** `app/llm/pricing.py` maps exact model IDs to prices, but the shipped card is empty and
   operator-supplied; an entry proves only which configured rate the algorithm used, not that a provider will
   charge it (`app/llm/pricing.py:1-35`).
3. **DB-PROVEN.** The database can prove which immutable `cost_events` rows, current `budgets` values, exact
   candidate/core, normalized assumption rows, and contract hashes were used. It can prove tenant/project
   binding, append-only history, arithmetic consistency, and exact child-set counts. It cannot prove that
   external spend omitted from the ledger or undeclared future work does not exist
   (`app/models/cost_event.py:1-14,50-106`; `app/models/budget.py:31-57`).
4. **SYSTEM-DERIVED COST FORECAST (proposed).** Versioned code may apply deterministic Decimal arithmetic to
   those exact inputs and stamp `system_derived_cost_forecast`. That tier means the calculation was performed by
   the ruled algorithm; it does **not** mean the future outcome was verified.
5. **GATE-INFERRED (proposed).** Gate #9 may say only that the latest current system-derived projection is inside
   the exact recorded policy under the ruled approval, freshness, coverage, and STOP conditions. It does not mean
   the policy has verified human authority, the forecast is accurate, A5 is satisfied, or production is approved.

The core honesty statement is:

> **A forecast proves reproducible arithmetic over recorded spend, recorded policy, operator-configured rates,
> and explicitly labelled planning assumptions. It never proves the future, input completeness, or spend
> certainty.**

### 0.1 Verified repository baseline for this plan

The following was re-verified from live files and Git before drafting; it is not inherited from a handoff:

- `git rev-parse HEAD` and `git rev-parse origin/main` both returned
  `3abb115a6587da72269cb6269c0b67a5f3b1229d`; the checked-out branch was `main`.
- `git status --porcelain` was empty. Local and remote branch inspection showed only `main` and `origin/main`.
- `UV_CACHE_DIR=/tmp/uaid-uv-cache uv run alembic heads` returned `0049 (head)`; migration `0049` revises `0048`
  and is additive over existing release/evidence objects (`migrations/versions/0049_release_verdicts.py:1-21`).
- A5 is `slice50.v1`; readiness is `slice20.v1`; the two exact no-go reasons are
  `a5_gates_not_all_satisfied` and `request_authenticated_a5_preapproval_not_implemented`
  (`app/release/production_autonomy.py:56-66`; `app/intake/readiness.py:45,57-60`).
- The current recorded suite counts are 931 Docker-free and 791 DB-backed
  (`CLAUDE.md:629-650,1297-1298,1398-1402`). No test command was run for this plan-only task.
- Before this file was added, symbol/file search found no Slice-51 plan, forecast module/model/repository, test,
  or migration. The roadmap’s sole next marker was Slice 51 and explicitly marked it not started
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:495-505,659-665`).

These are planning-time observations. Any later implementation must re-run them before branching.

---

## 1. Scope and non-goals

### 1.1 In scope after plan approval and all coordinator rulings

1. Define a strict, versioned structured-policy contract over the **actual** file-21 fields: four numeric caps,
   the forecast-percentage approval trigger, three routing booleans, and the listed stop-condition codes
   (`template21:1-15`; `spec:2668-2686`). Unknown fields and unruled values fail closed.
2. Record immutable project policy versions without pretending that the checked-in zero-valued template is a
   live project policy. `CLAUDE.md` identifies files 00–25 as blank project templates with defaults, while the
   actual file carries zero caps (`CLAUDE.md:1390-1396`; `template21:1-6`). Treating those zeros as usable policy
   would be an unsupported inference.
3. Add a pure deterministic forecast module using exact Decimal arithmetic and a coordinator-ruled v1 model.
   The recommended model is an explicit remaining-work envelope over all eight §19.2 cost components, combining
   immutable incurred ledger facts with labelled future assumptions; OD-51-2 controls the final model
   (`spec:1838-1849`; `app/cost.py:13-28,83-126`).
4. Reuse the exact existing model price-card reader for planned model work, snapshot only bounded rate facts and
   hashes needed to reproduce arithmetic, and keep `app/llm/pricing.py` unchanged
   (`app/llm/pricing.py:19-35`; proposed reuse).
5. Bind every gate-bearing forecast to the ruled release/project scope, current policy, current budget, exact
   ledger event set, exact planning-assumption set, exact price snapshot, and forecast-contract hash. Binding
   shape is OD-51-5.
6. Persist immutable attempts, exact normalized inputs, ledger-event references, per-policy-dimension results,
   and fail-closed outcomes in tenant-owned RLS ENABLE+FORCE tables. DB guards must re-prove the arithmetic and
   exact child sets against direct SQL (proposed design; OD-51-8).
7. Make A5 gate #9 PASS-capable under `slice51.v1` only through current, non-vacuous, exact-binding forecast
   evidence that satisfies the ruled ladder. Replace the current permanent
   `cost_stop_decision_only_no_forecast` branch; do not let `cost_policy_present=True` pass anything by itself
   (`app/release/production_autonomy.py:313-319`).
8. Preserve the incurred-cost STOP decision and Slice-8b STOP→pause behavior as a distinct control. A forecast
   may consume the current STOP outcome as an input but may never resume a run, raise a budget, or mutate runtime
   state (`app/cost.py:113-126`; `app/runtime/engine.py:348-400`).
9. Add pure and DB-backed tests, including direct-SQL attacks, truth-tier assertions, audit sentinels, golden A5
   regression, and the existing findings-guard MD5 pin. These tests are future implementation requirements only.

### 1.2 Non-goals

- No rollback verification (Slice 52), verified production pre-approval (Slice 53), emergency stop/rollback
  authority (Slice 54), or §23.3 control loop (Slice 55)
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:507-552,659-665`).
- No change to the Slice-7 incurred ledger schema, amount semantics, idempotency, budget writer, or
  `evaluate_stop` threshold. A narrowly additive composite-identity constraint on `cost_events` is permitted
  only if OD-51-8 requires it for a same-project child FK; no existing row is rewritten
  (`app/repositories/cost.py:47-170,173-250`; `migrations/versions/0008_cost_ledger.py:72-186`).
- No phase-budget subsystem. §19.3 requires budgets by phase, but neither the current `budgets` table nor the
  canonical file-21 template has a phase map; Slice 7 explicitly deferred per-phase budgets
  (`spec:1851-1863`; `app/models/budget.py:31-57`; `.planning/PHASE-1-PLAN.md:192-215`).
- No provider billing connector, cloud price catalog, CI provider API, procurement workflow, exchange rates,
  refunds/credits, multi-currency, price prediction, probabilistic confidence interval, Monte Carlo model, ML,
  or LLM forecast.
- No modification to `app/llm/pricing.py`; the slice reads exact configured entries only. No live network is
  needed, and no LLM client—fake or live—is involved.
- No automatic approval request or approval consumption. The approval-trigger interpretation is an OD; any
  “approval required” result is decision-only and blocking this slice unless the coordinator rules otherwise.
- No automatic budget increase, policy revision, cost-event creation, run pause/resume, agent/model rerouting,
  tool denial, release-candidate transition, evidence-pack regeneration, verdict regeneration, deploy, or other
  side effect.
- No evidence-pack schema/core mutation and no new canonical-export claim. The current pack schema has no cost
  forecast property and Slice-49 cores are immutable; Slice 51 can remain a separate gate-evidence source
  (`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:1-65`;
  `app/models/evidence_pack.py:160-246`; proposed non-goal).
- No HTTP endpoint or dashboard expansion. The existing cost route reports incurred total, current budget, and
  STOP decision only (`app/api/dashboard.py:141-167`).
- No change to `app/intake/readiness.py`; it remains byte-stable at `slice20.v1`.
- No go-live. Both hard no-go reasons remain byte-identical regardless of gate #9.

---

## 2. Current repository truth and the gaps Slice 51 must close honestly

### 2.1 The canonical template and §19.7 example materially differ

The shipped file-21 template declares:

- `max_total_model_cost_usd`;
- `max_daily_model_cost_usd`;
- `max_cloud_spend_usd`;
- `max_ci_minutes_per_day`;
- `require_approval_above_forecast_percentage: 20`;
- three routing booleans; and
- four stop-condition codes, including `model_provider_outage_extended`
  (`template21:1-15`; the same shape appears at `spec:2668-2686`).

The §19.7 illustrative YAML instead uses two model-cost caps, the boolean
`require_approval_if_forecast_exceeds_budget: true`, and a stop list that includes
`missing_oracle_for_critical_feature` rather than `model_provider_outage_extended`
(`spec:1915-1933`). The spec does not define how the file-21 percentage denominator works. Therefore the plan
must not silently convert `20` into “20% of budget,” “120% of budget,” “20% change from the last forecast,” or
an approval waiver. Policy authority and percentage semantics require OD-51-1/4.

### 2.2 The existing budget is not the canonical file-21 policy

`budgets` stores only `max_total_cost_usd` and optional `max_daily_cost_usd`; those are all-component ceilings
used by `evaluate_stop`, not the template’s model/cloud/CI split
(`app/models/budget.py:31-57`; `app/cost.py:69-75,113-126`). `BudgetRepository.upsert` mutates that row and
audits before/after values; it does not version a file-21 policy or validate the template’s other fields
(`app/repositories/cost.py:173-225`).

**Inference:** the gate needs a distinct structured policy version or an explicitly ruled extension of the
budget row. Treating the budget as if it already represented all file-21 fields would be a false provenance
upgrade. OD-51-1 chooses the authority/storage seam.

### 2.3 The ledger proves incurred rows, not forecast completeness

The current ledger is strong about what it stores: eight code/DB-enforced components, Decimal/`NUMERIC(18,6)`,
immutable rows, source-namespaced idempotency, tenant/project/run FKs, and UTC half-open daily sums
(`app/cost.py:13-28,77-126`; `app/models/cost_event.py:36-106`;
`app/repositories/cost.py:47-170`). It does **not** store model route, token counts, a quantity unit, task-contract
identity, remaining-work estimates, forecast horizon, policy version, or provider invoice verification
(`app/models/cost_event.py:84-106`).

Consequences:

- `quantity` cannot be silently reinterpreted as CI minutes or tokens because it has no unit field;
- a populated ledger does not prove all external costs were captured;
- an empty ledger does not prove zero spend; and
- historical averages cannot be mapped to remaining task contracts without an unsupported bridge.

The first three are direct limitations of the stored shape; the last is an inference from the absence of a
task/forecast link (`app/models/cost_event.py:90-100`; `app/models/task_contract.py`; symbol search).

### 2.4 The existing STOP decision is a current incurred-spend control

`evaluate_stop` returns STOP for no budget, total spend at/above the total cap, or daily spend at/above the daily
cap; otherwise it returns OK (`app/cost.py:47-75,113-126`). `CostEventRepository` always records valid incurred
cost even over budget, and module-level `evaluate` composes current sums and the budget into that decision
(`app/repositories/cost.py:47-65,228-250`). Slice 8b consumes STOP at a step boundary and pauses before the next
demo node; it does not forecast (`app/runtime/engine.py:22-28,348-400`).

A forecast cannot replace this control. Whether current STOP must block gate #9 even if forecast arithmetic is
otherwise within a newly recorded policy is a genuine rule choice, surfaced in OD-51-7.

### 2.5 The price card is real machinery but not durable provider truth

`get_price` resolves an exact model ID and fails closed when absent, while `PRICE_CARD` is intentionally empty and
operator-supplied (`app/llm/pricing.py:1-35`). Existing LLM paths use rate × token arithmetic for projected or
actual model cost (`app/intake/extraction.py:73-93`). Slices 43, 45, and 48 already reuse that boundary by
resolving exact reviewer/model routes and passing `ModelPrice` into the same arithmetic
(`app/repositories/test_oracles.py:439-476`; `app/repositories/shortcut_detectors.py:319-335`;
`app/repositories/reviewer_quality.py:112-140`). This is reusable for model forecast lines, but it cannot
price cloud runtime, CI minutes, storage, tools, monitoring, human review, or rework. It also provides no durable
price-version record.

The proposed forecast must therefore snapshot exact rates/hashes used for model arithmetic, label them
operator-configured, and keep non-model assumptions explicitly REPORTED. OD-51-2 chooses how much structured
future-work input v1 requires.

### 2.6 Gate #9 is permanently insufficient today

The pure evaluator currently makes gate #9 `insufficient_evidence` in both cases:

- budget row present → `cost_stop_decision_only_no_forecast`; or
- budget row absent → `no_cost_policy_and_no_forecast`
  (`app/release/production_autonomy.py:313-319`).

The repository supplies only `cost_policy_present=budget is not None`; no forecast repository or exact-binding
coverage object exists (`app/repositories/production_autonomy.py:111-123,211-216`). Appendix B nevertheless
requires “cost forecast is within policy” (`spec:2981-2997`). Slice 51 must retire the permanent branch without
letting a bare budget-presence boolean or caller-supplied `within_policy` value pass.

### 2.7 A release-scoped binding is not specified by Appendix B

The roadmap schedules Slice 51 after the evidence core and release verdict, but Appendix B #9 names no candidate,
pack, commit, or horizon (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:483-505`; `spec:2993`). The repository now has
an exact frozen-candidate and immutable-core vocabulary from Slices 25/49/50
(`app/models/release_candidate.py:30-77`; `app/models/evidence_pack.py:53-246`;
`app/models/release_verdict.py`).

**Inference:** a production-autonomy gate should not accept a forecast for an unrelated project snapshot, but
the exact binding—project only versus latest frozen candidate versus candidate+core—requires OD-51-5.

---

## 3. Proposed design semantics (contingent on §4 rulings)

### 3.1 Proposed forecast scope and vocabulary

The recommended v1 scope is `known_recorded_cost_plus_declared_remaining_to_release`: incurred ledger rows up to
one exact `as_of` instant plus a structured, explicitly REPORTED remaining-work envelope for one exact current
release scope. The wording must appear in records and gate context. It must never be shortened to “total future
cost” or “verified cost.” This is a conservative engineering inference, not verbatim spec language.

Proposed provenance/status vocabulary:

- policy source: `caller_supplied_unverified_structured_cost_policy`;
- remaining-work source: `reported_cost_forecast_assumption`;
- price source: `operator_configured_price_card_snapshot`;
- ledger source: `db_bound_incurred_cost_events`;
- forecast execution: `system_derived_cost_forecast`;
- outcomes: `succeeded | refused | failed`;
- result states: `within_limit | limit_reached_or_exceeded | approval_required | missing_input |
  inconsistent_input`.

All names are proposed bounded codes and require coordinator ruling; they do not retroactively relabel existing
`cost_events`, `budgets`, audit actors, or price-card entries.

### 3.2 Recommended deterministic model

**Recommended, contingent on OD-51-2:** use an explicit remaining-work envelope rather than extrapolating an
unobserved completion date from burn rate.

For each of the eight `COST_COMPONENTS`, using Decimal only:

```text
known_incurred_total[component] = SUM(exact referenced cost_events.amount_usd)
forecast_total[component]       = known_incurred_total[component]
                                  + reported_remaining_total_usd[component]

known_incurred_today[component] = SUM(exact referenced events in the UTC half-open current-day window)
forecast_today[component]       = known_incurred_today[component]
                                  + reported_remaining_today_usd[component]
```

For planned model work, `reported_remaining_*_usd[model_inference]` is not accepted directly: it is derived from
one or more exact model-route hashes, reported remaining input/output token quantities, and snapshotted
`ModelPrice` values using the same rate arithmetic as `project_cost`
(`app/intake/extraction.py:73-84`; proposed extension). For non-model components, v1 has no authoritative rate
catalog, so remaining USD is a labelled planning assumption. CI minutes are a separate reported quantity and are
never inferred from `cost_events.quantity` (`app/models/cost_event.py:91-100`).

Required all-cost aggregates:

```text
forecast_total_all_usd = SUM(forecast_total[all 8 components])
forecast_today_all_usd = SUM(forecast_today[all 8 components])
```

The forecast input must include all eight components exactly once, including explicit zeros; omission is not
zero. `reported_remaining_today_usd <= reported_remaining_total_usd` per component. Any future-dated “incurred”
ledger event relative to `as_of` refuses the run rather than being silently ignored. Those are recommended
fail-closed rules, not current ledger behavior.

### 3.3 Recommended six gate-bearing policy dimensions

To avoid silently dropping either the Slice-7 ceiling or the canonical template, the recommended result set has
exactly six dimensions:

| Dimension | Forecast value | Limit source | Source status |
|---|---|---|---|
| `all_cost_total_usd` | `forecast_total_all_usd` | `budgets.max_total_cost_usd` | existing DB row, mutable/audited, authority unverified |
| `all_cost_daily_usd` | `forecast_today_all_usd` | `budgets.max_daily_cost_usd` | existing optional DB field; proposed mandatory for gate |
| `model_cost_total_usd` | model incurred + model remaining | file-21 `max_total_model_cost_usd` | proposed policy version |
| `model_cost_daily_usd` | today model incurred + model remaining today | file-21 `max_daily_model_cost_usd` | proposed policy version |
| `cloud_spend_total_usd` | cloud incurred + cloud remaining | file-21 `max_cloud_spend_usd` | proposed policy version |
| `ci_minutes_daily` | explicit planned/current-day CI minutes | file-21 `max_ci_minutes_per_day` | reported quantity; not ledger-inferred |

The first two preserve the existing all-component economic envelope; the other four implement the actual
template fields (`app/models/budget.py:55-57`; `template21:1-6`). Every denominator must be positive. A missing
budget, NULL daily budget, missing policy, zero cap, missing ledger history, missing component line, missing price
for planned model work, or missing CI-minutes input refuses or fails the run with an exact reason. OD-51-3 rules
the final mandatory set.

Recommended hard-limit semantics are **strictly below** each cap, because Slice 7 STOPs at `>=`; “at the stop
threshold” must not simultaneously read as forecast-safe (`app/cost.py:119-126`; inference).

### 3.4 Approval-trigger semantics are separate from hard-limit semantics

The template says “above forecast percentage” but does not define a denominator (`template21:6`; §2.1 above).
Under recommended OD-51-4 Option A:

```text
utilization_percent[dimension] = forecast_value / positive_limit * 100
max_utilization_percent        = MAX(all six exact dimension utilizations)
approval_required              = max_utilization_percent
                                 > require_approval_above_forecast_percentage
```

“Above” is strict: equality does not trigger. A hard-cap reach/exceed remains a policy failure regardless of
approval. An approval-required result below every hard cap is recorded honestly but is **not gate-eligible in
Slice 51**, because this slice neither creates nor proves the verified authority required to waive/escalate cost.
No generic `approvals` row is consumed and no request is auto-created. This interpretation is recommended, not
specified; OD-51-4 must rule it.

### 3.5 Non-vacuous coverage rule

Recommended gate-bearing coverage requires all of the following:

- one current structured policy version with exact allowed fields;
- one current budget with positive total and daily ceilings;
- at least one immutable ledger event in the exact event inventory;
- all eight cost-component assumption lines, including explicit zeros;
- complete model price snapshots for every nonzero planned model route;
- one explicit CI-minutes input for the current UTC day;
- exactly six dimension results;
- consistent child counts, digests, arithmetic, and current binding; and
- no infrastructure/refusal outcome.

The “at least one ledger event” rule follows the user-required fail-closed no-history behavior, but it does not
turn one event into a completeness proof. A zero-amount event is still only a recorded row; tests must retain the
limitation. Exact rules are OD-51-3/8.

### 3.6 Binding and currentness

Recommended OD-51-5/6 binding:

```text
(tenant, project,
 current latest frozen release candidate,
 current latest complete/re-auditable evidence-pack core for that candidate,
 policy-version digest,
 current budget-value digest,
 exact ledger-event-set digest,
 exact assumption-set digest,
 exact price-snapshot digest,
 forecast-contract hash,
 UTC forecast date)
```

The forecast is immutable history. Gate currentness is computed, never patched into an old row. Any new cost
event, budget value change, newer policy version, assumption/price/contract change, candidate/core change, child
digest mismatch, or later failed/refused attempt de-currents the older pass. A daily result expires at the end of
its named UTC calendar day because its denominator and daily-spend window are day-specific; this is semantic
horizon validity, not an arbitrary TTL. No additional wall-clock TTL is recommended absent a policy field.

Historical records remain queryable as history but cannot satisfy the current gate after invalidation.

### 3.7 STOP remains an independent, stronger current blocker

Recommended OD-51-7 behavior:

- calculate the current Slice-7 STOP decision from current ledger totals and budget at forecast generation and
  gate evaluation;
- if STOP is active for `no_budget`, `budget_exceeded`, or `daily_budget_exceeded`, gate #9 cannot pass;
- never let a forecast outcome alter STOP, unpause a run, change a budget, or suppress a `cost_paused` event; and
- a later budget change/new spend invalidates the forecast through current digests before either control is
  reported as satisfied.

This keeps “incurred spend has already hit a ceiling” distinct from “projected cost is within a declared
envelope” while preventing contradictory pass/STOP output (`app/cost.py:47-75,113-126`;
`app/runtime/engine.py:366-400`; recommended inference).

---

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-51-1 — What is the authoritative project cost-policy record, and how does it relate to `budgets`?

**Option A — append-only structured file-21 policy versions alongside unchanged budgets (recommended).** Add
`cost_forecast_policy_versions`, validated against the exact canonical template field set. Stamp the source
`caller_supplied_unverified_structured_cost_policy`; do not claim verified owner authority. Keep `budgets` as
the existing all-cost STOP ceiling and require both sources for gate #9. The template’s zero defaults are invalid
for a gate-bearing live policy. This preserves meanings rather than widening `budgets` silently.

**Option B — add the file-21 columns to mutable `budgets`.** Fewer tables, but it mixes all-cost Slice-7 STOP
semantics with model/cloud/CI policy, loses append-only policy history, and increases the blast radius of a mature
table. Not recommended.

**Option C — use `budgets` alone.** Rejected for v1 planning: it ignores three canonical resource dimensions and
the actual approval-percentage field (`template21:1-15`; `app/models/budget.py:55-57`).

If Option A is ruled, the coordinator must also confirm that gate #9 means “within the recorded structured
policy” and does not claim that the caller-supplied policy has verified human/procurement authority. Gate #12 and
future authority work remain separate.

### OD-51-2 — Which deterministic forecast model and input truth tiers does v1 use?

**Option A — explicit remaining-work envelope over all eight components (recommended).** Use §3.2: exact
incurred ledger rows + all-eight explicit remaining-total/today assumptions; derive model USD from token plans
and exact price-card snapshots; accept other future USD and CI minutes only as REPORTED assumptions. This is
simple, explainable, and honest about what cannot be inferred.

**Option B — historical burn-rate extrapolation.** Project a fixed lookback across a fixed future window. This
avoids caller remaining-dollar inputs but requires invented lookback/horizon rules, assumes past burn predicts
remaining work, and has no completion-date source. It is not recommended absent new policy fields.

**Option C — task-contract/issue-count unit-cost model.** Estimate remaining cost from task/issue counts and
historical average cost. The ledger has no task-contract or issue identity, so the join and unit-cost meaning are
not DB-proven; implementing it would broaden scope substantially. Not recommended.

All options must call the result a projection, not verified future cost. Option A must refuse nonzero planned
model tokens with a missing, negative, non-finite, over-scale, or all-zero price snapshot; `PRICE_CARD` remains
unchanged and may be injected in tests (`app/llm/pricing.py:25-35`; `app/cost.py:83-110`).

### OD-51-3 — Which policy dimensions and completeness conditions are mandatory?

**Option A — all six dimensions plus non-vacuous input coverage (recommended).** Require the two existing
all-cost budget caps and all four file-21 numeric caps, all positive; require all eight component assumptions,
ledger history, exact model price coverage, CI minutes, and six results. Routing booleans and non-budget stop
conditions are validated/snapshotted but diagnostic in this gate; they are not silently claimed enforced.

**Option B — canonical four fields only.** Closer to file 21, but permits tool/storage/human/rework costs to evade
the existing all-cost budget, and disconnects gate #9 from Slice-7 STOP ceilings.

**Option C — total all-cost budget only.** Simplest, but does not implement the canonical model/cloud/CI policy
shape and contradicts the roadmap’s file-21 grounding.

Under every option: no policy, no budget, no spend history, any required zero denominator, missing dimension,
unknown policy/stop/routing key, or inconsistent child set fails closed with an exact reason. A zero assumption
must be explicit and never means universal absence.

### OD-51-4 — What does `require_approval_above_forecast_percentage` mean, and can approval make gate #9 pass?

**Option A — percentage utilization of the tightest applicable cap; decision-only blocker (recommended).** Use
§3.4. Above the threshold means `max(forecast/limit*100) > percentage`; equality does not trigger. Reaching any
hard cap fails. Below hard caps but above the approval trigger records `approval_required` and keeps gate #9
insufficient; Slice 51 creates/consumes no approval.

**Option B — percentage tolerance above budget (`100 + value`).** A value of 20 means approval above 120% of a
cap. This makes approval relevant only after the forecast is already outside the “within policy” hard limit and
does not fit the field name cleanly. Not recommended.

**Option C — percentage change from prior forecast.** This is useful operationally but no baseline/change
semantics appear in the spec or template. Rejected absent a new policy source.

The §19.7 boolean `require_approval_if_forecast_exceeds_budget` and the file-21 percentage cannot be silently
treated as identical (`spec:1917-1933,2668-2686`).

### OD-51-5 — What exact release/project scope binds a gate-bearing forecast?

**Option A — latest frozen candidate + latest complete re-auditable Slice-49 core (recommended).** Bind the
forecast to the current exact candidate/core while keeping cost inputs separate from immutable core bytes. No
frozen candidate or no complete/re-auditable core means gate #9 cannot pass. This follows the S49/S50 exact-
release evidence pattern without mutating the pack.

**Option B — latest frozen candidate only.** Less coupling, but provides no exact evidence-snapshot identity and
can leave the forecast current after the release evidence set changes.

**Option C — project only.** Matches Appendix B’s underspecified wording but permits a forecast for one project
state to satisfy another release candidate. Not recommended.

No option may claim candidate→cost completeness, candidate→provider invoice identity, or evidence-pack inclusion.

### OD-51-6 — What invalidates a forecast, and what time rule applies?

**Option A — content/binding latest-wins plus UTC-day semantic expiry; no extra TTL (recommended).** Use §3.6.
Order attempts `(created_at DESC, id DESC)` for the exact scope; later failed/refused attempts supersede older
passes. Any input digest/binding change invalidates. Daily dimensions are current only on their named UTC date.
No additional wall-clock TTL is invented.

**Option B — Option A plus a fixed 24-hour TTL.** Operationally conservative but neither spec nor file 21
declares 24 hours; it would be an ungrounded policy constant.

**Option C — content-only with no UTC-day expiry.** A “daily” forecast could satisfy tomorrow’s gate using
yesterday’s daily spend window. Rejected.

The chosen design must inject `as_of`/UTC date in pure tests and never rely on session timezone.

### OD-51-7 — Does an active Slice-7 STOP block gate #9?

**Option A — yes, always (recommended).** `no_budget`, total-cap `>=`, or daily-cap `>=` keeps gate #9
insufficient even if a separate forecast result appears within another policy dimension. STOP remains unchanged
and decision-only; the forecast cannot clear it.

**Option B — expose STOP as context but permit gate #9 to pass independently.** This preserves formal gate
separation but allows the report to say forecast-within-policy while incurred spend is already stopped under the
same project budget. Not recommended.

**Option C — forecast replaces STOP.** Rejected: it would weaken Slice-7/8b behavior and conflate incurred and
future cost (`app/runtime/engine.py:366-400`).

### OD-51-8 — How is forecast arithmetic and exact input membership made non-fakeable in storage?

**Option A — normalized append-only inputs/results plus deferred DB re-verification (recommended).** Add policy
versions, run attempts/summaries, exact ledger-event refs, assumption/price input lines, and exactly-six
dimension results. Composite FKs prove same tenant/project/candidate/core/policy/run identity. Generated columns
own row-local sums/ratios/limit flags where PostgreSQL permits; deferred constraint triggers re-derive child sets,
digests, aggregates, outcome/result duality, approval flag, STOP snapshot, and gate eligibility. Add only the
`UNIQUE(id,project_id,tenant_id)` targets needed on immutable `cost_events` and mutable `budgets`; no row or
meaning changes. A missing-evidence identity may be NULL only on a failed/refused attempt with the matching
reason; every present identity remains same-project pinned, and every succeeded run requires all identities.

**Option B — one JSONB forecast snapshot.** Smaller migration, but child completeness, exact ledger membership,
price inputs, arithmetic, and direct-SQL forgery become app-only claims. Not recommended.

**Option C — compute on read with no persistence.** Avoids migration but cannot provide immutable evidence,
latest failed-attempt precedence, reproducible exact inputs, or an audit trail for A5 gate #9. Not recommended.

Infrastructure errors/refusals remain visible attempts and never count as forecast misses or within-policy
evidence. A `succeeded` run must have one exact complete child set; a failed/refused run has no result children.

### OD-51-9 — What exact gate ladder, contracts, caps, audit surface, and downgrade rule ship?

**Recommended ruling:**

- contracts `slice51.cost_policy.v1`, `slice51.cost_forecast_input.v1`, and
  `slice51.cost_forecast.v1`, each with code-owned canonical SHA-256 hashes;
- at most 50,000 ledger-event refs and 1,000 assumption/price lines per run; exactly eight component aggregates
  and six policy-dimension results; at most 128 model-route price lines;
- money `NUMERIC(18,6)`; token/minute quantities non-negative bounded integers; percentage
  `NUMERIC(9,4)` within `0..100`; codes ≤128, source labels ≤255, evidence refs ≤500, all required strings
  non-blank; no raw YAML, prose, model prompts/responses, credentials, provider payloads, invoices, or secrets;
- gate #9 ladder, in order:
  1. `no_current_release_scope`;
  2. `no_current_structured_cost_policy` / `cost_policy_invalid`;
  3. `no_current_cost_budget` / `cost_budget_invalid`;
  4. `no_cost_history`;
  5. `cost_forecast_not_run`;
  6. `cost_forecast_latest_attempt_failed_or_refused`;
  7. `cost_forecast_binding_stale`;
  8. `cost_forecast_input_or_price_coverage_incomplete`;
  9. `cost_forecast_evidence_inconsistent`;
  10. `cost_stop_active`;
  11. `cost_forecast_limit_reached_or_exceeded`;
  12. `cost_forecast_requires_approval`;
  13. `passed:system_derived_cost_forecast_within_recorded_policy`;
- safe gate context contains counts, booleans, UTC date, dimension/reason codes, contract/policy/input digests,
  and provenance labels—never raw model IDs, actor/source prose, assumption values, policy YAML, or secrets;
- audit contains only project/candidate/core/policy/run IDs, contract/digest values, counts, outcome/reason codes,
  UTC date, and safe booleans; it excludes monetary/quantity assumptions, limits, model IDs, actor/source prose,
  raw YAML, cost descriptions/external refs, prompts/responses, URLs, tokens, and credentials; and
- downgrade `0050→0049` fails closed while any Slice-51 row exists. With no rows it drops only Slice-51 objects
  and the additive `cost_events`/`budgets` composite unique targets. It never deletes, relabels, or weakens
  existing data.

The ladder and caps are recommended engineering choices requiring an explicit ruling.

---

## 5. Proposed pure module (contingent on §4 rulings)

### 5.1 `app/cost_forecast.py`

Proposed responsibilities:

- exact constants for all eight `COST_COMPONENTS` imported from `app.cost`, the six ruled policy dimensions,
  outcome/reason/provenance vocabularies, and version/hash constants;
- frozen `StructuredCostPolicy`, `LedgerCostView`, `ForecastAssumptionLine`, `ModelPriceLine`,
  `ForecastDimensionResult`, and `CostForecastDecision` value types with bounded structural/scalar fields only;
- strict parser/validator for the exact `cost_and_resource_policy` root and full allowlisted template shape;
- Decimal validation through `app.cost.to_decimal`; no float/bool/non-finite/negative/over-scale value;
- deterministic model token × snapshotted rate arithmetic, per-component totals, current-UTC-day totals,
  all-cost sums, ratios, strict threshold comparisons, approval flag, STOP interaction, and reason precedence;
- canonical ordering and SHA-256 digests for policy, budget values, ledger refs, assumptions, price snapshot,
  dimension results, and complete input;
- fail-closed checks for missing/extra/duplicate component/dimension/model lines, zero denominators, incomplete
  rates, future-dated incurred rows, daily>total assumptions, overflow, and inconsistent totals; and
- no I/O, ORM, LLM, network, provider call, policy mutation, budget mutation, approval, runtime, or deployment.

The module may read `ModelPrice` values passed by the repository, but `app/llm/pricing.py` remains byte-stable.

---

## 6. Storage and expected migration `0050` (inference; additive-only after `0049`)

Migration numbering is an inference from the verified current head `0049`; the roadmap also says “possibly
`0050`” (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:495-505`). The reviewed implementation must use the actual
head at branch time.

### 6.1 `cost_forecast_policy_versions` — tenant-owned immutable normalized policy

Proposed columns:

- `id`, `tenant_id`, `project_id`;
- `policy_contract_version`, `policy_contract_hash`, `policy_digest`;
- the four exact template numeric caps and approval percentage;
- the three exact routing booleans;
- normalized allowlisted stop-condition codes and count;
- `source_provenance='caller_supplied_unverified_structured_cost_policy'`, bounded source/evidence labels;
- `created_at` with latest ordering `(created_at DESC,id DESC)`.

DB invariants: same-project composite FK; exact enum/hash/amount/percentage/bool/array shapes; positive gate caps;
no unknown stop code; derived count matches array length; immutable append-only; one exact digest per material
policy version for idempotent retry, while changed material creates a new row. The raw YAML and actor/source prose
do not persist.

### 6.2 `cost_forecast_runs` — tenant-owned immutable attempt + summary

Proposed columns:

- exact tenant/project plus nullable release-candidate, evidence-pack-core, policy-version, and budget identities;
- `as_of`, `forecast_utc_date`, scope code, all contract versions/hashes;
- snapshotted budget total/daily values + `budget_digest`;
- ledger/assumption/price/result/input digests and child counts;
- current STOP reason snapshot;
- `outcome`, `reason_code`, execution provenance, aggregate dimension counts;
- DB-verified `all_dimensions_within`, `approval_required`, `evidence_consistent`, `gate_eligible` summary;
- `created_at` for latest-wins.

Every present identity is composite-FK-pinned to the same tenant/project. Failed/refused attempts may leave the
particular missing or structurally unusable scope/policy/budget reference NULL so that the fail-closed attempt is
still durable; a `succeeded` run must have all four identities non-NULL. The migration may add only
`UNIQUE(id,project_id,tenant_id)` to `budgets` as the nullable budget identity's composite-FK target. Snapshotted
values and the budget digest preserve the exact values used. The DB verifies that a present core belongs to the
present candidate; no core bytes change (`app/models/budget.py:31-57`; proposed additive constraint/guards).

### 6.3 `cost_forecast_ledger_event_refs` — exact incurred-input inventory

One row per exact `cost_events` row used, with run/project/tenant composite FK, cost-event/project/tenant
composite FK, ordinal, event material digest, component, amount, and UTC occurrence metadata. Values must match
the referenced immutable row. The migration may add only `UNIQUE(id,project_id,tenant_id)` to `cost_events` as
the composite-FK target; because `id` is already the primary key, this adds identity proof without changing row
meaning (`app/models/cost_event.py:84-106`; proposed additive constraint).

The exact set is capped and duplicate/extra/missing/future-dated refs are refused. New cost events do not mutate
history; they make a prior run non-current at gate evaluation.

### 6.4 `cost_forecast_input_lines` — bounded reported assumptions and price snapshots

Proposed row kinds:

- exactly eight `component_remaining` aggregate lines, with total/today USD assumption and
  `reported_cost_forecast_assumption` provenance;
- zero to 128 `model_price` lines, each carrying model-route hash (not raw route in audit), total/today input and
  output tokens, snapshotted input/output rates, and operator-configured provenance; and
- exactly one `ci_minutes_today` line with explicit reported minutes.

Row-local generated columns derive model cost where applicable. Guards enforce kind-specific NULL/non-NULL
shape, component/units enums, amount/quantity bounds, model-price coverage, total/today relations, ordinals, and
unique material identity. Caller-supplied derived totals, trust, or pass flags are not columns.

### 6.5 `cost_forecast_dimension_results` — exactly six DB-reverified comparisons

One row for each ruled dimension, carrying forecast value, positive policy limit, generated/reverified
utilization percentage, strict within-limit flag, approval-trigger flag, and safe result code. Unique
`(run_id,dimension_code)` and ordinal constraints enforce exactly one of each.

The deferred run verifier re-derives all dimension values from ledger refs/input lines/policy/budget, then proves
run aggregates, reason precedence, approval and gate eligibility. Direct SQL cannot supply a cheaper forecast,
omit a component, change a rate, choose a looser limit, or forge `gate_eligible` without commit failure.

### 6.6 RLS, append-only, grants, guards, and preservation

- All five tables are tenant-owned, `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`, using the existing
  GUC-based `tenant_isolation` policy. Runtime grants are `SELECT, INSERT` only; PUBLIC gets none.
- UPDATE/DELETE/TRUNCATE block triggers apply to every table. Changed policy/input/result means a new row/run.
- Same-project composite FKs and DB guards reject cross-tenant/project candidate/core/policy/budget/event/run
  links even under direct SQL; nullable missing-evidence references are legal only for the corresponding
  failed/refused reason and can never appear on `succeeded`/gate-eligible rows.
- `cost_events` and `budgets` rows, grants, triggers, policy, semantics, and APIs are otherwise unchanged.
- `release_findings_guard()` remains completely untouched. Its catalog MD5 stays
  `808036faf2660d6810aeca4342e6f1ac`, as asserted on current main
  (`tests/test_release_verdicts.py:343-411`; `.planning/SLICE-50-PLAN.md:647-650`).
- No Slice-49/50 pack/verdict, release issue/risk/candidate, reviewer, oracle, scan, shortcut, acceptance,
  readiness, runtime, audit-chain, approval, connector, or price-card guard is replaced or weakened.

---

## 7. Proposed repository/orchestrator behavior

### 7.1 `app/repositories/cost_forecasts.py`

Proposed internal methods (names may change only by explicit reviewer/coordinator correction, not silent drift):

- `record_policy_version(*, project_id, payload, source_label, evidence_ref) -> CostForecastPolicyVersion`:
  validate exact structure, normalize, digest, insert/reselect idempotently, audit safe metadata.
- `generate_forecast(*, project_id, assumptions, price_card, as_of=None) -> CostForecastRun`:
  resolve ruled current release scope, policy, and budget; load exact ledger snapshot; compute STOP; resolve exact
  prices; validate/generate pure decision; persist attempt + exact children in one transaction; failed/refused
  attempts remain visible and never have satisfying result children.
- `latest_attempt_for_scope(...)`, `history_for_project(...)`, and
  `coverage_for_project(project_id) -> CostForecastCoverage`: tenant-scoped reads; coverage recomputes current
  candidate/core/policy/budget/ledger/input/price/date/contract digests and latest-wins state.
- `CostForecastCoverage.gate_kwargs()` exposes safe structural values only to the A5 repository.

All methods run inside caller-provided `tenant_scope`; there is no HTTP route. `generate_forecast` accepts
assumption values, never a verdict, within-policy, approval-required, trusted, complete, current, or gate-pass
field. The repository stamps all provenance/status fields and the DB re-verifies them.

### 7.2 Read-only extensions to `app/repositories/cost.py`

Only if the ruled design needs them, add read-only helpers for:

- exact event snapshot ordered deterministically;
- per-component total and UTC-day sums; and
- current material event-set digest inputs.

Do not change `record`, idempotency, audit payload, budget `upsert`, `evaluate`, `evaluate_stop`, or runtime
consumers (`app/repositories/cost.py:47-250`).

### 7.3 No action execution

Recording/evaluating a forecast does not request approval, increase a budget, change a policy, add a cost event,
pause/resume a run, select a cheaper model, deny a tool, transition a candidate, rebuild/export a pack, regenerate
a verdict, deploy, notify, or start the §23.3 loop. It records evidence and supplies gate context only.

---

## 8. A5 gate #9, readiness, and go-live — exact proposed change

### 8.1 Gate #9

- Advance `A5_RULESET_VERSION` to `slice51.v1` only after plan approval and all OD rulings.
- Keep gate number/name `9 / cost_forecast_within_policy` unchanged.
- Replace the current two-reason permanent branch with the ruled OD-51-9 ladder.
- Add repository-derived exact forecast coverage; do not accept bare `cost_policy_present`,
  `forecast_within_policy`, `approval_required`, `stop_ok`, or `passed` caller booleans as authoritative.
- A pass requires the latest current exact-binding successful run, complete child evidence, all ruled dimensions
  strictly within hard limits, no active STOP, no approval requirement, current UTC day, and DB consistency.
- A later failed/refused run, stale binding/date/digest, missing input, price gap, zero denominator, hard-limit
  reach/exceed, active STOP, or approval requirement is insufficient.
- Gate #9 becomes the tenth PASS-capable A5 gate after #1/#2/#3/#4/#5/#6/#7/#8/#11. “PASS-capable” is a code
  capability, not a claim that any current project passes (`CLAUDE.md:629-650`; inference from changing #9 only).

### 8.2 Required non-change

- Gates #1–#8 and #10–#13 are byte-identical for identical inputs; gate order remains 1..13.
- Gate #7 remains the bounded system-derived release-verdict gate; a cost forecast does not alter issue/risk
  disposition or canonical export (`app/release/production_autonomy.py:327-438`; Slice-50 current status at
  `CLAUDE.md:629-650`).
- Gate #10 and #13 remain `no_evidence_source`; gate #12 remains insufficient. Therefore A5 cannot become fully
  satisfied in this slice (`app/release/production_autonomy.py:870-887`; roadmap S52–S54 at
  `.planning/GO-LIVE-END-TO-END-ROADMAP.md:507-540`).
- `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- `NO_GO_LIVE_REASONS` remains exactly
  `('a5_gates_not_all_satisfied','request_authenticated_a5_preapproval_not_implemented')`, and
  `can_go_live_autonomously` remains literal `False`
  (`app/release/production_autonomy.py:63-66,93-110`).
- `app/runtime/engine.py`, `app/cost.py`, and `app/llm/pricing.py` remain byte-stable unless a coordinator ruling
  explicitly changes the approved scope; the recommended plan requires reads/reuse only.

Gate #9 passing is not a spend guarantee, budget authority, procurement approval, production pre-approval,
release verdict, A5 satisfaction, or go-live authorization.

---

## 9. Test plan for eventual implementation

No tests are written or run during this plan-only task. After explicit plan approval and all coordinator rulings,
implementation begins test-first and covers the following.

### 9.1 Pure / Docker-free

1. Canonical policy parser accepts exactly the actual file-21 root/fields and rejects missing/extra/renamed keys,
   bool-as-number, strings where numbers are required, unknown stop codes, malformed routing flags, negative/
   non-finite/over-scale caps, and gate-bearing zero denominators.
2. Drift tests pin the actual template percentage field and stop list while documenting—not silently merging—the
   §19.7 boolean/different-stop example.
3. Truth-tier matrix keeps policy/assumptions REPORTED, rates operator-configured, ledger DB-bound, arithmetic
   system-derived, and gate status inferred; no tier is called verified future spend.
4. Decimal formula tests for all eight component totals/today values, six dimensions, all-cost sums, token-rate
   model arithmetic, ratio scale, deterministic canonical ordering, and SHA-256 digest sensitivity.
5. Missing/duplicate/extra component, dimension, price, CI, policy, budget, history, and result cases fail closed;
   explicit zero differs from omission.
6. Price-card tests: exact route lookup; missing/negative/non-finite/over-scale/all-zero price for nonzero tokens
   refuses; no raw model route enters audit/gate context; `PRICE_CARD` remains unmodified.
7. Boundary tests: forecast `<`, `==`, and `>` every hard cap; current STOP `>=` alignment; percentage just below,
   equal, and above threshold; zero denominator never divides or passes.
8. Model-choice fixtures prove the ruled algorithm only. They must not be described as predictive accuracy,
   confidence calibration, or real-world forecast validation.
9. No-history, future-dated incurred event, daily>total assumption, empty/omitted assumption set, overflow, and
   invalid UTC-date/horizon cases follow the ruled reasons.
10. Latest-wins/currentness: new ledger event, budget value, policy, assumption, rate, contract, candidate, core,
    or UTC date changes the digest/currentness; later failed/refused supersedes older pass.
11. Active STOP matrix proves no-budget/total/daily STOP always blocks under OD-51-7 and never mutates the STOP
    decision or runtime state.
12. Gate #9 ladder tests every ruled rung and precedence; only exact current gate-eligible evidence passes;
    negative counts, inconsistent booleans, and caller truth fields fail.
13. Golden A5 regression: `slice51.v1`; only gate #9 changes for equivalent fixtures; gate #9 is the tenth
    pass-capable gate; all other gates, gate names/order, both no-go reasons, and readiness remain exact.
14. No LLM/network test: forecasting imports/calls no `LLMClient`, connector, or live price/provider adapter.

### 9.2 DB-backed and direct-SQL adversarial

1. Migration round trip `0049→0050→0049→0050`; head/model/catalog parity; only ruled Slice-51 objects and the
   additive cost-event/budget composite identity targets appear; empty downgrade succeeds and row-bearing
   downgrade fails closed.
2. RLS/grants: all five tables ENABLE+FORCE; same tenant works; cross-tenant rows are invisible/rejected;
   cross-project candidate/core/policy/budget/event/run links fail; PUBLIC has no privileges; runtime has
   SELECT/INSERT only.
3. Append-only: UPDATE/DELETE/TRUNCATE fail for policy versions, runs, event refs, input lines, and dimension
   results under runtime and admin DML paths.
4. Composite-FK attacks reject wrong tenant/project candidate, pack, policy, budget, event, or parent run; a core
   from another candidate fails.
5. Policy guard rejects unknown/extra normalized codes, zero/negative caps, percentage out of range, count/list
   mismatch, whitespace-only labels, caller-forged source provenance, and material digest mismatch.
6. Exact ledger-set guard rejects missing/extra/duplicate/wrong-project refs, event field mismatch, changed
   amount/component/time snapshot, ordinal gaps, future-dated events, forged ledger digest/count, and cap overflow.
7. Input guard rejects omission/duplication of any component, direct model projected-dollar injection, missing
   rate for planned tokens, price/token/CI/amount shape violations, daily>total, unknown units, and caller trust/
   pass/current fields.
8. Dimension/result guard rejects missing/extra/duplicate result, looser limit than policy/budget, forged forecast
   value/ratio/within/approval/gate flag, incorrect reason precedence, and succeeded-with-incomplete-child set.
9. Concurrency snapshot test: a forecast transaction has a deterministic exact ledger snapshot; a concurrent
   later cost insert cannot corrupt stored history and de-currents the forecast on the next coverage read.
10. Latest-wins uses `(created_at DESC,id DESC)`; a later failed/refused attempt blocks an older pass; same-
    timestamp ordering is deterministic.
11. UTC tests cover half-open day boundaries and day rollover without session-timezone dependence. Yesterday’s
    daily result cannot satisfy today’s gate.
12. STOP integration proves the current repository recomputes STOP and blocks a previously passing forecast after
    new spend or a budget decrease; it never writes `run_steps`, changes run state, or resumes a paused run.
13. Existing cost-ledger regression: amount/component/idempotency/over-budget recording, budget upsert/audit,
    total/daily sums, RLS, immutability, and Slice-8b pause/resume tests remain unchanged and green.
14. Findings guard pin across upgrade, downgrade, re-upgrade:
    `md5(pg_get_functiondef('release_findings_guard()'::regprocedure)) ==
    '808036faf2660d6810aeca4342e6f1ac'`; rerun Slice-23/44/45 direct-SQL attacks.
15. Audit sentinel injects cost description/external ref, policy source/evidence labels, raw YAML-like strings,
    model IDs, assumption values, URLs, token-like strings, provider payload text, and secrets into permitted
    upstream fields and proves forecast audit contains only the ruled safe metadata.
16. Production-autonomy repository loads only current tenant-scoped coverage, changes gate #9 only, exposes no
    raw monetary assumptions/model IDs/prose, and leaks no cross-tenant existence.
17. API golden regression: existing `/cost` and `/production_autonomy` routes remain read-only; no forecast write
    or export endpoint appears; GET does not generate/persist a forecast.

### 9.3 Verification commands for eventual implementation only

After approval/rulings and implementation: `git diff --check`; Ruff; focused pure/DB tests; `make test`;
`make test-db`; migration `0049→0050→0049→0050`; CI. Every suite claim must include the captured process exit
code and complete terminal summary; truncated output is a failed verification. These are future requirements,
not authorization to run them now.

---

## 10. Proposed file touch map for eventual implementation only

- Add pure forecast/policy module: `app/cost_forecast.py`.
- Add ruled models, likely:
  - `app/models/cost_forecast_policy.py`;
  - `app/models/cost_forecast_run.py`;
  - `app/models/cost_forecast_ledger_event_ref.py`;
  - `app/models/cost_forecast_input_line.py`;
  - `app/models/cost_forecast_dimension_result.py`;
  - model registration imports only as required.
- Add tenant repository/orchestrator: `app/repositories/cost_forecasts.py`.
- Extend `app/repositories/cost.py` with read-only exact snapshot/component aggregate helpers only if required.
- Modify gate #9 only in `app/release/production_autonomy.py` and
  `app/repositories/production_autonomy.py`.
- Add expected `migrations/versions/0050_cost_forecasts.py` and focused
  `tests/test_cost_forecasts.py`; extend existing cost/runtime/A5/API golden tests only where integration requires.
- Do not modify `app/cost.py`, `app/runtime/engine.py`, `app/llm/pricing.py`,
  `app/intake/readiness.py`, the canonical template/schema assets, evidence-pack/release-verdict sources,
  approvals, connectors, or gates other than #9 under the recommended rulings.
- Do not create a branch, code, migration, test, commit, or PR until this plan is approved and all ODs are ruled.
  This plan file is the sole deliverable now.

---

## 11. Must NOT claim

- Must NOT claim any forecast is a fact, verified future spend, provider quote, invoice, procurement commitment,
  confidence interval, accuracy measurement, or guarantee.
- Must NOT claim recorded ledger rows prove every incurred external cost was captured, or that one/zero rows prove
  complete/zero spend.
- Must NOT claim an explicit zero remaining-work assumption proves no work or cost remains.
- Must NOT call caller-supplied policy/assumption/source/actor labels verified owner, finance, procurement, human,
  or approval authority.
- Must NOT call operator-configured price-card values provider-verified prices or modify the price card.
- Must NOT infer CI minutes/tokens/model route/task identity from generic `cost_events.quantity`, `description`,
  `source_system`, or `external_ref`.
- Must NOT conflate the all-cost `budgets` row with the canonical model/cloud/CI policy fields.
- Must NOT silently resolve the §19.7 boolean versus file-21 percentage/stop-list drift.
- Must NOT divide by zero, treat missing/NULL/zero limits as unlimited, or pass on absent policy, budget, history,
  price, assumption, CI, result, candidate, or core evidence.
- Must NOT let a hard-cap equality pass when Slice-7 STOP semantics are `>=`.
- Must NOT let an approval-required forecast pass without the exact coordinator-ruled eligible authority path;
  under the recommended plan no approval path exists this slice.
- Must NOT let an older passed forecast outrank a newer failed/refused/current-input-mismatched forecast.
- Must NOT reuse yesterday’s daily forecast for today or invent an extra TTL absent a ruled policy source.
- Must NOT let a forecast clear/suppress STOP, unpause a run, raise a budget, revise policy, record incurred cost,
  reroute a model, approve, transition a release, regenerate/export a pack, deploy, or notify.
- Must NOT claim gate #9 passing means all cost policy is enforced; routing booleans/non-budget stop conditions are
  diagnostic unless explicitly ruled and implemented.
- Must NOT claim a gate-#9 pass means A5 satisfied, release verdict passed, production pre-approved, rollback
  verified, emergency authority present, deployment allowed, or go-live authorized.
- Must NOT flatten REPORTED, operator-configured, DB-proven, system-derived, and gate-inferred truth tiers.
- Must NOT store or audit raw YAML, free-form assumption/policy prose, model prompts/responses, raw model IDs in
  gate/audit context, cost descriptions/external refs, URLs, provider payloads, credentials, tokens, or secrets.
- Must NOT weaken the cost ledger, runtime STOP path, release/evidence/verdict objects, approval system, any RLS/
  FK/append-only/generated/guard invariant, or `release_findings_guard()` MD5 pin.
- Must NOT change readiness; it remains byte-stable at `slice20.v1`.
- Must NOT alter either hard no-go reason. Go-live remains hard-false regardless of gate #9.
- Must NOT start implementation until explicit reviewer APPROVE and coordinator rulings OD-51-1…9.

---

## 12. Definition of done for eventual implementation — not this plan-only task

After explicit plan approval and all coordinator rulings:

1. the rulings are copied verbatim into this plan before implementation;
2. the exact canonical policy shape and every spec/template drift are versioned, explicit, and tested without
   changing the checked-in template;
3. every forecast preserves truth tiers, uses deterministic Decimal arithmetic, and is labelled as a bounded
   system-derived projection rather than future truth;
4. policy, budget, ledger, assumptions, price, release scope, UTC date, and contracts are exact-bound and
   reproducibly digested; missing/zero/inconsistent evidence fails closed;
5. DB guards make child membership, arithmetic, result flags, approval/STOP status, and gate eligibility
   non-fakeable under direct SQL;
6. later failures/refusals and every ruled input/date change de-current older passes; history remains immutable;
7. the Slice-7 incurred ledger and Slice-8b STOP→pause semantics remain unchanged and regression-proven;
8. gate #9 alone gains the ruled pass branch under `slice51.v1`; all other gates are regression-identical;
9. readiness stays `slice20.v1`; both no-go reasons stay exact; go-live remains false;
10. migration `0050` is additive, RLS ENABLE+FORCE, append-only, composite-FK-bound, round-trips, refuses
    row-bearing downgrade, and preserves every prior guard including the findings MD5 pin;
11. audit/gate context is safe-metadata-only and all sentinel/cross-tenant/direct-SQL attacks fail;
12. no rollback, production approval, emergency stop, control loop, evidence-pack mutation, HTTP, LLM, network,
    provider billing, phase-budget, or deployment scope is added; and
13. `git diff --check`, Ruff, full pure suite, full DB suite, migration round trip, and CI are green with complete
    output and captured exit codes presented for independent review.

For this plan-only task, definition of done is only: this single sourced file exists, every genuine design choice
is exposed as an OD, the muhasabah audit passes, and work stops for reviewer APPROVE/REJECT.

## Reviewer gate

**Reviewer request:** APPROVE or REJECT this plan-only design. On APPROVE, the coordinator must rule OD-51-1
through OD-51-9 before implementation. Until both gates are satisfied: no branch, code, migration, tests,
commit, or PR.
