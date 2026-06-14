# Slice 20 — R5 readiness / gated-engine completeness (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice20-r5-readiness` off `main` @ `f28211f`; category partition 3/22/2, migration
`0020` (CHECK 20→22), R5 evaluator + repository engine gates, tests, docs. Verification:
`ruff` clean, `make test` 189, `make test-db` 250.
**Base:** `main` @ `f28211f` (clean).
**Rulings:** `.planning/SLICE-20-R5-DISCUSSION.md` (D-R5-1..8 all ruled).

---

## 0. One-line summary

Lift the auditor cap **R4 → R5** as deterministic **intake-package completeness**: R4 base + all
remaining declarable intake categories declared + the two engine gates present (autonomy policy row,
positive budget) + the two newly-declarable presence-only gates (human approval policy, production
authority). **`can_go_live_autonomously` stays hard-false** (A5/Appendix-B is a separate slice).
One narrow additive migration; no LLM; no new engine.

---

## 1. R5 rule (per rulings)

`level` becomes `"R5"` iff **all** hold (fail-closed; any miss ⇒ stays R4):
1. **R4 base** holds (R3 trio + R4 tools declared + zero spine gaps).
2. **All remaining declarable categories declared** (D-R5-2) — every category in the expanded
   `DECLARABLE_INTAKE_CATEGORIES` (22, see §2) not already consumed by R3/R4, status `declared`,
   D-6 stale-source exclusion applied. Includes `environments_and_deployment_targets`,
   `secrets_and_credentials_manifest` (**reference-only**, never values — already enforced by
   `categories.py`), `go_live_checklist`, `risk_register_and_assurance_requirements`, and the two
   new presence-only gates `human_approval_policy` + `production_authority`.
3. **Autonomy policy gate** (D-R5-3): `autonomy_policy_present` = a project-scoped
   `autonomy_policies` row **exists** AND `validate_overrides(policy.overrides)` **succeeds**
   (raises nothing). **Do NOT infer this from `decision_for("deploy_production")`** — a valid
   low-level policy can legitimately return DENY for deploy_production while still being a
   present/valid autonomy policy. `decision_for("deploy_production")` remains **transparency-only**
   for the report (`production_authority_decision`); it never gates R5.
4. **Cost policy gate** (D-R5-4): `BudgetRepository.get(project_id)` returns a budget with
   `max_total_cost_usd > 0`.

`can_go_live_autonomously` remains **false** at R5 (D-R5-1) — go-live needs A5/Appendix-B, not
evaluated here.

## 2. Category partition change (D-R5-5, D-R5-6)

In `app/intake/categories.py`, move `human_approval_policy` and `production_authority` from
`GATED_ENGINE_CATEGORIES` into `DECLARABLE_INTAKE_CATEGORIES`:
- `SPINE_CATEGORIES` = 3 (unchanged).
- `GATED_ENGINE_CATEGORIES` = **2** (`autonomy_policy`, `cost_and_resource_policy`) — still read
  from their engines (`autonomy_policies`, `budgets`), **not** declarable.
