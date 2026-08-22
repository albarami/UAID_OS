# Slice 55 Plan — §23.3 control loop through go-live gate evaluation

**Status:** APPROVED FOR EXECUTION — plan approved; OD-55-1…9 ruled and bound (see Coordinator rulings (final)).

**Execution authorization:** The plan-only review gate is closed. Implementation is authorized only on `feat/slice-55-control-loop` under the final rulings below; production execution, merge, and any scope expansion remain unauthorized.

**Author persona:** Senior release-control / durable-workflow architect, applying fail-closed production-governance and evidence-integrity discipline.

---

## Coordinator pre-rulings (binding; verbatim)

1. SPLIT RULING: Slice 55 is the §23.3 control loop THROUGH the go-live gate evaluation only. It produces a DB-proven, append-only, hash-chained go-live decision record with status `decided_not_executed` when and only when: all 13 A5 gates pass on a current evaluation, a current verified production pre-approval (Slice 53) exists, autonomy policy permits deploy_production, and no emergency latch is active. deploy_production() execution and any change to the literal `can_go_live_autonomously = False` are OUT OF SCOPE — they belong to a future separately-planned slice and the plan must say so under Must NOT claim.

2. EXECUTION BOUNDARY: the loop may orchestrate only capabilities that already exist in merged slices (through staging deploy), running under the Slice 8a/8b engine with checkpointing, cost STOP→pause, and the Slice 54 emergency latch enforced at every step boundary. No new external connector actions.

3. HONESTY: NO_GO_LIVE_REASONS stays ("a5_gates_not_all_satisfied",) — or if the plan proposes wording changes, they go to an Open Decision for coordinator ruling. The decision record's truth tier must state that pre-approval authority is request-authenticated key custody, not human signature.

These rulings narrow the roadmap entry. They are authoritative for Slice 55 and may not be weakened by an OD or implementation convenience.

## Coordinator rulings (final; verbatim)

- OD-55-1 Option A
- OD-55-2 Option A
- OD-55-3 Option A
- OD-55-4 Option A (the binding MUST enumerate the exact allowlisted invocable functions — A5 evaluation, Slice-49 evidence-pack re-audit, pre-approval coverage read, autonomy policy check, emergency status read, cost STOP evaluate; nothing else)
- OD-55-5 Option A
- OD-55-6 Option A
- OD-55-7 Option A
- OD-55-8 Option A (no HTTP)
- OD-55-9 recommended ruling accepted as written.

### OD-55-4 exact invocation allowlist (binding)

Slice 55 may invoke exactly these already-merged functions and no others:

1. A5 evaluation — `ProductionAutonomyRepository.evaluate` (`app/repositories/production_autonomy.py`).
2. Slice-49 evidence-pack re-audit — `EvidencePackRepository.audit_pack` (`app/repositories/evidence_packs.py`).
3. Pre-approval coverage read — `ProductionPreapprovalRepository.coverage_for_project` (`app/repositories/production_preapprovals.py`).
4. Autonomy policy check — `AutonomyPolicyRepository.decision_for` (`app/repositories/autonomy_policies.py`).
5. Emergency status read — `EmergencyControlRepository.status` (`app/repositories/emergency_controls.py`).
6. Cost STOP evaluate — `app.repositories.cost.evaluate` (`app/repositories/cost.py`).

No other repository, service, connector, broker, LLM, staging, CI, PM, deployment, rollback, or external action is invocable by the Slice-55 loop. Reads needed inside the DB finalizer to prove the ruled decision graph are storage integrity checks, not additional orchestrated capability invocations.

---

## Sanad / citation key

- **Spec** — docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md.
- **Roadmap** — .planning/GO-LIVE-END-TO-END-ROADMAP.md, Rev 15.
- **Session guide** — CLAUDE.md, current status dated 2026-07-14.
- **Runtime** — app/runtime/engine.py; app/runtime/checkpointer.py; app/repositories/runs.py; app/models/project_run.py; app/models/run_step.py; migrations 0009, 0010, and 0053.
- **A5 evaluator** — app/release/production_autonomy.py; app/repositories/production_autonomy.py.
- **Pre-approval** — app/identity.py; app/release/production_approval.py; app/release/production_approval_service.py; app/repositories/production_preapprovals.py; app/models/production_preapproval.py; migration 0052.
- **Policy** — app/policy/matrix.py; app/policy/engine.py; app/repositories/autonomy_policies.py; app/models/autonomy_policy.py.
- **Emergency control** — app/release/emergency_stop.py; app/release/emergency_control_service.py; app/repositories/emergency_controls.py; app/models/emergency_control.py; migration 0053.
- **Staging evidence** — app/release/deploy_connector.py; app/release/deploy_evidence_service.py; app/repositories/deployments.py; app/repositories/rollback_verifications.py; migrations 0029 and 0051.
- **Evidence/release binding** — app/repositories/evidence_packs.py; app/repositories/release_verdicts.py; app/models/evidence_pack.py; app/models/release_verdict.py; migrations 0048 and 0049.
- **Hash-chain prior art** — app/audit.py; app/models/audit_log.py; migration 0003.
- **Baseline commands** — git status --porcelain; git branch --show-current; git rev-parse HEAD; git rev-parse origin/main; git branch --format; git branch -r --format; git log; file existence checks, all run before drafting.

Line citations refer to the checked-out main tree at the baseline in §1.1. Recommendations and implementation shapes are labelled as proposals or inferences; they are not presented as existing facts.

---

## 0. Honesty crux

### 0.1 The split between evaluation and execution

Spec §23.3 lists a loop through evaluate_go_live_gate(), followed by a separate conditional branch that calls deploy_production() and monitor_and_stabilize() (Spec:2188-2212). Coordinator pre-ruling 1 stops Slice 55 at the evaluation boundary. Therefore this slice is a control-and-decision slice, not the full executable tail of the pseudocode.

The only positive outcome this slice may persist is:

> UAID evaluated the current bounded A5 evidence graph inside the durable local workflow, found all thirteen gates passed, found a current Slice-53 pre-approval, found the recorded autonomy policy did not deny deploy_production, found no active emergency latch, and recorded a tamper-evident decision with status decided_not_executed. It did not deploy production.

This is narrower than “go-live executed,” “production authorized,” or “the release is live.” Spec §2.6 requires production deployment to remain inside an explicit approval boundary (Spec:213-228), and §24.1 describes evidence conditions for go-live readiness rather than proof that a deployment occurred (Spec:2251-2271).

### 0.2 “When and only when” predicate

Subject to the policy interpretation in OD-55-2, the positive predicate is exactly:

    all_thirteen_gates_passed
    AND current_slice53_preapproval_gate_eligible
    AND deploy_production_policy_permits_under_recorded_approval
    AND emergency_latch_not_active

No fifth eligibility condition may be added silently. Candidate, evidence-core, verdict, rollback, cost, monitoring, and other evidence currentness are already inputs to the thirteen-gate evaluation and the Slice-53 pre-approval binding; they may be persisted as provenance references but not promoted into new independent gates (A5 repository:117-326; Pre-approval repository:510-671).

