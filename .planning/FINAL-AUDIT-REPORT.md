# UAID OS — Final System Audit

**Audit mode:** owner-authorized assurance audit; repository read-only except this report.  
**Audit target:** `main` at `50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba`; Alembic head `0062`.  
**Audit date:** 2026-08-24 (Asia/Riyadh).  
**Final verdict:** **INCOMPLETE**.  
**Release-assurance disposition:** **REJECT**. Required specification capability is absent, **19/63 numbered slice exits are not met (20/39 detailed roadmap exit rows, counting 61a/61b separately)**, the full typecheck fails, and evidence shows bypassable approval/tenant/immutability/source-authority boundaries. This report proposes remediation slice numbers only; it does **not** authorize Slice 64, lift the roadmap stop, or authorize go-live.
**Audit-coverage status:** **INCOMPLETE for one mandatory dynamic sweep.** The static concurrency census found `122` conservative candidate writer endpoints. Fourteen ad-hoc two-session result records were captured—six report unhandled PostgreSQL `23505` conflict signatures and eight report conforming outcomes—but their exact pair-driver programs were not retained. Separately, the retained OD-11 test exercised one SQL-wrapper endpoint, so the audit actions touched `15/122` distinct candidates, retained reproducible audit-specific pair coverage is `1/122`, and `107/122` were untouched by those actions (§§4.6–4.7/F-020). The separately missing Slice-55 dynamic action was completed through the owned start/resume entry points after committing the latch: owned start rolled back cleanly, but owned resume called the cost evaluator once before returning `paused_emergency_stop`, so the product invariant failed (§4.4/F-008). No product-wide concurrency PASS is claimed.

## 0. Audit rules and evidence grammar

- A `PASS` is permitted only with a quoted probe/test result, `file:line`, or reachable Git SHA/PR evidence.
- A planning statement is evidence of intent only. It is never implementation or test evidence.
- Citation aliases used in dense tables are exact repository paths: `spec:<line>` means `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:<line>` and `roadmap:<line>` means `.planning/GO-LIVE-END-TO-END-ROADMAP.md:<line>`; `template <file>` and `schemas/<file>` resolve under `docs/UAID_OS_Intake_Template_Pack_v1_2/`; a bare `:<line>` inherits the file named earlier in that row or an explicit table-default file stated immediately above the table.
- `MUST` below means normative language (`must`, `required`, `only if`, `cannot`, `never`, or an unconditional “is complete only if”). `SHOULD` is advisory design language. `SHAPE` is a binding artifact/schema field even where the surrounding prose uses template language.
- The requirement inventory below was derived from the standalone specification and intake pack/schemas before application mapping. The roadmap, `CLAUDE.md`, and `README.md` were read for later consistency auditing but were not allowed to narrow this inventory.
- Compact rows are atomic enumerations: every semicolon-delimited item is independently mappable and independently capable of producing a gap.

### Phase-0 completeness census

An independent second read remained confined to the permitted documentation set and counted: **40/40 source files**, **30/30 numbered specification sections (§0–§29)**, **26/26 templates**, **7/7 binding schema assets**, **57/57 §26 phase components**, **25/25 Appendix-A readiness items**, **13/13 Appendix-B gates**, **16/16 Appendix-C controls**, **16/16 Appendix-D upgrades**, **16/16 §29 operating-model capabilities**, **13/13 §23.2 runtime properties**, and **28/28 §23.4 core data objects**. These counts are a completeness cross-check, not unique-requirement totals, because the lists overlap. Evidence: spec `:1-3040`; pack `docs/UAID_OS_Intake_Template_Pack_v1_2/README.md:1-5`; templates `00_project_manifest.yaml:1-13` through `25_prior_decisions_and_architecture_log.md:1-41`; reference companions `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/README.md:1-3` and `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md:1-24`; seven pack schemas; independent Phase-0 read log quoted in §4.

## 1. Documentation-only requirement inventory

### 1.1 System identity, creed, authority, and reasoning

| ID | Norm | Requirement inventory item | Documentation source |
|---|---|---|---|
| R-00-01 | MUST | Domain-agnostic control plane capable of any domain expressible through domain/regulatory packs, data contracts, acceptance criteria, and test oracles. | `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md:12-21` |
| R-00-02 | MUST | Full lifecycle: Intake → Understanding → Specification → Staffing → Planning → Build → Review → Test → Fix → Deploy → Verify → Go Live → Operate. | spec `:47-65` |
| R-00-03 | MUST | Seven responsibilities: understand project; compile build package; create correct team; execute delivery; verify independently; control authority; operate until stable. | spec `:55-65` |
| R-00-04 | MUST | Autonomous go-live only at R5 plus permitted A5; incomplete intake produces gaps/spec compilation/approval request/stop; no invented unsafe facts, fake integrations, weakened tests, or false completion. | spec `:25-42` |
| R-01-01 | MUST | Build only systems whose behavior is specifiable, testable, reviewable, deployable, monitorable, and governable through tools/evidence; otherwise specify or stop. | spec `:81-113` |
| R-02-01 | MUST | No-fake-done control rejects placeholders-as-real, production fake data, demo-only claims, hardcoded test outcomes, simulated-required integrations, skipped AC, weakened tests, silent fallbacks, swallowed errors, required-path TODOs/empties, local substitutes for required services, unevidenced ticket closure, and requirement weakening. | spec `:129-149`; template `19_autonomy_policy.yaml:14-15` |
| R-02-02 | MUST | Independent checker for every consequential output; multiple reviewers for high-risk work; builder cannot approve its own work. | spec `:151-159` |
| R-02-03 | MUST | Evidence, not narrative, decides done; supported evidence classes include diffs, executed tests, CI logs, API responses, browser recordings, UI screenshots, deployment logs, data checks, security scans, provenance chains, acceptance matrices, approvals, monitoring, and audit entries. | spec `:161-178` |
| R-02-04 | MUST | Unsupported factual/regulatory/analytical/safety/financial/decision-support claims fail closed and are classified as source-supported fact, calculation, hypothesis, assumption, unverified claim, human-approved judgment, or third-party assertion. | spec `:180-194` |
| R-02-05 | MUST | User documentation becomes executable requirements, stories, task contracts, architecture/domain/data constraints, agent context, AC, oracles, compliance/release gates, and evidence requirements. | spec `:196-211` |
| R-02-06a | MUST | Explicit approval by default: production deployment. | spec `:213-228` |
| R-02-06b | MUST | Explicit approval by default: merge to protected branches. | spec `:213-228` |
| R-02-06c | MUST | Explicit approval by default: delete data or infrastructure. | spec `:213-228` |
| R-02-06d | MUST | Explicit approval by default: change secrets. | spec `:213-228` |
| R-02-06e | MUST | Explicit approval by default: modify billing or paid resources. | spec `:213-228` |
| R-02-06f | MUST | Explicit approval by default: communicate with real users. | spec `:213-228` |
| R-02-06g | MUST | Explicit approval by default: access sensitive customer data. | spec `:213-228` |
| R-02-06h | MUST | Explicit approval by default: accept legal, regulatory, clinical, financial, or safety risk. | spec `:213-228` |
| R-02-06i | MUST | Explicit approval by default: bypass a failed gate. | spec `:213-228` |
| R-02-06j | MUST | Explicit approval by default: weaken test or review standards. | spec `:213-228` |
| R-02-07 | MUST | Dynamic specialist selection/creation with independent reviewers; no fixed generic-agent assumption. | spec `:230-236` |
| R-03-01 | MUST | Consequential decisions pass the five-stage Al-Muhasibi wrapper: Khawatir, Muraqaba, Mujahada, Muhasaba, final output. | spec `:238-260` |
| R-03-02 | SHOULD | Consequential-decision record contains decision identity/type, proposal, initial rationale, risks, challenges, evidence, verdict, conditions, and reviewers. | spec `:262-287` |
| R-03-03 | MUST | Sanad chain contains claim, narrator chain, source-reliability scoring, content-consistency check, context boundary, verdict, and evidence link. | spec `:289-336` |
| R-03-04 | MUST | Evidence pack consumable by independent assurance/audit/certification/regulatory/customer/governance bodies without a named-certifier dependency. | spec `:338-342` |

### 1.2 Intake, readiness, autonomy, compiler, and authorship

| ID | Norm | Requirement inventory item | Documentation source |
|---|---|---|---|
| R-04-01 | MUST | Intake answers purpose, value, users, scope, domain, data, integrations, environments, tools, authority, success, go-live readiness, and risky-decision approvers. | spec `:344-364` |
| R-04-02 | MUST | Alternate intake formats compile into the 26-file canonical package enumerated in §1.6 below. | spec `:366-397`; pack `docs/UAID_OS_Intake_Template_Pack_v1_2/README.md:1-5` |
| R-04-03 | MUST | Readiness ladder R0–R5 with the exact meaning and allowed behavior in §4.3. | spec `:399-408` |
| R-04-04 | MUST | Non-R5 behavior selects: compile missing docs; ask a specific decision; create blocker; or make only a policy-permitted low-risk safe assumption. | spec `:410-419` |
| R-04-05 | MUST | Every generated assumption is labelled safe, needs approval, unsafe-blocked, or unknown-cannot-proceed. | spec `:421-428` |
| R-04-06 | MUST | Intake report fields: project, readiness, staging/go-live booleans, missing-for-go-live, safe assumptions, blocked assumptions. | spec `:430-455` |
| R-05-01 | MUST | Separate autonomy ladder A0–A5 with exact authority boundaries; A5 production only when every pre-approved gate passes and no blocker exists. | spec `:457-470` |
| R-05-02 | MUST | Authority matrix covers docs, draft PRD, project tasks, repo, branches/commits, PRs, tests, staging, protected merge, production, deletion, secrets, billing, sensitive data, and failed-gate override with the stated default levels/controls. | spec `:472-490` |
| R-05-03 | SHAPE | Autonomy policy stores level/run mode, allow flags, required approvals, and stop conditions; the canonical template also fixes `no_fake_done=true` and `no_silent_fallbacks=true`. | spec `:492-527`; template `19_autonomy_policy.yaml:1-15` |
| R-06-01 | MUST | Compiler accepts strategy, commercial, product, architecture, regulatory, data dictionary, diagram, policy, runbook, design, source, spreadsheet, API, contract, and Jira/GitHub inputs. | spec `:529-553` |
| R-06-02 | MUST | Pipeline: classification; source/authority mapping; requirement extraction; contradiction detection; gap detection; spec generation; domain/data/AC/oracle compilation; backlog; skill requirements; readiness report. | spec `:555-572` |
| R-06-03 | MUST | Outputs: manifest, PRD, architecture, data model, domain pack, integration plan, AC, oracle pack, backlog, task contracts, skill map, tool plan, risk register, evidence requirements, go-live checklist. | spec `:574-592` |
| R-06-04 | MUST | Conflicts classified as wording, scope, business rule, technical, legal/regulatory, security, budget/timeline, or authority; never silently selected; decision request or provenance-backed proposal emitted. | spec `:594-609` |
| R-06-05 | MUST | Spec Generation Mode can produce missing PRD, design options, data contracts, AC, oracles, backlog, domain drafts, go-live drafts, and risk drafts; generated specs remain non-binding pending §7 controls. | spec `:611-629` |
| R-07-01 | MUST | System-authored AC cannot bind verification until independently reviewed and approved. | spec `:631-641` |
| R-07-02 | MUST | Every AC has one provenance status: user-authored, user-normalized, system/human-approved, system/independent-approved, system-unapproved, or disputed, with stated verification weight. | spec `:643-654` |
| R-07-03 | MUST | Binding generated AC requires human owner, independent lineage, domain authority, or stable reference/contract oracle. | spec `:656-665` |
| R-07-04 | MUST | Independence means different role, prompt family, reviewer authority, and for high risk a different route/provider when available; a prompt family needs distinct template root, authoring lineage, and eval suite. | spec `:667-674` |
| R-07-05 | MUST | Evidence pack records AC authorship, generator, approver, approval time, and verification status. | spec `:675-690` |

### 1.3 Skill matching, Agent Factory, taxonomy, tools, and delivery workflow

| ID | Norm | Requirement inventory item | Documentation source |
|---|---|---|---|
| R-08-01 | MUST | Skill matching considers stack, domain, data, legal/regulatory, AI/ML, UX, integrations, risk, reviewers, oracle type, tools, cost, and speed. | spec `:692-711` |
| R-08-02 | MUST | Traceable graph Project → requirement → task → skill → capability → tool access → reviewer → evidence; supports all named skill categories in §8.2. | spec `:713-749` |
| R-08-03 | SHOULD | Transparent score exactly: capability .30 + domain .15 + tool .15 + eval .20 + reviewer .10 + cost/latency .10 − risk penalty; high-risk favors reliability. | spec `:751-766` |
| R-08-04 | MUST | Project squad manifest records active agents, roles, tasks, reviewers, missing skills, and factory requests. | spec `:768-797` |
| R-09-01 | SHAPE | Agent realization binds ID, role, mission, prompt family/template, task-contract interface, tool allowlist, context/memory/model-routing policies, authority limits, reviewer linkage, eval suite, budget, observability, version. | spec `:799-829`; `schemas/agent_realization_template.yaml:1-17` |
| R-09-BP | SHAPE | Agent blueprint binds ID, role, mission, system-prompt template, allowed and denied tools, included and excluded context, reviewer roles, archetype/project eval suite, and authority including reject-PR/mark-done limits. | spec `:831-874` |
| R-09-02 | MUST | Factory workflow: search registry; select archetype if absent; bind components; generate project cases; dry qualify; Agent-QA and Security review; register; monitor; reconfigure/split/replace/escalate. | spec `:876-889` |
| R-09-03 | MUST | Archetype library covers builder, reviewer, security, data, domain, prompt, KG/RAG, AI-eval, integration, deployment/SRE, evidence-auditor roles, each with representative tasks, gold/oracle, rubric, threshold, refresh. Exact activation floors: builder 80–90% risk-adjusted plus zero critical shortcut failures; reviewer critical recall ≥90%; security zero missed critical and high-severity recall ≥85%; data all critical contracts; domain zero critical unsupported-authority claims; prompt aggregate ≥85% and no critical loophole; KG project precision/recall floor and zero critical unsupported facts; AI-eval plan ≥85% and no missing critical metric; connector 100% critical contract tests and aggregate ≥85%; deployment zero critical deploy/rollback failures and aggregate ≥85%; evidence-auditor critical-evidence recall ≥95%. | spec `:891-930`; `schemas/archetype_eval_methodology.yaml:1-9` |
| R-09-04 | MUST | Eval corpus includes positive, negative, edge, adversarial, and incomplete-input cases; results versioned; below-threshold agents cannot activate. | spec `:930-930` |
| R-09-05 | MUST | Repeated-failure policy diagnoses missing skill, weak instructions, wrong tools, poor model, overload, repeated reject, safety violation, or persistent inability, and applies the corresponding response. | spec `:932-945` |
| R-09-06 | MUST | Agent version immutable once used; changes create new version; snapshot includes route plus prompt/tool/context/eval hashes and active run. | spec `:947-963` |
| R-10-01 | MUST/SHOULD | Core-company taxonomy: Delivery Commander, CTO, Product Manager, Business Analyst, Project Manager, Chief Quality Officer, Release Manager, Delivery Auditor. | spec `:965-978` |
| R-10-02 | MUST/SHOULD | Engineering taxonomy: Solution Architect, Frontend, Backend, Data, Database, Mobile, Integration, DevOps/SRE, Performance, Accessibility. | spec `:980-993` |
| R-10-03 | MUST/SHOULD | AI taxonomy: AI Systems Architect, AI Engineer, Prompt Engineer/Reviewer, Evals, Model Routing, RAG, Knowledge Graph, Agent Framework, MCP/Tooling, LLM Security. | spec `:995-1009` |
| R-10-04 | MUST/SHOULD | Review taxonomy: Specialist Reviewer, QA, QA Reviewer, Security Reviewer, Shortcut Detector, Acceptance Verifier, Test Oracle Reviewer, Evidence Pack Auditor, Go-Live Readiness. | spec `:1011-1023` |
| R-10-05 | MUST | Domain roles generated from domain-pack demand rather than hardcoded; examples in §10.5 are illustrative, not fixed. | spec `:1025-1044` |
| R-10-06 | SHOULD | MVP includes Delivery Commander, Compiler, Product/BA, Architect, Frontend/Backend/Data/DevOps, QA, Security, Shortcut, Acceptance, Evidence Auditor, Skill Matching, and Agent Factory. | spec `:1046-1065` |
| R-11-01 | MUST | All external tool calls traverse the Tool Broker; it enforces auth, least privilege, per-agent allowlists, input/output validation, rate/cost controls, approvals, audit, tenancy. | spec `:1067-1084` |
| R-11-02 | MUST | Tool categories: PM, source control, CI/CD, cloud, secrets, communications, browser tests, API tests, data tests, monitoring, documentation. | spec `:1086-1100` |
| R-11-03 | MUST | Every connector has permission manifest, auth method, tenant scope, allowed/denied operations, classification, audit policy, tests, owner, and incident contact. | spec `:1102-1117` |
| R-11-04 | SHAPE | Tool contract carries name, input schema, authority, approval flag, audit level, and forbidden conditions. | spec `:1119-1144` |
| R-12-01 | MUST | End-to-end 21-step delivery flow from intake sandbox through post-launch stabilization, including independent reviews and policy-gated production. | spec `:1146-1172` |
| R-12-02 | MUST | Iterative build→review→reject→fix→retest→verify loops; partial release only under policy with explicit included/excluded scope. | spec `:1174-1182` |
| R-12-03 | MUST | Board supports the 15 named states; builder cannot move own work to Done. | spec `:1184-1207` |
| R-12-04 | MUST | Every PR has task link/contract, summary, AC coverage, tests, evidence, limitations, fallbacks, security notes, rollback notes; merge requires checks and reviewers. | spec `:1209-1226` |
| R-13-01 | MUST | Three review layers: role-specific, cross-functional, acceptance. | spec `:1228-1236` |
| R-13-02 | SHAPE | Task contract includes source requirements, must-have/not-do, AC, oracles, evidence, tools, builder/reviewers, risk, DoD. | spec `:1238-1272`; spec `:2546-2566` |
| R-13-03 | MUST | Structured reviewer verdict includes verdict, summary, failed criteria, suspected shortcuts, required changes, and merge decision. | spec `:1274-1296` |
| R-13-04 | MUST | Shortcut detector checks hardcoding, static/fake behavior, disabled validation, weakened tests, broad error swallowing, placeholder UI, required-path TODOs, local substitutes, skipped AC, implementation-detail tests, and evidence-free readiness. | spec `:1298-1313` |
| R-13-05 | MUST | Reviewer QA: different route/provider policy; primary-evidence review; planted defects; miss metrics; suspension/requalification thresholds; blind reviews; human calibration. | spec `:1315-1347` |
| R-13-06 | SHAPE | Binding reviewer thresholds: planted sample `0.05`, maximum critical miss `0.00`, maximum false approval `0.03`; high-risk single-provider compensation required. | `schemas/reviewer_quality_assurance.yaml:1-10` |

### 1.4 Oracles, evidence, security, tenancy, UX, cost, domain, tools, and change control

| ID | Norm | Requirement inventory item | Documentation source |
|---|---|---|---|
| R-14-01 | MUST | Every critical feature has a classified specified/reference/judgment oracle with the stated controls. | spec `:1349-1363` |
| R-14-02 | MUST | Judgment oracles have rubric, representative/adversarial samples, blind/independent review, ≥2 evaluator lineages for high impact, disagreement handling, threshold, calibration, failure limits, and authority review as required. | spec `:1365-1378` |
| R-14-03 | SHAPE | Default judgment values are sample size `100`, pass rate `0.85`, IRR `0.70`, explicitly risk-tunable rather than universal. | spec `:1380-1405`; template `09_test_oracles.yaml:1-14` |
| R-14-04 | MUST | No valid critical oracle means draft/staging only, never production-ready. | spec `:1407-1411` |
| R-15-01 | MUST | Evidence pack is the artifact of done and carries scope, end-to-end traceability, build artifacts, tests/reviews, provenance, approvals, deployment, limitations, blockers. | spec `:1413-1472` |
| R-15-02 | MUST | DoD has all 13 conditions: implemented AC; tests exist/pass; no fake/fallback; specialist/QA/security/shortcut/acceptance approvals; pack updated; PR merged properly; deployment status matches. | spec `:1474-1490` |
| R-15-03 | MUST | Export formats: schema-valid JSON; human-readable MD/PDF; signed hash/timestamp/signer manifest; read-only link/archive; optional OSCAL. | spec `:1492-1504` |
| R-15-04 | MUST | Export crypto: per-file hashes; release-authority or tenant-key signature; mutation invalidation; logged read-only access; redacted packs preserve original hash refs. | spec `:1538-1546` |
| R-15-05 | SHAPE | Binding checked-in evidence schema requires version, project, release, time, scope, traceability, verdict, signatures; optional test/review/QA/risk/provenance/audit fields; exact four-value verdict enum. | `schemas/evidence_pack_schema.json:1-65` |
| R-16-01 | MUST | Product-security review covers authn/authz/RBAC, secrets, validation, dependencies/supply chain, privacy, logging/audit, rate limits, encryption, backup/restore, tenancy, incident response, secure deploy. | spec `:1548-1568` |
| R-16-02 | MUST | Intake injection defense: sandbox, instruction/data split, scan, content labels, hierarchy, no document override, reviewer check, quarantine. | spec `:1570-1587` |
| R-16-03 | MUST | Tool escalation defense: broker/allowlist, scoped credentials, approvals, unknown deny, param validation, audit, suspension. | spec `:1589-1602` |
| R-16-04 | MUST | Gap-resolution defense: unsafe assumptions blocked, authority sources for high-risk facts, risk labels, visible assumptions, high-risk approval. | spec `:1604-1614` |
| R-16-05 | MUST | Audit defense: append-only hash/evidence trail, external sink, writer/admin separation, reviewer read-only access, pre-release tamper checks. | spec `:1616-1627` |
| R-16-06 | MUST | Lineage/collusion defense, different routes/providers, explicit degraded fallback, blind/random review, delivery-auditor separation check; high-risk fallback additionally needs human/external authority/risk acceptance and disclosure. | spec `:1629-1661` |
| R-16-07 | MUST | Generated agents require Agent-QA and Security approval, eval gate, deny-production default, immutable version, kill switch. | spec `:1663-1674` |
| R-16-08 | MUST | Connector/supply-chain controls: signed versions, tests, permission manifest, secret isolation, dependency scan, activation approval, anomaly detection. | spec `:1676-1690` |
| R-17-01 | MUST | Tenant isolation covers identities, documents, prompts, memory, vector/graph stores, repositories, credentials, cloud, audit, evidence, cost, communications. | spec `:1692-1714` |
| R-17-02 | MUST | No cross-tenant retrieval/summary/comparison/reuse absent explicit reviewed cross-tenant policy. | spec `:1716-1718` |
| R-17-03 | MUST | Agent instances, context, memory, and tool grants tenant-scoped; only blueprints may be global. | spec `:1720-1723` |
| R-17-04 | MUST | Cross-project learning permits only the seven listed anonymized aggregate classes and forbids the ten listed tenant-content classes without consent/security review. | spec `:1724-1748` |
| R-17-05 | MUST | Any beyond-aggregate content use requires consent artifact, data classification, retention, removal; sovereign/regulated/high-confidential defaults to none. | spec `:1750-1752` |
| R-18-01 | SHOULD | Approval UX groups low-risk digest, medium decision bundle, high-risk realtime, formal production pack, immediate rollback alert. | spec `:1754-1770` |
| R-18-02 | SHOULD | Missing-info interview has five rounds; avoids answered questions; explains why/impact. | spec `:1772-1784` |
| R-18-03 | MUST | Mid-run correction freezes work, impact-maps requirements/code/tests/evidence, creates CR, estimates impact, gates consequential change, resumes traceably. | spec `:1786-1795` |
| R-18-04 | MUST | Nonresponse: low safe proceed after 24h; medium pause after 24h; high/production block; escalation chain. | spec `:1797-1811`; template `20_human_approval_policy.yaml:1-16` |
| R-18-05 | SHOULD | Owner dashboard shows run state, approvals, blockers, consumed/forecast cost, critical path, readiness, evidence status, high-risk findings, deployment, next action. | spec `:1813-1828` |
| R-18-06 | MUST/Surface | Human-facing owner dashboard/web UI implementing the §18.6 information surface, not merely data stores. | spec `:1813-1828`; spec §26.1 `:2432-2446` (“basic dashboard”) |
| R-19-01 | MUST | Cost ledger covers model, tools, cloud, CI, storage/retrieval, monitoring, human review, rework. | spec `:1830-1849` |
| R-19-02 | MUST | Per-phase budgets for intake, planning, build, review, test/fix, deployment, monitoring. | spec `:1851-1863` |
| R-19-03 | SHOULD | Risk-aware model-routing policy for nine named task classes. | spec `:1865-1879` |
| R-19-04 | MUST | Risk-adjusted review intensity; high intensity for security, payments, privacy, regulation, production, deletion, irreversibility, AI decisions, and high-risk claims. | spec `:1891-1913` |
| R-19-05 | SHAPE | Cost controls include total/daily/model/cloud/CI ceilings; 20% forecast approval default; stop on budget, repeated no-strategy failure, tool loop, prolonged provider outage. | spec `:1915-1935`; template `21_cost_and_resource_policy.yaml:1-15` |
| R-20-01 | SHAPE | Domain pack implements all fields in §20.2 and template 10: authorities/entities/jurisdiction, entities/lexicon/rules/formulas/standards, sensitivity/localization, per-decision authorities, scenarios, prohibited assumptions, open questions. | spec `:1937-2037`; template `10_domain_pack.yaml:1-40` |
| R-20-02 | MAY | Reference-intake companion library demonstrates generality without constraining core architecture. | spec `:2039-2044`; reference contract `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/README.md:1-3`; bounded example `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md:1-24` |
| R-21-01 | MUST | Tool gaps classified into existing/similar/public/private/no-API/unsafe with exact response rules. | spec `:2045-2060` |
| R-21-02 | MUST | New tool workflow: identify, specify contract, security review, build server, contract test, owner activation, broker registration, controlled use. | spec `:2062-2073` |
| R-21-03 | MUST | Each new connector produces interface, permissions, tests, sandbox evidence, security review, classification, error/audit policy, owner/escalation. | spec `:2075-2089` |
| R-22-01 | MUST | During-run snapshot: route, prompt hash, blueprint version, tool hash, context policy, eval version, dependencies, schemas. | spec `:2091-2108` |
| R-22-02 | MUST | Voluntary upgrade requires CR, reason, affected scope, requalification, regression, rollback, and approval if critical. | spec `:2110-2120` |
| R-22-03 | MUST | Forced deprecation pauses, selects successors, requalifies, regression-compares, limits transition work, gates resume on QA/Auditor, and discloses. | spec `:2122-2132`; `schemas/model_change_policy.yaml:1-11` |
| R-22-04 | MUST | Requalify on route, prompt, tool, context, eval, material domain, AC, or release-candidate changes. | spec `:2134-2147` |

### 1.5 Runtime, release, operations, phase components, external assurance, completeness

