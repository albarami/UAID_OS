# Slice 58 Plan — Hotfix-intent evaluation (does not close §26.6) (§25.2)

**Status:** APPROVED (v3) by GPT-5.6 Sol agent `aab9e2d8-141e-4de2-b992-d0d6555cba97`. OD-58-1…10 bound Option A (v3). Build authorized.

**Bound open decisions:** OD-58-1…10 default **Option A** as restated below (binding on independent plan APPROVE).

**Seats (binding):**
- **Builder:** Cursor Grok 4.6 (Grok family).
- **Reviewer:** GPT-5.6 Sol (`gpt-5.6-sol-max`, GPT family). Sole approval authority.

**Author persona:** Senior SRE / incident-response architect applying fail-closed evidence-integrity discipline.

**Slice closure:** This slice does **not** close spec §26.6 “self-healing/hotfix loop” and does **not** satisfy the roadmap Slice 58 exit. It lands a **hotfix-intent evaluation**: local A2 plans + fail-closed production non-execution + **current** Slice 52/54 rollback *context*. Diagnosis, patch artifacts, git branches, GitHub PRs, staging/production deploys, and production rollbacks remain unimplemented. Owner cadence still proceeds to Slice 59 after merge; Slice 59 must **not** treat self-healing as done. Residual actuators stay explicitly open.

**Execution authorization:** Plan-only until independent plan APPROVE. No git writes, no broker, no Jira, no staging/production deploy, no production rollback execution, no `can_go_live_autonomously` flip, no A5 ruleset bump, no §2.6 bypass.

---

## Coordinator standing rulings (2026-08-22; verbatim; binding)

1. The Slice 59 Salim gate is REMOVED. Run Slice 57 → 63 continuously. No per-slice owner reports.
2. Builder = Grok 4.6; Reviewer = GPT-5.6 Sol (different family; sole approval authority).
3. pyright is mandatory every slice; cannot run ⇒ log a HANDOFF blocker, never skip silently.
4. Hard stops unchanged: no weakening tests/CI, no force-push, no spec edits, no budget figures, no secrets, no go-live default-true, no §2.6 bypass.

---

## Sanad / citation key

- **Spec** — §2.1, §2.6 (`deploy_production` mandatory-approval), §5.2, §25.2 (2377–2389), §26.6 “self-healing/hotfix loop”.
- **Roadmap** — Slice 58 (583–593). Must NOT claim unapproved production hotfix. Must not claim the loop is closed.
- **Slice 57** — `ops_incident_action_results` seq 3–5 stay `deferred_slice58` (`app/ops/incident_db_checks.py`, 0056 importer). Not rewritten.
- **Latch** — `assert_project_not_stopped` locks `projects` FOR UPDATE then reads latest `emergency_stop_events` (`app/repositories/emergency_controls.py:79-121`). `status()` is **not** a lock.
- **Gate #10 currentness** — `production_autonomy.py:1188-1285` (the if/elif ladder), not the stored `RollbackCoverage.gate_eligible` flag (`rollback_verifications.py:445`). Coverage flags are inputs; the conjunction is the currentness proof.
- **Release-binding match** — `EmergencyControlRepository._current_release_binding` (`emergency_controls.py:247-296`) plus `authorize_rollback` identity checks (`:564-574`). Authorization is a distinct `EmergencyRollbackAuthorization` row, not a flag on the standing binding.
- **Policy** — `check_authority` is pure (`app/policy/engine.py`). `decision_for` re-reads the row (`autonomy_policies.py:84-93`) and must **not** be called four times.
- **Baseline** — `main` `08c17e0`. Alembic head **`0056`**. Migration **`0057_self_healing`** (`down_revision=0056`).

---

## 0. Honesty crux

UAID still cannot create a git branch, open a GitHub PR, deploy staging/production, or roll back production. Slice 58 records **intent under one policy snapshot**, not a healed system.

Claim allowed:

> UAID recorded a tenant-owned hotfix-intent evaluation for an existing non-terminal incident, after serializing against the Slice-54 latch. Local branch/PR plan rows were written only when a single loaded-and-validated policy snapshot ALLOWED the matching A2 action and the plan-kind FK proved the pairing. Staging and production hotfixes were not executed; DENY and NEEDS_APPROVAL outrank actuator-absence reasons. Current-release Slice 52/54 rows are cited by composite FK only when the complete gate-#10 conjunction holds and the authorization row matches the selected binding, candidate, evidence pack, rollback run, and binding digest. This is not a hotfix-bound rollback path and not a production rollback. This does not close §26.6.

---

## 1. Verified baseline (byte-stable)

