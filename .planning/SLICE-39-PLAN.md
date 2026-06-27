# Slice 39 — Agent realization + factory workflow + broker↔instance wiring — PLAN v3

**Status:** AWAITING PLAN REVIEW (v1+v2 REJECTED; v3 **adds B7 same-project broker identity**; OD-1…4 + B1–B6 settled) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.** Kept as **one slice** (factory + broker together — per the split ruling, factory must not grant instance-scoped allowlist rows while the broker still treats `agent_id` as a free string).

> **Revision log — v2 → v3 (B7 — same-project broker identity):**
> - **B7 — the broker resolves `agent_id` to a SAME-PROJECT instance, not only same-tenant.** RLS enforces tenant, not project, and policy/approval are **project-keyed** (`autonomy_policies.decision_for(project_id, …)`), so a same-tenant/different-project instance would let the caller's project evaluate against an identity owned by another project. v3 binds resolution to `id==agent_id AND tenant_id==context.tenant_id AND project_id==broker_call.project_id AND status∈{registered,active}`; a same-tenant/different-project instance ⇒ `DENIED_UNKNOWN_AGENT`; the realization lookup uses the resolved `(instance_id, project_id, tenant_id)`. DB isolation tests added. **All v2 fixes (OD-1…4, B1–B6) stand unchurned.**
>
> **Revision log — v1 → v2 (OD-1…4 + B1–B6 accepted):**
> - **OD rulings (bound):** OD-1 broker **hard-requires** a real `agent_instance` (free-string ⇒ `DENIED_UNKNOWN_AGENT`); OD-2 **reuse** `agent_tool_allowlist` keyed by `str(instance_id)` — **safe because broker instance-resolution is mandatory before any allowlist authority** (B5 order); OD-3 **new `agent_realizations` table** (Slice-6 instance not mutated with qualification); OD-4 **FK-backed reviewer child table**.
> - **B1 — trust-zone fixed.** `AgentFactory.realize` does **NO global registry writes**. Blueprint/version registration is an **admin-path precondition** (`register_blueprint`/`register_version` on an **admin session**, as today); `realize` takes an **already-registered `version_id`** and writes **only tenant rows** (instance + realization + allowlist grants) inside `tenant_scope`. The runtime role never mutates the global registry.
> - **B2 — decision schema bound.** Add `DENIED_UNKNOWN_AGENT` + `DENIED_UNQUALIFIED_AGENT` to `BrokerDecision` **and** `ToolCall._DECISIONS`; migration `0038` **drops/recreates `ck_tool_calls_decision_valid`** (7→9 values; downgrade restores 7); a direct-SQL test proves both new decisions persist.
> - **B3 — no denormalized blueprint.** `agent_realizations` carries **NO `blueprint_id`**; the §2.2 self-review guard resolves the **actual** blueprint via `realization → agent_instances → agent_versions.blueprint_id` and rejects a reviewer equal to it. Direct-SQL tests for self-review rejection.
> - **B4 — qualification mutability bound.** `agent_realizations` is **SELECT/INSERT only** in Slice 39 (NO UPDATE grant); the INSERT guard forces `qualification_status='unqualified'` (rejects an inserted `'qualified'`). The `unqualified→qualified` UPDATE transition lands in **Slice 40** (which adds the UPDATE grant). Direct-SQL tests for insert-`qualified` rejection + no-UPDATE.
> - **B5 — broker gate order bound** (§4): sanitize → known-tool → **resolve real instance** → **qualification** → allowlist → policy → approval → success; precedence tests.
> - **B6 — model/export scope bound** (§6): `app/models/agent_realization.py` (`AgentRealization` + `AgentRealizationReviewer`) + `__init__.py`; `AgentInstance.__table_args__` gains the additive `UNIQUE(id, project_id, tenant_id)`; `ToolCall._DECISIONS` updated.

> **Persona.** Senior agent-platform / release-governance backend architect (Sanad + security-reviewer hats).
> **Track / placement.** Roadmap §5 Track A — **Phase 4** (`GO-LIVE-END-TO-END-ROADMAP.md:347-357`). Foundational — flips **NO A5 gate**; go-live false.

