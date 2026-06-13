# CLAUDE.md — UAID OS
## How to work
- Engage project-orientation and task-standards first, every substantial task. One step at a time. No invented facts.
Read this first in any session. Re-read after a context reset or compaction.

## What this project is
**UAID OS** (Universal Autonomous Integration & Delivery OS) is a domain-agnostic
**autonomous delivery control plane**: you hand it a documentation package for any
build, and it judges build-readiness (R0–R5), compiles missing specs where safe,
dynamically staffs specialist AI agents, then builds → reviews → tests → deploys
under a graded autonomy policy (A0–A5). "Done" is proven by an **evidence pack**,
never an agent's claim.

The authoritative design is `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`
(~3,000 lines). Build to that spec. Section references below (§) point into it.

## Current status (2026-06-13)
**Phase 1 (§26.1) — Slices 1, 1b, 2, 3, 4, 5, 6, 7, 8a, 8b, 9, 10 merged + D4
API-key hardening; tagged `v0.1.0` / `v0.1.1`. Phase 2 (§26.2) — Slices 11 (canonical
intake spine), 12 (deterministic build-readiness auditor, originally R2-capped), 13 (deterministic
gap & structural contradiction detector), 14a (LLM-assisted extractor → inert,
provenance-verified, human-review proposals — the first real LLM integration), 14b
(promotion of approved proposals into the canonical spine), and 15 (declarable
intake-category model — the R3–R5 readiness *foundation*, inputs only) merged; **tagged `v0.2.0`** —
the Phase 2 documentation-compiler milestone, at the Slice‑14b commit. Slice 16 (R3 readiness
rules — the build-readiness auditor now consumes the Slice‑15 declared §4.3 technical categories
and lifts the cap from R2 to **R3**) **merged via PR #21 (commit `eaa9da1`).** **Slice 17 adds
read-only `GET /api/projects/{id}/{readiness,findings}` — exposing the latest persisted readiness
(Slices 12+16) and findings (Slice 13) snapshots over the Slice‑10 auth boundary; latest-only, no
compute/persist on GET, no migration/LLM/R4-R5 — merged via PR #23 (commit `eb19b4c`).**
Beyond the original scaffold: the persistence spine (async
SQLAlchemy + Alembic, four tenant-scoped tables, app-layer scoping, honest
liveness/readiness), DB-level tenant isolation via Postgres RLS (Slice 1b), a
tamper-evident hash-chained audit log (Slice 2), a deterministic autonomy policy
engine (Slice 3), an approval engine (Slice 4), a tool broker skeleton (deny-by-default
decision chokepoint composing policy + approval, Slice 5), an agent registry (global
blueprints + immutable content-hashed versions + tenant-scoped instances, Slice 6), a
cost ledger (immutable `cost_events` + per-project `budgets` + a deterministic
stop-condition decision, Slice 7), a durable workflow-runtime substrate (LangGraph +
a custom UAID-owned RLS checkpointer, run state machine, immutable `run_steps`,
crash→resume, Slice 8a), runtime integration (subject-scoped approval
wait/resume, node retry/backoff, cost STOP→pause, Slice 8b), a document
intake sandbox (untrusted-data documents: deterministic injection scan + quarantine,
instruction/data labeling, DB-verified content integrity, Slice 9), a read-only
JSON dashboard API behind hashed bearer-key tenant auth (§18.6, Slice 10), **and a
deterministic, provenance-backed canonical intake spine — tenant-owned, append-only
`intake_artifacts` + `intake_provenance` with DB-enforced Sanad source-count and
accepted-document-only pinning (Phase 2, Slice 11)**, **and a deterministic,
fail-closed build-readiness auditor over that spine — R0–R2 from the spine, **R3 when the
three §4.3 technical categories are declared** (Slice 16), emitting the §4.5
validation report as an immutable `readiness_reports` snapshot (Phase 2, Slices 12 + 16)**,
**and a deterministic gap & structural contradiction detector over the spine —
descriptive findings (gaps + structural contradictions) as an immutable
`intake_findings_reports` snapshot, no readiness claims (Phase 2, Slice 13)**, **and an
LLM-assisted extractor that turns an accepted document into inert, provenance-verified
proposals requiring human review (budget-gated, injection-hard-refused, no
auto-promotion) (Phase 2, Slice 14a)**, **and deterministic promotion of human-approved
proposals into canonical spine artifacts via `add_artifact` — promotion-time evidence
re-verification + §16.5 assumption gating + idempotent append-only link (Phase 2,
Slice 14b)**, **and a declarable intake-category model — the §4.2 categories
recorded as provenance-backed, secret-safe declarations (R3–R5 readiness *foundation*, inputs
only) (Phase 2, Slice 15)**, **and the Slice 16 R3 readiness rules that consume those
declarations (R2 → R3 on the declared §4.3 technical trio; staging = R3 AND environments
declared) — capping the auditor at R3**.
The rest of the engine described in the spec
(**semantic** contradiction analysis, **R4–R5 readiness rules** + the gated
autonomy/approval/cost/production-authority engines, agent factory,
maker-checker-verifier, evidence packs, etc.) is **not** implemented. Do not assume any
spec capability exists unless it is listed under "What exists" below.

Slice plan/status live in `.planning/PHASE-1-PLAN.md`. **Tenant isolation now holds
at two layers simultaneously:** app-layer (repository scoping + schema FKs, INV-1..4)
and DB-level RLS (INV-5). RLS is enforced because the runtime connects as a dedicated
**non-superuser role `uaid_app`** (superusers/owners bypass RLS); migrations run as
the admin `app` role only.

## What exists

### Stack (installed, Python 3.11 via uv — see `pyproject.toml` / `uv.lock`)
- **FastAPI + uvicorn** — web/API surface (`app/main.py`)
- **SQLAlchemy 2 + asyncpg + Alembic** (Postgres + migrations), **redis**, **chromadb** (vector store)
- **langgraph** (agent orchestration), **anthropic** + **openai** SDKs (LLM calls)
- **numpy + scipy** (deterministic compute) — `app/compute/`
- **pytest + pytest-asyncio + ruff** (dev)

### Code skeleton
- `app/main.py` — FastAPI app; `/health/live` + `/health/ready` (real `SELECT 1`,
  503 when DB down), a `/demo` endpoint that exercises the kernel below, and the Slice‑10
  read-only `/api` dashboard router. The old fake `/health` was removed. DB engine
  disposed on shutdown via lifespan.
