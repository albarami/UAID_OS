# Slice 41 — Agent replacement / §9.6 failure-policy (reported-classification + prescription) — PLAN v2

**Status:** MERGED — historical record. Implemented via PR #71 (commit `626e57f`); this v2 plan is retained as the design rationale for Slice 41.

> **Revision log — v1 → v2 (B1–B3 + OD-1…6 ruled):**
> - **B1 — failure events are Sanad/provenance-backed.** A reported failure-pattern is a fact-like claim that drives a policy decision, so `agent_failure_events` now carries a **required `source`** (the origin label) + optional **`evidence_ref`** (a bounded pointer to the evidence) + **`source_provenance`** (DB CHECK locked to `caller_supplied_unverified` this slice — the future verified tier mirrors the A5 stores). Pure validators, migration, repo, tests updated.
> - **B2 — no "diagnosis" overclaim.** The failure_pattern is **REPORTED** (caller-supplied, unverified), not inferred — Slice 41 has **no automatic diagnosis/classifier**. The honesty model is now "**reported §9.6 failure-pattern classification + deterministic §9.6 prescription + retry-cap decision**"; the module is `app/agents/failure_policy.py` (not "diagnosis"); "validate" = fail-closed validation of a reported pattern, never inference.
> - **B3 — every user-supplied text field is bounded.** `source`/`evidence_ref`/`summary`/`detail`/`reported_by` all get pure-validator length caps **and** DB `char_length` CHECKs; audit stays safe-metadata only.
> - **OD rulings bound as final:** OD-1 **decision-only — NO auto-suspend** (suspend is a real, ~irreversible enforcement path; coupling it to unverified failure events is too risky); OD-2 **per-instance**; OD-3 **compute-on-read** (events are the audit trail; no `replacement_decisions` table); OD-4 **fixed `MAX_FAILURE_ATTEMPTS=3`**; OD-5 **general ingest only** (no Slice-40 qualification auto-ingest); OD-6 **no HTTP endpoint**.

> **Persona.** Senior agent-platform / reliability-policy backend architect (Sanad + security-reviewer hats).
> **Provenance (Sanad — spec + verified recon):** §9.6 (`spec:932-945`) — the 8 failure-pattern→response table (incl. safety→suspend+audit, persistent-inability→escalate/blocker); §9.5.1 (`spec:930`) remediate-and-requalify; §9.7 (`spec:947`) immutable versions ⇒ a requalified agent is a new version→new instance. Reuse: `AgentInstanceRepository.suspend` (Slice 6 — status→suspended, **one-way/~irreversible**, `reason` NOT persisted; a suspended instance is **already broker-denied** — `broker.py:39-68` resolves only `registered`/`active`); Slice-21 compute-on-read decision (`production_autonomy.py` `GateResult`/`.to_dict()`/`ruleset_version`); Slice-23/24 append-only event store + **`release_findings.source`/`source_provenance`** (`release_finding.py:66-71`); Slice-7 `evaluate_stop`→`CostStopDecision`; `audit.record`. Migration head **0039 ⇒ 0040**.

---

## 0. The defining honesty constraint (the crux)
Slice 41 records a **REPORTED** §9.6 failure-pattern classification (caller-supplied, **unverified** — Sanad-backed by a required `source` + `source_provenance='caller_supplied_unverified'`), then deterministically **PRESCRIBES** the §9.6 response and enforces the retry cap **as a DECISION** (`escalate_or_blocker`). **No automatic diagnosis/classifier exists** — the pattern is *reported and fail-closed-validated*, never inferred. And §9.6's responses (route-model / prompt-gen / context-tune / remediation-task / recruit) need subsystems that don't exist, so Slice 41 **executes NOTHING** (the prescribed responses, incl. suspend, are recorded recommendations) — the Slice-21 *classify + decide, never act* model. The real enforcement path *exists* (an operator-/later-suspended instance is auto-denied by the broker), but the suspend is **not auto-triggered** here (OD-1).

## 1. Scope & non-goals
- **Scope.** (A) A tenant-owned, **append-only, provenance-backed** `agent_failure_events` store (RLS; the Slice-23/24 pattern) — per-INSTANCE **reported** failures over the §9.6 **8-pattern** taxonomy + severity + **required `source`/`source_provenance`** + bounded summary/detail/evidence_ref. (B) A **pure** `app/agents/failure_policy.py` — the §9.6 `prescribe(pattern)` table + the **retry-cap** rule + the fail-closed `validate_failure_event` (bounds every text field). (C) A **compute-on-read** `evaluate_replacement(instance_id)` decision (Slice-21) → `{attempt_count, latest_pattern, prescribed_response, budget_exhausted, effective_response}`; **non-authorizing, non-executing**. (D) `app/repositories/agent_failures.py`.
- **Non-goals (OD-bound).** **NO automatic diagnosis/classifier** (pattern is reported — B2). **NO execution of ANY response** — no auto-suspend (OD-1) / model routing / prompt-gen / context-tune / remediation-task / recruitment. **NO `agent_instances`/Slice-6 change.** **NO Slice-40 qualification auto-ingest** (OD-5). **NO HTTP endpoint** (OD-6). **NO LLM, NO A5/readiness/go-live change** (not an Appendix-B gate; bit-stable).