| ID | Norm | Requirement inventory item | Documentation source |
|---|---|---|---|
| R-23-01 | MUST | Control plane contains project state, workflow runtime, agent/skill/tool registries, policy/approval/evidence/audit/cost stores, tenant manager, run dashboard. | spec `:2149-2166` |
| R-23-02 | MUST | Durable runtime properties: persistence, resume, retry/backoff, external idempotency, human waits, cancel/pause, audit, cost, recovery, events, tool-result persistence, versioned agent runs, deterministic replay. | spec `:2168-2186` |
| R-23-03 | MUST | Main loop implements every listed read/inspect/staff/build/PR/CI/review/shortcut/acceptance/evidence/rework/cost-authority/staging/go-live step, then production deploy and stabilization only under gate+policy. | spec `:2188-2212` |
| R-23-04 | MUST | State model includes all **28** named collections: organizations, tenants, users, projects, project runs, documents, requirements, acceptance criteria, test oracles, assumptions, decisions, agents, agent versions, agent runs, skills, task contracts, issues, pull requests, test results, review reports, evidence packs, approvals, deployments, audit logs, cost events, tool calls, connectors, and incidents. | spec `:2214-2247` |
| R-24-01 | MUST | Go-live conjuncts: R5/limited scope; policy release permission; critical AC/oracles; no critical security/shortcut; complete pack; verified rollback; active monitoring; approvals; all open issues nonblocking or risk-accepted. | spec `:2249-2268` |
| R-24-02 | MUST | Risk exception requires every issue signed by approval-matrix approvers; critical security, fake-done, rollback, or regulated/safety authority gaps remain barred absent relevant human authority plus policy override. | spec `:2269-2285` |
| R-24-03 | MUST | Readiness checklist implements product, engineering, AI/data, security, operations, governance entries and exact required/conditional thresholds. | spec `:2287-2330`; template `23_go_live_checklist.yaml:1-11` |
| R-24-04 | MUST | Release verdict vocabulary: passed, passed-with-limitations, blocking failure, missing-evidence failure, human-decision, not-applicable. | spec `:2332-2343` |
| R-25-01 | MUST | Stabilization definition includes duration, owner/support owner, journeys, criteria, escalation, closure authority; reflected in go-live checklist. Binding default duration is 14 days. | spec `:2345-2361`; `schemas/stabilization_window_policy.yaml:1-13` |
| R-25-02 | MUST | Monitor eleven signals: uptime, errors, latency, jobs, security, journeys, data quality, cost, model drift, support, incidents. | spec `:2363-2375` |
| R-25-03 | MUST | Post-launch actions cover bug ticket, log diagnosis, patch branch, hotfix PR, staging hotfix, approval/A5 production hotfix, approval/preapproved rollback. | spec `:2377-2389` |
| R-25-04 | SHOULD | Continuous improvement updates lessons, failure patterns, evals, prompts, domain gaps, oracle gaps, forecasts, connector scores. | spec `:2391-2402` |
| R-25-05 | MUST | Before-release stabilization policy and exit enforcement include zero critical incidents, error budget, p95, security alerts, backup/restore, support handover, closure authority; failures create tickets and extension. Binding defaults require 3 zero-critical-incident days, error budget under threshold, active monitoring, zero rollback blockers, and complete handover. | spec `:2404-2426`; `schemas/stabilization_window_policy.yaml:7-13` |
| R-26-01 | MUST | Phase 1 components: tenant isolation, state store, durable runtime, broker, audit, approval, cost, sandbox, basic dashboard, registry, policy. | spec `:2430-2446` |
| R-26-02 | MUST | Phase 2: classifier, extractor, gap/contradiction, readiness, artifact generator, template pack, Sanad store. | spec `:2448-2459` |
| R-26-03 | MUST | Phase 3: PM, source control, PR, CI/CD, staging, communications/approval, secret verification, monitoring. | spec `:2461-2472` |
| R-26-04 | MUST | Phase 4: skill graph, blueprint registry, realization, archetype eval, Agent QA, generated-agent security, performance, replacement. | spec `:2474-2485` |
| R-26-05 | MUST | Phase 5: maker-checker-verifier, task contracts, reports, oracle framework, shortcut detector, acceptance verifier, evidence auditor, go-live agent. | spec `:2487-2498` |
| R-26-06 | MUST | Phase 6: release manager, production approval, rollback, post-launch monitoring, incident workflow, acting self-healing/hotfix loop, continuous-improvement engine. | spec `:2500-2510` |
| R-26-07 | MUST | Phase 7: vetted blueprint marketplace, connector library, reference-intake library, assurance export, advanced optimizer, tenant-safe learning, enterprise admin. | spec `:2512-2522` |
| R-27-01 | SHAPE | Canonical `build_readiness_report.json` contains project/readiness, requested and allowed autonomy levels, build/staging/production booleans, missing artifacts, unsafe/safe assumptions, blocked decisions, and recommended next action. | spec `:2568-2585` |
| R-28-01 | MUST | Stable external-assurance export contract with scope, three traceability maps, artifact refs, reviews/QA/routes/fallback, risk, approvals, integrity, and auditor-access fields. | spec `:2832-2902` |
| R-28-02 | MUST | JSON default + published schema/migrations; optional OSCAL when required; signed hashes; read-only scoped/temp/offline access; safe references/redaction; version/time/key/log policy; validation fails evidence gate. | spec `:2904-2914` |
| R-29-01 | MUST | Accept any serious project-documentation package. | spec `:2918-2924` |
| R-29-02 | MUST | Determine whether the package is build-ready. | spec `:2918-2925` |
| R-29-03 | MUST | Compile missing specifications where safe. | spec `:2918-2926` |
| R-29-04 | MUST | Block unsafe missing decisions. | spec `:2918-2927` |
| R-29-05 | MUST | Create a project-specific specialist team. | spec `:2918-2928` |
| R-29-06 | MUST | Create new agents mechanically through governed blueprints. | spec `:2918-2929` |
| R-29-07 | MUST | Set up delivery tools, repositories, workflows, tests, and environments. | spec `:2918-2930` |
| R-29-08 | MUST | Build through controlled iterations. | spec `:2918-2931` |
| R-29-09 | MUST | Require independent review for every consequential output. | spec `:2918-2932` |
| R-29-10 | MUST | Detect shortcuts and fake completion. | spec `:2918-2933` |
| R-29-11 | MUST | Verify behavior through valid test oracles. | spec `:2918-2934` |
| R-29-12 | MUST | Track claims through Sanad-style provenance chains. | spec `:2918-2935` |
| R-29-13 | MUST | Produce an evidence pack as the artifact of done. | spec `:2918-2936` |
| R-29-14 | MUST | Control cost, authority, tenancy, security, and tool access. | spec `:2918-2937` |
| R-29-15 | MUST | Deploy to production only when approved policy and evidence permit it. | spec `:2918-2938` |
| R-29-16 | MUST | Monitor and stabilize after launch. | spec `:2918-2939`; the final rule is compile/clarify/block and never fake certainty/completion/readiness `:2941-2947` |

### 1.6 Canonical 26-file intake artifact inventory

Every row is independently required for an R5 canonical package; alternate input formats do not remove the compiled artifact requirement.

| ID | Required artifact | Required content/surface | Source |
|---|---|---|---|
| T-00 | `project_manifest.yaml` | identity, owners, outcome/date, repo/PM/comms preferences, readiness/autonomy targets | spec `:368-397`; template `00_project_manifest.yaml:1-13` |
| T-01 | `product_brief.md` | build, audience, value, boundaries | template `01_product_brief.md:1-9` |
| T-02 | `business_objectives.md` | goals, success, value hypothesis, deadlines/constraints | template `02_business_objectives.md:1-9` |
| T-03 | `scope_and_boundaries.md` | in/out, assumptions, non-goals | template `03_scope_and_boundaries.md:1-9` |
| T-04 | `users_roles_permissions.md` | personas, roles, permission matrix, restricted actions | template `04_users_roles_permissions.md:1-9` |
| T-05 | `user_journeys_and_workflows.md` | critical/operational/approval/failure flows | template `05_user_journeys_and_workflows.md:1-9` |
| T-06 | `functional_requirements.md` | stable IDs, requirement, priority, source, notes | template `06_functional_requirements.md:1-6` |
| T-07 | `non_functional_requirements.md` | performance, reliability, scalability, accessibility, maintainability, availability | template `07_non_functional_requirements.md:1-13` |
| T-08 | `acceptance_criteria.yaml` | requirement link, text, six-value authorship, risk, verification method | template `08_acceptance_criteria.yaml:1-7` |
| T-09 | `test_oracles.yaml` | type, target, expected/reference, tolerance, sample/pass/IRR policy, reviewers | template `09_test_oracles.yaml:1-14` |
| T-10 | `domain_pack.yaml` | full §20 domain fields and per-decision authorities | template `10_domain_pack.yaml:1-40` |
| T-11 | `data_model_and_contracts.yaml` | entities, schemas, relations, validation, retention, lineage | template `11_data_model_and_contracts.yaml:1-7` |
| T-12 | `integrations_and_external_systems.yaml` | name/type/environment/auth/docs/owner/risk | template `12_integrations_and_external_systems.yaml:1-8` |
| T-13 | `existing_assets_and_repositories.yaml` | repos/docs/data/designs/legacy/credential locations | template `13_existing_assets_and_repositories.yaml:1-7` |
| T-14 | `architecture_and_technology_constraints.md` | required/preferred/forbidden stack, cloud, architecture | template `14_architecture_and_technology_constraints.md:1-11` |
| T-15 | `security_privacy_compliance.md` | data, threats, obligations, audit, privacy | template `15_security_privacy_compliance.md:1-11` |
| T-16 | `environments_and_deployment_targets.yaml` | local/dev/staging/production cloud-region-domain and approval | template `16_environments_and_deployment_targets.yaml:1-9` |
| T-17 | `secrets_and_credentials_manifest.yaml` | references only, owners, rotation, manager; no values | template `17_secrets_and_credentials_manifest.yaml:1-5` |
| T-18 | `tool_access_manifest.yaml` | GitHub/Jira/Slack/cloud/CI/monitoring/other tools | template `18_tool_access_manifest.yaml:1-8` |
| T-19 | `autonomy_policy.yaml` | allow/approval plus no-fake-done/no-silent-fallback | template `19_autonomy_policy.yaml:1-15` |
| T-20 | `human_approval_policy.yaml` | channel, digest/batching, realtime classes, nonresponse, approvers | template `20_human_approval_policy.yaml:1-16` |
| T-21 | `cost_and_resource_policy.yaml` | four ceilings, 20% threshold, routing flags, four stops | template `21_cost_and_resource_policy.yaml:1-15` |
| T-22 | `operations_observability_support.md` | monitoring/logs/alerts/runbooks/incidents/support/stabilization | template `22_operations_observability_support.md:1-25` |
| T-23 | `go_live_checklist.yaml` | product/engineering/AI/security/ops plus four governance gates | template `23_go_live_checklist.yaml:1-11` |
| T-24 | `risk_register_and_assurance_requirements.md` | risk, severity, owner, mitigation, evidence, status | template `24_risk_register_and_assurance_requirements.md:1-4` |
| T-25 | `prior_decisions_and_architecture_log.md` | active/rejected decisions, migration constraints, incidents, ownership | template `25_prior_decisions_and_architecture_log.md:1-41` |

### 1.7 Binding schema assets

| ID | Binding requirement | Source |
|---|---|---|
| S-AR | Agent realization 16-field shape. | `schemas/agent_realization_template.yaml:1-17` |
| S-AE | Eleven archetypes; tasks, gold source, rubric, threshold, refresh; adversarial and edge cases required. | `schemas/archetype_eval_methodology.yaml:1-9` |
| S-EP | Evidence-pack JSON schema and exact required fields/verdict enum. | `schemas/evidence_pack_schema.json:1-65` |
| S-MC | Pin during run; forced-deprecation pause/candidate/requalify/regression/QA-resume; short- and extended-provider-outage behavior. | `schemas/model_change_policy.yaml:1-11` |
| S-RQA | Route/provider separation, degraded fallback and human compensation, `0.05`/`0.00`/`0.03` thresholds. | `schemas/reviewer_quality_assurance.yaml:1-10` |
| S-RA | Risk record fields: IDs, severity, affected requirements, reason, controls, expiry, owner/approver/authority, rollback, evidence. | `schemas/risk_acceptance_record.yaml:1-14` |
| S-SW | Stabilization fields/defaults: 14-day duration; owner/support/journeys; error budget; 3 zero-critical-incident days; error budget under threshold; monitoring active; `rollback_blockers_open: 0`; handover complete; closure approver. | `schemas/stabilization_window_policy.yaml:1-13` |

### 1.8 Appendix-B A5 gates (all 13 are atomic)

| Gate | Normative pass condition | Source |
|---|---|---|
| A5-01 | R5 intake complete | spec `:2981-2997` |
| A5-02 | Production target available | spec `:2981-2997` |
| A5-03 | Branch protection and required checks active | spec `:2981-2997` |
| A5-04 | All critical test oracles pass | spec `:2981-2997` |
| A5-05 | No unaccepted critical security findings | spec `:2981-2997` |
| A5-06 | No unaccepted critical shortcut findings | spec `:2981-2997` |
| A5-07 | Remaining issues have approved risk acceptance | spec `:2981-2997` |
| A5-08 | No unapproved generated AC gate critical release | spec `:2981-2997` |
| A5-09 | Cost forecast within policy | spec `:2981-2997` |
| A5-10 | Rollback verified | spec `:2981-2997` |
| A5-11 | Monitoring and alerts active | spec `:2981-2997` |
| A5-12 | Production deployment explicitly conditionally pre-approved | spec `:2981-2997` |
| A5-13 | Emergency stop/rollback authority exists | spec `:2981-2997` |

### 1.9 Appendix-A R5 and Appendix-C platform-self-defense atomic inventories

| ID | Atomic requirement | Source |
|---|---|---|
| R5-01..05 | Purpose clear; scope explicit; roles defined; permission matrix; workflows documented. | spec `:2951-2979` |
| R5-06..10 | Functional and nonfunctional requirements; approved critical AC; critical oracles; adequate domain pack. | spec `:2951-2979` |
| R5-11..15 | Data contracts; integrations; environments; secret-manager refs; tool access. | spec `:2951-2979` |
| R5-16..20 | Autonomy, approval, cost, security/privacy, and go-live checklist approved/documented. | spec `:2951-2979` |
| R5-21..25 | Rollback, monitoring, risk review, prior-decision review when relevant, explicit production authority. | spec `:2951-2979` |
| C-01..04 | Documents untrusted; injection contained; broker used; per-agent least privilege. | spec `:2999-3016` |
| C-05..08 | Append-only tamper-evident audit; lineage separation; planted-defect QA; degraded fallback marked/compensated. | spec `:2999-3016` |
| C-09..12 | Tenant-safe learning; generated-agent security; tenant boundaries; connectors tested and permission-scoped. | spec `:2999-3016` |
| C-13..16 | Secrets constrained; unsafe assumptions blocked; cost stops; production overrides explicitly authorized. | spec `:2999-3016` |

### 1.10 Appendix-D v1.2 atomic upgrade inventory

| ID | Atomic requirement | Source |
|---|---|---|
| D-01..04 | Reviewer QA; formal archetype methodology; degraded single-provider fallback; signed/versioned evidence export. | spec `:3018-3039` |
| D-05..08 | Risk-acceptance path; forced model deprecation; tenant-safe learning boundary; illustrative judgment thresholds. | spec `:3018-3039` |
| D-09..12 | Prompt-family definition; stabilization exit and closure authority; 26-file canonical intake; judgment-heavy cost-variance note. | spec `:3018-3039` |
| D-13..16 | Provider-outage stop; per-decision domain authorities; deterministic replay; fixed ASCII Al-Muhasibi spelling. | spec `:3018-3039` |

### 1.11 Documentation conflicts/ambiguities to preserve during mapping

These are inventory conflicts, not implementation findings yet.

| ID | Conflict/ambiguity | Evidence |
|---|---|---|
| DCONF-01 | §15.4’s illustrative minimum schema requires `claims`, `requirements`, `tasks`, `pull_requests`, `tests`, `reviews`, `approvals`, `deployments`, and `risks`; the checked-in binding schema requires only eight core fields and merely offers a smaller optional set. Mapping must test both the binding asset and the broader normative export requirements. | spec `:1505-1536` vs `schemas/evidence_pack_schema.json:1-65` |
| DCONF-02 | Spec §27.9 contains `planted_critical_defect_sampling_rate=0.01` and `max_major_defect_miss_rate=0.05` plus a detailed fallback-control list; the checked-in binding reviewer-QA schema omits them. | spec `:2728-2748` vs `schemas/reviewer_quality_assurance.yaml:1-10` |
| DCONF-03 | §25.4 includes p95, unresolved-security, and backup/restore criteria; the binding stabilization schema instead names monitoring, rollback blockers, and handover, while template 22 is smaller still. All are retained; none is silently discarded. | spec `:2404-2426`; `schemas/stabilization_window_policy.yaml:1-13`; template `22_operations_observability_support.md:13-25` |
| DCONF-04 | §18.6 says the owner dashboard “should” show ten items, while §26.1 makes a basic dashboard a Phase-1 “must include” component. Inventory therefore distinguishes the required surface from advisory field wording. | spec `:1813-1828`, `:2430-2446` |
| DCONF-05 | §10 enumerates many possible platform roles and then uses “should include” for the MVP subset; the orphan audit must still check every named roadmap/spec component without upgrading every illustrative domain example to a hard requirement. | spec `:965-1065` |

## 2. Coverage matrix appendix — implementation/test/PR mapping

### 2.1 Coverage roll-up

| Population | Evidence-backed result |
|---|---:|
| Main-reachable implementation SHAs checked | **68/68 reachable**; reachability probe: `TOTAL=68 BAD=0 MAIN=50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba` |
| Numbered Slices 1–63, bounded slice-exit reading | **44 SATISFIED / 19 NOT SATISFIED**; probe `SLICE_TABLE_ROWS=64 SAT_ROWS=44 NOT_ROWS=20 NUMBERED_SLICES=63 SAT_SLICES=44 NOT_SLICES=19`; every row has implementation/test and reachable SHA/PR evidence in §2.3 |
| Roadmap §5 detailed exits, counting 61a and 61b separately | **19/39 SATISFIED / 20 NOT SATISFIED**; probe `ROADMAP_EXIT_ROWS=39 SAT=19 NOT=20`; roadmap `:184-665`, per-row evidence §2.3 |
| Roadmap/spec §26 Phase-2–7 named components | **7 SATISFIED / 27 PARTIAL / 12 GAP**; probe `COMPONENT_ROWS=46 SAT=7 PARTIAL=27 GAP=12` |
| Appendix-A semantic R5 conditions | **0/25 proven as worded**; `app/intake/readiness.py:17-23,300-309`, `app/intake/categories.py:138-164`, §2.5 |
| Appendix-B gate code paths | **13/13 implemented and PASS-test-capable; 0/13 authorization-complete as a production chain**; probe `A5_ROWS=13 PASS_TEST_ROWS=13 PERSISTED_SOURCE_PASS_COUNT=8 GATES=1,2,3,4,7,9,11,12 AUTHORIZATION_COMPLETE=0`; gate 1 is semantic-only (F-001), gates 2–6/8/10–13 admit runtime-written trusted/authenticated graphs, and gates 7/9 inherit caller-controlled/unverified sources (F-002/F-005/F-008); §2.6 |
| §29 complete operating-model capabilities | **5/16 bounded-SATISFIED**; probe `OPERATING_MODEL_ROWS=16 PASS_BOUNDED=5 PARTIAL_OR_GAP=11`; exact evidence §2.8 |
| Slices 43–63 deleted test/workflow files | **0**; `git diff --diff-filter=D --name-only 52785b3^..HEAD -- tests .github/workflows` returned no output |
| Clean suites | `make test`: **1277 passed / 1085 deselected**; `make test-db`: **1085 passed / 1277 deselected**; Ruff **PASS**; full Pyright **3050 errors**; §4.2 |

Table-bounded count probes supporting the roll-up:

```text
SLICE_TABLE_ROWS=64 SAT_ROWS=44 NOT_ROWS=20 NUMBERED_SLICES=63 SAT_SLICES=44 NOT_SLICES=19
ROADMAP_EXIT_ROWS=39 SAT=19 NOT=20
COMPONENT_ROWS=46 SAT=7 PARTIAL=27 GAP=12
A5_ROWS=13 PASS_TEST_ROWS=13 PERSISTED_SOURCE_PASS_COUNT=8 GATES=1,2,3,4,7,9,11,12 AUTHORIZATION_COMPLETE=0
OPERATING_MODEL_ROWS=16 PASS_BOUNDED=5 PARTIAL_OR_GAP=11
```

`SATISFIED*` below means that a deliberately bounded slice exit is present; it does not upgrade the frozen system requirement to complete.

### 2.2 Specification-to-implementation/test/PR matrix

Each row maps every inventory ID in the left column. `GAP` is explicit; a planning reference never counts as implementation.

| Inventory IDs | Implementation and test evidence | Reachable merged history | Verdict / explicit gap |
|---|---|---|---|
| R-00-01..04, R-01-01 | Lifecycle stores and bounded orchestration exist in `app/runtime/engine.py:1-286`, `app/runtime/control_loop.py:1-435`; tests `tests/test_runtime*.py`, `tests/test_control_loop*.py`. | S8 #9/#10 (`b461eaa`,`cddefda`); S55 #100 (`15d0e75`) | **GAP:** no build, PR, staging, production, or operating actuator; positive terminal is `decided_not_executed` (`app/release/go_live_decision.py:1-29`). |
| R-02-01..05 | Shortcut detector/evidence primitives: `app/verify/shortcut_detector.py`, `app/release/evidence_pack.py`; tests `tests/test_shortcut_detector.py`, `tests/test_evidence_packs.py`. | S45 #80 `d063ebe`; S49 #88 `0a04aec` | **PARTIAL:** bounded detector/evidence exists, but caller-reported review/eval paths and synthetic A5 graph violate no-fake-done; Findings F-005/F-013. |
| R-02-06a..j | Policy matrix `app/policy/matrix.py:60-70`; repository guard `app/repositories/approvals.py:65-110`; tests `tests/test_policy.py:65-77,136-142`, `tests/test_approvals.py`. | S3 #4 `48504b3`; S4 #5 `c1b4c6b`; S53 #96 `5fd8b18` | **FAIL:** live `uaid_app` forged every action with `requires_explicit_approval=false,status=proceeded_by_policy`; F-002. |
| R-02-07, R-08-01..04 | Skill graph/scoring/squad manifest `app/agents/skills.py:83+`; `tests/test_skills.py:53+`. | S38 #65 `ae3ea90` | **PASS (bounded):** skill matching and factory-request output exist; actual specialists/reviewers are not executed (R-09/R-10 gap). |
| R-03-01..04 | `app/core/reasoning.py:15-40` checks non-empty answer/sources/callbacks; `app/core/provenance.py:16-41` stores `Source`/`Fact`; shallow tests `tests/test_provenance.py`. | Scaffold `9a68984`; intake Sanad S11 #14 `03961c2` | **GAP:** no five-stage consequential-decision record/workflow, narrator chain, reliability score, consistency check, context boundary, or complete verdict/evidence chain; F-014. |
| R-04-01..06, R5-01..25 | Canonical category universe and structural spine: `app/intake/categories.py`, `app/intake/compiler.py`, `app/intake/readiness.py`; `tests/test_intake_categories.py`, `tests/test_intake_compiler.py`, `tests/test_readiness.py`. | S11–20, #14–#29 (`03961c2`…`74f45ce`) | **FAIL:** R5 is declaration presence, explicitly not content quality (`app/intake/readiness.py:17-23`); arbitrary/empty objects pass (`app/intake/categories.py:138-164`); §2.5/F-001. |
| R-05-01..03 | Policy/A5 engine `app/policy`, `app/release/production_autonomy.py`; tests `tests/test_policy.py`, `tests/test_production_autonomy.py`. | S3/S21/S54, #4/#31/#98 | **PARTIAL:** 13 gate ladders exist; production is literal false. Generic approval DB boundary and gate-source binding are bypassable (F-002/F-005). |
| R-06-01..05 | Classifier, extraction, findings, generator, contradictions: `app/intake/{classifier,extraction,findings,generator,semantic_contradictions}.py`; corresponding tests. | S13/14/35/36/37, #16/#17/#18/#59/#61/#63 | **PARTIAL:** 15 inert generator targets only (`app/intake/generator.py:23-39`), two approval bases deferred (`:54-57`), no complete interview/decision/tool flow; a captured concurrent-promotion `23505` signature requires retained rerun (§4.6/F-020); F-015. |
| R-07-01..05 | Generator authorship controls `app/intake/generator.py:41-57,107-150`; acceptance evaluator `app/verify/acceptance.py`; tests `tests/test_generator.py`, `tests/test_acceptance_verifier.py`. | S36 #61 `03f73b9`; S46 #82 `caee2bf` | **FAIL currentness:** repository supplies reviewer-currentness booleans from mere non-null ID (`app/repositories/acceptance_verification.py:309-348`); F-006. |
| R-09-01..06, R-09-BP, S-AR, S-AE | Blueprint/registry/realization/qualification/failure prescription in `app/agents` and `app/models/agent_blueprint.py`; tests `tests/test_agents.py`, `tests/test_factory.py`, `tests/test_qualification.py`, `tests/test_failure_policy.py`. | S6 #7 `ba3691f`; S39–41 #67/#69/#71 | **PARTIAL/GAP:** blueprint/realization shapes exist, but qualification scores caller-recorded cases and runs no agent (`app/agents/qualification.py:3-10`); failure policy recommends but does not suspend/replace (`tests/test_failure_policy.py:645-669`); no real Agent-QA/security/performance executor; F-013. |
| R-10-01..06 | Archetype names/registries in `app/agents/registry.py`, qualification definitions, tests `tests/test_agents.py`. | S6/S40 | **PARTIAL:** named specialist taxonomy is representable, but most roles are not active executors and maker/checker flows accept reported outcomes; F-013. |
| R-11-01..04 | Tool contracts and deny-first decision logging: `app/tools/{registry,broker}.py`; `tests/test_tools.py`. | S5 #6 `334cb48`; S28–34; S39 | **GAP:** source says “No real execution,” success is `ALLOWED_UNVERIFIED_IDENTITY`, authenticated approval allowlist is empty (`app/tools/broker.py:13-16,34-38,225-230`); no rate-limited credentialed broker actuator; F-009. |
| R-12-01..04 | Task/review state models `app/review/workflow.py`; bounded control loop `app/runtime/control_loop.py`; tests `tests/test_task_contracts.py`, `tests/test_control_loop.py`. | S42 #73 `c7f245e`; S55 #100 `15d0e75` | **GAP:** workflow module says it runs no review and accepts caller-reported verdicts (`app/review/workflow.py:1-12,61-62`); no build/PR/deploy loop; F-009/F-013. |
| R-13-01..06, S-RQA | Task contracts, reviewer reports, security/shortcut/acceptance/reviewer-QA stores/evaluators under `app/review`, `app/verify`; corresponding tests. | S42–48 #73–#86 | **PARTIAL:** structural layers and thresholds exist; no executed maker-checker-verifier, and gate-8 current QA inputs are fake/dead; F-006/F-013. |
| R-14-01..04 | Oracle types/runners `app/verify/{oracles,specified,reference,judgment}.py`; `tests/test_test_oracles.py`. | S43 #76 `52785b3` | **PARTIAL:** the evaluator/definition framework exists and a DB/composed PASS is tested (`tests/test_test_oracles.py:1178-1224`), but runtime can self-stamp its executed/connector evidence and three gate-4 conjuncts lack independent mutations (F-005/F-008). |
| R-15-01..05, S-EP | Evidence assembly/schema/export `app/release/{evidence_pack,evidence_export,export_bundle,export_signing}.py`; evidence/export tests. | S49 #88 `0a04aec`; S60 #110 `8e001ca` | **PARTIAL:** offline signed bundle works, but §15.4/schema vocabularies conflict; OSCAL, scoped/temp auditor access, expiry enforcement, and the broader minimum field contract are absent; F-016. |
| R-16-01..08 | RLS/guards, security scan, audit hash chain, reviewer QA, catalog contract tests across migrations and `app/verify`. | S1/2/44/48/61 | **FAIL/PARTIAL:** full 15-control product-security review absent; external audit sink absent; generated-agent security executor and D-8/D-9/D-10 open; live RLS/immutability failures F-003/F-004/F-019. |
| R-17-01..05 | Tenant context/RLS `app/tenancy.py`, migrations; aggregate learning `app/ecosystem/learning.py`; tests `tests/test_rls.py`, `tests/test_learning*.py`. | S1 #1/#2; S62 #114 `96faa86` | **FAIL boundary:** raw catalog is 121/123 `tenant_id` tables; one exception is the explicitly global pre-tenant key lookup (`app/models/tenant_api_key.py:1-5`), leaving 121/122 semantically tenant-owned tables with the full RLS triple. `uaid_app` can also select another tenant GUC; F-003/F-011/F-019. |
| R-18-01..06 | Approval routing/API `app/approvals/channels`, `app/api/dashboard.py`; tests `tests/test_approval_channel.py`, `tests/test_api.py`. | S10 #12/#13; S17/19; S33 #55 | **GAP:** no web UI; dashboard defers forecast, critical path, evidence, deployment, next action (`app/api/dashboard.py:7-12`); no durable nonresponse scheduler/mid-run correction; F-012/F-015. |
| R-19-01..05 | Cost ledger/forecast/decision-only optimizer `app/cost.py`, `app/cost_forecast.py`, `app/ecosystem/cost_optimizer.py`; tests. | S7 #8; S51 #92; S62 #114 | **PARTIAL:** ledger/forecast and recommendation exist; no full per-phase budget lifecycle or actuated model routing; captured budget/forecast-policy first-write `23505` signatures require retained rerun (§4.6/F-020); F-015. |
| R-20-01..02 | Template/domain fields and one reference-intake declaration; inert domain-pack generator target. | Docs; S36; S61b #113 | **PARTIAL:** no semantic domain-pack validator or per-decision authority execution; catalog exit remains open. |
| R-21-01..03 | Contract-test/listing primitives `app/ecosystem/contract_test.py`, catalog records/tests. | S61a/b #111/#113 | **GAP:** no governed connector-creation/tool-server workflow, owner activation, or live-provider/permission proof; D-8/D-9 open; F-011/F-015. |
| R-22-01..04, S-MC | Binding schema asset exists; agent-version hashes cover some snapshot fields. | S39 | **GAP:** no model/prompt/tool change request, forced-deprecation, regression, requalification, resume-approval, or provider-outage workflow; F-015. |
| R-23-01..03 | Durable runtime/checkpoint/state tables and bounded cycle in `app/runtime`; DB tests `tests/test_runtime*.py`, `tests/test_control_loop.py`. | S8, S55 | **PARTIAL:** persistence/resume/retry exists; no full deterministic replay proof, distributed workers, external action idempotency/tool-result execution, or end-to-end actuator chain; six captured first-write conflict signatures require retained reruns and 107/122 candidate writer endpoints were untouched by the mapped audit actions; F-009/F-015/F-020. |
| R-23-04 | Atomic 28-object state-model map immediately below. | S1–61b | **PARTIAL:** 23 named collections have exact/bounded persisted representations; decisions and connectors are partial; users, actual agent runs, and deployments are gaps; F-009/F-013/F-014/F-015. |
| R-24-01..04, S-RA | A5/release verdict/risk stores `app/release`; tests `tests/test_production_autonomy.py`, `tests/test_release_verdicts.py`, `tests/test_risk_acceptance.py`. | S21–55 | **FAIL as release capability:** evaluator can be synthetically satisfied, semantic R5 is invalid, and execution remains hard false; F-001/F-005/F-009. |
| R-25-01..05, S-SW | Signals/incidents/hotfix-intent/stabilization assessment in `app/ops`; ops tests. | S56–59 #102/#104/#106/#108 | **GAP:** S58/S59 exits explicitly NOT SATISFIED; no backup/restore, measured close, closure authority, real hotfix/rollback, acting improvement; F-010. |
| R-26-01..07 | Component-by-component matrix §2.4. | S1–63 | **7 SAT / 27 PARTIAL / 12 GAP**; probe `COMPONENT_ROWS=46 SAT=7 PARTIAL=27 GAP=12`; several components have no closing numbered slice. |
| R-27-01 | Related `ReadinessReport` exposes `readiness_level`, `can_build_to_staging`, hard-false `can_go_live_autonomously`, assumptions, and missing-for-go-live (`app/intake/readiness.py:158-203`; shape test `tests/test_readiness.py:175-203`). | S12/S20 #15/#29 (`11cd224`,`74f45ce`) | **GAP artifact:** no `build_readiness_report.json`; requested/allowed autonomy, `can_start_build`, exact deploy booleans, `missing_artifacts`, `unsafe_assumptions`, `blocked_decisions`, and `recommended_next_action` are absent (`rg` over `app tests migrations` returned no matching artifact/field identifiers); F-015. |
| R-28-01..02 | Signed offline bundle and read-only DB projections; export tests. | S60 #110 | **PARTIAL:** four-file offline mode only; declared 720-hour expiry unenforced, no OSCAL/scoped link/temp account (`app/release/export_bundle.py:24-38,82-93`); F-016. |
| R-29-01..16 | Operating-model roll-up §2.8. | S1–63 | **5/16 bounded-SATISFIED; 11/16 partial/gap**; probe `OPERATING_MODEL_ROWS=16 PASS_BOUNDED=5 PARTIAL_OR_GAP=11`. |

