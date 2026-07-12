# Slice 47 — Issue provenance + findings→issue bridge + deferred risk-acceptance release FK (A5 gate #7, partial) — PLAN v1

**Status:** APPROVED FOR EXECUTION — v1 approved; OD-47-1…8 ruled and bound (see Rulings section)

> **Persona.** Senior release-governance, evidence-provenance, and PostgreSQL security architect applying
> fail-closed release binding, tenant isolation, append-only history, and Sanad / No-Free-Facts discipline.
>
> **Primary Sanad.** A release is go-live-ready only when its remaining open issues are non-blocking or covered
> by explicit risk-acceptance records; known open issues require risk acceptance from the approval matrix, and
> the listed hard-refusal classes cannot be silently waived (`docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:2251-2285`).
> The governance checklist requires risk acceptance when open issues exist (`spec:2287-2330`), while Appendix-B
> gate #7 is exactly “any remaining open issues have approved risk-acceptance records” (`spec:2981-2997`,
> especially line 2991). The roadmap makes Slice 47 the sole next planned item, requires verified issue
> provenance, a findings→issue bridge, and the deferred release FK, and explicitly says gate #7 remains
> `insufficient_evidence` until the Slice-50 release verdict (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:445-455,659-665,830-838`).
>
> **Verified repository Sanad.** Before this file was created, `main` and `origin/main` were both
> `e94e2acd5c02c245440ecd6f83c6acae8a26fd6e`, the worktree was clean, and no local or remote feature branch
> existed (`git rev-parse HEAD origin/main`, `git status --porcelain`, and
> `git branch -a --format=...`, verified 2026-07-12). Alembic reports `0045 (head)` and `0045` revises `0044`
> (`uv run alembic heads`; `migrations/versions/0045_acceptance_verification.py:1-17`). The A5 evaluator is
> `slice46.v1`, readiness is `slice20.v1`, gate #7 narrows only from
> `no_issue_provenance_or_release_binding` to `no_issue_provenance` when a frozen candidate exists, and gate #7
> never passes (`app/release/production_autonomy.py:59,125-157,308-334`; `app/intake/readiness.py:45`;
> `app/repositories/production_autonomy.py:17-21,126-131,166-174,187-215`). Current verified suite counts are
> 851 Docker-free and 763 DB-backed (`CLAUDE.md:560-577,1224,1327-1328`).

## Coordinator rulings (final)

- OD-47-1 = Option A: only a DB-bound trusted Slice-44 security finding or Slice-45 shortcut finding may create a gate-counted trusted issue; issue provenance value db_verified_trusted_release_finding; PM mappings stay diagnostic connector observations; Slice-42 report content stays REPORTED.
- OD-47-2 = Option A: one issue per exact finding row via unique immutable source_finding_id; retries reselect on material match, conflict otherwise; the no-double-counting claim stays narrow — no cross-run semantic dedupe is claimed.
- OD-47-3 = Option A, with the consequence explicitly accepted: category from finding_type, severity copied, blocking=true for every bridged finding, blocking_category='critical_security_blocker' for critical security findings, blocking_category='fake_done_finding' for every shortcut finding — meaning every bridged shortcut finding, regardless of severity, is a hard blocker that can never be risk-accepted, only resolved or superseded. This is the intended §2.1/§24.1 posture: shortcuts get fixed, not accepted. Code-owned source='slice47.finding_bridge.v1', bounded code-owned summary, no copied detail. Record the mapping as a conservative inference, not verbatim spec taxonomy.
- OD-47-4 = Option A: producer-integrated bridging in the same transaction for new trusted findings (a bridge failure fails the whole transaction — never commit a trusted finding with a silently failed bridge) + an explicit, bounded, idempotent reconciliation method for historical trusted findings; no migration data backfill; no auto-binding into any candidate; post-freeze findings require a new draft candidate.
- OD-47-5 = Option A: composite NOT VALID FK (tenant_id, project_id, release_id) → release_candidates(tenant_id, project_id, release_ref) with RESTRICT; enforced for new writes; history untouched and visibly unvalidated; legacy-unbound counts exposed. "D-3 closed" means exactly "new writes FK-pinned, legacy visibly unvalidated" — never "history verified."
- OD-47-6 = Option A: nullable subject_type ∈ {'release_issue','release_finding'}, required on new rows, NULL only for legacy; new acceptances resolve to one same-project frozen candidate; issue subjects must be bound to that candidate; finding subjects reach membership only through their unique bridged issue; approver provenance tiers keep their existing meanings — no upgrade.
- OD-47-7 = recommended ladder: the five rungs exactly as written in plan §4/OD-47-7 — every rung insufficient_evidence, no passed branch anywhere in gate #7; ruleset advances to slice47.v1; gate name unchanged; safe counts/booleans only in context.
- OD-47-8 = recommended ruling: slice47.finding_bridge.v1; codes ≤128; code-owned summary ≤500; no bridge detail; ≤10,000 findings per reconciliation call; no caller trusted|verified|complete|blocking_category|gate|passed fields; audit safe-metadata only per the plan's list; downgrade fails closed while trusted attached issues or non-NULL subject_type rows exist.

---

## 0. The defining honesty constraint (the crux)

This slice may prove **lineage for known issues**. It cannot prove that all issues have been discovered.

The plan uses four truth classes and does not flatten them:

1. **REPORTED** — a caller supplied an issue, classification, lifecycle actor label, review-report verdict, or
   risk-acceptance signer/authority claim. Existing manual `release_issues.source` and
   `source_provenance='caller_supplied_unverified'` are in this tier
   (`app/models/release_issue.py:64-80`; `migrations/versions/0023_release_issues.py:179-208`). Slice-42 review
   report content is also `caller_supplied_unverified`, although the reporter registration is FK-bound
   (`app/models/review_report.py:1-12,43-68,100-119`; `migrations/versions/0041_task_contracts.py:266-353`).
2. **CONNECTOR-OBSERVED** — the PM connector observed an external Jira issue reference/status/board column.
   It did not verify the issue's UAID severity, blocker class, completeness, or release membership
   (`app/release/pm_issues.py:1-8,17-20,101-149`; `app/models/pm_issue_mapping.py:1-10,51-109`). Likewise, the
   Slice-44 security source proves a bounded CI artifact was connector-observed, not that UAID executed the
   scanner or that the scanner found every defect (`app/models/security_scan_run.py:24-76,95-118`).
3. **DB-PROVEN / SYSTEM-DERIVED** — the database proves a release issue was derived from one exact existing
   trusted `release_findings` row, and that finding already carries the guarded Slice-44 security attachment or
   Slice-45 shortcut attachment. The security path is
   `connector_verified_security_scan`; the shortcut path is `system_executed_shortcut_review`
   (`app/models/release_finding.py:48-85,96-135`; `migrations/versions/0044_shortcut_detector_execution.py:573-756`).
   This proves lineage, exact linkage, and ruled structural mapping. It does **not** prove the narrative is true,
   the detector is complete, or the release contains every issue.
4. **GATE-INFERRED** — gate #7 may report bounded counts over the latest frozen candidate's declared bindings
   and distinguish trusted from untrusted known issues. Even if every bound issue has trusted provenance, the
   result remains `insufficient_evidence` because no Slice-50 release verdict/completeness decision exists
   (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:445-455,483-490`; current evaluator at
   `app/release/production_autonomy.py:308-334`).

