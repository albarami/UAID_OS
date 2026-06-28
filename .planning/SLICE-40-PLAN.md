# Slice 40 — Agent qualification eval (the `unqualified→qualified` transition) — PLAN v3

**Status:** AWAITING PLAN REVIEW (v1+v2 REJECTED; v3 **adds B7 run-scoped sign-off**; OD-1…6 + B1–B6 settled) — **plan-only; no branch / no code / no migration / no tests / no PR.**

> **Revision log — v2 → v3 (B7 — sign-off bound to the EXACT run):**
> - **B7 — QA/Security approvals are RUN-scoped, not realization-scoped.** §9.4 runs dry tests THEN sends the spec for sign-off, so each sign-off must bind the **exact** qualification run it reviewed. `ApprovalRepository.latest_for` filters by `(action, subject_ref)` only — so a realization-scoped subject would let an approval for run A satisfy run B (or a *pre-run* approval satisfy a later run). v3 puts `run_id` in the subject ref (`agent_realization:<id>:qualification_run:<run_id>:{qa,security}`), changes the opener to `request_qualification_approvals(*, realization_id, run_id, requested_by)`, and `qualify(realization_id, run_id, …)` requires both approvals **for that exact run_id**. Run-binding tests added. **All v2 fixes (OD-1…6, B1–B6) stand unchurned.**
>
> **Revision log — v1 → v2 (OD-1…6 ruled + B1–B6):**
> - **OD rulings (bound):** OD-1 keep **per-case FK children with deferred DB count/aggregate/verdict backstops**; OD-2 require **passing run AND reviewer approvals**; OD-3 **TWO distinct approvals — QA + Platform Security**; OD-4 **migration-seed** the global controlled library v1 (admin-only new versions later); OD-5 **per-realization**; OD-6 **one Slice 40**, deterministic only (no LLM / no harness / no A5-readiness change).
> - **B1 — eval library fully modeled:** `archetype_evals` now carries the full §9.5.1 shape (representative tasks / gold-oracle source / scoring rubric / threshold / refresh policy) **+ per-category coverage requirements** (positive/negative/edge/adversarial/incomplete); the **exact 11 seeded rows** are specified (§5.1).
> - **B2 — archetype enum drift resolved:** DB/runtime use **`registry.ARCHETYPES`** values (incl. **`ai_evaluation`**); the schema's `ai_evaluator` is documented as the doc-side label that maps to runtime `ai_evaluation`.
> - **B3 — verdict is now genuinely DB-derived:** the run's `total_cases`/`passed_cases`/`critical_failure_count`/`coverage_complete` are **deferred-trigger-verified against the FK child rows** (caller can't fake them), and `aggregate_score` + `verdict` are **`GENERATED ALWAYS … STORED`** (caller cannot write them). Direct-SQL fake-verdict tests required.
> - **B4 — two distinct sign-offs:** exact action strings / subject refs / risk_tier / payload bound (§6); tests for missing + wrong-subject.
> - **B5 — scope de-overclaimed:** Slice 40 = the **controlled archetype eval library** (the platform half of §9.5) + a **recorded dry-test evidence gate** (§9.4 step 6, evidence-recorded NOT live) + **QA+Security sign-off** (§9.4 step 7) + the transition. **Project-specific eval-case GENERATION (§9.4 step 5) and LIVE dry tests are explicitly deferred** (no agent execution).
> - **B6 — broker wording fixed:** qualified ⇒ the agent path passes the **qualification gate** and **reaches** allowlist/policy/approval (which still decide); only a **controlled allowlisted + policy-permissive** test shows it can then reach `ALLOWED_UNVERIFIED_IDENTITY`.

> **Persona.** Senior agent-platform / evaluation-systems backend architect (Sanad + security-reviewer hats).
> **Provenance (Sanad — spec + verified recon):** §9.4 steps 6–7 (`spec:876-889`); §9.5/§9.5.1 controlled methodology + per-archetype thresholds + positive/negative/edge/adversarial/incomplete coverage (`spec:891-930`); schemas `archetype_eval_methodology.yaml` / `reviewer_quality_assurance.yaml`. Reuse: `agent_realizations` (Slice 39 — `0038` INSERT-locks `unqualified`, append-only block trigger, SELECT/INSERT-only grant); `broker.py:179` (agent path denies unless `qualification_status=='qualified'` — **no broker change**); `registry.ARCHETYPES` (11, incl. `ai_evaluation`; archetype = `instance→version→blueprint.archetype`); Slice-4 approval engine; Slice-37 deferred count triggers; Slice-22 column-mutability guard. Migration head **0038 ⇒ 0039**.

