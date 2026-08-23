# Slice 61a — Ecosystem catalog: the listing mechanism

**Seats (ruling 2026-08-23, re-confirmed by the owner).** PLANNER = Claude seat (this document).
BUILDER = Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on plan and
code, probe-backed verdicts only.

**Version.** v3 (v1 REJECTED — three defects; v2 REJECTED — two; all five accepted; see §10). This
is a **from-scratch replan** under the owner's 2026-08-23 direction after an earlier Slice 61a plan
was rejected three times (twenty defects). That earlier plan is archived at
`.planning/archive/SLICE-61A-PLAN-SUPERSEDED-v1-v3.md` and **nothing in it is carried forward**.
Halt rules are unchanged: three rejects on *this* plan (the from-scratch line, of which this is the
third version) means halt and report, not narrow again.

> **This slice does NOT satisfy the roadmap's Slice 61 exit.** It builds the listing mechanism and
> registers nothing. Slice 61b populates the catalog and also does **not** close that exit: the
> roadmap goal is a permission-scoped, tested library of security-reviewed blueprints, and those
> three capabilities remain §12 OPEN (D-8, D-9, D-10) until an evidence-backed gate exists for
> each. Claiming the exit from either 61a or 61b would be the fake-done §2.1 forbids. Precedent for
> the mechanism/population split: Slices 8a/8b and 14a/14b.

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 61 (to be split 61a/61b on
approval). **Spec grounding.** §26.7 (l.2512–2522); §20.3 (l.2039–2044); Appendix C l.3010, l.3012.

**Alembic.** Head is `0059` (`migrations/versions/0059_export_bundles.py:29-30`). This slice is
**`0060`**, `down_revision="0059"`, purely additive. No existing table is altered.

---

## 0. What this slice is

### 0.1 Why the previous plan failed, in one paragraph

Every rejected version tried to make a database constraint prove a property a database cannot
prove: that a stored text blob is a canonical serialization, that a recorded result was actually
computed, that a declared tool scope matches what code can do. Each round closed one evasion and
the next round found another — an escaped duplicate key, a reordered-but-equal JSON document, an
`ast.Attribute` the scanner never counted. The design was reaching for forgery resistance against
an adversary holding admin write access, which no CHECK constraint can deliver. This plan stops
reaching. It records only facts the datastore genuinely enforces, and labels everything else as
declared.

### 0.2 The one structural claim, and why it holds

**A listing is impossible without a passing vetting record of the required kind bound to that exact
asset row, and a connector's spec and declared scope cannot change after any vetting record exists
for that row.**

This is DB-proven, and it needs no hashing to be so.

The parent half: catalog tables are **append-only**, so a row, once written, never changes. A
row's primary key *is* therefore a stable version identity, and a vetting record carrying
`asset_id` is bound to that row by foreign key. Change any *parent-row* attribute and you get a new
row with a new id; every prior vetting record still points at the old one.

The child half, which v1 missed (reviewer defect 1). Append-only blocks UPDATE of a child row, not
INSERT of another child row. A connector's declared identity lives partly in
`connector_catalog_specs` and `connector_catalog_tool_scope`. Those children can accumulate. The
reviewer inserted a second `tool_scope` row after listing and changed `{tool.a}` into
`{tool.a, tool.b}` without a new asset id; a spec can also be absent at listing because v1's
listing guard never required one.

The freeze that closes it (OD-2, OD-13):

1. Tool-scope rows, like specs, pin `(asset_id, asset_kind)` with `asset_kind = 'connector'`.
2. Connector vetting — and therefore listing — refuses unless exactly one spec and at least one
   scope row exist.
3. Once **any** `catalog_vetting_records` row exists for an asset, INSERT into both child tables is
   refused. Failed or passing, the children freeze; a correction is a new `version_label`.
4. Both the child-insert trigger and the vetting-insert trigger take `SELECT … FROM catalog_assets
   WHERE id = … FOR UPDATE` before their existence checks, so a concurrent scope insert and a
   concurrent vetting **serialize** on the asset row. Serialization is not mutual exclusion. The
   two valid linearizations (v2 defect 1, confirmed on PostgreSQL 16): **vetting-first** — the
   vetting row commits, the later child insert raises `connector_children_frozen`; **child-first**
   — the child commits, the waiting vetting observes the completed children and also commits. In
   the child-first case both transactions succeed, and the extra child is part of the frozen
   pre-vetting set. What cannot happen is a child committing **after** a vetting row for the same
   asset. That was the v1 hole.

The mechanisms are a foreign key, an append-only trigger, a freeze trigger, a listing/vetting
guard, and a parent-row lock. Nothing exotic, and nothing that claims to resist an admin rewriting
a row.

The previous (archived) plan bolted a `content_hash` + canonical-JSON payload + deferrable
rebinding trigger on top of the parent half, to defend against direct SQL rewriting. That defence
never worked and is gone. v1 restored the parent half and stopped there; v2 adds the child freeze.

### 0.3 What the datastore proves, and what it does not

Proven by the schema, and claimable:

- **Binding** — a vetting record and a listing reference an existing asset row (foreign keys), and
  a listing's cited vetting record belongs to the asset it lists (guard clause).
- **Immutability of a written row** — no catalog row changes after insert (append-only triggers
  plus absent UPDATE/DELETE grants). The single exception is the listing's one-way
  `listed → delisted`.
- **Freeze of connector children** — once any vetting record exists for an asset, no further spec
  or scope row can be inserted (OD-13). Combined with the parent-row lock, a listed connector's
  declared spec and scope are the spec and scope that were present **when the vetting row was
  inserted**. That is not, by itself, "the children the checker ran against"; the repository
  ordering that aligns those two is OD-13's `record_contract_test` rule, separately proven.
- **Trust zone** — `uaid_app` holds SELECT and nothing else on every global catalog table, so the
  runtime role cannot register, vet, list, or delist (`0007:229-234`, `0037:315-317`,
  `0039:438-441`, `0047:83-86` precedent).
