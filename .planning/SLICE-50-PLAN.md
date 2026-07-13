# Slice 50 — Release manager + §24.3 release verdict (completes A5 gate #7) — PLAN v1

**Status:** MERGED — historical record. Implemented via PR #90 (squash commit `4f2012b`); this v1 plan is retained as the approved design rationale for Slice 50.

> **Citation key / Sanad discipline.** `spec:N-M` means numbered lines in
> `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`; bare
> `evidence_pack_schema.json:N-M` means
> `docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json`. Prospective designs are labelled
> **proposed**, **recommended**, or **inference**; they are not reported as existing repository facts.

## Coordinator rulings (final)

OD-50-1 = Option A: the six-value §24.3 enum is authoritative internally (spec_verdict, slice50.release_verdict.v1); a separate, versioned, explicitly lossy canonical projection (slice50.verdict_projection.v1) maps to the immutable four-value schema exactly per the plan's table; the canonical export carries the uncollapsed spec_verdict in the strict verdict_attestation semantic extension; the canonical asset stays byte-identical. Confirmed corollary: a passed_with_limitations outcome lacking eligible accepted-risk evidence has no truthful canonical projection and must not be emitted — OD-50-3/4 route that condition to requires_human_decision.

OD-50-2 = Option A: the verdict's decision scope is the bounded known_bound_issue_disposition over one re-audited core; the scope limitation is explicit in the record, context, and export; passed never means §24.1-whole or deployment permission.

OD-50-3 = Option A: strict canonical-aligned disposition. Resolved/superseded issues non-limiting; any open blocking/hard issue ⇒ failed_blocking_issue; any open non-blocking issue requires exact eligible risk evidence to be a limitation; explicit exact zero-member inventory may pass only under the §3.3 evidence rule (complete re-audited core, matching issue-binding digest, all required inventory present, exact current input digest). An empty store never passes by vacuity.

OD-50-4 = Option A (strict verified-authority), with the consequence explicitly accepted: neither caller_supplied_unverified nor request_authenticated supports a gate-bearing "approved" acceptance; structurally valid records remain diagnostic and drive requires_human_decision; passed_with_limitations is not gate-eligible until a future verified authority tier exists — gate #7 passes only via fully-clean disposition or the ruled zero-member path. No historical row relabelled; no stored provenance meaning altered.

OD-50-5 = Option A: content/binding-based latest-wins (latest frozen candidate → latest core → latest verdict attempt for the exact core+input+contract, (created_at DESC, id DESC)); newer failed/refused attempts supersede older passes; any lifecycle/evidence/contract/candidate change or input-digest mismatch de-currents an old verdict; no wall-clock TTL; history immutable.

OD-50-6 = Option A: requires_human_decision fires only on the exact authority-gap condition and is decision-only (no side effects); not_applicable is never emitted this slice — no applicability primitive exists; caller requests for it are refused.

OD-50-7 = Option A: append-only release_verdict_runs + release_verdicts + release_verdict_issue_results; generated columns own spec_verdict/canonical projection/reason/gate-eligibility; a deferred constraint trigger proves the child set exactly equals the frozen/core-represented binding set; succeeded run ⇔ exactly one attestation; infrastructure failures never masquerade as verdicts.

OD-50-8 = Option A: every successful DB-bound verdict outcome (including failed_*, requires_human_decision) unlocks canonical export of that exact historical pack — export is evidence, not authorization. Export re-audits core + attestation, emits signatures: [] + signature_status='unsigned_signer_tier_not_implemented', replaces verdict_deferred_to_slice_50 only in the export projection with the bounded/non-authorizing limitation, and never touches stored core bytes. Dataclass/caller-shaped attestations refused; only exact same-tenant/project/pack FK loads.

OD-50-9 = recommended ladder: the ten rungs exactly as written in plan §4/OD-50-9; ruleset advances to slice50.v1; gate name unchanged; safe counts/booleans/codes only in context; gates #1–#6 and #8–#13 byte-identical for identical inputs.

OD-50-10 = recommended ruling: the three contract versions, SHA-256 digests, ≤10,000 issue results per attempt, the stated bounds, caller truth-fields fail closed, audit safe-metadata-only per the plan's list, and downgrade 0049→0048 fails closed while any Slice-50 row exists.

## 0. The defining honesty constraint (the crux)

A Slice-50 verdict may be a **deterministic, system-derived decision over one exact frozen release candidate and
one exact, re-audited Slice-49 core assembly**. It is not a human decision, a release-manager signature, a
production approval, a deployment instruction, proof that every issue was discovered, or proof that the release
is ready. The release candidate freezes only declared issue membership, and the evidence pack itself states that
its bounded snapshot does not prove release readiness or issue completeness
(`app/models/release_candidate_issue_binding.py:1-10,30-72`; `app/release/evidence_pack.py:777-824,1041-1048`).

The plan keeps the following truth tiers separate:

1. **REPORTED.** Issue/risk prose, actor labels, approval-matrix names, and most reviewer report content remain
   caller/reviewer assertions. A risk acceptance may be `caller_supplied_unverified` or
   `request_authenticated`; the latter proves actor-bound key custody, **not** a human signature or approval-
   matrix authority (`app/models/risk_acceptance_record.py:1-10,68-112`;
   `app/repositories/risk_acceptance.py:42-85`).
2. **CONNECTOR-OBSERVED / CONNECTOR-VERIFIED / SYSTEM-EXECUTED.** Slice-49 preserves, rather than upgrades,
   the truth tier of each included Slice-43/44/45/46/48 source. A release verdict must not flatten those tiers
   into a generic “verified evidence” claim (`app/release/evidence_pack.py:453-650`;
   `.planning/SLICE-49-PLAN.md:23-69`).
3. **DB-PROVEN.** Composite FKs, frozen candidate membership, trusted finding→issue lineage, exact release-ref
   risk binding, immutable pack bytes, normalized child rows, and append-only history can be proved by the
   database. Those proofs remain bounded to rows that exist (`app/models/release_issue.py:33-100`;
   `app/models/risk_acceptance_record.py:35-112`; `migrations/versions/0048_evidence_packs.py:241-330,503-640`).
4. **ASSEMBLER-DERIVED.** Slice-49 computes inventory status, source/traceability digests, and core hashes under
   `system_assembled_evidence_pack`; even `assembly_status='complete'` means the ruled source inventory is
   complete, not that the evidence universe or release is complete (`app/models/evidence_pack.py:53-157`;
   `.planning/SLICE-49-PLAN.md:58-69`).
5. **SYSTEM-DERIVED RELEASE VERDICT (proposed).** Slice 50 may compute a versioned verdict from repository-loaded,
   re-audited structural evidence and persist it with provenance
   `system_derived_release_verdict`. The database may prove its exact candidate/core/input binding and that the
   verdict was generated by the ruled contract; it cannot prove that the contract’s bounded conclusion is
   universally true. This label and boundary are proposed engineering choices requiring OD-50 rulings.
6. **GATE-INFERRED (proposed).** A5 gate #7 may pass only when the latest gate-bearing verdict for the exact
   current candidate/core/input binding has a coordinator-ruled pass-eligible outcome. That pass means only that
   Appendix-B gate #7’s bounded issue-disposition condition is satisfied. It does **not** mean §24.1 as a whole,
   A5 as a whole, or production authorization is satisfied (`spec:2251-2271,2981-2997`;
   `app/release/production_autonomy.py:59-69,96-114,318-385`).

The core honesty statement is therefore:

> **A verdict is a reproducible decision over known, frozen membership and one immutable evidence snapshot. It
> does not prove issue-set completeness, real-world correctness, human authority, policy permission, or go-live
> readiness.**

### 0.1 Verified repository baseline for this plan

The following was re-verified from files and git before drafting; it is not inherited from a prior handoff:

- `git rev-parse HEAD` and `git rev-parse origin/main` both returned
  `d0805f33245c2c170a8b854432001c6a43ba4013`; the checked-out branch is `main`.
- `git status --porcelain` was empty. Local and remote ref inspection showed only `main` and `origin/main`; no
  feature branch exists.
- `uv run alembic heads` returned `0048 (head)`, and migration `0048` revises `0047`
  (`migrations/versions/0048_evidence_packs.py:1-21`).
- A5 is `slice47.v1`; readiness is `slice20.v1`; both hard no-go reasons are
  `a5_gates_not_all_satisfied` and `request_authenticated_a5_preapproval_not_implemented`
  (`app/release/production_autonomy.py:59-69`; `app/intake/readiness.py:45`).
- The current verified suite counts recorded on `main` are 902 Docker-free and 788 DB-backed
  (`CLAUDE.md:610-628,1275,1378-1379`). No test command was run for this plan-only task.
- Before this deliverable, no `.planning/SLICE-50-PLAN.md`, `release_verdicts` model/repository, Slice-50 test
  file, or migration `0049` existed (verified with `rg --files` and symbol search). The roadmap’s sole current
  next marker is Slice 50 and explicitly says it was not started
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:483-492,659-665`).

These are planning-time observations. Any later implementation must re-run the baseline checks before branching.

---

## 1. Scope and non-goals

### 1.1 In scope after plan approval and all coordinator rulings

1. Add a pure, deterministic release-manager decision module that accepts only code-owned structural views
   loaded from the exact candidate/core snapshot; no caller-supplied verdict, pass, trust, eligibility, or
   completeness flag. The spec assigns release readiness/deployment policy/rollback ownership to a Release
   Manager Agent and schedules a release manager in Phase 6, but this slice proposes a deterministic evaluator,
   not an executing LLM agent (`spec:965-978,2500-2510`; inference requiring OD-50-2).
2. Re-audit one immutable Slice-49 core before decision, bind the decision to the exact same tenant/project,
   frozen candidate, evidence-pack ID, core hash, issue-binding digest, source-set digest, traceability digest,
   audit checkpoint, and versioned verdict contract (`app/models/evidence_pack.py:160-246`;
   `app/repositories/evidence_packs.py:825-910`).
3. Evaluate the candidate’s exact frozen issue membership and each member’s snapshotted disposition, provenance,
   blocker status, and exact risk-acceptance linkage without copying source prose
   (`app/repositories/evidence_packs.py:492-640`; `app/release/evidence_pack.py:129-165,489-540`).
4. Persist append-only verdict attempts, successful verdict attestations, and normalized per-issue structural
   results under tenant RLS. Generated/guarded database logic must own the verdict and gate-eligibility outcome;
   direct SQL must not forge either. Exact table shape is contingent on OD-50-7.
5. Implement the ruled six-value §24.3 internal verdict vocabulary and a separate, explicit projection to the
   immutable four-value canonical evidence-pack schema. The canonical asset remains byte-stable under the binding
   OD-49-1 ruling (`spec:2332-2341,2769-2794`;
   `docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:1-65`;
   `.planning/SLICE-49-PLAN.md:5-9`).
6. Complete the reserved Slice-49 verdict-attestation boundary: load a real DB-bound row, re-audit core plus
   attestation, construct canonical JSON with an explicit unsigned status, validate the strict semantic contract
   and canonical schema, and audit safe export metadata. Core bytes remain unchanged
   (`app/release/evidence_export.py:20-74`; `app/repositories/evidence_packs.py:963-972`;
   `.planning/SLICE-49-PLAN.md:9,392-409`).
7. Advance only A5 gate #7 to its first coordinator-ruled pass branch under proposed ruleset `slice50.v1`.
   Every other gate must serialize identically for identical inputs. Readiness remains byte-stable at
   `slice20.v1`, and both hard no-go reasons remain exact (`app/release/production_autonomy.py:59-69,783-800`).
8. Expected migration `0049` after actual head `0048`. The number and name are an inference from the current
   migration chain, not an existing artifact (`migrations/versions/0048_evidence_packs.py:19-21`).

### 1.2 Non-goals

- No production approval or verified A5 pre-approval; that is roadmap Slice 53. `request_authenticated` remains
  key custody rather than a human signature (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:526-537`;
  `app/identity.py:1-13`).
