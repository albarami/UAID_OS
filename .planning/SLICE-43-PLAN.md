# Slice 43 — Test-oracle execution subsystem (A5 gate #4) — PLAN v1

**Status:** MERGED — historical record. Implemented via PR #76 (squash commit `52785b3`); this v1 plan is retained as the approved design rationale for Slice 43.

> **Persona.** Senior verification-platform and PostgreSQL governance architect, applying fail-closed
> evidence design, tenant isolation, and Sanad / No-Free-Facts discipline.
>
> **Primary Sanad.** Test-oracle purpose and the three types: spec §14.1–14.2
> (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1349-1363`); judgment controls and
> risk-tuned, non-universal numeric defaults: §14.3 (`spec:1365-1405`); “no oracle, no go-live”:
> §14.4 (`spec:1407-1409`); go-live conjunction: §24.1 (`spec:2251-2266`); Phase-5 framework:
> §26.5 (`spec:2487-2498`); A5 gate #4: Appendix B (`spec:2981-2988`); canonical template fields:
> `docs/UAID_OS_Intake_Template_Pack_v1_2/09_test_oracles.yaml:1-14`; roadmap commitment and expected
> migration: `.planning/GO-LIVE-END-TO-END-ROADMAP.md:397-407`.
>
> **Verified repository Sanad.** Canonical `test_oracle` artifacts are provenance-backed and append-only;
> their parent FK proves only same-project/tenant binding, while readiness—not the artifact table—treats an
> oracle as structurally valid only when its parent is an acceptance criterion. Their `data` remains
> unconstrained JSONB (`app/models/intake_artifact.py:1-13,47-90`;
> `migrations/versions/0014_intake_spine.py:57-117`; `app/intake/readiness.py:233-276`). Slice 42 can FK-link an
> oracle to a task contract and stores contract risk, but its freeze guard requires only a source
> requirement plus three reviewer layers—not an oracle link
> (`app/models/task_contract.py:57-149`; `migrations/versions/0041_task_contracts.py:469-483,561-597`).
> Readiness proves the structural requirement→acceptance-criterion→oracle spine, not executable oracle
> definition validity or execution (`app/intake/readiness.py:233-284`). The current A5 evaluator has no
> gate-#4 source and returns `no_evidence_source:test_oracle_execution`; its ruleset is `slice31.v1`
> (`app/release/production_autonomy.py:35-42,51,325-342`). The SCM connector observes branch protection,
> PR/review metadata, and summarized checks, but has no test-result-artifact method
> (`app/release/scm_connector.py:29-38,54-75,203-218`). These are the constraints behind the ODs below.

## Coordinator rulings (final)

- **OD-43-1 = Option A (conservative canonical scope):** gate #4 scopes ALL valid canonical project test_oracle artifacts. Record it explicitly as a conservative inference, stricter than Appendix B #4.
- **OD-43-2 = Option A (connector-verified CI artifact):** extend the existing fake/live SCM boundary to fetch a bounded, versioned result artifact for an exact declared repo + commit; observation_provenance='connector_verified_ci'. Live network adapter-only; CI uses the fake.
- **OD-43-3 = recommended ruling:** versioned slice43.oracle.v1 schema; specified = canonical-JSON exact + allowlisted rule keys; reference = exact + bounded numeric percentage tolerance; judgment = rubric aggregation; template custom is REJECTED as unsupported this slice; prose never executes.
- **OD-43-4 = recommended ruling:** Fleiss' kappa (named/versioned implementation); critical/high-impact judgment runs require ≥2 active, qualified, same-project ai_evaluation instances with distinct blueprint IDs AND distinct version hashes/model routes; blind calls; below-floor IRR or unresolved disagreement fails; configured human-review requirements remain blocking (no untrusted string satisfies them). LLM judgment execution IS approved for this slice — it must reuse the existing budget/cost/injection/failure discipline, and every CI test uses FakeLLMClient only.
- **OD-43-5 = recommended ruling:** latest-wins per (project, oracle artifact, definition hash, declared repo, commit SHA); any change requires a new run; latest failure supersedes an older pass; NO wall-clock TTL.

---

## 0. The defining honesty constraint (the crux)

Slice 43 must distinguish three different claims:

1. **REPORTED:** a caller supplied a definition, observation, evaluator label, or judgment. Existing
   artifact provenance and FKs prove who/what the row references; they do not prove the referenced system
   behavior occurred or that a judgment is correct (`app/repositories/intake.py:37-96`;
   `.planning/SLICE-42-PLAN.md:57-67`).
2. **DB-PROVEN:** tenant/project binding, oracle kind/parentage, result shape, append-only history,
   completeness counts, threshold arithmetic, evaluator-registration/lineage constraints, and the final
   stored aggregate are enforced or recomputed from FK children by PostgreSQL. This is a **proposed Slice-43
   invariant**, following the deferred child-count and generated-verdict pattern in
   `.planning/SLICE-40-PLAN.md:54-81`.
3. **EXECUTED:** a repository-controlled runner actually performed an allowlisted comparison, or the
   judgment service itself made independent evaluator calls. “Executed” does **not** prove the supplied
   system-under-test observation is authentic; a gate-passing run therefore also needs a trusted,
   binding-specific observation source selected in OD-43-2. This follows the repo’s existing separation
   between caller-supplied observations and connector-verified observations
   (`app/release/ci_evidence.py:4-21,28-31,102-123`).

**No result row may become gate-passing merely because a caller wrote `passed=true`.** Deterministic result
outcomes and run aggregates must be derived; judgment labels remain judgments and must be named as such.
No empty set, missing definition, invalid definition, unsupported runner, incomplete sample set, failed
execution, untrusted observation source, stale/mismatched binding, or inadequate judgment independence may
vacuously pass. These are proposed fail-closed rules needed to satisfy §14.4 and Appendix B #4
(`spec:1407-1409,2983-2988`).

## 1. Scope and non-goals

### 1.1 In scope (proposed implementation after approval)

- A strict, versioned validator for the three oracle types and the template controls (`spec:1357-1380`;
  template `09_test_oracles.yaml:1-14`).
- Pure specified/reference comparators and judgment aggregation/IRR logic; no arbitrary code or expression
  evaluation (security inference from the executable-versus-data boundary in `app/intake/sandbox.py:1-15`).
- A trusted observation-source boundary and execution orchestrator, with production provenance decided by
  OD-43-2; offline fakes only in tests (existing boundary pattern: `app/llm/client.py:1-70` and
  `app/release/scm_connector.py:1-11,203-218`).
- Two tenant-owned, RLS `ENABLE`+`FORCE`, append-only tables—`test_oracle_runs` and `test_results`—in additive
  migration `0042`, plus the minimum additive FK-target constraint required by the selected scope binding
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:401-403`; current head `0041_task_contracts` is recorded at
  `.planning/GO-LIVE-END-TO-END-ROADMAP.md:6` and exists at
  `migrations/versions/0041_task_contracts.py`).
