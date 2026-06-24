# Slice 29 — Pull-request evidence connector — DISCUSSION

**Status:** DISCUSSION v2 — **COMPLETE. Q1–Q6 answered**; the two material design forks (D-29-5 link storage, D-29-6 gate wiring) are now ruled. Remaining D-29-x are mechanical/connector details with recommendations. Ready to draft `SLICE-29-PLAN.md`. No code until the PLAN is approved.
**Persona:** senior release-governance / connector-security / evidence-model architect.
**Baseline (verified this session):** `main` @ `9e23868` ("docs: mark Slice 28 merged (#46)"). Migration head **`0027`** (`0027_connector_verified_evidence.py`). No Slice-29 code exists yet (`app/release/pr_evidence.py`, `app/models/pull_request_record.py`, `app/repositories/pr_evidence.py` all absent — `ls` confirmed).
**Roadmap anchor:** `.planning/GO-LIVE-END-TO-END-ROADMAP.md:221-231` (Slice 29).

> **Provenance (Sanad).** Read this session: spec §2.2 (`docs/…v1_2.md:151-157`), §12.3 (`:1184-1207`, incl. line 1207 "Builder agents cannot move their own work to Done"), §12.4 (`:1209-1224`); roadmap `:221-231`; the `branch_protection_snapshots` model (`app/models/branch_protection_snapshot.py:1-97`) and gate-#3 ladder + gate list (`app/release/production_autonomy.py:240-281`). Migration head + Slice-29 file absence verified via `ls`/`git log`. The Slice-28 append-only DDL precedent (`migrations/versions/0025_ci_evidence.py:143-177`) is cited but re-verify exact lines before authoring `0028`.

## 0. Objective
Record pull requests with the §12.4 required contents (linked task, task contract, implementation summary, AC coverage, tests added, evidence links, known limitations, workarounds/fallbacks, security notes, rollback notes) + review approvals + merge-through-protected-branch facts as **`connector_verified`** evidence, captured as **immutable, latest-wins observation snapshots**. Feeds traceability (§15.2) and the issue/AC provenance that gates #7/#8 will later need; supports gate #3's required-reviews observation. **No A5 gate flips here** (roadmap `:229-230`).

## ⚠️ Corrections to carry into the PLAN (verified this session)
- **Migration number:** roadmap says `0027` (`:226`) but `0027` is already taken by Slice 28. **Slice 29 = `0028`.** (Downstream roadmap numbers `0028`/`0029`/… all shift +1; the roadmap was written assuming Slice 28 added no migration.)
- **Continuity gap (resolved):** the original Q1 enumeration was lost in a context reset and was never persisted; the prior window's claim that Q2 was "recorded in continuity memory" was false on disk. This file is the first persisted Slice-29 continuity artifact. Q1 is **recovered** from the user's Q4 cross-reference (see Q1 below), not fabricated.

---

## Binding decisions (Q1–Q4)

### Q1 — nature/lifecycle of PR evidence — **DECISION (recovered): external-provider observation, not UAID-owned lifecycle.**
> Recovered from the Q4 binding answer's own words: *"This is the physical persistence binding for the Q1 lifecycle decision: PR evidence is external provider truth observed over time."* Exact original Q1 wording is not on disk; this captures its substance.
- PR status / reviews / merge facts are **provider-owned observations**, recorded over time — UAID does not own the PR state transition. Therefore the evidence pattern is the Slice-26/28 connector-evidence precedent, **not** the Slice-22..25 UAID-owned mutable-lifecycle-record pattern. (Physically bound by Q4.)

### Q2 — connector_verified meaning, §12.4 contents, adequacy, traceability — **DECISION: Option A** (presence indicators + provider-fact verification). Muhasabah: pass.
- **Provider facts** (`connector_verified` = fetched from the provider API, not asserted): PR state; merged flag/time; merge-commit SHA; base/head branch + SHA; review states/counts; requested reviewers; required-check status; protected-branch merge evidence.
- **§12.4 contents:** record only **structured presence flags**, never prose/body/diff, and **never semantic adequacy**.
- **Adequacy: explicitly deferred.** Roadmap forbids claiming "review approval == acceptance verification" (`:229-230`; that is Slice 46). Spec §12.4 (`:1209-1224`) lists required PR contents but defines **no** deterministic adequacy scoring.
- **Caller-only vs connector-derived checklist:** allow **both**, labeled separately, both structural-only:
  - `caller_declared` — caller asserts the §12.4 item is present.
  - `connector_observed_template` — connector sees a strict machine-readable PR-template checklist/marker.
  - **Never** infer adequacy, parse free prose semantically, or treat a checked box as accepted truth.
  - Each §12.4 flag carries at least: `present` (bool); `source` (`caller_declared` | `connector_observed_template`); optional `observed_marker` (bounded enum/key, **not** copied prose).
  - Even on a `connector_verified` snapshot, §12.4 flags mean **presence observed/declared**, not "content verified adequate."
