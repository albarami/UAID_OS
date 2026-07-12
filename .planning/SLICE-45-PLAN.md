# Slice 45 — Shortcut detector execution (A5 gate #6) — PLAN v1

**Status:** MERGED — historical record. Implemented via PR #80 (squash commit `d063ebe`); this v1 plan is retained as the approved design rationale for Slice 45.

> **Persona.** Senior verification-platform and PostgreSQL governance architect, applying fail-closed
> evidence design, tenant isolation, independent-review controls, and Sanad / No-Free-Facts discipline.
>
> **Primary Sanad.** UAID forbids placeholder features, fake production data, demo-only behavior presented
> as implementation, hardcoded test-passing output, simulated required integrations, skipped acceptance
> criteria, weakened tests, silent/broad error swallowing, required-path TODOs, local-only substitutes,
> evidence-free completion, and requirement weakening; it must prefer an honest blocker over fake completion
> (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:129-149`). Consequential output requires
> an independent checker, and high-risk output requires multiple reviewers (`spec:151-159`). The §13.4
> Shortcut Detection Agent checks twelve named shortcut classes (`spec:1298-1313`). The reviewer archetype is
> evaluated for defect/weak-test/fake-integration/unsupported-claim detection using planted-defect corpora,
> critical-defect recall, specificity, evidence use, and no rubber-stamping (`spec:912-930`, especially line
> 919). Appendix-B A5 gate #6 is exactly “no unaccepted critical shortcut findings are open”
> (`spec:2981-2991`, especially line 2990). The roadmap makes Slice 45 the sole next planned item and requires
> an independent shortcut review feeding the existing findings store with verified provenance, planted-
> shortcut fixtures, gate #6 PASS-capability, and no claim of shortcut absence without detector coverage
> (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:421-431`).
>
> **Verified repository Sanad.** `main` and `origin/main` are
> `13a1563e545500533e3f976994620dad9d786cbd`, the worktree was clean before this file was created, and no local
> or remote feature branch exists (`git rev-parse HEAD origin/main`, `git status --porcelain`, and
> `git branch -a --format=...`, verified 2026-07-12). Alembic reports `0043 (head)` and migration `0043`
> revises `0042` (`uv run alembic heads`; `migrations/versions/0043_security_scan_provenance.py:1-16`). The A5
> ruleset is `slice44.v1`; gate #6 still always returns
> `insufficient_evidence:no_finding_provenance_or_scan_source` from shortcut-finding counts only, while go-live
> is hard-false (`app/release/production_autonomy.py:39-48,57,95-112,123-190,349-357`). The A5 repository has
> no shortcut coverage source; it reads only project-wide open and open-critical shortcut counts
> (`app/repositories/production_autonomy.py:99-128,170-205,248-250`). Readiness remains the separate
> `slice20.v1` structural-intake evaluator (`app/intake/readiness.py:45`).
>
> **Existing-store and sibling Sanad.** The Slice-23 lifecycle already defines exactly twelve named shortcut
> categories plus `other`, requires new findings to be `open`, permits only one-way terminal transitions, and
> makes critical findings non-acceptable (`app/release/findings.py:1-13,18-92`). Slice 44 did not generalize
> shortcut execution: it added security-specific exact-commit connector-observed runs/category rows and
> security-only finding attachments (`app/verify/security_scan.py:1-37,157-227,367-445`;
> `app/repositories/security_scans.py:32-114,147-229`;
> `migrations/versions/0043_security_scan_provenance.py:37-223`). The current release-findings guard preserves
> both the Slice-23 lifecycle and the Slice-44 trusted security path
> (`migrations/versions/0043_security_scan_provenance.py:332-474`). Slice 43 supplies reusable system-executed
> blind LLM judgment, distinct evaluator lineage, injection refusal, budget/cost accounting, and exact-binding
> evidence patterns (`app/verify/judgment.py:1-32,75-99,102-201`;
> `app/repositories/test_oracles.py:430-529,563-621`). Those are precedents, not automatic authorization to
> reuse either sibling's truth claims.

## Coordinator rulings (final)

- OD-45-1 = Option A (UAID-executed hybrid over a connector-verified exact-commit corpus): extend the existing SCM boundary with one bounded/versioned review-corpus method; UAID runs code-owned deterministic detectors as candidate generators plus blind independent LLM reviewers over the same ruled corpus and rubric. Corpus retrieval recorded as connector_verified_ci_shortcut_corpus; deterministic and LLM calls separately labelled system_executed_* — a connector observation is never relabelled system-executed. Both layers must complete; either may create a finding; neither may erase the other. All CI LLM tests use FakeLLMClient; live network stays adapter-only.
- OD-45-2 = Option A (conservative independence): ≥2 active, qualified, same-project reviewer-archetype instances with distinct blueprint IDs, version hashes, AND model routes; blind calls; no reviewer blueprint may equal any active same-project builder blueprint; independence unresolved (gate cannot pass) if no builder blueprint is registered. Independence is claimed only as this DB-provable boundary — never as independence from actual Git authors.
- OD-45-3 = Option A: all twelve named §13.4 categories mandatory for gate-bearing coverage, no N/A; other is diagnostic/non-gating.
- OD-45-4 = Option A (shortcut-specific additive attachment): nullable shortcut_detector_category_result_id + shortcut_finding_fingerprint on release_findings; a ruled trusted shortcut provenance value; the Slice-44 security path preserved byte-for-byte semantically; downgrade restores the exact pre-0044 Slice-44 guard.
- OD-45-5 = Option A: exact declared repo + commit + current detector-contract hash, latest-wins, no wall-clock TTL; a later failed/refused run supersedes an older pass.
- OD-45-6 = Option A: append observations, never auto-close; the detector path never calls any lifecycle transition; dedupe per run only.
- OD-45-7 = Option A: versioned code-owned impact rubric derives severity from bounded factual flags; reviewer-emitted severity is REPORTED and never gates; unknown/contradictory flags fail the category; no silent critical downgrade is possible.
- OD-45-8 = recommended ruling: slice45.shortcut_review.v1 schema, slice45.detector.v1 code-owned contract, slice45.shortcut_fixtures.v1 planted corpus (≥1 expert-labelled positive per mandatory category + negative/edge/adversarial/injection/incomplete cases); the stated caps (corpus ≤8 MiB, ≤2,000 manifest entries, entry ≤256 KiB, extracted text ≤4 MiB, LLM packet ≤32,000 chars, result ≤2 MiB, ≤1,000 findings, summary ≤500, detail ≤4,000, evidence ref ≤500, keys/codes ≤128, all non-blank); raw corpus/prompts/responses/snippets never persisted or audited.

