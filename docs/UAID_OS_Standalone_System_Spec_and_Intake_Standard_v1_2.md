# Universal Autonomous Integration & Delivery OS (UAID OS)

## Standalone System Specification and Universal Intake Standard

**Version:** 1.2  
**Date:** May 2026  
**Document type:** Standalone product, architecture, operating model, assurance, and intake standard  
**Intended audience:** Founder, product owner, CTO, AI systems architect, platform engineer, delivery operations lead, security reviewer, compliance lead, enterprise buyer, and implementation team

---

## Document control

| Item | Value |
|---|---|
| Working name | Universal Autonomous Integration & Delivery OS |
| Short name | UAID OS |
| Purpose | Define a standalone, domain-agnostic system that turns sufficient project documentation into production-grade digital systems through autonomous execution, controlled authority, dynamic specialist staffing, review, verification, deployment, and post-launch stabilization. |
| Domain posture | Universal and field-agnostic. The system must support any domain expressible through a domain pack, regulatory pack, data contracts, acceptance criteria, and test oracles. |
| Critical clarification | The platform is not tied to any reference project, customer, region, industry, certifier, cloud, framework, or tool vendor. Reference intakes may exist as separate companion artifacts to prove generality, but they are not part of the core specification. |
| Terminology rendering | This specification intentionally uses the simplified ASCII spelling **Al-Muhasibi** for compatibility across DOCX/PDF readers and developer tooling. Companion artifacts may use diacritics when their rendering pipeline supports them. |

---

## 0. Executive answer

UAID OS is a universal autonomous delivery control plane. It is designed to receive a project documentation package, determine whether the package is build-ready, compile missing specifications when possible, create the correct project-specific specialist team, build the software or digital system, review every output, test the system against explicit oracles, deploy to staging, prove go-live readiness through evidence, and deploy to production only under the approved autonomy policy.

The platform is field-agnostic by design. Its generality should be validated against diverse reference intake packages kept outside the core specification. Reference intakes demonstrate coverage; they do not define or constrain the architecture.

The platform is **not** a fixed group of generic coding agents. It is a self-staffing autonomous systems integrator. For every project, it decides what disciplines are needed, creates or activates the relevant specialists, binds them to tools and reviewers, gives them scoped authority, and keeps running through build/review/fix cycles until the system is live-ready or a legitimate blocker is reached.

The core operating idea is:

```text
Autonomous in execution. Controlled in authority. Evidence decides done.
```

The system can build across domains only if the domain is made explicit through intake artifacts. A healthcare system, a geospatial analytics system, a finance workflow, an AI assurance platform, a manufacturing control dashboard, a regulatory evidence engine, a mobile app, or a knowledge-graph RAG platform may all be buildable, but each needs a different domain pack, acceptance model, safety posture, data contract, review authority, and tool stack.

A fully autonomous go-live run is possible only when the intake reaches **R5: autonomous go-live-ready build package** and the authority policy permits **A5: conditional autonomous production release**. When intake information is incomplete, UAID OS must generate a gap register, compile missing specs where safe, request approval where needed, or stop. It must never invent unsafe facts, fake integrations, weaken tests, or mark unfinished work as complete.

---

## 1. System identity and scope

### 1.1 What UAID OS is

UAID OS is a software delivery operating system that performs the work of a professional integration company through agents, tools, workflows, policies, evidence, and human approval gates.

Its lifecycle is:

```text
Intake -> Understanding -> Specification -> Staffing -> Planning -> Build -> Review -> Test -> Fix -> Deploy -> Verify -> Go Live -> Operate
```

It has seven primary responsibilities:

1. **Understand the project.** Read documentation, classify the project, extract requirements, identify domain constraints, and determine build readiness.
2. **Compile the build package.** Transform business, technical, regulatory, data, design, and operational documents into implementation-ready artifacts.
3. **Create the correct team.** Match required work to skills, activate reusable agents, and create new specialist agents when existing ones are insufficient.
4. **Execute delivery.** Create repositories, project boards, branches, pull requests, CI/CD, tests, deployment workflows, documentation, monitoring, and release artifacts.
5. **Verify independently.** Use specialist reviewers, QA agents, security reviewers, shortcut detectors, acceptance verifiers, platform auditors, and evidence packs.
6. **Control authority.** Enforce autonomy policy, approval gates, separation of duties, least privilege, cost ceilings, and production safeguards.
7. **Operate until stable.** Continue post-launch monitoring, defect triage, rollback readiness, incident handling, and improvement loops.

### 1.2 What UAID OS is not

UAID OS is not:

- a chatbot that writes code in a single answer;
- a fixed multi-agent group chat;
- a code generator that trusts its own output;
- a project manager that only creates tasks;
- a no-control automation that can ship unsafe work;
- an agent marketplace without governance;
- a production deployment bot;
- a system that treats every document as build-ready;
- a system that can replace legal, regulatory, clinical, financial, safety, or domain authority where human or institutional approval is required.

### 1.3 What "build anything" means

"Build anything" means:

```text
Any digital, software-defined, automatable, or deployable system whose desired behavior can be specified, tested, reviewed, deployed, monitored, and governed through tools and evidence.
```

This includes, but is not limited to:

- SaaS platforms;
- internal enterprise applications;
- APIs and backend services;
- data platforms and pipelines;
- AI applications;
- multi-agent systems;
- workflow and approval systems;
- knowledge graph systems;
- RAG and search systems;
- analytics engines;
- reporting and document-generation systems;
- decision-support systems;
- compliance and audit systems;
- mobile applications;
- integration platforms;
- dashboards and command centers;
- developer tools;
- operational automation systems.

The system cannot honestly "build anything" from nothing. It can build when the intake gives it enough truth, authority, tools, testability, and deployment access. If not, its job is to create the missing specification or stop at the right blocker.

---

## 2. Operating creed and non-negotiable principles

### 2.0 System creed

```text
Builders build.
Reviewers challenge.
Verifiers prove.
Auditors confirm.
Policy controls authority.
Evidence decides done.
```

This creed is the control language of the platform. It applies to product requirements, architecture, code, data, AI outputs, regulatory mapping, testing, deployment, and go-live decisions.

### 2.1 No fake done

No task is complete until evidence proves that it satisfies the original requirement or an approved revised requirement.

Forbidden unless explicitly approved and documented:

- placeholder features presented as real features;
- fake data in production paths;
- demo-only behavior presented as implementation;
- hardcoded outputs to pass tests;
- simulated integrations where real integrations were required;
- skipped acceptance criteria;
- tests weakened to pass bad code;
- silent fallbacks that hide failure;
- broad `try/catch` blocks that swallow real errors;
- empty functions or TODOs for required behavior;
- local-only behavior where a real external service was required;
- marking a ticket done without evidence;
- changing the requirement to fit a weak implementation.

The system must prefer an honest blocker over fake completion.

### 2.2 No agent approves its own work

Every consequential output must be reviewed by an independent checker. High-risk outputs require multiple reviewers.

```text
Builder -> Self-check -> Specialist reviewer -> QA -> Security -> Shortcut detector -> Acceptance verifier -> Delivery auditor
```

The builder may claim the work is complete. The platform decides whether it is complete.

### 2.3 Evidence over claims

Agent narratives are not evidence. Evidence includes:

- code diffs;
- executed tests;
- CI/CD logs;
- API responses;
- browser test recordings;
- screenshots for UI changes;
- deployment logs;
- data quality checks;
- security scan outputs;
- provenance chains;
- acceptance matrices;
- approval events;
- monitoring confirmation;
- audit trail entries.

### 2.4 Fail closed on unsupported facts

For any factual, regulatory, analytical, safety, financial, or decision-support claim, the system must know where the claim came from. If provenance cannot be established, the system must not present the claim as fact.

The system must distinguish:

```text
source-supported fact
calculated result
model-generated hypothesis
assumption
unverified claim
human-approved judgment
third-party-certified assertion
```

### 2.5 Documentation is executable input

User documentation is not merely context. It becomes:

- requirements;
- user stories;
- task contracts;
- architecture constraints;
- domain rules;
- data contracts;
- agent context;
- acceptance criteria;
- test oracles;
- compliance gates;
- release policy;
- evidence requirements.

### 2.6 Autonomy requires boundaries

The system may execute autonomously only inside approved authority boundaries.

Actions requiring explicit approval by default:

- production deployment;
- merging to protected branches;
- deleting data or infrastructure;
- changing secrets;
- modifying billing or paid resources;
- sending communications to real users;
- accessing sensitive customer data;
- accepting legal, regulatory, clinical, financial, or safety risk;
- bypassing a failed gate;
- weakening test or review standards.

### 2.7 Dynamic specialists, not generic agents

The system must not assume that every project needs the same agents. It must identify the required skills and create the right project-specific team.

If a project requires a knowledge graph expert, mobile accessibility reviewer, geospatial data engineer, industry formula verifier, payment-integration specialist, medical workflow reviewer, hardware-interface engineer, regulatory control mapper, ontology architect, or any other domain-specific specialist, the system must create or activate that role and assign independent reviewers.

---

## 3. Reasoning and provenance kernel

### 3.1 Purpose

UAID OS requires a reasoning kernel because autonomous delivery fails when agents jump from request to output without disciplined self-scrutiny. The reasoning kernel governs every consequential decision, including requirements interpretation, architecture choices, assumptions, domain claims, test design, release decisions, and go-live verdicts.

Low-risk mechanical steps may use simpler execution logic. Consequential decisions must pass through the kernel.

### 3.2 Universal Al-Muhasibi critical-reflection wrapper

UAID OS uses an internal reasoning discipline called the **Universal Al-Muhasibi Critical-Reflection Wrapper**. The name is a methodology label, not a domain restriction. It can be applied to any project, industry, or jurisdiction.

Every consequential decision is processed through five stages:

```text
1. Khawatir   -> surface the initial thought, plan, claim, or proposed action.
2. Muraqaba   -> monitor assumptions, incentives, authority, scope, and risk.
3. Mujahada   -> actively challenge shortcuts, weak evidence, unsafe assumptions, and false confidence.
4. Muhasaba   -> account for evidence, provenance, alternatives, residual risk, and responsibility.
5. Final output -> produce the decision, action, blocker, or escalation with evidence and limits.
```

The wrapper is not exposed as private chain-of-thought. It is operationalized as structured decision records, checklists, evidence fields, reviewer reports, and audit entries.

### 3.3 Consequential decision record

Every consequential decision should generate a structured record:

```yaml
decision_id: DEC-000123
decision_type: architecture | requirement | assumption | release | security | domain | cost | tool | agent
proposal: "Use managed PostgreSQL with vector extension for retrieval storage."
khawatir_initial_rationale: "The intake requires relational data plus semantic retrieval."
muraqaba_risks:
  - "Data residency constraints may limit provider choice."
  - "Vector extension performance must be tested."
mujahada_challenges:
  - "Do not assume managed service is allowed without environment policy."
  - "Do not claim enterprise readiness without backup/restore tests."
muhasaba_evidence:
  - "Requirement NFR-07 requires managed backups."
  - "Data contract DC-03 requires semantic retrieval."
verdict: approved_with_conditions
conditions:
  - "Run load test before go-live."
  - "Verify residency in deployment region."
reviewers:
  - architecture_reviewer
  - data_security_reviewer
```

### 3.4 Sanad-style provenance chain

UAID OS uses a **Sanad-style provenance chain** for claims and evidence. The term "Sanad" here means a traceable chain of support from output back to source, calculation, reviewer, and verdict.

A provenance chain contains:

```text
claim -> narrator chain -> source reliability scoring -> content consistency check -> context boundary -> verdict -> evidence link
```

Where:

