# Command receipts

All commands ran from `/Users/wangyiliang/market-research-workflow` on 2026-09-06.

## Safe PostgreSQL fixture discovery

`test -n "${MRW_TEST_POSTGRES_URL:-}"`

Result: unset. No database connection was attempted.

## Focused tests

`env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=main/backend:src main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider main/backend/tests/unit/test_schema_startup_boundary_unittest.py main/backend/tests/unit/test_workflow_graph_import_boundary_unittest.py main/backend/tests/unit/test_workflow_graph_compiler_unittest.py main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/unit/test_workflow_graph_handoff_store_unittest.py main/backend/tests/integration/test_schema_startup_postgres_concurrency.py stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation/test_startup_preservation_witness.py`

Result: exit 0; `52 passed, 1 skipped, 28 warnings in 17.78s`. The skip is the guarded live PostgreSQL multi-process fixture.

## Ruff

`ruff check main/backend/app/services/projects/schema_initialization.py main/backend/app/celery_app.py main/backend/app/services/projects/bootstrap.py main/backend/scripts/_cli_runtime.py main/backend/tests/unit/test_schema_startup_boundary_unittest.py main/backend/tests/integration/test_schema_startup_postgres_concurrency.py`

Result: exit 0; `All checks passed!`.

`ruff check --ignore E501,UP017,UP034 main/backend/app/startup_hooks.py main/backend/app/services/workflow_graph/store.py`

Result: exit 0; `All checks passed!`. The exclusions are pre-existing findings in shared dirty code and are not used to hide findings in the new schema boundary.

## Compile and whitespace

`env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=main/backend:src main/backend/.venv311/bin/python -m compileall -q` on the eight changed Python surfaces.

Result: exit 0.

`git diff --check --` on the eight changed Python surfaces and this evidence directory.

Result: exit 0.
