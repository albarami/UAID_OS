# Slice 42 — Task contracts + maker-checker-verifier workflow + reviewer reports (§13.1-13.3/§27.2/§12.3) — PLAN v3

**Status:** MERGED — historical record. Implemented via PR #73 (commit `c7f245e`); this v3 plan is retained as the design rationale for Slice 42. Merge status was recorded on `main` by commit `c5557ca`.

> **Revision log — v2 → v3:**
> - **V2-B1 — status vocabulary invariant fixed.** `draft`, `canceled`, `superseded` are NOT §12.3 columns
>   (verified: `app/release/pm_issues.py:22-40` `_SPEC_COLUMNS` lacks all three). v3 models them explicitly:
>   **`INTERNAL_STATUSES = ("draft",)`** (internal pre-board assembly status) and
>   **`TERMINAL_STATUSES = ("canceled", "superseded")`** (lifecycle terminals, the
>   `migrations/versions/0024_release_candidates.py` house pattern — not board columns). The invariant (and
>   its pure test) becomes **`CONTRACT_STATUSES ⊆ _SPEC_COLUMNS ∪ TERMINAL_STATUSES ∪ INTERNAL_STATUSES`**,
>   and D-42-5 no longer claims all names come from §12.3 — only the five BOARD-named statuses do
>   (`ready_for_development`, `in_progress`, `specialist_review`, `changes_requested`, `done`).
> - **V2-B2 — `can_merge` bound precisely: a DB-GENERATED column, never caller-writable.**
>   `can_merge BOOLEAN GENERATED ALWAYS AS (verdict = 'approved') STORED` via `sa.Computed(...,
>   persisted=True)` — the exact Slice-40 mechanism (`migrations/versions/0039_qualification_eval.py:232-235`,
>   `app/models/qualification_run.py:100-103`). It is NOT an input anywhere (the pure validator takes no
>   `can_merge`; the repo never writes it); a direct-SQL INSERT that supplies it fails at the DB
>   ("cannot insert a non-DEFAULT value into a generated column" — tested). The §13.3 verdict READ shape
>   still exposes it (stored, for the S49 evidence-pack inputs). The v2 "DB-derived-equal … CHECK" wording
>   (validate ≠ derive) is gone.
> - **Cleanup (requested).** The two unchanged rulesets are now stated separately: the A5
>   production-autonomy ruleset stays **`slice31.v1`** (`app/release/production_autonomy.py:51`) and the
>   readiness ruleset stays **`slice20.v1`** (`app/intake/readiness.py:45`).

> **Revision log — v1 → v2 (fixed, unchanged in v3):** B1 done-gate = per-REGISTRATION latest-approved
> (option (b)); B2 terminals explicit; B3 `task_contract_events` fully specified; B4 citations corrected.

