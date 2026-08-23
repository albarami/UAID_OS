# Slice 61a — Vetted ecosystem catalog: the mechanism

> **HALTED AT THE PLAN GATE — DO NOT BUILD FROM THIS DOCUMENT.**
> v3 was REJECTED, the third consecutive reject. The standing halt condition has fired: the
> continuous run is stopped and no v4 may be written until the owner authorizes a fourth round.
> The five outstanding v3 defects are recorded in `.planning/HANDOFF.json` under
> `slice_61a_verdicts.plan`. Two of them were re-verified by the planner against PostgreSQL 16.14
> and are real: a Unicode-escaped duplicate key evades the `regexp_count` rule, and reordered
> check-result text satisfies every specified guard clause because its digest is self-consistent.
> Nothing has been built — no code, no migration, no schema. Alembic head remains `0059`.

**Seats (ruling 2026-08-23).** PLANNER = Claude seat (this document). BUILDER = Cursor Grok 4.6
Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority, probe-backed verdicts only.

**Version.** v3 (v1 REJECTED — eight defects; v2 REJECTED — seven; all fifteen accepted and fixed,
none argued down; see §8).

> **This slice does NOT satisfy the roadmap's Slice 61 exit.** It builds the catalog mechanism and
> registers nothing. The roadmap exit — "vetted connector/blueprint/reference libraries" — requires
> populated libraries and is **Slice 61b**. Claiming the exit here would be exactly the fake-done
> §2.1 forbids. The split follows the Slice 8a/8b and 14a/14b precedent and was recommended by the
> reviewer on the v1 round.

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 61 (to be split into 61a/61b at
this plan's approval). **Spec grounding.** §26.7 (l.2512–2522); §20.3 (l.2039–2044); Appendix C
l.3010, l.3012.

**Alembic.** Head is `0059` (`migrations/versions/0059_export_bundles.py:29-30`). This slice is
**`0060`**, `down_revision="0059"`, purely additive.

---

## 0. What this slice is, and what it deliberately refuses

Appendix C states two conformance claims this codebase cannot currently make. Slice 61a builds the
mechanism that will make them *provable where they are true* and *visibly false where they are
not*. It does not make them true, and it does not make them true by assertion.

One mechanism — a global, append-only, content-hash-pinned **catalog** in which **a listing is
structurally impossible without a passing vetting record bound to that exact asset version** —
applied to all three §26.7 asset classes, plus a tenant-scoped adoption ledger.

### 0.1 What grounding established

An exploration of the existing surfaces (agent `d85e7aa9-d174-4863-a12a-a412a660e14a`), **as
corrected by the v1 review**, returned five facts. Each is load-bearing.

1. **"Permission-scoped" is currently unenforced.** `ToolContract` carries five fields
   (`app/tools/registry.py:34-41`), of which `category` and `audit_level` are **inert** — read only
   inside `registry.py`'s own constructor, never consulted by the broker or by
   `ToolCallRepository.record`. The only real scoping is the per-key `agent_tool_allowlist` ledger
   (`app/repositories/tools.py:32-44`), whose `agent_id` is an unconstrained `Text` column with no
   FK (`app/models/agent_tool_allowlist.py:35`).
2. **No security-review, vetting, approval, or trust field exists on `agent_blueprints` or
   `agent_versions`** (`app/models/agent_blueprint.py:28-37`,
   `app/models/agent_version.py:43-65`), nor anywhere else in the codebase.
3. **No live connector adapter has a real-provider integration test.** *(v1 said "untested"; the
   reviewer corrected this and the correction is adopted.)* The GitHub, deploy, and monitoring
   adapters **are** exercised in CI with mocked or injected transports — they are mock-tested, not
   untested. What none of them has is a test against a real provider. The Jira adapter does not
   exist at all (`app/release/pm_connector.py:5-7`). `EnvSecretsManagerConnector` is local and does
   no network I/O.
4. **The connector orchestration is uniform but the connector protocol is not.** All six services
   share a byte-identical `_ALLOWED` tuple, the same five-step skeleton, the same
   never-a-caller-target rule, and the same `*_present: True` safe-param convention. But fetch
   signatures, return cardinality, failure-honesty policy, network/SSRF model, and authentication
   differ irreconcilably — SCM is fail-closed-on-anything while deploy/monitoring write a
   verified-negative row on transport failure (B-30-9). Those differences encode per-slice A5-gate
   semantics.
5. **`reference_intakes/README.md` exists** and pre-declares the concept in three lines; the
   directory holds **zero** reference intakes. Separately, **none of the 26 intake templates is read
   at runtime** — only two `schemas/` files are.

Fact 4 is why this slice does **not** build a unified connector abstraction: flattening six
deliberately different failure-honesty policies into one interface would destroy the property each
was built to have. Facts 1–3 are why scope and test subject are first-class, DB-checked data.

### 0.2 The vetting honesty crux — two provenance tiers, never merged

- **`system_executed_contract_test`** — the admin path ran the structural checker in-process,
  deterministically, in this transaction, and recorded its complete result set. Available **only**
  for connector contract tests, because such a test is pure structural conformance and needs no
  network.
- **`caller_supplied_unverified`** — an actor asserted an outcome and UAID recorded the assertion.
  This is the **only** tier available for blueprint security reviews and reference-intake
  constraint attestations, because no automated blueprint security scanner and no §20.3 constraint
  checker exist in this codebase.

**What the system-executed tier does and does not prove (v1 defect 1, v2 defect 2).** v1's CHECK
admitted a record claiming system execution with an empty `check_results`. The fix is structural
and is specified in §3.3: a system-executed record must carry **exactly the six uniquely-named
checks** the checker emits — each element having **exactly** the keys `{name, passed}` and no
others — its `outcome` must be **derived** from them (`passed` iff all six passed), and its
`evidence_digest` must be bound to the canonical check-result bytes (§3.3, and see the digest
correction in v2 defect 3).

Even with all of that, the honest framing is: **this provenance is admin-path app-stamped.** A
CHECK constrains *shape*, and shape cannot prove execution occurred. The reviewer's point stands
that six fabricated `passed:true` values remain admissible to anyone holding admin write access.
What is therefore proven is exactly this and no more: **a complete, well-formed, internally
consistent, digest-bound six-check result set was recorded through a path `uaid_app` cannot reach**
(§OD-61-7). It is strictly weaker than "UAID ran this", and §0.6 is worded to claim only the
former.

### 0.3 The "tested" honesty crux — subject is a required axis

Appendix C l.3012 says connectors are *tested*. Given fact 3, a single boolean "tested" would
mislead.

Every connector contract-test record carries a required `test_subject ∈ {fake, live}`, and a DB
CHECK enforces `test_subject='live' ⟹ provenance='caller_supplied_unverified'`. UAID can genuinely
execute a structural contract test against the Fake; it cannot execute one against an adapter that
would need a real provider, so a live-subject record is an assertion and is labelled as one.

Listing requires a passing **`fake`-subject, system-executed** record. That bar proves protocol
conformance and exact scope agreement. It is explicitly **not** proof that the live adapter works
against a real provider.

**`live_adapter_status` vocabulary (v1 defect 4).** v1 used `shipped_untested`, which the reviewer
showed is factually wrong. The corrected, declared-only vocabulary is:

- `absent` — no live adapter exists (the Jira case);
- `shipped_mock_tested_no_live_provider` — a live adapter exists and is exercised in CI with a
  mocked or injected transport, with no real-provider test (GitHub, deploy, monitoring);
- `shipped_local_no_network` — a live adapter exists, runs locally, and makes no network call
  (`EnvSecretsManagerConnector`).

The field is **declared and unverified** by default. The contract test performs one narrow
verification and records it as check 6: if a `live_adapter_name` is declared, it must resolve as an
attribute of the declared `protocol_module`; if `live_adapter_status='absent'`, no
`live_adapter_name` may be declared. That proves presence or absence of a symbol — nothing about
its behaviour.

### 0.4 The "permission-scoped" honesty crux — declared scope must EQUAL the observed scope

Slice 61a does **not** add an enforcement point and does **not** touch `app/tools/broker.py`. The
chokepoint already exists and is already deny-by-default (`app/tools/broker.py:186-197`).

**v1 defect 3.** v1 required only that the service's `_TOOL` be *inside* the declared `tool_scope`,
which a wide declaration satisfies trivially and which proves no least-privilege scope at all. The
corrected rule is **set equality against a code-observed set**:

The contract test parses the service module's source with `ast` and collects every
`broker_call_service` call site, extracting each `tool` argument. Each such argument must be a bare
`Name` bound to a module-level constant; a dynamic expression (an f-string, a variable parameter, a
subscript) **fails the check closed**, because a scope cannot be observed from code that computes
its tool at runtime. The resolved set must then satisfy:

```
set(observed_broker_tools) == set(declared_tool_scope)
```

Neither a wider nor a narrower declaration passes. For all six current services the observed set is
the singleton `{_TOOL}`, so the declared scope must be exactly that one tool.

**Why a naive AST scan is not enough, and what is required instead (v2 defect 5).** The reviewer
showed that an aliased import, a `getattr`, a method call, a shadowed name, or a call routed
through an imported wrapper can be invisible to a scan — and that if one *ordinary* call also
exists, the observed set can equal the declaration while a hidden call goes undisclosed. That would
make the equality claim false precisely when it matters.

Check 5 therefore **fails closed unless the module is in a form the scanner can fully account
for**. All of the following must hold:

1. `broker_call_service` is bound exactly once, by a direct
   `from app.tools.broker import broker_call_service` statement — no alias (`as`), no
   `import app.tools.broker`, no module-object attribute access.
2. The name is never rebound, shadowed, reassigned, or passed as a value anywhere in the module.
3. The module contains no `getattr`, `setattr`, `eval`, `exec`, `__import__`, or `importlib` usage.
4. **Occurrence accounting:** the count of the identifier `broker_call_service` across the parsed
   AST equals 1 (the import binding) plus the number of observed direct call sites. Any surplus
   occurrence — the signature of a hidden route — fails the check.
5. At least one direct call site is observed. An empty observed set can never satisfy a non-empty
   declared scope, so "scan found nothing" can never be mistaken for "scope is empty".

Any violation fails check 5 with a message naming the specific form encountered.

**The claim, narrowed to what is actually proven.** Even with (1)–(5), this covers **direct,
syntactically observed calls within the service module itself**. A call made by a *different*
module that the service imports is outside the scanner's reach; conditions (1)–(4) make such a
route detectable only insofar as it would have to appear in this module. So the honest claim is:
*the declared `tool_scope` equals the set of tools this service module directly brokers, in a
module whose broker access is in a fully accounted-for form.* It is **not** a whole-program
capability analysis. §0.6 is worded to that scope.

This is verification of an existing boundary, not a new one. **Refused claim:** that Slice 61a
restricts what any connector can do at runtime. It does not; the allowlist remains the sole
enforcer.

### 0.5 The §20.3 refusal — structural, not merely tested

§20.3 permits a companion library of reference intakes and then constrains it: they "must not be
embedded into the core specification and must not make the core platform dependent on a specific
industry, geography, customer, or certifier."

**v1 defect 8.** v1 enforced isolation with an import scan, which the reviewer correctly called
regression evidence rather than a structural guarantee — a generic model import, a raw SQL string,
or a dynamic import bypasses it. The corrected position has two layers:

- **Structural (the real guarantee).** The schema has **no body column**. A reference-intake asset
  stores a `content_sha256`, a bounded `domain_label`, and a bounded `source_ref` string that is
  **never fetched**. `app/ecosystem/` exposes **no callable returning intake content**. There is
  nothing to read, so no decision can depend on one. This is a property of the schema, not of a
  test.
- **Boundary (regression evidence, honestly labelled).** A test scans every core decision module —
  `app/intake/readiness.py`, `app/release/production_autonomy.py`, `app/runtime/control_loop.py`,
  `app/policy/`, `app/tools/`, `app/agents/` — for both imports of the catalog package **and raw
  occurrences of the five table names**. This catches raw SQL, which an import scan misses. It is
  regression evidence and is described as such.

Registering a reference intake remains a bibliographic act.

### 0.6 Allowed claims, verbatim

- "UAID maintains a global, append-only, content-hash-pinned catalog of connectors, agent-blueprint
  versions, and reference intakes, in which an asset version cannot be listed unless a passing
  vetting record of the kind required for its asset class is bound to that exact version."
- "For a listed connector, a complete, well-formed, digest-bound, outcome-derived **six**-check
  structural contract-test result set was recorded through the admin path, covering protocol
  conformance of the Fake, resolution of every scoped tool, exact equality between the declared
  `tool_scope` and the tools the service module directly brokers as observed from its source, and
  presence of the declared live-adapter symbol." *(This claims a recorded result set, not that
  execution occurred and not that conformance is thereby proven — see §0.2.)*