---

## 0. The defining honesty constraint (the crux)
**Agent EXECUTION does not exist** (broker grants no execution; success caps at `ALLOWED_UNVERIFIED_IDENTITY`; Slice-27 approval unwired). So Slice 40 **cannot run a live agent**. Therefore:
- A **qualification run** scores **recorded** dry-test results; the run's counts + coverage are **DB-verified against FK child cases**, and `aggregate_score`/`verdict` are **DB-generated** — a `passed` verdict **cannot be faked** (it requires real child rows meeting threshold + zero-critical + required category coverage).
- Eval-result **provenance is `caller_supplied_unverified`** — a real eval harness / live agent run, and §9.4-step-5 **project-specific case generation**, are LATER slices.
- The one-way `unqualified→qualified` transition fires **only** on a **passing run** + **TWO distinct sign-offs (QA + Platform Security)** (§9.4 step 7 / §2.2).
- **Qualifying lets the agent path PASS the *qualification gate* and REACH allowlist/policy/approval (which still decide) — it unlocks NO execution.**

## 1. Scope & non-goals
- **Scope.** (A) A **global, migration-seeded, controlled archetype eval library** (`archetype_evals`) — the full §9.5.1 shape + category-coverage requirements (the platform half of §9.5; `uaid_app` SELECT-only — Slice-38 trust-zone). (B) A tenant-owned, **immutable** `qualification_runs` + FK-proven `qualification_case_results`, with **DB-verified counts/coverage** and **DB-generated `aggregate_score`/`verdict`**. (C) The guarded `unqualified→qualified` **transition** on `agent_realizations` (migration `0039`). (D) Pure scorer + repo + a controlled **broker-reaches-downstream** test. (E) `app/agents/qualification.py` + `app/repositories/qualification.py`.
- **Non-goals (explicit per B5/OD-6).** **NO §9.4-step-5 project-specific case generation; NO LIVE dry tests / agent execution / eval harness; NO LLM; NO §9.6 replacement; NO model routing; NO A5 / readiness / go-live change; NO broker signature change; NO execution unlocked** (success stays `ALLOWED_UNVERIFIED_IDENTITY`).

## 2. The honesty model in one line
Slice 40 builds the controlled archetype eval **library** + a **DB-non-fakeable** recorded-evidence qualification gate + a two-sign-off one-way transition, making the broker agent path **reach** its downstream gates; eval inputs are **unverified** and qualifying **unlocks no execution**.

## 3. BOUND decisions
- **D-40-1 — Deterministic, no LLM / no agent run / no cost.** Scores recorded cases only.
- **D-40-2 — Verdict + aggregate are DB-GENERATED; counts + coverage are DB-VERIFIED from children (B3/OD-1).** Caller writes neither `aggregate_score` nor `verdict`; a deferred trigger rejects any run whose `total_cases`/`passed_cases`/`critical_failure_count`/`coverage_complete` ≠ the FK children.
- **D-40-3 — Archetype = `registry.ARCHETYPES` runtime values incl. `ai_evaluation` (B2)**; resolved `instance→version→blueprint`, snapshotted with the threshold/coverage onto the run.
- **D-40-4 — One-way transition, DB-backstopped.** `0039` `CREATE OR REPLACE`s the `0038` block trigger to allow ONLY `qualification_status` `unqualified→qualified` (+ `updated_at`/`qualified_via_run_id`); the guard **requires a PASSING run** for the realization; column-level `GRANT UPDATE(qualification_status, updated_at, qualified_via_run_id)`. All else stays blocked.
- **D-40-5 — TWO distinct RUN-SCOPED sign-offs (QA + Security) + passing run (B4/B7/OD-2/OD-3).** `qualify` requires both approvals APPROVED **for the exact run_id** (run-scoped subject refs — an approval for one run can never satisfy another) **and** a passing run.
- **D-40-6 — Library global + SELECT-only + migration-seeded (OD-4/trust-zone).**
- **D-40-7 — Store/infra-only; bit-stable.** `production_autonomy.py`/`readiness.py` UNTOUCHED; audit safe-metadata only; go-live false.

