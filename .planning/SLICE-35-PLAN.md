# Slice 35 — Standalone document classifier + source/authority mapping — PLAN v2

**Status:** AWAITING PLAN REVIEW (v1 REJECTED; v2 **binds D‑35‑1…8** + fixes B1–B5) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**

> **Revision log — v1 → v2 (all five blockers accepted; every decision now BOUND):**
> - **B1 — every decision BOUND** (§1): no "proposed/recommended/alternative" language remains; D‑35‑1…8 are final choices (single‑table; exact §6.1 enum+`unknown`; minimal authority tiers *with definitions*; LLM‑assisted/inert/human‑reviewed/no‑broker; deterministic gates only; migration `0034`; store/infra‑only; latest‑wins append).
> - **B2 — cost semantics CORRECTED to "incurred provider cost"** (§3.3/§5/§8). v1 wrongly said "cost only on success." **Bound to match `extraction.py:144-180` exactly:** **NO** cost for injection‑refuse / budget‑block / provider‑exception / invalid‑or‑zero token accounting; **cost IS recorded** for **any** provider response with **valid positive tokens** — recorded **before** strict‑JSON parse and verbatim‑evidence verification, so a later parse/evidence failure (`outcome='failed'`) **still carries `cost_external_ref` + tokens**. New tests assert parse‑failure and non‑verbatim‑evidence rows **still record `model_inference` cost** (mirrors the verified 14a behavior; `test_extraction.py:587-610` asserts no‑cost **only** for zero‑token).
> - **B3 — document‑type enum BOUND to exact machine values** (§3.1): the 15 §6.1 types (snake_case) **+ `unknown`** — enumerated verbatim below.
> - **B4 — authority tiers DEFINED with decision criteria + scope disclaimer** (§3.2): `authoritative`/`supporting`/`informational`/`unknown`, each with a precise rule. **Explicitly NOT** full §3.4 source‑reliability scoring (no freshness/completeness/conflict/access‑method scoring) and **does NOT resolve authority conflicts** (`spec:303`).
> - **B5 — evidence/secret wording made HONEST** (§0/§4/§7): the table stores a **bounded verbatim evidence excerpt** (Text, like `extraction_proposal.evidence_quote`, `extraction_proposal.py:85`) — **not** "no free‑text." **Audit/logs never carry `evidence_quote`.** The "no secret value stored" claim is **DROPPED** (no token/secret denylist is added this slice — matching the 14a precedent, which stores excerpts without one; a denylist across 14a+35 is noted as possible future hardening, not this slice).

> **Track / placement.** Roadmap §5 **Track B** — Phase‑2 intake‑compiler closure (`.planning/GO-LIVE-END-TO-END-ROADMAP.md:293-307`); **OFF the A5‑gate critical path**. Closes the §26.2 named build item "document classifier" (`spec:2452`) — the **first two steps** of the §6.2 pipeline (`document classification` → `source and authority mapping`, `spec:559-560`).

> **Provenance (Sanad — verified this session):**
> - **§6.1 document types** (`spec:533-551`): 15 accepted types (enumerated in §3.1). **§6.2 pipeline** (`spec:555-572`): step 1 `document classification`, step 2 `source and authority mapping` — Slice 35's scope; downstream steps are other/existing slices.
> - **§6.4 contradiction** (`spec:594-609`) = Slice 37; **§6.5 Spec‑Gen** (`spec:611-627`) = Slice 36 — **NOT here.**
> - **§16.3 prompt injection** (`spec:1574-1587`): intake docs are **UNTRUSTED DATA** — sandboxing, instruction/data separation, **injection scanning**, content labeling, **never let document text override policy**. Binding security spine.
> - **§3.4 Sanad provenance** (`spec:289-307`): source‑reliability scoring spans **origin, authority, freshness, completeness, conflict, access method** — "authority" is **one** dimension; this slice does the **authority** axis only, as an inert LLM‑proposed/human‑reviewed tier, **not** the full §3.4 score (B4).
> - **Reuse (verified) — Slice 14a**: `extraction.py:144-209` cost/parse/evidence order (B2 anchor) + `review_proposal` distinct reviewer §2.2; `app/intake/extraction.py` (`estimate_input_tokens` [`CHARS_PER_TOKEN_CONSERVATIVE=3`,`PROMPT_OVERHEAD_TOKENS=4096`], `project_cost`, `actual_cost` [6dp], `verify_evidence`, `as_untrusted_block`); `extraction_proposals_guard` (content‑immutable, one‑way `pending→approved|rejected`, distinct reviewer, frozen‑once‑decided, accepted‑doc BEFORE‑INSERT trigger, append‑only, RLS ENABLE+FORCE); `evidence_quote` stored as Text (`extraction_proposal.py:85`); migration `0017`.
> - **Reuse (verified) — Slice 9 + LLM**: `sandbox.scan(content)->ScanResult(suspicious, markers)` (identifiers only) + `as_untrusted_block`; `DocumentRepository.get(document_id)` / `.list_usable(project_id)` (accepted‑only); `documents` (`status∈{accepted,quarantined}`, `source∈{customer_upload,api_ingest,manual}`, composite `UNIQUE(id,project_id,tenant_id)`); `LLMClient.complete(*, system,user,model,max_output_tokens,temperature=0.0)->LLMResponse(text,input_tokens,output_tokens,model,provider)` + `FakeLLMClient` (offline, records `.calls`) + `AnthropicClient` (shipped‑untested); `get_price`/empty `PRICE_CARD`/`UnpricedModelError`.
> - **Confirmed by grep — NO document classifier exists** (only §4.4 *artifact*‑classification, unrelated). Entirely new; zero duplication.

