# UAID OS — End-to-End Go-Live Roadmap

**Document type:** Authoritative planning roadmap (single source of truth for "what comes next" — from the current baseline to a *functional, evidence-backed, operating* go-live system, not merely an A5-gate skeleton).
**Author persona:** Senior delivery-platform / release-governance architect.
**Created:** 2026-06-17. **Revision:** Rev 7 (current-state reconciliation after Slice 46 merged; immediate-next marker advanced to Slice 47).
**Baseline state:** Post–Slice 46 (`main` at `caee2bf`; Slice 46 merged via PR #82 at `caee2bf`; Alembic head `0045_acceptance_verification`; A5 evaluator `ruleset_version = "slice46.v1"`; readiness `ruleset_version = "slice20.v1"`).
**Status of this document:** SEQUENCING RECORD — §6 reflects the current post–Slice-46 next action; the detailed baseline analyses in §§2–3 are retained as a historical post–Slice-25 snapshot. Slices through 46 are merged; Slice 47 is next planned and has not started. This document does **not** authorize implementation and does **not** authorize go-live.

> **Sourcing discipline (Sanad / No-Free-Facts).** Every factual claim cites its origin: the standalone spec
> (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`, cited as "spec §N" / line ranges), an
> intake template/schema, a `.planning/` doc, a source file, or a migration. Reasoned ordering not dictated by
> a single source is labelled **(inference)**; planning choices are labelled **(assumption)**.

> **Reader's quick answers (the five questions this roadmap must answer):**
> 1. *What from Slices 1–25 is complete?* → §2.1–§2.3 + the ledger §2.6 (status = **DONE**).
> 2. *What is partial or deferred?* → §2.6 (status = **PARTIAL** / **DEFERRED**), with the exact residual.
> 3. *Where is every deferred item scheduled?* → §2.6 "Scheduled in" column → §5 slices; nothing is left unscheduled.
> 4. *Where is every Phase 3–7 spec component mapped?* → the coverage matrix §10.
> 5. *What makes the system functional after go-live (not just A5-passable)?* → the operational-depth section §11.

---

## 1. Purpose and non-goals

### 1.1 Purpose
This roadmap exists so **future slices do not re-derive "what is the next step" after every merge** (Slices 17–25 each re-litigated the next target in a fresh discussion: `.planning/SLICE-22-RISK-ACCEPTANCE-DISCUSSION.md` … `SLICE-25-RELEASE-BINDING-DISCUSSION.md`). It fixes the full trajectory from the post–Slice-25 baseline to a **functional go-live system** — one that can, per spec §29 (lines 2918–2947), accept a documentation package, judge build-readiness, compile missing specs where safe, staff agents, build/review/test, deploy to production *only* when policy + evidence permit, and **monitor and stabilize after launch**. A future builder should read §6 + §5 + §2.6, pick the next slice, draft its `PLAN v1`, and proceed **without guessing**.

### 1.2 Non-goals (what this document is NOT)
- It is **not implementation**. No code, migration, runtime, or product file is created or modified by authoring it.
- It is **not approval** of any slice. Each slice still requires its own discussion → PLAN v1 → coordinator approval (`.planning/SLICE-24-PLAN.md`, `.planning/SLICE-25-PLAN.md`).
- It **does not authorize go-live** and changes nothing about today's hard-false posture (`app/release/production_autonomy.py:69-86`, `:22-24`).
- It does not invent spec capability. Sequencing choices the spec does not dictate are surfaced in §12 (Open decisions), not asserted.

---

## 2. Historical implemented baseline (post–Slice-25 snapshot)

### 2.1 Phase 1 — Control-plane foundation (§26.1, lines 2430–2446) — COMPLETE
All eleven Phase-1 capabilities in spec §26.1 are present (CLAUDE.md "Current status"; README.md; `.planning/PHASE-1-PLAN.md`): tenant isolation (app-layer + Postgres RLS, Slices 1/1b), project state store (1), durable workflow runtime (LangGraph + custom UAID RLS checkpointer, 8a/8b), tool broker skeleton (5), append-only hash-chained audit log (2), approval engine (4), cost ledger (7), document intake sandbox (9), read-only dashboard API (10), agent registry (6), autonomy policy engine (3). Tagged `v0.1.0`/`v0.1.1`.

### 2.2 Phase 2 — Documentation compiler & intake standard (§26.2, lines 2448–2459) — SUBSTANTIALLY COMPLETE (3 residual items, scheduled in §5 Track B)
Built: canonical intake spine (Slice 11; migration `0014`), build-readiness auditor R0→R5 (12/16/18/20; `0015`,`0020`), gap & **structural** contradiction detector (13; `0016`), LLM-assisted extractor → inert proposals (14a; `0017`), promotion into spine (14b; `0018`), declarable intake-category model (15; `0019`). Tagged `v0.2.0`.
**Residual Phase-2 items named by spec §26.2 but not yet built** (now scheduled — see §2.6 + §5 Track B): standalone **document classifier** (§6.2 line 559), **canonical artifact generator** beyond promotion (§6.3, lines 574–592), and **semantic** contradiction detector (§6.4, lines 594–609; today only *structural* per `app/intake/findings.py`).

### 2.3 Slices 21–25 — A5 evaluator + the first four release-evidence stores
| Slice | Capability | Tables / migration | A5 wiring | Source |
|---|---|---|---|---|
| 21 | Fail-closed, **non-authorizing** A5 evaluator scoring all 13 Appendix-B gates; compute-on-read | none (D-21-A) | only gate #1 can pass; `slice21.v1` | `app/release/production_autonomy.py` |
| 22 | Risk-acceptance record store (§24.1/§27.10); hard-refusal categories blocked at store time | `risk_acceptance_records` + events; `0021` | gate #7 context; `slice22.v1` | `app/release/risk_acceptance.py` |
| 23 | Security/shortcut release-findings store (§13.4/§916-920); critical never acceptable | `release_findings` + events; `0022` | gates #5/#6 `insufficient_evidence`; `slice23.v1` | `app/release/findings.py` |
| 24 | Open-issue/blocker store (§24.1/§24.2/App. B #7); `critical ⇒ blocking` | `release_issues` + events; `0023` | gate #7 reason; `slice24.v1` | `app/release/issues.py` |
| 25 | Release-candidate / release-binding store; freeze-locked issue bindings | `release_candidates` + events + bindings; `0024` | gate #7 narrows to `no_issue_provenance` when a frozen candidate exists; `slice25.v1` | `app/release/release_candidates.py` |

Every store is tenant-owned, RLS `ENABLE`+`FORCE`, append-only events, **no DELETE**, DB-guard lifecycle, audit safe-metadata-only; all provenance is `caller_supplied_unverified` (no verified provenance, no request-auth; `app/release/risk_acceptance.py:17`).

### 2.4 The go-live posture is hard-false — by construction
- `can_go_live_autonomously` is **always false** at every R0–R5 (`app/intake/readiness.py:342`) and in the A5 report (`production_autonomy.py:78-81`).
- `a5_satisfied` requires **all 13** gates passed; only gate #1 can pass today (`production_autonomy.py:69-71`).
- Go-live *also* requires a **request-authenticated, verified A5 pre-approval that does not exist** — a second permanent blocker (`production_autonomy.py:22-24`, `:38-41`).
- **R5 ≠ A5:** R5 = intake completeness (Slice 20); A5 = production-autonomy evidence (Slice 21); orthogonal (`.planning/SLICE-20-R5-DISCUSSION.md` D-R5-1).

### 2.5 Which A5 gates can pass / are partial / are sourceless (post–Slice 25)
- **Can pass (1):** gate #1 (passes at R5) — `production_autonomy.py:124-127`.
- **Partial context, never passes (7):** #2/#5/#6/#7/#8/#9/#12 (`insufficient_evidence`) — `:129-206`.
- **No evidence source (5):** #3/#4/#10/#11/#13 (`no_evidence_source:<subsystem>`) — `:212-222`.

### 2.6 Slices 1–25 completeness ledger (answers: what is complete / partial / deferred, and where each residual is scheduled)
"Scheduled in" points forward to §5. Nothing residual is left unscheduled.

| Spec subsystem | Slice(s) | Status | Residual (if any) | Scheduled in |
|---|---|---|---|---|
| Tenant isolation (§17) | 1, 1b | **DONE** | future tenant tables add same RLS | (each new table) |
| Project state store, runs (§23.4) | 1 | **DONE** | — | — |
| Durable runtime (§23.2) | 8a, 8b | **DONE (substrate)** | §23.3 control loop; tool-result persistence; distributed workers | §5 Slice 55 (loop); Phase 7 (distribution) |
| Tool broker (§11) | 5 | **DONE (skeleton)** | real execution / connectors / MCP / credentials | §5 Slices 28–34 (connectors), 39 (broker↔agent wiring) |
| Audit log (§16.6) | 2 | **DONE** | external sink; cryptographic signing | §5 Slice 49/60 (evidence signing); Phase 7 |
| Approval engine (§18) | 4 | **DONE** | scheduler; real channels; **request-auth** | §5 Slice 27 (request-auth), 33 (channel) |
| Cost ledger (§19) | 7 | **DONE** | price cards; **forecast**; per-phase budgets | §5 Slice 51 (forecast) |
| Agent registry (§9.7/§22.2) | 6 | **DONE (catalog)** | **Agent Factory**; eval execution; model routing; broker wiring | §5 Slices 38–41 |
| Document intake sandbox (§16.3) | 9 | **DONE** | Documentation Compiler; ML/RAG; binary parsing | §5 Track B Slices 35–37 |
| Read API/dashboard (§18.6) | 10,17,19,21 | **DONE (read subset)** | forecast, critical path, evidence-pack status, deployment status, next action; pagination; web UI | §5 (surfaces per slice); Phase 7 (UI) |
| Canonical intake spine + Sanad store (§3.4/§26.2) | 11 | **DONE** | — | — |
| Build-readiness auditor R0–R5 (§4.3/§4.5) | 12,16,18,20 | **DONE (capped R5)** | — (A5 is separate) | §5 (Phase 3–6 gates) |
| Requirement extractor (§26.2) | 14a | **DONE** | real-model quality/eval | §5 Slice 40 (evals) |
| Gap detector (§26.2) | 13 | **DONE** | — | — |
| **Contradiction detector** (§26.2/§6.4) | 13 | **PARTIAL (structural only)** | **semantic** contradiction analysis | §5 Track B **Slice 37** |
| **Document classifier** (§26.2/§6.2) | 9 (scan), 14a (per-doc) | **PARTIAL** | standalone multi-type **classifier + authority mapping** (§6.2) | §5 Track B **Slice 35** |
| **Canonical artifact generator** (§26.2/§6.3) | 14b (promotion) | **PARTIAL** | full §6.3 artifact generation + Spec Generation Mode (§6.5) under §7 authorship independence | §5 Track B **Slice 36** |
| Intake template pack (§26.2/§27) | docs/ | **DONE** | reference-intake companion library | §5 Slice 61 |
| Declarable intake-category model (§4.2) | 15 | **DONE** | — | — |
| A5 evaluator skeleton (§5.1/App. B) | 21 | **DONE (non-authorizing)** | every real evidence subsystem | §5 Slices 28–55 |
| Risk-acceptance store (§24.1/§27.10) | 22 | **DONE (store)** | verified signer (request-auth); `release_id` FK | §5 Slice 27, 47 |
| Security/shortcut findings store (§13.4) | 23 | **DONE (store)** | **scan/detector execution** + provenance | §5 Slices 44, 45 |
| Open-issue/blocker store (§24.1/App. B #7) | 24 | **DONE (store)** | **issue provenance**; findings→issue bridge | §5 Slice 47 |
| Release-candidate/binding store (§24.1/§24.2) | 25 | **DONE (store)** | release approval/verdict; `risk_acceptance.release_id` FK | §5 Slices 47, 50 |

---

## 3. Historical A5 Appendix-B gate matrix (post–Slice-25 snapshot)

The 13 gates are the verbatim Appendix-B checklist (spec lines 2981–2997), scored by `app/release/production_autonomy.py`. Status: **PASS-CAPABLE** = passes today when state qualifies; **INSUFFICIENT** = `insufficient_evidence` (context only, never passes); **NO-SOURCE** = `no_evidence_source:<subsystem>`.

| # | Gate text (Appendix B) | Code id / current source | Status | Missing evidence to ever pass | Phase / slice | Citation |
|---|---|---|---|---|---|---|
| 1 | R5 intake is complete | `r5_intake_complete` — readiness auditor | **PASS-CAPABLE** (at R5) | none | Done (Phase 2) | spec 2985; `production_autonomy.py:124-127` |
| 2 | production deployment target available | `production_deployment_target_available` — env declaration (context) | INSUFFICIENT | **provisioned + verified** target (connector) | Phase 3 — **Slice 30** | spec 2986; `:130-136`; tmpl `16_*` |
| 3 | branch protection + required checks active | `branch_protection_and_required_checks_active` — **none** | NO-SOURCE `ci_branch_protection` | source-control + CI reporting branch-protection + required-check status | Phase 3 — **Slices 26→28** | spec 2987; `:212`; tmpl `18_*` |
| 4 | all critical test oracles pass | `all_critical_test_oracles_pass` — **none** | NO-SOURCE `test_oracle_execution` | test-oracle **execution** (§14) | Phase 5 — **Slice 43** | spec 2988, §14; `:213`; tmpl `09_*` |
| 5 | no unaccepted critical **security** findings | `no_unaccepted_critical_security_findings` — `release_findings` (counts) | INSUFFICIENT `no_finding_provenance_or_scan_source` | authoritative security-scan coverage | Phase 5 — **Slice 44** | spec 2989; `:189-197`; `findings.py` |
| 6 | no unaccepted critical **shortcut** findings | `no_unaccepted_critical_shortcut_findings` — `release_findings` (counts) | INSUFFICIENT `no_finding_provenance_or_scan_source` | shortcut-detector execution (§13.4) | Phase 5 — **Slice 45** | spec 2990, §13.4; `:198-206` |
| 7 | remaining open issues have approved risk-acceptance | `approved_risk_acceptance_records` — risk-accept (22)+issues (24)+binding (25) | INSUFFICIENT (narrows to `no_issue_provenance` when frozen) | issue provenance/completeness + release **verdict** + `release_id` FK | Phase 5→6 — **Slices 47, 50** | spec 2991, §24.1; `:163-184` |
| 8 | no unapproved generated AC in critical gates | `no_unapproved_generated_ac_in_critical_gates` — extraction provenance (context) | INSUFFICIENT | release-gate binding proving only **approved** AC gate the release (§7) | Phase 5 — **Slice 46** | spec 2992, §7; `:137-143`; tmpl `08_*` |
| 9 | cost forecast within policy | `cost_forecast_within_policy` — cost stop-decision (context) | INSUFFICIENT | a forward **forecast** model (§19) | Phase 6 — **Slice 51** | spec 2993, §19; `:144-150`; tmpl `21_*` |
| 10 | rollback verified | `rollback_verified` — **none** | NO-SOURCE `rollback_verification` | rollback execution + verification | Phase 6 — **Slice 52** | spec 2994, §24.2; `:219` |
| 11 | monitoring + alerts active | `monitoring_and_alerts_active` — **none** | NO-SOURCE `monitoring` | monitoring integration confirming active alerts | Phase 3 connector → Phase 6 ops — **Slices 31, 56** | spec 2995; `:220`; tmpl `22_*` |
| 12 | production deploy pre-approved under conditions | `production_deploy_preapproved_under_conditions` — autonomy enum (context) | INSUFFICIENT | request-authenticated, **verified** A5 pre-approval | Phase 6 + request-auth — **Slices 27, 53** | spec 2996; `:151-157`; tmpl `20_*`,`23_*` |
| 13 | emergency stop/rollback authority | `emergency_stop_rollback_authority` — **none** | NO-SOURCE `emergency_stop` | emergency-stop mechanism + bound authority | Phase 6/7 — **Slice 54** | spec 2997, App. C l.3016; `:222` |

**Invariant:** no gate moves to PASS until its evidence source is genuinely complete and verified. Counts/declarations are context, never authorization (`production_autonomy.py:120-121`).

---

## 4. End-to-end phase roadmap (Phase 3 → Phase 7)

Phases follow spec §26.3–§26.7 (lines 2461–2522). Each is detailed slice-by-slice in §5; this is the per-phase frame. (Phase 2 closure — §26.2 residuals — is §5 Track B.)

### Phase 3 — Project execution integrations (§26.3, lines 2461–2472)
- **Objective.** Broker-mediated connectors to the outside world so *external facts* become **verifiable evidence**, not declarations: project management, source control, pull requests, CI/CD, staging deployment, communication/approval channel, secrets-reference verification, monitoring.
- **Required capabilities.** Source-control + CI connectors (gate #3); PR evidence (§12.4); deploy-target + staging connector (gate #2); monitoring connector (gate #11); secrets-reference verifier (§16.4); comms/approval channel (§18.2); PM/issue-tracker connector.
- **Dependencies.** Tool broker (Slice 5); per-agent allowlist; **request-auth** (Slice 27); `18_tool_access_manifest.yaml`.
- **Data model.** Tenant-owned, RLS, append-only external-evidence stores per integration class, each with a **two-tier provenance** column (`caller_supplied_unverified` vs `connector_verified`). (inference, mirroring Slices 22–25 + adding a verified tier.)
- **Surfaces.** Read-only `GET /api/projects/{id}/integrations/...`; admin-path connector config.
- **A5 gates.** #3, #2 PASS-capable; #11 sourced; #7 gains its eventual CI/reviewer provenance feed.
- **Evidence-pack impact.** `build.repository/pull_requests/commits`, `artifacts.build_logs/deployment_logs/monitoring_confirmations` (§15.2, §28.1).
- **Testing.** Fake connector in CI (mirrors `app/llm/FakeLLMClient`); `connector_verified` unforgeable from a caller path; RLS isolation.
- **Non-goals/safety.** No production deploy (staging only, A3); secret *values* never stored; no gate flips on caller-supplied data.

### Phase 4 — Agent Factory and skill matching (§26.4, lines 2474–2485)
- **Objective.** Turn the static registry (Slice 6) into a governed factory: skill graph (§8.2), skill matching (§8.3), agent realization (§9.2, `agent_realization_template.yaml`), archetype eval library (§9.5.1, `archetype_eval_methodology.yaml`), agent-QA workflow (§9.4), generated-agent security review (§16.8, App. C l.3010), performance monitoring + replacement policy (§9.6).
- **Required capabilities.** Skill graph + matching score; realization from blueprints; archetype evals with gold answers/rubrics/activation thresholds; reviewer/builder model-route separation (`reviewer_quality_assurance.yaml`); §9.7 immutable versioning (registry already enforces).
- **Dependencies.** Agent registry (6); tool broker (5) wired to instances (not yet); cost ledger + model routing (7); `model_change_policy.yaml`.
- **Data model.** `skills`, `agent_realizations`, `agent_eval_runs`/`agent_qa_records` (cf. `reviewer_quality_record`, §13.5).
- **A5 gates.** Indirect: supplies the reviewer/verifier/builder agents that Phase-5 gates need.
- **Evidence-pack impact.** `review_reports`, `reviewer_quality_records`, `reviewer_model_routes`.
- **Testing.** Planted-defect/miss-rate harness (`reviewer_quality_assurance.yaml`: sampling 0.05, max critical miss 0.00, max false-approval 0.03); eval determinism; no agent approves its own work (§2.2).
- **Non-goals/safety.** Generated agents pass security review before activation (App. C l.3010); lineage separation (App. C l.3006).

### Phase 5 — Review, verification, and evidence (§26.5, lines 2487–2498)
- **Objective.** Maker-checker-verifier workflow, task contracts, reviewer reports, test-oracle framework, shortcut detector, acceptance verifier, evidence-pack auditor, go-live-readiness agent — turning activity into *proof*.
- **Required capabilities.** Task contracts (§13.2/§27.2); three-layer review (§13.1); verdicts (§13.3); oracle execution (§14.2/§14.3); shortcut detection (§13.4); acceptance verification; evidence-pack generation + audit (§15/§27.11/§28.1); spec-authorship independence (§7).
- **Dependencies.** Phase 3 (CI runs oracles/reviews) + Phase 4 (agents perform reviews); Slice 22–25 stores as sinks; Sanad provenance (Slice 11).
- **Data model.** `task_contracts`, `review_reports`, `test_results`, `evidence_packs` (§23.4); findings→issue bridge + issue-provenance upgrade; `risk_acceptance_records.release_id` FK.
- **A5 gates.** #4, #5, #6, #7, #8 PASS-capable.
- **Evidence-pack impact.** Produces the pack: traceability, test_results, review_reports, reviewer_quality_records, provenance_chains, verdict.
- **Testing.** "No oracle, no go-live" (§14.4); reviewer QA miss-rate gates (§13.5); export validates against schema and **fails the gate** on missing fields (§28.1 l.2912).
- **Non-goals/safety.** No agent-asserted evidence without provenance (§2.3/§2.4); shortcut detection independent (§13.4); critical findings non-acceptable.

### Phase 6 — Production release and operations (§26.6, lines 2500–2510)
- **Objective.** Release manager, production-approval workflow, rollback verification, post-launch monitoring, incident workflow, self-healing/hotfix loop, continuous-improvement engine — exercising the go-live gate and the stabilization window.
- **Required capabilities.** Release verdict (§24.3); production approval → verified A5 pre-approval (gate #12); rollback verification (gate #10); cost forecast (gate #9); monitoring/alerts (gate #11); emergency stop/authority (gate #13); §23.3 control loop; stabilization (§25, `stabilization_window_policy.yaml`).
- **Dependencies.** All of Phases 3–5; request-auth; the §23.3 control loop (absent today).
- **Data model.** `deployments`, `incidents` (§23.4), `release_verdicts`, `production_approvals`, `rollback_verifications`, `stabilization_windows`.
- **Surfaces.** Formal release-approval UX with the go-live evidence pack (§18.2 l.1769); emergency-rollback alert (§18.2 l.1770); stabilization dashboard.
- **A5 gates.** #9, #10, #12, #13 PASS-capable; `a5_satisfied` + verified pre-approval co-reachable here only.
- **Evidence-pack impact.** `approvals`, `deployments`, `risk`, `verdict`, integrity manifest + signature (§28.1).
- **Testing.** Reproduce the §24.1 go-live gate exactly; rollback *verified* not asserted; §25.4 exit criteria enforced; production-deploy authority structurally non-bypassable (`app/policy/matrix.py`).
- **Non-goals/safety.** No production-deploy path until **all 13 gates have real evidence AND a verified pre-approval** (§2.6, App. B); emergency override needs explicit authority (App. C l.3016).

### Phase 7 — Scale and ecosystem (§26.7, lines 2512–2522)
- **Objective.** Marketplace of vetted blueprints, connector library, reference-intake companion library, external-assurance export hardening (§28), advanced cost optimizer, tenant-safe cross-project learning (§17.5/App. C l.3009), enterprise administration.
- **A5 gates.** None directly — hardens/scales/externalizes Phases 3–6.
- **Non-goals/safety.** Cross-project learning never reuses tenant content (App. C l.3009); marketplace blueprints pass security review (App. C l.3010).

---

## 5. Proposed slice sequence (after Slice 25)

Two tracks. **Track A** is the A5-gate / go-live critical path (Slices 26→63). **Track B** is the Phase-2 intake-compiler closure (§26.2 residuals) — *parallelizable, off the A5-gate critical path*; it can be scheduled flexibly alongside Track A and does **not** block any A5 gate (none of the §26.2 residuals appears in Appendix B or the §24.1 go-live gate — see §2.6 + the disposition note in each Track-B slice). Slice numbers are stable. Each entry carries the full field set. **No slice makes a gate PASS unless its evidence source is genuinely complete and verified.**

> Sequencing rests on: (a) spec §26 orders Phase 3 (integrations) before Phase 5 (review/evidence); (b) the dependency graph (§7) shows source-control/CI is the root every other evidence gate draws from (**inference** from §26 + the Slice 24/25 "no issue provenance" deferrals).

### Track A — A5 evidence / go-live critical path

#### Slice 26 — Source-control / CI evidence-provenance foundation (gate #3)
- **Goal.** Tenant-owned, RLS, append-only external-evidence store for branch-protection snapshots + required-check status, with a two-tier provenance enum; wire gate #3 `no_evidence_source` → `insufficient_evidence` while only unverified data exists.
- **Why now.** §26.3 next phase; dependency-graph root; first *positive, observable* evidence class; matches the Slice 22–25 "store first" pattern.
- **Spec grounding.** §26.3 (2461–2472); App. B #3 (2987); §5.2 "Merge to protected branch — A4+ — Required reviews and status checks" (l.484); tmpl `18_tool_access_manifest.yaml`.
- **Files.** new `app/release/ci_evidence.py`, `app/models/ci_check_result.py`, `app/models/branch_protection_snapshot.py`, `app/repositories/ci_evidence.py`; wire `production_autonomy.py` + its repo; dashboard read endpoint.
- **Migration.** `0025` — two tenant-owned RLS tables + append-only events; additive only.
- **Tenant/RLS/FK/audit/immutability.** Composite FK `(project_id, tenant_id)`; `tenant_isolation`; DB-guard INSERT invariants (provenance enum, status); append-only; audit safe-metadata only (ids/status/provenance — never tokens/URLs).
- **Tests.** RLS cross-tenant; `connector_verified` unforgeable from caller; gate #3 stays `insufficient_evidence` under unverified data; catalog/grants; append-only.
- **A5 gate(s) advanced.** #3 (to context only).
- **Must NOT claim.** That branch protection is active/verified; no gate passes on caller data; no real connector this slice.
- **Exit.** Store + provenance + conservative gate-#3 wiring merged; `ruleset_version` `slice26.v1`; go-live false; `make test`/`make test-db` green.

#### Slice 27 — Request-authentication → verified actor identity (cross-cutting enabler)
- **Goal.** Request-authenticated, verified actor identity so approvals/signers/connector evidence carry **verified** provenance.
- **Why now.** Most-shared prerequisite: gate #12 needs a verified pre-approval; gate #7 risk-acceptance needs verified signers; broker success caps at `ALLOWED_UNVERIFIED_IDENTITY` until it exists (README). Deferred since Phase 1 (D4-adjacent).
- **Spec grounding.** §18; §5.2; §2.2 (no self-approval).
- **Files.** `app/api/auth.py` (actor identity beyond tenant); `app/approvals/*`; `app/release/risk_acceptance.py`.
- **Migration.** `0026` — actor/identity table or approval columns; additive.
- **Tenant/RLS/FK/audit/immutability.** Verified-identity provenance tamper-evident + audited; no secret material in audit.
- **Tests.** Verified vs unverified identity; unverified signers still satisfy no gate; cross-tenant isolation.
- **A5 gate(s) advanced.** Enables (not passes) later #7/#12 verified-evidence paths.
- **Must NOT claim.** That Slice 27 itself flips any A5 gate to PASS; request-auth alone authorizes nothing (gate #1 still passes purely on R5).
- **Exit.** Verified identity available to approvals/signers/connectors; go-live false.
- **Note (D-1).** 26-vs-27 ordering is a coordinator choice (§12). Default: 26 first (self-contained), then 27 before any **additional, non-#1** A5 gate is allowed to PASS.

#### Slice 28 — Verified source-control / CI connector via the tool broker (gate #3 PASS-capable)
- **Goal.** Broker-mediated GitHub connector reading branch-protection + required-check status, writing `connector_verified` evidence. Gate #3 PASS-capable (passes only when verified evidence shows protection + required checks active).
- **Why now.** Slice 26 store + Slice 27 verified provenance make this the first non-#1 gate to genuinely pass.
- **Spec grounding.** §26.3; App. B #3; §11 broker; tmpl `18_*`.
- **Files.** `app/tools/registry.py` (tool entries); connector adapter (real, fake-in-tests); `app/repositories/ci_evidence.py`; gate-#3 PASS logic.
- **Migration.** likely none (reuses `0025`).
- **Tenant/RLS/FK/audit/immutability.** Broker decision recorded; secrets reference-verified (never stored); audit safe-metadata only.
- **Tests.** Fake connector only in CI; gate #3 passes **only** on verified "protection + required checks active"; deny-by-default when connector absent.
- **A5 gate(s) advanced.** **#3 → PASS-capable** (first gate after #1).
- **Must NOT claim.** That any other gate passes; go-live false (12 gates remain).
- **Exit.** Gate #3 passes under verified-active evidence in a DB-backed test; go-live false.

#### Slice 29 — Pull-request evidence connector (PRs, reviews, commits, protected-branch merges)
- **Goal.** Record PRs with the §12.4 required contents (linked task, task contract, AC coverage, tests, evidence links, limitations, security/rollback notes) + review approvals + merge-through-protected-branch facts as `connector_verified` evidence.
- **Why now.** Phase-3 integration (§26.3 "pull requests"); feeds traceability (§15.2) and the issue/AC provenance that gates #7/#8 need.
- **Spec grounding.** §26.3; §12.4 (1209–1224); §12.3 board workflow (1184–1207, "Builder agents cannot move their own work to Done").
- **Files.** `app/release/pr_evidence.py`, `app/models/pull_request_record.py`, `app/repositories/pr_evidence.py`; connector adapter.
- **Migration.** `0027` — `pull_request_records` + events; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; composite FK to project/tenant; append-only events; audit safe-metadata only (ids/status — never diff/body).
- **Tests.** RLS isolation; verified merge facts unforgeable; traceability links resolve.
- **A5 gate(s) advanced.** Indirect (#7/#8 provenance feed); supports gate #3 (required reviews).
- **Must NOT claim.** That review approval = acceptance verification (that's Slice 46); no gate flips here.
- **Exit.** PR evidence captured + linked to tasks/issues; go-live false.

#### Slice 30 — Production deployment-target verification + staging deploy connector (gate #2)
- **Goal.** Verify a reachable production deploy target + a staging-deploy connector (A3 staging autonomy). Gate #2 PASS-capable.
- **Why now.** Needed in the Phase-3 integration wave once verified provenance exists (S27/S28): A5 gate #2 requires a *provisioned + verified* deploy target, not the mere environment declaration that is context-only today (`production_autonomy.py:130-136`).
- **Spec grounding.** §26.3 (staging deployment); App. B #2; tmpl `16_*`; §5.2 "Deploy staging — A3+".
- **Files.** deploy connector + `app/models/deployment_record.py` + `app/repositories/deployments.py`; gate-#2 logic.
- **Migration.** `0028` — `deployment_records`; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; append-only; audit safe-metadata only.
- **Tests.** Verified deploy-target evidence; gate #2 passes only on verified evidence; staging-only.
- **A5 gate(s) advanced.** **#2 → PASS-capable**.
- **Must NOT claim.** Production-deploy authorization (still A4/A5 approval-gated, §5.2 l.485).
- **Exit.** Verified target evidence; gate #2 passes under verified evidence; go-live false.

#### Slice 31 — Monitoring / alerts evidence connector (gate #11)
- **Goal.** Monitoring connector confirming monitoring + alerts **active**, writing `connector_verified` evidence. Gate #11 PASS-capable.
- **Why now.** Needed in the Phase-3 integration wave: A5 gate #11 has no evidence source today (`no_evidence_source:monitoring`, `production_autonomy.py:220`); a verified "alerts active" connector is the pre-release half (the full §25.1 operational signals come later at S56).
- **Spec grounding.** §26.3 (monitoring integration) + §26.6 ops; App. B #11; tmpl `22_*`; `stabilization_window_policy.yaml` (`monitoring_confirmed_active`).
- **Files.** monitoring connector + `app/models/monitoring_status.py` + repo; gate-#11 logic.
- **Migration.** `0029` — `monitoring_status_snapshots`; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; append-only; audit safe-metadata only.
- **Tests.** Verified monitoring-active evidence; gate #11 passes only on verified evidence.
- **A5 gate(s) advanced.** **#11 → PASS-capable**.
- **Must NOT claim.** Post-launch operational completeness (that's §11 ops cluster, Slices 56–59).
- **Exit.** Verified monitoring-active evidence; gate #11 passes; go-live false.

#### Slice 32 — Secrets-reference verifier (no values stored)
- **Goal.** Validate the declared `17_secrets_and_credentials_manifest.yaml` references resolve in the approved secret manager — **without storing secret values** — producing verified "secrets available" evidence (Appendix A R5 item; supports gate #2 deploy readiness).
- **Why now.** Phase-3 integration (§26.3 "secrets reference verification"); R5 Appendix A "secrets are available through approved secret manager references" (l.2968).
- **Spec grounding.** §26.3; App. A (l.2968); §16.4 tool-privilege escalation (1589–1603); tmpl `17_*`; existing `categories.py` reference-only secret handling.
- **Files.** `app/release/secrets_verification.py` + `app/models/secret_reference_check.py` + repo; broker-mediated manager probe (fake-in-tests).
- **Migration.** `0030` — `secret_reference_checks` (reference + resolved-boolean only); additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; **no secret value ever persisted/logged/audited** (denylist defense-in-depth, cf. `categories.py:74-80`); append-only.
- **Tests.** Reference resolves vs missing; no secret value leaks to DB/audit/logs; RLS isolation.
- **A5 gate(s) advanced.** Supports #2 (deploy readiness) + R5 completeness; no gate flips alone.
- **Must NOT claim.** That references are *correct credentials* (only that they resolve); never store values.
- **Exit.** Verified secret-reference resolution evidence; zero value leakage proven; go-live false.

#### Slice 33 — Communication / approval channel (human-in-the-loop UX)
- **Goal.** A real approval/notification channel (digest + realtime) wiring the Slice-4 approval engine to a human surface per §18.2 batching, with verified-identity approvals (Slice 27).
- **Why now.** Phase-3 "communication/approval channel"; required for gate #12's *verified* approvals and for §18 HITL.
- **Spec grounding.** §26.3; §18.2 (1760–1770); §18.5 non-response policy; tmpl `20_human_approval_policy.yaml`.
- **Files.** `app/approvals/channels/*` (adapter, fake-in-tests); approval-engine wiring; dashboard.
- **Migration.** possibly `0031` — channel/notification log; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; approval events audited; verified-approver provenance (Slice 27); no secret material.
- **Tests.** Digest vs realtime routing by risk tier (§18.2); non-response policy (§18.5); cross-tenant isolation.
- **A5 gate(s) advanced.** Enables verified approvals for #12 (completed in Slice 53).
- **Must NOT claim.** That a channel ack = a production pre-approval (that's Slice 53).
- **Exit.** Approvals routed + recorded with verified identity; go-live false.

#### Slice 34 — Project-management / issue-tracker connector
- **Goal.** PM connector mapping tasks/issues/releases to the platform's issue/evidence model (§12.3 board workflow), so external PM state is reflected and traceable.
- **Why now.** Phase-3 "project management"; feeds traceability + issue provenance (gate #7).
- **Spec grounding.** §26.3; §12.3 (1184–1207); tmpl `18_*` (Jira access).
- **Files.** PM connector adapter + mapping repo; reuse `release_issues` where applicable.
- **Migration.** possibly none (reuse `release_issues`) or `0032` mapping table; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; append-only mapping; audit safe-metadata only.
- **Tests.** Task↔issue mapping; RLS isolation; idempotent sync.
- **A5 gate(s) advanced.** Indirect #7 (issue provenance feed).
- **Must NOT claim.** That a synced issue is *provenance-verified complete* (Slice 47).
- **Exit.** PM tasks/issues mapped + traceable; go-live false.

### Track B — Phase 2 intake-compiler closure (§26.2 residuals; parallelizable, OFF the A5-gate critical path)

> **Disposition (honest go-live-criticality).** None of these three residuals is an Appendix-B A5 gate (spec 2981–2997) or a §24.1 go-live-gate condition (2253–2267); the A5 path does not block on them. They **are** spec §26.2 Phase-2 scope and §29 operating-model items 3 ("compile missing specifications where safe") and 2 ("determine whether the package is build-ready"), so they belong on the end-to-end roadmap and are **scheduled here**, runnable in parallel with Track A. (assumption: a future builder may reorder them earlier if richer auto-intake is prioritized.)

#### Slice 35 — Standalone document classifier + source/authority mapping
- **Goal.** A deterministic-first (LLM-assisted, human-reviewed) classifier that routes the many §6.1 document types and performs source/authority mapping (§6.2 steps 1–2), feeding the existing Slice-9 sandbox + Slice-14a extractor.
- **Why now.** Closes the named §26.2 "document classifier"; improves intake automation; off the A5 critical path.
- **Spec grounding.** §6.1 (535–551), §6.2 (557–571 steps `document classification`, `source and authority mapping`); §26.2 (2452); §16.3 untrusted-data handling.
- **Files.** `app/intake/classifier.py` + `app/repositories/classification.py`; reuse `DocumentRepository`, `FakeLLMClient`.
- **Migration.** `0033` — `document_classifications` (tenant-owned, RLS, append-only); additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; documents stay untrusted data (§16.3); classifier output is inert + human-reviewable (no authoritative writes, cf. Slice 14a); audit safe-metadata only.
- **Tests.** Classification of representative doc types; injection-hard-refuse before any model call; RLS; FakeLLM only in CI.
- **Evidence impact.** Improves traceability `claims_to_sources` (§15.2) coverage; no A5 gate.
- **Must NOT claim.** That a classification is authoritative; no auto-promotion; no go-live effect.
- **Exit.** Inert classifications produced + human-reviewable; deterministic tests green; go-live false.

#### Slice 36 — Canonical artifact generator (Spec Generation Mode under §7 independence)
- **Goal.** Generate the §6.3 canonical artifacts (PRD, architecture doc, data model, domain pack, integration plan, AC, test-oracle pack, backlog, task contracts, skill map, tool-access plan, risk register, evidence requirements, go-live checklist) from source docs via Spec Generation Mode (§6.5), as **non-binding** drafts under §7 spec-authorship independence (authorship statuses §7.2; not binding until independently approved).
- **Why now.** Closes the named §26.2 "canonical artifact generator"; extends Slice-14b promotion from single proposals to full artifact sets; off the A5 critical path.
- **Spec grounding.** §6.3 (574–592), §6.5 (611–627); §7.1–7.3 (633–674); §26.2 (2457); tmpl `00`–`25` + `schemas/`.
- **Files.** `app/intake/generator.py` + repo; reuse `IntakeRepository.add_artifact`, extraction promotion, `categories.py`.
- **Migration.** likely additive authorship-status columns/table; `0034`.
- **Tenant/RLS/FK/audit/immutability.** RLS; generated artifacts carry §7.2 authorship status; **not binding until independent approval** (§7.3); Sanad provenance required (§2.4); audit safe-metadata only.
- **Tests.** Generated artifacts inert + status-tagged; cannot become binding without independent approval; provenance enforced; FakeLLM only.
- **Evidence impact.** Populates intake completeness inputs (raises R-level *only* after human approval); no A5 gate directly.
- **Must NOT claim.** That generated AC are binding (that triggers gate #8 risk — must stay `system_authored_unapproved` until approved, §7.2); no go-live effect.
- **Exit.** Artifact generation under authorship independence; binding only via independent approval; go-live false.

#### Slice 37 — Semantic contradiction detector
- **Goal.** Detect **semantic** contradictions across requirements/AC/docs (beyond Slice-13 structural), classifying conflict type per §6.4 (minor wording / scope / business-rule / technical / legal-regulatory / security / budget-timeline / authority) and producing a decision request or proposed resolution **with provenance**.
- **Why now.** Closes the named §26.2 "contradiction detector" semantic half; improves intake quality; off the A5 critical path.
- **Spec grounding.** §6.4 (594–609); §26.2 (2455); §16.5 adversarial gap resolution (1604–1615); §14.4; contrast `app/intake/findings.py` (structural only).
- **Files.** `app/intake/semantic_contradictions.py` + repo; reuse spine + `FakeLLMClient`; kept separate from Slice-13 `findings.py` (no consolidation, cf. Slice 13 discipline).
- **Migration.** `0035` — `semantic_contradiction_reports` (tenant-owned, RLS, append-only); additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; outputs descriptive + provenance-backed; no auto-resolution (decision request only, §6.4); audit safe-metadata only (counts/types — no prose).
- **Tests.** Conflict-type classification; provenance attached; no silent auto-choice (§6.4 "must not silently choose one"); FakeLLM only.
- **Evidence impact.** Feeds the decision-request/approval flow; descriptive only — no readiness/go-live claim.
- **Must NOT claim.** Semantic *correctness* of resolutions; no auto-resolve; no go-live effect.
- **Exit.** Semantic contradictions detected + classified + provenance-backed; descriptive only; go-live false.

### Track A (cont.) — Phase 4: Agent Factory & skill matching

#### Slice 38 — Skill graph + Skill Matching Engine
- **Goal.** Build the §8.2 skill graph and the §8.3 transparent matching score → §8.4 project squad manifest (which agents do which tasks, with reviewers + missing-skill → factory requests).
- **Why now.** Phase-4 entry (§26.4 "skill graph"); prerequisite for staffing real builder/reviewer agents (Phase 5 evidence).
- **Spec grounding.** §8.1–8.4 (692–795); §26.4 (2478).
- **Files.** `app/agents/skills.py` + `app/repositories/skills.py`; reuse Slice-6 registry.
- **Migration.** `0036` — `skills` + `skill_matches`/`squad_manifests`; tenant-aware where holding tenant context.
- **Tenant/RLS/FK/audit/immutability.** RLS for tenant-scoped manifests; global skill catalog (cf. blueprints); audited.
- **Tests.** Deterministic matching score; squad manifest shape; missing-skill → factory request emitted.
- **A5 gate(s) advanced.** None directly (foundational).
- **Must NOT claim.** That matching = qualification (evals are Slice 40).
- **Exit.** Skill graph + matching + squad manifest; go-live false.

#### Slice 39 — Agent realization + factory workflow + broker↔instance wiring
- **Goal.** Realize agents from blueprints (§9.2, `agent_realization_template.yaml`) via the §9.4 factory workflow, and **wire the broker `agent_id` to agent instances** (closes the Slice-6 deferral) so tool authority is instance-scoped.
- **Why now.** §26.4 "agent realization mechanism"; without broker↔instance wiring, no real agent can act under least privilege.
- **Spec grounding.** §9.1–9.4 (799–889); §9.7 versioning (947–961); §26.4; `agent_realization_template.yaml`; README "broker `agent_id` is NOT wired to instances yet".
- **Files.** `app/agents/factory.py` + repo; `app/tools/broker.py` (instance binding); reuse `agent_instances` (Slice 6).
- **Migration.** likely additive realization columns/table; `0037`.
- **Tenant/RLS/FK/audit/immutability.** Tenant-owned instances (RLS, already); immutable bound version (Slice 6); broker decision audited; least-privilege allowlist.
- **Tests.** Realization from blueprint; broker authority scoped to instance allowlist; immutable version on bind.
- **A5 gate(s) advanced.** None directly (enables Phase-5 agents).
- **Must NOT claim.** That a realized agent is qualified (Slice 40) or its work approved (Phase 5).
- **Exit.** Agents realized + bound + broker-scoped; go-live false.

#### Slice 40 — Archetype eval library + dry qualification + Agent QA workflow
- **Goal.** The §9.5.1 archetype eval library (representative tasks, gold-answer/oracle source, rubric, activation threshold, refresh policy per archetype) + dry qualification tests (§9.5) + Agent QA approval (§9.4 step 7); an agent below its activation threshold cannot be registered for autonomous work (§9.5.1 l.930).
- **Why now.** §26.4 "archetype eval library" + "agent QA workflow"; reviewer trustworthiness underpins gates #4–#8.
- **Spec grounding.** §9.5 (891–910), §9.5.1 (912–930 incl. the archetype table); §26.4; `archetype_eval_methodology.yaml`; `reviewer_quality_assurance.yaml`.
- **Files.** `app/agents/evals.py` + repo; eval fixtures; QA-record store (cf. `reviewer_quality_record`).
- **Migration.** `0038` — `agent_eval_runs` + `agent_qa_records`; tenant-aware.
- **Tenant/RLS/FK/audit/immutability.** RLS for project evals; eval results versioned + immutable (§9.5.1 l.930); audited.
- **Tests.** Activation-threshold gating (below threshold ⇒ not registerable); positive/negative/edge/adversarial/incomplete cases (§9.5.1 l.930); determinism.
- **A5 gate(s) advanced.** None directly (qualifies the agents gates #4–#8 rely on).
- **Must NOT claim.** That passing evals = production authority.
- **Exit.** Archetype evals gate agent activation; QA records produced; go-live false.

#### Slice 41 — Generated-agent security review + performance monitoring + replacement policy
- **Goal.** Mandatory §16.8 security review of generated agents before activation (App. C l.3010), performance monitoring, and the §9.6 replacement policy (diagnose failure → recruit/reprompt/reroute/suspend/escalate).
- **Why now.** §26.4 "generated-agent security review", "performance monitoring", "replacement policy"; platform self-defense (App. C).
- **Spec grounding.** §9.6 (932–945); §16.8 (1663–1675); §26.4; App. C (l.3010).
- **Files.** `app/agents/security_review.py` + `app/agents/monitoring.py` + repo.
- **Migration.** `0039` — `agent_security_reviews` + `agent_performance`; tenant-aware.
- **Tenant/RLS/FK/audit/immutability.** RLS; suspend-on-violation audited; lineage separation (App. C l.3006).
- **Tests.** Unreviewed agent cannot activate; replacement triggers fire on failure patterns (§9.6); suspension audited.
- **A5 gate(s) advanced.** None directly (self-defense for the agent fleet).
- **Must NOT claim.** That review = immunity; it is a gate, not a guarantee.
- **Exit.** Generated agents gated by security review + monitored + replaceable; go-live false.

### Track A (cont.) — Phase 5: Review, verification, evidence

#### Slice 42 — Task contracts + maker-checker-verifier workflow + reviewer reports — **MERGED (PR #73, `c7f245e`)**
- **Goal.** §13.2 task contracts (§27.2 shape) created before any builder; the §13.1 three-layer review producing §13.3 structured verdicts (`can_merge`, failed_criteria, suspected_shortcuts, required_changes); enforce §12.3 "builders cannot move their own work to Done".
- **Why now.** §26.5 "maker-checker-verifier workflow / task contracts / reviewer reports"; the spine all Phase-5 gates hang on.
- **Spec grounding.** §13.1–13.3 (1230–1296); §12.3 (1184–1207); §27.2 (2546–2566); §2.2 (no self-approval).
- **Files.** `app/review/task_contracts.py`, `app/review/workflow.py`, `app/models/review_report.py`, repos.
- **Migration.** `0041` — five additive, tenant-owned RLS tables: `task_contracts`, `task_contract_artifact_links`, `task_contract_reviewers`, `review_reports`, and `task_contract_events`.
- **Tenant/RLS/FK/audit/immutability.** RLS; verdicts immutable append-only; reviewer ≠ builder (§2.2); audited.
- **Tests.** Builder cannot self-approve; verdict shape; three-layer routing (role/cross-functional/acceptance, §13.1).
- **A5 gate(s) advanced.** Produces `review_reports` for the evidence pack; underpins #4/#5/#6/#8.
- **Must NOT claim.** That a verdict = acceptance verification (Slice 46) or oracle pass (Slice 43).
- **Exit.** SATISFIED by PR #73 (`c7f245e`): task contracts + reviewer registrations + reported verdicts recorded; the structural self-review/done gate is present; go-live remains false.

#### Slice 43 — Test-oracle execution subsystem (gate #4) — **MERGED (PR #76, `52785b3`)**
- **Goal.** Execute the three §14.2 oracle types (specified / reference / judgment, with §14.3 judgment controls) against critical features, producing per-oracle pass/fail `test_results`. "No oracle, no go-live" enforced (§14.4). Gate #4 PASS-capable.
- **Why now.** §26.5 "test oracle framework"; gate #4 is core to §24.1.
- **Spec grounding.** §14.1–14.4 (1349–1409); App. B #4 (2988); tmpl `09_test_oracles.yaml`; §24.1 "all required test oracles pass".
- **Files.** `app/verify/oracles.py` + runners (specified/reference/judgment) + `app/models/test_result.py` + repo; CI evidence (Slice 26/28) as the run substrate.
- **Migration.** `0042` — `test_oracle_runs` / `test_results`; tenant-owned, RLS ENABLE+FORCE, append-only.
- **Tenant/RLS/FK/audit/immutability.** RLS; results immutable; judgment oracles need ≥2 evaluator lineages + IRR (§14.3); audited.
- **Tests.** Specified pass/fail; reference drift tolerance; judgment rubric + IRR floor; critical feature without valid oracle ⇒ not production-ready (§14.4).
- **A5 gate(s) advanced.** **#4 → PASS-capable** (passes when all *critical* oracles pass).
- **Must NOT claim.** That non-critical-oracle coverage = go-live; that judgment thresholds are universal (illustrative defaults, §14.3).
- **Exit.** Critical-oracle execution + results; gate #4 passes when all critical pass; go-live false.

#### Slice 44 — Security reviewer / scan provenance (gate #5) — **MERGED (PR #78, `33fb926`)**
- **Goal.** Authoritative security-scan coverage (authz/injection/secrets/unsafe-tool/supply-chain, §13.5 archetype + §15) feeding `release_findings` with **verified scan provenance**, so "no unaccepted critical security findings" is provable. Gate #5 PASS-capable.
- **Why now.** §26.5 review; gate #5 needs scan coverage a store alone cannot supply (`production_autonomy.py:186-188`).
- **Spec grounding.** §13.5 (1315–1345), §9.5.1 security-reviewer archetype (l.920); App. B #5 (2989); §15 security; tmpl `15_*`; §16 threats.
- **Files.** `app/verify/security_scan.py` + provenance writer into `release_findings`; gate-#5 logic.
- **Migration.** `0043` — append-only `security_scan_runs` / `security_scan_category_results` plus direct verified-scan attachments on `release_findings`; tenant-owned, RLS ENABLE+FORCE.
- **Tenant/RLS/FK/audit/immutability.** RLS; connector-verified scan provenance; the Slice-23 findings lifecycle remains authoritative and critical findings stay non-acceptable; audit carries safe metadata only.
- **Tests.** Gate #5 passes only with verified five-category scan coverage AND zero open critical security findings from any provenance; absent/incomplete/untrusted coverage ⇒ `insufficient_evidence`.
- **A5 gate(s) advanced.** **#5 → PASS-capable**.
- **Must NOT claim.** Absence of findings without scan coverage; critical findings remain hard blockers.
- **Exit.** SATISFIED by PR #78 (`33fb926`): verified exact-binding security-scan provenance is present; gate #5 is PASS-capable under `slice44.v1`; readiness remains `slice20.v1`; go-live remains false.

#### Slice 45 — Shortcut detector execution (gate #6) — **MERGED (PR #80, `d063ebe`)**
- **Goal.** Run the §13.4 shortcut/fake-done checklist as an independent reviewer feeding `release_findings` (shortcut type) with verified provenance. Gate #6 PASS-capable.
- **Why now.** §26.5 "shortcut detector"; §2.1 "No fake done" enforcement at release.
- **Spec grounding.** §13.4 (1298–1313); App. B #6 (2990); §9.5.1; §2.1 (l.129–149).
- **Files.** `app/verify/shortcut_detector.py` + provenance writer; gate-#6 logic.
- **Migration.** `0044` — append-only `shortcut_detector_runs` / `shortcut_detector_category_results` / `shortcut_detector_reviewer_results` plus direct verified shortcut attachments on `release_findings`; tenant-owned, RLS ENABLE+FORCE.
- **Tenant/RLS/FK/audit/immutability.** RLS; connector-verified corpus provenance + separately system-executed deterministic/reviewer provenance; DB-enforced registered-builder/reviewer separation; critical non-acceptable; audit safe metadata only.
- **Tests.** Gate #6 passes only with trusted 12-category hybrid coverage + zero open critical shortcut findings from any provenance; planted-shortcut fixtures detected without claiming universal recall.
- **A5 gate(s) advanced.** **#6 → PASS-capable**.
- **Must NOT claim.** Absence of shortcuts without detector coverage.
- **Exit.** SATISFIED by PR #80 (`d063ebe`): exact-binding hybrid shortcut execution and independent-review provenance are present; gate #6 is PASS-capable under `slice45.v1`; readiness remains `slice20.v1`; go-live remains false.

#### Slice 46 — Acceptance verifier + spec-authorship independence + generated-AC release-gate binding (gate #8) — **MERGED (PR #82, `caee2bf`)**
- **Goal.** An acceptance verifier (§13.1 acceptance layer) that binds release gates to AC carrying approved authorship status (§7.2), proving "no unapproved generated AC gate the release". Gate #8 PASS-capable.
- **Why now.** §26.5 "acceptance verifier"; gate #8 + §7 acceptance-criteria paradox.
- **Spec grounding.** §7.1–7.3 (633–674); §13.1; App. B #8 (2992); tmpl `08_acceptance_criteria.yaml` (authorship/dispute).
- **Files.** `app/verify/acceptance.py` + AC-authorship binding + gate-#8 logic; reuse extraction promotion (Slice 14b).
- **Migration.** `0045` — append-only acceptance-authorship records plus exact-binding verification runs/results; tenant-owned, RLS ENABLE+FORCE.
- **Tenant/RLS/FK/audit/immutability.** RLS; `system_authored_unapproved`/`disputed` AC cannot gate a release (§7.2); audited.
- **Tests.** Gate #8 passes only when every in-scope AC has current DB-verified independent-agent lineage evidence; unknown/unverified/human-owner/unapproved/disputed AC block.
- **A5 gate(s) advanced.** **#8 → PASS-capable**.
- **Must NOT claim.** That system-authored unapproved AC are binding (§7.1).
- **Exit.** SATISFIED by PR #82 (`caee2bf`): gate #8 is PASS-capable only through DB-verified independent-agent lineage; human-owner approvals remain non-gating; A5 ruleset `slice46.v1`; readiness `slice20.v1`; go-live false.

#### Slice 47 — Issue provenance + findings→issue bridge + `risk_acceptance.release_id` FK (gate #7, partial) — **NEXT PLANNED (NOT STARTED)**
- **Goal.** Upgrade `release_issues` provenance from `caller_supplied_unverified` to reviewer/CI/verifier-verified; bridge `release_findings` → `release_issues`; add the deferred `risk_acceptance_records.release_id` → `release_candidates` FK (`.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md`). Moves gate #7 toward PASS-capable (still needs the release verdict, Slice 50).
- **Why now.** §26.5/§24.1; the missing half of gate #7 is *issue provenance/completeness*.
- **Spec grounding.** §24.1 (2251–2285); App. B #7 (2991); Slice 23/24/25 deferrals.
- **Files.** `app/release/issues.py` (verified provenance), findings→issue bridge, migration for the FK; gate-#7 logic.
- **Migration.** Any additive revision after current head `0045` is to be determined by the reviewed Slice-47 plan; it must include the provenance columns + findings→issue link + `risk_acceptance_records.release_id` FK (per Slice-25 D-RB no-retro-FK deferral now closed).
- **Tenant/RLS/FK/audit/immutability.** RLS; verified provenance; FK pins to same tenant/project; append-only history; audited.
- **Tests.** Verified issue provenance; findings spawn/link issues without double-count; `release_id` FK validates same-project.
- **A5 gate(s) advanced.** **#7 → partially PASS-capable** (completes with Slice 50 verdict).
- **Must NOT claim.** That a populated store proves *completeness* — completeness comes from the release verdict over bound issues (Slice 50).
- **Exit.** Verified issue provenance + bridge + FK; gate #7 still `insufficient_evidence` pending verdict; go-live false.

#### Slice 48 — Reviewer QA harness (planted defects, miss-rate, replacement triggers)
- **Goal.** The §13.5 reviewer-QA program (`reviewer_quality_assurance.yaml`): planted-defect/shortcut sampling, miss-rate tracking, reviewer-replacement threshold, blind challenge reviews — producing `reviewer_quality_records` for the evidence pack.
- **Why now.** §26.5 review-the-reviewers; required for trustworthy gates #4–#8 + evidence-pack `reviewer_quality_records`.
- **Spec grounding.** §13.5 (1315–1345); `reviewer_quality_assurance.yaml` (sampling 0.05, max critical miss 0.00, max false-approval 0.03); §27.9.
- **Files.** `app/verify/reviewer_qa.py` + `reviewer_quality_records` store.
- **Migration.** `0046` — `reviewer_quality_records`; tenant-aware.
- **Tenant/RLS/FK/audit/immutability.** RLS; records immutable; reviewer suspension audited.
- **Tests.** Planted-defect injection; miss-rate computed; reviewer above miss threshold suspended (cannot approve high-risk, §13.5 l.1345).
- **A5 gate(s) advanced.** Indirect (evidence-pack `reviewer_quality_records`; reviewer trust for #4–#8).
- **Must NOT claim.** That QA passing = zero risk.
- **Exit.** Reviewer QA records + replacement triggers; go-live false.

#### Slice 49 — Evidence-pack generator + auditor + export (§15/§27.11/§28.1)
- **Goal.** Assemble the release-scoped evidence pack from all sources (traceability, test_results, review_reports, reviewer_quality_records, risk_acceptances, provenance_chains, audit_log_hash, verdict, signatures), validate against `evidence_pack_schema.json`, and export (JSON + human-readable + signed manifest + read-only auditor access). **Fail the evidence gate on missing required fields** (§28.1 l.2912).
- **Why now.** §26.5 "evidence pack auditor"; "the artifact of done" (§15.1); prerequisite for the release verdict (Slice 50).
- **Spec grounding.** §15 (1413–1536); §27.11 (2769–2794); §28.1 (2851–2914); `schemas/evidence_pack_schema.json`; §15.3 definition-of-done (1476–1490).
- **Files.** `app/release/evidence_pack.py` + `app/models/evidence_pack.py` + repo + exporter + JSON-Schema validator.
- **Migration.** `0047` — `evidence_packs` (tenant-owned, RLS, immutable once verdict attached); additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; pack immutable post-verdict (cf. audit/cost); `audit_log_hash` from Slice-2 `audit_verify`; provenance_chains from Sanad; signing via Slice 27/60.
- **Tests.** Schema validation; missing required field ⇒ gate fails (§28.1 l.2912); traceability links resolve; tamper-evident hash.
- **A5 gate(s) advanced.** Enables the verdict (Slice 50) consuming gate states; supports #7/#8.
- **Must NOT claim.** That a generated pack = a passed verdict (verdict is Slice 50); export is a claim about evidence, not a replacement (§28 l.2914).
- **Exit.** Schema-valid, signed, exportable evidence pack; missing-field fail-closed; go-live false.

### Track A (cont.) — Phase 6: Production release & operations

#### Slice 50 — Release manager + release verdict (§24.3) — completes gate #7
- **Goal.** A release manager consuming all evidence + the bound `release_candidates`/issues to emit a §24.3 verdict (`passed | passed_with_limitations | failed_blocking_issue | failed_missing_evidence | requires_human_decision | not_applicable`); completes gate #7 (open issues either non-blocking or risk-accepted, over the *frozen* release's bound issues).
- **Why now.** §26.6 "release manager"; gate #7 completeness needs a verdict over the release's bound issues.
- **Spec grounding.** §24.1 (2251–2285), §24.3 (2332–2341); App. B #7 (2991); evidence_pack `verdict` enum.
- **Files.** `app/release/release_manager.py` + `release_verdicts` store; gate-#7 completion logic.
- **Migration.** `0048` — `release_verdicts`; tenant-owned, RLS, append-only.
- **Tenant/RLS/FK/audit/immutability.** RLS; verdict immutable; consumes Slice-25 frozen candidate + Slice-47 verified issues; audited.
- **Tests.** Verdict reflects gate states; open unaccepted blocking issue ⇒ `failed_blocking_issue`; missing evidence ⇒ `failed_missing_evidence`; gate #7 passes only when all bound open issues are non-blocking or risk-accepted.
- **A5 gate(s) advanced.** **#7 → PASS-capable** (over a frozen release with verified issue provenance + verdict).
- **Must NOT claim.** That a `passed` verdict = go-live (still needs gates #2/#3/#9/#10/#11/#12/#13 + verified pre-approval).
- **Exit.** Release verdict over bound issues; gate #7 passes when conditions hold; go-live false.

#### Slice 51 — Cost forecast model (gate #9)
- **Goal.** A forward cost **forecast** (vs the ledger's incurred-spend stop-decision) compared to `21_cost_and_resource_policy.yaml` (`require_approval_above_forecast_percentage`). Gate #9 PASS-capable.
- **Why now.** Needed after the release/evidence foundation (S49–S50): A5 gate #9 cannot pass without forward cost-forecast evidence, which is distinct from the cost ledger's incurred-spend stop-decision (§19; `app/cost.py`).
- **Spec grounding.** §19 (1830–1933); App. B #9 (2993); tmpl `21_*`; §19.7 stop conditions.
- **Files.** `app/cost_forecast.py` + repo; reuse cost ledger (Slice 7).
- **Migration.** possibly `0049` — forecast snapshots; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; forecast snapshots append-only; audited.
- **Tests.** Forecast vs policy threshold; over-forecast ⇒ approval required; gate #9 passes only when forecast within policy.
- **A5 gate(s) advanced.** **#9 → PASS-capable**.
- **Must NOT claim.** That incurred-spend = forecast.
- **Exit.** Forecast model; gate #9 passes within policy; go-live false.

#### Slice 52 — Rollback verification (gate #10)
- **Goal.** Execute + verify a rollback path (staging/drill) producing rollback-verified evidence. Gate #10 PASS-capable.
- **Why now.** Needed before go-live: A5 gate #10 requires a *verified* rollback, not rollback intent (§24.2 distinguishes a plan from a verified rollback), so it must exist before the control loop (S55) can authorize release.
- **Spec grounding.** §24.2 (2287–2330 `rollback_verified: required`); §25; App. B #10 (2994); §9.5.1 deployment/SRE archetype.
- **Files.** `app/release/rollback.py` + `rollback_verifications` store; deploy connector (Slice 30).
- **Migration.** `0050` — `rollback_verifications`; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; immutable verification records; audited.
- **Tests.** Verified rollback drill; gate #10 passes only on verified rollback; failure ⇒ `insufficient_evidence`.
- **A5 gate(s) advanced.** **#10 → PASS-capable**.
- **Must NOT claim.** That a rollback *plan* = a *verified* rollback (§24.2 distinguishes).
- **Exit.** Verified rollback evidence; gate #10 passes; go-live false.

#### Slice 53 — Production-approval workflow → verified A5 pre-approval (gate #12)
- **Goal.** A formal release-approval workflow (§18.2 production pattern) producing a **request-authenticated, verified A5 pre-approval under stated conditions** (Slice 27 identity + Slice 33 channel). Gate #12 PASS-capable AND removes the second `NO_GO_LIVE_REASON` (`production_autonomy.py:38-41`).
- **Why now.** Needed once gate evidence exists: A5 gate #12 requires a request-authenticated, verified production pre-approval under stated conditions, so its prerequisites (S27 verified identity, S33 approval channel) must already be in place.
- **Spec grounding.** §18.2 (1769); §24.1; App. B #12 (2996); tmpl `20_*`, `23_go_live_checklist.yaml`; §5.2 "Deploy production — A4/A5".
- **Files.** `app/release/production_approval.py` + `production_approvals` store; approval engine (Slice 4) + verified identity (Slice 27).
- **Migration.** `0051` — `production_approvals`; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; verified-approver provenance; mandatory-approval non-bypassable (`app/policy/matrix.py`); audited.
- **Tests.** Gate #12 passes only with a verified pre-approval under stated conditions; unverified approval ⇒ `insufficient_evidence`.
- **A5 gate(s) advanced.** **#12 → PASS-capable** + removes the second go-live blocker.
- **Must NOT claim.** That a pre-approval = go-live (still needs all 13 gates passed AND `a5_satisfied`).
- **Exit.** Verified A5 pre-approval; gate #12 passes; go-live still false unless all 13 + `a5_satisfied`.

#### Slice 54 — Emergency stop / rollback authority (gate #13)
- **Goal.** An emergency-stop mechanism + bound authority (who may halt/rollback) per App. C l.3016 + §25.2 (rollback "Approval or pre-approved emergency rollback policy"). Gate #13 PASS-capable.
- **Why now.** Needed before the control loop (S55) can authorize go-live: A5 gate #13 requires an emergency stop / rollback authority to exist (App. C l.3016), reusing the rollback path (S52) and verified identity (S27).
- **Spec grounding.** App. C (l.3016); §25.2 (2381–2389); App. B #13 (2997).
- **Files.** `app/release/emergency_stop.py` + authority binding + `emergency_stop_authorities` store.
- **Migration.** `0052` — `emergency_stop_authorities`; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; authority binding immutable + audited; verified identity (Slice 27).
- **Tests.** Emergency stop halts a run; authority required to invoke; gate #13 passes only with bound authority.
- **A5 gate(s) advanced.** **#13 → PASS-capable**.
- **Must NOT claim.** That a mechanism without bound authority suffices.
- **Exit.** Emergency-stop mechanism + authority; gate #13 passes; go-live false.

#### Slice 55 — §23.3 main control loop + go-live execution under policy
- **Goal.** The §23.3 autonomous control loop (read state → build → PR → CI → reviews → shortcut/acceptance → evidence pack → check cost/authority → deploy staging → evaluate go-live gate → deploy production iff gate passed AND autonomy policy allows). This is the first point where `a5_satisfied` (all 13) AND a verified pre-approval can co-occur and `can_go_live_autonomously` becomes *reachable* — under policy + explicit authority.
- **Why now.** §26.6/§23.3; the loop that turns pass-capable gates into an actual governed release.
- **Spec grounding.** §23.3 (2188–2212); §24.1; §2.6; §5.1 A5; App. B (all 13).
- **Files.** `app/runtime/control_loop.py` (extends Slice 8a/8b engine); go-live gate evaluation wiring `production_autonomy` + verdict + verified pre-approval.
- **Migration.** likely none (reuses runtime tables) or additive run-state.
- **Tenant/RLS/FK/audit/immutability.** RLS; every step audited + checkpointed (Slice 8a); cost STOP→pause (Slice 8b); production deploy structurally approval-gated.
- **Tests.** Loop halts at the go-live gate unless all 13 gates pass AND verified pre-approval AND policy permits; deploy-production never auto-ALLOW without these.
- **A5 gate(s) advanced.** Consumes all; makes `can_go_live_autonomously` *reachable* (not default-true).
- **Must NOT claim.** Any go-live without all 13 gates + verified pre-approval + policy; the loop never bypasses §2.6.
- **Exit.** Governed control loop; go-live reachable only under full gate+approval+policy; default still false.

### Track A (cont.) — Phase 6 operations & stabilization cluster (post-go-live functional system; §25.1–§25.4)

> These four slices make the system **functional after launch**, not merely A5-passable (see §11).

#### Slice 56 — Post-launch monitoring (the full §25.1 signal set)
- **Goal.** Monitor the complete §25.1 list: uptime, error rates, latency, job failures, security alerts, user-journey failures, data-quality issues, cost anomalies, model-output drift, support tickets, incident reports — beyond gate #11's "alerts active".
- **Why now.** Needed after go-live execution (S55): §25.1 requires *live* operational signals, not just the pre-release "alerts active" evidence of gate #11 (S31); without it the launched system is unobservable.
- **Spec grounding.** §25.1 (2363–2375); §26.6 "post-launch monitoring"; `stabilization_window_policy.yaml` (`monitored_journeys`, `error_budget_threshold`).
- **Files.** `app/ops/monitoring.py` + per-signal collectors (reuse Slice-31 connector) + `ops_signals` store.
- **Migration.** `0053` — `ops_signal_snapshots`; tenant-owned, RLS, append-only.
- **Tenant/RLS/FK/audit/immutability.** RLS; append-only signal history; audited.
- **Tests.** Each signal class recorded; thresholds drive alerts; model-drift + data-quality + cost-anomaly detection fire on fixtures.
- **A5 gate(s) advanced.** Deepens #11 beyond "active" to "observed" (operational, not a new gate).
- **Must NOT claim.** That monitoring = incident resolution (Slice 57).
- **Exit.** Full §25.1 signal coverage; go-live operationally observable.

#### Slice 57 — Incident workflow + post-launch ticket creation + support handover
- **Goal.** §25.2 incident workflow (autonomous bug ticket / log diagnosis; A2+ patch/hotfix branch) + post-launch ticket creation + §25.4 support handover.
- **Why now.** Needed after monitoring (S56): detected post-launch issues need an incident / ticket / support-handover workflow (§25.2/§25.4) to become actionable rather than just observed signals.
- **Spec grounding.** §25.2 (2377–2389), §25.4 (2417 `support_handover_complete`); §26.6 "incident workflow"; §23.4 `incidents`.
- **Files.** `app/ops/incidents.py` + `incidents` store + ticket integration (Slice 34 PM connector).
- **Migration.** `0054` — `incidents`; tenant-owned, RLS, append-only.
- **Tenant/RLS/FK/audit/immutability.** RLS; incident lifecycle audited; autonomy-gated actions (§25.2 table).
- **Tests.** Incident creation; autonomous vs approval-gated actions per autonomy level; support-handover record.
- **A5 gate(s) advanced.** None (operational).
- **Must NOT claim.** Autonomous production hotfix without approval unless A5 emergency policy permits (§25.2).
- **Exit.** Incident workflow + tickets + handover; go-live operationally supportable.

#### Slice 58 — Self-healing / hotfix + rollback paths
- **Goal.** §25.2 self-healing/hotfix loop (patch branch → hotfix PR → staging hotfix A3+ → production hotfix approval/emergency-policy) reusing rollback (Slice 52) + emergency authority (Slice 54).
- **Why now.** Needed after the incident workflow (S57) plus rollback (S52) + emergency authority (S54): remediation must remain autonomy/policy-governed (§25.2), so those governing dependencies must exist before automated healing acts.
- **Spec grounding.** §25.2 (2381–2389); §26.6 "self-healing/hotfix loop".
- **Files.** `app/ops/self_healing.py` reusing release/rollback/emergency-stop subsystems.
- **Migration.** likely none (reuses deploy/rollback tables).
- **Tenant/RLS/FK/audit/immutability.** RLS; every hotfix audited + evidence-tracked; production hotfix approval-gated.
- **Tests.** Hotfix flow honors autonomy levels; production hotfix blocked without approval/emergency policy; rollback path valid.
- **A5 gate(s) advanced.** None (operational).
- **Must NOT claim.** Unapproved production hotfix.
- **Exit.** Governed self-healing/hotfix + rollback; go-live operationally resilient.

#### Slice 59 — Backup/restore validation + stabilization report + closure authority + continuous-improvement loop
- **Goal.** §25.4 stabilization exit: backup/restore validated, stabilization report, closure authority sign-off (`stabilization_window_policy.yaml`), plus the §25.3 continuous-improvement loop (lessons, recurring-failure patterns, eval/prompt/domain-pack/oracle-gap updates, cost-forecast refresh).
- **Why now.** Needed after operational signals/incidents exist (S56–S58): stabilization closure depends on *measured* exit criteria and a closure authority (§25.4), which can only be evaluated once the live signals and incident history are available.
- **Spec grounding.** §25.3 (2391–2402), §25.4 (2404–2424); §26.6 "continuous-improvement engine"; `stabilization_window_policy.yaml` (`exit_criteria`, `closure_approver`).
- **Files.** `app/ops/stabilization.py` + `stabilization_windows` store + improvement-feedback writer.
- **Migration.** `0055` — `stabilization_windows`; tenant-owned, RLS, append-only.
- **Tenant/RLS/FK/audit/immutability.** RLS; closure sign-off verified-identity + audited; report immutable.
- **Tests.** Exit criteria enforced (zero open critical incidents N days, error budget, backup/restore validated, support handover, rollback valid); closure requires authority; failed exit ⇒ incident/improvement tickets + window extension (§25.4).
- **A5 gate(s) advanced.** None (operational closure).
- **Must NOT claim.** Window closure without exit criteria + closure authority.
- **Exit.** Validated stabilization + closure + improvement loop; the post-go-live system is complete.

### Track A (cont.) — Phase 7: Scale & ecosystem (§26.7)

#### Slice 60 — External-assurance export hardening (OSCAL, signed manifest, auditor access)
- **Goal.** Harden the §28.1 export: JSON Schema + versioned migrations, optional OSCAL mapping, signed manifest of hashes, read-only auditor access (scoped link / temp account / offline bundle), redaction policy.
- **Why now.** Needed after the evidence-pack/release flow exists (S49–S50): external assurance *hardens* export for third-party auditors — it is not core go-live, so it follows the working release flow rather than preceding it (§28).
- **Spec grounding.** §28 (2832–2914); §15.4; `evidence_pack_schema.json`.
- **Files.** `app/release/evidence_export.py` (extends Slice 49); signing + auditor-access.
- **Migration.** possibly `0056` — export/signature metadata; additive.
- **Tenant/RLS/FK/audit/immutability.** RLS; signed + immutable manifest; redaction enforced; no secret/tenant-private leakage (§28.1).
- **Tests.** Schema-valid export; signature verifies; auditor access read-only + expiring; redaction applied.
- **A5 gate(s) advanced.** None (externalization).
- **Must NOT claim.** That export replaces evidence (§28 l.2914).
- **Exit.** Signed, auditor-consumable export; go-live unaffected.

#### Slice 61 — Connector library + vetted-blueprint marketplace + reference-intake companion library
- **Goal.** Generalize connectors (Phase 3) into a permission-scoped, tested library; a marketplace of security-reviewed blueprints; a reference-intake companion library (§20.3).
- **Why now.** Needed after real connectors/agents exist (Phase 3/4): a marketplace/connector/reference library must *generalize proven implementations*, so it follows them rather than preceding them (§26.7).
- **Spec grounding.** §26.7; §20.3 (2039–2044); App. C (l.3012 connectors tested/permission-scoped, l.3010 blueprints security-reviewed).
- **Files.** `app/ecosystem/*`; reuse connector + agent-registry subsystems.
- **Migration.** additive catalog tables; `0057`.
- **Tenant/RLS/FK/audit/immutability.** Global catalogs (immutable versions, cf. blueprints); tenant usage RLS; audited.
- **Tests.** Connector contract tests (§9.5.1 integration archetype); blueprint listing requires security review.
- **A5 gate(s) advanced.** None.
- **Must NOT claim.** Listing without security review/connector tests.
- **Exit.** Vetted connector/blueprint/reference libraries; go-live unaffected.

#### Slice 62 — Advanced cost optimizer + tenant-safe cross-project learning
- **Goal.** §26.7 advanced cost optimizer; cross-project learning obeying §17.5 tenant-safe allowed-aggregate vs forbidden tenant-content rules (App. C l.3009).
- **Why now.** Needed after cost/ops/eval signals exist (S51/S56/S40): optimization and tenant-safe cross-project learning require real aggregate data to learn from (§17.5/§19), which only accrues once the system runs.
- **Spec grounding.** §26.7; §17.5 (1724+); App. C (l.3009); §19 model routing.
- **Files.** `app/ecosystem/cost_optimizer.py`, `app/ecosystem/learning.py`.
- **Migration.** additive; `0058`.
- **Tenant/RLS/FK/audit/immutability.** **Never reuse tenant content** (App. C l.3009) — only anonymized aggregate signals; audited.
- **Tests.** Learning uses only allowed aggregate signals; no tenant-content crossover; cost routing improves on fixtures.
- **A5 gate(s) advanced.** None.
- **Must NOT claim.** Any tenant-content reuse.
- **Exit.** Cost optimizer + tenant-safe learning; go-live unaffected.

#### Slice 63 — Enterprise administration
- **Goal.** §26.7 enterprise administration (org/tenant admin, RBAC, policy management) over the existing tenant model.
- **Why now.** Needed after the core runtime/go-live system exists (S55+): enterprise administration *scales* an already-working system and adds no new go-live capability, so it is intentionally last (§26.7).
- **Spec grounding.** §26.7; §17 multi-tenancy.
- **Files.** `app/admin/*`.
- **Migration.** additive admin tables; `0059`.
- **Tenant/RLS/FK/audit/immutability.** RLS preserved; admin actions audited; no RLS bypass for runtime role.
- **Tests.** RBAC; tenant-boundary preserved; admin actions audited.
- **A5 gate(s) advanced.** None.
- **Must NOT claim.** Admin convenience overriding tenant isolation.
- **Exit.** Enterprise admin; tenant isolation intact; end-to-end system complete.

---

## 6. Recommended immediate next slice

> **Current state (2026-07-12): Slice 46 is MERGED.** PR #82 landed as squash commit `caee2bf`. Migration `0045_acceptance_verification` is the Alembic head; Appendix-B gate #8 is PASS-capable only through DB-verified independent-agent lineage under A5 ruleset `slice46.v1`; human-owner approvals remain non-gating, readiness remains `slice20.v1`, and go-live remains hard-false (`CLAUDE.md` “Current status”; `migrations/versions/0045_acceptance_verification.py`; `app/release/production_autonomy.py`; `app/intake/readiness.py`; git history).

**Next planned (not started): Slice 47 — Issue provenance + findings→issue bridge + `risk_acceptance.release_id` FK (gate #7, partial).** This is the next unsatisfied item in the §5 sequence after merged Slice 46. Its eventual reviewed plan must ground any implementation in spec §24.1, Appendix-B gate #7, the Slice-23/24/25 stores and deferrals, and the current `release_findings` guard; this sequencing marker does not authorize implementation.

**Boundary:** no Slice-47 plan, feature branch, code, test, or migration exists at this checkpoint. The next action is to draft and submit the Slice-47 plan for review; implementation remains blocked until that plan is approved.

---

## 7. Dependency graph

```
                         ┌─────────────────────────────────────────────┐
                         │  request-auth / verified identity (Slice 27) │
                         └───────┬───────────────────────┬─────────────┘
                                 │                        │
        ┌────────────────────────▼───────┐        ┌───────▼──────────────────────┐
        │ source control + branch         │        │ production pre-approval        │
        │ protection + required checks    │        │ (verified A5, gate #12, S53)   │
        │ (Slice 26→28, gate #3)          │        └───────┬───────────────────────┘
        └───┬───────────┬───────────┬─────┘                │
            │           │           │                      │
   ┌────────▼──┐  ┌─────▼──────┐ ┌──▼───────────────┐      │
   │ CI required│  │ test-oracle│ │ security/shortcut │      │
   │ checks #3  │  │ exec #4 S43│ │ scan #5/#6 S44/45 │      │
   └────────────┘  └─────┬──────┘ └──────┬────────────┘      │
                         │               │                   │
                ┌────────▼───────────────▼─────────┐         │
                │ reviewer/verifier workflows        │         │
                │ (Phase 4 agents S38-41 + §13 S42)  │         │
                └────────┬───────────────────────────┘         │
                         │                                      │
              ┌──────────▼─────────────┐                        │
              │ issue provenance #7     │◄──── release candidate │
              │ S47 (+bridge +FK)       │      bindings (Slice 25, present)
              └──────────┬──────────────┘                        │
                         │                                       │
        ┌────────────────▼────────────────┐                      │
        │ release verdict §24.3 (S50)       │                     │
        │ gate #7 complete                  │                     │
        └───────┬───────────────────┬───────┘                     │
                │                   │                             │
       ┌────────▼───────┐   ┌───────▼─────────┐   ┌──────────────▼───┐
       │ rollback verify │   │ monitoring active│   │ deploy target     │
       │ #10 (S52)       │   │ #11 (S31)        │   │ #2 (S30)          │
       └───────┬─────────┘   └───────┬─────────┘   └────────┬─────────┘
               │                     │                       │
       ┌───────▼─────────┐   ┌───────▼──────────────────────▼─────────┐
       │ emergency stop   │   │ cost forecast within policy #9 (S51)    │
       │ #13 (S54)        │   └─────────────────────────────────────────┘
       └───────┬───────────┘
               │
   ┌───────────▼──────────────────────────────────────────────────────────┐
   │ EVIDENCE PACK gen/validate/sign/export (S49,S60; §15/§27.11/§28.1)     │
   └───────────┬──────────────────────────────────────────────────────────┘
               │
   ┌───────────▼──────────────────────────────────────────────────────────┐
   │ §23.3 control loop (S55): a5_satisfied (ALL 13) AND verified A5         │
   │ pre-approval ⇒ can_go_live_autonomously reachable (under policy+authority)│
   └───────────┬──────────────────────────────────────────────────────────┘
               │
   ┌───────────▼──────────────────────────────────────────────────────────┐
   │ POST-GO-LIVE OPS (S56-59): monitoring · incidents · self-heal ·        │
   │ stabilization/closure (§25) — the functional operating system          │
   └───────────────────────────────────────────────────────────────────────┘

   Parallel, off-critical-path: Track B (S35-37) Phase-2 compiler closure
   (classifier · artifact generator · semantic contradictions) — blocks no gate.
```

**Reading.** Source-control/CI (S26–28) is the root; oracles/scans/reviews build on it; issue provenance (S47) draws on reviewers/CI + present release-candidate bindings (Slice 25); the verdict (S50) completes gate #7; rollback/monitoring/deploy/cost/emergency feed the evidence pack; the pack + verified pre-approval are the *only* path to `can_go_live_autonomously` (S55), under policy + authority (§2.6, §5.2 l.485). Post-go-live ops (S56–59) make it a functioning operating system. (Graph from §24.1, §26.3–26.6, §25, and `production_autonomy.py` — **inference** where it orders slices.)

---

## 8. Go-live readiness milestones

A milestone is *claimed* only on evidence (§2.3), never narrative.

### M3 — Phase 3 integration foundation (Slices 26–34, +27)
Claimable when: verified source-control/CI evidence (**gate #3**, S26–28); verified production deploy target (**gate #2**, S30); monitoring connector confirms active alerts (**gate #11**, S31); request-auth verified identity (S27); PR evidence (S29), secrets-reference verifier (S32), comms/approval channel (S33), PM connector (S34) live. Evidence: `connector_verified` rows; DB-backed gate tests. *Go-live false.*

### M4 — Phase 4 agent-factory / skill-matching foundation (Slices 38–41)
Claimable when: skill graph + matching (S38); realization + broker wiring (S39); archetype evals gate activation (S40); generated-agent security review + monitoring + replacement (S41). Evidence: `agent_qa_records` within `reviewer_quality_assurance.yaml` thresholds. *No gate flips; foundational for M5.*

### M5 — Phase 5 verification / evidence-pack foundation (Slices 42–49)
Claimable when: task contracts + reviews (S42); test oracles (**#4**, S43); security scan (**#5**, S44); shortcut detector (**#6**, S45); acceptance verifier (**#8**, S46); issue provenance + bridge + FK (S47); reviewer QA (S48); schema-valid signed evidence pack failing closed on missing fields (S49, §28.1). Evidence: a generated evidence pack with complete traceability + provenance_chains (§15.2). *Go-live false (gates #2/#3/#9/#10/#11/#12/#13 + verdict still pending).*

### M6 — Phase 6 release / operations foundation (Slices 50–59)
Claimable when: release verdict (**#7 complete**, S50); cost forecast (**#9**, S51); rollback verification (**#10**, S52); verified A5 pre-approval (**#12**, S53); emergency authority (**#13**, S54); §23.3 control loop (S55); **and** the operational system — full monitoring (S56), incidents/handover (S57), self-heal/hotfix (S58), backup/restore + stabilization closure + continuous-improvement (S59). **Only here can all 13 gates be green AND a verified pre-approval exist** — the first point `can_go_live_autonomously` is *reachable*, under policy + authority — **and** the system can actually operate and stabilize post-launch (§25). Evidence: `a5_satisfied = true` + verified pre-approval + a `passed`/`passed_with_accepted_risk` verdict + a closed stabilization window.

### M7 — Phase 7 scaling / ecosystem hardening (Slices 60–63)
Claimable when: signed, OSCAL-optional, auditor-consumable export (S60); vetted connector/blueprint/reference libraries (S61); cost optimizer + tenant-safe learning (S62); enterprise admin (S63). Evidence: a signed evidence-pack export an independent auditor can verify without trusting agent claims (§28 l.2849).

---

## 9. Evidence pack plan

The evidence pack is "the artifact of done" (§15.1 l.1417). Grounded in §15.2 (1421–1472), §15.4 (1492–1536), §27.11 (`evidence_pack_schema.json`, 2769–2794), §28.1 (2851–2914), and `schemas/evidence_pack_schema.json`.

### 9.1 Generation, storage, scope
- **Release-scoped** by `release_id` (required, §27.11); the referent is a **frozen `release_candidates` row** (Slice 25); the `risk_acceptance_records.release_id` FK closes at Slice 47.
- **Stored** as tenant-owned, RLS, append-only `evidence_packs` (§23.4 l.2238), assembled by Slice 49; **immutable once a verdict is attached** (cf. audit/cost immutability).
- **Validated** against `evidence_pack_schema.json`; **fail the evidence gate on missing required fields** (§28.1 l.2912).
- **Exported** as JSON (schema-valid) + human-readable + signed hash manifest + read-only auditor access (§15.4 1498–1502; §28.1 2855–2902; Slice 60).

### 9.2 Section → primitive mapping
| Evidence-pack field | Source primitive | Status | Slice |
|---|---|---|---|
| `traceability` | `intake_artifacts` chain (11) + Sanad `intake_provenance` + PR/test links | partial | S29/S43/S49 |
| `test_results` | test-oracle execution | future | S43 |
| `review_reports` | maker-checker-verifier | future | S42 |
| `reviewer_quality_records` | reviewer-QA harness | future | S48 |
| `risk_acceptances` | `risk_acceptance_records` (22) | **present** | — |
| `provenance_chains` | Sanad `intake_provenance` + `app/core/provenance.py` | **present (intake)** | S49 (assemble) |
| `audit_log_hash` | Slice-2 hash-chained `audit_logs` + `audit_verify()` | **present** | S49 |
| `verdict` | release verdict (§24.3) | future | S50 |
| `signatures` | verified pre-approval + signing | future | S27/S53/S60 |
| `scope` (incl/excl requirements, limited-scope) | `release_candidates` + bindings (25) | **present** | — |
| `open_issues`/`accepted_risks`/`exceptions` | `release_issues` (24) + `risk_acceptance_records` (22) | **present** | — |
| integrity manifest/signature/key/log-ref | signing + audit-log ref (§28.1 2892–2897) | future | S60 |

**Insight (inference):** risk acceptances (22), open issues (24), release scoping (25), Sanad chains (11), and the tamper-evident audit hash (2) **already exist**; the missing inputs are the Phase-3/5/6 *evidence sources*. The evidence-pack generator (S49) is an **assembler** over present + future primitives.

---

## 10. Phase 2–7 spec-component → slice coverage matrix

Proves every named spec component maps to a future slice or milestone (no orphan components).

**Phase 2 residuals (§26.2, 2452–2459).** document classifier → **S35**; requirement extractor → DONE (14a); gap detector → DONE (13); contradiction detector → DONE structural (13) + **S37** semantic; build readiness auditor → DONE (12/16/18/20); canonical artifact generator → **S36**; intake template pack → DONE (docs/); Sanad provenance store → DONE (11).

**Phase 3 (§26.3, 2463–2472).** project management → **S34**; source control → **S26/S28**; pull requests → **S29**; CI/CD → **S26/S28**; staging deployment → **S30**; communication/approval channel → **S33**; secrets reference verification → **S32**; monitoring integration → **S31**. (+ request-auth enabler **S27**.)

**Phase 4 (§26.4, 2476–2485).** skill graph → **S38**; agent blueprint registry → DONE (6) + **S39**; agent realization mechanism → **S39**; archetype eval library → **S40**; agent QA workflow → **S40**; generated-agent security review → **S41**; performance monitoring → **S41**; replacement policy → **S41**.

**Phase 5 (§26.5, 2489–2498).** maker-checker-verifier workflow → **S42**; task contracts → **S42**; reviewer reports → **S42**; test oracle framework → **S43**; shortcut detector → **S45**; acceptance verifier → **S46**; evidence pack auditor → **S49**; go-live readiness agent → **S50/S55**. (+ security scan **S44**, reviewer QA **S48**, issue provenance **S47**.)

**Phase 6 (§26.6, 2502–2510).** release manager → **S50**; production approval workflow → **S53**; rollback verification → **S52**; post-launch monitoring → **S56**; incident workflow → **S57**; self-healing/hotfix loop → **S58**; continuous improvement engine → **S59**. (+ cost forecast **S51**, emergency stop **S54**, §23.3 loop **S55**.)

**Phase 7 (§26.7, 2514–2522).** marketplace of vetted blueprints → **S61**; connector library → **S61**; reference-intake companion library → **S61**; external assurance export format → **S60**; advanced cost optimizer → **S62**; cross-project learning → **S62**; enterprise administration → **S63**.

**13 A5 gates (App. B).** #1 DONE; #2 S30; #3 S26→28; #4 S43; #5 S44; #6 S45; #7 S47+S50; #8 S46; #9 S51; #10 S52; #11 S31; #12 S27+S53; #13 S54; aggregate `a5_satisfied` + go-live reachability S55.

---

## 11. What makes the system functional *after* go-live (operational depth, §25)

Go-live is not the end state; spec §29 item 16 requires "Monitor and stabilize after launch." A truly end-to-end roadmap must deliver a functioning operating system, not just pass the 13 gates. Mapping every §25.1–§25.4 operational concern to a slice:

| Operational concern (§25) | Requirement | Slice |
|---|---|---|
| uptime, error rates, latency | continuous SLO monitoring (§25.1) | S56 |
| job failures | failure monitoring (§25.1) | S56 |
| security alerts | post-launch security signal (§25.1) | S56 |
| user-journey failures | monitored journeys (§25.1; `stabilization_window_policy.yaml`) | S56 |
| data-quality issues | data-quality monitoring (§25.1) | S56 |
| cost anomalies | cost-anomaly detection (§25.1, §19) | S56 |
| model-output drift | drift monitoring (§25.1; `model_change_policy.yaml`) | S56 |
| support tickets, incident reports | incident workflow + tickets (§25.1/§25.2) | S57 |
| post-launch ticket creation | autonomous bug ticket (§25.2) | S57 |
| support handover | handover record (§25.4) | S57 |
| hotfix + rollback paths | self-healing/hotfix (§25.2) + rollback (S52) + emergency authority (S54) | S58 |
| backup/restore validation | exit criterion (§25.4) | S59 |
| stabilization report + closure authority | exit + closure sign-off (§25.4; `stabilization_window_policy.yaml`) | S59 |
| continuous-improvement feedback loop | lessons/evals/prompts/oracle-gaps/cost-forecast (§25.3) | S59 |

**Definition of "functional after go-live" (this roadmap's bar):** all §25.1 signals observed (S56); incidents created/triaged/handed over (S57); governed self-healing/hotfix/rollback under autonomy policy (S58); stabilization window with enforced exit criteria, validated backup/restore, and authorized closure, feeding a continuous-improvement loop (S59). Until S56–S59 exist, the system can *pass* A5 gates but cannot *operate* post-launch — so the end-to-end roadmap is not complete at S55.

---

## 12. Open decisions requiring coordinator approval

- **D-1 — Slice 26 vs 27 ordering.** (a) CI evidence store first, then request-auth; (b) request-auth first; (c) interleave. **Default (a)** — self-contained, follows §26.3, no gate-pass risk on unverified data; request-auth (S27) lands before any **additional, non-#1** gate is allowed to PASS (gate #1 already passes at R5 without request-auth, `production_autonomy.py:124-127`). (assumption: request-auth not a hard blocker for *building* the unverified-tier store.)
- **D-2 — Two-tier provenance vs separate verified tables.** **Default: one store + `provenance ∈ {caller_supplied_unverified, connector_verified}` column** — minimal churn, matches `findings.py`/`issues.py` convention.
- **D-3 — `risk_acceptance_records.release_id` retro-FK timing.** **Default: Slice 47** (bundle with issue-provenance that needs it). (`.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md` deferred it.)
- **D-4 — Connector platform priority.** Repo uses GitHub (`.github/workflows/ci.yml`, `gh`). **Default: GitHub-first** behind a thin adapter (generalized in S61). (inference.)
- **D-5 — Evidence-pack schema variant.** Spec ships two shapes: §27.11 (canonical asset `schemas/evidence_pack_schema.json`) and the longer §15.4 list. **Default: §27.11 canonical**, §15.4 fields as optional expanded sections. Coordinator to confirm.
- **D-6 — Track-B scheduling.** Phase-2 closure (S35–37) is off the A5 critical path. **Default: run in parallel after S26 ships**, builder's discretion; not the gate-path next step. (assumption.)
- **D-7 — Temporal revisit.** Deferred until a `.planning/PHASE-1-PLAN.md` trigger (distributed multi-worker, hard event-sourced replay, multi-region/compliance) is met — likely surfaced by S55 (§23.3 loop) or Phase 7. Flagged so it is not forgotten.

---

## 13. Non-negotiable invariants

Hold for every slice (spec §2, §15, App. C; reaffirmed across Slices 21–25):
1. **No fake done** (§2.1 "No fake done", l.129–149 "prefer an honest blocker over fake completion"; `19_autonomy_policy.yaml` `no_fake_done`).
2. **Evidence over claims** (§2.3, §15.1).
3. **No agent approves its own work** (§2.2, §7.1, §13.5, §12.3 l.1207).
4. **Fail closed on missing evidence** — missing/unverified ⇒ `insufficient_evidence`/`no_evidence_source` (`production_autonomy.py:120-121`).
5. **No production deploy path until all 13 A5 gates have real evidence AND a verified pre-approval** (§2.6, §24.1, App. B).
6. **Tenant isolation / RLS** on every tenant-owned table (`ENABLE`+`FORCE` + `tenant_isolation`, runtime non-superuser `uaid_app`).
7. **Audit safe-metadata only** — ids/status/counts, never prose/secrets/bodies.
8. **No secrets in repo / audit / logs** — reference-only (`categories.py` denylist; tmpl `17_*`).
9. **`.env` never committed** (gitignored; CLAUDE.md "Secrets").
10. **Append-only / immutable ledgers** via DB-guard triggers (migrations `0003/0008/0014/0021`–`0024` and every new store).

---

## 14. Source Reconciliation / Stale Status Notes

Some `.planning/` files retain **pre-implementation status text** conflicting with the merged reality. **Authoritative current source of truth:** CLAUDE.md "Current status" + README.md + git log + Alembic head + actual code/migrations — these agree Slices 17–42 are merged. Slice-41 and Slice-42 plan headers were reconciled after their merges; older stale headers below remain historical artifacts.

| Conflict | Stale text (verbatim) | Verdict | Evidence |
|---|---|---|---|
| Slice 24 status | `.planning/SLICE-24-PLAN.md:1-11` — "Status: APPROVED FOR EXECUTION pending the standing gate — **no branch / no code / no migration / no tests until this PLAN is approved.**" | **MERGED / implemented** — stale | git `4c6c1f4 … (#38)` + `7a2ae44 … (#37)`; migration `0023`; `app/release/issues.py`; CLAUDE.md "Slice 24 … PR #37". |
| Slice 25 plan status | `.planning/SLICE-25-PLAN.md:1-16` — "Status: **AWAITING PLAN APPROVAL** — no branch / no code / no migration / no tests until approved." | **MERGED / implemented** — stale | git head `3ec8116 … (#40)` + `f706a30 … (#39)`; migration `0024`; `release_candidates.py`; `production_autonomy.py:31` `slice25.v1`. |
| Slice 25 discussion status | `.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md:1-4` — "Status: **OPEN** — awaiting coordinator rulings on D-RB-1..8 before any PLAN." | **RESOLVED / merged** — stale | Same as Slice 25; the implemented store reflects D-RB rulings. |
| Slices 17–23 plan status | Headers read "APPROVED … and IMPLEMENTED — historical record" (e.g. `SLICE-22-PLAN.md:3`, `SLICE-23-PLAN.md:4-10`). | **Consistent — no conflict** | match CLAUDE.md + git. |

**Reconciliation rule (assumption, explicit):** where a `.planning/` header contradicts CLAUDE.md + git + migrations + present code, **code + git + CLAUDE.md win** (post-merge record; headers were written pre-approval and not back-stamped). No `.planning/` file is modified by this roadmap — stale headers are left intact as historical artifacts and reconciled here.

---

## Appendix R — Review checklist for this roadmap (APPROVE / REJECT)

**Sources read (read-first discipline):**
- [x] `CLAUDE.md`, `README.md`.
- [x] Spec — §2 (creed/principles), §4.3 (R0–R5), §5.1–5.2 (A0–A5 + authority matrix), **§6 (Documentation-to-Delivery Compiler: pipeline/artifacts/contradiction/spec-gen)**, **§7 (spec-authorship independence)**, **§8 (Skill Matching)**, **§9 (Agent Factory + §9.5.1 archetype evals)**, §12.3/12.4 (board + PR workflow), §13 (maker-checker-verifier), §14 (oracles), §15 (evidence pack), §16 (self-defense threats), §17 (tenancy), §18 (HITL), §19 (cost), §23 (runtime), §24 (go-live), §25 (stabilization), §26 (Phase 1–7), §27 (templates), §28 (export), §29 (operating model), Appendix A/B/C/D.
- [x] Intake pack README + all 26 templates + 7 `schemas/` (default-vs-blank noted for `23_*`/`24_*`).
- [x] Planning: `PHASE-1-PLAN.md`, `SLICE-17..25-PLAN.md`, the discussions.
- [x] Code: `production_autonomy.py` + repo; the four release stores + repos; `readiness.py` + repo; `categories.py`; migrations through head `0024`.

**Content coverage (answers the five resubmission questions):**
- [x] Q1 complete / Q2 partial-deferred → §2.6 ledger (every Slice 1–25 subsystem, status, residual).
- [x] Q3 every deferred item scheduled → §2.6 "Scheduled in" → §5 (Track A 26–63 + Track B 35–37); nothing unscheduled.
- [x] Q4 every Phase 3–7 spec component mapped → §10 coverage matrix.
- [x] Q5 functional after go-live → §11 operational-depth (§25.1–25.4 → S56–59).
- [x] Phase 2 closure scheduled with full field sets (Blocker 1) → S35/S36/S37.
- [x] All Phase 3 integrations slice-mapped incl. PM/PR/comms/secrets (Blocker 2) → S29/S32/S33/S34.
- [x] Phase 5/6/7 expanded to roadmap-grade with full field sets (Blocker 3) → S42–S63.
- [x] Post-go-live ops cluster (Blocker 4) → S56–S59 + §11, each citing §25.1–25.4 / §26.6.
- [x] 13-gate matrix; phase roadmap; recommended next slice; dependency graph; milestones; evidence-pack plan; open decisions; invariants; source reconciliation.

---

## Appendix S — Muhasabah self-audit

- **Unsourced claims removed or cited.** Every claim cites a spec section/line, template/schema, `.planning/` doc, source file, or migration; gate line numbers from `production_autonomy.py`. Ordering not dictated by a single source is **(inference)**; planning choices **(assumption)**.
- **Assumptions labelled.** The original Slice-26+ sequence was a proposal (§1.2, §5); merged Slices 26–46 now follow the actual migration chain through `0045`. Future migration numbering from Slice 47 onward remains directional until each plan is reviewed. "PASS-capable" means capability after the named slice, not proof that a particular project currently passes; Track-B scheduling was builder discretion (D-6).
- **No implementation hidden in planning.** This Rev-7 follow-up changes only `CLAUDE.md`, `.planning/GO-LIVE-END-TO-END-ROADMAP.md`, `.planning/HANDOFF.json`, and the Slice-46 plan header. Slice-46 implementation was already reviewed and merged via PR #82; this docs branch changes no code, test, or migration. `.env` and `.planning/.pending-auth-captures.jsonl` remain ignored and unstaged.
- **No go-live overclaim.** `can_go_live_autonomously`/`a5_satisfied` are stated false today; go-live is reachable only after **all 13 gates have verified evidence AND a verified pre-approval** (S55), under policy + authority. Gates #1/#2/#3/#4/#5/#6/#8/#11 are PASS-capable only from their named evidence, and no gate is marked PASS on a store/declaration alone.
- **Scope honesty.** The §26.2 residuals are explicitly classified as **not Appendix-B gates / not §24.1 conditions** (so off the A5 critical path) yet **still scheduled** (Track B) because §26.2/§29 require them — neither hidden nor overstated.
- **Residual uncertainty.** Far-term table shapes (S45–S63) and future migration numbering are directional; each future slice still needs its own PLAN (stated in §5). Some gate→phase assignments span two phases (e.g. monitoring §26.3 connector + §26.6 ops) and are noted as such.

— End of roadmap —