- No cost forecast (Slice 51), rollback verification (Slice 52), emergency-stop authority (Slice 54), §23.3
  control loop (Slice 55), deployment, post-launch operations, or stabilization
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:495-565`).
- No cryptographic signing, signer tier, OSCAL, auditor access, HTTP download, PDF, or archive; those stay Slice
  60. Canonical export remains explicitly unsigned (`.planning/SLICE-49-PLAN.md:9,21`;
  `app/release/evidence_export.py:106-123`).
- No new issue, finding, risk-acceptance, release-candidate, evidence-pack-core, or audit-checkpoint lifecycle.
  Slice 50 reads and binds existing records; it does not mutate or auto-close them.
- No auto-approval, auto-deployment, auto-resolution, auto-risk-acceptance, auto-supersession, or workflow action.
  `requires_human_decision` is decision-only, following the Slice-41 no-auto-action precedent
  (`CLAUDE.md:442-469`; `.planning/SLICE-41-PLAN.md`).
- No claim that a zero-issue binding set, an empty store, a complete pack, or a passed bounded verdict proves that
  no issue exists. Zero-member behavior is an explicit OD, never vacuous truth.
- No LLM or connector call. No `LLMClient`, agent instance, model route, SCM adapter, PM connector, or network
  path changes.
- No API/router/dashboard addition. Slice-49 export remains internal service/repository behavior
  (`app/repositories/evidence_packs.py:912-972`).
- No mutation of `docs/.../schemas/evidence_pack_schema.json`, `app/intake/readiness.py`, either no-go reason,
  any non-#7 gate, or any pre-existing guard/RLS/grant/generated expression except a strictly necessary
  additive Slice-49 semantic/export extension ruled in OD-50-8.

---

## 2. Current repository truth and the gaps Slice 50 must close honestly

### 2.1 The verdict vocabulary has verified, material drift

Spec §24.3 defines exactly six values and meanings:

| §24.3 value | Spec meaning | Source |
|---|---|---|
| `passed` | Release may proceed under policy | `spec:2332-2337` |
| `passed_with_limitations` | Release may proceed only if limitations are accepted | `spec:2332-2337` |
| `failed_blocking_issue` | Release blocked until critical issues are fixed | `spec:2338` |
| `failed_missing_evidence` | Release blocked because proof is incomplete | `spec:2339` |
| `requires_human_decision` | Release depends on authority decision | `spec:2340` |
| `not_applicable` | System is not intended for production release | `spec:2341` |

The canonical `uaid.evidence_pack.v1.2` asset instead accepts exactly four values:
`passed | passed_with_accepted_risk | failed | blocked`
(`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:53-59`; the spec-embedded copy is
`spec:2769-2794`). Only `passed` is shared verbatim. `passed_with_limitations` and
`passed_with_accepted_risk` are not the same string; the two failure reasons collapse to `failed`; the two
decision/applicability outcomes have no distinct canonical value. This is factual schema drift, not a naming
detail. OD-50-1 must choose the authority and an explicit, versioned, intentionally lossy projection; the
canonical asset may not be modified because OD-49-1 already bound it as immutable
(`.planning/SLICE-49-PLAN.md:7`).

### 2.2 Gate #7 has real structural evidence but deliberately no pass path

The current Slice-47 ladder checks, in order: frozen candidate, non-empty declared membership, trusted finding-
derived issue provenance, release-consistent accepted-issue risk links, then the missing release verdict. Every
rung returns `insufficient_evidence`; the most advanced reason is
`verified_known_issue_set_but_no_release_verdict` (`app/release/production_autonomy.py:318-385`). Its repository
selects the latest frozen candidate deterministically and computes bound total/trusted/untrusted/bridge/accepted
counts through tenant-scoped joins (`app/repositories/production_autonomy.py:163-208`;
`app/repositories/release_candidates.py:99-208`).

The trusted issue path is narrow: one release issue derives from one DB-bound Slice-44 security or Slice-45
shortcut finding, and every bridged shortcut is a hard-refusal blocker. It proves lineage for known rows, never
issue completeness (`app/release/issues.py:53-137`; `.planning/SLICE-47-PLAN.md:28-37,41-79`). Slice 50 must not
turn the existence of a verdict row into the missing completeness proof; it may only add a bounded decision over
the exact declared inventory.

### 2.3 Candidate membership is frozen; issue and risk dispositions are not

A candidate can bind issues only while `draft`; membership becomes immutable when the candidate is frozen
(`app/models/release_candidate_issue_binding.py:1-10`; `app/repositories/release_candidates.py:47-79`). Issue
rows can later move one way from `open` to `resolved | accepted | superseded`, while risk acceptances can later
become `expired | revoked | superseded` (`app/release/issues.py:47-49,140-188`;
`app/release/risk_acceptance.py:23-43,103-106`). Therefore a verdict cannot be permanently current merely because
its candidate membership is frozen. OD-50-5 must bind an input digest/latest-wins rule that detects lifecycle or
evidence changes without inventing a wall-clock TTL.

### 2.4 Existing risk acceptance proves binding more strongly than authority

For a newly created risk acceptance, Slice 47 proves a same-project frozen candidate, explicit subject kind, and
exact candidate membership; issue acceptance additionally joins the exact risk record, issue UUID, release ref,
active state, expiry, and non-hard-refusal status
(`app/repositories/risk_acceptance.py:87-143`;
`app/repositories/release_candidates.py:173-208`). The DB FK is deliberately `NOT VALID` over legacy history,
and legacy NULL `subject_type` rows remain visible rather than relabelled
(`migrations/versions/0046_issue_provenance.py:374-390`).

What it does **not** prove is equally load-bearing: `request_authenticated` is not a human signature or verified
approval-matrix authority, and `caller_supplied_unverified` proves less. Slice 47 explicitly preserved those
meanings (`.planning/SLICE-47-PLAN.md:194-215`; ruling OD-47-6 at `:35`). OD-50-4 must rule whether either tier can
support the phrase “approved risk-acceptance records” in Appendix B #7; no implicit upgrade is allowed.

### 2.5 Slice-49 core/attestation staging is real, but canonical finalization is intentionally refused

`evidence_packs` stores immutable canonical core text, exact digests, candidate/audit FKs, inventory counts, and
fixed `verdict_status='absent_deferred_slice50'`; the core guard rejects verdict/signature/truth fields
(`app/models/evidence_pack.py:160-246`; `migrations/versions/0048_evidence_packs.py:241-330,503-560`). Export
re-audits exact bytes, normalized refs/inventory, and the audit checkpoint before rendering
(`app/repositories/evidence_packs.py:825-910`).

The reserved `ReleaseVerdictAttestation` dataclass is not an authority: Slice 49 refuses even a right-looking
object because no DB store exists to reload and prove it (`app/release/evidence_export.py:20-74`). Canonical export
also currently validates a fixed assurance-limitation list containing `verdict_deferred_to_slice_50`
(`app/release/evidence_pack.py:1041-1057`). Slice 50 must append a real attestation and construct a canonical
export projection without mutating core bytes or leaving that stale exported limitation. OD-50-8 rules the exact
finalization behavior.

### 2.6 A §24.3 verdict and an A5/go-live decision are not coextensive in the current build

Spec §24.1’s full go-live formula includes intake, autonomy policy, acceptance, test oracles, security, shortcuts,
evidence pack, rollback, monitoring, approvals, and open-issue disposition (`spec:2251-2267`). Slice 50 is
sequenced only to complete Appendix-B gate #7; gates #9, #10, #12, and #13 remain future work, and verified A5
pre-approval does not exist (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:483-565,744-748`). A holistic reading of
“Release may proceed under policy” would therefore make `passed` unreachable in Slice 50 and would fail the
roadmap goal of making #7 PASS-capable. A gate-#7-bounded reading permits a pass but must carry an explicit scope
limitation. This is an inference/architecture choice, not a verbatim spec rule; OD-50-2 must bind it.

---

## 3. Required design semantics (contingent on §4 rulings)

### 3.1 Exact decision input

The proposed decision input is a repository-created frozen value containing only bounded scalars and exact IDs/
digests, derived after re-audit:

- tenant/project, exact candidate ID, candidate release-ref digest, `status='frozen'`, and `frozen_at`;
- exact evidence-pack ID, generation-run ID, core content hash, schema/semantic/projection/audit contract
  versions/hashes, audit checkpoint ID/tip, assembly status, repo-binding state/hash/commit, artifact-scope
  digest, issue-binding digest, source-set digest, traceability digest, and source timestamps;
- every exact bound issue’s binding ID, issue ID, source-provenance code, source-finding ID presence, category,
  severity, blocking boolean/category, lifecycle status, and projection digest;
- for each limitation/accepted issue, the exact candidate-bound risk-record ID, subject kind/ID, status, expiry,
  blocking-category presence, approver-provenance tier, and projection digest; and
- code-derived counts and a canonical SHA-256 `verdict_input_digest` over the ordered structural input.

These fields already exist in the candidate/issue/risk/core projections except the proposed verdict-layer digest
(`app/release/evidence_pack.py:129-165,489-540,721-824`; `app/models/evidence_pack.py:213-246`). Any new field,
ordering, or digest contract is a proposed engineering choice requiring OD-50-7/10.

No issue/finding/risk/review prose, approval names, accepted-by list, evidence links, URLs, prompts, responses,
scanner JSON, corpus content, source content, credentials, or arbitrary JSON enters the verdict tables or audit.

### 3.2 Decision precedence

The proposed fail-closed precedence is:

1. inability to load/re-audit the exact pack, candidate mismatch, core/child mismatch, invalid contract, or
   infrastructure failure ⇒ failed/refused **attempt**, not a fabricated §24.3 attestation;
2. an audited but incomplete/inconsistent core, stale input binding, unresolved trusted repo binding if ruled
   required, missing/untrusted issue provenance, or unsupported required evidence ⇒
   `failed_missing_evidence`;
3. any open critical/hard-refusal issue or any other open unaccepted blocking issue ⇒
   `failed_blocking_issue`; a hard blocker can never be converted to a pass/limitation verdict
   (`app/release/issues.py:140-147`; `spec:2269-2271`);
4. evidence is structurally consistent but a non-hard limitation needs authority that the ruled trust tier cannot
   prove ⇒ `requires_human_decision`;
5. no blocking/missing/authority condition and at least one ruled limitation/accepted-risk condition ⇒
   `passed_with_limitations`;
6. no blocking/missing/authority/limitation condition ⇒ `passed`;
7. `not_applicable` only on a positively proved, coordinator-ruled non-production applicability basis—never by
   absence, zero issues, caller string, or missing evidence.

The order and exact eligibility predicates are proposed, not yet authoritative. OD-50-2/3/4/6 bind them.

### 3.3 Zero issue inventory is not the same as no issue evidence

Slice 49’s inventory always has a `candidate_issues` section. That section may be `present_zero_rows` without
making the core incomplete, while missing required source classes use `missing_required_source`
(`app/repositories/evidence_packs.py:561-605`). The existing Slice-47 ladder refuses a zero binding set because no
verdict exists to make a bounded inventory decision (`app/release/production_autonomy.py:344-353`).