---

## 0. Goal & non-goal
- **Goal.** A **deterministic‑gated, LLM‑assisted, human‑reviewed** document classifier (Slice‑14a inert model — **NO tool broker**) that turns an **accepted** intake document into an **inert** proposed `(document_type, authority_tier, bounded verbatim evidence_quote)` classification awaiting human approval, in a tenant‑owned, RLS, immutable‑content `document_classifications` store. Implements §6.2 steps 1–2 honoring §16.3.
- **Non-goal.** `production_autonomy.py`/`readiness.py` **UNTOUCHED**; ruleset `slice31.v1`; **`before==after`**. A classification is **inert + proposed**, **never authoritative**, never auto‑promoted. **No broker / external I/O.** **No requirement extraction / contradiction / spec‑gen** (other slices). **No new spine kind. No HTTP endpoint.** The table stores a **bounded verbatim evidence excerpt** (Text); **audit/logs never carry `evidence_quote`**; **no secret/token denylist is added this slice** (so no "no‑secret" guarantee is claimed — B5). Live provider untested (Fake in CI).

## 1. BOUND decisions (B1 — final, no alternatives)
- **D‑35‑1 — Single table `document_classifications`** (run outcome + inert reviewable proposal + review lifecycle in one row; a classification is 1:1 with its run).
- **D‑35‑2 — Document‑type vocabulary = the exact §6.1 enum + `unknown`** (§3.1).
- **D‑35‑3 — Authority‑tier model = `{authoritative, supporting, informational, unknown}`, defined in §3.2.**
- **D‑35‑4 — LLM‑assisted, inert, human‑reviewed, NO broker** (Fake in CI; `AnthropicClient` shipped‑untested; injection hard‑refuse before any call; projected‑cost budget preflight; **incurred‑cost** metering per D‑35‑B2/§3.3).
- **D‑35‑5 — Deterministic gates only** (controlled vocabulary, validators, `scan` injection refuse, verbatim‑evidence verify) — **no separate heuristic pre‑classifier** this slice.
- **D‑35‑6 — Migration `0034`** (head is `0033_pm_issue_mappings`).
- **D‑35‑7 — Store/infra‑only; NO A5/readiness consumption** (`before==after`; ruleset `slice31.v1`).
- **D‑35‑8 — Re‑classify = latest‑wins append** (append‑only history; latest row wins).

## 2. Inputs (no new resolver)
Accepted documents only, via `DocumentRepository.get(document_id)` (status `accepted`; DB BEFORE‑INSERT trigger backstops). No `tool_access_manifest`/connector/credential (not a broker slice). `classified_by` is an **untrusted actor label** (not Slice‑27 verified identity — as 14a `extracted_by`).

