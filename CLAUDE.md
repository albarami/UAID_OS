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

## Current status (2026-07-02)
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
compute/persist on GET, no migration/LLM/R4-R5 — merged via PR #23 (commit `eb19b4c`).** **Slice 18
lifts the readiness auditor cap R3→R4: R4 = R3 base + the two §4.3 "tools" categories declared
(`integrations_and_external_systems`, `tool_access_manifest`) + zero spine gaps (full
requirement→AC→oracle coverage); secrets stay an R5 concern; go-live stays false; staging is
monotonic; `ruleset_version="slice18.v1"`; no migration — merged via PR #25 (commit `f69da00`).**
**Slice 19 adds read-only `GET /api/projects/{id}/{readiness,findings}/history` — the full persisted
snapshot list (newest-first) via `repo.history`; empty/cross-tenant/nonexistent return `200` + `[]`;
read-only, no pagination, no migration/LLM (closes the Slice 17 D-17-2 history deferral) — merged
via PR #27 (commit `0b40c91`).**
**Slice 20 lifts the readiness auditor cap R4→R5: R5 = R4 base + ALL declarable categories declared
(incl. the two new presence-only declarable gates `human_approval_policy` + `production_authority`)
+ the two engine gates (valid `autonomy_policies` row + positive `budgets` cap) = intake-package
completeness. `can_go_live_autonomously` stays false (A5/Appendix-B is separate); migration `0020`
expands the `intake_categories` CHECK to 22 categories; `ruleset_version="slice20.v1"` — merged via PR #29 (commit `74f45ce`).**
**Slice 21 adds a fail-closed, NON-AUTHORIZING A5 production-autonomy evaluator skeleton
(`app/release/production_autonomy.py`) + read-only `GET /api/projects/{id}/production_autonomy`:
scores the 13 Appendix-B gates — only gate #1 (R5 intake) can pass; #2/#8/#9/#12 are
`insufficient_evidence` (partial context only); the other 8 are `no_evidence_source:<subsystem>`.
`a5_satisfied` and `can_go_live_autonomously` are ALWAYS false; compute-on-read (no table, no
migration, no persistence); `ruleset_version="slice21.v1"` — merged via PR #31 (commit `7ad1b45`).**
**Slice 22 adds a deterministic, tenant-owned risk-acceptance record store (`risk_acceptance_records`
+ append-only `risk_acceptance_events`, migration `0021`, §24.1/§27.10) — the first real A5 evidence
source: required fields incl. `expiry_date`, hard-refusal categories rejected (§24.1), signer
`approver_provenance="caller_supplied_unverified"`, lifecycle active→{expired,revoked,superseded},
no DELETE, only `status`/`updated_at` mutable. Wires a CONSERVATIVE A5 gate-#7 hook
(`production_autonomy` `ruleset_version` bumped to `slice22.v1`, `GateResult.context` added): gate #7
moves `no_evidence_source` → `insufficient_evidence:no_open_issue_store` with
`context.active_risk_acceptance_count` — never passes (no issue store yet); go-live stays false — merged via PR #33 (commit `4ea38cc`).**
**Slice 23 adds a deterministic, tenant-owned security/shortcut release-findings store
(`release_findings` + append-only `release_finding_events`, migration `0022`, §13.4/§916-920) — the
next real A5 evidence source: `finding_type ∈ {security,shortcut}`, §13.4/§920 categories, DB-guarded
one-way lifecycle (open→resolved|false_positive|accepted|superseded), **critical findings can never
be accepted**, non-critical acceptance requires a usable `risk_acceptance_records` link (active +
non-expired + non-blocking + same tenant/project + `issue_id==finding.id`). Wires the conservative A5
gates #5/#6 (`production_autonomy` `ruleset_version` bumped to `slice23.v1`): both move
`no_evidence_source` → `insufficient_evidence:no_finding_provenance_or_scan_source` with open/critical
finding counts as context — never pass (no scan coverage); go-live stays false — merged via PR #35 (commit `da7ac4e`).**
**Slice 24 adds a deterministic, tenant-owned open-issue/blocker store (`release_issues` +
append-only `release_issue_events`, migration `0023`, §24.1/§24.2/Appendix B #7) — the fourth real A5
evidence source, giving the Slice-22 risk-acceptance `issue_id` a real referent: a 10-value
`issue_category` gate-axis taxonomy (`security`/`shortcut`/`test_or_acceptance`/`cost`/`deployment`/
`rollback`/`monitoring`/`evidence`/`approval`/`other`, `other`⇒summary+detail), `blocking` boolean
axis, **`critical`⇒`blocking`** (refused at the pure validator AND the DB-guard INSERT), DB-guarded
one-way lifecycle (open→{resolved,accepted,superseded}; no `false_positive`), **hard blockers
(critical OR a hard-refusal `blocking_category`) can never be accepted**, acceptance requires a usable
`risk_acceptance_records` link (active + non-expired + non-blocking + same tenant/project +
`issue_id==issue.id`); RLS ENABLE+FORCE, no DELETE, audit safe-metadata only. Wires the conservative
A5 gate #7 (`production_autonomy` `ruleset_version` bumped to `slice24.v1`): gate #7 moves
`insufficient_evidence:no_open_issue_store` → `insufficient_evidence:no_issue_provenance_or_release_binding`
with open-issue counts (`open_issue_count`/`open_blocking_issue_count`/
`open_unaccepted_blocking_issue_count`) + `active_risk_acceptance_count` as context — never passes (no
issue provenance/release binding); go-live stays false — merged via PR #37 (commit `7a2ae44`).**
**Slice 25 adds a deterministic, tenant-owned release-candidate / release-binding store
(`release_candidates` + append-only `release_candidate_events` + append-only, freeze-locked
`release_candidate_issue_bindings`, migration `0024`, §24.1/§24.2/Appendix B #7) — the *release-binding*
half of A5 gate #7, creating the **future** referent namespace for Slice-22
`risk_acceptance_records.release_id` (not yet FK'd/validated). One-way lifecycle
draft→frozen→{superseded,canceled} (`frozen_at` set iff entering frozen; identity immutable;
same-status no-op); **issue-only** bindings addable only while `draft` (freeze-locks membership) with
same-project enforcement, no unbind; additive FK Option A (no `release_issues` mutation —
`release_candidates` carries `UNIQUE(id,tenant_id)` [event FK] + `UNIQUE(id,project_id,tenant_id)`
[binding FK]); RLS ENABLE+FORCE, no DELETE, DB-guard backstop, audit safe-metadata only. Wires the
conservative A5 gate #7 (`production_autonomy` `ruleset_version` bumped to `slice25.v1`): the reason
narrows `no_issue_provenance_or_release_binding` → `no_issue_provenance` when a frozen release
candidate exists (release-binding half satisfied), with frozen/bound-issue counts as context — still
`insufficient_evidence`, **never passes** (no issue provenance/completeness); binding declares KNOWN
issues, not completeness; go-live stays false — merged via PR #39 (commit `f706a30`).**
**Slice 26 adds a deterministic, tenant-owned source-control / CI evidence-provenance store
(`branch_protection_snapshots`, migration `0025`, Appendix B #3 / §26.3) — the first evidence class for
A5 gate #3: immutable append-only snapshots (RLS, SELECT/INSERT only) with a two-tier `provenance` axis
(`caller_supplied_unverified` writable; `connector_verified` schema-reserved but **unwritable** this
slice), a `repo_ref` owner/repo-slug + GitHub-token-prefix-denylist DB backstop, and a JSON-array
`required_status_checks` guard. Wires the conservative A5 gate #3 (`production_autonomy`
`ruleset_version` bumped to `slice26.v1`): gate #3 moves `no_evidence_source` → `insufficient_evidence`
(reason narrows `no_branch_protection_evidence` → `branch_protection_observed_unverified` once a
snapshot exists), with snapshot/verified-count context — **never passes** (only unverified evidence is
writable; the PASS path lands with the real connector, Slice 28). Adds `GET
/api/projects/{id}/ci_evidence` (latest-or-null). merged via PR #41 (commit `dc622a09`).**
**Slice 27 adds request-authentication → verified actor identity (`app/identity.py`, migration `0026`,
§2.2/§5.2/§7.x/§23.4): a bearer key now binds a verified **principal** (`tenant_api_keys.principal_subject`
+ `actor_type`); the D4 resolver returns `(tenant_id, principal_subject, actor_type)` (DROP+recreate,
least-privilege model intact); `require_tenant` returns a `TenantContext` carrying an
`AuthenticatedActor`. A new **app-stamped** `request_authenticated` provenance tier
(**key-custody-based, NOT a human signature**) lands on approvals (new `requested_by_provenance` +
resolver-only `approver_provenance`, both CHECK-constrained) with a §2.2 verified self-approval refusal,
and on risk-acceptance under **actor-bound** signer semantics (the verified principal must equal the
payload `approver` AND appear in `accepted_by`, else refused). Flips **NO** A5 gate (#7/#12/#13 stay
unmet; go-live stays false); broker unwired (D-27-4). merged via PR #43 (commit `372e15b`).**
**Slice 28 makes A5 gate #3 PASS-capable: a GitHub-first, broker-mediated source-control connector
(`app/release/scm_connector.py` [SCMConnector protocol + FakeSCMConnector + shipped-but-untested
GitHubSCMConnector + pure `map_github_branch_protection`], `app/release/ci_evidence_service.py`
orchestration, `app/release/project_repo.py` shared resolver, migration `0027`, App. B #3). The connector
resolves the project's OWN declared repo (`existing_assets_and_repositories`) + credential source
(`secrets_and_credentials_manifest`) — **never a caller `repo_ref`** — calls `broker_call` for the
read-only `source_control.read_branch_protection` tool (maps to the new A1 read action
`read_source_control_config`; broker stays **decision-only**) with **safe params only**
(`provider`/`branch`/`repo_ref_present`, never `repo_ref`), and on a clean GitHub **200** writes a
`connector_verified` snapshot via `record_connector_verified_branch_protection` (the verified tier,
unlocked by `0027`'s guard relax — app-stamped on the connector path only). Gate #3 (`production_autonomy`
`ruleset_version` → `slice28.v1`) evaluates the latest snapshot **for the CURRENTLY declared repo/branch**
(`latest_branch_protection_for_repo`, B1-cont) via a latest-wins ladder — `branch_protection_repo_unbound`
→ `no_branch_protection_evidence` → `branch_protection_observed_unverified` → `branch_protection_evidence_stale`
→ `branch_protection_insufficient` → **`passed`** (verified + protection-enabled + PR-reviews + ≥1 required
check + fresh within `CI_EVIDENCE_MAX_AGE_HOURS`=24). Gate #3 is the **first non-#1 gate that can PASS**;
`a5_satisfied` + `can_go_live_autonomously` stay false (≥11 gates unmet). 403/404/non-200/timeout/malformed
⇒ no write (fail-closed, never a "verified-off" snapshot); token is operator env-only (`GITHUB_CONNECTOR_TOKEN`),
never stored/audited/in broker params; the report exposes `branch_protection_repo_bound` (bool), never the
raw `repo_ref`. merged via PR #45 (commit `6de94de`).**
**Slice 29 adds a deterministic, tenant-owned pull-request evidence connector (`app/release/pr_evidence.py`
[pure validators + `normalize_approvals` + `derive_separation_flags`], `app/release/scm_connector.py`
[extended with `fetch_pull_request` + pure `map_github_pull_request`], `app/release/pr_evidence_service.py`
orchestration, `app/models/pull_request_evidence_snapshot.py`, `app/repositories/pr_evidence.py`,
migration `0028`, §12.3/§12.4; App. B #7/#8 provenance feed) — immutable, append-only, latest-wins
`pull_request_evidence_snapshots` (Slice-26/28 evidence pattern, two-tier provenance). Records PR provider
facts + §12.4 **presence** flags (`caller_declared`|`connector_observed_template`, presence not adequacy)
+ **observed** `check_status_summary` (nullable, NOT required-check satisfaction) + normalized
review/identity facts + **structural-only** separation flags (`self_approval_observed`/`self_merge_observed`/
`review_separation_observed` — provider-principal equality, NOT a verified UAID-actor separation, no
enforcement) + an **observed** `merged_to_declared_protected_branch_observed` (cross-refs verified+fresh
branch-protection evidence; never overclaims) + repository-validated `traceability_refs` (same-project
`release_issues` + `kind='acceptance_criterion'` artifacts; dup/missing/wrong-kind/wrong-project fail
closed). The broker-gated, repo-bound connector resolves the project's OWN declared repo (shared
`resolve_declared_repo`, never a caller `repo_ref`), calls `broker_call` for the read-only
`source_control.read_pull_request` tool (new A1 read action `read_pull_requests`; broker stays
decision-only) with **safe params only** (`provider`/`pr_number`/`repo_ref_present`, never `repo_ref`); PR
+ reviews endpoints are **fail-closed** (failure ⇒ no snapshot), requested-reviewers is **observed**
(`requested_reviewers_observed`), checks are optional observed-only. DB guard enforces JSON shapes +
`approval_count = jsonb_array_length(approver_principals)` + the nullable check-summary shape (B-29-8,
mirrors `0025`). **Store-only — `production_autonomy.py` UNTOUCHED, ruleset stays `slice28.v1`, NO A5 gate
flip / status change; go-live stays false.** Token is operator env-only (`GITHUB_CONNECTOR_TOKEN`), never
stored/audited/in params; audit is safe-metadata only (never repo_ref/principals/traceability UUIDs/body).
merged via PR #47 (commit `52a4b958`).**
**Slice 30 makes A5 gate #2 PASS-capable: a deterministic, tenant-owned deployment-target verification
store + a broker-gated, SSRF-safe, read-only `generic_https` connector (`app/release/deploy_evidence.py`
[pure validators + `map_https_probe` + SSRF guard `validate_target_host`/`assert_safe_resolved_ips` +
the `target_available=(provisioned AND reachable)` invariant], `app/release/deploy_connector.py`
[DeployTargetConnector protocol + FakeDeployTargetConnector + shipped-but-untested
GenericHttpsDeployTargetConnector], `app/release/deploy_evidence_service.py` orchestration,
`app/models/deployment_target_snapshot.py`, `app/repositories/deployments.py`,
`resolve_declared_production_target` in `app/release/project_repo.py`, migration `0029`, App. B #2 /
§5.2 / §26.3). The connector resolves the project's OWN declared production target
(`environments.production.domain` from `environments_and_deployment_targets`, file 16 — **never a caller
target**), `broker_call`s the read-only `deployment.read_target_status` tool (new A1 read action
`read_deployment_target`; broker stays decision-only) with **safe params only** (no domain), runs the
**SSRF guard** (HTTPS+FQDN-only, deny IP-literal/localhost/.local/private/loopback/link-local/multicast/
reserved/cloud-metadata, DNS-resolve-then-pin) **before any socket**, then `GET https://{domain}/` (path
`/`, 5.0s, redirects off, no creds; `provisioned = 200–399 ∪ {401,403}`). Per **B-30-9** it writes a
`connector_verified` snapshot for **every safely-attempted outcome** (positive when serving, verified-NEGATIVE
when non-serving or transport-fail) so latest-wins gate #2 can't keep a stale passing snapshot; **no write**
only for target-unbound / SSRF-reject / broker-deny. Immutable append-only `deployment_target_snapshots`
(RLS; SELECT/INSERT only; the `target_available=(provisioned AND reachable)` invariant + FQDN/enum CHECKs
are the DB backstop — no guard trigger needed). Gate #2 (`production_autonomy.py` `ruleset_version` →
`slice30.v1`) evaluates the latest snapshot **for the CURRENTLY declared target** via a latest-wins ladder
(`no_environment_declaration` → `environments_declared_but_no_target_evidence` →
`deployment_target_observed_unverified` → `deployment_target_evidence_stale` → `deployment_target_unavailable`
→ **`passed`** [verified + available + fresh within `DEPLOYMENT_EVIDENCE_MAX_AGE_HOURS`=24]). Gate #2 is the
**first non-#1/#3 gate that can PASS**; `a5_satisfied` + `can_go_live_autonomously` stay false (≥10 gates
unmet). **ONLY gate #2 changes** (a no-other-gate-regression test guards the rest); production deploy stays
A4/A5 human/pre-approved (`spec:485`) — the connector never deploys. No secret/credential used or stored;
audit + broker params never carry the domain/target_ref. The live `generic_https` connector pins the
connection to the **validated resolved IP** (IPv6 bracketed) with `Host`/TLS-SNI = the hostname
(anti-rebind), streams **status-only** (no response body read), and normalizes DNS failures to a
fail-closed SSRF refusal. merged via PR #49 (commit `200c460`).**
**Slice 31 makes A5 gate #11 PASS-capable: a deterministic, tenant-owned monitoring/alerts
verification connector (`app/release/monitoring_evidence.py` [pure validators + read-state honesty model +
`parse_and_validate_status_url` + bounded JSON `parse_monitoring_body` + observation builders],
`app/release/monitoring_connector.py` [`MonitoringConnector` protocol + `FakeMonitoringConnector` +
shipped-but-untested `GenericMonitoringApiConnector` + `_default_http_probe`],
`app/release/monitoring_evidence_service.py` orchestration, `app/repositories/monitoring_evidence.py`,
`resolve_declared_monitoring_target` in `project_repo.py`, model `monitoring_status_snapshots`, migration
`0030`, App. B #11 / §26.3/§26.6). The connector resolves the project's OWN declared monitoring
`status_url` (`operations_observability_support` file 22 — `data.monitoring.{provider,status_url}`,
validated HTTPS/no-userinfo-query-fragment/port-443/SSRF-safe-FQDN-host/normalized-bounded-path; **never a
caller URL**), calls `broker_call` for the read-only `monitoring.read_status` tool (new A1 action
`read_monitoring_status`; broker decision-only) with **safe params only** (`provider`/`monitoring_present`,
never the URL), performs a **connect-time-pinned** (`https://{validated_ip}{normalized_path}`, Host/SNI=
hostname, IPv6 bracketed, never logged/persisted — B10), **unauthenticated** (no `Authorization`/credential
— B9), **bounded** (≤64 KiB, counts-only, no names) JSON read, and writes a `connector_verified`
`monitoring_status_snapshots` row for **every safely-attempted outcome** (B-30-9). **Read-state honesty
(B4/B6) is DB-enforced:** a failed/malformed read is NOT "0 monitors / 0 alerts" — `response_valid=False` +
a `failure_kind ∈ {unreachable,http_error,content_type,oversize,malformed}` + **NULL** counts; a valid read
requires 200 + non-null counts (`0..32767`, B7) + consistent active-booleans. Gate #11
(`production_autonomy` `ruleset_version` → `slice31.v1`) evaluates the latest snapshot **for the CURRENTLY
declared `status_url`** (B2) via a latest-wins ladder — `no_monitoring_declaration` →
`monitoring_declared_but_no_evidence` → `monitoring_observed_unverified` → `monitoring_evidence_stale` →
`monitoring_evidence_unreadable` (a verified+fresh but unreadable provider — **never "inactive"**, B4) →
`monitoring_or_alerts_inactive` → **`passed`** (verified + valid-read + `overall_active` + fresh within
`MONITORING_EVIDENCE_MAX_AGE_HOURS`=24). Gate #11 is the **4th** PASS-capable gate (#1/#2/#3/#11); only
gate #11 changed (no-other-gate-regression test); `a5_satisfied` + `can_go_live_autonomously` stay false
(≥9 gates unmet). Unauthenticated-only this slice (authenticated providers + operator-controlled
credential-audience allowlist deferred); SSRF guard reused verbatim from Slice 30. The bounded read is
cap-enforced **before** accumulation (a chunk that would exceed the 64 KiB read cap is never retained) with
an explicit transport chunk size (B11). merged via PR #51 (commit `e77bf7a`).**
**Slice 32 adds a deterministic, tenant-owned secrets-reference verifier (`app/release/secrets_verification.py`
[pure validators + honesty outcome model + bounded manager/reference-name shapes + `build_env_outcome`],
`app/release/secrets_connector.py` [`SecretsManagerConnector` protocol + `FakeSecretsManagerConnector` +
local `EnvSecretsManagerConnector`], `app/release/secrets_verification_service.py` orchestration,
`app/repositories/secrets_verification.py`, `resolve_declared_secret_references` in `project_repo.py`,
model `secret_reference_checks`, migration `0031`, R5 App. A l.2968 / §26.3 / spec:1094) — the "secrets
available" evidence class for R5 + gate #2 deploy-readiness. The broker-gated verifier resolves the
project's OWN declared `secrets_and_credentials_manifest` references (**canonical persisted shape only** —
`{manager, reference_name}` or `{references:[…]}`; template-YAML normalization out of scope, B5), calls
`broker_call` for the read-only `secrets.verify_reference` tool (new A1 action `verify_secret_reference`,
distinct from the mutating mandatory-approval `change_secrets`) with **safe params** (`{manager,
reference_present:true}` — the key is `reference_present`, NOT `secret_present`, which the sanitizer would
redact, B3), and writes a `connector_verified` `secret_reference_checks` row per reference recording **only**
`(manager, reference_name, outcome, resolved)`. **ZERO secret-value leakage (B4/B6):** no value is
stored/logged/audited/persisted/returned/bound — the schema has **no value column** (structural), and the
`env` connector inspects the value transiently in-process **only** to compute non-emptiness
(`bool((os.environ.get(name) or "").strip())`) then discards it. **Honesty (B1/B2):** `outcome ∈
{resolved, not_found, unsupported_manager, probe_error}` with DB-enforced `resolved=(outcome='resolved')`;
`manager` is bounded safe text with the DB rule `manager<>'env' ⟹ unsupported_manager+unresolved` (a
non-`env` manager is honestly unsupported, never "missing"); `reference_name` is a bounded shape that
ACCEPTS legit names like `prod/db_password`/`app/api_key` (no value denylist on the name). `env`-only this
slice (local; no network/SSRF; Vault/cloud + operator credential-audience allowlist deferred). **Store-only
— `production_autonomy.py`/`readiness.py` UNTOUCHED, `ruleset_version` stays `slice31.v1`** (a `before==after`
regression proves recording evidence flips no gate/readiness); go-live false. Immutable append-only
`secret_reference_checks` (RLS ENABLE+FORCE; SELECT/INSERT only; migration `0031`; Postgres regex
`{m,n}` caps at 255, so `reference_name` uses a char-class shape + a separate `char_length BETWEEN 1 AND
256`). merged via PR #53 (commit `214495c`).**
**Slice 33 adds a communication / approval channel (`app/approvals/channels/routing.py` [pure tier-only
router + notification validators], `app/approvals/channels/adapter.py` [`ApprovalChannel` protocol +
`FakeChannel` + `DashboardChannel`], `app/approvals/channels/service.py` [`ApprovalNotificationService` +
the authoritative `request_and_notify_approval`], `app/repositories/approval_notifications.py`, model
`approval_notifications`, migration `0032`, §18.2 / §26.3) — wiring the Slice-4 approval engine to a human
surface. The **tier-only** router (D-33-1; **no `human_approval_policy` read** this slice) routes `{low,
medium} → digest`, `{high, production} → realtime`; `digest` is a routing **label** only (D-33-7 — no
scheduler / `daily_digest_time` builder). The one authoritative `request_and_notify_approval` calls
`ApprovalRepository.request` (**UNTOUCHED**) then `ApprovalNotificationService.notify_for_approval`, writing
**both** an `approval_events` and an immutable append-only `approval_notifications` row via the channel
(`dashboard` only — no external I/O, surfaced by the existing read API; slack/teams/email/ticketing
deferred). Records **only** routing facts `(approval_id, risk_tier, routing_mode, channel, status)` —
**NO recipient/URL/credential column** (no secret material, structural). Migration `0032` also adds the
**additive** `UNIQUE(id, project_id, tenant_id)` on `approvals` (Slice-6/14b pattern) so the composite FK
`(approval_id, project_id, tenant_id) → approvals` **DB-proves** project/tenant consistency. Verified-
identity approvals are **reused from Slice 27** (on the resolution, not added here). **Store/infra-only —
`production_autonomy.py`/`readiness.py` UNTOUCHED, ruleset stays `slice31.v1`** (gate #12's verified
approvals complete in Slice 53); a `before==after` + an `is_blocked`-unchanged no-regression test guard it;
go-live false. A channel ack is **never** an approval / production pre-approval. merged via PR #55 (commit `e436668`).**
**Slice 34 adds a project-management / issue-tracker connector (`app/release/pm_issues.py` [pure validators +
`map_board_column` Jira-status→§12.3-column + shapes], `app/release/pm_connector.py` [`IssueTrackerConnector`
protocol + `FakeIssueTrackerConnector`; live Jira adapter **deferred**], `app/release/pm_sync_service.py`
[`sync_pm_issues`], `app/repositories/pm_issues.py`, `resolve_declared_pm_project` + `has_declared_jira_credential`
in `project_repo.py`, model `pm_issue_mappings`, migration `0033`, §12.3 / §26.3) — reflecting external **Jira**
PM issues into the platform, **mapping-only** (Slice 24 `release_issues` reuse where applicable). The broker-gated
connector resolves the project's OWN declared `tool_access_manifest.jira` `{project_key, instance_key}` (file 18;
`instance_key` = an operator alias, **never a URL/host**) + the reference-only `JIRA_CONNECTOR_TOKEN` credential,
calls `broker_call` for the read-only `pm.read_issues` tool (new A1 action `read_project_management_issues`,
distinct from the mutating `pm.create_issue`) with **safe params** (`provider`/`project_present`, never the
project/instance key), and writes a `connector_verified` `pm_issue_mappings` row per item recording **only**
observed facts `(external_ref, external_status, board_column, title_present)`. **No secret material / no
title-text** — the schema has **no title/description/credential/`release_issue_id` column** (structural).
Jira-status → §12.3 `board_column` via `map_board_column`; an unknown status ⇒ **`unmapped`** (honest fail-closed,
never guessed; raw `external_status` kept). **`connector_verified` = OBSERVATION-verified, NOT issue-provenance-
complete** (gate #7 adequacy is not provided — a synced issue is never provenance-verified-complete, Slice 47).
Idempotent **latest-wins** keyed by `(tenant, project, external_system, instance_key, external_ref)`; a malformed
observation is **skipped** (never aborts the sync). **STORE/INFRA-ONLY — creates NO `release_issues`;
`release_issues`/`production_autonomy.py`/`readiness.py` UNTOUCHED, ruleset stays `slice31.v1`** (a `before==after`
regression guards it); read-only (never writes back to Jira); go-live false. Migration `0033` additive; immutable
append-only `pm_issue_mappings` (RLS ENABLE+FORCE; SELECT/INSERT only). merged via PR #57 (commit `d65b98c`).**
**Slice 35 adds a deterministic-gated, LLM-assisted, human-reviewed document classifier + source/authority
mapping (`app/intake/classifier.py` [pure: the §6.1 16-value `DOCUMENT_TYPES` enum incl. the `unknown`
fail-closed sentinel, 4-tier `AUTHORITY_TIERS`, untrusted-data `CLASSIFY_SYSTEM_PROMPT`,
`parse_classification`→`ClassificationDraft` with OOV→`unknown` normalization, `validate_review_transition`],
`app/repositories/classification.py` [`ClassificationRepository.classify` + `review_classification` +
`latest_for_document`/`list_for_project`], model `document_classifications`, migration `0034`,
§6.1/§6.2/§16.3/§26.2) — the §6.2 pipeline **steps 1–2**, closing the §26.2 "document classifier" (Track B,
**off the A5 critical path**). The classifier is an **LLM call** (Slice-14a inert-proposal model — **NO tool
broker**), reusing the Slice-9 sandbox (`scan` injection-refuse, `as_untrusted_block`, `DocumentRepository`) +
Slice-14a cost/budget/evidence helpers. `classify` resolves an **accepted** document → injection hard-refuse
before any model call (§16.3; no call/no cost) → projected-cost budget preflight (deny-by-default) → FakeLLM
call (live `AnthropicClient` shipped-untested) → fail-closed token accounting → **incurred-cost metering on any
valid-token response BEFORE parse/evidence** (a later parse/non-verbatim-evidence failure still records the
`model_inference` cost — the `outcome='failed'` row keeps `cost_external_ref`+tokens) → strict-JSON parse →
verbatim-evidence verify → persists one **inert** row (`outcome ∈ {succeeded, refused_injection,
blocked_by_budget, failed}`); on success a proposed `(document_type, authority_tier, bounded verbatim
evidence_quote)` awaiting a **distinct-reviewer (§2.2)** `pending→approved|rejected` decision. **Authority tier
= the authority axis only** (`authoritative`/`supporting`/`informational`/`unknown`, per-tier criteria) — **NOT**
the full §3.4 source-reliability score, no conflict resolution. `document_classifications` is tenant-owned, RLS
ENABLE+FORCE; SELECT/INSERT/UPDATE, **no DELETE/TRUNCATE**; a DB guard enforces accepted-doc pinning +
shape-by-outcome (incl. the failed-cost duality) + content/identity immutability + the one-way review lifecycle.
The stored `evidence_quote` is a **bounded verbatim excerpt** (audit/logs never carry it; **no "no-secret"
guarantee** — no denylist this slice). **STORE/INFRA-ONLY — `production_autonomy.py`/`readiness.py` UNTOUCHED,
ruleset stays `slice31.v1`** (a `before==after` + readiness-level-unchanged regression guards it); a
classification is inert + **never authoritative / auto-promoted**; go-live false. Migration `0034` additive;
the `document_classifications` guard mirrors the Slice-14a `extraction_proposals` pattern. merged via PR #59 (commit `006ea7e`).**
**Slice 36 adds a deterministic-gated, LLM-assisted canonical-artifact generator under §7 spec-authorship
independence (`app/intake/generator.py` [pure: §6.3 15-value `ARTIFACT_TYPES` (a REQUESTED target, NO
`unknown` — validated up front), the §7.2 6-value `AUTHORSHIP_STATUSES`, the narrowed §7.3 `APPROVAL_BASES`
(`human_owner`/`independent_agent_lineage`; `domain_authority`+`reference_oracle` DEFERRED+fail-closed-refused),
`validate_independence`/`validate_authorship_transition`/`parse_generated_artifact`], `app/repositories/generator.py`
[`GeneratedArtifactRepository.generate` + `request_artifact_approval` + `review_artifact` + `authorship_marking`
+ reads], model `generated_artifacts`, migration `0035`, §6.3/§6.5/§7/§26.2) — closing the §26.2 "canonical
artifact generator" (Track B, **off the A5 critical path**). The generator is an **LLM call** (Slice-35 inert
model — **NO tool broker**) reusing the Slice-35 injection-safe/budget-gated/incurred-cost pipeline. `generate`
validates the **requested** `artifact_type` first → resolves an **accepted same-project** document (Slice-35
wrong-project gate) → injection hard-refuse → budget preflight → FakeLLM (live adapter shipped-untested) →
fail-closed token accounting → **incurred-cost metering BEFORE parse** (parse failure keeps cost — B2) →
persists one **inert, NON-BINDING** §6.3 draft (`outcome ∈ {succeeded,refused_injection,blocked_by_budget,failed}`)
stamped **`system_authored_unapproved`** (§7.2) with the generator lineage (§7.4). `review_artifact` applies the
**§7.3 independence rules**: the approver must be **distinct from the generator**; `human_owner` needs
`reviewer_authority`; `independent_agent_lineage` needs a `reviewer_prompt_family` **distinct from the
generator's** + role + authority; the deferred bases are refused; one-way `system_authored_unapproved →
{*_approved, disputed}`. **`*_approved` is independence-evidence-recorded, NOT verified** (actor labels
caller-supplied-unverified). `authorship_marking` recovers the §7.4 marking; `request_artifact_approval` opens a
subject-scoped (`generated_artifact:<id>`) approval. `generated_artifacts` is tenant-owned, RLS ENABLE+FORCE;
SELECT/INSERT/UPDATE, **no DELETE/TRUNCATE**; a DB guard enforces accepted-doc pinning + shape-by-outcome (incl.
the failed-cost duality) + INSERT-only `system_authored_unapproved` + content/identity/generator-lineage
immutability + the §7.3 authorship guard (deferred bases forbidden by the `approval_basis` CHECK + guard). Stored
`title`/`body` **may contain source-derived sensitive material** (audit/logs never carry it; **no no-secret
guarantee** — B5). **STRICTLY STORE/INFRA-ONLY (B2) — NO spine write, NO promotion: `production_autonomy.py`/
`readiness.py` UNTOUCHED, bit-stable** (a `before==after` + readiness-level-unchanged + `intake_artifacts`-count-
unchanged regression guards it); a generated artifact is **never binding before independent approval** (§7.1) and
**never enters the spine** this slice (approved-AC → spine `acceptance_criterion` promotion via the reused
`add_artifact` is a deferred follow-up); go-live false. Migration `0035` additive; the `generated_artifacts` guard
mirrors the Slice-35 `document_classifications` pattern. merged via PR #61 (commit `03f73b9`).**
**Slice 37 adds a deterministic-gated, LLM-assisted, DESCRIPTIVE-ONLY semantic contradiction detector
(`app/intake/semantic_contradictions.py` [pure: the §6.4 **8**-value `CONFLICT_TYPES` (NO `unclassified` — B3),
`OUTCOMES` incl. the no-call `skipped_insufficient_input` (B1), concrete bounds (B5), untrusted-data
`DETECT_SYSTEM_PROMPT` (no-resolution, §6.4), `format_artifacts`→**opaque per-prompt item keys** 1:1 to artifacts
(B8 — a bare `ref` is not unique across kinds), `parse_contradictions`→`ContradictionDraft`, `keep_valid` (drop
OOV-type/same-item/unknown-key/empty-desc, resolve keys→artifacts, truncate, cap)], `app/repositories/semantic_contradictions.py`
[`SemanticContradictionRepository.detect` + `latest`/`history`/`contradictions_for`], models
`semantic_contradiction_reports` (run snapshot) + `semantic_contradictions` (pairwise), migration `0036`,
§6.4/§16.5/§14.4/§26.2) — **ADVANCES** (does not close) the §26.2 contradiction detector with the spine-level
semantic half (document-level §6.4 + the Slice-13 STRUCTURAL detector stay separate/deferred). `detect` mirrors the
Slice-35/36 LLM pipeline (T1 app-minted report id keys the cost; T2 deterministic `(kind,ref,id)` artifact order +
`MAX_ANALYZED_ARTIFACTS` cap; **`<2` ⇒ `skipped_insufficient_input`** no-call/no-cost; injection refuse; budget
preflight; **incurred-cost BEFORE parse** (B2); `keep_valid` resolves opaque item keys → FK-backed artifacts) and
persists one report + one `semantic_contradictions` row per kept pair in one txn. **Provenance is DB-PROVEN (B4):**
each contradiction pins `artifact_a_id`/`artifact_b_id` via **composite-FK to `intake_artifacts`** (existence) +
`CHECK a<>b` (distinctness); a BEFORE-INSERT **kind guard** proves both are `requirement`/`acceptance_criterion`
(B7); `contradiction_count` is DB-bound to the child rows by **report-side AND child-side DEFERRABLE count-match
triggers** (B6/B9 — a late child insert is rejected). **NO auto-resolution / no proposed-resolution** (§6.4 "must not
silently choose one"). **STORE/INFRA-ONLY — `production_autonomy.py`/`readiness.py` UNTOUCHED, ruleset stays
`slice31.v1`** (a `before==after` bit-stable regression + no-readiness-side-effect guard it); audit safe-metadata only
(counts/per-`conflict_type` counts — never `description`/artifact content); FakeLLM only; go-live false. Migration
`0036` purely additive (two new tables; artifact FKs reuse the existing `intake_artifacts` UNIQUE); immutable
append-only (RLS ENABLE+FORCE; SELECT/INSERT only). merged via PR #63 (commit `98a47ed`).**
**Slice 38 adds a deterministic, Postgres-only Skill Matching Engine (`app/agents/skills.py` [pure: the §8.2
27-skill catalog, the §8.3 **VERBATIM** transparent score `capability_match*0.30 + domain_fit*0.15 +
tool_access_fit*0.15 + eval_performance*0.20 + reviewer_availability*0.10 + cost_latency_fit*0.10 −
risk_penalty` with a full per-component `ScoreBreakdown`, bounds/regexes (B6), `build_squad`→the §8.4 squad
manifest + per-(work-unit, agent) match records], `app/repositories/skills.py` [**admin-path**
`register_skill`/`register_capability` (admin session) + runtime `capability_view` + tenant
`SquadRepository.build_and_record`/`latest`/`history`/`matches_for`], models `squad_manifests` +
`skill_matches`, migration `0037`, §8/§26.4) — the **Phase-4 entry**, reusing the Slice-6 blueprint registry.
**5 additive tables:** GLOBAL `skills` (migration-seeded with the §8.2 27 categories) + `agent_skill_capabilities`
(append-only latest-wins) + `agent_provided_skills` (`skill_id` **FK→`skills`** — unknown keys cannot persist, B3)
— **`uaid_app` SELECT-only, admin-written** (B8, cf. Slice-6 `0007:231-232`), immutable append-only (B7); TENANT
`squad_manifests` (§8.4 snapshot) + `skill_matches` (the **persisted §8.3 breakdown**, B2) — RLS ENABLE+FORCE,
append-only, bounded CHECKs (B6: regex/enum/jsonb-array/0..1 components/manifest octet_length). The §8.3 high-risk
reliability rule zeroes `cost_latency` for high-risk work. **HONESTY: `eval_performance` (0.20) has no source until
archetype evals (Slice 40) → neutralized to `0.0` (`eval_source='absent_until_slice40'`, NEVER fabricated);
work-units are DECLARED inputs (task contracts = Slice 42) — so a score is a transparent RANKING AID, NOT a
qualification/authorization.** No distinct capable reviewer ⇒ `reviewer_availability=0` + `missing_skills:reviewer:<skill>`
+ a factory request (never self-review §2.2, B5). **STORE/INFRA-ONLY — `production_autonomy.py`/`readiness.py`
UNTOUCHED, ruleset stays `slice31.v1`, bit-stable; flips NO A5 gate** (foundational — supplies the Phase-5 staffing);
deterministic (no LLM), Postgres-only (no Neo4j/graph DB); go-live false. Migration `0037` purely additive (5 new
tables; reuses `agent_blueprints`). merged via PR #65 (commit `ae3ea90`).**
**Slice 39 adds agent realization + factory workflow + the broker↔instance wiring (`app/agents/factory.py`
[pure: `QUALIFICATION_STATUSES`, `validate_realization_request` — fail-closed non-empty + **KNOWN-tool**
(`get_contract`, lazy import to dodge the `app.tools` package cycle) bounded `tool_allowlist` +
`reviewer_blueprint_ids`], `app/repositories/agent_realizations.py` [`AgentRealizationRepository.realize` +
`for_instance`/`for_project`/`reviewers_of`], `app/models/agent_realization.py` [`AgentRealization` +
`AgentRealizationReviewer`], migration `0038`, §9.1-9.4/§26.4) — the §9.4 **bind+register** half (steps 5-7
eval/dry-qualify/QA = Slice 40). The **tenant-only** factory (B1 — **NO global registry writes**;
blueprint/version registration stays an admin-path precondition) realizes an **already-registered**
`version_id` into a Slice-6 instance (reusing `instantiate`) + an **instance-scoped** tool allowlist
(`agent_tool_allowlist` keyed by `str(instance.id)`) + FK-backed reviewers (the DB self-review guard resolves
the **ACTUAL** blueprint via `instance→version`, §2.2/B3 — no denormalized blueprint) + an inert
`agent_realizations` record stamped **`unqualified`** (B4 — the only INSERT-able value; the `qualified`
transition is Slice 40). The tool broker splits into **two fail-closed entry points** sharing one pipeline:
**`broker_call`** (the AGENT path — resolves a real **SAME-PROJECT** instance [`DENIED_UNKNOWN_AGENT` on
free-string / cross-project / unknown / inactive, B7] then the **always-firing** qualification gate
[`DENIED_UNQUALIFIED_AGENT`; qualification is Slice 40] before allowlist/policy/approval) and
**`broker_call_service`** (the PLATFORM-SERVICE path — the **6 release connectors** [ci/deploy/secrets/pr/
monitoring/pm], `service_id` is a service identity not an agent; **skips** the agent identity+qualification
gates, **keeps** sanitize→known-tool→allowlist→policy→approval). `ToolCall._DECISIONS` +
`ck_tool_calls_decision_valid` 7→9 (B2); `agent_instances` gains additive `UNIQUE(id,project,tenant)` (B6).
**Honesty: every realization is `unqualified` ⇒ the agent qualification gate ALWAYS denies ⇒ NO new tool
authority is unlocked** (success stays `ALLOWED_UNVERIFIED_IDENTITY`; Slice-27 approval still unwired).
**STORE/INFRA-ONLY — `production_autonomy.py`/`readiness.py` UNTOUCHED, ruleset stays `slice31.v1`,
bit-stable; flips NO A5 gate**; go-live false. Migration `0038` additive; `agent_realizations` +
`agent_realization_reviewers` are tenant-owned, RLS ENABLE+FORCE, **SELECT/INSERT-only** (`uaid_app` has no
UPDATE/DELETE grant — the privilege layer, distinct from the append-only triggers). merged via PR #67 (commit `9ea4f90`).**
**Slice 40 makes the broker's AGENT path PASS-capable via an agent qualification eval — the
`unqualified→qualified` transition (`app/agents/qualification.py` [pure: `derive_counts`/`coverage_complete`/
`expected_verdict` mirroring the DB GENERATED verdict + `validate_case_results`], `app/repositories/
qualification.py` [`QualificationRepository.record_qualification_run`/`request_qualification_approvals`/
`qualify`], `app/models/archetype_eval.py` + `app/models/qualification_run.py`, migration `0039`, §9.4
step 6-7/§9.5.1/§26.4) — the §9.4 step-6/7 GATE over **recorded** dry-test evidence (step-5 project case
generation + LIVE dry tests deferred — no agent execution). **Honesty crux: agent execution doesn't exist,
so the eval is DETERMINISTIC SCORING over recorded cases with `caller_supplied_unverified` provenance + a
DB-DERIVED verdict that cannot be faked; qualifying lets the broker agent path REACH allowlist/policy/
approval (which still decide) but unlocks NO execution (success stays `ALLOWED_UNVERIFIED_IDENTITY`).** A
**global, migration-seeded** `archetype_evals` library (the 11 §9.5.1 archetypes — `min_aggregate_score` +
zero-critical + required categories; `uaid_app` **SELECT-only** trust-zone; immutable append-only) is the
controlled asset. A `qualification_run` (tenant, RLS, immutable; + FK `qualification_case_results`) records
cases; `aggregate_score`/`verdict` are **`GENERATED ALWAYS … STORED`** and `total_cases`/`passed_cases`/
`critical_failure_count`/`coverage_complete` are **deferred-trigger-verified against the children**, while a
**BEFORE-INSERT snapshot guard** pins the snapshot columns to the referenced `archetype_evals` row AND the
eval archetype to the realization's ACTUAL blueprint (`instance→version→blueprint`) — so direct SQL can't
fake a `passed` by weakening the threshold/categories or using a wrong-archetype eval. `qualify` performs
the one-way transition (migration `0039` `CREATE OR REPLACE`s the `0038` `agent_realizations` block trigger
to allow only `unqualified→qualified` with a **passing-run backstop** + a column-level UPDATE grant) **only**
on a passing run **and** two distinct **run-scoped** sign-offs (`qualify_agent_qa` + `qualify_agent_security`,
the `run_id` in the subject ref — an approval can never satisfy a different run). **No broker change**
(`broker.py` already PASSes when `qualified`); a test proves the agent path now reaches downstream
(`DENIED_UNQUALIFIED_AGENT` → `DENIED_NOT_ALLOWLISTED` → `ALLOWED_UNVERIFIED_IDENTITY`). **STORE/INFRA-ONLY
— `production_autonomy.py`/`readiness.py` UNTOUCHED, bit-stable** (`before==after`); not an Appendix-B gate;
go-live false. Migration `0039` additive; deterministic (no LLM, no agent run). merged via PR #69 (commit `4bba0a0`).**
**Slice 41 adds the §9.6 agent replacement / failure-policy layer — an append-only store of REPORTED
failure events + a deterministic prescription + retry-cap DECISION (`app/agents/failure_policy.py` [pure:
the 8-value §9.6 `FAILURE_PATTERNS`→`RESPONSES` `PRESCRIPTION` table (spec:936-945), `SEVERITIES`,
`SOURCE_PROVENANCES=('caller_supplied_unverified',)`, `MAX_FAILURE_ATTEMPTS=3` (OD-4), B3 text bounds
(source≤100/evidence_ref≤200/summary≤2000/detail≤8000/reported_by≤200 — non-BLANK after strip, not merely
non-empty), fail-closed `validate_failure_event`, `prescribe`, the `effective_response` ladder (`none` →
safety-immediate `suspend_and_audit` [D-41-6] → `escalate_or_blocker` on cap-or-`persistent_inability`
[D-41-5] → else the §9.6 prescription), frozen `ReplacementDecision` (`ruleset_version="slice41.v1"`)],
`app/models/agent_failure_event.py`, `app/repositories/agent_failures.py`, migration `0040`,
§9.6/§9.5.1/§9.7/§26.4). **Honesty crux (B2): no diagnosis/classifier exists — the failure pattern is
caller-REPORTED and fail-closed-VALIDATED, never inferred (Sanad/B1: required `source` origin label +
`source_provenance` DB-CHECK-locked to `caller_supplied_unverified`); §9.6's responses need unbuilt
subsystems, so Slice 41 EXECUTES NOTHING — every prescribed response (incl. `suspend_and_audit`) is a
recorded RECOMMENDATION, "must not retry forever" is enforced AS A DECISION (`escalate_or_blocker`), and
there is NO auto-suspend (OD-1).** `agent_failure_events` is tenant-owned, RLS ENABLE+FORCE, **immutable
append-only** (SELECT/INSERT only — block triggers + no UPDATE/DELETE grant), **per-INSTANCE** (OD-2/§9.7
— a requalified agent = new version→new instance→fresh budget) via the composite FK
`(instance_id, project_id, tenant_id)→agent_instances` (the Slice-39 UNIQUE target), with 8-pattern +
4-severity + provenance-lock CHECKs and **bounded + non-blank `char_length`/`btrim` CHECKs on every user
text field** (whitespace-only provenance refused at the DB too; the btrim set = the Python `str.strip()`
whitespace set). `record_failure` derives `project_id` from the resolved same-tenant instance (never
caller input) and audits **safe metadata only** (never `summary`/`detail`/`evidence_ref`);
`evaluate_replacement` is **compute-on-read** (OD-3 — no decisions table, the events ARE the audit trail;
a nonexistent/cross-tenant instance yields the generic no-failure decision — no existence oracle).
**STORE/INFRA-ONLY — `production_autonomy.py`/`readiness.py` UNTOUCHED, the A5 ruleset stays
`slice31.v1`, bit-stable (`before==after` + instance status untouched); flips NO A5 gate**; no LLM, no
HTTP endpoint, no qualification auto-ingest (OD-5/OD-6); go-live false. Migration `0040` purely additive
(one table). merged via PR #71 (commit `626e57f`).**
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
three §4.3 technical categories are declared** (Slice 16), **R4 when the two §4.3 "tools"
categories are declared and the spine has full requirement→AC→oracle coverage** (Slice 18),
emitting the §4.5 validation report as an immutable `readiness_reports` snapshot
(Phase 2, Slices 12 + 16 + 18)**,
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
only) (Phase 2, Slice 15)**, **and the Slice 16 R3 + Slice 18 R4 + Slice 20 R5 readiness rules that
consume those declarations (R2 → R3 on the declared §4.3 technical trio; R3 → R4 on the two declared
§4.3 "tools" categories + zero spine gaps; R4 → R5 on all declarable categories declared + the
autonomy & cost engine gates; staging = R3/R4/R5 AND environments declared; go-live stays false even
at R5) — capping the auditor at R5**.
The rest of the engine described in the spec
(**semantic** contradiction analysis, **A5 / Appendix-B production autonomy** (the go-live authority
gate) + the gated autonomy/approval/cost/production-authority **engines** themselves, agent factory,
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
  (`/api/projects/{id}/{runs,approvals,blockers,cost,readiness,findings}` + the Slice 19
  `readiness/history` & `findings/history` + the Slice 21 `production_autonomy`) that open `tenant_scope`
  and read via existing repos — a cross-tenant `project_id` yields nothing (RLS). **Slice 17** added
  `readiness`/`findings`: each returns the **latest persisted snapshot** via `repo.latest`
  (read-only SELECT) or `null` — never-evaluated, cross-tenant, and nonexistent `project_id` are
  indistinguishable (`200` + `null`, no existence oracle); a GET never computes or persists.
  **Slice 19** added `…/readiness/history` & `…/findings/history`: the full snapshot list
  (newest-first, same per-element shape) via `repo.history`; empty/cross-tenant/nonexistent all
  return `200` + `[]` (no leak, no pagination this slice). **Slice 21** added `…/production_autonomy`:
  the fail-closed A5 report computed on read (no persistence); always `a5_satisfied:false` +
  `can_go_live_autonomously:false`; cross-tenant/nonexistent yield a generic not-satisfied report
  (no leak). `app/repositories/api_keys.py`:
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
  `actor` is an **untrusted** caller label (autonomy-policy writes are not wired to Slice 27 identity)).
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
  auditor (Phase 2, Slice 12 base + **Slice 16 R3** + **Slice 18 R4** + **Slice 20 R5**, §4.3/§4.4/§4.5).
  `readiness.py` (pure, **no LLM**): `evaluate_readiness` reads a snapshot of spine artifacts **plus
  the Slice‑15 declared intake categories** (`CategoryDeclarationView(category, status)`) and emits the
  §4.5 report, **fail-closed and capped at R5**. Ladder: R0 = no requirements; R1 = no valid
  requirement→acceptance chain; R2 = ≥1 valid chain; **R3 = R2 base PLUS the three §4.3 technical
  categories declared** (`architecture_and_technology_constraints`, `data_model_and_contracts`,
  `user_journeys_and_workflows`); **R4 = R3 base PLUS the two §4.3 "tools" categories declared
  (`integrations_and_external_systems`, `tool_access_manifest`) PLUS zero `spine_gaps`** (secrets
  excluded as an R5 concern); **R5 = R4 base PLUS ALL declarable categories declared (incl. the two
  presence-only gates `human_approval_policy` + `production_authority`, reference-only secrets) PLUS
  the two engine gates — a present+valid `autonomy_policies` row and a `budgets` row with
  `max_total_cost_usd > 0`** (intake-package completeness). Category rules check the presence of a
  provenance-backed declaration, not content quality. **Parent-kind validation does not trust the DB
  FK alone** — an acceptance criterion counts only if its parent is a `requirement`, an oracle only if
  its parent is that `acceptance_criterion`; orphan/wrong-kind links become `spine_gaps` and never
  raise the level. **`can_build_to_staging` is true at R3/R4/R5 AND when
  `environments_and_deployment_targets` is declared** (monotonic); **`can_go_live_autonomously` is
  ALWAYS false — even at R5** — because go-live needs A5/Appendix-B authority (not evaluated) and
  `production_authority` is presence-only, never an authorization. The `report` carries the §4.5 keys
  + deterministic extensions (`readiness_cap`, `readiness_cap_reason`, `not_assessed_categories`
  [**empty at R5** — the whole universe is assessed], `spine_gaps`, **`missing_r3_categories`**,
  **`missing_r4_categories`**, **`missing_r4_test_coverage`**, **`missing_r5_categories`**,
  **`missing_r5_gates`** [`autonomy_policy_absent_or_invalid` / `cost_budget_absent_or_zero`],
  `production_authority_decision`, `ruleset_version="slice20.v1"`); `missing_for_go_live` also lists
  `r3_/r4_/r5_category_not_declared:<category>` and `r5_gate_incomplete:<gate>`. `ReadinessRepository`
  (`evaluate`/`evaluate_and_record`/`latest`/`history`) reads the Slice‑15 declarations (D‑6: a
  doc-backed declaration counts only if its source document is still `accepted` — drops a
  later-quarantined source; same-project is enforced upstream by the `intake_categories` FK, with
  a defense-in-depth check in the repo), computes the **R5 engine gates** (autonomy: row exists AND
  `validate_overrides` passes — validity, not mere existence, NOT inferred from `decision_for`; cost:
  budget with positive cap),
  wires the **Slice‑3** autonomy policy via `decision_for(project_id, "deploy_production")` as
  **transparent context only** (mandatory-approval ⇒ `needs_approval`/`deny`, never authorization;
  never makes go-live true), and audits **safe metadata only — no assumption titles / report body**.
  `app/models/readiness_report.py` (`ReadinessReportRecord`, table `readiness_reports`): **tenant-owned,
  RLS, append-only**; `readiness_level` CHECK allows R0..R5; the code now emits
  R0/R1/R2/R3/R4/R5; `created_at` uses `clock_timestamp()` so same-transaction snapshots order
  deterministically (`latest`/`history` order `created_at DESC, id DESC`). The latest snapshot is
  read-only exposed at `GET /api/projects/{id}/readiness` (Slice 17) + `…/readiness/history`
  (Slice 19). **Skeleton: deterministic only — no LLM, no evidence pack, no new artifact kinds;
  A5 / Appendix-B production autonomy (the go-live authority gate) is out of scope — go-live stays
  false even at R5. Slice 20 adds migration `0020` (the `intake_categories` CHECK now allows 22
  categories); no new table/engine.**
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
  analysis, no LLM, no evidence pack, no new artifact kinds.** Latest + history snapshots are read-only
  exposed at `GET /api/projects/{id}/findings` + `…/findings/history` (Slices 17/19).
- `app/release/production_autonomy.py` + `app/repositories/production_autonomy.py` — **fail-closed,
  non-authorizing A5 production-autonomy evaluator skeleton** (Phase ahead, Slice 21, spec §5.1 +
  Appendix B). `production_autonomy.py` (pure, no I/O, no LLM): `evaluate_production_autonomy` scores
  the **13 Appendix-B gates** with status ∈ `{passed, insufficient_evidence, no_evidence_source}`
  (subsystem detail in `reason`; every gate also carries a `context` dict, default `{}`, since
  Slice 22). **Gate #1 (R5 intake) passes at R5 and — Slice 28 — gate #3 (branch protection) is
  PASS-capable**; **#2/#5/#6/#7/#8/#9/#12** are
  `insufficient_evidence` (partial *context* primitives that never pass a gate — **#5/#6
  security/shortcut findings are `insufficient_evidence:no_finding_provenance_or_scan_source` with
  open/critical-finding-count context** after Slice 23 added the stores; **#7 risk-acceptance is
  open/critical-finding-count context** after Slice 23 added the stores; **#7 (risk-acceptance +
  open-issue + release-binding) is `insufficient_evidence` — its reason narrows from
  `no_issue_provenance_or_release_binding` to `no_issue_provenance` once a FROZEN release candidate
  exists (Slice 25), with risk-acceptance/open-issue/frozen-release/bound-issue counts as context**);
  **#3 (branch protection, Slice 28) evaluates the latest snapshot for the project's CURRENTLY
  declared repo/branch via a latest-wins ladder (`branch_protection_repo_unbound` →
  `no_branch_protection_evidence` → `branch_protection_observed_unverified` →
  `branch_protection_evidence_stale` → `branch_protection_insufficient` → `passed`) and PASSes on a
  repo-bound latest `connector_verified` + protection-enabled + PR-reviews + ≥1 required check + fresh
  (`CI_EVIDENCE_MAX_AGE_HOURS`) snapshot — the first non-#1 gate that can pass; a Slice-26
  unverified-only store stays `branch_protection_observed_unverified`**);
  the other **4** (#4/#10/#11/#13) are
  `no_evidence_source:<subsystem>` (await
  Phase 5/6). `a5_satisfied` (all-13-passed) and **`can_go_live_autonomously` are ALWAYS false** —
  go-live also needs a request-authenticated A5 pre-approval (not implemented); this module never
  authorizes production. `ruleset_version` is `slice28.v1`. `ProductionAutonomyRepository`
  (`evaluate`, **compute-on-read, no persistence, no table/migration**) reads current state via the
  readiness/autonomy/budget/category/risk-acceptance/release-findings/release-issue/release-candidate/
  ci-evidence repos inside `tenant_scope`/RLS;
  cross-tenant/nonexistent yields a generic not-satisfied report (no leak). Read-only exposed at
  `GET /api/projects/{id}/production_autonomy` (Slice 21). **Skeleton: scores gate structure only —
  builds no evidence subsystem (test-exec/rollback/monitoring/emergency-stop), no go-live,
  no LLM.**
- `app/release/ci_evidence.py` + `app/models/branch_protection_snapshot.py` +
  `app/repositories/ci_evidence.py` — **deterministic, tenant-owned source-control / CI
  evidence-provenance store** (Slice 26, Appendix B #3 / §26.3 — the first evidence class for A5 gate
  #3). `ci_evidence.py` (pure): `PROVIDERS` (`github`), two-tier `PROVENANCES`
  (`caller_supplied_unverified` writable via the caller path; `connector_verified` writable via the
  **Slice-28 connector path only**), `REPO_REF_RE` (owner/repo slug) + `TOKENISH_RE` (GitHub-token-prefix denylist),
  `validate_new_snapshot` (provider/repo_ref-shape+token/bool-fields/`required_status_checks`
  bounded-string-list; rejects caller-asserted `connector_verified`), `derived_check_count`.
  `CIEvidenceRepository` (`record_branch_protection` [caller path; stamps `caller_supplied_unverified`,
  derives count, audits **safe metadata only** — never repo_ref/check-names/URLs],
  `record_connector_verified_branch_protection` [**Slice 28** connector path; stamps `connector_verified`
  after a verified GitHub 200], `latest_branch_protection`, `latest_branch_protection_for_repo` [the
  repo-scoped lookup gate #3 uses], `count_branch_protection_snapshots`,
  `count_connector_verified_branch_protection` [>0 once the connector has written]).
  `branch_protection_snapshots` (tenant-owned, RLS ENABLE+FORCE; **immutable append-only** —
  SELECT/INSERT only, UPDATE/DELETE/TRUNCATE blocked; the §3/§4.1 CHECKs + INSERT guard are the
  authoritative DB backstop, migrations `0025` + `0027`). Wires A5 gate #3 (`production_autonomy`
  `ruleset_version` `slice28.v1`): gate #3 evaluates the latest snapshot **for the currently declared
  repo/branch** via a latest-wins ladder and **PASSes** on a repo-bound latest `connector_verified` +
  protection-enabled + PR-reviews + ≥1 required check + fresh snapshot (Slice 28; a Slice-26
  unverified-only store stays `branch_protection_observed_unverified`). Latest snapshot read-only exposed
  at `GET /api/projects/{id}/ci_evidence` (latest-or-null, no list/history). **The Slice-28 connector
  itself (`app/release/scm_connector.py` + `ci_evidence_service.py` + `project_repo.py`) is summarized
  at the top of this file; this store stays deterministic — no secrets-reference verification, no
  PR/test-oracle evidence, no go-live, no LLM.**
- `app/release/findings.py` + `app/models/release_finding.py` + `app/models/release_finding_event.py`
  + `app/repositories/release_findings.py` — **deterministic, tenant-owned security/shortcut
  release-findings store** (Slice 23, §13.4/§916-920/§24.1 — A5 gates #5/#6 evidence). `findings.py`
  (pure): `FINDING_TYPES` (`security`/`shortcut`), `SEVERITIES`, `SECURITY_CATEGORIES` (§916-920),
  `SHORTCUT_CATEGORIES` (§13.4), `validate_new_finding` (required fields, category-per-type, `other`
  ⇒ non-empty summary+detail), `validate_transition` (one-way open→terminal), `is_critical`.
  `ReleaseFindingRepository` (`create`/`resolve`/`mark_false_positive`/`supersede`/`accept`/`get`/
  `count_open`/`count_open_unaccepted_critical`): create rejects invalid taxonomy; **accept is
  non-critical only and requires a usable risk-acceptance record**; audits safe metadata only
  (ids/type/severity/status/category — never summary/detail/resolution prose). `release_findings`
  (tenant-owned, RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, **no DELETE**; type/severity/status CHECKs;
  **DB guard** = INSERT invariants [status=open, unverified provenance, NULL resolution/acceptance
  metadata, category-per-type, `other` rule] + per-transition column mutability + one-way lifecycle +
  **critical-cannot-be-accepted** + accepted-requires-usable-risk-acceptance-record) + append-only
  `release_finding_events`. Migration `0022`. Feeds the conservative A5 gates #5/#6 (never pass).
  **Skeleton: store + lifecycle only — no scanner/security-reviewer/shortcut-detector execution, no
  issue/release entity, no evidence pack, no go-live, no LLM, no HTTP API; critical findings are hard
  blockers (the §24.1 human-authority override is out of scope).**
- `app/release/issues.py` + `app/models/release_issue.py` + `app/models/release_issue_event.py`
  + `app/repositories/release_issues.py` — **deterministic, tenant-owned open-issue / blocker store**
  (Slice 24, §24.1/§24.2/Appendix B #7 — the fourth real A5 evidence source; gives the Slice-22
  risk-acceptance `issue_id` a real referent). `issues.py` (pure): `ISSUE_CATEGORIES` (10 gate-axis
  values; `other`⇒summary+detail), `SEVERITIES`, `STATUSES` (`open`/`resolved`/`accepted`/`superseded`
  — no `false_positive`), `HARD_REFUSAL_CATEGORIES` (imported from `risk_acceptance` — single source),
  `validate_new_issue` (required fields, taxonomy, **`critical`⇒`blocking`**, `blocking` must be a real
  bool), `validate_transition` (one-way open→terminal), `is_critical`, `is_hard_blocker` (critical OR a
  hard-refusal `blocking_category`). `ReleaseIssueRepository` (`create`/`resolve`/`supersede`/`accept`/
  `get`/`count_open`/`count_open_blocking`/`count_open_unaccepted_blocking`): create rejects invalid
  taxonomy + critical-non-blocking; **accept refuses hard blockers and requires a usable
  risk-acceptance record**; audits safe metadata only (ids/issue_category/severity/blocking/status —
  never summary/detail/resolution/blocking_category prose). `release_issues` (tenant-owned, RLS
  ENABLE+FORCE; SELECT/INSERT/UPDATE, **no DELETE**; category/severity/status CHECKs; nullable
  composite FK → `risk_acceptance_records`; **DB guard** = INSERT invariants [status=open, unverified
  provenance, NULL resolution/acceptance metadata, `other` rule, **critical⇒blocking**] + per-transition
  column mutability + one-way lifecycle + **hard-blocker-cannot-be-accepted** +
  accepted-requires-usable-risk-acceptance-record) + append-only `release_issue_events`. Migration
  `0023`. Feeds the conservative A5 gate #7 (never passes — no issue provenance/release binding).
  **Skeleton: store + lifecycle only — no reviewer/CI/verifier issue provenance, no findings→issue
  bridge, no issue/release entity, no evidence pack, no go-live, no LLM, no HTTP API; `open` ⟹ not
  accepted, so `count_open_unaccepted_blocking` equals `count_open_blocking` this slice.**
- `app/release/release_candidates.py` + `app/models/release_candidate.py` +
  `app/models/release_candidate_event.py` + `app/models/release_candidate_issue_binding.py` +
  `app/repositories/release_candidates.py` — **deterministic, tenant-owned release-candidate /
  release-binding store** (Slice 25, §24.1/§24.2/Appendix B #7 — the *release-binding* half of gate #7;
  the **future** referent namespace for Slice-22 `risk_acceptance_records.release_id`, **not yet
  FK'd/validated**). `release_candidates.py` (pure): `STATUSES` (`draft`/`frozen`/`superseded`/
  `canceled`), `TERMINAL_STATUSES`, `validate_new_candidate` (required `release_ref`; optional str
  `title`), `validate_transition` (one-way draft→{frozen,canceled}, frozen→{superseded,canceled}).
  `ReleaseCandidateRepository` (`create`/`freeze`/`supersede`/`cancel`/`bind_issue`/`get`/
  `list_for_project` + A5 counts `count_frozen`/`latest_frozen` [ordered `frozen_at DESC, created_at
  DESC, id DESC`]/`bound_open_issue_count`/`bound_open_blocking_issue_count`/
  `bound_open_unaccepted_blocking_issue_count`): audits safe metadata only (ids/release_ref/status —
  never `title`/prose). `release_candidates` (tenant-owned, RLS ENABLE+FORCE; SELECT/INSERT/UPDATE,
  **no DELETE**; status CHECK; **`UNIQUE(id,tenant_id)`** [event FK target] +
  **`UNIQUE(id,project_id,tenant_id)`** [binding FK target] + `UNIQUE(tenant,project,release_ref)`;
  guard trigger = INSERT invariants [status=draft, frozen_at NULL] + identity immutability +
  same-status no-op + one-way lifecycle + `frozen_at`-iff-entering-`frozen`) + append-only
  `release_candidate_events` + append-only, **freeze-locked** `release_candidate_issue_bindings`
  [**Option A FK** — `(release_candidate_id,project_id,tenant_id)`→candidates,
  `(release_issue_id,tenant_id)`→`release_issues` (no `release_issues` mutation); guard trigger rejects
  INSERT unless the candidate is `draft` and the issue's project matches]. Migration `0024`. Feeds the
  conservative A5 gate #7 (never passes). **Skeleton: store + lifecycle only — no reviewer/CI issue
  provenance/completeness, no risk_acceptance `release_id` FK, no findings/risk-acceptance binding, no
  release approval/verdict/deploy, no evidence pack, no go-live, no LLM, no HTTP API; `open` ⟹ not
  accepted, so `bound_open_unaccepted_blocking_issue_count` equals `bound_open_blocking_issue_count`.**
- `app/release/risk_acceptance.py` + `app/models/risk_acceptance_record.py` +
  `app/models/risk_acceptance_event.py` + `app/repositories/risk_acceptance.py` — **deterministic,
  tenant-owned go-live risk-acceptance store** (Slice 22, §24.1/§27.10 — the first real A5 evidence
  source). `risk_acceptance.py` (pure): `SEVERITIES`, `HARD_REFUSAL_CATEGORIES`
  (`critical_security_blocker`/`fake_done_finding`/`missing_production_rollback`/
  `missing_regulated_or_safety_authority`), `STATUSES`, `validate_new_record` (required §27.10/§24.1
  fields incl. `expiry_date`; `accepted_by` non-empty; `approval_authority_source=="approval_matrix"`;
  **hard-refusal `blocking_category` rejected**), `validate_transition` (one-way
  active→{expired,revoked,superseded}). `RiskAcceptanceRepository` (`create`/`revoke`/`supersede`/
  `expire_if_overdue`/`count_active_nonblocking`/`get`/`list_for_project`): create rejects hard
  refusals at store time, stamps `approver_provenance` (`caller_supplied_unverified`, or — **Slice 27** —
  `request_authenticated` under **actor-bound** signer semantics: principal == payload `approver` AND in
  `accepted_by`; key-custody, **not** a verified human signature), writes a `risk_acceptance_events` row +
  audit (safe metadata only — ids/severity/status,
  never prose). `risk_acceptance_records` (tenant-owned, RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, **no
  DELETE**; severity + status CHECKs; **guard trigger: only `status`/`updated_at` mutable**) +
  append-only `risk_acceptance_events` (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked). Migration
  `0021`. Feeds the conservative A5 gate-#7 hook (never passes). **Skeleton: store + lifecycle only —
  no issue/release entity, no verified **human signature**/approval-matrix authority (Slice 27 adds only
  key-custody `request_authenticated` under actor-bound semantics), no evidence-pack, no go-live, no LLM,
  no HTTP API; the §24.1 human-authority override for hard refusals is out of scope (blocked outright).**
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
  (**2** after Slice 20: `autonomy_policy`/`cost_and_resource_policy` — engine-read from Slices 3/7 for
  the R5 gates, **not** declarable), `DECLARABLE_INTAKE_CATEGORIES` (**22** — Slice 20 made
  `human_approval_policy` + `production_authority` declarable as presence-only, non-authorizing).
  File 14 `architecture_and_technology_constraints` = architecture +
  stack. Validators: declarable-only category; non-secret `data` (secrets = reference-only
  `{manager, reference_name}`, inline values rejected); **source XOR** (document+locator+no-origin vs
  origin-only), fail-closed. `IntakeCategoryRepository` (`declare`/`revise`/`list_categories`/`get_category`)
  pre-checks document sources (accepted, same project) and audits **safe metadata only**
  (`has_source_document`/`has_origin` booleans — never the UUID/locator/summary/data/secret). `IntakeCategory`
  (table `intake_categories`): tenant-owned, RLS ENABLE+FORCE; one declaration per `(tenant, project,
  category)`; source-XOR + bounds CHECKs; guard trigger (accepted-source-doc + immutable
  `id`/`tenant_id`/`project_id`/`category`/`created_at`); **no DELETE/TRUNCATE**; `data` JSONB;
  SELECT/INSERT/UPDATE grants. **Skeleton: inputs only — Slice 15 itself adds no readiness computation.
  The rules that consume these declarations landed later: Slice 16 (R3 technical trio + environments
  staging gate), Slice 18 (the two R4 "tools" categories), Slice 20 (all remaining declarable categories
  for R5, including the two presence-only gates, + the autonomy/cost engine gates). No HTTP endpoint, no
  LLM, no secret values, no new spine kinds; A5/Appendix-B production autonomy remains deferred.**
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
  SELECT/INSERT only + UPDATE/DELETE/TRUNCATE block triggers]); `0020_r5_declarable_categories.py`
  (Slice 20: drops+recreates the `ck_intake_categories_category_valid` CHECK to allow the 22-category
  set — adds `human_approval_policy` + `production_authority`; no new table/column/grant/trigger;
  downgrade restores the 20-set); `0021_risk_acceptance.py` (Slice 22: **tenant-owned**
  `risk_acceptance_records` [RLS ENABLE+FORCE + `tenant_isolation`; SELECT/INSERT/UPDATE, no DELETE;
  severity + status CHECKs; guard trigger so only `status`/`updated_at` are mutable; no DELETE/TRUNCATE]
  + append-only `risk_acceptance_events` [SELECT/INSERT only; UPDATE/DELETE/TRUNCATE block triggers;
  composite FK pinning to the record's tenant]; no change to existing tables); `0022_release_findings.py`
  (Slice 23: **tenant-owned** `release_findings` [RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, no DELETE;
  type/severity/status CHECKs; nullable composite FK → `risk_acceptance_records`; guard trigger =
  INSERT invariants (status=open, unverified provenance, NULL resolution/acceptance metadata,
  category-per-type, `other`⇒summary+detail) + per-transition mutability + one-way lifecycle +
  critical-cannot-be-accepted + accepted-requires-usable-risk-acceptance-record; no DELETE/TRUNCATE]
  + append-only `release_finding_events` [SELECT/INSERT only; UPDATE/DELETE/TRUNCATE block triggers];
  no change to existing tables); `0023_release_issues.py`
  (Slice 24: **tenant-owned** `release_issues` [RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, no DELETE;
  category/severity/status CHECKs; nullable composite FK → `risk_acceptance_records`; guard trigger =
  INSERT invariants (status=open, unverified provenance, NULL resolution/acceptance metadata,
  `other`⇒summary+detail, critical⇒blocking) + per-transition mutability + one-way lifecycle +
  hard-blocker-cannot-be-accepted + accepted-requires-usable-risk-acceptance-record; no DELETE/TRUNCATE]
  + append-only `release_issue_events` [SELECT/INSERT only; UPDATE/DELETE/TRUNCATE block triggers];
  no change to existing tables); `0024_release_candidates.py`
  (Slice 25: **tenant-owned** `release_candidates` [RLS ENABLE+FORCE; SELECT/INSERT/UPDATE, no DELETE;
  status CHECK; `UNIQUE(id,tenant_id)` + `UNIQUE(id,project_id,tenant_id)` +
  `UNIQUE(tenant,project,release_ref)`; guard trigger = INSERT invariants (status=draft, frozen_at
  NULL) + identity immutability + same-status no-op + one-way lifecycle + frozen_at-iff-frozen; no
  DELETE/TRUNCATE] + append-only `release_candidate_events` + append-only, freeze-locked
  `release_candidate_issue_bindings` [Option A FKs → candidates + `release_issues`; guard trigger =
  candidate-must-be-draft + issue-project-match; SELECT/INSERT only]; no change to existing tables);
  `0025_ci_evidence.py` (Slice 26: **tenant-owned, immutable append-only** `branch_protection_snapshots`
  [RLS ENABLE+FORCE; **SELECT/INSERT only** — no UPDATE/DELETE/TRUNCATE (block triggers, mirroring
  `0015`); provider/provenance/count CHECKs; a `repo_ref` owner/repo-slug CHECK
  (`ck_bps_repo_ref_slug`) + a GitHub-token-prefix denylist CHECK (`ck_bps_repo_ref_not_tokenish`); a
  `required_status_checks` JSON-array CHECK (`ck_bps_checks_array`); a BEFORE INSERT guard enforcing
  provenance=caller_supplied_unverified (the `connector_verified` tier is schema-reserved but
  **unwritable** this slice), the `repo_ref` shape + token denylist, the JSON-array shape + per-element
  bounded-string rule, and `required_status_check_count` = jsonb_array_length(required_status_checks)];
  no change to existing tables);
  `0026_request_auth_identity.py` (Slice 27: request-auth → verified actor identity. `tenant_api_keys`
  gains `principal_subject` + `actor_type` (the verified principal; existing keys backfilled
  `service`/`legacy:<id>`, then NOT NULL + bounded/`IN ('human','service')` CHECKs);
  `resolve_tenant_api_key(text)` is **DROP+recreate**d to return `(tenant_id, principal_subject,
  actor_type)` with the D4 model restored verbatim (`api_key_resolver` owner; PUBLIC revoked; `uaid_app`
  EXECUTE-only, **no** table SELECT); `approvals` gains `requested_by_provenance` + value CHECKs on both
  provenance columns (`caller_supplied_unverified`/`request_authenticated`); the
  `risk_acceptance_records` guard is **CREATE OR REPLACE**d to allow `request_authenticated` on INSERT
  (every other 0021 invariant preserved). Reversible; no new table);
  `0027_connector_verified_evidence.py` (Slice 28: a single **`CREATE OR REPLACE`** of the `0025`
  `branch_protection_snapshots_guard()` so INSERT allows `provenance IN ('caller_supplied_unverified',
  'connector_verified')` — preserving verbatim the repo_ref slug+token denylist, JSON-array, per-element
  and count-equality invariants. The provenance **column CHECK already allowed both** (`0025`); only the
  guard forced the unverified tier. No new table/column/grant; `downgrade` restores the strict guard;
  reversible).
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
  `test_extraction_promotion.py`, `test_intake_categories.py`, `test_production_autonomy.py`,
  `test_risk_acceptance.py`, `test_release_findings.py`, `test_release_issues.py`, `test_release_candidates.py`, `test_ci_evidence.py`, `test_identity.py`, `test_pr_evidence.py`, `test_deploy_evidence.py`, `test_monitoring_evidence.py`, `test_secrets_verification.py`, `test_approval_channel.py`, `test_pm_issues.py`, `test_classification.py`, `test_generator.py`, `test_semantic_contradictions.py`, `test_skills.py`, `test_factory.py`, `test_qualification.py`, `test_failure_policy.py`, `test_api.py`
  (DB-backed `db` + Docker-free units) and `conftest.py`
  (admin fixtures build/seed `app_test`; `rls_engine` as `uaid_app`; per-test transaction rollback;
  auto-dispose of the `app.db` engine).
  **`make test` → 715 passing (Docker-free); `make test-db` → 713 passing (DB-backed: tenancy,
  readiness, RLS, audit, policy, approval, tool-broker, agent-registry, cost-ledger, runtime,
  document-intake, the read API [real-HTTP auth deny-by-default, cross-tenant denial via
  dependency→tenant_scope/RLS, read-only, catalog, + D4 SECURITY-DEFINER resolver: EXECUTE-only,
  no direct key-table read; **Slice 17 readiness/findings endpoints — latest snapshot, empty-state
  null, cross-tenant null, read-only/405, latest-ordering**; **Slice 19 history endpoints —
  newest-first ordering, empty-list, cross-tenant empty-list, auth deny, read-only/405,
  latest+history coexistence**], and the intake spine [Sanad fail-closed source-count via the
  deferrable constraint, document composite-FK cross-project/cross-tenant rejection,
  accepted-document-only trigger, append-only, the §4.4 classification CHECK, RLS + cross-tenant],
  the readiness auditor [R0–R5 ladder, R3 = declared §4.3 technical trio, **R4 = declared §4.3 tools
  pair + zero spine gaps** (Slice 18), **R5 = all declarable categories declared + the autonomy &
  cost engine gates** (Slice 20; repo reads real `autonomy_policies`/`budgets` rows — present+valid
  autonomy [invalid overrides ⇒ fail], positive budget), staging = R3/R4/R5 AND environments declared
  (monotonic), always-false go-live (even at R5 — A5/Appendix-B separate), D-6 stale-source exclusion
  (quarantined source drops R3→R2 and, for R4 tools, R4→R3; same-project pinning enforced upstream by
  the intake-category DB FK), deploy_production wiring, deterministic latest/history, RLS, append-only], and the
  gap/contradiction detector [taxonomy incl. generic
  C_SELF_PARENT, content-safe refs-only report + counts-only audit, RLS, append-only, count CHECKs],
  and the LLM extractor [FakeLLMClient only — no network; projected-cost preflight gating
  (no-budget/over/projected-over ⇒ no call), run-keyed cost idempotency, injection hard-refuse,
  hallucinated-evidence rejection, token/price fail-closed, DB review guard (distinct reviewer +
  frozen-once-decided), RLS, append-only runs, accepted-doc pinning, audit safety], and proposal
  promotion [eligibility + idempotency, promotion-time evidence re-verification, test_oracle/non-AC-parent
  refusal, parent validation, §16.5 assumption gating incl. approval-engine, approval-request idempotency
  + payload/audit safety, RLS, append-only], and intake category modeling [universe partition
  3/22/2 (Slice 20: human_approval_policy + production_authority now declarable; DB CHECK accepts
  them, non-declarable still rejected), declarable/secret/source-XOR validators, readiness interaction
  (no declared categories ⇒ R2, cap now R5, every category consumed ⇒ not-assessed empty), accepted-doc
  pinning, immutable keys, no-DELETE/TRUNCATE, RLS, catalog], the A5 production-autonomy evaluator
  [13 gates, #1 passes at R5 and **gate #3 (Slice 28) PASSes** on a repo-bound latest `connector_verified`
  + protection-enabled + PR-reviews + ≥1 required check + fresh snapshot (`test_gate3_ladder_and_pass`,
  `test_gate3_pass_count_depends_on_r5`); the other partial gates `insufficient_evidence` with context
  counts; `slice28.v1`;
  gate #7 reason narrows `no_issue_provenance_or_release_binding` → `no_issue_provenance` when a frozen
  release candidate exists, with open-issue + frozen/bound counts; **gate #3 latest-wins ladder
  (`branch_protection_repo_unbound` → … → `passed`); in the pure-engine no-evidence baseline gate #3 is
  `insufficient_evidence`, so the baseline set stays**
  `PARTIAL={2,3,5,6,7,8,9,12}`/`SOURCELESS={4,10,11,13}`; go-live always false; compute-on-read
  no-writes; cross-tenant no-leak], the risk-acceptance store [required-field + hard-refusal + lifecycle
  validation, store-time hard-refusal rejection, expire-on-demand, count-active-nonblocking, RLS +
  cross-tenant, append-only events + record immutability guard, audit safe-metadata, catalog/grants],
  and the release-findings store [taxonomy + category-per-type + `other` rule + lifecycle validation;
  DB-guard refusals (bad-status insert, `other`-without-detail, resolution-metadata-on-insert,
  critical-accept, terminal re-transition, accept-without-usable-record, cross-tenant accept);
  resolve/false_positive/supersede/accept; count_open + count_open_unaccepted_critical; RLS +
  cross-tenant; append-only events + immutability; audit safe-metadata; catalog/grants]), and the
  release-issues store [10-value taxonomy + `other` rule + critical⇒blocking + lifecycle validation +
  is_hard_blocker; DB-guard refusals (bad-status insert, `other`-without-detail,
  resolution-metadata-on-insert, critical-non-blocking insert, updated_at-only update, terminal
  re-transition, critical/hard-blocker accept, accept-without-record, accept with
  expired/non-active/blocking/wrong-project/wrong-issue/cross-tenant record); resolve/supersede/accept;
  count_open + count_open_blocking + count_open_unaccepted_blocking; RLS + cross-tenant; append-only
  events + immutability; audit safe-metadata; catalog/grants; A5 gate-#7 wiring reads the counts]), and
  the release-candidate/binding store [lifecycle validation; create/freeze/supersede/cancel/bind_issue;
  count_frozen + latest_frozen ordering + bound counts; DB-guard refusals (bad-status insert, frozen_at
  on insert, updated_at-only update, freeze-without-frozen_at, terminal re-transition, bind-when-not-draft,
  bind-cross-project, duplicate-binding, no-DELETE/TRUNCATE on all three); RLS + cross-tenant; audit
  safe-metadata; catalog incl. the three unique constraints; A5 gate-#7 narrowing reads the counts]),
  and the source-control/CI evidence store [Slice 26 + 28: pure validators (provider/provenance, repo_ref
  owner/repo-slug shape + GitHub-token-prefix denylist, required_status_checks bounded-string list,
  caller-cannot-assert-connector_verified [caller path still refused]); DB-guard refusals (bad provider,
  repo_ref URL/SSH/query/multislash/token, required_status_checks non-array/non-string/empty/oversized,
  count-mismatch) + **Slice 28: 0027 relaxes the guard so the connector path writes connector_verified**
  (`test_db_guard_now_allows_connector_verified_only`); append-only no-UPDATE/DELETE/TRUNCATE; FK
  cross-project/tenant; RLS + cross-tenant;
  audit safe-metadata (no repo_ref/check-names); catalog/grants (SELECT/INSERT only) + the three CHECKs;
  **A5 gate-#3 wiring + the latest-wins ladder PASS path** (repo-bound latest connector_verified + fresh +
  sufficient — `test_gate3_*`); ci_evidence read endpoint latest-or-null + cross-tenant
  no-leak]).
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
make test                                  # Docker-free tests (no services) — 715 passing
RLS_DB_PASSWORD=... make test-db           # DB-backed tests (needs `make up`) — 713 passing
make fmt                                   # ruff format + lint
make up                                    # start Postgres/Redis/Chroma (needs Docker)
make dev                                   # run API at http://localhost:8000
```
`make test` runs `pytest -m "not db"` (Docker-free). `make test-db` bootstraps the
`uaid_app` role (needs `RLS_DB_PASSWORD`), creates+migrates `app_test` **as admin**,
then runs `-m db` with the runtime `uaid_app` connection. Migrations never run as
`uaid_app`. Endpoints: `/health/live`, `/health/ready`, `/demo`, and the read-only
`/api/projects/{id}/{runs,approvals,blockers,cost,readiness,findings}` plus
`…/{readiness,findings}/history` and `…/production_autonomy` (require `Authorization: Bearer <key>`).

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
  expiry), no real channels (Slack/email), no dashboard (§18.6 / Slice 10). Slice 27 adds
  request-authenticated requester/resolver provenance (`request_authenticated`, key-custody — **not** a
  human signature) + a §2.2 verified self-approval refusal; an unauthenticated caller stays
  `caller_supplied_unverified`.** Note: the policy `is_mandatory_action` helper was added to `app/policy/matrix.py`.
