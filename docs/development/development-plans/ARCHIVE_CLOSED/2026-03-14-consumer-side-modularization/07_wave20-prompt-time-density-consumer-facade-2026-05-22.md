# Wave20 Prompt Time Density Consumer Facade Evidence (2026-05-22)

## Status

- Topic: `2026-03-14-consumer-side-modularization`
- Branch: `codex/devdocs-wave20-consumer-facade-slice`
- Result: bounded prompt-time-density Python read facade slice landed.

This slice intentionally avoids the worker 6 document-query endpoint surface. It extends the consumer facade work on a different stats consumer boundary and does not claim live DB/API smoke closure.

## What Changed

`main/backend/app/services/stats/prompt_time_density.py` previously still owned Python-level `doc.extracted_data` reads for:

1. effective/source/policy time provenance;
2. prompt group selection;
3. source domain fallback.

Those reads now route through `main/backend/app/services/document_views/stats_view.py`:

1. `get_prompt_time_density_fields(...)`
2. `get_prompt_time_density_group(...)`
3. `get_prompt_time_density_source_domain(...)`

The query-time date expression remains in `document_queries.prompt_time_density_time_expr()`. This keeps Wave11's SQL query boundary intact while moving the remaining stats Python reads into `document_views`.

## Guardrail

Added `main/backend/scripts/check_prompt_time_density_consumer_boundary.py`.

The checker verifies:

1. `prompt_time_density.py` imports the required `document_views` helpers;
2. `resolve_document_effective_time_provenance(...)`, `_prompt_group_of(...)`, and `_source_domain_of(...)` call those helpers;
3. `prompt_time_density.py` has zero direct `.extracted_data` reads;
4. `document_views/stats_view.py` defines the required facade helpers.

Checker output is stored at:

```text
development/latest-dev-docs/automation-runs/wave20-consumer-facade-prompt-time-density/2026-05-22/prompt_time_density_consumer_boundary.json
```

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave20-consumer-facade-slice`:

```bash
python3 main/backend/scripts/check_prompt_time_density_consumer_boundary.py
```

Result: `status=passed`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_prompt_time_density_consumer_boundary_unittest.py \
  main/backend/tests/unit/test_document_views_unittest.py \
  main/backend/tests/unit/test_prompt_time_density_priority_unittest.py \
  main/backend/tests/unit/test_prompt_time_density_decision_log_contract_unittest.py
```

Result: `14 passed`.

## Remaining Scope

1. No live DB/API smoke was run or claimed in this slice.
2. Admin governance write paths still intentionally own raw `extracted_data` mutation.
3. Worker 6's document-query endpoint slice remains separate.
4. Full consumer-side modularization still needs broader endpoint/runtime regression coverage.
