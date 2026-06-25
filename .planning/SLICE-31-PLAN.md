# Slice 31 — Monitoring / alerts evidence connector (A5 gate #11) — PLAN v5

**Status:** AWAITING PLAN REVIEW (v1→v4 REJECTED; v5 fixes B10 — containment vs pinned-request mechanics) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**
**Persona:** senior backend / release-systems / observability architect.
**Base:** `main` @ `9825757`; working tree clean except the intentional local-only `.planning/HANDOFF.json` (M) + roadmap (untracked).
**Migration head:** `0029_deployment_target_evidence` (verified) → new head **`0030`**. *(Roadmap's `0029` at `:250` is stale.)*
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:245-255`.

> **Revision log — v4 → v5 (B10 accepted — containment vs pinned-request mechanics):**
> - **B10 — Containment scoped to PERSISTED/EXPOSED surfaces; transient connector use allowed.** v4's "URL/host/path never in the pinned URL" contradicted the required pinned request (`https://{ip}{path}`). v5: **containment = no `status_url`/host/path in broker params, audit payloads, gate context/report/API, or logs** (the persisted/exposed surfaces). The resolver/connector **may use host/path in memory** solely to build the SSRF-pinned outbound request. **Pinned request shape (bound):** URL = `https://{validated_ip}{normalized_path}`, the **original hostname** is used only for `Host` + TLS-SNI/cert verification, **no credentials** (B9), and the **pinned URL is never logged/audited/persisted** (it is transient). (§3.1/§10/§12; new pinned-request-shape test §8.)
>
> **Revision log — v3 → v4 (B9 accepted — credential-audience safety):**
> - **B9 — Bearer auth REMOVED (Option A, the safest bind).** SSRF safety ≠ credential-audience safety: with auth enabled, the operator's global token could be sent to any project-declared public HTTPS host (the declarer controls `status_url`; `categories.py:138-148` accepts arbitrary non-secret JSON). v4 binds **`generic_monitoring_api` as UNAUTHENTICATED-ONLY**: there is **no `MONITORING_API_TOKEN`, no `auth` field, and the connector NEVER sends an `Authorization` header** (so there is no credential to mis-target or leak). The declared schema is `{provider, status_url}` only; auth-required providers will 401/403 ⇒ honest `http_error` negative (gate stays unmet). **Authenticated monitoring providers — with an operator-controlled credential-audience allowlist / token-host mapping (the rejected Option B model) — are explicitly DEFERRED to a dedicated follow-up slice** where that security surface gets its own review. (§1/§2.1/§3.1/§4.)
>
> **Revision log — v2 → v3 (all three accepted):**
> - **B6 — Per-`failure_kind` read-state invariants are now fully DB-enforced** (§2.2): `response_valid=true` ⟹ `provider_reachable=true AND observed_http_status=200 AND failure_kind IS NULL AND counts non-null+bounded AND active-booleans consistent`; `failure_kind='unreachable'` ⟹ `provider_reachable=false AND observed_http_status IS NULL`; `failure_kind='http_error'` ⟹ `provider_reachable=true AND observed_http_status IS NOT NULL AND observed_http_status<>200`; `failure_kind IN ('content_type','oversize','malformed')` ⟹ `provider_reachable=true AND observed_http_status=200`. Direct-SQL tests reject each inconsistent state (§8).
> - **B7 — Count bounds BOUND to `0..32767`** (smallint range, §2.2/§3.2): the connector treats a JSON count outside `0..32767` as **`malformed`** (NULL counts), so no value is undefined. Pure + DB tests.
> - **B8 — "No leak" scoped precisely** (§10/§12): the `status_url`/host/path are **persisted only** in the internal snapshot `target_ref` column; they must **never** appear in broker params, audit payloads, gate context / API responses, or logs. *(Refined by B10: the transient SSRF-pinned outbound request necessarily uses host/path in memory; see the v4→v5 log.)*
>
> **Revision log — v1 → v2 (all blockers accepted):**
> - **B1 — All decisions BOUND** (no recommendations/coordinator-confirm items left): D-31-1…7 are ruled below (§1, §7).
> - **B2 — Binding can't go stale.** The snapshot identity + gate lookup key is the **full normalized `status_url`** (host **AND** path), not just the host — a path/config change invalidates old evidence (§2.1/§2.2/§5).
> - **B3 — Deterministic response contract** (§3.2): exact JSON object, field names, types, bounds, status + content-type handling. No "enabled booleans" — the two integer **counts** are the sole signal.
> - **B4 — Evidence honesty FIXED (was fake-zero counts).** A failed/malformed read is **NOT** "0 monitors / 0 alerts". The model adds read-state fields `provider_reachable` / `response_valid` / `failure_kind` / `observed_http_status` and **NULLABLE** counts; counts are non-null **only** when actually parsed from a valid provider response (§2.2). Gate reasons are split so we never claim "alerts inactive" when the provider was unreadable (§5).
> - **B5 — Credential/auth model BOUND** (§3.1): unauthenticated by default; optional declared **Bearer** auth resolving the token from operator env `MONITORING_API_TOKEN` (reference-only, fail-closed empty ⇒ no read; never stored/audited/in params/in the pinned URL).
> - **URL/path safety BOUND** (§2.1): HTTPS only; no userinfo/query/fragment; port 443 only; host = SSRF-safe FQDN; path normalized + bounded; the full URL is the binding key.

> **Provenance (Sanad — read this session):** App. B #11 "monitoring and alerts are active" (`docs/…v1_2.md:2995`, list `:2985-2997`); gate #11 today `_no_source(11, "monitoring_and_alerts_active", "monitoring")` (`app/release/production_autonomy.py:291`, gate list `:279-293`); file 22 `operations_observability_support.md` = free-form markdown (`:1-26`; spec file-22 desc `:394`); category `operations_observability_support` declarable (`app/intake/categories.py:59`); category store = arbitrary non-secret JSON (`app/intake/categories.py:138-148`); `stabilization_window_policy.yaml:10` `monitoring_confirmed_active: true`; monitoring tool surface `:1099`; **no monitoring evidence code / tool / action exists** (grep). Reuse (merged): Slice-30 `deploy_evidence.py` (SSRF guard, invariant, verified-negative), `deploy_connector.py` (connect-time IP pinning incl. **IPv6 bracketing**, status-only stream, DNS-fail-closed), `deploy_evidence_service.py`, `repositories/deployments.py`, `resolve_declared_production_target` in `project_repo.py`, migration `0029`, gate-#2 ladder; Slice-28 `scm_connector` (broker-gated provider connector + operator-env credential `GITHUB_CONNECTOR_TOKEN`, fail-closed). README test/CI (`README.md:19-32,53-58`).

---

## 0. Goal & non-goal
- **Goal.** Make **A5 gate #11 (`monitoring_and_alerts_active`) PASS-capable**: a deterministic, tenant-owned **monitoring-status evidence store** + a **broker-gated, SSRF-safe** connector that performs a **bounded JSON read** of the project's OWN declared monitoring status API and **verifies ≥1 active monitor AND ≥1 active alert rule**, writing a **`connector_verified`** snapshot. Gate #11 PASSes only on **latest + verified + active + fresh** evidence for the currently declared binding (App. B #11 `spec:2995`; `monitoring_confirmed_active` `stabilization_window_policy.yaml:10`).
- **Non-goal.** **No post-launch operational completeness** (the §25.1 operational signals / stabilization window are Slices 56–59, roadmap `:247,:254`). No A5 go-live. No caller-supplied endpoint. **No secret value stored** (reference-only). **No monitor/alert names/IDs/labels/prose/raw payload stored or audited.** No real network in tests.
- **In-scope A5 change (the deliverable):** edits `production_autonomy.py` **gate #11 only** + bumps `ruleset_version` → `slice31.v1`. A **no-other-gate-regression** test guards every other gate; `a5_satisfied`/go-live stay false.

## 1. Bound decisions (D-31-1…7)
- **D-31-1 Verification model — BOUND: provider-read.** The connector reads the monitoring provider's status API and verifies active monitor + alert-rule counts. (Rejected: generic_https reachability — proves nothing about alerts; caller-declared — a declaration is not verified evidence, §2.3.)
- **D-31-2 Provider — BOUND: a single `generic_monitoring_api`** contract this slice (operator-configured; named vendors deferred). The connector adapter is provider-specific + fake-in-tests; model/gate/SSRF are provider-agnostic.
- **D-31-3 Declared config — BOUND** (under `operations_observability_support.data`): a `monitoring` object `{ "provider": "generic_monitoring_api", "status_url": "https://<host>/<path>" }` — **no credential/auth field** (B9: unauthenticated-only). Any credential-like key in the declaration is ignored (the connector never sends auth).
- **D-31-4 Bounded JSON contract — BOUND** (§3.2).
- **D-31-5 Active thresholds — BOUND:** `monitoring_active = active_monitor_count >= 1`; `alerts_active = active_alert_rule_count >= 1`; `overall_active = monitoring_active AND alerts_active`.
- **D-31-6 Freshness — BOUND:** `monitoring_evidence_max_age_hours = 24` (own setting in `app/config.py`).
- **D-31-7 Trigger surface — BOUND:** admin/internal connector method; **no HTTP endpoint**.

## 2. Evidence model + resolver

### 2.1 `resolve_declared_monitoring_target` (B2/URL-safety) — `app/release/project_repo.py`
Returns a bounded `(status_url, host, path)` or `None` (caller fails closed). From the declared `operations_observability_support` category (status `declared`), read `data["monitoring"]`:
- `provider` must equal `generic_monitoring_api`.
- `status_url` parsed + validated (fail-closed → `None`): **scheme == https**; **no userinfo** (`@`); **no query** (`?`) / **no fragment** (`#`); **port 443 only** (absent or explicit 443); **host** passes the SSRF host-shape rules (`validate_target_host`); **path** starts with `/`, is normalized (reject `..`, `//`, whitespace/control), and ≤ 256 chars; the **full normalized URL** ≤ 2048 chars + token denylist.
- **No credential** (B9): the resolver returns no auth; the connector sends no `Authorization` header. Any `auth`/credential-like key in the declaration is ignored.
- **Gate-time binding (B2):** gate #11 resolves the **currently declared** `status_url` and reads the **latest snapshot for that exact `target_ref = status_url`** — a path/host/provider change invalidates old evidence.

### 2.2 `monitoring_status_snapshots` (immutable latest-wins; mirror `deployment_target_snapshots`; B4 read-state)
Tenant-owned, RLS ENABLE+FORCE; SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked; composite FK `(project_id, tenant_id)→projects`; `created_at DEFAULT clock_timestamp()`; two-tier `provenance`. Columns:
- **Identity/binding:** `id`, `tenant_id`, `project_id`, `provider` (CHECK `IN ('generic_monitoring_api')`), **`target_ref`** = the full normalized `status_url` (CHECK: HTTPS-URL shape + bounded + token denylist `ck_mss_target_ref_not_tokenish`).
- **Read state (B4 — honesty):** `provider_reachable` (bool), `response_valid` (bool), `observed_http_status` (smallint NULL; CHECK null or 100..599), `failure_kind` (text NULL; CHECK null or `IN ('unreachable','http_error','content_type','oversize','malformed')`).
- **Verified facts (NULLABLE counts; B7 bounds):** `active_monitor_count` (smallint **NULL**; CHECK `null OR (BETWEEN 0 AND 32767)`), `active_alert_rule_count` (smallint **NULL**; CHECK `null OR (BETWEEN 0 AND 32767)`), `monitoring_active` (bool), `alerts_active` (bool), `overall_active` (bool). *(The connector maps any JSON count outside 0..32767 to `failure_kind='malformed'` with NULL counts — §3.2 — so a smallint overflow can never reach the column.)*
- **Provenance/freshness:** `provenance` (two-tier CHECK), `observed_at` (tz NULL), `created_at` (`clock_timestamp()`).
- **DB-guard CHECKs (authoritative; mirror `0029` CHECK-only design — the honesty invariants live in the DB, B6):**
  - `overall_active = (monitoring_active AND alerts_active)` (B-30-6 lesson).
  - **valid-read invariant:** `response_valid` ⟹ `provider_reachable = true AND observed_http_status = 200 AND failure_kind IS NULL AND active_monitor_count IS NOT NULL AND active_alert_rule_count IS NOT NULL AND monitoring_active = (active_monitor_count >= 1) AND alerts_active = (active_alert_rule_count >= 1)`.
  - **failed-read invariant:** `NOT response_valid` ⟹ `failure_kind IS NOT NULL AND active_monitor_count IS NULL AND active_alert_rule_count IS NULL AND monitoring_active = false AND alerts_active = false`.
  - **per-`failure_kind` read-state invariants (B6):**
    - `failure_kind = 'unreachable'` ⟹ `provider_reachable = false AND observed_http_status IS NULL`.
    - `failure_kind = 'http_error'` ⟹ `provider_reachable = true AND observed_http_status IS NOT NULL AND observed_http_status <> 200`.
    - `failure_kind IN ('content_type','oversize','malformed')` ⟹ `provider_reachable = true AND observed_http_status = 200`.
  - Append-only block triggers. **Migration `0030`** — additive; new table only.

## 3. Connector — `app/release/monitoring_connector.py` (mirror `deploy_connector.py`; fake-in-tests)
- `MonitoringConnector` protocol + `FakeMonitoringConnector` (**all tests/CI — no network/DNS**) + `GenericMonitoringApiConnector` (**never CI-tested**) + pure `map_monitoring_response(...)`.

### 3.1 SSRF + unauthenticated (reuse Slice-30 verbatim; B9)
- `validate_target_host(host)` + DNS-resolve + `assert_safe_resolved_ips` **before any socket**; **connect-time IP pinning** (anti-rebind, IPv6 bracketed); DNS-failure ⇒ `MonitoringSSRFRejected` (no write).
- **Pinned request shape (B10, bound):** the outbound URL is **`https://{validated_ip}{normalized_path}`**; the **original hostname** is used only for the `Host` header + TLS-SNI/cert verification; the request is transient and the **pinned URL is never logged / audited / persisted** (host/path are persisted only in `target_ref`, §2.2). The connector legitimately holds host/path in memory solely to build this request.
- **Unauthenticated-only (B9):** the connector sends **no `Authorization` header, no cookies, no credential of any kind** — there is no operator token in this slice, so nothing can be mis-targeted at a project-declared host or leaked. An auth-required endpoint simply returns 401/403 ⇒ `http_error` (an honest negative; gate stays unmet).

### 3.2 Bounded JSON read contract (D-31-4, B3)
- `GET {status_url}` pinned, timeout 5.0s, **redirects off**, `Accept: application/json`.
- **Read-state mapping (B4):**
  - transport/TLS/timeout ⇒ `provider_reachable=False, response_valid=False, failure_kind='unreachable', observed_http_status=NULL, counts=NULL, overall_active=False`.
  - response received, status ≠ 200 ⇒ `provider_reachable=True, response_valid=False, failure_kind='http_error', observed_http_status=<status>, counts=NULL`.
  - status 200 but Content-Type not `application/json` ⇒ `failure_kind='content_type'` (response_valid False, counts NULL).
  - body exceeds **64 KiB** cap (streamed) ⇒ `failure_kind='oversize'` (response_valid False, counts NULL).
  - body within cap but not a strict-shape JSON object `{active_monitor_count:int 0..32767, active_alert_rule_count:int 0..32767}` (missing/extra/wrong-type/negative/**> 32767**, B7) ⇒ `failure_kind='malformed'` (response_valid False, counts NULL).
  - **valid:** `response_valid=True, provider_reachable=True, failure_kind=NULL`, counts set; `monitoring_active`/`alerts_active`/`overall_active` per D-31-5. **No names/IDs/labels/prose/raw payload retained** — only the two integer counts.
- **B-30-9:** every safely-attempted read (valid OR any failure_kind) is a real observation and is written `connector_verified`. **No write only** for unbound / SSRF-reject / broker-deny.

## 4. Orchestration — `app/release/monitoring_evidence_service.py` (mirror `deploy_evidence_service.py`)
`refresh_monitoring_evidence(...)`: resolve the project's own declared monitoring binding (`None` ⇒ audited `monitoring_unbound`, no write) → `broker_call` (SAFE params, §6); non-ALLOW ⇒ **audited `broker_denied`** (B3-Slice30 lesson), no write → SSRF-safe **unauthenticated** bounded read via the injected connector; `MonitoringSSRFRejected` ⇒ audited `ssrf_reject`, no write → **write a `connector_verified` snapshot for every safely-attempted outcome** (valid or failure_kind). New setting `monitoring_evidence_max_age_hours=24` in `app/config.py`. Admin/internal — no HTTP endpoint.

## 5. Gate #11 — repo-bound, latest-wins ladder; honest split reasons (B4)
`production_autonomy.py` (gate #11 only) + repo wiring: resolve the currently declared binding; latest snapshot for that `target_ref`:
- not bound ⇒ `no_monitoring_declaration`
- no snapshot ⇒ `monitoring_declared_but_no_evidence`
- latest ≠ `connector_verified` ⇒ `monitoring_observed_unverified`
- verified but stale ⇒ `monitoring_evidence_stale`
- verified+fresh but `response_valid=False` ⇒ **`monitoring_evidence_unreadable`** (NEVER "inactive" — B4; `context.failure_kind` carries the detail)
- verified+fresh, `response_valid=True`, `overall_active=False` ⇒ **`monitoring_or_alerts_inactive`**
- verified+fresh + `overall_active` ⇒ **`passed`** (`monitoring_and_alerts_active_verified`).
`ruleset_version` → `slice31.v1`. **Only gate #11 changes.** Gate #11 becomes the **4th** PASS-capable gate (#1/#2/#3/#11); `a5_satisfied`/go-live stay false (≥9 gates unmet).

## 6. Broker + policy + audit
- `registry.py`: `monitoring.read_status` → action `read_monitoring_status` (read, `requires_approval=False`).
- `matrix.py`: `read_monitoring_status: _r(L.A1)` (A1 read; non-§2.6; aligns with `:1099` "read logs").
- **Safe broker params (EXACT):** `{"provider":"generic_monitoring_api","monitoring_present": true}` — never the url/host/path/credential/IPs.
- **Audit payload (EXACT):** `monitoring_status_snapshot_id`, `project_id`, `provider`, `provider_reachable`, `response_valid`, `failure_kind`, `monitoring_active`, `alerts_active`, `overall_active`, `active_monitor_count`, `active_alert_rule_count`, `provenance`. **NEVER** target_ref/url/host/path/IPs/monitor-or-alert names/credential.

## 7. Open decisions
- *(None — all of D-31-1…7 are bound in §1. The only future-slice items are named-vendor adapters and the §25.1 operational signals, both explicitly deferred.)*

## 8. Tests (DB-backed + Docker-free, per README `:19-32`)
- **Pure:** validators (provider/provenance, `target_ref` HTTPS-URL shape + token denylist + bounds, nullable-count + read-state invariants); `resolve_declared_monitoring_target` URL/path safety (http/userinfo/query/fragment/non-443-port/`..`/oversize-path/SSRF-host all rejected); `map_monitoring_response` **truth table** — valid (counts→active/inactive), and **each failure_kind** (`unreachable`/`http_error`/`content_type`/`oversize`/`malformed`) ⇒ **NULL counts + overall_active False + failure_kind set** (B4); strict JSON schema (missing/extra/wrong-type/negative/**> 32767** field ⇒ `malformed`, B7); caller path cannot assert `connector_verified`; connector requires it + `observed_at`; **SSRF units reused** (host-shape/IP-range/IPv6-bracketed-URL/DNS-fail-closed).
- **Repository (db):** verified write (valid + each failure_kind), latest-wins, counts, resolver fail-closed.
- **DB-guard (db, direct SQL; B6/B7):** bad provider/target_ref/token; count > 32767 rejected (smallint + CHECK); **each inconsistent read-state rejected** — `response_valid=true` with `observed_http_status<>200` / NULL counts / non-null failure_kind / `provider_reachable=false`; `response_valid=false` with non-null counts or counts masquerading as a read; `failure_kind='unreachable'` with a non-null status or `provider_reachable=true`; `failure_kind='http_error'` with `observed_http_status=200` or NULL status; `failure_kind IN ('content_type','oversize','malformed')` with `observed_http_status<>200`; `overall_active` mismatch; append-only; FK cross-project/tenant; RLS.
- **Binding-change invalidation (db, B2):** a snapshot for `https://h/old` does NOT satisfy gate #11 after the declaration changes to `https://h/new` (same host, different path).
- **Broker/fail-closed (db):** `monitoring_unbound` / `broker_denied` (audited) / `ssrf_reject` ⇒ no write; safely-attempted failure (e.g. http_error) ⇒ **write** with NULL counts; no url/host/IP in `tool_calls.params`.
- **Unauthenticated (B9):** the connector's request carries **no `Authorization` header / cookie / credential** for any host (injected-transport assertion); there is no operator token in this slice.
- **Pinned request shape (B10, injected transport):** the outbound URL is `https://{validated_ip}{normalized_path}` (IP-pinned, IPv6 bracketed), `Host` + TLS-SNI = the original hostname, no credentials; the pinned URL is not logged/audited/persisted (only `target_ref` holds host/path).
- **Containment (db, B8):** the `status_url`/host/path appear **only** in the snapshot `target_ref` — never in the audit payload, `tool_calls.params`, or the `production_autonomy` gate `context`/report; monitor/alert names appear nowhere (there is no credential token — B9).
- **Gate #11 (db):** PASS + the 6 ladder reasons incl. **`monitoring_evidence_unreadable` ≠ `monitoring_or_alerts_inactive`** (B4); **B-30-9 negative-supersedes-passing**; **no-other-gate-regression** (`ruleset_version=="slice31.v1"`; every non-#11 gate byte-identical; go-live false).
- `make test` + fresh `make test-db` + alembic `0030` round-trip; CI green.

## 9. Sequencing (TDD; mirror Slice 30 §9)
1. Pure validators + `map_monitoring_response` (incl. all failure_kinds) + invariants + (reused) SSRF. 2. Model + migration `0030` (drop→migrate; DB-guard incl. all invariants). 3. Repository + `resolve_declared_monitoring_target` (+ db tests incl. binding-change + negative-supersedes). 4. Connector + Fake (+ pure mapping + bounded-read + read-state tests). 5. Service + registry/matrix + `config` freshness (+ broker/SSRF/unauthenticated/audit tests). 6. Gate #11 ladder + repo wiring (+ PASS/fail + honest split reasons + negative-supersedes + no-other-gate-regression). 7. Full gates; CLAUDE.md + roadmap banner.

## 10. Risks / honesty caveats
- **Failed reads are honest unknowns, not zeros** (B4) — `response_valid=False` ⇒ NULL counts + `failure_kind`; the gate says `monitoring_evidence_unreadable`, never "alerts inactive".
- **URL/host/path containment (B8/B10) — precise scope:** the declared `status_url` (and its host/path) is **persisted only** in the internal snapshot `target_ref` column (it IS the binding identity, §2.1). It must **never** appear in the **persisted/exposed** surfaces: broker params (`tool_calls.params`), audit payloads, the gate `context` / `production_autonomy` report / read API, or logs. **Transient connector use is allowed (B10):** the resolver/connector hold host/path in memory solely to build the SSRF-pinned outbound request (`https://{validated_ip}{normalized_path}`, Host/SNI = hostname); that pinned URL is itself transient and **never logged/audited/persisted**. "No leak" in §12 means exactly this — `target_ref` is the sole *persisted* home. (B9: there is **no credential** in this slice — unauthenticated-only — so there is no token to mis-target or leak; **authenticated providers with an operator-controlled credential-audience allowlist are a deferred follow-up slice**.)
- **Bounded body read** is the deliberate, justified deviation from Slice-30 status-only (capped 64 KiB, two counts only, no names/prose) — the central review item, now fully bound.
- `connector_verified` is app-enforced, not DB-attested (documented caveat).
- "Active" = ≥1 active monitor + ≥1 active alert rule **now** — NOT post-launch operational health (Slices 56–59).
- Gate #11 binds the **currently declared** `status_url` (host+path); verified-negatives/unreadables supersede stale passes (B-30-9).
- SSRF reuses the Slice-30 hardened, tested guard (host-shape + resolved-IP + connect-time pinning + IPv6 + DNS-fail-closed).
- First A5-gate edit since Slice 30 — only gate #11 moves; the no-other-gate-regression test is the guardrail.

## 11. Must NOT claim
- That monitoring is operationally complete / the system is post-launch-stable (Slices 56–59); only that monitors + alert rules are configured + active now.
- That alerts are *inactive* when the provider was unreadable (B4 — that path is `monitoring_evidence_unreadable`).
- That any gate other than #11 changes, or that go-live is enabled.
- That the connector configures/creates monitors or alerts (read-only; broker decision-only).
- That a caller declaration is verified evidence, or that `connector_verified` is DB-attested authenticity.

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A broker-gated, SSRF-safe, binding-bound monitoring connector performs a bounded (≤64 KiB, counts-only, no-names) JSON read of the project's OWN declared `status_url` and writes immutable `connector_verified` `monitoring_status_snapshots` — **valid** (counts + active/inactive) or an **honest failed-read** (`response_valid=False`, NULL counts, `failure_kind`); append-only + RLS + DB-guard (incl. the read-state honesty invariants) + reused SSRF tests + binding-change invalidation; **gate #11 PASSes only on latest verified + valid + active + fresh evidence, says `monitoring_evidence_unreadable` (not "inactive") on a failed read, and STOPS passing after a negative/unreadable refresh**, `ruleset_version=slice31.v1`, **no other gate's semantics change**; the `status_url`/host/path are **persisted only** in the internal `target_ref` (B8) and never in broker params / audit / gate-context / API / logs (B10: transiently used in memory for the SSRF-pinned `https://{validated_ip}{normalized_path}` request, which is never logged/audited/persisted); the connector is **unauthenticated-only** (no `Authorization` header ever — B9); `make test` + `make test-db` + alembic `0030` round-trip + CI green; go-live stays false.

---
**Review note:** PLAN v5 keeps the v2–v4 bindings (D-31-1…7; B1–B9; unauthenticated-only) and fixes **B10 (containment vs pinned-request mechanics)**: containment of `status_url`/host/path is scoped to the **persisted/exposed** surfaces (broker params, audit, gate context/report/API, logs) — `target_ref` is their sole persisted home — while the connector legitimately uses host/path **in memory** to build the SSRF-pinned `https://{validated_ip}{normalized_path}` request (Host/SNI = hostname, no credentials), which is itself never logged/audited/persisted. Plan-only — no branch/code/migration/tests/PR until an approved plan + your explicit go.
