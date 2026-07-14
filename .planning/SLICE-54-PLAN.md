# Slice 54 Plan — Emergency stop / rollback authority (A5 gate #13)

**Status:** APPROVED FOR EXECUTION — v1 approved; OD-54-1…10 ruled and bound (see Rulings section)

**Task boundary:** This file is the only deliverable. No branch, code, migration, test, commit, or PR is part of this task.

---

## Coordinator rulings (final)

Slice 54 PLAN v1 was APPROVED by the independent reviewer (who independently confirmed the Appendix-C wording correction — "Production overrides require explicit authority," no mechanism mandate — and endorsed the hybrid resolution). All ten open decisions are now ruled as follows. These are final and binding:

- **OD-54-1 = Option A (hybrid):** a real DB-backed project latch executed and enforced over the existing UAID runtime (all eight entry points, every node boundary, plus the DB trigger refusing running while active), together with DB-bound exact rollback authority over the Slice-52 path. Gate #13 may pass with the honestly-scoped reason; it is explicitly accepted that this is not production incident execution — the five fixed scope-limitation codes carry that boundary permanently.
- **OD-54-2 = Option A:** reuse the exact current Slice-53 policy snapshot and production_approval_policy_approvers set; invokers must be exact request-authenticated members with actor_type=human metadata; digests only; provenance stays caller-supplied structured policy + key custody; app/policy/matrix.py and app/policy/engine.py byte-stable — any future executing production rollback needs its own separately reviewed matrix/broker policy.
- **OD-54-3 = Option A (split scope):** the stop latch is a standing project capability; the rollback-authority half is bound to the current frozen candidate + re-audited core + current gate-eligible Slice-52 run; gate #13 requires both halves current; stale release evidence never disables the standing stop.
- **OD-54-4 = Option A:** any current member may activate (no separation from Slice-53 roles — activation is safe-direction); clear requires a distinct second current member; gate-bearing bindings therefore require ≥2 members; any current member may record the non-executing rollback authorization. The two-person clear rule is recorded as a chosen security posture.
- **OD-54-5 = Option A:** rollback authority creates an immutable exact release/core/rollback-run-bound authorization event with result_code=authorized_not_executed; no connector, broker, deploy, or cloud call; gate #13 requires the capability binding, never an emergency occurrence.
- **OD-54-6 = Option A:** append-only linear latch chain (armed_anchor → activated → cleared → …) with unique-previous-event linearity; the shared exact project-row transaction lock across configure/activate/clear/runtime boundaries; activation pauses eligible running runs atomically with exact per-run effects; clear never auto-resumes; rebind never resets state; no TTL. The race guarantee is the post-commit step-boundary one — in-flight preemption is never claimed.
- **OD-54-7 = Option A:** the five bodyless bearer-authenticated endpoints with Idempotency-Key on mutations, identity only from TenantContext.actor, all bindings derived server-side, generic 404/409, no cross-tenant oracle.
- **OD-54-8 = Option A:** the five normalized append-only tables with generated row-local truth and deferred graph triggers (member-set equality to the Slice-53 policy, event-chain linearity, activation-effect completeness proving no running row remains at commit); the two additive runtime-object extensions only — run_steps gains emergency_paused and project_runs gains the active-latch guard — with the exact pre-0053 state restored on downgrade.
- **OD-54-9 = Option A:** the 14-rung ladder exactly as plan §8.1 including rung 13 (emergency_stop_active blocks); pass reason passed:request_authenticated_runtime_stop_and_release_bound_rollback_authority; ruleset slice54.v1 — gate #13 becomes the thirteenth and final PASS-capable gate; gates #1–12 byte-identical under the golden matrix; the literal False and single-reason tuple byte-identical, proven again by the synthetic all-13-pass matrix row.
- **OD-54-10 = Option A:** the three contract versions; canonical digests; ≤100 members; the stated bounds; no run-count cap on the safety stop (set-wise handling of the finite nonterminal inventory); the forbidden-content lists everywhere including the role-code-only audit actor; caller truth fields fail closed; downgrade 0053→0052 fails closed with live rows; findings-guard MD5 pinned across the round trip.

Three consequences are explicitly accepted: the gate-#13 pass rests on the current-local-runtime latch (the strongest honest lever that exists); gate-bearing bindings need ≥2 policy members; and the first additive touches to Slice-8 runtime objects land with exact downgrade restoration.

---

## Sanad / citation key

- **Spec** — docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md.
- **Roadmap** — .planning/GO-LIVE-END-TO-END-ROADMAP.md.
- **Session guide** — CLAUDE.md.
- **Approval policy template** — docs/UAID_OS_Intake_Template_Pack_v1_2/20_human_approval_policy.yaml.
- **Go-live template** — docs/UAID_OS_Intake_Template_Pack_v1_2/23_go_live_checklist.yaml.
- **Runtime engine/repository/models** — app/runtime/engine.py; app/repositories/runs.py; app/models/project_run.py; app/models/run_step.py; migrations/versions/0009_workflow_runtime.py; migrations/versions/0010_runtime_events.py.
- **Identity/authority sources** — app/identity.py; app/release/production_approval.py; app/release/production_approval_service.py; app/repositories/production_preapprovals.py; app/models/production_preapproval.py; app/api/production_preapprovals.py.
- **Rollback sources** — app/release/rollback.py; app/repositories/rollback_verifications.py; app/models/rollback_verification.py.
- **Failure-policy precedent** — app/agents/failure_policy.py; .planning/SLICE-41-PLAN.md.
- **A5 evaluator** — app/release/production_autonomy.py; app/repositories/production_autonomy.py.

Line citations are to the checked-out main tree at the verified baseline in §1.1. Git-state claims cite the exact commands used rather than prior conversation summaries.

---

## 0. Honesty crux

### 0.1 The exact problem

Appendix B gate #13 requires that “emergency stop/rollback authority exists” (Spec:2981-2997). This plan’s recommended **conservative inference** is that the sentence requires more than an authority label with no operative mechanism; the sentence does not say that UAID must execute a production rollback. Section 25.2 separately says production rollback requires approval or a pre-approved emergency rollback policy (Spec:2377-2389). Section 18.2 says emergency rollback produces an immediate alert and may auto-rollback only if policy permits (Spec:1760-1770).

Appendix C is narrower than the roadmap paraphrase. Its exact final rule is “Production overrides require explicit authority” (Spec:2999-3016). It does **not** literally say “implement an emergency-stop mechanism.” Therefore:

- Appendix B #13 is the direct source for the stop/rollback-authority gate.
- Section 25.2 is the direct source for production-rollback approval or policy.
- Appendix C supplies the explicit-authority constraint on production overrides.
- The roadmap’s “mechanism + bound authority per App. C” wording is a directional synthesis, not a verbatim Appendix-C requirement (Roadmap:531-540).

This source drift must remain visible in code comments, plan rationale, and review. It must not be silently rewritten into a stronger quotation.

### 0.2 The narrow claim proposed for Slice 54

Subject to OD-54-1 and OD-54-9, the recommended design may claim only:

