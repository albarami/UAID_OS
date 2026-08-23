# Slice 63 — Enterprise administration (org/tenant admin, DB-enforced RBAC, role-gated policy management)

**Seats (ruling 2026-08-23, standing).** PLANNER = Claude/Fable seat (this document).
BUILDER = Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on
plan and code, probe-backed verdicts only. **The builder never edits this plan.**

**Version.** v1. Owner (Salim) authorized Slice 63 with no further owner gate
(2026-08-24). Halt rule unchanged: three consecutive REJECTs on this plan line ⇒ stop,
no v4 without the owner.

> **This slice closes NO spec section and does NOT satisfy the roadmap Slice 61 exit.**
> D-8, D-9, and D-10 stay **OPEN** (owner = Salim). Slice 63 is the last scheduled slice:
> after it merges the coordinator STOPS for the Slice 55–63 final report. **This plan does
> not schedule Slice 64.**

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 63 (l.655–668).
**Spec grounding.** §26.7 last bullet ("enterprise administration", l.2522); §17.2 tenant
isolation controls (l.1698–1714); §17.3 tenant boundary rule (l.1716–1718); §16.1
"authorization" + "role-based access control" (l.1550–1568); §16.6 audit; §5/§2.6 (the
policy object being managed). **A5 / readiness / go-live are untouched.**

**Alembic.** Live head at plan time is **`0061`** (`migrations/versions/0061_cost_learning.py`,
`revision="0061"`, `down_revision="0060"`; verified `uv run alembic heads` → `0061 (head)`
on `main` @ `4a89742`). This slice adds **migration `0062`**, file
`migrations/versions/0062_enterprise_admin.py`, `revision="0062"`, `down_revision="0061"`.
Additive: four new tables (with their own PK/UNIQUE/CHECK/FK/trigger set), **one** new
column on an existing table (`organizations.status`), one function DROP+recreate
(`resolve_tenant_api_key`, same signature), and two grant additions on existing objects
(`SELECT` on `tenants`/`organizations` to `api_key_resolver`; `EXECUTE` on `audit_append` to
`CURRENT_USER`). **No existing table gains a UNIQUE, and no existing constraint, trigger,
or `uaid_app` grant is dropped or widened.** **Re-verify the head before writing the file**;
if it is not `0061`, stop and report rather than renumbering silently.

---

## 0. What this slice is

Enterprise administration **over UAID's existing tenant model** — no new isolation
mechanism, no weakening of the old one. Three bounded pieces:

1. **Org / tenant administration that actually enforces something.** `tenants.status`
   has existed since migration `0001` with a CHECK of `('active','suspended')` and
   **nothing has ever read it**. Slice 63 makes suspension live at the *only* place
   untrusted input becomes a tenant: the `SECURITY DEFINER` bearer-key resolver
   `resolve_tenant_api_key`. A key that is itself `active` no longer resolves when its
   tenant is `suspended` or its organization is `suspended` (new additive
   `organizations.status`). Lifecycle changes are operator-path and recorded in an
   append-only `tenant_admin_events` ledger whose rows are DB-checked against the real
   `tenants` / `organizations` status they claim.
2. **RBAC that SQL cannot ignore.** A tenant-owned `admin_role_grants` table on which the
   runtime role `uaid_app` has **SELECT only** — it can read grants, and cannot mint them.
   Every role-gated admin action is recorded in append-only `admin_actions`, where a
   BEFORE-INSERT guard trigger (which binds the admin role too, unlike an RLS `WITH CHECK`)
   refuses to record `decision='allowed'` unless a real **active, same-tenant** grant row
   exists for that principal and that role, and a generated CHECK refuses `allowed` unless
   the held role's rank meets the action's required rank. Refusal rows are equally
   guarded: `refused_no_grant` is refused when a grant does exist.
3. **Role-gated policy management.** A new service applies §5 autonomy-policy changes
   through the RBAC gate and records `admin_policy_changes`, whose guard trigger proves
   (a) the authorizing `admin_actions` row is `allowed` and of a policy kind, (b) the
   recorded level equals the referenced `autonomy_policies` row's real current level, and
   (c) one authorization can be spent exactly once. The Slice-3
   `AutonomyPolicyRepository.upsert` is **called, not modified.**

### 0.1 Grounding facts (re-verified 2026-08-24 against `main` @ `4a89742`)

1. **`tenants.status` is dead code today.** `app/models/tenant.py:19` declares
   `CHECK (status IN ('active','suspended'))`. A repo-wide scan for `suspended` finds
   only agent-instance statuses (`app/agents/registry.py:217`,
   `app/models/agent_instance.py:37`) and that CHECK. No code path reads
   `tenants.status`. Suspending a tenant currently does nothing.
2. **`organizations` has no status column** (`app/models/organization.py` — `id`, `name`,
   `slug` only). Org-level administration therefore needs one additive column.
3. **There is exactly one HTTP→tenant boundary.** `app/api/auth.py:34-54`
   (`require_tenant`) → `TenantApiKeyRepository.resolve` →
   `SELECT ... FROM public.resolve_tenant_api_key(:h)`. The function
   (`migrations/versions/0026_request_auth_identity.py:129-137`) is `LANGUAGE sql STABLE
   SECURITY DEFINER SET search_path = pg_catalog`, owned by `api_key_resolver`, PUBLIC
   revoked, `uaid_app` EXECUTE-only with **no** SELECT on `tenant_api_keys` (D4).
   Enforcing suspension inside that function needs **no Python change** — `auth.py` and
   `api_keys.py` stay byte-identical.
4. **`api_key_resolver` can currently read only `tenant_api_keys`** (migration `0013`).
   Joining `tenants`/`organizations` requires a narrow additive `GRANT SELECT` to that
   NOLOGIN role. `uaid_app` already has SELECT on both
   (`migrations/versions/0002_rls_tenant_isolation.py:41`), so this is not a new class of
   readable data — it is a new reader of already-runtime-readable global tables.
5. **`uq_autonomy_policies_id_proj_tenant` already exists** (added by migration
   `0052_production_preapprovals.py:624`). No new UNIQUE is needed on
   `autonomy_policies`; Slice 63 only FKs to it.
6. **`audit_append` is granted to `uaid_app` only** (`0003_audit_log.py:204`), with
   `REVOKE ALL ... FROM PUBLIC` and owner `audit_writer`. It derives the tenant from
   `app.current_tenant` and fails closed when unset (`0003_audit_log.py:138`). Runtime
   admin actions can therefore be hash-chain audited. The operator path can only audit if
   the migration-running role holds EXECUTE — true implicitly for a superuser `app`, false
   for a least-privilege operator — so `0062` adds an explicit
   `GRANT EXECUTE ... TO CURRENT_USER` (§3.6).
7. **The precedent for global admin writes is "the row is the trail."** Slice 6
   (`register_blueprint`/`register_version`), Slice 61a/61b (`CatalogAdmin`), and Slice 62
   (`publish_cross_project_aggregates`) deliberately do **not** call `audit_append`;
   platform-event audit stays deferred. Slice 63's operator path writes *tenant-owned*
   rows, so it **can** and **does** set the tenant GUC and audit — that is a strict
   improvement, not a new claim about global writes.
8. **`AutonomyPolicyRepository.upsert` already documents `actor` as UNTRUSTED**
   (`app/repositories/autonomy_policies.py:58-61`). Slice 63 passes the Slice-27 verified
   principal through the new path; direct Slice-3 callers are unchanged and stay
   unverified. The repository file is **frozen** (§1).