- `app/api/` — read-only JSON dashboard (Slice 10, §18.6; D3 API-only / D4 bearer-key auth).
  `auth.py`: `require_tenant` dependency — the **single** place untrusted HTTP input becomes a
  tenant. Parses `Authorization: Bearer <key>`, resolves it (hash → active `tenant_api_keys`
  row) on a **plain pre-tenant session**, returns `TenantContext`; missing/malformed/unknown/
  revoked ⇒ **401, no fallback tenant**. `dashboard.py`: GET-only, project-scoped endpoints
  (`/api/projects/{id}/{runs,approvals,blockers,cost,readiness,findings}`) that open `tenant_scope`
  and read via existing repos — a cross-tenant `project_id` yields nothing (RLS). **Slice 17** added
  `readiness`/`findings`: each returns the **latest persisted snapshot** via `repo.latest`
  (read-only SELECT) or `null` — never-evaluated, cross-tenant, and nonexistent `project_id` are
  indistinguishable (`200` + `null`, no existence oracle); a GET never computes or persists.
  `app/repositories/api_keys.py`:
  `TenantApiKeyRepository` (admin `issue`/`revoke`; runtime `resolve`); raw key generated with
  `secrets.token_urlsafe(32)`, **only the `sha256:` hash stored**, raw returned once. **D4 hardening
  (migration 0013):** `resolve` calls the **`SECURITY DEFINER`** function `resolve_tenant_api_key(hash)`
  (owned by the least-privilege NOLOGIN `api_key_resolver`); `uaid_app` has **EXECUTE only, no direct
  SELECT** on the key table; only the hash is passed to SQL (raw key never enters statement/logs).
  `app/models/tenant_api_key.py` (**global** auth-lookup — intentionally NOT RLS).
  **Skeleton: read-only; covers the implemented §18.6 subset (run state / open approvals / blockers /
  cost + stop decision / readiness snapshot / findings snapshot [Slice 17]); forecast / critical path /
  evidence-pack / deployment / next-action deferred; no web UI; no auth-event audit; admin-path key
  issuance only.**
- `app/health.py` — liveness/readiness handlers; readiness's DB ping is injected
  via a FastAPI dependency (`get_db_ping`) so it is overridable in route tests.
- `app/db.py` — lazy async engine + session factory from `settings.database_url`
  (the **runtime `uaid_app`** role); `ping()` (real round-trip for readiness),
  `get_session()` dependency, `dispose_engine()`.
- `app/models/` — `Base` (deterministic constraint naming) + the four spine tables:
  `organizations` (root), `tenants` (isolation boundary), `projects`, `project_runs`
  (both tenant-owned: `tenant_id NOT NULL` FK→`tenants`; runs pinned to their project's
  tenant by composite FK `(project_id, tenant_id)→projects(id, tenant_id)`).
- `app/tenancy.py` — `TenantContext` + `TenantScopedRepository` (app-layer INV-4) **and
  `tenant_scope(context)`**: an async context manager that opens a transaction and sets
  the `app.current_tenant` GUC (`set_config(..., true)`) on the **same** connection that
  runs the queries — the runtime binding RLS reads (INV-5). Cross-tenant writes raise
  `CrossTenantError` (app layer) and are blocked by RLS `WITH CHECK` (DB layer).
- `app/repositories/projects.py` — tenant-scoped CRUD for `projects` (use inside `tenant_scope`).
- `app/audit.py` — audit-log service (Slice 2, §16.6). `record(session, *, action, actor,
  target, payload)` appends via the DB `audit_append` function (tenant derived from the
  `app.current_tenant` GUC — **no tenant param**; call inside `tenant_scope`); returns only
  `{id, entry_hash, created_at}`. `verify_chain(admin_session)` runs the full-chain check
  (admin only). No engine/admin creds in the module.
- `app/models/audit_log.py` — **read-only** ORM model for `audit_logs` (writes go via the
  DB function, never the ORM).
- `app/policy/` — autonomy policy engine (Slice 3, §5/§2.6). `levels.py`
  (`AutonomyLevel` A0–A5), `matrix.py` (code authority matrix + **tighten-only**
  `apply_overrides`/`validate_overrides`; §2.6 actions flagged `mandatory_approval`
  and structurally non-bypassable), `engine.py` (pure deny-by-default
  `check_authority(action, level, overrides) -> Decision{ALLOW,DENY,NEEDS_APPROVAL}`).
- `app/models/autonomy_policy.py` — tenant-owned `autonomy_policies` (per-project
  level + overrides jsonb; composite FK to projects). `app/repositories/autonomy_policies.py`
  — `decision_for` (**fail-closed**: missing policy ⇒ DENY, invalid persisted override ⇒ DENY)
  and `upsert` (validates overrides, audits the change via `audit_append` with safe metadata;
  `actor` is an **untrusted** caller label until request-auth exists).
- `app/approvals/states.py` — pure approval state machine (Slice 4, §18): `Status`
  (pending/approved/rejected/cancelled/expired/proceeded_by_policy), `RiskTier`, transition
  validation, non-response policy (`compute_deadline`/`auto_transition`, §18.5 24h), and the
  fail-closed `is_blocked` gate. The **non-bypassable** rule: `requires_explicit_approval`
  (forced True for §2.6 actions via `app.policy.matrix.is_mandatory_action`) ⇒ only `APPROVED`
  unblocks; low-risk non-response can never bypass it. `PROCEEDED_BY_POLICY` unblocks only
  non-explicit low-risk after deadline; `EXPIRED` (medium) stays blocking; high/production never lapse.
- `app/models/approval.py` + `app/models/approval_event.py` — tenant-owned `approvals`
  (RLS; SELECT/INSERT/UPDATE, **no DELETE**) and append-only `approval_events`
  (RLS; SELECT/INSERT only). `app/repositories/approvals.py` — `ApprovalRepository`:
  request/approve/reject/cancel/expire_if_overdue + `is_blocked` gate + `latest_for(project,
  action, subject_ref=None)`; each transition writes an `approval_events` row + an `audit_log`
  entry. `requested_by`/`resolved_by` **untrusted**; `approver_provenance='caller_supplied_unverified'`
  — NOT verified human approvals. No scheduler (on-demand expiry).
- `app/tools/` — tool broker skeleton (Slice 5, §11). `registry.py` (code `TOOL_REGISTRY`
  catalog; deny-by-default unknown tools; `sanitize_params` — mapping-only, secret-key redaction,
  ≤16 KiB), `broker.py` (`broker_call` decision pipeline → `BrokerDecision`). Composes Slice 3
  authority + Slice 4 approval, **tool-scoped** (`subject_ref="tool:<name>"`). Two provenance
  gates keep it a safe **skeleton (no real execution)**: an unverified approval ⇒
  `NEEDS_AUTHENTICATED_APPROVAL`; the success terminal is `ALLOWED_UNVERIFIED_IDENTITY` (never
  bare ALLOWED). `app/models/tool_call.py` (tenant-owned, append-only, redacted params) +
  `app/models/agent_tool_allowlist.py` (append-only **grant/revoke ledger** with a monotonic
  `seq`; latest event decides). `app/repositories/tools.py` — `ToolAllowlistRepository`
  (grant/revoke/is_allowed, audited) + `ToolCallRepository.record` (records every attempt +
  audit; audit never includes params). `agent_id` is an **untrusted** label (the Slice-6
  agent registry is **not** wired to the broker yet).