## 3. Pure module — `app/intake/classifier.py`
### 3.1 `DOCUMENT_TYPES` (B3 — exact bound enum, 15 §6.1 + `unknown`)
`strategy_document`, `commercial_document`, `product_document`, `technical_architecture_document`, `regulatory_document`, `data_dictionary`, `diagram`, `policy`, `operational_runbook`, `design`, `source_code`, `spreadsheet`, `api_doc`, `contract`, `existing_jira_github_artifact`, **`unknown`**. An out‑of‑vocabulary / low‑confidence type ⇒ **`unknown`** (honest fail‑closed; never a guessed type).
### 3.2 `AUTHORITY_TIERS` (B4 — defined criteria + scope disclaimer)
- **`authoritative`** — the document is a **binding/governing** source for requirements: it states obligations intended to govern the build (e.g. signed **contract**, ratified **policy**, **regulatory** mandate, formally approved product/PRD requirement statements).
- **`supporting`** — the document **substantiates/elaborates** requirements but is **not itself governing** (e.g. **technical_architecture**, **design**, **data_dictionary**, **api_doc** describing how, not mandating what).
- **`informational`** — **context/background only**, not intended to govern or substantiate specific requirements (e.g. **strategy**, **commercial** overviews, **diagram** without normative content).
- **`unknown`** — authority **cannot be determined** from the document alone (fail‑closed; never guessed).
- **Scope disclaimer (BOUND).** This is the **authority axis only**, recorded as an **inert LLM‑proposed, human‑reviewed tier** — **NOT** the full §3.4 source‑reliability score (no freshness/completeness/conflict/access‑method scoring) and it **does NOT resolve authority conflicts** between documents (`spec:303`; conflict handling is §6.4 / Slice 37).
### 3.3 Cost rule (B2 — incurred provider cost, BOUND to `extraction.py:144-180`)
- **NO cost event:** `refused_injection` (no call), `blocked_by_budget` (no call), provider **exception** (`failed`, no tokens), **invalid/zero** token accounting (`failed`, no tokens).
- **Cost event recorded (`model_inference`, `external_ref=f"document_classification:{id}:provider_request"`, `quantity=input+output`, `actual_cost` 6dp):** **any** provider response with **valid positive** `input_tokens` AND `output_tokens` — recorded **BEFORE** strict‑JSON parse + verbatim‑evidence verify. Therefore a subsequent parse failure **or** non‑verbatim evidence ⇒ `outcome='failed'` **but the row still carries `cost_external_ref` + tokens** (cost was genuinely incurred).
### 3.4 Parsing/validation
`CLASSIFY_SYSTEM_PROMPT` (untrusted‑data framed; STRICT JSON `{document_type, authority_tier, evidence_quote}`; "if unsure use `unknown`"); `parse_classification(raw)->ClassificationDraft(document_type, authority_tier, evidence_quote)` (frozen); reuse `as_untrusted_block` (user block) + `verify_evidence` (verbatim substring — non‑verbatim ⇒ `failed`, **cost already recorded** per §3.3); `validate_document_type`/`validate_authority_tier` (enum, OOV⇒`unknown`); `validate_review_transition` (one‑way `pending→approved|rejected`).

## 4. Store + migration `0034`
`document_classifications` (tenant‑owned, RLS ENABLE+FORCE + `tenant_isolation`; **SELECT/INSERT/UPDATE, NO DELETE/TRUNCATE**; `created_at` `clock_timestamp()`):
- Run: `id`, `tenant_id`, `project_id`, `document_id`, `model`, `provider`, `prompt_version`, `input_tokens` (null), `output_tokens` (null), `outcome` (CHECK ∈ `{succeeded, refused_injection, blocked_by_budget, failed}`), `cost_external_ref` (null).
- Proposal (NON‑null **iff** `outcome='succeeded'`): `proposed_document_type` (CHECK ∈ §3.1), `proposed_authority_tier` (CHECK ∈ §3.2), `evidence_quote` (**Text — a bounded verbatim excerpt**, like `extraction_proposal.evidence_quote`; B5).
- Review: `review_status` (CHECK ∈ `{pending, approved, rejected, not_applicable}`; **`not_applicable` unless `succeeded`**, else `pending`→`approved|rejected`), `classified_by`, `reviewed_by` (null), `reviewed_at` (null).
- FKs: `(project_id, tenant_id)→projects`; **`(document_id, project_id, tenant_id)→documents`** + **accepted‑doc BEFORE‑INSERT trigger** (mirror `extraction_runs_require_accepted_doc`).
- **`document_classifications_guard` trigger** (mirror `extraction_proposals_guard`): INSERT shape‑by‑`outcome` — `succeeded`⇒ proposed fields + `evidence_quote` + `cost_external_ref` + tokens set, `review_status='pending'`; `refused_injection`/`blocked_by_budget`⇒ tokens/cost/proposed NULL, `review_status='not_applicable'`; `failed`⇒ proposed NULL + `review_status='not_applicable'`, and (cost_external_ref+tokens) **both set** (parse/evidence failure) **or both NULL** (exception/invalid‑token) per §3.3. UPDATE = content/identity/`outcome`/cost/tokens immutable + one‑way review (only when `succeeded`) + distinct reviewer (`reviewed_by≠classified_by`, §2.2) + `reviewed_at` on transition + frozen‑once‑decided. Block DELETE/TRUNCATE.
- Latest‑wins index `(tenant_id, project_id, document_id, created_at)` (D‑35‑8). **Additive — no change to existing tables.**

