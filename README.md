# UAID OS

Salim-standard AI service scaffold.

## Stack
- FastAPI ............ app/main.py
- Postgres + Redis + ChromaDB ... docker-compose.yml
- Async SQLAlchemy 2 + Alembic ... app/db.py, app/models/, migrations/
- Sanad provenance / No-Free-Facts ... app/core/provenance.py
- Muhasabah self-audit gate ... app/core/reasoning.py
- Deterministic compute (NumPy/SciPy) ... app/compute/
- Python 3.11 via uv

## Run
    make up      # start Postgres / Redis / Chroma (Docker)
    make dev     # run API on http://localhost:8000
    make fmt     # format + lint

## Tests
Two commands by design:

    make test                          # Docker-free: pure-logic + route tests only
    RLS_DB_PASSWORD=... make test-db   # DB-backed tests; requires `make up`

`make test` never touches Postgres. DB-backed tests (migration apply, tenancy
invariants INV-1..4, real readiness round-trip, **and RLS INV-5 + catalog
enforcement**) are marked `db` and run only under `make test-db`. That target
bootstraps the non-superuser `uaid_app` role (needs `RLS_DB_PASSWORD`), then
creates+migrates the dedicated `app_test` database **as admin** (schema built by
Alembic — never `create_all`), then runs `-m db` with the runtime `uaid_app`
connection. Helper targets: `make test-db-create`, `make test-db-migrate`,
`make test-db-drop`, `make db-bootstrap-rls-role`.

## Endpoints
- Liveness:  http://localhost:8000/health/live   (200 `{"status":"alive"}`, no dependency calls)
- Readiness: http://localhost:8000/health/ready  (real `SELECT 1`; 200 when DB up, 503 when down)
- Demo:      http://localhost:8000/demo

## CI
`.github/workflows/ci.yml` runs on pull requests and pushes to `main`: `uv sync`,
`uv run ruff check .`, `make test` (Docker-free), and `make test-db` against a
`postgres:16` **service container**. CI uses non-secret, ephemeral credentials
(`RLS_DB_PASSWORD=uaid_app`) and overrides the Makefile's admin `psql` via
`PSQL=psql` (TCP to the service) — no real `.env` or production secrets required.

## Security model — tenant isolation (two layers)
Tenant-owned tables (`projects`, `project_runs`) are protected at two layers:
- **App layer:** `TenantContext` + `TenantScopedRepository` require an explicit
  tenant and filter every query (INV-1..4).
- **DB layer (RLS):** Postgres Row-Level Security, `ENABLE`d + `FORCE`d, with a
  deny-by-default `tenant_isolation` policy keyed on the `app.current_tenant` GUC.
  Use `app.tenancy.tenant_scope(context)` so the GUC is set on the same
  transaction as the queries (INV-5).

Two DB roles:
- **`uaid_app`** — non-superuser (`NOSUPERUSER NOBYPASSRLS`), the **runtime**
  connection; RLS applies to it. Created by `make db-bootstrap-rls-role` from
  `RLS_DB_PASSWORD` (never committed).
- **`app`** — owner/superuser; used **only** for migrations, role bootstrap, and
  test seeding (superusers bypass RLS, so the runtime must not use it).

## Audit log (§16.6) — append-only, hash-chained
`audit_logs` is a tamper-evident, SHA-256 hash-chained trail. The runtime appends
**only** through the `SECURITY DEFINER` function `audit_append`, owned by a limited
NOLOGIN role **`audit_writer`**; `uaid_app` has `EXECUTE` on it and **no** direct table
privileges. The tenant is derived from the `app.current_tenant` GUC (fail-closed), so a
caller cannot forge another tenant's rows — use `app.audit.record(session, ...)` inside
`tenant_scope`. `UPDATE`/`DELETE`/`TRUNCATE` are blocked by a trigger; `audit_verify()`
(admin-only) walks the chain. **Tamper-evident, not tamper-proof** (a DB superuser can
still rewrite history); external sink + signing are deferred. Slice 2 records committed
tenant events only.

