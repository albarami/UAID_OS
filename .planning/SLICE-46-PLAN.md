# Slice 46 — Acceptance verifier + spec-authorship independence + generated-AC release-gate binding (A5 gate #8) — PLAN v1

**Status:** APPROVED FOR EXECUTION — v1 approved; OD-46-1…7 ruled and bound (see Rulings section)

> **Persona.** Senior verification-platform and PostgreSQL governance architect, applying fail-closed
> authorship provenance, separation of duties, tenant isolation, release-scope binding, and Sanad /
> No-Free-Facts discipline.
>
> **Primary Sanad.** System-authored acceptance criteria cannot become binding verification targets until
> independently reviewed and approved (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:633-641`).
> Every acceptance criterion must carry one of six authorship statuses; `system_authored_unapproved` is not
> binding for go-live and `disputed` is blocked until resolved (`spec:643-654`; template
> `docs/UAID_OS_Intake_Template_Pack_v1_2/08_acceptance_criteria.yaml:1-7`). Independent approval may come
> from a human product owner, independent agent lineage, domain authority, or stable reference/contract; the
> independence definition requires different role, prompt family, reviewer authority, and—at high risk—a
> different model route/provider when available (`spec:656-673`). The acceptance-review layer confirms that
> the user request is satisfied (`spec:1228-1236`), while Appendix-B gate #8 is exactly “no unapproved
> generated acceptance criteria are used for critical release gates” (`spec:2981-2997`, especially line
> 2992). The roadmap makes Slice 46 the sole next planned item and requires authorship binding, rejection of
> unapproved/disputed gate-bearing ACs, gate-#8 PASS-capability, and no go-live claim
> (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:433-443,658-665`).
>
> **Verified repository Sanad.** Before this file was created, `main` and `origin/main` were both
> `916e1cdcb3522c796ba8e678fb35bab0f06be2b6`, the worktree was clean, and no local or remote feature branch
> existed (`git rev-parse HEAD origin/main`, `git status --porcelain`, and
> `git branch -a --format=...`, verified 2026-07-12). Alembic reports `0044 (head)`, and migration `0044`
> revises `0043` (`uv run alembic heads`; `migrations/versions/0044_shortcut_detector_execution.py:1-17`).
> The A5 evaluator is `slice45.v1`; gate #8 is permanently `insufficient_evidence` with only the obsolete
> `generated_ac_provenance_ok` context flag, and the repository never supplies that flag
> (`app/release/production_autonomy.py:59,125-206,234-240,679-696`;
> `app/repositories/production_autonomy.py:109-255`). Readiness remains the separate `slice20.v1`
> structural-intake evaluator (`app/intake/readiness.py:45`).
>
> **Current-authorship Sanad.** Canonical `intake_artifacts` store kind/content/parent/provenance but no
> authorship status or approval binding (`app/models/intake_artifact.py:47-90`;
> `app/repositories/intake.py:37-97`). Extraction promotion DB-proves an approved proposal→canonical-artifact
> link and re-verifies its source evidence, but proposal approval proves only a distinct caller label
> (`app/models/extraction_proposal.py:1-8,73-92`; `app/repositories/extraction.py:211-241,296-400`;
> `migrations/versions/0017_extraction.py:187-264`; `0018_extraction_promotions.py:28-111`). Slice-36
> `generated_artifacts` carry the six §7 statuses and structural approval fields, but remain outside the
> spine; their `*_approved` states are explicitly “independence-evidence-recorded, NOT verified” because
> actor/lineage labels are caller supplied (`.planning/SLICE-36-PLAN.md:12-21,29-32,50-56`;
> `app/models/generated_artifact.py:1-9`; `app/repositories/generator.py:1-14,188-281`). Generic approvals can
> carry `request_authenticated`, but that tier proves API-key custody, not a human signature or authority; the
> generated-artifact review transition does not require or FK-bind an approval row
> (`app/identity.py:1-12,19-25`; `app/models/approval.py:1-8,73-94`;
> `app/repositories/approvals.py:45-88,172-196`; `app/repositories/generator.py:206-267`). Therefore the
> gate-relevant authorship approval is not currently verified merely because a row says `approved`.

## Coordinator rulings (final)

- **OD-46-1 = Option A (strict verified-evidence rule), with the gate-bearing path included in this slice:** `caller_supplied_unverified` never makes an authorship status gate-eligible; existing extraction `approved` and Slice-36 `*_approved` rows remain diagnostic/non-gating; no historical row is relabelled. This slice MUST implement the **DB-bound `independent_agent_lineage` approval path**: a real, active, qualified, same-project reviewer instance with DB-proven lineage separation from the generator (distinct blueprint/version/model-route, reusing the Slice-45 independence machinery), FK-bound to the approval decision — so `system_authored_independent_approved` is genuinely gate-eligible. Human-owner approval remains non-gating until a verified human tier exists (`request_authenticated` is key custody, never a human signature); ACs with unknown authorship honestly block; gate #8 never fakes PASS.
- **OD-46-2 = Option A:** all structurally valid canonical project ACs are gate-bearing scope; recorded explicitly as a conservative inference stricter than Appendix B #8; empty scope never passes.
- **OD-46-3 = Option A:** binding = project + canonical scope digest + current authorship-chain digest + verifier-contract hash; latest-wins ordered `(created_at DESC, id DESC)`; a later failed/refused run supersedes an older pass; no wall-clock TTL.
- **OD-46-4 = Option A:** additive append-only sidecar `acceptance_criterion_authorship_records`; no spine mutation; extraction-promoted ACs positively classified system-derived but `system_authored_unapproved`/untrusted until OD-46-1 evidence exists; direct ACs without positive source remain missing/untrusted; no backfill guesses.
- **OD-46-5 = Option A:** append-only supersession chain with linear latest-record and legal-transition DB proofs; `disputed` blocks immediately; resolution appends (never updates) a new eligible record with bound resolution evidence; history never erased.
- **OD-46-6 = Option A:** structural authorship verifier only; supported bases are `human_owner` (non-gating this slice per OD-46-1) and `independent_agent_lineage` (gate-bearing per OD-46-1); `domain_authority` and `reference_oracle` fail closed as unsupported; no LLM acceptance judging, no semantic AC-quality checks.
- **OD-46-7 = recommended ruling:** `slice46.acceptance_verification.v1` schema + `slice46.authorship.v1` code-owned eligibility contract; canonical SHA-256 digests; one result per in-scope AC; ≤10,000 ACs per run; keys/status/reason/source codes ≤128; actor/authority/source labels ≤255; evidence reference ≤500; all required strings non-blank; no AC/source/approval prose ever copied into verification tables or audit; caller-supplied `eligible/complete/passed/trusted/gate` fields fail closed.

