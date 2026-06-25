# Slice 33 — Communication / approval channel (human-in-the-loop UX) — PLAN v3

**Status:** AWAITING PLAN REVIEW (v1→v2 REJECTED; v3 fixes B6) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**

> **Revision log — v2 → v3 (B6 accepted):**
> - **B6 — policy-consumption contradiction resolved (recommended option): NO `human_approval_policy` read this slice.** The §0 goal said the router "consum[es] the declared `human_approval_policy`," contradicting the bound tier-only D-33-1 (§3/§5 read no policy). v3 binds **no policy read at all** — tier-only routing, no `PolicyView`, no `daily_digest_time`, no `realtime_for`, no `approval_channel` read (the channel is fixed to `dashboard`). §0 goal + non-goal, §3, §5, §9 sequencing now all agree.
>
> **Revision log — v1 → v2 (all five accepted):**
> - **B1 — D-33-1 routing BOUND: tier-only.** `{low, medium} → digest`; `{high, production} → realtime`. The template-20 `realtime_for` list + any action→category mapping are **explicitly deferred** to a follow-up (§2 D-33-1, §3).
> - **B2 — D-33-7 digest BOUND: label-only.** "digest" is a routing **label** recorded on the notification; **no scheduler, no `daily_digest_time` time-window builder, no digest assembly** this slice (`daily_digest_time` is not read/executed). The dashboard already batches visually (§2 D-33-7).
> - **B3 — FK integrity FIXED (Option A).** `approvals` today has only `UNIQUE(id, tenant_id)` (`app/models/approval.py`), so a `(approval_id, project_id, tenant_id)` FK has no target and project-consistency is unprovable. Migration `0032` adds the **additive** `UNIQUE(id, project_id, tenant_id)` to `approvals` (the Slice-6/14b composite-FK-target pattern), and `approval_notifications` FKs `(approval_id, project_id, tenant_id) → approvals` — DB-proving `notification.project_id == approval.project_id` (§4).
> - **B4 — Orchestration surface BOUND:** one authoritative `request_and_notify_approval(...)` that calls `ApprovalRepository.request(...)` **then** `ApprovalNotificationService.notify_for_approval(...)`. `ApprovalRepository` stays untouched (additive) (§5).
> - **B5 — Tests:** add routing truth-table, the orchestration path writing **both** an `approval_events` row **and** an `approval_notifications` row (direct repo tests unchanged), DB tenant/project FK integrity, the `before==after` no-gate-flip, and no-secret-material (§8).