## 5. Repository — `app/repositories/classification.py`
- `ClassificationRepository.classify(*, project_id, document_id, model, llm_client, classified_by, price_card=None, max_output_tokens=2048) -> DocumentClassification` — 14a pipeline mirror with **§3.3 cost rule**: price/config validate (`get_price`, fail‑closed) → accepted‑doc gate (`DocumentRepository.get`) → injection hard‑refuse (`scan` ⇒ `refused_injection`, **no call/no cost**) → projected‑cost budget preflight (`estimate_input_tokens`/`project_cost`/`BudgetRepository`; over/absent ⇒ `blocked_by_budget`, **no call**) → `llm_client.complete` (Fake in tests; **exception ⇒ `failed`, no cost**) → token accounting (**invalid/zero ⇒ `failed`, no cost**) → **record `model_inference` cost (valid tokens)** → strict‑JSON parse (fail ⇒ `failed`, **cost kept**) → verbatim‑evidence verify (fail ⇒ `failed`, **cost kept**) → persist inert `review_status='pending'` `succeeded` row → audit safe‑metadata.
- `review_classification(*, classification_id, decision, reviewed_by) -> DocumentClassification` — requires `outcome='succeeded'` + `review_status='pending'`; one‑way `pending→approved|rejected`; **distinct reviewer** (`≠ classified_by`, §2.2); `reviewed_at`; audit safe‑metadata.
- `latest_for_document(project_id, document_id)` / `list_for_project(project_id)` reads. **No HTTP endpoint; no broker; no service class** (single LLM step).

## 6. A5 / readiness / evidence impact
- **NONE.** `production_autonomy.py`+`readiness.py` **UNTOUCHED**; ruleset `slice31.v1`; **`before==after`** regression proves recording/reviewing classifications flips no gate/level. (Roadmap traceability note `:305` is **future** — nothing consumes classifications for a gate/level here.)

## 7. Tenant / RLS / FK / audit / immutability
RLS ENABLE+FORCE + `tenant_isolation`; content/identity/`outcome`/cost/tokens immutable + one‑way review + distinct reviewer (DB‑guarded); accepted‑doc FK + trigger; **no DELETE/TRUNCATE**. **Audit safe‑metadata only** — `document_classification_id`/`project_id`/`document_id`/`model`/`provider`/`outcome`/`proposed_document_type`/`proposed_authority_tier`/`review_status`/token counts; **NEVER the document body, NEVER `evidence_quote`** (B5). The stored `evidence_quote` is a **bounded verbatim excerpt**; no "no‑secret" guarantee is claimed (no denylist this slice).

