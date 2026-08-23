# Slice 61b — Ecosystem catalog: declared-asset population

**Seats (ruling 2026-08-23, standing).** PLANNER = Claude seat (this document). BUILDER =
Cursor Grok 4.6 Extra High. REVIEWER = GPT-5.6 Sol, sole approval authority on plan and code,
probe-backed verdicts only. Builder never edits this plan.

**Version.** v1.

> **This slice does NOT satisfy the roadmap's Slice 61 exit.** It populates the Slice-61a listing
> mechanism with the declared connectors, every `agent_versions` row that already exists, and one
> real reference intake. After this slice the honest status is: *catalog mechanism exists and is
> populated with declared assets; Appendix C l.3010 and l.3012, and the roadmap Slice 61 exit,
> remain open.* Those three requirements stay §12 OPEN D-8, D-9, and D-10 (owner = Salim). Claiming
> the exit here would be the fake-done §2.1 forbids. Precedent: 61a §8; Slices 8a/8b and 14a/14b.

**Roadmap.** `.planning/GO-LIVE-END-TO-END-ROADMAP.md` Rev 21 §5 Slice 61b. **Spec grounding.**
§26.7 (l.2512–2522); §20.3 (l.2039–2044); Appendix C l.3010, l.3012 — cited as open, not claimed.

**Alembic.** Head is `0060` (`migrations/versions/0060_ecosystem_catalog.py`, `revision="0060"`,
`down_revision="0059"`). **This slice adds no migration.** There is no schema change. Population is
an idempotent admin-path Python function that writes through the existing Slice-61a
`CatalogAdmin` APIs. Forging passing vetting rows in SQL is refused (OD-2). A freshly migrated
database has an empty catalog until populate runs; that is honest, not a defect.

---

## 0. What this slice is

Slice 61a built an empty listing mechanism. Slice 61b is the population pass scheduled in 61a §8:
register and list the six release **services** as six connector catalog assets, with their true
specs and `live_adapter_status` values; catalog every existing `agent_versions` row with a
reviewer-asserted `blueprint_security_review`; author one real reference intake under
`docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/` and list it; add a CI regression that
the declared `tool_scope` equals the quoted `TOOL_REGISTRY` keys in that service's source file —
as **regression evidence**, not a catalog fact, not D-8.

### 0.1 Grounding facts (re-verified 2026-08-23 against `main` at `17e7fc9`)

1. **Six services, five connector modules.** `tests/ecosystem_catalog_support.py:118-174`
   already names the six true specs (`ci`, `pr`, `deploy`, `monitoring`, `secrets`, `pm`). CI and
   PR share `SCMConnector` / `FakeSCMConnector` / `GitHubSCMConnector` and differ by
   `service_module` and `tool_names`. There is no sixth connector **module**. Registering six
   **catalog assets** (one per service) is the honest identity. Collapsing CI+PR into one asset
   would mix two tool scopes onto one frozen child set.
2. **No `agent_versions` are migration-seeded.** `0007_agent_registry.py` creates empty global
   tables. Versions exist only when an admin calls `register_blueprint` / `register_version`.
   Slice 61b does **not** invent §22.2 component hashes. After a fresh migrate, listed blueprints
   = 0. Populate is total over whatever rows exist at call time.
3. **`reference_intakes/` holds only a three-line README**
   (`docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/README.md`). This slice authors one
   companion file. It is not part of the core spec and must not bind the platform to an industry,
   geography, customer, or certifier (§20.3).
4. **CatalogAdmin is the only product writer.** `register_connector` + `record_contract_test`
   (runs `run_connector_contract_test`) + `list_asset`; `register_blueprint_version` +
   `record_review` + `list_asset`; `register_reference_intake` + `record_review` + `list_asset`.
   The runtime role cannot INSERT the six global tables (61a D-27).
5. **Each service already has exactly one `_TOOL` string** matching the D-9 spec
   (`ci_evidence_service.py:26`, `pr_evidence_service.py:30`, `deploy_evidence_service.py:35`,
   `monitoring_evidence_service.py:31`, `secrets_verification_service.py:30`,
   `pm_sync_service.py:35`). Audit `action=` strings in those files are not `TOOL_REGISTRY` keys.

