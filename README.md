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
- Dashboard (read-only, §18.6): `GET /api/projects/{id}/{runs,approvals,blockers,cost}` — require
  `Authorization: Bearer <api-key>`; missing/invalid ⇒ 401 (see "Read API / dashboard" below).

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

## Cost ledger (§19)
`app/cost.py` + `app/repositories/cost.py` track spend and enforce ceilings. **Tenant-owned,
DB-immutable** `cost_events` (the §19.2 components) is the source of truth — running totals are
**on-demand SUMs**, never a denormalized counter. Immutability is enforced by `BEFORE
UPDATE/DELETE` (row) + `BEFORE TRUNCATE` (statement) triggers + `REVOKE` (DML-immutable for all
roles incl. the table owner; **not tamper-proof vs. a DB superuser**). Money is `NUMERIC(18,6)`
with Python `Decimal`; inputs that are `float`/`bool`/negative/non-finite/over 6 dp are rejected.
Recording is **idempotent on a source-namespaced key** `(tenant_id, source_system, external_ref)`
via `INSERT … ON CONFLICT DO NOTHING` + re-select: a true retry returns the existing event, but
**reuse of the key with different material data raises `IdempotencyConflict`** (so provider/caller
corruption surfaces instead of being silently deduped). **Incurred costs are always recorded, even
over budget.** Per-project `budgets` (one per project, audited with before/after caps) drive a
**deterministic stop decision** (`evaluate`): missing budget ⇒ STOP `no_budget` (fail-closed),
threshold is `>=`, daily aggregation uses **UTC half-open bounds**. The decision is **returned, not
halting** — no workflow runtime consumes it yet. `cost_events` is `SELECT, INSERT` only; `budgets`
is `SELECT, INSERT, UPDATE` (no DELETE); both are RLS ENABLE+FORCE. **Budget changes are audited but
are NOT verified human approvals** — an approval workflow for budget increases is deferred. **Skeleton —
no price-card integration, provider calls, model routing, billing UI, forecasting, or per-phase budgets.**

## Durable workflow runtime (§23.2)
`app/runtime/` is the durable execution substrate (D2 = **LangGraph + a custom UAID-owned
checkpointer**, not Temporal). `UAIDCheckpointer` implements LangGraph's `BaseCheckpointSaver`
(`aput`/`aput_writes`/`aget_tuple`/`alist`/`adelete_thread`) over **UAID-owned, RLS-protected,
Alembic-managed** tables — **never** LangGraph's `.setup()` tables — so all durable workflow state
(which can hold tenant content) stays under our tenant isolation. Checkpoints are serialized with
LangGraph's serde to `BYTEA`; `thread_id == str(run_id)`. `run_checkpoints` /
`run_checkpoint_writes` are **mutable working state** (`adelete_thread` cleans them; `task_path` is
persisted at rest); `run_steps` is the **immutable** append-only history (UPDATE/DELETE/TRUNCATE
blocked by triggers). A `RunRepository` drives validated `project_runs` state transitions, audited.
A crash→resume test proves a run continues from its last checkpoint **without re-executing completed
steps**. **"Deterministic replay" here means state reconstruction** from checkpoints + `run_steps` +
the audit/tool/cost ledgers — **not** Temporal-style automatic event-history re-execution; it is valid
only while nodes stay deterministic over persisted state, external actions are idempotent and
broker/ledger-mediated, and nodes do no hidden I/O.

**Runtime integration (Slice 8b)** wires the substrate to the rest of the control plane:
- **Approval wait/resume** — a sentinel `approval_gate` precedes the protected node (so protected
  work never runs pre-approval); the engine requests a `workflow.resume` approval (risk tier `high`,
  `requires_explicit_approval=True`, subject `run:<run_id>:node:<protected>`) and marks the run
  `blocked`. Resume consults the additively-extended `ApprovalRepository.is_blocked(..., subject_ref=None)`:
  `APPROVED` ⇒ resume → complete; a terminal denial (`REJECTED`/`CANCELLED`/`EXPIRED`/explicit
  `PROCEEDED_BY_POLICY`) ⇒ the run **fails** (no stuck runs, no silent progress); `PENDING` stays blocked.
  Auto-policy proceed never unblocks an explicit workflow wait.
- **Retry/backoff** — node-level LangGraph `RetryPolicy`; a dedicated `TransientNodeError` is retryable,
  anything else fails the run; `retried` is recorded in `run_steps` **only for attempts > 1**, bounded by
  `max_attempts`.
- **Cost STOP→pause** — the engine consumes the Slice‑7 `evaluate` stop signal **before the next node**
  (at a checkpoint boundary); STOP ⇒ `running→paused` (`cost_paused`) without executing the node.

**Still skeleton:** no tool-result persistence, no §23.3 control loop, no distributed workers; the cost
guard is opt-in per run; LangGraph's native `interrupt()` is not used (the gate decision lives in the
audited, RLS-backed approval engine).