#### §23.4 atomic 28-collection state map

The exact-table-name probe over `app/models` and `migrations/versions` returned:

```text
EXACT_REQUIRED_TABLE_NAMES_CHECKED=28
EXACT_REQUIRED_TABLE_NAME_MATCHES=15
EXACT_REQUIRED_TABLE_NAME_NONMATCHES=13
MATCHES=organizations,tenants,projects,project_runs,documents,agent_versions,skills,task_contracts,test_results,review_reports,evidence_packs,approvals,audit_logs,cost_events,tool_calls
NONMATCHES=users,requirements,acceptance_criteria,test_oracles,assumptions,decisions,agents,agent_runs,issues,pull_requests,deployments,connectors,incidents
```

That name probe is not treated as proof of absence where a typed unified or specialized representation exists; each such analogue is mapped below. `PRESENT` means the named state has a persisted representation, not that its wider workflow is complete.

| # | Required collection | Implementing representation and direct test | Main-reachable slice / PR | Disposition |
|---:|---|---|---|---|
| 1 | organizations | `app/models/organization.py:18-19`; spine/catalog test `tests/test_tenancy.py:32-84` | S1 `b748566`; #1 | PRESENT |
| 2 | tenants | `app/models/tenant.py:14-15`; isolation tests `tests/test_tenancy.py:32-84` | S1 `b748566`; #1 | PRESENT |
| 3 | users | no exact table or user-domain analogue in the quoted name probe; tenant API keys are pre-tenant credentials, not users (`app/models/tenant_api_key.py:1-8,23-24`) | none | **GAP** (F-015) |
| 4 | projects | `app/models/project.py:15-16`; tenant/project tests `tests/test_tenancy.py:32-84` | S1 `b748566`; #1 | PRESENT |
| 5 | project runs | `app/models/project_run.py:25-26`; run tenant/FK tests `tests/test_tenancy.py:32-84` | S1 `b748566`,`fd40cfc`; #1/#2 | PRESENT |
| 6 | documents | `app/models/document.py:30-31`; ingest/quarantine tests `tests/test_intake.py:153-204` | S9 `a522ed5`; #11 | PRESENT |
| 7 | requirements | typed `intake_artifacts.kind='requirement'` (`app/models/intake_artifact.py:1-12,47-48`); kind/provenance tests `tests/test_intake_compiler.py:33-78,166-229` | S11 `03961c2`; #14 | PRESENT in unified canonical spine |
| 8 | acceptance criteria | typed `intake_artifacts.kind='acceptance_criterion'` and same-project parent FK (`app/models/intake_artifact.py:1-12,47-48`); parent tests `tests/test_intake_compiler.py:33-78,370-418` | S11 `03961c2`; #14 | PRESENT in unified canonical spine |
| 9 | test oracles | typed oracle definition in `intake_artifacts` plus `test_oracle_runs` (`app/models/intake_artifact.py:1-12,47-48`; `app/models/test_oracle_run.py:44-46`); definition/result tests `tests/test_test_oracles.py:172-266,835-879` | S11/S43 `03961c2`,`52785b3`; #14/#76 | PRESENT; execution authority F-005 |
| 10 | assumptions | typed/classified `intake_artifacts.kind='assumption'` (`app/models/intake_artifact.py:1-12,36-48`); classification/persistence tests `tests/test_intake_compiler.py:33-78,166-229` | S11 `03961c2`; #14 | PRESENT in unified canonical spine |
| 11 | decisions | specialized `go_live_decisions` only (`app/models/go_live_decision.py:294-363`); hard-false chain test `tests/test_control_loop.py:968-1039` | S55 `15d0e75`; #100 | **PARTIAL:** no general consequential-decision/Muhasabah collection (F-014/F-015) |
| 12 | agents | tenant-bound `agent_instances` (`app/models/agent_instance.py:42-43`); lifecycle/RLS tests `tests/test_agents.py:235-417` | S6 `ba3691f`; #7 | PRESENT; no agent execution F-013 |
| 13 | agent versions | immutable `agent_versions` (`app/models/agent_version.py:39-40`); version/immutability tests `tests/test_agents.py:170-225` | S6 `ba3691f`; #7 | PRESENT |
| 14 | agent runs | no `agent_runs` table or actual-agent execution; the nearest `qualification_runs` evidence explicitly runs no agent (`app/models/qualification_run.py:44-45`; `app/agents/qualification.py:1-10`), while tests exercise recorded qualification rows (`tests/test_qualification.py:296-364`) | S40 `4bba0a0`; #69 | **GAP:** no actual agent-run collection/executor (F-013/F-015) |
| 15 | skills | migration-owned global `skills` table (`migrations/versions/0037_skill_matching.py:31-89`); seed/ACL/immutability tests `tests/test_skills.py:366-419` | S38 `ae3ea90`; #65 | PRESENT; test weakness F-021 |
| 16 | task contracts | `app/models/task_contract.py:57-116`; create/freeze/FK tests `tests/test_task_contracts.py:600-897` | S42 `c7f245e`; #73 | PRESENT |
| 17 | issues | `app/models/release_issue.py:33-34`; lifecycle/RLS tests `tests/test_release_issues.py:226-372` | S24 `7a2ae44`; #37 | PRESENT; disposition authority F-002 |
| 18 | pull requests | `pull_request_evidence_snapshots` (`app/models/pull_request_evidence_snapshot.py:37-98`); connector/latest/gate tests `tests/test_pr_evidence.py:497-528,679-730` | S29 `52a4b95`; #47 | PRESENT as observation snapshots; no PR actuator F-009 |
| 19 | test results | `app/models/test_result.py:79-128`; generated-result/aggregate tests `tests/test_test_oracles.py:835-879` | S43 `52785b3`; #76 | PRESENT; source authority F-005 |
| 20 | review reports | `app/models/review_report.py:43-103`; registration/append-only/RLS tests `tests/test_task_contracts.py:898-1085` | S42 `c7f245e`; #73 | PRESENT as caller-reported verdicts; F-013 |
| 21 | evidence packs | `app/models/evidence_pack.py:160-244`; persistence/re-audit tests `tests/test_evidence_packs.py:513-687` | S49 `0a04aec`; #88 | PRESENT; upstream authority F-005 |
| 22 | approvals | `app/models/approval.py:34-65`; request/state tests `tests/test_approvals.py:173-237` | S4 `c1b4c6b`; #5 | PRESENT; structural bypass F-002 |
| 23 | deployments | only target-availability observations, expressly non-deploying (`app/models/deployment_target_snapshot.py:1-12,39-40`); snapshot tests `tests/test_deploy_evidence.py:331-381,446-497` | S30 `200c460`; #49 | **GAP deployment collection/actuator** (F-009/F-015) |
| 24 | audit logs | `app/models/audit_log.py:23-24`; append/verify/immutability tests `tests/test_audit.py:113-220` | S2 `b935e9f`; #3 | PRESENT; RLS omission F-019 |
| 25 | cost events | `app/models/cost_event.py:51-108`; record/idempotency tests `tests/test_cost.py:140-227` | S7 `c32a2c7`; #8 | PRESENT; truncate test weakness F-021 |
| 26 | tool calls | `app/models/tool_call.py:37-38`; decision-record tests `tests/test_tools.py:164-201` | S5 `334cb48`; #6 | PRESENT as broker decisions, not execution results (F-004/F-009) |
| 27 | connectors | global declared `connector_catalog_specs` (`app/models/ecosystem_catalog.py:63-91`); catalog-population tests `tests/test_ecosystem_catalog_populate_db.py:92-161` | S61a/b `17e7fc9`,`59af1c7`; #111/#113 | **PARTIAL:** declarations/listings, no active governed connector state or live-provider proof (F-011/F-015) |
| 28 | incidents | local `ops_incidents`, explicitly not production IR (`app/models/ops_incident.py:1-4,52-114`); policy/ticket tests `tests/test_ops_incidents_db.py:74-224` | S57 `037508c`; #104 | PRESENT bounded local ledger; no live IR actuator F-010 |

#### Canonical intake templates and binding schemas

| Inventory | Implementation/test/PR mapping | Verdict |
|---|---|---|
| T-00..T-25 | All 26 source templates exist; `_CANONICAL_FILE_ORDER` names 00–25 (`app/intake/readiness.py:90-120`) and tests pin the universe (`tests/test_intake_categories.py`). S15 #20 `7a6975f`; S20 #29 `74f45ce`. | **PARTIAL:** declarations, including empty dicts, satisfy presence; fields/thresholds are not semantically validated. |
| T-00/T-06/T-08/T-09/T-10/T-11/T-12/T-18/T-24 | Related 15 generator targets at `app/intake/generator.py:23-39`; `tests/test_generator.py:37+`; S36 #61. | **PARTIAL:** generator is inert; it does not generate the literal 26-file pack and omits product brief, objectives, boundaries, roles, journeys, NFR, existing assets, security/privacy, environments, secrets, human approval, cost, ops/support, prior-decisions as named file targets; F-015. |
| S-AR/S-AE | Realization and archetype shapes represented under `app/models/agent_realization.py`, `app/agents/registry.py`; S39/S40. | **PARTIAL:** case/eval outcomes are recorded caller input, not executed agent qualification. |
| S-EP | JSON Schema is loaded/hashed and tested (`tests/test_evidence_packs.py:124+`); S49/S60. | **PARTIAL:** DCONF-01/03 and F-016. |
| S-MC | Asset exists and is frozen by evidence tests. | **GAP runtime:** no model-change/deprecation engine. |
| S-RQA | Threshold constants/evaluator `app/verify/reviewer_qa.py`; `tests/test_reviewer_quality.py`; S48 #86. | **PARTIAL:** schema/spec disagreement DCONF-02 and dead gate-8 currentness F-006. |
| S-RA | Risk record store and release binding; `tests/test_risk_acceptance.py`, `tests/test_release_verdicts.py`; S22/S47/S50. | **FAIL authority:** active risk can be created without action-bound explicit approval; F-002. |
| S-SW | Policy shape is present and S59 persists an immutable assessment snapshot/tests, but does not execute the binding 14-day/3-day/zero-rollback-blocker closure contract. | **GAP:** only `open`, no backup/restore, measured binding-threshold exit, or closure authority; F-010. |

### 2.3 Slices 1–63: exit, implementation, test, and merged-PR lineage

For Slices 26–63, a bare exit `:<line>` defaults to the `roadmap` alias's §5 line. Slices 1–25 use the §2.6 ledger plus reachable merge history. All listed SHAs were probed reachable from audited `main` (`TOTAL=68 BAD=0`).

| Slice | Exit / primary implementation / test | Main-reachable SHA / merged PR | Result |
|---:|---|---|---|
| 1 | tenancy/state/RLS; `app/tenancy.py:24`; `tests/test_tenancy.py:32`, `tests/test_rls.py:118` | `b748566`,`fd40cfc`; #1/#2 | SATISFIED* |
| 2 | append-only audit; `app/audit.py:30`; `tests/test_audit.py:51` | `b935e9f`; #3 | SATISFIED* |
| 3 | autonomy policy; `app/policy/engine.py:16`; `tests/test_policy.py:37` | `48504b3`; #4 | SATISFIED* |
| 4 | approval engine; `app/approvals/states.py:15`; `tests/test_approvals.py:37` | `c1b4c6b`; #5 | SATISFIED* (DB bypass F-002) |
| 5 | broker skeleton; `app/tools/broker.py:42`; `tests/test_tools.py:30` | `334cb48`; #6 | SATISFIED* (non-executing) |
| 6 | registry; `app/agents/registry.py:57`; `tests/test_agents.py:45` | `ba3691f`; #7 | SATISFIED* (captured blueprint/version conflict signatures require rerun, F-020) |
| 7 | cost ledger; `app/cost.py:31`; `tests/test_cost.py:41` | `c32a2c7`; #8 | SATISFIED* (captured budget conflict signature requires rerun, F-020) |
| 8 | checkpointer/runtime; `app/runtime/checkpointer.py:37`, `app/runtime/engine.py:55`; runtime tests | `b461eaa`,`cddefda`; #9/#10 | SATISFIED* |
| 9 | intake sandbox; `app/intake/sandbox.py:42`; `tests/test_intake.py:36` | `a522ed5`; #11 | SATISFIED* |
| 10 | read API/dashboard + key hardening; `app/api/dashboard.py:43`; `tests/test_api.py:24` | `d32e3fa`,`a1c60c9`; #12/#13 | SATISFIED* (UI gap) |
| 11 | intake/Sanad spine; `app/intake/compiler.py:35`; `tests/test_intake_compiler.py:33` | `03961c2`; #14 | SATISFIED* |
| 12 | readiness snapshots; `app/intake/readiness.py:139`; `tests/test_readiness.py:67` | `11cd224`; #15 | SATISFIED* |
| 13 | structural gaps; `app/intake/findings.py:30`; `tests/test_findings.py:43` | `b5ed97d`; #16 | SATISFIED* |
| 14 | extraction/promotion; `app/intake/extraction.py:41`; extraction tests | `013d00c`,`ae9798f`; #17/#18 | SATISFIED* (captured promotion conflict signature requires rerun, F-020) |
| 15 | category model; `app/intake/categories.py:83`; `tests/test_intake_categories.py:39` | `7a6975f`; #20 | SATISFIED* |
| 16 | R3 presence rule; `app/intake/readiness.py:139`; readiness tests | `eaa9da1`; #21 | SATISFIED* |
| 17 | readiness/findings API; `app/api/dashboard.py:170`; API tests | `eb19b4c`; #23 | SATISFIED* |
| 18 | R4 presence rule; readiness code/tests | `f69da00`; #25 | SATISFIED* |
| 19 | dashboard histories; `app/api/dashboard.py:188`; API tests | `0b40c91`; #27 | SATISFIED* |
| 20 | R5 presence ladder; `app/intake/readiness.py:300`; `tests/test_readiness.py:430` | `74f45ce`; #29 | SATISFIED*; semantic exit FAIL (F-001) |
| 21 | A5 evaluator; `app/release/production_autonomy.py:84`; `tests/test_production_autonomy.py:63` | `7ad1b45`; #31 | SATISFIED* |
| 22 | risk acceptance; `app/release/risk_acceptance.py:63`; `tests/test_risk_acceptance.py:64` | `4ea38cc`; #33 | SATISFIED* (approval gap) |
| 23 | findings store; `app/release/findings.py:58`; `tests/test_release_findings.py:46` | `da7ac4e`; #35 | SATISFIED* |
| 24 | issues store; `app/release/issues.py:61`; `tests/test_release_issues.py:53` | `7a2ae44`; #37 | SATISFIED* |
| 25 | release candidates; `app/release/release_candidates.py:31`; tests `tests/test_release_candidates.py:34` | `f706a30`; #39 | SATISFIED* |
| 26 | roadmap exit `:194`; `app/release/ci_evidence.py:54`; `tests/test_ci_evidence.py:46` | `dc622a0`; #41 | SATISFIED |
| 27 | exit `:206`; `app/identity.py:30`; `tests/test_identity.py:30` | `372e15b`; #43 | **NOT SATISFIED:** exit requires verified identity; request/connector identity labels are not writer-isolated (F-005) |
| 28 | exit `:219`; `app/release/ci_evidence_service.py:30`; CI-evidence tests | `6de94de`; #45 | **NOT SATISFIED:** runtime can self-stamp the `connector_verified` evidence required for gate 3 (F-005) |
| 29 | exit `:231`; `app/release/pr_evidence_service.py:34`; `tests/test_pr_evidence.py:67` | `52a4b95`; #47 | SATISFIED |
| 30 | exit `:243`; `app/release/deploy_evidence_service.py:39`; deploy tests | `200c460`; #49 | **NOT SATISFIED:** verified target/gate-2 PASS is runtime-self-stampable (F-005) |
| 31 | exit `:255`; `app/release/monitoring_evidence_service.py:35`; monitoring tests | `e77bf7a`; #51 | **NOT SATISFIED:** verified monitoring/gate-11 PASS is runtime-self-stampable (F-005) |
| 32 | exit `:267`; `app/release/secrets_verification_service.py:34`; secret tests | `214495c`; #53 | **NOT SATISFIED:** zero-leakage tests exist, but the conjunctive exit's verified resolution label is runtime-writeable (F-005) |
| 33 | exit `:279`; `app/approvals/channels/service.py:29`; channel tests | `e436668`; #55 | **NOT SATISFIED:** verified identity is not writer-isolated and dashboard delivery is a no-I/O canned success (F-005/F-015) |
| 34 | exit `:291`; `app/release/pm_sync_service.py:39`; `tests/test_pm_issues.py:69` | `d65b98c`; #57 | SATISFIED* |
| 35 | exit `:307`; `app/intake/classifier.py:62`; classifier tests | `006ea7e`; #59 | SATISFIED |
| 36 | exit `:319`; `app/intake/generator.py:70`; generator tests | `03f73b9`; #61 | SATISFIED* |
| 37 | exit `:331`; `app/intake/semantic_contradictions.py:61`; tests | `98a47ed`; #63 | SATISFIED |
| 38 | exit `:345`; `app/agents/skills.py:83`; skill tests | `ae3ea90`; #65 | SATISFIED |
| 39 | exit `:357`; `app/agents/factory.py:32`; factory tests | `9ea4f90`; #67 | SATISFIED* |
| 40 | exit `:369`; `app/agents/qualification.py:29`; qualification tests | `4bba0a0`; #69 | SATISFIED* (record-only) |
| 41 | exit `:381`; `app/agents/failure_policy.py:69`; `tests/test_failure_policy.py:645-669` | `626e57f`; #71 | **NOT SATISFIED:** no security-review/performance executor; prescription does not suspend/replace |
| 42 | exit `:395`; `app/review/workflow.py:68`; task-contract tests | `c7f245e`; #73 | SATISFIED* (record-only) |
| 43 | exit `:407`; `app/verify/oracles.py:58`; oracle tests | `52785b3`; #76 | **NOT SATISFIED:** oracle run/results and their executed/connector labels are runtime-writeable (F-005) |
| 44 | exit `:419`; `app/verify/security_scan.py:59`; security tests | `33fb926`; #78 | **NOT SATISFIED:** verified scan provenance and gate-5 PASS are runtime-self-stampable (F-005) |
| 45 | exit `:431`; `app/verify/shortcut_detector.py:48`; shortcut tests | `d063ebe`; #80 | **NOT SATISFIED:** connector/system/LLM execution and review provenance are runtime-self-stampable (F-005) |
| 46 | exit `:443`; `app/verify/acceptance.py:38`; acceptance tests | `caee2bf`; #82 | **NOT SATISFIED:** complete relational lineage is runtime-writeable given the deployed read-only blueprint catalog; currentness is also fake (F-005/F-006) |
| 47 | exit `:455`; issue provenance; `tests/test_issue_provenance.py:39` | `5f3e693`; #84 | **NOT SATISFIED:** the exit's trusted Slice-44/45 provenance inherits their forgeable source graphs (F-005) |
| 48 | exit `:467`; `app/verify/reviewer_qa.py:67`; reviewer-QA tests | `da91068`; #86 | SATISFIED |
| 49 | exit `:479`; `app/release/evidence_pack.py:125`; evidence tests | `0a04aec`; #88 | SATISFIED* |
| 50 | exit `:493`; `app/release/release_manager.py:37`; verdict tests | `4f2012b`; #90 | SATISFIED |
| 51 | exit `:505`; `app/cost_forecast.py:76`; forecast tests | `0dbacb3`; #92 | SATISFIED* for the literal deterministic calculation exit; captured policy-version conflict signature requires rerun (F-020) |
| 52 | exit `:517`; `app/release/rollback.py:72`; rollback tests | `598c70b`; #94 | **NOT SATISFIED:** connector-observed rollback graph is runtime-self-stampable (F-005) |
| 53 | exit `:529`; `app/release/production_approval_service.py:36`; preapproval tests | `5fd8b18`; #96 | **NOT SATISFIED:** request-authenticated actors/attestations can be runtime-self-stamped (F-005) |
| 54 | exit `:541`; `app/release/emergency_control_service.py:21`; emergency tests | `84e955a`; #98 | **NOT SATISFIED:** a committed latch makes owned start roll back and owned resume return paused, but resume evaluates cost first (§4.4); the authority-bound gate-13 PASS graph is also runtime-writeable and lacks a full persisted PASS (F-005/F-008) |
| 55 | exit `:553`; `app/runtime/control_loop.py:62`; control-loop tests | `15d0e75`; #100 | SATISFIED* for the literal non-executing merge/CI exit; committed-latch resume-order failure F-008 |
| 56 | exit `:569`; `app/ops/signals.py:112`; signal tests | `5c4b3e9`; #102 | SATISFIED* (assessable, mostly not-observed) |
| 57 | exit `:581`; `app/ops/incidents.py:78`; incident tests | `037508c`; #104 | SATISFIED* (local ledger) |
| 58 | exit `:593`; `app/ops/hotfix.py:75`; hotfix tests | `787ddd6`; #106 | **NOT SATISFIED**; intent only, no diagnosis/git/PR/deploy/rollback |
| 59 | exit `:607`; `app/ops/stabilization.py:91`; stabilization tests | `15bb587`; #108 | **NOT SATISFIED**; no backup/restore/closure/acting improvement |
| 60 | exit `:621`; `app/release/export_bundle.py:43`; export tests | `8e001ca`; #110 | SATISFIED* (offline-only) |
| 61a | exit `:631`; `app/ecosystem/catalog.py:82`; catalog tests | `17e7fc9`; #111 | **NOT SATISFIED**; mechanism intentionally non-closing; captured catalog-adoption conflict signature requires rerun (F-020) |
| 61b | exit `:641`; `app/ecosystem/catalog_populate.py:41`; population tests | `59af1c7`; #113 | **NOT SATISFIED**; D-8/D-9/D-10 open |
| 62 | exit `:653`; `app/ecosystem/learning.py:176`; learning tests | `96faa86`; #114 | SATISFIED* (bounded aggregates/recommendation) |
| 63 | exit `:665`; `app/admin/rbac.py:35`; admin tests | `e6fbddc`; #116 | **NOT SATISFIED:** the exit requires tenant isolation intact and no runtime-role RLS bypass (`roadmap:661-665`), but the live runtime-role victim-GUC read and tenant-owned `audit_logs` RLS omission falsify that conjunct (F-003/F-019; §4.4) |

### 2.4 Roadmap §10 component and §2.6 residual/orphan audit

#### Every named Phase-2–7 component

Every `S<n>` reference below resolves to the reachable SHA and merged PR in §2.3; a row without a numbered slice is an orphan even when its source artifact exists.

