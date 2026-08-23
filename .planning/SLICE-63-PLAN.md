# Slice 63 — Enterprise administration (org/tenant admin, DB-enforced RBAC, role-gated policy management)

**Seats (ruling 2026-08-23, standing).** PLANNER = Claude/Fable seat (this document).
BUILDER = Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on
plan and code, probe-backed verdicts only. **The builder never edits this plan.**

**Version.** **v2.** Sol REJECTED v1; **consecutive plan REJECT count = 1, accepted in full**
(all six defects accepted, none argued down — see §10). Owner (Salim) authorized Slice 63
with no further owner gate (2026-08-24). Halt rule unchanged: three consecutive REJECTs on
this plan line ⇒ stop, no v4 without the owner.

> **This slice closes NO spec section and does NOT satisfy the roadmap Slice 61 exit.**
> D-8, D-9, and D-10 stay **OPEN** (owner = Salim). Slice 63 is the last scheduled slice:
> after it merges the coordinator STOPS for the Slice 55–63 final report. **This plan does
> not schedule Slice 64.**

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 63 (l.655–668).
**Spec grounding.** §26.7 last bullet ("enterprise administration", l.2522); §17.2 tenant
isolation controls (l.1698–1714); §17.3 tenant boundary rule (l.1716–1718); §16.1
"authorization" + "role-based access control" (l.1550–1568); §16.6 audit; §5/§2.6 (the
policy object being managed). **A5 / readiness / go-live are untouched.**

**Alembic.** Live head **re-verified for v2**: `uv run alembic heads` → **`0061 (head)`**
(`migrations/versions/0061_cost_learning.py`, `revision="0061"`, `down_revision="0060"`), run
on branch `feat/slice-63-enterprise-admin` at plan time. This slice adds **migration `0062`**,
file `migrations/versions/0062_enterprise_admin.py`, `revision="0062"`,
`down_revision="0061"`. Its footprint:

- **four new tables** (each with its own PK/UNIQUE/CHECK/FK/trigger set);
- **one new column** on an existing table (`organizations.status`);
- **two new functions**: `public.admin_write_autonomy_policy(...)` (SECURITY DEFINER, owned by
  the new NOLOGIN role `policy_admin_writer`) and the pure helper
  `public.admin_overrides_is_monotonic(jsonb, jsonb)`;
- **one function DROP+recreate**, same signature (`resolve_tenant_api_key`);
- **one privilege NARROWING on an existing table** —
  `REVOKE INSERT, UPDATE ON public.autonomy_policies FROM uaid_app` (§OD-11, defect 1).
  This is the one place Slice 63 changes an existing `uaid_app` grant, and it **removes**
  privilege; `SELECT` is untouched so every existing read path is unaffected;
- **grant additions**: to `policy_admin_writer`, `SELECT, INSERT, UPDATE ON
  autonomy_policies` plus `SELECT ON admin_actions, admin_policy_changes` (the rows its
  function must read); `SELECT ON tenants, organizations` to `api_key_resolver`;
  `EXECUTE ON audit_append` to `CURRENT_USER`.

**No existing table gains a UNIQUE, and no existing constraint or trigger is dropped, and no
`uaid_app` privilege is widened anywhere.** **Re-verify the head before writing the file**;
if it is not `0061`, stop and report rather than renumbering silently.

**New bootstrap role.** `scripts/bootstrap_rls_role.sql` gains `policy_admin_writer`
(NOLOGIN NOSUPERUSER NOBYPASSRLS, idempotent `DO $$` block, verbatim in the shape of
`audit_writer` at `scripts/bootstrap_rls_role.sql:41-48`). That file is **not** in the frozen
set. `0062` must fail closed with a message naming `make db-bootstrap-rls-role` if the role is
absent, following the `0003`/`0013` precedent that the bootstrap runs first.

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
   `tenants` / `organizations` status they claim, and whose role events are **FK-bound to the
   exact grant row they name** (§OD-13, defect 5).
2. **RBAC that SQL cannot ignore.** A tenant-owned `admin_role_grants` table on which the
   runtime role `uaid_app` has **SELECT only** — it can read grants, and cannot mint them.
   Every role-gated admin action is recorded in append-only `admin_actions`, where a
   BEFORE-INSERT guard trigger (which binds the admin role too, unlike an RLS `WITH CHECK`)
   enforces a **total, DB-derived partition** of the four decisions against the real grant
   state: `allowed` and `refused_insufficient_role` require the recorded role to be the
   **highest active same-tenant grant** the principal holds, `refused_no_grant` requires that
   *no* active grant exists, and an unauthenticated actor can only ever be recorded as
   `refused_unauthenticated_actor` (§OD-3/§OD-5, defect 6).
3. **Role-gated policy management that is a real DB lock, not a ledger about a bypass.**
   `uaid_app` **loses** `INSERT`/`UPDATE` on `autonomy_policies` (§OD-11, defect 1). The only
   remaining write path for the runtime role is the SECURITY DEFINER function
   `admin_write_autonomy_policy`, owned by a NOLOGIN `policy_admin_writer`, which refuses
   unless it is handed an `allowed`, policy-kind, same-tenant, **unspent** `admin_actions`
   row — and which, for `tighten_autonomy_overrides`, refuses any override map that is not
   **monotonically at least as restrictive as the map currently stored** (§OD-12, defect 2).
   `admin_policy_changes` then records the change, guarded as in v1.

### 0.1 Grounding facts (re-verified 2026-08-24 on branch `feat/slice-63-enterprise-admin`)

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
5. **`uq_autonomy_policies_id_proj_tenant` already exists** on `(id, project_id, tenant_id)`
   (added by `migrations/versions/0052_production_preapprovals.py:624`). No new UNIQUE is
   needed on `autonomy_policies`; Slice 63 only FKs to it.
6. **`audit_append` is granted to `uaid_app` only** (`0003_audit_log.py:204`), signature
   `public.audit_append(text, text, text, jsonb)` (`0003_audit_log.py:39`), with
   `REVOKE ALL ... FROM PUBLIC` and owner `audit_writer`. It derives the tenant from
   `app.current_tenant` and fails closed when unset (`0003_audit_log.py:138`). Runtime
   admin actions can therefore be hash-chain audited. The operator path can only audit if
   the migration-running role holds EXECUTE — true implicitly for a superuser `app`, false
   for a least-privilege operator — so `0062` adds an explicit
   `GRANT EXECUTE ... TO CURRENT_USER` (§3.5).
7. **The precedent for global admin writes is "the row is the trail."** Slice 6
   (`register_blueprint`/`register_version`), Slice 61a/61b (`CatalogAdmin`), and Slice 62
   (`publish_cross_project_aggregates`) deliberately do **not** call `audit_append`;
   platform-event audit stays deferred. Slice 63's operator path writes *tenant-owned*
   rows, so it **can** and **does** set the tenant GUC and audit — that is a strict
   improvement, not a new claim about global writes.
8. **`uaid_app` holds `SELECT, INSERT, UPDATE` on `autonomy_policies` today** — confirmed
   live: `information_schema.table_privileges` for `autonomy_policies` returns exactly
   `uaid_app → {SELECT, INSERT, UPDATE}` plus the owner `app`, and the grant is
   `migrations/versions/0004_autonomy_policies.py:87-88`
   (`GRANT SELECT, INSERT, UPDATE ... TO uaid_app`, "NO DELETE"). **This is Sol's defect 1**
   and §OD-11 revokes the two write privileges.
9. **No product module writes `autonomy_policies`.** `app/repositories/autonomy_policies.py`
   is the only writer; every other module that touches the table
   (`app/intake/readiness.py`, `app/repositories/readiness.py`,
   `app/repositories/production_autonomy.py`, `app/runtime/control_loop.py`,
   `app/tools/broker.py`, `app/repositories/ops_*.py`,
   `app/repositories/production_preapprovals.py`, `app/repositories/go_live_decisions.py`,
   `app/repositories/emergency_controls.py`) consumes `decision_for` /
   `snapshot_decisions` / a read query. **The revoke therefore breaks no product path.**
10. **`AutonomyPolicyRepository.upsert` is called from tests only** — 32 call sites across
    20 test files (`rg '\.upsert\(' tests/`, filtered to `AutonomyPolicyRepository`).
    `upsert` is defined at `app/repositories/autonomy_policies.py:49` and already documents
    `actor` as UNTRUSTED (`:58-61`). This is the named break of §OD-11 and §OD-14 is its
    remedy.
11. **Almost every one of those call sites runs as `uaid_app`.** They are wrapped in
    `async with tenant_scope(...) as session`, and `tenant_scope` uses the `app.db` engine
    (`TEST_DATABASE_URL` = the runtime `uaid_app` role). The exception class is call sites on
    the `db_session` fixture, which `tests/conftest.py:124-135` documents as connecting **with
    ADMIN creds (`app`)** in a rolled-back outer transaction (e.g.
    `tests/test_emergency_controls.py:491`). `app` is `rolsuper=t rolbypassrls=t` and owns
    `autonomy_policies` (verified live), so the revoke does not affect admin-path sites — only
    the new required argument does. §OD-14's helper must therefore have two modes.
12. **A5 is `slice54.v1`; readiness is `slice20.v1`; `can_go_live_autonomously` is the
    literal `False`** (`app/release/production_autonomy.py:71,119`;
    `app/intake/readiness.py:45`). Slice 63 must not move any of them.

### 0.2 Load-bearing claim

**Policy writes.** For the runtime role `uaid_app`, `autonomy_policies` is **write-locked**:
it holds `SELECT` and no `INSERT`/`UPDATE`/`DELETE`, so no repository, service, or ad-hoc SQL
executed as `uaid_app` can change a project's autonomy level or override map except by calling
`public.admin_write_autonomy_policy`, which fails closed unless handed an `admin_actions` row
that is `allowed`, of a policy kind, in the caller's own tenant and project, and **not already
spent** by an `admin_policy_changes` row. For `tighten_autonomy_overrides` it additionally
refuses any override map that is not monotonically at least as restrictive as the map the row
**currently** holds, so an empty map cannot re-enable a disabled action. Because the definer
role `policy_admin_writer` is neither the table owner nor `BYPASSRLS`, and
`autonomy_policies` is `FORCE ROW LEVEL SECURITY`, the definer path is **still confined to the
caller's tenant** by the existing `tenant_isolation` policy.

**Authorization.** An `admin_actions` row with `decision='allowed'` exists only if, in that
same tenant, an `admin_role_grants` row with `status='active'` binds that `actor_principal` to
that `actor_role`, that role is the **highest-ranked** active grant the principal holds, and
its rank meets the action kind's required rank. `refused_insufficient_role` requires the same
highest-grant identity with rank *below* the requirement — so a refusal cannot be recorded
while a sufficient higher grant is active. `refused_no_grant` requires that no active grant
exists at all. An unauthenticated actor can only be recorded as
`refused_unauthenticated_actor`. `uaid_app` cannot create a grant row — it has SELECT only.

**Ledger fidelity.** An `admin_policy_changes` row exists only if it references such an
`allowed` policy-kind action (spent once) and records the autonomy level the referenced
`autonomy_policies` row actually holds. A `tenant_admin_events` role event is composite-FK
bound to the exact grant row's `(id, tenant_id, principal_subject, admin_role)`, so it cannot
name a principal or role the grant does not carry. A bearer key whose tenant or organization
is `suspended` does not resolve.

