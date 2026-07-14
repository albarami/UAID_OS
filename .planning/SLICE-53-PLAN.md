# Slice 53 Plan — Production-approval workflow → request-authenticated A5 pre-approval (gate #12)

**Status:** MERGED — historical record. Implemented via PR #96 (squash commit `5fd8b18`); this v1 plan is retained as the approved design rationale for Slice 53.

**Plan type:** Highest-stakes gate-path authority slice; plan-only submission. This document authorizes exactly one planning file and does **not** authorize a branch, code, migration, tests, a commit, a PR, production access, or deployment.

**Author persona:** Senior release-governance and identity-security architect, applying fail-closed authority design.

## Sanad / citation key

- **Spec** — `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`.
- **Approval policy template** — `docs/UAID_OS_Intake_Template_Pack_v1_2/20_human_approval_policy.yaml`.
- **Go-live checklist template** — `docs/UAID_OS_Intake_Template_Pack_v1_2/23_go_live_checklist.yaml`.
- **Roadmap** — `.planning/GO-LIVE-END-TO-END-ROADMAP.md`, Rev 13.
- **Approval prior art** — `app/approvals/states.py`; `app/models/approval.py`; `app/models/approval_event.py`; `app/repositories/approvals.py`; migration `0005_approvals`.
- **Identity prior art** — `app/identity.py`; `app/api/auth.py`; `app/repositories/api_keys.py`; `app/models/tenant_api_key.py`; migration `0026_request_auth_identity`.
- **Approval-channel prior art** — `app/approvals/channels/routing.py`; `app/approvals/channels/service.py`; `app/models/approval_notification.py`; migration `0032_approval_notifications`.
- **Release-scope prior art** — `app/models/release_candidate.py`; `app/models/evidence_pack.py`; `app/models/release_verdict.py`; `app/repositories/evidence_packs.py`; `app/repositories/release_verdicts.py`; migrations `0048_evidence_packs` and `0049_release_verdicts`.
- **A5 evaluator** — `app/release/production_autonomy.py`; `app/repositories/production_autonomy.py`.
- **Repository guide** — `CLAUDE.md`, especially “How to work” and “Current status (2026-07-14).”
- **Baseline commands** — read-only Git and file inspection recorded in §1. No suite was run for this plan-only task.

Prospective modules, tables, migration contents, contract versions, bounds, reason codes, and tests below are **PROPOSED**, not current-code claims. Where sources do not dictate a choice, this plan labels it **inference**, **assumption**, or **open decision** and requires a coordinator ruling.

---

## Coordinator rulings (final)

- **OD-53-1 = Option A:** the existing app-stamped key-custody tier, used narrowly. Both actors require real `TenantContext.actor` values; both provenance fields `request_authenticated`; the sidecar proves binding, membership, and separation. All wording everywhere — code, reasons, docs, audit — says key custody under recorded policy; never "human signature" or "verified human." Direct-SQL tests prove relational guard resistance, never cryptographic identity or bearer custody.
- **OD-53-2 = Option A:** strict `slice53.production_approval_policy.v1` projection over current canonical template-20/23 data; concrete `dashboard` channel required; `production_deployment` in `realtime_for`; `production: block_until_approval`; exact shipped governance codes; non-empty unique bounded `approvers` as exact principal subjects (no roles — none exist); snapshot stamped `caller_supplied_unverified_structured_approval_policy`; pipe-placeholders and empty approver lists never pass as live policy; the spec-vs-file key drift stays recorded, never merged.
- **OD-53-3 = Option A:** binding = current frozen candidate + latest complete re-audited core + exact current gate-eligible verdict + current autonomy-policy digest + policy/checklist digests + code-owned `slice53.production_preapproval_conditions.v1` (fixed conditions: future production remains forbidden unless the exact binding is current, all 13 gates pass at use, pre-approval is current, policy permits, and Slice 55 authorizes the transition). No free-form conditions; any binding change requires a new request.
- **OD-53-4 = Option A:** requester is request-authenticated `human|service`; approver is a distinct request-authenticated principal with stored actor type `human` and exact policy membership; stated explicitly that actor type is key metadata, never human-presence proof; no self-approval, wildcards, roles, delegation, or channel-acknowledgement approval.
- **OD-53-5 = Option A:** the narrow bearer-authenticated API exactly as proposed, with the mandatory constraints: request bodies carry no actor/approver/release/condition/authority/truth fields; identity only from `TenantContext.actor`; idempotency; generic safe 404/409; no cross-tenant existence oracle; responses carry safe IDs/status/codes only.
- **OD-53-6 = Option A:** immutable requests/attestations + append-only `revoked|superseded` lifecycle events with linear-chain DB proofs; the newest request for the current binding wins even while pending/rejected/cancelled; revocation by a current policy-listed authenticated approver; no mutation of decided rows.
- **OD-53-7 = Option A:** approved attestations expire ≤24 hours after resolution — recorded explicitly as a coordinator-selected security posture, not a source-derived fact; UTC `now` injectable; production non-response stays pending/blocking forever; no `proceeded_by_policy`, timeout, notification, or escalation synthesizes approval; no escalation-chain field is fabricated.
- **OD-53-8 = Option A:** the five normalized append-only tables with generated row-local truth and deferred triggers re-deriving the complete approval graph (policy members, generic approval shape, notification, candidate/core/verdict bindings, separation, lifecycle, counts, digests, eligibility); a production-specific guard on referenced generic approvals; only the confirmed-absent additive composite identity targets on `intake_categories` and `autonomy_policies`.
- **OD-53-9 = Option A:** the 20-rung ladder exactly as plan §8.1; gate name unchanged; the only pass reason is `passed:request_authenticated_preapproval_under_recorded_conditions`; ruleset advances to `slice53.v1`; safe context only.
- **OD-53-10 = Option A:** `can_go_live_autonomously` stays the literal `False`; remove `request_authenticated_a5_preapproval_not_implemented` (the subsystem now exists); retain `a5_gates_not_all_satisfied`; a missing/stale pre-approval manifests as gate-#12 failure keeping A5 false; gate #13 remains sourceless; **only Slice 55 may ever replace the literal** after Slice 54 and control-loop policy design. Option B is explicitly rejected. The full §8.3 hard-false matrix, including the synthetic all-13-pass row, is a mandatory test.
- **OD-53-11 = recommended ruling:** the three contract versions; canonical digests; ≤100 approvers with only subject digests persisted; the stated bounds; the forbidden-content lists for tables/audit/context/errors/logs; caller truth fields fail closed; downgrade `0052→0051` fails closed with live rows; findings-guard MD5 pinned across the round trip.