## 2. The honesty model in one line
Slice 41 is the §9.6 **prescription + retry-cap DECISION** layer over a **provenance-backed, append-only store of REPORTED** failure-pattern classifications — it records (with Sanad `source`), validates fail-closed, prescribes, and decides; it does **not diagnose/infer, execute, or authorize** anything (bit-stable; go-live false).

## 3. BOUND decisions
- **D-41-1 — Deterministic, decision-only, non-executing.** No LLM; no response executed (incl. suspend — OD-1).
- **D-41-2 — Reported, provenance-backed (B1/B2).** The failure_pattern is caller-REPORTED; each event carries a required `source` + `source_provenance` (DB-locked `caller_supplied_unverified`). No inference.
- **D-41-3 — Per-INSTANCE, append-only (OD-2/§9.7).** Keyed on `instance_id`; a requalified agent = new version→new instance→fresh budget. SELECT/INSERT-only (no lifecycle).
- **D-41-4 — Compute-on-read decision (OD-3/Slice-21).** No `replacement_decisions` table; the events are the audit trail.
- **D-41-5 — Retry cap fixed `MAX_FAILURE_ATTEMPTS=3` (OD-4).** `budget_exhausted = attempt_count >= 3` ⇒ effective response `escalate_or_blocker`.
- **D-41-6 — Safety is immediate.** `latest_pattern == safety_authority_violation` ⇒ effective response `suspend_and_audit` regardless of count (a recommendation — not executed).
- **D-41-7 — All user text bounded (B3).** `source`/`evidence_ref`/`summary`/`detail`/`reported_by` capped in the pure validator AND by DB `char_length` CHECKs.
- **D-41-8 — Store/infra-only; bit-stable.** `production_autonomy.py`/`readiness.py` UNTOUCHED; audit safe-metadata only; go-live false.

## 4. Pure — `app/agents/failure_policy.py`
- `FAILURE_PATTERNS` (8 §9.6 machine values), `RESPONSES` (8), `SEVERITIES` (`low/medium/high/critical`), `SOURCE_PROVENANCES=('caller_supplied_unverified',)`, `MAX_FAILURE_ATTEMPTS=3`, `RULESET_VERSION="slice41.v1"`, bounds (`MAX_SOURCE=100`, `MAX_EVIDENCE_REF=200`, `MAX_SUMMARY=2000`, `MAX_DETAIL=8000`, `MAX_REPORTED_BY=200`).
- `PRESCRIPTION: dict[pattern → response]` (§9.6 verbatim); `prescribe(pattern) -> response`.
- `validate_failure_event(*, failure_pattern, severity, source, evidence_ref, summary, detail, reported_by, source_provenance)` — fail-closed: enum membership + non-empty required (`failure_pattern`/`severity`/`source`/`reported_by`/`source_provenance`) + every text field within bounds. **Reported, not inferred.**
- `effective_response(*, attempt_count, latest_pattern) -> response`: `none`(0 failures) / `suspend_and_audit`(safety) / `escalate_or_blocker`(budget exhausted OR `persistent_inability`) / else `prescribe(latest_pattern)`.
- `ReplacementDecision` (frozen + `to_dict()`): `instance_id`/`attempt_count`/`latest_pattern`/`prescribed_response`/`budget_exhausted`/`effective_response`/`ruleset_version`.

## 5. Storage + migration `0040`
- **`agent_failure_events`** (TENANT, RLS ENABLE+FORCE; **SELECT/INSERT only** — append-only block triggers): `id`/`tenant_id`/`project_id`/`instance_id`/`failure_pattern`(CHECK∈8)/`severity`(CHECK∈4)/**`source`(NOT NULL, `char_length 1..100`)**/**`evidence_ref`(nullable, `char_length 1..200`)**/**`source_provenance`(NOT NULL, CHECK = `'caller_supplied_unverified'`)**/`summary`(nullable, `char_length 1..2000`)/`detail`(nullable, `char_length 1..8000`)/`reported_by`(NOT NULL, `char_length 1..200`)/`created_at`. **composite FK** `(instance_id,project_id,tenant_id)→agent_instances`; index `(tenant_id,instance_id,created_at)`. Migration `0040` purely additive (one table; no Slice-6 change). `summary`/`detail` may carry source-derived material (audit/logs never carry them; **no no-secret guarantee**).