If the predicate is false, the loop must not insert a go_live_decisions row with decided_not_executed. The failed or blocked attempt remains visible through append-only control-loop events and the existing audit chain, subject to OD-55-5.

### 0.3 Truth tiers

| Tier | Slice-55 example | What it proves | What it must not be called |
|---|---|---|---|
| **REPORTED / caller-supplied structured policy** | Stored autonomy overrides and template-derived approval policy | What the recorded project policy says | Verified organizational mandate or signed policy |
| **REQUEST-AUTHENTICATED KEY CUSTODY** | Current Slice-53 requester/approver provenance | An active API key bound to the principal authenticated the request | Human signature, human presence, executive approval, or signer assurance |
| **CONNECTOR-OBSERVED** | Existing CI, staging-status, monitoring, scan, and rollback observations consumed by A5 | What the existing bounded connector artifacts report | UAID execution of the observed remote action |
| **SYSTEM-EXECUTED LOCAL RUNTIME** | LangGraph nodes, checkpoints, cost pause, emergency pause | What the current UAID runtime actually executed locally | Distributed worker execution or production infrastructure control |
| **SYSTEM-DERIVED CURRENT EVALUATION** | ProductionAutonomyRepository.evaluate at one ruled as_of instant | The versioned evaluator’s result over the transaction’s current evidence view | Independent DB re-execution of all thirteen gate algorithms |
| **DB-PROVEN DECISION GRAPH** | Same-tenant FKs, exact 13-row result set, current pre-approval/policy/latch bindings, fixed status, immutable predecessor/hash fields | The persisted decision graph satisfies the ruled relational predicate and chain invariants | Proof of future production success, human identity, or completeness beyond the bounded evidence |
| **TAMPER-EVIDENT HASH CHAIN** | prev_entry_hash plus entry_hash over canonical bounded decision fields | Later row mutation, deletion, reordering, or fork is detectable under the DB threat model | Tamper-proof storage against a DB superuser |
| **DECIDED_NOT_EXECUTED** | The only positive Slice-55 decision status | The ruled conditions were met at the recorded evaluation snapshot | Deployment, release, go-live, production permission, or can_go_live_autonomously=true |

The identity limit is source-grounded: app/identity.py says request_authenticated proves possession of an active key, is not a human signature or approval-matrix authority, and never authorizes go-live (Identity:1-12). Slice 53 preserves the same limit and never performs deployment (Production approval contract:1-26).

### 0.4 What “DB-proven” can honestly mean

The existing A5 evaluator is Python and compute-on-read; it writes no report table (A5 repository:1-7,108-119). No current database function or trigger invokes that Python evaluator. The recommended boundary in OD-55-3 is therefore:

- the existing evaluator remains the sole semantic source for each gate;
- one transaction records an immutable evaluation header plus exactly thirteen normalized gate results;
- DB constraints prove the complete child set, allowed status vocabulary, report digest, positive all-passed aggregate, exact current pre-approval/policy/latch references, fixed decided_not_executed status, and hash-chain integrity;
- the plan does not claim that PostgreSQL independently reimplemented all gate semantics.

Reimplementing thirteen gate ladders in SQL would create a second evaluator that can drift from app/release/production_autonomy.py. That is an option for coordinator review, not an unannounced design choice.

### 0.5 Staging honesty gap

Spec §23.3 says deploy_staging_if_ready() before gate evaluation (Spec:2203-2207), and the authority matrix has a deploy_staging action at A3 (Policy matrix:52-62). The merged deployment connector, however, exposes only probe_target(); its service is status-only, verification-only, and explicitly never deploys (Deploy connector:1-23,39-43; Deploy evidence service:1-12,112-163).

Therefore Slice 55 cannot honestly claim to deploy staging under pre-ruling 2. OD-55-1 asks the coordinator to bind the honest interpretation: consume current connector-observed staging/rollback evidence and label the stage staging_evidence_observed_not_deployed, or defer Slice 55 until a separate staging-deployment capability exists. Creating a deploy adapter here is pre-ruled out.

---

## 1. Verified baseline and source findings

### 1.1 Repository state verified before drafting

The following was observed directly:

- branch main;
- HEAD and origin/main both 8550c93b2ddf29e64de03b32c8c61c7c5fb77141;
- clean git status;
- local branches: main only;
- remote branches: origin/main only, apart from the symbolic origin entry shown by git;
- no .planning/SLICE-55-PLAN.md before this draft;
- no app/runtime/control_loop.py;
- Alembic head file migrations/versions/0053_emergency_controls.py with revision 0053 and down_revision 0052;
- A5_RULESET_VERSION = slice54.v1;
- readiness remains slice20.v1;
- CLAUDE.md records 1083 Docker-free and 826 DB-backed tests at the merged Slice-54 checkpoint.

Sources: baseline commands; migration 0053:14-22; A5 evaluator:71-80; Session guide:708-727.

No test suite was run to draft this plan. The counts above are current recorded project history, not fresh plan-task verification.

### 1.2 What the spec and roadmap require

- Autonomous execution must stay inside approved authority boundaries, and production deployment requires explicit approval by default (Spec:213-228).
- A3 permits staging autonomy; A4/A5 production remains approval/gate controlled (Spec:463-485).
- The durable runtime requires persistence, resume, retries, idempotency, approval waits, cancellation/pause, audit, cost tracking, recovery, tool-result persistence, and deterministic reconstruction (Spec:2168-2186).
- §23.3 sequences state reading, work/review/evidence operations, cost/authority checks, staging, and gate evaluation before the separate production branch (Spec:2188-2212).
- §24.1 lists the evidence conditions for go-live readiness and a constrained risk-exception path (Spec:2251-2271).
- The roadmap marks Slice 55 next but predates the coordinator split by describing production execution as part of the slice (Roadmap:543-553,661-665). The pre-rulings supersede that portion for this plan.

### 1.3 Existing primitives to extend, not fork

1. **Durable runtime.** UAIDCheckpointer-backed LangGraph graphs persist state and resume without re-executing completed steps. The current module explicitly says the §23.3 business loop is deferred (Runtime engine:1-28,72-145).
2. **Cost boundary.** The Slice-8b cost path evaluates the existing stop decision before the next node and pauses rather than executing work (Runtime engine:366-423).
3. **Emergency boundary.** Current runtime nodes and entry points call EmergencyControlRepository.enforce_boundary; an active latch pauses a running run and raises before later work (Runtime engine:76-106; Emergency repository:621-645).
4. **A5 report.** ProductionAutonomyRepository composes current tenant-scoped stores and returns the pure thirteen-gate report without persistence (A5 repository:108-326). ProductionAutonomyReport.a5_satisfied is true only when every gate is passed, while serialization keeps can_go_live_autonomously literal False and the one-item reasons tuple (A5 evaluator:71-125).
5. **Pre-approval.** ProductionPreapprovalRepository selects the latest candidate/core/verdict/policy graph, re-audits the core, verifies the current approval/lifecycle/binding, and returns gate_eligible only when the attestation remains current and unexpired (Pre-approval repository:173-233,510-671).
6. **Policy.** deploy_production is mandatory-approval at A4; check_authority therefore returns NEEDS_APPROVAL when eligible, DENY when disabled/too-low/invalid, and never ALLOW for this action under the current matrix (Policy matrix:52-70; Policy engine:16-37; Autonomy policy repository:84-98).
7. **Emergency control.** The current status derives the latest latch head; active state is separately exposed and gate #13 fails while active (Emergency repository:604-645; A5 evaluator:1381-1392).
8. **Hash chain.** The audit implementation computes canonical SHA-256 in one DB helper, serializes append with an advisory lock, blocks mutation, and provides an independent verifier. It is tamper-evident, not tamper-proof (Migration 0003:1-20,71-91,94-188).
9. **Staging boundary.** The only merged deploy connector is a bounded status probe, not a deploy actuator (Deploy connector:1-23,39-43; Deploy evidence service:112-163).