- `app/agents/` — agent registry (Slice 6, §9.7/§17.4/§22.2). `registry.py`: `ARCHETYPES`
  (§9.5.1 set), `compute_content_hash` (deterministic `sha256:` over the §22.2 snapshot),
  admin-path `register_blueprint`/`register_version` (validate the six component hashes;
  idempotent on `content_hash`; changed content ⇒ new version), and `AgentInstanceRepository`
  (tenant-scoped instantiate/bind_to_run/suspend/retire, each audited). `app/models/agent_blueprint.py`
  (**global**, admin-curated role identity) + `app/models/agent_version.py` (**global**, **immutable**:
  UPDATE/DELETE/TRUNCATE triggers; stores hashes only — no tenant content) + `app/models/agent_instance.py`
  (**tenant-owned**, RLS; `version_id` only; triple FK pins run→project→tenant; binding columns
  immutable + `active_run_id` set-once via trigger; partial unique on live `(tenant,project,instance_key)`).
  `actor` is an **untrusted** label. **Skeleton: no Agent Factory / eval execution / model routing /
  agent execution / broker wiring.**
- `app/cost.py` + `app/repositories/cost.py` — cost ledger (Slice 7, §19). `app/cost.py` (pure):
  `COST_COMPONENTS` (§19.2), `to_decimal` money guard (rejects float/bool/negative/non-finite/>6dp),
  `evaluate_stop` (deny-by-default: missing budget ⇒ STOP `no_budget`; threshold `>=`), exceptions
  (`InvalidAmount`/`InvalidComponent`/`IdempotencyConflict`). `app/repositories/cost.py`:
  `CostEventRepository.record` (validates + **always records incurred cost, even over budget**;
  **source-namespaced idempotency** via `INSERT … ON CONFLICT DO NOTHING` + re-select — identical
  retry returns the row, material mismatch raises `IdempotencyConflict`; audited on insert only),
  `total_spent`/`daily_spent` (on-demand SUM; daily uses **UTC half-open bounds**), `BudgetRepository`
  (`get`/`upsert` audited with **before/after caps**), module-level `evaluate` (§19.7 stop decision,
  **returned not halting**). `app/models/cost_event.py` (**tenant-owned, IMMUTABLE**:
  UPDATE/DELETE/TRUNCATE triggers; `NUMERIC(18,6)`; CHECK amount/quantity ≥ 0 + DB-enforced
  `component` in the §19.2 set; triple FK pins run→project→tenant; partial unique idempotency
  index) + `app/models/budget.py` (tenant-owned;
  one per project). `actor` is an **untrusted** label. **Budget changes are audited but NOT verified
  human approvals.** **Skeleton: no price cards / provider calls / model routing / billing UI /
  workflow runtime (stop signal is decision-only) / broker-agent wiring.**
