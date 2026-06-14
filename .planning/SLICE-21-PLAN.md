# Slice 21 — A5 production-autonomy evaluator skeleton (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice21-a5-evaluator` off `main` @ `e745e26`; pure A5 evaluator (`app/release/`), compute-on-read
repository, read-only endpoint, tests, docs. **No migration, no persistence, no go-live.**
Verification: `ruff` clean, `make test` 196, `make test-db` 257. D-21-A resolved: compute-on-read.
**Base:** `main` @ `e745e26` (clean).
**Rulings:** `.planning/SLICE-21-A5-DISCUSSION.md` (D-A5-1..5). Option A: fail-closed, non-authorizing
A5 evaluator skeleton. Separate `production_autonomy` report. Go-live stays hard-false.

---

## 0. One-line summary

Add a pure, deterministic, **fail-closed, non-authorizing** evaluator that scores the 13 Appendix-B
A5 gates and emits a **separate** `production_autonomy` report (distinct from the R5 readiness
report), exposed read-only. **Only gate #1 (R5 intake complete) can pass**; the other 12 are
`insufficient_evidence` (partial context) or `no_evidence_source`. `a5_satisfied` and
`can_go_live_autonomously` are **always false** this slice. No evidence subsystems, no go-live, no
migration, no LLM.

## 1. Scope & file layout

- **New pure engine** `app/release/production_autonomy.py` (new `app/release/` package — A5 is
  release *authority*, deliberately separate from `app/intake/` readiness). Exposes
  `evaluate_production_autonomy(...) -> ProductionAutonomyReport`.
- **New repository** `app/repositories/production_autonomy.py` —
  `ProductionAutonomyRepository.evaluate(project_id)`: reads RLS-scoped state (the R5 readiness
  level via `ReadinessRepository`, plus context for the partial gates), builds the gate inputs, calls
  the pure engine. **Read-only — computes on read, no persistence** (see §5).
- **Read API** — new `GET /api/projects/{project_id}/production_autonomy` in `app/api/dashboard.py`.

## 2. Gate-status contract (per D-A5-2)

Each of the 13 gates gets a `status` ∈ `{passed, insufficient_evidence, no_evidence_source}` + a
stable `reason`:
- **#1 R5 intake complete** — `passed` iff readiness level == `R5`; else `insufficient_evidence`
  (reason `readiness_below_r5:<level>`). The **only** gate that can pass this slice.
- **#2, #8, #9, #12** — always `insufficient_evidence` (partial *context* only; reasons name the gap,
  e.g. `environments_declared_but_no_live_target`, `cost_stop_only_no_forecast`,
  `a5_policy_primitive_but_no_preapproved_release`). Context booleans MAY be recorded but never flip
  the status to `passed`.
- **#3, #4, #5, #6, #7, #10, #11, #13** — always `no_evidence_source:<subsystem>` (e.g.
  `no_evidence_source:ci_branch_protection`, `:test_oracle_execution`, `:security_findings`,
  `:shortcut_findings`, `:risk_acceptance_records`, `:rollback_verification`, `:monitoring`,
  `:emergency_stop`).
- **No partial primitive may satisfy a gate** (D-A5-2). Deny-by-default.

## 3. Report shape (per D-A5-3 — separate from readiness)

`ProductionAutonomyReport.to_dict()`:
```jsonc
{
  "project_id": "...",
  "a5_satisfied": false,                 // always false this slice (all-13-passed AND gate #1)
  "can_go_live_autonomously": false,     // ALWAYS false (D-A5-5)
  "can_go_live_reasons": [               // why go-live is structurally false
    "a5_gates_not_all_satisfied",
    "request_authenticated_a5_preapproval_not_implemented"
  ],
  "gates": [ {"number": 1, "gate": "r5_intake_complete", "status": "passed|insufficient_evidence", "reason": "..."}, ... 13 ],
  "passed_gate_count": 1,                 // 0 or 1 this slice
  "unmet_gates": [ {"number": ..., "status": ..., "reason": ...}, ... ],
  "ruleset_version": "slice21.v1"
}
```
The R5 readiness report is **unchanged** — no `a5_gates` block added to it.

## 4. Evaluator design (pure)