---

## 0. The defining honesty constraint (the crux)

Slice 45 must keep five claims separate:

1. **REPORTED:** a detector or reviewer reports that it inspected a category, identifies a possible shortcut,
   and assigns evidence labels. Its narrative, category, and impact judgment are claims by that named/versioned
   source—not objective truth. Reviewer competence is not proved merely by an active/qualified flag; current
   qualification evidence is itself `caller_supplied_unverified` even though its recorded aggregates are
   DB-checked (`app/models/qualification_run.py:1-9,63-108`).
2. **CONNECTOR-OBSERVED:** UAID fetched a bounded, versioned review corpus or result artifact for the exact
   declared repository and commit. This proves retrieval/binding/shape only. It does not prove that omitted
   code has no shortcuts, that the producer actually ran every claimed check, or that a reviewer was
   independent (`app/verify/security_scan.py:1-5`; Slice-44 honesty precedent
   `.planning/SLICE-44-PLAN.md:58-85`).
3. **SYSTEM-EXECUTED:** only checks or blind reviewer calls actually invoked by UAID may carry this label. A
   connector-observed CI result must never be relabelled `system_executed`. If LLM execution is ruled in,
   `system_executed` proves that the bounded prompt was sent and a strict response was parsed; it does not prove
   semantic correctness or detector completeness (`app/verify/judgment.py:151-201,226-243`).
4. **DB-PROVEN:** PostgreSQL may prove tenant/project/binding lineage, immutable run/reviewer/category/finding
   relationships, exact mandatory-category coverage, count agreement, distinct declared reviewer lineages,
   current finding lifecycle state, and critical-cannot-accept. It cannot prove that a heuristic detected every
   shortcut or that an LLM conclusion is true (`migrations/versions/0043_security_scan_provenance.py:226-329,
   332-474`).
5. **GATE-INFERRED:** after the coordinator rules the source, independence, scope, severity, and binding policy,
   complete trusted execution coverage plus zero currently open critical shortcut findings is sufficient for
   Appendix-B gate #6. A passing gate #6 is not proof that the repository is shortcut-free, all non-critical
   findings are harmless, A5 is satisfied, or production may deploy (`spec:2981-2997`).

**An empty `release_findings` store, an empty detector result, or a reviewer saying “clean” must never pass gate
#6 by itself.** A zero-finding outcome is gate-bearing only inside a trusted exact-binding run with DB-proven
coverage for every coordinator-ruled mandatory category and all ruled independence/execution controls. Missing,
partial, unsupported, oversized, untrusted, wrong-binding, failed, refused, count-inconsistent, self-reviewed,
or superseded evidence fails closed. Even a complete review proves only that the ruled system inspected the
ruled bounded corpus and did not report a critical shortcut; **detection is not proof of absence**.

## 1. Scope and non-goals

### 1.1 In scope after approval and all OD rulings

- A strict, versioned, bounded shortcut-review input/result contract for one exact declared repo and commit,
  with explicit corpus/detector/reviewer versions and no caller-supplied gate verdict (evidence-over-claims:
  `spec:160-193`; connector boundary precedent `app/release/scm_connector.py:38-65`).
- The coordinator-ruled execution path from OD-45-1, with epistemic labels kept exact: connector observation,
  deterministic system execution, and/or LLM system execution are recorded separately.
- Independent-review enforcement selected by OD-45-2. The system must not infer independence from a prompt
  phrase, a reviewer-supplied string, or different instance IDs alone; lineage must resolve through existing
  instance→version→blueprint relationships (`app/models/agent_instance.py:1-10`;
  `app/repositories/task_contracts.py:182-215`).
- One-to-one consideration of the twelve §13.4 checklist items through the existing twelve named
  `SHORTCUT_CATEGORIES`; `other` remains diagnostic/non-gating unless the coordinator explicitly rules
  otherwise (`spec:1298-1313`; `app/release/findings.py:30-49`).
- Reuse of `release_findings` as the only shortcut-finding lifecycle store. The minimal additive provenance
  attachment is selected by OD-45-4; no parallel finding lifecycle is permitted.
- Proposed additive migration **`0044_shortcut_detector_execution`** after verified head `0043`. The number and
  name are an **inference from the repository's monotonic revision sequence**, not a spec fact; this plan does
  not create a migration.
- Tenant-owned evidence tables with RLS `ENABLE`+`FORCE`, composite tenant/project FKs, append-only
  UPDATE/DELETE/TRUNCATE guards, deferred aggregate verification, bounded non-blank text, and audit
  safe-metadata only (current sibling pattern `migrations/versions/0043_security_scan_provenance.py:111-223,
  226-329,477-502`).
- Compute-on-read, exact-binding, latest-wins gate-#6 coverage and a fail-closed A5 ladder. If gate #6 becomes
  PASS-capable, the A5 report ruleset must advance from `slice44.v1` to proposed **`slice45.v1`** because gate
  semantics materially change (`app/release/production_autonomy.py:57,349-357`).
- Pure and DB-backed tests, planted-shortcut fixtures, direct-SQL adversarial tests, and exact regression proof
  for every existing Slice-23 and Slice-44 guard rule.

### 1.2 Non-goals

- No reviewer-QA subsystem, miss-rate governance, reviewer challenge sampling, or calibration authority; those
  remain Slice 48. Slice 45 may enforce the minimal ruled execution/independence controls required for gate #6,
  but must not claim full §13.5 reviewer QA (`spec:1315-1345`; roadmap
  `.planning/GO-LIVE-END-TO-END-ROADMAP.md:457-467`).
- No acceptance verifier, acceptance-authorship gate, or gate #8 change (Slice 46); a shortcut reviewer may
  report `acceptance_silently_skipped`, but cannot certify acceptance (`roadmap:433-443`).
- No security-scanner or gate #5 change. Security coverage, tables, finding attachments, reasons, and counts
  remain exactly Slice-44 behavior (`app/release/production_autonomy.py:267-348`).
- No arbitrary detector plugins, uploaded executable, shell command, user-supplied Python/rule code, dynamic
  import, or unbounded repository execution. Only coordinator-ruled code-owned detectors/contracts may be
  gate-bearing (deny-by-default inference from tool/connector controls, `spec:1084-1127,1676-1684`).
- No automatic patching, remediation, issue creation, finding resolution, false-positive marking, acceptance,
  supersession, or risk acceptance. The detector write path only appends observations/findings.