- "For a listed blueprint version, a recorded security review exists, attributed to an actor
  distinct from the version's registrant, and bound to the exact referenced `agent_versions` row."
- "A tenant's adoption of a listed asset is recorded under RLS and is auditable."

### 0.7 Refused claims, verbatim

- That a listing is an endorsement, a safety guarantee, or evidence an asset is fit for a purpose.
- That the catalog contains anything. Slice 61a registers **no** asset; the libraries are 61b.
- That the roadmap's Slice 61 exit is met, or that Appendix C l.3010 / l.3012 are now satisfied.
- That a blueprint security review was performed by a qualified human security reviewer, or that it
  found anything — the outcome is caller-supplied and unverified.
- That any connector's live adapter is tested against a real provider. None is, and one does not
  exist.
- That the `system_executed_contract_test` tier proves execution occurred, or that a listed
  connector's Fake is thereby *proven* conformant. Six fabricated passing results remain
  admissible to a holder of admin write access; what is proven is the recorded shape and the
  writing path (§0.2).
- That check 5 is a whole-program capability analysis. It covers direct calls within the service
  module, in a module whose broker access is in a fully accounted-for form (§0.4).
- That Slice 61a adds runtime restriction of connector permissions.
- That the six connectors have been generalized into a common implementation.
- That a registered reference intake influences any platform decision, or that the platform now
  depends on any industry, geography, customer, or certifier (§20.3).
