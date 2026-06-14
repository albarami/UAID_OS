# Slice 20 — R5 readiness / gated-engine completeness — Discussion v0

**Status:** RESOLVED — historical record. All rulings D-R5-1..8 ruled by the coordinator and
implemented in Slice 20 (see `.planning/SLICE-20-PLAN.md`). Outcome: level decoupled from
go-live (go-live stays false at R5); full declarable set required; autonomy = row + valid
overrides; cost = positive budget; human_approval_policy + production_authority made
presence-only declarable; report fields `missing_r5_categories`/`missing_r5_gates`,
`ruleset_version="slice20.v1"`; narrow CHECK-only migration `0020`.
**Base:** `main` @ `f28211f` (clean).
**Goal:** decide whether/how R5 can be made deterministic and fail-closed, then (only after
rulings) draft a PLAN. R5 is materially harder than R3/R4 — its hardest gates have **no clean
data source today**, which is the whole reason this is a discussion, not a plan.

---

## 1. Current readiness boundary

- Ladder R0–R4 complete, deterministic, fail-closed; `READINESS_CAP = "R4"`
  (`app/intake/readiness.py`). R0–R4 + their report are operator-visible via Slice 17 (latest)
  and Slice 19 (history) read endpoints.
- `can_go_live_autonomously` is **always false** today (capped < R5; gated categories unevaluated).
- R3 consumed: the technical trio (`user_journeys_and_workflows`, `data_model_and_contracts`,
  `architecture_and_technology_constraints`) + `environments_and_deployment_targets` (staging gate).
  R4 consumed: `integrations_and_external_systems`, `tool_access_manifest` + zero spine gaps.
- `not_assessed_categories` is now 18 (the §4.2 universe minus the 9 consumed).

## 2. What R5 means in the spec

- **§4.3 R5** = "Requirements, oracles, environments, secrets, authority, approvals, and go-live
  gates are complete."
- **Appendix A (R5 intake completeness checklist)** — 24 conditions, including: product purpose,
  scope, users/roles, permission matrix, workflows, functional + non-functional reqs, **critical
  acceptance criteria approved**, **test oracles for critical features**, domain pack, data model,
  integrations, **environments available**, **secrets available (manager refs)**, **tool access
  approved**, **autonomy policy approved**, **human approval policy approved**, **cost policy
  approved**, security/privacy, **go-live checklist approved**, **rollback criteria defined**,
  monitoring, risk register reviewed, prior decisions reviewed, **production authority explicit**.
- **Appendix B (A5)** is a *separate* production-autonomy gate (branch protection, oracles pass,
  no open critical findings, rollback verified, pre-approved release, emergency stop, …). **A5 ≠ R5.**

## 3. Candidate R5 gates → authoritative data sources (what exists / what's missing)

| Gate (Appendix A) | Candidate source | Status |
|---|---|---|
| Spine: reqs/AC/oracles complete | spine `spine_gaps == []` | ✅ already computed (R4 reuse) |
| Environments available | `intake_categories` cat 16 declared | ✅ declarable (used for staging) |
| Secrets available (refs) | `intake_categories` cat 17 (reference-only) | ✅ declarable, secret-safe |
| Tool access approved | `intake_categories` cat 18 | ✅ declarable (R4 already consumes) |
| Integrations | `intake_categories` cat 12 | ✅ declarable (R4 already consumes) |
| Go-live checklist approved | `intake_categories` cat 23 | ✅ declarable (presence only) |
| Rollback criteria defined | within go_live_checklist (23) / risk_register (24) | ⚠️ no distinct field — presence-of-category only |
| Remaining intake content (00–07,10,13,15,22,24,25) | `intake_categories` declarations | ✅ declarable (presence only) |
| **Autonomy policy approved** | `autonomy_policies` row (`AutonomyPolicyRepository`) | ⚠️ table exists, but "approved" undefined |
| **Cost/resource policy approved** | `budgets` row (`BudgetRepository.get`) | ⚠️ table exists, but "approved" undefined |
| **Human approval policy approved** | — | ❌ **no policy table/repo** (only the per-approval engine, Slice 4) |
| **Production authority explicit** | — | ❌ **no affirmative source by design** (only the transparency-only `deploy_production` decision, which is mandatory-approval → `needs_approval`/`deny`, never ALLOW) |

**Crux:** the four **gated-engine** gates are the blockers. Two have a table but no "approved"
definition; one (human approval policy) has no representation at all; one (production authority)
is *intentionally* never affirmatively true under the current model.

