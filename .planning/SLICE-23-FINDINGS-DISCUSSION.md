# Slice 23 — Security / shortcut (fake-done) findings store — Discussion v0

**Status:** RESOLVED — historical record. Rulings D-SF-1..8 ruled by the coordinator and implemented
in Slice 23 (see `.planning/SLICE-23-PLAN.md`). Outcome: tenant-owned `release_findings` +
append-only `release_finding_events` (migration `0022`); §13.4/§916-920 taxonomy + `other` rule;
DB-guarded one-way lifecycle; **critical findings can never be accepted**; non-critical acceptance via
a usable `risk_acceptance_records` link; conservative A5 gates #5/#6 stay
`insufficient_evidence:no_finding_provenance_or_scan_source`; go-live never enabled.
**Base:** `main` @ `13885f2` (clean).
**Persona:** senior security/governance + delivery-platform architect.
**Goal:** lock the finding taxonomy, lifecycle, risk-acceptance interaction, and the conservative A5
gate-#5/#6 hook for a **deterministic, tenant-owned security/shortcut findings store** — the next
real A5 evidence source. It must add genuine evidence **without** faking A5, scanning, or enabling
go-live.

Provenance (Sanad): every shape/rule claim cites a spec line; inferences are labelled.

---

## 1. What the spec requires

- **Appendix B (spec:2989-2990):** A5 needs "no **unaccepted** critical security findings are open"
  and "no **unaccepted** critical shortcut findings are open."
- **§24.1 go-live gate (spec:2260-2261):** "no critical security finding is open **and** no critical
  shortcut finding is open."
- **§24.1 hard refusals (spec:2271):** risk acceptance is **not allowed** for "unresolved critical
  security blockers, fake-done findings…" — so **critical security/shortcut findings cannot be
  risk-accepted; they must be resolved.** (Reconciles the two: critical ⇒ resolve, never accept;
  lower severities ⇒ may be accepted.)
- **§13.4 shortcut checklist (spec:1300-1314):** the shortcut taxonomy — hardcoded values, static
  responses, fake integrations, disabled validation, removed/weakened tests, broad error swallowing,
  placeholder UI, TODOs in required paths, local-only substitutes, AC silently skipped, tests that
  check implementation not behavior, claims of readiness without evidence.
- **§920 security reviewer:** security categories — authz flaws, prompt injection, secrets exposure,
  unsafe tools, supply-chain risk; "severity classification."
- **§13.3 finding shape (spec:1286-1294):** `suspected_shortcuts`, `required_changes`, `can_merge`.
- **§2.1 No fake done:** the creed behind "shortcut/fake-done" findings.

## 2. The honest dependency reality (why gates #5/#6 won't pass this slice)

A findings store records findings and their resolution/acceptance — but **"no critical findings exist"
requires authoritative scan coverage** (security reviewer + shortcut detector actually run), which is
**out of scope** (no scanner/LLM). **Inference (labelled):** an empty store ≠ "clean" — undetected
findings can't be ruled out. So gates #5/#6 move from `no_evidence_source:{security,shortcut}_findings`
to **`insufficient_evidence:no_finding_provenance_or_scan_source`** and **never pass** this slice.
Honest, fail-closed.

## 3. Decisions to resolve

### D-SF-1 — Taxonomy
- `finding_type` ∈ `{security, shortcut}`.
- `severity` ∈ `{low, medium, high, critical}` (reuse the risk-acceptance enum).
- `category` (per type): **security** = `authz`, `injection`, `secrets_exposure`, `unsafe_tool`,
  `supply_chain`, `other` (§920); **shortcut** = the §13.4 list (e.g. `hardcoded_value`,
  `static_response`, `fake_integration`, `disabled_validation`, `weakened_tests`,
  `error_swallowing`, `placeholder_ui`, `todo_in_required_path`, `local_only_substitute`,
  `acceptance_silently_skipped`, `tests_check_implementation`, `readiness_without_evidence`).
  *Recommend:* validate `category` against the type's allowed set (fail-closed).

### D-SF-2 — Lifecycle
States: **open / resolved / false_positive / accepted / superseded**. One-way from `open`:
- `resolved` (fixed), `false_positive` (not a real finding), `accepted` (real but risk-accepted —
  see D-SF-3/4), `superseded` (replaced). Terminal states never transition again. Append-only
  event trail + DB-guarded immutability (mirror Slice 22: only `status` + `updated_at` mutable; no
  DELETE/TRUNCATE; append-only events).

