# Wave27 Structured / Consumer Closure Decision (2026-05-23)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Paired consumer topic: `2026-03-14-consumer-side-modularization`
- Decision: `retained_partial`
- Gate: `main/backend/scripts/check_wave27_structured_consumer_closure.py`

Wave27 proves the endpoint/query/consumer facade slices are now covered by deterministic gates, but it does not migrate this structured topic out of `CURRENT_DEV`.

## What The Gate Covers

The combined checker passes these repo-local surfaces:

1. `structured_sql_helper_migration`
2. `structured_endpoint_projection`
3. `consumer_side_facade_contract`
4. `consumer_sql_predicate_facade`
5. `admin_dashboard_consumer_boundary`
6. `policy_state_document_query_boundary`
7. `prompt_time_density_consumer_boundary`

The structured endpoint projection covers both `/api/v1/search` and `project.structured_data.search`.

## Remaining Blocker

Wave28 update: this repo-local blocker has been closed by [14_wave28-structured-document-query-statement-builder-2026-05-23.md](./14_wave28-structured-document-query-statement-builder-2026-05-23.md). The historical Wave27 decision below explains why this directory stayed in `CURRENT_DEV` before the builder existed.

The remaining structured-service blocker is repo-local:

```text
generic_document_query_db_statement_builder_missing
```

No exported `DocumentQuery -> SQLAlchemy statement` builder was found under `main/backend/app/services/document_queries`. Existing endpoint/predicate helpers are covered, but the generic DB statement-builder scope remains a repo-local blocker if it is still required for this modularization topic.

The paired consumer-side topic is now separable: it has no Wave27 repo-local blocker and only retains live DB/API smoke as an external-runtime condition, so it was moved to `ARCHIVE_EXTERNAL_BLOCKED`.

## Evidence

- [automation-runs/wave27-structured-consumer-closure/2026-05-23/README.md](../../../automation-runs/wave27-structured-consumer-closure/2026-05-23/README.md)
- [automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json](../../../automation-runs/wave27-structured-consumer-closure/2026-05-23/structured_consumer_closure_decision.json)

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_wave27_structured_consumer_closure.py

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```

Observed result: checker passed; pytest `2 passed`.