| Phase | Component | Numbered slice / actual evidence | Verdict |
|---:|---|---|---|
| 2 | document classifier | S35; `app/intake/classifier.py:62`; classifier tests | SATISFIED |
| 2 | requirement extractor | S14; #17/#18 in §2.3; inert proposals, real-model quality deferred | PARTIAL |
| 2 | gap detector | S13; `app/intake/findings.py:30` | SATISFIED |
| 2 | contradiction detector | S13/S37; `app/intake/semantic_contradictions.py:61` | SATISFIED |
| 2 | build-readiness auditor | S12/16/18/20; `app/intake/readiness.py:17-23` | **GAP:** presence is not semantic readiness |
| 2 | canonical artifact generator | S36; inert drafts, two approval bases deferred (`app/intake/generator.py:54-57`) | PARTIAL |
| 2 | intake template pack | source census `TOP_LEVEL_TEMPLATES=26`; endpoints `docs/UAID_OS_Intake_Template_Pack_v1_2/00_project_manifest.yaml:1-13` and `25_prior_decisions_and_architecture_log.md:1-41`; pack contract `docs/UAID_OS_Intake_Template_Pack_v1_2/README.md:1-5`; history is initial scaffold `9a68984`, not a numbered slice/merged PR | **PARTIAL / ORPHAN:** artifacts exist, but the component has no merged-slice lineage (F-015) |
| 2 | Sanad provenance store | S11; intake provenance only | PARTIAL |
| 3 | project management | S34; `app/release/pm_connector.py:1-8` says fake only | **GAP:** no Jira/live PM adapter |
| 3 | source control | S26/S28; `app/release/ci_evidence_service.py:30`; `tests/test_ci_evidence.py:46`; `dc622a0`,`6de94de`; #41/#45 | PARTIAL: read mechanism exists; runtime can self-stamp the trusted connector observation (F-005) |
| 3 | pull requests | S29; `app/release/pr_evidence_service.py:34`; `tests/test_pr_evidence.py:67`; `52a4b95`; #47 | PARTIAL: read/link mechanism exists; verified merge/review facts are not writer-authenticated (F-005) |
| 3 | CI/CD | S26/S28; branch/check observation only | PARTIAL; no CI/CD actuation |
| 3 | staging deployment | S30; `app/release/deploy_connector.py:17-23` target probe | **GAP:** no deployment |
| 3 | communication/approval | S33; dashboard-only channel/risk routing | PARTIAL; no external channel/scheduler |
| 3 | secret-reference verification | S32; local `env` adapter (`app/release/secrets_connector.py:1-9,46-58`) | PARTIAL: trusted resolution is runtime-self-stampable (F-005) |
| 3 | monitoring integration | S31; `app/release/monitoring_evidence_service.py:35`; `tests/test_monitoring_evidence.py:72`; `e77bf7a`; #51 | PARTIAL: observation mechanism exists; the trusted status row is runtime-writeable (F-005) |
| 4 | skill graph | S38; `app/agents/skills.py:83`; `tests/test_skills.py:53`; `ae3ea90`; #65 | SATISFIED |
| 4 | blueprint registry | S6/S39; `app/agents/registry.py:57`; `tests/test_agents.py:45`; `ba3691f`; #7 | SATISFIED as a bounded store; captured blueprint/version contention signatures require retained rerun (F-020) |
| 4 | realization mechanism | S39; `app/agents/factory.py:32`; `tests/test_factory.py:32`; `9ea4f90`; #67 | SATISFIED (binding) |
| 4 | archetype eval library | S40; definitions/results, no agent run | PARTIAL |
| 4 | Agent-QA workflow | S40; approval records, no QA executor | PARTIAL |
| 4 | generated-agent security review | claimed S41; no executor/evidence gate | **GAP / S41 exit NOT** |
| 4 | performance monitoring | claimed S41; no generated-agent monitor | **GAP / S41 exit NOT** |
| 4 | replacement policy | S41; decision-only recommendation | PARTIAL |
| 5 | maker-checker-verifier | S42; `app/review/workflow.py:1-12` reported verdict store | **GAP:** no review execution |
| 5 | task contracts | S42; `app/review/workflow.py:68`; `tests/test_task_contracts.py:59`; `c7f245e`; #73 | SATISFIED |
| 5 | reviewer reports | S42; caller-supplied/unverified | PARTIAL |
| 5 | test-oracle framework | S43; `app/verify/oracles.py:58`; `tests/test_test_oracles.py:57`; `52785b3`; #76 | PARTIAL: evaluator/definitions exist; persisted execution labels are runtime-self-stampable (F-005) |
| 5 | shortcut detector | S45; `app/verify/shortcut_detector.py:48`; `tests/test_shortcut_detector.py:30`; `d063ebe`; #80 | PARTIAL: detector paths exist; persisted connector/system/LLM labels are runtime-self-stampable (F-005) |
| 5 | acceptance verifier | S46 | PARTIAL; runtime-writeable source graph/current-reviewer gap (F-005/F-006) |
| 5 | evidence-pack auditor | S49; `app/release/evidence_pack.py:125`; `tests/test_evidence_packs.py:124`; `0a04aec`; #88 | PARTIAL: canonical assembly/re-audit exists, but it cannot authenticate runtime-self-stamped upstream sources (F-005) |
| 5 | go-live readiness agent | S50/S55; evaluation/non-executing only | **GAP:** no action, hard false |
| 6 | release manager | S50; `app/release/release_manager.py:37`; `tests/test_release_verdicts.py:67`; `4f2012b`; #90 | PARTIAL: deterministic verdict exists, but its trusted upstream source universe is not authenticated (F-002/F-005) |
| 6 | production approval | S53; API-key-authenticated request labels, not human signature; supporting graph is runtime-writeable | PARTIAL (F-005) |
| 6 | rollback verification | S52; `app/release/rollback.py:72`; `tests/test_rollback_verifications.py:80`; `598c70b`; #94 | PARTIAL: structural verification exists; connector-verified/observed rows are runtime-self-stampable and expressly are not deployment/execution proof (F-005; `migrations/versions/0051_rollback_verifications.py:111-144`) |
| 6 | post-launch monitoring | S56; assessment, mostly `not_observed` | PARTIAL |
| 6 | incident workflow | S57; local incident/ticket ledger | PARTIAL; no live IR/Jira/log diagnosis |
| 6 | self-healing/hotfix | S58 | **GAP / exit NOT** |
| 6 | continuous-improvement engine | S59 | **GAP / exit NOT** |
| 7 | vetted-blueprint marketplace | S61 | **GAP:** D-10/S61 exit open |
| 7 | connector library | S61 | **GAP:** D-8/D-9 open |
| 7 | reference-intake library | S61b; one declared intake | **GAP:** combined exit open |
| 7 | assurance export | S60; signed offline bundle | PARTIAL |
| 7 | advanced cost optimizer | S62; decision-only recommendation | PARTIAL |
| 7 | tenant-safe learning | S62; bounded aggregate publisher | PARTIAL; consent/privacy proof absent |
| 7 | enterprise administration | S63; three roles/two action kinds (`app/admin/rbac.py:12-29`) | PARTIAL: RBAC exists, but the exit's tenant-isolation/no-runtime-bypass conjunct fails (F-003/F-019) |

Table-bounded count probe:

```text
COUNT SAT=7 PARTIAL=27 GAP=12 TOTAL=46
```

#### §2.6 baseline residuals and phase-only/no-slice orphans

| Ledger component (`roadmap:72-95`) | Numbered merged lineage / roadmap scheduling | Audited disposition |
|---|---|---|
| Tenant isolation | S1 #1/#2; every new table | raw 121/123; excluding the declared global pre-tenant lookup leaves 121/122 tenant-owned, with `audit_logs` unmatched (F-019); runtime GUC is tenant-selectable (F-003) |
| Project state/runs | S1 #1/#2 | bounded store present (`app/models/project.py`, `app/models/project_run.py`; lineage §2.3) |
| Durable runtime | S8 #9/#10; S55 #100; “Phase 7” distribution | S55 bounded; tool-result execution/distributed workers/deterministic replay unclosed — **phase-only/no successor** (F-009/F-015) |
| Tool Broker | S5 #6; S28–34 #45/#47/#49/#51/#53/#55/#57; S39 #67 | connectors/binding landed; execution, authenticated approvals, credentials/MCP absent — **no successor** (F-009) |
| Audit log | S2 #3; S49 #88; S60 #110; “Phase 7” sink | signed export is not external audit sink — **phase-only/no numbered sink slice** (F-015) |
| Approval engine | S4 #5; S27 #43; S33 #55 | request auth/routing landed; durable timer/external channel absent (F-015); DB bypass F-002 |
| Cost ledger | S7 #8; S51 #92 | ledger/forecast landed; full phase budgets/model-routing actuation unclosed (F-015) |
| Agent registry | S6 #7; S38–41 #65/#67/#69/#71 | factory stores landed; real eval/security/performance/replacement absent; S41 NOT (F-013) |
| Intake sandbox | S9 #11; S35–37 #59/#61/#63 | compiler pieces landed; ML/RAG/binary parsing absent — **no numbered successor** (F-015) |
| Dashboard | S10 #12/#13; S17 #23; S19 #27; “Phase 7 (UI)” | five §18.6 data items and all web UI absent — **phase-only/no numbered UI slice and omitted from the roadmap §12 open-decision list** (`roadmap:836-847`; F-012/F-015) |
| Canonical spine/Sanad | S11 #14 for intake spine; no complete-Sanad slice | spine present; complete §3.4 chain absent (F-014) |
| R0–R5 auditor | S11 #14; S12 #15; S16 #21; S18 #25; S20 #29 | structural ladder present; semantic R5 GAP (F-001) |
| Extractor | S14 #17/#18; roadmap points quality/eval to S40 #69 | S40 is agent qualification, not extractor-quality eval — residual mis-mapped (F-015) |
| Gap detector | S13 #16 | SATISFIED bounded: `app/intake/findings.py:30`; `tests/test_findings.py:43`; `b5ed97d`; #16 |
| Contradiction detector | S37 #63 | SATISFIED bounded: `app/intake/semantic_contradictions.py:61`; `tests/test_semantic_contradictions.py:56`; `98a47ed`; #63 |
| Classifier | S35 #59 | SATISFIED bounded: `app/intake/classifier.py:62`; `tests/test_classification.py:60`; `006ea7e`; #59 |
| Artifact generator | S36 #61 | inert generator; authority/reference-oracle routes unscheduled (F-015) |
| Template pack | scaffold `9a68984` (no numbered slice/PR); S61b #113 companion attempt | pack exists; merged-slice lineage is orphaned and companion-library exit remains open (F-011/F-015) |
| Category model | S15 #20 despite roadmap “none” | input vocabulary present; semantic content absent (F-001) |
| A5 evaluator | S21 #31; evidence chain S28–55; S54 #98 | 13 paths; source-binding bypass and hard-false execution remain (F-005/F-009) |
| Risk acceptance | S22 #33; S47 #84 | signer/release binding landed; mandatory action approval bypass F-002 |
| Findings | S23 #35; S44 #78 | bounded finding/scan stores present |
| Issues | S24 #37; S47 #84 | provenance/bridge present |
| Release candidate | S25 #39; S50 #90 | binding/verdict present |

Additional unsliced requirement orphans from the frozen inventory: §18.3 interview orchestration; §18.4 mid-run freeze/impact/change-request/resume; §18.5 durable nonresponse scheduling; §22 model/prompt/tool change control and forced deprecation; §27.3 `build_readiness_report.json`; §16.1 unified 15-control security review; §11 broker output/rate/cost/tenant enforcement; §12/§23 actual builder/repository/deployment actuation. Evidence: spec `:1772-1811,2091-2147,2568-2585,1548-1568,1067-1084,1146-1226,2188-2212`; no corresponding numbered roadmap exit in `roadmap:176-665`.

### 2.5 Appendix-A R5 semantic coverage

The implementation explicitly checks declaration presence, not content quality (`app/intake/readiness.py:17-23,300-309`); `validate_category_data` accepts `None` or arbitrary non-secret objects (`app/intake/categories.py:138-148`), and the test accepts an empty secrets declaration (`tests/test_intake_categories.py:91-101`). Therefore every Appendix-A condition below is **NOT PROVEN AS WORDED**, even where a category label/store exists.

| IDs | Individual conditions | Result / evidence |
|---|---|---|
| R5-01..05 | purpose; explicit scope; roles; permission matrix; workflows | **0/5 semantically proven**; presence-only rule above |
| R5-06..10 | functional requirements; NFRs; approved critical AC; critical oracles; adequate domain pack | **0/5 semantically proven**; spine validates links, not adequacy/critical completeness |
| R5-11..15 | data contracts; integrations; environments; approved secret-manager refs; approved tools | **0/5 semantically proven**; empty secrets counterexample `tests/test_intake_categories.py:91-101` |
| R5-16..20 | approved autonomy; approval; cost; security/privacy; go-live checklist | **0/5 semantically proven**; category declaration plus two booleans reaches R5 (`tests/test_readiness.py:430-458`) |
| R5-21..25 | rollback; monitoring; reviewed risks; reviewed prior decisions; explicit production authority | **0/5 semantically proven**; `production_authority` is presence-only (`app/intake/readiness.py:53-60`) |

### 2.6 All 13 A5 gates: implementation, PASS, and FAIL-CLOSED tests

`evaluate_production_autonomy` assembles the ordered set at `app/release/production_autonomy.py:1394-1410`; `ProductionAutonomyRepository` calls it at `app/repositories/production_autonomy.py:235-236`; ruleset `slice54.v1` is at `app/release/production_autonomy.py:71`. “Pure PASS” means handcrafted evaluator inputs, not persisted-to-composed proof.

The source-authority sweep below is separate from malformed-row and wrong-object testing. It asks whether `uaid_app` is unable to construct a complete conforming graph bearing the exact trusted/executed/authenticated labels consumed by each gate. The result is **0/13 production-chain authorization-complete**: gate 1 fails semantically; gates 2–6, 8, and 10–13 have runtime-writeable trust graphs; gates 7 and 9 are deterministic structural derivations but inherit caller-controlled or explicitly reported source inputs. This is static catalog/code/test evidence, not a claim that each conforming forgery was executed during the audit.

| Gate | Source-authority evidence | Result |
|---:|---|---|
| 1 | reads runtime-writeable intake/category/budget declarations plus the current admin-controlled policy (`app/repositories/readiness.py:40-87`; runtime grants `migrations/versions/0014_intake_spine.py:266-269`, `migrations/versions/0019_intake_categories.py:153-161`, `migrations/versions/0008_cost_ledger.py:172-186`; current policy write revocation `app/admin/ddl.py:153-155`, verified SELECT-only at `tests/test_policy.py:503-517`) | **FAIL semantic authority** (F-001) |
| 2 | target snapshot permits and grants raw `connector_verified` INSERT with no writer-auth guard (`migrations/versions/0029_deployment_target_evidence.py:7-15,47-60,128-135`); runtime-role test writes it (`tests/test_deploy_evidence.py:275-304,330-345`) | **FAIL source authority** (F-005) |
| 3 | migration says DB cannot attest connector authenticity, permits the label, and retains runtime INSERT (`migrations/versions/0027_connector_verified_evidence.py:7-17,32-76`; `migrations/versions/0025_ci_evidence.py:101-138,170-177`); runtime test accepts it (`tests/test_ci_evidence.py:633-639`) | **FAIL source authority** (F-005) |
| 4 | runtime INSERTs run/results bearing `connector_verified_ci`/`system_executed`; guards rederive shape only (`migrations/versions/0042_test_oracles.py:88-95,128-136,295-342,440-475`; grants test `tests/test_test_oracles.py:912-949`) | **FAIL execution authority** (F-005) |
| 5 | runtime INSERTs trusted scan run/category rows and findings; deferred checks reconcile structure (`migrations/versions/0043_security_scan_provenance.py:61-105,226-286,315-328,477-501`; `migrations/versions/0022_release_findings.py:279-281`) | **FAIL execution authority** (F-005) |
| 6 | runtime INSERTs connector/system/LLM-labelled detector graph; verifier checks panel/aggregate consistency (`migrations/versions/0044_shortcut_detector_execution.py:68-136,371-525,760-779`); the QA overlay is relational and its support tables retain runtime INSERT (`migrations/versions/0047_reviewer_quality_assurance.py:773-858`) | **FAIL execution authority** (F-005) |
| 7 | verdict graph is exactly rederived (`migrations/versions/0049_release_verdicts.py:404-593,617-653`; raw downgrade rejected `tests/test_release_verdicts.py:744-829`), but issue/risk/candidate/evidence sources are caller-writeable (`migrations/versions/0021_risk_acceptance.py:234`, `migrations/versions/0023_release_issues.py:327`, `migrations/versions/0024_release_candidates.py:304-306`, `migrations/versions/0048_evidence_packs.py:84`) | **FAIL production-chain authority through upstream sources** (F-002/F-005) |
| 8 | given an existing read-only global blueprint/version (the normal deployed prerequisite), runtime INSERTs authorship/run/result labels and the supporting instance/realization/qualification/QA/approval graph; guards are relational (`migrations/versions/0045_acceptance_verification.py:27-113,117-267`; global blueprint/version SELECT-only plus instance INSERT at `migrations/versions/0007_agent_registry.py:231-234`; supporting grants `migrations/versions/0038_agent_realization.py:220`, `migrations/versions/0039_qualification_eval.py:436,485`, `migrations/versions/0047_reviewer_quality_assurance.py:72-80,847-858`, `migrations/versions/0005_approvals.py:148`) | **FAIL writer/currentness authority** (F-005/F-006) |
| 9 | all five forecast graph tables accept runtime INSERT; the run alone carries `system_derived_cost_forecast`, while policy/input rows use caller-, reported-, or DB-bound provenance and guards rederive deterministic math over those inputs (`migrations/versions/0050_cost_forecasts.py:49-58,61-120,136-230,265-359,629-645`); the named forge test only UPDATEs append-only rows (`tests/test_cost_forecasts.py:711-749`) | **PARTIAL structural calculation over recorded inputs; not independently authenticated evidence** (F-005/F-008) |
| 10 | runtime INSERTs rollback run/phases bearing `connector_verified_ci_rollback`/`connector_observed_ci`; guards rederive the graph, and the schema expressly says the record is not deployment/execution proof (`migrations/versions/0051_rollback_verifications.py:48-57,60-167,274-480`); SQL tests mutate/omit rather than deny a conforming clone (`tests/test_rollback_verifications.py:791-913`) | **FAIL trusted-observation writer authority** (F-005) |
| 11 | monitoring snapshot has no writer-auth guard and permits/grants runtime `connector_verified` INSERT (`migrations/versions/0030_monitoring_evidence.py:7-16,74-88,169-176`); runtime writes a valid trusted row (`tests/test_monitoring_evidence.py:386-396`) | **FAIL source authority** (F-005) |
| 12 | runtime INSERTs all five preapproval stores plus approvals/notifications and can stamp `request_authenticated`; guards bind graph, not identity (`migrations/versions/0052_production_preapprovals.py:48-57,153-250,258-428,436-635`; `migrations/versions/0005_approvals.py:148`; `migrations/versions/0032_approval_notifications.py:122`) | **FAIL authentication authority** (F-005) |
| 13 | runtime INSERTs five emergency stores and stamps authenticated actors; definer guards validate relations, not actor authentication (`migrations/versions/0053_emergency_controls.py:48-57,68-200,261-333,389-632`); app-layer wrong-actor tests are `tests/test_emergency_controls.py:394-446` | **FAIL safety-critical authority** (F-005) |

Implementation spans in the table below default to `app/release/production_autonomy.py`; a later bare test range inherits the rooted test file earlier in that row.

| Gate | Implementation | PASS test | FAIL-CLOSED / wrong-object test | Verdict |
|---:|---|---|---|---|
| 1 R5 | `app/release/production_autonomy.py:339-343` | persisted/composed `tests/test_production_autonomy.py:419-431` | below-R5 `:435-443`; pure `:70-75` | **FAIL semantic source** (F-001) |
| 2 target | `:345-362` | persisted/composed `tests/test_deploy_evidence.py:793-805` | stale/unverified/unavailable/wrong-target/newer-negative `:808-864`; no conforming-runtime-writer denial | **FAIL source authority:** the trusted row is runtime-writeable (F-005) |
| 3 branch/checks | `:964-998` | persisted/composed `tests/test_ci_evidence.py:643-671` | revision/wrong-repo/unbound-old `:659-688`; conjunction `:446-466`; no conforming-runtime-writer denial | **FAIL source authority:** the trusted row is runtime-writeable (F-005) |
| 4 oracles | `:1031-1165` | persisted/composed `tests/test_test_oracles.py:1178-1224` | pure ladder `:191-276`; no conforming-runtime-writer denial | **FAIL execution authority;** three conjunct mutations also absent (F-005/F-008) |
| 5 security | `:771-852` | pure only `tests/test_security_scans.py:337-340`; store-only `:611-687` | pure ladder/open-critical `:287-334`; raw tests reject incomplete/duplicate graphs `:449-607` | **FAIL execution authority;** no persisted-to-composed PASS and conjunct gaps (F-005/F-008) |
| 6 shortcut | `:853-962` | pure only `tests/test_shortcut_detector.py:276-298` | critical denial `:300-309`; ladder `:338-402`; raw trusted run fails only when children missing `:581-610` | **FAIL execution authority;** no composed PASS and reviewer-count mutation absent (F-005/F-008) |
| 7 risk/issues | `:624-769` | real verdict/composed `tests/test_release_verdicts.py:504-584` | newer-failed invalidates `:586-604`; ladder `:235-309`; exact raw downgrade denied `:744-829` | **FAIL production-chain authority upstream;** verdict rederivation is structural, but caller dispositions/sources remain (F-002/F-005/F-008) |
| 8 generated AC | `:363-411`; `app/verify/acceptance.py:129-156` | pure `tests/test_acceptance_verifier.py:142-160`; store reaches eligible `:368-393` | incomplete raw graph denied `:281-297,412-430`; no complete conforming-runtime-writer denial | **FAIL writer/currentness authority** and no composed PASS (F-005/F-006/F-008) |
| 9 cost | `:412-491` | real store→gate `tests/test_cost_forecasts.py:538-568`; composed `:571-593` | day rollover `:596-618`; ladder `:275-312`; no raw-writer isolation test | **PARTIAL structural calculation over reported inputs;** price/eligibility/provenance mutations absent (F-005/F-008) |
| 10 rollback | `:1167-1293` | pure `tests/test_rollback_verifications.py:375-386`; store coverage `:678-707` | ladder `:389-428`; composed latest-failure `:970-1012`; no conforming-runtime-writer denial | **FAIL execution authority;** no composed PASS and conjunct mutations absent (F-005/F-008) |
| 11 monitoring | `:1000-1029` | persisted/composed `tests/test_monitoring_evidence.py:1139-1160` | newer unreadable supersedes `:1161-1175`; ladder `:1056-1119`; no conforming-runtime-writer denial | **FAIL source authority:** the trusted row is runtime-writeable (F-005) |
| 12 preapproval | `:492-623` | real request/store→gate `tests/test_production_preapprovals.py:536-567` | expiry `:573-581`; 19-rung ladder `:258-288`; same-actor denial `:650-720`; no two-chosen-identity raw denial | **FAIL authentication authority;** conjunct isolation also absent (F-005/F-008) |
| 13 emergency | `:1295-1392` | pure only `tests/test_emergency_controls.py:228-240` | ladder `:164-225`; persisted test stops at missing rollback authority `:450-473`; no conforming-runtime-writer denial | **FAIL safety-critical authority and resume ordering;** no full persisted gate PASS; committed-latch owned resume evaluates cost before stopping (§4.4; F-005/F-008) |

Pure gate regression execution (all 13 files): **531 passed, 192 DB nodes deselected in 2.26s**. Control-loop/ops/review pure execution: **103 passed, 45 DB nodes deselected in 1.30s**. These counts do not upgrade the deselected persisted paths; exact commands are quoted in §4.2.

### 2.7 §2.6 ten mandatory approval actions

The canonical matrix is `app/policy/matrix.py:60-70`; `tests/test_policy.py:65-77,136-142` proves the policy decision for all ten. That is not a non-bypassability proof: live SQL using `uaid_app` inserted all ten as non-explicit and `proceeded_by_policy` (probe §4.4; F-002).

| Required action | Callable implementation / test | Audit result |
|---|---|---|
| protected merge | Tool contract `app/tools/registry.py:94-100`; policy-loop test only | **FAIL DB invariant;** merge actuator absent |
| production deployment | contract `app/tools/registry.py:87-93`, S53 preapproval/control-loop tests | **FAIL generic DB invariant;** final execution remains hard false |
| delete data/infrastructure | matrix only; helper test `tests/test_approvals.py:37-40` | **FAIL DB invariant; callable mutator absent** |
| change secrets | matrix; separate read-only verify tool `app/tools/registry.py:71-75` | **FAIL DB invariant; mutator absent** |
| billing/paid resources | matrix only | **FAIL DB invariant; mutator absent** |
| real-user communication | matrix only | **FAIL DB invariant; external sender absent** |
| sensitive-data access | matrix only | **FAIL DB invariant; access actuator absent** |
| accept risk | concrete `RiskAcceptanceRepository.create` directly makes active record (`app/repositories/risk_acceptance.py:42-85`); authenticated and caller-unverified creation tests `tests/test_identity.py:297-307,335-345` | **FAIL:** action path lacks bound explicit approval; downstream verdict currently refuses authority |
| bypass failed gate | matrix only | **FAIL DB invariant; override actuator absent** |
| weaken tests/reviews | matrix only | **FAIL DB invariant; mutator absent** |

### 2.8 Appendix-C/D and §29 final operating model

| Inventory | Evidence-backed disposition |
|---|---|
| C-01..02 documents/injection | **PASS bounded:** `app/intake/sandbox.py:42`; `tests/test_intake.py:36`; `a522ed5`; #11; classifier/generator boundaries `app/intake/classifier.py:62`, `app/intake/generator.py:70`; `006ea7e`,`03f73b9`; #59/#61 |
| C-03..04 broker/least privilege | **GAP:** broker non-executing and unverified; per-agent least privilege not proven end to end (`app/tools/broker.py:13-16,34-38,225-230`) |
| C-05 audit tamper evidence | **PARTIAL:** audit hash chain/immutability exists, but external sink absent; three other claimed ledgers mutable (probe §4.4) |
| C-06..08 lineage/reviewer QA/fallback | **PASS bounded mechanism only:** `app/verify/acceptance.py:38`; `tests/test_acceptance_verifier.py:35`; `caee2bf`; #82; `app/verify/reviewer_qa.py:67,208-232`; `tests/test_reviewer_quality.py:75`; `da91068`; #86; runtime-writer authority/currentness remain F-005/F-006 and learning drops QA source binding under F-022 |
| C-09 tenant-safe learning | **PARTIAL:** S62 aggregate guards, but consent/privacy proof absent and tenant GUC selectable |
| C-10 generated-agent security | **GAP:** no executed security review; S41 exit NOT |
| C-11 tenant boundaries | **FAIL:** live runtime role can select another tenant GUC; `audit_logs` lacks the full RLS triple, while the second raw-catalog exception is explicitly global/pre-tenant (`app/models/tenant_api_key.py:1-5`; F-003/F-019; §4.4) |
| C-12 connectors tested/scoped | **GAP:** D-8/D-9 open (roadmap `:845-847`) |
| C-13 secrets | **PASS bounded:** reference-only validation `app/intake/categories.py:71-79,138-164`; `tests/test_intake_categories.py:91-110`; verifier `app/release/secrets_verification_service.py:34`; `tests/test_secrets_verification.py:56`; `214495c`; #53; no mutation connector |
| C-14 unsafe assumptions | **PASS bounded:** readiness classifies non-safe assumptions blocked (`app/intake/readiness.py:326-336`); full authority resolution absent |
| C-15 cost stop | **PASS bounded cost behavior only:** cost truth-table plus a cost-paused start before graph-stage progress (`tests/test_cost.py`; `tests/test_control_loop.py:804-840`). This is not production emergency→cost ordering; real owned resume evaluates cost while the latch is active (§4.4/F-008). |
| C-16 overrides | **FAIL generic approvals:** live §2.6 forgery; admin writer is tighter but not a substitute |

| Appendix-D upgrade | Mapping | Verdict |
|---|---|---|
| D-01 reviewer QA | `app/verify/reviewer_qa.py:67`; `tests/test_reviewer_quality.py:75`; `da91068`; #86 | PASS bounded mechanism only; writer authority F-005 and aggregate lineage loss F-022 |
| D-02 archetype methodology | S40 record-only | PARTIAL |
| D-03 provider fallback | `app/verify/reviewer_qa.py:208-232` | PASS bounded |
| D-04 external export | S60 | PARTIAL (F-016) |
| D-05 risk acceptance | S22/S47/S50 | FAIL action approval (F-002) |
| D-06 forced deprecation | no runtime | GAP |
| D-07 tenant-safe learning | S62 | PARTIAL / tenant boundary fail |
| D-08 judgment thresholds | binding defaults `docs/UAID_OS_Intake_Template_Pack_v1_2/09_test_oracles.yaml:8-13`; `app/verify/oracles.py:307-380,575-587`; `tests/test_test_oracles.py:293-340`; `52785b3`; #76 | PASS bounded |
| D-09 prompt-family definition | `app/intake/generator.py:114-157`; `tests/test_generator.py:183-198`; `03f73b9`; #61; acceptance lineage `app/verify/acceptance.py:38`; `caee2bf`; #82 | PASS bounded |
| D-10 stabilization exit/authority | S59 | GAP / exit NOT |
| D-11 26-file intake | docs/categories only | PARTIAL / semantic R5 fail |
| D-12 cost variance note | documentation only | PARTIAL |
| D-13 provider-outage stop | no model-change actuator | GAP |
| D-14 per-decision authorities | template/generator fields only | PARTIAL |
| D-15 deterministic replay | checkpoint substrate only | PARTIAL; no full replay proof |
| D-16 spelling | spec/documentation | PASS (`spec:3039`) |

| §29 item | Verdict / implementation evidence |
|---:|---|
| 1 accept serious documentation | GAP: text/JSON only; binary/ML/RAG absent |
| 2 determine build-ready | GAP: presence-only R5 |
| 3 compile missing specs safely | GAP: inert/incomplete approval routes |
| 4 block unsafe missing decisions | PARTIAL: readiness/findings primitives |
| 5 staff specialists | **PASS bounded:** `app/agents/skills.py:83`; `tests/test_skills.py:53`; `ae3ea90`; #65 |
| 6 create governed agents | **PASS bounded:** `app/agents/factory.py:32`; `tests/test_factory.py:32`; `9ea4f90`; #67 |
| 7 set up tools/repos/workflows/tests/environments | GAP: evidence readers, no actuator |
| 8 build controlled iterations | GAP: no build actuator |
| 9 independent review | GAP: reported-review records only |
| 10 detect shortcuts | **PASS bounded mechanism only:** `app/verify/shortcut_detector.py:48`; `tests/test_shortcut_detector.py:30`; `d063ebe`; #80; persisted execution/source authority remains F-005/F-008 |
| 11 verify with oracles | **PASS bounded mechanism only:** `app/verify/oracles.py:58`; `tests/test_test_oracles.py:57`; `52785b3`; #76; persisted execution/source authority remains F-005/F-008 |
| 12 maintain Sanad chains | GAP: shallow/intake-only provenance |
| 13 evidence artifact of done | **PASS bounded mechanism only:** `app/release/evidence_pack.py:125`; `tests/test_evidence_packs.py:124`; `0a04aec`; #88; export `app/release/export_bundle.py:43`; `tests/test_export_bundle.py:76`; `8e001ca`; #110; upstream source authority/composed-proof/export scope remain F-005/F-008/F-016 |
| 14 control cost/authority/tenancy/security/tools | GAP: approval/RLS/broker/D-8/D-10 failures |
| 15 deploy only under policy/evidence | GAP capability: deployment absent |
| 16 monitor/stabilize | GAP: assessment only; S58/S59 NOT |