9. **A5 is `slice54.v1`; readiness is `slice20.v1`; `can_go_live_autonomously` is the
   literal `False`** (`app/release/production_autonomy.py:71,119`;
   `app/intake/readiness.py:45`). Slice 63 must not move any of them.

### 0.2 Load-bearing claim

For the runtime role `uaid_app`, an `admin_actions` row with `decision='allowed'` exists
only if, in that same tenant, an `admin_role_grants` row with `status='active'` binds that
`actor_principal` to that `actor_role`, and that role's rank meets the action kind's
required rank; and an `admin_policy_changes` row exists only if it references such an
`allowed` policy-kind action (spent once) and records the autonomy level that the
referenced `autonomy_policies` row actually holds. `uaid_app` cannot create a grant row —
it has SELECT only. A bearer key whose tenant or organization is `suspended` does not
resolve.

That does **not** prove: that the recorded `actor_principal` is the principal that
authenticated (the service stamps it from the Slice-27 `AuthenticatedActor`; the literal
`request_authenticated` is app-stamped and direct SQL as `uaid_app` can write it); that a
grant reflects a real human authority decision (the grant's own provenance is
`operator_admin_session_unverified`); that an operator holding DB-owner credentials is
constrained by anything here; that suspension stops work already running inside
`tenant_scope`; or that any read endpoint is role-gated (none is).

### 0.3 Honesty crux (verbatim, for CLAUDE.md / README.md)

*This slice records enterprise administration over UAID's existing tenant model. It is not
go-live authority, not an RLS bypass for `uaid_app`, not a human signature, not closing
Slice 61, and not closing D-8/D-9/D-10. What the database enforces is that the runtime role
cannot record an allowed admin action without a real active same-tenant role grant it has no
privilege to create, and that a suspended tenant's or organization's bearer key no longer
resolves at the single HTTP→tenant boundary. What it does not enforce is that the recorded
principal is the authenticated one (app-stamped), that a role grant carries real
organizational authority (its provenance is an unverified operator admin session), that an
operator with DB-owner credentials is constrained, that suspension halts work already inside
`tenant_scope`, or that any read endpoint is role-gated — none is. A5 stays `slice54.v1`,
readiness stays `slice20.v1`, and `can_go_live_autonomously` remains the literal `False`.*

### 0.4 Allowed claims, verbatim

- "`uaid_app` has `SELECT` and no `INSERT`/`UPDATE`/`DELETE` on `admin_role_grants`; the
  runtime role cannot mint its own authorization (P-grant-no-write)."
- "An `admin_actions` row with `decision='allowed'` requires an active same-tenant grant of
  the recorded `actor_role` (P-allow-no-grant, P-allow-revoked-grant,
  P-allow-cross-tenant-grant) **and** rank ≥ the action's required rank
  (P-allow-insufficient-rank)."
- "`decision='refused_no_grant'` is refused when an active grant for that principal exists
  (P-refuse-mislabel). The refusal ledger cannot lie about the grant state."
- "`required_role` is not caller-chosen: a generated CHECK binds it to `action_kind`
  (P-required-role-forged)."
- "The `admin_actions` authority is a BEFORE-INSERT trigger, not an RLS `WITH CHECK`, so it
  also binds the admin/owner role (P-allow-no-grant-as-admin)."
- "An `admin_policy_changes` row requires an `allowed` policy-kind action
  (P-change-refused-action), the real current autonomy level
  (P-change-level-mismatch), and an unspent authorization (P-change-action-reuse)."
- "A bearer key belonging to a `suspended` tenant does not resolve, and neither does one
  whose organization is `suspended` (P-suspend-tenant-blocks, P-suspend-org-blocks);
  reinstatement restores resolution (P-reinstate-restores)."
- "A `tenant_admin_events` row cannot claim a status the `tenants`/`organizations` row does
  not hold (P-event-lies)."
- "Every runtime admin action — allowed **and** refused — appends a hash-chained
  `audit_logs` entry, and `audit_verify()` still returns ok (P-audit-chain)."
- "The four new tables are tenant-owned with RLS ENABLE+FORCE; tenant A cannot read tenant
  B's rows (P-rls-cross-tenant). Slice 63 grants `uaid_app` no cross-tenant reach
  (A-grant-matrix)."
- "Migration `0062` is additive; head becomes `0062`; downgrade restores the `0026`
  resolver body byte-for-byte (P-downgrade-resolver)."

### 0.5 Refused claims, verbatim

- That the Slice 61 exit, D-8, D-9, or D-10 is closed. That any spec section is closed.
- **That admin convenience overrides tenant isolation.** No new grant gives `uaid_app`
  cross-tenant reach; grants are tenant-scoped rows and a cross-tenant grant is refused
  (P-allow-cross-tenant-grant). Cross-tenant/organization administration is an **operator
  DB-credential** path, stated openly, not a runtime capability.
- That `actor_provenance='request_authenticated'` proves the caller is that principal. It is
  app-stamped from a Slice-27 `AuthenticatedActor`; `uaid_app` can write the literal by
  direct SQL. The unforgeable half is the **grant**.
- That a role grant is a human signature, an approval-matrix authority (§24.1), or an
  organizational-authority attestation. Its provenance is
  `operator_admin_session_unverified`.
- That RBAC is enforced against an actor holding DB-owner credentials. It is not; that actor
  can insert grants directly. The claim is scoped to the runtime role, and the
  `admin_actions` guard is a trigger specifically so the owner path is still checked for the
  *grant-existence* half.
- That suspension is enforced inside `tenant_scope`, in repositories, or against
  already-running work. It is enforced only at bearer-key resolution
  (`suspension_not_enforced_inside_tenant_scope`).
- That any read endpoint (`/api/projects/{id}/…`) is role-gated. None is
  (`read_api_not_role_gated`). A valid bearer key still reads its own tenant exactly as
  before Slice 63.
- That role grants can be delegated at runtime. They cannot
  (`role_grant_delegation_not_implemented`); minting is operator-only by privilege.
- That `tenant_admin_events` / `admin_role_grants` operator writes are proof an authorized
  human acted. They are proof an operator DB session acted.
- That anything here advances an Appendix-B gate, changes readiness, or moves
  `can_go_live_autonomously`.
- That any HTTP route, LLM call, tool, A1 action, or broker behaviour changed. None does.

---

## 1. Frozen files — byte-identical, SHA-256 verified on `main` @ `4a89742`