- `app/runtime/` — durable workflow-runtime substrate (Slice 8a, §23.2; D2 = LangGraph +
  custom UAID checkpointer). `checkpointer.py`: `UAIDCheckpointer(BaseCheckpointSaver)` —
  async `aput`/`aput_writes`(+`task_path`)/`aget_tuple`/`alist`/`adelete_thread` over
  **UAID-owned** RLS tables (NOT LangGraph's `.setup()` tables); serializes via LangGraph's
  serde to BYTEA; `thread_id == str(run_id)`. `engine.py`: a minimal deterministic demo graph
  + `start_demo_run`/`resume_demo_run` proving **crash→resume** (static `interrupt_after`
  durability boundary). `app/repositories/runs.py`: `RunRepository` — validated `project_runs`
  state transitions + append-only `run_steps`, audited. `app/models/run_checkpoint.py` +
  `run_checkpoint_write.py` (**mutable working state**; `adelete_thread` cleans them) +
  `run_step.py` (**immutable** append-only history; UPDATE/DELETE/TRUNCATE triggers).
  **"Deterministic replay" here = state reconstruction from checkpoints + `run_steps` + the
  existing audit/tool/cost ledgers — NOT Temporal-style automatic re-execution.**
  **Slice 8b — runtime integration** (`engine.py`): subject-scoped **approval wait/resume**
  (sentinel `approval_gate` before the protected node + `interrupt_after`; engine requests a
  `workflow.resume` approval [tier `high`, `requires_explicit_approval=True`, subject
  `run:<id>:node:<protected>`], `running→blocked`; APPROVED ⇒ resume→complete, terminal
  denial ⇒ `blocked→failed`, PENDING ⇒ stays blocked) using the additively-extended
  `ApprovalRepository.is_blocked(..., subject_ref=None)`; node **retry/backoff** via LangGraph
  `RetryPolicy` (`retried` recorded only for attempts > 1; non-retryable ⇒ `failed`); **cost
  STOP→pause** consuming Slice-7 `evaluate` at the step boundary (`running→paused` before the
  node). **Still skeleton: no tool-result persistence / §23.3 loop / distributed workers; cost
  guard is opt-in per run (not yet mandatory for every run); LangGraph native `interrupt()` not
  used (the gate decision lives in the audited approval engine).**
- `app/intake/` — document intake sandbox (Slice 9, §16.3). `sandbox.py` (pure): treats
  customer documents as **untrusted data** — `scan(content)` is a **best-effort, deterministic**
  prompt-injection signal returning marker **identifiers** (never raw excerpts; no ML);
  `as_untrusted_block` labels content as data with a do-not-follow preamble; validators
  (content ≤1 MiB non-empty, `content_type`/`source` allowlists, bounded `filename`, no NUL) +
  `content_hash` (`sha256:`). `app/repositories/documents.py`: `DocumentRepository` —
  `ingest` (validate→scan→store; status `accepted`/`quarantined`; **idempotent on
  `(tenant,project,content_hash)`**; audited with metadata + marker ids, **never the body**),
  one-way reviewer `quarantine`, `list_usable` (accepted only). `app/models/document.py`
  (tenant-owned, RLS). **Guarantee = instruction/data separation + no LLM wired; scanning is
  best-effort, not a detection guarantee.** **Skeleton: no Documentation Compiler / ML / RAG /
  binary parsing / malware scanning / per-section quarantine.**
- `app/intake/compiler.py` + `app/repositories/intake.py` — canonical intake spine (Phase 2,
  Slice 11, §3.4/§4.2/§4.4). `compiler.py` (pure, **no LLM**): `ARTIFACT_KINDS`
  (`requirement`/`acceptance_criterion`/`test_oracle`/`assumption`), `ASSUMPTION_CLASSIFICATIONS`
  (§4.4 machine values), `SourceInput`, `validate_kind`/`validate_classification`, and
  `assert_sources` — the **fail-closed Sanad gate** built on `app/core/provenance.py`
  (`Fact`/`Source`/`NoFreeFactsError`). `IntakeRepository.add_artifact` validates kind +
  classification, **fails closed if no source is supplied**, pre-checks each document-backed
  source against the tenant-scoped `DocumentRepository` (must exist, be **accepted**, same
  project), then writes the artifact + its sources and audits **safe metadata only — never
  title/body/data**. `app/models/intake_artifact.py` (**tenant-owned, append-only**; unified
  `kind` table; self triple-FK `parent_id` pins a child to the same project+tenant; tightened
  §4.4 classification CHECK — assumptions **must** carry one valid value, others **must** be
  NULL) + `app/models/intake_provenance.py` (**tenant-owned, append-only** Sanad sources;
  composite FK pins a document-backed source to the **same tenant+project accepted document**;
  NULL `document_id` = non-document origin, skips the doc FK). **DB invariants:** a **deferrable
  constraint trigger** rejects any artifact that commits with zero provenance; a **BEFORE INSERT**
  trigger rejects non-accepted document sources; both tables append-only (SELECT/INSERT;
  UPDATE/DELETE/TRUNCATE blocked) + ENABLE+FORCE RLS + `tenant_isolation`. `app/models/document.py`
  gains an additive `UNIQUE(id, project_id, tenant_id)` (the document composite-FK target — the
  only change to the Slice‑9 table). **Skeleton: deterministic only — no LLM/classifier/extractor,
  no build-readiness auditor (Slice 12), no gap/contradiction detector (Slice 13), no artifact
  generation, no API exposure.**
- `app/intake/readiness.py` + `app/repositories/readiness.py` — deterministic build-readiness
  auditor (Phase 2, Slice 12 base + **Slice 16 R3 rules**, §4.3/§4.4/§4.5). `readiness.py` (pure,
  **no LLM**): `evaluate_readiness` reads a snapshot of spine artifacts **plus the Slice‑15 declared
  intake categories** (`CategoryDeclarationView(category, status)`) and emits the §4.5 report,
  **fail-closed and capped at R3**. Ladder: R0 = no requirements; R1 = no valid requirement→acceptance
  chain; R2 = ≥1 valid chain; **R3 = R2 base PLUS the three §4.3 technical categories declared —
  `architecture_and_technology_constraints`, `data_model_and_contracts`, `user_journeys_and_workflows`**
  (presence of a provenance-backed declaration, not content quality). R4/R5 require the gated engines +
  secrets/tooling/go-live/test-coverage rules and are **out of scope**. **Parent-kind validation does
  not trust the DB FK alone** — an acceptance criterion counts only if its parent is a `requirement`,
  an oracle only if its parent is that `acceptance_criterion`; orphan/wrong-kind links become
  `spine_gaps` and never raise the level. **`can_build_to_staging` is true only at R3 AND when
  `environments_and_deployment_targets` is declared** (D‑3b); **`can_go_live_autonomously` is always
  false** (capped < R5; gated categories unevaluated) — both with exact recorded reasons. The `report`
  carries the §4.5 keys + deterministic extensions (`readiness_cap`, `readiness_cap_reason`,
  `not_assessed_categories` [**20 categories**], `spine_gaps`, **`missing_r3_categories`**,
  `production_authority_decision`, `ruleset_version="slice16.v1"`); `missing_for_go_live` also lists
  `r3_category_not_declared:<category>`. `ReadinessRepository`
  (`evaluate`/`evaluate_and_record`/`latest`/`history`) reads the Slice‑15 declarations (D‑6: a
  doc-backed declaration counts only if its source document is still `accepted` — drops a
  later-quarantined source; same-project is enforced upstream by the `intake_categories` FK, with
  a defense-in-depth check in the repo),
  wires the **Slice‑3** autonomy policy via `decision_for(project_id, "deploy_production")` as
  **transparent context only** (mandatory-approval ⇒ `needs_approval`/`deny`, never authorization;
  never makes go-live true), and audits **safe metadata only — no assumption titles / report body**.
  `app/models/readiness_report.py` (`ReadinessReportRecord`, table `readiness_reports`): **tenant-owned,
  RLS, append-only**; `readiness_level` CHECK allows R0..R5 (forward-compat); the code now emits
  R0/R1/R2/R3; `created_at` uses `clock_timestamp()` so same-transaction snapshots order
  deterministically (`latest`/`history` order `created_at DESC, id DESC`). **Skeleton: deterministic
  only — no LLM, no evidence pack, no new artifact kinds, no HTTP/API endpoint; R4/R5 + gated-category
  completion out of scope (no migration — `readiness_level` already allowed R0..R5).**
- `app/intake/findings.py` + `app/repositories/findings.py` — deterministic gap & structural
  contradiction detector (Phase 2, Slice 13, §4.4/§14.4/§16.5). `findings.py` (pure, **no LLM**,
  **no semantic analysis**): `StructuralArtifactView` carries **only** structural fields
  (`id`/`kind`/`ref`/`parent_id`/`classification`) — never `title`/`body`/`data`, so "structural-only"
  is enforced by the type. `detect_findings` reports **gaps** (`G_NO_REQUIREMENTS`,
  `G_REQUIREMENT_WITHOUT_ACCEPTANCE`, `G_ACCEPTANCE_WITHOUT_ORACLE`, `G_UNRESOLVED_ASSUMPTION`) and
  **structural contradictions** (`C_REQUIREMENT_HAS_PARENT`, `C_WRONG_KIND_PARENT`,
  `C_ORPHAN_ACCEPTANCE`, `C_ORPHAN_ORACLE`, `C_SELF_PARENT`). **`C_SELF_PARENT` is generic across all
  kinds** (a first pass before kind-specific checks, so a requirement self-parent is not shadowed);
  parent-kind validation does **not** trust the DB FK alone; findings use refs only and are
  **deterministically sorted**. (Multi-node parent cycles are structurally impossible under
  append-only + parent-pre-exists-at-insert, so only self-parent is guarded.) `FindingsRepository`
  (`evaluate`/`evaluate_and_record`/`latest`/`history`) reads only structural fields, audits
  **counts/metadata only** (no refs/titles/body/report JSON), and orders `latest`/`history` by
  `created_at DESC, id DESC`. `app/models/intake_findings_report.py` (`IntakeFindingsReport`, table
  `intake_findings_reports`): **tenant-owned, RLS, append-only**; `gap_count`/`contradiction_count`
  `CHECK >= 0`; `created_at` `clock_timestamp()`. The findings detector is kept **separate** from
  `readiness.py` (no consolidation). **Skeleton: descriptive only — no readiness claims, no semantic contradiction
  analysis, no LLM, no evidence pack, no new artifact kinds, no HTTP/API endpoint.**
- `app/llm/` + `app/intake/extraction.py` + `app/repositories/extraction.py` — LLM-assisted
  extractor (Phase 2, Slice 14a, §2.1/§2.2/§2.4/§16.3/§16.5/§19). **The first real LLM integration;
  the model produces only inert proposals that a human must approve — it never writes authoritative
  facts or takes actions.** `app/llm/`: `LLMClient` protocol + `FakeLLMClient` (**all tests/CI — no
  network, no key**) + `AnthropicClient` adapter (**shipped, never exercised in tests**; key env-only,
  fail-closed, redacted) + `pricing.py` (operator-supplied `PRICE_CARD`, **empty by default**;
  unpriced ⇒ `UnpricedModelError`). `extraction.py` (pure): strict-JSON parse, conservative
  cost projection (`CHARS_PER_TOKEN_CONSERVATIVE=3`, `PROMPT_OVERHEAD_TOKENS=4096`),
  `as_untrusted_block` prompt, verbatim-evidence verification. `ExtractionRepository.extract`:
  accepted-doc only → fail-closed config (model + **price values via the ledger money guard**) →
  **injection hard-refuse before the call** → **projected-cost budget preflight** (deny-by-default:
  no budget / over / projected-over ⇒ **no provider call**) → call (fake in tests) → **cost only on a
  successful response with positive tokens** (`model_inference`, `external_ref=extraction_run:<run_id>:
  provider_request`; missing/zero usage ⇒ failed run, no cost) → drop hallucinated quotes → persist an
  immutable run + inert `pending` proposals → audit **safe metadata only**. `review_proposal` enforces
  one-way `pending→approved|rejected` + `reviewed_by != extracted_by` + `reviewed_at`.
  `app/models/extraction_run.py` (**tenant-owned, append-only** immutable final-outcome rows, app-minted
  `run_id`, accepted-doc composite FK) + `app/models/extraction_proposal.py` (**tenant-owned**;
  content-immutable; one-way lifecycle + distinct-reviewer + frozen-once-decided review metadata — all
  enforced by the `extraction_proposals_guard` trigger). Both ENABLE+FORCE RLS + `tenant_isolation`.
  **Skeleton: no auto-promotion to the spine (Slice 14b), no HTTP endpoint, no live provider calls in
  tests; real-model quality/eval is future work; price card ships empty (fail-closed until configured).**
- `app/repositories/extraction.py` (Slice 14b promotion methods) + `app/models/extraction_promotion.py`
  — deterministic promotion of human-approved proposals into the canonical spine (§2.2/§2.4/§16.5).
  `promote_proposal`: eligibility (`approved` only) → **idempotent** (returns the existing artifact if
  already promoted; one promotion per proposal via `UNIQUE(tenant, proposal)`) → promotable-kind
  (`test_oracle` refused; `parent_id` only for `acceptance_criterion`) → **promotion-time re-verification**
  (re-load source doc: accepted + same project; `evidence_quote` must be a **verbatim substring** — the
  trust boundary, not trusting 14a alone) → §16.5 assumption gating (`safe_assumption` promotes;
  `unsafe_assumption_blocked`/`unknown_cannot_proceed` **hard-refuse**; `needs_approval` blocked until a
  distinct subject-scoped approval-engine approval) → optional AC parent validated (exists, same project,
  `kind=requirement`) → `IntakeRepository.add_artifact` (title=`proposed_text`, body=None,
  data=`{extraction_proposal_id}`, classification, ref=`PREFIX-EXT-<proposal8hex>`, source=`document:<id>`
  + locator=`evidence_quote`) → append-only `extraction_promotions` link → audit (safe metadata only).
  `request_promotion_approval`: idempotent, **requires the proposal already approved** (two-gate model),
  safe-metadata payload. `extraction_promotions` is tenant-owned, append-only, RLS ENABLE+FORCE, with
  composite FKs pinning proposal + artifact to the same tenant/project; `extraction_proposals` gains a
  composite `UNIQUE(id, project_id, tenant_id)` (FK target). **Skeleton: promotion only — no LLM, no HTTP
  endpoint, no proposal mutation.**
- `app/intake/categories.py` + `app/models/intake_category.py` + `app/repositories/intake_categories.py`
  — declarable intake-category model (Phase 2, Slice 15, §4.2/§4.3/Appendix A). `categories.py` (pure):
  partitions the **authoritative §4.2 26-file universe** (+ Appendix‑A `production_authority`) into three
  disjoint sets — `SPINE_CATEGORIES` (3, already `intake_artifacts` kinds), `GATED_ENGINE_CATEGORIES`
  (4: `autonomy_policy`/`human_approval_policy`/`cost_and_resource_policy`/`production_authority` —
  evaluated later from Slices 3/4/7 + the policy matrix, **not** declarable and **not** verified-complete),
  `DECLARABLE_INTAKE_CATEGORIES` (20). File 14 `architecture_and_technology_constraints` = architecture +
  stack. Validators: declarable-only category; non-secret `data` (secrets = reference-only
  `{manager, reference_name}`, inline values rejected); **source XOR** (document+locator+no-origin vs
  origin-only), fail-closed. `IntakeCategoryRepository` (`declare`/`revise`/`list_categories`/`get_category`)
  pre-checks document sources (accepted, same project) and audits **safe metadata only**
  (`has_source_document`/`has_origin` booleans — never the UUID/locator/summary/data/secret). `IntakeCategory`
  (table `intake_categories`): tenant-owned, RLS ENABLE+FORCE; one declaration per `(tenant, project,
  category)`; source-XOR + bounds CHECKs; guard trigger (accepted-source-doc + immutable
  `id`/`tenant_id`/`project_id`/`category`/`created_at`); **no DELETE/TRUNCATE**; `data` JSONB;
  SELECT/INSERT/UPDATE grants. **Skeleton: inputs only — Slice 15 itself adds no readiness computation;
  the R3 rule that consumes these declarations lands in Slice 16 (the auditor is now R3-capped). No HTTP
  endpoint, no LLM, no secret values, no new spine kinds; gated categories + R4/R5 deferred to a later
  engine-reading readiness slice.**
- `migrations/` — Alembic (async `env.py`; URL = `ALEMBIC_DATABASE_URL` → `admin_database_url`,
  **admin only — never `uaid_app`**). `0001` (spine); `0002` (ENABLE+FORCE RLS on
  `projects`/`project_runs`, deny-by-default `tenant_isolation` policy, grants to `uaid_app`);
  `0003_audit_log.py` (append-only hash-chained `audit_logs`: SECURITY DEFINER `audit_append`
  [GUC-derived tenant, minimal return] + `audit_verify` owned by `audit_writer`, shared
  `audit_entry_hash` helper, REVOKE UPDATE/DELETE + append-only trigger; core `sha256`, no extension);
  `0004_autonomy_policies.py` (tenant-owned `autonomy_policies`: ENABLE+FORCE RLS +
  `tenant_isolation` policy; grants `SELECT, INSERT, UPDATE` to `uaid_app` — **no DELETE**);
  `0005_approvals.py` (tenant-owned `approvals` [SELECT/INSERT/UPDATE, no DELETE] + append-only
  `approval_events` [SELECT/INSERT only]; both ENABLE+FORCE RLS + `tenant_isolation`);
  `0006_tool_broker.py` (tenant-owned append-only `tool_calls` + `agent_tool_allowlist` ledger
  [both SELECT/INSERT only]; both ENABLE+FORCE RLS + `tenant_isolation`);
  `0007_agent_registry.py` (**global** `agent_blueprints` + **immutable** `agent_versions`
  [`uaid_app` SELECT-only; UPDATE/DELETE/TRUNCATE triggers] + **tenant-owned** `agent_instances`
  [ENABLE+FORCE RLS + `tenant_isolation`; SELECT/INSERT/UPDATE, no DELETE; binding-immutability
  trigger]; adds `UNIQUE(id, project_id, tenant_id)` to `project_runs` for the triple FK);
  `0008_cost_ledger.py` (**tenant-owned, IMMUTABLE** `cost_events` [UPDATE/DELETE/TRUNCATE triggers +
  REVOKE; `uaid_app` SELECT/INSERT only; partial unique idempotency index] + tenant-owned `budgets`
  [SELECT/INSERT/UPDATE, no DELETE]; both ENABLE+FORCE RLS + `tenant_isolation`);
  `0010_runtime_events.py` (Slice 8b: expands the `run_steps.event_type` CHECK with
  `blocked_on_approval` / `retried` / `cost_paused`; no tables/columns/grants change);
  `0009_workflow_runtime.py` (tenant-owned **mutable** `run_checkpoints` [SELECT/INSERT/DELETE] +
  `run_checkpoint_writes` [SELECT/INSERT/UPDATE/DELETE; carries `task_path`] + **immutable**
  `run_steps` [UPDATE/DELETE/TRUNCATE triggers; SELECT/INSERT only]; all three ENABLE+FORCE RLS +
  `tenant_isolation`; triple FK `(run_id, project_id, tenant_id) → project_runs`);
  `0010_runtime_events.py` (expands `run_steps.event_type` CHECK: `blocked_on_approval`/`retried`/
  `cost_paused`); `0011_documents.py` (**tenant-owned** `documents`: ENABLE+FORCE RLS +
  `tenant_isolation`; SELECT/INSERT/UPDATE, no DELETE; metadata/format CHECKs; combined
  `documents_guard` trigger — content integrity [size + core-`sha256` hash] on INSERT, content/identity
  immutability + one-way `accepted→quarantined` lifecycle on UPDATE);
  `0013_key_resolver.py` (D4 hardening: `SECURITY DEFINER` `resolve_tenant_api_key(text)` owned by
  `api_key_resolver`, `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE` to `uaid_app`; `GRANT SELECT` on
  `tenant_api_keys` to `api_key_resolver`, `REVOKE SELECT` from `uaid_app`; downgrade restores 0012);
  `0012_tenant_api_keys.py` (**global** `tenant_api_keys` auth-lookup — **NOT RLS** [resolution is
  pre-tenant]; hash-only `key_hash` with format CHECK + UNIQUE, bounded `label`, status CHECK; grant
  `SELECT` to `uaid_app`); `0014_intake_spine.py` (Slice 11: **tenant-owned, append-only**
  `intake_artifacts` [unified `kind` table; self triple-FK `parent_id`; tightened §4.4 classification
  CHECK] + `intake_provenance` [Sanad sources; composite FK `(document_id, project_id, tenant_id) →
  documents`]; both ENABLE+FORCE RLS + `tenant_isolation`, SELECT/INSERT only + UPDATE/DELETE/TRUNCATE
  block triggers; a **DEFERRABLE** constraint trigger enforcing ≥1 provenance per artifact; a BEFORE
  INSERT accepted-document-only trigger; plus an additive `documents` `UNIQUE(id, project_id, tenant_id)`
  as the composite-FK target); `0015_readiness_reports.py` (Slice 12: **tenant-owned, append-only**
  `readiness_reports` — ENABLE+FORCE RLS + `tenant_isolation`, SELECT/INSERT only + UPDATE/DELETE/TRUNCATE
  block triggers; `readiness_level` CHECK `R0..R5`; `created_at` default `clock_timestamp()`; composite FK
  `(project_id, tenant_id) → projects`; no change to existing tables); `0016_intake_findings_reports.py`
  (Slice 13: **tenant-owned, append-only** `intake_findings_reports` — ENABLE+FORCE RLS +
  `tenant_isolation`, SELECT/INSERT only + UPDATE/DELETE/TRUNCATE block triggers; `gap_count`/
  `contradiction_count` `CHECK >= 0`; `created_at` default `clock_timestamp()`; composite FK
  `(project_id, tenant_id) → projects`; no change to existing tables); `0017_extraction.py`
  (Slice 14a: **tenant-owned** `extraction_runs` [append-only: SELECT/INSERT only + UPDATE/DELETE/
  TRUNCATE block triggers; accepted-source-doc BEFORE INSERT trigger; `UNIQUE(id, project_id, tenant_id)`]
  + `extraction_proposals` [SELECT/INSERT/UPDATE, no DELETE; `extraction_proposals_guard` trigger =
  accepted-doc on insert + content immutability + one-way `pending→approved|rejected` + distinct-reviewer
  & `reviewed_at` required & review metadata frozen once decided]; both ENABLE+FORCE RLS +
  `tenant_isolation`; no change to existing tables); `0019_intake_categories.py` (Slice 15:
  **tenant-owned** `intake_categories` — one declaration per `(tenant, project, category)` over the 20
  declarable §4.2 categories; source-XOR CHECK (document+locator XOR origin); composite FK to accepted
  same-project `documents`; guard trigger [accepted-doc + immutable id/tenant/project/category/created_at];
  no DELETE/TRUNCATE; ENABLE+FORCE RLS + `tenant_isolation`; SELECT/INSERT/UPDATE grants; no change to
  existing tables); `0018_extraction_promotions.py` (Slice 14b:
  additive `extraction_proposals` `UNIQUE(id, project_id, tenant_id)` + **tenant-owned, append-only**
  `extraction_promotions` [composite FKs → `extraction_proposals` and `intake_artifacts`;
  `UNIQUE(tenant_id, extraction_proposal_id)` promote-once; ENABLE+FORCE RLS + `tenant_isolation`;
  SELECT/INSERT only + UPDATE/DELETE/TRUNCATE block triggers]).
- `scripts/bootstrap_rls_role.sql` — idempotent roles: `uaid_app` (LOGIN, password from
  `RLS_DB_PASSWORD` via psql `\getenv`, never committed), **`audit_writer`** (NOLOGIN — limited
  SECURITY DEFINER owner of the audit functions), and **`api_key_resolver`** (NOLOGIN — limited
  SECURITY DEFINER owner of the API-key resolver; SELECT on `tenant_api_keys` only). Run by
  `make db-bootstrap-rls-role`. **Must run before migrations 0003 / 0013 (which assign function
  ownership to these roles); `make test-db` bootstraps before migrating.**
- `app/config.py` — `Settings` (pydantic-settings) loaded from `.env`. Reads
  `DATABASE_URL` + `TEST_DATABASE_URL` (**runtime `uaid_app`**), `ADMIN_DATABASE_URL` +
  `TEST_ADMIN_DATABASE_URL` (**admin `app`**, migrations/bootstrap/seed only),
  `REDIS_URL`, `CHROMA_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and (Slice 14a)
  `LLM_EXTRACTION_MODEL` (**no default — empty fails closed**) + `LLM_MAX_OUTPUT_TOKENS`
  (default 2048). `RLS_DB_PASSWORD` is consumed by the Makefile (not a Settings field). Other
  `.env` keys (OpenRouter, Manus, Semantic Scholar, Perplexity) are **ignored** until added here.
- `app/core/provenance.py` — **Sanad / No-Free-Facts** primitive: a `Fact` must carry
  ≥1 `Source` or it raises `NoFreeFactsError`; `.isnad` renders the source chain.
  Minimal starting primitive — maps to spec §3.4, *not* the full provenance store.
- `app/core/reasoning.py` — **Muhasabah gate** primitive: `muhasabah_gate(answer, facts,
  extra_checks)` self-audits an output before it is returned. Minimal — maps to spec
  §3.2 (Al-Muhasibi wrapper), *not* the full reasoning kernel.
- `app/compute/` — reserved for deterministic NumPy/SciPy calculation cores.
- `tests/` — `test_provenance.py`, `test_health.py` (Docker-free) + `test_tenancy.py`,
  `test_rls.py`, `test_audit.py`, `test_policy.py`, `test_approvals.py`, `test_tools.py`,
  `test_agents.py`, `test_cost.py`, `test_runtime.py`, `test_runtime_8b.py`, `test_intake.py`,
  `test_intake_compiler.py`, `test_readiness.py`, `test_findings.py`, `test_extraction.py`,
  `test_extraction_promotion.py`, `test_intake_categories.py`, `test_api.py`
  (DB-backed `db` + Docker-free units) and `conftest.py`
  (admin fixtures build/seed `app_test`; `rls_engine` as `uaid_app`; per-test transaction rollback;
  auto-dispose of the `app.db` engine).
  **`make test` → 152 passing (Docker-free); `make test-db` → 235 passing (DB-backed: tenancy,
  readiness, RLS, audit, policy, approval, tool-broker, agent-registry, cost-ledger, runtime,
  document-intake, the read API [real-HTTP auth deny-by-default, cross-tenant denial via
  dependency→tenant_scope/RLS, read-only, catalog, + D4 SECURITY-DEFINER resolver: EXECUTE-only,
  no direct key-table read; **Slice 17 readiness/findings endpoints — latest snapshot, empty-state
  null, cross-tenant null, read-only/405, latest-ordering**], and the intake spine [Sanad fail-closed source-count via the
  deferrable constraint, document composite-FK cross-project/cross-tenant rejection,
  accepted-document-only trigger, append-only, the §4.4 classification CHECK, RLS + cross-tenant],
  the readiness auditor [R0–R3 ladder, R3 = declared §4.3 technical trio, staging = R3 AND
  environments declared, always-false go-live, D-6 stale-source exclusion (quarantined source
  drops R3→R2; same-project pinning enforced upstream by the intake-category DB FK),
  deploy_production wiring, deterministic latest/history, RLS, append-only], and the
  gap/contradiction detector [taxonomy incl. generic
  C_SELF_PARENT, content-safe refs-only report + counts-only audit, RLS, append-only, count CHECKs],
  and the LLM extractor [FakeLLMClient only — no network; projected-cost preflight gating
  (no-budget/over/projected-over ⇒ no call), run-keyed cost idempotency, injection hard-refuse,
  hallucinated-evidence rejection, token/price fail-closed, DB review guard (distinct reviewer +
  frozen-once-decided), RLS, append-only runs, accepted-doc pinning, audit safety], and proposal
  promotion [eligibility + idempotency, promotion-time evidence re-verification, test_oracle/non-AC-parent
  refusal, parent validation, §16.5 assumption gating incl. approval-engine, approval-request idempotency
  + payload/audit safety, RLS, append-only], and intake category modeling [universe partition
  3/20/4, declarable/secret/source-XOR validators, readiness interaction (no declared categories ⇒ R2,
  cap now R3, R3-consumed categories drop from not-assessed), accepted-doc
  pinning, immutable keys, no-DELETE/TRUNCATE, RLS, catalog]).
  `make test-db` requires `RLS_DB_PASSWORD`.**

### Infra / tooling files
- `docker-compose.yml` — postgres:16, redis:7, chromadb. Pinned to compose project
  `name: uaid_os`. **Verified working** via `make up` (confirmed with `docker inspect`):
  - postgres `:5432` — **healthy** via Compose healthcheck (`pg_isready`).
  - redis `:6379` — **healthy** via Compose healthcheck (`redis-cli ping`).
  - chroma `:8001` — **running** (no Compose healthcheck; the image has no
    curl/wget/python to script one). Connectivity verified externally: `HTTP 200`
    on `/api/v2/heartbeat`.
  `make down` stops them; data persists in volumes `uaid_os_{pgdata,redisdata,chromadata}`.
- `Makefile` (`test`, `test-db`, `test-db-create/migrate/drop`, `db-bootstrap-rls-role`,
  `migrate`, `require-rls-pw`, `up/down/dev/fmt`), `alembic.ini`, `.gitignore`,
  `.env.example`, `.python-version`. `make test-db` fails closed if `RLS_DB_PASSWORD` is unset.
  The DB admin `psql` is parameterized via `PSQL` (default: `docker exec … uaid_os-postgres-1`;
  CI overrides with `PSQL=psql` to use a service container over TCP).
- `.github/workflows/ci.yml` — GitHub Actions CI on PRs + pushes to `main`: `uv sync`,
  `ruff check`, `make test` (Docker-free), and `make test-db` against a `postgres:16`
  **service** (CI-only non-secret creds; `RLS_DB_PASSWORD=uaid_app`). No real `.env`/secrets.

### Source-of-truth docs (preserved in `docs/`)
- The standalone spec (above).
- `docs/UAID_OS_Intake_Template_Pack_v1_2/` — the 26 canonical intake files.
  - `00`–`25` are **blank templates** (forms a customer fills per build); `19`–`22`
    carry the spec's default policy values.
  - `schemas/` (7 files) are **real, reusable schema/policy definitions**
    (agent realization, archetype eval methodology, reviewer QA, risk acceptance,
    model change, stabilization window, and `evidence_pack_schema.json`). Treat
    `schemas/` as canonical when implementing validation — they are product assets,
    not throwaway templates.

## How to run
```
make test                                  # Docker-free tests (no services) — 152 passing
RLS_DB_PASSWORD=... make test-db           # DB-backed tests (needs `make up`) — 235 passing
make fmt                                   # ruff format + lint
make up                                    # start Postgres/Redis/Chroma (needs Docker)
make dev                                   # run API at http://localhost:8000
```
`make test` runs `pytest -m "not db"` (Docker-free). `make test-db` bootstraps the
`uaid_app` role (needs `RLS_DB_PASSWORD`), creates+migrates `app_test` **as admin**,
then runs `-m db` with the runtime `uaid_app` connection. Migrations never run as
`uaid_app`. Endpoints: `/health/live`, `/health/ready`, `/demo`, and the read-only
`/api/projects/{id}/{runs,approvals,blockers,cost,readiness,findings}` (require `Authorization: Bearer <key>`).

## Conventions to uphold (from the spec — non-negotiable, including in our own code)
- **No fake done.** No placeholders/stubs/hardcoded outputs presented as real. Prefer
  an honest blocker over fake completion. (§2.1)
- **Evidence decides done.** Narratives aren't proof; tests/diffs/logs/reviews are. (§2.3, §15)
- **No agent approves its own work** — independent review for consequential outputs. (§2.2)
- **Fail closed on unsupported facts** — every factual/decision claim needs provenance
  (use the Sanad primitive). (§2.4)
- **Autonomy needs boundaries** — production deploys, secret changes, deletions, etc.
  require approval. (§2.6)

## Not yet present (future build items — not blockers for the skeleton)
- Durable workflow runtime (§23.2): **substrate (Slice 8a) + integration (Slice 8b) present** —
  D2 = LangGraph + a custom UAID-owned RLS checkpointer (NOT `.setup()` tables);
  `run_checkpoints`/`run_checkpoint_writes` (mutable; `task_path`) + immutable `run_steps`;
  `project_runs` state machine; **crash→resume**, **subject-scoped approval wait/resume**
  (terminal denial fails the run), **node retry/backoff**, **cost STOP→pause**. "Deterministic
  replay" = reconstruction from checkpoints + `run_steps` + ledgers, **not** Temporal-style
  automatic re-execution. **Deferred:** tool-result persistence, the §23.3 business loop,
  distributed multi-worker execution, durable timers/scheduler for approval deadlines (on-demand
  expiry only), per-node (vs step-boundary) cost hooks, making the cost guard mandatory for every
  run, LangGraph native `interrupt()`. Temporal revisit triggers in `.planning/PHASE-1-PLAN.md`.
- Knowledge-graph store (added when KG features are built).
- Multi-tenant isolation (§17): **present for the spine** — app-layer scoping + schema FKs
  (Slice 1) **and DB-level RLS** on `projects`/`project_runs` (Slice 1b). Future tenant-owned
  tables must add the same RLS policy + grants when introduced.
- Audit log (§16.6): **present (Slice 2)** — append-only, hash-chained, tenant-event-only.
  Deferred: external log sink, cryptographic signing, platform/system events, reviewer/tenant
  read APIs + audit-table RLS (Slice 10). Tamper-evident, not tamper-proof.
- Policy engine (§5/§2.6): **present (Slice 3)** — A0–A5 + authority matrix, deny-by-default,
  tighten-only overrides, §2.6 mandatory-approval non-bypassable, fail-closed. **Enforced by the
  Slice 5 broker for brokered tool decisions only; no broader runtime/workflow enforcement exists
  yet.** A5 auto-release gates + stop_conditions deferred.
- Approval engine (§18): **present (Slice 4)** — request→await→resolve, risk tiers + non-response
  policy, fail-closed gate, non-bypassable `requires_explicit_approval` for §2.6 actions.
  **Wired into the Slice 5 broker for tool-scoped approval decisions only; no scheduler (on-demand
  expiry), no real channels (Slack/email), no dashboard (§18.6 / Slice 10), no request-auth — approver
  identity is unverified.** Note: the policy `is_mandatory_action` helper was added to `app/policy/matrix.py`.
- Tool broker (§11): **present (Slice 5)** — deny-by-default decision chokepoint composing
  policy + approval, per-agent allowlist ledger, every attempt recorded. **Skeleton: no real
  execution / connectors / MCP / credentials / rate limits / cost / auto-suspension.** Success
  caps at `ALLOWED_UNVERIFIED_IDENTITY`; unverified approvals ⇒ `NEEDS_AUTHENTICATED_APPROVAL`
  (nothing here is executable authorization until request-auth lands).
- Agent registry (§9.7/§17.4/§22.2): **present (Slice 6)** — global admin-curated `agent_blueprints`,
  global **immutable** `agent_versions` (full §22.2 hash snapshot; UPDATE/DELETE/TRUNCATE blocked by
  trigger — *DML-immutable, not tamper-proof vs. a DB superuser*), tenant-scoped RLS `agent_instances`
  (triple FK pins run→project→tenant; binding columns immutable; `active_run_id` set-once; one live
  binding per role handle). **Skeleton: no Agent Factory / qualification-eval execution / model routing /
  agent execution; the broker `agent_id` is NOT wired to instances yet; global registration is not
  audited (tenant-GUC-derived audit; platform-event audit deferred); component hashes are opaque
  caller-supplied inputs (the Factory that generates the artifacts is Phase 4).**
- Cost ledger (§19): **present (Slice 7)** — tenant-owned **immutable** `cost_events`
  (UPDATE/DELETE/TRUNCATE triggers — *DML-immutable, not tamper-proof vs. a DB superuser*;
  `NUMERIC(18,6)`; source-namespaced idempotency with `IdempotencyConflict` on key reuse) +
  per-project `budgets` (audited before/after caps). `evaluate` is **deny-by-default** (missing
  budget ⇒ STOP `no_budget`; threshold `>=`); daily aggregation uses **UTC half-open bounds**.
  Incurred costs are **always recorded, even over budget**. **Budget changes are audited but NOT
  verified human approvals** (approval workflow for increases deferred). **Skeleton: no price cards /
  provider calls / model routing / billing UI / workflow runtime (the stop signal is decision-only,
  not halting) / broker-agent wiring / forecasting / per-phase budgets.**
- Document intake sandbox (§16.3): **present (Slice 9)** — tenant-owned RLS `documents`; customer
  documents handled as **untrusted data** (instruction/data separation; **no LLM wired**, so nothing
  is injectable here). Deterministic **best-effort** injection `scan` (marker identifiers, no ML) ⇒
  quarantine; `as_untrusted_block` labeling; **DB-verified content integrity** (size + core-`sha256`
  hash), content/identity immutability, **one-way `accepted→quarantined`** lifecycle (all via the
  `documents_guard` trigger); idempotent on content hash; audit never carries the body. **Honest:
  scanning is best-effort/bypassable — the guarantee is data-not-instruction + quarantine, not
  detection. Deferred: Documentation Compiler (Phase 2), ML/embedding classification, LLM/RAG wiring,
  binary parsing, malware scanning, per-section quarantine, un-quarantine, Sanad wiring.**
- Read API / dashboard (§18.6): **present (Slice 10 + Slice 17)** — read-only JSON `/api` endpoints
  (run state, open approvals, blockers, cost + stop decision, **and — Slice 17 — the latest persisted
  build-readiness (§4.5) and gap/contradiction findings snapshots**) behind **hashed bearer-key tenant
  auth** (D4: `tenant_api_keys` stores only `sha256:` hashes; missing/invalid/revoked ⇒ 401, no
  fallback). The auth dependency is the single HTTP→tenant boundary; all reads stay in
  `tenant_scope`/RLS (cross-tenant reads return nothing). **D4 hardened (migration 0013):** resolution
  is via a `SECURITY DEFINER` function (`api_key_resolver`-owned); `uaid_app` has EXECUTE-only access
  and **no direct read of the key table**. **Slice 17** = `GET /api/projects/{id}/{readiness,findings}`
  returning the latest snapshot via `repo.latest` or `null` (never-evaluated / cross-tenant /
  nonexistent all return `200` + `null` — no existence oracle); GET never computes or persists
  (no `evaluate_and_record`); no migration, no LLM, no R4/R5. **Deferred: forecast, critical path,
  evidence-pack status, deployment status, next action; readiness/findings *history* endpoints
  (repos support it; not yet exposed); a write/trigger-evaluation endpoint; web UI; auth-event audit;
  HTTP key issuance (admin-path only); HMAC/salted key hashing.**
- Everything else in the Phase 1–7 roadmap (§26) beyond Slices 1 / 1b / 2 / 3 / 4 / 5 / 6 / 7 / 8a / 8b / 9 / 10.

## Secrets
`.env` holds **live API keys** and is **gitignored** (verified not tracked). It was
restored from a pre-scaffold backup after scaffolding. Never commit it. Consider
rotating any key that has been exposed in a non-private context.
