# Wave13 Worker 3: Structured Search Endpoint Contract Evidence (2026-05-22)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Branch: `codex/devdocs-wave13-structured-data-api-migration`
- Previous audit state: `partial/doc_aligned/wave9_verified/wave11_verified`
- This lane scope: advance the broader API/search endpoint migration gap without editing shared navigation indexes.
- Result: `/api/v1/search` now emits a `document_queries.v1` query/result projection alongside its existing legacy-compatible search payload.

## Implemented

Code:

- `main/backend/app/services/document_queries/search_endpoint.py`
  - Builds the `api.search` `DocumentQuery` boundary for `/api/v1/search`.
  - Converts search endpoint rows into a validated `document_queries.v1` result envelope.
  - Preserves endpoint-only runtime details in envelope meta: endpoint, rank mode, modality, top-k cap, and mapped backend diagnostics.
- `main/backend/app/api/search.py`
  - Keeps the existing `query/state/modality/rank/top_k/results/search_*` payload fields.
  - Adds `document_query_contract_version`, `document_query`, `document_query_results`, `document_query_pagination`, and `document_query_meta`.
- `main/backend/scripts/check_search_endpoint_document_query_contract.py`
  - Deterministic checker for the new search endpoint boundary and static API marker coverage.

Tests:

- `main/backend/tests/unit/test_search_endpoint_document_query_contract_unittest.py`
- `main/backend/tests/core_business/test_search_core_contract.py`

## Boundary Contract

This worker does not change the public route or remove legacy fields. The bounded migration contract is:

```text
/api/v1/search success response
  data.document_query_contract_version == document_queries.v1
  data.document_query.consumer == api.search
  data.document_query.project_key == resolved request project key when available
  data.document_query.filters includes the applied state filter
  data.document_query_results is the normalized document_queries.v1 result view
```

The search endpoint still calls the existing hybrid search implementation. This lane only makes the endpoint emit the structured document-query boundary so later workers can migrate more endpoint consumers without guessing query shape from ad hoc payload fields.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave13-structured-data-api-migration`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile \
  main/backend/app/services/document_queries/search_endpoint.py \
  main/backend/app/services/document_queries/__init__.py \
  main/backend/app/api/search.py \
  main/backend/scripts/check_search_endpoint_document_query_contract.py
```

Result: passed.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_search_endpoint_document_query_contract.py
```

Result:

```json
{
  "status": "pass",
  "checks": {
    "contract_version": "document_queries.v1",
    "consumer": "api.search",
    "project_key": "demo_proj",
    "state_filter": {
      "field": "state",
      "op": "eq",
      "value": "CA"
    },
    "result_count": 1,
    "result_source_type": "document",
    "api_marker_gaps": []
  }
}
```

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_search_endpoint_document_query_contract_unittest.py \
  main/backend/tests/core_business/test_search_core_contract.py
```

Result: `5 passed, 11 warnings`.

Additional gates:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_document_queries_contract.py
```

Result: `status=pass`, `contract_version=document_queries.v1`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py
```

Result: `4 passed`.

```bash
python3 scripts/check_current_dev_wave13_plan.py
```

Result: `OK wave13_current_dev_plan=passed ... worker_boundary_enforced=true`.

```bash
git diff --check
```

Result: passed.

## Remaining Scope

- This lane does not migrate `_init` or other admin/dashboard/search-adjacent endpoints.
- SQLAlchemy statement builders around `DocumentQuery` are still not introduced here.
- Legacy `/api/v1/search` response fields remain for compatibility; a later endpoint version can decide whether the `document_query_*` projection becomes the primary response body.
- Shared navigation indexes remain supervisor-owned for Wave13 integration.