- No claim of repository-wide semantic completeness from pattern matching, a planted-fixture suite, a bounded
  corpus, an LLM panel, or agreement among reviewers.
- No HTTP endpoint, UI, scheduler, production deployment, new approval authority, or public detector trigger.
- No readiness change: `app/intake/readiness.py` must remain byte-stable at `slice20.v1`. Intake completeness is
  not shortcut-review execution evidence (`app/intake/readiness.py:45`; `CLAUDE.md:505-539`).

## 2. Required checklist and coverage semantics

### 2.1 Canonical mapping (scope still requires OD-45-3)

The existing taxonomy is a direct, code-owned normalization of the twelve §13.4 bullets:

| Spec checklist item | Existing `release_findings` category | Source |
|---|---|---|
| hardcoded values | `hardcoded_value` | `spec:1302`; `app/release/findings.py:31-33` |
| static responses replacing real behavior | `static_response` | `spec:1303`; `findings.py:33` |
| fake external integrations | `fake_integration` | `spec:1304`; `findings.py:34` |
| disabled validation | `disabled_validation` | `spec:1305`; `findings.py:35` |
| removed or weakened tests | `weakened_tests` | `spec:1306`; `findings.py:36` |
| broad error swallowing | `error_swallowing` | `spec:1307`; `findings.py:37` |
| placeholder UI | `placeholder_ui` | `spec:1308`; `findings.py:38` |
| TODOs in required paths | `todo_in_required_path` | `spec:1309`; `findings.py:39` |
| local-only production-service substitutes | `local_only_substitute` | `spec:1310`; `findings.py:40` |
| acceptance criteria silently skipped | `acceptance_silently_skipped` | `spec:1311`; `findings.py:41` |
| tests checking implementation, not behavior | `tests_check_implementation` | `spec:1312`; `findings.py:42` |
| readiness claims without evidence | `readiness_without_evidence` | `spec:1313`; `findings.py:43` |

`other` exists in the lifecycle taxonomy but has no corresponding §13.4 checklist item; under the recommended
OD-45-3 ruling it is non-gating (`app/release/findings.py:44,84-86`). This mapping proves nomenclature only; it
does not prove that one execution method can detect all twelve classes.

### 2.2 Non-vacuous coverage

- **Coverage is per category, not per finding.** Every mandatory category needs an immutable result even when it
  produces zero findings; otherwise “no shortcut detected” is indistinguishable from “that check never ran.”
  This is the same structural lesson applied to gate #5 (`.planning/SLICE-44-PLAN.md:138-164`).
- **Clean is derived, never supplied.** A category result may be `completed_clean`,
  `completed_with_findings`, `failed`, `refused`, or `unsupported`; only the two `completed_*` outcomes count
  as coverage. `completed_clean` requires zero attached findings; `completed_with_findings` requires at least
  one. These labels are proposed implementation vocabulary, not spec terms.
- **Every ruled engine must finish.** Under a hybrid ruling, a deterministic component finishing cannot mask a
  missing/refused reviewer component, and a reviewer “clean” response cannot mask a detector finding. Any
  trusted component's shortcut finding is appended; unresolved component disagreement cannot become clean.
- **Corpus scope is explicit.** The run records a manifest/digest for the exact bounded review corpus. Any
  omitted required path, unsupported content, truncation, silent sample, over-cap file, or manifest mismatch
  makes coverage incomplete. The corpus proves what was reviewed, never universal repository completeness.
- **Findings stay lifecycle records.** New observations enter the existing store as `open`; the review path does
  not mutate older rows. Critical findings cannot become `accepted` under the existing rule
  (`app/release/findings.py:9-13,51-92`).

## 3. Evidence, independence, and verdict model

### 3.1 Separate provenance axes

- `corpus_provenance` says how exact-commit input was obtained. A connector-verified corpus may be gating only
  under the ruled contract; caller-supplied input remains explicitly unverified/non-gating.
- `execution_provenance` says who ran the check: proposed values are specific, such as
  `system_executed_deterministic`, `system_executed_llm_review`, or `connector_observed_ci_review`. A combined
  label must not collapse these facts.
- `detector_contract_hash` pins the code-owned category rules, prompt/rubric, normalization, planted-corpus
  version, and aggregation policy selected by OD-45-1/7/8. A changed contract requires a new run.
- Reviewer lineage snapshots instance, blueprint, version hash, model route hash, qualification state/source,
  and blind-call status. DB FKs prove registered lineage; they do not prove reviewer competence or truth.
- Run/category/reviewer verdicts are recomputed or commit-time verified from children. Public methods do not
  accept `coverage_complete`, `clean`, `independent`, gate status, or trusted provenance as caller facts.

### 3.2 Independence boundary

The repository can resolve an agent instance to its version and blueprint and can enforce blueprint
distinctness (`app/repositories/task_contracts.py:182-215,359-366`; migration guard
`migrations/versions/0041_task_contracts.py:599-626`). It cannot currently bind an exact Git commit to the
complete set of actual human/agent authors. Therefore Slice 45 must state independence narrowly as the ruled,
DB-checkable relationship (for example, distinct from every active registered same-project builder blueprint),
not “independent of everyone who wrote this commit.” This limitation is the reason OD-45-2 is blocking.

### 3.3 Latest-wins and open-finding interaction

Under OD-45-5, the gate reads only the latest committed attempt for the exact current binding and current
detector contract, ordered `(created_at DESC, id DESC)`. A later failed/refused/incomplete run supersedes an
older passing run; history remains append-only. Separately, gate #6 counts **all currently open critical
shortcut findings for the project regardless of provenance**. A manually reported critical is sufficient
blocker evidence even though it cannot establish detector coverage. A later clean result never closes it.

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-45-1 — What actually executes the §13.4 review?

**Gap:** the repo has no shortcut executor or review-corpus connector. A pure scanner artifact pattern would
prove only connector observation, while several §13.4 classes are semantic review judgments rather than
reliable text patterns (`spec:1298-1313`; current absence evidenced by gate #6 at
`app/release/production_autonomy.py:349-357`).

**Options:**

- **A — UAID-executed hybrid over a connector-verified exact-commit corpus (recommended):** extend the existing
  SCM boundary with one bounded/versioned review-corpus method. UAID runs code-owned deterministic detectors
  as candidate generators and then blind independent LLM reviewers over the same ruled corpus and rubric.
  Record corpus retrieval as `connector_verified_ci_shortcut_corpus`; deterministic and LLM calls separately
  as `system_executed`. Both layers must complete; either may create a finding; neither may erase the other.
  This honestly combines repeatable mechanical checks with semantic review, while preserving the bounded-
  corpus limitation. All CI LLM tests use `FakeLLMClient`; live network remains adapter-only.