> **Provenance (Sanad — verified via spec + a code-recon pass):**
> - **§9.1–9.2** (`spec:801-829`): the factory **binds** the 13-component agent (incl. tool allowlist, authority, reviewer linkage) "and **passing a qualification gate**."
> - **§9.4** (`spec:876-889`): steps 1–4 + 8 = bind + register (this slice); steps 5–7 (eval/dry-qualify/QA+Security) = **Slice 40**; §9.6 replacement = **Slice 41**.
> - **§9.5.1** (`spec:930`): an agent failing its activation threshold **cannot be registered for autonomous work** ⇒ unqualified ⇒ no executable authority.
> - **§9.7** (`spec:947-961`): version immutable once used; the instance carries `blueprint_id`(via version)/`model_route`/policy hashes/`active_run_id`.
> - **Reuse (recon-verified)**: `registry.py` `register_blueprint`/`register_version` (**admin-path globals**; version has `model_route`+6 sha256 hashes), `AgentInstanceRepository.instantiate/...` (tenant, audited); `agent_instances` (tenant, RLS; `version_id` FK→`agent_versions.blueprint_id`; status enum; **lacks** `UNIQUE(id,project,tenant)` — verified). `broker.py` `broker_call(...agent_id: str...)` — **`agent_id` untrusted** (`:94`); `BrokerDecision` 7 outcomes; success `ALLOWED_UNVERIFIED_IDENTITY`; records `ToolCall`. `tool_call.py` `_DECISIONS` (7) + `0006:94` `ck_tool_calls_decision_valid` (7). `ToolAllowlistRepository.grant/is_allowed` (append-only). No `factory.py`; migration head `0037` ⇒ **`0038`**.

---

## 0. Scope & non-goals
- **Scope.** (A) **Factory** (`app/agents/factory.py`): `realize(*, project_id, version_id, instance_key, tool_allowlist, reviewer_blueprint_ids, realized_by)` — **tenant-only** writes inside `tenant_scope`: `AgentInstanceRepository.instantiate` (instance for an **already-registered** `version_id`) → grant each `tool_allowlist` entry via `ToolAllowlistRepository.grant(agent_id=str(instance.id), …)` (**instance-scoped**) → insert `agent_realizations` (`qualification_status='unqualified'`) → insert `agent_realization_reviewers` (FK, ≠ the realized blueprint, §2.2). (B) **Broker↔instance wiring** (`app/tools/broker.py`): resolve `agent_id` → a real tenant `agent_instance` + its realization; new fail-closed gates `DENIED_UNKNOWN_AGENT` (absent/suspended/retired) + `DENIED_UNQUALIFIED_AGENT` (no/`!=qualified` realization), in a **bound order** (§4). (C) `tool_calls.decision` schema extended (B2).
- **Non-goals.** **NO global registry writes from the factory** (blueprint/version registration is an **admin-path precondition**, B1). **NO qualification** (eval/dry-test/QA+Security = Slice 40; §9.5.1) — every realization is `unqualified`. **NO §9.6 replacement** (Slice 41). **NO agent execution / model calls / real tool invocation** (success stays `ALLOWED_UNVERIFIED_IDENTITY`; Slice-27 approval unwired). **NO Slice-6 column/data/trigger changes** — the ONLY exception is an additive `UNIQUE(id,project,tenant)` on `agent_instances` (FK target, verified absent). **NO LLM, no HTTP endpoint, no A5/readiness/go-live change.**

## 1. The defining honesty constraint (the crux)
Qualification = **Slice 40** (§9.5.1). So every `agent_realizations` row is `unqualified` (the only INSERT-able value), and the broker's `DENIED_UNQUALIFIED_AGENT` gate **always fires** for every realized instance ⇒ the broker grants **NO new tool authority** this slice. Slice 39 **wires** identity + qualification awareness; it does **not unlock** execution (success stays `ALLOWED_UNVERIFIED_IDENTITY`; Slice-27 verified approval still unwired) — "wire the gate, don't pass it." Go-live false.