- **Claim** is the assertion, requirement, result, or recommendation.
- **Narrator chain** is the path through documents, agents, tools, calculations, reviewers, and approvals that produced it.
- **Source reliability scoring** evaluates origin, authority, freshness, completeness, conflict, and access method. This is analogous to jarh wa ta'dil scoring in concept: the platform evaluates the reliability of the source and transmitter chain.
- **Content consistency check** evaluates whether the content itself conflicts with other known evidence. This is analogous to matn review in concept: the platform checks the internal and external coherence of the assertion.
- **Context boundary** states where the claim is valid and where it is not.
- **Verdict** classifies the claim as accepted, accepted with limits, rejected, blocked, unverified, or human judgment required.
- **Evidence link** attaches the proof to the evidence pack.

Example:

```yaml
claim_id: CLAIM-0042
claim: "Users with role viewer cannot export restricted records."
narrator_chain:
  - source: "05_user_roles_and_permissions.md"
  - compiler: requirements_traceability_agent
  - implementation: backend_engineer_agent
  - tests: access_control_e2e_spec
  - reviewer: security_reviewer_agent
source_reliability:
  authority: user_provided_requirement
  freshness: current_intake
  conflict_status: no_conflict_found
content_consistency:
  matched_requirements:
    - PERM-08
    - SEC-03
  tested_behavior: true
context_boundary: "Applies to web application export endpoint and UI export button. Does not cover future API endpoints not yet built."
verdict: accepted
evidence:
  - pr_url
  - ci_run_url
  - e2e_test_log
  - security_review_report
```

### 3.5 Third-party assurance posture

The evidence pack is structured for consumption by any independent assurance, audit, certification, regulatory, customer, or internal governance body. UAID OS does not assume a specific certifier. A certifier may be internal, external, industry-specific, regional, or customer-appointed.

---

## 4. Universal intake standard

### 4.1 Intake purpose

The first intake is the most important control point. The platform can only run fully autonomously if the user provides enough information to prevent unsafe invention.

The intake must answer:

- What must be built?
- Why must it be built?
- Who will use it?
- What is in scope and out of scope?
- What domain rules apply?
- What data exists?
- Which integrations are required?
- Which environments are available?
- What tools may the system use?
- What authority does the system have?
- What counts as success?
- What counts as go-live readiness?
- Who approves risky or ambiguous decisions?

### 4.2 Required intake package for R5

For a project to be **R5: autonomous go-live-ready**, the user should provide a structured intake package containing the following 26 files. The system may support alternate formats, but it must compile them into this canonical shape.

| File | Name | Purpose |
|---:|---|---|
| 00 | `project_manifest.yaml` | Project identity, owner, run mode, target outcome, repository/project names, preferred tools. |
| 01 | `product_brief.md` | Plain-language description of what the system should do and who it is for. |
| 02 | `business_objectives.md` | Business goals, success metrics, ROI targets, constraints, deadlines. |
| 03 | `scope_and_boundaries.md` | In scope, out of scope, assumptions, explicit non-goals. |
| 04 | `users_roles_permissions.md` | Personas, roles, authorization rules, permission matrix. |
| 05 | `user_journeys_and_workflows.md` | End-to-end user journeys, operational workflows, approval paths. |
| 06 | `functional_requirements.md` | Features, modules, business rules, required behaviors. |
| 07 | `non_functional_requirements.md` | Performance, reliability, scalability, accessibility, availability, maintainability. |
| 08 | `acceptance_criteria.yaml` | Verifiable criteria that define completion for each feature and workflow. |
| 09 | `test_oracles.yaml` | Expected-output, reference-output, or judgment-based oracle definitions. |
| 10 | `domain_pack.yaml` | Domain entities, rules, terminology, authorities, sensitivities, constraints. |
| 11 | `data_model_and_contracts.yaml` | Entities, fields, schemas, relationships, lineage, validation, retention. |
| 12 | `integrations_and_external_systems.yaml` | APIs, third-party tools, protocols, authentication, sandbox/production access. |
| 13 | `existing_assets_and_repositories.yaml` | Existing code, docs, designs, datasets, credentials locations, legacy systems. |
| 14 | `architecture_and_technology_constraints.md` | Required/preferred stack, cloud, deployment model, infrastructure constraints. |
| 15 | `security_privacy_compliance.md` | Threats, sensitive data, compliance obligations, privacy rules, audit needs. |
| 16 | `environments_and_deployment_targets.yaml` | Local, dev, staging, production, domains, cloud accounts, regions. |
| 17 | `secrets_and_credentials_manifest.yaml` | Secret names, owners, availability, rotation policy; never actual secret values in plain documents. |
| 18 | `tool_access_manifest.yaml` | Approved tools, APIs, scopes, accounts, repositories, project boards, communication channels. |
| 19 | `autonomy_policy.yaml` | What the system may do automatically, what requires approval, escalation rules. |
| 20 | `human_approval_policy.yaml` | Approvers, approval thresholds, batching rules, non-response behavior, override authority. |
| 21 | `cost_and_resource_policy.yaml` | Budget ceilings, model-routing policy, cloud spending limits, stop conditions. |
| 22 | `operations_observability_support.md` | Monitoring, logging, alerts, runbooks, incident process, support model. |
| 23 | `go_live_checklist.yaml` | Enterprise go-live requirements, release gates, rollback criteria, post-launch stabilization. |
| 24 | `risk_register_and_assurance_requirements.md` | Known risks, required assurance evidence, third-party review needs, unresolved decisions. |
| 25 | `prior_decisions_and_architecture_log.md` | Existing architectural decisions, approved constraints, ADRs, migration constraints, deprecated paths, prior incidents, rejected options, and decisions that must not be rediscovered or reversed without approval. |

### 4.3 Readiness levels R0-R5

| Level | Name | Meaning | Allowed behavior |
|---|---|---|---|
| R0 | Idea only | User gives a vague idea. | Interview, discovery, concept brief only. |
| R1 | Strategy package | User gives business/strategy docs but no build spec. | Create PRD, options, roadmap, gap register. |
| R2 | Product package | Features and users are described, but technical/data/test details are incomplete. | Generate technical spec, backlog, assumptions, approval requests. |
| R3 | Technical package | Architecture, stack, data, and workflows exist, but authority/test/deployment gaps remain. | Create repo/Jira, prototype, build non-production modules, create blockers. |
| R4 | Implementation-ready package | Most requirements, architecture, tests, and tools are available; production authority incomplete. | Build to staging, run tests, evidence pack, request production decisions. |
| R5 | Autonomous go-live-ready package | Requirements, oracles, environments, secrets, authority, approvals, and go-live gates are complete. | Run autonomous build/review/fix/deploy flow to approved go-live gate. |

### 4.4 Mandatory behavior when intake is incomplete

If the intake is not R5, UAID OS must not pretend it can go live. It must choose one of four actions:

```text
1. Compile missing docs from available material.
2. Ask the human for a specific missing decision.
3. Create a blocker ticket.
4. Make a safe assumption only if the autonomy policy permits it and the assumption is low-risk.
```

The system must label every generated assumption as:

```text
safe assumption
needs approval
unsafe assumption - blocked
unknown - cannot proceed
```

### 4.5 Intake validation output

Every run starts with an intake validation report:

```json
{
  "project_id": "example_project",
  "readiness_level": "R3",
  "can_build_to_staging": true,
  "can_go_live_autonomously": false,
  "missing_for_go_live": [
    "production deployment target",
    "approved human approval policy",
    "test oracle for recommendation quality",
    "secrets manifest"
  ],
  "safe_assumptions": [
    "Use default accessibility target WCAG 2.2 AA unless stricter policy is provided."
  ],
  "blocked_assumptions": [
    "Cannot infer regulatory reporting threshold without authority source."
  ]
}
```

---

## 5. Autonomy policy standard

### 5.1 Autonomy levels A0-A5

Readiness and autonomy are separate. A project may have complete documentation but low allowed autonomy, or incomplete documentation but high aspiration for autonomy.

| Level | Name | Authority |
|---|---|---|
| A0 | Advisory only | System can analyze and recommend, but cannot modify tools or code. |
| A1 | Draft mode | System can draft specs, Jira tickets, code patches, and plans but cannot execute external actions. |
| A2 | Controlled build | System can create branches, write code, open PRs, and run tests. |
| A3 | Staging autonomy | System can deploy to staging and run verification loops. |
| A4 | Production prepared | System can prepare production release but requires explicit human approval to deploy. |
| A5 | Conditional production autonomy | System can deploy production only if all pre-approved gates pass and no blocker exists. |

### 5.2 Authority matrix

| Action | Default autonomy | Required control |
|---|---|---|
| Read user-provided docs | A0+ | Intake sandbox and injection defense |
| Create draft PRD | A1+ | Spec reviewer |
| Create Jira/project tasks | A1+ | Project owner or policy approval |
| Create GitHub repo | A2+ | Tool access manifest |
| Create branches and commits | A2+ | Branch policy and audit log |
| Open pull requests | A2+ | PR template and traceability |
| Run tests | A2+ | CI/test environment |
| Deploy staging | A3+ | Environment policy |
| Merge to protected branch | A4+ | Required reviews and status checks |
| Deploy production | A4/A5 | Human approval or pre-approved A5 gate |
| Delete resources | Manual by default | Explicit approval |
| Change secrets | Manual by default | Secret owner approval |
| Modify billing | Manual by default | Finance/admin approval |
| Access sensitive customer data | Manual by default | Data owner approval and audit |
| Override failed gate | Manual by default | Exception record and approver |

### 5.3 Autonomy policy template

```yaml
autonomy_policy:
  autonomy_level: A3
  run_mode: controlled_autonomous_staging

  allow:
    create_project_board: true
    create_repository: true
    create_branches: true
    commit_code: true
    open_pull_requests: true
    run_tests: true
    deploy_staging: true
    write_documentation: true

  require_approval:
    merge_to_main: true
    deploy_production: true
    delete_resources: true
    modify_billing: true
    change_secrets: true
    access_sensitive_data: true
    send_external_communications: true
    override_failed_gate: true

  stop_conditions:
    max_daily_cost_exceeded: true
    critical_security_finding: true
    missing_required_secret: true
    no_test_oracle_for_critical_feature: true
    human_approval_overdue_policy: pause
```

---

## 6. Documentation-to-Delivery Compiler

### 6.1 Purpose

The Documentation-to-Delivery Compiler converts raw user documentation into executable delivery artifacts.

It must accept many document types:

- strategy documents;
- commercial documents;
- product documents;
- technical architecture documents;
- regulatory documents;
- data dictionaries;
- diagrams;
- policies;
- operational runbooks;
- designs;
- source code;
- spreadsheets;
- API docs;
- contracts;
- existing Jira/GitHub artifacts.

It must then compile them into canonical artifacts the delivery runtime can execute.

### 6.2 Compiler pipeline

```text
Upload docs
  -> document classification
  -> source and authority mapping
  -> requirement extraction
  -> contradiction detection
  -> gap detection
  -> spec generation if needed
  -> domain pack generation
  -> data contract generation
  -> acceptance criteria extraction
  -> test oracle classification
  -> project backlog generation
  -> skill requirement generation
  -> build readiness report
```

### 6.3 Canonical output artifacts

The compiler produces:

- project manifest;
- PRD;
- system architecture document;
- data model;
- domain pack;
- integration plan;
- acceptance criteria;
- test oracle pack;
- Jira backlog;
- task contracts;
- agent skill map;
- tool access plan;
- risk register;
- evidence requirements;
- go-live checklist.

### 6.4 Contradiction handling

When documents conflict, UAID OS must not silently choose one. It must classify the conflict:

```text
minor wording conflict
scope conflict
business-rule conflict
technical conflict
legal/regulatory conflict
security conflict
budget/timeline conflict
authority conflict
```

Then it must produce a decision request or a proposed resolution with provenance.

### 6.5 Spec generation mode

If documentation is incomplete but enough context exists, the system may enter Spec Generation Mode.

Spec Generation Mode can produce:

- missing PRD sections;
- technical design options;
- data contracts;
- acceptance criteria;
- test oracles;
- backlog items;
- domain pack drafts;
- go-live checklist drafts;
- risk register drafts.

However, generated specifications are not automatically binding. They must pass spec-authorship independence controls.

---