`evaluate_production_autonomy(project_id, *, readiness_level: str, autonomy_policy_present: bool =
False, cost_policy_present: bool = False, environments_declared: bool = False,
generated_ac_provenance_ok: bool = False)`:
- Builds the 13 gate entries deterministically per §2 (only #1 keys off `readiness_level`; the four
  partial gates record the passed-in context booleans but stay `insufficient_evidence`; the rest are
  `no_evidence_source`).
- `a5_satisfied = all(g.status == "passed" for g in gates)` ⇒ false this slice.
- `can_go_live_autonomously = False` **always** (hard-coded; never derived from `a5_satisfied`), with
  `can_go_live_reasons` naming both "gates not satisfied" and "request-auth A5 pre-approval not
  implemented" (D-A5-5).
- Pure: no DB, no I/O, no LLM. Fail-closed defaults (every context bool defaults False).

## 5. Repository design + compute-on-read decision

`ProductionAutonomyRepository.evaluate(project_id)` (inside `tenant_scope`, RLS):
- `readiness_level` = `ReadinessRepository(session, ctx).evaluate(project_id).readiness_level`
  (pure read of current state).
- Context booleans for the partial gates (recorded, non-passing): `autonomy_policy_present`
  (an `autonomy_policies` row exists), `cost_policy_present` (a `budgets` row exists),
  `environments_declared` (the env category declared). These are **context only** — they never pass
  a gate.
- Calls the pure engine; returns the report. **No persistence, no migration** — the verdict is
  deterministic from current state and (this slice) always "not satisfied", so persisting snapshots
  adds no value yet. **Decision D-21-A (flag for confirmation):** compute-on-read (no table) vs.
  persist+history like readiness. *Recommend compute-on-read* — leaner, no migration; a persisted
  `production_autonomy_reports` table + history can be a later slice if operators want trend.
- This is **read-only**: a GET computes a pure verdict with **no DB writes** (consistent with the
  Slice-17 "no persist on GET" rule — computing ≠ persisting).

## 6. Read API