> **Persona.** Senior agent-platform / delivery-governance backend architect (Sanad + security-reviewer §2.2 hats).
> **Provenance (Sanad — spec + verified recon):** §2.2 (`spec:151-160`; multiple reviewers for high risk
> `spec:153`) — "the platform decides"; §12.3 (`spec:1184-1207`) board workflow + **`spec:1207` "Builder agents
> cannot move their own work to Done"**; §13.1 (`spec:1230-1236`) the 3 review layers; §13.2 (`spec:1238-1272`)
> task contract (4 reviewers in the example, `spec:1265-1270`); §13.3 (`spec:1274-1296`) structured verdicts
> (`can_merge`/`failed_criteria`/`suspected_shortcuts`/`required_changes`); §27.2 (`spec:2546-2566`)
> `task_contract.json` (risk enum `spec:2563`); `spec:1139` broker `forbidden_conditions:"no_task_contract"`
> (future broker consumption — NOT wired this slice). Roadmap `.planning/GO-LIVE-END-TO-END-ROADMAP.md:385-395`
> (its "Migration `0040`" at `:390` is the known +1 drift — Slice 41 took `0040`; **Slice 42 = migration
> `0041`**). Recon (verified): NO task-contract/review/verdict store exists (`app/review/` absent; the only
> hits are `app/release/pr_evidence.py:39` = the §12.4 PR-section **presence flag** and
> `app/intake/generator.py:33` = the §6.3 **non-binding generated-draft type** — both distinct concerns).
> Reuse: §12.3 column vocabulary (`app/release/pm_issues.py:22-40` `_SPEC_COLUMNS`); `agent_instances`
> composite UNIQUE (`app/models/agent_instance.py:69-72`); the actual-blueprint self-review guard pattern
> (`migrations/versions/0038_agent_realization.py:168-192`); `intake_artifacts` composite UNIQUE
> `uq_intake_artifacts_id_project_tenant` (`app/models/intake_artifact.py:69-71`) + the Slice-37 FK precedent
> (`app/models/semantic_contradiction.py:45-53`); the Slice-41 non-blank bounds pattern
> (`migrations/versions/0040_agent_failure_events.py:45-59`); the Slice-40 GENERATED-column mechanism
> (`migrations/versions/0039_qualification_eval.py:232-235`, `app/models/qualification_run.py:100-103`);
> broker known-tool check — lazy-import pattern `app/agents/factory.py:41-57`, `get_contract` itself
> `app/tools/registry.py:104-105`; factory caps `app/agents/factory.py:27-28`; §9.5.1 `ARCHETYPES`
> (`app/agents/registry.py:37-51`); `WorkUnit` (`app/agents/skills.py:89-96` — stays a DECLARED input;
> deriving WorkUnits from contracts is NOT wired).

---

## 0. The defining honesty constraint (the crux)
**No agent execution exists, so Slice 42 RUNS no review.** It is the deterministic CONTRACT + VERDICT-RECORD +
GATE layer: (a) a §27.2-shaped **task contract** whose spine references are **FK-PROVEN** (requirements/ACs/
oracles resolve to same-project `intake_artifacts` of the right kind) and whose builder/reviewers are **real
same-project `agent_instances`** with the §2.2 **blueprint-distinctness DB guard**; (b) **REPORTED** §13.3
reviewer verdicts — content `caller_supplied_unverified` (the Slice-41 B1 provenance model; reviewer QA = S48,
shortcut detection = S45) but the reporter's **registration is FK-proven** (a report binds to the exact
(contract, reviewer-instance, layer) registration — the Slice-40 exact-subject lesson) and `can_merge` is
**DB-GENERATED from the verdict, never caller-writable**; (c) the §12.3 done-rule enforced **STRUCTURALLY**:
`done` is unreachable unless **every registered reviewer's own latest verdict is `approved`** across all 3
covered §13.1 layers, and every registered reviewer is blueprint-distinct from the builder — so a builder
cannot approve its own work into Done, and no reviewer can be outvoted-by-recency, **by construction** (the
mover label itself stays an UNTRUSTED string — stated, not overclaimed). An approved verdict is a **recorded
decision, never quality/acceptance/oracle proof** (S43/S46). Executes nothing.

## 1. Scope & non-goals
- **Scope.** (A) Tenant-owned `task_contracts` (§27.2 shape; content frozen at `draft→ready_for_development`)
  + append-only children: `task_contract_artifact_links` (FK-proven spine Sanad), `task_contract_reviewers`
  (FK-proven §2.2 reviewer registry, 3-layer), `task_contract_events` (transition trail, §5.5). (B) Append-only,
  immutable `review_reports` (§13.3 verdict shape, provenance-backed, registration-FK-bound, GENERATED
  `can_merge`). (C) Pure `app/review/task_contracts.py` (shape/bounds validators) + `app/review/workflow.py`
  (lifecycle + the done-gate decision). (D) Repos `app/repositories/task_contracts.py` +
  `app/repositories/review_reports.py`. (E) Migration `0041` (5 additive tables). (F) `tests/test_task_contracts.py`.
