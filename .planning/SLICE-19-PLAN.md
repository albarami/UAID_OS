# Slice 19 — Readiness/findings history endpoints (PLAN v1)

**Status:** APPROVED (PLAN v1) and IMPLEMENTED — historical record. Implemented on branch
`feat/slice19-history-endpoints` off `main` @ `3efcf8a`; additive routes in `app/api/dashboard.py`
+ tests + docs (no migration, no LLM, no evaluator change). Verification: `ruff` clean,
`make test` 160, `make test-db` 243.
**Base:** `main` @ `3efcf8a` (clean).
**Closes:** the Slice 17 D-17-2 deferral (history endpoints).

---

## 0. One-line summary

Add two **read-only** GET endpoints exposing the **full ordered history** of persisted
readiness and findings snapshots, via the already-implemented `repo.history()`. Each element
reuses the exact Slice 17 per-snapshot serialization. No evaluator change, no migration, no LLM.

---

## 1. Scope (path/envelope contract — coordinator-provided)

Two new routes appended to `app/api/dashboard.py` (prefix `/api`), mirroring Slice 17:

```
GET /api/projects/{project_id}/readiness/history
  -> {"readiness_history": [ <same serialized readiness snapshot shape as Slice 17 latest>, ... ]}

GET /api/projects/{project_id}/findings/history
  -> {"findings_history": [ <same serialized findings snapshot shape as Slice 17 latest>, ... ]}
```

- **Newest-first**, matching `repo.history()` ordering (`created_at DESC, id DESC`).
- Tenant-scoped via existing `require_tenant` → `tenant_scope` → RLS.
- Auth denial follows the existing dashboard pattern (401, no fallback tenant).
- **Empty state → empty list** (`{"readiness_history": []}`), not 404.
- **Cross-tenant / nonexistent `project_id` → empty list** (RLS yields no rows; no leak, no
  existence oracle — consistent with Slice 17's null-for-latest behavior).
- **Read-only GET only.**
- **No pagination in this slice** — the full list is returned (see §6 out-of-scope).

Per-element shape is **identical** to Slice 17 `latest`:
- readiness: `{report_id, evaluated_at, readiness_level, can_build_to_staging,
  can_go_live_autonomously, report}` — `evaluated_by` omitted (D-17-1).
- findings: `{report_id, evaluated_at, gap_count, contradiction_count, report}` — `evaluated_by`
  omitted.

---

## 2. Implementation approach

Pure additive routing in `app/api/dashboard.py`; **reuse the existing helpers**
`_readiness_dict(rec)` / `_findings_dict(rec)` per element (no new serialization).

```python
@router.get("/projects/{project_id}/readiness/history")
async def project_readiness_history(project_id, context = Depends(require_tenant)) -> dict:
    async with tenant_scope(context) as session:
        rows = await ReadinessRepository(session, context).history(project_id)
        return {"readiness_history": [_readiness_dict(r) for r in rows]}

@router.get("/projects/{project_id}/findings/history")
async def project_findings_history(project_id, context = Depends(require_tenant)) -> dict:
    async with tenant_scope(context) as session:
        rows = await FindingsRepository(session, context).history(project_id)
        return {"findings_history": [_findings_dict(r) for r in rows]}
```

`history(project_id)` (`readiness.py:114`, `findings.py:74`) is a pure tenant+project-scoped
SELECT ordered `created_at DESC, id DESC` — newest-first, read-only, RLS-enforced. No new repo
code, no new imports beyond the `ReadinessRepository`/`FindingsRepository` already imported for
Slice 17.

**Route ordering note:** FastAPI matches `/projects/{id}/readiness` and
`/projects/{id}/readiness/history` as distinct paths (different segment counts), so the new routes
do not shadow or get shadowed by the Slice 17 `latest` routes. The tests confirm both still work.

---

## 3. Tests first (TDD) — exact tests

New tests in `tests/test_api.py` (DB-backed `@pytest.mark.db`), reusing the existing `api_ctx`
fixture and the Slice 17 `_record_readiness`/`_record_findings` helpers. Written to fail before the
routes exist (404):

1. **`test_readiness_history_returns_ordered_snapshots`** — record two readiness snapshots for A's
   project; `GET …/readiness/history` → `200`; `readiness_history` has 2 elements **newest-first**
   (`[0].report_id == second`, `[1].report_id == first`); each element has the Slice 17 keys;
   `evaluated_by` absent.
2. **`test_findings_history_returns_ordered_snapshots`** — same for findings.
3. **`test_history_empty_state_returns_empty_list`** — A's project with no snapshot →
   `200 {"readiness_history": []}` and `{"findings_history": []}` (not 404).
4. **`test_history_cross_tenant_returns_empty_list`** — record snapshots for tenant B's project;
   key A → `GET …/readiness/history` and `…/findings/history` → `200` with `[]` (no leak); key B on
   its own project sees its elements.
5. **`test_history_auth_deny_by_default`** — missing / Basic / unknown / revoked key → `401` on both
   history paths; authorized → `200`.
6. **`test_history_is_read_only`** — `POST` to both history paths → `405`; assert the
   `readiness_reports` / `intake_findings_reports` row counts are unchanged before/after the GETs
   (no `evaluate_and_record` side effect) — mirrors the Slice 17 both-tables read-only guard.
7. **`test_latest_and_history_coexist`** — both `…/readiness` (latest, single object) and
   `…/readiness/history` (list) return `200` for the same project (guards route non-shadowing).

TDD: write these (red, 404) before editing `dashboard.py`. Target: `make test-db` stays green
(currently 236) plus the new cases; `make test` unchanged (these are DB-backed).

---

## 4. Docs updates

- **`CLAUDE.md`:** add `readiness/history` + `findings/history` to the endpoint lists
  (`app/api/` skeleton paragraph, the Read-API entry, the "How to run" endpoint line); note Slice 19
  closes the D-17-2 history deferral; bump `make test-db` count; remove "history endpoints (… not yet
  exposed)" from the Read-API deferred list.
