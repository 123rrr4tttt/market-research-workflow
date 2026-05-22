# Wave15 Worker 6: Structured SQL Helper Migration Boundary (2026-05-22)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Branch: `codex/devdocs-wave15-structured-sql-helper-migration`
- Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave15-structured-sql-helper-migration`
- Scope: add a small deterministic SQL/query helper migration inventory gate without editing shared navigation indexes.
- Result: `main/backend/scripts/check_structured_sql_helper_migration.py` now verifies the covered `document_queries.v1` helper surfaces and records the remaining admin structured SQL predicate migration boundary.

## Implemented

Code:

- `main/backend/scripts/check_structured_sql_helper_migration.py`
  - Emits `structured-sql-helper-migration.wave15.v1`.
  - Verifies the `document_queries.v1` query object/result envelope helpers.
  - Verifies SQLAlchemy policy JSON predicate helpers in `document_queries.policy_filters`.
  - Verifies prompt-time-density consumes `prompt_time_density_time_expr()` instead of owning its local SQL JSON time expression.
  - Verifies writing material query helpers build document query envelopes before returning legacy rows.
  - Verifies `/api/v1/search` still uses `build_search_endpoint_document_query_envelope()` and emits the `document_query_*` projection fields.
  - Inventories admin endpoints whose structured JSON SQL predicates remain inline and deferred.

Tests:

- `main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py`
  - Confirms all covered helper and endpoint surfaces pass.
  - Confirms deferred admin SQL predicate boundaries remain explicit rather than silently claimed as migrated.

## Covered Boundary

The checker treats these surfaces as covered and regression-gated:

- Query object/envelope helpers: `main/backend/app/services/document_queries/contracts.py`
  - `DocumentQuery`, `DocumentQueryFilter`, `DocumentQuerySort`
  - `build_document_query()`
  - `build_document_query_result_envelope()`
  - `rows_for_document_views()`
  - `validate_document_query_result_envelope()`
- SQL/query helper expressions: `main/backend/app/services/document_queries/policy_filters.py`
  - `document_json_iso_date_expr()`
  - `policy_effective_date_expr()`
  - `policy_has_data_condition()`
  - `policy_state_condition()`
  - `policy_time_expr()`
  - `policy_type_condition()`
  - `policy_type_order_expr()`
  - `prompt_time_density_time_expr()`
- Consumer SQL helper migration: `main/backend/app/services/stats/prompt_time_density.py`
  - `query_prompt_time_density()` calls `prompt_time_density_time_expr()`.
- Writing material query helpers: `main/backend/app/services/document_queries/writing_material_queries.py`
  - `query_hybrid_document_envelope()`
  - `query_report_source_envelope()`
  - `query_source_library_material_envelope()`
  - Legacy row helpers derive rows from the contract envelope.
- Search endpoint projection: `main/backend/app/services/document_queries/search_endpoint.py` and `main/backend/app/api/search.py`
  - `/api/v1/search` keeps legacy fields while adding `document_query_contract_version`, `document_query`, `document_query_results`, `document_query_pagination`, and `document_query_meta`.

## Remaining Migration Boundary

The checker does not claim full SQL helper migration. It records these admin endpoint/query predicate surfaces as deferred:

- `/api/v1/admin/documents/list`
  - `main/backend/app/api/admin.py::list_documents`
  - Reason: `has_extracted_data` still builds `Document.extracted_data` predicates inline.
- `/api/v1/admin/social-data/list`
  - `main/backend/app/api/admin.py::list_social_data`
  - Reason: platform and sentiment filters still read structured JSON fields inline.
- `/api/v1/admin/content-graph`
  - `main/backend/app/api/admin.py::get_content_graph`
  - Reason: graph filters still check sentiment/entities structured JSON keys inline.
- `/api/v1/admin/market-graph`
  - `main/backend/app/api/admin.py::get_market_graph`
  - Reason: market graph filters still check market/company/product/operation structured JSON keys inline.
- `/api/v1/admin/policy-graph`
  - `main/backend/app/api/admin.py::get_policy_graph`
  - Reason: policy graph state/type predicates still read policy JSON fields inline.

These are next-step candidates for a narrower `document_queries` SQL predicate facade or endpoint-specific statement builders. This worker only adds the inventory gate and does not rewrite those endpoint queries.

## Validation

Commands run from the Wave15 worker worktree:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_sql_helper_migration.py
```

Result: passed; `covered_surface_count=6`, `covered_surface_gap_count=0`, `deferred_boundary_count=5`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py
```

Result: `2 passed`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_document_queries_policy_filters_unittest.py \
  main/backend/tests/unit/test_search_endpoint_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_data_search_unittest.py
```

Result: `17 passed`.

```bash
python3 scripts/check_current_dev_wave15_plan.py
```

Result: `OK wave15_current_dev_plan=passed ... worker_boundary_enforced=true`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
```

Result: `OK current_dev_status_evidence=passed entries=35 counts=partial:35,not_closed:0,no_closure_claim:0 links=184 placeholders=0 empty_dirs=0 wave_rows=117`.

```bash
git diff --check
```

Result: passed.

## Boundary Notes

- Shared indexes remain supervisor-owned and were not edited by this worker.
- `main/backend/scripts/workflow_graph_smoke_local.py` was not modified.
- This lane advances the SQL/query helper migration boundary by making the covered/deferred split executable; it does not close the broader structured service modularization topic.