- `DECLARABLE_INTAKE_CATEGORIES` = **22** (was 20).
- `CANONICAL_READINESS_CATEGORY_UNIVERSE` = 27 (unchanged; partition stays disjoint + complete —
  the module's partition assertions must still pass).

These two new declarations are **presence-only, non-authorizing** — they never flip go-live and do
not build any engine.

## 3. Migration (D-R5-8 — narrow, additive)

New `migrations/versions/0020_*.py`: expand the `intake_categories` category CHECK
(`ck_intake_categories_category_valid`) from the 20-set to the 22-set (add `human_approval_policy`,
`production_authority`). Drop+recreate the named CHECK; downgrade restores the 20-set. **No new
table, no new column, no new grant, no engine.** This is the only schema change.

## 4. Evaluator + repository changes

- **`app/intake/readiness.py` (pure):** add `R5_*` constants (`READINESS_CAP="R5"`,
  `RULESET_VERSION="slice20.v1"`, the R5 category list, new go-live reasons per D-R5-7). Extend
  `evaluate_readiness(...)` with fail-closed gate inputs: `autonomy_policy_present: bool = False`,
  `cost_policy_ok: bool = False` (defaults false ⇒ callers that don't pass them can't reach R5).
  Add the R5 lift after the R4 block. Update `_CONSUMED_CATEGORIES` to include the R5-consumed
  categories + the two engine-gate categories so `NOT_ASSESSED_CATEGORIES` becomes empty at the
  universe level (the module partition assertion updates accordingly).
- **`app/repositories/readiness.py`:** in `evaluate`, additionally read the two engine gates and
  pass booleans into `evaluate_readiness`:
  - `autonomy_policy_present` = `AutonomyPolicyRepository.get_for_project(pid)` is not None **and**
    `validate_overrides(policy.overrides)` succeeds (raises nothing). **Not** derived from
    `decision_for("deploy_production")` — that stays transparency-only for the report.
  - `cost_policy_ok` = `BudgetRepository.get(pid)` is not None **and** `max_total_cost_usd > 0`.
  The two new declarable categories flow through the existing generic `_category_declarations`
  (D-6 stale-source exclusion already covers them — no special-casing).
- **Report shape (D-R5-7):** add `missing_r5_categories` (declarable R5 categories not declared) and
  `missing_r5_gates` (e.g. `autonomy_policy_absent_or_invalid`, `cost_budget_absent_or_zero`);
  `readiness_cap → "R5"`; `ruleset_version → "slice20.v1"`. Replace the stale
  `readiness_capped_below_R5` go-live reason with an **Appendix-B/A5-not-evaluated** reason (e.g.
  `a5_production_autonomy_appendix_b_not_evaluated`) plus a note that production_authority is
  presence-only, not authorization. Extend `missing_for_go_live` with
  `r5_category_not_declared:<c>` and `r5_gate_incomplete:<gate>` entries (mirrors r3/r4 pattern).

## 5. Tests first (TDD) — exact scenarios (coordinator list)

Docker-free in `tests/test_readiness.py` (pure evaluator) + DB-backed where engine/migration state
is needed; category-declarability in `tests/test_intake_categories.py`:

1. **`test_r5_when_all_gates_present`** — R4 base + all R5 categories declared + autonomy row +
   budget>0 ⇒ `readiness_level == "R5"`; `missing_r5_categories == []`; `missing_r5_gates == []`.
2. **`test_r5_missing_each_category_stays_r4`** (parametrized over the R5 declarable categories) —
   omit one ⇒ stays `"R4"`; that category in `missing_r5_categories`.
3. **`test_r5_missing_human_approval_policy_declaration_no_r5`** — explicit per D-R5-5.
4. **`test_r5_missing_production_authority_declaration_no_r5`** — explicit per D-R5-6.
5. **`test_r5_autonomy_policy_absent_or_invalid_no_r5`** — no autonomy row (and: invalid overrides)
   ⇒ stays R4; `autonomy_policy_absent_or_invalid` in `missing_r5_gates`.
6. **`test_r5_budget_absent_or_zero_no_r5`** — no budget / `max_total_cost_usd == 0` ⇒ stays R4;
   `cost_budget_absent_or_zero` in `missing_r5_gates`.
7. **`test_r5_reached_go_live_still_false`** — at R5, `can_go_live_autonomously is False`; go-live
   reasons reference A5/Appendix-B not-evaluated, **not** "capped below R5".
8. **`test_r5_secrets_reference_only`** — `secrets_and_credentials_manifest` declared with reference
   metadata satisfies R5; inline secret values are still rejected at declaration (existing guard).
9. **Migration/validation** (`test_intake_categories.py`): `human_approval_policy` and
   `production_authority` are now **accepted** declarations (app validator + DB CHECK); a bogus/
   non-declarable category is still **rejected** (app + DB). DB-backed declare round-trip for the two
   new categories.

**Explicit DB-backed repository tests** (`tests/test_readiness.py`, `@pytest.mark.db`) — proving
`ReadinessRepository.evaluate` reads the **actual** `autonomy_policies` and `budgets` rows (not just
the pure engine with hand-passed booleans):
- **`test_db_r5_persists_when_all_categories_and_engine_gates_present`** — seed full spine + declare
  every R5 category + upsert a valid autonomy policy row + a budget with `max_total_cost_usd > 0`
  ⇒ `evaluate`/`evaluate_and_record` returns **R5**; row persists R5 (the 0015 CHECK allows R5).
- **`test_db_r5_missing_autonomy_row_no_r5`** — same but **no** `autonomy_policies` row ⇒ stays R4;
  `autonomy_policy_absent_or_invalid` in `missing_r5_gates`.
- **`test_db_r5_invalid_autonomy_overrides_no_r5`** — autonomy row present but with **invalid
  persisted overrides** (so `validate_overrides` raises) ⇒ stays R4; same gate flagged. Proves the
  gate is validity, not mere row existence.
- **`test_db_r5_missing_or_zero_budget_no_r5`** — no budget / `max_total_cost_usd == 0` ⇒ stays R4;
  `cost_budget_absent_or_zero` in `missing_r5_gates`.

Plus **golden updates** (behavior changed): the categories partition tests (3/22/2 instead of
3/20/4), `NOT_ASSESSED_CATEGORIES` (now empty at R5 / universe fully consumed), the readiness cap
test (`R5`), report-keys test (+`missing_r5_categories`, `missing_r5_gates`), and the
`test_intake_categories.py` partition/golden assertions.

TDD: write red first (R4-not-R5, missing fields, category rejected pre-migration), then implement.

## 6. Docs updates

- **`CLAUDE.md`:** readiness entry (R0–**R5** ladder, R5 = intake completeness + engine gates, cap
  R5, `slice20.v1`, go-live still false with A5 reason), the categories partition (3/22/2), the
  Slice 15 paragraph (now 22 declarable incl. the two presence-only gates), current-status line,
  migration `0020` entry, test counts.
- **`README.md`:** build-readiness auditor section (R5 rule + gates + report fields), intake-category
  section (22 declarable), migration list.
- **Docstrings:** `readiness.py`, `readiness_report.py` ("capped at R4"→R5; emits R0–R5),
  `categories.py` (partition 3/22/2; the two presence-only non-authorizing gates),
  `ReadinessRepository` (now reads autonomy+budget gates).

## 7. Out-of-scope

- A5 / Appendix-B production-autonomy evaluation; anything that flips `can_go_live_autonomously`.
- Real human-approval-policy engine; real production-authority engine/authorization.
- Semantic contradiction analysis; LLM; content-quality / "critical" detection.
- Any migration beyond the additive category CHECK expansion (no new table/column/grant).
- Cost/autonomy *approval workflows* (presence/validity only).

## 8. Risks & invariants

**Risks**
- **R-1 (go-live safety):** the headline risk — R5 must never imply production autonomy. Mitigation:
  `can_go_live_autonomously` stays hard-false (test 7); production_authority is presence-only;
  `deploy_production` stays mandatory-approval/never-ALLOW.
- **R-2 (partition drift):** moving 2 categories GATED→DECLARABLE must keep the universe disjoint +
  complete and the app CHECK in sync with the DB CHECK. Mitigation: module partition assertion +
  migration + golden tests (3/22/2); test 9 covers app+DB acceptance/rejection.
- **R-3 (fail-closed gates):** absent/invalid autonomy policy or absent/zero budget must block R5.
  Mitigation: boolean gate defaults are false; tests 5/6.
- **R-4 (not_assessed → empty):** at R5 the universe is fully consumed; the
  `NOT_ASSESSED == universe − consumed` invariant and `missing_for_go_live` composition must stay
  correct. Mitigation: module assert + golden tests.

**Invariants**
- Fail-closed: any missing category/gate or stale source ⇒ not R5.
- `can_go_live_autonomously == False` at every level (still capped < A5 authority).
- Determinism, no LLM, no I/O in `app/intake/readiness.py` (gate booleans computed in the repo).
- App declarable-set == DB CHECK set (22) after the migration.
- Monotonic: R0–R4 outcomes unchanged.

## 9. Verification commands (before review)

```bash
uv run ruff check .
make test
RLS_DB_PASSWORD=uaid_app make test-db
git diff --check
git status -sb
```
Expected: ruff clean; `make test` + `make test-db` green with new cases; diff-check clean;
`git status` shows only intended Slice 20 files (`app/intake/categories.py`,
`app/intake/readiness.py`, `app/repositories/readiness.py`, `migrations/versions/0020_*.py`,
`tests/test_readiness.py`, `tests/test_intake_categories.py`, `README.md`, `CLAUDE.md`, and the
`.planning/SLICE-20-PLAN.md` artifact) plus local-only `.planning/HANDOFF.json` / `.env`; nothing
staged.

## 10. Next step after approval

Create the Slice 20 branch; write the failing tests first (§5); then categories partition + migration
+ evaluator/repository (§2–§4); then docs (§6). Pause at green for implementation review before PR.
**Until then: no branch, no code.**
