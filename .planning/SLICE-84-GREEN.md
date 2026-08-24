# Slice 84 / F-021 — GREEN transcripts (identical probes after the test fix)

Captured on `feat/slice-84-test-integrity` after the named-guard tests landed.
Alembic head remains `0062`. Suites: `make test` 1277 passed / 1104 deselected;
`make test-db` 1104 passed / 1277 deselected.

## P-GREEN-1a — admin `TRUNCATE cost_events CASCADE`

```
sqlstate: P0001
message: cost_events is immutable (no UPDATE/DELETE/TRUNCATE)
absent: cannot truncate, append-only
```

## P-GREEN-1b — admin plain `TRUNCATE cost_events`

```
sqlstate: 0A000
message: cannot truncate a table referenced in a foreign key constraint
absent: cost_events is immutable
```

## P-MUT-1 — `cost_events_no_truncate` disabled, same CASCADE

```
sqlstate: P0001
message: cost_forecast_ledger_event_refs is append-only
absent: cost_events is immutable
tgenabled after restore: O
```

## P-GREEN-2a — `TRUNCATE {table} CASCADE`

MESSAGE_PRIMARY exact equality (Sol REJECT #2: `skills is append-only` is a
substring of `agent_provided_skills is append-only` on the SQLAlchemy wrapper).

```
skills                         P0001  skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
agent_skill_capabilities       P0001  agent_skill_capabilities is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
agent_provided_skills          P0001  agent_provided_skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
```

## P-MUT-2 — `{table}_no_truncate` disabled, same CASCADE

```
skills                         PRIMARY= agent_provided_skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
                               skills exact-primary assertion raises AssertionError
agent_skill_capabilities       PRIMARY= agent_provided_skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
agent_provided_skills          CASCADE succeeded (named trigger did not fire)
tgenabled after restore: O
```

## P-GREEN-2b — plain TRUNCATE neighbour control

```
TRUNCATE skills                         0A000  cannot truncate a table referenced in a foreign key constraint
TRUNCATE agent_skill_capabilities       0A000  cannot truncate a table referenced in a foreign key constraint
TRUNCATE agent_provided_skills          P0001  agent_provided_skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE)
```

## P-GREEN-2d — structurally valid runtime INSERT

```
sqlstate: 42501
message: permission denied for table {skills|agent_skill_capabilities|agent_provided_skills}
absent: null value / not-null / foreign key / check / duplicate key
```

## P-GREEN-2f — admin masking controls

```
INSERT INTO skills DEFAULT VALUES
  sqlstate: 23502
  message: null value in column "key" of relation "skills" violates not-null constraint
unknown skill_id APS insert
  sqlstate: 23503
  message: violates foreign key constraint "fk_aps_skill"
```

## P-GREEN-3a — direct `accept()` (pytest)

`InvalidFinding: critical findings cannot be accepted`
event count unchanged; no `event_type='accepted'`; no `release.finding_accepted` audit.

## P-GREEN-3b — SQL critical accept with a valid record

```
sqlstate: P0001
message: release_findings: critical findings cannot be accepted
```

## P-GREEN-4 — wrong-project / wrong-subject `_ACCEPT_SQL`

```
sqlstate: P0001
findings: release_findings: no usable risk-acceptance record for this finding
issues:   release_issues: no usable risk-acceptance record for this issue
matching pair succeeds (rolled back)
```

## P-GREEN-5a — cross-tenant SQL INSERT (GUC=t2, tenant_id=t1)

```
sqlstate: P0001
message: risk_acceptance_records: release/subject binding is not exact
```

Python path (same test): `InvalidRiskAcceptance: release_id must resolve to one same-project frozen candidate`

## P-GREEN-5b — identical SQL, only `risk_acceptance_records_guard` disabled

```
sqlstate: 42501
message: new row violates row-level security policy for table "risk_acceptance_records"
```

## P-GREEN-5c / P-MUT-5 — tenant axis corrected → INSERT rowcount 1, rolled back

Trigger restored `tgenabled='O'`.

## Pytest (27 nodes)

```
27 passed in 3.94s
```

## Pyright (eight §1 files)

Sol code REJECT #1 required the eight §1 files to report 0 errors (plan §5).
Pre-existing errors in `tests/test_skills.py` (`_inputs` / `latest()`) and
`tests/test_risk_acceptance.py` (`ra_ctx` dict inferred `dict[str, str]`) were
typed without suppressions and without a positive OD-1 delta.

```
uv run pyright tests/slice84_support.py tests/test_slice84_load_bearing.py \
  tests/test_slice84_acceptance_guards.py tests/test_cost.py tests/test_skills.py \
  tests/test_release_findings.py tests/test_release_issues.py tests/test_risk_acceptance.py
0 errors, 0 warnings, 0 informations
```

`git diff --numstat d0f38fd` on the five pre-existing files remains non-positive:
`test_cost.py` 3/36, `test_release_findings.py` 6/50, `test_release_issues.py` 2/40,
`test_risk_acceptance.py` 4/21, `test_skills.py` 12/33.