Both consequences are explicitly accepted: pre-approvals are perishable (≤24h) authority requiring re-approval near use, and the narrow mutating API exists solely because request-authenticated identity lives at the bearer boundary.

---


## 0. Honesty crux

### 0.1 The central tension, without euphemism

The existing identity tier proves a narrow fact: a request presented an active bearer API key bound to a stored principal. The code explicitly says `request_authenticated` is key custody, **not** a human signature, approval-matrix authority, or evidence-pack signer, and that the tier never authorizes go-live (`app/identity.py:3-12`; `app/api/auth.py:34-53`; `migrations/versions/0026_request_auth_identity.py:7-24`).

At the same time, Appendix B gate #12 requires production deployment to be “explicitly pre-approved under stated conditions,” the roadmap assigns that work to Slice 53, and the second no-go reason is literally `request_authenticated_a5_preapproval_not_implemented` (`Spec:2981-2997`; `Roadmap:519-529`; `app/release/production_autonomy.py:45-49,65-68`). Those sources do not create a verified-human tier. They require the narrower request-authenticated pre-approval the project actually designed.

Subject to OD-53-1, this plan proposes this exact claim:

> Two distinct request-authenticated principals, acting through the application trust boundary, requested and approved one production-scoped action; the approver matched an exact member of a recorded, structurally validated but caller-supplied policy; and the attestation is DB-bound to one exact current frozen candidate, re-audited evidence-pack core, current gate-eligible release verdict, code-owned conditions, and immutable lifecycle.

That is a **request-authenticated pre-approval under recorded conditions**. It is not a human signature, verified human authority, production command, or go-live authorization. Passing gate #12 removes the named “not implemented” blocker because the subsystem exists; it does not weaken the identity doctrine and does not make production reachable in this slice (`Spec:463-485`; `Roadmap:519-545`; `app/identity.py:5-12`).

### 0.2 Truth tiers

| Tier | Slice-53 example | Proves | Does **not** prove |
|---|---|---|---|
| **REPORTED / caller-supplied** | Template-20 policy values, `approvers`, template-23 checklist values | What canonical project declarations say | Real-human identity, organizational authority, or consent |
| **REQUEST-AUTHENTICATED / app-stamped** | Subjects derived by `actor_fields()` from `TenantContext.actor` | Possession of an active API key bound to that principal at the app request boundary | Human signature, role truth, approval authority, or future custody |
| **SYSTEM-DERIVED** | Strict parsing, digests, membership, currentness, expiry, gate reason | Deterministic computation under named contracts | External authority or permission to deploy |
| **DB-PROVEN** | Composite FKs, exact release/evidence/approval bindings, distinct recorded subjects, immutable history | Relational invariants and history enforced at commit | Bearer possession by a human; tenant transactions set a tenant GUC, not an independently verified actor GUC (`app/tenancy.py:41-61`) |
| **GATE-INFERRED** | `passed:request_authenticated_preapproval_under_recorded_conditions` | Gate #12's ruled evidence predicate is current | A5 satisfaction, go-live, or deployment authority |
| **NOT PROVEN** | Human signature, verified corporate role, production access, gate #13, deployment success | Nothing here | All remain prohibited claims |

“Verified” may describe only the **application-authenticated request path plus DB-bound evidence chain**. It must never become “verified human,” “signed approval,” or “verified organizational authority.”

### 0.3 Why the generic approval row is insufficient

Current approvals carry dual provenance and the repository refuses app-observed self-approval (`app/models/approval.py:1-8,54-62,79-93`; `app/repositories/approvals.py:64-83,172-195`). But:

1. provenance is app-stamped, not FK-bound to an authentication event (`app/identity.py:10-12`);
2. DB CHECKs constrain vocabulary but do not prove bearer possession (`app/models/approval.py:54-62`);
3. self-approval refusal is repository logic, not a DB constraint (`app/repositories/approvals.py:172-195`);
4. Slice-33 notification proves routing facts only; delivery/acknowledgement is not approval (`app/models/approval_notification.py:1-8`; `CLAUDE.md:250-268`);
5. Slice 33 deliberately did not read `human_approval_policy` (`app/approvals/channels/routing.py:1-6`);
6. gate #12 consumes no exact approval and has no pass branch (`app/release/production_autonomy.py:434-440`).

Therefore a generic approved row, empty approver list, delivery event, unverified label, or caller boolean never satisfies gate #12.

### 0.4 Non-vacuity and non-authorization

- Missing frozen candidate, complete re-auditable core, current gate-eligible verdict, valid policy, exact membership, distinct request-authenticated actors, or current attestation fails closed (`Spec:1760-1770,2251-2271,2996`; templates 20/23).
- Production non-response remains blocking; no timeout, notification, acknowledgement, or safe assumption synthesizes approval (`Spec:1797-1811`; approval policy template:11-16; `app/approvals/states.py:65-89`).
- Gate #12 passing does not satisfy A5 unless all 13 gates pass; gate #13 remains sourceless here (`app/release/production_autonomy.py:43-49,95-113`; `Roadmap:531-545`).
- No production adapter, broker action, control-loop transition, or production credential is added.

---

## 1. Verified baseline and source findings

### 1.1 Repository state verified before drafting

- `git status --porcelain` returned no entries.
- `git branch --show-current` returned `main`.
- local branches contained only `main`; remote branches contained only `origin/main` plus Git's symbolic `origin` entry.
- `HEAD` and `origin/main` both resolved to `d84f584e3b4edb3555a5c1e60b3e24b610235fe7`.
- `migrations/versions/0051_rollback_verifications.py:19-20` identifies `0051` after `0050`; no later migration exists.
- `app/release/production_autonomy.py:58` is `slice52.v1`; `app/intake/readiness.py:45` is `slice20.v1`.
- Slice 53 is the roadmap's sole next marker (`Roadmap:519-529,659-665`).
- no Slice-53 plan, implementation, migration, test, feature branch, or worktree change existed at orientation.