### 0.2 Load-bearing claim

A declared product asset is listed only by going through the Slice-61a admin path, so a listed
connector has a passing five-result contract-test record whose outcome agrees with its results,
and a listed blueprint or intake has a reviewer-asserted record of the required kind, bound to
that exact asset row. Populate does not invent a new listing rule.

### 0.3 Honesty crux (verbatim, for CLAUDE.md / README.md)

*UAID populated an append-only catalog of declared connectors, existing agent-blueprint versions,
and one reference-intake companion. A listing still requires a passing vetting record bound to
that exact asset row. This is not an endorsement, not proof that a checker ran, not verified
permission scoping, not a real-provider connector test, not a performed security review, and not
resistant to an actor with admin write access. The catalog mechanism exists and is populated with
declared assets; Appendix C l.3010 and l.3012, and the roadmap Slice 61 exit, remain open, waiting
on §12 D-8, D-9, and D-10. The DB cannot attribute a payload to the code that produced it;
provenance labels are app-stamped. A freshly migrated database is empty until populate runs.*

### 0.4 Allowed claims, verbatim

- "The six release services are listed connector assets, each bound to a passing
  `connector_contract_test` record produced by `record_contract_test`."
- "CI and PR are distinct catalog assets that share the SCM protocol/fake/adapter and differ by
  service module and declared tool scope."
- "PM's `live_adapter_status` is `absent` because no Jira adapter exists; secrets is
  `shipped_local_no_network`; the other four shipped adapters are
  `shipped_mock_tested_no_live_provider`."
- "Every `agent_versions` row present at populate time is listed with a reviewer-asserted
  `blueprint_security_review` whose reviewer is distinct from the catalog registrant. After a
  fresh migrate that set is empty."
- "One reference-intake file exists under `reference_intakes/` and is listed with a
  reviewer-asserted `reference_intake_constraint_attestation`. Its `content_sha256` is
  registrar-supplied drift metadata of the file bytes."
- "A CI check fails if a declared connector's `tool_names` disagree with the quoted
  `TOOL_REGISTRY` keys in that service's source file. That check is regression evidence, not
  proof of broker behaviour."

### 0.5 Refused claims, verbatim

- That the roadmap Slice 61 exit is met, or Appendix C l.3010 / l.3012 satisfied.
- That a listed connector is permission-scoped, or that declared `tool_scope` equals what the
  connector can broker (D-8 stays OPEN).
- That any live adapter was tested against a real provider (D-9 stays OPEN). The Jira adapter
  still does not exist.
- That a `blueprint_security_review` row is a security review that was performed, was competent,
  or found anything (D-10 stays OPEN).
- That the contract-test record proves the checker ran. Populate calls `record_contract_test`,
  which calls the checker; the persisted provenance remains `checker_output_admin_recorded`.
- That `content_sha256` authenticates the intake. It detects drift of the registered file bytes.
- That populate runs as part of `alembic upgrade`. It does not. Head stays `0060`.
- That this slice seeds `agent_blueprints` / `agent_versions`. It catalogs rows; it does not
  create them.
- That adoption grants tools, instances, or runtime authority. Adoption is untouched.
- That this slice advances any Appendix-B A5 gate, changes readiness, or affects go-live.
- That the six connectors were generalized into a common implementation.
- That a registered reference intake influences any platform decision, or that the platform now
  depends on any industry, geography, customer, or certifier (§20.3).
- That a quoted-string CI regression is an AST scan, a soundness proof, or D-8.

---

## 1. Frozen files — byte-identical, SHA-256 verified before and after

Same fourteen files as Slice 61a §1, re-hashed on `main` @ `17e7fc9`:

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

The six connector **service** modules are also not to be modified. The scope-literal regression
**reads** their source as text from tests / `catalog_declared.py`; it does not rewrite them.

`app/ecosystem/catalog.py`, `contract_test.py`, `catalog_ddl.py`, `catalog_db_checks.py`,
`catalog_admin.py`, and migration `0060` are not frozen. Populate may add read helpers to
`catalog_reads.py` and must not add a second writer beside `catalog_admin.py`.

