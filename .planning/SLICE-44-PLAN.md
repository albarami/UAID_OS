# Slice 44 — Security reviewer / scan provenance (A5 gate #5) — PLAN v1

**Status:** MERGED — historical record. Implemented via PR #78 (squash commit `33fb926`); this v1 plan is retained as the approved design rationale for Slice 44.

> **Persona.** Senior application-security verification and PostgreSQL governance architect, applying
> fail-closed evidence design, tenant isolation, and Sanad / No-Free-Facts discipline.
>
> **Primary Sanad.** The security-reviewer archetype must detect authz flaws, prompt injection, secrets
> exposure, unsafe tools, and supply-chain risk, with severity classification, zero missed critical
> vulnerabilities, and high-severity recall expectations (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:912-930`, especially line 920). Reviewer QA requires primary-evidence inspection,
> adversarial sampling, miss-rate tracking, blind challenge review, and human calibration where policy
> requires it (spec §13.5, `spec:1315-1345`). Security evidence belongs in the evidence pack and security
> approval is part of Done (spec §15, `spec:1413-1544`, especially `1448-1458,1474-1490`). Product and
> platform threats include auth/authz, secrets, input validation, dependency/supply-chain risk, prompt
> injection, tool privilege escalation, audit tampering, collusion, and connector compromise (spec §16,
> `spec:1548-1684`). Go-live requires no critical security finding open and Appendix-B gate #5 requires no
> **unaccepted** critical security finding open (`spec:2251-2271,2981-2989`). Phase 5 calls for review,
> verification, and evidence (`spec:2487-2498`). The canonical intake template provides project-specific
> sensitive-data, threat, compliance, audit, and privacy inputs, but no executable scan contract
> (`docs/UAID_OS_Intake_Template_Pack_v1_2/15_security_privacy_compliance.md:1-11`). The roadmap commits
> Slice 44 to verified scan coverage feeding the existing findings store and making gate #5 PASS-capable
> (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:409-419,659-665`).
>
> **Verified repository Sanad.** `main` and `origin/main` are `e117bf3`, the tree is clean, and only `main`
> exists (`git status`, `git branch -a`, and `git rev-parse`, verified 2026-07-12). Alembic reports
> `0042 (head)` and the current migration is `0042_test_oracles` (`uv run alembic heads` with a temporary
> cache; `migrations/versions/0042_test_oracles.py:1-23`). A5 ruleset is `slice43.v1`; gate #5 always returns
> `insufficient_evidence:no_finding_provenance_or_scan_source` using open-security counts only, while
> go-live is hard-false (`app/release/production_autonomy.py:1-54,96-108,120-175,252-263,477-494`). The A5
> repository reads only project-wide open and open-critical security-finding counts for gate #5
> (`app/repositories/production_autonomy.py:97-125,171-200`). Readiness remains `slice20.v1`
> (`app/intake/readiness.py:45`) and is a separate structural-intake evaluator.
>
> The existing Slice-23 store already owns the security taxonomy and lifecycle: security categories are
> `authz`, `injection`, `secrets_exposure`, `unsafe_tool`, `supply_chain`, `other`; findings start `open`;
> critical findings cannot be accepted; non-critical acceptance requires a usable risk-acceptance record
> (`app/release/findings.py:18-92`; `app/repositories/release_findings.py:24-162`). The DB guard locks every
> new finding to `source_provenance='caller_supplied_unverified'`, makes source/content immutable, enforces
> one-way lifecycle rules, and blocks DELETE/TRUNCATE (`migrations/versions/0022_release_findings.py:27-37,
> 127-281`). Slice 23 explicitly deferred authoritative scan coverage to a future slice
> (`.planning/SLICE-23-PLAN.md:14-26,102-124`; `.planning/SLICE-23-FINDINGS-DISCUSSION.md:39-46,81-86`).
> Slice 43 supplies the reusable exact-declared-repo + exact-commit, bounded/versioned, connector-fetched CI
> artifact pattern; connector retrieval verifies source/binding, while schema validation proves only shape
> (`app/verify/oracle_source.py:1-25,46-99`; `app/release/scm_connector.py:1-81,246-280,399-500`;
> `.planning/SLICE-43-PLAN.md:41-66,130-153`). These verified constraints drive the ODs below.

## Coordinator rulings (final)

- **OD-44-1 = Option A (connector-verified exact-commit CI artifact):** extend SCMConnector/FakeSCMConnector/GitHubSCMConnector with one bounded, versioned security-result artifact method; live network adapter-only, CI uses the fake; stamp artifact_provenance='connector_verified_ci_security' and execution_observation='connector_observed_ci' (never overclaim system_executed).
- **OD-44-2 = Option A (all five canonical categories mandatory, no N/A):** authz, injection, secrets_exposure, unsafe_tool, supply_chain; recorded explicitly as a conservative inference; other is non-gating.
- **OD-44-3 = Option A (additive direct attachment):** nullable security_scan_category_result_id + scan_finding_fingerprint on release_findings; provenance enum gains connector_verified_security_scan; the guard is replaced WITHOUT weakening any Slice-23 rule; downgrade restores the exact pre-0043 guard; existing rows stay unverified — no relabeling.
- **OD-44-4 = Option A (exact binding, latest-wins, no TTL):** bind by (project, declared-repo hash, commit SHA, scanner-manifest hash); any change requires a new run; a later failed run supersedes an older pass.
- **OD-44-5 = Option A (append findings, never auto-close):** the scan path never calls resolve/false_positive/accept/supersede; fingerprint dedupe is per run only; a prior open critical blocks until the explicit lifecycle closes it.
- **OD-44-6 = recommended ruling:** slice44.security_scan.v1; code-owned allowlisted (scanner_key, scanner_version, rule_pack_hash, supported_categories); versioned provider severity maps to low|medium|high|critical; unknown scanner/rule/category/severity fails the affected run; caps: artifact 2 MiB, ≤1,000 findings, summary ≤500, detail ≤4,000, evidence ref ≤500, keys/codes ≤128, all non-blank; raw snippets/secrets/arbitrary scanner JSON never persist.