Creating this file makes `.planning/SLICE-53-PLAN.md` the sole intended worktree change. The recorded 1014 Docker-free / 815 DB-backed counts are merged Slice-52 history, not tests rerun for this plan (`CLAUDE.md`, Slice-52 paragraph; `Roadmap:507-517`).

### 1.2 What the sources actually require

1. A4 requires explicit human approval; A5 production is conditional on all pre-approved gates, and the action matrix says production deploy needs human approval or a pre-approved A5 gate (`Spec:457-485`). This slice implements only the pre-approved-gate evidence path.
2. The production UX is formal release approval with a go-live evidence pack (`Spec:1760-1770`). This grounds exact Slice-49/50 binding but defines no API, expiry, signer scheme, or table.
3. A non-responsive production approver blocks (`Spec:1797-1811`; approval policy template:11-16). The spec example names `production_deployment`; the file names `production`. That drift is not silently merged.
4. §24.1 requires approvals complete and separately requires authority for risk acceptance (`Spec:2251-2285`). Slice 53 does not upgrade risk-acceptance authority.
5. Appendix B #12 requires explicit pre-approval under stated conditions (`Spec:2981-2997`); it does not make channel delivery or policy presence sufficient.
6. Template 20's actual fields are `approval_channel`, `daily_digest_time`, `batch_low_risk_questions`, `realtime_for`, four non-response keys, and `approvers`; its channel value is a pipe-placeholder and `approvers` is empty (approval policy template:1-16). It is a template, not live authorization.
7. Template 23 has five empty domain sections and four governance requirements (go-live checklist template:1-11). Empty sections cannot be invented into conditions.

### 1.3 Existing primitives to extend, not fork

| Primitive | Current proof | Limit | Slice-53 use |
|---|---|---|---|
| Slice-4 approval | Tenant/project request, explicit production tier, app transition, event history | Mutable row; no release/core/verdict binding | Reuse operational workflow; never gate alone |
| Slice-27 identity | Active key resolves tenant/principal/type; app stamps provenance | Key custody only; no signature/authority | Require real authenticated contexts and narrow label |
| Slice-33 channel | Production tier realtime dashboard + immutable routing facts | Delivery is not approval; no policy read | Require ruled notification as workflow evidence only |
| Template-20 category | Sourced structured project data | Presence-only/non-authorizing today (`app/intake/categories.py:32-63`) | Strictly parse/snapshot recorded policy if ruled |
| Slice-49 core | Immutable exact-candidate core and digests (`app/models/evidence_pack.py:160-245`) | Bounded assembly, not readiness/authority | Re-audit and bind exact bytes/digests |
| Slice-50 verdict | DB-bound generated decision/eligibility (`app/models/release_verdict.py:97-223`) | Known-issue disposition, not approval | Require exact current gate-eligible verdict |
| A5 evaluator | 13 gates, two-reason tuple, literal hard-false | Gate #12 stub only | Change gate #12; rule no-go transition |

The new store is a release-bound append-only sidecar around the existing approval engine, not a fork.

## 2. Scope and non-goals

### 2.1 In scope, contingent on rulings

1. Strict projections over canonical template-20/template-23 data with recorded provenance/digests.
2. A request bound to one current frozen candidate, re-audited core, current verdict, autonomy policy, recorded approval policy, and code-owned condition contract.
3. Reuse of `request_and_notify_approval` with `deploy_production`, `production`, explicit approval, code-owned subject, and realtime dashboard notification.
4. Request-authenticated resolution with exact policy membership and separation.
5. Append-only policy, request, attestation, and revocation/supersession evidence with RLS ENABLE+FORCE, composite FKs, DB guards, bounded fields, and safe audit.
6. Content/binding currentness and ruled expiry/non-response behavior.
7. Gate #12 ladder, `slice53.v1`, and ruled second-no-go change while all current states stay non-authorizing.
8. Pure/DB tests, direct-SQL attacks, audit sentinel, migration round trip, findings-guard pin, and golden A5 matrix.

### 2.2 Explicit non-goals

- No gate #13 (Slice 54), §23.3 loop (Slice 55), deploy decision, production connector, deployment, rollback action, merge, resource mutation, or production credential (`Roadmap:531-553`).
- No human-signature, WebAuthn, IdP, legal identity, role directory, authority connector, pack signer, or non-repudiation tier.
- No claim `actor_type='human'` proves a human was present (`app/models/tenant_api_key.py:23-49`).
- No risk-acceptance authority change or new `passed_with_limitations` path.
- No evidence-core mutation, verdict rewrite, signature, canonical-schema change, free-form condition language, or caller truth fields.
- No generic approval change for non-production actions and no readiness change.
- No A5 gate other than #12 changes.

---

## 3. Proposed semantics

Everything here is **PROPOSED** pending §4.

### 3.1 Recorded policy, not verified authority

Recommended v1 validates current same-project `human_approval_policy` and `go_live_checklist`, then appends an immutable normalized snapshot stamped `caller_supplied_unverified_structured_approval_policy`. Validation never upgrades source authority.

Gate-bearing use recommends: exact shipped field set; concrete `dashboard`; `production_deployment` in `realtime_for`; `non_response_policy.production='block_until_approval'`; non-empty unique bounded `approvers` interpreted as exact principal subjects because no role binding exists; exact shipped template-23 governance codes; no unknown/secret/free-form/truth keys. Exact-subject interpretation is a conservative **inference** for OD-53-2.

### 3.2 Exact release and stated-condition binding

Recommended requests derive only from DB-loaded current state:

1. latest current frozen candidate;
2. latest complete core re-audited through the real stored-byte/child/checkpoint path;
3. latest successful current same-candidate/core gate-eligible verdict;
4. current A5 autonomy policy with `deploy_production` not disabled and mandatory under the matrix (`Spec:463-490`; `app/policy/matrix.py:36-71,76-122`);
5. current ruled policy/checklist snapshot;
6. code-owned `slice53.production_preapproval_conditions.v1`: future production remains forbidden unless the exact release binding is current, all 13 gates pass at use, preapproval is current, policy permits, and Slice 55 authorizes the transition.