- Compute-on-read project oracle coverage plus an A5 gate-#4 decision. Gate #4 becomes PASS-capable only
  under the complete ladder in §9; the A5 ruleset advances from `slice31.v1` to **`slice43.v1`** because the
  pure report semantics change (`app/release/production_autonomy.py:51,325-342`).
- Pure and DB-backed tests, including adversarial/direct-SQL tests, cross-tenant/cross-project refusals, and
  A5/readiness interaction tests (house discipline: `.planning/SLICE-40-PLAN.md:95-106` and
  `.planning/SLICE-42-PLAN.md:267-289`).

### 1.2 Non-goals

- No acceptance verifier (Slice 46), security scan provenance (Slice 44), shortcut detector (Slice 45),
  reviewer QA (Slice 48), evidence-pack auditor (Slice 49), go-live agent (Slice 50), release authorization,
  or deployment action; the roadmap assigns those separately
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:409-505`).
- No arbitrary project code execution, shell execution, user-provided Python, dynamic import, or `custom`
  expression evaluation. `tolerance: custom` exists in the template, but no safe plugin/runtime contract
  exists in the repository; behavior is an OD-43-3 decision (template `09_test_oracles.yaml:7` and verified
  absence via the repository scan recorded above).
- No mutation of canonical intake artifacts, task contracts, or prior results. Intake artifacts are already
  append-only (`app/models/intake_artifact.py:1-7`); result immutability is proposed here.
- No HTTP endpoint, UI, scheduler, automatic Slice-43 work dispatch, task-contract lifecycle change, or
  broker authority change (scope inference; Slice 42 explicitly left execution/broker wiring out at
  `.planning/SLICE-42-PLAN.md:76-86`).
- No readiness-rule change. `app/intake/readiness.py` remains byte-stable and its ruleset remains
  **`slice20.v1`** (`app/intake/readiness.py:45`): R5 proves structural spine coverage, while Slice 43 adds
  separate execution evidence to A5.

## 2. Required oracle semantics

The validator must reject missing, extra-typed, blank, unbounded, non-finite, or inconsistent fields before
execution and mirror critical constraints in the DB where representable (proposed fail-closed design;
bounded/non-blank precedent: `.planning/SLICE-42-PLAN.md:140-147,174-182`).

- **Specified.** Exact expected value or a named deterministic rule; controls must map to an allowlisted,
  versioned comparator. A prose-only `expected_behavior` is explanatory evidence, not executable truth
  (`spec:1361`; template `09_test_oracles.yaml:5`).
- **Reference.** Immutable/binding-specific baseline digest or numeric baseline, explicit comparison mode,
  tolerance, and reference provenance are mandatory (`spec:1362`; template `09_test_oracles.yaml:6-7`).
- **Judgment.** Explicit rubric, representative and adversarial samples, independent judges, disagreement
  tracking, threshold, calibration examples, failure/limit evidence, and any required human/domain review
  are mandatory (`spec:1363,1365-1380`). The template’s `100`, `0.85`, and `0.70` values are defaults to tune,
  never universal truths (`spec:1380,1395-1404`; template `09_test_oracles.yaml:8-14`).
- **All types.** `sample_size`, `minimum_pass_rate`, and binding metadata are snapshotted into the immutable
  run. The run stores the SHA-256 of the canonicalized, validated definition so later reads can prove exactly
  which append-only definition was executed (proposed reproducibility mechanism; immutable artifact basis:
  `app/models/intake_artifact.py:1-7,86-90`).

## 3. Evidence and verdict model

### 3.1 Result truth levels

- `observation_provenance` is a separate axis from `execution_provenance`. A repository-controlled
  comparator over caller-supplied data is **executed but observation-unverified**, so it cannot satisfy A5
  gate #4 (proposed rule; provenance separation precedent: `app/release/ci_evidence.py:9-21`).
- Specified/reference `passed` is DB-generated or deferred-trigger-verified from stored digests/numeric
  comparison inputs; no write API accepts a final boolean. Judgment result labels are system-observed reports
  from independent evaluator calls, not objective truth; the aggregate must say `judgment_passed`, not imply
  deterministic proof (proposed honesty vocabulary grounded in `spec:1353,1363,1367`).
- A run-level verdict is generated from trigger-verified child counts, pass-rate arithmetic, coverage,
  execution status, trusted observation provenance, and—only for judgment—lineage count + IRR + adjudication
  controls. Direct SQL cannot supply or override the verdict (proposed reuse of the Slice-40 mechanism:
  `.planning/SLICE-40-PLAN.md:72-81,99-101`).

### 3.2 Latest-wins, binding-bound gate input

For every oracle in the coordinator-approved gate scope, the A5 repository uses the latest committed run by
`(created_at DESC, id DESC)` for the exact oracle-definition hash and selected system/release binding. A later
failed/refused/incomplete run blocks an older pass; a run for another oracle, definition, project, commit, or
release cannot be reused (proposed fail-closed reuse of the exact-binding/latest-wins convention in
`app/release/production_autonomy.py:258-292,294-323`). OD-43-5 decides the authoritative binding and whether a
time TTL is also required.

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-43-1 — What is the authoritative “critical oracle” gate scope?

**Gap:** `intake_artifacts` has no criticality field, while `task_contracts.risk_level` exists but an oracle
link is optional and contracts are not release-bound (`app/models/intake_artifact.py:81-90`;
`app/models/task_contract.py:91-109`; `migrations/versions/0041_task_contracts.py:469-483`). The spec requires
every *critical* oracle classified and every critical feature to have an oracle, but does not map “critical
feature” to a current table (`spec:1355,1407-1409`).

**Options:**

- **A — conservative canonical scope (recommended):** gate all valid canonical project `test_oracle`
  artifacts, not merely a guessed critical subset. R5 separately blocks missing structural oracle links
  (`app/intake/readiness.py:242-284`). This is stricter than Appendix B #4 and must be recorded as a
  conservative inference.
- **B — contract-critical scope:** gate active/non-canceled `risk_level='critical'` contracts and require
  each to have ≥1 `test_oracle` link; use exact link FK binding. This uses a real criticality field but assumes
  task contracts are a complete feature inventory, which Slice 42 does not prove.
- **C — add an explicit reviewed critical-scope registry:** strongest semantics, but expands migration `0042`
  beyond the two roadmap tables and needs a separate completeness/approval authority design.

**No ruling ⇒** gate #4 remains `insufficient_evidence:critical_oracle_scope_unresolved`; it must not pass.

### OD-43-2 — What source makes system-under-test observations trusted?

**Gap:** current CI evidence proves protection/configuration and summarizes checks; it does not fetch a
schema-bound per-oracle result artifact (`app/release/scm_connector.py:29-38,54-75`). Comparing arbitrary
caller payloads would execute a comparator without proving the tested behavior occurred.

**Options:**

- **A — connector-verified CI artifact (recommended):** extend the fake/live SCM boundary to fetch a bounded,
  versioned result artifact for an exact declared repo + commit/workflow run; validate it before execution;
  stamp `observation_provenance='connector_verified_ci'`. Live network remains adapter-only; CI uses a fake,
  following `app/release/scm_connector.py:1-11,203-218`.
- **B — allowlisted in-process observation providers:** code-owned runner keys return observations; no dynamic
  code. This is smaller but only covers UAID-owned targets registered in source.
- **C — caller supplied:** retain records as `caller_supplied_unverified`; useful for staging diagnostics but
  categorically non-gating.

**No ruling ⇒** caller runs may be recorded as non-gating only; gate #4 cannot pass.

### OD-43-3 — What is the executable definition contract?

**Recommended ruling:** versioned `slice43.oracle.v1` data schema; `specified` supports exact canonical-JSON
comparison plus allowlisted rule keys; `reference` supports exact and bounded numeric percentage tolerance;
`judgment` supports rubric aggregation; template `custom` is rejected as unsupported this slice. Prose never
executes. Alternative: approve a separately designed, code-owned custom-runner registry. This decision is
required because the current `data` column is arbitrary JSONB and the template’s `expected_behavior` is prose
(`app/models/intake_artifact.py:86-90`; template `09_test_oracles.yaml:5-7`).

### OD-43-4 — Judgment statistic, evaluator identity, and disagreement resolution

**Recommended ruling:** binary rubric decisions use a named/versioned **Fleiss’ kappa** implementation;
critical/high-impact judgment runs require at least two active, qualified, same-project `ai_evaluation`
instances with distinct blueprint IDs **and** distinct immutable version content hashes/model routes; calls
are blind to other judges’ outputs; any below-floor IRR or unresolved disagreement fails. A configured
human/domain-review requirement remains blocking until an authenticated human-authority binding exists—an
untrusted string cannot satisfy it. The spec mandates controls but deliberately does not select a universal
statistic or threshold (`spec:1367-1380`); available lineage/qualification anchors are
`app/models/agent_instance.py:1-16,48-72`, `app/models/agent_realization.py:33-82`,
`app/models/agent_version.py:39-64`, and `app/agents/registry.py:36-50`.

**Alternative rulings:** Cohen’s kappa with exactly two evaluators; Krippendorff’s alpha for variable/missing
ratings; or no LLM execution in Slice 43 (judgment runs remain reported/non-gating). If LLM judgment is
approved, the implementation must reuse the budget/cost/injection/failure discipline of existing LLM
pipelines, and every CI test must use `FakeLLMClient` only
(`app/repositories/extraction.py:71-188,418-431`; `app/llm/client.py:1-70`).

### OD-43-5 — What exact binding invalidates an old pass?

**Recommended ruling:** latest-wins per `(project, oracle artifact, definition hash, declared repo,
commit SHA)`; any definition/binding/commit change requires a new run; the latest failure supersedes an older
pass; no arbitrary wall-clock TTL until the spec supplies or the coordinator approves one. If Slice 43 gates
a frozen release candidate instead, the run must composite-bind that candidate and its immutable release
scope. The existing A5 evaluator is project-level and current release candidates are issue-bound, not
oracle-bound (`app/repositories/production_autonomy.py:94-165`; `app/models/release_candidate.py:1-15`).

## 5. Proposed pure modules (contingent on §4 rulings)

### 5.1 `app/verify/oracles.py`

- Frozen `OracleDefinition`, `OracleCase`, `OracleResult`, `OracleRunDecision`, and `Gate4Evidence` value
  objects; deterministic `to_dict()`; `RULESET_VERSION='slice43.v1'` for the oracle engine (proposed house
  pattern: `app/review/workflow.py:124-143`).
- Constants for exact enums and explicit caps: definition bytes, cases/run, case-ref length, rubric criteria,
  criterion length, evaluator count, evidence-ref length, and numeric precision. Every text is non-blank and
  bounded; every numeric value is finite and in an explicit domain (proposed DB/app dual validation; Slice-42
  precedent `.planning/SLICE-42-PLAN.md:140-147`).
- `validate_definition(data)` enforces the ruled `slice43.oracle.v1` discriminated union, template controls,
  representative/adversarial coverage for judgment, and risk-tuned threshold policy labels
  (`spec:1357-1380`; template `09_test_oracles.yaml:1-14`).
- `definition_hash()` canonicalizes the validated object and returns `sha256:<64 lowercase hex>`; raw
  definition prose/content is not copied into run/audit rows (proposed data-minimization rule; safe-audit
  precedent `app/repositories/intake.py:121-138`).
- `evaluate_run(children, definition)` recomputes counts/coverage/pass-rate/IRR and returns explicit failure
  reasons. It never accepts a caller verdict and never treats zero children as success (proposed §14.4
  enforcement).

### 5.2 Type runners

- `app/verify/specified.py`: canonical exact comparator and ruled allowlisted deterministic rules. Store
  expected/observed digests and derived equality only; no arbitrary executable string (proposed OD-43-3).
- `app/verify/reference.py`: exact or numeric percentage comparison against an immutable, provenance-bearing
  reference; reject zero-denominator ambiguity unless definition supplies an explicit ruled behavior;
  reject NaN/Infinity and unbounded decimals (proposed OD-43-3; required controls `spec:1362`).
- `app/verify/judgment.py`: rubric prompt/response parser, independent-call orchestration, per-criterion
  bounded scores, pass-label derivation, disagreement matrix, and the ruled IRR statistic. It never exposes
  another judge’s response in a judge prompt (`spec:1363,1369-1378`). If LLM-backed, provider/model/token
  metadata and cost are recorded using existing safe patterns; raw model output and sample content are not
  placed in audit payloads (`app/repositories/extraction.py:126-188`).
- `app/verify/oracle_source.py`: protocol/fake/production adapter selected by OD-43-2. Failures/refusals produce
  non-passing run statuses; malformed or over-cap payloads are rejected before persistence (proposed boundary;
  connector precedent `app/release/scm_connector.py:21-38,203-218`).

## 6. Storage and migration `0042` (additive only)

Both new tables are tenant-owned; each has composite `(project_id, tenant_id)→projects`, RLS `ENABLE` +
`FORCE`, `tenant_isolation` `USING` + `WITH CHECK`, `REVOKE ALL FROM PUBLIC`, `GRANT SELECT,INSERT TO
uaid_app`, and block triggers for `UPDATE`, `DELETE`, and `TRUNCATE`. Every child FK includes project+tenant.
This is proposed reuse of the exact Slice-42 pattern
(`migrations/versions/0041_task_contracts.py:645-687`; `.planning/SLICE-42-PLAN.md:213-220`).

### 6.1 `test_oracle_runs`

Proposed columns:

- identity/binding: `id`, `tenant_id`, `project_id`, `oracle_artifact_id`, optional ruled
  `task_contract_id`/`oracle_link_id` or `release_candidate_id`, `definition_hash`, `definition_schema_version`,
  `source_binding_hash`, `commit_sha` (when CI-bound), `created_at`;
- execution snapshot: `oracle_type`, `runner_key`, `runner_version`, `execution_status`
  (`succeeded|failed|refused`), `observation_provenance`, `execution_provenance`, `failure_code`;
- threshold/count snapshot: `required_sample_size`, `minimum_pass_rate`, `irr_minimum` nullable by type,
  `reported_result_count`, `reported_passed_count`, `reported_distinct_case_count`,
  `reported_evaluator_lineage_count`, `reported_irr` nullable;
- DB-derived: `aggregate_pass_rate` and `verdict` (`passed|failed`) are generated from the trigger-verified
  snapshot; `passed` additionally requires `execution_status='succeeded'`, trusted observation provenance,
  complete required coverage, and type-specific controls. No INSERT API accepts either derived field.

Constraints/guards:

- composite FK to `intake_artifacts(id,project_id,tenant_id)` plus BEFORE-INSERT kind/parent guard proving
  `kind='test_oracle'` with an acceptance-criterion parent; definition hash and schema are bounded; all enums,
  counts, decimals, SHAs, and nullability are type/status coherent
  (`app/models/intake_artifact.py:56-71,81-90`).
- If OD-43-1 chooses contract scope, add only the necessary composite UNIQUE target to
  `task_contract_artifact_links`, then composite-FK the run to the exact `link_kind='test_oracle'` link; a DB
  guard proves contract risk/status. If release scope is selected, use an exact same-tenant/project release
  composite FK. This is contingent design, not a fact.
- A DEFERRABLE INITIALLY DEFERRED constraint trigger on parent and child recomputes all reported counts,
  coverage, and the ruled IRR from `test_results`; mismatch aborts commit. `failed/refused` runs require zero
  result children and a bounded non-blank failure code; `succeeded` runs require the exact type-specific child
  shape. This prevents fake aggregate/verdict writes (proposed Slice-40 pattern:
  `.planning/SLICE-40-PLAN.md:72-81,99-101`).
- Unique/index keys support deterministic latest-wins lookup by tenant/project/oracle/binding/created_at/id;
  no uniqueness rule may erase historical reruns.

### 6.2 `test_results`

Proposed columns:

- `id`, `tenant_id`, `project_id`, `test_oracle_run_id`, `case_ref`, `sample_class`
  (`representative|adversarial|calibration|other`), `result_kind`, `created_at`;
- deterministic evidence: nullable `expected_digest`, `observed_digest`, `reference_digest`,
  `observed_numeric`, `reference_numeric`, `tolerance_numeric`, with mutually exclusive type-shape CHECKs;
- judgment evidence: nullable `evaluator_instance_id`, `evaluator_version_hash`, bounded per-criterion score
  JSON, `judgment_label`, and `disagreement_group`; raw sample/output/rationale is not stored in audit and is
  stored in-table only if the coordinator explicitly rules it necessary;
- `passed` is a generated/verified outcome from deterministic inputs or the bounded judgment label; its
  epistemic class is exposed by `result_kind` and must not be flattened in reports.

Constraints/guards:

- composite FK `(test_oracle_run_id,project_id,tenant_id)→test_oracle_runs`; if judgment, composite FK
  `(evaluator_instance_id,project_id,tenant_id)→agent_instances`, plus deferred guard resolving a qualified
  realization and the ruled distinct-lineage requirements (`app/models/agent_instance.py:48-72`;
  `app/models/agent_realization.py:33-82`).
- one deterministic result per `(run,case_ref)`; one judgment result per `(run,case_ref,evaluator_instance)`;
  duplicate/missing evaluator votes and cross-project/tenant references fail.
- every ref/hash/code and every JSON key/value is bounded/non-blank; JSON shape and numeric domains are
  mirrored in DB functions; append-only DML guards apply (proposed Slice-42 discipline:
  `.planning/SLICE-42-PLAN.md:197-220`).

### 6.3 Audit

Audit only safe metadata: run/result IDs, project/oracle IDs, oracle type, runner/status/verdict,
provenance tiers, binding hash/commit SHA where approved safe, counts, threshold presence, and failure-code
enum. Never audit expected/observed/reference values, rubric text, sample/output content, evaluator rationale,
raw provider response, URL, token, or free-text evidence reference (proposed reuse of
`app/repositories/ci_evidence.py:151-166` and `app/repositories/review_reports.py:78-101`). Actor fields remain
untrusted labels unless a separately authenticated path proves otherwise.

## 7. Repository/orchestrator behavior

`app/repositories/test_oracles.py` (proposed) owns all writes and these read paths:

1. Resolve the tenant/project oracle, its parent chain, provenance, and coordinator-approved scope binding;
   reject wrong kind/project/tenant before external I/O (FK/backstop basis:
   `app/models/intake_artifact.py:50-71`).
2. Validate and hash the immutable definition; resolve the exact trusted observation binding from OD-43-2.
3. Execute the type runner. Judgment calls, if approved, are separate/blind, budget-gated, and use only
   active+qualified ruled evaluator lineages; CI tests inject `FakeLLMClient` and never use live providers
   (`app/llm/client.py:1-70`).
4. In one transaction insert the run and all results; the deferred DB verifier recomputes aggregates at
   commit. Persist a failed/refused run without result children on safe execution failure; never convert an
   exception into a pass.
5. `latest_for_binding(...)` returns exact-binding latest only. `coverage_for_project(...)` returns totals and
   explicit sets/counts for missing definition, invalid definition, never-run, latest-failed, untrusted,
   binding-mismatch, incomplete, judgment-control-failed, and passed. A5 receives counts/booleans only—never
   tenant prose or raw result data (proposed safe-context pattern:
   `app/release/production_autonomy.py:263-270,300-305`).

No public method accepts `verdict`, aggregate counts without matching children, a verified provenance tier,
or a gate status. Connector/system provenance is stamped only inside its approved execution path (precedent:
`app/repositories/ci_evidence.py:32-81`).

## 8. A5 gate #4 and readiness — exact change

### 8.1 A5 changes

`app/release/production_autonomy.py` and `app/repositories/production_autonomy.py` **do change** because Slice
43 replaces the hard-coded no-source gate with a real fail-closed evidence ladder. The A5 report ruleset
becomes **`slice43.v1`**; all other gate algorithms and ordering must remain bit-stable, proven by regression
tests (`app/release/production_autonomy.py:117-342`).

Proposed gate #4 ladder, after §4 rulings:

1. unresolved scope → `insufficient_evidence:critical_oracle_scope_unresolved`;
2. empty/unproven scope → `insufficient_evidence:no_proven_critical_oracle_scope`;
3. any critical feature/scope item without a valid oracle definition →
   `insufficient_evidence:critical_feature_without_valid_oracle` (§14.4);
4. any oracle never run for the current binding → `insufficient_evidence:critical_oracle_not_executed`;
5. any latest run untrusted/mismatched/incomplete/failed/refused → a specific `insufficient_evidence:*` reason;
6. any latest valid run verdict failed, including threshold/IRR/adjudication failure →
   `insufficient_evidence:critical_oracle_failed`;
7. **only when scope is proven non-vacuously and every in-scope oracle’s exact-binding latest run is valid,
   trusted, complete, and `passed`** → `passed:all_critical_test_oracles_pass_verified`.

Context is safe counts only: scoped/missing/invalid/unrun/untrusted/failed/passed oracle counts plus selected
binding-present boolean and ruleset; no refs, prose, samples, rubric, or result content. This makes gate #4
PASS-capable as required by the roadmap, but it does not make A5 satisfied unless all 13 gates pass
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:397-407`; `app/release/production_autonomy.py:88-105`).