## 7. Spec authorship independence

### 7.1 The acceptance-criteria paradox

If the system writes the acceptance criteria and later grades itself against those criteria, it can unintentionally create an easy target. That violates separation of duties at the specification level.

Therefore:

```text
Acceptance criteria authored by the system cannot become binding verification targets until independently reviewed and approved.
```

### 7.2 Allowed authorship statuses

Every acceptance criterion must carry one of these provenance statuses:

| Status | Meaning | Verification weight |
|---|---|---|
| user_authored | Provided directly by the user or authorized product owner. | Full |
| user_authored_system_normalized | User authored; system cleaned wording or structure without changing meaning. | Full if reviewer confirms no meaning drift |
| system_authored_human_approved | Generated by system; approved by human owner. | Full |
| system_authored_independent_approved | Generated by one agent lineage; approved by independent reviewer lineage. | Conditional/full depending on risk |
| system_authored_unapproved | Generated but not approved. | Not binding for go-live |
| disputed | Conflicting or challenged. | Blocked until resolved |

### 7.3 Independent approval rules

For generated acceptance criteria to become binding, one of the following must occur:

1. A human product owner approves the criteria.
2. An independent agent lineage approves the criteria.
3. A domain authority reviewer approves criteria in a regulated or specialized domain.
4. A reference system or existing contract provides a stable oracle.

Independence means different role, different prompt family, separate reviewer authority, and, for high-risk projects, a different model route or provider when available.

Operational definition of **prompt family**:

```text
prompt family = a versioned, named template root with shared instruction lineage, examples, constraints, reviewer policy, and eval suite.
```

Two prompts are different families only when they have separate template roots, separate authoring lineage, and separate eval suites. Minor wording changes, persona labels, or temperature changes do not create true independence. If only one model provider is available, prompt-family separation is treated as a weaker control and must be compensated by additional adversarial review or human approval for high-risk criteria.

### 7.4 Evidence pack marking

The evidence pack must show which criteria were user-authored and which were system-generated:

```yaml
acceptance_criterion:
  id: AC-012
  text: "User can export only records permitted by role."
  authorship: system_authored_human_approved
  generated_by: requirements_compiler_agent_v3
  approved_by: product_owner
  approved_at: 2026-05-09T10:20:00Z
  verification_status: passed
```

---

## 8. Skill Matching Engine

### 8.1 Purpose

The Skill Matching Engine determines which capabilities are required and which agents should perform the work.

It must match not only technology stack but also:

- domain knowledge;
- data skills;
- legal/regulatory constraints;
- AI/ML requirements;
- UX requirements;
- integration requirements;
- risk level;
- reviewer needs;
- test oracle type;
- required tools;
- cost constraints;
- expected delivery speed.

### 8.2 Skill graph

The platform maintains a skill graph:

```text
Project -> requirement -> task -> skill -> agent capability -> tool access -> reviewer -> evidence requirement
```

Example skill categories:

- product strategy;
- business analysis;
- UX design;
- frontend engineering;
- backend engineering;
- mobile engineering;
- data engineering;
- AI engineering;
- prompt engineering;
- model evaluation;
- knowledge graph engineering;
- workflow automation;
- API integration;
- DevOps;
- security;
- privacy;
- domain analysis;
- compliance mapping;
- financial modeling;
- geospatial systems;
- formula verification;
- document generation;
- QA automation;
- accessibility;
- performance engineering;
- release management;
- incident response.

### 8.3 Matching score

The matching engine should rank agents using a transparent score:

```text
agent_score =
  capability_match * 0.30
+ domain_fit * 0.15
+ tool_access_fit * 0.15
+ eval_performance * 0.20
+ reviewer_availability * 0.10
+ cost_latency_fit * 0.10
- risk_penalty
```

High-risk work must favor reliability over cost or speed.

### 8.4 Output: project squad manifest

```yaml
project_squad:
  project_id: example_project
  active_agents:
    - id: backend_engineer_api_v2
      role: Backend Engineer
      assigned_tasks:
        - API-001
        - API-002
      reviewers:
        - backend_reviewer_v1
        - security_reviewer_v3

    - id: knowledge_graph_specialist_v1
      role: Knowledge Graph Specialist
      assigned_tasks:
        - KG-001
      reviewers:
        - knowledge_graph_reviewer_v1
        - data_quality_reviewer_v2

  missing_skills:
    - "Domain-specific formula verification"
  agent_factory_requests:
    - create_formula_verifier_agent
```

---

## 9. Agent Factory

### 9.1 Purpose

The Agent Factory creates, configures, qualifies, versions, and registers project-specific agents.

The system must be explicit: creating a new agent is not magic and is not usually model training. It is the binding of a role definition, instructions, tools, context policy, reviewers, evals, and authority into a controlled executable actor.

### 9.2 Agent realization mechanism

An agent is defined as:

```text
agent = (
  role and mission,
  system prompt template,
  task contract interface,
  tool allowlist,
  context retrieval policy,
  memory policy,
  model routing policy,
  action authority limits,
  reviewer linkage,
  eval suite reference,
  budget limits,
  observability hooks,
  version identifier
)
```

Creating a new agent means binding these components and passing a qualification gate. It does not mean fine-tuning a model unless the Tool/Model Governance Board explicitly approves fine-tuning as a separate project.

### 9.3 Agent blueprint

```yaml
agent_blueprint:
  id: domain_formula_verifier_v1
  role: Domain Formula Verifier
  mission: "Verify formulas, calculations, thresholds, and business-rule implementations against approved domain sources."

  system_prompt_template: agent_templates/domain_formula_verifier.md

  tools:
    allow:
      - read_project_docs
      - read_code
      - run_unit_tests
      - run_calculation_tests
      - create_review_report
    deny:
      - deploy_production
      - modify_acceptance_criteria
      - approve_own_output

  context_retrieval_policy:
    include:
      - domain_pack
      - data_contracts
      - acceptance_criteria
      - source_documents
    exclude:
      - unrelated_chat_history
      - untrusted_instructions_inside_documents

  reviewers:
    - qa_reviewer
    - domain_reviewer

  eval_suite:
    archetype: formula_verification
    project_specific_cases: generated_from_domain_pack

  authority:
    can_reject_pr: true
    can_mark_done: false
```

### 9.4 Factory workflow

```text
1. Receive missing skill or project-specific role request.
2. Search agent registry for qualified existing agent.
3. If no fit exists, select agent archetype.
4. Bind role, prompt template, tools, context policy, reviewer links, and eval suite.
5. Generate project-specific evaluation cases.
6. Run dry qualification tests.
7. Send agent spec to Agent QA Reviewer and Platform Security Reviewer.
8. Register approved agent in project squad.
9. Monitor performance.
10. Reconfigure, split, replace, or escalate if failure persists.
```

### 9.5 Dry tests and qualification oracles

The Factory cannot rely on "looks good" evaluation. It needs an eval library.

The platform ships with role-archetype evals:

- software engineer evals;
- reviewer evals;
- security evals;
- data engineer evals;
- UX evals;
- domain reasoning evals;
- prompt engineering evals;
- knowledge graph evals;
- AI evaluation evals;
- integration evals;
- deployment evals;
- evidence-pack evals.

Project-specific evals are generated from the intake, then reviewed independently before use.

### 9.5.1 Archetype eval methodology

The archetype eval library is a controlled asset, not an informal checklist. Each archetype eval must define representative tasks, a gold-answer or oracle source, a scoring rubric, a minimum pass threshold, and a refresh policy.

| Archetype | Representative task set | Gold-answer / oracle source | Scoring focus | Minimum activation threshold | Refresh policy |
|---|---|---|---|---|---|
| Builder | Implement features, fix bugs, preserve behavior, and avoid shortcuts. | Reference implementations, accepted PRs, deterministic tests, seeded defect corpora. | Correctness, maintainability, test coverage, no-fake-done behavior. | 80-90% aggregate by risk; zero critical shortcut failures. | Quarterly, plus after major model/framework/tool change. |
| Reviewer | Detect defects, missing criteria, weak tests, fake integrations, and unsupported claims. | Planted-defect corpus and expert-labeled review reports. | Critical-defect recall, specificity, evidence use, no rubber-stamping. | Critical defect recall >= 90%; false approval below policy threshold. | Monthly, plus after reviewer miss incident. |
| Security reviewer | Detect authz flaws, prompt injection, secrets exposure, unsafe tools, and supply-chain risk. | Security fixtures, known vulnerability patterns, red-team cases. | Severity classification, exploit clarity, remediation quality. | Zero missed critical vulnerabilities; high-severity recall >= 85%. | Monthly and when threat library changes. |
| Data engineer | Validate schemas, pipelines, lineage, data quality, retention, and migrations. | Data contracts, synthetic/approved datasets, lineage fixtures. | Data integrity, reproducibility, loss prevention, lineage accuracy. | All critical data contracts pass. | Quarterly and after data-stack changes. |
| Domain reasoner | Apply domain rules, terminology, authorities, and prohibited assumptions. | Domain pack fixtures, authority-source mappings, expert cases. | Source fidelity, boundary discipline, safe blocker behavior. | No critical unsupported authority claims. | Per domain pack release. |
| Prompt engineer | Create constrained agent/reviewer prompts and anti-shortcut instructions. | Prompt evals, injection tests, ambiguity tests, policy-bypass cases. | Clarity, tool discipline, failure-mode coverage, injection resistance. | No critical policy loopholes; aggregate >= 85%. | Monthly and after prompt-template changes. |
| Knowledge graph / RAG | Build entity/relation structures, retrieval tests, and provenance-backed responses. | Graph fixtures, retrieval gold sets, provenance benchmarks. | Entity/relation precision, retrieval relevance, citation grounding. | Project-defined precision/recall floor; zero unsupported facts in critical outputs. | Per corpus/domain refresh. |
| AI evaluation | Design rubrics, sampling, judge lineages, IRR checks, and adversarial sets. | Audited evaluation plans and calibration fixtures. | Oracle validity, sampling adequacy, bias controls, disagreement handling. | Plan-quality score >= 85%; no missing critical metric. | Quarterly and after model family change. |
| Integration / connector | Build connector contracts, auth, rate limits, error handling, and audit logging. | Sandbox APIs, mocked failure modes, connector contract tests. | Contract compliance, least privilege, error handling, observability. | 100% critical contract tests; aggregate >= 85%. | Per connector/API version change. |
| Deployment / SRE | Build CI/CD, infra, rollback, monitoring, backup/restore, and failure drills. | Reference deployments, failure-injection scenarios, runbooks. | Idempotency, rollback, observability, recovery, cost discipline. | Zero critical deploy/rollback failure; aggregate >= 85%. | Monthly and after runtime/cloud change. |
| Evidence auditor | Assemble and validate evidence packs. | Complete/incomplete evidence fixtures and schema tests. | Traceability, export validity, missing-evidence detection, tamper evidence. | Critical-evidence recall >= 95%. | Monthly and after evidence schema change. |

The library must include positive cases, negative cases, edge cases, adversarial cases, and incomplete-input cases. Eval results are versioned. An agent that fails its archetype activation threshold cannot be registered for autonomous work until remediated and requalified.

### 9.6 Replacement policy

If an agent fails repeatedly, the system must not retry forever. It should diagnose the failure:

| Failure pattern | Response |
|---|---|
| Missing skill | Create or recruit specialist agent. |
| Weak instructions | Generate prompt variant and run eval. |
| Wrong tools | Update tool allowlist after security review. |
| Poor model performance | Route to stronger model for this role. |
| Context overload | Improve context retrieval policy. |
| Reviewer rejects same issue repeatedly | Create focused remediation task. |
| Safety/authority violation | Suspend agent and trigger audit. |
| Persistent inability | Escalate to human or mark blocker. |

### 9.7 Agent versioning

Every agent version must be immutable once used in a delivery run. Changes create a new version.

