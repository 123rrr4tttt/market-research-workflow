# Wave20 Worker 6: Document Query Endpoint Slice Evidence (2026-05-22)

## Scope

- Topic: `2026-03-12-data-structured-service-modularization`
- Branch: `codex/devdocs-wave20-document-query-endpoint-slice`
- Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave20-document-query-endpoint-slice`
- Selected slice: `project.structured_data.search` query-service response projection

This worker advances the broader endpoint/query migration gap by aligning one internal search service boundary with `document_queries.v1`. It does not touch shared navigation indexes and does not claim all endpoints or DB statement builders have been migrated.

## Implemented

Code:

- `main/backend/app/services/document_queries/structured_data_search.py`
  - Builds a `DocumentQuery` for `project.structured_data.search`.
  - Normalizes requested datasets into a `dataset in [...]` filter.
  - Converts structured search items into a validated `document_queries.v1` result envelope with `structured_record` result type.
- `main/backend/app/services/agent_runtime/structured_data_search.py`
  - Keeps the existing `project.structured_data.search.v1` payload.
  - Adds `document_query_contract_version`, `document_query`, `document_query_results`, `document_query_pagination`, and `document_query_meta` for successful project searches.
- `main/backend/scripts/check_structured_data_search_document_query_contract.py`
  - Deterministic checker for the new helper and service marker coverage.

Tests:

- `main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py`
- Existing focused regression lane: `main/backend/tests/unit/test_structured_data_search_unittest.py`

Evidence:

- `development/latest-dev-docs/automation-runs/wave20-document-query-endpoint-slice/2026-05-22/README.md`
- `development/latest-dev-docs/automation-runs/wave20-document-query-endpoint-slice/2026-05-22/structured_data_search_document_query_contract.json`

## Boundary Contract

`project.structured_data.search` success response now includes:

```text
document_query_contract_version == document_queries.v1
document_query.consumer == project.structured_data.search
document_query.project_key == resolved project key
document_query.filters includes the requested dataset list
document_query_results contains normalized structured_record rows
```

The service still performs the same read-only tenant-schema queries. This slice only exposes a stable document-query projection so later endpoint or caller migrations can consume the query shape without inferring it from ad hoc structured-data fields.

## Validation

Commands run from this worker worktree:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile \
  main/backend/app/services/document_queries/structured_data_search.py \
  main/backend/app/services/document_queries/__init__.py \
  main/backend/app/services/agent_runtime/structured_data_search.py \
  main/backend/scripts/check_structured_data_search_document_query_contract.py \
  main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py
```

Result: passed.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_data_search_document_query_contract.py
```

Result: `status=pass`, `consumer=project.structured_data.search`, `result_source_type=structured_record`, `service_marker_gaps=[]`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_data_search_unittest.py
```

Result: `9 passed in 2.15s`.

Additional gates:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_document_queries_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_search_endpoint_document_query_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_data_search_unittest.py \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_search_endpoint_document_query_contract_unittest.py \
  main/backend/tests/core_business/test_search_core_contract.py
python3 scripts/check_current_dev_wave20_plan.py
git diff --check
```

Result: document/query and search endpoint checkers passed; pytest `18 passed, 11 warnings in 0.14s`; Wave20 plan gate passed; `git diff --check` passed.

## Remaining Scope

- More public API/search endpoints remain outside this worker slice.
- DB statement builders around `DocumentQuery` are not introduced here.
- Live DB/API smoke and production tenant data behavior remain separate validation work.
- Shared indexes remain supervisor-owned for Wave20 integration.