**Persona:** senior backend / release-systems / HITL-UX architect.
**Base:** `main` @ `25c8446` (Slice 32 merged); working tree clean except the intentional local-only `.planning/HANDOFF.json` (M) + roadmap (untracked); **0 open PRs**.
**Migration head:** `0031_secret_reference_checks` (verified — Slice 32) → new head **`0032`**. *(Roadmap `:274` says "possibly `0031`"; that is the stale +1 — `0031` is Slice 32's.)*
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:269-279` (Slice 33).

> **Provenance (Sanad — read this session):** §18.2 Approval batching table — low→daily digest/batch, medium→decision bundle, high→real-time, production→formal release approval, emergency→immediate alert (`docs/…v1_2.md:1760-1770`); §18.1 "executive control experience, not a stream of interruptions" (`:1758`); §18.5 non-response policy (already modeled in `app/approvals/states.py` `compute_deadline`/`auto_transition`, 24h); template 20 `20_human_approval_policy.yaml` = `{approval_channel ∈ (dashboard|slack|teams|email|ticketing_system), daily_digest_time, batch_low_risk_questions, realtime_for:[production_deployment|security_exception|cost_overrun|data_access|legal_or_regulatory_decision], non_response_policy:{low_risk,medium_risk,high_risk,production}, approvers:[]}`; the Slice-4 approval engine `ApprovalRepository.request(action, risk_tier, requested_by, requires_explicit_approval, subject_ref)` + `approve/reject/cancel/expire_if_overdue/is_blocked/latest_for` (`app/repositories/approvals.py:41+`), `RiskTier ∈ {low,medium,high,production}` (`app/approvals/states.py:23-27`); Slice-27 verified-actor identity + `request_authenticated` approver provenance (`app/identity.py`, already on approvals); the §18.6 read API already surfaces open approvals at `GET /api/projects/{id}/approvals` (`app/api/dashboard.py`). **No comms/notification channel code or `approval_notifications` table exists** (grep matches are substring false-positives in agent/checkpointer/sandbox). Reuse: the immutable append-only + RLS + two-tier-provenance pattern (Slices 26/28/30/31/32); the broker-gated/fake-in-tests adapter pattern.

---

## 0. Goal & non-goal
- **Goal.** Wire the **existing Slice-4 approval engine** to a **human surface**: a deterministic **tier-only risk-tier router** (§18.2 — digest vs realtime; **no `human_approval_policy` read this slice**, B6), a **channel adapter** (protocol + Fake + the **dashboard** channel), and an immutable, tenant-owned **`approval_notifications` log** recording what was routed/delivered. Approvals continue to be **resolved with Slice-27 verified identity** (already in the engine). (§18.2 `:1760-1770`; §26.3 communication/approval channel; roadmap `:269-279`.)
- **Non-goal — NO A5 gate flip** (roadmap `:277`: gate #12's verified approvals are **completed in Slice 53**, not here). `production_autonomy.py` is **UNTOUCHED**; `ruleset_version` stays `slice31.v1`. **No new verified-identity mechanism** (reuse Slice 27). **No external channel delivery** (slack/teams/email/ticketing) — adapters are protocol + fake + a follow-up; **dashboard-only** real channel this slice. **No secret material** stored (no webhook URLs/tokens — dashboard channel needs none; external-channel credentials are a future slice). **No change to `states.py` non-response logic** (§18.5 already exists). **No `human_approval_policy` read** this slice (B6) — routing is tier-only; `daily_digest_time` / `realtime_for` / `approval_channel` are **not** read or executed (the channel is fixed to `dashboard`). No new HTTP write endpoint.

## 1. The properties that dominate this slice
- **Additive / no-regression:** the Slice-4 approval engine (`states.py` / `approvals.py`) and the Slice-5 broker (which calls `ApprovalRepository.is_blocked`) must keep working unchanged. The notification layer is a **separate, additively-wired** service — it does not alter approval state transitions or the `is_blocked` gate.
- **No secret material:** the channel is an enum (`dashboard` this slice); no URLs/tokens/addresses are stored or logged. (Defense-in-depth: reuse the value-key denylist mindset — the notification log has no free-text recipient/credential column.)
- **Channel ack ≠ approval:** routing/delivering a notification is **not** an approval and **never** a production pre-approval (roadmap `:278`; that is Slice 53). The notification log is descriptive; only the approval engine's APPROVED state (with Slice-27 verified identity) unblocks.

## 2. Bound decisions + open decisions
- **D-33-2 Channel scope — BOUND: `dashboard` only** (real) + a `FakeChannel` (CI). The dashboard "delivery" is recording that the approval is surfaced on the existing read API (`GET …/approvals`) — **no external network, no secrets**. `slack`/`teams`/`email`/`ticketing_system` are protocol-conformant adapters **deferred** to a follow-up (each needs operator-controlled credentials/audience — out of scope, cf. the Slice-32 deferral).
- **D-33-3 Wiring — BOUND: a separate additive `ApprovalNotificationService`** (NOT embedded in `ApprovalRepository.request`), called explicitly after an approval is requested. The approval engine core is untouched (no regression to broker/`is_blocked`).
- **D-33-4 Notification log — BOUND:** immutable, append-only `approval_notifications` (one row per notify; RLS; no secret material).
- **D-33-5 Verified identity — BOUND: REUSE Slice 27** — the approval *resolution* already carries `request_authenticated`/verified-actor provenance; this slice adds **no** new identity mechanism. It records the routing; the human acts via the existing verified path.
- **D-33-6 No gate flip — BOUND:** `production_autonomy.py` untouched; ruleset stays `slice31.v1`; a `before == after` regression proves it (gate #12 = Slice 53).
- **D-33-1 Routing model — BOUND (B1): tier-only.** `route(risk_tier)` = `realtime` iff `risk_tier ∈ {high, production}` else `digest` (so `{low, medium} → digest`). Honors §18.2 (low=digest, medium=bundle≈batched, high/production=realtime). The template-20 `realtime_for` category list **and** any action→category mapping are **explicitly deferred** — not consulted this slice.
- **D-33-7 Digest model — BOUND (B2): label-only.** `digest` is a routing **label** stored on the notification; the dashboard already batches open approvals visually. This slice builds **no** scheduler, **no** `daily_digest_time` time-window builder, and **no** digest assembly/delivery — `daily_digest_time` is **not read or executed**. (Deferred to a follow-up with a real timer/scheduler.)

## 3. Pure module — `app/approvals/channels/routing.py`
- `RoutingMode` (`digest` | `realtime`); `CHANNELS` (`dashboard` writable this slice; `slack`/`teams`/`email`/`ticketing_system` reserved enum values, **unwritable**); `ROUTING_MODES`/`STATUSES` constants.
- **Pure `route(risk_tier) -> RoutingMode` (D-33-1, tier-only):** `realtime` iff `risk_tier ∈ {high, production}` else `digest`. Deterministic, fail-closed (an unknown tier raises — `RiskTier` already rejects unknown values). **No `policy_view`, no `realtime_for`** consulted (deferred).
- Validators for the notification record (`risk_tier`/`routing_mode`/`channel`/`status` enums; FK id presence) — fail-closed.

## 4. Evidence/log model + migration `0032` (B3 — FK integrity, Option A)
Migration `0032`:
1. **Additive** `UNIQUE(id, project_id, tenant_id)` on the **existing `approvals`** table (the Slice-6/14b composite-FK-target pattern — additive constraint only; no column/data change; `approvals` logic untouched).
2. New `approval_notifications` (tenant-owned, RLS ENABLE+FORCE; **SELECT/INSERT only**, append-only block triggers; `created_at` `clock_timestamp()`):
   - `id`, `tenant_id`, `project_id`, `approval_id`, `risk_tier` (CHECK ∈ RiskTier), `routing_mode` (CHECK ∈ {digest,realtime}), `channel` (CHECK ∈ {dashboard} this slice), `status` (CHECK ∈ {delivered, failed, skipped}), `created_at`.
   - **Composite FK `(approval_id, project_id, tenant_id) → approvals(id, project_id, tenant_id)`** — DB-proves `notification.project_id == approval.project_id == tenant` (closes B3); plus `(project_id, tenant_id) → projects`.
   - **No recipient/URL/credential column** (no secret material — structural).

## 5. Repository + adapter + service + **authoritative orchestration** (B4)
- `app/repositories/approval_notifications.py`: `ApprovalNotificationRepository.record(...)` (validates, audits **safe metadata only** — ids/risk_tier/routing_mode/channel/status; never recipient/free-text) + `latest_for_approval` / `list_for_project`.
- `app/approvals/channels/adapter.py`: `ApprovalChannel` protocol (`deliver(notification) -> status`) + `FakeChannel` (CI) + `DashboardChannel` (no external I/O — delivery = "surfaced via the existing read API"; returns `delivered`).
- `app/approvals/channels/service.py`: `ApprovalNotificationService.notify_for_approval(approval, *, actor, channel)` → `route(approval.risk_tier)` → `channel.deliver(...)` → `repo.record(...)`. Tier-only routing + injected channel (fake-in-tests). **No policy/secret read** (routing is tier-only this slice).
- **`request_and_notify_approval(session, context, *, …request args…, actor, channel) -> (approval, notification)`** — the **one authoritative orchestration surface** (B4): calls `ApprovalRepository.request(...)` (unchanged) **then** `ApprovalNotificationService.notify_for_approval(...)`. This is what "wires the approval engine to a human surface"; `ApprovalRepository` itself is **untouched** (additive — the broker/`is_blocked` path keeps calling `request` directly with no behavior change).

## 6. A5 / evidence impact
- **NONE.** `production_autonomy.py` + `readiness.py` untouched; `ruleset_version` stays `slice31.v1`. Proven by a **`before == after`** production-autonomy regression. Gate #12's *verified* approvals complete in Slice 53; this slice only builds the routing/notification surface.

## 7. Tenant / RLS / FK / audit / immutability
RLS ENABLE+FORCE + `tenant_isolation`; append-only (SELECT/INSERT only); composite FKs pin approval+project to tenant; audit safe-metadata only; **no secret material** (no recipient/URL/token columns or logs).

## 8. Tests (DB-backed + Docker-free, per README `:19-32`)
- **Pure:** `route()` truth table — `low`/`medium`→digest, `high`/`production`→realtime (tier-only; **no** `realtime_for`/policy path); record validators (enums/FK-id presence).
- **DB-guard (B3):** bad risk_tier/routing_mode/channel/status rejected; append-only no-UPDATE/DELETE/TRUNCATE; **composite-FK integrity** — a notification whose `(approval_id, project_id, tenant_id)` does not match a real `approvals(id, project_id, tenant_id)` row is rejected (wrong project_id for the approval ⇒ FK violation), proving `notification.project_id == approval.project_id`; RLS cross-tenant.
- **Orchestration (db, B4/B5):** `request_and_notify_approval(...)` writes **both** an `approval_events` row (from `request`) **and** an `approval_notifications` row, routed by tier (`high`⇒realtime, `low`⇒digest); `FakeChannel` delivery recorded; audit carries no recipient/free-text; **no secret material** in any row/audit. Direct `ApprovalRepository`/`ApprovalNotificationRepository` tests remain unchanged.
- **No-regression (db):** the broker (`is_blocked`) + approval transitions behave identically (`request`→`is_blocked`→`approve` unchanged whether or not a notification was emitted); **`before == after`** production-autonomy (no gate flip, ruleset `slice31.v1`).
- `make test` + fresh `make test-db` + alembic `0032` round-trip; CI green.

## 9. Sequencing (TDD)
1. Pure `routing.py` (modes/route/validators). 2. Model + migration `0032` (DB-guard enums + append-only). 3. Repository (+ db tests + audit safety). 4. Adapter (protocol + Fake + Dashboard). 5. Service + the authoritative `request_and_notify_approval` orchestration (no policy read; + db routing/no-secret tests). 6. No-regression + `before==after` guard. 7. Full gates; CLAUDE.md merge-stable entry + roadmap banner.

## 10. Must NOT claim
- That a channel ack / delivered notification is an **approval** or a **production pre-approval** (roadmap `:278`; that is Slice 53). Only the approval engine's APPROVED state (Slice-27 verified identity) unblocks.
- That this slice adds a verified-identity mechanism (it **reuses** Slice 27) or completes gate #12 (Slice 53).
- That external channels (slack/teams/email/ticketing) are delivered (dashboard + fake only this slice).
- That any A5 gate or readiness level changed (store/infra-only; ruleset `slice31.v1`; go-live false).
- That secret material (recipients/URLs/tokens) is stored (it is not — no such column).

## 11. Definition of done (for the eventual implementation — NOT this PLAN)
A single authoritative `request_and_notify_approval(...)` wires the Slice-4 approval engine to a human surface: it requests the approval (unchanged engine) then routes **tier-only** (`{low,medium}→digest`, `{high,production}→realtime`, D-33-1) and records an immutable append-only `approval_notifications` row (label-only digest, D-33-7) via a Fake/`dashboard` channel — writing **both** an `approval_events` and an `approval_notifications` row, with **no secret material**. The composite FK `(approval_id, project_id, tenant_id) → approvals` DB-proves project/tenant consistency (additive `UNIQUE` on `approvals`). Approvals still resolve with Slice-27 verified identity; the broker/`is_blocked` path is unchanged (no-regression) and `production_autonomy`/`readiness` are untouched (`before==after`, ruleset `slice31.v1`); RLS + DB-guard + alembic `0032` round-trip + `make test`/`make test-db` + CI green; go-live false.

---
**Review note:** PLAN v3 patches **B6 only** — the plan is now internally consistent that **no `human_approval_policy` is read this slice** (tier-only routing; no `PolicyView`/`daily_digest_time`/`realtime_for`/`approval_channel`); §0 goal + non-goal, §3, §5, §9 agree. The v2 bindings stand: D-33-1 tier-only routing (B1), D-33-7 label-only digest (B2), the B3 FK-integrity fix (additive `UNIQUE(id, project_id, tenant_id)` on `approvals` + composite FK), the B4 authoritative `request_and_notify_approval` orchestration (repository untouched), and the B5 both-rows tests. Central + unchanged: additive infra / **no gate flip** (production_autonomy untouched, ruleset `slice31.v1`, `before==after`), dashboard-only channel + fake (externals deferred), no secret material, verified identity reused from Slice 27, migration `0032`. No code/migration/tests/PR until an approved plan + your explicit go.
