# Slice 83 — per-leaf tier evidence (planner-owned, part of the plan contract)

**Owner.** The PLANNER writes and revises this file. The builder does **not** edit it; the builder
mirrors its `subtier` column into `tests/writer_inventory_c.py` and must **stop and report** on any
disagreement rather than editing either side.

**Companion to.** `.planning/SLICE-83-PLAN.md` v8 §0A. Tier definitions, the evidence rule, the
GREEN contracts, and the commit order live in the plan; this file carries only the per-leaf
evidence.

**Measured on.** branch `feat/slice-83-writer-concurrency` @ `1aa7225`, Alembic head `0062`,
database `app_test`. Leaves: **168** total — **112** Tier A (**21** A1, **38** A2, **53** A3), **54** B1, **2** B2.

**v8 (2026-08-25) — PLAN REJECT — Slice 83 v7.** Reviewer **GPT-5.6 Sol**, agent
`64f1e982-6d60-4f1a-af81-79eba8c67d64`; **consecutive REJECT #2** of the amendment line; all four
defects accepted in full. This file's change is **Sol's v7 defect 2**: v7 re-locked the A1 mechanism to
`projects` in the plan's §0A.5 but left this file still instructing the builder to lock
`control_loop_runs` / `intake_artifacts` / `production_preapproval_attestations` — the exact three
targets v7 struck as SQLSTATE `42501` for `uaid_app`. **All nine `Production change — REQUIRED` rows
below were rewritten** (not only the three Sol cited) to carry the exact `lock_project_row(...)`
insertion point from plan §0A.5 rows 1–4, each retaining its struck v6 target inline so the history is
visible and unusable. **Three modules newly import `lock_project_row`** from
`app/repositories/emergency_controls.py:79` — `acceptance_verification.py`, `go_live_decisions.py`,
`production_approval_service.py`; `emergency_controls.py` already owns it. **No GRANT and no
migration**; Alembic head stays `0062`.

**v7 (2026-08-25).** Sol REJECTED v6; all three defects accepted in full. `run_checkpoint_writes.uq_run_checkpoint_writes_id` moved A2 → **A1** (live upsert at `app/runtime/checkpointer.py:152-167`); the four `go_live_decisions` writer citations corrected from the blank `:443` to `:444`/`:452`; the A1 lock mechanisms re-locked to `projects FOR UPDATE` (plan §0A.5) because `uaid_app` has no `UPDATE` on the three previously planned lock targets.

Index columns and partial predicates are quoted from the live `pg_index` catalog via the OD-8
query. `REG` marks a leaf that already carries a registered node in `TIER_A_NODE_MAP`.

---

## 1. Tier A1 — derived-write (production change authorized)

Both citations are present for every row, as §0A.2 requires.

### `audit_logs.uq_audit_logs_seq`

- **Unique index columns** — `(seq)`
- **Writers** — `app/audit.py:30` `audit_append`
- **Read of committed state** — `migrations/versions/0003_audit_log.py:141-143` — `v_seq := nextval(...)` then `SELECT a.entry_hash INTO v_prev FROM public.audit_logs ORDER BY a.seq DESC LIMIT 1`
- **Derived value written** — `migrations/versions/0003_audit_log.py:147-151` — `INSERT INTO public.audit_logs(seq, …, prev_hash, entry_hash, …) VALUES (v_seq, …, v_prev, v_hash, …)`
- **Required contention scenario** — two concurrent `audit.record` appends in the same tenant
- **Production change** — none — `:140` `PERFORM pg_advisory_xact_lock(421)` precedes the predecessor read, so the loser blocks until the winner commits and then reads the committed head

### `audit_logs.uq_audit_logs_entry_hash`

- **Unique index columns** — `(entry_hash)`
- **Writers** — `app/audit.py:30` `audit_append`
- **Read of committed state** — `migrations/versions/0003_audit_log.py:142-143` — `SELECT a.entry_hash INTO v_prev`
- **Derived value written** — `migrations/versions/0003_audit_log.py:144-146` — `v_hash := public.audit_entry_hash(v_seq, …, v_prev)`
- **Required contention scenario** — two concurrent `audit.record` appends in the same tenant
- **Production change** — none — same advisory lock at `:140`; the chain is proven by `audit_verify()` under contention

### `go_live_decisions.uq_gld_previous`

- **Unique index columns** — `(previous_decision_id)`
- **Writers** — `app/repositories/go_live_decisions.py:444` `finalize_decision` (function span `:444-473`), SQL call at `:452` `SELECT public.slice55_finalize_decision(:evaluation)`
- **Read of committed state** — `migrations/versions/0054_control_loop_decisions.py:706-708` — `SELECT * INTO prior FROM public.go_live_decisions … ORDER BY decision_seq DESC LIMIT 1`
- **Derived value written** — `0054_control_loop_decisions.py:721-722` + `:731` — the `previous_decision_id, prev_entry_hash` columns bound to `prior.id, prior.entry_hash`
- **Required contention scenario** — two concurrent `finalize_decision` calls for the same project with a prior decision present
- **Production change** — none — `:650` locks the `projects` row `FOR UPDATE` before the predecessor read; `finalize_decision` also requires SERIALIZABLE (`app/repositories/go_live_decisions.py:445`)

### `go_live_decisions.uq_gld_entry_hash`

- **Unique index columns** — `(entry_hash)`
- **Writers** — `app/repositories/go_live_decisions.py:444` `finalize_decision` (function span `:444-473`), SQL call at `:452` `SELECT public.slice55_finalize_decision(:evaluation)`
- **Read of committed state** — `migrations/versions/0054_control_loop_decisions.py:706-708` — `prior` head read
- **Derived value written** — `0054_control_loop_decisions.py:709` `new_seq:=nextval(...)` and `:710-713` `new_hash:=public.slice55_entry_hash(new_seq, …, prior.entry_hash)`
- **Required contention scenario** — two concurrent `finalize_decision` calls for the same project
- **Production change** — none — project-row `FOR UPDATE` at `:650`

### `go_live_decisions.uq_gld_project_root`

- **Unique index columns** — `(tenant_id,project_id)`, partial `WHERE (previous_decision_id IS NULL)`
- **Writers** — `app/repositories/go_live_decisions.py:444` `finalize_decision` (function span `:444-473`), SQL call at `:452` `SELECT public.slice55_finalize_decision(:evaluation)`
- **Read of committed state** — `migrations/versions/0054_control_loop_decisions.py:706-708` — `prior` head read; the partial predicate is `previous_decision_id IS NULL`
- **Derived value written** — `0054_control_loop_decisions.py:721` + `:731` — `previous_decision_id := prior.id` (NULL iff no prior)
- **Required contention scenario** — two concurrent FIRST `finalize_decision` calls for the same project (no prior decision)
- **Production change** — none — project-row `FOR UPDATE` at `:650`; the loser re-reads a non-NULL `prior`

