# Slice 18 — R4 Readiness Rules — Discussion v0 (design decisions)

**Status:** RESOLVED — historical record. All five decisions (D-R4-1..5) ruled by the coordinator
and implemented in Slice 18 (see `.planning/SLICE-18-PLAN.md`). Outcome: D-R4-1 `spine_gaps==[]`;
D-R4-2 Broader (`integrations_and_external_systems` + `tool_access_manifest`, secrets excluded);
D-R4-3 monotonic staging + `STAGING_R4_NO_ENV_REASON`; D-R4-4 go-live false / cap R4 / no R5;
D-R4-5 `missing_r4_categories` + `missing_r4_test_coverage` + `ruleset_version="slice18.v1"`.
**Base:** `main` @ `aa64298` (clean).
**Goal of this doc:** resolve the 5 design decisions below, then draft PLAN v1.

---

## Grounding (spec + current code)

- **§4.3 R4** = "Most requirements, architecture, tests, and tools are available; **production
  authority incomplete**. → Build to staging, run tests, evidence pack, request production decisions."
- **§4.3 R5** = "Requirements, oracles, environments, secrets, authority, approvals, and go-live
  gates are complete."
- **§4.5 sample** (spec:437-438) shows `"readiness_level": "R3"` with `"can_build_to_staging": true`
  — the current behavior we must not regress.
