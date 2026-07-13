# Slice 49 — Evidence-pack generator + auditor + export (§15 / §27.11 / §28.1) — PLAN v1

**Status:** APPROVED FOR EXECUTION — v1 approved; OD-49-1…8 ruled and bound (see Rulings section)

## Coordinator rulings (final)

OD-49-1 = Option A: the checked-in uaid.evidence_pack.v1.2 asset is canonical and must not be modified; add the code-owned slice49.evidence_pack.v1 semantic contract with the expansion allowlist on top; declare jsonschema as a direct project dependency; validate with Draft202012Validator + FormatChecker (check_schema at init/test time; format checking at export time). Unknown caller fields fail the semantic contract even though the shallow schema permits them.

OD-49-2 = Option A (staged finalization): persist immutable core assemblies without inventing a verdict or signature; canonical evidence_pack.json export is refused until a real Slice-50 verdict attestation exists. Sub-ruling: once that attestation exists, canonical export is permitted with explicit signature_status=unsigned_signer_tier_not_implemented; full signed assurance stays deferred to Slice 60. Core, verdict attestation, and signature attestation are separate append-only records; reserve their interfaces without implementing Slices 50/60. Never emit a placeholder verdict; never put a hash in signatures.

OD-49-3 = Option A: one exact currently-frozen candidate; snapshot its issue bindings; conservative canonical-artifact scope cut off at frozen_at; verification evidence selected at generation time; repo/commit evidence binding derived only when trusted Slice-43/44/45 sources agree — disagreement refuses a single binding and records the disagreement state; absent trusted commit evidence is an explicit labeled missing-binding state (core assembly may still complete). Never claim a candidate→commit FK or complete feature scope.

OD-49-4 = Option A: restricted global audit_chain_verifications, admin-only insert via the locked real-audit_verify() transaction capturing the exact verified-through (seq, entry_hash); failed checkpoints retained as operator evidence but never pack-satisfying; uaid_app gets only the narrow safe reference read (ID/time/seq/hash/contract/status); no privilege widening.

OD-49-5 = Option A (conservative inventory): every canonical section structurally present; explicit source-inventory results for all twelve named source classes; empty only with code-owned zero/absence reasons; latest-wins includes later failures/refusals; lifecycle sections use complete bound sets; missing required sources make the assembly incomplete.

OD-49-6 = Option A (append-only layers): attempts, cores, refs, section results, and future attestations all append-only; failed attempts stay visible; changed anything ⇒ new assembly; historical assemblies remain exportable as history; new generation requires a currently frozen candidate; no invented TTL; source-specific freshness snapshotted.

OD-49-7 = Option A: refs + digests + bounded scalar metadata only; the stated caps (core ≤8 MiB, JSON ≤16 MiB, MD ≤4 MiB, ≤10,000 items/section, ≤50,000 refs and edges, strings bounded/non-blank); canonical JSON = UTF-8, sorted keys, no insignificant whitespace, SHA-256 over exact bytes. Sub-ruling: store the exact canonical text bytes (authoritative for hashing) plus normalized child rows for source refs and section results. App-audited properties are never claimed as DB proofs.

OD-49-8 = Option A: internal service/repository methods only — audited core preview (labeled not_canonical_export), canonical JSON only when OD-49-2 permits, deterministic safe Markdown, unsigned hash manifest; every export re-audits stored bytes; no HTTP, PDF, archive, links, accounts, OSCAL, or signer.

## 0. The defining honesty constraint (the crux)

An evidence pack is an **assembly of evidence with preserved lineage**, not an evidence upgrade and not a
release decision. The spec calls it “the artifact of done” and a reviewable evidence bundle, but also says an
export is a claim *about* evidence rather than a replacement for the underlying evidence
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1413-1419,2912-2914`).

Slice 49 therefore must preserve these distinct truth tiers in every section and source reference:

- **REPORTED:** a caller or reviewer supplied content whose row and registration may be DB-bound, but whose
  semantic truth is not independently verified. Slice-42 review-report content is explicitly
  `caller_supplied_unverified`; its reviewer registration and generated `can_merge` value are DB-proven, not
  the report’s semantic correctness (`app/models/review_report.py:1-13,43-68,92-122`).
- **REQUEST-AUTHENTICATED, NOT HUMAN-SIGNED:** Slice-22 risk acceptances may prove actor-bound key custody,
  but the model explicitly says this is not a human signature and never enables go-live
  (`app/models/risk_acceptance_record.py:1-10,97-112`).
- **CONNECTOR-OBSERVED / CONNECTOR-VERIFIED:** Slice-43 test evidence can carry
  `connector_verified_ci`; Slice-44 security runs distinguish `connector_observed_ci` from an attempted
  observation; Slice-45 separately records connector-verified corpus retrieval and UAID execution
  (`app/models/test_oracle_run.py:60-72,132-168`; `app/models/security_scan_run.py:24-75`;
  `app/models/shortcut_detector_run.py:24-80`).
- **SYSTEM-EXECUTED:** UAID executed a code-owned verifier, detector, or controlled challenge. Examples are
  test-oracle execution, Slice-45 deterministic/reviewer execution, Slice-46 structural authorship
  verification, and Slice-48 reviewer QA. This proves only the named, versioned contract ran against its
  bound inputs (`app/models/test_oracle_run.py:99-107,147-168`;
  `app/models/acceptance_verification.py:52-86`; `app/models/reviewer_quality.py:198-210,241-308`).
- **DB-PROVEN:** tenant/project identity, composite-FK linkage, frozen release membership, append-only
  history, generated columns, and exact lineage can be structural facts. They do not prove that all relevant
  issues, requirements, tests, or external facts were discovered (`app/models/release_candidate.py:29-65`;
  `app/models/release_candidate_issue_binding.py:1-10,30-72`;
  `app/repositories/release_candidates.py:1-9`).
- **ADMIN-VERIFIED AUDIT CHECKPOINT:** `audit_verify()` verifies the global hash chain only when invoked by
  an admin/owner session. It is not callable by the runtime role, and the audit log is global rather than a
  tenant-owned RLS table (`app/audit.py:55-58`; `app/models/audit_log.py:1-11`;
  `migrations/versions/0003_audit_log.py:160-205`).
- **ASSEMBLER-DERIVED:** section counts, deterministic ordering, source-set digests, schema-validation
  results, content hashes, and completeness codes are computed by Slice 49. They may be labelled
  `system_assembled_evidence_pack`; they must never be labelled connector-verified, DB-proven, signed, or a
  release verdict merely because the assembler computed them (inference from the source-tier boundaries
  above and the no-free-evidence rule at spec lines 2849 and 2914).

The pack may prove that a specific immutable snapshot contains specific source references, digests, truth-tier
labels, and an audit checkpoint. It **does not prove** that the evidence universe is complete, that a clean or
empty source means nothing was missed, that the release is ready, that a human approved it, or that the pack is
cryptographically signed. Missing, unsupported, unbound, stale, inconsistent, unsigned, or not-yet-built
sections remain explicit blockers; they are never filled with plausible placeholders
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1474-1490,1538-1544,2904-2914`).

### 0.1 Verified repository baseline for this plan

The following was re-verified from the repository before drafting, not inherited from a prior handoff:

- `git rev-parse HEAD` and `git rev-parse origin/main` both returned
  `9373830235e1a834b172e62442e73c8e2d64d4a7`; the checked-out branch is `main`.