---

## 2. Scope and non-goals

### 2.1 In scope, contingent on OD rulings

1. A versioned Slice-55 control-loop contract through evaluate_go_live_gate only.
2. A LangGraph control-loop graph using the Slice-8 checkpointer and project_run lifecycle.
3. A common pre-node guard that enforces, in order, the Slice-54 emergency latch and Slice-7 cost STOP before every Slice-55 node.
4. Checkpoint-safe, idempotent orchestration of only already-merged internal capabilities.
5. Honest observation records for §23.3 stages whose executing capability does not exist.
6. A current A5 evaluation snapshot with exactly thirteen normalized result rows.
7. Exact binding to the current Slice-53 request/attestation, autonomy policy, and emergency latch head used by the decision.
8. A fixed positive decision status decided_not_executed only when the four pre-ruled predicates are true.
9. An append-only tamper-evident decision chain with DB-computed predecessor and entry hash.
10. Safe audit metadata for successful, blocked, refused, paused, replayed, and failed paths.
11. An additive migration inferred as 0054_control_loop_decisions after verified head 0053.
12. Pure and DB-backed tests, including direct-SQL and race cases.

### 2.2 Explicit non-goals

1. No deploy_production() call, adapter, broker action, endpoint, queue message, cloud API, or provider mutation.
2. No change to the can_go_live_autonomously literal False.
3. No change to NO_GO_LIVE_REASONS; coordinator pre-ruling 3 already selects preservation.
4. No production deployment, rollback execution, monitoring/stabilization execution, or post-launch operation.
5. No new external connector method or tool-catalog action.
6. No claimed staging deployment while only a status probe exists.
7. No new code-build, branch-write, commit, PR-write, CI-runner, PM-write, or ticket-creation connector.
8. No semantic change to any of the thirteen A5 gates or ruleset slice54.v1.
9. No new approval tier, human signature, signer, or verified organizational authority.
10. No new readiness rule; app/intake/readiness.py remains byte-stable at slice20.v1.
11. No scheduler, distributed worker, multi-process cancellation, or automatic wake-up when evidence changes.
12. No evidence-pack signing, OSCAL export, or external auditor access.
13. No HTTP surface unless OD-55-8 explicitly selects one.
14. No Slice-56 monitoring expansion or later operations work.

---

## 3. Proposed semantics

### 3.1 Bounded control-loop cycle

The recommended v1 is a resumable cycle, not an unbounded while-loop. One start/resume processes one exact current evidence view and ends in one of:

- completed_decision_recorded;
- blocked_evidence_or_authority;
- paused_cost_stop;
- paused_emergency_stop;
- failed_infrastructure;
- refused_contract_or_binding.

Repeated work is a new cycle or a checkpoint resume; there is no busy polling. This is a YAGNI interpretation of the §23.3 loop compatible with the current runtime’s explicit start/resume model (Runtime engine:109-145,180-250,386-423).

### 3.2 Proposed stage graph

Under recommended OD-55-4 Option A, the graph uses these fixed nodes:

1. read_project_state
2. inspect_existing_work_evidence
3. observe_existing_review_and_verification_evidence
4. assemble_or_reaudit_evidence_pack
5. check_cost_and_authority_limits
6. observe_staging_evidence
7. evaluate_a5_gate
8. finalize_go_live_decision

Every node begins with the same guarded boundary. The graph checkpoints after every node. No node name implies a remote action that the node did not perform.

### 3.3 §23.3 mapping without fake execution

| Spec operation | Existing merged seam | Slice-55 behavior under recommended OD-55-4 | Claim |
|---|---|---|---|
| read_project_state / inspect requirements / inspect failed tests | readiness, findings, task contracts, oracle and verdict repositories | Read current state and record bounded counts/digests | SYSTEM-READ, not remediation |
| identify skills / create or assign agents | factory, qualification, reviewer QA stores | Read current evidence; do not create a new agent unless an already-merged internal service is explicitly ruled invocable | Existing-evidence observation |
| implement_next_task | no general code-execution worker exists | Record capability_unavailable_not_executed | Never “implemented” |
| open_pull_request | connector path is evidence-oriented, not a general write actuator | Read current PR/CI evidence only | CONNECTOR-OBSERVED |
| run_ci_and_tests | CI/test-oracle evidence exists; no general CI runner is introduced | Consume current results; optionally call only already-existing in-process verifier methods if OD-55-4 permits | Existing execution/observation tiers preserved |
| specialist review / shortcut / acceptance | merged review, shortcut, acceptance stores | Consume current evidence; no new reviewer or LLM contract | Existing tiers preserved |
| update_evidence_pack | Slice-49 generation/re-audit service exists | Re-audit current pack; generation may be invoked only if its existing preconditions and OD-55-4 permit | DB-bound assembly, not readiness |
| create rework tickets | PM integration is read-only | Record capability_unavailable_not_executed | Never “ticket created” |
| check cost and authority | cost STOP, forecast, policy, pre-approval | Execute existing reads and pause/block rules | SYSTEM-DERIVED |
| deploy_staging_if_ready | status-only staging probe/rollback evidence; no deploy actuator | Observe current staging evidence only under recommended OD-55-1 | CONNECTOR-OBSERVED, not deployed |
| evaluate_go_live_gate | current A5 evaluator | Execute and persist bounded snapshot | SYSTEM-DERIVED CURRENT EVALUATION |
| deploy_production | explicitly out of scope | No node, method, endpoint, or event | NOT EXECUTED |

The unavailable diagnostic stages are non-gating because coordinator pre-ruling 1 makes the positive predicate exactly the four named conditions. They are recorded to prevent the loop from claiming it executed the entire narrative sequence.

### 3.4 Guard order at every boundary

Recommended order:

1. lock/read current project emergency state through the Slice-54 repository;
2. if active, pause the project_run through the existing emergency path and stop;
3. evaluate the existing incurred-cost STOP decision;
4. if STOP, pause through the existing cost path and stop;
5. only then enter the node;
6. record one bounded control_loop_event after the node commits.

Emergency check is first because it is the immediate safe-direction latch; either guard prevents later work. Clear never auto-resumes, inherited from Slice 54 (Emergency repository:621-645; Session guide:708-727).

### 3.5 Current evaluation and decision predicate