---

## 0. The defining honesty constraint (the crux)

Slice 46 must keep three truth classes separate:

1. **REPORTED.** A caller, source document, extraction reviewer, generated-artifact reviewer, or approval row
   may report an author, status, role, authority, or approval. A non-blank label, distinct string, `approved`
   state, or template `authorship` value is still a claim unless its trust path is bound and independently
   supported (`app/repositories/extraction.py:211-241`; `app/repositories/generator.py:206-267`;
   `app/models/approval.py:73-94`).
2. **DB-PROVEN.** PostgreSQL can prove the canonical AC exists in the same tenant/project, its requirement
   parent, its provenance rows, whether it came through an extraction-promotion bridge, the exact authorship
   record/history selected, any FK-bound approval/reviewer/release-scope relationship, immutable snapshot
   membership, child-count agreement, and the verifier’s derived structural verdict. It cannot prove that a
   human label is a product owner, that a reviewer understood the criterion, that a reported user authored the
   words, or that satisfying the criterion proves product behavior (`app/models/intake_artifact.py:47-90`;
   `app/models/extraction_promotion.py:28-70`; `app/identity.py:3-12`).
3. **GATE-INFERRED.** Only after the coordinator rules the authoritative authorship evidence, critical/release
   scope, binding, dispute lifecycle, supported approval bases, and verifier contract may the A5 evaluator infer
   whether no unapproved generated AC is being used. A passing gate #8 would mean only that the ruled,
   non-vacuous bound scope contains no criterion classified as unapproved/disputed/ineligible under the ruled
   evidence contract. It would not prove the criteria are correct, implemented, tested, semantically satisfied,
   or sufficient for A5 (`spec:633-673,1228-1236,2981-2997`).

**A missing authorship record, an empty AC set, absence of a generation link, a caller-provided `user_authored`
label, an extraction proposal’s `approved` status, a generated-artifact `*_approved` status, or an approval
row by itself must never silently pass gate #8.** Absence of a known system-generation link is not proof of
human authorship. Existing `request_authenticated` evidence, where present, is custody evidence only and may
not be renamed a human signature or product-owner authority (`app/identity.py:3-12`). OD-46-1 is therefore a
blocking honesty decision: under the strict option, unverified approval keeps gate #8 insufficient; under any
weaker option, the limitation must be visible in the gate reason/context and must never be described as verified.

## 1. Scope and non-goals

### 1.1 In scope after plan approval and all OD rulings

- A strict, versioned, structural acceptance-authorship verifier over canonical
  `kind='acceptance_criterion'` rows. It verifies authorship eligibility and binding metadata; it does not
  execute product acceptance behavior (`spec:633-673,1228-1236`; `app/models/intake_artifact.py:81-90`).
- An additive sidecar authorship/history model rather than mutating or forking the append-only canonical spine.
  Every gate-bearing authorship fact must point to the exact canonical AC and any source proposal/generator,
  approval, reviewer, or release binding selected by the rulings.
- Explicit treatment of current source paths: direct spine creation, extraction proposal→promotion, and the
  separate Slice-36 generated-artifact store. No path is silently upgraded from unverified to trusted.
- A coordinator-ruled, non-vacuous definition of “critical release gate” / “release-gating AC,” with exact
  membership and completeness semantics. Task-contract risk/link data and release candidates may be reused only
  to the degree their current schemas actually prove (`app/models/task_contract.py:57-149`;
  `app/models/release_candidate.py:29-66`).
- A deterministic exact-binding/latest-wins verification snapshot. Any change to the ruled AC membership,
  selected authorship record, approval/dispute state, release binding, or verifier contract invalidates an old
  pass. No universal wall-clock TTL is assumed.
- Proposed additive migration **`0045_acceptance_verification`** after verified head `0044`. The revision/name
  are an **inference from the monotonic migration sequence**, not a spec fact; the roadmap deliberately leaves
  Slice-46 numbering to its reviewed plan (`roadmap:438`; `roadmap:898`).
- Tenant-owned tables with RLS `ENABLE`+`FORCE`, `tenant_isolation` `USING`+`WITH CHECK`, composite
  tenant/project FKs, append-only UPDATE/DELETE/TRUNCATE guards, bounded non-blank fields, DB-verified
  aggregates, least grants, and audit safe-metadata only (house pattern:
  `migrations/versions/0041_task_contracts.py:645-687`; `0044_shortcut_detector_execution.py`).
- A fail-closed gate-#8 ladder. Because gate semantics and context materially change, the proposed A5 ruleset
  advances from `slice45.v1` to **`slice46.v1`** even if OD-46-1 selects a strict option that leaves some or all
  current approval paths non-gating. PASS-capability itself remains contingent on that ruling.
- Pure and DB-backed tests, including direct-SQL adversarial cases, exact no-other-gate regression, catalog
  proof that Slice-23/Slice-44/Slice-45 finding guards are untouched, readiness byte stability, and the
  `0044→0045→0044→0045` migration round trip.

### 1.2 Non-goals

- No semantic execution of acceptance tests, UI journeys, product behavior, or test oracles. Slice 43 executes
  oracles; Slice 46 only verifies the structural authorship/binding condition for gate #8
  (`spec:1353-1409`; `.planning/SLICE-43-PLAN.md:110-153,372-410`).
- No claim that Slice-42 review approval or `done` is acceptance verification. Slice 42 records reported
  verdicts and DB-proves registration/done-gate structure only (`.planning/SLICE-42-PLAN.md:55-89,230-239,
  279-288`).
- No reviewer-QA, planted reviewer defects, miss-rate governance, or calibration authority; those remain
  Slice 48 (`spec:1315-1345`; roadmap `:457-467`).