## 2. BOUND decisions (v3 — final, all closed)
- **D-39-1 — Factory writes tenant-only** (B1): `realize` takes an existing `version_id`; no `register_blueprint`/`register_version` calls (those stay admin-path/admin-session, a documented precondition).
- **D-39-2 — Migration `0038`; Slice-6 logic untouched** except the additive `agent_instances UNIQUE(id,project,tenant)` (FK target).
- **D-39-3 — Broker hard-requires a real SAME-PROJECT instance** (OD-1/B7): `agent_id` must resolve to an `agent_instance` with `id==agent_id` **AND** `tenant_id==context.tenant_id` **AND `project_id==broker_call.project_id`** **AND** `status∈{registered,active}`; absent / **same-tenant-but-different-project** / suspended/retired / non-UUID ⇒ `DENIED_UNKNOWN_AGENT` (policy/approval are project-keyed, so a cross-project identity must never resolve).
- **D-39-4 — Qualification gate** (OD-1): no realization **or** `qualification_status != 'qualified'` ⇒ `DENIED_UNQUALIFIED_AGENT` (always fires this slice).
- **D-39-5 — Allowlist instance-scoped** (OD-2): reuse `agent_tool_allowlist` keyed by `agent_id=str(instance_id)`; **safe because instance-resolution + qualification run before the allowlist check** (B5 order).
- **D-39-6 — `agent_realizations` SELECT/INSERT-only this slice** (B4): INSERT guard forces `qualification_status='unqualified'`; the `qualified` transition (UPDATE) is Slice 40. No DELETE.
- **D-39-7 — Reviewer linkage FK-backed + self-review-guarded via the ACTUAL blueprint** (OD-4/B3): no denormalized `blueprint_id`; the guard joins `realization→instance→version→blueprint`.
- **D-39-8 — Decision schema extended** (B2): `BrokerDecision` + `ToolCall._DECISIONS` + `ck_tool_calls_decision_valid` add the 2 new values; downgrade restores 7.
- **D-39-9 — Store/infra-only; bit-stable** (B-): `production_autonomy.py`/`readiness.py` UNTOUCHED; audit safe-metadata only; go-live false.

## 3. Factory — `app/agents/factory.py` (+ `app/repositories/agent_realizations.py`)
- Pure: `QUALIFICATION_STATUSES=('unqualified','qualified')`, `REALIZE_INSERT_STATUS='unqualified'`, `validate_realization_request` (instance_key shape; bounded `tool_allowlist` [each a known tool name] + `reviewer_blueprint_ids`; non-empty checks).
- `AgentRealizationRepository(TenantScopedRepository).realize(...)` (tenant-only, in `tenant_scope`): instantiate → grant instance-scoped allowlist → INSERT realization (`unqualified`) → INSERT reviewer links → audit safe-metadata only (ids/status/counts — never prompts/policies). Reads `for_instance(instance_id)`, `for_project(project_id)`, `reviewers_of(realization_id)`. `realized_by` UNTRUSTED. **Precondition (admin-path, NOT here):** the `version_id` was registered via `register_version` on an admin session.

## 4. Broker wiring — `app/tools/broker.py` (bound gate order — B5)
`BrokerDecision` += `DENIED_UNKNOWN_AGENT`, `DENIED_UNQUALIFIED_AGENT`. `broker_call` order:
1. **sanitize params** → `DENIED_INVALID_PARAMS` (redaction/invalid behavior preserved).
2. **known tool** → `DENIED_UNKNOWN_TOOL`.
3. **resolve `agent_id` → an `agent_instances` row** with `id==agent_id` AND `tenant_id==context.tenant_id` AND **`project_id==broker_call.project_id`** (B7) AND `status∈{registered,active}`: any miss — non-UUID / absent / **same-tenant-different-project** / suspended/retired ⇒ `DENIED_UNKNOWN_AGENT`.
4. **qualification**: load `agent_realizations` for the **resolved same-project instance** (by `(instance_id, project_id, tenant_id)`); no realization or `!= 'qualified'` ⇒ `DENIED_UNQUALIFIED_AGENT` (always fires).
5. **allowlist** (instance-scoped, `agent_id=str(instance_id)`) → `DENIED_NOT_ALLOWLISTED`.
6. **policy** (Slice 3) → `DENIED_POLICY`.
7. **approval** (Slice 4/27) → `NEEDS_APPROVAL` / `NEEDS_AUTHENTICATED_APPROVAL`.
8. **success** → `ALLOWED_UNVERIFIED_IDENTITY` (unchanged; Slice-27 provenance set still empty ⇒ never executable).
Every attempt records a `ToolCall` with the final decision (incl. the 2 new) + the resolved instance id (or the raw `agent_id` when unresolved); audit/params redacted as today.

