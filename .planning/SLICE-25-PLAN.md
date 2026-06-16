# Slice 25 — Release candidate / release-binding store — PLAN v1

**Status:** AWAITING PLAN APPROVAL — no branch / no code / no migration / no tests until approved.
Rulings D-RB-1..8 are binding (see `.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md`, APPROVED).
**Base:** `main` @ `4c6c1f4`; working tree has intentional `.planning/HANDOFF.json` drift plus
untracked Slice-25 discussion/PLAN docs only. No implementation files changed.
**Migration head:** `0023` → new head **`0024`** (verified current head is `0023`).
**Persona:** senior release-governance / delivery-platform + Postgres-security engineer.
**Approach:** TDD-first — pure validators and DB-guard refusal tests written and shown failing before
the implementation/migration that satisfies them.
**Pattern source (mirror exactly):** Slice 24 — `app/release/issues.py`,
`app/models/release_issue.py`, `app/repositories/release_issues.py`,
`migrations/versions/0023_release_issues.py`, `tests/test_release_issues.py`.
**Process note (learned, see memory `migration-edit-requires-db-drop`):** if `0024` is edited after a
first `make test-db`, run `make test-db-drop` before re-running, else alembic upgrade is a no-op and
the old DDL persists.

---

## 0. Goal & non-goal
- **Goal:** a deterministic, tenant-owned **release-candidate / release-binding store**
  (`release_candidates` + append-only `release_candidate_events` + append-only, freeze-locked
  `release_candidate_issue_bindings`, migration `0024`) supplying the *release-binding* half of A5
  gate #7, and creating the **future** `release_id` referent namespace.
- **Non-goal:** gate #7 must **never pass**; no completeness claim; no release approval/verdict/deploy;
  no retro-FK or validation of `risk_acceptance_records.release_id`; no findings/risk-acceptance
  binding; no HTTP API; no go-live; no LLM.

## 1. Files (create / modify)

