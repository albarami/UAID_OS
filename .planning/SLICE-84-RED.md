# Slice 84 / F-021 — RED transcripts (captured on `d0f38fd` before any test edit)

Environment: `TEST_DATABASE_URL=postgresql+asyncpg://uaid_app:uaid_app@localhost:5432/app_test`,
`TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test`.
Temporary pytest plugin `/tmp/s84_red_plugin.py` was not committed.

## P-RED-1 — admin `TRUNCATE cost_events` (no CASCADE)

```
sqlstate: 0A000
message: cannot truncate a table referenced in a foreign key constraint
contains_cannot_truncate: true
contains_immutable: false  (cost_events is immutable ABSENT)
```

`pytest -m db tests/test_cost.py::test_cost_events_immutable` → **PASSED**
(the current `"immutable" or "cannot truncate"` disjunction accepts the neighbouring FK).

## P-RED-2a — admin `TRUNCATE skills` (no CASCADE)

```
sqlstate: 0A000
message: cannot truncate a table referenced in a foreign key constraint
matches_loose_regex: true via "cannot truncate"
contains_table_specific: false
  (skills is append-only / immutable (no UPDATE/DELETE/TRUNCATE) ABSENT)
```

`pytest -m db tests/test_skills.py::test_db_global_tables_immutable` → **PASSED**

## P-RED-2b (i) — runtime `INSERT INTO skills DEFAULT VALUES` (current ACL; not the masking path)

```
sqlstate: 42501
message: permission denied for table skills
```

## P-RED-2b (ii) — admin identical `INSERT INTO skills DEFAULT VALUES` (the masking path)

```
sqlstate: 23502
message: null value in column "key" of relation "skills" violates not-null constraint
```

`pytest -m db tests/test_skills.py::test_db_runtime_cannot_write_any_global_table` → **PASSED**
(unmatched `pytest.raises(Exception)` would accept the admin `23502` if INSERT were granted).

## P-RED-3 — `test_reject_critical_accept` never enters `accept()`

Plugin wrap of `ReleaseFindingRepository.accept` and `_make_ra_record`:

```
accept_entered: False
make_ra: ['InvalidRiskAcceptance: release/subject binding is not exact']
ra_create: ['InvalidRiskAcceptance: release/subject binding is not exact']
```

Test **PASSED**. Root cause: `risk_acceptance.py:120-123` / `:142-143`.

## P-RED-4 — last two invalid-record cases never execute `_ACCEPT_SQL`

Findings `test_guard_rejects_accept_with_invalid_records`:

```
accept_sql_findings: 3
direct_findings: three UPDATE release_findings SET status='accepted' ... (expired/revoked/blocking)
make_ra last two:
  1. RaiseError: release_candidate_issue_bindings: issue project mismatch
  2. InvalidRiskAcceptance: release/subject binding is not exact
```

Issues `test_guard_rejects_accept_with_invalid_records`:

```
accept_sql_issues: 3
direct_issues: three UPDATE release_issues SET status='accepted' ...
make_ra last two:
  1. RaiseError: release_candidate_issue_bindings: issue project mismatch
  2. InvalidRiskAcceptance: release/subject binding is not exact
```

Both tests **PASSED**. `_ACCEPT_SQL` did not increment for the last two cases.

## P-RED-5 — Python cross-tenant `create(project_id=p1)` as t2

```
InvalidRiskAcceptance: release_id must resolve to one same-project frozen candidate
```

(not `release/subject binding is not exact`). Test **PASSED**. §0.1.15 confirmed on live DB.

## Pytest session

```
7 passed in 1.40s
tests/test_cost.py::test_cost_events_immutable PASSED
tests/test_skills.py::test_db_global_tables_immutable PASSED
tests/test_skills.py::test_db_runtime_cannot_write_any_global_table PASSED
tests/test_release_findings.py::test_reject_critical_accept PASSED
tests/test_release_findings.py::test_guard_rejects_accept_with_invalid_records PASSED
tests/test_release_issues.py::test_guard_rejects_accept_with_invalid_records PASSED
tests/test_risk_acceptance.py::test_rls_deny_by_default_and_cross_tenant PASSED
```