- **B — connector-observed CI reviewer-result artifact:** mirror Slice 44 and fetch a bounded exact-commit
  `slice45.shortcut_review.v1` result produced in CI. Stamp `connector_observed_ci`, never `system_executed`.
  This is simpler but UAID does not witness detector/reviewer execution; claimed independence and coverage are
  reported unless separately cross-checked.
- **C — deterministic code-owned detectors only:** UAID can truthfully say `system_executed`, but pattern/rule
  coverage cannot honestly establish semantic review for fake integrations, silent acceptance skips,
  behavior-vs-implementation tests, or evidence-free readiness. This option requires narrowing gate-bearing
  claims or leaving gate #6 insufficient.
- **D — LLM reviewer execution only:** UAID can execute an independent review over bounded untrusted input and
  reuse Slice-43 controls, but loses deterministic candidate generation and remains model-sensitive. It still
  cannot claim full-repository completeness.

**No ruling ⇒** gate #6 remains `insufficient_evidence:no_finding_provenance_or_scan_source`.

### OD-45-2 — What exact reviewer-independence and panel rule is gate-bearing?

**Options:**

- **A — conservative project-wide builder exclusion plus a two-reviewer panel (recommended):** require at least
  two active, same-project agent instances whose blueprints use the `reviewer` archetype and whose realizations
  are currently marked qualified; reviewers have distinct blueprint IDs, version hashes, and model routes;
  calls are blind; and no reviewer blueprint may equal any active same-project `builder` blueprint. Require at
  least one registered builder blueprint, otherwise independence is unresolved. Any reviewer detection creates
  a finding; disagreement or incomplete responses fails clean coverage. This proves separation from registered
  project builders, not actual Git authorship. Qualification remains limited by its current unverified-source
  caveat (`app/models/qualification_run.py:1-9`).
- **B — task-contract builder set:** bind the run to selected Slice-42 task contracts and exclude their builder
  blueprints. This is more precise for registered tasks, but no current schema proves those contracts exhaust
  the authors/work represented by the exact commit; a completeness authority must be added or the claim stays
  declared-only (`app/models/task_contract.py:1-10,67-108`).
- **C — one distinct reviewer:** satisfies the minimum independent-checker phrase but conflicts with the spec's
  multiple-reviewer rule for high-risk outputs if a production gate is treated as high-risk (`spec:151-157`).
- **D — connector-reported reviewer identity:** non-gating unless every identity/lineage/qualification claim is
  resolved to current DB records and the ruled independence relationship is enforced.

**No ruling ⇒** `shortcut_review_independence_resolved=False`; gate #6 cannot pass.

### OD-45-3 — Which categories are mandatory, and is N/A allowed?

- **A — all twelve named §13.4 categories mandatory, no N/A (recommended):** require every non-`other`
  `SHORTCUT_CATEGORIES` value. A project without UI can still complete `placeholder_ui` review by proving the
  ruled corpus was inspected and no placeholder UI was reported; N/A is unnecessary. This is a conservative
  inference from §13.4, not explicit Appendix-B wording.
- **B — reviewed applicability matrix:** allow `not_applicable` only through a new independently approved,
  exact-binding applicability artifact. No such authority exists today; it expands scope and must itself be
  reviewed.
- **C — a smaller deterministic subset:** cannot represent execution of the full §13.4 checklist and therefore
  cannot make gate #6 PASS-capable under the roadmap commitment.

`other` remains non-gating in Options A/B. **No ruling ⇒** `shortcut_review_scope_resolved=False`.

### OD-45-4 — How does verified shortcut provenance attach to `release_findings`?

- **A — shortcut-specific additive direct attachment (recommended):** add nullable
  `shortcut_detector_category_result_id` and `shortcut_finding_fingerprint`; add a ruled trusted shortcut
  provenance value; composite-link `(category-result,project,tenant,category)`; require all trusted fields
  together with `finding_type='shortcut'`. Preserve the existing security-specific columns and guards without
  semantic widening. Existing/manual shortcut rows remain unverified.
- **B — generalize Slice-44 security objects into neutral verification objects:** could reduce future schema
  duplication, but renaming/reinterpreting merged security tables and columns is not additive-only and risks
  altering approved gate #5 semantics. Rejected as the default for this bounded slice.
- **C — append-only shortcut-finding binding table:** leaves `release_findings.source_provenance` unverified and
  attaches a separate trusted binding. This avoids new finding columns but creates two provenance surfaces and
  makes row-level truth harder to explain.

**No ruling ⇒** detector coverage may not create trusted shortcut findings and gate #6 cannot pass.

### OD-45-5 — What binding and staleness policy selects current evidence?

- **A — exact declared repo + commit + current detector-contract hash, latest-wins, no TTL (recommended):** any
  repo, commit, or contract change requires a new run; the latest attempt for that exact binding supersedes an
  older pass, including a later failure. The corpus digest is recorded and must match that run, but cannot
  partition selection so an older clean corpus remains current. This mirrors Slice-43/44 exact-binding policy
  (`app/repositories/security_scans.py:65-114`; `.planning/SLICE-43-PLAN.md` Ruling OD-43-5).
- **B — frozen release-candidate binding:** current candidates do not carry repository/commit identity, so this
  requires a separate reviewed design (`app/models/release_candidate.py:29-66`).
- **C — exact binding plus wall-clock TTL:** neither §13.4 nor Appendix B supplies a universal expiry duration;
  the coordinator must provide the policy and value.

**No ruling ⇒** `shortcut_review_binding_resolved=False`; gate #6 cannot pass.

### OD-45-6 — What does a later run do to earlier findings?

- **A — append observations, never auto-close (recommended):** the detector path never calls
  `resolve`, `mark_false_positive`, `accept`, or `supersede`; dedupe is within one run only. A prior open
  critical remains blocking until the explicit existing lifecycle closes it.
- **B — auto-supersede absent fingerprints after a later clean run:** rejected as the default because absence
  in a bounded/model-sensitive review is not proof of remediation or false positive.
- **C — update/reuse a finding across runs:** conflicts with immutable identity/content/source and erases
  observation history (`migrations/versions/0043_security_scan_provenance.py:332-474`).

**No ruling ⇒** implementation remains blocked; safety defaults do not substitute for coordinator authority.

### OD-45-7 — How is shortcut severity derived?

**Gap:** §13.4 names categories but no severity algorithm; the existing store requires
`low|medium|high|critical`, and Appendix-B gate #6 depends specifically on critical findings
(`app/release/findings.py:18-20,55-86`; `spec:2990`).

