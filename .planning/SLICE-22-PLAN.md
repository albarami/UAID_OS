# Slice 22 — Risk-acceptance records store + conservative A5 hook (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice22-risk-acceptance` off `main` @ `09e4d0c`; risk-acceptance store (`app/release/` +
models + repo), migration `0021` (DB guard enforces INSERT invariants + one-way transitions),
conservative A5 gate-#7 hook (`ruleset_version="slice22.v1"`, `GateResult.context`), tests, docs.
Verification (fresh DB): `ruff` clean, `make test` 219, `make test-db` 269. **No go-live; gate #7
never passes.** Note: local re-run requires `make test-db-drop` (edited `0021`); CI is fresh.
**Base:** `main` @ `09e4d0c` (clean).
**Rulings:** `.planning/SLICE-22-RISK-ACCEPTANCE-DISCUSSION.md` (D-RA-1..8, all approved with the
refinements below).

---

## 0. One-line summary

Add a deterministic, tenant-owned **risk-acceptance record store** (the §27.10 / §24.1 shape) with a
lifecycle (active/expired/revoked/superseded), **fail-closed hard refusals** (§24.1), unverified
signer identity, required expiry, one additive migration — plus a **conservative A5 gate-#7 hook**
that moves the gate from `no_evidence_source:risk_acceptance_records` to
`insufficient_evidence:no_open_issue_store` (**never passes**). One real A5 evidence source; **no
go-live enablement**.

## 1. Hard constraints (must appear in the implementation)

- **No go-live enablement** — `can_go_live_autonomously` / `a5_satisfied` stay hard-false.
- **No verified approval/signature** — `approver_provenance="caller_supplied_unverified"`.
- **No full gate-#7 pass** — gate #7 is `insufficient_evidence:no_open_issue_store` only.
- **No issue/release entity creation** — `issue_id`/`release_id` are free-form string refs.
- **No evidence-pack generation, no external integrations, no LLM, no HTTP API** (D-RA recommendation:
  no operator endpoint this slice).

## 2. File layout

- **Pure** `app/release/risk_acceptance.py`: constants + validators (no DB). `SEVERITIES`
  (`low|medium|high|critical`), `HARD_REFUSAL_CATEGORIES` (`critical_security_blocker`,
  `fake_done_finding`, `missing_production_rollback`, `missing_regulated_or_safety_authority`),
  `STATUSES` (`active|expired|revoked|superseded`), allowed one-way transitions;
  `validate_transition(from,to)`, `is_hard_refusal(category)`; and **`validate_new_record`** which
  rejects (fail-closed) when any of these is **missing or empty**:
  `release_id`, `issue_id`, `severity`, `reason_for_acceptance`, `business_impact`,
  `rollback_or_mitigation_plan`, `required_follow_up_ticket`, `expiry_date`, `owner`, `approver`,
  `accepted_by`, `approval_authority_source`. Additional rules:
  - `severity` must be in `SEVERITIES`;
  - `accepted_by` must be a **non-empty array**;
  - `approval_authority_source` must equal **`approval_matrix`** (this slice);
  - `blocking_category`, if set, must NOT be a hard-refusal category (else reject — D-RA-2 store-time).
