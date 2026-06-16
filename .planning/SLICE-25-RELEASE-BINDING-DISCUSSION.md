# Slice 25 — Release candidate / release-binding store — Discussion v0

**Status:** OPEN — awaiting coordinator rulings on D-RB-1..8 before any PLAN. No branch, no migration,
no code until PLAN approval.
**Base:** `main` @ `4c6c1f4` (clean; only the intentional `.planning/HANDOFF.json` drift).
**Persona:** senior release-governance / delivery-platform + Postgres-security architect.
**Goal:** lock the release-candidate identity, lifecycle, binding model, completeness boundary, and the
conservative A5 gate-#7 hook for a **deterministic, tenant-owned release-candidate / release-binding
store** — the *release-binding* half of what gate #7 is missing. It creates the deterministic
release-candidate namespace that can **later** become the authoritative referent for Slice-22
`risk_acceptance_records.release_id` and future evidence packs, and lets "remaining open issues
**for this release**" be scoped. **This slice does not yet FK or validate
`risk_acceptance_records.release_id`** — and it never asserts issue completeness, approves a release,
or enables go-live.

Provenance (Sanad): every shape/rule claim cites a spec line or a source file; inferences are
labelled **(inference)**.

---

## 1. What the spec requires / enables

- **Appendix B gate #7 (spec:2991):** A5 needs "any remaining open issues have approved
  risk-acceptance records." Slice 24 left this `insufficient_evidence:no_issue_provenance_or_release_binding`
  (`app/release/production_autonomy.py`) — **two** missing halves: (a) issue *provenance/completeness*,
  (b) *release binding* (which issues belong to this release). **This slice addresses (b).**
- **§24.1 go-live gate (spec:2266):** "remaining open issues are either non-blocking or covered by
  explicit risk-acceptance records" — "remaining" is inherently **per-release**; without a release
  entity it is unscoped.
- **§24.1 limited-scope release (spec:2256):** "intake_readiness >= R5 **or approved limited-scope
  release**" — a release is a first-class unit; approval is **out of scope** here.
- **§27.10 `risk_acceptance_record` (spec:2753-2767):** carries **`release_id: string`** +
  `issue_id`. The Slice-22 store already **requires `release_id`** as a free, unverified string
  (`app/release/risk_acceptance.py:45-58`). A `release_candidates` row creates the namespace that can
  **later** become the authoritative referent for that `release_id` (mirroring how Slice 24 gave
  `issue_id` a referent) — **but this slice does not yet FK or validate it** (D-RB-8).
- **§27.11 `evidence_pack_schema` (spec:2776-2782):** requires **`release_id`** + `scope` — the
  evidence pack (future) is **release-scoped**, so a release entity is the natural anchor.
- **spec:2145:** "production release candidate is created" is a defined lifecycle event (triggers
  requalification).
- **§24.3 release verdicts (spec:2336-2338):** `passed` / `passed_with_limitations` /
  `failed_blocking_issue` — **out of scope** this slice (no verdict computation).
- **Phase 6 (spec:2504) + Release Manager Agent (spec:977):** full release management
  (approval/deploy/rollback) is Phase 6 — Slice 25 builds only the deterministic *store* primitive.

## 2. The honest dependency reality (why gate #7 still won't pass)

A release-binding store lets us enumerate "the issues **we bound** to release R." It does **not**
prove that set is **complete** — issues are produced by reviewers/CI/verifiers that **do not run**
(Phase 3/5). **(inference)** So even a frozen release whose every bound issue is resolved/accepted
cannot prove "no other open issue exists." Therefore gate #7 **stays `insufficient_evidence` and never
passes** this slice. What changes: with a frozen release present, the *release-binding* half is
satisfied, so the reason can **narrow** from `no_issue_provenance_or_release_binding` →
`no_issue_provenance` (still failing, more precise). Honest, fail-closed.

## 3. Decisions to resolve

