# Slice 23 — Security/shortcut (release) findings store + conservative A5 gates #5/#6 (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice23-release-findings` off `main` @ `13885f2`; release-findings store (`app/release/findings.py`
+ models + repo), migration `0022` (DB guard: INSERT invariants, per-transition mutability incl.
`updated_at`, critical-no-accept, accept-requires-usable-record), conservative A5 gates #5/#6
(`ruleset_version="slice23.v1"`), tests, docs. Verification (fresh DB): `ruff` clean, `make test` 234,
`make test-db` 288. **No go-live; gates #5/#6/#7 never pass.** Local re-run needs `make test-db-drop`.
**Base:** `main` @ `13885f2` (clean).
**Rulings:** `.planning/SLICE-23-FINDINGS-DISCUSSION.md` (D-SF-1..8, approved with refinements below).

---

## 0. One-line summary

Add a deterministic, tenant-owned **release findings store** (`release_findings` +
append-only `release_finding_events`, migration `0022`) for **security** and **shortcut/fake-done**
findings (§13.4 / §920), with a DB-guarded one-way lifecycle, **critical = hard blocker (never
accepted)**, non-critical acceptance via a validated FK to `risk_acceptance_records`, and a
**conservative A5 hook** moving gates #5/#6 to `insufficient_evidence:no_finding_provenance_or_scan_source`
(**never pass**). Two real A5 evidence stores; **no scanner, no go-live, no shortcut.**

## 1. Hard constraints (must appear in the implementation)
No go-live enablement; gates #5/#6/#7 never pass; `a5_satisfied`/`can_go_live_autonomously` stay
false. No scanner / security-reviewer / shortcut-detector execution; no issue/release entity; no
evidence pack; no request-auth; no LLM; **no HTTP API** (no operator endpoint this slice).

## 2. Taxonomy (D-SF-1)
- `finding_type ∈ {security, shortcut}`; `severity ∈ {low, medium, high, critical}`.
- `category` validated against the type's allowed set (fail-closed), stable **snake_case**:
  - **security** (§916-920): `authz`, `injection`, `secrets_exposure`, `unsafe_tool`,
    `supply_chain`, `other`.
  - **shortcut** (§1298-1313): `hardcoded_value`, `static_response`, `fake_integration`,
    `disabled_validation`, `weakened_tests`, `error_swallowing`, `placeholder_ui`,
    `todo_in_required_path`, `local_only_substitute`, `acceptance_silently_skipped`,
    `tests_check_implementation`, `readiness_without_evidence`, `other`.
- `category="other"` is **not a silent escape hatch**: require a non-empty `summary` **and**
  non-empty `detail` when `category="other"` (validator-enforced).

## 3. Fields (D-SF-7)
`release_findings`: `id, tenant_id, project_id, finding_type, category, severity, summary, detail,
source, source_provenance, status, risk_acceptance_record_id (nullable), resolution_note (nullable),
detected_at, resolved_at (nullable), resolved_by (nullable), created_at, updated_at`.
- **Required on create:** `finding_type, category, severity, summary, source`.
- **Defaults:** `status='open'`, `source_provenance='caller_supplied_unverified'`,
  `detected_at=clock_timestamp()`, `created_at/updated_at=clock_timestamp()`.