- **Non-goals.** NO review execution / LLM / agent run; NO oracle execution (S43), shortcut DETECTION (S45 —
  `suspected_shortcuts` strings are recorded verbatim, never derived), acceptance verification (S46), reviewer
  QA/adversarial sampling (S48), evidence pack (S49); NO full §12.3 board/PM sync (statuses are the contract's
  own gate-axis subset; `pm_issue_mappings` untouched); NO broker/`spec:1139` wiring, NO runtime/workflow-engine
  wiring, NO HTTP endpoint, NO generator-draft promotion (`app/intake/generator.py:33` drafts stay non-binding);
  NO `app/release/production_autonomy.py` / `app/intake/readiness.py` change (bit-stable; **the A5 ruleset
  stays `slice31.v1` — `app/release/production_autonomy.py:51`; the readiness ruleset stays `slice20.v1` —
  `app/intake/readiness.py:45`**); go-live false.

## 2. The honesty model in one line
Slice 42 records **who must build, who must check (FK-proven, §2.2-distinct), against which FK-proven spine
targets, and what EACH checker REPORTED** — and enforces "not Done until every registered checker's own latest
verdict approves" as a **DB-guarded structural gate**; it never performs, verifies, or authorizes the work.

## 3. BOUND decisions
- **D-42-1 — Deterministic, store/gate-only.** No LLM, no execution; verdicts are recorded REPORTS.
- **D-42-2 — §27.2 shape with FK-proven Sanad where referents exist.** `source_requirements`/
  `acceptance_criteria`/`test_oracles` → `task_contract_artifact_links` rows, composite-FK to `intake_artifacts`
  (`app/models/intake_artifact.py:69-71`; precedent `app/models/semantic_contradiction.py:45-53`) + a
  BEFORE-INSERT **kind guard** (`link_kind→spine kind`: `source_requirement→requirement`,
  `acceptance_criterion→acceptance_criterion`, `test_oracle→test_oracle` — the FK proves existence, the guard
  proves kind; Slice-37 B7). Free-text lists (`must_have`/`must_not_do`/`required_evidence`/
  `definition_of_done`) = bounded, **non-blank** JSONB string arrays (Slice-41 lesson) with DB array guards;
  `allowed_tools`/`forbidden_tools` = KNOWN broker-registry tools (`get_contract` not None —
  `app/tools/registry.py:104-105`, lazy-import pattern `app/agents/factory.py:41-57`), **disjoint**, bounded.
- **D-42-3 — Builder + reviewers are real same-project instances; §2.2 is DB-proven.** `builder_instance_id` +
  each `task_contract_reviewers.reviewer_instance_id` composite-FK → `agent_instances`
  (`app/models/agent_instance.py:69-72`); a BEFORE-INSERT guard resolves each reviewer's ACTUAL blueprint
  (`instance→version→blueprint`, `migrations/versions/0038_agent_realization.py:168-192` pattern) and refuses
  `= builder's blueprint`. Layer ∈ the §13.1 3-set `{role_specific, cross_functional, acceptance}`.
  **Cardinality: multiple reviewers per layer are allowed** (`spec:153`, `spec:1265-1270`), each registration
  unique per `(contract, reviewer_instance, layer)`. **Honest:** blueprint-distinctness + layer coverage are
  proven; layer-ADEQUACY (the right archetype per layer) is NOT validated this slice (S38/S48).
- **D-42-4 — Reports are REPORTED, provenance-backed, immutable, registration-bound; `can_merge` is
  DB-GENERATED (V2-B2).** `verdict ∈ {approved, rejected_with_required_changes}` (§13.3);
  **`can_merge BOOLEAN GENERATED ALWAYS AS (verdict = 'approved') STORED`** (`sa.Computed(..., persisted=True)`
  — the Slice-40 mechanism, `migrations/versions/0039_qualification_eval.py:232-235`) — **not an input
  anywhere**: the pure validator takes no `can_merge`, the repo never writes it, and a direct-SQL INSERT that
  supplies it is refused by Postgres (non-DEFAULT into a generated column); reads expose it (§13.3 shape,
  future S49 input). `approved ⇒ failed_criteria/suspected_shortcuts/required_changes ALL empty` (a suspected
  shortcut is not an approval — §2.1/§13.4); `rejected_with_required_changes ⇒ failed_criteria ≥1 AND
  required_changes ≥1` (`spec:1279-1295`); `summary` required non-blank bounded; required `source` +
  `source_provenance` CHECK-locked `'caller_supplied_unverified'` (Slice-41 B1). Composite FK
  `(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)` → `task_contract_reviewers` — a
  report from an unregistered reviewer/wrong layer is FK-impossible (Slice-40 B7). Recordable only while the
  contract is in `{in_progress, specialist_review, changes_requested}` (guard).
