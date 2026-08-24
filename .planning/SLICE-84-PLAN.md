# Slice 84 — F-021 test integrity: five load-bearing regressions

**Seats.** PLANNER = **Claude Opus, substituting for the owner-named "Claude Fable 5" seat.** That
slug is not an addressable model in this environment; this document was written by Claude Opus and
the substitution is recorded here rather than silently absorbed. BUILDER = **Cursor Grok 4.6 Extra
High**, which implements exactly this approved plan and never edits it. REVIEWER = **GPT-5.6 Sol**,
sole approval authority on plan and code, probe-backed verdicts only.

**Version.** **v2** — issued after one **Sol REJECT** of v1.1 (five defects, **all accepted, none
argued down**). Consecutive plan REJECT count for this item: **1**. A third consecutive REJECT swaps
seats (Sol implements, Opus reviews). Every v1/v1.1 technical claim Sol did not reject is retained
unchanged; the five corrections are marked **(Sol defect N)** at the point of change and summarised
in §9.

**Finding.** **F-021** (`.planning/FINAL-AUDIT-REPORT.md:745`, evidence `:869-870`, live positive
control `:1134-1140`). **Slice.** **84** — Wave 1, the **first numbered remediation slice**
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:733-734,743`).

**Base.** `origin/main` = `d0f38fd` (Wave 0, PRs #118/#119, docs-only). The audited commit was
`50bc055`; F-021's code and tests are unchanged between them.

**Alembic.** Live head is **0062** (`migrations/versions/0062_enterprise_admin.py`,
`revision="0062"`). **This slice adds no migration and head stays 0062.** F-021 is not a missing
production guard: every guard this slice targets already exists and already raises the exact string
required. The defect is that the tests can pass on a neighbouring constraint, on invalid setup, or
without ever reaching the named branch. **Do not add a migration. Do not change any production
guard, grant, trigger, or repository.**

**Frozen.** `app/release/production_autonomy.py`, `app/intake/readiness.py`, `.github/workflows/`,
`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`, and
`.planning/FINAL-AUDIT-REPORT.md` are not touched. `can_go_live_autonomously` stays the literal
`False`; A5 stays `slice54.v1`; readiness stays `slice20.v1`.

**Never** re-grant a privilege to make a test pass. **Never** weaken, skip, `xfail`, or delete a
test. **No** `pytest.raises(Exception)` without `match=`.

---

## 0. What this slice is / is not

**Is:** a test-integrity slice. It makes five already-existing production refusals *provably* the
thing each test measures, by (a) executing the operation that actually reaches the named guard,
(b) asserting that guard's exact message and SQLSTATE, (c) independently asserting the neighbouring
refusal so the two can never be confused, and (d) adding a mutation probe that disables **only** the
targeted guard and shows the test then fails.

**Is not**, and must not drift into:

| Not this slice | Owner disposition |
|---|---|
| F-002 approval/override authority is bypassable | Wave 3, Slice 65 |
| F-004 `approval_events` / `tool_calls` / `agent_tool_allowlist` accept owner UPDATE/DELETE/TRUNCATE | **parked/unassigned — do not expand into it** (audit `:728,:1124-1128`) |
| F-005 runtime role self-stamps trusted source graphs | Slice 68 |
| F-003 runtime role can set another tenant's GUC | Slice 66 |
| F-017 full-repository pyright (3050 errors) | Slice 80 |
| F-020 writer concurrency | Slice 83 (next) |

No production code changes. No new table, column, trigger, grant, CHECK, HTTP route, LLM call, or
broker change.

### 0.1 Grounding facts (re-read on `d0f38fd` while writing this plan)

1. **`cost_events` truncate guard.** Function `public.cost_events_block_mutation()` raises
   `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)`
   (`migrations/versions/0008_cost_ledger.py:152`); triggers `cost_events_no_update_delete`
   (BEFORE UPDATE OR DELETE, row) and `cost_events_no_truncate` (BEFORE TRUNCATE, statement) at
   `:157-170`. Runtime grants are `SELECT, INSERT` only (`:183-184`), so a `uaid_app`
   UPDATE/DELETE is `permission denied for table cost_events`, never the trigger.
2. **The neighbouring FK.** `cost_forecast_ledger_event_refs` carries
   `FOREIGN KEY (cost_event_id, project_id, tenant_id) → cost_events(...)`
   (`migrations/versions/0050_cost_forecasts.py:285`), and PostgreSQL's FK check for a
   non-`CASCADE` TRUNCATE runs before the BEFORE-TRUNCATE triggers. Audit live positive control
   (`.planning/FINAL-AUDIT-REPORT.md:1134-1140`): `TRUNCATE ... CASCADE` returned the trigger
   message; plain `TRUNCATE` "first hit a foreign key from `cost_forecast_ledger_event_refs`".
3. **The cascade discriminator.** `cost_forecast_ledger_event_refs` has its own blocker whose
   message is `cost_forecast_ledger_event_refs is append-only` (`0050:36`) — textually distinct
   from the `cost_events` message. That distinctness is what makes the R1 mutation probe readable.
4. **Global skill guards.** `public.{table}_block_dml()` raises
   `{table} is append-only / immutable (no UPDATE/DELETE/TRUNCATE)` for each of the three global
   tables (`migrations/versions/0037_skill_matching.py:293-312`); triggers `{table}_no_truncate` /
   `{table}_no_update_delete`. `skills` and `agent_skill_capabilities` are FK-referenced by
   `agent_provided_skills` (`0037:143-145`), so plain TRUNCATE stops at the FK for those two;
   `agent_provided_skills` has no dependent and reaches its trigger directly.
5. **Intended global ACL — and what the runtime role actually hits (corrected in v2, Sol defect 1).**
   `REVOKE ALL ON {table} FROM PUBLIC; GRANT SELECT ON {table} TO uaid_app` (`0037:315-317`):
   SELECT-only. On the live database, `uaid_app` running `INSERT INTO skills DEFAULT VALUES` is
   refused with SQLSTATE **`42501`**, `permission denied for table skills` — PostgreSQL evaluates the
   table ACL **before** NOT NULL, so the runtime role never reaches `23502`. **v1.1 claimed the
   runtime role hits NOT NULL. That was wrong and is withdrawn.** The masking defect is therefore
   *not* which error `uaid_app` gets; it is that `tests/test_skills.py:373-387` wraps the statement
   in an **unmatched** `pytest.raises(Exception)`, so that test would keep passing unchanged if
   INSERT were ever granted — it would then simply pass on the `23502` NOT NULL error instead. The
   `23502` path is real and is demonstrated **as admin** (admin holds INSERT and therefore does reach
   `null value in column "key" of relation "skills" violates not-null constraint`).
6. **Structurally valid global-table INSERT shapes, and the collision that forbids reusing `sk_ctx`
   (corrected in v2, Sol defect 4).** `skills(key, category)` with
   `key ~ '^[a-z][a-z0-9_]{1,63}$'` and `category` in the 27 seeded values (`0037:68-87`);
   `agent_skill_capabilities(blueprint_id, cost_latency_class)` with the class in
   `('low','medium','high')` and `provided_tools`/`domains` defaulting to `'[]'` (`0037:90-121`);
   `agent_provided_skills(capability_id, skill_id, can_review)` (`0037:125-148`), which carries
   **`UNIQUE (capability_id, skill_id)` = `uq_aps_capability_skill`** (`0037:147`). **v1.1 claimed
   all three valid rows could be built from `sk_ctx`'s `cap` and `skill`. That was wrong and is
   withdrawn:** `sk_ctx` already inserts exactly that pair (`tests/test_skills.py:334-352`), and live
   rows show `existing_pair_count = 1`, so the admin shape control would fail on
   `uq_aps_capability_skill`, not succeed. The probes therefore **mint their own parents** (§3.2):
   a fresh `skills.key` of the form `s84_` + `uuid4().hex` (36 chars, matches the key regex, cannot
   collide with `uq_skills_key`), a fresh `agent_skill_capabilities` row with an explicit new UUID id
   over `sk_ctx`'s **existing** blueprint `bp`, and the `agent_provided_skills` pair over those two
   new ids — with `SELECT count(*) = 0` for that pair asserted before both probes.
7. **Critical finding acceptance, repository branch.**
   `ReleaseFindingRepository.accept` raises `InvalidFinding("critical findings cannot be accepted")`
   at `app/repositories/release_findings.py:73-74`, **before any DB access**. The current test never
   calls it (`tests/test_release_findings.py:333-341`); it wraps `_make_ra_record` instead.
8. **ROOT CAUSE of the `_make_ra_record` failure on a critical finding — named, as required.**
   `RiskAcceptanceRepository._require_subject_binding` requires, for
   `subject_type='release_finding'`, that the Slice-47 bridged issue have
   `ReleaseIssue.blocking_category IS NULL` **and** `ReleaseIssue.severity != 'critical'`
   (`app/repositories/risk_acceptance.py:120-123`). The Slice-47 bridge mirrors the finding's
   severity onto the issue, so a **critical** finding's bridged issue is critical, the count is `0`,
   and `create` raises `InvalidRiskAcceptance("release/subject binding is not exact")` at
   `app/repositories/risk_acceptance.py:142-143`. The same predicate exists in the DB guard at
   `migrations/versions/0046_issue_provenance.py:116-122`. **A usable risk-acceptance record for a
   critical finding is structurally impossible.** The workaround in §3.3 is therefore mandatory, not
   optional.
9. **Findings acceptance guard.** `release_findings_guard()` (trigger `release_findings_guard`,
   `migrations/versions/0022_release_findings.py:216-219`) checks
   `r.tenant_id / r.project_id / r.status='active' / r.expiry_date>=CURRENT_DATE /
   r.blocking_category IS NULL / r.issue_id = NEW.id::text` and raises
   `release_findings: no usable risk-acceptance record for this finding` (`0022:191-200`). The
   additive Slice-47 trigger `release_findings_slice47_subject_guard`
   (`0046:394-425`) raises `release_findings: accepted record subject kind must be release_finding`.
   PostgreSQL fires BEFORE-ROW triggers in trigger-name order, so `release_findings_guard` fires
   first.
10. **Issues acceptance guard.** `release_issues_guard()` raises
    `release_issues: no usable risk-acceptance record for this issue` (`0046:339-342`) using the
    Slice-47 binding-aware query at `0046:240-257`.
11. **Cross-tenant risk-acceptance INSERT cannot reach RLS on the plain path.** The BEFORE-INSERT
    trigger `risk_acceptance_records_guard` runs before RLS `WITH CHECK`, and its binding sub-selects
    are themselves RLS-filtered by the caller's GUC (`0046:79-122`, `:133-147`). With `GUC=t2` and
    `tenant_id=t1` the guard cannot see t1's frozen candidate, so it raises
    `risk_acceptance_records: release/subject binding is not exact` (`0046:120-122`) **before**
    PostgreSQL evaluates the RLS policy. See OD-3.
12. **Mutation helper exists.** `set_trigger(session, table, name, *, enabled)` at
    `tests/learning_support.py:386-389` and an equivalent at `tests/admin_support.py:341-344`. Both
    take a session; the Slice-84 probes need a committed admin-engine toggle with guaranteed
    restore, so §1 adds one narrow helper rather than bending either existing one. Precedent for the
    admin-engine disable/restore pattern: `tests/test_evidence_packs.py:779-796`.
13. **Fixtures available.** `cost_ctx` (`tests/test_cost.py:96-130`), `sk_ctx`
    (`tests/test_skills.py:340-362`), `rf_ctx` (`tests/test_release_findings.py:119-138`), `ri_ctx`
    (`tests/test_release_issues.py:154-178`), `ra_ctx` (`tests/test_risk_acceptance.py:138-191`),
    plus `rls_engine` / `admin_engine` / `db_session` (`tests/conftest.py:124-193`). The four `_ctx`
    fixtures are module-local; the new probe files therefore get their own seeding helper (§1).
14. **A trusted finding is never event-free (added in v2, Sol defect 5).** Creating a trusted
    security finding always inserts a `release_finding_events` row with `event_type='created'`
    (`app/repositories/security_scans.py:220-229`); live rows show `created_events = 1`. **v1.1
    claimed P-GREEN-3a could assert that *no* finding-event row exists. That was wrong and is
    withdrawn.** The refusal-side assertion must instead be *no new* event: the event count is
    unchanged across the `accept()` call, no row with `event_type='accepted'` exists for that
    finding, and no `audit_logs` row with `action='release.finding_accepted'`
    (`app/repositories/release_findings.py:82`) exists for it. The refusal itself is at
    `app/repositories/release_findings.py:73-74`, before the `status`/`risk_acceptance_record_id`
    mutation at `:75-77`, before the `flush()` at `:80`, and before the event and audit writes at
    `:81-82`.
15. **The cross-tenant *Python* refusal is the candidate lookup, not the binding count (corrected in
    v2, Sol defect 2).** `_require_subject_binding` resolves the frozen release candidate first,
    under the caller's tenant (`RiskAcceptanceRepository`'s `self.context.tenant_id`) — with `GUC=t2`
    and t1's project the lookup returns `None` and it raises
    `InvalidRiskAcceptance("release_id must resolve to one same-project frozen candidate")` at
    `app/repositories/risk_acceptance.py:104-105`, **never reaching** the binding-count branch at
    `:142-143`. **v1.1 pinned the Python path to `release/subject binding is not exact`. That was
    wrong and is withdrawn.** Sol's direct probe confirmed the candidate-lookup message.
    `release/subject binding is not exact` remains correct for two *other* paths and is kept only
    there: the **raw-SQL** DB guard `risk_acceptance_records: release/subject binding is not exact`
    (`0046:120-122`, probe P-GREEN-5a, fact 11) and the **same-tenant critical-finding** Python path
    (`:142-143`, fact 8) where the candidate does resolve but the bridged issue is critical.

### 0.2 Load-bearing claim (one sentence)

After this slice, each of the five named refusals is asserted by a test that executes the operation
which actually reaches that guard, pins that guard's exact message, separately pins the neighbouring
refusal it could be confused with, and fails when that one guard is disabled — which proves the test
is bound to that guard, **not** that the guard is new, stronger, or sufficient.

### 0.3 Honesty crux (verbatim, for `CLAUDE.md`)

*Slice 84 changed tests only. It added no migration, no guard, no grant, and no production code:
Alembic head stays `0062`. What is now true is that five previously masked assertions execute the
operation that reaches the named guard and pin that guard's exact message and SQLSTATE — the
`cost_events` immutability trigger via `TRUNCATE ... CASCADE`, the three global skill append-only
triggers via controlled `TRUNCATE ... CASCADE`, the `uaid_app` SELECT-only grant on all three global
tables via structurally valid INSERTs, the `critical findings cannot be accepted` repository branch
via a direct `accept()` call, the finding and issue acceptance guards via direct SQL over separately
valid wrong-project and wrong-subject records, and the risk-acceptance tenant boundary via a
structurally valid cross-tenant SQL INSERT. Each is paired with a mutation probe that disables only
that guard and shows the test fail. This does not make any of those guards stronger, does not close
F-002, F-003, F-004, F-005, F-017, or F-020, and does not prove the rest of the suite is
load-bearing — it repairs the five regressions the audit named and nothing else. A usable
risk-acceptance record for a critical finding is structurally impossible
(`app/repositories/risk_acceptance.py:120-123`), so the critical-accept test supplies a separately
valid non-critical record purely to reach the refusal. On the risk-acceptance table the tenant-scoped
Slice-47 binding guard refuses a cross-tenant INSERT before PostgreSQL evaluates the row-level
security policy; RLS attribution is therefore proven on a second probe that disables only that
guard. `can_go_live_autonomously` remains the literal `False`, A5 remains `slice54.v1`, and
readiness remains `slice20.v1`.*

### 0.4 Allowed claims, verbatim

- "Admin `TRUNCATE cost_events CASCADE` is refused with exactly
  `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)`, and plain admin `TRUNCATE cost_events` is
  refused earlier by the Slice-51 foreign key with `cannot truncate a table referenced in a foreign
  key constraint`. Both refusals are asserted separately and cannot be substituted for each other."
- "Each of `skills`, `agent_skill_capabilities`, and `agent_provided_skills` refuses a controlled
  admin `TRUNCATE ... CASCADE` with its own exact table-specific append-only message."
- "The runtime role `uaid_app` holds SELECT and not INSERT/UPDATE/DELETE/TRUNCATE on all three
  global skill tables, asserted both by `has_table_privilege` and by a structurally valid INSERT
  that is refused with `permission denied for table <name>` (SQLSTATE `42501`) — while **the same
  bound parameters** insert successfully as admin, over freshly minted parents proven absent
  beforehand, so the refusal is attributable to the grant and not to the row shape or to a unique
  collision with the fixture's own rows."
- "The cross-tenant risk-acceptance refusal on the **Python** path is
  `release_id must resolve to one same-project frozen candidate`, raised before any SQL INSERT is
  issued; `release/subject binding is not exact` is asserted only where it is actually raised — the
  raw-SQL DB guard, and the same-tenant critical-finding binding count."
- "`ReleaseFindingRepository.accept` is entered with a critical finding and a separately valid
  risk-acceptance record and raises `InvalidFinding` with exactly
  `critical findings cannot be accepted`; the DB guard branch is asserted separately with exactly
  `release_findings: critical findings cannot be accepted`."
- "A wrong-project and a wrong-subject risk-acceptance record are each built as a complete valid
  graph and then used in a direct-SQL accept, which is refused by the named acceptance guard with
  its exact message, for both findings and issues."
- "A structurally valid cross-tenant SQL INSERT into `risk_acceptance_records` is refused, first by
  the Slice-47 binding guard and — with only that guard disabled — by row-level security with
  exactly `new row violates row-level security policy for table \"risk_acceptance_records\"`
  (SQLSTATE `42501`); with the tenant axis corrected and nothing else, the same row inserts."

