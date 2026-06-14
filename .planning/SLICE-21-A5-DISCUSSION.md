# Slice 21 — A5 / Appendix-B production autonomy — Discussion v0

**Status:** RESOLVED — historical record. Rulings D-A5-1..5 ruled by the coordinator and
implemented in Slice 21 (see `.planning/SLICE-21-PLAN.md`). Outcome: Option A (fail-closed,
non-authorizing A5 evaluator skeleton); only gate #1 (R5) passes, #2/#8/#9/#12
`insufficient_evidence`, the rest `no_evidence_source`; separate `production_autonomy` report;
`can_go_live_autonomously` hard-false; compute-on-read (no table/migration, D-21-A).
**Base:** `main` @ `e745e26` (clean).
**Persona:** senior delivery-platform / production-release architect.
**Goal:** decide whether/how the A5 production-autonomy gate (the go-live authority) can be made
deterministic and **fail-closed**, given that most of its evidence sources do not exist yet. This is
a discussion, not a plan — A5 depends on multiple unbuilt subsystems.

Provenance note (Sanad): every "exists / missing" claim below is sourced to a spec line or to the
`CLAUDE.md` "What exists" inventory; inferences are labelled.

---

## 1. What A5 is, and why R5 ≠ go-live

- **A5 (spec §5.1, spec:470):** "Conditional production autonomy — system can deploy production only
  if **all pre-approved gates pass and no blocker exists**." Deploy-production authority is A4/A5 +
  human approval **or** a pre-approved A5 gate (spec:485).
- **A fully autonomous go-live run needs R5 AND A5** (spec:41). **R5 is intake/package completeness;
  A5 is production *authority + evidence*.** They are orthogonal: a project can be R5 (intake
  complete — Slice 20) yet nowhere near A5 (no passing tests, no verified rollback, no monitoring).
  That is exactly why `can_go_live_autonomously` is hard-false today and must stay so until A5 is
  genuinely satisfied — anything else is "fake done" (spec §2.1 creed).
- **Appendix B (spec:2983-2997)** lists **13 conditions** that must ALL hold for A5.

## 2. The 13 A5 gates → evidence source map (the core finding)

Legend: ✅ built and gate-passing · ⚠️ partial **context only — does NOT pass the gate** (gate stays
fail-closed) · ❌ no evidence source today. **Crucially, a ⚠️ primitive is never sufficient to pass
its A5 gate** — A5 requires real production-autonomy evidence, so every gate below except #1 remains
fail-closed.

| # | Appendix-B gate (spec:2985-2997) | What exists (context only unless ✅) | Status |
|---|---|---|---|
| 1 | R5 intake complete | readiness auditor R5 (Slice 20) | ✅ built |
| 2 | production deployment target available | `environments_and_deployment_targets` is an R5 **declaration/presence** signal, **not** proof of a live/reachable production target | ⚠️ context only; **gate fail-closed** until a real deployment-target/connectivity source exists (Phase 3 §26.3) |
| 3 | branch protection + required checks active | — (source-control/CI integration) | ❌ Phase 3 (§26.3) |
| 4 | all critical test oracles **pass** | spine has `test_oracle` *artifacts*; **no execution/pass results** | ❌ Phase 5 (§26.5; "no oracle, no go-live" §14.4) |
| 5 | no unaccepted critical **security** findings | existing `intake_findings_reports` store (`findings.py`) holds **structural intake gaps/contradictions only**; **no security-findings store** with severity / accepted / open status | ❌ Phase 5 / secure-phase |
| 6 | no unaccepted critical **shortcut** findings | **no shortcut/fake-done findings store or acceptance workflow**; the existing intake findings are **not** release-blocker findings | ❌ Phase 5 (§26.5) |
| 7 | open issues have approved **risk-acceptance** records | `schemas/` has a risk-acceptance *schema* asset; **no engine/store** | ❌ Phase 5/6 |
| 8 | no unapproved **generated AC** in critical gates | AC provenance + `system_authored_unapproved` class (spec:653); extraction needs human approval (Slice 14a/b) | ⚠️ context only; no release-gate binding check ⇒ **gate fail-closed** |
| 9 | cost forecast within policy | cost ledger + budget + **`evaluate_stop`** (incurred-cost/budget **stop** logic, Slice 7) — **not forecast logic**; forecasting deferred (CLAUDE.md) | ⚠️ context only; **gate fail-closed** until cost-forecast evidence exists |
| 10 | rollback **verified** | — | ❌ Phase 6 (§26.6) |
| 11 | monitoring + alerts active | — | ❌ Phase 3/6 |
| 12 | production deploy **pre-approved under stated conditions** | `AutonomyLevel.A5` enum (`levels.py`) + `deploy_production` mandatory-approval (`matrix.py`) + approval engine (Slice 4); `decision_for("deploy_production")` is transparency/context; **A5 auto-release gates + stop_conditions deferred** | ⚠️ context only; **gate fail-closed** until explicit pre-approved-release evidence with stated conditions + verified authority exists |
| 13 | emergency stop / rollback authority | runtime cost STOP→pause (Slice 8b) — not a production emergency-stop authority | ❌ Phase 6 |