- **D-42-5 — Lifecycle = board-named subset + internal + terminals (V2-B1).** `CONTRACT_STATUSES =
  INTERNAL_STATUSES ∪ {ready_for_development, in_progress, specialist_review, changes_requested, done} ∪
  TERMINAL_STATUSES`, where **only the five middle statuses take their names from §12.3**
  (`app/release/pm_issues.py:22-40`; the other §12.3 columns belong to the S43-49 subsystems — modeling them
  now would be fake stages), **`INTERNAL_STATUSES = ("draft",)`** is the pre-board assembly status (not a
  §12.3 column), and **`TERMINAL_STATUSES = ("canceled", "superseded")`** are lifecycle terminals (the
  `migrations/versions/0024_release_candidates.py` pattern; not §12.3 columns) — final, no outgoing. **`done`
  is NOT terminal: exactly one outgoing transition `done→superseded`; `done→canceled` and any reopen are
  refused.** Transitions (DB-guarded): `draft→ready_for_development` (**freeze**: ≥1 `source_requirement`
  link + all 3 layers covered; content/links/reviewers immutable after), `ready_for_development→in_progress`,
  `in_progress→specialist_review`, `specialist_review→changes_requested`, `changes_requested→in_progress`
  (rework loop), `specialist_review→done` (**DONE-GATE** — §5.1), `{draft, ready_for_development, in_progress,
  specialist_review, changes_requested}→canceled`, `done→superseded`. Same-status no-op refused.
- **D-42-6 — Compute-on-read review status.** Pure `evaluate_done_gate(per-REGISTRATION latest verdicts) →
  DoneGateDecision` (frozen; `ruleset_version="slice42.v1"`) + repo `review_status(contract_id)` — no writes
  (the Slice-21/41 decision pattern); the DB done-gate trigger is the authoritative backstop of the same rule.
- **D-42-7 — Every user text field bounded + non-blank at BOTH layers** (validator `.strip()` + DB
  `char_length`/`btrim` over the `str.strip()` set — `migrations/versions/0040_agent_failure_events.py:45-59`),
  incl. every JSONB list item and the event `actor` label.
- **D-42-8 — Store/infra-only; bit-stable.** `app/release/production_autonomy.py` / `app/intake/readiness.py`
  UNTOUCHED (`before==after` + readiness-unchanged tests; A5 ruleset `slice31.v1` —
  `app/release/production_autonomy.py:51`; readiness ruleset `slice20.v1` — `app/intake/readiness.py:45`);
  audit safe-metadata only (ids/status/verdict/layer/counts — NEVER title/description/must_*/summary/criteria/
  changes prose); migration `0041` purely additive; go-live false.

## 4. Pure — `app/review/task_contracts.py` + `app/review/workflow.py`
- `task_contracts.py`: `RISK_LEVELS=("low","medium","high","critical")` (`spec:2563`);
  `REVIEW_LAYERS=("role_specific","cross_functional","acceptance")` (§13.1); `ARTIFACT_LINK_KINDS` (the D-42-2
  3-map); bounds `MAX_TASK_REF=64` (shape `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`), `MAX_TITLE=200`,
  `MAX_DESCRIPTION=4000`, `MAX_LIST_ITEMS=32`, `MAX_ITEM_CHARS=500`, `MAX_TOOLS=64`, `MAX_REVIEWERS=16`
  (factory parity `app/agents/factory.py:27-28`); `validate_new_contract(...)` fail-closed (enum/shape/bounds/
  non-blank per item/list caps/known tools/disjoint allowed∩forbidden); `validate_artifact_link(link_kind)`.