| # | File | Action | Mirrors |
|---|---|---|---|
| 1 | `app/release/release_candidates.py` | **create** (pure validators) | `app/release/issues.py` |
| 2 | `app/models/release_candidate.py` | **create** | `app/models/release_issue.py` |
| 3 | `app/models/release_candidate_event.py` | **create** | `app/models/release_issue_event.py` |
| 4 | `app/models/release_candidate_issue_binding.py` | **create** | (new shape) |
| 5 | `app/models/__init__.py` | **modify** (register 3 models) | existing |
| 6 | `app/repositories/release_candidates.py` | **create** | `app/repositories/release_issues.py` |
| 7 | `migrations/versions/0024_release_candidates.py` | **create** (`down_revision="0023"`) | `0023` |
| 8 | `app/release/production_autonomy.py` | **modify** (gate #7 + `slice25.v1`) | current gate #7 |
| 9 | `app/repositories/production_autonomy.py` | **modify** (wire release-candidate counts) | current |
| 10 | `tests/test_release_candidates.py` | **create** (pure + `db`) | `tests/test_release_issues.py` |
| 11 | `tests/test_production_autonomy.py` | **modify** (gate #7 reason/context + `slice25.v1`) | existing |
| 12 | `tests/test_api.py` | **modify** (`production_autonomy` ruleset/reason) | existing |
| 13 | `CLAUDE.md` + `README.md` | **modify** | Slice-24 entries |

## 2. Pure module — `app/release/release_candidates.py` (D-RB-2/3)

```text
STATUSES          = (draft, frozen, superseded, canceled)
TERMINAL_STATUSES = (superseded, canceled)
_ALLOWED_TRANSITIONS = {(draft,frozen),(draft,canceled),(frozen,superseded),(frozen,canceled)}
REQUIRED_CREATE_FIELDS = (release_ref,)
```
- `InvalidReleaseCandidate(ValueError)`.
- `validate_new_candidate(record)`: `release_ref` present + non-empty; `title` optional (if present,
  must be a str). (status defaults `draft`; no other required fields.)
- `validate_transition(from_status, to_status)`: only the 4 pairs above; everything else (incl.
  `draft→superseded`, `frozen→draft`, terminal→anything, same→same) refused.

## 3. Models (D-RB-2/4/7)

**Direct tenant-FK convention (mirror Slice 24, `0023:126-130`,`160-164`):** all three new
tenant-owned tables carry a direct `tenant_id → tenants.id` (RESTRICT) FK in addition to their
composite FKs.

`app/models/release_candidate.py` — `ReleaseCandidate`, table `release_candidates`:
`id, tenant_id, project_id, release_ref, title (nullable), status (default 'draft'), frozen_at
(nullable), created_at (clock_timestamp), updated_at (clock_timestamp)`.
`__table_args__`:
- direct FK `tenant_id → tenants.id` RESTRICT;
- composite FK `(project_id, tenant_id) → projects(id, tenant_id)` RESTRICT;
- `UniqueConstraint("tenant_id","project_id","release_ref")` (the `release_ref` namespace);
- **`UniqueConstraint("id","tenant_id", name="uq_release_candidates_id_tenant")`** (the
  `release_candidate_events` FK target — mirrors Slice 23/24 event pattern);
- **`UniqueConstraint("id","project_id","tenant_id")`** (the `release_candidate_issue_bindings`
  FK target);
- `Index(tenant_id, project_id, status)`.

`app/models/release_candidate_event.py` — `ReleaseCandidateEvent`, table `release_candidate_events`:
`id, tenant_id, release_candidate_id, event_type, actor, created_at`;
- direct FK `tenant_id → tenants.id` RESTRICT;
- composite FK `(release_candidate_id, tenant_id) → release_candidates(id, tenant_id)` (uses the new
  `uq_release_candidates_id_tenant`).

`app/models/release_candidate_issue_binding.py` — `ReleaseCandidateIssueBinding`, table
`release_candidate_issue_bindings`: `id, tenant_id, project_id, release_candidate_id,
release_issue_id, created_at`.
`__table_args__` (**Option A — additive, no `release_issues` mutation**):
- direct FK `tenant_id → tenants.id` RESTRICT;
- FK `(release_candidate_id, project_id, tenant_id) → release_candidates(id, project_id, tenant_id)`
- FK `(release_issue_id, tenant_id) → release_issues(id, tenant_id)`
- `UniqueConstraint("tenant_id","release_candidate_id","release_issue_id")`
- `Index(tenant_id, release_candidate_id)`

`app/models/__init__.py` — import + export the 3 new classes.

## 4. Migration — `migrations/versions/0024_release_candidates.py` (D-RB-7; mirror `0023`)

`revision="0024"`, `down_revision="0023"`. Three tables + CHECKs + FKs + indexes + RLS **exactly as
the models in §3** — including (a) the direct `tenant_id → tenants.id` FK on **all three** tables,
(b) `release_candidates` carrying **both** `UNIQUE(id, tenant_id)` (`uq_release_candidates_id_tenant`,
the event FK target) **and** `UNIQUE(id, project_id, tenant_id)` (the binding FK target) plus
`UNIQUE(tenant_id, project_id, release_ref)`, (c) the event/binding composite FKs pointing at those
unique targets. `_PREDICATE` identical to `0023`. Grants: `release_candidates` → SELECT/INSERT/UPDATE, REVOKE
DELETE/TRUNCATE; `release_candidate_issue_bindings` + `release_candidate_events` → SELECT/INSERT,
REVOKE UPDATE/DELETE/TRUNCATE. ENABLE+FORCE RLS + `tenant_isolation` on all three.
CHECK: `status IN ('draft','frozen','superseded','canceled')`.

### 4.1 `release_candidates_guard()` BEFORE INSERT OR UPDATE
- **INSERT:** `status='draft'`; `frozen_at IS NULL`.
- **UPDATE — immutable cols** (`IS DISTINCT FROM`): `id, tenant_id, project_id, release_ref, title,
  created_at`.
- **UPDATE — same status** (`NEW.status IS NOT DISTINCT FROM OLD.status`): no field may change (incl.
  `frozen_at`, `updated_at`) — blocks out-of-band edits.
- **UPDATE — transition** (else): `(OLD.status, NEW.status)` must be one of the 4 allowed pairs
  (else "terminal/invalid transition"). Specifically:
  - entering `frozen` (`draft→frozen`): `NEW.frozen_at IS NOT NULL` (set on freeze) and
    `OLD.frozen_at IS NULL`.
  - any non-frozen transition (`draft→canceled`, `frozen→superseded`, `frozen→canceled`):
    `NEW.frozen_at IS NOT DISTINCT FROM OLD.frozen_at` (frozen_at unchanged).
- no DELETE/TRUNCATE (block triggers).

### 4.2 `release_candidate_issue_bindings_guard()` BEFORE INSERT
- look up the parent candidate: **must be `status='draft'`** (freeze-locks membership) — else raise.
- look up the referenced `release_issues` row: **`project_id = NEW.project_id`** — else raise
  (the FK to `release_issues(id, tenant_id)` can't enforce project match).
- append-only: block UPDATE/DELETE/TRUNCATE.

### 4.3 `release_candidate_events` — append-only block triggers (mirror `0023`).

`downgrade()` drops triggers/functions/indexes/tables + RLS in reverse.

## 5. Repository — `app/repositories/release_candidates.py` (D-RB-3/4/6; mirror Slice 24)

`ReleaseCandidateRepository(TenantScopedRepository)`:
- `create(*, project_id, payload, actor)` → `validate_new_candidate`; insert `status='draft'`;
  `_event("created")`; `_audit("release.candidate_created")`.
- `freeze(*, candidate_id, actor)` → `validate_transition(status,"frozen")`; set `status='frozen'`,
  `frozen_at=clock_timestamp()`, `updated_at`; `_event`/`_audit`.
- `supersede(*, candidate_id, actor)` / `cancel(*, candidate_id, actor)` → validated transition; set
  status (+`updated_at`); `_event`/`_audit`. (`cancel` allowed from `draft` or `frozen`.)
- `bind_issue(*, candidate_id, release_issue_id, actor)` → load candidate (for `project_id`); insert
  a binding row (the DB guard enforces draft + project match); `_event("issue_bound")`;
  `_audit("release.issue_bound")`.
- `get(candidate_id)`; `list_for_project(project_id)`.
- **A5 count helpers:**
  - `count_frozen(project_id)` → `status='frozen'`.
  - `latest_frozen(project_id)` → first row ordered **`frozen_at DESC, created_at DESC, id DESC`**.
  - `bound_open_issue_count(candidate_id)` / `bound_open_blocking_issue_count(candidate_id)` → JOIN
    `release_candidate_issue_bindings` → `release_issues` WHERE `status='open'` [AND `blocking`].
    `bound_open_unaccepted_blocking_issue_count` == blocking (open ⟹ unaccepted; documented
    equivalence, no fabricated distinction).
- `_event`/`_audit` mirror Slice 24. **Audit safe-metadata only**: `release_candidate_id, project_id,
  release_ref, status` (+ for bindings `release_issue_id`) — **never `title`/prose**.

## 6. A5 hook (D-RB-6)

### 6.1 `app/release/production_autonomy.py`
- `A5_RULESET_VERSION`: `slice24.v1` → **`slice25.v1`** (+ docstring).
- `evaluate_production_autonomy(...)` gains kwargs (defaults fail-closed): `frozen_release_candidate_count=0`,
  `latest_frozen_release_candidate_id=None`, `latest_frozen_release_ref=None`,
  `bound_open_issue_count=0`, `bound_open_blocking_issue_count=0`,
  `bound_open_unaccepted_blocking_issue_count=0`.
- Gate #7:
  ```python
  reason = ("no_issue_provenance" if frozen_release_candidate_count > 0
            else "no_issue_provenance_or_release_binding")
  gate7 = _insufficient(7, "approved_risk_acceptance_records", reason, {
      "active_risk_acceptance_count": active_risk_acceptance_count,
      "open_issue_count": open_issue_count,
      "open_blocking_issue_count": open_blocking_issue_count,
      "open_unaccepted_blocking_issue_count": open_unaccepted_blocking_issue_count,
      "frozen_release_candidate_count": frozen_release_candidate_count,
      "latest_frozen_release_candidate_id": latest_frozen_release_candidate_id,
      "latest_frozen_release_ref": latest_frozen_release_ref,
      "bound_open_issue_count": bound_open_issue_count,
      "bound_open_blocking_issue_count": bound_open_blocking_issue_count,
      "bound_open_unaccepted_blocking_issue_count": bound_open_unaccepted_blocking_issue_count,
  })
  ```
  Status stays `insufficient_evidence` — **gate #7 never passes**. No other gate changes. (No `title`
  in context.)

### 6.2 `app/repositories/production_autonomy.py`
- Instantiate `ReleaseCandidateRepository`; compute `count_frozen`; if a `latest_frozen` exists, read
  its id/`release_ref` + bound counts; pass all into `evaluate_production_autonomy`. Counts come from
  `release_candidates`/bindings only.

## 7. Tests — TDD-first

### 7.1 `tests/test_release_candidates.py`
**Pure (Docker-free):** `validate_new_candidate` (missing/empty `release_ref` ⇒ raise; title optional);
`validate_transition` (the 4 allowed pairs pass; `draft→superseded`, `frozen→draft`,
terminal→anything, same→same raise); `STATUSES`/`TERMINAL_STATUSES` constants.

**DB-backed (`@pytest.mark.db`):**
1. create draft (status=draft, frozen_at NULL); freeze (status=frozen, frozen_at set); supersede;
   cancel-from-draft; cancel-from-frozen — happy paths + events + audit.
2. bind issue while draft (succeeds, event recorded); **counts** `count_frozen`,
   `bound_open_issue_count`/`bound_open_blocking_issue_count`/`...unaccepted...` over a seeded mix.
3. `latest_frozen` ordering (`frozen_at DESC, created_at DESC, id DESC`) across 2+ frozen candidates.
4. **audit safe-metadata**: payload has ids/release_ref/status, **no `title`/prose**.
5. RLS / cross-tenant: tenant B can't see/bind tenant-A candidates.
6. **Direct-SQL guard refusals:**
   - insert with `status<>'draft'` ⇒ raise; insert with `frozen_at` non-NULL ⇒ raise;
   - `updated_at`-only update (status unchanged) ⇒ raise;
   - terminal re-transition (e.g. `superseded→canceled` not allowed; `canceled→*`) ⇒ raise;
   - `draft→frozen` with `frozen_at` left NULL ⇒ raise;
   - **bind when candidate not `draft`** (freeze then raw-insert binding) ⇒ raise;
   - **bind cross-project** (issue from another project, raw insert) ⇒ raise (project-match trigger);
   - **dup binding** (same candidate+issue) ⇒ unique violation;
   - bind referencing a **cross-tenant** issue ⇒ raise (composite FK);
   - **DELETE** `release_candidates` ⇒ raise; **UPDATE/DELETE** `release_candidate_issue_bindings`
     ⇒ raise; **UPDATE/DELETE** `release_candidate_events` ⇒ raise;
   - **TRUNCATE** each of the three tables ⇒ raise.
7. **catalog/grants/RLS/constraints**: `release_candidates` = {SELECT,INSERT,UPDATE}; bindings +
   events = {SELECT,INSERT}; all three `relrowsecurity`+`relforcerowsecurity` true; verify
   `release_candidates` carries the three unique constraints (`uq_release_candidates_id_tenant`,
   `(id,project_id,tenant_id)`, `(tenant_id,project_id,release_ref)`) via `pg_constraint`.

### 7.2 `tests/test_production_autonomy.py` (modify)
- Pure: with `frozen_release_candidate_count=0` ⇒ gate #7 reason
  `no_issue_provenance_or_release_binding`; with `>0` ⇒ `no_issue_provenance`; both
  `insufficient_evidence`, gate #7 in unmet set, `a5_satisfied` False.
- Context carries the new release-binding keys (+ Slice-24 keys).
- `ruleset_version == "slice25.v1"`.
- DB: `test_db_gate7_reads_release_candidate_counts` — seed issues + a frozen candidate with bound
  issues; assert reason narrows to `no_issue_provenance`, context counts match, still never passes.
- Unchanged: only gate #1 can pass; PARTIAL/SOURCELESS sets; go-live always false; compute-on-read.

### 7.3 `tests/test_api.py` (modify)
- `production_autonomy` endpoint: `ruleset_version == "slice25.v1"`; gate #7 reason matches the API
  fixture state (no frozen release seeded ⇒ `no_issue_provenance_or_release_binding`) + the new
  context keys present. (Auth/cross-tenant/read-only assertions unchanged.)

## 8. Docs (D-RB-7)
- `CLAUDE.md`: add the `release_candidates` What-exists entry + `0024` migrations entry; update the
  production-autonomy bullet (gate #7 narrow + `slice25.v1`); status line "Slice 25 … In progress.";
  test-files list (+`test_release_candidates.py`); test counts from **actual** `make test`/`make
  test-db` output (no invented numbers — §2.1).
- `README.md`: add a "Release candidates / bindings" section; update the production-autonomy gate #7
  wording + `slice25.v1`.

## 9. Acceptance criteria (evidence-decided)
- `make fmt`/`ruff check .` clean (format only my files to avoid unrelated churn).
- `make test` (Docker-free) green incl. new pure tests; `make test-db` green incl. all §7.1 guard
  refusals + §7.2/§7.3 gate-#7 changes (run on a **fresh** DB — `make test-db-drop` first since `0024`
  is new/edited).
- `alembic upgrade head` → `downgrade -1` → `upgrade head` round-trips cleanly (`0024` reversible).
- Gate #7 demonstrably **never passes**; reason narrows to `no_issue_provenance` only when a frozen
  candidate exists; `can_go_live_autonomously` false everywhere.
- No change to existing tables (esp. `release_issues`); `risk_acceptance_records.release_id` untouched.
- Record actual passing test counts in `CLAUDE.md` from real output.

## 10. Risk / reversibility
- **Additive only** (one migration, three new tables, two modified Python modules + tests + docs).
  `downgrade()` fully drops the slice. No existing table altered.
- **Blast radius:** the only change to existing surface is gate #7's `reason`/`context` + `ruleset_version`
  on the read-only `…/production_autonomy` endpoint — still always not-satisfied, still no go-live;
  consumers keying on `status` unaffected (`insufficient_evidence`).
- **Honesty preserved:** binding ≠ completeness; gate #7 stays fail-closed.

## 11. Notes for the coordinator (non-blocking)
- `bound_open_unaccepted_blocking_issue_count` equals `bound_open_blocking_issue_count` under the
  lifecycle (`open` ⟹ not accepted); implemented as a distinct method per the gate-context contract,
  equivalence documented (no fabricated distinction) — same pattern accepted in Slice 24.
- `latest_frozen_release_ref` is included in gate context as a human **identifier** (not prose);
  `title` is excluded from both context and audit.

---
**Awaiting PLAN approval. On approval:** branch `feat/slice25-release-binding` off `main`, execute
TDD-first in §1 order (tests → pure → models → migration → repo → A5 hook → wire → docs), atomic
commits per github-flow. No implementation begins until then.