- **A — versioned code-owned impact rubric (recommended):** reviewers/detectors return bounded factual impact
  flags and evidence; pure code maps the ruled flag combinations to the four existing severities. Unknown,
  incomplete, or contradictory flags fail the category/run. Reviewer-supplied free-form severity never
  directly gates. The rubric and hash require coordinator approval because the spec provides no universal map.
- **B — reviewer-emitted severity:** retain as REPORTED and non-gating unless independently normalized; otherwise
  a reviewer can downgrade a critical shortcut to make gate #6 pass.
- **C — every shortcut is critical:** maximally conservative but collapses the existing severity taxonomy and
  blocks on low-impact findings beyond Appendix B's explicit threshold.

**No ruling ⇒** no detected shortcut can receive gate-bearing severity provenance; gate #6 cannot pass.

### OD-45-8 — What schema, detector contract, bounds, and planted corpus are authoritative?

**Recommended ruling:** `slice45.shortcut_review.v1`; code-owned `slice45.detector.v1` manifest mapping all
ruled categories to deterministic candidate checks plus a strict reviewer rubric; code-owned
`slice45.shortcut_fixtures.v1` with at least one expert-labelled positive fixture per mandatory category plus
negative, edge, adversarial, prompt-injection, incomplete-input, and false-approval cases (fixture classes are
grounded in `spec:914-930`; exact fixtures are engineering policy). Proposed caps: corpus archive ≤8 MiB,
≤2,000 manifest entries, each text entry ≤256 KiB, extracted review text ≤4 MiB, LLM category packet ≤32,000
characters, result artifact ≤2 MiB, ≤1,000 findings, summary ≤500, detail ≤4,000, evidence ref ≤500, and
keys/codes ≤128; all required strings non-blank. Reject path traversal, links, encrypted members, duplicate
paths, unsupported required-path content, truncation, raw caller verdicts, unknown fields/categories/rules/
severity flags, NaN/Infinity, and over-cap values. Source content may be processed ephemerally but never
persisted or audited; secrets, raw snippets, arbitrary model output, and arbitrary scanner JSON never persist.

The planted suite proves detection of those known exemplars only. It must never be described as recall over all
possible shortcuts or proof of detector completeness. Numeric caps, corpus scope, rule mappings, prompt/rubric,
fixture contents, and normalization are proposed engineering choices—not spec facts—and require the ruling.

**No ruling ⇒** production inputs remain unsupported and gate #6 cannot pass.

## 5. Proposed execution modules (contingent on §4 rulings)

### 5.1 `app/verify/shortcut_detector.py`

- Frozen strict value objects for corpus manifest, detector definition, candidate observation, reviewer
  lineage/vote, normalized finding, category decision, run decision, and `Gate6Evidence`.
- Canonical JSON/hash helpers; strict field equality; exact SHA/digest shapes; unique normalized paths,
  categories, reviewers, and fingerprints; bounded non-blank text; no caller `clean`, `passed`, `independent`,
  `trusted`, or gate field.
- Code-owned deterministic candidate checks selected by OD-45-1/8. Candidate rules may raise findings; a clean
  rule result is not semantic proof for the category.
- Category aggregation requires every ruled execution component, every ruled reviewer, and consistent finding
  counts. Any detection wins over clean; disagreement/incomplete/refused inputs fail closed; unknown output is
  never silently dropped.
- Severity is derived only under OD-45-7; fingerprints are canonical digests of safe normalized identity fields,
  not raw snippets.

### 5.2 `app/verify/shortcut_review.py` (only if OD-45-1 includes LLM execution)

- Blind calls: each reviewer receives the same code-owned rubric and untrusted bounded category packet without
  builder summary, another reviewer identity, vote, or final gate label. The model returns strict factual flags
  and bounded finding records, never a caller-authoritative pass field.
- Reuse `as_untrusted_block`/injection scanning, validate all packets before the first call, cap model output,
  reject malformed/partial/extra output, and persist no prompt/response/source content
  (`app/verify/judgment.py:24-32,102-148,178-201`).
- Reuse existing price-card validation, projected budget refusal, actual token-cost events, provider/model/token
  shape checks, and failure/refusal taxonomy (`app/repositories/test_oracles.py:430-529,608-621`). Any call
  failure, unpriced route, exhausted budget, injection signal, disagreement, or missing reviewer makes the run
  non-covering. Every CI test injects `FakeLLMClient`; no live model/network test is permitted.

### 5.3 Existing connector extension

- Extend `SCMConnector`, `FakeSCMConnector`, and `GitHubSCMConnector` only as selected by OD-45-1. Resolve the
  repo through `resolve_declared_repo`; never accept a caller repo string at the trusted service boundary
  (`app/release/project_repo.py:40-60`).
- Fetch the exact commit and a fixed-name versioned corpus/result artifact. Enforce bounded streaming before
  accumulation, safe archive rules, no redirect credential leakage, and exact commit validation (existing
  archive boundary `app/release/scm_connector.py`; Slice-44 parser use
  `app/repositories/security_scans.py:36-63`).
- Live network stays adapter-only. Fake connector and `FakeLLMClient` are the only CI paths.

## 6. Storage and proposed migration `0044` (additive only; contingent on rulings)

The following is the recommended OD-45-1/2/4 Option-A shape. A different ruling requires this section to be
revised and re-reviewed before implementation.

Every new table is tenant-owned and receives `(project_id,tenant_id)→projects`, tenant FK, RLS
`ENABLE`+`FORCE`, `tenant_isolation` `USING`+`WITH CHECK`, `REVOKE ALL FROM PUBLIC`, and only required
`SELECT,INSERT` grants to `uaid_app`. UPDATE/DELETE/TRUNCATE are trigger-blocked. Every child FK includes
project+tenant. Append-only run evidence is distinct from the lifecycle-mutating `release_findings` store.

### 6.1 `shortcut_detector_runs` — immutable exact-binding parent

Proposed columns:

- IDs/binding: `id`, `tenant_id`, `project_id`, `provider`, `repo_binding_hash`, `commit_sha`,
  `schema_version`, `detector_contract_hash`, `corpus_digest`, `created_at`;
- epistemics: `corpus_provenance`, `deterministic_execution_provenance`,
  `review_execution_provenance`, `execution_status`, bounded nullable `failure_code`;
- deferred snapshots: reported category/reviewer/finding counts, `coverage_complete`, and
  `coverage_verdict`. Public code cannot set derived values independently of children.