## 4. Pure — `app/agents/qualification.py`
- `QUALIFICATION_ARCHETYPES` (= `registry.ARCHETYPES`), `CASE_CATEGORIES=('positive','negative','edge','adversarial','incomplete')`, `VERDICTS=('passed','failed')`.
- `derive_counts(cases) -> (total, passed, critical_failure_count, categories_present)` — `critical_failure = is_critical AND NOT passed`; mirrors the DB trigger exactly (single source of the formula).
- `coverage_complete(categories_present, required_categories) -> bool`.
- `expected_verdict(*, total, passed, critical_failure_count, coverage_complete, min_cases, min_aggregate_score, require_zero_critical) -> verdict` — mirrors the DB GENERATED expression (for tests).
- `validate_case_results(cases)` (bounded `case_ref`, category∈enum, real bools, fail-closed).

## 5. Storage + migration `0039`

### 5.1 `archetype_evals` (GLOBAL, SELECT-only for `uaid_app`; migration-seeded; immutable append-only — new versions = new rows, never UPDATE)
Columns: `id`/`archetype`(CHECK∈`ARCHETYPES`)/`eval_version`/`representative_task_set`(JSONB array)/`gold_answer_source`(JSONB array)/`scoring_rubric`(JSONB array)/`min_aggregate_score`(NUMERIC(4,3) 0..1)/`require_zero_critical`(bool)/`min_cases`(int ≥1)/`required_categories`(JSONB array ⊆ CASE_CATEGORIES)/`refresh_policy`(text)/`created_at`; `UNIQUE(archetype,eval_version)`; bounded-JSON CHECKs.
**Exact 11 seeded rows (`eval_version='v1'`, `require_zero_critical=true`, `required_categories=[all 5]`, `min_cases=5`)** — task/gold/rubric verbatim-condensed from §9.5.1, thresholds:

| archetype | min_aggregate_score | refresh_policy |
|---|---|---|
| builder | 0.850 | quarterly + after major model/framework/tool change |
| reviewer | 0.900 | monthly + after reviewer-miss incident |
| security_reviewer | 0.850 | monthly + when threat library changes |
| data_engineer | 0.850 | quarterly + after data-stack change |
| domain_reasoner | 0.850 | per domain-pack release |
| prompt_engineer | 0.850 | monthly + after prompt-template change |
| knowledge_graph_rag | 0.850 | per corpus/domain refresh |
| ai_evaluation | 0.850 | quarterly + after model-family change |
| integration_connector | 0.850 | per connector/API version change |
| deployment_sre | 0.850 | monthly + after runtime/cloud change |
| evidence_auditor | 0.950 | monthly + after evidence-schema change |

(Each row's `representative_task_set`/`gold_answer_source`/`scoring_rubric` are the §9.5.1 row text. `ai_evaluation` = the schema's `ai_evaluator`.)

### 5.2 `qualification_runs` (TENANT, RLS ENABLE+FORCE; SELECT/INSERT only)
`id`/`tenant_id`/`project_id`/`realization_id`/`archetype_eval_id`(FK→`archetype_evals`) + **snapshots** `archetype`/`eval_version`/`min_aggregate_score`/`require_zero_critical`/`min_cases`/`required_categories` + **caller-provided, trigger-verified** `total_cases`/`passed_cases`/`critical_failure_count`/`coverage_complete`(bool) + **GENERATED** `aggregate_score NUMERIC GENERATED ALWAYS AS (passed_cases::numeric/NULLIF(total_cases,0)) STORED` and `verdict text GENERATED ALWAYS AS (CASE WHEN total_cases>=min_cases AND passed_cases::numeric/NULLIF(total_cases,0)>=min_aggregate_score AND (NOT require_zero_critical OR critical_failure_count=0) AND coverage_complete THEN 'passed' ELSE 'failed' END) STORED` + `provenance`(`caller_supplied_unverified`)/`evaluated_by`/`created_at`. **composite FK** `(realization_id,project_id,tenant_id)→agent_realizations`; `UNIQUE(id,project_id,tenant_id)` (the realization FK target); `passed_cases≤total_cases`, counts ≥0 CHECKs. **A DEFERRABLE INITIALLY DEFERRED constraint trigger (run-side + child-side, Slice-37 pattern) recomputes `total_cases`/`passed_cases`/`critical_failure_count`/`coverage_complete` from the children and REJECTS any mismatch** (so the GENERATED verdict is non-fakeable).

