# Slice 63 — Enterprise administration (org/tenant admin, DB-enforced RBAC, role-gated policy management)

**Seats (ruling 2026-08-23, standing).** PLANNER = Claude/Fable seat (this document).
BUILDER = Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on
plan and code, probe-backed verdicts only. **The builder never edits this plan.**

**Version.** **v4.1** (amendment to the approved v4; **plan REJECT count stays 0** — this
amendment does not restart it).

**v4 history, unchanged.** Sol REJECTED v1, v2, and v3 **as plans**. The v3 REJECT
(`369abc89-7144-4f42-b810-72f6ec367a64`) found that the four writer-function mutations at
§5.2.a remained **masked by a neighbouring trigger** (`admin_policy_changes_guard`), so
`P-writer-no-existing-policy` did not close v2 defect 3. **The owner (Salim, 2026-08-24) ruled
that all three rejects were correct against the standard he had set, and that the standard
itself was wrong for overlapping guards.** He amended it (the **overlapping-guard probe pair**,
now §5.0 rule 8), authorized v4, and **reset the consecutive plan REJECT count to 0**. v4
changed **only** what that amendment required: §5.0 gained rule 8, the five §5.2.a rows the
amendment covers became named **pairs** in the new §5.2.a.1, and §10 recorded it. Every claim v2
was rejected for is still backed by the live PostgreSQL 16 results in §0.1 facts 13–16, and
**which** rows overlap was **measured live** on PostgreSQL 16.14 while writing v4 (§5.2.a.1,
C1–C7) rather than assumed — including the two findings recorded against the plan's own interest:
one case has a **second** neighbour inside the writer function itself, and the GUC case's real
neighbour is **RLS**, not the ledger trigger. **v4 was APPROVED as a plan and built** on
`feat/slice-63-enterprise-admin` at `ddb3869`.

**Why v4.1 exists.** Sol then **REJECTED the code**
(`380cc908-3745-46fb-b762-504f4e1bd4fd`) for a **concurrent first-policy-write race** that the
approved v4 step sequence itself produces. Measured by Sol on PostgreSQL 16.14: two authorized
writers both observed **no** policy row, the final stored level was `2`, and the two
`admin_policy_changes` rows were `[(NULL, 3), (NULL, 2)]` — the second write overwrote level 3
while recording `previous_autonomy_level = NULL`, so the ledger no longer described what changed.
**Root cause: approved v4 §OD-11 steps 5–7** — `SELECT … FOR UPDATE` on an **absent** row, then
`INSERT … ON CONFLICT DO UPDATE`, with the ledger's `previous_autonomy_level` taken from the
empty pre-insert read. **`FOR UPDATE` on an absent row locks nothing**, so the two writers never
serialized and both believed they were the first. The finding is accepted in full: it is a defect
in this plan's sequence, not in the build. The builder **correctly refused** to patch outside the
approved plan, so the sequence is amended **here**.

**Scope of v4.1 — §OD-11 and the owner's required test surface, nothing else.** The writer's
absent-row path is replaced (§OD-11 step 3.7: `INSERT … ON CONFLICT DO NOTHING` to serialize
creation, **then** lock / read / update, with `previous_autonomy_level` read only **after** the
row is guaranteed to exist); the owner's standing addition to the test bar lands as **§5.0
rule 9**; its named probe **`P-writer-concurrent-first-write`** lands as **§5.2.a.2**; §9's
probe bar moves from eight conditions to nine; §10 gains a **v4.1** entry. **Everything else in
v4 stands as approved and is not reopened** — §5.0 rule 8, the five §5.2.a.1 reachable/own-reason
pairs, and every v1–v3 accepted fix. No new tables, no new columns, no HTTP, no go-live flip, no
D-8/D-9/D-10 close, **no new migration and no renumber**: this slice's migration is `0062` and
v4.1 does not touch it (the writer body is created by `0062` from
`app/admin/policy_sql.py`, so the amended sequence ships as a change to that module's clause
text, not as a second migration).

**One correction inside v4.1, before review (coordinator finding, 2026-08-24).** The finding held
that §5.2.a.2's interleaving could not reproduce the race, on the reading that the second writer
would wait at its existence probe on the first writer's uncommitted row and therefore behave
correctly under the v4 body too. That premise was measured and **does not hold**: a tuple
invisible to the reader's snapshot cannot be row-locked, so that `SELECT … FOR UPDATE` returns no
row **without waiting** (§OD-11 R6), and under the specified interleaving the v4 body reproduced
`[(NULL, 3), (NULL, 2)]` (R7) while v4.1 produced `[(NULL, 3), (3, 2)]` (R8). The window is
therefore kept and the **step sequence is unchanged**; what changed is the **evidence**: the
mechanism is now stated in the probe rather than left to inference, assertion 6 gained an observer
half that pins the waiter to the write rather than the probe, rule 9 gained the by-construction
and blocking-site requirements, and R6–R8 were recorded. This is still v4.1, not a v5.

**Halt rule: one REJECT of v4.1 halts this line — there is no v5 without the owner.**

> **This slice closes NO spec section and does NOT satisfy the roadmap Slice 61 exit.**
> D-8, D-9, and D-10 stay **OPEN** (owner = Salim). Slice 63 is the last scheduled slice:
> after it merges the coordinator STOPS for the Slice 55–63 final report. **This plan does
> not schedule Slice 64.**

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 63 (l.655–668).
**Spec grounding.** §26.7 last bullet ("enterprise administration", l.2522); §17.2 tenant
isolation controls (l.1698–1714); §17.3 tenant boundary rule (l.1716–1718); §16.1
"authorization" + "role-based access control" (l.1550–1568); §16.6 audit; §5/§2.6 (the
policy object being managed). **A5 / readiness / go-live are untouched.**

**Alembic.** Live head **re-verified for v3**: `uv run alembic heads` → **`0061 (head)`**
(`migrations/versions/0061_cost_learning.py`, `revision="0061"`, `down_revision="0060"`), run
on branch `feat/slice-63-enterprise-admin` at plan time. This slice adds **migration `0062`**,
file `migrations/versions/0062_enterprise_admin.py`, `revision="0062"`,
`down_revision="0061"`. Its footprint:

- **four new tables** (each with its own PK/UNIQUE/CHECK/FK/trigger set);
- **one new column** on an existing table (`organizations.status`);
- **two new functions**: `public.admin_write_autonomy_policy(...)` (SECURITY DEFINER, owned by
  the new NOLOGIN role `policy_admin_writer`; it performs the policy write **and** spends the
  authorization in one call, §OD-11 as revised for defect 1) and the pure helper
  `public.admin_overrides_is_monotonic(jsonb, jsonb)`;
- **one function DROP+recreate**, same signature (`resolve_tenant_api_key`);
- **one privilege NARROWING on an existing table** —
  `REVOKE INSERT, UPDATE ON public.autonomy_policies FROM uaid_app` (§OD-11, v2 defect 1).
  This is the one place Slice 63 changes an existing `uaid_app` grant, and it **removes**
  privilege; `SELECT` is untouched so every existing read path is unaffected;
- **grant additions**: to `policy_admin_writer`, `SELECT, INSERT, UPDATE ON
  autonomy_policies`, `SELECT ON admin_actions`, and `SELECT, INSERT ON
  admin_policy_changes` (it now writes the ledger row itself — v3 defect 1);
  `SELECT ON tenants, organizations` to `api_key_resolver`;
  `EXECUTE ON audit_append` to `CURRENT_USER`. On the four **new** tables `uaid_app` is
  granted `SELECT` everywhere and `INSERT` **only** on `admin_actions`.

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
    the loss of `upsert` does. §OD-14 (v3) resolves those sites **on their own connection**.
12. **A5 is `slice54.v1`; readiness is `slice20.v1`; `can_go_live_autonomously` is the
    literal `False`** (`app/release/production_autonomy.py:71,119`;
    `app/intake/readiness.py:45`). Slice 63 must not move any of them.

The next four facts were **executed against the live PostgreSQL 16 container** (`app_test`,
role `app`) while writing v3, each in a rolled-back transaction on throwaway schemas, because
v2 was rejected for asserting three of them without proof. They are the load-bearing evidence
for §OD-11, §OD-14, §5.2.a and §5.2.g, and the builder must reproduce each as a real test.

13. **A non-owner `SECURITY DEFINER` function is RLS-confined, and it works on the caller's
    own uncommitted transaction.** With a `FORCE ROW LEVEL SECURITY` table, a
    `NOLOGIN NOSUPERUSER NOBYPASSRLS` owner role, and a `tenant_isolation` policy keyed on
    `current_setting('app.current_tenant', true)`: called from a **superuser** session inside
    one open transaction, after `set_config(..., true)`, the function **read a row the same
    transaction had just inserted and not committed**, and wrote successfully. With the GUC
    set to a different tenant the same call refused (the action row was invisible), and with
    the GUC unset it refused. This is why §OD-14 needs **no second connection** for
    admin-session tests, and why "RLS still applies inside the definer function" is a
    measured fact, not an inference.