### D-SF-3 — Critical findings are hard blockers (the crux)
**Recommend:** a **critical** security or shortcut finding **cannot be `accepted`** (matches §24.1
hard refusals + Slice-22 D-RA-2). It may only become `resolved` or `false_positive`. Only
**non-critical** (low/medium/high) findings may be `accepted`. This keeps Appendix B #5/#6 and §24.1
consistent and fail-closed. *(Ruling needed; this is the central safety rule.)*

### D-SF-4 — Risk-acceptance interaction
**Recommend:** an `accepted` finding carries a FK `risk_acceptance_record_id` →
`risk_acceptance_records(id, tenant_id)` (same tenant/project). Accept transition requires: severity
non-critical (D-SF-3) **and** the referenced record exists and is `active`. The finding's `id` is the
natural `issue_id` a risk-acceptance record references (closing the Slice-22 loop). *(Confirm the FK
direction: finding→record. Note: a record's hard-refusal `blocking_category` already blocks critical
acceptance on the record side too — defense in depth.)*

### D-SF-5 — A5 gate-#5/#6 hook (conservative)
Per §2, both gates become `insufficient_evidence:no_finding_provenance_or_scan_source` and **never
pass** this slice. Context (recorded, non-passing): counts of `open` and `open_unaccepted_critical`
security/shortcut findings. They flip to evaluable only once authoritative scan provenance + complete
coverage exist (future slice). *Recommend: add the conservative hook now.* (Adds gate context →
`production_autonomy` `ruleset_version` bump, e.g. `slice23.v1`, + the existing `GateResult.context`.)

### D-SF-6 — Persistence
Tenant-owned `findings` (name TBD — e.g. `release_findings` to avoid clashing with the Slice-13
`intake_findings_reports`) + append-only `release_finding_events`; ENABLE+FORCE RLS; SELECT/INSERT/
UPDATE, **no DELETE**; severity/type/status/category CHECKs; DB guard (immutable content + one-way
lifecycle + critical-cannot-be-accepted). One additive migration (`0022`). Audit safe-metadata only
(ids/type/severity/status/category — never the finding description/evidence prose).

### D-SF-7 — Fields
`id, tenant_id, project_id, finding_type, category, severity, title/summary (short), detail (prose),
source (e.g. security_reviewer|shortcut_detector|manual — UNVERIFIED), source_provenance
(`caller_supplied_unverified`), status, risk_acceptance_record_id (nullable), resolution_note
(nullable), created_at, updated_at`. *Confirm.* (Detail/title are prose ⇒ never in audit.)

### D-SF-8 — Scope boundary vs Slice 13 / readiness
These are **release-blocker** findings (A5), distinct from Slice-13 `intake_findings_reports`
(structural intake gaps, descriptive, no readiness claim). This slice does **not** touch the R0–R5
readiness ladder. *Confirm the separation + the table name.*

## 4. Out of scope
- Scanner / security-reviewer / shortcut-detector **execution** (no real detection); LLM; evidence
  pack; issue tracker / release entities; go-live enablement; request-auth.

## 5. Coordinator rulings needed before a PLAN
- **D-SF-1** taxonomy (type, severity, per-type category sets, fail-closed validation).
- **D-SF-2** lifecycle states + one-way transitions + append-only events + immutability guard.
- **D-SF-3** critical = hard blocker (cannot be accepted) — confirm.
- **D-SF-4** finding→`risk_acceptance_records` FK; accept requires non-critical + active record.
- **D-SF-5** conservative A5 hook → `insufficient_evidence:no_finding_provenance_or_scan_source`
  (never passes), `ruleset_version` bump, context counts.
- **D-SF-6** persistence shape + table name (`release_findings`?) + additive migration `0022`.
- **D-SF-7** field set.
- **D-SF-8** separation from Slice-13 intake findings + no readiness impact.

## 6. Recommendation
Build the deterministic, tenant-owned **release findings store** (RLS, no-DELETE, DB-guarded one-way
lifecycle, append-only events) with the §13.4/§920 taxonomy, **critical = hard blocker (never
accepted)**, non-critical acceptance via a FK to `risk_acceptance_records`, and a **conservative A5
gate-#5/#6 hook** that stays `insufficient_evidence:no_finding_provenance_or_scan_source`. Two real
gates get an evidence *store* with **no scanner, no go-live, no shortcut**. **Pausing for rulings on
D-SF-1..8 before any PLAN.**