## 5. Storage + migration `0038`
- **`agent_realizations`** (TENANT, RLS ENABLE+FORCE; **SELECT/INSERT only** — B4): `id`/`tenant_id`/`project_id`/`instance_id`/`qualification_status`(CHECK ∈ {unqualified,qualified})/`realized_by`/`created_at`. **composite FK `(instance_id,project_id,tenant_id)→agent_instances`**; FK `(project_id,tenant_id)→projects`; **UNIQUE(instance_id)**; **UNIQUE(id,project_id,tenant_id)** (reviewer FK target). **INSERT guard:** `qualification_status='unqualified'` (rejects `'qualified'`); append-only block triggers (no UPDATE/DELETE/TRUNCATE).
- **`agent_realization_reviewers`** (TENANT, RLS, append-only SELECT/INSERT): `id`/`tenant_id`/`project_id`/`realization_id`/`reviewer_blueprint_id`/`created_at`. composite FK `(realization_id,project_id,tenant_id)→agent_realizations`; FK `reviewer_blueprint_id→agent_blueprints`; **UNIQUE(realization_id,reviewer_blueprint_id)**. **Self-review guard (BEFORE INSERT, B3):** reject if `reviewer_blueprint_id = (SELECT v.blueprint_id FROM agent_realizations r JOIN agent_instances i ON … JOIN agent_versions v ON … WHERE r.id=NEW.realization_id)` — the **actual** blueprint, not a denormalized copy.
- **`agent_instances`**: additive `UNIQUE(id,project_id,tenant_id)` (FK target; verified absent; no other change).
- **`tool_calls`**: `DROP/ADD ck_tool_calls_decision_valid` to the 9-value set (downgrade restores 7) — B2.
- Grants: tenant tables SELECT/INSERT to `uaid_app`; RLS `tenant_isolation`. Purely additive otherwise.

## 6. Models / export scope (B6)
- **`app/models/agent_realization.py`**: `AgentRealization` + `AgentRealizationReviewer` (RLS tenant-owned; composite FKs; constraints above). Register both in `app/models/__init__.py`.
- **`app/models/agent_instance.py`**: add `UNIQUE(id, project_id, tenant_id)` to `__table_args__`.
- **`app/models/tool_call.py`**: extend `_DECISIONS` with the 2 new values.

## 7. A5 / readiness impact
- **NONE — bit-stable.** `production_autonomy.py`/`readiness.py` UNTOUCHED; a `before==after` A5 + readiness-unchanged regression guards it. Go-live false.

## 8. Tenant / RLS / FK / audit / immutability
Both new tables tenant-owned, RLS ENABLE+FORCE + `tenant_isolation`; composite FKs pin project/tenant; **self-review guard via the actual blueprint** (B3); `qualification_status` `unqualified`-locked + SELECT/INSERT-only (B4); append-only; audit safe-metadata only (never prompts/policies/tool params). `agent_tool_allowlist` reused as-is. No secret material.