> UAID executed a project-scoped emergency latch against its **current local workflow runtime**, enforced the latch at DB and runtime step boundaries, and DB-bound the principals permitted to activate/clear that latch and to record an exact release-scoped rollback authorization. Those principals are request-authenticated key holders under a recorded policy. The rollback path itself remains the connector-observed staging A→B→A path from Slice 52; no production rollback is executed.

This is deliberately narrower than “production incident response works.” The existing runtime is a local durable/demo workflow substrate and the existing rollback subsystem observes a remote staging drill; neither is a production deployment actuator (Runtime engine:1-28; Rollback contract:1-5; Rollback repository:105-217; Session guide:668-706).

### 0.3 Truth tiers

| Tier | Slice-54 example | What it may prove | What it must not be called |
|---|---|---|---|
| **REPORTED / caller-supplied structured policy** | Template-20 policy values and declared approver subjects | What the project’s recorded policy says | Verified organizational authority, human identity, or consent |
| **REQUEST-AUTHENTICATED** | TenantContext.actor stamps a principal derived from an active bearer key | Key custody for the request-bound principal | Human signature, human presence, on-call status, or signer assurance |
| **DB-PROVEN** | Same-tenant/project FKs, exact policy membership, immutable event order, release/rollback binding, active-latch state, run status transition | Relational facts held by the DB graph | Cryptographic bearer possession outside the request boundary, or real-world authority |
| **SYSTEM-EXECUTED-RUNTIME-STOP** | UAID sets the local project latch and changes an eligible current project_run from running to paused | The current UAID runtime honored the stop at a ruled boundary | OS process kill, distributed-worker cancellation, external tool cancellation, or production stop |
| **CONNECTOR-OBSERVED-STAGING** | Slice-52 exact A→B→A artifact and staging probe | One bounded staging drill was observed | UAID-executed rollback or future production rollback success |
| **SYSTEM-DERIVED** | Binding digests, currentness, latch state, authority membership, gate eligibility | Deterministic result under named contracts | Completeness of incident response or future operational success |
| **GATE-INFERRED** | Gate #13 passes under a ruled limited-scope contract | The ruled gate evidence is present and current | A5 authorization, deployment permission, or go-live |

The identity boundary is inherited, not upgraded: request_authenticated proves active-key possession bound to a principal and “never authorizes go-live” (app/identity.py:1-12). Slice 53 likewise describes policy as caller-supplied structured policy and key custody rather than a human signature or production authority (app/release/production_approval.py:1-5,164-225; CLAUDE.md:687-706).

### 0.4 Why a pure authority record is insufficient

The current gate has no source at all: gate #13 is hard-coded as no_evidence_source:emergency_stop (app/release/production_autonomy.py:1269-1284). A table saying “Alice may stop” without a checked runtime latch would still leave no system action that the record controls. That is a paper mechanism and conflicts with the project’s “honest blocker over fake completion” doctrine (Spec:129-149).

Slice 41 is intentionally decision-only because its inputs are reported failure classifications and suspension is a consequential enforcement action (app/agents/failure_policy.py:1-13,118-151; Slice-41 plan:16-34,51-55). Emergency stop differs in direction: pausing new work is a fail-safe action, not continuation or deployment. Whether this distinction is sufficient to make a local executing latch gate-bearing is a coordinator decision, surfaced in OD-54-1 rather than assumed.

### 0.5 The stop’s hard boundary

The runtime already supports cancellation/pause as a required runtime property in the spec (Spec:2168-2186), but the implementation only exposes a running→paused transition and a cost-specific pre-step STOP path (app/repositories/runs.py:21-29,90-171; app/runtime/engine.py:348-401). The recommended stop:

- is project-scoped;
- prevents new or resumed work from crossing the next UAID runtime step boundary after activation commits;
- pauses currently running project_runs where the existing state machine permits running→paused;
- does not preempt a node already executing before the activation transaction acquires the shared lock;
- does not kill processes, cancel provider calls, or stop external workers;
- does not execute any production rollback.

Those limitations are design requirements, not caveats to hide.

---

## 1. Verified baseline and source findings

### 1.1 Repository state verified before drafting

The following were verified directly before this file was created:

- git branch --show-current returned main.
- git rev-parse HEAD and git rev-parse origin/main both returned d8e65b3e09b50ef9fd4051c2934bbf8db15a0749.
- git status --porcelain returned no output.
- git branch --format and the remote-ref inspection found only main / origin/main.
- migrations/versions/0052_production_preapprovals.py declares revision 0052 and down_revision 0051 (migration 0052:1-20).
- app/release/production_autonomy.py declares A5_RULESET_VERSION = "slice53.v1", NO_GO_LIVE_REASONS = ("a5_gates_not_all_satisfied",), and serializes can_go_live_autonomously as the literal False (A5 evaluator:63-72,94-117).
- app/intake/readiness.py remains the Slice-20 readiness evaluator; CLAUDE records readiness as slice20.v1 after Slice 53 (Session guide:39-43,687-706).
- the pre-draft Roadmap boundary found no Slice-54 plan, branch, code, test, or migration (Roadmap:661-665).

Expected migration 0053 is therefore an **inference** from current head 0052 and Roadmap:535-536. It is not an existing artifact.

### 1.2 What the sources actually require

1. A5 gate #13 says emergency stop/rollback authority exists (Spec:2981-2997).
2. Runtime must support cancellation and pause, but the spec does not define a database shape or stop-latch algorithm (Spec:2168-2186).
3. Emergency rollback should produce an immediate alert; automatic rollback is optional and only if policy permits (Spec:1760-1770).
4. Production rollback requires approval or a pre-approved emergency rollback policy (Spec:2377-2389).
5. Production overrides require explicit authority (Spec:2999-3016).
6. Production action remains A4/A5 controlled; deploy production requires human approval or a pre-approved A5 gate (Spec:463-485).
7. The Deployment/SRE archetype expects rollback and failure drills, but that eval row does not itself grant production authority (Spec:912-930).
8. Template 20 contains approval channel, real-time categories, non-response rules, and an approvers list, but no emergency-stop action, emergency-rollback permission, auto-rollback boolean, or authority role (Approval policy template:1-16).
9. Template 23 contains governance and go-live checklist fields but no emergency authority declaration (Go-live template:1-11).

The absence in items 8-9 is load-bearing. No implementation may invent “policy permits auto-rollback” from template silence.

### 1.3 Existing primitives to extend, not fork