No evidence bytes, tenant prose, policy YAML, issue detail, or identities enter audit/A5 context. Callers cannot weaken conditions.

### 3.3 Workflow and separation

1. Authenticated requester asks the dedicated service for current binding; caller IDs are at most optimistic assertions.
2. Service snapshots policy, creates exact sidecar request, and calls Slice-33 request+notify in one transaction.
3. Distinct authenticated resolver uses dedicated production resolution; generic approval transition plus policy membership plus sidecar attestation commit atomically.
4. Notification proves routing only. Authenticated decision plus sidecar is evidence.
5. New pending/rejected/cancelled request supersedes older passes for selection.
6. Revocation/supersession appends history and executes nothing.

### 3.4 Currentness

Latest-wins `(created_at DESC, id DESC)` for the exact current binding is recommended. Any newer candidate/core/verdict/policy/autonomy/contract, newer request (including pending/rejected), expiry, revocation, supersession, or graph inconsistency de-currents the attestation. Other A5 evidence remains independently evaluated; the preapproval never freezes an older gate pass or overrides a later failure.

### 3.5 Actor boundary

Recommended v1 requires both actors to be `request_authenticated`, with distinct principal hashes. The approver must exactly match a policy member and have stored actor type `human`; requester may be `human|service`. Actor type remains key metadata, never human-presence proof. No wildcard, role, group, substring, case-fold, delegation, or “any admin” match.

---

## 4. Open decisions requiring coordinator ruling

No implementation may begin until every OD below has a final ruling bound verbatim into this plan.

### OD-53-1 — What makes request authentication gate-eligible?

**Option A — recommended:** use the existing app-stamped key-custody tier narrowly. Request and resolution require real `TenantContext.actor` values; both provenance fields are `request_authenticated`; the sidecar proves binding, membership, and separation. Wording always says key custody under recorded policy. Direct-SQL tests prove relational guards, not cryptographic identity.

**Option B:** add a DB-bound authentication-assertion subsystem first. Stronger, but requires a new least-privilege resolver/attestation flow and likely authenticated write API; it materially expands the slice and still is not a human signature.

**Option C:** require a future human-signed/connector-verified authority tier. Most conservative, but gate #12 remains no-pass and Slice 53 does not meet the roadmap goal.

### OD-53-2 — What recorded policy is authoritative?

**Option A — recommended:** strict `slice53.production_approval_policy.v1` projection over current canonical template-20 and template-23 data. Require concrete dashboard channel, realtime production routing, production block-on-nonresponse, exact shipped governance codes, and non-empty `approvers` interpreted as exact principal subjects. Snapshot normalized values with `caller_supplied_unverified_structured_approval_policy`.

**Option B:** code-owned authority matrix only. Rejected unless another source answers who may approve.

**Option C:** treat approver entries as roles and add role→principal binding. More expressive, but no such verified binding exists today.

The shipped placeholder channel and empty approvers never pass as live policy. The spec-example/template key drift remains recorded; v1 follows the checked-in file plus a code-owned semantic contract.

### OD-53-3 — What release and stated conditions are approved?

**Option A — recommended:** current frozen candidate + latest complete re-audited core + exact current gate-eligible verdict + current autonomy-policy digest + policy/checklist digest + code-owned condition hash. Fixed conditions require all 13 gates/current preapproval/policy at future use. No free-form conditions; any binding change requires a new request.

**Option B:** candidate only. Rejected as too weak for §18.2's evidence-pack release pattern.

**Option C:** also snapshot every non-#12 A5 gate result. Stronger coupling, but daily Slice-51 evidence would force repeated approval and it risks circular semantics; exact included gates must be ruled.

### OD-53-4 — Who may request and approve?

**Option A — recommended:** requester is request-authenticated `human|service`; approver is a distinct request-authenticated principal with stored actor type `human` and exact subject membership. Explicitly state actor type is not human-presence proof.

**Option B:** both stored actor types must be `human`. Stricter, but prevents a release-manager service preparing the request.

**Option C:** any two distinct request-authenticated principals. Rejected unless the coordinator accepts service-key approval from a caller-declared list.

No option permits self-approval, fallback labels, wildcard membership, or channel acknowledgement as approval.

### OD-53-5 — What workflow surface exists?

**Option A — recommended:** narrow bearer-authenticated request/approve/reject/cancel/revoke endpoints plus safe current-status GET, all delegating to one service and the existing dashboard channel. This roots the tier at the real API boundary; no endpoint accepts truth fields or deployment commands.

**Option B:** internal service/repository only. Smaller, but future callers must still prove a real authenticated context; tests constructing actors are not production request evidence.

**Option C:** generic approval mutation endpoints. Rejected because they can bypass release-binding orchestration.

If A is ruled: idempotency, generic safe 404/409, no cross-tenant existence oracle, bounded responses, and no raw policy/evidence are mandatory.

### OD-53-6 — What lifecycle/latest-wins rule applies?

**Option A — recommended:** immutable requests/attestations plus append-only `revoked|superseded` events. Newest request for current binding wins even if pending/rejected/cancelled; no fallback. A current policy-listed authenticated approver may revoke; a later approval explicitly supersedes the prior one.

**Option B:** mutate approval to revoked. Rejected because it erases decision state.

**Option C:** generic approval status alone. Rejected because its enum has no revocation or release currentness.

### OD-53-7 — What expiry and non-response rule applies?

**Option A — recommended, conservative inference:** approved attestations expire no more than 24 hours after resolution; UTC `now` is injectable. The 24-hour cap is a coordinator-selected security posture, **not** inferred from low/medium non-response timing.

**Option B:** content/binding currentness only; no TTL because §18.2/template 20 define none. Source-honest, but stable approval can persist indefinitely.

**Option C:** caller/policy expiry. Rejected unless template 20 is explicitly version-extended; arbitrary validity is unsafe.