- **`README.md`:** add the two history GETs to the dashboard endpoint enumeration + the Read-API
  section.
- **`app/api/dashboard.py` module docstring:** mention the history endpoints alongside latest.
- **No spec change** — implements existing §18.6 read surface.

---

## 5. Risks & invariants

**Risks**
- **R-1 (route shadowing):** `/readiness/history` must not collide with `/readiness`. Mitigation:
  distinct path depth; test 7 asserts both resolve.
- **R-2 (unbounded response):** full history returned with no pagination; a project with many
  snapshots yields a large payload. Mitigation: explicitly out-of-scope (§6) and called out in docs;
  acceptable for current scale (snapshots are operator-triggered, low volume).
- **R-3 (cross-tenant leak):** must return `[]`, never another tenant's rows. Mitigation: reads stay
  in `tenant_scope`/RLS; test 4 asserts it.

**Invariants**
- Read-only: only `repo.history()` (SELECT); no INSERT/UPDATE/DELETE, no `evaluate_and_record`.
  Tables remain append-only at the DB layer regardless.
- Single HTTP→tenant boundary unchanged (`require_tenant`); all reads inside `tenant_scope`/RLS.
- No existence oracle: empty-history and cross-tenant both return `200` + `[]`.
- Per-element shape is byte-for-byte the Slice 17 serialization (shared helpers) — no drift.
- No evaluator/semantic change; no migration; no LLM; no new write path.

---

## 6. Out-of-scope

- **Pagination / limit / offset / cursor** — full list only this slice (explicitly deferred).
- Filtering (by level, date range), sorting options — none.
- Any readiness/findings evaluator or report-shape change.
- A "compute fresh history" path — history is persisted snapshots only.
- Migration, new tables/columns/grants, new model.
- LLM, write endpoints, web UI.

---

## 7. Verification commands (before review)

```bash
uv run ruff check .
make test
RLS_DB_PASSWORD=uaid_app make test-db
git diff --check
git status -sb
```
Expected: ruff clean; `make test` unchanged (160); `make test-db` 236 + new cases; diff-check clean;
`git status` shows only the intended Slice 19 files (`app/api/dashboard.py`, `tests/test_api.py`,
`README.md`, `CLAUDE.md`, and the `.planning/SLICE-19-PLAN.md` artifact) plus local-only
`.planning/HANDOFF.json` / `.env` as unstaged/untracked as applicable; **nothing staged** (staging
happens at the approved commit step).

---

## 8. Next step after approval

On approval: create the Slice 19 branch, write the 7 failing tests first (§3), then the two routes
(§2), then docs (§4). Pause at green for implementation review before PR. **Until then: no branch,
no code.**