- project_runs uses statuses created/running/paused/blocked/completed/failed; running→paused and paused→running are valid transitions (app/models/project_run.py:22-57; app/repositories/runs.py:21-29).
- RunRepository records every status transition in immutable run_steps and safe-metadata audit entries (app/repositories/runs.py:66-126). The event taxonomy contains cost_paused but no emergency event (app/models/run_step.py:32-74; migration 0010:20-38).
- app/runtime/engine.py has exactly eight execution entry points: start/resume demo, start/resume approval, retry demo, failing demo, and start/resume cost-guarded run (app/runtime/engine.py:100-134,167-235,298-344,366-401). There is no common emergency latch check.
- The cost STOP path checks immediately before its one protected node and turns running→paused; resumption re-evaluates cost before continuing (app/runtime/engine.py:348-401). It is precedent for a step-boundary safe-direction halt, not an emergency authority.
- Slice 53 already supplies strict policy parsing, subject hashing, request-authenticated actor evidence, policy-member rows, exact release binding, bodyless bearer-authenticated endpoints, and safe response/error patterns (app/release/production_approval.py:99-111,147-225,284-335; app/models/production_preapproval.py:29-126; app/api/production_preapprovals.py:1-68).
- Slice 52 supplies a current candidate/core/commit/target-bound rollback verification, with connector_observed_ci explicitly separated from system execution (app/release/rollback.py:1-23,25-137; app/repositories/rollback_verifications.py:322-448).
- The authority matrix has no emergency-stop or rollback-authorization action; unknown actions deny by default (app/policy/matrix.py:36-71,125-136; app/policy/engine.py:22-37). Any matrix extension or deliberate non-use must be ruled, not implied.

---

## 2. Scope and non-goals

### 2.1 In scope, contingent on coordinator rulings

1. A code-owned emergency-control contract with an honest current-runtime-only scope.
2. A project-scoped DB-backed active/clear latch with an append-only state chain.
3. Actual safe-direction enforcement over every current app/runtime/engine.py entry point and before every runtime node boundary.
4. Immediate running→paused transitions for eligible current local project runs, with immutable per-run effects.
5. A request-authenticated, exact-policy-member authority binding that stores principal digests only.
6. A release-scoped rollback-authority binding to one current frozen candidate, re-audited evidence core, and current gate-eligible Slice-52 rollback verification.
7. A non-executing exact rollback-authorization event surface.
8. Narrow bodyless bearer-authenticated configure/activate/clear/authorize/current API operations if OD-54-7 selects the recommended option.
9. Additive tenant-owned RLS ENABLE+FORCE storage and DB guards after migration head 0052.
10. A5 gate #13’s first pass-capable ladder under a proposed slice54.v1 ruleset.
11. Golden regression proof that gates #1-12 are unchanged for identical inputs.
12. Explicit proof that can_go_live_autonomously remains literal False and the single no-go tuple remains byte-identical even for a synthetic all-thirteen-pass report.

### 2.2 Explicit non-goals

- No Slice-55 control loop, production deployment, broker-to-production wiring, or replacement of the literal False (Roadmap:543-545; A5 evaluator:99-117).
- No production rollback execution, cloud/infrastructure mutation, or production connector.
- No automatic rollback; current templates provide no permission primitive and §18.2 makes it optional only under policy (Spec:1760-1770; Approval policy template:1-16).
- No claim of interrupting a node already in flight, killing a process, cancelling a distributed worker, or cancelling a remote tool call.
- No new incident workflow, alert delivery channel, post-launch stabilization loop, hotfix loop, or runbook engine; those are later Phase-6 capabilities (Spec:2345-2389,2500-2510).
- No human-signature, verified-human, on-call, role, delegation, group, or organizational-authority tier.
- No weakening or reinterpretation of Slice-52 rollback evidence.
- No automatic resume after clearing a stop.
- No change to cost STOP semantics, approval wait semantics, or normal terminal run states.
- No generic authority-matrix or Tool-Broker action under recommended OD-54-2/5; a future executing production rollback cannot inherit this non-executing exception.
- No readiness change; app/intake/readiness.py remains byte-stable at slice20.v1.
- No evidence-pack or release-verdict mutation.

---

## 3. Proposed semantics

### 3.1 Recommended hybrid: execute the stop, bind rollback authority

The recommended design under OD-54-1 Option A has two deliberately different halves:

1. **Runtime stop:** UAID actually executes a local project latch and pauses current eligible project_runs. This is SYSTEM-EXECUTED-RUNTIME-STOP.
2. **Rollback authority:** UAID records who may authorize the exact currently verified rollback path. This is DB-PROVEN authority binding over CONNECTOR-OBSERVED-STAGING evidence. It does not execute production rollback.

This avoids both false extremes: a paper-only stop and a fabricated production rollback.

### 3.2 Proposed authority policy

The recommended authority source under OD-54-2 reuses the exact current Slice-53 policy snapshot and production_approval_policy_approvers rows. It does not add a second parser or infer roles. A binding is acceptable only when:

- the underlying template-20 and template-23 declarations still parse under slice53.production_approval_policy.v1;
- their current content digests equal the binding’s snapshots;
- the authority member set exactly equals the policy’s normalized principal-subject hashes;
- every invoking actor is request-authenticated and is an exact current member;
- actor_type is stored as human key metadata if the coordinator chooses the strict recommended option.

The binding provenance remains caller_supplied_unverified_structured_approval_policy plus request_authenticated key custody. It does not become verified organization policy.

Reusing the production approver set for emergency control is a **conservative coordinator-selected inference**, not a field declared by template 20. OD-54-2 must rule it explicitly.

### 3.3 Recommended split scope

Under OD-54-3 Option A:

- the **stop latch** is a standing project capability, because it must remain usable even when release evidence is incomplete or stale;
- the **rollback-authority half** is bound to the latest frozen candidate, latest complete re-audited core, and exact current gate-eligible Slice-52 rollback-verification run;
- gate #13 passes only when both halves are present, current, and consistent;
- a stale release binding must never disable an already configured safety stop, but it makes gate #13 insufficient until rebound.

This is a conservative inference from the combination of project-wide runtime pause (Spec:2168-2186), exact rollback verification (Spec:2287-2303), and release-control authority (Spec:2377-2389). Appendix B #13 does not itself specify the binding scope.

### 3.4 Proposed latch semantics

The project latch has an append-only linear state:

    armed_anchor -> activated -> cleared -> activated -> cleared ...

Rules:

- configuration creates armed_anchor only if no state exists;
- a new authority binding never resets or clears an existing active latch;
- activate while active and clear while clear fail closed or return an exact idempotent replay, per OD-54-6;
- activated means no current runtime work may begin or resume across the next protected step boundary;
- activation pauses every currently running project_run in the activation transaction;
- created runs stay created, blocked runs stay blocked, already-paused runs stay paused, and terminal runs stay terminal;
- clear changes only the latch state; it never resumes any run;
- after an authorized clear, every run must still satisfy its normal approval, cost, and state-machine conditions before a separate explicit resume.

An active emergency stop is itself a blocker. The gate ladder should not call gate #13 passed while the stop is engaged, even though mechanism and authority exist. This is a conservative safety inference surfaced in OD-54-9.

### 3.5 Race boundary

The recommended race rule uses one shared transaction-scoped exact project-row lock for:

- configure/rebind;
- activate;
- clear;
- runtime start/resume;
- every protected runtime node boundary.

Activation also locks current nonterminal project runs, appends the activated event, pauses eligible running rows, writes exact effects, and commits atomically. A DB trigger refuses any INSERT/UPDATE that would make a project_run running while the latest latch is active.

The guarantee is:

> After activation commits, no later UAID runtime step may begin while the latch remains active.

It is **not**:

> Activation preempts code already executing before the shared lock is acquired.

That distinction must be tested and documented.

### 3.6 Proposed stop/clear separation

The recommended policy under OD-54-4 is asymmetric:

- activation is safe-direction and may be invoked by any current bound authority, even if that principal requested or approved the current production pre-approval;
- clear is risk-increasing and requires a second, distinct current bound authority from the principal that activated the current stop;
- therefore a gate-bearing binding requires at least two distinct authority members;
- rollback authorization is explicit, exact-release-scoped, and request-authenticated, but does not execute the rollback.

This two-person clear rule is a proposed security posture, not literal source text. Section 2.2 supports independence for consequential outputs, while Appendix B #13 and §25.2 do not specify a clear-stop quorum (Spec:151-159,2377-2389,2997).

### 3.7 Currentness and staleness

Recommended content/binding currentness:

- latest **authorized** binding attempt wins by created_at DESC, id DESC;
- a later authorized failed/refused binding attempt supersedes an older eligible binding;
- an unauthorized call is rejected and safely audited but creates no binding attempt, so a nonmember cannot supersede a valid binding by denial-of-service;
- current policy/checklist digest or member-set change de-currents the binding;
- autonomy-policy digest change de-currents the rollback-authority half;
- current frozen candidate, evidence core, or Slice-52 rollback-run change de-currents the rollback-authority half;
- contract-version change requires a new binding;
- active/clear state is independent and carries forward across rebinds;
- there is no wall-clock TTL for the standing stop mechanism;
- Slice-52 staging-snapshot freshness remains independently enforced by Slice 52;
- no policy member or binding is silently backfilled or relabelled.

Appendix B #13 and §25.2 specify no TTL. Adding one would require an explicit coordinator security ruling.

### 3.8 Immediate alert and auto-rollback

Section 18.2 says emergency rollback has an immediate alert and optional auto-rollback if policy permits (Spec:1760-1770). This slice can honestly reuse the existing dashboard approval-channel notification shape only if the coordinator rules it; it cannot call that alert delivered unless an actual channel result exists.

Recommended v1 behavior:

- every stop activation and rollback authorization writes safe audit metadata immediately, but an audit row is **not** called an alert;
- a dedicated incident alert is deferred because template 20 declares no emergency-alert contract or destination (Approval policy template:1-16);
- auto-rollback is forbidden because no canonical policy field permits it;
- the absence of auto-rollback does not get rewritten as a failure of the stop latch, but remains an explicit scope limitation.

---

## 4. Open decisions requiring coordinator ruling

### OD-54-1 — What mechanism is sufficient for gate #13?

**Option A — recommended:** the hybrid in §3.1: real DB-backed project latch enforced over the existing UAID runtime, plus DB-bound exact rollback authority over the Slice-52 path. Permit gate #13 to pass with a reason that names request-authenticated authority and current-runtime scope. Accept explicitly that this is not production incident execution.

**Option B:** authority-binding records only. Keep gate #13 non-passing because no executable halt lever exists. This is smaller but risks a paper mechanism.

**Option C:** defer gate #13 PASS-capability until a real production deployment/rollback connector exists. The local runtime latch may still ship as trust infrastructure, but gate #13 remains insufficient.

### OD-54-2 — What is the authority source and actor tier?

**Option A — recommended:** reuse the exact current Slice-53 strict policy snapshot/member set. Invokers must be exact request-authenticated members with actor_type=human metadata. Persist digests only. Keep the source labelled caller-supplied structured policy and key custody, never verified human authority. Leave the generic authority matrix byte-stable: activating the safe-direction latch is a direct exact-member operation, while the Slice-54 rollback action only records authority and executes nothing. Any future executing production rollback must receive its own separately reviewed matrix/broker policy.

**Option B:** allow request-authenticated human or service members. This improves operational availability but broadens emergency authority beyond Slice-53’s gate-bearing approver actor rule.

**Option C:** add a separate caller-declared emergency-authority list. This avoids coupling but duplicates policy, and no canonical template defines its semantics.

### OD-54-3 — Is authority standing or release-scoped?

**Option A — recommended:** split scope: standing project stop capability plus exact candidate/core/Slice-52-run-bound rollback authority. Stale release evidence never disables stop activation, but gate #13 requires both halves current.

**Option B:** standing project binding for both stop and rollback authority. Simpler, but less exact than the release-binding discipline of Slices 49-53.

**Option C:** fully release-scope both stop and rollback. Strong binding, but a stale/missing release graph could disable the safety stop.

### OD-54-4 — Who may activate, clear, and authorize rollback?

**Option A — recommended:** any current member may activate; activation has no separation from Slice-53 requester/approver roles. Clear requires a distinct second current member, so gate-bearing bindings require at least two members. Any current member may record exact rollback authorization; that event remains non-executing.

**Option B:** the same current member may activate and clear. Operationally simpler but weaker against premature clearing.

**Option C:** require two distinct members for activation, clear, and rollback authorization. Strongest separation but may delay a safe-direction emergency stop.

### OD-54-5 — What does “rollback authority” do in this slice?

**Option A — recommended:** it creates an immutable, exact release/core/rollback-run-bound authorization event. It invokes no connector and no deployment. Gate #13 requires the capability binding, not an emergency event to have occurred.

**Option B:** invoke another staging rollback drill. That proves staging behavior, not production authority, and duplicates gate #10.

**Option C:** execute production rollback. Unsupported: the current runtime defers real tool/broker wiring, the rollback contract is observation-only, and template 20 has no emergency permission primitive (Runtime engine:26-28; Rollback contract:1-5; Approval policy template:1-16).

### OD-54-6 — What lifecycle and race rule governs the latch?

**Option A — recommended:** append-only linear latch events; shared exact project-row transaction lock; exact per-run effects; DB refusal of running state while active; step-boundary checks; clear never auto-resumes; no TTL.

**Option B:** one mutable project boolean. Smaller, but erases history unless paired with a second event log and makes direct-SQL truth ownership harder.

**Option C:** append-only events without DB/runtime guards. Honest as a log, but not sufficient as an executing stop.

### OD-54-7 — What invocation surface exists?

**Option A — recommended:** narrow bearer-authenticated, bodyless, idempotent endpoints for bind/rebind, activate, clear, authorize-current-rollback, and current status. Identity only from TenantContext.actor; all source/binding IDs derived server-side; safe IDs/status/reason codes only; generic 404/409; no cross-tenant existence oracle.

**Option B:** internal service/repository methods only. This avoids HTTP but leaves no actual operator-facing invocation path.

### OD-54-8 — What data model owns truth?

**Option A — recommended:** the five normalized append-only tables in §6, generated row-local fields, deferred graph triggers, one additive project_runs active-latch guard, and an additive run_steps event-type extension restoring the exact prior constraint on downgrade.

**Option B:** fewer JSON-heavy rows. Smaller schema, but weaker DB re-derivation and easier caller truth injection.

### OD-54-9 — What exact gate ladder and hard-false behavior ship?

**Option A — recommended:** the ladder in §8.1, including active-stop blocking, and pass reason passed:request_authenticated_runtime_stop_and_release_bound_rollback_authority. Advance only gate #13 under slice54.v1. Keep the one-element no-go tuple and literal False byte-identical; synthetic all-13-pass yields a5_satisfied=true but can_go_live_autonomously=false.