`GET /api/projects/{project_id}/production_autonomy` → `{"production_autonomy": { ...report... }}`.
- Behind `require_tenant` → `tenant_scope` → RLS (unchanged auth boundary).
- Cross-tenant / nonexistent `project_id`: RLS-scoped reads yield an empty-spine state ⇒ a generic
  R0-based "not satisfied" report (gate #1 `insufficient_evidence`) — **no existence oracle, no leak**
  (same property as readiness). Always `200`.
- GET-only ⇒ write verbs `405`. No `null` case (the report is always computable).

## 7. Tests first (TDD) — exact

**Pure engine** (`tests/test_production_autonomy.py`, Docker-free):
1. `test_only_r5_gate_passes_when_readiness_r5` — readiness `R5` ⇒ gate #1 `passed`; all other 12
   not `passed`; `passed_gate_count == 1`.
2. `test_gate1_insufficient_when_readiness_below_r5` — readiness `R4` ⇒ gate #1
   `insufficient_evidence` (`readiness_below_r5:R4`); `passed_gate_count == 0`.
3. `test_partial_context_gates_are_insufficient_evidence` — gates #2/#8/#9/#12 are
   `insufficient_evidence` even when their context booleans are True (context never passes).
4. `test_sourceless_gates_are_no_evidence_source` — gates #3/#4/#5/#6/#7/#10/#11/#13 are
   `no_evidence_source:<subsystem>`.
5. `test_a5_never_satisfied_and_go_live_always_false` — `a5_satisfied is False` and
   `can_go_live_autonomously is False` even with readiness `R5` + all context booleans True;
   `can_go_live_reasons` names the A5-preapproval prerequisite.
6. `test_report_keys_and_ruleset` — all report keys present; `ruleset_version == "slice21.v1"`; 13
   gate entries; `unmet_gates` length == 12.
7. `test_fail_closed_defaults` — calling with only `readiness_level` (all context defaults False)
   still yields a well-formed report; no gate erroneously passes.

**Repository** (`tests/test_production_autonomy.py`, `@pytest.mark.db`):
8. `test_db_reads_readiness_r5_passes_gate1` — seed a full R5 project (reuse the Slice-20 helpers:
   full spine + all declarable categories + autonomy row + budget) ⇒ repo `evaluate` returns gate #1
   `passed`, `a5_satisfied` False, go-live False.
9. `test_db_below_r5_gate1_insufficient` — an R2/R4 project ⇒ gate #1 `insufficient_evidence`.
10. `test_db_read_only_no_writes` — `evaluate` performs no INSERT/UPDATE (assert no new rows in
    `readiness_reports`/any table; pure read).

**API** (`tests/test_api.py`, `@pytest.mark.db`):
11. `test_production_autonomy_endpoint_returns_report` — authorized GET ⇒ `200`, `production_autonomy`
    non-null, `can_go_live_autonomously` False, 13 gates.
12. `test_production_autonomy_auth_deny_by_default` — missing/Basic/unknown/revoked ⇒ `401`;
    authorized ⇒ `200`.
13. `test_production_autonomy_cross_tenant_no_leak` — key A on tenant B's project ⇒ `200` with a
    generic not-satisfied report (no B data, gate #1 not passed).
14. `test_production_autonomy_read_only` — `POST` ⇒ `405`.

TDD: write red first (module/endpoint absent), then implement.

## 8. Docs updates

- **`CLAUDE.md`:** new `app/release/production_autonomy.py` + repo entry; the read-API endpoint list
  (+`production_autonomy`); a "What exists" note that A5 is a **fail-closed, non-authorizing skeleton**
  — only gate #1 (R5) can pass, go-live stays hard-false, the 12 other gates await Phase 3/5/6
  evidence subsystems; current-status line; test counts.
- **`README.md`:** a short "Production-autonomy (A5) evaluator" section + the new endpoint;
  emphasize non-authorizing / go-live-false.
- **Module docstrings:** state non-authorizing + fail-closed + the A5/Appendix-B mapping.

## 9. Risks & invariants

**Risks**
- **R-1 (authority safety — headline):** the skeleton must be unmistakably **non-authorizing** —
  `can_go_live_autonomously` hard-false, `a5_satisfied` cannot be True while any gate is stubbed,
  `deploy_production` stays mandatory-approval/never auto-ALLOW. Tests 5 + (api) enforce.
- **R-2 (no fake pass):** stubbed gates report `no_evidence_source`/`insufficient_evidence`, never
  `passed` (spec §2.1). Tests 3/4.
- **R-3 (no existence oracle):** cross-tenant returns a generic report, not another tenant's data.
  Test 13.
- **R-4 (scope creep):** must NOT build any evidence subsystem (CI, test exec, findings, rollback,
  monitoring). Out-of-scope (§10).

**Invariants**
- `can_go_live_autonomously == False` always; `a5_satisfied == False` this slice.
- Only gate #1 can pass; deny-by-default for the rest.
- Pure engine: no I/O/LLM; repo read-only (no writes, no migration).
- Auth boundary unchanged (`require_tenant`/`tenant_scope`/RLS).
- R5 readiness report unchanged (separate surfaces).

## 10. Out-of-scope

- Any real evidence subsystem: CI/branch-protection, test-oracle execution, security findings,
  shortcut/fake-done findings, risk-acceptance records, rollback verification, monitoring, emergency
  stop (Phase 3/5/6).
- Request-authentication / verified A5 pre-approval; any path that flips go-live true.
- Persisting A5 snapshots / history / a migration (compute-on-read this slice — D-21-A).
- LLM, semantic analysis, actual production deploy.

## 11. Verification commands (before review)

```bash
uv run ruff check .
make test
RLS_DB_PASSWORD=uaid_app make test-db
git diff --check
git status -sb
```
Expected: ruff clean; `make test` + `make test-db` green with new cases; diff-check clean; `git
status` shows only intended Slice 21 files (`app/release/production_autonomy.py`,
`app/repositories/production_autonomy.py`, `app/api/dashboard.py`, `tests/test_production_autonomy.py`,
`tests/test_api.py`, `README.md`, `CLAUDE.md`, and the `.planning/SLICE-21-PLAN.md` artifact) plus
local-only `.planning/HANDOFF.json` / `.env`; nothing staged.

## 12. Open decision for coordinator

- **D-21-A (persistence):** compute-on-read (recommended, no table/migration) vs. persist a
  `production_autonomy_reports` table with latest/history like readiness. The plan assumes
  compute-on-read; confirm or switch.

## 13. Next step after approval

Create the Slice 21 branch; write the 14 failing tests first (§7); then the pure engine (§4), the
repository (§5), the endpoint (§6); then docs (§8). Pause at green for implementation review before
PR. **Until then: no branch, no code.**
