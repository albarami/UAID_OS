# Slice 83 — F-020 writer concurrency: six first-write signatures + the 122-candidate barrier suite

**Seats (v9, current).** PLANNER = **GPT-5.6 Sol**. REVIEWER = **Claude Opus**, the available
substitute for the owner-named **Claude Fable 5**; that substitution is recorded here and is not
silent. The planner revises this file only. `.planning/SLICE-83-LEAF-EVIDENCE.md` remains planner-owned
and unchanged because its live A1 contracts already lock `projects` via `lock_project_row`; the
builder edits neither planner-owned file.

**Seat-swap status (owner ruling, 2026-08-25).** The prior Opus-authored amendment line has **three**
REJECTs: v6, v7, and v8. The owner ruling of 2026-08-25 is still **not** a reject. The swapped-pair
reject counter resets to **0** for this Sol-authored line; **three consecutive Opus REJECTs halt the
run**. After PLAN APPROVE, the implementation seats revert: BUILDER = **Cursor Grok 4.6 Extra High**,
resuming from **commit 6**, and REVIEWER = **GPT-5.6 Sol** for code.

**Version.** **v9 — both v8 blockers accepted in full (2026-08-25).**

> ### **PLAN REJECT — Slice 83 v8**
>
> Reviewer **GPT-5.6 Sol**, agent `c7a97392-0a24-41a4-8d60-d8374f2b5e57`. This is the **third
> REJECT of the prior Opus-authored amendment line** and fires the owner-ruled seat swap. Both blockers
> are accepted in full below; neither is argued down.
>
> 1. BLOCKER — stale live counts remain. `.planning/SLICE-83-PLAN.md:169-170,1690-1692,1760-1762`
> still state 20/39 and the 11/9 split. Replace with 21/38 and commit 7 = 9, commit 8 = 12.
>
> 2. BLOCKER — OD-9 still carries the obsolete schedule.
> `.planning/SLICE-83-PLAN.md:1498,1741-1743,1796-1802,2035-2040,2244-2245` still say nine commits,
> removals through commit 9, and final-empty at commit 9. Replace with fourteen commits, removals in
> commits 7–13, and final-empty at commit 14.

> ### **PLAN REJECT — Slice 83 v7**
>
> Reviewer **GPT-5.6 Sol**, agent `64f1e982-6d60-4f1a-af81-79eba8c67d64`. This is **consecutive REJECT
> #2 of the amendment line**. It is **not yet a seat swap**: the planner seat stays Claude Opus
> (substituting for Claude Fable 5) and the reviewer seat stays Sol; a **third** consecutive REJECT
> swaps them. All four defects are **probe-backed** and are **accepted in full below — none is argued
> down**.

> ### **PLAN REJECT — Slice 83 v6**
>
> Reviewer **GPT-5.6 Sol**, agent `27f3f958-ac5a-493f-ae91-ca04c6bdcf6e`. This is the **first
> consecutive REJECT of the v6 amendment line**, and it is **not a seat swap**: the planner seat stays
> Claude Opus (substituting for Claude Fable 5) and the reviewer seat stays Sol. All three defects are
> **probe-backed** and are **accepted in full below — none is argued down**.

The **OD-9 halt after commit 5 was CORRECT** and remains discharged by the owner's ruling of
2026-08-25, not by a reject. Commits **1–5 are landed and are not re-planned**; v9 governs commit
**6** onward. Reject tally on the prior Opus-authored amendment line: **3** (v6, v7, v8). The new
swapped-pair reject counter is **0**. The v5 approval of everything the v6/v7/v8/v9 amendments do not
touch still stands.

**v9 authority.** Where v9 conflicts with v8, **v9 governs** and the v8 statement is superseded in
place. Where v8 conflicts with v7, **v8 governs**. Where v7 conflicts with v6 §0A, **v7 governs**.
Where v6 §0A conflicts with any v1–v5 statement, **§0A governs**. Every v1–v5 lock that §0A and the
v7/v8/v9 blocks do not touch remains binding.

**The live contract's counts, stated once and authoritatively (v9).** **A1 = 21, A2 = 38, A3 = 53**
(112 Tier-A), **B1 = 54, B2 = 2** (168 total). Of the 21 A1 leaves, **9 are module-owned** (the four
§0A.5 modules, commit 7) and **12 are barrier-alone** (commit 8, including
`run_checkpoint_writes.uq_run_checkpoint_writes_id`). The branch has **fourteen commits total**:
commits **1–5** are landed, commit **6** publishes subtiers without shrinking pending, commits
**7–13** land nodes and remove their pending IDs, and commit **14** asserts final-empty. Every
execution-facing sentence — OD-7/8/9, §0A.1, the inventory tests, P-MUT-17, the GitHub commit count,
and §3.3–3.6 — matches those counts and that schedule. Any superseded count or schedule remaining in
this file appears only inside explicitly struck text, a historical quotation, or a defect-table
"from" column and is not the contract.

**v9 corrections — both of Sol's v8 defects accepted in full, none argued down.**

| # | Sol's v8 defect | Correction in v9 |
|---|---|---|
| 1 | **Stale live counts remained.** §0A.1 and OD-8 still carried the pre-v7 A1/A2 totals, while OD-9 still carried the transposed A1 batch split. | **Accepted.** Every live contract now states **A1 = 21 / A2 = 38 / A3 = 53**, commit 7 = **9 module-owned** leaves, and commit 8 = **12 barrier-alone** leaves including `run_checkpoint_writes`. Coverage remains **112** Tier-A leaves. |
| 2 | **OD-9 still carried the obsolete schedule.** The frozen pending comment, Option A lock, sequencing rules, inventory test 4, P-MUT-17, and reviewer confirmations still ended the work too early. | **Accepted.** The live contract now has **fourteen commits**; commit 6 publishes subtiers without shrinking pending; only commits **7–13** remove a pending ID as its node lands; commit **14** asserts final-empty. No 83a/83b split is introduced. |

**v8 corrections — all four of Sol's v7 defects accepted in full, none argued down.** All four were
**mechanical-completeness** defects: v7 corrected the authoritative sections but did not propagate the
corrections to every dependent sentence. v8 fixes the propagation and adds the standing count
statement above so a future amendment has one place to change.

| # | Sol's v7 defect (probe-backed) | Correction in v8 |
|---|---|---|
| 1 | **Counts not propagated.** The v7 honesty crux (`:962-966`), the allowed-claims list (`:1046-1047`), and three test-file table rows (`:1263`, `:1265`, `:1266`) still described the contract as **20** A1 / **39** A2, with commit 7 covering `11` leaves and commit 8 covering `9`. | **Accepted.** Every live-contract occurrence is now **A1 = 21, A2 = 38**; `A1_LEAF_IDS` holds **21** ids; commit 7 covers the **9** module-owned leaves; commit 8 covers the **12** barrier-alone leaves and names `run_checkpoint_writes` explicitly. The standing count statement above is added so the contract has a single authoritative home. The only surviving `20`/`39`/`11`/`9`-split strings are inside `~~struck~~` or explicitly historical quotations, verified by grep after the edit. |
| 2 | **Evidence still mandated forbidden locks.** `.planning/SLICE-83-LEAF-EVIDENCE.md:85,112,157` still instructed the builder to lock `control_loop_runs` / `intake_artifacts` / `production_preapproval_attestations` — the exact three targets v7 struck as `42501`. The plan's crux (`:975-977`) and allowed-claims (`:1053-1056`) also still claimed "an existing parent or project row" and "**no import** is added", although v7 added three imports. | **Accepted, and widened beyond the three lines cited.** All **nine** `Production change — REQUIRED` rows in the evidence file were rewritten — not only the three Sol found — each now carrying the exact `lock_project_row(...)` insertion point from plan §0A.5 rows 1–4, with the struck v6 target retained inline as `~~…~~` so the history is visible and unusable. The plan's two claim sites now state the truth: the lock target is **`projects`** via the existing helper, and **three of the four modules newly import `lock_project_row`** (`emergency_controls.py` already owns it). **No GRANT, no migration** — head stays `0062`. |
| 3 | **Pyright coverage incomplete.** `:2141-2147` omitted the four A1 production modules and `tests/writer_inventory_c.py` — the files this slice actually changes. | **Accepted.** All five paths are added to the mandatory local `pyright` invocation (and to the `wc -l` cap report), with existing owned paths kept. An honest scope note is added: the run is **local and mandatory at 0 errors on owned paths**, while **CI's `pyright` scope remains the Slice 55–63 paths** — widening it is **F-017**, which Slice 83 does not close. |
| 4 | **OD-9 commit count.** `:2292` said "**Nine** atomic conventional commits" while the list beneath it enumerates fourteen. | **Accepted.** Corrected to **Fourteen**, with the arithmetic stated: commits **1–5 landed** + commits **6–14 remaining** = **14** total on the branch. OD-9's table remains the single authority. |

**v7 corrections — all three of Sol's v6 defects accepted in full, none argued down.** Each was
re-verified by the planner against live source and the live database before acceptance; the
verification transcripts are recorded as grounding facts §0.1.29–§0.1.32.

| # | Sol's v6 defect (probe-backed) | Correction in v7 |
|---|---|---|
| 1 | `run_checkpoint_writes.uq_run_checkpoint_writes_id` was wrongly **A2**. The v6 evidence citation stopped at `checkpointer.py:136-150`, **before** the true upsert. | **Accepted.** Live source `app/runtime/checkpointer.py:152-167` is `on_conflict_do_update(set_={channel, type, blob, task_path})` (§0.1.29) — an **upsert path**, which the owner's ruling lists as **A1**, and A2 requires create-once. The leaf moves to **A1** and takes a full A1 two-session node. Totals become **A1 = 21, A2 = 38**, A3 = 53; 21+38+53 = 112, unchanged. **21 ≤ 40, so still not a halt.** Per Sol's own note, `aput` at `:109` is `on_conflict_do_nothing`, so `run_checkpoints.uq_run_checkpoints_id` **stays A2** and is not moved. **Production change: NONE, decided honestly** — the existing `DO UPDATE` is one atomic statement with **no pre-read at all**, so no derived value can go stale and no `23505` reaches the caller; it already meets A1 GREEN. **No fifth §1a module is added**, and `app/runtime/checkpointer.py` stays out of §1a-v7. The last-writer-wins semantics of that `set_` clause are recorded as a named limitation (§0A.7) rather than claimed as proof of correctness. |
| 2 | Three planned A1 locks **cannot execute** as `uaid_app`: v6 `:246,248-249` locked `intake_artifacts`, `control_loop_runs`, and `production_preapproval_attestations`, all SELECT/INSERT-only. Live `SELECT … FOR UPDATE` returned SQLSTATE **`42501`** on all three. | **Accepted.** Reproduced live as `uaid_app` on `app_test`: all three return `42501 permission denied`, while `projects FOR UPDATE` and `run_checkpoint_writes FOR UPDATE` succeed (§0.1.30, §0.1.31). **§0A.5 is re-locked to `projects FOR UPDATE` for all four modules**, via the existing in-repo helper `lock_project_row` (`app/repositories/emergency_controls.py:79`), following the precedent Sol cited (`slice55_finalize_decision`, migration `0054_control_loop_decisions.py:650`) and the two existing importers (`ops_stabilization.py:62`, `emergency_control_service.py:16`). **No GRANT, no migration, no new privilege** — Alembic head stays `0062`. The v6 claim "no new import" is corrected in place: three modules add exactly one import of an existing helper; no import cycle exists (§0.1.32). |
| 3 | Four A1 writer citations were **stale**: evidence `:44,53,62,71` cited `go_live_decisions.py:443`, which is a **blank line**. `finalize_decision` begins at `:444`; the SQL call is at `:452`. | **Accepted.** Verified: `:443` is blank, `async def finalize_decision` is `:444`, the function spans `:444-473`, and `text("SELECT public.slice55_finalize_decision(:evaluation)")` is `:452` (§0.1.32). All four evidence rows now cite **`:444` (function, span `:444-473`) and `:452` (SQL call)**. The **inventory's** census wrapper span `app/repositories/go_live_decisions.py:443-472` is a **different coordinate system** — a hand-authored constant inside the landed Appendix-B `CENSUS_SCANNER` (commit 5) — and is **not** a claim about where the function starts. v7 keeps that landed constant byte-identical, states the discrepancy explicitly, forbids quoting the two interchangeably, and records it as the named limitation `census_wrapper_span_443_472_is_an_audit_constant_not_a_writer_citation` (§0A.7). |

**v6 corrections — the owner's ruling, recorded in full.**

| # | What the ruling changed | Correction in v6 |
|---|---|---|
| 1 | An earlier idea of shrinking Tier A **by redefinition** was WRONG. The owner verified against the migrations that ~76 unique constraints across ~66 tables are genuine caller-collidable create-once keys. | Tier A does **not** shrink. It stays **112 leaves**. It is **subdivided by CONSEQUENCE** into A1 / A2 / A3 (§0A.1). Coverage is not reduced: every one of the 112 keeps a retained two-session node. |
| 2 | v5 treated all 112 Tier-A leaves as one class and would have added conflict handling wherever a `23505` could escape. | **GREEN is redefined per subtier** (§0A.4). For **A2** an escaped `23505` is the **CORRECT observed behaviour**, not a failure. **Adding conflict handling to an A2 or A3 leaf is now forbidden** — that is the Slice 61a mistake. |
| 3 | v5's §1a production manifest was fixed at the ten files of commits 1–4. | §1a **expands to exactly the A1 writer modules that must change** — **four** modules (§0A.5) — **plus** the ten already landed. No extras. A2 and A3 are **tests only**. |
| 4 | v5 had no rule preventing a builder from asserting a tier by judgement. | **Classification is evidence, not judgement** (§0A.2). Per leaf the plan records (a) the unique constraint name over caller-supplied columns, or its proven absence from the catalog, and (b) whether the writer reads-then-derives, with the **exact `file:line` of the read and of the derived value**. **A1 requires both cited.** A leaf placed in A2 or A3 without the catalog query and the read-then-derive check is a **defect**. All 168 leaves are evidenced in `.planning/SLICE-83-LEAF-EVIDENCE.md`. |
| 5 | The A1 count had to be reported prominently and is a halt above 40. | **A1 = 21** (§0A.3) — ~~20~~, **superseded by v7 defect 1**. **21 ≤ 40, so this is not a halt** and the builder proceeds from commit 6 after Sol's APPROVE. A2 = 38 (~~39~~), A3 = 53, B1 = 54, B2 = 2; 21+38+53 = 112 and 112+54+2 = 168, both machine-checked. |
| 6 | v5's OD-9 order stopped at commit 9. | OD-9 is **re-locked from commit 6** (§0A.6): A1 production+tests, then A2 tests, then A3 tests, `PENDING_TIER_A_BATCHES` shrinking monotonically, and a final commit asserting **no pending** and complete A1/A2/A3 registration. |
| 7 | The owner expected the eight already-registered leaves to be "**likely** A1 (already fixed)". | Reported, not absorbed: on the evidence only **`budgets`** and **`autonomy_policies`** are A1. The other six — `agent_blueprints`, both `agent_versions` axes, `tenant_catalog_adoptions`, `cost_forecast_policy_versions`, `intake_artifacts` — are **A2** whose key columns are provably independent of any read. **All eight keep their registered nodes** (OD-9 compliance: coverage is not reduced). The consequence is stated plainly in §0A.8: measured against the amended standard, commit 4 hardened six writers of which only one was A1 — landed, not reverted, and the amended "no production change for A2" rule applies **prospectively from commit 6**. |

**v5 corrections — all four of Opus's v4 defects accepted in full, none argued down.** The four v3
defects remain closed; every unchallenged v1–v4 lock remains binding.