### 5.3 `qualification_case_results` (TENANT, RLS, SELECT/INSERT only)
`id`/`tenant_id`/`project_id`/`run_id`(composite FK→`qualification_runs`)/`case_ref`/`case_category`(CHECK∈CASE_CATEGORIES)/`passed`(bool)/`is_critical`(bool)/`created_at`. Feeds the §5.2 deferred verify trigger.

### 5.4 `agent_realizations` (migration `0039`)
ADD `updated_at`(nullable) + `qualified_via_run_id`(UUID nullable, composite FK→`qualification_runs`); **CREATE OR REPLACE** the `0038` block trigger → allow the one-way qualification UPDATE (D-40-4) only, with the **passing-run backstop** (`qualified_via_run_id` must reference a `verdict='passed'` run for THIS realization/tenant); `GRANT UPDATE(qualification_status, updated_at, qualified_via_run_id) ON agent_realizations TO uaid_app`.

## 6. Repository — `app/repositories/qualification.py`
- `record_qualification_run(*, realization_id, cases, evaluated_by)` — resolve archetype (`instance→version→blueprint`) + `archetype_evals` row → `validate_case_results` → `derive_counts` → INSERT run (snapshots + the derived counts/coverage) + child cases in one txn (the deferred trigger re-verifies at commit) → audit safe-metadata (archetype/threshold/aggregate/verdict/counts — never `case_ref`/prose).
- **Two RUN-SCOPED approvals (B4/B7/D-40-5)** via Slice-4 `ApprovalRepository.request` (`requires_explicit_approval=True`, `risk_tier='high'`) — the subject ref binds the **exact `run_id`**, so an approval for run A can never satisfy run B, nor can a pre-run approval satisfy a later run:
  - QA: `action='qualify_agent_qa'`, `subject_ref='agent_realization:<id>:qualification_run:<run_id>:qa'`.
  - Security: `action='qualify_agent_security'`, `subject_ref='agent_realization:<id>:qualification_run:<run_id>:security'`.
  - `request_qualification_approvals(*, realization_id, run_id, requested_by)` opens both for that run (idempotent); payload safe-metadata only (`realization_id`, `run_id`, `archetype` — never case prose).
- `qualify(*, realization_id, run_id, qualified_by)` — requires a **passing** `run_id` for the realization **AND both** approvals `APPROVED` **for that exact `run_id`** (run-scoped subject; wrong-run/wrong-subject/missing ⇒ refuse) → UPDATE the realization to `qualified` (+ `qualified_via_run_id`, `updated_at`); audited. Reads `runs_for`/`latest_run`/`is_qualified`.

## 7. Broker — NO change (the *reach*, not an unlock)
`broker.py` untouched. A controlled test: a qualified realization **+ an allowlist grant for its instance + a policy-permissive project** ⇒ `broker_call` (agent path) passes the qualification gate, reaches allowlist→policy→approval, and returns `ALLOWED_UNVERIFIED_IDENTITY`; without the allowlist grant ⇒ `DENIED_NOT_ALLOWLISTED` (proving the downstream gates still decide); an `unqualified` realization ⇒ `DENIED_UNQUALIFIED_AGENT` (regression).

## 8. A5 / readiness / tenancy / audit
**A5/readiness: NONE — bit-stable** (`before==after`). Both tenant tables RLS ENABLE+FORCE + `tenant_isolation`; `archetype_evals` global SELECT-only. Composite FKs pin project/tenant. Audit safe-metadata only. Go-live false.

