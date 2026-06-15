# Slice 24 — Open-issue / blocker store (A5 gate #7) — PLAN v1

**Status:** APPROVED FOR EXECUTION pending the standing gate — **no branch / no code / no migration /
no tests until this PLAN is approved.** Rulings D-OI-1..8 are binding (see
`.planning/SLICE-24-OPEN-ISSUES-DISCUSSION.md`), with the coordinator's required refinements folded in
below.
**Base:** `main` @ `d16341f` (clean; only the intentional `.planning/HANDOFF.json` drift).
**Migration head:** `0022` → new head **`0023`** (verified: `0022_release_findings.py` is current).
**Persona:** senior delivery-platform / release-governance + Postgres-security engineer.
**Approach:** TDD-first — pure validators and DB-guard refusal tests are written and shown failing
before the implementation/migration that satisfies them.
**Pattern source (mirror exactly):** Slice 23 — `app/release/findings.py`,
`app/models/release_finding.py`, `app/models/release_finding_event.py`,
`app/repositories/release_findings.py`, `migrations/versions/0022_release_findings.py`,
`tests/test_release_findings.py`.

---

## 0. Goal & non-goal (one line each)
- **Goal:** a deterministic, tenant-owned **open-issue/blocker store** (`release_issues` +
  append-only `release_issue_events`) that gives A5 gate #7 a real evidence *store* and gives the
  Slice-22 risk-acceptance `issue_id` a real referent — **without** issue provenance, release
  binding, or go-live.
- **Non-goal:** gate #7 must **never pass** this slice; no scanner/reviewer/CI execution; no
  findings→issues bridge; no release entity; no HTTP API; no request-auth; no readiness impact.

## 1. Files (create / modify)