## 3. Findings ledger

The slice numbers below are proposals for the owner’s later authorization. They do not create work, change the roadmap, or lift `STOP. No Slice 64.`

Ledger count: **22 findings — 8 blocker, 13 major, 1 minor**. Mechanical table parse output: `FINDING_ROWS=22`; proposed remediation numbers are contiguous `64`–`85`.

| Finding | Severity | Specification / evidence | Required remediation outcome | Proposed slice |
|---|---|---|---|---:|
| F-001 Semantic R5 can be reached from declarations without semantic completeness | **blocker** | Appendix A/spec `:2951-2979`; implementation says presence, not quality (`app/intake/readiness.py:17-23,300-309`); arbitrary/empty category data accepted (`app/intake/categories.py:138-164`); empty secrets accepted (`tests/test_intake_categories.py:91-101`) | Validate and prove each of 25 R5 conditions, including approval/authority/currentness, with direct negative mutations | 64 |
| F-002 Approval/override authority is bypassable: all ten §2.6 rows, risk acceptance, and release-blocker disposition | **blocker** | spec §§2.4/2.6/24.1 `:180-194,213-228,2253-2271`; generic approvals lack the action→explicitness graph and accepted ten forged rows (§4.4; `app/models/approval.py:34-65`; `migrations/versions/0005_approvals.py:138-149`); active risk is writable without approval while verified limitation authority is hardcoded false (`app/repositories/risk_acceptance.py:42-85`; `app/repositories/release_verdicts.py:218-243,336-369`); tenant-session repository methods (no dedicated HTTP route found) let untrusted caller labels resolve/false-positive/supersede findings/issues (`app/repositories/release_findings.py:1-10,49-66,114-128`; `app/repositories/release_issues.py:1-12,173-181,230-248`; tests `tests/test_release_findings.py:293-315`, `tests/test_release_issues.py:256-273`), and verdict evaluation excludes those statuses (`app/release/release_manager.py:172-208`; `app/repositories/release_verdicts.py:298-330`) | Controlled DB writers; structural action/state/event constraints; authenticated, subject-bound approval and disposition authority; remediation/primary-evidence/reviewer-rerun binding; real-role negatives for all ten actions and trusted finding/issue closure | 65 |
| F-003 Runtime RLS role can select another tenant’s GUC | **blocker** | spec §17 `:1692-1752`; live probe: RLS blocks mismatched-context reads/writes but `uaid_app` can set `app.current_tenant` to the victim and read it (§4.4); policy derives identity from GUC (`app/tenancy.py`) | Bind tenant context to non-user-selectable authenticated identity/session, test credential-holder cross-tenant attacks | 66 |
| F-004 Three ledgers described as append-only accept owner UPDATE/DELETE/TRUNCATE | **major** | spec §16.6 `:1616-1627`; live probes succeeded for `approval_events`, `tool_calls`, `agent_tool_allowlist` (§4.4); their contracts say append-only/immutable (`app/models/approval_event.py:1-4`, `app/models/tool_call.py:1-3`, `app/models/agent_tool_allowlist.py:1-5`; migration `migrations/versions/0005_approvals.py:147-149`) | Add/revoke/guard required operations and load-bearing owner/runtime mutation tests; document any intentionally mutable registry separately | 67 |
| F-005 Runtime role can self-stamp trusted/executed/authenticated/observed A5 source graphs, and synthetic final gate rows can create an official `decided_not_executed` chain | **blocker** | spec §15.1/Appendix B `:1413-1419,2981-2997`; gates 2/3/11 directly trust runtime-writeable `connector_verified` rows (`migrations/versions/0029_deployment_target_evidence.py:47-60,128-135`; `migrations/versions/0027_connector_verified_evidence.py:7-17,32-76`; `migrations/versions/0030_monitoring_evidence.py:74-88,169-176`); runtime can INSERT and self-label trusted execution/authentication/observation graphs for gates 4–6/8/10/12/13 (`migrations/versions/0042_test_oracles.py:88-95,128-136,451-475`; `migrations/versions/0043_security_scan_provenance.py:61-105,477-501`; `migrations/versions/0044_shortcut_detector_execution.py:68-136,760-779`; `migrations/versions/0045_acceptance_verification.py:27-113,254-267`; `migrations/versions/0051_rollback_verifications.py:48-57,60-167`; `migrations/versions/0052_production_preapprovals.py:48-57,153-428,619-635`; `migrations/versions/0053_emergency_controls.py:48-57,68-200,261-468,620-632`); gate 10 specifically stores connector-verified/observed evidence that its schema says is not deployment/execution proof (`migrations/versions/0051_rollback_verifications.py:111-144`), and guards validate graph shape/relations rather than the asserted connector/model/request/observation event (§2.6). Supporting PR and secret-resolution paths have the same trusted-label boundary (`migrations/versions/0028_pull_request_evidence.py:115-128,164-220,249-256`; runtime-role/catalog tests `tests/test_pr_evidence.py:328-361,437-460`; `migrations/versions/0031_secret_reference_checks.py:43-56,124-131`). Gate 7 is structurally rederived but inherits caller-writeable issue/risk/candidate/evidence sources; gate 9 deterministically derives from reported inputs (§2.6). Above those stores, `ProductionAutonomyReport.a5_satisfied` accepts any nonempty all-pass list (`app/release/production_autonomy.py:102-110`), `record_evaluation` persists the submitted report (`app/repositories/go_live_decisions.py:337-425`), and DB finalization validates row shape/digests rather than rereading the thirteen canonical stores (`migrations/versions/0054_control_loop_decisions.py:546-565,639-705`); the positive test fabricates `gate_1..13` (`tests/test_control_loop.py:968-1017`) | Revoke raw runtime trusted-tier graph INSERTs; expose controlled writers/procedures authenticated to the exact connector/model/request/observation event and bound primary evidence; add a same-runtime-role complete-conforming-graph denial for each affected gate; bind gates 7/9 to an authenticated, complete source universe; make finalization reread/canonically bind all thirteen sources in one transaction and reject synthetic all-pass reports | 68 |
| F-006 Gate 8 current reviewer/QA failure branches are unreachable in the real repository | **major** | spec §13.5/Appendix B `:1315-1345,2992`; evaluator checks active/qualified/distinct/current (`app/verify/acceptance.py:129-156`), but repository maps each from non-null reviewer ID and `current_record=True` (`app/repositories/acceptance_verification.py:309-348`); QA can later expire/breach (`tests/test_reviewer_quality.py:775-841`) | Re-read/bind current reviewer realization, lineage and QA, or define immutable-at-approval semantics; add expiry/suspension/breach mutations | 69 |
| F-007 Literal-false truth is not structurally closed on auxiliary surfaces | **major** | spec §24.1 `:2249-2271`; main evaluator/readiness hard-false (`app/release/production_autonomy.py:112-125`; `app/intake/readiness.py:338-343`) and final decision DB CHECK is strong (`app/models/go_live_decision.py:356-363`; test `tests/test_control_loop.py:1546-1613`), but `readiness_reports` has no false CHECK and retains a runtime INSERT grant (`migrations/versions/0015_readiness_reports.py:102-104`); dashboard echoes it (`app/api/dashboard.py:65-73`); unvalidated `DecisionOutcome` accepts caller truth fields (`app/release/go_live_decision.py:164-171`), while forbidden-field sanitization is separate at `:78-92,262-270` | Controlled readiness insert/hard-false consistency; validate `DecisionOutcome`; wire exact truth-field sanitizer at ingress | 70 |
| F-008 A5/load-bearing/E2E test gaps and emergency resume-order failure | **major** | spec §24/Appendix B `:2249-2315,2981-2997`; no persisted-to-composed PASS for gates 5/6/8/10/13; conjunct gaps listed §2.6, including gate-12 `notification_valid` trusting the canned `delivered` row (`app/repositories/production_preapprovals.py:615-666`; gate `app/release/production_autonomy.py:492-524,571-623`). The committed-latch owner-role probe (§4.4/Appendix A) observed `cost_evaluator_calls_while_active=1` and `product_invariant_passed=false`: real resume reads emergency, nevertheless evaluates cost, and only then returns for the latch (`app/runtime/control_loop.py:646-673`), contrary to `.planning/SLICE-55-PLAN.md:256-267,682-688`. The intended `run_guarded_stage` order is dead outside isolated tests (`app/runtime/control_loop.py:72-83`; repository-wide references only `tests/test_control_loop.py:287-354`). The source-text test merely checks that legacy entry/work-node source mentions `_emergency_boundary` (`tests/test_emergency_controls.py:254-276`); the all-eight behavioral test activates before entry, so an outer guard can mask a missing inner/node guard (`:540-601`), while only demo node B has mid-run activation/checkpoint behavior (`:513-537`). Only negative tests exercise `staging_evidence_observed_not_deployed` (`tests/test_control_loop_owner_retry.py:376-452`; contract `.planning/SLICE-55-PLAN.md:122,366`) | Check committed emergency state before cost on the real owned resume path; move the active-latch check before `start_cycle`, or make the session-bound helper non-public and enforce that every caller uses the owned transaction wrapper so catching the refusal cannot persist the pre-latch cycle; make production use the guarded-stage order; add a load-bearing owned-resume test whose cost evaluator fails if called while active, an owned-start transaction-boundary test, and before/after assertions for both checkpoint tables; add one real-store PASS + wrong-object/newer-negative per gate, individual conjunct mutations including delivery/receipt, every inner-boundary mutation/mid-run window, and a positive bounded staging-evidence test without claiming deployment | 71 |
| F-009 Tool Broker/actuator chain does not execute; ecosystem mislabels authorization decisions as tool reliability | **blocker** | spec §§11/12/17.5/23/29 (`spec:1067-1144,1146-1226,1724-1752,2149-2247,2918-2947`); broker/control loop perform no execution (`app/tools/broker.py:13-16,34-38,225-230`; `app/runtime/control_loop.py:1-6`; `tests/test_control_loop.py:217-253`); learning SQL counts authorization rows and defines failure as broker denial (`app/ecosystem/learning_sql.py:111-126`; row model `app/models/tool_call.py:1-4,23-34`), then optimizer names it `generic_tool_reliability` and can recommend `hold` (`app/ecosystem/cost_optimizer.py:201-228`; zero-result tests `tests/test_cost_optimizer.py:178-203`, `tests/test_cost_optimizer_db.py:283-315`) | Authenticated, credentialed, rate/cost/output-validating broker plus governed build/PR/CI/staging/production/rollback actions; derive reliability from execution result/error/latency evidence, or rename denial-frequency and keep it explicitly non-actuating | 72 |
| F-010 Slice 58/59 exits remain open; stabilization’s sole passable criterion trusts unverified caller state | **blocker** | spec §25 `:2345-2424`; roadmap `:583-607`; hotfix says no DB/git/deploy/rollback (`app/ops/hotfix.py:1-4`; tests `tests/test_ops_hotfix.py:176-190,279-286`); stabilization is open-only/unreachable all-pass (`app/ops/stabilization.py:1-5,22-77`); handover PASS checks only `status="recorded_complete"` and ignores provenance (`app/ops/stabilization_criteria.py:81-94`, repository feed `app/repositories/ops_stabilization.py:231-243`), while actorless writes are `caller_supplied_unverified` and the positive DB test uses that path (`app/repositories/ops_incidents.py:371-393`; `tests/test_ops_stabilization_db.py:60-87`) | Diagnosis/patch/git/PR/staging/production/rollback actuators; measured backup/restore criteria; authenticated/authorized independently acknowledged handover evidence; authority closure and acting improvement | 73 |
| F-011 Slice 61/D-8–10 remain open, and catalog population manufactures review PASS | **blocker** | spec §11.3/Appendix D `:1102-1117,3024-3033`; roadmap `:623-641,845-847`; `_list_review` records `outcome="passed"` with asserted provenance without reading review evidence and uses it to list every blueprint/intake (`app/ecosystem/catalog_populate.py:149-224,235-270`); repository only validates vocabulary and persists caller outcome (`app/repositories/catalog_admin.py:242-272`); tests assert the manufactured PASS/labels (`tests/test_ecosystem_catalog_populate_db.py:265-319`, `tests/test_ecosystem_catalog_populate_review_db.py:90-120`); main commits explicitly “does not close Slice 61” (`17e7fc9`,`59af1c7`,`96faa86`,`e6fbddc`) | Permission-scope proof, live-provider testing, executed primary-evidence reviewer/attestor for blueprint and intake, and closure of the combined library exit | 74 |
| F-012 §18.6 owner web UI and five required data surfaces are absent | **major** | spec `:1813-1828`; dashboard source defers forecast/critical path/evidence/deployment/next action (`app/api/dashboard.py:7-12`) and `app/main.py:22-27` mounts API routers only; roadmap schedules “Phase 7 (UI)” (`roadmap:81`) with no numbered slice and omits it from the §12 open-decision list (`roadmap:836-847`) | Implement human-facing UI plus all ten fields, pagination/currentness/accessibility/security tests | 75 |
| F-013 Qualification and maker-checker-verifier paths are caller-recorded fake-done boundaries | **blocker** | spec §§9/13 `:836-944,1228-1345`; qualification runs no agent (`app/agents/qualification.py:3-10`), failure policy does not suspend (`tests/test_failure_policy.py:645-669`), and task review accepts reported content (`app/review/workflow.py:1-12,61-62`); classification/extraction approve on distinct free-text actor labels (`app/repositories/classification.py:211-244`; `app/repositories/extraction.py:211-241,296-335`; `tests/test_classification.py:651-673`), while generator documents caller-unverified labels and accepts supplied authority/lineage/prompt-family strings (`app/intake/generator.py:9-12,114-155`; `app/repositories/generator.py:206-267`; `tests/test_generator.py:751-822`); S41 exit `roadmap:381` | Execute evals/Agent-QA/security/performance/replacement and all independent review orchestration over primary evidence; bind reviewer identity, authority, current qualification, lineage and review output to authenticated/DB-resolved facts | 76 |
| F-014 Al-Muhasibi/Sanad kernel is materially absent | **major** | spec `:238-340`; current `app/core/provenance.py:16-41` is Source/Fact and `app/core/reasoning.py:15-40` checks nonempty answer/sources/callbacks only | Structured five-stage decision records and full narrator/reliability/consistency/context/verdict/evidence chain | 77 |
| F-015 Multiple mandatory components/artifacts/state collections/residuals have only phase labels or no slice; dashboard delivery is a gate-bearing recorded no-op | **major** | orphan table §2.4; examples: audit external sink roadmap `:76`, dashboard UI `:81`, model change spec `:2091-2147`, mid-run correction `:1786-1795`, runtime actuators `:2188-2212`, and the unsliced canonical `build_readiness_report.json` shape (`spec:2568-2585`; missing-field mapping R-27-01). The §23.4 atomic map finds no user collection, actual agent-run collection, or deployment collection/actuator, while general decisions and connectors have only specialized/declaration representations (§2.2 R-23-04). The template pack exists only in scaffold `9a68984`, not a numbered merged slice/PR; `DashboardChannel.deliver` performs no I/O and always returns `"delivered"`, which the service persists (`app/approvals/channels/adapter.py:1-7,40-47`; `app/approvals/channels/service.py:35-48`; test `tests/test_approval_channel.py:265-270`); preapproval converts that label into `notification_valid`/gate eligibility (`app/repositories/production_preapprovals.py:615-666`; positive gate-12 path `tests/test_production_preapprovals.py:535-567`) | Owner disposition and numbered closure for every residual; implement and schema-test the exact §27.3 report artifact plus the missing user/agent-run/deployment state and general decision/active-connector models; real channel delivery/receipt evidence and scheduler; no gate-bearing `delivered` outcome or “nothing unscheduled” claim until primary evidence and mapping exist | 78 |
| F-016 Evidence/assurance export is narrower than the normative contract | **major** | spec §15.4 `:1492-1546`, §28 `:2832-2914`; schema conflict DCONF-01; S60 offline-only, unenforced 720h, no OSCAL/scoped-link/temp-account (`app/release/export_bundle.py:24-38,82-93`) | Reconcile verdict/field schemas; version migrations; enforce access expiry/redaction links; add required modes/policy-triggered OSCAL | 79 |
| F-017 Full repository Pyright fails while CI typechecks only owned late-slice paths | **major** | spec §§13.4/24.2 `:1298-1313,2296-2302`; clean full run: `477 filesAnalyzed, 3050 errors` (§4.2); CI line is scoped to S55–63 (`.github/workflows/ci.yml:61-62`); Ruff/tests still pass | Establish full type baseline or explicit ratchet, eliminate errors, make the actual promised scope mandatory | 80 |
| F-018 Project ledgers contain stale/contradictory closure statements | **minor** | spec §§15.1/29 `:1413-1419,2918-2947`; `.planning/HANDOFF.json:77-79` says no remaining tasks/blockers while `:164-168` lists open residuals; roadmap graph/M6 “reachable/functional” wording `:723-736,753-754` conflicts with S58/S59 NOT and literal false; `README.md:660-688` and `CLAUDE.md:1455-1475` retain old A5 status; dashboard comment `app/api/dashboard.py:22-24` says `a5_satisfied` always false although `app/release/production_autonomy.py:107-110` can make it true | Reconcile status ledgers and code comments to precise bounded/current claims without changing the stop absent owner direction | 81 |
| F-019 `audit_logs` fails the requested ENABLE+FORCE+`tenant_isolation` invariant | **major** | raw catalog: `TENANT_ID_TABLES=123 FULL_RLS_TRIPLE=121 EXCEPTIONS=audit_logs,tenant_api_keys` (§4.4); `tenant_api_keys` is explicitly global/pre-tenant (`app/models/tenant_api_key.py:1-5`; `app/repositories/api_keys.py:6,34,73-76`), so the tenant-owned denominator is 122 and `audit_logs` is the remaining mismatch; spec §17 `:1692-1752` | Add FORCE RLS and a tenant policy to `audit_logs` while retaining its controlled writer; catalog assertion must enumerate and distinguish all 122 tenant-owned plus the global auth lookup | 82 |
| F-020 Six captured first-write conflict signatures lack retained reproduction; the every-writer pair sweep is unproved | **major** | spec §23.2 `:2168-2186`; conservative AST census `DIRECT_WRITER_ENDPOINTS=119`, plus three indirect SQL-function wrapper endpoints, for `CANDIDATE_WRITER_ENDPOINT_TOTAL=122` (§4.6/Appendix B). Fourteen ad-hoc result records report `6` unhandled `23505` conflicts and `8` conforming outcomes, but their exact pair-driver programs were not retained. The separate retained OD-11 test maps to `admin_write_autonomy_policy` (`app/repositories/admin.py:91-114`; `tests/test_admin_policy_race_db.py:49-99,141-192`), making audit-action coverage `15/122` distinct endpoints, retained reproducible audit-specific coverage `1/122`, and `107/122` untouched by those actions. The six unretained signatures name `BudgetRepository.upsert` (`app/repositories/cost.py:184-222`), `register_blueprint`/`register_version` (`app/agents/registry.py:102-176`), `CatalogAdoptionRepository.adopt` (`app/repositories/catalog_adoptions.py:31-62`), `CostForecastRepository.record_policy_version` (`app/repositories/cost_forecasts.py:153-214`), and `ExtractionRepository.promote_proposal` (`app/repositories/extraction.py:296-389`); captured records report one `IntegrityError`/`23505` loser and final row_count one, but require rerun before being treated as retained load-bearing findings | Reproduce and retain each six-signature harness/result first; make every verified idempotent/create-once writer return the winner or a domain result under contention (atomic conflict handling, advisory/key lock, or equivalent); publish a deduplicated, semantically closed writer-leaf inventory; add and retain a load-bearing two-session absence barrier per candidate endpoint, including compound child writers and all three SQL wrappers | 83 |
| F-021 Load-bearing tests can pass on neighboring constraints, invalid setup, or the wrong repository/DB branch | **major** | spec §16.6 `:1616-1627`; Slices 43–63 weakened the `cost_events` assertion from only `"immutable"` to `"immutable" or "cannot truncate"` (`tests/test_cost.py:472-485`), and the live positive-control reached the intended guard only with `TRUNCATE cost_events CASCADE`, returning `cost_events is immutable (no UPDATE/DELETE/TRUNCATE)` (§4.4). The global-skill test similarly accepts any of `append-only`, `immutable`, or `cannot truncate` for all three tables (`tests/test_skills.py:405-419`), while `skills` and `agent_skill_capabilities` are FK-referenced by `agent_provided_skills` and have named truncate guards (`migrations/versions/0037_skill_matching.py:124-146,293-312`). Its runtime-role INSERT check uses `DEFAULT VALUES` and accepts any exception (`tests/test_skills.py:373-387`), so NOT NULL/FK rejection would mask an accidental INSERT grant; the intended ACL is SELECT-only (`migrations/versions/0037_skill_matching.py:314-317`). The full deleted-line history sweep also found Slice-47 regressions: the critical-finding test now fails while creating its risk record and never calls `ReleaseFindingRepository.accept` (`tests/test_release_findings.py:333-341`; unexercised branch `app/repositories/release_findings.py:68-80`; base call `52785b3^:tests/test_release_findings.py:236-246`); finding/issue wrong-project and wrong-subject cases now fail during risk-record setup instead of executing the named acceptance guards (`tests/test_release_findings.py:531-573`; `tests/test_release_issues.py:548-589`; base direct-SQL calls `52785b3^:tests/test_release_findings.py:470-478`, `52785b3^:tests/test_release_issues.py:570-578`; guard predicates `migrations/versions/0046_issue_provenance.py:240-257,326-341,394-423`); and the claimed cross-tenant CREATE/RLS test can fail in `_require_subject_binding` before `session.add` (`tests/test_risk_acceptance.py:306-327`; `app/repositories/risk_acceptance.py:42-46,87-105`) | Exercise each named trigger via controlled `TRUNCATE ... CASCADE` and assert its exact table-specific rejection; assert exact role grants and attempt a structurally valid runtime-role INSERT for every global table; independently test neighboring FK/shape failures; restore a direct critical `accept` call; construct separately valid wrong-project/wrong-subject records before direct acceptance; use structurally valid cross-tenant SQL and assert exact RLS attribution | 84 |
| F-022 Cross-project learning erases source trust tiers and publishes untrusted-input-contaminated operational metrics | **major** | spec §§2.4/17.5 `:180-194,1724-1750`; after the 3-project/2-tenant threshold (`app/ecosystem/learning.py:26-27`; `app/repositories/learning.py:47-48`), all seven source-query classes aggregate without source-tier composition or binding (`app/ecosystem/learning_sql.py:33-191`). Inputs include caller-supplied/unexecuted qualification (`app/models/qualification_run.py:1-9,68,93-108`), reported unverified agent failures (`app/models/agent_failure_event.py:1-14,75-78,99-108`), caller-unverified release findings (`app/models/release_finding.py:1-11,109-111`), non-executed broker authorization decisions (F-009), and caller-recorded cost component/amount rows (`app/repositories/cost.py:1-8,47-82`; `app/models/cost_event.py:51-108`). Reviewer-QA status/latency sources carry model/prompt/fixture/contract/policy hashes (`app/models/reviewer_quality.py:198-210,241-309,312-368`; executed repository path `app/repositories/reviewer_quality.py:106-243`), but aggregation drops that lineage (`app/ecosystem/learning_sql.py:52-68,88-106`); moreover, runtime has raw INSERT on those tables and connector tables, whose guards permit self-labelled trusted literals/shape without proving the external call (`migrations/versions/0047_reviewer_quality_assurance.py:72-80,512-570,847-858`; connector enum/grants `migrations/versions/0029_deployment_target_evidence.py:47-60,128-135`, `migrations/versions/0030_monitoring_evidence.py:74-88,169-176`, `migrations/versions/0031_secret_reference_checks.py:43-56,124-131`). Published rows retain aggregate dimensions/counts/sum/unit/publication but no source-tier composition or source-binding hashes (`app/models/cross_project_aggregate.py:56-83`; `app/repositories/learning.py:39-70`); the optimizer consumes published cost sums (`app/ecosystem/cost_optimizer.py:231-246`; `app/repositories/cost_optimizer.py:175-199`). The P-4 test checks only a forbidden-column-name list and contains no source-tier assertion (`tests/test_learning.py:64-72`) | Move trusted-tier writes behind controlled, execution-bound writers; prove connector/reviewer execution from primary evidence before filtering; publish separately named unverified and broker-authorization buckets; preserve tier composition/source hashes; add poisoning mutations for every source class and prove untrusted/self-labelled/cost rows cannot alter optimizer decisions | 85 |

No absence-of-race conclusion is made; F-020 records the unclosed denominator.

## 4. Probe and suite evidence

### 4.1 Baseline and cleanliness

The documentation-only reader checkpointed before it was allowed to inspect code:

```text
all 40 permitted documentation files are fully read
(spec, 26 templates, pack + reference files, 7 schemas,
roadmap, CLAUDE, README); no code/tests/migrations/scripts/git/
slice plans inspected
```

The source census was independently reproduced:

```text
SPEC_LINES=3040
TOP_LEVEL_TEMPLATES=26
PACK_README=1
REFERENCE_FILES=2
SCHEMA_FILES=7
ROADMAP_CLAUDE_README=3
TOTAL=40
```

**Sequence disclosure:** before the owner supplied the later Phase-0 ordering message, the coordinating auditor had already opened `app/db.py` and `app/config.py`. After that message, application inspection stopped until a separate context-isolated reader completed and froze the 40-file documentation-only inventory quoted above. Those two early files were not supplied to that reader and did not define or narrow §1. This disclosure is audit-protocol evidence, not a claim that the earlier reads can be undone.

```text
$ git branch --show-current
main
$ git rev-parse HEAD
50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba
$ git rev-parse origin/main
50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba
$ git status --short
?? .planning/FINAL-AUDIT-REPORT.md
?? UAID_OS/
$ git -C UAID_OS rev-parse HEAD
50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba
$ git -C UAID_OS status --short
<no output>
```

The nested `UAID_OS/` checkout was the clean-suite checkout; it remained clean after all commands. The outer report and pre-existing nested checkout are the only untracked paths. Evidence: quoted commands above.

### 4.2 Mandatory clean-checkout suites

All runs set `PYTHONDONTWRITEBYTECODE=1`, disabled pytest cache, placed tool caches in `/tmp`, and used the lock-compatible existing environment. The DB target ran against an isolated PostgreSQL-16 container, not the repository’s existing `app_test`.

```text
$ make test
1277 passed, 1085 deselected, 1 warning in 3.67s
exit 0

$ make test-db
CREATE DATABASE
... Alembic upgrade head ...
1085 passed, 1277 deselected, 1 warning in 109.65s (0:01:49)
exit 0

$ uv run ruff check .
All checks passed!
exit 0

$ uv run pyright --venvpath /tmp/uaid-final-audit-pyright-env-50bc055 --outputjson
{'filesAnalyzed': 477, 'errorCount': 3050, 'warningCount': 0,
 'informationCount': 0, 'timeInSec': 9.936}
exit 1
```

One preliminary constrained-runner health invocation timed out (`exit 124`); no repository conclusion is drawn from it. The same clean health file in the unrestricted audit environment returned:

```text
tests/test_health.py: 4 passed, 1 deselected, 1 warning in 0.65s
```

The authoritative unrestricted full `make test` then passed all 1,277 selected nodes as quoted above, so the preliminary timeout is not counted as a repository finding.

Targeted gate/review runs independently returned:

```text
13 A5 implementation test files: 531 passed, 192 deselected in 2.26s
control-loop/ops/review files:     103 passed, 45 deselected in 1.30s
```

The deselections are DB-marked nodes and were not treated as executed by those targeted commands; they are included in the full `make test-db` count.

#### Disposable DB cleanup proof for `make test-db`

```text
container: uaid_final_audit_pg_50bc055_20260824
container id: ff77e92e5c5e6f546568d243a89d3c55f91a7282d23119b23a3f75fae2d27935
/var/run/postgresql:5432 - accepting connections
DROP DATABASE
SELECT count(*) FROM pg_database WHERE datname='app_test' -> 0
docker stop -> uaid_final_audit_pg_50bc055_20260824
docker ps -a --filter name=... -> <no output>
```

### 4.3 Test-suite and workflow history, Slices 43–63

```text
$ git diff --diff-filter=D --name-only 52785b3^..HEAD -- tests .github/workflows
<no output>
$ git diff --numstat ... | aggregate
TEST_INSERTIONS=30214 TEST_DELETIONS=242 TEST_FILES_CHANGED=100
$ git log -G 'pytest.mark.(skip|xfail)|pytest.(skip|xfail)' 52785b3^..HEAD -- tests
d063ebed3e2e41eefe3ed15d0770e3e2da779b67 feat: execute Slice 45 shortcut detector (A5 gate #6) (#80)
HISTORY_SKIP_XFAIL_COMMITS=1 FIXTURE_TEXT_ONLY=1 ACTUAL_SKIP_OR_XFAIL_ADDED=0
BASE_TEST_FILE_NAME_NODES=1046 HEAD_TEST_FILE_NAME_NODES=1694
ADDED_FILE_NAME_NODES=650 REMOVED_FILE_NAME_NODES=2 UNIQUE_ADDED_BARE_NAMES=644
DELETED_TEST_LINES=242 DELETION_HUNKS=184 TEST_FILES_WITH_DELETIONS=24
ASSERTION_DELETIONS=35 NONASSERTION_DELETIONS=207
BENIGN_EXACT_OR_STRONGER_DELETIONS=228 WEAKENED_DELETIONS=14 LOAD_BEARING_PROBLEMS=5
```