**Option B:** keep gate #13 insufficient even with the local latch because it is not a production stop; defer the pass branch. This pairs naturally with OD-54-1 Option C.

### OD-54-10 — Contracts, bounds, audit, downgrade, and preservation

**Option A — recommended:** use slice54.emergency_control.v1, slice54.emergency_stop.v1, and slice54.rollback_authority.v1; canonical SHA-256 digests; ≤100 authority members; codes/keys ≤128; refs ≤500; empty request bodies; no arbitrary run-count cap that could make a safety stop refuse—the finite DB-owned current nonterminal project-run set is handled set-wise; no raw principals/policy/target/repo/version/log/body/prose in new tables, A5 context, audit, errors, or logs; caller truth fields fail closed; downgrade 0053→0052 fails closed while Slice-54 rows exist; findings guard MD5 remains 808036faf2660d6810aeca4342e6f1ac; downgrade restores the exact pre-0053 project-run/run-step guard state.

**Option B:** coordinator supplies different contract versions, caps, or downgrade posture before implementation.

No implementation may begin until OD-54-1…10 are all ruled and bound verbatim into this plan.

---

## 5. Proposed modules and workflow

### 5.1 app/release/emergency_stop.py

Pure responsibilities:

- contract-version constants;
- bounded code and digest validation;
- authority-set digest and exact release/rollback binding digest;
- latch transition validation;
- actor authorization matrix;
- scope-limitation codes;
- currentness comparison;
- gate-safe coverage dataclass;
- no I/O, no deployment, no connector.

Proposed fixed scope codes:

- local_uaid_runtime_step_boundary_only;
- in_flight_node_not_preempted;
- production_rollback_not_executed;
- rollback_path_connector_observed_staging_only;
- authority_is_request_authenticated_key_custody_under_recorded_policy.

These codes prevent prose drift and keep the limitation machine-visible.

### 5.2 app/repositories/emergency_controls.py

Proposed responsibilities:

- resolve the current strict Slice-53 policy without reimplementing its parser;
- derive the current member set from production_approval_policy_approvers;
- resolve current autonomy, candidate, re-audited core, and gate-eligible Slice-52 rollback run;
- append authorized binding attempts and exact member rows;
- take the shared exact project-row lock;
- activate/clear the latch;
- enumerate and pause eligible running runs;
- append per-run effects;
- record exact rollback authorization without connector execution;
- compute gate coverage from current sources and latest attempts/events;
- audit safe metadata only.

### 5.3 app/release/emergency_control_service.py

The service is the only mutating orchestrator:

1. require TenantContext.actor;
2. hash the actor subject;
3. prove exact current policy membership;
4. derive all project/release/evidence bindings server-side;
5. acquire the shared exact project-row lock;
6. perform one idempotent operation;
7. flush the complete graph;
8. rely on deferred constraints at commit;
9. return safe IDs/status/reason codes.

No method accepts actor, authority, approved, trusted, eligible, current, gate, passed, release candidate, evidence pack, rollback run, policy member, or latch-state fields from a request body.

### 5.4 Runtime integration

Proposed narrow changes:

- add RunRepository.mark_paused_for_emergency with event_type emergency_paused;
- add a single reusable emergency boundary check;
- invoke it at all eight runtime entry points and before every graph node that may do work;
- share the same project transaction lock with activation/clear;
- keep cost STOP evaluation independent;
- refuse mark_running/mark_resumed while the project latch is active through both repository and DB guards;
- never automatically mark a blocked run running;
- never resume on clear.

The existing normal transition table remains semantically unchanged except for using the already-valid running→paused path (app/repositories/runs.py:21-29). The run_steps event allowlist gains only emergency_paused; every old value remains accepted and downgrade restores the exact pre-0053 set (migration 0010:20-38).

### 5.5 Proposed API under OD-54-7 Option A

Bodyless endpoints, all with Idempotency-Key where mutating:

- POST /api/projects/{project_id}/emergency-control/bind
- POST /api/projects/{project_id}/emergency-stop/activate
- POST /api/projects/{project_id}/emergency-stop/clear
- POST /api/projects/{project_id}/emergency-rollback/authorize
- GET /api/projects/{project_id}/emergency-control/current

The endpoints reuse Slice-53’s empty-body, generic conflict, and request-authenticated context patterns (app/api/production_preapprovals.py:25-68,71-164). No request body can select an identity, release, target, version, or authority.

---

## 6. Additive data model and expected migration 0053

Expected 0053_emergency_controls.py is an inference from verified head 0052 and Roadmap:535-536. All new tables are tenant-owned, RLS ENABLE+FORCE, composite-FK pinned to tenant/project, append-only, SELECT/INSERT only for uaid_app, and protected against UPDATE/DELETE/TRUNCATE. Existing rows are never backfilled or relabelled.

### 6.1 emergency_control_bindings

One immutable binding attempt:

- id, tenant_id, project_id;
- policy_version_id;
- autonomy_policy_id;
- release_candidate_id nullable for a stop-only partial binding;
- evidence_pack_id nullable;
- rollback_verification_run_id nullable;
- emergency_control_contract_version;
- emergency_stop_contract_version;
- rollback_authority_contract_version;
- source_provenance;
- binding_attempt_status: succeeded | failed | refused;
- reason_code;
- policy_digest, checklist_digest, approver_set_digest, autonomy_policy_digest;
- release/core/rollback binding digests nullable as a complete set;
- authority_member_count;
- stop_authority_bound;
- rollback_authority_bound;
- evidence_consistent;
- gate_eligible_at_creation;
- configured_by_subject_hash;
- configured_by_actor_type;
- configured_by_provenance=request_authenticated;
- idempotency_key_hash;
- created_at.

Succeeded stop-only bindings may remain operational but are not gate-eligible without exact rollback authority. Failed/refused rows have no member children unless the failure occurred after an exact authorized member set was established. The deferred guard owns this duality.

### 6.2 emergency_control_authority_members

Exact normalized member snapshot:

- id, tenant_id, project_id, binding_id;
- policy_approver_id;
- ordinal;
- principal_subject_hash;
- may_activate_stop=true;
- may_clear_stop according to OD-54-4;
- may_authorize_rollback=true;
- created_at.

Deferred constraints require the child set and digest to equal the referenced current Slice-53 policy member set exactly. A caller cannot add a member, omit a member, change a capability flag, or provide a plaintext subject.

### 6.3 emergency_stop_events

Append-only project latch chain:

- id, tenant_id, project_id;
- binding_id;
- previous_event_id nullable;
- event_type: armed_anchor | activated | cleared;
- state_after generated as armed | active;
- actor_member_id;
- actor_subject_hash;
- actor_type;
- actor_provenance=request_authenticated;
- reason_code, code-owned only;
- idempotency_key_hash;
- created_at.

DB rules:

- exactly one root armed_anchor per project;
- every later event has exactly one previous event;
- previous_event_id is unique, making the chain linear;
- transitions alternate active/armed correctly;
- an active event cannot be bypassed by adding a new binding;
- clear satisfies the OD-54-4 separation rule;
- actor member, binding, project, tenant, subject hash, and provenance all agree.

### 6.4 emergency_stop_run_effects