Under every option, production non-response stays pending/blocking. No `proceeded_by_policy`, safe assumption, notification, or timeout approves production (`Spec:1797-1811`; `app/approvals/states.py:65-89`). The shipped template has no escalation-chain field, so none is fabricated.

### OD-53-8 — How is stored truth made resistant to forged rows?

**Option A — recommended:** five normalized append-only tables (§6), generated row-local truth, and deferred triggers re-deriving policy members, generic approval/action/tier/status/provenance, notification, candidate/core/verdict, separation, lifecycle, counts, digests, and eligibility. Add a production-specific guard on referenced generic approvals. Preserve the limit that DB proves recorded provenance, not bearer custody under OD-53-1 A.

**Option B:** one JSON `production_approvals` row. Rejected: completeness and binding stay caller-shaped.

**Option C:** application validation only. Rejected for gate-bearing authority evidence.

Direct-SQL tests reject malformed/forged evidence graphs but must not claim resistance to a DB superuser.

### OD-53-9 — What gate ladder and pass reason ship?

**Option A — recommended:** §8.1's ordered ladder ending only in `passed:request_authenticated_preapproval_under_recorded_conditions`; gate name unchanged; safe context only; ruleset `slice53.v1`.

**Option B:** approved/unapproved boolean. Rejected because it hides missing policy, identity tier, stale binding, revocation, and inconsistency.

No reason may say `human_approved`, `verified_human`, `signed`, `authorized_to_deploy`, or `go_live_approved`.

### OD-53-10 — What happens to hard-false and the no-go tuple?

**Option A — recommended and roadmap-aligned:** keep `can_go_live_autonomously` literal `False`; remove `request_authenticated_a5_preapproval_not_implemented` because the subsystem exists; retain `a5_gates_not_all_satisfied`. Missing preapproval is gate #12 failure and keeps A5 false. Gate #13 is still sourceless. Slice 55 alone may replace the literal after Slice 54/control-loop policy (`Roadmap:531-553`).

**Option B:** compute `a5_satisfied AND current_preapproval`. False now, but becomes reachable after Slice 54 before the roadmap's Slice-55 loop.

**Option C:** keep literal false and conditionally keep/rename a second evidence-state reason. More diagnostic, but the stale “not implemented” code cannot survive implementation.

All options preserve `app/identity.py` doctrine.

### OD-53-11 — Contracts, caps, audit, and downgrade

**Recommended ruling:**

- contracts `slice53.production_approval_policy.v1`, `slice53.production_preapproval_conditions.v1`, `slice53.production_preapproval.v1`;
- canonical SHA-256 `sha256:` digests; sorted-key UTF-8 canonical JSON without insignificant whitespace;
- ≤100 approvers; source principal 1…255 bytes but persist only digest in new tables; codes/keys ≤128; refs ≤500; all required values non-blank;
- no raw policy, principal, API-key data, evidence bytes, verdict detail, note/reason prose, condition prose, recipient, URL, credential, or tenant content in new tables/audit/context/errors/logs;
- caller `approved|verified|trusted|eligible|current|passed|gate|authority|human_signed` fails closed;
- downgrade `0052→0051` fails closed while any Slice-53 row exists;
- `release_findings_guard()` stays MD5 `808036faf2660d6810aeca4342e6f1ac` across the round trip (`tests/test_rollback_verifications.py:516`; `.planning/SLICE-52-PLAN.md:489`).

---


## 5. Proposed modules and workflow

### 5.1 `app/release/production_approval.py`

Proposed pure responsibilities:

- validate ruled template-20/template-23 projections;
- canonicalize policy/checklist/release/conditions and hash subjects;
- validate exact membership and distinct actors;
- derive typed attempt, attestation, lifecycle, expiry, and gate reason codes;
- reject unknown/caller truth fields;
- emit safe audit/A5 projections;
- never call a connector, execute deployment, or decide human identity.

### 5.2 `app/release/production_approval_service.py`

One authoritative service owns request, resolution, revocation, and current evidence. It composes rather than bypasses `ApprovalRepository`, Slice-33 `request_and_notify_approval`, the real evidence-pack re-audit, current release-verdict resolution, autonomy policy/matrix checks, and the new repository. Generic production approvals without this sidecar remain non-gating.

### 5.3 Optional API under OD-53-5 A

Proposed narrow surface:

```text
POST /api/projects/{project_id}/production-preapprovals/requests
POST /api/projects/{project_id}/production-preapprovals/{request_id}/approve
POST /api/projects/{project_id}/production-preapprovals/{request_id}/reject
POST /api/projects/{project_id}/production-preapprovals/{request_id}/cancel
POST /api/projects/{project_id}/production-preapprovals/{attestation_id}/revoke
GET  /api/projects/{project_id}/production-preapprovals/current
```

Every mutation requires `require_tenant`; identity comes only from `TenantContext.actor`. Request bodies carry no actor, approver, release/core/verdict ID, condition, authority, status, or truth field. Responses contain safe IDs/status/reason/timestamps, never principal/policy/evidence content.

---

## 6. Additive data model and expected migration `0052`

`0052_production_preapprovals.py` is an **inference** from verified head `0051` and roadmap direction (`Roadmap:519-525`). It is additive-only; no historical approval is relabelled or backfilled into gate evidence.

All new tenant tables use RLS ENABLE+FORCE, exact tenant policies, composite same-project FKs with `RESTRICT`, append-only UPDATE/DELETE/TRUNCATE guards, bounded CHECKs, least-privilege grants, and deterministic `(created_at DESC,id DESC)` ordering.

### 6.1 `production_approval_policy_versions`

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
human_approval_category_id UUID NOT NULL
go_live_checklist_category_id UUID NOT NULL
policy_contract_version TEXT NOT NULL
source_provenance TEXT NOT NULL
policy_digest TEXT NOT NULL
checklist_digest TEXT NOT NULL
approval_channel TEXT NOT NULL
production_realtime BOOLEAN generated/re-derived
production_nonresponse_code TEXT NOT NULL
governance_requirements_digest TEXT NOT NULL
approver_count SMALLINT generated/re-derived
created_at TIMESTAMPTZ NOT NULL
```

Only normalized safe scalars/digests are copied. Raw intake data stays in its existing source row.

### 6.2 `production_approval_policy_approvers`

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
policy_version_id UUID NOT NULL
ordinal SMALLINT NOT NULL
principal_subject_hash TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL
```

