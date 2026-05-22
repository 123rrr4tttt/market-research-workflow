# Wave17 Policy State Consumer Query Boundary Evidence (2026-05-22)

## Result

The policy state consumer endpoint now reuses the shared document-query predicate/time helpers instead of owning its own structured JSON predicate:

- `get_state_policies` uses `policy_state_condition(state)`.
- `get_state_policies` uses `policy_time_expr()`.
- The endpoint function has zero direct `Document.extracted_data` reads.

This extends the Wave15 admin/dashboard predicate facade work to one additional non-admin/dashboard consumer boundary.

## Gate

Added `main/backend/scripts/check_policy_state_document_query_boundary.py`.

The gate checks:

1. `main/backend/app/api/policies.py::get_state_policies` imports the required query helpers.
2. The function calls `policy_state_condition` and `policy_time_expr`.
3. The function does not directly read `Document.extracted_data`.
4. `main/backend/app/services/document_queries/policy_filters.py` still defines the required helpers.

## Validation

Commands run from this Wave17 worker branch:

```bash
python3 scripts/check_current_dev_wave17_plan.py
python3 main/backend/scripts/check_policy_state_document_query_boundary.py
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_policy_state_document_query_boundary_unittest.py main/backend/tests/unit/test_document_queries_policy_filters_unittest.py
git diff --check
```

## Remaining Risk

No live DB/API smoke was run in this slice. The evidence is limited to static boundary checks and focused unit tests. The focused pytest lane requires Python 3.11 in this worktree; system `python3` is 3.9.6 and fails test collection on PEP 604 type syntax before executing tests.