- `app/release/production_autonomy.py` = `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029`
- `app/intake/readiness.py` = `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26`
- `app/runtime/control_loop.py` = `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180`
- `app/ops/db_checks.py` = `468837a3afe452239fa392a16cdf1ab90c10938fecb0854478f32606eabb49fc`
- `app/ops/incident_db_checks.py` frozen.
- `app/ops/incidents.py` = `0b5e996c410169b41d3aacd12659d680e3147354cfd23e2dad568a4221eb76c7`
- Findings-guard MD5 = `808036faf2660d6810aeca4342e6f1ac`

Do **not** modify those files, policy `MATRIX` keys, spec, templates, `.env`. Additive methods on `AutonomyPolicyRepository` and `EmergencyControlRepository` are allowed.

---

## 2. Design

### 2.1 Contracts

- `slice58.hotfix_intent.v1` (not a “self-healing complete” contract)
- `slice58.hotfix_plan.v1`
- `ruleset_version='slice58.v1'`
- A5 `slice54.v1`; readiness `slice20.v1`.

### 2.2 Action map (seq 3–7; no new MATRIX keys) — policy precedence first (v3 defect 3)

Shared ladder for **every** seq 3–7 result, applied to that sequence’s matrix action:

1. `Decision.DENY` → posture `recorded_not_executed`, reason `plan_denied_by_policy`, no plan row.
2. `Decision.NEEDS_APPROVAL` → posture `recorded_not_executed`, reason `plan_needs_approval`, no plan row.
3. `Decision.ALLOW` only then:
   - seq 3 → `local_branch_plan_written` / `plan_written`
   - seq 4 → `local_pr_plan_written` / `plan_written` **iff** same-run `patch_branch` plan exists; else `recorded_not_executed` / `branch_plan_required`
   - seq 5 → `staging_not_executed` / `no_deploy_actuator` (never a plan)
   - seq 6–7 → `production_not_executed` / `production_not_executed` (never a plan; never an A5 emergency bypass)

`NEEDS_APPROVAL` is **not** `plan_denied_by_policy`. `no_deploy_actuator` and `production_not_executed` are **ALLOW-only residual reasons**. They must not hide a DENY or a required approval.

| seq | action | matrix_action | ALLOW residual |
|---|---|---|---|
| 3 | `create_patch_branch` | `create_branches` | local branch plan |
| 4 | `open_hotfix_pr` | `open_pull_requests` | local PR plan if branch plan exists |
| 5 | `deploy_staging_hotfix` | `deploy_staging` | `no_deploy_actuator` |
| 6 | `deploy_production_hotfix` | `deploy_production` | `production_not_executed` |
| 7 | `rollback_production` | `deploy_production` | `production_not_executed` |

Seq 4 **requires** the same-run `patch_branch` plan. No caller “existing-branch” source. Branch DENY + PR ALLOW ⇒ no PR plan, seq-4 `branch_plan_required`.

### 2.3 One policy snapshot (v3 defect 2)

Do **not** call `decision_for` four times. `decision_for` re-SELECTs (`autonomy_policies.py:87`) so four calls at READ COMMITTED can straddle two policy versions.

Add **one** authoritative repository operation on `AutonomyPolicyRepository` (additive; existing `decision_for` unchanged):

`snapshot_decisions(project_id, actions: Sequence[str]) -> PolicyDecisionSnapshot`

Inside the same write transaction, after the project latch lock:

1. `SELECT … FROM autonomy_policies WHERE project+tenant FOR SHARE` **once** (missing row ⇒ fail-closed DENY for every action; `policy_present=false`).
2. `validate_overrides` **once** on that row (invalid ⇒ DENY for every action).
3. Derive every requested Decision in-process via `check_authority(action, snapshot.level, snapshot.overrides)` — no further SQL.
4. Return a frozen snapshot: `{policy_present, policy_id, autonomy_level, overrides, decisions}`.

Persist on the run:

- `policy_present`, `policy_id`, `autonomy_level_snapshot` (NULL iff absent)
- `policy_input_digest` — canonical JSON of `{policy_present, policy_id, autonomy_level, overrides: full mapping, ruleset_version}`
- `request_digest` — canonical JSON of `{incident_id, ruleset_version}` (no clocks)
- `decision_snapshot` JSONB of the four unique matrix actions from **this** snapshot

Overlay maps those Decisions onto postures. Authorization of plans is only the snapshot Decisions.

Concurrent test: evaluate holds `FOR SHARE`; a concurrent `upsert` of the same project policy waits; after evaluate commits, the stored digest matches the locked snapshot, not a later upsert. A second evaluate after the upsert stores a different digest.

### 2.4 Public API

Owns `tenant_scope` at **READ COMMITTED**. **No `session` arg. No broker.**

- `evaluate_hotfix_intent(context, project_id, incident_id, *, actor, idempotency_key)`
- `latest_hotfix_intent(context, project_id, incident_id)`
- `history_hotfix_intent(context, project_id, incident_id, *, limit)`