## Document intake sandbox (§16.3)
`app/intake/` treats customer-supplied documents as **untrusted data**. The architectural guarantee is
**instruction/data separation**: document text is stored and labeled as data, **no LLM is wired**, and
no code path lets document content reach the policy/authority/approval engines. `scan()` is a
**best-effort, deterministic** prompt-injection signal (a curated marker set, **no ML**) returning
marker **identifiers** (never raw excerpts) — used to **quarantine**, not as a detection guarantee.
`as_untrusted_block()` wraps content as data with a do-not-follow preamble (retrieval-time labeling).
`DocumentRepository.ingest()` validates (content ≤ 1 MiB, `content_type`/`source` allowlists, bounded
`filename`), scans, and stores to the tenant-owned, RLS `documents` table as `accepted` or
`quarantined`; it is **idempotent on `(tenant, project, content_hash)`** and audits **metadata + marker
identifiers only — never the body**. DB-level guards (the `documents_guard` trigger + CHECKs) enforce
**content integrity** (`size_bytes` and the core-`sha256` `content_hash` must match the content),
**content/identity immutability**, and a **one-way `accepted → quarantined`** lifecycle (a reviewer can
quarantine; `quarantined → accepted` is rejected by the DB). `documents` is `SELECT, INSERT, UPDATE`
(no DELETE). **Skeleton — no Documentation Compiler, ML/embedding classification, LLM/RAG wiring,
binary parsing, malware scanning, or per-section quarantine.**

## Canonical intake spine (Phase 2, Slice 11 — §3.4 / §4.2 / §4.4)
`app/intake/compiler.py` + `app/repositories/intake.py` add a **deterministic (no-LLM),
provenance-backed canonical intake spine**: the foundation later Phase‑2 work attaches to.
Two tenant-owned, RLS-protected (ENABLE+FORCE + `tenant_isolation`), **append-only** tables:
- **`intake_artifacts`** — a unified `kind` table (`requirement` / `acceptance_criterion` /
  `test_oracle` / `assumption`). A self **triple-FK** `parent_id` pins a child to the same
  project+tenant. A tightened §4.4 CHECK means an `assumption` **must** carry exactly one valid
  classification (`safe_assumption` / `needs_approval` / `unsafe_assumption_blocked` /
  `unknown_cannot_proceed`) and every other kind **must** be `NULL` (the `IS NOT NULL` guard
  defeats SQL three-valued logic, so a missing assumption classification is rejected, not passed).
- **`intake_provenance`** — the Sanad source store. A document-backed source is pinned to an
  **accepted** document of the **same tenant+project** by a composite FK
  `(document_id, project_id, tenant_id) → documents` **plus** a `BEFORE INSERT` trigger that rejects
  non-accepted documents; a `NULL document_id` is a non-document origin (e.g. a recorded human
  decision) and skips the document FK.

**Fail-closed (No-Free-Facts, §2.4) is DB-enforced:** a **deferrable constraint trigger** rejects
any artifact that commits with zero provenance rows (the artifact may be inserted before its
sources within one transaction; the check runs at commit). The repository (`IntakeRepository.add_artifact`)
also fails closed via the `app/core/provenance.py` `Fact` gate and pre-checks document sources against
the tenant-scoped `DocumentRepository` (exists, accepted, same project). Both tables are `SELECT, INSERT`
only (UPDATE/DELETE/TRUNCATE blocked by triggers); audit records **safe metadata only — never the
artifact title/body/data**. `documents` gains an additive `UNIQUE(id, project_id, tenant_id)` solely as
the composite-FK target. **Slice 11 is deterministic only — no LLM/classifier/extractor, no
build-readiness auditor, no gap/contradiction detector, no artifact generation, and no API exposure.**

## Read API / dashboard (§18.6)
`app/api/` exposes **read-only JSON** endpoints behind **hashed bearer-key tenant auth** (Phase‑1
decisions: D3 API-only, D4 hashed API-key → tenant). `require_tenant` is the **single place** an
HTTP request becomes a tenant: it parses `Authorization: Bearer <key>`, resolves the key (its
`sha256:` hash → an active `tenant_api_keys` row) on a pre-tenant session, and returns a
`TenantContext`; a missing/malformed/unknown/revoked key ⇒ **`401` with no fallback tenant**.
Endpoints are GET-only and project-scoped — `GET /api/projects/{id}/{runs|approvals|blockers|cost}` —
and each opens `tenant_scope(context)` so all reads pass through RLS; a `project_id` outside the
caller's tenant returns nothing (never another tenant's data, proven end-to-end over HTTP).
`tenant_api_keys` is a **global auth-lookup table** (intentionally not RLS, since resolution happens
before any tenant is known) storing **only key hashes** — never the raw key; keys are issued/revoked
by an admin-path helper (`secrets.token_urlsafe(32)`; raw key returned once). Resolution goes through a
**`SECURITY DEFINER` function** (`resolve_tenant_api_key`, owned by the least-privilege NOLOGIN role
`api_key_resolver`): the runtime role `uaid_app` has **EXECUTE-only** access and **no direct read** of
the key table, and only the hash is passed into SQL (the raw key never reaches the statement/logs).
Covers the implemented
§18.6 subset (run state, open approvals, blockers, cost + stop decision); **forecast, critical path,
readiness, evidence-pack status, high-risk findings, deployment status, next action, and any web UI
are deferred.**

## Migrations (admin only)
    ALEMBIC_DATABASE_URL=$ADMIN_DATABASE_URL uv run alembic upgrade head   # or: make migrate

The URL is resolved in `migrations/env.py` from `ALEMBIC_DATABASE_URL` (if set)
or `app.config.settings.admin_database_url` — **admin credentials only; migrations
never run as `uaid_app`** (which lacks DDL rights). No `CREATE EXTENSION` is used —
UUID PKs rely on core `gen_random_uuid()` (Postgres 13+; we pin 16).