**Proposed distinction (inference):** an empty release-issue table or zero bound rows alone never passes. A ruled
Slice-50 path may treat an explicit zero-member `candidate_issues` inventory as a bounded clean outcome only when
the exact complete core has re-audited, its issue-binding digest matches the frozen candidate, all required
source inventory is present, and the current input digest is exact. This still does not prove universal issue
absence. OD-50-3 must accept or reject zero-member gate eligibility.

### 3.4 Append-only attestation, not core mutation

Under the recommended architecture, the immutable Slice-49 core retains its original bytes and historically
accurate deferred status. A new `release_verdicts` row references it and serves as the real verdict attestation.
Canonical export builds a new payload in memory from the re-audited core plus the DB-reloaded attestation; it
does not UPDATE `evidence_packs`, rewrite `canonical_core_text`, or relabel old history
(`.planning/SLICE-49-PLAN.md:9,17`; `migrations/versions/0048_evidence_packs.py:660-694`).

### 3.5 Latest-wins and change invalidation

The proposed staleness rule is content/binding based, not time based:

- gate evaluation selects the existing deterministic latest frozen candidate;
- for that candidate, the latest evidence-pack generation attempt/core is selected by
  `(created_at DESC,id DESC)` under the current contract;
- the latest verdict attempt for that exact core/input/contract is selected by the same order;
- any newer incomplete/failed/refused pack or verdict attempt supersedes an older pass for current gate use;
- any issue/risk lifecycle change, evidence source change, core/contract change, candidate status change, or
  current input-digest mismatch requires a new core and/or verdict as ruled; and
- there is no invented wall-clock TTL. Historical cores/verdicts remain immutable history and may be explicitly
  exported as historical artifacts when they have an attestation.

This extends the append-only “changed anything ⇒ new assembly” ruling from OD-49-6
(`.planning/SLICE-49-PLAN.md:17`) and the current latest-frozen order
(`app/repositories/release_candidates.py:109-124`). Exact ordering and supersession are OD-50-5.

---

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-50-1 — Which verdict enum is authoritative, and how is it projected into the immutable canonical schema?

**Option A — §24.3 authoritative internally; versioned lossy canonical projection (recommended).** Persist the
six-value §24.3 verdict as `spec_verdict` under `slice50.release_verdict.v1`. Derive a separate
`canonical_verdict` under `slice50.verdict_projection.v1`:

| §24.3 `spec_verdict` | Canonical `verdict` |
|---|---|
| `passed` | `passed` |
| `passed_with_limitations` | `passed_with_accepted_risk`, only when the ruled limitations are in fact covered by eligible risk evidence |
| `failed_blocking_issue` | `failed` |
| `failed_missing_evidence` | `failed` |
| `requires_human_decision` | `blocked` |
| `not_applicable` | `blocked` |

The canonical export also includes a strict semantic-extension `verdict_attestation` with the uncollapsed
`spec_verdict`, attestation ID/provenance/contract hash/time, and reason code. The schema remains unchanged and
permits the extension because it does not set `additionalProperties:false`; the code-owned semantic contract
remains stricter (`evidence_pack_schema.json:1-65`; `app/release/evidence_pack.py:827-858`). The projection is
explicitly lossy and never used to reconstruct the six-value verdict.

**Option B — canonical four-value enum authoritative internally.** Simpler export, but it discards the exact
§24.3 failure/decision distinctions and contradicts the roadmap’s six-value goal. Not recommended.

**Option C — keep six values but refuse all canonical exports until the canonical asset changes.** Honest but
conflicts with binding OD-49-2, which permits unsigned canonical export after a real Slice-50 attestation.

If Option A is selected, the coordinator must also confirm that a `passed_with_limitations` outcome lacking
eligible accepted-risk evidence has **no truthful canonical projection** and therefore cannot be emitted under
that condition; OD-50-3/4 govern whether such a condition becomes `requires_human_decision` instead.

### OD-50-2 — What is the verdict’s decision scope?

**Option A — bounded gate-#7 issue-disposition verdict over a re-audited release evidence core
(recommended).** The evaluator consumes the whole core for integrity, inventory, and binding checks, but its
pass/fail decision is explicitly scoped as `known_bound_issue_disposition`. A `passed` value means the ruled
gate-#7 condition holds for that exact snapshot; it does not mean all §24.1/A5 conditions hold or that deployment
may proceed. This is the only design that can honestly satisfy the roadmap’s “#7 → PASS-capable” milestone while
other gates remain unbuilt, but it is a conservative architecture inference rather than verbatim §24.3 wording.

**Option B — holistic §24.1 release verdict.** Include every §24.1 condition in the decision. This is the most
literal reading of “Release may proceed under policy,” but `passed` is impossible in Slice 50 because gates
#9/#10/#12/#13 and verified pre-approval are absent; gate #7 therefore remains no-pass. It does not meet the
roadmap’s stated Slice-50 exit.

**Option C — caller/release-manager supplied verdict.** Rejected: neither an actor label nor request-auth key
custody is verified release authority, and the task requires a deterministic system-derived verdict.

### OD-50-3 — What exact issue-disposition and zero-inventory rules produce `passed` versus limitations/failure?

**Option A — strict, canonical-aligned disposition (recommended).** A complete, exact zero-member inventory may
produce `passed` only under §3.3’s explicit evidence rule. For non-empty membership: resolved/superseded issues
are non-limiting; any open blocking/hard issue yields `failed_blocking_issue`; any open non-blocking issue must
have exact eligible risk evidence to become a limitation-bearing outcome; accepted issues require the same exact
eligible record. `passed_with_limitations` requires at least one such eligible limitation and no blocking/missing
condition. This is stricter than §24.1 line 2266’s “non-blocking OR covered” phrasing but aligns Appendix B #7’s
“any remaining open issues have approved risk-acceptance records” and the canonical accepted-risk value
(`spec:2266,2991`; `evidence_pack_schema.json:53-59`).

**Option B — §24.1 permissive open-nonblocking rule.** An open non-blocking issue may produce
`passed_with_limitations` without a risk record. This follows `spec:2266` but cannot honestly map to canonical
`passed_with_accepted_risk`; canonical export for that verdict would need refusal or a separately ruled mapping.

**Option C — zero bound issues never gate-pass.** Avoids vacuity but makes genuinely explicit zero inventories
permanently non-passable and narrows the practical pass path to candidates with only resolved/superseded rows.

All options retain: untrusted issue provenance ⇒ missing evidence; any open critical/hard-refusal issue forces a
failing verdict; no hard blocker can be risk-accepted; an empty store without exact core inventory never passes.

### OD-50-4 — Which risk-acceptance provenance is gate/verdict eligible?

**Option A — strict verified-authority rule (recommended).** Neither `caller_supplied_unverified` nor
`request_authenticated` is sufficient for a gate-bearing “approved” acceptance because neither proves a human
signature or approval-matrix authority. Such a structurally valid exact record remains diagnostic and drives
`requires_human_decision`; `passed_with_limitations` is not gate-eligible until a future verified authority tier
exists. Gate #7 is still PASS-capable via `passed` when no accepted risk is needed. No historical row is relabelled.

**Option B — request-authenticated operational acceptance with explicit limitation.** Permit only exact,
active, unexpired, non-hard-refusal `request_authenticated` records to support `passed_with_limitations`, while
stating everywhere that this proves key custody, not human identity/signature or approval-matrix membership.
This makes accepted-risk gate passage available now but puts a weaker evidence tier on a critical gate.

**Option C — either current provenance tier.** Rejected: it would let an unverified caller assertion satisfy an
“approved” gate.

This OD does not alter the stored provenance meanings or the Slice-22/27/47 guards under any option.

### OD-50-5 — What exact binding, latest-wins, and invalidation rule applies?