Therefore:

- An empty `release_issues` table is **not** evidence that no issues exist.
- A populated table is **not** evidence that all issues are known.
- A connector-observed PM record is **not** a verified blocker classification.
- A DB-bound finding bridge is evidence about one known issue only.
- A `release_id` FK proves referential/release binding for ruled rows; it does not verify approver authority,
  signature, risk reason, or issue-set completeness.
- Gate #7 has **no PASS path in Slice 47**. The slice advances the quality and precision of evidence only.

## 1. Scope and non-goals

### 1.1 In scope after plan approval and all OD rulings

- Add a strict trusted-finding→release-issue path that reuses `release_findings` and `release_issues`; do not
  fork either lifecycle store (`app/release/findings.py:1-14`; `app/release/issues.py:1-17`).
- Add an immutable direct source-finding attachment to `release_issues` and a ruled trusted provenance value.
  Existing rows remain `caller_supplied_unverified`; there is no historical relabeling.
- Derive issue category, severity, blocking semantics, source code, and safe summary shape by code/DB rule rather
  than accepting caller truth on the bridge path.
- Preserve one finding lifecycle and one issue lifecycle. Bridge creation does not resolve, accept, supersede,
  reopen, or otherwise transition either row.
- Prevent one `release_findings` row from spawning more than one issue; gate #7 counts `release_issues`, not
  findings plus issues.
- Close roadmap D-3 for new writes by binding `risk_acceptance_records.release_id` (`TEXT`) to the same-project,
  same-tenant `release_candidates.release_ref` (`TEXT`) namespace—not to the candidate UUID. The intended
  namespace is documented in the Slice-25 decision (`.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md:64-71,130-139`)
  and the current types are visible at `app/models/risk_acceptance_record.py:53-63` and
  `app/models/release_candidate.py:50-60`.
- Make new risk-acceptance writes release-consistent with a ruled frozen candidate and its freeze-locked issue
  binding, while preserving the existing fact that `risk_acceptance_records.issue_id` can be consumed by either
  the release-finding or release-issue lifecycle. Keep pre-Slice-47 rows visibly legacy/unvalidated if OD-47-5
  selects that path.
- Refine only A5 gate #7's reason/context under proposed ruleset `slice47.v1`; it remains
  `insufficient_evidence` for every input.
- Add pure and DB-backed tests, including direct-SQL attacks against bridge provenance, tenant/project pins,
  legacy FK behavior, issue/risk lifecycles, RLS, immutability, and gate serialization.