```yaml
agent_instance:
  id: backend_engineer_api_v2_2026_05_09
  blueprint_id: backend_engineer_api_v2
  model_route: frontier_reasoning_for_complex_tasks
  prompt_hash: sha256:...
  tool_policy_hash: sha256:...
  context_policy_hash: sha256:...
  eval_suite_hash: sha256:...
  active_run_id: RUN-001
```

---

## 10. Dynamic agent taxonomy

### 10.1 Core company agents

| Agent | Purpose |
|---|---|
| Delivery Commander | Owns run orchestration and state. |
| CTO Agent | Owns technical direction. |
| Product Manager Agent | Converts goals into product scope. |
| Business Analyst Agent | Creates user stories and acceptance criteria. |
| Project Manager Agent | Creates and maintains board/backlog/sprint flow. |
| Chief Quality Officer Agent | Owns quality policy and review routing. |
| Release Manager Agent | Owns release readiness, deployment policy, rollback. |
| Delivery Auditor Agent | Confirms evidence, traceability, and separation of duties. |

### 10.2 Engineering agents

| Agent | Purpose |
|---|---|
| Solution Architect | Designs system architecture. |
| Frontend Engineer | Builds UI and client-side logic. |
| Backend Engineer | Builds APIs, services, auth, domain logic. |
| Data Engineer | Builds schemas, pipelines, validation, lineage. |
| Database Engineer | Designs and optimizes persistence. |
| Mobile Engineer | Builds mobile applications when needed. |
| Integration Engineer | Connects external APIs and tools. |
| DevOps/SRE Agent | Builds CI/CD, infrastructure, monitoring, reliability. |
| Performance Engineer | Tests and optimizes latency, load, throughput. |
| Accessibility Engineer | Ensures accessibility requirements are met. |

### 10.3 AI-native agents

| Agent | Purpose |
|---|---|
| AI Systems Architect | Designs AI, agent, RAG, evaluation, and model-routing architecture. |
| AI Engineer | Implements AI features, model calls, agents, tools, and model workflows. |
| Prompt Engineer | Designs agent instructions, task contracts, and reviewer prompts. |
| Prompt Reviewer | Checks prompts for ambiguity, loopholes, unsafe authority, and shortcut incentives. |
| Evals Engineer | Creates evaluation suites for model and agent behavior. |
| Model Routing Agent | Assigns tasks to the correct model based on risk, cost, latency, and quality. |
| RAG Engineer | Builds retrieval systems and context pipelines. |
| Knowledge Graph Expert | Builds ontologies, entity/relation extraction, graph storage, graph retrieval. |
| Agent Framework Specialist | Designs framework-specific workflows when a project needs them. |
| MCP/Tooling Specialist | Builds reusable tool connectors and controlled tool interfaces. |
| LLM Security Agent | Tests prompt injection, data leakage, unsafe tool use, and model abuse cases. |

### 10.4 Review and verification agents

| Agent | Purpose |
|---|---|
| Specialist Reviewer | Reviews work in the same discipline as the builder. |
| QA Agent | Tests behavior against requirements. |
| QA Reviewer | Reviews test quality and coverage. |
| Security Reviewer | Reviews product security. |
| Shortcut Detection Agent | Detects stubs, fakes, hardcoding, test weakening, and hidden fallbacks. |
| Acceptance Verifier | Confirms delivery matches original requirement and approved criteria. |
| Test Oracle Reviewer | Confirms oracles are valid for the target behavior. |
| Evidence Pack Auditor | Confirms evidence is complete and traceable. |
| Go-Live Readiness Agent | Decides whether release criteria are satisfied. |

### 10.5 Domain agents

Domain agents are generated from the domain pack. They are not hardcoded into the core platform.

Examples of possible domain-agent categories:

- regulatory control mapper;
- clinical workflow reviewer;
- financial model verifier;
- geospatial data specialist;
- manufacturing process specialist;
- education assessment specialist;
- logistics optimization specialist;
- energy systems analyst;
- public-sector policy reviewer;
- legal document workflow reviewer;
- terminology/localization specialist;
- industry-reporting specialist.

These examples illustrate the mechanism. They are not a fixed taxonomy.

### 10.6 MVP vs expandable roles

The MVP platform should include:

- Delivery Commander;
- Documentation Compiler;
- Product/BA Agent;
- Solution Architect;
- Frontend/Backend/Data/DevOps Agents;
- QA Agent;
- Security Reviewer;
- Shortcut Detection Agent;
- Acceptance Verifier;
- Evidence Pack Auditor;
- Skill Matching Engine;
- Agent Factory with a small archetype library.

Additional agents should be created dynamically from skill demand rather than preloaded as bureaucracy.

---

## 11. Tool, integration, and execution layer

### 11.1 Tool broker

Agents must not call external tools directly. They call a platform-controlled Tool Broker.

The Tool Broker enforces:

- authentication;
- least privilege;
- per-agent allowlists;
- input validation;
- output validation;
- rate limits;
- cost controls;
- approval gates;
- audit logging;
- tenant boundaries.

### 11.2 Core tool categories

| Category | Examples of functions |
|---|---|
| Project management | create issue, transition issue, attach evidence, create epic, comment. |
| Source control | create repo, create branch, commit files, open PR, comment, read diff. |
| CI/CD | run workflow, read build logs, check status, deploy staging. |
| Cloud/infrastructure | provision environment, deploy service, read metrics, rollback. |
| Secrets | request secret reference, verify secret exists, rotate under approval. |
| Communication | send update, request approval, receive command, post digest. |
| Browser testing | open app, fill form, click, assert state, capture evidence. |
| API testing | call endpoint, validate response, compare schema. |
| Data testing | validate dataset, lineage, schema, data quality. |
| Monitoring | create uptime checks, read logs, configure alerts. |
| Documentation | read docs, write docs, link artifacts, generate runbooks. |

### 11.3 MCP and connector abstraction

The platform should support a standardized connector layer for tools, data sources, and workflows. MCP-style servers or equivalent controlled tool servers can be used to expose external systems safely.

Every connector must have:

- permission manifest;
- authentication method;
- tenant scope;
- allowed operations;
- denied operations;
- data classification;
- audit policy;
- test suite;
- owner;
- incident contact.

### 11.4 Tool contract example

```json
{
  "tool_name": "github.create_pull_request",
  "input_schema": {
    "owner": "string",
    "repo": "string",
    "branch": "string",
    "base": "string",
    "title": "string",
    "body": "string",
    "linked_issue": "string"
  },
  "required_authority": "A2",
  "requires_approval": false,
  "audit_level": "high",
  "forbidden_conditions": [
    "branch_contains_unreviewed_secret",
    "linked_issue_missing",
    "no_task_contract"
  ]
}
```

---

## 12. Delivery operating model

### 12.1 End-to-end flow

```text
1. Intake package received.
2. Intake sandbox scans documents for injection, malware, and unsafe instructions.
3. Documentation Compiler classifies and extracts requirements.
4. Build Readiness Auditor assigns R-level.
5. Autonomy Policy Agent assigns A-level and approval gates.
6. Spec Compiler fills safe gaps or requests decisions.
7. Skill Matching Engine creates project skill map.
8. Agent Factory creates/activates specialist agents.
9. Project Manager Agent creates backlog and workflow board.
10. Repository Bootstrapper creates repository and branch policies.
11. Architecture Agent creates initial architecture and implementation plan.
12. Builders implement ticket-by-ticket.
13. Reviewers challenge outputs.
14. Tests and oracles verify behavior.
15. Shortcut Detector searches for fake completion.
16. Acceptance Verifier checks original request coverage.
17. Delivery Auditor confirms evidence pack.
18. Staging deployment occurs when eligible.
19. Go-Live Readiness Agent reviews release criteria.
20. Production deployment occurs only if policy allows.
21. Post-launch monitoring and stabilization continue until stable.
```

### 12.2 Iteration inside phases

The lifecycle is not a rigid waterfall. Each phase contains loops:

```text
build -> review -> reject -> fix -> retest -> verify
```

The system may run multiple cycles inside a phase before phase exit. Partial-scope release is allowed only when the autonomy policy permits it and the evidence pack clearly states what is and is not included.

### 12.3 Project board workflow

Recommended workflow:

```text
Backlog
  -> Analysis
  -> Requirements Review
  -> Ready for Development
  -> In Progress
  -> Developer Self-Check
  -> Specialist Review
  -> Changes Requested
  -> QA Testing
  -> Security Review
  -> Shortcut Detection
  -> Acceptance Verification
  -> Evidence Audit
  -> Ready for Release
  -> Released
  -> Done
```

Builder agents cannot move their own work to Done.

### 12.4 Pull request workflow

Every PR must include:

- linked task or issue;
- task contract;
- implementation summary;
- acceptance criteria coverage;
- tests added;
- evidence links;
- known limitations;
- workarounds/fallbacks used;
- security notes;
- rollback notes if relevant.

PRs cannot merge until required checks pass and required reviewers approve.

---

## 13. Maker-checker-verifier quality system

### 13.1 Three-layer review

| Layer | Purpose | Examples |
|---|---|---|
| Role-specific review | Confirm discipline quality. | Backend reviewer, UX reviewer, data reviewer. |
| Cross-functional review | Confirm integration, security, operations. | QA, security, DevOps, architecture. |
| Acceptance review | Confirm the user request is satisfied. | Acceptance verifier, evidence auditor, go-live readiness agent. |

### 13.2 Task contract

Before any builder starts, the system creates a task contract.

```json
{
  "task_id": "AUTH-013",
  "title": "Implement user login",
  "must_have": [
    "User can log in with email and password",
    "Invalid credentials are rejected",
    "Successful login creates secure session",
    "Protected routes require authentication"
  ],
  "must_not_do": [
    "Do not use fake authentication",
    "Do not hardcode credentials",
    "Do not store plain-text passwords",
    "Do not silently accept invalid credentials"
  ],
  "required_evidence": [
    "unit tests",
    "API tests",
    "E2E login test",
    "security review",
    "CI passing run"
  ],
  "reviewers": [
    "backend_reviewer",
    "security_reviewer",
    "qa_agent",
    "acceptance_verifier"
  ]
}
```

### 13.3 Reviewer verdicts

Reviewers return structured verdicts:

```json
{
  "verdict": "REJECTED_WITH_REQUIRED_CHANGES",
  "summary": "Implementation accepts any password for existing emails.",
  "failed_criteria": [
    "Invalid credentials are rejected",
    "Password verification is implemented"
  ],
  "suspected_shortcuts": [
    "Authentication service returns success without password hash comparison"
  ],
  "required_changes": [
    "Implement password hash verification",
    "Add invalid-login tests",
    "Add E2E test for protected route access"
  ],
  "can_merge": false
}
```

### 13.4 Shortcut detection checklist

The Shortcut Detection Agent checks for:

- hardcoded values;
- static responses replacing real behavior;
- fake external integrations;
- disabled validation;
- removed or weakened tests;
- broad error swallowing;
- placeholder UI;
- TODOs in required paths;
- local-only substitutes for production services;
- acceptance criteria silently skipped;
- tests that check implementation details instead of behavior;
- claims of readiness without evidence.

### 13.5 Reviewer quality assurance

Reviewer agents are not automatically trustworthy. LLM-based reviewers may rubber-stamp work, over-trust builder summaries, or miss subtle shortcuts. UAID OS must therefore review the reviewers.

Reviewer QA rules:

1. **Different LLM from builder.** For consequential work, the reviewer should use a different model route from the builder. For high-risk work, the reviewer should use a different model provider when available. If that is not possible, the degraded independence rule in Section 16.7 applies.
2. **No summary-only approvals.** Reviewers must inspect primary evidence: PR diffs, changed files, test output, logs, runtime behavior, acceptance criteria, and tool results.
3. **Adversarial sampling.** The platform periodically injects planted defects, planted shortcuts, weakened tests, fake integrations, and missing-evidence cases into reviewer queues.
4. **Miss-rate tracking.** Each reviewer agent has metrics for critical-defect recall, false approvals, false rejections, review latency, evidence usage, and specificity of required changes.
5. **Reviewer replacement threshold.** If a reviewer misses planted critical defects above the allowed threshold, the system suspends or downgrades that reviewer and triggers the Agent Factory replacement policy.
6. **Blind challenge reviews.** Selected high-risk PRs receive a second blind reviewer that cannot see the first reviewer verdict until after its own verdict is submitted.
7. **Human calibration.** High-risk reviewer evals require periodic human or authorized authority sampling when the project policy requires it.

