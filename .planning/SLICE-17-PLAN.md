# Slice 17 — Read API endpoints for readiness + findings visibility (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice17-readiness-findings-read-api` off `main` @ `a652007`; `app/api/dashboard.py` +
`tests/test_api.py` + docs. Verification: `ruff` clean, `make test` 152, `make test-db` 235
(228 prior + 7 new). Plan kept as the design rationale for the slice.
**Candidate:** B (low-risk read-API visibility slice), selected by coordinator.

---

## 0. One-line summary

Expose the already-built **readiness** (Slices 12+16) and **findings** (Slice 13)
engines through two new **GET-only** endpoints on the existing Slice 10 read API,
behind the existing `require_tenant → tenant_scope → RLS` boundary. Return the
**latest persisted snapshot** or an honest empty state. No writes, no LLM, no
migration, no R4/R5 logic.

This directly closes part of the Slice 10 deferral. `app/api/dashboard.py:8-9`
states forecast / critical path / **readiness** / evidence-pack / **high-risk
findings** / deployment / next action are "deferred (subsystems not built)."
Readiness and findings subsystems are now built — Slice 17 makes them visible.

---

## 1. Exact endpoint paths and response shapes

Two new routes appended to the existing `app/api/dashboard.py` router
(`prefix="/api"`), mirroring the existing project-scoped GET pattern at
`dashboard.py:46-105`.

```
GET /api/projects/{project_id}/readiness
GET /api/projects/{project_id}/findings
```

### 1.1 Readiness response

The persisted record (`ReadinessReportRecord`, `app/models/readiness_report.py`)
already carries the top-level columns + a full `report` JSONB (the §4.5 document
+ deterministic extensions, built by `ReadinessReport.to_dict()`,
`app/intake/readiness.py:136-158`). The `report` dict is JSON-safe (it has
round-tripped through JSONB). Proposed envelope — single key, value is `null`
when never evaluated:

```jsonc
// 200 — latest snapshot exists
{
  "readiness": {
    "report_id": "…uuid…",
    "evaluated_at": "2026-06-13T08:30:00.123456+00:00",   // record.created_at, ISO
    "readiness_level": "R2",                               // record column
    "can_build_to_staging": false,                         // record column
    "can_go_live_autonomously": false,                     // record column
    "report": { /* full §4.5 doc + extensions, verbatim from record.report */ }
  }
}

// 200 — project readable by this tenant but no readiness ever recorded
{ "readiness": null }
```

### 1.2 Findings response

Same shape over `IntakeFindingsReport` (`app/models/intake_findings_report.py`);
`report` is `FindingsReport.to_dict()` (`app/intake/findings.py:46-54`):

```jsonc
// 200 — latest snapshot exists
{
  "findings": {
    "report_id": "…uuid…",
    "evaluated_at": "2026-06-13T08:30:00.123456+00:00",
    "gap_count": 3,                          // record column
    "contradiction_count": 0,                // record column
    "report": { /* gaps[], contradictions[], counts, ruleset_version — refs only */ }
  }
}

// 200 — project readable by this tenant but no findings ever recorded
{ "findings": null }
```

**Note on content safety:** the findings `report` is already refs-only by
construction (Slice 13 carries no titles/body/data). The readiness `report`
carries the §4.5 doc including assumption summaries — this is the tenant's *own*
data returned to an authenticated caller of that same tenant, consistent with
how `/cost` returns the tenant's budget caps. No cross-tenant exposure (§4 below).

### 1.3 Implementation sketch (for review only — not code)

```python
# app/api/dashboard.py  (append; reuse existing imports + helpers pattern)
from app.repositories.readiness import ReadinessRepository
from app.repositories.findings import FindingsRepository

@router.get("/projects/{project_id}/readiness")
async def project_readiness(project_id, context = Depends(require_tenant)) -> dict:
    async with tenant_scope(context) as session:
        rec = await ReadinessRepository(session, context).latest(project_id)
        return {"readiness": _readiness_dict(rec) if rec else None}

@router.get("/projects/{project_id}/findings")
async def project_findings(project_id, context = Depends(require_tenant)) -> dict:
    async with tenant_scope(context) as session:
        rec = await FindingsRepository(session, context).latest(project_id)
        return {"findings": _findings_dict(rec) if rec else None}
```

