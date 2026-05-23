# Wave9 Worker 4: Document Queries Contract Evidence (2026-05-22)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Previous audit state: `partial/doc_aligned`
- This lane scope: close the first `document_queries` gap without editing shared indexes.
- Result: `document_queries` now has a deterministic `document_queries.v1` contract for query object, filters, sort, result envelope, and view-consumer rows.

## Implemented

Code:

- `main/backend/app/services/document_queries/contracts.py`
  - `DocumentQuery`
  - `DocumentQueryFilter`
  - `DocumentQuerySort`
  - `build_document_query_result_envelope()`
  - `validate_document_query_result_envelope()`
  - `rows_for_document_views()`
- `main/backend/app/services/document_queries/writing_material_queries.py`
  - `query_hybrid_document_envelope()`
  - `query_report_source_envelope()`
  - `query_source_library_material_envelope()`
  - Existing `*_rows()` functions now derive legacy row lists from the contract envelope.
- `main/backend/scripts/check_document_queries_contract.py`
  - Deterministic checker proving the envelope can feed `document_views` keyword-card construction.

Tests:

- `main/backend/tests/unit/test_document_queries_contracts_unittest.py`
- Existing policy filter, document view, writing keyword card, structured data search, and search contract tests were kept in the validation set.

## Contract Shape

The stable envelope is:

```json
{
  "status": "ok",
  "data": {
    "contract_version": "document_queries.v1",
    "query": {
      "contract_version": "document_queries.v1",
      "query": "robotics",
      "normalized_query": "robotics",
      "project_key": "demo_proj",
      "consumer": "writing.keyword_cards",
      "sources": ["document"],
      "filters": [{"field": "state", "op": "eq", "value": "CA"}],
      "sort": [{"field": "relevance", "direction": "desc"}],
      "limit": 20,
      "offset": 0,
      "query_id": "stable-hash"
    },
    "results": [],
    "pagination": {
      "limit": 20,
      "offset": 0,
      "result_count": 0,
      "total": 0
    }
  },
  "error": null,
  "meta": {
    "contract_version": "document_queries.v1",
    "query_id": "stable-hash",
    "consumer": "writing.keyword_cards",
    "source": "search.hybrid",
    "result_count": 0
  }
}
```

## Validation

Commands run in `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave9-data-structured-document-queries`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile \
  main/backend/app/services/document_queries/contracts.py \
  main/backend/app/services/document_queries/writing_material_queries.py \
  main/backend/app/services/document_queries/__init__.py \
  main/backend/scripts/check_document_queries_contract.py
```

Result: passed.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_document_queries_policy_filters_unittest.py \
  main/backend/tests/unit/test_document_views_unittest.py \
  main/backend/tests/unit/test_writing_keyword_card_service_unittest.py \
  main/backend/tests/unit/test_structured_data_search_unittest.py \
  main/backend/tests/core_business/test_search_core_contract.py
```

Result: `25 passed, 11 warnings`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_document_queries_contract.py
```

Result: `status=pass`, `contract_version=document_queries.v1`, `view_card_source_type=document`.

## Remaining Scope

This lane does not claim full topic closure. Remaining work is still larger than this worker scope:

- Migrate more API/search endpoints to emit or accept `document_queries.v1` directly.
- Add SQLAlchemy statement builders around the query object if backend endpoints need first-class DB execution.
- Decide whether graph/index/vector downstream should consume the envelope directly or continue through view adapters.