### `go_live_decisions.uq_gld_evaluation`

- **Unique index columns** — `(evaluation_id)`
- **Writers** — `app/repositories/go_live_decisions.py:444` `finalize_decision` (function span `:444-473`), SQL call at `:452` `SELECT public.slice55_finalize_decision(:evaluation)`
- **Read of committed state** — `migrations/versions/0054_control_loop_decisions.py:706-708` — `prior` head read in the same statement set that writes `evaluation_id`
- **Derived value written** — `0054_control_loop_decisions.py:714-731` — the single `INSERT … VALUES` carrying both `evaluation_id` (`:715` / `:724`) and the derived chain columns (`:721-722` / `:731`)
- **Required contention scenario** — two concurrent `finalize_decision` calls for the SAME evaluation id
- **Production change** — none — the loser's `23505` is already translated at `app/repositories/go_live_decisions.py:456-465` into `GoLiveDecisionRepositoryError('decision_finalization_refused')`

### `control_loop_events.uq_cle_run_ordinal`

- **Unique index columns** — `(control_loop_run_id,ordinal)`
- **Writers** — `app/repositories/go_live_decisions.py:290` `append_event`
- **Read of committed state** — `app/repositories/go_live_decisions.py:299-310` — `select(ControlLoopEvent) … order_by(ordinal.desc()).limit(1).with_for_update()`
- **Derived value written** — `app/repositories/go_live_decisions.py:320` — `ordinal = 1 if prior is None else prior.ordinal + 1`, written at `:327`
- **Required contention scenario** — two concurrent `append_event` calls on the same `control_loop_run_id`
- **Production change** — REQUIRED — `app/repositories/go_live_decisions.py`: `lock_project_row(..., cycle.project_id)` inserted **between `:298` and `:299`** (plan §0A.5 row 3) — `cycle = await self._require_cycle(...)` already resolves at `:298`, before the head read, and `cycle.project_id` is already used at `:325`, so no new read is introduced. This module **newly imports** `lock_project_row` from `app/repositories/emergency_controls.py:79`. ~~v6: lock the parent `control_loop_runs` row `FOR UPDATE`~~ — struck, `42501` for `uaid_app` (§0.1.30). No GRANT, no migration.

### `control_loop_events.uq_cle_previous`

- **Unique index columns** — `(previous_event_id)`
- **Writers** — `app/repositories/go_live_decisions.py:290` `append_event`
- **Read of committed state** — `app/repositories/go_live_decisions.py:299-310` — head read
- **Derived value written** — `app/repositories/go_live_decisions.py:328` — `previous_event_id=prior.id if prior else None`
- **Required contention scenario** — two concurrent SECOND `append_event` calls on the same cycle (both read the same head)
- **Production change** — REQUIRED — the **same** `lock_project_row` insertion in `app/repositories/go_live_decisions.py` (plan §0A.5 row 3, between `:298` and `:299`); no additional lock and no additional import.

### `control_loop_events.uq_cle_loop_root`

- **Unique index columns** — `(control_loop_run_id)`, partial `WHERE (previous_event_id IS NULL)`
- **Writers** — `app/repositories/go_live_decisions.py:290` `append_event`
- **Read of committed state** — `app/repositories/go_live_decisions.py:299-310` — head read; partial predicate `previous_event_id IS NULL`
- **Derived value written** — `app/repositories/go_live_decisions.py:328` — `previous_event_id` derived (NULL iff no prior)
- **Required contention scenario** — two concurrent FIRST `append_event` calls on the same cycle
- **Production change** — REQUIRED — the **same** `lock_project_row` insertion in `app/repositories/go_live_decisions.py` (plan §0A.5 row 3, between `:298` and `:299`); no additional lock and no additional import.

### `acceptance_criterion_authorship_records.uq_acar_criterion_sequence`

- **Unique index columns** — `(acceptance_criterion_id,sequence)`
- **Writers** — `app/repositories/acceptance_verification.py:66` `record_independent_approval`; `app/repositories/acceptance_verification.py:118` `record_extraction_unapproved`; `app/repositories/acceptance_verification.py:158` `record_dispute`
- **Read of committed state** — `app/repositories/acceptance_verification.py:42-59` (`_current_record`, `order_by(sequence.desc(), id.desc()).limit(1)`, NO `FOR UPDATE`), called at `:84`, `:128`, `:167`
- **Derived value written** — `app/repositories/acceptance_verification.py:90` / `:134` / `:175` — `sequence=(current.sequence + 1) if current else 1`
- **Required contention scenario** — two concurrent `record_*` calls for the same `acceptance_criterion_id`
- **Production change** — REQUIRED — `app/repositories/acceptance_verification.py`: `lock_project_row(self.session, self.context, project_id)` immediately before each `_current_record` call — `:84`, `:128`, `:167` (plan §0A.5 row 1). `project_id` is already a parameter of all three `record_*` methods (`:69` and peers) and of `_current_record` (`:43`). This module **newly imports** `lock_project_row` from `app/repositories/emergency_controls.py:79`. ~~v6: lock the criterion's `intake_artifacts` row `FOR UPDATE`~~ — struck, `42501` for `uaid_app` (§0.1.30). No GRANT, no migration.

### `acceptance_criterion_authorship_records.uq_acar_supersedes_once`

- **Unique index columns** — `(supersedes_record_id)`
- **Writers** — `app/repositories/acceptance_verification.py:66` `record_independent_approval`; `app/repositories/acceptance_verification.py:118` `record_extraction_unapproved`; `app/repositories/acceptance_verification.py:158` `record_dispute`
- **Read of committed state** — `app/repositories/acceptance_verification.py:42-59`, called at `:84`, `:128`, `:167`
- **Derived value written** — `app/repositories/acceptance_verification.py:89` / `:133` / `:174` — `supersedes_record_id=current.id`
- **Required contention scenario** — two concurrent `record_*` calls for a criterion that ALREADY has a record (both derive the same `supersedes_record_id`; a NULL supersedes value cannot contend)
- **Production change** — REQUIRED — the **same** `lock_project_row` insertion in `app/repositories/acceptance_verification.py` (plan §0A.5 row 1, before `:84` / `:128` / `:167`); no additional lock and no additional import.

### `emergency_stop_events.uq_ese_previous`

- **Unique index columns** — `(previous_event_id)`
- **Writers** — `app/repositories/emergency_controls.py:337` `append_binding`; `app/repositories/emergency_controls.py:463` `append_event`
- **Read of committed state** — `app/repositories/emergency_controls.py:502` and `:572` — `head = await latest_stop_event(...)`
- **Derived value written** — `app/repositories/emergency_controls.py:476` — `previous_event_id=previous.id` in `append_event`, called at `:505-511` / `:577-583`
- **Required contention scenario** — two concurrent `activate` (or `clear`) calls for the same project
- **Production change** — none for `activate`/`clear` — `lock_project_row` at `:500` / `:570` precedes the head read