| # | Opus's v4 defect | Correction in v5 |
|---|---|---|
| 1 | Commit 5 could not be green because inventory test 4 required nodes that do not land until commits 6–9. | **Historical v5 lock — superseded by v6 §0A.6.** OD-9 locked option **(b)**: code-owned `PENDING_TIER_A_BATCHES: frozenset[str]`. At commit 5 every Tier-A leaf was either registered or pending, never neither/both; all 122 candidates and all leaves were already inventoried. v5 assigned atomic removals and node landings to commits 6–9 and final-empty to commit 9. **Current schedule: pending removals in commits 7–13; final-empty at commit 14.** P-MUT-17 proves a leaf cannot remain hidden pending. |
| 2 | `ConcurrentWriteUnresolved` had a module but no locked base class, contradicting §0.1.12. | Exactly `class ConcurrentWriteUnresolved(Exception)` lives in `app/concurrency.py`. It is one shared caller-visible exception, not a subclass of any writer's domain root. Existing domain-error catchers do not catch it unless updated to catch it explicitly; this is intentional. |
| 3 | The Tier-A harness had no SERIALIZABLE loser branch and tried to commit an already-aborted W2. | Isolation and retryable loser SQLSTATEs are explicit per leaf. Existing SERIALIZABLE writers run both connections at SERIALIZABLE and may return `40001`/`40P01` (or the owned wrapper's post-retry result). An aborted W2 is rolled back, never committed. SQLSTATE `23505` remains forbidden. P-MUT-18 makes both branches load-bearing. |
| 4 | Three source citations drifted from `72ee544`. | Re-measured from source: budget pre-read `app/repositories/cost.py:199`; `promote_proposal` `app/repositories/extraction.py:296-401`; `record_policy_version` `app/repositories/cost_forecasts.py:153-228`. All active occurrences are corrected; wrong locked facts still trigger stop-and-report. |

**v4 corrections — all four of Sol's v3 defects accepted in full, none argued down.** Each is
locked below and carried through the implementation steps, probes, validation, and builder
constraints.

| # | Sol's v3 defect | Correction in v4 |
|---|---|---|
| 1 | P-GREEN-1b used three runtime-role transactions but did not re-bind transaction-local `app.current_tenant` after either commit. | New grounding fact §0.1.21 records the live `<unset>` result after `COMMIT`. The `two_committed_transactions(...)` helper, §3.1, P-GREEN-1b, §8.3b, and P-MUT-1c now require `SELECT set_config('app.current_tenant', :t, true)` **inside each of the three transactions**: txn 1, txn 2, and the independent confirming read. Omitting txn 2's bind must yield SQLSTATE `42501` from the `budgets` RLS policy. Session-level `set_config(..., false)` is forbidden. |
| 2 | B2-5 was writer-specific but stored only on a deduplicated leaf, so one candidate's true citation could mask another candidate sharing the leaf. | OD-7 adds `B2_EDGE_EVIDENCE`, keyed by the exact candidate→leaf edge and carrying that candidate's citation plus exact parent leaf. Inventory test 7 enumerates every B2 edge. If any candidate sharing a leaf lacks valid B2-5 evidence, the **whole shared leaf** must be Tier A. P-MUT-16 proves one cited edge cannot mask one uncited edge. |
| 3 | §3.1 still said “Commit per writer,” and OD-9 commit 5 said six §3.2 tests although §3.2 defines seven. | **Historical v4 lock — superseded by v6 §0A.6 (commits 6–14 by subtier).** OD-9 remained the single authority: commits 1–2 splits, 3 RED, **4 one fix commit for all six writers**, 5 inventory with **seven** tests, then v4's 6–9 barrier batches. §3.1 now forbids six per-writer fix commits. |
| 4 | `PromotionRefConflict` still had an unlocked “builder picks one home” choice, and §1a-split called the five modified production files six. | `PromotionRefConflict` is locked in `app/repositories/extraction_promotion.py`; `app/repositories/extraction.py` re-exports it. The manifest language now says **five modified, five created** throughout. |

**v3 corrections — all four of Sol's v2 defects accepted in full, none argued down.** Each was
re-verified live before being written in.

| # | Sol's v2 defect | Correction in v3 |
|---|---|---|
| 1 | P-GREEN-1b was underspecified: `func.now()` did **not** advance `updated_at`, because two upserts inside **one** transaction share one `now()`. | Confirmed live (§0.1.19): `now()` is `transaction_timestamp()` and is frozen for the transaction. P-GREEN-1b is re-locked to **one `AsyncSession(rls_engine, expire_on_commit=False)` across two separately committed transactions**, with the stored value re-read through an **independent** session so the assertion cannot be satisfied by the identity map. The `updated_at` mechanism itself is unchanged — the defect was in the probe, not the fix. |
| 2 | "One or more leaves" contradicted four surviving "**exactly one** leaf / barrier" statements (v2 lines 57, 247, 261, 1083). Index completeness was enforced per **table**, which a one-to-many mapping can satisfy while a specific candidate still omits an axis. | All four statements replaced with "**one or more leaves; one tiered barrier per leaf**". Inventory test 5 is re-scoped to **per-candidate** completeness: for every candidate, for every table it writes, every collidable index on that table must appear in **that candidate's** `leaf_ids`. New P-MUT-14 proves the per-table form would have passed where the per-candidate form fails. |
| 3 | §0 called the whole thing a "two-writer barrier suite" although only Tier A executes two writers; and Tier B2 never verified its claimed FK mapping through `pg_constraint`. | Renamed throughout to a **tiered** barrier suite (a two-writer harness is Tier A's instrument, not the suite's name). OD-8's Tier B2 now requires four `pg_constraint`/`pg_attrdef`-backed assertions, and **any leaf that fails any of them is reclassified Tier A** (fail closed). The one B2 premise the catalog *cannot* prove — that the writer mints the parent row in the same transaction — is stated as such, must be cited to an exact writer line, and is a named limitation. |
| 4 | Commit order was self-contradictory: OD-9 said splits first, §7 listed RED first, and §3.2 told the builder to update the inventory "in the same commit as each split" although the inventory module does not exist yet. Also §1a's "exactly six / no other `app/` file" manifest omitted the four split modules. | **One executable order locked in OD-9** (§2) and mirrored verbatim in §7 and §4.1: splits → RED → fixes → inventory → four barrier batches. The §3.2 contradiction is removed — the inventory is authored **once, after** the splits, against post-split paths. §1a's manifest is corrected to **ten** production files: five modified, five created. |

**v1 → v2 corrections, retained as history.** All six of Sol's v1 defects, accepted in full and
each re-verified on the live database before being written in; none was absorbed silently.

| # | Sol's defect | Correction in v2 |
|---|---|---|
| 1 | v1's OD-2 row 1 (`DO UPDATE … RETURNING id` then `session.get()`) returns the **stale identity-mapped** instance. Sol's probe: `same_identity=True`, `returned_caps=1,1`, `stored_caps=2,2`. | OD-2 row 1 rewritten: `RETURNING` the row, then a re-select with `execution_options(populate_existing=True)` so the returned instance carries the **stored** caps; `updated_at` stamped explicitly in `set_` because Core `onupdate` does not fire in a `DO UPDATE` clause; plus a new sequential update regression (P-GREEN-1b) and its mutation (P-MUT-1b). Grounding fact §0.1.17. *(v2 specified P-GREEN-1b as same-session, same-transaction; **re-locked in v3** to two committed transactions — v2 defect 1.)* |
| 2 | The inventory could not represent a **multi-key** writer; `register_version` has two collidable indexes. | `Candidate.leaf_ids` is now **one-to-many** (OD-7); a fifth inventory test asserts **index-coverage completeness** — every collidable index on any written table must be a declared leaf — so removing either `agent_versions` axis fails (P-MUT-10). OD-10 restated for the one-to-many mapping. *(v2 enforced that completeness **per table**; **re-scoped in v3** to per candidate, and v2's four surviving "exactly one leaf/barrier" statements removed — v2 defect 2.)* |
| 3 | The OD-8 `pg_index` query read **all** `indkey` attributes, so it counts `INCLUDE` columns; Sol's `UNIQUE(code) INCLUDE(id)` mutation returned zero rows. | OD-8 query replaced with an `indnkeyatts`-bounded form, re-verified live (§0.1.16): it returns the same `120`/`88` on `0062` and now **detects** the INCLUDE mutation (`1` row vs the old query's `0`). Sol's mutation is retained as P-MUT-11. |
| 4 | OD-3 and OD-5 contradicted each other on `register_version`. | One ladder locked in OD-3, and OD-5 now defers to it explicitly: content-hash re-select → `(blueprint_id, version_label)` re-select → differing-content label match ⇒ `VersionLabelConflict` → neither visible ⇒ `ConcurrentWriteUnresolved`. |
| 5 | v1's OD-4 caught **every** `IntegrityError` and assumed "no promotion row", mislabelling FK / CHECK / NOT NULL failures as a promotion conflict. | OD-4 now requires SQLSTATE **`23505`** *and* a constraint name in `{uq_intake_artifacts_ref, uq_extraction_promotions_proposal}`, branches per constraint, and **re-raises everything else unchanged**; controls P-GREEN-6c and P-MUT-12 prove the re-raise. |
| 6 | §1 / OD-9 imposed the 500-line cap on created test modules but not on **modified production** files (`cost_forecasts.py`, `extraction.py`). | Measured `wc -l` on `72ee544`: `cost_forecasts.py` **858**, `extraction.py` **491** (Sol quoted 859 / 492; the one-line difference does not touch the defect — one already violates the cap and the other crosses it the moment the fix lands). §1a-split and OD-9 lock **exact** module splits as pure-move commits with every public symbol re-exported. |

**Finding.** **F-020** (`.planning/FINAL-AUDIT-REPORT.md:744`; evidence §4.6 `:1230-1296`; census
Appendix B `:1676-1913`; the single retained pair `:1314`). **Slice.** **83** — Wave 1, second
numbered remediation slice (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:730-731`, next-slice pointer
`:743`; `.planning/HANDOFF.json` `next_action`).

**Base.** `origin/main` = **`72ee544`** (docs close-out of Slice 84, PR #121). Slice 84 / F-021 is
merged tests-only at `65e85c4` (PR #120). No F-020 code or test changed between `65e85c4` and
`72ee544`.

**Alembic.** Live head confirmed by `uv run alembic heads` → **`0062 (head)`**
(`migrations/versions/0062_enterprise_admin.py`). **This slice adds no migration and head stays
0062** (OD-1). Every one of the six fixes is a Python-level conflict-handling change; no table,
column, constraint, trigger, grant, or index is added, altered, or dropped.

**Frozen — not touched.** `app/release/production_autonomy.py`, `app/intake/readiness.py`,
`.github/workflows/`, `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`, and
`.planning/FINAL-AUDIT-REPORT.md`. `can_go_live_autonomously` stays the literal `False`; A5 stays
`slice54.v1`; readiness stays `slice20.v1`; §2.6 mandatory-approval is not softened.

**Never** weaken, skip, `xfail`, or delete a test. **Never** re-grant a privilege to make a probe
pass. **No** `pytest.raises(Exception)` without `match=`. **No** alternation across two different
refusal classes in any assertion this slice writes.

---

## 0A. The owner-ruled tier amendment (v6, authoritative)

This section governs the whole plan. It replaces v5's single Tier-A class with three consequence
subtiers, redefines GREEN per subtier, derives the §1a production manifest, and re-locks the commit
order from **6**. Nothing here reduces coverage, drops a tier, or splits Slice 83.

### 0A.1 Tier definitions (amended)

| Tier | Definition | Consequence of losing the race | Production change |
|---|---|---|---|
| **A1 — derived-write** | The writer **reads** committed state and writes a value **derived from that read** into the contended key: a hash-chain value, a `previous_*` pointer, a sequence/ordinal derived from a **count or head read**, a true upsert branch, a `supersedes_*` link, or any ledger predecessor. | The loser persists a **WRONG row, silently**. This is the **OD-11 class**. | **AUTHORIZED.** §1a expands to exactly this set. |
| **A2 — independent-insert** | Create-once on a unique key over **caller-supplied or caller-derived** columns, and **no** inserted value depends on a prior read of that key. | The loser raises **`23505` to the caller and persists nothing wrong**. | **NONE.** Tests only. |
| **A3 — append-only** | **No** collidable key over caller-supplied columns: the unique key contains an identifier minted **inside the same call**, so concurrent calls legitimately produce **distinct rows**. | Both callers succeed; no collision is reachable. | **NONE.** Tests only. |
| **B1** | Unchanged from v5: the table is absent from the OD-8 collidable query. | — | None. |
| **B2** | Unchanged from v5: child writers covered by their parent's node under B2-1…B2-5. | — | None. |

**Forbidden.** Do **not** add conflict handling to an A2 or A3 leaf. An escaped `23505` on an A2 leaf
is the **correct observed behaviour**; defending against a race that corrupts nothing is the Slice 61a
mistake and is a review rejection.

**Tier A did not shrink.** 112 leaves in v5, 112 leaves in v6. A is **subdivided**, not redefined:
21 + 38 + 53 = 112, machine-checked against `WRITE_LEAVES`.

### 0A.2 The evidence rule — classification is evidence, not judgement

For **every** leaf the plan records both of:

- **(a)** the **unique constraint name** over caller-supplied columns together with its **key columns
  and partial predicate**, quoted from the live catalog by the OD-8 query — or its **proven absence**
  from that query (B1);
- **(b)** whether the writer **reads-then-derives**, citing the **exact `file:line` of the read** and
  the **exact `file:line` of the derived value**. If no such read exists, the **write site** is cited
  and the row states **"no prior-state derivation"**.

**A1 requires both citations present.** A leaf placed in **A2 or A3 without** the catalog query result
and the read-then-derive check is a **defect**, not a shortcut. **Builder judgement alone never
suffices**, and this rule must not become a route to a smaller A1.

**The discriminator, stated once so no row can be argued.** A read that produces a value whose
correctness depends on being the **latest committed state** — `ORDER BY … DESC LIMIT 1`, `max()`,
`count()`, `nextval` plus a predecessor hash, a head read that chooses insert-vs-skip on the contended
key, or an `ON CONFLICT DO UPDATE` whose `set_` values came from a pre-read — is a **derivation** (A1).
A plain existence or validation read of a row whose identity the **caller supplied**, and an **in-call
positional counter** over children of a parent minted in the same call, are **not** derivations. That
second clause is the single biggest lever on the A1 count and is therefore stated explicitly and cited
per leaf: an `ordinal`/`seq` that counts committed rows is A1; an `ordinal`/`seq` that enumerates a
list the same call is about to write under a freshly minted parent is A3.

**Two fail-closed steps, in this order.**

1. If a `previous_*` / `seq` / `ordinal` / chain-`hash` / upsert / `supersedes` path exists on the
   contended key and **independence of every key column from any read cannot be proven**, the leaf is
   **A1**.
2. If A3's premise — that concurrent callers cannot collide — **cannot be proven**, the leaf is
   **A2**, never A3. (A2 and A3 are both tests-only, so this step cannot hide an A1.)

**Sibling-axis rule.** If **any** collidable axis written by one `INSERT` statement is A1, **every**
collidable axis written by that same statement is A1. PostgreSQL reports whichever unique index it
reaches first (§0.1.3), so the loser's observed axis is **nondeterministic**; classifying siblings
differently would let a derived-write race be observed on an A2-labelled axis under an A2-strength
barrier. This is why `emergency_stop_events.uq_ese_idempotency` and the two non-`previous`
`production_preapproval_lifecycle_events` axes are A1.

**Where the per-leaf evidence lives.** `.planning/SLICE-83-LEAF-EVIDENCE.md` — **planner-owned and part
of this plan contract**. It carries all **168** leaves: **21** A1 rows with both citations, **38** A2 rows
with an independence citation, 53 A3 rows with a minted-parent citation, and the unchanged 54 B1 / 2 B2
rows. The builder **mirrors** its subtier column into `tests/writer_inventory_c.py` and must
**stop and report** any disagreement rather than editing either side.

**One A1 row has an empty "read of committed state" field, and that is not a defect.**
`run_checkpoint_writes.uq_run_checkpoint_writes_id` (v7 defect 1) is A1 because its writer holds an
`ON CONFLICT DO UPDATE`, which the owner's ruling lists as an A1 path **irrespective of whether a read
precedes it** — the writer *resolves* the contended key instead of letting a create-once failure reach the
caller. For that one row §0A.2's "both citations" requirement is met by **(a)** the unique index over
caller-supplied columns and **(b)** the **upsert citation** `app/runtime/checkpointer.py:152-167` in place
of a read citation, with the absence of any pre-read stated explicitly rather than left blank. No other A1
row may use this form; every other A1 row cites a real read and a real derived value.

### 0A.3 A1 COUNT — reported prominently

> ## **A1 = 21 leaves. 21 ≤ 40, so this is NOT a halt.**
>
> A2 = **38** · A3 = **53** · B1 = **54** · B2 = **2** · total **168**.
> (v7: ~~A1 = 20 / A2 = 39~~ — `run_checkpoint_writes.uq_run_checkpoint_writes_id` moved A2 → A1 on
> Sol's defect 1. Tier A is still **112**; coverage is unchanged.)

The exact A1 leaf-id list, in the evidence file's order. **Column 3 is the *fix* column, not the
*coverage* column** — "none" means no production change, never no node: **all 21 keep a retained A1
two-session node with an absent-read barrier, a mutation control, and the only-wrong-axis assertion.**

| # | A1 leaf id | production change |
|---|---|---|
| 1 | `audit_logs.uq_audit_logs_seq` | none (advisory lock `421`) |
| 2 | `audit_logs.uq_audit_logs_entry_hash` | none (advisory lock `421`) |
| 3 | `go_live_decisions.uq_gld_previous` | none (`projects` row `FOR UPDATE` inside the SECURITY DEFINER function) |
| 4 | `go_live_decisions.uq_gld_entry_hash` | none (same) |
| 5 | `go_live_decisions.uq_gld_project_root` | none (same) |
| 6 | `go_live_decisions.uq_gld_evaluation` | none (already a named domain error) |
| 7 | `control_loop_events.uq_cle_run_ordinal` | **REQUIRED** — `app/repositories/go_live_decisions.py` |
| 8 | `control_loop_events.uq_cle_previous` | **REQUIRED** — same module |
| 9 | `control_loop_events.uq_cle_loop_root` | **REQUIRED** — same module |
| 10 | `acceptance_criterion_authorship_records.uq_acar_criterion_sequence` | **REQUIRED** — `app/repositories/acceptance_verification.py` |
| 11 | `acceptance_criterion_authorship_records.uq_acar_supersedes_once` | **REQUIRED** — same module |
| 12 | `emergency_stop_events.uq_ese_previous` | none (`lock_project_row` on `activate`/`clear`) |
| 13 | `emergency_stop_events.uq_ese_project_root` | **REQUIRED** — `app/repositories/emergency_controls.py` (`append_binding`) |
| 14 | `emergency_stop_events.uq_ese_idempotency` | none (sibling-axis rule; `lock_project_row`) |
| 15 | `production_preapproval_lifecycle_events.uq_pple_previous` | **REQUIRED** — `app/release/production_approval_service.py` |
| 16 | `production_preapproval_lifecycle_events.uq_pple_attestation_event` | **REQUIRED** — same module |
| 17 | `production_preapproval_lifecycle_events.uq_pple_idempotency` | **REQUIRED** — same module |
| 18 | `budgets.uq_budgets_tenant_id_project_id` | none — landed in commit 4; node registered |
| 19 | `autonomy_policies.uq_autonomy_policies_tenant_id_project_id` | none — landed in Slice 63; node registered |
| 20 | `admin_policy_changes.uq_admin_policy_changes_action` | **none possible** — migration-frozen (§0A.7) |
| **21** | **`run_checkpoint_writes.uq_run_checkpoint_writes_id`** *(v7, Sol defect 1)* | **none** — the existing atomic `ON CONFLICT DO UPDATE` at `app/runtime/checkpointer.py:152-167` already meets A1 GREEN; **no pre-read exists**, so no derived value can go stale. `app/runtime/checkpointer.py` is therefore **NOT** added to §1a-v7. |

**Rows 3–5 lock `projects FOR UPDATE` legally, and that does not contradict v7 defect 2.** That lock
lives at `migrations/versions/0054_control_loop_decisions.py:650` inside `slice55_finalize_decision`,
which is `prosecdef = true` (**SECURITY DEFINER**, §0.1.31) — it runs as the function owner, not as
`uaid_app`, so its `FOR UPDATE` privileges are the owner's. Defect 2 applies only to the **new** locks
this slice adds from **Python as `uaid_app`**, which is why §0A.5 targets `projects` and nothing else.

**The split of the 21, corrected in v7.** v6 stated these two numbers the wrong way round; the
correction is arithmetic and is not one of Sol's three defects, but it is recorded rather than absorbed:

| | v6 said | v7 (verified against the table above) |
|---|---|---|
| A1 leaves owned by the four §1a-v7 modules | ~~11~~ | **9** — rows 7, 8, 9, 10, 11, 13, 15, 16, 17 |
| A1 leaves proven **by barrier alone** (no production change) | ~~9~~ | **12** — rows 1, 2, 3, 4, 5, 6, 12, 14, 18, 19, 20, **21** |

9 + 12 = **21** ✓. The barrier-alone count rose by exactly one — the new row 21 — because
`run_checkpoint_writes` needs a node but no fix. OD-9 §0A.6 commits 7 and 8 are re-locked to these
corrected counts.

**No A1 leaf was hidden in A2 or A3.** The scan is mechanical and reproducible: every catalog index
whose key columns contain `previous_*`, `supersedes_*`, a chain `entry_hash`, or a `seq`/`ordinal`, and
every writer holding an `ON CONFLICT DO UPDATE` or a head-read-then-insert branch, appears above or is
excluded in the evidence file with the in-call-counter citation that excludes it. **v7 additionally
re-audited every upsert path in the repository** — the audit that Sol's defect 1 proved v6 had cut short
— and the result is grounding fact §0.1.29: **exactly two** `on_conflict_do_update` call sites exist in
`app/` (`cost.py:210` → `budgets`, A1 row 18; `checkpointer.py:152` → `run_checkpoint_writes`, A1 row
21), **exactly one** raw `ON CONFLICT … DO UPDATE` exists in `app/` (`admin/policy_sql.py:91`, which is
inside `_RACY_UPSERT_AND_SPEND` and is emitted **only** when `racy_first_write=True` at `:179` — the
deliberately racy **mutation-probe** variant, not the installed path), and **zero** exist in
`migrations/`. **Every upsert path therefore maps to an A1 leaf and none is left in A2 or A3.** Row 19
(`autonomy_policies`) is A1 by **read-then-derive**, not by upsert: its installed path is
`_SERIALIZE_AND_SPEND` — `DO NOTHING` (`:107`), a locked `FOR UPDATE` re-read (`:110-114`), then
`UPDATE … RETURNING` (`:122-127`) — which is exactly what its evidence row cites.

### 0A.4 GREEN contracts per subtier

Every subtier keeps a **retained two-session node with an absent-read barrier and a mutation probe**.
What the node asserts differs.

**A1 GREEN.** Atomic conflict handling. The caller receives **the winner or a named domain result**,
and **the loser never persists a derived value read before the winner committed**. Concretely: exactly
one row on the contended key or two rows whose derived chain is **correct and consistent**; no raw
`IntegrityError` and no `23505` reaches the caller; where the writer already runs at SERIALIZABLE the
loser may instead surface `40001`/`40P01` or the owned wrapper's post-retry result; an aborted loser is
rolled back, never committed. For chain leaves the node additionally asserts chain validity under
contention (`audit_verify()` for `audit_logs`; a single unbroken `previous_*` chain elsewhere).

**A1 GREEN for an already-atomic upsert leaf (v7, Sol defect 1 — the `run_checkpoint_writes` case).**
Where the writer's conflict handling *is* the statement (`ON CONFLICT DO UPDATE`) and **no read precedes
it**, the A1 contract is met by the existing code and the node asserts the observable consequence rather
than a new mechanism. For `run_checkpoint_writes.uq_run_checkpoint_writes_id`
(`app/runtime/checkpointer.py:152-167`) the node asserts, under two concurrent `aput_writes` calls on the
same `(thread_id, checkpoint_ns, checkpoint_id, task_id, idx)`:

1. **both** transactions commit — neither caller sees `23505`, `IntegrityError`, or any raised exception;
2. **exactly one** row exists on the contended key;
3. the surviving row's `(channel, type, blob, task_path)` equals **one caller's tuple in full** — it is
   **never a mix** of the two callers' values, which is what makes the atomicity observed rather than
   assumed;
4. tenant attribution is correct and no deadlock occurs;
5. the observed constraint name equals the leaf's `unique_index` (only-wrong-axis control).

Its **mutation control** is the A1 form, not the A2 form: replace `on_conflict_do_update` with a plain
`pg_insert(...)` (no conflict clause) and the test must fail with a raw `23505` reaching the caller. That
mutation is what proves the existing `DO UPDATE` is load-bearing, and it is the reason this leaf is A1
with **zero** production change rather than A2. What the node does **not** claim is that last-writer-wins
is the *correct* merge semantics — see the §0A.7 limitation.

**A2 GREEN (redefined — this is the amendment).** **Exactly one row** exists on the contended key after
the barrier; the loser **fails cleanly with no partial state** — either raising `23505` /
`IntegrityError`, **which is the correct observed behaviour and is asserted as such**, or, where the
writer *already* reconciles, returning the winner; **correct tenant attribution**; **no deadlock**.
The node **must not** be "fixed" into an A1 contract, and no conflict handling may be added.

**A3 GREEN.** **Both** transactions commit, **both rows exist and are distinct**, and attribution is
correct. The node also asserts that the two rows' minted parent identifiers differ — that is what makes
non-collidability observed rather than assumed.

**Mutation controls, still required for every leaf.**

- **A1** — a mutation that removes **only** the new serialization/conflict handling and shows the racy
  outcome return (a raw `23505`, or a wrong derived value).
- **A2** — a mutation that proves the **assertion is load-bearing**: with the barrier's absent-read
  removed (so the row is pre-seeded and the writer takes its idempotent path) the test must **fail**,
  because a single-session pre-seeded probe never reaches the contended insert (§0.1.7).
- **A3** — a mutation that collapses the two calls onto **one** minted parent identifier and shows the
  distinctness assertion fail.

**Only-wrong-axis control (mandatory, all subtiers).** Each barrier must contend **its own** declared
unique index. The node asserts the observed constraint name **equals** the leaf's `unique_index`. If the
only reachable contention path collides first on a **different** index — including a different axis of
the same table — that is a **stop-and-report**, not a pass, and never a silent downgrade of the leaf.

### 0A.5 Derived §1a production file list — A1 only, no extras

**Exactly four `app/` modules change from commit 6 onward** — unchanged in count by v7. **No fifth module
is added:** `app/runtime/checkpointer.py` carries A1 leaf 21 but needs **no** production change (§0A.3
row 21, §0A.4), so it stays out of this manifest.

**v7 re-locks the mechanism column (Sol defect 2).** v6 planned `FOR UPDATE` on `intake_artifacts`,
`control_loop_runs`, and `production_preapproval_attestations`. All three are **SELECT/INSERT-only** for
`uaid_app`, so `SELECT … FOR UPDATE` fails with SQLSTATE **`42501`** — reproduced live on all three
(§0.1.30). Those three targets are **struck**. Every lock now targets **`projects`**, the one table in
these writers' reach that `uaid_app` holds `UPDATE` on (§0.1.30, §0.1.31), through the **existing**
helper `lock_project_row` (`app/repositories/emergency_controls.py:79`). **No GRANT and no migration** —
Alembic head stays `0062`.

| # | module | A1 leaves it must fix | locked mechanism (v7) | ~~v6 mechanism (struck: `42501`)~~ |
|---|---|---|---|---|
| 1 | `app/repositories/acceptance_verification.py` | `uq_acar_criterion_sequence`, `uq_acar_supersedes_once` | `lock_project_row(self.session, self.context, project_id)` immediately before each `_current_record` call — `:84`, `:128`, `:167`. `project_id` is already a **parameter** of all three `record_*` methods (`:69` and peers) and of `_current_record` (`:43`). | ~~lock the criterion's `intake_artifacts` row `FOR UPDATE`~~ |
| 2 | `app/repositories/emergency_controls.py` | `uq_ese_project_root` | this module's own `lock_project_row` (`:79`) in `append_binding` before the `:437` head read | *(unchanged — already `projects`)* |
| 3 | `app/repositories/go_live_decisions.py` | `uq_cle_run_ordinal`, `uq_cle_previous`, `uq_cle_loop_root` | `lock_project_row(..., cycle.project_id)` inserted **between `:298` and `:299`** — `cycle = await self._require_cycle(...)` already resolves at `:298`, before the head read, and `cycle.project_id` is already used at `:325`, so no new read is introduced | ~~lock the parent `control_loop_runs` row `FOR UPDATE`~~ |
| 4 | `app/release/production_approval_service.py` | `uq_pple_previous`, `uq_pple_attestation_event`, `uq_pple_idempotency` | `lock_project_row(..., project_id)` before the **first** read of each derive chain: before `:231` (the `prior` attestation select, which precedes the `:248` head read) and before `:326` in `revoke`. `project_id` is a **parameter** at both sites (used at `:236`; `revoke` signature `:324`). | ~~lock the `production_preapproval_attestations` row `FOR UPDATE`~~ |

Plus the **ten already-landed** §1a files of commits 1–4, which remain in the manifest unchanged (five
modified, five created). **No other `app/` file may change.** These four modules own **9** A1 leaves
(rows 7–11, 13, 15–17); the remaining **12** A1 leaves are proven by barrier alone — the corrected split
in §0A.3, replacing v6's transposed 11/9.

**Builder verification gate for the mechanism (mandatory, v7).** Before writing any lock, the builder
runs, as the runtime role, `SELECT … FROM public.projects WHERE id=:p AND tenant_id=:t FOR UPDATE` and
quotes the success; and confirms from `information_schema.role_table_grants` that the target of **every**
lock this slice adds has `UPDATE` granted to `uaid_app`. **A `42501` from any newly added lock is a
stop-and-report**, never a workaround, a GRANT, or a migration.

**One mechanism, four modules: serialize on the project row before deriving.** This follows the in-repo
precedent verbatim (`emergency_controls.activate` `:500`, `emergency_controls.clear` `:570`,
`ops_stabilization.attempt_closure` `:162`, and the `projects … FOR UPDATE` that
`slice55_finalize_decision` itself takes at `0054_control_loop_decisions.py:650`). Consequences, all
binding:

- **No new module and no new exception class.** `ConcurrentWriteUnresolved` (`app/concurrency.py`)
  already exists and is **not** extended.
- **Corrected in v7: three modules add exactly one import each.** v6 said "no new import"; that is
  **superseded**. `acceptance_verification.py`, `go_live_decisions.py`, and
  `production_approval_service.py` each add `from app.repositories.emergency_controls import
  lock_project_row`; `emergency_controls.py` already owns it. This is an existing helper reused, not a
  new file — the precedent is `ops_stabilization.py:62` and `emergency_control_service.py:16`, which
  import it the same way. **No import cycle exists**: all four modules import cleanly alongside
  `emergency_controls` (§0.1.32). If any import raises, that is a **stop-and-report**, not a new shared
  module.
- **Coarser granularity than v6 planned, and stated as such.** A project-row lock serializes *all* A1
  writers of that project, not only the contended criterion / cycle / attestation. It is correct and
  fail-closed, it is what the runtime role is actually permitted to do, and it is **not** claimed to be
  minimum-granularity — see the §0A.7 limitation.
- **The loser blocks, then re-derives from committed state.** It does not collide, so no new
  conflict-handling branch and no new error path is introduced. Where the writer runs at SERIALIZABLE
  (`append_event`, via the control loop's owned wrapper at `go_live_decisions.py:157`) the loser may
  surface `40001`, which the **existing** owned retry already handles — that is an A1-GREEN outcome and
  no retry loop is added.
- **A legitimate post-lock refusal is A1 GREEN.** After re-reading the committed head, a transition
  validator or lifecycle check may refuse with an existing named domain error (for example
  `control_loop_event_transition_invalid`, or `revoke`'s idempotent-replay return at
  `production_approval_service.py:337-338`). That is "the winner or a named domain result" and is
  asserted as such.

Rejected: adding a `savepoint` + `23505` handler per writer (four bespoke handlers where one lock
suffices, and it would introduce new caller-visible error paths this slice was not asked to add);
rejected: raising the isolation level of any writer that does not already own one (v5 §0 forbids it);
rejected: a new shared locking helper module (an extra file, which the ruling's "no extras" clause
forbids).

**The 500-line cap and the two already-oversized modules.** `emergency_controls.py` is **790** lines and
`go_live_decisions.py` is **627** on `1aa7225`; both already exceed the house cap **before** this slice
touches them. `acceptance_verification.py` (**456**) and `production_approval_service.py` (**383**) stay
under it after the change. **Locked decision: the two oversized modules are NOT split.** The ruling
states §1a expands to **exactly** the A1 writer modules with **no extras**, and a split creates extra
modules; splitting the Slice-54/55 control-plane repositories would also enlarge the diff far beyond a
few lines of locking. This is recorded as the named limitation
`emergency_controls_and_go_live_decisions_remain_over_the_500_line_cap`, and it **supersedes** the v5
rule at §OD-9 ("every file this slice modifies is ≤ 500 lines after the modification") **for these two
files only**. Every file this slice **creates** stays ≤ 500 lines, with overflow into `_b.py` then
`_c.py`, exactly as v5 locked.

### 0A.6 OD-9 re-locked from commit 6

Commits **1–5** are landed at `ff87704`, `b8a5321`, `7a0347f`, `9d0e543`, `43d5ceb` and are **not
rewritten**. The remaining order:

| # | Commit | Contents | Gate to pass before moving on |
|---|---|---|---|
| **6** | `test(slice-83): publish the A1/A2/A3 consequence subtiers` | `tests/writer_inventory_c.py` carrying `SUBTIER` for all 112 Tier-A leaves, mirrored from the evidence file; two new inventory tests — **8**: every Tier-A leaf has exactly one subtier in `{A1,A2,A3}` and no B leaf has one; **9**: the A1 set equals the plan's §0A.3 list verbatim, i.e. **21** ids including `run_checkpoint_writes.uq_run_checkpoint_writes_id`, and the A2/A3 sets have **38**/**53** members. | Inventory tests 1–9 green. `git diff --stat -- app/` **empty** for this commit. |
| **7** | `fix(concurrency): serialize the derived reads behind the A1 write leaves` | The **four** §0A.5 modules, each locking **`projects`** via `lock_project_row` (v7 defect 2); A1 GREEN + mutation + only-wrong-axis nodes for the **9** leaves those modules own (§0A.3 rows 7–11, 13, 15–17); those **9** leaf ids move from `PENDING_TIER_A_BATCHES` into `TIER_A_NODE_MAP` in the same commit. | The `projects FOR UPDATE` privilege probe quoted **before** the first lock is written (§0A.5 gate); every A1 GREEN and mutation transcript quoted; `wc -l` quoted for all four; the two oversized modules' line counts quoted as the named limitation. **No `42501` from any added lock.** |
| **8** | `test(slice-83): A1 barriers for the barrier-alone leaves` | A1 nodes for the remaining **12** A1 leaves — `audit_logs` ×2 (rows 1–2), `go_live_decisions` ×4 (rows 3–6), `emergency_stop_events` ×2 (rows 12, 14), `admin_policy_changes` ×1 (row 20), **`run_checkpoint_writes` ×1 (row 21, v7)** — plus registration for the already-nodded `budgets` / `autonomy_policies` (rows 18–19). Tests only. | Chain-validity assertions quoted (`audit_verify()`); row 21's node asserts the five §0A.4 upsert clauses and its mutation removes `on_conflict_do_update` and shows a raw `23505`; `admin_policy_changes`'s migration-frozen limitation recorded, **not** fixed. `git diff --stat -- app/` **empty**. |
| **9–10** | `test(slice-83): A2 barriers for {tenant,platform} leaves` | A2 nodes for the **32** unregistered A2 leaves (~16 per commit) — **v7: 32, not 33**, because `run_checkpoint_writes` left A2 for A1; the 6 already-registered A2 leaves keep their nodes and are re-asserted against the A2 contract. **No production file may change in either commit.** | `git diff --stat -- app/` empty for both; pending shrinks monotonically. |
| **11–13** | `test(slice-83): A3 barriers for {evidence,ops,release} leaves` | A3 nodes for the **53** A3 leaves, ~18 per commit. **No production file may change.** | `git diff --stat -- app/` empty; pending shrinks monotonically. |
| **14** | `test(slice-83): close the inventory` | `assert PENDING_TIER_A_BATCHES == frozenset()`; inventory test 8 strengthened so **every** Tier-A leaf has a registered, collectible node **and** a subtier; the evidence file's A1 rows asserted to carry both citations. | Both suites green; P-MUT-17 and P-MUT-18 pass; no Tier-A leaf pending, unclassified, or unnodded. |

Every commit leaves `make test` and `make test-db` green on its own. `PENDING_TIER_A_BATCHES` still may
never gain a leaf after commit 5, and a leaf leaves it only in the same commit that adds its node
(v5 OD-9 commit-5 sequencing lock, unchanged). **No leaf is parked and no leaf moves to a later
slice.** The v5 stop-and-report trigger stands with one amendment: the "projected Tier-A count exceeds
60 leaves" clause is **discharged** — the count is measured at 112 and subdivided, and subdivision is
the owner's ruling, not a coverage reduction. The wall-time trigger (**+240 s** over the `72ee544`
baseline) stands.

### 0A.7 Named limitations added by v6

- `admin_policy_changes_double_spend_raises_raw_sqlstate` — the derived write behind
  `admin_policy_changes.uq_admin_policy_changes_action` lives inside a SECURITY DEFINER function
  installed by migration `0062` (body at `app/admin/policy_sql.py:58-77`). OD-1 forbids a migration, so
  a double-spend of one `admin_action_id` still surfaces a raw SQLSTATE. Its A1 GREEN is met only in the
  weaker recorded form: **exactly one ledger row exists and the policy is not changed twice**.
- `emergency_controls_and_go_live_decisions_remain_over_the_500_line_cap` — 790 and 627 lines, already
  over before this slice; not split (§0A.5).
- `a1_a2_a3_subtier_is_a_consequence_classification_not_a_proof_of_absence_of_other_anomalies` — the
  subtiers classify only the **unique-violation** conflict class. Lost update, write skew, phantoms, and
  logical latest-wins anomalies remain out of scope, exactly as v5 §0.5 states.
- `four_a1_fixes_serialize_a_read_they_do_not_prove_the_lock_is_the_narrowest_possible` — each fix takes
  an existing parent or project row lock, following the in-repo precedent. It is correct and
  fail-closed, not proven minimal-granularity.
- `a2_no_production_change_rule_applies_from_commit_6_not_retroactively` — see §0A.8.
- **`run_checkpoint_write_upsert_is_last_writer_wins_not_a_proven_merge`** *(v7, Sol defect 1)* — A1 leaf
  21's `ON CONFLICT DO UPDATE` (`app/runtime/checkpointer.py:161-166`) overwrites
  `channel`/`type`/`blob`/`task_path` with whichever caller commits last. Its node proves the write is
  **atomic** and that the surviving row is **one caller's tuple in full, never a mix**. It does **not**
  prove that last-writer-wins is the semantically correct resolution for two genuinely different writes
  on the same `(task_id, idx)`; under LangGraph's contract that key identifies one task's one write, so
  a re-put is expected to be idempotent, but this slice **observes** the atomicity rather than proving
  the framework contract. No production change is made, so no behaviour changes either way.
- **`a1_locks_serialize_the_project_row_not_the_contended_child`** *(v7, Sol defect 2)* — because
  `uaid_app` has no `UPDATE` on `intake_artifacts`, `control_loop_runs`, or
  `production_preapproval_attestations` (live `42501`, §0.1.30), all four A1 fixes lock **`projects`**.
  That is coarser than the child-row lock v6 planned: it serializes every A1 writer of the project, not
  only the contended criterion / cycle / attestation. It is correct, fail-closed, privilege-compatible,
  and precedent-following (`0054_control_loop_decisions.py:650`), and it is **not** minimum-granularity.
  Narrowing it would need a GRANT or a migration, both forbidden by OD-1 this slice.
- **`census_wrapper_span_443_472_is_an_audit_constant_not_a_writer_citation`** *(v7, Sol defect 3)* — the
  landed `CENSUS_SCANNER` wrapper tuple in `tests/writer_inventory_b.py` reads
  `app/repositories/go_live_decisions.py:443-472`. Line `:443` is **blank**; `finalize_decision` actually
  spans `:444-473` with its SQL call at `:452` (§0.1.32). That tuple is a hand-authored constant of the
  Appendix-B reproduction landed at commit 5 and is kept **byte-identical** — v7 does not rewrite a
  landed commit to change an audit constant. The **evidence file's writer citations are corrected** to
  `:444`/`:452`, and the two coordinate systems must **never** be quoted interchangeably: an inventory
  wrapper span is a census coordinate, a writer citation is a source coordinate. Any future statement
  that `finalize_decision` "begins at 443" is a defect.
- `subtier_assignment_is_planner_authored_and_review_verified` — the citations are machine-quoted from
  the live catalog and from source, but the A1/A2/A3 assignment itself is planner-authored and
  Sol-reviewed, not machine-derived. This is the same honesty tier as v5's hand-authored
  candidate→leaf mapping (§0.1.9).

### 0A.8 The commit-4 consequence, stated plainly rather than absorbed

Measured against the amended standard, commit 4 (`9d0e543`) hardened six writers of which **only
`budgets` is A1**; `agent_blueprints`, both `agent_versions` axes, `tenant_catalog_adoptions`,
`cost_forecast_policy_versions`, and `intake_artifacts` are **A2** — their pre-fix losers raised `23505`
and persisted nothing wrong. Under §0A.1 those five would today be **tests only**.

Three things follow, and none of them is a silent edit:

1. **Commits 1–5 are landed and are not reverted.** The owner locked them ("do not re-plan"). The added
   conflict handling is correct, tested, and harmless; it is simply broader than the amended rule would
   now authorize.
2. **All eight registered nodes are retained.** Dropping any would reduce coverage and breach the
   OD-9 compliance conditions the reviewer checks.
3. **The rule binds prospectively.** From commit 6 onward, adding conflict handling to an A2 or A3 leaf
   is a **review rejection**. Commits 9–13 must show `git diff --stat -- app/` **empty**.

This is reported because the owner's ruling said the eight were "**likely** A1", and a planner that
silently agreed would be asserting a fact it had not checked.

---

## 0. What this slice is / is not

**Is:** (a) reproduce and **retain** the six captured first-write `23505` signatures as RED, (b) fix
each of the six writers so that under real two-session contention the caller receives **the winner or
a named domain result — never a raw `IntegrityError`**, (c) publish a **deduplicated writer-leaf
inventory** over the 122 audit candidates, and (d) land a **complete, retained tiered barrier suite**
in which every one of the 122 candidates is bound to **one or more write leaves, and every one of
those leaves carries exactly one tiered barrier**, in batches, inside this slice.

**"Tiered", not "two-writer" (Sol v2 defect 3).** Only **Tier A** barriers execute two concurrent
writers. Tier B1 and Tier B2 are catalog proofs that the unique-violation conflict class is absent for
a table. Calling the whole suite a "two-writer barrier suite" overstates two thirds of it, so the suite
is named **tiered** everywhere and the two-writer harness is described as **Tier A's instrument**. Each
barrier's strength is always stated by its tier.

**Is not**, and must not drift into:

| Not this slice | Owner disposition |
|---|---|
| F-008 Slice-55 owned-resume calls the cost evaluator before stopping | Wave 2, Slice 71 (next after this) |
| F-002 approval/override authority is bypassable | Wave 3, Slice 65 |
| F-003 runtime role can set another tenant's GUC | Slice 66 |
| F-004 `approval_events` / `tool_calls` / `agent_tool_allowlist` accept owner UPDATE/DELETE/TRUNCATE | **parked/unassigned — do not expand into it** (audit `:728`, `:1124-1128`) |
| F-005 runtime role self-stamps trusted source graphs | Slice 68 |
| F-017 full-repository pyright (`3050` errors) | Slice 80 |
| F-019 `audit_logs` lacks FORCE RLS + `tenant_isolation` | Slice 82 |
| F-022 cross-project learning truth tiers | Slice 85 |

No new table, column, migration, trigger, grant, CHECK, HTTP route, LLM call, or broker change. No
`SERIALIZABLE` retry loop is added to any writer that does not already own one.

### 0.1 Grounding facts (established on `72ee544` while writing this plan)

1. **Pre-fix census reproduced verbatim.** The Appendix-B scanner (`.planning/FINAL-AUDIT-REPORT.md:1681-1779`)
   was re-run unmodified on `72ee544` and printed exactly:

   ```text
   DIRECT_WRITER_ENDPOINTS=119
   PRIVATE_DIRECT=40
   PUBLIC_DIRECT=79
   MECHANISMS=orm_add:107,orm_add+pg_insert:1,pg_insert:9,raw_insert:2
   INDIRECT_SQL_WRAPPER_ENDPOINTS=3
   CANDIDATE_WRITER_ENDPOINT_TOTAL=122
   ```

   `119 + 3 = 122`. This `MECHANISMS` mix is the **pre-fix `72ee544` baseline only**; commit 4 changes
   several writers from `orm_add` to `pg_insert`, so commit 5 must record the scanner's real
   **post-fix** mechanism mix rather than asserting equality with `orm_add:107`. The endpoint total
   remains locked at 122. Retained reproducible audit pair coverage is **1/122**
   (`admin_write_autonomy_policy`, `tests/test_admin_policy_race_db.py`); **107/122** untouched
   (audit `:1253-1255`).
2. **The six unique constraints, named and located.**
   `uq_budgets_tenant_id_project_id` — `migrations/versions/0008_cost_ledger.py:68`, columns
   `(tenant_id, project_id)`;
   `uq_agent_blueprints_key` — `0007_agent_registry.py:54`, column `(key)`;
   `uq_agent_versions_blueprint_id_version_label` — `0007:82-86`, columns
   `(blueprint_id, version_label)`;
   `uq_tca_tenant_project_listing` — `0060_ecosystem_catalog.py:199`, columns
   `(tenant_id, project_id, listing_id)`;
   `uq_cfpv_project_digest` — `0050_cost_forecasts.py:131`, columns
   `(tenant_id, project_id, policy_digest)`;
   `uq_intake_artifacts_ref` — `0014_intake_spine.py:112`, columns
   `(tenant_id, project_id, kind, ref)`.
3. **`agent_versions` carries TWO collidable unique keys, not one.** `0007:82-86` is
   `(blueprint_id, version_label)` and `0007:87` is `uq_agent_versions_content_hash` on
   `(content_hash)`. `register_version`'s idempotency read is on `content_hash`
   (`app/agents/registry.py:162-166`), so identical content collides on **either** index and
   PostgreSQL reports whichever it reaches first — which is why the audit captured
   `uq_agent_versions_blueprint_id_version_label` for what may have been an identical-content race.
   The fix must therefore handle **both** keys and must distinguish them (OD-3): identical content is
   idempotent, a same-`(blueprint, label)` pair with **different** content is a §22.2 identity
   conflict.
4. **Runtime grants decide which conflict clause is even legal.** Live `has_table_privilege` on
   `app_test` @ `0062`:

   ```text
   agent_blueprints              | SELECT=t INSERT=f UPDATE=f
   agent_versions                | SELECT=t INSERT=f UPDATE=f
   budgets                       | SELECT=t INSERT=t UPDATE=t
   cost_forecast_policy_versions | SELECT=t INSERT=t UPDATE=f
   extraction_promotions         | SELECT=t INSERT=t UPDATE=f
   intake_artifacts              | SELECT=t INSERT=t UPDATE=f
   tenant_catalog_adoptions      | SELECT=t INSERT=t UPDATE=f
   ```

   Consequences, binding: `ON CONFLICT DO UPDATE` is legal **only** on `budgets`; the other four
   tenant tables permit `ON CONFLICT DO NOTHING` only; the two `agent_*` global tables are
   **admin-path** writers, so their RED/GREEN pairs must use two **admin** sessions and must carry
   the §4.7 caveat that this proves the writer's handling, not a fresh `uaid_app` privilege boundary.
5. **The in-repo conflict-handling precedent already exists and is the locked pattern.**
   `app/repositories/release_issues.py:98-110` — `async with self.session.begin_nested(): add; flush`
   / `except IntegrityError:` / re-select the winner by its natural key / `_require_material_match` /
   return the winner. `app/repositories/go_live_decisions.py:446-465` shows the sibling savepoint
   idiom translating a refusal into a named repository error while re-raising retryable `40001`.
   `app/repositories/ops_signals.py:154-189` with caller `:256-268` and
   `app/repositories/export_bundles.py:209-249` show the `pg_insert(...).on_conflict_do_nothing(...)
   .returning(id)` → `None`-means-loser idiom. Nothing new is being invented.
6. **The retained-pair reference harness.** `tests/test_admin_policy_race_db.py` is the shape to
   follow: two independent `rls_engine.connect()` transactions plus an `admin_engine` observer,
   `write_wait_snapshot` to prove the second writer is genuinely **blocked at the write** before the
   first commits, `pending_before_commit is True`, and a mutation test that reinstalls the racy body
   and shows the corrupted outcome. Helpers live in `tests/admin_lock_support.py` and
   `tests/admin_support.py` (`pg_state` at `:252`).
7. **Absent-read barrier is mandatory.** The audit's own note on two of the six —
   "Barrier after both absent reads made the race load-bearing" (`:1262`, `:1267`) — is the reason a
   single-session pre-seeded test is **not** a substitute: if the conflicting row is already visible,
   the writer takes its idempotent early-return path and the conflict handler is never entered. Every
   Tier-A probe must force both writers past their pre-read while the row is still absent.
8. **Live collidability catalog on `app_test` @ `0062`.** `144` tables in `public`. `116` tables carry
   at least one non-primary unique index (`199` such indexes). Excluding unique indexes whose column
   set is a **superset of the primary key** — the `UNIQUE (id, project_id, tenant_id)` composite-FK
   targets, which can never collide because `id` defaults to `gen_random_uuid()` — leaves **120
   collidable unique indexes across 88 distinct tables**. That reduction, not prose, is what makes the
   122-candidate sweep finite; the exact query is locked verbatim in OD-8.
9. **Static target resolution is impossible; the mapping must be hand-authored.** Extending the
   census scanner to also capture the inserted class shows `ENDPOINTS=119 RESOLVED=13 MANUAL=106`:
   106 of 119 endpoints insert a **local variable** (`self.session.add(row)`), so no AST pass can
   name their target table. The deduplicated writer-leaf inventory is therefore a hand-authored,
   review-verified constant whose *keys* are machine-checked against the scanner and whose *values*
   are machine-checked against the live catalog (OD-7). This limitation is named, not hidden.
10. **Existing conforming barriers to register, not rewrite.** `tests/test_ops_signals_db.py:286-294`,
    `tests/test_ops_stabilization_db.py:288-307`, `tests/test_export_bundle_db.py:340-357`, and
    `tests/test_admin_policy_race_db.py:141-192` already exist (audit `:1290`, `:1314`).
11. **`extraction_promotions` promote-once key.** `uq_extraction_promotions_proposal` on
    `(tenant_id, extraction_proposal_id)` — `app/models/extraction_promotion.py:53-55`. So
    `promote_proposal` has **two** conflict axes: the artifact's `uq_intake_artifacts_ref` raised
    inside `IntakeRepository.add_artifact`, and this promote-once key. Both must be handled by one
    savepoint (OD-4).
12. **Domain-error bases that already exist, plus one shared concurrency exception.** `RegistryError`
    (`app/agents/registry.py:57`), `CostError` (`app/cost.py:31`), `CostForecastRepositoryError`
    (`app/repositories/cost_forecasts.py:55`), `CatalogAdoptionError`
    (`app/repositories/catalog_adoptions.py:21`). `app/repositories/extraction.py` raises bare
    `ValueError`/`LookupError` and gets one new named subclass (OD-4). Separately, this slice adds
    exactly **one** cross-cutting class: `class ConcurrentWriteUnresolved(Exception)` in
    `app/concurrency.py` (OD-5). It is **not** rooted in `RegistryError`, `CatalogAdoptionError`,
    `CostForecastRepositoryError`, or `ValueError`, and there are no per-writer subclasses. A caller
    that catches only one of those domain roots will not catch `ConcurrentWriteUnresolved` unless it
    adds that shared class explicitly; that caller-visible consequence is intentional and is proven
    by GREEN tests that name the exact class.
13. **The `1/122` baseline is narrower than "the repository has one race test" — do not mis-state it.**
    The audit's figure is *retained reproducible **audit-specific** pair coverage*
    (`:1254`), i.e. coverage produced by the audit's own mapped actions. Independently of that,
    `72ee544` already contains concurrency tests the audit did not map — notably
    `tests/test_ecosystem_catalog_races.py` (205 lines; two-connection ordering probes over
    `record_contract_test` and the vetting-vs-child sequence at `:42,:85,:138,:151,:171,:187`), which
    covers catalog **vetting/scope** endpoints and **not** `CatalogAdoptionRepository.adopt`. A raw
    count of `engine.connect()` across `tests/` returns 74 files, but the large majority are
    single-connection grant/RLS probes, not concurrent writers. The builder must therefore **survey**
    the real pre-existing concurrent-writer set and **register** what qualifies rather than
    duplicating it (OD-13), and must never write or repeat the claim that only one race test existed.
14. **CI's pyright gate already covers one of the six files.** `.github/workflows/ci.yml:61-62`
    typechecks a fixed Slice 55–63 path list that includes `app/repositories/catalog_adoptions.py`,
    `app/repositories/go_live_decisions.py`, `app/repositories/ops_signals.py`,
    `app/repositories/export_bundles.py`, and `app/runtime/checkpointer.py`. So the OD-2 row-4 change
    is a **CI-gated** file: it must be pyright-clean or CI fails. The other five owned production
    files are outside that list and are covered only by the local run in §5 — that asymmetry is
    F-017 / Slice 80, and the workflow must not be edited to paper over it.
15. **Test-file sizes on `72ee544`.** The largest are `tests/test_control_loop.py` (1613),
    `test_test_oracles.py` (1418), `test_pr_evidence.py` (1312). The house 500-line cap is already
    widely violated **in files this slice does not touch**; every file this slice **creates** must
    stay ≤ 500 lines (OD-9). Support-module convention is `tests/<area>_support.py`.
16. **`indkey` is the wrong attribute list; `indnkeyatts` is the right one (Sol v1 defect 3, verified).**
    `pg_index.indkey` includes an index's `INCLUDE` (non-key) columns, so a query that compares the
    **whole** `indkey` against the primary key's columns silently treats
    `UNIQUE (code) INCLUDE (id)` as a primary-key superset and drops it. Both queries were run live on
    `app_test` @ `0062`:

    ```text
    corrected (indnkeyatts-bounded), full schema : ROWS=120  TABLES=88
    corrected, agent_versions                   : uq_agent_versions_blueprint_id_version_label
                                                  uq_agent_versions_content_hash
    mutation  CREATE TABLE s83_mut_probe (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL);
              CREATE UNIQUE INDEX … ON s83_mut_probe (code) INCLUDE (id);
      v1 query (whole indkey)  → 0 rows for s83_mut_probe   ← the defect
      v2 query (indnkeyatts)   → 1 row  for s83_mut_probe   ← detected
    ```

    So the corrected query reproduces the same `120` / `88` totals on the current schema — no census
    number moves — **and** closes the false-negative. The probe table was dropped. The corrected form
    is locked verbatim in OD-8 and Sol's mutation is retained as P-MUT-11.
17. **`session.get()` after an upsert returns the stale identity-mapped row (Sol v1 defect 1, confirmed
    by inspection).** `BudgetRepository.upsert` calls `self.get(project_id)`
    (`app/repositories/cost.py:199`) **before** writing, which puts the pre-existing `Budget` in the
    session's identity map. `session.get(Budget, id)` is an identity-map hit and returns that stale
    instance without re-reading — hence Sol's `same_identity=True`, `returned_caps=1,1`,
    `stored_caps=2,2`. The fix is a re-select carrying `execution_options(populate_existing=True)`,
    which overwrites the mapped attributes from the row. Separately, `TimestampMixin.updated_at`
    (`app/models/base.py:33-38`) uses Core `onupdate=func.now()`, which fires for an ORM/Core
    **UPDATE** statement and **not** inside an `INSERT … ON CONFLICT DO UPDATE` `set_` clause, so
    today's `updated_at` bump would be silently lost unless `set_` sets it explicitly. `created_at`
    must stay out of `set_`.
18. **Production-file sizes on `72ee544`, measured.** `wc -l`: `app/repositories/cost.py` **250**,
    `app/agents/registry.py` **249**, `app/repositories/catalog_adoptions.py` **107**,
    `app/repositories/cost_forecasts.py` **858**, `app/repositories/extraction.py` **491**. Sol quoted
    `859` / `492`; the difference is one line and does not touch the defect — `cost_forecasts.py`
    already violates the house 500-line cap, and `extraction.py` crosses it the moment the OD-4
    savepoint lands. The public symbols that must survive any split, because they are imported
    elsewhere, are: `CostForecastRepository`
    (`app/repositories/production_autonomy.py:65`, `app/repositories/ops_stabilization.py:61`),
    `CostForecastRepositoryError` and `ReportedModelPlan` and `CostForecastCoverage`
    (`tests/test_cost_forecasts.py`, `tests/test_cost_optimizer_*.py`), and `ExtractionRepository`
    (`tests/test_extraction.py:34`, `tests/test_extraction_promotion.py:22`). `_subject_ref` and
    `_PROMOTE_ASSUMPTION_ACTION` are referenced only from the promotion methods
    (`app/repositories/extraction.py:274-391`), so they move with them cleanly. Splits are locked in
    §1a-split / OD-9.
19. **`now()` is frozen for the whole transaction, so a same-transaction `updated_at` assertion is
    unprovable (Sol v2 defect 1, verified live).** Run on `app_test` @ `0062`:

    ```text
    BEGIN;
      SELECT now();                                   -> 2026-08-24 20:55:56.735804+00
      SELECT pg_sleep(0.05);
      SELECT now(), clock_timestamp() <> now(), statement_timestamp() = now();
                                                      -> 2026-08-24 20:55:56.735804+00 | t | t
    COMMIT;
    ```

    `now()` is `transaction_timestamp()`. Two `upsert` calls inside **one** transaction therefore
    write the **identical** `updated_at`, and v2's "`updated_at` strictly advanced" assertion could
    never pass — the defect is in the probe, not in the fix. Two consequences, both binding: any
    `updated_at`-advanced assertion needs **two committed transactions**, and `clock_timestamp()` is
    **not** substituted into `set_` to dodge this (the repository's convention is `func.now()`, the
    conflict path must match the ORM `UPDATE` path it replaces, and changing the time source would be
    an unrequested semantic change). The committing-session convention already exists in this
    repository — `AsyncSession(engine, expire_on_commit=False)` against `rls_engine` / `admin_engine`
    with real commits and a freshly seeded unique tenant per test, as in
    `tests/test_admin_policy_race_db.py:96-99` and `tests/test_agents.py:148` — and it is what
    P-GREEN-1b uses. The shared `db_session` fixture (`tests/conftest.py:125-154`) wraps each test in
    an outer transaction that is rolled back, so it **cannot** be used for a two-commit probe.
20. **A naive Tier-B2 foreign-key assertion is satisfiable by a column that serializes nothing (Sol
    v2 defect 3, verified live).** A `pg_constraint` query asking only "is the declared
    `parent_fk_column` part of some FK whose columns intersect this unique index" returns matches on
    `tenant_id` and `project_id` for nearly every child table — and both writers in a race share the
    same tenant and project, so such a column serializes nothing at all. Restricting to non-scoping
    columns whose referenced parent attribute is a **server-generated primary key** yields the
    intended shape, e.g. `acceptance_criterion_authorship_records.uq_acar_criterion_sequence` →
    `acceptance_criterion_id` → `intake_artifacts.id` (`gen_random_uuid()` default, primary key). The
    same query also exposes the opposite trap: `agent_provided_skills.uq_aps_capability_skill` matches
    **two** qualifying FKs, `capability_id → agent_skill_capabilities.id` and `skill_id → skills.id`,
    and `skills` is **migration-seeded**, not minted per call — so a catalog-only rule would accept
    `skill_id` as the serializing parent and be wrong. "The parent row is created in this transaction"
    is a **code** fact the catalog cannot prove; OD-8 therefore requires both the catalog assertions
    and an exact writer-line citation, and fails closed to Tier A.
21. **`app.current_tenant` is transaction-local and is cleared by commit (Sol v3 defect 1, verified
    live).** `app/tenancy.py:47-55` explains that RLS reads a transaction-local
    `set_config(..., true)` and denies by default when it is unset. The established test pattern
    re-binds inside each new transaction (`tests/slice84_support.py:303-310`;
    `tests/test_release_issues.py:446-452`). The v4 probe on `app_test` @ `0062` printed:

    ```text
    BEGIN;
    SELECT set_config('app.current_tenant',
                      '00000000-0000-0000-0000-000000000001', true);
      -> 00000000-0000-0000-0000-000000000001
    COMMIT;
    SELECT COALESCE(NULLIF(current_setting('app.current_tenant', true), ''), '<unset>');
      -> <unset>
    ```

    Therefore P-GREEN-1b must execute the transaction-local `SELECT set_config(...)` separately in
    txn 1, txn 2, and the independent confirming-read transaction. A single bind before txn 1 cannot
    authorize txn 2, and a confirming session without its own bind cannot prove the stored value.
    `set_config(..., false)` is rejected because it changes the test to session-level state and stops
    exercising the runtime transaction invariant.

**Grounding facts added while writing v6 (measured on `1aa7225`, head `0062`, database `app_test`).**

22. **The OD-8 query still returns 120 rows over 88 tables, and the column list was extracted.** The
    locked `indnkeyatts`-bounded query was re-run with an added
    `string_agg(a.attname, ',' ORDER BY x.ord)` projection and `pg_get_expr(indpred, indrelid)`; it
    returned **120** rows, and all 120 `(table, index, key columns, partial predicate)` tuples are
    quoted per leaf in `.planning/SLICE-83-LEAF-EVIDENCE.md`. Eleven of the 120 are partial:
    `agent_instances.uq_agent_instances_live_key`, `catalog_listings.uq_cl_live_asset`,
    `control_loop_events.uq_cle_loop_root`, `cost_events.uq_cost_events_idempotency`,
    `emergency_stop_events.uq_ese_project_root`, `go_live_decisions.uq_gld_project_root`, both
    `release_findings` fingerprints, `release_issues.uq_release_issues_source_finding`, and both
    `test_results` axes. The predicates matter: `uq_cle_loop_root`, `uq_ese_project_root`, and
    `uq_gld_project_root` are all `WHERE previous_* IS NULL`, which is what makes them **first-write
    root** keys of a derived chain rather than ordinary create-once keys.
23. **`audit_append` already serializes its own predecessor read.**
    `migrations/versions/0003_audit_log.py:140` is `PERFORM pg_advisory_xact_lock(421)`, placed
    **before** `nextval` at `:141` and the `SELECT a.entry_hash INTO v_prev` at `:142-143`. So both
    `audit_logs` leaves are A1 by derivation and already meet the A1 GREEN contract by construction;
    their barrier proves the loser blocks and `audit_verify()` still passes.
24. **`slice55_finalize_decision` already serializes on the project row.**
    `migrations/versions/0054_control_loop_decisions.py:650` is
    `PERFORM 1 FROM public.projects WHERE id=e.project_id AND tenant_id=e.tenant_id FOR UPDATE`,
    **before** the predecessor read at `:706-708` and the derived `new_seq` / `new_hash` at `:709-713`.
    A duplicate finalization of the same evaluation is already translated at
    `app/repositories/go_live_decisions.py:456-465` into
    `GoLiveDecisionRepositoryError("decision_finalization_refused")`. All four `go_live_decisions`
    leaves therefore need **no** production change.
25. **Four derived reads are genuinely unserialized, and that is the whole A1 production surface.**
    `app/repositories/go_live_decisions.py:299-310` carries `.with_for_update()` on the **head event**,
    which locks nothing when no prior event exists, so the first-write race is open;
    `app/repositories/acceptance_verification.py:42-59` has **no** `FOR UPDATE` and no project lock;
    `app/repositories/emergency_controls.py:437` reads the stop-event head inside `append_binding`,
    which — unlike `activate` (`:500`) and `clear` (`:570`) — does **not** call `lock_project_row`; and
    `app/release/production_approval_service.py:248` / `:336` read the lifecycle head with no lock of
    any kind (`rg -n "lock_project_row" app/release/production_approval_service.py` returns nothing).
26. **`lock_project_row` already exists in-repo and is the established idiom.**
    `app/repositories/emergency_controls.py:79`, used at `:118`, `:500`, `:570` and from
    `app/repositories/ops_stabilization.py:162`. The A1 fixes reuse this pattern rather than inventing a
    mechanism. ~~Three of the four take a **local** `FOR UPDATE` re-select of a parent row the writer
    already resolves, so no cross-module import is created.~~ **Superseded by v7 (Sol defect 2):** the
    three child-row targets are not `FOR UPDATE`-able by `uaid_app` (§0.1.30), so **all four** call the
    shared `lock_project_row`, and three of them **do** add one import of it — the same import
    `ops_stabilization.py:62` and `emergency_control_service.py:16` already make (§0.1.32).
27. **An `ordinal`/`seq` is only a derivation when it counts committed rows.** Verified by inspection
    across all 17 `ordinal`/`seq` axes in the catalog: `control_loop_events.uq_cle_run_ordinal` derives
    from the head read at `app/repositories/go_live_decisions.py:299-310` (A1), while the other 16 —
    for example `app/repositories/cost_forecast_persistence.py:137`/`:165` (`ordinal = 1`, `ordinal +=
    1`) and `app/repositories/production_preapprovals.py:275` (`enumerate(...)`) — are **in-call
    positional counters** scoped to a parent minted in the same call. This single distinction is the
    largest lever on the A1 count, so it is stated in §0A.2 and cited on every affected row of the
    evidence file rather than asserted.
28. **Production-file sizes on `1aa7225`, measured.** `wc -l`:
    `app/repositories/acceptance_verification.py` **456**, `app/repositories/emergency_controls.py`
    **790**, `app/repositories/go_live_decisions.py` **627**,
    `app/release/production_approval_service.py` **383**,
    `app/repositories/production_preapprovals.py` **704**, `app/audit.py` **58**,
    `app/repositories/admin.py` **121**, `app/repositories/cost.py` **266**, `app/concurrency.py`
    **64**, `app/admin/policy_sql.py` **226**. Two of the four A1 targets are already over the house
    cap **before** this slice touches them; see §0A.5 for the locked decision and its named limitation.

**v7 grounding facts — measured while accepting Sol's three v6 defects (2026-08-25).**

29. **Every upsert path in the repository, enumerated — the audit v6 cut short (Sol defect 1).**
    `rg -n "on_conflict_do_update" app/` returns **exactly two** sites:
    `app/repositories/cost.py:210` (→ `budgets`, A1 row 18) and
    **`app/runtime/checkpointer.py:152`** (→ `run_checkpoint_writes`, A1 row **21**). The live body at
    `app/runtime/checkpointer.py:152-167` is
    `.on_conflict_do_update(index_elements=["tenant_id","thread_id","checkpoint_ns","checkpoint_id","task_id","idx"], set_={"channel": channel, "type": type_, "blob": blob, "task_path": task_path})`,
    and all four `set_` values are the loop's own arguments (`:133-135`, `:127`) — **no `SELECT` precedes
    the write**. `rg -in "ON CONFLICT.*DO UPDATE" app/` returns **exactly one** raw-SQL site,
    `app/admin/policy_sql.py:91`, which lives in `_RACY_UPSERT_AND_SPEND` (`:84-98`) and is emitted
    **only** when `racy_first_write=True` (`:179`) — the deliberately racy **mutation-probe** variant.
    The installed `autonomy_policies` path is `_SERIALIZE_AND_SPEND` (`:129`): `DO NOTHING` (`:107`),
    locked `FOR UPDATE` re-read (`:110-114`), `UPDATE … RETURNING` (`:122-127`). The same query over
    `migrations/` returns **zero**. **Consequence: every upsert path maps to an A1 leaf; none remains in
    A2 or A3.** By Sol's own note, `aput` at `app/runtime/checkpointer.py:109` is
    `on_conflict_do_nothing`, so `run_checkpoints.uq_run_checkpoints_id` correctly **stays A2**.
30. **`uaid_app` cannot `FOR UPDATE` the three lock targets v6 planned; it can `FOR UPDATE` `projects`
    (Sol defect 2).** Run live as `uaid_app` on `app_test` in one `DO` block with per-statement
    `EXCEPTION WHEN insufficient_privilege`:
    `intake_artifacts: 42501 permission denied for table intake_artifacts`;
    `control_loop_runs: 42501 permission denied for table control_loop_runs`;
    `production_preapproval_attestations: 42501 permission denied for table production_preapproval_attestations`;
    `projects: OK (no 42501)`; `run_checkpoint_writes: OK (no 42501)`. Confirmed against
    `information_schema.role_table_grants` for `grantee='uaid_app'`: `projects` →
    `DELETE,INSERT,SELECT,UPDATE`; `run_checkpoint_writes` → `DELETE,INSERT,SELECT,UPDATE`
    (`migrations/versions/0009_workflow_runtime.py:214`); `intake_artifacts`, `control_loop_runs`,
    `production_preapproval_attestations`, `acceptance_criterion_authorship_records`,
    `control_loop_events`, `production_preapproval_lifecycle_events`,
    `emergency_rollback_authorizations` → **`INSERT,SELECT`** only; `run_checkpoints` →
    `DELETE,INSERT,SELECT`; `go_live_decisions` → `SELECT` only. **Every lock this slice adds therefore
    targets `projects`, a table with `UPDATE` granted to `uaid_app`.**
31. **The existing `projects FOR UPDATE` precedents, and why the SECURITY DEFINER one is not a
    counter-example.** `migrations/versions/0054_control_loop_decisions.py:650` is
    `PERFORM 1 FROM public.projects WHERE id=e.project_id AND tenant_id=e.tenant_id FOR UPDATE;`, and
    `:651-653` additionally locks `autonomy_policies` — a table `uaid_app` may not even `UPDATE` after
    Slice 63. That is legal because `pg_proc.prosecdef` is **`t`** for `slice55_finalize_decision`,
    `audit_append`, and `admin_write_autonomy_policy` (queried live): they run as the function owner, not
    as `uaid_app`. The Python-side precedents that *do* run as `uaid_app` are
    `app/repositories/emergency_controls.py:79` `lock_project_row` (`select(Project) …
    .with_for_update()`), called at `:500`, `:570` and from `app/release/emergency_control_service.py:77`
    and `app/repositories/ops_stabilization.py:162`. **v7's four A1 locks join the second group.**
32. **`go_live_decisions.finalize_decision` coordinates, and the import-cycle check (Sol defects 2 and
    3).** From source: `:443` is a **blank line**; `:444` is
    `async def finalize_decision(self, evaluation_id: uuid.UUID) -> GoLiveDecision:`; `:445` is
    `await self.require_serializable()`; `:452` is
    `text("SELECT public.slice55_finalize_decision(:evaluation)")`; `:456-465` is the `DBAPIError`
    translation into `GoLiveDecisionRepositoryError`; the function ends at `:473`. The landed
    `CENSUS_SCANNER` wrapper constant says `app/repositories/go_live_decisions.py:443-472` and is kept
    byte-identical (§0A.7). Separately, importing
    `app.repositories.acceptance_verification`, `app.repositories.go_live_decisions`,
    `app.release.production_approval_service`, and `app.runtime.checkpointer` each alongside
    `app.repositories.emergency_controls` all succeed, and
    `from app.repositories.emergency_controls import lock_project_row` resolves with
    `__module__ == 'app.repositories.emergency_controls'` — **no import cycle blocks the v7 mechanism.**

### 0.2 Load-bearing claim (one sentence)

**v6 amendment to §0.2–§0.5.** The three paragraphs and two claim lists below were written for v5's
single Tier-A class. They remain accurate for **A1** leaves. For **A2** the phrase "no `IntegrityError`
and no SQLSTATE `23505` reaches the caller" is **replaced** by "the loser fails cleanly with no partial
state — an escaped `23505` is the correct observed behaviour"; for **A3** "exactly one row exists on the
contended unique key" is **replaced** by "both rows exist and are distinct". §0A.4 governs. Three claims
are added to §0.4 and four to §0.5 at the end of each list.


After this slice, each of the six named writers is proven by a retained two-session test — with an
absent-read barrier, a blocked-at-write observation, and a mutation probe that removes only the new
conflict handling and shows `23505` return — to hand its loser the winner or a named domain error,
and every one of the 122 audit candidates is bound to **one or more** deduplicated write leaves — each
leaf carrying exactly one tiered barrier — whose conflict class is derived from the live catalog, so
that a new writer, a dropped candidate, a newly added collidable unique key, or a candidate that omits
one of its own collidable axes fails the inventory test.

### 0.3 Honesty crux (verbatim, for `CLAUDE.md`)

*Slice 83 fixed six named first-write writers so that under real two-session contention each returns
the winner or raises a named domain error, and it published a code-owned deduplicated writer-leaf
inventory with a retained tiered barrier registered for every write leaf of every one of the 122 audit
candidates. It
added no migration: the Alembic head stays `0062`. What is now proven is narrow and exact: for those
six writers a concurrent first write no longer escapes to the caller as a SQLAlchemy `IntegrityError`
/ PostgreSQL `23505` — each proven by a retained two-session test that forces both writers past their
pre-read while the row is absent, observes the second writer blocked at the write before the first
commits, and is paired with a mutation probe that removes only the new conflict handling and shows the
`23505` return; and every candidate endpoint is bound to one or more write leaves — each carrying
exactly one tiered barrier — whose conflict class is derived from the live `pg_index` catalog, so a new
writer, a removed candidate, or a newly added collidable unique key fails the inventory test, and every
collidable unique index on every table a given candidate writes must appear among **that candidate's**
own leaves, so a multi-key writer cannot be represented by one axis. What is not proven is that UAID is
free of races. The suite is **tiered, not uniformly two-writer**: only Tier-A leaves are proven by
actually executing two concurrent writers, and only Tier A is what the two-writer harness covers. Tier
B1 proves from the catalog that a table carries no collidable unique key. Tier B2 proves from
`pg_index`, `pg_constraint`, and `pg_attrdef` that every collidable unique key on a child table
contains a foreign-key column — not a tenant or project scoping column — that references a
server-generated parent primary key, and that the parent's own leaf is Tier A; the remaining premise,
that the writer mints that parent row inside the same transaction, is **not catalog-provable** and rests
on a cited writer line plus review, which is why any leaf failing any catalog condition is reclassified
Tier A rather than argued. All three tiers prove only that the unique-violation conflict class is absent
or handled for that table; none of them proves the absence of lost update, write skew, phantom, or
logical latest-wins anomalies. `register_version` deliberately refuses instead of returning a row when a same
`(blueprint_id, version_label)` pair carries different content, because returning the other row would
be a §22.2 identity lie; identical content stays idempotent. Its ladder's last rung — neither the
content hash nor the label pair visible after the conflict — fails closed with
`ConcurrentWriteUnresolved`, and that rung is proven by fault injection, not by a real race, because
the tenant-scoped and global keys involved make it unreachable by construction on this schema.
`ConcurrentWriteUnresolved` is the single shared `Exception` subclass for an unresolvable concurrency
state across the four writer modules; it is deliberately outside their domain-error roots, so callers
must catch it explicitly.
`BudgetRepository.upsert` returns an instance re-populated from the stored row, so its caps are the
stored caps and not a stale identity-map value, and it stamps `updated_at` explicitly because Core
`onupdate` does not fire inside a conflict-update clause; that stamp is proven across **two committed
transactions**, since `now()` is frozen within one transaction and a same-transaction comparison could
prove nothing; each upsert transaction and the independent confirming-read transaction re-binds the
transaction-local tenant GUC before touching tenant-owned rows; and its audited pre-image is still
read before the write and is therefore an
observed-before-write value, not a serialized pre-image.
`promote_proposal` narrows its handler to SQLSTATE `23505` on two named constraints and re-raises
every other integrity error unchanged, so a foreign-key, CHECK, or NOT NULL failure is never relabelled
as a promotion conflict. Two oversized production modules — `app/repositories/cost_forecasts.py` and
`app/repositories/extraction.py` — were split to bring the files this slice modifies under the house
500-line cap; those splits are pure moves that re-export every previously importable symbol and change
no behaviour, and they are landed as separate commits from the conflict-handling change so the two are
reviewable apart. The two `agent_*` writers are admin-path and their pairs run as two admin sessions,
so they prove the writer's handling and not a fresh `uaid_app` privilege boundary. The endpoint-to-leaf
mapping is hand-authored because 106 of the 119 syntactic endpoints insert a local variable that no
static pass can resolve; its keys are machine-checked against the census scanner and its values
against the live catalog, but the mapping itself is review-verified, not machine-proven. Some
Tier-B2 evidence is additionally bound to each exact candidate→leaf edge; one candidate's citation
cannot satisfy another candidate sharing that leaf, and one missing edge forces the whole shared leaf
to Tier A.
Some
registered Tier-A barriers are pre-existing tests rather than new ones: the audit's `1/122` figure is
retained **audit-specific** pair coverage, not a claim that the repository held a single concurrency
test, and the PR reports the registered-pre-existing and newly-added counts separately.
Tier-A isolation is leaf-specific. READ COMMITTED remains the default; a leaf whose existing writer
requires SERIALIZABLE is tested at SERIALIZABLE and admits only `40001`/`40P01` as the raw retryable
loser outcome (or the owned wrapper's post-retry result). An aborted loser transaction is rolled back,
never committed, and no Tier-A leaf may leak `23505`.
`can_go_live_autonomously` remains the literal `False`, A5 remains `slice54.v1`, readiness remains
`slice20.v1`, and F-002, F-003, F-004, F-005, F-008, F-017, F-019, and F-022 are untouched.*

**§0.3 addendum — the honesty crux (verbatim, for `CLAUDE.md`; counts corrected in v7, propagated in v8).**

*Slice 83's 112 Tier-A write leaves are subdivided by consequence, not reduced: 21 are **derived-write**
(A1) — the writer reads committed state and writes a hash-chain value, a `previous_*` pointer, a
head-derived ordinal, an upsert branch, or a supersedes link, so a lost race would persist a wrong row
silently; 38 are **independent-insert** (A2) — a create-once key over caller-supplied columns, where a
lost race raises `23505` and persists nothing wrong; 53 are **append-only** (A3) — the unique key
contains an identifier minted inside the same call, so concurrent callers legitimately produce distinct
rows. Every one of the 112 keeps a retained two-session node with an absent-read barrier and a mutation
probe; what each node asserts differs by subtier, and an escaped `23505` on an A2 leaf is asserted as
the **correct** observed behaviour rather than defended against. Each classification is bound to
evidence — the unique index's key columns and partial predicate quoted from the live `pg_index` catalog,
plus either the exact `file:line` of the read and of the derived value (A1) or the exact write site with
no prior-state derivation (A2 / A3) — published in `.planning/SLICE-83-LEAF-EVIDENCE.md` and mirrored
into a code-owned `SUBTIER` map an inventory test checks against the plan. Only **four** production
modules change, and each changes the same way: it serializes that project's existing **`projects`** row
`FOR UPDATE` — through the existing helper `lock_project_row`
(`app/repositories/emergency_controls.py:79`) — before the derived read, so the loser blocks and
re-derives from committed state rather than colliding. `projects` is the target because the three
originally-planned child tables are SELECT/INSERT-only for `uaid_app` and raise SQLSTATE `42501`
(§0.1.30). **Three of the four modules newly import `lock_project_row`**
(`acceptance_verification.py`, `go_live_decisions.py`, `production_approval_service.py`);
`emergency_controls.py` already owns it. No migration, module, exception class, GRANT, or isolation
level is added; the Alembic head stays `0062`. What is **not** proven: that UAID is race-free; that any subtier covers a conflict
class other than unique violation — lost update, write skew, phantoms, and logical latest-wins anomalies
remain out of scope; that the four locks are the narrowest possible granularity; that the subtier
assignment itself is machine-derived, since only its citations are; that
`admin_policy_changes.uq_admin_policy_changes_action` returns a named domain error on a double-spend, as
its derived write sits inside a migration-frozen SECURITY DEFINER function and still surfaces a raw
SQLSTATE; or that `app/repositories/emergency_controls.py` and `app/repositories/go_live_decisions.py`
were brought under the house 500-line cap, as both were already over it and are not split.
`can_go_live_autonomously` remains the literal `False`, A5 remains `slice54.v1`, and readiness remains
`slice20.v1`.*

### 0.4 Allowed claims, verbatim

- "Under two concurrent sessions that both read the key as absent, each of the six named writers
  returns the winning row or raises a named domain error; no `IntegrityError` and no SQLSTATE `23505`
  reaches the caller, and exactly one row exists on the contended unique key afterwards."
- "Each of the six is paired with a mutation probe that removes only the new conflict handling and
  shows the identical two-session driver returning `IntegrityError` / `23505` on the named
  constraint."
- "All 122 Appendix-B candidate endpoints are enumerated in a code-owned inventory whose key set is
  asserted equal to the re-run census scanner's output; adding a writer, removing a candidate, or
  renaming an endpoint fails that test."
- "Every candidate endpoint declares one or more write leaves, every leaf carries exactly one tiered
  barrier, every declared leaf's table exists in the live catalog and is classified Tier A / B1 / B2 by
  the locked `indnkeyatts`-bounded `pg_index` query, and every Tier-A leaf has a registered,
  collectible two-session pytest node."
- "For **each candidate**, and for every table that candidate writes, the set of unique indexes named
  in that candidate's own leaves equals the set of collidable unique indexes the live catalog reports
  for that table — so a writer with two collidable keys carries two leaves, and dropping either one
  fails the inventory test even when another candidate still declares it."
- "Tier B2's foreign-key premise is asserted against `pg_constraint` and `pg_attrdef`: the declared
  parent column is a real foreign-key column, is not a tenant or project scoping column, references a
  server-generated parent primary key, appears in every collidable index on the child, and the
  parent's own leaf is Tier A. A leaf that fails any of these is classified Tier A instead."
- "`BudgetRepository.upsert` bumps `updated_at` across two committed transactions, proven with one
  session and an independent confirming read; all three runtime-role transactions bind
  `app.current_tenant` locally before touching tenant-owned rows."
- "The classification query counts only an index's key attributes (`indnkeyatts`), so a unique index
  with `INCLUDE` columns is still classified collidable; a retained mutation proves the whole-`indkey`
  form misses it."
- "`BudgetRepository.upsert` returns the stored row's caps — asserted both as the returned value and
  by an independent subsequent read in the same session — and bumps `updated_at` on the conflict
  path."
- "`promote_proposal` handles only SQLSTATE `23505` on `uq_intake_artifacts_ref` or
  `uq_extraction_promotions_proposal`; any other `IntegrityError` propagates to the caller unchanged,
  proven by a retained control."
- "The `cost_forecasts` and `extraction` splits are pure moves: every symbol importable before the
  split is importable from the same module path after it, and the moved bodies are unchanged."
- "`register_version` returns the existing row for identical content and raises
  `VersionLabelConflict` for a same `(blueprint_id, version_label)` pair with different content; it
  never returns a row whose component hashes differ from those requested."
- "`ConcurrentWriteUnresolved` is exactly one shared `Exception` subclass, not a writer-domain
  subclass; existing domain-root catchers do not catch it unless they name it explicitly."
- "Tier B1 proves, from `pg_index`, that the table carries no unique index outside the primary key or
  a primary-key superset, so two concurrent inserts cannot raise a unique violation on it."
- "Tier B2 proves, from `pg_index`, `pg_constraint`, and `pg_attrdef`, that every collidable unique
  index on the child table includes a non-scoping foreign-key column referencing a server-generated
  parent primary key whose parent leaf is itself Tier A — and states separately, as a cited and
  review-verified premise on **every candidate→leaf edge**, rather than a catalog proof, that that
  candidate creates the parent row in the same transaction, so two concurrent callers write children
  under distinct parents. If one candidate sharing the leaf lacks that evidence, the whole leaf is
  Tier A."
- "Tier-A isolation is declared per leaf. Existing SERIALIZABLE writers may hand the loser a
  retryable `40001`/`40P01` or the owned wrapper's post-retry result; an aborted loser is rolled back,
  and `23505` remains forbidden."

**Added in v6:**

- "Every one of the 112 Tier-A write leaves is classified into exactly one consequence subtier — **21**
  A1, **38** A2, **53** A3 — and every classification is bound to evidence: the unique index's key
  columns and partial predicate quoted from the live `pg_index` catalog, plus either the exact
  `file:line` of the read and of the derived value (A1) or the exact write site with no prior-state
  derivation (A2 / A3). The classification and its evidence are published in
  `.planning/SLICE-83-LEAF-EVIDENCE.md` and mirrored into a code-owned `SUBTIER` map that an inventory
  test asserts against the plan's A1 list."
- "Exactly four `app/` modules change for A1 — `acceptance_verification.py`, `emergency_controls.py`,
  `go_live_decisions.py`, `production_approval_service.py` — each by serializing that project's existing
  **`projects`** row `FOR UPDATE` through the existing helper `lock_project_row`
  (`app/repositories/emergency_controls.py:79`) **before** the derived read, so the loser blocks and
  re-derives from committed state. **Three of the four newly import `lock_project_row`**
  (`acceptance_verification.py`, `go_live_decisions.py`, `production_approval_service.py`);
  `emergency_controls.py` already owns it. No new module, exception class, GRANT, migration, or isolation
  level is added, and `git diff --stat -- app/` is empty for every A2 and A3 barrier commit."
- "For an A2 leaf the loser's `23505` is asserted as the **correct** observed outcome; for an A3 leaf
  both transactions commit and the two rows' minted parent identifiers are asserted to differ. Each
  barrier also asserts that the constraint it observed **is** the leaf's own declared unique index."

### 0.5 Refused claims, verbatim

- That UAID is free of races, or that a product-wide concurrency PASS is established. **Forbidden
  wording** — see §6.
- That Tier B1 or Tier B2 proves anything beyond the absence of the **unique-violation** conflict
  class. Lost update, write skew, phantom reads, and logical latest-wins anomalies are out of scope
  and are named limitations.
- That the endpoint-to-leaf mapping is machine-derived. It is hand-authored (§0.1.9).
- That the two `agent_*` pairs prove a runtime-role privilege boundary. They are admin-path
  (§0.1.4).
- That `BudgetRepository.upsert`'s audited `old_total` / `old_daily` are a serialized pre-image.
- That `register_version`'s `ConcurrentWriteUnresolved` rung was reached by a real race. It is
  fault-injected and labelled as such (OD-3, P-GREEN-3c).
- That splitting `cost_forecasts.py` / `extraction.py` improved, refactored, or hardened them. The
  splits are pure moves made solely to keep a modified file under the house cap; no logic changed.
- That the house 500-line cap now holds repository-wide. It holds only for the files this slice
  creates or modifies.
- That the barrier suite is a two-writer suite. Only **Tier A** executes two writers; the suite is
  **tiered** and each barrier's strength is stated by its tier (**forbidden wording** — see §6).
- That Tier B2 proves the parent row is minted in the same transaction. The catalog cannot prove that;
  it is a cited writer line plus review, and any leaf whose catalog conditions fail becomes Tier A.
- That every candidate maps to exactly one leaf or exactly one barrier. A candidate maps to **one or
  more** leaves; each **leaf** carries exactly one barrier.
- That `updated_at` was proven to advance within a single transaction. It cannot be — `now()` is
  frozen per transaction (§0.1.19); the proof spans two committed transactions.
- That one transaction-local tenant bind survives a commit, or that P-GREEN-1b may use
  `set_config(..., false)`. Each transaction binds independently with `set_config(..., true)`
  (§0.1.21).
- That one candidate's B2-5 citation covers another candidate sharing the same leaf. B2-5 is
  per candidate→leaf edge, and a missing edge forces the whole leaf to Tier A.
- That `ConcurrentWriteUnresolved` derives from any existing writer-domain base, or that four
  per-writer unresolved classes exist. It is exactly `ConcurrentWriteUnresolved(Exception)`.
- That every Tier-A loser must return an equal identity or domain error. Existing SERIALIZABLE
  writers may instead surface only the ruled retryable SQLSTATEs `40001`/`40P01`; `23505` is still
  forbidden.
- That any production guard, trigger, grant, CHECK, or migration was added. None was; head stays
  `0062`.
- That any A5 gate, readiness level, or go-live bit moved. None did.
- That the eight audit-reported conforming writers were trusted from the audit. They are re-proved
  here by retained tests; the audit's own drivers were never retained (`:1294`).
- That the repository contained only one concurrency test before this slice. It did not; the audit's
  `1/122` is retained **audit-specific** pair coverage, and unmapped concurrency tests already exist
  (§0.1.13, OD-13).
- That the pre-existing >500-line test files were brought under the house cap. They were not; this
  slice does not touch them.

**Added in v6:**

- That Tier A was reduced, redefined, or narrowed. It was **subdivided by consequence** on the owner's
  ruling and still holds **112** leaves, every one of which keeps a retained two-session node.
- That an A2 or A3 leaf received conflict handling, or that one needs it. Adding it is **forbidden** from
  commit 6 (§0A.1); a `23505` that corrupts nothing is not a defect.
- That the A1/A2/A3 assignment is machine-derived. The **citations** are machine-quoted from the live
  catalog and from source; the assignment is planner-authored and reviewer-verified (§0A.7).
- That commit 4's six fixes were all A1 work. On the amended standard only `budgets` was A1; the other
  five were A2 and are landed, not reverted, with the rule binding prospectively (§0A.8).
- That `admin_policy_changes`'s double-spend now returns a named domain error. It still surfaces a raw
  SQLSTATE; the derived write is inside a migration-frozen SECURITY DEFINER function (§0A.7).
- That `app/repositories/emergency_controls.py` or `app/repositories/go_live_decisions.py` was brought
  under the house 500-line cap. Neither was; both were already over it and are not split (§0A.5).
- That any of this makes UAID race-free. It does not, and the forbidden wording in §6 still applies.

---

## 1. Exact files to create / modify

### 1a. Production files — the ten landed at commits 1–4 (five modified, five created)

**Expanded by §1a-v7 below to fourteen**, adding exactly the four A1 writer modules that must change
(§0A.5). The ten rows in this subsection are **landed** and are not re-planned.

**Manifest corrected (Sol v2 defect 4).** v2's heading said "exactly six" and its closing line said
"no other `app/` file is touched", yet §1a-split creates four more modules. The complete, exhaustive
production manifest is:

| # | Path | Disposition |
|---|---|---|
| 1 | `app/repositories/cost.py` | modified — conflict handling |
| 2 | `app/agents/registry.py` | modified — conflict handling |
| 3 | `app/repositories/catalog_adoptions.py` | modified — conflict handling (**CI pyright-gated**, §0.1.14) |
| 4 | `app/repositories/cost_forecasts.py` | modified — split, then conflict handling |
| 5 | `app/repositories/extraction.py` | modified — split (its conflict handling lands in #10) |
| 6 | `app/concurrency.py` | **created** — shared conflict primitives |
| 7 | `app/repositories/cost_forecast_types.py` | **created** — §1a-split pure move |
| 8 | `app/repositories/cost_forecast_persistence.py` | **created** — §1a-split pure move |
| 9 | `app/repositories/cost_forecast_coverage.py` | **created** — §1a-split pure move |
| 10 | `app/repositories/extraction_promotion.py` | **created** — §1a-split pure move + the OD-4 change |

Five of the ten are pure-move or new-primitive modules that contain **no** conflict-handling logic of
their own except #10. Nothing outside this list may be touched.

| Path | Change | Lines after |
|---|---|---|
| `app/repositories/cost.py` | `BudgetRepository.upsert` (`:184-225`) → `pg_insert` + `on_conflict_do_update` on `uq_budgets_tenant_id_project_id`, `updated_at` in `set_`, then a `populate_existing=True` re-select (OD-2 row 1). | ~270 |
| `app/agents/registry.py` | `register_blueprint` (`:102-122`) → `on_conflict_do_nothing` + winner re-select. `register_version` (`:125-177`) → untargeted `on_conflict_do_nothing` + the OD-3 two-rung re-select ladder + new `VersionLabelConflict(RegistryError)` (OD-2 rows 2–3, OD-3). | ~290 |
| `app/repositories/catalog_adoptions.py` | `CatalogAdoptionRepository.adopt` (`:31-80`) → `on_conflict_do_nothing` on `uq_tca_tenant_project_listing` + winner re-select (OD-2 row 4). **CI-gated by pyright** (§0.1.14). | ~125 |
| `app/repositories/cost_forecasts.py` | **Split first (§1a-split), then** `record_policy_version` → `on_conflict_do_nothing` on `uq_cfpv_project_digest` + winner re-select (OD-2 row 5). | ≤ 400 |
| `app/repositories/extraction.py` | **Split first (§1a-split);** `promote_proposal` moves to the new promotion module and is changed there (OD-2 row 6, OD-4). | ≤ 340 |
| `app/concurrency.py` | **Create.** One shared module, ≤ 120 lines: exactly `class ConcurrentWriteUnresolved(Exception)` (OD-5), `unique_violation_constraint(exc) -> str \| None`, and `is_unique_violation(exc) -> bool` reading `sqlstate`/`pgcode` the way `app/repositories/go_live_decisions.py:55-77` already does. The class is not a domain-root subclass and has no per-writer subclasses. Google-style docstrings. No other module gains a private copy of this logic. | ≤ 120 |

### 1a-v7. The manifest expanded to exactly the A1 writer modules (owner ruling, §0A.5)

*(This section was `§1a-v6`; **v7 supersedes it in place** on Sol defect 2. Cross-references to
"§1a-v6" elsewhere in this plan mean this section.)*

The ten rows above are **landed** at commits 1–4 and stay in the manifest. This adds **exactly four**
more, derived from the A1 classification and nothing else. **Fourteen production paths total; no
fifteenth.** v7 changed the *mechanism* of rows 11, 13 and 14 — not the count.

| # | Path | Disposition (v7) | A1 leaves | Lines before → after |
|---|---|---|---|---|
| 11 | `app/repositories/acceptance_verification.py` | modified — `lock_project_row(self.session, self.context, project_id)` immediately before each `_current_record` call (`:84`, `:128`, `:167`); `project_id` is already a parameter of all three `record_*` methods. ~~lock the criterion's `intake_artifacts` row `FOR UPDATE`~~ (v6, **struck: `42501`**) | `uq_acar_criterion_sequence`, `uq_acar_supersedes_once` | 456 → ≤ 472 |
| 12 | `app/repositories/emergency_controls.py` | modified — call this module's own `lock_project_row` (`:79`) at the top of `append_binding` (`:337`), before the `:437` stop-event head read *(unchanged by v7 — already `projects`)* | `uq_ese_project_root` | 790 → ≤ 795 (**already over cap, not split — §0A.5**) |
| 13 | `app/repositories/go_live_decisions.py` | modified — `lock_project_row(..., cycle.project_id)` in `append_event` inserted **between `:298` and `:299`**, reusing the `cycle` that `_require_cycle` already resolved at `:298`; no `_lock_cycle` helper and no second read. ~~lock the parent `control_loop_runs` row `FOR UPDATE`~~ (v6, **struck: `42501`**) | `uq_cle_run_ordinal`, `uq_cle_previous`, `uq_cle_loop_root` | 627 → ≤ 640 (**already over cap, not split — §0A.5**) |
| 14 | `app/release/production_approval_service.py` | modified — `lock_project_row(..., project_id)` before the **first** read of each derive chain: before `:231` (`_supersede_prior`'s `prior` select, which precedes the `:248` head read) and before `:326` in `revoke`. ~~lock the `production_preapproval_attestations` row `FOR UPDATE`~~ (v6, **struck: `42501`**) | `uq_pple_previous`, `uq_pple_attestation_event`, `uq_pple_idempotency` | 383 → ≤ 400 |

**Not in the manifest, and why.** `app/audit.py`, `app/repositories/admin.py`, `app/repositories/cost.py`
(beyond commit 4), `app/repositories/production_preapprovals.py`, `app/admin/policy_sql.py`, **and — v7 —
`app/runtime/checkpointer.py`** each own or front an A1 leaf but require **no change**: three are already
serialized (advisory lock `421`, the SECURITY DEFINER `projects FOR UPDATE`, the Slice-63 v4.1 first-write
path), one is already fixed, one is migration-frozen (§0A.7), and **`checkpointer.py`'s
`ON CONFLICT DO UPDATE` (`:152-167`) is already atomic with no pre-read to go stale (§0A.3 row 21,
§0A.4)**. `app/repositories/production_preapprovals.py` holds the lifecycle **write** but the derived
**read** is in the service, so the lock belongs in row 14 — putting it in the repository would lock after
the read and prove nothing. **There is no fifteenth path and no fifth new module.**

**No new file.** No new module, no new exception class, no migration, no grant, no trigger, no
isolation-level change. `app/concurrency.py` is **not** extended. ~~No new import.~~ **v7:** rows 11, 13
and 14 each add exactly one import — `from app.repositories.emergency_controls import lock_project_row` —
of an existing helper already imported the same way by `ops_stabilization.py:62` and
`emergency_control_service.py:16`; no import cycle exists (§0.1.32).

**No `app/` file outside the fourteen-row manifest is touched.** No `migrations/`, no `scripts/`, no
`.github/`, no `Makefile`. `git diff --name-only` restricted to `app/` must list at most those fourteen
paths and nothing else (§5), and for commits **9–13** (the A2 and A3 barriers) it must list **nothing**.

### 1a-split. Mandatory pure-move splits (Sol v1 defect 6, locked)

Two of the five modified production files breach the house 500-line cap (§0.1.18): `cost_forecasts.py`
is already at **858**, and `extraction.py` at **491** crosses it the moment the OD-4 savepoint lands.
Both are split **before** any conflict-handling edit, as their own commits, so the move and the
behaviour change are reviewable apart.

**Split rules, binding for both.**

1. **Pure move.** A moved function or class body is **byte-identical** apart from import lines and the
   `self`-attribute declarations a mixin needs. No rename, no signature change, no logic change, no
   docstring rewrite.
2. **Public API preserved exactly.** Every symbol importable from the original module path before the
   split is importable from that same path after it, via an explicit re-export. Callers listed in
   §0.1.18 are **not** edited. `app/repositories/production_autonomy.py` and
   `app/repositories/ops_stabilization.py` keep their current import lines untouched — if either
   would have to change, the split is wrong.
3. **Mixins, not partial classes.** A class is never split across files. Where methods must move, they
   move into a private mixin the original class inherits, and the mixin declares the attributes it
   uses (`session: AsyncSession`, `context: TenantContext`) so pyright stays clean on the owned paths.
4. **Every new module ≤ 500 lines**, and the post-split original ≤ 500 lines **with the slice's new
   conflict-handling code already in it**. The builder quotes `wc -l` for every file before and after.
5. **Proof of no behaviour change.** The split commit must leave `make test` and `make test-db` at
   **exactly** the pre-split pass counts — not merely green, *identical* — and `git diff -M -C
   --stat` must show the moves as moves. A count that changes means the "pure move" claim is false and
   the builder stops and reports.

**`app/repositories/cost_forecasts.py` — 858 → four modules.**

| Module | Contents moved | Approx. |
|---|---|---|
| **Create** `app/repositories/cost_forecast_types.py` | `ReportedModelPlan` (`:60-68`), `CostForecastCoverage` (`:69-113`) incl. `gate_kwargs`, and the five private formatters `_storage_hash` / `_money` / `_percent` / `_utc_text` / `_route_hash` (`:114-135`). | ~100 |
| **Create** `app/repositories/cost_forecast_persistence.py` | `_CostForecastPersistenceMixin` with `_record_refusal` (`:425-496`) and `_persist_success` (`:497-738`). | ~340 |
| **Create** `app/repositories/cost_forecast_coverage.py` | `_CostForecastCoverageMixin` with `_latest_pack` (`:243-255`), `_events` (`:256-267`), `_event_line` (`:268-284`), and `coverage_for_project` (`:739-858`). | ~190 |
| **Keep** `app/repositories/cost_forecasts.py` | `CostForecastRepositoryError`; **re-exports** `ReportedModelPlan`, `CostForecastCoverage`; `class CostForecastRepository(_CostForecastPersistenceMixin, _CostForecastCoverageMixin)` holding `__init__`, `_latest_policy`, `record_policy_version` (**the OD-2 row-5 change**), `_policy_value`, and `generate_forecast`. | ≤ 400 |

**`app/repositories/extraction.py` — 491 → two modules.**

| Module | Contents moved | Approx. |
|---|---|---|
| **Create** `app/repositories/extraction_promotion.py` | `_PROMOTE_ASSUMPTION_ACTION` (`:55`), `_subject_ref` (`:63-65`), **`PromotionRefConflict(ValueError)`**, and `_ExtractionPromotionMixin` with `request_promotion_approval` (`:256-295`), `promote_proposal` (`:296-401`, **the OD-2 row-6 / OD-4 change lands here**), `promotion_for` (`:402-408`), `list_promotions` (`:409-417`). The error lives next to its only raising writer. Both helpers are referenced only by these methods (§0.1.18), so nothing else needs them. | ~230 |
| **Keep** `app/repositories/extraction.py` | `class ExtractionRepository(_ExtractionPromotionMixin, TenantScopedRepository)` holding `extract`, `review_proposal`, `list_proposals`, `_projected_exceeds_budget`, `_record_run`, `_get_proposal`; **re-export `PromotionRefConflict` from `app.repositories.extraction_promotion`** so `from app.repositories.extraction import PromotionRefConflict` remains the stable public path. The builder does not choose another home. | ≤ 340 |

Do **not** rename `app/repositories/extraction_promotion.py` to a plural or a `_ops` suffix; the name
is fixed here so the module the reviewer expects is the module that exists. There is already an
`app/models/extraction_promotion.py`; the repository module lives under `app/repositories/`, so the
paths do not collide, and the builder must import the model with its existing path.

### 1b. Test files — created only

| Path | Contents | Cap |
|---|---|---|
| **Create** `tests/slice83_support.py` | **Tier A's instrument** — the shared two-writer harness (the suite as a whole is tiered, §0): `run_two_writers(...)` (two independent connections, absent-read barrier, blocked-at-write observation reusing `write_wait_snapshot` from `tests/admin_lock_support.py`, ordered commit, structured result), `two_admin_writers(...)` for the admin-path pair, `unique_row_count(...)`, `assert_no_integrity_error(...)`, `assert_integrity_error_on(constraint)`, `patched_out_conflict_handling(...)` for the mutation probes, and `two_committed_transactions(...)`. That helper owns one `AsyncSession(engine, expire_on_commit=False)` for txn 1 and txn 2 plus an independent session for the confirming read; **inside each of the three transactions**, before any repository call/read, it executes `SELECT set_config('app.current_tenant', :t, true)`. It never uses `set_config(..., false)`. This is required both because `now()` is frozen per transaction (§0.1.19) and because the tenant GUC is cleared at commit (§0.1.21). Google-style docstrings, one responsibility per function. | ≤ 500 |
| **Create** `tests/writer_inventory.py` | The code-owned artifact (OD-7): `CENSUS_SCANNER` (the Appendix-B program verbatim), `CANDIDATE_ENDPOINTS` (122 entries), `WRITE_LEAVES`, `B2_EDGE_EVIDENCE`, `TIER_A_NODES`, `PENDING_TIER_A_BATCHES`. | ≤ 500 |
| **Create** `tests/test_slice83_inventory.py` | Batch 2 (OD-9 commit 5) — the **seven** inventory tests (§3.2), including test 5 **per-candidate** index-coverage completeness, test 6 the retained `INCLUDE`-column classification mutation, and test 7 the Tier-B2 `pg_constraint` mapping verification. | ≤ 500 |
| **Create** `tests/test_slice83_races_core.py` | Batch 1 — the six signatures: RED-retained GREEN + mutation pairs. | ≤ 500 |
| ~~`tests/test_slice83_races_intake.py`~~ | ~~Batch 3 — intake / documents / extraction / … leaves.~~ **SUPERSEDED by the v6 subtier modules below — not created.** | — |
| ~~`tests/test_slice83_races_release.py`~~ | ~~Batch 4 — release / evidence / preapproval / emergency / cost-forecast leaves.~~ **SUPERSEDED — not created.** | — |
| ~~`tests/test_slice83_races_agents.py`~~ | ~~Batch 5 — agents / skills / task contracts / reviewer QA / tools leaves.~~ **SUPERSEDED — not created.** | — |
| ~~`tests/test_slice83_races_platform.py`~~ | ~~Batch 6 — tenancy / runs / checkpointer / audit / ops / catalog / admin leaves.~~ **SUPERSEDED — not created**; `audit_append` and `slice55_finalize_decision` move to `tests/test_slice83_a1_ledger.py`. | — |

**v6 addition — the subtier files.** Commits 6–14 add these and nothing else under `tests/`:

| Path | Contents | Cap |
|---|---|---|
| **Create** `tests/writer_inventory_c.py` | `SUBTIER: Mapping[str, str]` — one of `"A1"`/`"A2"`/`"A3"` for each of the 112 Tier-A leaves, mirrored **verbatim** from `.planning/SLICE-83-LEAF-EVIDENCE.md`, plus `A1_LEAF_IDS: frozenset[str]` holding the **21** ids of plan §0A.3. `tests/writer_inventory.py` re-exports both. Commit 6. | ≤ 500 |
| **Extend** `tests/test_slice83_inventory.py` | Inventory tests **8** and **9** (§0A.6 commit 6), and test 8's strengthening at commit 14. If it would breach the cap, overflow into `tests/test_slice83_inventory_b.py`. | ≤ 500 |
| **Create** `tests/test_slice83_a1_races.py` (+ `_b.py` as needed) | The A1 GREEN + mutation + only-wrong-axis nodes for the **9** module-owned leaves — the four §0A.5 modules' A1 leaves (commit 7). | ≤ 500 each |
| **Create** `tests/test_slice83_a1_ledger.py` | The A1 nodes for the **12** barrier-alone A1 leaves — already-serialized, migration-frozen, or atomic-upsert — (commit 8), **including `run_checkpoint_writes.uq_run_checkpoint_writes_id`** (v7: reclassified A2→A1, atomic `ON CONFLICT DO UPDATE`, no production change) and the `audit_verify()` chain assertion. | ≤ 500 |
| **Create** `tests/test_slice83_a2_races.py`, `…_a2_races_b.py` | A2 nodes for the **32** unregistered A2 leaves (commits 9–10) — v7: 32, not ~~33~~, since `run_checkpoint_writes` moved to A1. | ≤ 500 each |
| **Create** `tests/test_slice83_a3_races.py`, `…_b.py`, `…_c.py` | A3 nodes for the 53 A3 leaves (commits 11–13). | ≤ 500 each |

The v5 domain-batch modules (`…_races_intake.py`, `…_races_release.py`, `…_races_agents.py`,
`…_races_platform.py`) are **superseded by the subtier modules above** and are not created; §0A.6
organises the barrier work by consequence, not by domain, and creating both sets would duplicate nodes.
`tests/slice83_support.py` and `tests/test_slice83_races_core.py` are landed and unchanged.

**Overflow rule (locked):** if a batch module would exceed 500 lines, split it into
`<name>_b.py` (then `_c.py`) and register the new module in `tests/writer_inventory.py`. Never exceed
the cap; never merge two batches to dodge a split.

**Existing test files.** Preferably none change. If one of the six fixes breaks an existing
assertion, the builder may make a **mechanical adaptation or a tightening only** — never a weakening,
never a deletion, never an `xfail` — and must list every such edit with a before/after diff in the PR
body (OD-6). Existing conforming barriers named in §0.1.10 are **registered** in
`tests/writer_inventory.py`, not rewritten.

---

## 2. Open decisions — locked, Option A. The builder may not choose.

**OD-1 — does this slice need a migration?**
**Option A (locked): no.** All six fixes are Python-level (`ON CONFLICT` clauses the runtime role is
already privileged for per §0.1.4, plus one savepoint). Alembic head stays **`0062`** and
`uv run alembic heads` must print `0062 (head)` before and after. Rejected: adding advisory-lock
helper functions or a new unique index — both would change the schema to solve a problem the existing
indexes already detect.

**OD-2 — the fix mechanism per writer.** Binding table; the builder implements exactly this.

| # | Writer | Mechanism (locked) | Loser's result |
|---|---|---|---|
| 1 | `BudgetRepository.upsert` `app/repositories/cost.py:184` | See the locked snippet below. `UPDATE` is granted (§0.1.4). | The single surviving row, **re-populated from storage**, carrying **this** call's caps. |
| 2 | `register_blueprint` `app/agents/registry.py:102` | `pg_insert(AgentBlueprint).on_conflict_do_nothing(constraint="uq_agent_blueprints_key").returning(id)`; on `None`, re-select by `key`. | The existing blueprint — identical to today's `existing is not None` early return. |
| 3 | `register_version` `app/agents/registry.py:125` | `pg_insert(AgentVersion).on_conflict_do_nothing()` — **untargeted**, so it covers both unique indexes and still lets a bad `blueprint_id` raise a foreign-key error — `.returning(id)`; on `None`, walk the OD-3 ladder. | Winner for identical content; `VersionLabelConflict` for a differing-content label match; `ConcurrentWriteUnresolved` if neither key is visible (OD-3). |
| 4 | `CatalogAdoptionRepository.adopt` `app/repositories/catalog_adoptions.py:31` | `pg_insert(TenantCatalogAdoption).on_conflict_do_nothing(constraint="uq_tca_tenant_project_listing").returning(id)`; on `None`, re-select the triple and return it **without** writing an audit row — matching today's early return, which also skips the audit. | The existing adoption. |
| 5 | `record_policy_version` `app/repositories/cost_forecasts.py:153-228` | `pg_insert(CostForecastPolicyVersion).on_conflict_do_nothing(constraint="uq_cfpv_project_digest").returning(id)`; on `None`, re-select by `(tenant, project, policy_digest)`; return it, skipping the audit. | The existing policy version. |
| 6 | `promote_proposal`, after §1a-split in `app/repositories/extraction_promotion.py` | One `async with self.session.begin_nested():` wrapping **both** the `intake.add_artifact(...)` call and the `ExtractionPromotion` insert + flush; then the OD-4 **narrowed** handler — SQLSTATE `23505` on one of two named constraints only, everything else re-raised. | Winner's artifact, a named refusal, or the original error unchanged (OD-4). |

`DO UPDATE` is used **only** on row 1 because it is the only one of the six with a live `UPDATE`
grant and the only one whose contract is genuinely an upsert. Rejected everywhere else: it would fail
with `permission denied` (§0.1.4) and would silently overwrite a winner's row.

**OD-2 row 1, locked in full (Sol v1 defect 1).** v1 said `.returning(Budget.id)` then
`session.get(Budget, id)`. That is **wrong** and Sol's probe proved it: `upsert` reads the row first
(`app/repositories/cost.py:199`), so the instance is already in the identity map and `session.get` is
a map hit that returns the *stale* object — `same_identity=True`, `returned_caps=1,1`,
`stored_caps=2,2` (§0.1.17). The mechanism is now:

```python
stmt = (
    pg_insert(Budget)
    .values(
        tenant_id=self.context.tenant_id,
        project_id=project_id,
        max_total_cost_usd=total,
        max_daily_cost_usd=daily,
    )
    .on_conflict_do_update(
        constraint="uq_budgets_tenant_id_project_id",
        set_={
            "max_total_cost_usd": total,
            "max_daily_cost_usd": daily,
            "updated_at": func.now(),   # Core onupdate does NOT fire in a DO UPDATE clause
        },
    )
    .returning(Budget.id)
)
budget_id = (await self.session.execute(stmt)).scalar_one()
budget = (
    await self.session.execute(
        select(Budget)
        .where(Budget.id == budget_id)
        .execution_options(populate_existing=True)   # overwrite the stale identity-map row
    )
).scalar_one()
```

Binding details: `updated_at` **must** be in `set_` (§0.1.17 — otherwise the conflict path silently
stops bumping it, a regression against today's ORM `UPDATE`); `created_at` **must not** be, or the
winner's creation time is rewritten; the re-select **must** carry `populate_existing=True` (a plain
`select` would also return the stale mapped instance); the pre-write `self.get(project_id)` call
stays, because the audit payload's `old_total` / `old_daily` come from it — and that is exactly why
those values are documented as observed-before-write, not a serialized pre-image. Rejected:
`session.expire(existing)` then `session.get` (two round trips and it relies on the caller never
having touched the instance); rejected: `session.refresh` (raises if the instance was never persisted
in this session, i.e. the insert path).

**OD-3 — `register_version` has two collidable keys (§0.1.3). One ladder, locked (Sol v1 defect 4).**
v1 left OD-3 and OD-5 contradicting each other about the "nothing found" case. There is now exactly
one ladder, and OD-5 defers to it by name. After the untargeted
`on_conflict_do_nothing().returning(AgentVersion.id)`:

| Rung | Condition | Result |
|---|---|---|
| 1 | The statement returned an id | **Winner.** Return that version. |
| 2 | No id; re-select by `content_hash` finds a row | **Idempotent winner.** Return it — identical content, identical version, exactly today's `:162-166` contract. |
| 3 | No id; content-hash re-select empty; re-select by `(blueprint_id, version_label)` finds a row | **Differing content by construction** (rung 2 already excluded an identical hash) ⇒ raise `VersionLabelConflict(RegistryError)`, message exactly `agent version label already registered with different content`. |
| 4 | No id and **neither** re-select finds anything | Fail closed ⇒ raise `ConcurrentWriteUnresolved` (OD-5) carrying both attempted keys in its message. |

The ladder is ordered content-hash-first deliberately: it is the writer's own idempotency key
(`app/agents/registry.py:162-166`), so the common identical-content race resolves as idempotent before
the label axis is ever consulted, and a `VersionLabelConflict` therefore only ever fires on genuinely
different content. Rung 4 is unreachable by construction on this schema — both keys are global and
visible to any session that can see the committed conflicting row — so it is proven by **fault
injection**, labelled as such (P-GREEN-3c), and never described as a raced outcome.

The loser is **never** handed a row whose component hashes differ from those it requested. Rejected:
returning the existing row (a §22.2 identity lie and a fake-done under §2.1); rejected: minting a new
label (silent renaming of a caller's declared version); rejected: collapsing rungs 3 and 4 into one
error (they are different facts — a visible conflicting label versus an unexplained invisible
conflict).

**OD-4 — `promote_proposal` is compound, with two conflict axes (§0.1.11).**
**Option A (locked):** one savepoint over the whole artifact + link creation, so a losing attempt
leaves **no** artifact, **no** provenance, and **no** audit row.

**The handler is narrowed (Sol v1 defect 5).** v1 caught *every* `IntegrityError` and inferred "no
promotion row", which would relabel a foreign-key, CHECK, or NOT-NULL failure — or a unique violation
on some unrelated constraint — as a promotion conflict. That is a fake-done under §2.1 and is
replaced by an explicit classification:

```python
except IntegrityError as exc:
    constraint = unique_violation_constraint(exc)   # None unless SQLSTATE 23505
    if constraint not in _PROMOTION_CONFLICT_CONSTRAINTS:   # frozenset of exactly the two below
        raise                                                # FK / CHECK / NOT NULL / other unique: untouched
    ...
```

`_PROMOTION_CONFLICT_CONSTRAINTS` is exactly
`{"uq_intake_artifacts_ref", "uq_extraction_promotions_proposal"}` and is defined next to the handler,
not inline. `unique_violation_constraint` comes from `app/concurrency.py` and returns `None` for any
SQLSTATE other than `23505`, so a non-unique integrity error can never enter a branch. Then, per
constraint:

| Constraint | Meaning | Result |
|---|---|---|
| `uq_extraction_promotions_proposal` | The other session promoted the **same** proposal. | Re-read `promotion_for(proposal_id)`; present ⇒ return its artifact (idempotent, matching the existing `:313-318` contract); absent ⇒ `ConcurrentWriteUnresolved`. |
| `uq_intake_artifacts_ref` | The artifact `ref` was taken. | Re-read `promotion_for(proposal_id)`; present ⇒ the same-proposal race resolved on the artifact axis first, return its artifact; absent ⇒ the `ref` belongs to a **different** proposal's artifact ⇒ raise `PromotionRefConflict(ValueError)`, message exactly `artifact ref already used by a different promotion`. |

Because the promoted `ref` is derived from the proposal id (`PREFIX-EXT-<proposal8hex>`, CLAUDE.md
Slice-14b), a same-proposal race is expected to collide on `uq_intake_artifacts_ref` **first**, and
`uq_extraction_promotions_proposal` may prove unreachable under a real race. P-RED-6 must therefore
quote which constraint actually fires, exactly as P-RED-3 does. If the promote-once axis is
unreachable, its branch still stays (fail-closed), its control is fault-injected and labelled as
such, and the fact is recorded as a limitation — it is **not** deleted, and it is **not** claimed to
have been raced. Rejected: converting
`IntakeRepository.add_artifact` to `ON CONFLICT` — it is the shared Slice-11 spine writer whose
deferrable zero-provenance constraint trigger fires at commit, and changing its insert shape is
out of scope and risks that invariant. A savepoint rollback is a transaction-level operation and
fires no UPDATE/DELETE block trigger, so the append-only guarantees are untouched.

**OD-5 — `ON CONFLICT DO NOTHING` returned no row and the winner re-select finds nothing.**
Possible when the conflicting row is invisible to this session — impossible for the four
tenant-scoped keys, whose columns include `tenant_id`, but structurally reachable.
**Option A (locked):** a **bounded** re-select ladder — never a loop — then raise exactly
`ConcurrentWriteUnresolved` from `app/concurrency.py`, declared exactly as
`class ConcurrentWriteUnresolved(Exception)`: fail closed, with the attempted constraint name(s) in
the message and no row returned. It is one shared base, not four domain-rooted subclasses. Callers
that catch only `RegistryError`, `CatalogAdoptionError`, `CostForecastRepositoryError`, or
`ValueError` will not catch it; they must explicitly catch `ConcurrentWriteUnresolved` if they intend
to handle this cross-cutting state. Every GREEN/fault-injection test for this terminal rung asserts
`type(exc) is ConcurrentWriteUnresolved` and the exact message, never merely a parent class.

**Scope, to remove the v1 contradiction Sol named (defect 4):** "bounded" means **one** re-select for
the four single-key writers (rows 1, 2, 4, 5 — one collidable key each), and **the OD-3 ladder** for
`register_version`, which has two collidable keys and therefore two re-selects in a fixed order
before this error is reached. OD-3 is the authority for row 3; this OD supplies only its terminal
rung. There is no third reading. Rejected: a retry loop (unbounded work on an unexplained state);
rejected: returning `None` (turns a real conflict into a silent absence); rejected: raising
`VersionLabelConflict` here (that error means a *visible* conflicting label, which is precisely the
case this rung has excluded).

**OD-6 — existing tests broken by the six fixes.**
**Option A (locked):** mechanical adaptation or tightening only, each listed with a before/after
diff in the PR body and justified against the new contract. Any change that removes an assertion,
loosens a `match=`, or adds `xfail` is a hard review rejection. A newly-unreachable assertion must be
**replaced by an assertion of the new contract**, never deleted.

**OD-7 — how the inventory is published.**
**Option A (locked):** a **code-owned Python constant** in `tests/writer_inventory.py`, not a
generated artifact and not a Markdown table. Structure, frozen:

```python
CENSUS_SCANNER: str  # the Appendix-B program, byte-for-byte
CANDIDATE_ENDPOINTS: tuple[Candidate, ...]   # exactly 122
WRITE_LEAVES: tuple[WriteLeaf, ...]          # deduplicated, one per (table, unique_index)
B2_EDGE_EVIDENCE: tuple[B2EdgeEvidence, ...] # exactly one row per candidate→B2-leaf edge
TIER_A_NODES: Mapping[str, tuple[str, ...]]  # leaf_id -> pytest node ids
PENDING_TIER_A_BATCHES: frozenset[str]       # awaiting commits 7–13 only; empty at commit 14
```

**The candidate→leaf mapping is one-to-many (Sol v1 defect 2).** v1 gave `Candidate` a single `leaf_id`,
which cannot represent a writer that can collide on more than one key — and `register_version` is
exactly that: `uq_agent_versions_blueprint_id_version_label` **and**
`uq_agent_versions_content_hash` (§0.1.3, re-confirmed live in §0.1.16). A one-to-one mapping would
have silently dropped one of its two conflict classes. The frozen dataclasses are therefore:

```python
@dataclass(frozen=True)
class Candidate:
    path: str
    lineno: int
    name: str
    mechanism: str
    leaf_ids: tuple[str, ...]   # >= 1; every collidable key this endpoint can violate

@dataclass(frozen=True)
class WriteLeaf:
    leaf_id: str                # canonically f"{table}.{unique_index}" for A/B2, f"{table}.-" for B1
    table: str
    unique_index: str | None    # None only for tier B1
    tier: str                   # "A" | "B1" | "B2"
    parent_table: str | None
    parent_fk_column: str | None
    rationale: str
    isolation_level: str                      # "READ COMMITTED" | "SERIALIZABLE"
    retryable_loser_sqlstates: tuple[str, ...] # empty, or exactly ("40001", "40P01")
    isolation_citation: str | None             # exact app/…:<line>; required for SERIALIZABLE

@dataclass(frozen=True)
class B2EdgeEvidence:
    candidate_path: str
    candidate_lineno: int
    candidate_name: str
    candidate_mechanism: str
    leaf_id: str
    parent_leaf_id: str
    parent_creation_citation: str  # exact app/…:<line> inside this candidate's function span
```

`register_version` therefore declares **two** `leaf_ids`, each its own Tier-A leaf with its own
registered node (the identical-content race for the content-hash axis, the label-conflict race for the
label axis — P-GREEN-3a and P-GREEN-3b respectively). Because a one-to-many mapping can hide an
omission that a totality check alone would not catch, OD-8 adds an **index-coverage completeness**
assertion (inventory test 5, §3.2), scoped **per candidate** (Sol v2 defect 2): for **each candidate**,
for every table that candidate's own leaves name, **that candidate's** declared `unique_index` set must
**equal** the live catalog's collidable-index set for that table. Dropping either `agent_versions` axis
from `register_version`'s own entry then fails that test by name (P-MUT-10), and P-MUT-14 shows the
per-table form v2 shipped would have let exactly that omission through.

**B2-5 evidence is per candidate→leaf edge (Sol v3 defect 2).** `WriteLeaf` remains deduplicated by
`(table, unique_index)` and carries only catalog-level B2 facts (`parent_table`,
`parent_fk_column`). The writer-specific facts live exclusively in `B2_EDGE_EVIDENCE`. For every
candidate and every `leaf_id` it names whose leaf is Tier B2, there must be exactly one evidence row
matching that candidate's full `(path, lineno, name, mechanism)` identity and the `leaf_id`. The
citation path must equal `candidate.path`; its line must fall inside that candidate function's AST
span; `parent_leaf_id` must resolve to a Tier-A leaf on the declared `parent_table`.

**Shared-leaf fail-closed rule.** Tier is a property of the deduplicated leaf, not of one candidate.
If two or more candidates share a proposed B2 leaf and **any one** candidate→leaf edge lacks valid
B2-5 evidence, the **whole shared leaf is Tier A** and gets a Tier-A node; no candidate may continue
to treat that leaf as B2. Rejected: storing one citation on `WriteLeaf`; rejected: keeping one
candidate in B2 and another in A for the same leaf; rejected: letting a cited edge mask an uncited
edge.

**Per-leaf isolation.** Every leaf declares `isolation_level`. `"READ COMMITTED"` with an empty
`retryable_loser_sqlstates` tuple is the default. A leaf is `"SERIALIZABLE"` only when an exact
existing writer citation proves `require_serializable()` or an owned SERIALIZABLE retry wrapper; its
retryable tuple is exactly `("40001", "40P01")`. If candidates sharing a leaf differ, the whole
deduplicated leaf uses SERIALIZABLE conservatively. Inventory test 3 rejects any other combination.
The `slice55_finalize_decision` leaf is explicitly SERIALIZABLE with those two retryable SQLSTATEs
and `isolation_citation="app/repositories/go_live_decisions.py:445"`.

The inventory lives in `tests/` because it is test infrastructure describing `app/`, not product
behaviour; that placement is a named limitation. Rejected: a Markdown inventory (prose, unassertable);
rejected: a build-time generated file (its own provenance problem, and §0.1.9 shows generation cannot
resolve 106 of 119 targets anyway); rejected: keeping `leaf_id` singular and adding a second
`extra_leaf_ids` field (two ways to say the same thing, and the totality check would only walk one).

**OD-8 — the barrier tier taxonomy and its classification rule.**
**Option A (locked): three tiers, and the tier of every leaf is derived from the live catalog by this
exact query, which the builder must embed verbatim in `tests/test_slice83_inventory.py`:**

**Sol v1 defect 3 is fixed here.** v1's query compared the **whole** `indkey`, which includes an index's
`INCLUDE` (non-key) columns, so `UNIQUE (code) INCLUDE (id)` looked like a primary-key superset and
was dropped — Sol's mutation returned zero rows. The query below is bounded to the first
`indnkeyatts` **key** attributes on both sides. It was re-run live (§0.1.16): same `120` / `88` on the
current schema, and it now returns `1` row for Sol's mutation where v1's returned `0`.

```sql
WITH pk AS (
  SELECT i.indrelid AS reloid,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols
    FROM pg_index i
   WHERE i.indisprimary
),
uq AS (
  SELECT i.indrelid AS reloid, ic.relname AS idxname,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols,
         i.indpred IS NOT NULL AS partial
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c  ON c.oid  = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND i.indisunique AND NOT i.indisprimary AND c.relkind = 'r'
)
SELECT c.relname, uq.idxname, uq.partial
  FROM uq JOIN pk ON pk.reloid = uq.reloid JOIN pg_class c ON c.oid = uq.reloid
 WHERE NOT (pk.cols <@ uq.cols)
 ORDER BY c.relname, uq.idxname;
```

Note the array slice must be written this way: `ARRAY(SELECT …)[1:n]` is a **syntax error** in
PostgreSQL 16 (verified while writing this plan), which is why the plan uses
`unnest … WITH ORDINALITY`. Do not "simplify" it back into a subscript.

On `72ee544` / head `0062` this returns **120 rows over 88 distinct tables** (§0.1.8, §0.1.16); the
builder must quote the live numbers it observes and **stop and report** if they differ.

**Index-coverage completeness, enforced PER CANDIDATE (Sol v1 defect 2, re-scoped by Sol v2 defect
2).** v2 enforced this per **table**: the union of all leaves declared on a table had to equal the
catalog's collidable set for it. That is too weak under a one-to-many mapping — if candidate *X*
declares both `agent_versions` axes and candidate *Y* declares only one, the union is still complete
and *Y*'s omission passes silently. The rule is now:

> For **every candidate**, and for **every table appearing among that candidate's own leaves**, the set
> of `unique_index` values in **that candidate's** `leaf_ids` for that table must **equal** the set of
> `idxname` values this query returns for that table.

A candidate that writes a table therefore declares **every** collidable index on it — conservative and
fail-closed: if a writer genuinely cannot violate one of those indexes, that is an argument for a
cheaper *barrier*, not for omitting the *leaf*. Note this changes only the **mapping**, not the leaf
count: leaves stay deduplicated per `(table, unique_index)` (OD-10), so no Tier-A test is duplicated
and the OD-9 Tier-A projection is unaffected. Per-table completeness is retained as a weaker
additional assertion so an entirely undeclared index still fails. P-MUT-14 proves the difference bites.

**Tier-B2 verification query (Sol v2 defect 3).** The builder embeds this verbatim alongside the OD-8
query and asserts B2-1…B2-4 from it. It was validated live while writing this plan; note the
`attnum = ANY(pi.indkey::int2[])` cast — the `int[]`/`array_agg` spellings fail with
`operator does not exist: integer = integer[]`.

```sql
WITH uq AS (
  SELECT i.indrelid AS reloid, ic.relname AS idxname,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c  ON c.oid  = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND i.indisunique AND NOT i.indisprimary AND c.relkind = 'r'
),
strict_fk AS (
  SELECT con.conrelid, con.confrelid, con.conname,
         ca.attname AS child_col, ca.attnum AS child_attnum, pa.attname AS parent_col,
         (pg_get_expr(d.adbin, d.adrelid) ILIKE '%gen_random_uuid%'
            OR pa.attidentity <> '')                                AS parent_server_generated,
         EXISTS (SELECT 1 FROM pg_index pi
                  WHERE pi.indrelid = con.confrelid AND pi.indisprimary
                    AND pa.attnum = ANY(pi.indkey::int2[]))          AS parent_col_is_pk
    FROM pg_constraint con
    JOIN LATERAL generate_subscripts(con.conkey, 1) AS s(i) ON TRUE
    JOIN pg_attribute ca ON ca.attrelid = con.conrelid  AND ca.attnum = con.conkey[s.i]
    JOIN pg_attribute pa ON pa.attrelid = con.confrelid AND pa.attnum = con.confkey[s.i]
    LEFT JOIN pg_attrdef d ON d.adrelid = con.confrelid AND d.adnum = pa.attnum
   WHERE con.contype = 'f'
     AND ca.attname NOT IN ('tenant_id', 'project_id')          -- B2-2: scoping columns serialize nothing
)
SELECT child.relname AS child_table, uq.idxname, parent.relname AS parent_table,
       f.child_col, f.parent_col, f.parent_server_generated, f.parent_col_is_pk
  FROM uq
  JOIN pg_class child  ON child.oid  = uq.reloid
  JOIN strict_fk f     ON f.conrelid = uq.reloid AND f.child_attnum = ANY(uq.cols)
  JOIN pg_class parent ON parent.oid = f.confrelid
 WHERE f.parent_server_generated AND f.parent_col_is_pk
 ORDER BY child.relname, uq.idxname, parent.relname;
```

A B2 leaf is admissible only if, for **every** collidable index on its table, this query returns a row
matching the declared `(child_table, idxname, parent_table, parent_fk_column)`. Any gap ⇒ Tier A.

- **Tier A — real two-session race test, required.** The leaf's table appears in that result and its
  collidable index is **not** parent-scoped. Barrier: a retained two-session test with an absent-read
  barrier, a blocked-at-write observation, an assertion that no `IntegrityError` escaped and exactly
  one row exists on the contended key, **and** a mutation probe.
  **Amended by v6 §0A and corrected by v7/v9.** Tier A is now **subdivided by consequence** into
  **A1** (derived-write, **21** leaves, production change authorized), **A2** (independent-insert,
  **38** leaves, tests only, an escaped
  `23505` is the correct observed behaviour) and **A3** (append-only, 53 leaves, tests only, both rows
  commit and are distinct). The sentence above states the **A1** barrier; §0A.4 states the A2 and A3
  barriers, which are what those leaves must assert instead. Where this bullet and §0A.4 differ, **§0A.4
  governs**; in particular "exactly one row exists on the contended key" does **not** apply to A3, and
  "no `IntegrityError` escaped" does **not** apply to A2. The classification of every leaf into a
  subtier is evidence-bound per §0A.2 and recorded in `.planning/SLICE-83-LEAF-EVIDENCE.md`.
- **Tier B1 — catalog non-collidability.** The leaf's table does **not** appear in that result.
  Barrier: assert from the same query that the table is absent, therefore two concurrent inserts
  cannot raise a unique violation. Load-bearing: a migration that later adds a collidable unique key
  moves the table into the result set and fails the test until a Tier-A node is registered.
- **Tier B2 — parent-serialized child.** Every collidable index on the table includes a column
  belonging to a foreign key to the declared `parent_table`, and the parent row is created in the same
  transaction with a server-generated identifier.

  **The B2 barrier must verify its own claim (Sol v2 defect 3).** v2 asserted only that
  `parent_fk_column` sat in each collidable index and that the parent leaf was Tier A — it never
  checked that the column *is* a foreign key to the declared parent, or that the parent key is
  server-generated. §0.1.20 shows why that is not a formality: an FK-intersection check alone matches
  `tenant_id` and `project_id` on nearly every child table, and both racers share the same tenant and
  project, so such a column serializes **nothing**. Every B2 leaf must now satisfy **all five**
  conditions, four of them catalog-asserted:

  | # | Condition | Proven from |
  |---|---|---|
  | B2-1 | `parent_fk_column` is a column of a real `contype='f'` constraint on the child whose referenced table is exactly the declared `parent_table` | `pg_constraint` |
  | B2-2 | `parent_fk_column` is **not** `tenant_id` and **not** `project_id` (a shared scoping column serializes nothing) | column name, explicit denylist |
  | B2-3 | The parent attribute that column references is the parent's **primary key** and carries a server-generated default (`gen_random_uuid()`) or is an identity column | `pg_index` + `pg_attrdef` / `attidentity` |
  | B2-4 | `parent_fk_column` appears in the key columns of **every** collidable index on the child table | the OD-8 query |
  | B2-5 | **For each candidate→leaf edge**, that candidate creates the parent row **in the same transaction**, cited to an exact `app/…:<line>` inside that candidate's function span; the edge names the exact Tier-A parent leaf | **not catalog-provable** — edge-bound cited code + review |

  **Fail closed:** a leaf that fails **any** of B2-1…B2-4 is **reclassified Tier A** and gets a real
  two-writer test. It is never argued into B2 with prose. If B2-5 cannot be proved for **every
  candidate→leaf edge**, the whole shared leaf is also Tier A. Where a collidable index contains
  **several** qualifying FK columns, the declared one
  must be the one the writer actually mints — §0.1.20's `agent_provided_skills.uq_aps_capability_skill`
  is the trap: it qualifies on both `capability_id → agent_skill_capabilities.id` and
  `skill_id → skills.id`, and `skills` is migration-seeded, so declaring `skill_id` would be wrong even
  though the catalog accepts it. Every candidate edge's B2-5 citation plus exact Tier-A parent-leaf
  binding is what excludes that; the residual reliance on review is a named limitation.

  Load-bearing: adding an unscoped unique key (say `UNIQUE (tenant_id, code)`) to a child breaks B2-4
  and forces Tier A; redeclaring a B2 leaf's parent column as `tenant_id` breaks B2-2; pointing it at a
  non-FK column breaks B2-1; pointing it at a seeded parent whose key is not server-generated breaks
  B2-3.

Rejected: a static "the code contains `on_conflict_do_nothing`" assertion as a barrier — it proves a
clause exists, not that the caller handles the `None`. Rejected: a single-session pre-seeded probe —
§0.1.7 shows it never enters the conflict handler.

**OD-9 — batching, the 500-line cap, and whether 122 barriers fit one PR.**
**Option A (locked): one slice number 83, one branch, one PR, fourteen sequential commits in ONE
executable order.** The 122 candidates are **not** parked and are **not** deferred to a later slice.

**THE ORDER (Sol v2 defect 4 — this table is the single authority; §7 and §4.1 mirror it and must not
diverge).** v2 contradicted itself three ways: OD-9 said splits first, §7 listed the RED commit first,
and §3.2 told the builder to update the inventory "in the same commit as each split" although
`tests/writer_inventory.py` does not exist until commit 5. Resolved as follows:

| # | Commit | Contents | Gate to pass before moving on |
|---|---|---|---|
| **1** | `refactor(cost-forecasts): …` | §1a-split of `cost_forecasts.py` → 4 modules. Pure move. | Suite pass counts **identical** to the branch point (§1a-split rule 5); `wc -l` all ≤ 500. |
| **2** | `refactor(extraction): …` | §1a-split of `extraction.py` → 2 modules. Pure move. | Same. P-MUT-13 (re-exports load-bearing). |
| **3** | `test(slice-83): retain the six first-write RED signatures` | `tests/slice83_support.py` + the seven RED drivers; **report only, no conflict-handling line**. | All seven RED transcripts quoted, nine constraint determinations (P-RED-3 and P-RED-6 each name two). |
| **4** | `fix(concurrency): …` | **One fix commit** containing `app/concurrency.py`, all six OD-2 mechanisms, and all GREEN/mutation tests for those mechanisms. Six per-writer fix commits are forbidden. | Every GREEN and P-MUT-1…6, 1b, 1c, 12 quoted. |
| **5** | `test(slice-83): publish and assert the … inventory` | `tests/writer_inventory.py` + the **seven** §3.2 tests. All 122 candidates and all leaves land now. `PENDING_TIER_A_BATCHES` is initialized to exactly the Tier-A leaves lacking a collectible pre-existing node. | Tests 1–3 and 5–7 pass over the complete inventory. Test 4 proves `TierA == registered ⊎ pending`; no leaf is absent or in both. P-MUT-7…11, 14, 15, 16 pass. |
| ~~**6–8**~~ | ~~`test(slice-83): tiered barriers for {intake,release,agent} leaves`~~ | **SUPERSEDED by v6 §0A.6.** | — |
| ~~**9**~~ | ~~`test(slice-83): tiered barriers for platform leaves`~~ | **SUPERSEDED by v6 §0A.6.** | — |

**Commits 6 onward are re-locked in v6 §0A.6** — commit 6 publishes the subtiers, 7 lands the four A1
production fixes with their **9 module-owned barriers**, 8 the remaining **12 A1 barriers** (including
`run_checkpoint_writes`), 9–10 the A2 barriers, 11–13 the A3 barriers, and 14 closes the inventory.
The v5 rows above are struck through, not deleted, so the history stays readable. Everything else in
OD-9 — the per-commit green rule, the no-partial-inventory rule, the commit-5 sequencing lock, and the
"no leaf is parked" rule — is unchanged and still binding.

**Batch labels ↔ commit numbers**, so the §3 section names and this table cannot be read apart:
Batch 1 (§3.1, the six signatures) = commits **3** (its REDs) and **4** (its fixes, GREENs and
mutations); Batch 2 (§3.2, inventory) = commit **5**. The two §1a-split commits (**1** and **2**)
precede every batch and belong to no batch. **v6 §0A.6 replaces the v5 batch-3-to-6 mapping**: the
§3.3–3.6 barrier work is now organised by **subtier**, not by domain — commit 6 (subtier publication),
7–8 (A1), 9–10 (A2), 11–13 (A3), 14 (close). Where a §3.3–3.6 heading names a domain batch, read it as
the barrier bar for the leaves in that domain and take the commit assignment from §0A.6.

**Why splits come first, and why that does not weaken RED.** The splits are pure moves that add **no**
conflict handling, so RED captured *after* them still runs against unfixed writers — the signatures are
unchanged. Doing them first buys two things: the RED drivers import the final module paths (no rewrite
at commit 4), and the inventory is authored **once**, at commit 5, against post-split `(path, lineno)`
values. Rejected: RED first then splits (the RED drivers and every quoted line reference would have to
be reworked, and the split's "identical pass counts" gate would be measured against a moving suite);
rejected: splits after the fixes (ships a knowingly over-cap file and mixes a move with a behaviour
change in one reviewable unit).

Each commit must leave `make test` and `make test-db` green on its own; commits 1 and 2 must leave the
pass counts **identical**, not merely green (§1a-split rule 5).

**Commit-5 sequencing lock — Option (b), resolving Opus D-1.** `PENDING_TIER_A_BATCHES` is a
fail-closed sequencing set, not a parking lot and not a partial inventory:

1. At commit 5, all 122 candidates and every deduplicated leaf are present and pass inventory tests
   1–3 and 5–7. After the OD-13 survey registers collectible pre-existing nodes,
   `PENDING_TIER_A_BATCHES` is initialized once to the exact set of remaining Tier-A leaf IDs.
2. Inventory test 4 asserts the disjoint-union invariant
   `tier_a_leaf_ids == set(TIER_A_NODES) | set(PENDING_TIER_A_BATCHES)` and
   `set(TIER_A_NODES).isdisjoint(PENDING_TIER_A_BATCHES)`. It still validates every registered node's
   collectibility; it skips that one node-existence assertion only for a pending ID.
3. No leaf may be added to pending after commit 5. Commit 6 publishes subtiers and must not shrink
   pending unless a node lands in that same commit; no node lands in commit 6. Each of commits 7–13
   may remove a leaf ID only in the same commit that adds its collectible node and `TIER_A_NODES`
   registration. Thus every intermediate commit remains green as required by OD-9's per-commit green
   rule (v4 line 1024), while the complete 122-candidate inventory required by OD-9's
   no-partial-inventory rule (v4 line 1049) is never reduced or deferred.
4. Commit 14 strengthens the same test 4 with
   `assert PENDING_TIER_A_BATCHES == frozenset()`. Pending is therefore temporary intra-PR sequencing
   state only; it cannot survive the final tree.

**The 500-line cap applies to modified production files too, not only created test modules (Sol
defect 6).** v1 stated the cap for created test modules and left `cost_forecasts.py` at 858 and
`extraction.py` at 491 unaddressed. Binding now:

- Every file this slice **creates** — production or test — is ≤ 500 lines.
- Every file this slice **modifies** is ≤ 500 lines **after** the modification. The two that would
  breach it are split per §1a-split, before their conflict-handling edit. **Amended by v6 §0A.5 for
  exactly two files:** `app/repositories/emergency_controls.py` (790) and
  `app/repositories/go_live_decisions.py` (627) already exceed the cap on `1aa7225`, receive only a few
  lines of locking, and are **not** split — the ruling's "no extras" clause forbids creating split
  modules. Recorded as the named limitation
  `emergency_controls_and_go_live_decisions_remain_over_the_500_line_cap`. No other file is exempt.
- A file this slice does **not** touch is out of scope; the pre-existing >500-line test modules
  (§0.1.15) are not reformatted, and that remains a named limitation, not a claim.
- The builder quotes `wc -l` for every created and modified file, before and after, in the PR body.
  Any owned file over 500 lines at the end is a hard review rejection — including via the overflow
  rule below.

Rejected: exempting production files because the cap is "a test-module convention" (the house rule in
the project standards is per-file and says nothing of the kind); rejected: appending the fix to
`cost_forecasts.py` and deferring its split to a later slice (that ships a knowingly non-conforming
file and pushes the debt); rejected: splitting by cutting a class in half across two modules.
**Stop-and-report trigger (not a licence to park):** if after Batch 3 the measured `make test-db`
wall time exceeds **+240 s** over the `72ee544` baseline, ~~or the projected Tier-A count exceeds
**60 leaves**~~ — **the Tier-A-count clause is discharged by v6 §0A.6: the count is measured at 112 and
subdivided by consequence on the owner's ruling, which is not a coverage reduction** — the builder stops
and reports the measured numbers and the projection to the owner and
awaits a ruling on stacking PRs — it does **not** silently reduce coverage, drop a tier, or move
candidates to a later slice. Rejected: splitting into Slices 83a/83b (the owner bound the finding to
one slice number); rejected: shipping a partial inventory.

**OD-10 — deduplication rule for Tier-A tests.**
**Option A (locked):** Tier-A tests are keyed by **(target table, collidable unique index)**, not by
endpoint and not by table. Several endpoints writing the same table through the same key share **one**
Tier-A node, registered against every one of them in `TIER_A_NODES`. This is exactly the
"deduplicated, semantically closed writer-leaf inventory" the audit demanded (`:744`), and it is what
makes 122 candidates finite.

**Restated for the one-to-many mapping (Sol v1 defect 2).** Deduplication runs on the **leaf** side while
the candidate side fans out: one endpoint with two collidable keys declares two `leaf_ids` and is
covered by two nodes, while two endpoints sharing one key declare the same single `leaf_id` and share
one node. The inventory tests assert all three directions: **totality** (every candidate names ≥ 1
leaf and every named leaf exists), **no orphans** (every leaf is named by ≥ 1 candidate), and
**per-candidate index-coverage completeness** (per OD-8: for **each candidate**, for every table that
candidate writes, **that candidate's own** declared index set equals the catalog's collidable set — so a
second axis cannot be quietly omitted by one candidate even when another declares it). Every Tier-A leaf
must have at least one collectible node.

**Cardinality, stated once so nothing contradicts it (Sol v2 defect 2).** A **candidate** maps to **one
or more** leaves. A **leaf** carries **exactly one** tiered barrier. A **barrier** may be shared by many
candidates. No sentence anywhere in this plan says a candidate maps to exactly one leaf or to exactly
one barrier; if one appears to, this paragraph governs.

Rejected: one test per endpoint (duplicated proof of the same index); rejected: one test per table
(merges two distinct keys on one table and loses a conflict class — precisely the `agent_versions`
case); rejected: deduplicating on the candidate side (a multi-key writer would keep only one axis).

**OD-11 — the eight audit-reported "conforming" writers.**
**Option A (locked):** they are **re-proved**, not trusted. The audit's own drivers were never
retained (`:1294`), so each of the eight (`CostEventRepository.record`, `DocumentRepository.ingest`,
`GoLiveDecisionRepository.start_cycle`, the ops incident / signal / hotfix / stabilization inserts,
`ExportBundleRepository.generate`) becomes a Tier-A leaf with a retained two-session test — reusing
the three existing nodes in §0.1.10 where they already satisfy the Tier-A bar, and adding what they
lack. ~~Any of the eight found to *not* return one semantic row without an unhandled `23505` is a
**new** finding: the builder stops and reports it rather than fixing it under this plan.~~ Rejected:
carrying the audit's unretained records forward as coverage.

**Amended by v6 §0A.** All eight are **A2** or **A3** leaves — `cost_events.uq_cost_events_idempotency`,
`documents.uq_documents_content`, `control_loop_runs.uq_clr_idempotency`, and the four ops idempotency
keys are A2; `export_bundles`' file and signature children are A3. So the struck sentence is **inverted**:
an unhandled `23505` on any of them is now the **correct** observed behaviour under the A2 GREEN
contract, not a new finding and not something to fix. What *is* still a stop-and-report is a **wrong row**
— a partial write, a cross-tenant attribution, a deadlock, or a collision reported on an index other than
the leaf's own declared one. The phrase "the OD-11 class" used in §0A.1 refers to the **derived-write**
consequence class this decision named, which is A1; it does not mean these eight writers are A1.

**OD-12 — the three SQL-function wrappers.**
**Option A (locked):** `admin_write_autonomy_policy` registers the existing
`tests/test_admin_policy_race_db.py::test_p_writer_concurrent_first_write` (plus its mutation node) as
its Tier-A barrier, unchanged. `audit_append` (`app/audit.py:30-52`) and `slice55_finalize_decision`
(reached from `app/repositories/go_live_decisions.py:444` `finalize_decision`, span `:444-473`, SQL call
`:452` — **v7 defect 3**; the landed census wrapper constant for this writer reads `:443-472`, which is a
census coordinate and must not be quoted as the writer's location) each get a **new** Tier-A node in
`tests/test_slice83_a1_ledger.py` (v6 §0A.6 commit 8; v5 said `tests/test_slice83_races_platform.py`,
which is superseded and not created). All three wrappers are **A1** leaves under §0A.1 — each reads
committed state and writes a value derived from it — and all three need **no** production change
(advisory lock `421`, project-row `FOR UPDATE`, and the Slice-63 v4.1 first-write path respectively),
except that `admin_policy_changes`'s double-spend still surfaces a raw SQLSTATE because the function is
migration-frozen (§0A.7). The `slice55_finalize_decision` leaf is explicitly
`SERIALIZABLE` because `finalize_decision` calls `require_serializable()` at `:445`; its raw loser may
be only `40001`/`40P01`, and an aborted W2 is rolled back. If the node instead drives the existing
owned retry wrapper, it asserts that wrapper's post-retry row/domain result. In every form, `23505`
must not escape. `audit_append`'s pair must also assert the hash chain stays
verifiable under contention via `audit_verify` — a broken chain there is a **stop-and-report**, not a
fix under this plan. Rejected: treating a wrapper as Tier B1 because its Python is thin.

**OD-13 — pre-existing concurrency tests the audit did not map (§0.1.13).**
**Option A (locked): survey first, then register — never duplicate, never delete.** Before writing any
Batch 3–6 barrier, the builder enumerates every existing test that opens **two or more** concurrent
writer transactions against the same table (starting from, but not limited to,
`tests/test_ecosystem_catalog_races.py`, `tests/test_ops_signals_db.py`,
`tests/test_ops_stabilization_db.py`, `tests/test_export_bundle_db.py`,
`tests/test_admin_policy_race_db.py`) and publishes that survey in the PR body. Any existing node that
already meets the §3.0 Tier-A bar is **registered** in `TIER_A_NODES` as-is; any that contends but
misses part of the bar (no absent-read barrier, no blocked-at-write observation, no mutation) gets a
**new** node in the relevant batch module and the existing test is left untouched. The plan's baseline
claim is exactly the audit's: retained reproducible **audit-specific** pair coverage is `1/122`. Writing
or implying "the repository had only one race test" is a factual error and a review rejection.
Rejected: rewriting existing race tests (churn that invalidates their own citations); rejected:
assuming a file named `*_races.py` already covers the endpoints in its domain — the catalog file
demonstrably does not cover `adopt`.

---

## 3. Implementation steps

Every probe is a `@pytest.mark.db` async test. `pytest.raises(..., match=...)` with `re.escape` on
literals. Two-session probes use two independent connections from `rls_engine` (or `admin_engine` for
the two `agent_*` writers, §0.1.4) plus an `admin_engine` observer, following
`tests/test_admin_policy_race_db.py:49-131`.

### 3.0 Shared harness contract — `tests/slice83_support.py`

`run_two_writers` takes a seeding callable, two writer callables, the contended
`(table, unique_index, key_predicate)`, and the leaf's locked `isolation_level` /
`retryable_loser_sqlstates`. It must, in order:

1. Seed the shared prerequisites and **commit** them, so both writers see identical committed state.
2. Open connection W1 at the leaf's isolation level (**before** beginning the transaction), set the
   tenant GUC, and drive W1 **past its pre-read** so the pre-read returns
   absent — then hold the transaction open.
3. Open connection W2 at the same isolation level, set the same GUC, drive W2 past **its** pre-read
   (also absent), and launch its
   write as a task.
4. Poll `write_wait_snapshot` until `blocked_at_write` is true or the task completes; record
   `pending_before_commit`.
5. Commit W1 and await W2 with a timeout. If W2 completed normally or raised a domain result without
   aborting its transaction, commit W2. If W2 raised a retryable transaction error and PostgreSQL
   aborted its transaction, **roll back W2; never attempt to commit an aborted transaction**.
6. Return a structured result carrying both outcomes (returned row or raised exception), the
   `blocked_at_write` snapshot, `pending_before_commit`, and the post-commit `unique_row_count`.

Every Tier-A assertion set must include: `pending_before_commit is True`;
`blocked_at_write is True`; neither outcome carries SQLSTATE `23505`; and `unique_row_count == 1`.
For a READ COMMITTED leaf, the loser's returned row identity **equals** the winner's or the loser
raises the exact named domain error. For a SERIALIZABLE leaf, a third outcome is admissible: a DBAPI
error whose SQLSTATE is exactly in the leaf's `{"40001", "40P01"}` allowlist, or the owned retry
wrapper's exact post-retry row/domain result. No other DBAPI error is accepted.

A Tier-A test whose `blocked_at_write` is false did not race and is not a barrier — it must
**fail**, not be relaxed.

### 3.1 Batch 1 — the six signatures

For each writer, in the OD-2 row order: (i) quote its RED transcript from §4.1; (ii) apply exactly the
OD-2 mechanism; (iii) add the GREEN two-session test; (iv) add the mutation probe from §4.2.
Implement **all six** OD-2 mechanisms and their GREEN/mutation tests in OD-9 **commit 4, one fix
commit**. Do **not** emit six per-writer fix commits.

**RED→GREEN transition (OD-6, locked).** Commit 3's RED drivers are retained, but commit 4 replaces
their now-unreachable “raw `IntegrityError`/`23505` is returned” assertions with the corresponding
GREEN contract and mutation assertion; it does not leave knowingly failing tests and does not delete
the scenarios. The PR body includes a before/after diff for each transition. This is OD-6's required
replacement of a newly unreachable assertion by the new contract, not a weakening.

Specific obligations beyond the shared contract:

- **Budgets.** Assert the surviving row carries **this** call's caps, that a `budget.set` audit row
  exists for each successful call, and that the audited `old_total` is documented in the test
  docstring as observed-before-write (OD-2 note, named limitation). **Plus the Sol-defect-1
  regression, P-GREEN-1b:** use one `AsyncSession(rls_engine, expire_on_commit=False)` across two
  committed transactions and an independent second session. **Inside txn 1**, bind
  `app.current_tenant` with `set_config(..., true)`, then `upsert` caps `1,1` and commit. **Inside
  txn 2**, re-bind with `set_config(..., true)`, then `upsert` caps `2,2` and commit. **Inside the
  independent confirming-read transaction**, bind again with `set_config(..., true)` before reading.
  Then
  assert *both* that the **returned** object reports `2,2` and that an independent subsequent
  `BudgetRepository.get` reports `2,2` — the returned value and the stored value must agree. Assert
  `updated_at` strictly advanced across the two calls and `created_at` did **not** change. This test
  is sequential, not a race, and its docstring says so. Omitting the txn-2 rebind must produce the
  exact SQLSTATE `42501` RLS refusal on the `budgets` write in P-MUT-1c; session-level
  `set_config(..., false)` is forbidden.
- **`register_blueprint` / `register_version`.** Two **admin** sessions. The `register_version` ladder
  (OD-3) needs **three** GREEN tests: rung 2 — identical content ⇒ both callers get the same row;
  rung 3 — same `(blueprint_id, version_label)` with a different `prompt_hash` ⇒ the loser raises
  `VersionLabelConflict` and the winner's stored component hashes are asserted **unchanged**; rung 4 —
  **fault-injected** (both re-selects patched to return `None`) ⇒ `ConcurrentWriteUnresolved`, with a
  docstring stating plainly that this rung is unreachable by construction and is therefore proven by
  injection, not by contention.
- **`adopt` / `record_policy_version`.** Assert the loser wrote **no** audit row (the early-return
  contract) and that the winner did.
- **`promote_proposal`.** Three GREEN tests: same proposal from both sessions ⇒ one artifact, one
  promotion, both callers get the same artifact id, **and the test quotes which constraint fired**;
  two different proposals forced onto the same explicit `ref` ⇒ the loser raises
  `PromotionRefConflict` and `intake_artifacts` / `extraction_promotions` counts for the loser's
  proposal are **zero** (savepoint left nothing behind); and P-GREEN-6c — a **non-`23505`** integrity
  error inside the savepoint propagates to the caller **unchanged** (`IntegrityError`, not
  `PromotionRefConflict`, not `ConcurrentWriteUnresolved`), which is the control for the OD-4
  narrowing. Prefer a genuine foreign-key or CHECK violation; if none is reachable through this code
  path — the AC parent is pre-validated before insert, so `23503` is not naturally reachable there —
  use fault injection that raises an `IntegrityError` carrying a non-`23505` `sqlstate`, and label the
  test as fault-injected.

### 3.2 Batch 2 — inventory and classification

**Seven** tests in `tests/test_slice83_inventory.py` (v1 had four; tests 5 and 6 came from Sol's v1
defects 2 and 3, and test 7 from his v2 defect 3):

1. **Census equality.** Execute `CENSUS_SCANNER` in-process on the **post-split, post-fix commit-5
   tree** and assert the produced
   `(path, lineno, name, mechanism)` set equals `{(c.path, c.lineno, c.name, c.mechanism) for c in
   CANDIDATE_ENDPOINTS}` minus the three wrappers, that `DIRECT_WRITER_ENDPOINTS == 119`, and that
   `len(CANDIDATE_ENDPOINTS) == 122`. Record and assert the actual post-fix `MECHANISMS` mix in the
   commit-5 inventory; do **not** require equality with §0.1.1's pre-fix `orm_add:107` baseline.
   **This is the load-bearing "a missing candidate fails" test.**
   Its failure message must name the symmetric difference in both directions. **The §1a-split moves
   code between modules, so the scanner's `(path, lineno)` pairs for the moved writers change — which
   is exactly why the locked order (OD-9) puts both splits at commits 1–2 and this inventory at commit
   5.** The inventory is therefore authored **once**, against post-split paths. v2's instruction to
   "update the inventory in the same commit as each split" was impossible — the module does not exist
   yet — and is withdrawn.
2. **Mapping totality.** Every candidate declares ≥ 1 `leaf_id`, each resolving to a `WRITE_LEAVES`
   entry; every leaf is referenced by ≥ 1 candidate (no orphan leaves); every leaf's `table` exists in
   `pg_tables` for `public`; `leaf_id` values are unique and match the canonical
   `f"{table}.{unique_index}"` form for Tier A/B2 or **`f"{table}.-"` for Tier B1**.
3. **Tier derivation.** Run the OD-8 query; assert every Tier-A/B2 leaf's table is in the result and
   every B1 leaf's table is absent; quote the live row/table counts. (B2's own conditions B2-1…B2-5 are
   asserted by test 7, not here.) Also assert every leaf's isolation tuple: READ COMMITTED ⇒ no
   retryable loser SQLSTATEs; SERIALIZABLE ⇒ exactly `("40001", "40P01")` plus an exact existing
   writer citation proving `require_serializable()` or an owned retry wrapper. Assert the
   `slice55_finalize_decision` leaf is SERIALIZABLE.
4. **Tier-A node registration with fail-closed pending sequencing (Opus D-1).** At commits 5–13,
   every Tier-A leaf is in exactly one of `TIER_A_NODES` or `PENDING_TIER_A_BATCHES`; every listed
   node id is collectible, and every pending ID resolves to a real Tier-A leaf with no registered
   node. Tests 1–3 and 5–7 still execute over pending leaves; only the collectible-node assertion is
   skipped for those IDs. Commit 6 publishes subtiers without shrinking pending. Commits 7–13 remove
   a pending ID only as its node lands. Commit 14 adds
   `assert PENDING_TIER_A_BATCHES == frozenset()`. P-MUT-17 proves final pending cannot hide a leaf.
5. **Index-coverage completeness, PER CANDIDATE (Sol v1 defect 2, re-scoped by Sol v2 defect 2).** For
   **each candidate**, and for every table appearing among **that candidate's own** leaves, the set of
   `unique_index` values in that candidate's `leaf_ids` for that table **equals** the set of `idxname`
   values the OD-8 query returns for that table. Retain the weaker per-table union assertion as well,
   so a wholly undeclared index still fails. Assert explicitly that `register_version`'s **own**
   candidate entry names both `agent_versions` axes. The failure message must name the candidate, the
   table, and the missing or extra index. This is the test that makes P-MUT-10 and P-MUT-14 bite.
6. **Classification-query correctness (Sol v1 defect 3).** In one transaction on the admin engine,
   create a scratch table with a primary key and a `UNIQUE (code) INCLUDE (id)` index, run the OD-8
   query, and assert the scratch index **is** returned; then run the whole-`indkey` variant and assert
   it is **not**. Roll the transaction back so nothing persists. This retains Sol's mutation as a
   permanent guard against the query regressing.
7. **Tier-B2 mapping and per-edge verification (Sol v2 defect 3 + Sol v3 defect 2).** Put the
   candidate-edge checks in one private pure helper,
   `_assert_b2_edge_evidence(candidates, leaves, edge_evidence)`, so inventory test 7 and P-MUT-16
   execute the identical rules. Run the OD-8 Tier-B2 query; for every B2 leaf
   assert B2-1…B2-4 against it — real FK to the declared `parent_table`, `parent_fk_column` not
   `tenant_id`/`project_id`, referenced parent attribute a server-generated primary key, and presence
   in **every** collidable index on the child. Then enumerate the exact set of candidate→leaf edges
   whose leaves are Tier B2 and assert it equals the key set of `B2_EDGE_EVIDENCE`: exactly one row
   per edge, no missing or extra rows. For each edge, assert the non-empty citation has the form
   `app/…:<line>`, the path equals the candidate path, the line is inside that candidate function's
   AST span, and `parent_leaf_id` resolves to a Tier-A leaf on the declared parent table. Any B2 leaf
   failing B2-1…B2-4, or having **any** candidate edge fail B2-5, must be Tier A in every candidate
   mapping; the test fails naming the candidate, leaf, and condition. This is what makes P-MUT-15 and
   P-MUT-16 bite.

### 3.3–3.6 Leaf barriers — organised by SUBTIER in v6, not by domain

**v6 re-scope.** v5 batched these four sections by domain across commits 6–9. §0A.6 replaces that with a
**subtier** order across commits 6–14, because the barrier a leaf needs is decided by its consequence
class and not by which subsystem it lives in. The paragraph below still states the *bar*; the *batching*
comes from §0A.6 and the module names from the §1b v6 addition.

Per batch: add the two-session tests for that batch's leaves — each asserting the **subtier's** GREEN
contract from §0A.4, each with its subtier mutation control, and each with the mandatory only-wrong-axis
assertion — plus the Tier-B1/B2 catalog assertions for any B leaves in scope. Reuse the existing
`tests/*_support.py` seeders rather than writing new graph builders. Each batch commit must leave both
suites green and must keep every §3.2 test passing — atomically adding `TIER_A_NODES` registrations and
removing those exact IDs from `PENDING_TIER_A_BATCHES`, so the inventory and barriers stay consistent at
every commit, never one without the other. No new pending ID may be added after commit 5. **Commit 14**
adds the final-empty assertion and P-MUT-17. Because the inventory module already exists from commit 5,
these are edits to it, not creations of it — with the single exception of `tests/writer_inventory_c.py`,
which commit 6 creates.

For commits **9–13** there is an additional hard gate: `git diff --stat -- app/` must be **empty**. An A2
or A3 barrier that required a production change was mis-tiered — **stop and report** (§0A.2 and §8
constraint 0a), never re-tier the leaf and never add the handler.

---

## 4. Named probes

### 4.1 RED — run at OD-9 commit 3, before any conflict-handling edit, and quote raw output

The audit gives result records but no retained drivers (`:1294`), so all six drivers are written by
the builder from the §3.0 harness and must be shown RED before any conflict-handling line changes.

**Line references in this table are `72ee544` coordinates; RED actually runs at OD-9 commit 3, i.e.
after the two pure-move splits.** Two targets therefore live in new modules by then:
`promote_proposal` in `app/repositories/extraction_promotion.py` and — unchanged — `record_policy_version`
in `app/repositories/cost_forecasts.py` (the split leaves it there, §1a-split). The drivers call the
**public** entry points (`ExtractionRepository.promote_proposal`, `CostForecastRepository.record_policy_version`),
which the re-exports keep stable, so no driver depends on a moved private symbol. Because a pure move
adds no conflict handling, these are still true REDs; if any signature differs from the audit's,
**stop and report** rather than adjusting the expectation.

RED for the six = the loser's outcome
**is** a SQLAlchemy `IntegrityError` carrying SQLSTATE `23505` on the **named** constraint. Quote, for
each: `type(exc).__name__`, `pg_state(exc)` (`tests/admin_support.py:252`), the constraint name from
the message, and the post-commit `unique_row_count`.

| Probe | Endpoint | Must show |
|---|---|---|
| **P-RED-1** `budget_upsert_first_write` | `BudgetRepository.upsert` `app/repositories/cost.py:184-225` | `IntegrityError` / `23505` / `uq_budgets_tenant_id_project_id`; `row_count == 1` |
| **P-RED-2** `register_blueprint_first_write` | `register_blueprint` `app/agents/registry.py:102-122` (two **admin** sessions) | `IntegrityError` / `23505` / `uq_agent_blueprints_key`; `row_count == 1` |
| **P-RED-3** `register_version_first_write` | `register_version` `app/agents/registry.py:125-177` (two **admin** sessions) | `IntegrityError` / `23505`; quote the constraint **actually** reported and whether it is `uq_agent_versions_blueprint_id_version_label` or `uq_agent_versions_content_hash` (§0.1.3); `row_count == 1` |
| **P-RED-4** `catalog_adopt_first_write` | `CatalogAdoptionRepository.adopt` `app/repositories/catalog_adoptions.py:31-80` | `IntegrityError` / `23505` / `uq_tca_tenant_project_listing`; `row_count == 1` |
| **P-RED-5** `forecast_policy_version_first_write` | `record_policy_version` `app/repositories/cost_forecasts.py:153-228` | `IntegrityError` / `23505` / `uq_cfpv_project_digest`; `row_count == 1` |
| **P-RED-6** `promote_proposal_first_write` | `ExtractionRepository.promote_proposal` — `app/repositories/extraction.py:296-401` at `72ee544`, **`app/repositories/extraction_promotion.py` after the commit-2 split** (the public entry point is unchanged; see the note below the table) | `IntegrityError` / `23505`; quote the constraint **actually** reported and whether it is `uq_intake_artifacts_ref` or `uq_extraction_promotions_proposal` (OD-4); artifact and promotion counts `== 1` |
| **P-RED-7** `unbarriered_candidate_survey` | the coverage half of F-020 | Before any test is added: (a) `CANDIDATE_WRITER_ENDPOINT_TOTAL=122` from the re-run scanner; (b) the **OD-13 survey** — the enumerated set of existing tests that open two or more concurrent writer transactions on one table, with the endpoints each actually contends, quoted with the command used; (c) the derived set of candidates with **no** existing barrier, whose size must be > 0. This is the RED for "a missing retained barrier". Do **not** state that only one race test exists (§0.1.13); state that retained reproducible **audit-specific** pair coverage is `1/122` and that the survey found *N* pre-existing contending nodes covering *M* endpoints, leaving `122 − M` unbarriered. |

Every RED must also record `pending_before_commit is True` and `blocked_at_write is True`; a RED that
did not actually contend proves nothing and must be re-driven, **not** re-interpreted.

**Gate.** No **conflict-handling** line may change until all seven RED transcripts are in the build
report — and both P-RED-3 and P-RED-6 must name their two candidate constraints and state which one
actually fired, so the report carries nine constraint determinations across the seven probes. Per the
OD-9 order (the single authority on sequencing), the two §1a-split commits land **first**, at commits 1
and 2, **before** this RED report at commit 3; that is sound because a pure move introduces no conflict
handling, so the RED signatures it precedes are unchanged — and it means every RED driver and quoted
line reference already targets the final module paths. RED is therefore captured on the split tree, not
on `72ee544` verbatim; the builder states that plainly when quoting, and any RED whose signature
differs from the audit's is a **stop-and-report**. If a RED does
not reproduce, **stop and report** with the raw output; do not adjust the probe until it reproduces,
and do not proceed on the assumption that the audit's record was wrong.

### 4.2 GREEN and MUTATION

| Probe | Asserts (exact) |
|---|---|
| P-GREEN-1 | Budgets, raced: no `IntegrityError`, no `23505`, `row_count == 1`, loser row id == winner row id, surviving caps == this call's caps, one `budget.set` audit row per successful call |
| **P-GREEN-1b** | Budgets, **sequential regression across two committed transactions (Sol v1 defect 1, re-locked by Sol v2 defect 1 and Sol v3 defect 1)**. Exact shape: **one** `AsyncSession(rls_engine, expire_on_commit=False)` on a freshly seeded unique tenant/project; transaction 1 → `SELECT set_config('app.current_tenant', :t, true)` → `upsert(1,1)` → **commit**; transaction 2 → the same transaction-local `set_config(..., true)` **again** → `upsert(2,2)` → **commit**. In an **independent second session and transaction**, execute the same `set_config(..., true)` before the confirming read. Assert: the object returned by call 2 reports `2,2`; a `BudgetRepository.get` in the same session reports `2,2`; the independent second session reports `2,2` (so the claim cannot be satisfied by the identity map); `updated_at` **strictly advanced** between the two commits; `created_at` unchanged; `row_count == 1`. Two committed transactions are required because `now()` is frozen per transaction (§0.1.19); three separate tenant binds are required because the GUC is cleared at commit (§0.1.21). Not a race; the docstring says so. `set_config(..., false)` is forbidden. |
| P-GREEN-2 | Blueprints: loser returns the winner's blueprint id; `row_count == 1` |
| P-GREEN-3a | Versions, ladder rung 2, identical content: both callers receive the same `AgentVersion.id`; `row_count == 1` |
| P-GREEN-3b | Versions, ladder rung 3, same `(blueprint_id, version_label)` + different `prompt_hash`: loser raises `VersionLabelConflict` with exactly `agent version label already registered with different content`; the winner's six component hashes are unchanged; `row_count == 1` |
| **P-GREEN-3c** | Versions, ladder rung 4 (OD-3/OD-5), **fault-injected**: both re-selects patched to return `None` ⇒ `type(exc) is ConcurrentWriteUnresolved`, naming both attempted keys; no row returned. It must not be caught by `pytest.raises(RegistryError)`. Docstring states it is injected because the rung is unreachable by construction. |
| P-GREEN-4 | Adoptions: loser returns the winner's adoption id, wrote **no** `catalog.adopted` audit row; `row_count == 1` |
| P-GREEN-5 | Forecast policy: loser returns the winner's row, wrote **no** `cost_forecast.policy_recorded` audit row; `row_count == 1` |
| P-GREEN-6a | Promotion, same proposal: one artifact, one promotion, both callers get the same artifact id; the fired constraint is quoted |
| P-GREEN-6b | Promotion, different proposals forced onto one `ref`: loser raises `PromotionRefConflict` with exactly `artifact ref already used by a different promotion`; the loser's proposal has **zero** artifacts and **zero** promotions (savepoint left nothing) |
| **P-GREEN-6c** | Promotion, **non-`23505` control (Sol v1 defect 5)**: an integrity error inside the savepoint whose SQLSTATE is **not** `23505` propagates unchanged as `IntegrityError` — **not** `PromotionRefConflict`, **not** `ConcurrentWriteUnresolved`. Prefer a real FK/CHECK violation; if unreachable through this path, fault-inject and label it. |
| P-MUT-1…6 | For each writer: with **only** the new conflict handling removed — monkeypatch the repository method to the pre-fix body via `patched_out_conflict_handling` — the **identical** two-session driver again yields `IntegrityError` / `23505` on the named constraint. A mutation that changes anything else is invalid. |
| **P-MUT-1b** | Budgets: drop **only** `populate_existing=True` from the re-select ⇒ P-GREEN-1b fails, and the failure shows the stale identity-mapped caps (Sol's `returned_caps=1,1` vs `stored_caps=2,2`). Separately, drop **only** `updated_at` from `set_` ⇒ the `updated_at`-advanced assertion fails. Both directions required. |
| **P-MUT-1c** | Budget tenant rebind (Sol v3 defect 1): omit **only** the `set_config(..., true)` call in transaction 2 while retaining txn 1 and the independent-read binds ⇒ the second upsert raises a SQLAlchemy DBAPI error carrying PostgreSQL SQLSTATE **`42501`** (`new row violates row-level security policy for table "budgets"`), because commit cleared the GUC. Assert that exact SQLSTATE/message; do not accept a read miss or alternate exception. This proves the rebind is load-bearing. A session-level bind is not an allowed mutation repair. |
| P-MUT-7 | Inventory: delete one entry from `CANDIDATE_ENDPOINTS` ⇒ the census-equality test fails naming that entry; add a fake entry ⇒ it fails naming the fake. Both directions required. |
| P-MUT-8 | Tier derivation: point one B1 leaf at a table that **does** carry a collidable unique key ⇒ inventory test 3 fails; point one B2 leaf's `parent_fk_column` at a column absent from one of its collidable indexes ⇒ **B2-4** fails in inventory test 7 (this is the containment half; P-MUT-15 covers B2-1, B2-2, B2-3 and the wrong-parent-leaf half of B2-5; P-MUT-16 covers missing per-edge evidence). |
| P-MUT-9 | Tier-A registration: remove one node id from `TIER_A_NODES` ⇒ the registration test fails naming the unbarriered leaf. |
| **P-MUT-10** | Multi-key inventory (Sol v1 defect 2): remove the `agent_versions.uq_agent_versions_content_hash` leaf ⇒ inventory test 5 fails naming that index; separately remove `agent_versions.uq_agent_versions_blueprint_id_version_label` ⇒ it fails naming that one. **Both** directions required — a mutation that only proves one axis does not prove the mapping is one-to-many. Also remove one `leaf_id` from `register_version`'s candidate entry ⇒ test 5 fails. |
| **P-MUT-11** | Classification query (Sol v1 defect 3): Sol's `UNIQUE (code) INCLUDE (id)` scratch index, retained as inventory test 6 — the `indnkeyatts` query returns it, the whole-`indkey` query does not. Reverting OD-8's query to the whole-`indkey` form must fail that test. |
| **P-MUT-12** | Promotion handler narrowing (Sol v1 defect 5): widen the handler back to bare `except IntegrityError:` with the "no promotion row" inference ⇒ P-GREEN-6c fails, showing a non-`23505` error relabelled as a promotion conflict. |
| **P-MUT-13** | Split purity (Sol v1 defect 6): after each §1a-split commit, confirm every symbol in §0.1.18 still imports from its original module path, and that deleting one re-export breaks a real existing caller's import — proving the re-exports are load-bearing rather than decorative. |
| **P-MUT-14** | **Per-candidate completeness bites (Sol v2 defect 2).** Construct the state Sol's defect describes: leave `agent_versions.uq_agent_versions_content_hash` in `WRITE_LEAVES` and declared by *some* candidate, but remove it from `register_version`'s **own** `leaf_ids`. Assert (a) inventory test 5's **per-candidate** assertion **fails**, naming `register_version` and that index, and (b) the retained **per-table** union assertion still **passes** — proving the per-table form v2 shipped would have missed exactly this omission. Mirror it for the label axis. |
| **P-MUT-15** | **Tier-B2 catalog assertions bite (Sol v2 defect 3).** For one real B2 leaf, four separate one-line mutations, each of which must fail inventory test 7 naming the violated condition: (a) redeclare `parent_fk_column` as `tenant_id` ⇒ B2-2 fails — and note it would have **passed** v2's assertion set, since `tenant_id` sits in the collidable index and in a real FK (§0.1.20); (b) redeclare `parent_table` as a table with no FK from the child ⇒ B2-1 fails; (c) point the leaf at a parent whose referenced key is not a server-generated primary key — a migration-seeded parent such as `skills` ⇒ B2-3 fails; (d) point one edge's `parent_leaf_id` at a non-Tier-A or wrong-table leaf ⇒ B2-5 fails. |
| **P-MUT-16** | **B2-5 is per candidate→leaf edge (Sol v3 defect 2).** Run `_assert_b2_edge_evidence(...)`, the same private pure helper used by inventory test 7, against a minimal fixture containing two candidates mapped to one B2 leaf. Keep valid edge evidence for candidate A and remove only candidate B's edge row/citation. The helper must fail naming candidate B and the shared leaf, and must reject the leaf remaining Tier B2. If the final real inventory naturally contains such a shared B2 leaf, repeat the mutation against that real edge set; the synthetic fixture remains mandatory so the proof does not depend on final tier cardinality. The only valid inventory repair is to restore B's valid edge evidence or reclassify the **whole shared leaf** Tier A for both candidates. |
| **P-MUT-17** | **Pending Tier-A leaves cannot hide (Opus D-1).** On the commit-14 shape, remove one Tier-A leaf's node/registration and leave that real leaf ID in `PENDING_TIER_A_BATCHES`. Tests 1–3 and 5–7 still pass over the fully inventoried leaf, but test 4's final-empty assertion fails naming it. Separately, putting an already-registered or non-Tier-A leaf into pending fails the disjoint-union/type assertions. |
| **P-MUT-18** | **SERIALIZABLE loser handling is exact (Opus D-3).** For the `slice55_finalize_decision` leaf, capture the real loser SQLSTATE (which must be `40001` or `40P01`), remove that observed value from `retryable_loser_sqlstates`, and show its Tier-A node fails; then restore the exact two-value allowlist and mutate step 5 to commit rather than roll back the aborted W2, showing the node fails on the aborted-transaction commit. Neither mutation may admit `23505` or a broad DBAPI exception. |

Every refusal or absence claim needs a paired mutation or only-wrong-axis control. A probe without one
is incomplete and must be rejected in review. Mutations are performed in the probe run and reverted;
no mutation is committed.

---

## 5. Validation — the builder runs all of these and quotes REAL counts

```
uv run alembic heads                 # must print: 0062 (head)
uv sync --frozen
uv run ruff check .
uv run pyright app/concurrency.py app/repositories/cost.py app/agents/registry.py \
                app/repositories/catalog_adoptions.py app/repositories/cost_forecasts.py \
                app/repositories/cost_forecast_types.py \
                app/repositories/cost_forecast_persistence.py \
                app/repositories/cost_forecast_coverage.py \
                app/repositories/extraction.py app/repositories/extraction_promotion.py \
                app/repositories/acceptance_verification.py \
                app/repositories/emergency_controls.py \
                app/repositories/go_live_decisions.py \
                app/release/production_approval_service.py \
                tests/slice83_support.py tests/writer_inventory.py \
                tests/writer_inventory_c.py tests/test_slice83_*.py
make test
RLS_DB_PASSWORD=... make test-db
uv run alembic heads                 # must still print: 0062 (head)
wc -l app/concurrency.py app/repositories/cost.py app/agents/registry.py \
      app/repositories/catalog_adoptions.py app/repositories/cost_forecast*.py \
      app/repositories/extraction*.py app/repositories/acceptance_verification.py \
      app/repositories/emergency_controls.py app/repositories/go_live_decisions.py \
      app/release/production_approval_service.py tests/slice83_support.py \
      tests/writer_inventory.py tests/writer_inventory_c.py tests/test_slice83_*.py
```

- **Pyright scope — honest statement (v8, Sol v7 defect 3).** The `pyright` invocation above is
  **local and mandatory** and must cover **every file this slice touches**, including the four A1
  production modules (`acceptance_verification.py`, `emergency_controls.py`, `go_live_decisions.py`,
  `production_approval_service.py`) and the new `tests/writer_inventory_c.py`. It must report **0
  errors** on those owned paths. What is **not** claimed: that CI enforces this. **CI's `pyright` scope
  is still the Slice 55–63 owned paths only** — widening it to the full repository is **F-017**, which
  Slice 83 does not close, and the full repository still reports thousands of pre-existing errors
  (`CLAUDE.md`). A green local owned-path run therefore proves those files type-check, not that the
  repository does.
- Baseline on `72ee544` for comparison: `make test` → `1277 passed, 1104 deselected`; `make test-db`
  → `1104 passed, 1277 deselected` (`CLAUDE.md` Slice-84 entry). New counts will be higher —
  **quote the actual numbers; never invent or carry them forward.** Every new probe is a `db` test, so
  `make test`'s *deselected* count rises while its *passed* count stays flat.
- Report, as real measured numbers: the §0.1.1 **pre-fix** census block verbatim and a separate
  **post-fix commit-5** census block (including its changed `MECHANISMS` mix); the OD-8 query's live row and
  distinct-table counts; `len(CANDIDATE_ENDPOINTS)`, `len(WRITE_LEAVES)`, and the Tier A / B1 / B2
  split; the count of Tier-A nodes, split into **registered pre-existing** and **newly added**
  (OD-13); and the `make test-db` wall time against the baseline (OD-9).
- **Split verification (Sol v1 defect 6).** Quote `wc -l` for every created and modified file, before and
  after, and confirm **every owned file is ≤ 500 lines** — the `72ee544` starting points are
  `cost_forecasts.py` `858` and `extraction.py` `491` (§0.1.18). For each of the two split commits,
  quote `make test` and `make test-db` pass counts and confirm they are **identical** to the
  immediately preceding commit's, and quote `git diff -M -C --stat` showing the moves as moves. A
  changed count refutes "pure move" — stop and report rather than explaining it.
- **Sol v1-defect confirmations, each quoted:** P-GREEN-1b's returned-vs-stored caps and the
  `updated_at` / `created_at` assertions; both P-MUT-10 directions; inventory test 6 with both query
  forms and their row counts; P-GREEN-6c's propagated `IntegrityError` with its non-`23505` SQLSTATE;
  and the `register_version` ladder rung reached by each of P-GREEN-3a/3b/3c.
- **Sol v2-defect confirmations, each quoted:** P-GREEN-1b's **two commit boundaries** with the two
  distinct `updated_at` values and the independent session's read (and the `now()`-frozen fact of
  §0.1.19 stated as the reason two transactions are required); **both** P-MUT-14 halves — the
  per-candidate assertion failing *and* the per-table assertion still passing on the same mutation;
  all four P-MUT-15 mutations with the condition each violated, including the `tenant_id` case that
  v2's assertion set would have accepted; and the corrected §1a manifest as
  `git diff --name-only -- app/` listing at most the ten paths in §1a — **amended by v6 to the fourteen
  paths of §1a-v7**.
- **Sol v3-defect confirmations, each quoted:** P-GREEN-1b's **three**
  transaction-local tenant binds and P-MUT-1c's txn-2 SQLSTATE `42501`; P-MUT-16's shared-leaf case
  where one cited edge cannot mask one uncited edge; OD-9 commit 4 as one fix commit and commit 5 as
  seven inventory tests; and the locked `PromotionRefConflict` home plus re-export.
- **Opus v4-defect confirmations, each quoted:** commit 5's registered⊎pending invariant,
  monotonic pending-set removals, commit 14's empty set (v4 originally put emptiness at commit 9;
  v6 §0A.6 superseded it), and P-MUT-17; the exact declaration
  `class ConcurrentWriteUnresolved(Exception)` plus a domain-root non-catch; the
  `slice55_finalize_decision` SERIALIZABLE `40001`/`40P01` branch, aborted-W2 rollback, and P-MUT-18;
  and corrected source spans `cost.py:199`, `extraction.py:296-401`, and
  `cost_forecasts.py:153-228`.
- **Commit-order confirmation (OD-9, as amended by v6 §0A.6).** Quote `git log --oneline` for the branch
  and confirm it matches: two `refactor(...)` commits, the RED commit, the fix commit, the inventory
  commit (1–5, landed), then the subtier-publication commit, the A1 fix commit, the A1 ledger commit,
  two A2 commits, three A3 commits, and the closing commit — **fourteen** in total, no reordering.
- **v6/v7 subtier confirmations, each quoted.** (a) The A1 count **`21`** (v7: ~~20~~) and the A1 leaf-id
  set printed from `tests/writer_inventory_c.py` and asserted equal to plan §0A.3 by inventory test 9. (b) The
  **21 / 38** / 53 / 54 / 2 = 168 totals printed from `WRITE_LEAVES` and `SUBTIER` (v7: ~~20 / 39~~).
  (c) The OD-8 query re-run
  live with its `120` rows / `88` tables. (d) `git diff --stat -- app/` **empty** for each of commits
  9–13, proving no A2 or A3 leaf received conflict handling. (e) For each of the four A1 modules, the
  `FOR UPDATE` line added and `wc -l` before/after, with `emergency_controls.py` and
  `go_live_decisions.py` explicitly reported as remaining over the house cap under the §0A.5 limitation.
  (f) One A2 transcript showing the loser's `23505` asserted as the **correct** outcome, and one A3
  transcript showing two committed distinct rows with differing minted parent ids. (g) Each barrier's
  only-wrong-axis assertion naming the observed constraint.
- **v7 defect confirmations, each quoted (Sol `27f3f958-ac5a-493f-ae91-ca04c6bdcf6e`).**
  **(h)** `run_checkpoint_writes.uq_run_checkpoint_writes_id` printed with `SUBTIER == "A1"`, its A1 node
  showing both callers committing with **one** surviving row whose `(channel, type, blob, task_path)` is
  one caller's tuple **in full**, and its mutation — `on_conflict_do_update` replaced by a bare
  `pg_insert` — failing with a raw `23505`; plus `run_checkpoints.uq_run_checkpoints_id` still printed as
  `A2`. **(i)** The pre-lock privilege probe: `SELECT … FROM public.projects … FOR UPDATE` succeeding as
  the runtime role, and the `information_schema.role_table_grants` row proving `UPDATE` on **every** table
  this slice locks; **no `42501` anywhere in the run**. **(j)** `git grep -n "lock_project_row"` over the
  four A1 modules showing four call groups and exactly three added imports, with `git diff -- app/`
  containing **no** `FOR UPDATE` against `intake_artifacts`, `control_loop_runs`, or
  `production_preapproval_attestations`. **(k)** `sed -n '443,444p;452p'
  app/repositories/go_live_decisions.py` proving `:443` blank, `:444` the `async def`, `:452` the SQL
  call — and the landed `CENSUS_SCANNER` wrapper constant `443-472` quoted **unchanged**, with the §0A.7
  limitation naming the two coordinate systems. **(l)** `alembic heads` = **`0062`**, and
  `git diff --name-only -- migrations/` **empty**.
- Pyright: CI's scoped step covers Slices 55–63 only (`.github/workflows/ci.yml:61-62`) and **must
  not be edited**. Run pyright locally on the owned paths above and report `0 errors` for that set.
  The repository-wide `3050`-error baseline is F-017 / Slice 80 and is neither fixed nor hidden.
- `ruff format` only over the files this slice touches; never over the tree.
- Re-assert after the suites: `A5_RULESET_VERSION == "slice54.v1"`; readiness ruleset
  `"slice20.v1"`; `can_go_live_autonomously is False`; `alembic heads` = `0062`;
  `git diff --stat` touches only the paths in §1 plus any OD-6 adaptation, each listed.
- Confirm no probe left a trigger disabled, a monkeypatch installed, or a temporary database behind.

---

## 6. Documentation after merge

Only after the PR merges, and only these:

- **`CLAUDE.md`** — one Slice 83 entry carrying §0.3 **verbatim**, plus: six writers fixed; no
  migration; head stays `0062`; inventory published; 122 candidates barriered; A5 `slice54.v1`;
  readiness `slice20.v1`; `can_go_live_autonomously` literal `False`; F-002/F-003/F-004/F-005/F-008/
  F-017/F-019/F-022 untouched.
- **`.planning/GO-LIVE-END-TO-END-ROADMAP.md`** — §5 Slice 83 status `NOT STARTED` → `COMPLETE`, with
  the exact scope sentence and the tier split; §6 next slice = **Slice 71 / F-008**. Change no other
  slice status; do not mark Slice 61 done; do not touch D-8/D-9/D-10.
- **`.planning/HANDOFF.json`** — Slice 83 merged, next = Slice 71, and the limitations below. Do
  **not** write "no remaining blockers" — that is the F-018 defect.
- **Named limitations to record, verbatim:**
  `f020_tier_b_barriers_prove_absence_of_unique_violation_class_only`,
  `serializable_anomalies_lost_update_write_skew_phantom_not_covered`,
  `endpoint_to_leaf_mapping_is_hand_authored_and_review_verified`,
  `writer_inventory_is_test_owned_not_a_product_api`,
  `agent_blueprint_and_version_pairs_are_admin_path_not_a_runtime_role_boundary`,
  `budget_upsert_audit_preimage_is_observed_before_write`,
  `register_version_label_conflict_refuses_rather_than_returning_a_row`,
  `register_version_unresolved_rung_is_fault_injected_not_raced`,
  `cost_forecasts_and_extraction_split_into_modules_public_api_re_exported`,
  `house_500_line_cap_enforced_only_on_files_this_slice_created_or_modified`,
  `ci_pyright_scope_still_s55_63_full_repo_typecheck_is_f017`,
  `f004_approval_events_tool_calls_allowlist_owner_mutation_still_succeeds`,
  `barrier_suite_is_tiered_only_tier_a_executes_two_concurrent_writers`,
  `tier_b2_same_transaction_parent_creation_is_cited_code_not_a_catalog_proof`,
  `tier_b2_same_transaction_parent_creation_is_bound_per_candidate_leaf_edge`,
  `budget_updated_at_advance_proven_across_two_committed_transactions_only`,
  `budget_runtime_tenant_guc_rebound_inside_all_three_transactions`,
  `tier_a_pending_set_is_intra_pr_sequencing_and_empty_at_final`,
  `concurrent_write_unresolved_is_shared_exception_not_domain_subclass`,
  `serializable_tier_a_allows_only_owned_retryable_transaction_sqlstates`.
  Record **additionally, and only if the builder actually observes it**:
  `promote_proposal_promote_once_axis_control_is_fault_injected` (if P-RED-6 shows
  `uq_extraction_promotions_proposal` is unreachable under a real race, OD-4) and
  `promote_proposal_non_23505_control_is_fault_injected` (if no real FK/CHECK violation is reachable
  through that path, P-GREEN-6c). Do not record either pre-emptively, and do not omit one that was
  observed.
- **Forbidden wording.** Do **not** write, in any form, that UAID is free of races, that writer
  concurrency is proven product-wide, that a concurrency PASS was achieved, or that "all writers are
  safe". Also do **not** write that the repository had only one race test before this slice (§0.1.13).
  Do **not** call the result a "two-writer barrier suite" — only Tier A executes two writers (Sol v2
  defect 3) — and do **not** say a candidate is bound to "exactly one" leaf or barrier. Do **not**
  claim Tier B2 proves the parent row is created in the same transaction; the catalog cannot prove that.
  The correct claim is: *six named first-write writers now hand their loser the winner or a named domain
  error under a retained two-session race, and every one of the 122 audit candidates is bound to one or
  more write leaves, each carrying exactly one tiered barrier whose strength is stated by its tier.*

Do not edit `.planning/FINAL-AUDIT-REPORT.md` or the spec.

---

## 7. GitHub

- Branch **`feat/slice-83-writer-concurrency`** off `72ee544`.
- **Fourteen atomic conventional commits** (commits 1–5 already landed on the branch + commits 6–14
  remaining = 14 total), **in exactly the OD-9 order (Sol v2 defect 4). OD-9's table is the
  single authority; this list mirrors it and must not diverge:**
  1. `refactor(cost-forecasts): split the module under the house line cap, no behaviour change`
  2. `refactor(extraction): split promotion into its own module, no behaviour change`
  3. `test(slice-83): retain the six first-write RED signatures` (report only, no conflict-handling edit)
  4. `fix(concurrency): return the winner or a named result for the six first-write writers`
  5. `test(slice-83): publish and assert the deduplicated writer-leaf inventory`
  6. `test(slice-83): publish the A1/A2/A3 consequence subtiers`
  7. `fix(concurrency): serialize the derived reads behind the A1 write leaves`
  8. `test(slice-83): A1 barriers for the ledger and admin writers`
  9. `test(slice-83): A2 barriers for tenant leaves`
  10. `test(slice-83): A2 barriers for platform leaves`
  11. `test(slice-83): A3 barriers for evidence leaves`
  12. `test(slice-83): A3 barriers for ops leaves`
  13. `test(slice-83): A3 barriers for release leaves`
  14. `test(slice-83): close the inventory`
- PR body must contain: the seven RED transcripts with their nine constraint determinations, every
  GREEN transcript (including P-GREEN-1b's two commit boundaries, 3c, 6c), every mutation transcript
  (including P-MUT-1b, P-MUT-1c, and P-MUT-10 through **P-MUT-18**), the pre-fix and post-fix census blocks, the OD-8 live counts
  and the Tier-B2 query's rows for every B2 leaf, the Tier A/B1/B2 split, the before/after `wc -l` table
  and the two split commits' identical pass counts, `git log --oneline` matching the OD-9 order,
  `git diff --name-only -- app/` matching the §1a-v7 **fourteen**-path manifest, the seven v6 subtier
  confirmations of §5 (A1 count and leaf list, the **21/38**/53/54/2 totals, the live OD-8 counts, the empty
  `app/` diff for commits 9–13, the four A1 modules' `FOR UPDATE` lines and `wc -l`, one A2 and one A3
  transcript, and the only-wrong-axis assertions), the real `make test` /
  `make test-db` / `ruff` / `pyright` counts and the `make test-db` wall-time delta, every OD-6
  adaptation with a before/after diff, and §0.3 verbatim.
- Do not commit `.env`. Do not edit this plan.

---

## 8. Builder constraints, restated

0. **v6: you resume at commit 6.** Commits 1–5 are landed at `ff87704`, `b8a5321`, `7a0347f`,
   `9d0e543`, `43d5ceb`; do **not** rewrite, amend, rebase, or re-plan them. Read §0A before anything
   else — it governs the whole plan. You do **not** edit `.planning/SLICE-83-PLAN.md` or
   `.planning/SLICE-83-LEAF-EVIDENCE.md`; on any disagreement with either, **stop and report**.
0a. **Never add conflict handling to an A2 or A3 leaf.** An escaped `23505` on an A2 leaf is the correct
   observed behaviour and is asserted as such. `git diff --stat -- app/` must be **empty** for commits
   9–13. Violating this is a review rejection (§0A.1).
0b. **Never move a leaf between subtiers.** The subtier is planner-authored and evidence-bound (§0A.2).
   If the evidence looks wrong, stop and report; do not re-tier a leaf to make a barrier easier.
1. **Follow the OD-9 commit order exactly** — v5's landed 1–5 then **v6 §0A.6's commits 6–14**. RED was
   quoted at commit 3 — all seven drivers, with both P-RED-3 and P-RED-6 naming their two candidate
   constraints and which fired (nine determinations). Do not reorder, merge, or split the fourteen
   commits.
1a. **The manifest is exhaustive: fourteen `app/` paths — the ten landed at commits 1–4 plus the four A1
   writer modules of §1a-v7.** `git diff --name-only -- app/` must list nothing else, and nothing at all
   for commits 9–13.
1b. **Commit-5 pending lock (Opus D-1):** all 122 candidates and all leaves landed at commit 5.
   `PENDING_TIER_A_BATCHES` contains exactly the then-unregistered Tier-A leaves; test 4 enforces the
   disjoint union. Commits **7–13** may only remove IDs as their nodes land, and commit **14** must
   assert the set empty. A pending leaf is inventoried, not parked or deferred.
2. **No migration. Head stays `0062`**, asserted before and after.
3. Implement exactly the OD-2 mechanism per writer. Do not substitute `DO UPDATE` where the grant
   forbids it (§0.1.4), and do not add an advisory lock or a retry loop.
3a. **Budget (Sol v1 defect 1):** `updated_at` in `set_`, `created_at` not in `set_`, and the re-select
   carries `populate_existing=True`. `session.get()` after the upsert is forbidden — it returns the
   stale identity-mapped row (§0.1.17).
3b. **Budget probe shape (Sol v2 defect 1):** P-GREEN-1b runs **two committed transactions** on one
   `expire_on_commit=False` session and confirms the stored value through an **independent** session.
   **Inside each of those three transactions**, before any tenant-owned operation, execute
   `SELECT set_config('app.current_tenant', :t, true)`; commit clears the setting (§0.1.21).
   A same-transaction `updated_at` comparison is forbidden — `now()` is frozen per transaction
   (§0.1.19) — and neither `clock_timestamp()` nor session-level `set_config(..., false)` may be
   substituted to make one work. P-MUT-1c proves the txn-2 rebind is load-bearing.
4. `register_version` must walk the OD-3 ladder in order — content hash, then
   `(blueprint_id, version_label)`, then `ConcurrentWriteUnresolved` — must refuse on a
   differing-content label match, and must never return a differing-content row.
4a. **Promotion handler (Sol v1 defect 5):** handle only SQLSTATE `23505` on
   `uq_intake_artifacts_ref` or `uq_extraction_promotions_proposal`; **re-raise every other
   `IntegrityError` unchanged**. A bare `except IntegrityError:` that infers "no promotion row" is a
   hard review rejection.
4b. **Shared unresolved exception (Opus D-2):** define exactly
   `class ConcurrentWriteUnresolved(Exception)` in `app/concurrency.py`; no domain-root inheritance
   and no per-writer subclasses. Tests assert the exact type. Existing domain-root catchers do not
   catch it unless they add this class explicitly.
5. `promote_proposal`'s savepoint must leave a loser with zero artifacts, zero provenance, and zero
   audit rows.
5a. **Inventory (Sol v1 defect 2, re-scoped by Sol v2 defect 2):** `Candidate.leaf_ids` is one-to-many;
   a candidate maps to **one or more** leaves and each **leaf** carries exactly one tiered barrier;
   `register_version` declares both `agent_versions` axes in its **own** entry; inventory test 5
   asserts index-coverage completeness **per candidate** (per-table retained as a weaker extra check);
   P-MUT-10 is proven in **both** directions and P-MUT-14 shows the per-table form would have passed.
5b. **Classification query (Sol v1 defect 3):** use the `indnkeyatts`-bounded form verbatim from OD-8
   and retain inventory test 6. Do not rewrite it as an array subscript — that is a PostgreSQL 16
   syntax error (§0.1.16).
5c. **Tier B2 (Sol v2 defect 3 + Sol v3 defect 2):** every B2 leaf satisfies B2-1…B2-4 asserted from the OD-8 Tier-B2
   `pg_constraint` / `pg_attrdef` query (inventory test 7), and **every candidate→B2-leaf edge** has
   exactly one `B2_EDGE_EVIDENCE` row carrying that candidate's `app/…:<line>` citation and exact
   Tier-A parent leaf. **Any leaf failing any catalog condition, or used by any candidate whose edge
   fails B2-5, is reclassified Tier A as a whole and gets a real two-writer test** — never argued into
   B2 with prose and never split into candidate-specific tiers. Do not
   declare `tenant_id` or `project_id` as a `parent_fk_column`; both racers share them (§0.1.20). Do
   not call the suite a "two-writer" suite; it is **tiered**.
6. Every Tier-A test asserts `pending_before_commit`, `blocked_at_write`, no `23505` escaped, and
   `row_count == 1`. Isolation is per leaf. READ COMMITTED leaves require equal identity or exact
   domain error; existing SERIALIZABLE leaves additionally allow only `40001`/`40P01` or the owned
   wrapper's post-retry result, and roll back an aborted W2 rather than committing it. A test that did
   not contend must fail, not be relaxed.
7. Every refusal or absence claim carries a mutation or only-wrong-axis control. No committed
   mutations.
8. The 122 candidates are not parked, not deferred, and not partially inventoried. If OD-9's
   stop-and-report trigger fires, report measured numbers and wait — do not reduce coverage.
8a. Run the OD-13 survey before Batch 3 and publish it. Register qualifying existing nodes; never
   duplicate, rewrite, or delete them; never claim the repository had only one race test.
8b. `app/repositories/catalog_adoptions.py` is inside CI's pyright path list
   (`.github/workflows/ci.yml:61-62`, §0.1.14). It must be pyright-clean or CI fails. Do not edit the
   workflow to widen or narrow that list.
9. No existing test file grows without an OD-6 justification. **Every file this slice creates or
   modifies — production or test — is ≤ 500 lines at the end (Sol v1 defect 6).** Split
   `cost_forecasts.py` and `extraction.py` per §1a-split at **commits 1 and 2** of the OD-9 order —
   before the RED report and before any conflict-handling edit — as separate pure-move commits:
   byte-identical bodies, every public symbol re-exported from its original path, no caller edited, and
   **identical** suite pass counts across the split commit. A count that moves means it was not a pure
   move — stop and report. The inventory is authored **once** at commit 5, against post-split paths; it
   is never "updated in the same commit as each split", which was impossible.
10. Never re-grant a privilege, never weaken/skip/delete/`xfail` a test, no
    `pytest.raises(Exception)` without `match=`, no alternation across refusal classes.
11. Google-style docstrings on every new public function in `app/concurrency.py` and
    `tests/slice83_support.py`; one function, one responsibility.
12. If any locked decision in §2 turns out to be wrong on the live database — including the OD-8
    counts or any of the six RED signatures — **stop and report to the owner** with raw output. Do not
    re-decide it.

---

## 9. Change log

**v8.** **PLAN REJECT — Slice 83 v7.** Reviewer **GPT-5.6 Sol**, agent
`64f1e982-6d60-4f1a-af81-79eba8c67d64`, 2026-08-25. **Consecutive REJECT #2 of the amendment line.** Not
yet a seat swap — planner stays Claude Opus (substituting for Claude Fable 5), reviewer stays Sol, builder
stays Cursor Grok 4.6 Extra High resuming at **commit 6** — but the owner has ruled that **a third
consecutive REJECT swaps the seats (Sol implements, Opus reviews)**, which is why v8 was verified by
grepping **both** planner-owned files end-to-end rather than only the lines Sol cited. All **four**
probe-backed defects are **accepted in full; none argued down.** All four were **mechanical-completeness**
failures of the same kind: v7 corrected each authoritative section but did not propagate the correction
into every dependent sentence.

| Change | What changed in the document |
|---|---|
| **Defect 1 — counts propagated** | The honesty crux, the allowed-claims list, and the three `tests/` table rows now all read **A1 = 21 / A2 = 38**; `A1_LEAF_IDS` holds **21** ids; commit 7 covers the **9** module-owned leaves; commit 8 covers the **12** barrier-alone leaves and **names `run_checkpoint_writes` explicitly**. The `§0A.3` summary row that read `**A1 = 20** *(v7: 21)*` is rewritten so the live number is the bold one and `20` is struck. |
| **Defect 1 — single source of truth added** | A new **standing count statement** in the header states A1/A2/A3/B1/B2 and the 9 + 12 split **once, authoritatively**, and declares that any surviving `20`/`39`/`11`-`9`/"Nine" string is historical. This is the structural fix for the recurrence: a future amendment changes one paragraph, not eleven. |
| **Defect 2 — every stale lock replaced, not only the three cited** | Sol named evidence lines `85`, `112`, `157`. A grep of `^- \*\*Production change\*\* — REQUIRED` found **nine** such rows; **all nine** were rewritten to carry the exact `lock_project_row(...)` insertion point from §0A.5 rows 1–4 (`acceptance_verification` before `:84`/`:128`/`:167`; `go_live_decisions` between `:298` and `:299`; `production_approval_service` before `:231` and `:326`; `emergency_controls` unchanged at `:79`). Each retains its struck v6 target inline. Six of the nine were stale beyond Sol's three: `94`, `103`, `121`, `166`, `175` carried the same forbidden targets by reference ("same parent-row lock", "same attestation-row lock"). |
| **Defect 2 — the "no new import" claim corrected** | The crux and the allowed-claims list no longer say "an existing parent or project row" or "no import is added". Both now state the truth: the target is **`projects`** via the existing helper `lock_project_row` (`app/repositories/emergency_controls.py:79`), and **three of the four modules newly import it**; `emergency_controls.py` already owns it. **No GRANT, no migration**; head stays `0062`. |
| **Defect 3 — pyright scope completed and bounded honestly** | The four A1 production modules and `tests/writer_inventory_c.py` are added to the mandatory local `pyright` run and to the `wc -l` cap report; existing owned paths kept. A new note states plainly that the run is **local and mandatory at 0 errors on owned paths**, and that **CI's scope remains the Slice 55–63 paths** — widening it is **F-017**, which Slice 83 does not close, with the repository's pre-existing error count acknowledged. |
| **Defect 4 — commit count corrected** | "**Nine** atomic conventional commits" → "**Fourteen**", with the arithmetic shown (commits **1–5 landed** + **6–14 remaining** = **14**). OD-9's table, which already listed fourteen, remains the single authority. |
| Verification performed before returning | Both files grepped for `20` A1 / `39` A2 / `11 leaves` / `holding the 20 ids` / `Nine atomic` and for the three forbidden lock targets. Every surviving occurrence is inside a `~~struck~~` or explicitly historical quotation; the OD-9 table's `9`/`12`/`32`/`53` were confirmed to already agree with the corrected `tests/` table. |

**v7.** **PLAN REJECT — Slice 83 v6.** Reviewer **GPT-5.6 Sol**, agent
`27f3f958-ac5a-493f-ae91-ca04c6bdcf6e`, 2026-08-25. **First consecutive REJECT of the v6 amendment line;
not a seat swap** — planner stays Claude Opus (substituting for Claude Fable 5), reviewer stays Sol,
builder stays Cursor Grok 4.6 Extra High resuming at **commit 6**. All **three** probe-backed defects are
**accepted in full; none argued down.** Each was re-verified by the planner against live source and the
live `app_test` database before acceptance; the transcripts are grounding facts **§0.1.29–§0.1.32**.

| Change | What changed in the document |
|---|---|
| **Defect 1 — leaf reclassified A2 → A1** | `run_checkpoint_writes.uq_run_checkpoint_writes_id` is A1: `app/runtime/checkpointer.py:152-167` is `on_conflict_do_update`, an **upsert path**, and A2 requires create-once. **A1 = 21, A2 = 38** (was 20/39); A3 = 53; Tier A still **112**; total still **168**. **21 ≤ 40 — no halt.** `run_checkpoints.uq_run_checkpoints_id` **stays A2** (`aput` at `:109` is `on_conflict_do_nothing`). New §0A.4 subsection gives its five-clause A1 GREEN contract and its A1-form mutation; §0A.3 row 21 added; §0A.2 records why one A1 row cites an upsert instead of a read. |
| **Defect 1 — production-change decision, made honestly** | **NONE, and no fifth §1a module.** The existing `DO UPDATE` is one atomic statement with **no pre-read**, so nothing derived can go stale and no `23505` reaches the caller — it already meets A1 GREEN. `app/runtime/checkpointer.py` is explicitly listed in §1a-v7's "not in the manifest, and why". Fourteen production paths, unchanged. |
| **Defect 2 — three A1 lock targets struck as unexecutable** | Live as `uaid_app`: `intake_artifacts`, `control_loop_runs`, `production_preapproval_attestations` all return SQLSTATE **`42501`** on `SELECT … FOR UPDATE`; `projects` succeeds. **All four A1 fixes now lock `projects`** via the existing `lock_project_row` (`app/repositories/emergency_controls.py:79`), precedent `0054_control_loop_decisions.py:650` / `ops_stabilization.py:162`. §0A.5 and §1a-v7 tables re-locked with the v6 targets struck through and the exact insertion point and in-scope `project_id` expression named per site. **No GRANT, no migration — head stays `0062`.** New mandatory pre-lock privilege gate; a `42501` from any added lock is a stop-and-report. |
| **Defect 2 — two v6 statements corrected in place** | "**No new import**" is superseded: three modules add exactly one import of an existing helper (§1a-v7, §0A.5, grounding fact §0.1.26 struck and amended); no import cycle exists (§0.1.32). Rows 3–5 of §0A.3 are shown to lock `projects` legally because `slice55_finalize_decision` is **SECURITY DEFINER** (`prosecdef = t`), so defect 2 applies only to locks this slice adds from Python as `uaid_app`. |
| **Defect 3 — four stale writer citations corrected** | `:443` is **blank**; `finalize_decision` is `:444` (span `:444-473`) with its SQL call at `:452`. All four evidence rows now cite `:444`/`:452`. The landed `CENSUS_SCANNER` wrapper constant `app/repositories/go_live_decisions.py:443-472` is kept **byte-identical** (a census coordinate, not a writer citation) and the two coordinate systems may never be quoted interchangeably. |
| Arithmetic transposition fixed | v6 said the four §1a modules own **11** A1 leaves and **9** are barrier-alone. Verified from the §0A.3 table: it is **9** owned (rows 7–11, 13, 15–17) and **12** barrier-alone (rows 1–6, 12, 14, 18–21). 9 + 12 = 21. Not one of Sol's three defects; recorded rather than absorbed. |
| Complete upsert re-audit | §0.1.29 enumerates **every** upsert path: two `on_conflict_do_update` sites in `app/` (`cost.py:210`, `checkpointer.py:152`), one raw-SQL site (`policy_sql.py:91`, the `racy_first_write=True` **mutation-probe** variant only — the installed `autonomy_policies` path is `DO NOTHING` + locked `FOR UPDATE` + `UPDATE`), and **zero** in `migrations/`. All map to A1 leaves; none is left in A2 or A3. |
| Commit order re-locked to the corrected counts | §0A.6: commit **7** = four modules + **9** leaves; commit **8** = the remaining **12** A1 leaves (now naming `emergency_stop_events` ×2 and `run_checkpoint_writes`); commits **9–10** = **32** unregistered A2 leaves (~16 each, was 33/~17); commit **6** now also requires an empty `git diff --stat -- app/`; commit **9** count in §1b updated. Still fourteen commits, still monotonic pending, still empty at the end. |
| Three named limitations added | §0A.7: `run_checkpoint_write_upsert_is_last_writer_wins_not_a_proven_merge`, `a1_locks_serialize_the_project_row_not_the_contended_child`, `census_wrapper_span_443_472_is_an_audit_constant_not_a_writer_citation`. |
| Four grounding facts added, one struck | **§0.1.29–32**: the complete upsert audit; the live `42501`/`OK` privilege matrix; the `projects FOR UPDATE` precedents plus the `prosecdef` check; and the `finalize_decision` coordinates plus the import-cycle check. §0.1.26's "no cross-module import" clause struck and amended. |
| Validation extended | §5 gains **five** v7 confirmations (h)–(l): the A1 subtier and upsert-mutation transcripts, the pre-lock privilege probe with no `42501`, the `lock_project_row` diff shape with no struck target, the `sed -n '443,444p;452p'` proof beside the unchanged census constant, and `alembic heads` = `0062` with an empty `migrations/` diff. |
| Evidence file revised | `.planning/SLICE-83-LEAF-EVIDENCE.md`: the A1 section gains the `run_checkpoint_writes` entry (21 entries), the A2 table drops it and renumbers to **38**, the four `go_live_decisions` citations are corrected, and the header records the v7 counts and the reason. Machine-checked: 21 + 38 + 53 = 112 and 112 + 54 + 2 = 168. |

Consecutive plan REJECT count on the v6/v7 amendment line: **1** (v6, Sol). The v5 approval of
everything neither v6 nor v7 amends still stands, and commits 1–5 are still not re-planned.

---

**v6.** **Owner ruling, 2026-08-25 (Salim) — not a reject.** The OD-9 halt after commit 5 was CORRECT and
is discharged by ruling; the **consecutive plan REJECT count is unchanged**. PLANNER seat = **Claude
Opus substituting for the owner-named Claude Fable 5**, recorded in the header; REVIEWER = **GPT-5.6
Sol**; BUILDER resumes at **commit 6**. Commits 1–5 are landed and were not re-planned.

Written after measuring on branch `feat/slice-83-writer-concurrency` @ `1aa7225` (head `0062`, database
`app_test`): re-running the locked OD-8 query with an added column-name and partial-predicate projection
(**120** rows / **88** tables, all 120 tuples captured); loading `tests/writer_inventory.py` and
`tests/writer_inventory_b.py` to enumerate the **168** leaves and the **112** Tier-A leaf→writer edges;
reading the writer source for **every** candidate mapping to a Tier-A leaf, including the three SQL
function bodies (`audit_append` via `migrations/versions/0003_audit_log.py:140-152`,
`slice55_finalize_decision` via `0054_control_loop_decisions.py:650-731`, `admin_write_autonomy_policy`
via `app/admin/policy_sql.py:58-127`); and measuring `wc -l` on all ten candidate A1 modules.

| Change | What changed in the document |
|---|---|
| Tier A subdivided by consequence, not reduced | New **§0A.1**: A1 derived-write / A2 independent-insert / A3 append-only, with B1 and B2 unchanged. 112 leaves before and after. |
| Evidence rule | New **§0A.2**: per leaf, the catalog constraint with key columns and partial predicate, plus the exact `file:line` of the read and of the derived value (A1) or the write site with "no prior-state derivation" (A2/A3). Adds the latest/aggregate-vs-in-call-counter discriminator, the two-step fail-closed ladder, and the **sibling-axis rule**. |
| A1 count reported prominently | New **§0A.3**: **A1 = 21** (~~v6: 20~~ — superseded by v7 defect 1), under the owner's 40-leaf halt threshold, with the exact leaf-id list and the per-leaf production-change column. |
| GREEN redefined per subtier | New **§0A.4**: A1 unchanged in substance; **A2 redefined** so an escaped `23505` is the correct observed behaviour; A3 asserts two distinct committed rows. Adds per-subtier mutation controls and the mandatory **only-wrong-axis** control. |
| §1a expanded to exactly the A1 modules | New **§0A.5** and **§1a-v6** *(renamed **§1a-v7**)*: **four** modules — `acceptance_verification.py`, `emergency_controls.py`, `go_live_decisions.py`, `production_approval_service.py` — plus the ten already landed. One mechanism for all four: serialize the derived read on an existing row with `FOR UPDATE` *(v7: that row is **`projects`**, via `lock_project_row`; the three child-row targets were struck as `42501`)*. No new module, exception, migration, or isolation change *(v7: three modules do add one import each)*. Three alternatives rejected. |
| Commit order re-locked from 6 | New **§0A.6**, with v5's rows 6–9 struck through in OD-9: 6 publishes subtiers, 7 lands the A1 fixes and ~~11~~ **9** barriers, 8 the remaining ~~9~~ **12** A1 barriers, 9–10 the A2 barriers *(**32** leaves)*, 11–13 the A3 barriers, 14 closes the inventory. `PENDING_TIER_A_BATCHES` still shrinks monotonically and must be empty at the end. |
| Per-leaf evidence externalised | New planner-owned `.planning/SLICE-83-LEAF-EVIDENCE.md` (396 lines) carrying all **168** leaves. Declared part of the plan contract; the builder mirrors its subtier column into `tests/writer_inventory_c.py` and may not edit it. |
| The owner's "likely A1" expectation checked, not assumed | **§0A.8**: of the eight registered leaves only `budgets` and `autonomy_policies` are A1; the other six are A2. All eight keep their nodes. The consequence — commit 4 hardened five A2 writers the amended rule would not authorize — is reported, the commits are not reverted, and the rule binds prospectively from commit 6. |
| Six new grounding facts | **§0.1.22-28**: the re-run OD-8 query with the eleven partial predicates; `audit_append`'s advisory lock `421`; `slice55_finalize_decision`'s project-row `FOR UPDATE`; the four genuinely unserialized derived reads; `lock_project_row` as the in-repo idiom; the ordinal/seq discriminator verified across all 17 axes; and measured file sizes. |
| Six named limitations added | **§0A.7**, including `admin_policy_changes_double_spend_raises_raw_sqlstate` (migration-frozen) and `emergency_controls_and_go_live_decisions_remain_over_the_500_line_cap` (already over the cap before this slice; the v5 modified-file cap rule is superseded for exactly those two files). |
| Claim lists and crux extended | Three claims added to §0.4, seven refusals to §0.5, a §0.3 addendum honesty crux, §5 gains the seven v6 confirmations, §8 gains constraints 0/0a/0b, and §7's commit-message list is replaced. |

Consecutive plan REJECT count: **unchanged** (v6 is an owner-ruled amendment, not a revision of a
rejected plan).

**v1.** First version. Written against `origin/main` `72ee544`, live Alembic head `0062` confirmed by
`uv run alembic heads`, after re-running the Appendix-B census scanner verbatim
(`DIRECT_WRITER_ENDPOINTS=119`, `CANDIDATE_WRITER_ENDPOINT_TOTAL=122`), querying the live
`app_test` @ `0062` catalog for collidable unique keys (`120` indexes over `88` tables) and runtime
grants on the six target tables, and reading `.planning/FINAL-AUDIT-REPORT.md` F-020 (`:744`), §4.6
(`:1230-1296`), §4.7 (`:1314`), Appendix B (`:1676-1913`), spec §23.2 (`:2168-2186`),
`tests/test_admin_policy_race_db.py`, `tests/admin_lock_support.py`, `tests/admin_support.py`, the six
writer implementations, the in-repo savepoint precedent
(`app/repositories/release_issues.py:98-110`, `app/repositories/go_live_decisions.py:446-465`), the
`ON CONFLICT DO NOTHING` precedent (`app/repositories/ops_signals.py:154-189,256-268`,
`app/repositories/export_bundles.py:209-249`), migrations `0007`/`0008`/`0014`/`0050`/`0060`,
`.planning/SLICE-84-PLAN.md` for structure, `CLAUDE.md`, and
`.planning/GO-LIVE-END-TO-END-ROADMAP.md:730-731,743`, `.github/workflows/ci.yml:55-68`, and
`tests/test_ecosystem_catalog_races.py`. **Thirteen** open decisions locked to Option A. Two baseline
corrections made before issue, both recorded as grounding facts rather than absorbed: the audit's
`1/122` is retained **audit-specific** pair coverage and unmapped concurrency tests already exist
(§0.1.13, OD-13, P-RED-7), and `app/repositories/catalog_adoptions.py` is already inside CI's pyright
path list so one of the six fixes is CI-gated (§0.1.14, §8.8b). The planner-seat substitution is
recorded in the header. Consecutive plan REJECT count: **0**.

**v2.** Sol REJECTed v1 (reviewer `8917813d-a58f-4e93-9e12-74564ca89190`); consecutive plan REJECT
count **1**. **All six defects accepted in full; none argued down, none partially absorbed.** Each was
re-verified against the live `app_test` @ `0062` or the source before being written in, and the
verification is recorded as a grounding fact rather than asserted in prose. No production code was
written — this remains a plan.

| Defect | What changed in the document |
|---|---|
| 1 — stale identity map on the budget upsert | New grounding fact §0.1.17 (the pre-write `self.get` seeds the identity map, so `session.get` is a map hit; and Core `onupdate` does not fire inside a `DO UPDATE` clause). OD-2 row 1 replaced with a fully locked snippet: `updated_at` in `set_`, `created_at` out of it, re-select with `populate_existing=True`; two alternatives explicitly rejected. New P-GREEN-1b sequential regression asserting returned **and** subsequently-read caps plus `updated_at`/`created_at`, and P-MUT-1b in both directions. §3.1, §5, §8.3a updated. |
| 2 — inventory could not hold a multi-key writer | OD-7 rewritten: `Candidate.leaf_ids` is one-to-many, `WriteLeaf` gains an explicit canonical `leaf_id` form, and a singular-plus-extras alternative is rejected. OD-8 gains the **index-coverage completeness** rule; OD-10 restated so dedup runs leaf-side while candidates fan out. Inventory test **5** added (§3.2) and P-MUT-10 requires **both** `agent_versions` axes. §0.3, §0.4, §8.5a updated. |
| 3 — `pg_index` query counted `INCLUDE` columns | New grounding fact §0.1.16 with both queries' live output, including Sol's `UNIQUE (code) INCLUDE (id)` mutation returning `0` on v1's query and `1` on the corrected one, and the note that the totals stay `120`/`88`. OD-8's SQL replaced with the `indnkeyatts`-bounded form, plus the PostgreSQL-16 array-subscript syntax warning. Inventory test **6** retains Sol's mutation permanently; P-MUT-11 added. §8.5b updated. |
| 4 — OD-3 / OD-5 contradiction | OD-3 rewritten as one explicit four-rung ladder table; OD-5 narrowed to supply only the terminal rung and to state what "bounded" means for the four single-key writers versus `register_version`. Rung 4 labelled fault-injected and unreachable by construction, with P-GREEN-3c and a matching refused claim. §0.3, §3.1, §8.4 updated. |
| 5 — over-broad `IntegrityError` catch | OD-4 rewritten with the narrowed handler, a named `_PROMOTION_CONFLICT_CONSTRAINTS` frozenset, and a per-constraint result table; everything not `23505`-on-those-two re-raises. P-RED-6 must now quote which constraint fires (as P-RED-3 does); P-GREEN-6c and P-MUT-12 added; the possibly-unreachable promote-once axis is handled honestly as a conditional limitation. §8.4a updated. |
| 6 — 500-line cap unaddressed for modified production files | New grounding fact §0.1.18 with measured `wc -l` for all six files and the exact external importers that constrain any split (Sol's `859`/`492` versus the measured `858`/`491` noted without arguing the defect down). New **§1a-split** section locking five split rules and the exact module breakdown: `cost_forecasts.py` 858 → four modules, `extraction.py` 491 → two. OD-9 extended to cover modified production files and to order the split commits first. §1a table gains a post-change line budget; §5 adds `wc -l` and identical-pass-count verification; P-MUT-13 proves the re-exports are load-bearing; §7 adds two `refactor(...)` commits; §8.9 rewritten. |

Also updated for consistency: §0.3 honesty crux (index coverage, the version ladder's fault-injected
rung, the budget's re-populated return and explicit `updated_at`, the `23505` narrowing, and the pure
splits), §0.4 (six new allowed claims), §0.5 (four new refused claims), §4.1's RED gate (nine
constraint determinations, and the split commits as the sole permitted earlier production change), and
§6's limitation list (four new names plus two conditional ones). **Thirteen** locked decisions remain
Option A — no OD was added; the six corrections tightened existing ones. Alembic head stays **`0062`**
and no defect forced a migration. Frozen files untouched; `can_go_live_autonomously` stays the literal
`False`; A5 `slice54.v1`; readiness `slice20.v1`.

**v3.** Sol REJECTed v2 (reviewer `85ddfaa0-8b87-4b72-8608-6f8c22c7fb57`); consecutive plan REJECT
count **2** — one more swaps the planner seat. **All four defects accepted in full; none argued down,
none partially absorbed.** Each was re-verified live before being written in. No production code was
written — this remains a plan, and `git status` shows only this file changed.

| Defect | What changed in the document |
|---|---|
| 1 — P-GREEN-1b unprovable because `now()` does not advance in one transaction | New grounding fact **§0.1.19** quoting the live `BEGIN; now(); pg_sleep; now()` transcript showing the identical timestamp and `clock_timestamp() <> now()`, plus the two consequences: two committed transactions are required, and `clock_timestamp()` must **not** be substituted into `set_` to dodge it. P-GREEN-1b re-locked to one `AsyncSession(rls_engine, expire_on_commit=False)` across two committed transactions with an **independent** confirming read, citing the existing in-repo committing-session convention (`tests/test_admin_policy_race_db.py:96-99`, `tests/test_agents.py:148`) and noting that `tests/conftest.py:125-154` rolls back and therefore cannot be used. New harness helper `two_committed_transactions(...)` (§1b); new constraint §8.3b; §0.3, §0.4, §5, §6 limitation `budget_updated_at_advance_proven_across_two_committed_transactions_only`. The fix mechanism itself is unchanged — the defect was in the probe. |
| 2 — one-to-many contradicted by four surviving "exactly one" statements; completeness enforced per table | All four sites rewritten (§0 lead, §0.2, §0.3, §6's correct-claim sentence) to "**one or more leaves; one tiered barrier per leaf**", and OD-10 gains a **Cardinality** paragraph declared to govern any apparent contradiction. Index completeness re-scoped to **per candidate** in OD-8, OD-7's narrative, inventory test 5, and §8.5a, with per-table retained as a weaker additional assertion. New **P-MUT-14** proves both halves: the per-candidate assertion fails while the per-table one still passes on the same mutation — i.e. the form v2 shipped would have missed it. §0.4 allowed claims updated; a new refused claim added. |
| 3 — "two-writer barrier suite" overstated Tiers B1/B2, and B2 never verified its FK claim | Renamed to a **tiered** barrier suite at every site (§0 lead with an explanatory paragraph, §0.2, §0.3, §1b's harness row now "Tier A's instrument", §6's correct claim and forbidden wording, §7's four batch commit subjects). New grounding fact **§0.1.20** showing live that a naive FK check matches `tenant_id`/`project_id` — which serialize nothing between two racers sharing a tenant — and that `agent_provided_skills.uq_aps_capability_skill` qualifies on a **migration-seeded** `skills` parent. OD-8's Tier B2 rewritten as five numbered conditions **B2-1…B2-5** with a validated `pg_constraint`/`pg_attrdef` query embedded verbatim (including the `attnum = ANY(pi.indkey::int2[])` cast that the `int[]` spellings get wrong), a **fail-closed reclassification to Tier A** on any catalog failure, and B2-5 stated as cited code rather than a catalog proof. New **inventory test 7** and **P-MUT-15** (four mutations, one per condition, including the `tenant_id` case v2 would have accepted). New constraint §8.5c; new limitations `barrier_suite_is_tiered_only_tier_a_executes_two_concurrent_writers` and `tier_b2_same_transaction_parent_creation_is_cited_code_not_a_catalog_proof`. |
| 4 — three-way commit-order contradiction and an incomplete `app/` manifest | **OD-9 now carries the single authoritative nine-row order table** — splits (1–2), RED (3), fixes (4), inventory (5), batches (6–9) — with the rationale for splits-first and two rejected alternatives; §7 and §4.1 mirror it verbatim and are labelled as mirrors; §8.1 restates it as a constraint. §3.2 test 1's impossible "update the inventory in the same commit as each split" instruction is **withdrawn** and replaced with the statement that the inventory is authored once at commit 5 against post-split paths; §3.3–3.6 adjusted to edits-not-creation. §4.1's gate now says "no **conflict-handling** line" and states plainly that RED is captured on the split tree rather than `72ee544` verbatim, with a stop-and-report if any signature differs. §1a's heading and closing line corrected to an exhaustive **ten-path** table (five modified, five created) including the four split modules and `app/concurrency.py`; §5 and §7 now require `git diff --name-only -- app/` and `git log --oneline` as evidence. |

Also updated for consistency: §0.5 gains four new refused claims (two-writer naming, B2's
same-transaction premise, exactly-one cardinality, same-transaction `updated_at`); §6's forbidden
wording bans "two-writer barrier suite", "exactly one" cardinality, and any claim that B2 proves
same-transaction parent creation; §5 gains Sol-v2-defect confirmations and a commit-order confirmation;
the header's v1 history rows 1 and 2 are annotated where v3 supersedes them rather than rewritten.
**Thirteen** locked decisions remain Option A — no OD was added; the four corrections tightened OD-7,
OD-8, OD-9, and OD-10. Alembic head stays **`0062`** and no defect forced a migration. Frozen files
untouched; `can_go_live_autonomously` stays the literal `False`; A5 `slice54.v1`; readiness
`slice20.v1`.

**v4.** Sol REJECTed the Opus-authored v3, producing the third consecutive plan REJECT and firing
the owner seat-swap rule. PLANNER = GPT-5.6 Sol; REVIEWER = Claude Opus; BUILDER after APPROVE =
Cursor Grok 4.6 Extra High. The swapped-pair reject counter resets to 0; three consecutive Opus
REJECTs of this Sol-authored line trigger the escalation-failure halt. All four v3 defects were
accepted in full:

| Defect | What changed in the document |
|---|---|
| 1 — tenant GUC missing from P-GREEN-1b's three transactions | Added grounding fact §0.1.21 with the live `<unset>`-after-commit transcript and existing test citations. Locked transaction-local `set_config(..., true)` inside txn 1, txn 2, and the independent read in the helper contract, §3.1, P-GREEN-1b, §8.3b, and P-MUT-1c. Session-level binding is forbidden. |
| 2 — B2-5 incorrectly stored per deduplicated leaf | Added `B2EdgeEvidence` / `B2_EDGE_EVIDENCE`, keyed by exact candidate identity plus leaf. Inventory test 7 enumerates every candidate→B2-leaf edge, verifies that candidate's citation and exact Tier-A parent leaf, and forces the whole shared leaf to Tier A if any edge fails. P-MUT-16 proves one candidate's citation cannot mask another's omission. |
| 3 — commit instructions still contradicted OD-9 | Replaced “Commit per writer” with one locked commit 4 for all six fixes; corrected OD-9 commit 5 to seven inventory tests. OD-9 remains the single authority. |
| 4 — unlocked promotion-error home and stale modified-file count | Locked `PromotionRefConflict` in `app/repositories/extraction_promotion.py` with a re-export from `app/repositories/extraction.py`; corrected the active manifest wording to five modified production files. |

No production code was written. This revision changes only `.planning/SLICE-83-PLAN.md`; Alembic
head remains `0062`, `can_go_live_autonomously` remains literal `False`, A5 remains `slice54.v1`,
and readiness remains `slice20.v1`.

**v5.** Claude Opus (`c6b5cbc0-d59e-4938-8cd7-0a289274749e`) REJECTed Sol's v4 with
`PLAN REJECT — Slice 83 v4`; post-swap consecutive REJECT count is **1**. PLANNER remains GPT-5.6
Sol (`85ddfaa0`); REVIEWER remains Claude Opus; two more consecutive Opus REJECTs halt the run.
All four defects were accepted in full:

| Defect | What changed in the document |
|---|---|
| 1 — commit 5 could not satisfy Tier-A node registration | **Historical v5 lock — superseded by v6 §0A.6.** Locked option (b): `PENDING_TIER_A_BATCHES`; complete inventory at commit 5; registered⊎pending test; v5 placed atomic removals with nodes in commits 6–9 and final-empty at commit 9. **Current schedule: pending removals in commits 7–13; final-empty at commit 14.** |
| 2 — `ConcurrentWriteUnresolved` base unlocked | Locked exactly `ConcurrentWriteUnresolved(Exception)`, one shared class outside all domain roots, with intended caller-visible non-catch behavior and exact-type GREEN assertions. |
| 3 — no SERIALIZABLE loser branch | Added per-leaf isolation/retryable SQLSTATEs, ruled `40001`/`40P01`, aborted-W2 rollback, explicit Slice-55 wrapper behavior, and P-MUT-18. `23505` remains forbidden. |
| 4 — drifted source citations | Re-measured and corrected budget `:199`, promotion `:296-401`, and forecast policy `:153-228`. |

Also locked the post-fix census distinction, the B1 `f"{table}.-"` leaf form, and commit 3
RED→commit 4 GREEN/mutation assertion replacement under OD-6. No production code was written; only
this plan file changed. Alembic remains `0062`; go-live remains literal `False`.

**v9.** **PLAN REJECT — Slice 83 v8.** Reviewer **GPT-5.6 Sol**, agent
`c7a97392-0a24-41a4-8d60-d8374f2b5e57`, 2026-08-25. This was the **third REJECT on the prior
Opus-authored amendment line** and fired the owner-ruled seat swap. PLANNER = GPT-5.6 Sol; REVIEWER =
Claude Opus, substituting for the owner-named Claude Fable 5. The swapped-pair reject counter resets
to **0**; three consecutive Opus REJECTs of this Sol-authored line halt. After PLAN APPROVE, BUILDER =
Cursor Grok 4.6 Extra High and REVIEWER = Sol for code. Both blockers were accepted in full, none
argued down; commits 1–5 remain landed and were not re-planned.

| Change | What changed in the document |
|---|---|
| **Blocker 1 — stale live counts removed** | §0A.1 and OD-8 now state **A1 = 21 / A2 = 38 / A3 = 53**; OD-9 commit 7 now owns **9 module-owned** leaves and commit 8 owns **12 barrier-alone** leaves including `run_checkpoint_writes`. Coverage remains **112**. |
| **Blocker 2 — live OD-9 schedule replaced** | The frozen OD-7 comment, OD-9 Option A and sequencing lock, inventory test 4, P-MUT-17, and the Opus-v4 confirmation now all use **fourteen commits**, pending removals in **7–13**, and final-empty at **14**. Commit 6 publishes subtiers and removes nothing. |
| **Historical schedule cells labelled** | The v5 correction row, v4 correction row, and v5 changelog row retain their then-current schedule only under an explicit **historical / superseded by v6 §0A.6** label. Struck quotations and defect-table descriptions of prior wrong text were not rewritten. |
| **Scope preserved** | No production code, tests, migrations, spec, audit report, or evidence file changed. Alembic remains `0062`; `can_go_live_autonomously` remains literal `False`; A5 remains `slice54.v1`; readiness remains `slice20.v1`. A1 = **21 ≤ 40**; coverage is not reduced; A is subdivided rather than dropped; no 83a/83b split is introduced. |