Immutable activation effects:

- id, tenant_id, project_id;
- activation_event_id;
- run_id;
- emergency_run_step_id nullable only for no-transition outcomes;
- status_before;
- status_after;
- effect_code: paused | already_paused | already_blocked | not_started;
- created_at.

For paused effects, status_before=running, status_after=paused, and emergency_run_step_id references an immutable same-run emergency_paused run_steps row. Non-transition effects prove classification only; they do not claim a status change.

The deferred graph guard re-derives the exact **nonterminal** activation inventory under the transaction lock and proves that no running row remains when activation commits. Terminal rows are excluded from effect inventory because activation cannot change them. Direct SQL cannot forge an effect to stand in for an unpaused run.

### 6.5 emergency_rollback_authorizations

Immutable, non-executing exact authorization:

- id, tenant_id, project_id;
- binding_id;
- release_candidate_id;
- evidence_pack_id;
- rollback_verification_run_id;
- actor_member_id;
- actor_subject_hash;
- actor_type;
- actor_provenance=request_authenticated;
- release_rollback_binding_digest;
- authorization_contract_version;
- result_code=authorized_not_executed;
- scope_limitation_code=production_rollback_not_executed;
- idempotency_key_hash;
- created_at.

The DB re-derives exact membership and binding. This row is not a deployment event, connector call, provider observation, or proof that a rollback occurred.

### 6.6 Existing-object extensions

Under OD-54-8 Option A only:

1. Extend run_steps event_type CHECK with emergency_paused; preserve every existing value and restore the exact Slice-8b set on downgrade (app/models/run_step.py:32-56; migration 0010:20-38).
2. Add a project_runs emergency-latch guard that refuses created/paused/blocked→running and direct running inserts while the latest project latch is active. Preserve every existing status and transition meaning (app/models/project_run.py:22-57; app/repositories/runs.py:21-41).
3. Add only missing composite UNIQUE targets needed by new same-project FKs, after verifying absence in the migration implementation.
4. Do not touch release_findings_guard(); pin MD5 808036faf2660d6810aeca4342e6f1ac before/after upgrade, downgrade, and re-upgrade, matching current test assertions (tests/test_production_preapprovals.py:757-759; tests/test_rollback_verifications.py:513-515).

### 6.7 Downgrade

Downgrade 0053→0052:

- refuses while any Slice-54 row exists;
- removes only Slice-54 triggers, policies, grants, tables, and additive identity targets;
- restores the exact pre-0053 run_steps CHECK;
- removes the project_runs latch guard;
- leaves all runtime history, Slice-52 rollback evidence, Slice-53 authority evidence, findings guard, A5 rules, and readiness behavior otherwise unchanged.

---

## 7. Repository/service behavior

### 7.1 Bind/rebind

1. Require a request-authenticated actor.
2. Parse current canonical policy/checklist with the existing Slice-53 parser.
3. Require actor membership under the ruled actor type.
4. Snapshot exact policy members and content digests.
5. Resolve autonomy policy and, separately, current candidate/core/rollback evidence.
6. Write a stop-capable partial binding even if release evidence is absent only if OD-54-3 permits; mark rollback_authority_bound=false and gate_eligible=false.
7. Write a fully gate-eligible binding only when the exact release/rollback graph is current.
8. Never clear an active latch during rebind.

### 7.2 Activate

1. Require a current authorized binding member.
2. Acquire the shared exact project-row lock.
3. Re-check current policy/member binding inside the lock.
4. Reject/idempotently replay if already active.
5. Append activated.
6. Pause every running project_run through the ruled emergency transition.
7. Record exact effects for all current nonterminal runs.
8. Commit only when deferred graph checks pass.
9. Return activated plus safe counts; never return principal, target, repo, version, or policy data.

### 7.3 Runtime behavior while active

- all start operations fail before a run becomes executing;
- all resume operations remain paused/blocked and execute no next node;
- a run already running at activation is paused at the first transaction boundary the stop can acquire;
- direct SQL cannot set running;
- cost and approval gates are not bypassed;
- repeated status reads are side-effect free.

### 7.4 Clear

1. Require active state.
2. Require current member and the ruled separation.
3. Acquire the shared exact project-row lock.
4. Append cleared.
5. Do not mutate any project_run.
6. Do not enqueue work or auto-resume.

### 7.5 Authorize rollback

1. Require a current fully release-bound authority binding.
2. Re-audit current core and current Slice-52 evidence.
3. Require exact member authorization.
4. Append authorized_not_executed.
5. Invoke no connector, broker, deploy service, cloud API, or rollback action.

### 7.6 Audit surface

Allowed audit fields only:

- project_id;
- binding/event/effect/authorization IDs;
- operation code;
- result/reason code;
- contract versions;
- member_count;
- affected_run_count and per-effect safe counts;
- stop state code;
- booleans for policy current, rollback bound, evidence consistent, gate eligible;
- request_authenticated provenance label;
- fixed scope-limitation codes.

Forbidden everywhere in audit/context/errors/logs:

- plaintext or hashed principal subjects;
- policy YAML/JSON or approver lists;
- API keys or headers;
- release refs, repo names, commit SHAs, target domains/URLs/IPs/ports;
- artifact/version digests;
- run payloads/checkpoint content;
- free-form reason, incident, approval, or rollback prose;
- connector artifacts, response bodies, logs, prompts, or secrets.

Audit actor is a bounded role code such as emergency_control_authority, never a principal or subject hash.

---

## 8. A5 gate #13 and hard-false boundary

### 8.1 Proposed ordered ladder under OD-54-9 Option A

Gate name remains emergency_stop_rollback_authority. The proposed precedence is:

1. insufficient_evidence:no_recorded_emergency_authority_policy
2. insufficient_evidence:emergency_authority_policy_invalid
3. insufficient_evidence:no_emergency_control_binding
4. insufficient_evidence:latest_emergency_control_binding_failed_or_refused
5. insufficient_evidence:emergency_control_contract_mismatch
6. insufficient_evidence:emergency_authority_membership_incomplete
7. insufficient_evidence:emergency_stop_mechanism_uninitialized
8. insufficient_evidence:emergency_stop_state_inconsistent
9. insufficient_evidence:rollback_authority_not_release_bound
10. insufficient_evidence:rollback_authority_binding_stale
11. insufficient_evidence:rollback_verification_not_current_or_gate_eligible
12. insufficient_evidence:emergency_control_evidence_inconsistent
13. insufficient_evidence:emergency_stop_active
14. passed:request_authenticated_runtime_stop_and_release_bound_rollback_authority

Safe context only:

- policy_present, policy_valid;
- binding_present, latest_binding_failed_or_refused, binding_current;
- authority_member_count;
- mechanism_initialized, stop_active;
- rollback_authority_bound, rollback_binding_current;
- rollback_verification_current;
- evidence_consistent;
- emergency_control_contract_version;
- emergency_stop_contract_version;
- rollback_authority_contract_version;
- fixed scope-limitation codes.

No IDs, subject hashes, policy digests, release refs, repo/commit/target/version data, run IDs, or incident details enter A5 context.

### 8.2 Ruleset and golden matrix