## 9. Tests
- **Pure:** `derive_counts` (critical_failure = critical∧¬passed), `coverage_complete`, `expected_verdict` (threshold edge, zero-critical, sub-min, missing-category ⇒ failed); `QUALIFICATION_ARCHETYPES == registry.ARCHETYPES`.
- **DB — library:** the **11 seeded rows** present with the right thresholds + `required_categories`; `uaid_app` SELECT-only (INSERT/UPDATE privilege-denied); append-only.
- **DB — runs (B3 fake-verdict, direct-SQL):** a real passing + failing run; **caller cannot write `verdict`/`aggregate_score`** (generated-column error); **deferred trigger REJECTS** a run whose claimed `passed_cases`/`critical_failure_count`/`coverage_complete` ≠ the children; coverage-incomplete ⇒ `verdict='failed'`; RLS cross-tenant; append-only; composite-FK cross-project/tenant refused.
- **DB — transition:** `qualify` flips `unqualified→qualified` on a passing run + **both** approvals; **refused** with only one approval, wrong-subject approval, **an approval bound to a DIFFERENT run (run A's approval can't qualify run B; a pre-run / realization-scoped approval can't satisfy a later run — B7)**, no passing run (guard backstop), a failing run, and on `qualified→unqualified`/same-status/other-column UPDATE; `uaid_app` UPDATE limited to the 3 columns.
- **DB — broker reach (B6):** qualified + allowlisted + permissive ⇒ `ALLOWED_UNVERIFIED_IDENTITY`; qualified + NOT allowlisted ⇒ `DENIED_NOT_ALLOWLISTED`; unqualified ⇒ `DENIED_UNQUALIFIED_AGENT`.
- **No-A5/readiness:** `before==after` after `qualify`.
- `make test` + fresh `make test-db` + alembic `0039` round-trip; CI green.

## 10. Must NOT claim
- That qualification is **execution-proven** or a **live dry test** (recorded evidence, `caller_supplied_unverified`; no agent ran; §9.4-step-5 generation + live tests deferred — B5).
- That qualifying **unlocks execution** or returns `ALLOWED` by itself (it lets the agent path **reach** allowlist/policy/approval, which still decide; success only in a controlled permissive setup — B6).
- That the library is **project-specific/LLM-generated** (controlled global archetype asset only).
- That **A5 / readiness / go-live** changed (not an Appendix-B gate; bit-stable).

## 11. RESOLVED decisions (formerly open)
OD-1 FK children + deferred DB verify (D-40-2/§5.2-5.3); OD-2 run **and** approvals (D-40-5); OD-3 **two** RUN-SCOPED approvals QA+Security (§6, B7); OD-4 migration-seed global SELECT-only (D-40-6/§5.1); OD-5 per-realization (§5.2 `realization_id`); OD-6 one slice, deterministic (D-40-1, §1 non-goals).

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A migration-seeded global archetype eval library (11 rows, full §9.5.1 shape + coverage reqs, SELECT-only) + an immutable tenant `qualification_runs`/`qualification_case_results` whose counts/coverage are **deferred-trigger-verified from the children** and whose `aggregate_score`/`verdict` are **GENERATED** (a fake `passed` is DB-rejected) + a one-way `unqualified→qualified` transition (migration `0039`, passing-run backstop + column-level grant) gated on a passing run **and two distinct (QA+Security) APPROVED approvals**; the broker agent path now **reaches** its downstream gates for a qualified agent (no broker change) — **no execution unlocked**; provenance `caller_supplied_unverified`; `production_autonomy.py`/`readiness.py` untouched, **bit-stable**, go-live false; `0039` round-trips; `make test` + `make test-db` + CI green. **No LLM, no agent run, no case generation, no live dry tests, no A5 flip.**

---
**Review note (v3):** Adds **B7** — QA/Security sign-offs are **run-scoped** (`…:qualification_run:<run_id>:{qa,security}`), so an approval binds the exact run it reviewed (no cross-run / pre-run reuse); `request_qualification_approvals(realization_id, run_id, …)` + `qualify` gates on both approvals for that `run_id`; run-binding tests added. **All v2 fixes stand.** v2 fixed **B1** (full §9.5.1 library shape + 11 exact seeds + category coverage), **B2** (`ai_evaluation` runtime value), **B3** (counts/coverage **deferred-trigger-verified from FK children**; `aggregate_score`/`verdict` **GENERATED** — non-fakeable, with direct-SQL tests), **B4** (two distinct QA+Security approvals — exact actions/subjects/tier/payload), **B5** (scope honestly = library + recorded-evidence gate + transition; step-5 generation + live tests deferred), **B6** (qualified **reaches** downstream gates; `ALLOWED` only under a controlled permissive test). All 6 ODs ruled. Deterministic, store/infra-only, bit-stable, migration `0039`. **No code/migration/tests/PR until an approved plan + your explicit go.**