- `git status --porcelain` was empty. Local and remote branch-ref inspection showed only `main` and
  `origin/main`; no feature branch exists.
- `uv run alembic heads` returned `0047 (head)`. Migration `0047` revises `0046`
  (`migrations/versions/0047_reviewer_quality_assurance.py:1-22`).
- A5 is `slice47.v1` (`app/release/production_autonomy.py:57-64`); readiness is `slice20.v1`
  (`app/intake/readiness.py:43-46`).
- No `.planning/SLICE-49-PLAN.md`, evidence-pack model/repository/service, or Slice-49 migration existed
  before this file was added (verified with `rg --files` and repository-symbol search). The roadmap alone
  marks Slice 49 “NEXT PLANNED (NOT STARTED)”
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:469-479`).

These are planning-time observations, not permanent product invariants. Implementation must re-run the same
checks before branching.

## 1. Scope and non-goals

### 1.1 In scope after plan approval and all OD rulings

1. A pure, versioned evidence-pack contract that:
   - uses the ruled canonical schema;
   - preserves source truth tiers rather than flattening them;
   - produces deterministic, bounded, safe-metadata projections and SHA-256 digests;
   - validates Draft 2020-12 plus code-owned semantic requirements; and
   - returns explicit section-level completeness/failure codes.
   The shipped asset declares Draft 2020-12 and `$id = uaid.evidence_pack.v1.2`
   (`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:1-17`).
2. Release-scoped assembly for one exact, currently `frozen` `release_candidates` row, using its
   freeze-locked known-issue bindings and a deterministic source snapshot. Candidate identity and issue
   membership are DB-provable; issue-set completeness is not
   (`app/models/release_candidate.py:29-65`; `app/models/release_candidate_issue_binding.py:1-10`).
3. Safe projections from the user-named source primitives:
   - Slice 2 audit-chain checkpoint;
   - Slice 11 intake artifacts and Sanad provenance;
   - Slices 22–25 risk acceptances, findings, issues, candidate, and issue bindings;
   - Slice 42 review reports;
   - Slice 43 test-oracle runs/results;
   - Slice 44 security runs/category coverage and trusted finding attachments;
   - Slice 45 shortcut runs/category coverage and trusted finding attachments;
   - Slice 46 acceptance-authorship verification; and
   - Slice 48 reviewer-quality records.
   The roadmap’s section-to-primitive table names these sources and explicitly marks verdict/signatures as
   future (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:755-781`).
4. A pack auditor that verifies, without executing new project evidence:
   - the selected JSON Schema itself is valid;
   - the assembled export validates with format checking;
   - the ruled semantic section contract is satisfied;
   - every source reference resolves to the same tenant/project and matches its stored safe projection digest;
   - traceability edges resolve;
   - latest/source-selection rules were applied consistently;
   - the global audit checkpoint was produced by the real `audit_verify()` path; and
   - the stored canonical bytes still hash to the stored content digest.
   This is the bounded meaning of “evidence pack auditor” in Slice 49; it is not a semantic re-review of the
   source evidence (spec lines 2849, 2906-2914).
5. Additive-only storage after `0047` for generation attempts, immutable core assemblies, source references,
   section audit results, and a restricted audit-chain checkpoint, subject to the OD rulings.
6. Internal machine-readable JSON and deterministic Markdown rendering/refusal behavior. Any canonical export
   that lacks the ruled required evidence must fail closed; no HTTP endpoint is presumed
   (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1492-1502,2904-2912`).
7. Audit events containing IDs, schema/contract versions, digests, booleans, status/failure codes, and counts
   only. No tenant prose, source locator, URL, secret, prompt, response, finding detail, approval rationale, or
   artifact body may enter the new tables’ safe projections or audit payloads
   (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:844-854`).

### 1.2 Non-goals

- No release-manager verdict or completion of A5 gate #7; that is Slice 50
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:483-493`).
- No cryptographic signer, signing key, signed manifest, OSCAL mapping, public/offline auditor package,
  temporary auditor account, scoped auditor link, or read-only auditor access workflow. The spec requires those
  for full export assurance, but the roadmap assigns assurance hardening to Slice 60
  (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1496-1502,1538-1544,2906-2911`;
  `.planning/GO-LIVE-END-TO-END-ROADMAP.md:750-751`).
- No fake `verdict`, signer, signer identity, signing-key ID, human signature, release-authority signature, or
  “verified human approval.” The canonical schema’s required keys do not manufacture missing source records
  (`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:5-14,53-63`).
- No new test, scan, detector, review, acceptance, QA, PM, SCM, CI, deployment, monitoring, or LLM execution.
  Slice 49 consumes recorded evidence; it does not create the underlying evidence (inference from roadmap §9’s
  “assembler” boundary at `.planning/GO-LIVE-END-TO-END-ROADMAP.md:765-781`).
- No raw artifact archive, SARIF, scanner JSON, CI logs, source corpus, review prose, LLM packet/response,
  requirement body, risk-acceptance rationale, issue/finding detail, or source locator embedded in the pack.
- No mutation or relabelling of existing evidence, lifecycle rows, provenance tiers, candidate bindings, or
  historical data.
- No A5 gate ladder, reason, context, pass path, or ruleset change. No readiness change. No go-live path.
- No weakening/replacement of `release_findings_guard()`, any Slice-22/24/25/44/45/46/47/48 guard, RLS policy,
  append-only trigger, generated column, grant, or composite binding. The current findings guard remains pinned
  to MD5 `808036faf2660d6810aeca4342e6f1ac`
  (`tests/test_reviewer_quality.py:372-373`; `.planning/SLICE-48-PLAN.md:461-470`).
- No branch, implementation, migration, test, commit, push, or PR until this plan is approved and every OD is
  ruled.

## 2. Current repository truth and the gaps Slice 49 must not conceal

### 2.1 The repository ships two evidence-pack shapes