- **Shape and vocabulary** — enums, bounds, non-blank text, nullable-column iff rules, uniqueness.
- **Cardinality and derivation** — a checker record carries exactly one result row per check name,
  and its `outcome` agrees with those rows (deferred triggers, both directions, the Slice-37 and
  Slice-40 pattern).
- **Separation** — a blueprint listing's reviewer differs from the asset's registrant (§2.2).
- **Tenant isolation** — adoptions are RLS ENABLE+FORCE and invisible across tenants.

**Not proven, and therefore not claimed anywhere in this slice:**

- That a recorded checker result was actually computed. The provenance label is stamped by a
  repository function; a constraint sees shape, never invocation.
- That a declared tool scope matches what the connector can broker. No verifier exists (§7, D-8).
- That a security review happened, was competent, or found anything. It is an assertion.
- That a reference intake's recorded digest corresponds to any real document. UAID never fetches
  it.
- Anything at all against an actor holding admin write access. The trust zone bounds `uaid_app`;
  it does not bound the table owner, and this plan makes no forgery-resistance claim.

### 0.4 Content digests are integrity metadata, never authenticity

Per the owner's constraint, the one digest this slice stores — `reference_intakes.content_sha256` —
is **registrar-supplied drift-detection metadata**. UAID does not fetch the document, cannot
recompute the digest, and does not treat it as evidence of authorship, authenticity, integrity in
the cryptographic sense, or non-repudiation. It exists so a later registrar can notice that a
source document changed. No other digest, signature, or hash-chain appears in this slice, and no
part of the design depends on one.

The blueprint case needs no digest at all: `catalog_assets.agent_version_id` is a foreign key to
the already-immutable `agent_versions` row (`app/models/agent_version.py:40-65`), so the binding is
referential and real.

### 0.5 Grounding facts

Established by exploration and confirmed against the current tree:

1. **"Permission-scoped" is unenforced today.** `ToolContract` carries five fields
   (`app/tools/registry.py:34-41`) of which `category` and `audit_level` are inert — read only in
   `registry.py`'s own constructor, never consulted by the broker or by `ToolCallRepository.record`.
   The only real scoping is the per-key `agent_tool_allowlist` ledger
   (`app/repositories/tools.py:32-44`), whose `agent_id` is an unconstrained `Text` column with no
   FK (`app/models/agent_tool_allowlist.py:35`).
2. **No vetting, review, approval, or trust field exists** on `agent_blueprints` or `agent_versions`
   (`app/models/agent_blueprint.py:28-37`, `app/models/agent_version.py:43-65`), or anywhere else.
3. **No live connector adapter has a real-provider test.** GitHub, deploy, and monitoring adapters
   are exercised in CI with mocked or injected transports — mock-tested, not untested. The Jira
   adapter does not exist (`app/release/pm_connector.py:1-8`). `EnvSecretsManagerConnector` is local
   and does no network I/O.
4. **Connector orchestration is uniform; the connector protocol is not.** All six services share a
   byte-identical `_ALLOWED` tuple, the same five-step skeleton, the same never-a-caller-target
   rule, and the same `*_present: True` safe-param convention. Fetch signatures, return cardinality,
   failure-honesty policy, network model, and authentication differ irreconcilably — SCM is
   fail-closed-on-anything while deploy and monitoring write a verified-negative row on transport
   failure (B-30-9). Those differences encode per-slice A5-gate semantics, which is why this slice
   builds **no** unified connector abstraction: flattening them would destroy the property each was
   built to have.
5. **`reference_intakes/README.md` exists** and pre-declares the concept in three lines; the
   directory holds zero reference intakes. Separately, none of the 26 intake templates is read at
   runtime — only two `schemas/` files are.

### 0.6 Allowed claims, verbatim

- "UAID maintains a global, append-only catalog of connectors, agent-blueprint versions, and
  reference intakes, in which an asset version cannot be listed unless a passing vetting record of
  the kind required for its asset class references that exact asset row."
- "For a listed connector, a complete five-result contract-test record exists whose outcome agrees
  with its results, recorded through the admin path, which the runtime role cannot write."
- "For a listed blueprint version, a reviewer-asserted record labelled
  `blueprint_security_review` exists, attributed to an actor distinct from the version's
  registrant, and bound by foreign key to the exact `agent_versions` row. This is the recorded
  label, not a performed review."
- "A tenant's adoption of a listed asset is recorded under RLS and is auditable."

### 0.7 Refused claims, verbatim

- That a listing is an endorsement, a safety guarantee, or evidence of fitness for a purpose.
- That the catalog contains anything. Slice 61a registers **no** asset.
- That Slice 61b will close the roadmap Slice 61 exit. 61b populates the declared catalog; D-8,
  D-9, and D-10 remain open until an evidence-backed permission-scope verifier, a real-provider
  test, and an evidence-backed security-review gate exist.
- That the roadmap Slice 61 exit is met, or Appendix C l.3010 / l.3012 satisfied.
- That the contract-test record proves the checker ran, or that the connector is thereby conformant.
  The record proves its own shape and its writing path.
- That a reviewer-asserted record labelled `blueprint_security_review` is a security review that
  was performed, was competent, or found anything. Appendix C l.3010 remains open (§7, D-10).
- That any connector's live adapter is tested against a real provider. None is; one does not exist.
- That any connector is permission-scoped, or that a declared `tool_scope` reflects code behaviour.
- That the recorded `content_sha256` of a reference intake authenticates any document.
- That any catalog record resists forgery by an actor with admin write access.
- That Slice 61a restricts what a connector can do at runtime. The allowlist remains the sole
  enforcer and is untouched.
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

The six connector **service** modules are also not to be modified. The contract test imports them
normally and reads no source text.

---

## 2. Design decisions

### OD-1 — One catalog, three asset kinds, one listing guard

