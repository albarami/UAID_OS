# Slice 57 Plan — Incident workflow + local tickets + support handover (§25.2 / §25.4)

**Status:** APPROVED FOR EXECUTION — independent plan review APPROVE (GPT-5.6 Sol, agent `dba3f159-6d5b-4077-b945-617d83e84383`). OD-57-1…10 = Option A.

**Bound open decisions:**

- OD-57-1 = Option A
- OD-57-2 = Option A
- OD-57-3 = Option A
- OD-57-4 = Option A
- OD-57-5 = Option A
- OD-57-6 = Option A
- OD-57-7 = Option A
- OD-57-8 = Option A
- OD-57-9 = Option A
- OD-57-10 = Option A

**Seats (binding, recorded in `.planning/HANDOFF.json` before planning):**
- **Builder:** Cursor Grok 4.6 (Grok family).
- **Reviewer:** GPT-5.6 Sol (`gpt-5.6-sol-max`, GPT family). Builder sub-agents may not approve.

**Author persona:** Senior SRE / incident-response architect applying fail-closed evidence-integrity discipline.

**Execution authorization:** Plan-only until independent plan APPROVE. Production deploy, hotfix execution, Jira writes, real log diagnosis, `can_go_live_autonomously` flip, A5 ruleset bump, and Slice 59 stabilization closure remain out of scope.

---

## Coordinator standing rulings (2026-08-22; verbatim; binding)

1. The Slice 59 Salim gate is REMOVED. Run Slice 57 → 63 continuously. No per-slice owner reports.
2. Builder = Grok 4.6; Reviewer = GPT-5.6 Sol (different family; sole approval authority).
3. pyright is mandatory every slice; cannot run ⇒ log a HANDOFF blocker, never skip silently.
4. Hard stops unchanged: no weakening tests/CI, no force-push, no spec edits, no budget figures, no secrets, no go-live default-true, no §2.6 bypass.

---

## Sanad / citation key

- **Spec** — `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md` §2.1, §2.6 (213–227; `accept_risk` is listed as a bounded action), §5.2 matrix, §23.4 `incidents` (2245), §25.2 (2377–2389), §25.4 `support_handover_complete` (2417), §26.6 “incident workflow” (2508).
- **Roadmap** — Rev 17 Slice 57 (571–581).
- **Slice 34** — `pm_issue_mappings` are latest-wins observations keyed by `(tenant, project, external_system, instance_key, external_ref)`, not by `external_ref` alone (`app/models/pm_issue_mapping.py`).
- **Slice 56** — `ops_signal_results` PK is `id` only; no `(id, project_id, tenant_id)` unique target (`migrations/versions/0055_ops_signals.py`). `app/ops/db_checks.py` is imported by `0055` and must stay byte-stable.
- **Policy** — `create_project_tasks` is A1; missing policy ⇒ DENY (`app/repositories/autonomy_policies.py`); `deploy_production` and `accept_risk` are §2.6 mandatory-approval (`app/policy/matrix.py:61-68`).
- **Baseline** — `main` `994aca4`; Alembic head `0055`; Slice 57 migration **`0056_ops_incidents`**.

---

## 0. Honesty crux

Unchanged from v1 except:

- **Tickets are authorized, not automatic.** A local bug ticket is written only when `decision_for(project, "create_project_tasks")` is ALLOW. A0 or missing policy ⇒ DENY and **no ticket row**.
- **No `accepted` incident status.** `accept_risk` is §2.6 mandatory-approval. This slice has no verified risk-acceptance path for incidents. Terminal statuses are `resolved` | `superseded` only.
- **Diagnose log error is unavailable, not performed.** `record_log_diagnosis_unavailable` records that the §25.2 action could not run (`no_log_source`). Real source-bound log diagnosis is a **future slice**. Slice 57 does **not** close that capability.
- Optional signal bind uses `source_signal_id` against an **additive** `UNIQUE (id, project_id, tenant_id)` on `ops_signal_results` created in `0056` (not by editing `0055`).
- Optional mapping bind uses `pm_issue_mapping_id` against an additive `UNIQUE (id, project_id, tenant_id)` on `pm_issue_mappings`. Invalid bind **aborts the whole open** before any INSERT.

Claim allowed:

> UAID recorded a tenant-owned incident workflow ledger, and wrote a local bug ticket only when the current autonomy policy ALLOWED `create_project_tasks`. §25.2 A2+ actions and log diagnosis are `recorded_not_executed`. This does not prove production is live, that Jira received a ticket, that logs were diagnosed, or that support took the queue.

---

## 1. Verified baseline

Same hashes as v1 (must remain byte-stable):

- `app/release/production_autonomy.py` = `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029`
- `app/intake/readiness.py` = `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26`
- `app/runtime/control_loop.py` = `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180`
- `app/ops/db_checks.py` frozen.
- Recorded Slice-56 suites: 1160 / 861 and 861 / 1160. Plan task does not re-run them.

---

## 2. Design

### 2.1 Contracts

- `slice57.incidents.v1`
- `slice57.action_eval.v1`
- `ruleset_version='slice57.v1'`
- A5 `slice54.v1`; readiness `slice20.v1`.

### 2.2 §25.2 action map (frozen seq 1–7; no new MATRIX keys)

| seq | Spec action (`action`) | `matrix_action` | Execution this slice |
|---|---|---|---|
| 1 | `create_bug_ticket` | `create_project_tasks` | `local_ticket_written` **iff** decision ALLOW; else `recorded_not_executed` and **no ticket** |
| 2 | `diagnose_log_error` | `none` (literal; CHECK-locked; never empty string) | always `recorded_not_executed`; child `policy_decision='not_evaluated'` (legal **only** on seq 2); `reason_code='no_log_source'`. Capability **not closed**. |
| 3 | `create_patch_branch` | `create_branches` | `recorded_not_executed` / `deferred_slice58` |
| 4 | `open_hotfix_pr` | `open_pull_requests` | `recorded_not_executed` / `deferred_slice58` |
| 5 | `deploy_staging_hotfix` | `deploy_staging` | `recorded_not_executed` / `deferred_slice58` |
| 6 | `deploy_production_hotfix` | `deploy_production` | `recorded_not_executed`; structurally never `local_ticket_written`; no A5 emergency bypass |
| 7 | `rollback_production` | `deploy_production` | same as #6 |

`decision_for` missing policy ⇒ DENY.

Parent evaluation stores one `policy_input_digest` (`sha256:` of canonical JSON, sorted keys, no timestamps):

```
{
  "policy_present": bool,
  "policy_id": <uuid str or null>,
  "autonomy_level": <int or null>,
  "overrides": <full validated overrides mapping, recursively key-sorted>,
  "ruleset_version": "slice57.v1"
}
```

Same keys with different override values MUST differ. Tests include that pair. Optional composite FK `(policy_id, project_id, tenant_id) → autonomy_policies` when `policy_present`; NULL policy_id iff not present.

### 2.3 Incident taxonomy

- `severity ∈ {low, medium, high, critical}`
- `category ∈ {availability, security, error, cost, data_quality, other}`; `other` ⇒ non-blank summary+detail
- `status` one-way: `open` → `investigating` → `mitigated` → `{resolved, superseded}`
- **No `accepted`.** Critical vs non-critical both resolve or supersede; neither is a risk-acceptance.
- Create provenance: `caller_supplied_unverified` only
- Optional `source_signal_id` — composite FK `(source_signal_id, project_id, tenant_id) → ops_signal_results (id, project_id, tenant_id)` after `0056` adds that UNIQUE. Wrong-project/unknown ⇒ refuse **open** (no partial writes).

### 2.4 Tickets (authorized local record)

Ticket rows are append-only. Action-result rows are append-only. Therefore the ticket that seq-1 will reference MUST exist **before** those result rows are inserted.

`open_incident` order inside one REPEATABLE READ transaction:

1. Validate payload + idempotency.
2. If `pm_issue_mapping_id` provided, resolve same-project/tenant mapping or **abort** (no writes).
3. If `source_signal_id` provided, resolve same-project/tenant signal or **abort** (no writes).
4. Load policy; compute seven decisions + `policy_input_digest`.
5. INSERT incident (`status='open'`).
6. **If seq-1 is ALLOW:** INSERT the ticket (`ticket_kind='bug'`, `delivery='local_record'`, optional `pm_issue_mapping_id`). **If seq-1 is not ALLOW:** do not insert a ticket.
7. INSERT evaluation parent.
8. INSERT seven immutable children. Seq-1 `ticket_id` is the row from step 6 or NULL.