## 9. Tests (DB-backed + Docker-free)
- **Pure:** `validate_realization_request` (bad shapes/bounds); `QUALIFICATION_STATUSES`/insert-status.
- **DB — factory:** `realize` ⇒ instance + instance-scoped allowlist grants + `unqualified` realization + FK reviewers; **self-review refused** (B3, direct-SQL, via the actual blueprint); **insert-`qualified` refused** + **no UPDATE grant** (B4); reviewer-FK unknown-blueprint refused; RLS cross-tenant; composite-FK cross-tenant/project refused.
- **DB — broker (B5 precedence):** invalid params ⇒ `DENIED_INVALID_PARAMS`; unknown tool ⇒ `DENIED_UNKNOWN_TOOL`; valid tool + non-instance/absent/suspended `agent_id` ⇒ `DENIED_UNKNOWN_AGENT`; **a same-tenant/DIFFERENT-project instance id ⇒ `DENIED_UNKNOWN_AGENT`** (B7 — even when that instance is realized + allowlisted for its OWN project, it cannot satisfy identity for the caller's project; `ToolCall` records the denial with NO cross-project realization data); realized **unqualified** same-project instance ⇒ `DENIED_UNQUALIFIED_AGENT`; **`ToolCall` persists both new decisions** (B2, direct-SQL CHECK). **Existing `test_tools.py` updated** to real same-project instances (free-string now `DENIED_UNKNOWN_AGENT`).
- **No-A5/readiness (db):** `realize` ⇒ `production_autonomy` `before==after` + readiness unchanged; broker grants no new authority.
- `make test` + fresh `make test-db` + alembic `0038` round-trip (incl. the `tool_calls` CHECK recreate); CI green.

## 10. Must NOT claim
- That a realized agent is **qualified** / may do **autonomous work** (Slice 40, §9.5.1; every realization `unqualified`; broker denies).
- That the broker now **authorizes execution** (resolves identity + denies unqualified/unknown, but success stays `ALLOWED_UNVERIFIED_IDENTITY`; Slice-27 approval unwired ⇒ nothing executes).
- That the factory **registers blueprints/versions** (admin-path precondition; the tenant factory writes only tenant rows — B1).
- That a reviewer linkage is a **verified review** (records bound reviewer roles only).
- That any **A5 gate / readiness / go-live** changed (foundational, bit-stable; go-live false).

## 11. Resolved decisions (formerly open; now ruled)
OD-1 broker hard-requires real instance (D-39-3/4); OD-2 reuse allowlist keyed by `str(instance_id)`, safe via the B5 order (D-39-5); OD-3 new `agent_realizations` table (D-39-2/6); OD-4 FK-backed reviewer child table (D-39-7). **Split:** kept as ONE slice (factory + broker together).

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A tenant-only factory realizes an **already-registered** version into an instance with an instance-scoped tool allowlist, FK-backed reviewers (≠ the actual blueprint, §2.2), and an `unqualified`, SELECT/INSERT-only `agent_realizations` record; the broker resolves `agent_id`→a real instance in a **bound order** (sanitize→known-tool→resolve→qualification→allowlist→policy→approval) and fail-closed-denies unknown/inactive (`DENIED_UNKNOWN_AGENT`) and unqualified (`DENIED_UNQUALIFIED_AGENT`) agents, granting **no new authority**; `BrokerDecision`/`ToolCall._DECISIONS`/`ck_tool_calls_decision_valid` extended (round-trips); RLS + composite FKs + actual-blueprint self-review guard + `qualified`-write-lock; `production_autonomy.py`/`readiness.py` untouched, **bit-stable**, go-live false; migration `0038` round-trips; `make test` + `make test-db` + CI green. **No global registry writes from the factory, no qualification, no execution, no LLM, no A5 flip.**

---
**Review note (v3):** v3 adds **B7** — the broker resolves `agent_id` to a **SAME-PROJECT** instance (`id==agent_id AND tenant_id==context.tenant_id AND project_id==broker_call.project_id AND status∈{registered,active}`); a same-tenant/different-project instance ⇒ `DENIED_UNKNOWN_AGENT` (policy/approval are project-keyed); the realization lookup uses the resolved `(instance_id, project_id, tenant_id)`; DB isolation tests added. **All v2 fixes stand.** v2 baked the OD-1…4 rulings and fixed **B1** (factory writes tenant-only; blueprint/version registration stays admin-path — no trust-zone break), **B2** (`tool_calls.decision` CHECK + `_DECISIONS` extended, round-trip + DB test), **B3** (no denormalized blueprint; self-review guard via the actual `instance→version→blueprint`), **B4** (`agent_realizations` SELECT/INSERT-only, `unqualified`-locked; `qualified` transition deferred to Slice 40), **B5** (exact broker gate order + precedence tests), **B6** (models + `__init__` + `AgentInstance` UNIQUE + `ToolCall._DECISIONS` scope). Honesty constraint stands: every realization is `unqualified` ⇒ the broker's gate always denies ⇒ no execution unlocked. One slice (factory + broker). Store/infra-only, bit-stable, go-live false; migration `0038`. **No code/migration/tests/PR until an approved plan + your explicit go.**