| # | File | Action | Mirrors |
|---|---|---|---|
| 1 | `app/release/issues.py` | **create** (pure validators) | `app/release/findings.py` |
| 2 | `app/models/release_issue.py` | **create** | `app/models/release_finding.py` |
| 3 | `app/models/release_issue_event.py` | **create** | `app/models/release_finding_event.py` |
| 4 | `app/models/__init__.py` | **modify** (register 2 models) | existing pattern |
| 5 | `app/repositories/release_issues.py` | **create** | `app/repositories/release_findings.py` |
| 6 | `migrations/versions/0023_release_issues.py` | **create** (`down_revision="0022"`) | `0022_release_findings.py` |
| 7 | `app/release/production_autonomy.py` | **modify** (gate #7 + ruleset) | current gate #7 (`:141-144`) |
| 8 | `app/repositories/production_autonomy.py` | **modify** (wire counts) | current (`:62-81`) |
| 9 | `tests/test_release_issues.py` | **create** (pure + `db`) | `tests/test_release_findings.py` |
| 10 | `tests/test_production_autonomy.py` | **modify** (gate #7 reason/context + `slice24.v1`) | existing |
| 11 | `CLAUDE.md` + `README.md` | **modify** (status + "What exists") | Slice-23 entries |

## 2. Pure module — `app/release/issues.py` (D-OI-2/3/4)

```text
ISSUE_CATEGORIES = (security, shortcut, test_or_acceptance, cost, deployment,
                    rollback, monitoring, evidence, approval, other)   # D-OI-2 (no 'blocker')
SEVERITIES       = (low, medium, high, critical)                       # reuse
STATUSES         = (open, resolved, accepted, superseded)             # D-OI-3 (no false_positive)
TERMINAL_STATUSES= (resolved, accepted, superseded)
_ALLOWED_TRANSITIONS = {(open, t) for t in TERMINAL_STATUSES}          # one-way from open
HARD_REFUSAL_CATEGORIES  ← imported from app.release.risk_acceptance   # single source of truth
REQUIRED_CREATE_FIELDS   = (issue_category, severity, blocking, summary, source)
```

Functions (pure, fail-closed, raise `InvalidIssue(ValueError)`):
- `is_critical(severity) -> bool`
- `is_hard_blocker(severity, blocking_category) -> bool` → `severity=="critical" or
  blocking_category in HARD_REFUSAL_CATEGORIES` (**D-OI-4 refinement**).
- `validate_new_issue(record)`:
  - all `REQUIRED_CREATE_FIELDS` present + non-empty (`blocking` must be a real bool, not empty);
  - `issue_category ∈ ISSUE_CATEGORIES`; `severity ∈ SEVERITIES`;
  - `issue_category=="other"` ⇒ non-empty `summary` **and** `detail` (D-OI-2);
  - **critical ⇒ blocking** (`severity=="critical" and blocking is not True` ⇒ refuse) — the
    fail-closed "critical implies blocking semantics" refinement.
- `validate_transition(from_status, to_status)`: only `open → {resolved, accepted, superseded}`.

*Pure module does NOT decide acceptance usability (that needs DB state) — it only blocks critical/hard
acceptance structurally; the repository + DB guard own the usable-record check.*

## 3. Models (D-OI-8)

`app/models/release_issue.py` — `ReleaseIssue`, table `release_issues`, columns:
`id, tenant_id, project_id, issue_category, severity, blocking (Boolean, not null),
blocking_category (Text, nullable), summary (not null), detail (nullable), source (not null),
source_provenance (default 'caller_supplied_unverified'), status (default 'open'),
risk_acceptance_record_id (UUID, nullable), resolution_note (nullable), resolved_at (nullable),
resolved_by (nullable), created_at (clock_timestamp), updated_at (clock_timestamp)`.
`__table_args__` (mirror `release_finding.py:32-54`):
- composite FK `(project_id, tenant_id) → projects(id, tenant_id)` `ondelete=RESTRICT`;
- **nullable composite FK** `(risk_acceptance_record_id, tenant_id) →
  risk_acceptance_records(id, tenant_id)` `ondelete=RESTRICT` (D-OI-5; target `UNIQUE(id, tenant_id)`
  confirmed to exist);
- `UniqueConstraint("id", "tenant_id")`;
- `Index("ix_release_issues_tenant_project_status", tenant_id, project_id, status)`.

`app/models/release_issue_event.py` — `ReleaseIssueEvent`, table `release_issue_events`:
`id, tenant_id, issue_id, event_type, actor, created_at` (mirror `release_finding_event.py`),
composite FK `(issue_id, tenant_id) → release_issues(id, tenant_id)`.

`app/models/__init__.py` — import + export `ReleaseIssue`, `ReleaseIssueEvent`.

## 4. Migration — `migrations/versions/0023_release_issues.py` (D-OI-8; mirror `0022`)

`revision="0023"`, `down_revision="0022"`. Two tables + CHECKs + FKs + indexes exactly as the models;
`_PREDICATE` RLS clause identical to `0022:25`. Grants: `release_issues` → SELECT/INSERT/UPDATE to
`uaid_app`, REVOKE DELETE/TRUNCATE; `release_issue_events` → SELECT/INSERT, REVOKE
UPDATE/DELETE/TRUNCATE. ENABLE+FORCE RLS + `tenant_isolation` policy on both.

CHECKs: `issue_category IN (…10…)`, `severity IN (low,medium,high,critical)`,
`status IN (open,resolved,accepted,superseded)`.

### 4.1 `release_issues_guard()` BEFORE INSERT OR UPDATE (authoritative backstop)
**INSERT invariants** (refinements folded in):
- `status='open'`;
- `source_provenance='caller_supplied_unverified'`;
- `risk_acceptance_record_id`, `resolution_note`, `resolved_at`, `resolved_by` **all NULL**;
- `issue_category` valid (CHECK also covers it);
- `issue_category='other'` ⇒ non-empty `summary` **and** `detail`;
- **`severity='critical'` ⇒ `blocking = true`** (critical-implies-blocking, fail-closed).

**UPDATE — immutable columns** (`IS DISTINCT FROM` set, mirror `0022:27-30`):
`id, tenant_id, project_id, issue_category, severity, blocking, blocking_category, summary, detail,
source, source_provenance, created_at`.

**UPDATE — same status unchanged** (mirror `0022:163-171`): if `NEW.status IS NOT DISTINCT FROM
OLD.status`, then **no** field may change — incl. `risk_acceptance_record_id, resolution_note,
resolved_at, resolved_by, updated_at` (blocks `updated_at`-only / out-of-band edits).

**UPDATE — transition** (`OLD.status='open'` required; else "terminal status cannot transition"):
- target ∈ `{resolved, accepted, superseded}`;
- **`accepted` path:**
  - refuse if `OLD.severity='critical' OR OLD.blocking_category IN (…HARD_REFUSAL…)` →
    `'critical/hard-blocker issues cannot be accepted'` (**D-OI-4 at DB layer**);
  - `NEW.risk_acceptance_record_id IS NOT NULL` (required — accepted *always* needs a record,
    D-OI-5 refinement);
  - `resolution_note/resolved_at/resolved_by` must be NULL;
  - **usable-record check** (mirror `0022:191-198`): `SELECT 1 FROM risk_acceptance_records r
    WHERE r.id=NEW.risk_acceptance_record_id AND r.tenant_id=NEW.tenant_id AND
    r.project_id=NEW.project_id AND r.status='active' AND r.expiry_date>=CURRENT_DATE AND
    r.blocking_category IS NULL AND r.issue_id = NEW.id::text` → NULL ⇒
    `'no usable risk-acceptance record for this issue'`;
- **`resolved`/`superseded` path:** `NEW.risk_acceptance_record_id` must be NULL (mirror
  `0022:202-205`); the repo sets `resolution_note/resolved_by/resolved_at`.

### 4.2 Block triggers (mirror `0022:221-269`)
- `release_issues`: BEFORE DELETE (row) + BEFORE TRUNCATE (stmt) → raise.
- `release_issue_events`: BEFORE UPDATE OR DELETE (row) + BEFORE TRUNCATE (stmt) → raise
  (append-only).

`downgrade()` drops triggers/functions/indexes/tables + RLS in reverse (mirror `0022:284-308`).

## 5. Repository — `app/repositories/release_issues.py` (D-OI-3/5; mirror `release_findings.py`)

`ReleaseIssueRepository(TenantScopedRepository)`:
- `create(*, project_id, payload, actor)` → `validate_new_issue(payload)`; insert `status='open'`;
  `_event(row,"created",actor)`; `_audit(row,"release.issue_created",actor)`.
- `resolve(*, issue_id, resolution_note, resolved_by, actor)` → `_resolve_like("resolved", …)`.
- `supersede(*, issue_id, resolution_note, resolved_by, actor)` → `_resolve_like("superseded", …)`.
- `accept(*, issue_id, risk_acceptance_record_id, actor)`:
  - `validate_transition(row.status,"accepted")`;
  - **repository-layer hard-block** (defense in depth): `if is_hard_blocker(row.severity,
    row.blocking_category): raise InvalidIssue("critical/hard-blocker issues cannot be accepted")`;
  - set `status='accepted'`, `risk_acceptance_record_id=…`, `updated_at=clock_timestamp()`; flush
    (DB guard re-validates usability); `_event("accepted")`; `_audit("release.issue_accepted")`.
- `get(issue_id)` → tenant-scoped `scalar_one_or_none`.
- **Counts for gate #7 (D-OI-7):**
  - `count_open(project_id)` → `status='open'`;
  - `count_open_blocking(project_id)` → `status='open' AND blocking=true`;
  - `count_open_unaccepted_blocking(project_id)` → `status='open' AND blocking=true`.
    *(Note, surfaced honestly: under the Slice-24 lifecycle `open ⟹ not accepted`, so this equals
    `count_open_blocking`. Implemented as a separate method per the binding ruling; the name documents
    intent and stays correct if a future slice adds a non-terminal "acknowledged" state. No fake
    distinction is claimed.)*
- `_resolve_like`, `_get_or_raise`, `_event`, `_audit` mirror `release_findings.py:114-162`.
  **Audit = safe metadata only**: `release_issue_id, project_id, issue_category, severity, blocking,
  status` — **never** `summary/detail/resolution_note/blocking_category prose`.

## 6. A5 hook (D-OI-7)

### 6.1 `app/release/production_autonomy.py`
- Bump `ruleset_version`: `slice23.v1` → **`slice24.v1`** (+ module docstring).
- `evaluate_production_autonomy(...)` gains kwargs (default 0, fail-closed):
  `open_issue_count, open_blocking_issue_count, open_unaccepted_blocking_issue_count`.
- Gate #7 changes reason + context (keep `active_risk_acceptance_count`):
  ```python
  gate7 = _insufficient(
      7, "approved_risk_acceptance_records",
      "no_issue_provenance_or_release_binding",
      {
          "active_risk_acceptance_count": active_risk_acceptance_count,
          "open_issue_count": open_issue_count,
          "open_blocking_issue_count": open_blocking_issue_count,
          "open_unaccepted_blocking_issue_count": open_unaccepted_blocking_issue_count,
      },
  )
  ```
  Status stays `insufficient_evidence` — **gate #7 never passes**. No other gate changes.

### 6.2 `app/repositories/production_autonomy.py`
- Instantiate `ReleaseIssueRepository`; pass the three counts into `evaluate_production_autonomy`
  (mirror the Slice-23 findings wiring at `:65-80`). Counts come from `release_issues` **only**
  (D-OI-6 — no double-count with `release_findings`).

## 7. Tests — TDD-first

### 7.1 `tests/test_release_issues.py`
**Pure (Docker-free)** — written first, shown failing:
- valid issue per `issue_category` value; each `REQUIRED_CREATE_FIELDS` missing/empty ⇒ `InvalidIssue`;
- bad `issue_category` / bad `severity` ⇒ refuse;
- `issue_category='other'` without `detail`/`summary` ⇒ refuse;
- **critical without blocking ⇒ refuse** (critical-implies-blocking);
- `validate_transition`: only `open→{resolved,accepted,superseded}`; every other pair refused;
- `is_hard_blocker`: critical ⇒ True; each `HARD_REFUSAL_CATEGORIES` ⇒ True; benign ⇒ False.

**DB-backed (`@pytest.mark.db`)** — store, RLS, append-only, audit, and the **direct SQL guard
refusal** suite (raw `text()` against the guard, mirror `test_release_findings.py`):
1. create→resolve / create→supersede / create→accept (happy paths, events + audit recorded);
2. **bad insert status** (`status<>'open'`) ⇒ guard raises;
3. **`other` without detail** on insert ⇒ raises;
4. **resolution/acceptance metadata on insert** (`risk_acceptance_record_id`/`resolution_note`/
   `resolved_at`/`resolved_by` not NULL) ⇒ raises;
5. **critical-implies-blocking** insert (`severity='critical', blocking=false`) ⇒ raises;
6. **`updated_at`-only update** (status unchanged) ⇒ raises;
7. **terminal re-transition** (e.g. resolved→accepted) ⇒ raises;
8. **critical accept** (critical/hard-blocker → accepted) ⇒ raises (repo *and* direct SQL);
9. **accept without record** (`risk_acceptance_record_id` NULL) ⇒ raises;
10. **accept with unusable record** — one case each: expired / non-active / record has
    `blocking_category` / wrong project / `issue_id != issue.id` / cross-tenant ⇒ raises;
11. **accept with a usable record** ⇒ succeeds;
12. **DELETE / TRUNCATE** on `release_issues` ⇒ raises; **UPDATE/DELETE/TRUNCATE** on
    `release_issue_events` ⇒ raises;
13. **RLS / cross-tenant**: a second tenant cannot see/accept tenant-A issues;
14. **audit safe-metadata**: the audit payload contains ids/issue_category/severity/blocking/status and
    **none** of summary/detail/resolution prose;
15. **counts**: `count_open`, `count_open_blocking`, `count_open_unaccepted_blocking` over a seeded
    mix (open blocking, open non-blocking, accepted, resolved).

### 7.2 `tests/test_production_autonomy.py` (modify)
- Gate #7 reason is now `insufficient_evidence:no_issue_provenance_or_release_binding`; status still
  `insufficient_evidence`; **gate #7 still in the unmet set** (a5 not satisfied; go-live false).
- Gate #7 `context` carries the three new counts + `active_risk_acceptance_count`; counts reflect
  seeded `release_issues`.
- `ruleset_version == "slice24.v1"`.
- Unchanged: only gate #1 can pass; `PARTIAL`/`SOURCELESS` gate sets; `can_go_live_autonomously`
  always false; compute-on-read no-writes; cross-tenant no-leak.

## 8. Docs (D-OI-8)
- `CLAUDE.md`: add the `app/release/issues.py` + models + repo + `0023` entries (mirror the Slice-23
  bullets); update the production-autonomy bullet (gate #7 reason + `slice24.v1`); status line "Slice
  24 … In progress." Update test counts after the run (don't pre-write numbers — fill from actual
  `make test` / `make test-db` output).
- `README.md`: mirror the Slice-23 one-liner addition.

## 9. Acceptance criteria (evidence-decided)
- `make fmt` clean; `make test` (Docker-free) green incl. the new pure tests; `make test-db` green
  incl. all §7.1 DB-guard refusal tests + §7.2 gate-#7 changes.
- `alembic upgrade head` then `downgrade -1` then `upgrade head` round-trips cleanly (0023 reversible).
- Gate #7 demonstrably **never passes**; `can_go_live_autonomously` false in every test.
- No change to `readiness_reports` / the R0–R5 ladder; no new HTTP route.
- Record actual passing test counts in `CLAUDE.md` from real output (no invented numbers — §2.1).

## 10. Risk / reversibility
- **Additive only** (one new migration, two new tables, two modified Python modules + tests + docs).
  `downgrade()` fully drops the slice. No existing table altered. No data migration.
- **Blast radius:** the only behavioral change to existing surface is gate #7's `reason`/`context`
  string + `ruleset_version` on the read-only `/api/projects/{id}/production_autonomy` endpoint —
  still always not-satisfied, still no go-live. Consumers keying on `status` are unaffected (still
  `insufficient_evidence`).
- **Honest dependency reality preserved:** the store cannot prove issue completeness or release
  binding, so gate #7 stays fail-closed.

## 11. Interpretation rulings (SETTLED — applied in this v1)
- **Point 1 — critical ⇒ blocking (strong/fail-closed reading, APPROVED):** `severity='critical' AND
  blocking=false` is **refused at both** the pure-validator (§2) **and** the DB-guard INSERT (§4.1).
  Critical rows cannot masquerade as non-blocking. No relaxation.
- **Point 2 — `open_unaccepted_blocking_issue_count` (literal, APPROVED):** implemented literally
  (`status='open' AND blocking=true`); it may equal `open_blocking_issue_count` under the Slice-24
  lifecycle, and that equivalence is documented honestly (§5). **Not** redefined to mean "hard
  blockers" in this slice.

---
**Awaiting PLAN approval. On approval:** branch `feat/slice24-open-issues` off `main`, then execute
TDD-first in the file order of §1 (tests → pure module → models → migration → repo → A5 hook → wire →
docs), committing atomically per the github-flow skill. No implementation begins until then.