- Expected migration `0046` after current head `0045`. This number is an **inference** from the actual migration
  chain, not an approved fact; the roadmap intentionally leaves the post-`0045` revision to this reviewed plan
  (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:445-455,898`).

### 1.2 Non-goals

- No §24.3 release verdict or claim of issue-set completeness; that is Slice 50
  (`spec:2332-2341`; roadmap `:483-490`).
- No evidence-pack generator/auditor/export; that is Slice 49 (roadmap `:469-479`).
- No reviewer-QA harness or upgrade of Slice-42 reported review content; reviewer QA is Slice 48
  (roadmap `:457-467`; `app/models/review_report.py:1-12`).
- No new scanner, detector, LLM call, reviewer execution, SCM method, PM provider call, or live network access.
- No semantic inference that a PM issue equals a release blocker. The existing PM store is mapping-only and
  carries no title, description, severity, blocker category, or release-issue FK
  (`migrations/versions/0033_pm_issue_mappings.py:7-14,50-126`).
- No global cross-run semantic dedupe unless explicitly selected in OD-47-2. Existing Slice-44/45 fingerprints
  are guarded per run (`app/models/release_finding.py:70-85`; `migrations/versions/0044_shortcut_detector_execution.py:679-689`).
- No automatic binding of a newly bridged issue into a frozen candidate. Membership is append-only and may be
  added only while the candidate is `draft` (`app/repositories/release_candidates.py:62-77`;
  `migrations/versions/0024_release_candidates.py:216-247`).
- No weakening or rewriting of gates #1-#6 or #8-#13; no readiness change; no go-live enablement.
- No verified-human-signature claim. `request_authenticated` remains key custody, not human signature
  (`app/release/risk_acceptance.py:16-18`; `app/repositories/risk_acceptance.py:37-78`).
- No API/UI surface, migration execution, implementation, tests, branch, or PR in this plan-only task.

## 2. Current repository truth and the gaps this slice closes

| Current fact | What is proven now | What is missing | Sanad |
|---|---|---|---|
| Manual `release_issues` insert | Known row, validated taxonomy/lifecycle, caller-supplied source | Trusted origin and completeness | `app/release/issues.py:24-45,66-101`; `app/models/release_issue.py:64-80` |
| Slice-44 security finding | Exact guarded scan-category attachment, connector-observed CI provenance | General gate-#7 issue row/binding | `app/repositories/security_scans.py:150-230`; `0044_shortcut_detector_execution.py:653-689` |
| Slice-45 shortcut finding | Exact guarded detector-category attachment, system-executed hybrid lineage | General gate-#7 issue row/binding | `app/repositories/shortcut_detectors.py:418-499`; `0044...py:590-630` |
| Slice-42 review report | Registered reviewer/layer and reported verdict/list shape | Trusted report content and structured issue provenance | `app/models/review_report.py:1-12`; `0041_task_contracts.py:266-353` |
| Slice-34 PM mapping | Connector-observed external ref/status/board column | UAID issue classification, release binding, completeness | `app/release/pm_issues.py:1-8`; `app/models/pm_issue_mapping.py:90-109` |
| Release candidate binding | Declared known issue membership frozen at `frozen` | Proof that membership is complete | `app/repositories/release_candidates.py:97-154`; Slice-25 discussion `:92-110` |
| Risk acceptance `issue_id` | Free `TEXT`; finding and issue acceptance guards each compare it to their own row UUID when used | An explicit subject kind and release membership for every historical record | `app/models/risk_acceptance_record.py:60-63`; `0044_shortcut_detector_execution.py:725-743`; `0023_release_issues.py:227-252` |
| Risk acceptance `release_id` | Required immutable free `TEXT` | Any release-candidate referential constraint | `app/release/risk_acceptance.py:44-58`; `app/models/risk_acceptance_record.py:60-63`; `0026_request_auth_identity.py:40-102` |
| Gate #7 | Counts known issues/acceptances and frozen candidate bindings | Trusted issue provenance, release-bound risk acceptance, completeness/verdict | `production_autonomy.py:308-334`; `repositories/production_autonomy.py:126-131,166-174,193-215` |

### 2.1 Actual legacy-row observation (not a deployment-wide claim)

A read-only aggregate query against the running local `app_test` database on 2026-07-12 found **714**
`risk_acceptance_records`, **0** UUID-shaped `release_id` values, and **0** rows whose `release_id` matched a
same-tenant/same-project `release_candidates.release_ref`. The local `app` database did not contain the table.
This is operational evidence about this workspace only; it is **not** evidence about production or every
installation. It proves that a migration plan cannot assume the current local history is FK-clean. Repository
history independently permits arbitrary non-blank `TEXT` release IDs and makes them immutable
(`0021_risk_acceptance.py:28-65,133-171`; `0026_request_auth_identity.py:40-102`).

Consequently, a fully validated retro-FK is not an honest default. OD-47-5 must select a legacy strategy, and
tests must exercise both pre-existing unmatched rows and post-migration writes.

## 3. Required provenance, bridge, and release-binding semantics

### 3.1 Trusted finding eligibility

A finding is eligible for the trusted bridge only if all of these are DB-proven:

- same tenant and project as the issue;
- `status='open'` when bridge creation begins;
- `finding_type='security'` with `source_provenance='connector_verified_security_scan'`, non-null
  `security_scan_category_result_id`, non-null well-shaped scan fingerprint, and no shortcut attachment; **or**
- `finding_type='shortcut'` with `source_provenance='system_executed_shortcut_review'`, non-null
  `shortcut_detector_category_result_id`, non-null well-shaped shortcut fingerprint, and no security attachment;
- category/result/run relationships already satisfy the active `release_findings_guard()` and upstream
  composite FKs (`app/models/release_finding.py:48-85`; `0044_shortcut_detector_execution.py:573-756`).

Manual findings, `other` findings without a ruled trusted category attachment, unsupported provenance, PM rows,
and reported review content are not eligible. The bridge must query the stored row; it never accepts a caller's
`trusted`, `verified`, `finding_type`, `severity`, `category`, attachment, or fingerprint assertion.

### 3.2 One-way derivation, not lifecycle coupling

Bridge creation creates one new `release_issues` row and an ordinary `release_issue_events.created` event. It
does not update the finding. After commit:

- finding and issue statuses remain independently governed by their existing one-way lifecycles;
- resolving/false-positive/accepting/superseding a finding never auto-transitions the issue;
- resolving/accepting/superseding the issue never auto-transitions the finding;
- a later clean scan/review does not close either row;
- a terminal issue is never reopened; a new finding observation is separate evidence unless OD-47-2 explicitly
  selects a more complex lineage policy.

These boundaries preserve the Slice-23 and Slice-24 lifecycle contracts
(`app/release/findings.py:9-13,89-92`; `app/release/issues.py:13-17,98-101`).

### 3.3 Release binding and risk acceptance

The deferred referent is `release_candidates.release_ref`, not `release_candidates.id`: both the spec template
and current risk store use `release_id: string`, while Slice 25 deliberately created `release_ref` as the future
per-project namespace (`spec:2750-2767`; `schemas/risk_acceptance_record.yaml:1-14`;
`.planning/SLICE-25-RELEASE-BINDING-DISCUSSION.md:32-38,64-71`).

A gate-relevant risk acceptance must eventually prove, at minimum:

- its release ref exists for the same tenant/project;
- the selected release candidate is in the coordinator-ruled lifecycle state;
- an explicit ruled subject kind distinguishes `release_issue` from `release_finding` without guessing across
  two UUID namespaces;
- for an issue subject, `issue_id` identifies the same release issue being accepted and that issue is bound to
  the candidate;
- for a finding subject, `issue_id` identifies the same release finding being accepted and its unique bridged
  release issue is bound to the candidate;
- the record remains active, unexpired, non-hard-refusal, and otherwise usable under the existing store rules;
- the issue's acceptance references that exact record.

This proves referential consistency only. `caller_supplied_unverified` and `request_authenticated` approver
provenance retain their existing meanings; neither becomes a verified human signature or approval-matrix proof.

### 3.4 Selection and staleness

Slices 43–46 use exact bindings, deterministic latest selection, composite tenant/project FKs, and no invented
wall-clock TTL where the governing spec supplies none (`.planning/SLICE-43-PLAN.md:225-230,297-310`;
`.planning/SLICE-44-PLAN.md:270-283,399-419`; `.planning/SLICE-45-PLAN.md:311-320,466-489`;
`.planning/SLICE-46-PLAN.md:262-277,390-428`). Slice 47 reuses that discipline but does **not** invent another
run/snapshot table:

- release scope is the current latest frozen candidate under the existing deterministic order
  `(frozen_at DESC,created_at DESC,id DESC)` (`app/repositories/release_candidates.py:107-122`);
- the candidate's issue membership is freeze-locked and append-only;
- issue provenance is the immutable direct source-finding attachment, not a time-limited assertion;
- current issue/finding/risk lifecycle state is read live; risk expiry remains date-based under the existing
  record contract (`app/repositories/risk_acceptance.py:86-119`);
- there is no wall-clock TTL for the bridge. A changed candidate requires its own bindings; a new finding row
  requires its own ruled bridge; a later lifecycle event changes current disposition without erasing history.

This is a proposed application of prior house discipline. OD-47-7 still controls the exact gate selection and
reason precedence.

## 4. OPEN DECISIONS — coordinator ruling required before implementation

### OD-47-1 — Which existing sources qualify as trusted issue provenance?

**Option A — strict existing-evidence reuse (recommended).** Only a DB-bound trusted Slice-44 security finding
or Slice-45 shortcut finding may create a gate-counted trusted issue. Security remains honestly
connector-observed; shortcut remains honestly system-executed hybrid review. PM mappings remain diagnostic
connector observations; Slice-42 reports remain registered-but-REPORTED; generic CI/reviewer strings remain
unsupported. Proposed issue provenance: `db_verified_trusted_release_finding`.

**Option B — include PM-origin issues as trusted.** Rejected by recommendation: PM rows contain no severity,
category, blocking flag, narrative, or release membership, so any such classification would still be reported.

**Option C — introduce a new reviewer/CI issue artifact and executor.** This could provide a broader source but
adds a new schema/execution subsystem beyond the roadmap's “extend, not fork” scope and requires a separately
reviewed design.

**No ruling ⇒** all issues remain unverified for gate #7 and no bridge is implemented.

### OD-47-2 — What is the bridge cardinality and dedupe boundary?

**Option A — one issue per exact finding row (recommended).** Add a unique immutable `source_finding_id` on
`release_issues`; one finding can create at most one issue, retries reselect the materially identical issue, and
gate #7 counts only issues. No global/cross-run semantic dedupe is claimed. A later run's new finding row may
create a new issue even if its provider fingerprint resembles an earlier row; this avoids silently conflating
different commits/contracts or reopening a terminal issue.

**Option B — roll up by a stable cross-run fingerprint.** Requires a ruled identity key, repo/commit/contract
semantics, recurrence generation, and concurrency guard. It risks treating distinct defects as one or treating a
recurrence as resolved. Not recommended in this slice.

**Option C — many findings to one manually selected issue.** Makes semantic identity caller-selected and cannot
be called DB-verified without another reviewed adjudication mechanism.

Option A's “no double-counting” claim is deliberately narrow: one DB finding row cannot produce two issue rows,
and gate #7 never sums both stores. It is not a universal semantic-deduplication claim.

### OD-47-3 — How are issue fields and blocker semantics derived from a trusted finding?

**Option A — conservative code-owned mapping (recommended).** Derive `issue_category` exactly from
`finding_type`, copy `severity`, set `blocking=true` for every bridged finding, set
`blocking_category='critical_security_blocker'` for critical security findings, set
`blocking_category='fake_done_finding'` for every shortcut finding, and otherwise leave
`blocking_category=NULL`. Use code-owned `source='slice47.finding_bridge.v1'`, a code-owned bounded summary by
type/category, and no copied detail. The source finding remains the narrative referent. This is conservative:
all known trusted findings require explicit disposition, and §24.1 hard-refusal classes cannot be accepted
(`spec:2269-2285`; `app/release/risk_acceptance.py:23-31`; `app/release/issues.py:52-59`).

**Option B — only critical findings are blocking.** Closer to Appendix-B gates #5/#6 but lets non-critical
trusted findings become non-blocking by construction without a documented issue-triage policy.

**Option C — caller supplies blocking/category/summary/detail.** Rejected by recommendation because it turns
the bridge's load-bearing classification back into REPORTED data.

The mapping is a proposed conservative inference, not verbatim spec taxonomy. Coordinator acceptance must say
so explicitly.

### OD-47-4 — When does bridging run, and how does it interact with release-candidate freeze?

**Option A — producer-integrated for new trusted findings + explicit idempotent reconciliation for old trusted
findings (recommended).** Slice-44/45 repositories call the bridge in the same transaction after persisting each
trusted finding. A separate internal method may explicitly bridge eligible historical trusted findings; the
migration performs no automatic data backfill. No bridge method auto-binds a candidate. If a finding appears
after candidate freeze, the issue cannot enter that frozen membership; a new draft candidate is required.

**Option B — explicit bridge invocation only.** Smaller producer changes, but trusted findings can remain
silently unbridged unless an orchestrator calls the method.

**Option C — auto-bind to the latest candidate, including frozen candidates.** Rejected: this would weaken the
Slice-25 freeze lock and silently change a release's declared issue set
(`migrations/versions/0024_release_candidates.py:216-247`).

### OD-47-5 — How is the legacy `release_id TEXT` FK added?

**Option A — composite `NOT VALID`, enforced for new writes (recommended).** Add
`(tenant_id,project_id,release_id) → release_candidates(tenant_id,project_id,release_ref)` with `RESTRICT`, leave
the constraint unvalidated over history, and expose legacy-unbound counts. Existing rows are not relabelled,
deleted, or mutated. New repository/direct-SQL writes must satisfy the referent. This is the only option
compatible with the verified local legacy observation without inventing mappings.

**Option B — fully validate and fail migration on any unmatched row.** Strongest final catalog state but known
to fail against the current local `app_test` history and unsafe to assume for unknown deployments.

**Option C — add a separate append-only remediation sidecar before validating.** Preserves history and could
support explicit mappings, but is a larger authority/migration workflow not requested by the roadmap. It still
cannot guess which candidate an arbitrary legacy string meant.

Under Option A, “D-3 closed” means **new writes are FK-pinned and legacy rows are visibly unvalidated**. It must
not be reported as “all historical risk acceptances are release-verified.” A future validation/remediation step
remains explicit.

### OD-47-6 — What release-candidate and issue-binding checks apply to new risk acceptances?

**Option A — frozen, bound, explicit subject kind (recommended).** Add nullable
`subject_type ∈ {'release_issue','release_finding'}` to `risk_acceptance_records`; it is required for new rows and
NULL only for legacy rows. On INSERT, `release_id` resolves to one same-project candidate with `status='frozen'`.
For `release_issue`, `issue_id` is the UUID text of that same-project issue and the issue is bound to the
candidate. For `release_finding`, `issue_id` is the UUID text of that same-project finding and the finding's
unique bridged issue is bound to the candidate. The DB verifies the declared subject kind; a caller cannot make
an arbitrary ID authoritative. The existing hard-refusal/required-field/provenance rules remain. Each
`accepted` transition must consume a record whose immutable, DB-checked subject kind and exact release
membership match that lifecycle. Legacy rows stay diagnostic unless a separately ruled remediation exists.

**Option B — any candidate lifecycle state.** Referentially valid but permits risk acceptance before release
membership freezes, so the accepted issue set may change after the decision.

**Option C — FK existence only; no subject/binding check.** Closes the column FK mechanically but permits an
acceptance for a finding/issue outside the named release and leaves the polymorphic `issue_id` ambiguous. Not
recommended.

No new direct `risk_acceptance_records.issue_id` FK is proposed: it is a polymorphic `TEXT` reference consumed by
both finding and issue guards, while both target IDs are UUIDs. Option A adds an explicit DB-checked subject kind
and release-membership proof without breaking the Slice-23 noncritical-finding acceptance path
(`0044_shortcut_detector_execution.py:725-743`; `0023_release_issues.py:227-252`).

### OD-47-7 — What exact gate-#7 ladder and context are recorded?

**Recommended ladder (all rungs remain `insufficient_evidence`):**

1. no frozen candidate → `insufficient_evidence:no_issue_provenance_or_release_binding`;
2. frozen candidate but zero declared bound issues →
   `insufficient_evidence:no_declared_issue_inventory_or_release_verdict` (empty is never “clean”);
3. any bound issue missing ruled trusted provenance →
   `insufficient_evidence:bound_issue_provenance_incomplete`;
4. any bound accepted issue whose risk acceptance is legacy-unbound, wrong-release, expired, inactive, or
   otherwise unusable → `insufficient_evidence:risk_acceptance_release_binding_incomplete`;
5. all known bound issues have ruled provenance and any accepted issue has a usable exact-release record →
   `insufficient_evidence:verified_known_issue_set_but_no_release_verdict`.

Safe context only: frozen-candidate count/id/ref; total/bound/open/blocking counts; bound trusted/untrusted issue
counts; bound finding-bridge count by type; release-bound active risk-acceptance count; legacy/unmatched risk-
acceptance count; and booleans for declared membership/provenance/risk-binding consistency. No issue/finding
prose, provider artifact, PM status, repo/commit, fingerprint, risk reason, signer list, or evidence link.

The A5 ruleset advances `slice46.v1 → slice47.v1` because gate #7's input contract, reason precedence, and
context change. There is **no `passed` branch**. All other gate dicts must remain byte-identical for identical
inputs.

### OD-47-8 — What schema versions, bounds, and audit contract are authoritative?

**Recommended ruling:** bridge contract `slice47.finding_bridge.v1`; issue provenance value
`db_verified_trusted_release_finding`; source/key/reason/provenance codes ≤128 characters; code-owned issue
summary ≤500 characters; no bridge detail; UUIDs strict; aggregate counts non-negative and bounded to the
repository result set; at most 10,000 findings per explicit reconciliation call; no caller-provided
`trusted|verified|complete|blocking_category|gate|passed` field is accepted on the bridge path.

Audit is safe metadata only: issue/finding IDs, project ID, type/category, severity, blocking, provenance code,
status, and aggregate counts. It must never include summary/detail/resolution text, raw finding narrative,
fingerprint, repo/commit, scanner artifact, shortcut corpus, prompt/response, PM status/title/description, risk
reason/business impact/controls, signer/accepted-by values, evidence links, credentials, or arbitrary JSON.

These names and numeric caps are proposed engineering choices, not spec facts. **No ruling ⇒** no implementation.

## 5. Proposed pure module changes (contingent on §4 rulings)

### 5.1 `app/release/issues.py`

- Add constants for ruled trusted issue provenance, bridge source, bridge contract, and exact finding→issue
  category/blocker mapping.
- Add a frozen `TrustedFindingIssueDerivation` value carrying only IDs, enums, booleans, and code-owned summary.
- Add `derive_issue_from_finding(...)` that accepts a repository-loaded structural finding view, rejects every
  unsupported/untrusted/non-open/malformed combination, and returns derived fields. It never accepts caller
  blocking/provenance/trust.
- Preserve `validate_new_issue` and existing lifecycle semantics for manual issues. Add a separate trusted-create
  validator rather than weakening the caller path.
- Add pure helpers for release-bound risk-acceptance evidence and gate-#7 reason precedence. Negative or
  inconsistent counts fail closed; no helper returns a gate pass.

### 5.2 No new detector or connector

The bridge consumes stored, already-guarded rows. `SCMConnector`, `GitHubSCMConnector`, `FakeSCMConnector`, PM
connector, LLM clients, and reviewer execution do not change. This slice performs no network/model work.

## 6. Storage and proposed migration `0046` (additive-only intent; contingent on rulings)

The migration is expected to revise `0045`. It adds one nullable attachment and constraints, extends two guard
functions without weakening prior rules, and adds no parallel finding/issue/risk lifecycle store.

### 6.1 `release_issues` direct trusted-finding attachment

Proposed additive column:

- `source_finding_id UUID NULL`.

Proposed constraints/index:

- composite FK `(source_finding_id,tenant_id) → release_findings(id,tenant_id) ON DELETE RESTRICT`;
- unique partial index `(tenant_id,source_finding_id) WHERE source_finding_id IS NOT NULL`;
- existing rows remain NULL + `caller_supplied_unverified`;
- `source_finding_id` is immutable once inserted.

Replace `release_issues_guard()` only as required to add a trusted INSERT branch. The new function must preserve
every Slice-24 rule: open-only insert; lifecycle metadata NULL at create; taxonomy/severity/other checks;
critical/hard-refusal⇒blocking; immutable identity/content/source; same-status no metadata mutation; one-way
terminal lifecycle; hard blockers cannot be accepted; accepted requires an active/unexpired/nonblocking same-
tenant/project exact-issue risk record; non-accepted states cannot carry acceptance IDs
(`migrations/versions/0023_release_issues.py:179-266`).

Additional trusted-branch DB proofs:

- caller-unverified issue ⇒ `source_finding_id IS NULL`;
- trusted provenance ⇒ non-null source finding, exact code-owned source/summary shape, no copied detail, and exact
  OD-47-3 category/severity/blocking/blocking-category derivation;
- parent finding same project, open at bridge insert, and exactly one allowed trusted Slice-44/45 provenance+
  attachment shape;
- no PM/review/manual row can enter the trusted branch;
- update cannot change source attachment/provenance/derived fields.

Downgrade drops the new attachment/index/FK and restores the exact pre-`0046` Slice-24 guard. Downgrade must fail
closed if trusted attached issues exist rather than silently converting them to unverified or deleting history;
the exact downgrade policy is part of OD-47-8 review and migration tests.

### 6.2 Findings guard preservation

Migration `0046` must not replace, alter, drop, or weaken `release_findings_guard()`, its deferrable verification
triggers, category/result FKs, fingerprint indexes, grants, or RLS. The bridge only reads and references findings.
Tests compare the guard definition/catalog before and after `0046` and rerun every Slice-23/44/45 adversarial
invariant (`0022_release_findings.py`; `0043_security_scan_provenance.py`;
`0044_shortcut_detector_execution.py:573-756`).

### 6.3 `risk_acceptance_records.release_id` composite FK and guard extension

Under OD-47-5 Option A:

- add a composite `NOT VALID` FK
  `(tenant_id,project_id,release_id) → release_candidates(tenant_id,project_id,release_ref) ON DELETE RESTRICT`;
- do not cast `release_id`, mutate historical values, invent candidate mappings, or change the spec-facing string
  field;
- keep constraint validation state visible and count unmatched legacy rows as non-gate-bearing;
- replace the current Slice-27 `risk_acceptance_records_guard()` only to add the ruled candidate/issue-binding
  INSERT proof while preserving all Slice-22 fields, hard-refusal checks, active-only create, immutable columns,
  one-way lifecycle, and both allowed approver provenance tiers
  (`0021_risk_acceptance.py:28-171`; `0026_request_auth_identity.py:40-102`).

Under OD-47-6 Option A, add nullable `subject_type` (legacy NULL; required on new INSERT) and require the exact
same-tenant/project `release_ref`, frozen candidate, subject UUID text, and freeze-locked candidate→issue
binding. A finding subject reaches candidate membership only through its unique trusted bridge issue. The guard
never upgrades approver provenance.

Downgrade drops only the Slice-47 FK/extra checks and restores the exact pre-`0046` Slice-27 risk-acceptance
guard. It must fail closed while any post-Slice-47 non-NULL `subject_type` row exists rather than silently discard
release-binding evidence; an empty-data migration round trip remains required. Historical records and events
remain untouched.

### 6.4 Existing RLS, grants, append-only history, and audit

No new tenant table is required under the recommended direct-attachment design. Existing `release_findings`,
`release_issues`, `release_issue_events`, `risk_acceptance_records`, `risk_acceptance_events`,
`release_candidates`, and candidate bindings retain their RLS ENABLE+FORCE policies and grants. No DELETE or
TRUNCATE privilege is added; lifecycle events remain append-only. Audit uses §4/OD-47-8 safe metadata only.

## 7. Repository/orchestrator behavior

### 7.1 Trusted bridge transaction

Proposed `ReleaseIssueRepository.create_from_trusted_finding(...)`:

1. load the finding inside the caller's tenant scope; reject missing/cross-tenant/cross-project;
2. validate the stored current row against the ruled trusted eligibility; never trust payload fields;
3. derive issue fields via the pure mapping;
4. insert `release_issues` with immutable source attachment/provenance and existing `open` lifecycle;
5. on unique conflict, reselect by `source_finding_id` and return only if every material derived field matches;
   otherwise raise an idempotency conflict;
6. write the existing append-only `created` event and safe audit metadata;
7. do not transition the finding and do not bind any release candidate.

Under OD-47-4 Option A, security-scan and shortcut-detector success writers invoke this after each trusted finding
inside the same transaction. Any bridge failure fails the transaction; the system does not commit a trusted
finding while pretending its issue bridge succeeded. Explicit historical reconciliation is bounded/idempotent
and never runs in the migration.

### 7.2 Risk-acceptance creation and issue acceptance

`RiskAcceptanceRepository.create` continues accepting the spec-facing `release_id` string and requires the
ruled subject kind, but loads the candidate and exact issue/finding→bridge binding before INSERT. It does not
accept a caller-provided candidate UUID or verified flag. Existing signer provenance behavior remains unchanged.

The `release_issues` accepted transition additionally checks that the chosen active risk record belongs to a
candidate containing that issue. A record accepted for release A must not silently satisfy release B. Existing
accepted legacy issues are not rewritten; gate context marks a mismatched/unbound acceptance inconsistent.

### 7.3 Compute-on-read gate context

Add repository helpers scoped to the latest frozen candidate that count all bound issues (not only open),
trusted/untrusted provenance, bridge type, current open/blocking state, and accepted issues with exact usable
release-bound risk records. Queries join through tenant/project keys and leak no prose or cross-tenant IDs.

The evaluator remains read-only and deterministic. It does not persist a verdict or completeness flag.

## 8. A5 gate #7 and readiness — exact proposed change

### 8.1 Gate #7

- Advance `A5_RULESET_VERSION` from `slice46.v1` to proposed `slice47.v1`.
- Replace the two-reason gate-#7 branch with the coordinator-ruled §4/OD-47-7 ladder.
- Gate name remains `approved_risk_acceptance_records`, unless the coordinator explicitly rules a versioned
  rename; Appendix B names the condition, not an implementation identifier (`spec:2991`).
- Every rung returns `status='insufficient_evidence'`; **there is no `GateResult(... STATUS_PASSED ...)` path for
  gate #7 in this slice**.
- The most advanced reason says only that the **known, bound** issue set has trusted lineage and internally
  consistent risk-release bindings; it explicitly says the release verdict is absent.
- Empty issue membership, zero findings, zero open issues, or zero risk acceptances can never imply completion.

### 8.2 What does not change

- Gate #5 continues to use security-scan coverage and all-source open-critical security findings; gate #6
  continues to use shortcut coverage and all-source open-critical shortcut findings. Bridging neither consumes
  nor suppresses those counts (`app/release/production_autonomy.py:336-417,418-528`).
- Gates #1-#6 and #8-#13 serialize identically for identical inputs. Gate order remains 1..13.
- Slice-23/44/45 finding guard and lifecycle are unchanged; Slice-24 issue lifecycle is preserved with a new
  trusted create branch; Slice-25 candidate freeze semantics are unchanged.
- Gate #7 does not become PASS-capable until a separately reviewed Slice-50 verdict/completeness design exists.
- `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- `a5_satisfied` remains the conjunction of all 13 gates; `can_go_live_autonomously` remains hard-false and the
  request-authenticated A5 preapproval still does not exist (`production_autonomy.py:46-50,66-69,96-114`).

## 9. Test plan for eventual implementation

### 9.1 Pure / Docker-free

- Trusted-source matrix: valid Slice-44 security and Slice-45 shortcut structures accepted; manual finding,
  caller `trusted` flag, wrong/blank/unknown provenance, mixed attachments, unsupported type/category, terminal
  finding, malformed UUID/hash, and PM/review/CI labels rejected.
- Deterministic field mapping for every security/shortcut category × severity; exact critical⇒blocking and ruled
  hard-refusal mapping; caller category/severity/blocking/source/summary/detail cannot override.
- One-finding/one-issue idempotency; exact retry returns existing; material mismatch conflicts; no cross-run
  semantic-dedupe claim.
- Bridge/lifecycle independence: neither side transitions the other; later clean evidence does not close rows.
- Candidate interaction: bridge never binds a candidate; frozen membership is immutable; issue appearing after
  freeze requires a new candidate.
- Risk-release binding: exact same-tenant/project release ref, candidate state, explicit issue/finding subject,
  bound issue or finding→bridge membership, and active/unexpired record; wrong subject kind, ambiguous ID, wrong
  release, unbound subject, legacy unmatched row, expired/revoked/superseded record fail.
- Gate #7: every ladder rung and precedence; empty membership never passes; negative/inconsistent counts fail
  closed; advanced evidence still insufficient; context contains safe bounded metadata only.
- A5 regression: ruleset `slice47.v1`; only gate #7 changes; representative reports keep `a5_satisfied=false`
  and go-live false. Hash/output check keeps readiness `slice20.v1` byte-stable.

### 9.2 DB-backed and direct-SQL adversarial tests

- Migration round trip `0045→0046→0045→0046`; head/model/catalog parity; no unruled object; downgrade policy for
  attached trusted issues explicit and fail-closed; no historical relabel/delete/backfill.
- Seed unmatched legacy risk rows before upgrade. Under OD-47-5 A, upgrade succeeds with FK unvalidated; old
  rows remain queryable/untrusted; new unmatched rows fail; new exact rows succeed; cross-tenant/project and
  wrong candidate ref fail. A deliberate `VALIDATE CONSTRAINT` fails while unmatched legacy rows exist.
- New risk-acceptance direct SQL rejects NULL/unknown/forged `subject_type`, non-frozen candidate, issue not bound
  to candidate, finding without exactly one bridged bound issue, subject-kind/UUID mismatch, same release ref in
  wrong project/tenant, hard-refusal category, forged approver provenance, invalid status/expiry/authority shape,
  and mutation of immutable release/issue/subject/prose/provenance fields.
- Re-prove every Slice-22/Slice-27 guard rule: required fields; active-only insert; hard-refusal rejection;
  approver provenance only `caller_supplied_unverified|request_authenticated`; immutable identity/content;
  one-way terminal lifecycle; no DELETE/TRUNCATE; exact downgrade restores the pre-`0046` function.
- RLS: same-tenant bridge succeeds; cross-tenant rows invisible; cross-project parent rejected; PUBLIC revoked;
  exact existing grants preserved; no bypass role; source-finding FK and unique index enforced.
- Direct SQL cannot forge trusted issue provenance with null/manual/wrong-type/wrong-project/terminal finding,
  wrong attachment, mismatched category/severity/blocking/hard-refusal/source/summary/detail, duplicate source
  finding, or lifecycle metadata at insert.
- Re-prove every Slice-24 rule against the replaced issue guard: taxonomy, `other`, critical/hard⇒blocking,
  open-only create, immutable content/source, one-way lifecycle, terminal immutability, hard cannot accept,
  accepted requires exact usable record, non-accepted cannot carry record, no DELETE/TRUNCATE.
- Issue acceptance direct SQL rejects a risk record for another release/candidate or an issue not bound to that
  candidate, even if every old Slice-24 usability field passes.
- **Layered finding-guard preservation:** compare `release_findings_guard()`/triggers/constraints/grants before
  and after migration; rerun every Slice-23 lifecycle/critical rule, Slice-44 security attachment/provenance/
  count rule, and Slice-45 shortcut attachment/provenance/independence/count rule. Migration `0046` must not
  call a finding-guard replacement helper.
- Re-prove Slice-25 candidate guard/binding: draft-only bind, same project, freeze lock, no unbind, append-only,
  lifecycle/identity immutable. Bridge never changes candidate rows or bindings.
- PM/review adversarial cases: connector-verified PM mapping and registered review report cannot satisfy trusted
  issue provenance; forged cross-link/ref/status/actor labels fail or remain diagnostic.
- Audit sentinel injects finding prose, issue prose, resolution text, fingerprints, repo/commit, PM status,
  risk reason/business impact/controls, signer values, evidence URLs, prompts, model output, token-like strings,
  and credentials into permitted source fields and proves Slice-47 audit contains safe metadata only.
- Production-autonomy repository selects the latest frozen candidate deterministically, uses exact bound issue/
  risk joins, emits the ruled no-pass reason/context, leaks no prose/cross-tenant IDs, and changes only gate #7.

### 9.3 Verification commands (eventual implementation only)

`git diff --check`; Ruff; focused pure tests; focused DB tests; `make test`; `make test-db`; migration
`0045→0046→0045→0046`; CI. These are future implementation review requirements, not commands authorized by
this plan-only task.

## 10. Proposed file touch map (eventual implementation only)

- Modify pure issue/bridge validation: `app/release/issues.py`.
- Modify issue model/repository: `app/models/release_issue.py`, `app/repositories/release_issues.py`.
- Modify trusted producer repositories only under OD-47-4 Option A:
  `app/repositories/security_scans.py`, `app/repositories/shortcut_detectors.py`.
- Modify risk-release binding: `app/models/risk_acceptance_record.py`,
  `app/repositories/risk_acceptance.py`; preserve public spec-facing `release_id` string.
- Add expected migration `migrations/versions/0046_issue_provenance.py` (filename provisional until ruling) and
  focused `tests/test_issue_provenance.py`.
- Modify gate #7 only: `app/release/production_autonomy.py`,
  `app/repositories/production_autonomy.py`, and focused golden/API tests.
- Modify `app/models/__init__.py` only if a ruled design adds a model; the recommended direct column adds none.
- Do not modify `app/release/pm_issues.py`, PM connector/network code, review-report execution, SCM/LLM adapters,
  `app/intake/readiness.py`, or any gate other than #7.
- No branch, code, migration, test, commit, or PR is authorized until this plan is approved and OD-47-1 through
  OD-47-8 are explicitly ruled. This plan file is the sole deliverable now.

## 11. Must NOT claim

- Must NOT claim an empty issue store, empty candidate binding set, zero open rows, or zero bridged findings
  proves no issues remain.
- Must NOT claim a populated issue store or frozen membership is complete.
- Must NOT claim a trusted finding bridge proves detector/scanner completeness, finding narrative truth, correct
  risk severity in the real world, or universal defect absence.
- Must NOT relabel connector-observed security execution as UAID system-executed; the scanner ran in CI and UAID
  observed its artifact.
- Must NOT claim PM `connector_verified` proves UAID issue category, severity, blocker status, release scope, or
  completeness. It proves the external facts the connector observed only.
- Must NOT claim a registered Slice-42 reviewer report has trusted content; its verdict/lists remain REPORTED.
- Must NOT claim one-finding/one-issue prevents semantic duplicates across runs, commits, tools, or fingerprints.
- Must NOT silently merge recurrent findings, reopen terminal issues, or auto-close either lifecycle.
- Must NOT let resolving/accepting/superseding one store mutate or authorize a transition in the other.
- Must NOT auto-bind a bridged issue to a frozen candidate or weaken freeze-locked membership.
- Must NOT claim `risk_acceptance_records.release_id` references candidate UUID; the ruled referent is the
  per-project `release_ref` string.
- Must NOT claim a `NOT VALID` FK validates history. Legacy unmatched rows remain explicitly untrusted.
- Must NOT claim the local `app_test` row observation represents production or every deployment.
- Must NOT claim a release FK verifies approver authority, approval-matrix membership, a human signature, risk
  reasoning, compensating controls, or evidence quality.
- Must NOT claim `request_authenticated` is a human signature; it remains key-custody evidence only.
- Must NOT allow a risk acceptance for release A to satisfy an issue under release B.
- Must NOT weaken any Slice-22/23/24/25/27/44/45 guard, hard-refusal rule, RLS policy, append-only trigger, or
  lifecycle invariant.
- Must NOT copy or audit finding/issue/risk/review/PM prose, fingerprints, repo/commit, raw artifacts, corpora,
  prompts, responses, credentials, secrets, signer lists, or arbitrary JSON.
- Must NOT claim gate #7 is PASS-capable in Slice 47. Every branch remains `insufficient_evidence` pending the
  Slice-50 release verdict/completeness design.
- Must NOT claim Slice 47 implements reviewer QA (Slice 48), evidence pack (Slice 49), release verdict (Slice 50),
  production preapproval, deployment, or go-live.
- Must NOT claim readiness changes; `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- Must NOT claim improved gate #7 evidence makes A5 satisfied or authorizes production. Go-live remains hard-false.

## 12. Definition of done for the eventual implementation — not this plan

After explicit plan approval and all coordinator rulings: every trusted bridge issue has one immutable exact
source-finding attachment and code/DB-derived category, severity, blocker semantics, source, and safe summary;
manual/PM/review evidence remains honestly weaker; one finding row cannot create two issues; finding and issue
lifecycles remain independent; new risk-acceptance release IDs are same-tenant/project FK-pinned to the ruled
candidate namespace and exact bound issue, while legacy rows remain visibly unvalidated under the selected
strategy; every prior risk/issue/finding/candidate guard remains intact and direct SQL cannot forge provenance,
binding, acceptance, or lifecycle state; audit is safe-metadata-only; gate #7 follows the ruled no-PASS ladder
under `slice47.v1`; all other gates and readiness `slice20.v1` are unchanged; `a5_satisfied` and go-live remain
false; full verification and migration round trip are green.

**Reviewer request:** APPROVE or REJECT this plan-only design. On APPROVE, the coordinator must rule OD-47-1
through OD-47-8 before any implementation begins.
