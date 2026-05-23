# Wave11 Structured Consumer Query Extraction Evidence (2026-05-22)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Shared slice: `2026-03-14-consumer-side-modularization`
- Branch: `codex/devdocs-wave11-structured-consumer-extraction`
- Result: `prompt_time_density` no longer owns the hard-coded effective/source time SQL JSON expression; it now consumes the shared `document_queries` boundary.

## Implemented

Code:

- `main/backend/app/services/document_queries/policy_filters.py`
  - Promoted the top-level extracted-data ISO date helper to `document_json_iso_date_expr(...)`.
  - Exposed `prompt_time_density_time_expr()` as the shared query expression for time-density consumers.
- `main/backend/app/services/document_queries/__init__.py`
  - Exported the new query helpers through the package boundary.
- `main/backend/app/services/stats/prompt_time_density.py`
  - Removed local `_json_iso_date_expr(...)` and `_effective_date_expr()`.
  - Uses `prompt_time_density_time_expr()` for the query-time date filter.
- `main/backend/scripts/check_structured_consumer_query_extraction.py`
  - Static checker that guards this Wave11 extraction without importing the full backend runtime.
- `main/backend/scripts/check_consumer_side_facade_contract.py`
  - Records `prompt_time_density.py` under extracted query surfaces rather than deferred query surfaces.

Tests:

- `main/backend/tests/unit/test_document_queries_policy_filters_unittest.py`
  - Confirms `document_json_iso_date_expr(...)` and `prompt_time_density_time_expr()` compile as SQL expressions.
  - Confirms the shared time-density expression preserves `effective_time`, `source_time`, and policy `effective_date` fallback semantics.
- `main/backend/tests/unit/test_consumer_side_facade_contract_unittest.py`
  - Confirms `prompt_time_density.py` stays out of deferred query surfaces after this extraction.

## Boundary Contract

The extracted query boundary is:

```text
main/backend/app/services/document_queries.prompt_time_density_time_expr
```

It remains part of the existing `document_queries.v1` direction: consumer services do not rebuild SQL JSON predicates locally when a shared document query helper exists.

This is intentionally narrow and does not change the stats API request or response shape.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave11-structured-consumer-extraction`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile \
  main/backend/app/services/document_queries/policy_filters.py \
  main/backend/app/services/document_queries/__init__.py \
  main/backend/app/services/stats/prompt_time_density.py \
  main/backend/scripts/check_structured_consumer_query_extraction.py
```

Result: passed.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_document_queries_contract.py
```

Result: `status=pass`, `contract_version=document_queries.v1`.

```bash
python3 main/backend/scripts/check_structured_consumer_query_extraction.py
```

Result: `status=passed`, `contract_version=document_queries.v1`.

```bash
python3 main/backend/scripts/check_consumer_side_facade_contract.py
```

Result: `status=passed`, `extracted_query_surfaces` includes `main/backend/app/services/stats/prompt_time_density.py`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_document_queries_policy_filters_unittest.py \
  main/backend/tests/unit/test_prompt_time_density_priority_unittest.py \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_consumer_side_facade_contract_unittest.py
```

Result: `16 passed`.

```bash
python3 scripts/check_current_dev_wave11_plan.py
```

Result: passed.

## Remaining Scope

- `admin.py` and `dashboard.py` still have additional query/Python read paths that should be handled in later small slices.
- This worker did not edit shared navigation indexes.