### 8.2 What does not change

- `app/intake/readiness.py` is untouched; readiness ruleset remains **`slice20.v1`**
  (`app/intake/readiness.py:45`). Structural oracle presence is not execution proof
  (`app/intake/readiness.py:242-284`).
- `can_go_live_autonomously` remains hard-false. The existing report requires all A5 gates plus a verified,
  request-authenticated A5 preapproval that does not exist (`app/release/production_autonomy.py:38-42,58-61,
  88-105`). Slice 43 implements neither preapproval nor the remaining gates.
- Therefore **go-live remains false regardless of gate #4’s result**, and Slice 43 must not claim production
  readiness (`spec:2253-2266`; roadmap `.planning/GO-LIVE-END-TO-END-ROADMAP.md:405-407`).

## 9. Test plan for the eventual implementation

### 9.1 Pure/Docker-free

- Definition validator: valid specified/reference/judgment shapes; missing/blank/over-cap/wrong-type/NaN/
  Infinity/unknown-key/inconsistent tolerance cases; template defaults accepted only as explicitly labeled
  illustrative; unsupported `custom` fails per OD-43-3 (`spec:1380`; template `09_test_oracles.yaml:7-14`).
- Specified: exact pass/fail; canonicalization stability; digest mismatch; allowlist unknown; no caller verdict.
- Reference: exact; inside/on/outside percentage boundary; negative values; zero baseline ruled behavior;
  missing reference provenance; drift fail (`spec:1362`).