Rejected: three parallel subsystems, which would triplicate the guard machinery and give three
chances to get the listing rule subtly different. `catalog_assets` carries the common identity and
a nullable kind-specific tail governed by an iff CHECK; connector-only attributes live in a child
table.

### OD-2 — Identity is the row, not a hash — and connector children freeze at first vetting

Because every catalog table is append-only, a *written row* is immutable and its `id` is a stable
version identity. All binding is by foreign key to that id. There is no `content_hash` column on
`catalog_assets`, no canonical-JSON payload, and no rebinding trigger.

That is sufficient for columns on `catalog_assets` itself, and for the already-immutable
`agent_versions` row a blueprint points at. It is **not** sufficient for connector children. v1
stated the parent-row argument as if it covered declared scope; the reviewer disproved it by
inserting a second `tool_scope` row after listing.

**Re-vetting on a parent-row change is still automatic:** registering a changed `version_label`
inserts a new asset row; the old vetting record still references the old row, so the new one is
unvetted. Probe D-21 keeps that proof.

**Re-vetting on a child-row change is now also automatic, because the child cannot change.** See
OD-13. Probe D-21a…D-21i prove the freeze, the nonempty-spec/scope requirement, the kind pin, the
parent-row lock's two linearizations, and the repository lock-before-load.

`UNIQUE (asset_kind, asset_key, version_label)` prevents two rows claiming the same version, and
`UNIQUE (id, asset_kind)` is the composite FK target that pins both the connector spec and the
tool-scope rows to a connector.

### OD-3 — Vetting results are typed rows, not a JSON document

`catalog_vetting_check_results` holds one row per `(vetting_record_id, check_name)` with a boolean
`passed`. `check_name` is a CHECK-constrained enum of the five names in OD-5, and
`UNIQUE (vetting_record_id, check_name)` makes a duplicate structurally impossible.

This replaces the previous plan's JSONB array, canonical-text column, and digest. No serialization
exists, so no serialization can be non-canonical, and no digest can be computed over the wrong
bytes. The two questions the DB must answer — "are all five present?" and "does the outcome match?"
— are answered by counting rows, which PostgreSQL does exactly.

Two **DEFERRABLE** constraint triggers, one on each side, enforce it at commit:

- Parent side: a `checker_output_admin_recorded` record has exactly five result rows and
  `outcome = 'passed'` iff every one has `passed = true`; a `reviewer_asserted_admin_recorded`
  record has zero result rows.
- Child side: the same predicate re-evaluated after a child insert, so a result row added late
  cannot slip past a parent already validated (the Slice-37 B6/B9 lesson).

### OD-4 — Two provenance values, both admin-path, honestly named

- `checker_output_admin_recorded` — the recorded results are the output of the code-owned contract
  checker as invoked by `record_contract_test`. Available only for `connector_contract_test`.
- `reviewer_asserted_admin_recorded` — an actor asserted an outcome and UAID recorded the
  assertion. The only value available for blueprint security reviews and reference-intake
  attestations, because no evidence-backed security-review gate (verified human workflow or
  scanner — §12 D-10) and no §20.3 constraint checker exist.

Both are written through the admin path. **The difference between them is which repository function
produced the payload, and the database cannot see that difference** — the label is app-stamped.
`record_contract_test` runs the checker and stamps the first; `record_review` stamps the second and
refuses to stamp the first (probe D-15). What the DB independently establishes is narrower and
still worth having: the record has the complete, internally consistent shape its label requires,
and `uaid_app` could not have written it.

### OD-5 — The contract checker: five checks

`run_connector_contract_test(spec)` is deterministic — no network, no DB, no LLM, no broker call —
and always emits all five results:

1. `tool_scope_nonempty` — at least one declared tool, each bounded, non-blank, and distinct.
2. `tool_scope_resolves` — every declared tool name resolves through
   `app.tools.registry.get_contract` (lazy import, as `app/agents/factory.py` already does to avoid
   the `app.tools` package cycle).
3. `protocol_resolves` — `protocol_module` and `protocol_name` resolve and the target is a
   `typing.Protocol`.
4. `fake_conforms` — `fake_name` resolves in the same module and structurally implements every
   protocol method: present, callable, matching parameter names.
5. `live_adapter_symbol` — `live_adapter_status = 'absent'` **if and only if** `live_adapter_name`
   is NULL; when a name is declared it must resolve as an attribute of `protocol_module`.

Returns a frozen `ContractTestResult` with the five `CheckResult`s and `passed = all(...)`.

**Boundary.** This is structural conformance of the Fake plus symbol resolution. It executes no
connector, makes no request, and says nothing about whether a Fake behaves like the real provider.
There is deliberately **no** static analysis of broker usage — see §7, D-8.

### OD-6 — Declared tool scope is declared, and nothing more

`connector_catalog_tool_scope` records the tool names a registrar declares for a connector, one row
each. The database bounds the strings, enforces uniqueness within an asset, and pins the row to a
connector via `(asset_id, asset_kind)`. The repository additionally requires each name to resolve
in `TOOL_REGISTRY` at write time (`TOOL_REGISTRY` is a code constant, not a table, so no foreign
key is possible).

Nothing verifies that the declaration matches what the connector can actually broker. The archived
plan attempted this with AST analysis and failed twice; the capability is deferred with a §12 OPEN
entry (§7, D-8). Until it exists, the catalog's scope field is metadata, and §0.7 refuses the
permission-scoped claim outright.

A declared scope that can grow after vetting is not even a stable declaration. OD-13 freezes it.

### OD-7 — Listing guard

`catalog_listings_guard()`, BEFORE INSERT, refuses unless all hold, each with a distinct message so
probes can tell them apart:

1. The cited `vetting_record_id` references a record whose `asset_id` equals the listing's.
2. That record has `outcome = 'passed'`.
3. Its `vetting_kind` is the one required for the asset's `asset_kind`: connector →
   `connector_contract_test`, agent_blueprint → `blueprint_security_review`, reference_intake →
   `reference_intake_constraint_attestation`.