---

## 0. The defining honesty constraint (the crux)

Slice 44 must keep four claims distinct:

1. **REPORTED:** a scanner/reviewer artifact reports that a category ran, assigns a severity, and describes a
   finding. A report—even one fetched by a connector—is not self-proving. Scanner correctness, detection
   completeness, and narrative accuracy remain bounded claims of the named/versioned source (spec §2.3–2.4,
   `spec:160-193`; reviewer fallibility `spec:1315-1327`).
2. **CONNECTOR-OBSERVED / PARSED:** the platform fetched a bounded, versioned artifact for the project's exact
   declared repository and commit and validated its schema. This can prove retrieval, binding, and declared
   coverage metadata; it cannot prove the scanner has no blind spots or that an empty result means universal
   security (`app/verify/oracle_source.py:1-5,46-99`; Slice-43 precedent
   `.planning/SLICE-43-PLAN.md:48-64`).
3. **DB-PROVEN:** tenant/project/repo/commit binding, exactly-once mandatory-category coverage, immutable run
   history, run→category→finding lineage, count consistency, source tier, open/terminal lifecycle state, and
   the fact that a critical finding cannot be accepted are enforced or recomputed from PostgreSQL rows. The
   current DB proves the final lifecycle rule but does not yet prove scan lineage
   (`migrations/versions/0022_release_findings.py:127-219`; proposed Slice-44 invariants below).
4. **GATE-INFERRED:** complete trusted coverage for the ruled category set plus zero currently open critical
   security findings is sufficient for Appendix-B gate #5. It is **not** proof that the software is
   vulnerability-free, that non-critical findings are harmless, that security approval is complete, or that
   A5/go-live is satisfied (`spec:2253-2266,2983-2997`).

**An empty `release_findings` table or an artifact with `findings=[]` must never pass gate #5 by itself.** A
zero-finding result is meaningful only inside a trusted, exact-binding run that proves every coordinator-ruled
mandatory category completed successfully. Missing, untrusted, malformed, failed, unsupported, partial,
wrong-repo, wrong-commit, count-inconsistent, or superseded coverage fails closed. A current clean scan also
must not silently close a previously open critical finding; OD-44-5 rules that lifecycle boundary.

## 1. Scope and non-goals

### 1.1 In scope (proposed implementation after approval and all OD rulings)

- A strict, versioned, bounded security-scan artifact contract and pure normalizer for the coordinator-ruled
  authoritative source. The contract records named/versioned scanner identity, category coverage, severity,
  finding fingerprint, and evidence digest/reference—not a caller-supplied gate verdict (spec evidence-over-
  claims `spec:160-179`; connector requirements `spec:1676-1684`).
- Extension of the **existing** declared-repository/SCM boundary, not a parallel repository resolver or
  duplicate connector framework (`app/release/project_repo.py:1-60`; `app/release/scm_connector.py:38-53`).
- Reuse of `release_findings` as the one security-finding lifecycle store, with the minimum additive provenance
  attachment selected by OD-44-3. Existing critical-cannot-accept and risk-acceptance rules remain intact
  (`app/release/findings.py:9-13`; `migrations/versions/0022_release_findings.py:159-207`).
- Proposed additive migration **`0043_security_scan_provenance`** after verified head `0042`. `0043` is an
  **inference from the repository's monotonic revision sequence**, not a spec-assigned number; no migration is
  authorized by this plan.
- New scan-evidence tables are tenant-owned, RLS `ENABLE`+`FORCE`, append-only, composite-FK-bound, and guarded
  against direct-SQL count/category/provenance inconsistencies. Existing `release_findings` retains its
  DB-guarded lifecycle mutability; it is not falsely relabelled append-only
  (`migrations/versions/0022_release_findings.py:127-281`).
- Compute-on-read security coverage and a fail-closed A5 gate-#5 ladder. Because gate behavior changes from
  permanently insufficient to PASS-capable, the A5 ruleset advances from `slice43.v1` to proposed
  **`slice44.v1`** (`app/release/production_autonomy.py:54,252-263`).
- Pure and DB-backed tests, including direct-SQL adversarial cases, tenant/project/binding isolation, audit
  minimization, and exact no-regression assertions for every gate other than #5 and for readiness (house
  precedent `.planning/SLICE-43-PLAN.md:410-451`).

### 1.2 Non-goals

- No shortcut/fake-done detector or gate #6 change (Slice 45), no acceptance verifier or gate #8 change
  (Slice 46), no issue-provenance bridge (Slice 47), no reviewer-QA subsystem (Slice 48), no evidence-pack
  auditor (Slice 49), and no go-live agent/release authorization (roadmap
  `.planning/GO-LIVE-END-TO-END-ROADMAP.md:421-505`).
- No claim that Slice 44 implements all §13.5 reviewer-QA controls. §13.5 is grounding for why reviewer claims
  are not automatically trusted; the dedicated reviewer-QA system remains Slice 48
  (`spec:1315-1345`; roadmap `:457-467`).
- No generalized SAST/DAST platform, arbitrary scanner plugin execution, shell execution, uploaded executable,
  dynamic import, user-provided rule code, or provider-agnostic marketplace. Only coordinator-ruled,
  code-owned scanner keys and schemas may become gate-bearing (security inference from Tool Broker and
  connector controls, `spec:1084-1127,1676-1684`).
