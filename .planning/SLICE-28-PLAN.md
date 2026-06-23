# Slice 28 — Verified source-control / CI connector (A5 gate #3 PASS-capable) — PLAN v3

**Status:** AWAITING PLAN APPROVAL — **no branch / no code / no migration / no tests until separately approved.**
**Persona:** senior release-governance / connector-security architect.
**Base:** `main` @ `3bcc457` (verified in sync); only HANDOFF + roadmap local drift. This plan adds `.planning/SLICE-28-{CONNECTOR-DISCUSSION,PLAN}.md`.
**Migration head:** `0026_request_auth_identity` (verified) → new head **`0027`**.
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:209-219`. **Discussion:** `.planning/SLICE-28-CONNECTOR-DISCUSSION.md`.

> **Revision log — v1 → v2 (each is a strict-review blocker, verified against the named anchors):**
> - **B1 — Project-repo binding.** v1 took `repo_ref` as a caller arg, so an unrelated protected repo (e.g. `torvalds/linux`) could satisfy gate #3 for the wrong project. v2: the connector **resolves the repo from the project's own declared `existing_assets_and_repositories`** intake category and the credential **source** from `secrets_and_credentials_manifest` (`app/intake/categories.py:52,56`; `app/repositories/intake_categories.py:35-47`); **no caller-supplied `repo_ref`**. New test: an unrelated protected repo cannot satisfy gate #3 (D-28-11).
> - **B2 — No raw `repo_ref` in broker params.** v1 passed `{"repo_ref",…}` to `broker_call`, which records sanitized params to `tool_calls.params`, and `repo_ref` is **not** in the secret-marker denylist (`app/tools/registry.py:15-23`; `app/repositories/tools.py:69-88`). v2: broker params are **safe-only** `{"provider":"github","branch":…,"repo_ref_present":true}`; `repo_ref` lives only in connector execution + the snapshot row (D-28-12).
> - **B3 — GitHub 404 semantics.** v1 ambiguously wrote a "verified-false" snapshot for disabled protection, but GitHub returns **404 "Branch not protected"** (indistinguishable from missing branch / no access). v2: **only a clean `200` writes a `connector_verified` snapshot**; `403/404/non-200/timeout/malformed ⇒ no verified write, fail-closed` (no "verified-false" snapshot). Min token perm + 403/404 behavior specified (D-28-8).
> - **B4 — Gate #3 latest-wins ordering.** v1 branched on `connector_verified_count > 0` before checking the latest snapshot. v2 keys **only off the latest snapshot** in the reviewer-specified order (§8).
> - **B5 — `passed_gate_count` claim.** Gate #3 passing adds **one** gate; the total is `2` only when readiness is also `R5` (gate #1). v2 corrects wording + tests (§8, §10, §17).
>
> **Revision log — v2 → v3 (completing B1 at gate-evaluation time, per re-review):**
> - **B1-cont — Gate-time repo binding.** v2 bound the connector *fetch* to the declared repo, but gate #3 still evaluated the **project-only** latest snapshot (`latest_branch_protection`, `app/repositories/ci_evidence.py:52-67`) — so a verified snapshot for repo A could still PASS after the declaration is **revised** to repo B (declarations are revisable incl. `data`, `app/repositories/intake_categories.py:67-99`). v3: gate #3 **resolves the currently declared repo/branch** (same resolver as the connector) and evaluates the latest snapshot **for `(tenant, project, provider, repo_ref, branch)`** via a new `latest_branch_protection_for_repo`; missing/malformed/undeclared ⇒ **fail-closed `branch_protection_repo_unbound`**. Raw `repo_ref` stays out of the gate report / broker params / audit (D-28-13).

> **Provenance (Sanad).** Code/migration `file:line` anchors read this session; spec `§:line` anchors carried from the Slice-27 exploration sweep, cross-corroborated (see DISCUSSION §0).

---

## 0. Goal & non-goal
- **Goal:** a **GitHub-first, broker-mediated** connector that fetches branch-protection for **the project's own declared repo**, verifies it, and writes the **`connector_verified`** tier into the Slice-26 `branch_protection_snapshots` model — making **A5 gate #3 PASS deterministically** only on **latest + verified + active + fresh** evidence for that project's repo (Appendix B #3 `spec:2987`).
- **Non-goal:** no go-live beyond gate-#3 evidence (`can_go_live_autonomously` stays false; `a5_satisfied` false); GitHub only; **no** HTTP write API (D-28-7); no broker authority broadening; no PR/test-result evidence (Slice 29); no real network in tests; no raw token/repo_ref in audit or broker params.

## 1. Files (create / modify)
| # | File | Action |
|---|---|---|
| 1 | `app/release/ci_evidence.py` | **modify** — `CONNECTOR_WRITABLE`, `validate_connector_snapshot`, `gate3_protection_sufficient(...)` |
| 2 | `app/release/scm_connector.py` | **create** — `SCMConnector` protocol + `FakeSCMConnector` + `GitHubSCMConnector` (never tested) + `map_github_branch_protection` |
| 3 | `app/release/project_repo.py` | **create** — shared `resolve_declared_repo` + `resolve_credential_ref` (used by BOTH connector + gate) |
| 3b | `app/release/ci_evidence_service.py` | **create** — `refresh_branch_protection` (resolve → broker_call → fetch → verify → write) |
| 4 | `app/repositories/ci_evidence.py` | **modify** — `record_connector_verified_branch_protection` + **`latest_branch_protection_for_repo`** (gate uses this, not project-only `latest`) |
| 5 | `app/tools/registry.py` | **modify** — add `source_control.read_branch_protection` (read, no approval) |
| 6 | `app/policy/matrix.py` | **modify** — add `read_source_control_config` = `_r(L.A1)` (read; non-mandatory) |
| 7 | `migrations/versions/0027_connector_verified_evidence.py` | **create** — guard `CREATE OR REPLACE` allows `connector_verified` |
| 8 | `app/release/production_autonomy.py` | **modify** — gate #3 latest-wins ladder + PASS; `ruleset_version` → `slice28.v1` |
| 9 | `app/repositories/production_autonomy.py` | **modify** — pass latest `required_pull_request_reviews` + freshness |
| 10 | `app/config.py` | **modify** — `github_connector_token=""` (env, fail-closed) + `ci_evidence_max_age_hours=24` |
| 11-13 | `tests/{test_ci_evidence,test_production_autonomy,test_api}.py` | **modify** |
| 14 | `CLAUDE.md` + `README.md` | **modify** |

## 2. Project-repo + credential resolution — SHARED leaf module `app/release/project_repo.py` (B1 / D-28-11/13)
**One resolver, used by BOTH the connector (fetch time) AND the gate (evaluation time)** — so the evidence written and the evidence the gate trusts are bound to the **same** current declaration. Leaf module (imports only `IntakeCategoryRepository` + the pure `ci_evidence` validators) to avoid an import cycle with `production_autonomy`.
- `resolve_declared_repo(session, context, project_id) -> tuple[str, str] | None`:
  - read `IntakeCategoryRepository.get_category(project_id, "existing_assets_and_repositories")`; returns **`None`** (⇒ caller fails closed) if absent / `status != "declared"`.
  - extract `data["primary_repository"]` — **validate** against `REPO_REF_RE` + `TOKENISH_RE` (`ci_evidence.py:32,35`); `branch = data.get("protected_branch", "main")`; on malformed/missing return **`None`** (never a partial/guessed repo). Returns `(repo_ref, branch)` or `None`.
- `resolve_credential_ref(...)`: require `get_category(project_id, "secrets_and_credentials_manifest")` declared with a `{manager, reference_name}` reference (`categories.py:79`); **fail-closed** if absent. The reference is the credential **source/provenance**; the actual token value resolves from operator env `GITHUB_CONNECTOR_TOKEN` (per-tenant value deferred, D-28-9) — stated honestly.
- **Result:** the connector fetches **only the project's own declared repo**, AND the gate (re-)resolves the **current** declaration at evaluation time (§8) — so a snapshot for a no-longer-declared repo cannot satisfy gate #3. (Same-project + RLS enforced by the intake-category FK; `CLAUDE.md` Slice 15.)

## 3. Pure additions — `app/release/ci_evidence.py` (D-28-4/5)
- `CONNECTOR_WRITABLE = ("connector_verified",)`.
- `validate_connector_snapshot(record)` — same shape checks as `validate_new_snapshot` (`ci_evidence.py:75-101`) but provenance, if present, **must be `connector_verified`**; `observed_at` **required**.
- `gate3_protection_sufficient(*, protection_enabled, required_pull_request_reviews, required_status_check_count) -> bool` — pure, fail-closed: `protection_enabled is True AND required_pull_request_reviews is True AND required_status_check_count >= 1` (D-28-10). Freshness + latest/verified checks live in the gate ladder (§8), not here.

## 4. Connector adapter — `app/release/scm_connector.py` (D-28-1/3/8; mirror `app/llm/`)
- `SCMConnector(Protocol).fetch_branch_protection(*, repo_ref, branch) -> dict | None`.
- `FakeSCMConnector` — **all tests/CI, no network, no token**: canned mapped result, or set to return `None` / raise, to drive the truth table.
- `GitHubSCMConnector` — **shipped, never exercised in tests**: token from `settings.github_connector_token` (**env-only; empty ⇒ `MissingConnectorCredential`**, redacted). Calls `GET /repos/{owner}/{repo}/branches/{branch}/protection`. **`200` only ⇒ mapped result** (protection is on). **`404`** ("not protected" / missing / no access), **`403`** (insufficient token scope), any non-200 / timeout / malformed ⇒ `SCMConnectorError` ⇒ **no verified write** (B3). **Min token permission:** classic `repo` scope or fine-grained **Administration: read** on the repo (branch-protection read requires admin); documented in `README.md`.
- `map_github_branch_protection(payload) -> dict` (pure): `protection_enabled=True` (200 ⇒ protection on), `required_pull_request_reviews = payload has "required_pull_request_reviews"`, `required_status_checks = names from payload["required_status_checks"]["contexts"]` (or `checks`), `enforce_admins = payload["enforce_admins"]["enabled"]`; unexpected shape ⇒ `SCMConnectorError`. No token/URL in the result.

## 5. Orchestration — `refresh_branch_protection(session, context, *, project_id, agent_id, actor, connector)` (D-28-2/7/8/11/12)
1. **Resolve** `(repo_ref, branch)` (§2) + credential presence; fail-closed on missing config (no broker call, no write).
2. **Broker decision** — `broker_call(session, context, project_id=project_id, agent_id=agent_id, tool_name="source_control.read_branch_protection", params={"provider":"github","branch":branch,"repo_ref_present":True})` — **safe params only; NO `repo_ref`** (B2). Only an `ALLOWED_*` terminal proceeds; else return the decision, no fetch/write.
3. **Fetch** — `connector.fetch_branch_protection(repo_ref=repo_ref, branch=branch)`. `None` / `SCMConnectorError` / `MissingConnectorCredential` ⇒ **no snapshot** (audited failure, safe metadata only — D-28-8); `200`-mapped ⇒ continue.
4. **Verify + write** — build dict (`provenance="connector_verified"`, `observed_at=now`), `validate_connector_snapshot`, `repo.record_connector_verified_branch_protection(...)`.
Admin/internal-path; **no HTTP endpoint** (D-28-7); tests call it directly with `FakeSCMConnector`.

## 6. Repository — `app/repositories/ci_evidence.py` (D-28-4/13)
- `record_connector_verified_branch_protection(*, project_id, payload, actor)`: `validate_connector_snapshot`; **stamp `provenance="connector_verified"`**; derive count; INSERT; `_audit("ci.branch_protection_verified", …)` — **safe metadata only** (mirror `ci_evidence.py:86-102`; never `repo_ref`/checks/URL/token).
- **NEW `latest_branch_protection_for_repo(project_id, repo_ref, branch, provider="github")`** — latest snapshot filtered by `(tenant_id, project_id, provider, repo_ref, branch)` (extends the project-only WHERE of `ci_evidence.py:55-67`), ordered `created_at DESC, id DESC`, or `None`. **Gate #3 uses THIS** (§8); the project-only `latest_branch_protection` stays only for the informational `GET …/ci_evidence` read (B1 requires gate evaluation to be repo-bound, not project-wide).
- `count_*` reused (`ci_evidence.py:69-84`).

## 7. Broker tool + matrix action (D-28-2)
- `matrix.py`: `"read_source_control_config": _r(L.A1)` (read; `requires_approval=False`; **non-`mandatory`** — not §2.6; `matrix.py:32-58`).
- `registry.py`: `"source_control.read_branch_protection": _c(…, "source_control", "read_source_control_config")` — `requires_approval=False`, `audit_level="standard"`. **No mutation capability.** Broker stays **decision-only** (`broker.py:42-138`); per-agent allowlist still gates; connector executes only on ALLOW.

## 8. Migration `0027` + Gate #3 (B3/B4/B5; D-28-4/5/6)
**Migration:** `CREATE OR REPLACE public.branch_protection_snapshots_guard()` changing only the provenance line to `IF NEW.provenance NOT IN ('caller_supplied_unverified','connector_verified') THEN RAISE …` (was `<>`, `0025:107-108`), **preserving** repo_ref slug+token, JSON-array, per-element, count-equality (`0025:110-129`). Column CHECK already allows both (`0025:66`). `downgrade` restores the strict guard. No new table/column/grant; reversible.

**Gate #3 — `production_autonomy.py` (`slice28.v1`); the latest is the snapshot for the CURRENTLY DECLARED repo/branch (B1-cont/B4):**
```
if not branch_protection_repo_bound:                    # no/malformed existing_assets_and_repositories
    insufficient("branch_protection_repo_unbound")      # FAIL-CLOSED — old snapshots cannot rescue this