4. Its `provenance` is the one required for that kind (OD-4): connector →
   `checker_output_admin_recorded`, the other two → `reviewer_asserted_admin_recorded`.
5. For `agent_blueprint`, the record's `reviewer` differs from the asset's `registered_by` (§2.2).
6. `listing_state = 'listed'` with `delisted_at` and `delisted_reason` NULL.
7. For `connector`, `catalog_connector_children_complete(asset_id)` is true — exactly one spec
   row and at least one scope row. The same helper is the vetting-time check in OD-13. Distinct
   message: `listing_connector_children_required`.

Clause 7 is defense in depth: a connector cannot be listed unless the children present **when the
cited vetting row was inserted** are still complete. After that insert those children cannot grow.
The helper is probed directly (D-21f). The listing guard's *call* of the helper is probed
behaviourally (D-22 clause 7): an admin-only trigger-bypassed setup creates an incomplete
connector that already has a passing-shaped vetting row, then — with `catalog_listings_guard`
having remained enabled the whole time — a listing INSERT is refused with
`listing_connector_children_required`.

Naming a specific record, rather than proving some qualifying record exists, makes the listing's
justification explicit and auditable.

### OD-8 — Delisting and owner-level lifecycle protection

`catalog_listings` is the one table with an UPDATE grant, and the guard permits exactly one
transition, `listed → delisted`, mutating only `listing_state`, `delisted_at`, and
`delisted_reason`, with `delisted_at` non-NULL iff entering `delisted`. Same-state updates are
refused. Re-listing requires a new row, which re-runs the full guard. This is the `release_findings`
pattern (migration `0022`).

"No DELETE grant" constrains `uaid_app` but says nothing about the table owner, so all seven tables
— including `catalog_listings` and the tenant adoption ledger — carry DELETE and TRUNCATE **block
triggers**, and the six append-only ones additionally block UPDATE. Probe D-29 exercises these as
the **admin** role, which holds the grants; a grant-only test would not catch their absence.

### OD-9 — Tenant adoption is a record, not a grant

`tenant_catalog_adoptions` is tenant-owned, RLS ENABLE+FORCE, append-only, with a composite FK to
`catalog_listings(id, asset_id)` and the standard `(project_id, tenant_id) → projects` pinning. It
records that a tenant adopted a listed asset. It creates no allowlist entry, instantiates no agent,
and configures no connector — probe D-25 asserts both counts are unchanged across an adoption. A
guard refuses adopting a `delisted` listing. Idempotency is a plain `UNIQUE (tenant_id, project_id,
listing_id)`.

### OD-10 — Transaction, isolation, audit

Registration, vetting, listing, and delisting run on an **admin session** and are therefore not
tenant-audited, exactly as `register_blueprint` / `register_version` are not
(`app/agents/registry.py:5-9`). Adoption runs in `tenant_scope` at READ COMMITTED and **is** audited
with safe metadata only — listing id, asset kind, asset key, version label — never `source_ref`,
never `domain_label` free text.

### OD-11 — §20.3 isolation is structural

The schema has **no body column**. A reference-intake asset stores a `domain_label`, a
`content_sha256` (OD-4 metadata), and a `source_ref` string that is **never fetched**.
`app/ecosystem/` exposes **no callable returning intake content**. There is nothing to read, so no
platform decision can depend on one. That is a property of the schema, not of a test.

A companion test scans the core decision modules — `app/intake/readiness.py`,
`app/release/production_autonomy.py`, `app/runtime/control_loop.py`, `app/policy/`, `app/tools/`,
`app/agents/` — for both imports of the catalog package and raw occurrences of the seven table
names, catching raw SQL that an import scan misses. It is regression evidence and is labelled as
such, not as the guarantee.

### OD-12 — Downgrade refuses on a populated database

Following the `0059` convention, `populated_downgrade_sql` raises when **any** of the seven tables
holds a row. An empty downgrade drops them in FK order. No pre-existing object is altered, so
nothing needs restoring.

### OD-13 — Connector children freeze at first vetting (v1 defect 1)

Two BEFORE INSERT triggers, `connector_spec_freeze_guard` on `connector_catalog_specs` and
`connector_scope_freeze_guard` on `connector_catalog_tool_scope`, share one rule:

```
LOCK catalog_assets WHERE id = NEW.asset_id FOR UPDATE;
IF EXISTS (SELECT 1 FROM catalog_vetting_records WHERE asset_id = NEW.asset_id) THEN
    RAISE 'connector_children_frozen';
END IF;
```

`catalog_vetting_records_guard()`, BEFORE INSERT, for `asset_kind = 'connector'`:

```
LOCK catalog_assets WHERE id = NEW.asset_id FOR UPDATE;
IF NOT catalog_connector_children_complete(NEW.asset_id) THEN
    RAISE 'connector_children_required';
END IF;
```

`catalog_connector_children_complete(asset_id)` is a `STABLE` SQL function:
`(SELECT count(*) FROM connector_catalog_specs WHERE asset_id = $1) = 1`
AND
`EXISTS (SELECT 1 FROM connector_catalog_tool_scope WHERE asset_id = $1)`.
The listing guard's connector clause calls the same function. Probe D-21f asserts the helper
itself. Probe D-22 clause 7 asserts that the listing guard *calls* it, by refusing a listing of an
incomplete connector (setup in OD-7 / D-22).

The two locks are the same row, so a concurrent scope insert and a concurrent vetting serialize.
PostgreSQL 16 confirms both linearizations (v2 defect 1):

- **Vetting-first.** The vetting session acquires the lock, inserts, commits. The waiting scope
  insert then sees a vetting row and raises `connector_children_frozen`. Final: one vetting, no
  extra scope.
- **Child-first.** The scope session acquires the lock, inserts `tool.b`, commits. The waiting
  vetting then observes completed children and also commits. Final: two scopes, one vetting. The
  extra scope is in the frozen pre-vetting set; a subsequent `tool.c` is refused.