- `source` is UNVERIFIED (e.g. `security_reviewer|shortcut_detector|manual`) — not authoritative.
`release_finding_events` (append-only): `id, tenant_id, finding_id, event_type, actor, created_at`
(composite FK pins to the finding's tenant).

## 4. Lifecycle + DB guard (D-SF-2/3/4) — exact mutability contract

States: **open → resolved | false_positive | accepted | superseded** (one-way; terminal states
never transition again). The **DB guard is the authoritative backstop** (`BEFORE INSERT OR UPDATE`),
so the column-mutability rules are explicit (no post-review tightening):

**On INSERT (all DB-guard-enforced — `uaid_app` has direct INSERT, so the validator is not the only
gate):** `status='open'`; `source_provenance='caller_supplied_unverified'`; `finding_type` valid;
`category` in the type's set; **all resolution/acceptance metadata must be NULL at creation** —
`risk_acceptance_record_id IS NULL`, `resolution_note IS NULL`, `resolved_at IS NULL`,
`resolved_by IS NULL`; and **the `other` escape-hatch rule is DB-enforced** — if
`category='other'`, then `summary` **and** `detail` must both be non-empty after trim
(`btrim(...) <> ''`).

**On UPDATE:**
- **Immutable always** (raise if changed): `id, tenant_id, project_id, finding_type, category,
  severity, summary, detail, source, source_provenance, detected_at, created_at`.
- **Status transition:** if `status` changes, `OLD.status` must be `open` and `NEW.status ∈
  {resolved,false_positive,accepted,superseded}`; if `status` unchanged, **no other field may
  change** (no out-of-band edits).
- **Per-transition mutable fields:**
  - `open → accepted`: may set `status, updated_at, risk_acceptance_record_id`. Requires
    `OLD.severity <> 'critical'` (**critical hard-block, D-SF-3**) and `risk_acceptance_record_id
    NOT NULL`; `resolution_note/resolved_at/resolved_by` must stay NULL. **Referenced record must be
    valid (D-SF-4):** a `risk_acceptance_records` row with that id where `tenant_id`=finding tenant,
    `project_id`=finding project, `status='active'`, `expiry_date >= CURRENT_DATE`,
    `blocking_category IS NULL`, and `issue_id = NEW.id::text`. (Same usability rule as the Slice-22
    A5 count — active **+ non-expired + non-blocking**.)
  - `open → resolved | false_positive | superseded`: may set `status, updated_at, resolution_note,
    resolved_at, resolved_by`; `risk_acceptance_record_id` must stay NULL.
- **No DELETE / no TRUNCATE** (block triggers). `release_finding_events` append-only
  (UPDATE/DELETE/TRUNCATE blocked).

CHECKs: `finding_type IN (...)`, `severity IN (...)`, `status IN (...)`. Category-per-type is
validator-enforced (app) + the guard's INSERT check.

## 5. Repository
`ReleaseFindingRepository(session, ctx)`: `create(*, project_id, payload, actor)` (validates via the
pure `app.release.findings` validators, inserts `open`, writes a `created` event + audit safe-metadata);
`resolve` / `mark_false_positive` / `supersede` (set `resolution_note`, `resolved_at`, `resolved_by`);
`accept(*, finding_id, risk_acceptance_record_id, actor)` (non-critical only; validates the record is
active+non-expired+non-blocking+same-tenant/project+`issue_id==str(finding_id)`); `get`;
`count_open(project_id, finding_type)`; `count_open_unaccepted_critical(project_id, finding_type)`.
Audit payload = ids/type/severity/status/category only — **never** summary/detail/resolution_note.

## 6. Pure validators
`app/release/findings.py`: `FINDING_TYPES`, `SEVERITIES`, `SECURITY_CATEGORIES`,
`SHORTCUT_CATEGORIES`, `STATUSES`, allowed transitions; `validate_new_finding(payload)` (required
fields, type, category-per-type, `other`-needs-summary+detail); `validate_transition(from,to)`;
`is_critical(severity)`. (Distinct module from Slice-13 `app/intake/findings.py` — D-SF-8.)

## 7. A5 hook (D-SF-5)
- `A5_RULESET_VERSION` bump `slice22.v1` → **`slice23.v1`**.
- Gates **#5 and #6** move from `no_evidence_source` to **`insufficient_evidence`**,
  reason `no_finding_provenance_or_scan_source`; **never pass** (a store can't prove absence of
  findings without authoritative scan coverage). Context (non-authorizing) on each gate:
  - #5: `{open_security_finding_count, open_unaccepted_critical_security_finding_count}`
  - #6: `{open_shortcut_finding_count, open_unaccepted_critical_shortcut_finding_count}`
- `evaluate_production_autonomy` gains the four count params (default 0, fail-closed).
  `ProductionAutonomyRepository.evaluate` wires them via `ReleaseFindingRepository`.
- **Gate-set golden update:** partial gates `{2,7,8,9,12}` → **`{2,5,6,7,8,9,12}`**; sourceless
  `{3,4,5,6,10,11,13}` → **`{3,4,10,11,13}`**; `passed_gate_count` still 1 at R5; `unmet_gates`
  still 12.

## 8. Migration `0022`
Tenant-owned `release_findings` (RLS ENABLE+FORCE + `tenant_isolation`; SELECT/INSERT/UPDATE, **no
DELETE**; type/severity/status CHECKs; composite FK `(project_id,tenant_id)→projects`;
`UNIQUE(id,tenant_id)` as the events FK target; nullable FK `risk_acceptance_record_id` →
`risk_acceptance_records(id,tenant_id)` composite) + append-only `release_finding_events`
(SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked; composite FK to the finding's tenant) + the
guard/lifecycle/no-delete triggers (§4). The guard's **INSERT** branch enforces (§4): `status='open'`,
unverified provenance, NULL resolution/acceptance metadata (`risk_acceptance_record_id`,
`resolution_note`, `resolved_at`, `resolved_by`), and the `category='other'` ⇒ non-empty
`summary`+`detail` rule. Additive — no change to existing tables. Downgrade drops both.

## 9. Tests first (TDD)

**Pure** (`tests/test_release_findings.py`): valid finding; missing each required field; bad
finding_type; category-not-in-type; `category="other"` without summary/detail; lifecycle transitions
(one-way, terminal-frozen); `is_critical`.

**DB guard (direct SQL via `rls_engine`)** — all must be refused:
1. INSERT with `status<>'open'`.
2. UPDATE `open→accepted` on a **critical** finding.
3. terminal-state re-transition (e.g. `resolved → accepted`).
4. UPDATE `open→accepted` with **no/invalid** `risk_acceptance_record_id` (missing, expired,
   blocking, wrong tenant/project, or `issue_id != finding.id`).
5. **cross-tenant** finding→risk-acceptance FK (accept referencing another tenant's record).
6. INSERT with `category='other'` and empty/NULL `detail` (or empty/NULL `summary`).
7. INSERT with non-NULL `resolution_note` (or non-NULL `resolved_at`/`resolved_by`/
   `risk_acceptance_record_id`) on an `open` finding.

**DB repository:**
8. create open finding; 9. resolve / false_positive / supersede; 10. accept a **non-critical**
finding with a valid active record; 11. reject critical accept; 12. reject accept with
expired/blocking/non-active record; 13. `count_open` + `count_open_unaccepted_critical` by type;
14. RLS deny-by-default + cross-tenant invisibility; 15. append-only events + immutable-content guard;
16. catalog grants (`release_findings` `{SELECT,INSERT,UPDATE}`, `release_finding_events`
`{SELECT,INSERT}`) + RLS `(t,t)`.

**A5 / API golden:**
17. pure engine: gates #5/#6 = `insufficient_evidence:no_finding_provenance_or_scan_source` with the
    four context counts; never `passed`; `ruleset_version == "slice23.v1"`; **gate-set golden using
    the literal test constants** — `PARTIAL_GATES == {2, 5, 6, 7, 8, 9, 12}` and
    `SOURCELESS_GATES == {3, 4, 10, 11, 13}` (the names the existing `tests/test_production_autonomy.py`
    uses); `passed_gate_count == 1` at R5; `len(unmet_gates) == 12`.
18. DB: `ProductionAutonomyRepository` wires the four counts into gates #5/#6 context; still not
    passing.
19. `tests/test_api.py` production-autonomy endpoint golden: `ruleset_version="slice23.v1"`; gates
    #5/#6 carry the new context; gate #7 unchanged.

## 10. Docs
`CLAUDE.md` (new `app/release/findings.py` + models + repo; migration `0022`; A5 gates #5/#6 status +
ruleset `slice23.v1`; counts) and `README.md` (a "Release findings" section); module docstrings
(non-authorizing, critical-hard-block, unverified source, no scanner). Note the local
`make test-db-drop` requirement (edited/new migration).

## 11. Risks & invariants
- **R-1 (authority safety):** gates #5/#6/#7 never pass; go-live stays false; critical findings can
  never be accepted. Tests 2/9/15.
- **R-2 (guard completeness):** per-transition column mutability is DB-enforced (no out-of-band
  edits) — tests 1-5,13 (avoids the Slice-22 post-review tightening).
- **R-3 (acceptance integrity):** accept requires a *usable* record (active+non-expired+non-blocking+
  same tenant/project+issue_id match). Tests 4,5,10.
- **R-4 (gate-set drift):** the golden gate-set move must keep passed=1 / unmet=12. Test 15.
- **Invariants:** fail-closed; tenant isolation (RLS); append-only events; no DELETE; audit
  safe-metadata only; no readiness (R0–R5) impact; no scanner/LLM/HTTP/go-live.

## 12. Verification
```bash
uv run ruff check .
make test
RLS_DB_PASSWORD=uaid_app make test-db   # locally: run `make test-db-drop` first (new migration 0022)
git diff --check
git status -sb
```
Expected: ruff clean; both suites green; diff-check clean; `git status` shows only the intended Slice
23 files (`app/release/findings.py`, `app/models/release_finding.py`, `app/models/release_finding_event.py`,
`app/repositories/release_findings.py`, `app/release/production_autonomy.py`,
`app/repositories/production_autonomy.py`, `migrations/versions/0022_release_findings.py`,
`tests/test_release_findings.py`, `tests/test_production_autonomy.py`, `tests/test_api.py`,
`README.md`, `CLAUDE.md`, the `.planning/SLICE-23-*` artifacts) plus local-only
`.planning/HANDOFF.json` / `.env`; nothing staged.

## 13. Next step after approval
Branch `feat/slice23-release-findings`; write all §9 tests first; then pure validators → models →
migration → repository → A5 hook → docs. Pause at green for review before PR. **No branch, no code
until approved.**