- **Current code** (`app/intake/readiness.py`):
  - `READINESS_CAP = "R3"` (readiness.py:34); R4/R5 explicitly deferred (need gated engines).
  - Ladder: R0 (no requirements) → R1 (no valid req→AC chain) → R2 (≥1 valid chain) → R3 (R2 +
    the three §4.3 technical categories declared, `R3_TECHNICAL_CATEGORIES` = 05/11/14).
  - **`spine_gaps` is already computed exhaustively** (readiness.py:195-220): every requirement
    without an acceptance criterion, every AC without a test oracle, and both invalid-parent kinds
    (`acceptance_criterion_invalid_parent`, `test_oracle_invalid_parent`). The R2/R3 *level* only
    needs ≥1 valid chain — it does **not** require `spine_gaps == []`.
  - Staging facet (readiness.py:236-245): `can_build_to_staging = True` iff `level == "R3"` AND
    `environments_and_deployment_targets` declared; else False with a recorded reason.
  - `can_go_live_autonomously = False` always (readiness.py:263).
  - Slice 15 declarations already flow into `evaluate_readiness()` via `ReadinessRepository`
    (readiness.py:55-61); `declared = {d.category for d in declarations if d.status == "declared"}`.
  - `DECLARABLE_INTAKE_CATEGORIES` includes `tool_access_manifest` (18),
    `integrations_and_external_systems` (12), `secrets_and_credentials_manifest` (17),
    `environments_and_deployment_targets` (16). `GATED_ENGINE_CATEGORIES` =
    autonomy/approval/cost/**production_authority** (the R5 gate).

---

## D-R4-1 — What does "tests available" mean?

**Recommendation (deterministic, fail-closed):** R4 requires **`spine_gaps == []`** — i.e. zero
spine test-coverage gaps:
- every requirement has a valid acceptance criterion;
- every valid acceptance criterion has a valid test oracle;
- no invalid/wrong-kind parent chains anywhere in the requirement→AC→oracle spine.

**Why:** `spine_gaps` already encodes exactly these four conditions (readiness.py:195-220). R4 simply
adds the predicate "the spine has no gaps" on top of the R3 base. Fully deterministic, reuses
existing computation, no vague "most." A project can be R3 *with* gaps; R4 demands the gaps are gone.

**Surfaced as:** `missing_r4_test_coverage` = the blocking `spine_gaps` (refs + summaries) when
non-empty; empty list means the test-coverage precondition is met.

**Open sub-question for your ruling:** R4 = "*most* requirements" in prose, but the rule above
requires **full** chain coverage (every requirement). I recommend full coverage (stricter,
fail-closed, unambiguous) rather than a fractional threshold. Confirm, or specify a threshold.

---

## D-R4-2 — Which declared categories satisfy "tools available"?

| Option | Categories required | Note |
|---|---|---|
| Minimal | `tool_access_manifest` (18) | "approved tools, APIs, scopes, accounts" only |
| **Broader (recommended)** | `tool_access_manifest` (18) + `integrations_and_external_systems` (12) | the tools *and* the external systems they reach |
| Strict | Broader + `secrets_and_credentials_manifest` (17) | adds secrets-manifest presence |

**Recommendation: Broader (18 + 12).** §4.3 R4 says "tools … available"; the tool access manifest
plus the integrations/external-systems manifest together represent "tools available" without
reaching into R5 territory.

**Risk flag (per your note):** **secrets are named in the R5 definition**, so requiring
`secrets_and_credentials_manifest` for R4 would blur the R4/R5 boundary. If you choose Strict, it
must mean **reference-only manifest *presence*** (Slice 15 already stores only
`{manager, reference_name}`, never values) — i.e. "the manifest is declared," **not** "secrets are
ready/available." I recommend keeping secrets out of R4 to keep the boundary crisp; the §4.5 sample
even lists "secrets manifest" under `missing_for_go_live` (an R5 gap).

**Surfaced as:** `missing_r4_categories` = the chosen tools categories not yet `declared`.

---

## D-R4-3 — Staging behavior reconciliation

**Tension:** §4.3 associates "Build to staging" with R4, but Slice 16 already grants
`can_build_to_staging = true` at **R3 AND environments declared**, and the §4.5 sample shows exactly
that (R3 + staging true).

**Recommendation — preserve monotonic compatibility:**
- **Do not regress** the existing R3 + `environments_and_deployment_targets` → staging-true behavior.
- Extend the staging-true condition from `level == "R3"` to **`level in ("R3", "R4")`** AND
  `environments_and_deployment_targets` declared.
- R4 **must not** imply go-live (D-R4-4).

Net: R3+env and R4+env both yield `can_build_to_staging = true`; R4 without env declared →
`false` with a recorded reason. This keeps the §4.5 sample valid and aligns R4 with "build to staging."

---

## D-R4-4 — R5 boundary

**State explicitly (no ruling needed unless you object):**
- R4 keeps **`can_go_live_autonomously = false`** (unchanged, readiness.py:263).
- **Production authority remains incomplete by definition** (`production_authority` is a
  `GATED_ENGINE_CATEGORY`, not evaluated for completeness in this slice).
- **No** autonomy/approval/cost/production-authority gated-completeness logic.
- **No R5 logic** in this slice. R5 (oracles+environments+secrets+authority+approvals+go-live gates
  all complete) stays out of scope; `READINESS_CAP` becomes `"R4"`, not `"R5"`.

---

## D-R4-5 — Report shape

**Proposed deterministic additions to `ReadinessReport.to_dict()`:**
- `missing_r4_categories` — tools categories (per D-R4-2) not declared.
- `missing_r4_test_coverage` — blocking `spine_gaps` (refs+summaries) when test coverage incomplete.
- `readiness_cap` → **`"R4"`** (was `"R3"`).
- `readiness_cap_reason` → updated to explain R5 is out of scope (gated-engine completeness +
  go-live gates not implemented).
- `not_assessed_categories` → **shrinks**: the tools categories now consumed by the R4 rule move out
  of "not assessed" (and `_CONSUMED_CATEGORIES` / the `NOT_ASSESSED_CATEGORIES` invariant assertion
  at readiness.py:275 updated accordingly).
- `missing_for_go_live` → additionally lists `r4_category_not_declared:<category>` and
  `r4_test_coverage_gap:<ref>` entries (mirroring the existing `r3_category_not_declared:` pattern).
- `ruleset_version` → bump (e.g. `"slice18.v1"`).

**No migration expected** — `readiness_level` CHECK already allows `R0..R5` (model docstring +
migration 0015). No new table/column.

---

## Pause — coordinator rulings requested

Please rule on:
- **D-R4-1:** confirm "zero spine_gaps" (full chain coverage), or specify a threshold.
- **D-R4-2:** Minimal / **Broader (rec)** / Strict — and if Strict, confirm "reference-only presence."
- **D-R4-3:** confirm monotonic staging (R3 behavior preserved; R4+env → staging true).
- **D-R4-4:** confirm R5 boundary as stated.
- **D-R4-5:** confirm the report-shape additions (or adjust field names).

After your rulings I'll draft **PLAN v1 for Slice 18** (still no branch, no code).