- **PASS — no Slice-43–63 xfail or executable skip was introduced.** The history search returned only `d063ebe`; its added match is a quoted malicious-test corpus string, not a decorator (`tests/test_shortcut_detector.py:81-84`). Current `rg` found no xfail and only that fixture text plus two DB-unavailable runtime skips at `tests/conftest.py:79,121`; blame attributes both skips to `b748566`, before the Slice-43 base. CI provisions PostgreSQL and runs DB setup before DB pytest (`.github/workflows/ci.yml:19-44,67-71`).
- **PASS — no test/workflow file deletion.** The deletion command returned no output, quoted above.
- **PASS — the numeric test population grew, but that fact is not treated as proof of strength.** The tests-only diff is 30,214 insertions/242 deletions across 100 files. Historical AST comparison found 650 file/name nodes added and two removed (`1046 + 650 - 2 = 1694`); those additions contain 644 unique bare names because six names occur in more than one file. The two removed nodes were renames: `test_gates_5_6_are_insufficient_no_finding_provenance` became `test_gates_5_6_are_insufficient_without_their_required_evidence` in S44; `test_sourceless_gates_are_no_evidence_source` became `test_no_a5_gate_remains_sourceless` in S54. Evidence: Git/AST comparison over `52785b3^..HEAD`; current nodes `tests/test_production_autonomy.py:85,193`.
- **FAIL — the assertion-only subset contains one genuine weakening.** The 35/35 assertion classification is quoted below: `EXACT_OR_STRONGER=20`, `BENIGN_CONTRACT_OR_RULESET_REBASELINE=14`, `WEAKENED=1`. The failure is the old exact `"immutable"` assertion: current `tests/test_cost.py:472-485` accepts `"immutable"` **or** neighboring-FK `"cannot truncate"`; migration `migrations/versions/0008_cost_ledger.py:144-169` names the intended trigger and `migrations/versions/0050_cost_forecasts.py:265-288` adds the referencing FK. The independent live probe in §4.4 reached the named guard only with `TRUNCATE ... CASCADE`; F-021 records the gap.
- **FAIL — deleted non-assertion test bodies contain four more load-bearing regressions.** The complete 242-line/184-hunk census classified 35 assertion deletions plus 207 non-assertion deletions: 228 lines were benign/exact/stronger and 14 were weakened. The 14 weakened lines represent five problems total: the cost assertion above plus four Slice-47 call-path defects. The critical-finding test no longer calls `ReleaseFindingRepository.accept` (`tests/test_release_findings.py:333-341`; branch `app/repositories/release_findings.py:68-80`; old call `52785b3^:tests/test_release_findings.py:236-246`). The finding and issue wrong-project/wrong-subject cases fail during risk-record setup rather than attempting the acceptance SQL (`tests/test_release_findings.py:531-573`; `tests/test_release_issues.py:548-589`; old direct calls `52785b3^:tests/test_release_findings.py:470-478`, `52785b3^:tests/test_release_issues.py:570-578`). The cross-tenant risk-record CREATE test can fail in subject lookup before INSERT/RLS (`tests/test_risk_acceptance.py:306-327`; `app/repositories/risk_acceptance.py:42-46,87-105`). F-021 records exact remediation.
- **PASS — workflow was not softened in its complete tracked history.** `git log --follow -p -- .github/workflows/ci.yml` has ten commits: creation `2277dd7` added 68 lines with Ruff, `make test`, and `make test-db`; `5c4b3e9` added scoped Pyright; the eight later `2 insertions / 2 deletions` diffs only renamed/expanded that Pyright path list through Slice 63. Ruff, `make test`, and `make test-db` remain at `.github/workflows/ci.yml:58-71`. The separate full-repository Pyright gap is F-017.
- **PASS — Slice-62’s three known weak tests remain hardened.** Current files equal merge `96faa86`; wrong overlay citations assert the exact wrong key set (`tests/test_cost_optimizer_checks.py:438-485`), RLS denies private reads and aggregate inserts (`tests/test_learning_db.py:96-121`), and the count-trigger mutation first proves its named rejection then disables only that trigger while neighboring guards accept the otherwise-valid graph (`tests/test_learning_guards.py:91-122`).

#### Deleted-line classification (Slices 43–63; assertion subset detailed)

```text
BASE=9586f212cad1d3347dfe55c1bb6bd846680a591f
HEAD=50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba
DELETED_ASSERTION_LIKE_LINES=35
EXACT_OR_STRONGER=20
BENIGN_CONTRACT_OR_RULESET_REBASELINE=14
WEAKENED=1
```

| Deleted IDs | Classification | Current replacement / provenance evidence |
|---|---|---|
| 01,02 | ruleset rebaseline | exact `slice54.v1` at `tests/test_api.py:663,675`; constant `app/release/production_autonomy.py:71` |
| 03 | exact/stronger | normalized gate-7 status/reason at `tests/test_api.py:678-683` |
| 04 | stronger | separate exact gate-5/6 reasons at `tests/test_api.py:698-705`; `33fb926`, #78 |
| 05,07,09,11,12,20,24,32,34,35 | ruleset rebaseline | current exact assertions at `tests/test_approval_channel.py:434`, `tests/test_classification.py:749`, `tests/test_deploy_evidence.py:887`, `tests/test_monitoring_evidence.py:1134`, `tests/test_pm_issues.py:591`, `tests/test_pr_evidence.py:1077`, `tests/test_production_autonomy.py:117`, `tests/test_secrets_verification.py:666`, `tests/test_semantic_contradictions.py:729`, `tests/test_skills.py:552` |
| 06 | stronger/corrected | all non-gate-9 values stable plus exact ledger delta at `tests/test_classification.py:736-750` |
| **08** | **weakened** | exact trigger assertion became trigger-or-FK at `tests/test_cost.py:472-485`; F-021 |
| 10 | stronger/corrected | all non-gate-9 values stable plus exact cost-event delta at `tests/test_generator.py:917-931` |
| 13 | stronger | both replacement audit rows asserted at `tests/test_policy.py:369-372` |
| 14 | contract rebaseline | exact two-event contract at `tests/test_policy.py:357-370`; Slice-63 contract `.planning/SLICE-63-PLAN.md:649-656` |
| 15 | exact replacement | renamed `new_autonomy_level` remains exactly A2 at `tests/test_policy.py:383-390` |
| 16 | security-contract rebaseline | count-only payload asserted at `tests/test_policy.py:390-393`; contract `.planning/SLICE-63-PLAN.md:649-664` |
| 17 | stronger | exact schemas for both audit events plus secret/hash exclusions at `tests/test_policy.py:370-393` |
| 18 | stronger | exact SQLSTATE `42501` and table attribution at `tests/test_policy.py:474-478` |
| 19 | stronger | exact runtime grant `SELECT`, explicit INSERT/UPDATE/DELETE negatives at `tests/test_policy.py:503-517`; `e6fbddc`, #116 |
| 21,22 | stronger/non-vacuous | empty sourceless-gate set, per-gate negatives, exact gate-13 reason at `tests/test_production_autonomy.py:85-91` |
| 23 | stronger collectively | exact aggregate reason at `tests/test_production_autonomy.py:94-99`; gate-12 ladder `tests/test_production_preapprovals.py:246-322` |
| 25,30 | exact/stronger | normalized no-provenance/no-binding branch at `tests/test_production_autonomy.py:128-139,623-628` |
| 26,27,29,31 | stronger ladder binding | exact next-rung failures and DB evidence booleans at `tests/test_production_autonomy.py:139,183-190,529-536,660-665`; `4f2012b`, #90 |
| 28 | stronger | distinct gate-5/6 binding failures at `tests/test_production_autonomy.py:193-216` |
| 33 | stronger/corrected | all non-gate-9 values stable plus exact ledger delta at `tests/test_semantic_contradictions.py:716-731` |

The ID groups contain exactly 20 + 14 + 1 = 35 deletions. ID 08 is load-bearing because plain `TRUNCATE cost_events` can stop at the Slice-51 FK; the named trigger and live `CASCADE` proof are at `migrations/versions/0008_cost_ledger.py:144-169` and §4.4.

### 4.4 Database invariant probes

The database worker used only `uaid_audit_db_concurrency_20260824_4f7c2a9d`, owned by `app`. Its create/migrate checkpoint and cleanup transcript were:

```text
DATABASE=uaid_audit_db_concurrency_20260824_4f7c2a9d OWNER=app
ALEMBIC_VERSION=0062
PUBLIC_BASE_TABLES=144
pre-drop: uaid_audit_db_concurrency_20260824_4f7c2a9d | app | t
DROP DATABASE
remaining_throwaway_databases | 0
independent post-cleanup SELECT count(*) FROM pg_database ... -> 0
```

#### Tenant isolation / RLS

The catalog and two-tenant probes consolidated to:

```text
tenant_id_tables | full_rls | exceptions | exception_tables
123              | 121      | 2          | audit_logs, tenant_api_keys

audit_logs, tenant_api_keys:
relrowsecurity=f | relforcerowsecurity=f | tenant_isolation policy absent
direct uaid_app table privileges absent

uaid_app + tenant-A GUC:
SELECT projects/project_runs -> tenant-A IDs only
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1
  cccccccc-cccc-cccc-cccc-ccccccccccc1
INSERT tenant-B project -> ERROR: new row violates row-level security policy for table "projects"
UPDATE tenant-B project -> UPDATE 0
DELETE tenant-B project -> DELETE 0
post-write count -> 0

uaid_app set_config('app.current_tenant', tenant-B, true) -> succeeded
subsequent SELECT -> bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2
```

A separate static all-table residual classification checked that the direct-`tenant_id` census did not silently omit tenant-owned child tables:

```text
SQLALCHEMY_MODELED=140
DIRECT_TENANT_ID=123
NO_TENANT_ID_MODELED=17
NO_TENANT_ID_NAMES=agent_blueprints,agent_versions,archetype_evals,audit_chain_verifications,catalog_assets,catalog_listings,catalog_vetting_check_results,catalog_vetting_records,connector_catalog_specs,connector_catalog_tool_scope,cross_project_aggregate_buckets,cross_project_aggregate_runs,organizations,reviewer_qa_fixture_cases,reviewer_qa_fixture_defects,reviewer_qa_fixture_suites,tenants
MIGRATION_ONLY_GLOBAL=3
MIGRATION_ONLY_NAMES=agent_provided_skills,agent_skill_capabilities,skills
ALEMBIC_VERSION=1
CLASSIFIED_PUBLIC_BASE_TABLES=144
```

The 21 rows outside the direct-`tenant_id` set are declared global/control-plane catalogs, aggregate/audit checkpoints, organization/tenant roots, or migration bookkeeping: blueprint/version contracts (`app/models/agent_blueprint.py:1-14`; `app/models/agent_version.py:1-15`), archetype/audit/aggregate contracts (`app/models/archetype_eval.py:1-7`; `app/models/audit_chain_verification.py:1`; `app/models/cross_project_aggregate.py:1-30`), global catalog migration (`migrations/versions/0060_ecosystem_catalog.py:7`), controlled reviewer fixtures (`app/models/reviewer_quality.py:1,63-141`), organization/tenant roots (`app/models/organization.py:1`; `app/models/tenant.py:1-2`), and the three explicitly global skill tables (`migrations/versions/0037_skill_matching.py:7-16,31`). The arithmetic `123 + 17 + 3 + 1 = 144` closes the live-table denominator; the separately declared pre-tenant `tenant_api_keys` is inside the 123-column set and is handled below.

- **PASS, narrowly:** the sampled cross-tenant read and write were blocked while the runtime GUC named the caller’s original tenant; the quoted probe supplies both outcomes.
- **FAIL for the tenant-owned denominator:** `tenant_api_keys` is explicitly a global pre-tenant authentication lookup, not a tenant-scoped store (`app/models/tenant_api_key.py:1-5`; `app/repositories/api_keys.py:6,34,73-76`). Excluding that declared global exception leaves 122 tenant-owned tables, of which 121 have the full triple; `audit_logs` is the remaining §17 mismatch. Neither exception grants direct table access to `uaid_app`, which narrows exposure but does not supply RLS for tenant audit data (F-019).
- **FAIL:** `uaid_app` could change the GUC to the victim tenant and then read that tenant’s row. The policy therefore isolates the selected GUC value, not a non-user-selectable authenticated tenant identity (F-003; tenancy helper `app/tenancy.py:24-56`).

Complete ordered catalog, where each row is `table|ENABLE|FORCE|tenant_isolation` (`tenant_api_keys` is the one declared global/pre-tenant row; the other 122 form the tenant-owned denominator):

```text
acceptance_criterion_authorship_records|t|t|t
acceptance_verification_results|t|t|t
acceptance_verification_runs|t|t|t
admin_actions|t|t|t
admin_policy_changes|t|t|t
admin_role_grants|t|t|t
agent_failure_events|t|t|t
agent_instances|t|t|t
agent_realization_reviewers|t|t|t
agent_realizations|t|t|t
agent_tool_allowlist|t|t|t
approval_events|t|t|t
approval_notifications|t|t|t
approvals|t|t|t
audit_logs|f|f|f
autonomy_policies|t|t|t
branch_protection_snapshots|t|t|t
budgets|t|t|t
control_loop_events|t|t|t
control_loop_runs|t|t|t
cost_events|t|t|t
cost_forecast_dimension_results|t|t|t
cost_forecast_input_lines|t|t|t
cost_forecast_ledger_event_refs|t|t|t
cost_forecast_policy_versions|t|t|t
cost_forecast_runs|t|t|t
cost_optimizer_citations|t|t|t
cost_optimizer_runs|t|t|t
deployment_target_snapshots|t|t|t
document_classifications|t|t|t
documents|t|t|t
emergency_control_authority_members|t|t|t
emergency_control_bindings|t|t|t
emergency_rollback_authorizations|t|t|t
emergency_stop_events|t|t|t
emergency_stop_run_effects|t|t|t
evidence_pack_export_files|t|t|t
evidence_pack_export_records|t|t|t
evidence_pack_generation_runs|t|t|t
evidence_pack_manifest_signatures|t|t|t
evidence_pack_section_results|t|t|t
evidence_pack_source_refs|t|t|t
evidence_packs|t|t|t
extraction_promotions|t|t|t
extraction_proposals|t|t|t
extraction_runs|t|t|t
generated_artifacts|t|t|t
go_live_decisions|t|t|t
go_live_evaluation_gate_results|t|t|t
go_live_evaluations|t|t|t
intake_artifacts|t|t|t
intake_categories|t|t|t
intake_findings_reports|t|t|t
intake_provenance|t|t|t
monitoring_status_snapshots|t|t|t
ops_hotfix_plans|t|t|t
ops_improvement_results|t|t|t
ops_incident_action_evaluations|t|t|t
ops_incident_action_results|t|t|t
ops_incident_events|t|t|t
ops_incident_tickets|t|t|t
ops_incidents|t|t|t
ops_observation_runs|t|t|t
ops_self_healing_results|t|t|t
ops_self_healing_runs|t|t|t
ops_signal_results|t|t|t
ops_stabilization_closure_attempts|t|t|t
ops_stabilization_criterion_results|t|t|t
ops_stabilization_windows|t|t|t
ops_support_handovers|t|t|t
pm_issue_mappings|t|t|t
production_approval_policy_approvers|t|t|t
production_approval_policy_versions|t|t|t
production_preapproval_attestations|t|t|t
production_preapproval_lifecycle_events|t|t|t
production_preapproval_requests|t|t|t
project_runs|t|t|t
projects|t|t|t
pull_request_evidence_snapshots|t|t|t
qualification_case_results|t|t|t
qualification_runs|t|t|t
readiness_reports|t|t|t
release_candidate_events|t|t|t
release_candidate_issue_bindings|t|t|t
release_candidates|t|t|t
release_finding_events|t|t|t
release_findings|t|t|t
release_issue_events|t|t|t
release_issues|t|t|t
release_verdict_issue_results|t|t|t
release_verdict_runs|t|t|t
release_verdicts|t|t|t
review_reports|t|t|t
reviewer_quality_case_results|t|t|t
reviewer_quality_defect_results|t|t|t
reviewer_quality_records|t|t|t
risk_acceptance_events|t|t|t
risk_acceptance_records|t|t|t
rollback_verification_phase_results|t|t|t
rollback_verification_runs|t|t|t
run_checkpoint_writes|t|t|t
run_checkpoints|t|t|t
run_steps|t|t|t
secret_reference_checks|t|t|t
security_scan_category_results|t|t|t
security_scan_runs|t|t|t
semantic_contradiction_reports|t|t|t
semantic_contradictions|t|t|t
shortcut_detector_category_results|t|t|t
shortcut_detector_reviewer_results|t|t|t
shortcut_detector_runs|t|t|t
skill_matches|t|t|t
squad_manifests|t|t|t
task_contract_artifact_links|t|t|t
task_contract_events|t|t|t
task_contract_reviewers|t|t|t
task_contracts|t|t|t
tenant_admin_events|t|t|t
tenant_api_keys|f|f|f
tenant_catalog_adoptions|t|t|t
test_oracle_runs|t|t|t
test_results|t|t|t
tool_calls|t|t|t
```

#### §2.6 mandatory approvals

The live runtime-role probe iterated the canonical action list at `app/policy/matrix.py:60-70`:

```text
ACTIONS_PROBED=10
FORGED_INSERTS_ACCEPTED=10
merge_to_protected                 | f | proceeded_by_policy
deploy_production                  | f | proceeded_by_policy
delete_resources                   | f | proceeded_by_policy
change_secrets                     | f | proceeded_by_policy
modify_billing_or_paid_resources   | f | proceeded_by_policy
send_external_communications       | f | proceeded_by_policy
access_sensitive_data              | f | proceeded_by_policy
accept_risk                        | f | proceeded_by_policy
override_failed_gate               | f | proceeded_by_policy
weaken_test_or_review_standards    | f | proceeded_by_policy
INSERT 0 10
ROLLBACK
```

This is **FAIL**, not a policy-engine PASS: every mandatory action accepted a direct same-tenant `uaid_app` row that the repository refuses (`app/repositories/approvals.py:65-110`), because the generic table/grants carry no equivalent action→explicitness/state/event constraint (`app/models/approval.py:34-65`; `migrations/versions/0005_approvals.py:138-149`). Finding F-002 records the boundary failure.

#### Append-only / immutability

The owner-role mutation probe reported:

```text
approval_events:      UPDATE=SUCCEEDED DELETE=SUCCEEDED TRUNCATE=SUCCEEDED
tool_calls:           UPDATE=SUCCEEDED DELETE=SUCCEEDED TRUNCATE=SUCCEEDED
agent_tool_allowlist: UPDATE=SUCCEEDED DELETE=SUCCEEDED TRUNCATE=SUCCEEDED

per table, exact owner-command tags: UPDATE 1 | DELETE 1 | TRUNCATE TABLE | ROLLBACK

catalog positive-control denominator:
tables with BEFORE UPDATE/DELETE plus BEFORE TRUNCATE blockers = 115
protected tables lacking a truncate blocker = 0

cost_events UPDATE/DELETE/TRUNCATE CASCADE ->
  ERROR: cost_events is immutable (no UPDATE/DELETE/TRUNCATE)
run_steps UPDATE/DELETE/TRUNCATE ->
  ERROR: run_steps is immutable (no UPDATE/DELETE/TRUNCATE)
```

That is **FAIL** for the declared append-only contracts at `app/models/approval_event.py:1-4`, `app/models/tool_call.py:1-3`, and `app/models/agent_tool_allowlist.py:1-5`; F-004 records the missing owner-level protection. **PASS, for the two named positive controls:** the trigger-generated messages prove that the intended immutability guard—not a neighboring FK—rejected each operation. `cost_events` used `TRUNCATE ... CASCADE` because plain `TRUNCATE` first hit a foreign key from `cost_forecast_ledger_event_refs`; this avoids treating a neighboring constraint as the named proof.

#### Literal-false go-live chain

- **PASS — persisted terminal truth remains hard-false.** Exact live output was:

  ```text
  uaid_app fabricated-evaluation finalizer -> ERROR: go-live evaluation unavailable
  uaid_app direct decision INSERT -> permission denied for table go_live_decisions
  owner complete decision INSERT with both truth fields true ->
    violates check constraint ck_go_live_decisions_hard_false
  ```

  The full DB suite also executed `tests/test_control_loop.py::test_direct_sql_incomplete_evaluation_and_hard_false_forgery_are_rejected` (`tests/test_control_loop.py:1546-1613`), with total output `1085 passed, 1277 deselected` (§4.2). The DB/model constraints are `app/models/go_live_decision.py:356-363` and `migrations/versions/0054_control_loop_decisions.py:714-731`.
- **PASS — the three tested canonical evaluator/control-loop outputs are literal false.** Three direct nodes returned `... [100%]`: `test_synthetic_all_thirteen_passes_remains_hard_false`, `test_control_loop_has_no_http_surface_or_production_action_call`, and `test_positive_outcome_is_non_executing_and_hard_false` in `tests/test_control_loop.py`; implementation `app/release/production_autonomy.py:112-125` and `app/intake/readiness.py:338-343`. This bounded PASS excludes the auxiliary surfaces in the next bullet/F-007.
- **FAIL — authorization-chain honesty before the terminal bit.** The runtime role can self-stamp the trusted/executed/authenticated source graphs consumed by gates 2–6/8/10–13, gates 7/9 inherit caller-controlled or reported sources, and a submitted synthetic thirteen-row report can become an official `decided_not_executed` chain (§2.6/F-005); auxiliary readiness/outcome surfaces can also carry caller-true values (F-007). Neither weakness made the final production bit true in any probe.

#### Emergency stop

**FAIL — the committed latch blocks an owned start and leaves the measured event/checkpoint-row/run-step/evaluation/decision counters unchanged, but the real owned resume evaluates cost before honoring the active latch.** The final probe used a fresh 0062 database, committed activation transaction `394939`, disposed that connection, then invoked `resume_control_loop_owned` and `start_control_loop_owned` through their own SERIALIZABLE tenant transactions. It ran as database owner `app`; this is a control-flow/persistence probe, not a fresh `uaid_app` privilege proof. Appendix A contains the complete runnable invocation.

Exact raw driver output was:

```text
S55_OWNED_PERSISTED_LATCH_PROBE={"activation": {"affected_run_count": 2, "state": "active"}, "activation_transaction_id": 394939, "after": {"activation_effects": 2, "activation_events": 1, "created_run_checkpoints": 0, "created_run_cycles": 0, "created_run_decisions": 0, "created_run_evaluations": 0, "created_run_events": 0, "created_run_status": "created", "created_run_steps": 0, "cycle_checkpoints": 3, "cycle_decisions": 0, "cycle_evaluations": 0, "cycle_events": 1, "cycle_run_steps": 2, "latest_latch_state": "active"}, "assertions": {"activation_committed_before_owned_calls": true, "activation_inventory_has_both_runs": true, "initial_start_paused_for_cost": true, "owned_calls_use_post_commit_connection": true, "owned_resume_no_checkpoint_progress": true, "owned_resume_no_decision": true, "owned_resume_no_event_progress": true, "owned_resume_no_persisted_evaluation": true, "owned_resume_no_run_step_progress": true, "owned_resume_returns_emergency_pause": true, "owned_resume_same_cycle": true, "owned_resume_still_calls_cost_evaluator": true, "owned_start_exact_refusal": true, "owned_start_leaves_created_run_untouched": true, "owned_start_no_work_persisted": true, "owned_start_rolls_back_pre_latch_cycle": true}, "audit_probe_passed": true, "before": {"created_run_cycles": 0, "created_run_status": "created", "cycle_checkpoints": 3, "cycle_decisions": 0, "cycle_evaluations": 0, "cycle_events": 1, "cycle_run_steps": 2, "outcome": "paused_cost_stop", "paused_run_status": "paused"}, "database": "uaid_audit_s55_owned_20260824_67c2e9a1", "database_role": "app_owner", "isolation": "serializable", "product_invariant_passed": false, "resume": {"cost_evaluator_calls_while_active": 1, "cycle": "4861f5b3-56d7-4643-a8eb-1934c3cea65d", "outcome": "paused_emergency_stop"}, "start_exception": "EmergencyStopActive:project emergency stop is active"}
```

The raw key `owned_calls_use_post_commit_connection` is misnamed: Appendix A shows that its executed predicate compares the later verification connection PID with the seeding PID, not either owned call. That predicate is not used as proof. Post-commit sequencing instead follows directly from the executed driver—activation commits before either owned call—and both owned wrappers delegate through a fresh SERIALIZABLE tenant transaction (`app/runtime/control_loop.py:567-621`; `app/repositories/go_live_decisions.py:147-161`).

The following is an annotated lifecycle summary assembled from the commands' unlabeled scalar results and standard command output; it is not a verbatim stdout/stderr transcript:

```text
pre-create database count: 0
CREATE DATABASE
alembic_version: 0062
public base tables: 144
pre-drop: uaid_audit_s55_owned_20260824_67c2e9a1|app|t
DROP DATABASE
post-drop database count: 0
```

- **PASS, bounded owned-start behavior:** after the committed active latch, `start_control_loop_owned` raised exactly `EmergencyStopActive:project emergency stop is active`; its owned transaction rolled back the cycle inserted before `RunRepository.transition`, leaving the created run and all cycle/work counters unchanged at zero. The call order is `start_cycle` first (`app/runtime/control_loop.py:511-517`) and `runs.mark_running` second (`:536-545`); the latter reaches `assert_project_not_stopped` through `app/repositories/runs.py:90-107`, with the raise at `app/repositories/emergency_controls.py:113-121`.
- **FAIL, end-to-end halt invariant:** `resume_control_loop_owned` returned `paused_emergency_stop`; the measured event, `run_checkpoints` row, run-step, evaluation, and decision counts did not change, but the load-bearing wrapper around the real cost evaluator recorded exactly one call while the committed latch was active. The probe did not snapshot `run_checkpoint_writes`, whose writer can update an existing row without changing the parent checkpoint count (`app/runtime/checkpointer.py:122-169`), so no exhaustive no-write claim is made. Production reads emergency at `app/runtime/control_loop.py:646-650`, calls `evaluate_cost_stop` unconditionally at `:651`, and only returns for the active latch at `:671-673`. This reverses the mandated emergency-before-cost boundary in `.planning/SLICE-55-PLAN.md:256-267,682-688`; F-008 records remediation.
- **FAIL, load-bearing test:** `run_guarded_stage` implements the intended emergency→cost order at `app/runtime/control_loop.py:72-83`, but repository-wide references are only that definition and its isolated tests (`tests/test_control_loop.py:287-354`). The real resume path does not call it, so `test_active_emergency_prevents_cost_and_stage` cannot fail when production resume order regresses.

### 4.5 Migration chain and determinism

Static chain evidence is a single linear history of 62 revisions:

```text
$ uv run alembic heads
0062 (head)
$ uv run alembic history
0061 -> 0062 (head), enterprise administration
0060 -> 0061, cost learning aggregates and optimizer
...
0001 -> 0002, rls tenant isolation
<base> -> 0001, control-plane spine
```

The recovery worker used a second uniquely named throwaway database, `uaid_audit_db_recovery_20260824_b7e91c3f`, solely because the first worker had already dropped its database before completing the required down/up probe. Exact lifecycle and catalog output:

```text
pre-create pg_database count: 0
CREATE DATABASE
upgrade head: exit 0
version_num=0062
public_base_tables=144

normalized schema-only pg_dump hash, pass 1:
195bd88d55584a370bb561c54b5ff21c0c3e5e192545c315ba545c6e1db78951
normalized schema-only pg_dump hash, pass 2:
195bd88d55584a370bb561c54b5ff21c0c3e5e192545c315ba545c6e1db78951

0062 catalog fingerprint:
0062|144|1967|1488|435|386|121|270|4|1|121|121
(revision|tables|columns|constraints|indexes|triggers|policies|functions|
 sequences|views|RLS-enabled|RLS-forced)

downgrade base: exit 0
base catalog: <base>|1|1|1|0
re-upgrade head: exit 0
post-round-trip dump hash:
195bd88d55584a370bb561c54b5ff21c0c3e5e192545c315ba545c6e1db78951
post-round-trip catalog:
0062|144|1967|1488|435|386|121|270|4|1|121|121
```