**Option A — latest current core/input wins; no TTL (recommended).** Evaluate the latest frozen candidate, then
the latest pack generation for it, then the latest verdict attempt for the exact pack + candidate + core hash +
issue/source/input digests + verdict-contract hash. Later incomplete/failed/refused attempts supersede older
passes. Candidate no longer frozen, newer core without verdict, or current structural-input digest mismatch makes
the old verdict historical/non-gating. Any changed evidence requires a new assembly; any changed verdict input
requires a new verdict. No wall-clock TTL.

**Option B — any historical passed verdict remains current.** Rejected: later failures or lifecycle changes could
be ignored.

**Option C — fixed time TTL.** Rejected absent a governing spec/policy value; source-specific freshness already
lives in source evidence and pack snapshots.

### OD-50-6 — What deterministically triggers `requires_human_decision` and `not_applicable`?

**Option A — authority gap is decision-only; `not_applicable` unsupported this slice (recommended).** Emit
`requires_human_decision` only when evidence is otherwise structurally complete/consistent, no hard blocker is
open, and a non-hard limitation depends on authority not proven by OD-50-4. Persist the decision only; do not
create an approval or mutate anything. The current candidate model has no production-applicability/authority
field (`app/models/release_candidate.py:29-65`), so never emit `not_applicable`; a caller request for it is
refused and absent applicability evidence fails closed. A later reviewed authority/applicability primitive may
make the sixth value reachable.

**Option B — add a request-authenticated applicability declaration.** Makes `not_applicable` reachable, but key
custody is not verified production authority and this widens the slice into a new authority workflow.

**Option C — infer `not_applicable` from zero issues, missing deployment evidence, or caller text.** Rejected:
absence/missing evidence is not positive proof that a system is not intended for production.

### OD-50-7 — How is the decision made non-fakeable in storage?

**Option A — attempts + generated verdict + exact child set (recommended).** Add append-only
`release_verdict_runs`, `release_verdicts`, and `release_verdict_issue_results`. The run records success,
failure, or refusal. A successful attestation has one normalized child per exact candidate binding/core issue
projection. Code-owned SQL functions/generated columns derive `spec_verdict`, canonical projection, reason, and
gate eligibility from guarded scalar inputs; a deferred constraint trigger re-derives counts, proves the child
set equals the exact frozen/core source set, checks risk links, and rejects forged/missing/duplicate results.
Infrastructure failures never masquerade as release verdicts.

**Option B — one parent row with application-computed counts/verdict.** Smaller, but a direct SQL insert could
forge a plausible pass unless a complex trigger re-reads everything; it loses per-issue auditability.

**Option C — update `evidence_packs` with verdict columns.** Rejected by OD-49-2/6: core and attestation are
separate append-only layers.

### OD-50-8 — Which real attestations unlock canonical export, and how is the deferred limitation retired?

**Option A — every successful DB-bound verdict outcome unlocks that exact historical pack (recommended).** Export
is evidence, not authorization, so `failed`, `blocked`, and pass-like outcomes may all be exported. The repository
re-audits the exact core, reloads the exact attestation, verifies its current contract/binding, builds a new
canonical payload with the OD-50-1 canonical value, strict `verdict_attestation`, `signatures: []`, and
`signature_status='unsigned_signer_tier_not_implemented'`, then runs both semantic and Draft-2020-12 schema
validation. The export projection replaces `verdict_deferred_to_slice_50` with a code-owned limitation stating
that the verdict is bounded/non-authorizing, while retaining signer deferral; stored core bytes never change.

**Option B — only gate-pass-eligible verdicts unlock export.** Conflates evidence export with approval and hides
failed/blocked evidence packs from canonical history.

**Option C — mutate the core limitation/status.** Rejected: violates immutable core history.

Under every option, a mere dataclass/caller object is refused; the attestation must be loaded by exact FK from the
Slice-50 table. Full signed assurance remains Slice 60.

### OD-50-9 — What exact gate-#7 ladder and A5 context ship?

**Recommended ladder (Options A in prior ODs assumed):**

1. no current frozen candidate ⇒ existing
   `insufficient_evidence:no_issue_provenance_or_release_binding`;
2. no current exact pack/core or no successful audit ⇒
   `insufficient_evidence:no_audited_release_evidence_core`;
3. latest pack/verdict attempt failed or refused, or its binding is stale, contract-mismatched, or input-
   inconsistent ⇒
   `insufficient_evidence:release_verdict_evidence_incomplete_or_stale`;
4. no DB-bound verdict for the latest exact core/input ⇒
   `insufficient_evidence:verified_known_issue_set_but_no_release_verdict`;
5. `failed_missing_evidence` ⇒ `insufficient_evidence:release_verdict_failed_missing_evidence`;
6. `failed_blocking_issue` ⇒ `insufficient_evidence:release_verdict_failed_blocking_issue`;
7. `requires_human_decision` ⇒ `insufficient_evidence:release_verdict_requires_human_decision`;
8. `not_applicable` ⇒ `insufficient_evidence:release_verdict_not_applicable`;
9. `passed_with_limitations` but OD-50-4/contract says risk evidence is not gate-eligible ⇒
   `insufficient_evidence:release_limitations_not_authoritatively_accepted`;
10. ruled gate-eligible `passed` or `passed_with_limitations` ⇒ `status='passed'`, reason
    `passed:bound_release_issue_disposition_verdict_current`.

Safe context only: candidate/core/verdict presence booleans; assembly/repo-binding/verdict/reason/provenance codes;
current/exact/stale booleans; bound total/trusted/untrusted/open/blocking/hard/accepted/resolved/superseded/limited
counts; eligible/ineligible risk counts; legacy-unbound count; and consistency booleans. No prose, signer names,
accepted-by list, risk reason/controls, evidence links, URLs, artifacts, prompts, responses, secrets, or arbitrary
JSON. Existing safe candidate ID/ref context may remain for compatibility
(`app/release/production_autonomy.py:354-385`).

Advance `A5_RULESET_VERSION` from `slice47.v1` to `slice50.v1` because gate #7 gains a new input contract,
reasons, context, and first pass branch. Gate name remains `approved_risk_acceptance_records`. Gates #1-#6 and
#8-#13 remain byte-identical for identical inputs.

### OD-50-10 — What contracts, bounds, audit surface, and downgrade rule are authoritative?

**Recommended ruling:** `slice50.release_verdict.v1`, `slice50.verdict_projection.v1`, and
`slice50.release_verdict_input.v1`; canonical SHA-256 input/core/contract digests; at most 10,000 bound issue
results per attempt; one result per exact binding; codes/provenance/status/scope keys ≤128 characters; evidence
reference ≤500; all required strings non-blank; no raw or prose fields. Caller-supplied
`verdict|canonical_verdict|passed|eligible|trusted|complete|ready|gate|authority|signed` fields fail closed.

Audit safe metadata only: attempt/verdict/core/candidate/project IDs; execution/spec/canonical/reason/provenance
codes; contract hashes; aggregate counts; current/exact/export booleans; export byte count/hash. Audit must never
contain release title/ref text, issue/finding/risk/review prose, blocker detail, actor authority claims, signer/
accepted-by values, evidence links, URLs, raw core JSON, prompts/responses, source artifacts, tokens, or secrets.

Downgrade `0049→0048` must fail closed while any Slice-50 run/verdict/result exists, rather than delete or relabel
attestation history. With no Slice-50 rows it drops only Slice-50 objects and restores the exact Slice-49 export
refusal code path. No existing table/guard is rewritten by the migration. These are proposed choices requiring
the coordinator ruling.

---

## 5. Proposed pure modules (contingent on §4 rulings)

### 5.1 `app/release/release_manager.py`

Proposed contents:

- six-value `SPEC_VERDICTS` exactly from §24.3;
- four-value `CANONICAL_VERDICTS` exactly from the immutable schema;
- version/hash constants from OD-50-1/7/10;
- frozen `ReleaseVerdictInput`, `IssueDisposition`, `RiskAcceptanceDisposition`, and
  `ReleaseVerdictDecision` value types containing bounded structural fields only;
- validators for counts, enum/status/provenance codes, exact set membership, hard-blocker rules, and digest
  format;
- deterministic input digest and canonical ordering;
- `evaluate_release_verdict(...)` with the coordinator-ruled precedence;
- `project_canonical_verdict(...)` with no fallback/guessing;
- explicit failure/refusal exceptions whose codes are bounded and safe; and
- no DB, network, LLM, connector, approval, issue mutation, pack mutation, audit write, deployment, or gate side
  effect.

Pure decision code must accept no caller `verdict`, `pass`, `trusted`, `complete`, `eligible`, `authority`, or
`gate` field. Repository-loaded structures are wrapped into the input after re-audit; the public seam does not
accept an arbitrary evidence-pack payload as authority.

### 5.2 `app/release/evidence_pack.py` and `app/release/evidence_export.py`

Only the ruled canonical-finalization extension is allowed:

- preserve core validation and its exact historical limitation list;
- add a separate canonical-export semantic shape for `verdict_attestation`, the post-verdict limitation list,
  canonical verdict, empty `signatures`, and unsigned status;
- reject unknown extension fields and lossy projections not authorized by OD-50-1;
- require the DB-reloaded attestation shape rather than trusting the reserved dataclass;
- validate canonical export with the existing `Draft202012Validator` + `FormatChecker`; and
- keep core preview/Markdown/unsigned-manifest behavior honest and deterministic.

The canonical schema asset itself remains byte-identical. No signing implementation is added.

---

## 6. Storage and expected migration `0049` (inference; additive-only)

### 6.1 `release_verdict_runs` — tenant-owned immutable attempts

Proposed columns (exact names subject to OD-50-7/10):

- `id`, `tenant_id`, `project_id`, `release_candidate_id`, nullable `evidence_pack_id` for a pre-attestation
  failed/refused attempt, exact input/core/contract hashes, execution status/provenance/failure code, safe counts,
  `created_at`;
- composite same-tenant/project FKs to project/candidate and, when present, evidence pack;
- `execution_status ∈ succeeded|failed|refused` and
  `execution_provenance='system_derived_release_verdict'`;
- row-shape CHECKs: succeeded ⇒ pack present + no failure code; failed/refused ⇒ bounded failure code; and
- a deferred constraint trigger proves that a succeeded run has exactly one attestation while a failed/refused
  run has none (a row-local PostgreSQL `CHECK` cannot inspect the sibling attestation table); and
- deterministic latest order `(created_at DESC,id DESC)`.

Failed/refused runs remain operator evidence and supersede older gate-bearing success under OD-50-5; they never
become canonical verdict attestations.

### 6.2 `release_verdicts` — tenant-owned immutable attestation

Proposed columns:

- `id`, run/candidate/pack/project/tenant FKs, exact frozen/core/audit/schema/contract/input snapshot hashes,
  structural counts, generated `spec_verdict`, generated `canonical_verdict`, generated reason code, generated
  gate-eligibility, `decision_scope`, fixed decision provenance, and `created_at`;
- unique `run_id`; composite unique `(id,project_id,tenant_id)` for exact child/export FKs; and
- no mutable lifecycle, caller verdict, signer, approval, prose, raw payload, or arbitrary JSON.

This row implements the reserved Slice-49 verdict-attestation role; `evidence_packs.verdict_status` stays
historically fixed and is not updated.

### 6.3 `release_verdict_issue_results` — exact normalized membership proof

Proposed one append-only row per exact frozen candidate binding/core issue projection:

- result/verdict/candidate/binding/issue IDs with composite tenant/project FKs;
- exact issue and risk projection digests;
- structural status/provenance/category/severity/blocking/hard/limitation/acceptance eligibility codes;
- optional exact risk-acceptance FK only when the core/input proves the link; and
- ordinal plus unique `(verdict_id,binding_id)` and `(verdict_id,ordinal)`.

A deferred constraint trigger must prove at transaction end that the child set exactly equals the candidate’s
frozen binding set represented in the attested core, all ordinals/counts/digests agree, and every acceptance link
is the same tenant/project/release/subject represented by the core. Missing, extra, duplicate, cross-tenant,
cross-project, wrong-release, stale, or forged child rows fail.

### 6.4 RLS, append-only, guards, preservation, and grants

