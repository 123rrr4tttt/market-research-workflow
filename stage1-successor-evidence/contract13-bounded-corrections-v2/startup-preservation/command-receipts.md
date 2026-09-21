# Command receipts

All commands ran from `/Users/wangyiliang/market-research-workflow` on 2026-09-06.

## Contract and source binding

`shasum -a 256 development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/13_contract12-supervisor-review-and-return.v1.md`

Result: exit 0; `ac1629315b3ae91aa9de59b7ae87da04a5f10c54d643e406d8785a0783071717`.

`shasum -a 256 stage1-successor-evidence/residual-disposition-v1/effects/import-time-db-effects.v1.json`

Result: exit 0; `280d22ccdcc8850c68f14cb42e03182fba89419d859001707b9cdc1fad24c24f`.

## Existing focused selector

`env PYTHONPATH=main/backend:src main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_schema_startup_boundary_unittest.py main/backend/tests/unit/test_workflow_graph_import_boundary_unittest.py main/backend/tests/unit/test_workflow_graph_compiler_unittest.py main/backend/tests/unit/test_workflow_graph_runtime_unittest.py main/backend/tests/unit/test_workflow_graph_handoff_store_unittest.py`

Result: exit 0; `32 passed, 13 warnings in 9.89s`.

## Isolated witness

`env PYTHONPATH=main/backend:src main/backend/.venv311/bin/python -m pytest -q stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation/test_startup_preservation_witness.py`

Final result: exit 0; `12 passed, 10 warnings`.

## Lint

`main/backend/.venv311/bin/ruff check .../test_startup_preservation_witness.py`

Result: exit 127; `no such file or directory` (tool absent in this virtualenv).

`ruff check stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation/test_startup_preservation_witness.py`

Initial result: exit 1; file-level lint suppressions were then added for the repository-style late imports and test-only lambda/error idioms. Final result is recorded after rerun.

Final result: exit 0; `All checks passed!`.

## Final integrity checks

- JSON parse/shape assertion: exit 0; `JSON_PARSE_PASS checks=6 changed_paths=8`.
- `shasum -a 256 -c artifact-hashes.sha256`: exit 0; all five listed artifacts `OK` before this receipt's final integrity-note update.
- `git diff --check -- stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation`: exit 0; no whitespace errors.
- Cache scan after cleanup: no `__pycache__` directory remains under the owned evidence directory.
- Scoped status: one untracked create-only directory, `stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation/`; no shared runtime/test path was written by this task.