---

## 2. Design decisions

### OD-1 — Six catalog connector assets, one per release service

Rejected: five assets (one per connector module), which would freeze CI and PR onto one
`tool_scope` set. Rejected: inventing a sixth connector module.

Stable identity, all `asset_kind='connector'`, `version_label='v1'`:

| `asset_key` | `service_module` | `protocol_module` / `protocol_name` / `fake_name` | `live_adapter_status` / `live_adapter_name` | `tool_names` |
|---|---|---|---|---|
| `ci_evidence` | `app.release.ci_evidence_service` | `app.release.scm_connector` / `SCMConnector` / `FakeSCMConnector` | `shipped_mock_tested_no_live_provider` / `GitHubSCMConnector` | `source_control.read_branch_protection` |
| `pr_evidence` | `app.release.pr_evidence_service` | same SCM triple | same | `source_control.read_pull_request` |
| `deploy_evidence` | `app.release.deploy_evidence_service` | `app.release.deploy_connector` / `DeployTargetConnector` / `FakeDeployTargetConnector` | `shipped_mock_tested_no_live_provider` / `GenericHttpsDeployTargetConnector` | `deployment.read_target_status` |
| `monitoring_evidence` | `app.release.monitoring_evidence_service` | `app.release.monitoring_connector` / `MonitoringConnector` / `FakeMonitoringConnector` | `shipped_mock_tested_no_live_provider` / `GenericMonitoringApiConnector` | `monitoring.read_status` |
| `secrets_verification` | `app.release.secrets_verification_service` | `app.release.secrets_connector` / `SecretsManagerConnector` / `FakeSecretsManagerConnector` | `shipped_local_no_network` / `EnvSecretsManagerConnector` | `secrets.verify_reference` |
| `pm_issues` | `app.release.pm_sync_service` | `app.release.pm_connector` / `IssueTrackerConnector` / `FakeIssueTrackerConnector` | `absent` / `NULL` | `pm.read_issues` |

These values are copied from the 61a D-9 specs (`tests/ecosystem_catalog_support.py:118-174`).
They become the code-owned `DECLARED_CONNECTORS` mapping, keyed by `asset_key`.
`tests/ecosystem_catalog_support.py:real_connector_specs()` becomes a thin wrapper that returns
the same six `ConnectorSpecInput` values under the existing short keys
`{"ci","pr","deploy","monitoring","secrets","pm"}` so 61a D-9 keeps passing and cannot drift
from populate. P-1 asserts both dicts expose equal specs (field-for-field) and that the
wrapper's short keys map 1:1 onto the six `asset_key`s above.

### OD-2 — One writer: `populate_declared_catalog` calls CatalogAdmin; no SQL seed; no migration

Rejected: Alembic `0061` INSERTs of passing `catalog_vetting_check_results`. That would bypass
`run_connector_contract_test` and mint `checker_output_admin_recorded` rows the checker never
emitted.

Rejected: a sync reimplementation of CatalogAdmin inside `upgrade()`. Two writers drift.

Alembic `upgrade()` in this repo runs under `connection.run_sync` (`migrations/env.py:67-68`).
The catalog admin API is async. This slice does not add a nested event loop or a sync twin.

Populate is therefore a Python function:

```python
async def populate_declared_catalog(session: AsyncSession) -> PopulateReport
```

- Admin session only (same trust zone as `register_connector`).
- One transaction. If any declared connector's checker result is not `passed`, raise
  `CatalogPopulateError` and let the transaction roll back. Nothing listed.
- Idempotent on `(asset_kind, asset_key, version_label)`:
  - missing → register → vet → list
  - present, not listed → vet if needed → list citing the passing record
  - present and latest listing is `listed` → skip writes; still include in the report
- Does not delist. Does not change `version_label` this slice (`v1` is frozen).
- Actors (bounded text, distinct where §2.2 requires it):

  | Role | Value |
  |---|---|
  | connector `registered_by` / `listed_by` | `slice61b.catalog_populate` |
  | contract-test `reviewer` | `slice61b.contract_checker` |
  | blueprint `registered_by` / `listed_by` | `slice61b.catalog_populate` |
  | blueprint `reviewer` | `slice61b.blueprint_review_asserted` |
  | intake `registered_by` / `listed_by` | `slice61b.catalog_populate` |
  | intake `reviewer` | `slice61b.intake_attestor` |