`latest(project_id)` is a pure tenant+project-scoped SELECT
(`readiness.py:100-110`, `findings.py:62-72`) ordered `created_at DESC, id DESC`
— a true read, no write, RLS-scoped.

---

## 2. Latest-persisted vs compute-fresh vs both

**Decision: return latest persisted snapshot only (`repo.latest`). Do not compute,
do not persist, on a GET.** (Matches coordinator's recommendation.)

Rationale:
- `repo.latest()` is read-only. `repo.evaluate()` computes fresh but is heavier and
  not needed for "what is the current recorded state." `repo.evaluate_and_record()`
  **writes** — using it from a GET would violate read-only and the no-write-from-GET
  guardrail.
- Keeps GET idempotent and side-effect-free; preserves the Slice 10 invariant that
  the read API never mutates (`test_endpoints_are_read_only`, `test_api.py:230-248`).
- "Compute fresh" / "evaluate-and-record" belongs to a future *write* slice with its
  own authority/approval story — explicitly out of scope here (§7).

---

## 3. API error / empty-state behavior

- **Never evaluated (no snapshot):** `200` with `{"readiness": null}` /
  `{"findings": null}`. **Not 404.** A project may be readable by the tenant but
  simply not yet evaluated — a valid state, mirroring `/runs` returning
  `{"runs": []}` for a project with no runs (`dashboard.py:46-52`).
- **Cross-tenant / non-existent `project_id`:** RLS yields no rows ⇒ `latest()`
  returns `None` ⇒ identical `200 {"…": null}`. **This is deliberate and a security
  feature:** "exists-but-unevaluated" and "not-your-tenant / nonexistent" are
  indistinguishable to the caller, so the endpoint leaks no existence signal across
  tenants (see §4).
- **Missing/malformed/unknown/revoked bearer key:** `401`, no fallback tenant —
  inherited unchanged from `require_tenant` (`auth.py`), proven by
  `test_auth_deny_by_default` (`test_api.py:198-207`).
- **Malformed `project_id` (not a UUID):** `422` from FastAPI path validation
  (`project_id: uuid.UUID`), same as every existing endpoint.
- **Write verbs (POST/PUT/DELETE) to these paths:** `405` automatically (only GET
  registered), matching `test_api.py:247`.

---

## 4. Security / tenant-boundary invariants (must hold)

1. **Single HTTP→tenant boundary unchanged:** both endpoints use
   `Depends(require_tenant)` — the only place untrusted HTTP becomes a tenant. No new
   auth path.
2. **All reads inside `tenant_scope`:** every query runs with the `app.current_tenant`
   GUC set ⇒ RLS-enforced. A cross-tenant `project_id` returns nothing, never another
   tenant's report (INV-5).
3. **Read-only:** only `repo.latest()` (SELECT) is called. No INSERT/UPDATE/DELETE,
   no `evaluate_and_record`. `readiness_reports` / `intake_findings_reports` are
   append-only at the DB layer regardless (migrations 0015/0016), defense-in-depth.
4. **No new write paths, no new tables, no new grants, no migration.**
5. **No existence oracle across tenants:** empty-state and cross-tenant both return
   `200 {…: null}` (§3).
6. **No secrets / no audit-internal leakage:** response surfaces report bodies +
   snapshot columns only. `evaluated_by` is an untrusted internal label — **omit it
   from the response** (open decision D-17-1 below; default = omit).

---

## 5. Tests required

New tests in `tests/test_api.py` (DB-backed, `@pytest.mark.db`), mirroring the
existing `api_ctx` fixture + httpx ASGITransport pattern (`test_api.py:48-115`).
Fixture extended to seed, for tenant A's project, **one persisted readiness report
and one persisted findings report** (via `evaluate_and_record` inside a tenant_scope
in setup, or direct admin insert), and to leave tenant B's project **unevaluated**.

1. **Happy read — readiness:** A's key → `GET …/readiness` → `200`, `readiness`
   non-null, `readiness_level`/`can_build_to_staging`/`can_go_live_autonomously`
   present, `report` is the full dict.
2. **Happy read — findings:** A's key → `GET …/findings` → `200`, `findings`
   non-null, `gap_count`/`contradiction_count` + `report.gaps`/`report.contradictions`.
3. **Empty state:** A's key on a project with no snapshot → `200`,
   `{"readiness": null}` / `{"findings": null}` (not 404).
4. **Cross-tenant denial (the key test):** A's key → `GET /api/projects/{B_project}/
   readiness` and `/findings` → `200` with `null` (B's report never leaks), while
   B's own key on the same project sees its data. Mirrors
   `test_cross_tenant_reads_denied` (`test_api.py:213-224`).
5. **Auth deny-by-default:** missing / Basic / unknown / revoked key → `401` on both
   new paths; authorized request to the same path → `200` (proves auth, not path).
6. **Read-only:** `POST` to both paths → `405`; assert snapshot row count unchanged
   before/after a `GET` (no `evaluate_and_record` side effect). Mirrors
   `test_endpoints_are_read_only` (`test_api.py:230-248`).
7. **Latest semantics:** record two readiness snapshots for A's project; `GET`
   returns the most recent (`created_at DESC, id DESC`) — guards the `latest()`
   ordering contract.

**TDD:** write these (red) before touching `dashboard.py`. Target: `make test-db`
stays green (currently 228 passing) plus the new cases.

---

## 6. Docs updates required

- **`CLAUDE.md`:** update the Slice 10 / Read-API entries — remove "readiness" and
  "findings" from the "deferred" list in both the `app/api/` skeleton paragraph and
  the "Read API / dashboard (§18.6)" not-yet-present entry; add Slice 17 to current
  status + endpoint list (`/api/projects/{id}/{runs,approvals,blockers,cost,
  readiness,findings}`); bump the `make test-db` passing count.
- **`app/api/dashboard.py` module docstring:** move readiness + findings out of the
  deferred sentence into the covered set.
- **`README.md`:** if it enumerates endpoints, add the two new GETs.
- **No spec change** — this implements existing §18.6 / §4.5 surface.

---

## 7. Explicit out-of-scope

- No `evaluate` / `evaluate_and_record` from HTTP (no fresh compute, no persistence
  on GET). A "trigger evaluation" write endpoint is a separate future slice.
- No history endpoint (`repo.history` exists but not exposed this slice) — can be a
  trivial follow-up; keep this slice to "latest" only unless coordinator wants both.
- No R4/R5 readiness logic, no gated-engine readiness, no autonomy/go-live changes.
- No LLM, no extraction/promotion exposure, no intake-category exposure.
- No migration, no new table/column/grant, no new model.
- No web UI, no auth-event audit, no HTTP key issuance, no pagination/filtering.
- No change to the §4.5 report contents or findings taxonomy.

---

## 8. Open decisions for coordinator (resolve before/with implementation)

- **D-17-1 (response fields):** Include `evaluated_by` (untrusted caller label) in
  the response? **Recommend OMIT** — it's internal provenance metadata, not operator
  signal, and matches the minimalism of existing endpoints. *(Default: omit.)*
- **D-17-2 (history):** Expose `GET …/readiness/history` + `…/findings/history` now,
  or defer? **Recommend DEFER** to keep the slice minimal; the repos already support
  it, so it's a cheap later add. *(Default: defer.)*
- **D-17-3 (envelope key vs flat):** Single-key envelope `{"readiness": …|null}`
  (recommended, consistent with `{"runs": […]}`) vs a flat object with an
  `"evaluated": bool` flag. **Recommend the single-key envelope.**

---

## 9. Standing guardrails (unchanged)

One vertical slice; TDD-first (red→green); fail-closed; two-commit pattern; gated
merge via PR; no overclaim; no secrets; keep `HANDOFF.json`/`.env` out of commits;
`main` stays green and shareable.

---

## 10. Outcome (as built)

Implemented per plan: TDD-first (7 failing DB tests → endpoints → green); both endpoints
return `repo.latest()` only (no compute/persist on GET); single-key envelopes; `evaluated_by`
omitted (D-17-1); history deferred (D-17-2); no migration/LLM/R4-R5. Decisions D-17-1/2/3
locked as recommended. Docs (CLAUDE.md, README.md) updated and made merge-safe (no transient
branch/review state in committed docs). Verification: `ruff` clean · `make test` 152 ·
`make test-db` 235.
