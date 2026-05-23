# Wave28 Structured Document Query Statement Builder (2026-05-23)

## Status

- Topic: `2026-03-12-data-structured-service-modularization`
- Worker: structured worker A
- Previous repo-local blocker: `generic_document_query_db_statement_builder_missing`
- Result: blocker closed in repo-local code.

Wave28 adds the missing generic `DocumentQuery -> SQLAlchemy statement` boundary under `main/backend/app/services/document_queries/`. The topic no longer has a deterministic repo-local blocker in `check_wave27_structured_consumer_closure.py`; only live DB/API smoke remains external-runtime validation.

## Implemented

Code:

- `main/backend/app/services/document_queries/statement_builder.py`
  - `build_document_query_statement(query)`
  - `apply_document_query_to_statement(query, statement=None)`
  - `document_query_to_statement(query)`
  - `compile_document_query_statement(query_or_statement)`
- `main/backend/app/services/document_queries/__init__.py`
  - Exports the statement-builder boundary through the package API.

Checker updates:

- `main/backend/scripts/check_structured_sql_helper_migration.py`
  - Adds `document_query_statement_builder` to the covered structured SQL/query helper surfaces.
- `main/backend/scripts/check_wave27_structured_consumer_closure.py`
  - Dynamically builds and compiles a sample `DocumentQuery` with text search, project key, scalar filters, JSON-path filter, sort, limit, and offset.
  - Reports `generic_document_query_db_statement_builder` as `covered`.

Tests:

- `main/backend/tests/unit/test_document_queries_contracts_unittest.py`
  - Proves the builder compiles filters, JSON-path filters, sorting, pagination, and adapter use against an existing `select(Document)` statement.
- `main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py`
  - Proves the structured SQL helper checker tracks the new covered surface.
- `main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py`
  - Proves the structured topic now has no repo-local blocker and is eligible for external-blocked archive migration.

## Boundary

The builder is intentionally allowlist-based:

- Supported scalar fields include `id`, `document_id`, `source_id`, `state`, `doc_type`, `title`, `status`, `publish_date`, `published_at`, `content`, `summary`, `uri`, `url`, `created_at`, and `updated_at`.
- Supported JSON paths use `extracted_data.<path>`, compiled through SQLAlchemy JSON path expressions.
- Supported filter operators reuse `document_queries.v1`: `eq`, `in`, `contains`, `gte`, `lte`, and `exists`.
- Unsupported fields raise `ValueError` instead of interpolating raw SQL.

This closes the generic DB statement-builder blocker without changing existing API envelopes or endpoint response shapes.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_document_queries_contracts_unittest.py \
  main/backend/tests/unit/test_structured_sql_helper_migration_check_unittest.py \
  main/backend/tests/unit/test_wave27_structured_consumer_closure_unittest.py
```

Observed result after supervisor integration: `12 passed in 2.97s`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_structured_sql_helper_migration.py
```

Observed result: `status=passed`, `covered_surface_count=7`, `covered_surface_gap_count=0`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_wave27_structured_consumer_closure.py
```

Observed result: `status=passed`, `repo_local_blocker_count=0`, `document_query_statement_builder.status=covered`, `decision.status=external_blocked_candidate`.

## Remaining Scope

- No live DB/API stack was started by this worker.
- The remaining blocker is external-runtime only: `live_db_api_smoke_not_run`.
- The directory is now in `ARCHIVE_EXTERNAL_BLOCKED`; keep it there until live DB/API smoke can prove production-like behavior.