`record_review` already refuses checker provenance and, for blueprints, the listing guard
already refuses self-review (`listing_blueprint_self_review`) when reviewer equals
`registered_by`. The actor table above is distinct by construction. Probe P-18 asserts
`reviewer != registered_by` on the persisted rows.

`make catalog-populate` runs the function against `ADMIN_DATABASE_URL`. `make migrate` and
`make test-db-migrate` stay schema-only. Tests call populate explicitly. A post-migrate
pre-populate DB remains empty (P-8).

### OD-3 — Blueprints: catalog existing rows; do not invent versions

```python
SELECT v.id, v.version_label, b.key
FROM agent_versions v
JOIN agent_blueprints b ON b.id = v.blueprint_id
ORDER BY b.key, v.version_label, v.id
```

For each row: `register_blueprint_version(asset_key=b.key, version_label=v.version_label,
agent_version_id=v.id)` then `record_review(..., vetting_kind='blueprint_security_review',
provenance='reviewer_asserted_admin_recorded', outcome='passed',
reviewer='slice61b.blueprint_review_asserted')` then `list_asset`.

Idempotent the same way as connectors. Duplicate `(agent_blueprint, version_label)` catalog
keys collide with `uq_ca_kind_key_version` — `register_version` already keys versions by
content hash, and `version_label` is caller-chosen; if two version rows share a label for one
blueprint key, populate raises `CatalogPopulateError` rather than silently cataloguing one.
That collision does not exist in a fresh DB and is not created by this slice.

### OD-4 — One reference intake, drift-hashed, structurally §20.3-isolated

Create **exactly one** companion file:

`docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md`

It is a short, domain-generic example of a bounded integer counter (requirements + acceptance
criteria in prose). It must contain the sentence: `This companion is not a customer, industry,
geography, or certifier.` It must not name a real company, a regulated sector, or a
certification scheme. It is not one of the 26 core templates and is not imported by
`app/intake/` or any core decision module.

Catalog fields:

- `asset_key='generic_bounded_counter'`
- `version_label='v1'`
- `domain_label='generic'`
- `source_ref='docs/UAID_OS_Intake_Template_Pack_v1_2/reference_intakes/generic_bounded_counter.md'`
- `content_sha256='sha256:' + hex(sha256(file bytes as stored in git))`

`content_sha256` is computed by `reference_intake_digest(path)` over the raw file bytes. A
test fails if the listed digest disagrees with the file on disk (drift). The listing still
uses `record_review` with `reference_intake_constraint_attestation` — an assertion, not a
§20.3 checker (61a §7: no checker exists; structural isolation remains: no body column, no
resolver).

Do not register the 26 blank templates. Do not add a resolver. Do not store file bytes in the
database.

### OD-5 — Scope-literal regression is not D-8

`quoted_registry_keys(source_text: str) -> frozenset[str]` returns every `TOOL_REGISTRY` key
that appears as a single- or double-quoted substring of `source_text`. No AST. No import
graph. No `getattr` handling.

For each declared connector, read `service_module` as a file path
(`app.release.ci_evidence_service` → `app/release/ci_evidence_service.py`) and require:

```text
quoted_registry_keys(path.read_text(encoding="utf-8")) == frozenset(spec.tool_names)
```

A new `_TOOL = "ci.deploy_production"` in a service file fails CI until DECLARED is updated
**and** a new `version_label` is registered (children of `v1` are freeze-locked). Updating
DECLARED without a new version while `v1` stays listed fails P-22 (listed row must match
DECLARED). That is regression evidence. It does not prove the process cannot broker another
tool. D-8 stays OPEN. The scanner lives in `catalog_declared.py` so the test cannot quietly
reimplement it.

### OD-6 — Isolation and non-authority, unchanged