That does **not** prove: that the recorded `actor_principal` is the principal that
authenticated (the service stamps it from the Slice-27 `AuthenticatedActor`; the literal
`request_authenticated` is app-stamped and direct SQL as `uaid_app` can write it); that a
grant reflects a real human authority decision (the grant's own provenance is
`operator_admin_session_unverified`); that an operator holding DB-owner credentials is
constrained by anything here (that actor can insert grants and write policies directly);
that `set_autonomy_policy` cannot *relax* a project-specific override (it can — the
authority to loosen a project's own extra tightening is the admin action; the §5/§2.6 matrix
floor below which nothing may go is enforced by the frozen
`app/policy/matrix.py:validate_overrides` in Python, **not** by the DB —
`matrix_floor_enforced_in_python_only`); that suspension stops work already running inside
`tenant_scope`; that cost budgets are RBAC-gated (they are not —
`cost_budget_writes_not_rbac_gated`); or that any read endpoint is role-gated (none is).

### 0.3 Honesty crux (verbatim, for CLAUDE.md / README.md)

*This slice records enterprise administration over UAID's existing tenant model. It is not
go-live authority, not an RLS bypass for `uaid_app`, not a human signature, not closing
Slice 61, and not closing D-8/D-9/D-10. What the database enforces is that the runtime role
holds no INSERT or UPDATE on `autonomy_policies` at all, so its only policy-write path is a
SECURITY DEFINER function that refuses without an allowed, unspent, same-tenant admin action —
and which refuses a "tighten" that would relax the currently stored override map, including an
empty map; that the runtime role cannot record an allowed admin action without a real active
same-tenant role grant it has no privilege to create, and cannot record a lesser refusal while
a sufficient higher grant is active; and that a suspended tenant's or organization's bearer key
no longer resolves at the single HTTP→tenant boundary. What it does not enforce is that the
recorded principal is the authenticated one (app-stamped), that a role grant carries real
organizational authority (its provenance is an unverified operator admin session), that an
operator with DB-owner credentials is constrained — that actor can still write policies and
grants directly — that the §5/§2.6 matrix floor is checked in the database rather than in
Python, that cost budgets are role-gated, that suspension halts work already inside
`tenant_scope`, or that any read endpoint is role-gated — none is. A5 stays `slice54.v1`,
readiness stays `slice20.v1`, and `can_go_live_autonomously` remains the literal `False`.*

### 0.4 Allowed claims, verbatim

- "`uaid_app` holds no `INSERT` or `UPDATE` on `autonomy_policies`; the runtime role cannot
  write a policy at all except through `admin_write_autonomy_policy`
  (P-priv/autonomy_policies/INSERT, P-priv/autonomy_policies/UPDATE)."
- "`admin_write_autonomy_policy` refuses without an `allowed` (P-writer-requires-allowed-action),
  policy-kind (P-writer-requires-policy-kind), unspent (P-writer-requires-unspent-action)
  same-tenant admin action."
- "`tighten_autonomy_overrides` is monotonic against the **currently stored** override map: an
  empty map (P-tighten-relax-empty-map), a map that drops a disable
  (P-tighten-relax-drops-disable), one that lowers a `min_level`
  (P-tighten-relax-lowers-min-level), or one that moves the level
  (P-tighten-changes-level) is refused."
