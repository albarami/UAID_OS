# Slice 26 — Source-control / CI evidence-provenance foundation (A5 gate #3) — Discussion v0

**Status:** OPEN — awaiting coordinator rulings on D-26-1..7 before any PLAN. **No branch, no code, no migration, no tests until PLAN v1 is separately approved.**
**Base:** `main` @ `3ec8116` (clean w.r.t. required scope; working tree is planning-only — the untracked, **approved** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` + the intentional `.planning/HANDOFF.json` drift).
**Persona:** senior release-governance / delivery-platform + Postgres-security architect.
**Authority for this slice:** the approved roadmap (`.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 "Slice 26", §6 "Recommended immediate next slice", and open decisions D-1/D-2/D-4). This discussion **refines** that entry into ruling-ready decisions; where it proposes a refinement of the approved roadmap, it says so explicitly.
**Goal:** lock the scope, provenance model, connector boundary, data model, the **conservative** A5 gate-#3 hook, and the test/evidence bar for a **deterministic, tenant-owned source-control / CI evidence-provenance store** — the first evidence class for A5 gate #3. **This slice builds no real connector, writes no verified evidence, and never lets gate #3 PASS.**

Provenance (Sanad): every shape/rule claim cites a spec line or a source file; reasoned choices not dictated by a single source are labelled **(inference)**.

---

## 1. What the spec requires / enables