Idempotency `(tenant, project, incident, idempotency_key)`. Digest mismatch ⇒ conflict. Retry max 5 on `40001`/`40P01`.

### 2.5 Latch serialization

Inside the write transaction, **before any INSERT**:

1. `assert_project_not_stopped(session, context, project_id)` — `SELECT … FOR UPDATE` on the project row, then latest stop event; active ⇒ raise, no writes.
2. Then `snapshot_decisions` (`FOR SHARE` on the policy row) in that same transaction.
3. Hold both through run/plan/child INSERTs.
4. BEFORE INSERT DB guard on `ops_self_healing_runs`: if latest `emergency_stop_events.state_after` for the same tenant/project is `active`, RAISE.
5. Test: concurrent activation vs evaluate — activation that wins the project lock causes evaluate to fail with the stop-active error; no run row.

Do **not** use unlocked `status()` as the gate.

### 2.6 Current-release rollback context (v3 defect 1)

Not a hotfix-bound rollback path. Optional nullable composite FKs on the **run**.

**Gate #10 currentness (do not copy `coverage.gate_eligible`):**

1. Call existing `RollbackVerificationRepository.coverage_for_project(project_id)` to obtain the **flags**.
2. Apply a Slice-58 **pure** helper `gate10_conjunction_passed(coverage) -> bool` that is the same ladder as `production_autonomy.py:1188-1285`:
   - fail unless `scope_resolved`, `core_present`, `core_reaudited`, `repo_binding_agreed`, `staging_target_valid`, `staging_snapshot_present`, `staging_snapshot_available` **and** `staging_snapshot_fresh`, `run_present`, not `attempt_failed`, `artifact_trusted` and `execution_observation == connector_observed_ci`, `binding_current`, `phase_coverage_complete` and `phase_count == 5`, `evidence_consistent`, `drill_passed` **and** the stored `gate_eligible` flag.
3. Set `rollback_verification_run_id` only when that conjunction is true **and** the exact latest bound run can be selected (same identity filters `coverage_for_project` used: current frozen candidate + re-audited pack + staging binding). If the SELECT misses, FK stays NULL.
4. Store `rollback_coverage_digest` = canonical JSON of the same keys as `gate10_context` (`production_autonomy.py:1168-1187`).

A stored `gate_eligible=true` run whose staging snapshot is stale or whose binding is not current **must not** receive the FK.

**Standing binding:** `emergency_control_binding_id` → `emergency_control_bindings` via `uq_ecb_id_project_tenant` when `latest_binding` exists. This is **not** an authorization.

**Authorization (must match the selected current graph, not any same-project row):**

Expose an additive public `current_release_binding_context(project_id)` on `EmergencyControlRepository` that returns the same tuple as `_current_release_binding` (candidate, core, rollback run, digest) without changing `authorize_rollback`.

Set `emergency_rollback_authorization_id` only when **all** of the following hold for one `EmergencyRollbackAuthorization` row:

- `result_code='authorized_not_executed'`
- `binding_id == latest_binding.id`
- `release_candidate_id == current candidate.id`
- `evidence_pack_id == current core.id`
- `rollback_verification_run_id == current rollback run.id`
- `release_rollback_binding_digest == current digest`

0057 adds additive `UNIQUE (id, project_id, tenant_id)` on `emergency_rollback_authorizations` if missing.

An older `authorized_not_executed` row for a previous binding/digest **must not** be cited. NULL FKs are honest absence. These FKs never change seq 6/7 off the §2.2 ladder (ALLOW residual stays `production_not_executed`).

### 2.7 Write order

1. READ COMMITTED tenant_scope; `assert_project_not_stopped`; resolve non-terminal same-project incident; `snapshot_decisions` once; compute digests + currentness FKs.
2. INSERT run (guard may still refuse if latch flipped).
3. If seq-3 ALLOW: INSERT `patch_branch` plan.
4. If seq-4 ALLOW **and** branch plan exists: INSERT `hotfix_pr` plan; else no PR plan.
5. INSERT five children with plan FKs that include `plan_kind`.
6. Audit ids/status/decisions/counts/FK-present booleans — never `intended_ref`.

### 2.8 Plan FK integrity

`ops_hotfix_plans`:

- `plan_kind ∈ {patch_branch, hotfix_pr}`
- `UNIQUE (tenant_id, run_id, plan_kind)`
- `UNIQUE (id, run_id, project_id, tenant_id, plan_kind)` — **kind is in the FK target**

Child columns:

- seq 3: `plan_id` NOT NULL iff ALLOW; FK pinned to `patch_branch`. Direct SQL attaching a `hotfix_pr` row to seq 3 must fail.
- seq 4: `plan_id` NOT NULL iff ALLOW and branch plan present; FK pinned to `hotfix_pr`.
- seq 5–7: `plan_id` IS NULL.

Test swapped-kind INSERT and branch-denied / PR-allowed.