The long §15.4 example requires `claims`, `requirements`, `tasks`, `pull_requests`, `tests`, `reviews`,
`approvals`, `deployments`, `risks`, and `signatures`
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1492-1535`). The later §27.11 schema—and
the checked-in asset—requires only `schema_version`, project/release/time, `scope`, `traceability`, `verdict`,
and `signatures`, with optional test/review/quality/risk/provenance/audit fields
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:2769-2794`;
`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:1-65`). Roadmap decision D-5 defaults
to §27.11 as canonical and §15.4 fields as optional expansions, but explicitly leaves coordinator confirmation
open (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:830-837`). OD-49-1 binds the choice.

The asset is deliberately shallow: it does not set `additionalProperties: false`, does not constrain UUID
formats, and does not define item shapes or non-empty arrays. JSON-Schema validity alone therefore cannot prove
source resolution, content safety, evidence completeness, or readiness. Slice 49 needs a separate versioned
semantic contract and must name which conclusions come from JSON Schema versus the code-owned auditor
(`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:15-65`; inference from those absent
constraints).

`jsonschema` appears only transitively in `uv.lock`, not as a declared project dependency
(`pyproject.toml:7-24`; `uv.lock:677-700`). If OD-49-1 selects the canonical JSON Schema path, implementation
must declare the validator directly and use `Draft202012Validator.check_schema` plus a `FormatChecker`; it must
not silently depend on another package keeping the transitive dependency installed.

### 2.2 Verdict and signing sources do not exist yet

The canonical asset requires both `verdict` and `signatures`, and limits verdict values to four strings
(`docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json:5-14,53-63`). The roadmap identifies
the real release verdict as future Slice 50 and signatures as future Slices 53/60
(`.planning/GO-LIVE-END-TO-END-ROADMAP.md:775-779`). Existing risk-acceptance `request_authenticated`
provenance is expressly key custody rather than a human signature
(`app/models/risk_acceptance_record.py:1-10`).

Therefore a Slice-49 value such as `passed`, `failed`, or `blocked` cannot silently pose as a release verdict,
and an app-computed SHA-256 cannot be placed in `signatures` or described as signed. OD-49-2 must bind a staged
assembly/finalization rule that breaks the schema/verdict circularity without fabrication.

### 2.3 A frozen candidate is a real release referent, but not a repo/commit or feature-scope binding

`release_candidates` stores tenant/project, `release_ref`, title, status, and freeze timestamps; it has no repo,
commit, included requirement, excluded requirement, or artifact membership column
(`app/models/release_candidate.py:29-65`). Its issue bindings are immutable after freeze and declare issues
known for the release, explicitly not issue completeness
(`app/models/release_candidate_issue_binding.py:1-10,30-72`). Slice-47 risk-acceptance rows now FK-pin new
`release_id` values to a same-tenant/project candidate `release_ref`, while legacy rows remain a separate
honesty boundary (`app/models/risk_acceptance_record.py:35-79`).

Slices 43–45 carry exact repo/commit evidence on their own runs, but that does not retrospectively add a
candidate→commit FK (`app/models/test_oracle_run.py:122-168`; `app/models/shortcut_detector_run.py:33-80`). A
pack can truthfully be **candidate-scoped** and can separately state the exact commit bindings of included
evidence; without new binding evidence it must not claim that the candidate itself is DB-bound to that commit.
OD-49-3 rules the v1 scope statement and snapshot binding.

### 2.4 The source stores have heterogeneous, non-flattenable truth

| Pack projection | What the current repository can prove | What it cannot prove |
|---|---|---|
| `scope` / bound issues | Exact frozen candidate identity and immutable known-issue membership (`app/models/release_candidate.py:29-65`; `app/models/release_candidate_issue_binding.py:1-10`) | Complete issue universe, included/excluded feature truth, candidate→commit identity |
| `traceability` / `provenance_chains` | Intake parent links are same-project/tenant FKs; every canonical artifact has at least one append-only Sanad source, and document-backed sources are same-project/tenant pinned (`app/models/intake_artifact.py:47-90`; `app/models/intake_provenance.py:1-8,28-67`) | External truth of caller-supplied `origin`/`locator`; full requirement→task→PR→test coverage |
| `risk_acceptances` | Same-project release FK for new rows; lifecycle/status; recorded provenance tier (`app/models/risk_acceptance_record.py:35-112`) | Human signature; truth of rationale, owner, approver labels, or legacy release identity |
| `release_issues` / `release_findings` | Exact trusted finding→issue bridge where present; critical/hard-refusal lifecycle guards; recorded status (`app/models/release_issue.py:1-12,33-100`; `app/models/release_finding.py:32-123`) | All issues/findings are known; prose truth; a clean project |
| `review_reports` | Exact contract/reviewer/layer registration, append-only reported verdict, DB-generated `can_merge` (`app/models/review_report.py:1-13,43-122`) | Semantic review quality or correctness |
| `test_results` | Exact definition/repo/commit binding, execution/observation tiers, DB-generated aggregate/verdict (`app/models/test_oracle_run.py:44-168`) | Universal correctness or coverage outside declared oracle scope |
| security / shortcut evidence | Versioned coverage and execution records; DB-bound trusted finding attachments where present (`app/models/security_scan_run.py:24-110`; `app/models/shortcut_detector_run.py:24-80`; `app/models/release_finding.py:32-123`) | Absence of undiscovered vulnerabilities/shortcuts; universal detector recall |
| acceptance verification | Versioned structural authorship verification and DB-bound independent-agent evidence where eligible (`app/models/acceptance_verification.py:13-111`) | Semantic acceptance quality or verified human ownership |
| reviewer QA | Challenge-only system execution, generated rates/status, exact reviewer lineage (`app/models/reviewer_quality.py:171-308`) | General competence or real-world/live-review miss rate |
| `audit_log_hash` | An admin can verify the global chain and identify the first bad sequence (`app/audit.py:55-58`; `migrations/versions/0003_audit_log.py:160-191`) | A tenant-runtime proof, a signature, or proof of semantic truth in audited payloads |

The assembler must include failures/refusals and untrusted tiers when they are in the ruled snapshot. Filtering
them out would make the pack misleading.

### 2.5 The promised Slice-48 safe projection is not implemented

The approved Slice-48 plan required an “evidence-pack-safe record projection”
(`.planning/SLICE-48-PLAN.md:477-499`). The merged `ReviewerQualityRepository` currently exposes
`execute_suite()` and `is_currently_eligible()` plus private execution helpers; it has no safe-projection or
history method (`app/repositories/reviewer_quality.py:66-70,209-255,256-442`). This is a repository-observed
implementation gap, not evidence that Slice 48 failed: the immutable quality record and its safe scalar fields
exist (`app/models/reviewer_quality.py:171-308`). Slice 49 must implement the promised projection itself or add
a narrowly scoped repository read; it must not claim the projection already exists.

### 2.6 The audit verifier is privileged and global

`audit_verify()` scans the entire global chain, while `uaid_app` receives execute permission only on
`audit_append`; PUBLIC is revoked from both functions (`migrations/versions/0003_audit_log.py:120-205`). Calling
`verify_chain()` inside an ordinary tenant repository would fail or tempt a privilege bypass. An app-supplied
“audit verified” boolean would be caller-controlled and unacceptable. OD-49-4 must bind a privileged,
non-forgeable checkpoint flow and the exact claim it supports.

## 3. Required design semantics (contingent on §4 rulings)

### 3.1 Deterministic candidate-scoped snapshot

The recommended v1 assembly input is one exact `release_candidate_id`; generation must:

1. load it under tenant scope and require current `status == 'frozen'`;
2. snapshot its immutable issue-binding set;
3. derive a conservative canonical-artifact scope from all structurally valid project artifacts existing at
   the ruled cutoff, never from a caller-supplied list labelled complete;
4. collect the exact repo/commit identities carried by trusted Slice-43/44/45 evidence, refusing an asserted
   single code binding when trusted sources disagree or none exists;
5. select source records under the ruled source-selection contract, preserving failure/untrusted/stale states;
6. create safe projections, canonical source-reference ordering, per-item digests, per-section digests, and a
   whole source-set digest; and
7. persist an immutable attempt even when assembly is incomplete, with bounded missing/inconsistent section
   codes only.

Candidate scope, canonical artifact scope, evidence repo/commit scope, and audit checkpoint are separate fields.
No one field silently stands in for another.

### 3.2 Source selection and completeness inventory

The auditor needs a code-owned matrix, versioned as proposed `slice49.evidence_pack.v1`, that declares for each
section:

- source table/type and expected truth tiers;
- exact same-tenant/project resolution rule;
- release/candidate/commit binding rule, where one exists;
- latest-wins or all-history selection rule inherited from the producer;
- whether the section is structurally required, may be legitimately empty, is unsupported, or is deferred;
- deterministic ordering key;
- safe projected keys and prohibited keys;
- item/section cap;
- digest algorithm and canonicalization; and
- absence, stale, untrusted, inconsistent, unsupported, and deferred reason codes.

An empty array is never silently interpreted as “clean.” A section may be empty only alongside an explicit
inventory result such as `present_zero_rows`, `missing_required_source`, `unsupported_this_slice`, or
`deferred_to_slice_50`; whether that state permits core assembly or canonical export is governed by OD-49-5.
This is required because issue bindings explicitly do not prove completeness and §28.1 requires traceable
evidence rather than trusted summaries (`app/repositories/release_candidates.py:1-9`;
`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:2849,2910-2914`).

Latest-wins sections must use their producer’s exact binding and ordering, including `(created_at DESC, id
DESC)` where ruled by prior slices. Later failed/refused evidence is included and supersedes an older pass for
the same exact binding. Historical/lifecycle sections such as findings, issues, risk acceptances, candidate
bindings, and Sanad provenance use the ruled complete bound set, not latest-only filtering.

### 3.3 Safe projection and traceability rules

Safe projections must contain only IDs, code-owned refs/digests, schema/contract versions, bounded categories,
truth-tier codes, status/verdict codes, booleans, numeric counts/rates, timestamps, exact commit SHA where
already recorded, and hashes. Examples:

- Intake: artifact ID/kind/ref digest/parent ID/content digest plus provenance row ID/document ID and
  origin/locator digests; never title/body/data/origin/locator.
- Review report: report/contract/reviewer IDs, layer, reported verdict, `can_merge`, source-provenance code,
  timestamp; never summary, failed criteria, suspected shortcuts, required changes, or source prose.
- Risk acceptance: record ID, release ref digest, subject type/subject ID, severity, status, expiry,
  blocking-category code, inclusion boolean, and approver-provenance tier; never rationale, business impact,
  controls, mitigation plan, owner/approver labels, or evidence-link contents.
- Finding/issue: IDs, type/category/severity/blocking/status/provenance and bridge/attachment IDs; never
  summary/detail/resolution prose/evidence snippets.
- Verification/QA runs: IDs, exact binding hashes, schema/contract versions, execution/observation tiers,
  statuses, generated verdicts, counts/rates, and timestamps; never packets, prompts, responses, fixture bodies,
  labels, scanner JSON, or source corpus.

Traceability edges are references among these projections. Every edge must resolve inside the pack or to a
ruled redacted/source reference with an exact digest; unresolved edges fail the affected section. A digest is a
tamper-detection aid, not a disclosure of the source and not proof the source is true
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1538-1544,2910-2914`).