All Slice-50 tables are tenant-owned with `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, the standard
`tenant_isolation` policy, `SELECT,INSERT` only for `uaid_app`, no UPDATE/DELETE/TRUNCATE, and append-only triggers
mirroring existing immutable evidence tables (`migrations/versions/0048_evidence_packs.py:56-84`). PUBLIC gets no
privilege; all FKs use `ON DELETE RESTRICT`.

Migration `0049` must not alter `release_findings_guard()`, `release_issues_guard()`,
`risk_acceptance_records_guard()`, candidate guards, evidence-pack core/child guards, audit functions/lock,
approval/identity guards, reviewer-QA eligibility, or any RLS/grant on existing objects. The current findings-
guard catalog MD5 remains `808036faf2660d6810aeca4342e6f1ac` before upgrade, after upgrade, after downgrade, and
after re-upgrade (`tests/test_evidence_packs.py:406-457`; `.planning/SLICE-49-PLAN.md:619-620,775-776`).

---

## 7. Repository/orchestrator behavior

### 7.1 `app/repositories/release_verdicts.py`

Proposed `evaluate_and_record(project_id, release_candidate_id, evidence_pack_id, actor)` flow:

1. resolve the exact same-tenant/project candidate and require it is currently `frozen`;
2. load the exact pack and invoke the real Slice-49 `_reaudit`/public audit seam—never trust stored booleans;
3. verify candidate/pack/core/audit/contract binding and obtain exact normalized source refs/inventory;
4. load exact bound issue/risk structural rows and compare them to the core projections/digests;
5. build the code-owned ordered input and digest; reject caps, unsupported fields, and mismatches;
6. evaluate the pure ruled decision;
7. insert the attempt, successful attestation, and exact issue results atomically; force deferred constraints
   before returning;
8. audit safe metadata only; and
9. on infrastructure/contract failure, roll back partial work and record a separate safe failed/refused attempt
   where transaction semantics permit—never manufacture `failed_missing_evidence` from an execution error.

Proposed reads:

- `latest_attempt_for_candidate(...)` and `latest_for_exact_binding(...)`, ordered
  `(created_at DESC,id DESC)`;
- `current_gate7_evidence(project_id)` that recomputes the current input digest and returns a bounded safe view;
- `get_attestation_for_pack(pack_id)` for canonical export, exact FK/contract only; and
- safe history metadata, never verdict input prose/core JSON.

Idempotency for identical exact input may reselect an existing attestation or append an identical attempt only as
explicitly ruled; it must never return a materially different row under the same idempotency identity.

### 7.2 Evidence-pack canonical export

`EvidencePackRepository.export_canonical_json(pack_id, actor)` must:

1. re-audit the pack’s exact stored bytes and normalized children;
2. load a real successful Slice-50 attestation by exact same-tenant/project/pack FK;
3. revalidate verdict contract, input/core hashes, and enum projection;
4. construct the OD-50-8 export projection without mutating the core;
5. validate the strict semantic contract and canonical JSON Schema with format checking;
6. emit deterministic UTF-8 sorted compact bytes within the existing 16-MiB JSON cap; and
7. audit safe file/hash/count/status metadata.

Missing, failed/refused, forged, stale-contract, wrong-pack, cross-tenant, or projection-incompatible
attestations refuse canonical export. The export’s `signatures: []` and explicit unsigned status never become a
signature claim (`app/release/evidence_pack.py:1049-1057`; `app/release/evidence_export.py:106-123`).

### 7.3 No action execution

No verdict triggers deployment, approval request, risk acceptance, issue/finding transition, candidate
supersession, pack regeneration, notification, agent replacement, or control-loop step. A consumer may read the
decision later; this slice records and gates only.

---

## 8. A5 gate #7, readiness, and go-live — exact proposed change

### 8.1 Gate #7

- Advance proposed `A5_RULESET_VERSION` to `slice50.v1` only after coordinator rulings.
- Add repository-derived verdict inputs; do not accept a caller-provided `verdict_present`/`passed` boolean as
  authoritative.
- Replace the Slice-47 five-rung no-pass branch with the ruled OD-50-9 ladder.
- A pass requires a successful, current, exact-binding, gate-eligible verdict over the latest current frozen
  candidate/core/input. A stored historical pass, stale digest, newer failure/refusal, or unsupported limitation
  never passes.
- Gate name stays `approved_risk_acceptance_records`; the gate context remains safe metadata only.
- Gate #7 becomes the ninth PASS-capable gate after #1/#2/#3/#4/#5/#6/#8/#11, but other unmet gates keep A5
  false at the current repository state (`CLAUDE.md:578-628`; inference from adding #7 only).

### 8.2 Required non-change

- Gates #1-#6 and #8-#13 are byte-identical for identical inputs; gate order stays 1..13.
- Gate #5 continues to block on all-source open critical security findings; gate #6 continues to block on all-
  source open critical shortcut findings. A gate-#7 verdict cannot suppress either
  (`app/release/production_autonomy.py:387-578`).
- Gate #8 remains its DB-verified independent-agent authorship gate. Slice 50 does not interpret acceptance
  semantics or execute test oracles.
- `a5_satisfied` remains the conjunction of all 13 gates. Gates #9/#10/#12/#13 remain unmet after this slice.
- `app/intake/readiness.py` is byte-stable at `slice20.v1`.
- `can_go_live_autonomously` remains literal `False`, and
  `NO_GO_LIVE_REASONS == ('a5_gates_not_all_satisfied',
  'request_authenticated_a5_preapproval_not_implemented')` remains byte-identical
  (`app/release/production_autonomy.py:66-69,96-114`).

No §24.3 value removes either no-go reason. A canonical export, including a `passed` value, is an evidence
artifact—not deployment authority.

---

## 9. Test plan for eventual implementation

No tests are written or run during this plan-only task. After plan approval and all OD rulings, implementation
must begin test-first and cover the following.

### 9.1 Pure / Docker-free

1. Assert the source enum is exactly the six §24.3 values and the canonical asset is byte-stable with exactly its
   four values; test every ruled projection and reject every unknown value.
2. Truth-tier matrix: reported/request-auth/connector/system/DB/assembler evidence remains distinct; verdict
   provenance is only `system_derived_release_verdict`; no source tier is upgraded.
3. Deterministic canonical ordering/input digest; same material input ⇒ same digest/verdict; one changed issue,
   risk, core, contract, candidate, or projection ⇒ changed digest/refusal as ruled.
4. Decision-precedence matrix: execution failure versus missing evidence; missing/untrusted evidence; trusted
   critical/hard blocker; ordinary blocking issue; nonblocking limitation; exact accepted risk; authority gap;
   clean/resolved; unsupported applicability.
5. Hard blockers: every open critical issue and every hard-refusal category always produces a failing verdict;
   caller fields can never downgrade it; no passed-with-* outcome is possible.
6. Zero inventory: empty store alone refuses; explicit exact zero inventory follows the ruled OD-50-3 behavior;
   missing inventory never passes by vacuous truth.
7. Risk provenance matrix: caller-unverified, request-authenticated, legacy NULL subject, wrong release/subject,
   inactive/expired/revoked/superseded, blocking-category, and any future verified tier follow OD-50-4 exactly.
8. `requires_human_decision` and `not_applicable` triggers/refusals follow OD-50-6; neither causes a side effect.
9. Latest-wins/staleness: newer failed/refused verdict/core supersedes older pass; changed lifecycle/input invalidates
   old gate use; no time-only TTL.
10. Canonical export: all ruled outcomes, strict attestation shape, unsigned status, correct post-verdict
    limitations, canonical schema/format validation, deterministic exact bytes/hash, and 16-MiB cap.
11. Canonical export refuses dataclass-only/caller-shaped, wrong-pack/project/tenant, stale-contract, malformed
    mapping, absent, failed-attempt-only, or tampered attestations.
12. A5 gate #7: every OD-50-9 rung/precedence; only ruled pass-eligible outcomes pass; negative/inconsistent counts
    fail; context contains safe metadata only.
13. Golden A5 regression: ruleset `slice50.v1`; only gate #7 changes for equivalent fixtures; gates #1-#6 and
    #8-#13 remain exact; both no-go reasons/readiness remain exact.
14. No LLM/network calls: tests import no live adapter and need no API key.

### 9.2 DB-backed and direct-SQL adversarial

1. Migration round trip `0048→0049→0048→0049`; head/model/catalog parity; only ruled Slice-50 objects added;
   empty downgrade succeeds and row-bearing downgrade fails closed.
2. RLS/grants: all verdict tables ENABLE+FORCE; same tenant works; cross-tenant rows invisible/rejected;
   cross-project candidate/pack/issue/risk FKs reject; PUBLIC has no privilege; runtime has SELECT/INSERT only.
3. Append-only: UPDATE/DELETE/TRUNCATE rejected on attempts, verdicts, and results; identity/contracts/digests/
   counts/outcomes immutable.
4. Direct SQL cannot insert or alter generated `spec_verdict`, canonical verdict, reason, gate eligibility,
   provenance, completeness, or counts; any attempt to forge a pass fails.
5. Deferred exact-set guard rejects missing/extra/duplicate child results, ordinal gaps, wrong binding/issue, issue
   not represented by the core, projection-digest mismatch, count mismatch, and result after parent mismatch.
6. Exact pack/candidate guard rejects non-frozen/superseded/canceled candidate, wrong generation/core/audit IDs,
   incomplete structural binding, wrong core hash/digests, stale contracts, and pack from another project/tenant.
7. Risk-link attacks reject wrong release ref, wrong subject kind/UUID, unbound issue/finding, different candidate,
   legacy-unbound row, inactive/expired/revoked/superseded row, hard-refusal record, wrong issue acceptance FK, and
   forged approver provenance.
8. Hard-blocker attacks: direct SQL cannot record a passed/limitation verdict over open critical or
   `fake_done_finding`/other hard-refusal issue; cannot attach a risk acceptance to bypass it.
9. Zero-member transaction proves exact explicit inventory/digest under ruled behavior; deleting/omitting child
   evidence never converts missing into clean.
10. Latest-wins repository uses `(created_at DESC,id DESC)` and a later failed/refused/incomplete attempt blocks an
    older pass; current lifecycle/source digest mismatch blocks historical verdict use.
11. Canonical export reloads FK-bound attestation, re-audits exact core/children, validates both contracts, emits
    exact bytes, and refuses cross-tenant/historical-without-attestation/tampered rows.
12. Core immutability: no export/verdict path updates `evidence_packs.verdict_status`, canonical core bytes,
    limitations, hashes, source refs, or inventory rows; Slice-49 core/child guards remain exact.
13. Re-prove Slice-22/27/47 risk guard, Slice-24/47 issue guard, Slice-25 candidate freeze/binding guard, and
    Slice-49 evidence-pack/audit guard behavior line-by-line for all existing adversarial cases.
14. Findings-guard preservation: pin
    `md5(pg_get_functiondef('release_findings_guard()'::regprocedure))` to
    `808036faf2660d6810aeca4342e6f1ac` before/after upgrade, downgrade, and re-upgrade; rerun Slice-23/44/45 guard
    attacks.
15. Audit sentinel injects tenant prose, resolution text, blocker detail, risk reason/business impact/controls,
    signer/accepted-by values, evidence links, URLs, source/core JSON, prompts/responses, token-like strings, and
    secrets into permitted upstream fields and proves verdict/export audit contains only ruled safe metadata.
16. Production-autonomy repository computes the current digest and exact latest verdict through tenant-scoped
    reads, changes only gate #7, and leaks no cross-tenant IDs or prose.
17. API golden regression: existing read-only production-autonomy route reflects the new safe gate context without
    adding a write/export endpoint, existence oracle, or mutating read.

### 9.3 Verification commands for eventual implementation only

After approval/rulings and implementation: `git diff --check`; Ruff; focused pure/DB tests; `make test`;
`make test-db`; migration `0048→0049→0048→0049`; CI. Exact outputs/counts must be shown before PR review. These
commands are future implementation requirements, not authorization to run or implement them now.

---

## 10. Proposed file touch map for eventual implementation only

- Add pure decision module: `app/release/release_manager.py`.
- Add ruled models, likely `app/models/release_verdict_run.py`, `app/models/release_verdict.py`, and
  `app/models/release_verdict_issue_result.py`; register imports only as required.
- Add tenant repository/orchestrator: `app/repositories/release_verdicts.py`.
- Modify only the ruled Slice-49 finalization seams: `app/release/evidence_pack.py`,
  `app/release/evidence_export.py`, and `app/repositories/evidence_packs.py`.
- Modify gate #7 only: `app/release/production_autonomy.py` and
  `app/repositories/production_autonomy.py`.
- Add expected migration `migrations/versions/0049_release_verdicts.py` and focused
  `tests/test_release_verdicts.py`; extend evidence-pack/A5 golden tests only where integration requires.
- Do not modify the canonical schema asset, issue/finding/risk/candidate lifecycles, audit verifier, LLM/
  connectors, APIs/routers, `app/intake/readiness.py`, or gates other than #7.
- Do not create a branch, code, migration, test, commit, or PR until this plan is approved and all ODs are ruled.
  This plan file is the sole deliverable now.

---

## 11. Must NOT claim

- Must NOT claim a §24.3 `passed` or `passed_with_limitations` value means the release may actually deploy or
  proceed under full policy in this slice; the ruled decision scope is bounded and other gates remain unmet.
- Must NOT claim a verdict, gate-#7 pass, complete evidence core, canonical export, or unsigned manifest means
  A5 satisfied, release ready, safe, compliant, approved, deployable, signed, or go-live authorized.
- Must NOT claim a frozen candidate or populated/zero issue binding set proves issue completeness, feature scope,
  candidate→commit identity, or universal defect absence.
- Must NOT claim an empty issue/finding/risk store is clean. Only the ruled exact inventory behavior applies, and
  even that is a bounded decision—not a completeness proof.
- Must NOT flatten REPORTED, request-authenticated, connector-observed/verified, system-executed, DB-proven,
  admin-verified, assembler-derived, and verdict-derived truth tiers.
- Must NOT call `request_authenticated` a human signature, human identity proof, approval-matrix authority, or
  verified release-manager decision.
- Must NOT allow `caller_supplied_unverified` risk acceptance to satisfy an approved-risk gate.
- Must NOT allow any open critical or hard-refusal issue to produce `passed`, `passed_with_limitations`, or a
  gate-#7 pass; it must be fixed/resolved/superseded under the existing lifecycle.
- Must NOT let a risk record for release A, another subject, another candidate, expired/inactive authority, or
  legacy-unbound history satisfy release B.
- Must NOT infer `not_applicable` from missing evidence, zero issues, caller text, or absent deployment target.
- Must NOT treat `requires_human_decision` as the human decision itself or auto-create/resolve an approval.
- Must NOT silently choose between the six-value §24.3 enum and four-value canonical enum, or hide the lossy
  mapping. The canonical projection never reconstructs the normative verdict.
- Must NOT modify the canonical evidence-pack schema asset or mutate immutable core bytes/status to attach a
  verdict.
- Must NOT leave `verdict_deferred_to_slice_50` in the post-verdict canonical export limitation list; equally,
  must NOT erase it from historical stored core bytes.
- Must NOT unlock canonical export from a caller-shaped dataclass/string, a failed/refused attempt, or an
  attestation not loaded through exact same-tenant/project/pack FKs.
- Must NOT call `signatures: []`, a digest, content hash, actor label, key-custody record, or unsigned manifest a
  signature or external assurance.
- Must NOT trust stored/app-supplied counts, status, gate eligibility, or verdict without DB guards and export-
  time re-audit.
- Must NOT let an older passed verdict outrank a newer failed/refused/incomplete/stale input.
- Must NOT invent a verdict TTL absent a policy source.
- Must NOT mutate, auto-close, accept, supersede, resolve, bind, approve, deploy, notify, or execute any source
  lifecycle as a side effect of evaluation.
- Must NOT copy or audit issue/finding/risk/review/source prose, blocker detail, signer lists, evidence links,
  URLs, raw core/source JSON, artifacts, corpora, prompts, responses, credentials, tokens, or secrets.
- Must NOT weaken or replace any Slice-22/23/24/25/27/44/45/47/48/49 guard, FK, RLS policy, grant, generated
  column, append-only trigger, audit lock, or hard-refusal rule. Findings-guard MD5 remains pinned.
- Must NOT claim readiness changes; it stays byte-stable at `slice20.v1`.
- Must NOT alter either hard no-go reason. Go-live remains hard-false regardless of gate #7.
- Must NOT start implementation until explicit reviewer APPROVE and coordinator rulings on OD-50-1…10.

---

## 12. Definition of done for eventual implementation — not this plan-only task

After explicit plan approval and all coordinator rulings:

1. the rulings are copied verbatim into this plan before implementation;
2. the six-value normative verdict and four-value canonical projection are versioned, explicit, tested, and do
   not modify the canonical asset;
3. every successful verdict is deterministic, generated/non-forgeable, immutable, exact-candidate/core/input
   bound, re-audited, and supported by an exact normalized issue result set;
4. hard blockers and missing/untrusted/stale evidence fail closed; risk-acceptance authority follows the ruled
   trust tier without relabelling history;
5. failed/refused attempts remain visible and supersede older gate evidence under the ruled latest-wins policy;
6. canonical export accepts only a real DB-bound attestation, removes only the stale export-time verdict deferral,
   remains unsigned, re-audits, validates both contracts, and leaves core bytes immutable;
7. gate #7 alone gains the ruled pass branch under `slice50.v1`; every other gate is regression-identical;
8. readiness stays `slice20.v1`; both no-go reasons stay exact; go-live remains false;
9. migration `0049` is additive, RLS ENABLE+FORCE, append-only, exact-FK-bound, round-trips, fails closed on
   row-bearing downgrade, and preserves every prior guard including the findings MD5 pin;
10. audit is safe-metadata-only and all sentinel/direct-SQL/cross-tenant attacks fail;
11. no Slice-51+, approval, signing, deployment, LLM, connector, HTTP, or control-loop scope is added; and
12. `git diff --check`, Ruff, full pure suite, full DB suite, migration round trip, and CI are green with outputs
    presented for independent review.

For the present task, definition of done is only: this single sourced plan exists, all genuine choices are open
ODs, the muhasabah audit passes, and work stops for reviewer APPROVE/REJECT.

## Reviewer gate

**Reviewer request:** APPROVE or REJECT this plan-only design. On APPROVE, the coordinator must rule OD-50-1
through OD-50-10 before any implementation begins. Until both gates are satisfied: no branch, code, migration,
tests, commit, or PR.