- No automatic remediation, patch generation, status transition, finding acceptance, false-positive decision,
  or risk acceptance. Those are separate consequential actions; the existing lifecycle remains the authority
  (`app/repositories/release_findings.py:49-83,114-128`).
- No raw SARIF/archive/log/code snippet/secret value persistence or audit payload. The raw artifact is untrusted
  input; only bounded normalized records and cryptographic digests/references may cross the persistence
  boundary (proposed minimization grounded in spec §16.1–16.9, `spec:1548-1684`). This is not a claim that a
  text denylist can guarantee stored narrative is secret-free.
- No HTTP endpoint, UI, scheduler, production deployment, new approval authority, or public scanner trigger.
- No readiness change: `app/intake/readiness.py` must remain byte-stable and `RULESET_VERSION` remains
  `slice20.v1` (`app/intake/readiness.py:45`; separation precedent `.planning/SLICE-43-PLAN.md:399-408`).

## 2. Required security-coverage semantics

The eventual validator must reject missing, unknown, blank, over-cap, non-canonical, duplicate, or
binding-inconsistent data before persistence. DB-representable invariants must be mirrored by CHECKs,
composite FKs, and guards (proposed house discipline; `.planning/SLICE-43-PLAN.md:271-337`).

- **Coverage is per category, not per finding.** A category result is required even when it yields zero
  findings; otherwise absence cannot be distinguished from “scanner never ran” (reasoned inference from the
  Slice-23 empty-store limitation, `.planning/SLICE-23-FINDINGS-DISCUSSION.md:39-46`).
- **Coverage is exact-binding.** Every run is tied to one tenant, project, declared-repo digest, and full commit
  SHA. A run for another repository, project, commit, or later-revised declaration cannot satisfy the gate
  (existing exact-binding pattern `app/repositories/test_oracles.py:203-299`).
- **Coverage has an outcome.** Each mandatory category must say `completed_with_findings`, `completed_clean`,
  `failed`, or `unsupported`; only the two `completed_*` states are coverage. `completed_clean` requires zero
  bound findings; `completed_with_findings` requires one or more. These are proposed non-vacuous states, not
  spec vocabulary.
- **Findings remain lifecycle records.** Every observed vulnerability is inserted `open` into the existing
  store and retains its ruled category/severity. Critical findings cannot be accepted; non-critical findings
  may follow the existing validated lifecycle, which is outside the scan run itself
  (`app/release/findings.py:51-92`; `app/repositories/release_findings.py:49-83`).
- **Severity and category are normalized, versioned decisions.** Provider strings cannot silently become UAID
  severity/category values. Unknown tool, rule, category, or severity fails closed under OD-44-6; Appendix B
  gate #5 depends specifically on the critical axis (`spec:2989`; current enums
  `app/release/findings.py:18-29`).
- **Non-critical findings do not directly fail gate #5.** Appendix B #5 is the “unaccepted critical” gate;
  non-critical lifecycle/risk belongs elsewhere in the conjunction. Their counts remain visible safe context,
  and Slice 44 does not auto-accept or hide them (`spec:2253-2271,2983-2991`).

## 3. Evidence and verdict model

### 3.1 Truth/provenance axes

- `artifact_provenance` identifies how the scan artifact was obtained; the proposed gating tier is selected by
  OD-44-1. Caller-supplied artifacts may be recorded only as explicitly unverified/non-gating if the
  coordinator authorizes that diagnostic path (two-tier precedent `app/models/test_oracle_run.py` and
  `migrations/versions/0042_test_oracles.py:87-95`).
- `execution_observation` states what UAID actually knows: a connector can observe a successful CI run and
  retrieve its artifact; it does not independently witness every scanner instruction. The plan must use
  `connector_observed_ci`, not overclaim `system_executed`, unless OD-44-1 chooses a UAID-controlled execution
  path with separately proven semantics (honesty precedent `app/verify/oracle_source.py:1-5`).
- `scanner_manifest_hash` pins the ordered set of scanner keys/versions/rule-pack hashes used for category
  coverage. It proves which declared manifest was reported; it does not certify scanner quality. This is a
  proposed reproducibility mechanism grounded in the spec's versioned eval/source requirements
  (`spec:914-930,2091-2108`).