### 3.4 Audit checkpoint semantics

Under recommended OD-49-4 Option A, an admin-only auditor transaction must:

1. acquire the existing audit-chain advisory lock used by `audit_append`;
2. invoke the real `audit_verify()`;
3. if `ok`, read the exact verified-through tip `(seq, entry_hash)` in the same transaction;
4. append a restricted `audit_chain_verifications` checkpoint row with `ok`, `first_bad_seq`, verified-through
   sequence/hash, verifier contract version, and timestamp; and
5. release the lock on transaction completion.

The tenant runtime may reference a successful checkpoint but may not create, update, delete, or forge one.
The export must say `audit_chain_verified_through_seq/hash`, never “the audit log is currently valid forever.”
Audit entries appended after the checkpoint are outside its claim. The checkpoint is global because the
underlying chain is global; its hash/sequence reveal no audit payload
(`app/models/audit_log.py:1-11,23-44`; `migrations/versions/0003_audit_log.py:120-205`).

### 3.5 Two validation layers

The auditor must report both layers separately:

1. **JSON Schema validation:** `uaid.evidence_pack.v1.2` with Draft 2020-12 and format checking. It proves only
   conformance to the shipped schema.
2. **Slice-49 semantic audit:** versioned required sections, source-resolution, projection allowlist,
   provenance preservation, exact candidate/source bindings, section completeness, traceability resolution,
   content bounds, source-set digests, and audit-checkpoint rules. It proves only conformance to the ruled
   Slice-49 contract.

Failure in either layer produces a failed/incomplete generation or export result. No caller may supply
`schema_valid`, `complete`, `verified`, `passed`, `trusted`, `signed`, `gate`, or `ready` fields. Export must
re-run both layers over stored canonical bytes and current source resolution rather than trusting a persisted
success boolean.

### 3.6 Integrity manifest versus signature

Slice 49 may compute SHA-256 digests over exact canonical core JSON, source projections, and rendered export
bytes. It may emit an **unsigned integrity manifest** containing file name, content hash, byte count, generated
time, schema/contract version, source-set digest, and audit checkpoint reference. It must set an explicit
`signature_status = unsigned_signer_tier_not_implemented` (subject to OD-49-2/8) and keep schema
`signatures = []` only where the ruled staged contract permits. A content hash is not a signature; no
`signer_id`, `signing_key_id`, or signature bytes may be synthesized
(`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:1496-1502,1538-1544,2892-2912`).

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-49-1 — Which evidence-pack schema is canonical, and how are §15.4 fields handled?

- **Option A (recommended; roadmap D-5 default):** the checked-in §27.11 asset
  `uaid.evidence_pack.v1.2` is canonical. Slice 49 adds a code-owned
  `slice49.evidence_pack.v1` semantic contract and allowlisted optional expanded sections for §15.4/§28.1;
  it does not fork or rewrite the canonical schema. Use a directly declared Draft-2020-12 validator plus
  format checker. Unknown caller fields fail the semantic contract even though the shallow schema permits
  additional properties.
- **Option B:** introduce a new stricter schema asset/version now that merges §15.4 and §27.11. This is more
  explicit but creates a third spec shape and expands the slice into schema governance/migration.
- **Option C:** validate only the shallow asset and accept arbitrary extensions. **Rejected in principle:** it
  cannot enforce safe projections, item shapes, traceability, or completeness.

Coordinator must name the schema ID, semantic-contract version, expansion allowlist, and whether changing the
checked-in asset is allowed.

### OD-49-2 — How does v1 handle the required `verdict` and `signatures` fields before Slices 50/60?

- **Option A (recommended; strict staged finalization):** Slice 49 persists an immutable **core assembly** and
  its audit result without inventing a release verdict or signature. A canonical `evidence_pack.json` export
  is refused while the release-verdict attestation is absent. Slice 50 later appends a real verdict attestation;
  the canonical payload may then carry that verdict and `signatures: []` with explicit unsigned status, but
  full signed assurance remains incomplete until Slice 60 appends a real signing attestation. Core assembly,
  verdict, and signature are separate append-only records; none mutates the prior layer. Slice 50 may consume
  the audited core assembly without requiring a circular pre-existing verdict.
- **Option B:** emit `verdict: blocked` as a Slice-49 system-derived placeholder and `signatures: []` now, with
  explicit provenance fields. This is mechanically schema-valid but risks confusing pack-audit status with the
  future release-manager verdict.
- **Option C:** accept caller-supplied verdict/signature strings. **Rejected in principle:** no verified source
  exists, and it would fabricate the two most consequential fields.

Coordinator must rule whether an unsigned post-Slice-50 canonical JSON is exportable-but-incomplete or fully
refused until Slice 60, and must reserve the exact future attestation interfaces without implementing Slice 50
or 60.

### OD-49-3 — What exactly binds a pack to a release and code snapshot?