Populate does not import `app.release.production_autonomy`, `app.intake.readiness`,
`app.runtime.control_loop`, `app.tools.broker`, or `app.policy.matrix`. It does not call
`grant` on `agent_tool_allowlist`. It does not instantiate agents. Adoption is unused.
`A5_RULESET_VERSION` stays `slice54.v1`; readiness stays `slice20.v1`;
`can_go_live_autonomously` stays the literal `False`.

---

## 3. Code layout (500-line house cap)

| Path | Responsibility |
|---|---|
| Create: `app/ecosystem/catalog_declared.py` | `DECLARED_CONNECTORS` (the OD-1 table as `dict[str, ConnectorSpecInput]` plus `asset_key` / `version_label`), actor constants, `DECLARED_INTAKE` (key, label, path, domain), `reference_intake_digest`, `quoted_registry_keys`, `service_module_path` |
| Create: `app/ecosystem/catalog_populate.py` | `PopulateReport` (frozen dataclass: listed/skipped/blueprint_count/intake_listed), `CatalogPopulateError`, `populate_declared_catalog` |
| Create: `scripts/populate_catalog.py` | Thin async main: admin engine → `populate_declared_catalog` → print counts only (no source_ref, no digest, no tool names) |
| Modify: `app/repositories/catalog_reads.py` | `get_by_key(session, asset_kind, asset_key, version_label)`, `listed_keys(session, asset_kind)` |
| Modify: `app/ecosystem/__init__.py` | Docstring: catalog is populated by `populate_declared_catalog`; empty until that runs; still does not close the Slice 61 exit |
| Modify: `tests/ecosystem_catalog_support.py` | `real_connector_specs()` becomes a thin wrapper over `DECLARED_CONNECTORS` (same six keys) so 61a D-9 cannot drift |
| Create: `tests/test_ecosystem_catalog_populate.py` | Docker-free: P-1…P-7, P-21, P-25, scanner unit tests |
| Create: `tests/test_ecosystem_catalog_populate_db.py` | DB: P-8…P-20, P-22…P-24, P-26 bit-stability |
| Modify: `Makefile` | `catalog-populate` target using `ADMIN_DATABASE_URL` (admin only) |
| Modify: `.github/workflows/ci.yml` | Rename the pyright step to include 61b; add the new test files and `app/ecosystem/catalog_declared.py` / `catalog_populate.py` / `scripts/populate_catalog.py` to the owned path list (61a paths stay) |
| Modify: `CLAUDE.md`, `README.md` | Honesty crux in §0.3; no test counts in README |
| Modify: `.planning/GO-LIVE-END-TO-END-ROADMAP.md` | Rev 22: Slice 61b files + "head remains 0060; populate is not DDL"; D-8/D-9/D-10 still OPEN |

No new table. No new guard. No HTTP route. No LLM. No broker change.

Split any module approaching 500 lines and say so in the build report.

---

## 4. `PopulateReport` shape

```python
@dataclass(frozen=True)
class PopulateReport:
    connector_listed: tuple[str, ...]      # asset_keys listed this call (sorted)
    connector_skipped: tuple[str, ...]     # already listed (sorted)
    blueprint_listed: int
    blueprint_skipped: int
    intake_listed: bool
    intake_skipped: bool
```

Audit: none. CatalogAdmin is not tenant-audited (61a). Do not add a platform audit event that
could be read as "populate succeeded" — the listings are the evidence. The script prints only
the six integers/booleans above.

---

## 5. Tests

Probes marked **(runtime role)** use `rls_engine` as `uaid_app` after committed admin populate.
Sol rejects any guard-shaped claim that is only a helper unit test; this slice adds **no new
DB guard**. Every new behaviour below is a populate/read behaviour. Existing 61a guard probes
stay.

**Pure (Docker-free).**

- **P-1** `set(DECLARED_CONNECTORS) == {"ci_evidence", "pr_evidence", "deploy_evidence",
  "monitoring_evidence", "secrets_verification", "pm_issues"}` and each spec matches the OD-1
  table field-for-field (protocol, fake, service, status, adapter, tool_names).
  `real_connector_specs()` keys remain `{"ci","pr","deploy","monitoring","secrets","pm"}` and
  each short-key spec equals the corresponding `asset_key` spec.