- "`uaid_app` has `SELECT` and no `INSERT`/`UPDATE`/`DELETE` on `admin_role_grants`; the
  runtime role cannot mint its own authorization (P-priv/admin_role_grants/*)."
- "An `admin_actions` row with `decision='allowed'` requires an active same-tenant grant of
  the recorded `actor_role` (P-allow-no-grant, P-allow-revoked-grant,
  P-allow-cross-tenant-grant), that role being the highest active grant held
  (P-allow-not-highest-grant), and rank ≥ the action's required rank
  (P-allow-insufficient-rank)."
- "`decision='refused_no_grant'` is refused when an active grant for that principal exists
  (P-refuse-mislabel), and `refused_insufficient_role` is refused when a sufficient higher
  grant is active (P-refuse-insufficient-with-higher-grant). The refusal ledger cannot
  understate the authority actually held."
- "An unauthenticated actor can only be recorded as `refused_unauthenticated_actor`
  (P-check-provenance-unauth-mislabel, P-check-provenance-verified-unauth)."
- "`required_role` is not caller-chosen: a generated CHECK binds it to `action_kind`
  (P-required-role-forged)."
- "The `admin_actions` authority is a BEFORE-INSERT trigger, not an RLS `WITH CHECK`, so it
  also binds the admin/owner role (P-allow-no-grant-as-admin)."
- "An `admin_policy_changes` row requires an `allowed` policy-kind action
  (P-change-refused-action), the real current autonomy level (P-change-level-mismatch), and an
  unspent authorization (P-change-action-reuse)."
- "A bearer key belonging to a `suspended` tenant does not resolve, and neither does one
  whose organization is `suspended` (P-suspend-tenant-blocks, P-suspend-org-blocks);
  reinstatement restores resolution (P-reinstate-restores)."
- "A `tenant_admin_events` row cannot claim a status the `tenants`/`organizations` row does
  not hold (P-event-lies), and a role event cannot name a principal or role its referenced
  grant does not carry (P-event-principal-mismatch, P-event-role-mismatch)."
- "The four new tables are tenant-owned with RLS ENABLE+FORCE; tenant A cannot read tenant
  B's rows on any of them (P-rls/*). Slice 63 grants `uaid_app` no cross-tenant reach
  (A-grant-matrix)."
- "Migration `0062` is additive apart from one privilege **narrowing**; head becomes `0062`;
  downgrade restores the `0026` resolver body byte-for-byte and restores the `0004`
  `autonomy_policies` grants (P-downgrade-resolver, A-downgrade-grants)."

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
  can insert grants and write `autonomy_policies` directly. The claim is scoped to the runtime
  role, and the `admin_actions` guard is a trigger specifically so the owner path is still
  checked for the *grant-existence* half.
- **That the §5/§2.6 matrix floor is enforced in the database.** It is not. The DB enforces
  monotonicity of a *tighten* against the stored map; the absolute floor (no override may drop
  below `MATRIX`, no §2.6 mandatory approval may be cleared) remains the frozen Python
  `validate_overrides`. Limitation: `matrix_floor_enforced_in_python_only`.
- **That `set_autonomy_policy` cannot relax anything.** A `tenant_admin` may lower a
  project-specific override back toward the matrix; that is the admin authority being
  administered, and it is gated, recorded, and audited — not prevented.
- **That cost budgets are role-gated.** `BudgetRepository.upsert` keeps its `uaid_app`
  privileges and is untouched (`cost_budget_writes_not_rbac_gated`).
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

## 1. Frozen files — byte-identical, SHA-256 verified on branch `feat/slice-63-enterprise-admin`

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
| `app/tenancy.py` | `cb7f9827bcf2c25fdd72ad29177e0f2fb6911b4ffbd7931ac1fe2cb939c2dbc1` |
| `app/identity.py` | `a76f99b85593e6d7ade9f71b6adb1a1ca81b3066436bb12ec9a04e7876897a09` |
| `app/audit.py` | `b44c45706c86ad4a55b45d81c43d9db0115e642267b2592c29d0649699c6c116` |
| `app/api/auth.py` | `86930b47f16f0a487518b2e232412ce61e7536d45bf963e7da7f7518d0fc76ab` |
| `app/api/dashboard.py` | `752c1bb4e96c6681f16ea4314a3835603d0bb19c19dfc1b49b2e6207762d8a81` |
| `app/repositories/api_keys.py` | `9dc80483746f0098efc65ead51267650404f9d315baa9f77706c66b836dcaeda` |
| `app/models/tenant_api_key.py` | `c3753ea4648ecf857f16798754b7fcb07f091d81573bc99a61c305b21862d321` |
| `app/models/tenant.py` | `d6b5cd28b139f1487eaa2d649ba443fe754964521635afd130d17f5a5a3594aa` |

**Seventeen** frozen files (v1 had eighteen).

### 1.1 Deliberately UN-FROZEN in v2, stated explicitly (defect 1)

Sol's defect 1 cannot be fixed without touching the Slice-3 write path, so v1's freeze of it
is lifted **on the record**:

| File | SHA-256 **before** Slice 63 | Why un-frozen | What may change |
|---|---|---|---|
| `app/repositories/autonomy_policies.py` | `9b563f6a8780da4a60cd1a57de377df6f3510a221d656564c115b89812288317` | Its `upsert` writes `autonomy_policies` via the ORM as `uaid_app`; after §OD-11's REVOKE that privilege is gone, so the method must route through `admin_write_autonomy_policy` or it is dead code that raises | **Only** `upsert` (signature gains a required `admin_action_id`, body calls the definer function). `decision_for`, `snapshot_decisions`, and every read stay behaviourally identical, and the `actor`-is-untrusted docstring stays |
| `scripts/bootstrap_rls_role.sql` | `7a611e198d1efff926646dcbfaebe95782e9de0d8ed3d2c20fd4c38bbccc9c61` | Needs the new NOLOGIN `policy_admin_writer` role | One additive idempotent `DO $$` block + one `ALTER ROLE`, in the `audit_writer` shape (`:41-48`). No change to `uaid_app`, `audit_writer`, or `api_key_resolver` |

**Builder duty:** publish the **post-change** SHA-256 of both files in the PR body and in the
`CLAUDE.md` close-out, next to the pre-change hashes above, so the diff surface of the
un-freeze is auditable without reading the diff. `app/policy/matrix.py` and
`app/policy/engine.py` stay frozen — `validate_overrides` is *called*, never edited.

`app/models/organization.py` (one additive `status` column, §3.5) and the twenty test files in
§OD-14 are the remaining pre-existing files Slice 63 edits. Do **not** `ruff format` the whole
tree.

---

## 2. Design decisions

### OD-1 — Role vocabulary: three ranked roles, no decorative entries

`app/admin/rbac.py`:

```
ADMIN_ROLES = ("tenant_viewer", "tenant_operator", "tenant_admin")
ROLE_RANKS  = {"tenant_viewer": 1, "tenant_operator": 2, "tenant_admin": 3}
```

Ranks are distinct, so "the highest active grant" is unique — no tie-break rule, which is what
makes the §OD-5 highest-grant rules well-defined. `tenant_viewer` is the deliberate **floor**:
a real grant that authorizes *no* action kind, which is what makes P-allow-insufficient-rank,
P-refuse-mislabel, and P-refuse-insufficient-with-higher-grant possible. It is not claimed to
gate reads.

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

Grounding: §5/§2.6 overrides are tighten-only, so an overrides-only change that leaves
`autonomy_level` untouched **and is monotonically at least as restrictive as what is stored**
is strictly safety-increasing, and is an *operator* action. Setting the level, or relaxing a
project's own extra tightening back toward the matrix, is an *admin* action.
**A single action kind would make "insufficient rank" untestable**; that is why there are two.

**v1 defect (Sol defect 2), accepted:** v1 asserted that `tighten_autonomy_overrides` was
"strictly safety-increasing" because `validate_overrides` is tighten-only. That was wrong.
`validate_overrides` validates each override *against the code MATRIX*, not against the stored
row, and the frozen `upsert` **replaces** the whole map. Sol's live probe is correct: both
`{"run_tests": {"allow": false}}` and `{}` validate, and applying `{}` re-enables `run_tests`.
Monotonicity is therefore enforced in the DB by §OD-12, against the current stored map — never
against a caller-supplied "previous" snapshot, which a caller could simply lie about.

`tighten_autonomy_overrides` on a project with no existing policy row is refused
(`no_existing_policy`) — there is no stored map to be monotonic against.

### OD-3 — Decision vocabulary: a total partition of the real grant state

```
DECISIONS = ("allowed",
             "refused_unauthenticated_actor",
             "refused_no_grant",
             "refused_insufficient_role")
```

Pure `evaluate_authorization(request, grants) -> AuthorizationDecision` (frozen dataclass,
`ruleset_version="slice63.v1"`), evaluated in this fixed order:

1. `actor_provenance != "request_authenticated"` ⇒ `refused_unauthenticated_actor`,
   `actor_role=None`. **This branch is unconditional and first**: an unauthenticated actor is
   never reported as `refused_no_grant`, even when it has no grant (defect 6).
2. no active grant for `(tenant, principal)` ⇒ `refused_no_grant`, `actor_role=None`.
3. otherwise let `held` = the **highest-rank** active grant. `rank(held) < rank(required)`
   ⇒ `refused_insufficient_role`, `actor_role=held`.
4. else ⇒ `allowed`, `actor_role=held`.

Unknown `action_kind` / `admin_role` / decision ⇒ raise, never default.

**The DB enforces the same partition, not a weaker one** (defect 6). §OD-5's trigger derives
the highest active grant itself and requires `actor_role` to *be* it, so the two properties
Sol found missing are DB-true: a `refused_insufficient_role` row cannot exist while a
sufficient higher grant is active (P-refuse-insufficient-with-higher-grant), and an `allowed`
row cannot understate the role held (P-allow-not-highest-grant). The provenance half is a
single biconditional CHECK (§3.2), so `refused_no_grant` with an unverified provenance is
impossible (P-check-provenance-unauth-mislabel).

### OD-4 — The unforgeable half is the grant row, and the privilege is the enforcement

`admin_role_grants` is tenant-owned with RLS ENABLE+FORCE and `tenant_isolation`, and
`uaid_app` is granted **`SELECT` only**. Minting and revoking are operator-path
(`ADMIN_DATABASE_URL`). This is the Slice-6 / 61a trust-zone pattern (a runtime-readable,
admin-written asset) applied to a *tenant-owned* table for the first time, so RLS still
scopes reads.

The root of trust is therefore the **operator DB credential**, stated openly in §0.3/§0.5.
Runtime delegation of grants is out of scope (`role_grant_delegation_not_implemented`).

### OD-5 — The `admin_actions` authority is a trigger, and it derives the highest grant itself

An RLS `WITH CHECK` would be bypassed by the table owner / a superuser operator, so a
forged `allowed` inserted by the admin session would commit. A `BEFORE INSERT` trigger
fires for **every** role. `admin_actions_guard()` is `SECURITY INVOKER` (default) and
inlines its grant lookups — filtered on `NEW.tenant_id`, so it is correct both under RLS
(runtime) and without it (owner). It computes, in one query over `admin_role_grants` where
`tenant_id=NEW.tenant_id AND principal_subject=NEW.actor_principal AND status='active'`:

- `v_n_active` — the count of active grants;
- `v_max_rank` — `MAX(<rank CASE over admin_role>)`, NULL when none;
- `v_has_role` — whether an active grant with `admin_role = NEW.actor_role` exists.

Then it asserts, with a distinct `RAISE` message per clause so a probe can match the reason:

| `NEW.decision` | required state | `RAISE` message on failure |
|---|---|---|
| `allowed` | `v_has_role` **and** `<rank(NEW.actor_role)> = v_max_rank` **and** `v_max_rank >= <rank(NEW.required_role)>` | `no_active_grant_for_recorded_role` / `actor_role_is_not_highest_active_grant` / `highest_active_grant_rank_below_required` |
| `refused_insufficient_role` | `v_has_role` **and** `<rank(NEW.actor_role)> = v_max_rank` **and** `v_max_rank < <rank(NEW.required_role)>` | `no_active_grant_for_recorded_role` / `actor_role_is_not_highest_active_grant` / `sufficient_active_grant_exists` |
| `refused_no_grant` | `v_n_active = 0` | `active_grant_exists_for_principal` |
| `refused_unauthenticated_actor` | *(exempt — the provenance CHECK owns it)* | — |

The rank CHECK constraints in §3.2 remain installed as an independent second layer; the
trigger and the CHECKs are probed separately (§5.0 rule 4).

**No standalone table-reading SQL helper is created.** An `admin_grant_active(uuid,text,text)`
function EXECUTE-able by `uaid_app` would be a grant-existence oracle; inlining avoids it.
Trigger functions do not require `EXECUTE` for the invoker when the trigger fires, so no new
function grant is needed for the guards. A-no-helper-fn asserts no Slice-63 **table-reading**
function is EXECUTE-able by `uaid_app`; the two functions `uaid_app` may execute are
`admin_write_autonomy_policy` (which is the gate itself, §OD-11) and the pure
`admin_overrides_is_monotonic` (which reads no table).

### OD-6 — Rank arithmetic lives in the DB as generated SQL text, not a Python enum

`app/admin/db_checks.py` generates **inline SQL `CASE` expressions** from `ROLE_RANKS` /
`ACTION_REQUIRED_ROLE` and exports them as named CHECK-constraint strings **and** as the rank
snippets interpolated into the §OD-5 guard body, consumed by the ORM `__table_args__`,
`app/admin/guards_sql.py`, and migration `0062` (the `catalog_db_checks` /
`learning_db_checks` pattern). No `IMMUTABLE` rank function is introduced, so there is no
CHECK-time function-permission question and no drift surface beyond the text itself.
A-check-drift asserts the installed `pg_get_constraintdef` contains the Python-generated
expression for each named constraint, and that `pg_get_functiondef(admin_actions_guard)`
contains the generated rank snippet — if a builder edits `ROLE_RANKS` without re-running the
migration, that assertion fails.

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

### OD-11 — The policy write lock (defect 1): revoke, then one gated definer path

**Accepted defect.** v1 left `uaid_app` with `INSERT, UPDATE ON autonomy_policies`
(fact 0.1.8), so any SQL running as the runtime role could change a policy without an
`admin_actions` row, and both ledgers would simply not know. A ledger describing a bypassable
write is not "DB-enforced policy management". v2 takes Sol's preferred branch — the real DB
lock — because fact 0.1.9 shows **no product path breaks**.

1. `REVOKE INSERT, UPDATE ON public.autonomy_policies FROM uaid_app`. `SELECT` is untouched,
   so `decision_for` / `snapshot_decisions` / readiness / control-loop / broker reads are
   unaffected. `DELETE` was never granted (`0004`'s "NO DELETE"), so the runtime role now has
   **no write path at all** to the table.
2. New NOLOGIN role `policy_admin_writer` (bootstrap script, §Alembic), granted exactly what
   its one function needs and nothing more: `SELECT, INSERT, UPDATE ON
   public.autonomy_policies` (no DELETE) and `SELECT ON public.admin_actions,
   public.admin_policy_changes` (steps 2/5 below read them). It gets no grant on
   `admin_role_grants`, `tenant_admin_events`, `tenant_api_keys`, or anything else. Because
   the role is `NOBYPASSRLS` and not the owner of any of those tables, **every one of those
   reads is itself RLS-confined to the caller's tenant** — the GUC is transaction-local and
   `SECURITY DEFINER` does not change it — so the function cannot see, let alone spend,
   another tenant's admin action.
3. `CREATE FUNCTION public.admin_write_autonomy_policy(p_admin_action_id uuid,
   p_project_id uuid, p_autonomy_level smallint, p_overrides jsonb) RETURNS uuid`,
   `LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog` (all names
   `public.`-qualified, the `0026` discipline), `ALTER FUNCTION ... OWNER TO
   policy_admin_writer`, `REVOKE ALL ... FROM PUBLIC`, `GRANT EXECUTE ... TO uaid_app`.
   Body, fail-closed in order, each failure a distinct `RAISE` message:
   1. `v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid`;
      NULL ⇒ `RAISE 'tenant_guc_unset'`.
   2. load `admin_actions` by `id = p_admin_action_id AND tenant_id = v_tenant AND
      project_id = p_project_id`; missing ⇒ `no_such_admin_action`.
   3. `decision = 'allowed'` else `admin_action_not_allowed`.
   4. `action_kind IN ('set_autonomy_policy','tighten_autonomy_overrides')` else
      `admin_action_not_policy_kind`.
   5. no `admin_policy_changes` row references it, else `admin_action_already_spent`.
   6. `SELECT ... FOR UPDATE` the current `autonomy_policies` row for
      `(v_tenant, p_project_id)`.
   7. `action_kind='tighten_autonomy_overrides'` ⇒ the row must exist
      (`no_existing_policy`), `p_autonomy_level` must equal the stored level
      (`tighten_may_not_change_level`), and
      `public.admin_overrides_is_monotonic(stored, p_overrides)` must be true
      (`tighten_would_relax_overrides`) — §OD-12.
   8. `INSERT ... ON CONFLICT (tenant_id, project_id) DO UPDATE SET autonomy_level,
      overrides, updated_at = now() RETURNING id`.
4. **RLS still applies inside the definer function.** `policy_admin_writer` is neither the
   owner of `autonomy_policies` nor `BYPASSRLS`, the table is `FORCE ROW LEVEL SECURITY`, and
   `0004`'s `tenant_isolation` policy has no `TO` clause (so it applies to that role too).
   The GUC is transaction-local and unaffected by `SECURITY DEFINER`, so the write is confined
   to the caller's tenant with no policy change. The composite FK
   `(project_id, tenant_id) → projects` on `admin_actions` is the second half.
5. The function is the **only** writer. `AutonomyPolicyRepository.upsert` (un-frozen, §1.1)
   gains a required `admin_action_id` and calls it; `app/admin/policy_admin.py` is the only
   caller that mints the action. A caller cannot express an ungated write.

**What this does not lock:** an operator with DB-owner credentials still writes the table
directly (§0.5), and the matrix floor stays in Python (§0.2). Both are named, not claimed.

### OD-12 — Monotonic tighten, compared against the stored row (defect 2)

`public.admin_overrides_is_monotonic(p_old jsonb, p_new jsonb) RETURNS boolean`,
`LANGUAGE sql IMMUTABLE`, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE TO policy_admin_writer`
(it reads no table, so it is not an oracle; §OD-5). True iff **every restriction present in
`p_old` survives in `p_new`** — the override lattice of the frozen
`app/policy/matrix.py:76-112`, where a raised `min_level`, `requires_approval: true`, and
`allow: false` are the three tightening axes:

```sql
SELECT NOT EXISTS (
  SELECT 1
  FROM jsonb_each(COALESCE(p_old, '{}'::jsonb)) AS o(action, ov)
  WHERE
       NOT (COALESCE(p_new, '{}'::jsonb) ? o.action)
    OR (ov ? 'allow'
        AND (p_new -> o.action -> 'allow') IS DISTINCT FROM to_jsonb(false))
    OR (ov ? 'requires_approval'
        AND (p_new -> o.action -> 'requires_approval') IS DISTINCT FROM to_jsonb(true))
    OR (ov ? 'min_level'
        AND (   NOT (p_new -> o.action ? 'min_level')
             OR (p_new -> o.action ->> 'min_level')::int < (ov ->> 'min_level')::int))
)
```

Consequences, all probed: dropping an action key relaxes ⇒ refused, so `{}` against a
non-empty stored map is refused (P-tighten-relax-empty-map); dropping `allow: false` while
keeping the key is refused (P-tighten-relax-drops-disable); lowering `min_level` is refused
(P-tighten-relax-lowers-min-level); **adding** a restriction is allowed, and `{} → {}` is
allowed. The comparison is against the row read `FOR UPDATE` in step 6 — never against a
caller-supplied "previous" map, which a caller could fabricate. A non-integer stored
`min_level` makes the `::int` cast raise, which refuses the write; that is fail-closed and is
recorded as the honest edge `malformed_stored_override_refuses_tighten`.

Monotonicity is **not** applied to `set_autonomy_policy` — see §0.5. Relaxing a project's own
extra tightening back toward the matrix is the `tenant_admin` authority being administered.

### OD-13 — Role events are FK-bound to the grant they name (defect 5)

**Accepted defect.** v1's `tenant_admin_events_guard()` checked the referenced grant's
*status* but never compared `subject_principal` / `admin_role` to that grant, so a
`role_granted` event could name any principal or role. v2 makes the binding a **foreign key**,
not a trigger comparison, so it holds for every writer including the owner:

- `admin_role_grants` gains `UNIQUE (id, tenant_id, principal_subject, admin_role)` named
  `uq_admin_role_grants_identity` (a new UNIQUE on a **new** table).
- `tenant_admin_events` carries the composite FK
  `(admin_role_grant_id, tenant_id, subject_principal, admin_role) →
  admin_role_grants(id, tenant_id, principal_subject, admin_role)` named
  `fk_tae_grant_identity`, replacing v1's `(admin_role_grant_id, tenant_id)` FK.
- MATCH SIMPLE means the FK is not enforced when any of the four columns is NULL, which is
  exactly right for the four non-role lifecycle kinds; `ck_tae_role_shape` forces all-four-or-
  none, so a role event can never slip through with a NULL.

The guard keeps the orthogonal status clause (`role_granted` ⇒ the grant is `active`;
`role_revoked` ⇒ `revoked`), which the FK cannot express.

### OD-14 — The named break of §OD-11, and its remedy

**The break.** After the REVOKE and the required `admin_action_id`, the 32 test call sites of
`AutonomyPolicyRepository.upsert` (fact 0.1.10) stop working: the `tenant_scope` sites lose the
privilege, and the `db_session` sites lose the signature. Named files (20):
`tests/test_policy.py`, `test_tools.py`, `test_pm_issues.py`, `test_ops_incidents_db.py`,
`test_readiness.py`, `test_factory.py`, `test_control_loop.py`, `test_secrets_verification.py`,
`test_rollback_verifications.py`, `test_qualification.py`, `test_production_autonomy.py`,
`test_pr_evidence.py`, `test_ops_incidents_catalog.py`, `test_ops_hotfix_db.py`,
`test_monitoring_evidence.py`, `test_emergency_controls.py`, `test_deploy_evidence.py`,
`test_ci_evidence.py`, `tests/ops_stabilization_support.py`, `tests/ops_hotfix_support.py`.

**The remedy — wrap the callers through the new path, do not weaken it.**
`tests/admin_support.py` gains one helper:

```
async def seed_gated_policy(*, session, ctx, project_id, autonomy_level,
                            overrides=None, session_is_admin=False,
                            principal="test:tenant_admin") -> PolicyChangeResult
```

which (a) ensures an **active `tenant_admin` grant** for `principal` in `ctx.tenant_id` —
committed via its own short-lived admin engine built from `TEST_ADMIN_URL` when
`session_is_admin=False`, or inserted on the caller's own session when `session_is_admin=True`
(fact 0.1.11: `db_session` is the admin connection inside one rolled-back transaction, so a
second connection could not see its uncommitted tenant); then (b) calls the **production**
`app/admin/policy_admin.apply_policy_change(...)` with a `TenantContext` carrying an
`AuthenticatedActor` whose `principal_subject == principal`; then (c) asserts the returned
decision is `allowed`. Call sites become a one-line substitution.

The helper must not have a bypass branch, and A-helper-uses-production-path asserts
`tests/admin_support.py` contains no direct `autonomy_policies` INSERT/UPDATE and no call to
`admin_write_autonomy_policy` other than through `apply_policy_change`.

**Ordering rule this exposes:** `apply_policy_change` calls the frozen
`validate_overrides` **before** recording anything. A malformed or matrix-relaxing override map
is a bad *request*, not an authorization decision: it raises `PolicyOverrideError` and writes
**no** `admin_actions` row (so `tests/test_policy.py:234`'s relaxing-override expectation still
holds and leaves no ledger residue). An authorization refusal, by contrast, always records a
refusal row.

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
- `UNIQUE (id, tenant_id, principal_subject, admin_role)` named
  **`uq_admin_role_grants_identity`** — the §OD-13 FK target.
- Grants: `GRANT SELECT ON public.admin_role_grants TO uaid_app` — **no INSERT/UPDATE/DELETE.**
- Guard trigger `admin_role_grants_guard` (function `admin_role_grants_guard()`), BEFORE
  INSERT OR UPDATE: INSERT ⇒ `status='active'`; UPDATE ⇒ only `status` and `updated_at` may
  change, and only `active→revoked` (one-way).
- Append-only pair, **DELETE and TRUNCATE only** — UPDATE is legal on this table, so no
  BEFORE-UPDATE block is installed (that would contradict revoke):
  `admin_role_grants_no_delete` (BEFORE DELETE, FOR EACH ROW) and
  `admin_role_grants_no_truncate` (BEFORE TRUNCATE, FOR EACH STATEMENT), both over
  `admin_role_grants_block_dml()`, in the shape of
  `app/ecosystem/learning_ddl.py:198-212`.

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
- Generated CHECKs (OD-6), each individually named so a probe can target it, and each with a
  named refusal probe in §5.2 (defect 3):
  - `ck_admin_actions_required_role_bound`:
    `required_role = CASE action_kind WHEN 'set_autonomy_policy' THEN 'tenant_admin'
     WHEN 'tighten_autonomy_overrides' THEN 'tenant_operator' END`
    → P-required-role-forged
  - `ck_admin_actions_allowed_rank`: `decision <> 'allowed' OR
     (<rank(actor_role)> >= <rank(required_role)>)`
    → P-allow-insufficient-rank
  - `ck_admin_actions_insufficient_rank`: `decision <> 'refused_insufficient_role' OR
     (<rank(actor_role)> < <rank(required_role)>)`
    → **P-check-insufficient-rank** (new in v2)
  - `ck_admin_actions_role_presence`: `(actor_role IS NOT NULL) =
     (decision IN ('allowed','refused_insufficient_role'))` — a biconditional, so the two
    rank CHECKs can never be vacuous on a NULL `actor_role`
    → **P-check-role-presence** (new in v2)
  - `ck_admin_actions_provenance_partition`:
    `(actor_provenance = 'caller_supplied_unverified') =
     (decision = 'refused_unauthenticated_actor')` — **replaces** v1's two weaker CHECKs
    (`ck_admin_actions_allowed_authenticated`, `ck_admin_actions_unauth_shape`) and closes
    defect 6's second half: `refused_no_grant` and `refused_insufficient_role` now also
    require `request_authenticated`
    → **P-check-provenance-unauth-mislabel** + **P-check-provenance-verified-unauth** (new)
- Guard trigger `admin_actions_guard` (function `admin_actions_guard()`) per §OD-5 — the
  grant-existence **and** highest-grant authority.
- Append-only: `admin_actions_no_update_delete` (BEFORE UPDATE OR DELETE, FOR EACH ROW) +
  `admin_actions_no_truncate` (BEFORE TRUNCATE, FOR EACH STATEMENT) over
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
- `UNIQUE (admin_action_id)` named **`uq_admin_policy_changes_action`** — one authorization is
  spent exactly once, and the same constraint is what §OD-11 step 3.5 reads.
- Guard trigger `admin_policy_changes_guard` (function `admin_policy_changes_guard()`)
  BEFORE INSERT:
  - the referenced `admin_actions` row has `decision='allowed'` and
    `action_kind IN ADMIN_ACTION_KINDS`;
  - `NEW.new_autonomy_level` equals the referenced `autonomy_policies.autonomy_level`;
  - `action_kind='tighten_autonomy_overrides'` ⇒
    `previous_autonomy_level = new_autonomy_level` (level untouched, §OD-2).
- Append-only: `admin_policy_changes_no_update_delete` + `admin_policy_changes_no_truncate`
  over `admin_policy_changes_block_dml()`; grant `SELECT, INSERT`.

### 3.4 `tenant_admin_events` — tenant-owned, append-only; `uaid_app` **SELECT only**

`id`, `tenant_id`, `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE
RESTRICT`,
`event_kind TEXT CHECK IN ('tenant_suspended','tenant_reinstated','organization_suspended',
'organization_reinstated','role_granted','role_revoked')`,
`subject_principal TEXT NULL` (≤255, non-blank when present),
`admin_role TEXT NULL CHECK (admin_role IS NULL OR admin_role IN ADMIN_ROLES)`,
`admin_role_grant_id UUID NULL`,
`performed_by TEXT` (≤200, non-blank),
`performed_by_provenance TEXT CHECK (= 'operator_admin_session_unverified')`, `created_at`.

- Composite FK `fk_tae_grant_identity` per §OD-13:
  `(admin_role_grant_id, tenant_id, subject_principal, admin_role) →
  admin_role_grants(id, tenant_id, principal_subject, admin_role)`.
- CHECK `ck_tae_role_shape`: `(event_kind IN ('role_granted','role_revoked')) =
  (subject_principal IS NOT NULL AND admin_role IS NOT NULL AND
  admin_role_grant_id IS NOT NULL)` → **P-check-tae-role-shape** (new in v2, defect 3).
- Guard trigger `tenant_admin_events_guard` (function `tenant_admin_events_guard()`)
  BEFORE INSERT — the ledger cannot lie about state the FK cannot express:
  - `tenant_suspended` ⇒ `tenants.status='suspended'` for `NEW.tenant_id`;
    `tenant_reinstated` ⇒ `'active'`;
  - `organization_suspended` ⇒ `organizations.status='suspended'` for
    `NEW.organization_id`; `organization_reinstated` ⇒ `'active'`;
  - every kind ⇒ the tenant's `organization_id` equals `NEW.organization_id`;
  - `role_granted` ⇒ the referenced grant row is `status='active'`; `role_revoked` ⇒
    `'revoked'`.
- Grants: `GRANT SELECT ... TO uaid_app` only. Append-only:
  `tenant_admin_events_no_update_delete` + `tenant_admin_events_no_truncate` over
  `tenant_admin_events_block_dml()`.

### 3.5 Additive changes to existing objects

1. `organizations.status TEXT NOT NULL DEFAULT 'active'` + CHECK
   `status IN ('active','suspended')`. Existing rows become `'active'`.
   `app/models/organization.py` gains the mapped column. No grant change (`uaid_app` already
   has SELECT).
2. `resolve_tenant_api_key(text)` DROP + recreate per §OD-7; `GRANT SELECT ON public.tenants,
   public.organizations TO api_key_resolver`.
3. `GRANT EXECUTE ON FUNCTION public.audit_append(text,text,text,jsonb) TO CURRENT_USER`
   (§OD-8).
4. **The policy write lock (§OD-11):** assert `policy_admin_writer` exists (fail closed
   naming `make db-bootstrap-rls-role`); `REVOKE INSERT, UPDATE ON public.autonomy_policies
   FROM uaid_app`; `GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO
   policy_admin_writer` and `GRANT SELECT ON public.admin_actions,
   public.admin_policy_changes TO policy_admin_writer` (after those tables are created, so
   this step runs last); create `admin_overrides_is_monotonic` and
   `admin_write_autonomy_policy` with their owner/revoke/grant matrix.

Nothing else is altered. `tenants`, `tenant_api_keys`, `projects`, `audit_logs`, and
`autonomy_policies`' columns, constraints, triggers, RLS policy, and `SELECT` grant are
untouched — only the two `uaid_app` write privileges on `autonomy_policies` are removed.

### 3.6 Downgrade

`downgrade()` order: (a) fail closed via `populated_downgrade_sql()` if **any** of the four
new tables has a row; (b) restore the `0026` resolver body byte-for-byte (owner/grants
restored) and `REVOKE SELECT ON public.tenants, public.organizations FROM api_key_resolver`;
(c) `REVOKE EXECUTE ON FUNCTION public.audit_append(...) FROM CURRENT_USER`; (d) drop
`admin_write_autonomy_policy` and `admin_overrides_is_monotonic`, `REVOKE SELECT, INSERT,
UPDATE ON public.autonomy_policies FROM policy_admin_writer`, `REVOKE SELECT ON
public.admin_actions, public.admin_policy_changes FROM policy_admin_writer`, and **restore
`GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO uaid_app`** (the `0004` state,
asserted by A-downgrade-grants); (e) drop the guards/triggers; (f) drop the four tables
(children first);
(g) drop `organizations.status`. Empty-database `0062 → 0061 → 0062` must succeed. The role
`policy_admin_writer` is **not** dropped (bootstrap-owned, like `audit_writer`).

---

## 4. Python modules (new unless noted; all ≤500 lines)

| Path | Responsibility |
|---|---|
| `app/admin/__init__.py` | package marker |
| `app/admin/rbac.py` | pure: `ADMIN_ROLES`, `ROLE_RANKS`, `ADMIN_ACTION_KINDS`, `ACTION_REQUIRED_ROLE`, `DECISIONS`, `RULESET_VERSION`, bounds, validators, frozen `AdminActionRequest` / `RoleGrantView` / `AuthorizationDecision`, pure `evaluate_authorization` (§OD-3, highest-grant-wins) |
| `app/admin/db_checks.py` | the named CHECK strings + the generated rank / required-role `CASE` snippets (§OD-6); consumed by the ORM, `guards_sql.py`, **and** the migration |
| `app/admin/guards_sql.py` | the four `plpgsql` guard bodies, the four `_block_dml` bodies, and the two §OD-11/§OD-12 function bodies as strings |
| `app/admin/ddl.py` | `install_admin_guards()` / `drop_admin_guards()` / `populated_downgrade_sql()` / resolver replace + restore / **policy-lock grant matrix** / grant matrix |
| `app/admin/tenant_admin.py` | **operator path** (admin session): `suspend_tenant`, `reinstate_tenant`, `suspend_organization`, `reinstate_organization`, `grant_admin_role`, `revoke_admin_role` — each sets the tenant GUC, writes the row + `tenant_admin_events`, and calls `audit_append` (§OD-8/§OD-9) |
| `app/admin/policy_admin.py` | **runtime service**: `apply_policy_change(...) -> PolicyChangeResult`; owns `tenant_scope`, calls frozen `validate_overrides` first (§OD-14), loads grants, pure-evaluates, records `admin_actions` (allowed **and** refused), on allowed calls `AutonomyPolicyRepository.upsert(admin_action_id=…)` then writes `admin_policy_changes`, audits both |
| `app/models/admin_rbac.py` | `AdminRoleGrant`, `AdminAction` |
| `app/models/admin_policy.py` | `AdminPolicyChange`, `TenantAdminEvent` |
| `app/repositories/admin.py` | `AdminGrantRepository` (tenant read), `AdminActionRepository` (insert + reads), `AdminPolicyChangeRepository` |
| `scripts/admin_roles.py` | operator CLI, argparse subcommands `grant`, `revoke`, `suspend-tenant`, `reinstate-tenant`, `suspend-org`, `reinstate-org`; prints ids/status only, never a key or an override value; uses `ADMIN_DATABASE_URL` |
| `migrations/versions/0062_enterprise_admin.py` | additive + the one §OD-11 narrowing; imports the CHECK strings and DDL helpers (the `0061` import pattern) |

**Edited (not new):** `app/repositories/autonomy_policies.py` (`upsert` only, §1.1),
`scripts/bootstrap_rls_role.sql` (`policy_admin_writer`, §1.1),
`app/models/organization.py` (`status`), and the twenty test files of §OD-14.

Tests (new): `tests/test_admin_rbac.py` (pure), `tests/test_admin_rbac_db.py`,
`tests/test_admin_policy_db.py`, `tests/test_admin_policy_lock_db.py` (§OD-11/§OD-12 probes),
`tests/test_admin_tenant_db.py`, `tests/test_admin_checks.py`,
`tests/test_admin_migrate.py`, plus `tests/admin_support.py` (shared seeding: org + two
tenants + projects + keys + grants, and `seed_gated_policy`, §OD-14).

`policy_admin.apply_policy_change` refuses **before** touching the policy: on any
non-`allowed` decision it records the refusal action + audit and returns without calling
`upsert`. Insert order inside one transaction: `admin_actions` →
`upsert(admin_action_id=…)` → `admin_policy_changes`.

No `Makefile` target is added; the operator CLI is invoked as
`uv run python -m scripts.admin_roles <subcommand> …`. `make migrate` /
`test-db-migrate` stay schema-only: a freshly migrated database has **zero** grants, so no
runtime admin action can be `allowed` and no runtime policy write can succeed until an
operator grants a role.

---

## 5. Probes

### 5.0 The owner test standard (applies to every probe in §5.2)

Sol's Slice-62 finding is carried forward, and v2 adds rules 4–6 to close defect 4.

1. **The mutation must actually be able to commit if the guard were absent.** Each refusal
   probe pairs with an explicit mutation — `ALTER TABLE … DISABLE TRIGGER <exact name>`,
   `ALTER TABLE … DROP CONSTRAINT <exact name>`, `GRANT <exact privilege>`,
   `ALTER TABLE … DISABLE ROW LEVEL SECURITY`, or `CREATE OR REPLACE FUNCTION` with the one
   clause removed — then re-run the *same* statement, assert it **commits**, then restore and
   re-assert the denial (`tgenabled='O'`, the constraint/grant/policy back, the original
   function body back). A mutation that cannot commit proves nothing and is a REJECT.
2. **It must fail for the guard's own reason, not a neighbouring constraint.** Every probe
   payload is otherwise fully valid, and the assertion matches on the guard's own error —
   the `pg_constraint` name for CHECK/UNIQUE/FK violations, the SQLSTATE `42501` plus the
   table name for privilege denials, or the guard's own `RAISE` message text for trigger and
   function violations. A bare "some IntegrityError" is a REJECT.
3. **The denial must be proven on the exact object the guard protects.** Table, and
   trigger/constraint/function/policy name, are asserted. Privilege denials are proven by
   attempting the statement **as `uaid_app` through `rls_engine`** — never as the admin role.
   Any forgery probe run as admin outside the §9 exception list is a REJECT.
4. **Layered guards are probed one layer at a time, and the plan says which layer.** Where a
   BEFORE-INSERT trigger fires before the CHECK under test (Postgres evaluates BEFORE ROW
   triggers first) or a privilege denial precedes a trigger, the probe **disables the outer
   layer in setup**, states in its docstring that it is doing so and why, asserts the inner
   guard's own name/message, and uses dropping the **inner** guard as its mutation. Setup and
   mutation are never the same object.
5. **Privilege probes are per privilege.** One probe per (table, privilege) pair, and the
   mutation grants **that** privilege — never `INSERT` standing in for `UPDATE`/`DELETE`. When
   a second guard would also refuse the mutated statement (e.g. an append-only trigger after
   an `UPDATE` grant), the mutation is `GRANT <priv>` **plus** disabling that named trigger,
   and the probe asserts the *unmutated* failure was `42501` so the privilege is proven to be
   the outer layer.
6. **Matrix probes enumerate every object.** Append-only, RLS, and privilege families are
   parametrized with one named case per (table, statement) or (table, privilege) pair, and
   each case's mutation targets **that** table's **that**-statement trigger / that table's
   RLS / that exact grant. One UPDATE trigger may not stand in for nine assertions.

Global: use `DISABLE TRIGGER` / `DROP CONSTRAINT` / `DISABLE ROW LEVEL SECURITY` /
`CREATE OR REPLACE FUNCTION` on the **named** object only; never
`SET CONSTRAINTS ALL DEFERRED`, never a session-wide `session_replication_role`, and always
restore in a `finally`. `TRUNCATE` cases run inside a transaction that is rolled back.

### 5.1 Pure probes

- **P-1** `ADMIN_ROLES` is exactly the three §OD-1 names; `ROLE_RANKS` values are
  `{1,2,3}` and distinct; `ADMIN_ACTION_KINDS` and `ACTION_REQUIRED_ROLE` match §OD-2
  key-for-key; `DECISIONS` is exactly the four §OD-3 values; `RULESET_VERSION == "slice63.v1"`.
- **P-2** `evaluate_authorization` decision table: (a) unverified provenance ⇒
  `refused_unauthenticated_actor` even with a `tenant_admin` grant present (order matters);
  (b) unverified provenance **and no grant** ⇒ still `refused_unauthenticated_actor`, never
  `refused_no_grant` (defect 6); (c) no grants ⇒ `refused_no_grant`, `actor_role is None`;
  (d) `tenant_viewer` only, `set_autonomy_policy` ⇒ `refused_insufficient_role`,
  `actor_role='tenant_viewer'`; (e) `tenant_operator`, `tighten_autonomy_overrides` ⇒
  `allowed`; (f) `tenant_operator`, `set_autonomy_policy` ⇒ `refused_insufficient_role`;
  (g) `{tenant_viewer, tenant_admin}` both active ⇒ `allowed` with `actor_role='tenant_admin'`
  (highest rank wins); (h) `{tenant_viewer, tenant_admin}` active with
  `tighten_autonomy_overrides` ⇒ `allowed` with `actor_role='tenant_admin'` — the pure
  function never records a lower role than held, which is what keeps it in step with the
  §OD-5 trigger; (i) a `revoked` grant is not counted.
- **P-3** unknown `action_kind`, unknown `admin_role`, blank/oversized `actor_principal`
  ⇒ raise, never a default decision.
- **P-4** `app/admin/*.py` source contains no bearer-key, raw-key, override-**value**, or
  document/prompt parameter name; `inspect.signature` of every public function in
  `app.admin.rbac`, `tenant_admin`, `policy_admin` has no parameter named `content`,
  `document`, `prompt`, `body`, `raw_key`, `key_hash`, or `password`.
- **P-5** the seventeen frozen hashes match §1 exactly, **and** `app/policy/matrix.py` +
  `app/policy/engine.py` are among them (the un-freeze of §1.1 did not leak into the matrix).
- **P-6** `A5_RULESET_VERSION == "slice54.v1"`; readiness `RULESET_VERSION == "slice20.v1"`;
  `can_go_live_autonomously is False` by identity.

### 5.2 Named refusal probes (each with its §5.0 mutation)

Unless stated, the statement under test is executed **as `uaid_app` inside `tenant_scope`**.

#### 5.2.a Policy write lock and monotonic tighten (defects 1 and 2)

| Probe | Guard under test | Refusal payload (otherwise fully valid) | Mutation that must commit |
|---|---|---|---|
| **P-priv/autonomy_policies/INSERT** | privilege: `uaid_app` has no INSERT on `autonomy_policies` | as `uaid_app`, a well-formed INSERT for its own tenant/project ⇒ `42501` naming `autonomy_policies` | `GRANT INSERT ON public.autonomy_policies TO uaid_app`; the same INSERT commits (RLS passes: the GUC is set); `REVOKE INSERT`, re-assert `42501` |
| **P-priv/autonomy_policies/UPDATE** | privilege: no UPDATE | as `uaid_app`, `UPDATE autonomy_policies SET autonomy_level=5` on its own admin-seeded row ⇒ `42501` | `GRANT UPDATE …`; the same UPDATE commits; `REVOKE UPDATE`, re-assert. No other guard exists on this table, so the grant alone is the whole mutation |
| **P-writer-requires-allowed-action** | `admin_write_autonomy_policy` step 3 | call the function with an `admin_actions` id whose `decision='refused_insufficient_role'` (same tenant + project, policy kind, unspent) ⇒ `RAISE 'admin_action_not_allowed'` | `CREATE OR REPLACE FUNCTION public.admin_write_autonomy_policy(...)` with **only** the `decision='allowed'` clause removed; the same call commits and the policy row changes; restore the original body from `guards_sql.py` and assert `pg_get_functiondef` matches |
| **P-writer-requires-policy-kind** | step 4 | an `allowed` action whose `action_kind` is set by admin to a non-policy value ⇒ `RAISE 'admin_action_not_policy_kind'`. Because `ck_admin_actions_*` bind the kinds, the setup writes the row as admin with the kind CHECK dropped for that statement only, and says so (§5.0 rule 4) | `CREATE OR REPLACE` with the kind clause removed; the same call commits; restore |
| **P-writer-requires-unspent-action** | step 5 | run one full allowed change, then call the function again with the **same** `admin_action_id` ⇒ `RAISE 'admin_action_already_spent'` | `CREATE OR REPLACE` with the spent-check removed; the second call commits; restore |
| **P-tighten-relax-empty-map** | §OD-12 monotonicity | stored `overrides = {"run_tests": {"allow": false}}` at level 2; an **allowed** `tighten_autonomy_overrides` action; call with `p_autonomy_level=2`, `p_overrides='{}'` ⇒ `RAISE 'tighten_would_relax_overrides'` | `CREATE OR REPLACE` with the monotonic clause removed; the same call commits and `overrides` becomes `{}` (Sol's exact re-enable case); restore and re-assert the refusal |
| **P-tighten-relax-drops-disable** | same | stored `{"run_tests": {"allow": false}}` → `{"run_tests": {"min_level": 3}}` (key kept, disable dropped) ⇒ same `RAISE` | same |
| **P-tighten-relax-lowers-min-level** | same | stored `{"deploy_staging": {"min_level": 4}}` → `{"deploy_staging": {"min_level": 3}}` ⇒ same `RAISE` | same |
| **P-tighten-changes-level** | §OD-11 step 7 | stored level 2; allowed tighten action; call with `p_autonomy_level=3` and a monotone map ⇒ `RAISE 'tighten_may_not_change_level'` | `CREATE OR REPLACE` with the level-equality clause removed; the same call commits; restore |

#### 5.2.b `admin_actions` authority — trigger layer (§OD-5, defect 6)

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-allow-no-grant** | `admin_actions_guard` | `allowed`, `set_autonomy_policy`, `actor_role='tenant_admin'`, `request_authenticated`, **no** grant ⇒ `RAISE 'no_active_grant_for_recorded_role'` | `ALTER TABLE public.admin_actions DISABLE TRIGGER admin_actions_guard`; same INSERT commits; restore, assert `tgenabled='O'` |
| **P-allow-no-grant-as-admin** | same guard binds the owner role | the identical INSERT on the **admin** session ⇒ same `RAISE` (proves the trigger-not-RLS choice) | same disable/restore, run as admin |
| **P-allow-revoked-grant** | same | grant exists but `status='revoked'`; rank would suffice ⇒ same `RAISE` | same |
| **P-allow-cross-tenant-grant** | same + §17.3 | principal holds an active `tenant_admin` grant in tenant **B**; INSERT `allowed` in tenant **A**'s scope ⇒ `RAISE`. The guard is what refuses; RLS is why it sees nothing | same disable/restore; with the guard off the row commits |
| **P-allow-not-highest-grant** | same, highest-grant clause | principal holds active `tenant_operator` **and** `tenant_admin`; INSERT `allowed` for `tighten_autonomy_overrides` with `actor_role='tenant_operator'` (all CHECKs pass: rank 2 ≥ 2) ⇒ `RAISE 'actor_role_is_not_highest_active_grant'` | same disable/restore |
| **P-refuse-insufficient-with-higher-grant** | same, `sufficient_active_grant_exists` clause (defect 6) | principal holds active `tenant_viewer` **and** `tenant_admin`; INSERT `refused_insufficient_role` for `set_autonomy_policy` with `actor_role='tenant_viewer'` (rank 1 < 3, so `ck_admin_actions_insufficient_rank` and `ck_admin_actions_role_presence` both pass) ⇒ `RAISE 'actor_role_is_not_highest_active_grant'`; the sibling case with `actor_role='tenant_admin'`, `required_role='tenant_admin'` reaches `sufficient_active_grant_exists` with the rank CHECK dropped in setup (§5.0 rule 4) | same disable/restore for both cases |
| **P-refuse-mislabel** | same, `active_grant_exists_for_principal` clause | an active `tenant_viewer` grant exists; INSERT `refused_no_grant`, `actor_role=NULL`, `request_authenticated` (so both the presence and provenance CHECKs pass) ⇒ `RAISE` | same disable/restore |

#### 5.2.c `admin_actions` authority — CHECK layer (defect 3)

Each case's payload satisfies every neighbouring CHECK; where the §OD-5 trigger would fire
first it is disabled **in setup** per §5.0 rule 4, and the assertion matches the constraint
name so it cannot be a neighbour.

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-allow-insufficient-rank** | `ck_admin_actions_allowed_rank` | active `tenant_operator` grant (trigger passes on the role-exists clause); `allowed` for `set_autonomy_policy` with `actor_role='tenant_operator'` ⇒ violation names `ck_admin_actions_allowed_rank`. Trigger disabled in setup (its `highest_active_grant_rank_below_required` clause would mask the CHECK) | `DROP CONSTRAINT ck_admin_actions_allowed_rank`; the same INSERT commits; re-add from `db_checks.py` |
| **P-check-insufficient-rank** | `ck_admin_actions_insufficient_rank` | `refused_insufficient_role` with `actor_role='tenant_admin'` (rank 3) and `required_role='tenant_operator'` (rank 2) — a refusal claiming insufficiency while recording a sufficient role ⇒ violation names the constraint. Trigger disabled in setup | `DROP CONSTRAINT ck_admin_actions_insufficient_rank`; same INSERT commits; re-add |
| **P-check-role-presence** | `ck_admin_actions_role_presence` | `refused_no_grant` with `actor_role='tenant_admin'` where the role must be NULL; no grant seeded, so the trigger's own clause passes and **no trigger disable is needed** ⇒ violation names the constraint. Sibling case: `allowed` with `actor_role=NULL` (trigger disabled in setup) ⇒ same constraint | `DROP CONSTRAINT ck_admin_actions_role_presence`; same INSERT commits — and for the sibling, assert it then fails on `ck_admin_actions_allowed_rank` or the guard, never silently, proving the trio is not under-constrained; re-add |
| **P-check-provenance-unauth-mislabel** | `ck_admin_actions_provenance_partition` (defect 6) | `refused_no_grant` with `actor_provenance='caller_supplied_unverified'`, `actor_role=NULL`, no grant (trigger clause passes) ⇒ violation names the constraint. This is the DB proof that an unauthenticated actor cannot be filed as "no grant" | `DROP CONSTRAINT ck_admin_actions_provenance_partition`; same INSERT commits; re-add |
| **P-check-provenance-verified-unauth** | same constraint, other direction | `refused_unauthenticated_actor` with `actor_provenance='request_authenticated'`, `actor_role=NULL` ⇒ violation names the constraint | same drop/re-add |
| **P-required-role-forged** | `ck_admin_actions_required_role_bound` | `set_autonomy_policy` with `required_role='tenant_operator'`, `actor_role='tenant_operator'` + a matching active grant (so the trigger and both rank CHECKs pass) ⇒ violation names the constraint | drop/re-add that named constraint |

#### 5.2.d `admin_policy_changes` and `admin_role_grants` lifecycle

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-change-refused-action** | `admin_policy_changes_guard` | reference an `admin_actions` row with `decision='refused_insufficient_role'`; every FK/CHECK satisfied and `new_autonomy_level` equal to the real policy level ⇒ `RAISE` on the decision clause | `DISABLE TRIGGER admin_policy_changes_guard`; same INSERT commits; restore |
| **P-change-level-mismatch** | same | referenced action is `allowed`; the real level is 3; record `new_autonomy_level=2` (in range, so the 0–5 CHECK cannot mask it) ⇒ `RAISE` on the level clause | same |
| **P-change-tighten-level-moved** | same | `tighten_autonomy_overrides`, `previous_autonomy_level=2`, `new_autonomy_level=3` where the policy really holds 3 (level clause passes) ⇒ `RAISE` on the tighten clause | same |
| **P-change-action-reuse** | `uq_admin_policy_changes_action` | commit one valid change; INSERT a second row for the **same** `admin_action_id`, differing only in `id`, every guard clause satisfied ⇒ violation names `uq_admin_policy_changes_action` | `DROP CONSTRAINT uq_admin_policy_changes_action`; the second row commits; re-add |
| **P-grant-update-widen** | `admin_role_grants_guard` | as **admin**: UPDATE a revoked grant back to `status='active'` ⇒ `RAISE`; and UPDATE `admin_role` on an active grant ⇒ `RAISE` (two cases, one trigger) | `DISABLE TRIGGER admin_role_grants_guard`; each same UPDATE commits; restore |

#### 5.2.e `tenant_admin_events` fidelity (defect 5)

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-event-principal-mismatch** | FK `fk_tae_grant_identity` (defect 5) | as **admin**, `role_granted` referencing a real active grant for principal `alice` but with `subject_principal='bob'`; `admin_role` matches, shape CHECK satisfied, guard's status clause satisfied ⇒ FK violation naming `fk_tae_grant_identity` | `ALTER TABLE public.tenant_admin_events DROP CONSTRAINT fk_tae_grant_identity`; the same INSERT commits (the lie is now recordable); re-add |
| **P-event-role-mismatch** | same FK | `role_granted` referencing a `tenant_admin` grant but with `admin_role='tenant_viewer'` ⇒ FK violation naming the same constraint | same drop/re-add |
| **P-check-tae-role-shape** | `ck_tae_role_shape` | `role_granted` with `subject_principal` and `admin_role_grant_id` set but `admin_role=NULL` — the FK is unenforced (MATCH SIMPLE, one NULL) and the guard's status clause passes, so only the shape CHECK can fire ⇒ violation names it | `DROP CONSTRAINT ck_tae_role_shape`; the same INSERT commits; re-add |
| **P-event-lies** | `tenant_admin_events_guard` | tenant is `active`; as **admin**, INSERT `event_kind='tenant_suspended'` with the correct org id and valid shape ⇒ `RAISE`. Mirror case for `organization_suspended` while the org is `active` | `DISABLE TRIGGER tenant_admin_events_guard`; each same INSERT commits; restore |
| **P-event-wrong-org** | same guard | valid `role_granted` shape (FK satisfied) but `organization_id` set to a **second** organization that does not own the tenant ⇒ `RAISE` on the org clause (the org FK is satisfied — the org exists) | same |
| **P-event-role-grant-status** | same guard | `event_kind='role_revoked'` referencing a grant whose `status` is still `'active'`, with the identity FK satisfied ⇒ `RAISE` | same |

#### 5.2.f Privilege matrix — one case per (table, privilege), §5.0 rule 5

Family **P-priv/`<table>`/`<privilege>`**, all executed as `uaid_app` via `rls_engine`, each
asserting SQLSTATE `42501` naming that table, each mutation granting **that** privilege on
**that** table (plus, where noted, disabling the one named trigger that would otherwise mask
the commit), then re-running the identical statement, then `REVOKE` + re-assert:

| Case | Statement | Extra mutation needed to reach commit |
|---|---|---|
| `admin_role_grants/INSERT` | INSERT a well-formed active grant (throwaway principal, so the residue is inert — the table is DELETE-blocked by design and must not be cleaned up by DELETE) | none |
| `admin_role_grants/UPDATE` | UPDATE an admin-seeded active grant to `status='revoked'` (the direction the guard permits, so the guard cannot mask the grant) | none |
| `admin_role_grants/DELETE` | DELETE an admin-seeded grant | also `DISABLE TRIGGER admin_role_grants_no_delete` |
| `admin_actions/UPDATE` | UPDATE `decision` on an admin-seeded row | also `DISABLE TRIGGER admin_actions_no_update_delete` |
| `admin_actions/DELETE` | DELETE that row | also `DISABLE TRIGGER admin_actions_no_update_delete` |
| `admin_policy_changes/UPDATE` | UPDATE `new_autonomy_level` | also `DISABLE TRIGGER admin_policy_changes_no_update_delete` |
| `admin_policy_changes/DELETE` | DELETE the row | same |
| `tenant_admin_events/INSERT` | INSERT a lifecycle event (throwaway tenant, inert residue; append-only, no DELETE cleanup) | none |
| `tenant_admin_events/UPDATE` | UPDATE `event_kind` | also `DISABLE TRIGGER tenant_admin_events_no_update_delete` |
| `tenant_admin_events/DELETE` | DELETE the row | same |
| `autonomy_policies/INSERT` | see §5.2.a | none |
| `autonomy_policies/UPDATE` | see §5.2.a | none |

#### 5.2.g Append-only matrix — one case per (table, statement), §5.0 rule 6

Family **P-ao/`<table>`/`<statement>`**, 11 cases. Each runs **as admin** (stated in the
docstring: the runtime role has no privilege on these statements, so a `uaid_app` attempt
would prove the grant, not the trigger — the object under test here is the trigger), asserts
the named trigger's own `RAISE`, and mutates **that** table's **that**-statement trigger:

| Table | Statements | Trigger disabled by the mutation |
|---|---|---|
| `admin_role_grants` | DELETE, TRUNCATE | `admin_role_grants_no_delete`, `admin_role_grants_no_truncate` |
| `admin_actions` | UPDATE, DELETE, TRUNCATE | `admin_actions_no_update_delete` (UPDATE and DELETE cases each re-run their own statement), `admin_actions_no_truncate` |
| `admin_policy_changes` | UPDATE, DELETE, TRUNCATE | `admin_policy_changes_no_update_delete`, `admin_policy_changes_no_truncate` |
| `tenant_admin_events` | UPDATE, DELETE, TRUNCATE | `tenant_admin_events_no_update_delete`, `tenant_admin_events_no_truncate` |

`admin_role_grants` has no UPDATE case by design (§3.1: revoke is a legal UPDATE); its UPDATE
authority is probed by P-grant-update-widen instead.

#### 5.2.h RLS matrix — one case per table, §5.0 rule 6

Family **P-rls/`<table>`**, 4 cases. Admin seeds one row for tenant **B** on that table; as
`uaid_app` in tenant **A**'s scope, `SELECT` it ⇒ zero rows; for the two INSERT-able tables,
also attempt an INSERT with `tenant_id = B` ⇒ RLS `WITH CHECK` violation naming that table.
Mutation for each case: `ALTER TABLE public.<table> DISABLE ROW LEVEL SECURITY` — then the
cross-tenant SELECT returns B's row (and the INSERT commits) — then restore
`ENABLE` + `FORCE` and re-assert. Cases: `admin_role_grants`, `admin_actions`,
`admin_policy_changes`, `tenant_admin_events`.

#### 5.2.i Suspension and migration

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-suspend-tenant-blocks** | resolver body | issue a key (raw returned once), assert it resolves; as admin set `tenants.status='suspended'`; the **same raw key** now yields `resolve(...) is None`, **and** a real HTTP `GET /api/projects/{id}/runs` with that bearer returns **401** with the generic body | restore the `0026` resolver body (drop + create the old body) — the same key resolves again; reinstall the `0062` body and re-assert `None`. This proves the resolver clause, not a Python check |
| **P-suspend-org-blocks** | resolver body | tenant stays `active`; set `organizations.status='suspended'` ⇒ `resolve(...) is None` and HTTP 401 | same resolver mutation |
| **P-reinstate-restores** | resolver body | after either suspension, set status back to `'active'` ⇒ the same key resolves and the endpoint returns 200 (proves suspension is a live filter, not a one-way key kill) | n/a (positive control for the two above) |
| **P-downgrade-populated** | `populated_downgrade_sql()` | with one row in **each** of the four tables (four sub-cases, one per table, so the guard is proven on each object) `alembic downgrade 0061` fails closed with the guard's own message naming that table | in the same transaction, execute the downgrade's own DDL **without** the emptiness check (the guard-free equivalent: drop that table) and assert it succeeds, then `ROLLBACK` — proving the drop would have happened had the guard been absent |

### 5.3 Catalog / invariant assertions (not refusal probes)

These are assertions, not guards, and are labelled as such so they are never counted as
proven refusals. Where v1 claimed a probe that could only be mutated by monkeypatching a
copy, v2 demotes it here rather than pretending (defect 4).

- **A-grant-matrix** `information_schema.role_table_grants` for `uaid_app` is exactly:
  `admin_role_grants` → `{SELECT}`; `tenant_admin_events` → `{SELECT}`;
  `admin_actions` → `{SELECT, INSERT}`; `admin_policy_changes` → `{SELECT, INSERT}`;
  **`autonomy_policies` → `{SELECT}`** (no INSERT, no UPDATE — the §OD-11 lock, asserted at
  the catalog as well as behaviourally). No `UPDATE`, `DELETE`, `TRUNCATE`, or `REFERENCES`
  on any Slice-63 table. `PUBLIC` has none.
- **A-writer-role** `admin_write_autonomy_policy` is `prosecdef=true`, owned by
  `policy_admin_writer`; that role is `rolsuper=false rolbypassrls=false rolcanlogin=false`;
  `information_schema.routine_privileges` shows `EXECUTE` for `uaid_app` and none for PUBLIC;
  `policy_admin_writer` holds exactly `{SELECT, INSERT, UPDATE}` on `autonomy_policies`,
  `{SELECT}` on `admin_actions` and `admin_policy_changes`, and **nothing** on
  `admin_role_grants`, `tenant_admin_events`, or `tenant_api_keys`.
- **A-writer-guc** calling `admin_write_autonomy_policy` with no `app.current_tenant` set
  raises `tenant_guc_unset`. Recorded as an assertion, not a refusal probe: with the GUC
  unset, `autonomy_policies` RLS would refuse the write anyway, so no mutation of the GUC
  check alone can commit and it cannot meet §5.0 rule 1.
- **A-monotonic-table** a truth table over `SELECT public.admin_overrides_is_monotonic(a, b)`:
  `({}, {})` true; `({}, {"run_tests": {"allow": false}})` true (adding restriction);
  `({"run_tests": {"allow": false}}, {})` false; `(…{"allow": false}, …{"min_level": 3})`
  false; `(…{"min_level": 3}, …{"min_level": 4})` true;
  `(…{"min_level": 4}, …{"min_level": 3})` false;
  `(…{"requires_approval": true}, …{})` false.
- **A-rls-enabled** `pg_class.relrowsecurity` **and** `relforcerowsecurity` are true for all
  four new tables, and each has exactly one policy named `tenant_isolation` whose
  `pg_get_expr` text equals the `PREDICATE` string. `autonomy_policies` still has its
  `0004` policy, ENABLE, and FORCE unchanged.
- **A-check-drift** for each named constraint in §3.1–§3.4, `pg_get_constraintdef` contains
  the expression generated by `app/admin/db_checks.py`, and
  `pg_get_functiondef('admin_actions_guard')` contains the generated rank snippet (§OD-6).
  Editing `ROLE_RANKS` without a migration fails this.
- **A-no-helper-fn** no function created by `0062` **that reads a table** is EXECUTE-able by
  `uaid_app` except `admin_write_autonomy_policy`, which is the gate itself; the four trigger
  functions are invoked by triggers and granted to no one;
  `admin_overrides_is_monotonic` reads no table.
- **A-triggers-enabled** after the whole DB suite, every Slice-63 trigger has
  `tgenabled='O'`, every dropped constraint is back, `autonomy_policies` grants match
  A-grant-matrix, and `pg_get_functiondef` of both new functions equals the migration text
  (catches an unrestored mutation from §5.2.a).
- **A-downgrade-grants** after `alembic downgrade 0061` on an empty DB, `uaid_app` holds
  exactly `{SELECT, INSERT, UPDATE}` on `autonomy_policies` again (the `0004` state), both new
  functions are gone, and `policy_admin_writer` holds nothing on the table.
- **P-downgrade-resolver** (assertion, named for continuity) on an empty DB,
  `alembic downgrade 0061` then `pg_get_functiondef` for `resolve_tenant_api_key` is
  byte-identical to the `0026` body, `api_key_resolver` no longer has SELECT on
  `tenants`/`organizations`, and `organizations.status` is gone.
- **A-service-refusal-no-write** (demoted from v1's P-service-refusal-no-write) calling
  `apply_policy_change` for a principal with **no** grant leaves an `admin_actions` row with
  `decision='refused_no_grant'`, adds no `admin_policy_changes` row, and leaves the
  `autonomy_policies` row's `autonomy_level` / `overrides` / `updated_at` unchanged. This is
  an ordering assertion about the Python service, **not** a guard: the DB authority for the
  same property is P-writer-requires-allowed-action, which mutates the production function.
- **A-audit-chain** (demoted from v1's P-audit-chain) an allowed change and a refused attempt
  each append an `audit_logs` row with the §OD-9 action name and payload keys; `audit_verify()`
  returns `ok=true`; no payload value contains an override value, a key hash, or a raw key.
  Audit is coverage, not a guard; no mutation is claimed.
- **A-helper-uses-production-path** `tests/admin_support.py` contains no direct
  `autonomy_policies` INSERT/UPDATE and reaches the policy only via
  `policy_admin.apply_policy_change` (§OD-14).
- **A-suspend-no-oracle** a suspended-tenant key and a syntactically valid **unknown** key
  produce byte-identical 401 status, body, and headers.
- **A-head** `uv run alembic heads` → `0062`; exactly one head.
- **A-frozen-untouched** real `ProductionAutonomyRepository.evaluate` and
  `ReadinessRepository.evaluate` before and after a full admin flow (grant → allowed change →
  suspend → reinstate) are bit-equal on `a5_satisfied`, `can_go_live_autonomously`,
  `ruleset_version`, every gate `status`, and readiness `readiness_level` / `ruleset_version`.
  Not a pure-function tautology — both go through the repositories.
- **A-no-http-surface** the FastAPI route table is unchanged versus `main` (same paths and
  methods); `app/admin/**` imports no `fastapi` symbol.
- **A-suite-green** `make test` and `make test-db` both pass **after** the §OD-14 migration of
  all twenty test files; the builder reports both counts, and any test that had to change
  behaviour (rather than just its seeding call) is named individually in the PR body.

---

## 6. Documentation language, required

`CLAUDE.md` and `README.md` must:

- carry the §0.3 honesty crux **verbatim**;
- state Slice 63 adds org/tenant administration, DB-enforced RBAC, and a **real DB write lock**
  on `autonomy_policies` for the runtime role, and **closes no spec section**;
- name the limitations explicitly: `read_api_not_role_gated`,
  `suspension_not_enforced_inside_tenant_scope`, `role_grant_delegation_not_implemented`,
  `matrix_floor_enforced_in_python_only`, `cost_budget_writes_not_rbac_gated`,
  `malformed_stored_override_refuses_tighten`, and "an operator holding DB-owner credentials
  is not constrained by this RBAC — that actor can write policies and grants directly";
- record that `uaid_app` **lost** `INSERT`/`UPDATE` on `autonomy_policies`, that
  `AutonomyPolicyRepository.upsert` now requires an `admin_action_id`, and that
  `scripts/bootstrap_rls_role.sql` must be run before `0062` (it creates
  `policy_admin_writer`);
- publish the post-change SHA-256 of `app/repositories/autonomy_policies.py` and
  `scripts/bootstrap_rls_role.sql` next to the §1.1 pre-change hashes;
- state that the Slice 61 exit and D-8 / D-9 / D-10 stay **OPEN** (owner = Salim);
- state A5 `slice54.v1`, readiness `slice20.v1`, `can_go_live_autonomously` literal `False`;
- state that a freshly migrated database has zero role grants, so no runtime admin action
  can be `allowed` and no runtime policy write can succeed until an operator grants a role;
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
| DB-side enforcement of the §5/§2.6 matrix floor | Deferred (`matrix_floor_enforced_in_python_only`) — the DB enforces monotonicity against the stored map only |
| RBAC-gating cost budget writes | Deferred (`cost_budget_writes_not_rbac_gated`) |
| Role-gating the read API | Deferred (`read_api_not_role_gated`) |
| Runtime delegation of role grants | Deferred (`role_grant_delegation_not_implemented`) |
| Suspension enforcement inside `tenant_scope` / against running work | Deferred |
| Verified-human authority for a grant (a signer tier above `request_authenticated`) | Deferred |
| Constraining an operator with DB-owner credentials | Out of reach; stated, not claimed |
| HTTP admin API / admin UI | Deferred (§OD-10) |
| Per-project or per-resource ACLs, groups, SCIM/SSO, key rotation policy | Deferred |
| Platform-event audit of non-tenant-owned global writes | Deferred (Slice-6 precedent) |
| A5 / readiness / go-live movement | Forbidden |

---

## 8. Non-goals, restated

No change to the seventeen frozen files. No new HTTP route, tool, A1 action, connector, LLM
call, or credential type. No RLS bypass. **No new privilege for `uaid_app` anywhere** — it
gains `SELECT`/`INSERT` on the two ledgers and `SELECT` on the two admin-written tables, and
**loses** `INSERT`/`UPDATE` on `autonomy_policies`. No budget figures. No spec edit. No
softening of go-live or §2.6. No Slice 64.

---

## 9. Builder constraints

- TDD: land P-1…P-6, then the failing P-priv/autonomy_policies/INSERT and
  P-tighten-relax-empty-map (the two defect-1 / defect-2 proofs) before the feature code.
- Every guard in §3 and §OD-11/§OD-12/§OD-13 has a named probe in §5.2 and must satisfy all
  six §5.0 conditions. A probe whose mutation cannot commit is a defect, not a pass; if a
  guard genuinely cannot carry a load-bearing probe, demote it to §5.3 and say so — do not
  dress an assertion as a refusal.
- All forgery/privilege probes run as **`uaid_app`** via `rls_engine`, except those that must
  exercise the owner path because the runtime role has no privilege to reach the guard under
  test — each stating that reason in its docstring: **P-allow-no-grant-as-admin**,
  **P-grant-update-widen**, the whole **P-ao/\*** family (11 cases), **P-event-lies**,
  **P-event-wrong-org**, **P-event-role-grant-status**, **P-event-principal-mismatch**,
  **P-event-role-mismatch**, **P-check-tae-role-shape**, and the admin-side seeding halves of
  the **P-rls/\*** family. Any *other* probe run as admin is a defect.
- Restore every disabled trigger, dropped constraint, temporary grant, disabled RLS, and
  replaced function body in a `finally`, and let A-triggers-enabled catch a miss.
- The §OD-14 test migration touches twenty existing test files. Change **only** the policy
  seeding call at each site. If any test's *assertions* must change, name it in the PR body
  with the reason — a silently weakened assertion is a defect.
- Do not `ruff format` the whole tree. Line cap 500 per file — split rather than grow
  (`guards_sql.py` is pre-split from `ddl.py` for exactly this reason; if the two new function
  bodies push it over, split again into `app/admin/policy_sql.py`).
- `pyright` on the CI-owned paths **plus** every new Slice-63 module and test in §4, plus the
  two un-frozen files of §1.1; 0 errors on that set. Full-repo pyright remains out of scope
  (pre-existing errors).
- Conventional commits (`feat(admin):`, `test(admin):`, `feat(migrations):`,
  `refactor(policy):` for the un-frozen `upsert`). Do not commit `.env`.
  **Do not edit this plan.**
- Branch `feat/slice-63-enterprise-admin`. Do not open the PR before Sol's code APPROVE.

---

## 10. Change log

**v1.** First version. Grounded on `main` @ `4a89742` (Slice 62 merged via PR #114 plus
close-out PR #115; live Alembic head `0061`; no `app/admin/` package). Carried forward the
owner test standard from Sol's Slice-62 code REJECT: mutation-must-commit, own-reason, and
exact-object for every guard (§5.0).

**v2.** Sol REJECT #1 accepted in full; head re-verified `0061`. Six defects, none argued
down:

1. **`uaid_app` kept INSERT/UPDATE on `autonomy_policies`, so SQL could bypass RBAC and both
   ledgers.** Taken Sol's preferred branch — the real DB lock (§OD-11). `0062` now REVOKEs
   both privileges, adds the NOLOGIN `policy_admin_writer` role and the SECURITY DEFINER
   `admin_write_autonomy_policy`, and makes that function the runtime role's only write path;
   it refuses without an `allowed`, policy-kind, same-tenant, unspent `admin_actions` row, and
   RLS still confines it to the caller's tenant. Fact 0.1.9 shows **no product path breaks**;
   the named break is 32 test call sites in 20 files, wrapped through the production service by
   §OD-14, not exempted. `app/repositories/autonomy_policies.py` and
   `scripts/bootstrap_rls_role.sql` are **un-frozen on the record** with pre-change hashes and
   a builder duty to publish post-change hashes (§1.1). The v1 claim is no longer a
   contradiction; what remains uncovered (owner credentials, the Python matrix floor) is named
   in §0.2/§0.3/§0.5, not claimed. New probes: P-priv/autonomy_policies/INSERT,
   P-priv/autonomy_policies/UPDATE, P-writer-requires-allowed-action,
   P-writer-requires-policy-kind, P-writer-requires-unspent-action; assertions A-writer-role,
   A-downgrade-grants.
2. **`tighten_autonomy_overrides` could relax.** Accepted — v1's reasoning about
   `validate_overrides` was wrong (§OD-2 records why). §OD-12 adds
   `admin_overrides_is_monotonic(old, new)` over the three tightening axes of
   `app/policy/matrix.py:76-112`, enforced inside the writer against the row read
   `FOR UPDATE` — never a caller-supplied snapshot — so `{}` cannot re-enable a disabled
   action. New probes: P-tighten-relax-empty-map (Sol's exact case),
   P-tighten-relax-drops-disable, P-tighten-relax-lowers-min-level, P-tighten-changes-level;
   assertion A-monotonic-table.
3. **Four CHECKs had no load-bearing refusal probe.** Added, each with a drop-constraint
   mutation and a payload that satisfies its neighbours: P-check-insufficient-rank,
   P-check-role-presence, P-check-tae-role-shape, and — replacing v1's weaker
   `ck_admin_actions_unauth_shape` with the biconditional
   `ck_admin_actions_provenance_partition` — P-check-provenance-unauth-mislabel and
   P-check-provenance-verified-unauth. §5.0 rule 4 states how a probe reaches a CHECK that a
   BEFORE-INSERT trigger would otherwise mask.
4. **Probe/mutation mismatches.** Fixed object by object: privileges became the
   **P-priv/`<table>`/`<privilege>`** family (12 cases, each mutation granting *that*
   privilege, §5.2.f); append-only became **P-ao/`<table>`/`<statement>`** (11 cases, each
   mutating that table's that-statement trigger, §5.2.g); RLS became **P-rls/`<table>`**
   (4 cases, each disabling that table's own RLS, §5.2.h); the monkeypatched service probe was
   replaced by P-writer-requires-allowed-action, which mutates the **production** function
   body, with the Python ordering demoted to the honestly-labelled A-service-refusal-no-write;
   P-audit-chain was demoted to A-audit-chain for the same reason; and P-downgrade-populated
   now names its mutation (execute the guard-free downgrade DDL and prove it commits, then
   roll back). §5.0 gained rules 4–6 to make these requirements general.
5. **Role events could lie about the grant.** `admin_role_grants` gains
   `uq_admin_role_grants_identity` and `tenant_admin_events` now carries the composite FK
   `fk_tae_grant_identity` binding `(grant_id, tenant_id, subject_principal, admin_role)` to
   the grant row — a foreign key, not a trigger comparison, so it holds for the owner too
   (§OD-13). New probes: P-event-principal-mismatch, P-event-role-mismatch.
6. **Decision partitioning was not DB-true.** §OD-5's trigger now derives the highest active
   grant itself and requires `actor_role` to *be* it, so `refused_insufficient_role` is
   impossible while a sufficient higher grant is active and `allowed` cannot understate the
   role held; the provenance biconditional makes `refused_no_grant` impossible for an
   unauthenticated actor. §OD-3 documents the matching pure order. New probes:
   P-refuse-insufficient-with-higher-grant, P-allow-not-highest-grant, plus P-2 cases (b) and
   (h).