Both may therefore succeed. What the lock proves is that a child cannot commit **after** a vetting
row for the same asset. Probe D-21h requires both linearizations and forbids the post-vetting
child.

**`record_contract_test` lock-before-load (v2 defect 1, the application half).** The trigger
serializes *row insertion*. It does not, by itself, make the checker observe the children that
end up frozen. `record_contract_test` therefore:

1. `SELECT … FROM catalog_assets WHERE id = :asset_id FOR UPDATE`;
2. loads spec and scope from that locked state;
3. runs the checker against those loaded children;
4. inserts the vetting record (the trigger re-takes the same row lock, already held).

A concurrent extra-scope insert blocks at step 1, then either freezes (vetting-first) or is
already visible at step 2 (child-first). Either way the checker input equals the frozen set.
`record_review` does not write connector contract tests (`ck_cvr_kind_provenance`); it still takes
the same lock when the asset is a connector, so a misplaced call cannot race a child insert.
Probe D-21i.

The repository is not the freeze: a direct admin `INSERT` still hits the trigger. A failed vetting
freezes the version; a correction is a new `version_label`. That is the identity-is-the-row rule
applied to children.

---

## 3. Schema — migration `0060_ecosystem_catalog`, purely additive

Every global table: `REVOKE ALL … FROM PUBLIC`, `GRANT SELECT` and only SELECT to `uaid_app`
(`catalog_listings` included — delisting is admin-path), UPDATE/DELETE/TRUNCATE block triggers
except where OD-8 permits the one listing UPDATE.

### 3.1 `catalog_assets` (GLOBAL, append-only)

`id` UUID PK · `asset_kind` text CHECK `IN ('connector','agent_blueprint','reference_intake')` ·
`asset_key` text 1–120 non-blank · `version_label` text 1–64 non-blank · `registered_by` text 1–200
non-blank · `agent_version_id` UUID NULL FK → `agent_versions.id` · `domain_label` text NULL 1–120
non-blank · `content_sha256` text NULL CHECK `~ '^sha256:[0-9a-f]{64}$'` · `source_ref` text NULL
1–500 non-blank · `created_at` timestamptz `clock_timestamp()`.

- `ck_ca_kind_shape`, both directions: `agent_version_id` non-NULL iff
  `asset_kind='agent_blueprint'`; `domain_label`, `content_sha256`, `source_ref` all non-NULL iff
  `asset_kind='reference_intake'`; a `connector` row has all four NULL.
- `UNIQUE (asset_kind, asset_key, version_label)`; `UNIQUE (id, asset_kind)` as the connector-spec
  FK target.

### 3.2 `connector_catalog_specs` (GLOBAL, append-only)

`id` UUID PK · `asset_id` UUID + `asset_kind` text, composite FK → `catalog_assets(id, asset_kind)`
with `CHECK (asset_kind = 'connector')` · `protocol_module` / `protocol_name` / `fake_name` /
`service_module` text 1–200 non-blank · `live_adapter_status` text CHECK `IN ('absent',
'shipped_mock_tested_no_live_provider','shipped_local_no_network')` · `live_adapter_name` text NULL
1–200 non-blank · `created_at`.

- `UNIQUE (asset_id)` — one spec per connector asset.
- `ck_ccs_adapter_name_iff_shipped`, an **iff**: `live_adapter_status = 'absent'` if and only if
  `live_adapter_name IS NULL`. A shipped status must name an adapter; an absent one must not.
- `connector_spec_freeze_guard` implements OD-13.

The `live_adapter_status` vocabulary is declared and unverified, and its values are drawn from
grounding fact 3: `absent` is Jira, `shipped_mock_tested_no_live_provider` is GitHub / deploy /
monitoring, `shipped_local_no_network` is `EnvSecretsManagerConnector`. Check 5 verifies only that
a declared symbol resolves.

### 3.3 `connector_catalog_tool_scope` (GLOBAL, append-only)

`id` UUID PK · `asset_id` UUID + `asset_kind` text, composite FK → `catalog_assets(id, asset_kind)`
with `CHECK (asset_kind = 'connector')` · `tool_name` text 1–120 non-blank · `created_at`.
`UNIQUE (asset_id, tool_name)`.

Per OD-6 this is a declaration. The repository validates each name against `get_contract`; the
database bounds and de-duplicates it, and pins it to a connector so a scope row cannot attach to a
blueprint or a reference intake. `connector_scope_freeze_guard` implements OD-13.

### 3.4 `catalog_vetting_records` (GLOBAL, append-only)

`id` UUID PK · `asset_id` UUID FK → `catalog_assets.id` · `vetting_kind` text CHECK `IN
('connector_contract_test','blueprint_security_review',
'reference_intake_constraint_attestation')` · `provenance` text CHECK `IN
('checker_output_admin_recorded','reviewer_asserted_admin_recorded')` · `outcome` text CHECK `IN
('passed','failed')` · `reviewer` text 1–200 non-blank · `created_at`.

- `ck_cvr_kind_provenance`, both directions: `provenance = 'checker_output_admin_recorded'` iff
  `vetting_kind = 'connector_contract_test'`. A security review can never claim checker output, and
  a contract test can never be recorded as a bare assertion.
- `UNIQUE (id, asset_id)` as the listing FK target, so the guard's clause 1 is also structurally
  backed.

No prose column. There is no `review_notes`, no free-text finding, and therefore nothing in this
table that could carry a secret or a document excerpt.

### 3.5 `catalog_vetting_check_results` (GLOBAL, append-only)

`id` UUID PK · `vetting_record_id` UUID FK → `catalog_vetting_records.id` · `check_name` text CHECK
`IN ('tool_scope_nonempty','tool_scope_resolves','protocol_resolves','fake_conforms',
'live_adapter_symbol')` · `passed` boolean NOT NULL · `created_at`.
`UNIQUE (vetting_record_id, check_name)`.