elif latest_branch_protection_provenance is None:        # bound, but no snapshot for the declared repo/branch
    insufficient("no_branch_protection_evidence")
elif latest_branch_protection_provenance != "connector_verified":
    insufficient("branch_protection_observed_unverified")   # latest-for-repo is unverified — older verified ignored
elif not latest_branch_protection_fresh:                # null/older than CI_EVIDENCE_MAX_AGE
    insufficient("branch_protection_evidence_stale")
elif not gate3_protection_sufficient(enabled, pr_reviews, checks_count):
    insufficient("branch_protection_insufficient")
else:
    PASSED("branch_protection_and_required_checks_active_verified")
```
The `latest_*` inputs are the **repo-scoped** latest (`latest_branch_protection_for_repo`), NOT the project-only one. Counts stay **context only**. New engine kwargs (fail-closed defaults): `branch_protection_repo_bound: bool = False`, `latest_branch_protection_required_pull_request_reviews: bool | None = None`, `latest_branch_protection_fresh: bool = False`. Gate #3 context adds **`branch_protection_repo_bound`** (bool) — **never the raw `repo_ref`** (D-28-13; the gate report is exposed at `GET …/production_autonomy`).
**`passed_gate_count` (B5):** gate #3 passing adds **one** passed gate. Total is **`2` only when readiness is also `R5`** (gate #1, `production_autonomy.py:134-138`); **`1`** when gate #3 passes but readiness < R5. `a5_satisfied` false (≥11 gates unmet); `can_go_live_autonomously` **hard-false** (`production_autonomy.py:79-91`).
**Repo wiring (`repositories/production_autonomy.py`):** call `resolve_declared_repo(...)` (§2). If `None` ⇒ `branch_protection_repo_bound=False` (latest_* default None/False). Else `repo_bound=True` and `latest_bp = await ci.latest_branch_protection_for_repo(project_id, repo_ref, branch)`; pass `latest_bp.required_pull_request_reviews` + `latest_branch_protection_fresh = latest_bp.observed_at is not None AND (now - observed_at) <= CI_EVIDENCE_MAX_AGE` (repo holds the clock; engine pure). Raw `repo_ref` is used only for the scoped query — never placed in the report/context.

## 9. Config (D-28-3/6)
`github_connector_token: str = ""` (env `GITHUB_CONNECTOR_TOKEN`; empty ⇒ fail-closed). `ci_evidence_max_age_hours: int = 24` (env `CI_EVIDENCE_MAX_AGE_HOURS`).

## 10. Tests — TDD-first
**Pure:** `validate_connector_snapshot` (accepts `connector_verified` + requires `observed_at`; caller path still rejects it via `validate_new_snapshot`); `gate3_protection_sufficient` truth table; `map_github_branch_protection` happy + malformed.
**Repo-binding at gate time (B1-cont):** (a) project declares repo A + verified-active-fresh snapshot for A ⇒ gate #3 **`passed`**; (b) declaration **revised** to repo B (`intake_categories.py:67-99`) ⇒ the old A snapshot **no longer passes** (gate resolves B, no B snapshot ⇒ `no_branch_protection_evidence`); (c) verified-active-fresh snapshot for B ⇒ gate #3 **`passed`**; (d) **older verified A + newer unverified B** ⇒ latest-for-B reason `branch_protection_observed_unverified`, **never pass from A**; (e) **missing/malformed declaration** ⇒ `branch_protection_repo_unbound` **even if old verified snapshots exist**. The gate report carries `branch_protection_repo_bound` but **no raw `repo_ref`**. Also: the connector cannot fetch/resolve a non-declared repo (no caller `repo_ref` path).
**Broker params (B2):** after `refresh_branch_protection`, `tool_calls.params` contains `provider`/`branch`/`repo_ref_present` and **NOT** `repo_ref`; audit has no `repo_ref`/token/URL.
**GitHub semantics (B3):** `FakeSCMConnector` 200 ⇒ verified write; returns `None` / raises (`SCMConnectorError`/`MissingConnectorCredential`) ⇒ **no snapshot**; **no "verified-false" snapshot exists in any path**.
**DB:** verified write ⇒ `connector_verified` row, count 0→1, latest returns it; **DB-guard now accepts** direct-SQL `connector_verified` but still rejects bad provider/repo_ref/token/array/count + UPDATE/DELETE/TRUNCATE.
**Gate #3 (B4/B5):** latest-wins ordering (older verified + newer unverified ⇒ `observed_unverified`); PASS only on latest+verified+enabled+pr_reviews+≥1 check+fresh; stale ⇒ `branch_protection_evidence_stale`; insufficient ⇒ `branch_protection_insufficient`; **`passed_gate_count`**: `==2` with R5 seeded, `==1` without R5 (both with gate #3 `passed`); `can_go_live_autonomously` false in every case; `ruleset_version=="slice28.v1"`.
**API:** `…/ci_evidence` shows the verified latest; `…/production_autonomy` gate #3 `passed` under a seeded verified-active-fresh snapshot. `make test` + fresh `make test-db` + alembic round-trip.

## 11. Documentation
`CLAUDE.md`: `scm_connector.py` + `ci_evidence_service.py` entries (repo-bound, broker-gated, safe params, 200-only verified, fail-closed); `0027`; gate #3 PASS-capable + latest-wins + `slice28.v1`; honest connector-authenticity + operator-token caveats; status "Slice 28 … in progress"; **actual** test counts. `README.md`: "Verified source-control / CI connector" section (GitHub-first, project-repo-bound, broker-gated read, connector-verified evidence, gate #3 PASS rule + 24h freshness, min token perm, fail-closed, no-secret, no `repo_ref` in broker params). Roadmap stays local.

## 12. Bound decisions (proposed; coordinator to RULE at approval)
- **D-28-1** GitHub only. **D-28-2** broker-gated read; broker stays decision-only; connector executes on ALLOW. **D-28-3** operator env `GITHUB_CONNECTOR_TOKEN`, fail-closed, reference-only (manifest declares the source). **D-28-4** connector-only verified write + `0027` guard relax (other invariants preserved). **D-28-5** gate #3 latest-wins ladder (§8). **D-28-6** freshness 24h default; null/older ⇒ not pass. **D-28-7** no HTTP write endpoint (admin/internal). **D-28-8** `200`-only verified write; `403/404/non-200/timeout/malformed ⇒ no write` (no verified-false); min token = repo-admin read. **D-28-9** per-tenant token value deferred (operator env now). **D-28-10** include `required_pull_request_reviews` in sufficiency. **D-28-11 (new)** repo + credential **resolved from the project's own intake** (`existing_assets_and_repositories` + `secrets_and_credentials_manifest`); no caller `repo_ref`. **D-28-12** broker params safe-only (`provider`/`branch`/`repo_ref_present`); `repo_ref` never in broker params/audit. **D-28-13 (new) — Gate-time repo binding (B1-cont):** gate #3 evaluates `latest_branch_protection_for_repo(provider, repo_ref, branch)` for the **currently declared** repo (shared `resolve_declared_repo`), not the project-only latest; missing/malformed declaration ⇒ fail-closed `branch_protection_repo_unbound`; the gate report exposes `branch_protection_repo_bound` (bool), **never the raw `repo_ref`**.

## 13. Security / fail-closed
Repo **bound to the project's own declaration** (B1) — an unrelated protected repo cannot satisfy gate #3. `repo_ref` never in broker params/audit (B2); token only in process env at call time, never persisted/audited/in params (`sanitize_params`, `registry.py:15-23`), never in `repo_ref` (`TOKENISH_RE`). New tool is a **read** (no mutation). `connector_verified` app-stamped on the verified path only (DB widens the allowed value; app enforces *when* — documented caveat). `200`-only verified writes; all error paths fail-closed (B3). Gate #3 trusts only the **latest, fresh, verified** snapshot **for the currently declared repo/branch** (B4 / B1-cont) — a revised declaration invalidates old-repo evidence, and an undeclared/malformed repo fails closed (`branch_protection_repo_unbound`). Tenant-scoped throughout (RLS); no cross-tenant repo/credential.

## 14. Implementation sequence (on approval; branch `feat/slice28-scm-connector`)
1. Tests (failing first): pure validator + sufficiency truth table; **repo-binding / unrelated-repo**; **broker safe-params**; **200-only / no-write error paths**; **gate #3 latest-wins + passed_gate_count R5/non-R5**; no-secret audit.
2. `ci_evidence.py` pure → `scm_connector.py` → `ci_evidence_service.py` (resolution + orchestration).
3. `registry.py` + `matrix.py`.
4. `migrations/0027` (guard `CREATE OR REPLACE`).
5. `repositories/ci_evidence.py` verified write → `production_autonomy.py` ladder + repo wiring → `config.py`.
6. Docs. Atomic commits per `github-flow`.

## 15. Required evidence before review
`ruff check .` clean; `make test` green; **fresh** `make test-db` (drop first) green incl. all §10 DB cases; `alembic 0027` up→down→up clean; gate #3 PASSes **only** on latest+verified+active+fresh for the project's own repo; unrelated-repo test green; go-live false everywhere; real counts in `CLAUDE.md`.

## 16. Must NOT claim
- That any gate other than #3 passes, or that go-live is enabled (`can_go_live_autonomously` false; `a5_satisfied` false).
- That `passed_gate_count` is 2 when gate #3 passes — it is `1 + (1 if R5 else 0)` (B5).
- That `connector_verified` is DB-attested — it is **app-enforced** (connector path sole writer).
- That the broker executes or that authority widened — decision-only; new tool is a read.
- That disabled/insufficient/stale protection passes, or that the connector records "verified-false" disabled protection (it does not — B3).
- That a caller-supplied repo can be evidenced, or that a snapshot for a **no-longer-declared** repo can satisfy gate #3 — the connector fetch AND gate #3 both bind to the project's **currently declared** repo; revising the declaration invalidates old-repo evidence, and an unbound declaration fails closed (`branch_protection_repo_unbound`) (B1 / B1-cont).
- That `GitHubSCMConnector` runs in tests — only `FakeSCMConnector` (no network).

## 17. Exit criteria
- The connector fetches **the project's own declared repo** (B1), via a broker-gated read with **safe params** (B2), writes `connector_verified` **only on a clean 200** (B3); the verified tier is writable only via the connector path.
- Gate #3 evaluates the latest snapshot **for the currently declared repo/branch** (B1-cont; `branch_protection_repo_unbound` when undeclared/malformed) and **PASSes** deterministically by the **latest-wins ladder** (B4) on latest+verified+enabled+pr_reviews+≥1 check+fresh, fail-closed otherwise; `passed_gate_count` is `1 + (1 if R5)` (B5); go-live stays false.
- `0027` reversible; `make test`/`make test-db` green fresh; unrelated-repo + no-secret tests green; honesty caveats documented.

---
**Awaiting PLAN v3 approval + rulings on D-28-1..13.** On approval: branch `feat/slice28-scm-connector` off `main`, TDD-first per §14, atomic commits, then pause for review. **No implementation until this PLAN is separately approved.**