- `workflow.py`: **`INTERNAL_STATUSES=("draft",)`**, `BOARD_STATUSES=("ready_for_development","in_progress",
  "specialist_review","changes_requested","done")`, **`TERMINAL_STATUSES=("canceled","superseded")`**,
  `CONTRACT_STATUSES = INTERNAL_STATUSES + BOARD_STATUSES + TERMINAL_STATUSES` (the V2-B1 invariant:
  `BOARD_STATUSES ⊆ _SPEC_COLUMNS`; `CONTRACT_STATUSES ⊆ _SPEC_COLUMNS ∪ TERMINAL_STATUSES ∪
  INTERNAL_STATUSES`); `validate_transition` (the D-42-5 matrix);
  `VERDICTS=("approved","rejected_with_required_changes")`; `REPORTABLE_STATUSES`; `MAX_SUMMARY=2000`;
  `validate_review_report(...)` — **no `can_merge` parameter (V2-B2: derived, never input)** — (verdict enum,
  approved⇒empty-lists, rejected⇒failed+changes non-empty, bounded non-blank summary/source/items, provenance
  ∈ `("caller_supplied_unverified",)`).
  **`evaluate_done_gate`:** input = the contract's registrations with each registration's latest verdict —
  `Sequence[RegistrationView(layer, reviewer_ref, latest_verdict: str | None)]`; output `DoneGateDecision`
  (frozen + `to_dict()`): `eligible` / `missing_layers` (layers with zero registrations — impossible
  post-freeze, handled for pure-fn totality) / `pending_registrations` (no report yet) /
  `rejected_registrations` (latest not `approved`) / `ruleset_version="slice42.v1"`.
  `eligible ⇔ missing_layers = ∅ AND pending_registrations = ∅ AND rejected_registrations = ∅`.

## 5. Storage + migration `0041` (5 additive tables; RLS ENABLE+FORCE + `tenant_isolation` on all)
- **5.1 `task_contracts`** (grants SELECT/INSERT/UPDATE, no DELETE): `id`/`tenant_id`/`project_id`/`task_ref`/
  `title`/`description`/4 free-text JSONB lists/`allowed_tools`/`forbidden_tools` (JSONB)/`risk_level`/
  `builder_instance_id`/`status`/`created_at`/`updated_at`. CHECKs: enums + `char_length`+`btrim` on
  `task_ref`/`title`/`description`; `UNIQUE(tenant_id, project_id, task_ref)`; `UNIQUE(id, tenant_id)` +
  `UNIQUE(id, project_id, tenant_id)` (FK targets); composite FKs `project_tenant` +
  `(builder_instance_id, project_id, tenant_id)→agent_instances`. Guard trigger: INSERT ⇒ `status='draft'`;
  JSONB array shapes (string items, bounded, non-blank, caps, tools disjoint) on INSERT + draft-UPDATE;
  content/identity immutable once not-draft (then only `status`/`updated_at` mutable); the D-42-5 transition
  matrix incl. the **freeze prerequisites** (draft→ready: ≥1 `source_requirement` link + 3-layer coverage) and
  the **DONE-GATE** on `specialist_review→done` — in-trigger query shape:
  `SELECT 1 FROM task_contract_reviewers r LEFT JOIN LATERAL (SELECT p.verdict FROM review_reports p WHERE
  p.task_contract_id = r.task_contract_id AND p.reviewer_instance_id = r.reviewer_instance_id AND p.layer =
  r.layer ORDER BY p.created_at DESC, p.id DESC LIMIT 1) latest ON true WHERE r.task_contract_id = NEW.id AND
  (latest.verdict IS NULL OR latest.verdict <> 'approved') LIMIT 1` — **IF FOUND ⇒ RAISE** (any registration
  pending or latest-rejected blocks `done`; 3-layer coverage was frozen in at `draft→ready`).
- **5.2 `task_contract_artifact_links`** (SELECT/INSERT only + block triggers): composite FKs →`task_contracts`
  and →`intake_artifacts` (`app/models/intake_artifact.py:69-71`); `link_kind` CHECK ∈3; BEFORE-INSERT guards:
  contract must be `draft` (freeze-lock, `migrations/versions/0024_release_candidates.py` pattern) + the
  artifact-kind match (D-42-2); `UNIQUE(task_contract_id, artifact_id, link_kind)`.