The plan proposes an optional as_of parameter on ProductionAutonomyRepository.evaluate and its freshness helpers, defaulting to current UTC so existing callers remain byte-for-byte equivalent in output. The Slice-55 service captures one aware UTC instant and uses it for:

- A5 freshness calculations;
- pre-approval expiry;
- decision evaluated_at;
- canonical decision digest.

The pure A5 evaluator remains unchanged. A5_RULESET_VERSION remains slice54.v1.

The decision service then requires:

- report has exactly gates 1 through 13 once each;
- every status is passed;
- report.a5_satisfied is true;
- current pre-approval coverage is gate_eligible and exposes exact request/attestation IDs;
- policy predicate matches OD-55-2;
- latest emergency head is not active;
- persisted normalized snapshot and binding digests match the in-memory result.

The service does not consult report.can_go_live_autonomously because that field is deliberately hard-false and must remain so.

### 3.6 Policy semantics

The current matrix makes deploy_production mandatory-approval. A valid A4/A5 policy therefore yields NEEDS_APPROVAL, not ALLOW (Policy matrix:52-70; Policy engine:27-37). Slice 53 already defines autonomy_eligible as exactly NEEDS_APPROVAL and separately proves a current approval (Pre-approval repository:200-216,219-233).

Recommended OD-55-2 Option A defines “policy permits” as:

    decision_for(project, "deploy_production") is NEEDS_APPROVAL
    AND current Slice-53 preapproval coverage is gate_eligible

DENY always blocks. ALLOW is treated as invalid for this mandatory-approval action because it would indicate matrix drift or corruption. This does not collapse approval into policy; it composes the two ruled conditions.

### 3.7 Binding and currentness

Recommended OD-55-6 Option A binds the evaluation/decision to:

- tenant and project;
- Slice-8 project_run and Slice-55 control_loop_run;
- exact evaluation timestamp and A5 ruleset;
- exact thirteen gate result digest;
- current frozen release candidate, evidence pack, and release verdict IDs already selected through current pre-approval;
- current pre-approval request and attestation IDs plus expiry;
- current autonomy_policy ID and canonical policy digest;
- current emergency_control_binding ID and latest emergency_stop_event ID/state;
- fixed control-loop and decision contract hashes.

Current means the serializable transaction’s evaluation snapshot. No extra wall-clock TTL is added. A later evidence row, policy update, pre-approval expiry/revocation, emergency event, contract change, or different A5 result makes the record historical and requires a new cycle. Historical decided_not_executed rows are never relabelled or deleted.

### 3.8 Transaction and race boundary

Recommended OD-55-6 Option A uses:

- SERIALIZABLE isolation for the final evaluate-and-decide transaction;
- the existing project-row lock before emergency-state evaluation;
- one captured as_of;
- a final same-transaction re-read of pre-approval, policy, and latch state;
- retry on serialization failure with the same idempotency key;
- decision insert only after all child rows exist and deferred guards can validate them.

This may prove a serializable decision snapshot. It must not claim that later evidence cannot arrive after commit. A later change de-currents the record; the future production-execution slice must re-evaluate rather than trust an old decision.

### 3.9 Hash-chain semantics

Recommended OD-55-7 Option A creates a per-project decision chain:

- global identity decision_seq for deterministic ordering;
- previous_decision_id and prev_entry_hash point to the latest prior decision for the same tenant/project;
- one DB helper canonicalizes bounded scalar fields;
- one DB finalizer acquires the project lock, derives predecessor/hash/status, and inserts;
- entry_hash is SHA-256 over decision_seq, tenant/project IDs, evaluation ID/digest, exact binding IDs/digests, status, truth-tier code, fixed scope-limit codes, created_at UTC, and prev_entry_hash;
- UPDATE, DELETE, and TRUNCATE are blocked;
- a verifier recomputes predecessor and hashes for one tenant/project chain;
- runtime receives only safe IDs/hash/status, not unrelated chain contents.

This mirrors the audit-log pattern without joining the decision chain to the global audit chain (Migration 0003:71-188). Every decision is also written to the existing audit log with safe metadata.

### 3.10 Idempotency and latest meaning

Recommended behavior:

- Idempotency key is required at the internal service boundary and stored only as sha256 digest.
- Same key plus same material binding returns the existing cycle/decision.
- Same key plus different binding raises idempotency_conflict.
- A new current evaluation or binding requires a new key and new record.
- There is no “latest pass wins” authorization. The future execution slice must ask for a current decision and re-run the predicate.
- Negative or infrastructure outcomes never fall back to an older decided_not_executed record.

---

## 4. Open decisions requiring coordinator ruling

No OD may override the three pre-rulings.

### OD-55-1 — What does “through staging deploy” mean when no deploy actuator exists?

**Option A — recommended strict honesty:** the node is observe_staging_evidence and consumes current Slice-52 staging/rollback evidence; it records staging_evidence_observed_not_deployed. The loop may still reach evaluation because the ruled positive predicate is the four conditions and gate #10 carries rollback evidence.

**Option B:** refuse every decision until a separately reviewed staging-deployment capability exists. This is maximally literal but makes Slice 55 unable to satisfy its pre-ruled output.
**Rejected as out of scope:** add a deploy connector or call a fabricated deploy action.

### OD-55-2 — What exactly means “autonomy policy permits deploy_production”?

**Option A — recommended:** current policy decision must be NEEDS_APPROVAL, not DENY, and the separate current Slice-53 pre-approval satisfies that mandatory approval. ALLOW is treated as invalid matrix drift.

**Option B:** require ALLOW. This is unreachable under the current non-relaxable mandatory-approval matrix and would make the positive path impossible.
**Option C:** accept either ALLOW or NEEDS_APPROVAL with current pre-approval. This tolerates future matrix evolution but weakens detection of a current impossible state.

### OD-55-3 — What is the exact DB-proof boundary?

**Option A — recommended:** Python remains canonical for individual gate semantics; DB proves a complete immutable thirteen-row evaluation snapshot and independently proves the final relational decision predicate/bindings/hash chain. Documentation says DB-PROVEN DECISION GRAPH, not DB-recomputed A5.

**Option B:** port all thirteen gate ladders into SQL and make the DB evaluator canonical. This provides stronger DB derivation but forks a large security-critical engine and creates drift risk.
**Option C:** persist one app-computed boolean/digest without normalized rows. Rejected as too weak for the pre-ruling.

### OD-55-4 — Which existing capabilities may the loop actively invoke?

**Option A — recommended minimal v1:** actively invoke only local, already-merged deterministic/re-audit services; consume connector-backed evidence without refreshing it. Record unavailable operations honestly. No connector protocol or tool action changes.

**Option B:** allow the loop to invoke existing read-only connector services with their existing broker policies and injected adapters; CI remains fake-only. This adds live network orchestration but no new connector actions.
**Option C:** observation-only loop: read all stores and invoke nothing except A5 evaluation/finalization. Safest, but thinner than §23.3 orchestration.

The ruling must list exact invocable service functions; “any existing capability” is too broad.

### OD-55-5 — How are non-positive cycles retained?

**Option A — recommended:** every cycle/event is append-only; only a positive predicate produces go_live_decisions. Blocked/refused/failed outcomes remain in control_loop_events and the audit log.