## 6. Repository — `app/repositories/agent_failures.py`
- `record_failure(*, instance_id, failure_pattern, severity, source, reported_by, evidence_ref=None, summary=None, detail=None, source_provenance='caller_supplied_unverified')` — `validate_failure_event` → confirms the instance exists/same-tenant → inserts the event → audits **safe-metadata only** (`instance_id`/`failure_pattern`/`severity`/`source`/`source_provenance` — never `summary`/`detail`/`evidence_ref`).
- `evaluate_replacement(instance_id) -> ReplacementDecision` — reads the instance's failure events (tenant-scoped) → computes `attempt_count`/`latest_pattern`/`effective_response` (pure); **no write, no persistence, non-authorizing**.
- Reads: `failures_for(instance_id)`, `attempt_count(instance_id)`.

## 7. Execution / enforcement — NONE (the honest boundary)
No response is executed (OD-1). "Must not retry forever" is enforced **as a decision** (`escalate_or_blocker`); the operative suspend→broker-deny is an operator-/later action. A test asserts `evaluate_replacement`/`record_failure` change no agent/instance/A5 state.

## 8. A5 / readiness / tenancy / audit
**A5/readiness: NONE — bit-stable** (`before==after`). RLS ENABLE+FORCE + `tenant_isolation`; composite FK pins instance/project/tenant; append-only; audit safe-metadata only. Go-live false.

## 9. Tests
- **Pure:** `prescribe` (all 8); `effective_response` (none / safety-immediate / budget-exhausted→escalate / persistent_inability→escalate / else→prescribed); `validate_failure_event` (bad pattern/severity/source_provenance + **every oversized/empty text field** fail-closed — B3); constants.
- **DB — store:** `record_failure` inserts + audits safe-metadata (no summary/detail/evidence_ref in audit — B1); bad pattern/severity refused (CHECK); **`source_provenance <> 'caller_supplied_unverified'` refused (CHECK)**; **oversized `source`/`evidence_ref`/`summary`/`detail`/`reported_by` refused (char_length CHECK)**; composite-FK cross-project/tenant refused; RLS cross-tenant; append-only (no UPDATE/DELETE).
- **DB — decision:** 0 failures ⇒ `none`; 1 weak_instructions ⇒ `regenerate_prompt_and_eval`; 3 ⇒ `budget_exhausted`+`escalate_or_blocker`; 1 safety_authority_violation ⇒ `suspend_and_audit`; per-instance isolation.
- **DB — non-executing / bit-stable:** no agent_instance status change + `production_autonomy` `before==after`.
- `make test` + fresh `make test-db` + alembic `0040` round-trip; CI green.

## 10. Must NOT claim
- That the system **diagnoses/infers** the failure pattern (it is **reported + fail-closed-validated**, `caller_supplied_unverified` — B2).
- That any §9.6 **response is executed** (recorded recommendations only — incl. suspend; OD-1/D-41-1).
- That "must not retry forever" is **auto-enforced** (it is a **decision**; the operative suspend is operator-/later).
- That a failure record **authorizes/blocks** anything, or that **A5/readiness/go-live** changed (non-authorizing; bit-stable).

## 11. RESOLVED decisions (formerly open)
OD-1 decision-only, **no auto-suspend** (§7/D-41-1); OD-2 per-instance (D-41-3); OD-3 compute-on-read (D-41-4); OD-4 fixed `MAX_FAILURE_ATTEMPTS=3` (D-41-5); OD-5 general ingest only (§1 non-goals); OD-6 no HTTP endpoint (§1 non-goals).

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A **provenance-backed**, append-only `agent_failure_events` store (RLS, per-instance, §9.6 8-pattern, required `source`/`source_provenance='caller_supplied_unverified'`, every text field bounded by `char_length` CHECKs, composite-FK pinned) + a pure §9.6 `prescribe`/`effective_response` over **REPORTED** patterns (no inference) + a compute-on-read `evaluate_replacement` that enforces the retry cap **as a decision** (`escalate_or_blocker`) and flags safety violations as `suspend_and_audit` — **executing nothing, auto-suspending nothing**, unlocking no authority; `production_autonomy.py`/`readiness.py` untouched, **bit-stable**, go-live false; migration `0040` round-trips; `make test` + `make test-db` + CI green. **No diagnosis/classifier, no response execution, no auto-suspend, no LLM, no qualification auto-ingest, no HTTP endpoint, no A5 flip.**

---
**Review note (v2):** Fixes **B1** (Sanad provenance — required `source` + `source_provenance` DB-locked to `caller_supplied_unverified`, mirroring `release_findings`), **B2** (no "diagnosis" overclaim — the pattern is **reported**, validated fail-closed not inferred; module renamed `failure_policy.py`), **B3** (every user text field bounded in the validator AND by DB `char_length` CHECKs). All six ODs bound as final (decision-only / per-instance / compute-on-read / fixed-cap / general-ingest / no-endpoint). Deterministic, store/infra-only, bit-stable, migration `0040`. **No code/migration/tests/PR until an approved plan + your explicit go.**
