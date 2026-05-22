# Wave20 Document Query Endpoint Slice Evidence

Date: 2026-05-22 PST

Branch: `codex/devdocs-wave20-document-query-endpoint-slice`

Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave20-document-query-endpoint-slice`

## Scope

This evidence covers one low-risk query-service slice for the data structured service modularization topic:

- Selected boundary: `project.structured_data.search`
- Contract projection added: `document_queries.v1`
- Helper owner: `main/backend/app/services/document_queries/structured_data_search.py`
- Runtime caller: `main/backend/app/services/agent_runtime/structured_data_search.py`

This run does not claim all API/search endpoints are migrated and does not introduce a DB statement-builder migration.

## Evidence

`structured_data_search_document_query_contract.json` was produced by:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_data_search_document_query_contract.py
```

Result: `status=pass`.

Focused tests:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_data_search_unittest.py
```

Result: `9 passed in 2.15s`.

Final worker gates:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_data_search_document_query_contract.py
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

Result: checker statuses passed; pytest `18 passed, 11 warnings in 0.14s`; Wave20 plan gate `OK wave20_current_dev_plan=passed`; `git diff --check` passed.

## Boundary

The selected service now returns `document_query_contract_version`, `document_query`, `document_query_results`, `document_query_pagination`, and `document_query_meta` alongside the existing `project.structured_data.search.v1` payload. Legacy fields remain unchanged for agent-runtime consumers.

Remaining scope stays explicit: more endpoints, live DB/API smoke, and DB statement builders remain follow-up work.