- Judgment: rubric bounds; representative+adversarial coverage; insufficient sample; <2 lineages; same
  blueprint/version route; independent prompt construction; below/on/above pass and IRR floors; disagreement
  blocking/adjudication; human-required blocking. If LLM is selected, **FakeLLMClient only** and no network/key
  (`app/llm/client.py:1-70`).
- Aggregate: zero children never pass; exact-bound latest-wins; failed latest supersedes earlier pass; other
  project/oracle/binding runs ignored; deterministic reason ordering.
- A5: each gate-#4 ladder rung plus passing rung; `ruleset_version='slice43.v1'`; gates other than #4
  byte-equal before/after for identical inputs; `can_go_live_autonomously is False` in every case. Readiness
  report byte-equal and remains `slice20.v1`.

### 9.2 DB-backed

- Migration `0041→0042→0041` round-trip; exactly the approved additive schema; model metadata/catalog parity.
- RLS same-tenant success and cross-tenant invisibility; composite-FK cross-project/tenant/oracle-kind/parent/
  scope/evaluator refusal; PUBLIC revoked; exact grants; RLS ENABLE+FORCE.
- Append-only UPDATE/DELETE/TRUNCATE blocked on both tables, including direct SQL; historical reruns retained.
- Direct SQL cannot write generated `passed`/aggregate/verdict; deferred trigger rejects parent counts,
  coverage, pass count, lineage count, or IRR inconsistent with children; empty-success run rejected;
  failed/refused shape enforced.
