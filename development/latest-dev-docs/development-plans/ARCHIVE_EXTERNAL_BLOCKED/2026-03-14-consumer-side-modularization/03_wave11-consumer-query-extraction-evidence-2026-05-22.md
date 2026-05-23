# Wave11 Consumer Query Extraction Evidence (2026-05-22)

## Status

- Topic: `2026-03-14-consumer-side-modularization`
- Shared slice: `2026-03-12-data-structured-service-modularization`
- Branch: `codex/devdocs-wave11-structured-consumer-extraction`
- Result: one remaining time-density consumer SQL JSON path was extracted from the consumer service into `document_queries`.

## What Changed

`main/backend/app/services/stats/prompt_time_density.py` previously owned a local SQL expression chain for:

- `Document.extracted_data["effective_time"]`
- `Document.extracted_data["source_time"]`
- policy `effective_date`
- publish/create fallback dates

That query path is now routed through:

```text
main/backend/app/services/document_queries.prompt_time_density_time_expr
```

This keeps `prompt_time_density` as the consumer service and moves query construction into the shared query boundary. The API endpoint layer is unchanged.

## Guardrail

Added `main/backend/scripts/check_structured_consumer_query_extraction.py`.

The checker verifies:

- `prompt_time_density.py` imports `prompt_time_density_time_expr` from `document_queries`.
- `query_prompt_time_density(...)` calls that boundary helper.
- Local `_json_iso_date_expr(...)` and `_effective_date_expr()` are absent from `prompt_time_density.py`.
- The local `Document.extracted_data[...]` SQL query path is absent from `prompt_time_density.py`.
- `document_queries/policy_filters.py` owns the exported helper and still contains the effective/source/policy date fallback terms.
- The existing consumer-side facade checker now records `prompt_time_density.py` as an extracted query surface, not a deferred query surface.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave11-structured-consumer-extraction`:

```bash
python3 main/backend/scripts/check_structured_consumer_query_extraction.py
```

Result: `status=passed`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_document_queries_contract.py
```

Result: `status=pass`, `contract_version=document_queries.v1`.

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

- This does not claim full consumer-side modularization closure.
- `admin.py` / `dashboard.py` still need later narrow extractions for their own SQL JSON and Python read surfaces.
- Shared indexes were intentionally left untouched for the Wave11 worker branch.