| File | SHA-256 |
|---|---|
| `app/release/production_autonomy.py` | `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029` |
| `app/intake/readiness.py` | `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26` |
| `app/runtime/control_loop.py` | `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180` |
| `app/tools/broker.py` | `20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57` |
| `app/cost.py` | `2dc1e1d1a0dcfb433af536b69bba926b5c74f3c028bda841d243416546819b43` |
| `app/cost_forecast.py` | `0fb050597363bcb4af6393e48e8822d975094108f92f4c5770ea4656b3ce02b6` |
| `app/llm/pricing.py` | `0693ab457daefd45fedbf3bd6df08e531568c89e2ca9a91dbd710c40febe5d59` |
| `app/policy/matrix.py` | `c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f` |
| `app/policy/engine.py` | `6269f250cc3fc621ed1f445175f79d9e5227f3ece4f0ea2546aa3fc1337a45c0` |
| `app/repositories/autonomy_policies.py` | `9b563f6a8780da4a60cd1a57de377df6f3510a221d656564c115b89812288317` |
| `app/tenancy.py` | `cb7f9827bcf2c25fdd72ad29177e0f2fb6911b4ffbd7931ac1fe2cb939c2dbc1` |
| `app/identity.py` | `a76f99b85593e6d7ade9f71b6adb1a1ca81b3066436bb12ec9a04e7876897a09` |
| `app/audit.py` | `b44c45706c86ad4a55b45d81c43d9db0115e642267b2592c29d0649699c6c116` |
| `app/api/auth.py` | `86930b47f16f0a487518b2e232412ce61e7536d45bf963e7da7f7518d0fc76ab` |
| `app/api/dashboard.py` | `752c1bb4e96c6681f16ea4314a3835603d0bb19c19dfc1b49b2e6207762d8a81` |
| `app/repositories/api_keys.py` | `9dc80483746f0098efc65ead51267650404f9d315baa9f77706c66b836dcaeda` |
| `app/models/tenant_api_key.py` | `c3753ea4648ecf857f16798754b7fcb07f091d81573bc99a61c305b21862d321` |
| `app/models/tenant.py` | `d6b5cd28b139f1487eaa2d649ba443fe754964521635afd130d17f5a5a3594aa` |

`app/models/organization.py` is the **only** pre-existing product module Slice 63 edits
(one additive `status` column, §3.5). Do **not** `ruff format` the whole tree.

---

## 2. Design decisions

### OD-1 — Role vocabulary: three ranked roles, no decorative entries

`app/admin/rbac.py`:

```
ADMIN_ROLES = ("tenant_viewer", "tenant_operator", "tenant_admin")
ROLE_RANKS  = {"tenant_viewer": 1, "tenant_operator": 2, "tenant_admin": 3}
```

Ranks are distinct, so "the highest active grant" is unique — no tie-break rule.
`tenant_viewer` is the deliberate **floor**: it is a real grant that authorizes *no* action
kind, which is what makes P-allow-insufficient-rank and P-refuse-mislabel possible. It is
not claimed to gate reads.

**Rejected:** `org_admin`. A grant row is tenant-scoped; an "org admin" grant stored per
tenant would either be decorative or would imply cross-tenant reach, which §17.3 forbids
and §0.5 refuses. Organization administration stays operator-path.

**Rejected:** gating the Slice-10/17/19/21 read API. Every existing key has no grant, so
gating reads would 403 the entire product and would be a behaviour change, not
administration. Recorded as the limitation `read_api_not_role_gated`.

### OD-2 — Two gated action kinds, so the rank ladder is testable

```
ADMIN_ACTION_KINDS   = ("set_autonomy_policy", "tighten_autonomy_overrides")
ACTION_REQUIRED_ROLE = {"set_autonomy_policy": "tenant_admin",
                        "tighten_autonomy_overrides": "tenant_operator"}
```

Grounding: §5/§2.6 autonomy overrides are **tighten-only** and validated by the frozen
`app/policy/matrix.py:validate_overrides`, so an overrides-only change that leaves
`autonomy_level` untouched is strictly safety-increasing and is an *operator* action.
Setting the level is an *admin* action. `tighten_autonomy_overrides` on a project with no
existing policy row is refused in the service (`no_existing_policy`) — there is no level to
preserve. **A single action kind would make "insufficient rank" untestable**; that is why
there are two.

### OD-3 — Decision vocabulary and mutual exclusivity

```
DECISIONS = ("allowed",
             "refused_unauthenticated_actor",
             "refused_no_grant",
             "refused_insufficient_role")
```

Pure `evaluate_authorization(request, grants) -> AuthorizationDecision` (frozen dataclass,
`ruleset_version="slice63.v1"`), evaluated in this fixed order:

1. `actor_provenance != "request_authenticated"` ⇒ `refused_unauthenticated_actor`,
   `actor_role=None`.
2. no active grant for `(tenant, principal)` ⇒ `refused_no_grant`, `actor_role=None`.
3. `max(rank of active grants) < required rank` ⇒ `refused_insufficient_role`,
   `actor_role` = the highest-rank active grant.
4. else ⇒ `allowed`, `actor_role` = the highest-rank active grant.

The four decisions are mutually exclusive by construction, and the DB enforces the same
partition (§3.2). Unknown `action_kind` / `admin_role` / decision ⇒ raise, never default.

### OD-4 — The unforgeable half is the grant row, and the privilege is the enforcement

`admin_role_grants` is tenant-owned with RLS ENABLE+FORCE and `tenant_isolation`, and
`uaid_app` is granted **`SELECT` only**. Minting and revoking are operator-path
(`ADMIN_DATABASE_URL`). This is the Slice-6 / 61a trust-zone pattern (a runtime-readable,
admin-written asset) applied to a *tenant-owned* table for the first time, so RLS still
scopes reads.

The root of trust is therefore the **operator DB credential**, stated openly in §0.3/§0.5.
Runtime delegation of grants is out of scope (`role_grant_delegation_not_implemented`).

### OD-5 — The `admin_actions` authority is a trigger, not an RLS `WITH CHECK`

An RLS `WITH CHECK` would be bypassed by the table owner / a superuser operator, so a
forged `allowed` inserted by the admin session would commit. A `BEFORE INSERT` trigger
fires for **every** role. `admin_actions_guard()` is `SECURITY INVOKER` (default) and
inlines its grant lookup — filtered on `NEW.tenant_id`, so it is correct both under RLS
(runtime) and without it (owner). It asserts:

- `decision IN ('allowed','refused_insufficient_role')` ⇒ an `admin_role_grants` row exists
  with `tenant_id=NEW.tenant_id`, `principal_subject=NEW.actor_principal`,
  `admin_role=NEW.actor_role`, `status='active'`.
- `decision='refused_no_grant'` ⇒ **no** `admin_role_grants` row exists with
  `tenant_id=NEW.tenant_id`, `principal_subject=NEW.actor_principal`, `status='active'`
  (any role). The refusal ledger cannot understate the grant state.
- `decision='refused_unauthenticated_actor'` ⇒ no grant assertion (exempt).

**No standalone table-reading SQL helper is created.** A `admin_grant_active(uuid,text,text)`
function EXECUTE-able by `uaid_app` would be a grant-existence oracle; inlining avoids it.
Trigger functions do not require `EXECUTE` for the invoker when the trigger fires, so no new
function grant is needed. A-no-helper-fn asserts no Slice-63 table-reading function is
EXECUTE-able by `uaid_app`.

### OD-6 — Rank arithmetic lives in the DB catalog as generated CHECK text, not a Python enum

`app/admin/db_checks.py` generates **inline SQL `CASE` expressions** from `ROLE_RANKS` /
`ACTION_REQUIRED_ROLE` and exports them as named CHECK-constraint strings, consumed by both
the ORM `__table_args__` and migration `0062` (the `catalog_db_checks` / `learning_db_checks`
pattern). No `IMMUTABLE` SQL function is introduced, so there is no CHECK-time function
permission question and no drift surface beyond the text itself. A-check-drift asserts the
installed `pg_constraint.consrc`-equivalent (`pg_get_constraintdef`) contains the
Python-generated expression for each named constraint — if a builder edits `ROLE_RANKS`
without re-running the migration, that assertion fails.