### 0.5 Refused claims, verbatim

- That any production guard, grant, trigger, CHECK, or repository branch was added, strengthened, or
  changed. None was. Head stays `0062`.
- That the rest of the test suite is load-bearing. Only the five F-021 regressions were repaired;
  the audit's own census found `242` deleted test lines with `14` weakened
  (`.planning/FINAL-AUDIT-REPORT.md:863`), and this slice addresses the five it classified as
  load-bearing problems.
- That F-004 is addressed. `approval_events`, `tool_calls`, and `agent_tool_allowlist` still accept
  owner UPDATE/DELETE/TRUNCATE (audit `:1124-1128`); that finding is parked and untouched.
- That RLS is the **first** refusal for a cross-tenant `risk_acceptance_records` INSERT. It is not;
  the tenant-scoped binding guard is. See OD-3.
- That the wrong-project acceptance case isolates the project predicate alone. It cannot: a
  separately valid p1b record is necessarily bound to a p1b subject, so project and subject both
  differ. The wrong-subject case is the one that isolates the subject predicate. See OD-4.
- That disabling a trigger in a probe proves tamper-resistance. It proves the test is bound to that
  trigger. A DB owner can still disable triggers; that is the standing `0008:145-146` limitation.
- That the five repaired tests prove the guards are sufficient, correct, or complete — only that
  each test now measures the guard it names.