- **Traceability targets:** prefer typed, internal, same-project links — `release_issues` links (issue/blocker traceability), canonical intake-artifact links (AC coverage); provider refs (PR number, commit SHA, merge-commit SHA, check-run/status refs). **Avoid** free-form URLs as trusted evidence; if accepted at all, store as **bounded untrusted references**, never gate-grade proof.
- **Rejected:** B (storing structured *content* drifts toward PR-body/diff storage + semantic extraction without an LLM/strict parser); C (deferring §12.4 under-delivers the roadmap's explicit Slice-29 goal, `:221-231`).

### Q3 — separation-of-duties / no-self-approval — **DECISION: Option 1/A** (record facts + descriptive flags). Muhasabah: pass (with caveat).
Record provider identities and derive structural-only separation-of-duties flags, with **no refusal, no hard finding, no gate effect, no ruleset bump**.
- **Provider facts (when available):** `author_principal`; `approver_principals` (review state = approving); `reviewer_principals` (identities + review states, full context); `requested_reviewer_principals` (requested reviewers/teams); `merger_principal`; `approval_count` (derived count of approving reviewers).
- **Structural-only derived flags:** `self_approval_observed` (`author_principal` appears in approving reviewers); `self_merge_observed` (`author_principal == merger_principal`); `review_separation_observed` (optional — ≥1 approving reviewer differs from author).
- **Semantics:** connector-verified = identity facts from the provider API; structural-only = equality over provider identities; **not enforcement** (no rejection / write-suppression / issue creation / gate change); **not adequacy**. Enforcement deferred to later acceptance-verification / release-gate slices. Honesty: **observed ≠ enforced** (cf. Slice 28's "observed ≠ asserted").
- **Grounding:** §2.2 (`:151-157`); §12.3 (`:1184-1207`, line 1207); roadmap `:221-231`.
- **⚠️ Honesty caveat (recorded):** the flags compare **provider-principal equality** (same GitHub identity authored *and* approved/merged). They are **NOT** a verified UAID-agent-vs-reviewer separation — mapping a provider principal to a UAID actor identity (Slice 27) is **out of scope for Slice 29**.
- **Rejected:** "raw identities only" (leaves the §2.2 relationship uncomputed though facts are present); "self-merge as hard finding" (overclaims enforcement Slice 29 must not assert; Slice 46).

### Q4 — persistence model — **DECISION: Option 1** (immutable snapshots, latest-wins). Muhasabah: pass.
The physical binding of the Q1 lifecycle decision: PR evidence is external provider truth observed over time ⇒ Slice-26/28 evidence pattern, not the Slice-22..25 lifecycle-record pattern.
- **Table:** `pull_request_evidence_snapshots`.
- **Physical identity:** `id` per observation. **Logical identity:** `(tenant_id, project_id, provider, repo_ref, pr_number)`.
- **Ordering / latest-wins:** `created_at DESC, id DESC` (use `clock_timestamp()` default like `branch_protection_snapshots`, `branch_protection_snapshot.py:93-96`).
- **Runtime grants:** SELECT, INSERT only. **Mutation guard:** block UPDATE/DELETE/TRUNCATE (cf. `0025:143-177`).
- **RLS/FK:** tenant-owned, RLS ENABLE+FORCE + `tenant_isolation`; composite FK `(project_id, tenant_id) → projects`.
- **Provenance:** two-tier axis `caller_supplied_unverified` | `connector_verified` (same model as `branch_protection_snapshot.py:46-48,88-90`).
- **Trusted A5 context:** the latest **`connector_verified`** snapshot only.
- **No gate flip:** Slice 29 records context/provenance feed only; **no A5 status change**.
- **Rejected:** mutable lifecycle + events (right only when UAID owns the transition — `release_issue.py`/`release_candidate.py`; PR facts are provider-owned, so `branch_protection_snapshot.py` is the precedent); hybrid (complexity without a Slice-29 need; latest-wins over indexed snapshots suffices, roadmap `:221-231`).

---

## 3. The snapshot model (design from Q1–Q4)
One immutable row per **observation** of a PR. Columns (provider facts + structured presence + identity facts + derived flags + bounded refs):
- **Identity/binding:** `id`, `tenant_id`, `project_id`, `provider` (`github`), `repo_ref` (owner/repo slug + token denylist, reuse `ck_bps_repo_ref_slug` + `ck_bps_repo_ref_not_tokenish`), `pr_number` (int > 0).
- **Provider PR facts (Q2):** `pr_state` (enum: open/closed/merged), `merged` (bool), `merged_at` (nullable), `merge_commit_sha` (nullable, hex-bounded), `base_branch`, `base_sha`, `head_branch`, `head_sha`, `review_approval_count` (int ≥ 0), `requested_reviewer_count` (int ≥ 0), `required_check_summary` (bounded — e.g. counts/states, **no** prose), `merged_via_protected_branch` (bool).
- **§12.4 presence (Q2):** a bounded JSON object keyed by the 10 §12.4 items (`linked_task_or_issue`, `task_contract`, `implementation_summary`, `acceptance_criteria_coverage`, `tests_added`, `evidence_links`, `known_limitations`, `workarounds_fallbacks`, `security_notes`, `rollback_notes`), each value `{present: bool, source: caller_declared|connector_observed_template, observed_marker?: bounded-enum}`. **No body/prose/diff.**
- **Identity facts (Q3):** `author_principal`, `approver_principals[]`, `reviewer_principals[]` (+ states), `requested_reviewer_principals[]`, `merger_principal`, `approval_count`.
- **Derived structural flags (Q3, computed at write time, frozen with the immutable row):** `self_approval_observed`, `self_merge_observed`, `review_separation_observed`.
- **Traceability refs (Q2 + Q5):** `traceability_refs JSONB NOT NULL DEFAULT '{}'` — bounded, typed, **app-validated at write time**: same-project `release_issue_ids[]` + canonical `acceptance_criterion_ids[]`; provider refs (`pr_number`, `commit_sha`, `merge_commit_sha`, check/status refs). **Refs only — no prose/body/diff.** No FK table this slice; same-project validation is write-time; refs are part of the immutable row (corrections ⇒ a new snapshot).
- **Provenance/freshness:** `provenance` (two-tier), `observed_at` (nullable; connector sets it), `created_at` (`clock_timestamp()`).

## 4. Security boundaries (carried from Slice 28's verified pattern)
- **Repo binding:** evidence is for the **project's own declared repo** (`existing_assets_and_repositories`), never a caller-supplied `repo_ref` (D-29-3). A caller-supplied **`pr_number`** against the bound repo is acceptable (it is not a secret and is repo-scoped) — but `repo_ref` itself is never a broker/param input.
- **Param minimization:** `repo_ref` never enters `broker_call` params / `tool_calls.params` / audit — only safe params (`provider`, `pr_number`, `repo_ref_present`). (cf. Slice 28 B2.)
- **Credential containment:** operator env `GITHUB_CONNECTOR_TOKEN`, fail-closed empty, never persisted/audited/in params (LLM-key pattern).
- **Authority containment:** the connector calls a **read-only** tool (`source_control.read_pull_request`, mapping to the existing low-privilege read action `read_source_control_config`); broker stays **decision-only**; the connector executes only on an ALLOWED decision.
- **Provenance integrity:** `connector_verified` is **app-stamped on the connector path only**; the DB guard widens the allowed value but cannot itself attest authenticity (documented caveat, same as Slices 26/28).
- **Honesty:** observed ≠ enforced (Q3); presence ≠ adequacy (Q2); a failed/partial fetch ⇒ **no verified snapshot** (never a fabricated "verified-off").
- **Audit:** safe metadata only — ids/provider/pr_number/state/flags — **never** PR body/diff/title/check-names/URLs/principals' tokens.

## 5. Open decisions remaining (recommendations; coordinator rules at PLAN approval)
- **D-29-1 Connector source:** GitHub only (REST: `GET /repos/{owner}/{repo}/pulls/{n}`, `…/reviews`, `…/requested_reviewers`, merge fields). *(rec: yes — mirror Slice 28.)*
- **D-29-2 Broker path:** new read-only contract `source_control.read_pull_request` → existing `read_source_control_config` action; connector executes only on ALLOW; broker decision-only. *(rec: yes — no new authority.)*
- **D-29-3 Repo binding:** repo resolved from the project's own `existing_assets_and_repositories`; **no caller `repo_ref`**; `pr_number` may be caller-supplied against the bound repo. *(rec: yes.)*
- **D-29-4 Freshness for A5 context:** reuse `CI_EVIDENCE_MAX_AGE_HOURS` (24h) for "latest connector_verified" context. *(rec: yes; confirm window.)*
- **D-29-5 Traceability link storage shape — RULED Q5=Option 1:** bounded JSON `traceability_refs JSONB NOT NULL DEFAULT '{}'` on the snapshot — typed, same-project, app-validated at write time; same-project `release_issue_ids[]` + `acceptance_criterion_ids[]` + provider refs (PR number / commit SHA / merge-commit SHA / check refs); **refs only, no prose/body/diff**; **no FK binding table** this slice (FK-normalized graph deferred to a later slice if queries demand); refs are part of the immutable row (corrections ⇒ new snapshot). Rationale: Slice 29 = PR-evidence capture + traceability *feed*, not a normalized graph; a separate FK table adds lifecycle/mutation questions that conflict with Q4's immutable latest-wins model.
- **D-29-6 Gate wiring — RULED Q6=Option 1: store-only.** **Do NOT edit `production_autonomy.py`; ruleset stays `slice28.v1`.** No PR-evidence counts/context in the A5 report; no change to gate statuses, `passed_gate_count`, `a5_satisfied`, or go-live reasons. PR-evidence context lands with the first **consuming** gate slice, not here. Rationale: wiring read-only context now would change A5 report semantics with no consuming gate and invite overclaiming despite "no gate flips."
- **D-29-7 Trigger surface:** admin/internal connector method; **no** new HTTP write endpoint. A read-only `GET …/pull_request_evidence` (latest-or-null) is optional. *(rec: connector method only this slice; defer/decide the read endpoint.)*
- **D-29-8 Flag derivation timing:** derive Q3 flags at **write time** and freeze them in the immutable row (deterministic from fetched facts). *(rec: write-time — matches the immutable-snapshot model.)*

## 6. Tests (planned)
Pure (snapshot validators: provider/provenance, repo_ref slug+token denylist, pr_number, §12.4 presence-object shape, identity-list bounds; Q3 flag derivation truth table; caller path cannot assert `connector_verified`); repository (connector-verified write stamps `connector_verified`, latest-wins ordering, caller path stamps unverified); DB-guard (direct SQL: append-only UPDATE/DELETE/TRUNCATE blocked; bad provider/repo_ref/token rejected; FK cross-project/tenant rejected); broker path (FakeSCMConnector only — no network; connector executes only on ALLOW; deny ⇒ no write); identity/flags (self-approval/self-merge/separation derived correctly; no enforcement side-effect); RLS + cross-tenant (no leak); **no-secret audit** (token/body/diff/URLs/check-names never in audit or `tool_calls` params). `make test` + fresh `make test-db` + alembic round-trip.

## 7. Non-goals
No go-live; **no A5 gate flips** (`can_go_live_autonomously` stays false). No acceptance-verification / adequacy scoring (Slice 46). No enforcement of §2.2/§12.3 (descriptive flags only). No PR-body/diff/prose storage; no semantic parsing; no LLM. No multi-provider framework (GitHub-only). No new write HTTP API beyond an optional latest-or-null read. No real network in tests.

## 8. Must NOT claim
- That review approval == acceptance verification (Slice 46).
- That any A5 gate flips in Slice 29.
- That `connector_verified` attests §12.4 content **adequacy** (it attests presence/provider-facts only).
- That the structural self-approval flags are §2.2 **enforcement** or a verified UAID-agent-vs-reviewer separation (they are provider-principal equality, observed only).
- That `connector_verified` is DB-attested authenticity — it is app-enforced (connector path is the sole writer).