### `emergency_stop_events.uq_ese_project_root`

- **Unique index columns** — `(tenant_id,project_id)`, partial `WHERE (previous_event_id IS NULL)`
- **Writers** — `app/repositories/emergency_controls.py:337` `append_binding`; `app/repositories/emergency_controls.py:463` `append_event`
- **Read of committed state** — `app/repositories/emergency_controls.py:437` — `head = await latest_stop_event(...)` in `append_binding`, which does NOT call `lock_project_row`; partial predicate `previous_event_id IS NULL`
- **Derived value written** — `app/repositories/emergency_controls.py:439-443` — the armed anchor is inserted with `previous_event_id=None` only when `head is None`
- **Required contention scenario** — two concurrent `append_binding` calls for the same project with no prior stop event
- **Production change** — REQUIRED — `app/repositories/emergency_controls.py`: call the module's **own** `lock_project_row` (`:79`) in `append_binding` before the `:437` head read (plan §0A.5 row 2 — *unchanged, already `projects`*; **no new import**, the helper is local). No GRANT, no migration.

### `emergency_stop_events.uq_ese_idempotency`

- **Unique index columns** — `(tenant_id,project_id,idempotency_key_hash)`
- **Writers** — `app/repositories/emergency_controls.py:337` `append_binding`; `app/repositories/emergency_controls.py:463` `append_event`
- **Read of committed state** — `app/repositories/emergency_controls.py:502` / `:572` — head read feeding the same INSERT
- **Derived value written** — `app/repositories/emergency_controls.py:476` + `:487` — the single `EmergencyStopEvent(...)` carrying both the derived `previous_event_id` and `idempotency_key_hash`
- **Required contention scenario** — two concurrent `activate` calls for the same project with the SAME `idempotency_key_hash` (contends this axis and `uq_ese_previous` together)
- **Production change** — none — `lock_project_row` at `:500`; sibling-axis rule (§0A.3) keeps this axis A1

### `production_preapproval_lifecycle_events.uq_pple_previous`

- **Unique index columns** — `(previous_event_id)`
- **Writers** — `app/repositories/production_preapprovals.py:440` `append_lifecycle_event`
- **Read of committed state** — `app/release/production_approval_service.py:248` and `:336` — `head = await self.repo.latest_lifecycle(...)`, with NO project or attestation lock
- **Derived value written** — `app/release/production_approval_service.py:253` / `:343` — `previous_event_id=head.id`, written at `app/repositories/production_preapprovals.py:455`
- **Required contention scenario** — two concurrent `revoke` calls for the same attestation (both read the same `approved_anchor` head)
- **Production change** — REQUIRED — `app/release/production_approval_service.py`: `lock_project_row(..., project_id)` before the **first** read of each derive chain — before `:231` (the `prior` attestation select, which precedes the `:248` head read) and before `:326` in `revoke` (plan §0A.5 row 4). `project_id` is a parameter at both sites (used at `:236`; `revoke` signature `:324`). This module **newly imports** `lock_project_row` from `app/repositories/emergency_controls.py:79`. ~~v6: lock the `production_preapproval_attestations` row `FOR UPDATE`~~ — struck, `42501` for `uaid_app` (§0.1.30). No GRANT, no migration.

### `production_preapproval_lifecycle_events.uq_pple_attestation_event`

- **Unique index columns** — `(attestation_id,event_type)`
- **Writers** — `app/repositories/production_preapprovals.py:440` `append_lifecycle_event`
- **Read of committed state** — `app/release/production_approval_service.py:336` — head read feeding the same INSERT
- **Derived value written** — `app/repositories/production_preapprovals.py:451-465` — the single `ProductionPreapprovalLifecycleEvent(...)` carrying the derived `previous_event_id` and `(attestation_id, event_type)`
- **Required contention scenario** — two concurrent `revoke` calls for the same attestation
- **Production change** — REQUIRED — the **same** `lock_project_row` insertion in `app/release/production_approval_service.py` (plan §0A.5 row 4, before `:231` and before `:326`); no additional lock and no additional import.

### `production_preapproval_lifecycle_events.uq_pple_idempotency`

- **Unique index columns** — `(tenant_id,project_id,idempotency_key_hash)`
- **Writers** — `app/repositories/production_preapprovals.py:440` `append_lifecycle_event`
- **Read of committed state** — `app/release/production_approval_service.py:336` — head read feeding the same INSERT
- **Derived value written** — `app/repositories/production_preapprovals.py:451-465` — same INSERT as above
- **Required contention scenario** — two concurrent `revoke` calls for the same attestation with the SAME idempotency key
- **Production change** — REQUIRED — the **same** `lock_project_row` insertion in `app/release/production_approval_service.py` (plan §0A.5 row 4, before `:231` and before `:326`); no additional lock and no additional import.

### `budgets.uq_budgets_tenant_id_project_id` **[REG]**

- **Unique index columns** — `(tenant_id,project_id)`
- **Writers** — `app/repositories/cost.py:184` `upsert`
- **Read of committed state** — `app/repositories/cost.py:199` — `existing = await self.get(project_id)` before the write
- **Derived value written** — `app/repositories/cost.py:210-215` — `on_conflict_do_update(set_={… 'updated_at': func.now()})`, re-selected at `:225` with `execution_options(populate_existing=True)`
- **Required contention scenario** — two concurrent `upsert` calls for the same project (already registered, commit 4)
- **Production change** — none — landed in commit 4 (`9d0e543`); node `tests/test_slice83_races_core.py::test_p_green_1_budget_upsert_first_write`

### `autonomy_policies.uq_autonomy_policies_tenant_id_project_id` **[REG]**

- **Unique index columns** — `(tenant_id,project_id)`
- **Writers** — `app/repositories/admin.py:91` `admin_write_autonomy_policy`
- **Read of committed state** — `app/admin/policy_sql.py:58-63` and `:111-114` — `SELECT p.id, p.autonomy_level, p.overrides INTO … FOR UPDATE`
- **Derived value written** — `app/admin/policy_sql.py:95` / `:108` / `:127` — the `INSERT … ON CONFLICT DO NOTHING` first-write path then the locked `UPDATE … RETURNING id`
- **Required contention scenario** — two concurrent `admin_write_autonomy_policy` calls for the same project
- **Production change** — none — landed in Slice 63 v4.1; node `tests/test_admin_policy_race_db.py::test_p_writer_concurrent_first_write` (+ mutation)

### `admin_policy_changes.uq_admin_policy_changes_action`

