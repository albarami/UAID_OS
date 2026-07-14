# Slice 52 Plan — Rollback Verification (A5 Gate #10)

**Status:** APPROVED FOR EXECUTION — v1 approved; OD-52-1…9 ruled and bound (see Rulings section)

**Plan type:** Gate-path evidence slice; plan-only submission. This document does not authorize a branch, code, migration, tests, a commit, or a PR.

**Author persona:** Senior release-reliability / deployment-evidence architect, applying fail-closed release governance.

## Sanad / citation key

- **Spec** — `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`.
- **Environment template** — `docs/UAID_OS_Intake_Template_Pack_v1_2/16_environments_and_deployment_targets.yaml`.
- **Roadmap** — `.planning/GO-LIVE-END-TO-END-ROADMAP.md`, Rev 12.
- **Slice 30 prior art** — `.planning/SLICE-30-PLAN.md`; `app/release/deploy_evidence.py`; `app/release/deploy_connector.py`; `app/release/deploy_evidence_service.py`; `app/repositories/deployments.py`; `app/models/deployment_target_snapshot.py`; migration `0029_deployment_target_evidence`.
- **Verified-artifact prior art** — `app/release/scm_connector.py`; `app/verify/security_scan.py`; `app/repositories/security_scans.py`; migrations `0042_test_oracles`, `0043_security_scan_provenance`, and `0044_shortcut_detector_execution`; `.planning/SLICE-43-PLAN.md` through `.planning/SLICE-45-PLAN.md`.
- **Exact release-scope prior art** — `app/models/release_candidate.py`; `app/models/evidence_pack.py`; `app/repositories/evidence_packs.py`; `app/repositories/release_verdicts.py`; `app/repositories/cost_forecasts.py`; migrations `0048_evidence_packs`, `0049_release_verdicts`, and `0050_cost_forecasts`; `.planning/SLICE-49-PLAN.md` through `.planning/SLICE-51-PLAN.md`.
- **A5 evaluator** — `app/release/production_autonomy.py`; `app/repositories/production_autonomy.py`.
- **Baseline commands** — read-only `git`/`rg`/Alembic commands recorded in §1. No tests were run to draft this plan.

Prospective file names, table names, contracts, reason codes, migration contents, and test cases below are **PROPOSED**, not descriptions of current code. Where the spec does not dictate a design, the text says **inference**, **assumption**, or **open decision**.

---

## Coordinator rulings (final)

OD-52-1 = Option A (dual connector observation), with the embedded question explicitly answered: yes, a connector-observed staging drill is accepted as sufficient for gate #10 — it is the strongest honest evidence available since UAID does not operate deployment infrastructure. Extend the SCM boundary with the bounded exact-commit rollback artifact (connector_verified_ci_rollback / connector_observed_ci) and extend the Slice-30 deploy-target service with the staging probe (connector_verified availability). UAID derives the verdict; it never claims it executed the remote actions.

OD-52-2 = Option A: strict code-owned slice52.staging_target.v1 projection over canonical template 16 (staging.provider=generic_https + strict FQDN staging.domain); Slice-30 FQDN/SSRF/tokenish/public-IP rules reused; production targets, IPs, URLs, ports, credentials, private/local targets impossible; the canonical asset stays byte-stable; raw target never enters audit or A5 context.

OD-52-3 = Option A: exactly the five A→B→A phases (baseline_a_probe, forward_deploy_b, forward_b_probe, rollback_to_a, post_rollback_a_probe); all five passed for gate eligibility; valid negative artifacts preserved with failed/not_run; omitted rows are malformed, never implicit failure.

OD-52-4 = Option A: binding = current frozen candidate + latest complete re-audited Slice-49 core with repo_binding_state='agreed'; to_commit_sha equals the core commit; A/B exact digests that must differ; the missing from-version record carried explicitly as from_version_connector_observed_not_deployment_fk; no candidate→commit FK claimed.

OD-52-5 = Option A: a gate-bearing run requires a composite-FK-bound, connector-verified, available, same-target staging snapshot observed after artifact completion (availability only, never version); migration may add only the additive composite identity target on deployment_target_snapshots; gate #2 selection and the Slice-30 guard unchanged.

OD-52-6 = Option A: content/binding latest-wins (created_at DESC, id DESC); later failed/refused attempts supersede older passes; no drill TTL (the §9.5.1 monthly cadence is correctly rejected as one); the staging snapshot keeps its existing independently configured freshness rule.

OD-52-7 = Option A: normalized rollback_verification_runs + rollback_verification_phase_results; generated row-local fields plus deferred constraint triggers re-derive exact phase set/order, digests, bindings, execution/result duality, and gate eligibility; infrastructure failed/refused attempts have no phase children; observed negative drills retain theirs.

OD-52-8 = accepted: the 15-rung ladder exactly as plan §8.1; gate name rollback_verified unchanged; pass reason passed:connector_observed_staging_rollback_drill_verified; ruleset advances to slice52.v1; gates #1–#9/#11–#13 byte-identical under the golden matrix.

OD-52-9 = accepted: the three contract versions; exactly five phase rows; artifact ≤2 MiB with exactly one safe named JSON member; the stated bounds; no raw URLs/domains/IPs/credentials/logs/bodies/version labels anywhere in audit or A5 context; no caller truth fields; downgrade 0051→0050 fails closed while any Slice-52 row exists.

---

## 0. Honesty crux

### 0.1 The narrow claim this slice may make

A successful Slice-52 record may prove only this bounded statement:

> UAID obtained a bounded rollback-drill artifact through a ruled connector for one exact repository/commit and one declared staging target, independently observed that staging target's availability through the existing deploy-target connector, deterministically verified the ruled A→B→A phase/result contract, and DB-bound that observation to one exact currently frozen release candidate and one exact re-audited evidence-pack core.

That claim is a design **inference** from the roadmap's staging/drill direction (`Roadmap:507-517`), the spec's `rollback_verified: required` and “rollback is verified” requirements (`Spec:2287-2303`, `Spec:2981-2997`), and the A3 staging boundary (`Spec:457-485`). The spec does **not** prescribe an A→B→A sequence, an artifact schema, a target class, a freshness period, or an execution adapter in §24.2. The roadmap phrase “§24.2 distinguishes a plan from a verified rollback” overstates the literal text: §24.2 supplies the required boolean but no explicit plan-versus-drill definition. This plan therefore labels the drill protocol as a conservative, coordinator-ruled interpretation rather than a verbatim spec rule.