Constraints/guards:

- exact enums/hash/SHA/caps and provenance/status/nullability coherence; failed/refused runs have no covering
  children and cannot be clean;
- deferred parent/child verifier recomputes mandatory category equality, ruled reviewer panel/lineage
  distinctness, per-category execution completion, finding counts, and coverage verdict;
- latest-selection index on tenant/project/repo/commit/current-contract/created_at/id; no uniqueness constraint
  erases rerun history.

### 6.2 `shortcut_detector_category_results` — immutable per-category coverage

Proposed columns: `id`, tenant/project/run IDs, `category`, deterministic rule-set hash/status,
review status, `coverage_status`, reported finding/reviewer counts, safe evidence digest, and `created_at`.
There is exactly one row per `(run,category)`. A composite unique target
`(id,project_id,tenant_id,category)` supports finding attachments. DB guards require the ruled category set,
component/status coherence, and `completed_clean` iff zero bound findings /
`completed_with_findings` iff at least one.

### 6.3 `shortcut_detector_reviewer_results` — immutable declared review evidence

Proposed columns: `id`, tenant/project/run/category IDs, `reviewer_instance_id`, snapshotted
`reviewer_blueprint_id`, `reviewer_version_hash`, model-route hash, blind-call boolean, execution status,
bounded decision/failure code, reported finding count, response digest, token counts/cost external ref when LLM
is used, and `created_at`.

Composite FKs bind the reviewer instance and category to the same tenant/project/run. Deferred guards enforce
the OD-45-2 panel size, unique reviewer per category, blueprint/version/model-route distinctness, project-wide
builder exclusion selected by the ruling, blind execution, and child-count agreement. A DB-proven row proves
registered lineage and recorded execution metadata, not competence or judgment truth.

### 6.4 Additive `release_findings` attachment (OD-45-4 Option A)

Proposed columns:

- nullable `shortcut_detector_category_result_id`;
- nullable `shortcut_finding_fingerprint` (`sha256:<64 lowercase hex>`).

The replacement guard must preserve **every current Slice-23 and Slice-44 rule** while adding one shortcut
path:

- manual path: both security and shortcut attachment pairs NULL; provenance remains
  `caller_supplied_unverified`;
- existing security path: current `connector_verified_security_scan` fields, limits, trusted parent/category
  checks, per-run dedupe, and immutability remain byte-for-byte semantically unchanged
  (`migrations/versions/0043_security_scan_provenance.py:339-385`);
- trusted shortcut path: shortcut pair non-NULL, security pair NULL, `finding_type='shortcut'`, ruled source
  provenance, bounded normalized source/summary/detail, derived severity, composite category-result binding,
  trusted successful parent, and unique per-run fingerprint;
- all original rules remain: created-open, category/type validation, `other` prose, immutable identity/content/
  source/attachments, one-way terminal lifecycle, critical-cannot-accept, accepted-record validation, finding
  event trail, no DELETE/TRUNCATE, and existing grants.

Existing rows need no backfill and may not be relabelled. Downgrade must restore the **exact pre-0044 Slice-44
guard**, including its security attachment path, before dropping shortcut-only columns/tables.

### 6.5 Audit and sensitive-data boundary

Audit only IDs, project ID, execution/coverage statuses, provenance tiers, safe counts, schema/contract version
or hash, category, bounded failure-code enum, and reviewer instance/lineage IDs where already approved safe.
Never audit repo ref, commit SHA, source path, file manifest, raw source, code snippet, corpus/artifact URL, prompt,
model response, finding summary/detail/evidence ref, fingerprint input, token, credential, provider response, or
secret-like sentinel. Raw corpus/result artifacts and LLM prompts/responses are never persisted. Bounded finding
narrative remains only in the existing RLS-protected lifecycle row and is not claimed secret-free.

## 7. Repository/orchestrator behavior

Proposed `app/repositories/shortcut_detectors.py` owns the only trusted write path:

1. Resolve tenant/project and current declared repo before external I/O; validate a full lowercase commit SHA.
2. Resolve the ruled reviewer panel and independence facts before model calls. Under OD-45-2 A, absence of a
   builder set, any shared blueprint, inactive/unqualified reviewer, duplicate lineage/route, or wrong-project
   instance records a refused/non-covering attempt.
3. Fetch and strictly validate the exact-commit bounded corpus/result under OD-45-1/8. Any omission, truncation,
   unsupported required content, manifest mismatch, injection signal, unknown field/rule, or over-cap value
   fails/refuses; never silently sample or drop an item that could make the result appear clean.
4. Execute deterministic checks and/or blind LLM review exactly as ruled. Validate all untrusted input before
   the first LLM call; enforce budget before calls; record actual usage through existing cost events.
5. In one transaction append the run, category results, reviewer results, trusted open shortcut findings, and
   content-free audit. Deferred guards recompute aggregates at commit. Failed/refused attempts are retained and
   supersede older passes for the current exact binding.
6. Never invoke finding lifecycle transitions. Dedupe is within a run only; a later run creates a new observation
   and does not mutate old findings.
7. `coverage_for_project()` returns safe counts/booleans only: scope/binding/independence resolved, run present,
   corpus trusted, execution failed/refused, coverage complete, evidence consistent, mandatory/completed/failed
   category counts, reviewer counts/control failures, finding count, and existing all-source open/open-critical
   shortcut counts. It returns no repo/commit/path/corpus/prompt/response/finding prose or fingerprints.

No public method accepts trusted provenance, reviewer independence, coverage/verdict, derived severity, gate
status, or lifecycle terminal status. Trusted stamps occur only after the ruled connector/execution path.

## 8. A5 gate #6 and readiness — exact proposed change

### 8.1 A5 changes

`app/release/production_autonomy.py` and `app/repositories/production_autonomy.py` change only to replace gate
#6's permanent insufficient result with the ruled evidence ladder. The A5 ruleset advances to
**`slice45.v1`** because gate #6 becomes PASS-capable. Gate #6 would become the **sixth named non-intake
PASS-capable evidence gate and seventh PASS-capable gate overall**: #1, #2, #3, #4, #5, #6, and #11 are then
PASS-capable (`app/release/production_autonomy.py:7-48`; `CLAUDE.md:505-539`). This count is an inference from
the current evaluator; tests must assert the serialized gate set rather than rely on prose.

Proposed gate #6 ladder after every OD is ruled:

1. unresolved mandatory-category scope → `insufficient_evidence:shortcut_review_scope_unresolved`;
2. unresolved exact repo/commit/current-contract binding →
   `insufficient_evidence:shortcut_review_binding_unresolved`;