14. **Ledger-backed spend is atomic and rolls the policy write back.** In the same harness, a
    function that upserted the policy and then inserted a ledger row protected by
    `UNIQUE(admin_action_id)` refused the second call for the same action id, and the policy
    column **retained its first value** (the caller saw `level=3`, not the replay's `2`) —
    the plpgsql exception path unwound the whole call. This is the defect-1 design, measured.
15. **`TRUNCATE <parent>` never reaches a BEFORE TRUNCATE trigger when an inbound FK exists.**
    Live: `ERROR: cannot truncate a table referenced in a foreign key constraint` (SQLSTATE
    `0A000`), exactly what Sol observed. Truncating parent **and** child in one explicitly
    ordered statement **does** reach the trigger (`RAISE` observed, naming the parent), and
    with both truncate triggers disabled the same statement **commits** (`rows_left = 0`).
    With only the *child's* trigger disabled in setup, the surviving `RAISE` provably comes
    from the **parent's** trigger. §5.2.g is rebuilt on this.
16. **`DROP TABLE <parent>` alone also fails** — `cannot drop table … because other objects
    depend on it` (SQLSTATE `2BP01`, dependent constraint named). The populated-downgrade
    mutation must therefore be the ordered children-first sequence, not a single drop
    (§5.2.i). Separately, `uaid_app` holds **only `SELECT`** on `organizations` and `tenants`
    (live `information_schema.table_privileges`), so the `organizations.status` CHECK can only
    be probed on the owner path.

### 0.2 Load-bearing claim

**Policy writes.** For the runtime role `uaid_app`, `autonomy_policies` is **write-locked**:
it holds `SELECT` and no `INSERT`/`UPDATE`/`DELETE`, so no repository, service, or ad-hoc SQL
executed as `uaid_app` can change a project's autonomy level or override map except by calling
`public.admin_write_autonomy_policy`, which fails closed unless handed an `admin_actions` row
that is `allowed`, of a policy kind, in the caller's own tenant and project, and **not already
spent** by an `admin_policy_changes` row. **The write and the spend are the same database
call** (v3): that one function upserts the policy *and* inserts the ledger row, so there is no
Python-side sequence to interleave, abandon, or replay, and `uaid_app` holds no `INSERT` on the
ledger table either. For `tighten_autonomy_overrides` it additionally
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
`autonomy_policies` row actually holds; its `previous_autonomy_level` and `override_key_count`
are derived by the function from the rows themselves, never accepted from a caller. **v4.1:**
`previous_autonomy_level` is derived only **after** the policy row is guaranteed to exist —
creation is serialized on `UNIQUE (tenant_id, project_id)` — so two concurrent first writers
cannot both record a NULL previous level while one silently overwrites the other (§OD-11 step
3.7; standing proof `P-writer-concurrent-first-write`, §5.2.a.2). Derivation is only worth
something if it is correct under contention, which is the defect Sol's code REJECT found.
A `tenant_admin_events` role event is composite-FK
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
one that spends that authorization in the same call and transaction as the write, so a policy
can neither change without a ledger row nor be changed twice on one authorization — and which
refuses a "tighten" that would relax the currently stored override map, including an
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
  policy-kind (P-writer-requires-policy-kind), unspent (P-writer-spends-action-atomically)
  same-tenant admin action, and refuses to infer the tenant when the GUC is unset
  (P-writer-guc-unset)."
- "The policy write and the spending of its authorization are **one** database call: the same
  function that upserts the policy inserts the `admin_policy_changes` row, and a second call
  with the same `admin_action_id` is refused with the policy left unchanged
  (P-writer-spends-action-atomically, A-writer-returns-both-ids). `uaid_app` cannot insert a
  ledger row at all (P-priv/admin_policy_changes/INSERT), and no `upsert` method survives on
  the policy repository (A-no-ungated-upsert)."
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
  unspent authorization (P-writer-spends-action-atomically) — and those guards bind the owner
  path too, since the runtime role cannot insert one at all."
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

### 1.1 Deliberately UN-FROZEN, stated explicitly (v2 defect 1)

Sol's v1 defect 1 cannot be fixed without touching the Slice-3 write path, so v1's freeze of it
is lifted **on the record**:

| File | SHA-256 **before** Slice 63 | Why un-frozen | What may change |
|---|---|---|---|
| `app/repositories/autonomy_policies.py` | `9b563f6a8780da4a60cd1a57de377df6f3510a221d656564c115b89812288317` | Its `upsert` writes `autonomy_policies` via the ORM as `uaid_app`; after §OD-11's REVOKE that privilege is gone, so the method can only raise | **`upsert` is DELETED** (v3, defect 1). It is not re-signatured: the gated write now also writes the ledger, which is not a policy-repository responsibility, and a surviving `upsert` is a name a future caller would reach for. `decision_for`, `snapshot_decisions`, and every read stay behaviourally identical, and the `actor`-is-untrusted docstring on the reads stays |
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
row, and the Slice-3 `upsert` **replaced** the whole map. Sol's live probe is correct: both
`{"run_tests": {"allow": false}}` and `{}` validate, and applying `{}` re-enables `run_tests`.
Monotonicity is therefore enforced in the DB by §OD-12, against the current stored map — never
against a caller-supplied "previous" snapshot, which a caller could simply lie about.

`tighten_autonomy_overrides` on a project with no existing policy row is refused
(`no_existing_policy`) — there is no stored map to be monotonic against, and without the clause
a "tighten" would silently *create* a policy at a level nobody set (P-writer-no-existing-policy).

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

**Amended in v4.1 (owner ruling 2026-08-24, after Sol's code REJECT
`380cc908-3745-46fb-b762-504f4e1bd4fd`).** Steps **3.5 – 3.7** below are rewritten. The approved
v4 sequence took `SELECT … FOR UPDATE` on a possibly-absent row, then upserted with
`ON CONFLICT DO UPDATE`, and derived the ledger's `previous_autonomy_level` from that pre-insert
read. **`FOR UPDATE` on an absent row locks nothing**, so two authorized first writers both saw
"no policy" and both recorded `previous_autonomy_level = NULL` while the second silently
overwrote the first's level. v4.1 serializes creation on the unique index with
`INSERT … ON CONFLICT DO NOTHING`, and reads `previous_autonomy_level` only **after** the row is
guaranteed to exist. Nothing else in §OD-11 changes: the REVOKE, the `policy_admin_writer` role,
the single-call write-and-spend, RLS confinement inside the definer, and the "only runtime
writer" claim all stand as approved.

1. `REVOKE INSERT, UPDATE ON public.autonomy_policies FROM uaid_app`. `SELECT` is untouched,
   so `decision_for` / `snapshot_decisions` / readiness / control-loop / broker reads are
   unaffected. `DELETE` was never granted (`0004`'s "NO DELETE"), so the runtime role now has
   **no write path at all** to the table.
2. New NOLOGIN role `policy_admin_writer` (bootstrap script, §Alembic), granted exactly what
   its one function needs and nothing more: `SELECT, INSERT, UPDATE ON
   public.autonomy_policies` (no DELETE), `SELECT ON public.admin_actions`, and
   `SELECT, INSERT ON public.admin_policy_changes` (it writes the ledger itself, step 3.9).
   It gets no grant on `admin_role_grants`, `tenant_admin_events`, `tenant_api_keys`, or
   anything else. Because the role is `NOBYPASSRLS` and not the owner of any of those tables,
   **every one of those reads and writes is itself RLS-confined to the caller's tenant** — the
   GUC is transaction-local and `SECURITY DEFINER` does not change it — so the function cannot
   see, let alone spend, another tenant's admin action. Fact 0.1.13 measured all three halves
   of this (confinement, cross-tenant refusal, unset-GUC refusal).
3. `CREATE FUNCTION public.admin_write_autonomy_policy(p_admin_action_id uuid,
   p_project_id uuid, p_autonomy_level smallint, p_overrides jsonb,
   OUT o_autonomy_policy_id uuid, OUT o_admin_policy_change_id uuid)`,
   `LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog` (all names
   `public.`-qualified, the `0026` discipline), `ALTER FUNCTION ... OWNER TO
   policy_admin_writer`, `REVOKE ALL ... FROM PUBLIC`, `GRANT EXECUTE ... TO uaid_app`.
   **It returns both ids because it performs both writes** (defect 1); Python calls it as
   `SELECT * FROM public.admin_write_autonomy_policy(...)` and never writes either table.
   Body, fail-closed in order, each failure a distinct `RAISE` message:
   1. `v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid`;
      NULL ⇒ `RAISE 'tenant_guc_unset'`. The function **never** falls back to a tenant read
      off the action row — probed by P-writer-guc-unset.
   2. load `admin_actions` by `id = p_admin_action_id AND tenant_id = v_tenant AND
      project_id = p_project_id`; missing ⇒ `no_such_admin_action`.
   3. `decision = 'allowed'` else `admin_action_not_allowed`.
   4. `action_kind IN ('set_autonomy_policy','tighten_autonomy_overrides')` else
      `admin_action_not_policy_kind`.
   5. **Existence probe.** `SELECT id, autonomy_level, overrides ... FOR UPDATE` the current
      `autonomy_policies` row for `(v_tenant, p_project_id)`; `v_found := FOUND`. **Honest
      about what this statement does (v4.1):** when the row exists it really locks it, which is
      what step 3.6 and step 3.7(a) rely on; when the row does **not** exist, `FOR UPDATE`
      locks **nothing** — there is no row to lock, so this is an existence probe and no more.
      Its level is therefore used only for the step-3.6 tighten comparisons (which require an
      existing row) and is **never** the ledger's `previous_autonomy_level` on the absent-row
      path. That confusion is exactly the v4 defect.
   6. `action_kind='tighten_autonomy_overrides'` ⇒ the row must exist
      (`no_existing_policy`), `p_autonomy_level` must equal the stored level
      (`tighten_may_not_change_level`), and
      `public.admin_overrides_is_monotonic(stored, p_overrides)` must be true
      (`tighten_would_relax_overrides`) — §OD-12. **This block runs BEFORE any INSERT (v4.1),
      and that ordering is load-bearing.** A tighten against an absent row refuses
      `no_existing_policy` while `autonomy_policies` still holds **zero** rows for the project:
      the step-3.7 serialize-INSERT is reachable **only** on the `NOT v_found` path, which a
      tighten can never reach because this clause has already raised. The function therefore
      never creates a row in order to then refuse the tighten that would have used it — that
      would leave an orphan policy nobody authorized, and a `set_autonomy_policy` level for a
      project whose administrator only ever asked to tighten. Measured (v4.1 probe R3):
      `pol_rows_before = 0`, refusal `no_existing_policy` (SQLSTATE `P0001`),
      `pol_rows_after = 0`, `chg_rows_after = 0`.
   7. **The write — v4.1 replaces v4's single `ON CONFLICT DO UPDATE` upsert.** Two booleans
      carry the state (`v_found` from step 3.5, plus a new `v_created`), alongside the existing
      `v_previous_level` / `v_stored_overrides`:
      - **(a) Present row** (`v_found` true): nothing to serialize — this transaction already
        holds the row lock from step 3.5, and `v_previous_level` is that locked read's level.
        Continue at (d).
      - **(b) Absent row — serialize creation.** `INSERT INTO public.autonomy_policies
        (tenant_id, project_id, autonomy_level, overrides, updated_at) VALUES (v_tenant,
        p_project_id, p_autonomy_level, COALESCE(p_overrides,'{}'::jsonb), now())
        ON CONFLICT (tenant_id, project_id) DO NOTHING RETURNING id INTO
        o_autonomy_policy_id;` then `v_created := FOUND`. The `UNIQUE (tenant_id, project_id)`
        index is what serializes: a concurrent first writer's in-flight speculative insertion
        makes this statement **wait** for that transaction, and `DO NOTHING` then reports no row
        inserted. So `v_created` distinguishes *"I created it"* from *"someone else did and I
        waited for them"* — the distinction v4 had no way to make. If the transaction we waited
        for **aborted**, the index entry is released and our INSERT proceeds, so `v_created` is
        true and the ledger honestly records a creation: a rolled-back first write must never
        leave the next writer citing a previous level that was never committed.
      - **(c) Authoritative read, taken only after the row is guaranteed to exist.** Re-run
        `SELECT id, autonomy_level, overrides ... FOR UPDATE` for `(v_tenant, p_project_id)`
        into `o_autonomy_policy_id, v_previous_level, v_stored_overrides`. The row provably
        exists now — this transaction either inserted it at (b) or waited for the transaction
        that committed it — so this `FOR UPDATE` really locks. `IF NOT FOUND THEN RAISE
        'policy_write_row_unavailable'` is the fail-closed backstop for a snapshot that cannot
        see it; the function never proceeds on a row it could not read. Then `IF v_created THEN
        v_previous_level := NULL; END IF;` — a genuine creation has no previous level, and
        (b)'s `RETURNING` is the only thing entitled to assert that. **Every other value of
        `previous_autonomy_level` comes from this post-insert locked read, never from the
        step-3.5 probe.**
      - **(d) Update the locked row** to `(p_autonomy_level, COALESCE(p_overrides,'{}'::jsonb),
        now())`, `RETURNING id INTO o_autonomy_policy_id`. The row exists and is locked by this
        transaction, so a plain `UPDATE` is sufficient and there is no second conflict path to
        reason about. For the creator this rewrites its own just-inserted values, which is a
        deliberate no-op kept in order to have one write path instead of two.
   8. **Spend the authorization in the same function, same transaction.** `INSERT INTO
      public.admin_policy_changes (tenant_id, project_id, admin_action_id,
      autonomy_policy_id, previous_autonomy_level, new_autonomy_level, override_key_count)`
      … `RETURNING id INTO o_admin_policy_change_id`, wrapped in
      `BEGIN … EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION
      'admin_action_already_spent' … END`. `uq_admin_policy_changes_action` is the **sole**
      spend authority — there is deliberately **no** separate "already spent?" `SELECT`,
      because a pre-check would mask the constraint and could not carry a load-bearing
      mutation (§5.0 rule 1). `override_key_count` (`jsonb_object_keys` cardinality) is
      **derived here** and `previous_autonomy_level` is the value derived at step 3.7 — neither
      is ever accepted from the caller, so the ledger cannot be falsified even by the one
      privileged caller. **v4.1:** "derived" is only worth something if the derivation is
      correct under concurrency, which is what step 3.7 now provides and
      `P-writer-concurrent-first-write` (§5.2.a.2) is the standing proof of.
   9. Ordering is load-bearing in one direction: the policy write must precede the ledger
      INSERT, because `admin_policy_changes_guard` (§3.3) requires `new_autonomy_level` to
      equal the **stored** policy level. Fact 0.1.14 measured the consequence that matters —
      a refused spend unwinds the policy write, so there is no window in which a policy is
      changed without a ledger row.

   **Isolation, stated rather than assumed (v4.1).** The production entry point
   `apply_policy_change_in_scope` opens `tenant_scope(ctx)` with no `isolation_level`, so the
   engine default **READ COMMITTED** is the isolation this sequence is designed for and probed
   at: step 3.7(c) is a new statement and therefore takes a fresh snapshot, which is why it can
   see the row the writer it waited for has just committed. At **REPEATABLE READ** or
   **SERIALIZABLE** the loser does **not** silently record a wrong `previous_autonomy_level`:
   measured on PostgreSQL 16.14 (v4.1 probe R4), the step-3.7(b) `ON CONFLICT DO NOTHING` itself
   raised SQLSTATE **`40001`** (`could not serialize access due to concurrent update`), the
   transaction rolled back, and no ledger row was written — fail closed. The
   `policy_write_row_unavailable` clause at 3.7(c) is a **backstop that did not fire in that
   build**, and the plan claims nothing more for it than that: it exists so that a snapshot which
   cannot see the row can never fall through to a write, not because a path to it has been
   demonstrated.

   **Measured, on a throwaway database (v4.1, PostgreSQL 16.14, container
   `uaid_os-postgres-1`; database `s63v41_tmp` created and dropped in the same session, no app
   database touched).** The harness reproduces this writer's clause structure and the
   §3.3:938–944 `admin_policy_changes_guard`; these are harness results, and **the builder must
   reproduce them against the real `0062` objects**:

   | # | Scenario | Result |
   |---|---|---|
   | R1 | **v4 sequence** (`FOR UPDATE` on the absent row, then `ON CONFLICT DO UPDATE`), two concurrent first writers (levels 3 then 2) | **Defect reproduced** — ledger `[(NULL, 3), (NULL, 2)]`, stored level `2`; matches Sol's `380cc908` measurement exactly, so the harness is credible before it is used to bless the fix |
   | R2 | **v4.1 sequence**, same two concurrent first writers | **Correct** — writer B blocked until A committed (B called at `31.740`, returned `33.049`, A committed `33.047`), both calls returned the **same** `o_autonomy_policy_id`, ledger `[(NULL, 3), (3, 2)]`, stored level `2`, two distinct spends |
   | R3 | **v4.1 sequence**, tighten against an absent row | Refused `no_existing_policy` (`P0001`) with `pol_rows` `0 → 0` and `chg_rows = 0` — the refusal precedes any INSERT |
   | R4 | **v4.1 sequence**, loser at `REPEATABLE READ` | Refused `40001` at step 3.7(b); no policy overwrite, no ledger row |
   | R5 | **v4.1 sequence**, sequential sanity: first write, second write, monotone tighten, relaxing tighten | `[(NULL, 3), (3, 2), (2, 2)]` then `tighten_would_relax_overrides` (`P0001`) — the present-row path, the tighten level-equality path and §OD-12 all still behave as approved in v4 |
   | R6 | **Lock mechanics of the absent row**, isolated from the writer: session A holds an **uncommitted** `INSERT` for `(tenant, project)`; session B then runs `SELECT … FOR UPDATE` on that key, and afterwards `INSERT … ON CONFLICT DO NOTHING` on the same key | The `SELECT … FOR UPDATE` returned **0 rows in 0.252 ms — it did not wait**; the `INSERT … ON CONFLICT DO NOTHING` **blocked 2916.840 ms** and returned at `24.933` immediately after A committed at `24.932`. A tuple invisible to the reader's snapshot is not lockable, so **the existence probe is not a serialization point and the unique index is** — this is the mechanical reason step 3.7(b) is the fix and the reason the §5.2.a.2 interleaving reaches the TOCTOU window |
   | R7 | **v4 sequence** under the §5.2.a.2 forced interleaving exactly as specified — W2's call issued **1.79 s after W1's call returned** (so W1 had already INSERTed, uncommitted), W1 committing only after W2 was observed pending | **Defect reproduced** — W2's step-3.5 probe reported `probe_found=f previous=<NULL>` (it did **not** block), W2 then blocked **3219.597 ms** on an ungranted `transactionid ShareLock` with `pg_blocking_pids = {W1}`, and the result was ledger `[(NULL, 3), (NULL, 2)]`, stored level `2`, **1** policy row, **2** distinct spends — Sol's `380cc908` shape, from this probe's own interleaving and with **no** barrier added to the mutated body |
   | R8 | **v4.1 sequence** under the **identical** interleaving and observer | **Correct** — W2's probe likewise reported `probe_found=f` (the same TOCTOU window is entered), W2 blocked **3477.491 ms**, the observer captured W2 `state='active'`, `wait_event_type='Lock'`, `wait_event='transactionid'`, `pg_blocking_pids = {W1}` **while W1 was still open**, and 3.7(c) then reported `created=f previous_after=3` — ledger `[(NULL, 3), (3, 2)]`, stored level `2`, **1** policy row, **2** distinct spends |

   **What v4.1 does not change.** The clause names the §5.2.a.1 pairs mutate — the GUC clause,
   the `decision`/`action_kind` clauses, and the tighten existence / level-equality / monotonic
   clauses — keep their identity, their `RAISE` texts and their order, so all five approved pairs
   stand as written. The one wording consequence: in a `/reachable` half whose payload has **no**
   stored policy row (Pair 4), the row that appears is created by step 3.7(b)'s serialize-INSERT
   rather than by v4's `ON CONFLICT DO UPDATE`. The asserted harm — a policy row created by
   "tightening", with a ledger row endorsing it — is identical, and neither half of any pair needs
   restating.

   **Where the amended sequence lands.** `0062` installs this body by executing
   `WRITER_CREATE_SQL` from `app/admin/policy_sql.py` (via `app/admin/ddl.py`), so the fix is a
   change to that module's clause text and `0062` is **not** renumbered and **no** second
   migration is added. The branch is unmerged, so no deployed database holds the v4 body; a
   developer database already migrated by the pre-amendment `0062` on this branch must be
   dropped and re-migrated (`make test-db-drop test-db-create test-db-migrate`) rather than
   patched in place, and the builder should say so in the PR body.
4. **RLS still applies inside the definer function.** `policy_admin_writer` is neither the
   owner of `autonomy_policies` nor `BYPASSRLS`, the table is `FORCE ROW LEVEL SECURITY`, and
   `0004`'s `tenant_isolation` policy has no `TO` clause (so it applies to that role too).
   The GUC is transaction-local and unaffected by `SECURITY DEFINER`, so the write is confined
   to the caller's tenant with no policy change. The composite FK
   `(project_id, tenant_id) → projects` on `admin_actions` is the second half.
5. The function is the **only** runtime writer of **either** table.
   `AutonomyPolicyRepository.upsert` is **deleted** (§1.1) rather than re-pointed, and
   `uaid_app` holds no `INSERT` on `admin_policy_changes` (§3.3), so the ledger row can only
   come from inside the function. `app/admin/policy_admin.py` is the only caller, and it mints
   the `admin_actions` row first. **There is no Python-side sequence a caller can interleave,
   abandon, or replay:** the write and the spend are one statement to the caller. A second
   call with the same `admin_action_id` refuses — P-writer-spends-action-atomically.

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

**The remedy (v3, defect 2): the service takes a session, and the helper never opens a second
connection.** v2 said the helper would seed the grant "via its own short-lived admin engine"
for runtime-mode sites while acknowledging in the same sentence that a second connection cannot
see an uncommitted fixture. Sol is right that this cannot work, and the acknowledgement did not
make it work. **The chosen path is (a): the SECURITY DEFINER function is called on the caller's
own session.** Fact 0.1.13 proves that works, including for rows the caller has not committed.

Two shape changes make it possible:

1. `app/admin/policy_admin.py` exposes `apply_policy_change(session, ctx, *, …)` — it
   **accepts** a session and owns no transaction. A thin
   `apply_policy_change_in_scope(ctx, *, …)` wrapper opens `tenant_scope` for real runtime
   callers, so production ergonomics are unchanged. This is the repository convention
   (`AutonomyPolicyRepository(session, ctx)`), not a test affordance.
2. `tests/admin_support.py` gains one helper:

```
async def seed_gated_policy(*, session, ctx, project_id, autonomy_level,
                            overrides=None, session_is_admin=False,
                            admin_engine=None,
                            principal="test:tenant_admin") -> PolicyChangeResult
```

It **builds no engine of its own** in either mode — v2's "short-lived admin engine from
`TEST_ADMIN_URL`" is deleted outright.

- **Admin-session sites** (`session_is_admin=True`, the `db_session` fixture — fact 0.1.11):
  everything happens **on that one session, in that one transaction**. The helper runs
  `SELECT set_config('app.current_tenant', <ctx.tenant_id>, true)`, INSERTs the active
  `tenant_admin` grant directly (the admin role has the privilege), and calls
  `apply_policy_change(session, ctx, …)`. The definer function executes on the same
  connection and therefore sees the fixture's uncommitted tenant, project, and grant. **No
  second engine, no commit of a rolled-back fixture, no bypass.** This is exactly the sequence
  measured in fact 0.1.13.
- **Runtime-scope sites** (`session_is_admin=False`, the `tenant_scope` majority): `uaid_app`
  has no `INSERT` on `admin_role_grants` by design, so the grant is seeded through the
  **existing `admin_engine` fixture**, which the caller passes in — not through an engine the
  helper builds. That fixture is the repo's established seeding path and it **commits**: these
  sites' tenants and projects are created inside `async with admin_engine.begin()` blocks that
  have already exited (verified in `tests/conftest.py:162-169` and, as one representative call
  site, `tests/test_ci_evidence.py:160-162`), so the committed-tenant precondition holds by
  construction rather than by hope. The helper still **states and enforces** it: with
  `session_is_admin=False` and no `admin_engine`, or with a tenant the admin connection cannot
  see, it raises `SeedPreconditionError("gated policy seeding in runtime mode needs the "
  "admin_engine fixture and an already-committed tenant; seed before entering tenant_scope, "
  "or pass session_is_admin=True")`. It never falls back, never skips, and never writes the
  policy another way, so a site that trips it is a loud failure the builder must convert — not
  a silent pass. **No claim is made anywhere that a second connection can see an uncommitted
  fixture.**

Both modes then call the **production** `apply_policy_change` with a `TenantContext` carrying
an `AuthenticatedActor` whose `principal_subject == principal`, and assert the returned
decision is `allowed`. Call sites become a one-line substitution.

The helper must not have a bypass branch, and A-helper-uses-production-path asserts
`tests/admin_support.py` contains no direct `autonomy_policies` or `admin_policy_changes`
INSERT/UPDATE and no call to `admin_write_autonomy_policy` other than through
`apply_policy_change`. **Builder duty:** run the migrated suite before writing anything else
in §OD-14 — the helper working on both fixture shapes is the gate on this remedy, and
A-suite-green is where it is proven.

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
  INSERT OR UPDATE: INSERT ⇒ `status='active'` (a grant is **born active**; history is made by
  revoking, never by inserting a pre-revoked row) → **P-grant-insert-status** (new in v3,
  defect 3); UPDATE ⇒ only `status` and `updated_at` may change, and only `active→revoked`
  (one-way) → P-grant-update-widen.
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

### 3.3 `admin_policy_changes` — tenant-owned, append-only; `uaid_app` **SELECT only**

**Changed in v3 (defect 1):** `uaid_app` is **not** granted `INSERT`. The only writer is
`admin_write_autonomy_policy`, which inserts this row in the same call and same transaction as
the policy write; `policy_admin_writer` holds `SELECT, INSERT`. That is what makes the spend
atomic rather than a Python convention — and it means the three guard-trigger probes below run
on the owner path (§9), because the runtime role cannot reach the trigger at all
(P-priv/admin_policy_changes/INSERT proves that outer layer).

`id`, `tenant_id`, `project_id`, `admin_action_id UUID NOT NULL`,
`autonomy_policy_id UUID NOT NULL`,
`previous_autonomy_level SMALLINT NULL CHECK (BETWEEN 0 AND 5)`,
`new_autonomy_level SMALLINT NOT NULL CHECK (BETWEEN 0 AND 5)`,
`override_key_count SMALLINT NOT NULL CHECK (>= 0)`, `created_at`.

- Composite FKs: `(admin_action_id, project_id, tenant_id) → admin_actions(id, project_id,
  tenant_id)`; `(autonomy_policy_id, project_id, tenant_id) → autonomy_policies(id,
  project_id, tenant_id)` (target `uq_autonomy_policies_id_proj_tenant`, fact 0.1.5).
- `UNIQUE (admin_action_id)` named **`uq_admin_policy_changes_action`** — one authorization is
  spent exactly once. This constraint **is** the spend mechanism of §OD-11 step 3.8: the writer
  inserts and translates `unique_violation` into `admin_action_already_spent`, so there is no
  separate pre-check to drift from it.
- `previous_autonomy_level` and `override_key_count` are derived inside the writer, never
  supplied by a caller (§OD-11 step 3.8).
- Guard trigger `admin_policy_changes_guard` (function `admin_policy_changes_guard()`)
  BEFORE INSERT:
  - the referenced `admin_actions` row has `decision='allowed'` and
    `action_kind IN ADMIN_ACTION_KINDS`;
  - `NEW.new_autonomy_level` equals the referenced `autonomy_policies.autonomy_level`;
  - `action_kind='tighten_autonomy_overrides'` ⇒
    `previous_autonomy_level = new_autonomy_level` (level untouched, §OD-2).
- Append-only: `admin_policy_changes_no_update_delete` + `admin_policy_changes_no_truncate`
  over `admin_policy_changes_block_dml()`; `uaid_app` grant is `SELECT` only.

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
   `status IN ('active','suspended')`, named **`ck_organizations_status_valid`** so a probe can
   target it → **P-org-status-check** (new in v3, defect 3). Existing rows become `'active'`.
   `app/models/organization.py` gains the mapped column. No grant change — and per fact 0.1.16
   `uaid_app` has **only** `SELECT` here, so this CHECK is probed on the owner path (§9).
2. `resolve_tenant_api_key(text)` DROP + recreate per §OD-7; `GRANT SELECT ON public.tenants,
   public.organizations TO api_key_resolver`.
3. `GRANT EXECUTE ON FUNCTION public.audit_append(text,text,text,jsonb) TO CURRENT_USER`
   (§OD-8).
4. **The policy write lock (§OD-11):** assert `policy_admin_writer` exists (fail closed
   naming `make db-bootstrap-rls-role`); `REVOKE INSERT, UPDATE ON public.autonomy_policies
   FROM uaid_app`; `GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO
   policy_admin_writer`, `GRANT SELECT ON public.admin_actions TO policy_admin_writer`, and
   `GRANT SELECT, INSERT ON public.admin_policy_changes TO policy_admin_writer` (after those
   tables are created, so this step runs last); create `admin_overrides_is_monotonic` and
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
public.admin_actions FROM policy_admin_writer`, `REVOKE SELECT, INSERT ON
public.admin_policy_changes FROM policy_admin_writer`, and **restore
`GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO uaid_app`** (the `0004` state,
asserted by A-downgrade-grants); (e) drop the guards/triggers; (f) drop the four tables in
this **exact order** — `admin_policy_changes`, `tenant_admin_events`, then `admin_actions`,
`admin_role_grants` — because both remaining tables are FK parents and a single
`DROP TABLE` on either fails with SQLSTATE `2BP01` (fact 0.1.16). This order is the mutation
P-downgrade-populated must execute, so it is named here rather than left as "children first";
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
| `app/admin/policy_admin.py` | **runtime service**: `apply_policy_change(session, ctx, …) -> PolicyChangeResult` (takes a session, §OD-14) + `apply_policy_change_in_scope(ctx, …)` which owns `tenant_scope`; calls frozen `validate_overrides` first (§OD-14), loads grants, pure-evaluates, records `admin_actions` (allowed **and** refused), and on allowed makes **one** call to `admin_write_autonomy_policy` — which returns both ids — then audits |
| `app/models/admin_rbac.py` | `AdminRoleGrant`, `AdminAction` |
| `app/models/admin_policy.py` | `AdminPolicyChange`, `TenantAdminEvent` (both **read-only** ORM models for the runtime role, in the `app/models/audit_log.py` spirit: the ledger is written by the definer function, never the ORM) |
| `app/repositories/admin.py` | `AdminGrantRepository` (tenant read), `AdminActionRepository` (insert + reads), `AdminPolicyChangeRepository` (**reads plus the single `SELECT * FROM public.admin_write_autonomy_policy(...)` call site** — the one place in the codebase that invokes the gated writer) |
| `scripts/admin_roles.py` | operator CLI, argparse subcommands `grant`, `revoke`, `suspend-tenant`, `reinstate-tenant`, `suspend-org`, `reinstate-org`; prints ids/status only, never a key or an override value; uses `ADMIN_DATABASE_URL` |
| `migrations/versions/0062_enterprise_admin.py` | additive + the one §OD-11 narrowing; imports the CHECK strings and DDL helpers (the `0061` import pattern) |

**Edited (not new):** `app/repositories/autonomy_policies.py` (`upsert` **deleted**, §1.1),
`scripts/bootstrap_rls_role.sql` (`policy_admin_writer`, §1.1),
`app/models/organization.py` (`status`), and the twenty test files of §OD-14.

Tests (new): `tests/test_admin_rbac.py` (pure), `tests/test_admin_rbac_db.py`,
`tests/test_admin_policy_db.py`, `tests/test_admin_policy_lock_db.py` (§OD-11/§OD-12 probes),
`tests/test_admin_tenant_db.py`, `tests/test_admin_checks.py`,
`tests/test_admin_migrate.py`, plus `tests/admin_support.py` (shared seeding: org + two
tenants + projects + keys + grants, and `seed_gated_policy`, §OD-14).

`policy_admin.apply_policy_change` refuses **before** touching the policy: on any
non-`allowed` decision it records the refusal action + audit and never calls the writer.
The order inside one transaction is now only **two** Python steps — `INSERT admin_actions`,
then `SELECT * FROM public.admin_write_autonomy_policy(...)` — because the policy upsert and
the `admin_policy_changes` spend both happen **inside** that one call (§OD-11 step 3.8, v3
defect 1). Python cannot write the policy without spending the action, cannot spend without
writing the policy, and cannot replay a spent action.

No `Makefile` target is added; the operator CLI is invoked as
`uv run python -m scripts.admin_roles <subcommand> …`. `make migrate` /
`test-db-migrate` stay schema-only: a freshly migrated database has **zero** grants, so no
runtime admin action can be `allowed` and no runtime policy write can succeed until an
operator grants a role.

---

## 5. Probes

### 5.0 The owner test standard (applies to every probe in §5.2)

Sol's Slice-62 finding is carried forward, v2 adds rules 4–6 to close defect 4, v3 adds rule 7,
**v4 adds rule 8 — the owner's amended standard for overlapping guards (ruling 2026-08-24)** —
and **v4.1 adds rule 9, the owner's standing addition for writers whose target row may not yet
exist (same ruling, after Sol's code REJECT)**. Rules 1–3 are the single-guard bar and are
unchanged. Rules 1–8 are **not** deleted or renumbered by rule 9.

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
7. **A referential obstacle is never allowed to stand in for the guard** (v3, defect 4). On a
   table that is an FK **parent**, an inbound reference can pre-empt the guard entirely, so
   the probe must remove the obstacle rather than mistake it for a refusal:
   - **TRUNCATE.** `TRUNCATE <parent>` alone raises SQLSTATE `0A000` *before* any BEFORE
     TRUNCATE trigger fires (fact 0.1.15), so such a probe is false in both directions. The
     statement under test is instead the **explicitly ordered multi-table** `TRUNCATE
     <parent>, <child>`, with the **child's** truncate trigger disabled in setup (rule 4) so
     the surviving `RAISE` provably belongs to the parent, and the mutation additionally
     disables the parent's trigger — measured to commit.
   - **DELETE / UPDATE.** Parent-row cases seed a row with **no referencing child**, so an FK
     `RESTRICT` can never masquerade as the append-only trigger or the privilege denial.
   - **DROP TABLE.** A single `DROP TABLE <parent>` fails with `2BP01` (fact 0.1.16); any
     drop-based mutation must be the named children-first sequence of §3.6(f).
   If a guard cannot be reached without dismantling so much that the probe stops being
   evidence, the honest move is to delete the claim, not to keep a probe whose absent-guard
   mutation cannot commit.
8. **Overlapping guards are proven by a named PROBE PAIR** (v4, owner ruling 2026-08-24).
   Rules 1–3 above are the **single-guard** bar and stand unchanged. When a **neighbouring
   constraint independently refuses the same mutation** — i.e. removing the target guard alone
   still leaves the statement refused, by a different object or a different clause — one probe
   is not enough. The target guard is proven by **two named halves**, both of which must be in
   this plan with their expected outcomes:
   - **`<probe>/reachable`** — the **target guard AND every independently-refusing neighbour
     are disabled** ⇒ the mutation **COMMITS**, and the probe asserts the **harm** the target
     guard exists to prevent actually happened (the row that should not exist, the column that
     should not have moved). This establishes that the mutation is genuinely reachable and that
     nothing else was blocking it.
   - **`<probe>/own-reason`** — the **neighbour is disabled, the target guard is ENABLED** ⇒ the
     mutation is **REFUSED**, and the raised error is the **target guard's own** (its exact
     `RAISE` text and SQLSTATE, or its own constraint name). This proves the target guard is
     sufficient on its own, with no neighbour able to be mistaken for it.

   **A single probe that disables only the target while a neighbour still refuses the statement
   proves nothing and is not acceptable** — it is exactly the v3 defect. Each pair must name:
   the **target** (the specific clause, constraint, or trigger), the **neighbour(s)**, exactly
   **what is disabled in each half**, the **expected SQLSTATE / `RAISE` text** (or COMMIT plus
   the asserted harm), and the **restore + re-assert**. Whether a neighbour independently
   refuses is a **measured** fact, not an assumption: a row is converted to a pair only on a
   live PostgreSQL 16 result, and a row the neighbour does **not** independently refuse stays
   single-guard under rules 1–3 (§5.2.a.1 records both outcomes). A "neighbour" may be another
   object (a trigger, a UNIQUE, a privilege, RLS) **or another clause of the same function**.
9. **A writer whose target row may not yet exist is proven with a TWO-WRITER PROBE, never with
   a single-writer path test** (v4.1, owner ruling 2026-08-24; **standing — it applies to every
   later slice and to any later audit of this one**). `SELECT … FOR UPDATE` on an **absent** row
   locks nothing, so a single-session test can execute the entire first-write path, pass, and
   still leave the writer racy — which is precisely what happened to the approved v4 sequence
   (§OD-11, Sol code REJECT `380cc908-3745-46fb-b762-504f4e1bd4fd`). For every writer of this
   class the plan must name a probe that:
   - runs **two concurrent sessions**, each in its **own transaction on its own connection**, at
     the **production entry point's isolation level** (named in the probe, not assumed);
   - gives each session its **own** authorization row — two distinct allowed `admin_actions` for
     the same tenant and project — so neither can be blamed on a shared or replayed
     authorization, and both spends must succeed;
   - starts from the **absent-row** state (no pre-existing target row), and **forces the
     interleaving** rather than hoping for it: writer 1 calls and holds its transaction open,
     writer 2 then calls and must **block**, writer 1 commits, writer 2 proceeds;
   - asserts **that writer 2 actually waited, and where** — its call is still pending immediately
     before writer 1 commits, **and** an observer session shows it blocked at the **write**
     (the unique-index / `transactionid` wait, blocked by writer 1's pid), not at the existence
     probe. A correct final state reached without contention proves nothing about serialization,
     and a wait at the probe would mean the pre-write window was never entered;
   - **enters the pre-write window by construction, not by timing.** The interleaving must be one
     in which **both** writers complete the existence probe against an absent row before either
     commits. Holding writer 1 open until writer 2 is confirmed pending achieves this, because a
     tuple invisible to writer 2's snapshot cannot be row-locked (§OD-11 R6), so writer 2's probe
     cannot wait on writer 1's uncommitted row. A third-session `LOCK TABLE … EXCLUSIVE` followed
     by a dual start does **not** achieve it: once the table lock is released, one writer can
     finish its probe and its write before the other probes at all. The probe must say which
     mechanism it relies on and why;
   - asserts the **full derived record**, not merely the absence of an exception: exactly one
     target row, one ledger row per writer, exactly one ledger row whose "previous" column is
     NULL and which belongs to the **first** writer, the other ledger row citing the first
     writer's value, and the stored value equal to the **last committed** writer's;
   - carries a **rule-1 mutation in its concurrency form**: reinstall the **previous** (racy)
     body — the body and **nothing else**, with no barrier, sleep or hook added to make the race
     reachable — re-run **the identical scenario under the identical interleaving**, and assert
     the **falsified record** appears; here the harm is not a refused statement but a ledger that
     lies. Then restore the production body, re-assert it by the same comparison the §5.2.a.1
     pairs use, and re-run the probe green. If the mutation comes back green, the interleaving is
     wrong and the probe — not the fix — is what must be repaired.

   A "no exception was raised" assertion, a sequential two-call test, or a probe that cannot
   demonstrate the old sequence failing is **not** evidence for this class and is a REJECT.

Global: use `DISABLE TRIGGER` / `DROP CONSTRAINT` / `DISABLE ROW LEVEL SECURITY` /
`CREATE OR REPLACE FUNCTION` on the **named** object only; never
`SET CONSTRAINTS ALL DEFERRED`, never a session-wide `session_replication_role`, and always
restore in a `finally`. `TRUNCATE` cases run inside a transaction that is rolled back. Where
the mutation is **pure DDL** (drop a constraint, disable a trigger, disable RLS, replace a
function body), restoring by rolling back the enclosing transaction is preferred over an
explicit `finally`, because PostgreSQL DDL is transactional and a rollback cannot leak a
half-restored object; the probe must still **re-assert the guard's presence and its refusal
afterwards**, so a rollback is never a substitute for proving the restore.

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

**Restructured in v4 (owner ruling 2026-08-24).** Five of this section's rows are
**overlapping-guard** cases under the new §5.0 rule 8 and have moved to **§5.2.a.1** as named
probe **pairs**: `P-writer-requires-allowed-action`, `P-writer-requires-policy-kind`,
`P-writer-guc-unset`, `P-writer-no-existing-policy`, and `P-tighten-changes-level`. The table
below keeps only the rows that stay single-guard under §5.0 rules 1–3: the two privilege
denials (single-guard per the owner's ruling, not measured) and the four rows a **live
measurement** shows the neighbour does **not** independently refuse — the UNIQUE-constraint
spend and the three monotonicity cases.

| Probe | Guard under test | Refusal payload (otherwise fully valid) | Mutation that must commit |
|---|---|---|---|
| **P-priv/autonomy_policies/INSERT** | privilege: `uaid_app` has no INSERT on `autonomy_policies` | as `uaid_app`, a well-formed INSERT for its own tenant/project ⇒ `42501` naming `autonomy_policies` | `GRANT INSERT ON public.autonomy_policies TO uaid_app`; the same INSERT commits (RLS passes: the GUC is set); `REVOKE INSERT`, re-assert `42501` |
| **P-priv/autonomy_policies/UPDATE** | privilege: no UPDATE | as `uaid_app`, `UPDATE autonomy_policies SET autonomy_level=5` on its own admin-seeded row ⇒ `42501` | `GRANT UPDATE …`; the same UPDATE commits; `REVOKE UPDATE`, re-assert. No other guard exists on this table, so the grant alone is the whole mutation |
| **P-writer-spends-action-atomically** (renames v2's P-writer-requires-unspent-action; absorbs v2's P-change-action-reuse) | `uq_admin_policy_changes_action`, the sole spend authority (§OD-11 step 3.8) | one **allowed** action; call the writer once (asserting it returned both ids and the policy moved to level 2); call it again with the **same** `admin_action_id` and a different level ⇒ `RAISE 'admin_action_already_spent'`, **and** the policy row still reads level 2 and `admin_policy_changes` still holds exactly one row for that action — the refused replay unwound its own policy write (fact 0.1.14) | `ALTER TABLE public.admin_policy_changes DROP CONSTRAINT uq_admin_policy_changes_action`; the identical second call now **commits**, the policy moves again, and a second ledger row appears for the same action — i.e. the authorization is replayable exactly when this constraint is absent. The mutated half runs inside a transaction that is **rolled back**, which restores the constraint and removes the forged ledger row together (the table is DELETE-blocked, so a rollback is the only clean undo); the probe then re-asserts the constraint in `pg_constraint` and re-asserts the refusal. **Measured single-guard (v4, probe C7):** with `uq_admin_policy_changes_action` dropped and `admin_policy_changes_guard` still **enabled**, the replay **committed** and a second ledger row appeared for the same action (`chg_rows = 2`) — the neighbour does **not** independently refuse it, because the replay action is `set_autonomy_policy` (so the guard's tighten clause is inapplicable) and the policy upsert precedes the ledger INSERT (so the guard's level clause is satisfied). This row therefore stays single-guard under §5.0 rules 1–3, as the owner's ruling directs |
| **P-tighten-relax-empty-map** | §OD-12 monotonicity | stored `overrides = {"run_tests": {"allow": false}}` at level 2; an **allowed** `tighten_autonomy_overrides` action; call with `p_autonomy_level=2`, `p_overrides='{}'` ⇒ `RAISE 'tighten_would_relax_overrides'` | `CREATE OR REPLACE` with the monotonic clause removed; the same call commits and `overrides` becomes `{}` (Sol's exact re-enable case); restore and re-assert the refusal |
| **P-tighten-relax-drops-disable** | same | stored `{"run_tests": {"allow": false}}` → `{"run_tests": {"min_level": 3}}` (key kept, disable dropped) ⇒ same `RAISE` | same |
| **P-tighten-relax-lowers-min-level** | same | stored `{"deploy_staging": {"min_level": 4}}` → `{"deploy_staging": {"min_level": 3}}` ⇒ same `RAISE` | same |

**Why the three `P-tighten-relax-*` rows stay single-guard (measured, v4 probe C6).** With the
monotonic clause removed and `admin_policy_changes_guard` still **enabled**, the relaxing call
**committed** (`pol_rows = 1`, `chg_rows = 1`, `overrides` became `{}`): the requested level
equals the stored level, so the guard's level clause and its tighten clause are both satisfied
and the guard has nothing to say about the override map. The neighbour does not independently
refuse these, so per the owner's ruling they are **not** converted.

#### 5.2.a.1 Overlapping-guard probe pairs (v4, §5.0 rule 8)

**Why this subsection exists.** Sol's v3 REJECT
(`369abc89-7144-4f42-b810-72f6ec367a64`) found that §5.2.a's four writer-function mutations
"remain masked by `admin_policy_changes_guard`": removing the writer clause alone still left the
statement refused, by the ledger guard, so those mutations never demonstrated a reachable
mutation and `P-writer-no-existing-policy` did not close v2 defect 3. The owner ruled the
finding correct and the standard incomplete, and amended it — §5.0 rule 8. Each case below is
therefore **two named probes**, and neither half alone is acceptable.

**Which rows overlap was measured, not assumed.** Measured 2026-08-24 against the live
`postgres:16` container `uaid_os-postgres-1` (**PostgreSQL 16.14**) in a throwaway database
(`s63v4_tmp`, created and dropped in the same session, no app database touched), whose schema
reproduces the §OD-11 step-3 writer body and the §3.3:938–944 `admin_policy_changes_guard`
clauses in shape, each mutation expressed as the removal of the named clause(s) only. Results:

| Case | Target clause | Target disabled, neighbour(s) ENABLED | Target **and** neighbour(s) disabled | Verdict |
|---|---|---|---|---|
| C1 | writer step 3.3 `decision='allowed'` | REFUSED — the guard's own decision clause | **COMMITTED** (`pol_rows=1 chg_rows=1`) | **pair** |
| C2 | writer step 3.4 `action_kind IN (…)` | REFUSED — the guard's own kind clause | **COMMITTED** (`pol_rows=1 chg_rows=1`) | **pair** |
| C3 | writer step 3.1 GUC clause | **COMMITTED** — the guard stayed silent | **COMMITTED** (`pol_rows=1 chg_rows=1`) | **pair by ruling**; the ledger guard is **not** an independent refuser here (the RLS layer is — see the pair) |
| C4 | writer step 3.6 `no_existing_policy` | REFUSED **twice over**: first `tighten_may_not_change_level` (the writer's *own* next clause, because `previous_autonomy_level` is NULL), then, with that also removed, the guard's tighten clause | **COMMITTED** (`pol_rows=1 chg_rows=1`) | **pair, two neighbours** |
| C5 | writer step 3.6 `tighten_may_not_change_level` | REFUSED — the guard's own tighten clause | **COMMITTED** (`pol_rows=1 chg_rows=1`) | **pair** |
| C6 | writer step 3.6 monotonic clause | **COMMITTED** — guard silent | n/a | single-guard, **not** converted (§5.2.a) |
| C7 | `uq_admin_policy_changes_action` | **COMMITTED** (`chg_rows=2`) — guard silent | n/a | single-guard, **not** converted (§5.2.a) |

C4 is a finding beyond the REJECT's own wording and is load-bearing: an implementation that
removes **only** the existence clause is still refused by the writer's next clause, so the
`/reachable` half must remove both. Every measurement above is a harness result, not a claim
about the real `0062` objects; **the builder must reproduce each pair against the real objects**,
and a pair that does not reproduce is a defect to report, never a licence to drop a half.

**Conventions for all five pairs.**

- The call under test is `SELECT * FROM public.admin_write_autonomy_policy(...)` executed **as
  `uaid_app`** (it holds `EXECUTE`); only the setup, the trigger disable, and the seeding run as
  admin. Every payload is otherwise fully valid: same tenant, same project, unspent action, a
  real `autonomy_policies` row where the case calls for one.
- "Disable the neighbour" means exactly
  `ALTER TABLE public.admin_policy_changes DISABLE TRIGGER admin_policy_changes_guard`, and
  nothing wider. "Disable the target" means
  `CREATE OR REPLACE FUNCTION public.admin_write_autonomy_policy(...)` with **only** the named
  clause(s) removed and the rest of the body byte-identical to `guards_sql.py`. Never
  `SET CONSTRAINTS ALL DEFERRED`, never `session_replication_role`.
- Every `RAISE EXCEPTION '<text>'` in both the writer and the guard carries SQLSTATE **`P0001`**
  (plpgsql's default `raise_exception`), so **the message text is the discriminator**. The
  builder gives the four `admin_policy_changes_guard` clauses message texts **distinct** from the
  writer's (an `admin_policy_change_*` prefix), so that a `/own-reason` assertion on the writer's
  text cannot be satisfied by the guard even if a future edit re-enables it.
- Both halves are pure DDL mutations, so each runs inside a transaction that is **rolled back**
  (§5.0 global rule). After restore, every pair re-asserts:
  `pg_get_functiondef('public.admin_write_autonomy_policy'::regproc)` equals the
  `guards_sql.py` text; `tgenabled = 'O'` for `admin_policy_changes_guard`; and the **unmutated**
  call is refused again with the target's own message. A rollback is never accepted as a
  substitute for proving the restore (A-triggers-enabled is the backstop).
- Where the rest of this plan cites a converted probe by its base name — `P-writer-guc-unset`,
  `P-writer-requires-allowed-action`, `P-writer-requires-policy-kind`,
  `P-writer-no-existing-policy`, `P-tighten-changes-level` (§0.2, §0.4, §OD-2, §OD-11, §5.3, §9)
  — that name now denotes **the pair**, and **both halves are required** for the claim it backs.

---

**Pair 1 — `P-writer-requires-allowed-action`** (was §5.2.a row 3; measured C1)

- **Target guard:** the `decision = 'allowed'` clause of `admin_write_autonomy_policy`
  (§OD-11 step 3.3), whose refusal is `admin_action_not_allowed`.
- **Neighbour:** `admin_policy_changes_guard` on `public.admin_policy_changes`
  (§3.3:938–944), **decision clause** — it re-reads the referenced `admin_actions` row and
  refuses a ledger row citing a non-`allowed` action.
- **Shared payload:** an `admin_actions` row with `decision='refused_insufficient_role'`,
  `action_kind='set_autonomy_policy'`, same tenant + project, **unspent**; a real
  `autonomy_policies` row at level 2; `app.current_tenant` set.

| Half | Disabled | Expected |
|---|---|---|
| **`/reachable`** | the writer's `decision='allowed'` clause **and** `admin_policy_changes_guard` | **COMMITS.** Asserted harm: the `autonomy_policies` row's `autonomy_level`/`overrides` moved, **and** an `admin_policy_changes` row now exists citing an action that was **refused** — a policy changed on a refused authorization, with a ledger that endorses it (measured: `pol_rows=1 chg_rows=1`) |
| **`/own-reason`** | `admin_policy_changes_guard` **only**; the writer clause **ENABLED** (production body) | **REFUSED** with SQLSTATE `P0001` and message exactly `admin_action_not_allowed`. With the guard off, the guard's own decision message cannot appear, so the refusal is provably the writer's |

- **Restore + re-assert:** roll back both halves; assert `pg_get_functiondef` matches
  `guards_sql.py` and `tgenabled='O'`; re-run the unmutated call and assert
  `admin_action_not_allowed` again.

---

**Pair 2 — `P-writer-requires-policy-kind`** (was §5.2.a row 4; measured C2)

- **Target guard:** the `action_kind IN ('set_autonomy_policy','tighten_autonomy_overrides')`
  clause (§OD-11 step 3.4), refusal `admin_action_not_policy_kind`.
- **Neighbour:** `admin_policy_changes_guard`, **kind clause** (§3.3:941).
- **Shared payload:** an `allowed` `admin_actions` row whose `action_kind` is a **non-policy**
  value; a real policy row at level 2; GUC set. **Setup layer disclosed (§5.0 rule 4):** the
  `ck_admin_actions_*` kind CHECK binds the vocabulary, so the row is written **as admin** with
  that named CHECK dropped for that one statement and re-added immediately — this is stated in
  the docstring, and the dropped CHECK is *not* the object under test in either half.

| Half | Disabled | Expected |
|---|---|---|
| **`/reachable`** | the writer's kind clause **and** `admin_policy_changes_guard` | **COMMITS.** Asserted harm: an authorization for a **non-policy** action moved a policy and produced a ledger row (measured: `pol_rows=1 chg_rows=1`) |
| **`/own-reason`** | `admin_policy_changes_guard` **only**; the writer's kind clause **ENABLED** | **REFUSED**, `P0001`, message exactly `admin_action_not_policy_kind` |

- **Restore + re-assert:** roll back; re-add the `ck_admin_actions_*` kind CHECK and assert it
  is back in `pg_constraint`; assert the function body and `tgenabled='O'`; re-assert the
  refusal.

---

**Pair 3 — `P-writer-guc-unset`** (was §5.2.a row 6; measured C3)

- **Target guard:** §OD-11 step 3.1 — the refusal to **infer** a tenant
  (`v_tenant := NULLIF(current_setting('app.current_tenant', true), '')::uuid`; NULL ⇒
  `tenant_guc_unset`). The function must never fall back to the tenant on the action row.
- **Neighbours, honestly named:**
  1. **RLS** on `public.autonomy_policies`, `public.admin_actions`, and
     `public.admin_policy_changes` — the real independent refuser here, because with no
     `app.current_tenant` the `tenant_isolation` policy refuses every one of those reads and
     writes regardless of the writer's own clause. This is the layer v3 already disclosed and
     disabled in setup under §5.0 rule 4, and it stays disabled in **both** halves.
  2. `admin_policy_changes_guard`. **Measured (C3): with RLS out of the way, this trigger did
     NOT independently refuse the fallback-mutated call — it committed.** The pair still
     disables it in the `/reachable` half, per the owner's ruling that all four writer-function
     mutations be pairs; the plan does not claim the trigger blocks this case.
- **Shared payload:** an `allowed`, policy-kind, unspent action; a real policy row at level 2;
  **no** `app.current_tenant` set; RLS disabled (and un-FORCEd) on the three tables in setup,
  disclosed in the docstring.

| Half | Disabled | Expected |
|---|---|---|
| **`/reachable`** | RLS on the three tables (setup) **and** the writer's step 3.1 clause — replaced by the tempting fallback "take the tenant from the action row", nothing else changed — **and** `admin_policy_changes_guard` | **COMMITS.** Asserted harm: a policy row exists for a tenant the caller **never proved** it holds, plus a ledger row endorsing it (measured: `pol_rows=1 chg_rows=1`; consistent with fact 0.1.13's harness) |
| **`/own-reason`** | RLS on the three tables (setup) **and** `admin_policy_changes_guard`; the writer's step 3.1 clause **ENABLED** | **REFUSED**, `P0001`, message exactly `tenant_guc_unset` — with both neighbours out of the way, the refusal can only be the writer's own GUC clause |

- **Restore + re-assert:** roll back; then `ENABLE ROW LEVEL SECURITY` **and**
  `FORCE ROW LEVEL SECURITY` on all three tables and assert `relrowsecurity` **and**
  `relforcerowsecurity` are true for each; assert the function body and `tgenabled='O'`;
  re-assert `tenant_guc_unset`.

---

**Pair 4 — `P-writer-no-existing-policy`** (was §5.2.a row 7 — **the row named in the v3
REJECT**; measured C4)

- **Target guard:** §OD-11 step 3.6's existence clause — a `tighten_autonomy_overrides` action
  requires a stored `autonomy_policies` row — refusal `no_existing_policy`.
- **Neighbours, both measured, both independent:**
  1. **The writer's own next clause**, `tighten_may_not_change_level`: with no stored row
     `v_previous_level` is NULL, so `IS DISTINCT FROM p_autonomy_level` is true and this clause
     refuses on its own. **This is why v3's "only the existence clause removed" mutation could
     not commit even before the trigger was reached** — the neighbour is inside the same
     function.
  2. `admin_policy_changes_guard`'s **tighten clause** (§3.3:943–944), which requires
     `previous_autonomy_level = new_autonomy_level`: with the derived
     `previous_autonomy_level` NULL, it refuses.
- **Shared payload:** a project with **no** `autonomy_policies` row; an `allowed`
  `tighten_autonomy_overrides` action, same tenant + project, unspent; a call with
  `p_autonomy_level` set and a non-empty monotone map (monotonicity is vacuously satisfied
  against an absent row, so the monotonic clause is never the refuser in either half).

| Half | Disabled | Expected |
|---|---|---|
| **`/reachable`** | **both** writer clauses — the existence clause **and** `tighten_may_not_change_level` — **and** `admin_policy_changes_guard` | **COMMITS.** Asserted harm: a policy row is **created** by "tightening" — a first-time grant of an autonomy level nobody ever set, with a ledger row whose `previous_autonomy_level` is NULL endorsing it (measured: `pol_rows=1 chg_rows=1`). This is exactly the harm the existence clause prevents |
| **`/own-reason`** | `admin_policy_changes_guard` **and** the writer's `tighten_may_not_change_level` clause; the **existence clause ENABLED** | **REFUSED**, `P0001`, message exactly `no_existing_policy`. Measured consistency: with everything enabled the same payload also yields `no_existing_policy` (C4 first row), because the existence clause is evaluated first — so the pair proves both that the clause fires in production order and that it is sufficient with both neighbours removed |

- **Restore + re-assert:** roll back; assert the function body equals `guards_sql.py` (both
  clauses back) and `tgenabled='O'`; re-assert `no_existing_policy` on the unmutated call.

---

**Pair 5 — `P-tighten-changes-level`** (was §5.2.a row 11; **converted in v4** because measured
C5 shows the neighbour independently refuses it, exactly as the owner anticipated)

- **Target guard:** §OD-11 step 3.6's level-equality clause — a tighten may not move
  `autonomy_level` — refusal `tighten_may_not_change_level`.
- **Neighbour:** `admin_policy_changes_guard`'s tighten clause (§3.3:943–944),
  `previous_autonomy_level = new_autonomy_level`. With the writer clause removed, the policy is
  upserted to the new level and the ledger row carries `previous=2, new=3`, which the guard
  refuses on its own. **Measured, so this row is converted; the three `P-tighten-relax-*` rows,
  measured not to overlap (C6), are not.**
- **Shared payload:** a stored policy at level 2 with
  `overrides = {"run_tests": {"allow": false}}`; an `allowed` `tighten_autonomy_overrides`
  action, same tenant + project, unspent; the call passes `p_autonomy_level = 3` with the **same
  (monotone) map**, so the monotonic clause cannot be the refuser.

| Half | Disabled | Expected |
|---|---|---|
| **`/reachable`** | the writer's level-equality clause **and** `admin_policy_changes_guard` | **COMMITS.** Asserted harm: a "tighten" **raised** the project's autonomy level from 2 to 3 — a widening of authority under a restriction-only action kind — and the ledger recorded `previous=2, new=3` as if that were legitimate (measured: `pol_rows=1 chg_rows=1`, stored level now 3) |
| **`/own-reason`** | `admin_policy_changes_guard` **only**; the writer's level-equality clause **ENABLED** | **REFUSED**, `P0001`, message exactly `tighten_may_not_change_level` |

- **Restore + re-assert:** roll back; assert the function body and `tgenabled='O'`; re-assert
  the refusal, and assert the stored `autonomy_level` is still 2.

#### 5.2.a.2 Concurrency probe (v4.1, §5.0 rule 9)

**Why this subsection exists.** Sol's code REJECT (`380cc908-3745-46fb-b762-504f4e1bd4fd`) of
`ddb3869` measured two authorized writers racing on the **first** policy write for a project:
the final stored level was `2` and the two ledger rows were `[(NULL, 3), (NULL, 2)]` — the second
write overwrote level 3 while recording `previous_autonomy_level = NULL`. The build was faithful
to the approved v4 sequence, so the defect is this plan's: **`SELECT … FOR UPDATE` on an absent
row locks nothing.** §OD-11 step 3.7 is amended, and this probe is the standing proof that it
stayed fixed.

---

**`P-writer-concurrent-first-write`**

- **Target under test:** §OD-11 step 3.7 as a whole — the serialize-then-lock-then-read sequence
  and the rule that `previous_autonomy_level` is derived **after** the row is guaranteed to
  exist. This is not a refusal probe: the correct outcome is that **both** calls succeed and the
  **record is truthful**.
- **Isolation:** the production path's own — `apply_policy_change_in_scope` opens
  `tenant_scope(ctx)` with no `isolation_level`, so **READ COMMITTED**. The probe states this in
  its docstring; it does not silently pick an isolation the product does not use. (§OD-11's
  isolation note records the measured `40001` fail-closed behaviour at REPEATABLE READ; a
  separate case for it is optional and, if written, must assert `40001` and **no** ledger row —
  never a "wrong previous".)
- **Setup, committed before either writer starts** (so both connections can see it — the
  §OD-14 runtime-mode precondition applies unchanged): one organization, one tenant, one project;
  an **active `tenant_admin`** grant for the test principal; **two distinct `allowed`
  `set_autonomy_policy` `admin_actions` rows** for that same tenant **and** project, both
  **unspent**; and **no `autonomy_policies` row** for the project (asserted, not assumed).
- **Execution.** Two `uaid_app` sessions, each on its **own** connection inside its **own**
  `tenant_scope`, each setting `app.current_tenant` to that tenant, each calling the production
  writer once — `apply_policy_change(session, ctx, …)` or, equivalently,
  `SELECT * FROM public.admin_write_autonomy_policy(...)` — with its **own** `admin_action_id`:
  **W1 → level 3**, **W2 → level 2**. The interleaving is **forced, not raced**, in three ordered
  steps, each gated on an observation rather than on a sleep:

  1. **W1 calls the writer and holds its transaction open.** Signal an `asyncio.Event` once the
     call **returns**; W1 does not commit yet.
  2. **W2 calls the writer.** It **must block**. Confirm this **positively** before releasing W1
     — see assertion 6 — rather than assuming it from timing.
  3. **W1 commits.** W2's call then returns and W2 commits.

  Both call-return instants and W1's commit instant are recorded.

  **Why this window is the TOCTOU window** (state this in the probe's docstring, because the
  contrary reading is plausible and wrong). It is tempting to think that once W1's call has
  returned, W1's uncommitted `autonomy_policies` row makes W2 wait at its step-3.5
  `SELECT … FOR UPDATE`, so that W2 would observe the row and both bodies would behave. **It does
  not.** A tuple that is invisible to W2's snapshot cannot be row-locked, so W2's step-3.5 probe
  finds **no row and does not wait** — measured, R6: `SELECT … FOR UPDATE` against another
  session's uncommitted insert returned 0 rows in 0.252 ms. W2 therefore reaches its write with
  `v_found = false` and, under the v4 body, with `v_previous_level` already frozen at `NULL`.
  Because W1 is held open until W2 is confirmed pending, **both writers completing the empty
  existence probe before either commits is guaranteed by construction, not by luck** — which is
  exactly Sol's race. The first thing that can make W2 wait is the unique index (R6: the same
  key's `INSERT … ON CONFLICT` blocked 2916.840 ms), which is why this single interleaving both
  reproduces the defect on the mutated body (R7) and proves the fix on the production body (R8).
  A `LOCK TABLE … EXCLUSIVE` third session plus a dual start is **not** used and would be weaker:
  after the table lock is released, one writer can complete its probe **and** its INSERT before
  the other runs its probe, collapsing the window non-deterministically. No `pg_sleep`,
  advisory-lock wait or other barrier is added to **either** body.

  **Expected (all six, per §5.0 rule 9):**

  1. **Both calls succeed**, each returning a non-NULL `o_autonomy_policy_id` and
     `o_admin_policy_change_id`, on **two distinct** `admin_action_id`s — i.e. **both spends
     succeed**, and `uq_admin_policy_changes_action` refused neither.
  2. Exactly **one** `autonomy_policies` row exists for `(tenant, project)`, and **both** calls
     returned that **same** `o_autonomy_policy_id` — the race produced one policy, not two.
  3. Exactly **one** `admin_policy_changes` row has `previous_autonomy_level IS NULL`, and it is
     **W1's** row (`admin_action_id` = W1's), with `new_autonomy_level = 3`.
  4. The **other** row is W2's, with `previous_autonomy_level = 3` — W1's `new_autonomy_level` —
     and `new_autonomy_level = 2`.
  5. `autonomy_policies.autonomy_level = 2` — the **last committed** writer's level — and
     exactly **two** ledger rows exist for that project.
  6. **W2 provably waited, at the write and not at the probe.** Two parts, both required, because
     a green final state reached without W2 ever blocking would not prove serialization and a
     green state reached because W2 blocked *at its existence probe* would not prove that the
     TOCTOU window was entered:
     - **(a) Pending.** W2's writer call is **still pending** at the instant immediately before
       W1 commits (an awaited task that has not completed). A wall-clock comparison showing W2's
       return instant after W1's commit instant is a secondary check, not the assertion.
     - **(b) Blocking site.** While W2 is pending and W1 is still open, a **third observer
       session** finds W2's backend with `state = 'active'`,
       `wait_event_type = 'Lock'`, `wait_event = 'transactionid'` and
       `pg_blocking_pids(pid)` containing **W1's** pid, and an **ungranted** `transactionid`
       lock in `pg_locks` — the unique-index wait of step 3.7(b), which is only reachable
       *after* an empty step-3.5 probe. Measured green as R8 and, with the mutated body, R7.

- **Mutation (§5.0 rule 1 in its concurrency form).** Reinstall the **approved-v4 body** — the
  step-3.5 `FOR UPDATE` read followed by `INSERT … ON CONFLICT (tenant_id, project_id) DO UPDATE`
  with `previous_autonomy_level` taken from that pre-insert read — via
  `CREATE OR REPLACE FUNCTION public.admin_write_autonomy_policy(...)` and **nothing wider**;
  re-run **the identical two-writer scenario, with the same three-step interleaving and the same
  observer** — the mutation replaces the body and changes nothing about how the probe is driven.
  It **must reproduce the defect**: **two** ledger rows with `previous_autonomy_level IS NULL`
  (`[(NULL, 3), (NULL, 2)]`) while the stored level is `2` — the harm here is a **ledger that
  lies**, not a refused statement. Measured twice: in the first v4.1 harness (R1) and again under
  this probe's exact specified interleaving (R7), and by Sol on the real build. A mutation that
  *cannot* reproduce it would mean the probe is not exercising the sequence and is itself the
  defect (§5.0 rule 1), so if the builder's run of the mutation comes back green, that is a
  **blocker to report, not a pass**.

  **No barrier is added to make the race reachable.** The mutated body is v4's sequence and
  nothing else — no `pg_sleep`, no advisory-lock wait, no test-only hook, and therefore nothing
  that could be mistaken for a product feature or a GUC the production body reads. The race is
  reachable because W1 is held open until W2 is confirmed pending and W2's step-3.5 probe cannot
  wait on W1's invisible row (R6). This is stated so that a reviewer does not have to infer it.
- **Restore + re-assert.** Roll back the DDL (pure-DDL mutation, §5.0 global rule), then assert
  the installed body matches the production body **by the same comparison the §5.2.a.1 pairs
  already use** — `pg_get_functiondef('public.admin_write_autonomy_policy'::regproc)` against the
  text generated from `app/admin/policy_sql.py`, one source of truth, no new convention — and
  **re-run the probe green**. A restore is not proven by the rollback alone.
- **Sibling case `P-writer-concurrent-first-write/tighten-no-orphan`** (the "measure if needed"
  half of the owner's ruling, measured as v4.1 R3 and re-measured unchanged against the v4.1 body
  after R8: `probe_found=f`, refused `no_existing_policy`, policy rows `0 → 0` across the refusal
  **and** after the enclosing commit, ledger rows `0`). **Deliberately single-session, and §5.0
  rule 9 does not apply to it:** rule 9 governs writers that may *create* the row, and this case
  asserts that this path creates **nothing**, so a second writer would add no window — there is no
  row for two sessions to race for. With **no**
  `autonomy_policies` row for the project and an `allowed` `tighten_autonomy_overrides` action,
  the call is refused with SQLSTATE `P0001` and message exactly `no_existing_policy`, **and**
  `autonomy_policies` still holds **zero** rows for that project and `admin_policy_changes`
  **zero** rows. This is what proves step 3.6 precedes step 3.7: the serialize-INSERT never
  creates a row that a tighten then refuses, so the fix cannot leave an orphan policy. Its
  mutation is the §5.2.a.1 Pair 4 `/reachable` mutation (both writer clauses plus the ledger
  guard removed), which is already required to **commit** — so the "absent guard would commit"
  obligation is discharged by a probe this plan already carries, and is cross-referenced rather
  than duplicated.

**Honest scope of this probe.** It proves that **this** writer serializes **first creation** of
**this** row on **this** PostgreSQL 16 build at READ COMMITTED, and that the ledger it derives is
truthful for two writers. It does **not** prove there is no other race anywhere in the slice, does
not prove anything about crash-recovery, and does not make the ledger a human signature. What it
removes is one specific, measured falsification.

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

The three `admin_policy_changes_guard` cases run **as admin** (§9): after v3's defect-1 change
`uaid_app` holds no `INSERT` on that table, so a runtime attempt would prove the grant, not the
trigger — and that outer layer is proven separately by P-priv/admin_policy_changes/INSERT.
These probes exist because the guard must also bind the **owner** path, which the definer
function cannot police.

| Probe | Guard under test | Refusal payload | Mutation that must commit |
|---|---|---|---|
| **P-change-refused-action** | `admin_policy_changes_guard` | reference an `admin_actions` row with `decision='refused_insufficient_role'`; every FK/CHECK satisfied and `new_autonomy_level` equal to the real policy level ⇒ `RAISE` on the decision clause | `DISABLE TRIGGER admin_policy_changes_guard`; same INSERT commits; restore |
| **P-change-level-mismatch** | same | referenced action is `allowed`; the real level is 3; record `new_autonomy_level=2` (in range, so the 0–5 CHECK cannot mask it) ⇒ `RAISE` on the level clause | same |
| **P-change-tighten-level-moved** | same | `tighten_autonomy_overrides`, `previous_autonomy_level=2`, `new_autonomy_level=3` where the policy really holds 3 (level clause passes) ⇒ `RAISE` on the tighten clause | same |
| **P-grant-insert-status** (new in v3, defect 3) | `admin_role_grants_guard`, INSERT clause | as **admin**, INSERT an otherwise perfectly valid grant with `status='revoked'` ⇒ `RAISE` on the born-active clause. The `status` CHECK **permits** `'revoked'`, so it cannot be the refuser, and no FK/UNIQUE is touched | `ALTER TABLE public.admin_role_grants DISABLE TRIGGER admin_role_grants_guard`; the identical INSERT commits, creating a grant with no `role_granted` history — which is why the clause exists; restore, assert `tgenabled='O'`, re-assert the `RAISE` |
| **P-grant-update-widen** | `admin_role_grants_guard`, UPDATE clause | as **admin**: UPDATE a revoked grant back to `status='active'` ⇒ `RAISE`; and UPDATE `admin_role` on an active grant ⇒ `RAISE` (two cases, one trigger) | `DISABLE TRIGGER admin_role_grants_guard`; each same UPDATE commits; restore |

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

Family **P-priv/`<table>`/`<privilege>`**, **13 cases** in v3 (12 in v2, plus
`admin_policy_changes/INSERT`), all executed as `uaid_app` via `rls_engine`, each
asserting SQLSTATE `42501` naming that table, each mutation granting **that** privilege on
**that** table (plus, where noted, disabling the one named trigger that would otherwise mask
the commit), then re-running the identical statement, then `REVOKE` + re-assert:

Per §5.0 rule 7, every seeded row in this family is an **unreferenced** row, so no FK
`RESTRICT` can be mistaken for a privilege denial on the two parent tables.

| Case | Statement | Extra mutation needed to reach commit |
|---|---|---|
| `admin_role_grants/INSERT` | INSERT a well-formed active grant (throwaway principal, so the residue is inert — the table is DELETE-blocked by design and must not be cleaned up by DELETE) | none |
| `admin_role_grants/UPDATE` | UPDATE an admin-seeded active grant to `status='revoked'` (the direction the guard permits, so the guard cannot mask the grant) | none |
| `admin_role_grants/DELETE` | DELETE an admin-seeded grant that **no** `tenant_admin_events` row references (rule 7) | also `DISABLE TRIGGER admin_role_grants_no_delete` |
| `admin_actions/UPDATE` | UPDATE `decision` on an admin-seeded row | also `DISABLE TRIGGER admin_actions_no_update_delete` |
| `admin_actions/DELETE` | DELETE that row, seeded **unspent** so no `admin_policy_changes` row references it (rule 7) | also `DISABLE TRIGGER admin_actions_no_update_delete` |
| `admin_policy_changes/INSERT` (new in v3, defect 1) | INSERT a fully valid ledger row for a real allowed action ⇒ `42501`, proving the runtime role cannot record a spend, let alone forge one, outside `admin_write_autonomy_policy` | `GRANT INSERT ON public.admin_policy_changes TO uaid_app`; the identical INSERT commits (the guard clauses are all satisfied, so the privilege was the only obstacle); `REVOKE INSERT`, re-assert `42501` |
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
the named trigger's own `RAISE`, mutates **that** table's **that**-statement trigger, and runs
inside a transaction that is rolled back.

**Rebuilt in v3 (defect 4).** Sol's live `0A000` is reproduced in fact 0.1.15: on the two FK
**parent** tables a single-table `TRUNCATE` never reaches the trigger, so v2's two cases were
false in both directions — the unmutated failure was the FK, and the mutation could not commit.
The DELETE cases are additionally re-specified to seed **unreferenced** rows (rule 7).

| Case | Statement under test | Setup layer disclosed | Mutation that must commit |
|---|---|---|---|
| `admin_role_grants/DELETE` | DELETE an unreferenced grant | none | `DISABLE TRIGGER admin_role_grants_no_delete` |
| `admin_role_grants/TRUNCATE` | `TRUNCATE public.admin_role_grants, public.tenant_admin_events;` — the ordered two-table form, so the inbound `fk_tae_grant_identity` is satisfied and the trigger is the only obstacle | `tenant_admin_events_no_truncate` is **disabled in setup**, so the surviving `RAISE` provably names `admin_role_grants` (measured: fact 0.1.15) | additionally `DISABLE TRIGGER admin_role_grants_no_truncate`; the identical statement then commits (measured: both tables emptied); restore both triggers, assert `tgenabled='O'` on each, ROLLBACK |
| `admin_actions/UPDATE` | UPDATE `decision` | none | `DISABLE TRIGGER admin_actions_no_update_delete` |
| `admin_actions/DELETE` | DELETE an **unspent** action (no ledger child) | none | same trigger, re-running the DELETE |
| `admin_actions/TRUNCATE` | `TRUNCATE public.admin_actions, public.admin_policy_changes;` | `admin_policy_changes_no_truncate` disabled in setup | additionally `DISABLE TRIGGER admin_actions_no_truncate`; commits; restore both |
| `admin_policy_changes/{UPDATE,DELETE,TRUNCATE}` | its own statement; **no inbound FK**, so the single-table `TRUNCATE` is legitimate here | none | `admin_policy_changes_no_update_delete` / `admin_policy_changes_no_truncate` |
| `tenant_admin_events/{UPDATE,DELETE,TRUNCATE}` | its own statement; leaf table, single-table `TRUNCATE` legitimate | none | `tenant_admin_events_no_update_delete` / `tenant_admin_events_no_truncate` |

`admin_role_grants` has no UPDATE case by design (§3.1: revoke is a legal UPDATE); its UPDATE
authority is probed by P-grant-update-widen instead.

**Honest scope of the two multi-table cases.** What they prove is that *this* `TRUNCATE`
statement is refused by *that* trigger and would otherwise succeed. They do **not** claim
`TRUNCATE` is impossible: a role that can `ALTER TABLE ... DISABLE TRIGGER` — i.e. the table
owner — can always truncate, exactly as §0.5 already says about owner credentials.

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
| **P-org-status-check** (new in v3, defect 3) | `ck_organizations_status_valid` (§3.5) | as **admin** (fact 0.1.16: `uaid_app` has only SELECT here, so the owner path is the only way to reach the CHECK), `UPDATE public.organizations SET status='bogus'` on a real org ⇒ violation naming `ck_organizations_status_valid`. Nothing else constrains the column, so the name cannot be a neighbour's | `ALTER TABLE public.organizations DROP CONSTRAINT ck_organizations_status_valid`; the identical UPDATE commits and the org now holds a status the resolver's `= 'active'` test silently rejects forever — the reason the CHECK exists; re-add the constraint from the migration text and re-assert the violation |
| **P-downgrade-populated** | `populated_downgrade_sql()` | with one row in **each** of the four tables (four sub-cases, one per table, so the guard is proven on each object) `alembic downgrade 0061` fails closed with the guard's own message naming that table | **Re-specified in v3 (defect 4).** v2 said "drop that table", which is impossible for the two FK parents (fact 0.1.16: `2BP01`). The mutation is instead the **ordered guard-free sequence** of §3.6(f) executed in the same transaction with the emptiness check skipped — `DROP TABLE public.admin_policy_changes`, `public.tenant_admin_events`, `public.admin_actions`, `public.admin_role_grants`, in that order — asserting **each** statement succeeds despite the seeded rows, then `ROLLBACK`. That proves the data really would have been destroyed had the guard been absent, which is the claim the guard makes. No `CASCADE` is used anywhere: `CASCADE` would drop objects the downgrade does not own and would hide an ordering mistake |

### 5.3 Catalog / invariant assertions (not refusal probes)

These are assertions, not guards, and are labelled as such so they are never counted as
proven refusals. Where v1 claimed a probe that could only be mutated by monkeypatching a
copy, v2 demoted it here rather than pretending. **v3 moves one item the other way:** v2's
A-writer-guc is now the real refusal probe P-writer-guc-unset, because fact 0.1.13's harness
showed a mutation that does commit once the outer RLS layer is disclosed and disabled in setup.

- **A-grant-matrix** `information_schema.role_table_grants` for `uaid_app` is exactly:
  `admin_role_grants` → `{SELECT}`; `tenant_admin_events` → `{SELECT}`;
  **`admin_policy_changes` → `{SELECT}`** (no INSERT — v3 defect 1: the ledger is written only
  inside the definer function); `admin_actions` → `{SELECT, INSERT}`;
  **`autonomy_policies` → `{SELECT}`** (no INSERT, no UPDATE — the §OD-11 lock, asserted at
  the catalog as well as behaviourally). No `UPDATE`, `DELETE`, `TRUNCATE`, or `REFERENCES`
  on any Slice-63 table. `PUBLIC` has none.
- **A-writer-role** `admin_write_autonomy_policy` is `prosecdef=true`, owned by
  `policy_admin_writer`; that role is `rolsuper=false rolbypassrls=false rolcanlogin=false`;
  `information_schema.routine_privileges` shows `EXECUTE` for `uaid_app` and none for PUBLIC;
  `policy_admin_writer` holds exactly `{SELECT, INSERT, UPDATE}` on `autonomy_policies`,
  `{SELECT}` on `admin_actions`, `{SELECT, INSERT}` on `admin_policy_changes`, and **nothing**
  on `admin_role_grants`, `tenant_admin_events`, or `tenant_api_keys`.
- **A-no-ungated-upsert** (new in v3, defect 1) `AutonomyPolicyRepository` has **no** `upsert`
  attribute (`hasattr` is False), and a repo-wide scan finds no `INSERT`/`UPDATE` against
  `autonomy_policies` or `admin_policy_changes` outside `0062` and the two guard/DDL modules —
  so the gated writer is not merely the intended path but the only expressible one below the
  owner role.
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
- **A-writer-returns-both-ids** (new in v3, defect 1) one allowed change returns a non-null
  `o_autonomy_policy_id` **and** `o_admin_policy_change_id` from the single call, the ledger
  row's `admin_action_id` is the action just minted, and its `previous_autonomy_level` /
  `override_key_count` match what the DB derived rather than anything Python passed — the
  positive control for the atomic path whose negative control is
  P-writer-spends-action-atomically.
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
- record that `uaid_app` **lost** `INSERT`/`UPDATE` on `autonomy_policies` and holds no
  `INSERT` on `admin_policy_changes`, that `AutonomyPolicyRepository.upsert` was **removed** in
  favour of the single gated call, that the policy write and the spending of its authorization
  are one database call, and that `scripts/bootstrap_rls_role.sql` must be run before `0062`
  (it creates `policy_admin_writer`);
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
gains `SELECT` on all four new tables plus `INSERT` on `admin_actions` **only**, and **loses**
`INSERT`/`UPDATE` on `autonomy_policies`. No budget figures. No spec edit. No softening of
go-live or §2.6. No Slice 64.

---

## 9. Builder constraints

- TDD: land P-1…P-6, then the failing P-priv/autonomy_policies/INSERT,
  P-writer-spends-action-atomically, and P-tighten-relax-empty-map (the three proofs the v1
  and v2 rejections turned on) before the feature code.
- Every guard in §3 and §OD-11/§OD-12/§OD-13 has a named probe in §5.2 and must satisfy all
  **nine** §5.0 conditions. Where §5.0 rule 8 applies, **both halves** of the §5.2.a.1 pair
  must land — a lone `/own-reason` half is the v3 defect and a lone `/reachable` half proves no
  guard. Where §5.0 rule 9 applies — the policy writer is the one writer of that class in this
  slice — **`P-writer-concurrent-first-write` (§5.2.a.2) must land with all six assertions
  (including assertion 6's observer half, which pins the waiter to the **write** rather than the
  existence probe) and its racy-body mutation**, driven by the three-step interleaving §5.2.a.2
  specifies and **no** added barrier in either body, and its `/tighten-no-orphan` sibling with it;
  a single-writer path test over the absent-row branch is not evidence and is the v4 code defect.
  A probe whose mutation cannot commit (or, for rule 9, cannot reproduce the falsified ledger) is
  a defect, not a pass — for rule 9 specifically, a green mutation means the interleaving never
  entered the pre-write window and the **probe** is what to repair; if a
  guard genuinely cannot carry a load-bearing probe, demote it to §5.3 and say so — do not
  dress an assertion as a refusal.
- All forgery/privilege probes run as **`uaid_app`** via `rls_engine`, except those that must
  exercise the owner path because the runtime role has no privilege to reach the guard under
  test — each stating that reason in its docstring: **P-allow-no-grant-as-admin**,
  **P-grant-insert-status**, **P-grant-update-widen**, the whole **P-ao/\*** family (11 cases),
  the three **P-change-\*** guard cases (v3: the runtime role lost INSERT on
  `admin_policy_changes`), **P-org-status-check** (fact 0.1.16), **P-event-lies**,
  **P-event-wrong-org**, **P-event-role-grant-status**, **P-event-principal-mismatch**,
  **P-event-role-mismatch**, **P-check-tae-role-shape**, and the admin-side seeding halves of
  the **P-rls/\*** family. Any *other* probe run as admin is a defect.
- Restore every disabled trigger, dropped constraint, temporary grant, disabled RLS, and
  replaced function body in a `finally`, and let A-triggers-enabled catch a miss. The two
  probes that disable RLS or drop `uq_admin_policy_changes_action` must additionally re-assert
  `relforcerowsecurity` / the constraint's presence before the test ends.
- The §OD-14 test migration touches twenty existing test files. Change **only** the policy
  seeding call at each site. If any test's *assertions* must change, name it in the PR body
  with the reason — a silently weakened assertion is a defect. If `seed_gated_policy` raises
  `SeedPreconditionError` at a site, convert that site (Mode A, or seed before the
  `tenant_scope` block) — never loosen the helper.
- Do not `ruff format` the whole tree. Line cap 500 per file — split rather than grow
  (`guards_sql.py` is pre-split from `ddl.py` for exactly this reason; if the two new function
  bodies push it over, split again into `app/admin/policy_sql.py`).
- `pyright` on the CI-owned paths **plus** every new Slice-63 module and test in §4, plus the
  two un-frozen files of §1.1; 0 errors on that set. Full-repo pyright remains out of scope
  (pre-existing errors).
- Conventional commits (`feat(admin):`, `test(admin):`, `feat(migrations):`,
  `refactor(policy):` for the removal of `upsert`). Do not commit `.env`.
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

**v3.** Sol REJECT #2 accepted in full; head re-verified `0061`. Four defects, none argued
down. The common thread in both rejections was a claim asserted rather than measured, so v3
**executed every contested behaviour against the live PostgreSQL 16 container** before writing
it down; the results are facts 0.1.13–0.1.16 and each is a test the builder must reproduce.

1. **Policy write and action consumption were not atomic.** Accepted. The spend moved
   **inside** `admin_write_autonomy_policy` (§OD-11 step 3.8): the function now upserts the
   policy *and* inserts the `admin_policy_changes` row in one call, returning both ids via
   `OUT` parameters, with `uq_admin_policy_changes_action` as the **sole** spend authority —
   v2's separate "already spent?" `SELECT` is **deleted**, because a pre-check would mask the
   constraint and could not carry a mutation that commits. `previous_autonomy_level` and
   `override_key_count` are now DB-derived, not caller-supplied. `uaid_app` loses `INSERT` on
   `admin_policy_changes` (§3.3), so the ledger row cannot originate anywhere else, and
   `AutonomyPolicyRepository.upsert` is **deleted** rather than re-signatured (§1.1) so no
   ungated name survives for a future caller. Python is down to two steps, neither of which can
   be interleaved or replayed. Measured (fact 0.1.14): the replay refuses **and** the policy
   column retains its first value, so there is no window where a policy changed without a
   ledger row. Probes: **P-writer-spends-action-atomically** (renamed from
   P-writer-requires-unspent-action; absorbs P-change-action-reuse, now removed),
   **P-priv/admin_policy_changes/INSERT**; assertions **A-no-ungated-upsert**,
   **A-writer-returns-both-ids**; A-grant-matrix and A-writer-role updated.
2. **The §OD-14 helper could not see uncommitted admin-session fixtures.** Accepted; v2's own
   parenthetical admitted the problem and did not fix it. **Chosen path (a):** the definer
   function is called **on the caller's own session** — `apply_policy_change` now *takes* a
   session (with `apply_policy_change_in_scope` owning `tenant_scope` for production callers),
   so admin-session tests seed the GUC and the grant and call the writer in **one transaction,
   one connection**. Fact 0.1.13 measured exactly this: a non-owner SECURITY DEFINER function
   called from a superuser session read a row that transaction had not committed, and stayed
   RLS-confined (cross-tenant and unset-GUC both refused). For runtime-scope sites the grant
   still needs an admin connection, so the helper takes the **existing `admin_engine` fixture**
   — v2's "short-lived admin engine from `TEST_ADMIN_URL`" is deleted, and the helper now builds
   no engine at all — and it **states and enforces** the committed-tenant precondition with a
   loud `SeedPreconditionError` instead of a fallback. That precondition was checked, not
   assumed: those fixtures seed inside `async with admin_engine.begin()`, which commits
   (`tests/conftest.py:162-169`, `tests/test_ci_evidence.py:160-162`). A tripped site is a
   failure the builder converts, never a silent pass. **No claim that a second connection sees
   uncommitted work appears anywhere in v3.**
3. **Four guards had no refusal/mutation pair.** All four added as real §5.2 probes:
   **P-writer-guc-unset** (setup discloses and disables the outer RLS layer per §5.0 rule 4;
   the mutation replaces the guard with the tempting "infer the tenant from the action row"
   fallback and **commits** — measured, `pol_rows = 1`; v2's A-writer-guc assertion is
   promoted and deleted from §5.3), **P-writer-no-existing-policy** (monotonicity is vacuous
   against an absent row, so the existence clause is provably the only refuser),
   **P-grant-insert-status** (the `status` CHECK permits `'revoked'`, so only the guard can
   refuse a born-revoked grant), and **P-org-status-check** (`ck_organizations_status_valid` is
   now a named constraint in §3.5; owner path, because fact 0.1.16 shows `uaid_app` has only
   `SELECT` on `organizations`).
4. **TRUNCATE/parent mutations could not commit.** Accepted, and Sol's `0A000` reproduced: on
   an FK parent, `TRUNCATE` never reaches the BEFORE TRUNCATE trigger (fact 0.1.15), so v2's
   two parent cases were false in *both* directions. §5.2.g is rebuilt: the statement under
   test is the **explicitly ordered two-table** `TRUNCATE <parent>, <child>`, the child's
   truncate trigger is disabled in setup so the surviving `RAISE` provably names the parent,
   and the mutation additionally disables the parent's trigger — all three states measured
   live, including the commit (`rows_left = 0`). P-downgrade-populated's mutation becomes the
   **ordered children-first drop sequence** now named in §3.6(f), because a single
   `DROP TABLE` on either parent fails with `2BP01`; no `CASCADE` is used. §5.0 gains **rule
   7**, which also re-specifies parent-row DELETE cases to seed unreferenced rows so an FK
   `RESTRICT` can never stand in for the guard, and states plainly that a probe whose
   absent-guard mutation cannot commit must be deleted rather than kept.

**v4.** Sol REJECT #3 (`369abc89-7144-4f42-b810-72f6ec367a64`) accepted: §5.2.a's four
writer-function mutations remained **masked by `admin_policy_changes_guard`**, so
`P-writer-no-existing-policy` did not close v2 defect 3. **The owner (Salim, 2026-08-24) ruled
that all three rejects were correct against the standard he had set, and that the standard was
wrong for overlapping guards.** He amended the standing test bar, authorized v4, and **reset the
consecutive plan REJECT count to 0**. v4 carries out that amendment and **nothing else** — no
new scope, no new table, no HTTP, no go-live flip, no D-8/D-9/D-10 close, and no re-litigation
of any v1 or v2 defect (all stay closed as accepted). One defect, accepted in full:

1. **Overlapping guards were proven by single probes that could not commit.** Accepted. §5.0
   gains **rule 8**: when a neighbouring constraint independently refuses the same mutation, the
   target guard is proven by a named **PROBE PAIR** — `/reachable` (target **and** every
   independently-refusing neighbour disabled ⇒ the mutation **COMMITS**, with the prevented harm
   asserted) and `/own-reason` (neighbour disabled, target **ENABLED** ⇒ refused with the
   target's own `RAISE` text and SQLSTATE). Rules 1–3, the single-guard bar, are unchanged, and
   the plan states plainly that a single probe disabling only the target while a neighbour still
   refuses **proves nothing**. Which rows overlap was **measured**, not assumed: a live
   PostgreSQL 16.14 harness (`uaid_os-postgres-1`, throwaway database created and dropped in the
   same session, no app database touched) reproduced the §OD-11 step-3 writer body and the
   §3.3:938–944 guard clauses and ran each mutation with the neighbour both enabled and
   disabled. The results are tabulated at §5.2.a.1 (C1–C7). Five rows moved out of the §5.2.a
   table into **§5.2.a.1** as named pairs — **`P-writer-requires-allowed-action`**,
   **`P-writer-requires-policy-kind`**, **`P-writer-guc-unset`**,
   **`P-writer-no-existing-policy`** (the row the REJECT named), and — newly converted, exactly
   as the owner anticipated — **`P-tighten-changes-level`**, because the ledger guard's
   `previous_autonomy_level = new_autonomy_level` clause independently refuses a moved level
   (measured C5). Two findings beyond the REJECT's wording are recorded rather than smoothed
   over: (a) `P-writer-no-existing-policy` has **two** independent neighbours, the second being
   the writer's **own** next clause `tighten_may_not_change_level` (with no stored row the
   derived previous level is NULL), so the `/reachable` half must remove both — measured C4; and
   (b) for `P-writer-guc-unset` the ledger guard is **not** an independent refuser at all once
   RLS is out of the way (measured C3) — the real neighbour is **RLS on the three tables**, which
   v3 already disclosed and disabled in setup, so the pair names RLS as neighbour 1 and disables
   the trigger only because the ruling directs it, claiming nothing more. **Four** rows were
   measured **not** to overlap and therefore stay single-guard under rules 1–3, each with its
   measurement recorded: **`P-writer-spends-action-atomically`** (C7 — with
   `uq_admin_policy_changes_action` dropped the replay commits and a second ledger row appears
   while the guard is enabled) and the three **`P-tighten-relax-*`** rows (C6 — with the
   monotonic clause removed the relaxing call commits while the guard is enabled). The two
   `P-priv/autonomy_policies/*` rows stay single-guard per the ruling. §9's probe bar moves from
   seven conditions to **eight** and requires **both** halves of every pair. Every harness
   result is labelled a harness result: the builder must reproduce each pair against the real
   `0062` objects, and a pair that does not reproduce is a defect to report, never a licence to
   drop a half.

**v4.1.** v4 was APPROVED as a plan and built at `ddb3869`. Sol then **REJECTED the code**
(`380cc908-3745-46fb-b762-504f4e1bd4fd`): a **concurrent first-policy-write race**. Measured on
PostgreSQL 16.14 — two authorized writers both observed no policy row, the final stored level was
`2`, and the ledgers were `[(NULL, 3), (NULL, 2)]`, so the second write overwrote level 3 while
recording `previous_autonomy_level = NULL`. **The defect is in this plan, not the build:** approved
v4 §OD-11 steps 5–7 took `SELECT … FOR UPDATE` on an **absent** row (which locks nothing), then
`INSERT … ON CONFLICT DO UPDATE`, and derived the ledger's previous level from the empty pre-insert
read. The builder **correctly refused** to patch outside the approved plan; the owner (Salim,
2026-08-24) authorized this amendment, scoped to **OD-11 plus the required test surface**, and
ruled that **the plan REJECT count stays 0** — v4.1 does not restart it. One defect, accepted in
full:

1. **The writer's absent-row path did not serialize, and the ledger's previous level came from a
   read taken before the row existed.** Accepted. §OD-11 steps **3.5–3.7** are rewritten: 3.5 is
   named an **existence probe** (with the fact that `FOR UPDATE` on an absent row locks nothing
   stated where it can no longer be forgotten); 3.6's tighten block is stated to run **before any
   INSERT**, so a tighten against an absent row still refuses `no_existing_policy` with zero rows
   created — the fix must not buy serialization by leaving an orphan policy; and 3.7 becomes
   **(a)** present row → already locked, **(b)** absent row → `INSERT … ON CONFLICT
   (tenant_id, project_id) DO NOTHING RETURNING id` to serialize creation on the unique index,
   with `v_created := FOUND` distinguishing *"I created it"* from *"I waited for whoever did"*,
   **(c)** an authoritative `FOR UPDATE` read taken **after** the row is guaranteed to exist
   (`previous_autonomy_level` comes from here, or is NULL only when (b) reported a real creation),
   plus the fail-closed `policy_write_row_unavailable` backstop, and **(d)** a plain `UPDATE` of
   the now-locked row. The owner's standing test-bar addition lands as **§5.0 rule 9** — a writer
   whose target row may not exist is proven with a **two-writer probe**, never a single-writer
   path test — and its named probe **`P-writer-concurrent-first-write`** lands as **§5.2.a.2**
   with six assertions (both spends succeed; one policy row and one shared policy id; exactly one
   NULL-previous ledger row, belonging to the first writer; the other row citing the first
   writer's level; the stored level equal to the last committed writer's; and **proof that the
   second writer actually blocked**), a rule-1 mutation that **reinstalls the racy v4 body and
   must reproduce `[(NULL, 3), (NULL, 2)]`**, and the `/tighten-no-orphan` sibling. §9's probe bar
   moves from eight conditions to **nine**. Measured while writing v4.1 on a throwaway database
   (PostgreSQL 16.14, created and dropped in the same session, no app database touched): the
   harness **reproduced Sol's exact defect** with the v4 body before it was used to check the fix
   (R1), the v4.1 body produced `[(NULL, 3), (3, 2)]` with the second writer provably blocked
   (R2), the tighten path refused with zero rows created (R3), a REPEATABLE READ loser failed
   closed with `40001` and no ledger row (R4), and the sequential present-row, tighten and
   §OD-12 paths were unchanged (R5).

   **Probe window, corrected within v4.1 (coordinator finding, 2026-08-24, before Sol review; not
   a v5).** The coordinator read §5.2.a.2's interleaving — writer 1 held open after its call
   *returns*, writer 2 then calls — as the **wrong** window, on the reasoning that writer 1 has by
   then INSERTed its (uncommitted) row, so writer 2 would wait at its step-3.5 `SELECT … FOR
   UPDATE`, observe the row, and behave correctly **under the v4 body too** — making the mutation
   unable to reproduce the harm, which under rule 1 would itself be a REJECT. **Measured, and the
   premise does not hold on PostgreSQL 16.14:** a tuple invisible to the reader's snapshot cannot
   be row-locked, so that `SELECT … FOR UPDATE` returns **0 rows in 0.252 ms without waiting**,
   and the first thing that waits is the unique index (R6). Driven exactly as specified — writer 2
   issued 1.79 s after writer 1's call returned, writer 1 committing only after writer 2 was
   observed pending — the **v4 body reproduced `[(NULL, 3), (NULL, 2)]`** with both probes empty
   and writer 2 blocked 3219.597 ms on a `transactionid` lock held by writer 1 (R7), while the
   **v4.1 body on the identical interleaving produced `[(NULL, 3), (3, 2)]`** (R8). The specified
   window **is** the TOCTOU window, and it is guaranteed by construction rather than by timing,
   because writer 1 is held open until writer 2 is confirmed pending. The rejected alternative —
   a third session's `LOCK TABLE … EXCLUSIVE` plus a dual start — is **weaker**, since after the
   release one writer can finish probe *and* write before the other probes; and no test-only
   `pg_sleep` or advisory-lock barrier is added to either body, so nothing in the mutation can be
   mistaken for product scope. What v4.1 changes in response is **evidence, not sequence**: the
   probe now states this mechanism in its docstring so a reviewer need not infer it, assertion 6
   gains a second half requiring an observer to pin the **blocking site** (`wait_event_type='Lock'`,
   `wait_event='transactionid'`, `pg_blocking_pids` containing writer 1) so a wait at the *probe*
   can never be mistaken for a wait at the *write*, rule 9 gains the by-construction and
   blocking-site requirements plus the rule that a green mutation means the probe is the defect,
   and R6–R8 join the §OD-11 measurement table. `/tighten-no-orphan` is **confirmed correct as
   written** — single-session by design, and rule 9 does not reach it because the path it asserts
   creates no row for two writers to race for; it was re-measured unchanged.

   **Nothing else moved:** §5.0 rule 8 and all five §5.2.a.1
   pairs stand as approved (the only consequence is that Pair 4's `/reachable` row is now created
   by 3.7(b) instead of the old upsert — same asserted harm), every v1–v3 fix stays closed, no
   new table, column, migration, renumber, HTTP route, or go-live change, and D-8/D-9/D-10 stay
   OPEN.

**Halt rule for v4.1.** If Sol REJECTS v4.1, this line **halts**: there is no v5 without the
owner.