The fingerprint used schema-only `pg_dump`, retained ACLs, excluded owners/comments, and then removed PostgreSQL-16’s randomized `\restrict`/`\unrestrict` meta-command lines; no schema SQL was removed by normalization. **PASS — single-head 0001→0062 up/down/up determinism in the exercised PostgreSQL-16 environment:** both migration commands exited zero, both 0062 catalog tuples were identical, and all three normalized schema hashes were byte-identical. This does not prove data-bearing downgrade behavior or other PostgreSQL versions (§5).

### 4.6 Concurrency sweep

The exact AST scanner and ordered output are reproduced in Appendix B. It conservatively inventories syntactic writer endpoints; it is **not** a deduplicated semantic-leaf proof. In particular, it intentionally counts the base `TenantScopedRepository.add` endpoint (`app/tenancy.py:96-105`) separately from semantic callers such as `ProjectRepository.create` (`app/repositories/projects.py:12-14`), because both are callable row-creation boundaries within the user-requested every-writer sweep.

```text
DIRECT_WRITER_ENDPOINTS=119
PRIVATE_DIRECT=40
PUBLIC_DIRECT=79
MECHANISMS=orm_add:107,orm_add+pg_insert:1,pg_insert:9,raw_insert:2
INDIRECT_SQL_WRAPPER_ENDPOINTS=3
CANDIDATE_WRITER_ENDPOINT_TOTAL=122
```

The three indirect SQL-function wrapper endpoints added to the 119 syntactic endpoints are `app/audit.py:30-52` (`audit_append`), `app/repositories/admin.py:91-114` (`admin_write_autonomy_policy`), and `app/repositories/go_live_decisions.py:443-472` (`slice55_finalize_decision`). This yields a conservative candidate-endpoint denominator, not proof that every unique insert has been semantically deduplicated or that no indirect wrapper is missing.

Fourteen captured result records state that two independent `AsyncSession` transactions were used in the disposable 0062 database `uaid_audit_concurrency_20260824_73d92a1f`. Because the exact drivers were not retained, the statements below are auditor-observation records, not reproducible retained pair coverage:

```text
AD_HOC_OBSERVED_TWO_SESSION_RESULT_RECORDS=14
OBSERVED_CONFORMING_RECORDS=8
OBSERVED_23505_CONFLICT_RECORDS=6
RETAINED_AD_HOC_PAIR_DRIVER_PROGRAMS=0
SEPARATE_RETAINED_OD11_PAIR_ENDPOINTS=1
TOTAL_DISTINCT_AUDIT_TOUCHED_ENDPOINTS=15/122
RETAINED_REPRODUCIBLE_AUDIT_PAIR_COVERAGE=1/122
UNTOUCHED_BY_MAPPED_AUDIT_ACTIONS=107/122
```

**Captured first-write conflict signatures requiring retained rerun.** Every result record below reports one transaction committed, the other emitted an unhandled SQLAlchemy `IntegrityError` / PostgreSQL `23505`, and the final unique-key row count was one.

| Row-creating writer | Exact two-session result | Source / nearest sequential evidence |
|---|---|---|
| `BudgetRepository.upsert` | A=`23505 uq_budgets_tenant_id_project_id`; B=commit `7f0eb257-ad89-4a60-a5e3-e5cb880d2efe`; row_count=1. Barrier after both absent reads made the race load-bearing. | `app/repositories/cost.py:184-222`; `tests/test_cost.py:420-446` |
| `register_blueprint` | A=`23505 uq_agent_blueprints_key`; B=commit `9fed758f-a7ed-440e-b4d7-0fd5a83d151e`; row_count=1 | `app/agents/registry.py:102-121` |
| `register_version` | A=`23505 uq_agent_versions_blueprint_id_version_label`; B=commit `436111d9-ff2f-41fb-a8af-53b3a9693d0d`; row_count=1 | `app/agents/registry.py:125-176`; `tests/test_agents.py:170-193` |
| `CatalogAdoptionRepository.adopt` | A=commit `273ce0f8-9f72-4cbc-a8e6-bd35484bca11`; B=`23505 uq_tca_tenant_project_listing`; row_count=1 | `app/repositories/catalog_adoptions.py:31-62`; `tests/test_ecosystem_catalog_db.py:122-143` |
| `CostForecastRepository.record_policy_version` | A=`23505 uq_cfpv_project_digest`; B=commit `281b4400-9b3f-45ce-a154-8ddcbea293a4`; row_count=1 | `app/repositories/cost_forecasts.py:153-214`; `tests/test_cost_forecasts.py:449-479` |
| `ExtractionRepository.promote_proposal` | A=commit artifact `b1ffc70b-e11c-42f1-9451-ad43f9a7ca77`; B=`23505 uq_intake_artifacts_ref`; artifact/promotion row counts=1. Barrier after both `promotion_for()` absent reads made the race load-bearing. | `app/repositories/extraction.py:296-389`; `tests/test_extraction_promotion.py:264-303` |

**Captured conforming two-session records.** Each record reports exactly one semantic row and no unhandled exception:

```text
CostEventRepository.record:
  A=commit same id; B=commit same id 2073066a-ef82-419e-93ec-7d3f1219b342; row_count=1
DocumentRepository.ingest:
  A=commit same id; B=commit same id ecdd19f1-b7ae-4f76-a43b-36b3e6a5e049; row_count=1
GoLiveDecisionRepository.start_cycle:
  A=commit same id; B=commit same id 95614907-b7b9-4228-9e7a-c1b5d07cc26b; row_count=1
OpsIncidentRepository.open/try_insert_incident:
  A=committed_none; B=commit 846d4474-021b-4882-8eaa-14b59703e862; row_count=1
OpsSignalRepository.record_run/try_insert_run:
  A=committed_none; B=commit dec51968-9177-47fa-9a0b-c2ab2994c116; row_count=1
OpsHotfixRepository.evaluate/_try_insert_run:
  A=commit e07a4863-2a05-4164-a91c-3169d846672c; B=committed_none; row_count=1
OpsStabilizationRepository.assess/_try_insert_window:
  A=committed_none; B=commit 217261f9-a4fc-47d1-a994-f2728b80dbb9; row_count=1
ExportBundleRepository.generate/_try_insert_record:
  A=committed_none; B=commit 45e0f73c-b4ce-47d6-a474-6ed1fba50f6d; row_count=1
```

Implementations for those bounded pairs are `app/repositories/cost.py:47-114`, `app/repositories/documents.py:36-81`, `app/repositories/go_live_decisions.py:176-215`, `app/repositories/ops_incidents.py:119-148,227-281`, `app/repositories/ops_signals.py:154-224,240-290`, `app/repositories/ops_hotfix.py:203-243,252-295`, `app/repositories/ops_stabilization.py:86-158,291-347`, and `app/repositories/export_bundles.py:61-203,209-250`. Existing concurrency nodes for the last group include `tests/test_ops_signals_db.py:286-294`, `tests/test_ops_stabilization_db.py:288-307`, and `tests/test_export_bundle_db.py:340-357`.

Three invalid setup attempts were excluded rather than counted: wrong-case blueprint archetype produced two pre-write `InvalidArchetype` results; the first version harness passed a UUID instead of an ORM row and produced two pre-write `AttributeError` results; a parent-only ops-signal attempt produced two deferred child-count refusals and zero rows. Each affected scenario was corrected before the valid results above.

The table and block above are captured ad-hoc probe-result records. The exact 14 pair-driver programs were not retained after cleanup, so the report does not present them as self-contained reproduction recipes or count them as retained load-bearing coverage. Separately, the retained/executed OD-11 pair test in §4.7 exercises `admin_write_autonomy_policy`, one of Appendix B's three SQL-wrapper candidates (`app/repositories/admin.py:91-114`; test sessions/writer/mutation `tests/test_admin_policy_race_db.py:49-99,141-192`). Appendix B makes only the static candidate census independently reproducible.

**Result: audit INCOMPLETE / product unproved under F-020.** Fourteen unretained ad-hoc observations plus one distinct retained OD-11 endpoint touched `15/122` candidates; retained reproducible audit-specific pair coverage is `1/122`, and 107 candidates—including the other two SQL-function wrappers—were untouched by the mapped audit actions. Six conflict signatures require retained rerun. Compound winner-only child writers were not promoted to independent endpoint coverage. No product-wide concurrency PASS or definitive absence/presence-of-race conclusion is asserted from the unretained drivers.

### 4.7 Bounded recovery probes and final cleanup

The recovery DB used admin-role URLs for the three targeted pytest nodes because no runtime-role password was present in that shell. This proves their lock/trigger semantics, not a fresh `uaid_app` privilege boundary:

```text
collected 3 items
tests/test_control_loop.py::test_direct_sql_incomplete_evaluation_and_hard_false_forgery_are_rejected PASSED
tests/test_admin_policy_race_db.py::test_p_writer_concurrent_first_write PASSED
tests/test_emergency_controls.py::test_checkpointed_node_b_never_executes_after_activation PASSED
3 passed in 0.87s

post-tests schema hash:
195bd88d55584a370bb561c54b5ff21c0c3e5e192545c315ba545c6e1db78951
post-tests revision|tables: 0062|144
```

- **PASS — OD-11 only:** the retained real two-writer first-write node passed; its two independent sessions/writer path and load-bearing racy mutation are `tests/test_admin_policy_race_db.py:49-99,141-192`. It maps to the `admin_write_autonomy_policy` SQL-wrapper candidate (`app/repositories/admin.py:91-114`), giving the audit one retained reproducible endpoint and reducing candidates untouched by the mapped audit actions from 108 to 107; it does not close F-020.
- **PASS — older checkpoint guard only:** this selected node proves its demo checkpoint boundary. The later committed-latch owned-entry probe in §4.4 completed the missing dynamic audit action but found that real resume calls the cost evaluator before stopping; F-008 records that failure plus the remaining A5-conjunct, inner-boundary, and bounded-staging gaps.
- **PASS — hard-false node:** this independently repeats the direct-SQL constraint probe described in §4.4.

Cleanup and repository-state proof:

```text
DROP DATABASE
SELECT count(*) FROM pg_database
 WHERE datname='uaid_audit_db_recovery_20260824_b7e91c3f' -> 0

pre-drop: uaid_audit_s55_latch_20260824_c3f977cb | app | t
DROP DATABASE
SELECT count(*) FROM pg_database
 WHERE datname='uaid_audit_s55_latch_20260824_c3f977cb' -> 0

pre-drop: uaid_audit_s55_persist_20260824_8e4d21b7 | app | t
DROP DATABASE
post-drop count: 0

pre-drop: uaid_audit_s55_persist_20260824_f1a7c4d2 | app | t
DROP DATABASE
post-drop count: 0

pre-drop: uaid_audit_s55_owned_20260824_67c2e9a1 | app | t
DROP DATABASE
post-drop count: 0

DB=uaid_audit_concurrency_20260824_73d92a1f
PRECREATE_COUNT=0
CREATE DATABASE
MIGRATED_HEAD=0062
TABLE_COUNT=144
PRE_DROP_COUNT=1
PRE_DROP_ACTIVE_CONNECTIONS=0
DROP DATABASE
POST_DROP_COUNT=0
POST_DROP_ACTIVE_CONNECTIONS=0
DISPOSABLE_DB_COUNT=0

git status --short
?? .planning/FINAL-AUDIT-REPORT.md
?? UAID_OS/
```

Every named disposable audit database has verified post-drop count `0`; the final cluster-wide audit-name count was `DISPOSABLE_DB_COUNT=0`. The only repository write is this uncommitted report; no roadmap, source, migration, test, commit, or merge changed. The other status entry, `UAID_OS/`, is the pre-existing clean nested checkout proven in §4.1.

### 4.8 Fake-done observation/evaluation path census

The denominator is every callable `app/` path family whose public result observes, evaluates, verifies, assesses, classifies, detects, forecasts, recommends, qualifies, reviews, refreshes, computes readiness/coverage, or makes a persisted/UI/gate/action decision. Pure DTO/serialization, CRUD/history readers, migrations, and test fakes are excluded; service + repository + pure evaluator for one externally meaningful outcome are one group. Search vocabulary plus semantic equivalents was `observe|evaluate|verify|assess|refresh|result|coverage|readiness|classify|detect|recommend|qualify|review|forecast|collect|health|decision`. Result: **54/54 path groups inspected**; table parse output is `TRUTH_PATH_GROUPS=54 FINDING_LINKED=46 BOUNDED_NO_FINDING_REF=8`. “Bounded” does not mean the full specification is satisfied; every row cites a load-bearing PASS/failure test or an existing finding.

| # | Observation/evaluation path | Implementation / evidence read | Load-bearing PASS + failure evidence, or finding |
|---:|---|---|---|
| 1 | Health readiness | `app/health.py:25-43` | P `tests/test_health.py:18-35,62-72`; injected failure `:38-54`; no automated real-DB-outage test |
| 2 | Audit-chain/checkpoint verification | `app/audit.py:55-58`; `app/repositories/evidence_packs.py:79-112` | chain P/failure/tamper `tests/test_audit.py:113-141,224-246,287-300`; checkpoint P/forgery `tests/test_evidence_packs.py:498-502,688-724` |
| 3 | Muhasabah/Sanad result | `app/core/reasoning.py:21-40` | only sourced-fact P `tests/test_provenance.py:7-16`; **F-014** |
| 4 | Intake classification/review | `app/intake/classifier.py:83`; `app/repositories/classification.py:59-244` | parse P/failure `tests/test_classification.py:511-651`; free-text reviewer PASS `:651-673`: **F-013** |
| 5 | Extraction/evidence/promotion review | `app/intake/extraction.py:101-144`; `app/repositories/extraction.py:71-241,296-335` | P/hallucination/budget/injection `tests/test_extraction.py:227-386`; promotion recheck `tests/test_extraction_promotion.py:158-230`; caller-label review **F-013** |
| 6 | Generated-artifact review | `app/intake/generator.py:9-12,87,114-155`; `app/repositories/generator.py:67-267` | P/failure `tests/test_generator.py:648-750`; arbitrary-label review `:751-822`: **F-013** |
| 7 | Structural findings | `app/intake/findings.py:57-167`; `app/repositories/findings.py:28-60` | P/failure `tests/test_findings.py:43-176,253-318` |
| 8 | Semantic contradictions | `app/repositories/semantic_contradictions.py:62-184` | P/failure `tests/test_semantic_contradictions.py:562-674,735-815` |
| 9 | Readiness | `app/intake/readiness.py:17-23,215-353` | tests encode presence-only P/failure `tests/test_readiness.py:453-503,754-824`; **F-001/F-007** |
| 10 | Policy/autonomy decision | `app/policy/engine.py:22-37`; repository policy decision `app/repositories/autonomy_policies.py:47-96` | engine outcomes `tests/test_policy.py:37-145,197-344`; DB workflow bypass **F-002** |
| 11 | Approval gate | `app/approvals/states.py:49-89`; `app/repositories/approvals.py:200-234` | structural direct-write bypass **F-002** |
| 12 | Cost stop | `app/cost.py:113-126`; `app/repositories/cost.py:228-250` | P/failure `tests/test_cost.py:41-83,382-449` |
| 13 | Agent skill matching/ranking | `app/agents/skills.py:165-192,210-258` | P assignment `tests/test_skills.py:165-183`; self-review/missing-reviewer failures `:185-241`; bounded ranking, not qualification execution |
| 14 | Agent qualification | `app/agents/qualification.py:1-10`; `app/repositories/qualification.py:74-210` | caller-recorded, no agent execution: **F-013** |
| 15 | Agent failure/replacement assessment | `app/agents/failure_policy.py:1-10,118-137`; `app/repositories/agent_failures.py:37-113` | prescriptive/non-actuating: **F-013** |
| 16 | Task review/done workflow | `app/review/workflow.py:1-12,80-112,145-167`; `app/repositories/review_reports.py:32-108` | caller-supplied report, no review execution: **F-013** |
| 17 | Reviewer QA | `app/verify/reviewer_qa.py:544-651`; `app/repositories/reviewer_quality.py:106-290` | P `tests/test_reviewer_quality.py:617-668`; infrastructure/history failure `:679-706,769-842`; raw trusted-tier dependency/learning input **F-005/F-022** |
| 18 | Acceptance/authorship gates | `app/verify/acceptance.py:129-156`; repository projection `app/repositories/acceptance_verification.py:309-348` | runtime-writeable support graph plus current/reviewer fields inferred from non-null IDs: **F-005/F-006** |
| 19 | Specified/reference/judgment oracles | `app/verify/oracles.py:435-587`; `app/verify/judgment.py:151-243`; `app/repositories/test_oracles.py:100-299,563-746` | P/failure `tests/test_test_oracles.py:57-276,492-577,980-1060,1178-1224`; writer-auth/conjunct gaps **F-005/F-008** |
| 20 | Security scan | `app/verify/security_scan.py:24-37,259-384,422-445`; `app/repositories/security_scans.py:37-170` | artifact P/failure `tests/test_security_scans.py:61-211,611-687`; writer-auth/composed gaps **F-005/F-008** |
| 21 | Shortcut detection + LLM review | `app/verify/shortcut_detector.py:170-334`; `app/verify/shortcut_review.py:181-228`; `app/repositories/shortcut_detectors.py:64-523` | P/failure `tests/test_shortcut_detector.py:30-206,237-275,777-933`; writer-auth/composed gaps **F-005/F-008** |
| 22 | Admin RBAC check and persisted policy mutation consumer | pure evaluator `app/admin/rbac.py:101-138`; consuming service `app/admin/policy_admin.py:46-137` | pure P/failure `tests/test_admin_rbac.py:119-160`; real refused/allowed/store path `tests/test_admin_checks.py:415-468` |
| 23 | CI/branch-protection observation | `app/release/ci_evidence_service.py:50-103`; `app/release/ci_evidence.py:126-141` | P/failure `tests/test_ci_evidence.py:643-778,839-878`; trusted status is runtime-self-stampable **F-005** |
| 24 | PR observation | `app/release/pr_evidence_service.py:54-113` | P/failure `tests/test_pr_evidence.py:679-730,830-930,981-1056,1188-1214`; verified merge/review evidence is not writer-authenticated **F-005** |
| 25 | Production-target observation | `app/release/deploy_evidence_service.py:59-163`; mapping `app/release/deploy_evidence.py:70-88` | P/failure `tests/test_deploy_evidence.py:140-167,474-496,656-767,794-864,923-988`; trusted row is runtime-writeable and no deployment actuator exists **F-005/F-009** |
| 26 | Staging-target observation | same implementation/evidence read as #25 | same P/failure tests; trusted row is runtime-writeable and the result is explicitly observation-only/not proof of deployment (`roadmap:543-552`): **F-005/F-009** |
| 27 | Monitoring observation | `app/release/monitoring_evidence_service.py:55-103`; `app/release/monitoring_evidence.py:130-172,178-259` | P/unreadable/failure `tests/test_monitoring_evidence.py:151-188,596-617,938-1048,1098-1175`; trusted row is runtime-self-stampable **F-005** |
| 28 | Secret-reference verification | `app/release/secrets_verification_service.py:55-113`; `app/release/secrets_verification.py:51-111` | P/failure `tests/test_secrets_verification.py:89-142,477-510,531-635,673-742`; trusted resolution is runtime-self-stampable **F-005** |
| 29 | PM synchronization observation | `app/release/pm_sync_service.py:59-116` | P/failure/no-write `tests/test_pm_issues.py:485-567,595-644`; live adapter gap F-015 |
| 30 | Evidence pack + re-audit | `app/repositories/evidence_packs.py:79-112,828-915` | P/reaudit/failure `tests/test_evidence_packs.py:495-687,806-934`; canonical re-audit does not authenticate upstream self-stamped sources **F-005** |
| 31 | Cost forecast | `app/cost_forecast.py:356-499`; `app/repositories/cost_forecasts.py:285-423,497-737` | P/failure/source-forge `tests/test_cost_forecasts.py:145-241,538-618,682-751`; deterministic calculation over reported inputs plus gate-conjunct gaps **F-005/F-008** |
| 32 | Rollback-drill verification | `app/release/rollback.py:173-330`; `app/repositories/rollback_verifications.py:138-468` | P/failure/latest-failure `tests/test_rollback_verifications.py:80-167,678-791,970-1012`; writer-auth/composed gaps **F-005/F-008** |
| 33 | Release verdict | `app/release/release_manager.py:172-209`; `app/repositories/release_verdicts.py:85-397` | P/blocker `tests/test_release_verdicts.py:503-604,620-694`; real limitation authority is hard-false and upstream sources are caller-controlled (`app/repositories/release_verdicts.py:218-243,336-369`): **F-002/F-005** |
| 34 | Risk-acceptance authority | downstream authority wiring in #33; records `app/repositories/risk_acceptance.py:42-85` | authorized limitation outcome unreachable while unapproved active record is writable, and the named cross-tenant CREATE test can stop before INSERT/RLS: **F-002/F-021** |
| 35 | Production preapproval | `app/repositories/production_preapprovals.py:510-673` | P/failure `tests/test_production_preapprovals.py:536-581,606-720`; authentication-writer/conjunct gaps **F-005/F-008** |
| 36 | Emergency-control evaluation | `app/release/production_autonomy.py:1295-1392`; repositories `app/repositories/emergency_controls.py:452-768` | P/failure/latch `tests/test_emergency_controls.py:218-243,395-629`; owned start rollback is bounded PASS, but committed-latch owned resume evaluates cost first and authority/full persisted gate-PASS gaps remain **F-005/F-008** (§4.4) |
| 37 | A5 composition | `app/release/production_autonomy.py:103-1410`; `app/repositories/production_autonomy.py:120-331` | supplied-gate binding and composite gaps: **F-005/F-008** |
| 38 | Go-live evaluation/finalize | `app/release/go_live_decision.py:174-270`; `app/repositories/go_live_decisions.py:337-425,444-513` | caller/composed report and auxiliary projection defects: **F-005/F-007** |
| 39 | Control-loop stage evaluation/latches | `app/runtime/control_loop.py:267-436,501-621,633-741`; owned transaction helper `app/repositories/go_live_decisions.py:147-161` | committed-latch owned start rolls back, but owned resume calls cost before its emergency return; isolated `run_guarded_stage` tests do not exercise production resume (§4.4). Self-stamped upstream evidence, per-inner-boundary mutation gaps, and non-actuation remain **F-005/F-008/F-009**; bounded staging has only negative tests `tests/test_control_loop_owner_retry.py:376-452` |
| 40 | Export-bundle verification | `app/repositories/export_bundle_reads.py:98-169`; `app/release/export_bundle_service.py:125-151` | hash/signature/binding/redaction P/failure `tests/test_export_bundle.py:76-206`; product scope **F-016** |
| 41 | Tool permission/broker result | `app/tools/broker.py:42-230` | tests terminate at `allowed_unverified_identity` (`tests/test_tools.py:289-393`); no adapter execution **F-009** |
| 42 | Ops signal collection/assessment | `app/ops/signals.py:23-98,449-497`; `app/ops/assessment.py:29-219`; `app/ops/collect.py:70-193` | P/failure/unknown `tests/test_ops_signals.py:95-234,341-395`; observed-class limits **F-010** |
| 43 | Incident/action + handover observation | `app/ops/incidents.py:40-67,313-390`; `app/repositories/ops_incidents.py:119-393` | P/failure `tests/test_ops_incidents_db.py:74-220`; caller-recorded/non-actuating and unverified handover **F-010** |
| 44 | Hotfix evaluation | `app/ops/hotfix.py:188-240,316-408`; `app/repositories/ops_hotfix.py:76-242` | P/failure `tests/test_ops_hotfix.py:92-204`; DB `tests/test_ops_hotfix_db.py:32-129`; no actuator **F-010** |
| 45 | Stabilization criteria | `app/ops/stabilization.py:22-77`; `app/ops/stabilization_criteria.py:30-231` | P/failure `tests/test_ops_stabilization.py:79-237,331-379`; DB `tests/test_ops_stabilization_db.py:45-133,257-367`; unverified sole-PASS/closure gaps **F-010** |
| 46 | Connector-contract evaluation | `app/ecosystem/contract_test.py:62-137` | structural P/failure `tests/test_ecosystem_catalog.py:34-94`; no live provider/permission proof **F-011** |
| 47 | Catalog reviewer/attestor outcome | `app/ecosystem/catalog_populate.py:149-270`; `app/repositories/catalog_admin.py:242-272` | tests accept manufactured PASS (`tests/test_ecosystem_catalog_populate_db.py:265-319`; `tests/test_ecosystem_catalog_populate_review_db.py:90-120`): **F-011** |
| 48 | Cross-project learning publication | `app/ecosystem/learning_publish.py:24-33`; queries `app/ecosystem/learning_sql.py:1-191` | aggregate P/failure `tests/test_learning_db.py:40-190`; denial-frequency naming, caller-recorded cost aggregates, and erased source tiers **F-009/F-022** |
| 49 | Cost optimization assessment/recommendation | `app/ecosystem/cost_optimizer.py:132-258`; `app/repositories/cost_optimizer.py:32-200` | P/failure `tests/test_cost_optimizer.py:61-225`; zero-result DB hold `tests/test_cost_optimizer_db.py:283-315`; recommendation-only but consumes mislabeled reliability and source-tier-erased cost aggregates **F-009/F-015/F-022** |
| 50 | Release finding/issue disposition | `app/repositories/release_findings.py:49-66,114-128`; `app/repositories/release_issues.py:173-181,230-248`; downstream exclusion `app/release/release_manager.py:172-208` | arbitrary caller labels close blockers (`tests/test_release_findings.py:293-315`; `tests/test_release_issues.py:256-273`), while critical/wrong-project/wrong-subject acceptance tests no longer reach the named branch/guard: **F-002/F-021** |
| 51 | Approval notification delivery | `app/approvals/channels/adapter.py:40-47`; persistence `app/approvals/channels/service.py:35-83`; preapproval consumption `app/repositories/production_preapprovals.py:615-666` | no-I/O adapter always returns gate-bearing `delivered`; canned-success/gate tests `tests/test_approval_channel.py:265-270,290-317`, `tests/test_production_preapprovals.py:535-567`: **F-008/F-015** |
| 52 | Intake document scan/quarantine | `app/intake/sandbox.py:57-60`; persisted decision `app/repositories/documents.py:36-81` | accepted/quarantined P/failure `tests/test_intake.py:153-204` |
| 53 | Legacy runtime approval/cost/emergency decisions | emergency boundary `app/runtime/engine.py:76-80`; guarded entry points `:118-145,180-250,315-363,386-423` | approval/retry/cost P/failure `tests/test_runtime_8b.py:203-466`; checkpoint/all-eight-entry tests `tests/test_emergency_controls.py:513-601`; §4.4 proves bounded owned-start rollback but finds S55 resume-order failure, without removing generic approval/authority-writer or inner-boundary gaps **F-002/F-005/F-008** |
| 54 | Request authentication / actor provenance | bearer resolution `app/api/auth.py:23-54`; key lookup `app/repositories/api_keys.py:72-90`; actor validation/stamping `app/identity.py:43-62` | actor-tier P/fallback `tests/test_identity.py:60-69`; valid/unknown/revoked-key P/failure `:184-212`; API-key custody becomes the gate-bearing `request_authenticated` label, while downstream trusted-tier graph writers remain forgeable **F-005** |

Every truthfulness defect found within this denominator is linked from its row to the numbered ledger; the census does not imply that finding-free bounded rows satisfy the full specification. Row 26 is not a deployment claim: the binding Slice-55 contract deliberately says `staging_evidence_observed_not_deployed` (`.planning/SLICE-55-PLAN.md:122,366`); real deployment remains absent under F-009/F-015.

### 4.9 Ledger and close-out consistency

Live, read-only GitHub metadata probes returned:

```text
REFERENCED_UNIQUE_PRS=68 LIVE_MERGED_WITH_COMMIT=68 BAD=0
BAD_PRS=<none>
SHA_PR_PAIRS=68 LIVE_PR_CONTAINS_OR_MERGES_SHA=68 BAD=0 EARLY_MULTI_COMMIT_PAIRS=13
HANDOFF_CLOSEOUT_PR_SHA_CLAIMS=12 LIVE_MERGED_SHA_MATCH=12 BAD=0
HANDOFF_CLAIMED_PRS=102,103,104,105,106,107,108,110,111,113,114,116
PR106_TITLE=feat(ops): record hotfix-intent evaluation without executing self-healing
PR108_TITLE=Slice 59: stabilization-window assessment (non-closing; does not exit §25.4 or close §26.6)
PR110_TITLE=Slice 60 — signed offline auditor bundle (§28.1 export hardening; closes no spec section)
PR111_TITLE=Slice 61a: empty ecosystem catalog listing mechanism (closes no spec section)
PR113_TITLE=Slice 61b: populate declared catalog (does not close Slice 61 exit)
PR114_TITLE=Slice 62: tenant-safe aggregates and decision-only cost optimizer (does not close Slice 61 exit)
PR116_TITLE=Slice 63: enterprise administration with DB-enforced RBAC (does not close Slice 61 exit)
```