- That any A5 gate, readiness level, or go-live bit moved. None did.
- That the pre-existing `>500`-line test files were brought under the house cap. They were not; see
  OD-1.

---

## 1. Exact files to modify

Tests only. No `app/`, no `migrations/`, no `scripts/`, no `.github/`, no `Makefile`.

| Path | Change |
|---|---|
| **Create** `tests/slice84_support.py` | Shared helpers: `s84_ctx` seeding fixture (org, `t1`/`t2`, `p1`/`p1b`/`px`), `sqlstate_of(exc)`, `err_text(exc)`, `expect_db_error(...)`, `disabled_trigger(admin_engine, table, trigger)` async context manager (committed DISABLE, guaranteed ENABLE in `finally`), `build_valid_finding_graph(...)`, `build_valid_issue_graph(...)`, `raw_risk_acceptance_insert_sql()`, `mint_global_skill_rows()` (§3.2, Sol defect 4), and the exported match constants `NO_USABLE_RECORD_FINDING` / `NO_USABLE_RECORD_ISSUE` consumed by the six tightened assertions in §3.4 (Sol defect 3). Google-style docstrings; one responsibility per function. |
| **Create** `tests/test_slice84_load_bearing.py` | R1, R2, R5 probes: `P-GREEN-1*`, `P-MUT-1`, `P-GREEN-2*`, `P-MUT-2`, `P-GREEN-5*`, `P-MUT-5`. |
| **Create** `tests/test_slice84_acceptance_guards.py` | R3, R4 probes: `P-GREEN-3*`, `P-MUT-3`, `P-GREEN-4*`, `P-MUT-4`. Split from the file above solely to keep both under the 500-line cap. |
| **Modify** `tests/test_cost.py` | §3.1 — split `test_cost_events_immutable`; remove the `"immutable" or "cannot truncate"` disjunction at `:472-485`; tighten the runtime half at `:457-471` (OD-2). Net line delta ≤ 0. |
| **Modify** `tests/test_skills.py` | §3.2 — `test_db_runtime_cannot_write_any_global_table` (`:372-387`) and `test_db_global_tables_immutable` (`:404-419`) become exact-message / exact-grant assertions delegating to `tests/slice84_support.py`. Net line delta ≤ 0. |
| **Modify** `tests/test_release_findings.py` | §3.3 — `test_reject_critical_accept` (`:332-341`) calls `accept()` directly. §3.4 — the last two cases of `test_guard_rejects_accept_with_invalid_records` (`:565-573`) execute `_ACCEPT_SQL`, **and the three retained bare catches at `:548`, `:557`, `:562` are tightened** (Sol defect 3). Tighten `test_guard_rejects_critical_accept_and_terminal_retransition` (`:454,:465`) to `match=`. Net line delta ≤ 0 — achieved by importing the match constants from `tests/slice84_support.py` rather than repeating them. |
| **Modify** `tests/test_release_issues.py` | §3.4 — the last two cases of `test_guard_rejects_accept_with_invalid_records` (`:581-589`) execute `_ACCEPT_SQL`, **and the three retained bare catches at `:564`, `:573`, `:578` are tightened** (Sol defect 3). Net line delta ≤ 0 via the same shared constants. |
| **Modify** `tests/test_risk_acceptance.py` | §3.5 — `test_rls_deny_by_default_and_cross_tenant` (`:305-327`) pins the Python refusal exactly and gains the structurally valid SQL probes via the helper. |

No other file is touched.

---

## 2. Open decisions — locked, Option A. The builder may not choose.

**OD-1 — house 500-line cap versus five already-oversized test files.**
`tests/test_skills.py` (826), `tests/test_release_issues.py` (701), `tests/test_release_findings.py`
(664), and `tests/test_cost.py` (617) already exceed the cap on `d0f38fd`.
**Option A (locked):** no existing test file may grow — each of the five edits must have a **net line
delta ≤ 0**; all new probes live in the two new Slice-84 files, each of which must stay **≤ 500
lines**; `tests/slice84_support.py` must stay ≤ 500 lines. The pre-existing violation is recorded as
an unfixed limitation in §6 and is **not** repaired here, because splitting four test modules the
audit's line citations depend on is an unscoped refactor that would invalidate F-021's own evidence
addresses. Rejected: reformatting the four files (breaks audit citations); rejected: appending to
them (grows a violation).

**OD-2 — the runtime-role half of `test_cost_events_immutable` (`tests/test_cost.py:457-471`) also
carries a disjunction (`"permission denied" or "immutable"`).**
**Option A (locked):** tighten it to exactly `permission denied for table cost_events` with SQLSTATE
`42501`, justified by `migrations/versions/0008_cost_ledger.py:183-184` (runtime holds
`SELECT, INSERT` only, so the trigger is unreachable from `uaid_app`). This is a tightening **inside
the same test function the audit named**; it is **not** a sixth regression and must not be reported
as one. Rejected: leaving it, which would leave a masking disjunction in the exact function being
repaired.

