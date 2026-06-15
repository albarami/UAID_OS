# Slice 24 — Open-issue / blocker store (A5 gate #7) — Discussion v0

**Status:** OPEN — awaiting coordinator rulings on D-OI-1..8 before any PLAN. No branch, no
migration, no code until PLAN approval.
**Base:** `main` @ `d16341f` (clean; only the intentional `.planning/HANDOFF.json` drift).
**Persona:** senior delivery-platform / release-governance architect.
**Goal:** lock the open-issue/blocker taxonomy, lifecycle, blocking semantics, risk-acceptance
interaction, relationship to the Slice-23 findings store, and the conservative A5 gate-#7 hook for a
**deterministic, tenant-owned open-issue/blocker store** — the fourth real A5 evidence source
(after Slice 22 risk-acceptance + Slice 23 findings). It must add genuine evidence **without** faking
A5, enumerating issues it cannot prove are complete, or enabling go-live.

Provenance (Sanad): every shape/rule claim cites a spec line or a source file; inferences are
labelled **(inference)**.

---

## 1. What the spec requires

- **Appendix B gate #7 (spec:2991):** A5 is allowed only if "any remaining open issues have
  **approved risk-acceptance records**." This is the gate this slice serves.
- **§24.1 go-live gate (spec:2266):** "remaining open issues are either **non-blocking** or **covered
  by explicit risk-acceptance records**." → an issue carries a *blocking* property; the gate is
  satisfied per-issue by (non-blocking) **OR** (active risk-acceptance record).
- **§24.1 exception path (spec:2271):** "A release may proceed with known open issues only when
  **every** remaining issue has a risk-acceptance record signed by the approvers named in the approval
  matrix. Risk acceptance is **not allowed** for unresolved critical security blockers, fake-done
  findings, missing production rollback, or missing authority for regulated/safety-critical
  obligations…" → the same hard-refusal set already encoded in
  `app/release/risk_acceptance.py:26-31` (`HARD_REFUSAL_CATEGORIES`).
- **§24.1 record shape (spec:2274-2284):** a `risk_acceptance_record` references an **`issue_id`**
  (e.g. `RISK-042`), `severity`, `required_follow_up_ticket`, `expires_at`. Slice 22 already stores
  `issue_id` as a **free, unverified string** (`app/release/risk_acceptance.py:45-58`). This slice
  gives that `issue_id` a **real referent** (a `release_issues` row).
- **§24.2 governance checklist (spec:2328):** `open_issues_have_risk_acceptance:
  required_if_any_open_issues`.
- **§24.3 release verdicts (spec:2336-2338):** `passed` / `passed_with_limitations` /
  `failed_blocking_issue` — confirms the blocking-vs-non-blocking axis as the load-bearing
  distinction for open issues.

## 2. The honest dependency reality (why gate #7 will NOT pass this slice)

Gate #7 reads "**any remaining** open issues have approved risk-acceptance records." Proving that
truthfully needs two things a store alone cannot supply:

1. **Issue provenance / completeness** — confidence the issue set is *complete*. Issues are produced
   by reviewers / CI / verifiers / scanners that **do not run** (Phase 3/5/6). A store with N rows
   cannot prove there are no undetected open issues. **(inference)**
2. **Release binding** — knowing *which* issues belong to *this release*. No release/issue-tracker
   entity exists; without it "remaining open issues *for this release*" is unscoped. **(inference)**