- No issue provenance/findings→issue bridge/risk-acceptance release FK (Slice 47), evidence-pack auditor
  (Slice 49), release verdict (Slice 50), production preapproval (Slice 53/55), deployment, or go-live.
- No automatic promotion of Slice-36 `generated_artifacts` into the canonical spine, no free-form AC parser,
  and no generated prose rewrite. A generator draft that never enters the spine cannot be a release-gating
  canonical AC (`app/models/generated_artifact.py:1-9`; `.planning/SLICE-36-PLAN.md:20-21,29-32`).
- No mutation, relabeling, or trust backfill of historical `intake_artifacts`, extraction proposals/promotions,
  generated artifacts, approvals, task contracts, or release candidates. Existing rows retain their actual
  provenance limits.
- No modification to the Slice-23/44/45 `release_findings` lifecycle or its layered security/shortcut guard;
  gate #8 needs no finding attachment. No security/shortcut gate semantics change.
- No HTTP endpoint, UI, scheduler, external connector, arbitrary plugin, LLM acceptance judge, or live network
  call. This slice is deterministic structural verification only unless a coordinator ruling explicitly
  expands and re-reviews the plan.
- No readiness change: `app/intake/readiness.py` must remain byte-stable at `slice20.v1`; structural intake
  completeness is not authorship approval (`app/intake/readiness.py:45,233-284`).

## 2. What the current repository can honestly say about an AC

| Current path | What is DB-proven now | Maximum honest gate-#8 statement before Slice 46 | Sources |
|---|---|---|---|
| Direct `IntakeRepository.add_artifact(kind='acceptance_criterion')` | Canonical row, same-project parent FK, ≥1 provenance row, accepted document when document-backed | Authorship is **unknown/reported**; no authorship field exists, and absence of an extraction link does not prove `user_authored` | `app/models/intake_artifact.py:47-90`; `app/repositories/intake.py:37-97`; migration `0014` |
| Approved extraction proposal promoted by Slice 14b | The model-created proposal, distinct reviewer **label**, verbatim source evidence, accepted source document, promote-once bridge to the exact canonical AC | **DB-proven system-derived origin; approval identity/authority remains unverified.** The proposal review is faithful-extraction review, not automatically §7.3 product-owner/independent-lineage approval | `app/models/extraction_proposal.py:1-8,73-92`; `app/repositories/extraction.py:211-241,296-400`; migrations `0017`/`0018` |
| Slice-36 `generated_artifacts(artifact_type='acceptance_criteria')` | Inert draft, §7 status transition shape, distinct labels/prompt-family fields, accepted source document | Status is recorded in a **separate non-spine store**; `*_approved` is binding-eligible but explicitly unverified and cannot gate a canonical AC without a reviewed promotion/binding | `.planning/SLICE-36-PLAN.md:20-21,29-32,50-56`; `app/models/generated_artifact.py:1-9`; migration `0035` |
| Generic subject-scoped `approvals` row | Request/resolve lifecycle; possibly `request_authenticated` key-custody provenance; verified self-approval refusal only when both sides are authenticated | Not bound to `GeneratedArtifactRepository.review_artifact`; not a human signature, product-owner authority, or agent-lineage proof | `app/models/approval.py:1-8,67-94`; `app/repositories/approvals.py:45-88,134-196`; `app/identity.py:3-12` |
| Task-contract AC link | Same-project AC existence/kind; contract risk level; freeze-locked membership | A real declared task scope, but not a proven complete release scope and not AC authorship approval | `app/models/task_contract.py:57-149`; migration `0041:469-505,561-597` |
| Frozen release candidate | Release identity and freeze-locked **issue-only** membership | No AC/repo/commit membership, no release verdict, and no issue/AC completeness claim | `app/models/release_candidate.py:29-66`; `app/models/release_candidate_issue_binding.py:1-10`; `.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md:30-45` |

**Consequence (inference from the sourced rows):** the verifier must not derive `user_authored` from “no
generation link found,” must not derive §7 approval from extraction `status='approved'`, and must not apply a
Slice-36 draft’s status to a canonical AC without an exact bridge. Historical unknowns remain unknown.

## 3. Required authorship, scope, and verifier semantics

### 3.1 Authorship eligibility

- The six status values are verbatim from §7.2/template 08; no `other`, `unknown`, or free-form status may be
  treated as eligible (`spec:643-654`; template `08_acceptance_criteria.yaml:5`). Missing evidence is represented
  by absence/ineligibility outside the status enum, not by inventing a seventh canonical status.
- `system_authored_unapproved` always blocks when in scope. `disputed` always blocks until a later ruled,
  append-only resolution record becomes current. No approval can overwrite or delete dispute history.
- `user_authored_system_normalized` requires a no-meaning-drift review because §7.2 makes its full weight
  conditional on that confirmation (`spec:650`).
- `system_authored_human_approved` and `system_authored_independent_approved` require the exact approval basis
  and trust tier selected by OD-46-1/6; a status string cannot satisfy itself.
- `user_authored` requires positive evidence selected by OD-46-1. A missing extraction/generator link is only
  an absence of known lineage, never positive user-authorship evidence.

### 3.2 Non-vacuous critical/release scope