- That this slice advances any Appendix-B A5 gate, changes readiness, or affects go-live.
- That `ToolContract.category` / `audit_level` became meaningful. They remain inert.

---

## 1. Frozen files — byte-identical, SHA-256 verified before and after

| File | SHA-256 |
|---|---|
| `app/tools/broker.py` | `20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57` |
| `app/tools/registry.py` | `c10023cfcbd074bb8c99e4dc0fa5a2b7de89d685820394b0902cde1ccfcc94e3` |
| `app/policy/matrix.py` | `c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f` |
| `app/agents/registry.py` | `b942a9d6a210cbe9730c0b447d20158137e3c87e2c317515b35d91cb99195964` |
| `app/release/production_autonomy.py` | `55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029` |
| `app/intake/readiness.py` | `7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26` |
| `app/runtime/control_loop.py` | `3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180` |
| `app/release/scm_connector.py` | `b0d0e41086dac11f11f95cc8cb101f2cdf6456f164f1a57497122d6dcbabb648` |
| `app/release/deploy_connector.py` | `49cd49fa21df0a7b80aa32b61f8964e07cba8b8154b7d3315a75ce74d45fcdcb` |
| `app/release/monitoring_connector.py` | `7f507ca61a90f8ea1c6620e7bc06d87ea3921a42c244b1a5946bf9d4da01c09b` |
| `app/release/secrets_connector.py` | `1105e3c3cd0a1909ba70444b5203d5ea30b1451b774f279e316526450abe86c0` |
| `app/release/pm_connector.py` | `96747244dcb2f857ed44478679e0ebc4b4307989ef4cc66e78c898d2d6bd8e03` |
| `app/release/project_repo.py` | `01ea9375a6afed9ffacba8eb7de23c99cc2f6b0cef8311ec3ff2a74efa0a84d4` |
| `app/repositories/tools.py` | `395330aa8581ccfccd52b2ab270fa81b96a33f0d8b4e013405aad378632e1ee0` |

The six connector **service** modules are also not to be modified. The contract test reads their
source read-only; it must not import-execute side effects beyond a normal module import, and must
not monkeypatch them.

---

## 2. Design

### OD-61-1 — One catalog, three asset kinds, one listing guard

Rejected: three parallel subsystems, which would triplicate the guard machinery and give three
chances to get the listing rule subtly different.

Adopted: one `catalog_assets` identity table with `asset_kind ∈ {connector, agent_blueprint,
reference_intake}`, one `catalog_vetting_records` table, one `catalog_listings` table with a single
guard, one connector-specific spec table, one tenant adoption table.

| `asset_kind` | required `vetting_kind` | required provenance | required `test_subject` |
|---|---|---|---|
| `connector` | `connector_contract_test` | `system_executed_contract_test` | `fake` |
| `agent_blueprint` | `blueprint_security_review` | `caller_supplied_unverified` | NULL |
| `reference_intake` | `reference_intake_constraint_attestation` | `caller_supplied_unverified` | NULL |

The map is code-owned in `app/ecosystem/catalog.py` and mirrored in the listing guard. A test
asserts the two agree, so they cannot drift.

### OD-61-2 — Canonical identity, DB-verifiable (v1 defect 2)

**The v1 problem.** Connector identity lives partly in `connector_catalog_specs`, *outside* the
hashed asset row, so "changing any identity field changes the hash" was not defined, let alone
proven. Blueprint labels were caller-supplied text with no DB binding to the referenced
`agent_versions` row.

**The fix.** `catalog_assets` carries `identity_canonical_json TEXT NOT NULL` — the exact bytes the
hash is taken over, produced by Python with `json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=False)`, matching `compute_content_hash`
(`app/agents/registry.py:77-94`). A plain CHECK then verifies the hash *exactly*, with no
cross-language rendering ambiguity:

```sql
content_hash = 'sha256:' || encode(sha256(convert_to(identity_canonical_json, 'UTF8')), 'hex')
```

`sha256(bytea)` is core Postgres, no extension (established at `0003_audit_log.py`).

A **DEFERRABLE** constraint trigger then rebinds the canonical bytes to the actual rows. Deferral
is sound — the constraint still fires at commit, so nothing lands unchecked — and is needed
because the connector spec row is inserted in the same transaction.

**v2 defect 4 — the rebinding must be exact, not merely present.** The reviewer showed four ways a
field-by-field `->>` comparison leaks: extra JSON keys are ignored, duplicate keys silently collapse
during `::jsonb`, `->>` coerces wrong scalar types to text, and a missing key is indistinguishable
from an explicit null. The trigger therefore enforces, in this order, before comparing anything:

1. **Exact key set.** Each `asset_kind` has a **fixed, non-optional** key list, code-owned in
   `app/ecosystem/catalog.py` and mirrored in the guard. The payload's top-level key set must equal
   it exactly — same members, same count via `jsonb_object_keys`. No optional fields exist, so
   "missing" and "explicitly null" are both simply invalid.
2. **No duplicate keys.** For each expected key `k`, `regexp_count(identity_canonical_json, '"' ||
   k || '":')` must equal 1. This inspects the raw text, before `::jsonb` collapses a duplicate,
   and closes the two-texts-one-identity gap.