- **Option A (recommended; conservative and no new evidence execution):** require one exact current frozen
  candidate; snapshot its candidate/known-issue membership; conservatively include all structurally valid
  canonical project artifacts existing at the ruled candidate cutoff; derive a separately labelled
  repo/commit evidence binding only when trusted Slice-43/44/45 source records agree. Persist candidate scope,
  artifact-scope digest, issue-binding digest, and evidence repo/commit binding separately. Never claim a
  candidate→commit FK or complete feature scope.
- **Option B:** add a new connector-verified candidate-scope sidecar that binds included/excluded requirements,
  declared repo, and commit before pack generation. This gives a stronger release scope but performs new scope
  evidence work and requires product semantics not present in Slice 25.
- **Option C:** treat project ID plus `release_ref` as sufficient release/code scope. **Rejected in principle:**
  the current candidate has no repo/commit/artifact membership.

Coordinator must rule the cutoff (`frozen_at` recommended for canonical artifacts; generation time for later
verification evidence), disagreement behavior, and whether no trusted exact-commit evidence makes the assembly
incomplete.

### OD-49-4 — Who may verify and checkpoint the global audit chain?

- **Option A (recommended):** restricted admin-only `audit_chain_verifications` checkpoint rows created only
  by a dedicated admin auditor transaction that locks, calls the real `audit_verify()`, and captures the exact
  verified-through tip. `uaid_app` has reference/read access only through a safe path and cannot forge a row.
- **Option B:** omit the audit checkpoint and mark every core assembly incomplete until an operator supplies
  one outside the system. Safer than forgery but does not implement the Slice-49 auditor requirement.
- **Option C:** grant `uaid_app` `audit_verify()` or trust caller-provided `ok/hash`. **Rejected in principle:**
  it widens global audit privilege or creates fake verification.

Coordinator must rule checkpoint table ownership, exact privileges, advisory-lock use, and whether a failed
checkpoint row is retained for operations without exposing tenant payloads.

### OD-49-5 — Which sections are v1-required, and what source-selection/completeness rule applies?

- **Option A (recommended; conservative inventory):** every canonical §27.11 section is structurally present;
  the semantic contract additionally requires explicit source-inventory results for scope, traceability,
  candidate issues, risk acceptances, review reports, test oracles, security, shortcuts, acceptance
  verification, reviewer QA, Sanad, and audit checkpoint. Legitimately empty collections remain empty only
  with code-owned zero/absence reasons. Latest-wins sources include later failures/refusals; lifecycle sources
  include the exact bound set. Missing required sources make the assembly incomplete. Verdict/signature follow
  OD-49-2.
- **Option B:** require only the eight top-level keys from the shallow schema and treat all optional arrays as
  absent. This is mechanically valid but below §15/§28’s evidence and traceability bar.
- **Option C:** require every field from the longer §15.4 example as complete now. This fails honestly on
  several unbound/deferred sources and may prevent even a useful core assembly.

Coordinator must rule per-section required/optional/deferred status, legitimate-empty semantics, caps, and
the exact latest/all-history rules. No “clean” inference may come from an empty store.

### OD-49-6 — What is the immutable lifecycle and staleness model?

- **Option A (recommended; append-only layers):** generation attempts, core assemblies, source refs, section
  audit results, future verdict attestations, and future signature attestations are all append-only. A failed
  attempt stays visible. No pack is updated; changed source evidence, contract/schema, candidate state, or
  audit checkpoint requires a new assembly. Read selection is newest `(created_at DESC, id DESC)` for the exact
  candidate+scope+contract binding, but older assemblies remain historical. No wall-clock TTL is invented;
  source-specific freshness (for example Slice-48 calibration) is snapshotted and preserved.
- **Option B:** allow a one-way mutable draft→verdict-attached→signed pack guarded by triggers, matching the
  roadmap’s phrase “immutable once a verdict is attached.” Fewer rows, but mutation complicates reproducible
  hashes and audit history.

Coordinator must rule whether generation on a candidate that later becomes superseded/canceled remains
historically exportable and whether new generation requires current `frozen` status (recommended: historical
record remains; new generation requires current frozen).

### OD-49-7 — What safe projection schema, caps, and storage representation are authoritative?

- **Option A (recommended):** refs+digests+bounded scalar metadata only; no tenant/source prose. Proposed
  versions: `slice49.evidence_pack.v1`, `slice49.evidence_projection.v1`, and
  `slice49.evidence_audit.v1`. Proposed caps: canonical core ≤8 MiB; any rendered JSON ≤16 MiB; Markdown ≤4
  MiB; ≤10,000 items per named section; ≤50,000 total source refs; ≤50,000 traceability edges; keys/codes ≤128;
  bounded labels ≤255; evidence refs/digests ≤500; all required strings non-blank. Canonical JSON bytes use
  UTF-8, sorted keys, no insignificant whitespace; SHA-256 covers exact bytes. Raw bodies/prose/URLs/locators,
  prompts/responses/snippets/logs/secrets and arbitrary JSON never persist or enter audit.
- **Option B:** inline source documents/reports with redaction. Richer standalone export, but redaction policy,
  access control, and disclosure verification belong to Slice 60 and increase leakage risk.
- **Option C:** references only with no safe snapshots/digests. Minimal storage, but later lifecycle changes
  would make the historical pack non-reproducible.

Coordinator must rule the exact caps, canonicalization algorithm, and whether the safe snapshot is JSONB plus
exact canonical text or normalized child rows plus generated export. The implementation must not claim DB proof
for any property only recomputed by the app auditor.

### OD-49-8 — Which export surfaces ship in Slice 49?

- **Option A (recommended):** internal service/repository methods only: audited core preview JSON, canonical
  JSON only when OD-49-2 permits, deterministic safe Markdown, and unsigned hash manifest. No HTTP route, PDF,
  archive, scoped link, account, OSCAL, network publishing, or signer. Every export re-audits stored bytes and
  logs safe metadata.
- **Option B:** add an authenticated HTTP download endpoint now. This expands request authorization,
  disclosure policy, streaming, content disposition, and auditor access beyond the current slice.
- **Option C:** JSON only, no human-readable output. Smaller, but fails the §15.4 machine+auditor-readable
  minimum.

Coordinator must rule file names, Markdown inclusion policy, whether incomplete preview artifacts may leave
the service boundary, and the exact refusal codes for missing verdict/signature/required section.

## 5. Proposed pure modules (contingent on §4 rulings)

### 5.1 `app/release/evidence_pack.py`

Pure, Docker-free responsibilities:

- constants for schema/projection/auditor versions and exact SHA-256 contract hashes;
- typed `EvidenceSourceRef`, `SectionInventory`, `CoreAssembly`, `PackAuditResult`,
  `AuditCheckpointRef`, `UnsignedManifest`, and export/refusal objects;
- allowlisted source kinds, provenance tiers, section names, status/failure codes, projected keys, and caps;
- deterministic ordering and canonical JSON byte serialization;
- safe projection builders that reject unknown or prohibited fields rather than dropping them silently;
- source/section/whole-pack digest derivation;
- candidate/artifact/issue/evidence-binding digest derivation;
- schema loading/checking and export validation with `Draft202012Validator` + `FormatChecker`;
- semantic completeness and traceability resolution;
- no-verdict/no-signature staged-finalization logic per OD-49-2;
- deterministic Markdown and unsigned-manifest rendering per OD-49-8; and
- no DB, network, LLM, connector, filesystem write, release-verdict, signing, or gate-evaluation side effects.

### 5.2 Schema asset usage and dependency declaration