### 0.2 Truth tiers

| Tier | Slice-52 example | What it proves | What it does **not** prove |
|---|---|---|---|
| **REPORTED / caller-supplied** | The project's canonical staging-target declaration and any human-readable version label in the source workflow | What the canonical project artifact or workflow declared | Authority, correctness, production equivalence, or that a command had the stated effect |
| **CONNECTOR-OBSERVED** | An exact-commit, bounded CI artifact fetched by the live SCM adapter; a status-only staging probe made by `DeployTargetConnector` | The named external system returned those bounded observations through the adapter | That UAID itself executed the deploy/rollback, that artifact contents are a cryptographic attestation, or that the observed staging system equals production |
| **SYSTEM-DERIVED** | Strict artifact parsing, phase-order checks, A/B digest comparisons, binding digests, currentness, and the derived drill/gate result | Deterministic computation under a named code-owned contract over the stored inputs | Truth of the future, universal rollback reliability, or production permission |
| **DB-PROVEN** | Same-tenant/project FKs, exact child-set cardinality, immutable history, generated/re-derived result fields, and candidate/core/snapshot bindings | The persisted relational invariants and history enforced at commit | External deployment effects, operator identity, target topology equivalence, or evidence completeness outside the ruled inventory |
| **NOT PROVEN** | Future production rollback success, production credentials/authority, actual production topology, full feature scope, or absence of unknown failure modes | Nothing in this slice establishes these | These claims remain prohibited even if gate #10 passes |

`connector_observed_ci` must never be relabelled `system_executed`. If the coordinator instead selects a UAID-driven option in OD-52-1, the plan must still separate **system-invoked orchestration** from **connector-observed remote effects**; invoking an adapter is not proof that the provider performed the effect.

### 0.3 Non-vacuity

- A rollback plan, runbook, command string, caller boolean, empty store, missing artifact, empty phase list, or merely reachable target cannot pass gate #10 (`Spec:2263`, `Spec:2302`, `Spec:2994`; current deployment evidence is availability-only at `app/release/deploy_evidence.py:1-17`).
- A complete five-phase result with any failed/not-run phase cannot pass.
- An older passing drill cannot survive a newer failed/refused attempt for the same current binding.
- A drill for a different candidate, evidence core, repository, commit, target, artifact pair, or contract cannot pass for the current release scope.
- A production target must be rejected by this slice. Production rollback remains approval/emergency-policy territory (`Spec:2377-2389`).

---

## 1. Verified baseline and source findings

### 1.1 Repository state verified before drafting

The following were observed directly, not inherited from a prior handoff:

- `git status --porcelain` returned no entries: the worktree and index were clean before this file was created.
- `git branch --show-current` returned `main`.
- local branch enumeration returned only `main`; remote branch enumeration returned only `origin/main` (plus Git's `origin` symbolic remote entry).
- `git rev-parse HEAD` and `git rev-parse origin/main` both returned `1002cb78b88c1ad8755118358b906beec415febd`.
- `uv run alembic heads` returned `0050 (head)`; `migrations/versions/0050_cost_forecasts.py` identifies the current migration as `0050` after `0049`.
- `app/release/production_autonomy.py:58` is `A5_RULESET_VERSION = "slice51.v1"`.
- `app/intake/readiness.py` remains the `slice20.v1` readiness evaluator (`CLAUDE.md`, Current status and testing sections).
- `CLAUDE.md:666-667`, `CLAUDE.md:1314`, and `CLAUDE.md:1417-1418` record 963 Docker-free and 807 DB-backed tests after Slice 51. These are historical recorded counts; no suite was run for this plan-only task.

Creating this plan makes `.planning/SLICE-52-PLAN.md` the sole intended worktree change. No branch, implementation file, migration, test, commit, or PR is authorized.

### 1.2 What the sources actually require

1. A3 may deploy to staging and run verification loops; production deploy remains A4/A5 authority (`Spec:457-485`).
2. The go-live condition says the rollback plan is verified (`Spec:2251-2267`), the checklist says `rollback_verified: required` (`Spec:2287-2303`), and Appendix B gate #10 says “rollback is verified” (`Spec:2981-2997`).
3. Missing production rollback is not ordinarily risk-acceptable (`Spec:2269-2284`). Slice 52 does not implement an override or approval path.
4. Stabilization says the rollback path “remains valid,” while production rollback requires approval or a pre-approved emergency policy (`Spec:2351-2361`, `Spec:2377-2389`). This supports content/currentness checks but does not define a numeric TTL.
5. The deployment/SRE archetype covers rollback and failure drills, with reference deployments, failure injection, runbooks, zero critical deploy/rollback failures, and a monthly/after-change **agent-evaluation refresh policy** (`Spec:912-930`). That monthly cadence governs archetype evaluation; it is not evidence for a rollback-record TTL.
6. Appendix A separately requires rollback **criteria** to be defined (`Spec:2960-2979`). Criteria are not executed verification.
7. The roadmap makes Slice 52 the sole next planned item and expects staging/drill rollback evidence, migration `0051`, and gate #10 PASS-capability (`Roadmap:507-517`, `Roadmap:659-665`). Its detailed schema and execution wording are planning intent, not current implementation.

### 1.3 Existing implementation facts to extend, not fork

- Slice 30's `deployment_target_snapshots` are immutable observations of target availability, not deployments and not version checks (`app/models/deployment_target_snapshot.py:1-12`; `app/release/deploy_evidence.py:1-17`).
- The existing deployment domain already permits `environment IN ('production','staging')`, but the orchestration resolves and probes only the declared production target (`app/release/deploy_evidence.py:25-29`; `app/models/deployment_target_snapshot.py:47-64`; `app/release/deploy_evidence_service.py:1-10,54-104`).
- The deploy connector is a status-only, SSRF-guarded HTTPS probe. It never reads a body, verifies a served version, or executes a deployment (`app/release/deploy_connector.py:1-23,39-43,68-80,96-116`).
- The canonical environment template has `{}` for staging and defines production-only fields (`Environment template:1-9`). Therefore no current canonical staging-target shape can be assumed; OD-52-2 must rule one.
- The SCM boundary already fetches exact-commit bounded artifacts/corpora for Slices 43-45 and has fake/live separation (`app/release/scm_connector.py:63-76,342-384,513-611`). A rollback artifact method should extend that boundary rather than create an unrelated network client if OD-52-1 selects artifact observation.
- Release candidates contain release identity and lifecycle but no repository, commit, deployed version, or artifact digest (`app/models/release_candidate.py:29-66`). Slice 49 cores carry a derived repo-binding state and optional commit SHA (`app/models/evidence_pack.py:170-236`). That limitation is load-bearing in OD-52-4.
- Gate #10 is currently a permanent `no_evidence_source:rollback_verification` stub (`app/release/production_autonomy.py:965-980`). Gate #10 has no current pass branch.
- A5 is `slice51.v1`, while both no-go reasons remain `a5_gates_not_all_satisfied` and `request_authenticated_a5_preapproval_not_implemented` (`app/release/production_autonomy.py:58-68`).

---

## 2. Scope and non-goals

### 2.1 In scope, subject to coordinator rulings

1. A strict, versioned rollback-drill observation contract for one declared **staging** target.
2. Exact A→B→A phase/result verification: establish A, forward-deploy B, verify B, roll back to A, verify A.
3. Extension of the existing SCM connector boundary for a bounded exact-commit rollback artifact if OD-52-1 selects the recommended path.
4. Extension of the existing deployment-target resolver/probe path to a staging declaration and a connector-verified staging availability snapshot if OD-52-1/2 selects the recommended dual-observation path.
5. Immutable tenant-owned rollback attempt and phase-result records with RLS ENABLE + FORCE, append-only privileges/triggers, composite same-project FKs, DB-generated/re-derived invariants, and safe-metadata audit.
6. Exact binding to the current frozen release candidate, its complete re-audited Slice-49 core, the core's agreed repo/commit binding, the declared staging target, a connector-verified staging snapshot, the A/B artifact digests, and the current code-owned contracts.
7. A fail-closed gate-#10 evidence ladder and the A5 ruleset advance `slice51.v1` → `slice52.v1`.
8. Pure and DB-backed tests, including direct-SQL forgery attempts, artifact/parser adversarial cases, golden A5 regression coverage, and a full migration round trip.

### 2.2 Explicit non-goals

- No production deployment or production rollback. §25.2 leaves production rollback to approval/emergency policy (`Spec:2377-2389`).
- No production pre-approval (Slice 53), emergency-stop authority (Slice 54), or control loop (Slice 55) (`Roadmap:519-554`).
- No claim that staging is topology-equivalent to production.
- No deployment lifecycle, release promotion engine, environment provisioning, credentials/secrets handling, arbitrary command runner, shell execution, plugin execution, or generic workflow engine.
- No new production-target semantics and no gate-#2 meaning change.
- No modification of the canonical environment template unless separately ruled; the recommended design adds a code-owned strict projection over its existing staging object.
- No evidence-pack core mutation or canonical-export schema change. Slice 52 may bind to and re-audit the current core; it does not rewrite historical core bytes.
- No new release-candidate→repo/commit FK and no inference that `release_ref` names a commit.
- No rollback-plan authoring, runbook quality judgment, semantic topology comparison, or universal failure-injection framework.
- No A5 gate other than #10 changes; no readiness change; no removal or alteration of either no-go reason.

---

## 3. Proposed evidence semantics

Everything in this section is **PROPOSED** and awaits the ODs in §4.

### 3.1 Recommended execution boundary

The recommended path is a dual connector observation:

1. Resolve the project's current canonical repo exactly as Slices 43-45 do.
2. Resolve a strict project staging target under the ruled Slice-52 staging-target contract.
3. Fetch one bounded versioned rollback result artifact for the exact repository and core-bound commit through an additive `SCMConnector.fetch_rollback_drill_artifact(...)` method.
4. Fetch the latest **completed exact-commit** workflow attempt, not merely the latest successful attempt. A valid failure artifact must be observable so a newer failed drill supersedes an older pass. If the run never emits its bounded artifact, record an infrastructure/fetch failure; do not reuse an older pass.
5. After artifact retrieval, probe the exact declared staging target with the existing SSRF-safe `DeployTargetConnector`; persist a new `connector_verified`, `environment='staging'` snapshot for every safely attempted positive or negative result.
6. Strictly parse, bind, and score the artifact. The direct probe proves only current generic-HTTPS availability. The CI artifact supplies the connector-observed phase/version evidence. Neither is silently promoted into the other.

The live network remains adapter-only. All CI uses `FakeSCMConnector` and `FakeDeployTargetConnector`. This follows the existing connector separation (`app/release/deploy_connector.py:1-23,83-116`; `app/release/scm_connector.py:63-76,342-384`).

### 3.2 Proposed staging-target contract

Because the canonical template's staging object is empty (`Environment template:1-9`), the recommended code-owned projection is:

```yaml
environments:
  staging:
    provider: generic_https
    domain: staging.example.test
```

This is a Slice-52 **inference**, not a schema already defined by the template. The implementation would:

- read only the canonical, structurally valid template-16 artifact for the same project;
- require exactly the two allowlisted staging keys above for gate-bearing use;
- reuse Slice-30 FQDN, tokenish, SSRF, and public-IP rules;
- reject `production`, IP literals, URLs, ports, paths, credentials, private/local targets, unknown providers, and unknown staging keys;
- treat the declaration as `caller_supplied_unverified_structured_staging_target` while treating a safely attempted probe as `connector_verified` availability;
- compute a SHA-256 staging-target binding from canonical provider + normalized lowercase FQDN; raw target/domain never enters A5 context or audit.

The canonical template asset remains byte-stable. Gate #2 continues to resolve only `environments.production.domain` and remains semantically unchanged.

### 3.3 Proposed drill contract

Contract `slice52.rollback_drill.v1` requires exactly five ordered phase rows:

| Ordinal | Code | Required observation | Pass condition |
|---:|---|---|---|
| 1 | `baseline_a_probe` | target A before change | target is healthy/serving and observed version digest equals `from_artifact_digest` |
| 2 | `forward_deploy_b` | attempted A→B action | operation reported complete for the exact target and expected B digest |
| 3 | `forward_b_probe` | target after forward deploy | target is healthy/serving and observed version digest equals `to_artifact_digest` |
| 4 | `rollback_to_a` | attempted B→A action | rollback operation reported complete for the exact target and expected A digest |
| 5 | `post_rollback_a_probe` | target after rollback | target is healthy/serving and observed version digest equals the original `from_artifact_digest` |

Additional exact rules:

- `from_artifact_digest` and `to_artifact_digest` are canonical lowercase SHA-256 and must differ.
- `to_commit_sha` is canonical lowercase 40-hex and must match the requested/core commit.
- Every phase uses the same target binding and runner-manifest hash.
- Timestamps are UTC-aware, nondecreasing within a phase, and strictly ordered between phase completions/starts. They prove artifact-reported sequence only, not trusted clock accuracy.
- Phase status is `passed | failed | not_run`. A gate-bearing pass requires five `passed` rows. A valid negative artifact may use `failed` and then `not_run`; omitted rows are malformed, not an implicit failure result.
- Probe phases require bounded code-owned probe codes plus health and exact expected/observed digest equality. Action phases require bounded code-owned operation result codes. Caller/artifact fields named `verified`, `trusted`, `gate`, `passed`, `eligible`, or equivalent are rejected.
- The artifact's workflow conclusion is separately captured. Gate eligibility requires a successful provider conclusion and system-derived phase pass. A completed failing/cancelled/timed-out workflow is preserved as negative evidence.
- A valid artifact result is not a signature or provider proof. It is connector-observed CI content.

The five-phase protocol is the recommended conservative interpretation of verified rollback, not a sequence specified by §24.2.

### 3.4 Release, commit, artifact, and target binding

A gate-bearing run is proposed to bind:

```text
tenant + project
+ latest currently frozen release candidate
+ latest complete, re-audited Slice-49 core for that candidate
+ core_content_hash + artifact_scope_digest + issue_binding_digest
+ source_set_digest + traceability_digest
+ core repo_binding_state = agreed
+ exact repo_binding_hash + commit_sha
+ staging-target binding hash
+ connector-verified staging snapshot ID + snapshot observation digest
+ from_artifact_digest + to_artifact_digest
+ rollback runner-manifest hash
+ artifact content hash
+ drill contract hash + verification contract hash
```

`to_commit_sha` must equal the core's agreed `commit_sha`. This establishes a content binding through the Slice-49 core, **not** a release-candidate→commit FK (`app/models/release_candidate.py:29-66`; `app/models/evidence_pack.py:170-236`).

The current repository has no authoritative record for the version already serving in staging. Therefore `from_artifact_digest` is connector-observed drill input, not DB-proven deployment history. The plan must record the limitation code `from_version_connector_observed_not_deployment_fk`. A gate pass must not claim that A was the current production release or a prior frozen candidate.

### 3.5 Currentness and staleness

Recommended currentness is content/binding based:

- latest currently frozen candidate;
- latest complete, successfully re-audited core for that candidate;
- exact current repo/commit binding;
- exact current staging-target declaration;
- a current connector-verified staging availability snapshot under the existing deployment-evidence freshness setting;
- exact current A/B artifact and runner-manifest digests;
- exact current drill/verification contract hashes;
- latest attempt by `(created_at DESC, id DESC)` for that exact binding.

Any binding change requires a new run. A later failed/refused attempt supersedes an older pass. There is no additional wall-clock TTL for the rollback drill in v1 because neither §24.2, Appendix B #10, template 16, nor the roadmap defines one. The §9.5.1 monthly period is an agent-evaluation refresh policy, not a rollback-evidence TTL (`Spec:912-930`).

The staging target probe keeps its existing independently configured freshness semantics (`app/repositories/production_autonomy.py:81-100`); this does not make the drill itself “fresh for N hours.”

### 3.6 What “failure injection” means in v1

The deployment/SRE archetype names failure-injection scenarios as an oracle source (`Spec:927`). That row governs archetype evaluation, while gate #10 only says rollback is verified (`Spec:2994`). The recommended v1 drill uses an explicit controlled A→B→A reversal and does not require causing an outage or production-like failure. A future richer failure-injection library is not silently claimed.

---

## 4. Open decisions requiring coordinator ruling

No implementation may begin until every OD is ruled.

### OD-52-1 — What executes or observes the rollback drill?

- **Option A — dual connector-observed staging drill (recommended):** extend the SCM boundary with a bounded exact-commit rollback artifact and extend Slice 30's deploy-target service to probe the declared staging target after artifact retrieval. Stamp artifact provenance `connector_verified_ci_rollback`, execution observation `connector_observed_ci`, and target observation `connector_verified`. UAID derives the verdict but does not claim it executed the remote actions.
- **Option B — SCM artifact only:** simpler, but the current target's availability is not independently observed by Slice 30's connector.
- **Option C — UAID-driven staging orchestration:** expand a deployment adapter to invoke A→B→A and probe the results. This provides system-invoked orchestration but requires a mutation-capable provider contract, credentials/secret references, artifact deployment semantics, failure compensation, and stronger tool-policy design absent today. Remote effects would still be connector-observed, not DB-proven.

**Ruling must also decide** whether a connector-observed staging drill is sufficient for gate #10 despite not proving future production rollback. Option A is recommended as the smallest truthful use of the repository's existing authority and adapters.

### OD-52-2 — What is the authoritative staging-target declaration?

- **Option A (recommended):** code-owned strict projection over canonical template 16 requiring `staging.provider=generic_https` and `staging.domain=<strict FQDN>`; declaration is caller-supplied structured input, probe is connector-verified. Canonical asset remains unchanged.
- **Option B:** artifact-only target digest with no canonical project target binding. This is weaker and cannot prove the drill addressed the project's declared staging target.
- **Option C:** add a new standalone staging-target declaration artifact/table. This creates a second source of environment truth and risks forking the intake spine.

Production-domain reuse is not an option: this slice must never target production (`Spec:483-485`, `Spec:2387-2389`).

### OD-52-3 — What exact phase set constitutes v1 rollback verification?

- **Option A (recommended):** exactly the five §3.3 phases; all five must pass for gate eligibility; failed/not-run results remain visible; missing phases are malformed.
- **Option B:** three phases (deploy B, rollback A, final probe A). This cannot establish the same observed A baseline or verify B actually served before rollback.
- **Option C:** require injected-failure phases in addition to A→B→A. This is stronger but needs a ruled failure model and provider semantics not supplied by §24.2.

### OD-52-4 — How does the drill bind to release scope and versions?

- **Option A (recommended):** current frozen candidate + current complete re-audited core + agreed core repo/commit; `to_commit_sha` equals the core commit; A/B are exact artifact digests; the missing authoritative from-version record is explicit.
- **Option B:** candidate-only binding. This is insufficient because the candidate has no repo/commit identity.
- **Option C:** add a full deployed-artifact inventory/history subsystem first. Stronger, but materially expands this slice and duplicates future deployment lifecycle work.

### OD-52-5 — Must gate-bearing evidence include a Slice-30 staging availability snapshot?

- **Option A (recommended):** yes. Extend the production-only orchestration with a fixed staging path that reuses the same resolver validation, broker, connector, repository, and freshness behavior; bind the run by composite FK to a connector-verified, available, same-target staging snapshot observed after the artifact completed. The snapshot proves availability only, not version.
- **Option B:** no; phase probe results in the CI artifact are sufficient. This avoids a second observation but weakens independent target availability evidence.

If Option A is ruled, migration `0051` may add only the composite identity target needed on `deployment_target_snapshots`; it must not change existing rows, provenance meanings, gate-#2 selection, or the Slice-30 guard.

### OD-52-6 — What invalidates a current drill, and is there a TTL?

- **Option A (recommended):** exact content/binding latest-wins as §3.5; no drill TTL; later failed/refused attempts supersede; staging snapshot retains its already-configured freshness rule.
- **Option B:** add a code-owned drill TTL. This is not grounded in a canonical rollback policy field and would be an explicit product assumption.
- **Option C:** treat §9.5.1's monthly refresh as the drill TTL. Not recommended because that line applies to deployment/SRE archetype evals, not release evidence.

### OD-52-7 — What is the append-only DB shape and truth ownership?

- **Option A (recommended):** normalized `rollback_verification_runs` + `rollback_verification_phase_results`; generated row-local fields plus a deferred constraint trigger re-derive exact phase set/order, digests, binding, execution/result duality, and gate eligibility. Valid observed negative drills retain phase children; infrastructure failed/refused attempts have no phase children. Succeeded observation means “artifact was validly observed/scored,” not “drill passed.”
- **Option B:** a single JSON result row. Simpler, but exact child coverage and per-phase direct-SQL invariants become application-only.

### OD-52-8 — What is the gate-#10 ladder and pass reason?

Accept or modify the proposed ordered ladder in §8. Gate name remains `rollback_verified`; proposed pass reason is `passed:connector_observed_staging_rollback_drill_verified`. Every failure is `insufficient_evidence`; the current `no_evidence_source` branch is retired only when the subsystem exists. Ruleset advances to `slice52.v1`.

### OD-52-9 — Contract versions, caps, audit, and downgrade

Accept or modify the recommended ruling:

- `slice52.rollback_drill.v1`, `slice52.rollback_verification.v1`, and `slice52.staging_target.v1`;
- canonical SHA-256 digests; exactly five phase rows; artifact ≤2 MiB; ZIP contains exactly one safe named JSON member; codes/keys ≤128; safe evidence reference ≤500; provider workflow ID/hash ≤128; all required strings non-blank;
- no raw URLs, target domains, IPs, credentials, logs, stack traces, commands, environment variables, response bodies, source snippets, or arbitrary artifact JSON in audit/A5 context;
- downgrade `0051→0050` fails closed while any Slice-52 row exists;
- no caller-supplied `trusted|verified|passed|eligible|gate|complete|system_executed` field is accepted.

---

## 5. Proposed pure domain module

### 5.1 `app/release/rollback.py`

Prospective responsibilities:

- contract/version constants and allowlists;
- strict staging-target projection validation;
- bounded rollback-artifact validation;
- exact phase/status/result-code validation;
- canonical hashing and target-binding derivation;
- A/B/time/order/target/commit invariants;
- deterministic `derive_rollback_drill_result(...)` returning only code-owned status/reason/safe counts;
- no I/O, DB, network, environment access, or clock reads.

Suggested immutable input/output types:

```text
RollbackArtifactObservation
RollbackPhaseObservation
RollbackBinding
RollbackDerivedResult
```

The result distinguishes:

- artifact observation infrastructure `succeeded | failed | refused`;
- drill result `passed | failed | incomplete`;
- gate eligibility, generated from the prior two plus bindings and target snapshot.

It must not accept a caller-provided outcome.

### 5.2 SCM connector extension

If OD-52-1 Option A/B is ruled:

```text
SCMConnector.fetch_rollback_drill_artifact(
    repo_ref,
    commit_sha,
    contract_version,
) -> validated bounded artifact observation
```

- `FakeSCMConnector` is the only connector used by CI/tests.
- `GitHubSCMConnector` is the only live network adapter.
- Exact repo + exact commit + exact workflow/artifact name + bounded size + non-expired artifact.
- Inspect the latest completed exact-commit run, including failure/cancel/timeout conclusions; do not filter to success before latest-wins selection.
- Require the exact safe artifact member; reject traversal, symlinks, multiple members, malformed JSON, duplicates, excessive nesting, unknown keys, and decompression overflow.
- No arbitrary workflow dispatch or command execution is introduced under the recommended option.

### 5.3 Staging deployment-evidence extension

If OD-52-1/2/5 recommended options are ruled:

- add `resolve_declared_staging_target(...)` alongside, not inside, production resolution;
- share the existing strict target validation and normalization;
- add an internal `refresh_staging_target_evidence(...)` path using `deployment.read_target_status`, safe broker params, and the existing connector/repository;
- persist `environment='staging'` for every safely attempted result;
- never route a staging request through the production target and never alter the existing production refresh API's behavior;
- audit only project ID, environment code, outcome code, and snapshot ID; omit target/domain/IP/status body data.

---

## 6. Additive data model and migration `0051`

Migration number is an **inference** from verified head `0050` and the roadmap's proposed `0051` (`Roadmap:511-513`). Final filename should be `0051_rollback_verifications.py` after approval.

### 6.1 `rollback_verification_runs`

Tenant-owned, RLS ENABLE + FORCE, append-only.

Proposed columns:

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
release_candidate_id UUID NOT NULL
evidence_pack_id UUID NOT NULL
staging_target_snapshot_id UUID NULL/NOT NULL per OD-52-5
contract_version TEXT NOT NULL
verification_contract_version TEXT NOT NULL
staging_target_contract_version TEXT NOT NULL
artifact_provenance TEXT NOT NULL
execution_observation TEXT NOT NULL
repo_binding_hash CHAR(64) NOT NULL
commit_sha CHAR(40) NOT NULL
core_content_hash CHAR(64) NOT NULL
artifact_scope_digest CHAR(64) NOT NULL
issue_binding_digest CHAR(64) NOT NULL
source_set_digest CHAR(64) NOT NULL
traceability_digest CHAR(64) NOT NULL
staging_target_binding_hash CHAR(64) NOT NULL
staging_snapshot_digest CHAR(64) NULL/NOT NULL per OD-52-5
from_artifact_digest CHAR(64) NOT NULL on observed result
to_artifact_digest CHAR(64) NOT NULL on observed result
runner_manifest_hash CHAR(64) NOT NULL
artifact_content_hash CHAR(64) NOT NULL on observed result
provider_run_ref_hash CHAR(64) NULL
workflow_conclusion TEXT NULL
attempt_status TEXT NOT NULL
attempt_reason_code TEXT NOT NULL
phase_count SMALLINT generated/re-derived
phase_input_digest CHAR(64) generated/re-derived
drill_result TEXT generated/re-derived
gate_eligible BOOLEAN generated/re-derived
scope_limitation_code TEXT NOT NULL
artifact_completed_at TIMESTAMPTZ NULL
created_at TIMESTAMPTZ NOT NULL
```

Composite FKs pin tenant/project/candidate/evidence-pack/snapshot identity with `RESTRICT`. In the current model, the immutable core is the `evidence_packs` row itself; there is no separate `evidence_pack_core_id` (`app/models/evidence_pack.py:160-246`). The exact FK path must follow the existing candidate/pack identity constraints; no cross-tenant/project ID-only FK is permitted.

### 6.2 `rollback_verification_phase_results`

Tenant-owned, RLS ENABLE + FORCE, append-only.

Proposed columns:

```text
id UUID PK
tenant_id UUID NOT NULL
project_id UUID NOT NULL
run_id UUID NOT NULL
ordinal SMALLINT NOT NULL
phase_code TEXT NOT NULL
phase_status TEXT NOT NULL
result_code TEXT NOT NULL
target_binding_hash CHAR(64) NOT NULL
expected_version_digest CHAR(64) NULL
observed_version_digest CHAR(64) NULL
health_ok BOOLEAN NULL
operation_ok BOOLEAN NULL
started_at TIMESTAMPTZ NOT NULL
completed_at TIMESTAMPTZ NOT NULL
created_at TIMESTAMPTZ NOT NULL
```

Unique `(run_id, ordinal)`, `(run_id, phase_code)`, and composite same-project FK to the parent. No prose or raw external payload.

### 6.3 DB-authoritative invariants

The migration must enforce at least:

1. same tenant/project across run, candidate, evidence pack, phase children, and staging snapshot;
2. candidate is the one represented by the core; repository cannot substitute IDs after derivation;
3. `artifact_provenance='connector_verified_ci_rollback'` pairs only with `execution_observation='connector_observed_ci'` under the recommended path;
4. `attempt_status='succeeded'` has exactly one valid five-row child set; infrastructure `failed|refused` has no children or artifact truth fields;
5. exact ordinals/codes and legal field shapes per phase;
6. A and B digest inequality and exact A→B→A equality rules;
7. target-binding equality across all phases/run/snapshot;
8. timestamps and phase order;
9. phase digest/cardinality/result re-derived from children at deferred constraint time;
10. workflow success + all phases passed + current binding inputs are necessary for `gate_eligible=true`;
11. caller attempts to insert/alter generated truth fields fail;
12. append-only UPDATE/DELETE/TRUNCATE denial for app/runtime roles;
13. required fields bounded and non-blank; hash/commit formats exact;
14. production target/environment cannot be attached;
15. RLS tenant isolation on both tables.

Deferred triggers are needed for cross-row exactness. Row-local checks/generated columns must own what PostgreSQL can derive locally. The repository must not be the sole guardian.

### 6.4 Existing-object preservation

- Migration is additive after `0050`; no data backfill and no historical relabeling.
- `release_findings_guard()` stays byte-identical, with MD5 `808036faf2660d6810aeca4342e6f1ac` pinned before/after upgrade, downgrade, and re-upgrade (current assertion: `tests/test_cost_forecasts.py:533-535`).
- If a composite identity target is added to `deployment_target_snapshots`, it is additive only and must not modify row meaning or guard behavior.
- Existing Slice-23/44/45 layered finding rules remain untouched.
- Downgrade removes only Slice-52 objects/additive identity target and refuses while Slice-52 rows exist.

---

## 7. Repository and service behavior

### 7.1 Attempt flow

Proposed internal service flow:

1. Resolve exact tenant/project and latest currently frozen release candidate.
2. Resolve latest complete Slice-49 core for that candidate and re-audit exact stored bytes/children/checkpoint through the existing real re-audit path.
3. Require `repo_binding_state='agreed'`; load exact repo and commit binding without trusting caller input.
4. Resolve and validate the current canonical staging declaration.
5. Ask the broker for only the exact safe connector operations; caller cannot choose production or arbitrary workflow/target.
6. Fetch the latest exact-commit rollback artifact using the injected SCM connector.
7. Probe the same declared staging target through the injected deploy connector (if ruled).
8. Strictly validate and system-derive all phase and binding values.
9. Insert one attempt plus the exact child set in one transaction. A persistence/guard failure aborts the whole transaction.
10. Audit safe metadata only after durable insertion.

Failures/refusals append an immutable attempt where a safe binding can be established. A malformed or negative latest observation must supersede an older pass; a transient caller retry may not silently select the old pass.

### 7.2 Retrieval/currentness

`latest_current_rollback_verification(project_id, now)` must re-derive the current candidate/core/repo/commit/target/contracts and select `(created_at DESC, id DESC)` for that exact binding. It must not accept a caller-selected run ID as current evidence.

If current state cannot be established, return a typed evidence-state/reason; do not raise a truthy default or reinterpret absence as pass.

### 7.3 Audit surface

Allowed examples:

```text
project_id
run_id
release_candidate_id
evidence_pack_id
staging_target_snapshot_id (if ruled)
attempt_status
attempt_reason_code
drill_result
phase_count
workflow_conclusion_code
artifact_provenance
execution_observation
scope_limitation_code
gate_eligible
contract versions
```

Forbidden:

```text
raw repo ref, commit URL, target/domain/IP, artifact URL, provider workflow URL,
credentials/tokens, environment variables, commands/scripts, logs, stack traces,
HTTP bodies, raw artifact JSON, version labels, source snippets, tenant prose
```

Audit sentinel tests must inject unique secret/prose markers into every reachable input/error and prove the markers are absent from audit payloads, A5 context, persisted safe rows, exception text exposed by the service, and logs captured by tests.

---

## 8. A5 gate #10 change

### 8.1 Proposed ordered ladder

Only gate #10 changes. Ordered first-match reasons:

1. `insufficient_evidence:no_current_frozen_release_candidate`
2. `insufficient_evidence:no_complete_reauditable_evidence_core`
3. `insufficient_evidence:release_core_reaudit_failed`
4. `insufficient_evidence:release_repo_commit_binding_missing_or_disagreed`
5. `insufficient_evidence:staging_target_declaration_missing_or_invalid`
6. `insufficient_evidence:no_current_connector_verified_staging_target` (if OD-52-5 Option A)
7. `insufficient_evidence:staging_target_unavailable_or_stale` (if OD-52-5 Option A)
8. `insufficient_evidence:rollback_verification_not_run_for_current_binding`
9. `insufficient_evidence:latest_rollback_attempt_failed_or_refused`
10. `insufficient_evidence:rollback_artifact_provenance_untrusted`
11. `insufficient_evidence:rollback_binding_stale_or_inconsistent`
12. `insufficient_evidence:rollback_phase_coverage_incomplete`
13. `insufficient_evidence:rollback_phase_evidence_inconsistent`
14. `insufficient_evidence:rollback_drill_failed`
15. `passed:connector_observed_staging_rollback_drill_verified`

All context is safe counts/booleans/codes/contract versions only. No repo, commit, target, version, URL, or prose.

### 8.2 Ruleset and unchanged behavior

- Advance only `A5_RULESET_VERSION` from `slice51.v1` to `slice52.v1` because gate #10 gains its first real evidence path and pass branch.
- Gate name remains `rollback_verified`.
- Gates #1-#9 and #11-#13 must be byte-for-byte equivalent in output for identical inputs under a golden before/after matrix.
- Gate #10 becomes the eleventh PASS-capable A5 gate; gates #12 and #13 remain no-source/unmet at this baseline (`app/release/production_autonomy.py:965-980`; roadmap sequencing after Slice 52).
- `app/intake/readiness.py` remains byte-stable at `slice20.v1`.
- `NO_GO_LIVE_REASONS` remains byte-identical:
  - `a5_gates_not_all_satisfied`
  - `request_authenticated_a5_preapproval_not_implemented`
- `can_go_live` remains literal `False` regardless of gate #10.

---

## 9. Test-first implementation plan

Implementation, if later authorized, must use red→green TDD. This plan task itself creates no tests.

### 9.1 Pure tests — proposed `tests/test_rollback_verifications.py`

1. Exact artifact contract accepts one canonical five-pass A→B→A observation.
2. Each phase missing, duplicated, reordered, renamed, or extra fails closed.
3. `failed`/`not_run` negative artifacts derive non-gate-eligible results; omission never substitutes for `not_run`.
4. A==B rejects; final observed A!=initial A rejects; B probe mismatch rejects.
5. Wrong target binding, repo, commit, runner manifest, artifact digest, or core digest rejects.
6. Naive, reversed, overlapping, or non-ordered timestamps reject; same instant at a strict boundary rejects.
7. Unknown workflow conclusion/result/status/provider/contract/key rejects.
8. Artifact `passed|verified|trusted|eligible|gate|system_executed` fields reject.
9. Exact cap boundaries pass; cap+1 fails for bytes, strings, keys, nesting, and member count.
10. ZIP traversal, absolute path, symlink, duplicate member, multiple member, compression bomb, malformed UTF-8/JSON, duplicate JSON key, NaN/Infinity, and wrong member name reject.
11. Target shape/normalization reuses Slice-30 behavior; private/local/IP/URL/credential/production targets reject.
12. Safe target hash is deterministic; audit projection contains no raw target/repo/version/log data.
13. Derived truth-tier labels never say `system_executed` under connector-observed option.
14. Gate ladder hits each rung in precedence order and only the exact final state passes.
15. Passing gate #10 leaves A5/go-live false when gates #12/#13 and pre-approval remain unmet.
16. Golden matrix proves gates #1-#9/#11-#13 unchanged.
17. `app/intake/readiness.py`, both no-go reasons, existing price/cost/deploy semantics, and findings-guard source contract remain unchanged.

### 9.2 Connector/service pure tests

1. `FakeSCMConnector` and `FakeDeployTargetConnector` only; no DNS/network in CI.
2. Exact repo/commit/artifact/contract arguments are passed; caller cannot override the workflow or artifact name.
3. Latest completed failed workflow with valid negative artifact supersedes older success.
4. Latest completed workflow missing its artifact records a failed attempt; it does not fall back.
5. Deploy probe occurs only for ruled staging target and after artifact observation; production target is impossible.
6. SSRF/broker/core/repo/target refusals are fail-closed with safe audit.
7. A safely attempted unavailable probe persists a negative staging snapshot and blocks the gate.
8. Connector artifact phase pass plus generic target-probe failure remains non-gate-eligible.
9. The generic probe is never described as version verification.
10. Secret/prose sentinel covers successful, negative, malformed, denied, and exception paths.

### 9.3 DB-backed tests

1. Migration `0050→0051→0050→0051` round trip with captured exit codes.
2. New tables have RLS ENABLE + FORCE; app role has SELECT/INSERT only; UPDATE/DELETE/TRUNCATE fail.
3. Cross-tenant/project candidate/core/snapshot/run/phase FKs fail under direct SQL.
4. Candidate/core mismatch, incomplete core, failed re-audit, missing/disagreed repo binding, and wrong commit refuse.
5. Production/caller-unverified/unavailable/stale/wrong-target staging snapshot refuses gate eligibility.
6. Forged artifact provenance or `system_executed` label fails.
7. Direct-SQL missing/extra/duplicate/wrong-order phase children fail at commit.
8. Direct-SQL forged A/B digest, phase target, time, health/operation flag, child digest, phase count, drill result, or gate eligibility fails at commit.
9. Infrastructure failed/refused attempt with children fails; observed succeeded attempt without exact children fails.
10. Valid negative artifact persists children but cannot be marked eligible.
11. Later failure/refusal supersedes older pass; a different binding never de-currents or satisfies the current binding incorrectly.
12. Candidate/core/repo/commit/target/manifest/contract change de-currents old pass.
13. No rollback TTL is applied; only content/binding and independent staging-snapshot freshness matter.
14. RLS prevents cross-tenant current-evidence leakage and count leakage.
15. Audit sentinel proves no target/repo/version/URL/log/secret/prose leakage.
16. `release_findings_guard()` MD5 remains `808036faf2660d6810aeca4342e6f1ac` before/after each migration leg.
17. Slice-30 deployment guard/provenance/availability rules remain intact; gate #2 results are unchanged with staging rows present.
18. Existing Slice-23/44/45 finding guard direct-SQL suites remain green untouched.
19. Golden full A5 matrix proves only gate #10 and ruleset version change.
20. Both `NO_GO_LIVE_REASONS` and literal hard-false go-live behavior remain exact.
21. Downgrade refuses while any Slice-52 row exists; after explicit test cleanup, downgrade succeeds and restores `0050` exactly.

### 9.4 Required pre-PR verification after implementation approval

Not run during plan drafting. Before any eventual PR:

```text
git diff --check
ruff
make test
make test-db
migration 0050→0051→0050→0051
```

Every command must have complete captured output and an explicit exit code. A truncated or interrupted run is a failed verification, not green.

---

## 10. Prospective file-touch map

Exact names may be adjusted only by reviewer/coordinator ruling; scope must not expand silently.

### New

- `app/release/rollback.py`
- `app/models/rollback_verification.py`
- `app/repositories/rollback_verifications.py`
- `migrations/versions/0051_rollback_verifications.py`
- `tests/test_rollback_verifications.py`

### Modified, narrowly

- `app/release/scm_connector.py` — one bounded rollback-artifact method and fake/live implementations.
- `app/release/project_repo.py` — strict canonical staging-target resolver, if ruled.
- `app/release/deploy_evidence_service.py` — staging refresh path sharing existing connector behavior, if ruled.
- `app/models/deployment_target_snapshot.py` — additive composite identity metadata only if required by FK; no semantic changes.
- `app/release/production_autonomy.py` — gate #10 and ruleset version only.
- `app/repositories/production_autonomy.py` — load current rollback evidence and pass safe inputs only.
- `app/models/__init__.py` and repository wiring as mechanically required.
- `.planning/SLICE-52-PLAN.md` — bind approved coordinator rulings before implementation.

### Byte-stable / semantically untouched

- `app/intake/readiness.py`
- `app/cost.py`, `app/runtime/engine.py`, `app/llm/pricing.py`
- findings/security/shortcut/acceptance/issue/reviewer-QA stores and guards
- evidence-pack core bytes and canonical schema asset
- release-verdict and cost-forecast semantics
- canonical template 16 under the recommended option
- both no-go reasons

---

## 11. Must NOT claim

The implementation, docs, audit, A5 context, commit, and PR **must not claim**:

1. that a rollback plan or runbook is a verified rollback;
2. that an empty evidence store, empty phase list, or reachable endpoint passes gate #10;
3. that UAID executed the remote rollback when it only observed a CI artifact;
4. that a CI artifact is a signature, cryptographic attestation, or proof its contents are true;
5. that a generic HTTPS probe verifies which version is serving;
6. that a staging drill proves a future production rollback will succeed;
7. that staging is topology-, data-, configuration-, traffic-, credential-, or provider-equivalent to production;
8. that the from-version is DB-proven deployed history or that A is a prior frozen candidate;
9. that a release candidate has a repo/commit FK;
10. that a rollback drill covers every feature, migration, state transition, integration, data restoration, or unknown failure mode;
11. that the §9.5.1 monthly archetype-eval cadence is a rollback-evidence TTL;
12. that a passed gate #10 satisfies A5, removes either no-go reason, grants production authority, or permits deployment;
13. that Slice 52 implements production pre-approval, emergency stop, automated production rollback, or the control loop;
14. that reported timestamps establish trusted clock truth;
15. that artifact/version/target/repo identifiers are safe to expose in audit or gate context;
16. that gate #2 deployment-target availability and gate #10 rollback verification are the same evidence;
17. that a later failed/refused run can be ignored in favor of an older pass;
18. that readiness changed from `slice20.v1` or go-live ceased to be hard-false.

---

## 12. Definition of done for a future implementation

Slice 52 will be complete only when all of the following are reviewer-verified:

- all OD-52-1…9 rulings are bound verbatim into this plan before code;
- implementation is on an approved feature branch under github-flow;
- migration `0051` is additive, round-trips, preserves all named guards, and fails closed on downgrade with live Slice-52 rows;
- the ruled connector/target/drill contracts are implemented without production access;
- DB constraints own exact phase coverage, truth fields, binding, and eligibility against direct-SQL attack;
- latest-wins/currentness cannot preserve stale passes;
- gate #10 alone gains its exact pass branch under `slice52.v1`;
- other gates, readiness, findings guard, both no-go reasons, and hard-false go-live are regression-proven unchanged;
- pure and DB-backed suites pass with full captured output and exit codes;
- no `.env` or `.pending-auth-captures.jsonl` is staged;
- the implementation PR is opened against `main` and paused for reviewer APPROVE/REJECT without merge.

---

## 13. Reviewer gate

Requested verdict: **APPROVE** or **REJECT** this plan only.

An **APPROVE** confirms the plan's source grounding and scope discipline but does not authorize implementation until the coordinator also rules every OD-52-1…9. A **REJECT** should identify exact lines/claims and the required correction. Until both conditions are satisfied, there must be no branch, code, migration, tests, commit, or PR for Slice 52.