3. no exact-binding run → `insufficient_evidence:shortcut_review_not_executed`;
4. latest corpus/result provenance untrusted →
   `insufficient_evidence:shortcut_review_observed_unverified`;
5. latest execution failed/refused → `insufficient_evidence:shortcut_review_execution_failed`;
6. reviewer independence/panel unresolved →
   `insufficient_evidence:shortcut_review_independence_unproven`;
7. missing/failed/unsupported mandatory category or execution component →
   `insufficient_evidence:shortcut_review_coverage_incomplete`;
8. run/category/reviewer/finding aggregates or severity derivation inconsistent →
   `insufficient_evidence:shortcut_review_evidence_inconsistent`;
9. any open critical shortcut finding, regardless of provenance →
   `insufficient_evidence:critical_shortcut_findings_open`;
10. **only with trusted exact-binding complete independent-review coverage and zero open critical shortcut
    findings** → `passed:no_unaccepted_critical_shortcut_findings_verified`.

An empty findings list can reach rung 10 only when every prior rung is positively satisfied. Context is bounded
safe counts/booleans only. Non-critical open shortcut findings are visible context and are not auto-accepted or
hidden; Appendix B #6 keys on open unaccepted **critical** findings (`spec:2990`).

### 8.2 What does not change

- Gate #5 remains exactly Slice-44 PASS-capable security logic. Shortcut corpus/results cannot satisfy security
  coverage, and security scan results cannot satisfy shortcut coverage.
- Gates #1–#5 and #7–#13 remain semantically unchanged for identical inputs; regression tests compare every
  serialized gate dict other than #6 and preserve ordering 1..13.