### OD-7 — Suspension is enforced in the resolver, so no Python changes and no new bypass

`0062` `DROP FUNCTION public.resolve_tenant_api_key(text)` and recreates it with the same
signature, `LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog`, owner
`api_key_resolver`, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE TO uaid_app` — the `0026`
model restored verbatim — with the body extended to:

```sql
SELECT k.tenant_id, k.principal_subject, k.actor_type
FROM public.tenant_api_keys k
JOIN public.tenants t       ON t.id = k.tenant_id
JOIN public.organizations o ON o.id = t.organization_id
WHERE k.key_hash = p_key_hash
  AND k.status = 'active'
  AND t.status = 'active'
  AND o.status = 'active'
LIMIT 1
```

plus `GRANT SELECT ON public.tenants, public.organizations TO api_key_resolver`. Both
tables are already `SELECT`-able by `uaid_app` (fact 0.1.4), so no new class of data
becomes readable; the new reader is a NOLOGIN definer role. A suspended tenant yields
NULLs, `TenantApiKeyRepository.resolve` returns `None`, and `require_tenant` raises the
existing generic 401 — **no existence oracle** (a suspended tenant is indistinguishable
from an unknown key). `app/api/auth.py` and `app/repositories/api_keys.py` stay frozen.

Limitation, stated: `tenant_scope` does not check status, so internal/operator callers and
in-flight work are unaffected (`suspension_not_enforced_inside_tenant_scope`).

### OD-8 — Operator writes are tenant-scoped, therefore auditable

`admin_role_grants` and `tenant_admin_events` are tenant-owned. The operator path opens an
admin session, sets `app.current_tenant` for the affected tenant, writes the row, and calls
`audit_append` — the same hash chain the runtime uses. `0062` adds
`GRANT EXECUTE ON FUNCTION public.audit_append(text,text,text,jsonb) TO CURRENT_USER` so a
least-privilege (non-superuser) operator role also works; a superuser `app` already has it
implicitly. **Trust-zone note:** `CURRENT_USER` at migration time is the role that owns the
schema and runs DDL — it can already write anything; giving it the *append* function does
not widen its reach and keeps the chain intact instead of tempting a direct `audit_logs`
INSERT. Downgrade revokes it.

Organization-level events carry the organization id plus the affected tenant id (one row per
tenant touched), so every audited row still has a tenant. Organizations remain non-tenant-owned.

### OD-9 — Audit payloads are safe metadata only

- Runtime: `action="admin_action.recorded"`, `actor` = the verified principal,
  `target=f"project:{project_id}"`, payload
  `{admin_action_id, action_kind, decision, required_role, actor_role, actor_provenance}`.
  On an allowed policy change also `action="admin_policy_change.recorded"` with
  `{admin_policy_change_id, autonomy_policy_id, previous_autonomy_level,
  new_autonomy_level, override_key_count}`.
- Operator: `action="admin_role.granted" | "admin_role.revoked" |
  "tenant.suspended" | "tenant.reinstated" | "organization.suspended" |
  "organization.reinstated"`, payload `{tenant_admin_event_id, event_kind, admin_role,
  subject_principal}` as applicable.

**Never** override *values*, policy JSON, key hashes, raw keys, or any document/prompt
content. Only override key **counts** are recorded (the Slice-3 audit already records key
names on its own path; Slice 63 adds no new content surface).

### OD-10 — No HTTP, no LLM, no broker, no A5, no new credential type

No route (the existing bearer boundary is the only entry point and it is unchanged except
for the resolver's status filter). No new tool, A1 action, connector, or LLM call. No
`PRICE_CARD` entry. `production_autonomy.py` / `readiness.py` / `control_loop.py` /
`broker.py` / `cost*.py` / `pricing.py` frozen (§1). No new secret material: the only new
text columns are principal subjects, role names, operator labels, and enum values.

---

## 3. Schema (migration `0062_enterprise_admin`)

All four tables: `tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT`, RLS
`ENABLE` + `FORCE`, policy `tenant_isolation USING (<PREDICATE>) WITH CHECK (<PREDICATE>)`
where `PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"`
(verbatim from `app/ecosystem/learning_ddl.py:12`), `REVOKE ALL ... FROM PUBLIC`,
`created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()`. All bounded text columns carry
both a `char_length BETWEEN 1 AND n` CHECK **and** a `btrim(col) <> ''` non-blank CHECK
(the Slice-41 B3 pattern).

### 3.1 `admin_role_grants` — tenant-owned; `uaid_app` **SELECT only**

`id`, `tenant_id`, `principal_subject TEXT` (≤255, non-blank),
`admin_role TEXT CHECK IN ADMIN_ROLES`, `status TEXT CHECK IN ('active','revoked')`,
`granted_by TEXT` (≤200, non-blank),
`granted_by_provenance TEXT CHECK (= 'operator_admin_session_unverified')`,
`created_at`, `updated_at`.

- `UNIQUE (tenant_id, principal_subject, admin_role)` — one row per triple; revoke flips
  `status`, it does not delete.
- `UNIQUE (id, tenant_id)`.
- Grants: `GRANT SELECT ON public.admin_role_grants TO uaid_app` — **no INSERT/UPDATE/DELETE.**
- Guard trigger `admin_role_grants_guard()`: INSERT ⇒ `status='active'`; UPDATE ⇒ only
  `status` and `updated_at` may change and only `active→revoked` (one-way); DELETE and
  TRUNCATE blocked by the standard pair from `app/ecosystem/learning_ddl.py:198-212` —
  `admin_role_grants_no_update_delete` (BEFORE UPDATE OR DELETE, FOR EACH ROW) and
  `admin_role_grants_no_truncate` (BEFORE TRUNCATE, FOR EACH STATEMENT) over
  `admin_role_grants_block_dml()`. Because UPDATE is legal here, the pair is installed for
  **DELETE only** on this table (`BEFORE DELETE`), and the one-way `status` rule is the
  UPDATE authority — do not install a BEFORE UPDATE block that would contradict revoke.

### 3.2 `admin_actions` — tenant-owned, append-only; `uaid_app` `SELECT, INSERT`

`id`, `tenant_id`, `project_id UUID NOT NULL` with composite FK
`(project_id, tenant_id) → projects(id, tenant_id)`,
`action_kind TEXT CHECK IN ADMIN_ACTION_KINDS`,
`actor_principal TEXT` (≤255, non-blank),
`actor_provenance TEXT CHECK IN ('caller_supplied_unverified','request_authenticated')`,
`required_role TEXT CHECK IN ADMIN_ROLES`,
`actor_role TEXT NULL CHECK (actor_role IS NULL OR actor_role IN ADMIN_ROLES)`,
`decision TEXT CHECK IN DECISIONS`,
`ruleset_version TEXT CHECK (= 'slice63.v1')`, `created_at`.

