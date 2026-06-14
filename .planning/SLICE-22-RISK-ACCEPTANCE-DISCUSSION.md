# Slice 22 — Risk-acceptance records — Discussion v0

**Status:** RESOLVED — historical record. Rulings D-RA-1..8 ruled by the coordinator and implemented
in Slice 22 (see `.planning/SLICE-22-PLAN.md`). Outcome: deterministic tenant-owned store
(`risk_acceptance_records` + append-only `risk_acceptance_events`, migration `0021`); hard refusals
blocked outright (store-time + DB guard + never-counted); required `expiry_date`; unverified signer;
one-way lifecycle (DB-enforced); conservative A5 gate-#7 hook stays `insufficient_evidence:no_open_issue_store`;
go-live never enabled.
**Base:** `main` @ `09e4d0c` (clean).
**Persona:** senior security/governance + delivery-platform architect.
**Goal:** lock authority semantics, lifecycle, and the A5 gate-#7 hook for a **deterministic,
tenant-owned risk-acceptance record store** — one real A5 evidence source — before any PLAN. It must
add a genuine evidence source **without** faking A5 or enabling go-live.

Provenance (Sanad): every shape/rule claim is cited to a spec line or the schema asset; inferences
are labelled.

---

## 1. What the spec requires

- **§24.1 go-live gate (spec:2266):** a release may proceed with known open issues only when "every
  remaining issue has a **risk-acceptance record signed by the approvers named in the approval
  matrix**."
- **§24.1 hard refusals (spec:2271):** risk acceptance is **not allowed** for — *unresolved critical
  security blockers, fake-done findings, missing production rollback, or missing authority for
  regulated/safety-critical obligations* — **unless** the relevant human authority explicitly accepts
  the risk **and** the autonomy policy permits that override.
- **Appendix B gate #7 (spec:2991):** "any remaining open issues have approved risk-acceptance
  records" — the A5 gate this slice targets.
- **Canonical record shape — §27.10 / `schemas/risk_acceptance_record.yaml`** (identical): `id`,
  `release_id`, `issue_id`, `severity` (low|medium|high|critical), `affected_requirements[]`,
  `reason_for_acceptance`, `compensating_controls[]`, `expiry_date`, `owner`, `approver`,
  `approval_authority_source: approval_matrix`, `rollback_or_mitigation_plan`, `evidence_links[]`.
  **§24.1 adds:** `business_impact`, `accepted_by[]`, `required_follow_up_ticket`,
  `included_in_release_notes`.
- **§ spec:3028:** "Go-live risk-acceptance path … with **signed records and expiry/follow-up
  controls**." Evidence packs carry `risk_acceptances[]` (§27.11, spec:2787).

## 2. The honest dependency reality (why this is a store, not a gate-flip)

A5 gate #7 = "**all remaining open issues** are covered by active accepted records." But there is **no
issue/findings store** today (the security/shortcut findings store is a *separate, later* slice). So
even with a real risk-acceptance store, the evaluator **cannot know the full open-issue set** and
therefore **cannot pass gate #7**. **Inference (labelled):** this slice builds the real evidence
*store* and a conservative evaluator hook; gate #7 moves from `no_evidence_source:risk_acceptance_records`
to **`insufficient_evidence:no_open_issue_store`** — still fail-closed, never passing. No shortcut.

## 3. Decisions to resolve

### D-RA-1 — Gate/record scope (what can be risk-accepted)
Records reference an `issue_id` and `release_id` as **free-form external string refs** this slice (no
issue/release entity exists). `affected_requirements[]` MAY reference real spine artifact refs.
*Recommend:* accept records for any caller-supplied issue ref **except** the hard-refusal categories
(D-RA-2); validate shape + severity enum; do not pretend to enumerate "all open issues".

### D-RA-2 — Hard refusals (fail-closed, the core safety rule)
Per §24.1 (spec:2271), a record for any of these categories must be **refused / never counted**:
critical **security** blocker, **fake-done** finding, **missing production rollback**, **missing
authority** for regulated/safety-critical obligations. The spec's "unless human authority explicitly
accepts AND autonomy policy permits" override needs **verified authority + an autonomy-override
path that do not exist yet**. *Recommend (ruling needed):* in this slice the override is
**unavailable** → these categories are **hard-blocked outright** (a record cannot accept them; if
recorded, the A5 hook never counts it). A `blocking_category` field (caller-supplied, **untrusted**)
lets the evaluator recognise and refuse them. *(Confirm: store-time rejection vs evaluator-time
non-counting vs both. Recommend both — reject at store time for the known categories, and the
evaluator never counts them regardless.)*