So gate #7 moves from `insufficient_evidence:no_open_issue_store` → **`insufficient_evidence:
no_issue_provenance_or_release_binding`** and **never passes** this slice. Counts become *context
only*. This mirrors the Slice-23 reasoning for gates #5/#6 (an empty findings store ≠ "clean").
Honest, fail-closed.

## 3. Decisions to resolve

### D-OI-1 — Naming
**Recommend:** `release_issues` + append-only `release_issue_events`.
*Justification:* mirrors the Slice-23 `release_findings` / `release_finding_events` pair; the
`release_` prefix groups the A5/release-gate evidence stores (findings, issues) and keeps them
clearly distinct from the Slice-13 `intake_findings_reports` (structural intake gaps, descriptive)
and the Slice-12/16 `readiness_reports`. *(Confirm name.)*

### D-OI-2 — Taxonomy
- `issue_category` — coarse blocker dimension, grounded in the Appendix-B / §24.1 gate axes
  **(inference: mapped to gate dimensions, not a verbatim spec list):**
  `security`, `shortcut`, `test_or_acceptance`, `cost`, `deployment`, `rollback`, `monitoring`,
  `evidence`, `approval`, `other`. `other` is **not a silent escape hatch** — it requires non-empty
  `summary` + `detail` (mirror Slice-23 D-SF-1 `other` rule).
- `severity` ∈ `{low, medium, high, critical}` (reuse the Slice-22/23 enum).
- Validate `issue_category` and `severity` against the allowed sets (fail-closed).
*(Ruling needed on the category set. Note the deliberate overlap of `security`/`shortcut` with the
Slice-23 findings store — see D-OI-6 for how we avoid double-counting.)*

### D-OI-3 — Lifecycle
States: **open / resolved / accepted / superseded**. One-way from `open`:
- `resolved` (fixed/closed), `accepted` (real, non-blocking-or-risk-accepted — see D-OI-4/5),
  `superseded` (replaced/duplicate folded here). Terminal states never transition again.
- Append-only `release_issue_events` trail + DB-guarded immutability (mirror Slice 22/23: only
  `status` + resolution fields + `updated_at` mutable per transition; no DELETE/TRUNCATE).
*(Open question: do we also want a `false_positive` terminal as in Slice-23 findings? An "issue" is a
human/agent-asserted blocker rather than a detector signal, so `false_positive` is arguably less apt
than `superseded`/`resolved`. Recommend omit; confirm.)*

### D-OI-4 — Blocking + hard-blocker semantics (the crux)
- Each issue carries **`blocking`** (bool) — is it release-blocking (§24.1)?
- Optional **`blocking_category`** (nullable). When set to a value in
  `HARD_REFUSAL_CATEGORIES` (`risk_acceptance.py:26-31` — critical security blocker / fake-done /
  missing production rollback / missing regulated-or-safety authority), the issue **can never be
  `accepted`** (spec:2271). It may only be `resolved` or `superseded`.
- **(inference, fail-closed):** a `critical`-severity blocking issue is treated as a hard blocker
  even without an explicit `blocking_category` — recommend `critical` ⇒ not acceptable, parallel to
  Slice-23 D-SF-3 (critical findings can never be accepted). *(Confirm whether the hard-block trigger
  is `blocking_category ∈ hard-refusals` only, or also `severity == critical`.)*

### D-OI-5 — Risk-acceptance interaction
- An `accepted` issue carries a FK `risk_acceptance_record_id` → `risk_acceptance_records(id,
  tenant_id)` (same tenant/project). The `accept` transition requires:
  (a) the issue is **not** a hard blocker (D-OI-4), and
  (b) the referenced record is **usable** — `active`, non-expired, non-blocking
  (`blocking_category` NULL on the record), same tenant+project, and **`record.issue_id ==
  issue.id`** — exactly the Slice-23 "usable record" rule (`repositories/release_findings.py:68-83`
  + the migration `0022` DB guard).
- This **closes the Slice-22 loop:** the risk-acceptance record's free-string `issue_id` now points
  at a real `release_issues.id`. *(We do NOT add a reverse FK on the older `risk_acceptance_records`
  table; the issue→record FK + the DB guard mirror the proven findings pattern. Confirm direction.)*

### D-OI-6 — Relationship to the Slice-23 findings store
**Recommend (separate, no bridge this slice):**
- `release_issues` is the **general blocker ledger** for gate #7's "any remaining open issues";
  `release_findings` remains the **specialized** security/shortcut detector-evidence sub-store
  (gates #5/#6). They stay **separate tables** with **no auto-creation** and **no FK bridge** this
  slice.
- To avoid **double-counting** in gate #7, the gate-#7 context counts come from `release_issues`
  **only** (not from `release_findings`). A future "bridge" slice can let a finding spawn/link an
  issue; explicitly deferred.
*(This is the central composition question the coordinator flagged. Confirm: separate now, bridge
later, no double-count.)*

### D-OI-7 — A5 gate-#7 hook (conservative)
- Gate #7 reason: `insufficient_evidence:no_open_issue_store` → **`insufficient_evidence:
  no_issue_provenance_or_release_binding`** — **never passes** this slice (§2).
- `context` (recorded, non-passing): `open_issue_count`, `open_blocking_issue_count`,
  `open_unaccepted_blocking_issue_count`. (Keep the existing `active_risk_acceptance_count` too.)
- `production_autonomy` `ruleset_version` bump `slice23.v1` → **`slice24.v1`**; reuse the existing
  `GateResult.context`. No other gate changes.
*(Confirm the new reason string + the context-count set. Gate #7 must NOT pass.)*

### D-OI-8 — Persistence / DB guard / fields / audit
- **`release_issues`** (tenant-owned): `id, tenant_id, project_id, issue_category, severity,
  blocking (bool), blocking_category (nullable), summary (short prose), detail (nullable prose),
  source (e.g. manual|reviewer|verifier — UNVERIFIED), source_provenance
  (`caller_supplied_unverified`), status, risk_acceptance_record_id (nullable FK), resolution_note
  (nullable prose), resolved_by (nullable, untrusted), resolved_at (nullable), created_at,
  updated_at`. `created_at`/`updated_at` via `clock_timestamp()`.
- **`release_issue_events`** (append-only): `id, tenant_id, issue_id, event_type, actor, created_at`.
- **RLS** ENABLE+FORCE + `tenant_isolation`; grants SELECT/INSERT/UPDATE, **no DELETE**;
  type/severity/status/category CHECKs; nullable composite FK → `risk_acceptance_records`.
- **DB guard trigger** (authoritative backstop, mirror migration `0022`): INSERT invariants
  (status=open, unverified provenance, NULL resolution/acceptance metadata, category-per-set,
  `other`⇒summary+detail) + per-transition column mutability + one-way lifecycle +
  **hard-blocker-cannot-be-accepted** + **accepted-requires-usable-risk-acceptance-record**;
  no DELETE/TRUNCATE on both tables.
- One additive migration **`0023_release_issues.py`** (no change to existing tables except — TBD —
  whether the FK target already exists on `risk_acceptance_records`; it has `UNIQUE(id, tenant_id)`?
  *to verify at PLAN time*).
- **Audit safe-metadata only** (ids / category / severity / blocking / status — **never**
  summary/detail/resolution prose), mirror `repositories/release_findings.py:147-162`.
- **No readiness impact:** this slice does not touch the R0–R5 ladder or `readiness_reports`.
*(Confirm field set + migration number + the FK-target check deferred to PLAN.)*

## 4. Out of scope (held)
- Issue **provenance/completeness** (no reviewer/CI/verifier/scanner execution); the
  findings→issue **bridge**; any **release entity / issue-tracker** integration; external scanners /
  CI / Phase-3+ integrations; HTTP API; request-auth / verified signatures; **go-live enablement**;
  LLM; evidence pack; making gate #7 pass.

## 5. Coordinator rulings needed before a PLAN
- **D-OI-1** table names (`release_issues` / `release_issue_events`).
- **D-OI-2** taxonomy (`issue_category` set, severity, `other` rule, fail-closed validation).
- **D-OI-3** lifecycle states + one-way transitions + append-only events + immutability;
  `false_positive` yes/no.
- **D-OI-4** blocking + hard-blocker semantics; is the hard-block trigger `blocking_category ∈
  hard-refusals` only, or also `severity == critical`?
- **D-OI-5** issue→`risk_acceptance_records` FK + usable-record accept rule (closes the Slice-22
  `issue_id` loop); confirm FK direction.
- **D-OI-6** relationship to Slice-23 findings: separate stores, **no bridge this slice**, gate-#7
  counts from `release_issues` only (no double-count).
- **D-OI-7** conservative A5 hook → `insufficient_evidence:no_issue_provenance_or_release_binding`
  (never passes), context counts, `ruleset_version` → `slice24.v1`.
- **D-OI-8** persistence shape + DB guard + field set + additive migration `0023` + audit
  safe-metadata-only + no readiness impact.

## 6. Recommendation
Build the deterministic, tenant-owned **open-issue / blocker store** (`release_issues` +
append-only `release_issue_events`, RLS, no-DELETE, DB-guarded one-way lifecycle) with a coarse
gate-axis `issue_category` taxonomy, **blocking + hard-blocker semantics** (hard blockers can never
be accepted, per spec:2271), non-blocker acceptance via a **usable** `risk_acceptance_records` link
(closing the Slice-22 `issue_id` loop), kept **separate** from the Slice-23 findings store (no bridge
yet, no double-count), and a **conservative A5 gate-#7 hook** that stays
`insufficient_evidence:no_issue_provenance_or_release_binding` and **never passes**. Gate #7 gets a
real evidence *store* with **no issue provenance, no release binding, no go-live, no shortcut**.
**Pausing for rulings on D-OI-1..8 before any PLAN.**