- `UNIQUE (id, project_id, tenant_id)` — the FK target for §3.3.
- Generated CHECKs (OD-6), each individually named so a probe can target it:
  - `ck_admin_actions_required_role_bound`:
    `required_role = CASE action_kind WHEN 'set_autonomy_policy' THEN 'tenant_admin'
     WHEN 'tighten_autonomy_overrides' THEN 'tenant_operator' END`
  - `ck_admin_actions_allowed_rank`: `decision <> 'allowed' OR
     (<rank(actor_role)> >= <rank(required_role)>)`
  - `ck_admin_actions_insufficient_rank`: `decision <> 'refused_insufficient_role' OR
     (<rank(actor_role)> < <rank(required_role)>)`
  - `ck_admin_actions_role_presence`: `actor_role IS NOT NULL` iff
    `decision IN ('allowed','refused_insufficient_role')`
  - `ck_admin_actions_allowed_authenticated`:
    `decision <> 'allowed' OR actor_provenance = 'request_authenticated'`
  - `ck_admin_actions_unauth_shape`: `decision <> 'refused_unauthenticated_actor' OR
     actor_provenance = 'caller_supplied_unverified'`

  The two rank CHECKs must **not** lean on SQL NULL semantics (a CHECK passes on NULL):
  `ck_admin_actions_role_presence` is what forces `actor_role IS NOT NULL` for the two
  decisions the rank CHECKs constrain, so all three must be installed together. A probe that
  drops `ck_admin_actions_role_presence` and then inserts `allowed` with `actor_role=NULL`
  must fail on `ck_admin_actions_allowed_rank` **or** the guard trigger — if it commits, the
  set is under-constrained and that is a defect.
- Guard trigger `admin_actions_guard()` (trigger name `admin_actions_guard_trg`) per OD-5
  (the grant-existence authority).
- Append-only: the `learning_ddl.py:198-212` pair verbatim —
  `admin_actions_no_update_delete` + `admin_actions_no_truncate` over
  `admin_actions_block_dml()`; grant is `SELECT, INSERT` only.

### 3.3 `admin_policy_changes` — tenant-owned, append-only; `uaid_app` `SELECT, INSERT`

`id`, `tenant_id`, `project_id`, `admin_action_id UUID NOT NULL`,
`autonomy_policy_id UUID NOT NULL`,
`previous_autonomy_level SMALLINT NULL CHECK (BETWEEN 0 AND 5)`,
`new_autonomy_level SMALLINT NOT NULL CHECK (BETWEEN 0 AND 5)`,
`override_key_count SMALLINT NOT NULL CHECK (>= 0)`, `created_at`.

- Composite FKs: `(admin_action_id, project_id, tenant_id) → admin_actions(id, project_id,
  tenant_id)`; `(autonomy_policy_id, project_id, tenant_id) → autonomy_policies(id,
  project_id, tenant_id)` (target `uq_autonomy_policies_id_proj_tenant`, fact 0.1.5).
- `UNIQUE (admin_action_id)` named **`uq_admin_policy_changes_action`** — one authorization
  is spent exactly once (`admin_action_id` is the PK of `admin_actions`, so a bare UNIQUE is
  already tenant-safe).
- Guard trigger `admin_policy_changes_guard()` (trigger name
  `admin_policy_changes_guard_trg`) BEFORE INSERT:
  - the referenced `admin_actions` row has `decision='allowed'` and
    `action_kind IN ADMIN_ACTION_KINDS`;
  - `NEW.new_autonomy_level` equals the referenced `autonomy_policies.autonomy_level`;
  - `action_kind='tighten_autonomy_overrides'` ⇒
    `previous_autonomy_level = new_autonomy_level` (level untouched, OD-2).
- Append-only; grant `SELECT, INSERT`.

### 3.4 `tenant_admin_events` — tenant-owned, append-only; `uaid_app` **SELECT only**

`id`, `tenant_id`, `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE
RESTRICT`,
`event_kind TEXT CHECK IN ('tenant_suspended','tenant_reinstated','organization_suspended',
'organization_reinstated','role_granted','role_revoked')`,
`subject_principal TEXT NULL` (≤255, non-blank when present),
`admin_role TEXT NULL CHECK (admin_role IS NULL OR admin_role IN ADMIN_ROLES)`,
`admin_role_grant_id UUID NULL` with composite FK `(admin_role_grant_id, tenant_id) →
admin_role_grants(id, tenant_id)`,
`performed_by TEXT` (≤200, non-blank),
`performed_by_provenance TEXT CHECK (= 'operator_admin_session_unverified')`, `created_at`.

- CHECK `ck_tae_role_shape`: `event_kind IN ('role_granted','role_revoked')` iff
  (`subject_principal IS NOT NULL AND admin_role IS NOT NULL AND admin_role_grant_id IS NOT NULL`).
- Guard trigger `tenant_admin_events_guard()` BEFORE INSERT — the ledger cannot lie:
  - `tenant_suspended` ⇒ `tenants.status='suspended'` for `NEW.tenant_id`;
    `tenant_reinstated` ⇒ `'active'`;
  - `organization_suspended` ⇒ `organizations.status='suspended'` for
    `NEW.organization_id`; `organization_reinstated` ⇒ `'active'`;
  - every kind ⇒ the tenant's `organization_id` equals `NEW.organization_id`;
  - `role_granted` ⇒ the referenced grant row is `status='active'`; `role_revoked` ⇒
    `'revoked'`.
- Grants: `GRANT SELECT ... TO uaid_app` only. Append-only.

### 3.5 Additive changes to existing objects

1. `organizations.status TEXT NOT NULL DEFAULT 'active'` + CHECK
   `status IN ('active','suspended')`. Existing rows become `'active'`. `app/models/organization.py`
   gains the mapped column. No grant change (`uaid_app` already has SELECT).
2. `resolve_tenant_api_key(text)` DROP + recreate per OD-7; `GRANT SELECT ON public.tenants,
   public.organizations TO api_key_resolver`.
3. `GRANT EXECUTE ON FUNCTION public.audit_append(text,text,text,jsonb) TO CURRENT_USER`
   (OD-8).

Nothing else is altered. `autonomy_policies`, `tenants`, `tenant_api_keys`, `projects`,
`audit_logs` keep their existing columns, constraints, triggers, and grants.

### 3.6 Downgrade

`downgrade()` order: (a) fail closed via `populated_downgrade_sql()` if **any** of the four
tables has a row; (b) restore the `0026` resolver body byte-for-byte (owner/grants
restored) and `REVOKE SELECT ON public.tenants, public.organizations FROM api_key_resolver`;
(c) `REVOKE EXECUTE ON FUNCTION public.audit_append(...) FROM CURRENT_USER`; (d) drop the
guards/triggers; (e) drop the four tables (children first); (f) drop
`organizations.status`. Empty-database `0062 → 0061` must succeed.

---

## 4. Python modules (new unless noted; all ≤500 lines)