### D-RB-1 — Naming
**Recommend:** `release_candidates` + append-only `release_candidate_events` +
`release_candidate_issue_bindings`. *Justification:* continues the `release_` evidence-store family
(`release_findings`, `release_issues`); "candidate" matches spec:2145 and keeps it distinct from a
future approved/deployed "release". *(Confirm names.)*

### D-RB-2 — Release identity (minimal fields)
**Recommend** `release_candidates`: `id, tenant_id, project_id, release_ref` (human label, e.g.
`REL-2026-06-15-001`, unique per project — the **future** `release_id` referent namespace, not yet
enforced this slice), `title` (short, optional),
`status`, `frozen_at` (nullable; set on freeze), `created_at`, `updated_at`. **No** approval/deploy/
verdict/go-live columns. Constraints: `UNIQUE(tenant_id, project_id, release_ref)` (the `release_id`
namespace) **and** `UNIQUE(id, project_id, tenant_id)` — the latter is the composite-FK target for the
binding table (D-RB-7). *(Confirm fields + both unique constraints.)*

### D-RB-3 — Lifecycle
**Recommend** states **`draft` / `frozen` / `superseded` / `canceled`**; one-way transitions:
- `draft → frozen` (locks membership; sets `frozen_at`), `draft → canceled`;
- `frozen → superseded` (replaced by a newer candidate), `frozen → canceled`;
- `superseded`/`canceled` terminal. **No approval/go-live state.** DB-guarded + append-only
  `release_candidate_events`. *(Confirm the transition set.)*

### D-RB-4 — Binding model (the crux)
**Recommend (append-only, freeze-locked):**
- `release_candidate_issue_bindings` rows link a `release_candidate` to a `release_issues` row
  (composite FKs pinning both to the **same tenant+project**). **Append-only**; a binding may be
  added **only while the candidate is `draft`**; once `frozen`, the membership set is **immutable**
  (no add/remove). **No unbinding** — a wrong draft set is fixed by `canceling` the candidate and
  creating a new one (keeps it deterministic + append-only).