- **5.3 `task_contract_reviewers`** (SELECT/INSERT only + block triggers): composite FKs →`task_contracts` and
  `(reviewer_instance_id, project_id, tenant_id)→agent_instances`; `layer` CHECK ∈3; BEFORE-INSERT guards:
  contract `draft` + the §2.2 blueprint-distinctness (D-42-3); `UNIQUE(task_contract_id, reviewer_instance_id,
  layer)` + `UNIQUE(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)` (the report FK
  target).
- **5.4 `review_reports`** (SELECT/INSERT only + block triggers — immutable verdicts): composite FKs
  →`task_contracts` and `(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)`
  →`task_contract_reviewers` (registration-bound, D-42-4); **`can_merge` = `sa.Computed("verdict =
  'approved'", persisted=True)`** (GENERATED ALWAYS … STORED — never caller-writable, V2-B2); CHECKs: verdict
  enum; approved⇒`jsonb_array_length`=0 ×3; rejected⇒failed≥1 AND changes≥1; `summary`/`source`
  `char_length`+`btrim`; `source_provenance` locked; JSONB item guard trigger + the contract-status-window
  guard (D-42-4); index `(tenant_id, task_contract_id, layer, created_at)`.
- **5.5 `task_contract_events`.** Columns: `id` UUID PK `gen_random_uuid()`; `tenant_id` UUID NOT NULL
  FK→`tenants` RESTRICT; `project_id` UUID NOT NULL; `task_contract_id` UUID NOT NULL; `from_status` TEXT NULL
  (**NULL only for the creation event**; else CHECK ∈ `CONTRACT_STATUSES`); `to_status` TEXT NOT NULL CHECK ∈
  `CONTRACT_STATUSES`; `actor` TEXT NOT NULL (UNTRUSTED label — `char_length 1..200` + `btrim <> ''`);
  `created_at` timestamptz NOT NULL `clock_timestamp()`. Constraints: composite FK `(task_contract_id,
  project_id, tenant_id) → task_contracts(id, project_id, tenant_id)` RESTRICT (tenant/project-pinned);
  composite FK `(project_id, tenant_id) → projects` RESTRICT; CHECK `(from_status IS NULL) = (to_status =
  'draft')` (creation-event duality). Index `(tenant_id, task_contract_id, created_at)`. RLS ENABLE+FORCE +
  `tenant_isolation` (USING + WITH CHECK on the tenant GUC predicate); `REVOKE ALL FROM PUBLIC`; grants
  **SELECT, INSERT only** to `uaid_app`; append-only **block triggers** (`BEFORE UPDATE OR DELETE` row trigger
  + `BEFORE TRUNCATE` statement trigger, the `migrations/versions/0038_agent_realization.py:194-213` loop
  pattern). One row per creation + per transition, written by the repo in the same txn as the status change.