- **Models** `app/models/risk_acceptance_record.py` + `app/models/risk_acceptance_event.py`.
- **Repository** `app/repositories/risk_acceptance.py`: `RiskAcceptanceRepository`.
- **Migration** `migrations/versions/0021_risk_acceptance.py` (additive; two tables).
- **A5 hook**: extend `app/release/production_autonomy.py` (gate #7) + `ProductionAutonomyRepository`
  to read the active-record count.

## 3. Record fields (D-RA-8, normalized to `expiry_date`)

`risk_acceptance_records`: `id`, `tenant_id`, `project_id`, `release_id`, `issue_id`, `severity`,
`affected_requirements` (jsonb array), `reason_for_acceptance`, `business_impact`,
`compensating_controls` (jsonb), `rollback_or_mitigation_plan`, `evidence_links` (jsonb),
`required_follow_up_ticket`, `included_in_release_notes` (bool), **`expiry_date` (required)**, `owner`,
`approver`, `accepted_by` (jsonb), `approval_authority_source`, `blocking_category` (nullable),
`status` (default `active`), `approver_provenance` (`caller_supplied_unverified`), `created_at`,
`updated_at`. **Only `expiry_date`** — no `expires_at` column (alias deferred).
`risk_acceptance_events`: append-only `(id, tenant_id, record_id, event_type, actor, created_at)`
pinned to the record's tenant/project.

## 4. Lifecycle (D-RA-4/D-RA-5)

- Create ⇒ `active` (requires `expiry_date`; rejects hard-refusal `blocking_category`).
- One-way terminal transitions from `active`: `revoke` → `revoked`, `supersede` → `superseded`,
  `expire_if_overdue` → `expired` (computed on-demand from `expiry_date`, like approval non-response).
- Terminal states never transition again. **No DELETE / no TRUNCATE.** Each transition writes a
  `risk_acceptance_events` row + an audit entry (safe metadata only — ids/severity/status, never
  reason/business_impact/evidence prose).
- **Record immutability (DB guard trigger):** after creation, the ONLY mutable columns are
  **`status`** and **`updated_at`**. A guard trigger rejects any UPDATE that changes any other column —
  immutable: `tenant_id`, `project_id`, `release_id`, `issue_id`, `severity`, `affected_requirements`,
  `reason_for_acceptance`, `business_impact`, `compensating_controls`, `rollback_or_mitigation_plan`,
  `evidence_links`, `required_follow_up_ticket`, `included_in_release_notes`, `expiry_date`, `owner`,
  `approver`, `accepted_by`, `approval_authority_source`, `blocking_category`, `approver_provenance`,
  `created_at`. (Mirrors the Slice-9 `documents_guard` / Slice-14a `extraction_proposals_guard`
  immutability pattern.)
- **Counting rule:** only `status=active` AND `expiry_date` in the future AND
  `blocking_category IS NULL` records are "active non-blocking" (the only ones the A5 hook may count
  as context).

## 5. A5 gate-#7 hook (D-RA-6) + ruleset bump

- **Ruleset bump:** `A5_RULESET_VERSION = "slice22.v1"` (was `slice21.v1`) — Slice 22 changes
  production_autonomy semantics (gate #7 moves category), so the version MUST bump.
- **`GateResult` gains a `context: dict` field (default `{}`)**, and `to_dict()` **always serializes
  a `"context"` key on every gate entry** (API-stable: gates with no context emit `"context": {}`).
  This is the single chosen shape (no "extension field" ambiguity).
- Pure engine `evaluate_production_autonomy` gains `active_risk_acceptance_count: int = 0`. Gate #7
  becomes **always**:
  ```json
  {
    "number": 7,
    "gate": "approved_risk_acceptance_records",
    "status": "insufficient_evidence",
    "reason": "no_open_issue_store",
    "context": { "active_risk_acceptance_count": 0 }
  }
  ```
  The count is **context only** — it never flips the status (gate #7 can never pass without an
  issue/findings store). All other gates serialize `"context": {}`.
- `ProductionAutonomyRepository.evaluate` reads `RiskAcceptanceRepository.count_active_nonblocking`
  and passes it as `active_risk_acceptance_count`. `a5_satisfied` / `can_go_live_autonomously` stay
  false.
- **Golden updates (Slice 21 tests):**
  - `tests/test_production_autonomy.py`: (a) gate #7 moves from the `no_evidence_source` set into the
    `insufficient_evidence` set — `SOURCELESS_GATES` drops 7, `PARTIAL_GATES` adds 7; (b) every gate
    entry now has a `context` key (update any gate-entry shape assertion); (c) the ruleset assertion
    changes `slice21.v1` → `slice22.v1`. `passed_gate_count` (1) and `unmet_gates` (12) unchanged.
  - **`tests/test_api.py` (the existing production-autonomy endpoint test
    `test_production_autonomy_endpoint_returns_report`):** update `ruleset_version` expectation
    `slice21.v1` → `slice22.v1`; account for the serialized `context` key on every gate entry; and
    (optionally) assert gate #7 is
    `{"status":"insufficient_evidence","reason":"no_open_issue_store","context":{"active_risk_acceptance_count":0}}`.

## 6. Tests first (TDD)

**Pure** (`tests/test_risk_acceptance.py`, Docker-free):
1. `test_valid_record_accepted` — well-formed record (with `expiry_date`, non-blocking) validates.
2. `test_missing_expiry_rejected` — no `expiry_date` ⇒ rejected (D-RA-5).
3. `test_invalid_severity_rejected` — severity outside the enum ⇒ rejected.
4. `test_hard_refusal_category_rejected` — each of the 4 hard-refusal categories ⇒ rejected at
   validation (D-RA-2).
5. `test_lifecycle_transitions` — active→revoked/superseded/expired valid; terminal→anything invalid;
   active→active invalid.
5b. `test_required_fields_enforced` — parametrized over each required field
   (`release_id, issue_id, severity, reason_for_acceptance, business_impact,
   rollback_or_mitigation_plan, required_follow_up_ticket, expiry_date, owner, approver, accepted_by,
   approval_authority_source`): missing/empty ⇒ rejected. Plus: empty `accepted_by` array ⇒ rejected;
   `approval_authority_source != "approval_matrix"` ⇒ rejected.

**DB repository** (`tests/test_risk_acceptance.py`, `@pytest.mark.db`):
6. `test_create_persists_active_and_audits_safely` — create ⇒ `active`; audit payload has
   ids/severity/status only (no reason/business_impact/evidence prose).
7. `test_revoke_and_supersede` — one-way transitions persist + write events; re-transition of a
   terminal record refused.
8. `test_expire_if_overdue` — a past `expiry_date` ⇒ `expired` on demand; never counted.
9. `test_hard_refusal_rejected_at_store_time` — store-time rejection of a hard-refusal
   `blocking_category` (D-RA-2 "both").
10. `test_count_active_nonblocking` — only active + future-expiry + non-blocking counted.
11. `test_rls_deny_by_default_and_cross_tenant` — no GUC ⇒ no rows; cross-tenant insert blocked;
    other tenant sees none.
12. `test_append_only_no_delete` — UPDATE of immutable columns / DELETE / event mutation refused;
    `risk_acceptance_events` append-only.
13. `test_catalog_grants_and_rls` — table grants `{SELECT,INSERT,UPDATE}` (records), `{SELECT,INSERT}`
    (events); RLS `(t,t)`.

**A5 hook** (`tests/test_production_autonomy.py`):
14. `test_gate7_is_insufficient_evidence_no_open_issue_store` — pure engine: gate #7 has
    `status="insufficient_evidence"`, `reason="no_open_issue_store"`, and
    `context == {"active_risk_acceptance_count": <int>}`; never `passed`; `a5_satisfied`/go-live false.
14b. `test_ruleset_is_slice22` — report `ruleset_version == "slice22.v1"`; every gate entry has a
    `context` key (gates without context ⇒ `{}`).
15. `test_db_gate7_reads_active_count` (`@pytest.mark.db`) — repo wires `count_active_nonblocking`
    into `context.active_risk_acceptance_count`; gate #7 stays `insufficient_evidence`; still not
    passing. Plus the golden updates (§5): `SOURCELESS_GATES` drops 7, `PARTIAL_GATES` adds 7, the
    ruleset assertion → `slice22.v1`, and gate-entry shape now includes `context`.

**API golden** (`tests/test_api.py`, `@pytest.mark.db`):
16. `test_production_autonomy_endpoint_returns_slice22_context_shape` — the endpoint returns
    `ruleset_version == "slice22.v1"`; every gate entry has a `context` key; gate #7 is
    `insufficient_evidence` / `no_open_issue_store` with `context.active_risk_acceptance_count`. Also
    update the existing `test_production_autonomy_endpoint_returns_report` (ruleset → `slice22.v1`,
    tolerate the `context` key) — §5.

TDD: write red first (module/migration absent), then implement.

## 7. Docs updates

- **`CLAUDE.md`:** new `app/release/risk_acceptance.py` + models + repo; migration `0021`; A5 gate-#7
  status change (now `insufficient_evidence:no_open_issue_store` with `context.active_risk_acceptance_count`);
  **`ruleset_version` bump `slice21.v1` → `slice22.v1`**; the new `GateResult.context` field;
  current-status line; test counts.
- **`README.md`:** a "Risk-acceptance records" section (store, lifecycle, hard refusals, unverified
  signer, A5 hook still fail-closed); note no HTTP API this slice.
- **Module docstrings:** state non-authorizing, unverified-signer, hard-refusal, no-go-live.

## 8. Migration (additive)

`migrations/versions/0021_risk_acceptance.py`: create `risk_acceptance_records` (tenant-owned,
ENABLE+FORCE RLS + `tenant_isolation`; SELECT/INSERT/UPDATE, **no DELETE**; severity + status CHECKs;
composite FK `(project_id, tenant_id)→projects`) + `risk_acceptance_events` (append-only:
SELECT/INSERT only + UPDATE/DELETE/TRUNCATE block triggers; composite FK pinning to the record's
tenant). Downgrade drops both. No change to existing tables.

## 9. Risks & invariants

**Risks**
- **R-1 (authority safety — headline):** must never become a verified approval or a go-live path.
  Mitigation: `approver_provenance` unverified; gate #7 can't pass; tests 14/15.
- **R-2 (hard-refusal bypass):** the 4 categories must be blocked at store time AND never counted.
  Tests 4/9/10.
- **R-3 (silent waiver):** missing/elapsed expiry must never count. Tests 2/8/10.
- **R-4 (Slice-21 regression):** the gate-#7 category move must not change `passed_gate_count`/
  `unmet_gates` totals or any other gate. Golden update + §5.

**Invariants**
- Fail-closed: invalid/expired/hard-refusal records never count; gate #7 never passes.
- Tenant isolation (RLS), append-only events, no DELETE; audit safe-metadata only.
- `can_go_live_autonomously` / `a5_satisfied` stay false.
- No issue/release entity, no HTTP API, no LLM, no external integration.

## 10. Verification commands

```bash
uv run ruff check .
make test
RLS_DB_PASSWORD=uaid_app make test-db
git diff --check
git status -sb
```
Expected: ruff clean; both suites green with new cases; diff-check clean; `git status` shows only
intended Slice 22 files (`app/release/risk_acceptance.py`, `app/models/risk_acceptance_record.py`,
`app/models/risk_acceptance_event.py`, `app/repositories/risk_acceptance.py`,
`app/release/production_autonomy.py`, `app/repositories/production_autonomy.py`,
`migrations/versions/0021_risk_acceptance.py`, `tests/test_risk_acceptance.py`,
`tests/test_production_autonomy.py`, `tests/test_api.py` (production-autonomy endpoint golden update),
`README.md`, `CLAUDE.md`, the `.planning/SLICE-22-*` artifacts)
plus local-only `.planning/HANDOFF.json` / `.env`; nothing staged.

## 11. Next step after approval

Create the Slice 22 branch; write all §6 failing tests first (pure 1–5b, DB repo 6–13, A5-hook
14/14b/15, API golden 16); then pure validators → models → migration → repository → A5 hook; then
docs. Pause at green for implementation review before PR. **Until then: no branch, no code.**