- Tool broker (§11): **present (Slice 5)** — deny-by-default decision chokepoint composing
  policy + approval, per-agent allowlist ledger, every attempt recorded. **Skeleton: no real
  execution / connectors / MCP / credentials / rate limits / cost / auto-suspension.** Success
  caps at `ALLOWED_UNVERIFIED_IDENTITY`; the broker is **not wired** to Slice 27 identity (D-27-4) — its
  authenticated-approval allowlist is empty, so even `request_authenticated` ⇒ `NEEDS_AUTHENTICATED_APPROVAL`
  (nothing here is executable authorization yet).
- Agent registry (§9.7/§17.4/§22.2): **present (Slice 6)** — global admin-curated `agent_blueprints`,
  global **immutable** `agent_versions` (full §22.2 hash snapshot; UPDATE/DELETE/TRUNCATE blocked by
  trigger — *DML-immutable, not tamper-proof vs. a DB superuser*), tenant-scoped RLS `agent_instances`
  (triple FK pins run→project→tenant; binding columns immutable; `active_run_id` set-once; one live
  binding per role handle). **Slice 39** adds the tenant-only **realization factory**
  (`AgentRealizationRepository.realize` — instance + instance-scoped allowlist + FK reviewers + an inert
  `unqualified` `agent_realizations` record) and **wires the broker agent path** (`broker_call` resolves
  `agent_id`→a real same-project instance + a qualification gate). **Slice 40** adds the qualification eval
  (`QualificationRepository` + `archetype_evals`/`qualification_runs`, migration `0039`) — the
  `unqualified→qualified` transition on a passing **recorded-evidence** run + two run-scoped QA+Security
  sign-offs, after which the broker agent path **reaches** its downstream gates (still
  `ALLOWED_UNVERIFIED_IDENTITY` — no execution). **Slice 41** adds the §9.6 replacement-policy layer
  (`app/agents/failure_policy.py` + append-only `agent_failure_events` + compute-on-read
  `evaluate_replacement`, migration `0040`) — REPORTED failure patterns → the §9.6 prescription + the
  retry-cap decision (`escalate_or_blocker` at `MAX_FAILURE_ATTEMPTS=3`); decision-only, NO
  auto-suspend/execution. **Skeleton: no LIVE eval execution / agent run / model
  routing / agent execution (qualification is recorded-evidence, `caller_supplied_unverified`); no §9.6
  response execution (Slice 41 records + decides only — the operative suspend stays an operator/later
  action); global
  registration is not audited (tenant-GUC-derived audit; platform-event audit deferred); component hashes
  are opaque caller-supplied inputs (the Factory that generates the artifacts is Phase 4).**
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
- Read API / dashboard (§18.6): **present (Slice 10 + Slice 17 + Slice 19)** — read-only JSON `/api` endpoints
  (run state, open approvals, blockers, cost + stop decision, **and — Slice 17 — the latest persisted
  build-readiness (§4.5) and gap/contradiction findings snapshots**) behind **hashed bearer-key tenant
  auth** (D4: `tenant_api_keys` stores only `sha256:` hashes; missing/invalid/revoked ⇒ 401, no
  fallback). The auth dependency is the single HTTP→tenant boundary; all reads stay in
  `tenant_scope`/RLS (cross-tenant reads return nothing). **D4 hardened (migration 0013):** resolution
  is via a `SECURITY DEFINER` function (`api_key_resolver`-owned); `uaid_app` has EXECUTE-only access
  and **no direct read of the key table**. **Slice 17** = `GET /api/projects/{id}/{readiness,findings}`
  returning the latest snapshot via `repo.latest` or `null` (never-evaluated / cross-tenant /
  nonexistent all return `200` + `null` — no existence oracle); GET never computes or persists
  (no `evaluate_and_record`); no migration, no LLM, no R4/R5. **Slice 19** = `GET /api/projects/{id}/
  {readiness,findings}/history` returning the full snapshot list (newest-first, same per-element shape)
  via `repo.history`; empty/cross-tenant/nonexistent all return `200` + `[]`; read-only, no pagination.
  **Deferred: forecast, critical path,
  evidence-pack status, deployment status, next action; readiness/findings history **pagination**;
  a write/trigger-evaluation endpoint; web UI; auth-event audit;
  HTTP key issuance (admin-path only); HMAC/salted key hashing.**
- Everything else in the Phase 1–7 roadmap (§26) beyond Slices 1 / 1b / 2 / 3 / 4 / 5 / 6 / 7 / 8a / 8b / 9 / 10.

## Secrets
`.env` holds **live API keys** and is **gitignored** (verified not tracked). It was
restored from a pre-scaffold backup after scaffolding. Never commit it. Consider
rotating any key that has been exposed in a non-private context.