| Path | Responsibility |
|---|---|
| `app/admin/__init__.py` | package marker |
| `app/admin/rbac.py` | pure: `ADMIN_ROLES`, `ROLE_RANKS`, `ADMIN_ACTION_KINDS`, `ACTION_REQUIRED_ROLE`, `DECISIONS`, `RULESET_VERSION`, bounds, validators, frozen `AdminActionRequest` / `RoleGrantView` / `AuthorizationDecision`, pure `evaluate_authorization` (OD-3) |
| `app/admin/db_checks.py` | the named CHECK strings + the generated rank/required-role `CASE` expressions (OD-6); consumed by ORM **and** migration |
| `app/admin/guards_sql.py` | the four `plpgsql` guard bodies + `_block_dml` pairs as strings |
| `app/admin/ddl.py` | `install_admin_guards()` / `drop_admin_guards()` / `populated_downgrade_sql()` / resolver replace + restore / grant matrix |
| `app/admin/tenant_admin.py` | **operator path** (admin session): `suspend_tenant`, `reinstate_tenant`, `suspend_organization`, `reinstate_organization`, `grant_admin_role`, `revoke_admin_role` — each sets the tenant GUC, writes the row + `tenant_admin_events`, and calls `audit_append` (OD-8/OD-9) |
| `app/admin/policy_admin.py` | **runtime service**: `apply_policy_change(...) -> PolicyChangeResult`; owns `tenant_scope`, loads grants, pure-evaluates, records `admin_actions` (allowed **and** refused), on allowed calls the frozen `AutonomyPolicyRepository.upsert` then writes `admin_policy_changes`, audits both |
| `app/models/admin_rbac.py` | `AdminRoleGrant`, `AdminAction` |
| `app/models/admin_policy.py` | `AdminPolicyChange`, `TenantAdminEvent` |
| `app/repositories/admin.py` | `AdminGrantRepository` (tenant read), `AdminActionRepository` (insert + reads), `AdminPolicyChangeRepository` |
| `scripts/admin_roles.py` | operator CLI, argparse subcommands `grant`, `revoke`, `suspend-tenant`, `reinstate-tenant`, `suspend-org`, `reinstate-org`; prints ids/status only, never a key or an override value; uses `ADMIN_DATABASE_URL` |
| `migrations/versions/0062_enterprise_admin.py` | additive; imports the CHECK strings and DDL helpers (the `0061` import pattern) |

Tests (all new): `tests/test_admin_rbac.py` (pure), `tests/test_admin_rbac_db.py`,
`tests/test_admin_policy_db.py`, `tests/test_admin_tenant_db.py`,
`tests/test_admin_checks.py`, `tests/test_admin_migrate.py`, plus
`tests/admin_support.py` (shared seeding: org + two tenants + projects + keys + grants).

`policy_admin.apply_policy_change` refuses **before** touching the policy: on any
non-`allowed` decision it records the refusal action + audit and returns/raises without
calling `upsert`, and P-service-refusal-no-write proves the `autonomy_policies` row is
byte-identical afterwards. Insert order inside one transaction: `admin_actions` →
(`upsert`, flush) → `admin_policy_changes`.

No `Makefile` target is added; the operator CLI is invoked as
`uv run python -m scripts.admin_roles <subcommand> …`. `make migrate` /
`test-db-migrate` stay schema-only: a freshly migrated database has **zero** grants, so no
runtime admin action can be `allowed` until an operator grants a role.

---

## 5. Probes

### 5.0 The owner test standard (applies to every probe in §5.2)

Sol's Slice-62 finding is carried forward. For **every** guard, the probe must satisfy all
three, and the plan names how:

1. **The mutation must actually be able to commit if the guard were absent.** Each refusal
   probe pairs with an explicit mutation: `ALTER TABLE … DISABLE TRIGGER <exact name>` (or
   `ALTER TABLE … DROP CONSTRAINT <exact name>`, or a temporary `GRANT`), re-run the *same*
   statement, assert it **commits**, then restore and assert `tgenabled='O'` /
   the constraint/grant is back. A mutation that cannot commit proves nothing and is a
   REJECT.
2. **It must fail for the guard's own reason, not a neighbouring constraint.** Every probe
   payload is otherwise fully valid, and the assertion matches on the guard's own error —
   `pg_constraint` name for CHECK/UNIQUE violations, or the guard's own `RAISE` message
   text for trigger violations. A bare "some IntegrityError" is a REJECT. Where two guards
   could both fire, the plan says which one is under test and the payload satisfies the other.
3. **The denial must be proven on the exact object the guard protects.** Table name and
   trigger/constraint name are asserted, and privilege denials are proven by attempting the
   statement **as `uaid_app` through `rls_engine`** — never as the admin role. Any forgery
   probe run as admin is a REJECT (the Slice-60 finding).

Global: use `DISABLE TRIGGER`/`DROP CONSTRAINT` on the **named** object only; never
`SET CONSTRAINTS ALL DEFERRED`, never a session-wide `session_replication_role`, and always
restore in a `finally`.

### 5.1 Pure probes

- **P-1** `ADMIN_ROLES` is exactly the three OD-1 names; `ROLE_RANKS` values are
  `{1,2,3}` and distinct; `ADMIN_ACTION_KINDS` and `ACTION_REQUIRED_ROLE` match OD-2
  key-for-key; `DECISIONS` is exactly the four OD-3 values; `RULESET_VERSION == "slice63.v1"`.
- **P-2** `evaluate_authorization` decision table: (a) unverified provenance ⇒
  `refused_unauthenticated_actor` even with a `tenant_admin` grant present (order matters);
  (b) no grants ⇒ `refused_no_grant`, `actor_role is None`; (c) `tenant_viewer` only,
  `set_autonomy_policy` ⇒ `refused_insufficient_role`, `actor_role='tenant_viewer'`;
  (d) `tenant_operator`, `tighten_autonomy_overrides` ⇒ `allowed`; (e) `tenant_operator`,
  `set_autonomy_policy` ⇒ `refused_insufficient_role`; (f) `{tenant_viewer, tenant_admin}`
  both active ⇒ `allowed` with `actor_role='tenant_admin'` (highest rank wins);
  (g) a `revoked` grant is not counted.
- **P-3** unknown `action_kind`, unknown `admin_role`, blank/oversized `actor_principal`
  ⇒ raise, never a default decision.
- **P-4** `app/admin/*.py` source contains no bearer-key, raw-key, override-**value**, or
  document/prompt parameter name; `inspect.signature` of every public function in
  `app.admin.rbac`, `tenant_admin`, `policy_admin` has no parameter named `content`,
  `document`, `prompt`, `body`, `raw_key`, `key_hash`, or `password`.
- **P-5** the eighteen frozen hashes match §1 exactly.
- **P-6** `A5_RULESET_VERSION == "slice54.v1"`; readiness `RULESET_VERSION == "slice20.v1"`;
  `can_go_live_autonomously is False` by identity.

### 5.2 Named refusal probes (each with its §5.0 mutation)

Unless stated, the statement under test is executed **as `uaid_app` inside `tenant_scope`**.