**Option B:** hash-chain every outcome in go_live_decisions with multiple statuses. This broadens “decision record” beyond the pre-ruled fixed positive status.
**Option C:** retain only audit events for negative paths. Rejected because crash/resume and reviewer evidence need structured cycle history.

### OD-55-6 — What currentness, transaction, and staleness rule applies?

**Option A — recommended:** one SERIALIZABLE snapshot, project lock, injected UTC as_of, final same-transaction re-read, content/binding currentness, no extra TTL. Later change requires a new cycle.

**Option B:** READ COMMITTED plus double-read. Simpler but leaves a smaller race window between final read and commit.
**Option C:** require every existing evidence writer to share a new project advisory lock. Stronger serialization but far beyond this slice and risks changing every evidence subsystem.

### OD-55-7 — What chain topology and verifier ship?

**Option A — recommended:** per-project chain with global ordering identity, DB-computed predecessor/hash, append-only guards, and an admin verifier; safe tenant-scoped latest read.

**Option B:** one global chain like audit_logs. Simpler ordering but creates unnecessary global contention and cross-tenant operational coupling.
**Option C:** rely only on the existing audit chain. Rejected because the pre-ruling explicitly requires the go-live decision record itself to be hash-chained.

### OD-55-8 — What API surface exists?

**Option A — recommended:** internal service/repository methods only; tests and future scheduler/control-plane integration call them inside tenant_scope. No HTTP in this slice.

**Option B:** bodyless bearer-authenticated start/resume/current endpoints with Idempotency-Key on mutations and safe status-only responses, following Slices 53–54. This requires an explicit actor/authority ruling even though no production action executes.
**Option C:** read-only latest-decision endpoint only; starts remain internal.

### OD-55-9 — Contracts, caps, audit, downgrade, and preservation

**Recommended ruling:**

- slice55.control_loop.v1;
- slice55.go_live_evaluation.v1;
- slice55.go_live_decision.v1;
- slice55.go_live_decision_chain.v1;
- exactly 13 gate rows numbered 1–13;
- at most 64 stage events per cycle and 10,000 cycles per project query page boundary, with no unbounded list API;
- stage/status/reason/truth-tier/scope-limit codes non-blank and ≤128 bytes;
- idempotency digest and all contract/binding/context digests canonical sha256;
- no raw A5 context JSON, policy JSON, principal subject/hash, target/repo/commit/version label, URL, host, prompt, response, log, test output, document, AC, oracle, finding, issue, or secret in Slice-55 tables/audit/errors;
- caller-supplied passed, eligible, current, approved, policy_permits, latch_active, decision_status, executed, can_go_live, prev_hash, entry_hash, or chain_seq fields fail closed;
- expected migration 0054 is additive; downgrade to 0053 fails closed while Slice-55 rows exist;
- findings-guard MD5 remains pinned; readiness, A5 pure evaluator, A5 ruleset, NO_GO_LIVE_REASONS, policy matrix/engine, templates, and can_go_live_autonomously literal remain unchanged.

---

## 5. Proposed pure modules and interfaces

### 5.1 app/release/go_live_decision.py

Proposed responsibility: pure contracts and canonicalization only.

Proposed symbols:

- CONTROL_LOOP_CONTRACT_VERSION
- GO_LIVE_EVALUATION_CONTRACT_VERSION
- GO_LIVE_DECISION_CONTRACT_VERSION
- GO_LIVE_CHAIN_CONTRACT_VERSION
- DECISION_STATUS = decided_not_executed
- AUTHORITY_TRUTH_TIER = request_authenticated_key_custody_under_recorded_policy_not_human_signature
- SCOPE_LIMITATION_CODES
- GateSnapshot
- DecisionInputs
- DecisionOutcome
- decision_eligible(inputs) -> bool
- canonical_gate_digest(gates) -> sha256
- canonical_binding_digest(inputs) -> sha256
- validate_exact_gate_set(gates)
- reject_caller_truth_fields(payload)

The pure function returns eligible only for the exact four pre-ruled conditions. It never returns deploy, execute, authorize_production, or can_go_live.

### 5.2 app/runtime/control_loop.py

Proposed responsibility: build and run the checkpointed graph, with no connector definitions.

Proposed symbols:

- CONTROL_LOOP_NODES fixed tuple;
- ControlLoopState TypedDict carrying IDs, stage code, bounded outcome codes, and digests only;
- guarded_control_loop_node;
- build_control_loop_graph;
- start_control_loop;
- resume_control_loop.

Every node:

1. enforces emergency boundary;
2. evaluates cost STOP;
3. performs only the ruled existing operation;
4. appends a bounded event;
5. checkpoints before the next node.

The graph ends after finalize_go_live_decision. There is no production node and no conditional edge to one.

### 5.3 app/repositories/go_live_decisions.py

Proposed responsibility: tenant-scoped reads, exact current source selection, snapshot persistence, finalization, chain reads, and safe audit calls.

Proposed interfaces:

- start_cycle(project_id, project_run_id, idempotency_key)
- append_event(control_loop_run_id, stage_code, outcome_code, refs)
- record_current_evaluation(control_loop_run_id, as_of)
- finalize_decision(control_loop_run_id, evaluation_id, idempotency_key)
- current_decision(project_id, as_of)
- verify_project_chain_admin(project_id)

finalize_decision accepts IDs and idempotency only. It does not accept status, booleans, hashes, actor labels, policy outcomes, or latch state from the caller.

### 5.4 app/models/go_live_decision.py

Proposed responsibility: ORM mappings only for the five new tables in §6.

### 5.5 Narrow modifications

- app/repositories/production_autonomy.py — optional injected as_of and a safe snapshot helper; default callers retain current behavior.
- app/repositories/runs.py — control-loop blocked wrapper, using the existing state machine.
- app/models/run_step.py — one additive control_loop_waiting event type if OD-55-5 Option A.
- app/models/__init__.py — model registration.
- app/main.py and app/api/control_loop.py only if OD-55-8 chooses an HTTP option.

The pure app/release/production_autonomy.py file should remain byte-stable under the recommended plan.

---

## 6. Additive storage and expected migration 0054

Migration number/name is an inference from verified head 0053. Final filename proposed: migrations/versions/0054_control_loop_decisions.py.

All new tables are tenant-owned, RLS ENABLE+FORCE, protected by the existing tenant_isolation policy, same-tenant/project composite FKs, append-only guards, no DELETE/TRUNCATE, and runtime grants limited to the ruled path. Existing rows are never backfilled or relabelled.

### 6.1 control_loop_runs

Immutable cycle header:

- id UUID primary key;
- tenant_id, project_id;
- project_run_id composite-FK pinned to the same tenant/project;
- idempotency_digest;
- control_loop_contract_version/hash;
- created_at;
- UNIQUE tenant/project/idempotency_digest;
- UNIQUE id/project/tenant for downstream composite FKs.

No mutable status column. Current state derives from the latest event.

### 6.2 control_loop_events

Append-only linear cycle history:

- id;
- tenant_id, project_id, control_loop_run_id;
- ordinal;
- previous_event_id;
- stage_code;
- outcome_code;
- evidence_reference_digest nullable;
- created_at;
- unique run+ordinal;
- unique previous_event_id to prevent forks;
- deferred guard for genesis/linearity and allowed transitions.

No raw state payload or external output.

### 6.3 go_live_evaluations

Immutable evaluation header:

- id;
- tenant_id, project_id, control_loop_run_id;
- evaluated_at;
- A5 ruleset_version fixed to slice54.v1;
- evaluation_contract_version/hash;
- gate_result_digest;
- passed_gate_count generated/re-derived;
- all_gates_passed generated/re-derived;
- exact current candidate/core/verdict IDs where present through the pre-approval graph;
- created_at;
- one evaluation per finalized cycle attempt under recommended OD-55-5.

The DB guard requires exactly thirteen children numbered 1–13 before a successful finalization.

### 6.4 go_live_evaluation_gate_results

Exactly thirteen immutable rows:

- id;
- tenant_id, project_id, evaluation_id;
- gate_number;
- gate_name_code;
- status;
- reason_code;
- safe_context_digest;
- ordinal;
- created_at;
- unique evaluation+gate_number and evaluation+ordinal.

Only the three existing A5 statuses are accepted. Raw context is never persisted. The deferred guard recomputes count, ordering, passed count, and gate_result_digest.

### 6.5 go_live_decisions

The positive, append-only, hash-chained record:

- id;
- decision_seq BIGINT identity always;
- tenant_id, project_id;
- control_loop_run_id and evaluation_id;
- preapproval_request_id and preapproval_attestation_id;
- autonomy_policy_id and autonomy_policy_digest;
- emergency_control_binding_id and emergency_stop_event_id;
- release_candidate_id, evidence_pack_id, release_verdict_id;
- evaluation_digest and decision_binding_digest;
- status fixed to decided_not_executed;
- authority_truth_tier fixed to request_authenticated_key_custody_under_recorded_policy_not_human_signature;
- production_action_executed fixed false;
- can_go_live_autonomously_snapshot fixed false;
- scope_limitation_digest over the fixed code list;
- previous_decision_id and prev_entry_hash;
- entry_hash;
- created_at;
- unique evaluation_id;
- unique previous_decision_id to prevent forks;
- unique entry_hash.

The finalizer derives status, booleans, predecessor, and hashes. The caller cannot provide them.

### 6.6 DB functions and triggers

Recommended functions:

- go_live_decision_entry_hash(...) — one canonical DB hash helper;
- go_live_decision_finalize(control_loop_run_id, evaluation_id, idempotency_digest) — SECURITY DEFINER with narrow search_path and no caller truth fields;
- go_live_decision_verify(project_id) — admin-only chain verifier;
- block_control_loop_mutation() — shared UPDATE/DELETE/TRUNCATE refusal;
- deferred control_loop_graph_guard() — event/evaluation/decision completeness and exact binding checks.

The finalizer must:

1. derive tenant from app.current_tenant;
2. lock the exact project row;
3. load the exact evaluation and thirteen children;
4. require all thirteen passed;
5. load and recheck current Slice-53 coverage/reference graph;
6. derive the policy result under OD-55-2;
7. require latest emergency head not active;
8. require current binding digests;
9. compute predecessor and entry hash;
10. insert decided_not_executed;
11. append safe audit metadata.

The function cannot independently call the Python evaluator; OD-55-3 defines the honest proof boundary.

### 6.7 Existing-object changes

Under recommended options:

- add control_loop_waiting to the run_steps event-type CHECK;
- no new project_run status;
- no change to the emergency active-latch trigger except regression tests;
- no new composite identity targets are expected because project_runs, release candidates, evidence packs, verdicts, pre-approval records, autonomy policies, and emergency-control rows already expose same-project/tenant unique identities (model sources cited in §1.3; catalog rechecked during implementation).

### 6.8 Downgrade

0054→0053 must:

- refuse while any Slice-55 row exists;
- remove only the Slice-55 event-type extension after the row check;
- drop Slice-55 functions/triggers/tables in dependency order;
- restore the exact pre-0054 run_steps CHECK;
- leave migration 0053, emergency guards, all evidence stores, the A5 evaluator, audit chain, readiness, and findings guard untouched.

---

## 7. Workflow behavior

### 7.1 Start

1. Require an existing same-project project_run in created state.
2. Enforce emergency boundary.
3. Mark running through RunRepository.
4. Insert immutable control_loop_run using idempotency digest.
5. Start the LangGraph with UAIDCheckpointer.
6. Execute until the next checkpoint or a guard outcome.

No external action is implied by starting the loop.

### 7.2 Resume

1. Require paused or blocked run.
2. Enforce emergency boundary; active remains paused.
3. Re-evaluate cost STOP; active STOP remains paused.
4. Mark resumed only after both guards clear.
5. Resume from the stored checkpoint without replaying completed nodes.
6. Re-read current evidence at the nodes that depend on currentness.

Clear of an emergency latch never auto-calls resume.

### 7.3 Evidence not ready

If any A5 gate fails, pre-approval is absent/stale, policy is DENY/ineligible, or the ruled predicate is otherwise false:

- no go_live_decisions row;
- append a bounded event with the first ordered blocking code plus failed-gate count;
- transition the project_run to blocked through a Slice-55-specific event;
- audit counts/codes only;
- never fall back to an older positive record.

### 7.4 Cost STOP

The existing incurred-cost STOP remains separate from gate #9’s forecast. STOP pauses before the next node, writes the existing cost_paused run event, and produces no decision. The control loop never changes budgets, clears STOP, or resumes itself (Runtime engine:386-423).

### 7.5 Emergency stop

An active latch pauses through the existing emergency path and raises before the node. Even if the A5 snapshot immediately before activation had all gates passed, no finalization may occur while the latest head is active. The shared project lock and final re-read are mandatory race tests (Emergency repository:79-121,621-645).

### 7.6 Positive decision

When and only when the four pre-ruled conditions are true:

- finalize one hash-chained row;
- status = decided_not_executed;
- production_action_executed = false;
- can_go_live_autonomously_snapshot = false;
- append control_loop decision_recorded event;
- mark the local project_run completed;
- return safe decision ID, status, entry hash, and created_at.

There is no next graph edge to production.

### 7.7 Audit surface

Allowed audit fields:

- project_id;
- control_loop_run_id;
- project_run_id;
- evaluation_id;
- decision_id;
- stage_code;
- outcome/reason code;
- passed_gate_count;
- predicate booleans without identities;
- contract versions;
- decision status;
- production_action_executed=false;
- entry_hash if the existing audit policy permits a decision digest.

Forbidden:

- principal subject or subject hash;
- policy/checklist/override content;
- raw gate contexts;
- release_ref, repo, branch, commit, target, URL, host, version label;
- evidence prose, tests, logs, findings, issues, prompts, responses, credentials, secrets;
- exception strings from external libraries.

---

## 8. A5 and hard-false preservation

### 8.1 A5 evaluator