### 2.9 Schema (`0057_self_healing`)

Three tenant-owned tables, RLS ENABLE+FORCE + `tenant_isolation`, SELECT/INSERT only, append-only triggers:

1. `ops_self_healing_runs`
2. `ops_hotfix_plans`
3. `ops_self_healing_results` — `action_count=5`; dual deferred count-match

Additive UNIQUE on `emergency_rollback_authorizations (id, project_id, tenant_id)` if absent.

Populated downgrade refused if any 0057 table has rows (`DBAPIError` match `cannot downgrade Slice 58`). Empty `0057→0056→0057`.

---

## 3. Open decisions

| ID | Option A (v3) |
|---|---|
| OD-58-1 | New 0057 store. Leave 0056 `deferred_slice58` historical. |
| OD-58-2 | Never broker/git. Local plans only. Slice is **non-closing**. |
| OD-58-3 | Staging ALLOW residual is `no_deploy_actuator`. Staging DENY/`NEEDS_APPROVAL` outrank that reason. |
| OD-58-4 | No A5 emergency production bypass. |
| OD-58-5 | Cite Slice 52 run only via complete gate-#10 conjunction; cite `EmergencyRollbackAuthorization` only when it matches the selected binding+candidate+pack+run+digest. Current-release context only. |
| OD-58-6 | `assert_project_not_stopped` + hold lock + INSERT guard + concurrent test. |
| OD-58-7 | Do not auto-request Slice-4 approval. Distinct `plan_needs_approval`. |
| OD-58-8 | No HTTP. |
| OD-58-9 | No new MATRIX keys. One `snapshot_decisions` load, not four `decision_for` calls. |
| OD-58-10 | Frozen file list in §1. |

No §12 halt. Residual §26.6 actuators are **open**, not a Salim blocker for landing this evaluation store.

---

## 4. Tests

Docker-free: missing/A0 zero plans; A2 ALLOW writes branch+PR; A2 tighten `requires_approval` ⇒ `plan_needs_approval` and zero plans; branch DENY + PR ALLOW ⇒ `branch_plan_required`, zero PR plans; **staging DENY ⇒ `plan_denied_by_policy` (not `no_deploy_actuator`)**; **staging `requires_approval` override ⇒ `plan_needs_approval`**; A3+ staging ALLOW still `staging_not_executed`/`no_deploy_actuator`; A5 seq 6–7 never a plan; wrappers have no `session`; no `broker_call`/`git`; A5/readiness/go-live `before==after`; Slice 57 seq 3–5 reason still `deferred_slice58`.

DB: RLS/append-only self-seeded; count-match 5; swapped-kind FK fail; seq 6/7 with plan_id fail; latch concurrent activation; **concurrent policy upsert vs `FOR SHARE` snapshot**; **stale Slice-52 binding / stale staging snapshot does not set rollback-run FK**; **old authorization for a previous digest/binding is not cited**; idempotency; empty/populated migrate; frozen hashes; audit has no `intended_ref`.

CI pyright: add Slice 58 paths; keep 55/56/57; do not lower the bar.

---

## 5. Must NOT claim

- §26.6 / roadmap Slice 58 exit is satisfied.
- Git branch, GitHub PR, CI workflow, staging/production deploy, or production rollback ran.
- Standing `rollback_authority_bound` **is** `authorized_not_executed`.
- Current-release Slice 52/54 context is a hotfix-bound rollback path.
- Unapproved production hotfix; latch bypass; `can_go_live_autonomously=true`.
- Slice 57 `deferred_slice58` rows were upgraded into executed hotfixes.
- A stored `gate_eligible` flag, by itself, proves current rollback context.

---

## 6. Sequence after plan APPROVE

Stamp OD-58-* = Option A (v3). `feat/slice-58-hotfix-intent` from current `main`. Tests with the slice. Validate. Sol code review. Docs must say **non-closing**. PR, green CI, squash-merge, HANDOFF (residual §26.6 open). Owner cadence: Slice 59 next; 59 plan must not claim self-healing closed.

---

## 7. Exit

Plan APPROVE + code APPROVE + CI green + merge of a **hotfix-intent evaluation store**. §26.6 remains open. A5/readiness/go-live unchanged.

---

## Appendix S — Muhasabah

- v1 REJECT (`aab9e2d8`): false closure; unlocked latch; rollback booleans; policy NEEDS_APPROVAL collapse; plan-kind FK.
- v2 REJECT (`aab9e2d8`): stored `gate_eligible` ≠ gate-#10 conjunction + unmatched authorization; four `decision_for` calls at READ COMMITTED; seq 5–7 residual reasons hiding DENY/NEEDS_APPROVAL.
- v3 addresses those three remaining defects. Alembic 0056→0057 unchanged. Owner continuous-run to 59 is not a claim that 58 closed the loop.
