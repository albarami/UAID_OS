# Slice 27 — Request-authentication → verified actor identity (cross-cutting enabler) — PLAN v2

**Status:** AWAITING PLAN APPROVAL — **no branch / no code / no migration / no tests until separately approved.**
**Persona:** senior backend/security architect — authentication, actor identity, provenance, tenant isolation, fail-closed release controls.
**Base:** `main` @ `f8a1146` (verified in sync with `origin/main`). Working tree: intentional `.planning/HANDOFF.json` drift + untracked roadmap; this plan is `.planning/SLICE-27-PLAN.md`. No implementation files changed.
**Migration head:** `0025_ci_evidence` (verified) → new head **`0026`**.
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:196-207`.

> **Revision log — v1 → v2 (each fix is a strict-review blocker, all verified against the named anchors):**
> - **B1 — Resolver return type.** v1 said `CREATE OR REPLACE resolve_tenant_api_key(text)` to change the return from `uuid` → a 3-field row. PostgreSQL forbids changing a function's return type via `CREATE OR REPLACE` (verified the current `RETURNS uuid` at `migrations/versions/0013_key_resolver.py:30`). v2: **DROP + recreate + restore owner/grants** (§4.2, §5).
> - **B2 — Approval provenance conflation.** `approvals` has one `approver_provenance` column (`app/models/approval.py:73-75`) plus `requested_by`(:65)/`resolved_by`(:70). One column cannot carry both a verified *requester* and a verified *resolver*. v2: **add `requested_by_provenance`**; `approver_provenance` is now **resolver-only** (§4.3, §5).
> - **B3 — D-27-2 unimplementable.** v1 claimed "no DB change"; the verified `requester ≠ resolver` check needs requester provenance, which did not exist. v2: D-27-2 depends on the new `requested_by_provenance` column (§4.4, §12).
> - **B4 — Risk-acceptance fake-verified risk.** `create` copies `approver`/`accepted_by`/`approval_authority_source` from payload (`app/repositories/risk_acceptance.py:49-52`). Stamping the verified tier without binding the signer to `context.actor` would assert verification of a caller-typed signer. v2: the verified tier is permitted **only** under **actor-bound signer semantics** (§4.3, §5, §12 D-27-1).
> - **B5 — False tenant-isolation wording.** `tenant_api_keys` is **global / non-RLS** (`app/models/tenant_api_key.py:1-9`); adding `principal_subject` there means principal metadata lives in a global table, not "only in tenant-owned RLS rows." v2: §7 restated — global key table protected by **least-privilege resolver access (D4)**, not RLS.
> - **B6 — Unbound decisions.** D-27-1..6 are now **RULED** in §12 (coordinator rulings recorded in-file before implementation).

> **Provenance discipline (Sanad / No-Free-Facts).** Every factual claim cites a source. **Sanad chain disclosure:** code/migration `file:line` anchors and the `§5.2`/`§7.2-7.4` spec anchors were read directly; the other spec `§:line` anchors were gathered by three read-only exploration agents and cross-corroborated against code I read myself (`app/release/production_autonomy.py`, `app/models/risk_acceptance_record.py`). The reviewer should re-verify any anchor before relying on it.

---

## 0. Goal
Bind an **authenticated request to a verified actor principal**, and make that principal first-class (`TenantContext.actor`) so authenticated entrypoints can stamp a **new, distinct provenance tier** (`request_authenticated`) onto approval / risk-acceptance / audit records — replacing the free, caller-typed `actor` for authenticated paths. Most-shared prerequisite the roadmap defers here (roadmap `:198`): gate #12 needs a verified pre-approval; gate #7 needs verified signers; the broker caps at `ALLOWED_UNVERIFIED_IDENTITY` until request-auth exists (`app/tools/broker.py:8,32`; `README.md:123-125`).

**Honest definition of "verified actor" (custody-based, not human-signed).** A bearer key is *something you have* (`app/repositories/api_keys.py:22-29`); binding it to a principal proves **possession of an active key bound to that principal** — strictly stronger than today's caller-typed strings (`app/models/approval.py:65`, `app/models/risk_acceptance_record.py:81`), but **NOT** an identity-proofed human signature. The spec's strongest bars — "signed by the approvers named in the approval matrix" (§24.1, `spec:2271`), `approval_authority_source: approval_matrix` (§27.10, `spec:2764`), evidence-pack "signer identity"/signed manifest (§15.4, `spec:1540`) — are **later concerns**, out of scope.

## 1. Non-goals
- **No A5 gate flips to PASS.** Gates #7/#12/#13 (`spec:2991,2996,2997`) need approval-matrix authority + release binding + separation of duties — none built here. `passed_gate_count` stays **1** (`app/release/production_autonomy.py:135-138`). (roadmap `:205`.)
- **`can_go_live_autonomously` stays hard-false**; `request_authenticated_a5_preapproval_not_implemented` (`app/release/production_autonomy.py:46`) is **not removed**.
- **No human signature / approval-matrix authority mapping / evidence-pack signer** (§24.1/§27.10/§15.4).
- **No new broad authenticated write API** — §18.6 dashboard stays **read-only** (`app/api/dashboard.py` GET-only). (D-27-3 RULED: read-only.)
- **No connector / `connector_verified` evidence** (Slice 28, roadmap `:209-219`).
- **No cross-tenant principal correlation** (§17.3, `spec:1716-1718`).
- **No broker wiring** (D-27-4 RULED: defer), **no LLM/runtime/cost change.**

## 2. Spec grounding
| Theme | Anchor | Requirement |
|---|---|---|
| No self-approval / separation | §2.2 `spec:151-159`; §16.7 `spec:1631-1643`; board `spec:1207` | Reviewer/approver identity independent of builder. |
| Authority matrix | §5.2 `spec:485,487,489,490` | Deploy-production: "Human approval or pre-approved A5 gate"; secrets: "Secret owner approval". |
| Authorship/approval provenance | §7.2 `spec:645-654`; §7.3 `spec:656-665`; §7.4 `spec:679-688` | Binding needs a **named human / independent lineage / domain authority** (`approved_by`/`approved_at`). |
| Risk-acceptance signer | §24.1 `spec:2271`; §27.10 `spec:2750-2767`; §24.2 `spec:2324-2328` | Signed by approvers **named in the approval matrix**; `approval_events_recorded`, `separation_of_duties_confirmed`. |
| A5 identity gates | App. B `spec:2991`(#7),`2996`(#12),`2997`(#13); App. A `spec:2979` | Verified approver/authority identity. |
| Tenant isolation of identity | §17.1 `spec:1694-1696`; §17.2 `spec:1698-1714`; §17.3 `spec:1716-1718` | "user identities" isolated; no cross-tenant reuse. |
| Audit attribution | §16.6 `spec:1616-1627` | Append-only, hash-chained, attributable. |
| Human/machine actor model | §23.4 `spec:2219,2229,2241` | `users` vs `agents` vs `audit_logs`. |
| Request-auth mechanism | **ABSENT** (only product-security: §16.1 `spec:1554`; §11.1 `spec:1069-1084`) | ⇒ mechanism is a design choice (§4.0). |

## 3. Current-state findings (verified by read)
1. Identity stops at the tenant: `require_tenant → TenantContext(tenant_id)` only (`app/api/auth.py:33-43`); `TenantContext` frozen with only `tenant_id` (`app/tenancy.py:27-31`).
2. Key table maps key→tenant only: `id, tenant_id, key_hash, label, status` (`app/models/tenant_api_key.py:29-38`); **global / non-RLS by design** (`tenant_api_key.py:1-9`).
3. Every downstream `actor` is a free caller-typed string: `audit.record(actor:str)` (`app/audit.py:30-36`); `approvals.{requested_by:65,resolved_by:70,approver_provenance:73-75}`; `risk_acceptance_records.{owner:80,approver:81,accepted_by:82,approval_authority_source:83,approver_provenance:87-89}` copied from payload at `app/repositories/risk_acceptance.py:49-52`.
4. Only authenticated surface is **read-only** (`app/api/dashboard.py` GET-only); approvals/risk-records are created by internal repo calls. ⇒ Slice 27 supplies identity *plumbing*, exercised at the auth+repo layer (§9).
5. Provenance-tier precedent: Slice 26's stronger tier is schema-reserved but **caller-unwritable** (`connector_verified`; `app/release/ci_evidence.py:27-28`; guard `0025:107-108`). Slice 27 adds an **identity-axis** token, **app-stamped only**.
6. Guard topology (verified): `approvals.approver_provenance` has a default but **no forcing trigger / no value CHECK** (`app/models/approval.py:43-48,73-75`) → additive. `risk_acceptance_records` `0021` guard **forces `caller_supplied_unverified` on INSERT** (`0021:140-141`) **and** `approval_authority_source='approval_matrix'` (`0021:143-145`), keeps only `status`/`updated_at` mutable (`0021:150-160`) → relaxing it needs a `CREATE OR REPLACE` in `0026` that preserves all other invariants.
7. Resolver returns scalar `uuid` (`0013:30`), owned by `api_key_resolver`, `uaid_app` has EXECUTE-only, no direct SELECT (`0013:39-44`).
8. Broker upgrade hook exists (`app/tools/broker.py:27,32,34`) — wiring deferred (D-27-4).

## 4. Proposed design

### 4.0 Approach decision — extend the bearer key, NOT a separate credential model
**Chosen:** bind a verified **principal** to the existing bearer-key path, reusing the D4 resolver (`0013`). **Rejected (this slice):** a separate human/SSO credential store. Rationale: smallest blast radius; directly upgrades the unverified `actor` flow (§3.3). A richer human-identity store (§23.4 `users`) + approval-matrix authority (§24.1) are later concerns (§1). Honest consequence: "verified" = **API-key custody**, not human identity-proofing (§0, §8).

### 4.1 Identity model — `app/identity.py` (new, pure)
- `ACTOR_TYPES = ("human","service")`; `IDENTITY_PROVENANCES = ("caller_supplied_unverified","request_authenticated")`; `APP_WRITABLE = ("request_authenticated",)`.
- `@dataclass(frozen=True) AuthenticatedActor(subject:str, actor_type:str, provenance:str="request_authenticated")` + `validate_actor` (subject 1..255 bytes; `actor_type ∈ ACTOR_TYPES`); fail-closed.
- `actor_fields(context, fallback_actor) -> (actor_str, provenance)`: verified tuple iff `context.actor` set, else `(fallback_actor,"caller_supplied_unverified")`. The verified tier is **never** derived from a caller payload field (trust boundary; mirrors Slice 26 "caller may not assert `connector_verified`").

### 4.2 Auth boundary — `app/api/auth.py`, `app/tenancy.py`, resolver (B1 fix)
- **Resolver (`0026`): DROP + recreate + regrant** — `CREATE OR REPLACE` cannot change `RETURNS uuid` → a row (verified `0013:30`). Steps, in order:
  1. `DROP FUNCTION public.resolve_tenant_api_key(text)`;
  2. recreate with OUT params: `resolve_tenant_api_key(p_key_hash text, OUT tenant_id uuid, OUT principal_subject text, OUT actor_type text)` `LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog`, body `SELECT tenant_id, principal_subject, actor_type FROM public.tenant_api_keys WHERE key_hash=p_key_hash AND status='active' LIMIT 1`;
  3. **restore the exact 0013 privilege model**: `ALTER FUNCTION … OWNER TO api_key_resolver`; `REVOKE ALL … FROM PUBLIC`; `GRANT EXECUTE … TO uaid_app` (`0013:39-44`).
  Downgrade reverses: DROP the row version, recreate the scalar `RETURNS uuid` version + the same regrant block.
- `TenantApiKeyRepository.resolve` → `(tenant_id, principal_subject, actor_type)` or `None` (no row / NULL tenant ⇒ unauthenticated). Call site `SELECT tenant_id, principal_subject, actor_type FROM public.resolve_tenant_api_key(:h)` (was `SELECT public.resolve_tenant_api_key(:h)`, `app/repositories/api_keys.py:60-63`).
- `require_tenant` builds `AuthenticatedActor` and returns a `TenantContext` carrying it. **`TenantContext` gains `actor: AuthenticatedActor | None = None`** — backward compatible: every existing `TenantContext(tenant_id)` call still works. Deny-by-default unchanged (`app/api/auth.py:36-42`).

### 4.3 Stamping verified provenance (app-enforced, fail-closed)
- **Approvals (B2 fix — two provenance columns):**
  - `request(...)`: stamp **`requested_by_provenance`** from `actor_fields(context, requested_by)`; `requested_by` = verified subject when present.
  - `approve/reject/cancel(...)`: stamp **`approver_provenance`** (resolver-only) from `actor_fields(context, actor)`; `resolved_by` = verified subject when present.
  - System auto-transitions (`expire_if_overdue`, `app/repositories/approvals.py:112`) keep `actor="system"`, `approver_provenance="caller_supplied_unverified"` (no human principal).
- **Risk-acceptance (B4 fix — actor-bound signer semantics; only if D-27-1 included):** `create` may stamp `approver_provenance="request_authenticated"` **only when** `context.actor` is present **and** the signer fields are actor-bound: require `approver == context.actor.subject` **and** `context.actor.subject ∈ accepted_by`. If `context.actor` is present but the signer fields do not match ⇒ **reject** (`InvalidRiskAcceptance` — fail-closed; never silently downgrade a claimed-verified acceptance). If `context.actor` is absent ⇒ current behavior (`caller_supplied_unverified`, payload signer fields). `approval_authority_source` stays the guard-forced `approval_matrix` constant — still **caller-asserted**, so gate #7 stays unmet (§14).
- **Audit:** callers pass the verified subject as `actor` (`app/audit.py:34` signature unchanged).

### 4.4 Separation-of-duties with verified identity (§2.2) — D-27-2 (RULED include; B3 fix)
Enforce `approver.subject != requester.subject` **only when both `requested_by_provenance` and `approver_provenance` are `request_authenticated`** (needs the new `requested_by_provenance` column — §5). Mirrors the extraction rule `extracted_by != reviewed_by` (`app/repositories/extraction.py:223`). When either side is unverified, no cross-check (cannot trust either label). Full approval-matrix authority deferred.

## 5. Data / model / migration impact (`0026`)
| Object | Change | Anchor / note |
|---|---|---|
| `resolve_tenant_api_key(text)` | **DROP + recreate** as a row-returning fn (OUT params) + **restore owner/grants** | B1; `0013:30,39-44`. Not `CREATE OR REPLACE`. |
| `tenant_api_keys` | **ADD** `principal_subject TEXT`, `actor_type TEXT` CHECK `IN ('human','service')`. Backfill (D-27-6): `actor_type='service'`, `principal_subject='legacy:'||id`, then NOT NULL. | global non-RLS table (`tenant_api_key.py:1-9`); admin `issue` gains the two params (`app/repositories/api_keys.py:38-46`). |
| `approvals` | **ADD** `requested_by_provenance TEXT NOT NULL DEFAULT 'caller_supplied_unverified'`; **ADD** value CHECKs on **both** `requested_by_provenance` and `approver_provenance` `IN ('caller_supplied_unverified','request_authenticated')` | B2/B3; currently unconstrained Text (`app/models/approval.py:73-75`). Additive. |
| `risk_acceptance_records` guard | **`CREATE OR REPLACE`** the `0021` guard so INSERT allows `approver_provenance ∈ {caller_supplied_unverified, request_authenticated}`, **preserving every other `0021` invariant verbatim** (`status='active'` `0021:137-138`; `approval_authority_source='approval_matrix'` `0021:143-145`; hard-refusal `0021:146-149`; UPDATE immutability/transition `0021:150-160`). Actor-bound signer semantics enforced in the **repo** (§4.3), not the guard. | B4; verified `0021:136-160`. **Only if D-27-1 included.** |
| Round-trip | `0026` up→down→up clean; downgrade restores `0013` scalar resolver + grants, drops columns/CHECKs, restores `0021` guard | reversibility (house rule; `SLICE-26-PLAN.md:184`). |

## 6. API / auth impact
- `require_tenant` yields a principal-bearing `TenantContext`; **all GET endpoints unchanged** (they ignore `context.actor`). No new write endpoint (D-27-3: read-only).
- 401 deny-by-default, generic message, no key-exists oracle — unchanged (`app/api/auth.py:15-19`).

## 7. Tenant / RLS / FK / audit / immutability impact (B5 fix)
- **Principal metadata lives in the GLOBAL, non-RLS `tenant_api_keys` table** (`app/models/tenant_api_key.py:1-9`) — **not** RLS-protected, and **not** "only in tenant-owned rows." It is protected exactly like the rest of that table: **least-privilege resolver access (D4)** — `uaid_app` has **EXECUTE-only** on `resolve_tenant_api_key` and **no direct SELECT** on `tenant_api_keys` (`0013:40-44`). The cross-tenant non-leak rests on three facts, each test-backed (§9): (a) each key row is tenant-bound (`tenant_api_key.py:32-34`); (b) the resolver returns `principal_subject` **only together with that row's `tenant_id`**, for an active key; (c) no query keys on `principal_subject` across tenants. When the principal is later stamped into tenant-owned rows (approvals/risk-records), those rows **are** RLS-protected; the *source* of the principal is the global key table.
- **Audit (§16.6).** Verified subject flows as `actor` into the append-only hash-chained log; **no secret/credential material** (raw key never leaves `resolve`, `api_keys.py:57`).
- **Immutability.** `risk_acceptance` identity columns stay immutable (`0021` UPDATE branch unchanged); the guard edit only widens the allowed INSERT *value*.
- **FK.** No new cross-table FK; `tenant_api_keys` columns additive.

## 8. Security / fail-closed analysis
- **Honest tier semantics.** `request_authenticated` ≠ human signature; documented in `app/identity.py` + docs. A5 report unchanged ⇒ no reader mistakes key-custody for go-live authority.
- **App-enforced, not DB-attested, authenticity.** `uaid_app` holds INSERT, so the DB cannot prove a `request_authenticated` row came from a real authenticated request; the authenticity boundary is the **app path + the repo being the sole INSERT mediator** (same caveat as all existing app-stamped provenance, e.g. `app/repositories/risk_acceptance.py:8-9`). The DB widens the *allowed value*; the app guarantees *when* it is used. (Contrast Slice 26, which keeps its strong tier wholly unwritable — impossible here since we must write the tier.)
- **No fake-verified signer (B4).** The verified tier on risk-acceptance is permitted only under actor-bound signer match; mismatch ⇒ reject.
- **No caller assertion**; **deny-by-default** preserved (missing principal ⇒ `caller_supplied_unverified`, never a fabricated identity).
- **No new injection surface.**

## 9. Test matrix (TDD-first)
**Pure (`tests/test_identity.py`):** `validate_actor` good/bad; `actor_fields` verified vs fallback; constants.
**DB (extend `tests/test_api.py`, `tests/test_approvals.py`, `tests/test_risk_acceptance.py`, new `tests/test_identity.py`):**
1. Resolver drop/recreate: `resolve` returns `(tenant_id, principal_subject, actor_type)`; owner = `api_key_resolver`, `uaid_app` EXECUTE-only, **no** direct SELECT (catalog assertions); unknown/revoked ⇒ `None` ⇒ 401.
2. **Approvals dual provenance (B2):** verified `request()` ⇒ `requested_by_provenance='request_authenticated'`, `requested_by`=subject; verified `approve()` ⇒ `approver_provenance='request_authenticated'`, `resolved_by`=subject; unverified ⇒ both default, fallback strings (regression).
3. **Caller cannot assert verified:** payload claiming a provenance is ignored; only `context.actor` stamps it.
4. **§2.2 separation (D-27-2):** both-verified and `requester.subject==resolver.subject` ⇒ rejected; distinct ⇒ allowed; mixed/unverified ⇒ no cross-check.
5. **Risk-acceptance actor-bound (B4, D-27-1):** `context.actor` present + `approver==subject` + `subject ∈ accepted_by` ⇒ `request_authenticated`; `context.actor` present + mismatch ⇒ **rejected**; absent ⇒ unverified + payload fields. DB-guard direct-SQL still rejects bogus provenance; identity columns immutable.
6. **Tenant isolation (B5):** a tenant-A key's principal never resolves/leaks under tenant-B; principal never used in a cross-tenant query; cross-tenant `project_id` writes still RLS-blocked.
7. **A5 unchanged:** `passed_gate_count==1`; #7/#12/#13 unmet; `can_go_live_autonomously==False`; `NO_GO_LIVE_REASONS` unchanged (`app/release/production_autonomy.py:44-47`).
8. **Migration round-trip** `0026` up/down/up; catalog: columns + CHECKs + 3-field resolver + grants.

## 10. Documentation updates
- `CLAUDE.md`: `app/identity.py` entry; `tenant_api_keys` principal columns + `requested_by_provenance` + `0026`; principal-bearing `TenantContext`; honest `request_authenticated` tier; status "Slice 27 … in progress"; **actual** `make test`/`make test-db` counts (no invented numbers — §2.1).
- `README.md`: auth section — principal resolution; two-tier identity provenance + honesty caveat; "read-only API contract unchanged"; the global-key-table-not-RLS clarification (§7).
- Roadmap stays untracked/local unless the coordinator includes it.

## 11. Implementation sequence (on approval; branch `feat/slice27-request-auth`)
1. `tests/` (failing first): pure identity; resolver 3-field + grants; approvals dual provenance; §2.2 separation; risk-acceptance actor-bound; tenant isolation; A5-unchanged.
2. `app/identity.py`.
3. `app/tenancy.py` (`TenantContext.actor`), `app/api/auth.py`, `app/repositories/api_keys.py` (resolve/issue).
4. `migrations/versions/0026_*.py` (resolver DROP+recreate+regrant; `tenant_api_keys` columns + backfill; `approvals.requested_by_provenance` + dual CHECKs; `0021` guard `CREATE OR REPLACE` [D-27-1]).
5. `app/repositories/approvals.py` (dual stamping + §2.2 check) + `app/repositories/risk_acceptance.py` (actor-bound) + audit call sites.
6. Docs. Atomic commits per `github-flow`.

## 12. Bound decisions (RULED by coordinator 2026-06-23)
- **D-27-1 — Risk-acceptance:** **INCLUDE, only with actor-bound signer semantics** (§4.3 / B4). The `0021` guard `CREATE OR REPLACE` preserves all other invariants (§5).
- **D-27-2 — Separation of duties:** **INCLUDE, only with `requested_by_provenance`** (§4.4 / B2/B3); enforced only when both sides are `request_authenticated`.
- **D-27-3 — Write endpoint:** **KEEP READ-ONLY** (no authenticated write endpoint this slice; §1, §6).
- **D-27-4 — Broker wiring:** **DEFER** (`app/tools/broker.py` untouched this slice).
- **D-27-5 — Tier name:** **`request_authenticated`.**
- **D-27-6 — Backfill:** `actor_type='service'`, `principal_subject='legacy:'||id` for pre-`0026` keys, then NOT NULL (operators may re-issue with real principals).

## 13. Required evidence before review (on execution)
Actual output required: `ruff check .` clean; `make test` green incl. new pure tests; **fresh** `make test-db` (drop first per memory `migration-edit-requires-db-drop`) green incl. all §9 DB cases; `alembic upgrade head → downgrade -1 → upgrade head` clean (resolver drop/recreate + `0021` replace both reverse); A5-unchanged assertions green; real counts recorded in `CLAUDE.md`.

## 14. Must NOT claim
- That Slice 27 makes any A5 gate PASS, enables go-live, or removes `request_authenticated_a5_preapproval_not_implemented` (`app/release/production_autonomy.py:46`).
- That `request_authenticated` is a human signature, an approval-matrix authority (§24.1/§27.10 — `approval_authority_source` stays a **caller-asserted constant**), or an evidence-pack signer (§15.4) — it is **key-custody-based**.
- That the DB attests authenticity of the verified tier — it is **app-enforced** (§8).
- That a verified actor can yet act over HTTP (no write endpoint; D-27-3).
- Any connector / `connector_verified` evidence (Slice 28).

## 15. Exit criteria
- Principal-bearing `TenantContext` from `require_tenant`; resolver returns 3 fields with the D4 grant model intact; `request_authenticated` tier **app-stamped** onto approvals (dual provenance) + risk-acceptance (actor-bound) + audit; unverified callers still get `caller_supplied_unverified` (regression-clean).
- §2.2 verified separation enforced when both sides verified; risk-acceptance rejects mismatched verified signer.
- Tenant isolation of principals proven (global key table protected by least-privilege resolver, not RLS); deny-by-default preserved.
- A5 report unchanged (gate count 1; #7/#12/#13 unmet; go-live false).
- `0026` reversible; `make test`/`make test-db` green on a fresh DB; honesty caveats documented.

---
**Awaiting PLAN v2 approval.** On approval: branch `feat/slice27-request-auth` off `main`, TDD-first per §11, atomic commits, then pause for strict-reviewer + coordinator merge approval. **No implementation begins until this PLAN is separately approved.**