If OD-54-9 Option A is ruled:

- A5_RULESET_VERSION advances from slice53.v1 to slice54.v1 because gate #13 gains its first pass branch.
- Gate #13 becomes the thirteenth and final PASS-capable Appendix-B gate.
- Gates #1-12 remain byte-identical for identical inputs.
- Gate #13 alone changes from a permanent no-source row to the ruled ladder.
- a5_satisfied may become true for a synthetic report where all 13 gates are passed.
- can_go_live_autonomously remains literal False.
- NO_GO_LIVE_REASONS remains exactly ("a5_gates_not_all_satisfied",).
- Slice 55 alone may replace the literal after its control-loop policy is separately designed and approved (A5 evaluator:99-117; Roadmap:543-545; Session guide:699-706).

### 8.3 Mandatory hard-false matrix

| Constructible/synthetic state | Gate #13 | a5_satisfied | can_go_live_autonomously |
|---|---:|---:|---:|
| no binding | insufficient | false | false |
| authority binding but no executing latch | insufficient | false | false |
| latch armed but rollback authority stale | insufficient | false | false |
| latch active | insufficient | false | false |
| gate #13 passes but any other gate fails | passed | false | false |
| synthetic all 13 pass | passed | true | **false** |

The single no-go reason remains accurate because Slice 54 completes evidence PASS-capability but does not implement the governed transition that Slice 55 owns.

---

## 9. Test-first implementation plan

### 9.1 Pure tests — proposed tests/test_emergency_controls.py

1. Contract constants and fixed scope codes.
2. Truth-tier matrix rejects any relabelling of request-authenticated as human-signed or system runtime stop as production stop.
3. Policy-member normalization reuses exact Slice-53 subject digests and rejects blank/duplicate/oversized/wildcard/role-shaped inputs through the existing parser.
4. Exact authority-set digest is order-stable only under the ruled canonical order.
5. Exact release/rollback binding requires every ruled component.
6. State transitions accept only armed→active→armed.
7. Rebind never changes latch state.
8. Activation authorization matrix across member/nonmember, actor type, and provenance.
9. OD-54-4 separation matrix for activate/clear/rollback authorization.
10. Currentness invalidation for policy, member set, autonomy, candidate, core, rollback run, and contract changes.
11. No TTL beyond source-specific currentness.
12. All 14 gate rungs are precedence-tested with deterministic single-rung fixtures.
13. Pass reason vocabulary contains request_authenticated and runtime_stop, never human, signed, production_stop, production_rollback_executed, or deploy.
14. Golden pure matrix proves gates #1-12 before==after.
15. Hard-false matrix includes the synthetic all-thirteen-pass row.
16. Forbidden caller truth fields fail closed.

### 9.2 Runtime/service/API tests

1. Configure succeeds only for an exact current request-authenticated policy member.
2. Configure by absent actor, nonmember, stale member, wrong project, or wrong tenant fails generically.
3. Bodyless API/OpenAPI proves no actor, authority, release, target, condition, or truth field is accepted.
4. Idempotent replay returns the same safe result; conflicting key use fails.
5. Start a checkpointed demo run, activate stop, attempt resume: node_b never executes and run remains paused.
6. Activate before each of all eight runtime entry points: no protected node executes.
7. Activate against running/created/paused/blocked/completed/failed runs: only running transitions; all effects are exact.
8. Stop activation after an approval-gated run blocks: it stays blocked and cannot resume while active.
9. Stop activation after cost pause: it stays paused; clear never bypasses the cost STOP.
10. Unauthorized clear fails; direct resume remains blocked.
11. Under OD-54-4 Option A, the activating member cannot clear; a second current member can.
12. Authorized clear changes only latch state and does not resume runs.
13. After clear, normal approval/cost/state-machine gates still control resume.
14. Activation/restart race uses the shared lock: once activation commits, no subsequent node begins.
15. An already executing node is not described as preempted; test fixtures prove only the transaction/step-boundary guarantee.
16. New binding while active cannot clear or reset the latch.
17. Policy/release changes de-current gate evidence without disabling the active latch.
18. Exact rollback authorization appends a row and performs zero connector/deploy/broker calls.
19. Stale/missing/non-gate-eligible Slice-52 evidence refuses rollback authorization.
20. Generic 404/409 behavior gives no cross-tenant existence oracle.
21. Audit sentinel covers configure success/failure, activation, already-active, clear, unauthorized clear, rollback authorization, API errors, and exceptions.

### 9.3 DB-backed and direct-SQL adversarial tests

1. Migration 0052→0053→0052→0053 with captured exit codes.
2. All new tables RLS ENABLE+FORCE; uaid_app has only intended grants.
3. Cross-tenant and cross-project composite FKs reject binding/member/event/effect/authorization forgery.
4. UPDATE/DELETE/TRUNCATE rejected on every new table.
5. Plaintext/invalid subject hashes, wrong provenance, fake actor types, forged membership, and member omission reject at commit.
6. Failed/refused versus succeeded binding child-set duality enforced.
7. Direct SQL cannot set stop_authority_bound, rollback_authority_bound, evidence_consistent, or gate_eligible contrary to re-derived graph truth.
8. Event root/linear chain/alternation enforced; forked, skipped, duplicate, cross-binding, or clear-without-active chains reject.
9. Direct-SQL clear by a nonmember or disallowed same actor rejects.
10. Direct SQL cannot make project_runs running while active.
11. Direct SQL cannot forge an emergency_paused run step or run effect to hide an unpaused running run.
12. Missing, duplicate, wrong-run, wrong-state, or wrong-event activation effects reject at commit.
13. Activation commit proves no running project run remains.
14. Direct SQL cannot forge a rollback authorization for a stale/different candidate, core, rollback run, member, project, or tenant.
15. A rollback authorization cannot claim executed/succeeded deployment.
16. Existing run-step immutability remains intact.
17. Existing runtime transition and Slice-8b approval/cost suites remain untouched and green.
18. Slice-52 rollback verification behavior and gate #10 remain unchanged.
19. Slice-53 production preapproval behavior and gate #12 remain unchanged.
20. release_findings_guard() MD5 equals 808036faf2660d6810aeca4342e6f1ac before/after upgrade, downgrade, and re-upgrade.
21. Existing finding, issue, verdict, evidence-pack, cost, rollback, and preapproval guards remain unchanged.
22. Audit rows contain safe metadata only; sentinel principals, hashes, policy values, release refs, repo/commit/target/version data, run payloads, logs, URLs, and secrets appear nowhere in audit/context/errors/logs.
23. Downgrade refuses while Slice-54 rows exist, then succeeds after explicit fixture cleanup.
24. Readiness output and app/intake/readiness.py hash are byte-stable.
25. NO_GO_LIVE_REASONS tuple and the literal False are byte-identical.
26. app/policy/matrix.py and app/policy/engine.py hashes and behavior are byte-stable under recommended OD-54-2/5.

“Forged membership” above means a nonmember hash, mismatched member row, wrong binding, or wrong tenant/project. A DB session that copies an exact existing member hash is outside what relational constraints can distinguish from the application’s app-stamped value. The service/API tests must prove callers cannot supply that value; the direct-SQL suite proves relational guard resistance and exact stored-graph derivation, not API-key secrecy, real-world bearer custody, human presence, or organizational authority (app/identity.py:1-12).

