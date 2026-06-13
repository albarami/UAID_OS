# Slice 18 — R4 readiness rules (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice18-r4-readiness-rules` off `main` @ `aa64298`; pure evaluator change in
`app/intake/readiness.py` + tests + docs (no migration). Verification: `ruff` clean, `make test`
160, `make test-db` 236.
**Base:** `main` @ `aa64298` (clean).
**Design rulings:** see `.planning/SLICE-18-R4-DISCUSSION.md` (D-R4-1..5 all approved).

---

## 0. One-line summary

Lift the deterministic build-readiness auditor cap from **R3 → R4**: a project reaches **R4**
when it is R3 **and** (a) the requirement→AC→oracle spine has **zero gaps** and (b) the two R4
"tools" categories are declared. R4 never implies go-live. Pure-evaluator change; **no migration**,
no LLM, no new API (Slice 17's `/readiness` endpoint surfaces it for free).

---

## 1. Exact scope

In `app/intake/readiness.py` (`evaluate_readiness`, pure, no I/O), after the existing R3 step:

- **R4 lift (D-R4-1, D-R4-2):** `level` becomes `"R4"` iff `level == "R3"` **and**
  `spine_gaps == []` **and** both R4 tool categories are `declared`:
  - `R4_TOOL_CATEGORIES = ("integrations_and_external_systems", "tool_access_manifest")` — in
    canonical §4.2 file order (12 before 18), matching the existing readiness constants for
    deterministic report output. Secrets **excluded** — kept an R5 concern (D-R4-2).
  - `spine_gaps` is already computed exhaustively before the ladder (requirement-without-AC,
    valid-AC-without-oracle, and both invalid-parent kinds) — R4 reuses that exact list.
- **Staging, monotonic (D-R4-3):** extend the staging-true gate from `level == "R3"` to
  `level in ("R3", "R4")` AND `environments_and_deployment_targets` declared. R3+env and R4+env →
  `can_build_to_staging = True`; R4 without env → `False` with an explicit reason; below R3 unchanged.
- **Go-live (D-R4-4):** `can_go_live_autonomously` stays hard-`False` (unchanged).
- **Cap + report (D-R4-5):** `READINESS_CAP = "R4"`; updated `READINESS_CAP_REASON` (R5 needs
  gated-engine completeness + go-live gates, out of scope); `ruleset_version = "slice18.v1"`; new
  report fields `missing_r4_categories`, `missing_r4_test_coverage`; `not_assessed_categories`
  shrinks by exactly the two R4 tool categories.

---

## 2. Implementation approach (pure evaluator changes)

All changes are in the pure module `app/intake/readiness.py` — no DB, no network, deterministic.

1. **Constants:** add `R4_TOOL_CATEGORIES`; bump `READINESS_CAP`/`READINESS_CAP_REASON`/
   `RULESET_VERSION`; add `_CONSUMED_CATEGORIES |= set(R4_TOOL_CATEGORIES)` so the
   `NOT_ASSESSED_CATEGORIES = universe − consumed` derivation shrinks correctly. **Staging reasons:**
   leave the existing R3 reason string unchanged and add
   `STAGING_R4_NO_ENV_REASON = "r4_but_environments_and_deployment_targets_not_declared"` — R3
   without env uses the old R3 reason; R4 without env uses the new R4 reason.
2. **Ladder:** after the R3 assignment, compute `missing_r4 = [c for c in R4_TOOL_CATEGORIES if c
   not in declared]` and lift to `"R4"` when `level == "R3" and not missing_r4 and not spine_gaps`.
3. **Staging gate:** widen the condition to `level in ("R3", "R4")`.
4. **`ReadinessReport` + `to_dict()`:**
   - `missing_r4_categories` = `missing_r4` (the R4 tool categories not declared).
   - `missing_r4_test_coverage` = the **blocking `spine_gaps` dicts** (each preserving `kind`,
     `ref`, `summary`) — not just summaries; empty when coverage is complete. Safe because
     `spine_gaps` is already exposed in the report.
   - `missing_for_go_live`: add `r4_category_not_declared:<c>` entries for missing R4 categories.
     **Do not** add `r4_test_coverage_gap:<ref>` entries — spine-gap summaries already appear in
     `missing_for_go_live`, and the structured R4 test blockers live in `missing_r4_test_coverage`;
     duplicate signals are intentionally avoided.
   - Keep all existing keys.
5. **Module invariant:** the module-level `assert NOT_ASSESSED == universe − _CONSUMED` updates
   automatically once `_CONSUMED_CATEGORIES` includes the R4 categories — verify it still holds.

Decision precedence is preserved and fail-closed: a missing R4 category **or** any spine gap keeps
the project at R3 with explicit reasons; nothing weakens the R0–R3 ladder.

---

## 3. Repository impact — none beyond docstrings

`ReadinessRepository` already (a) passes Slice-15 declarations into `evaluate_readiness` and
(b) applies the **D-6 stale-source exclusion generically to every declared category** in
`_category_declarations` (a quarantined/missing/cross-project source doc drops that declaration).
The two R4 tool categories are ordinary declarations, so **no repository logic change is needed** —
the stale-source rule already covers R4 inputs. Update the `ReadinessRepository` docstring only.
The `readiness_reports` model/migration are unchanged (see §6).

---

## 4. Tests first (TDD) — specific failing tests

New/updated tests in `tests/test_readiness.py` (Docker-free pure-evaluator units, plus one DB case).
Each is written to fail before the evaluator change:

1. **`test_r4_when_r3_plus_tools_and_full_coverage`** — R3 (trio declared) + both R4 tool categories
   declared + a complete requirement→AC→oracle chain with **no** gaps ⇒ `readiness_level == "R4"`.
2. **`test_r4_blocked_by_missing_tool_category`** — R3 + only `tool_access_manifest` (no
   `integrations_and_external_systems`) + full coverage ⇒ stays `"R3"`;
   `missing_r4_categories == ["integrations_and_external_systems"]`.
3. **`test_r4_blocked_by_spine_gap`** — R3 + both tools declared but one requirement lacks an AC
   (or an AC lacks an oracle, or an invalid parent chain) ⇒ stays `"R3"`;
   `missing_r4_test_coverage` non-empty.
4. **`test_r4_staging_monotonic`** — (a) **regression:** R3 + env ⇒ staging `True` (unchanged);
   (b) R4 + env ⇒ staging `True`; (c) R4 without env ⇒ staging `False` with the explicit reason.
5. **`test_r4_go_live_always_false`** — at R4, `can_go_live_autonomously is False`.
6. **`test_readiness_cap_is_r4`** — `readiness_cap == "R4"`; `to_dict()["ruleset_version"] ==
   "slice18.v1"`; `readiness_cap_reason` references R5/gated-engine scope.
7. **`test_not_assessed_excludes_r4_tool_categories`** — `tool_access_manifest` and
   `integrations_and_external_systems` are **absent** from `not_assessed_categories`; the count
   shrinks by exactly 2 vs. Slice 16; the module-level `NOT_ASSESSED == universe − consumed`
   invariant holds.
8. **`test_report_keys_include_r4_fields`** — update the existing report-keys golden test to require
   `missing_r4_categories` and `missing_r4_test_coverage` (and the unchanged R3 keys).
9. **`test_d6_stale_source_excludes_r4_tool_declaration`** (DB-backed `@pytest.mark.db`) — a tool
   category declared from a source document that is later **quarantined** is dropped, blocking R4 —
   confirms the existing generic D-6 exclusion applies to R4 inputs (no new repo code).

Update any existing R3 golden tests that assert exact `not_assessed_categories` membership/length.

---

## 5. Docs updates

- **`CLAUDE.md`:** readiness entry → ladder now **R0–R4**, R4 = R3 + zero spine gaps + the two tool
  categories, cap `R4`, `ruleset_version slice18.v1`, monotonic staging; current-status line; bump
  `make test` / `make test-db` counts.
- **`README.md`:** build-readiness auditor section → add the R4 rule + report fields.
- **Module/model docstrings:** `app/intake/readiness.py` header and
  `app/models/readiness_report.py` (currently says "capped at R3" / "emits R0/R1/R2/R3") → R4.
- **`ReadinessRepository` docstring:** note R4 inputs use the same D-6 stale-source exclusion.

---

## 6. No migration expected

`readiness_reports.readiness_level` CHECK already permits `R0..R5` (migration `0015`, model
docstring). R4 is already a legal stored value. No table/column/grant/migration change. If TDD
surfaces a concrete need, stop and escalate before adding one.

---

## 7. Explicit out-of-scope

- **R5** and any go-live-readiness logic.
- **Gated-engine completeness:** autonomy / human-approval / cost / **production_authority** — not
  evaluated for completeness; production authority stays incomplete by definition.
- **Secrets** as an R4 precondition (`secrets_and_credentials_manifest` excluded — R5 concern).
- Semantic contradiction analysis, evidence packs, new artifact kinds, LLM, any write path.
- API changes — Slice 17's `GET /api/projects/{id}/readiness` already serves the R4 report verbatim;
  no endpoint edits.
- Content-quality judgement — declarations are presence-checked, not validated for quality (matches
  the R3 rule).

---

## 8. Risks & invariants

**Risks**
- **R-1 (spine_gaps semantics):** R4 must consume the *same* exhaustive `spine_gaps` list; any gap
  blocks R4. Mitigation: tests 1 & 3 pin both directions.
- **R-2 (staging reason wording):** the existing R3 reason text says "r3_but…" and is wrong at
  R4-without-env. Resolved: keep the R3 reason unchanged and add
  `STAGING_R4_NO_ENV_REASON = "r4_but_environments_and_deployment_targets_not_declared"`; R4 without
  env uses it. Test 4(c) asserts the R4 reason.
- **R-3 (not_assessed drift):** moving two categories into "consumed" must shrink `not_assessed` by
  exactly 2. Mitigation: module-level invariant assert + golden test 7; update existing R3 golden
  tests.
- **R-4 (monotonic regression):** must not change any R0–R3 outcome or the §4.5-sample R3+staging
  behavior. Mitigation: regression assertion in test 4(a); existing R3 suite must stay green.

**Invariants to uphold**
- Fail-closed: missing R4 category or any spine gap or stale source ⇒ no R4, explicit reasons.
- `can_go_live_autonomously == False` at every level (capped < R5).
- `NOT_ASSESSED_CATEGORIES == CANONICAL_READINESS_CATEGORY_UNIVERSE − _CONSUMED_CATEGORIES`
  (module assert + golden test).
- Monotonic: R0–R3 semantics and the staging facet for R3 are unchanged.
- Determinism, no LLM, no I/O in `app/intake/readiness.py`.

---

## 9. Next step after approval

On approval: create the Slice 18 branch, write the failing tests first (§4), then the evaluator
change (§2), then docs (§5). Pause at green for implementation review before PR. **Until then: no
branch, no code.**
