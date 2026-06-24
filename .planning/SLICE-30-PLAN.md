# Slice 30 — Production deployment-target verification connector (A5 gate #2) — PLAN v3

**Status:** AWAITING PLAN REVIEW (v1 REJECTED → v2 REJECTED → v3 binds probe semantics B-30-8 + fixes the negative-observation contradiction B-30-9) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**
**Persona:** senior backend / release-systems architect.
**Base:** `main` @ `1156b42`; working tree clean except the intentional local-only `.planning/HANDOFF.json` (M) + roadmap (untracked).
**Migration head:** `0028_pull_request_evidence` (verified) → new head **`0029`**. *(Roadmap's `0028` at `:238` is stale.)*
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:233-243`.

> **Revision log — v2 → v3 (both remaining blockers accepted):**
> - **B-30-8 — Probe semantics BOUND (exact v1 contract).** `method = GET`; `path = "/"` (**not configurable** this slice); `timeout = 5.0s`; redirects disabled; **`provisioned = (200 ≤ status ≤ 399) OR status ∈ {401, 403}`**. Removes the residual B-30-2 open choices (old D-30-2a/2b are now bound, not deferred).
> - **B-30-9 — Negative-observation write semantics FIXED (was a merge-blocking contradiction).** v2 wrongly said "any probe failure ⇒ no write", which lets an older fresh *passing* snapshot keep gate #2 green after a failed refresh (latest-wins reads stale evidence). v3: a **`connector_verified` NEGATIVE snapshot is written for every SAFELY-ATTEMPTED probe outcome**, so a negative refresh supersedes the old passing snapshot:
>   - **Non-serving HTTP status** (status not in the provisioned set, e.g. `500`/`502`): write `reachable=True, provisioned=False, target_available=False, observed_http_status=<status>`.
>   - **Transport/TLS/timeout AFTER SSRF-safe resolution:** write `reachable=False, provisioned=False, target_available=False, observed_http_status=NULL`.
>   - **NO write ONLY for** (not observations of the target — failures to *attempt*): target unbound/malformed, SSRF reject, broker deny.
>   - **Why this differs from Slice 28** (which writes no snapshot on a GitHub 404): a 404 there is *ambiguous* ("not protected" vs "no access"), so fabricating "verified-off" would be a false claim. Here, a safely-attempted probe that gets a definitive transport/HTTP result is an **unambiguous observation** that the target is not available right now — a real verified negative, required for latest-wins gate safety.

> **Revision log — v1 → v2 (carried; all verified):** B-30-1 scope BOUND verification-only (mutation deferred); B-30-2 `generic_https` read-only no-creds probe; B-30-3 exact resolver from file 16; B-30-4 SSRF guard; B-30-5 exact safe broker/audit metadata; B-30-6 `target_available == (provisioned AND reachable)` DB invariant; B-30-7 `deployment_evidence_max_age_hours = 24`.

> **Provenance (Sanad — read this session):** App. B #2 "production deployment target is available" (`docs/…v1_2.md:2986`); §5.2 "Deploy staging | A3+" (`:483`), "Deploy production | A4/A5" (`:485`); gate #2 today `production_deployment_target_available` → `insufficient_evidence` from `environments_declared` (`app/release/production_autonomy.py:149-156`); `environments_declared` ← declared `environments_and_deployment_targets` (`app/repositories/production_autonomy.py:52,82-84`; constant `app/intake/categories.py:55`); **file 16 production block** = `cloud_provider/region/domain/deployment_approval_required` (`16_environments_and_deployment_targets.yaml:5-9`); category data = **arbitrary non-secret JSON, no shape enforcement** (`app/intake/categories.py:138-148`); **no deploy code exists** (grep). Precedents: `branch_protection_snapshots`/`scm_connector`/`ci_evidence_service`/`project_repo` (26/28), `pull_request_evidence_snapshots`/`pr_evidence*` (29), migrations `0025`/`0028`. README test/CI (`README.md:19-32,53-58`).

---

## 0. Goal & non-goal
- **Goal.** Make **A5 gate #2 (`production_deployment_target_available`) PASS-capable**: a deterministic, tenant-owned **deployment-target evidence store** + a **broker-gated, SSRF-safe, read-only `generic_https` verification connector** that probes the project's OWN declared production target (`environments.production.domain`) and writes a **`connector_verified`** snapshot — **positive when serving, negative when safely-observed-unavailable** (B-30-9). Gate #2 PASSes only on **latest + verified + available + fresh** evidence for the currently declared target. (App. B #2 `spec:2986`.)
- **Non-goal.** **No production-deploy authorization** (A4/A5, `spec:485`). **No actual staging-deploy / mutation** (B-30-1 — deferred). **No A5 go-live** (≥10 gates remain). No caller-supplied target. **No credential** used/stored (unauthenticated probe). **No response body** read/stored/audited. No real network/DNS in tests.
- **In-scope A5 change (the deliverable):** edits `production_autonomy.py` **gate #2 only** + bumps `ruleset_version` → `slice30.v1`. A **no-other-gate-regression** test guards every other gate; `a5_satisfied`/go-live stay false.

## 1. Scope — D-30-1 RULED: verification-only (mutation deferred)
Gate #2 (`spec:2986`) needs only that the production target is **available** — a read-only verification. The actual staging deploy (A3+, `spec:483`) is the system's first **mutating** action and is deferred to its own slice. This PLAN is read-only end-to-end; the broker stays decision-only.

## 2. Evidence model + resolver + invariant

### 2.1 `resolve_declared_production_target` (B-30-3) — `app/release/project_repo.py`
Returns a bounded `target_ref` (the production host) or `None` (caller fails closed):
- **Category** `environments_and_deployment_targets`, **status `declared`** (else `None`).
- **Shape (file 16 `:5-9`):** read `data["environments"]["production"]` (dict); require a **non-blank string `domain`** ⇒ host.
- **Fail-closed → `None`:** missing category / status ≠ `declared` / explicit `not_applicable` / `data` not a dict / missing `environments` / missing/non-dict `production` / blank/non-string `domain` / **domain fails the §3.1 FQDN+SSRF rules** (IP/private/loopback/metadata ⇒ `None`, never probed).
- **Gate-time binding:** gate #2 resolves the **currently declared** `domain` and reads the **latest snapshot for that exact `target_ref`** (a revised domain invalidates old-target evidence; mismatch ⇒ not-pass).

### 2.2 `deployment_target_snapshots` (immutable latest-wins; mirror `pull_request_evidence_snapshots`)
> Naming deviation (as Slice 29): external-target **observation** ⇒ `deployment_target_snapshot.py`/`DeploymentTargetSnapshot` (immutable snapshot), not the roadmap's mutable `deployment_record.py` (that belongs to the deferred mutation slice).

Tenant-owned, RLS ENABLE+FORCE; **SELECT/INSERT only**; UPDATE/DELETE/TRUNCATE blocked; composite FK `(project_id, tenant_id)→projects`; `created_at DEFAULT clock_timestamp()`; two-tier `provenance`. Columns:
- **Identity/binding:** `id`, `tenant_id`, `project_id`, `provider` (CHECK `IN ('generic_https')`), `environment` (CHECK `IN ('production','staging')`; v1 writes `production`), `target_ref` (bounded FQDN host; CHECK shape + token/secret denylist, mirroring `ck_bps_repo_ref_not_tokenish`).
- **Verified facts:** `reachable` (bool), `provisioned` (bool), `target_available` (bool), `observed_http_status` (smallint null), `observed_at` (tz null).
- **Provenance/freshness:** `provenance` (CHECK two-tier), `created_at` (`clock_timestamp()`).
- **DB guard (BEFORE INSERT, mirror `0028`) — authoritative backstop:** provider/environment/provenance enums; `target_ref` FQDN shape + token/secret denylist; real bools; **B-30-6 invariant `target_available = (provisioned AND reachable)`** (RAISE on mismatch); `observed_http_status` NULL or 100–599. Append-only block triggers. **Migration `0029`** — additive; new table only.

## 3. Connector — `app/release/deploy_connector.py` (mirror `scm_connector.py`; fake-in-tests)
- `DeployTargetConnector` protocol + `FakeDeployTargetConnector` (**all tests/CI — no network/DNS**) + `GenericHttpsDeployTargetConnector` (**never exercised in CI**) + pure `map_https_probe(...)`.
- **Exact probe (B-30-8):** `generic_https`, **`GET https://{domain}/`** (path `"/"`, **not configurable**), **no `Authorization`/cookies/body**, **`timeout = 5.0s`**, **redirects disabled**.
- **Deterministic mapping (pure):**
  - serving: `observed_http_status ∈ [200,399] ∪ {401,403}` ⇒ `reachable=True, provisioned=True, target_available=True`.
  - non-serving status (any other received status, e.g. `404`/`500`/`502`): `reachable=True, provisioned=False, target_available=False, observed_http_status=<status>`.
  - transport/TLS/timeout (after SSRF-safe resolution): `reachable=False, provisioned=False, target_available=False, observed_http_status=NULL`.
  - **Always returns an observation for a safely-attempted probe** (never raises on transport failure — that IS the negative observation, B-30-9). It **raises `DeploySSRFRejected`** only when §3.1 forbids attempting (no observation).

### 3.1 SSRF / network safety (B-30-4) — resolver + connector, before any socket
HTTPS only · **FQDN only** (reject raw IPv4/IPv6 literals) · reject `localhost`/`*.local`/`*.internal` and any host that **resolves** into loopback (`127/8`,`::1`), private (`10/8`,`172.16/12`,`192.168/16`,`fc00::/7`), link-local (`169.254/16`,`fe80::/10`), multicast, reserved/`0.0.0.0`, **cloud-metadata** (`169.254.169.254`,`fd00:ec2::254`) · **DNS-resolve-then-pin** (anti-rebind; pin/re-validate the resolved IP) · **redirects disabled** · strict timeout · no body · no `Authorization` · no cookies · **no response body read/stored/audited** (only the numeric status + transport outcome). An SSRF violation ⇒ `DeploySSRFRejected` ⇒ **no write**.

## 4. Orchestration — `app/release/deploy_evidence_service.py` (mirror `ci_evidence_service.py`)
`refresh_deployment_target_evidence(...)`:
1. Resolve the project's own declared production target (§2.1). `None` ⇒ audited `target_unbound`, **no write**.
2. `broker_call` (SAFE params, §5) for `deployment.read_target_status`. Non-ALLOW ⇒ audited `broker_denied`, **no write**.
3. Probe via the injected connector (Fake in tests). `DeploySSRFRejected` ⇒ audited `ssrf_reject`, **no write**.
4. **Otherwise (any safely-attempted outcome — positive OR negative) ⇒ WRITE a `connector_verified` snapshot** with `target_available=(provisioned AND reachable)`, `observed_at=now` (B-30-9). So a later unavailable probe writes a newer verified-negative snapshot that supersedes any older passing one (latest-wins).
- Admin/internal — **no HTTP endpoint**. New setting `deployment_evidence_max_age_hours=24` in `app/config.py` (B-30-7).

## 5. Broker + policy + audit (B-30-5; least-privilege)
- `registry.py`: `deployment.read_target_status` → action `read_deployment_target` (read, `requires_approval=False`).
- `matrix.py`: `read_deployment_target: _r(L.A1)`. Broker decision-only; connector executes only on `ALLOWED_UNVERIFIED_IDENTITY`.
- **Safe broker params (EXACT):** `{"provider":"generic_https","environment":"production","target_present": true}` — **never** raw `domain`/`target_ref`/URL/resolved IPs/credential ref/headers.
- **Audit payload (EXACT):** `deployment_target_snapshot_id`, `project_id`, `provider`, `environment`, `reachable`, `provisioned`, `target_available`, `provenance`. **NEVER** `target_ref`/`domain`/URL/resolved IPs/headers/response body.

## 6. Gate #2 — repo-bound, latest-wins ladder (mirror Slice-28 gate-#3)
`production_autonomy.py` (gate #2 only) + repo wiring: resolve the currently declared target; evaluate the **latest snapshot for that `target_ref`**: `no_environment_declaration` → `environments_declared_but_no_target_evidence` → `deployment_target_observed_unverified` (latest ≠ `connector_verified`) → `deployment_target_evidence_stale` (older than `deployment_evidence_max_age_hours`) → `deployment_target_unavailable` (latest verified+fresh but `target_available=False` — the B-30-9 negative path) → **`passed`** (latest `connector_verified` + `target_available` + fresh). `ruleset_version` → `slice30.v1`. **Only gate #2 changes.**

## 7. Open decisions remaining (minor)
- **D-30-8 Trigger surface:** admin/internal connector method; no HTTP endpoint. *(rec: yes.)*
- *(B-30-8 closed the former D-30-2a/2b — method/path/timeout/status are now bound, not open.)*

## 8. Tests (DB-backed + Docker-free, per README `:19-32`)
- **Pure:** validators; `map_https_probe` **truth table** — serving set `[200,399]∪{401,403}`⇒available; `404`/`500`⇒`reachable=True,provisioned=False,available=False`; transport/TLS/timeout⇒`reachable=False,...,status=NULL`; **`target_available == provisioned AND reachable`** for all rows; caller path cannot assert `connector_verified`; connector path requires it + `observed_at`. **SSRF units:** non-https / IP-literal / localhost / `.local` / private / loopback / link-local / metadata / DNS-resolves-to-private ⇒ `DeploySSRFRejected` (no probe); redirect-not-followed.
- **Repository (db):** connector write stamps `connector_verified` (positive AND negative); latest-wins; counts; resolver fail-closed cases.
- **DB guard (db, direct SQL):** bad provider/environment/`target_ref`/token; **`target_available != (provisioned AND reachable)` rejected**; `observed_http_status` out of 100–599 rejected; append-only UPDATE/DELETE/TRUNCATE blocked; FK cross-project/tenant rejected; RLS cross-tenant empty.
- **Negative-supersedes (db, B-30-9) — REQUIRED:** record a positive (available) snapshot ⇒ gate #2 PASSES; then a negative refresh (non-serving status, and separately transport-fail) writes a newer verified-negative snapshot ⇒ gate #2 reads `deployment_target_unavailable` (**no longer passes**) for the same currently-declared target.
- **Broker/fail-closed (db):** broker-deny / SSRF-reject / target-unbound ⇒ **no write**; safely-attempted negative ⇒ **write**; no raw `target_ref`/domain/IP in `tool_calls.params`.
- **Safe audit (db):** target/domain/URL/IP/credential/headers/body never in audit.
- **Gate #2 (db):** PASS (verified+available+fresh) and fail (unverified/unavailable/stale/absent/unbound/target-mismatch); **no-other-gate-regression** (all gates except #2 byte-identical; `ruleset_version=="slice30.v1"`; go-live false).
- `make test` + fresh `make test-db` (drop→bootstrap→migrate→`-m db`) + alembic `0029` down/up round-trip; CI green (`README:53-58`).

## 9. Sequencing (TDD; mirror Slice 29)
1. Pure validators + `map_https_probe` (incl. negative rows) + SSRF guard + invariant (+ pure tests). 2. Model + migration `0029` (drop→migrate; DB-guard incl. invariant). 3. Repository + resolver (+ db tests incl. negative-supersedes). 4. Connector + Fake (+ mapping tests). 5. Service + registry/matrix + `config` freshness (+ broker/SSRF/write-vs-no-write tests). 6. Gate #2 ladder + repo wiring (+ PASS/fail + negative-supersedes + no-other-gate-regression). 7. Full `make test`/`make test-db`/alembic round-trip; CLAUDE.md + roadmap banner.

## 10. Risks / honesty caveats
- `connector_verified` is app-enforced, not DB-attested (documented caveat, as 26/28/29).
- **Verified negatives are real observations** (B-30-9) — unlike Slice-28's ambiguous 404 (no write), a safely-attempted deploy-probe result is unambiguous and IS written, so latest-wins cannot leave a stale passing snapshot active.
- "Available" = the target responds now, not a guarantee a deploy will succeed.
- Gate #2 binds the **currently declared** target (B1-cont).
- **SSRF** is the dominant risk for a user-declared probe; §3.1 is mandatory, tested, fail-closed.
- First A5-gate edit since Slice 28 — only gate #2 moves; the no-other-gate-regression test is the guardrail.

## 11. Must NOT claim
- That production deploy is authorized (A4/A5 — `spec:485`); only target availability is verified.
- That any gate other than #2 changes, or that go-live is enabled.
- That the connector deploys or mutates anything (read-only; broker decision-only).
- That `connector_verified` is DB-attested authenticity.

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A broker-gated, SSRF-safe, target-bound, read-only `generic_https` (`GET /`, 5s, no redirects, no creds) verification connector writes immutable `connector_verified` `deployment_target_snapshots` — **positive when serving, verified-negative for every safely-attempted unavailable outcome** — with `target_available = provisioned AND reachable`; append-only + RLS + DB-guard (incl. the invariant) + SSRF rejections proven by tests; **gate #2 PASSes only on latest verified + available + fresh evidence and STOPS passing after a negative refresh of the same target**; `ruleset_version=slice30.v1`, **no other gate's semantics change**; no target/credential/IP leak; `make test` + `make test-db` + alembic `0029` round-trip + CI green; go-live stays false.

---
**Review note:** PLAN v3 binds the exact probe contract (B-30-8: GET `/`, 5.0s, no redirects, provisioned = `200–399 ∪ {401,403}`) and fixes the negative-observation contradiction (B-30-9: verified-negative snapshots for every safely-attempted probe so latest-wins cannot leave an old passing target snapshot active; no-write only for unbound/SSRF-reject/broker-deny). Plan-only — no branch/code/migration/tests/PR until an approved plan + your explicit go.