### 9.4 Required eventual pre-PR verification

Only after plan approval, coordinator rulings, and implementation:

    git diff --check
    ruff check .
    make test
    RLS_DB_PASSWORD=... make test-db
    # captured-exit migration round trip:
    0052 -> 0053 -> 0052 -> 0053

Every command must have complete output and a captured exit code. A truncated run is a failed verification, following the Slice-50 process lesson recorded by the coordinator.

---

## 10. Prospective file-touch map

### New, only after approval/rulings

- app/release/emergency_stop.py
- app/release/emergency_control_service.py
- app/repositories/emergency_controls.py
- app/models/emergency_control.py
- app/api/emergency_controls.py if OD-54-7 Option A
- migrations/versions/0053_emergency_controls.py
- tests/test_emergency_controls.py

### Modified narrowly

- app/models/__init__.py — model registration only.
- app/main.py — router registration only if OD-54-7 Option A.
- app/models/run_step.py — add emergency_paused only.
- app/repositories/runs.py — emergency pause wrapper and central latch enforcement seam.
- app/runtime/engine.py — shared check at all current entry/node boundaries.
- app/release/production_autonomy.py — gate #13 ladder and slice54.v1 only; literal False and no-go tuple untouched.
- app/repositories/production_autonomy.py — read safe emergency coverage only.
- shared Slice-53 policy-resolution code only if a minimal extraction is required to reuse, never fork, the exact parser/current-policy logic.

### Byte-stable / semantically untouched

- app/intake/readiness.py
- app/identity.py
- app/release/rollback.py
- app/repositories/rollback_verifications.py
- app/models/rollback_verification.py
- app/release/production_approval.py except a minimal no-semantics helper extraction if strictly needed
- app/models/production_preapproval.py
- app/policy/matrix.py
- app/policy/engine.py
- templates 20 and 23
- release_findings_guard()
- all gate #1-12 outputs for identical inputs
- NO_GO_LIVE_REASONS
- the can_go_live_autonomously literal False

---

## 11. Must NOT claim

1. Must NOT claim Appendix C literally mandates an emergency-stop mechanism; it says production overrides require explicit authority.
2. Must NOT claim the local runtime latch is a production kill switch, incident-response platform, process kill, distributed cancellation, or provider-call cancellation.
3. Must NOT claim activation preempts a node already executing.
4. Must NOT claim a paused project_run proves every external effect stopped.
5. Must NOT claim a pure authority record without an operative latch is sufficient under recommended OD-54-1.
6. Must NOT call request_authenticated a human signature, human-presence proof, verified human, verified on-call operator, or organizational authority.
7. Must NOT call template-20 approvers verified authority or infer roles/groups/delegation.
8. Must NOT claim DB constraints cryptographically prove bearer custody or can distinguish a copied exact member hash from the app-stamped hash.
9. Must NOT invent emergency permission, an auto-rollback policy, alert destination, or escalation chain from template silence.
10. Must NOT call an audit row, status endpoint, or stored event the §18.2 immediate alert.
11. Must NOT claim a rollback authorization executes rollback.
12. Must NOT claim Slice-52 connector-observed staging evidence proves production rollback success.
13. Must NOT claim a new binding clears an active stop.
14. Must NOT auto-resume on clear or bypass approval/cost/state-machine gates.
15. Must NOT allow missing, stale, failed, or refused evidence to fall back to an older passing binding.
16. Must NOT let active stop state coexist with a passed gate #13 under recommended OD-54-9.
17. Must NOT expose or audit principal hashes, policy contents, release/repo/commit/target/version data, run payloads, logs, URLs, credentials, or secrets.
18. Must NOT accept caller-supplied actor/authority/release/binding/current/active/cleared/trusted/eligible/passed/gate fields.
19. Must NOT weaken run history, run transitions, Slice-52 rollback guards, Slice-53 preapproval guards, or the layered findings guard.
20. Must NOT change readiness.
21. Must NOT claim a passing gate #13 means A5 is satisfied in a real project state.
22. Must NOT claim all 13 pass-capable gates authorize production.
23. Must NOT change the literal False or the one-reason no-go tuple; Slice 55 owns any future change.
24. Must NOT implement the Slice-55 control loop, production deploy, production rollback, incident workflow, or auto-rollback.
25. Must NOT begin implementation until reviewer APPROVE and final coordinator rulings for every OD-54-1…10 are bound into this plan.

---

## 12. Definition of done for future implementation — not this task

Future implementation is done only when:

- this plan is reviewer-approved;
- OD-54-1…10 are ruled and recorded verbatim before code;
- the plan-binding change is its own atomic commit, following the restored convention;
- migration 0053 is additive and round-trips with captured exit codes;
- the real current-runtime stop executes and cannot be bypassed through current runtime entry points or direct SQL;
- stopped runs do not resume without ruled current authority;
- rollback authority is exact and non-executing;
- gate #13 follows the ruled ladder and gate #1-12 golden outputs are unchanged;
- findings guard, readiness, no-go tuple, and literal False are preserved;
- pure and DB suites are green against a freshly recreated DB;
- audit and error sentinels are clean;
- no .env or .pending-auth-captures.jsonl is staged;
- a reviewer receives branch, atomic commit SHAs, PR URL, complete test counts/exit codes, migration evidence, and muhasabah audit;
- the PR is not merged without explicit reviewer approval.

---

## 13. Muhasabah self-audit

Completed before submission:

- **Sanad:** current-state and specification claims were checked against the cited git commands, source lines, templates, migrations, and prior approved plans. The Appendix-C/roadmap overstatement is corrected explicitly rather than repeated.
- **Hidden assumptions:** mechanism sufficiency, actor tier, policy source, standing versus release scope, separation, rollback semantics, lifecycle/race behavior, API surface, DB truth ownership, gate behavior, and bounds are all exposed as OD-54-1…10.
- **No fabrication:** the draft creates no production actuator, auto-rollback permission, immediate-alert claim, human-signature tier, production-stop claim, or DB proof of bearer custody.
- **Scope:** only .planning/SLICE-54-PLAN.md exists as a worktree change; no branch, code, migration, test, commit, or PR was created.
- **Safety:** active stop blocks gate #13; clearing never resumes; stale release evidence cannot disable the stop; direct SQL and runtime bypass cases are planned; the literal False and single no-go reason remain unchanged.
- **Verification discipline:** implementation-only commands and test claims are prospective. No implementation test result is claimed in this plan-only task.

Result: **PASS for plan submission**, pending independent reviewer APPROVE/REJECT and coordinator rulings.

---

## 14. Reviewer gate

**Reviewer request:** APPROVE or REJECT this plan-only design.

APPROVE confirms source grounding, honesty, and scope discipline. It does not authorize implementation until the coordinator also rules every OD-54-1…10 and those rulings are bound into this file. REJECT should cite exact lines/claims and required corrections.

Until both gates are satisfied: no branch, code, migration, tests, commit, PR, production action, rollback action, control-loop work, or Slice-55 work.