**OD-3 — R5 cannot reach RLS on the plain path.**
Per §0.1.11 the tenant-scoped Slice-47 BEFORE-INSERT guard refuses first.
**Option A (locked):** a three-probe proof — (a) the structurally valid cross-tenant SQL INSERT is
pinned to the guard's exact message and explicitly asserted **not** to be an FK, CHECK, or Python
error; (b) the **identical** SQL with only `risk_acceptance_records_guard` disabled is pinned to the
exact RLS message and SQLSTATE `42501`; (c) the identical SQL with the guard disabled and **only the
tenant axis corrected** succeeds inside a rolled-back transaction, proving (b) is attributable to the
tenant mismatch and not to the row shape. Rejected: claiming plain-path RLS attribution (false);
rejected: weakening or removing the guard (forbidden).

**OD-4 — the wrong-project acceptance case cannot isolate the project predicate.**
A separately valid p1b record must be bound to a p1b subject, so `r.project_id` and `r.issue_id` both
differ from the p1 subject.
**Option A (locked):** build both graphs anyway, assert the exact guard message, and state in the
test docstring and §6 that this case proves *a foreign-project record is refused by the acceptance
guard*, while the wrong-subject case (same project, different subject) isolates the subject
predicate. Rejected: implying single-predicate isolation.

**OD-5 — two named acceptance guards exist on `release_findings`.**
**Option A (locked):** assert exactly **one** observed message per probe — the expected first is
`release_findings: no usable risk-acceptance record for this finding` (`0022:200`) by trigger-name
order. The builder must quote the RED/GREEN output and pin the message actually observed; a
`match=` alternation across two guards is **forbidden**, because that is the masking pattern F-021
is about. Each probe additionally asserts the message contains none of `release/subject binding is
not exact`, `foreign key`, `violates check constraint`.

---

## 3. Per-regression implementation steps

Every probe below is a `@pytest.mark.db` async test using `pytest.raises(..., match=...)` (or an
explicit message assertion on the captured exception) with the exact substrings quoted here in
backticks. Regex metacharacters in `match=` patterns must be escaped with `re.escape`.

### 3.1 Regression 1 — `cost_events` truncate assertion

Current defect: `tests/test_cost.py:472-485` accepts `"immutable" or "cannot truncate"` for admin
`TRUNCATE cost_events`.

**In place (`tests/test_cost.py`, net delta ≤ 0):**

1. Runtime loop (`:459-471`): assert exactly `permission denied for table cost_events` and SQLSTATE
   `42501` (OD-2).
2. Admin loop (`:473-485`): split into
   - UPDATE and DELETE → exactly `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)`;
   - plain `TRUNCATE cost_events` → exactly `cannot truncate a table referenced in a foreign key
     constraint`, **and** assert `cost_events is immutable` is **absent** from that message.
   The `or` disjunction is deleted. No `TRUNCATE ... CASCADE` here — that lives in the probe file so
   the file does not grow.

**New (`tests/test_slice84_load_bearing.py`):**

- **P-GREEN-1a** admin `TRUNCATE cost_events CASCADE` after seeding one cost event → message contains
  exactly `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)`, SQLSTATE `P0001`, and contains
  neither `cannot truncate` nor `append-only`.
- **P-GREEN-1b** (neighbouring-refusal control) admin plain `TRUNCATE cost_events` → exactly
  `cannot truncate a table referenced in a foreign key constraint`, SQLSTATE `0A000`, and **not**
  `cost_events is immutable`. Docstring cites `0050:285` as the referencing FK.
- **P-MUT-1** inside `disabled_trigger(admin_engine, "cost_events", "cost_events_no_truncate")`:
  re-run the **identical** `TRUNCATE cost_events CASCADE`. Assert the outcome is **either** success
  **or** a failure whose message does **not** contain `cost_events is immutable` — the builder must
  quote which occurred (the expected observation is
  `cost_forecast_ledger_event_refs is append-only`, `0050:36`, because CASCADE also collects that
  table). The trigger is re-enabled in `finally`, and the probe asserts `tgenabled = 'O'` for
  `cost_events_no_truncate` afterwards. Run the whole probe in a transaction that is rolled back so
  no ledger row is actually truncated.

### 3.2 Regression 2 — global skill tables

Current defects: `tests/test_skills.py:405-419` accepts `append-only|immutable|cannot truncate` for
all three tables; `:373-387` uses `INSERT INTO {table} DEFAULT VALUES` with an unmatched
`pytest.raises(Exception)`.

**In place (`tests/test_skills.py`, net delta ≤ 0):**

1. `test_db_runtime_cannot_write_any_global_table` (`:372-387`): for each of the three tables assert
   `permission denied for table {table}` with SQLSTATE `42501`, using the **structurally valid**
   statements from §0.1.6 (not `DEFAULT VALUES`) supplied by `tests/slice84_support.py`. Keep the
   existing positive `SELECT count(*) >= 1`. Note (Sol defect 1): `uaid_app` already returns `42501`
   for the current `DEFAULT VALUES` statement too — the tightening here is that the assertion now
   *pins* `42501` and a structurally valid row, so the test can no longer pass on some other error.
2. `test_db_global_tables_immutable` (`:404-419`): per-table exact messages —
   `skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)`,
   `agent_skill_capabilities is append-only / immutable (no UPDATE/DELETE/TRUNCATE)`,
   `agent_provided_skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)` — for the
   UPDATE/DELETE statements. The truncate cases move to the probe file (they need CASCADE plus the
   FK control), keeping this edit a net reduction.

**New (`tests/test_slice84_load_bearing.py`):**

- **P-GREEN-2a** for each of the three tables, admin `TRUNCATE {table} CASCADE` → exactly
  `{table} is append-only / immutable (no UPDATE/DELETE/TRUNCATE)`, SQLSTATE `P0001`.
- **P-GREEN-2b** (neighbouring-refusal control) admin plain `TRUNCATE skills` and plain
  `TRUNCATE agent_skill_capabilities` → exactly `cannot truncate a table referenced in a foreign key
  constraint`, SQLSTATE `0A000`, and **not** `append-only`. Plain `TRUNCATE agent_provided_skills`
  has no dependent and must give the trigger message; assert that too, so the two refusal classes are
  pinned in both directions.
- **P-GREEN-2c** (grant matrix) `SELECT has_table_privilege('uaid_app', :t, :p)` for
  `p ∈ {SELECT, INSERT, UPDATE, DELETE, TRUNCATE}` on each of the three tables: `SELECT` is `True`,
  the other four are `False`. Cites `0037:315-317`.
**Minting the probe rows — `mint_global_skill_rows()` (Sol defect 4; binding, not the builder's
choice).** `sk_ctx` already owns the `(cap, skill)` pair (§0.1.6), so 2d/2e must not reuse it. The
helper returns one frozen parameter set, computed once and used **byte-identically** by 2d and 2e:

- `skill_id` = a new `uuid4()`, `skill_key` = `"s84_" + uuid4().hex` (matches
  `^[a-z][a-z0-9_]{1,63}$`, cannot collide with `uq_skills_key`), `category='backend_engineering'`;
- `capability_id` = a new `uuid4()`, `blueprint_id` = `sk_ctx["bp"]` (an **existing** blueprint, so
  `fk_asc_blueprint` is satisfiable), `cost_latency_class='medium'`, `provided_tools`/`domains`
  `'[]'::jsonb`;
- the `agent_provided_skills` row = `(capability_id, skill_id, can_review=false)` over those two new
  ids, so `uq_aps_capability_skill` cannot fire.

Before both probes, assert
`SELECT count(*) FROM agent_provided_skills WHERE capability_id=:c AND skill_id=:s` **= 0** and
`SELECT count(*) FROM skills WHERE key=:k` **= 0**. Every parent row is created **only** inside
2e's rolled-back admin transaction, so nothing persists and the global cross-test capability map
(`tests/test_skills.py:340-341`) is not perturbed.