Unique `(policy_version_id,ordinal)` and `(policy_version_id,principal_subject_hash)`. Deferred guards rederive exact count/digest; omitted, duplicate, extra, reordered, or blank members fail. No raw principal string is copied.

### 6.3 `production_preapproval_requests`

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
release_candidate_id UUID NOT NULL
evidence_pack_id UUID NOT NULL
release_verdict_id UUID NOT NULL
policy_version_id UUID NOT NULL
autonomy_policy_id UUID NOT NULL
generic_approval_id UUID NOT NULL
approval_notification_id UUID NOT NULL
preapproval_contract_version TEXT NOT NULL
condition_contract_version TEXT NOT NULL
condition_contract_hash TEXT NOT NULL
release_binding_digest TEXT NOT NULL
core_content_hash TEXT NOT NULL
issue_binding_digest TEXT NOT NULL
source_set_digest TEXT NOT NULL
traceability_digest TEXT NOT NULL
verdict_input_digest TEXT NOT NULL
verdict_contract_hash TEXT NOT NULL
autonomy_policy_digest TEXT NOT NULL
requester_subject_hash TEXT NOT NULL
requester_actor_type TEXT NOT NULL
requester_provenance TEXT NOT NULL
requested_at TIMESTAMPTZ NOT NULL
created_at TIMESTAMPTZ NOT NULL
```

Generic approval must be same tenant/project, `deploy_production`, `production`, explicit, pending at creation, code-owned subject ref, and request-authenticated. Notification must bind the same approval/project/tenant and satisfy ruled realtime/dashboard status.

### 6.4 `production_preapproval_attestations`

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
request_id UUID NOT NULL
generic_approval_id UUID NOT NULL
policy_version_id UUID NOT NULL
release_candidate_id UUID NOT NULL
evidence_pack_id UUID NOT NULL
release_verdict_id UUID NOT NULL
approver_subject_hash TEXT NOT NULL
approver_actor_type TEXT NOT NULL
approver_provenance TEXT NOT NULL
approved_at TIMESTAMPTZ NOT NULL
valid_from TIMESTAMPTZ NOT NULL
expires_at TIMESTAMPTZ NULL/NOT NULL per OD-53-7
attestation_result TEXT generated/re-derived
identity_separation_ok BOOLEAN generated/re-derived
policy_membership_ok BOOLEAN generated/re-derived
gate_eligible_at_creation BOOLEAN generated/re-derived
created_at TIMESTAMPTZ NOT NULL
```

Exactly one per request. The generic row must be approved by the same resolver/provenance/time; approver must be an exact policy member; subjects differ; all bindings match. Creation eligibility never freezes future currentness.