The two DEFERRABLE constraint triggers of OD-3 live here and on the parent. The five names are
code-owned in `app/ecosystem/catalog.py` and mirrored in the CHECK; probe D-11 asserts they agree,
so the two lists cannot drift.

### 3.6 `catalog_listings` (GLOBAL; SELECT/INSERT/UPDATE, DELETE and TRUNCATE blocked)

`id` UUID PK · `asset_id` UUID FK → `catalog_assets.id` · `vetting_record_id` UUID + `asset_id`,
composite FK → `catalog_vetting_records(id, asset_id)` · `listing_state` text CHECK `IN
('listed','delisted')` · `listed_by` text 1–200 non-blank · `delisted_at` timestamptz NULL ·
`delisted_reason` text NULL 1–500 non-blank · `created_at`.

`UNIQUE (id, asset_id)` is the adoption FK target. Partial `UNIQUE (asset_id) WHERE listing_state =
'listed'` allows at most one live listing per asset version — legitimately partial, since it has a
state predicate. `catalog_listings_guard()` implements OD-7 on INSERT and OD-8 on UPDATE.

### 3.7 `tenant_catalog_adoptions` (TENANT-owned, RLS ENABLE+FORCE, append-only)

`id` UUID PK · `tenant_id`, `project_id` composite FK → `projects(id, tenant_id)` · `listing_id` +
`asset_id` composite FK → `catalog_listings(id, asset_id)` · `adopted_by` text 1–200 non-blank ·
`created_at`. RLS `tenant_isolation` with the standard predicate; `GRANT SELECT, INSERT` only; plain
`UNIQUE (tenant_id, project_id, listing_id)`; guard refuses a `delisted` listing.

---

## 4. Code layout (500-line house cap)

`app/ecosystem/__init__.py` · `catalog.py` (pure: the enums, the five check names, the
required-kind and required-provenance maps, bounds and validators) · `contract_test.py` (the five
checks) · `catalog_db_checks.py` (shared `NAME, SQL` tuples, the `app/ops/db_checks.py` convention)
· `catalog_ddl.py` (`install_catalog_guards` / `drop_catalog_guards` /
`populated_downgrade_sql` / `catalog_connector_children_complete`, the `0059` convention) · `app/models/ecosystem_catalog.py` · `app/repositories/catalog_admin.py`
(register, vet, list, delist) · `app/repositories/catalog_reads.py` ·
`app/repositories/catalog_adoptions.py` · `migrations/versions/0060_ecosystem_catalog.py`.

Tests: `tests/ecosystem_catalog_support.py`, `test_ecosystem_catalog.py`,
`test_ecosystem_catalog_db.py`, `test_ecosystem_catalog_checks.py`,
`test_ecosystem_catalog_migrate.py`.

Split any module approaching 500 lines and say so in the build report.

---

## 5. Tests

Probes marked **(runtime role)** must execute through a session bound to `rls_engine` as
`uaid_app`, after committed admin seeding — the Slice-60 lesson that an admin-fixture probe does not
establish what the runtime role can do.

**Pure — contract checker (D-1…D-8).** D-1 a well-formed spec passes all five checks. D-2 empty
scope fails. D-3 a duplicate tool name fails. D-4 a name absent from `TOOL_REGISTRY` fails. D-5 a
non-`Protocol` target fails. D-6 a Fake missing a method fails. D-7 a Fake with mismatched parameter
names fails. D-8 the adapter iff: a declared name that does not resolve fails, and an `absent`
status carrying a name fails.

**Pure — real connectors (D-9).** For each of the six real services, build its true spec and assert
the checker passes all five. A live regression: renaming a protocol method breaks it.

**Pure — vocabulary (D-10…D-11).** D-10 the required-kind and required-provenance maps are
exhaustive over the asset-kind and vetting-kind enums, with no default branch. D-11 the five check
names in `catalog.py` equal the CHECK constraint's list.

**DB — append-only identity (D-12…D-14).** D-12 an UPDATE to any `catalog_assets` column is blocked
by trigger, as the **admin** role. D-13 the same for the other five append-only tables:
`connector_catalog_specs`, `connector_catalog_tool_scope`, `catalog_vetting_records`,
`catalog_vetting_check_results`, and `tenant_catalog_adoptions`. D-14
`UNIQUE (asset_kind, asset_key, version_label)` refuses a second row for the same version.

**DB — vetting shape (D-15…D-20).** D-15 `record_review` refuses to stamp
`checker_output_admin_recorded`, and no row lands. D-16 a checker record with four result rows is
refused at commit by the parent trigger. D-17 a checker record with `outcome='passed'` while one
result is `passed=false` is refused. D-18 inserting a sixth result row late, after a valid parent,
is refused at commit by the child trigger. D-19 a duplicate `check_name` for one record is refused
by the unique constraint. D-20 an assertion-provenance record carrying any result row is refused,
and a `blueprint_security_review` claiming checker provenance is refused by
`ck_cvr_kind_provenance`.

**DB — re-vetting on change and child freeze (D-21…D-21i).** D-21 register a connector, vet it, list
it; register the same `asset_key` with a changed `version_label`, producing a new asset row;
listing the new row while citing the **old** vetting record is refused — the guard's clause 1
fires, and the composite FK independently would too. D-21a after a (passing or failing) vetting
record exists, INSERT into `connector_catalog_tool_scope` is refused with `connector_children_frozen`,
probed as the **admin** role — the exact v1 hole. D-21b the same after listing. D-21c INSERT into
`connector_catalog_specs` after vetting is refused the same way. D-21d vetting a connector with no
spec is refused (`connector_children_required`). D-21e vetting a connector with zero scope rows is
refused the same way. D-21f `catalog_connector_children_complete` returns false for an asset with
no spec, false for a spec and zero scope rows, and true for a spec plus at least one scope row —
the helper both guards call, probed directly, no trigger bypass. D-21g a `tool_scope` row whose
`asset_kind` is not `'connector'`, or that targets a blueprint asset, is refused by the composite
FK. D-21h two sessions against the same asset that already has a spec and `tool.a`: one inserts
`tool.b`, the other inserts a vetting record. Both valid linearizations must occur in the suite
(or be forced by lock ordering) and are accepted: **vetting-first** — vetting commits, `tool.b`
raises `connector_children_frozen`, final `scopes=1, vettings=1`; **child-first** — `tool.b`
commits, vetting waits then commits, final `scopes=2, vettings=1`, and a subsequent `tool.c` is
refused. The forbidden outcome is `tool.b` committing after the vetting row — the v1 hole.
D-21i `record_contract_test` takes `FOR UPDATE` on the asset **before** loading children and
running the checker; a concurrent extra-scope insert either blocks and then freezes, or is
visible to the checker. After commit, the frozen scope set equals the set the checker was given.