Use the checked-in asset at its fixed repository path; do not fetch a schema over the network. If OD-49-1
Option A is ruled, add `jsonschema` as a direct project dependency and update `uv.lock`. The module must call
`check_schema` at initialization/test time and a format checker at export time; a syntactically valid but
malformed `generated_at` must fail.

### 5.3 `app/release/evidence_export.py`

Pure/rendering boundary only:

- canonical byte/file-name selection;
- deterministic Markdown from safe projections;
- unsigned manifest with exact byte hashes;
- explicit assurance limitations;
- refusal when the ruled canonical export prerequisites are missing; and
- no endpoint, signer, archive, account, or external storage.

## 6. Storage and expected migration `0048` (inference; additive-only)

`0048` is an inference from current head `0047`, not an existing migration. Exact names and columns remain
contingent on the OD rulings. The recommended shape is:

### 6.1 Restricted global `audit_chain_verifications`

Not tenant-owned because the underlying chain is global. Proposed fields:

- UUID `id`;
- verifier contract version/hash;
- `verification_ok`, nullable `first_bad_seq`;
- nullable `verified_through_seq`, `verified_through_entry_hash`;
- `created_at` from DB clock.

Only an admin/owner path may insert/select full rows; `uaid_app` gets no direct insert/update/delete/truncate and
cannot call `audit_verify()`. A narrow safe reference lookup may expose successful checkpoint ID, timestamp,
sequence, and hash. Rows are append-only. Failed checks may be retained as operator evidence but never satisfy
a pack.

### 6.2 Tenant-owned `evidence_pack_generation_runs`

RLS `ENABLE` + `FORCE`, append-only, composite-pinned to project/tenant and exact release candidate. Proposed
safe fields:

- UUID/tenant/project/candidate IDs and candidate `release_ref` digest;
- schema/projection/auditor versions and contract hashes;
- requested cutoff and generated time;
- execution status `succeeded|failed|refused`;
- bounded failure/missing/inconsistent section codes and counts;
- source/section/edge/byte counts;
- execution provenance fixed to `system_assembled_evidence_pack`; and
- created timestamp.

No payload, prose, raw source, caller-supplied success/completeness, or release verdict belongs here.

### 6.3 Tenant-owned `evidence_packs` (immutable core assemblies)

RLS `ENABLE` + `FORCE`, append-only, one-to-one with a successful generation run, composite-pinned to the same
candidate/project/tenant and a successful audit checkpoint. Proposed fields:

- core/candidate/artifact/issue/source-set/traceability digests;
- separately labelled repo-binding hash and commit SHA when derivable;
- schema/projection/auditor versions and contract hashes;
- exact canonical safe core JSON bytes or ruled normalized representation;
- DB-derived hash over exact stored canonical bytes where feasible;
- signature status fixed to unsigned/deferred and release-verdict status fixed to absent/deferred in Slice 49;
- generated time and immutable source cutoff.

No mutable `status`, caller-provided `schema_valid`, verdict, signature, signer, readiness, gate, or trusted flag.
Future Slice-50/60 attestations reference this immutable core rather than update it under recommended OD-49-6.

### 6.4 Tenant-owned source references and section audit results

`evidence_pack_source_refs` and `evidence_pack_section_results` are RLS `ENABLE` + `FORCE`, append-only, and
composite-FK-bound to pack/project/tenant. Source refs carry only allowlisted source kind, source row ID,
source truth tier, safe-projection digest, source created timestamp, and deterministic ordinal. A DB guard must
resolve the allowlisted source kind to the real source table, prove same tenant/project, and reject unknown,
cross-tenant, cross-project, duplicate, or mismatched kinds. Where an existing composite FK target exists, use
it directly; the guard covers the heterogeneous remainder without altering source tables.

Section results carry section code, presence/completeness code, item count, digest, and bounded failure code.
A deferred end-of-transaction backstop must ensure declared counts/ordinals/source-set digest match persisted
children before a core assembly commits. It must not claim semantic completeness beyond the ruled matrix.

### 6.5 RLS, grants, guards, downgrade, and preservation

- Every tenant-owned table: `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, exact tenant policy,
  runtime non-owner, explicit least-privilege SELECT/INSERT only, and no UPDATE/DELETE/TRUNCATE.
- Global audit-checkpoint table: no RLS claim, no runtime mutation privilege, explicit admin ownership/grants.
- Composite FKs pin pack/run/children to candidate/project/tenant; `RESTRICT` deletion behavior.
- DB checks own enums, hash formats, non-blank/bounded strings, counts, exact one-to-one relationships, and
  forbidden lifecycle shapes.
- No migration data backfill and no relabelling of historical source rows.
- `release_findings_guard()` is not replaced or touched. Its catalog MD5 remains
  `808036faf2660d6810aeca4342e6f1ac` before/after upgrade, downgrade, and re-upgrade.
- Catalog snapshots prove every pre-0048 guard/policy/grant/generated expression unchanged.
- Recommended downgrade fails closed while any Slice-49 row exists; with no rows, it drops only Slice-49
  objects and restores head `0047` exactly.

## 7. Repository/orchestrator behavior

### 7.1 `app/repositories/evidence_packs.py`

Tenant-scoped methods only, except the explicitly separate admin checkpoint writer:

1. `record_audit_checkpoint(admin_session)` performs OD-49-4’s locked real-chain verification.
2. `assemble_core(project_id, candidate_id, audit_checkpoint_id, actor)`:
   - rejects non-frozen, missing, cross-tenant, or cross-project candidates;
   - loads deterministic source sets without network/LLM execution;
   - preserves producer truth tiers and latest/history semantics;
   - builds safe projections and explicit section inventory;
   - re-resolves every traceability/source link;
   - applies caps before expensive serialization;
   - validates the core/preview contract;
   - persists attempt, core, refs, and section results atomically; and
   - writes a safe audit event.
3. `get_history(candidate_id)` orders newest-first and returns safe metadata only.
4. `get_latest_exact_binding(...)` uses exact candidate/scope/source/contract keys and
   `(created_at DESC, id DESC)`.
5. `audit_pack(pack_id)` reloads exact stored bytes, recomputes digests, re-resolves refs, validates schema and
   semantic contract, and returns a newly computed result; it does not trust stored booleans.
6. `export_json(pack_id)` and `export_markdown(pack_id)` enforce OD-49-2/8 and audit export attempts.

The generation transaction must fail atomically: no successful core row may commit without all required
children and section results. A failed attempt may be recorded in a separate transaction with safe failure
metadata, never a partial successful pack.

### 7.2 Source adapters are reads, not forks

Slice 49 may add narrowly named `evidence_pack_projection(...)` read methods to existing repositories or keep
all source reads in the new repository, but it must reuse the canonical stores and their lifecycle rules. It
must not duplicate findings, issues, test runs, reports, QA records, or acceptance evidence into new semantic
stores. The new pack stores only immutable safe snapshots/references/digests needed for reproducibility.

The Slice-48 projection gap identified in §2.5 must be closed explicitly and tested. Similar projections must
be compared against source model fields so no prose field is accidentally introduced.

### 7.3 Export behavior

Under recommended rulings:

- core preview: internal-only, visibly labelled `not_canonical_export`, with missing/deferred sections;
- canonical JSON: exact `evidence_pack.json`, refused until real verdict attachment exists; unsigned assurance
  remains explicit until Slice 60;
- human output: deterministic `evidence_pack.md` containing only safe projections, digests, source truth tiers,
  limitations, and traceability refs;
- manifest: unsigned hashes/timestamps only, never `signature` or `signer` fields; and
- no HTTP or external file publication.

Every export re-audits first. A source digest mismatch, missing source, invalid schema, unresolved edge,
checkpoint failure, missing required section, absent real verdict, or ruled missing signature fails with a
bounded code; it never returns a best-effort artifact labelled canonical.

## 8. A5, readiness, and go-live — exact non-change

Slice 49 changes **no A5 gate**. It is trust/assembly infrastructure enabling Slice 50; it does not supply the
release verdict needed to complete gate #7. Gate #7 currently has no passed branch and remains
`insufficient_evidence` under `slice47.v1` (`app/release/production_autonomy.py:319-357`).

Required non-change:

- `app/release/production_autonomy.py` byte-stable;
- `A5_RULESET_VERSION == "slice47.v1"` before and after;
- identical A5 reports for a comprehensive fixture matrix before/after Slice 49;
- all existing gates and reasons unchanged;
- `app/intake/readiness.py` byte-stable at `slice20.v1`;
- `a5_satisfied` still false when any gate is not passed; and
- `can_go_live_autonomously` remains hard-false with the same two no-go reasons
  (`app/release/production_autonomy.py:46-69`).

No evidence-pack count/status is added to A5 context this slice. The roadmap says Slice 49 enables the future
verdict; it does not mark a gate PASS-capable (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:469-479,483-493`).