3. **Exact JSON types.** Every scalar field must satisfy `jsonb_typeof(payload->'k') = 'string'`
   and `tool_scope` must satisfy `= 'array'`, checked *before* any `->>` extraction, so text
   coercion can never launder a number or boolean into a matching string.

Only then are values compared:

- **All kinds.** `asset_kind`, `asset_key`, `version_label` equal the asset columns.
- **Connector.** `protocol_module`, `protocol_name`, `fake_name`, `service_module`,
  `live_adapter_status`, `live_adapter_name`, and `tool_scope` equal the
  `connector_catalog_specs` row's columns, with `tool_scope` compared as a **sorted** jsonb array so
  declaration order is not identity.
- **Agent blueprint.** `agent_version_content_hash` equals the referenced
  `agent_versions.content_hash`; `blueprint_key` equals the blueprint reached by
  `agent_versions.blueprint_id → agent_blueprints.key`; and — added per the reviewer —
  `catalog_assets.asset_key` must itself equal `agent_blueprints.key` and
  `catalog_assets.version_label` must equal `agent_versions.version_label`. Without those two, the
  asset's own labels could drift from the version they claim to describe even while the payload
  matched the payload.
- **Reference intake.** `domain_label`, `content_sha256`, `source_ref` equal the asset columns.

Because `catalog_assets` is immutable, changing any identity field yields a **new row with a new
hash**, and every prior vetting record stays bound to the old row via the composite FK
`(asset_id, content_hash) → catalog_assets(id, content_hash)`. A changed asset therefore arrives
unvetted and unlistable. Probe D-39 proves this end to end; probes D-16…D-19c prove each rebinding
clause fires on a forged mismatch.

### OD-61-3 — Listing guard

`catalog_listings_guard()`, BEFORE INSERT, refuses unless **all** hold. Each clause raises a
distinct message so probes can tell them apart.

1. The referenced asset exists and its `content_hash` equals the listing's `asset_content_hash`.
   The composite FK enforces this; the guard re-derives it so a future FK change cannot silently
   weaken the rule.