**DB — listing guard (D-22…D-24).** D-22 each of OD-7 clauses 1–6 is exercised separately and
refused with its own distinct message: wrong asset, failed outcome, wrong `vetting_kind`, wrong
provenance, blueprint self-review, and non-`listed` insert state. Clause 7 is a **behavioural**
probe, not a source-text assertion (v2 defect 2): as the **admin** role, disable
`connector_spec_freeze_guard`, `connector_scope_freeze_guard`, and
`catalog_vetting_records_guard` — and **not** `catalog_listings_guard`; insert a connector asset
with no spec and no scope plus a passing-shaped `connector_contract_test` /
`checker_output_admin_recorded` record and its five result rows; re-enable the three disabled
triggers; with `catalog_listings_guard.tgenabled = 'O'` throughout, INSERT a listing citing that
record; refused with `listing_connector_children_required`. Replica-role is not used: it would
also silence the listing guard. D-23 two live listings for one asset are refused by the partial
unique index. D-24 the delist lifecycle: `listed → delisted` succeeds and sets `delisted_at`;
`delisted → listed` is refused; mutating any other column during delist is refused; a same-state
update is refused.

**DB — adoption (D-25…D-26).** D-25 adopting a listed asset succeeds, is audited with safe metadata
only — assert the payload carries no `source_ref` and no `domain_label` free text — and creates
**no** `agent_tool_allowlist` row and **no** `agent_instances` row, counts unchanged before and
after. D-26 adopting a delisted listing is refused; adoption is idempotent; **(runtime role)** a
cross-tenant adoption is invisible under RLS.

**DB — trust zone (D-27…D-29).** D-27 **(runtime role)** `uaid_app` cannot INSERT into any of the
six global tables, and cannot UPDATE `catalog_listings`. D-28 **(runtime role)** the `pg_catalog`
privilege query confirms `uaid_app` holds SELECT and nothing else on all six global tables, and
SELECT+INSERT on `tenant_catalog_adoptions` with RLS enabled **and** forced. D-29 DELETE and
TRUNCATE are blocked by trigger on all seven tables, probed as the **admin** role, while the one
permitted listing UPDATE still works.

**§20.3 isolation (D-30…D-31).** D-30 the structural property: no catalog table has a body or
content column, and `app/ecosystem/` exposes no callable returning intake content. D-31 the
boundary regression: no core decision module imports the catalog package or mentions any of the
seven table names in a raw string.

**Non-regression (D-32…D-34).** D-32 the fourteen frozen files' SHA-256 unchanged. D-33 a
`before == after` bit-stability assertion on a **real** `ProductionAutonomyRepository` report and a
**real** `ReadinessRepository` evaluation against the DB across the whole lifecycle — register, vet,
list, adopt, delist — not by calling pure functions twice (the Slice-59 tautology lesson). D-34
`A5_RULESET_VERSION == 'slice54.v1'`, readiness ruleset `slice20.v1`, `can_go_live_autonomously` is
the literal `False`.

**Migration (D-35).** `0060` upgrades from `0059`; a **populated** downgrade is refused; an
**empty** downgrade succeeds, removes the seven tables, and alters no pre-existing object.

---

## 6. Documentation language, required

`CLAUDE.md` and `README.md` must describe this slice in the non-closing, non-authorizing register
Slices 55–60 use. Specifically:

- State that it **closes no spec section** and does **not** meet the roadmap Slice 61 exit, and
  that Slice 61b populates the catalog without closing that exit either.
- Carry an explicit honesty crux in the house form: *UAID maintains an append-only catalog in which
  a listing requires a passing vetting record bound to that exact asset row. This is not an
  endorsement, not proof that a checker ran, not verified permission scoping, not a real-provider
  connector test, not a performed security review, and not resistant to an actor with admin write
  access. The catalog is empty; Slice 61b populates it and still does not close the roadmap
  Slice 61 exit, which waits on §12 D-8, D-9, and D-10.*
- State that A5 stays `slice54.v1`, readiness stays `slice20.v1`, and
  `can_go_live_autonomously` remains the literal `False`.
- Record no test counts in `README.md`, per the Slice-60 convention.

---

## 7. Deferred / not claimed

Every capability dropped relative to the roadmap's Slice 61 goal or the superseded plan, with its
reason. Nothing here is silently deleted; the three that the spec actually requires get a roadmap
§12 OPEN entry with **owner = Salim**, added by the builder in the same PR.