## 8. Tests (DB-backed + Docker-free, per README `:19-32`)
- **Pure:** the exact 16‑value `DOCUMENT_TYPES` enum + OOV⇒`unknown`; the 4 `AUTHORITY_TIERS`; `validate_review_transition` one‑way; strict‑JSON parse (well‑formed/malformed); verbatim‑evidence verify (substring vs non‑substring).
- **Pipeline (FakeLLMClient only):** happy path ⇒ `succeeded` pending row + verified evidence + **cost recorded**; **injection refuse** ⇒ `refused_injection`, **0 LLM calls** (`fake.calls`), **no cost**; **budget** (no budget / projected‑over) ⇒ `blocked_by_budget`, no call, no cost; provider **exception** ⇒ `failed`, no cost; **invalid/zero tokens** ⇒ `failed`, no cost; **B2 — parse failure ⇒ `failed` WITH `cost_external_ref`+tokens AND a `model_inference` cost row**; **B2 — non‑verbatim evidence ⇒ `failed` WITH cost recorded**.
- **Review:** `pending→approved|rejected`; **distinct‑reviewer refusal** (`reviewed_by==classified_by` ⇒ ValueError + DB‑guard); frozen‑once‑decided; review on non‑`succeeded` rejected.
- **DB‑guard:** bad `outcome`/type/tier/review enum rejected; **shape‑by‑`outcome`** (succeeded/refused/blocked/failed) invariants incl. the §3.3 `failed`‑cost duality; content/identity/cost/tokens immutable; append‑only no‑DELETE/TRUNCATE; FK cross‑project/tenant; accepted‑doc trigger (non‑accepted ⇒ reject); **`evidence_quote` exists as a bounded Text column** (structural — honest, B5); RLS cross‑tenant.
- **No‑A5/readiness (db):** `ProductionAutonomyRepository.evaluate` **`before==after`**; `ReadinessRepository` level unchanged; `ruleset_version=="slice31.v1"`.
- `make test` + fresh `make test-db` + alembic `0034` round‑trip; CI green.

## 9. Sequencing (TDD)
1. Pure module (enum/tiers/prompt/parse/validators + `verify_evidence` reuse) + unit tests. 2. Model + migration `0034` (CHECKs + `document_classifications_guard` incl. §3.3 `failed`‑cost duality + accepted‑doc trigger + append‑only) + DB‑guard tests. 3. `classify` pipeline (reuse sandbox/llm/cost/budget; **§3.3 cost rule**) + Fake‑LLM tests incl. **B2 parse‑fail/non‑verbatim still‑cost**. 4. `review_classification` (distinct reviewer) + review tests. 5. Reads + no‑A5/readiness `before==after`. 6. Full gates; CLAUDE.md merge‑stable entry + roadmap banner.

## 10. Must NOT claim
- That a classification is authoritative/binding (inert + proposed + human‑reviewed).
- That any A5 gate / readiness level / `can_*` flag changed (`before==after`; ruleset `slice31.v1`; go‑live false).
- That authority mapping is the full §3.4 source‑reliability score or resolves conflicts (it is the authority axis only — B4).
- That cost is "only on success" (it is **incurred‑cost**: any valid‑token provider response is metered, even if parse/evidence later fails — B2).
- That the store guarantees "no secret" (it stores a bounded verbatim excerpt with **no** denylist this slice; audit never carries it — B5).
- That requirements are extracted / contradictions detected / specs generated (other slices); that a live provider was exercised (Fake only).

## 11. Definition of done (for the eventual implementation — NOT this PLAN)
A deterministic‑gated, LLM‑assisted (Fake‑in‑CI), human‑reviewed classifier turns an **accepted** document into an **inert** `document_classifications` row — proposed `(document_type ∈ exact §6.1 enum∪`unknown`, authority_tier ∈ the 4 defined tiers, bounded verbatim `evidence_quote`)` with `outcome ∈ {succeeded, refused_injection, blocked_by_budget, failed}` — injection‑hard‑refused before any call (§16.3), budget‑preflighted (deny‑by‑default), **incurred‑cost metered** (any valid‑token response, even on later parse/evidence failure — B2), one‑way `pending→approved|rejected` under a distinct reviewer (§2.2); RLS + DB‑guard (shape‑by‑`outcome`) + accepted‑doc trigger + append‑only/no‑DELETE; **no `production_autonomy`/`readiness`/spine change**, `ruleset_version=slice31.v1`, `before==after` green; migration `0034` round‑trip; `make test` + `make test-db` + CI green; go‑live false; classifications inert + non‑authoritative; `evidence_quote` audit‑safe (never logged); **no "no‑secret" guarantee claimed**.

---
**Review note (v2):** Binds **D‑35‑1…8** and fixes **B1–B5**: every decision final (B1); **cost = incurred provider cost**, parse/evidence failure still meters `model_inference` with new tests (B2, anchored to `extraction.py:144-180` / `test_extraction.py:587-610`); **exact 16‑value document‑type enum** (B3); **authority tiers defined + §3.4 scope disclaimer** (B4); **honest evidence/secret wording** — bounded verbatim excerpt, audit‑safe, no‑secret claim dropped (B5). Reuses Slice‑9 + Slice‑14a; **no broker, no duplication**; store/infra‑only, `before==after`, migration `0034`. **No code/migration/tests/PR until this plan is approved + your explicit go.**