- **P-GREEN-2d** (structurally valid runtime INSERT) as `uaid_app`, for each of the three tables,
  run the fully populated INSERT with the minted parameters → exactly
  `permission denied for table {table}`, SQLSTATE `42501`, and assert the message contains none of
  `null value in column`, `violates not-null constraint`, `violates foreign key constraint`,
  `violates check constraint`, `duplicate key value violates unique constraint`. **Honesty note the
  docstring must carry:** the ACL is evaluated before any constraint, so 2d is refused whether or
  not its parents exist; parent existence is therefore irrelevant to 2d and is supplied only in 2e.
- **P-GREEN-2e** (shape control — the load-bearing half of 2d) inside **one rolled-back admin
  transaction**, insert the minted `skills` row, then the minted `agent_skill_capabilities` row,
  then the minted `agent_provided_skills` row — **with the identical bound parameters 2d used** —
  and assert all three **succeed** (`rowcount == 1` each). This is what proves the `42501` in 2d is
  the grant and not the shape, the key, or a unique collision. Roll back; then re-assert the two
  `count(*) = 0` queries above, proving nothing leaked.
- **P-GREEN-2f** (masking controls, **admin** — the role that actually has INSERT, Sol defect 1)
  `INSERT INTO skills DEFAULT VALUES` fails with SQLSTATE `23502`,
  `null value in column "key" of relation "skills" violates not-null constraint`; and
  `INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) VALUES (:cap,
  gen_random_uuid(), false)` — `:cap` from `sk_ctx`, a random `skill_id` that cannot collide with
  `uq_aps_capability_skill` — fails with `violates foreign key constraint "fk_aps_skill"`. Docstring
  states plainly: **these are the errors a granted INSERT would produce, and the pre-Slice-84
  unmatched `pytest.raises(Exception)` at `tests/test_skills.py:373-387` would accept either of them
  as if it were the grant refusal.** Both run in a rolled-back transaction.
- **P-MUT-2** for each of the three tables, inside
  `disabled_trigger(admin_engine, table, f"{table}_no_truncate")`, re-run the identical
  `TRUNCATE {table} CASCADE` and assert the message no longer contains
  `{table} is append-only / immutable`. Restore in `finally`; assert `tgenabled='O'` afterwards; run
  inside a rolled-back transaction.

### 3.3 Regression 3 — direct critical `accept()`

Current defect: `tests/test_release_findings.py:333-341` never calls
`ReleaseFindingRepository.accept`; it asserts that `_make_ra_record` raises. Root cause of that
setup failure is named in §0.1.8.

**In place (`tests/test_release_findings.py:332-341`), rewritten to:**

1. Create a **critical** trusted security finding in `p1` (`_trusted_security_finding(..., severity=
   "critical")`).
2. Create a **separately valid** graph: a second, **non-critical** (`severity="high"`) trusted
   security finding in the **same project** `p1`, and a usable risk-acceptance record for **that**
   finding via the existing `_make_ra_record` (which succeeds, because its bridged issue is
   non-critical — §0.1.8).
3. Call `await repo.accept(finding_id=critical.id, risk_acceptance_record_id=rec.id, actor="rm")`
   inside `pytest.raises(InvalidFinding, match=...)` pinning exactly
   `critical findings cannot be accepted`.
4. Assert the critical finding's status is still `open` after the refusal.

The exception type must be `InvalidFinding` (imported at `tests/test_release_findings.py:21`), never
bare `Exception` — that alone excludes a setup error.

**Also in place:** tighten `test_guard_rejects_critical_accept_and_terminal_retransition`
(`:454`, `:465`) from `pytest.raises(Exception)` to `match=` on
`release_findings: critical findings cannot be accepted` and
`release_findings: terminal status resolved cannot transition` respectively. Strengthening only.

**New (`tests/test_slice84_acceptance_guards.py`):**

- **P-GREEN-3a** the repository branch, as above, additionally asserting the raised exception is
  `InvalidFinding` and that the refusal wrote **nothing new** (corrected in v2, Sol defect 5 — a
  trusted finding always carries a `created` event, `app/repositories/security_scans.py:220-229`,
  so "no event row exists" is false and must not be asserted). The three assertions are:
  (i) `SELECT count(*) FROM release_finding_events WHERE finding_id = :critical` is **identical
  before and after** the `accept()` call — captured into a variable *before*, compared *after*;
  (ii) **no** `release_finding_events` row for that finding has `event_type = 'accepted'`;
  (iii) **no** `audit_logs` row for that finding has `action = 'release.finding_accepted'`
  (`app/repositories/release_findings.py:82`). The refusal is raised at
  `app/repositories/release_findings.py:73-74`, before the mutation at `:75-77`, the `flush()` at
  `:80`, and the event/audit writes at `:81-82` — which is why the count is unchanged rather than
  zero.
- **P-GREEN-3b** the **DB-guard** branch, kept distinct from the repository branch: direct
  `_ACCEPT_SQL`-shaped UPDATE as `uaid_app` setting `status='accepted'` **and** a valid
  `risk_acceptance_record_id` (the §3.3.2 record) on the **critical** finding → exactly
  `release_findings: critical findings cannot be accepted` (`0022:181`), SQLSTATE `P0001`, and
  **not** `accepted requires a risk_acceptance_record_id`. Supplying the record is what stops the
  earlier null branch from masking the critical branch.
- **P-MUT-3** inside `disabled_trigger(admin_engine, "release_findings", "release_findings_guard")`,
  re-run P-GREEN-3b's identical SQL and assert the message no longer contains
  `release_findings: critical findings cannot be accepted`. Restore in `finally`.

### 3.4 Regression 4 — wrong-project / wrong-subject must reach the acceptance guard

Current defect: `tests/test_release_findings.py:565-573` and `tests/test_release_issues.py:581-589`
wrap `_finding_and_record` / `_issue_and_record` in `pytest.raises` so the failure happens during
`_make_ra_record` and `_ACCEPT_SQL` is never executed.

**Shared helpers (`tests/slice84_support.py`).** One function per responsibility:

- `build_valid_finding_graph(session, ctx, project_id, *, severity="high") -> (finding_id,
  record_id)` — trusted non-critical finding, its Slice-47 bridged issue, a draft release candidate,
  `bind_issue`, `freeze`, then `RiskAcceptanceRepository.create` with
  `subject_type="release_finding"`. Returns both ids. Raises immediately if the record is not
  created, so a setup failure can never be mistaken for a guard refusal.
- `build_valid_issue_graph(session, ctx, project_id) -> (issue_id, record_id)` — the same shape with
  `subject_type="release_issue"`.

**In place — the six retained bare catches (Sol defect 3; binding).** v1.1 claimed no touched
assertion would keep an unmatched `pytest.raises(Exception)`. That was wrong: the three earlier
cases in each of the two `test_guard_rejects_accept_with_invalid_records` functions kept bare
catches. Those three cases per file **already execute `_ACCEPT_SQL`** — they reach the acceptance
guard today and are merely unpinned — so each is tightened to the single exact message with no
alternation, plus SQLSTATE `P0001`:

| File | Line | Case | Exact `match=` |
|---|---|---|---|
| `tests/test_release_findings.py` | `:548` | expired record | `release_findings: no usable risk-acceptance record for this finding` |
| `tests/test_release_findings.py` | `:557` | revoked record | same |
| `tests/test_release_findings.py` | `:562` | `blocking_category` set | same |
| `tests/test_release_issues.py` | `:564` | expired record | `release_issues: no usable risk-acceptance record for this issue` |
| `tests/test_release_issues.py` | `:573` | revoked record | same |
| `tests/test_release_issues.py` | `:578` | `blocking_category` set | same |

Sources: `0022:191-200` and `0046:339-342`. Each of the six additionally asserts SQLSTATE `P0001`
and that the message contains none of `release/subject binding is not exact`, `foreign key`,
`violates check constraint`. **OD-1 is preserved by delegation, not by omission:** the two match
strings live once in `tests/slice84_support.py` as `NO_USABLE_RECORD_FINDING` and
`NO_USABLE_RECORD_ISSUE`, and each call site uses a single shared assertion helper, so the six
tightenings plus the four rewrites in this section must still produce a **net line delta ≤ 0** on
both files. If a file would grow, move more of the body into the helper — never drop an assertion.

