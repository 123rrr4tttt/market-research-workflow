# Wave20 Consumer Facade Prompt Time Density Evidence

- status: `passed`
- topic: `2026-03-14-consumer-side-modularization`
- branch: `codex/devdocs-wave20-consumer-facade-slice`
- contract_version: `prompt-time-density-consumer-facade.wave20.v1`
- scope: `repo_local_prompt_time_density_python_read_facade_only`

## Result

`main/backend/app/services/stats/prompt_time_density.py` no longer reads `doc.extracted_data` directly for Python-level consumer fields. It now uses `document_views` helpers for:

1. effective/source/policy time provenance fields;
2. prompt group selection;
3. source-domain fallback.

The SQL date predicate remains in `document_queries.prompt_time_density_time_expr`, preserving the Wave11 query boundary.

## Evidence

Machine-readable checker output:

- [`prompt_time_density_consumer_boundary.json`](./prompt_time_density_consumer_boundary.json)

Focused validation run:

```bash
python3 main/backend/scripts/check_prompt_time_density_consumer_boundary.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_prompt_time_density_consumer_boundary_unittest.py \
  main/backend/tests/unit/test_document_views_unittest.py \
  main/backend/tests/unit/test_prompt_time_density_priority_unittest.py \
  main/backend/tests/unit/test_prompt_time_density_decision_log_contract_unittest.py
```

Observed result: `14 passed`.

## Boundary

This is not a live DB/API smoke closure. It does not claim full consumer-side modularization, admin governance write cleanup, or worker 6 document-query endpoint coverage.