- **This slice binds *issues only*** (the gate-#7 concern). Binding *findings* (Slice 23) and
  *risk-acceptance records* (Slice 22) to a release is **deferred** to a later slice.
*(Rulings: (a) issue-only bindings now? (b) append-only with no unbind — or allow draft remove? (c)
freeze locks membership.)*

### D-RB-5 — Completeness claim (honesty boundary)
**Ruling to lock:** a release candidate + its bindings represent a **known, declared** issue set for
the release — it **must not** be read as "all issues are known." No field/flag may imply completeness.
Gate #7 stays `insufficient_evidence` (§2). *(Confirm: no completeness assertion anywhere.)*

### D-RB-6 — A5 gate-#7 hook (conservative)
**Recommend:** when ≥1 `frozen` release candidate exists for the project, gate #7 reason **narrows**
`no_issue_provenance_or_release_binding` → **`no_issue_provenance`** (release-binding half satisfied);
otherwise it stays the full reason. **Either way `insufficient_evidence` — never passes.**
- **Latest frozen candidate** = deterministic ordering **`frozen_at DESC, created_at DESC, id DESC`**.
- **`context` keys (safe metadata only — no `title`/prose):** `frozen_release_candidate_count`; and
  for the latest frozen candidate `latest_frozen_release_candidate_id`, `latest_frozen_release_ref`,
  `bound_open_issue_count`, `bound_open_blocking_issue_count`,
  `bound_open_unaccepted_blocking_issue_count`. Keep the existing Slice-24 counts +
  `active_risk_acceptance_count`. (`release_ref` is a human label/identifier, not prose — safe;
  `title` is **excluded**.)
- `production_autonomy` `ruleset_version` → **`slice25.v1`**.
*(Rulings: (a) narrow-the-reason vs keep-and-add-context; (b) latest-frozen scopes the context, ordered
as above; (c) gate #7 must NOT pass.)*

### D-RB-7 — Persistence / DB guard / migration / audit
- `release_candidates` (tenant-owned): RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, **no DELETE**; status
  CHECK; `UNIQUE(tenant_id, project_id, release_ref)` + `UNIQUE(id, project_id, tenant_id)` (binding
  FK target); composite FK `(project_id, tenant_id) → projects`. **DB guard:** INSERT (status=draft,
  `frozen_at` NULL); per-transition mutability (only `status`/`frozen_at`/`updated_at` change;
  identity immutable); one-way lifecycle; `frozen_at` set **iff** entering `frozen`; no DELETE/TRUNCATE.
- `release_candidate_issue_bindings` (tenant-owned, **append-only**, carries `tenant_id` +
  `project_id`): RLS; SELECT/INSERT only. **FK shape (Option A — additive, no `release_issues`
  mutation):**
  - `(release_candidate_id, project_id, tenant_id) → release_candidates(id, project_id, tenant_id)`
    (uses the new `UNIQUE(id, project_id, tenant_id)` from D-RB-2);
  - `(release_issue_id, tenant_id) → release_issues(id, tenant_id)` (uses the **existing**
    `UNIQUE(id, tenant_id)` — no change to `release_issues`).
  - `UNIQUE(tenant_id, release_candidate_id, release_issue_id)` (no dup binding).
  - **DB trigger on INSERT** verifies (a) the referenced `release_issues.project_id == NEW.project_id`
    (project match the FK to `release_issues` alone can't enforce) **and** (b) the parent candidate is
    **`draft`** (freeze-locks membership). No UPDATE/DELETE/TRUNCATE.
- append-only `release_candidate_events` (SELECT/INSERT only; block triggers).
- One additive migration **`0024_release_candidates.py`** (no change to existing tables — in
  particular **no retro-FK** onto `risk_acceptance_records.release_id`, which stays a free string this
  slice; see D-RB-8).
- **Audit safe-metadata only** (ids / release_ref / status / counts — never `title`/prose), mirroring
  the Slice-23/24 repos.
*(Confirm shape + migration number + the freeze-lock-via-trigger approach.)*

### D-RB-8 — Scope boundaries
- **`risk_acceptance_records.release_id` stays a free string** this slice (no retro-FK / table change);
  wiring it to `release_candidates` is a later slice. **(inference: avoids mutating a prior store.)**
- **Out of scope:** release **approval**, deploy authorization, request-authenticated pre-approval,
  scanner/reviewer **issue provenance** (completeness), §24.3 **release verdicts**, evidence pack,
  findings/risk-acceptance↔release binding, go-live, LLM, HTTP API.
*(Confirm the boundary.)*

## 4. Coordinator rulings needed before a PLAN
- **D-RB-1** table names.
- **D-RB-2** release-candidate fields + `release_ref` uniqueness.
- **D-RB-3** lifecycle states + one-way transitions (no approval/go-live state).
- **D-RB-4** binding model: issue-only now, append-only + freeze-locked, no-unbind (confirm).
- **D-RB-5** completeness boundary — no field may imply "all issues known".
- **D-RB-6** conservative A5 hook: narrow reason → `no_issue_provenance` when a frozen release exists,
  context counts, `ruleset_version` → `slice25.v1`, gate #7 never passes.
- **D-RB-7** persistence + DB guard + freeze-lock trigger + additive migration `0024` + audit
  safe-metadata.
- **D-RB-8** scope (risk-acceptance `release_id` stays free string; verdicts/approval/provenance out).

## 5. Recommendation
Build the deterministic, tenant-owned **release-candidate / release-binding store**
(`release_candidates` + append-only `release_candidate_events` + append-only, freeze-locked
`release_candidate_issue_bindings`; RLS, no-DELETE, DB-guarded lifecycle) with a minimal release
identity, `draft→frozen→{superseded,canceled}` lifecycle, **issue-only** freeze-locked bindings, an
explicit **no-completeness** boundary, and a **conservative A5 gate-#7 hook** that **narrows** the
reason to `insufficient_evidence:no_issue_provenance` once a frozen release exists but **never
passes**. Gate #7 gets its *release-binding* half with **no approval, no provenance, no go-live**.
**Pausing for rulings on D-RB-1..8 before any PLAN.**