| Probe | Guard under test | Refusal payload (otherwise fully valid) | Mutation that must commit |
|---|---|---|---|
| **P-grant-no-write** | privilege: `uaid_app` has no INSERT/UPDATE/DELETE on `admin_role_grants` | as `uaid_app`, INSERT a well-formed active grant ⇒ `InsufficientPrivilege` on `admin_role_grants`; separately UPDATE and DELETE an admin-seeded grant ⇒ `InsufficientPrivilege` (three statements, one table) | as admin `GRANT INSERT ON public.admin_role_grants TO uaid_app`; the *same* INSERT commits; then `REVOKE INSERT` and re-assert denial. The mutation's payload uses a throwaway principal so the residual row is inert (the table is DELETE-blocked by design — do not attempt cleanup by DELETE) |
| **P-allow-no-grant** | `admin_actions_guard()` | `decision='allowed'`, `action_kind='set_autonomy_policy'`, `actor_role='tenant_admin'`, `actor_provenance='request_authenticated'`, **no** grant row ⇒ guard `RAISE` | `ALTER TABLE public.admin_actions DISABLE TRIGGER admin_actions_guard_trg`; same INSERT commits; restore, assert `tgenabled='O'` |
| **P-allow-no-grant-as-admin** | same guard binds the owner role | the identical INSERT executed on the **admin** session ⇒ same guard `RAISE` (proves OD-5's trigger-not-RLS choice) | same disable/restore, run as admin |
| **P-allow-revoked-grant** | same guard | grant exists but `status='revoked'` ⇒ guard `RAISE` (all CHECKs satisfied: rank is sufficient) | same |
| **P-allow-cross-tenant-grant** | same guard + §17.3 | principal holds an **active `tenant_admin`** grant in tenant **B**; INSERT `allowed` in tenant **A**'s scope ⇒ guard `RAISE`. This is the "admin convenience does not override tenant isolation" probe | same disable/restore; with the guard off the row commits, proving the guard — not RLS visibility — is what refuses |
| **P-allow-insufficient-rank** | CHECK `ck_admin_actions_allowed_rank` | seed an **active `tenant_operator`** grant (so the trigger passes), INSERT `allowed` for `set_autonomy_policy` with `actor_role='tenant_operator'` ⇒ violation names `ck_admin_actions_allowed_rank` | `ALTER TABLE … DROP CONSTRAINT ck_admin_actions_allowed_rank`; same INSERT commits; re-add from `db_checks.py` |
| **P-required-role-forged** | CHECK `ck_admin_actions_required_role_bound` | `action_kind='set_autonomy_policy'` with `required_role='tenant_operator'` and `actor_role='tenant_operator'` + a matching active grant (so trigger and rank CHECK both pass) ⇒ violation names `ck_admin_actions_required_role_bound` | drop/re-add that named constraint |
| **P-refuse-mislabel** | `admin_actions_guard()` | an **active `tenant_viewer`** grant exists; INSERT `decision='refused_no_grant'`, `actor_role=NULL` (so `ck_admin_actions_role_presence` is satisfied) ⇒ guard `RAISE` | disable/restore `admin_actions_guard_trg` |
| **P-unauth-allowed** | CHECK `ck_admin_actions_allowed_authenticated` | `decision='allowed'` with `actor_provenance='caller_supplied_unverified'`, valid active `tenant_admin` grant ⇒ violation names that constraint | drop/re-add |
| **P-actions-append-only** | `admin_actions_no_update_delete` / `admin_actions_no_truncate` | as **admin** (the runtime role lacks the privilege, so a `uaid_app` attempt would prove the grant, not the trigger — the §5.0 rule 3 object here is the trigger): UPDATE `decision`, DELETE the row, TRUNCATE ⇒ each refused by the named trigger. Repeat the same three on `admin_policy_changes` and `tenant_admin_events` | `DISABLE TRIGGER admin_actions_no_update_delete`; the same UPDATE commits; restore and assert `tgenabled='O'` |
| **P-grant-update-widen** | `admin_role_grants_guard()` | as **admin**, UPDATE a revoked grant back to `status='active'` (reverse direction) ⇒ guard `RAISE`; and UPDATE `admin_role` on an active grant ⇒ guard `RAISE` | disable/restore `admin_role_grants_guard_trg` |
| **P-change-refused-action** | `admin_policy_changes_guard()` | reference an `admin_actions` row with `decision='refused_insufficient_role'`; every FK/CHECK satisfied and `new_autonomy_level` equal to the real policy level ⇒ guard `RAISE` on the decision clause | disable/restore `admin_policy_changes_guard_trg` |
| **P-change-level-mismatch** | same guard | referenced action is `allowed`; the real `autonomy_policies.autonomy_level` is 3; record `new_autonomy_level=2` (in-range, so the 0–5 CHECK cannot mask it) ⇒ guard `RAISE` on the level clause | same disable/restore |
| **P-change-tighten-level-moved** | same guard | `action_kind='tighten_autonomy_overrides'`, `previous_autonomy_level=2`, `new_autonomy_level=3` where the policy really holds 3 (so the level clause passes) ⇒ guard `RAISE` on the tighten clause | same |
| **P-change-action-reuse** | `UNIQUE (admin_action_id)` on `admin_policy_changes` | commit one valid change; INSERT a second row for the **same** `admin_action_id`, differing only in `id`, with every guard clause still satisfied ⇒ violation names `uq_admin_policy_changes_action` | `DROP CONSTRAINT uq_admin_policy_changes_action`; the second row commits; re-add |
| **P-event-lies** | `tenant_admin_events_guard()` | tenant is `active`; as **admin**, INSERT `event_kind='tenant_suspended'` with matching org id and valid shape ⇒ guard `RAISE`. Repeat the mirror for `organization_suspended` while the org is `active` | disable/restore `tenant_admin_events_guard_trg` |
| **P-event-wrong-org** | same guard | valid `role_granted` shape but `organization_id` set to a **second** organization that does not own the tenant ⇒ guard `RAISE` on the org clause (FK is satisfied — the org exists) | same |
| **P-event-role-grant-status** | same guard | `event_kind='role_revoked'` referencing a grant whose `status` is still `'active'` ⇒ guard `RAISE` | same |
| **P-tae-no-runtime-write** | privilege | as `uaid_app`, INSERT into `tenant_admin_events` ⇒ `InsufficientPrivilege` on that table | temporary `GRANT INSERT`; the same INSERT commits (payload uses a throwaway tenant so the residue is inert — the table is append-only, do not clean up by DELETE); `REVOKE INSERT`, re-assert denial |
| **P-suspend-tenant-blocks** | resolver body | issue a key (raw returned once), assert it resolves; as admin set `tenants.status='suspended'`; the **same raw key** now yields `resolve(...) is None`, **and** a real HTTP `GET /api/projects/{id}/runs` with that bearer returns **401** with the generic body | restore the `0026` resolver body (drop + create the old body) — the same key resolves again; reinstall the `0062` body and re-assert `None`. This proves the resolver clause, not a Python check |
| **P-suspend-org-blocks** | resolver body | tenant stays `active`; set `organizations.status='suspended'` ⇒ `resolve(...) is None` and HTTP 401 | same resolver mutation |
| **P-reinstate-restores** | resolver body | after either suspension, set status back to `'active'` ⇒ the same key resolves and the endpoint returns 200 (proves suspension is a live filter, not a one-way key kill) | n/a (positive control for the two above) |
| **P-suspend-no-oracle** | resolver body | a suspended-tenant key and a syntactically valid **unknown** key produce byte-identical 401 status + body + headers | n/a (assertion, paired with the two above) |
| **P-rls-cross-tenant** | `tenant_isolation` on all four tables | seed rows for tenants A and B; as `uaid_app` in A's scope, `SELECT` each table ⇒ zero B rows; attempt an `admin_actions` INSERT with `tenant_id = B` ⇒ RLS `WITH CHECK` violation on `admin_actions` | `ALTER TABLE public.admin_actions NO FORCE ROW LEVEL SECURITY` + `DISABLE ROW LEVEL SECURITY`; the cross-tenant INSERT commits; restore ENABLE+FORCE |
| **P-service-refusal-no-write** | `policy_admin` ordering | call `apply_policy_change` for a principal with **no** grant; assert (a) an `admin_actions` row with `decision='refused_no_grant'` exists, (b) `admin_policy_changes` gained no row, (c) the `autonomy_policies` row's `autonomy_level`/`overrides`/`updated_at` are unchanged | remove the pre-`upsert` decision check in a monkeypatched copy of the service ⇒ the policy is written; assert the unpatched service does not |
| **P-audit-chain** | audit coverage | an allowed change and a refused attempt each append an `audit_logs` row with the OD-9 action name and payload keys; `audit_verify()` returns `ok=true`; no payload value contains an override value, a key hash, or a raw key | monkeypatch the service's `audit_record` to a no-op ⇒ the row count does not increase, proving the assertion is load-bearing |
| **P-downgrade-resolver** | `0062.downgrade()` | on an empty DB, `alembic downgrade 0061` then assert `pg_get_functiondef` for `resolve_tenant_api_key` is byte-identical to the `0026` body, `api_key_resolver` no longer has SELECT on `tenants`/`organizations`, and `organizations.status` is gone | n/a (direct assertion) |
| **P-downgrade-populated** | `populated_downgrade_sql()` | with one row in **each** of the four tables (four separate sub-cases, one per table, so the guard is proven on each object) `alembic downgrade 0061` fails closed | n/a (four positive refusals; the empty-DB success in P-downgrade-resolver is the paired control) |

### 5.3 Catalog / invariant assertions (not refusal probes)

- **A-grant-matrix** `information_schema.role_table_grants` for `uaid_app` is exactly:
  `admin_role_grants` → `{SELECT}`; `tenant_admin_events` → `{SELECT}`;
  `admin_actions` → `{SELECT, INSERT}`; `admin_policy_changes` → `{SELECT, INSERT}`.
  No `UPDATE`, `DELETE`, `TRUNCATE`, or `REFERENCES` anywhere. `PUBLIC` has none.
- **A-rls-enabled** `pg_class.relrowsecurity` **and** `relforcerowsecurity` are true for all
  four tables, and each has exactly one policy named `tenant_isolation` whose
  `pg_get_expr` text equals the `PREDICATE` string.
- **A-check-drift** for each named constraint in §3.2/§3.3/§3.4,
  `pg_get_constraintdef` contains the expression generated by `app/admin/db_checks.py`
  (OD-6). Editing `ROLE_RANKS` without a migration fails this.
- **A-no-helper-fn** no function created by `0062` that reads a table is EXECUTE-able by
  `uaid_app` (query `information_schema.routine_privileges`); only the four trigger
  functions exist and they are invoked by triggers, not granted.
- **A-triggers-enabled** after the whole DB suite, every Slice-63 trigger has
  `tgenabled='O'` (catches an unrestored mutation).
- **A-head** `uv run alembic heads` → `0062`; exactly one head.
- **A-frozen-untouched** real `ProductionAutonomyRepository.evaluate` and
  `ReadinessRepository.evaluate` before and after a full admin flow (grant → allowed change
  → suspend → reinstate) are bit-equal on `a5_satisfied`, `can_go_live_autonomously`,
  `ruleset_version`, every gate `status`, and readiness `readiness_level` /
  `ruleset_version`. Not a pure-function tautology — both go through the repositories.
- **A-no-http-surface** the FastAPI route table is unchanged versus `main` (same paths and
  methods); `app/admin/**` imports no `fastapi` symbol.

---

## 6. Documentation language, required

`CLAUDE.md` and `README.md` must:

- carry the §0.3 honesty crux **verbatim**;
- state Slice 63 adds org/tenant administration, DB-enforced RBAC, and role-gated policy
  management over the existing tenant model, and **closes no spec section**;
- name the four limitations explicitly: `read_api_not_role_gated`,
  `suspension_not_enforced_inside_tenant_scope`, `role_grant_delegation_not_implemented`,
  and "an operator holding DB-owner credentials is not constrained by this RBAC";
- state that the Slice 61 exit and D-8 / D-9 / D-10 stay **OPEN** (owner = Salim);
- state A5 `slice54.v1`, readiness `slice20.v1`, `can_go_live_autonomously` literal `False`;
- state that a freshly migrated database has zero role grants, so no runtime admin action
  can be `allowed` until an operator grants a role;
- record no test counts in `README.md`.

Roadmap Slice 63 **Exit** may be marked as enterprise administration delivered with tenant
isolation intact, and the roadmap's "end-to-end system complete" wording may be recorded
**only** as a roadmap-scope statement, immediately qualified by: go-live is not authorized,
`can_go_live_autonomously` is still `False`, the Slice 61 exit is still open, and
D-8/D-9/D-10 are still open. Do **not** mark Slice 61 done. Do **not** claim go-live.
Do **not** add a Slice 64.

---

## 7. Deferred / not claimed

| Capability | Disposition |
|---|---|
| Slice 61 exit / D-8 / D-9 / D-10 | Stay OPEN, owner = Salim |
| Role-gating the read API | Deferred (`read_api_not_role_gated`) |
| Runtime delegation of role grants | Deferred (`role_grant_delegation_not_implemented`) |
| Suspension enforcement inside `tenant_scope` / against running work | Deferred |
| Verified-human authority for a grant (a signer tier above `request_authenticated`) | Deferred |
| Constraining an operator with DB-owner credentials | Out of reach; stated, not claimed |
| HTTP admin API / admin UI | Deferred (OD-10) |
| Per-project or per-resource ACLs, groups, SCIM/SSO, key rotation policy | Deferred |
| Platform-event audit of non-tenant-owned global writes | Deferred (Slice-6 precedent) |
| A5 / readiness / go-live movement | Forbidden |

---

## 8. Non-goals, restated

No change to the eighteen frozen files. No new HTTP route, tool, A1 action, connector, LLM
call, or credential type. No RLS bypass, no new privilege for `uaid_app` beyond
`SELECT`/`INSERT` on the two ledgers and `SELECT` on the two admin-written tables. No
budget figures. No spec edit. No softening of go-live or §2.6. No Slice 64.

---

## 9. Builder constraints

- TDD: land P-1…P-6 and a failing P-allow-no-grant / P-grant-no-write first.
- Every guard in §3 has a named probe in §5.2 and must satisfy all three §5.0 conditions.
  A probe whose mutation cannot commit is a defect, not a pass.
- All forgery/privilege probes run as **`uaid_app`** via `rls_engine`, except the four that
  must exercise the owner path because the runtime role has no privilege to reach the guard
  under test: P-allow-no-grant-as-admin, P-event-lies (and its two siblings
  P-event-wrong-org / P-event-role-grant-status), P-grant-update-widen, and
  P-actions-append-only. Each of those states in its docstring why `uaid_app` cannot be the
  actor there. Any *other* probe run as admin is a defect.
- Restore every disabled trigger / dropped constraint / temporary grant in a `finally`, and
  let A-triggers-enabled catch a miss.
- Do not `ruff format` the whole tree. Line cap 500 per file — split rather than grow
  (`guards_sql.py` is pre-split from `ddl.py` for exactly this reason).
- `pyright` on the CI-owned paths **plus** every new Slice-63 module and test in §4;
  0 errors on that set. Full-repo pyright remains out of scope (pre-existing errors).
- Conventional commits (`feat(admin):`, `test(admin):`, `feat(migrations):`). Do not commit
  `.env`. **Do not edit this plan.**
- Branch `feat/slice-63-enterprise-admin`. Do not open the PR before Sol's code APPROVE.

---

## 10. Change log

**v1.** First version. Grounded on `main` @ `4a89742` (Slice 62 merged via PR #114 plus
close-out PR #115; live Alembic head `0061`; no `app/admin/` package). Carries forward the
owner test standard from Sol's Slice-62 code REJECT: mutation-must-commit, own-reason, and
exact-object for every guard (§5.0).