Example reviewer QA record:

```yaml
reviewer_quality_record:
  reviewer_agent: backend_reviewer_v4
  model_route: provider_b_high_quality_review
  prompt_family: backend_review_family_v3
  sample_window: 2026-05-01_to_2026-05-09
  planted_cases_reviewed: 40
  planted_critical_defects_missed: 1
  critical_miss_rate: 0.025
  allowed_critical_miss_rate: 0.03
  status: qualified
  next_calibration_due: 2026-05-16
```

A reviewer that fails planted critical-defect checks must not approve high-risk work until requalified.

---

## 14. Test oracle framework

### 14.1 Why oracles matter

A system cannot verify completion without knowing what correct behavior means. For deterministic features, correct behavior may be exact. For AI, ranking, forecasting, recommendation, or decision-support systems, correct behavior may require reference baselines or judgment rubrics.

UAID OS must classify every critical test oracle before claiming go-live readiness.

### 14.2 Oracle types

| Oracle type | Meaning | Best for | Required controls |
|---|---|---|---|
| Specified oracle | Exact expected output or deterministic rule is known. | Calculations, permissions, API behavior, formulas, workflow state transitions. | Unit/integration/E2E tests, schema checks, formula checks. |
| Reference oracle | A known-good baseline exists. | Legacy replacement, migration, regression tests, benchmark systems, approved manual outputs. | Baseline snapshot, drift tolerance, comparison rules, reference provenance. |
| Judgment oracle | Correctness requires human or evaluator judgment against a rubric. | AI outputs, rankings, recommendations, generated reports, strategy suggestions, subjective UX quality. | Rubric, sample size, independent judges, inter-rater reliability threshold, disagreement resolution. |

### 14.3 Judgment oracle requirements

Judgment oracles are high-risk because the expected output is not mechanically obvious. They require additional controls:

- explicit rubric;
- representative sample set;
- adversarial sample set;
- blind or independent review when possible;
- at least two evaluator lineages for high-impact outputs;
- disagreement tracking;
- minimum acceptance threshold;
- reviewer calibration examples;
- evidence of failure cases and limits;
- human/domain authority review when required.

The numeric defaults below are illustrative defaults, not universal statistical truth. Projects must tune them by risk, consequence of error, output variability, and available reference data. A sample of 100 gives a practical initial signal for common product-quality decisions, while higher-risk or high-variance AI tasks may need larger samples, stratified sampling, or human adjudication. The inter-rater reliability floor is intended to prevent evaluator disagreement from being hidden by aggregate scores; projects may raise it for safety, legal, financial, regulatory, clinical, or mission-critical outputs.

Example:

```yaml
oracle:
  id: ORACLE-RANK-001
  type: judgment
  target: "Recommendation ranking quality"
  rubric:
    - relevance
    - factual support
    - user goal fit
    - harmful suggestion avoidance
    - explainability
  sample_size: 100
  sample_size_policy: illustrative_default_tune_per_project_risk
  minimum_pass_rate: 0.85
  minimum_pass_rate_policy: illustrative_default_tune_per_project_risk
  inter_rater_reliability_minimum: 0.70
  irr_policy: illustrative_default_tune_per_project_risk
  reviewers:
    - evaluator_agent_a
    - evaluator_agent_b
    - human_domain_reviewer_for_sample
```

### 14.4 No oracle, no go-live

If a critical feature has no valid oracle, UAID OS may build a draft or staging prototype, but it cannot mark the feature production-ready.

---

## 15. Evidence pack and definition of done

### 15.1 Evidence pack purpose

The evidence pack is the artifact of done. It is the reviewable proof that the system satisfied requirements and obeyed policy.

Production readiness is not a feeling, a demo, or an agent summary. It is an evidence bundle.

### 15.2 Evidence pack structure

```yaml
evidence_pack:
  release_id: REL-2026-05-09-001
  project_id: example_project
  scope:
    included_features:
      - feature_a
      - feature_b
    excluded_features:
      - future_feature_c

  traceability:
    requirements_to_tasks: true
    tasks_to_prs: true
    prs_to_tests: true
    tests_to_acceptance_criteria: true
    claims_to_sources: true

  build:
    repository: repo_url
    pull_requests:
      - pr_url
    commits:
      - commit_hash

  verification:
    unit_tests: passed
    integration_tests: passed
    e2e_tests: passed
    security_review: passed
    shortcut_detection: passed
    acceptance_verification: passed

  provenance:
    sanad_chains_complete: true
    unverified_claims: []

  approvals:
    product_owner: approved
    release_manager: approved
    security: approved

  deployment:
    staging: successful
    production: pending_or_successful
    rollback_plan: verified

  known_limitations: []
  open_blockers: []
```

### 15.3 Definition of done

A task is Done only when:

1. acceptance criteria are implemented;
2. required tests exist;
3. tests pass;
4. no required behavior is stubbed or faked;
5. no unauthorized fallback is used;
6. specialist reviewer approves;
7. QA approves;
8. security approves when applicable;
9. Shortcut Detection Agent approves;
10. Acceptance Verifier approves;
11. evidence pack is updated;
12. the linked PR is merged through approved workflow;
13. deployment status matches the task's release stage.

### 15.4 Evidence pack export standard

The evidence pack must be exportable as a machine-readable and auditor-readable bundle. The export contract is required because third-party auditors, customers, internal governance teams, and certifiers cannot consume an undefined bundle.

Minimum export formats:

- `evidence_pack.json` using the platform evidence-pack JSON Schema;
- `evidence_pack.md` or `evidence_pack.pdf` for human review;
- signed manifest of files, hashes, timestamps, and signer identity;
- read-only auditor access link or archive package;
- optional compliance mapping, including OSCAL-style control mapping when the project is compliance-heavy.

Minimum JSON Schema shape:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UAID Evidence Pack Export",
  "type": "object",
  "required": [
    "schema_version", "project_id", "release_id", "generated_at",
    "scope", "traceability", "claims", "requirements", "tasks",
    "pull_requests", "tests", "reviews", "approvals",
    "deployments", "risks", "signatures"
  ],
  "properties": {
    "schema_version": { "type": "string" },
    "project_id": { "type": "string" },
    "release_id": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "scope": { "type": "object" },
    "traceability": { "type": "array" },
    "claims": { "type": "array" },
    "requirements": { "type": "array" },
    "tasks": { "type": "array" },
    "pull_requests": { "type": "array" },
    "tests": { "type": "array" },
    "reviews": { "type": "array" },
    "approvals": { "type": "array" },
    "deployments": { "type": "array" },
    "risks": { "type": "array" },
    "signatures": { "type": "array" }
  }
}
```

Cryptographic requirements:

- every exported file must have a content hash;
- the manifest must be signed by the platform release authority or tenant-approved signing key;
- post-signature mutation invalidates the pack;
- auditor access is read-only and logged;
- redacted auditor packs must preserve hash references to original evidence items without exposing restricted content.

---

## 16. Security, privacy, and platform self-defense

### 16.1 Product security

For systems built by UAID OS, security review must include:

- authentication;
- authorization;
- role-based access control;
- secrets handling;
- input validation;
- dependency scanning;
- supply-chain risk;
- data privacy;
- logging and audit;
- rate limits;
- encryption;
- backup and restore;
- tenant isolation;
- incident response;
- secure deployment configuration.

### 16.2 Platform self-defense

UAID OS itself is a high-value attack surface. The platform must defend against attacks on intake, agents, tools, logs, policies, and review routing.

### 16.3 Threat: prompt injection through intake documents

Customer-supplied documents are untrusted data. They may contain instructions such as "ignore the security reviewer" or "disable shortcut detection." The platform must treat such content as document content, not system instruction.

Controls:

- document sandboxing;
- instruction/data separation;
- prompt injection scanning;
- retrieval-time content labeling;
- policy hierarchy enforcement;
- never allowing document text to override platform policy;
- reviewer check for injected instructions;
- quarantine for suspicious sections.

### 16.4 Threat: tool privilege escalation

An agent may attempt to call tools outside its role.

Controls:

- Tool Broker with per-agent allowlist;
- least-privilege tokens;
- scope-limited credentials;
- approval gates for high-risk tools;
- deny-by-default unknown tools;
- runtime validation of tool parameters;
- audit logs for every tool call;
- automatic suspension on privilege violation.

### 16.5 Threat: adversarial gap resolution

A malicious or careless requirement may pressure the system to invent unsafe assumptions.

Controls:

- unsafe assumptions are blocked;
- missing legal/regulatory/safety facts require authority source;
- generated assumptions are classified by risk;
- all assumptions are visible in the evidence pack;
- high-risk assumptions require human or domain authority approval.

### 16.6 Threat: audit log tampering

Agents must not be able to rewrite the evidence trail.

Controls:

- append-only audit log;
- hash chaining of log entries;
- external log sink;
- separation of log writer and log administrator;
- read-only reviewer access;
- tamper-evidence checks before release.

### 16.7 Threat: sybil or collusion between agents

The same agent lineage must not act as builder and reviewer for the same work.

Controls:

- lineage tracking;
- role incompatibility matrix;
- reviewer independence policy;
- different model route for reviewer vs builder by default;
- different model/provider separation for high-risk review when available;
- explicit single-provider fallback when provider separation is unavailable;
- random reviewer assignment for selected audits;
- blind second review for selected high-risk work;
- Delivery Auditor validation of separation of duties.

Single-provider fallback:

If a deployment uses only one model provider, the system must explicitly mark provider-level independence as unavailable. It may still use compensating controls, but these are weaker than true provider separation:

```text
single_provider_review_fallback =
  different prompt family
  + different model variant or route when available
  + different temperature/sampling policy where appropriate
  + different reviewer persona and role authority
  + separate eval suite
  + blind review where possible
  + adversarial planted-defect reviewer QA
  + human review compensation for high-risk decisions