- The gate needs an explicit set of AC IDs. A count of zero cannot pass: empty scope is indistinguishable from
  omitted requirements or missing bindings without an independent completeness authority (No fake done:
  `spec:129-149`; Appendix B #8 `spec:2992`).
- Every membership row/result is FK-bound to `kind='acceptance_criterion'` in the same tenant/project. A raw
  `ref`, JSON list, task title, or caller count cannot be gate-bearing.
- If all canonical project ACs are conservatively in scope (recommended OD-46-2 A), the plan explicitly labels
  that a **conservative inference stricter than Appendix B #8**; the spec does not say every AC is critical.
- If task contracts or a frozen release candidate define scope, the design must also prove membership
  completeness. Current contract links and issue-only candidate bindings do not do that by themselves.

### 3.3 What the acceptance verifier verifies

The proposed `app/verify/acceptance.py` verifies only:

1. the scope is ruled, non-empty, exact, same-project, and hash-bound;
2. every member has one unambiguous current authorship record under an append-only chain;
3. the record’s origin/approval/reviewer/dispute evidence matches the ruled status and trust tier;
4. no in-scope AC is missing, untrusted, `system_authored_unapproved`, unresolved `disputed`, or otherwise
   binding-ineligible;
5. the persisted per-AC results/counts equal the run snapshot and the latest exact binding is selected.

It does **not** read AC prose to decide quality, compare product behavior, run tests, decide whether the user
request is semantically satisfied, or replace Slice-43 oracles. “Acceptance verifier” is therefore a
structural authorship-and-release-gate verifier in this slice, not full semantic acceptance execution. That
scope is an explicit implementation interpretation of §13.1 and the roadmap’s gate-#8 objective, and requires
OD-46-6 confirmation (`spec:1230-1236`; roadmap `:433-443`).

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-46-1 — Which authorship/approval provenance is authoritative, and can gate #8 pass this slice?

**Gap:** current canonical ACs have no authorship field; extraction and Slice-36 approvals use unverified
labels; generic `request_authenticated` is API-key custody only and is not bound to generated-artifact review
(`app/repositories/generator.py:188-267`; `app/identity.py:3-12`; §2 table above).

**Options:**

- **A — strict verified-evidence rule (recommended):** `caller_supplied_unverified` never makes an authorship
  status gate-eligible. Existing extraction `approved` and generated-artifact `*_approved` rows remain
  diagnostic/non-gating. A gate-bearing human-owner path requires a separately DB-bound authority source;
  a gate-bearing independent-agent path requires a real same-project reviewer instance plus the ruled
  generator/reviewer lineage separation and a bound approval decision. If those sources are not added and
  proved in this slice, gate #8 remains `insufficient_evidence:authorship_approval_unverified` rather than
  faking PASS-capability. The A5 ruleset still advances because gate evidence/reasons become real.
- **B — accept `request_authenticated` as a limited approval tier:** allow a subject-scoped approved row whose
  resolver is `request_authenticated`, distinct from its authenticated requester, to support a status. The gate
  must expose `approval_limit='api_key_custody_not_human_signature_or_authority'`; it may not call the evidence
  human-signed or product-owner-authorized. Additional authority/lineage fields remain REPORTED unless separately
  DB-bound. This is weaker than §7.3’s authority language.
- **C — accept existing caller-unverified structural approvals:** permit extraction/generated-artifact distinct
  labels and DB-guarded status transitions to pass, but name the gate reason
  `passed_with_caller_supplied_unverified_authorship_approval`. This is not recommended: it would place an
  unverified assertion on the A5 critical path and must never be described as verified independence.

**No ruling ⇒** gate #8 remains `insufficient_evidence:authorship_authority_policy_unresolved`; implementation
is blocked. If the ruling adds an authority registry or executed reviewer path, this plan’s storage/test sections
must be revised and re-reviewed before code.

### OD-46-2 — What is the authoritative “critical release gate” AC scope?

- **A — all structurally valid canonical project ACs (recommended):** every canonical AC is gate-bearing. This
  mirrors the conservative Slice-43 oracle ruling and prevents omission, but is explicitly stricter than
  Appendix B #8 (`.planning/SLICE-43-PLAN.md:155-178`; `spec:2992`).
- **B — critical/high-risk task-contract AC links:** include AC links from non-canceled contracts whose
  `risk_level` is `high|critical`. The DB proves link kind and contract risk, but current contracts are not
  release-bound or proven complete; an additional completeness authority is required
  (`app/models/task_contract.py:57-149`; migration `0041:469-505,561-597`).
- **C — explicit frozen-release AC membership:** add freeze-locked
  `release_candidate_acceptance_bindings` and require a DB-proven completeness snapshot before freeze. This is
  closest to “critical release gates” but expands the Slice-25 issue-only candidate and requires a precise
  completeness rule; caller-selected membership alone cannot prove no AC was omitted
  (`app/models/release_candidate_issue_binding.py:1-10`; Slice-25 discussion §2/D-RB-5).

`risk_level` in template 08 is not present on canonical `intake_artifacts`; it cannot be silently inferred from
prose (`template:6`; `app/models/intake_artifact.py:81-90`). **No ruling ⇒**
`acceptance_scope_resolved=False`; gate #8 cannot pass.

### OD-46-3 — What exact binding and staleness policy selects current verification evidence?

- **A — project + canonical scope digest + current authorship-chain digest + verifier-contract hash,
  latest-wins, no TTL (recommended with OD-46-2 A):** a new/removed AC, new authorship/dispute/approval record,
  changed contract, or changed verifier requires a new run; a later failed/refused run supersedes an older pass.
  No repository commit is required because the verified objects are append-only DB artifacts and their exact
  membership/state is hashed.
- **B — frozen release candidate + freeze-locked AC membership + authorship digest + verifier hash:** use only
  with OD-46-2 C. Current release candidates have no repo/commit or AC membership, so the additive binding and
  completeness design must land together (`app/models/release_candidate.py:29-66`).
- **C — task-contract set digest:** binds to selected contract/link versions but inherits OD-46-2 B’s
  completeness problem.
- **D — add a wall-clock TTL:** requires a coordinator-supplied policy/value; neither §7 nor Appendix B #8
  supplies a universal duration.

**No ruling ⇒** `acceptance_binding_resolved=False`; gate #8 cannot pass.

### OD-46-4 — How are canonical AC authorship and existing source paths represented?

- **A — additive sidecar history (recommended):** create append-only
  `acceptance_criterion_authorship_records` keyed to the exact canonical AC. A source-shape guard binds optional
  extraction proposal/promotion, generated artifact/approved promotion (if a future bridge exists), approval,
  and reviewer evidence coherently. Existing extraction-promoted ACs may be positively identified as
  system-derived but are recorded `system_authored_unapproved`/untrusted until OD-46-1 evidence exists. Direct
  ACs with no positive authorship source remain missing/untrusted; no backfill guesses.
- **B — add authorship columns directly to `intake_artifacts`:** rejected as the default because the spine is
  append-only, existing rows lack a truthful backfill, and a mutable status would weaken Slice-11 semantics
  (`app/models/intake_artifact.py:1-13`; migration `0014`).
- **C — reuse `generated_artifacts` as the authoritative AC store:** rejected because it stores whole
  `artifact_type='acceptance_criteria'` drafts, not exact canonical AC rows, and has no spine promotion link.
- **D — infer `user_authored` whenever no extraction/generator link exists:** rejected because absence of a
  known machine path is not positive authorship evidence.

**No ruling ⇒** no authorship status is gate-bearing.

### OD-46-5 — How is dispute recorded and resolved?

- **A — append-only supersession chain (recommended):** each new authorship record points to the previous
  current record for the same AC. `disputed` immediately blocks. Resolution appends—not updates—a new eligible
  status with a bound resolution approval/evidence record; the entire chain remains auditable. Direct SQL must
  prove a single linear latest record and legal transition.
- **B — terminal dispute:** mirrors the current Slice-36 draft lifecycle but conflicts with §7.2’s “blocked
  until resolved” unless resolution means creating a replacement canonical AC (`spec:654`;
  migration `0035:215-282`).
- **C — mutable current status:** rejected as the default because it erases history and conflicts with the
  required append-only evidence discipline.

**No ruling ⇒** any disputed AC remains blocking and no resolution path is implemented.

### OD-46-6 — Which §7.3 approval bases and verifier semantics are supported?

- **A — structural authorship verifier; only `human_owner` and `independent_agent_lineage` (recommended):**
  retain Slice-36’s supported bases, but apply OD-46-1’s stronger trust rule. `domain_authority` and
  `reference_oracle` remain fail-closed unsupported because no authority/contract evidence model exists.
  No semantic AC-quality or product-behavior judgment runs.
- **B — support all four §7.3 bases:** requires new domain-authority and stable-reference/contract registries,
  provenance, lifecycle, and tests; this materially expands scope and must be specified before implementation.
- **C — run an LLM acceptance-review panel:** would add semantic reviewer execution, budget/cost/injection and
  reviewer-QA boundaries. It exceeds this structural slice and overlaps Slice 48 unless separately designed.

**No ruling ⇒** only diagnostic structural results may be recorded; gate #8 cannot pass.

### OD-46-7 — What schema, bounds, and count/verdict contract are authoritative?

**Recommended ruling:** `slice46.acceptance_verification.v1` input/result schema and
`slice46.authorship.v1` code-owned eligibility contract; canonical SHA-256 digests; one result per in-scope AC;
at most 10,000 ACs per run; keys/status/reason/source codes ≤128 characters; actor/authority/source labels ≤255;
optional evidence reference ≤500; all required strings non-blank; no AC title/body/data, source-document text,
approval note, generated draft, proposal text/evidence quote, prompt, model response, secret, raw repo ref, or
arbitrary JSON is copied into verification tables or audit. Unknown fields/statuses/bases/provenance,
duplicate membership, over-cap scope, malformed hash, missing child, count mismatch, and caller-supplied
`eligible/complete/passed/trusted/gate` fields fail closed.

The numeric caps and schema names are proposed engineering choices, not spec facts. **No ruling ⇒** production
verification input remains unsupported and gate #8 cannot pass.

## 5. Proposed pure module (contingent on §4 rulings)

### `app/verify/acceptance.py`

- Verbatim constants for the six §7.2 statuses, ruled approval bases, provenance tiers, source kinds,
  verification outcomes, and bounded reason codes.
- Frozen value objects for `AuthorshipEvidence`, `AcceptanceScope`, `AcceptanceResult`,
  `AcceptanceVerificationDecision`, and `Gate8Evidence`; none accepts a final gate status from a caller.
- Canonical JSON hashing for the ordered scope, current authorship chains, approval/reviewer binding, and
  verifier contract. UUIDs/hashes/enums/counts are strict; prose is never hashed into audit-visible context.
- A pure eligibility matrix derived from the coordinator rulings. `system_authored_unapproved`, unresolved
  `disputed`, missing/untrusted status, unsupported approval basis, wrong subject/action, self-approval,
  incomplete lineage, and source-shape inconsistency fail closed.
- Structural aggregation only. It computes per-AC reason codes and expected counts; it does not read product
  behavior, run oracles, interpret AC prose, or claim user-request satisfaction.

## 6. Storage and proposed migration `0045` (additive only; contingent on rulings)

The following is the recommended OD-46-2/3/4/5 Option-A shape. A ruling that selects release-candidate scope,
adds an authority registry, or adds executed review requires this section to be updated and re-reviewed.

Every new table is tenant-owned with `(project_id,tenant_id)→projects`, tenant FK, RLS `ENABLE`+`FORCE`,
`tenant_isolation`, `REVOKE ALL FROM PUBLIC`, and only required `SELECT,INSERT` grants to `uaid_app`.
UPDATE/DELETE/TRUNCATE are trigger-blocked. Every child FK includes project+tenant. Existing source/gate/finding
tables are not rewritten.

### 6.1 `acceptance_criterion_authorship_records` — append-only status/evidence chain

Proposed columns:

- identity: `id`, `tenant_id`, `project_id`, `acceptance_criterion_id`, `supersedes_record_id`, `sequence`,
  `created_at`;
- status/source: `authorship_status`, `authorship_provenance`, `source_kind`, nullable
  `extraction_proposal_id`, nullable `generated_artifact_id`, nullable `approval_id`, nullable
  `reviewer_instance_id`;
- safe snapshots selected by rulings: approval basis, generator/reviewer prompt-family/version/model-route
  hashes or IDs, bounded authority/source code, and optional evidence-reference digest (not prose).

Constraints/guards:

- Composite FK to `intake_artifacts(id,project_id,tenant_id)` plus a BEFORE-INSERT kind/parent guard proving
  `kind='acceptance_criterion'` with a same-project requirement parent; the canonical FK alone does not prove
  kind (`app/models/intake_artifact.py:56-71,81-90`).
- Optional composite FKs/guards prove the exact extraction proposal→promotion→artifact bridge, generated
  artifact→future promotion bridge if later ruled, approval subject/action/status/provenance, and reviewer
  instance lineage. All source fields are all-or-none and status/provenance coherent.
- Linear append-only chain: first record has no supersedes; later record must supersede the current latest for
  the same AC, with sequence + legal transition verified. No forks, gaps, same-status no-ops, delete, or update.
- `user_authored` cannot be inferred from a NULL source link. Extraction-promoted ACs can be DB-classified as
  system-derived, but no historical approval is relabelled trusted. Existing rows need no guessed backfill.
- Index supports current-record lookup `(tenant,project,acceptance_criterion_id,sequence DESC,id DESC)`.

### 6.2 `acceptance_verification_runs` — immutable exact-binding parent

Proposed columns:

- binding: `id`, `tenant_id`, `project_id`, optional ruled `release_candidate_id`, `scope_digest`,
  `authorship_digest`, `schema_version`, `verifier_contract_hash`, `created_at`;
- execution: `execution_status` (`succeeded|failed|refused`), `execution_provenance='system_executed_structural'`,
  nullable bounded `failure_code`;
- trigger-verified snapshots: `reported_scope_count`, `reported_eligible_count`,
  `reported_unapproved_count`, `reported_disputed_count`, `reported_missing_or_untrusted_count`,
  `evidence_consistent`, and `verdict` (`eligible|blocked`). Public code may not independently set derived
  truth.

Constraints/guards:

- Exact schema/hash/enums/count/nullability. Failed/refused runs have no result children and cannot be
  `eligible`; succeeded runs require a non-empty scope.
- A DEFERRABLE INITIALLY DEFERRED parent/child verifier recomputes membership equality, current-authorship
  record selection, per-reason counts, digests, evidence consistency, and verdict. Direct SQL cannot mark an
  empty/partial/untrusted run eligible.
- Latest-selection index covers the exact ruled binding and `(created_at DESC,id DESC)`; no uniqueness
  constraint erases rerun history. Under OD-46-3 A, a later failed attempt for the same exact digest supersedes
  an older pass; a changed current digest makes the old run non-current.

### 6.3 `acceptance_verification_results` — immutable per-AC evidence

Proposed columns: `id`, tenant/project/run IDs, `acceptance_criterion_id`,
`authorship_record_id`, `authorship_status`, `authorship_provenance`, `source_kind`, `eligibility_status`,
bounded `reason_code`, boolean `generated_origin_db_proven`, approval/reviewer control booleans and safe
lineage hashes selected by the rulings, and `created_at`.

Constraints/guards:

- Composite FKs bind run, AC, and authorship record to the same tenant/project; one result per `(run,AC)`.
- Snapshot fields must equal the referenced current authorship record and ruled source/approval facts. The DB
  derives/verifies eligibility; a caller cannot override it.
- `eligible` is impossible for missing/untrusted evidence, `system_authored_unapproved`, unresolved
  `disputed`, unsupported basis, non-current authorship record, wrong approval subject/action, failed approval,
  same-actor approval where separation is required, or incomplete lineage.

### 6.4 Optional `release_candidate_acceptance_bindings` (only if OD-46-2/3 select release scope)

If selected, this table is append-only and freeze-locked like Slice-25 issue bindings: composite FKs to the
candidate and canonical AC, unique membership, inserts only while `draft`, no unbind, and a DB-proven scope
digest/completeness rule before candidate freeze. The existing issue binding and candidate lifecycle must not
be semantically widened silently. This optional table is **not** part of the recommended project-wide scope.

### 6.5 Audit and sensitive-data boundary

Audit only IDs, project/release IDs where ruled safe, schema/contract versions or hashes, statuses, provenance
tiers, reason-code enums, safe counts/booleans, and lineage IDs/hashes already approved for audit. Never audit
AC ref/title/body/data, document/proposal/generated-artifact content, evidence quote, approval payload/note,
authority prose, prompt family text, prompt/model response, source URL, repo/commit, credential, token, secret,
or arbitrary JSON. Verification tables contain no duplicated AC prose. Existing source content remains in its
current RLS-protected table and is not claimed secret-free.

## 7. Repository/orchestrator behavior

Proposed `app/repositories/acceptance_verification.py` owns the only verification write path:

1. Resolve the tenant/project and coordinator-ruled scope from canonical DB rows; reject empty, malformed,
   wrong-kind, cross-project, duplicate, incomplete, or unruled scope before writing an eligible result.
2. Load the current append-only authorship chain for every member. Positively identify extraction-promoted
   system origin through the exact promotion bridge; never infer user authorship from absence.
3. Resolve and validate the ruled approval/authority/reviewer evidence. Keep `caller_supplied_unverified`,
   `request_authenticated`, DB-lineage, and any future signed/verified tiers distinct. Never accept a caller
   `trusted`, `eligible`, `passed`, or final gate value.
4. Canonicalize and hash the exact membership/current-authorship/verifier binding. Execute the pure structural
   verifier; no LLM, connector, test, or product behavior runs.
5. In one transaction append the run and one result per scope member plus content-free audit. Deferred guards
   recompute counts/digests/verdict at commit. A safe validation failure may append a failed/refused run with no
   children; it never preserves an old pass as current for the same binding.
6. `coverage_for_project()` returns safe booleans/counts only: scope/binding resolved, run present,
   execution failed/refused, scope count, missing-authorship count, untrusted count, unapproved-generated
   count, disputed count, unsupported-basis count, inconsistent count, eligible count, and whether approval
   provenance is limited. It returns no AC refs/prose, actor names, approval notes, source IDs exposed as
   strings, or raw lineage content.

No public method accepts current-chain status, trusted provenance, scope completeness, aggregate counts without
matching children, verdict, or gate status as caller facts.

## 8. A5 gate #8 and readiness — exact proposed change

### 8.1 A5 changes

`app/release/production_autonomy.py` and `app/repositories/production_autonomy.py` change only to replace the
obsolete boolean/context-only gate #8 with the ruled evidence ladder. Remove or retire
`generated_ac_provenance_ok`; the repository reads `AcceptanceVerificationRepository.coverage_for_project()`.
The A5 ruleset advances to **`slice46.v1`** because gate #8’s inputs, reasons, and possibly PASS path materially
change (`app/release/production_autonomy.py:125-206,234-240`; current version line 59).

Proposed ladder, with exact PASS behavior contingent on OD-46-1:

1. unresolved critical/release scope → `insufficient_evidence:acceptance_scope_unresolved`;
2. unresolved exact binding → `insufficient_evidence:acceptance_binding_unresolved`;
3. empty/unproven scope → `insufficient_evidence:no_proven_release_gating_acceptance_scope`;
4. no current exact-binding verification run → `insufficient_evidence:acceptance_verification_not_run`;
5. latest run failed/refused → `insufficient_evidence:acceptance_verification_failed`;
6. missing/ambiguous/non-current authorship record → `insufficient_evidence:acceptance_authorship_missing`;
7. untrusted authorship/approval/authority/lineage under OD-46-1 →
   `insufficient_evidence:authorship_approval_unverified`;
8. any unresolved `disputed` AC → `insufficient_evidence:disputed_acceptance_criteria_in_release_scope`;
9. any `system_authored_unapproved` AC →
   `insufficient_evidence:unapproved_generated_acceptance_criteria_in_release_scope`;
10. unsupported approval basis or failed independence/no-drift control →
    `insufficient_evidence:acceptance_authorship_controls_failed`;
11. run/result/count/digest inconsistency → `insufficient_evidence:acceptance_evidence_inconsistent`;
12. **only if OD-46-1 authorizes a PASS path and every non-empty in-scope AC is current, trusted, and
    binding-eligible with zero unapproved/disputed items** →
    `passed:no_unapproved_generated_acceptance_criteria_in_critical_gates_verified` (or a limitation-labelled
    reason if the coordinator explicitly selects a weaker provenance option).

Context contains bounded safe counts/booleans only. It must expose a limitation flag/tier when applicable and
must never flatten REPORTED, custody-authenticated, DB-lineage, and independently verified evidence.

### 8.2 What does not change

- Gates #1–#7 and #9–#13 remain semantically identical for identical inputs; tests compare every serialized
  gate dict other than #8 and preserve ordering 1..13.
- Gate #4 remains test-oracle execution; gate #8 never consumes a test pass as authorship approval. Gate #6’s
  `acceptance_silently_skipped` shortcut category does not satisfy acceptance authorship verification.
- Slice-23/44/45 `release_findings` tables, attachments, guard function, triggers, grants, security/shortcut
  coverage, and gates #5/#6 remain untouched. Migration `0045` creates no finding column or provenance value.
- `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- Even if gate #8 becomes PASS-capable, it would be the eighth PASS-capable A5 gate overall (#1/#2/#3/#4/#5/
  #6/#8/#11), an **inference from the current evaluator** that tests must derive rather than trust as prose.
  Gates #7/#9/#10/#12/#13 remain unmet (`CLAUDE.md` Current status; `production_autonomy.py:1-50`).
- `a5_satisfied` remains the conjunction of all 13 gates, and `can_go_live_autonomously` remains hard-false;
  the request-authenticated A5 preapproval still does not exist (`production_autonomy.py:46-50,66-69,96-114`).

## 9. Test plan for the eventual implementation

### 9.1 Pure / Docker-free

- Exact six-status taxonomy and template parity; unknown/blank/extra statuses refused.
- Eligibility matrix for every status × provenance/approval-basis combination selected by OD-46-1/6;
  `system_authored_unapproved` and unresolved `disputed` always block; normalized-user no-drift requirement;
  unsupported domain/reference bases fail closed.
- Source mapping: extraction promotion positively classifies system origin; missing link never classifies user
  origin; generated artifact without canonical promotion cannot enter scope; wrong/ambiguous source shapes fail.
- Scope: non-empty exact set, duplicate/wrong-kind/cross-project/missing members, all-project conservative
  scope, task/release variants if ruled, count cap, stable ordering and digest.
- Binding/latest-wins: changed AC membership, authorship chain, dispute/approval record, release candidate, or
  verifier contract invalidates old evidence; later failed/refused attempt supersedes old pass for the same
  binding; no TTL under OD-46-3 A.
- Dispute chain: initial state, dispute insertion, disputed blocking, legal ruled resolution by appended record,
  fork/gap/self-supersession/same-status/illegal transition refusal.
- Strict schema/bounds: malformed hashes/UUIDs, missing/extra fields, oversized/blank strings, over-cap counts,
  duplicate results, caller-supplied `eligible/complete/passed/trusted/gate` fields.
- Gate #8: every ladder rung, exact reason precedence, safe context, limitation exposure, PASS only under the
  coordinator-ruled evidence tier, empty scope never passes, and no unverified approval silently becomes
  “verified.”
- A5 regression: `slice46.v1`; only gate #8 changes; representative reports keep `a5_satisfied=false` and
  go-live false. Readiness module hash/output remains `slice20.v1`.

### 9.2 DB-backed and direct-SQL adversarial tests

- Migration round trip `0044→0045→0044→0045`; head/model/catalog parity; only ruled additive objects; no
  historical row relabel/backfill; downgrade removes only Slice-46 objects and restores `0044` exactly.
- RLS same-tenant success/cross-tenant invisibility; PUBLIC revoked; exact least grants; RLS ENABLE+FORCE;
  every run/result/authorship/optional-release child composite FK rejects cross-project/tenant references.
- UPDATE/DELETE/TRUNCATE refused on every new evidence/history table; rerun/authorship/dispute history retained.
- Direct SQL rejects wrong-kind/non-parent AC, fabricated user/system status, missing/contradictory source link,
  extraction source without exact promotion bridge, generated draft without exact canonical bridge, wrong
  approval action/subject/project/status/provenance, self-approval, missing authority/lineage, wrong reviewer
  project, unsupported basis, duplicate/forked/non-current chain, disputed→eligible without ruled resolution,
  caller-derived verdict/count/digest, empty/partial scope, stale authorship record, malformed/blank/oversized
  values, and result/aggregate mismatch.
- If release scope is ruled: binding only while candidate draft, same-project AC, no unbind, freeze locks
  membership, direct-SQL freeze without complete scope refused, and candidate change invalidates evidence.
- Audit sentinel injects AC prose, source text, evidence quote, approval note, actor/authority strings, secret-like
  values, prompt text, URLs, and credentials into source rows and proves Slice-46 audit contains safe metadata
  only; no content is duplicated into verification tables.
- Re-prove the canonical spine/provenance guards: ≥1 source at commit, accepted-document pinning, same-project
  parent/source FKs, append-only, classification CHECK, and RLS (`0014`).
- Re-prove extraction/generator boundaries: proposal content/identity immutability, distinct-label review,
  promotion exact bridge/promote-once, generated-artifact one-way status/evidence guard, no generator-spine
  promotion, and no trust upgrade of existing rows (`0017`, `0018`, `0035`).
- **Layered finding-guard preservation:** prove migration `0045` does not replace or alter
  `release_findings_guard()` or its triggers/constraints/grants; rerun direct-SQL adversarial cases for every
  Slice-23 lifecycle rule, every Slice-44 security attachment/provenance/count rule, and every Slice-45 shortcut
  attachment/provenance/independence/count rule (`migrations/versions/0022_release_findings.py`,
  `0043_security_scan_provenance.py`, `0044_shortcut_detector_execution.py`). Gates #5/#6 serialize identically.
- Production-autonomy repository uses only current exact acceptance evidence. Missing/untrusted/manual labels do
  not satisfy scope; unapproved/disputed always block; ruled trusted complete evidence can change **only gate
  #8**. Cross-tenant/nonexistent projects leak no IDs or prose.

### 9.3 Verification commands (eventual implementation only)

`git diff --check`; Ruff; focused pure tests; focused DB tests; `make test`; `make test-db`; migration
`0044→0045→0044→0045`; CI. These are future implementation review requirements, not commands authorized by
this plan-only task.

## 10. Proposed file touch map (eventual implementation only)

- New, contingent on rulings: `app/verify/acceptance.py`, models for authorship/run/result evidence,
  `app/repositories/acceptance_verification.py`, `migrations/versions/0045_acceptance_verification.py`, and
  `tests/test_acceptance_verifier.py`.
- Modify minimally for model registration: `app/models/__init__.py`.
- Modify only as required by ruled source binding: `app/repositories/extraction.py` and/or
  `app/repositories/generator.py`; do not duplicate promotion or silently relabel historical records.
- Optional only under OD-46-2/3 release scope: a release-candidate AC-binding model/repository method and exact
  freeze-completeness guard. Existing issue bindings remain semantically unchanged.
- Modify for gate #8 only: `app/release/production_autonomy.py`,
  `app/repositories/production_autonomy.py`, and focused golden/API tests.
- `app/intake/readiness.py`, all Slice-23/44/45 finding/security/shortcut modules and migration guards, and all
  other gates must remain unchanged.
- No branch, implementation file, migration, test, or PR is authorized until this plan is approved and
  OD-46-1 through OD-46-7 are explicitly ruled. This plan file is the sole deliverable now.

## 11. Must NOT claim

- Must NOT claim an AC is user-authored because no extraction/generator link was found.
- Must NOT claim extraction `approved` means §7.3 authorship approval; it currently proves only a distinct
  caller label and the proposal→promotion structure.
- Must NOT claim a Slice-36 `*_approved` generated artifact is a binding canonical AC; it is outside the spine,
  and its actor/lineage labels are explicitly unverified.
- Must NOT claim `request_authenticated` is a human signature, product-owner/domain authority, or proof the
  principal authored/read/understood the criterion.
- Must NOT let `caller_supplied_unverified` approval silently satisfy a “verified” gate reason. If the
  coordinator accepts a weaker tier, the limitation must be explicit in the reason/context and later A5 work.
- Must NOT claim a distinct string, instance, blueprint, prompt family, model route, approval row, or qualified
  flag alone proves independent thought, competence, semantic review, or human authority.
- Must NOT claim an empty scope, empty AC set, missing authorship rows, caller count, or absence of disputed/
  unapproved records proves gate #8.
- Must NOT claim task-contract AC links or release-candidate membership are complete merely because populated.
- Must NOT claim authorship eligibility proves AC quality, no meaning drift, implementation, product behavior,
  oracle pass, user-request satisfaction, release readiness, or evidence-pack completeness.
- Must NOT mutate or erase authorship/dispute history; a later eligible record does not make the earlier dispute
  nonexistent.
- Must NOT copy or audit AC/source/proposal/generated-artifact prose, evidence quotes, approval notes, prompts,
  model responses, secrets, credentials, or arbitrary JSON.
- Must NOT claim Slice 46 implements reviewer QA (Slice 48), issue provenance (Slice 47), evidence-pack audit
  (Slice 49), release verdict (Slice 50), production preapproval, deployment, or go-live.
- Must NOT claim gate #8 changes gate #4/#5/#6 or any other gate; all other gate algorithms and contexts remain
  regression-proven identical.
- Must NOT claim readiness changes; it remains byte-stable `slice20.v1`.
- Must NOT claim a passing gate #8 means A5 is satisfied or production may deploy. Go-live remains hard-false.

## 12. Definition of done for the eventual implementation — not this plan

After explicit plan approval and all coordinator rulings: every ruled non-empty release-gating canonical AC is
exactly scoped and carries an append-only, source-bound, current authorship record; direct/extraction/generated
paths retain their honest provenance class; unapproved/disputed/missing/untrusted/unsupported evidence fails
closed; any coordinator-accepted approval limitation is explicit and never renamed verified; the structural
acceptance verifier produces immutable exact-binding per-AC evidence with DB-recomputed counts/digests/verdict;
direct SQL cannot fabricate authorship, approval, scope, chain state, eligibility, or PASS; every new table is
tenant-owned, RLS ENABLE+FORCE, append-only, composite-FK-pinned, bounded, and audited with safe metadata only;
gate #8 follows the ruled ladder under A5 ruleset `slice46.v1`; all other gates—including Slice-23/44/45 layered
finding behavior—are regression-proven unchanged; readiness is byte-stable `slice20.v1`; go-live remains
hard-false; migration `0045` round-trips; pure suite, DB suite, and CI pass. Sources: spec §7.1–7.3, §13.1,
Appendix B #8 (`spec:633-673,1228-1236,2981-2997`), template 08, roadmap Slice 46
(`roadmap:433-443`), Slice-42/43/45 house patterns, and repository constraints cited throughout.

---

**Review request:** **APPROVE or REJECT this plan only.** On rejection, identify the exact section and required
correction. On approval, the coordinator must still rule OD-46-1 through OD-46-7 before any branch, code,
migration, tests, or PR begins. This file is the sole authorized deliverable for the present task.