- Type-shape CHECKs reject deterministic/judgment column smuggling, duplicate cases/votes, unknown enums,
  blank/over-cap text, malformed hashes/SHAs, non-finite/out-of-domain numerics, untrusted provenance elevated
  to trusted, and judgment evaluator not active/qualified/distinct as ruled.
- Repository execution records successful and failed/refused runs atomically; audit contains safe metadata and
  excludes sentinel secrets/content/rubric/rationale/reference values/URLs/tokens.
- Production-autonomy repository reads only exact-scope/exact-binding latest runs; untrusted or stale/mismatch
  never passes; all approved-scope latest runs passing makes only gate #4 pass.

### 9.3 Verification commands (eventual implementation only)

`git diff --check`; focused pure test file; focused DB test file; `make test`; `make test-db`; migration
upgrade/downgrade; CI. These are requirements for implementation review, **not commands authorized by this
plan-only task** (house precedent: `.planning/SLICE-42-PLAN.md:267-307`).

## 10. Proposed file touch map (eventual implementation only)

- New: `app/verify/__init__.py`, `app/verify/oracles.py`, `app/verify/specified.py`,
  `app/verify/reference.py`, `app/verify/judgment.py`, `app/verify/oracle_source.py`.
- New: `app/models/test_oracle_run.py`, `app/models/test_result.py`,
  `app/repositories/test_oracles.py`, `migrations/versions/0042_test_oracles.py`,
  `tests/test_test_oracles.py`.