```

For high-risk production, security, legal, financial, clinical, safety, privacy, or irreversible decisions, single-provider fallback is insufficient by itself. The platform must require human review, external authority review, or explicit risk acceptance before release. The evidence pack must disclose whether high-risk reviews used provider separation or only single-provider fallback controls.

### 16.8 Threat: malicious generated agents

The Agent Factory could accidentally create an agent with unsafe authority.

Controls:

- generated agent specs reviewed by Agent QA Reviewer;
- Platform Security Reviewer approval for tool grants;
- eval gate before activation;
- deny production authority by default;
- agent version immutability;
- kill switch.

### 16.9 Threat: connector and supply-chain compromise

Connectors can become attack paths.

Controls:

- signed connector versions;
- connector test suite;
- permission manifest;
- secret isolation;
- dependency scanning;
- approval before new connector activation;
- runtime anomaly detection.

---

## 17. Multi-tenancy and tenant isolation

### 17.1 Gate-zero requirement

For enterprise, regulated, sovereign, or multi-customer use, tenant isolation is not a later enhancement. It is a Phase 1 requirement.

### 17.2 Tenant isolation controls

UAID OS must isolate:

- user identities;
- documents;
- prompts;
- agent memory;
- vector stores;
- knowledge graphs;
- repositories;
- tool credentials;
- cloud environments;
- audit logs;
- evidence packs;
- billing/cost records;
- communication channels.

### 17.3 Tenant boundary rule

No agent may retrieve, summarize, compare, or reuse another tenant's project context unless explicitly authorized by a cross-tenant policy and reviewed by security.

### 17.4 Tenant-aware agent registry

Reusable agent blueprints may be global. Agent instances, context policies, memory, and tool grants must be tenant-scoped.

### 17.5 Cross-project learning boundary

UAID OS may improve from operational patterns across projects only if tenant isolation is preserved. Cross-project learning must distinguish between allowed aggregate signals and forbidden tenant-derived content.

Allowed without explicit tenant content-sharing consent, if anonymized and aggregated:

- aggregate eval failure rates;
- aggregate reviewer miss patterns;
- anonymized cost and latency benchmarks;
- generic tool reliability metrics;
- generic connector failure categories;
- non-identifying frequency counts of failure modes;
- security-safe statistics that cannot reconstruct tenant content.

Forbidden without explicit consent and security review:

- tenant documents;
- tenant prompts or task contracts containing project specifics;
- tenant code, data, schemas, logs, or screenshots;
- tenant-specific retrieval context;
- tenant-identifying metadata;
- unique architecture decisions that reveal strategy;
- evidence-pack contents;
- domain authorities, customers, vendors, or user identities tied to a tenant;
- exact defect narratives that can identify the project.

If cross-project learning uses any tenant-derived content beyond aggregate anonymized signals, the project must have an explicit consent artifact, approved data classification, retention policy, and removal mechanism. Sovereign, regulated, or high-confidentiality tenants default to no cross-project content sharing.

---

## 18. Human-in-the-loop UX

### 18.1 Purpose

Autonomy fails if the system asks humans 500 questions. Human-in-the-loop must be designed as an executive control experience, not a stream of interruptions.

### 18.2 Approval batching

Approvals should be grouped by risk and time sensitivity:

| Approval type | UX pattern |
|---|---|
| Low-risk clarifications | Daily digest or batch approval. |
| Medium-risk scope decisions | Decision bundle with recommendation and alternatives. |
| High-risk security/legal/cost decision | Real-time approval request with evidence and impact. |
| Production deployment | Formal release approval with go-live evidence pack. |
| Emergency rollback | Immediate alert and optional auto-rollback if policy permits. |

### 18.3 Spec Generation Mode interviews

When information is missing, the system should interview the user in structured rounds:

```text
Round 1: project purpose and scope
Round 2: users, roles, workflows
Round 3: data, integrations, environments
Round 4: acceptance criteria and test oracles
Round 5: authority, cost, go-live policy
```

The system should avoid asking questions already answered in the documents. Each question must say why it matters and what happens if unanswered.

### 18.4 Mid-run course correction

A human owner may issue a mid-run correction. The system must:

1. freeze affected tasks;
2. identify impacted requirements, code, tests, and evidence;
3. create a change request;
4. estimate cost/scope impact;
5. require approval if the change affects schedule, security, compliance, or production readiness;
6. resume with updated traceability.

### 18.5 Non-responsive owner policy

If an approver does not respond, the system follows `human_approval_policy.yaml`:

```yaml
non_response_policy:
  low_risk_decision: proceed_with_safe_assumption_after_24h
  medium_risk_decision: pause_affected_work_after_24h
  high_risk_decision: block_until_approval
  production_deployment: block_until_approval
  escalation_chain:
    - product_owner
    - technical_owner
    - executive_owner
```

### 18.6 Human dashboard

The owner dashboard should show:

- current run state;
- open approvals;
- blockers;
- cost consumed and forecast;
- remaining critical path;
- build/readiness level;
- evidence pack status;
- high-risk findings;
- deployment status;
- next recommended action.

---

## 19. Economic envelope and cost control

### 19.1 Why cost control is core architecture

A multi-agent build can become expensive. A 200-task project with eight review steps per task can create 1,600 agent/review actions before deployment. Without model routing, caching, phase budgets, and early stop rules, autonomous delivery becomes economically unsafe.

Cost control is therefore a first-class platform feature.

### 19.2 Cost components

```text
total_cost = model_inference_cost
           + tool_execution_cost
           + cloud_runtime_cost
           + CI/CD minutes
           + storage and retrieval cost
           + monitoring cost
           + human review cost
           + rework cost
```

### 19.3 Phase budget policy

Each project must define budgets by phase:

| Phase | Budget controls |
|---|---|
| Intake and compilation | Limit deep analysis until document completeness is known. |
| Architecture and planning | Use stronger models for architecture decisions; require review before implementation. |
| Build | Use cost-efficient models for routine code; stronger models for complex modules. |
| Review | Use stronger models for security, acceptance, and shortcut detection. |
| Test/fix loops | Cap repeated failures; trigger agent improvement or human escalation. |
| Deployment | Require explicit approval for cloud cost expansion. |
| Monitoring | Define post-launch stabilization window and alert policy. |

### 19.4 Model routing policy

Recommended routing:

| Task | Model policy |
|---|---|
| Document classification | Cost-efficient model unless ambiguity is high. |
| Requirements extraction | Mid/high-quality model with provenance checks. |
| Architecture decisions | Frontier reasoning model. |
| Routine code generation | Cost-efficient or mid-tier model with tests. |
| Complex AI/security/domain work | Frontier model plus specialist reviewer. |
| Code review | Mid/high-quality model; frontier for high-risk PRs. |
| Shortcut detection | High-quality model; adversarial prompt. |
| Acceptance verification | High-quality model plus tool evidence. |
| Judgment oracle review | Multiple reviewers; model diversity when possible. |

### 19.5 Worked economic example

The following is a policy-envelope example, not a vendor price quote. Actual cost depends on the provider rate card, context size, tool usage, cloud runtime, and human-review needs.

| Project size | Approx. tasks | Review intensity | Suggested model budget envelope | Typical controls |
|---|---:|---:|---:|---|
| Small | 20-40 | 3-5 review actions/task | USD 1k-5k | Tight scope, staging-first, limited judgment oracles. |
| Medium | 80-150 | 5-8 review actions/task | USD 10k-50k | Budget gates per phase, agent reuse, caching, selective frontier routing. |
| Large | 200-500+ | 8-12 review actions/task | USD 50k-250k+ | Formal budget approval, multiple squads, cost forecasting, phase-level procurement. |

### 19.6 Cost-of-review vs cost-of-rework

The platform should not review everything equally. Review intensity should be risk-adjusted.

High review intensity is required for:

- security;
- payments;
- privacy;
- regulated outputs;
- production deployment;
- data deletion;
- irreversible actions;
- AI decision-support;
- legal/financial/clinical/safety claims.

Lower review intensity may be acceptable for:

- copy updates;
- non-critical UI polish;
- internal prototypes;
- draft documentation;
- low-risk experiments.

### 19.7 Cost stop conditions

```yaml
cost_policy:
  max_total_model_cost_usd: 25000
  max_daily_model_cost_usd: 3000
  max_failed_retries_per_task: 3
  require_approval_if_forecast_exceeds_budget: true
  use_frontier_models_only_for:
    - architecture
    - security
    - acceptance_verification
    - high_risk_domain_reasoning
  stop_if:
    - repeated_failure_without_new_strategy
    - budget_exceeded
    - tool_loop_detected
    - missing_oracle_for_critical_feature
```

---

## 20. Domain pack schema

### 20.1 Purpose

The domain pack makes UAID OS field-agnostic. Instead of hardcoding industries into the platform, every project expresses its domain through a structured pack.

The domain pack can describe any field: finance, healthcare, education, geospatial systems, sovereign data, logistics, manufacturing, insurance, media, law, energy, retail, agriculture, religious/ethical review, government services, or any other domain.

### 20.2 Generic domain pack fields

```yaml
domain_pack:
  domain_name: string
  domain_summary: string

  regulatory_authorities:
    - name: string
      jurisdiction: string
      authority_type: regulator | standards_body | internal_policy_owner | certifier | other
      source_reference: string

  legal_entities:
    - name: string
      role: operator | processor | controller | customer | vendor | regulator | other
      jurisdiction: string

  jurisdictional_scope:
    countries: []
    regions: []
    data_residency_requirements: []
    cross_border_data_rules: []

  domain_entities:
    - name: string
      definition: string
      fields: []
      relationships: []

  terminology_lexicon:
    - term: string
      definition: string
      synonyms: []
      forbidden_misuses: []
      language: string

  business_rules:
    - id: string
      rule: string
      source: string
      test_oracle: string
      risk_level: low | medium | high | critical

  formulas_and_calculations:
    - id: string
      formula: string
      variables: []
      source: string
      tolerance: string
      reviewer_required: boolean

  standards_and_frameworks:
    - name: string
      version: string
      applicable_sections: []
      source: string

  sensitivity_rules:
    data_classes: []
    prohibited_outputs: []
    restricted_actions: []
    escalation_triggers: []

  localization_policy:
    languages: []
    locale_formats: []
    cultural_sensitivity_rules: []
    accessibility_expectations: []

  domain_review_authorities:
    - decision_type: regulatory | clinical | financial | safety | legal | technical | ethical | operational | data_privacy | other
      authority_name: string
      authority_role: string
      jurisdiction_or_scope: string
      approval_required_for: []
      evidence_expectations: []
      escalation_path: []

  domain_test_scenarios:
    - id: string
      scenario: string
      expected_result: string
      oracle_type: specified | reference | judgment

  prohibited_assumptions:
    - string

  open_domain_questions:
    - question: string
      risk_if_unanswered: string
      required_owner: string
```

### 20.3 Reference intakes as companion artifacts

UAID OS may maintain a separate `reference-intakes/` companion artifact library. Those examples can demonstrate how different domains fill the domain pack. They must not be embedded into the core specification and must not make the core platform dependent on a specific industry, geography, customer, or certifier.

---

## 21. Tool gap handling

### 21.1 Problem

A project may require a connector or tool the platform does not yet have. For example, a legacy ERP, specialized sensor platform, private data warehouse, proprietary workflow system, or niche industry API.

### 21.2 Tool gap classification

| Gap type | Response |
|---|---|
| Existing connector available | Activate after tenant/tool approval. |
| Similar connector available | Adapt only after Tool Reviewer approval. |
| Public API available | Build new connector/MCP server. |
| Private API available | Request credentials and docs; build with higher security review. |
| No API | Propose manual bridge, export/import workflow, RPA, or block. |
| Unsafe or unauthorized access | Block. |

### 21.3 New tool creation workflow

```text
1. Tooling Engineer identifies missing connector.
2. Tool Spec Agent writes connector contract.
3. Platform Security Reviewer checks permissions and data exposure.
4. Connector Builder implements tool server.
5. Connector QA runs contract tests.
6. Tenant owner approves activation.
7. Tool Broker registers connector with limited scope.
8. Delivery agents use connector through controlled interface.
```

### 21.4 Tool evidence requirements

Every new connector must produce:

- interface specification;
- permission manifest;
- test cases;
- sandbox run evidence;
- security review;
- data classification;
- error handling policy;
- audit log policy;
- owner and escalation path.

---

## 22. Model drift, upgrades, and agent change control

### 22.1 Problem

Models, tools, prompts, dependencies, and frameworks change during long-running projects. A model upgrade can improve performance or break behavior. UAID OS must manage this like production change control.

### 22.2 Pinning policy

During a run, the platform must snapshot:

- model route;
- prompt template hash;
- agent blueprint version;
- tool policy hash;
- context retrieval policy;
- eval suite version;
- critical dependencies;
- output schemas.

### 22.3 Upgrade policy

A model or agent upgrade during a run requires:

1. change request;
2. reason for upgrade;
3. affected agents/tasks;
4. requalification evals;
5. regression comparison;
6. rollback path;
7. approval if the upgrade affects critical work.

### 22.3.1 Forced model deprecation policy

Forced deprecation is different from voluntary upgrade. If a provider sunsets, removes, or materially changes a pinned model during an active run, UAID OS must:

1. pause affected agent roles and high-risk decisions;
2. identify successor model candidates;
3. run archetype requalification on the successor route;
4. regression-compare representative completed tasks, review decisions, and evidence outputs;
5. route only low-risk work during the transition if policy permits;
6. resume critical work only after Agent QA Reviewer and Delivery Auditor approve the replacement route;
7. disclose the model deprecation and requalification result in the run audit trail and release evidence pack.

### 22.4 Requalification triggers

Requalification is required when:

- model route changes;
- prompt template changes;
- tool permission changes;
- context retrieval policy changes;
- eval suite changes;
- domain pack changes materially;
- acceptance criteria change;
- production release candidate is created.

---

## 23. Architecture and runtime

### 23.1 Control plane

The control plane contains:

- project state store;
- workflow runtime;
- agent registry;
- skill graph;
- tool registry;
- policy engine;
- approval engine;
- evidence store;
- audit log;
- cost ledger;
- tenant manager;
- run dashboard.

### 23.2 Durable runtime

The system must support long-running workflows that can continue for hours or days.

Required runtime properties:

- persistent workflow state;
- resumable execution;
- retries with backoff;
- idempotency for external actions;
- human approval waits;
- cancellation and pause;
- audit trails;
- cost tracking;
- failure recovery;
- event-driven updates;
- tool-result persistence;
- versioned agent runs;
- deterministic replay for audit, debugging, and incident reconstruction.

### 23.3 Main control loop

```text
while not go_live_ready:
    read_project_state()
    inspect_open_requirements()
    inspect_failed_tests()
    identify_missing_skills()
    create_or_assign_agents()
    implement_next_task()
    open_pull_request()
    run_ci_and_tests()
    run_specialist_reviews()
    run_shortcut_detection()
    run_acceptance_verification()
    update_evidence_pack()
    create_rework_tickets_if_needed()
    check_cost_and_authority_limits()
    deploy_staging_if_ready()
    evaluate_go_live_gate()