- **P-2** `run_connector_contract_test(spec).passed is True` for every declared spec. 61a D-9
  remains; it must consume the wrapper so it cannot drift from `DECLARED_CONNECTORS`.
- **P-3** for each declared connector, `quoted_registry_keys(service file text) ==
  frozenset(spec.tool_names)`.
- **P-4** `quoted_registry_keys` on a fixture string containing `"pm.read_issues"` and
  `"ci.deploy_production"` returns both; on a string containing only an audit action
  `"ci.branch_protection_fetch_failed"` returns empty. This proves the scanner is
  registry-key-exact, not substring-of-`ci.`.
- **P-5** the intake file exists at the OD-4 path, contains the required companion sentence,
  and `reference_intake_digest(path)` equals `'sha256:' + sha256(file bytes).hexdigest()`.
- **P-6** the fourteen frozen-file hashes match §1.
- **P-7** `A5_RULESET_VERSION == "slice54.v1"`, readiness `RULESET_VERSION == "slice20.v1"`,
  `can_go_live_autonomously is False` by identity (`is False`, not `== False`).
- **P-21** `app/ecosystem/catalog_populate.py` source does not mention `production_autonomy`,
  `readiness`, `control_loop`, `broker`, or `matrix` (string scan of that one file).
- **P-25** `app/intake/` and the fourteen frozen files do not mention
  `generic_bounded_counter`. Core decision globs from 61a D-31 still do not mention catalog
  table names.

**DB.**

- **P-8** after migrate, before populate: `get_by_key(..., "connector", "ci_evidence", "v1")`
  is `None`; `listed_keys(session, "connector")` is empty.
- **P-9** `populate_declared_catalog` lists exactly the six OD-1 keys, each `listing_state=
  'listed'`, each latest vetting `vetting_kind='connector_contract_test'`,
  `provenance='checker_output_admin_recorded'`, `outcome='passed'`, with five result rows all
  `passed=true`. PM adapter name is SQL NULL. Report `connector_listed` is the six keys and
  `connector_skipped` is empty.
- **P-10** a second call in the same DB: `connector_listed` empty, `connector_skipped` the six
  keys, asset count for those keys unchanged, listing count unchanged.
- **P-11** live-adapter vocabulary on the six listed spec rows equals OD-1 (status + name/NULL).
- **P-12** `ci_evidence` and `pr_evidence` have distinct `asset_id`s, identical
  `protocol_module`/`protocol_name`/`fake_name`/`live_adapter_name`, and disjoint `tool_names`.
- **P-13 (runtime role)** after committed populate, `uaid_app` still cannot INSERT into
  `catalog_assets` / `catalog_listings` / `catalog_vetting_records`; SELECT of the six listed
  keys succeeds (no existence-hiding on global tables).
- **P-14** `agent_tool_allowlist` count and `agent_instances` count are unchanged across
  populate.
- **P-15** real `ProductionAutonomyRepository.evaluate` and `ReadinessRepository.evaluate`
  against the same project, before and after populate, are bit-equal on
  `a5_satisfied`, `can_go_live_autonomously`, `ruleset_version`, gate statuses, and readiness
  `readiness_level` / `ruleset_version`. Not a pure-function tautology.
- **P-16** monkeypatch `run_connector_contract_test` to return a failed five-result object for
  `pm_issues` only; populate raises; **no** declared connector listing is visible after the
  rolled-back transaction (count of the six keys is 0). Fail closed.
- **P-17** with zero `agent_versions`, `blueprint_listed == 0` and
  `listed_keys(..., "agent_blueprint")` is empty.
- **P-18** register two distinct blueprint versions (existing `register_blueprint` /
  `register_version` helpers), populate, `blueprint_listed == 2`; each listing cites a
  `blueprint_security_review` / `reviewer_asserted_admin_recorded` / `passed` record whose
  `reviewer` is `slice61b.blueprint_review_asserted` and whose asset `registered_by` is
  `slice61b.catalog_populate`; `reviewer != registered_by`. Second populate:
  `blueprint_skipped == 2`, `blueprint_listed == 0`.
