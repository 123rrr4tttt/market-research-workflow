# Wave17 Policy State Query Boundary Evidence (2026-05-22)

## Scope

This Wave17 worker advances the structured document-query migration by moving one more non-admin/dashboard query boundary behind reusable `document_queries` helpers:

- Endpoint: `/api/v1/policies/state/{state}`
- Function: `main/backend/app/api/policies.py::get_state_policies`
- Helper owner: `main/backend/app/services/document_queries/policy_filters.py`

The endpoint now uses `policy_state_condition()` and `policy_time_expr()` instead of rebuilding the structured JSON state predicate and time expression inline.

## Code Evidence

- `main/backend/app/api/policies.py`
  - `get_state_policies` calls `policy_state_condition(state)`.
  - `get_state_policies` calls `policy_time_expr()`.
  - The function no longer directly references `Document.extracted_data`.
- `main/backend/scripts/check_policy_state_document_query_boundary.py`
  - Static gate for the endpoint/helper boundary.
- `main/backend/tests/unit/test_policy_state_document_query_boundary_unittest.py`
  - Verifies the gate and helper exports/compiled SQL expressions.

## Validation

Commands run from this Wave17 worker branch:

```bash
python3 scripts/check_current_dev_wave17_plan.py
python3 main/backend/scripts/check_policy_state_document_query_boundary.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_policy_state_document_query_boundary_unittest.py main/backend/tests/unit/test_document_queries_policy_filters_unittest.py
git diff --check
```

## Boundary

This is repo-local helper/facade evidence only. It does not claim live DB/API smoke closure, production policy data correctness, or full structured-service modularization closure. The focused pytest lane requires Python 3.11 in this worktree; system `python3` is 3.9.6 and fails test collection on PEP 604 type syntax before executing tests.