### D-RA-3 — Approver identity (unverified until request-auth)
Store `accepted_by[]` / `approver` / `owner` and `approval_authority_source`, but — exactly as the
broker/approval engines already do — mark signer identity **unverified** (e.g.
`approver_provenance="caller_supplied_unverified"`) until request-auth lands. The A5 hook treats
records as **not authority-verified**; this ties to the A5 request-auth prerequisite (Slice 21
discussion §6). *Recommend: store + label unverified; never treat as a verified human signature.*

### D-RA-4 — Lifecycle
States: **active / expired / revoked / superseded**. Mirror the approval-engine pattern
(state machine + append-only event trail). *Recommend:* one-way transitions (active→{expired,
revoked,superseded}); `revoke`/`supersede` are reviewer actions; `expired` is computed from
`expiry_date` (on-demand, like approval non-response). No record is ever DELETEd.

### D-RA-5 — Expiry (required vs optional)
*Recommend: REQUIRED* `expiry_date` (matches spec:3028 "expiry/follow-up controls"). An accepted
risk without an expiry is a permanent silent waiver — unsafe. Fail-closed: no expiry ⇒ rejected.

### D-RA-6 — A5 gate-#7 integration (conservative hook)
Per §2, gate #7 **cannot pass** this slice. The hook reports `insufficient_evidence:no_open_issue_store`
and (context) how many **active, non-blocking** accepted records exist. It flips to evaluable only
once a findings/issue store exists (later slice) AND every open issue has an active accepted record.
*Recommend: add the conservative hook now; gate stays fail-closed.*

### D-RA-7 — Persistence
Tenant-owned `risk_acceptance_records` table; **ENABLE+FORCE RLS + tenant_isolation**; SELECT/INSERT/
UPDATE (no DELETE); lifecycle via status + append-only event rows (like `approval_events`); audit
**safe metadata only** (ids/severity/status — never reason/business_impact/evidence prose). Needs a
**migration** (new table) — the first since Slice 20. *Recommend: yes, one additive migration.*

### D-RA-8 — Record fields (union of §27.10 + §24.1)
`id`, `issue_id`, `release_id`, `severity`, `affected_requirements[]`, `reason_for_acceptance`,
`business_impact`, `compensating_controls[]`, `rollback_or_mitigation_plan`, `evidence_links[]`,
`required_follow_up_ticket`, `included_in_release_notes`, `expiry_date` (required), `owner`,
`accepted_by[]`/`approver`, `approval_authority_source`, `blocking_category` (nullable), `status`,
`approver_provenance` (unverified), timestamps. *Confirm the field set.*

## 4. Out-of-scope

- The issue/findings store (separate slice) — so gate #7 stays fail-closed.
- Request-auth / verified approver identity; the §24.1 human-authority **override** path.
- Evidence-pack generation; release entities; any go-live enablement.
- LLM, external integrations.

## 5. Coordinator rulings needed before a PLAN

- **D-RA-1** record scope (free-form issue/release refs; spine refs for affected requirements).
- **D-RA-2** hard refusals — confirm **hard-blocked outright this slice** (no override), and
  store-time reject **and** evaluator never-count.
- **D-RA-3** store approver identity but mark **unverified**.
- **D-RA-4** lifecycle states + one-way transitions + append-only events.
- **D-RA-5** expiry **required** (recommended).
- **D-RA-6** conservative A5 gate-#7 hook → `insufficient_evidence:no_open_issue_store` (never passes
  this slice).
- **D-RA-7** persistence shape + the additive migration.
- **D-RA-8** confirm the field set (§27.10 ∪ §24.1).

## 6. Recommendation

Build the **real, deterministic, tenant-owned risk-acceptance store** (RLS, no-DELETE, lifecycle +
audited events) with the §27.10/§24.1 fields and **fail-closed hard refusals**, plus a **conservative
A5 gate-#7 hook** that stays `insufficient_evidence` until an issue/findings store exists. This adds
one genuine A5 evidence source with **no shortcut and no go-live enablement**. **Pausing for rulings
on D-RA-1..8 before any PLAN.**