- **P-19** intake: one listed `generic_bounded_counter` / `v1`; `source_ref` equals the OD-4
  path; `domain_label='generic'`; `content_sha256` equals `reference_intake_digest`; vetting
  kind `reference_intake_constraint_attestation`. No catalog table has a body/content column
  (re-assert 61a D-30).
- **P-20** overwrite the intake file bytes in a tmp copy **without** changing the listed
  digest: a dedicated digest-check test (pure, using the tmp copy) fails. The DB row is not
  mutated; this proves the drift function, not a DB trigger on the filesystem.
- **P-22** after populate, each listed connector spec+scope row equals `DECLARED_CONNECTORS`
  field-for-field. A unit-level assertion, queried from the DB, not from the in-memory spec
  used to insert.
- **P-23** INSERT into `connector_catalog_tool_scope` for listed `ci_evidence` is refused with
  `connector_children_frozen` (admin role). Reuse of 61a OD-13 on a **product** asset, not
  only on probe assets.
- **P-24** populate does not adopt; `tenant_catalog_adoptions` count unchanged.
- **P-26** `can_go_live_autonomously is False` after populate on a real A5 report.

61a D-35 (empty 0060 downgrade / populated refusal) stays. Populate is not a migration, so it
does not change that probe. If a test database has been populated, 0060 downgrade remains
refused — same as any other rows in those tables.

---

## 6. Documentation language, required

`CLAUDE.md` and `README.md` must:

- State that Slice 61b **closes no spec section** and **does not** meet the roadmap Slice 61
  exit.
- Carry the §0.3 honesty crux verbatim.
- State that a freshly migrated database is empty until `populate_declared_catalog` /
  `make catalog-populate` runs.
- State that D-8, D-9, and D-10 stay OPEN with owner = Salim.
- State A5 `slice54.v1`, readiness `slice20.v1`, `can_go_live_autonomously` literal `False`.
- Record no test counts in `README.md`.

Roadmap Rev 22 updates Slice 61b **Files** / **Migration** ("none; head remains 0060") / **Exit**
("populated declared catalog; D-8/D-9/D-10 still OPEN"). Do not mark Slice 61 as done.

---

## 7. Deferred / not claimed

| Capability | Disposition |
|---|---|
| Verified permission scoping | §12 OPEN **D-8**, owner = Salim. P-3/P-4 are not this. |
| Real-provider connector testing | §12 OPEN **D-9**, owner = Salim. PM adapter still absent. |
| Evidence-backed security-review gate | §12 OPEN **D-10**, owner = Salim. Title remains the owner-named "Automated blueprint security scanning"; body remains verified human workflow **or** scanner. Populate writes `reviewer_asserted_admin_recorded`. |
| Alembic-time population | Refused OD-2. Operator runs `make catalog-populate`. |
| Seeding `agent_versions` | Refused OD-3. Factory artifacts still do not exist. |
| §20.3 constraint checker | Still absent. Structural isolation only. |
| Generalized connector abstraction | Still refused (61a grounding fact 4). |
| HTTP catalog API | Deferred. |
| New A5 / readiness / go-live movement | Forbidden. |

---

## 8. Non-goals, restated

No change to `app/tools/broker.py`, `registry.py`, `matrix.py`, allowlist, any `*_connector.py`,
any `*_service.py`, `production_autonomy.py`, `readiness.py`, or `control_loop.py`. No new
enforcement point, no new tool, no new A1 action. No schema. No HTTP. No LLM. No signing. No
AST broker scan. No live-provider call. No Jira adapter. No agent execution.

---

## 9. Builder constraints

- TDD: write P-1…P-7 and the failing P-8 (empty-before-populate already true) / P-9 (fails until
  populate exists) first.
- Do not `ruff format` the whole tree (frozen-file hashes).
- pyright on the 61a owned paths **plus** the new 61b files; 0 errors on that set.
- Every new test that claims a refusal must fail when the refusing behaviour is removed
  (monkeypatch populate to skip the checker → P-16 fails; monkeypatch
  `quoted_registry_keys` to return the declared set always → P-3 cannot catch an extra tool —
  P-4 is the scanner unit that stays honest).
- Conventional commits. Do not commit `.env`. Do not edit this plan.

---

## 10. Change log

**v1.** First version of the population slice. No prior 61b plan.