## 4. Proposed deterministic definitions (for rulings — not yet decided)

For each gate, "complete" must be a **presence/structural** check (never content-quality, matching
R3/R4) and fail-closed (absent ⇒ not R5):

- **Declarable categories** (environments, secrets, tool access, integrations, go-live checklist,
  and the remaining intake categories): a provenance-backed **declaration exists** (status
  `declared`), with the same D-6 stale-source exclusion already applied generically.
- **Autonomy policy approved:** an `autonomy_policies` row **exists** for the project. *(Open: is
  mere presence enough, or must it be a specific level / an audited "approved" marker?)*
- **Cost policy approved:** a `budgets` row **exists** with a positive `max_total_cost_usd`.
  *(Open: presence enough, or a specific approval marker?)*
- **Human approval policy approved:** **no source exists.** Options: (a) add an
  `intake_categories`-style declaration for `human_approval_policy` (presence-only); (b) introduce a
  new policy record; (c) defer R5 until the approval-policy engine is built. *(Ruling required.)*
- **Production authority explicit:** **no affirmative source by design.** Options: (a) represent it
  as a presence-only declared intake category `production_authority` (explicitly **not** an
  authorization — mirrors the transparency-only decision wiring); (b) require an audited
  approval-engine record; (c) **keep R5 unreachable** until a production-authority engine exists.
  *(Ruling required — this is the central decision.)*

## 5. Fail-closed behavior — what keeps `can_go_live_autonomously = false`

**Strong recommendation:** even if the R5 *level* is reached, `can_go_live_autonomously` stays
**false** in this slice. Rationale: go-live authority is **Appendix B (A5)** — a distinct gate
(branch protection, oracles pass, verified rollback, pre-approved release, emergency stop) tied to
the autonomy policy A0–A5, none of which this slice evaluates. R5 = *intake package complete*;
A5 = *production autonomy allowed*. Conflating them would be "fake done." So:
- R5 level can become reachable **without** ever flipping go-live true.
- `can_go_live_autonomously` remains hard-false; A5/Appendix-B evaluation is a separate future slice.
- Any gate whose source is absent/ambiguous ⇒ **not R5** (deny-by-default).

## 6. Out-of-scope (for the eventual PLAN)

- Semantic contradiction analysis; any LLM; content-quality judgement.
- **Inventing production authority** or any path that makes `can_go_live_autonomously` true.
- Appendix-B / A5 production-autonomy evaluation (separate slice).
- New gated-engine *engines* (a real human-approval-policy engine, production-authority engine) —
  this slice would at most read presence, not build the engines.
- Migrations beyond, at most, an additive category if a ruling requires representing
  human_approval_policy / production_authority as declarations.

## 7. Coordinator rulings needed before a PLAN

- **D-R5-1 (level vs go-live):** confirm R5 *level* is decoupled from go-live, and
  `can_go_live_autonomously` stays false this slice. *(Recommend: yes.)*
- **D-R5-2 (R5 category set):** confirm R5 requires **all remaining declarable categories declared**
  (the 14 not yet consumed) + the R3/R4 sets + zero spine gaps — or specify a narrower critical
  subset (Appendix A says "critical" for some items; presence-only can't see "critical").
- **D-R5-3 (autonomy policy "approved"):** presence of an `autonomy_policies` row, or a stricter
  marker?
- **D-R5-4 (cost policy "approved"):** presence of a `budgets` row with positive cap, or stricter?
- **D-R5-5 (human approval policy):** which representation — new declaration category, new record,
  or defer R5 until its engine exists?
- **D-R5-6 (production authority — the crux):** presence-only declared category (non-authorizing),
  audited approval record, or keep R5 unreachable for now?
- **D-R5-7 (report shape):** new fields (`missing_r5_categories`, `missing_r5_gates`),
  `readiness_cap → "R5"`, `ruleset_version` bump — and whether R5 is terminal (cap stays R5).
- **D-R5-8 (migration):** acceptable to add an additive intake-category (or small table) **only if**
  D-R5-5/6 require representing human_approval_policy / production_authority? Default: avoid; prefer
  reading existing sources.

## 8. Recommendation

R5 is worth doing but its value hinges on D-R5-5 and **D-R5-6**. If the rulings keep
production-authority/human-approval as **presence-only, non-authorizing** signals (with go-live
hard-false), R5 becomes a clean deterministic extension of the R3/R4 pattern and a PLAN is
straightforward. If they require real engines, R5 should wait. **Pausing for rulings on
D-R5-1..8 before any PLAN.** Semantic contradiction analysis remains deferred.