### 6.5 `production_preapproval_lifecycle_events`

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
attestation_id UUID NOT NULL
previous_event_id UUID NULL
event_type TEXT NOT NULL  -- approved_anchor | revoked | superseded
actor_subject_hash TEXT NOT NULL
actor_type TEXT NOT NULL
actor_provenance TEXT NOT NULL
reason_code TEXT NOT NULL
created_at TIMESTAMPTZ NOT NULL
```

Composite self-FK/deferred guards prove one linear chain, legal transitions, no duplicate head, and same project/tenant. Rejection/cancellation lives on the generic approval/newest request and creates no positive attestation.

### 6.6 DB-authoritative invariants

Migration must enforce at least:

1. same tenant/project across intake categories, policy/members, candidate/core/verdict, approval/notification, request/attestation/lifecycle;
2. exact candidate/core/verdict relationship and stored digest equality;
3. only complete cores and exact gate-eligible verdicts seed requests;
4. exact policy/checklist contract and nonempty exact child set;
5. generic approval action/tier/explicit/status/provenance/subject shape;
6. notification same approval, realtime, dashboard, and ruled status;
7. ruled provenance/actor shapes, distinctness, and exact member digest;
8. attestation iff ruled successful approval graph exists; caller cannot set truth;
9. linear legal lifecycle, bounds, time ordering, and expiry;
10. later mutation of referenced generic approval revalidates or fails;
11. RLS isolation and append-only history;
12. downgrade refusal with live rows and no findings-guard change.

Cross-row truth belongs in DEFERRABLE constraint triggers; row-local truth in CHECKs/generated columns. Repository validation is defense in depth.

### 6.7 Existing-object preservation

- No historical approval/identity/policy/core/verdict relabelling.
- Add only composite identity targets required for same-project FKs: `UNIQUE(id,project_id,tenant_id)` on `intake_categories` and `autonomy_policies` if catalog inspection confirms they remain absent; these constraints change no row meaning (`app/models/intake_category.py:40-64`; `app/models/autonomy_policy.py:26-38`).
- Generic non-production approvals remain compatible.
- Any production-specific trigger is limited to new sidecar references/exact production shape.
- Notifications remain routing facts; no acknowledgement semantic.
- All prior evidence stores/guards remain semantically untouched.
- Findings-guard MD5 is pinned across the full round trip.

---

## 7. Repository/service behavior

### 7.1 Request

1. Require non-null authenticated actor; no fallback label.
2. Resolve current frozen candidate internally.
3. Load/re-audit exact latest complete core.
4. Load exact latest current gate-eligible verdict.
5. Validate current A5 autonomy policy and production matrix decision.
6. Load/validate/snapshot ruled template data.
7. Derive digests/fixed conditions.
8. Create generic production approval + realtime notification via Slice 33.
9. Append exact request in the same transaction.
10. Audit safe metadata after durable insert.

Any failure rolls back partial rows. Failed notification is honest newest state and cannot fall back.

### 7.2 Resolution

1. Require non-null authenticated resolver.
2. Load newest exact request without cross-tenant oracle.
3. Recheck currentness before resolution.
4. Verify separation and exact policy membership.
5. Execute generic transition.
6. Append attestation + anchor event atomically.
7. Let deferred DB guards rederive graph.
8. Audit only safe metadata.

Reject/cancel creates no attestation. Concurrent resolutions yield one winner; others fail closed.

### 7.3 Revocation/current retrieval

Revocation requires ruled authenticated policy authority, appends history, and immediately blocks; it does not edit the generic approval. Newest request wins even while negative/pending.

`latest_current_production_preapproval(project_id,now)` derives current candidate/core/verdict/policy/autonomy/contracts from DB; caller-selected attestations never establish currentness. Safe projection contains only policy/core/verdict presence booleans, status/reason codes, separation/membership/current/expiry booleans, contract versions, and counts—never identities, policy entries, refs, repo/commit, or digests.

### 7.4 Audit surface

Allowed: project/request/attestation/candidate/core/verdict/approval/notification IDs; event/reason/status/provenance/actor-type codes; policy count; separation/eligibility booleans; contract versions.

Forbidden: raw principal or subject hash in audit/A5; key/hash/label/token; policy/checklist/approver list; payload/note/reason/condition prose; evidence/verdict/finding detail; repo/commit/URL/domain/IP/credential/log/body/stack; tenant prose.

Sentinel tests inject unique secret/prose markers through every source/error and prove absence from new rows, audit, context, API, exceptions, and logs.

---

## 8. A5 gate #12 and hard-false boundary

### 8.1 Proposed ordered ladder

Only gate #12 changes, first-match:

1. `insufficient_evidence:no_current_frozen_release_candidate`
2. `insufficient_evidence:no_complete_reauditable_evidence_core`
3. `insufficient_evidence:release_core_reaudit_failed`
4. `insufficient_evidence:no_current_gate_eligible_release_verdict`
5. `insufficient_evidence:release_approval_policy_missing_or_invalid`
6. `insufficient_evidence:release_approval_policy_has_no_exact_approver`
7. `insufficient_evidence:a5_autonomy_policy_missing_or_ineligible`
8. `insufficient_evidence:no_production_preapproval_request_for_current_binding`
9. `insufficient_evidence:latest_preapproval_request_binding_stale_or_inconsistent`
10. `insufficient_evidence:preapproval_requester_not_request_authenticated`
11. `insufficient_evidence:production_approval_notification_missing_or_invalid`
12. `insufficient_evidence:production_preapproval_pending`
13. `insufficient_evidence:production_preapproval_rejected_or_cancelled`
14. `insufficient_evidence:preapproval_approver_not_request_authenticated`
15. `insufficient_evidence:preapproval_approver_not_in_recorded_policy`
16. `insufficient_evidence:preapproval_separation_of_duties_failed`
17. `insufficient_evidence:production_preapproval_revoked_or_superseded`
18. `insufficient_evidence:production_preapproval_expired` (if OD-53-7 A)
19. `insufficient_evidence:production_preapproval_evidence_inconsistent`
20. `passed:request_authenticated_preapproval_under_recorded_conditions`

Context is safe counts/booleans/codes/contracts only.

### 8.2 Ruleset and unchanged behavior

- Advance `slice52.v1` → `slice53.v1`; gate name remains `production_deploy_preapproved_under_conditions`.
- Gates #1-#11/#13 are identical for identical inputs under golden matrix.
- Gate #13 remains `no_evidence_source:emergency_stop` (`app/release/production_autonomy.py:1126`; `Spec:2997`; `Roadmap:531-541`).
- `a5_satisfied` remains all-13 conjunction and is false for current repository states.
- readiness stays byte-stable `slice20.v1`.

### 8.3 Explicit hard-false matrix

| State | #12 | #13 | A5 | Can go live |
|---|---:|---:|---:|---:|
| no request | fail | fail | false | **false** |
| unverified approval | fail | fail | false | **false** |
| pending/non-response | fail | fail | false | **false** |
| self/wrong approver | fail | fail | false | **false** |
| rejected/cancelled/revoked/expired | fail | fail | false | **false** |
| stale candidate/core/verdict/policy | fail | fail | false | **false** |
| current authenticated preapproval | pass | fail | false | **false** |
| synthetic report with all 13 marked passed | pass | synthetic pass | synthetic true | **false under OD-53-10 A** |

The synthetic row defends the literal; it does not claim gate #13 is currently constructible. Slice 55 owns a future computed conjunction (`Roadmap:543-553`).

---

## 9. Test-first implementation plan

If separately authorized, implementation uses red→green TDD. This plan creates/runs no tests.

### 9.1 Pure tests — proposed `tests/test_production_preapprovals.py`

1. Exact template field sets; pipe-placeholder rejected as live policy.
2. Dashboard/realtime production/block-until-approval/exact governance/nonempty approvers required.
3. Missing/extra/changed template keys and truth fields fail.
4. Empty/duplicate/blank/oversized/wildcard/role-shaped/mixed-case/>100 approvers fail under recommended contract.
5. Deterministic policy/checklist/release/condition digests; raw content absent from safe projections.
6. Caller truth keys fail at every nesting level.
7. Fixed conditions cannot omit all gates, current binding, autonomy, lifecycle, or Slice-55 boundary.
8. Any binding component change changes digest.
9. Actor provenance/types/distinctness and exact membership matrix.
10. No substring/case-fold/role/group/wildcard/fallback match.
11. Notification and approval negative states produce exact outcomes.
12. Lifecycle one-way; no self-clear/history rewrite.
13. Injected UTC expiry before/equal/after, naive time, cap/cap+1.
14. Newest negative/pending request supersedes old pass; deterministic id tie-break.
15. Every ladder rung/precedence; only rung 20 passes.
16. Pass reason says request-authenticated/recorded conditions, never human/signed/authorized.
17. Golden A5 matrix changes only #12/version.
18. §8.3 hard-false matrix, including synthetic all-pass object.
19. Identity doctrine unchanged.
20. Safe projections exclude sentinels/forbidden fields.

### 9.2 Service/API tests

1. Request requires real authenticated actor; fallback refused.
2. Caller IDs cannot replace current DB selection.
3. Bad core/verdict/autonomy/policy refuses before generic request.
4. Exact production action/tier/explicit/subject + Slice-33 path.
5. Notification failure cannot attest.
6. Approve requires second authenticated exact member/current request.
7. Generic approve + attestation + anchor atomic; injected failure rolls back.
8. Generic-only/sidecar-only never gates.
9. Self/unverified/service approver (if ruled)/nonmember/stale refused.
10. Reject/cancel no attestation; revoke blocks.
11. Concurrent resolution/revocation races fail closed.
12. Cross-tenant/nonexistent safe responses; no oracle.
13. No deployment/broker/connector/control-loop call.
14. Sentinel on success and every negative/exception path.

### 9.3 DB-backed/direct-SQL tests

1. Captured-exit `0051→0052→0051→0052` round trip.
2. RLS ENABLE+FORCE, least grants, mutation/truncate refusal.
3. Every cross-tenant/project FK combination fails.
4. Missing/extra/duplicate/reordered members fail deferred commit.
5. Forged policy counts/digests/routing/nonresponse/checklist/provenance fails.
6. Forged approval action/tier/explicit/subject/provenance/status/time fails binding.
7. Direct-SQL self-approval fails.
8. Wrong/nonmember/mismatched actor fails.
9. Missing/wrong/failed notification cannot be eligible.
10. Wrong candidate/core/verdict/digests/eligibility fails.
11. Caller-set truth/generated values impossible or rejected.
12. Attestation without exact approval fails; generic-only stays non-gating.
13. Later invalidating generic approval mutation fails.
14. Lifecycle fork/cycle/un-revoke/illegal order fails.
15. Newest negative state supersedes old pass.
16. Candidate/core/verdict/policy/autonomy/contract changes de-current.
17. RLS prevents evidence/count/member/status leakage.
18. Audit sentinel excludes identity/key/policy/note/evidence/prose.
19. Existing approval/channel tests stay green.
20. Findings guard MD5 exact every migration leg.
21. Golden DB A5 changes only #12/version; #13 no-source.
22. No-go tuple/literal exactly match OD-53-10 in every state.
23. Downgrade refuses with rows; succeeds after explicit cleanup.

Direct-SQL reporting must say it proves relational guard resistance. Under OD-53-1 A it does not prove DB-witnessed bearer custody.

### 9.4 Eventual pre-PR verification

```text
git diff --check
ruff
make test
make test-db
migration 0051→0052→0051→0052
```

Complete output and explicit exit code are mandatory; truncated/interrupted/exit-code-less output is failed, never green.

---

## 10. Prospective file-touch map

### New

- `app/release/production_approval.py`
- `app/release/production_approval_service.py`
- `app/models/production_preapproval.py`
- `app/repositories/production_preapprovals.py`
- `migrations/versions/0052_production_preapprovals.py`
- `tests/test_production_preapprovals.py`
- narrow API router/schemas only under OD-53-5 A

### Modified narrowly

- `app/repositories/approvals.py` — compose production path without generic shortcut.
- approval-channel service only if same-transaction hook mechanically needed; routing unchanged.
- `app/release/production_autonomy.py` — gate #12/version/exact OD-53-10 change only.
- `app/repositories/production_autonomy.py` — safe current projection only.
- model/repository/API wiring mechanically required.
- this plan — bind rulings before implementation.

### Byte-stable / semantically untouched

- `app/intake/readiness.py` (`slice20.v1`)
- `app/identity.py` doctrine/tier meanings
- `app/policy/matrix.py` mandatory production rule
- canonical templates 20/23
- evidence core/schema and verdict decision/authority semantics
- cost/rollback/deploy/monitoring/connectors and every other A5 gate
- findings guard and layered rules

---

## 11. Must NOT claim

1. `request_authenticated` is human signature, verified-human presence, legal identity, non-repudiation, or approval-matrix authority.
2. `actor_type='human'` proves a human held the key.
3. caller-declared approvers have independently verified organizational authority.
4. policy presence, empty list, generic approval, delivery, acknowledgement, or non-response is preapproval.
5. app-stamped approval alone is DB proof of bearer custody under OD-53-1 A.
6. gate #12 pass authorizes deploy, satisfies A5, proves completeness, or makes go-live reachable.
7. this slice implements gate #13, emergency stop, control loop, deploy, or mutation.
8. approval covers changed/different candidate/core/verdict/policy or unknown future evidence.
9. old pass survives newer pending/rejected/revoked/expired/stale state.
10. production non-response may proceed by policy/timeout/escalation/channel.
11. core/verdict is signature or production authority.
12. failed/non-gate-eligible verdict can be preapproved for A5.
13. `passed_with_limitations` or verified risk authority is added.
14. free-form conditions, caller truth, wildcard roles/groups/delegation are supported.
15. removing second implementation blocker makes the first pass.
16. go-live is computed/reachable in Slice 53 under recommended OD-53-10 A.
17. readiness changes from `slice20.v1`.
18. canonical template/prior row/provenance is relabelled.
19. direct SQL proves superuser resistance or human key possession.
20. secrets/identity/policy/prose/evidence are safe to audit because hashed/structured.

---

## 12. Definition of done for future implementation

- reviewer approves plan and coordinator rules OD-53-1…11, bound verbatim before code;
- dedicated github-flow branch; separate plan-binding commit restored;
- additive `0052` round-trips, preserves guards, fails closed with live rows;
- workflow reuses approval/channel without treating either alone as gate evidence;
- exact binding/separation/lifecycle/currentness survives direct-SQL attack;
- identity language stays key-custody-only;
- only gate #12 gains ruled pass under `slice53.v1`;
- no-go/literal behavior exactly follows OD-53-10;
- gate #13/other gates/readiness/findings/evidence/verdict/action surfaces unchanged;
- every §8.3 state remains false;
- full suites/round trip pass with complete output and exit codes;
- `.env` and `.pending-auth-captures.jsonl` never staged;
- implementation PR pauses unmerged for APPROVE/REJECT.

---

## 13. Reviewer gate

Requested verdict: **APPROVE** or **REJECT** this plan only.

APPROVE confirms grounding and scope but does not authorize implementation until all OD-53-1…11 rulings are final and bound. REJECT should cite exact lines/claims and required correction. Until both exist: no branch, code, migration, tests, commit, PR, production action, or Slice-54 work.