**In place — `tests/test_release_findings.py` (replacing `:565-573`):**

- **wrong-project:** build a complete valid graph in `p1` (`fid_a`, unused record) and a complete
  valid graph in `p1b` (`fid_b`, `rec_b`). Then execute `_ACCEPT_SQL` with
  `fid=fid_a, rid=rec_b` under `GUC=t1` (same tenant, different project). Expect exactly
  `release_findings: no usable risk-acceptance record for this finding`.
- **wrong-subject:** build **two** complete valid graphs in the **same** project `p1` →
  `(fid_a, rec_a)` and `(fid_b, rec_b)`. Execute `_ACCEPT_SQL` with `fid=fid_a, rid=rec_b`. Expect
  the same exact message. Docstring records OD-4.

Both cases assert the message contains none of `release/subject binding is not exact`,
`foreign key`, `violates check constraint` — i.e. it is the acceptance guard, not the setup or a
neighbouring constraint. Both assert SQLSTATE `P0001`. Both assert the finding is still `open` after
the refusal.

**In place — `tests/test_release_issues.py` (replacing `:581-589`):** identical structure with
`build_valid_issue_graph`, `_ACCEPT_SQL` from `tests/test_release_issues.py:455-457`, and the exact
message `release_issues: no usable risk-acceptance record for this issue` (`0046:341`).

**New (`tests/test_slice84_acceptance_guards.py`):**

- **P-GREEN-4a / 4b** the findings wrong-project and wrong-subject probes, as above, plus an
  explicit positive control in the same test: `_ACCEPT_SQL` with the **matching** `(fid_a, rec_a)`
  pair **succeeds**. Without that control the refusals could be caused by an always-failing setup.
  Run the positive control in a rolled-back transaction so it does not leave an accepted finding.
- **P-GREEN-4c / 4d** the issues wrong-project and wrong-subject probes plus the same positive
  control against `release_issues`.
- **P-MUT-4a** inside `disabled_trigger(admin_engine, "release_findings",
  "release_findings_guard")`, re-run P-GREEN-4a's identical SQL; assert the message no longer
  contains `no usable risk-acceptance record for this finding`. (The expected observation is that
  `release_findings_slice47_subject_guard` then raises
  `release_findings: accepted record subject kind must be release_finding`; the builder quotes what
  is observed.)
- **P-MUT-4b** inside `disabled_trigger(admin_engine, "release_issues", "release_issues_guard")`,
  re-run P-GREEN-4c's identical SQL; assert it **succeeds** or that the message no longer contains
  `no usable risk-acceptance record for this issue`. Roll back.

### 3.5 Regression 5 — structurally valid cross-tenant SQL

Current defect: `tests/test_risk_acceptance.py:322-327` calls the **Python** repository as t2 for
t1's project. Under `GUC=t2` the frozen-candidate lookup in `_require_subject_binding` returns
`None` and raises `InvalidRiskAcceptance("release_id must resolve to one same-project frozen
candidate")` at `app/repositories/risk_acceptance.py:94-105` — before `session.add`, so no INSERT is
issued and RLS is never exercised (corrected in v2, Sol defect 2; see §0.1.15).

**In place (`tests/test_risk_acceptance.py:305-327`):**

1. Keep the no-GUC deny-by-default `SELECT count(*) == 0` (`:313-318`) — it already proves RLS on
   the read path.
2. Keep the t2 `count_active_nonblocking(p1) == 0` cross-tenant read (`:320-321`).
3. Replace the bare `pytest.raises(Exception)` at `:323-327` with
   `pytest.raises(InvalidRiskAcceptance, match=...)` pinning exactly
   `release_id must resolve to one same-project frozen candidate` (`risk_acceptance.py:105`) — **not**
   `release/subject binding is not exact`, which this path never reaches (Sol defect 2). The
   assertion additionally checks the message does **not** contain `binding is not exact`,
   `row-level security`, or `permission denied`, and a comment names this as the Python-path refusal
   that never reaches SQL — the exact masking the audit found.
4. Add the structurally valid SQL probe by calling the shared helper (one or two lines here; the
   full battery lives in the probe file).

**Shared helper (`tests/slice84_support.py`).** `raw_risk_acceptance_insert_sql()` returns the
INSERT modelled on `tests/test_risk_acceptance.py:362-369`, **extended with `subject_type`** and
parameterised on `tenant_id`, `project_id`, `release_id`, `issue_id`, so that every column is
populated with a value that would be legal if the tenant identity matched:

```
INSERT INTO risk_acceptance_records
  (tenant_id, project_id, release_id, issue_id, subject_type, severity,
   reason_for_acceptance, business_impact, rollback_or_mitigation_plan,
   required_follow_up_ticket, expiry_date, owner, approver, accepted_by,
   approval_authority_source, status, approver_provenance)
VALUES (:t, :p, :rel, :iid, 'release_issue', 'low', 'r', 'b', 'rb', 'T-1', :exp,
        'o', 'a', '["o"]'::jsonb, 'approval_matrix', 'active',
        'caller_supplied_unverified')
```

`:rel` and `:iid` are t1's **real** frozen candidate `release_ref` and its bound issue id from
`ra_ctx` (`tests/test_risk_acceptance.py:176-190`), so the row is structurally complete.

**New (`tests/test_slice84_load_bearing.py`):**

- **P-GREEN-5a** as `uaid_app` with `set_config('app.current_tenant', t2)` and `:t = t1`, `:p = p1`:
  the INSERT is refused with exactly `risk_acceptance_records: release/subject binding is not exact`
  (`0046:121`), SQLSTATE `P0001`. Assert the message contains none of `foreign key`,
  `violates check constraint`, `null value in column`, `InvalidRiskAcceptance`. The docstring states
  OD-3 verbatim: this is the tenant-scoped guard firing before RLS, **not** RLS.
- **P-GREEN-5b** inside `disabled_trigger(admin_engine, "risk_acceptance_records",
  "risk_acceptance_records_guard")`, the **identical** SQL with the identical parameters → exactly
  `new row violates row-level security policy for table "risk_acceptance_records"`, SQLSTATE
  `42501`. Assert the message contains none of `foreign key`, `permission denied`,
  `binding is not exact`.
- **P-GREEN-5c** (tenant-axis mutation / attribution control) inside the same disabled-guard scope,
  the identical SQL with **only** the tenant axis corrected (`GUC = t1`, `:t = t1`, `:p = p1`)
  **succeeds**, inside an explicitly rolled-back transaction. This proves 5b's refusal is the tenant
  mismatch, not the row shape.
- **P-MUT-5** with the guard **enabled** (production state) and the tenant axis corrected, the
  identical SQL **succeeds** (rolled back) — proving 5a's refusal is the cross-tenant claim reaching
  the guard, not a permanently invalid row.
- All three disabled-guard probes restore the trigger in `finally` and then assert
  `tgenabled = 'O'` for `risk_acceptance_records_guard`.

---

## 4. Named probes

### 4.1 RED — the builder runs these on `d0f38fd` **before** any edit, and quotes raw output

The audit supplies an exact driver only for P-RED-1 (`.planning/FINAL-AUDIT-REPORT.md:1134-1140`).
The other four drivers are written here, as the PROBE RULE requires. Each must be shown **RED**
(i.e. succeeding at the thing it should not, or failing for the wrong reason) before any test is
changed. Record every raw message and SQLSTATE in the build report.

- **P-RED-1** — as admin, `TRUNCATE cost_events` (no `CASCADE`) on a database with one cost event.
  **Expected RED:** the error contains `cannot truncate` and does **not** contain
  `cost_events is immutable`. Then run `pytest -m db tests/test_cost.py::test_cost_events_immutable`
  and quote that it **passes** — proving the current test accepts the neighbouring FK.