**Inference (labelled):** **only R5 intake completion (#1) is fully evaluable and gate-passing
today.** Several gates (#2, #8, #9, #12) have partial *context* primitives, but **no other
Appendix-B gate has enough evidence to pass safely** — each stays fail-closed. The remaining gates
depend on Phase 3 (integrations), Phase 5 (review/verification/evidence), or Phase 6 (release/ops)
subsystems that are **not implemented** (CLAUDE.md "Not yet present"). Therefore **A5 cannot be
deterministically *satisfied* in one slice.**

## 3. Options

- **Option A (recommended) — fail-closed A5 *evaluator skeleton* (deny-by-default, non-authorizing).**
  Build a pure, deterministic A5 evaluator that scores all 13 gates. **Only gate #1 (R5) can pass
  today**; every other gate is marked hard-FALSE — gates with no source at all as
  `no_evidence_source:<subsystem>`, and gates with partial *context* primitives (#2/#8/#9/#12) as
  `insufficient_evidence:<gate>` (the context is recorded but does not pass). It emits an honest "A5
  NOT satisfied — 12/13 gates not met" report and **keeps `can_go_live_autonomously` false**. Mirrors
  the readiness-ladder pattern; **operator-visible only if the resulting PLAN adds a new read-only
  production-autonomy endpoint/report, or explicitly extends an existing dashboard endpoint per
  D-A5-3** (the existing readiness/findings read APIs do **not** expose this). Delivers structure +
  honesty now; each future evidence subsystem flips one gate. *Risk:* must be unmistakably
  non-authorizing — never flips go-live true while any gate is stubbed.
- **Option B — defer A5 entirely** until the upstream evidence subsystems exist; build those first
  (each its own slice). Cleanest separation, but no A5 surface at all for a long time.
- **Option C — build ONE prerequisite evidence subsystem first** (e.g. a **risk-acceptance record
  store**, or **test-oracle pass-evidence**, or a **security/shortcut findings store**) as a normal
  slice, deferring the A5 evaluator until enough gates have sources. Picks the highest-value gate to
  unblock first.

## 4. Fail-closed / go-live-safety invariants (non-negotiable, whichever option)

- `can_go_live_autonomously` stays **false** unless **every** Appendix-B gate is satisfied with real
  evidence — and even then only behind an explicit, authenticated A5 pre-approval (request-auth does
  not exist yet, CLAUDE.md). Until then it is hard-false.
- Deny-by-default: an absent/ambiguous gate ⇒ A5 **not** satisfied (never "assume pass").
- No faking: stubbed gates are reported as `no_evidence_source`, never as "pass" (spec §2.1).
- `deploy_production` stays mandatory-approval / never auto-ALLOW (Slice 3 matrix).

## 5. Out-of-scope (for any resulting PLAN)

- Actually performing a production deploy; real CI / source-control / monitoring integrations
  (Phase 3); test execution; security/shortcut detectors; rollback machinery (Phase 5/6).
- Request-authentication / verified approver identity (separate prerequisite).
- LLM; semantic analysis.
- Flipping `can_go_live_autonomously` true while any gate is stubbed.

## 6. Coordinator rulings needed before a PLAN

- **D-A5-1 (path):** Option A (fail-closed evaluator skeleton), B (defer), or C (build one evidence
  subsystem first)? *(Recommend A — honest, operator-visible, non-authorizing; or C if you'd rather
  land real evidence for one gate first.)*
- **D-A5-2 (if A): gate-source mapping** — confirm that **only #1 (R5) passes** today, and that the
  partial-context gates (#2 environments-presence, #8 AC provenance, #9 cost stop-decision, #12 A5
  policy/approval primitive) are recorded as **context only** and remain **fail-closed**
  (`insufficient_evidence`), never gate-passing; all sourceless gates are `no_evidence_source`.
- **D-A5-3 (if A): output shape** — a separate A5 report/endpoint, or extend the readiness report
  with an `a5_gates` block? (Recommend a **separate** `production_autonomy` evaluator + report to
  keep R5 intake-readiness and A5 authority cleanly distinct.)
- **D-A5-4 (if C): which evidence subsystem first** — risk-acceptance records, test-oracle pass
  evidence, or security/shortcut findings?
- **D-A5-5:** confirm `can_go_live_autonomously` remains hard-false in this slice regardless of path,
  and that request-auth / verified A5 pre-approval is a separate prerequisite (no go-live this slice).

## 7. Recommendation

A5 is the correct long-term frontier but it is a **capstone gate over many unbuilt subsystems**, not
a single feature. **Only R5 (gate #1) is satisfiable today; the other 12 gates are not met** — some
have partial context, none has enough evidence to pass safely. The safest, most honest increment is
**Option A**: a fail-closed, non-authorizing A5 evaluator skeleton that makes the 13-gate structure
explicit, reports every unmet gate as `no_evidence_source` / `insufficient_evidence`, and keeps
go-live hard-false (operator visibility requires a new production-autonomy report/endpoint per
D-A5-3). If you prefer landing real evidence first, **Option C** (one evidence subsystem) is the
alternative. **Pausing for rulings on D-A5-1..5 before any PLAN.**