- Modify: `app/models/__init__.py`, `app/release/production_autonomy.py`,
  `app/repositories/production_autonomy.py`, and only the connector/config/cost files selected by OD-43-2/
  OD-43-4. `app/intake/readiness.py` must not change.
- No code file is authorized until plan approval and coordinator rulings; this list is a proposed boundary,
  grounded in the roadmap’s file sketch at `.planning/GO-LIVE-END-TO-END-ROADMAP.md:401-403`.

## 11. Must NOT claim

- Must NOT claim an oracle **executed** merely because a result was reported or persisted.
- Must NOT claim a system-under-test observation is verified when only the comparator was system-executed.
- Must NOT claim FK-proven identity/lineage proves evaluator competence, independence of thought, or judgment
  correctness; qualification is a gate, not infallibility (`app/models/agent_realization.py:1-8`).
- Must NOT claim a DB-derived pass proves the input observation or reference was authentic; provenance remains
  a separate axis.
- Must NOT claim structural readiness (`slice20.v1`) proves oracle validity or execution.
- Must NOT claim one passing run covers another definition, oracle, task, project, commit, release, or later
  failed run.
- Must NOT claim a missing/empty critical scope is success or apply vacuous truth to A5.
- Must NOT claim `100`, `0.85`, `0.70`, or the selected IRR statistic is universal statistical truth
  (`spec:1380`).