- **P-RED-2a** — as admin, `TRUNCATE skills` (no `CASCADE`). **Expected RED:** the message satisfies
  the current loose regex `append-only|immutable|cannot truncate` via `cannot truncate`, not via the
  table-specific append-only message. Quote both the message and the fact that
  `tests/test_skills.py::test_db_global_tables_immutable` passes.
- **P-RED-2b** — two halves (rewritten in v2, Sol defect 1; the v1.1 shape predicted the wrong
  runtime error and is withdrawn).
  **(i) Runtime, current outcome — not itself the defect.** As `uaid_app`,
  `INSERT INTO skills DEFAULT VALUES`. **Expected:** SQLSTATE `42501`,
  `permission denied for table skills`. Quote it verbatim. The ACL is checked before NOT NULL, so
  the runtime role does **not** reach `23502`. Record this as the current state, and do **not**
  claim it is the masking path.
  **(ii) Admin, the actual masking path.** As **admin**, the **identical** invalid SQL
  `INSERT INTO skills DEFAULT VALUES`. **Expected RED:** SQLSTATE `23502`,
  `null value in column "key" of relation "skills" violates not-null constraint`. Quote it. **This
  is the proof:** `tests/test_skills.py:373-387` catches an unmatched `pytest.raises(Exception)`, so
  if INSERT were ever granted to `uaid_app` the test would pass on this `23502` and report nothing.
  Run the admin half in a rolled-back transaction.
  **GREEN for 2b** is unchanged in substance: a **structurally valid** runtime INSERT refused with
  `permission denied for table {table}` / `42501` (P-GREEN-2d), **plus** the admin shape-success of
  that same valid row (P-GREEN-2e), **plus** the admin `23502` and FK masking controls pinned
  explicitly (P-GREEN-2f).
- **P-RED-3** — show that `tests/test_release_findings.py::test_reject_critical_accept` never enters
  `ReleaseFindingRepository.accept`: monkeypatch `accept` to set a module-level flag (or run under
  `coverage run --include app/repositories/release_findings.py`) and quote that the flag is unset /
  lines `68-83` are unexecuted, **and** quote the exception the test actually catches — expected
  `InvalidRiskAcceptance: release/subject binding is not exact` raised inside `_make_ra_record` →
  `RiskAcceptanceRepository.create` (`app/repositories/risk_acceptance.py:142-143`), for the root
  cause at `:120-123`.
- **P-RED-4** — instrument `_ACCEPT_SQL` (wrap `_direct_sql` in a counter, or add a temporary print)
  and run
  `tests/test_release_findings.py::test_guard_rejects_accept_with_invalid_records` and
  `tests/test_release_issues.py::test_guard_rejects_accept_with_invalid_records`. **Expected RED:**
  the last two cases of each raise inside `_make_ra_record` / `bind_issue` and the `_ACCEPT_SQL`
  counter does not increment for them. Quote the counter and the two exceptions. Revert the
  instrumentation before proceeding.
- **P-RED-5** — run `tests/test_risk_acceptance.py::test_rls_deny_by_default_and_cross_tenant` with
  the exception captured and printed. **Expected RED:** the t2 `create(project_id=p1)` raises a
  **Python** `InvalidRiskAcceptance` from the frozen-candidate lookup in `_require_subject_binding`
  with exactly `release_id must resolve to one same-project frozen candidate`
  (`app/repositories/risk_acceptance.py:94-105`) — **not** `release/subject binding is not exact`,
  which is unreachable here (Sol defect 2, §0.1.15) — with no SQL INSERT issued and no RLS policy
  error. Quote the exception type and the exact message. If the observed message is instead the
  binding-count one, **stop and report**: that would mean §0.1.15 is wrong on the live database.

**Gate.** The builder may not edit a single test line until all six RED drivers are quoted in the
build report — seven transcripts, since P-RED-2b has a runtime half and an admin half and **both**
are required. If any RED does not reproduce, **stop and report** — do not adjust the probe to make
it reproduce.

### 4.2 GREEN and MUTATION

| Probe | Asserts (exact) |
|---|---|
| P-GREEN-1a | `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)`, `P0001`, on `TRUNCATE cost_events CASCADE` |
| P-GREEN-1b | `cannot truncate a table referenced in a foreign key constraint`, `0A000`, on plain TRUNCATE |
| P-MUT-1 | with `cost_events_no_truncate` disabled, CASCADE no longer yields `cost_events is immutable` |
| P-GREEN-2a | per-table `{table} is append-only / immutable (no UPDATE/DELETE/TRUNCATE)`, `P0001` |
| P-GREEN-2b | FK-referenced tables → `cannot truncate a table referenced in a foreign key constraint`, `0A000`; `agent_provided_skills` → its trigger message |
| P-GREEN-2c | `has_table_privilege('uaid_app', t, 'SELECT')` true; `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` false, all three tables |
| P-GREEN-2d | structurally valid runtime INSERT, freshly minted non-colliding parameters → `permission denied for table {table}`, `42501`, and none of the not-null / FK / check / unique texts |
| P-GREEN-2e | the **identical bound parameters** insert as admin over minted parents in one rolled-back txn (shape control); pair proven absent (`count(*) = 0`) before and after |
| P-GREEN-2f | admin `DEFAULT VALUES` → `23502` `null value in column "key" of relation "skills" violates not-null constraint`; admin unknown `skill_id` → `violates foreign key constraint "fk_aps_skill"` — the two errors the unmatched catch would accept |
| P-MUT-2 | with `{table}_no_truncate` disabled, CASCADE no longer yields `{table} is append-only / immutable` |
| P-GREEN-3a | `InvalidFinding` with `critical findings cannot be accepted` from a direct `accept()`; finding-event count **unchanged** across the call, no `event_type='accepted'` row, no `release.finding_accepted` audit action |
| P-GREEN-3b | `release_findings: critical findings cannot be accepted`, `P0001`, via SQL with a valid record supplied |
| P-MUT-3 | with `release_findings_guard` disabled, that message no longer appears |
| P-GREEN-4a/4b | `release_findings: no usable risk-acceptance record for this finding`, `P0001`; matching pair succeeds; the three in-place expired/revoked/blocking cases pinned to the same exact string with no alternation |
| P-GREEN-4c/4d | `release_issues: no usable risk-acceptance record for this issue`, `P0001`; matching pair succeeds; the three in-place expired/revoked/blocking cases pinned likewise |
| P-MUT-4a/4b | with the respective guard disabled, those messages no longer appear |
| P-GREEN-5a | `risk_acceptance_records: release/subject binding is not exact`, `P0001`, from **raw SQL only**; the Python path is pinned separately to `release_id must resolve to one same-project frozen candidate` |
| P-GREEN-5b | guard disabled → `new row violates row-level security policy for table "risk_acceptance_records"`, `42501` |
| P-GREEN-5c | guard disabled, tenant axis corrected → INSERT succeeds (rolled back) |
| P-MUT-5 | guard enabled, tenant axis corrected → INSERT succeeds (rolled back) |

**Every** probe that asserts a refusal must have a paired mutation or control that fails when the
targeted guard/grant is removed or when the only-wrong-axis is corrected. A probe without one is
incomplete and must be rejected in review.

**Trigger-toggle hygiene.** `disabled_trigger` must: take an `admin_engine`; `DISABLE` in its own
committed transaction; `yield`; `ENABLE` in `finally` in its own committed transaction; and the
calling probe must assert `SELECT tgenabled FROM pg_trigger WHERE tgname = :n` equals `'O'` after
the block. A probe that leaves a trigger disabled poisons the rest of the suite and is a hard
review rejection. Reuse `set_trigger` (`tests/learning_support.py:386-389`) only where a session-scoped
toggle is sufficient; it is not sufficient here, because the probes need a **committed** toggle
visible to the separate `rls_engine` connection.

---

## 5. Validation — the builder runs all of these and quotes REAL counts

```
uv sync --frozen
uv run ruff check .
uv run pyright <the eight files in §1>
make test
RLS_DB_PASSWORD=... make test-db
```