- A5_RULESET_VERSION remains slice54.v1.
- Gate names, ladders, reasons, contexts, and ordering remain identical for identical inputs.
- ProductionAutonomyReport.a5_satisfied may be true when all thirteen gates pass.
- ProductionAutonomyReport.to_dict continues to serialize can_go_live_autonomously as literal False.
- NO_GO_LIVE_REASONS remains exactly ("a5_gates_not_all_satisfied",).
- The Slice-55 decision record is not a fourteenth A5 gate and is not fed back into the A5 evaluator.

Sources: coordinator pre-rulings 1 and 3; A5 evaluator:71-125.

### 8.2 Required synthetic matrix

Tests must include:

| A5 all pass | Pre-approval current | Policy permits | Latch active | Decision row | can_go_live_autonomously |
|---:|---:|---:|---:|---|---:|
| false | true | true | false | none | false |
| true | false | true | false | none | false |
| true | true | false | false | none | false |
| true | true | true | true | none | false |
| true | true | true | false | decided_not_executed | false |

Every single-gate-negative permutation must refuse the decision. The synthetic all-pass row proves coexistence of a5_satisfied=true and can_go_live_autonomously=false.

---

## 9. API surface

### 9.1 Recommended OD-55-8 Option A

No HTTP route. The internal service runs only inside an established tenant_scope with an explicit project_run. This avoids inventing who may start a consequential control cycle before production execution authority is separately designed.

### 9.2 If the coordinator selects an HTTP option

The plan must be amended before implementation to bind:

- exact request-authenticated actor types and policy membership;
- bodyless request shape;
- Idempotency-Key requirement;
- generic 404/409 behavior with no cross-tenant oracle;
- safe response fields only;
- rate/size limits;
- OpenAPI tests;
- explicit statement that starting or reading a decision does not authorize production.

No route may accept release IDs, policy outcomes, gate results, latch state, decision status, hashes, or any truth field from the body.

---

## 10. Test-first implementation plan

No test is created by this task. After plan approval and all ODs are ruled, implementation must proceed TDD.

### 10.1 Pure tests — proposed tests/test_control_loop.py

1. Exact contract versions and fixed status vocabulary.
2. decision_eligible truth table for all four pre-ruled predicates.
3. All 13 gate numbers required once; missing, duplicate, reordered, unknown, or non-passed row refuses.
4. One failed gate among thirteen refuses for each gate number.
5. NEEDS_APPROVAL + current pre-approval policy interpretation under OD-55-2.
6. DENY refuses; impossible ALLOW handling follows the ruling.
7. Caller truth-field rejection recursively.
8. Canonical gate/binding digests deterministic under key-order variation and sensitive to material change.
9. Bounds and non-blank code validation.
10. Scope-limit set contains production_not_executed and key_custody_not_human_signature.
11. No pure result exposes deploy/execute/can_go_live true.
12. Stage map labels unavailable and staging-observed operations honestly.

### 10.2 Runtime tests

1. Graph contains exactly the ruled nodes and no production node/edge.
2. Every node calls emergency guard before cost guard and before node body.
3. Cost STOP pauses before each node; the node body is not called.
4. Active emergency latch pauses before each node; the node body is not called.
5. Checkpoint crash/resume does not replay a completed stage.
6. Blocked evidence resumes from the correct checkpoint after new evidence.
7. Clear never auto-resumes.
8. Existing capability adapter invocation is restricted to the OD-55-4 allowlist.
9. A sentinel connector proves no new or unruled network method is called.
10. Staging node never calls a deploy method and records the ruled observation code.
11. Positive cycle ends after decision finalization.
12. Infrastructure exception records safe code and fails the run without leaking exception text.

### 10.3 Repository/service tests

1. Positive exact graph records one decided_not_executed row.
2. Each false predicate produces no decision row and a structured negative event.
3. Same idempotency key/material returns existing result.
4. Same key/different material conflicts.
5. Later evidence/policy/pre-approval/latch change makes old decision non-current.
6. No older positive fallback after a newer blocked/refused cycle.
7. as_of expiry boundary for Slice-53 pre-approval.
8. Policy override disable/level change refuses.
9. Active-latch race between evaluation and finalize refuses/serializes.
10. Pre-approval revoke/expiry race refuses/serializes.
11. Evidence change during serializable transaction produces retry or a serially ordered historical decision, never mixed input.
12. Audit sentinel covers success, blocked, paused-cost, paused-emergency, malformed, replay, conflict, and exception paths.

### 10.4 DB-backed and direct-SQL adversarial tests

1. RLS ENABLE+FORCE and deny-by-default cross-tenant behavior on all tables.
2. Same-tenant/project composite FKs reject cross-project run/evaluation/preapproval/policy/emergency bindings.
3. UPDATE/DELETE/TRUNCATE rejected on every new table.
4. Direct insert with decided_not_executed but one failed/missing/duplicate gate row rejected at commit.
5. Direct insert with stale/expired/revoked pre-approval rejected.
6. Direct insert with policy DENY or forged policy_permits rejected.
7. Direct insert while latest latch active rejected.
8. Direct insert with caller production_action_executed=true or can_go_live=true rejected.
9. Caller-supplied status, chain_seq, prev hash, or entry hash rejected/overwritten only by the finalizer.
10. Chain genesis, continuation, recomputation, and verifier success.
11. Chain fork, skipped predecessor, copied hash, changed material, cross-project predecessor, and reordered seq rejected/detected.
12. Concurrent two-finalizer test yields one linear order with no fork.
13. Negative cycle has no decision row under OD-55-5 Option A.
14. Deferred child-set and digest attacks rejected at commit.
15. Runtime role cannot bypass the narrow finalizer with direct table truth writes.
16. Audit contains no principal hash, policy JSON, target/repo/commit data, raw context, exception string, or sentinel secret.
17. Existing audit chain still verifies.
18. release_findings_guard() MD5 remains 808036faf2660d6810aeca4342e6f1ac before/after upgrade, downgrade, and re-upgrade.
19. Migration 0053→0054→0053→0054; downgrade with live Slice-55 rows fails closed.
20. Catalog grants, constraints, indexes, functions, ownership, and search_path are exact.

### 10.5 Golden regression tests

1. app/release/production_autonomy.py byte-stable.
2. A5 outputs before==after for the existing golden matrix.
3. ruleset remains slice54.v1.
4. gates #1–#13 identical for identical inputs.
5. NO_GO_LIVE_REASONS exact tuple unchanged.
6. can_go_live_autonomously literal False under baseline, partial, all-pass, decision-recorded, and stale-decision states.
7. app/intake/readiness.py byte-stable at slice20.v1.
8. app/policy/matrix.py and app/policy/engine.py byte-stable unless OD-55-2 explicitly rules otherwise.
9. Slice-8b, Slice-49/50, Slice-52, Slice-53, and Slice-54 focused suites remain green unchanged.

### 10.6 Required eventual pre-PR verification

Only after plan approval, bound OD rulings, and implementation:

    git diff --check
    uv run ruff check .
    make test
    RLS_DB_PASSWORD=... make test-db
    migration 0053 -> 0054 -> 0053 -> 0054

Every command requires complete captured output and exit code. A truncated run is failed verification.