- **Unique index columns** — `(admin_action_id)`
- **Writers** — `app/repositories/admin.py:91` `admin_write_autonomy_policy`
- **Read of committed state** — `app/admin/policy_sql.py:58-63` — `SELECT … INTO o_autonomy_policy_id, v_previous_level, v_stored_overrides … FOR UPDATE`
- **Derived value written** — `app/admin/policy_sql.py:71-77` — `INSERT INTO public.admin_policy_changes (… previous_autonomy_level …) VALUES (… v_previous_level …)`
- **Required contention scenario** — two concurrent `admin_write_autonomy_policy` calls spending the SAME `admin_action_id`
- **Production change** — none POSSIBLE — the derived write lives inside a SECURITY DEFINER function installed by migration `0062`; OD-1 forbids a migration, so the raw-SQLSTATE escape on double-spend is a named limitation (§0A.7), not a fix in this slice

### `run_checkpoint_writes.uq_run_checkpoint_writes_id`

- **Unique index columns** — `(tenant_id,thread_id,checkpoint_ns,checkpoint_id,task_id,idx)`
- **Writers** — `app/runtime/checkpointer.py:122` `aput_writes` (loop body `:133-169`)
- **Read of committed state** — **NONE.** No `SELECT` precedes the write. The conflict resolution is
  the statement itself: `app/runtime/checkpointer.py:152-167` is
  `.on_conflict_do_update(index_elements=[tenant_id, thread_id, checkpoint_ns, checkpoint_id, task_id, idx],
  set_={channel, type, blob, task_path})`. **This is the A1 discriminator here:** the owner's ruling lists
  **upsert paths** as A1 irrespective of whether a read precedes them, because the writer resolves the
  contended key rather than letting the caller see a create-once failure.
- **Derived value written** — `app/runtime/checkpointer.py:161-166` — the `set_` clause overwrites
  `channel`/`type`/`blob`/`task_path` on the existing row. Every one of those four values is the loop's own
  argument (`channel`, `type_`, `blob` from `self.serde.dumps_typed(value)` at `:135`; `task_path` from the
  parameter at `:127`) — **not** a value read from committed state.
- **Required contention scenario** — two concurrent `aput_writes` calls for the same
  `(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)` in the same tenant
- **Production change** — **none.** The existing `ON CONFLICT DO UPDATE` is a single atomic statement:
  the loser blocks on the winner's row lock and then updates it, so no `23505` reaches the caller and no
  value derived from a pre-winner read can be persisted — there is no pre-read at all. The leaf is
  **A1 and keeps a full A1 two-session node**; only the *fix* column is empty. The node's contract and the
  last-writer-wins limitation are stated in plan §0A.4 and §0A.7.

---

## 2. Tier A2 — independent-insert (tests only, no production change)

Every row states the create-once unique constraint over caller-supplied columns and cites the write
site with **no prior-state derivation** of any key column.