- **PASS — live merged PR, commit membership, and bounded close-out lineage.** Every Slice-1–63 row in §2.3 carries a main-reachable implementation SHA and PR number; the local reachability probe returned `TOTAL=68 BAD=0 MAIN=50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba`, and the live GitHub probes above found all 68 referenced PRs merged with a merge commit and all 68 implementation SHAs either inside the early multi-commit PR or equal to the later squash merge commit. First-parent history encodes PRs #1–#13 in merge subjects (for example, `e611214 Merge pull request #1` through `e5cac0a Merge pull request #13`); later squash implementation subjects carry `(#N)` annotations. All 12 PR/SHA claims in the Slice-56–63 close-out entries (`.planning/HANDOFF.json:63-75`) match live merge metadata; the seven bounded/non-closing implementation titles quoted above agree with the corresponding close-out descriptions. The validation block names `e6fbddc`, `#116`, `0062`, `1277/1085`, and the recorded CI run (`.planning/HANDOFF.json:156-162`). This proves merge and code membership plus the title-level close-out description; it does not prove reviewer identity or independently re-adjudicate every PR discussion comment.
- **FAIL — semantic closure ledgers do not agree.** `HANDOFF.json` declares no remaining tasks/blockers (`.planning/HANDOFF.json:77-79`) while recording open S58/S59/S60/S61 residuals (`:104-108,164-168`); the roadmap graph/M6 says the go-live path and operating system become reachable/functional (`roadmap:723-736,753-754`) although the literal-false and non-closing implementations contradict that; `README.md:660-688` and `CLAUDE.md:1444-1476` retain early-slice A5 status. F-018 records the exact reconciliation scope. The authoritative merge facts agree; capability-completion narratives do not.

## 5. What this audit does NOT prove

- It does **not** prove that UAID OS can build, merge, deploy, roll back, or hotfix a real system. The broker states that it performs no real execution (`app/tools/broker.py:1-16,225-230`), the bounded control loop states that it executes no production action (`app/runtime/control_loop.py:1-6`), and the Slice-58 implementation records intent only (`app/ops/hotfix.py:1-4`; `tests/test_ops_hotfix.py:176-190,279-286`).
- It does **not** prove live-provider behavior, production credentials, GitHub branch settings, human signer identity, cloud permissions, or production monitoring. The evidence exercised local code, tracked Git history, and disposable PostgreSQL; the roadmap itself leaves real-provider testing and permission scoping open at `roadmap:845-847`, and request authentication is not human-signature proof (`app/identity.py:30-62`; `tests/test_identity.py:297-307,335-345`).
- It does **not** turn green tests into proof of semantic completeness. The clean suites passed 1,277 non-DB and 1,085 DB nodes (§4.2), while empty/arbitrary intake declarations still satisfy presence checks (`app/intake/readiness.py:17-23,300-309`; `app/intake/categories.py:138-164`; `tests/test_intake_categories.py:91-101`).
- It does **not** establish compliance certification or the full external-assurance contract. The implemented bundle is offline-only and lacks enforced expiry, OSCAL, scoped links, and temporary auditor accounts (`app/release/export_bundle.py:24-38,82-93`), against specification requirements at `spec:1492-1546,2832-2914`.
- It does **not** prove that environment-held signing keys provide PKI/HSM custody or a human release-authority signature. The implemented key source and bundle limitations are at `app/release/export_bundle.py:24-38,82-93`; the normative signature requirement is `spec:1492-1504,1538-1546`.
- It does **not** prove behavior on PostgreSQL versions, operating systems, provider APIs, or deployment topologies outside the exercised environment. The exact local evidence is PostgreSQL 16 plus the suite/probe transcripts in §§4.2–4.6; no external-provider execution exists (`app/tools/broker.py:13-16`).
- It does **not** prove data-preserving downgrade behavior. The migration PASS in §4.5 is an empty-database schema/ACL round-trip: hash `195bd88d…78951` before and after, with `downgrade base: exit 0`; no production-like rows were carried down and back up.
- It does **not** prove product-wide two-writer safety. The conservative candidate-endpoint denominator is 122, not a deduplicated semantic-leaf proof. Fourteen ad-hoc result records were captured—six conflict signatures and eight conforming outcomes—but exact drivers were not retained. The separate retained OD-11 test maps to one additional candidate, so the mapped audit actions touched 15/122 distinct endpoints, retained reproducible audit-specific pair coverage is `1/122`, and 107 candidates were untouched (§§4.6–4.7/F-020). The OD-11 run is not a rerun of the six recorded signatures.
- It does **not** prove the emergency-stop invariant end to end. The committed-latch owner-role probe established bounded owned-start rollback and unchanged measured event/parent-checkpoint/run-step/evaluation/decision counts, but did not measure `run_checkpoint_writes` and found one cost-evaluator call before owned resume returned `paused_emergency_stop` (§4.4/Appendix A); the source-name assertion and outer-entry behavioral test can also mask removal of an individual inner boundary (`tests/test_emergency_controls.py:254-276,513-601`; F-008).
- It does **not** dynamically read/write every tenant table as two tenants. The catalog exhaustively enumerated 122 tenant-owned tables and their three RLS bits (§4.4), but the live cross-tenant sample was `projects`/`project_runs`; the GUC-impersonation counterexample and `audit_logs` catalog failure remain F-003/F-019.
- It does **not** make an absence-of-finding claim for paths outside tracked `main` at `50bc0558df37fbc438ac5349c1b0b3f4ec06e5ba`. The baseline and clean-checkout SHA evidence is quoted in §4.1; the report file itself is the sole authorized audit artifact.
- It does **not** authorize remediation, deployment, or a new slice. The governing handoff’s `next_action` is `STOP. ... No Slice 64. No new work.` (`.planning/HANDOFF.json:170-171` in the inspected file); the numbers in §3 are proposals for owner review only.


## Appendix A — Exact committed-latch probe invocation

This is the complete command transcript for the final emergency-stop probe summarized in §4.4. It is retained verbatim for reproducibility. The URLs deliberately name only the disposable audit database and use the local owner role `app`; the database was dropped immediately afterward.

### A.1 Create and migrate

```bash
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d postgres -v ON_ERROR_STOP=1 -Atqc "SELECT count(*) FROM pg_database WHERE datname='uaid_audit_s55_owned_20260824_67c2e9a1'"
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE "uaid_audit_s55_owned_20260824_67c2e9a1" OWNER app'
ALEMBIC_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1' .venv/bin/alembic upgrade head
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d uaid_audit_s55_owned_20260824_67c2e9a1 -v ON_ERROR_STOP=1 -Atqc "SELECT version_num FROM alembic_version; SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
```

### A.2 Commit activation, invoke owned resume/start, and verify

```bash
DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1' ADMIN_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1' TEST_ADMIN_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1' ALEMBIC_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1' .venv/bin/python - <<'PY'
import asyncio
import json
import uuid
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

URL = "postgresql+asyncpg://app:app@localhost:5432/uaid_audit_s55_owned_20260824_67c2e9a1"

async def scalar(session, sql, **params):
    return await session.scalar(text(sql), params)

async def bind_tenant(session, tenant_id):
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )

async def main():
    from app.db import dispose_engine
    from app.release.emergency_control_service import EmergencyControlService
    from app.repositories.emergency_controls import EmergencyStopActive
    from app.runtime.control_loop import (
        ControlLoopCapabilities,
        resume_control_loop_owned,
        start_control_loop,
        start_control_loop_owned,
    )
    from tests.test_control_loop import _seed_decision_ready

    seed_engine = create_async_engine(URL, isolation_level="SERIALIZABLE")
    async with seed_engine.connect() as conn:
        transaction = await conn.begin()
        seed_pid = await conn.scalar(text("SELECT pg_backend_pid()"))
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            seeded = await _seed_decision_ready(session)
            await bind_tenant(session, seeded["tenant"])
            created_run = await scalar(
                session,
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id",
                tenant=seeded["tenant"], project=seeded["project"],
            )
            initial = await start_control_loop(
                session,
                seeded["requester_context"],
                project_id=seeded["project"],
                project_run_id=seeded["project_run"],
                idempotency_key="audit-s55-owned-initial-pause",
            )
            cycle_id = uuid.UUID(str(initial["control_loop_run_id"]))
            before = {
                "outcome": initial.get("outcome_code"),
                "paused_run_status": await scalar(session, "SELECT status FROM project_runs WHERE id=:run", run=seeded["project_run"]),
                "created_run_status": await scalar(session, "SELECT status FROM project_runs WHERE id=:run", run=created_run),
                "cycle_events": await scalar(session, "SELECT count(*) FROM control_loop_events WHERE control_loop_run_id=:cycle", cycle=cycle_id),
                "cycle_checkpoints": await scalar(session, "SELECT count(*) FROM run_checkpoints WHERE run_id=:run AND checkpoint_ns=:ns", run=seeded["project_run"], ns=str(cycle_id)),
                "cycle_run_steps": await scalar(session, "SELECT count(*) FROM run_steps WHERE run_id=:run", run=seeded["project_run"]),
                "cycle_evaluations": await scalar(session, "SELECT count(*) FROM go_live_evaluations WHERE control_loop_run_id=:cycle", cycle=cycle_id),
                "cycle_decisions": await scalar(session, "SELECT count(*) FROM go_live_decisions WHERE control_loop_run_id=:cycle", cycle=cycle_id),
                "created_run_cycles": await scalar(session, "SELECT count(*) FROM control_loop_runs WHERE project_run_id=:run", run=created_run),
            }
            activation = await EmergencyControlService(
                session, seeded["approver_context"]
            ).activate(
                project_id=seeded["project"],
                idempotency_key="audit-s55-owned-activate",
            )
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            activation_txid = await scalar(session, "SELECT txid_current()")
            await transaction.commit()
        except BaseException:
            if transaction.is_active:
                await transaction.rollback()
            raise
        finally:
            await session.close()
    await seed_engine.dispose()

    original_cost = ControlLoopCapabilities.evaluate_cost_stop
    cost_evaluator_calls = 0

    async def observed_cost(self, *, as_of_date):
        nonlocal cost_evaluator_calls
        cost_evaluator_calls += 1
        return await original_cost(self, as_of_date=as_of_date)

    with patch.object(ControlLoopCapabilities, "evaluate_cost_stop", observed_cost):
        resumed = await resume_control_loop_owned(
            seeded["requester_context"],
            project_id=seeded["project"],
            project_run_id=seeded["project_run"],
            control_loop_run_id=cycle_id,
        )

    start_exception = None
    try:
        await start_control_loop_owned(
            seeded["requester_context"],
            project_id=seeded["project"],
            project_run_id=created_run,
            idempotency_key="audit-s55-owned-active-start",
        )
    except EmergencyStopActive as exc:
        start_exception = f"{type(exc).__name__}:{exc}"
    await dispose_engine()

    verify_engine = create_async_engine(URL, isolation_level="SERIALIZABLE")
    async with verify_engine.connect() as conn:
        verify_pid = await conn.scalar(text("SELECT pg_backend_pid()"))
        after = {
            "latest_latch_state": await conn.scalar(text(
                "SELECT state_after FROM emergency_stop_events "
                "WHERE tenant_id=:tenant AND project_id=:project "
                "ORDER BY created_at DESC,id DESC LIMIT 1"
            ), {"tenant": seeded["tenant"], "project": seeded["project"]}),
            "activation_events": await conn.scalar(text(
                "SELECT count(*) FROM emergency_stop_events "
                "WHERE tenant_id=:tenant AND project_id=:project "
                "AND event_type='activated' AND state_after='active'"
            ), {"tenant": seeded["tenant"], "project": seeded["project"]}),
            "activation_effects": await conn.scalar(text(
                "SELECT count(*) FROM emergency_stop_run_effects "
                "WHERE tenant_id=:tenant AND project_id=:project"
            ), {"tenant": seeded["tenant"], "project": seeded["project"]}),
            "cycle_events": await conn.scalar(text("SELECT count(*) FROM control_loop_events WHERE control_loop_run_id=:cycle"), {"cycle": cycle_id}),
            "cycle_checkpoints": await conn.scalar(text("SELECT count(*) FROM run_checkpoints WHERE run_id=:run AND checkpoint_ns=:ns"), {"run": seeded["project_run"], "ns": str(cycle_id)}),
            "cycle_run_steps": await conn.scalar(text("SELECT count(*) FROM run_steps WHERE run_id=:run"), {"run": seeded["project_run"]}),
            "cycle_evaluations": await conn.scalar(text("SELECT count(*) FROM go_live_evaluations WHERE control_loop_run_id=:cycle"), {"cycle": cycle_id}),
            "cycle_decisions": await conn.scalar(text("SELECT count(*) FROM go_live_decisions WHERE control_loop_run_id=:cycle"), {"cycle": cycle_id}),
            "created_run_status": await conn.scalar(text("SELECT status FROM project_runs WHERE id=:run"), {"run": created_run}),
            "created_run_cycles": await conn.scalar(text("SELECT count(*) FROM control_loop_runs WHERE project_run_id=:run"), {"run": created_run}),
            "created_run_events": await conn.scalar(text("SELECT count(*) FROM control_loop_events e JOIN control_loop_runs c ON c.id=e.control_loop_run_id WHERE c.project_run_id=:run"), {"run": created_run}),
            "created_run_checkpoints": await conn.scalar(text("SELECT count(*) FROM run_checkpoints WHERE run_id=:run"), {"run": created_run}),
            "created_run_evaluations": await conn.scalar(text("SELECT count(*) FROM go_live_evaluations e JOIN control_loop_runs c ON c.id=e.control_loop_run_id WHERE c.project_run_id=:run"), {"run": created_run}),
            "created_run_decisions": await conn.scalar(text("SELECT count(*) FROM go_live_decisions d JOIN control_loop_runs c ON c.id=d.control_loop_run_id WHERE c.project_run_id=:run"), {"run": created_run}),
            "created_run_steps": await conn.scalar(text("SELECT count(*) FROM run_steps WHERE run_id=:run"), {"run": created_run}),
        }
    await verify_engine.dispose()

    assertions = {
        "activation_committed_before_owned_calls": after["latest_latch_state"] == "active" and after["activation_events"] == 1,
        "activation_inventory_has_both_runs": activation.state == "active" and activation.affected_run_count == after["activation_effects"] == 2,
        "owned_calls_use_post_commit_connection": verify_pid != seed_pid,
        "initial_start_paused_for_cost": before["outcome"] == "paused_cost_stop" and before["paused_run_status"] == "paused",
        "owned_resume_returns_emergency_pause": resumed.get("outcome_code") == "paused_emergency_stop",
        "owned_resume_same_cycle": resumed.get("control_loop_run_id") == str(cycle_id),
        "owned_resume_no_event_progress": after["cycle_events"] == before["cycle_events"],
        "owned_resume_no_checkpoint_progress": after["cycle_checkpoints"] == before["cycle_checkpoints"],
        "owned_resume_no_run_step_progress": after["cycle_run_steps"] == before["cycle_run_steps"],
        "owned_resume_no_persisted_evaluation": after["cycle_evaluations"] == before["cycle_evaluations"] == 0,
        "owned_resume_no_decision": after["cycle_decisions"] == before["cycle_decisions"] == 0,
        "owned_resume_still_calls_cost_evaluator": cost_evaluator_calls == 1,
        "owned_start_exact_refusal": start_exception == "EmergencyStopActive:project emergency stop is active",
        "owned_start_rolls_back_pre_latch_cycle": before["created_run_cycles"] == after["created_run_cycles"] == 0,
        "owned_start_leaves_created_run_untouched": before["created_run_status"] == after["created_run_status"] == "created",
        "owned_start_no_work_persisted": all(after[key] == 0 for key in (
            "created_run_events", "created_run_checkpoints", "created_run_evaluations",
            "created_run_decisions", "created_run_steps"
        )),
    }
    result = {
        "database": "uaid_audit_s55_owned_20260824_67c2e9a1",
        "database_role": "app_owner",
        "isolation": "serializable",
        "activation_transaction_id": activation_txid,
        "before": before,
        "activation": {"state": activation.state, "affected_run_count": activation.affected_run_count},
        "resume": {
            "outcome": resumed.get("outcome_code"),
            "cycle": resumed.get("control_loop_run_id"),
            "cost_evaluator_calls_while_active": cost_evaluator_calls,
        },
        "start_exception": start_exception,
        "after": after,
        "assertions": assertions,
        "audit_probe_passed": all(assertions.values()),
        "product_invariant_passed": cost_evaluator_calls == 0,
    }
    if not result["audit_probe_passed"]:
        raise RuntimeError("owned persisted-latch probe assertion failed")
    print("S55_OWNED_PERSISTED_LATCH_PROBE=" + json.dumps(result, sort_keys=True, default=str))

asyncio.run(main())
PY
```

### A.3 Drop and verify absence

```bash
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d postgres -v ON_ERROR_STOP=1 -Atqc "SELECT datname,pg_get_userbyid(datdba),datallowconn FROM pg_database WHERE datname='uaid_audit_s55_owned_20260824_67c2e9a1'"
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE "uaid_audit_s55_owned_20260824_67c2e9a1"'
docker exec -e PGPASSWORD=app uaid_os-postgres-1 psql -U app -d postgres -v ON_ERROR_STOP=1 -Atqc "SELECT count(*) FROM pg_database WHERE datname='uaid_audit_s55_owned_20260824_67c2e9a1'"
```

## Appendix B — Exact static writer-candidate census

This is the exact reproducible read-only scanner implementing the conservative 119 direct-endpoint census rule in §4.6. It recognizes only the stated syntactic forms, does not descend from a function into a nested function/lambda, and deliberately counts a base writer helper and a semantic caller as separate callable endpoints. The three SQL-function wrappers below are a manual, cited addition. This appendix makes the **candidate census** reproducible; it does not convert that census into a deduplicated/exhaustive semantic-leaf proof.

```bash
.venv/bin/python - <<'PY'
import ast
from collections import Counter
from pathlib import Path


class LocalCalls(ast.NodeVisitor):
    def __init__(self, root):
        self.root = root
        self.calls = []

    def visit_FunctionDef(self, node):
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if node is self.root:
            self.generic_visit(node)

    def visit_Lambda(self, node):
        return

    def visit_Call(self, node):
        self.calls.append(node)
        self.generic_visit(node)


def receiver_kind(node):
    if isinstance(node, ast.Name) and node.id in {"session", "self"}:
        return node.id
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "session"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return "self.session"
    return None


rows = []
for path in sorted(Path("app").rglob("*.py")):
    tree = ast.parse(path.read_text())
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for function in functions:
        visitor = LocalCalls(function)
        visitor.visit(function)
        mechanisms = set()
        for call in visitor.calls:
            target = call.func
            if (
                isinstance(target, ast.Attribute)
                and target.attr in {"add", "add_all"}
                and receiver_kind(target.value)
            ):
                mechanisms.add("orm_add")
            if isinstance(target, ast.Name) and target.id == "pg_insert":
                mechanisms.add("pg_insert")
            if (
                isinstance(target, ast.Name)
                and target.id == "text"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
                and "INSERT INTO" in call.args[0].value.upper()
            ):
                mechanisms.add("raw_insert")
        if mechanisms:
            rows.append(
                (
                    str(path),
                    function.lineno,
                    function.name,
                    "+".join(sorted(mechanisms)),
                )
            )

print(f"DIRECT_WRITER_ENDPOINTS={len(rows)}")
print(f"PRIVATE_DIRECT={sum(name.startswith('_') for _, _, name, _ in rows)}")
print(f"PUBLIC_DIRECT={sum(not name.startswith('_') for _, _, name, _ in rows)}")
counts = Counter(mechanism for *_, mechanism in rows)
print("MECHANISMS=" + ",".join(f"{key}:{counts[key]}" for key in sorted(counts)))
for path, line, name, mechanism in sorted(rows):
    print(f"{path}:{line}|{name}|{mechanism}")

wrappers = (
    "app/audit.py:30-52|audit_append|sql_function_wrapper",
    "app/repositories/admin.py:91-114|admin_write_autonomy_policy|sql_function_wrapper",
    "app/repositories/go_live_decisions.py:443-472|slice55_finalize_decision|sql_function_wrapper",
)
for wrapper in wrappers:
    print(wrapper)
print(f"INDIRECT_SQL_WRAPPER_ENDPOINTS={len(wrappers)}")
print(f"CANDIDATE_WRITER_ENDPOINT_TOTAL={len(rows) + len(wrappers)}")
PY
```

Exact output:

```text
DIRECT_WRITER_ENDPOINTS=119
PRIVATE_DIRECT=40
PUBLIC_DIRECT=79
MECHANISMS=orm_add:107,orm_add+pg_insert:1,pg_insert:9,raw_insert:2
app/admin/tenant_admin.py:49|_record_event|orm_add
app/admin/tenant_admin.py:100|grant_admin_role|orm_add
app/agents/registry.py:102|register_blueprint|orm_add
app/agents/registry.py:125|register_version|orm_add
app/agents/registry.py:186|instantiate|orm_add
app/repositories/acceptance_verification.py:66|record_independent_approval|orm_add
app/repositories/acceptance_verification.py:118|record_extraction_unapproved|orm_add
app/repositories/acceptance_verification.py:158|record_dispute|orm_add
app/repositories/acceptance_verification.py:202|record_failed_verification|orm_add
app/repositories/acceptance_verification.py:334|verify_project|orm_add
app/repositories/admin.py:58|record|orm_add
app/repositories/agent_failures.py:37|record_failure|orm_add
app/repositories/agent_realizations.py:30|realize|orm_add
app/repositories/api_keys.py:39|issue|orm_add
app/repositories/approval_notifications.py:24|record|orm_add
app/repositories/approvals.py:65|request|orm_add
app/repositories/approvals.py:308|_record|orm_add
app/repositories/catalog_admin.py:71|register_connector|orm_add
app/repositories/catalog_admin.py:130|register_blueprint_version|orm_add
app/repositories/catalog_admin.py:156|register_reference_intake|orm_add
app/repositories/catalog_admin.py:211|record_contract_test|orm_add
app/repositories/catalog_admin.py:242|record_review|orm_add
app/repositories/catalog_admin.py:275|list_asset|orm_add
app/repositories/catalog_adoptions.py:31|adopt|orm_add
app/repositories/ci_evidence.py:35|record_branch_protection|orm_add
app/repositories/ci_evidence.py:60|record_connector_verified_branch_protection|orm_add
app/repositories/classification.py:289|_record|orm_add
app/repositories/cost.py:47|record|orm_add+pg_insert
app/repositories/cost.py:184|upsert|orm_add
app/repositories/cost_forecasts.py:153|record_policy_version|orm_add
app/repositories/cost_forecasts.py:425|_record_refusal|orm_add
app/repositories/cost_forecasts.py:497|_persist_success|orm_add
app/repositories/cost_optimizer.py:32|recommend|orm_add
app/repositories/deployments.py:48|_record|orm_add
app/repositories/documents.py:36|ingest|pg_insert
app/repositories/emergency_controls.py:337|append_binding|orm_add
app/repositories/emergency_controls.py:463|append_event|orm_add
app/repositories/emergency_controls.py:493|activate|orm_add
app/repositories/emergency_controls.py:593|authorize_rollback|orm_add
app/repositories/evidence_packs.py:79|record_audit_chain_verification|orm_add
app/repositories/evidence_packs.py:205|record_failed_attempt|orm_add
app/repositories/evidence_packs.py:654|_persist_core|orm_add
app/repositories/export_bundles.py:61|generate|orm_add
app/repositories/export_bundles.py:209|_try_insert_record|pg_insert
app/repositories/extraction.py:71|extract|orm_add
app/repositories/extraction.py:296|promote_proposal|orm_add
app/repositories/extraction.py:433|_record_run|orm_add
app/repositories/findings.py:44|evaluate_and_record|orm_add
app/repositories/generator.py:333|_record|orm_add
app/repositories/go_live_decisions.py:176|start_cycle|pg_insert
app/repositories/go_live_decisions.py:290|append_event|orm_add
app/repositories/go_live_decisions.py:337|record_evaluation|orm_add
app/repositories/intake.py:37|add_artifact|orm_add
app/repositories/intake_categories.py:35|declare|orm_add
app/repositories/learning.py:39|persist|orm_add
app/repositories/monitoring_evidence.py:48|_record|orm_add
app/repositories/ops_hotfix.py:252|_try_insert_run|pg_insert
app/repositories/ops_hotfix.py:297|_insert_plans|orm_add
app/repositories/ops_hotfix.py:327|_insert_children|orm_add
app/repositories/ops_incidents.py:119|try_insert_incident|pg_insert
app/repositories/ops_incidents.py:150|_insert_ticket|orm_add
app/repositories/ops_incidents.py:167|_append_event|orm_add
app/repositories/ops_incidents.py:177|insert_evaluation|orm_add
app/repositories/ops_incidents.py:371|record_handover|orm_add
app/repositories/ops_signals.py:154|try_insert_run|pg_insert
app/repositories/ops_signals.py:191|insert_results|orm_add
app/repositories/ops_stabilization.py:159|attempt_closure|orm_add
app/repositories/ops_stabilization.py:291|_try_insert_window|pg_insert
app/repositories/ops_stabilization.py:349|_insert_children|orm_add
app/repositories/pm_issues.py:43|_record|orm_add
app/repositories/pr_evidence.py:68|_record|orm_add
app/repositories/production_preapprovals.py:248|append_policy_snapshot|orm_add
app/repositories/production_preapprovals.py:288|append_request|orm_add
app/repositories/production_preapprovals.py:403|append_attestation|orm_add
app/repositories/production_preapprovals.py:440|append_lifecycle_event|orm_add
app/repositories/projects.py:12|create|orm_add
app/repositories/qualification.py:74|record_qualification_run|orm_add
app/repositories/readiness.py:108|evaluate_and_record|orm_add
app/repositories/release_candidates.py:32|create|orm_add
app/repositories/release_candidates.py:64|bind_issue|orm_add
app/repositories/release_candidates.py:267|_event|orm_add
app/repositories/release_findings.py:28|create|orm_add
app/repositories/release_findings.py:136|_event|orm_add
app/repositories/release_issues.py:42|create|orm_add
app/repositories/release_issues.py:62|create_from_trusted_finding|orm_add
app/repositories/release_issues.py:256|_event|orm_add
app/repositories/release_verdicts.py:245|evaluate_and_record|orm_add
app/repositories/release_verdicts.py:399|record_failed_attempt|orm_add
app/repositories/review_reports.py:32|record_report|orm_add
app/repositories/reviewer_quality.py:106|execute_suite|orm_add
app/repositories/reviewer_quality.py:337|_record_case|orm_add
app/repositories/reviewer_quality.py:383|_failure|orm_add
app/repositories/risk_acceptance.py:42|create|orm_add
app/repositories/risk_acceptance.py:223|_event|orm_add
app/repositories/rollback_verifications.py:273|_record_failure|orm_add
app/repositories/rollback_verifications.py:301|_record_observation|orm_add
app/repositories/runs.py:66|record_step|orm_add
app/repositories/secrets_verification.py:47|_record|orm_add
app/repositories/security_scans.py:117|_record_failure|orm_add
app/repositories/security_scans.py:148|_record_observation|orm_add
app/repositories/security_scans.py:180|_record_category|orm_add
app/repositories/semantic_contradictions.py:243|_record|orm_add
app/repositories/shortcut_detectors.py:345|_record_failure|orm_add
app/repositories/shortcut_detectors.py:380|_record_success|orm_add
app/repositories/skills.py:40|register_skill|raw_insert
app/repositories/skills.py:52|register_capability|raw_insert
app/repositories/skills.py:178|build_and_record|orm_add
app/repositories/task_contracts.py:53|create|orm_add
app/repositories/task_contracts.py:129|add_artifact_link|orm_add
app/repositories/task_contracts.py:178|add_reviewer|orm_add
app/repositories/task_contracts.py:256|_transition|orm_add
app/repositories/test_oracles.py:364|_record_failure|orm_add
app/repositories/test_oracles.py:623|_record_judgment_success|orm_add
app/repositories/test_oracles.py:691|_record_deterministic_success|orm_add
app/repositories/tools.py:46|_event|orm_add
app/repositories/tools.py:69|record|orm_add
app/runtime/checkpointer.py:81|aput|pg_insert
app/runtime/checkpointer.py:122|aput_writes|pg_insert
app/tenancy.py:96|add|orm_add
app/audit.py:30-52|audit_append|sql_function_wrapper
app/repositories/admin.py:91-114|admin_write_autonomy_policy|sql_function_wrapper
app/repositories/go_live_decisions.py:443-472|slice55_finalize_decision|sql_function_wrapper
INDIRECT_SQL_WRAPPER_ENDPOINTS=3
CANDIDATE_WRITER_ENDPOINT_TOTAL=122
```