if go_live_gate_passed and autonomy_policy_allows:
    deploy_production()
    monitor_and_stabilize()
```

### 23.4 State model

Core tables or collections:

- organizations;
- tenants;
- users;
- projects;
- project_runs;
- documents;
- requirements;
- acceptance_criteria;
- test_oracles;
- assumptions;
- decisions;
- agents;
- agent_versions;
- agent_runs;
- skills;
- task_contracts;
- issues;
- pull_requests;
- test_results;
- review_reports;
- evidence_packs;
- approvals;
- deployments;
- audit_logs;
- cost_events;
- tool_calls;
- connectors;
- incidents.

---

## 24. Go-live readiness

### 24.1 Go-live gate

The system is go-live ready only when:

```text
intake_readiness >= R5 or approved limited-scope release
and autonomy_policy permits release action
and all critical acceptance criteria pass
and all required test oracles pass
and no critical security finding is open
and no critical shortcut finding is open
and evidence pack is complete
and rollback plan is verified
and monitoring is active
and approvals are complete
and remaining open issues are either non-blocking or covered by explicit risk-acceptance records
```

Formal exception path:

A release may proceed with known open issues only when every remaining issue has a risk-acceptance record signed by the approvers named in the approval matrix. Risk acceptance is not allowed for unresolved critical security blockers, fake-done findings, missing production rollback, or missing authority for regulated/safety-critical obligations unless the relevant human authority explicitly accepts the risk and the autonomy policy permits that override.

```yaml
risk_acceptance_record:
  issue_id: RISK-042
  severity: medium
  description: "Known non-critical dashboard export limitation."
  business_impact: "Export unavailable for archived records until next release."
  accepted_by:
    - product_owner
    - release_manager
  expires_at: 2026-06-30
  required_follow_up_ticket: APP-219
  included_in_release_notes: true
```

### 24.2 Go-live readiness checklist

```yaml
go_live_checklist:
  product:
    all_critical_user_journeys_passed: required
    acceptance_coverage: 100
    known_limitations_disclosed: required

  engineering:
    build_passes: required
    unit_tests_pass: required
    integration_tests_pass: required
    e2e_tests_pass: required
    migrations_verified: required
    rollback_verified: required

  ai_and_data:
    critical_oracles_pass: required
    judgment_oracle_thresholds_met: required_if_applicable
    provenance_chains_complete: required
    unverified_claims_blocked: required

  security:
    authz_review_passed: required
    secrets_scan_passed: required
    dependency_scan_passed: required
    threat_model_reviewed: required
    critical_findings_open: 0

  operations:
    monitoring_enabled: required
    alerts_configured: required
    logs_available: required
    backup_restore_tested: required
    incident_runbook_complete: required

  governance:
    evidence_pack_complete: required
    approval_events_recorded: required
    separation_of_duties_confirmed: required
    open_issues_have_risk_acceptance: required_if_any_open_issues
    third_party_assurance_ready: optional_or_required_by_policy
```

### 24.3 Release verdicts

| Verdict | Meaning |
|---|---|
| passed | Release may proceed under policy. |
| passed_with_limitations | Release may proceed only if limitations are accepted. |
| failed_blocking_issue | Release blocked until critical issues are fixed. |
| failed_missing_evidence | Release blocked because proof is incomplete. |
| requires_human_decision | Release depends on authority decision. |
| not_applicable | System is not intended for production release. |

---

## 25. Post-launch stabilization and self-healing

### 25.1 Stabilization loop

After production deployment, UAID OS remains active for the approved stabilization window.

The stabilization window must be defined in `22_operations_observability_support.md` and reflected in the go-live checklist. It must specify duration, owner, support owner, monitored journeys, exit criteria, escalation path, and closure authority. Common windows are 7, 14, or 30 days depending on release risk.

Minimum exit criteria:

- zero open critical incidents for the required number of days;
- no unresolved security alert above the approved severity threshold;
- error budget under threshold;
- monitoring, alerts, logs, and dashboards confirmed active;
- support queue reviewed and handed over;
- rollback path remains valid;
- stabilization owner and release authority sign closure.

It must monitor:

- uptime;
- error rates;
- latency;
- job failures;
- security alerts;
- user journey failures;
- data quality issues;
- cost anomalies;
- model output drift;
- support tickets;
- incident reports.

### 25.2 Post-launch actions

Allowed actions depend on autonomy policy:

| Action | Default behavior |
|---|---|
| Create bug ticket | Autonomous |
| Diagnose log error | Autonomous |
| Create patch branch | A2+ |
| Open hotfix PR | A2+ |
| Deploy staging hotfix | A3+ |
| Deploy production hotfix | Approval required unless A5 emergency policy permits |
| Rollback production | Approval or pre-approved emergency rollback policy |

### 25.3 Continuous improvement

The system should update:

- lessons learned;
- recurring failure patterns;
- agent evals;
- prompt templates;
- domain pack gaps;
- test oracle gaps;
- cost forecasts;
- connector reliability scores.

### 25.4 Stabilization window definition and exit

A stabilization window must be explicit before production release.

```yaml
stabilization_window:
  duration_days: 7 | 14 | 30 | custom
  exit_criteria:
    zero_open_critical_incidents_for_days: 3
    error_budget_consumed_below_percent: 20
    p95_latency_within_slo: true
    no_unresolved_security_alerts: true
    backup_restore_validated: true
    support_handover_complete: true
  closure_authority:
    - release_manager
    - operations_owner
    - product_owner_if_customer_impacting
```

The system exits stabilization only after the closure authority approves the stabilization report or the autonomy policy grants a pre-approved closure rule. If exit criteria fail, UAID OS must create incident, defect, or improvement tickets and extend stabilization under the policy.

---

## 26. Implementation roadmap

### 26.1 Phase 1 - Control plane foundation

Phase 1 must include:

- tenant isolation;
- project state store;
- durable workflow runtime;
- tool broker;
- audit log;
- approval engine;
- cost ledger;
- document intake sandbox;
- basic dashboard;
- agent registry;
- policy engine.

Tenant isolation belongs in Phase 1, not as a late enterprise add-on.

### 26.2 Phase 2 - Documentation compiler and intake standard

Build:

- document classifier;
- requirement extractor;
- gap detector;
- contradiction detector;
- build readiness auditor;
- canonical artifact generator;
- intake template pack;
- Sanad-style provenance store.

### 26.3 Phase 3 - Project execution integrations

Build controlled integrations for:

- project management;
- source control;
- pull requests;
- CI/CD;
- staging deployment;
- communication/approval channel;
- secrets reference verification;
- monitoring integration.

### 26.4 Phase 4 - Agent Factory and skill matching

Build:

- skill graph;
- agent blueprint registry;
- agent realization mechanism;
- archetype eval library;
- agent QA workflow;
- generated-agent security review;
- performance monitoring;
- replacement policy.

### 26.5 Phase 5 - Review, verification, and evidence

Build:

- maker-checker-verifier workflow;
- task contracts;
- reviewer reports;
- test oracle framework;
- shortcut detector;
- acceptance verifier;
- evidence pack auditor;
- go-live readiness agent.

### 26.6 Phase 6 - Production release and operations

Build:

- release manager;
- production approval workflow;
- rollback verification;
- post-launch monitoring;
- incident workflow;
- self-healing/hotfix loop;
- continuous improvement engine.

### 26.7 Phase 7 - Scale and ecosystem

Build:

- marketplace of vetted agent blueprints;
- connector library;
- reference-intake companion library;
- external assurance export format;
- advanced cost optimizer;
- cross-project learning with tenant-safe anonymization;
- enterprise administration.

---

## 27. Canonical templates

### 27.1 `project_manifest.yaml`

```yaml
project:
  id: string
  name: string
  owner: string
  business_owner: string
  technical_owner: string
  target_outcome: string
  desired_go_live_date: string
  repository_preference: string
  project_management_preference: string
  communication_channel: string
  readiness_target: R5
  autonomy_target: A3
```

### 27.2 `task_contract.json`

```json
{
  "task_id": "string",
  "source_requirements": ["REQ-001"],
  "title": "string",
  "description": "string",
  "must_have": [],
  "must_not_do": [],
  "acceptance_criteria": [],
  "test_oracles": [],
  "required_evidence": [],
  "allowed_tools": [],
  "forbidden_tools": [],
  "builder_agent": "string",
  "reviewer_agents": [],
  "risk_level": "low|medium|high|critical",
  "definition_of_done": []
}
```

### 27.3 `build_readiness_report.json`

```json
{
  "project_id": "string",
  "readiness_level": "R0|R1|R2|R3|R4|R5",
  "autonomy_level_requested": "A0|A1|A2|A3|A4|A5",
  "autonomy_level_allowed": "A0|A1|A2|A3|A4|A5",
  "can_start_build": true,
  "can_deploy_staging": false,
  "can_deploy_production": false,
  "missing_artifacts": [],
  "unsafe_assumptions": [],
  "safe_assumptions": [],
  "blocked_decisions": [],
  "recommended_next_action": "string"
}
```

### 27.4 `human_approval_policy.yaml`

```yaml
human_approval_policy:
  approval_channel: slack | email | dashboard | ticketing_system
  daily_digest_time: "09:00"
  batch_low_risk_questions: true
  realtime_for:
    - production_deployment
    - security_exception
    - cost_overrun
    - data_access
    - legal_or_regulatory_decision
  non_response_policy:
    low_risk: proceed_with_safe_assumption_after_24h
    medium_risk: pause_affected_work_after_24h
    high_risk: block_until_approval
    production: block_until_approval
```

### 27.5 `test_oracles.yaml`

```yaml
test_oracles:
  - id: ORACLE-001
    type: specified
    target_requirement: REQ-001
    expected_behavior: "string"
    tolerance: "exact"
    evidence_required:
      - unit_test
      - e2e_test

  - id: ORACLE-002
    type: reference
    target_requirement: REQ-002
    reference_source: "legacy_system_export.csv"
    comparison_rule: "match within 1% tolerance"

  - id: ORACLE-003
    type: judgment
    target_requirement: REQ-003
    rubric: []
    sample_size: 100
    minimum_pass_rate: 0.85
    reviewers: []