| # | leaf | index columns | partial | write site | independence evidence |
|---|---|---|---|---|---|
| 1 | `admin_role_grants.uq_admin_role_grants_tenant_id_principal_subject_admin_role` | `tenant_id,principal_subject,admin_role` | — | `app/admin/tenant_admin.py:113-122` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 2 | `agent_blueprints.uq_agent_blueprints_key` **[REG]** | `key` | — | `app/agents/registry.py:153-159` | pre-read at `:148-150` is an idempotent fast path only; the inserted key column `key` is a caller argument, so independence of every key column from any read is provable. Already hardened in commit 4 (`9d0e543`); node retained. |
| 3 | `agent_instances.uq_agent_instances_live_key` | `tenant_id,project_id,instance_key` | `((status)::text = ANY ((ARRAY['registered'::character varying, 'active'::character varying, 'suspended'::character varying])::text[]))` | `app/agents/registry.py:257-261` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 4 | `agent_versions.uq_agent_versions_blueprint_id_version_label` **[REG]** | `blueprint_id,version_label` | — | `app/agents/registry.py:215-227` | pre-read at `:209-211` is on `content_hash`, not this axis; `blueprint_id`/`version_label` are caller arguments. Already hardened in commit 4; node retained. |
| 5 | `agent_versions.uq_agent_versions_content_hash` **[REG]** | `content_hash` | — | `app/agents/registry.py:215-227` | `content_hash` is computed from caller arguments at `:203-208`, not from any read; the `:209-211` pre-read is an idempotent fast path. Already hardened in commit 4; node retained. |
| 6 | `catalog_assets.uq_ca_kind_key_version` | `asset_kind,asset_key,version_label` | — | `app/repositories/catalog_admin.py:102-109` (also `:130`, `:156`) | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 7 | `catalog_listings.uq_cl_live_asset` | `asset_id` | `(listing_state = 'listed'::text)` | `app/repositories/catalog_admin.py:283-290` | `list_asset` (`:275-291`) performs no pre-read of an existing listing; `asset_id` is a caller argument. A `23505` here corrupts nothing — this is the Slice 61a class the owner named: do NOT add conflict handling. |
| 8 | `control_loop_runs.uq_clr_idempotency` | `tenant_id,project_id,idempotency_digest` | — | `app/repositories/go_live_decisions.py:187-202` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 9 | `cost_events.uq_cost_events_idempotency` | `tenant_id,source_system,external_ref` | `(external_ref IS NOT NULL)` | `app/repositories/cost.py:96-105` | insert-first `ON CONFLICT DO NOTHING` at `:96-105` with post-read reconciliation at `:111-113` — no pre-read, no UPDATE branch, no read-derived key column. |
| 10 | `cost_forecast_policy_versions.uq_cfpv_project_digest` **[REG]** | `tenant_id,project_id,policy_digest` | — | `app/repositories/cost_forecasts.py:112-139` | `policy_digest` is derived from the caller payload at `:88-100`, not from a read; the `:101-109` pre-read is a fast path. Already hardened in commit 4; node retained. |
| 11 | `documents.uq_documents_content` | `tenant_id,project_id,content_hash` | — | `app/repositories/documents.py:57-75` | `content_hash` is computed from caller content at `:51`; insert-first `ON CONFLICT DO NOTHING` at `:72`, winner re-read at `:78`. |
| 12 | `emergency_control_bindings.uq_ecb_idempotency` | `tenant_id,project_id,idempotency_key_hash` | — | `app/repositories/emergency_controls.py:386-416` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 13 | `emergency_rollback_authorizations.uq_era_idempotency` | `tenant_id,project_id,idempotency_key_hash` | — | `app/repositories/emergency_controls.py:615-633` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 14 | `evidence_pack_export_records.uq_epr_idempotency` | `tenant_id,evidence_pack_id,idempotency_key` | — | `app/repositories/export_bundles.py:223-249` | the `:71-73` pre-read is an idempotent fast path; on a real collision `_try_insert_record` returns `None` and `generate` returns `None` at `:161-162` BEFORE any child row is written. |
| 15 | `extraction_promotions.uq_extraction_promotions_proposal` | `tenant_id,extraction_proposal_id` | — | `app/repositories/extraction_promotion.py:173` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 16 | `go_live_evaluations.uq_gle_loop` | `control_loop_run_id` | — | `app/repositories/go_live_decisions.py:372-408` | `control_loop_run_id` is the caller's cycle; the reads at `:350` / `:355-371` feed content columns and digests, not this key column. |
| 17 | `intake_artifacts.uq_intake_artifacts_ref` **[REG]** | `tenant_id,project_id,kind,ref` | — | `app/repositories/intake.py:69-81` (also `extraction_promotion.py:88`) | `ref` is a caller argument; the document pre-checks at `:57-67` read other tables and feed no key column. Already hardened in commit 4; node retained. |
| 18 | `intake_categories.uq_intake_categories_cat` | `tenant_id,project_id,category` | — | `app/repositories/intake_categories.py:51-63` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 19 | `ops_incident_tickets.uq_ops_incident_tickets_incident` | `tenant_id,incident_id` | — | `app/repositories/ops_incidents.py:155-163` | reachable from the re-evaluation path `app/repositories/ops_incidents.py:341-344`, which pre-reads `ticket_for` and inserts for a PRE-EXISTING incident — so it is not A3; the key columns are still caller-resolved, not read-derived. |
| 20 | `ops_incidents.uq_ops_incidents_idempotency` | `tenant_id,project_id,idempotency_key` | — | `app/repositories/ops_incidents.py:127-148` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 21 | `ops_observation_runs.uq_ops_observation_runs_idempotency` | `tenant_id,project_id,idempotency_key` | — | `app/repositories/ops_signals.py:168-189` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 22 | `ops_self_healing_runs.uq_ops_self_healing_runs_idempotency` | `tenant_id,project_id,incident_id,idempotency_key` | — | `app/repositories/ops_hotfix.py:265-266` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 23 | `ops_stabilization_windows.uq_ops_stab_windows_idempotency` | `tenant_id,project_id,idempotency_key` | — | `app/repositories/ops_stabilization.py:311-312` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 24 | `production_preapproval_attestations.uq_ppa_idempotency` | `tenant_id,project_id,resolution_idempotency_key_hash` | — | `app/repositories/production_preapprovals.py:415-437` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 25 | `production_preapproval_attestations.uq_ppa_request` | `request_id` | — | `app/repositories/production_preapprovals.py:415-437` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 26 | `production_preapproval_requests.uq_ppr_generic_approval` | `generic_approval_id` | — | `app/repositories/production_preapprovals.py:331-360` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 27 | `production_preapproval_requests.uq_ppr_idempotency` | `tenant_id,project_id,request_idempotency_key_hash` | — | `app/repositories/production_preapprovals.py:331-360` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 28 | `projects.uq_projects_tenant_id_slug` | `tenant_id,slug` | — | `app/repositories/projects.py:13-14` via `app/tenancy.py:96` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 29 | `release_candidate_issue_bindings.uq_release_candidate_issue_binding` | `tenant_id,release_candidate_id,release_issue_id` | — | `app/repositories/release_candidates.py:68-76` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 30 | `release_candidates.uq_release_candidates_ref` | `tenant_id,project_id,release_ref` | — | `app/repositories/release_candidates.py:34-42` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 31 | `release_issues.uq_release_issues_source_finding` | `tenant_id,source_finding_id` | `(source_finding_id IS NOT NULL)` | `app/repositories/release_issues.py:84-97` | `source_finding_id` is the caller's finding id; the `:79-82` pre-read is a fast path with a material-match check. The partial predicate excludes `create` (`:42`), which leaves the column NULL. |
| 32 | `run_checkpoints.uq_run_checkpoints_id` | `tenant_id,thread_id,checkpoint_ns,checkpoint_id` | — | `app/runtime/checkpointer.py:95-113` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 33 | `skills.uq_skills_key` | `key` | — | `app/repositories/skills.py:46-49` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 34 | `task_contract_artifact_links.uq_tc_artifact_links_triple` | `task_contract_id,artifact_id,link_kind` | — | `app/repositories/task_contracts.py:156-164` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 35 | `task_contract_reviewers.uq_tc_reviewers_registration` | `task_contract_id,reviewer_instance_id,layer,project_id,tenant_id` | — | `app/repositories/task_contracts.py:211` | `(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)` are all resolved from caller arguments; the blueprint reads at `:195-196` are §2.2 validation only. |
| 36 | `task_contract_reviewers.uq_tc_reviewers_triple` | `task_contract_id,reviewer_instance_id,layer` | — | `app/repositories/task_contracts.py:211` | same INSERT as `uq_tc_reviewers_registration`; neither axis carries a read-derived value. |
| 37 | `task_contracts.uq_task_contracts_ref` | `tenant_id,project_id,task_ref` | — | `app/repositories/task_contracts.py:85-100` | no prior-state derivation — every key column is a caller argument or a digest of caller input; no pre-read selects an insert-vs-update branch on this key |
| 38 | `tenant_catalog_adoptions.uq_tca_tenant_project_listing` **[REG]** | `tenant_id,project_id,listing_id` | — | `app/repositories/catalog_adoptions.py:56-68` | pre-read at `:44-52` is a fast path; all three key columns are caller-supplied. Already hardened in commit 4; node retained. |

---

## 3. Tier A3 — append-only (tests only, no production change)

Every row proves that no collidable key column is caller-supplied: the key contains an identifier
minted inside the same call, so two concurrent callers produce distinct rows.

