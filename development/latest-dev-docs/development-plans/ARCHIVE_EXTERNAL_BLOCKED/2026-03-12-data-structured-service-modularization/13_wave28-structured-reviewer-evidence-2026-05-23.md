# Wave28 Structured Reviewer Evidence (2026-05-23)

## Result

- Reviewer role: `wave28 structured reviewer`
- Topic: `2026-03-12-data-structured-service-modularization`
- Current decision: `external_blocked`; the directory has been moved to `ARCHIVE_EXTERNAL_BLOCKED`.
- Reviewer verdict: before the builder changes appeared, current executable closure evidence supported that the only repo-local blocker was the generic `DocumentQuery -> SQLAlchemy statement` builder. After the builder changes landed and the supervisor migration ran, focused gates report no repo-local blocker.

This review checked the current `document_queries` service modules, the Wave27 closure checker, the Wave27 automation output, and the current status surfaces. The active evidence does not show another repo-local blocker for the current document-query modularization slice, but it still does not prove live DB/API behavior.

## Evidence Read

- `main/backend/app/services/document_queries/contracts.py`
- `main/backend/app/services/document_queries/__init__.py`
- `main/backend/app/services/document_queries/search_endpoint.py`
- `main/backend/app/services/document_queries/structured_data_search.py`
- `main/backend/app/services/document_queries/consumer_predicates.py`
- `main/backend/app/services/document_queries/policy_filters.py`
- `main/backend/app/services/document_queries/writing_material_queries.py`
- `main/backend/app/services/document_queries/writing_documents.py`
- `main/backend/app/services/document_queries/statement_builder.py`
- `main/backend/scripts/check_wave27_structured_consumer_closure.py`
- `main/backend/scripts/check_structured_sql_helper_migration.py`
- `development/latest-dev-docs/automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`

## Findings

1. The combined Wave27 checker still passes all seven endpoint/query/consumer gates.
2. In the current worktree, the checker reports `repo_local_blockers=[]` and `decision.status=external_blocked_candidate`; supervisor status migration records the topic as `external_blocked`.
3. Current static search finds implementations and exports for all expected builder tokens:
   - `build_document_query_statement`
   - `compile_document_query_statement`
   - `apply_document_query_to_statement`
   - `document_query_to_statement`
4. `statement_builder.py` compiles a sample query with text search, `project_key`, scalar filters, JSON path filters, ordering, limit, and offset; the closure checker reports `compile_gaps=[]`.
5. Historical topic docs still contain wider source-library, quality-frontdoor, and writer language. For current closure, those wider concerns appear to be routed through other current topics or earlier evidence; they should not be used as hidden blockers unless the active status row is expanded again.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_document_queries_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_sql_helper_migration.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_structured_data_search_document_query_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_search_endpoint_document_query_contract.py
```

Observed result:

- `check_wave27_structured_consumer_closure.py`: `status=passed`, `decision=external_blocked_candidate`, `gate_count=7`, `passed_gate_count=7`, `repo_local_blockers=[]`
- `check_document_queries_contract.py`: `status=pass`
- `check_structured_sql_helper_migration.py`: `status=passed`, `covered_surface_count=7`, `covered_surface_gap_count=0`, `deferred_boundary_count=0`
- `check_structured_data_search_document_query_contract.py`: `status=pass`
- `check_search_endpoint_document_query_contract.py`: `status=pass`

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_document_queries_policy_filters_unittest.py \
  main/backend/tests/unit/test_search_endpoint_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_data_search_document_query_contract_unittest.py \
  main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py \
  main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```

Observed result in the supervisor integration pass: `12 passed in 2.97s` for the focused Wave28 subset.

## Minimum Closure Verification

To keep this topic out of `CURRENT_DEV`, the minimum closure set is:

- Run the focused checker/test set above.
- Keep `CURRENT_DEV/INDEX.md`, `STATUS_AUDIT_2026-04-07.md`, and topic README evidence links aligned with the archive path.
- Run `scripts/check_current_dev_status_evidence.py` and confirm this topic is no longer counted in `partial`.
- If only `live_db_api_smoke_not_run` remains, keep this directory in `ARCHIVE_EXTERNAL_BLOCKED`, not `ARCHIVE_CLOSED`.
- Move to `ARCHIVE_CLOSED` only after a live DB/API smoke explicitly proves production-like structured/document-query behavior.

## Risk

The main risk is closing the directory too aggressively by treating deterministic gates as live runtime proof. The current builder is covered by compile-level tests, but it has not executed against a live tenant DB/API stack. Reviewer caveats for the current builder candidate:

- `DocumentQuery.sources` now treats document-source aliases as metadata and applies non-document sources as `Document.doc_type` scope; live DB/API smoke should confirm this convention matches production data.
- `project_key` is compiled as `Document.extracted_data["project_key"].astext == ...`; `Document` has no first-class `project_key` column, so this should stay documented as a JSON-metadata convention.
- `scripts/check_current_dev_status_evidence.py` now passes with this topic removed from `CURRENT_DEV`; do not mark the directory `ARCHIVE_CLOSED` until live DB/API evidence exists.