---

## 11. Prospective file-touch map

### New only after approval and rulings

- app/release/go_live_decision.py
- app/runtime/control_loop.py
- app/repositories/go_live_decisions.py
- app/models/go_live_decision.py
- migrations/versions/0054_control_loop_decisions.py
- tests/test_control_loop.py
- app/api/control_loop.py only if OD-55-8 selects HTTP

### Modified narrowly

- app/models/__init__.py — register new models.
- app/repositories/production_autonomy.py — inject one as_of and expose safe snapshot data without semantic change.
- app/repositories/runs.py — Slice-55 blocked wrapper only.
- app/models/run_step.py — control_loop_waiting event only.
- app/main.py — router registration only if OD-55-8 selects HTTP.

### Byte-stable / semantically untouched

- app/release/production_autonomy.py
- app/intake/readiness.py
- app/identity.py
- app/policy/matrix.py and app/policy/engine.py under recommended OD-55-2
- app/release/production_approval.py and Slice-53 DB guards
- app/release/emergency_stop.py and Slice-54 DB/runtime guards
- app/release/deploy_connector.py and all connector protocols
- app/tools catalog and broker policy
- templates and schemas
- all thirteen gate semantics and A5 ruleset slice54.v1
- NO_GO_LIVE_REASONS
- can_go_live_autonomously literal False
- release_findings_guard()

---

## 12. Must NOT claim

1. Must NOT claim Slice 55 implements the entire §23.3 pseudocode; it stops after go-live gate evaluation by pre-ruling.
2. Must NOT implement or call deploy_production().
3. Must NOT change, derive, shadow, or bypass can_go_live_autonomously = False.
4. Must NOT change NO_GO_LIVE_REASONS without a new explicit coordinator ruling; this draft proposes no change.
5. Must NOT call decided_not_executed a deployment, release, go-live event, production authorization, or permission to execute later.
6. Must NOT claim all thirteen PASS-capable gates currently pass for any project.
7. Must NOT claim a5_satisfied alone authorizes production.
8. Must NOT call request_authenticated a human signature, human-presence proof, verified human approval, organizational authority, or signer attestation.
9. Must NOT call caller-supplied structured policy verified policy authority.
10. Must NOT claim the DB independently re-executed all thirteen Python gate algorithms under recommended OD-55-3.
11. Must NOT call the decision chain tamper-proof against a DB superuser.
12. Must NOT add a fourteenth A5 gate or advance A5_RULESET_VERSION.
13. Must NOT create a new external connector method, tool action, cloud call, deployment adapter, PR writer, CI runner, PM writer, or ticket writer.
14. Must NOT claim the current status-only staging probe deployed staging.
15. Must NOT claim connector-observed evidence is system-executed by UAID.
16. Must NOT silently skip missing §23.3 execution capabilities and then describe them as completed.
17. Must NOT let a negative/newer cycle fall back to an older decision.
18. Must NOT trust caller-supplied gate results, approval/currentness, policy permission, latch state, decision status, chain pointers, hashes, executed flags, or go-live booleans.
19. Must NOT persist or audit raw gate contexts, principal identities/hashes, policy contents, target/repo/commit/version data, tenant prose, logs, prompts, responses, credentials, or secrets.
20. Must NOT run a node before emergency and cost guards.
21. Must NOT auto-clear a latch, auto-resume a paused/blocked run, alter a budget, or bypass the Slice-8 state machine.
22. Must NOT weaken Slice-23/44/45 findings guards, Slice-49/50 evidence/verdict guards, Slice-52 rollback guards, Slice-53 pre-approval guards, or Slice-54 emergency guards.
23. Must NOT change readiness.
24. Must NOT add a wall-clock TTL not grounded in an existing source; underlying evidence and pre-approval freshness remain authoritative.
25. Must NOT claim the control loop is distributed, scheduled, continuously polling, or production-operational.
26. Must NOT start the future production-execution slice, Slice 56, or any post-launch operations work.
27. Must NOT begin implementation until the reviewer returns APPROVE and every OD-55-1…9 is ruled and bound into this plan.

---

## 13. Definition of done for future implementation — not this task

Future implementation is complete only when:

- this plan is independently approved;
- all OD-55-1…9 rulings are recorded verbatim before code;
- a feature branch is created only after those gates;
- plan binding is an atomic first commit;
- the graph ends at decision finalization and has no production edge;
- every node is checkpointed and guarded by emergency plus cost;
- only ruled existing capabilities are invoked;
- the positive record exists exactly under the four pre-ruled conditions;
- direct SQL cannot forge the decision graph or chain;
- history is append-only and chain verification passes;
- request-authenticated authority remains labelled key custody, not human signature;
- A5 ruleset, gates, no-go tuple, literal False, readiness, policy engine, connectors, and layered guards are preserved;
- pure and DB suites pass with complete captured outputs and exit codes;
- migration round-trip and fresh-DB verification pass;
- audit/error sentinels are clean;
- .env and .planning/.pending-auth-captures.jsonl are never staged;
- a PR is opened but not merged pending independent APPROVE/REJECT.

---

## 14. Muhasabah self-audit

Completed before submission:

- **Provenance:** source claims are tied to the spec, roadmap, current source files, migrations, or verified git commands.
- **Pre-ruling fidelity:** all three coordinator rulings are recorded verbatim and drive the split, predicate, execution boundary, identity wording, no-go tuple, and literal-False constraints.
- **Brainstorming alternatives:** the staging gap, policy semantics, DB-proof boundary, invocation breadth, negative-history shape, transaction/currentness, chain topology, API surface, and contract/cap choices are exposed as OD-55-1…9 with trade-offs.
- **No fabrication:** the plan does not invent staging or production deployment, a human-signature tier, new connector actions, a DB-native thirteen-gate evaluator, or go-live reachability.
- **Scope:** the atomic plan-binding commit precedes implementation; all later work remains limited to the ruled Slice-55 feature branch and must stop at a review-only PR.
- **Safety:** the graph stops after a non-executing decision; emergency and cost guards precede every node; negative/currentness races fail closed; direct-SQL, chain, audit, and downgrade attacks are planned.
- **Residual uncertainty:** none within Slice-55 scope; OD-55-1…9 are now ruled and bound above. Any scope expansion requires a new plan and coordinator ruling.

Result: PASS for plan binding; implementation remains subject to the verification requirements in §10.6 and §13.

---

## 15. Reviewer gate

Reviewer must return exactly APPROVE or REJECT.

APPROVE requires:

- all three coordinator pre-rulings are present verbatim;
- the plan ends before production execution;
- decided_not_executed has exactly the four-condition predicate;
- staging, policy, identity, and DB-proof gaps are honest;
- ODs are complete enough for final coordinator rulings;
- storage/chain/race/direct-SQL plans are implementable without weakening existing gates;
- no factual claim lacks a source or an inference/assumption label;
- only this planning file changed.

REJECT must identify exact section/line, violated ruling/source, and required correction.

Plan APPROVE and coordinator rulings OD-55-1…9 are now recorded above. Implementation may begin on the ruled feature branch; review remains required before merge.