## 9. Test plan for eventual implementation

No tests are written or run during this plan-only task. After approval/rulings, implementation must begin with
failing tests and then satisfy the following.

### 9.1 Pure / Docker-free

1. Shipped schema loads; Draft-2020-12 `check_schema` passes; wrong schema ID/version fails.
2. Format checking rejects malformed `generated_at` values (not merely type-checking strings).
3. Each required top-level field missing in turn yields the exact fail-closed code; unknown/prohibited fields
   fail the semantic allowlist even though the asset permits additions.
4. D-5 ruled expanded sections validate and unruled extensions fail.
5. Deterministic canonical JSON is byte-identical across dict insertion order, locale, and repeated runs;
   digests match exact bytes and change on one-byte mutation.
6. Source ordering and source-set/section/scope/issue-binding/traceability digests are deterministic.
7. Truth-tier projection table: REPORTED, request-authenticated, connector-observed/verified, system-executed,
   DB-proven, admin-checkpoint, and assembler-derived labels survive unchanged; no automatic upgrade.
8. Prohibited prose/secret sentinel appears in every source prose field and is absent from safe projection,
   JSON, Markdown, manifest, exceptions, and audit payload builders.
9. Every source model projection allowlist has a positive and unknown-field rejection test, including the new
   ReviewerQuality projection.
10. Candidate/artifact/evidence scope distinctions: disagreement across trusted repo/commit sources refuses a
    single binding; no source yields explicit missing-binding state; no candidate→commit claim is emitted.
11. Empty sections use ruled absence/zero codes and never produce `clean`, `passed`, or `complete` by vacuity.
12. Later failed/refused exact-binding evidence supersedes older passed evidence in selection and remains in the
    pack.
13. Traceability: all edges resolve; missing/cross-project/duplicate/cyclic-invalid edges fail with bounded
    codes; source digests are not treated as semantic truth.
14. Verdict/signature matrix per OD-49-2: missing real verdict never becomes `blocked`; content hash never enters
    `signatures`; unsigned status is explicit; canonical export refusal is exact.
15. JSON Schema valid but semantic-contract incomplete payload fails the semantic audit.
16. Content/section/item/edge/string caps: exact boundary passes, boundary+1 fails before serialization.
17. Markdown is deterministic, safe, non-HTML-active, and carries the same truth tiers/limitations as JSON.
18. Unsigned manifest hashes every returned byte artifact and never contains fake signer/signature/key data.
19. A5 before==after golden matrix; ruleset, gate statuses/reasons/context, no-go reasons, and go-live output are
    identical.
20. Readiness before==after golden matrix; version and output identical.

### 9.2 DB-backed and direct-SQL adversarial tests

1. Migration catalog: expected tables/functions/triggers/policies/grants/indexes; Alembic head `0048`.
2. Tenant tables have RLS ENABLE+FORCE, correct tenant policy, runtime non-owner, least-privilege grants, and
   no UPDATE/DELETE/TRUNCATE.
3. Cross-tenant/cross-project pack, candidate, source ref, section result, or source ID is invisible/rejected.
4. Candidate must exist, match tenant/project, and be currently frozen; draft/superseded/canceled candidate
   generation fails without a successful core.
5. Composite candidate/run/pack/child FKs reject mixed tenant/project identities.
6. Direct SQL unknown source kind, mismatched source kind/row, missing source, duplicate ordinal/ref, wrong
   project, wrong truth tier, forged digest, or unresolved traceability link fails at insert/commit or causes
   the mandatory auditor/export recheck to refuse; no forged row is treated as audited.
7. Deferred completeness: missing child, wrong declared count, ordinal gap, section digest mismatch, source-set
   digest mismatch, or section inventory mismatch rolls back the successful core transaction.
8. Direct SQL attempts to set `schema_valid`, `complete`, `verified`, `passed`, `trusted`, `signed`, `ready`,
   gate fields, verdict, signer, or signature are rejected by shape/grants/guards.
9. Append-only guards reject UPDATE/DELETE/TRUNCATE on generation runs, cores, refs, section results, and audit
   checkpoints.
10. Admin audit checkpoint happy path: lock + real `audit_verify()` + exact tip persisted. Runtime cannot execute
    verifier, insert checkpoint, or read audit payloads.
11. Deliberately corrupt audit chain under test-admin setup: checkpoint `ok=false`, first bad sequence recorded,
    no pack can reference it successfully, and no “verified” claim appears.
12. Audit race test: a concurrent append cannot interleave between verify and tip capture under the shared
    advisory lock.
13. Global checkpoint reference exposes only ID/time/seq/hash/contract status, never other-tenant audit data.
14. Source lifecycle snapshot: later issue/risk status change or new evidence does not mutate old canonical
    bytes/digest; a new generation creates a new row.
15. Latest exact-binding order uses `(created_at DESC, id DESC)`; a later failed/refused run supersedes older
    success where producer semantics require.
16. Risk-acceptance legacy/null subject rows remain labelled legacy/unbound; no history is upgraded. New rows’
    same-candidate FK is respected.
17. Review-report summary/list/source, intake title/body/data/origin/locator, finding/issue prose,
    risk-acceptance prose/actor labels, raw test/scan/shortcut/QA material, and a high-entropy secret sentinel
    never appear in pack tables, rendered output, error text, logs, or audit rows.
18. Audit events contain safe IDs/digests/versions/status/counts only and are appended for attempt, core audit,
    and export/refusal.
19. Stored-byte tamper under test-admin setup is detected by digest/schema/semantic re-audit; export refuses.
20. Existing guard/policy/grant/generated-expression catalog before==after. Specifically,
    `md5(pg_get_functiondef('release_findings_guard()'::regprocedure))` is
    `808036faf2660d6810aeca4342e6f1ac` before upgrade, after upgrade, after downgrade, and after re-upgrade.
