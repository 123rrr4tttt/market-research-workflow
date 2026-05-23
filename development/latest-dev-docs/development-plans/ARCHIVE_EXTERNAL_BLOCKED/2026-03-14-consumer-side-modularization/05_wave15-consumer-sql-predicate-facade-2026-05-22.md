# Wave15 Consumer SQL Predicate Facade Evidence (2026-05-22)

## Status

- Topic: `2026-03-14-consumer-side-modularization`
- Branch: `codex/devdocs-wave15-consumer-sql-predicate-facade`
- Result: admin/dashboard consumer SQL JSON predicates are routed through `document_queries`.

This slice closes the admin/dashboard SQL predicate gap left by Wave13. It does not claim every structured-data read in the backend, nor writer/governance paths that intentionally own raw `extracted_data` mutation.

## What Changed

Added `main/backend/app/services/document_queries/consumer_predicates.py` as the query facade for admin/dashboard consumer predicates.

The facade now owns these SQL JSON expression families:

1. Generic structured-data presence predicates.
2. Social platform and sentiment filters.
3. Content graph structured-data predicates.
4. Market graph structured-data, state, game, and report-date predicates.
5. Policy graph structured-data, state, and policy-type predicates.

Updated admin/dashboard consumers to call the facade instead of writing `Document.extracted_data[...]` directly:

1. `main/backend/app/api/admin.py`
   - `list_documents(...)`
   - `list_social_data(...)`
   - `get_content_graph(...)`
   - `get_market_graph(...)`
   - `get_policy_graph(...)`
2. `main/backend/app/api/dashboard.py`
   - `get_dashboard_stats(...)`
   - `get_document_analysis(...)`
   - `get_sentiment_analysis(...)`
   - `get_sentiment_sources(...)`

Also updated the Wave13 Python-read checker so it no longer treats SQL JSON predicates as deferred inside the selected functions. Wave15 now owns that gate.

## Guardrail

Added `main/backend/scripts/check_consumer_sql_predicate_facade.py`.

The checker verifies:

1. `consumer_predicates.py` exists and exports the required facade functions through `document_queries`.
2. `admin.py` and `dashboard.py` import `document_queries`.
3. The nine selected consumer query functions call their required facade helpers.
4. `admin.py` and `dashboard.py` contain no direct `Document.extracted_data` SQL JSON expressions.

Current checker result:

```text
status: passed
checked_api_surface_count: 2
checked_consumer_query_function_count: 9
direct_admin_dashboard_document_extracted_data_read_count: 0
owned_document_extracted_data_expression_count: 20
```

## Coverage And Boundary

Covered:

- Admin/dashboard SQL JSON predicates in the selected document-view consumer query paths.
- Dashboard structured-data extraction-rate predicates.
- Social/content/market/policy graph SQL JSON filters used before document-view normalization.

Remaining boundary:

- `Document.extracted_data` SQL JSON expressions now remain inside `main/backend/app/services/document_queries`.
- This gate does not claim non-admin/dashboard consumers.
- This gate does not claim Python instance-level raw data writes, re-extraction, or governance/admin mutation paths.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave15-consumer-sql-predicate-facade`:

```bash
python3 main/backend/scripts/check_consumer_sql_predicate_facade.py
```

Result: `status=passed`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_consumer_sql_predicate_facade_unittest.py \
  main/backend/tests/unit/test_admin_dashboard_consumer_boundary_unittest.py \
  main/backend/tests/unit/test_document_queries_policy_filters_unittest.py
```

Result: `7 passed`.

```bash
python3 scripts/check_current_dev_wave15_plan.py
```

Result: `OK wave15_current_dev_plan=passed mode=codex/devdocs-wave15-consumer-sql-predicate-facade branches=9 changed_files=10 worker_boundary_enforced=true`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
```

Result: `OK current_dev_status_evidence=passed entries=35 counts=partial:35,not_closed:0,no_closure_claim:0 links=184 placeholders=0 empty_dirs=0 wave_rows=117`.

```bash
git diff --check
```

Result: passed.