- Baseline on `d0f38fd` for comparison: `make test` → `1277 passed, 1085 deselected`; `make test-db`
  → `1085 passed, 1277 deselected` (`.planning/FINAL-AUDIT-REPORT.md:800-808`). The new counts will
  be higher; **quote the actual numbers, never invent or carry forward them.** Every new probe is a
  `db` test, so `make test`'s *deselected* count rises and its *passed* count is unchanged unless a
  Docker-free test was added.
- Pyright: CI's scoped step covers Slices 55–63 only (`.github/workflows/ci.yml:61-62`) and **must
  not be edited** in this slice. Run pyright locally on the eight §1 files anyway and report `0
  errors` for that set. The repository-wide `3050`-error baseline (audit `:814-817`) is F-017 /
  Slice 80 and is neither fixed nor hidden here.
- `ruff format` must **not** be run over the tree; format only the files this slice touches.
- Re-assert after the suites: `A5_RULESET_VERSION == "slice54.v1"`, readiness ruleset
  `"slice20.v1"`, `can_go_live_autonomously is False`, and `alembic heads` = `0062`.
- Confirm `git diff --stat` touches only the eight paths in §1 and that
  `git diff --numstat` shows a **non-positive** line delta for each of the five pre-existing files
  (OD-1).

---

## 6. Documentation after merge

Only after the PR merges, and only these:

- **`CLAUDE.md`** — one Slice 84 entry carrying §0.3 **verbatim**, stating: test-integrity only; no
  migration; head stays `0062`; no production guard added; A5 `slice54.v1`; readiness `slice20.v1`;
  `can_go_live_autonomously` literal `False`; F-002/F-003/F-004/F-005/F-017/F-020 untouched.
- **`README.md`** — only if it states test counts or claims about these five tests. No test counts
  are to be added.
- **`.planning/GO-LIVE-END-TO-END-ROADMAP.md`** — §5 Slice 84 status `NOT STARTED` →
  `COMPLETE (tests only; no migration; head 0062)`; §6 next slice = **Slice 83 / F-020**. Do not
  change any other slice status, do not mark Slice 61 done, do not touch D-8/D-9/D-10.
- **`.planning/HANDOFF.json`** — record Slice 84 merged, next = Slice 83, and the limitations below.
  Do not write "no remaining blockers" (that is the F-018 defect).
- **Named limitations to record, verbatim:**
  `f021_test_integrity_only_no_production_guard_added`,
  `risk_acceptance_cross_tenant_insert_refused_by_binding_guard_before_rls`,
  `wrong_project_acceptance_case_differs_in_both_project_and_subject`,
  `four_touched_test_files_remain_over_the_500_line_house_cap`,
  `ci_pyright_scope_still_s55_63_full_repo_typecheck_is_f017`,
  `f004_approval_events_tool_calls_allowlist_owner_mutation_still_succeeds`.
- **Forbidden wording:** do not write that F-021's production guards were added or hardened. The
  correct claim is: *the tests now refuse the audit's own masking paths.*

Do not edit `.planning/FINAL-AUDIT-REPORT.md` or the spec.

---

## 7. GitHub

- Branch `feat/slice-84-test-integrity` off `d0f38fd` (current `origin/main`).
- Conventional commits, atomic, one regression per commit where possible:
  `test(slice-84): reproduce F-021 RED probes` (report only, no test edits),
  `test(slice-84): bind cost_events truncate assertion to its named trigger`,
  `test(slice-84): assert exact global skill grants and truncate guards`,
  `test(slice-84): restore direct critical accept()`,
  `test(slice-84): reach the finding and issue acceptance guards`,
  `test(slice-84): structurally valid cross-tenant risk-acceptance SQL`.
- PR body must contain: the seven RED transcripts (six drivers; P-RED-2b counts twice — runtime
  `42501` and admin `23502`), the GREEN transcripts, the mutation transcripts,
  the real `make test` / `make test-db` / `ruff` / `pyright` counts, and §0.3 verbatim.
- Do not commit `.env`. Do not edit this plan.

---

## 8. Builder constraints, restated

1. RED first, quoted, for all six drivers — seven transcripts, since P-RED-2b has a runtime half and
   an admin half. No test edit before that.
2. No migration. No production file. Head stays `0062`.
3. No `pytest.raises(Exception)` without `match=`; no `or`/alternation across two different refusal
   classes in any assertion this slice writes or touches.
4. Every refusal probe has a mutation or an only-wrong-axis control.
5. Every disabled trigger is restored in `finally` and re-asserted `'O'`.
6. No existing test file grows; the three new files stay ≤ 500 lines each.
7. Never re-grant a privilege, never weaken/skip/delete a test, never mark `xfail`.
8. Google-style docstrings on every new public helper in `tests/slice84_support.py`; one function,
   one responsibility.
9. If any locked decision in §2 turns out to be wrong on the live database, **stop and report to the
   owner** with the raw output. Do not re-decide it.

---

## 9. Change log

**v1.** First version. Written against `d0f38fd`, Alembic head `0062`, after re-reading
`tests/test_cost.py`, `tests/test_skills.py`, `tests/test_release_findings.py`,
`tests/test_release_issues.py`, `tests/test_risk_acceptance.py`, `tests/conftest.py`,
`tests/learning_support.py`, `tests/admin_support.py`,
`migrations/versions/0008_cost_ledger.py`, `0022_release_findings.py`, `0037_skill_matching.py`,
`0046_issue_provenance.py`, `0050_cost_forecasts.py`,
`app/repositories/release_findings.py`, and `app/repositories/risk_acceptance.py`. Five open
decisions locked to Option A; the root cause of the critical-finding `_make_ra_record` failure named
at `app/repositories/risk_acceptance.py:120-123`.

**v1.1.** Two factual corrections only, no scope or technical change: the standing BUILDER/REVIEWER
seats are named in the header, and the §0 "is not" row for F-002 / Slice 65 is corrected from Wave 2
to **Wave 3** per `.planning/GO-LIVE-END-TO-END-ROADMAP.md:676` (Wave 2 is Slice 71 / F-008, `:694`).

**v2.** Issued after **one Sol REJECT** of v1.1 (agent `4ec48fdf-3cdd-4330-a6d2-ae9990d1a08b`);
consecutive plan REJECT count **1**; all five defects accepted, none argued down; no scope added, no
migration, no production file, OD-1…OD-5 not reopened. Corrections, each traced to the section that
now encodes it: **(1)** `uaid_app` gets `42501 permission denied for table skills`, not NOT NULL —
§0.1.5 withdrawn and rewritten, P-RED-2b split into a runtime-`42501` record and an **admin**
`23502` masking demonstration, P-GREEN-2f re-pointed at admin (§3.2, §4.1, §4.2); **(2)** the
cross-tenant **Python** refusal is `release_id must resolve to one same-project frozen candidate`
(`risk_acceptance.py:104-105`), not `release/subject binding is not exact` — new fact §0.1.15, §3.5
step 3 and P-RED-5 re-pinned, the binding-count string retained only for raw-SQL P-GREEN-5a and the
same-tenant critical path; **(3)** six bare `pytest.raises(Exception)` survived in the touched
invalid-record functions (`test_release_findings.py:548,557,562`,
`test_release_issues.py:564,573,578`) — §3.4 gains a binding six-row table pinning each to the exact
acceptance-guard message plus `P0001`, with the constants exported from `tests/slice84_support.py`
so OD-1's net-line-delta ≤ 0 still holds; **(4)** `sk_ctx` already owns the `(cap, skill)` pair and
`uq_aps_capability_skill` (`0037:147`) forbids duplicating it — §0.1.6 withdrawn and rewritten, and
§3.2 adds `mint_global_skill_rows()` (fresh `s84_<uuid4hex>` key, new capability UUID over the
existing blueprint, `count(*) = 0` asserted before both probes, identical bound parameters for the
runtime and admin probes); **(5)** a trusted finding always carries a `created` event
(`security_scans.py:220-229`), so P-GREEN-3a asserts an **unchanged** event count, absence of
`event_type='accepted'`, and absence of the `release.finding_accepted` audit action instead of
"no event row" — new fact §0.1.14, §3.3 and §4.2 updated.