| # | leaf | index columns | partial | write site | why concurrent callers cannot collide |
|---|---|---|---|---|---|
| 1 | `acceptance_verification_results.uq_avres_run_criterion` | `acceptance_verification_run_id,acceptance_criterion_id` | — | `app/repositories/acceptance_verification.py:334` (`verify_project`) | `acceptance_verification_run_id` is the run minted in the same call at `:350` |
| 2 | `agent_provided_skills.uq_aps_capability_skill` | `capability_id,skill_id` | — | `app/repositories/skills.py:102-108` | `capability_id` is minted in the same call at `:86-99` (`INSERT INTO agent_skill_capabilities … RETURNING id`) |
| 3 | `agent_realizations.uq_agent_realizations_instance` | `instance_id` | — | `app/repositories/agent_realizations.py:56-64` | `instance_id` is the instance minted in the same call at `:45-50` |
| 4 | `catalog_vetting_check_results.uq_cvcr_record_name` | `vetting_record_id,check_name` | — | `app/repositories/catalog_admin.py:232-238` | `vetting_record_id` is the record minted in the same call at `:230-231` |
| 5 | `connector_catalog_specs.uq_ccs_asset_id` | `asset_id` | — | `app/repositories/catalog_admin.py:110-121` | `asset_id` is the asset minted in the same call at `:102-109` |
| 6 | `cost_forecast_dimension_results.uq_cfdr_run_dimension` | `run_id,dimension_code` | — | `app/repositories/cost_forecast_persistence.py:117` (`_persist_success`) | `run_id` is the run minted in the same call at `:264` |
| 7 | `cost_forecast_dimension_results.uq_cfdr_run_ordinal` | `run_id,ordinal` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264`; `ordinal` is an in-call positional counter, not a count of committed rows |
| 8 | `cost_forecast_input_lines.uq_cfil_run_kind_component` | `run_id,line_kind,component` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264` |
| 9 | `cost_forecast_input_lines.uq_cfil_run_model_route` | `run_id,model_route_hash` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264` |
| 10 | `cost_forecast_input_lines.uq_cfil_run_ordinal` | `run_id,ordinal` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264`; `ordinal` is the in-call counter initialised at `:137` and incremented at `:165` |
| 11 | `cost_forecast_ledger_event_refs.uq_cfler_run_event` | `run_id,cost_event_id` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264` |
| 12 | `cost_forecast_ledger_event_refs.uq_cfler_run_ordinal` | `run_id,ordinal` | — | `app/repositories/cost_forecast_persistence.py:117` | `run_id` minted at `:264`; in-call positional `ordinal` |
| 13 | `cost_optimizer_citations.uq_coc_run_bucket` | `run_id,bucket_id` | — | `app/repositories/cost_optimizer.py:32` (`recommend`) | `run_id` is the run minted in the same call at `:74` |
| 14 | `cross_project_aggregate_buckets.uq_cpab_run_class_key` | `run_id,signal_class,bucket_key` | — | `app/repositories/learning.py:56-68` | `run_id` is the run minted in the same call at `:50-55` |
| 15 | `emergency_control_authority_members.uq_ecam_binding_ordinal` | `binding_id,ordinal` | — | `app/repositories/emergency_controls.py:418-431` | `binding_id` is the binding minted in the same call at `:415-416`; `ordinal` comes from policy-approver children minted in the same call at `app/repositories/production_preapprovals.py:275-285` |
| 16 | `emergency_control_authority_members.uq_ecam_binding_subject` | `binding_id,principal_subject_hash` | — | `app/repositories/emergency_controls.py:418-431` | `binding_id` minted at `:415-416` |
| 17 | `emergency_stop_run_effects.uq_esre_event_run` | `activation_event_id,run_id` | — | `app/repositories/emergency_controls.py:541-552` | `activation_event_id` is the event minted in the same call at `:505-511` |
| 18 | `evidence_pack_export_files.uq_epef_file_name` | `export_record_id,file_name` | — | `app/repositories/export_bundles.py:166-178` | `export_record_id` is the record minted in the same call at `:140-163` |
| 19 | `evidence_pack_export_files.uq_epef_ordinal` | `export_record_id,ordinal` | — | `app/repositories/export_bundles.py:166-178` | `export_record_id` minted at `:140-163`; `ordinal` is the code-owned `BUNDLE_FILES` position |
| 20 | `evidence_pack_manifest_signatures.uq_epms_export_record` | `export_record_id` | — | `app/repositories/export_bundles.py:179-188` | `export_record_id` minted at `:140-163` |
| 21 | `evidence_pack_section_results.uq_eps_pack_ordinal` | `evidence_pack_id,ordinal` | — | `app/repositories/evidence_packs.py:654` (`_persist_core`) | `evidence_pack_id` is the pack minted in the same call at `:740` |
| 22 | `evidence_pack_section_results.uq_eps_pack_section` | `evidence_pack_id,section_code` | — | `app/repositories/evidence_packs.py:654` | `evidence_pack_id` minted at `:740` |
| 23 | `evidence_pack_source_refs.uq_epsr_pack_ordinal` | `evidence_pack_id,ordinal` | — | `app/repositories/evidence_packs.py:654` | `evidence_pack_id` minted at `:740` |
| 24 | `evidence_pack_source_refs.uq_epsr_pack_source` | `evidence_pack_id,source_kind,source_id` | — | `app/repositories/evidence_packs.py:654` | `evidence_pack_id` minted at `:740` |
| 25 | `evidence_packs.uq_evidence_packs_generation_run` | `generation_run_id` | — | `app/repositories/evidence_packs.py:740` | `generation_run_id` is the run minted in the same call at `:713-714` (`id=uuid.uuid4()`) |
| 26 | `go_live_evaluation_gate_results.uq_glegr_gate` | `evaluation_id,gate_number` | — | `app/repositories/go_live_decisions.py:409-424` | `evaluation_id` is the evaluation minted in the same call at `:407-408` |
| 27 | `go_live_evaluation_gate_results.uq_glegr_ordinal` | `evaluation_id,ordinal` | — | `app/repositories/go_live_decisions.py:409-424` | `evaluation_id` minted at `:407-408`; `ordinal` is the gate number |
| 28 | `ops_hotfix_plans.uq_ops_hotfix_plans_run_kind` | `tenant_id,run_id,plan_kind` | — | `app/repositories/ops_hotfix.py:304-311` | `run_id` is minted at `:265-266`; `:234-235` returns before children when the parent insert loses |
| 29 | `ops_improvement_results.uq_ops_improvement_results_window_seq` | `tenant_id,window_id,seq` | — | `app/repositories/ops_stabilization.py:349` (`_insert_children`) | `window_id` is minted at `:311-312`; children are written only for the freshly minted window |
| 30 | `ops_incident_action_results.uq_ops_incident_action_results_eval_action` | `evaluation_id,action` | — | `app/repositories/ops_incidents.py:177` (`insert_evaluation`) | `evaluation_id` is the evaluation minted in the same call at `:184-189` |
| 31 | `ops_incident_action_results.uq_ops_incident_action_results_eval_seq` | `evaluation_id,seq` | — | `app/repositories/ops_incidents.py:177` | `evaluation_id` minted at `:184-189` |
| 32 | `ops_self_healing_results.uq_ops_self_healing_results_run_action` | `run_id,action` | — | `app/repositories/ops_hotfix.py:327-341` | `run_id` minted at `:265-266`; `:234-235` short-circuits on a lost parent insert |
| 33 | `ops_self_healing_results.uq_ops_self_healing_results_run_seq` | `run_id,seq` | — | `app/repositories/ops_hotfix.py:327-341` | `run_id` minted at `:265-266` |
| 34 | `ops_signal_results.uq_ops_signal_results_run_class` | `run_id,signal_class` | — | `app/repositories/ops_signals.py:191-204` | `run_id` is minted at `:168-189`; children follow only a successful parent insert |
| 35 | `ops_signal_results.uq_ops_signal_results_run_seq` | `run_id,seq` | — | `app/repositories/ops_signals.py:191-204` | `run_id` minted at `:168-189` |
| 36 | `ops_stabilization_criterion_results.uq_ops_stab_criteria_window_seq` | `tenant_id,window_id,seq` | — | `app/repositories/ops_stabilization.py:355-363` | `window_id` minted at `:311-312` |
| 37 | `production_approval_policy_approvers.uq_papa_policy_ordinal` | `policy_version_id,ordinal` | — | `app/repositories/production_preapprovals.py:275-285` | `policy_version_id` is the version minted in the same call at `:273-274`; `ordinal` comes from `enumerate(...)` at `:275` |
| 38 | `production_approval_policy_approvers.uq_papa_policy_subject` | `policy_version_id,principal_subject_hash` | — | `app/repositories/production_preapprovals.py:275-285` | `policy_version_id` minted at `:273-274` |
| 39 | `release_findings.uq_release_findings_scan_fingerprint` | `tenant_id,security_scan_category_result_id,scan_finding_fingerprint` | `(security_scan_category_result_id IS NOT NULL)` | `app/repositories/security_scans.py:180` (`_record_category`) | the partial predicate is `security_scan_category_result_id IS NOT NULL`; that id is minted in the same call under the run created at `:155`. `release_findings.create` (`:28-47`) leaves the column NULL and is excluded by the predicate. |
| 40 | `release_findings.uq_release_findings_shortcut_fingerprint` | `tenant_id,shortcut_detector_category_result_id,shortcut_finding_fingerprint` | `(shortcut_detector_category_result_id IS NOT NULL)` | `app/repositories/shortcut_detectors.py:380` (`_record_success`) | the partial predicate is `shortcut_detector_category_result_id IS NOT NULL`; that id is minted in the same call under the run created at `:409` |
| 41 | `release_verdict_issue_results.uq_rvir_verdict_binding` | `verdict_id,binding_id` | — | `app/repositories/release_verdicts.py:245` (`evaluate_and_record`) | `verdict_id` is the verdict minted in the same call at `:301` |
| 42 | `release_verdict_issue_results.uq_rvir_verdict_ordinal` | `verdict_id,ordinal` | — | `app/repositories/release_verdicts.py:245` | `verdict_id` minted at `:301` |
| 43 | `release_verdicts.uq_release_verdicts_run` | `run_id` | — | `app/repositories/release_verdicts.py:301` | `run_id` is the run minted in the same call at `:282` |
| 44 | `reviewer_quality_case_results.uq_rqcr_record_case` | `reviewer_quality_record_id,fixture_case_id` | — | `app/repositories/reviewer_quality.py:345-359` | `reviewer_quality_record_id` is the record minted in the same call at `:193` |
| 45 | `reviewer_quality_defect_results.uq_rqdr_case_defect` | `reviewer_quality_case_result_id,fixture_defect_id` | — | `app/repositories/reviewer_quality.py:337` (`_record_case`) | `reviewer_quality_case_result_id` is the case result minted in the same call at `:345-359` |
| 46 | `rollback_verification_phase_results.uq_rvpr_run_ordinal` | `run_id,ordinal` | — | `app/repositories/rollback_verifications.py:301` (`_record_observation`) | `run_id` is the run minted in the same call at `:310` |
| 47 | `rollback_verification_phase_results.uq_rvpr_run_phase` | `run_id,phase_code` | — | `app/repositories/rollback_verifications.py:301` | `run_id` minted at `:310` |
| 48 | `security_scan_category_results.uq_sscr_run_category` | `security_scan_run_id,category` | — | `app/repositories/security_scans.py:180` | `security_scan_run_id` is the run minted in the same call at `:155` |
| 49 | `shortcut_detector_category_results.uq_sdcr_run_category` | `shortcut_detector_run_id,category` | — | `app/repositories/shortcut_detectors.py:380` | `shortcut_detector_run_id` is the run minted in the same call at `:409` |
| 50 | `shortcut_detector_reviewer_results.uq_sdrr_category_reviewer` | `shortcut_detector_category_result_id,reviewer_instance_id` | — | `app/repositories/shortcut_detectors.py:380` | `shortcut_detector_category_result_id` is minted in the same call under the run at `:409` |
| 51 | `tenant_api_keys.uq_tenant_api_keys_key_hash` | `key_hash` | — | `app/repositories/api_keys.py:56-59` | `key_hash` is `sha256` of a fresh `secrets.token_urlsafe(32)` minted per call at `:55`, so two concurrent callers cannot produce the same key column |
| 52 | `test_results.uq_test_results_deterministic_case` | `test_oracle_run_id,case_ref` | `(evaluator_instance_id IS NULL)` | `app/repositories/test_oracles.py:691` (`_record_deterministic_success`) | `test_oracle_run_id` is the run minted in the same call (`id=run_id`, `:639-641` pattern) |
| 53 | `test_results.uq_test_results_judgment_vote` | `test_oracle_run_id,case_ref,evaluator_instance_id` | `(evaluator_instance_id IS NOT NULL)` | `app/repositories/test_oracles.py:623` (`_record_judgment_success`) | `test_oracle_run_id` is the run minted in the same call at `:639-641` |

---

## 4. Tier B1 — no collidable unique index (unchanged from v5)

Proven by absence from the OD-8 query on head `0062`. Retained as B1; a migration that adds a
collidable unique key moves the table into the result set and fails inventory test 3.

| # | leaf | writers |
|---|---|---|
| 1 | `acceptance_verification_runs.-` | `app/repositories/acceptance_verification.py:202` `record_failed_verification`; `app/repositories/acceptance_verification.py:334` `verify_project` |
| 2 | `admin_actions.-` | `app/repositories/admin.py:58` `record`; `app/tenancy.py:96` `add` |
| 3 | `agent_failure_events.-` | `app/repositories/agent_failures.py:37` `record_failure` |
| 4 | `agent_skill_capabilities.-` | `app/repositories/skills.py:52` `register_capability` |
| 5 | `agent_tool_allowlist.-` | `app/repositories/tools.py:46` `_event`; `app/tenancy.py:96` `add` |
| 6 | `approval_events.-` | `app/repositories/approvals.py:308` `_record`; `app/tenancy.py:96` `add` |
| 7 | `approval_notifications.-` | `app/repositories/approval_notifications.py:24` `record` |
| 8 | `approvals.-` | `app/repositories/approvals.py:65` `request`; `app/tenancy.py:96` `add` |
| 9 | `audit_chain_verifications.-` | `app/repositories/evidence_packs.py:79` `record_audit_chain_verification` |
| 10 | `branch_protection_snapshots.-` | `app/repositories/ci_evidence.py:35` `record_branch_protection`; `app/repositories/ci_evidence.py:60` `record_connector_verified_branch_protection` |
| 11 | `catalog_vetting_records.-` | `app/repositories/catalog_admin.py:211` `record_contract_test`; `app/repositories/catalog_admin.py:242` `record_review` |
| 12 | `cost_forecast_runs.-` | `app/repositories/cost_forecast_persistence.py:45` `_record_refusal`; `app/repositories/cost_forecast_persistence.py:117` `_persist_success` |
| 13 | `cost_optimizer_runs.-` | `app/repositories/cost_optimizer.py:32` `recommend` |
| 14 | `cross_project_aggregate_runs.-` | `app/repositories/learning.py:39` `persist` |
| 15 | `deployment_target_snapshots.-` | `app/repositories/deployments.py:48` `_record` |
| 16 | `document_classifications.-` | `app/repositories/classification.py:289` `_record` |
| 17 | `evidence_pack_generation_runs.-` | `app/repositories/evidence_packs.py:205` `record_failed_attempt`; `app/repositories/evidence_packs.py:654` `_persist_core` |
| 18 | `extraction_proposals.-` | `app/repositories/extraction.py:62` `extract` |
| 19 | `extraction_runs.-` | `app/repositories/extraction.py:295` `_record_run` |
| 20 | `generated_artifacts.-` | `app/repositories/generator.py:333` `_record` |
| 21 | `intake_findings_reports.-` | `app/repositories/findings.py:44` `evaluate_and_record` |
| 22 | `intake_provenance.-` | `app/repositories/intake.py:37` `add_artifact` |
| 23 | `monitoring_status_snapshots.-` | `app/repositories/monitoring_evidence.py:48` `_record` |
| 24 | `ops_incident_action_evaluations.-` | `app/repositories/ops_incidents.py:177` `insert_evaluation`; `app/tenancy.py:96` `add` |
| 25 | `ops_incident_events.-` | `app/repositories/ops_incidents.py:167` `_append_event`; `app/tenancy.py:96` `add` |
| 26 | `ops_stabilization_closure_attempts.-` | `app/repositories/ops_stabilization.py:159` `attempt_closure`; `app/tenancy.py:96` `add` |
| 27 | `ops_support_handovers.-` | `app/repositories/ops_incidents.py:371` `record_handover`; `app/tenancy.py:96` `add` |
| 28 | `pm_issue_mappings.-` | `app/repositories/pm_issues.py:43` `_record` |
| 29 | `production_approval_policy_versions.-` | `app/repositories/production_preapprovals.py:248` `append_policy_snapshot` |
| 30 | `pull_request_evidence_snapshots.-` | `app/repositories/pr_evidence.py:68` `_record` |
| 31 | `qualification_case_results.-` | `app/repositories/qualification.py:74` `record_qualification_run` |
| 32 | `qualification_runs.-` | `app/repositories/qualification.py:74` `record_qualification_run` |
| 33 | `readiness_reports.-` | `app/repositories/readiness.py:108` `evaluate_and_record` |
| 34 | `release_candidate_events.-` | `app/repositories/release_candidates.py:267` `_event` |
| 35 | `release_finding_events.-` | `app/repositories/release_findings.py:136` `_event`; `app/repositories/security_scans.py:180` `_record_category`; `app/repositories/shortcut_detectors.py:380` `_record_success` |
| 36 | `release_issue_events.-` | `app/repositories/release_issues.py:256` `_event` |
| 37 | `release_verdict_runs.-` | `app/repositories/release_verdicts.py:245` `evaluate_and_record`; `app/repositories/release_verdicts.py:399` `record_failed_attempt` |
| 38 | `review_reports.-` | `app/repositories/review_reports.py:32` `record_report` |
| 39 | `reviewer_quality_records.-` | `app/repositories/reviewer_quality.py:106` `execute_suite`; `app/repositories/reviewer_quality.py:383` `_failure` |
| 40 | `risk_acceptance_events.-` | `app/repositories/risk_acceptance.py:223` `_event` |
| 41 | `risk_acceptance_records.-` | `app/repositories/risk_acceptance.py:42` `create` |
| 42 | `rollback_verification_runs.-` | `app/repositories/rollback_verifications.py:273` `_record_failure`; `app/repositories/rollback_verifications.py:301` `_record_observation` |
| 43 | `run_steps.-` | `app/repositories/runs.py:66` `record_step`; `app/tenancy.py:96` `add` |
| 44 | `secret_reference_checks.-` | `app/repositories/secrets_verification.py:47` `_record` |
| 45 | `security_scan_runs.-` | `app/repositories/security_scans.py:117` `_record_failure`; `app/repositories/security_scans.py:148` `_record_observation` |
| 46 | `semantic_contradiction_reports.-` | `app/repositories/semantic_contradictions.py:243` `_record` |
| 47 | `semantic_contradictions.-` | `app/repositories/semantic_contradictions.py:243` `_record` |
| 48 | `shortcut_detector_runs.-` | `app/repositories/shortcut_detectors.py:345` `_record_failure`; `app/repositories/shortcut_detectors.py:380` `_record_success` |
| 49 | `skill_matches.-` | `app/repositories/skills.py:178` `build_and_record` |
| 50 | `squad_manifests.-` | `app/repositories/skills.py:178` `build_and_record` |
| 51 | `task_contract_events.-` | `app/repositories/task_contracts.py:53` `create`; `app/repositories/task_contracts.py:256` `_transition` |
| 52 | `tenant_admin_events.-` | `app/admin/tenant_admin.py:49` `_record_event` |
| 53 | `test_oracle_runs.-` | `app/repositories/test_oracles.py:364` `_record_failure`; `app/repositories/test_oracles.py:623` `_record_judgment_success`; `app/repositories/test_oracles.py:691` `_record_deterministic_success` |
| 54 | `tool_calls.-` | `app/repositories/tools.py:69` `record`; `app/tenancy.py:96` `add` |

---

## 5. Tier B2 — parent-serialized child (unchanged from v5)

B2-1…B2-4 stay catalog-asserted and B2-5 stays bound per candidate→leaf edge (v5 OD-7 / OD-8).

| # | leaf | index columns | parent table | parent FK column | parent leaf | B2-5 citation |
|---|---|---|---|---|---|---|
| 1 | `agent_realization_reviewers.uq_agent_realization_reviewers_pair` | `realization_id,reviewer_blueprint_id` | `agent_realizations` | `realization_id` | `agent_realizations.uq_agent_realizations_instance` | `app/repositories/agent_realizations.py:63` |
| 2 | `connector_catalog_tool_scope.uq_ccts_asset_tool` | `asset_id,tool_name` | `catalog_assets` | `asset_id` | `catalog_assets.uq_ca_kind_key_version` | `app/repositories/catalog_admin.py:108` |

---

## 6. Leaves the planner could not evidence

**None.** Every one of the 112 former Tier-A leaves carries either both A1 citations, an A2
independence citation, or an A3 minted-parent citation. No leaf was parked and no leaf was left
unclassified; the fail-closed ladder in §0A.2 of the plan was not needed as an escape hatch.