- `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- `a5_satisfied` is still the conjunction of all 13 gates. Gates #7/#8/#9/#10/#12/#13 remain unmet under the
  current evaluator, so a passing gate #6 does not satisfy A5 (`app/release/production_autonomy.py:42-48,
  95-112`).
- `can_go_live_autonomously` remains hard-false regardless of gate #6. Request-authenticated A5 preapproval is
  still absent (`app/release/production_autonomy.py:64-67,99-108`).

## 9. Test plan for eventual implementation

### 9.1 Pure / Docker-free

- Strict corpus/result validation: valid exact schema; unknown/missing fields; malformed/uppercase/wrong commit;
  wrong repo/contract binding; duplicate/malformed paths/categories/reviewers/fingerprints; traversal, link,
  encrypted, unsupported, truncated, blank, NaN/Infinity, over-cap and count-inconsistent inputs; caller
  `clean/passed/trusted/independent/gate` fields refused.
- One test per canonical category mapping; all twelve under OD-45-3 A; each missing/duplicate/failed/refused/
  unsupported category; `other` non-gating; no N/A; clean with findings and findings-status without findings
  both refused; zero findings with complete coverage succeeds at the coverage layer, zero findings without
  coverage fails.
- Deterministic component: known positives/negatives, ambiguous inputs fail safe, changed detector contract hash
  invalidates old runs, no rule claims semantic completeness.
- LLM component if ruled: exactly ruled panel, blind prompts, distinct lineages/routes, strict response fields,
  injection refusal before first call, malformed/partial/extra/oversized output, provider/model/token mismatch,
  call failure, unpriced route, missing budget, projected over-budget, cost-event callback, disagreement, and
  every CI call through `FakeLLMClient` only.
- Severity: every OD-45-7 mapping boundary; unknown/incomplete/contradictory impact flags; no reviewer text can
  silently downgrade critical; derived severity deterministic.
- Binding/latest: wrong repo/commit/contract/corpus; later failed/refused/incomplete attempt supersedes old pass;
  no wall-clock TTL under OD-45-5 A; deterministic reason precedence.
- Lifecycle: prior manual or trusted open critical blocks a later clean run; resolved/false-positive/superseded
  critical is no longer open; accepted critical impossible; non-critical open does not directly fail gate #6;
  detector path never calls lifecycle transitions.
- A5: every ladder rung and passing rung; context excludes sensitive data; ruleset `slice45.v1`; only gate #6
  changes; `a5_satisfied` and go-live remain false in representative current-state reports.
- Readiness: byte/hash snapshot plus representative outputs unchanged at `slice20.v1`.

### 9.2 Planted-shortcut corpus tests

- At least one expert-labelled positive fixture for each of the twelve categories, plus clean negative controls,
  edge cases, adversarial disguises, incomplete-input cases, and prompt-injection content under the ruled
  `slice45.shortcut_fixtures.v1` corpus (`spec:914-930`).
- Each positive asserts the correct normalized category and evidence lineage; critical fixtures assert the ruled
  severity mapping. Multi-shortcut fixtures assert no silent dropping and stable fingerprint dedupe.
- Mutants include hardcoded test-pass output, static fake responses, fake connector success, disabled validation,
  weakened assertions, swallowed errors, placeholder UI, required-path TODO, local substitute, skipped AC,
  implementation-coupled test, and unsupported readiness claim—directly mirroring `spec:1302-1313`.
- Negative fixtures must not be described as a measured false-positive rate; planted positives must not be
  described as universal recall. The tests prove only behavior on the versioned fixture corpus.

### 9.3 DB-backed and direct-SQL adversarial tests

- Migration round trip `0043→0044→0043→0044`; head/model/catalog parity; only approved additive objects;
  downgrade restores the exact current Slice-44 findings guard and security path.
- RLS same-tenant success/cross-tenant invisibility; PUBLIC revoked; exact grants; RLS ENABLE+FORCE; all
  run/category/reviewer/finding composite FKs reject cross-project or cross-tenant relationships.
- UPDATE/DELETE/TRUNCATE refused on every new evidence table; rerun history retained. Existing finding lifecycle
  DML remains exactly Slice 23 behavior.
- Direct SQL rejects fabricated trusted provenance, caller-set coverage/verdict, success with zero/partial
  categories, duplicate/missing category, clean category with finding, finding category with zero findings,
  count/aggregate mismatch, wrong repo/commit/contract, malformed hash/SHA/enum/text, invalid severity,
  untrusted/failed parent, shortcut finding attached to security result, security finding attached to shortcut
  result, both attachment axes set, wrong category, duplicate per-run fingerprint, missing reviewer, duplicate
  reviewer/blueprint/version/route, shared builder blueprint, non-blind result, and inconsistent token/cost shape.
- Re-prove every Slice-23 guard: open-only create; type/category rule; `other` prose; immutable content/source;
  one-way terminal transition; terminal re-transition refusal; critical acceptance refusal; non-critical
  acceptance requires usable record; no DELETE/TRUNCATE; append-only events.
- Re-prove every Slice-44 extension: unverified finding cannot carry security attachment; trusted security
  finding requires its exact attachment/provenance/type/category/scanner/source/bounds; per-run security
  fingerprint dedupe; failed/untrusted security parent refusal; security aggregates; existing security rows and
  gate #5 behavior unchanged (`migrations/versions/0043_security_scan_provenance.py:226-474`).
- Repository transaction atomically writes exact-binding run/category/reviewer/findings; parse, connector,
  detector, reviewer, budget, injection, or DB-verifier failure cannot leave trusted complete coverage; later
  failed attempt becomes current.
- Audit sentinel injects secret-like strings, code, paths, URLs, prompt-injection text, model prose, evidence
  refs, and credentials into inputs and proves audit contains safe metadata only. Raw corpus/result/prompt/
  response bytes are absent from new tables.
- Production-autonomy repository uses exact latest coverage plus the existing all-source open-critical shortcut
  count. Unverified/manual findings never satisfy coverage, but every open critical shortcut finding blocks.
  Trusted complete coverage plus zero open critical makes **only gate #6** pass.

### 9.4 Verification commands (eventual implementation only)

`git diff --check`; Ruff; focused pure tests; focused DB tests; `make test`; `make test-db`; migration
`0043→0044→0043→0044`; CI. Any LLM or live SCM integration is replaced by `FakeLLMClient` and
`FakeSCMConnector` in CI. These are future implementation review requirements, not commands authorized by this
plan-only task.

## 10. Proposed file touch map (eventual implementation only)

- New, contingent on rulings: `app/verify/shortcut_detector.py`, optional
  `app/verify/shortcut_review.py`, models for run/category/reviewer evidence,
  `app/repositories/shortcut_detectors.py`, `migrations/versions/0044_shortcut_detector_execution.py`, and
  focused pure/DB tests plus versioned planted fixtures.
- Modify only if OD-45-1 requires it: existing `app/release/scm_connector.py` and minimum service/config/tool-
  policy wiring; no duplicate repo resolver or connector framework.
- Modify under OD-45-4 A: `app/models/release_finding.py`, `app/release/findings.py`,
  `app/repositories/release_findings.py`, and `app/models/__init__.py`; preserve all lifecycle/security rules.
- Modify for gate #6 only: `app/release/production_autonomy.py`,
  `app/repositories/production_autonomy.py`, and focused golden/API tests as required.
- `app/intake/readiness.py` must not change. No Slice-46 or Slice-48 implementation is in scope.
- No branch, code, migration, test, or PR is authorized until this plan is approved and OD-45-1 through
  OD-45-8 are explicitly ruled. This file is the sole deliverable now.

## 11. Must NOT claim

- Must NOT claim “no shortcuts” from an empty findings store, empty result list, missing detector/reviewer,
  failed/refused run, incomplete category set, N/A, or unsupported/omitted/truncated corpus content.
- Must NOT claim connector-verified retrieval means UAID executed the review or proves producer behavior.
- Must NOT claim a deterministic detector covers semantic §13.4 review or an LLM review covers all possible
  shortcuts.
- Must NOT claim a bounded exact-commit corpus is necessarily the entire repository or all production behavior.
- Must NOT claim a planted-fixture pass proves universal recall, completeness, or an acceptable false-positive
  rate.
- Must NOT claim reviewer instance, qualification flag, distinct lineage, blindness, or agreement proves
  reviewer competence or judgment truth. Current qualification provenance remains limited as cited.
- Must NOT claim project-wide blueprint exclusion proves independence from every actual Git author.
- Must NOT accept a free-form reviewer severity as gate-bearing or permit a silent critical→non-critical
  downgrade; severity requires the ruled code-owned derivation.
- Must NOT ignore a manually reported/unverified open critical shortcut finding because it cannot establish
  coverage. **All open critical shortcut findings block gate #6 regardless of provenance.**
- Must NOT claim DB-proven lineage proves finding narrative truth; it proves structure, binding, recorded
  execution metadata, and lifecycle state.
- Must NOT claim a later clean run resolves, supersedes, accepts, or disproves an older open finding.
- Must NOT claim `other` or N/A satisfies a mandatory category unless the coordinator explicitly rules a
  reviewed applicability authority.
- Must NOT persist or audit raw corpus/artifact/code, source paths, snippets, prompts, model responses, secrets,
  credentials, finding prose, or evidence references.
- Must NOT claim Slice 45 implements reviewer QA (Slice 48), acceptance verification (Slice 46), security scan
  coverage, issue provenance, release approval, deployment, or go-live.
- Must NOT claim a passing gate #6 means gate #5 changed, A5 is satisfied, or go-live is authorized. Readiness
  remains `slice20.v1`; go-live remains hard-false.
- Must NOT claim live network/model tests ran in CI; all such tests use fakes.

## 12. Definition of done for eventual implementation — not this plan

After explicit plan approval and all coordinator rulings: the ruled exact-binding source produces a strict,
bounded, versioned corpus/result; the ruled deterministic/reviewer execution runs with precisely labelled
provenance; every ruled mandatory §13.4 category has non-vacuous immutable coverage; reviewer independence is
enforced only to the exact ruled DB-provable boundary and never overclaimed; findings reuse the Slice-23
lifecycle through a shortcut-specific composite attachment without weakening Slice-23 or Slice-44; all new
tenant-owned evidence tables are RLS ENABLE+FORCE and append-only; direct SQL cannot fabricate coverage,
lineage, counts, severity, or clean status; audits contain safe metadata only; all open critical shortcut
findings block regardless of provenance; gate #6 is fail-closed and PASS-capable only for trusted complete
latest exact-binding coverage plus zero open critical shortcuts; A5 ruleset is `slice45.v1`; gate #5 and all
other gates are regression-proven unchanged; readiness is byte-stable `slice20.v1`; go-live remains hard-false;
migration `0044` round-trips; planted fixtures, pure suite, DB suite, and CI pass. Sources: spec §2.1–2.2,
§9.5.1, §13.4, Appendix B #6 (`spec:129-159,912-930,1298-1313,2981-2991`), roadmap Slice 45
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:421-431`), and repository constraints cited throughout.

---

**Review request:** **APPROVE or REJECT this plan only.** On rejection, identify the exact section and required
correction. On approval, the coordinator must still rule OD-45-1 through OD-45-8 before any branch, code,
migration, tests, or PR begins. This file is the sole authorized deliverable for the present task.