- **Appendix B gate #3 (spec:2987):** A5 requires "branch protection and required checks are active." Today the evaluator returns `no_evidence_source:ci_branch_protection` (`app/release/production_autonomy.py:212`) — there is no store and no source.
- **§5.2 authority matrix (spec:484):** "Merge to protected branch — **A4+** — Required reviews and status checks." Branch protection + required status checks is the concrete control gate #3 is asserting; it is a **configuration state** of the source-control repo.
- **§12.4 PR workflow (spec:1224):** "PRs cannot merge until **required checks pass and required reviewers approve**." This is the *operational* counterpart (the PR-merge evidence) — it belongs to the **PR-evidence connector (Slice 29)** and the **test-oracle execution (gate #4, Slice 43)**, **not** to gate #3's *configuration* evidence. Keeping these apart prevents gate #3 (config "active") from being conflated with gate #4 (checks "pass").
- **§26.3 Phase 3 (spec:2461-2472):** source control, pull requests, CI/CD are Phase-3 controlled integrations. Slice 26 builds the **store/provenance substrate**; the **real connector** is Slice 28 (roadmap §5).
- **§16.4 tool privilege escalation (spec:1589-1603) + §11 tool broker:** any *real* read of branch-protection config must go through the deny-by-default broker with a verified, least-privilege connector — **out of scope here** (Slice 28).
- **Pattern precedent — immutable append-only snapshots:** `readiness_reports` (Slice 12; `app/models/readiness_report.py`, migration `0015`) and `intake_findings_reports` (Slice 13, migration `0016`) are tenant-owned, RLS `ENABLE`+`FORCE`, **append-only** (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked), `created_at = clock_timestamp()`. **(inference)** CI evidence is *observational snapshots*, not a lifecycle entity, so it should follow **this** precedent — not the mutable `open→terminal` lifecycle of `release_findings`/`release_issues` (no events table, no status machine).
- **Provenance convention:** `release_findings`/`release_issues`/`risk_acceptance_records` stamp `source_provenance = "caller_supplied_unverified"` (`app/release/findings.py`, etc.). Slice 26 extends this to a **two-tier** axis (roadmap D-2).

## 2. The honest dependency reality (why gate #3 still won't PASS in Slice 26)

A store of branch-protection observations does **not** prove branch protection is *actually* active: in Slice 26 every row is **caller-supplied and unverified** (no connector reads the real config until Slice 28). **(inference)** A caller/agent could assert "protection on" with no truth behind it. Therefore:
- Gate #3 moves `no_evidence_source` → **`insufficient_evidence`** (a store now exists) **but never PASSes** — exactly mirroring how Slice 23 moved gates #5/#6 to `insufficient_evidence:no_finding_provenance_or_scan_source` without ever passing.
- The **PASS path** (keyed on `connector_verified` evidence) is **deliberately not implemented this slice** — it lands in **Slice 28** (real connector) and is additionally gated behind the **Slice 27 request-auth policy** (roadmap D-1: no non-#1 gate PASSes before request-auth).
- This keeps the slice **fail-closed and self-contained**: it can ship before Slice 27 because it adds **no** authorization path at all.

---

## 3. Decisions to resolve

### D-26-1 — Slice 26 scope (source-control / CI evidence-provenance for gate #3)
**Recommend:** Slice 26 ships a single evidence class — **branch-protection configuration snapshots** — plus the conservative gate-#3 hook. A snapshot records, for a protected branch: protection enabled? required pull-request reviews? the set/count of required status checks? enforce-admins? — i.e. the **configuration** gate #3 asserts ("active").
- **Refinement of the approved roadmap (flagged):** the roadmap §5 Slice-26 entry named **two** model files (`branch_protection_snapshot.py` **and** `ci_check_result.py`). On reflection, gate #3 is a **configuration** gate, while per-check *run results* (pass/fail) are gate #4 (Slice 43) and PR-merge evidence (Slice 29). **Recommend deferring `ci_check_results` to Slice 28/29** to keep Slice 26 tight and avoid overlapping gate #3 with gate #4. *(Ruling: (a) branch-protection-snapshots only — recommended — or (b) keep both tables as the roadmap listed?)*
- **Out of scope (this slice):** any real connector/broker call, secrets-reference verification (Slice 32), PR evidence (Slice 29), test-oracle/check results (gate #4, Slice 43), and any gate-#3 PASS path (Slice 28).
*(Ruling: confirm the single-evidence-class scope + the deferral.)*

### D-26-2 — Ordering vs Slice 27 (what Slice 26 may do before request-auth; what stays blocked)
**Recommend:**
- **Slice 26 may, before Slice 27:** create the store (with the full two-tier provenance **enum reserved** in the schema), write only **`caller_supplied_unverified`** rows, and wire gate #3 → `insufficient_evidence` (context only). None of this needs request-auth.
- **Must remain blocked until Slice 27 (+ Slice 28):** gate #3 ever reaching **PASS**. Per roadmap D-1, no non-#1 gate PASSes before request-auth; and technically a `connector_verified` row can only be produced by the trusted connector (Slice 28).
- **Clarifying ruling:** is request-auth a **hard technical** prerequisite for gate-#3 PASS, or a **policy** prerequisite? **Recommend treating it as moot for Slice 26**, because Slice 26 implements **no PASS path whatsoever** — the gate stays `insufficient_evidence` unconditionally (even if a `connector_verified` row hypothetically existed, Slice 26's evaluator would still not pass it; the PASS logic is added in Slice 28). This is the most fail-closed reading.
*(Ruling: confirm Slice 26 ships before Slice 27, adds no PASS path, and reserves — but does not enable — the verified tier.)*

### D-26-3 — Provenance model (observed-unverified vs verified)
**Recommend** a single `provenance` column on the snapshot, CHECK-constrained to **two values**:
- **`caller_supplied_unverified`** — a caller/agent asserted the configuration; **not** trustworthy. **The only value Slice 26 may write** (the DB guard forces it on INSERT, exactly as `release_findings`/`release_issues` force their unverified provenance).
- **`connector_verified`** — a trusted, broker-mediated source-control connector directly read the config from the provider API. **Reserved in the schema, not writable in Slice 26** (Slice 28 relaxes the guard to admit connector-written rows through the trusted path).
- **Naming:** reuse the existing token `caller_supplied_unverified` (cross-store consistency with `findings.py`/`issues.py`) rather than a new `observed_unverified`. *(inference)*
*(Ruling: (a) one `provenance` column with these two values; (b) Slice 26 writes only `caller_supplied_unverified`, guard-enforced; (c) `connector_verified` reserved but unusable this slice.)*

### D-26-4 — Connector scope (GitHub-first / CI-first boundary)
**Recommend:** Slice 26 builds **no connector** — the store schema is **provider-agnostic but GitHub-shaped**: a `provider` column (e.g. `"github"`), a repo **identifier** (slug, **never** a credentialed URL), `branch`, and provider-neutral config fields. This records the roadmap D-4 decision (**GitHub-first**, behind a thin adapter generalized later in Slice 61) so the eventual connector (Slice 28) needs **no migration** to fit.
- **Boundary:** the first real connector (Slice 28) targets GitHub because the repo already uses `.github/workflows/ci.yml` + the `gh` CLI (**inference**). Other providers + the connector library are Slice 61.
*(Ruling: (a) provider-agnostic, GitHub-shaped schema now; (b) no connector this slice; (c) GitHub-first confirmed for Slice 28.)*

### D-26-5 — Data model / tenant ownership / RLS / FKs / audit / immutability
**Recommend** one table, **`branch_protection_snapshots`** (tenant-owned), modelled on the **immutable append-only snapshot** precedent (`readiness_reports`), **not** the lifecycle-store precedent:
- **Columns:** `id`, `tenant_id`, `project_id`, `provider`, `repo_ref` (slug/identifier — no secrets), `branch`, `protection_enabled` (bool), `required_pull_request_reviews` (bool), `required_status_checks` (jsonb list of check names) + `required_status_check_count` (int, derived/denormalized for safe context), `enforce_admins` (bool), `provenance` (enum, D-26-3), `observed_at` (timestamptz), `created_at` (`clock_timestamp()` for deterministic newest-first ordering, per `readiness_reports`).
- **Tenant ownership / RLS:** RLS `ENABLE`+`FORCE` + `tenant_isolation`; composite FK `(project_id, tenant_id) → projects(id, tenant_id)`; runtime role `uaid_app`.
- **Append-only / immutable:** grants `SELECT, INSERT` only; UPDATE/DELETE/TRUNCATE blocked by triggers (mirrors `readiness_reports`/`intake_findings_reports`). **No events table, no status machine** — a snapshot is immutable; "newest wins" by ordering.
- **DB guard (INSERT invariants):** `provenance = 'caller_supplied_unverified'` (rejects `connector_verified` this slice); booleans non-null; `required_status_check_count >= 0`; provider in an allowlist.
- **Audit (safe-metadata only):** ids / provider / branch / booleans / `required_status_check_count` / provenance — **never** `repo_ref` if it could embed anything sensitive (recommend ids + provider + provenance + counts only; **never** tokens/URLs/check-name lists), mirroring the Slice-23/24 audit discipline.
- **Read surface:** a minimal GET endpoint `GET /api/projects/{id}/ci_evidence` returning the **latest** snapshot (or `null`) — or the list — mirroring the Slice-17/19 readiness/findings read pattern (`app/api/dashboard.py`), GET-only, `require_tenant` → `tenant_scope`/RLS, cross-tenant ⇒ `null`/`[]`.
- **Pure module:** `app/release/ci_evidence.py` (validators + the provenance/provider constants), following `app/release/release_candidates.py` conventions (module-level tuples + fail-closed `validate_*`).
*(Ruling: (a) snapshot-not-lifecycle model; (b) columns + `clock_timestamp()` ordering; (c) RLS/FK/append-only/guard shape; (d) audit fields; (e) the read endpoint; (f) migration `0025_ci_evidence.py`, additive only — no change to existing tables.)*

### D-26-6 — A5 gate-#3 evaluator impact (no PASS overclaim)
**Recommend** the conservative hook, mirroring Slices 23–25:
- Gate #3 moves from `no_evidence_source:ci_branch_protection` → **`insufficient_evidence`**, with the reason **narrowing** by state (**(inference)**, matching the Slice-25 narrowing pattern):
  - no snapshot for the project → `insufficient_evidence:no_branch_protection_evidence`;
  - ≥1 snapshot, all `caller_supplied_unverified` → `insufficient_evidence:branch_protection_observed_unverified`.
- **Gate #3 NEVER passes this slice** (no `connector_verified` evidence is writable, and **no PASS path exists** — the PASS logic is Slice 28). Even a hypothetical verified row would not flip it in Slice 26.
- **`context` (safe metadata only — never prose/tokens):** `branch_protection_snapshot_count`, `connector_verified_snapshot_count` (= 0 this slice), `latest_snapshot_provenance`, `latest_protection_enabled` (**observed, unverified** — explicitly *not* an assertion that protection is on), `latest_required_status_check_count`.
- **Gate-set move:** gate #3 leaves the SOURCELESS set `{3,4,10,11,13}` and joins the PARTIAL set `{2,5,6,7,8,9,12}` → PARTIAL `{2,3,5,6,7,8,9,12}`, SOURCELESS `{4,10,11,13}` (the README/test-asserted sets). `passed_gate_count` stays **1** at R5; `unmet_gates` stays **12**.
- **Wiring:** `ProductionAutonomyRepository.evaluate` reads a new `CIEvidenceRepository` (counts + latest snapshot) inside `tenant_scope`/RLS and passes new kwargs to `evaluate_production_autonomy` (additive signature, defaults False/0 — fail-closed, as in `app/release/production_autonomy.py:97-119`).
- `production_autonomy` `ruleset_version` → **`slice26.v1`**.
*(Ruling: (a) narrow-by-state reason; (b) the context keys; (c) gate #3 must NOT pass; (d) gate-set move + `slice26.v1`.)*

### D-26-7 — Tests and acceptance evidence
**Recommend** (mirroring the existing `make test` / `make test-db` split):
- **Pure unit (`not db`, Docker-free):** provenance/provider/field validators (fail-closed); the gate-#3 evaluator transition — `no_evidence_source → insufficient_evidence`; reason narrows by state; **gate #3 NEVER `passed`** across all inputs (no snapshot / unverified snapshot(s) / even a hypothetical `connector_verified` row); `context` shape + safe-metadata only; gate-set membership (`3 ∈ PARTIAL`); `ruleset_version == "slice26.v1"`.
- **DB-backed (`db`):** migration `0025` applies; **RLS** cross-tenant isolation (a tenant cannot read another tenant's snapshots; cross-tenant `project_id` ⇒ empty/`null`); **append-only** (UPDATE/DELETE/TRUNCATE blocked); **DB-guard INSERT** forces `caller_supplied_unverified` (rejects a `connector_verified` write this slice); composite FK pins project+tenant (cross-project/cross-tenant insert rejected); **audit safe-metadata only** (no `repo_ref`/check-name lists/tokens in the audit payload); catalog/grants (`SELECT, INSERT` only, **no DELETE/UPDATE**).
- **A5 wiring (`db`):** the `production_autonomy` report shows gate #3 `insufficient_evidence` + the context counts; `a5_satisfied` false; `can_go_live_autonomously` false; `ruleset_version` `slice26.v1`.
- **Read API (`db`):** `GET /api/projects/{id}/ci_evidence` returns the latest snapshot or `null`; cross-tenant ⇒ `null` (no leak); GET-only (405 on mutation).
- **Acceptance evidence:** `make test` + `make test-db` green with updated counts; a sample `production_autonomy` report JSON showing gate #3 `insufficient_evidence` with context as the honest artifact-of-done.
*(Ruling: confirm the test matrix + the acceptance-evidence bar.)*

---

## 4. Coordinator rulings needed before a PLAN
- **D-26-1** scope: branch-protection-snapshots only (defer `ci_check_results`) — or keep both tables?
- **D-26-2** ordering: Slice 26 ships before Slice 27, adds **no** PASS path, reserves but does not enable the verified tier.
- **D-26-3** provenance: one `provenance` column, two values, Slice 26 writes only `caller_supplied_unverified` (guard-enforced).
- **D-26-4** connector: provider-agnostic, **GitHub-shaped** schema now; no connector this slice; GitHub-first for Slice 28.
- **D-26-5** data model: immutable append-only **snapshot** (not lifecycle); columns; RLS/FK/guard/audit; read endpoint; additive migration `0025`.
- **D-26-6** A5 hook: gate #3 → `insufficient_evidence` (reason narrows by state), context counts, **never passes**, gate-set move, `ruleset_version` `slice26.v1`.
- **D-26-7** tests + acceptance evidence bar.

## 5. Recommendation
Build a **deterministic, tenant-owned source-control / CI evidence-provenance store** as a single immutable, append-only **`branch_protection_snapshots`** table (RLS, no-DELETE, DB-guarded, audit safe-metadata only), with a **two-tier `provenance`** axis whose **verified tier is reserved but unwritable** this slice, a **GitHub-shaped, connector-less** schema, a minimal read endpoint, and a **conservative A5 gate-#3 hook** that moves gate #3 `no_evidence_source → insufficient_evidence` (reason narrowing by state) with safe context counts but **never PASSes** (`ruleset_version` → `slice26.v1`). Gate #3 gets its first evidence class with **no connector, no verified evidence, no PASS, no go-live** — fail-closed, self-contained, and shippable before Slice 27. **Pausing for rulings on D-26-1..7 before any PLAN v1.**