- Must NOT claim non-critical coverage alone satisfies Appendix B #4, or that a passing gate #4 satisfies A5.
- Must NOT claim Slice 43 implements acceptance verification, security/shortcut coverage, evidence-pack
  completeness, release preapproval, autonomous deployment, or go-live.
- Must NOT claim live LLM/provider tests ran in CI; all LLM/connector tests use fakes
  (`app/llm/client.py:1-70`; `app/release/scm_connector.py:1-11`).

## 12. Definition of done for the eventual implementation — not this plan

After explicit plan approval and coordinator rulings: all three oracle types have strict executable
definitions; trusted exact-binding observations feed repository-controlled runners; immutable RLS-protected
`test_oracle_runs`/`test_results` make child completeness and aggregate verdicts non-fakeable; judgment runs
enforce the ruled rubric/sample/lineage/IRR/disagreement/human controls; gate #4 is fail-closed and PASS-capable
only when every approved-scope exact-binding latest oracle run passes; A5 ruleset is `slice43.v1`; readiness
remains `slice20.v1`; go-live remains hard-false; migration `0042` round-trips; pure+DB suites and CI pass.
Sources: spec §14.1–14.4, §24.1, Appendix B #4 (`spec:1349-1409,2251-2266,2981-2988`), roadmap Slice 43
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:397-407`), and the repository constraints cited throughout.

---

**Review request:** **APPROVE or REJECT this plan only.** On rejection, identify the exact section and required
correction. On approval, the coordinator must still rule OD-43-1 through OD-43-5 before any branch, code,
migration, tests, or PR begins. This file is the sole authorized deliverable for the present task.