## 6. Repositories
- `TaskContractRepository` (`app/repositories/task_contracts.py`): `create` (draft; validates via pure;
  resolves the builder instance same-tenant — project derived from the instance, the
  `app/repositories/agent_failures.py` pattern; writes the creation event; audits safe-metadata),
  `add_artifact_link` (resolves the same-project artifact; pre-checks kind; FK/guard backstop), `add_reviewer`
  (repo-level §2.2 pre-check mirroring the DB guard), `submit_for_development`/`start`/`submit_for_review`/
  `request_changes`/`complete`/`cancel`/`supersede` (each: pure `validate_transition` → UPDATE (DB guard
  backstop) → event row → audit), `get`/`list_for_project`, `review_status` (compute-on-read D-42-6: loads
  registrations + each registration's latest report → pure `evaluate_done_gate`).
- `ReviewReportRepository` (`app/repositories/review_reports.py`): `record_report` (pure validation — **no
  `can_merge` accepted** → registration lookup (refuse unregistered) → INSERT → audit safe-metadata:
  contract/reviewer ids + layer + verdict + list COUNTS — never prose), `latest_by_registration`, `reports_for`.

## 7. Execution / enforcement — the honest boundary
The system never performs a review, never moves a board, never merges. The §12.3 done-rule and §2.2 are
enforced as **structural DB gates over recorded facts**; verdict CONTENT stays unverified until S45/S48. The
broker's `no_task_contract` forbidden-condition (`spec:1139`) is future wiring — **no broker change**.

## 8. A5 / readiness / tenancy / audit
**NONE — bit-stable** (`before==after` + readiness-level-unchanged tests; the A5 ruleset stays `slice31.v1` —
`app/release/production_autonomy.py:51` — and the readiness ruleset stays `slice20.v1` —
`app/intake/readiness.py:45`); RLS everywhere; composite FKs pin every child to tenant+project; audit
safe-metadata only. `review_reports` become S49 evidence-pack INPUTS later — no gate flips now; go-live false.

## 9. Tests — `tests/test_task_contracts.py`
- **Pure:** constants (**the V2-B1 invariant: `BOARD_STATUSES ⊆ _SPEC_COLUMNS` and `CONTRACT_STATUSES ⊆
  _SPEC_COLUMNS ∪ TERMINAL_STATUSES ∪ INTERNAL_STATUSES`, with `INTERNAL_STATUSES == ("draft",)` and
  `TERMINAL_STATUSES == ("canceled","superseded")` exact**; layers/verdicts; ruleset; bounds);
  `validate_new_contract` ok-at-caps + refusals (unknown tool, allowed∩forbidden overlap, bad risk,
  oversized/empty/**whitespace-only** title/description/task_ref/every-list-item, list-cap overflow);
  `validate_transition` full matrix (legal, illegal, same-status, **done→superseded OK, done→canceled refused,
  canceled/superseded no outgoing**); `validate_review_report` ok + refusals (bad verdict,
  approved-with-nonempty-lists, rejected-without-failed/changes, blank/whitespace summary/source, bad
  provenance, oversized items; **signature takes no `can_merge`**); `evaluate_done_gate` per-registration
  (all approved ⇒ eligible; a pending registration ⇒ not eligible; one registration's latest rejected while a
  DIFFERENT same-layer registration approved ⇒ NOT eligible; reject-then-approve by the SAME reviewer ⇒
  eligible; missing layer ⇒ not eligible; `to_dict`).
- **DB — contracts:** create-draft + creation event + audit-safe (leak probes: description/must_have item NOT
  in audit); JSONB guard refusals (non-array, non-string item, blank item, >32 items, tool overlap) via direct
  SQL; draft→ready freeze refusals (no requirement link / missing a layer) + success freezes (content UPDATE,
  link INSERT, reviewer INSERT all refused post-draft); cross-project builder-instance FK refusal; `task_ref`
  uniqueness.
- **DB — links/reviewers:** wrong-kind link refused (AC-link → requirement artifact); cross-project artifact
  FK refusal; §2.2 reviewer-blueprint=builder-blueprint refused (direct SQL AND repo); duplicate reviewer/link
  UNIQUE refusals.
- **DB — reports:** unregistered-reviewer / wrong-layer report FK-refused; report while draft/ready/done
  refused (window guard); **direct-SQL INSERT supplying `can_merge` refused (generated column — non-DEFAULT
  value error); an `approved` row reads back `can_merge=true`, a rejected row `false` (V2-B2)**;
  approved-with-lists, rejected-empty-lists, whitespace-summary, non-locked provenance all CHECK-refused;
  immutability (UPDATE/DELETE blocked) + `uaid_app` privilege-layer denial; RLS cross-tenant (contracts +
  reports + events).
- **DB — done-gate (§12.3/§2.2):** all registrations approved ⇒ `complete` OK + event row; a registration
  with NO report ⇒ refused; **two reviewers in one layer, A rejects then B approves ⇒ refused; A then
  re-approves (A's own latest approved) ⇒ OK**; `review_status` matches the DB outcome; the builder cannot be
  registered as any reviewer (§2.2 guard) — so no self-approval path to done.
- **DB — events:** creation row (`from_status` NULL ⇔ `to_status='draft'` CHECK, both directions) + one row
  per transition; composite-FK cross-project/tenant refusal; append-only (UPDATE/DELETE/TRUNCATE blocked) +
  privilege-layer denial; whitespace-only `actor` refused; RLS cross-tenant.
- **DB — bit-stable:** contracts+reports+transitions ⇒ `production_autonomy` `before==after` + readiness
  untouched.
- `make test` + fresh `make test-db` + alembic `0041` round-trip; CI green.

## 10. Must NOT claim
- That the system **performs/runs** any review, or that a verdict's CONTENT is verified (it is REPORTED,
  `caller_supplied_unverified`; only the reviewer's registration + §2.2 distinctness + the GENERATED
  `can_merge` derivation are DB-proven).
- That `approved`/`done` = **acceptance verification / oracle pass / shortcut-scanned / quality** (S43/S45/S46/S48).
- That the full §12.3 board is modeled or synced (only the five BOARD-named statuses are §12.3 columns;
  `draft`/`canceled`/`superseded` are internal/terminal, not board columns), or that the broker enforces
  `no_task_contract` (future).
- That the mover of a transition is a verified actor (labels UNTRUSTED; the done-gate is the structural rule).
- That A5/readiness/go-live changed (bit-stable; A5 ruleset `slice31.v1`, readiness ruleset `slice20.v1`).

## 11. Decisions — ALL BOUND (v3)
D-42-1…8 bound above (V2-B1 status vocabulary; V2-B2 GENERATED `can_merge`). Closest-call alternatives
(rejected): one-reviewer-per-layer (`UNIQUE(contract, layer)` — contradicts `spec:153`
multiple-reviewers-for-high-risk and the §13.2 4-reviewer example); per-LAYER latest-wins done-gate (the v1
B1 hole — lets recency bury an independent rejection); **`can_merge` computed-on-read-only (loses the stored
§13.3 row shape the S49 evidence pack will consume) and caller-supplied-but-DB-validated (weaker than the
house GENERATED pattern — a caller-writable derived value is the Slice-40 B3 anti-lesson)**; full §12.3
status set (fake stages without S43-49); JSON string refs instead of FK links (violates the FK-prove lesson,
Slice-37 B4/B8); auto-reopen on late rejection (auto-anything violates the decision-only house model; a
post-done rejection report is refused by the status window).

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A frozen-once-ready, §27.2-shaped, FK-Sanad task-contract store + FK-proven §2.2-distinct 3-layer reviewer
registry + immutable, provenance-backed, registration-bound §13.3 review reports (**GENERATED, never
caller-writable `can_merge`**) + the DB-guarded §12.3 done-gate (**every registration's own latest verdict
approved**) + fully-specified append-only event trail + compute-on-read `review_status` — executing nothing,
verifying no content, flipping no gate; `app/release/production_autonomy.py` / `app/intake/readiness.py`
untouched (rulesets `slice31.v1` / `slice20.v1`), bit-stable; migration `0041` round-trips; `make test` +
fresh `make test-db` + CI green. **No review execution, no LLM, no oracle/shortcut/acceptance subsystems, no
board sync, no broker wiring, no HTTP endpoint, no A5 flip.**

---
**Review note (v3):** Fixes **V2-B1** (status vocabulary: `INTERNAL_STATUSES=("draft",)` +
`TERMINAL_STATUSES=("canceled","superseded")` are NOT §12.3 columns; only the five BOARD statuses are; the
pure invariant + test corrected to `_SPEC_COLUMNS ∪ TERMINAL_STATUSES ∪ INTERNAL_STATUSES`) and **V2-B2**
(`can_merge` = `GENERATED ALWAYS AS (verdict='approved') STORED` via `sa.Computed(..., persisted=True)` —
the Slice-40 mechanism, never caller-writable, no validator/repo input, direct-SQL write DB-refused; the
"DB-derived-equal CHECK" wording is gone). Adds the requested ruleset cleanup (A5 `slice31.v1` @
`app/release/production_autonomy.py:51`; readiness `slice20.v1` @ `app/intake/readiness.py:45`). v1→v2 fixes
(per-registration done-gate, terminals, events spec, citations) carried unchanged. Version labels swept to
v3. Migration `0041` (roadmap `:390` `0040` = the known +1 drift); the roadmap's 2-table sketch expands to
**5 tables** so spine refs, reviewer registrations, and transitions are FK-proven append-only rows, not JSON
(Slice-37 B4/B8 + the event-trail house pattern). **No code until this plan is APPROVED.**