- A run-level coverage verdict is DB-derived or deferred-trigger-verified from child category rows and bound
  findings. No API accepts `coverage_complete`, `clean`, or gate status as a caller-controlled fact (proposed
  reuse of Slice-43's parent/child verifier, `migrations/versions/0042_test_oracles.py:295-447`).

### 3.2 Latest-wins and open-finding interaction

For the exact binding ruled by OD-44-4, gate #5 uses the latest committed run ordered by
`(created_at DESC, id DESC)`. A later failed/refused/incomplete/untrusted run supersedes an older complete run;
history is never deleted. Separately, the gate counts **all currently open critical security findings in the
project, regardless of source provenance**. A manually reported critical is known blocker evidence even when
it cannot establish scan coverage. A clean latest run cannot erase an unresolved earlier critical finding
(proposed conservative rule; existing terminal lifecycle
`app/release/findings.py:51-53`; exact-binding precedent `app/repositories/test_oracles.py:226-299`).

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-44-1 — What is an authoritative scan source?

**Gap:** the repository has an SCM connector and exact-commit CI artifact pattern, but no security-scan method,
scanner contract, SARIF parser, or trusted security-review execution (`app/release/scm_connector.py:38-53`;
repository scan performed during orientation). The current findings store accepts only caller-unverified
sources (`migrations/versions/0022_release_findings.py:136-142`).

**Options:**

- **A — connector-verified exact-commit CI artifact (recommended):** extend `SCMConnector` with one bounded,
  versioned security-result artifact method. The live GitHub adapter resolves the project's declared repo,
  selects an exact-commit successful workflow artifact, and returns a strictly parsed
  `slice44.security_scan.v1` document; tests use `FakeSCMConnector` only. Stamp
  `artifact_provenance='connector_verified_ci_security'` and
  `execution_observation='connector_observed_ci'`. This matches Slice 43's proven boundary
  (`app/release/scm_connector.py:49-81,246-280,399-500`) but does not claim scanner infallibility.
- **B — hybrid provider APIs plus CI artifact:** GitHub code-scanning/secret-scanning/dependency endpoints
  supply supported provider facts, while a versioned CI artifact covers authz/injection/unsafe-tool. This may
  strengthen source diversity but adds permissions, pagination, cross-endpoint completeness, and partial-read
  semantics that require a larger connector contract (inference from spec connector controls
  `spec:1084-1127,1676-1684`).
- **C — caller-supplied artifact:** useful only as `caller_supplied_unverified`; categorically non-gating.
- **D — LLM/agent reviewer verdict:** non-gating in this slice unless the coordinator expands scope to a
  separately controlled execution and reviewer-QA design. General agent execution and Slice-48 reviewer QA are
  not present (`CLAUDE.md` Current status; roadmap `:457-467`).

**No ruling ⇒** gate #5 remains `insufficient_evidence:no_finding_provenance_or_scan_source`.

### OD-44-2 — Which security categories are mandatory for gate-bearing coverage?

**Gap:** the security archetype names five categories, while §16.1 lists a broader product-security review and
the intake template is project-specific prose (`spec:920,1550-1568`; template `15_*:1-11`). No current table
proves a risk-tuned applicability decision.

**Options:**

- **A — all five canonical categories, no N/A (recommended):** require `authz`, `injection`,
  `secrets_exposure`, `unsafe_tool`, and `supply_chain` for every gate-bearing run. This is a conservative
  inference from the security-reviewer archetype and exactly matches the existing Slice-23 taxonomy excluding
  the `other` escape hatch (`app/release/findings.py:21-29`).
- **B — reviewed applicability matrix:** allow a category to be `not_applicable` only through a new
  independently approved, exact-binding applicability artifact. Stronger flexibility, but the repository has
  no such authority/completeness store; this expands Slice 44.
- **C — full §16.1 universe:** require every listed product-security domain. This is broadest but exceeds the
  roadmap's five-category Slice-44 commitment and needs a new taxonomy (`roadmap:409-419`).

**No ruling ⇒** `security_scan_scope_resolved=False`; gate #5 cannot pass.

### OD-44-3 — How does verified scan provenance attach to existing `release_findings`?

**Gap:** `release_findings.source_provenance` is immutable and INSERT-locked to
`caller_supplied_unverified`; no scan-run FK exists (`app/models/release_finding.py:63-86`;
`migrations/versions/0022_release_findings.py:27-30,136-161`).

**Options:**

- **A — additive direct attachment (recommended):** add nullable `security_scan_category_result_id` and
  `scan_finding_fingerprint` to `release_findings`; extend the provenance enum/guard with
  `connector_verified_security_scan`. A composite FK includes `(category-result, project, tenant, category)`,
  and a DB guard requires all verified-provenance fields together, `finding_type='security'`, a trusted
  successful parent run, and count consistency. Existing/manual rows remain unverified and unchanged.
- **B — append-only binding table:** leave the finding row's provenance unverified and create
  `security_scan_finding_bindings` that composite-links the run/category result to the finding. Gate #5 trusts
  only valid bindings. This minimizes alteration of the Slice-23 row but creates two provenance surfaces and
  requires careful API/report honesty: the finding itself is still caller-unverified.
- **C — separate security-finding table:** rejected as a default because it forks the existing lifecycle store
  the roadmap says to feed and risks inconsistent critical/risk-acceptance rules
  (`roadmap:410-419`; `app/repositories/release_findings.py`).

**No ruling ⇒** scan coverage may be recorded, but no finding can be treated as verified and gate #5 cannot
pass.

### OD-44-4 — What exact binding and freshness rule invalidates old scan coverage?

**Options:**

- **A — exact declared repo + commit, latest-wins, no wall-clock TTL (recommended):** bind by
  `(project, declared-repo hash, commit SHA, scanner-manifest hash)`. Any repo/commit/manifest change requires
  a new run; the latest failed run supersedes an old pass. This mirrors the ruled Slice-43 model
  (`app/repositories/test_oracles.py:203-299`).
- **B — frozen release-candidate binding:** bind scans to a release candidate. Current candidates have
  `release_ref` and issue membership but no repository/commit identity, so this requires additional release
  scope design (`app/models/release_candidate.py:29-66`).
- **C — exact binding plus TTL:** additionally expire coverage after a configured interval. Neither the spec
  nor current roadmap supplies a universal security-scan TTL, so the coordinator must provide the policy
  source and value.

**No ruling ⇒** `security_scan_binding_resolved=False`; gate #5 cannot pass.

### OD-44-5 — What does a later scan do to findings from earlier scans?

**Options:**

- **A — append findings; never auto-close (recommended):** the scan path creates new open findings (deduped
  within the run by a fingerprint) and never calls `resolve`, `mark_false_positive`, `accept`, or `supersede`.
  A previous open critical remains blocking until the existing explicit lifecycle closes it. This treats
  “not found this time” as insufficient to prove remediation or false positive.
- **B — auto-supersede exact fingerprints absent from a later complete run:** reduces stale findings but turns
  absence into a lifecycle decision and may hide intermittent or scanner-regression defects.
- **C — update/reuse one finding row across scans:** conflicts with immutable source/content fields and erases
  per-run observation history (`migrations/versions/0022_release_findings.py:27-30,159-170`).

**No ruling ⇒** the conservative Option-A behavior is required for safety, but implementation still remains
blocked until the coordinator explicitly binds it.

### OD-44-6 — What is the versioned scan schema, scanner allowlist, severity map, and text cap?

**Recommended ruling:** `slice44.security_scan.v1`; exactly five category results under OD-44-2 Option A;
code-owned allowlisted `(scanner_key, scanner_version, rule_pack_hash, supported_categories)` entries;
provider severity maps versioned in code to `low|medium|high|critical`; unknown scanner/rule/category/severity
fails the affected run; `other` is non-gating; canonical artifact cap 2 MiB, at most 1,000 findings, finding
summary ≤500 characters, detail ≤4,000 characters, evidence reference ≤500 characters, and all keys/codes
≤128 characters with non-blank checks. Raw snippets, raw secrets, and arbitrary scanner JSON never persist.
These numeric caps are **proposed engineering safety bounds**, not spec facts, and require this ruling.

**Alternatives:** permit artifact-supplied UAID severity/category (weaker because normalization is merely
reported), or adopt a separately reviewed SARIF subset with code-owned rule mappings. A generic unbounded
SARIF pass-through is rejected because it violates bounded-input and data-minimization requirements
(`spec:1548-1684`).

**No ruling ⇒** the parser may reject all production artifacts; gate #5 cannot pass.

## 5. Proposed pure and connector modules (contingent on §4 rulings)

### 5.1 `app/verify/security_scan.py`

- Frozen `SecurityScanArtifact`, `ScannerManifestEntry`, `CategoryCoverage`, `NormalizedSecurityFinding`,
  `SecurityCoverageDecision`, and `Gate5Evidence` value objects with deterministic `to_dict()`.
- Exact constants and caps bound by OD-44-2/6; every text is non-blank and bounded; hashes are
  `sha256:<64 lowercase hex>`; commit SHA is 40 lowercase hex; JSON uses canonical encoding and rejects
  NaN/Infinity/unknown fields (proposed reuse `app/verify/oracle_source.py:14-37,46-99`).
- `validate_security_scan_artifact(payload, expected_commit_sha)` enforces the ruled discriminated schema,
  exact binding, unique category coverage, code-owned scanner support, severity normalization, unique finding
  fingerprints, and coverage/finding count agreement. It never accepts `gate_passed` or `clean` as an
  authoritative caller field.
- `scanner_manifest_hash()` and `artifact_digest()` canonicalize validated safe metadata; raw artifact bytes
  are discarded after parsing.
- `evaluate_security_coverage(run, category_children, bound_findings)` recomputes coverage and returns
  explicit failures; zero findings can pass this pure coverage decision only when all mandatory category rows
  are trusted and complete. The A5 gate separately evaluates open critical findings.

### 5.2 Existing connector extension

- Under OD-44-1 Option A, extend `SCMConnector`, `FakeSCMConnector`, and `GitHubSCMConnector` with
  `fetch_security_scan_artifact(repo_ref, commit_sha)` and an archive parser. Use a distinct fixed artifact
  name/file, safe ZIP rules, exact-commit validation, bounded streaming before accumulation, no raw response
  logging, and no redirect credential leakage (Slice-43 precedent `app/release/scm_connector.py:56-81,
  399-500`).
- Resolve the repository through `resolve_declared_repo`; never accept a caller repo string at the service
  boundary (`app/release/project_repo.py:40-60`). Live network remains adapter-only; all CI tests inject the
  fake. No scanner or connector credential is persisted/audited.
- If OD-44-1 selects Option B, the plan must be revised with exact endpoint permissions, pagination,
  partial-read semantics, and source-completeness rules before implementation; this v1 plan does not silently
  invent them.

## 6. Storage and proposed migration `0043` (additive only; contingent on §4)

The following is the recommended OD-44-3 Option-A shape. If the coordinator selects another option, this
section must be revised and re-reviewed before implementation.

Both new tables are tenant-owned; each has composite `(project_id,tenant_id)→projects`, RLS `ENABLE`+`FORCE`,
`tenant_isolation` `USING`+`WITH CHECK`, `REVOKE ALL FROM PUBLIC`, and `GRANT SELECT,INSERT TO uaid_app`.
UPDATE/DELETE/TRUNCATE are blocked by row/statement triggers. Every child FK includes project+tenant. This is
proposed reuse of the Slice-43 migration pattern
(`migrations/versions/0042_test_oracles.py:149-178,451-470`).

### 6.1 `security_scan_runs` — immutable coverage parent

Proposed columns:

- identity/binding: `id`, `tenant_id`, `project_id`, `provider`, `repo_binding_hash`, `commit_sha`,
  `artifact_schema_version`, `scanner_manifest_hash`, `artifact_digest`, `created_at`;
- observation: `execution_status` (`succeeded|failed|refused`), `artifact_provenance`,
  `execution_observation`, nullable bounded `failure_code`;
- trigger-verified snapshots: `reported_category_count`, `reported_finding_count`; DB-derived/verified
  `coverage_complete` and
  `coverage_verdict` (`covered|failed`). No public method accepts the derived fields.

Constraints/guards:

- provider/schema/provenance/status enums; exact hash/SHA formats; all counts non-negative and bounded;
  status/provenance/nullability coherence; failed/refused runs have zero category children and a failure code;
  succeeded runs require ruled trusted provenance and mandatory-category children.
- A DEFERRABLE INITIALLY DEFERRED parent/child verifier recomputes category count, bound-finding count,
  per-category counts, mandatory-set equality, and coverage verdict. Direct SQL cannot make an empty or
  partial run `covered` (proposed Slice-43 mechanism `migrations/versions/0042_test_oracles.py:321-447`).
- Index supports exact-binding latest selection by tenant/project/repo/commit/manifest/created_at/id; no
  uniqueness constraint erases rerun history.

### 6.2 `security_scan_category_results` — immutable proof that each category ran

Proposed columns:

- `id`, `tenant_id`, `project_id`, `security_scan_run_id`, `category`, `scanner_key`, `scanner_version`,
  `rule_pack_hash`, `coverage_status`, `reported_finding_count`, `evidence_digest`, `created_at`;
- one row per `(run,category)`; category/scanner compatibility comes from the OD-44-6 code-owned manifest and
  is snapshotted/DB-guarded; `completed_clean` iff count=0, `completed_with_findings` iff count>0;
  `failed|unsupported` never counts as coverage.

Constraints/guards:

- composite FK `(security_scan_run_id,project_id,tenant_id)→security_scan_runs`; composite UNIQUE target
  `(id,project_id,tenant_id,category)` for the findings attachment; exact enums/hash formats and bounded,
  non-blank scanner fields; category must be in the ruled set.
- deferred verification counts OD-44-3-bound findings for the exact category result. A security finding from
  another tenant/project/category/run, an unverified finding, a duplicate fingerprint, or a non-security row
  cannot satisfy the reported count.

### 6.3 Additive `release_findings` provenance attachment (OD-44-3 Option A)

Proposed additive columns:

- nullable `security_scan_category_result_id`;
- nullable `scan_finding_fingerprint` (`sha256:<64 lowercase hex>`).

Proposed constraint/guard replacement:

- `source_provenance` allows existing `caller_supplied_unverified` plus
  `connector_verified_security_scan`.
- Existing/manual path: both new columns NULL and provenance unverified. Verified path: both non-NULL,
  `finding_type='security'`, `source_provenance='connector_verified_security_scan'`, source is a bounded
  code-owned label, summary/detail/evidence fields meet OD-44-6 caps, and the composite FK
  `(security_scan_category_result_id,project_id,tenant_id,category)` resolves a trusted successful category
  result. Unique `(tenant_id,security_scan_category_result_id,scan_finding_fingerprint)` prevents duplicate
  observations within a run.
- The `release_findings_guard()` is replaced **without weakening any Slice-23 rule**: created-open invariant,
  immutable identity/content/source, category-per-type checks, `other` rule, one-way transitions,
  critical-cannot-accept, accepted-record validation, no DELETE/TRUNCATE, event trail, and grants all remain
  (`migrations/versions/0022_release_findings.py:127-281`). Downgrade restores the exact pre-0043 guard before
  dropping additive columns/tables.
- Existing rows require no backfill and remain explicitly unverified/non-gating. No migration may relabel
  historical findings as connector verified.

### 6.4 Audit and sensitive-data boundary

Audit safe metadata only: scan/category/finding IDs, project ID, provider, category, execution/coverage status,
provenance tier, counts, scanner/manifest version identifiers or hashes, and failure-code enum. Do **not** audit
repo ref, commit SHA unless separately approved safe, artifact URL/run URL, raw artifact, rule output, source
path, code snippet, summary/detail, evidence reference, fingerprint input, token, credential, or provider
response. Existing finding audits remain content-free (`app/repositories/release_findings.py:147-162`).

The normalized finding row may contain bounded project-sensitive summary/detail needed for lifecycle review;
that content is RLS-protected but is not claimed secret-free. Raw artifacts are not persisted. This is a
proposed minimization boundary, not a guarantee against every scanner accidentally emitting sensitive text.

## 7. Repository/orchestrator behavior

Proposed `app/repositories/security_scans.py` owns the connector-controlled write path:

1. Resolve tenant/project and the project's currently declared repo before any external I/O; reject
   undeclared/malformed/cross-project input (`app/release/project_repo.py:40-60`).
2. Validate the caller-supplied full commit SHA shape, ask the coordinator-ruled connector for that exact
   binding, and validate the returned artifact. A caller never supplies trusted provenance or a raw repo ref.
3. Normalize categories/severities through the ruled code-owned manifest. Any malformed/unknown/over-cap
   item fails or refuses the run according to OD-44-6; it is never silently dropped if dropping could make
   coverage appear clean.
4. In one transaction insert the run, all category results, and all verified `release_findings`; deferred DB
   guards recompute counts/coverage at commit. On safe connector/parse failure, record a failed/refused run
   with no coverage children if the ruled source contract permits it; never preserve an old passing run as
   current after a newer failed attempt (OD-44-4).
5. Under OD-44-5 Option A, never mutate prior finding lifecycle. Fingerprint dedupe is per run only; the same
   vulnerability observed in a later run creates another observation rather than silently altering history.
6. `latest_for_binding(...)` returns exact-binding latest only. `coverage_for_project(...)` returns safe
   booleans/counts for unresolved scope/binding, absent run, untrusted artifact, execution failure, incomplete
   categories, inconsistent evidence, all open findings, all open critical findings, and complete coverage. A5
   receives no repo ref, commit, summary, detail, raw rule, path, URL, or scanner output.

No public method accepts `coverage_complete`, run verdict, gate status, verified source tier, or lifecycle
terminal status. Trusted provenance is stamped only after the connector path returns a valid exact-binding
artifact (app-stamped provenance precedent `app/repositories/test_oracles.py:100-201,338-395`).

## 8. A5 gate #5 and readiness — exact change

### 8.1 A5 changes

`app/release/production_autonomy.py` and `app/repositories/production_autonomy.py` **do change** because Slice
44 replaces gate #5's permanent `no_finding_provenance_or_scan_source` result with a real fail-closed evidence
ladder. The A5 report ruleset becomes **`slice44.v1`**. Gate #5 becomes the **sixth PASS-capable gate** after
#1/#2/#3/#4/#11; no other gate algorithm, ordering, reason, or context changes
(`app/release/production_autonomy.py:1-45,252-272,477-494`).

Proposed gate #5 ladder after all ODs are bound:

1. unresolved category scope → `insufficient_evidence:security_scan_scope_unresolved`;
2. unresolved declared-repo/commit binding → `insufficient_evidence:security_scan_binding_unresolved`;
3. no exact-binding run → `insufficient_evidence:security_scan_not_executed`;
4. latest artifact source untrusted → `insufficient_evidence:security_scan_observed_unverified`;
5. latest execution failed/refused → `insufficient_evidence:security_scan_execution_failed`;
6. missing/failed/unsupported mandatory category → `insufficient_evidence:security_scan_coverage_incomplete`;
7. run/category/finding counts inconsistent → `insufficient_evidence:security_scan_evidence_inconsistent`;
8. any open critical security finding, regardless of source provenance →
   `insufficient_evidence:critical_security_findings_open`;
9. **only with trusted exact-binding complete coverage and zero open critical security findings** →
   `passed:no_unaccepted_critical_security_findings_verified`.

Context is safe counts/booleans only: scope/binding resolved, mandatory/completed/failed category counts,
trusted/untrusted/failed run counts, open security count, open critical security count, and a latest-coverage
complete boolean. It excludes repo/commit/artifact/scanner URLs, finding text, evidence refs, fingerprints,
rule names, paths, and raw output. Non-critical open findings remain context and do not directly fail Appendix-B
gate #5 (`spec:2989`); they are not accepted or hidden by this gate.

### 8.2 What does not change

- Gate #6 remains `insufficient_evidence:no_finding_provenance_or_scan_source`; Slice 44 must not reuse
  security coverage as shortcut-detector coverage (`app/release/production_autonomy.py:264-272`; roadmap
  `:421-431`).
- Gates #1–#4 and #7–#13 remain byte-for-byte semantically unchanged for identical inputs; regression tests
  compare their serialized gate dicts before/after. Gate ordering remains 1..13.
- `app/intake/readiness.py` is untouched and stays `slice20.v1`; R5 intake declarations are not security scan
  execution evidence (`app/intake/readiness.py:45,233-284`).
- `can_go_live_autonomously` remains hard-false. Gates #6/#7/#8/#9/#10/#12/#13 remain unmet, and the required
  request-authenticated A5 preapproval still does not exist (`app/release/production_autonomy.py:41-45,
  61-64,96-108,477-494`). Therefore go-live remains false regardless of gate #5.

## 9. Test plan for the eventual implementation

### 9.1 Pure / Docker-free

- Artifact validator: exact valid schema; unknown/missing fields; malformed/uppercase/wrong commit; wrong
  repo-binding digest; empty/duplicate/over-cap categories/findings; malformed JSON; NaN/Infinity; oversized
  artifact; blank/over-cap text; unknown scanner/rule-pack; duplicate fingerprint; forbidden raw/snippet
  fields; no caller gate/verdict field.
- Category coverage: all five ruled categories; each missing category; duplicate; `failed`; `unsupported`;
  `completed_clean` with nonzero finding count; `completed_with_findings` with zero; zero total findings with
  all categories complete succeeds at coverage layer; zero findings with absent coverage fails.
- Severity/category normalization: every ruled provider mapping; unknown severity/category/rule fails closed;
  `other` non-gating; critical remains critical; no silent downgrade.
- Connector/archive parser under OD-44-1 A: one safe file; wrong filename; multiple members; path traversal;
  directory/encrypted/oversized member; zip bomb/stream cap; malformed payload; commit mismatch; fake connector
  only, no network/token in CI (Slice-43 precedent `tests/test_test_oracles.py`).
- Latest/binding: exact repo+commit+manifest only; repo revision/commit/manifest mismatch; later failed run
  supersedes old complete run; no wall-clock TTL under OD-44-4 A; deterministic reason precedence.
- Lifecycle interaction: prior open critical blocks a later clean run; resolved/false-positive critical is no
  longer open; accepted critical is impossible; non-critical open does not directly fail gate #5; scan path
  never calls lifecycle transitions under OD-44-5 A.
- A5: every ladder rung plus passing rung; `ruleset_version='slice44.v1'`; gate #5 becomes PASS-capable; all
  other gate dicts unchanged; `a5_satisfied` and `can_go_live_autonomously` remain false in this slice.
- Readiness: source hash/bytes and representative reports unchanged; `ruleset_version='slice20.v1'`.

### 9.2 DB-backed, including direct-SQL adversarial cases

- Migration round trip `0042→0043→0042→0043`; current head/model/catalog parity; exactly the approved additive
  tables/columns/constraints/guards; downgrade restores the pre-0043 findings guard exactly.
- RLS same-tenant success and cross-tenant invisibility; PUBLIC revoked; exact grants; RLS ENABLE+FORCE on both
  new tables; cross-project/tenant run/category/finding composite FKs refused.
- UPDATE/DELETE/TRUNCATE refused on scan runs/category results; historical reruns retained. Existing findings
  lifecycle DML remains exactly as Slice 23 specifies—no blanket append-only rewrite.
- Direct SQL rejects: trusted finding without category result; unverified finding with scan attachment;
  non-security/incorrect category attached; wrong project/tenant/run; failed/untrusted parent run; duplicate
  fingerprint; malformed hashes/SHA/enums; blank/over-cap scanner/finding text; unknown category/scanner;
  count mismatch; success with zero children; missing/duplicate mandatory category; clean category with bound
  finding; findings category with zero bound findings; parent aggregate/verdict fabrication.
- Direct SQL preserves every Slice-23 backstop: non-open create refused; content/source mutation refused;
  terminal re-transition refused; critical acceptance refused; non-critical acceptance without a usable record
  refused; DELETE/TRUNCATE refused; event rows append-only
  (`migrations/versions/0022_release_findings.py:136-281`).
- Repository success writes run/category/finding rows atomically and commit-time verification passes; connector,
  parsing, or validation failure cannot create trusted coverage; later failed attempt becomes latest.
- Audit sentinel test places secret-like strings, source paths, raw output, URLs, and narrative in source input
  and proves audit payload contains only the approved metadata. Raw artifact bytes are absent from all new
  tables; finding narrative remains only in the existing RLS-protected row.
- Production-autonomy repository consumes exact-binding latest coverage and the existing all-source
  open-critical count. Wrong-binding/unverified/manual findings never satisfy **coverage**, but any manual or
  verified open critical finding still blocks; trusted complete coverage plus zero open critical makes
  **only gate #5** pass.

### 9.3 Verification commands (eventual implementation only)

`git diff --check`; focused pure test file; focused DB test file; `make test`; `make test-db`; migration
`0042→0043→0042→0043`; CI. All LLM/connector tests use fakes and no live network. These are implementation
review requirements, **not commands authorized by this plan-only task**
(`.planning/SLICE-43-PLAN.md:447-451`).

## 10. Proposed file touch map (eventual implementation only)

- New: `app/verify/security_scan.py`, `app/models/security_scan_run.py`,
  `app/models/security_scan_category_result.py`, `app/repositories/security_scans.py`,
  `migrations/versions/0043_security_scan_provenance.py`, `tests/test_security_scans.py`.
- Modify under OD-44-1 A: `app/release/scm_connector.py` and only the existing service/config/tool-policy
  files required for a broker-gated read. No duplicate repository resolver or connector framework.
- Modify under OD-44-3 A: `app/models/release_finding.py`, `app/release/findings.py`,
  `app/repositories/release_findings.py`, and `app/models/__init__.py`; preserve every existing lifecycle rule.
- Modify for gate #5 only: `app/release/production_autonomy.py`,
  `app/repositories/production_autonomy.py`, focused production-autonomy/API golden tests as required.
- `app/intake/readiness.py` must not change. No Slice-45/46/47/48/49/50 file is in scope.
- No code file, migration, test, branch, or PR is authorized until this plan is approved and OD-44-1 through
  OD-44-6 are explicitly ruled. This file is the sole deliverable now.

## 11. Must NOT claim

- Must NOT claim “no security findings” from an empty store, empty list, missing scanner, failed scanner,
  unsupported category, or partial scan coverage.
- Must NOT claim connector-verified retrieval proves scanner correctness, complete vulnerability detection,
  exploitability, remediation, or absence of blind spots.
- Must NOT claim a reported scanner severity/category is DB-proven unless it passed the ruled code-owned
  normalization and exact scan-lineage constraints.
- Must NOT ignore a manually reported or otherwise unverified open critical finding merely because it cannot
  establish authoritative scan coverage; all open critical security findings block gate #5.
- Must NOT claim a DB-proven run/finding link proves the finding narrative is true; it proves lineage, shape,
  binding, and lifecycle state.
- Must NOT claim a later clean scan resolves, supersedes, or makes a prior open critical finding false.
- Must NOT claim `false_positive`, `resolved`, or `accepted` without the existing explicit lifecycle action;
  critical findings remain non-acceptable (`app/release/findings.py:9-13`).
- Must NOT claim non-critical findings are safe merely because Appendix-B gate #5 keys on critical findings.
- Must NOT claim `other` category coverage satisfies any mandatory ruled security category.
- Must NOT claim Slice 44 implements shortcut detection, acceptance verification, reviewer QA, evidence-pack
  completeness, release preapproval, deployment, or go-live.
- Must NOT claim readiness `slice20.v1` proves scan execution or security approval.
- Must NOT claim a passing gate #5 means A5 is satisfied or production may deploy. Go-live remains hard-false.
- Must NOT claim live connector/provider/scanner tests ran in CI; every connector test uses fakes.

## 12. Definition of done for the eventual implementation — not this plan

After explicit plan approval and coordinator rulings: the ruled authoritative exact-binding source produces a
strict bounded/versioned scan artifact; every ruled mandatory category has immutable DB-proven coverage,
including honest zero-finding coverage; findings reuse the Slice-23 lifecycle with DB-guarded composite
lineage and critical-cannot-accept preserved; new scan-evidence tables are tenant-owned RLS ENABLE+FORCE and
append-only; direct SQL cannot fake structural coverage, counts, or category/lineage coherence; the trusted
source tier remains an application-stamped connector observation and is not misrepresented as DB proof of a
network call; audit carries safe metadata only; gate #5 is fail-closed and PASS-capable only when exact-binding
trusted coverage is complete and zero open critical security findings remain; **all** open critical security
findings block regardless of source; A5 ruleset is `slice44.v1`; every other A5 gate is unchanged;
readiness remains byte-stable `slice20.v1`; go-live remains hard-false; migration `0043` round-trips; pure+DB
suites and CI pass. Sources: spec §9.5.1, §13.5, §15, §16, §24.1, §26.5, Appendix B #5
(`spec:912-930,1315-1345,1413-1684,2251-2271,2487-2498,2981-2989`), roadmap Slice 44
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:409-419`), and repository constraints cited throughout.

---

**Review request:** **APPROVE or REJECT this plan only.** On rejection, identify the exact section and required
correction. On approval, the coordinator must still rule OD-44-1 through OD-44-6 before any branch, code,
migration, tests, or PR begins. This file is the sole authorized deliverable for the present task.