```

### 27.6 `domain_pack.yaml`

```yaml
domain_pack:
  domain_name: string
  domain_summary: string
  regulatory_authorities: []
  legal_entities: []
  jurisdictional_scope: {}
  domain_entities: []
  terminology_lexicon: []
  business_rules: []
  formulas_and_calculations: []
  standards_and_frameworks: []
  sensitivity_rules: {}
  localization_policy: {}
  domain_review_authorities:
    by_decision_type:
      regulatory: {}
      clinical: {}
      financial: {}
      safety: {}
      legal: {}
      data_privacy: {}
      ethics_or_cultural_sensitivity: {}
      technical: {}
      operational: {}
      other: {}
  domain_test_scenarios: []
  prohibited_assumptions: []
  open_domain_questions: []
```

### 27.7 `cost_and_resource_policy.yaml`

```yaml
cost_and_resource_policy:
  max_total_model_cost_usd: 0
  max_daily_model_cost_usd: 0
  max_cloud_spend_usd: 0
  max_ci_minutes_per_day: 0
  require_approval_above_forecast_percentage: 20
  model_routing:
    cheap_first_for_low_risk: true
    frontier_for_high_risk: true
    use_cached_context_when_possible: true
  stop_conditions:
    - budget_exceeded
    - repeated_failure_without_new_strategy
    - tool_loop_detected
    - model_provider_outage_extended
```

### 27.8 `prior_decisions_and_architecture_log.md`

```md
# Prior decisions and architecture log

## Purpose
Use this file when the project extends, migrates, replaces, or depends on prior work. UAID OS must treat approved prior decisions as constraints unless an authorized owner approves revisiting them.

## Existing architecture decisions
- ADR ID:
- Decision:
- Date:
- Owner:
- Status: active | superseded | rejected | unknown
- Source/evidence:
- Constraint imposed on this project:

## Rejected options that must not be rediscovered
- Option:
- Reason rejected:
- Evidence/source:
- Conditions under which it may be reconsidered:

## Migration and compatibility constraints
- Existing system/component:
- Constraint:
- Required compatibility behavior:
- Test oracle:

## Prior incidents or lessons learned
- Incident/lesson:
- Impact:
- Design implication:

## Decision ownership
- Decision type:
- Current owner/approver:
- Escalation path:
```

### 27.9 `reviewer_quality_assurance.yaml`

```yaml
reviewer_quality_assurance:
  require_different_model_route_from_builder: true
  high_risk_prefer_different_provider: true
  single_provider_fallback:
    allowed: true
    requires_human_compensation_for_high_risk: true
    required_controls:
      - different_prompt_family
      - separate_agent_blueprint
      - separate_context_policy
      - adversarial_sampling
      - blind_evidence_first_review
  planted_defect_sampling_rate: 0.05
  planted_critical_defect_sampling_rate: 0.01
  max_critical_defect_miss_rate: 0.00
  max_major_defect_miss_rate: 0.05
  max_false_approval_rate: 0.03
```

### 27.10 `risk_acceptance_record.yaml`

```yaml
risk_acceptance_record:
  id: string
  release_id: string
  issue_id: string
  severity: low | medium | high | critical
  affected_requirements: []
  reason_for_acceptance: string
  compensating_controls: []
  expiry_date: date
  owner: string
  approver: string
  approval_authority_source: approval_matrix
  rollback_or_mitigation_plan: string
  evidence_links: []
```

### 27.11 `evidence_pack_schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "uaid.evidence_pack.v1.2",
  "type": "object",
  "required": ["schema_version", "project_id", "release_id", "generated_at", "scope", "traceability", "verdict", "signatures"],
  "properties": {
    "schema_version": { "const": "uaid.evidence_pack.v1.2" },
    "project_id": { "type": "string" },
    "release_id": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "scope": { "type": "object" },
    "traceability": { "type": "array" },
    "test_results": { "type": "array" },
    "review_reports": { "type": "array" },
    "reviewer_quality_records": { "type": "array" },
    "risk_acceptances": { "type": "array" },
    "provenance_chains": { "type": "array" },
    "audit_log_hash": { "type": "string" },
    "verdict": { "enum": ["passed", "passed_with_accepted_risk", "failed", "blocked"] },
    "signatures": { "type": "array" }
  }
}
```

### 27.12 `model_change_policy.yaml`

```yaml
model_change_policy:
  pin_models_during_run: true
  forced_deprecation_behavior:
    pause_affected_runs: true
    identify_successor_candidates: true
    requalify_agents: true
    regression_compare_representative_tasks: true
    require_agent_qa_approval_to_resume: true
  provider_outage_behavior:
    short_outage: pause_or_reroute_low_risk_work
    extended_outage: trigger_stop_condition_model_provider_outage_extended
```

### 27.13 `stabilization_window_policy.yaml`

```yaml
stabilization_window:
  duration_days: 14
  owner: string
  support_owner: string
  monitored_journeys: []
  error_budget_threshold: string
  exit_criteria:
    zero_open_critical_incidents_for_days: 3
    error_budget_under_threshold: true
    monitoring_confirmed_active: true
    rollback_blockers_open: 0
    support_handover_complete: true
  closure_approver: string
```

---

## 28. Assurance and certification neutrality

UAID OS produces evidence. It does not assume who certifies that evidence.

The evidence pack may be consumed by:

- internal QA teams;
- customer security teams;
- external audit firms;
- industry certifiers;
- regulators;
- compliance officers;
- enterprise procurement teams;
- domain authorities;
- safety boards;
- internal governance committees.

The platform must export evidence in a form that independent reviewers can inspect without trusting agent claims.

### 28.1 Evidence pack export standard

UAID OS must support a stable evidence export contract so third-party reviewers can inspect release readiness without direct access to the internal agent runtime and without trusting agent summaries.

Minimum export requirements:

```yaml
evidence_pack_export:
  schema_version: uaid.evidence_pack.v1.2
  release_id: string
  project_id: string
  generated_at: iso_datetime
  scope:
    included_requirements: []
    excluded_requirements: []
    limited_scope_release: boolean
  traceability:
    requirement_task_pr_test_map: []
    acceptance_criteria_map: []
    claim_provenance_map: []
  artifacts:
    repositories: []
    pull_requests: []
    commits: []
    build_logs: []
    test_reports: []
    security_reports: []
    deployment_logs: []
    monitoring_confirmations: []
  reviews:
    reviewer_reports: []
    reviewer_quality_status: []
    reviewer_model_routes: []
    single_provider_independence_fallback: boolean
  risk:
    open_issues: []
    accepted_risks: []
    exceptions: []
  approvals:
    approval_events: []
    approvers: []
  integrity:
    content_hash: sha256
    artifact_hash_manifest: []
    signature: string
    signing_key_id: string
    immutable_log_reference: string
  auditor_access:
    mode: read_only | offline_bundle | temporary_account
    expiry: iso_datetime
    redaction_policy: string
```

Implementation requirements:

- export as JSON by default, with a published JSON Schema and versioned schema migrations;
- support optional OSCAL-compatible mapping for compliance-heavy projects when policy requires it;
- cryptographically sign the evidence pack contents or store a signed manifest of hashes for all included artifacts;
- provide read-only auditor access through scoped links, temporary audit accounts, or offline export bundles;
- include enough artifact references for independent verification without exposing secrets or tenant-private material outside policy;
- preserve schema version, export time, signing key ID, immutable log reference, and redaction policy;
- validate the export before release and fail the evidence gate if required fields are missing.

Evidence exports are claims about evidence, not replacements for evidence. An auditor must be able to follow each traceability link back to the underlying artifact or an approved redacted substitute.

---

## 29. Final operating model

UAID OS is complete only if it can do the following:

```text
1. Accept any serious project documentation package.
2. Determine whether the package is build-ready.
3. Compile missing specifications where safe.
4. Block unsafe missing decisions.
5. Create a project-specific specialist team.
6. Create new agents mechanically through governed blueprints.
7. Set up delivery tools, repositories, workflows, tests, and environments.
8. Build through controlled iterations.
9. Require independent review for every consequential output.
10. Detect shortcuts and fake completion.
11. Verify behavior through valid test oracles.
12. Track claims through Sanad-style provenance chains.
13. Produce an evidence pack as the artifact of done.
14. Control cost, authority, tenancy, security, and tool access.
15. Deploy to production only when the approved policy and evidence permit it.
16. Monitor and stabilize after launch.
```

The final rule is:

```text
If the system has enough documentation, authority, tools, test oracles, and evidence, it may autonomously build to go-live.
If it does not, it must compile, clarify, or block.
It must never fake certainty, fake completion, or fake production readiness.
```

---

## Appendix A - R5 intake completeness checklist

A project is R5 only if all of the following are true:

- product purpose is clear;
- scope and out-of-scope are explicit;
- users and roles are defined;
- permission matrix exists;
- core workflows are documented;
- functional requirements exist;
- non-functional requirements exist;
- critical acceptance criteria are approved;
- test oracles exist for critical features;
- domain pack is complete enough for implementation;
- data model and contracts are defined;
- required integrations are documented;
- environments are available;
- secrets are available through approved secret manager references;
- tool access is approved;
- autonomy policy is approved;
- human approval policy is approved;
- cost policy is approved;
- security/privacy requirements are documented;
- go-live checklist is approved;
- rollback criteria are defined;
- monitoring expectations are defined;
- risk register is reviewed;
- prior decisions and architecture log is reviewed when the project extends or migrates prior work;
- production authority is explicit.

## Appendix B - A5 production autonomy checklist

A5 is allowed only if:

- R5 intake is complete;
- production deployment target is available;
- branch protection and required checks are active;
- all critical test oracles pass;
- no unaccepted critical security findings are open;
- no unaccepted critical shortcut findings are open;
- any remaining open issues have approved risk-acceptance records;
- no unapproved generated acceptance criteria are used for critical release gates;
- cost forecast is within policy;
- rollback is verified;
- monitoring and alerts are active;
- production deployment is explicitly pre-approved under stated conditions;
- emergency stop/rollback authority exists.

## Appendix C - Platform self-defense checklist

- Documents are treated as untrusted data.
- Intake prompt injection is scanned and contained.
- Tool calls pass through Tool Broker.
- Per-agent least privilege is enforced.
- Audit logs are append-only and tamper-evident.
- Agent lineage separation is enforced.
- Reviewer QA uses planted defects and miss-rate tracking.
- Single-provider review fallback is marked as degraded and compensated.
- Cross-project learning obeys tenant-safe allowed/forbidden signal rules.
- Generated agents pass security review.
- Tenant boundaries are enforced.
- Connectors are tested and permission-scoped.
- Secrets are never exposed to agents unless absolutely required and policy permits it.
- Unsafe assumptions are blocked.
- Cost loops trigger stop conditions.
- Production overrides require explicit authority.

## Appendix D - Version 1.2 upgrade summary

Version 1.2 strengthens the standalone, domain-agnostic architecture without adding project-specific dependency.

Key upgrades:

- Reviewer quality assurance with planted defects, adversarial sampling, miss-rate tracking, reviewer replacement triggers, and explicit model/provider separation guidance.
- Archetype eval library methodology defining representative tasks, gold-answer sources, scoring rubrics, activation thresholds, and refresh policies.
- Single-provider sybil-control fallback, documented as weaker than provider separation and requiring compensating controls for high-risk reviews.
- Evidence pack export standard with JSON Schema minimum contract, signed manifest, optional compliance mapping, and read-only auditor access.
- Go-live risk-acceptance path for known acceptable open issues, with signed records and expiry/follow-up controls.
- Forced model deprecation policy for provider sunset or removal of pinned models during active runs.
- Cross-project learning boundaries that separate allowed anonymized aggregate signals from forbidden tenant-content reuse.
- Judgment-oracle thresholds labeled as illustrative defaults and tied to project risk.
- Prompt-family operational definition for true specification and review independence.
- Stabilization-window exit criteria and closure authority.
- R5 intake package expanded to 26 files with a prior-decisions and architecture-log artifact.
- Cost-envelope variance note for judgment-oracle-heavy workloads.
- Extended stop condition for model provider outages.
- Per-decision-type domain review authorities instead of a monolithic reviewer role.
- Deterministic replay added to durable runtime requirements.
- Simplified spelling convention for Al-Muhasibi locked for this core specification.