`UNIQUE (tenant_id, incident_id)` — at most one ticket per incident.
`UNIQUE (id, incident_id, project_id, tenant_id)` — composite FK target so a result cannot point at another incident’s ticket.

**Re-evaluation (`evaluate_post_launch_actions`):** appends a **new** evaluation; never updates old result rows.

- **Repeated ALLOW:** reuse the existing ticket id on the new seq-1 (`local_ticket_written`). Do not insert a second ticket.
- **DENY → ALLOW:** if no ticket exists, INSERT ticket first, then the new evaluation/results with that `ticket_id`. If a ticket already exists from an earlier ALLOW, reuse it.
- **ALLOW → DENY:** new seq-1 is `recorded_not_executed` with `ticket_id` NULL. The historical ticket row remains (not deleted). Latest seq-1 does not cite it.

Never `broker_call`. Never write Jira.

### 2.5 Log diagnosis — unavailable record (does not close §25.2)

`record_log_diagnosis_unavailable(context, project_id, incident_id, *, actor)` appends event `log_diagnosis_unavailable` with `reason_code='no_log_source'`. It does not inspect logs, call an LLM, or mark the spec action complete. A future slice owns source-bound diagnosis.

### 2.6 Support handover (§25.4 presence only)

Unchanged from v1: append-only `ops_support_handovers`; `recorded_complete` | `recorded_incomplete`; provenance `caller_supplied_unverified` or `request_authenticated` (principal must equal `handed_over_by`); not Slice 59 closure.

### 2.7 Public API (owns `tenant_scope`; no `session` arg)

```python
async def open_incident(context, project_id, *, actor, payload, idempotency_key) -> IncidentSnapshot
async def transition_incident(context, project_id, incident_id, *, actor, to_status) -> IncidentSnapshot
async def record_log_diagnosis_unavailable(context, project_id, incident_id, *, actor) -> IncidentSnapshot
async def evaluate_post_launch_actions(context, project_id, incident_id) -> ActionPrescriptionSet
async def record_support_handover(context, project_id, *, actor, payload) -> HandoverRecord
async def latest_incident / list_open / latest_handover / history  # default 50 / max 100
```

`open_incident` always persists the seven-row evaluation. `evaluate_post_launch_actions` recomputes against **current** policy and appends a new evaluation (latest-wins for reads). Historical evaluations remain immutable.

### 2.8 Persistence — **six** new tables + two additive unique targets

Migration `0056_ops_incidents` (`down_revision=0055`):

**Additive unique targets (no 0055 rewrite):**

- `ALTER TABLE ops_signal_results ADD CONSTRAINT uq_ops_signal_results_id_project_tenant UNIQUE (id, project_id, tenant_id);` mirrored in `app/models/ops_signal.py`.
- `ALTER TABLE pm_issue_mappings ADD CONSTRAINT uq_pm_issue_mappings_id_project_tenant UNIQUE (id, project_id, tenant_id);` mirrored in `app/models/pm_issue_mapping.py`.

**New tenant-owned tables** (all RLS ENABLE+FORCE + `tenant_isolation`):

1. `ops_incidents` — SELECT/INSERT/UPDATE, no DELETE. Guard: INSERT `status='open'`; identity/content immutable; only `status`/`updated_at` mutable; one-way matrix; **`accepted` absent from CHECK**.
2. `ops_incident_events` — SELECT/INSERT only.
3. `ops_incident_tickets` — SELECT/INSERT only. Composite FK to incident; nullable composite FK to mapping unique target; `UNIQUE (tenant_id, incident_id)`; `UNIQUE (id, incident_id, project_id, tenant_id)` as the action-result FK target.
4. `ops_support_handovers` — SELECT/INSERT only.
5. `ops_incident_action_evaluations` — SELECT/INSERT only. `action_count=7`; `policy_input_digest` sha256 of the **full** snapshot in §2.2 (not keys-only); `autonomy_level_snapshot` NULL or 0–5; `UNIQUE (id, incident_id, project_id, tenant_id)`.
6. `ops_incident_action_results` — SELECT/INSERT only. Dual deferred count-match (parent-side AND child-side). Unique `(evaluation_id, seq)` and `(evaluation_id, action)`. CHECK frozen pairs:

```
(seq=1 AND action='create_bug_ticket' AND matrix_action='create_project_tasks')
OR (seq=2 AND action='diagnose_log_error' AND matrix_action='none' AND policy_decision='not_evaluated')
OR (seq=3 AND action='create_patch_branch' AND matrix_action='create_branches')
OR (seq=4 AND action='open_hotfix_pr' AND matrix_action='open_pull_requests')
OR (seq=5 AND action='deploy_staging_hotfix' AND matrix_action='deploy_staging')
OR (seq=6 AND action='deploy_production_hotfix' AND matrix_action='deploy_production')
OR (seq=7 AND action='rollback_production' AND matrix_action='deploy_production')
```

`policy_decision` CHECK: seq 2 must be `not_evaluated`; seq 1 and 3–7 must be `allow`/`deny`/`needs_approval` (never `not_evaluated`).

Posture CHECK:

- seq 2–7: `execution_posture='recorded_not_executed' AND ticket_id IS NULL`
- seq 2 also: `reason_code='no_log_source'`
- seq 1: `(policy_decision='allow' AND execution_posture='local_ticket_written' AND ticket_id IS NOT NULL) OR (policy_decision<>'allow' AND execution_posture='recorded_not_executed' AND ticket_id IS NULL)`
- seq 6–7: `execution_posture='recorded_not_executed'` always.

Composite FK on results:

`(ticket_id, incident_id, project_id, tenant_id) → ops_incident_tickets (id, incident_id, project_id, tenant_id)`

when `ticket_id` is NOT NULL. Parent evaluation carries `incident_id`/`project_id`/`tenant_id`; children inherit via FK to the evaluation unique `(id, incident_id, project_id, tenant_id)`. Direct-SQL attaching another incident’s ticket is refused. Tests cover that.

Also: `app/models/__init__.py` imports the new models. Tests cover RLS/grants/append-only for **each** of the six tables.

Idempotency: same Slice-56 race retry (max 5; `40001`/`40P01`; no unique-violation RAISE). Populated downgrade refused; empty `0056→0055→0056`.

### 2.9 pyright CI

Keep Slice 55/56 paths. Add:

`app/models/ops_incident.py app/repositories/ops_incidents.py tests/test_ops_incidents.py tests/test_ops_incidents_db.py tests/test_ops_incidents_checks.py tests/test_ops_incidents_migrate.py tests/ops_incidents_support.py`

`app/ops` already covers new modules in that package. Also typecheck the two touched models: `app/models/ops_signal.py` (already in CI) and `app/models/pm_issue_mapping.py` (add).

---

## 3. Files (planned)

- `app/ops/incidents.py`, `app/ops/incident_service.py`
- `app/models/ops_incident.py`
- `app/repositories/ops_incidents.py`
- `migrations/versions/0056_ops_incidents.py`
- Additive UniqueConstraint on `app/models/ops_signal.py` + `app/models/pm_issue_mapping.py`
- `app/models/__init__.py`
- tests as in §2.9
- CI yaml

Do **not** modify: `production_autonomy.py`, `readiness.py`, `control_loop.py`, `app/ops/db_checks.py`, `app/ops/signals.py`, `app/ops/assessment.py`, `app/ops/collect.py`, policy `MATRIX` keys, spec, templates, `.env`.

---

## 4. Open decisions

OD-57-1…10 remain Option A as in v1, with these v2 bindings on the same letters:

- OD-57-1 no collect rewire
- OD-57-2 never Jira / `pm.create_issue`
- OD-57-3 no patch/hotfix/deploy/rollback execution
- OD-57-4 no log source; unavailable-record only; diagnosis **not closed**
- OD-57-5 no new MATRIX keys; rollback → `deploy_production`
- OD-57-6 no A5 emergency hotfix bypass
- OD-57-7 never auto-open from signals
- OD-57-8 no HTTP
- OD-57-9 pyright §2.9
- OD-57-10 preservation list including additive uniques only

---

## 5. Tests

Docker-free:

1. Missing policy / A0: incident persists; **zero tickets**; seq-1 DENY + `recorded_not_executed`.
2. A1 (or higher) with `create_project_tasks` allowed: exactly one local ticket; seq-1 ALLOW + `local_ticket_written` + `ticket_id` set.
3. Tightened override `create_project_tasks.allow=false`: DENY, zero tickets.
4. Invalid taxonomy refused; `other` without detail refused; transition skip refused; **`accepted` rejected by validator and not in STATUSES**.
5. A2: patch/PR ALLOW + not_executed; staging DENY; production/rollback not_executed.
6. A5: production hotfix still not_executed and still needs_approval (mandatory); no emergency bypass.
7. Unknown `pm_issue_mapping_id` / wrong-project: open raises; **no incident row**.
8. Valid same-project mapping id: ticket carries that FK; no broker calls (`pm.create_issue` / `broker_call` absent from incident modules).
9. Unknown `source_signal_id`: open raises; no incident row.
10. `record_log_diagnosis_unavailable` writes the unavailable event only; tests assert it does not set a “diagnosed” capability flag.
11. Public wrappers have no `session` parameter.
12. A5/readiness/go-live `before==after`; Slice 56 collect still `2/0/9` and `incident_reports=not_observed`.

DB:

1. Six-table RLS + grants + append-only (UPDATE/DELETE/TRUNCATE) per table; incidents UPDATE only via guard-legal status.
2. Additive uniques exist; composite FKs reject cross-project signal/mapping ids.
3. Evaluation ≠7 children fails deferred count-match; wrong seq/action pair fails CHECK; seq-6/7 with `local_ticket_written` fails CHECK; seq-1 ALLOW without ticket_id fails CHECK; seq-2 with `policy_decision='allow'` fails CHECK; same override keys/different values change `policy_input_digest`; attaching another incident’s `ticket_id` fails the composite FK. DENY→ALLOW creates a ticket then a new evaluation; repeated ALLOW reuses the ticket (still one row).
4. Idempotency race; digest conflict.
5. Empty `0056→0055→0056`; populated downgrade refused; findings-guard MD5 unchanged; `db_checks.py` SHA unchanged.
6. Handover `request_authenticated` without matching principal refused.

---

## 6. Must NOT claim

- Production/staging deployed; pager/on-call exists.
- Jira/Linear ticket created.
- Logs were diagnosed; §25.2 “Diagnose log error” is implemented.
- Patch/hotfix/deploy/rollback ran.
- A5 emergency policy authorized an unapproved production hotfix.
- Incident `accepted` is a verified risk-acceptance.
- Request-authenticated handover is a human signature.
- Slice 56 `incident_reports` is now observed.
- `can_go_live_autonomously=true`.
- **An open incident, a local ticket, a prescription set, or a handover record establishes adequate incident response, support coverage, or stabilization success.**

---

## 7. Sequence after plan APPROVE

Stamp OD-57-* = Option A. Tests first. Build. Validate (ruff, pyright, make test, make test-db). Sol code review. Docs, PR, CI, squash-merge, HANDOFF. Immediately Slice 58.

---

## 8. Exit

Plan APPROVE + code APPROVE + CI green + merge. Authorized local tickets only. Diagnosis capability explicitly open. A5/readiness/go-live unchanged.

---

## Appendix S — Muhasabah (v3)

v2 REJECT (agent `4aee0355-1d48-4471-8ee5-6a2ce41fddab`): digest now hashes full overrides; ticket is inserted before immutable results; seq-2 decision is `not_evaluated` + `matrix_action='none'`; ticket composite FK proves same incident.

v1 REJECT (agent `84891467-61af-47ea-aab1-fcf336848335`) — seven defects closed in v2 text:

1. Ticket created only on ALLOW; A0/missing policy tested.
2. `accepted` removed; `accept_risk` not used.
3. Additive `UNIQUE (id, project_id, tenant_id)` on `ops_signal_results` in `0056`.
4. Bind via `pm_issue_mapping_id` + additive unique; invalid bind aborts all writes.
5. Frozen seq/action/matrix CHECKs, uniques, posture by action, policy digest snapshot.
6. Six tables named; models `__init__` + two existing models for FK targets.
7. Diagnosis renamed unavailable; future slice owns real diagnosis.

Residual: Slice 59 numeric error-budget contract still unparsed; not guessed.