2. The listing's **named** `vetting_record_id` row is bound to that exact `(asset_id,
   content_hash)` pair, has `outcome='passed'`, has the `vetting_kind` required for the asset's
   `asset_kind`, has the provenance required for that kind, and — for connectors —
   `test_subject='fake'`.
3. For `agent_blueprint`, the vetting record's `reviewer` differs from the asset's `registered_by`
   (§2.2, no self-review). Both are bounded non-blank text.
4. `listing_state='listed'` and `delisted_at`/`delisted_reason` are NULL on insert.

Clause 2 naming a specific record — rather than merely proving *some* qualifying record exists —
is deliberate: it makes the listing's justification explicit and auditable, and the reviewer
confirmed on the v1 round that this adds real auditability.

### OD-61-4 — Delisting, and owner-level lifecycle protection (v1 defect 5)

`catalog_listings` is SELECT/INSERT/UPDATE with **no DELETE grant**, and the guard permits exactly
one transition, `listed → delisted`, mutating only `listing_state`, `delisted_at`, and
`delisted_reason`. Same-state updates are refused. Re-listing requires a new listing row, which
re-runs the full guard. This is the `release_findings` lifecycle pattern (migration `0022`).

**The v1 gap the reviewer found:** "no DELETE grant" constrains `uaid_app` but says nothing about
the table owner `app`. So `catalog_listings` additionally gets **DELETE and TRUNCATE block
triggers** — UPDATE remains permitted precisely because the guard already constrains it. Probe D-53
covers all five tables, including this one, using the **admin** role, which holds the grants.

`UNIQUE (id, asset_id)` is the adoption FK target. A partial `UNIQUE (asset_id) WHERE listing_state
= 'listed'` allows at most one live listing per asset version — this one *is* legitimately partial,
because it has a state predicate.

### OD-61-5 — Contract test: the six checks, and its hard boundary

`run_connector_contract_test(spec)` is deterministic: no network, no DB, no LLM, no broker call. It
emits **exactly six uniquely-named checks**, always all six, each with an explicit outcome:

1. `tool_scope_shape` — non-empty, 1–16 bounded non-blank strings, no duplicates.
2. `tool_scope_resolves` — every scoped name resolves via `app.tools.registry.get_contract` (lazy
   import, as `app/agents/factory.py` already does to avoid the `app.tools` cycle).
3. `protocol_resolves` — `protocol_module`/`protocol_name` resolve and the target is a
   `typing.Protocol`.
4. `fake_conforms` — `fake_name` resolves in the same module and structurally implements every
   protocol method: present, callable, and parameter names matching.
5. `observed_scope_equals_declared` — the `ast` scan of §0.4; set equality, with a dynamic tool
   argument failing closed.
6. `live_adapter_symbol` — **iff** (v2 defect 6, which closed the reverse direction v2 left open):
   `live_adapter_status='absent'` **if and only if** `live_adapter_name IS NULL`. A shipped status
   must therefore name an adapter, and that name must resolve as an attribute of
   `protocol_module`; an `absent` status must name none. v2 enforced only `absent ⇒ NULL`, which
   let a shipped adapter claim a status while naming nothing verifiable.

Returns a frozen `ContractTestResult` carrying the six `CheckResult`s and `passed = all(...)`.

**Boundary:** this proves structural conformance, exact scope agreement, and symbol presence. It
does not execute any connector, make any request, or prove a Fake behaves like the real provider.

### OD-61-6 — Reference intakes: digest-only

Covered structurally in §0.5. A `reference_intake` asset carries `domain_label`, `content_sha256`,
and `source_ref`. No body, no parse, no resolver, no fetch.

### OD-61-7 — Trust zone: global catalogs are admin-write, `uaid_app` SELECT-only

The four global tables follow the established precedent exactly (`0007:229-234`, `0037:315-317`,
`0039:438-441`, `0047:83-86`): `REVOKE ALL … FROM PUBLIC`; `GRANT SELECT` — and only SELECT — to
`uaid_app`; append-only block triggers; writes only by admin-session module functions outside any
tenant repository. `catalog_listings` grants `uaid_app` SELECT only as well: the delist UPDATE is
admin-path, so no runtime role can list, vet, or delist.

Consequence: `uaid_app` cannot forge a `system_executed_contract_test` record, because it cannot
insert into `catalog_vetting_records` at all. Probes D-49…D-52, which run **as `uaid_app`**, confirm
this rather than assume it.

### OD-61-8 — Tenant adoption

`tenant_catalog_adoptions` is tenant-owned, RLS ENABLE+FORCE, append-only (SELECT/INSERT), with a
composite FK to `catalog_listings(id, asset_id)` and the standard `(project_id, tenant_id) →
projects` pinning. It records that a tenant adopted a listed asset. An adoption is **not** a grant:
it creates no allowlist entry, instantiates no agent, configures no connector. A guard refuses
adopting a `delisted` listing. Idempotency uses a **plain** `UNIQUE (tenant_id, project_id,
listing_id)` — v1 called it partial, which was wrong, as there is no predicate.

### OD-61-9 — Transaction, isolation, audit

Registration, vetting, listing, and delisting run on an **admin session** and are therefore not
tenant-audited, exactly as `register_blueprint`/`register_version` are not
(`app/agents/registry.py:5-9`). Adoption runs in `tenant_scope` at READ COMMITTED and **is**
audited with safe metadata only — listing id, asset kind, asset key, content hash — never
`source_ref`, never `review_notes`, never `domain_label` free text.

Registration is idempotent on `content_hash`, returning the existing row, exactly as
`register_version` is (`registry.py:162-166`).

### OD-61-10 — Downgrade refuses on a populated database (v1 defect 6)

v1's downgrade dropped five populated tables. Following the `0059` convention,
`populated_downgrade_sql` raises when **any** of the five tables holds a row. Probe D-62 covers
both halves: a populated downgrade is refused, and an empty downgrade succeeds and leaves no
pre-existing object altered.

---

## 3. Schema — migration `0060_ecosystem_catalog`, purely additive

No existing table is altered.

### 3.1 `catalog_assets` (GLOBAL, immutable append-only)

`id` UUID PK · `asset_kind` text CHECK `IN ('connector','agent_blueprint','reference_intake')` ·
`asset_key` text 1–120 non-blank · `version_label` text 1–64 non-blank · `identity_canonical_json`
text 1–8000 · `content_hash` text CHECK `~ '^sha256:[0-9a-f]{64}$'` · `registered_by` text 1–200
non-blank · `agent_version_id` UUID NULL FK → `agent_versions.id` · `domain_label` text NULL 1–120
non-blank · `content_sha256` text NULL `^sha256:[0-9a-f]{64}$` · `source_ref` text NULL 1–500
non-blank · `created_at` timestamptz `clock_timestamp()`.

- `ck_ca_hash_matches_canonical` — the `encode(sha256(convert_to(...)))` equality of OD-61-2.
- `ck_ca_kind_shape` — enforced **in both directions**: `agent_version_id` non-NULL iff
  `asset_kind='agent_blueprint'`; `domain_label`/`content_sha256`/`source_ref` all non-NULL iff
  `asset_kind='reference_intake'`; a `connector` row has all four NULL.
- `UNIQUE (content_hash)`; additive `UNIQUE (id, content_hash)` and `UNIQUE (id, asset_kind)` as
  composite FK targets; `UNIQUE (asset_kind, asset_key, version_label)`.
- `catalog_assets_identity_rebind` — the DEFERRABLE constraint trigger of OD-61-2.

### 3.2 `connector_catalog_specs` (GLOBAL, immutable append-only)

`id` UUID PK · `asset_id` UUID UNIQUE · `asset_kind` text CHECK `= 'connector'` ·
`protocol_module` 1–200 · `protocol_name` 1–120 · `fake_name` 1–120 · `service_module` 1–200 ·
`live_adapter_name` text NULL 1–120 · `live_adapter_status` text CHECK `IN ('absent',
'shipped_mock_tested_no_live_provider','shipped_local_no_network')` · `tool_scope` jsonb CHECK
`jsonb_typeof='array'` · `tool_scope_count` int CHECK `BETWEEN 1 AND 16` · `created_at`.

Composite FK `(asset_id, asset_kind) → catalog_assets(id, asset_kind)` with the `asset_kind` CHECK
pinning it to `'connector'`, so a spec can never attach to a blueprint or reference intake. A guard
enforces `tool_scope` element shape (1–16 distinct bounded non-blank strings) and
`tool_scope_count = jsonb_array_length(tool_scope)` — the `0025`/`0028` count-equality pattern.

`ck_ccs_adapter_name_iff_shipped` — the v2 defect-6 fix, an **iff** in both directions:
`live_adapter_status='absent'` if and only if `live_adapter_name IS NULL`. v2 enforced only the
forward direction, so a `shipped_*` status could name nothing and check 6 would verify no symbol.

### 3.3 `catalog_vetting_records` (GLOBAL, immutable append-only)

`id` UUID PK · `asset_id` UUID + `asset_content_hash` text, composite FK →
`catalog_assets(id, content_hash)` · `vetting_kind` text CHECK `IN ('connector_contract_test',
'blueprint_security_review','reference_intake_constraint_attestation')` · `provenance` text CHECK
`IN ('system_executed_contract_test','caller_supplied_unverified')` · `test_subject` text NULL
CHECK `IN ('fake','live')` when non-NULL · `outcome` text CHECK `IN ('passed','failed')` ·
`reviewer` text 1–200 non-blank · `check_results` jsonb CHECK `jsonb_typeof='array'` ·
`check_results_canonical_json` text NULL 1–4000 · `check_result_count` int CHECK
`BETWEEN 0 AND 16` · `evidence_digest` text NULL `^sha256:[0-9a-f]{64}$` · `created_at`.

`ck_cvr_count_matches` — **universal**, not system-only (v2 defect 2): `check_result_count =
jsonb_array_length(check_results)` for **every** row, so a caller-supplied record cannot be
internally inconsistent either.

`ck_cvr_kind_provenance_shape`, in both directions:
- `vetting_kind='connector_contract_test'` ⟹ `test_subject IS NOT NULL`;
- `vetting_kind <> 'connector_contract_test'` ⟹ `test_subject IS NULL` **and**
  `provenance='caller_supplied_unverified'` **and** `check_results='[]'::jsonb` **and**
  `check_results_canonical_json IS NULL` **and** `evidence_digest IS NULL`;
- `provenance='system_executed_contract_test'` ⟹ `vetting_kind='connector_contract_test'`
  **and** `test_subject='fake'` **and** `check_result_count=6` **and**
  `check_results_canonical_json IS NOT NULL` **and** `evidence_digest IS NOT NULL`.

**The digest binding, corrected (v2 defect 3).** v2 bound `evidence_digest` to
`check_results::text`. The reviewer disproved that on real PostgreSQL: the JSONB text rendering
inserts spaces, so `[{"name": "tool_scope_shape", "passed": true}]` and Python's
`[{"name":"tool_scope_shape","passed":true}]` hash differently — reintroducing exactly the
cross-language rendering ambiguity that OD-61-2 was designed to avoid.

The fix is to reuse the identity solution rather than invent a second one: a
`check_results_canonical_json TEXT` column holds the **Python-produced canonical bytes**
(`sort_keys=True, separators=(",",":"), ensure_ascii=False`), and a plain CHECK binds the digest to
*those* bytes with no rendering assumption on either side:

```sql
evidence_digest = 'sha256:' || encode(sha256(convert_to(check_results_canonical_json,'UTF8')),'hex')
```

**`catalog_vetting_records_guard()`, BEFORE INSERT.** For
`provenance='system_executed_contract_test'` it additionally requires:

1. `check_results_canonical_json::jsonb` equals `check_results` — the canonical text and the queryable
   column are the same document, so neither can drift from the other;
2. the six check `name` values are **exactly** the six of OD-61-5, each appearing once — no
   missing, no duplicate, no invented name;
3. every element is an object whose key set is **exactly** `{name, passed}` — no extra keys (v2
   defect 2) — with `jsonb_typeof` `string` and `boolean` respectively;
4. `outcome` is **derived**: `'passed'` iff every element's `passed` is true, else `'failed'`.

An empty, partial, padded, duplicated, invented, or extra-keyed result set is refused, and the
outcome cannot contradict the results. The six required names are code-owned in
`app/ecosystem/catalog.py` and mirrored in the guard; a test asserts they agree.

What this does **not** do, restated because it is easy to overread: six well-formed
`passed:true` elements written by a holder of admin access are admissible. The guard proves shape
and writing path, not truth (§0.2).

### 3.4 `catalog_listings` (GLOBAL; SELECT/INSERT/UPDATE, DELETE and TRUNCATE blocked)

`id` UUID PK · `asset_id` + `asset_content_hash`, composite FK → `catalog_assets(id,
content_hash)` · `vetting_record_id` UUID FK → `catalog_vetting_records.id` · `listing_state` text
CHECK `IN ('listed','delisted')` · `listed_by` text 1–200 non-blank · `delisted_at` timestamptz
NULL · `delisted_reason` text NULL 1–500 non-blank when non-NULL · `created_at`.

`UNIQUE (id, asset_id)`; partial `UNIQUE (asset_id) WHERE listing_state='listed'`.
`catalog_listings_guard()` implements OD-61-3 on INSERT and OD-61-4 on UPDATE, with `delisted_at`
non-NULL iff entering `delisted`.

### 3.5 `tenant_catalog_adoptions` (TENANT-owned, RLS ENABLE+FORCE, append-only)

`id` UUID PK · `tenant_id`, `project_id` composite FK → `projects(id, tenant_id)` · `listing_id` +
`asset_id` composite FK → `catalog_listings(id, asset_id)` · `adopted_by` text 1–200 non-blank ·
`created_at`. RLS `tenant_isolation` with the standard predicate; `GRANT SELECT, INSERT` only;
plain `UNIQUE (tenant_id, project_id, listing_id)`; guard refuses a `delisted` listing.

### 3.6 Downgrade

Per OD-61-10 (probe D-62): refuse when populated; otherwise drop the five tables and their guards
in FK order.
No pre-existing object is altered, so nothing needs restoring.

---

## 4. Code layout (500-line house cap)

`app/ecosystem/__init__.py` · `catalog.py` (pure enums, the required-vetting map, the six check
names, bounds, `compute_asset_identity` returning canonical JSON + hash, validators) ·
`contract_test.py` (the six checks incl. the `ast` scan) · `catalog_db_checks.py` (shared `NAME,
SQL` tuples, the `app/ops/db_checks.py` convention) · `catalog_ddl.py`
(`install_catalog_guards`/`drop_catalog_guards`/`populated_downgrade_sql`, the `0059` convention) ·
`app/models/ecosystem_catalog.py` · `app/repositories/catalog_admin.py` ·
`catalog_reads.py` · `catalog_adoptions.py` · `migrations/versions/0060_ecosystem_catalog.py`.

Tests: `tests/ecosystem_catalog_support.py`, `test_ecosystem_catalog.py`,
`test_ecosystem_catalog_db.py`, `test_ecosystem_catalog_checks.py`,
`test_ecosystem_catalog_guards.py`, `test_ecosystem_catalog_migrate.py`.

Split any module approaching 500 lines and say so in the build report.

---

## 5. Tests

Probes marked **(runtime role)** must execute through a session bound to `rls_engine` as
`uaid_app`, after committed admin seeding — the Slice-60 lesson that an admin-fixture probe does
not establish what the runtime role can do.

**Pure — contract test (D-1…D-9).** D-1 a well-formed spec passes all six checks. D-2 empty
`tool_scope` fails. D-3 duplicates fail. D-4 a name absent from `TOOL_REGISTRY` fails. D-5 a
non-`Protocol` target fails. D-6 a Fake missing a method fails. D-7 a Fake with mismatched
parameter names fails. D-8 a declared scope **wider** than observed fails, naming the extra tool;
D-8b a scope **narrower** than observed fails, naming the missing tool — set equality in both
directions (§0.4). D-9 a service module whose `broker_call_service` tool argument is a dynamic
expression fails closed.

**Pure — real connectors (D-10).** For each of the six real services, build its true spec and
assert the contract test passes with all six checks. A live regression: renaming a protocol method
or changing a `_TOOL` breaks it.

**Pure — broker-access accountability (D-10a…D-10f), the v2 defect-5 probes.** Each fixture is a
synthetic service module that *does* contain one ordinary observable call, so a scan that merely
collected direct calls would produce a set equal to the declaration and pass. Check 5 must fail
each one, naming the form: D-10a an aliased import (`from … import broker_call_service as _b`);
D-10b a module-object call (`import app.tools.broker` then `app.tools.broker.broker_call_service(…)`);
D-10c a `getattr`-routed call; D-10d the name rebound or shadowed later in the module; D-10e a
surplus bare occurrence of the identifier that is neither the import nor an observed call site
(occurrence accounting). D-10f: a module with **zero** direct calls fails rather than reporting an
empty observed set.

**Pure — identity and validators (D-11…D-15).** D-11 `compute_asset_identity` is stable across
input key order and matches the `agent_versions` canonicalization convention. D-12 changing any
identity field changes the hash. D-13 `tool_scope` order does not change the hash (sorted). D-14
bounds/blank validators reject whitespace-only text on every bounded field. D-15 the
required-vetting map and the six check names are exhaustive over their enums and agree with the
guard's mirrored lists (no drift, no default branch).

**DB — identity rebinding (D-16…D-19c).** Forge, by direct admin SQL, an asset whose
`identity_canonical_json` disagrees with the row for: D-16 `asset_key`; D-17 a connector spec field
(`tool_scope` with an extra element); D-18 `agent_version_content_hash` versus the referenced
`agent_versions` row; D-19 `content_sha256` for a reference intake. Each is refused by the
deferrable rebind trigger, and D-17 must be refused **at commit**, proving deferral works.

The v2 defect-4 probes, each of which v2's field-by-field comparison would have admitted: D-19a an
**extra** top-level key in the payload is refused by the exact-key-set rule; D-19b a **duplicate**
key in the raw canonical text — where the later value matches the row and the earlier does not — is
refused by the `regexp_count` rule **before** `::jsonb` collapses it; D-19c a field whose JSON type
is a number or boolean rather than a string is refused by the `jsonb_typeof` rule, not laundered
through `->>` text coercion. D-19d: for a blueprint asset, `asset_key ≠ agent_blueprints.key` and
`version_label ≠ agent_versions.version_label` are each refused, even when the payload internally
agrees with itself.

**DB — system-execution shape (D-20…D-25b).** D-20 a `system_executed_contract_test` record with
`check_results='[]'` is refused (the exact v1 defect). D-21 five checks instead of six is refused.
D-22 six checks with a duplicated name is refused. D-23 six checks with an invented name is
refused. D-24 `outcome='passed'` while one check is `passed:false` is refused (outcome is derived).
D-25 a wrong `evidence_digest` is refused.

The v2 defect-2 and defect-3 probes: D-25a an element carrying an **extra key** beyond
`{name, passed}` is refused. D-25b `check_results_canonical_json` that does not parse to the same
document as `check_results` is refused — and, as the direct regression on the rendering defect, a
record whose digest was computed over PostgreSQL's `check_results::text` rendering rather than the
Python canonical bytes is refused, with the test asserting the two byte strings genuinely differ so
it cannot pass vacuously. D-25c a Unicode-bearing check name round-trips correctly under
`ensure_ascii=False`, and key-order variation in the submitted canonical text is refused rather
than silently normalized.

**DB — provenance CHECK (D-26…D-29).** D-26 a `blueprint_security_review` claiming
`system_executed_contract_test` is refused. D-27 a contract test with `test_subject='live'` and
system-executed provenance is refused. D-28 a non-contract-test record with non-empty
`check_results` is refused. D-29 a contract test with NULL `test_subject` is refused.

**DB — the repository will not forge execution (D-30).** Call `record_vetting` directly asking for
`system_executed_contract_test` with a caller-supplied outcome. Refused at the Python layer; only
`record_contract_test`, which actually runs the checker, may write that tier. Assert no row landed.

**DB — listing guard (D-31…D-38).** D-31 listing a connector with a passing fake system-executed
record succeeds. D-32 no vetting record is refused. D-33 a `failed` record is refused. D-34 a
connector citing a `live`-subject record is refused. D-35 a blueprint citing a contract-test record
is refused. D-36 a blueprint whose reviewer equals `registered_by` is refused (§2.2). D-37 a record
bound to a different `content_hash` is refused — assert the **guard** clause fires, not only the
FK. D-38 two live listings for one asset version are refused by the partial unique index.

**DB — re-vetting on change (D-39).** Register v1, vet, list. Register the same `asset_key` with a
changed identity field, producing a new hash. List the new row citing the **old** record: refused.

**DB — delist lifecycle (D-40…D-43).** D-40 `listed → delisted` succeeds and sets `delisted_at`.
D-41 `delisted → listed` is refused. D-42 mutating any other column during delist is refused. D-43
a same-state update is refused.

**DB — adoption (D-44…D-48).** D-44 adopting a listed asset succeeds and is audited with safe
metadata only — assert the payload carries no `source_ref`, no `review_notes`, no `domain_label`
free text. D-45 adopting a delisted listing is refused. D-46 adoption is idempotent. D-47
**(runtime role)** cross-tenant adoption is invisible under RLS. D-48 adoption creates **no**
`agent_tool_allowlist` row and **no** `agent_instances` row — counts unchanged before and after.

**DB — trust zone (D-49…D-52) (runtime role).** D-49 `uaid_app` cannot INSERT into any of the four
global tables. D-50 `uaid_app` cannot UPDATE `catalog_listings`. D-51 `uaid_app` cannot UPDATE or
DELETE any global catalog row. D-52 the `pg_catalog` privilege query confirms `uaid_app` holds
SELECT and nothing else on all four global tables, and SELECT+INSERT on `tenant_catalog_adoptions`
with RLS **enabled and forced**.

**DB — lifecycle protection (D-53).** UPDATE, DELETE, and TRUNCATE are blocked by **trigger** on
`catalog_assets`, `connector_catalog_specs`, `catalog_vetting_records`, and
`tenant_catalog_adoptions`; DELETE and TRUNCATE are blocked by trigger on `catalog_listings` while
its one permitted UPDATE still works. Probe with the **admin** role, which holds the grants — this
is the v1 defect-5 fix and a grant-only test would not catch it.

**DB — spec shape (D-54…D-56b).** D-54 `tool_scope_count` disagreeing with
`jsonb_array_length(tool_scope)` is refused. D-55 a non-array or non-string-element `tool_scope` is
refused. D-56 a spec attached to a non-connector asset is refused. The v2 defect-6 probes, both
directions of the iff: D-56a `live_adapter_status='absent'` carrying a `live_adapter_name` is
refused; D-56b a `shipped_*` status with `live_adapter_name IS NULL` is refused — the direction v2
left open, which would have let a "shipped" adapter name nothing and pass check 6 vacuously.

**§20.3 isolation (D-57…D-58).** D-57 the structural property: `catalog_assets` has no body/content
column, and `app/ecosystem/` exposes no callable returning intake content. D-58 the boundary
regression: no core decision module (`app/intake/readiness.py`,
`app/release/production_autonomy.py`, `app/runtime/control_loop.py`, `app/policy/`, `app/tools/`,
`app/agents/`) imports the catalog package **or** mentions any of the five table names in a raw
string — the raw-string half is what an import scan misses.

**Non-regression (D-59…D-61).** D-59 the fourteen frozen files' SHA-256 unchanged. D-60 a
`before == after` bit-stability assertion on a **real** `ProductionAutonomyRepository` report and a
**real** `ReadinessRepository` evaluation against the DB across the whole lifecycle — register,
vet, list, adopt, delist — not by calling pure functions twice (the Slice-59 tautology lesson).
D-61 `A5_RULESET_VERSION == 'slice54.v1'`, readiness ruleset `slice20.v1`,
`can_go_live_autonomously` is the literal `False`.

**Migration (D-62).** `0060` upgrades from `0059`; a **populated** downgrade is refused
(OD-61-10); an **empty** downgrade succeeds, removes the five tables, and alters no pre-existing
object.

---

## 6. Non-goals, restated

No change to `app/tools/broker.py`, `registry.py`, `matrix.py`, or the allowlist — no new
enforcement point, no new tool, no new A1 action. No generalized connector abstraction and no
change to any connector's failure-honesty policy. No live-provider connector test. No Jira adapter.
No automated blueprint security scanner. No §20.3 constraint checker. No reference-intake content
storage, parsing, fetching, or runtime consumption. No HTTP route. No LLM. No A5 gate movement, no
readiness change, no go-live change. **No catalog population** — that is Slice 61b.

---

## 7. Slice 61b, scheduled here so it is not lost

61a's exit is the mechanism. The roadmap's Slice 61 exit needs 61b to:

- register and list all six connectors with their true specs and corrected
  `live_adapter_status` values;
- register the existing `agent_versions` and record their blueprint security reviews;
- author at least one real reference intake under
  `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/` and register it;
- only then claim the roadmap exit, Appendix C l.3010, and l.3012.

Until 61b merges, the honest status is "catalog mechanism exists; libraries are empty."

---

## 8. Change log

**v1 → v2 (eight reviewer defects, all accepted).**

1. **Forgeable system-execution shape.** A `system_executed_contract_test` record with
   `check_results='[]'` satisfied every v1 clause. Fixed: the guard requires exactly the six
   uniquely-named checks, derives `outcome` from them, and binds `evidence_digest` to their hash
   (§3.3); the provenance is relabelled admin-path app-stamped (§0.2). Probes D-20…D-25.
2. **Under-specified content hash.** Connector identity lived outside the hashed row and blueprint
   labels were unbound. Fixed: `identity_canonical_json` plus a hash CHECK plus a deferrable
   per-kind rebinding trigger (OD-61-2). Probes D-16…D-19.
3. **Trivially widened permission scope.** `_TOOL ∈ scope` is satisfied by declaring everything.
   Fixed: set **equality** against an `ast`-observed brokered-tool set, dynamic arguments failing
   closed (§0.4). Probes D-8, D-8b, D-9.
4. **`shipped_untested` factually wrong.** The adapters are mock-tested. Fixed: the corrected
   three-value vocabulary, the field declared-and-unverified, plus check 6 verifying symbol
   presence only (§0.3). Grounding fact 3 corrected in §0.1.
5. **Incomplete lifecycle protection.** No owner-level DELETE/TRUNCATE blockers on
   `catalog_listings`, and D-41 excluded it. Fixed: block triggers plus admin-role probe D-53. The
   adoption index is now a plain UNIQUE (OD-61-8).
6. **Destructive populated downgrade.** Fixed: refuse when populated, test empty separately
   (OD-61-10, D-62).
7. **Empty catalog presented as the roadmap deliverable.** Fixed: split into 61a (mechanism, this
   plan, explicitly not the exit) and 61b (population, §7).
8. **Import scan called structural.** Fixed: the structural guarantee is restated as no body
   column and no resolver; the scan is relabelled regression evidence and extended to raw table
   names across core decision modules (§0.5, D-57/D-58).

**v2 → v3 (seven reviewer defects, all accepted).**

1. **Cardinality contradiction — five checks versus six.** §0.2 said five while §3.3, OD-61-5, and
   the probes said six, so the plan did not specify one number. Six is correct — the checker emits
   six. Standardized to six in every section, and the guard's mirrored name list is now the single
   source, probed for exhaustiveness by D-15.
2. **The vetting guard still admitted under-constrained system results.** Elements could carry
   extra keys beyond `{name, passed}`, and count equality was not universal. Fixed in §3.3: exact
   two-key elements, count equality asserted in every direction, and — the part that cannot be
   fixed by shape — §0.2 now states plainly that six fabricated `passed:true` values remain
   admissible to admin write access, so the proven claim is "recorded through a path `uaid_app`
   cannot reach", not "UAID executed this". Probes D-25a, D-30.
3. **`check_results::text` is not the canonical bytes.** PostgreSQL's JSONB text rendering differs
   from Python's canonical JSON in key order and separators, so a digest computed one way and
   verified the other cannot agree; v2's binding would have been unsatisfiable or, worse, satisfied
   only by whatever the DB happened to render. Fixed: a `check_results_canonical_json TEXT` column
   carries the exact Python-produced bytes, the digest binds to those bytes, and the guard verifies
   the column parses to the same document as `check_results` — the same two-column technique the
   plan already uses for asset identity. Probe D-25b asserts the two renderings genuinely differ,
   so the regression cannot pass vacuously.
4. **Identity rebinding was not exact.** Field-by-field `->>` comparison ignored extra keys,
   silently collapsed duplicate keys at `::jsonb`, coerced wrong scalar types to matching text, and
   could not distinguish a missing key from an explicit null; blueprint labels were also compared
   only to the payload rather than to `agent_blueprints`/`agent_versions`. Fixed in OD-61-2 by three
   gates that run before any comparison — exact key set, `regexp_count` duplicate detection on the
   raw text, and `jsonb_typeof` type checks — plus direct label equality against the source rows.
   Probes D-19a…D-19d.
5. **The AST scan could miss a hidden broker call while still matching the declaration.** An
   aliased import, a module-object call, a `getattr`, a shadowed name, or a wrapper could route a
   call the scanner never sees; with one ordinary call also present, the observed set would equal
   the declaration and check 5 would pass on a false claim. Fixed in §0.4 with five conditions that
   fail closed unless the module's broker access is fully accountable — single direct import
   binding, no rebinding, no dynamic-access builtins, occurrence accounting, and at least one
   observed call — and the claim narrowed in §0.6 to direct calls within the service module.
   Probes D-10a…D-10f.
6. **`live_adapter_status` was a one-way implication.** v2 forbade a name when `absent` but allowed
   a `shipped_*` status to name nothing, which makes check 6 verify no symbol at all. Fixed:
   `ck_ccs_adapter_name_iff_shipped` enforces the iff. Probes D-56a, D-56b.
7. **Stale probe references.** Several cross-references pointed at renumbered probes. All
   references in §§0, 2, 3, 4 now resolve to the probe that actually covers the claim.