| Capability | Reason | Disposition |
|---|---|---|
| **Verified permission scoping** — proving a connector's declared `tool_scope` equals what it can broker | Two rejected attempts showed static analysis of Python broker access is not soundly achievable at slice scope; an alias, module-object call, `getattr`, shadowed name, or imported wrapper each defeat it | **§12 OPEN D-8**, owner = Salim. Appendix C l.3012 requires it; §0.7 refuses the claim until then. Slice 61b does not close this. |
| **Real-provider connector testing** | No live-provider integration test exists for any adapter, and the Jira adapter does not exist at all (grounding fact 3) | **§12 OPEN D-9**, owner = Salim. Appendix C l.3012 says connectors are tested; mock-tested is not that. Slice 61b does not close this. |
| **Evidence-backed security-review gate** — generated agents pass security review (Appendix C l.3010). A verified human workflow or an automated scanner would both satisfy it; neither exists | Reviews today are actor assertions with no evidence that a review occurred | **§12 OPEN D-10**, owner = Salim. Not "build a scanner" — build a gate whose evidence a listing can require. Slice 61b does not close this. |
| **Proof that a recorded checker result was computed** | A constraint sees shape, never invocation; the label is app-stamped | Not separately deferrable — it is a permanent property of DB-recorded facts. Stated in §0.3 and refused in §0.7 |
| **Forgery resistance against admin write access** | Out of reach for any CHECK constraint; attempting it produced most of the twenty defects | Explicitly out of scope; refused in §0.7. Not a spec requirement — the spec's tamper-evidence requirement (§16.6) is met by the audit chain, which is untouched |
| **Canonical-serialization pinning of catalog records** | PostgreSQL has no canonical JSON serializer, so the property is unenforceable in-database | Not lost capability — typed columns and child rows replace it and are strictly stronger |
| **Catalog population** — the six connectors, the existing agent versions, at least one real reference intake | 61a is the mechanism; populating it is separable work with its own review surface | **Slice 61b**, §8. Population is not the roadmap exit. |
| **§20.3 constraint checking** — verifying a reference intake does not bind the platform to an industry or certifier | No checker exists | Structural refusal instead (OD-11): no body column, no resolver, nothing to depend on |
| **Generalized connector abstraction** | Grounding fact 4 — six deliberately different failure-honesty policies encode per-slice A5-gate semantics; flattening them would destroy properties each was built to have | Refused by design, not deferred. Recorded here so the roadmap's "generalize connectors" wording is not read as silently dropped |

---

## 8. Slice 61b, scheduled here so it is not lost

61a's exit is the mechanism. Slice 61b populates it: register and list all six connectors with
their true specs and `live_adapter_status` values; register the existing `agent_versions` and
record a reviewer-asserted `blueprint_security_review` for each; author at least one real
reference intake under `docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/` and register
it; and add a CI regression asserting each registered connector's declared scope matches its
source — as regression evidence, not a catalog fact.

**61b does not close the roadmap Slice 61 exit.** The roadmap goal is a permission-scoped, tested
library of security-reviewed blueprints (`GO-LIVE-END-TO-END-ROADMAP.md` §5 Slice 61). Those three
requirements are §12 OPEN D-8, D-9, and D-10 and stay open until an evidence-backed gate exists
for each. After 61b the honest status is "catalog mechanism exists and is populated with declared
assets; Appendix C l.3010 and l.3012, and the roadmap Slice 61 exit, remain open."

Until 61b merges, the honest status is "catalog mechanism exists; libraries are empty."

---

## 9. Non-goals, restated

No change to `app/tools/broker.py`, `registry.py`, `matrix.py`, or the allowlist — no new
enforcement point, no new tool, no new A1 action. No connector modified. No HTTP route. No LLM. No
signing, hashing-for-authenticity, or hash chain. No A5 gate movement, no readiness change, no
go-live change. No catalog population.

---

## 10. Change log

**v1 → v2 (three reviewer defects, all accepted).**

1. **Connector identity was not frozen.** Append-only parent rows do not freeze child tables. A
   second `tool_scope` row could land after listing and widen declared scope without a new asset
   id, and a spec could be absent at listing. Fixed: tool-scope rows pin `(asset_id, asset_kind)`
   with `asset_kind='connector'`; `catalog_connector_children_complete` requires exactly one spec
   and nonempty scope at vetting and at listing; INSERT into spec or scope is refused once any
   vetting record exists; both the freeze trigger and the vetting trigger `FOR UPDATE` the asset
   row. Probes D-21a…D-21h.
2. **§8 scheduled a false roadmap-exit claim.** v1 said 61b may claim the exit while D-8, D-9, and
   D-10 remain open, contradicting the roadmap's actual goal. Fixed: 61b populates the declared
   catalog; the Slice 61 exit stays open until those three gates exist. Header, §0.7, §6, §7, and
   §8 now agree.
3. **D-10 tracked a scanner, and §0.6 overclaimed a performed review.** Appendix C l.3010 requires
   generated agents to pass security review, not specifically an automated scanner; "a recorded
   security review exists" contradicted §0.7. Fixed: D-10 is an evidence-backed security-review
   gate (verified human workflow or scanner); the allowed claim is "a reviewer-asserted record
   labelled `blueprint_security_review` exists."

**v2 → v3 (two reviewer defects, all accepted).**

1. **Race outcome overspecified.** v2 said a concurrent scope insert and a concurrent vetting
   "cannot both succeed" / "exactly one commits." A PostgreSQL 16 probe with the proposed triggers
   showed the child-first linearization: scope acquires the lock, inserts `tool.b`, commits;
   vetting waits, observes completed children, also commits; final `scopes=2, vettings=1`. That is
   safe serialization, not mutual exclusion. Fixed: both linearizations are specified and probed
   (D-21h); the forbidden outcome is a child committing after a vetting row. `record_contract_test`
   locks before loading children and running the checker, so the checker input equals the frozen
   set (D-21i). The listing/vetting claim is "children present when the vetting row was inserted,"
   not "children the checker ran against," except on the repository path D-21i proves.
2. **Listing-guard clause 7 had no behavioural test.** D-21f tested the helper; a source-text
   assertion that the listing function mentions the helper name does not prove the guard calls it
   on the listed asset or refuses incomplete state. Fixed: D-22 clause 7 prepares incomplete
   connector/vetting state by disabling the freeze and vetting guards only (admin-only), restores
   them, then — with `catalog_listings_guard` enabled throughout — inserts a listing and requires
   `listing_connector_children_required`. Replica-role is not used.