## Autonomy policy engine (§5 / §2.6)
A deterministic, **deny-by-default** authority engine: `check_authority(action, level,
overrides) → ALLOW | DENY | NEEDS_APPROVAL` over a code-defined authority matrix
(`app/policy/`). Autonomy levels A0–A5 are stored per project in the tenant-owned,
RLS-protected `autonomy_policies` table. Per-project overrides are **tighten-only**
(may raise `min_level`, add approval, or disable — never relax), and §2.6
mandatory-approval actions (production deploy, protected-branch merge, delete, secrets,
billing, external comms, sensitive data, risk acceptance, gate bypass, weakening
test/review standards) are **structurally non-bypassable**. `AutonomyPolicyRepository.decision_for`
is **fail-closed**: a missing policy or an invalid persisted override yields DENY. Policy
changes are audited via the Slice 2 audit log. The policy is **enforced by the Slice 5 broker
for brokered tool decisions only**; no broader runtime/workflow enforcement exists yet.

## Approval engine (§18)
Request → await → resolve approval lifecycle (`app/approvals/`, `ApprovalRepository`).
`risk_tier` (low/medium/high/production) drives only the **non-response policy** (§18.5:
low auto-proceeds after 24h, medium pauses, high/production block until approval — computed
on demand, **no scheduler**). A separate **non-bypassable** flag `requires_explicit_approval`
(forced `True` for §2.6 actions via the policy matrix) means **only `APPROVED` unblocks** — a
low-risk non-response can never bypass it. The gate `is_blocked(project, action)` is
**fail-closed** (no approval ⇒ blocked). Every transition writes an `approval_events` row and
an audit-log entry. Tables are tenant-owned + RLS; `approvals` is never `DELETE`-able and
`approval_events` is append-only. The engine is **wired into the Slice 5 broker for tool-scoped
approval decisions only** (no scheduler/channels/dashboard); and **approver identity is unverified**
(`approver_provenance='caller_supplied_unverified'`) until request-auth exists, so these are not yet
verified human approvals.

## Tool broker (§11)
`app/tools/` is the controlled chokepoint for tool calls (`broker_call`). It is
**deny-by-default** and composes the policy + approval engines: unknown tool ⇒ denied;
not on the per-agent allowlist ⇒ denied; policy `DENY` ⇒ denied; policy/contract
needs-approval ⇒ checks a **tool-scoped** approval (`subject_ref="tool:<name>"`). Tool
catalog is code-defined; params are validated (mapping-only, ≤16 KiB) and **secret-ish
keys redacted** before storage (`DENIED_INVALID_PARAMS` otherwise; audit never includes
params). The allowlist is an append-only **grant/revoke ledger** (no UPDATE/DELETE; latest
event decides). Every attempt is recorded to tenant-owned, append-only `tool_calls` + the
audit log. **Skeleton — no real execution.** Because request-auth is out of scope, an
unverified approval yields `NEEDS_AUTHENTICATED_APPROVAL` and the success terminal is
`ALLOWED_UNVERIFIED_IDENTITY` — never executable authorization yet.

## Agent registry (§9.7 / §17.4 / §22.2)
`app/agents/` is the durable agent identity + change-control substrate. **Global,
admin-curated** `agent_blueprints` (reusable role identity) and **global, immutable**
`agent_versions` (the §22.2 pinning snapshot — `model_route` + six `sha256:` component
hashes + a derived `content_hash`) make up the catalog; the runtime role `uaid_app`
has `SELECT` only. Versions are immutable via `BEFORE UPDATE/DELETE` (row) and
`BEFORE TRUNCATE` (statement) triggers — **DML-immutable for all roles incl. the table
owner, but not tamper-proof against a DB superuser** who can disable triggers (same bar
as the audit log). `register_version` is idempotent on `content_hash`; changed content
always yields a **new** version. **Tenant-scoped** `agent_instances` (RLS ENABLE+FORCE)
bind a global version into a project/run: a triple composite FK pins an active run to
the **same project and tenant**, binding identity columns are immutable and
`active_run_id` is set-once (UPDATE trigger), and a partial unique index allows only one
**live** instance per `(tenant, project, instance_key)` (retired rows may repeat). The
global catalog holds **role metadata + hashes only — never tenant prompts/code/documents**
(§17.5; structurally enforced — there are no body/content columns). Instance lifecycle is
audited; **skeleton — no Agent Factory, eval execution, model routing, agent execution,
or broker wiring.**

## Migrations (admin only)
    ALEMBIC_DATABASE_URL=$ADMIN_DATABASE_URL uv run alembic upgrade head   # or: make migrate

The URL is resolved in `migrations/env.py` from `ALEMBIC_DATABASE_URL` (if set)
or `app.config.settings.admin_database_url` — **admin credentials only; migrations
never run as `uaid_app`** (which lacks DDL rights). No `CREATE EXTENSION` is used —
UUID PKs rely on core `gen_random_uuid()` (Postgres 13+; we pin 16).