21. Existing Slice-22/24/25/44/45/46/47/48 direct-SQL adversarial tests remain green; no guard replacement.
22. Downgrade with Slice-49 rows fails closed under recommended OD-49-6; empty downgrade removes only Slice-49
    objects and returns exact head/catalog to `0047`; re-upgrade succeeds.
23. Full transaction failure injection at each persist/audit stage leaves no partial successful pack.
24. A5 repository integration before==after reports are byte/structure identical and no evidence-pack field is
    wired into gate context.

### 9.3 Verification commands (eventual implementation only)

Required before any implementation PR:

```bash
git diff --check
uv run ruff check app tests migrations
make test
RLS_DB_PASSWORD=... make test-db
ALEMBIC_DATABASE_URL=... uv run alembic downgrade 0047
ALEMBIC_DATABASE_URL=... uv run alembic upgrade 0048
ALEMBIC_DATABASE_URL=... uv run alembic downgrade 0047
ALEMBIC_DATABASE_URL=... uv run alembic upgrade 0048
ALEMBIC_DATABASE_URL=... uv run alembic current
ALEMBIC_DATABASE_URL=... uv run alembic check
```

Report exact pass/deselection counts from the actual outputs; do not predict them in the plan.

## 10. Proposed file touch map for eventual implementation only

Subject to rulings; none of these implementation files is touched by this plan-only task:

- `app/release/evidence_pack.py` — pure contract, projections, canonicalization, auditor.
- `app/release/evidence_export.py` — deterministic JSON/Markdown/unsigned-manifest rendering and refusal.
- `app/models/evidence_pack.py` — run/core/source-ref/section-result ORM models.
- `app/models/audit_chain_verification.py` — restricted global checkpoint model, if OD-49-4 Option A.
- `app/repositories/evidence_packs.py` — tenant assembly/audit/export reads plus separated admin checkpoint path.
- `app/models/__init__.py` — model registration only.
- `migrations/versions/0048_evidence_packs.py` — additive storage/guards/RLS/grants; no existing guard rewrite.
- `pyproject.toml`, `uv.lock` — direct JSON-Schema dependency if OD-49-1 Option A.
- `tests/test_evidence_packs.py` — pure and DB-backed tests above.
- `.planning/SLICE-49-PLAN.md` — approved/ruling-bound plan on the future branch.

Explicitly byte-stable unless a later approved ruling changes scope:

- `app/release/production_autonomy.py`;
- `app/intake/readiness.py`;
- all existing migrations and guards, especially `release_findings_guard()`;
- every source model/store lifecycle; and
- canonical schema asset under OD-49-1 Option A.

No API/router file is added under recommended OD-49-8 Option A.

## 11. Must NOT claim

- Must NOT claim an assembled core, schema-valid JSON, complete section inventory, or successful export means
  “Done,” release-ready, A5-satisfied, approved, deployable, safe, compliant, or go-live-authorized.
- Must NOT claim a pack proves the evidence universe is complete. It proves only the ruled snapshot and links.
- Must NOT interpret an empty issue/finding/risk/test/review/QA/security/shortcut/acceptance section as clean,
  absent, passed, or complete without the ruled evidence and explicit inventory status.
- Must NOT flatten REPORTED, request-authenticated, connector-observed, connector-verified, system-executed,
  DB-proven, admin-verified, and assembler-derived evidence into one “verified” tier.
- Must NOT call Slice-42 review content verified; only registration and generated `can_merge` are DB-proven.
- Must NOT call request-authenticated risk acceptance a human approval or signature.
- Must NOT claim candidate identity or issue membership proves candidate→commit, feature scope, or complete issue
  inventory.
- Must NOT claim project-level/reviewer-level evidence is release-specific unless an exact ruled binding proves
  it.
- Must NOT fabricate `passed`, `failed`, `blocked`, or accepted-risk release verdicts before Slice 50.
- Must NOT put a digest, content hash, actor label, key-custody record, approval row, or empty array forward as a
  cryptographic signature.
- Must NOT claim the unsigned manifest is signed, tamper-proof, externally verifiable, or non-repudiable.
- Must NOT claim a successful `audit_verify()` checkpoint validates source semantics, future audit entries, or
  only this tenant’s chain; it verifies the global chain through one exact tip.
- Must NOT let `uaid_app` execute/forge the global audit verifier/checkpoint or expose audit payloads.
- Must NOT call JSON-Schema validity semantic evidence completeness; the shipped schema is shallow.
- Must NOT trust persisted/app-supplied success fields instead of revalidation at export.
- Must NOT omit later failed/refused/untrusted/stale evidence merely to make a pack look cleaner.
- Must NOT copy tenant prose, source URLs/locators, artifacts, findings, reports, prompts, responses, snippets,
  logs, secrets, or arbitrary JSON into pack storage/audit/rendering.
- Must NOT claim safe digests are redacted source substitutes approved by an auditor; Slice 60 owns external
  auditor/redaction policy.
- Must NOT claim Slice 49 supplies signing, OSCAL, PDF, archive, auditor links/accounts, HTTP downloads, or
  third-party publication.
- Must NOT claim Slice 49 executes any new source evidence or changes any source lifecycle.
- Must NOT claim gate #7 is PASS-capable or any A5 gate changes. A5 stays `slice47.v1`, readiness stays
  `slice20.v1`, and go-live remains hard-false.
- Must NOT weaken, replace, or relabel any existing guard/RLS/grant/generated column/source record. The findings
  guard MD5 remains pinned.
- Must NOT start implementation before explicit plan approval and rulings on all eight ODs.

## 12. Definition of done for eventual implementation — not this plan

After explicit approval and rulings, Slice 49 implementation is complete only when:

1. every OD-49-1…8 ruling is copied verbatim into this plan and implemented exactly;
2. expected migration `0048` is additive, round-trips, preserves all existing catalog/guard behavior, and keeps
   the findings-guard MD5 pinned;
3. the canonical schema and semantic contract validate independently with exact failure provenance;
4. one current frozen candidate can produce a deterministic immutable core assembly over ruled sources, with
   truth tiers preserved and every source/traceability link auditable;
5. missing/inconsistent/untrusted/deferred sections remain explicit and fail according to the ruled matrix;
6. no release verdict or signature is fabricated; staged finalization behaves exactly as ruled;
7. the real admin-only audit verifier produces a non-forgeable exact checkpoint, or the ruled alternative is
   implemented without privilege widening;
8. safe projections and caps prevent all prohibited tenant/raw content from storage, exports, errors, logs, and
   audit;
9. immutable lifecycle and new-generation-on-change behavior are DB- and app-proven;
10. internal JSON/Markdown/manifest outputs and refusal behavior match the ruled export boundary;
11. pure, DB-backed, direct-SQL, RLS, guard-preservation, audit-sentinel, tamper, failure-injection, and migration
    tests pass;
12. `production_autonomy.py` and readiness are byte-stable; A5 outputs remain identical at `slice47.v1`,
    readiness remains `slice20.v1`, and go-live remains hard-false;
13. `git diff --check`, ruff, full pure suite, full DB suite, and `0047→0048→0047→0048` are green with exact
    output reported; and
14. implementation is submitted through the reviewed GitHub-flow process and is not merged without reviewer
    approval.

## Reviewer gate

This document is the sole deliverable of the current task. Reviewer should return **APPROVE** or **REJECT** and
cite exact lines/findings. Even after APPROVE, implementation remains blocked until the coordinator rules
OD-49-1 through OD-49-8. No branch, code, migration, tests, commit, or PR may begin before both gates are met.
